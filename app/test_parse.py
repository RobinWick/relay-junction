"""Tests for parse.parse_list on a tiny made-up snapshot (run: cd app && python3 test_parse.py)."""
from engine import Snapshot
from parse import parse_list

FUNDS = {"creandum": "Creandum", "northzone": "Northzone", "inventure": "Inventure", "speedinvest": "Speedinvest",
         "lifeline": "Lifeline Ventures", "maki": "Maki.vc", "sunstone": "Sunstone Capital", "thuja": "Thuja Capital",
         "capital": "Capital", "felix": "Felix Capital", "fund": "Fund", "plug and play": "Plug and Play",
         "superhero": "Superhero Capital", "icebreaker": "Icebreaker.vc", "johan brenner": "Johan Brenner"}


def _snap() -> Snapshot:
    rounds = []
    for key in FUNDS:
        for i in range(3):
            rounds.append({"id": len(rounds), "company": f"Co {key} {i}", "ckey": f"co{key}{i}", "t": 2025.0, "year": 2025,
                           "month": 1, "stage": "seed", "leads": [key], "participants": [], "sources": []})
    return Snapshot.from_dict({"rounds": rounds, "investor_names": FUNDS, "fund_keys": [], "stats": {},
                               "retrieved": "", "version": "t"})


def keys(text: str, **kw) -> list[str]:
    return [m["key"] for m in parse_list(_snap(), text, **kw)["matched"]]


def test_every_fund_on_a_line_counts():
    assert keys("Creandum, Northzone, Inventure, Speedinvest") == ["creandum", "northzone", "inventure", "speedinvest"]
    assert keys("Creandum / Northzone") == ["creandum", "northzone"]
    assert keys("Creandum and Northzone, then Lifeline & Inventure") == ["creandum", "northzone", "lifeline", "inventure"]
    assert keys("Creandum\tSeed\tBooked") == ["creandum"]
    assert keys("creandum; northzone") == ["creandum", "northzone"]
    assert keys("Plug and Play") == ["plug and play"]


def test_day_names_and_venue_words_do_not_eat_fund_names():
    assert keys("Sunstone Capital\nThuja Capital") == ["sunstone", "thuja"]
    assert keys("Meeting Maki.vc") == ["maki"]
    assert keys("Wed 10:30  Maki.vc  (Table 12)") == ["maki"]
    assert keys("Thu 13 Nov 10:00 Table 42 Speedinvest") == ["speedinvest"]


def test_fund_vehicles_match_their_fund():
    assert keys("Lifeline Ventures Fund IV\nMaki.vc Fund II\nSuperhero Capital III") == ["lifeline", "maki", "superhero"]
    assert keys("Lifeline Ventures GP Oy") == ["lifeline"]
    assert keys("Inventure Fund I Ky") == ["inventure"]


def test_first_names_and_headers_do_not_take_a_line():
    assert keys("Felix - Creandum") == ["creandum"]
    assert keys("Johan Brenner (Creandum)") == ["creandum"]
    assert keys("fund,partner,city,stage\nLifeline Ventures,Timo,Helsinki,Seed") == ["lifeline"]
    assert keys("Dinner with Felix and Robin") == []
    assert keys("Felix") == ["felix"]  # a name alone on its line is what was typed


def test_skipped_lines_are_counted():
    text = "\n".join(["Creandum", "Northzone", "Inventure", "Speedinvest", "Lifeline Ventures"])
    p = parse_list(_snap(), text, limit=3)
    assert [m["key"] for m in p["matched"]] == ["creandum", "northzone", "inventure"] and p["skipped_lines"] == 2
    long = "Creandum\n" + "x" * 7995 + "\nNorthzone\nInventure"
    p = parse_list(_snap(), long)
    assert [m["key"] for m in p["matched"]] == ["creandum"] and p["skipped_lines"] == 3


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
