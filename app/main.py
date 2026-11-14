"""Recount web app: FastAPI serving the API and the static page from one origin.

An optional passcode gate exists (RELAY_GATE=on with RELAY_DEMO_PASSCODE). It is off by default, so the demo is
open; every visitor still gets one signed session cookie so the live Cala lookup caps work per visitor.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
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
import receipt_exits
import receipt_intro
import receipt_pace
from engine import (REGIONS, STAGE_LABEL, STAGES, Snapshot, competitor_coverage, conflicts, discover, fund_portfolio,
                    fund_profile, lead_comes_back, record, tie, timing)
from dispute import dispute
from merge import Builder, canon
from parse import FIRST_NAMES, FUNDISH, line_keys, parse_list

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
_hits: dict[str, list] = {}
_hits_lock = threading.Lock()
# Per IP limits are loose: a venue's Wi-Fi puts many visitors behind one address. Fresh cookies are free, so the
# cookie limit alone does not hold; the IP limit and the daily caps do.
CHECKS_PER_MIN = {"session": 40, "ip": 150}
DISCOVER_PER_MIN = {"session": 30, "ip": 120}
GEMINI_DAY_CAP = int(os.environ.get("GEMINI_DAY_CAP", "1500"))  # Gemini calls per day, all visitors
GEMINI_IP_DAY_CAP = int(os.environ.get("GEMINI_IP_DAY_CAP", "200"))
PAID_IP_DAY_CAP = int(os.environ.get("LIVE_IP_DAY_CAP", "30"))  # live Cala calls per IP per day (live.DAY_CAP still holds)


def _over(bucket: str, key: str, limit: int, window_s: float, cost: int = 1) -> bool:
    """Sliding-window counter in memory. Counts the attempt only when it is allowed."""
    now = time.time()
    with _hits_lock:
        k = f"{bucket}:{key}"
        hits = [t for t in _hits.get(k, []) if now - t < window_s]
        over = len(hits) + cost > limit
        if not over:
            hits.extend([now] * cost)
        _hits[k] = hits
        if len(_hits) > 20000:  # bound memory if someone sprays cookies: drop per-minute session counters only,
            for stale in [x for x in _hits if x.split(":", 1)[0].endswith("-s")]:  # never the daily caps
                del _hits[stale]
        return over


def _too_many(request: Request, bucket: str, per_min: dict) -> bool:
    ip = auth.client_ip(request)
    sess = _session(request)
    if sess == "anon":  # no cookie: one shared 'anon' bucket would let one script lock out every cookieless visitor
        sess = "anon-" + ip
    return _over(bucket + "-ip", ip, per_min["ip"], 60) or _over(bucket + "-s", sess, per_min["session"], 60)


def _gemini_allowed(request: Request) -> bool:
    return (not _over("gemini-ip", auth.client_ip(request), GEMINI_IP_DAY_CAP, 86400)
            and not _over("gemini-all", "all", GEMINI_DAY_CAP, 86400))


def _paid_allowed(request: Request, calls: int) -> bool:
    return not _over("paid-ip", auth.client_ip(request), PAID_IP_DAY_CAP, 86400, cost=calls)


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
    funds_text: str = Field(default="", max_length=32000)  # parse_list reads 8,000 and reports the rest as skipped
    stage: str = "seed"
    target_eur_m: Optional[float] = Field(default=None, ge=0, le=5000)
    investors: list[str] = Field(default_factory=list, max_length=12)
    lead: Optional[str] = Field(default=None, max_length=120)
    company: Optional[str] = Field(default=None, max_length=120)
    competitors: list[str] = Field(default_factory=list, max_length=3)


# lines with a saved Gemini answer (the sample's messy line) stay on the Gemini path, so the sample shows that step
SAVED_LINES = frozenset(line for lines in gemini.SAVED for line in lines)


def _resolve(s: Snapshot, name: str) -> Optional[str]:
    """The fund key a name stands for, with the parser's variants (URL host, 'Fund IV', 'GP Oy', typos)."""
    keys = line_keys(s, name)
    return keys[0] if len(keys) == 1 else s.match_fund(name)


THIN_TOTAL = 8  # a fund with this many rounds in our data is never sent to a paid lookup


def _flat(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _is_person(name: str) -> bool:
    """'Johan Brenner', 'Mikko Kuusi': a first name and a surname, no fund word."""
    words = re.sub(r"[^\w\s]", " ", name.lower()).split()
    return (2 <= len(words) <= 4 and words[0] in FIRST_NAMES and not any(w in FUNDISH for w in words)
            and all(w.isalpha() for w in words))


def _lookup_ok(name: str, pasted: str) -> bool:
    """A paid Cala lookup is offered only for a fund-shaped name that the founder literally pasted."""
    if not live.clean_name(name) or re.search(r"[<>]|https?:|www\.|\.(com|vc|fi|se|io|co|eu|net)\b", name, re.I):
        return False
    if _is_person(name) or len(_flat(name)) < 3:
        return False
    clean = [ln for ln in pasted.splitlines() if not re.search(r"[<>]", ln)]  # never a name lifted out of markup
    return any(_flat(name) in _flat(ln) or name.lower() in ln.lower() for ln in clean)


@app.post("/api/check")
def check(body: Check, request: Request):
    if _too_many(request, "check", CHECKS_PER_MIN):
        raise HTTPException(429, "Too many checks in a minute. Wait a moment.")
    s = snap()
    stage = body.stage if body.stage in STAGES else "seed"
    parsed = parse_list(s, body.funds_text, defer=SAVED_LINES)
    read_by_gemini = None
    lookup_candidates: list[str] = []
    if parsed["unmatched"]:
        saved = tuple(parsed["unmatched"]) in gemini.SAVED
        g = (gemini.extract_funds(parsed["unmatched"]) if saved or _gemini_allowed(request)
             else {"error": "The Gemini budget for today is used up"})
        if "funds" in g:
            seen = {m["key"] for m in parsed["matched"]}
            shown, in_data = [], []  # names to show, and the ones among them that are in our data
            for name in g["funds"]:
                if not live.clean_name(name):
                    continue
                key = _resolve(s, name)
                if key:
                    if key not in seen:
                        seen.add(key)
                        parsed["matched"].append({"key": key, "pasted": name, "via": "gemini"})
                    shown.append(name)
                    in_data.append(name)  # also when the parser already matched it: never "not in our data"
                elif _lookup_ok(name, body.funds_text):
                    shown.append(name)
                    if name not in lookup_candidates:
                        lookup_candidates.append(name)
            read_by_gemini = {"lines": len(parsed["unmatched"]), "funds": shown, "matched": in_data,
                              "not_in_data": [n for n in shown if n not in in_data],
                              "model": g["model"], "ms": g["ms"], "saved": g.get("saved", False)}
            parsed["unmatched"] = []
        else:
            read_by_gemini = {"error": g["error"]}
    my_inv = [k for k in (s.match_fund(x) for x in body.investors if x.strip()) if k]
    comps = [c.strip()[:80] for c in body.competitors if c.strip()][:3]
    rows = []
    for m in parsed["matched"]:
        prof = fund_profile(s, m["key"], stage, body.target_eur_m)
        rows.append({"pasted": m["pasted"], "via": m.get("via", "parser"), **prof, "exit_receipts": _exit_count(m["key"]),
                     "conflicts": conflicts(s, m["key"], comps) if comps else [],
                     "tie": tie(s, m["key"], my_inv, body.company),
                     "portfolio": fund_portfolio(s, m["key"])})
    counts = {}
    for r in rows:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
        # thin data on a fund we never asked Cala about directly: offer a live investor-first query
        if (not r["queried"] and r["known"] < 3 and r["total_rounds"] < THIN_TOTAL and r["verdict"] != "public"
                and r["name"] not in lookup_candidates and not _is_person(r["name"])
                and (_lookup_ok(r["name"], body.funds_text) or _flat(r["key"]) in _flat(body.funds_text))):
            lookup_candidates.append(r["name"])
    lookup_candidates = lookup_candidates[:12]
    lead_key = s.match_fund(body.lead) if body.lead else None
    return {
        "stage": STAGE_LABEL.get(stage, stage), "rows": rows, "unmatched": parsed["unmatched"], "counts": counts,
        "skipped_lines": parsed["skipped_lines"],
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
def discover_funds(body: Discover, request: Request):
    if _too_many(request, "discover", DISCOVER_PER_MIN):
        raise HTTPException(429, "Too many searches in a minute. Wait a moment.")
    if body.region and body.region not in REGIONS:
        raise HTTPException(422, "Unknown region.")
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
        f["exit_receipts"] = _exit_count(f["key"])
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
        if not n or re.search(r"[<>]|https?:|www\.", n) or _is_person(n):
            continue
        k = _resolve(s, n) or canon(n)
        # already asked investor-first, or plenty of rounds already, also under another spelling ('a16z')
        if k in seen or k in s.fund_keys or len(s.by_investor.get(k, [])) >= THIN_TOTAL:
            continue
        seen.add(k)
        names.append(n)
    if not names:
        raise HTTPException(400, "These funds are already in our Cala data, or the names are not valid fund names.")
    sess = _session(request)
    b = live.budget(sess)
    if b["day_left"] < 1 or b["session_left"] < 1 or not _paid_allowed(request, len(names)):
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
    if not _paid_allowed(request, 1):
        raise HTTPException(429, "Live Cala lookups for this demo are used up for now.")
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
    if not _paid_allowed(request, live.GRAPH_CALLS):
        raise HTTPException(429, "Live Cala lookups for this demo are used up for now.")
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


EXITS = receipt_exits.load()  # built offline from cached Cala answers (pipeline/fetch_exits.py); 0 calls at runtime


def _exit_count(key: str) -> int:
    """How many acquisition receipts we hold for a fund: the list's one marker. 0 also for funds never fetched."""
    f = receipt_exits.for_fund(EXITS, key)
    return len(f["receipts"]) + len(f["undisclosed"]) if f else 0


BRIEF = ("id", "company", "date", "stage", "amount_eur_m")


def _pace(s: Snapshot, k: str, stage: str) -> dict:
    """Lead pace per year at the founder's stage band, trimmed to what the strip and its round list show."""
    p = receipt_pace.lead_pace(s, k, stage, include_context=False)
    return {"stage_label": p["stage_label"], "band_label": p["band_label"],
            "years": [{x: y[x] for x in ("year", "led", "joined", "lead_unknown", "follow_on")} for y in p["years"]],
            "summary": p["summary"], "summary_basis": p["summary_basis"], "summary_withheld": p["summary_withheld"],
            "last_lead_at_stage": p["last_lead_at_stage"], "caveat": p["caveat"],
            "rounds": {rid: {x: b.get(x) for x in BRIEF} for rid, b in p["rounds"].items()}}


def _exits(k: str) -> Optional[dict]:
    f = receipt_exits.for_fund(EXITS, k)
    if not f or not (f["receipts"] or f["undisclosed"]):
        return None  # never fetched, or nothing found: the UI hides the section, never says "no exits"
    keep = ("company", "date", "year", "acquirers", "value", "description", "vintage", "sources")
    return {"receipts": [{x: r.get(x) for x in keep} for r in f["receipts"]],
            "undisclosed": [{x: r.get(x) for x in keep} for r in f["undisclosed"]],
            "caveat": f["caveat"], "value_label": receipt_exits.VALUE_LABEL}


SHARED_KEEP = ("rid", "echo_rids", "company", "date", "stage", "amount_eur_m", "n_investors", "with", "fund_led",
               "confirmation")


def _shared(entry: dict) -> dict:
    lr = entry["lead_record"]
    return {"key": entry["key"], "name": entry["name"],
            "lead_record": {x: lr.get(x) for x in ("stage", "verdict", "verdict_label", "led_at_stage", "led",
                                                   "known", "unknown")}
                           | {"last_lead": {x: lr["last_lead"].get(x) for x in BRIEF} if lr.get("last_lead") else None},
            "shared_rounds": [{x: r.get(x) for x in SHARED_KEEP} for r in entry["shared_rounds"]]}


def _intro(s: Snapshot, k: str, stage: str, investors: list[str], lead: Optional[str], company: Optional[str]) -> Optional[dict]:
    """This fund's small shared rounds with the founder's investors, plus other funds that lead the next stage and
    have one. None when the founder added no investors or is already at the last stage."""
    names = [x.strip()[:120] for x in investors if x.strip()][:12]
    if lead and lead.strip():
        names = [lead.strip()[:120]] + names
    nxt = receipt_intro.next_stage_of(stage)
    if not names or not nxt:
        return None
    mine, _ = receipt_intro.resolve_funds(s, names)
    if not mine:
        return None
    paths = receipt_intro.intro_paths(s, names, nxt, None, company, None, limit=50)
    this = None if k in mine else _shared(receipt_intro.pasted_fund_receipts(s, [k], names, nxt, None, company)["funds"][0])
    rest = [e for e in paths["suggestions"] if e["key"] != k]
    return {"next_stage": paths["next_stage"], "investors": [i["name"] for i in paths["investors"] if not i["excluded"]],
            "own_investor": k in mine, "fund": this, "others": [_shared(e) for e in rest[:5]],
            "more": max(0, len(rest) - 5) + paths["more"],
            "footnote": paths["footnote"], "rules": paths["rules"]}


@app.get("/api/fund/{key}/receipts")
def get_fund_receipts(key: str, stage: str = "seed", inv: list[str] = Query(default=[]),
                      lead: Optional[str] = None, company: Optional[str] = None):
    """Three receipt sections for one fund's evidence pane: lead pace, acquisitions, shared-round intro paths.

    All local (snapshot plus the cached exits file), 0 Cala calls. Every round id opens with GET /api/record/{rid}.
    """
    s = snap()
    k = re.sub(r"[^a-z0-9 ]", "", key.lower())[:80]
    if k not in s.by_investor:
        raise HTTPException(404, "Fund not in our Cala data.")
    st = stage if stage in STAGES else "seed"
    return {"key": k, "pace": _pace(s, k, st), "exits": _exits(k),
            "intro": _intro(s, k, st, inv[:12], lead, (company or "")[:120] or None)}


VALIDATION = json.loads((HERE / "validation.json").read_text()) if (HERE / "validation.json").exists() else None
