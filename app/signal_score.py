"""Recount Signal score: pure, deterministic scoring of companies, funds and founders from Cala round data.

No web code and no file IO beyond `load_weights`. Every public function takes plain dicts/lists and an `as_of_t`
(decimal year). Only rounds with t < as_of_t are read, so the same code serves the live table (as_of = today) and the
point-in-time backtest (as_of = start of the year after a cutoff). See signal/DESIGN.md section 1.

Company score
    Signal   = round(100 * sum_i w_i * v_i), v_i in [0, 1], weights renormalised to sum 1.
    A component with no data counts as a visible neutral 0.5 ("no data, counted as neutral"); it is never imputed
    silently and never renormalised away (the old renormalisation let one known binary fact score 1.0).
    Evidence (how much Cala data backs the number) is a separate 0..1 value and never blended into Signal.
    A company is ranked only when its last equity round has a stage; the others stay listed as "Not enough data".

Inputs (`ScoreInputs`)
    rounds          snapshot rounds (merge.Builder.snapshot shape: id, ckey, company, country, t, year, month, stage,
                    amount_eur_m, leads, participants, query_path, sources, not_led, disputed)
    investor_names  {investor_key: display name}
    fund_keys       the investors Cala was asked investor-first (the "queried funds")
    exits           [{"fund_key", "ckey", "year"}] acquisition receipts per backing fund
    checked_funds   fund keys whose exits were looked up (a backer outside this set is "not checked", not "no exit")
    sectors         {ckey: [sector tag, ...]} Cala sector tags (only needed for the conditional sector component)
"""
from __future__ import annotations

import bisect
import hashlib
import json
import math
import re
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from engine import CROSSOVERS, HUBS
from explore_shapes import country as norm_country
from merge import _date_precision, company_key
from parse import FIRST_NAMES, FUNDISH

VERSION = "signal-1"
NOW_T = 2026.87  # 14 Nov 2026, same as engine.Snapshot.now_t
STAGE_ORDER = ["pre-seed", "seed", "series a", "series b", "series c", "series d", "series e", "series f", "growth"]
STAGE_IX = {s: i for i, s in enumerate(STAGE_ORDER)}
EARLY = {"pre-seed", "seed", "series a"}
LATE = {"series b", "series c", "series d", "series e", "series f", "growth"}
COLLAPSE_YEARS = 0.25  # rounds under 3 months apart are one raise for gap-based components
MIN_PEERS = 15
NEUTRAL = 0.5

# key, label, tier, default weight, cap. Tier: measured | thesis | conditional (DESIGN.md 1.1).
COMPONENTS = [
    ("size_for_stage", "Size for stage", "measured", 0.40, 0.60),
    ("syndicate_breadth", "Syndicate breadth", "measured", 0.20, 0.60),
    ("lead_named", "Cala names a lead", "measured", 0.12, 0.60),
    ("acceleration", "Acceleration", "measured", 0.05, 0.60),
    ("backer_graduation", "Backer graduation rate", "thesis", 0.06, 0.15),
    ("insider_follow_on", "Insiders came back", "thesis", 0.03, 0.15),
    ("named_angels", "Named operator angels", "thesis", 0.03, 0.15),
    ("lead_supply", "Next-stage lead supply at home", "thesis", 0.03, 0.15),
    ("cross_border", "Foreign backers", "thesis", 0.02, 0.15),
    ("step_up", "Step-up on last raise", "thesis", 0.02, 0.15),
    ("backer_exits", "Backers with exit receipts", "thesis", 0.02, 0.15),
    ("freshness", "On the stage clock", "thesis", 0.02, 0.15),
    ("sector_heat", "Sector momentum", "conditional", 0.00, 0.15),
]
KEYS = [c[0] for c in COMPONENTS]
LABEL = {c[0]: c[1] for c in COMPONENTS}
TIER = {c[0]: c[2] for c in COMPONENTS}
DEFAULT_WEIGHTS = {c[0]: c[3] for c in COMPONENTS}
CAP = {c[0]: c[4] for c in COMPONENTS}
THESIS_TOTAL_CAP = 0.30
SECTOR_MIN = 0.05

FUND_COMPONENTS = [("lead_pace", "Leads lately", 0.50), ("lead_share", "Leads when it invests", 0.30),
                   ("stage_fit", "Leads at your stage", 0.20)]
FUND_LABEL = "How actively this fund leads, not how well it picks."
FOUNDER_FACTS = ["dated role", "earlier Cala company", "prior exit", "cohort match"]

DUP_SUFFIX = re.compile(r"(ab|oy|gmbh|ltd|inc|sas|bv|as|aps|technologies|technology|tech|ai|labs|health|therapeutics|"
                        r"group|io|app|hq)$")


# ---------------------------------------------------------------- weights
def load_weights(path: Optional[Path] = None) -> dict[str, float]:
    """Default weights from signal_weights.json next to this file; DEFAULT_WEIGHTS when the file is absent."""
    p = path or Path(__file__).with_name("signal_weights.json")
    if not p.exists():
        return dict(DEFAULT_WEIGHTS)
    w = json.loads(p.read_text())["weights"]
    unknown = set(w) - set(KEYS)
    if unknown:
        raise ValueError(f"unknown components in {p.name}: {sorted(unknown)}")
    return {k: float(w.get(k, 0.0)) for k in KEYS}


def clamp_weights(overrides: Optional[dict] = None, base: Optional[dict] = None,
                  sector_active: bool = False) -> dict[str, float]:
    """Apply overrides on base, clamp to caps (thesis 0.15 each, 0.30 total; sector only with a sector filter),
    renormalise to sum 1. Raises ValueError on unknown keys or negative or non-numeric values."""
    w = dict(base or DEFAULT_WEIGHTS)
    for k, v in (overrides or {}).items():
        if k not in CAP:
            raise ValueError(f"unknown component '{k}'")
        if isinstance(v, bool) or not isinstance(v, (int, float)) or math.isnan(v) or v < 0:
            raise ValueError(f"weight for '{k}' must be a number >= 0")
        w[k] = float(v)
    for k in KEYS:
        w[k] = min(max(w.get(k, 0.0), 0.0), CAP[k])
    if not sector_active:
        w["sector_heat"] = 0.0
    elif 0 < w["sector_heat"] < SECTOR_MIN:
        w["sector_heat"] = SECTOR_MIN
    thesis = sum(w[k] for k in KEYS if TIER[k] == "thesis")
    if thesis > THESIS_TOTAL_CAP:
        for k in KEYS:
            if TIER[k] == "thesis":
                w[k] *= THESIS_TOTAL_CAP / thesis
    total = sum(w.values())
    if total <= 0:
        raise ValueError("all weights are zero")
    return {k: w[k] / total for k in KEYS}


def rules_hash(weights: dict[str, float]) -> str:
    blob = json.dumps({"v": VERSION, "w": {k: round(weights.get(k, 0.0), 4) for k in KEYS}}, sort_keys=True)
    return "sig-" + hashlib.sha1(blob.encode()).hexdigest()[:8]


# ---------------------------------------------------------------- small helpers
def is_hub(k: str) -> bool:
    """Public bodies and programmes never count as investors (engine.HUBS)."""
    return k in HUBS or any(k.startswith(h + " ") for h in HUBS)


def is_equity(r: dict) -> bool:
    return not r.get("not_led") and not r.get("disputed")


def investors(r: dict) -> list[str]:
    """Distinct named investors of a round (leads first), public bodies removed."""
    return [k for k in dict.fromkeys(list(r.get("leads") or []) + list(r.get("participants") or [])) if not is_hub(k)]


def names_anyone(r: dict) -> bool:
    return bool(r.get("leads") or r.get("participants"))


def is_person(name: str) -> bool:
    """'Johan Brenner': 2 to 3 capitalised words, a known first name, no fund word."""
    toks = name.split()
    words = [re.sub(r"[^\w]", "", t.lower()) for t in toks]
    return (2 <= len(toks) <= 3 and words[0] in FIRST_NAMES and all(t[:1].isupper() for t in toks)
            and all(w.isalpha() for w in words) and not any(w in FUNDISH for w in words))


def midrank_pct(v: float, pool_sorted: list[float]) -> float:
    lo = bisect.bisect_left(pool_sorted, v)
    hi = bisect.bisect_right(pool_sorted, v)
    return (lo + 0.5 * (hi - lo)) / len(pool_sorted)


def collapse(rs: list[dict]) -> list[list[dict]]:
    """Group rounds (sorted by t) into raises: a round under 3 months after the group's first round joins it."""
    out: list[list[dict]] = []
    for r in rs:
        if out and r["t"] - out[-1][0]["t"] < COLLAPSE_YEARS:
            out[-1].append(r)
        else:
            out.append([r])
    return out


def ordinal(n: int) -> str:
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def next_stage(s: str) -> str:
    i = STAGE_IX[s]
    return STAGE_ORDER[min(i + 1, len(STAGE_ORDER) - 1)]


def possible_duplicates(ckeys: Iterable[str]) -> set[str]:
    """Suffix twins such as 'baichuan' and 'baichuanai': every member of a group with 2+ keys."""
    groups: dict[str, list[str]] = defaultdict(list)
    for k in ckeys:
        groups[DUP_SUFFIX.sub("", k) or k].append(k)
    return {k for v in groups.values() if len(v) > 1 for k in v}


# ---------------------------------------------------------------- inputs and point-in-time context
@dataclass
class ScoreInputs:
    rounds: list[dict]
    investor_names: dict[str, str]
    fund_keys: set[str]
    exits: list[dict] = field(default_factory=list)
    checked_funds: set[str] = field(default_factory=set)
    sectors: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class Context:
    """Everything derived from rounds with t < as_of_t. Built once per as_of, shared by all companies."""
    inp: ScoreInputs
    as_of_t: float
    by_company: dict[str, list[dict]]          # equity rounds before as_of, sorted
    disputed: set[str]
    full_history: set[str]
    country_of: dict[str, Optional[str]]
    size_pools: dict[tuple[str, int], list[float]]
    size_recent: dict[str, list[float]]
    fund_country: dict[str, Optional[str]]
    grad: dict[str, tuple[int, int]]           # investor -> (entries, hits) over observable early entries
    grad_own: dict[tuple[str, str], tuple[int, int]]
    grad_p0: float
    leads_by_stage_country: dict[tuple[str, str], set[str]]
    stage_gap_median: dict[str, float]
    exits_by_fund: dict[str, set[str]]
    acquired: set[str]
    sector_heat: dict[str, float]


def build_context(inp: ScoreInputs, as_of_t: float = NOW_T) -> Context:
    eq = sorted((r for r in inp.rounds if r["t"] < as_of_t and is_equity(r)), key=lambda r: (r["t"], r["id"]))
    by_c: dict[str, list[dict]] = defaultdict(list)
    for r in eq:
        by_c[r["ckey"]].append(r)
    disputed = {r["ckey"] for r in inp.rounds if r.get("disputed") and r["t"] < as_of_t}
    full = {r["ckey"] for r in inp.rounds if r.get("query_path") in ("company_first", "both")}

    country_of = {}
    for ck, rs in by_c.items():
        cs = Counter(c for c in (norm_country(r.get("country")) for r in rs) if c)
        country_of[ck] = sorted(cs.items(), key=lambda x: (-x[1], x[0]))[0][0] if cs else None

    size_pools: dict[tuple[str, int], list[float]] = defaultdict(list)
    size_recent: dict[str, list[float]] = defaultdict(list)
    for r in eq:
        if r.get("stage") and r.get("amount_eur_m"):
            size_pools[(r["stage"], r["year"])].append(r["amount_eur_m"])
            if r["t"] >= as_of_t - 4:
                size_recent[r["stage"]].append(r["amount_eur_m"])
    for v in list(size_pools.values()) + list(size_recent.values()):
        v.sort()

    fc: dict[str, Counter] = defaultdict(Counter)
    for r in eq:
        c = norm_country(r.get("country"))
        if c:
            for k in investors(r):
                if k in inp.fund_keys:
                    fc[k][c] += 1
    fund_country = {k: sorted(v.items(), key=lambda x: (-x[1], x[0]))[0][0] for k, v in fc.items()}

    # backer graduation: an early entry (pre-seed, seed, A) is observable when its 24 month window closed before as_of
    grad: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    grad_own: dict[tuple[str, str], tuple[int, int]] = {}
    tot = [0, 0]
    for ck, rs in by_c.items():
        first_entry: dict[str, float] = {}
        for r in rs:
            if r.get("stage") in EARLY:
                for k in investors(r):
                    first_entry.setdefault(k, r["t"])
        for k, te in first_entry.items():
            if te + 2 > as_of_t:
                continue
            hit = int(any(te + COLLAPSE_YEARS <= x["t"] <= te + 2 for x in rs))
            grad[k][0] += 1
            grad[k][1] += hit
            grad_own[(k, ck)] = (1, hit)
            tot[0] += 1
            tot[1] += hit
    p0 = tot[1] / tot[0] if tot[0] else 0.5

    lsc: dict[tuple[str, str], set[str]] = defaultdict(set)
    for r in eq:
        c = norm_country(r.get("country"))
        if c and r.get("stage") and r["t"] >= as_of_t - 3:
            for k in r.get("leads") or []:
                if not is_hub(k):
                    lsc[(r["stage"], c)].add(k)

    gaps: dict[str, list[float]] = defaultdict(list)
    for rs in by_c.values():
        raises = collapse([r for r in rs if _date_precision(r) >= 2])
        for a, b in zip(raises, raises[1:]):
            st = next((r["stage"] for r in a if r.get("stage")), None)
            if st:
                gaps[st].append((b[0]["t"] - a[0]["t"]) * 12)
    gap_med = {s: statistics.median(v) for s, v in gaps.items() if len(v) >= 5}

    ex: dict[str, set[str]] = defaultdict(set)
    acquired = set()
    for e in inp.exits:
        if e.get("year") is not None and e["year"] < as_of_t:
            ex[e["fund_key"]].add(e["ckey"])
            acquired.add(e["ckey"])

    heat = _sector_heat(inp.sectors, eq, as_of_t)
    return Context(inp, as_of_t, dict(by_c), disputed, full, country_of, dict(size_pools), dict(size_recent),
                   fund_country, {k: (v[0], v[1]) for k, v in grad.items()}, grad_own, p0, dict(lsc), gap_med,
                   dict(ex), acquired, heat)


def _sector_heat(sectors: dict[str, list[str]], eq: list[dict], as_of_t: float) -> dict[str, float]:
    """{sector: (rounds 24m + 3)/(prior 24m + 3), relative to all tagged rounds}."""
    if not sectors:
        return {}
    now, prior = Counter(), Counter()
    for r in eq:
        for s in sectors.get(r["ckey"], []):
            if as_of_t - 2 <= r["t"]:
                now[s] += 1
            elif as_of_t - 4 <= r["t"]:
                prior[s] += 1
    all_ratio = (sum(now.values()) + 3) / (sum(prior.values()) + 3)
    return {s: ((now[s] + 3) / (prior[s] + 3)) / all_ratio for s in set(now) | set(prior)}


# ---------------------------------------------------------------- components
def _comp(present: bool, raw=None, value=None, records=None, missing=None, peer=None, text=None, pct_pool=None) -> dict:
    """pct_pool: when set, `value` is filled later as a mid-rank percentile of `raw["x"]` within that cohort pool."""
    return {"present": present, "raw": raw or {}, "value": value, "records": records or [], "missing_reason": missing,
            "peer_group": peer, "text": text, "pct_pool": pct_pool}


def _rid(r: dict) -> dict:
    return {"round_id": r["id"], "date": f"{r['year']}-{(r.get('month') or 1):02d}", "stage": r.get("stage"),
            "amount_eur_m": r.get("amount_eur_m")}


def company_components(ctx: Context, ck: str) -> dict[str, dict]:
    """Raw component dicts for one company. Percentile components carry pct_pool and get their value in score_all."""
    rs = ctx.by_company.get(ck, [])
    names = ctx.inp.investor_names
    out: dict[str, dict] = {}
    last = rs[-1] if rs else None
    stage = last.get("stage") if last else None
    t = ctx.as_of_t

    # 1 size for stage
    sized = [r for r in rs if r.get("stage") and r.get("amount_eur_m")]
    if not sized:
        out["size_for_stage"] = _comp(False, missing="no round with both a stage and an amount")
    else:
        r = sized[-1]
        pool = sorted(a for y in (r["year"] - 1, r["year"], r["year"] + 1) for a in ctx.size_pools.get((r["stage"], y), []))
        label = f"{r['stage']} rounds {r['year'] - 1} to {min(r['year'] + 1, int(t))}"
        kind = "stage_year"
        if len(pool) < MIN_PEERS:
            pool, kind = ctx.size_recent.get(r["stage"], []), "stage_4y"
            label = f"{r['stage']} rounds in the 4 years before {int(t)}"
        peer = {"kind": kind, "label": label, "n": len(pool)}
        if len(pool) < MIN_PEERS:
            out["size_for_stage"] = _comp(False, raw={"amount_eur_m": r["amount_eur_m"], "stage": r["stage"]},
                                          records=[_rid(r)], missing=f"not enough peers ({len(pool)} under {MIN_PEERS})",
                                          peer=peer)
        else:
            v = midrank_pct(r["amount_eur_m"], pool)
            word = "Big" if v >= 0.5 else "Small"
            out["size_for_stage"] = _comp(True, raw={"amount_eur_m": r["amount_eur_m"], "stage": r["stage"]}, value=v,
                                          records=[_rid(r)], peer=peer,
                                          text=f"{word} for its stage: {ordinal(min(99, max(1, round(100 * v))))} pct of {label} (n {len(pool)})")

    # 2 syndicate breadth, 3 lead named
    if not last or not names_anyone(last):
        out["syndicate_breadth"] = _comp(False, missing="the last round names no investor")
        out["lead_named"] = _comp(False, missing="the last round names no investor")
    else:
        k = len(investors(last))
        out["syndicate_breadth"] = _comp(True, raw={"x": math.log2(1 + min(k, 12)), "named_investors": k},
                                         records=[_rid(last)], text=f"{k} named investors on the last round",
                                         pct_pool="cohort")
        ln = bool(last.get("leads"))
        lead_names = [names.get(x, x) for x in last.get("leads") or []]
        out["lead_named"] = _comp(True, raw={"lead_named": ln, "leads": lead_names}, value=1.0 if ln else 0.0,
                                  records=[_rid(last)],
                                  text=f"Cala names a lead: {', '.join(lead_names[:2])}" if ln else "Cala names no lead")

    raises = collapse([r for r in rs if _date_precision(r) >= 2])
    # 4 acceleration
    if len(raises) < 3:
        out["acceleration"] = _comp(False, missing=f"needs 3 or more dated raises; Cala has {len(raises)}")
    else:
        g1 = raises[-2][0]["t"] - raises[-3][0]["t"]
        g2 = raises[-1][0]["t"] - raises[-2][0]["t"]
        x = max(-2.0, min(2.0, math.log2(g1 / g2)))
        out["acceleration"] = _comp(True, raw={"prev_gap_months": round(g1 * 12), "last_gap_months": round(g2 * 12)},
                                    value=(x + 2) / 4, records=[_rid(g[0]) for g in raises[-3:]],
                                    text=f"Last gap {round(g2 * 12)} months vs {round(g1 * 12)} before")

    backers = sorted({k for r in rs for k in investors(r)})
    # 5 backer graduation
    best = None
    for b in backers:
        n, h = ctx.grad.get(b, (0, 0))
        on, oh = ctx.grad_own.get((b, ck), (0, 0))
        n, h = n - on, h - oh
        if n >= 3:
            rate = (h + 5 * ctx.grad_p0) / (n + 5)
            if best is None or rate > best[0] or (rate == best[0] and b < best[1]):
                best = (rate, b, h, n)
    if best is None:
        out["backer_graduation"] = _comp(False, missing="no backer with 3 or more early bets whose 24 months have passed")
    else:
        rate, b, h, n = best
        out["backer_graduation"] = _comp(True, raw={"x": rate, "backer": names.get(b, b), "k": h, "n": n,
                                                    "prior": round(ctx.grad_p0, 3)},
                                         records=[{"investor": b}], pct_pool="cohort",
                                         text=f"{names.get(b, b)}: {h} of {n} early bets raised again within 24 months")

    # 6 insiders came back
    if len(raises) < 2:
        out["insider_follow_on"] = _comp(False, missing="needs 2 raises")
    else:
        prev = {k for r in raises[-2] for k in investors(r)}
        cur = {k for r in raises[-1] for k in investors(r)}
        if not prev:
            out["insider_follow_on"] = _comp(False, missing="the previous raise names no investor")
        else:
            back = sorted(prev & cur)
            out["insider_follow_on"] = _comp(True, raw={"came_back": [names.get(x, x) for x in back], "of": len(prev)},
                                             value=len(back) / len(prev), records=[_rid(raises[-1][0])],
                                             text=f"{len(back)} of {len(prev)} earlier investors came back")

    # 7 named angels (upward only: no angel found is "no data", never a penalty)
    angels = [b for b in backers if is_person(names.get(b, b))]
    if not angels:
        out["named_angels"] = _comp(False, missing="no person-named backer found (name heuristic)")
    else:
        v = NEUTRAL + NEUTRAL * min(math.log2(1 + len(angels)), 3) / 3
        out["named_angels"] = _comp(True, raw={"angels": [names.get(a, a) for a in angels]}, value=v,
                                    records=[{"investor": a} for a in angels], text=f"{len(angels)} named angel backers")

    # 8 next-stage lead supply at home
    c = ctx.country_of.get(ck)
    if not stage or not c:
        out["lead_supply"] = _comp(False, missing="no stage or no country")
    else:
        ns = next_stage(stage)
        leads = sorted(ctx.leads_by_stage_country.get((ns, c), set()))
        out["lead_supply"] = _comp(True, raw={"x": math.log1p(len(leads)), "funds": len(leads), "next_stage": ns,
                                              "country": c, "lead_desert": len(leads) <= 2},
                                   records=[{"investor": k} for k in leads[:20]], pct_pool="cohort",
                                   text=f"{len(leads)} funds led {ns} rounds in {c} in the last 36 months")

    # 9 cross border
    qb = [b for b in backers if b in ctx.fund_country]
    if not c or not qb:
        out["cross_border"] = _comp(False, missing="no country, or no backer with a known home market")
    else:
        foreign = [b for b in qb if ctx.fund_country[b] != c]
        out["cross_border"] = _comp(True, raw={"foreign": [names.get(b, b) for b in foreign], "of": len(qb)},
                                    value=len(foreign) / len(qb), records=[{"investor": b} for b in foreign],
                                    text=f"{len(foreign)} of {len(qb)} queried backers are mostly active outside {c}")

    # 10 step up
    sized_raises = [max((r for r in g if r.get("amount_eur_m")), key=lambda r: r["amount_eur_m"])
                    for g in collapse(rs) if any(r.get("amount_eur_m") for r in g)]
    if len(sized_raises) < 2:
        out["step_up"] = _comp(False, missing="needs 2 sized raises")
    else:
        a, b = sized_raises[-2], sized_raises[-1]
        ratio = b["amount_eur_m"] / a["amount_eur_m"]
        out["step_up"] = _comp(True, raw={"ratio": round(ratio, 2)}, value=max(0.25, min(1.0, (math.log2(ratio) + 1) / 4)),
                               records=[_rid(a), _rid(b)], text=f"Last raise {ratio:.1f}x the previous")

    # 11 backer exits
    checked = [b for b in backers if b in ctx.inp.checked_funds]
    if not checked:
        out["backer_exits"] = _comp(False, missing="not checked: no backer is among the funds with exit lookups")
    else:
        exited = sorted({e for b in checked for e in ctx.exits_by_fund.get(b, set()) if e != ck})
        out["backer_exits"] = _comp(True, raw={"exits": len(exited), "checked_backers": len(checked)},
                                    value=min(1.0, math.log1p(len(exited)) / math.log1p(4)),
                                    records=[{"exited_company": e} for e in exited[:20]],
                                    text=f"Backers hold {len(exited)} exit receipts" if exited
                                    else "No exit found for checked backers (does not mean no exit)")

    # 12 freshness
    med = ctx.stage_gap_median.get(stage) if stage else None
    if not last or not med:
        out["freshness"] = _comp(False, missing="no stage or too few gaps for this stage")
    else:
        months = (t - last["t"]) * 12
        r = months / med
        v = 1.0 if r <= 1 else max(0.0, 1 - (r - 1) / 2)
        out["freshness"] = _comp(True, raw={"months_since": round(months), "stage_median_gap": round(med)}, value=v,
                                 records=[_rid(last)],
                                 text=f"{round(months)} months since last raise; {stage} median gap {round(med)}")

    # 13 sector heat (conditional)
    tags = [s for s in ctx.inp.sectors.get(ck, []) if s in ctx.sector_heat]
    if not tags:
        out["sector_heat"] = _comp(False, missing="no Cala sector tag")
    else:
        s = max(tags, key=lambda x: (ctx.sector_heat[x], x))
        h = ctx.sector_heat[s]
        out["sector_heat"] = _comp(True, raw={"x": math.log(h), "sector": s, "heat": round(h, 2)}, pct_pool="tagged",
                                   text=f"{s} rounds at {h:.1f}x the prior 24 months, relative to all tagged rounds")
    return out


def evidence(ctx: Context, ck: str, coverage_weighted: float, duplicate: bool) -> dict:
    rs = ctx.by_company.get(ck, [])
    src = sum(len(r.get("sources") or []) for r in rs)
    indep = min(1.0, max(0, src - 1) / 3 + (0.25 if ck in ctx.full_history else 0.0))
    age_m = (ctx.as_of_t - rs[-1]["t"]) * 12 if rs else 999
    recency = 1.0 if age_m <= 12 else max(0.0, 1 - (age_m - 12) / 36)
    dq = sum(1 for r in rs if _date_precision(r) >= 2) / len(rs) if rs else 0.0
    v = 0.30 * coverage_weighted + 0.35 * indep + 0.20 * recency + 0.15 * dq
    if duplicate or ck in ctx.disputed:
        v = min(v, 0.5)
    band = "solid" if v >= 0.65 else "some" if v >= 0.40 else "thin"
    return {"value": round(v, 3), "band": band,
            "parts": {"coverage": round(coverage_weighted, 3), "independence": round(indep, 3),
                      "recency": round(recency, 3), "date_quality": round(dq, 3)}}


def combine(comps: dict[str, dict], weights: dict[str, float]) -> dict:
    """Signal from component values. Missing = neutral 0.5, shown; weights must already sum to 1."""
    total, parts = 0.0, []
    for k in KEYS:
        c = comps[k]
        w = weights.get(k, 0.0)
        v = c["value"] if c["present"] and c["value"] is not None else NEUTRAL
        total += w * v
        parts.append({"key": k, "label": LABEL[k], "tier": TIER[k], "weight": round(w, 4),
                      "present": bool(c["present"] and c["value"] is not None), "value": round(v, 4),
                      "points": round(w * (v - NEUTRAL) * 100, 2), "raw": c["raw"], "records": c["records"],
                      "peer_group": c["peer_group"], "missing_reason": c["missing_reason"], "text": c["text"]})
    active = [p for p in parts if p["weight"] > 0]
    cov = {"k": sum(1 for p in active if p["present"]), "n": len(active),
           "weighted": round(sum(p["weight"] for p in active if p["present"]), 4)}
    return {"raw_score": total, "score": round(100 * total), "components": parts, "coverage": cov}


def _fill_percentiles(ctx: Context, comps: dict[str, dict[str, dict]], cohort: dict[str, tuple]) -> None:
    """Percentile components: mid-rank within (history stratum, last stage), falling back to last stage alone when the
    cohort has under 15 values; 'tagged' components rank within all tagged companies."""
    pools: dict[tuple, list[float]] = defaultdict(list)
    for ck, cc in comps.items():
        for k, c in cc.items():
            if c["present"] and c["pct_pool"]:
                if c["pct_pool"] == "tagged":
                    pools[(k, "tagged")].append(c["raw"]["x"])
                elif ck in cohort:
                    pools[(k,) + cohort[ck]].append(c["raw"]["x"])
                    pools[(k, "stage", cohort[ck][1])].append(c["raw"]["x"])
    for v in pools.values():
        v.sort()
    for ck, cc in comps.items():
        for k, c in cc.items():
            if not (c["present"] and c["pct_pool"]):
                continue
            if c["pct_pool"] == "tagged":
                pool, label = pools[(k, "tagged")], "all companies with a Cala sector tag"
            elif ck not in cohort:
                c.update(present=False, missing_reason="unranked: no stage on the last round")
                continue
            else:
                full, st = cohort[ck]
                pool = pools[(k,) + cohort[ck]]
                label = f"{st} companies, {'full history' if full else 'seen via investors'}"
                if len(pool) < MIN_PEERS:
                    pool, label = pools[(k, "stage", st)], f"{st} companies"
            if len(pool) < MIN_PEERS:
                c.update(present=False, missing_reason=f"not enough peers ({len(pool)} under {MIN_PEERS})")
                continue
            c["value"] = midrank_pct(c["raw"]["x"], pool)
            c["peer_group"] = {"kind": "cohort", "label": label, "n": len(pool)}


@dataclass
class ScoreRun:
    as_of_t: float
    weights: dict[str, float]
    rules_hash: str
    rows: dict[str, dict]          # ckey -> scored row
    ranked: list[str]              # ckeys, best first


@dataclass
class Prepared:
    """Weight-independent part of a score run: components with percentiles filled. Built once, ranked many times."""
    ctx: Context
    comps: dict[str, dict[str, dict]]
    cohort: dict[str, tuple]
    dups: set[str]


def prepare(inp: ScoreInputs, as_of_t: float = NOW_T, ctx: Optional[Context] = None) -> Prepared:
    ctx = ctx or build_context(inp, as_of_t)
    dups = possible_duplicates(ctx.by_company)
    comps = {ck: company_components(ctx, ck) for ck in sorted(ctx.by_company)}
    cohort = {ck: (ck in ctx.full_history, ctx.by_company[ck][-1]["stage"])
              for ck in comps if ctx.by_company[ck][-1].get("stage")}
    _fill_percentiles(ctx, comps, cohort)
    return Prepared(ctx, comps, cohort, dups)


def score_all(inp: ScoreInputs, as_of_t: float = NOW_T, weights: Optional[dict[str, float]] = None,
              ctx: Optional[Context] = None, companies: Optional[Iterable[str]] = None) -> ScoreRun:
    """Score every company with an equity round before as_of. Deterministic: same inputs, same output.

    weights: an effective weight set (use clamp_weights); defaults to load_weights() renormalised.
    companies: optional subset to return (percentiles are still formed over everyone)."""
    return rank(prepare(inp, as_of_t, ctx), weights, companies)


def rank(prep: Prepared, weights: Optional[dict[str, float]] = None,
         companies: Optional[Iterable[str]] = None) -> ScoreRun:
    """Combine prepared components with one weight set, rank, band. Cheap enough to run per request."""
    ctx, comps, cohort, dups = prep.ctx, prep.comps, prep.cohort, prep.dups
    w = weights if weights is not None else clamp_weights(base=load_weights())
    if abs(sum(w.values()) - 1) > 1e-6:
        raise ValueError("weights must sum to 1; pass them through clamp_weights")

    rows = {}
    for ck, cc in comps.items():
        comb = combine(cc, w)
        rs = ctx.by_company[ck]
        flags = [f for f, on in (("possible_duplicate", ck in dups), ("already_acquired", ck in ctx.acquired),
                                 ("disputed_round", ck in ctx.disputed)) if on]
        ev = evidence(ctx, ck, comb["coverage"]["weighted"], ck in dups)
        why = sorted((p for p in comb["components"] if p["points"] > 0 and p["text"]), key=lambda p: (-p["points"], p["key"]))
        rows[ck] = {"ckey": ck, "name": rs[-1]["company"], "country": ctx.country_of.get(ck),
                    "history_depth": "full_history" if ck in ctx.full_history else "investor_first",
                    "last_stage": rs[-1].get("stage"), "ranked": ck in cohort,
                    "score": comb["score"] if ck in cohort else None,
                    "raw_score": comb["raw_score"] if ck in cohort else None,
                    "score_reason": None if ck in cohort else "Not enough data: no stage on the last round",
                    "components": comb["components"], "coverage": comb["coverage"], "evidence": ev, "flags": flags,
                    "why": [{"key": p["key"], "text": p["text"], "points": p["points"]} for p in why[:2]],
                    "last_round": _rid(rs[-1])}

    ranked = sorted((ck for ck in rows if rows[ck]["ranked"]), key=lambda k: (-rows[k]["raw_score"], k))
    n = len(ranked)
    i = 0
    while i < n:  # ties share the best rank
        j = i
        while j < n and rows[ranked[j]]["raw_score"] == rows[ranked[i]]["raw_score"]:
            j += 1
        for k in ranked[i:j]:
            rows[k]["rank"] = i + 1
            top = 1 - i / n  # share of ranked companies at or below this score
            rows[k]["percentile"] = round(top, 4)
            if i < math.ceil(0.1 * n):
                rows[k]["band"] = "strong" if rows[k]["evidence"]["band"] == "solid" else "promising"
            elif i < math.ceil(0.4 * n):
                rows[k]["band"] = "watch"
            else:
                rows[k]["band"] = "low"
        i = j
    for ck, r in rows.items():
        if not r["ranked"]:
            r.update(rank=None, percentile=None, band="not_enough_data", rank_in_cohort=None, cohort_size=None)
    by_cohort: dict[tuple, list[str]] = defaultdict(list)
    for ck in ranked:  # already best first
        by_cohort[cohort[ck]].append(ck)
    for members in by_cohort.values():
        for i, ck in enumerate(members):
            rows[ck]["rank_in_cohort"] = i + 1
            rows[ck]["cohort_size"] = len(members)
    if companies is not None:
        keep = set(companies)
        rows = {k: v for k, v in rows.items() if k in keep}
        ranked = [k for k in ranked if k in keep]
    return ScoreRun(ctx.as_of_t, w, rules_hash(w), rows, ranked)


# ---------------------------------------------------------------- funds
def fund_scores(inp: ScoreInputs, as_of_t: float = NOW_T, stage: str = "seed") -> dict[str, dict]:
    """Descriptive activity score for queried funds only. Other investors: score None with a reason."""
    if stage not in STAGE_IX:
        raise ValueError(f"unknown stage '{stage}'")
    eq = [r for r in inp.rounds if r["t"] < as_of_t and is_equity(r)]
    led24, ledprior, led_stage, led_known, joined_known, last_lead = (Counter(), Counter(), Counter(), Counter(),
                                                                       Counter(), {})
    for r in eq:
        leads = set(r.get("leads") or [])
        for k in leads:
            if as_of_t - 2 <= r["t"]:
                led24[k] += 1
            elif as_of_t - 4 <= r["t"]:
                ledprior[k] += 1
            if r.get("stage") == stage and as_of_t - 4 <= r["t"]:
                led_stage[k] += 1
            led_known[k] += 1
            last_lead[k] = max(last_lead.get(k, 0), r["t"])
        if leads:
            for k in set(r.get("participants") or []) - leads:
                joined_known[k] += 1
    q = sorted(inp.fund_keys)
    pace_pool = sorted(led24[k] for k in q)
    stage_pool = sorted(led_stage[k] for k in q)
    out = {}
    for k in inp.investor_names:
        nm = inp.investor_names[k]
        if k not in inp.fund_keys:
            out[k] = {"key": k, "name": nm, "queried": False, "score": None,
                      "score_reason": "not enough data: seen only as a co-investor"}
            continue
        denom = led_known[k] + joined_known[k]
        comps = {"lead_pace": {"present": True, "value": midrank_pct(led24[k], pace_pool), "raw": {"led_24m": led24[k]}},
                 "lead_share": ({"present": True, "value": led_known[k] / denom,
                                 "raw": {"led": led_known[k], "of": denom}} if denom >= 5 else
                                {"present": False, "value": NEUTRAL, "raw": {"led": led_known[k], "of": denom},
                                 "missing_reason": "fewer than 5 lead-known rounds"}),
                 "stage_fit": {"present": True, "value": midrank_pct(led_stage[k], stage_pool),
                               "raw": {"stage": stage, "led_48m": led_stage[k]}}}
        total = sum(w * comps[key]["value"] for key, _, w in FUND_COMPONENTS)
        out[k] = {"key": k, "name": nm, "queried": True, "score": round(100 * total), "raw_score": total,
                  "score_label": FUND_LABEL,
                  "components": [{"key": key, "label": lab, "weight": w, **comps[key]} for key, lab, w in FUND_COMPONENTS],
                  "led_24m": led24[k], "led_prior_24m": ledprior[k],
                  "months_since_last_lead": round((as_of_t - last_lead[k]) * 12) if k in last_lead else None}
    return out


# ---------------------------------------------------------------- founders
def founder_evidence(founder: dict, cohort_rows: Optional[list[dict]] = None) -> dict:
    """Founder facts k of 4. A number appears only when k >= 2; it counts documented facts, it is not a quality score.

    founder: load.load_founders() shape (roles[].since, founded[].org/org_id, prior_exits, ckeys, name).
    cohort_rows: cohorts.json rows for the founder's companies (their 'founder' text is matched by name)."""
    own = {DUP_SUFFIX.sub("", c) or c for c in founder.get("ckeys") or []}

    def is_own(org: str) -> bool:  # 'IPRally' is the same company as ckey 'iprallytechnologies'
        k = company_key(org)
        return not k or (DUP_SUFFIX.sub("", k) or k) in own

    facts = []
    if any(r.get("since") for r in founder.get("roles") or []):
        facts.append("dated role")
    if any(f.get("org_id") and not is_own(f.get("org") or "") for f in founder.get("founded") or []):
        facts.append("earlier Cala company")
    if founder.get("prior_exits"):
        facts.append("prior exit")
    last = (founder.get("name") or "").split()[-1:] or [""]
    if last[0] and any(last[0].lower() in (r.get("founder") or "").lower() for r in cohort_rows or []):
        facts.append("cohort match")
    k = len(facts)
    return {"k": k, "of": 4, "facts": facts, "missing": [f for f in FOUNDER_FACTS if f not in facts],
            "score": round(100 * k / 4) if k >= 2 else None,
            "score_reason": None if k >= 2 else f"Not enough data ({k} of 4)",
            "score_label": "Share of four track-record facts Cala documents, not a judgment of the founder."}
