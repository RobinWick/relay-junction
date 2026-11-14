"""Tests for the Recount Signal API (run: python3 app/test_signal_api.py, or pytest).

Uses a small synthetic snapshot through signal_data.set_snapshot_provider, so no database, file or network is needed.
Gemini is replaced by a stub; the real key path is never called here.
"""
import json
import os
import re
from pathlib import Path
from urllib.parse import quote

try:
    import pytest
except ImportError:  # run without pytest
    import minitest as pytest

os.environ.setdefault("COOKIE_KEY", "test-cookie-key")
os.environ["RELAY_GATE"] = "off"
os.environ["SIGNAL_WARM"] = "off"

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
import signal_api  # noqa: E402
import signal_chat  # noqa: E402
import signal_data as sd  # noqa: E402
import signal_filters as sf  # noqa: E402

DASH = re.compile("[–—]")
_ids = iter(range(10 ** 6))


def _r(ck, t, stage="seed", amount=1.0, leads=("alpha",), parts=("beta",), country="Finland", path="investor_first",
       company=None, **kw):
    return {"id": next(_ids), "ckey": ck, "company": company or ck.title(), "country": country, "t": t,
            "year": int(t), "month": 6, "stage": stage, "amount_eur_m": amount, "leads": list(leads),
            "participants": list(parts), "query_path": path, "type": stage,
            "sources": [{"path": path, "row": {"date": f"Jun {int(t)}"}}], **kw}


def _snapshot() -> dict:
    rounds = []
    for i in range(30):  # peers with spread sizes so percentiles exist
        rounds.append(_r(f"peer{i}", 2024.5, amount=0.5 + i * 0.25, parts=tuple(f"p{j}" for j in range(i % 6)),
                         country="Sweden" if i % 2 else "Germany"))
    rounds += [
        _r("payco", 2022.4, amount=1.0, path="company_first"),
        _r("payco", 2024.4, stage="series a", amount=8.0, leads=("gamma",), parts=("alpha", "beta", "delta"),
           path="company_first"),
        _r("thinco", 2025.1, stage=None, amount=None, leads=(), parts=("beta",)),
        _r("grantco", 2025.0, stage=None, amount=0.2, leads=(), parts=("business finland",), not_led=True),
    ]
    names = {k: k.title() for r in rounds for k in r["leads"] + r["participants"]}
    names["jane smith"] = "Jane Smith"
    return {"version": "test-1", "retrieved": "2026-11-14", "rounds": rounds, "investor_names": names,
            "fund_keys": ["alpha", "gamma"], "entities": {}, "stats": {}}


EXTRA = {"sectors": {"payco": ["Fintech"]}, "text_sector": {"peer1": ["Payments platform for SMEs"]},
         "cohorts": {"payco": [{"employer": "Google", "evidence": "worked_at", "founder": "Jane Smith"}]},
         "founders": [{"id": "f1", "name": "Jane Smith", "ckeys": ["payco"], "roles": [{"org": "Payco", "role": "CEO",
                                                                                    "since": None, "until": None}],
                       "founded": [], "prior_exits": [], "description": None, "files": ["test"], "twin_link": False,
                       "link_basis": ["FOUNDED"], "merged_duplicate": False},
                      {"id": "f2", "name": "Twin Person", "ckeys": ["peer2"], "roles": [], "founded": [],
                       "prior_exits": [], "description": None, "files": ["test"], "twin_link": True,
                       "link_basis": ["FOUNDED (twin entity)"], "merged_duplicate": False}],
         "exits": [], "checked_funds": []}

_SNAP = _snapshot()


def _setup():
    orig = sd.load_extra
    sd.load_extra = lambda path=None: EXTRA
    sd.set_snapshot_provider(lambda: _SNAP)
    signal_api._list_cache.clear()
    signal_api._hits.clear()
    return orig


_orig_extra = _setup()
client = TestClient(main.app)


def _get(path, **params):
    q = "&".join(f"{k}={quote(json.dumps(v) if not isinstance(v, str) else v)}" for k, v in params.items())
    return client.get(f"/api/signal{path}" + (f"?{q}" if q else ""))


def _strings(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for k, v in o.items():
            yield from _strings(k)
            yield from _strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from _strings(v)


# ---------------------------------------------------------------- lists
def test_companies_list_shape_and_transparency():
    r = _get("/companies", limit="100")
    assert r.status_code == 200
    d = r.json()
    m = d["meta"]
    assert m["total"] == len({x["ckey"] for x in _SNAP["rounds"]})
    assert "backtest_line" in m and m["weights_effective"]
    assert abs(sum(m["weights_effective"].values()) - 1) < 0.01
    row = next(x for x in d["rows"] if x["id"] == "c:payco")
    assert row["country"] == {"code": "FI", "name": "Finland", "flag": "\U0001F1EB\U0001F1EE"}
    assert row["coverage"]["n"] > 0 and "evidence" in row and row["band"] in signal_api.BAND_ORDER


def test_unranked_stay_visible_and_never_get_a_number():
    d = _get("/companies", limit="200").json()
    by = {x["id"]: x for x in d["rows"]}
    assert by["c:thinco"]["score"] is None and by["c:thinco"]["band"] == "not_enough_data"
    assert by["c:grantco"]["score"] is None  # only a programme round
    assert "Not enough data" in by["c:grantco"]["score_reason"]


def test_sector_filter_reports_not_considered_and_low_coverage():
    d = _get("/companies", filters=[{"key": "sector", "op": "in", "value": ["Fintech"]}]).json()
    ids = {x["id"] for x in d["rows"]}
    assert "c:payco" in ids and "c:peer1" in ids  # tag and text match
    nc = {x["filter"]: x["count"] for x in d["meta"]["not_considered"]}
    assert nc["sector"] > 0
    assert d["meta"]["coverage_warnings"][0]["filter"] == "sector"
    shown = _get("/companies", filters=[{"key": "sector", "op": "in", "value": ["Fintech"]}],
                 no_data_group="true", limit="200").json()
    assert any(x.get("group") == "no_data" for x in shown["rows"])


def test_unknown_filter_key_is_400():
    r = _get("/companies", filters=[{"key": "revenue", "op": "gte", "value": 1}])
    assert r.status_code == 400 and r.json()["error"] == "bad_filter"
    assert _get("/companies", weights={"revenue": 1}).status_code == 400
    assert _get("/companies", sort="nope:desc").status_code == 400


def test_weights_clamped_renormalised_and_diffed():
    d = _get("/companies", weights={"backer_graduation": 5, "named_angels": 5, "sector_heat": 0.1}).json()
    w = d["meta"]["weights_effective"]
    assert abs(sum(w.values()) - 1) < 0.01
    assert w["sector_heat"] == 0  # no sector filter, no sector weight
    thesis = sum(v for k, v in w.items() if sd.ss.TIER[k] == "thesis")
    assert thesis <= 0.31
    assert any(x["key"] == "backer_graduation" for x in d["meta"]["weights_diff"])


def test_fair_rank_and_sorts():
    d = _get("/companies", fair_rank="true", limit="5").json()
    assert d["meta"]["fair_rank"] is True and d["rows"][0]["rank"] == 1
    d = _get("/companies", sort="last_amount_eur_m:desc", limit="3").json()
    assert d["rows"][0]["last_round"]["amount_eur_m"] == 8.0


def test_funds_and_founders_lists():
    d = _get("/funds").json()
    assert all(r["queried"] for r in d["rows"]) and {r["key"] for r in d["rows"]} == {"alpha", "gamma"}
    assert d["meta"]["score_label"].startswith("How actively")
    allf = _get("/funds", filters=[{"key": "fund_queried_only", "op": "is_false"}], limit="200").json()
    assert any(r["score"] is None and r["score_reason"] for r in allf["rows"])
    f = _get("/founders").json()
    assert {r["name"] for r in f["rows"]} == {"Jane Smith"}  # twin link hidden by default
    jane = f["rows"][0]
    assert jane["score"] is None and jane["score_reason"].startswith("Not enough data")
    assert jane["company"]["score_label"] == "company score, not a founder score"
    assert "not a judgment" in f["meta"]["note"]


# ---------------------------------------------------------------- detail
def test_company_detail_shows_every_component():
    d = client.get("/api/signal/companies/c:payco").json()
    comps = d["score"]["components"]
    assert [c["key"] for c in comps] == sd.ss.KEYS
    for c in comps:
        assert {"weight", "value", "points", "raw", "records", "present"} <= set(c)
        if not c["present"]:
            assert c["value"] == 0.5 and c["missing_reason"]
    assert d["rounds"] and all(r["record_url"].startswith("/api/record/") for r in d["rounds"])
    assert client.get("/api/signal/companies/c:nope").status_code == 404
    assert client.get("/api/signal/funds/f:alpha").json()["entity"] == "fund"
    assert client.get("/api/signal/founders/p:f1").json()["name"] == "Jane Smith"


# ---------------------------------------------------------------- meta
def test_meta_has_claim_line_and_filter_coverage():
    d = _get("/meta").json()
    assert d["backtest_line"] and d["honesty"]
    assert any("74% exact, 89% right fund" in h for h in d["honesty"])
    assert not any("85%" in h for h in d["honesty"])
    sector = next(f for f in d["filters"] if f["key"] == "sector" and f["view"] == "companies")
    assert sector["coverage"]["n"] == 2 and sector["low_coverage"] is True
    assert len([f for f in d["filters"] if f["view"] == "companies"]) >= 50


# ---------------------------------------------------------------- chat
def _stub(raw=None, err=None, rejected=False):
    def fake(st, view, message, user_key):
        _stub.last_key = user_key
        if rejected:
            raise signal_chat.UserKeyRejected()
        return {"raw": raw, "model": "stub", "ms": 1} if raw is not None else {"error": err or "down"}
    return fake


def _chat(body, fake):
    orig = signal_chat.call_gemini
    signal_chat.call_gemini = fake
    try:
        return client.post("/api/signal/chat", json=body)
    finally:
        signal_chat.call_gemini = orig


def test_chat_validates_gemini_output_unknown_keys_go_to_unmatched():
    raw = {"filters": [{"key": "sector", "op": "in", "values": ["Fintech"], "reason": "fintech"},
                       {"key": "revenue_growth", "op": "gte", "number": 0.5, "reason": "growth"},
                       {"key": "country", "op": "in", "values": ["FI", "Atlantis"], "reason": "x"}],
           "weight_overrides": {"lead_named": 0.18, "made_up": 1}, "explanation": "Fintech, ranked.",
           "unmatched": [{"phrase": "ARR", "reason": "no revenue data"}]}
    r = _chat({"message": "fintech with revenue growth in Finland"}, _stub(raw))
    assert r.status_code == 200
    d = r.json()
    assert d["source"] == "gemini"
    assert {f["key"] for f in d["filters"]} == {"sector", "country"}
    phrases = {u["phrase"] for u in d["unmatched"]}
    assert {"revenue_growth", "ARR", "Atlantis", "made_up"} <= phrases
    assert d["weights_effective"]["sector_heat"] > 0  # sector named: momentum on
    assert d["coverage_warnings"] and d["results_preview"]["rows"]


def test_chat_fallback_keywords_when_gemini_fails():
    d = _chat({"message": "Nordic fintech at seed with strong revenue"}, _stub(err="timeout")).json()
    assert d["source"] == "fallback" and "keywords" in d["notice"]
    keys = {f["key"] for f in d["filters"]}
    assert {"sector", "region", "last_stage"} <= keys
    assert any(u["phrase"] == "revenue" for u in d["unmatched"])


def test_chat_user_key_used_once_and_rejection_is_401():
    _chat({"message": "fintech", "user_api_key": "user-key-123"}, _stub({"filters": [], "weight_overrides": {},
                                                                         "explanation": "ok", "unmatched": []}))
    assert _stub.last_key == "user-key-123"
    r = _chat({"message": "fintech", "user_api_key": "bad"}, _stub(rejected=True))
    assert r.status_code == 401 and r.json()["error"] == "user_key_rejected"
    assert "bad" not in r.text


def test_chat_empty_and_long_messages():
    assert _chat({"message": "  "}, _stub(err="x")).json()["error"] == "empty_message"
    d = _chat({"message": "fintech " * 100}, _stub(err="x")).json()
    assert any("first 500" in u["reason"] for u in d["unmatched"])


def test_chat_founders_view_shows_thin_data():
    d = _chat({"message": "founders with a great track record", "view": "founders"}, _stub(err="x")).json()
    assert "Not enough data" in d["results_preview"]["rows"][0]["score_reason"]
    assert "thin" in d["note"]


def test_chat_rate_limited_per_ip():
    signal_api._hits.clear()
    codes = [_chat({"message": "fintech"}, _stub(err="x")).status_code for _ in range(signal_api.CHAT_PER_MIN["session"] + 2)]
    assert 429 in codes
    signal_api._hits.clear()


# ---------------------------------------------------------------- honesty
def test_no_dashes_in_api_strings_and_sources():
    for name in ("signal_api.py", "signal_chat.py", "signal_data.py", "signal_filters.py", "signal_extra_build.py"):
        assert not DASH.search(Path(sd.__file__).with_name(name).read_text()), name
    for path in ("/meta", "/companies?limit=200", "/funds", "/founders", "/companies/c:payco"):
        for s in _strings(client.get("/api/signal" + path).json()):
            assert not DASH.search(s), (path, s)


def test_real_extra_file_has_no_dashes_and_expected_shape():
    p = Path(sd.__file__).with_name("signal_extra.json")
    if not p.exists():
        pytest.skip("run signal_extra_build.py first")
    d = json.loads(p.read_text())
    assert {"sectors", "text_sector", "cohorts", "founders", "exits", "checked_funds"} <= set(d)
    assert not DASH.search(p.read_text())


def test_filter_catalogue_is_consistent():
    for view, specs in sf.SPECS.items():
        for k, s in specs.items():
            assert s.key == k and s.label and s.group and s.kind
    assert len(sf.SPECS["companies"]) >= 50



def test_switching_off_a_default_exclusion_keeps_everyone():
    base = _get("/companies", limit="1").json()["meta"]["matched"]
    for key in ("hide_duplicates", "exclude_acquired", "exclude_disputed", "exclude_public_bodies"):
        off = _get("/companies", limit="1", filters=[{"key": key, "op": "is_false"}]).json()["meta"]["matched"]
        assert off >= base, key  # never inverts into "only the excluded ones"


def test_fund_led_in_downturn_filter():
    d = _get("/funds", filters=[{"key": "fund_led_in_downturn", "op": "gte", "value": 1}]).json()
    assert d["meta"]["matched"] <= _get("/funds").json()["meta"]["matched"]
    assert all((r.get("downturn_lead_share") or {}).get("led", 0) >= 1 for r in d["rows"] if "downturn_lead_share" in r)

if __name__ == "__main__":
    import minitest
    minitest.main(globals())
