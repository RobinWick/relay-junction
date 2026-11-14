"""Tests for hunt_lead (run: python3 app/test_hunt_lead.py, or pytest). Point-in-time: rounds after as_of never matter."""
try:
    import pytest  # noqa: F401
except ImportError:
    import minitest as pytest  # noqa: F401

from hunt_lead import KEYS, lead_signals

_id = iter(range(10 ** 6))


def _r(ck, t, stage="seed", amount=1.0, leads=("alpha",), parts=(), **kw):
    return {"id": next(_id), "ckey": ck, "company": ck, "country": "Finland", "t": t, "year": int(t), "month": 6,
            "stage": stage, "amount_eur_m": amount, "leads": list(leads), "participants": list(parts),
            "query_path": "company_first", **kw}


def _world():
    rs = [_r(f"o{i}", 2015 + i * 0.3, amount=1.0 + i * 0.1) for i in range(6)]  # alpha leads seed rounds
    rs += [_r(f"q{i}", 2016 + i * 0.3, stage="series a", amount=5.0, leads=("gamma",)) for i in range(4)]
    rs += [_r("acme", 2017.0, amount=1.0, leads=("gamma",), parts=("alpha",)),
           _r("acme", 2018.5, amount=4.0, leads=("alpha",))]
    return rs


def _future():
    """Rounds dated after as_of that would flip every signal if they leaked in."""
    return [_r("acme", 2019.5, stage="series a", amount=50.0, leads=("delta",)),
            _r("z1", 2019.2, amount=0.1, leads=("alpha",)), _r("z2", 2019.3, stage="series b", leads=("alpha",)),
            _r("z3", 2019.4, amount=100.0, leads=("gamma",)), _r("z4", 2019.6, amount=100.0, leads=("gamma",))]


def test_future_rounds_never_change_values():
    as_of = 2019.0
    base = lead_signals(_world(), as_of)
    leaked = lead_signals(_world() + _future(), as_of)
    assert base == leaked
    assert set(base["acme"]) == set(KEYS)


def test_values_on_known_case():
    v = lead_signals(_world(), 2019.0)["acme"]
    assert v["insider_lead"] == 1.0 and v["new_outside_lead"] == 0.0  # alpha joined the 2017 raise
    assert v["lead_stretch"] == 1.0  # 4.0 above alpha's p75 seed lead size
    assert v["lead_stage_stretch"] == 0.0  # alpha has led seed before
    assert v["lead_upgrade"] == 0.0  # alpha median about 1.25 vs gamma's 5.0


def test_disputed_and_programme_rounds_ignored():
    rs = _world() + [_r("acme", 2018.8, leads=("delta",), disputed=True), _r("acme", 2018.9, not_led="programme")]
    assert lead_signals(rs, 2019.0)["acme"] == lead_signals(_world(), 2019.0)["acme"]


def test_first_round_company_has_no_insider_value():
    v = lead_signals([_r("solo", 2018.0)], 2019.0)["solo"]
    assert v["insider_lead"] is None and v["new_outside_lead"] is None


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
