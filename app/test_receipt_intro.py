"""Tests for receipt_intro (run: python3 app/test_receipt_intro.py, or pytest)."""
import json
import os
from pathlib import Path

try:
    import pytest
except ImportError:  # run without pytest: python3 app/<this file>.py
    import minitest as pytest

from engine import Snapshot
from receipt_intro import (FOOTNOTE, confirmation, dedupe_rounds, intro_paths, next_stage_of, pasted_fund_receipts,
                           shared_rounds)

CF_QUERY = "List every funding round of {c} with announcement date, round type, amount, lead investor and all participating investors"
IF_QUERY = "List every funding round that {f} invested in, with company name, company country, announcement date"


def cf(company, leads, parts, date="12 March 2025"):
    return {"path": "company_first", "query": CF_QUERY.format(c=company),
            "row": {"announcement_date": date, "lead_investor": ", ".join(leads), "participating_investors": ", ".join(parts)}}


def inv(fund, leads, parts, date="Mar 2025"):
    return {"path": "investor_first", "query": IF_QUERY.format(f=fund),
            "row": {"company": "x", "date": date, "lead_investor": ", ".join(leads), "all_investors": ", ".join(parts)}}


def rnd(company, t, leads, parts=(), stage="seed", amount=5.0, sources=None, month=3, **extra):
    leads, parts = list(leads), list(parts)
    ckey = company.lower().replace(" ", "")
    return {"company": company, "ckey": ckey, "country": "Finland", "t": t, "year": int(t), "month": month,
            "stage": stage, "type": stage.title(), "amount_eur_m": amount, "amount_raw": f"EUR {amount}M",
            "leads": leads, "participants": parts, "cf_leads": leads,
            "sources": sources if sources is not None else [cf(company, leads, parts)],
            "query_path": "company_first", **extra}


def bravo_leads_series_a():
    """Bravo leads 3 Series A rounds in the window, so engine.fund_profile says it leads at Series A."""
    return [rnd(f"Bco{i}", 2025.0 + i / 10, ["bravo"], ["zeta"], stage="series a", amount=10.0) for i in range(3)]


def make(rounds):
    for i, r in enumerate(rounds):
        r["id"] = i
    names = {"alpha": "Alpha", "bravo": "Bravo", "charlie": "Charlie", "delta": "Delta", "zeta": "Zeta",
             "echo": "Echo", "fox": "Fox", "golf": "Golf", "hotel": "Hotel", "india": "India"}
    return Snapshot.from_dict({"rounds": rounds, "investor_names": names, "fund_keys": [], "stats": {},
                               "retrieved": "test", "version": "test", "entities": {}})


def test_suggests_fund_that_leads_next_stage_with_a_confirmed_shared_round():
    snap = make(bravo_leads_series_a() + [rnd("Sono", 2025.2, ["alpha"], ["bravo", "zeta"])])
    out = intro_paths(snap, ["Alpha"], "series a", my_lead="Alpha", my_company="My Startup")
    assert out["lead"] == "Alpha" and out["next_stage"] == "Series A"
    [s] = out["suggestions"]
    assert s["name"] == "Bravo"
    assert s["lead_record"]["verdict"] == "leads" and s["lead_record"]["led_at_stage"] == 3
    assert len(s["lead_record"]["rounds_led_at_stage"]) == 3
    [r] = s["shared_rounds"]
    assert r["company"] == "Sono" and r["date"] == "Mar 2025" and r["amount_eur_m"] == 5.0
    assert r["investors"] == ["Alpha", "Bravo", "Zeta"] and r["with"] == ["Alpha"]
    assert r["confirmation"] == "company_first" and r["rid"] == 3 and r["fund_led"] is False
    assert s["confirmed_companies"] == 1 and not s["one_sided_only"]
    assert "94%" in out["footnote"] and "warm-path-stress.md" in out["footnote_source"]


@pytest.mark.parametrize("bad", [
    {"parts": ["bravo", "zeta", "echo", "fox", "golf", "hotel"]},  # 7 investors
    {"amount": 60.0},  # over 50M EUR
    {"t": 2021.5},  # older than 4 years
    {"month": 6, "sources": [cf("Sono", ["alpha"], ["bravo"], date="2025")]},  # year only, June default
    {"disputed": "source names another lead"},
    {"not_led": "Accelerator or support programme"},
    {"stage": "grant"},  # type 'Grant' is not equity
    {"company": "My Startup"},  # the founder's own company
])
def test_rounds_that_are_not_small_recent_equity_rounds_are_never_receipts(bad):
    kw = {"company": "Sono", "t": 2025.2, "parts": ["bravo"], "amount": 5.0}
    kw.update(bad)
    company, t, parts = kw.pop("company"), kw.pop("t"), kw.pop("parts")
    shared = rnd(company, t, ["alpha"], parts, **kw)
    snap = make(bravo_leads_series_a() + [shared])
    assert shared_rounds(snap, "bravo", ["alpha"], "My Startup") == []
    assert intro_paths(snap, ["Alpha"], "series a", my_company="My Startup")["suggestions"] == []


def test_one_sided_tie_is_never_suggested():
    charlie = [rnd(f"Cco{i}", 2025.0 + i / 10, ["charlie"], ["zeta"], stage="series a", amount=10.0) for i in range(3)]
    one_sided = rnd("Ovi", 2026.0, ["alpha"], ["bravo"], sources=[inv("Alpha", ["Alpha"], ["Alpha", "Bravo"])])
    confirmed = rnd("Qmi", 2024.5, ["alpha"], ["charlie"])
    snap = make(bravo_leads_series_a() + charlie + [one_sided, confirmed])
    out = intro_paths(snap, ["Alpha"], "series a")
    assert [s["name"] for s in out["suggestions"]] == ["Charlie"]  # Bravo has only a one-sided tie
    assert all(r["confirmation"] != "one_sided" for s in out["suggestions"] for r in s["shared_rounds"])
    # a fund the founder names still shows its one-sided round, labelled
    named = pasted_fund_receipts(snap, ["Bravo"], ["Alpha"], "series a")["funds"][0]
    assert named["one_sided_only"] is True and named["shared_rounds"][0]["confirmation"] == "one_sided"


def test_suggestion_drops_one_sided_rounds_but_keeps_confirmed_ones():
    one_sided = rnd("Ovi", 2026.0, ["alpha"], ["bravo"], sources=[inv("Alpha", ["Alpha"], ["Alpha", "Bravo"])])
    confirmed = rnd("Qmi", 2024.5, ["alpha"], ["bravo"])
    out = intro_paths(make(bravo_leads_series_a() + [one_sided, confirmed]), ["Alpha"], "series a")
    (s,) = out["suggestions"]
    assert [r["company"] for r in s["shared_rounds"]] == ["Qmi"]
    assert s["shared_rounds"][0]["confirmation"] == "company_first"


def test_last_lead_at_stage_is_at_the_next_stage():
    later_seed = rnd("Late", 2026.5, ["bravo"], ["zeta"], stage="seed")
    snap = make(bravo_leads_series_a() + [later_seed, rnd("Qmi", 2024.5, ["alpha"], ["bravo"])])
    lr = intro_paths(snap, ["Alpha"], "series a")["suggestions"][0]["lead_record"]
    assert lr["last_lead_at_stage"]["stage"] == "Series A"
    assert lr["last_lead_at_stage"]["t"] == max(r["t"] for r in lr["rounds_led_at_stage"])


def test_two_independent_investor_first_answers_confirm_a_tie():
    sources = [inv("Alpha", ["Alpha"], ["Bravo"]), inv("Bravo", ["Alpha"], ["Alpha and others"])]
    r = rnd("Ovi", 2025.5, ["alpha"], ["bravo"], sources=sources)
    assert confirmation([r], "alpha", "bravo") == "two_sources"
    assert confirmation([r], "alpha", "zeta") == "one_sided"


def test_company_aliases_and_echo_rows_count_once():
    a = rnd("IQM", 2025.2, ["alpha"], ["bravo"], amount=8.0)
    b = rnd("IQM Quantum Computers", 2025.25, ["alpha"], ["bravo"], amount=8.2)
    other = rnd("IQM", 2024.2, ["alpha"], ["bravo"], amount=3.0, stage="pre-seed")
    snap = make(bravo_leads_series_a() + [a, b, other])
    assert len(dedupe_rounds([a, b, other])) == 2
    got = shared_rounds(snap, "bravo", ["alpha"], None)
    assert len(got) == 2 and len(got[0]["echo_rids"]) == 1
    [s] = intro_paths(snap, ["Alpha"], "series a")["suggestions"]
    assert s["shared_companies"] == 1  # two rounds, one company


def test_echo_merge_can_push_a_round_over_six_investors():
    a = rnd("Sono", 2025.2, ["alpha"], ["bravo", "zeta", "echo"])
    b = rnd("Sono", 2025.25, ["alpha"], ["fox", "golf", "hotel", "india"])
    snap = make(bravo_leads_series_a() + [a, b])
    assert shared_rounds(snap, "bravo", ["alpha"], None) == []


def test_fund_that_does_not_lead_next_stage_is_not_suggested_but_pasted_funds_keep_receipts():
    snap = make(bravo_leads_series_a() + [rnd("Sono", 2025.2, ["alpha"], ["delta"])])
    assert intro_paths(snap, ["Alpha"], "series a")["suggestions"] == []
    out = pasted_fund_receipts(snap, ["Delta", "Bravo", "No Such Fund Anywhere"], ["Alpha"], "series a")
    assert [f["name"] for f in out["funds"]] == ["Delta", "Bravo"]
    assert out["funds"][0]["shared_rounds"][0]["company"] == "Sono"
    assert out["funds"][0]["lead_record"]["verdict"] == "few"
    assert out["funds"][1]["shared_rounds"] == [] and out["funds"][1]["latest_shared"] is None
    assert out["unmatched"] == ["No Such Fund Anywhere"] and "94%" in out["footnote"]


def test_founders_own_investors_and_hubs_are_never_suggested():
    snap = make(bravo_leads_series_a() + [rnd("Sono", 2025.2, ["alpha"], ["bravo", "business finland"])])
    out = intro_paths(snap, ["Alpha", "Bravo", "Business Finland"], "series a")
    assert out["suggestions"] == []
    assert {"key": "business finland", "name": "Business Finland", "excluded": True} in out["investors"]


def test_stage_helpers():
    assert next_stage_of("seed") == "series a" and next_stage_of("growth") is None and next_stage_of("x") is None
    with pytest.raises(ValueError):
        intro_paths(make([]), ["Alpha"], "Series A")


SNAPSHOT = Path(os.environ.get("RELAY_SNAPSHOT_PATH", "/Users/robinwickholm/junction-2026/cala/data/snapshot.json"))


@pytest.mark.skipif(not SNAPSHOT.exists(), reason="no local snapshot")
def test_real_snapshot_receipts_obey_the_rules():
    snap = Snapshot.from_dict(json.loads(SNAPSHOT.read_text()))
    out = intro_paths(snap, ["Lifeline Ventures", "Maki.vc"], "series a", 8.0, my_lead="Lifeline Ventures")
    assert out["suggestions"] and not out["unmatched"]
    rank = {"two_sources", "company_first"}  # one-sided rounds are never suggested
    for s in out["suggestions"]:
        assert s["lead_record"]["verdict"] in ("leads", "leads_size")
        assert s["confirmed_companies"] > 0 and not s["one_sided_only"]
        for r in s["shared_rounds"]:
            assert 2 <= r["n_investors"] <= 6 and (r["amount_eur_m"] or 0) <= 50
            assert snap.now_t - r["t"] <= 4 and r["confirmation"] in rank
            assert not snap.rounds[r["rid"]].get("disputed")

if __name__ == "__main__":
    import minitest
    minitest.main(globals())
