"""Tests for receipt_exits (run: python3 app/test_receipt_exits.py, or pytest)."""
import json
from datetime import date

import receipt_exits as rx

TODAY = date(2026, 11, 14)
FUND = "fund-1"


def _src(url, day="2026-01-01"):
    return {"name": "n", "document": url, "date": day}


def _company(cid="co-1", events=(), investors=(), founded=None):
    props = {"name": {"value": "Co"}}
    if founded:
        props["founding_date"] = {"value": founded}
    return {"id": cid, "name": "Co", "properties": props,
            "relationships": {"outgoing": {"PARTICIPATES_IN_CORPORATE_EVENT": list(events)},
                              "incoming": {"INVESTED_IN": list(investors)}}}


def _edge(eid="ev-1", name="MNA_COMPLETED", role="TARGET", day="2018-09-20"):
    return {"id": eid, "name": name, "properties": {"role": role, "event_date": day,
                                                    "sources": [_src("https://buyer.example/press", day)]}}


def _event(eid="ev-1", value=2.2e9, units="USD", day="2018-09-20", acquirer="Buyer Inc"):
    props = {"event_date": {"value": day, "sources": [_src("https://buyer.example/press", day)]},
             "event_type": {"value": "MNA_COMPLETED"}}
    if value is not None:
        props["transaction_value"] = {"value": value, "sources": [_src("https://buyer.example/press", day)]}
        props["transaction_value_units"] = {"value": units}
    parts = [{"id": "buyer-1", "name": acquirer, "properties": {"role": "ACQUIRER"}},
             {"id": "co-1", "name": "Co", "properties": {"role": "TARGET"}}]
    return {"id": eid, "properties": props, "relationships": {"incoming": {"PARTICIPATES_IN_CORPORATE_EVENT": parts}}}


def _investor(day="2026-01-01"):
    return {"id": FUND, "name": "Fund", "properties": {"sources": [_src("https://fund.example/portfolio", day)]}}


def _build(company, events):
    return rx.build_fund("fund", "Fund", FUND, None, [{"company": company, "events": events}], TODAY)


def test_old_disclosed_exit_is_a_receipt_with_value_label_and_sources():
    out = _build(_company(events=[_edge()], investors=[_investor()]), [_event()])
    [r] = out["receipts"]
    assert r["acquirers"] == [{"name": "Buyer Inc", "entity": "buyer-1"}]
    assert r["value"] == {"status": "disclosed", "amount": 2.2e9, "currency": "USD",
                          "reported": {"value": 2.2e9, "units": "USD"}, "display": "2.2B USD",
                          "label": "deal value, not return"}
    assert r["vintage"]["rule"] == "exit_at_least_6y_ago"
    assert r["sources"][0]["url"] == "https://buyer.example/press"
    assert r["fund_link_sources"][0]["url"] == "https://fund.example/portfolio"
    assert out["undisclosed"] == []


def test_missing_value_goes_to_undisclosed_bucket():
    out = _build(_company(events=[_edge()], investors=[_investor()]), [_event(value=None)])
    assert out["receipts"] == []
    assert out["undisclosed"][0]["value"] == {"status": "undisclosed", "display": "undisclosed",
                                              "label": "deal value, not return"}


def test_acquirer_role_is_not_an_exit():
    out = _build(_company(events=[_edge(role="ACQUIRER")], investors=[_investor()]), [])
    assert out["receipts"] == [] and out["undisclosed"] == []
    assert out["excluded"][0]["reason"] == "no completed acquisition as target in Cala"


def test_funding_round_events_are_ignored():
    edge = _edge(name="FINANCING_RAISED_OR_FACILITY_ENTERED", role="ISSUER")
    out = _build(_company(events=[edge], investors=[_investor()]), [])
    assert out["receipts"] == [] and out["undisclosed"] == []


def test_recent_exit_without_old_investor_source_fails_vintage_gate():
    out = _build(_company(events=[_edge(day="2024-03-01")], investors=[_investor("2025-01-01")]),
                 [_event(day="2024-03-01")])
    assert out["receipts"] == []
    assert out["excluded"][0]["reason"] == "too recent for the 6 year gate"


def test_recent_exit_passes_with_investor_source_six_years_before_deal():
    out = _build(_company(events=[_edge(day="2024-03-01")], investors=[_investor("2017-05-01")]),
                 [_event(day="2024-03-01")])
    [r] = out["receipts"]
    assert r["vintage"]["rule"] == "investor_source_6y_before_exit"
    assert r["vintage"]["source"]["date"] == "2017-05-01"


def test_no_fund_link_means_no_receipt():
    out = _build(_company(events=[_edge()]), [_event()])
    assert out["receipts"] == []
    assert out["excluded"][0]["reason"] == "no Cala source links the fund to this company"


def test_fund_link_from_fund_side_edge_counts():
    fund_raw = {"relationships": {"outgoing": {"INVESTED_IN": [
        {"id": "co-1", "name": "Co", "properties": {"sources": [_src("https://fund.example/p")]}}]}}}
    out = rx.build_fund("fund", "Fund", FUND, fund_raw,
                        [{"company": _company(events=[_edge()]), "events": [_event()]}], TODAY)
    assert out["receipts"][0]["fund_link_sources"][0]["url"] == "https://fund.example/p"
    assert out["portfolio_edges_in_cala"] == 1


def test_deal_before_founding_is_dropped():
    out = _build(_company(events=[_edge()], investors=[_investor()], founded="2019-01-01"), [_event()])
    assert out["excluded"][0]["reason"] == "deal dated before the company was founded"


def test_fund_as_buyer_is_dropped():
    ev = _event()
    ev["relationships"]["incoming"]["PARTICIPATES_IN_CORPORATE_EVENT"][0]["id"] = FUND
    out = _build(_company(events=[_edge()], investors=[_investor()]), [ev])
    assert out["excluded"][0]["reason"] == "the fund itself is the buyer"


def test_receipts_sorted_by_date_not_value():
    company = _company(events=[_edge("a", day="2015-01-01"), _edge("b", day="2019-06-01")],
                       investors=[_investor()])
    out = _build(company, [_event("a", value=9e9, day="2015-01-01"), _event("b", value=1e6, day="2019-06-01")])
    assert [r["date"] for r in out["receipts"]] == ["2019-06-01", "2015-01-01"]


def test_output_has_no_rate_or_score_fields():
    out = _build(_company(events=[_edge()], investors=[_investor()]), [_event()])
    text = json.dumps(out).lower()
    for word in ("rate", "score", "probability", "lift", "percent"):
        assert f'"{word}' not in text


def test_units_in_millions_are_scaled_not_misread():
    for units in ("USD_millions", "USD million"):
        out = _build(_company(events=[_edge()], investors=[_investor()]), [_event(value=170.0, units=units)])
        v = out["receipts"][0]["value"]
        assert (v["amount"], v["currency"], v["display"]) == (170e6, "USD", "170M USD")
        assert v["reported"] == {"value": 170.0, "units": units}


def test_target_event_without_fetched_details_is_not_shown_as_undisclosed():
    out = _build(_company(events=[_edge()], investors=[_investor()]), [])
    assert out["receipts"] == [] and out["undisclosed"] == []
    assert out["excluded"][0]["reason"] == "deal details (value, buyer) not fetched from Cala"


def test_several_entity_ids_for_one_fund():
    company = _company(events=[_edge()], investors=[_investor()])
    out = rx.build_fund("fund", "Fund", ["other-id", FUND], None, [{"company": company, "events": [_event()]}], TODAY)
    assert len(out["receipts"]) == 1


def test_format_value():
    assert rx.format_value(2.2e9, "USD") == "2.2B USD"
    assert rx.format_value(35e6, "EUR") == "35M EUR"
    assert rx.format_value(1.25e6, None) == "1.2M"


def test_load_missing_file_is_empty(tmp_path):
    data = rx.load(tmp_path / "nope.json")
    assert data["funds"] == {} and rx.for_fund(data, "lifeline") is None


def test_cached_file_only_keys_by_canon_fund_keys():
    data = rx.load()
    if not data["funds"]:
        return
    import merge
    for key, fund in data["funds"].items():
        assert merge.canon(fund["name"]) == key
        for r in fund["receipts"] + fund["undisclosed"]:
            assert r["sources"] and r["fund_link_sources"] and r["vintage"]
            assert r["value"]["label"] == "deal value, not return"

if __name__ == "__main__":
    import minitest
    minitest.main(globals())
