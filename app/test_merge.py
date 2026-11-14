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


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
