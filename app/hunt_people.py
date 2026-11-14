"""People / cohort candidate signals for the Recount Signal hunt (family 'people').

Pure, point-in-time functions. Every signal takes the snapshot rounds, an as_of time (decimal year, e.g. 2021.0
for 1 Jan 2021) and a PeopleSources bundle, and returns {ckey: value or None}. None = no data (never imputed).

Point-in-time rules
  * Rounds: only rounds with t < as_of are read (disputed rounds dropped).
  * Person facts: a career role or FOUNDED edge counts only when its own `since` date is before as_of, OR (for
    FOUNDED edges to another company) when that company has a snapshot round dated before as_of, which dates the
    company's existence from our own record.
  * Undated person facts (most of them) do not count. Founder identity itself (who founded the company) is a
    2026-11-14 Cala fetch; it is treated as time-invariant, which is the one assumption these signals make.
  * Cohort tags (cala/expansion/cohort-tags.csv) are an undated Cala knowledge query fetched 2026-11-14. That is after
    every backtest as_of, so tag-based variants return None unless allow_lookahead=True (diagnostic only).

Sources (local only, 0 Cala calls): cala/expansion/people.json (211 persons), relay/app/people.json (22 founders),
cala/expansion/cohort-tags.csv (162 tagged companies).
"""
from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from merge import company_key
from signal_score import is_person

APP = Path(__file__).parent
ROOT = APP.parent.parent
EXP_PEOPLE = ROOT / "cala" / "expansion" / "people.json"
APP_PEOPLE = APP / "people.json"
COHORT_TAGS = ROOT / "cala" / "expansion" / "cohort-tags.csv"
SOURCES_FETCHED_T = 2026 + (11 - 1) / 12 + 13 / 365  # 2026-11-14, fetch date of every people/cohort source

RESEARCH = ["university", "yliopisto", "universitet", "universidad", "institute of technology", "vtt", "cern",
            "max planck", "research institute", "aalto", "kth", "dtu", "ntnu", "chalmers", "karolinska",
            "investigación nuclear", "fraunhofer", "eth zurich", "epfl"]
UNICORN_BIGTECH = ["supercell", "rovio", "wolt", "spotify", "klarna", "skype", "king.com", "king digital", "mojang",
                   "izettle", "zettle", "kahoot", "northvolt", "trustly", "tink", "aiven", "oura", "relex", "kry",
                   "voi technology", "truecaller", "epidemic sound", "pleo", "trustpilot", "zendesk", "unity",
                   "smartly", "iqm", "lovable", "einride", "bolt", "wise", "pipedrive", "veriff", "revolut", "n26",
                   "zalando", "google", "alphabet", "deepmind", "microsoft", "apple", "amazon", "aws", "meta platforms",
                   "facebook", "netflix", "nvidia"]
# cohort-tags.csv tags counted as unicorn / big-tech alumni ("?" = query match only, dropped in strict mode)
UNICORN_TAGS = {"google", "meta", "microsoft", "amazon", "klarna", "spotify", "supercell", "rovio", "wolt",
                "revolut", "n26", "zalando"}
EXEC = re.compile(r"\b(co-?founder|founder|chief|ceo|cto|cfo|coo|cpo|partner|president|managing director)\b", re.I)


# ---------------------------------------------------------------- sources
def to_t(d: Optional[str]) -> Optional[float]:
    """'2019-03-01' -> 2019.167; None/'' -> None."""
    if not d:
        return None
    m = re.match(r"(\d{4})(?:-(\d{2}))?", str(d))
    if not m:
        return None
    return int(m.group(1)) + (int(m.group(2) or 1) - 1) / 12


@dataclass
class Fact:
    org: str
    org_key: str
    org_id: Optional[str]
    since_t: Optional[float]
    title: str = ""


@dataclass
class Person:
    pid: str
    name: str
    founded: list[Fact] = field(default_factory=list)
    roles: list[Fact] = field(default_factory=list)


@dataclass
class PeopleSources:
    persons: dict[str, Person]
    founders: dict[str, set[str]]           # company ckey -> founder person ids
    company_ids: dict[str, set[str]]        # company ckey -> Cala entity ids of the company (and twins)
    cohort_tags: dict[str, set[str]]        # company ckey -> strict cohort tags (lowercase, '?' dropped)
    tags_fetched_t: float = SOURCES_FETCHED_T


def _fact(org: str, org_id: Optional[str], since: Optional[str], title: str = "") -> Fact:
    return Fact(org, company_key(org), org_id, to_t(since), title or "")


def load_sources(exp_path: Path = EXP_PEOPLE, app_path: Path = APP_PEOPLE, tags_path: Path = COHORT_TAGS) -> PeopleSources:
    persons: dict[str, Person] = {}
    founders: dict[str, set[str]] = defaultdict(set)
    ids: dict[str, set[str]] = defaultdict(set)
    exp = json.loads(exp_path.read_text())
    for pid, p in exp["persons"].items():
        per = persons.setdefault(pid, Person(pid, p["name"]))
        per.founded += [_fact(c["org"], c.get("org_id"), c.get("since")) for c in p.get("companies_founded", [])]
        per.roles += [_fact(r["org"], r.get("org_id"), r.get("since"), r.get("title")) for r in p.get("roles", [])]
        for link in p.get("linked_to", []):
            if "FOUNDED" in link.get("basis", ""):
                founders[link["ckey"]].add(pid)
    for ck, c in exp["companies"].items():
        founders[ck].update(c.get("founders") or [])
        if c.get("cala_id"):
            ids[ck].add(c["cala_id"])
        for tw in (c.get("lookup") or {}).get("twins", []):
            if tw.get("founded"):
                ids[ck].add(tw["id"])
    app = json.loads(app_path.read_text())
    for c in app["companies"]:
        founders[c["ckey"]].update(c.get("founders") or [])
        if c.get("entity_id"):
            ids[c["ckey"]].add(c["entity_id"])
    for p in app["people"]:
        per = persons.setdefault(p["id"], Person(p["id"], p["name"]))
        per.roles += [_fact(r["org"], r.get("org_id"), r.get("since"), r.get("role")) for r in p.get("roles", [])]
        per.founded += [_fact(f["org"], f.get("org_id"), None) for f in p.get("founded", [])]
    tags: dict[str, set[str]] = defaultdict(set)
    with tags_path.open() as fh:
        for row in csv.DictReader(fh):
            for t in (row.get("background_tags") or "").split(";"):
                t = t.strip().lower()
                if t and not t.endswith("?"):
                    tags[row["ckey"]].add(t)
    return PeopleSources(persons, dict(founders), dict(ids), dict(tags))


# ---------------------------------------------------------------- point-in-time helpers
def first_round_t(rounds: list[dict], as_of: float) -> dict[str, float]:
    out: dict[str, float] = {}
    for r in rounds:
        if r.get("disputed") or r.get("t") is None or r["t"] >= as_of:
            continue
        out[r["ckey"]] = min(out.get(r["ckey"], r["t"]), r["t"])
    return out


def _is_target(f: Fact, ck: str, src: PeopleSources) -> bool:
    return f.org_key == ck or (f.org_id is not None and f.org_id in src.company_ids.get(ck, set())) \
        or (len(ck) >= 3 and f.org_key.startswith(ck)) or (len(f.org_key) >= 3 and ck.startswith(f.org_key))


def _matches(org: str, words: list[str]) -> bool:
    o = org.lower()
    return any(re.search(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])", o) for w in words)


def _dated_before(f: Fact, as_of: float) -> bool:
    return f.since_t is not None and f.since_t < as_of


def _founders(ck: str, src: PeopleSources) -> list[Person]:
    return [src.persons[p] for p in sorted(src.founders.get(ck, ())) if p in src.persons]


def _companies(rounds: list[dict], as_of: float) -> set[str]:
    return set(first_round_t(rounds, as_of))


# ---------------------------------------------------------------- signals
def prior_founder(rounds: list[dict], as_of: float, src: PeopleSources) -> dict[str, Optional[float]]:
    """Founders who founded ANOTHER company, counted only if that FOUNDED edge is dated before as_of or the other
    company has a snapshot round before as_of. Value = number of such founders; None = no founder known."""
    fr = first_round_t(rounds, as_of)
    out: dict[str, Optional[float]] = {}
    for ck in fr:
        fs = _founders(ck, src)
        if not fs:
            out[ck] = None
            continue
        out[ck] = float(sum(1 for p in fs if any(
            not _is_target(f, ck, src) and (_dated_before(f, as_of) or f.org_key in fr) for f in p.founded)))
    return out


def _role_hits(ck: str, src: PeopleSources, as_of: float, words: list[str], dated_only: bool) -> int:
    n = 0
    for p in _founders(ck, src):
        for f in p.roles + p.founded:
            if _is_target(f, ck, src) or not _matches(f.org, words):
                continue
            if _dated_before(f, as_of) or (not dated_only and f.since_t is None):
                n += 1
                break
    return n


def research_alumni(rounds: list[dict], as_of: float, src: PeopleSources,
                    dated_only: bool = True) -> dict[str, Optional[float]]:
    """Founders with a university / research-lab role dated before as_of. dated_only=False also counts undated roles
    (NOT point-in-time, diagnostic). None = no founder known."""
    return {ck: (float(_role_hits(ck, src, as_of, RESEARCH, dated_only)) if _founders(ck, src) else None)
            for ck in first_round_t(rounds, as_of)}


def unicorn_alumni(rounds: list[dict], as_of: float, src: PeopleSources,
                   mode: str = "careers_dated", allow_lookahead: bool = False) -> dict[str, Optional[float]]:
    """mode 'careers_dated': founders with a dated (before as_of) role at a Nordic unicorn / big-tech employer.
    mode 'cohort_tags': company carries a strict unicorn/big-tech tag in cohort-tags.csv. That file is fetched after
    every as_of, so it returns all None unless allow_lookahead (diagnostic, not point-in-time)."""
    cks = first_round_t(rounds, as_of)
    if mode == "cohort_tags":
        if src.tags_fetched_t >= as_of and not allow_lookahead:
            return {ck: None for ck in cks}
        return {ck: (float(bool(src.cohort_tags[ck] & UNICORN_TAGS)) if ck in src.cohort_tags else None) for ck in cks}
    return {ck: (float(_role_hits(ck, src, as_of, UNICORN_BIGTECH, True)) if _founders(ck, src) else None)
            for ck in cks}


def _employers(ck: str, src: PeopleSources, as_of: float, mode: str) -> set[str]:
    if mode == "cohort_tags":
        return set(src.cohort_tags.get(ck, set())) - {"repeat_founder"}
    return {f.org_key for p in _founders(ck, src) for f in p.roles + p.founded
            if not _is_target(f, ck, src) and _dated_before(f, as_of)}


def mafia_density(rounds: list[dict], as_of: float, src: PeopleSources,
                  mode: str = "careers_dated", allow_lookahead: bool = False) -> dict[str, Optional[float]]:
    """Number of OTHER snapshot companies (first round before as_of) whose founders share an employer with this
    company's founders. careers_dated: employers from roles dated before as_of. cohort_tags: tag sets (fetched after
    every as_of -> None unless allow_lookahead). None = no employer known for this company."""
    cks = first_round_t(rounds, as_of)
    if mode == "cohort_tags" and src.tags_fetched_t >= as_of and not allow_lookahead:
        return {ck: None for ck in cks}
    emp = {ck: _employers(ck, src, as_of, mode) for ck in cks}
    by_emp: dict[str, set[str]] = defaultdict(set)
    for ck, es in emp.items():
        for e in es:
            by_emp[e].add(ck)
    return {ck: (float(len(set().union(*(by_emp[e] for e in es)) - {ck})) if es else None) for ck, es in emp.items()}


def named_operator_angels(rounds: list[dict], as_of: float, src: PeopleSources,
                          investor_names: Optional[dict] = None) -> dict[str, Optional[float]]:
    """Person-named backers (rounds before as_of) who are founders / C-level of ANOTHER snapshot company that has a
    round before as_of. Value = count; None = company has no person-named backer before as_of."""
    names = investor_names or {}
    fr = first_round_t(rounds, as_of)
    by_name: dict[str, list[Person]] = defaultdict(list)
    for p in src.persons.values():
        by_name[p.name.strip().lower()].append(p)
    backers: dict[str, set[str]] = defaultdict(set)
    for r in rounds:
        if r.get("disputed") or r.get("t") is None or r["t"] >= as_of:
            continue
        for b in (r.get("leads") or []) + (r.get("participants") or []):
            if is_person(names.get(b, b)):
                backers[r["ckey"]].add(b)
    out: dict[str, Optional[float]] = {}
    for ck in fr:
        if not backers.get(ck):
            out[ck] = None
            continue
        n = 0
        for b in backers[ck]:
            for p in by_name.get(names.get(b, b).strip().lower(), []) + by_name.get(b, []):
                other = [f for f in p.founded + [x for x in p.roles if EXEC.search(x.title)]
                         if not _is_target(f, ck, src) and f.org_key in fr]
                if other:
                    n += 1
                    break
        out[ck] = float(n)
    return out


SIGNALS = {
    "prior_founder": prior_founder,
    "research_alumni": research_alumni,
    "unicorn_alumni": unicorn_alumni,
    "mafia_density": mafia_density,
    "named_operator_angels": named_operator_angels,
}
