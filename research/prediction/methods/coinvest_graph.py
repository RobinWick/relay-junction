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
"""
from __future__ import annotations

import bisect
import math
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

# hand-off edges: investors of an earlier round of the same company -> leads of a later round.
# Edge "exists" at the later round's index (e_r2); masked so both rounds are in the past.
h_src, h_dst, h_r = [], [], []
RIDX = {id(r): k for k, r in enumerate(R)}
for ck, rs in H.BY_COMPANY.items():
    for r2 in rs:
        leads = r2.get("leads") or []
        if not leads:
            continue
        earlier = set()
        for r1 in rs:
            if r1["t"] < r2["t"] - H.EPS:
                earlier |= H.investors(r1)
        k2 = RIDX[id(r2)]
        for a in earlier:
            for l in leads:
                if a != l:
                    h_src.append(IDX[a]); h_dst.append(IDX[l]); h_r.append(k2)
h_src = np.array(h_src, dtype=int); h_dst = np.array(h_dst, dtype=int); h_r = np.array(h_r, dtype=int)


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
    m = inc_r < cut
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
    em = e_r < cut
    w = e_base[em] * decay(t0 - T[e_r[em]], half) * np.power(1.0 + e_amt[em], size_beta)
    src, dst = e_src[em], e_dst[em]
    if hand_w > 0:
        hm = h_r < cut
        hw = hand_w * decay(t0 - T[h_r[hm]], half)
        src = np.concatenate([src, h_src[hm]]); dst = np.concatenate([dst, h_dst[hm]]); w = np.concatenate([w, hw])
    restart = np.zeros(NI)
    cp = ctx.company_past
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
        hm = h_r < cut
        hw = decay(t0 - T[h_r[hm]], half)
        handoff = np.bincount(h_dst[hm], weights=hw * restart[h_src[hm]], minlength=NI)
    else:
        handoff = np.zeros(NI)
    # insider info
    last_leads = set()
    any_lead = set()
    for o in cp:
        any_lead |= set(o.get("leads") or [])
    if cp:
        last_leads = set(cp[-1].get("leads") or [])
    f = dict(seen=seen, lead_cnt=lead_cnt, act=act, stage_lead=stage_lead, amt_fit=amt_fit, country=country,
             pr=pr, handoff=handoff, last_leads=last_leads, any_lead=any_lead)
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
            for x in ctx.current:
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
        top = np.argsort(-sc)[:60]
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


def _main():
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
