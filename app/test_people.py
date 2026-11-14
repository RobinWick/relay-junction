"""Tests for people.py on saved Cala probe responses (no network) and small hand-made edges (run: cd app && python3 test_people.py)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import people as pp

PROBE = Path(__file__).resolve().parents[2] / "research" / "patterns" / "probe"
AIVEN_ID = "72941c0f-0508-4c50-8a5f-1eb87ad0df1e"


def _probe(name: str) -> dict:
    raw = json.loads((PROBE / name).read_text())
    return {"response": raw["response"], "fetched": "2026-11-14", "body": raw.get("body")}


def _person(edges: list[dict], pid: str = "p1", name: str = "Test Person", founded: list[dict] | None = None) -> dict:
    return {"response": {"id": pid, "name": name, "relationships": {"outgoing": {
        "WORKS_AT": edges, "FOUNDED": founded or []}}}, "fetched": "2026-11-14"}


def _job(org: str, role: str, since: str | None = None, until: str | None = None, oid: str | None = None) -> dict:
    props = {"role": role, "sources": [{"name": "example.org", "document": "https://example.org/x", "date": "2026-01-01"}]}
    if since:
        props["valid_since"] = since
    if until:
        props["valid_until"] = until
    return {"id": oid or f"id-{org}", "name": org, "entity_type": "Company", "properties": props}


def test_year_of():
    assert pp.year_of("2015-07-01") == 2015.5
    assert pp.year_of("2010") == 2010
    assert pp.year_of(None) is None
    assert pp.year_of("unknown") is None


def test_levels_highest_match_wins():
    assert pp.level("Summer Intern") == 0
    assert pp.level("Business Analyst") == 0
    assert pp.level("Software Engineer") == 1
    assert pp.level("Senior Software Engineer") == 2
    assert pp.level("Engagement Manager") == 2
    assert pp.level("Head of Growth") == 3
    assert pp.level("VP Product & Co-founder") == 4
    assert pp.level("Chief Product Officer") == 4
    assert pp.level("Ninja") is None


def test_tags_match_whole_words():
    assert pp.tags_for("McKinsey & Company") == ["consulting"]
    assert pp.tags_for("Supercell Oy") == ["nordic_unicorn"]
    assert "research" in pp.tags_for("Aalto University")
    assert pp.tags_for("Bainbridge Labs") == []  # 'bain' must not match inside a word
    assert pp.tags_for("Kingston Ltd") == []


def test_founders_of_aiven_from_probe():
    founders = pp.founder_candidates(_probe("p06_project_aiven_people.json")["response"])
    assert len(founders) >= 4
    assert all(re.fullmatch(r"[0-9a-f-]{36}", pid) for pid, _ in founders)


def test_valtonen_timeline_and_prior_company():
    raw = _probe("p08_project_person_valtonen.json")
    rec = pp.person_record(raw, ["aiven"], {"aiven": AIVEN_ID}, {}, 1)
    orgs = [r["org"] for r in rec["roles"]]
    assert orgs[0] == "Ohmu Ltd"  # oldest dated role first
    assert rec["roles"][0]["level"] == 4 and rec["roles"][0]["open"]
    assert rec["prior_founder"]["value"] is True
    assert rec["prior_founder"]["companies"][0]["org"] == "Ohmu Ltd"
    assert rec["metrics"]["years_before_company"] == 5.5  # 2010-01 to 2015-07
    assert rec["source"]["entity_id"] and rec["source"]["fetched"] == "2026-11-14"
    assert any("no start date" in g for g in rec["gaps"])  # CPO edge has only an end date
    assert not any("name collision" in g for g in rec["gaps"])  # links back to Aiven


def test_tenure_and_level_ups():
    raw = _person([
        _job("McKinsey & Company", "Business Analyst", "2012-09-01", "2014-09-01"),
        _job("McKinsey & Company", "Engagement Manager", "2014-09-01", "2016-03-01"),
        _job("Wolt", "Head of Operations", "2016-03-01", "2019-03-01"),
        _job("NewCo", "Co-founder & CEO", "2019-03-01", oid="newco"),
    ])
    rec = pp.person_record(raw, ["newco"], {"newco": "newco"}, {}, 1)
    m = rec["metrics"]
    assert m["avg_tenure_n"] == 3 and m["avg_tenure_years"] == 2.2
    assert m["level_ups"] == 3 and m["level_downs"] == 0
    assert m["dated_span_years"] == 6.5 and m["level_ups_per_year"] == 0.46
    assert m["years_before_company"] == 6.5
    assert m["employers"] == 3
    assert rec["tags"] == ["consulting", "nordic_unicorn"]
    assert [s["dir"] for s in rec["level_steps"]] == ["up", "up", "up"]


def test_home_company_gives_no_tag_and_orgs_dedupe():
    raw = _person([_job("Sana Labs", "Engineer", "2016-01-01", "2019-12-31", oid="s1"),
                   _job("Sana Labs AB", "Engineer", oid="s2"),
                   _job("Organización Europea para la Investigación Nuclear (CERN)", "Physicist", oid="c1"),
                   _job("CERN", "Physicist", oid="c2"),
                   _job("Lovable", "Co-Founder & CEO", "2023-11-01", oid="lov")])
    rec = pp.person_record(raw, ["lovable"], {"lovable": "lov"}, {}, 1, ["lovable"])
    assert "nordic_unicorn" not in rec["tags"]  # Lovable is the home company, not a background
    assert rec["metrics"]["employers"] == 3  # Sana Labs, CERN, Lovable
    assert rec["metrics"]["years_before_company"] == 7.8


def test_merged_roles_keep_the_title_and_counts_agree():
    """Bug 5: duplicate Cala entities collapse to one row that keeps its title; counts and gaps use merged rows."""
    raw = _person([_job("Sana Labs", "First employee and Engineer", "2016-01-01", "2019-12-31", oid="s1"),
                   _job("Lovable", "Co-Founder & CEO", "2023-11-01", oid="lov"),
                   _job("CERN", "", oid="c2"),
                   _job("Lovable", "CEO", oid="lov2"),
                   _job("Organización Europea para la Investigación Nuclear (CERN)", "Particle Physicist", oid="c1"),
                   _job("Sana Labs AB", "", oid="s2"),
                   _job("Aiven", "CPO", until="2024-01-01", oid="a1"), _job("Aiven", "Engineer", "2015-01-01", oid="a2")])
    rec = pp.person_record(raw, ["lovable"], {"lovable": "lov"}, {}, 1, ["lovable"])
    rows = [(r["org"], r["role"]) for r in rec["roles"]]
    assert ("Organización Europea para la Investigación Nuclear (CERN)", "Particle Physicist") in rows
    assert ("CERN", "") not in rows and ("Sana Labs AB", "") not in rows and ("Lovable", "CEO") not in rows
    assert ("Aiven", "CPO") in rows  # a different title at the same org is a different role
    m = rec["metrics"]
    assert m["roles"] == len(rows) == 5 and m["roles_outside_company"] == 4 <= m["roles"]
    assert "2 of 5 roles have no start date" in rec["gaps"]
    assert "2 dated roles have no end date (current, or end unknown)" in rec["gaps"]
    one = pp.person_record(_person([_job("A", "Engineer", "2020-01-01"), _job("B", "")]), [], {}, {}, 1)
    assert "1 of 2 roles has no start date" in one["gaps"]
    assert "1 dated role has no end date (current, or end unknown)" in one["gaps"]


def test_per_year_needs_a_year_of_span():
    raw = _person([_job("A", "Engineer", "2020-01-01"), _job("B", "Director", "2020-06-01")])
    rec = pp.person_record(raw, [], {}, {}, 1)
    assert rec["metrics"]["level_ups"] == 1
    assert rec["metrics"]["level_ups_per_year"] is None


def test_missing_link_and_collision_sources_are_gaps():
    job = _job("Some FC", "Midfielder", "2001-01-01")
    job["properties"]["sources"] = [{"name": "transfermarkt", "document": "https://www.transfermarkt.com/x", "date": "2026"}]
    rec = pp.person_record(_person([job]), ["acme"], {"acme": "acme-id"}, {}, 2)
    joined = " ".join(rec["gaps"])
    assert "name collision" in joined and "transfermarkt" in joined and "2 Cala person entities" in joined


def test_prior_exit_from_exit_cache():
    raw = _person([_job("NewCo", "Founder", "2021-01-01", oid="newco")],
                  founded=[{"id": "old", "name": "OldCo", "entity_type": "Company", "properties": {}}])
    exits = {"old": {"response": {"relationships": {"outgoing": {"PARTICIPATES_IN_CORPORATE_EVENT": [
        {"id": "ev", "name": "MNA_COMPLETED", "entity_type": "CorporateEvent",
         "properties": {"role": "TARGET", "event_date": "2019-05-01", "sources": []}},
        {"id": "ev2", "name": "MNA_COMPLETED", "entity_type": "CorporateEvent",
         "properties": {"role": "ACQUIRER", "event_date": "2020-05-01", "sources": []}}]}}}}}
    rec = pp.person_record(raw, ["newco"], {"newco": "newco"}, exits, 1)
    assert [e["date"] for e in rec["prior_exits"]] == ["2019-05-01"]
    assert rec["prior_exit_checked"] == ["OldCo"]
    rec = pp.person_record(raw, ["newco"], {"newco": "newco"}, {"old": {"response": {}}}, 1)
    assert rec["prior_exits"] == [] and any("not proof" in g for g in rec["gaps"])


def test_cohort_splits_worked_at_from_funded_by():
    coh = pp.cohort_record("Supercell", _probe("q02_founder_prevjob.json"), {})
    rel = {r["company"]: r["relation"] for r in coh["rows"]}
    assert rel["Redly Games"] == "funded_by"
    assert rel["Shipyard Games"] == "funded_by"
    assert rel["Antihero Studios"] == "listed_only"  # row text names Sisu and the government, never Supercell
    assert coh["n"] == 4 and coh["n_funded_by"] == 2


def test_cohort_reads_stated_prior_jobs():
    row = {"name": "Ajaib", "founders": "Yada Piyajomkwan (McKinsey Bangkok 2014–17)", "year_founded": 2018}
    assert pp.cohort_relation("McKinsey", row)[0] == "worked_at_stated"
    row = {"company": "Anyfin", "founders": "Mikael Hussain (former VP Credit at Klarna), Filip Polhem"}
    assert pp.cohort_relation("Klarna", row)[0] == "worked_at_stated"
    row = {"name": "Phantom Gamelabs", "founders": "Former developers from Zynga, Rovio, and Kopla Games",
           "funding": "Investment from Supercell"}
    assert pp.cohort_relation("Rovio", row)[0] == "worked_at_stated"
    assert pp.cohort_relation("Supercell", row)[0] == "funded_by"
    row = {"company": "Skalar", "founders": "Founder who previously sold a startup to Klarna for €110M"}
    assert pp.cohort_relation("Klarna", row)[0] == "sold_to"
    assert pp.cohort_relation("McKinsey", {"name": "Kavak", "founders": "Carlos Julio Garcia"})[0] == "listed_only"


def _walk_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _walk_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_keys(v)


def test_build_has_no_score_or_rank_and_sources_on_every_person():
    persons = {"p1": _person([_job("Google", "Engineer", "2015-01-01", "2018-01-01"),
                              _job("X", "Founder", "2018-01-01", oid="xid")]),
               "p2": _person([_job("X", "Co-founder", "2019-01-01", oid="xid")], pid="p2", name="Other Person")}
    company = {"response": {"id": "xid", "name": "X", "relationships": {"incoming": {"FOUNDED": [
        {"id": "p1", "name": "Test Person", "entity_type": "Person"},
        {"id": "p2", "name": "Other Person", "entity_type": "Person"}]}}}, "fetched": "2026-11-14"}
    rounds = [{"ckey": "x", "company": "X", "country": "Finland", "t": 2024.1, "year": 2024, "month": 2,
               "stage": "seed", "amount_eur_m": 2.0, "leads": ["maki"]}]
    out = pp.build({"x": company}, persons, {}, {}, {"c:x": "xid"}, rounds, calls_used=3)
    keys = {k.lower() for k in _walk_keys(out)}
    assert not any("score" in k or "rank" in k for k in keys - {"rank"})  # 'rank' only as a source's own rank field
    assert all(p["source"]["entity_id"] and p["source"]["fetched"] for p in out["people"])
    assert [p["name"] for p in out["people"]] == ["Other Person", "Test Person"]  # alphabetical, not by metric
    big = next(x for x in out["patterns"] if x["label"] == "Worked at: Big tech")
    assert big["count"] == 1 and big["n"] == 1  # p2 has no record outside X, so is not counted as 'no'
    assert out["companies"][0]["founder_source"] == "FOUNDED"
    assert out["companies"][0]["rounds"][0]["leads"] == ["maki"]


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        fn()
        print("ok", name)
    print(f"{len(tests)} people tests passed")
