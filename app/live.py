"""Live Cala lookups for funds that are not in the snapshot yet, or that we only saw from the company side.

Each fund gets one investor-first query (plus a dated fallback when Cala says the question is too complex).
Calls run in background threads inside the single web container, with request starts kept under our client
limit of 10 per minute. Spending is capped per day in Aiven (`live_usage`), so restarts cannot reset it, and
per session in memory. Results are stored in Aiven (`live_funds`) and merged into the snapshot.
"""
from __future__ import annotations

import os
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import requests

CALA = "https://api.cala.ai/v1/knowledge/query"
OPEN_Q = ("List every funding round that {f} invested in, with company name, company country, announcement date, "
          "round type, amount, lead investor, all participating investors, and whether {f} led the round")
YEAR_Q = ("Funding rounds {f} invested in during {y}, with company, company country, date, round type, amount, "
          "lead investor, participating investors and whether {f} led")
DAY_CAP = int(os.environ.get("LIVE_DAY_CAP", "120"))
SESSION_CAP = int(os.environ.get("LIVE_SESSION_CAP", "15"))
MIN_INTERVAL_S = 6.2
SAFE_NAME = re.compile(r"^[\w .,&'+\-]{2,60}$")

_pool = ThreadPoolExecutor(max_workers=8)
_lock = threading.Lock()
_last_start = 0.0
_used_session: dict[str, int] = {}
_used_memory: dict[str, int] = {}  # fallback when no database (local development)
JOBS: dict[str, dict] = {}


def clean_name(name: str) -> str | None:
    """Fund names only: letters, digits and a few punctuation marks; nothing that reads like an instruction."""
    n = re.sub(r"\s+", " ", str(name or "")).strip()
    return n if SAFE_NAME.match(n) and len(n.split()) <= 6 else None


def _db():
    url = os.environ.get("RELAY_DATABASE_URL")
    if not url or os.environ.get("RELAY_SNAPSHOT_PATH"):
        return None
    import psycopg
    return psycopg.connect(url, connect_timeout=10)


def _charge(n: int) -> bool:
    """Atomically spend n paid calls from today's cap. Returns False when the cap would be exceeded."""
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    conn = _db()
    if conn is None:
        with _lock:
            if _used_memory.get(day, 0) + n > DAY_CAP:
                return False
            _used_memory[day] = _used_memory.get(day, 0) + n
            return True
    with conn:
        conn.execute("create table if not exists live_usage (day text primary key, used int not null default 0)")
        conn.execute("insert into live_usage(day, used) values (%s, 0) on conflict (day) do nothing", (day,))
        row = conn.execute("update live_usage set used = used + %s where day = %s and used + %s <= %s returning used",
                           (n, day, n, DAY_CAP)).fetchone()
        conn.commit()
        return row is not None


def day_left() -> int:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    conn = _db()
    if conn is None:
        return DAY_CAP - _used_memory.get(day, 0)
    with conn:
        conn.execute("create table if not exists live_usage (day text primary key, used int not null default 0)")
        row = conn.execute("select used from live_usage where day = %s", (day,)).fetchone()
    return DAY_CAP - (row[0] if row else 0)


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
    return [] if (len(rows) == 1 and isinstance(rows[0], dict) and "error" in rows[0]) else rows


def budget(session: str) -> dict:
    return {"day_left": max(0, day_left()), "session_left": max(0, SESSION_CAP - _used_session.get(session, 0))}


def _spend_session(session: str, n: int) -> bool:
    with _lock:
        if _used_session.get(session, 0) + n > SESSION_CAP:
            return False
        _used_session[session] = _used_session.get(session, 0) + n
        if len(_used_session) > 2000:
            _used_session.clear()
        return True


def start(names: list[str], session: str, on_result) -> dict:
    """Queue lookups (names must already be cleaned and de-duplicated). on_result(record) merges and persists."""
    job = {"id": uuid.uuid4().hex[:12], "items": [], "created": time.time()}
    for name in names[:12]:
        if not _spend_session(session, 1):
            job["items"].append({"name": name, "status": "budget", "rows": 0})
        elif not _charge(1):
            job["items"].append({"name": name, "status": "budget", "rows": 0})
        else:
            job["items"].append({"name": name, "status": "queued", "rows": 0, "t0": None, "t1": None})
    JOBS[job["id"]] = job
    if len(JOBS) > 500:
        for k in list(JOBS)[:250]:
            JOBS.pop(k, None)
    for item in job["items"]:
        if item["status"] == "queued":
            _pool.submit(_run, item, session, on_result)
    return view(job["id"])


def _run(item: dict, session: str, on_result) -> None:
    item["status"], item["t0"] = "asking", time.time()
    queries = []
    try:
        rows = _ask(OPEN_Q.format(f=item["name"]))
        queries.append({"q": OPEN_Q.format(f=item["name"]), "rows": rows})
        if not rows and _spend_session(session, 1) and _charge(1):
            q = YEAR_Q.format(f=item["name"], y=2025)
            queries.append({"q": q, "year": 2025, "rows": _ask(q)})
        total = sum(len(q["rows"]) for q in queries)
        item["rows"] = total
        if total:
            on_result({"name": item["name"], "queries": queries, "source": "live"})
            item["status"] = "done"
        else:
            item["status"] = "empty"
    except Exception as err:  # any failure must end the item, or the browser polls forever
        item["status"], item["error"] = "error", f"{type(err).__name__}"
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


SEARCH = "https://api.cala.ai/v1/knowledge/search"
MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
               "November", "December"]


def source_question(r: dict) -> str:
    stage = (r.get("stage") or "funding").replace("series", "Series")
    return (f"Who led {r['company']}'s {stage} round announced around {MONTH_NAMES[r['month'] - 1]} {r['year']}, "
            f"how much was raised, and which investors took part?")


def search_round(r: dict, session: str) -> dict:
    """One live Cala search for a round's sources. Raises RuntimeError when the budget is used up."""
    if not _spend_session(session, 1) or not _charge(1):
        raise RuntimeError("budget")
    _slot()
    resp = requests.post(SEARCH, json={"input": source_question(r)}, timeout=150,
                         headers={"X-API-KEY": os.environ["CALA_API_KEY"], "Content-Type": "application/json"})
    resp.raise_for_status()
    return resp.json()
