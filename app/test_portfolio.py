"""Tests for engine.portfolio (run: cd app && python3 -m pytest test_portfolio.py)."""
from engine import portfolio, weak_name


def _r(rid, company, t, leads=(), participants=(), stage="seed", month=1, year=2025):
    return {"id": rid, "company": company, "t": t, "leads": list(leads), "participants": list(participants),
            "stage": stage, "month": month, "year": year}


def test_one_entry_per_company_led_beats_joined():
    rounds = [_r(1, "Sono Oy", 2025.1, participants=["maki"]),
              _r(2, "Sono", 2024.5, leads=["maki"]),
              _r(3, "Other", 2026.0, leads=["x"])]
    out = portfolio(rounds, "maki")
    assert len(out) == 1
    assert out[0] == {"company": "Sono", "ckey": "sono", "stage": "Seed", "date": "Jan 2025", "t": 2024.5,
                      "led": True, "rid": 2, "weak": True}


def test_newest_first_and_capped():
    rounds = [_r(i, f"Co {i}", 2020 + i / 10, participants=["f"]) for i in range(10)]
    out = portfolio(rounds, "f", cap=3)
    assert [p["rid"] for p in out] == [9, 8, 7]
    assert all(not p["led"] for p in out)


def test_company_key_drops_legal_suffix():
    out = portfolio([_r(1, "Acme Health (Finland) Oy", 2025.0, leads=["f"])], "f")
    assert out[0]["ckey"] == "acmehealth"


def test_weak_names_short_or_ordinary_words():
    common = frozenset({"junction", "garage"})
    assert weak_name("sono", common)  # 5 characters or fewer
    assert weak_name("junction", common)
    assert not weak_name("kinedb", common)
    out = portfolio([_r(1, "Junction", 2025.0, participants=["f"]), _r(2, "KineDB", 2025.0, leads=["f"])], "f",
                    common=common)
    assert {p["ckey"]: p["weak"] for p in out} == {"junction": True, "kinedb": False}
