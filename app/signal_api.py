"""Recount Signal API (signal/DESIGN.md section 3): ranked companies, funds and founders with transparent scores.

Integration: main.py adds `app.include_router(signal_api.router)` and `app.include_router(signal_api.pages)`.
The snapshot comes from main.SNAP_DICT through signal_data.store() (rebuilt only when the snapshot version changes).
Scores are precomputed per weight set and cached; list answers are cached per query.

Every score carries its components, raw values, weights, points and the Cala records behind them. Missing
components count as a visible neutral 0.5. Filters that lack data for an entity report it as not considered.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from collections import Counter, OrderedDict
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

import auth
import signal_chat as sc
import signal_data as sd
import signal_filters as sf
import signal_score as ss

HERE = Path(__file__).parent
router = APIRouter(prefix="/api/signal")
pages = APIRouter()

BAND_ORDER = {"strong": 0, "promising": 1, "watch": 2, "low": 3, "not_enough_data": 4, "no_data": 5}
BAND_RULES = [
    {"key": "strong", "label": "Strong signal", "rule": "Top tenth on your weights, and well documented."},
    {"key": "promising", "label": "Promising, thin data",
     "rule": "Top tenth on your weights, but Cala has little on them. Unknowns lower evidence, never the score."},
    {"key": "watch", "label": "Watch", "rule": "Above most peers on your weights."},
    {"key": "low", "label": "Low", "rule": "Below most peers on your weights."},
    {"key": "not_enough_data", "label": "Not enough data",
     "rule": "No stage on the last round, so size and breadth cannot be compared."},
]
FORMULA = "Signal = 100 x sum(weight x value). Missing parts count as neutral 0.5 and are shown hatched."
HONESTY = ["Lead accuracy: 74% exact, 89% right fund.", "Cala names no lead in about a third of seed rounds.",
           "No exit found does not mean no exit.",
           "Weights were chosen after seeing 2018 to 2023; held-out years were seen by the design debate.",
           "Revenue, headcount and valuation are not in Cala data here.",
           "Never read the score as a probability."]
FALLBACK_LINE = ("Signal is a transparent summary of Cala's funding record. Use it to sort and read, not to "
                 "predict.")
HOW = {
    "size_for_stage": "Percentile of the last sized, staged round among rounds of the same stage in year t-1..t+1 "
                      "(4 years before today when under 15 peers).",
    "syndicate_breadth": "Named non-public investors on the last round (capped 12), percentile within stage and "
                         "history depth.",
    "lead_named": "1 when Cala names a lead on the last round, else 0.",
    "acceleration": "log2(previous gap / last gap) between dated raises, needs 3 raises.",
    "backer_graduation": "Best backer's shrunk rate of early bets that raised again within 24 months, percentile.",
    "insider_follow_on": "Share of the previous raise's investors back in the last raise.",
    "named_angels": "Person-named backers (name heuristic), upward only.",
    "lead_supply": "Funds that led the next stage in the company's country in the last 36 months, percentile.",
    "cross_border": "Share of queried backers whose main market is another country.",
    "step_up": "Last raise vs previous raise, down rounds floored.",
    "backer_exits": "Exit receipts of checked backers, log scaled.",
    "freshness": "Months since last raise vs the stage median gap. Activity, not quality.",
    "sector_heat": "Sector rounds in the last 24 months vs the 24 before, relative to all tagged rounds. Only with a "
                   "sector query.",
}

# ---------------------------------------------------------------- rate limits (same shape as main.py)
GET_PER_MIN = {"session": 120, "ip": 400}
CHAT_PER_MIN = {"session": 12, "ip": 40}
CHAT_IP_DAY_CAP = int(os.environ.get("SIGNAL_CHAT_IP_DAY_CAP", "150"))
CHAT_DAY_CAP = int(os.environ.get("SIGNAL_CHAT_DAY_CAP", "1000"))
MAX_CHAT_BODY = 8192
_hits: dict[str, list] = {}
_hits_lock = threading.Lock()


def _over(bucket: str, key: str, limit: int, window_s: float) -> bool:
    now = time.time()
    with _hits_lock:
        k = f"{bucket}:{key}"
        hits = [t for t in _hits.get(k, []) if now - t < window_s]
        over = len(hits) >= limit
        if not over:
            hits.append(now)
        _hits[k] = hits
        if len(_hits) > 20000:
            for stale in [x for x in _hits if x.split(":", 1)[0].endswith("-s")]:
                del _hits[stale]
        return over


def _limit(request: Request, bucket: str, per_min: dict) -> None:
    ip = auth.client_ip(request)
    sess = (request.cookies.get(auth.COOKIE) or "anon-" + ip)[-16:]
    if _over(bucket + "-ip", ip, per_min["ip"], 60) or _over(bucket + "-s", sess, per_min["session"], 60):
        raise HTTPException(429, "Too many requests in a minute. Wait a moment.")


def _bad(detail: str, error: str = "bad_filter"):
    return JSONResponse({"error": error, "detail": detail}, status_code=400)


# ---------------------------------------------------------------- caches
_list_cache: "OrderedDict[str, dict]" = OrderedDict()
_list_lock = threading.Lock()


def _cached(key: str, fn):
    with _list_lock:
        if key in _list_cache:
            _list_cache.move_to_end(key)
            return _list_cache[key]
    val = fn()
    with _list_lock:
        _list_cache[key] = val
        while len(_list_cache) > 256:
            _list_cache.popitem(last=False)
    return val


def warm() -> None:
    """Precompute the store, the default ranking and /meta (startup)."""
    st = sd.store()
    st.run(st.default_weights)
    _meta(st)
    companies_payload(st, [], {})


def _warm_in_background() -> None:
    def go():
        try:
            warm()
        except Exception as e:  # serving still works: the store builds on the first request instead
            print(f"signal warm failed: {type(e).__name__}: {e}")
    if os.environ.get("SIGNAL_WARM", "on") == "on":
        threading.Thread(target=go, daemon=True).start()


pages.add_event_handler("startup", _warm_in_background)


# ---------------------------------------------------------------- parsing helpers
def _parse_filters(st: sd.Store, view: str, raw: Optional[str]) -> list[dict]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except ValueError:
        raise sf.FilterError("filters must be a JSON array")
    if not isinstance(data, list) or len(data) > 40:
        raise sf.FilterError("filters must be a JSON array of at most 40 filters")
    out = []
    for f in data:
        n = sf.normalise(st, view, f)
        out = [x for x in out if x["key"] != n["key"]] + [n]
    return out


def _parse_weights(raw: Optional[str]) -> dict:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        raise sf.FilterError("weights must be a JSON object")
    if not isinstance(data, dict):
        raise sf.FilterError("weights must be a JSON object")
    return data


def _effective_weights(st: sd.Store, overrides: dict, filters: list[dict]) -> dict:
    sector_active = any(f["key"] == "sector" and f["op"] == "in" for f in filters)
    try:
        return ss.clamp_weights(overrides, base=st.default_weights, sector_active=sector_active)
    except ValueError as e:
        raise sf.FilterError(str(e))


def _diff(st: sd.Store, w: dict, by: str = "user") -> list[dict]:
    return [{"key": k, "from": round(st.default_weights[k], 4), "to": round(w[k], 4), "by": by} for k in ss.KEYS
            if abs(w[k] - st.default_weights[k]) > 0.0005]


def _backtest_line(st: sd.Store) -> str:
    return (st.backtest.get("verdict") or {}).get("line") or FALLBACK_LINE


# ---------------------------------------------------------------- company rows
def _company_score_row(run: ss.ScoreRun, st: sd.Store, ck: str) -> dict:
    """The scored row, or an unranked placeholder for companies with no equity round (programme or disputed only)."""
    r = run.rows.get(ck)
    if r is not None:
        return r
    comps = [{"key": k, "label": ss.LABEL[k], "tier": ss.TIER[k], "weight": round(run.weights[k], 4),
              "present": False, "value": ss.NEUTRAL, "points": 0.0, "raw": {}, "records": [], "peer_group": None,
              "missing_reason": "no equity round on file (only programme, grant or disputed rounds)", "text": None}
             for k in ss.KEYS]
    n = sum(1 for k in ss.KEYS if run.weights[k] > 0)
    return {"ckey": ck, "ranked": False, "score": None, "raw_score": None, "rank": None, "rank_in_cohort": None,
            "cohort_size": None, "percentile": None, "band": "not_enough_data",
            "score_reason": "Not enough data: no equity round on file", "components": comps,
            "coverage": {"k": 0, "n": n, "weighted": 0.0},
            "evidence": {"value": 0.0, "band": "thin", "parts": {}}, "flags": [], "why": []}


def _company_list_row(st: sd.Store, f: dict, r: dict, fair: bool) -> dict:
    chips = [f["history_depth"]]
    if f.get("lead_desert"):
        chips.append("lead_desert")
    if f.get("raised_in_downturn"):
        chips.append("raised_in_downturn")
    flags = list(r["flags"])
    if f.get("backer_faded"):
        flags.append("backer_faded")
    return {
        "id": f"c:{f['ckey']}", "rank": r.get("rank_in_cohort") if fair else r.get("rank"),
        "rank_global": r.get("rank"), "rank_in_cohort": r.get("rank_in_cohort"), "cohort_size": r.get("cohort_size"),
        "name": f["name"], "country": f["country"], "region": f["region"],
        "sector": {"tags": f["sector_tags"], "text_tags": f["sector_text_tags"], "text": f["sector_text"][:1],
                   "source": f["sector_source"]},
        "history_depth": f["history_depth"], "last_stage": f["last_stage"], "last_round": f["last_round"],
        "total_known_eur_m": f["total_known_eur_m"], "n_rounds": f["n_rounds"],
        "score": r["score"], "score_reason": r.get("score_reason"), "band": r["band"],
        "evidence": {"value": r["evidence"]["value"], "band": r["evidence"]["band"]},
        "coverage": r["coverage"], "why": r["why"], "flags": flags, "chips": chips,
        "components": {p["key"]: (round(p["value"], 3) if p["present"] else None) for p in r["components"]},
    }


SORTS = {
    "score": lambda f, r: r["raw_score"],
    "name": lambda f, r: f["name"].lower(),
    "last_round_date": lambda f, r: f["last_round"]["date"] if f["last_round"] else None,
    "last_amount_eur_m": lambda f, r: f["last_round"]["amount_eur_m"] if f["last_round"] else None,
    "total_known_eur_m": lambda f, r: f["total_known_eur_m"],
    "evidence": lambda f, r: r["evidence"]["value"],
    "based_on": lambda f, r: r["coverage"]["k"],
    "syndicate_size": lambda f, r: f["syndicate_size"],
    "country": lambda f, r: f["country"]["name"] if f["country"]["code"] != "XX" else None,
    "stage": lambda f, r: ss.STAGE_IX.get(f["last_stage"]) if f["last_stage"] else None,
    "n_rounds": lambda f, r: f["n_rounds"],
    "months_since_last": lambda f, r: f["months_since_last"],
}


def _parse_sort(sort: str, allowed) -> tuple[str, str]:
    key, _, d = (sort or "score:desc").partition(":")
    d = d or "desc"
    if key not in allowed or d not in ("asc", "desc"):
        raise sf.FilterError(f"unknown sort '{sort}'")
    return key, d


def _order(items: list, getter, desc: bool) -> list:
    have = [x for x in items if getter(x) is not None]
    none = [x for x in items if getter(x) is None]
    have.sort(key=getter, reverse=desc)
    return have + none


def _apply(st: sd.Store, view: str, filters: list[dict], items: list[tuple]) -> tuple[list, list, Counter]:
    """items: [(facts, row)]. Returns (matched, no_data_only, not_considered counter)."""
    matched, no_data, nc = [], [], Counter()
    for f, r in items:
        missing, ok = [], True
        for flt in filters:
            res = sf.evaluate(st, view, flt, f, r)
            if res is None:
                missing.append(flt["key"])
            elif not res:
                ok = False
                break
        if not ok:
            continue
        if missing:
            for k in missing:
                nc[k] += 1
            no_data.append((f, r))
        else:
            matched.append((f, r))
    return matched, no_data, nc


def _coverage_warnings(st: sd.Store, view: str, filters: list[dict], rows: Optional[dict]) -> list[dict]:
    out = []
    for flt in filters:
        if flt.get("default"):
            continue
        c = sf.coverage(st, view, flt["key"], rows)
        if c["pct"] < sf.LOW_COVERAGE:
            label = sf.SPECS[view][flt["key"]].label
            out.append({"filter": flt["key"], "coverage_pct": c["pct"], "n": c["n"], "of": c["of"],
                        "text": f"{label} only exists for {c['n']:,} of {c['of']:,}. "
                                f"{c['of'] - c['n']:,} have no data for it and were not considered."})
    return out


def companies_payload(st: sd.Store, filters: list[dict], overrides: dict, sort: str = "score:desc",
                      limit: int = 50, offset: int = 0, fair_rank: bool = False, include_unranked: bool = True,
                      no_data_group: bool = False, by: str = "user") -> dict:
    w = _effective_weights(st, overrides, filters)
    run = st.run(w)
    full = sf.with_defaults("companies", filters)
    key, d = _parse_sort(sort, SORTS)
    rows = {ck: _company_score_row(run, st, ck) for ck in st.facts}
    items = [(st.facts[ck], rows[ck]) for ck in st.facts]
    if not include_unranked:
        items = [x for x in items if x[1]["ranked"]]
    matched, no_data, nc = _apply(st, "companies", full, items)
    getter = SORTS[key]
    if key == "score" and fair_rank:
        ordered = _order(matched, lambda x: (x[1]["rank_in_cohort"] or 10 ** 6) * (-1 if d == "desc" else 1)
                         if x[1]["ranked"] else None, True)
    elif key == "score":
        ordered = sorted(matched, key=lambda x: (BAND_ORDER[x[1]["band"]] if d == "desc" else 0,
                                                 -(x[1]["raw_score"] or -1) if d == "desc" else (x[1]["raw_score"] or 2),
                                                 x[0]["ckey"]))
    else:
        ordered = _order(matched, lambda x: getter(*x), d == "desc")
    groups = Counter(r["band"] for _, r in ordered)
    out_rows = [_company_list_row(st, f, r, fair_rank) for f, r in ordered]
    if no_data_group:
        nd = [{**_company_list_row(st, f, r, fair_rank), "group": "no_data"} for f, r in no_data]
        out_rows += nd
        groups["no_data"] = len(nd)
    page = out_rows[offset:offset + limit]
    nc_list = [{"filter": k, "count": v, "reason": f"no {k.replace('_', ' ')} data"}
               for k, v in nc.most_common()]
    ranked_n = len(run.ranked)
    return {
        "meta": {"as_of": sd.AS_OF, "snapshot_version": st.version, "rules_hash": run.rules_hash,
                 "total": len(st.facts), "ranked": ranked_n, "unranked": len(st.facts) - ranked_n,
                 "matched": len(matched), "not_considered": nc_list,
                 "considered": len(matched), "no_data_shown": no_data_group,
                 "filters_applied": full,
                 "weights_effective": {k: round(v, 4) for k, v in w.items()}, "weights_diff": _diff(st, w, by),
                 "bands": {"strong_min_pct": 90, "watch_min_pct": 60},
                 "coverage_warnings": _coverage_warnings(st, "companies", filters, rows),
                 "backtest_line": _backtest_line(st), "fair_rank": fair_rank, "sort": f"{key}:{d}"},
        "rows": page,
        "groups": [{"band": b, "count": groups.get(b, 0)} for b in BAND_ORDER if groups.get(b, 0) or b != "no_data"],
        "limit": limit, "offset": offset,
    }


# ---------------------------------------------------------------- funds and founders rows
def _fund_list_row(f: dict) -> dict:
    keep = ("id", "key", "name", "country", "queried", "score", "score_label", "score_reason", "led_24m",
            "led_prior_24m", "lead_share", "months_since_last_lead", "exit_receipts", "evidence", "main_stage",
            "rounds_on_file", "companies", "faded")
    row = {k: f.get(k) for k in keep}
    row["id"] = f.get("id") or f"f:{f['key']}"
    if f.get("components"):
        row["components"] = {c["key"]: round(c["value"], 3) for c in f["components"]}
    return row


FUND_SORTS = {"score": lambda f: f.get("raw_score"), "name": lambda f: f["name"].lower(),
              "led_24m": lambda f: f.get("led_24m"), "rounds_on_file": lambda f: f.get("rounds_on_file"),
              "months_since_last_lead": lambda f: f.get("months_since_last_lead"),
              "lead_share": lambda f: (f["lead_share"]["led"] / f["lead_share"]["of"])
              if f.get("lead_share") and f["lead_share"]["of"] else None}


def funds_payload(st: sd.Store, filters: list[dict], sort: str, limit: int, offset: int, stage: str) -> dict:
    full = sf.with_defaults("funds", filters)
    key, d = _parse_sort(sort, FUND_SORTS)
    funds = st.funds
    if stage != "seed":  # stage fit depends on the selected stage
        rescored = ss.fund_scores(st.inp, ss.NOW_T, stage)
        funds = {k: ({**f, **{x: rescored[k][x] for x in ("score", "raw_score", "components")}} if f["queried"] else f)
                 for k, f in funds.items()}
    items = [(f, None) for f in funds.values()]
    matched, _, nc = _apply(st, "funds", full, items)
    ordered = _order([f for f, _ in matched], FUND_SORTS[key], d == "desc")
    return {"meta": {"as_of": sd.AS_OF, "snapshot_version": st.version, "total": len(funds),
                     "queried": len(st.fund_keys), "matched": len(ordered), "stage": stage,
                     "score_label": ss.FUND_LABEL, "filters_applied": full,
                     "not_considered": [{"filter": k, "count": v} for k, v in nc.most_common()],
                     "coverage_warnings": _coverage_warnings(st, "funds", filters, None),
                     "weights": {k: w for k, _, w in ss.FUND_COMPONENTS},
                     "note": "Only the queried funds get a number; others are seen only as co-investors."},
            "rows": [_fund_list_row(f) for f in ordered[offset:offset + limit]], "limit": limit, "offset": offset}


def _founder_list_row(st: sd.Store, f: dict, run: ss.ScoreRun) -> dict:
    comp = None
    if f["company_ckey"]:
        cf = st.facts[f["company_ckey"]]
        cr = run.rows.get(f["company_ckey"])
        comp = {"id": f"c:{cf['ckey']}", "name": cf["name"], "score": cr["score"] if cr else None,
                "score_label": "company score, not a founder score"}
    return {"id": f["id"], "name": f["name"], "title": f["title"], "company": comp, "country": f["country"],
            "founder_evidence": f["founder_evidence"], "score": f["score"], "score_reason": f["score_reason"],
            "score_label": f["score_label"], "flags": f["flags"], "cohort_tags": f["cohort_tags"]}


FOUNDER_SORTS = {"evidence": lambda f: f["founder_evidence"]["k"], "name": lambda f: f["name"].lower()}


def founders_payload(st: sd.Store, filters: list[dict], sort: str, limit: int, offset: int) -> dict:
    full = sf.with_defaults("founders", filters)
    key, d = _parse_sort(sort if sort != "score:desc" else "evidence:desc", FOUNDER_SORTS)
    run = st.run(st.default_weights)
    matched, _, nc = _apply(st, "founders", full, [(f, None) for f in st.founders])
    ordered = [f for f, _ in matched]
    ordered.sort(key=lambda f: f["name"].lower())
    if key == "evidence":
        ordered.sort(key=lambda f: f["founder_evidence"]["k"], reverse=d == "desc")
    elif d == "desc":
        ordered.reverse()
    scoreable = sum(1 for f in st.founders if f["score"] is not None)
    return {"meta": {"as_of": sd.AS_OF, "snapshot_version": st.version, "total": len(st.founders),
                     "matched": len(ordered), "scoreable": scoreable, "filters_applied": full,
                     "not_considered": [{"filter": k, "count": v} for k, v in nc.most_common()],
                     "coverage_warnings": _coverage_warnings(st, "founders", filters, None),
                     "note": (f"Founder data is thin: {scoreable} of {len(st.founders)} founders have 2 or more of 4 "
                              "documented track-record facts. Everyone else shows Not enough data. The number counts "
                              "documented facts; it is not a judgment of the person. Sorted by evidence, then name.")},
            "rows": [_founder_list_row(st, f, run) for f in ordered[offset:offset + limit]],
            "limit": limit, "offset": offset}


# ---------------------------------------------------------------- endpoints: lists
def _list(request: Request, view: str, filters: Optional[str], weights: Optional[str], sort: str, limit: int,
          offset: int, fair_rank: bool, include_unranked: bool, no_data_group: bool, stage: str):
    _limit(request, "signal-get", GET_PER_MIN)
    st = sd.store()
    ck = json.dumps([view, filters, weights, sort, limit, offset, fair_rank, include_unranked, no_data_group, stage,
                     st.version])
    try:
        fl = _parse_filters(st, view, filters)
        if view == "companies":
            ov = _parse_weights(weights)
            return _cached(ck, lambda: companies_payload(st, fl, ov, sort, limit, offset, fair_rank, include_unranked,
                                                         no_data_group))
        if view == "funds":
            if sf._stage_norm(st, stage) is None:
                raise sf.FilterError(f"unknown stage '{stage}'")
            return _cached(ck, lambda: funds_payload(st, fl, sort, limit, offset, sf._stage_norm(st, stage)))
        return _cached(ck, lambda: founders_payload(st, fl, sort, limit, offset))
    except sf.FilterError as e:
        return _bad(str(e))


@router.get("/companies")
def list_companies(request: Request, filters: Optional[str] = Query(None, max_length=8000),
                   weights: Optional[str] = Query(None, max_length=2000), sort: str = "score:desc",
                   limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                   fair_rank: bool = False, include_unranked: bool = True, no_data_group: bool = False):
    return _list(request, "companies", filters, weights, sort, limit, offset, fair_rank, include_unranked,
                 no_data_group, "seed")


@router.get("/funds")
def list_funds(request: Request, filters: Optional[str] = Query(None, max_length=8000), sort: str = "score:desc",
               limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), stage: str = "seed"):
    return _list(request, "funds", filters, None, sort, limit, offset, False, True, False, stage)


@router.get("/founders")
def list_founders(request: Request, filters: Optional[str] = Query(None, max_length=8000),
                  sort: str = "evidence:desc", limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    return _list(request, "founders", filters, None, sort, limit, offset, False, True, False, "seed")


# ---------------------------------------------------------------- meta and backtest
def _component_backtest(st: sd.Store, k: str) -> dict:
    res = st.backtest.get("results") or {}
    out = {}
    for outcome, label in (("next_round_24m", "next_24m_auc"), ("graduate_b_plus_36m", "graduation_auc")):
        c = (((res.get(outcome) or {}).get("held_out") or {}).get("components") or {}).get(k) or {}
        po = c.get("present_only") or {}
        out[label] = po.get("auc")
        out[label.replace("auc", "n")] = po.get("n")
    out["scope"] = "held-out cutoffs, full-history companies, rows where the component has data"
    return out


def _meta(st: sd.Store) -> dict:
    def build():
        run = st.run(st.default_weights)
        rows = {ck: _company_score_row(run, st, ck) for ck in st.facts}
        comps = []
        for k in ss.KEYS:
            n = sum(1 for r in run.rows.values() for p in r["components"] if p["key"] == k and p["present"])
            comps.append({"key": k, "label": ss.LABEL[k], "tier": ss.TIER[k],
                          "tier_label": {"measured": "Measured", "thesis": "Your thesis, no measured lift",
                                         "conditional": "Only with a sector query"}[ss.TIER[k]],
                          "default_weight": round(st.default_weights[k], 4), "design_default": ss.DEFAULT_WEIGHTS[k],
                          "cap": ss.CAP[k], "coverage": {"n": n, "of": len(st.facts)}, "how": HOW[k],
                          "backtest": _component_backtest(st, k)})
        filters = []
        for view, specs in sf.SPECS.items():
            for sp in specs.values():
                c = sf.coverage(st, view, sp.key, rows if view == "companies" else None)
                item = {"key": sp.key, "view": view, "label": sp.label, "group": sp.group, "type": sp.type,
                        "kind": sp.kind, "entity": list(sp.entity), "source": sp.source, "coverage": c,
                        "low_coverage": c["pct"] < sf.LOW_COVERAGE, "default": sp.default, "note": sp.note}
                if sp.values and sp.key not in ("acquirer",):
                    vals = sp.values(st)
                    counts = _value_counts(st, view, sp, rows)
                    item["values"] = [{"value": v, "count": counts.get(v, 0), **_value_label(sp.key, v)}
                                      for v in vals]
                filters.append(item)
        bt = st.backtest.get("verdict") or {}
        sel = st.backtest.get("selection") or {}
        return {
            "as_of": sd.AS_OF, "snapshot_version": st.version, "rules_hash": run.rules_hash,
            "counts": {"companies": len(st.facts), "ranked": len(run.ranked), "funds": len(st.funds),
                       "funds_queried": len(st.fund_keys), "founders": len(st.founders),
                       "founders_scoreable": sum(1 for f in st.founders if f["score"] is not None),
                       "rounds": len(st.inp.rounds)},
            "components": comps,
            "weights_default": {k: round(v, 4) for k, v in st.default_weights.items()},
            "weights_note": ("Default weights chosen by validation AUC (cutoffs 2018 to 2020) among 3 candidates; "
                             "renormalised. Difference to the design defaults is within noise."),
            "weights_selection": sel,
            "fund_components": [{"key": k, "label": lab, "default_weight": w} for k, lab, w in ss.FUND_COMPONENTS],
            "fund_score_label": ss.FUND_LABEL,
            "fund_evidence_how": "0.5 x share of its rounds with a named lead + 0.5 x min(1, rounds on file / 20)",
            "founder_score_label": "Share of four track-record facts Cala documents, not a judgment of the founder.",
            "filters": filters,
            "intent_presets": [{"id": i, "label": lab, "words": words[:3], "filters": fl, "weights": ov}
                               for i, lab, words, fl, ov in sc.INTENTS],
            "regions": [{"key": k, "label": lab, "countries": sorted(cs)} for k, (lab, cs) in sd.REGIONS.items()],
            "sectors": sd.SECTOR_TAGS, "stages": ss.STAGE_ORDER,
            "bands": BAND_RULES, "formula": FORMULA,
            "backtest_line": _backtest_line(st),
            "backtest_summary": {"verdict": bt.get("verdict"), "line": _backtest_line(st),
                                 "gap_vs_size_alone": bt.get("gap_vs_size_alone"),
                                 "always": ("Size for stage carries most of the measured lift. The other parts express "
                                            "your thesis. Weights were chosen after seeing the data. Never read the "
                                            "score as a probability.")},
            "honesty": HONESTY,
            "gemini": {"model": sc.MODEL, "server_key": bool(os.environ.get("GEMINI_API_KEY")
                                                              or os.environ.get("GEMINI_API_KEY_FALLBACK")),
                       "user_key_note": "Used for your request only. Not stored on our server."},
        }
    return _cached(f"meta:{st.version}", build)


def _value_label(key: str, v) -> dict:
    if key in ("country", "fund_country"):
        c = sd.country_obj(sd.ISO_NAME.get(v))
        return {"label": c["name"], "flag": c["flag"]}
    if key == "region":
        return {"label": sd.REGIONS[v][0]}
    return {}


def _value_counts(st: sd.Store, view: str, sp: sf.Spec, rows: dict) -> Counter:
    cnt: Counter = Counter()
    if view == "companies":
        items = [(f, rows[ck]) for ck, f in st.facts.items()]
    elif view == "funds":
        items = [(f, None) for f in st.funds.values() if f["queried"]]
    else:
        items = [(f, None) for f in st.founders]
    for f, r in items:
        try:
            g = sp.get(st, f, r)
        except (KeyError, TypeError):
            continue
        if g is None:
            continue
        if sp.kind == "sector":
            for t in set(g["tags"]) | set(g["text_tags"]):
                cnt[t] += 1
        elif isinstance(g, list):
            for x in set(g):
                cnt[x] += 1
        elif isinstance(g, (str, int)):
            cnt[g] += 1
    return cnt


@router.get("/meta")
def meta(request: Request):
    _limit(request, "signal-get", GET_PER_MIN)
    return _meta(sd.store())


@router.get("/backtest")
def backtest(request: Request):
    _limit(request, "signal-get", GET_PER_MIN)
    st = sd.store()
    if not st.backtest:
        raise HTTPException(404, "Backtest not built. Run signal_backtest.py.")
    return {**st.backtest, "claim_line": _backtest_line(st)}


LAB_PATH = HERE / "signal_lab.json"
_lab_cache: dict = {}


def load_lab(path: Path = LAB_PATH) -> dict:
    """Every signal tested on held-out years (signal/hunt/build_lab.py). Read once; the file only changes on deploy."""
    if path not in _lab_cache:
        _lab_cache[path] = json.loads(path.read_text()) if path.exists() else {}
    return _lab_cache[path]


@router.get("/lab")
def lab(request: Request):
    _limit(request, "signal-get", GET_PER_MIN)
    d = load_lab()
    if not d.get("rows"):
        raise HTTPException(404, "Lab not built. Run signal/hunt/build_lab.py.")
    return d


# ---------------------------------------------------------------- detail
def _strip(prefix: str, id_: str) -> str:
    return id_[len(prefix):] if id_.startswith(prefix) else id_


def company_detail(st: sd.Store, ck: str, overrides: dict, filters: list[dict]) -> Optional[dict]:
    f = st.facts.get(ck)
    if f is None:
        return None
    w = _effective_weights(st, overrides, filters)
    run = st.run(w)
    r = _company_score_row(run, st, ck)
    comps = []
    bt = {k: _component_backtest(st, k) for k in ss.KEYS}
    for p in r["components"]:
        recs = [{**x, "source_url": f"/api/record/{x['round_id']}"} if "round_id" in x else x for x in p["records"]]
        comps.append({**p, "records": recs, "backtest": bt[p["key"]], "how": HOW[p["key"]],
                      "tier_label": {"measured": "Measured", "thesis": "Your thesis", "conditional": "Off"
                                     if p["weight"] == 0 else "Sector query"}[p["tier"]]})
    allr = sorted((x for x in st.inp.rounds if x["ckey"] == ck), key=lambda x: (x["t"], x["id"]))
    rounds = []
    for x in allr:
        fl = [n for n, on in (("not_led", x.get("not_led")), ("disputed", x.get("disputed")),
                              ("sourced", x.get("source")), ("graph_checked", x.get("graph")),
                              ("corrected", x.get("corrected"))) if on]
        rounds.append({"id": x["id"], "date": sd.ym(x), "date_precision": sd.PRECISION[sd._date_precision(x)],
                       "stage": x.get("stage"), "type": x.get("type"), "amount_eur_m": x.get("amount_eur_m"),
                       "amount_raw": x.get("amount_raw"),
                       "leads": [st.names.get(k, k) for k in x.get("leads") or []],
                       "participants": [st.names.get(k, k) for k in x.get("participants") or []],
                       "query_path": x.get("query_path"), "sources": len(x.get("sources") or []), "flags": fl,
                       "record_url": f"/api/record/{x['id']}"})
    leads_all = set(f["leads_all"])
    ctx = st.prep.ctx
    investors = []
    for k in f["backers"]:
        fund = st.funds.get(k, {})
        investors.append({"key": k, "id": f"f:{k}", "name": st.names.get(k, k),
                          "role": "lead" if k in leads_all else "participant", "queried": k in st.fund_keys,
                          "graduation": ({"k": ctx.grad[k][1], "n": ctx.grad[k][0]} if k in ctx.grad else None),
                          "exit_receipts": fund.get("exit_receipts"),
                          "person_named": k in set(_angel_keys(st, f))})
    founders = [_founder_list_row(st, p, run) for p in st.founders if p["company_ckey"] == ck or ck in p["ckeys"]]
    move = []
    for p in comps:
        if p["weight"] <= 0:
            continue
        if p["key"] == "lead_named" and p["present"] and p["value"] == 0:
            move.append({"key": p["key"], "text": f"A named lead on the next round adds up to "
                                                  f"{round(100 * p['weight'], 1)} points."})
        elif not p["present"]:
            move.append({"key": p["key"], "text": f"Data for {p['label'].lower()} would move the score by up to "
                                                  f"{round(50 * p['weight'], 1)} points either way "
                                                  f"(now counted neutral: {p['missing_reason']})."})
    chips = [f"lead_desert:{str(bool(f['lead_desert'])).lower()}" if f["lead_desert"] is not None else None,
             f"raised_in_downturn:{str(f['raised_in_downturn']).lower()}",
             f"history:{f['history_depth']}"]
    return {
        "entity": "company", "id": f"c:{ck}", "name": f["name"], "country": f["country"], "region": f["region"],
        "entity_id": f["entity_id"], "history_depth": f["history_depth"], "flags": r["flags"],
        "last_stage": f["last_stage"], "total_known_eur_m": f["total_known_eur_m"], "first_year": f["first_year"],
        "score": {"value": r["score"], "reason": r.get("score_reason"), "rank": r.get("rank"),
                  "rank_in_cohort": r.get("rank_in_cohort"), "cohort_size": r.get("cohort_size"),
                  "of": len(run.ranked), "band": r["band"], "percentile": r.get("percentile"),
                  "rules_hash": run.rules_hash, "formula": FORMULA, "components": comps},
        "evidence": r["evidence"], "coverage": r["coverage"], "why": r["why"],
        "what_would_move_it": move, "rounds": rounds, "investors": investors, "founders": founders,
        "founders_note": None if founders else "Cala names no founder for this company.",
        "sector": {"tags": f["sector_tags"], "text_tags": f["sector_text_tags"], "text": f["sector_text"],
                   "source": f["sector_source"],
                   "note": "A Cala tag means Cala returned the company for that sector slice; not a verified label."},
        "cohorts": f["cohorts"], "facts": {k: f[k] for k in (
            "months_since_last", "months_at_stage", "n_rounds", "raised_vs_stage_pct", "step_up_ratio",
            "accelerating", "round_due", "outside_new_lead", "insider_came_back", "backer_graduation",
            "backer_exit", "lead_desert", "foreign_backer", "named_angels", "serial_angel", "top50_lead_in_cap_table",
            "lead_upgrade", "lead_active_at_stage_months", "backer_faded", "crossover", "raised_in_downturn",
            "cycle_bridge", "stage_velocity", "syndicate_size", "acquirers", "sector_heat")},
        "chips": [c for c in chips if c], "weights_effective": {k: round(v, 4) for k, v in w.items()},
        "backtest_line": _backtest_line(st),
    }


def _angel_keys(st: sd.Store, f: dict) -> list[str]:
    return [k for k in f["backers"] if ss.is_person(st.names.get(k, k))]


def fund_detail(st: sd.Store, key: str) -> Optional[dict]:
    f = st.funds.get(key)
    if f is None:
        return None
    run = st.run(st.default_weights)
    row = _fund_list_row(f)
    if not f["queried"]:
        return {**row, "entity": "fund", "evidence_cards": [],
                "portfolio": [_portfolio_row(st, run, ck) for ck in f.get("portfolio_ckeys", [])[:100]]}
    g = f.get("graduation")
    cards = [
        {"key": "lead_pace", "label": "Lead pace", "value": {"led_24m": f["led_24m"], "led_prior_24m": f["led_prior_24m"],
                                                           "months_since_last_lead": f["months_since_last_lead"]}},
        {"key": "graduation", "label": "Early bets that raised again within 24 months",
         "value": ({"k": g["k"], "n": g["n"]} if g and g["n"] >= 8 else None),
         "text": (f"{g['k']} of {g['n']}" if g and g["n"] >= 8 else "too few to judge")},
        {"key": "exit_receipts", "label": "Exit receipts", "value": f["exit_receipts"],
         "items": [{"company": e["company"], "year": e.get("year"), "acquirers": e.get("acquirers"),
                    "value_bucket": _bucket(e.get("value_usd"))} for e in f.get("exits", [])],
         "text": None if f["exit_receipts"]["state"] == "checked" else "not checked",
         "note": "No exit found does not mean no exit."},
        {"key": "downturn", "label": "Lead share 2022 to 2023 vs 2019 to 2021",
         "value": {"downturn": f["downturn_lead_share"], "boom": f["boom_lead_share"]}},
        {"key": "co_investors", "label": "Top co-investors (frequency x recency)", "value": f["top_coinvestors"]},
        {"key": "blind_spot", "label": "Seed rounds with no named lead", "value": f["seed_no_lead_share"]},
    ]
    if f.get("faded"):
        cards.append({"key": "faded", "label": "Leads less often after 2021 (flag, not a verdict)", "value": f["faded"]})
    port = sorted((_portfolio_row(st, run, ck) for ck in f.get("portfolio_ckeys", [])),
                  key=lambda x: (x["score"] is None, -(x["score"] or 0), x["name"]))
    return {**row, "entity": "fund", "components": f.get("components"), "led_by_stage": f["led_by_stage"],
            "evidence_cards": cards, "portfolio": port[:200], "portfolio_total": len(port)}


def _bucket(v) -> Optional[str]:
    if not v:
        return None
    return "under 100M USD" if v < 1e8 else "100M to 1B USD" if v < 1e9 else "over 1B USD"


def _portfolio_row(st: sd.Store, run: ss.ScoreRun, ck: str) -> dict:
    f = st.facts[ck]
    r = run.rows.get(ck)
    return {"id": f"c:{ck}", "name": f["name"], "country": f["country"], "last_stage": f["last_stage"],
            "score": r["score"] if r else None, "band": r["band"] if r else "not_enough_data"}


def founder_detail(st: sd.Store, pid: str) -> Optional[dict]:
    f = next((x for x in st.founders if x["pid"] == pid or x["id"] == pid), None)
    if f is None:
        return None
    run = st.run(st.default_weights)
    return {**_founder_list_row(st, f, run), "entity": "founder", "roles": f["roles"], "founded": f["founded"],
            "prior_exits": f["prior_exits"], "facts": f["founder_evidence"]["facts"],
            "missing": f["founder_evidence"]["missing"], "description": f["description"], "files": f["files"],
            "link_basis": f["link_basis"],
            "companies": [_portfolio_row(st, run, ck) for ck in f["ckeys"]]}


@router.get("/companies/{cid:path}")
def get_company(cid: str, request: Request, weights: Optional[str] = Query(None, max_length=2000),
                filters: Optional[str] = Query(None, max_length=8000)):
    _limit(request, "signal-get", GET_PER_MIN)
    st = sd.store()
    try:
        fl = _parse_filters(st, "companies", filters)
        d = company_detail(st, _strip("c:", cid), _parse_weights(weights), fl)
    except sf.FilterError as e:
        return _bad(str(e))
    return d if d else JSONResponse({"error": "not_found"}, status_code=404)


@router.get("/funds/{fid:path}")
def get_fund(fid: str, request: Request):
    _limit(request, "signal-get", GET_PER_MIN)
    st = sd.store()
    d = fund_detail(st, _strip("f:", fid))
    return d if d else JSONResponse({"error": "not_found"}, status_code=404)


@router.get("/founders/{pid:path}")
def get_founder(pid: str, request: Request):
    _limit(request, "signal-get", GET_PER_MIN)
    st = sd.store()
    d = founder_detail(st, _strip("p:", pid))
    return d if d else JSONResponse({"error": "not_found"}, status_code=404)


# ---------------------------------------------------------------- chat
class Current(BaseModel):
    filters: list = Field(default_factory=list, max_length=40)
    weights: dict = Field(default_factory=dict)


class Chat(BaseModel):
    message: str = Field(default="", max_length=4000)
    view: Literal["companies", "funds", "founders"] = "companies"
    current: Optional[Current] = None
    user_api_key: Optional[str] = Field(default=None, max_length=200)

    def __repr__(self) -> str:  # never print the user key
        return f"Chat(view={self.view!r}, message_len={len(self.message)})"

    __str__ = __repr__


@router.post("/chat")
def chat(body: Chat, request: Request):
    length = request.headers.get("content-length")
    if not length or not length.isdigit() or int(length) > MAX_CHAT_BODY:
        raise HTTPException(413, "Request body missing or too large.")
    _limit(request, "signal-chat", CHAT_PER_MIN)
    msg = body.message.strip()
    if not msg:
        return JSONResponse({"error": "empty_message"}, status_code=400)
    truncated = len(msg) > sc.MAX_MESSAGE
    msg = msg[:sc.MAX_MESSAGE]
    st = sd.store()
    user_key = (body.user_api_key or "").strip() or None
    t0 = time.time()
    if user_key:
        allowed, notice = True, None  # the user's own quota; per-minute limit above still holds
    else:
        ip = auth.client_ip(request)
        allowed = not _over("signal-chat-day", ip, CHAT_IP_DAY_CAP, 86400) and \
            not _over("signal-chat-all", "all", CHAT_DAY_CAP, 86400)
        notice = None if allowed else "The Gemini budget for today is used up"
    try:
        g = sc.call_gemini(st, body.view, msg, user_key) if allowed else {"error": notice}
    except sc.UserKeyRejected:
        return JSONResponse({"error": "user_key_rejected",
                             "detail": "Google did not accept that Gemini key. The server key was not used."},
                            status_code=401)
    if "raw" in g:
        proposal, source, model, ms = sc.from_gemini(g["raw"]), "gemini", g["model"], g["ms"]
    else:
        proposal, source, model = sc.keyword_proposal(st, body.view, msg), "fallback", None
        ms = int((time.time() - t0) * 1000)
    cur = body.current or Current()
    cur_w = {k: v for k, v in (cur.weights or {}).items() if k in ss.KEYS}
    v = sc.validate(st, body.view, proposal, cur_w)
    if body.view == "founders" and re.search(r"\b(best|top|good|great|strongest|rank)", msg.lower()):
        v["unmatched"].append({"phrase": "best", "reason": "there is no founder quality score; founders are sorted by "
                                                           "how many of 4 track-record facts Cala documents"})
    if truncated:
        v["unmatched"].append({"phrase": "(message)", "reason": f"only the first {sc.MAX_MESSAGE} characters were read"})
    try:
        if body.view == "companies":
            prev = companies_payload(st, v["filters"], v["weight_overrides"], f"{v['sort']['key']}:{v['sort']['dir']}",
                                     10, 0, by="chat")
            w_eff, diff = prev["meta"]["weights_effective"], prev["meta"]["weights_diff"]
            warn = prev["meta"]["coverage_warnings"]
        elif body.view == "funds":
            prev = funds_payload(st, v["filters"], "score:desc", 10, 0, "seed")
            w_eff, diff, warn = v["weights_effective"], [], prev["meta"]["coverage_warnings"]
        else:
            prev = founders_payload(st, v["filters"], "evidence:desc", 10, 0)
            w_eff, diff, warn = v["weights_effective"], [], prev["meta"]["coverage_warnings"]
    except sf.FilterError as e:
        return _bad(str(e))
    resp = {"source": source, "model": model, "ms": ms,
            "notice": None if source == "gemini" else (g.get("error") or "Gemini was unavailable") +
            ", matched keywords only",
            "filters": v["filters"], "weight_overrides": v["weight_overrides"] if body.view == "companies" else {},
            "weights_effective": w_eff, "weights_diff": diff, "explanation": v["explanation"],
            "unmatched": v["unmatched"], "coverage_warnings": warn, "sort": v["sort"],
            "results_preview": {"matched": prev["meta"]["matched"], "rows": prev["rows"],
                                "not_considered": prev["meta"].get("not_considered", [])},
            "backtest_line": _backtest_line(st)}
    if body.view == "founders":
        resp["note"] = prev["meta"]["note"]
    return resp


# ---------------------------------------------------------------- page
@pages.get("/signal")
def signal_page():
    for p in (HERE / "static" / "signal.html", HERE / "static" / "signal" / "index.html"):
        if p.exists():
            return FileResponse(p)
    return JSONResponse({"error": "The Signal page is not built yet. The API is under /api/signal."}, status_code=503)
