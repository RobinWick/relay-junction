"""Cala API client: cached on disk, rate-limited to the Starter plan (10 req/min).

Every response is cached by request hash, so a query is never paid for twice.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
import time
from pathlib import Path

import requests

API = "https://api.cala.ai/v1"
CACHE = Path(__file__).parent / "cache" / "api"
MIN_INTERVAL_S = 6.2  # 10 req/min with margin; spacing between request STARTS
_last_call = 0.0
_lock = threading.Lock()
live_calls = 0  # paid (non-cached) requests made by this process


def _reserve_slot() -> None:
    """Block until this thread may start a request, keeping starts >= MIN_INTERVAL_S apart."""
    global _last_call
    with _lock:
        start = max(time.time(), _last_call + MIN_INTERVAL_S)
        _last_call = start
    delay = start - time.time()
    if delay > 0:
        time.sleep(delay)


def _key() -> str:
    key = os.environ.get("CALA_API_KEY_WICFLOW")
    if not key:
        sys.exit("CALA_API_KEY_WICFLOW missing: source ~/.claude/secrets/api_keys.env")
    return key


def _cache_path(path: str, body: dict) -> Path:
    digest = hashlib.sha256(json.dumps([path, body], sort_keys=True).encode()).hexdigest()[:20]
    return CACHE / f"{digest}.json"


def post(path: str, body: dict, retries: int = 4) -> dict:
    """POST to Cala, returning the cached response if this exact request was made before."""
    cached = _cache_path(path, body)
    if cached.exists():
        return json.loads(cached.read_text())["response"]

    global live_calls
    for attempt in range(retries):
        _reserve_slot()
        with _lock:
            live_calls += 1
        try:
            resp = requests.post(
                f"{API}{path}",
                headers={"X-API-KEY": _key(), "Content-Type": "application/json"},
                json=body,
                timeout=150,
            )
        except (requests.Timeout, requests.ConnectionError):
            time.sleep(10 * (attempt + 1))
            continue
        if resp.status_code == 429 or resp.status_code >= 500:
            time.sleep(15 * (attempt + 1))
            continue
        if resp.status_code != 200:
            raise RuntimeError(f"Cala {path} -> {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        CACHE.mkdir(parents=True, exist_ok=True)
        cached.write_text(json.dumps({"path": path, "body": body, "response": data}, ensure_ascii=False))
        return data
    raise RuntimeError(f"Cala {path} failed after {retries} retries")


def query(text: str) -> dict:
    """Structured rows + entities for a Cala QL expression or natural-language question."""
    return post("/knowledge/query", {"input": text})
