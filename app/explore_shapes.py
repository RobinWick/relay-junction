"""Response shapes for the Explore page (static/explore.html), built from the Cala snapshot and people.json.

Pure functions, no web framework; explore_views.py serves them live. The contract is docs/explore-api.md.

People rules: career data is shown as facts, timelines and filterable metrics with neutral labels. Nothing here
scores, ranks or predicts a person, and every person carries its source and fetch date.
"""
from __future__ import annotations

import re
import statistics
from collections import Counter, defaultdict
from datetime import date
from typing import Optional

DOWNTURN = (2022, 2023)
MAX_PARTICIPANTS = 8
RECENT_FUND_ROUNDS = 30
STAGE_ORDER = ["pre-seed", "seed", "series a", "series b", "series c", "series d", "series e", "series f", "growth"]
COUNTRY_ALIASES = {"USA": "United States", "US": "United States", "UK": "United Kingdom",
                   "UAE": "United Arab Emirates", "—": None, "-": None, "Europe": None, "Unknown": None,
                   "Not disclosed": None, "Undisclosed": None, "Not confirmed": None, "Latin America": None}
EXITS_CAVEAT = ("Acquisitions Cala has on file for companies this fund backed. A deal counts if it closed at least 6 "
                "years ago, or a source dates the investment 6 or more years before the deal. Deal value is the total "
                "price, not the fund's return. No exit found in Cala does not mean no exit.")
COHORT_RELATION = {"worked_at_stated": "Text says a founder worked there", "funded_by": "Employer invested in it",
                   "sold_to": "Sold to the employer", "listed_only": "Listed by Cala, no tie stated"}
BORN = re.compile(r",?\s*born (in )?\d{4}", re.I)  # age must never become a filter or a label
DASH_RANGE = re.compile(r"(\d)\s*[\u2012-\u2015]\s*(\d)")
DASH = re.compile(r"\s*[\u2012-\u2015]\s*")


def no_dash(text):
    """Cala's own text carries en and em dashes ('McKinsey Bangkok 2014\u201317'); the page shows none."""
    if not isinstance(text, str):
        return text
    return DASH.sub(", ", DASH_RANGE.sub(r"\1 to \2", text)).strip(", ")


def country(raw: Optional[str]) -> Optional[str]:
    """'Sweden (Stockholm)' -> 'Sweden'; 'UK / Israel' -> 'United Kingdom' (first named); vague -> None."""
    if not raw:
        return None
    base = raw.split(" (")[0].split("/")[0].strip()
    return COUNTRY_ALIASES.get(base, base) or None


def ym(r: dict) -> str:
    return f"{r['year']}-{(r.get('month') or 1):02d}"


def months_between(a: date, b: date) -> int:
    return (b.year - a.year) * 12 + (b.month - a.month)


def source_block(retrieved: str) -> dict:
    return {"name": "Cala round data", "retrieved": retrieved,
            "note": "Leads are missing for about a third of rounds. Counted, not predicted."}


def round_view(r: dict, names: dict) -> dict:
    lead_known = bool(r["leads"]) and not r.get("not_led")
    return {
        "id": r["id"], "company": r["company"], "ckey": r["ckey"], "country": country(r["country"]),
        "date": ym(r), "year": r["year"], "stage": r["stage"], "type": r["type"],
        "amount_eur_m": r["amount_eur_m"],
        "leads": [{"key": k, "name": names.get(k, k)} for k in r["leads"]] if lead_known else [],
        "participants": [{"key": k, "name": names.get(k, k)} for k in r["participants"][:MAX_PARTICIPANTS]],
        "participants_total": len(r["participants"]),
        "lead_known": lead_known,
        "source_path": r["query_path"],
    }


# ---------- funds ----------
def build_funds(rounds: list[dict], names: dict, fund_keys, asof: date, src: dict,
                exits: Optional[dict] = None, exits_caveat: str = EXITS_CAVEAT):
    """exits: {fund_key: [receipt]} in the receipt_exits.py shape (app/exits.json)."""
    exits = exits or {}
    per: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for r in rounds:
        if r.get("disputed"):
            continue
        lead_known = bool(r["leads"]) and not r.get("not_led")
        for k in set(r["leads"]) | set(r["participants"]):
            if k not in fund_keys:
                continue
            role = "unknown" if not lead_known else "led" if k in r["leads"] else "joined"
            per[k].append((role, r))

    items, details = [], {}
    for k in sorted(fund_keys):
        rows = per.get(k, [])
        if not rows:
            continue
        led = [r for role, r in rows if role == "led"]
        joined = [r for role, r in rows if role == "joined"]
        unknown = [r for role, r in rows if role == "unknown"]
        known = len(led) + len(joined)
        led_amounts = [r["amount_eur_m"] for r in led if r["amount_eur_m"]]
        last_led = max(led, key=lambda r: r["t"]) if led else None
        down_led = sum(1 for r in led if DOWNTURN[0] <= r["year"] <= DOWNTURN[1])
        down_known = sum(1 for role, r in rows if DOWNTURN[0] <= r["year"] <= DOWNTURN[1] and role != "unknown")
        co = Counter()
        for _, r in rows:
            co.update(x for x in set(r["leads"]) | set(r["participants"]) if x != k)
        countries = Counter(country(r["country"]) for _, r in rows if r["country"])
        countries.pop(None, None)
        receipts = exits.get(k) or []
        item = {
            "key": k, "name": names.get(k, k),
            "rounds": len(rows), "led": len(led), "joined": len(joined), "lead_unknown": len(unknown),
            "lead_share": round(len(led) / known, 3) if known else None, "lead_known": known,
            "median_led_round_eur_m": round(statistics.median(led_amounts), 1) if led_amounts else None,
            "last_lead": ym(last_led) if last_led else None,
            "months_since_last_lead": months_between(date(last_led["year"], last_led.get("month") or 1, 1), asof)
            if last_led else None,
            "downturn_led": down_led, "downturn_lead_known": down_known,
            "exit_receipts": len(receipts),
            "countries": dict(countries.most_common()),
            "stages_led": dict(Counter(r["stage"] for r in led if r["stage"])),
            "stages": dict(Counter(r["stage"] for _, r in rows if r["stage"])),
            "co_investors": [{"key": x, "name": names.get(x, x), "shared_rounds": n} for x, n in co.most_common(8)],
        }
        items.append(item)
        pace = defaultdict(lambda: {"led": 0, "joined": 0, "unknown": 0})
        for role, r in rows:
            pace[r["year"]][role] += 1
        details[k] = {
            **item,
            "pace": [{"year": y, **pace[y]} for y in range(min(pace), max(pace) + 1)],
            "recent_rounds": [dict(round_view(r, names), role=role)
                              for role, r in sorted(rows, key=lambda x: -x[1]["t"])[:RECENT_FUND_ROUNDS]],
            "exits": receipts, "exits_caveat": exits_caveat, "source": src,
        }
    items.sort(key=lambda f: f["name"].lower())
    return items, details


# ---------- companies ----------
def build_companies(rounds: list[dict], names: dict, asof: date, src: dict, people_by_company: Optional[dict] = None):
    """people_by_company: {ckey: [founder list item]} so a company row can carry its founders' background facts."""
    people_by_company = people_by_company or {}
    by: dict[str, list[dict]] = defaultdict(list)
    for r in rounds:
        if not r.get("disputed"):
            by[r["ckey"]].append(r)
    items, details = [], {}
    for ck, rs in by.items():
        rs.sort(key=lambda r: r["t"])
        last = rs[-1]
        investors, leads = Counter(), Counter()
        for r in rs:
            investors.update(set(r["leads"]) | set(r["participants"]))
            if not r.get("not_led"):
                leads.update(r["leads"])
        amounts = [r["amount_eur_m"] for r in rs if r["amount_eur_m"]]
        founders = people_by_company.get(ck, [])
        item = {
            "key": ck, "name": last["company"], "country": country(last["country"]),
            "rounds": len(rs), "last_round": ym(last),
            "last_stage": next((r["stage"] for r in reversed(rs) if r["stage"]), None),
            "last_amount_eur_m": last["amount_eur_m"],
            "months_since_last_round": months_between(date(last["year"], last.get("month") or 1, 1), asof),
            "total_known_eur_m": round(sum(amounts), 1) if amounts else None,
            # every investor and lead: the page filters on these lists, so a cap would hide real matches
            "investors": [{"key": k, "name": names.get(k, k)} for k, _ in investors.most_common()],
            "leads": [{"key": k, "name": names.get(k, k)} for k, _ in leads.most_common()],
            "last_leads": [{"key": k, "name": names.get(k, k)} for k in last["leads"]] if not last.get("not_led") else [],
            "founders": [{"id": p["id"], "name": p["name"]} for p in founders],
            "founder_tags": sorted({t for p in founders for t in p["tags"]}),
            "repeat_founder": any(p["metrics"]["repeat_founder"] for p in founders),
        }
        items.append(item)
        details[ck] = {**item, "timeline": [round_view(r, names) for r in rs], "source": src}
    items.sort(key=lambda c: c["last_round"], reverse=True)
    return items, details


# ---------- founders (people.json records from people.py, mapped for the page) ----------
def _ym(d: Optional[str]) -> Optional[str]:
    return d[:7] if d and re.match(r"^\d{4}-\d{2}", d) else None


def _months(a: str, b: str) -> int:
    return months_between(date(int(a[:4]), int(a[5:7]), 1), date(int(b[:4]), int(b[5:7]), 1))


def person_view(p: dict, home: Optional[dict], tag_labels: dict, org_key, asof: date,
                merge_roles=lambda rows: rows) -> dict:
    """One people.py record -> the page's Person. org_key and merge_roles are people.py's (they merge Cala's
    duplicate entities), so the page shows exactly the rows people.py counted in its metrics and gaps."""
    home_name = (home or {}).get("name") or ""
    home_keys = {org_key(home_name)}
    dated, undated = [], []
    for r in merge_roles(p.get("roles") or []):
        own = org_key(r.get("org") or "") in home_keys
        tags = [tag_labels[t] for t in r.get("tags") or [] if t in tag_labels and not own]
        start, end = _ym(r.get("since")), _ym(r.get("until"))
        view = {"org": no_dash(r.get("org")) or "Organisation not named", "org_type": "Own company" if own else
                (tags[0] if tags else "Employer"), "title": no_dash(r.get("role")) or "Title not stated",
                "level": r.get("level"), "level_label": r.get("level_label") or "Not mapped",
                "start": start, "end": end, "current": bool(r.get("open")),
                "sources": [{"name": no_dash(s.get("name") or s.get("url")), "url": s.get("url"), "date": s.get("date")}
                            for s in (r.get("sources") or [])[:3] if s.get("url")]}
        if start:
            view["months"] = _months(start, end or asof.isoformat()[:7])
            dated.append(view)
        else:
            undated.append(view)
    dated.sort(key=lambda r: r["start"])
    shown = dated + undated
    m = p.get("metrics") or {}
    prior = p.get("prior_founder") or {}
    prior_cos = [c.get("org") for c in prior.get("companies") or [] if c.get("org")]
    exits = [e for e in p.get("prior_exits") or []]
    rounds = (home or {}).get("rounds") or []
    tags = [tag_labels[t] for t in p.get("tags") or [] if t in tag_labels]
    src = p.get("source") or {}
    return {
        "id": p["id"], "name": p["name"], "sample": False,
        "country": country((home or {}).get("country")) or "Not stated",
        "company": home_name or "Company not named", "company_key": (home or {}).get("ckey"),
        "company_stage": rounds[-1].get("stage") if rounds else None,
        "description": no_dash(BORN.sub("", p.get("description") or "").strip()) or None,
        "linkedin_url": p.get("linkedin_url"),
        "career_start": _ym(m.get("career_start")),
        "roles": dated, "undated_roles": undated,
        "level_steps": p.get("level_steps") or [],
        "founded": [{"company": home_name, "how": "The company we found this person through", "exit": None}]
        + [{"company": c, "how": "Founded earlier (Cala FOUNDED edge)",
            "exit": "Acquisition on file in Cala" if c in {e.get("org") for e in exits}
            else "Checked: no acquisition in Cala, which is not proof there was none"
            if c in (p.get("prior_exit_checked") or []) else "Not checked"} for c in prior_cos],
        "metrics": {
            # counted over the rows the page shows, so roles, outside roles and the gaps text agree
            "employers": m.get("employers"), "roles": len(shown), "roles_dated": len(dated),
            "roles_outside_company": sum(1 for r in shown if r["org_type"] != "Own company"),
            "avg_tenure_years": m.get("avg_tenure_years"), "avg_tenure_n": m.get("avg_tenure_n"),
            "shortest_tenure_years": m.get("shortest_tenure_years"),
            "longest_tenure_years": m.get("longest_tenure_years"),
            "level_ups": m.get("level_ups"), "level_ups_per_year": m.get("level_ups_per_year"),
            "years_before_company": m.get("years_before_company"),
            "companies_founded": 1 + len(prior_cos), "repeat_founder": bool(prior.get("value")),
            "prior_exit": bool(exits),
        },
        "tags": tags + (["Repeat founder"] if prior.get("value") else []),
        "tag_evidence": {tag_labels[k]: v for k, v in (p.get("tag_evidence") or {}).items() if k in tag_labels},
        "gaps": [no_dash(g) for g in p.get("gaps") or []],
        "source": {"name": src.get("provider") or "Cala entity graph", "retrieved": src.get("fetched") or "",
                   "entity_id": src.get("entity_id") or p["id"],
                   "note": src.get("note") or "Career edges as Cala holds them."},
    }


def build_founders(people_json: dict, tag_labels: dict, org_key, asof: date,
                   merge_roles=lambda rows: rows) -> tuple[list[dict], dict]:
    homes = {c["ckey"]: c for c in people_json.get("companies") or [] if c.get("ckey")}
    people = []
    for p in people_json.get("people") or []:
        if not (p.get("id") and p.get("name")):
            continue
        home = next((homes[c] for c in p.get("companies") or [] if c in homes), None)
        people.append(person_view(p, home, tag_labels, org_key, asof, merge_roles))
    people.sort(key=lambda x: (x["company"].lower(), x["name"].lower()))
    return people, {p["id"]: p for p in people}


def founder_item(p: dict) -> dict:
    return {k: v for k, v in p.items() if k not in ("roles", "undated_roles", "level_steps", "tag_evidence")}


def cohort_views(people_json: dict, company_keys: set) -> list[dict]:
    """Background cohorts: companies Cala lists for 'founder previously worked at X'. Claims, with no source URLs."""
    out = []
    for c in people_json.get("cohorts") or []:
        rows = []
        for r in c.get("rows") or []:
            ck = re.sub(r"[^a-z0-9]", "", (r.get("company") or "").lower())
            rows.append({"company": no_dash(r.get("company")), "founded": r.get("founded"),
                         "founders": no_dash(r.get("founders")),
                         "about": no_dash(r.get("about")), "location": no_dash(r.get("location")),
                         "relation": r.get("relation"), "relation_label": COHORT_RELATION.get(r.get("relation"), ""),
                         "evidence": no_dash(r.get("evidence") or ""),
                         "ckey": ck if r.get("in_snapshot") and ck in company_keys else None})
        out.append({"employer": c.get("employer"), "fetched": c.get("fetched"), "source": c.get("source"),
                    "n": c.get("n", len(rows)), "n_worked_at_stated": c.get("n_worked_at_stated", 0),
                    "n_in_snapshot": c.get("n_in_snapshot", 0), "gaps": c.get("gaps") or [], "rows": rows})
    return out


def people_coverage(people_json: dict) -> Optional[dict]:
    cov = people_json.get("coverage")
    if not cov:
        return None
    return {**cov, "source": (people_json.get("source") or {}).get("graph"), "generated": people_json.get("generated"),
            "rules": people_json.get("rules") or []}


def build_meta(funds: list, companies: list, people: list, src: dict, tag_labels: dict, levels: dict,
               coverage: Optional[dict] = None) -> dict:
    countries = Counter(c["country"] for c in companies if c["country"])
    return {
        "source": src,
        "counts": {"funds": len(funds), "companies": len(companies), "founders": len(people)},
        "countries": [c for c, _ in countries.most_common()],
        "stages": STAGE_ORDER,
        "founder_tags": sorted(tag_labels.values()),
        "investors": sorted({i["name"] for c in companies for i in c["investors"]})[:4000],
        "levels": levels,
        "people_coverage": coverage,
    }
