"""Tests for hunt_graph (run: python3 app/test_hunt_graph.py, or pytest)."""
import copy

try:
    import pytest  # noqa: F401
except ImportError:  # run without pytest
    import minitest as pytest  # noqa: F401

import hunt_graph as hg

_id = iter(range(10 ** 6))


def _r(ck, t, stage="seed", amount=1.0, leads=("alpha",), parts=("beta",)):
    return {"id": next(_id), "ckey": ck, "company": ck.title(), "country": "Finland", "t": t, "year": int(t),
            "month": 6, "stage": stage, "amount_eur_m": amount, "leads": list(leads), "participants": list(parts),
            "query_path": "company_first", "sources": []}


def _world():
    rs = []
    # five funds with early-bet track records: "alpha" companies tend to raise again and reach B
    for i in range(6):
        ck = f"a{i}"
        rs += [_r(ck, 2016.5 + 0.1 * i, "seed", 1.0, ("alpha",), ("gamma",)),
               _r(ck, 2017.6 + 0.1 * i, "series a", 5.0, ("delta",), ("alpha",)),
               _r(ck, 2018.9 + 0.1 * i, "series b", 20.0, ("epsilon",), ("alpha",))]
    for i in range(6):
        rs.append(_r(f"b{i}", 2016.4 + 0.1 * i, "seed", 0.5, ("beta",), ("gamma",)))
    rs += [_r("target", 2019.2, "pre-seed", 0.3, ("alpha",), ()),
           _r("target", 2020.4, "seed", 2.0, ("beta",), ("zeta", "eta"))]
    return rs


AS_OF = 2021.0


def test_future_round_never_changes_any_value():
    base = _world()
    before = hg.compute_all(base, AS_OF)
    future = copy.deepcopy(base) + [
        _r("target", AS_OF + 0.1, "series a", 30.0, ("omega",), ("alpha", "beta")),   # target raises after as_of
        _r("a0", AS_OF + 0.5, "series c", 90.0, ("zeta",), ("eta",)),                 # new co-investment edge
        _r("newco", AS_OF, "seed", 1.0, ("alpha",), ("zeta",)),                        # dated exactly at as_of
    ]
    after = hg.compute_all(future, AS_OF)
    assert before == after


def test_values_exist_and_are_in_range():
    v = hg.compute_all(_world(), AS_OF)["target"]
    assert v["syndicate_pagerank"] is not None and v["syndicate_pagerank"] > 0
    assert 0.0 <= v["syndicate_novelty"] <= 1.0
    for k in ("smart_money_early", "contrarian"):
        assert v[k] in (None, 0.0, 1.0)


def test_novelty_counts_only_earlier_coinvestment():
    rs = _world()
    # zeta + eta never co-invested before target's seed round; beta + zeta neither -> all 3 pairs new
    assert hg.compute_all(rs, AS_OF)["target"]["syndicate_novelty"] == 1.0
    rs.append(_r("other", 2018.0, "seed", 1.0, ("zeta",), ("eta",)))
    assert abs(hg.compute_all(rs, AS_OF)["target"]["syndicate_novelty"] - 2 / 3) < 1e-9


def test_own_company_excluded_from_track_record():
    rs = [_r(f"c{i}", 2015.5 + 0.1 * i, "seed", 1.0, ("solo",), ()) for i in range(3)]
    rs += [_r(f"c{i}", 2016.5 + 0.1 * i, "series a", 3.0, ("other",), ()) for i in range(3)]
    track = hg.early_track(hg.by_company(hg.equity_before(rs, 2020.0)), 2020.0, 2.0, late_only=False)
    assert hg.rate_excluding(track, "solo", "c0") == (2, 2)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
