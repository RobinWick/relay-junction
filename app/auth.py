"""Passcode gate for the private judge demo: signed cookie, 5 tries per IP per 10 minutes."""
from __future__ import annotations

import hashlib
import hmac
import os
import time
from collections import defaultdict, deque

COOKIE = "lc_session"
MAX_TRIES, WINDOW_S, SESSION_S = 5, 600, 60 * 60 * 72
_tries: dict[str, deque] = defaultdict(deque)


def _key() -> bytes:
    key = os.environ.get("COOKIE_KEY")
    if not key:
        raise RuntimeError("COOKIE_KEY is not set")
    return key.encode()


def passcode_ok(given: str) -> bool:
    expected = os.environ.get("RELAY_DEMO_PASSCODE", "")
    return bool(expected) and hmac.compare_digest(given.strip().encode(), expected.encode())


def rate_limited(ip: str) -> bool:
    q, now = _tries[ip], time.time()
    while q and now - q[0] > WINDOW_S:
        q.popleft()
    return len(q) >= MAX_TRIES


def record_try(ip: str) -> None:
    _tries[ip].append(time.time())


def make_cookie() -> str:
    exp = str(int(time.time()) + SESSION_S)
    sig = hmac.new(_key(), exp.encode(), hashlib.sha256).hexdigest()
    return f"{exp}.{sig}"


def cookie_ok(value: str | None) -> bool:
    if not value or "." not in value:
        return False
    exp, sig = value.split(".", 1)
    good = hmac.new(_key(), exp.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, good) and exp.isdigit() and int(exp) > time.time()
