"""Recount Signal filter catalogue: one source for /meta, the Gemini prompt, chat validation and filter evaluation.

A filter is {"key", "op", "value"}. Evaluation per entity returns True (match), False (no match) or None (no data for
this entity: "not considered", counted and reported, never silently treated as a match or a miss).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import signal_score as ss
from signal_data import ISO, ISO_NAME, REGIONS, SECTOR_TAGS, SECTOR_WORDS, Store, text_tags

OPS = ["eq", "in", "not_in", "gte", "lte", "between", "is_true", "is_false", "contains"]
LOW_COVERAGE = 25.0
BANDS = ["strong", "promising", "watch", "low", "not_enough_data"]
STAGES = ss.STAGE_ORDER
STAGE_ALIASES = {"preseed": "pre-seed", "pre seed": "pre-seed", "a": "series a", "b": "series b", "c": "series c",
                 "series-a": "series a", "series-b": "series b", "series-c": "series c", "seriesa": "series a",
                 "seriesb": "series b", "seriesc": "series c", "late": "growth"}


class FilterError(ValueError):
    pass


@dataclass
class Spec:
    key: str
    label: str
    group: str
    type: str                     # text | multi_select | seg | toggle | range | select | slider | component_min
    entity: tuple
    source: str
    get: Callable                 # (store, facts, row) -> value or None (no data)
    kind: str                     # set | str | num | bool | text | component
    values: Optional[Callable] = None  # (store) -> allowed values (enumerated filters)
    default: Optional[dict] = None     # default filter applied unless the request sets this key
    note: Optional[str] = None
    norm: Optional[Callable] = None    # (store, value) -> canonical value or None (unknown)
    ops: tuple = field(default=())


def _stage_norm(_st, v):
    s = str(v).strip().lower()
    s = STAGE_ALIASES.get(s, s)
    return s if s in STAGES else None


def _country_norm(_st, v):
    s = str(v).strip()
    if s.upper() in ISO_NAME:
        return s.upper()
    for name, code in ISO.items():
        if name.lower() == s.lower():
            return code
    if s.lower() in ("xx", "unknown", "country unknown"):
        return "XX"
    return {"uk": "GB", "usa": "US", "england": "GB", "britain": "GB", "great britain": "GB"}.get(s.lower())


def _region_norm(_st, v):
    s = str(v).strip().lower()
    for k, (label, _) in REGIONS.items():
        if s in (k, label.lower()) or s.rstrip("s") == k.rstrip("s"):
            return k
    return {"nordic": "nordics", "uk": "uk_ie", "uk+ie": "uk_ie", "ireland": "uk_ie", "benelux": "france_benelux",
            "southern europe": "south", "baltic": "baltics", "us": "us", "usa": "us", "united states": "us",
            "eastern europe": "cee", "central and eastern europe": "cee"}.get(s)


def _sector_norm(_st, v):
    s = str(v).strip()
    for t in SECTOR_TAGS:
        if t.lower() == s.lower():
            return t
    alias = {"artificial intelligence": "AI", "machine learning": "AI", "climate tech": "Climate",
             "cleantech": "Climate", "health": "Healthtech", "medtech": "Healthtech", "e-commerce": "Ecommerce",
             "deep tech": "Deeptech", "security": "Cybersecurity", "payments": "Fintech", "insurtech": "Fintech",
             "games": "Gaming", "real estate": "Proptech", "education": "Edtech", "food": "Foodtech",
             "software": "SaaS", "b2b software": "SaaS", "life science": "Biotech", "energy tech": "Energy"}
    return alias.get(s.lower()) or (s.lower() if 2 <= len(s) <= 40 else None)  # free word: text match only


def _fund_norm(st: Store, v):
    return st.resolve_investor(v)


def _employer_norm(st: Store, v):
    emps = _employers(st)
    for e in emps:
        if e.lower() == str(v).strip().lower():
            return e
    return None


def _employers(st: Store) -> list[str]:
    return sorted({r["employer"] for rows in st.extra.get("cohorts", {}).values() for r in rows
                   if r["employer"] != "repeat_founder"})


def _choice(values):
    def n(_st, v):
        s = str(v).strip().lower()
        return s if s in values else None
    return n


def _comp_value(row, key):
    for p in row["components"]:
        if p["key"] == key:
            return p["value"] if p["present"] else None
    return None


def _sector_get(st, f, row):
    if f["sector_source"] == "none":
        return None
    return {"tags": f["sector_tags"], "text_tags": f["sector_text_tags"], "text": " ".join(f["sector_text"]).lower()}


def _bool(v):
    return None if v is None else bool(v)


def _step_bands(f):
    r = f["step_up_ratio"]
    if r is None:
        return None
    out = ["down"] if r < 0.9 else ["flat"] if r < 2 else ["2x+"]
    if r >= 5:
        out.append("5x+")
    return out


C, F, P = ("company",), ("fund",), ("founder",)
COMPANY_SPECS = [
    # A. Basics
    Spec("q", "Name search", "Basics", "text", ("company", "fund", "founder"), "Cala round data",
         lambda st, f, r: f["name"], "text"),
    Spec("country", "Country", "Basics", "multi_select", C, "Cala round data (normalised)",
         lambda st, f, r: f["country"]["code"] if f["country"]["code"] != "XX" else None, "str",
         values=lambda st: sorted({f["country"]["code"] for f in st.facts.values()}), norm=_country_norm),
    Spec("region", "Region", "Basics", "multi_select", C, "derived from country",
         lambda st, f, r: f["region"], "str", values=lambda st: list(REGIONS), norm=_region_norm),
    Spec("history_depth", "History depth", "Basics", "seg", C, "Cala query path",
         lambda st, f, r: f["history_depth"], "str", values=lambda st: ["full_history", "investor_first"],
         norm=_choice({"full_history", "investor_first"})),
    Spec("hide_duplicates", "Hide possible duplicates", "Basics", "toggle", C, "derived (name suffix twins)",
         lambda st, f, r: "possible_duplicate" not in r["flags"], "bool", default={"op": "is_true"}),
    Spec("exclude_acquired", "Exclude already acquired", "Basics", "toggle", C, "exit receipts",
         lambda st, f, r: not f["acquired"], "bool", default={"op": "is_true"}),
    # B. Funding
    Spec("last_stage", "Last stage", "Funding", "multi_select", C, "Cala round data",
         lambda st, f, r: f["last_stage"], "str", values=lambda st: STAGES, norm=_stage_norm),
    Spec("months_at_stage", "Months at current stage", "Funding", "range", C, "derived",
         lambda st, f, r: f["months_at_stage"], "num"),
    Spec("raised_within_months", "Raised in the last N months", "Funding", "select", C, "Cala round data",
         lambda st, f, r: f["months_since_last"], "num", note="value N means months since last round at most N"),
    Spec("last_round_date", "Last round date (YYYY or YYYY-MM)", "Funding", "range", C, "Cala round data",
         lambda st, f, r: f["last_round"]["date"] if f["last_round"] else None, "date"),
    Spec("last_amount_eur_m", "Last round size (EUR m)", "Funding", "range", C, "Cala round data",
         lambda st, f, r: f["last_round"]["amount_eur_m"] if f["last_round"] else None, "num"),
    Spec("total_known_eur_m", "Raised to date (EUR m, lower bound)", "Funding", "range", C, "derived",
         lambda st, f, r: f["total_known_eur_m"], "num"),
    Spec("size_for_stage_pct", "Size for stage percentile", "Funding", "slider", C, "score component",
         lambda st, f, r: None if _comp_value(r, "size_for_stage") is None else 100 * _comp_value(r, "size_for_stage"),
         "num"),
    Spec("raised_vs_stage_pct", "Raised to date vs stage peers (percentile)", "Funding", "slider", C, "derived",
         lambda st, f, r: f["raised_vs_stage_pct"], "num"),
    Spec("n_rounds", "Rounds on file", "Funding", "range", C, "Cala round data",
         lambda st, f, r: f["n_rounds"], "num"),
    Spec("step_up_band", "Step-up on last raise", "Funding", "seg", C, "derived",
         lambda st, f, r: _step_bands(f), "set", values=lambda st: ["down", "flat", "2x+", "5x+"],
         norm=_choice({"down", "flat", "2x+", "5x+"})),
    Spec("accelerating", "Accelerating (last gap shorter than the one before)", "Funding", "toggle", C, "derived",
         lambda st, f, r: f["accelerating"], "bool"),
    Spec("stage_velocity", "Stages climbed per year", "Funding", "range", C, "derived",
         lambda st, f, r: f["stage_velocity"], "num"),
    Spec("round_due", "Stage clock (on clock / due / quiet)", "Funding", "seg", C, "derived",
         lambda st, f, r: f["round_due"], "str", values=lambda st: ["on_clock", "due", "quiet"],
         norm=_choice({"on_clock", "due", "quiet"})),
    Spec("raised_in_downturn", "Raised in the 2022 to 2023 downturn", "Funding", "toggle", C, "Cala round data",
         lambda st, f, r: f["raised_in_downturn"] if f["has_equity"] else None, "bool"),
    Spec("cycle_bridge", "Raised before 2022 and again in 2022 to 2023", "Funding", "toggle", C, "Cala round data",
         lambda st, f, r: f["cycle_bridge"] if f["has_equity"] else None, "bool",
         note="mostly means 2 or more rounds on file"),
    # C. Investors
    Spec("backed_by", "Backed by fund", "Investors", "multi_select", C, "Cala round data",
         lambda st, f, r: f["backers"] or None, "set", norm=_fund_norm),
    Spec("led_by", "Led by fund", "Investors", "multi_select", C, "Cala round data (leads)",
         lambda st, f, r: f["leads_all"] or None, "set", norm=_fund_norm),
    Spec("lead_named", "Last round lead named", "Investors", "seg", C, "Cala round data",
         lambda st, f, r: (("named" if f["last_round"]["lead_named"] else "none")
                           if f["last_round"] and f["syndicate_size"] is not None else None), "str",
         values=lambda st: ["named", "none"], norm=_choice({"named", "none"})),
    Spec("outside_new_lead", "Outside new lead on last round", "Investors", "seg", C, "derived",
         lambda st, f, r: f["outside_new_lead"], "str", values=lambda st: ["yes", "insider_led", "needs_2_rounds"],
         norm=_choice({"yes", "insider_led", "needs_2_rounds"})),
    Spec("insider_came_back", "An earlier investor came back", "Investors", "seg", C, "derived",
         lambda st, f, r: f["insider_came_back"], "str", values=lambda st: ["yes", "no", "needs_2_rounds"],
         norm=_choice({"yes", "no", "needs_2_rounds"})),
    Spec("syndicate_size", "Named syndicate size, last round (lower bound)", "Investors", "range", C,
         "Cala round data", lambda st, f, r: f["syndicate_size"], "num"),
    Spec("backer_graduation_min", "Backer graduation rate at least (0 to 1)", "Investors", "slider", C, "derived",
         lambda st, f, r: f["backer_graduation"]["rate"] if f["backer_graduation"] else None, "num"),
    Spec("backer_exit", "Any backer has an exit receipt", "Investors", "seg", C, "exit receipts",
         lambda st, f, r: None if f["backer_exit"] == "not_checked" else f["backer_exit"], "str",
         values=lambda st: ["yes", "no_exit_found"], norm=_choice({"yes", "no_exit_found"}),
         note="not checked for most backers; no exit found does not mean no exit"),
    Spec("acquirer", "Backer exited to acquirer", "Investors", "multi_select", C, "exit receipts",
         lambda st, f, r: [a.lower() for a in f["acquirers"]] or None, "set",
         values=lambda st: sorted({a for e in st.extra.get("exits", []) for a in e.get("acquirers") or []}),
         norm=lambda st, v: str(v).strip().lower() or None),
    Spec("top50_lead_in_cap_table", "A top 50 lead is in the cap table", "Investors", "toggle", C, "derived",
         lambda st, f, r: f["top50_lead_in_cap_table"], "bool", note="filter only, never scored"),
    Spec("lead_active_at_stage", "Last lead led at this stage within N months", "Investors", "select", C, "derived",
         lambda st, f, r: f["lead_active_at_stage_months"], "num"),
    Spec("lead_upgrade", "Latest lead has led more rounds than the previous lead", "Investors", "toggle", C,
         "derived", lambda st, f, r: f["lead_upgrade"], "bool"),
    Spec("lead_desert", "Few next-stage leads at home (2 or fewer)", "Investors", "toggle", C, "derived",
         lambda st, f, r: f["lead_desert"], "bool"),
    Spec("foreign_backer", "Has a foreign backer", "Investors", "toggle", C, "derived (queried funds only)",
         lambda st, f, r: f["foreign_backer"], "bool"),
    Spec("has_named_angel", "Backed by a named angel / serial angel (3+ companies)", "Investors", "seg", C,
         "derived (name heuristic)",
         lambda st, f, r: (["any"] + (["serial"] if f["serial_angel"] else [])) if f["named_angels"] else None,
         "set", values=lambda st: ["any", "serial"], norm=_choice({"any", "serial", "true", "yes"})),
    Spec("exclude_public_bodies", "Exclude public bodies and programmes from syndicate counts", "Investors",
         "toggle", C, "engine.HUBS", lambda st, f, r: True, "bool", default={"op": "is_true"},
         note="always applied in scoring; the toggle is informational"),
    Spec("crossover_in_round", "Crossover investor in a round", "Investors", "toggle", C, "engine.CROSSOVERS",
         lambda st, f, r: f["crossover"] if f["backers"] else None, "bool"),
    Spec("co_invested_with", "A backer co-invested with fund X (round of 5M EUR or less, last 4 years)",
         "Investors", "select", C, "derived",
         lambda st, f, r: f["backers"] or None, "coinvest", norm=_fund_norm),
    Spec("warm_path_from", "Warm path from my fund (same rule as co-invested, filter only)", "Investors", "select",
         C, "derived", lambda st, f, r: f["backers"] or None, "coinvest", norm=_fund_norm,
         note="access, not quality; an earlier stress test found warm paths do not predict the next lead"),
    Spec("backer_faded", "Last lead faded after 2021", "Investors", "toggle", C, "derived",
         lambda st, f, r: None if f["backer_faded"] is None else bool(f["backer_faded"]), "bool"),
    # D. Sector
    Spec("sector", "Sector (16 Cala tags + text match)", "Sector and market", "multi_select", C,
         "Cala sector tag + discovery text", _sector_get, "sector", values=lambda st: SECTOR_TAGS, norm=_sector_norm),
    Spec("sector_source", "Sector source", "Sector and market", "seg", C, "Cala sector tag + discovery text",
         lambda st, f, r: f["sector_source"], "str", values=lambda st: ["cala_tag", "text_match", "none"],
         norm=_choice({"cala_tag", "text_match", "none"})),
    Spec("sector_heat_min", "Sector momentum at least (x vs prior 24 months)", "Sector and market", "slider", C,
         "derived (tagged set only)", lambda st, f, r: f["sector_heat"], "num"),
    # E. Team
    Spec("founder_alumni", "Founder alumni of employer (verified only)", "Team and founders", "multi_select",
         ("company", "founder"), "Cala employer cohorts",
         lambda st, f, r: [x["employer"] for x in f["cohorts"] if x.get("evidence") == "worked_at"
                           and x["employer"] != "repeat_founder"] or None, "set", values=_employers,
         norm=_employer_norm),
    Spec("acquired_startup_alumni", "Founders came from an acquired startup", "Team and founders", "toggle", C,
         "Cala employer cohorts", lambda st, f, r: True if any(x["employer"] == "repeat_founder" for x in f["cohorts"])
         else None, "bool"),
    Spec("founder_named", "Founder named in Cala", "Team and founders", "toggle", C, "people files",
         lambda st, f, r: True if f["founder_ids"] else None, "bool"),
    # F. Data quality
    Spec("evidence_band", "Evidence at least", "Data quality", "seg", C, "derived",
         lambda st, f, r: r["evidence"]["band"], "evidence", values=lambda st: ["solid", "some", "thin"],
         norm=_choice({"solid", "some", "thin"})),
    Spec("based_on_min", "Score based on at least k components", "Data quality", "slider", C, "derived",
         lambda st, f, r: r["coverage"]["k"], "num"),
    Spec("date_precision", "Last round dated to", "Data quality", "seg", C, "Cala round data",
         lambda st, f, r: f["last_round"]["date_precision"] if f["last_round"] else None, "str",
         values=lambda st: ["day", "month", "year", "none"], norm=_choice({"day", "month", "year", "none"})),
    Spec("sourced_round", "Has a sourced or graph-checked round", "Data quality", "toggle", C, "Cala round flags",
         lambda st, f, r: True if f["sourced_round"] else None, "bool"),
    Spec("exclude_disputed", "Exclude companies with disputed rounds", "Data quality", "toggle", C,
         "Cala round flags", lambda st, f, r: not f["disputed"], "bool", default={"op": "is_true"}),
    # G. Score
    Spec("score_min", "Signal score at least", "Score", "slider", ("company", "fund"), "derived",
         lambda st, f, r: r["score"], "num"),
    Spec("band", "Band", "Score", "multi_select", C, "derived", lambda st, f, r: r["band"], "str",
         values=lambda st: BANDS, norm=_choice(set(BANDS))),
    Spec("component_min", "Component at least x (0 to 1)", "Score", "component_min", C, "derived",
         lambda st, f, r: r, "component"),
]

FUND_SPECS = [
    Spec("q", "Name search", "Basics", "text", F, "Cala", lambda st, f, r: f["name"], "text"),
    Spec("fund_queried_only", "Funds with full round lists only", "Funds", "toggle", F, "Cala query path",
         lambda st, f, r: f["queried"], "bool", default={"op": "is_true"}),
    Spec("fund_led_at_stage", "Led at stage S at least n times (all years)", "Funds", "select", F, "Cala round data",
         lambda st, f, r: f.get("led_by_stage") or {}, "stage_count"),
    Spec("fund_lead_share_min", "Lead share at least (0 to 1)", "Funds", "slider", F, "Cala round data",
         lambda st, f, r: (f["lead_share"]["led"] / f["lead_share"]["of"])
         if f.get("lead_share") and f["lead_share"]["of"] >= 5 else None, "num"),
    Spec("fund_led_in_downturn", "Led rounds in the 2022 to 2023 downturn, at least n", "Funds", "range", F,
         "Cala round data (leads)",
         lambda st, f, r: (f.get("downturn_lead_share") or {}).get("led", 0) if f.get("queried") else None, "num",
         note="counts lead-known equity rounds dated 2022 or 2023; Cala names no lead in about a third of seed rounds"),
    Spec("fund_exit_receipts_min", "Exit receipts at least n (checked funds only)", "Funds", "range", F,
         "exit receipts", lambda st, f, r: f["exit_receipts"]["count"] if f.get("exit_receipts") else None, "num"),
    Spec("fund_country", "Fund main portfolio country", "Funds", "multi_select", F, "derived",
         lambda st, f, r: f["country"]["code"] if f.get("country") and f["country"]["code"] != "XX" else None, "str",
         norm=_country_norm, values=lambda st: sorted({f["country"]["code"] for f in st.funds.values()
                                                       if f.get("country")})),
    Spec("score_min", "Activity score at least", "Score", "slider", F, "derived", lambda st, f, r: f["score"], "num"),
]

FOUNDER_SPECS = [
    Spec("q", "Name search", "Basics", "text", P, "people files", lambda st, f, r: f["name"], "text"),
    Spec("country", "Company country", "Basics", "multi_select", P, "Cala round data",
         lambda st, f, r: f["country"]["code"] if f["country"]["code"] != "XX" else None, "str", norm=_country_norm,
         values=lambda st: sorted({f["country"]["code"] for f in st.founders})),
    Spec("founder_alumni", "Founder alumni of employer (verified, name matched)", "Team and founders",
         "multi_select", P, "Cala employer cohorts",
         lambda st, f, r: [t["tag"] for t in f["cohort_tags"] if t["verified"]] or None, "set", values=_employers,
         norm=_employer_norm),
    Spec("founder_evidence_min", "Founder evidence at least k of 4", "Team and founders", "slider", P,
         "people files", lambda st, f, r: f["founder_evidence"]["k"], "num"),
    Spec("hide_twin_links", "Hide founders linked via a same-name entity", "Team and founders", "toggle", P,
         "people files", lambda st, f, r: "twin_link" not in f["flags"], "bool", default={"op": "is_true"}),
]

SPECS = {"companies": {s.key: s for s in COMPANY_SPECS}, "funds": {s.key: s for s in FUND_SPECS},
         "founders": {s.key: s for s in FOUNDER_SPECS}}
ENTITY_OF_VIEW = {"companies": "company", "funds": "fund", "founders": "founder"}


# ---------------------------------------------------------------- validation
def _num(v) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        try:
            v = float(str(v).strip())
        except (TypeError, ValueError):
            raise FilterError("needs a number")
    if math.isnan(v) or math.isinf(v):
        raise FilterError("needs a finite number")
    return float(v)


def normalise(st: Store, view: str, flt: Any) -> dict:
    """One filter in canonical form; raises FilterError with a plain reason."""
    if not isinstance(flt, dict):
        raise FilterError("a filter must be an object with key, op and value")
    key = flt.get("key")
    spec = SPECS[view].get(key) if isinstance(key, str) else None
    if spec is None:
        raise FilterError(f"unknown key '{key}'")
    op = flt.get("op") or ("in" if spec.kind in ("set", "sector") else "eq")
    if op not in OPS:
        raise FilterError(f"unknown op '{op}' for '{key}'")
    v = flt.get("value")
    out = {"key": key, "op": op}
    if flt.get("reason"):
        out["reason"] = str(flt["reason"])[:200]
    if spec.kind == "bool":
        if op in ("is_true", "is_false"):
            out["value"] = op == "is_true"
        elif op == "eq" and isinstance(v, bool):
            out.update(op="is_true" if v else "is_false", value=v)
        else:
            raise FilterError(f"'{key}' takes is_true or is_false")
        return out
    if spec.kind == "text":
        if op not in ("contains", "eq") or not isinstance(v, str) or not v.strip():
            raise FilterError(f"'{key}' takes contains with a text value")
        out.update(op="contains", value=v.strip()[:80])
        return out
    if spec.kind in ("num", "date"):
        conv = _num if spec.kind == "num" else _date_key
        if op == "between":
            if not isinstance(v, (list, tuple)) or len(v) != 2:
                raise FilterError(f"'{key}' between takes [min, max]")
            out["value"] = [conv(v[0]), conv(v[1])]
        elif op in ("gte", "lte", "eq"):
            out["value"] = conv(v[0] if isinstance(v, list) and len(v) == 1 else v)
        else:
            raise FilterError(f"'{key}' takes gte, lte, eq or between")
        if key == "raised_within_months" and op == "eq":
            out["op"] = "lte"
        return out
    if spec.kind == "component":
        if not isinstance(v, dict) or v.get("component") not in ss.KEYS:
            raise FilterError("component_min takes {\"component\": <component key>, \"min\": 0..1}")
        out.update(op="gte", value={"component": v["component"], "min": _num(v.get("min", 0.5))})
        return out
    if spec.kind == "stage_count":
        if not isinstance(v, dict) or _stage_norm(st, v.get("stage")) is None:
            raise FilterError("fund_led_at_stage takes {\"stage\": <stage>, \"min\": n}")
        out.update(op="gte", value={"stage": _stage_norm(st, v["stage"]), "min": _num(v.get("min", 1))})
        return out
    # enumerated or set filters
    vals = v if isinstance(v, list) else [v]
    if not vals or any(x is None or isinstance(x, (dict, list)) for x in vals):
        raise FilterError(f"'{key}' needs one or more values")
    if op not in ("eq", "in", "not_in", "contains"):
        raise FilterError(f"'{key}' takes in, not_in or eq")
    good, bad = [], []
    for x in vals[:30]:
        n = spec.norm(st, x) if spec.norm else str(x)
        if n is None:
            bad.append(str(x))
        elif n not in good:
            good.append(n)
    if spec.kind == "evidence" and len(good) == 1:
        op = "gte" if op in ("eq", "in") else op
    if not good:
        raise FilterError(f"no known value for '{key}': {', '.join(bad)[:120]}")
    out.update(op="not_in" if op == "not_in" else ("gte" if spec.kind == "evidence" and op == "gte" else "in"),
               value=good)
    if bad:
        out["dropped_values"] = bad
    return out


def _date_key(v) -> str:
    s = str(v).strip()
    if len(s) == 4 and s.isdigit():
        return s
    if len(s) == 7 and s[:4].isdigit() and s[4] == "-" and s[5:].isdigit():
        return s
    raise FilterError("dates are YYYY or YYYY-MM")


def with_defaults(view: str, filters: list[dict]) -> list[dict]:
    keys = {f["key"] for f in filters}
    out = list(filters)
    for s in SPECS[view].values():
        if s.default and s.key not in keys:
            out.append({"key": s.key, "op": s.default["op"], "value": s.default["op"] == "is_true", "default": True})
    return out


# ---------------------------------------------------------------- evaluation
EVID_RANK = {"thin": 0, "some": 1, "solid": 2}


def evaluate(st: Store, view: str, flt: dict, facts: dict, row: Optional[dict]) -> Optional[bool]:
    spec = SPECS[view][flt["key"]]
    if spec.default and flt["op"] == "is_false":
        return True  # switching off a default exclusion keeps everyone; it never inverts into "only the excluded"
    got = spec.get(st, facts, row)
    if got is None:
        return None
    op, v = flt["op"], flt.get("value")
    k = spec.kind
    if k == "bool":
        return bool(got) == (op == "is_true")
    if k == "text":
        return v.lower() in str(got).lower()
    if k == "date":
        g = str(got)
        if op == "between":
            return v[0] <= g[:len(v[0])] and g[:len(v[1])] <= v[1]
        return g[:len(v)] >= v if op == "gte" else g[:len(v)] <= v if op == "lte" else g.startswith(v)
    if k == "num":
        if op == "between":
            return v[0] <= got <= v[1]
        return got >= v if op == "gte" else got <= v if op == "lte" else got == v
    if k == "component":
        cv = _comp_value(got, v["component"])
        return None if cv is None else cv >= v["min"]
    if k == "stage_count":
        return got.get(v["stage"], 0) >= v["min"]
    if k == "evidence":
        if op == "gte":
            return EVID_RANK[got] >= min(EVID_RANK[x] for x in v)
        hit = got in v
        return not hit if op == "not_in" else hit
    if k == "sector":
        hit = any((x in got["tags"] or x in got["text_tags"]) if x in SECTOR_TAGS else x in got["text"] for x in v)
        return not hit if op == "not_in" else hit
    if k == "coinvest":
        hit = any(set(got) & st.coinvestors_of(x) for x in v)
        return not hit if op == "not_in" else hit
    if k == "set":
        g = set(got)
        if flt["key"] == "has_named_angel":
            v = ["any" if x in ("true", "yes") else x for x in v]
        hit = bool(g & set(v))
        return not hit if op == "not_in" else hit
    hit = got in v  # str
    return not hit if op == "not_in" else hit


def coverage(st: Store, view: str, key: str, rows: Optional[dict] = None) -> dict:
    """How many entities have data for this filter (n of total). rows: {ckey: scored row} for companies."""
    spec = SPECS[view][key]
    if view == "companies":
        items = [(f, (rows or {}).get(ck)) for ck, f in st.facts.items()]
    elif view == "funds":
        items = [(f, None) for f in st.funds.values() if f["queried"]]
    else:
        items = [(f, None) for f in st.founders]
    n = 0
    for f, r in items:
        try:
            if spec.get(st, f, r) not in (None, "needs_2_rounds"):  # "needs 2 rounds" is a state, not data
                n += 1
        except (KeyError, TypeError):
            pass
    total = len(items)
    return {"n": n, "of": total, "pct": round(100 * n / total, 1) if total else 0.0}
