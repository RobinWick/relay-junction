"""Explore page endpoints in the shapes static/explore.js reads (contract: docs/explore-api.md).

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
NEGATION = re.compile(r"\b(no|not|without|never|none)\b|n't\b", re.I)
DROPPED_LABEL = {"tags": "founder background", "co_invested_with": "co-investor name", "investor": "investor name",
                 "lead": "lead name"}
VIEW_TARGET = {"funds": "funds", "companies": "companies", "founders": "people"}
NO_RANKING = "Recount doesn't rank people or predict success. It shows what Cala has on file."
RANK_WORDS = re.compile(r"\b(best|worst|rank(ed|ing|s)?|score[sd]?|scoring|predict\w*|likel(y|iest)|succe(ed|ss|ssful)|"
                        r"promising|winners?|top \d+|top (founders|people|funds|companies))\b", re.I)
SORT_WORDS = re.compile(r"\b(sort(ed|ing)?|order(ed)? by|highest|lowest|largest|biggest|most active)\b[^,.;]{0,40}", re.I)
AMOUNT = re.compile(r"(?:€|\$|\b(?:eur|usd|sek|nok|dkk)\s?)?\b\d+(?:[.,]\d+)?\s?(?:m|mn|million|k|bn|billion|"
                    r"meur|musd|m€|€m)\b(?:\s?(?:eur|euros?|usd|dollars?|sek|nok))?|(?:€|\$)\s?\d+(?:[.,]\d+)?", re.I)
SECTORS = ("fintech", "healthtech", "medtech", "biotech", "saas", "ai", "climate", "climate tech", "cleantech",
           "gaming", "edtech", "proptech", "insurtech", "deeptech", "deep tech", "foodtech", "mobility", "e-commerce",
           "ecommerce", "crypto", "web3", "robotics", "energy", "logistics", "cybersecurity", "security", "quantum",
           "space", "agritech", "legaltech", "hrtech", "martech", "b2b", "b2c", "consumer", "hardware", "software",
           "marketplace", "defence", "defense", "semiconductor", "batteries")
SECTOR_RX = re.compile(r"\b(" + "|".join(re.escape(x) for x in sorted(SECTORS, key=len, reverse=True)) + r")\b", re.I)
# Filters that hold an amount, per page view: a money phrase is matched only when one of these was set
AMOUNT_KEYS = {"funds": ("round",), "companies": ("last_amount", "raised"), "founders": ()}
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
        founders, founder_details = xs.build_founders(people_json, TAG_LABELS, pp.org_key, asof, pp.merge_roles)
        by_company: dict[str, list] = {}
        for p in founders:
            if p["company_key"]:
                by_company.setdefault(p["company_key"], []).append(p)
        names = _page_names(s.names)
        funds, fund_details = xs.build_funds(s.rounds, names, s.fund_keys, asof, src, xa.exits_by_fund(), caveat)
        companies, company_details = xs.build_companies(s.rounds, names, asof, src, by_company)
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


def _page_names(names: dict) -> dict:
    """Cala fund names like 'NPIF II \u2013 Mercia Equity Finance' carry dashes; the page shows none. The AI filter
    answer is mapped through the same no_dash in to_ui, so its names still match these."""
    return {k: xs.no_dash(v) for k, v in names.items()}


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
    _, details = xs.build_funds(rounds, _page_names(s.names), {key}, asof, xs.source_block(s.retrieved[:10]),
                                xa.exits_by_fund())
    return details.get(key)


# ---------- AI filters: explore_api's answer renamed to the page's filter keys ----------
class UiAi(BaseModel):
    text: str = Field(min_length=3, max_length=600)
    role: Literal["founder", "investor"] = "founder"
    view: Literal["funds", "companies", "founders"] = "funds"


def _span(lo, hi, unit: str = "") -> str:
    if lo is not None and hi is not None:
        return f"{lo} to {hi}{unit}"
    return f"at least {lo}{unit}" if lo is not None else f"at most {hi}{unit}"


def _stage(st: str) -> str:
    return {"pre-seed": "Pre-seed", "seed": "Seed", "growth": "Growth"}.get(st) or st.title()


UI_TEXT = {
    "country": lambda v, view: ("Has rounds in " if view == "funds" else "Country ") + " or ".join(v),
    "stage": lambda v, view: ("Led at stage " if view == "funds" else "Last stage ") + " or ".join(map(_stage, v)),
    "lead_share": lambda v, view: f"Lead share {_span(v['min'], v['max'], '%')}",
    "lead_known": lambda v, view: f"At least {v} lead-known rounds",
    "round": lambda v, view: f"Median led round {_span(v['min'], v['max'])} M EUR",
    "last_lead": lambda v, view: f"Last lead within {v} months",
    "downturn": lambda v, view: "Led a round in 2022 to 2023",
    "exits": lambda v, view: "Has an exit receipt",
    "co_investor": lambda v, view: "Co-invested with " + ", ".join(v),
    "last_round_after": lambda v, view: f"Last round on or after {v}",
    "last_amount": lambda v, view: f"Last round size {_span(v['min'], v['max'])} M EUR",
    "months_since": lambda v, view: f"Months since last round {_span(v['min'], v['max'])}",
    "investor": lambda v, view: "Investors include " + ", ".join(v),
    "lead": lambda v, view: "Led a round: " + ", ".join(v),
    "founder_tags": lambda v, view: "Founder background " + ", ".join(v),
    "repeat": lambda v, view: "Repeat founder",
    "tags": lambda v, view: "Background " + ", ".join(v),
    "tenure": lambda v, view: f"Average years per role {_span(v['min'], v['max'])}",
    "ups": lambda v, view: f"Title level-ups per year {_span(v['min'], v['max'])}",
    "prior_exit": lambda v, view: "Prior exit",
}


def explain(view: str, filters: dict) -> str:
    """The explanation the page shows, built only from the filters that were set, never from the model's prose."""
    parts = [UI_TEXT[k](v, view) for k, v in filters.items() if k in UI_TEXT]
    return ("Set from your sentence: " + "; ".join(parts) + ".") if parts else "No filter could be set from your sentence."


def sentence_gaps(text: str, view: str, filters: dict) -> tuple[list[str], str | None]:
    """What the sentence asks for that no filter holds: amounts, sectors, sort orders. Plus the fixed line when it
    asks to rank, score or predict. Read from the sentence itself, so nothing unasked shows up here."""
    out = []
    if not any(k in filters for k in AMOUNT_KEYS[view]):
        out += [f"amount ({m.group(0).strip()})" for m in AMOUNT.finditer(text)]
    out += [f"sector ({m.group(1)}): Recount has no sector data" for m in SECTOR_RX.finditer(text)]
    ranks = bool(RANK_WORDS.search(text))
    if not ranks:
        out += [f"sort ({m.group(0).strip()}): sort with the column headers" for m in SORT_WORDS.finditer(text)]
    return list(dict.fromkeys(out)), NO_RANKING if ranks else None


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
    about_founders = bool(FOUNDER_WORDS.search(text))
    # founder tags the model adds unasked are noise, not something the sentence asked for
    unmatched = [DROPPED_LABEL.get(k, k.replace("_", " ")) for k in out.get("dropped") or []
                 if not (k == "tags" and (t == "funds" or not about_founders))]
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
        if val == "no" and NEGATION.search(text):  # a "no" the sentence did not say is the model's guess
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
            ui["co_investor"] = [xs.no_dash(f["co_invested_with"])]
        return {"view": "funds", "filters": ui, "unmatched": unmatched}
    if t == "companies":
        if f.get("last_from"):
            ui["last_round_after"] = f"{f['last_from'][:4]}-01"
        if _range(f.get("amount_min"), f.get("amount_max")):
            ui["last_amount"] = _range(f.get("amount_min") or None, f.get("amount_max"))
        if _range(f.get("months_since_min"), f.get("months_since_max")):
            ui["months_since"] = _range(f.get("months_since_min"), f.get("months_since_max"))
        if f.get("investor"):
            ui["investor"] = [xs.no_dash(f["investor"])]
        if f.get("lead"):
            ui["lead"] = [xs.no_dash(f["lead"])]
        if f.get("tags") and about_founders:
            ui["founder_tags"] = [TAG_LABELS[x] for x in f["tags"]]
        if f.get("repeat_founder") == "yes" and about_founders:
            ui["repeat"] = True
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
    out = xa.ai_filters(xa.AiFilters(text=body.text, role=body.role, view=VIEW_TARGET[body.view]), request)
    res = to_ui(out, views()["meta"]["countries"], body.text)
    gaps, refusal = sentence_gaps(body.text, res["view"], res["filters"])
    engine = f"Gemini ({out['model']})" if out["via"] == "gemini" else "Keyword rules"
    return {**res, "unmatched": list(dict.fromkeys(res["unmatched"] + gaps)), "refusal": refusal,
            "explanation": explain(res["view"], res["filters"]), "engine": engine, "notice": out.get("notice"),
            "filled_by_keywords": out.get("filled_by_keywords") or []}
