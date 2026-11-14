"""Tests for the Explore page endpoints (run: python3 app/test_explore_views.py, or pytest).

Uses the real snapshot and the committed people.json and exits.json, through a tiny app with both explore routers.
"""
from __future__ import annotations

import json
import os
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
    body = client.post("/api/explore/ui/ai-filters", json={"text": "nordic seed leads", "role": "founder"}).json()
    f = body["filters"]
    assert "Finland" in f["country"] and "Sweden" in f["country"]
    assert f["stage"] == ["seed"] and f["lead_share"] == {"min": 50, "max": None}
    assert f["round"] == {"min": 1, "max": 3} and f["downturn"] is True and "exits" not in f
    assert "has exits: no" in body["unmatched"]


def test_unasked_founder_tags_do_not_empty_a_company_search(client, monkeypatch):
    raw = {"target": "companies", "country": "Sweden", "tags": ["nordic_unicorn"], "explanation": "x"}
    monkeypatch.setattr(xa, "_gemini", lambda *a: {"raw": raw, "model": "test", "ms": 1})
    body = client.post("/api/explore/ui/ai-filters", json={"text": "Swedish series A companies", "role": "investor"}).json()
    assert "founder_tags" not in body["filters"] and body["filters"]["country"] == ["Sweden"]
    body = client.post("/api/explore/ui/ai-filters", json={"text": "Swedish companies with ex-Spotify founders",
                                                           "role": "investor"}).json()
    assert body["filters"]["founder_tags"] == ["Nordic unicorn alumni"]


if __name__ == "__main__":
    import minitest
    minitest.main(globals())
