"""Tests for receipt_pace (run: python3 app/test_receipt_pace.py, or pytest)."""
import json
import os
import re
from pathlib import Path

try:
    import pytest
except ImportError:  # run without pytest: python3 app/<this file>.py
    import minitest as pytest

from engine import Snapshot
from receipt_pace import POPULATION_CONTEXT, dedup_rounds, lead_pace

FORBIDDEN = re.compile(r"\u2013|\u2014|\bstopped\b|\bstarted\b|\blikely\b|\bscore\b|\bprobabilit", re.I)
REAL_SNAPSHOT = Path(os.environ.get("RELAY_SNAPSHOT_PATH", "/Users/robinwickholm/junction-2026/cala/data/snapshot.json"))
CONTEXT_JSON = Path(__file__).resolve().parents[2] / "research" / "patterns" / "pace-context.json"


def _r(rid, company, year, leads=(), parts=(), stage="seed", month=3, amount=None, **extra):
    return {"id": rid, "company": company, "ckey": re.sub(r"[^a-z0-9]", "", company.lower()), "t": year + (month - 1) / 12,
            "year": year, "month": month, "stage": stage, "leads": list(leads), "participants": list(parts),
            "amount_eur_m": amount, "sources": [{"path": "company_first", "query": "q", "row": {"date": f"{year}-{month:02d}-10"}}],
            **extra}


def _snap(rounds):
    for i, r in enumerate(rounds):
        assert r["id"] == i, "ids must be list positions, as in the real snapshot"
    return Snapshot.from_dict({"rounds": rounds, "investor_names": {"f": "Fund F"}, "fund_keys": ["f"],
                               "stats": {}, "retrieved": "2026-11-14", "version": "t"})


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)


def _pause_history():
    """F leads 4 of 4 new deals 2019 to 2021, joins 4 led by others in 2022 to 2023, leads again in 2024."""
    rs = []
    for y in (2019, 2020, 2020, 2021):
        rs.append(_r(len(rs), f"Led{len(rs)}", y, leads=["f"]))
    for y in (2022, 2022, 2023, 2023):
        rs.append(_r(len(rs), f"Join{len(rs)}", y, leads=["other"], parts=["f"]))
    rs.append(_r(len(rs), "Back", 2024, leads=["f"]))
    rs.append(_r(len(rs), "Mystery", 2023, parts=["f"]))  # lead unknown
    return rs


def test_dedup_merges_alias_names_and_links_both_ids():
    rs = [_r(0, "IQM", 2020, leads=["mig"], amount=39.0, stage="series a"),
          _r(1, "IQM Quantum Computers", 2020, parts=["f"], amount=39.5, stage="series a"),
          _r(2, "IQM", 2020, leads=["x"], amount=80.0, stage="series a"),  # amount 2x apart: another round
          _r(3, "IQM", 2020, leads=["y"], stage="series a", disputed=True),
          _r(4, "IQM", 2020, leads=["z"], stage="series a", not_led="Accelerator")]
    out, merged = dedup_rounds(rs)
    assert merged == 1
    assert len(out) == 2
    m = next(r for r in out if 1 in r.get("same_round_ids", []) or r["id"] == 1)
    assert set(m["leads"]) == {"mig"} and m["participants"] == ["f"]
    assert {m["id"], *m["same_round_ids"]} == {0, 1}


def test_lead_is_kept_when_one_duplicate_names_it_and_the_other_lists_it_as_participant():
    out, _ = dedup_rounds([_r(0, "Voi", 2021, leads=["f"], amount=10.0), _r(1, "VOI Technology", 2021, parts=["f", "g"])])
    assert len(out) == 1 and out[0]["leads"] == ["f"] and out[0]["participants"] == ["g"]


def test_years_split_led_joined_unknown_followon_and_band():
    rs = [_r(0, "A", 2021, leads=["f"]),
          _r(1, "A", 2022, leads=["other"], parts=["f"]),  # its own company's next round: follow-on
          _r(2, "B", 2022, leads=["other"], parts=["f"]),
          _r(3, "C", 2022, parts=["f"]),
          _r(4, "D", 2022, leads=["f"], stage="series c"),  # outside the seed band
          _r(5, "E", 2022, leads=["f"], stage=None),
          _r(6, "F", 2018, leads=["f"])]  # before the window
    p = lead_pace(_snap(rs), "f", "seed")
    y22 = next(y for y in p["years"] if y["year"] == 2022)
    assert (y22["led"], y22["joined"], y22["lead_unknown"], y22["follow_on"]) == ([], [2], [3], [1])
    assert y22["counts"] == {"led": 0, "joined": 1, "lead_known": 1, "lead_unknown": 1, "follow_on": 1}
    assert p["totals"]["other_stage"] == 1 and p["totals"]["stage_not_stated"] == 1
    assert p["stage_not_stated_ids"] == [5]
    assert [y["year"] for y in p["years"]] == list(range(2019, 2027))
    assert p["band_label"] == "Pre-seed to Series A"


def test_closed_pause_gives_one_line_with_its_rounds():
    p = lead_pace(_snap(_pause_history()), "f", "seed")
    assert p["summary"] == "Paused leading at Pre-seed to Series A 2022 to 2023 (0 of 4 lead-known rounds), resumed 2024."
    b = p["summary_basis"]
    assert b["kind"] == "pause" and b["round_ids"] == [4, 5, 6, 7] and b["resumed_round_ids"] == [8]
    assert b["prior"] == {"led": 4, "lead_known": 4}
    for rid in b["round_ids"] + b["resumed_round_ids"]:
        assert p["rounds"][str(rid)]["record"] == f"/api/record/{rid}"


def test_open_run_today_is_never_a_line():
    rs = _pause_history()[:-2]  # no lead in 2024: the run is still open
    p = lead_pace(_snap(rs), "f", "seed")
    assert p["summary_basis"]["kind"] == "overall"
    assert p["summary"] == "Led 4 of 8 lead-known rounds at Pre-seed to Series A, 2019 to 2026."
    assert "aused" not in p["summary"]


def test_pause_needs_four_lead_known_rounds():
    rs = _pause_history()
    rs[7] = _r(7, "Join7", 2023, parts=["f"])  # lead unknown now: only 3 lead-known in the run
    p = lead_pace(_snap(rs), "f", "seed")
    assert p["summary_basis"]["kind"] == "overall"
    assert "(1 more round, lead unknown)" not in p["summary"] and "lead unknown" in p["summary"]


def test_pause_is_withheld_when_zero_leads_is_what_the_fund_usually_does():
    rs = [_r(0, "L0", 2019, leads=["f"]), _r(1, "L1", 2020, leads=["f"])]
    rs += [_r(len(rs) + i, f"J{i}", 2019 + i % 2, leads=["o"], parts=["f"]) for i in range(8)]  # prior share 2 of 10
    rs += [_r(len(rs) + i, f"K{i}", 2022, leads=["o"], parts=["f"]) for i in range(4)]
    rs.append(_r(len(rs), "Back", 2024, leads=["f"]))
    p = lead_pace(_snap(rs), "f", "seed")
    assert p["summary_basis"]["kind"] == "overall"  # 0.8 ** 4 = 0.41: zero leads is chance at this fund's pace


def test_too_few_rounds_says_nothing():
    p = lead_pace(_snap([_r(0, "A", 2024, leads=["f"]), _r(1, "B", 2025, leads=["o"], parts=["f"])]), "f", "seed")
    assert p["summary"] is None and p["summary_basis"] is None
    assert p["summary_withheld"].startswith("Fewer than 5 lead-known rounds")


def test_last_lead_at_exact_stage_in_months():
    rs = [_r(0, "A", 2025, leads=["f"], month=11), _r(1, "B", 2026, leads=["f"], stage="series a", month=6)]
    p = lead_pace(_snap(rs), "f", "seed")
    last = p["last_lead_at_stage"]
    assert last["round_id"] == 0 and last["record"] == "/api/record/0" and last["date"] == "Nov 2025"
    assert last["months_ago"] == 12 and last["date_approx"] is False
    assert "0" in p["rounds"]
    assert lead_pace(_snap(rs), "f", "series b")["last_lead_at_stage"] is None


def test_every_counted_id_links_to_a_record():
    p = lead_pace(_snap(_pause_history()), "f", "seed")
    for y in p["years"]:
        for kind in ("led", "joined", "lead_unknown", "follow_on"):
            for rid in y[kind]:
                assert p["rounds"][str(rid)]["record"] == f"/api/record/{rid}"


def test_caveat_and_no_forbidden_words():
    p = lead_pace(_snap(_pause_history()), "f", "seed")
    assert p["caveat"].startswith("Based on 10 announced rounds in Cala")
    assert "Leads are missing for" in p["caveat"]
    for s in _strings(p):
        assert not FORBIDDEN.search(s), s


def test_unknown_stage_fails_loud():
    with pytest.raises(ValueError):
        lead_pace(_snap([_r(0, "A", 2024, leads=["f"])]), "f", "series z")


def test_context_can_be_left_out():
    assert lead_pace(_snap([_r(0, "A", 2024, leads=["f"])]), "f", "seed", include_context=False)["context"] == []


@pytest.mark.skipif(not CONTEXT_JSON.exists(), reason="run research/patterns/pace-context.py first")
def test_population_context_matches_the_recompute_script():
    got = json.loads(CONTEXT_JSON.read_text())
    assert got["matches_decision"] is True
    a, b = POPULATION_CONTEXT[0]["numbers"], POPULATION_CONTEXT[1]["numbers"]
    assert a == {"lead_back": got["lead_back"], "participant_back": got["participant_back"]}
    assert b["gap30_led_again"] == got["gap30_led_again"] and b["no_gap30_led_again"] == got["no_gap30_led_again"]
    assert b["gap30_came_back"] == got["gap30_came_back"] and b["fisher_p"] == got["gap30_fisher_p"]
    for c in POPULATION_CONTEXT:  # every percent in the text is its own fraction, rounded
        for k, n in re.findall(r"\((\d+) of (\d+)\)", c["text"]):
            assert f"{round(100 * int(k) / int(n))}%" in c["text"]


@pytest.mark.skipif(not REAL_SNAPSHOT.exists(), reason="real snapshot not on this machine")
def test_real_snapshot_dedup_and_target_global():
    s = Snapshot.from_dict(json.loads(REAL_SNAPSHOT.read_text()))
    p = lead_pace(s, "target global", "seed")
    assert p["dedup"]["merged_in_snapshot"] == 32  # stopped-leading-check.md: 32 merged
    # 2022 to 2023 holds too few lead-known seed-band rounds to call a pause (stopped-leading-check.md item 4)
    assert p["summary_basis"]["kind"] == "overall"
    for s_ in _strings(p):
        assert not FORBIDDEN.search(s_), s_

if __name__ == "__main__":
    import minitest
    minitest.main(globals())
