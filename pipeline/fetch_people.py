"""Fetch the Cala people data behind the founder career view and build app/people.json.

Four kinds of live call, each cached to disk by tag so nothing is ever paid for twice:
- cohort:  POST /v1/knowledge/query with Cala QL `companies.founder.incorporation>2015.previous_job=<X>`
           (seeds founder background cohorts; rows mix "worked at X" and "funded by X", app/people.py separates them)
- company: POST /v1/entities/{id} projecting FOUNDED, IS_CEO_OF, IS_CTO_OF, WORKS_AT (incoming) and corporate events
- person:  POST /v1/entities/{id} projecting the person's FOUNDED and WORKS_AT edges (role, valid_since, valid_until)
- exit:    POST /v1/entities/{id} projecting a founder's earlier company's corporate events (prior exit check)

Every live call, failed ones included, is logged to research/patterns/people-call-log.md and counted against BUDGET.
There are no automatic retries: a retry would spend budget silently. Calls take about 4 minutes, so WORKERS run at once.

Usage (key from env, never printed):
  set -a; source ~/.claude/secrets/api_keys.env; set +a
  python3 fetch_people.py cohorts            # QL cohort queries
  python3 fetch_people.py companies          # company projections for COMPANIES
  python3 fetch_people.py persons [N]        # person projections for up to N founders found in the company cache
  python3 fetch_people.py exits [N]          # up to N earlier companies of prior founders
  python3 fetch_people.py status             # calls used, nothing fetched
  python3 fetch_people.py build              # raw cache -> app/people.json (no calls)
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "app"))
import people as pp  # noqa: E402

API = "https://api.cala.ai/v1"
RESEARCH = HERE.parents[1] / "research" / "patterns"
RAW = Path(os.environ.get("PEOPLE_RAW_DIR", RESEARCH / "people-raw"))
LOG = RESEARCH / "people-call-log.md"
LEDGER = RAW / "_ledger.json"
SNAPSHOT = HERE.parents[1] / "cala" / "data" / "snapshot.json"
OUT = HERE.parent / "app" / "people.json"
BUDGET = 60
WORKERS = 4  # 5 at once hit HTTP 429 while another lane shared the key
TIMEOUT_S = 480

# Cohorts: founders who previously worked at these employers. Supercell is reused free from the earlier probe (q02).
COHORTS = ["McKinsey", "BCG", "Bain", "Rovio", "Wolt", "Spotify", "Klarna"]
FREE_COHORTS = {"Supercell": RESEARCH / "probe" / "q02_founder_prevjob.json"}

# Nordic companies in the snapshot with a seed or Series A in 2023 to 2026, ranked by ties to the demo sample funds
# (Maki.vc, Voima, Creandum, Inventure, Northzone, Icebreaker, byFounders, Seedcamp, Superhero, Lifeline ...).
COMPANIES = ["verda", "reduciner", "haminawireless", "reorbit", "valpas", "lovable", "riff", "spektr", "kuvaspace",
             "algorithmiq", "iprallytechnologies", "datacrunch", "steadyenergy", "aibidia",
             # second batch: 7 of the first 14 had no founder edge in Cala, so six more were added
             "inven", "metroc", "nadmed", "quanscient", "encube", "gilion"]

COMPANY_BODY = {
    "properties": ["name", "description", "founded_date", "incorporation_date", "operational_status"],
    "relationships": {
        "incoming": {"FOUNDED": {"limit": 10}, "IS_CEO_OF": {"limit": 3}, "IS_CTO_OF": {"limit": 3},
                     "WORKS_AT": {"limit": 30}},
        "outgoing": {"PARTICIPATES_IN_CORPORATE_EVENT": {"limit": 10}},
    },
}
PERSON_BODY = {
    "properties": ["name", "description", "linkedin_url"],
    "relationships": {"outgoing": {"FOUNDED": {"limit": 20}, "WORKS_AT": {"limit": 40},
                                   "IS_CEO_OF": {"limit": 10}, "IS_BOARD_MEMBER_OF": {"limit": 10}}},
}
EXIT_BODY = {
    "properties": ["name", "operational_status"],
    "relationships": {"outgoing": {"PARTICIPATES_IN_CORPORATE_EVENT": {"limit": 20}}},
}

_lock = threading.Lock()


def _key() -> str:
    key = os.environ.get("CALA_API_KEY")
    if not key:
        sys.exit("CALA_API_KEY missing: export it before running")
    return key


def _ledger() -> list[dict]:
    return json.loads(LEDGER.read_text()) if LEDGER.exists() else []


def calls_used() -> int:
    """Calls that count against BUDGET: every claim, except attempts that failed to connect at all (never sent)."""
    return sum(1 for r in _ledger() if r.get("counted", True))


def _log(entry: dict) -> None:
    """Append one call to the ledger (the budget count) and the human-readable markdown log."""
    rows = _ledger()
    rows.append(entry)
    LEDGER.write_text(json.dumps(rows, indent=1))
    n = sum(1 for r in rows if r.get("counted", True) and r.get("status") != "pending")
    if not LOG.exists():
        LOG.write_text("# Cala call log: people and career data (lane A)\n\n"
                       f"Budget {BUDGET} calls, failed calls included. Key from env, never printed. "
                       f"Raw responses in `{RAW}`.\n\n"
                       "| # | Started (UTC) | Tag | Call | Target | Status | Seconds | Note |\n"
                       "|---|---|---|---|---|---|---|---|\n")
    with LOG.open("a") as f:
        f.write(f"| {n if entry.get('counted', True) else '-'} | {entry['started']} | {entry['tag']} | {entry['method']} {entry['path']} | "
                f"{entry['target']} | {entry['status']} | {entry['seconds']} | {entry['note']} |\n")


def _reserve() -> bool:
    """Claim one call from the budget before it starts, so concurrent workers can never overspend."""
    with _lock:
        rows = _ledger()  # pending claims count too; a crashed run leaves them in, which only errs on the safe side
        if sum(1 for r in rows if r.get("counted", True)) >= BUDGET:
            return False
        rows.append({"status": "pending"})
        LEDGER.write_text(json.dumps(rows, indent=1))
        return True


def _release_pending() -> None:
    rows = _ledger()
    for i, r in enumerate(rows):
        if r.get("status") == "pending":
            del rows[i]
            break
    LEDGER.write_text(json.dumps(rows, indent=1))


def cached(tag: str) -> Optional[dict]:
    p = RAW / f"{tag}.json"
    return json.loads(p.read_text()) if p.exists() else None


def call(tag: str, path: str, body: dict, target: str) -> Optional[dict]:
    """One live Cala POST, cached by tag. Never refetches a tag that is on disk, never retries."""
    hit = cached(tag)
    if hit is not None:
        return hit
    if not _reserve():
        print(f"{tag}: budget of {BUDGET} reached, skipped")
        return None
    started = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    t = time.time()
    status, note, data = "error", "", None
    try:
        r = requests.post(API + path, headers={"X-API-KEY": _key(), "Content-Type": "application/json"},
                          json=body, timeout=TIMEOUT_S)
        status = str(r.status_code)
        if r.status_code == 200:
            data = r.json()
        else:
            note = r.text[:120].replace("|", "/").replace("\n", " ")
    except requests.RequestException as e:
        note = type(e).__name__
    secs = round(time.time() - t, 1)
    # a connection refused in under 2 s never reached Cala, so it is logged but not counted against the budget
    counted = not (note == "ConnectionError" and secs < 2)
    if not counted:
        note = "ConnectionError in under 2 s: never reached Cala, not counted"
    with _lock:
        _release_pending()
        if data is not None:
            note = note or _summary(path, data)
            (RAW / f"{tag}.json").write_text(json.dumps(
                {"tag": tag, "path": path, "body": body, "target": target, "fetched": started[:10],
                 "status": int(status), "seconds": secs, "response": data}, ensure_ascii=False, indent=1))
        _log({"tag": tag, "method": "POST", "path": path, "target": target, "status": status, "seconds": secs,
              "started": started, "note": note, "counted": counted})
    print(f"{tag} {status} {secs}s {note}")
    return cached(tag)


def _summary(path: str, data: dict) -> str:
    if path.startswith("/knowledge"):
        return f"{len(data.get('results') or [])} rows, {len(data.get('entities') or [])} entities"
    rel = data.get("relationships") or {}
    parts = [f"{k} {len(v)}" for side in ("incoming", "outgoing") for k, v in (rel.get(side) or {}).items() if v]
    return (data.get("name") or "?").replace("|", "/") + ": " + (", ".join(parts) or "no edges")


def run(jobs: list[tuple[str, str, dict, str]]) -> None:
    todo = [j for j in jobs if cached(j[0]) is None]
    left = BUDGET - calls_used()
    print(f"{len(jobs)} jobs, {len(todo)} not cached, {left} calls left in budget")
    with ThreadPoolExecutor(WORKERS) as ex:
        list(ex.map(lambda j: call(*j), todo))


def snapshot_entities() -> dict:
    return json.loads(SNAPSHOT.read_text())["entities"]


def cohort_jobs() -> list[tuple[str, str, dict, str]]:
    return [(f"cohort_{c.lower()}", "/knowledge/query",
             {"input": f"companies.founder.incorporation>2015.previous_job={c}"}, c) for c in COHORTS]


def company_jobs() -> list[tuple[str, str, dict, str]]:
    ents = snapshot_entities()
    return [(f"company_{k}", f"/entities/{ents['c:' + k]}", COMPANY_BODY, k) for k in COMPANIES if f"c:{k}" in ents]


def person_jobs(cap: int) -> list[tuple[str, str, dict, str]]:
    seen, jobs = set(), []
    for k in COMPANIES:
        raw = cached(f"company_{k}")
        if not raw:
            continue
        for pid, name in pp.founder_candidates(raw["response"])[:5]:
            if pid not in seen:
                seen.add(pid)
                jobs.append((f"person_{pid}", f"/entities/{pid}", PERSON_BODY, f"{name} ({k})"))
    return jobs[:cap]


def exit_jobs(cap: int) -> list[tuple[str, str, dict, str]]:
    jobs, seen = [], set()
    for p in sorted(RAW.glob("person_*.json")):
        raw = json.loads(p.read_text())
        for cid, name in pp.earlier_founded(raw["response"], _sample_company_ids(), _sample_company_names()):
            if cid not in seen:
                seen.add(cid)
                jobs.append((f"exit_{cid}", f"/entities/{cid}", EXIT_BODY, name))
    return jobs[:cap]


def _sample_company_names() -> frozenset:
    names = set()
    for k in COMPANIES:
        raw = cached(f"company_{k}")
        names.add(pp._squash(k))
        if raw:
            names.add(pp._squash(raw["response"].get("name") or ""))
    return frozenset(n for n in names if n)


def _sample_company_ids() -> set[str]:
    ents = snapshot_entities()
    return {ents[f"c:{k}"] for k in COMPANIES if f"c:{k}" in ents}


def build() -> None:
    ents = snapshot_entities()
    companies = {k: cached(f"company_{k}") for k in COMPANIES}
    persons = {p.stem[len("person_"):]: json.loads(p.read_text()) for p in RAW.glob("person_*.json")}
    exits = {p.stem[len("exit_"):]: json.loads(p.read_text()) for p in RAW.glob("exit_*.json")}
    cohorts = {c: cached(f"cohort_{c.lower()}") for c in COHORTS}
    for c, path in FREE_COHORTS.items():
        if path.exists():
            raw = json.loads(path.read_text())
            cohorts[c] = {"response": raw["response"], "fetched": "2026-11-14", "body": raw["body"]}
    snap_rounds = json.loads(SNAPSHOT.read_text())["rounds"]
    out = pp.build(companies, persons, exits, cohorts, ents, snap_rounds, calls_used=calls_used())
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"wrote {OUT}: {len(out['people'])} people, {len(out['companies'])} companies, "
          f"{len(out['cohorts'])} cohorts, {calls_used()} Cala calls used")


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    cap = int(sys.argv[2]) if len(sys.argv) > 2 else BUDGET
    if cmd == "status":
        print(f"{calls_used()} of {BUDGET} calls used")
    elif cmd == "cohorts":
        run(cohort_jobs())
    elif cmd == "companies":
        run(company_jobs())
    elif cmd == "first":  # cohorts and companies share one worker pool
        run(company_jobs() + cohort_jobs())
    elif cmd == "persons":
        run(person_jobs(cap))
    elif cmd == "exits":
        run(exit_jobs(cap))
    elif cmd == "build":
        build()
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
