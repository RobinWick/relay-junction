"""Fetch the Cala entity data behind "Who bought this fund's companies" and build app/exits.json.

Three kinds of entity projection (POST /v1/entities/{id}), each cached to disk by tag so nothing is paid twice:
- fund:    the fund's outgoing INVESTED_IN edges (its portfolio, with the sources that name it)
- company: a portfolio company's corporate events (MNA_COMPLETED as TARGET) and incoming INVESTED_IN edges
- event:   one CorporateEvent's value, date and participants (the acquirer)

Every live call is logged (endpoint, target, status, seconds) to research/patterns/exits-call-log.md and the
total is capped by BUDGET, counting failed calls too. Calls take about 4 minutes each, so jobs run 4 at a time.

Usage (key from env, never printed):
  set -a; source ~/.claude/secrets/api_keys.env; set +a
  python3 fetch_exits.py fetch <tag>:<kind>:<entity_id> [...]   # live calls, concurrent
  python3 fetch_exits.py build                                  # raw cache -> app/exits.json (no calls)
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "app"))
import receipt_exits as rx  # noqa: E402

API = "https://api.cala.ai/v1"
RESEARCH = HERE.parents[1] / "research" / "patterns"
RAW = Path(os.environ.get("EXITS_RAW_DIR", RESEARCH / "exits-raw"))
LOG = RESEARCH / "exits-call-log.md"
OUT = HERE.parent / "app" / "exits.json"
BUDGET = 20
WORKERS = 4
_lock = threading.Lock()

BODIES = {
    "fund": {"properties": ["name", "description"],
             "relationships": {"outgoing": {"INVESTED_IN": {"limit": 500}}}},
    "company": {"properties": ["name", "founding_date", "operational_status"],
                "relationships": {"outgoing": {"PARTICIPATES_IN_CORPORATE_EVENT": {"limit": 40}},
                                  "incoming": {"INVESTED_IN": {"limit": 60}}}},
    "event": {"properties": ["event_date", "transaction_value", "transaction_value_units", "description",
                             "event_type", "name"],
              "relationships": {"incoming": {"PARTICIPATES_IN_CORPORATE_EVENT": {"limit": 20}}}},
}


# Which fetched company and event belongs to which fund (tags of cached raw projections). Chosen from the fund
# pulls: companies the fund backed that are known to have been sold long ago, plus misses kept as misses.
PLAN = {
    "lifeline": {"name": "Lifeline Ventures", "entity": ["476a73ac-afa2-4713-9f73-188bc7ec0b95"],
                 "fund_tag": "fund_lifeline",
                 "companies": [{"company_tag": "co_supercell", "event_tags": ["event_supercell"]},
                               {"company_tag": "co_beddit"}]},
    "northzone": {"name": "Northzone", "entity": ["10c75ca4-24d6-4a32-8f22-08d4b1dfffce"],
                  "fund_tag": "probe_fund_northzone",
                  "companies": [{"company_tag": "co_zettle", "event_tags": ["event_zettle"]},
                                {"company_tag": "co_energy_micro", "event_tags": ["event_energy_micro"]},
                                {"company_tag": "co_nimsoft", "event_tags": ["event_nimsoft"]},
                                {"company_tag": "co_mamut"},
                                {"company_tag": "probe_ipo_kahoot"}]},
    # Cala has two Creandum entities: 'Creandum' (the firm, used here) and 'Creandum Fund' (our snapshot's id)
    "creandum": {"name": "Creandum", "entity": ["6ba00a20-2cb4-4559-8fe2-f39484a9e5f6",
                                                "7d4ebd18-3539-4f19-a2e0-93bebb838554"],
                 "fund_tag": "fund_creandum",
                 "companies": [{"company_tag": "co_small_giant_games", "event_tags": ["event_small_giant_games"]},
                               {"company_tag": "co_tictail"},
                               {"company_tag": "probe_ipo_kahoot"}]},
}
NOT_FETCHED = {
    "maki": "Not fetched: the 20 call budget went to older funds; Maki.vc's first fund is from 2018.",
    "inventure": "Not fetched: the 20 call budget ran out.",
    "voima": "Not fetched: the 20 call budget went to older funds.",
}


def _key() -> str:
    key = os.environ.get("CALA_API_KEY")
    if not key:
        sys.exit("CALA_API_KEY missing: export it before running")
    return key


def calls_used() -> int:
    """Live calls already logged (one table row per call, failed calls included)."""
    if not LOG.exists():
        return 0
    return sum(1 for line in LOG.read_text().splitlines() if line.startswith("| ") and line[2:3].isdigit())


def _log(tag: str, path: str, status: int | str, seconds: float, note: str) -> None:
    with _lock:
        if not LOG.exists():
            LOG.write_text("# Cala call log: Who Bought This Fund's Companies\n\n"
                           f"Budget: at most {BUDGET} calls. Key sent as X-API-KEY from env, never printed or saved. "
                           f"Raw responses: `{RAW}`.\n\n"
                           "| # | Tag | Endpoint | Status | Seconds | When (UTC) | Note |\n|---|---|---|---|---|---|---|\n")
        n = calls_used() + 1
        when = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        with LOG.open("a") as f:
            f.write(f"| {n} | {tag} | POST {path} | {status} | {seconds:.1f} | {when} | {note} |\n")


def raw_path(tag: str) -> Path:
    return RAW / f"{tag}.json"


def fetch(tag: str, kind: str, entity_id: str) -> dict | None:
    """One cached projection. Returns the response, or None when the call failed (still counted)."""
    cached = raw_path(tag)
    if cached.exists():
        return json.loads(cached.read_text())["response"]
    with _lock:
        if calls_used() >= BUDGET:
            print(f"{tag}: budget of {BUDGET} calls reached, not fetched", flush=True)
            return None
    path = f"/entities/{entity_id}"
    body = BODIES[kind]
    started = time.time()
    try:
        resp = requests.post(f"{API}{path}", headers={"X-API-KEY": _key(), "Content-Type": "application/json"},
                             json=body, timeout=900)
    except requests.RequestException as exc:
        _log(tag, path, "error", time.time() - started, type(exc).__name__)
        print(f"{tag}: {type(exc).__name__}", flush=True)
        return None
    seconds = time.time() - started
    try:
        data = resp.json()
    except ValueError:
        data = {"raw": resp.text[:2000]}
    if resp.status_code != 200:
        _log(tag, path, resp.status_code, seconds, str(data)[:80].replace("|", "/"))
        print(f"{tag}: HTTP {resp.status_code}", flush=True)
        return None
    RAW.mkdir(parents=True, exist_ok=True)
    cached.write_text(json.dumps({"tag": tag, "kind": kind, "path": path, "body": body, "status": resp.status_code,
                                  "seconds": round(seconds, 1), "response": data}, ensure_ascii=False, indent=1))
    _log(tag, path, resp.status_code, seconds, f"{kind} {data.get('name', '')}")
    print(f"{tag}: 200 in {seconds:.0f}s", flush=True)
    return data


def fetch_many(jobs: list[tuple[str, str, str]]) -> None:
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        list(pool.map(lambda j: fetch(*j), jobs))


def load_raw(tag: str) -> dict | None:
    p = raw_path(tag)
    return json.loads(p.read_text())["response"] if p.exists() else None


def build(today: date) -> dict:
    """Join the cached fund, company and event projections into receipts per fund key. No calls."""
    funds = {}
    for fund_key, spec in PLAN.items():
        fund_raw = load_raw(spec["fund_tag"]) if spec.get("fund_tag") else None
        companies = []
        for c in spec.get("companies", []):
            comp = load_raw(c["company_tag"])
            events = {t: load_raw(t) for t in c.get("event_tags", [])}
            companies.append({"company": comp, "events": [e for e in events.values() if e]})
        funds[fund_key] = rx.build_fund(fund_key, spec["name"], spec["entity"], fund_raw, companies, today,
                                        spec.get("note"))
    return {"version": 1, "built": today.isoformat(), "caveat": rx.CAVEAT, "value_label": rx.VALUE_LABEL,
            "funds": funds, "not_fetched": NOT_FETCHED}


def main(argv: list[str]) -> None:
    if not argv:
        sys.exit(__doc__)
    if argv[0] == "fetch":
        jobs = []
        for spec in argv[1:]:
            tag, kind, entity_id = spec.split(":", 2)
            if kind not in BODIES:
                sys.exit(f"unknown kind {kind}")
            jobs.append((tag, kind, entity_id))
        fetch_many(jobs)
        print(f"calls used: {calls_used()} of {BUDGET}")
    elif argv[0] == "build":
        out = build(date.today())
        OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
        print(f"wrote {OUT}: " + ", ".join(f"{k} {len(v['receipts'])} disclosed + {len(v['undisclosed'])} undisclosed"
                                           for k, v in out["funds"].items()))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
