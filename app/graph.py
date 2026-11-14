"""Cross-check a round against Cala's entity graph (the entity endpoints Cala recommends for this challenge).

Per round:
1. POST /v1/entities/{company_id}: the company's outgoing PARTICIPATES_IN_FUNDING_ROUND edges (role ISSUER). When
   the id from the query answer has no rounds, GET /v1/entities?name=... finds the Company entity that does.
2. POST /v1/entities/{round_id} for the round with our stage label: label, amount, dates, and its incoming
   PARTICIPATES_IN_FUNDING_ROUND edges, where Cala marks lead investors with is_lead.

`post(path, body)` and `search(name)` are injected: the pipeline passes its cached client, the app a budgeted call.
"""
from __future__ import annotations

import re
from typing import Callable

from merge import canon, company_key, parse_date, stage_of

Post = Callable[[str, dict], dict]
Search = Callable[[str], list]
RANK_ORDER = {"FILING": 0, "PRIMARY": 1, "PRESS": 2, "AGGREGATOR": 3}
COMPANY_BODY = {"properties": ["name"],
                "relationships": {"outgoing": {"PARTICIPATES_IN_FUNDING_ROUND": {"limit": 60}}}}
ROUND_BODY = {"properties": ["round_label", "transaction_value", "transaction_value_units", "announcement_date",
                             "event_date", "instrument"],
              "relationships": {"incoming": {"PARTICIPATES_IN_FUNDING_ROUND": {"limit": 80}}}}


def _value(props: dict, name: str):
    v = props.get(name)
    return v.get("value") if isinstance(v, dict) else v


def _label_stage(label: str | None) -> str | None:
    """'SERIES_A' or 'Seed+' -> our stage key ('series a', 'seed')."""
    if not label:
        return None
    return stage_of(re.sub(r"[_+]", " ", str(label)).strip())


def _edge_year(edge: dict) -> float | None:
    """Earliest dated source on an edge, as a fractional year: the best hint of when a round happened."""
    ts = []
    for s in (edge.get("properties") or {}).get("sources") or []:
        d = parse_date(s.get("date"))
        if d:
            ts.append(d[0] + (d[1] - 1) / 12)
    return min(ts) if ts else None


def issuer_rounds(company: dict) -> list[dict]:
    edges = ((company.get("relationships") or {}).get("outgoing") or {}).get("PARTICIPATES_IN_FUNDING_ROUND") or []
    return [e for e in edges if (e.get("properties") or {}).get("role") in (None, "ISSUER")]


def pick_round(edges: list[dict], stage: str | None, t: float) -> dict | None:
    """The graph round with our stage label, closest in time. No stage match means not in the graph."""
    if not stage:
        return None
    same = [e for e in edges if _label_stage(e.get("name")) == stage]
    if not same:
        return None
    return min(same, key=lambda e: abs((_edge_year(e) if _edge_year(e) is not None else t + 5) - t))


def _sources(items: list[dict], limit: int = 4) -> list[dict]:
    seen, out = set(), []
    for s in sorted(items, key=lambda s: RANK_ORDER.get(s.get("source_rank"), 9)):
        url = s.get("document") or ""
        if not url.startswith("https://") or url in seen:
            continue
        seen.add(url)
        out.append({"name": (s.get("name") or "")[:80], "url": url[:500], "rank": s.get("source_rank"),
                    "date": s.get("date")})
    return out[:limit]


def summarize_round(rnd: dict) -> dict:
    props = rnd.get("properties") or {}
    edges = ((rnd.get("relationships") or {}).get("incoming") or {}).get("PARTICIPATES_IN_FUNDING_ROUND") or []
    investors, leads, srcs = [], [], []
    for e in edges:
        p = e.get("properties") or {}
        if p.get("role") == "ISSUER":
            continue
        investors.append(e.get("name"))
        if p.get("is_lead") is True:
            leads.append({"name": e.get("name"), "id": e.get("id")})
            srcs += p.get("sources") or []
    for name in ("round_label", "transaction_value", "announcement_date"):
        v = props.get(name)
        if isinstance(v, dict):
            srcs += v.get("sources") or []
    return {"round_id": rnd.get("id"), "label": _value(props, "round_label") or rnd.get("name"),
            "amount": _value(props, "transaction_value"), "currency": _value(props, "transaction_value_units"),
            "announced": _value(props, "announcement_date"), "event_date": _value(props, "event_date"),
            "instrument": _value(props, "instrument"), "leads": leads, "n_investors": len(investors),
            "investors": [x for x in investors if x][:30], "sources": _sources(srcs)}


def _round_year(g: dict) -> float | None:
    d = parse_date(g.get("event_date") or g.get("announced"))
    return d[0] + (d[1] - 1) / 12 if d else None


def agreement(our_leads: list[str], check: dict, t: float | None = None) -> str:
    """agrees / differs / graph_no_lead / not_in_graph. A same-stage graph round more than a year away from ours
    is a different round, so it counts as not in the graph."""
    g = check.get("round") if check else None
    if not g:
        return "not_in_graph"
    y = _round_year(g)
    if t is not None and y is not None and abs(y - t) > 1.0:
        return "not_in_graph"
    theirs = {canon(x["name"]) for x in g["leads"] if x.get("name")}
    if not theirs:
        return "graph_no_lead"
    ours = {canon(x) for x in our_leads}
    if ours & theirs or any(_same_name(a, b) for a in ours for b in theirs):
        return "agrees"
    return "differs"


LEGAL = {"private", "limited", "ltd", "lp", "llc", "inc", "gmbh", "ab", "oy", "as", "a", "s", "kommanditbolag", "sa",
         "bv", "plc", "co", "kg", "management", "capital", "ventures", "partners", "fund"}


def _same_name(a: str, b: str) -> bool:
    """'gic' vs 'gic private limited', 'creandum' vs 'creandum kommanditbolag': same once legal words go."""
    wa = [w for w in re.split(r"[^a-z0-9]+", a) if w and w not in LEGAL]
    wb = [w for w in re.split(r"[^a-z0-9]+", b) if w and w not in LEGAL]
    return bool(wa) and wa == wb


def resolve_company(post: Post, search: Search, company_id: str | None, name: str) -> dict | None:
    """The Company entity that carries funding rounds. Query answers sometimes point at a brand entity without
    rounds, so fall back to Cala's fuzzy entity search on the name (the guide's own advice)."""
    tried = set()
    ids = [company_id] if company_id else []
    for attempt in range(2):
        for cid in ids:
            if cid in tried:
                continue
            tried.add(cid)
            company = post(f"/entities/{cid}", COMPANY_BODY)
            if issuer_rounds(company):
                return company
        if attempt == 0:
            hits = search(name)
            key = company_key(name)
            hits = sorted(hits, key=lambda h: 0 if company_key(h.get("name") or "") == key else 1)
            ids = [h["id"] for h in hits[:2] if h.get("id")]
    return None


def check_round(post: Post, search: Search, company_id: str | None, name: str, stage: str | None,
                t: float) -> dict:
    """Returns {"status": ..., "company_entity": id, "round": summary or None}."""
    company = resolve_company(post, search, company_id, name)
    if not company:
        return {"status": "no_rounds_in_graph", "company_entity": None, "round": None}
    edge = pick_round(issuer_rounds(company), stage, t)
    if not edge:
        return {"status": "round_not_in_graph", "company_entity": company.get("id"), "round": None,
                "graph_rounds": [e.get("name") for e in issuer_rounds(company)][:12]}
    return {"status": "found", "company_entity": company.get("id"),
            "round": summarize_round(post(f"/entities/{edge['id']}", ROUND_BODY))}
