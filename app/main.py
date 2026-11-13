"""Lead Check web app: FastAPI serving the API and the static page from one origin, behind a passcode gate."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from typing import Optional

from pydantic import BaseModel, Field

import auth
from engine import STAGE_LABEL, STAGES, Snapshot, competitor_coverage, conflicts, fund_profile, lead_comes_back, record, tie, timing
from parse import parse_list

HERE = Path(__file__).parent
STATIC = HERE / "static"
app = FastAPI(title="Lead Check", docs_url=None, redoc_url=None, openapi_url=None)
SNAP: Snapshot | None = None


def load_snapshot() -> Snapshot:
    path = os.environ.get("RELAY_SNAPSHOT_PATH")
    if path and Path(path).exists():
        return Snapshot.from_dict(json.loads(Path(path).read_text()))
    import psycopg
    with psycopg.connect(os.environ["RELAY_DATABASE_URL"], connect_timeout=20) as conn:
        row = conn.execute("select data from snapshot order by created_at desc limit 1").fetchone()
    if not row:
        raise RuntimeError("no snapshot in the database")
    return Snapshot.from_dict(row[0])


def snap() -> Snapshot:
    global SNAP
    if SNAP is None:
        SNAP = load_snapshot()
    return SNAP


OPEN_PATHS = {"/login", "/api/login", "/static/styles.css", "/static/login.js", "/static/favicon.svg"}


@app.middleware("http")
async def gate(request: Request, call_next):
    path = request.url.path
    if path in OPEN_PATHS or path.startswith("/static/fonts/") or auth.cookie_ok(request.cookies.get(auth.COOKIE)):
        resp = await call_next(request)
    elif path.startswith("/api/"):
        resp = JSONResponse({"error": "Enter the demo passcode first."}, status_code=401)
    else:
        resp = RedirectResponse("/login", status_code=303)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Content-Security-Policy"] = ("default-src 'self'; img-src 'self' data:; style-src 'self'; "
                                               "script-src 'self'; connect-src 'self'; frame-ancestors 'none'")
    return resp


class Login(BaseModel):
    passcode: str = Field(max_length=200)


@app.post("/api/login")
def login(body: Login, request: Request):
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0].strip()
    if auth.rate_limited(ip):
        raise HTTPException(429, "Too many tries. Wait 10 minutes.")
    auth.record_try(ip)
    if not auth.passcode_ok(body.passcode):
        raise HTTPException(401, "That passcode is not right.")
    resp = JSONResponse({"ok": True})
    resp.set_cookie(auth.COOKIE, auth.make_cookie(), httponly=True, secure=request.url.scheme == "https",
                    samesite="strict", max_age=auth.SESSION_S)
    return resp


@app.get("/login", response_class=HTMLResponse)
def login_page():
    return FileResponse(STATIC / "login.html")


@app.get("/", response_class=HTMLResponse)
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/method", response_class=HTMLResponse)
def method_page():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/api/meta")
def meta():
    s = snap()
    return {**s.stats, "retrieved": s.retrieved, "version": s.version,
            "stages": [{"key": k, "label": STAGE_LABEL[k]} for k in STAGES if k != "growth"],
            "validation": VALIDATION}


@app.get("/api/suggest")
def suggest(q: str = ""):
    return snap().suggest(q[:60])


class Check(BaseModel):
    funds_text: str = Field(default="", max_length=8000)
    stage: str = "seed"
    target_eur_m: Optional[float] = Field(default=None, ge=0, le=5000)
    investors: list[str] = Field(default_factory=list, max_length=12)
    lead: Optional[str] = Field(default=None, max_length=120)
    company: Optional[str] = Field(default=None, max_length=120)
    competitors: list[str] = Field(default_factory=list, max_length=3)


@app.post("/api/check")
def check(body: Check):
    s = snap()
    stage = body.stage if body.stage in STAGES else "seed"
    parsed = parse_list(s, body.funds_text)
    my_inv = [k for k in (s.match_fund(x) for x in body.investors if x.strip()) if k]
    comps = [c.strip()[:80] for c in body.competitors if c.strip()][:3]
    rows = []
    for m in parsed["matched"]:
        prof = fund_profile(s, m["key"], stage, body.target_eur_m)
        rows.append({"pasted": m["pasted"], **prof,
                     "conflicts": conflicts(s, m["key"], comps) if comps else [],
                     "tie": tie(s, m["key"], my_inv, body.company)})
    counts = {}
    for r in rows:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    lead_key = s.match_fund(body.lead) if body.lead else None
    return {
        "stage": STAGE_LABEL.get(stage, stage), "rows": rows, "unmatched": parsed["unmatched"], "counts": counts,
        "conflict_count": sum(1 for r in rows if any(c["level"] == "led" for c in r["conflicts"])),
        "competitors": competitor_coverage(s, comps) if comps else {},
        "my_investors": [s.name(k) for k in my_inv],
        "lead_back": lead_comes_back(s, lead_key) if lead_key else None,
        "timing": timing(s, stage),
    }


@app.get("/api/record/{rid}")
def get_record(rid: int):
    rec = record(snap(), rid)
    if not rec:
        raise HTTPException(404, "No such round.")
    return rec


@app.get("/api/fund/{key}")
def get_fund(key: str, stage: str = "seed", target: Optional[float] = None):
    s = snap()
    k = re.sub(r"[^a-z0-9 ]", "", key.lower())[:80]
    if k not in s.by_investor:
        raise HTTPException(404, "Fund not in our Cala data.")
    return fund_profile(s, k, stage if stage in STAGES else "seed", target)


VALIDATION = json.loads((HERE / "validation.json").read_text()) if (HERE / "validation.json").exists() else None
