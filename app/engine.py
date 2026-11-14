"""Lead Check engine: deterministic counting over the merged Cala snapshot. No model is used here.

Verdict rules (shown verbatim on the Method page):
  Public body or programme : fund is on the hand list.
  Too few rounds           : fewer than 3 rounds with a known lead at your stage or the one next to it (last 48 months).
  Leads at your stage      : led 2+ rounds at your stage and led / known >= 30%.
  Mostly follows           : 5+ known rounds and led / known < 15%.
  No lead since {date}     : it has led before, but not in the last 24 months.
  Mixed                    : everything else.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from difflib import get_close_matches

from merge import canon, company_key

STAGES = ["pre-seed", "seed", "series a", "series b", "series c", "series d", "series e", "series f", "growth"]
STAGE_LABEL = {"pre-seed": "Pre-seed", "seed": "Seed", "series a": "Series A", "series b": "Series B",
               "series c": "Series C", "series d": "Series D", "series e": "Series E", "series f": "Series F",
               "growth": "Growth"}
HUBS = {
    "european innovation council", "eic fund", "eic", "european investment bank", "eib", "european investment fund",
    "eif", "business finland", "tekes", "htgf", "high tech grunderfonds", "aws grunderfonds", "cdti", "eifo",
    "innosuisse", "vinnova", "bpifrance", "austria wirtschaftsservice", "aws", "ffg", "venture kick",
    "y combinator", "plug and play", "techstars", "innovate uk", "british business bank", "kfw", "almi invest",
    "almi", "innovation norway", "eit innoenergy", "eit", "european union", "horizon 2020",
}
CROSSOVERS = {"blackrock", "j p morgan", "jp morgan", "salesforce", "tiger global", "insight", "softbank vision fund",
              "temasek", "gic", "tencent", "fidelity", "t rowe price", "coatue", "dst global"}
WINDOW_YEARS = 4.0


def norm(s: str) -> str:
    """Same canonical key the merge step uses, so typed names and stored keys always agree."""
    return canon(s)


@dataclass
class Snapshot:
    rounds: list[dict]
    names: dict[str, str]
    fund_keys: set[str]
    stats: dict
    retrieved: str
    version: str
    entities: dict[str, str] = field(default_factory=dict)
    by_investor: dict[str, list[int]] = field(default_factory=dict)
    by_company: dict[str, list[int]] = field(default_factory=dict)
    _compact: dict | None = None
    now_t: float = 2026.87  # 14 Nov 2026

    @classmethod
    def from_dict(cls, d: dict) -> "Snapshot":
        s = cls(rounds=d["rounds"], names=d["investor_names"], fund_keys=set(d.get("fund_keys", [])),
                stats=d["stats"], retrieved=d["retrieved"], version=d["version"],
                entities=d.get("entities", {}))
        by_inv: dict[str, list[int]] = defaultdict(list)
        by_co: dict[str, list[int]] = defaultdict(list)
        for r in s.rounds:
            for k in set(r["leads"]) | set(r["participants"]):
                by_inv[k].append(r["id"])
            by_co[r["ckey"]].append(r["id"])
        s.by_investor, s.by_company = dict(by_inv), dict(by_co)
        return s

    # ---------- name matching ----------
    def match_fund(self, text: str) -> str | None:
        key = norm(text)
        if not key:
            return None
        if key in self.by_investor:
            return key
        if self._compact is None:
            self._compact = {k.replace(" ", ""): k for k in self.by_investor}
        if key.replace(" ", "") in self._compact:
            return self._compact[key.replace(" ", "")]
        if len(key) < 5:
            return None
        # typo tolerance ('Kreandum'), but only towards funds with real history and similar length
        pool = [k for k in self.by_investor if abs(len(k) - len(key)) <= 3 and len(self.by_investor[k]) >= 3]
        close = get_close_matches(key, pool, n=1, cutoff=0.84)
        return close[0] if close else None

    def suggest(self, q: str, limit: int = 8) -> list[dict]:
        key = norm(q)
        if len(key) < 2:
            return []
        hits = [k for k in self.by_investor if k.startswith(key)] + \
               [k for k in self.by_investor if key in k and not k.startswith(key)]
        hits.sort(key=lambda k: -len(self.by_investor[k]))
        return [{"key": k, "name": self.names.get(k, k), "rounds": len(self.by_investor[k])} for k in hits[:limit]]

    def name(self, key: str) -> str:
        return self.names.get(key, key.title())

    def is_hub(self, key: str) -> bool:
        return key in HUBS or any(key == h or key.startswith(h + " ") for h in HUBS)

    def is_crossover(self, key: str) -> bool:
        return any(key == c or key.startswith(c) for c in CROSSOVERS)


def stage_band(stage: str) -> set[str]:
    if stage not in STAGES:
        return set()
    i = STAGES.index(stage)
    return {STAGES[j] for j in (i - 1, i, i + 1) if 0 <= j < len(STAGES)}


def month_label(r: dict) -> str:
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return f"{months[r['month'] - 1]} {r['year']}"


def round_brief(snap: Snapshot, r: dict) -> dict:
    return {"id": r["id"], "company": r["company"], "date": month_label(r), "t": r["t"],
            "stage": STAGE_LABEL.get(r["stage"] or "", "Stage not stated"),
            "amount_eur_m": r["amount_eur_m"], "amount_raw": r.get("amount_raw"),
            "n_investors": len(r["leads"]) + len(r["participants"]),
            "leads": [snap.name(k) for k in r["leads"]], "path": r.get("query_path"), "sourced": bool(r.get("source"))}


def fund_profile(snap: Snapshot, key: str, stage: str, target_m: float | None) -> dict:
    """Everything one table row needs, with denominators and the rounds behind each number."""
    ids = snap.by_investor.get(key, [])
    since = snap.now_t - WINDOW_YEARS
    band = stage_band(stage)
    led, joined_known, unknown, led_at_stage = [], [], [], []
    all_led = []
    first_t: dict[str, float] = {}
    for rid in ids:  # when did this fund first appear in each company?
        r = snap.rounds[rid]
        first_t[r["ckey"]] = min(first_t.get(r["ckey"], r["t"]), r["t"])
    follow_ons = []
    for rid in ids:
        r = snap.rounds[rid]
        is_lead = key in r["leads"]
        if is_lead:
            all_led.append(r)
        if r["t"] < since or (band and r["stage"] not in band):
            continue
        if r["t"] > first_t[r["ckey"]] + 0.17 and not is_lead:
            follow_ons.append(r)  # joining its own company's next round says nothing about leading new deals
            continue
        if not r["leads"]:
            unknown.append(r)
            continue
        joined_known.append(r)
        if is_lead:
            led.append(r)
            if r["stage"] == stage:
                led_at_stage.append(r)
    known = len(joined_known)
    ratio = len(led) / known if known else None
    last_lead = max(all_led, key=lambda r: r["t"]) if all_led else None
    exact = sorted(x["amount_eur_m"] for x in led_at_stage if x.get("amount_eur_m"))
    band_sizes = sorted(x["amount_eur_m"] for x in led if x.get("amount_eur_m"))
    sizes, size_basis = (exact, "exact") if len(exact) >= 2 else (band_sizes, "band")

    size = None
    if sizes:
        lo = sizes[len(sizes) // 4]
        hi = sizes[(3 * len(sizes)) // 4] if len(sizes) > 1 else sizes[0]
        fit = None
        if target_m:
            fit = "fits" if lo * 0.8 <= target_m <= hi * 1.25 else ("larger" if target_m > hi * 1.25 else "smaller")
        size = {"lo": lo, "hi": hi, "n": len(sizes), "fit": fit, "basis": size_basis}

    if snap.is_hub(key):
        verdict = ("public", "Public body or programme")
    elif known < 3:
        verdict = ("few", "Too few rounds")
    elif len(led_at_stage) >= 2 and ratio >= 0.30:
        if size and size["fit"] == "fits":
            verdict = ("leads", "Leads rounds like yours")
        elif size and size["fit"] == "larger":
            verdict = ("leads_size", "Leads, but smaller rounds")
        elif size and size["fit"] == "smaller":
            verdict = ("leads_size", "Leads, but larger rounds")
        else:
            verdict = ("leads", "Leads at your stage")
    elif known >= 5 and ratio < 0.15:
        verdict = ("follows", "Mostly follows")
    elif last_lead and snap.now_t - last_lead["t"] > 2.0:
        verdict = ("stale", f"No lead since {month_label(last_lead)}")
    else:
        verdict = ("mixed", "Mixed")

    return {
        "key": key, "name": snap.name(key), "verdict": verdict[0], "verdict_label": verdict[1],
        "led": len(led), "known": known, "unknown": len(unknown), "led_at_stage": len(led_at_stage),
        "follow_ons": len(follow_ons),
        "size": size, "last_lead": round_brief(snap, last_lead) if last_lead and not snap.is_hub(key) else None,
        "queried": key in snap.fund_keys, "total_rounds": len(ids),
        "rounds_led": [round_brief(snap, r) for r in sorted(led, key=lambda r: -r["t"])],
        "rounds_joined": [round_brief(snap, r) for r in sorted(joined_known, key=lambda r: -r["t"]) if key not in r["leads"]],
        "rounds_unknown": [round_brief(snap, r) for r in sorted(unknown, key=lambda r: -r["t"])],
    }


def conflicts(snap: Snapshot, key: str, competitors: list[str]) -> list[dict]:
    out = []
    for comp in competitors:
        ckey = company_key(comp)
        for rid in snap.by_company.get(ckey, []):
            r = snap.rounds[rid]
            if key in r["leads"]:
                out.append({"level": "led", "competitor": r["company"], "round": round_brief(snap, r)})
            elif key in r["participants"]:
                out.append({"level": "joined", "competitor": r["company"], "round": round_brief(snap, r)})
    out.sort(key=lambda c: (c["level"] != "led", -c["round"]["t"]))
    return out


def competitor_coverage(snap: Snapshot, competitors: list[str]) -> dict:
    found = {}
    for comp in competitors:
        ckey = company_key(comp)
        found[comp] = len(snap.by_company.get(ckey, []))
    return found


def tie(snap: Snapshot, key: str, my_investors: list[str], my_company: str | None) -> dict | None:
    """Strongest small-round tie: a founder's investor and this fund in the same equity round (max 6 investors)."""
    my_ckey = company_key(my_company or "")
    best = None
    for inv in my_investors:
        if inv == key or snap.is_hub(inv) or snap.is_hub(key):
            continue
        shared = set(snap.by_investor.get(inv, [])) & set(snap.by_investor.get(key, []))
        for rid in shared:
            r = snap.rounds[rid]
            n = len(r["leads"]) + len(r["participants"])
            if r["ckey"] == my_ckey or n > 6 or n < 2 or snap.now_t - r["t"] > WINDOW_YEARS:
                continue
            if r.get("amount_eur_m") and r["amount_eur_m"] > 50:  # a large round is not a small cap table
                continue
            weight = 1 / (n - 1)
            if best is None or (weight, r["t"]) > (best["weight"], best["round"]["t"]):
                best = {"investor": snap.name(inv), "weight": weight, "round": round_brief(snap, r)}
    return best


def lead_comes_back(snap: Snapshot, lead_key: str) -> dict | None:
    """For a founder's current lead: in its other companies, did it come back in (and lead) the next round?

    Only companies Cala gave us a full round history for (company-first) count: investor-first answers only show
    rounds the fund was in, which would make every fund look loyal. A later round within 6 months at the same
    stage is a tranche, not a next round.
    """
    came, led_again, cases = 0, 0, []
    for rid in snap.by_investor.get(lead_key, []):
        r = snap.rounds[rid]
        if lead_key not in r["leads"]:
            continue
        rs = [snap.rounds[i] for i in snap.by_company[r["ckey"]]]
        if not any(s["path"] == "company_first" for x in rs for s in x["sources"]):
            continue
        later = sorted((x for x in rs if x["t"] > r["t"] + 0.17
                        and not (x["t"] - r["t"] < 0.5 and (x["stage"] == r["stage"] or not x["stage"]))),
                       key=lambda x: x["t"])
        if not later:
            continue
        nxt = later[0]
        inside = lead_key in nxt["leads"] or lead_key in nxt["participants"]
        came += inside
        led_again += lead_key in nxt["leads"]
        cases.append({"from": round_brief(snap, r), "next": round_brief(snap, nxt), "came_back": inside,
                      "led": lead_key in nxt["leads"]})
    if len(cases) < 3:
        return None
    return {"lead": snap.name(lead_key), "cases": len(cases), "came_back": came, "led_again": led_again,
            "examples": sorted(cases, key=lambda c: -c["next"]["t"])[:6]}


def timing(snap: Snapshot, stage: str) -> dict | None:
    """Months from the previous stage to this one across companies in the data (peer range, not a prediction)."""
    if stage not in STAGES or STAGES.index(stage) == 0:
        return None
    prev = STAGES[STAGES.index(stage) - 1]
    gaps = []
    for ids in snap.by_company.values():
        rs = sorted((snap.rounds[i] for i in ids), key=lambda r: r["t"])
        a = next((r for r in rs if r["stage"] == prev), None)
        b = next((r for r in rs if r["stage"] == stage), None)
        if a and b and b["t"] > a["t"]:
            gaps.append(round((b["t"] - a["t"]) * 12))
    if len(gaps) < 10:
        return None
    gaps.sort()
    return {"from": STAGE_LABEL[prev], "to": STAGE_LABEL[stage], "median": gaps[len(gaps) // 2],
            "p25": gaps[len(gaps) // 4], "p75": gaps[(3 * len(gaps)) // 4], "n": len(gaps)}


REGIONS = {
    "nordics": {"sweden", "finland", "norway", "denmark", "iceland"},
    "baltics": {"estonia", "latvia", "lithuania"},
    "dach": {"germany", "austria", "switzerland"},
    "uk-ie": {"united kingdom", "uk", "ireland", "england", "scotland"},
    "france-benelux": {"france", "netherlands", "belgium", "luxembourg"},
    "south": {"spain", "portugal", "italy"},
    "cee": {"poland", "czech republic", "czechia", "hungary", "romania", "estonia", "lithuania", "latvia"},
}


def _country_ok(country, region: str | None) -> bool:
    if not region or region not in REGIONS:
        return True
    c = str(country or "").lower()
    return any(name in c for name in REGIONS[region])


def discover(snap: Snapshot, stage: str, target_m: float | None, region: str | None, limit: int = 15) -> dict:
    """Funds that led rounds like the founder's (same stage, similar size, same region, last 30 months)."""
    since = snap.now_t - 2.5
    lo, hi = (target_m / 2, target_m * 2) if target_m else (None, None)
    matches = []
    for r in snap.rounds:
        if r["stage"] != stage or r["t"] < since or not r["leads"] or not _country_ok(r.get("country"), region):
            continue
        if lo is not None and (not r.get("amount_eur_m") or not lo <= r["amount_eur_m"] <= hi):
            continue
        matches.append(r)
    counts: dict[str, list[dict]] = defaultdict(list)
    for r in matches:
        for k in r["leads"]:
            if not snap.is_hub(k) and not snap.is_crossover(k):
                counts[k].append(r)
    # a fund needs some history to be recommended: 2+ matching led rounds, or 1 plus 5+ rounds overall
    eligible = {k: rs for k, rs in counts.items() if len(rs) >= 2 or len(snap.by_investor.get(k, [])) >= 5}
    ranked = sorted(eligible.items(), key=lambda kv: (-len(kv[1]), -max(x["t"] for x in kv[1])))[:limit]
    funds = []
    for k, rs in ranked:
        prof = fund_profile(snap, k, stage, target_m)
        prof["like_you"] = [round_brief(snap, x) for x in sorted(rs, key=lambda x: -x["t"])]
        funds.append(prof)
    return {"rounds_matched": len(matches), "funds": funds,
            "filters": {"stage": STAGE_LABEL.get(stage, stage), "size": [lo, hi] if lo else None, "region": region}}


def record(snap: Snapshot, rid: int) -> dict | None:
    if not 0 <= rid < len(snap.rounds):
        return None
    r = snap.rounds[rid]
    return {**round_brief(snap, r), "type": r.get("type"), "country": r.get("country"),
            "participants": [snap.name(k) for k in r["participants"]],
            "sources": [{"path": s["path"], "query": s["query"], "row": s["row"]} for s in r["sources"]],
            "source": r.get("source"), "graph": r.get("graph"),
            "entity_ids": {"company": snap.entities.get("c:" + r["ckey"]),
                           "leads": [{"name": snap.name(k), "id": snap.entities.get("i:" + k)} for k in r["leads"]]}}
