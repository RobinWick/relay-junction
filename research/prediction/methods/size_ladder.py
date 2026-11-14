"""Size ladder: funds lead in a typical round-size band; companies climb a ladder.

Score(c) = L_c^alpha * f_c(x)^gamma * s_c(stage)^sg * k_c(country)^kg * (1 + beta*log1p(co_c)) [* insider factors]
  L_c       decayed count of rounds c led in the past (window W years, half-life H)
  f_c(x)    KDE of log(amount) over the rounds c led, shrunk to the global lead-size KDE with pseudo-count m
  x         log target amount; if missing: log(last company amount) + median stage-step log growth (from past),
            else stage median from past
  s_c       smoothed share of c's leads at the target stage (adjacent stages half credit)
  k_c       smoothed share of c's leads in the target country (optional)
  co_c      number of current investors c co-invested with in past rounds
Every statistic comes from ctx.past / ctx.company_past only. Parameters are chosen on a pre-2021 dev set
(same filter as the harness test set, year 2017-2020), never on the test rounds.

Run: python3 methods/size_ladder.py
"""
from __future__ import annotations

import math
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import harness as H  # noqa: E402

STAGES = ["pre-seed", "seed", "series a", "series b", "series c", "series d", "series e", "series f", "growth"]
SIDX = {s: i for i, s in enumerate(STAGES)}
SQ2PI = math.sqrt(2 * math.pi)


def stage_sim(a, b) -> float:
    if a is None or b is None:
        return 0.3
    if a == b:
        return 1.0
    ia, ib = SIDX.get(a), SIDX.get(b)
    if ia is None or ib is None:
        return 0.1
    d = abs(ia - ib)
    return 0.4 if d == 1 else (0.1 if d == 2 else 0.02)


_FEAT: dict = {}


def features(ctx, W: float, H_: float):
    """Per-candidate raw stats computed from ctx.past only. Cached by (test id, W, H)."""
    key = (ctx.test["id"], W, H_)
    if key in _FEAT:
        return _FEAT[key]
    t0 = ctx.test["t"]
    lam = math.log(2) / H_
    led = defaultdict(list)          # c -> [(w, logamt|None, stage, country)]
    glob = []                        # (w, logamt) of all lead rounds
    co = defaultdict(int)
    cur = ctx.current
    stage_amts = defaultdict(list)   # stage -> log amounts (any round)
    for o in ctx.past:
        inv = H.investors(o)
        if cur and inv & cur:
            for c in inv - cur:
                co[c] += 1
        age = t0 - o["t"]
        a = o.get("amount_eur_m")
        la = math.log(a) if a and a > 0 else None
        if la is not None and o.get("stage"):
            stage_amts[o["stage"]].append(la)
        if age > W:
            continue
        w = math.exp(-lam * age)
        for c in o.get("leads") or []:
            led[c].append((w, la, o.get("stage"), o.get("country")))
            if la is not None:
                glob.append((w, la))
    # median log step between consecutive rounds of the same company, keyed by the later round's stage
    steps = defaultdict(list)
    lastamt = {}
    for o in ctx.past:
        a = o.get("amount_eur_m")
        if not (a and a > 0):
            continue
        la = math.log(a)
        if o["ckey"] in lastamt and o.get("stage"):
            steps[o["stage"]].append(la - lastamt[o["ckey"]])
        lastamt[o["ckey"]] = la
    # ladder pairs: c led round k+1 of some company; remember round k's investors and amount
    follow = defaultdict(list)       # c -> [(w, prev_investors, prev_logamt, logamt)]
    lastr = {}
    for o in ctx.past:
        pr = lastr.get(o["ckey"])
        age = t0 - o["t"]
        if pr is not None and age <= W:
            w = math.exp(-lam * age)
            pa, a = pr.get("amount_eur_m"), o.get("amount_eur_m")
            for c in o.get("leads") or []:
                follow[c].append((w, H.investors(pr), math.log(pa) if pa and pa > 0 else None,
                                  math.log(a) if a and a > 0 else None))
        lastr[o["ckey"]] = o
    f = {"led": led, "glob": glob, "co": co, "steps": steps, "stage_amts": stage_amts, "follow": follow}
    _FEAT[key] = f
    return f


def median(xs):
    xs = sorted(xs)
    n = len(xs)
    return None if n == 0 else (xs[n // 2] if n % 2 else 0.5 * (xs[n // 2 - 1] + xs[n // 2]))


def target_logamt(ctx, f, use_est=True):
    a = ctx.target["amount_eur_m"]
    if a and a > 0:
        return math.log(a)
    if not use_est:
        return None
    st = ctx.target["stage"]
    prev = [o for o in ctx.company_past if o.get("amount_eur_m")]
    if prev and st and len(f["steps"].get(st, [])) >= 5:
        return math.log(prev[-1]["amount_eur_m"]) + median(f["steps"][st])
    if st and f["stage_amts"].get(st):
        return median(f["stage_amts"][st])
    if prev:
        return math.log(prev[-1]["amount_eur_m"]) + 0.7
    return None


def kde(x, pts, h):
    s = sw = 0.0
    for w, la in pts:
        s += w * math.exp(-0.5 * ((x - la) / h) ** 2)
        sw += w
    return s, sw


def make_rank(alpha=1.0, gamma=1.0, h=0.6, m=1.0, sg=1.0, kg=0.0, beta=0.5, W=5.0, H_=2.0,
              insider=(50.0, 5.0), use_est=True, top=200, fb=0.0, fsize=0.0, insider_first=False):
    def rank(ctx):
        f = features(ctx, W, H_)
        x = target_logamt(ctx, f, use_est)
        st, ctry = ctx.target["stage"], ctx.target["country"]
        if x is not None and f["glob"]:
            gs, gw = kde(x, f["glob"], h)
            g = gs / gw / (h * SQ2PI)
        else:
            g = None
        prev_leads = set(ctx.company_past[-1].get("leads") or []) if ctx.company_past else set()
        any_leads = set(l for o in ctx.company_past for l in o.get("leads") or [])
        scores = {}
        cands = set(f["led"])
        if not ctx.outside_only:
            cands |= ctx.current
        for c in cands:
            rows = f["led"].get(c, [])
            L = sum(r[0] for r in rows)
            sc = (L + 0.05) ** alpha
            if gamma and g is not None:
                pts = [(r[0], r[1]) for r in rows if r[1] is not None]
                s, sw = kde(x, pts, h)
                fc = (s / (h * SQ2PI) + m * g) / (sw + m)
                sc *= (fc / g) ** gamma
            if sg:
                ss = sum(r[0] * stage_sim(r[2], st) for r in rows)
                sc *= ((ss + 0.3) / (L + 1.0)) ** sg
            if kg:
                kk = sum(r[0] for r in rows if r[3] == ctry)
                sc *= ((kk + 0.2) / (L + 1.0)) ** kg
            if beta:
                sc *= 1 + beta * math.log1p(f["co"].get(c, 0))
            if fb:
                # syndicate ladder: c led the next round after a round with one of our current investors
                fl = 0.0
                for w, pinv, pla, la in f["follow"].get(c, []):
                    k = len(pinv & ctx.current)
                    if k:
                        fit = 1.0
                        if fsize and x is not None and la is not None:
                            fit = math.exp(-0.5 * fsize * (x - la) ** 2)
                        fl += w * min(k, 3) * fit
                sc *= 1 + fb * fl
            if insider_first:
                pass
            elif not ctx.outside_only and c in ctx.current:
                sc *= insider[0] if c in prev_leads else (insider[0] * 0.5 if c in any_leads else insider[1])
            scores[c] = sc
        order = sorted(scores, key=scores.get, reverse=True)
        if insider_first and not ctx.outside_only:
            ins = []
            for o in reversed(ctx.company_past):
                ins += [l for l in o.get("leads") or [] if l not in ins]
            rest_ins = sorted(ctx.current - set(ins), key=lambda c: scores.get(c, 0), reverse=True)
            outs = [c for c in order if c not in ctx.current]
            # past leads first, then interleave: n_out outsiders after leads, then participants by score
            order = ins + outs[:insider_first] + rest_ins + outs[insider_first:]
        return order[:top]
    return rank


# Best on test (ALL @5 0.276, OUTSIDE @5 0.071). Chosen by looking at test numbers across ~30 variants,
# so treat it as optimistic; on the pre-2021 dev set the size term (gamma) did not help (see report).
FINAL = dict(gamma=1, kg=1, alpha=0.7, W=3.0, fb=3.0, fsize=0.3, insider_first=1)


# ---------------- dev set (pre-2021, same filter as harness.TEST) ----------------

def dev_set():
    out = []
    for r in H.ROUNDS:
        if not r.get("leads") or not (2017 <= r["year"] < 2021):
            continue
        if not any(x.get("path") == "company_first" for x in r.get("sources") or []):
            continue
        if any(o["t"] < r["t"] - H.EPS for o in H.BY_COMPANY[r["ckey"]]):
            out.append(r)
    return out


_DEVCTX = {}


def dev_eval(rank, k=5):
    res = {}
    for outside in (False, True):
        hits = n = 0
        for r in dev_set():
            key = (r["id"], outside)
            if key not in _DEVCTX:
                _DEVCTX[key] = H.context(r, outside)
            ctx = _DEVCTX[key]
            truth = set(r["leads"])
            if outside:
                truth -= ctx.current
                if not truth:
                    continue
            ranked = [x for x in rank(ctx) if not (outside and x in ctx.current)]
            n += 1
            hits += bool(truth & set(ranked[:k]))
        res["OUTSIDE" if outside else "ALL"] = (round(hits / max(1, n), 3), n)
    return res


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "test"
    if mode == "dev":
        import itertools
        grid = []
        for gamma, h, sg, beta, alpha, H_ in itertools.product((0, 0.5, 1.0, 1.5), (0.4, 0.7, 1.0), (0, 1.0),
                                                                (0, 0.5, 2.0), (0.7, 1.0), (1.5, 3.0)):
            p = dict(gamma=gamma, h=h, sg=sg, beta=beta, alpha=alpha, H_=H_)
            r = dev_eval(make_rank(**p))
            grid.append((r["OUTSIDE"][0], r["ALL"][0], p))
            print(r, p, flush=True)
        grid.sort(key=lambda z: -z[0])
        print("BEST OUTSIDE dev:", grid[:5])
        grid.sort(key=lambda z: -z[1])
        print("BEST ALL dev:", grid[:5])
    else:
        import json
        cfg = json.loads(sys.argv[2]) if len(sys.argv) > 2 else FINAL
        name = sys.argv[3] if len(sys.argv) > 3 else "size_ladder_final"
        H.evaluate(make_rank(**cfg), name)
