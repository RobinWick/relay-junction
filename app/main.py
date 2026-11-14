"""Recount web app: FastAPI serving the API and the static page from one origin.

An optional passcode gate exists (RELAY_GATE=on with RELAY_DEMO_PASSCODE). It is off by default, so the demo is
open; every visitor still gets one signed session cookie so the live Cala lookup caps work per visitor.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from typing import Optional

from pydantic import BaseModel, Field

import threading
import time

import auth
import gemini
import live
from engine import (STAGE_LABEL, STAGES, Snapshot, competitor_coverage, conflicts, discover, fund_portfolio, fund_profile,
                    lead_comes_back, record, tie, timing)
from dispute import dispute
from merge import Builder, canon
from parse import parse_list

HERE = Path(__file__).parent
STATIC = HERE / "static"
app = FastAPI(title="Recount", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(GZipMiddleware, minimum_size=2000)  # check responses carry each fund's portfolio
SNAP: Optional[Snapshot] = None
SNAP_DICT: Optional[dict] = None
_merge_lock = threading.Lock()


def _db():
    import psycopg
    return psycopg.connect(os.environ["RELAY_DATABASE_URL"], connect_timeout=20)


def load_snapshot() -> Snapshot:
    global SNAP_DICT
    path = os.environ.get("RELAY_SNAPSHOT_PATH")
    if path and Path(path).exists():
        SNAP_DICT = json.loads(Path(path).read_text())
    else:
        with _db() as conn:
            row = conn.execute("select data from snapshot order by created_at desc limit 1").fetchone()
        if not row:
            raise RuntimeError("no snapshot in the database")
        SNAP_DICT = row[0]
    return Snapshot.from_dict(SNAP_DICT)


def snap() -> Snapshot:
    global SNAP
    if SNAP is None:
        SNAP = load_snapshot()
    return SNAP


def merge_live(record_: dict) -> None:
    """Fold a live Cala answer into the snapshot, persist the raw rows and the new snapshot in Aiven."""
    global SNAP, SNAP_DICT
    with _merge_lock:
        snap()
        b = Builder.from_snapshot(SNAP_DICT)
        b.add_fund_record(record_)
        new = b.snapshot(set(SNAP_DICT.get("fund_keys", [])) | {canon(record_["name"])})
        SNAP_DICT, SNAP = new, Snapshot.from_dict(new)
    if os.environ.get("RELAY_SNAPSHOT_PATH"):
        return  # local development: keep live answers in memory only
    try:
        from psycopg.types.json import Jsonb
        with _db() as conn:
            conn.execute("create table if not exists live_funds (id bigserial primary key, fund text not null, "
                         "data jsonb not null, created_at timestamptz default now())")
            conn.execute("insert into live_funds(fund, data) values (%s, %s)", (record_["name"], Jsonb(record_)))
            conn.execute("insert into snapshot(version, data) values (%s, %s) on conflict (version) do nothing",
                         (new["version"], Jsonb(new)))
            conn.execute("delete from snapshot where version not in "
                         "(select version from snapshot order by created_at desc limit 3)")
            conn.commit()
    except Exception as err:  # the in-memory merge already succeeded; log and keep serving
        print(f"persist live result failed: {type(err).__name__}: {err}")


GATE_ON = os.environ.get("RELAY_GATE", "off") == "on"  # passcode gate; off by default since 14.11 (Robin)
OPEN_PATHS = {"/llms.txt", "/login", "/api/login", "/static/styles.css", "/static/login.js", "/static/brand.js",
              "/static/favicon.svg"}


MAX_BODY = 64 * 1024
_check_hits: dict[str, list] = {}


def _too_many_checks(session: str, per_min: int = 40) -> bool:
    now = time.time()
    hits = [t for t in _check_hits.get(session, []) if now - t < 60]
    hits.append(now)
    _check_hits[session] = hits
    if len(_check_hits) > 5000:
        _check_hits.clear()
    return len(hits) > per_min


@app.middleware("http")
async def gate(request: Request, call_next):
    path = request.url.path
    length = request.headers.get("content-length")
    if request.method in ("POST", "PUT", "PATCH") and (not length or not length.isdigit() or int(length) > MAX_BODY):
        return JSONResponse({"error": "Request body missing or too large."}, status_code=413)
    has_session = auth.cookie_ok(request.cookies.get(auth.COOKIE))
    if path in OPEN_PATHS or path.startswith("/static/fonts/") or has_session or not GATE_ON:
        resp = await call_next(request)
        if not has_session and not GATE_ON:  # open demo: still one signed session per visitor for the live caps
            resp.set_cookie(auth.COOKIE, auth.make_cookie(), httponly=True, secure=request.url.scheme == "https",
                            samesite="strict", max_age=auth.SESSION_S)
    elif path.startswith("/api/"):
        resp = JSONResponse({"error": "Enter the demo passcode first."}, status_code=401)
    else:
        resp = RedirectResponse("/login", status_code=303)
    resp.headers["X-Robots-Tag"] = "noindex, nofollow"
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
    ip = auth.client_ip(request)
    if auth.blocked(ip):
        raise HTTPException(429, "Too many wrong tries. Wait 10 minutes.")
    if not auth.passcode_ok(body.passcode):
        auth.record_failure(ip)
        raise HTTPException(401, "That passcode is not right.")
    resp = JSONResponse({"ok": True})
    resp.set_cookie(auth.COOKIE, auth.make_cookie(), httponly=True, secure=request.url.scheme == "https",
                    samesite="strict", max_age=auth.SESSION_S)
    return resp


LLMS = HERE.parent / "llms.txt"  # repo root locally, /root/llms.txt on Modal


@app.get("/llms.txt")
def llms_txt():
    """Plain-text summary for AI readers (llmstxt.org format)."""
    return FileResponse(LLMS, media_type="text/plain; charset=utf-8")


@app.get("/login", response_class=HTMLResponse)
def login_page():
    if not GATE_ON:
        return RedirectResponse("/", status_code=303)
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


_PROOF: dict = {}


@app.get("/api/proof")
def proof():
    """The first-run recount strip: two funds from the sample list, counted live from the snapshot, never hardcoded.

    Voima Ventures leads nearly every round it is in; FJ Labs mostly follows. Each round is one dot, so only the
    fields a dot and its hover card need are sent.
    """
    s = snap()
    if _PROOF.get("version") == s.version:
        return _PROOF["body"]
    funds = []
    for name in ("Voima Ventures", "FJ Labs"):
        key = s.match_fund(name)
        if not key:
            continue
        p = fund_profile(s, key, "seed", 3.0)
        keep = ("id", "company", "date", "t", "stage", "amount_eur_m", "leads")
        funds.append({k: p[k] for k in ("key", "name", "verdict", "verdict_label", "led", "known", "unknown", "disputed")}
                     | {"rounds_led": [{k: x[k] for k in keep} for x in p["rounds_led"]],
                        "rounds_joined": [{k: x[k] for k in keep} for x in p["rounds_joined"]]})
    body = {"stage": STAGE_LABEL["seed"], "target_eur_m": 3, "funds": funds}
    _PROOF.update(version=s.version, body=body)
    return body


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
def check(body: Check, request: Request):
    if _too_many_checks(_session(request)):
        raise HTTPException(429, "Too many checks in a minute. Wait a moment.")
    s = snap()
    stage = body.stage if body.stage in STAGES else "seed"
    parsed = parse_list(s, body.funds_text)
    read_by_gemini = None
    lookup_candidates: list[str] = []
    if parsed["unmatched"]:
        g = gemini.extract_funds(parsed["unmatched"])
        if "funds" in g:
            seen = {m["key"] for m in parsed["matched"]}
            found = []
            for name in g["funds"]:
                if not live.clean_name(name):
                    continue
                key = s.match_fund(name)
                if key and key not in seen:
                    seen.add(key)
                    parsed["matched"].append({"key": key, "pasted": name, "via": "gemini"})
                    found.append(name)
                elif not key and canon(name) and name not in lookup_candidates:
                    lookup_candidates.append(name)
            read_by_gemini = {"lines": len(parsed["unmatched"]), "funds": g["funds"], "matched": found,
                              "model": g["model"], "ms": g["ms"], "saved": g.get("saved", False)}
            parsed["unmatched"] = []
        else:
            read_by_gemini = {"error": g["error"]}
    my_inv = [k for k in (s.match_fund(x) for x in body.investors if x.strip()) if k]
    comps = [c.strip()[:80] for c in body.competitors if c.strip()][:3]
    rows = []
    for m in parsed["matched"]:
        prof = fund_profile(s, m["key"], stage, body.target_eur_m)
        rows.append({"pasted": m["pasted"], "via": m.get("via", "parser"), **prof,
                     "conflicts": conflicts(s, m["key"], comps) if comps else [],
                     "tie": tie(s, m["key"], my_inv, body.company),
                     "portfolio": fund_portfolio(s, m["key"])})
    counts = {}
    for r in rows:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
        # thin data on a fund we never asked Cala about directly: offer a live investor-first query
        if not r["queried"] and r["known"] < 3 and r["verdict"] != "public" and r["name"] not in lookup_candidates:
            lookup_candidates.append(r["name"])
    lookup_candidates = lookup_candidates[:12]
    lead_key = s.match_fund(body.lead) if body.lead else None
    return {
        "stage": STAGE_LABEL.get(stage, stage), "rows": rows, "unmatched": parsed["unmatched"], "counts": counts,
        "conflict_count": sum(1 for r in rows if any(c["level"] == "led" for c in r["conflicts"])),
        "competitors": competitor_coverage(s, comps) if comps else {},
        "my_investors": [s.name(k) for k in my_inv],
        "lead_back": lead_comes_back(s, lead_key) if lead_key else None,
        "timing": timing(s, stage),
        "read_by_gemini": read_by_gemini,
        "lookup_candidates": lookup_candidates,
    }


class Discover(BaseModel):
    stage: str = "seed"
    target_eur_m: Optional[float] = Field(default=None, ge=0, le=5000)
    region: Optional[str] = Field(default=None, max_length=20)
    investors: list[str] = Field(default_factory=list, max_length=12)
    competitors: list[str] = Field(default_factory=list, max_length=3)


@app.post("/api/discover")
def discover_funds(body: Discover):
    s = snap()
    stage = body.stage if body.stage in STAGES else "seed"
    out = discover(s, stage, body.target_eur_m, body.region)
    my_inv = [k for k in (s.match_fund(x) for x in body.investors if x.strip()) if k]
    comps = [c.strip()[:80] for c in body.competitors if c.strip()][:3]
    out["funds"] = [f for f in out["funds"] if f["key"] not in my_inv]  # never suggest pitching your own investor
    for f in out["funds"]:
        f["conflicts"] = conflicts(s, f["key"], comps) if comps else []
        f["tie"] = tie(s, f["key"], my_inv, None)
        f["pasted"] = f["name"]
        f["portfolio"] = fund_portfolio(s, f["key"])
    return out


class Lookup(BaseModel):
    names: list[str] = Field(max_length=12)


def _session(request: Request) -> str:
    return (request.cookies.get(auth.COOKIE) or "anon")[-16:]


@app.post("/api/lookup")
def lookup_start(body: Lookup, request: Request):
    s = snap()
    names, seen = [], set()
    for raw in body.names:
        n = live.clean_name(raw)
        k = canon(n) if n else None
        if not n or k in seen or k in s.fund_keys:
            continue
        seen.add(k)
        names.append(n)
    if not names:
        raise HTTPException(400, "These funds are already in our Cala data, or the names are not valid fund names.")
    sess = _session(request)
    b = live.budget(sess)
    if b["day_left"] < 1 or b["session_left"] < 1:
        raise HTTPException(429, "Live Cala lookups for this demo are used up for now.")
    return {**live.start(names, sess, merge_live), "budget": live.budget(sess)}


@app.get("/api/lookup/{job_id}")
def lookup_status(job_id: str, request: Request):
    v = live.view(job_id[:20])
    if not v:
        raise HTTPException(404, "No such lookup.")
    return {**v, "budget": live.budget(_session(request))}


@app.get("/api/record/{rid}")
def get_record(rid: int):
    rec = record(snap(), rid)
    if not rec:
        raise HTTPException(404, "No such round.")
    return rec


@app.post("/api/source/{rid}")
def get_source(rid: int, request: Request):
    """Sourced answer for one round from Cala /v1/knowledge/search (cached per round, stored in Aiven)."""
    from merge import round_key, summarize_search
    s = snap()
    if not 0 <= rid < len(s.rounds):
        raise HTTPException(404, "No such round.")
    r = s.rounds[rid]
    if r.get("source"):
        return r["source"]
    try:
        res = live.search_round(r, _session(request))
    except RuntimeError:
        raise HTTPException(429, "Live Cala lookups for this demo are used up for now.")
    except Exception as err:
        raise HTTPException(502, f"Cala did not answer ({type(err).__name__}). Try again.")
    src = {**summarize_search(res), "question": live.source_question(r)}
    r["source"] = src
    r["disputed"] = dispute(r, s.names, set(s.names))  # shown now; lead counts follow on the next rebuild
    if not os.environ.get("RELAY_SNAPSHOT_PATH"):
        try:
            from psycopg.types.json import Jsonb
            with _db() as conn:
                conn.execute("create table if not exists round_sources (key text primary key, data jsonb not null, "
                             "created_at timestamptz default now())")
                conn.execute("insert into round_sources(key, data) values (%s, %s) on conflict (key) do update set data = excluded.data",
                             (round_key(r), Jsonb(src)))
                conn.commit()
        except Exception as err:
            print(f"persist source failed: {type(err).__name__}")
    return {**src, "disputed": r["disputed"]}


@app.post("/api/graph/{rid}")
def get_graph(rid: int, request: Request):
    """Cross-check one round against Cala's entity graph (FundingRound entities with is_lead), cached per round."""
    from graph import agreement
    from merge import round_key
    s = snap()
    if not 0 <= rid < len(s.rounds):
        raise HTTPException(404, "No such round.")
    r = s.rounds[rid]
    if r.get("graph"):
        return r["graph"]
    try:
        check = live.graph_round(r, s.entities.get("c:" + r["ckey"]), _session(request))
    except RuntimeError:
        raise HTTPException(429, "Live Cala lookups for this demo are used up for now.")
    except Exception as err:
        raise HTTPException(502, f"Cala did not answer ({type(err).__name__}). Try again.")
    g = {**check, "agreement": agreement([s.name(k) for k in r["leads"]], check, r["t"])}
    r["graph"] = g
    if not os.environ.get("RELAY_SNAPSHOT_PATH"):
        try:
            from psycopg.types.json import Jsonb
            with _db() as conn:
                conn.execute("create table if not exists round_graph (key text primary key, data jsonb not null, "
                             "created_at timestamptz default now())")
                conn.execute("insert into round_graph(key, data) values (%s, %s) on conflict (key) do update set data = excluded.data",
                             (round_key(r), Jsonb(g)))
                conn.commit()
        except Exception as err:
            print(f"persist graph failed: {type(err).__name__}")
    return g


@app.get("/api/fund/{key}")
def get_fund(key: str, stage: str = "seed", target: Optional[float] = None):
    s = snap()
    k = re.sub(r"[^a-z0-9 ]", "", key.lower())[:80]
    if k not in s.by_investor:
        raise HTTPException(404, "Fund not in our Cala data.")
    return fund_profile(s, k, stage if stage in STAGES else "seed", target)


VALIDATION = json.loads((HERE / "validation.json").read_text()) if (HERE / "validation.json").exists() else None
