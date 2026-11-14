"""Tests for signal_score (run: python3 app/test_signal_score.py, or pytest)."""
import json
import re
from pathlib import Path

try:
    import pytest
except ImportError:  # run without pytest: python3 app/<this file>.py
    import minitest as pytest

import signal_score as ss
from signal_score import ScoreInputs, build_context, clamp_weights, founder_evidence, fund_scores, score_all

DASH = re.compile("[–—]")
_id = iter(range(10 ** 6))


def _r(ck, t, stage="seed", amount=1.0, leads=("alpha",), parts=("beta",), country="Finland", path="investor_first", **kw):
    return {"id": next(_id), "ckey": ck, "company": ck.title(), "country": country, "t": t, "year": int(t),
            "month": 6, "stage": stage, "amount_eur_m": amount, "leads": list(leads), "participants": list(parts),
            "query_path": path,
            "sources": [{"path": path, "row": {"date": f"Jun {int(t)}"}}], **kw}


def _inp(rounds, **kw):
    names = {k: k.title() for r in rounds for k in r["leads"] + r["participants"]}
    return ScoreInputs(rounds, names, set(kw.pop("fund_keys", {"alpha"})), **kw)


def _peers(n=20, t=2024.5, stage="seed"):
    """n peer companies with spread amounts so percentiles have a pool."""
    return [_r(f"peer{i}", t, stage=stage, amount=0.5 + i * 0.25, parts=tuple(f"p{j}" for j in range(i % 6)))
            for i in range(n)]


def _row(run, ck):
    return run.rows[ck]


def _comp(row, key):
    return next(p for p in row["components"] if p["key"] == key)


# ---------------------------------------------------------------- weights
def test_clamp_weights_caps_and_renormalises():
    w = clamp_weights({"backer_graduation": 0.9, "named_angels": 0.9, "insider_follow_on": 0.9})
    assert abs(sum(w.values()) - 1) < 1e-9
    raw_thesis = {k: v for k, v in w.items() if ss.TIER[k] == "thesis"}
    assert sum(raw_thesis.values()) / sum(w.values()) <= ss.THESIS_TOTAL_CAP / (1 - 0) + 1e-9
    assert w["sector_heat"] == 0.0  # no sector filter, no sector weight


def test_clamp_weights_sector_only_with_sector_filter():
    assert clamp_weights({"sector_heat": 0.1})["sector_heat"] == 0.0
    assert clamp_weights({"sector_heat": 0.1}, sector_active=True)["sector_heat"] > 0
    assert clamp_weights({"sector_heat": 0.01}, sector_active=True)["sector_heat"] > 0.04


def test_clamp_weights_rejects_unknown_and_negative():
    with pytest.raises(ValueError):
        clamp_weights({"revenue": 0.5})
    with pytest.raises(ValueError):
        clamp_weights({"size_for_stage": -1})
    with pytest.raises(ValueError):
        clamp_weights({k: 0.0 for k in ss.KEYS})


def test_weights_file_matches_components():
    w = ss.load_weights()
    assert set(w) == set(ss.KEYS)
    assert abs(sum(clamp_weights(base=w).values()) - 1) < 1e-9


# ---------------------------------------------------------------- score
def test_renormalisation_bug_one_fact_never_scores_100():
    """Skeptic 2a: a company known only by 'lead named' must not reach a perfect score."""
    rounds = _peers() + [_r("onefact", 2024.5, amount=None, parts=())]
    run = score_all(_inp(rounds), as_of_t=2025.0, weights=clamp_weights())
    row = _row(run, "onefact")
    assert row["ranked"] and row["score"] < 70
    missing = [p for p in row["components"] if not p["present"] and p["weight"] > 0]
    assert missing and all(p["value"] == 0.5 and p["missing_reason"] for p in missing)
    assert row["coverage"]["k"] < row["coverage"]["n"]


def test_no_stage_means_unranked_but_listed():
    rounds = _peers() + [_r("nostage", 2024.5, stage=None)]
    run = score_all(_inp(rounds), as_of_t=2025.0, weights=clamp_weights())
    row = _row(run, "nostage")
    assert not row["ranked"] and row["score"] is None and row["band"] == "not_enough_data"
    assert "nostage" not in run.ranked and row["score_reason"]


def test_point_in_time_ignores_future_rounds():
    rounds = _peers() + [_r("x", 2023.5, amount=1.0), _r("x", 2026.0, stage="series a", amount=50.0)]
    a = score_all(_inp(rounds), as_of_t=2025.0, weights=clamp_weights())
    b = score_all(_inp([r for r in rounds if r["t"] < 2025.0]), as_of_t=2025.0, weights=clamp_weights())
    assert a.rows["x"]["score"] == b.rows["x"]["score"]
    assert a.rows["x"]["last_stage"] == "seed"


def test_excludes_programmes_and_disputed_and_hubs():
    rounds = _peers() + [_r("y", 2024.5, leads=("business finland",), parts=("eic", "beta")),
                         _r("y", 2024.7, not_led="Accelerator or support programme, not a led round")]
    run = score_all(_inp(rounds), as_of_t=2025.0, weights=clamp_weights())
    br = _comp(run.rows["y"], "syndicate_breadth")
    assert br["raw"]["named_investors"] == 1  # only beta; public bodies never count
    assert run.rows["y"]["last_round"]["date"].startswith("2024")


def test_bigger_round_scores_higher_size_for_stage():
    rounds = _peers() + [_r("big", 2024.5, amount=20.0), _r("small", 2024.5, amount=0.1)]
    run = score_all(_inp(rounds), as_of_t=2025.0, weights=clamp_weights())
    big, small = _comp(run.rows["big"], "size_for_stage"), _comp(run.rows["small"], "size_for_stage")
    assert big["value"] > 0.9 > 0.1 > small["value"]
    assert big["peer_group"]["n"] >= ss.MIN_PEERS and big["records"][0]["amount_eur_m"] == 20.0
    assert run.rows["big"]["score"] > run.rows["small"]["score"]


def test_not_enough_peers_is_missing_not_zero():
    rounds = [_r("lonely", 2024.5, stage="series f", amount=100.0)]
    run = score_all(_inp(rounds), as_of_t=2025.0, weights=clamp_weights())
    c = _comp(run.rows["lonely"], "size_for_stage")
    assert not c["present"] and "not enough peers" in c["missing_reason"]


def test_acceleration_needs_three_raises_and_collapses_close_rounds():
    rs = [_r("acc", 2019.5), _r("acc", 2021.5, stage="series a"), _r("acc", 2021.6, stage="series a"),
          _r("acc", 2022.5, stage="series b")]
    run = score_all(_inp(_peers() + rs), as_of_t=2025.0, weights=clamp_weights())
    c = _comp(run.rows["acc"], "acceleration")
    assert c["present"] and c["raw"] == {"prev_gap_months": 24, "last_gap_months": 12} and c["value"] > 0.5
    two = score_all(_inp(_peers() + rs[:3]), as_of_t=2025.0, weights=clamp_weights())
    assert not _comp(two.rows["acc"], "acceleration")["present"]


def test_insider_follow_on_and_step_up():
    rs = [_r("ins", 2021.5, amount=1.0, leads=("alpha",), parts=("beta", "gamma")),
          _r("ins", 2023.5, stage="series a", amount=4.0, leads=("delta",), parts=("beta",))]
    run = score_all(_inp(_peers() + rs), as_of_t=2025.0, weights=clamp_weights())
    ins = _comp(run.rows["ins"], "insider_follow_on")
    assert ins["present"] and abs(ins["value"] - 1 / 3) < 1e-3
    su = _comp(run.rows["ins"], "step_up")
    assert su["raw"]["ratio"] == 4.0 and abs(su["value"] - 0.75) < 1e-3


def test_named_angels_never_lower_than_neutral():
    rs = [_r("ang", 2024.5, parts=("Johan Brenner",))]
    inp = _inp(_peers() + rs)
    inp.investor_names["Johan Brenner"] = "Johan Brenner"
    run = score_all(inp, as_of_t=2025.0, weights=clamp_weights())
    c = _comp(run.rows["ang"], "named_angels")
    assert c["present"] and c["value"] > 0.5
    assert not _comp(run.rows["peer1"], "named_angels")["present"]


def test_backer_graduation_point_in_time_and_own_company_excluded():
    rs = []
    for i in range(4):  # gamma backs 4 seeds in 2019, 3 raise again within 24 months
        rs.append(_r(f"g{i}", 2019.5, leads=("gamma",), parts=()))
        if i < 3:
            rs.append(_r(f"g{i}", 2020.5, stage="series a", leads=("zeta",), parts=()))
    rs.append(_r("target", 2024.0, leads=("gamma",), parts=()))
    run = score_all(_inp(_peers() + rs), as_of_t=2025.0, weights=clamp_weights())
    c = _comp(run.rows["target"], "backer_graduation")
    assert c["raw"]["k"] == 3 and c["raw"]["n"] == 4
    own = _comp(run.rows["g0"], "backer_graduation")
    assert own["present"] is False or own["raw"]["n"] == 3  # g0's own entry is not counted for g0
    early = score_all(_inp(_peers() + rs), as_of_t=2021.0, weights=clamp_weights())
    assert not _comp(early.rows["g1"], "backer_graduation")["present"]  # 24 months not over by 2021


def test_backer_exits_not_checked_vs_none_found():
    rs = [_r("e1", 2024.5, leads=("alpha",), parts=()), _r("e2", 2024.5, leads=("omega",), parts=())]
    inp = _inp(_peers() + rs, exits=[{"fund_key": "alpha", "ckey": "soldco", "year": 2020}], checked_funds={"alpha"})
    run = score_all(inp, as_of_t=2025.0, weights=clamp_weights())
    assert _comp(run.rows["e1"], "backer_exits")["raw"]["exits"] == 1
    assert "not checked" in _comp(run.rows["e2"], "backer_exits")["missing_reason"]


def test_deterministic_and_rank_order():
    rounds = _peers() + [_r("big", 2024.5, amount=20.0)]
    a = score_all(_inp(rounds), as_of_t=2025.0, weights=clamp_weights())
    b = score_all(_inp(list(reversed(rounds))), as_of_t=2025.0, weights=clamp_weights())
    assert a.ranked == b.ranked and a.rules_hash == b.rules_hash
    assert [a.rows[k]["score"] for k in a.ranked] == sorted((a.rows[k]["score"] for k in a.ranked), reverse=True)
    assert a.rows[a.ranked[0]]["rank"] == 1


def test_bands_cover_ranked_and_top_tenth():
    rounds = _peers(40)
    run = score_all(_inp(rounds), as_of_t=2025.0, weights=clamp_weights())
    bands = [run.rows[k]["band"] for k in run.ranked]
    top = sum(1 for b in bands if b in ("strong", "promising"))
    assert 1 <= top <= 6 and set(bands) <= {"strong", "promising", "watch", "low"}


def test_points_sum_to_score_minus_neutral():
    run = score_all(_inp(_peers()), as_of_t=2025.0, weights=clamp_weights())
    row = run.rows["peer7"]
    assert abs(sum(p["points"] for p in row["components"]) + 50 - 100 * row["raw_score"]) < 0.1


def test_weights_must_sum_to_one():
    with pytest.raises(ValueError):
        score_all(_inp(_peers()), as_of_t=2025.0, weights={k: 1.0 for k in ss.KEYS})


def test_sector_heat_only_for_tagged():
    rounds = _peers() + [_r("fin", 2024.5), _r("fin2", 2024.6)]
    inp = _inp(rounds, sectors={"fin": ["Fintech"], "fin2": ["Fintech"]})
    run = score_all(inp, as_of_t=2025.0, weights=clamp_weights({"sector_heat": 0.1}, sector_active=True))
    assert _comp(run.rows["fin"], "sector_heat")["raw"]["sector"] == "Fintech"
    assert not _comp(run.rows["peer1"], "sector_heat")["present"]


def test_possible_duplicates():
    assert ss.possible_duplicates(["baichuan", "baichuanai", "other"]) == {"baichuan", "baichuanai"}


# ---------------------------------------------------------------- funds and founders
def test_fund_scores_queried_only():
    rounds = [_r(f"c{i}", 2024.5, leads=("alpha",), parts=("beta",)) for i in range(6)]
    out = fund_scores(_inp(rounds, fund_keys={"alpha", "beta"}), as_of_t=2025.0)
    assert out["alpha"]["queried"] and out["alpha"]["score"] is not None
    assert out["alpha"]["components"][1]["raw"] == {"led": 6, "of": 6}
    assert out["beta"]["components"][1]["raw"] == {"led": 0, "of": 6}
    assert out["alpha"]["score"] > out["beta"]["score"]
    out2 = fund_scores(_inp(rounds, fund_keys={"alpha"}), as_of_t=2025.0)
    assert out2["beta"]["score"] is None and "co-investor" in out2["beta"]["score_reason"]


def test_founder_not_enough_data_below_two_facts():
    thin = {"name": "A B", "ckeys": ["x"], "roles": [{"since": None}], "founded": [], "prior_exits": []}
    e = founder_evidence(thin)
    assert e["score"] is None and e["score_reason"] == "Not enough data (0 of 4)"
    rich = {"name": "A Smith", "ckeys": ["x"], "roles": [{"since": "2015"}],
            "founded": [{"org": "Old Co", "org_id": "u-1"}], "prior_exits": []}
    e2 = founder_evidence(rich, cohort_rows=[{"founder": "Anna Smith"}])
    assert e2["k"] == 3 and e2["score"] == 75 and e2["missing"] == ["prior exit"]


def test_founder_own_company_with_suffix_is_not_an_earlier_company():
    f = {"name": "S Arvela", "ckeys": ["iprallytechnologies"], "roles": [{"since": "2024-05-21"}],
         "founded": [{"org": "IPRally", "org_id": "u-1"}], "prior_exits": []}
    e = founder_evidence(f)
    assert "earlier Cala company" not in e["facts"] and e["score"] is None


# ---------------------------------------------------------------- honesty
def _strings(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for v in o.values():
            yield from _strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from _strings(v)


def test_no_dashes_in_user_visible_strings():
    src = Path(ss.__file__).read_text()
    assert not DASH.search(src)
    run = score_all(_inp(_peers() + [_r("onefact", 2024.5, amount=None)]), as_of_t=2025.0, weights=clamp_weights())
    for s in _strings([run.rows[k] for k in run.rows]):
        assert not DASH.search(s), s
    for name in ("signal_weights.json", "signal_backtest.json"):
        p = Path(ss.__file__).with_name(name)
        if p.exists():
            assert not DASH.search(p.read_text()), name


def test_backtest_json_has_verdict_and_held_out():
    p = Path(ss.__file__).with_name("signal_backtest.json")
    if not p.exists():
        pytest.skip("run signal_backtest.py first")
    d = json.loads(p.read_text())
    assert d["verdict"]["verdict"] in ("pass", "weak", "fail")
    for y in ("next_round_24m", "graduate_b_plus_36m"):
        assert d["results"][y]["held_out"]["signal"]["n"] > 0


if __name__ == "__main__":
    import minitest
    minitest.main(globals())
