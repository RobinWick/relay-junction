"""Recount Signal data store: everything the API needs, built once per snapshot version and cached.

Inputs (all local, 0 Cala calls at request time)
  the snapshot dict main.py already loaded (main.SNAP_DICT; Aiven on Modal, RELAY_SNAPSHOT_PATH locally)
  app/signal_extra.json   sector tags, discovery text, cohorts, merged founders, exit receipts (signal_extra_build.py)
  app/signal_weights.json default weights (signal_backtest.py)

The store holds weight-independent facts per company, fund and founder plus the prepared score components. Ranking
for one weight set is `Store.run(weights)` (cached per rules hash). Nothing here is imputed: a missing value is None
and every filter that needs it reports the company as "not considered".
"""
from __future__ import annotations

import json
import math
import statistics
import threading
from collections import Counter, OrderedDict, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import signal_score as ss
from engine import CROSSOVERS
from explore_shapes import country as norm_country
from merge import _date_precision, canon

HERE = Path(__file__).parent
EXTRA_PATH = HERE / "signal_extra.json"
BACKTEST_PATH = HERE / "signal_backtest.json"
AS_OF = "2026-11-14"
DOWNTURN = (2022, 2023)
BOOM = (2019, 2021)

ISO = {
    "Sweden": "SE", "Finland": "FI", "Norway": "NO", "Denmark": "DK", "Iceland": "IS", "Estonia": "EE",
    "Latvia": "LV", "Lithuania": "LT", "Germany": "DE", "Austria": "AT", "Switzerland": "CH",
    "United Kingdom": "GB", "Ireland": "IE", "France": "FR", "Netherlands": "NL", "Belgium": "BE",
    "Luxembourg": "LU", "Spain": "ES", "Portugal": "PT", "Italy": "IT", "Greece": "GR", "Cyprus": "CY",
    "Poland": "PL", "Czech Republic": "CZ", "Hungary": "HU", "Romania": "RO", "Bulgaria": "BG", "Croatia": "HR",
    "Serbia": "RS", "Ukraine": "UA", "Slovakia": "SK", "Slovenia": "SI", "United States": "US", "Canada": "CA",
    "Israel": "IL", "India": "IN", "China": "CN", "Nigeria": "NG", "United Arab Emirates": "AE", "Brazil": "BR",
    "Singapore": "SG", "Egypt": "EG", "Saudi Arabia": "SA", "Australia": "AU", "Japan": "JP", "Mexico": "MX",
    "Turkey": "TR", "Colombia": "CO", "Kenya": "KE", "Algeria": "DZ", "Uzbekistan": "UZ", "South Korea": "KR",
    "Argentina": "AR", "Pakistan": "PK", "Russia": "RU", "Ghana": "GH", "Morocco": "MA", "Vietnam": "VN",
    "Marshall Islands": "MH", "Bahamas": "BS", "Malaysia": "MY", "Indonesia": "ID", "Hong Kong": "HK",
    "Tanzania": "TZ", "Zambia": "ZM", "South Africa": "ZA", "Chile": "CL", "Peru": "PE", "Thailand": "TH",
    "Philippines": "PH", "Taiwan": "TW", "New Zealand": "NZ", "Malta": "MT", "Monaco": "MC", "Liechtenstein": "LI",
}
ISO_NAME = {v: k for k, v in ISO.items()}
REGIONS = OrderedDict([
    ("nordics", ("Nordics", {"SE", "FI", "NO", "DK", "IS"})),
    ("dach", ("DACH", {"DE", "AT", "CH", "LI"})),
    ("uk_ie", ("UK and Ireland", {"GB", "IE"})),
    ("france_benelux", ("France and Benelux", {"FR", "NL", "BE", "LU", "MC"})),
    ("south", ("Southern Europe", {"ES", "PT", "IT", "GR", "CY", "MT"})),
    ("cee", ("CEE", {"PL", "CZ", "HU", "RO", "BG", "HR", "RS", "UA", "SK", "SI"})),
    ("baltics", ("Baltics", {"EE", "LV", "LT"})),
    ("us", ("United States", {"US"})),
])
REGION_OF = {c: k for k, (_, cs) in REGIONS.items() for c in cs}
SECTOR_TAGS = ["Fintech", "AI", "SaaS", "Climate", "Energy", "Deeptech", "Biotech", "Cybersecurity", "Gaming",
               "Healthtech", "Ecommerce", "Mobility", "Robotics", "Proptech", "Edtech", "Foodtech"]
# Free-text match: a discovery text that contains one of these words counts as that sector ("text match").
SECTOR_WORDS = {
    "Fintech": ["fintech", "payment", "banking", "neobank", "insurtech", "lending", "regtech", "wealthtech", "credit"],
    "AI": [" ai", "ai ", "ai,", "ai/", "artificial intelligence", "machine learning", "llm", "generative"],
    "SaaS": ["saas", "software as a service", "b2b software"],
    "Climate": ["climate", "carbon", "decarbon", "sustainab", "cleantech", "circular"],
    "Energy": ["energy", "battery", "batteries", "solar", "wind", "hydrogen", "grid"],
    "Deeptech": ["deeptech", "deep tech", "quantum", "semiconductor", "photonic", "space"],
    "Biotech": ["biotech", "therapeut", "drug", "pharma", "life science", "genom"],
    "Cybersecurity": ["cyber", "security"],
    "Gaming": ["gaming", "game", "esport"],
    "Healthtech": ["health", "medtech", "medical", "care", "diagnos"],
    "Ecommerce": ["e-commerce", "ecommerce", "retail", "marketplace", "commerce"],
    "Mobility": ["mobility", "transport", "automotive", "electric vehicle", "logistics"],
    "Robotics": ["robot", "drone", "automation"],
    "Proptech": ["proptech", "real estate", "property", "construction"],
    "Edtech": ["edtech", "education", "learning"],
    "Foodtech": ["foodtech", "food", "agri", "agtech"],
}
ACQUIRED_STARTUP_COHORT = "repeat_founder"  # cohort of founders who came from an acquired startup


def flag(code: Optional[str]) -> Optional[str]:
    if not code or len(code) != 2 or not code.isalpha():
        return None
    return "".join(chr(0x1F1E6 + ord(ch) - 65) for ch in code.upper())


def country_obj(name: Optional[str]) -> dict:
    code = ISO.get(name) if name else None
    if not code:
        return {"code": "XX", "name": name or "Country unknown", "flag": None}
    return {"code": code, "name": name, "flag": flag(code)}


def text_tags(texts: list[str]) -> list[str]:
    low = " " + " ".join(texts).lower() + " "
    return [t for t in SECTOR_TAGS if any(w in low for w in SECTOR_WORDS[t])]


def ym(r: dict) -> str:
    return f"{r['year']}-{(r.get('month') or 1):02d}"


PRECISION = {3: "day", 2: "month", 1: "year", 0: "none"}


def _pct(v: float, pool: list[float]) -> float:
    return ss.midrank_pct(v, pool)


@dataclass
class Store:
    version: str
    retrieved: str
    inp: ss.ScoreInputs
    prep: ss.Prepared
    names: dict[str, str]
    fund_keys: set[str]
    facts: dict[str, dict]                      # ckey -> company facts (all companies in the snapshot)
    funds: dict[str, dict]                      # investor key -> fund facts
    founders: list[dict]
    extra: dict
    backtest: dict
    default_weights: dict[str, float]
    name_index: dict[str, str]                  # lower name and canon key -> investor key
    top50: set[str]
    faded: dict[str, dict]
    serial_angels: set[str]
    _runs: "OrderedDict[str, ss.ScoreRun]" = field(default_factory=OrderedDict)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _coinvest: dict = field(default_factory=dict)

    # ---------------- ranking per weight set
    def run(self, weights: dict[str, float]) -> ss.ScoreRun:
        h = ss.rules_hash(weights)
        with self._lock:
            hit = self._runs.get(h)
            if hit is not None:
                self._runs.move_to_end(h)
                return hit
        r = ss.rank(self.prep, weights)
        with self._lock:
            self._runs[h] = r
            while len(self._runs) > 24:
                self._runs.popitem(last=False)
        return r

    # ---------------- investor name resolution
    def resolve_investor(self, value: str) -> Optional[str]:
        v = str(value).strip()
        if not v:
            return None
        low = v.lower()
        if low in self.names:
            return low
        return self.name_index.get(low) or self.name_index.get(canon(v))

    def coinvestors_of(self, fund: str) -> set[str]:
        """Investors that sat in a round of 5M EUR or less with `fund` in the last 4 years (warm path helper)."""
        if fund in self._coinvest:
            return self._coinvest[fund]
        out: set[str] = set()
        for rs in self.prep.ctx.by_company.values():
            for r in rs:
                if r["t"] < ss.NOW_T - 4 or (r.get("amount_eur_m") or 0) > 5:
                    continue
                inv = ss.investors(r)
                if fund in inv:
                    out.update(k for k in inv if k != fund)
        self._coinvest[fund] = out
        return out


# ---------------------------------------------------------------- build
def load_extra(path: Path = EXTRA_PATH) -> dict:
    if not path.exists():
        return {"sectors": {}, "text_sector": {}, "cohorts": {}, "founders": [], "exits": [], "checked_funds": []}
    return json.loads(path.read_text())


def load_backtest(path: Path = BACKTEST_PATH) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}


def build_store(snap: dict, extra: Optional[dict] = None, backtest: Optional[dict] = None) -> Store:
    extra = extra if extra is not None else load_extra()
    backtest = backtest if backtest is not None else load_backtest()
    exits = [{"fund_key": e["fund_key"], "ckey": e["ckey"], "year": e.get("year")} for e in extra.get("exits", [])]
    inp = ss.ScoreInputs(snap["rounds"], snap["investor_names"], set(snap["fund_keys"]), exits,
                         set(extra.get("checked_funds", [])), extra.get("sectors", {}))
    prep = ss.prepare(inp, ss.NOW_T)
    names = snap["investor_names"]
    name_index: dict[str, str] = {}
    for k, nm in names.items():
        name_index.setdefault(nm.lower(), k)
        name_index.setdefault(canon(nm), k)
        name_index.setdefault(k, k)
    led_count = Counter(k for rs in prep.ctx.by_company.values() for r in rs for k in (r.get("leads") or [])
                        if not ss.is_hub(k))
    top50 = {k for k, _ in led_count.most_common(50)}
    faded = _faded(prep.ctx, set(snap["fund_keys"]))
    angel_cos: dict[str, set[str]] = defaultdict(set)
    for ck, rs in prep.ctx.by_company.items():
        for r in rs:
            for k in ss.investors(r):
                if ss.is_person(names.get(k, k)):
                    angel_cos[k].add(ck)
    serial = {k for k, v in angel_cos.items() if len(v) >= 3}
    st = Store(snap["version"], snap.get("retrieved", AS_OF), inp, prep, names, set(snap["fund_keys"]), {}, {}, [],
               extra, backtest, ss.clamp_weights(base=ss.load_weights()), name_index, top50, faded, serial)
    st.facts = _company_facts(st, snap)
    st.funds = _fund_facts(st)
    st.founders = _founder_facts(st)
    return st


def _lead_share(rounds: list[dict]) -> dict[str, list[int]]:
    out: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in rounds:
        leads = set(r.get("leads") or [])
        if not leads:
            continue
        for k in leads:
            out[k][0] += 1
        for k in set(r.get("participants") or []) - leads:
            out[k][1] += 1
    return out


def _faded(ctx: ss.Context, fund_keys: set[str]) -> dict[str, dict]:
    """Queried funds with 3+ boom (2019 to 2021) lead-known rounds whose 2022 to 2023 lead share fell to 0 or under
    half of the boom share. A flag with its numbers, never worded as 'stopped'."""
    eq = [r for rs in ctx.by_company.values() for r in rs]
    boom = _lead_share([r for r in eq if BOOM[0] <= r["year"] <= BOOM[1]])
    down = _lead_share([r for r in eq if DOWNTURN[0] <= r["year"] <= DOWNTURN[1]])
    out = {}
    for k in fund_keys:
        b = boom.get(k)
        if not b or sum(b) < 3:
            continue
        bs = b[0] / sum(b)
        d = down.get(k, [0, 0])
        ds = d[0] / sum(d) if sum(d) else 0.0
        if bs > 0 and (ds == 0 or ds < bs / 2):
            out[k] = {"boom_share": round(bs, 3), "boom_n": sum(b), "downturn_share": round(ds, 3),
                      "downturn_n": sum(d)}
    return out


def _company_facts(st: Store, snap: dict) -> dict[str, dict]:
    ctx = st.prep.ctx
    all_by: dict[str, list[dict]] = defaultdict(list)
    for r in snap["rounds"]:
        all_by[r["ckey"]].append(r)
    sectors, texts, cohorts = (st.extra.get("sectors", {}), st.extra.get("text_sector", {}),
                               st.extra.get("cohorts", {}))
    founders_by: dict[str, list[str]] = defaultdict(list)
    for f in st.extra.get("founders", []):
        for ck in f.get("ckeys") or []:
            founders_by[ck].append(f["id"])
    acquirers_by_fund: dict[str, set[str]] = defaultdict(set)
    for e in st.extra.get("exits", []):
        for a in e.get("acquirers") or []:
            acquirers_by_fund[e["fund_key"]].add(a)
    exited_cos = {e["ckey"] for e in st.extra.get("exits", [])}

    # raised to date vs stage peers: total known amount, percentile within companies at the same last stage
    totals: dict[str, Optional[float]] = {}
    for ck, rs in ctx.by_company.items():
        amts = [r["amount_eur_m"] for r in rs if r.get("amount_eur_m")]
        totals[ck] = round(sum(amts), 3) if amts else None
    stage_pool: dict[str, list[float]] = defaultdict(list)
    for ck, rs in ctx.by_company.items():
        if rs[-1].get("stage") and totals[ck] is not None:
            stage_pool[rs[-1]["stage"]].append(totals[ck])
    for v in stage_pool.values():
        v.sort()

    # last time each fund led at each stage
    last_led: dict[tuple[str, str], float] = {}
    for rs in ctx.by_company.values():
        for r in rs:
            if r.get("stage"):
                for k in r.get("leads") or []:
                    key = (k, r["stage"])
                    last_led[key] = max(last_led.get(key, 0), r["t"])
    led_total = Counter(k for rs in ctx.by_company.values() for r in rs for k in (r.get("leads") or []))

    out = {}
    for ck in sorted(all_by):
        allr = sorted(all_by[ck], key=lambda r: (r["t"], r["id"]))
        rs = ctx.by_company.get(ck, [])
        comps = st.prep.comps.get(ck, {})
        last = rs[-1] if rs else None
        cname = ctx.country_of.get(ck)
        if cname is None:
            cs = Counter(c for c in (norm_country(r.get("country")) for r in allr) if c)
            cname = cs.most_common(1)[0][0] if cs else None
        cobj = country_obj(cname)
        backers = sorted({k for r in rs for k in ss.investors(r)})
        all_leads = sorted({k for r in rs for k in (r.get("leads") or []) if not ss.is_hub(k)})
        stage = last.get("stage") if last else None
        tags = list(sectors.get(ck, []))
        txt = list(texts.get(ck, []))
        ttags = [t for t in text_tags(txt) if t not in tags]
        sector_source = "cala_tag" if tags else "text_match" if txt else "none"
        coh = cohorts.get(ck, [])
        years = [r["year"] for r in rs]
        f = {
            "ckey": ck, "name": (last or allr[-1])["company"], "country": cobj,
            "region": REGION_OF.get(cobj["code"]),
            "entity_id": snap.get("entities", {}).get(f"c:{ck}"),
            "history_depth": "full_history" if ck in ctx.full_history else "investor_first",
            "has_equity": bool(rs),
            "last_stage": stage,
            "n_rounds": len(rs),
            "first_year": years[0] if years else None,
            "months_since_last": round((ss.NOW_T - last["t"]) * 12) if last else None,
            "total_known_eur_m": totals.get(ck),
            "raised_vs_stage_pct": (round(100 * _pct(totals[ck], stage_pool[stage]), 1)
                                    if stage and totals.get(ck) is not None and len(stage_pool[stage]) >= ss.MIN_PEERS
                                    else None),
            "backers": backers, "leads_all": all_leads,
            "sector_tags": tags, "sector_text": txt, "sector_text_tags": ttags, "sector_source": sector_source,
            "cohorts": coh, "founder_ids": founders_by.get(ck, []),
            "raised_in_downturn": any(DOWNTURN[0] <= y <= DOWNTURN[1] for y in years),
            "cycle_bridge": any(y < DOWNTURN[0] for y in years) and any(DOWNTURN[0] <= y <= DOWNTURN[1] for y in years),
            "sourced_round": any(r.get("source") or r.get("graph") for r in allr),
            "disputed": any(r.get("disputed") for r in allr),
            "acquired": ck in exited_cos,
            "crossover": any(k in CROSSOVERS for k in backers),
            "top50_lead_in_cap_table": any(k in st.top50 for k in backers) if backers else None,
            "acquirers": sorted({a for k in backers for a in acquirers_by_fund.get(k, set())}),
        }
        if last:
            prec = _date_precision(last)
            f["last_round"] = {"id": last["id"], "date": ym(last), "date_precision": PRECISION[prec],
                               "amount_eur_m": last.get("amount_eur_m"), "stage": stage,
                               "lead_named": bool(last.get("leads")),
                               "leads": [{"key": k, "name": st.names.get(k, k)} for k in last.get("leads") or []]}
            f["syndicate_size"] = len(ss.investors(last)) if ss.names_anyone(last) else None
            same = [r for r in rs if r.get("stage") == stage] if stage else []
            f["months_at_stage"] = round((ss.NOW_T - same[0]["t"]) * 12) if same else None
            staged = [r for r in rs if r.get("stage")]
            if len(staged) >= 2 and staged[-1]["t"] - staged[0]["t"] > 0.25:
                steps = ss.STAGE_IX[staged[-1]["stage"]] - ss.STAGE_IX[staged[0]["stage"]]
                f["stage_velocity"] = round(steps / (staged[-1]["t"] - staged[0]["t"]), 2)
            else:
                f["stage_velocity"] = None
            # outside new lead on the last round
            if not last.get("leads"):
                f["outside_new_lead"] = None
            elif len(rs) < 2:
                f["outside_new_lead"] = "needs_2_rounds"
            else:
                earlier = {k for r in rs[:-1] for k in ss.investors(r)}
                f["outside_new_lead"] = "insider_led" if set(last["leads"]) & earlier else "yes"
            # lead upgrade: the latest named lead has led more rounds than the previous named lead
            lead_rounds = [r for r in rs if r.get("leads")]
            if len(lead_rounds) >= 2 and set(lead_rounds[-1]["leads"]) != set(lead_rounds[-2]["leads"]):
                a = max(led_total[k] for k in lead_rounds[-1]["leads"])
                b = max(led_total[k] for k in lead_rounds[-2]["leads"])
                f["lead_upgrade"] = a > b
            else:
                f["lead_upgrade"] = None
            if last.get("leads") and stage:
                ts = [last_led.get((k, stage)) for k in last["leads"]]
                ts = [x for x in ts if x]
                f["lead_active_at_stage_months"] = round((ss.NOW_T - max(ts)) * 12) if ts else None
            else:
                f["lead_active_at_stage_months"] = None
            lead_keys = [k for k in last.get("leads") or [] if k in st.faded]
            f["backer_faded"] = {"fund": st.names.get(lead_keys[0], lead_keys[0]), **st.faded[lead_keys[0]]} \
                if lead_keys else (False if last.get("leads") else None)
        else:
            f.update(last_round=None, syndicate_size=None, months_at_stage=None, stage_velocity=None,
                     outside_new_lead=None, lead_upgrade=None, lead_active_at_stage_months=None, backer_faded=None)
        # values read from score components (weight independent)
        def raw(k):
            c = comps.get(k)
            return c["raw"] if c and c["present"] else None
        su = raw("step_up")
        f["step_up_ratio"] = su["ratio"] if su else None
        ac = raw("acceleration")
        f["accelerating"] = (ac["last_gap_months"] < ac["prev_gap_months"]) if ac else None
        fr = comps.get("freshness")
        if fr and fr["present"]:
            ratio = fr["raw"]["months_since"] / max(fr["raw"]["stage_median_gap"], 1)
            f["round_due"] = "on_clock" if ratio <= 1 else "due" if ratio <= 2 else "quiet"
        else:
            f["round_due"] = None
        ins = comps.get("insider_follow_on")
        f["insider_came_back"] = (("yes" if ins["raw"]["came_back"] else "no") if ins and ins["present"]
                                  else "needs_2_rounds" if len(rs) < 2 else None)
        bg = raw("backer_graduation")
        f["backer_graduation"] = {"rate": round(bg["x"], 3), "backer": bg["backer"], "k": bg["k"], "n": bg["n"]} \
            if bg else None
        be = comps.get("backer_exits")
        f["backer_exit"] = ("not_checked" if not be or not be["present"]
                            else "yes" if be["raw"]["exits"] else "no_exit_found")
        ls = raw("lead_supply")
        f["lead_desert"] = ls["lead_desert"] if ls else None
        cb = raw("cross_border")
        f["foreign_backer"] = bool(cb["foreign"]) if cb else None
        an = raw("named_angels")
        f["named_angels"] = an["angels"] if an else []
        f["serial_angel"] = any(k in st.serial_angels for k in backers)
        sh = raw("sector_heat")
        f["sector_heat"] = sh["heat"] if sh else None
        out[ck] = f
    return out


def _fund_facts(st: Store) -> dict[str, dict]:
    ctx = st.prep.ctx
    scores = ss.fund_scores(st.inp, ss.NOW_T, "seed")
    eq = [r for rs in ctx.by_company.values() for r in rs]
    lead_unknown, rounds_in, led_stage, seed_in, seed_nolead = Counter(), Counter(), defaultdict(Counter), Counter(), Counter()
    boom = _lead_share([r for r in eq if BOOM[0] <= r["year"] <= BOOM[1]])
    down = _lead_share([r for r in eq if DOWNTURN[0] <= r["year"] <= DOWNTURN[1]])
    co = defaultdict(Counter)
    portfolio: dict[str, set[str]] = defaultdict(set)
    for r in eq:
        inv = set(r.get("leads") or []) | set(r.get("participants") or [])
        for k in inv:
            rounds_in[k] += 1
            portfolio[k].add(r["ckey"])
            if not r.get("leads"):
                lead_unknown[k] += 1
            if r.get("stage") == "seed":
                seed_in[k] += 1
                if not r.get("leads"):
                    seed_nolead[k] += 1
            if k in st.fund_keys:
                w = 1.0 + max(0.0, 1 - (ss.NOW_T - r["t"]) / 6)  # frequency x recency
                for o in inv - {k}:
                    if not ss.is_hub(o):
                        co[k][o] += w
        for k in r.get("leads") or []:
            if r.get("stage"):
                led_stage[k][r["stage"]] += 1
    exits_by: dict[str, list[dict]] = defaultdict(list)
    for e in st.extra.get("exits", []):
        exits_by[e["fund_key"]].append(e)
    checked = set(st.extra.get("checked_funds", []))
    out = {}
    for k, s in scores.items():
        nm = st.names.get(k, k)
        cname = ctx.fund_country.get(k)
        led = sum(led_stage[k].values())
        ls = next((c for c in s.get("components", []) if c["key"] == "lead_share"), None)
        n = rounds_in[k]
        known_share = 1 - lead_unknown[k] / n if n else 0.0
        ev = 0.5 * known_share + 0.5 * min(1.0, n / 20)
        exits = exits_by.get(k, [])
        out[k] = {
            **s, "id": f"f:{k}", "country": country_obj(cname),
            "rounds_on_file": n, "companies": len(portfolio[k]),
            "lead_share": ({"led": ls["raw"]["led"], "of": ls["raw"]["of"], "lead_unknown": lead_unknown[k]}
                           if ls else None),
            "led_by_stage": dict(led_stage[k]), "led_total": led,
            "main_stage": led_stage[k].most_common(1)[0][0] if led_stage[k] else None,
            "exit_receipts": ({"state": "checked", "count": len({e["ckey"] for e in exits})} if k in checked
                              else {"state": "not_checked", "count": None}),
            "evidence": {"value": round(ev, 3), "band": "solid" if ev >= 0.65 else "some" if ev >= 0.4 else "thin",
                         "parts": {"lead_known_share": round(known_share, 3), "rounds_on_file": n},
                         "how": "0.5 x share of its rounds with a named lead + 0.5 x min(1, rounds on file / 20)"},
            "graduation": ({"k": ctx.grad[k][1], "n": ctx.grad[k][0]} if k in ctx.grad else None),
            "boom_lead_share": _share(boom.get(k)), "downturn_lead_share": _share(down.get(k)),
            "seed_no_lead_share": ({"k": seed_nolead[k], "n": seed_in[k]} if seed_in[k] else None),
            "top_coinvestors": [{"key": o, "name": st.names.get(o, o), "weight": round(w, 2)}
                                for o, w in co[k].most_common(5)],
            "portfolio_ckeys": sorted(portfolio[k]),
            "exits": exits,
            "faded": st.faded.get(k),
        }
        out[k]["name"] = nm
    return out


def _share(x) -> Optional[dict]:
    if not x or not sum(x):
        return None
    return {"led": x[0], "of": sum(x), "share": round(x[0] / sum(x), 3)}


def _founder_facts(st: Store) -> list[dict]:
    out = []
    for f in st.extra.get("founders", []):
        ckeys = [c for c in f.get("ckeys") or [] if c in st.facts]
        rows = [r for c in ckeys for r in st.facts[c]["cohorts"]]
        ev = ss.founder_evidence({**f, "ckeys": ckeys}, rows)
        last = (f["name"].split() or [""])[-1].lower()
        tags = []
        for r in rows:
            if last and last in (r.get("founder") or "").lower():
                t = {"tag": r["employer"], "verified": r.get("evidence") == "worked_at"}
                if t not in tags:
                    tags.append(t)
        comp = ckeys[0] if ckeys else None
        title = next((r.get("role") for r in f.get("roles") or []
                      if comp and r.get("org") and canon(r["org"]) and st.facts[comp]["name"].lower() in r["org"].lower()),
                     None) or next((r.get("role") for r in f.get("roles") or [] if r.get("role")), None)
        flags = (["twin_link"] if f.get("twin_link") else []) + (["merged_duplicate"] if f.get("merged_duplicate") else [])
        out.append({"id": f"p:{f['id']}", "pid": f["id"], "name": f["name"], "title": title, "ckeys": ckeys,
                    "company_ckey": comp,
                    "country": st.facts[comp]["country"] if comp else country_obj(None),
                    "founder_evidence": {k: ev[k] for k in ("k", "of", "facts", "missing")},
                    "score": ev["score"], "score_reason": ev["score_reason"], "score_label": ev["score_label"],
                    "flags": flags, "cohort_tags": tags, "roles": f.get("roles") or [],
                    "founded": f.get("founded") or [], "prior_exits": f.get("prior_exits") or [],
                    "description": f.get("description"), "files": f.get("files") or [],
                    "link_basis": f.get("link_basis") or []})
    return out


# ---------------------------------------------------------------- cache by snapshot version
_STORE: Optional[Store] = None
_store_lock = threading.Lock()
_provider: Optional[Callable[[], dict]] = None


def set_snapshot_provider(fn: Optional[Callable[[], dict]]) -> None:
    """Tests swap the snapshot source; production reads main.SNAP_DICT."""
    global _provider, _STORE
    _provider = fn
    _STORE = None


def _snapshot_dict() -> dict:
    if _provider is not None:
        return _provider()
    import main  # lazy: main includes the signal router
    main.snap()
    return main.SNAP_DICT


def store() -> Store:
    """The current store; rebuilt when the snapshot version changes (a live Cala merge)."""
    global _STORE
    snap = _snapshot_dict()
    cur = _STORE
    if cur is not None and cur.version == snap["version"]:
        return cur
    with _store_lock:
        if _STORE is None or _STORE.version != snap["version"]:
            _STORE = build_store(snap)
        return _STORE
