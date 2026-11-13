"""Live Cala lookups for funds that are not in the snapshot yet.

Each fund gets one investor-first query (plus a dated fallback when Cala says the question is too complex).
Calls run in background threads inside the single web container, with request starts kept under Cala's
10 per minute plan limit, a global live budget and a per-session budget. Results are stored in Aiven
(`live_funds`) and merged into the in-memory snapshot, so the next check shows them.
"""
from __future__ import annotations

import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import requests

CALA = "https://api.cala.ai/v1/knowledge/query"
OPEN_Q = ("List every funding round that {f} invested in, with company name, company country, announcement date, "
          "round type, amount, lead investor, all participating investors, and whether {f} led the round")
YEAR_Q = ("Funding rounds {f} invested in during {y}, with company, company country, date, round type, amount, "
          "lead investor, participating investors and whether {f} led")
GLOBAL_CAP = int(os.environ.get("LIVE_GLOBAL_CAP", "150"))
SESSION_CAP = int(os.environ.get("LIVE_SESSION_CAP", "15"))
MIN_INTERVAL_S = 6.2

_pool = ThreadPoolExecutor(max_workers=8)
_lock = threading.Lock()
_last_start = 0.0
_used_global = 0
_used_session: dict[str, int] = {}
JOBS: dict[str, dict] = {}


def _slot() -> None:
    global _last_start
    with _lock:
        start = max(time.time(), _last_start + MIN_INTERVAL_S)
        _last_start = start
    time.sleep(max(0.0, start - time.time()))


def _ask(question: str) -> list[dict]:
    _slot()
    resp = requests.post(CALA, json={"input": question}, timeout=150,
                         headers={"X-API-KEY": os.environ["CALA_API_KEY"], "Content-Type": "application/json"})
    if resp.status_code == 429:
        raise RuntimeError("Cala is rate-limiting")
    resp.raise_for_status()
    rows = resp.json().get("results", []) or []
    return [] if (len(rows) == 1 and "error" in rows[0]) else rows


def budget(session: str) -> dict:
    return {"global_left": max(0, GLOBAL_CAP - _used_global),
            "session_left": max(0, SESSION_CAP - _used_session.get(session, 0))}


def start(names: list[str], session: str, on_result) -> dict:
    """Queue lookups. on_result(record) is called for each finished fund (merge + persist happens there)."""
    global _used_global
    job = {"id": uuid.uuid4().hex[:12], "items": [], "created": time.time()}
    with _lock:
        for name in names[:12]:
            left = min(GLOBAL_CAP - _used_global, SESSION_CAP - _used_session.get(session, 0))
            if left < 1:
                job["items"].append({"name": name, "status": "budget", "rows": 0})
                continue
            _used_global += 1
            _used_session[session] = _used_session.get(session, 0) + 1
            job["items"].append({"name": name, "status": "queued", "rows": 0, "t0": None, "t1": None})
    JOBS[job["id"]] = job
    for item in job["items"]:
        if item["status"] == "queued":
            _pool.submit(_run, item, session, on_result)
    return view(job["id"])


def _run(item: dict, session: str, on_result) -> None:
    global _used_global
    item["status"], item["t0"] = "asking", time.time()
    queries = []
    try:
        rows = _ask(OPEN_Q.format(f=item["name"]))
        queries.append({"q": OPEN_Q.format(f=item["name"]), "rows": rows})
        if not rows:
            with _lock:
                ok = GLOBAL_CAP - _used_global >= 1
                if ok:
                    _used_global += 1
            if ok:
                q = YEAR_Q.format(f=item["name"], y=2025)
                queries.append({"q": q, "year": 2025, "rows": _ask(q)})
        total = sum(len(q["rows"]) for q in queries)
        item["rows"] = total
        if total:
            on_result({"name": item["name"], "queries": queries, "source": "live"})
            item["status"] = "done"
        else:
            item["status"] = "empty"
    except (requests.RequestException, RuntimeError, KeyError, ValueError) as err:
        item["status"], item["error"] = "error", str(err)[:120]
    finally:
        item["t1"] = time.time()


def view(job_id: str) -> dict | None:
    job = JOBS.get(job_id)
    if not job:
        return None
    now = time.time()
    items = [{"name": i["name"], "status": i["status"], "rows": i["rows"], "error": i.get("error"),
              "seconds": round(((i.get("t1") or now) - i["t0"])) if i.get("t0") else None} for i in job["items"]]
    return {"id": job["id"], "items": items, "done": all(i["status"] not in ("queued", "asking") for i in items)}
