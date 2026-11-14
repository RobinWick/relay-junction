"""Who Bought This Fund's Companies: acquisition receipts for a fund, built from Cala's entity graph.

A receipt is one completed acquisition (Cala CorporateEvent, event_type MNA_COMPLETED) where a company the fund
invested in (Cala INVESTED_IN edge) took part as TARGET. Each receipt carries the buyer, the date, the deal
value as reported (or "undisclosed") and the source URLs Cala gives for the event and for the fund link.

Rules (research/patterns/DECISION.md #3 and exit-record-redteam.md):
- Receipts only. No rates, no counts of exits over portfolio size, no fund vs fund comparison, no ranking by value.
- Vintage gate: a receipt is shown only when the fund's investment is at least 6 years old, proven one of two ways:
  * the acquisition itself is at least 6 years ago (a fund that sold in the deal held its stake before it), or
  * a source naming the fund as investor is dated at least 6 years before the deal.
- The value is the total deal value, never the fund's return. Undisclosed values are their own unranked bucket.
- No exit found in Cala does not mean no exit.

build_fund() turns cached raw projections into one fund's record (used by pipeline/fetch_exits.py).
load() and for_fund() read the cached app/exits.json for the app.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

EXITS_PATH = Path(__file__).resolve().parent / "exits.json"
VINTAGE_YEARS = 6
VALUE_LABEL = "deal value, not return"
UNDISCLOSED = "undisclosed"
CAVEAT = ("Acquisitions Cala has on file for companies this fund backed. A deal counts if it closed at least 6 years "
          "ago, or a source dates the investment 6 or more years before the deal. Deal value is the total price, "
          "not the fund's return. No exit found in Cala does not mean no exit.")


def parse_day(raw: str | None) -> date | None:
    """'2018-09-20' -> date; '2018-09' and '2018' take the first day (the earliest the event can be)."""
    if not raw:
        return None
    parts = str(raw)[:10].split("-")
    try:
        y = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 1
        d = int(parts[2]) if len(parts) > 2 else 1
        return date(y, m, d)
    except (ValueError, IndexError):
        return None


def years_before(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year - years)
    except ValueError:  # 29 Feb
        return day.replace(year=day.year - years, day=28)


SCALES = (("billion", 1e9), ("million", 1e6), ("thousand", 1e3))


def normalize_value(amount: float, units: str | None) -> tuple[float, str | None]:
    """Cala reports units several ways: 'USD', 'USD_millions', 'USD million'. Returns (whole amount, currency).

    The currency is never converted: values in different currencies are never compared or summed.
    """
    text = (units or "").replace("_", " ").strip()
    words = text.split()
    currency = words[0].upper() if words else None
    scale = next((factor for word, factor in SCALES if word in text.lower()), 1.0)
    return float(amount) * scale, currency


def format_value(amount: float, units: str | None) -> str:
    """2200000000, 'USD' -> '2.2B USD'. The currency stays as reported."""
    for size, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if amount >= size:
            num = f"{amount / size:.1f}".rstrip("0").rstrip(".")
            return f"{num}{suffix} {units or ''}".strip()
    return f"{amount:g} {units or ''}".strip()


def _sources(items: list[dict] | None) -> list[dict]:
    out = []
    for s in items or []:
        url = s.get("document")
        if isinstance(url, dict):  # some sources are API lookups, not documents
            url = url.get("endpoint")
        if url:
            name = (s.get("name") or "").replace("\u2013", "-").replace("\u2014", "-") or None
            out.append({"name": name, "url": url, "date": s.get("date"), "rank": s.get("source_rank")})
    return out


def _dedupe(sources: list[dict]) -> list[dict]:
    seen, out = set(), []
    for s in sources:
        if s["url"] not in seen:
            seen.add(s["url"])
            out.append(s)
    return out


def _prop(entity: dict, name: str):
    p = (entity.get("properties") or {}).get(name)
    return p.get("value") if isinstance(p, dict) else p


def _prop_sources(entity: dict, *names: str) -> list[dict]:
    out = []
    for n in names:
        p = (entity.get("properties") or {}).get(n)
        if isinstance(p, dict):
            out += _sources(p.get("sources"))
    return out


def _edges(entity: dict | None, direction: str, rel: str) -> list[dict]:
    return (((entity or {}).get("relationships") or {}).get(direction) or {}).get(rel) or []


def fund_links(fund_entities: set[str], fund_raw: dict | None, company: dict) -> list[dict]:
    """Sources that say the fund invested in the company: the fund's outgoing edge or the company's incoming one."""
    links = []
    for e in _edges(fund_raw, "outgoing", "INVESTED_IN"):
        if e.get("id") == company.get("id"):
            links += _sources((e.get("properties") or {}).get("sources"))
    for e in _edges(company, "incoming", "INVESTED_IN"):
        if e.get("id") in fund_entities:
            links += _sources((e.get("properties") or {}).get("sources"))
    return _dedupe(links)


def target_events(company: dict) -> list[dict]:
    """The company's completed acquisitions where it was the TARGET (not its own purchases as ACQUIRER)."""
    return [e for e in _edges(company, "outgoing", "PARTICIPATES_IN_CORPORATE_EVENT")
            if e.get("name") == "MNA_COMPLETED" and (e.get("properties") or {}).get("role") == "TARGET"]


def vintage(event_day: date, links: list[dict], today: date) -> dict | None:
    """Proof that the fund's investment is at least 6 years old, or None when it cannot be shown."""
    if event_day <= years_before(today, VINTAGE_YEARS):
        return {"rule": "exit_at_least_6y_ago",
                "text": f"Acquired {event_day.year}, so the fund's stake is at least {VINTAGE_YEARS} years old."}
    dated = sorted(((parse_day(s.get("date")), s) for s in links if parse_day(s.get("date"))), key=lambda x: x[0])
    if dated and dated[0][0] <= years_before(event_day, VINTAGE_YEARS):
        day, src = dated[0]
        return {"rule": "investor_source_6y_before_exit",
                "text": f"A source naming the fund as investor is dated {day.isoformat()}, "
                        f"at least {VINTAGE_YEARS} years before the deal.", "source": src}
    return None


def build_receipt(fund_entities: set[str], fund_raw: dict | None, company: dict, edge: dict, event: dict | None,
                  today: date) -> tuple[dict | None, str | None]:
    """One receipt for one TARGET event, or (None, reason) when a rule keeps it out."""
    if event is None:
        return None, "deal details (value, buyer) not fetched from Cala"
    links = fund_links(fund_entities, fund_raw, company)
    if not links:
        return None, "no Cala source links the fund to this company"
    edge_props = edge.get("properties") or {}
    day = parse_day(_prop(event, "event_date")) or parse_day(edge_props.get("event_date"))
    if not day:
        return None, "deal date missing"
    founded = parse_day(_prop(company, "founding_date"))
    if founded and day < founded:
        return None, "deal dated before the company was founded"
    acquirers = []
    for p in _edges(event, "incoming", "PARTICIPATES_IN_CORPORATE_EVENT"):
        if (p.get("properties") or {}).get("role") == "ACQUIRER":
            acquirers.append({"name": p.get("name"), "entity": p.get("id")})
    if any(a["entity"] in fund_entities for a in acquirers):
        return None, "the fund itself is the buyer"
    gate = vintage(day, links, today)
    if not gate:
        return None, f"too recent for the {VINTAGE_YEARS} year gate"
    reported = _prop(event, "transaction_value")
    units = _prop(event, "transaction_value_units")
    if isinstance(reported, (int, float)) and reported > 0:
        amount, currency = normalize_value(reported, units)
        value = {"status": "disclosed", "amount": amount, "currency": currency,
                 "reported": {"value": reported, "units": units},
                 "display": format_value(amount, currency), "label": VALUE_LABEL}
    else:
        value = {"status": UNDISCLOSED, "display": UNDISCLOSED, "label": VALUE_LABEL}
    sources = _sources(edge_props.get("sources"))
    sources += _prop_sources(event, "event_date", "transaction_value", "event_type", "description")
    return {
        "company": company.get("name"),
        "company_entity": company.get("id"),
        "event_entity": edge.get("id"),
        "event_type": "MNA_COMPLETED",
        "role": "TARGET",
        "date": day.isoformat(),
        "year": day.year,
        "acquirers": acquirers,
        "acquirer_known": bool(acquirers),
        "value": value,
        "description": _prop(event, "description"),
        "vintage": gate,
        "sources": _dedupe(sources),
        "fund_link_sources": links,
    }, None


def build_fund(fund_key: str, name: str, fund_entity: str | list[str], fund_raw: dict | None, companies: list[dict],
               today: date, note: str | None = None) -> dict:
    """companies: [{"company": raw company projection, "events": [raw event projections]}].

    fund_entity may list several Cala ids for one fund (Cala has 'Creandum' and 'Creandum Fund' as two entities).
    """
    fund_entities = {fund_entity} if isinstance(fund_entity, str) else set(fund_entity)
    disclosed, undisclosed, excluded = [], [], []
    for item in companies:
        company = item.get("company")
        if not company:
            continue
        events = {e.get("id"): e for e in item.get("events") or []}
        found = target_events(company)
        if not found:
            excluded.append({"company": company.get("name"), "reason": "no completed acquisition as target in Cala"})
        for edge in found:
            receipt, reason = build_receipt(fund_entities, fund_raw, company, edge, events.get(edge.get("id")), today)
            if receipt is None:
                excluded.append({"company": company.get("name"), "reason": reason})
            elif receipt["value"]["status"] == UNDISCLOSED:
                undisclosed.append(receipt)
            else:
                disclosed.append(receipt)
    by_date = lambda r: r["date"]  # noqa: E731  newest first; never ranked by value
    portfolio = _edges(fund_raw, "outgoing", "INVESTED_IN")
    return {
        "fund_key": fund_key,
        "name": name,
        "fund_entities": sorted(fund_entities),
        "portfolio_edges_in_cala": len(portfolio) if fund_raw else None,
        "companies_checked": [c["company"].get("name") for c in companies if c.get("company")],
        "receipts": sorted(disclosed, key=by_date, reverse=True),
        "undisclosed": sorted(undisclosed, key=by_date, reverse=True),
        "excluded": excluded,
        "note": note,
        "caveat": CAVEAT,
    }


def load(path: Path = EXITS_PATH) -> dict:
    """The cached receipts file; an empty record when it has not been built (the app must not crash)."""
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {"version": 1, "funds": {}, "caveat": CAVEAT, "value_label": VALUE_LABEL}


def for_fund(data: dict, fund_key: str) -> dict | None:
    """One fund's receipts by our canon fund key ('lifeline', 'northzone'), or None when it was not fetched."""
    return (data.get("funds") or {}).get(fund_key)
