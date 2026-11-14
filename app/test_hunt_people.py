"""Point-in-time tests for hunt_people.py. Run: cd relay/app && python3 -m pytest -q test_hunt_people.py (or python3 test_hunt_people.py)."""
from __future__ import annotations

import copy

import hunt_people as hp

AS_OF = 2021.0


def _src() -> hp.PeopleSources:
    P = hp.Person
    F = hp._fact
    persons = {
        "a": P("a", "Alice Founder", founded=[F("Target", "t1", None), F("Oldco", None, None)],
               roles=[F("Spotify", None, "2015-01-01", "Engineer"), F("Aalto University", None, "2016-01-01", "Researcher")]),
        "b": P("b", "Oscar Werner", founded=[F("Otherco", None, None)],
               roles=[F("Spotify", None, "2014-01-01", "PM"), F("Otherco", None, None, "CEO")]),
        "c": P("c", "Carol Late", founded=[F("Futureco", None, "2022-05-01")],
               roles=[F("Klarna", None, "2023-01-01", "Lead"), F("KTH", None, "2024-01-01", "Researcher")]),
    }
    return hp.PeopleSources(persons, {"target": {"a", "c"}, "otherco": {"b"}}, {"target": {"t1"}},
                            {"target": {"spotify"}}, tags_fetched_t=2026.9)


def _rounds() -> list[dict]:
    return [
        {"ckey": "target", "t": 2019.5, "leads": ["oscar werner"], "participants": []},
        {"ckey": "otherco", "t": 2018.2, "leads": [], "participants": []},
        {"ckey": "oldco", "t": 2017.0, "leads": [], "participants": []},
    ]


def _all(rounds, src, as_of=AS_OF):
    return {
        "prior_founder": hp.prior_founder(rounds, as_of, src),
        "research_alumni": hp.research_alumni(rounds, as_of, src),
        "unicorn_alumni": hp.unicorn_alumni(rounds, as_of, src),
        "unicorn_tags": hp.unicorn_alumni(rounds, as_of, src, mode="cohort_tags"),
        "mafia_density": hp.mafia_density(rounds, as_of, src),
        "angels": hp.named_operator_angels(rounds, as_of, src, {"oscar werner": "Oscar Werner", "carol late": "Carol Late"}),
    }


def test_expected_values():
    v = _all(_rounds(), _src())
    assert v["prior_founder"]["target"] == 1.0          # Alice founded Oldco, which has a 2017 round
    assert v["research_alumni"]["target"] == 1.0        # Aalto 2016; Carol's KTH 2024 must not count
    assert v["unicorn_alumni"]["target"] == 1.0         # Spotify 2015; Carol's Klarna 2023 must not count
    assert v["mafia_density"]["target"] == 1.0          # shares Spotify with Otherco's founder
    assert v["angels"]["target"] == 1.0                 # Oscar angel, CEO/founder of Otherco (round 2018)
    assert v["unicorn_tags"]["target"] is None          # tags fetched after as_of: not point-in-time


def test_round_after_as_of_never_changes_values():
    src = _src()
    base = _all(_rounds(), src)
    late = _rounds() + [
        {"ckey": "target", "t": 2021.3, "leads": ["carol late", "oscar werner"], "participants": []},
        {"ckey": "futureco", "t": 2022.6, "leads": [], "participants": []},
        {"ckey": "newco", "t": 2021.0, "leads": [], "participants": []},   # exactly at as_of: excluded
    ]
    assert _all(late, src) == base


def test_person_fact_dated_after_as_of_never_changes_values():
    src = _src()
    base = _all(_rounds(), src)
    src2 = copy.deepcopy(src)
    src2.persons["a"].roles.append(hp._fact("Google", None, "2023-01-01", "Engineer"))
    src2.persons["a"].founded.append(hp._fact("Spinoff", None, "2022-01-01"))
    assert _all(_rounds(), src2) == base


def test_real_snapshot_late_round_invariant():
    from signal_backtest import load_inputs
    inp, _ = load_inputs()
    src = hp.load_sources()
    as_of = 2022.0
    base = {k: f(inp.rounds, as_of, src) for k, f in hp.SIGNALS.items() if k != "named_operator_angels"}
    base["angels"] = hp.named_operator_angels(inp.rounds, as_of, src, inp.investor_names)
    extra = [dict(r, t=as_of + 0.5) for r in inp.rounds[:300]]
    extra += [{"ckey": "bitstechnology", "t": 2023.0, "leads": ["oscar werner"], "participants": []}]
    rounds = inp.rounds + extra
    after = {k: f(rounds, as_of, src) for k, f in hp.SIGNALS.items() if k != "named_operator_angels"}
    after["angels"] = hp.named_operator_angels(rounds, as_of, src, inp.investor_names)
    assert after == base


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
