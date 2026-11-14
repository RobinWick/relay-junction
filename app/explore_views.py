"""Explore page endpoints in the shapes static/explore.js reads (contract: static/explore-fixtures/API.md).

The page filters and sorts in the browser, so list endpoints return every item. Shapes are built by
explore_shapes.py from the live snapshot (main.snap() through explore_api), app/exits.json and app/people.json,
and cached until one of them changes. AI filters reuse explore_api's Gemini step with its rate limits and enums,
then rename its query params to the page's filter keys.

Integration: main.py adds `app.include_router(explore_views.router)` and serves /explore.
"""
from __future__ import annotations

import re
import threading
from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

import explore_api as xa
import explore_shapes as xs
import people as pp
from engine import REGIONS

router = APIRouter(prefix="/api/explore/ui")
TAG_LABELS = {k: v["label"] for k, v in pp.TAGS.items()}
LEVELS = {str(lvl): label for lvl, label, _ in pp.LEVELS}
FOUNDER_WORDS = re.compile(r"founder|ceo|team|background|worked|career|consult|mckinsey|bcg|bain|alumni|\bex-", re.I)
DROPPED_LABEL = {"tags": "founder background", "co_invested_with": "co-investor name", "investor": "investor name",
                 "lead": "lead name"}
_lock = threading.Lock()
_cache: dict = {}


def _stamp(s) -> tuple:
    return (s.version, len(s.rounds), id(xa._load_json(xa.PEOPLE_PATH)), id(xa._load_json(xa.EXITS_PATH)))


def views() -> dict:
    """Every shape the page needs, rebuilt when the snapshot, people.json or exits.json change."""
    s = xa._snap()
    stamp = _stamp(s)
    with _lock:
        if _cache.get("stamp") == stamp:
            return _cache["v"]
        asof = date.fromisoformat(s.retrieved[:10])
        src = xs.source_block(s.retrieved[:10])
        exits_file = xa._load_json(xa.EXITS_PATH)
        caveat = exits_file.get("caveat") if isinstance(exits_file, dict) and exits_file.get("caveat") else xs.EXITS_CAVEAT
        people_json = xa._load_json(xa.PEOPLE_PATH) or {}
        founders, founder_details = xs.build_founders(people_json, TAG_LABELS, pp.org_key, asof)
        by_company: dict[str, list] = {}
        for p in founders:
            if p["company_key"]:
                by_company.setdefault(p["company_key"], []).append(p)
        funds, fund_details = xs.build_funds(s.rounds, s.names, s.fund_keys, asof, src, xa.exits_by_fund(), caveat)
        companies, company_details = xs.build_companies(s.rounds, s.names, asof, src, by_company)
        coverage = xs.people_coverage(people_json)
        people_src = {"name": (people_json.get("source") or {}).get("graph") or "Cala entity graph",
                      "retrieved": people_json.get("generated") or "",
                      "note": "Career facts as Cala holds them. Not a score; nothing here predicts success."}
        v = {
            "meta": xs.build_meta(funds, companies, founders, src, TAG_LABELS, LEVELS, coverage),
            "funds": {"items": funds, "source": src}, "fund_details": fund_details,
            "companies": {"items": companies, "source": src}, "company_details": company_details,
            "founders": {"items": [xs.founder_item(p) for p in founders], "source": people_src,
                         "coverage": coverage,
                         "cohorts": xs.cohort_views(people_json, set(company_details))},
            "founder_details": founder_details,
        }
        _cache.update(stamp=stamp, v=v)
        return v


def _get(request: Request) -> dict:
    xa._limit(request, "explore", xa.GET_PER_MIN)
    return views()


@router.get("/meta")
def meta(request: Request):
    return _get(request)["meta"]


@router.get("/{view}")
def list_view(view: Literal["funds", "companies", "founders"], request: Request):
    return _get(request)[view]


@router.get("/{view}/{key}")
def detail(view: Literal["funds", "companies", "founders"], key: str, request: Request):
    table = {"funds": "fund_details", "companies": "company_details", "founders": "founder_details"}[view]
    hit = _get(request)[table].get(key[:120])
    if not hit and view == "funds":
        hit = _any_fund(key[:120])
    if not hit:
        raise HTTPException(404, "Not in our Cala data.")
    return hit


def _any_fund(key: str) -> dict | None:
    """Detail for an investor outside the queried fund list, so Check can link any fund it shows."""
    s = xa._snap()
    if key not in s.by_investor:
        return None
    rounds = [s.rounds[i] for i in s.by_investor[key]]
    asof = date.fromisoformat(s.retrieved[:10])
    _, details = xs.build_funds(rounds, s.names, {key}, asof, xs.source_block(s.retrieved[:10]), xa.exits_by_fund())
    return details.get(key)


# ---------- AI filters: explore_api's answer renamed to the page's filter keys ----------
class UiAi(BaseModel):
    text: str = Field(min_length=3, max_length=600)
    role: Literal["founder", "investor"] = "founder"
    view: Literal["funds", "companies", "founders"] = "funds"


def _countries(f: dict, known: list[str]) -> list[str] | None:
    if f.get("country"):
        return [f["country"]]
    if f.get("region") in REGIONS:
        names = REGIONS[f["region"]]
        return [c for c in known if any(n in c.lower() for n in names)] or None
    return None


def _range(lo, hi) -> dict | None:
    return None if lo is None and hi is None else {"min": lo, "max": hi}


def to_ui(out: dict, known_countries: list[str], text: str = "") -> dict:
    """explore_api.clamp_filters output -> {view, filters} with the keys explore.js understands. On companies,
    founder fields need founder words in the sentence: the model adds a background tag unasked, which empties the list."""
    f, t = out["filters"], out["target"]
    unmatched = [DROPPED_LABEL.get(k, k.replace("_", " ")) for k in out.get("dropped") or []
                 if not (t == "funds" and k == "tags")]  # the model adds founder tags to fund searches unasked
    ui: dict = {}
    countries = _countries(f, known_countries)
    if countries and t != "people":
        ui["country"] = countries
    if f.get("stage") and t != "people":
        if f["stage"] == "unknown":
            unmatched.append("stage not stated")
        else:
            ui["stage"] = [f["stage"]]
    for k, val in f.items():
        if val == "no":
            unmatched.append(f"{k.replace('_', ' ')}: no")
    if t == "funds":
        if f.get("lead_share_min") is not None:
            ui["lead_share"] = {"min": round(f["lead_share_min"] * 100), "max": None}
        if f.get("min_known"):
            ui["lead_known"] = f["min_known"]
        if f.get("size_band"):
            lo, hi = xa.SIZE_BANDS[f["size_band"]]
            ui["round"] = {"min": lo or None, "max": hi if hi < 1e9 else None}
        if f.get("last_lead_within_months"):
            ui["last_lead"] = f["last_lead_within_months"]
        if f.get("led_downturn") == "yes":
            ui["downturn"] = True
        if f.get("has_exits") == "yes":
            ui["exits"] = True
        if f.get("co_invested_with"):
            ui["co_investor"] = [f["co_invested_with"]]
        return {"view": "funds", "filters": ui, "unmatched": unmatched}
    if t == "companies":
        if f.get("last_from"):
            ui["last_round_after"] = f"{f['last_from'][:4]}-01"
        if _range(f.get("amount_min"), f.get("amount_max")):
            ui["last_amount"] = _range(f.get("amount_min") or None, f.get("amount_max"))
        if _range(f.get("months_since_min"), f.get("months_since_max")):
            ui["months_since"] = _range(f.get("months_since_min"), f.get("months_since_max"))
        if f.get("investor"):
            ui["investor"] = [f["investor"]]
        if f.get("lead"):
            ui["lead"] = [f["lead"]]
        about_founders = bool(FOUNDER_WORDS.search(text))
        if f.get("tags") and about_founders:
            ui["founder_tags"] = [TAG_LABELS[x] for x in f["tags"]]
        if f.get("repeat_founder") == "yes" and about_founders:
            ui["repeat"] = True
        if (f.get("tags") or f.get("repeat_founder")) and not about_founders:
            unmatched.append("founder background (not in your sentence)")
        return {"view": "companies", "filters": ui, "unmatched": unmatched}
    if f.get("tags"):
        ui["tags"] = [TAG_LABELS[x] for x in f["tags"]]
    if _range(f.get("avg_tenure_min"), f.get("avg_tenure_max")):
        ui["tenure"] = _range(f.get("avg_tenure_min"), f.get("avg_tenure_max"))
    if _range(f.get("ups_per_year_min"), f.get("ups_per_year_max")):
        ui["ups"] = _range(f.get("ups_per_year_min"), f.get("ups_per_year_max"))
    if f.get("prior_founder") == "yes":
        ui["repeat"] = True
    if f.get("prior_exit") == "yes":
        ui["prior_exit"] = True
    return {"view": "founders", "filters": ui, "unmatched": unmatched}


@router.post("/ai-filters")
def ai_filters(body: UiAi, request: Request):
    out = xa.ai_filters(xa.AiFilters(text=body.text, role=body.role), request)
    res = to_ui(out, views()["meta"]["countries"], body.text)
    engine = f"Gemini ({out['model']})" if out["via"] == "gemini" else "Keyword rules"
    return {**res, "engine": engine, "explanation": out.get("explanation") or "", "notice": out.get("notice"),
            "filled_by_keywords": out.get("filled_by_keywords") or []}
