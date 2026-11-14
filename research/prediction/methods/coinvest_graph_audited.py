"""Warm-path graph method (slug coinvest_graph).

Idea: the next lead is reachable from the company's current investors through the co-investment graph.
For every test round we rebuild, from ctx.past ONLY (rounds with t < test_t - EPS), a weighted investor graph:
  - co-invest edges: investors in the same round, weight = recency decay * size factor / (round size - 1)
  - hand-off edges (directed): investor of an earlier round of company C -> lead of a later round of C
    (both rounds in the past), weight = recency decay of the later round.
Then personalised PageRank (random walk with restart) from ctx.current (latest round weighted up), and the
walk score is combined log-linearly with the candidate's fit as a LEAD: decayed lead count at the target
stage, lead-amount fit, country activity.

All per-round statistics are recomputed per test round from the masked past (no global fit). No FUND_KEYS.
Tuning: grid over weights on a DEV split (test rounds with year <= 2023), then the chosen variant is
reported on the full test set by harness.evaluate().

Run: python3 methods/coinvest_graph.py            (sweep on dev + final evaluate of best variants)
     python3 methods/coinvest_graph.py --final    (only the final chosen variants)

AUDITED COPY (2026-11-14). Changes vs coinvest_graph.py:
  1. Data-selection leak (harness/snapshot level, not in the original method code). 72% of snapshot rounds are
     investor_first-only: they exist only because a fund was crawled. The crawled list
     (relay/pipeline/fetch_funds.py fund_list) is a hand list (NORDIC) plus the top-140 investors by frequency
     across ALL company-first rounds through 2026, test rounds and their answers included. So which funds have a
     rich, well-connected past depends on the answers.
     Default mode "--honest-crawl": for each test round, re-run the fund_list rule on company-first rounds dated
     before the test round only; an investor_first-only round is usable only if it came from a fund that would
     have been picked then. Everything (incidence features, co-invest edges, hand-off edges, restart, insider
     terms) uses only usable rounds.
     --cf-only: stricter lower bound, drop every investor_first-only round.
     --keep-fund-crawl: original information set (reproduces the original numbers).
     --rule-at-end: control for the rule replication (165/194 funds match): same rule on ALL company-first data.
       honest-crawl vs rule-at-end isolates the time leak; rule-at-end vs keep-crawl is replication noise.
     --full-company-past: restart + insider terms keep the harness's full company_past (only with the two above).
     --baselines: harness stage_leads / last_lead_again on the same usable-round information set.
  2. Tie-break: np.argsort(-sc) is unstable, so ties were broken by array position, which depends on the set of
     investors in ALL rounds (future ones included). Now a stable sort over alphabetical INV order. (Effect: nil.)
Weights are unchanged (BEST_ALL / BEST_OUT from the original dev sweep). No re-tuning on the corrected data.
"""
from __future__ import annotations

import ast
import bisect
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import harness as H  # noqa: E402

R = H.ROUNDS
NR = len(R)
T = np.array([r["t"] for r in R])

# ---------- static index (structure only; every use below is masked by the time cut) ----------
INV = sorted(set().union(*(H.investors(r) for r in R)))
IDX = {k: i for i, k in enumerate(INV)}
NI = len(INV)

if "--cf-only" in sys.argv:
    MODE = "cf-only"
elif "--keep-fund-crawl" in sys.argv:
    MODE = "keep-crawl"
elif "--rule-at-end" in sys.argv:
    MODE = "rule-at-end"  # control: same replicated rule, but on ALL company-first data (uses the future)
else:
    MODE = "honest-crawl"
FULL_CP = "--full-company-past" in sys.argv
RIDX = {id(r): k for k, r in enumerate(R)}


def _is_cf(r: dict) -> bool:
    return any(s.get("path") == "company_first" for s in r.get("sources") or [])


IS_CF = np.array([_is_cf(r) for r in R], dtype=bool)

# ---- which crawled fund produced each investor_first source (funds.jsonl name -> crawl key) ----
_SRC = Path(__file__).resolve().parents[3] / "relay" / "pipeline" / "fetch_funds.py"
_FUNDS = H.SNAP.parent / "funds.jsonl"
_NAME2KEY = {json.loads(l)["name"]: json.loads(l)["key"] for l in _FUNDS.open()}
_Q = re.compile(r"^(?:List every funding round that (.+?) invested in,|Funding rounds (.+?) invested in during)")


def _crawl_funds(r: dict) -> set:
    out = set()
    for s in r.get("sources") or []:
        if s.get("path") != "investor_first":
            continue
        mt = _Q.match(s.get("query") or "")
        nm = (mt.group(1) or mt.group(2)) if mt else None
        out.add(_NAME2KEY.get(nm, "?live:" + str(nm)))  # live-added funds (e.g. Wave Ventures) are never time-honest
    return out


ROUND_FUNDS = [_crawl_funds(r) for r in R]

# fund_list() rule from relay/pipeline/fetch_funds.py, copied (that module imports the paid API client).
_tree = ast.parse(_SRC.read_text())
_consts = {t.targets[0].id: ast.literal_eval(t.value) for t in _tree.body
           if isinstance(t, ast.Assign) and isinstance(t.targets[0], ast.Name) and t.targets[0].id in ("HUBS", "NORDIC")}
HUBS, NORDIC = _consts["HUBS"], _consts["NORDIC"]
TOP_N = 140
_JUNK = re.compile(r"\b(angel|individual|undisclosed|disclosed|founder|existing|shareholder|europa|council|"
                   r"innvierte|grunderfonds|gr nderfonds|almi|eit|government|ministry|bank|amf)\b")


def _core(key: str) -> str:
    return re.sub(r"\b(ventures?|capital|vc|partners|fund|management|invest(ments)?)\b", "", key).replace(" ", "")


def _ikey(name: str) -> str:  # same as normalize.investor_key for these plain names
    sys.path.insert(0, str(_SRC.parent))
    from normalize import investor_key
    return investor_key(name)


_NORDIC_CORES = {}
for _n in NORDIC:
    _NORDIC_CORES.setdefault(_core(_ikey(_n)), _ikey(_n))


def picked_cores(cut: int) -> set:
    """fund_list(140) recomputed on company-first rounds with index < cut (i.e. dated before the test round)."""
    joined: dict = defaultdict(int)
    for k in range(cut):
        if IS_CF[k]:
            for x in H.investors(R[k]):
                joined[x] += 1
    picked = dict(_NORDIC_CORES)
    for key, _ in sorted(joined.items(), key=lambda kv: (-kv[1], kv[0])):
        if len(picked) >= TOP_N + len(NORDIC):
            break
        if key in HUBS or not key or _JUNK.search(key):
            continue
        picked.setdefault(_core(key), key)
    return set(picked)


_ALLOW: dict = {}


def allow_mask(cut: int) -> np.ndarray:
    """Rounds usable as information for a test round whose past is R[:cut]."""
    if MODE == "keep-crawl":
        return np.ones(NR, dtype=bool)
    if MODE == "cf-only":
        return IS_CF.copy()
    if MODE == "rule-at-end":
        cut_rule = NR
    else:
        cut_rule = cut
    if cut_rule not in _ALLOW:
        cores = picked_cores(cut_rule)
        _ALLOW[cut_rule] = np.array([IS_CF[k] or any(_core(f) in cores for f in ROUND_FUNDS[k] if not f.startswith("?"))
                                     for k in range(NR)], dtype=bool)
    return _ALLOW[cut_rule]


STAGES = ["pre-seed", "seed", "series a", "series b", "series c", "series d", "series e", "series f", "growth"]
SPOS = {s: i for i, s in enumerate(STAGES)}

inc_r, inc_i, inc_lead = [], [], []
for k, r in enumerate(R):
    leads = set(r.get("leads") or [])
    for x in H.investors(r):
        inc_r.append(k)
        inc_i.append(IDX[x])
        inc_lead.append(x in leads)
inc_r = np.array(inc_r)
inc_i = np.array(inc_i)
inc_lead = np.array(inc_lead, dtype=bool)
inc_stage = np.array([SPOS.get(R[k].get("stage"), -1) for k in inc_r])
inc_country = [R[k].get("country") for k in inc_r]
inc_logamt = np.array([math.log1p(R[k]["amount_eur_m"]) if R[k].get("amount_eur_m") else np.nan for k in inc_r])

# co-invest edges (undirected, both directions), base weight 1/(n-1); per-round amount for size factor
e_src, e_dst, e_r, e_base = [], [], [], []
for k, r in enumerate(R):
    xs = sorted(H.investors(r))
    n = len(xs)
    if n < 2:
        continue
    for a in xs:
        for b in xs:
            if a != b:
                e_src.append(IDX[a]); e_dst.append(IDX[b]); e_r.append(k); e_base.append(1.0 / (n - 1))
e_src = np.array(e_src); e_dst = np.array(e_dst); e_r = np.array(e_r); e_base = np.array(e_base)
e_amt = np.array([R[k].get("amount_eur_m") or 0.0 for k in e_r])

# hand-off edges: investors of an earlier round r1 of the same company -> leads of a later round r2.
# Stored per (r1, r2) pair so a test round can drop pairs whose rounds are not usable; deduped per (a, l, r2).
h_src, h_dst, h_r, h_r1 = [], [], [], []
for ck, rs in H.BY_COMPANY.items():
    for r2 in rs:
        leads = r2.get("leads") or []
        if not leads:
            continue
        k2 = RIDX[id(r2)]
        for r1 in rs:
            if r1["t"] < r2["t"] - H.EPS:
                k1 = RIDX[id(r1)]
                for a in H.investors(r1):
                    for l in leads:
                        if a != l:
                            h_src.append(IDX[a]); h_dst.append(IDX[l]); h_r.append(k2); h_r1.append(k1)
h_src = np.array(h_src, dtype=int); h_dst = np.array(h_dst, dtype=int)
h_r = np.array(h_r, dtype=int); h_r1 = np.array(h_r1, dtype=int)


def handoff_edges(cut: int, allow: np.ndarray):
    hm = (h_r < cut) & allow[h_r] & allow[h_r1]
    trip = np.unique(np.stack([h_src[hm], h_dst[hm], h_r[hm]]), axis=1) if hm.any() else np.zeros((3, 0), dtype=int)
    return trip[0], trip[1], trip[2]


def cut_of(t: float) -> int:
    return bisect.bisect_left(H.TIMES, t - H.EPS)


def decay(dt: np.ndarray, half: float) -> np.ndarray:
    return np.power(0.5, np.maximum(dt, 0.0) / half)


def ppr(src, dst, w, restart: np.ndarray, alpha: float, iters: int = 30) -> np.ndarray:
    """Random walk with restart; alpha = restart probability. Dangling mass goes back to restart."""
    out = np.bincount(src, weights=w, minlength=NI)
    pw = w / np.where(out[src] > 0, out[src], 1.0)
    x = restart.copy()
    for _ in range(iters):
        flow = np.bincount(dst, weights=x[src] * pw, minlength=NI)
        dangling = x[out == 0].sum()
        x = alpha * restart + (1 - alpha) * (flow + dangling * restart)
    return x


# ---------------- per-test-round features (cached) ----------------
_FEAT: dict = {}


def features(ctx: H.Context, half: float, alpha: float, size_beta: float, hand_w: float) -> dict:
    gp = (half, alpha, size_beta, hand_w)
    if _FEAT.get("gp") != gp:  # keep one graph setting in memory
        _FEAT.clear()
        _FEAT["gp"] = gp
    key = ctx.test["id"]
    if key in _FEAT:
        return _FEAT[key]
    tg = ctx.target
    t0 = tg["t"]
    cut = cut_of(t0)
    assert cut == len(ctx.past)  # same cut as the harness
    # incidence features
    allow = allow_mask(cut)
    m = (inc_r < cut) & allow[inc_r]
    d = decay(t0 - T[inc_r[m]], half)
    ii = inc_i[m]
    lm = inc_lead[m]
    seen = np.bincount(ii, minlength=NI) > 0
    lead_cnt = np.bincount(ii[lm], weights=d[lm], minlength=NI)
    act = np.bincount(ii, weights=d, minlength=NI)
    sp = SPOS.get(tg.get("stage"), -1)
    st = inc_stage[m]
    if sp >= 0:
        sim = np.where(st >= 0, np.power(0.4, np.abs(st - sp)), 0.15)
    else:
        sim = np.full(len(st), 0.5)
    stage_lead = np.bincount(ii[lm], weights=(d * sim)[lm], minlength=NI)
    # amount fit of rounds the candidate led
    amt = tg.get("amount_eur_m")
    la = inc_logamt[m]
    ok = lm & ~np.isnan(la)
    cnt_a = np.bincount(ii[ok], minlength=NI).astype(float)
    s1 = np.bincount(ii[ok], weights=la[ok], minlength=NI)
    s2 = np.bincount(ii[ok], weights=la[ok] ** 2, minlength=NI)
    if amt:
        mu = np.where(cnt_a > 0, s1 / np.maximum(cnt_a, 1), np.nan)
        var = np.where(cnt_a > 1, s2 / np.maximum(cnt_a, 1) - mu ** 2, 0.0)
        sd2 = np.maximum(var, 0) + 0.5
        z = math.log1p(amt)
        amt_fit = np.where(cnt_a > 0, np.exp(-((z - np.nan_to_num(mu)) ** 2) / (2 * sd2)), 0.3)
    else:
        amt_fit = np.full(NI, 0.5)
    # country activity
    c = tg.get("country")
    if c:
        cm = np.array([inc_country[j] == c for j in np.nonzero(m)[0]], dtype=bool)
        country = np.bincount(ii[cm], weights=d[cm], minlength=NI)
    else:
        country = np.zeros(NI)
    # graph
    em = (e_r < cut) & allow[e_r]
    w =e_base[em] * decay(t0 - T[e_r[em]], half) * np.power(1.0 + e_amt[em], size_beta)
    src, dst = e_src[em], e_dst[em]
    hs, hd, hr = handoff_edges(cut, allow)
    if hand_w > 0:
        hw = hand_w * decay(t0 - T[hr], half)
        src = np.concatenate([src, hs]); dst = np.concatenate([dst, hd]); w = np.concatenate([w, hw])
    restart = np.zeros(NI)
    cp = ctx.company_past if (FULL_CP or MODE == "keep-crawl") else [o for o in ctx.company_past if allow[RIDX[id(o)]]]
    for j, o in enumerate(cp):
        rec = 2.0 ** (j - len(cp) + 1)  # latest round weight 1, previous 0.5, ...
        for x in H.investors(o):
            restart[IDX[x]] += rec * (2.0 if x in (o.get("leads") or []) else 1.0)
    if restart.sum() > 0:
        restart /= restart.sum()
        pr = ppr(src, dst, w, restart, alpha)
    else:
        pr = np.zeros(NI)
    # direct one-hop hand-off from current investors
    if len(cp):
        hw = decay(t0 - T[hr], half)
        handoff = np.bincount(hd, weights=hw * restart[hs], minlength=NI)
    else:
        handoff = np.zeros(NI)
    # insider info
    last_leads = set()
    any_lead = set()
    for o in cp:
        any_lead |= set(o.get("leads") or [])
    if cp:
        last_leads = set(cp[-1].get("leads") or [])
    current = set().union(*(H.investors(o) for o in cp)) if cp else set()
    f = dict(seen=seen, lead_cnt=lead_cnt, act=act, stage_lead=stage_lead, amt_fit=amt_fit, country=country,
             pr=pr, handoff=handoff, last_leads=last_leads, any_lead=any_lead, current=current)
    _FEAT[key] = f
    return f


def make_rank(p: dict):
    """p: half, alpha, size_beta, hand_w (graph) + weights w_pr, w_stage, w_amt, w_cty, w_hand, w_act, ins_*"""
    def rank(ctx: H.Context) -> list[str]:
        f = features(ctx, p["half"], p["alpha"], p["size_beta"], p["hand_w"])
        pr = f["pr"]
        prn = pr / (pr.max() + 1e-12)
        sc = (p["w_pr"] * np.log(prn + p["eps_pr"])
              + p["w_stage"] * np.log(f["stage_lead"] + 0.05 * f["act"] + p["eps_stage"])
              + p["w_amt"] * np.log(f["amt_fit"] + 0.05)
              + p["w_cty"] * np.log(f["country"] + 0.1)
              + p["w_hand"] * np.log(f["handoff"] / (f["handoff"].max() + 1e-12) + 0.01))
        if not ctx.outside_only:
            cur = np.zeros(NI, dtype=bool)
            for x in f["current"]:
                cur[IDX[x]] = True
            sc = sc + p["ins_cur"] * cur
            for x in f["any_lead"]:
                sc[IDX[x]] += p["ins_anylead"]
            for x in f["last_leads"]:
                sc[IDX[x]] += p["ins_lastlead"]
        else:
            for x in ctx.current:
                sc[IDX[x]] = -1e9
        sc = np.where(f["seen"], sc, -np.inf)
        top = np.argsort(-sc, kind="stable")[:60]
        return [INV[i] for i in top if np.isfinite(sc[i]) and sc[i] > -1e8]
    return rank


BASE = dict(half=3.0, alpha=0.3, size_beta=0.0, hand_w=0.0, w_pr=1.0, eps_pr=1e-3, w_stage=0.5, eps_stage=0.05,
            w_amt=0.3, w_cty=0.2, w_hand=0.0, ins_cur=4.0, ins_anylead=2.0, ins_lastlead=3.0)


# ---------------- fast dev scoring (mirrors harness logic, used only for tuning) ----------------
_CTX: dict = {}


def quick(rank, outside: bool, rounds) -> dict:
    hits = {k: 0 for k in H.KS}
    n = 0
    for r in rounds:
        key = (r["id"], outside)
        if key not in _CTX:
            _CTX[key] = H.context(r, outside)
        ctx = _CTX[key]
        truth = set(r["leads"])
        if outside:
            truth -= ctx.current
            if not truth:
                continue
        ranked = [x for x in rank(ctx) if not (outside and x in ctx.current)]
        n += 1
        for k in H.KS:
            hits[k] += bool(truth & set(ranked[:k]))
    return {k: round(hits[k] / max(n, 1), 3) for k in H.KS} | {"n": n}


DEV = [r for r in H.TEST if r["year"] <= 2023]
HOLD = [r for r in H.TEST if r["year"] >= 2024]


def sweep(setting: str):
    outside = setting == "OUTSIDE"
    best = dict(BASE)
    if outside:
        best.update(ins_cur=0, ins_anylead=0, ins_lastlead=0)

    def score(p):
        q = quick(make_rank(p), outside, DEV)
        return q[5] + 0.3 * q[20]

    cur_s = score(best)
    print(setting, "start", cur_s, flush=True)
    grid = [
        ("half", [1.0, 2.0, 3.0, 5.0, 10.0]),
        ("alpha", [0.1, 0.2, 0.3, 0.5, 0.7]),
        ("hand_w", [0.0, 0.5, 2.0, 5.0]),
        ("size_beta", [0.0, 0.3, -0.3]),
        ("w_pr", [0.0, 0.5, 1.0, 2.0]),
        ("eps_pr", [1e-4, 1e-3, 1e-2]),
        ("w_stage", [0.0, 0.25, 0.5, 1.0]),
        ("w_amt", [0.0, 0.3, 0.6]),
        ("w_cty", [0.0, 0.2, 0.5]),
        ("w_hand", [0.0, 0.2, 0.5]),
    ]
    if not outside:
        grid += [("ins_cur", [0, 2, 4, 8]), ("ins_anylead", [0, 1, 2, 4]), ("ins_lastlead", [0, 1, 3, 6])]
    for rnd in range(2):
        for name, vals in grid:
            for v in vals:
                if v == best[name]:
                    continue
                p = dict(best); p[name] = v
                s = score(p)
                if s > cur_s + 1e-9:
                    cur_s, best = s, p
                    print(f"  {setting} {name}={v} -> {s:.3f}", flush=True)
    return best


def report(p, name):
    res = H.evaluate(make_rank(p), name)
    for setting, outside in (("ALL", False), ("OUTSIDE", True)):
        print(f"   {name} {setting} dev(<=2023)={quick(make_rank(p), outside, DEV)}  hold(>=2024)={quick(make_rank(p), outside, HOLD)}")
    return res


def cf_baselines():
    """Harness baselines on the same usable-round information set as the method (see MODE)."""
    def wrap(fn):
        def rank(ctx: H.Context) -> list[str]:
            allow = allow_mask(len(ctx.past))
            cp = ctx.company_past if (FULL_CP or MODE == "keep-crawl") else [o for o in ctx.company_past if allow[RIDX[id(o)]]]
            cur = set().union(*(H.investors(o) for o in cp)) if cp else set()
            c2 = H.Context(ctx.test, [o for o in ctx.past if allow[RIDX[id(o)]]], cp, cur, ctx.outside_only)
            return fn(c2)
        return rank
    for fn in (H.stage_leads, H.last_lead_again):
        r = wrap(fn)
        H.evaluate(r, f"cf:{fn.__name__}")
        for setting, outside in (("ALL", False), ("OUTSIDE", True)):
            print(f"   cf:{fn.__name__} {setting} dev={quick(r, outside, DEV)} hold={quick(r, outside, HOLD)}")


def _main():
    if "--baselines" in sys.argv:
        cf_baselines()
        return
    if "--base" in sys.argv:
        report(BASE, "coinvest_graph_audited[base]")
        return
    if "--ablate" in sys.argv:
        ablations()
        return
    if "--final" in sys.argv:
        report_best()
        return
    if True:
        b_all = sweep("ALL")
        b_out = sweep("OUTSIDE")
        print("BEST_ALL", b_all)
        print("BEST_OUT", b_out)
        report(b_all, "coinvest_graph[all-tuned]")
        report(b_out, "coinvest_graph[out-tuned]")
    report(BASE, "coinvest_graph[base]")


def report_best():
    res = H.evaluate(best_rank, "coinvest_graph[best]")
    for setting, outside in (("ALL", False), ("OUTSIDE", True)):
        print(f"   best {setting} dev(<=2023)={quick(best_rank, outside, DEV)}  hold(>=2024)={quick(best_rank, outside, HOLD)}")
    return res


# ---------------- chosen variants (from the dev-split sweep, run 1) ----------------
BEST_ALL = dict(BASE, half=2.0, alpha=0.7, hand_w=0.5, w_stage=0.0, ins_anylead=1)
BEST_OUT = dict(BASE, half=2.0, alpha=0.1, hand_w=0.5, eps_pr=0.01, w_stage=0.25, ins_cur=0, ins_anylead=0,
                ins_lastlead=0)


def best_rank(ctx: H.Context) -> list[str]:
    """Final method: per-setting tuned weights (the harness tells the method which setting it is in)."""
    return (_R_OUT if ctx.outside_only else _R_ALL)(ctx)


_R_ALL = make_rank(BEST_ALL)
_R_OUT = make_rank(BEST_OUT)


def ablations():
    report(dict(BEST_OUT, w_pr=0.0), "abl[no-graph lead-fit only]")
    report(dict(BEST_OUT, w_stage=0.0, w_amt=0.0, w_cty=0.0), "abl[graph only]")
    report(dict(BEST_OUT, hand_w=0.0), "abl[no hand-off edges]")


if __name__ == "__main__":
    _main()
