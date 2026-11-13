"""Overnight Cala crawl: discover European startups, then fetch each one's round history.

Cala queries take ~45 s each, so requests run in parallel threads while cala_client keeps
request starts under the 10/min plan limit. Resumable: every request is cached.
Writes data/companies.json and data/histories.jsonl.
"""
from __future__ import annotations

import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import cala_client as cala

DATA = Path(__file__).parent / "data"
WORKERS = 9
COUNTRIES = [
    "Sweden", "Finland", "Norway", "Denmark", "Estonia", "Lithuania", "Latvia",
    "Germany", "France", "United Kingdom", "Netherlands", "Spain", "Poland",
    "Switzerland", "Ireland", "Belgium", "Austria", "Portugal", "Italy",
]
BANDS = [("2M", "20M"), ("20M", "200M")]
HISTORY_Q = ("List every funding round of {name} with announcement date, round type, amount, "
             "lead investor and all participating investors")
_write_lock = threading.Lock()


def _discover_one(country: str, lo: str, hi: str) -> tuple[str, str, list[dict]]:
    q = f"startups.location={country}.funding>{lo}.funding<{hi}"
    return country, f"{lo}-{hi}", cala.query(q).get("results", [])


def discover() -> list[dict]:
    seen: dict[str, dict] = {}
    jobs = [(c, lo, hi) for c in COUNTRIES for lo, hi in BANDS]
    with ThreadPoolExecutor(WORKERS) as pool:
        futures = [pool.submit(_discover_one, *job) for job in jobs]
        for fut in as_completed(futures):
            try:
                country, band, rows = fut.result()
            except RuntimeError as err:
                print(f"discover FAIL: {err}", flush=True)
                continue
            for row in rows:
                name = (row.get("name") or row.get("company") or "").strip()
                if name and name.lower() not in seen:
                    seen[name.lower()] = {"name": name, "country": country, "band": band, "row": row}
            print(f"discover {country} {band}: {len(rows)} rows, {len(seen)} unique", flush=True)
    companies = sorted(seen.values(), key=lambda c: (c["country"], c["name"]))
    DATA.mkdir(exist_ok=True)
    (DATA / "companies.json").write_text(json.dumps(companies, ensure_ascii=False, indent=1))
    return companies


def _history_one(co: dict) -> tuple[dict, dict]:
    return co, cala.query(HISTORY_Q.format(name=co["name"]))


def histories(companies: list[dict], limit: int) -> None:
    out = DATA / "histories.jsonl"
    done = {json.loads(line)["name"] for line in out.open()} if out.exists() else set()
    todo = [c for c in companies[:limit] if c["name"] not in done]
    print(f"histories: {len(done)} done, {len(todo)} to fetch", flush=True)
    finished = 0
    with ThreadPoolExecutor(WORKERS) as pool, out.open("a") as fh:
        futures = [pool.submit(_history_one, co) for co in todo]
        for fut in as_completed(futures):
            try:
                co, res = fut.result()
            except RuntimeError as err:
                print(f"history FAIL: {err}", flush=True)
                continue
            with _write_lock:
                fh.write(json.dumps({"name": co["name"], "country": co["country"],
                                     "rounds": res.get("results", []),
                                     "entities": res.get("entities", [])}, ensure_ascii=False) + "\n")
                fh.flush()
            finished += 1
            print(f"history {finished}/{len(todo)} {co['name']}: {len(res.get('results', []))} rounds", flush=True)


if __name__ == "__main__":
    max_histories = int(sys.argv[1]) if len(sys.argv) > 1 else 700
    cos = discover()
    print(f"DISCOVERED {len(cos)} companies", flush=True)
    histories(cos, max_histories)
    print("DONE", flush=True)
