"""Tests for merge.py (run: cd app && python3 test_merge.py, or python3 -m pytest test_merge.py)."""
from merge import Builder


def _fund(name, *rows):
    return {"name": name, "queries": [{"q": "test", "rows": list(rows)}]}


def _row(company, **kw):
    return {"company": company, "country": "Finland", "date": "Mar 2024", "round_type": "Series A", "amount": "$10M", **kw}


def test_queried_fund_not_added_when_row_lists_others():
    b = Builder()
    b.add_fund_record(_fund("Tencent", _row("Uzum", lead_investor="FinSight Ventures",
                                                participating_investors="FinSight Ventures, Xanara", tencent_led="No")))
    assert b.rounds[0]["leads"] == ["finsight"]
    assert "tencent" not in b.rounds[0]["participants"]


def test_queried_fund_added_when_named_flagged_or_list_open():
    b = Builder()
    b.add_fund_record(_fund("Tencent",
                            _row("A", lead_investor="X Capital", participating_investors="Tencent (details limited)", tencent_led="No"),
                            _row("B", lead_investor="X Capital", tencent_led="No"),
                            _row("C", lead_investor="X Capital", co_investors="Y Ventures + others", tencent_led="No"),
                            _row("D", lead_investor=None, tencent_led="Yes")))
    by = {r["company"]: r for r in b.rounds}
    assert "tencent" in by["A"]["participants"]
    assert "tencent" in by["B"]["participants"]  # no participant list: nothing contradicts the fund's own answer
    assert "tencent" in by["C"]["participants"]  # the list says it is partial
    assert by["D"]["leads"] == ["tencent"]


def test_fold_same_round_dated_twice_and_bare_echo():
    b = Builder()
    b.add_fund_record(_fund("Lifeline Ventures",
                            _row("ConfidentialMind", date="Nov 2023", round_type="Seed", amount="€3.5M",
                                 lead_investor="Lifeline Ventures & D11Z Ventures", lifeline_led="Co-led"),
                            _row("Confidentialmind", date="Apr 2026", round_type="Seed", amount="€3.5M (~$4M)",
                                 lead_investor="Lifeline Ventures, D11Z Ventures",
                                 participating_investors="Innovestor, Sofokus", lifeline_led="Yes"),
                            _row("Reduciner", date="May 2026", round_type="Seed", amount="€3.6M",
                                 lead_investor="Voima Ventures, Lifeline Ventures (co-led)", lifeline_led="Co-led")))
    b.add_fund_record(_fund("Voima Ventures",
                            _row("Reduciner", date="May 5, 2026", round_type="Series A", amount=None, lead_investor=None,
                                 co_investors="Lifeline Ventures + others", voima_led="No")))
    snap = b.snapshot(set())
    assert snap["stats"]["folded_duplicates"] == 2
    cm = [r for r in snap["rounds"] if r["ckey"] == "confidentialmind"]
    assert len(cm) == 1 and (cm[0]["year"], cm[0]["month"]) == (2026, 4) and len(cm[0]["sources"]) == 2
    red = [r for r in snap["rounds"] if r["ckey"] == "reduciner"]
    assert len(red) == 1 and red[0]["stage"] == "seed"
    assert [r["id"] for r in snap["rounds"]] == list(range(len(snap["rounds"])))


def test_different_rounds_with_same_lead_are_kept():
    b = Builder()
    b.add_fund_record(_fund("Lifeline Ventures",
                            _row("Vensum", date="Nov 2019", round_type="Seed", amount="€1M", lifeline_led="Yes"),
                            _row("Vensum", date="May 2023", round_type="Seed", amount="€3.8M", lifeline_led="Yes")))
    assert len(b.snapshot(set())["rounds"]) == 2


def test_accelerator_and_pipe_rounds_are_not_led():
    b = Builder()
    b.add(company="Stilta", country="SE", when=(2026, 1), type_="Accelerator / Incubator", amount="~$500K",
          leads=["Y Combinator"], parts=[], path="company_first", query="q",
          raw={"round_type": "Accelerator / Incubator"})
    b.add(company="Viscaria", country="SE", when=(2026, 6), type_="PIPE (Directed Share Issue)", amount="SEK 1.7 billion",
          leads=["InfraVia"], parts=["Swedbank Robur"], path="investor_first", query="q",
          raw={"round_type": "PIPE (Directed Share Issue)"})
    b.add(company="Value.Space", country="FI", when=(2023, 3), type_="Seed", amount="€1M", leads=["Specialist VC"],
          parts=[], path="company_first", query="q", raw={"round_type": "Seed"})
    snap = b.snapshot(set())
    by = {r["company"]: r for r in snap["rounds"]}
    assert by["Stilta"]["leads"] == [] and "y combinator" in by["Stilta"]["participants"] and by["Stilta"]["not_led"]
    assert by["Viscaria"]["leads"] == [] and by["Viscaria"]["named_leads"] == ["infravia"]
    assert by["Value.Space"]["leads"] == ["specialist"] and not by["Value.Space"].get("not_led")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
