"""Tests for hunt_timing (run: python3 app/test_hunt_timing.py, or pytest). Proves point-in-time: rounds dated on or
after as_of never change any value."""
import copy
import json
import random
from pathlib import Path

try:
    import pytest
except ImportError:  # run without pytest
    import minitest as pytest

from hunt_timing import KEYS, timing_signals

_id = iter(range(10 ** 6))


def _r(ck, t, stage="seed", amount=1.0, leads=("alpha",), parts=("beta",)):
    return {"id": next(_id), "ckey": ck, "company": ck.title(), "country": "Finland", "t": t, "year": int(t), "month": 6,
            "stage": stage, "amount_eur_m": amount, "leads": list(leads), "participants": list(parts),
            "query_path": "company_first", "sources": [{"path": "company_first", "row": {"date": f"Jun {int(t)}"}}]}


def _world(n=25):
    rs = []
    for i in range(n):
        rs.append(_r(f"c{i}", 2017.4 + (i % 5) * 0.1, "seed", 1 + i * 0.2, parts=tuple(f"p{j}" for j in range(i % 4))))
        rs.append(_r(f"c{i}", 2019.0 + (i % 7) * 0.2, "series a", 3 + i * 0.5, parts=tuple(f"p{j}" for j in range(i % 6))))
        if i < 8:  # gives the series a stage enough gaps for a median
            rs.append(_r(f"c{i}", 2020.6, "series b", 20 + i))
    return rs


def test_future_round_never_changes_values():
    base = _world()
    as_of = 2021.0
    before = timing_signals(base, as_of)
    future = [_r("c3", 2021.0, "series b", 50.0, parts=("x", "y", "z")), _r("c4", 2022.5, "series b", 80.0),
              _r("newco", 2021.3, "seed", 9.0)]
    after = timing_signals(base + future, as_of)
    assert after == before
    assert "newco" not in after


def test_changing_a_future_round_changes_nothing():
    base = _world() + [_r("c1", 2023.0, "series b", 10.0)]
    a = timing_signals(base, 2021.0)
    mod = copy.deepcopy(base)
    mod[-1].update(amount_eur_m=999.0, t=2021.01, participants=["q"] * 1)
    assert timing_signals(mod, 2021.0) == a


def test_values_present_and_sane():
    v = timing_signals(_world(), 2021.0)["c10"]
    assert set(v) == set(KEYS)
    assert v["overdue"] is not None and v["overdue"] > 0
    assert v["syndicate_growth"] is not None
    for k in ("cadence_vs_cohort", "step_up_vs_peers", "recency_x_size"):
        assert v[k] is None or 0.0 <= v[k] <= 1.0


def test_point_in_time_on_real_snapshot():
    snap = Path(__file__).resolve().parents[2] / "cala" / "data" / "snapshot.json"
    if not snap.exists():
        return
    rounds = json.loads(snap.read_text())["rounds"]
    as_of = 2022.0
    past = [r for r in rounds if r["t"] < as_of]
    assert timing_signals(rounds, as_of) == timing_signals(past, as_of)
    shuffled = past[:]
    random.Random(7).shuffle(shuffled)
    assert timing_signals(shuffled, as_of) == timing_signals(past, as_of)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
