"""Passcode gate for the private judge demo: signed cookie, failed-login limits per IP and globally."""
from __future__ import annotations

import hashlib
import hmac
import os
import time
from collections import defaultdict, deque

COOKIE = "lc_session"
MAX_FAILS_PER_IP, MAX_FAILS_GLOBAL, WINDOW_S, SESSION_S = 8, 60, 600, 60 * 60 * 72
_fails: dict[str, deque] = defaultdict(deque)
_global: deque = deque()


def client_ip(request) -> str:
    """The proxy appends the real client to X-Forwarded-For, so trust the right-most entry, never the left-most."""
    xff = request.headers.get("x-forwarded-for", "")
    if xff.strip():
        return xff.split(",")[-1].strip()[:64]
    return (request.client.host if request.client else "?")[:64]


def _prune(q: deque, now: float) -> None:
    while q and now - q[0] > WINDOW_S:
        q.popleft()


def _key() -> bytes:
    key = os.environ.get("COOKIE_KEY")
    if not key:
        raise RuntimeError("COOKIE_KEY is not set")
    return key.encode()


def passcode_ok(given: str) -> bool:
    expected = os.environ.get("RELAY_DEMO_PASSCODE", "")
    return bool(expected) and hmac.compare_digest(given.strip().encode(), expected.encode())


def blocked(ip: str) -> bool:
    now = time.time()
    _prune(_global, now)
    q = _fails.get(ip)
    if q is not None:
        _prune(q, now)
        if not q:
            _fails.pop(ip, None)
            q = None
    return len(_global) >= MAX_FAILS_GLOBAL or (q is not None and len(q) >= MAX_FAILS_PER_IP)


def record_failure(ip: str) -> None:
    now = time.time()
    _fails[ip].append(now)
    _global.append(now)
    if len(_fails) > 5000:  # bound memory if someone sprays addresses
        for k in list(_fails)[:2500]:
            _fails.pop(k, None)


def make_cookie() -> str:
    exp = str(int(time.time()) + SESSION_S)
    sig = hmac.new(_key(), exp.encode(), hashlib.sha256).hexdigest()
    return f"{exp}.{sig}"


def cookie_ok(value: str | None) -> bool:
    if not value or "." not in value or len(value) > 200:
        return False
    exp, sig = value.split(".", 1)
    good = hmac.new(_key(), exp.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, good) and exp.isdigit() and int(exp) > time.time()
