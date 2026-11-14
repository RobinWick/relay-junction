"""Build the JSON fixtures the Explore UI (app/static/explore.html) reads while the /api/explore/* endpoints are built.

Funds and companies are counted from the real Cala snapshot (cala/data/snapshot.json). Founders are SAMPLE
profiles: invented people at invented companies, marked sample in every record, because the career data
(Cala WORKS_AT / FOUNDED edges) is not fetched yet. Replace them with the API, never with real names.

Each output file has the exact shape the matching endpoint must return (see app/static/explore-fixtures/API.md),
so the UI does not change when the flag flips from fixtures to the API.

Usage: python3 pipeline/build_explore_fixtures.py
"""
from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
SNAPSHOT = HERE.parent.parent / "cala" / "data" / "snapshot.json"
OUT = HERE.parent / "app" / "static" / "explore-fixtures"

DOWNTURN = (2022, 2023)
MAX_PARTICIPANTS = 8
RECENT_FUND_ROUNDS = 30
STAGE_ORDER = ["pre-seed", "seed", "series a", "series b", "series c", "series d", "series e", "series f", "growth"]
COUNTRY_ALIASES = {"USA": "United States", "US": "United States", "UK": "United Kingdom",
                   "UAE": "United Arab Emirates", "—": None, "-": None, "Europe": None, "Unknown": None,
                   "Not disclosed": None, "Undisclosed": None, "Not confirmed": None, "Latin America": None}

# The only acquisition receipt verified end to end in Cala so far (research/patterns/probe/p03, p05):
# Zettle has an incoming INVESTED_IN edge from Northzone; PayPal completed the acquisition on 2018-09-20.
VERIFIED_EXITS = {
    "northzone": [{
        "company": "Zettle (iZettle)", "event_type": "MNA_COMPLETED", "role": "TARGET",
        "date": "2018-09-20", "year": 2018, "acquirers": [{"name": "PayPal"}],
        "value": {"status": "disclosed", "display": "2.2B USD", "label": "deal value, not return"},
        "sources": [{"name": "PayPal Completes Acquisition of iZettle",
                     "url": "https://newsroom.paypal-corp.com/2018-09-20-PayPal-Completes-Acquisition-of-iZettle",
                     "date": "2018-09-20"}],
    }],
}


def country(raw: str | None) -> str | None:
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


def build_funds(rounds: list[dict], names: dict, fund_keys: list[str], asof: date, src: dict):
    per: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for r in rounds:
        if r.get("disputed"):
            continue
        lead_known = bool(r["leads"]) and not r.get("not_led")
        for k in set(r["leads"]) | set(r["participants"]):
            if k not in fund_keys:
                continue
            if not lead_known:
                role = "unknown"
            elif k in r["leads"]:
                role = "led"
            else:
                role = "joined"
            per[k].append((role, r))

    items, details = [], {}
    for k in fund_keys:
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
        down_known = sum(1 for _, r in rows if DOWNTURN[0] <= r["year"] <= DOWNTURN[1] and _ != "unknown")
        co = Counter()
        for _, r in rows:
            co.update(x for x in set(r["leads"]) | set(r["participants"]) if x != k)
        countries = Counter(country(r["country"]) for _, r in rows if r["country"])
        stages_led = Counter(r["stage"] for r in led if r["stage"])
        stages_all = Counter(r["stage"] for _, r in rows if r["stage"])
        exits = VERIFIED_EXITS.get(k, [])
        item = {
            "key": k, "name": names.get(k, k),
            "rounds": len(rows), "led": len(led), "joined": len(joined), "lead_unknown": len(unknown),
            "lead_share": round(len(led) / known, 3) if known else None, "lead_known": known,
            "median_led_round_eur_m": round(statistics.median(led_amounts), 1) if led_amounts else None,
            "last_lead": ym(last_led) if last_led else None,
            "months_since_last_lead": months_between(date(last_led["year"], last_led.get("month") or 1, 1), asof)
            if last_led else None,
            "downturn_led": down_led, "downturn_lead_known": down_known,
            "exit_receipts": len(exits),
            "countries": dict(countries.most_common()),
            "stages_led": dict(stages_led), "stages": dict(stages_all),
            "co_investors": [{"key": x, "name": names.get(x, x), "shared_rounds": n} for x, n in co.most_common(8)],
        }
        items.append(item)
        pace = defaultdict(lambda: {"led": 0, "joined": 0, "unknown": 0})
        for role, r in rows:
            pace[r["year"]][role] += 1
        years = range(min(pace), max(pace) + 1)
        details[k] = {
            **item,
            "pace": [{"year": y, **pace[y]} for y in years],
            "recent_rounds": [dict(round_view(r, names), role=role)
                              for role, r in sorted(rows, key=lambda x: -x[1]["t"])[:RECENT_FUND_ROUNDS]],
            "exits": exits,
            "exits_caveat": "Acquisitions Cala has on file for companies this fund backed. A deal counts if it "
                            "closed at least 6 years ago, or a source dates the investment 6 or more years before "
                            "the deal. Deal value is the total price, not the fund's return. "
                            "No exit found in Cala does not mean no exit.",
            "source": src,
        }
    items.sort(key=lambda f: f["name"].lower())
    return items, details


def build_companies(rounds: list[dict], names: dict, asof: date, src: dict):
    by: dict[str, list[dict]] = defaultdict(list)
    for r in rounds:
        if not r.get("disputed"):
            by[r["ckey"]].append(r)
    items, details = [], {}
    for ck, rs in by.items():
        rs.sort(key=lambda r: r["t"])
        last = rs[-1]
        investors = Counter()
        for r in rs:
            investors.update(set(r["leads"]) | set(r["participants"]))
        amounts = [r["amount_eur_m"] for r in rs if r["amount_eur_m"]]
        last_stage = next((r["stage"] for r in reversed(rs) if r["stage"]), None)
        item = {
            "key": ck, "name": last["company"], "country": country(last["country"]),
            "rounds": len(rs), "last_round": ym(last), "last_stage": last_stage,
            "months_since_last_round": months_between(date(last["year"], last.get("month") or 1, 1), asof),
            "total_known_eur_m": round(sum(amounts), 1) if amounts else None,
            "investors": [{"key": k, "name": names.get(k, k)} for k, _ in investors.most_common(12)],
            "last_leads": [{"key": k, "name": names.get(k, k)} for k in last["leads"]] if not last.get("not_led") else [],
        }
        items.append(item)
        details[ck] = {**item, "timeline": [round_view(r, names) for r in rs], "source": src}
    items.sort(key=lambda c: c["last_round"], reverse=True)
    return items, details


# ---------- sample founders (invented) ----------
LEVELS = {1: "Individual contributor", 2: "Senior", 3: "Lead or manager", 4: "Head or director",
          5: "VP", 6: "C-level or founder"}

SAMPLE_PEOPLE = [
    ("s01", "Aino Sample", "Finland", "Northwind Robotics", "seed", [
        ("Harbor Pike Consulting", "Strategy consulting", "Business Analyst", 1, "2014-09", "2015-10"),
        ("Harbor Pike Consulting", "Strategy consulting", "Associate", 2, "2015-10", "2016-11"),
        ("Harbor Pike Consulting", "Strategy consulting", "Engagement Manager", 3, "2016-11", "2018-03"),
        ("Fennic Logistics", "Scale-up", "Head of Operations", 4, "2018-04", "2020-06"),
        ("Northwind Robotics", "Own company", "Co-founder and CEO", 6, "2020-08", None)],
     [("Northwind Robotics", "2020-08", "active", None)]),
    ("s02", "Jonas Example", "Sweden", "Lumen Ledger", "series a", [
        ("Bright Bank", "Finance", "Analyst", 1, "2011-06", "2014-08"),
        ("Bright Bank", "Finance", "Senior Analyst", 2, "2014-08", "2017-12"),
        ("Paystream", "Scale-up", "Product Lead", 3, "2018-01", "2019-12"),
        ("Lumen Ledger", "Own company", "Founder and CEO", 6, "2020-02", None)],
     [("Lumen Ledger", "2020-02", "active", None)]),
    ("s03", "Mira Placeholder", "Germany", "Cobalt Grid", "series b", [
        ("Tensor Labs", "Big tech", "Software Engineer", 1, "2012-01", "2013-02"),
        ("Tensor Labs", "Big tech", "Senior Software Engineer", 2, "2013-02", "2014-01"),
        ("Tensor Labs", "Big tech", "Engineering Manager", 3, "2014-01", "2015-06"),
        ("Gridlet", "Own company", "Co-founder and CTO", 6, "2015-07", "2018-09"),
        ("Cobalt Grid", "Own company", "Co-founder and CEO", 6, "2019-01", None)],
     [("Gridlet", "2015-07", "acquired", "Sample Energy Group"), ("Cobalt Grid", "2019-01", "active", None)]),
    ("s04", "Eero Demo", "Finland", "Saunalabs AI", "pre-seed", [
        ("Aalto Research Lab", "Research", "Doctoral Researcher", 1, "2016-09", "2021-05"),
        ("Aalto Research Lab", "Research", "Postdoctoral Researcher", 2, "2021-05", "2023-08"),
        ("Saunalabs AI", "Own company", "Co-founder and CTO", 6, "2023-09", None)],
     [("Saunalabs AI", "2023-09", "active", None)]),
    ("s05", "Clara Fixture", "Spain", "Verde Pay", "seed", [
        ("Atlas Partners", "Strategy consulting", "Consultant", 1, "2015-09", "2016-08"),
        ("Atlas Partners", "Strategy consulting", "Senior Consultant", 2, "2016-08", "2017-07"),
        ("Rapido Delivery", "Scale-up", "Expansion Manager", 3, "2017-08", "2018-07"),
        ("Rapido Delivery", "Scale-up", "Head of Southern Europe", 4, "2018-07", "2019-09"),
        ("Rapido Delivery", "Scale-up", "VP Operations", 5, "2019-09", "2021-02"),
        ("Verde Pay", "Own company", "Founder and CEO", 6, "2021-04", None)],
     [("Verde Pay", "2021-04", "active", None)]),
    ("s06", "Lars Mockberg", "Denmark", "Fjord Health", "series a", [
        ("Nordic Pharma", "Corporate", "Medical Advisor", 2, "2009-03", "2014-05"),
        ("Nordic Pharma", "Corporate", "Director, Medical Affairs", 4, "2014-05", "2019-10"),
        ("Fjord Health", "Own company", "Co-founder and CEO", 6, "2019-11", None)],
     [("Fjord Health", "2019-11", "active", None)]),
    ("s07", "Sofia Testdata", "Sweden", "Kelp Materials", "seed", [
        ("Volta Motors", "Scale-up", "Battery Engineer", 1, "2016-02", "2017-01"),
        ("Volta Motors", "Scale-up", "Senior Engineer", 2, "2017-01", "2017-11"),
        ("Volta Motors", "Scale-up", "Team Lead, Cells", 3, "2017-11", "2018-10"),
        ("Volta Motors", "Scale-up", "Head of Cell R&D", 4, "2018-10", "2021-03"),
        ("Kelp Materials", "Own company", "Founder and CEO", 6, "2021-05", None)],
     [("Kelp Materials", "2021-05", "active", None)]),
    ("s08", "Tomas Sampleman", "Germany", "Quanta Freight", "series b", [
        ("Harbor Pike Consulting", "Strategy consulting", "Associate", 2, "2010-09", "2012-08"),
        ("Cargo One", "Own company", "Co-founder and COO", 6, "2012-09", "2016-12"),
        ("Bright Bank", "Finance", "Director, Venture Partnerships", 4, "2017-01", "2018-06"),
        ("Quanta Freight", "Own company", "Co-founder and CEO", 6, "2018-07", None)],
     [("Cargo One", "2012-09", "acquired", "Sample Logistics AG"), ("Quanta Freight", "2018-07", "active", None)]),
    ("s09", "Noor Example", "United Kingdom", "Patchwork Security", "series a", [
        ("Tensor Labs", "Big tech", "Security Engineer", 1, "2013-09", "2016-04"),
        ("Tensor Labs", "Big tech", "Senior Security Engineer", 2, "2016-04", "2019-02"),
        ("Tensor Labs", "Big tech", "Staff Security Engineer", 3, "2019-02", "2021-01"),
        ("Patchwork Security", "Own company", "Co-founder and CEO", 6, "2021-03", None)],
     [("Patchwork Security", "2021-03", "active", None)]),
    ("s10", "Pekka Fixturinen", "Finland", "Kide Games", "seed", [
        ("Arctic Games", "Scale-up", "Game Designer", 1, "2015-01", "2016-03"),
        ("Arctic Games", "Scale-up", "Lead Designer", 3, "2016-03", "2018-06"),
        ("Pine Studio", "Own company", "Co-founder", 6, "2018-07", "2020-02"),
        ("Arctic Games", "Scale-up", "Game Lead", 4, "2020-03", "2022-09"),
        ("Kide Games", "Own company", "Co-founder and CEO", 6, "2022-10", None)],
     [("Pine Studio", "2018-07", "closed", None), ("Kide Games", "2022-10", "active", None)]),
    ("s11", "Ines Mockado", "France", "Atelier Data", "pre-seed", [
        ("Atlas Partners", "Strategy consulting", "Consultant", 1, "2018-09", "2019-09"),
        ("Atlas Partners", "Strategy consulting", "Senior Consultant", 2, "2019-09", "2020-09"),
        ("Atlas Partners", "Strategy consulting", "Project Leader", 3, "2020-09", "2022-01"),
        ("Atelier Data", "Own company", "Founder and CEO", 6, "2022-03", None)],
     [("Atelier Data", "2022-03", "active", None)]),
    ("s12", "Ville Esimerkki", "Finland", "Routa Climate", "series a", [
        ("Nordic Utility", "Corporate", "Engineer", 1, "2008-08", "2012-12"),
        ("Nordic Utility", "Corporate", "Project Manager", 3, "2013-01", "2017-06"),
        ("Sun Array", "Own company", "Founder", 6, "2017-07", "2020-11"),
        ("Routa Climate", "Own company", "Co-founder and CEO", 6, "2021-01", None)],
     [("Sun Array", "2017-07", "acquired", "Sample Power Oyj"), ("Routa Climate", "2021-01", "active", None)]),
    ("s13", "Hanna Demodata", "Netherlands", "Tulip Health", "seed", [
        ("City Hospital", "Healthcare", "Physician", 2, "2012-08", "2018-07"),
        ("Carely", "Scale-up", "Medical Lead", 3, "2018-08", "2020-05"),
        ("Tulip Health", "Own company", "Co-founder and CMO", 6, "2020-06", None)],
     [("Tulip Health", "2020-06", "active", None)]),
    ("s14", "Oskar Platshallare", "Sweden", "Stack North", "series a", [
        ("Tensor Labs", "Big tech", "Product Manager", 2, "2014-06", "2015-05"),
        ("Tensor Labs", "Big tech", "Group Product Manager", 3, "2015-05", "2016-04"),
        ("Paystream", "Scale-up", "Director of Product", 4, "2016-05", "2017-06"),
        ("Paystream", "Scale-up", "VP Product", 5, "2017-06", "2019-08"),
        ("Stack North", "Own company", "Founder and CEO", 6, "2019-09", None)],
     [("Stack North", "2019-09", "active", None)]),
]


def parse_ym(s: str) -> date:
    y, m = s.split("-")
    return date(int(y), int(m), 1)


def person_record(p: tuple, asof: date) -> dict:
    pid, name, ctry, company, stage, roles_raw, founded_raw = p
    roles = []
    for org, org_type, title, level, start, end in roles_raw:
        s = parse_ym(start)
        e = parse_ym(end) if end else asof
        roles.append({"org": org, "org_type": org_type, "title": title, "level": level,
                      "level_label": LEVELS[level], "start": start, "end": end,
                      "months": months_between(s, e), "current": end is None})
    # tenure per employer: consecutive roles at one org form one stint
    stints: list[dict] = []
    for r in roles:
        if stints and stints[-1]["org"] == r["org"] and stints[-1]["end"] == r["start"]:
            stints[-1]["end"] = r["end"]
            stints[-1]["months"] += r["months"]
            stints[-1]["roles"] += 1
        else:
            stints.append({"org": r["org"], "org_type": r["org_type"], "start": r["start"], "end": r["end"],
                           "months": r["months"], "roles": 1})
    closed = [s["months"] for s in stints if s["end"]]
    steps = [(a, b) for a, b in zip(roles, roles[1:]) if b["level"] > a["level"] and b["org_type"] != "Own company"]
    first_start = parse_ym(roles[0]["start"])
    pre_founding = [r for r in roles if r["org_type"] != "Own company"]
    if steps:
        reach = parse_ym(steps[-1][1]["start"])
        months_per_step = round(months_between(first_start, reach) / len(steps), 1)
    else:
        months_per_step = None
    head = next((r for r in pre_founding if r["level"] >= 4), None)
    founded = [{"company": c, "start": s, "status": st, "acquirer": acq} for c, s, st, acq in founded_raw]
    tags = sorted({r["org_type"] for r in pre_founding})
    if len(founded) >= 2:
        tags.append("Repeat founder")
    if any(f["status"] == "acquired" for f in founded[:-1]):
        tags.append("Prior exit")
    internal = sum(1 for a, b in steps if a["org"] == b["org"])
    return {
        "id": pid, "name": name, "sample": True, "country": ctry,
        "company": company, "company_stage": stage,
        "career_start": roles[0]["start"],
        "roles": roles, "stints": stints, "founded": founded,
        "metrics": {
            "employers": len({s["org"] for s in stints if s["org_type"] != "Own company"}),
            "roles": len(roles),
            "median_tenure_months": statistics.median(closed) if closed else None,
            "shortest_tenure_months": min(closed) if closed else None,
            "title_steps": len(steps),
            "internal_title_steps": internal,
            "months_per_title_step": months_per_step,
            "months_to_head_level": months_between(first_start, parse_ym(head["start"])) if head else None,
            "companies_founded": len(founded),
            "repeat_founder": len(founded) >= 2,
            "prior_exit": any(f["status"] == "acquired" for f in founded[:-1]),
        },
        "tags": tags,
        "source": {"name": "Sample profile, invented for the UI", "retrieved": asof.isoformat(),
                   "note": "Not a real person. Live profiles come from Cala WORKS_AT and FOUNDED edges."},
    }


def build_meta(funds, companies, people, src):
    countries = Counter(c["country"] for c in companies if c["country"])
    return {
        "source": src,
        "counts": {"funds": len(funds), "companies": len(companies), "founders": len(people)},
        "countries": [c for c, _ in countries.most_common()],
        "stages": STAGE_ORDER,
        "founder_tags": sorted({t for p in people for t in p["tags"]}),
        "investors": sorted({i["name"] for c in companies for i in c["investors"]})[:4000],
        "levels": LEVELS,
    }


def write(name: str, data) -> None:
    path = OUT / name
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    print(f"{name}: {path.stat().st_size // 1024} KB")


def main() -> None:
    snap = json.loads(SNAPSHOT.read_text())
    asof = date.fromisoformat(snap["retrieved"])
    names = snap["investor_names"]
    src = source_block(snap["retrieved"])
    OUT.mkdir(parents=True, exist_ok=True)
    funds, fund_details = build_funds(snap["rounds"], names, snap["fund_keys"], asof, src)
    companies, company_details = build_companies(snap["rounds"], names, asof, src)
    people = [person_record(p, asof) for p in SAMPLE_PEOPLE]
    write("meta.json", build_meta(funds, companies, people, src))
    write("funds.json", {"items": funds, "source": src})
    write("fund-details.json", fund_details)
    write("companies.json", {"items": companies, "source": src})
    write("company-details.json", company_details)
    write("founders.json", {"items": [{k: v for k, v in p.items() if k not in ("roles", "stints")} for p in people],
                            "source": people[0]["source"]})
    write("founder-details.json", {p["id"]: p for p in people})


if __name__ == "__main__":
    main()
