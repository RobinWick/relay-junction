"""Tests for the Explore page endpoints (run: python3 app/test_explore_views.py, or pytest).

Uses the real snapshot and the committed people.json and exits.json, through a tiny app with both explore routers.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

try:
    import pytest
except ImportError:  # run without pytest: python3 app/<this file>.py
    import minitest as pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import explore_api as xa
import explore_views as xv
from engine import Snapshot

SNAPSHOT = Path(os.environ.get("RELAY_SNAPSHOT_PATH", Path(__file__).parents[2] / "cala" / "data" / "snapshot.json"))
_SNAP: dict = {}
OSIKA = "200f320b-5b81-4e9a-bf47-4e82a27f0a0f"


def _load() -> Snapshot:
    if "s" not in _SNAP:
        _SNAP["s"] = Snapshot.from_dict(json.loads(SNAPSHOT.read_text()))
    return _SNAP["s"]


@pytest.fixture
def client():
    xa.set_snapshot_provider(_load)
    app = FastAPI()
    app.include_router(xa.router)
    app.include_router(xv.router)
    return TestClient(app)


def test_lists_return_every_item_with_a_source(client):
    meta = client.get("/api/explore/ui/meta").json()
    for view in ("funds", "companies", "founders"):
        body = client.get(f"/api/explore/ui/{view}").json()
        assert len(body["items"]) == meta["counts"][view] > 0
        assert body["source"]["retrieved"]
    assert client.get("/api/explore/ui/people").status_code == 422  # only the three views exist


def test_fund_detail_has_pace_and_real_exit_receipts(client):
    f = client.get("/api/explore/ui/funds/lifeline").json()
    assert sum(y["led"] + y["joined"] + y["unknown"] for y in f["pace"]) == f["rounds"]
    assert f["exit_receipts"] == len(f["exits"]) >= 1 and f["exits"][0]["sources"][0]["url"].startswith("https://")
    assert client.get("/api/explore/ui/funds/no such fund").status_code == 404


def test_fund_outside_the_queried_list_still_has_a_page(client):
    s = _load()
    other = next(k for k, ids in s.by_investor.items() if k not in s.fund_keys and len(ids) >= 3)
    assert client.get(f"/api/explore/ui/funds/{other}").json()["rounds"] >= 1


def test_person_is_facts_with_source_and_no_score(client):
    p = client.get(f"/api/explore/ui/founders/{OSIKA}").json()
    assert p["source"]["entity_id"] == OSIKA and p["source"]["retrieved"]
    assert [r["org"] for r in p["roles"]] == ["Sana Labs", "Lovable"]  # dated roles, oldest first
    assert p["roles"][1]["org_type"] == "Own company"
    orgs = [r["org"] for r in p["undated_roles"]]
    assert len(orgs) == 1 and "CERN" in orgs[0]  # Cala's duplicate CERN and Lovable entities merged
    assert "born" not in (p["description"] or "").lower()
    assert not any("score" in k or "rank" in k for k in p["metrics"])


def test_company_links_its_founders(client):
    c = client.get("/api/explore/ui/companies/lovable").json()
    assert any(f["id"] == OSIKA for f in c["founders"])


def test_ai_filters_map_to_page_keys(client, monkeypatch):
    monkeypatch.setattr(xa, "_gemini", lambda *a: {"error": "off"})
    body = client.post("/api/explore/ui/ai-filters", json={
        "text": "Founders who worked at McKinsey and moved up fast, repeat founders", "role": "investor",
        "view": "companies"}).json()
    assert body["view"] == "founders"
    assert body["filters"]["tags"] == ["Management consulting"]
    assert body["filters"]["ups"] == {"min": 0.5, "max": None} and body["filters"]["repeat"] is True
    assert body["engine"] == "Keyword rules"


def test_ai_filters_map_fund_bands_and_regions(client, monkeypatch):
    raw = {"target": "funds", "region": "nordics", "stage": "seed", "lead_share_min": "0.5", "size_band": "1-3",
           "led_downturn": "yes", "has_exits": "no", "explanation": "x"}
    monkeypatch.setattr(xa, "_gemini", lambda *a: {"raw": raw, "model": "test", "ms": 1})
    body = client.post("/api/explore/ui/ai-filters", json={"text": "nordic seed leads without exits",
                                                           "role": "founder"}).json()
    f = body["filters"]
    assert "Finland" in f["country"] and "Sweden" in f["country"]
    assert f["stage"] == ["seed"] and f["lead_share"] == {"min": 50, "max": None}
    assert f["round"] == {"min": 1, "max": 3} and f["downturn"] is True and "exits" not in f
    assert "has exits: no" in body["unmatched"]
    quiet = client.post("/api/explore/ui/ai-filters", json={"text": "nordic seed leads", "role": "founder"}).json()
    assert not any("has exits" in u for u in quiet["unmatched"])  # a "no" the sentence never said is not shown


def test_unasked_founder_tags_do_not_empty_a_company_search(client, monkeypatch):
    raw = {"target": "companies", "country": "Sweden", "tags": ["nordic_unicorn"], "explanation": "x"}
    monkeypatch.setattr(xa, "_gemini", lambda *a: {"raw": raw, "model": "test", "ms": 1})
    body = client.post("/api/explore/ui/ai-filters", json={"text": "Swedish series A companies", "role": "investor"}).json()
    assert "founder_tags" not in body["filters"] and body["filters"]["country"] == ["Sweden"]
    assert not any("founder background" in u for u in body["unmatched"])  # bug 4: the model's extra is not noise
    body = client.post("/api/explore/ui/ai-filters", json={"text": "Swedish companies with ex-Spotify founders",
                                                           "role": "investor"}).json()
    assert body["filters"]["founder_tags"] == ["Nordic unicorn alumni"]


def test_investor_filters_see_every_investor_of_a_company(client):
    """Bug 1: the page filters on each company's investor list, so it must hold every investor, not the top 12."""
    s = _load()
    items = client.get("/api/explore/ui/companies").json()["items"]
    by_key = {c["key"]: c for c in items}
    creandum = {r["ckey"] for i in s.by_investor["creandum"] for r in [s.rounds[i]] if not r.get("disputed")}
    shown = {c["key"] for c in items if any(i["name"].lower() == s.name("creandum").lower() for i in c["investors"])}
    assert shown == creandum and len(shown) == 54 and "klarna" in shown
    for ck in creandum:
        assert any(i["key"] == "creandum" for i in by_key[ck]["investors"])
    big = max(items, key=lambda c: len(c["investors"]))
    assert len(big["investors"]) > 12
    led = {r["ckey"] for i in s.by_investor["creandum"] for r in [s.rounds[i]]
           if not r.get("disputed") and not r.get("not_led") and "creandum" in r["leads"]}
    assert {c["key"] for c in items if any(i["key"] == "creandum" for i in c["leads"])} == led


def test_ai_keeps_the_users_tab_when_the_sentence_fits_it(client, monkeypatch):
    """Bug 2: on Founders, a founder sentence stays on Founders even when the model picks companies."""
    raw = {"target": "companies", "repeat_founder": "yes", "tags": ["research"], "explanation": "x"}
    monkeypatch.setattr(xa, "_gemini", lambda *a: {"raw": raw, "model": "test", "ms": 1})
    body = client.post("/api/explore/ui/ai-filters", json={
        "text": "repeat founders with a research lab background", "role": "investor", "view": "founders"}).json()
    assert body["view"] == "founders" and body["filters"]["repeat"] is True
    assert body["filters"]["tags"] == [xv.TAG_LABELS["research"]]
    # no list named: the tab wins when it holds as many of the sentence's filters as the model's pick
    raw2 = {"target": "people", "tags": ["consulting"], "explanation": "x"}
    monkeypatch.setattr(xa, "_gemini", lambda *a: {"raw": raw2, "model": "test", "ms": 1})
    body = client.post("/api/explore/ui/ai-filters", json={
        "text": "ex-McKinsey background", "role": "investor", "view": "companies"}).json()
    assert body["view"] == "companies" and body["filters"]["founder_tags"] == ["Management consulting"]


def test_ai_explanation_comes_from_the_filters_set(client, monkeypatch):
    """Bug 3: the text names only filters that were set; amount and sector the sentence asked for are not matched."""
    raw = {"target": "companies", "country": "Norway", "months_since_last_max": "12",
           "explanation": "Norwegian fintech companies that raised over 10 million in the last 12 months"}
    monkeypatch.setattr(xa, "_gemini", lambda *a: {"raw": raw, "model": "test", "ms": 1})
    body = client.post("/api/explore/ui/ai-filters", json={
        "text": "Norwegian fintech that raised over 10M in the last 12 months", "role": "investor",
        "view": "companies"}).json()
    assert body["filters"] == {"country": ["Norway"], "months_since": {"min": None, "max": 12}}
    assert body["explanation"] == "Set from your sentence: Country Norway; Months since last round at most 12."
    assert "10 million" not in body["explanation"] and "fintech" not in body["explanation"]
    assert any(u.startswith("amount (10M)") for u in body["unmatched"])
    assert any(u.startswith("sector (fintech)") for u in body["unmatched"])
    assert body["refusal"] is None
    sort = client.post("/api/explore/ui/ai-filters", json={
        "text": "Nordic seed funds sorted by lead share", "role": "founder", "view": "funds"}).json()
    assert "sorted" not in sort["explanation"] and any(u.startswith("sort (sorted by lead share") for u in sort["unmatched"])


def test_ai_says_it_does_not_rank_people(client, monkeypatch):
    monkeypatch.setattr(xa, "_gemini", lambda *a: {"raw": {"target": "people", "explanation":
                                                           "founders most likely to succeed"}, "model": "test", "ms": 1})
    body = client.post("/api/explore/ui/ai-filters", json={
        "text": "Show me the best founders most likely to succeed, rank them", "role": "investor",
        "view": "founders"}).json()
    assert body["refusal"] == "Recount doesn't rank people or predict success. It shows what Cala has on file."
    assert body["filters"] == {} and "succeed" not in body["explanation"]


def test_person_counts_agree(client):
    """Bug 5: merged duplicate roles keep the titled row, and roles, outside roles and the gaps text agree."""
    p = client.get(f"/api/explore/ui/founders/{OSIKA}").json()
    mt = p["metrics"]
    assert mt["roles"] == len(p["roles"]) + len(p["undated_roles"]) == 3
    assert mt["roles_outside_company"] <= mt["roles"] and mt["roles_outside_company"] == 2
    assert p["undated_roles"][0]["title"] == "Particle Physicist"
    assert f"1 of {mt['roles']} roles has no start date" in p["gaps"]
    assert "1 dated role has no end date (current, or end unknown)" in p["gaps"]
    for item in client.get("/api/explore/ui/founders").json()["items"]:
        m = item["metrics"]
        assert m["roles_outside_company"] <= m["roles"] and m["roles_dated"] <= m["roles"]
        for g in item["gaps"]:
            n = re.match(r"(\d+) of (\d+) roles? ha(s|ve) no start date", g)
            assert not n or int(n.group(2)) == m["roles"]
            assert not re.search(r"\b1 dated roles\b|\b1 of \d+ roles have", g)


def test_no_dashes_reach_the_page(client):
    for view in ("founders",):
        text = json.dumps(client.get(f"/api/explore/ui/{view}").json(), ensure_ascii=False)
        assert not re.search("[\u2012-\u2015]", text)
    text = json.dumps(client.get(f"/api/explore/ui/founders/{OSIKA}").json(), ensure_ascii=False)
    assert not re.search("[\u2012-\u2015]", text)


if __name__ == "__main__":
    import minitest
    minitest.main(globals())
