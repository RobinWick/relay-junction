"""insider_switch: when does an existing investor lead again, and how to interleave insiders with outsiders.

One chronological pass builds investor statistics incrementally. For every round R (test or not) we compute
candidate features using ONLY rounds with t < R.t - EPS (exactly what ctx.past holds) and R's projected target
fields (company, country, t, stage, amount). Labels (R's leads) are used only when R serves as a TRAINING example
for a later time cut. A logistic model per half-year cut is trained on examples with t < cut <= test_t - EPS.

Variants:
  rule_*    : hand rules (insider ordering by lead propensity, outsider slots)
  model_*   : pointwise logistic model over insiders + generated outsiders
"""
from __future__ import annotations

import math
import sys
from collections import defaultdict, Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import harness as H  # noqa: E402

EPS = H.EPS
STAGE_IDX = {"pre-seed": 0, "seed": 1, "series a": 2, "series b": 3, "series c": 4, "series d": 5,
             "series e": 6, "series f": 7, "growth": 6}
N_OUT = 40
TARGET_KEYS = ("company", "ckey", "country", "t", "year", "month", "stage", "amount_eur_m")


def proj(r: dict) -> dict:
    return {k: r.get(k) for k in TARGET_KEYS}


class Stats:
    """Investor statistics over the rounds added so far (all strictly in the past of the round being scored)."""

    def __init__(self):
        self.n = 0
        self.leads = Counter()
        self.app = Counter()
        self.lead_years = defaultdict(list)      # inv -> list of (t, stage) when leading
        self.country_app = defaultdict(Counter)  # inv -> country -> count
        self.last_t = {}
        self.coinv = defaultdict(Counter)        # inv -> other inv -> co-appearances
        self.colead = defaultdict(Counter)       # participant -> lead -> times that lead led a round with participant
        self.company = defaultdict(list)         # ckey -> rounds (past)

    def add(self, r: dict):
        self.n += 1
        L = list(dict.fromkeys(r.get("leads") or []))
        P = [p for p in dict.fromkeys(r.get("participants") or []) if p not in L]
        allv = L + P
        for x in L:
            self.leads[x] += 1
            self.lead_years[x].append((r["t"], r.get("stage")))
        for x in allv:
            self.app[x] += 1
            self.country_app[x][r.get("country")] += 1
            self.last_t[x] = r["t"]
        if len(allv) <= 40:
            for i, a in enumerate(allv):
                for b in allv:
                    if a != b:
                        self.coinv[a][b] += 1
            for p in allv:
                for l in L:
                    if l != p:
                        self.colead[p][l] += 1
        self.company[r["ckey"]].append(r)


def stage_pop(st: Stats, stage, t, country):
    c = defaultdict(float)
    for inv, lst in st.lead_years.items():
        s = 0.0
        for (tt, sg) in lst:
            if t - tt > 4:
                continue
            s += 3 if sg == stage else 0.2
        if s:
            c[inv] = s
    return c


_SP_CACHE = {}


def stage_pop_cached(st: Stats, stage, t):
    # recomputed at most once per (stats size, stage)
    key = (st.n, stage)
    if key not in _SP_CACHE:
        _SP_CACHE.clear() if len(_SP_CACHE) > 64 else None
        _SP_CACHE[key] = stage_pop(st, stage, t, None)
    return _SP_CACHE[key]


FEATS = ["ins", "prev_lead", "ever_lead_co", "n_co", "in_last", "since_seen", "tot_leads", "lead_ratio",
         "leads3y", "stage_leads", "country_share", "coinv", "colead", "yrs_idle", "sp",
         "pl_x_jump", "pl_x_months", "pl_x_growth", "pl_x_tot", "ins_x_ncur", "ins_x_jump", "ins_x_months",
         "ins_x_growth", "pl_x_nprevleads", "ins_x_unknownstage", "pl_x_ncur", "first_round_lead",
         "pl_x_samestage"]


def candidates(tg: dict, st: Stats):
    """Return (cands, feature matrix, base heuristic order). Uses only tg (projected target) and st (past)."""
    t = tg["t"]
    cp = st.company.get(tg["ckey"], [])
    if not cp:
        return [], np.zeros((0, len(FEATS))), []
    cur = []
    for o in reversed(cp):
        for x in (o.get("leads") or []) + (o.get("participants") or []):
            if x not in cur:
                cur.append(x)
    curset = set(cur)
    last = cp[-1]
    prev_leads = set(last.get("leads") or [])
    first_leads = set(cp[0].get("leads") or [])
    led_co = Counter(l for o in cp for l in (o.get("leads") or []))
    n_co = Counter(x for o in cp for x in H.investors(o))
    last_seen_idx = {}
    for i, o in enumerate(cp):
        for x in H.investors(o):
            last_seen_idx[x] = i
    in_last = H.investors(last)
    s_t, s_p = STAGE_IDX.get(tg.get("stage")), STAGE_IDX.get(last.get("stage"))
    jump = (max(-1, min(3, s_t - s_p)) if (s_t is not None and s_p is not None) else 0.5)
    months = math.log1p(max(0.0, (t - last["t"]) * 12))
    a_t, a_p = tg.get("amount_eur_m"), last.get("amount_eur_m")
    growth = math.log((a_t + 0.1) / (a_p + 0.1)) if (a_t and a_p) else 0.0
    ncur = math.log1p(len(cur))
    unknown = 1.0 if tg.get("stage") is None else 0.0
    samestage = 1.0 if (tg.get("stage") is not None and tg.get("stage") == last.get("stage")) else 0.0
    sp = stage_pop_cached(st, tg.get("stage"), t)

    # outsider generation
    oscore = defaultdict(float)
    for x in cur:
        for l, c in st.colead.get(x, {}).items():
            if l not in curset:
                oscore[l] += 2.0 * c
        for l, c in st.coinv.get(x, {}).items():
            if l not in curset and st.leads.get(l):
                oscore[l] += 0.5 * c
    for l, v in sp.items():
        if l not in curset:
            oscore[l] += 0.3 * v
    outs = sorted(oscore, key=oscore.get, reverse=True)[:N_OUT]
    cands = cur + outs
    country = tg.get("country")
    rows = []
    for c in cands:
        ins = 1.0 if c in curset else 0.0
        pl = 1.0 if c in prev_leads else 0.0
        app = st.app.get(c, 0)
        ld = st.leads.get(c, 0)
        lys = st.lead_years.get(c, [])
        l3 = sum(1 for (tt, _) in lys if t - tt <= 3)
        sl = sum(1 for (tt, sg) in lys if t - tt <= 4 and sg == tg.get("stage"))
        csh = st.country_app[c][country] / app if app else 0.0
        co = sum(st.coinv.get(c, {}).get(x, 0) for x in cur if x != c)
        cl = sum(st.colead.get(x, {}).get(c, 0) for x in cur if x != c)
        idle = min(10.0, t - st.last_t.get(c, t - 10))
        since = (len(cp) - 1 - last_seen_idx[c]) if c in last_seen_idx else 0
        tot = math.log1p(ld)
        rows.append([ins, pl, 1.0 if led_co.get(c) else 0.0, math.log1p(n_co.get(c, 0)), 1.0 if c in in_last else 0.0,
                     min(5, since), tot, ld / (app + 1), math.log1p(l3), math.log1p(sl), csh,
                     math.log1p(co), math.log1p(cl), idle, math.log1p(sp.get(c, 0.0)),
                     pl * jump, pl * months, pl * growth, pl * tot, ins * ncur, ins * jump, ins * months,
                     ins * growth, pl * math.log1p(len(prev_leads)), ins * unknown, pl * ncur,
                     1.0 if c in first_leads else 0.0, pl * samestage])
    return cands, np.array(rows, dtype=float), outs


# ---------------- one chronological pass ----------------

def build():
    st = Stats()
    rounds = H.ROUNDS
    j = 0
    examples = []   # (t, is_cf, X, y)
    test_feats = {}  # round id -> (cut_len, cands, X)
    test_ids = {r["id"] for r in H.TEST}
    for r in rounds:
        while j < len(rounds) and rounds[j]["t"] < r["t"] - EPS:
            st.add(rounds[j])
            j += 1
        if not st.company.get(r["ckey"]):
            continue
        tg = proj(r)
        cands, X, _ = candidates(tg, st)
        if not cands:
            continue
        if r["id"] in test_ids:
            test_feats[r["id"]] = (j, cands, X, tg)
        if r.get("leads"):
            y = np.array([1.0 if c in set(r["leads"]) else 0.0 for c in cands])
            is_cf = any(x.get("path") == "company_first" for x in r.get("sources") or [])
            examples.append((r["t"], is_cf, X, y))
    return test_feats, examples


def fit_logreg(X, y, l2=1.0, iters=25):
    mu, sd = X.mean(0), X.std(0) + 1e-6
    Z = np.hstack([(X - mu) / sd, np.ones((len(X), 1))])
    w = np.zeros(Z.shape[1])
    for _ in range(iters):
        p = 1 / (1 + np.exp(-np.clip(Z @ w, -30, 30)))
        g = Z.T @ (p - y) + l2 * np.r_[w[:-1], 0]
        Wd = p * (1 - p)
        Hm = (Z * Wd[:, None]).T @ Z + l2 * np.eye(len(w))
        w -= np.linalg.solve(Hm, g)
    return mu, sd, w


print("building features (single chronological pass)...", flush=True)
TEST_FEATS, EXAMPLES = build()
print(f"examples {len(EXAMPLES)}, test feats {len(TEST_FEATS)}", flush=True)

_MODELS = {}


def model_for(t, cf_only, min_year, feat_idx):
    cut = math.floor((t - EPS) * 2) / 2  # half-year bin, cut <= t - EPS
    key = (cut, cf_only, min_year, tuple(feat_idx))
    if key not in _MODELS:
        Xs, ys = [], []
        for (tt, cf, X, y) in EXAMPLES:
            if tt >= cut or tt < min_year:
                continue
            if cf_only and not cf:
                continue
            if y.sum() == 0:
                continue  # no candidate was a lead: uninformative for ranking
            Xs.append(X[:, feat_idx])
            ys.append(y)
        X = np.vstack(Xs)
        y = np.concatenate(ys)
        _MODELS[key] = fit_logreg(X, y)
    return _MODELS[key]


def lookup(ctx):
    rid = ctx.test["id"]
    if rid not in TEST_FEATS:
        return None
    cutlen, cands, X, tg = TEST_FEATS[rid]
    assert cutlen == len(ctx.past), "feature snapshot must equal ctx.past"
    assert tg == ctx.target
    return cands, X


def make_model_rank(cf_only=False, min_year=2010, feats=None):
    idx = [FEATS.index(f) for f in (feats or FEATS)]

    def rank(ctx):
        got = lookup(ctx)
        tail = H.stage_leads(ctx)
        if not got:
            return H.last_lead_again(ctx)
        cands, X = got
        mu, sd, w = model_for(ctx.test["t"], cf_only, min_year, idx)
        Z = np.hstack([(X[:, idx] - mu) / sd, np.ones((len(X), 1))])
        s = Z @ w
        order = [cands[i] for i in np.argsort(-s, kind="stable")]
        return order + tail
    return rank


def make_hybrid(k_ins=3, cf_only=False):
    """Model order, but guarantee the model's top insiders keep the first k_ins slots."""
    base = make_model_rank(cf_only=cf_only)

    def rank(ctx):
        order = base(ctx)
        if ctx.outside_only:
            return order
        ins = [x for x in order if x in ctx.current][:k_ins]
        rest = [x for x in order if x not in ins]
        return ins + rest
    return rank


def rule_propensity(n_out_slots=0):
    """Insiders: prev lead first, then other insiders by global lead propensity; outsiders by heuristic."""
    def rank(ctx):
        got = lookup(ctx)
        if not got:
            return H.last_lead_again(ctx)
        cands, X = got
        fi = {f: i for i, f in enumerate(FEATS)}
        ins = [(c, X[i]) for i, c in enumerate(cands) if X[i, fi["ins"]] == 1]
        outs = [c for i, c in enumerate(cands) if X[i, fi["ins"]] == 0]
        ins.sort(key=lambda cx: (-cx[1][fi["prev_lead"]], -cx[1][fi["ever_lead_co"]],
                                 -(cx[1][fi["tot_leads"]] + cx[1][fi["in_last"]])))
        ins = [c for c, _ in ins]
        k = max(1, 5 - n_out_slots)
        return ins[:k] + outs[:n_out_slots] + ins[k:] + outs[n_out_slots:] + H.stage_leads(ctx)
    return rank


# ---------------- listwise (conditional logit) variant ----------------

def fit_clogit(groups, l2=1.0, steps=400, lr=0.05):
    """groups: list of (X, y). Maximises sum over groups of log(sum_{pos} softmax)."""
    Xall = np.vstack([g[0] for g in groups])
    mu, sd = Xall.mean(0), Xall.std(0) + 1e-6
    Zs = [((X - mu) / sd, y) for X, y in groups]
    w = np.zeros(Xall.shape[1])
    m, v = np.zeros_like(w), np.zeros_like(w)
    for it in range(1, steps + 1):
        g = l2 * w
        for Z, y in Zs:
            s = Z @ w
            s -= s.max()
            e = np.exp(s)
            p = e / e.sum()
            q = e * y
            q = q / q.sum()
            g -= Z.T @ (q - p)
        g /= len(Zs)
        m = 0.9 * m + 0.1 * g
        v = 0.999 * v + 0.001 * g * g
        w -= lr * (m / (1 - 0.9 ** it)) / (np.sqrt(v / (1 - 0.999 ** it)) + 1e-8)
    return mu, sd, w


_CL = {}


def clogit_for(t, cf_only, min_year, feat_idx, l2):
    cut = math.floor((t - EPS) * 2) / 2
    key = (cut, cf_only, min_year, tuple(feat_idx), l2)
    if key not in _CL:
        groups = [(X[:, feat_idx], y) for (tt, cf, X, y) in EXAMPLES
                  if tt < cut and tt >= min_year and (cf or not cf_only) and y.sum() > 0]
        _CL[key] = fit_clogit(groups, l2=l2 / max(1, len(groups)) * 50)
    return _CL[key]


def make_clogit_rank(cf_only=False, min_year=2010, feats=None, l2=1.0, ins_first=0):
    idx = [FEATS.index(f) for f in (feats or FEATS)]

    def rank(ctx):
        got = lookup(ctx)
        tail = H.stage_leads(ctx)
        if not got:
            return H.last_lead_again(ctx)
        cands, X = got
        mu, sd, w = clogit_for(ctx.test["t"], cf_only, min_year, idx, l2)
        s = ((X[:, idx] - mu) / sd) @ w
        order = [cands[i] for i in np.argsort(-s, kind="stable")]
        if ins_first and not ctx.outside_only:
            ins = [x for x in order if x in ctx.current][:ins_first]
            order = ins + [x for x in order if x not in ins]
        return order + tail
    return rank


def make_rule_then_model(n_rule=1, cf_only=True, listwise=False):
    """First n_rule slots from the insider propensity rule (best for hit@1), the rest from the model."""
    rule = rule_propensity(0)
    model = make_clogit_rank(cf_only=cf_only) if listwise else make_model_rank(cf_only=cf_only)

    def rank(ctx):
        head = [] if ctx.outside_only else rule(ctx)[:n_rule]
        return head + [x for x in model(ctx) if x not in head]
    return rank


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")  # numpy 2.0 + Accelerate emits spurious matmul warnings; values are finite
    which = sys.argv[1:] or ["best"]
    if "best" in which or "all" in which:
        H.evaluate(make_rule_then_model(1, cf_only=True), "insider_switch_best")
    if "all" in which:
        H.evaluate(rule_propensity(0), "rule_prop_0out")
        H.evaluate(rule_propensity(1), "rule_prop_1out")
        H.evaluate(make_model_rank(), "model_all")
        H.evaluate(make_model_rank(cf_only=True), "model_cf")
        H.evaluate(make_clogit_rank(), "clogit")
