"""Learning to rank who leads a company's next round (Cala backtest, method family: learning_to_rank).

How it stays honest
- One pass over the snapshot in time order builds an incremental "state" (lead counts, co-investment graph,
  handoffs, ...). Before features are computed for a round r, the state contains exactly the rounds with
  t < r.t - EPS, i.e. the same set the harness hands over as ctx.past. rank() asserts that count.
- Every round with a named lead and an earlier round of the same company becomes a candidate list + feature
  matrix. Labels (its leads) are only used to TRAIN models for test rounds dated later than it.
- Model for a test round at time T is a listwise conditional logit (softmax over candidates) fitted on
  examples with t < quarter_start(T) - EPS, retrained once per quarter. Separate models for ALL and OUTSIDE.
- No FUND_KEYS, no statistic fitted on the full snapshot, no test-round leads/participants in rank().
Candidate generation = union of top candidates from simple scorers (current investors, stage popularity,
country popularity, co-investors of current investors, handoff targets of current investors).

Run: python3 methods/learning_to_rank.py [variant ...]
"""
from __future__ import annotations

import bisect
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

np.seterr(all="ignore")  # numpy 2.0 + Accelerate emits spurious matmul FP warnings (checked: no NaN features)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import harness as H  # noqa: E402

EPS = H.EPS
STAGE_ORD = {"pre-seed": 0, "seed": 1, "series a": 2, "series b": 3, "series c": 4, "series d": 5,
             "series e": 6, "series f": 7, "growth": 6}
TAU = 2.0  # years, recency decay


def _key(target: dict) -> tuple:
    return (target["ckey"], target["t"], target.get("stage"), target.get("amount_eur_m"), target.get("country"))


class State:
    """Everything known from the rounds ingested so far (strictly the past)."""

    def __init__(self):
        self.n = 0
        self.lead_n = Counter()
        self.part_n = Counter()
        self.lead_stage = Counter()
        self.lead_times = defaultdict(list)          # c -> [t]
        self.lead_stage_times = defaultdict(list)    # (c, st) -> [t]
        self.last_t = {}
        self.last_lead_t = {}
        self.country_n = defaultdict(Counter)        # c -> country -> n
        self.country_lead = defaultdict(Counter)     # c -> country -> n led
        self.tot_n = Counter()
        self.amt = defaultdict(lambda: [0.0, 0])     # c -> [sum log amount led, n]
        self.stord = defaultdict(lambda: [0.0, 0])   # c -> [sum stage ord led, n]
        self.coinv = defaultdict(Counter)
        self.handoff = defaultdict(Counter)          # a -> b: a invested earlier in a company b later led
        self.insider_opp = Counter()                 # c was current investor when company raised a led round
        self.insider_lead = Counter()                # ... and c led it
        self.companies = defaultdict(set)            # c -> companies
        self.comp_inv = defaultdict(set)
        self.comp_rounds = defaultdict(list)
        self.lead_events = []
        self.country_lead_times = defaultdict(list)  # (c, country) -> [t]                        # (t, c, stage, country), time ordered

    def ingest(self, r: dict) -> None:
        self.n += 1
        t, st, co, ck = r["t"], r.get("stage"), r.get("country"), r["ckey"]
        leads = set(r.get("leads") or [])
        invs = H.investors(r)
        cur = self.comp_inv[ck]
        if leads:
            for a in sorted(cur):
                self.insider_opp[a] += 1
                if a in leads:
                    self.insider_lead[a] += 1
                for b in sorted(leads):
                    if a != b:
                        self.handoff[a][b] += 1
        for c in sorted(invs):
            self.tot_n[c] += 1
            self.last_t[c] = t
            self.companies[c].add(ck)
            if co:
                self.country_n[c][co] += 1
            if c in leads:
                self.lead_n[c] += 1
                self.lead_times[c].append(t)
                self.last_lead_t[c] = t
                if st:
                    self.lead_stage[(c, st)] += 1
                    self.lead_stage_times[(c, st)].append(t)
                    if st in STAGE_ORD:
                        self.stord[c][0] += STAGE_ORD[st]
                        self.stord[c][1] += 1
                if co:
                    self.country_lead[c][co] += 1
                    self.country_lead_times[(c, co)].append(t)
                if r.get("amount_eur_m"):
                    self.amt[c][0] += math.log1p(r["amount_eur_m"])
                    self.amt[c][1] += 1
                self.lead_events.append((t, c, st, co))
            else:
                self.part_n[c] += 1
        il = sorted(invs)
        for i, a in enumerate(il):
            for b in il[i + 1:]:
                self.coinv[a][b] += 1
                self.coinv[b][a] += 1
        cur |= invs
        self.comp_rounds[ck].append(r)


def _decay(times, T):
    return sum(math.exp(-(T - t) / TAU) for t in times)


def handoff2(S: State, cur: set) -> Counter:
    """2-hop handoff: c led a later round of a company backed by a co-investor of a current investor."""
    agg = Counter()
    for a in sorted(cur):
        for b, nb in S.coinv[a].items():
            for c, n in S.handoff[b].items():
                agg[c] += n
    return agg


def candidates(S: State, tg: dict, cur: set, outside: bool, hop2: Counter = None, n_pop=150, n_graph=150,
               n_country=60, n_hop2=0) -> list[str]:
    T, st, co = tg["t"], tg.get("stage"), tg.get("country")
    pop, cpop = Counter(), Counter()
    lo = bisect.bisect_left(S.lead_events, (T - 4,))
    for t, c, s, cc in S.lead_events[lo:]:
        w = 3.0 if s == st else 0.2
        pop[c] += w
        if co and cc == co:
            cpop[c] += w
    graph = Counter()
    for a in sorted(cur):
        for b, n in S.handoff[a].items():
            graph[b] += 2 * n
        for b, n in S.coinv[a].items():
            graph[b] += n
    out = [] if outside else sorted(cur)
    out += [c for c, _ in pop.most_common(n_pop + len(cur))]
    out += [c for c, _ in graph.most_common(n_graph + len(cur))]
    out += [c for c, _ in cpop.most_common(n_country + len(cur))]
    if hop2 and n_hop2:
        out += [c for c, _ in hop2.most_common(n_hop2 + len(cur))]
    seen, res = set(), []
    for c in out:
        if c not in seen and not (outside and c in cur):
            seen.add(c)
            res.append(c)
    return res


FEATS = ["is_cur", "is_last_lead", "is_prev_lead", "comp_rounds_in", "in_latest", "lead_n", "part_n", "lead_share",
         "lead_stage", "dec_lead", "dec_lead_stage", "yrs_seen", "yrs_lead", "amt_fit", "amt_miss", "country_share",
         "country_lead", "coinv_cur", "coinv_cur_k", "handoff_cur", "two_hop", "insider_rate", "stage_fit",
         "stage_miss", "n_companies", "cur_x_insider", "coinv_last_lead", "handoff_last_lead",
         "hop2", "stage_lead_share", "dec_country_lead", "handoff_out_any", "follow_on_rate"]


def features(S: State, tg: dict, cands: list[str], comp_past: list[dict], cur: set, hop2: Counter) -> np.ndarray:
    T, st, co = tg["t"], tg.get("stage"), tg.get("country")
    A = tg.get("amount_eur_m")
    la = math.log1p(A) if A else None
    so = STAGE_ORD.get(st)
    last = comp_past[-1] if comp_past else {}
    last_leads = set(last.get("leads") or [])
    last_inv = H.investors(last) if last else set()
    prev_leads = set().union(*(set(o.get("leads") or []) for o in comp_past)) if comp_past else set()
    rounds_in = Counter()
    for o in comp_past:
        for c in H.investors(o):
            rounds_in[c] += 1
    ncur = set()
    for a in cur:
        ncur.update(S.coinv[a].keys())
    X = np.zeros((len(cands), len(FEATS)))
    for i, c in enumerate(cands):
        ln, pn = S.lead_n[c], S.part_n[c]
        isc = float(c in cur)
        ins = (S.insider_lead[c] + 0.5) / (S.insider_opp[c] + 2.0)
        am = S.amt[c]
        amt_fit = -abs(la - am[0] / am[1]) if (la is not None and am[1]) else 0.0
        sd = S.stord[c]
        stage_fit = -abs(so - sd[0] / sd[1]) if (so is not None and sd[1]) else 0.0
        tot = S.tot_n[c]
        cs = S.coinv[c]
        X[i] = [
            isc,
            float(c in last_leads),
            float(c in prev_leads),
            math.log1p(rounds_in[c]),
            float(c in last_inv),
            math.log1p(ln),
            math.log1p(pn),
            ln / (ln + pn) if ln + pn else 0.0,
            math.log1p(S.lead_stage[(c, st)]) if st else 0.0,
            math.log1p(_decay(S.lead_times[c], T)),
            math.log1p(_decay(S.lead_stage_times[(c, st)], T)) if st else 0.0,
            min(10.0, T - S.last_t[c]) if c in S.last_t else 10.0,
            min(10.0, T - S.last_lead_t[c]) if c in S.last_lead_t else 10.0,
            amt_fit,
            float(not (la is not None and am[1])),
            S.country_n[c][co] / tot if (co and tot) else 0.0,
            math.log1p(S.country_lead[c][co]) if co else 0.0,
            math.log1p(sum(cs[a] for a in cur)),
            math.log1p(sum(1 for a in cur if cs[a])),
            math.log1p(sum(S.handoff[a][c] for a in cur)),
            math.log1p(len(ncur & cs.keys())),
            ins,
            stage_fit,
            float(not (so is not None and sd[1])),
            math.log1p(len(S.companies[c])),
            isc * ins,
            math.log1p(sum(cs[a] for a in last_leads)),
            math.log1p(sum(S.handoff[a][c] for a in last_leads)),
            math.log1p(hop2[c]),
            S.lead_stage[(c, st)] / ln if (st and ln) else 0.0,
            math.log1p(_decay(S.country_lead_times[(c, co)], T)) if co else 0.0,
            math.log1p(sum(S.handoff[c].values())),
            (S.lead_n[c] - S.insider_lead[c] + 0.5) / (len(S.companies[c]) + 2.0),
        ]
    return X


def build_examples():
    """One time-ordered pass. Returns {key: example} for every round with a lead and an earlier company round."""
    S = State()
    R = H.ROUNDS
    ptr = 0
    ex = {}
    for r in R:
        while ptr < len(R) and R[ptr]["t"] < r["t"] - EPS:
            S.ingest(R[ptr])
            ptr += 1
        if not r.get("leads"):
            continue
        cp = S.comp_rounds.get(r["ckey"]) or []
        if not cp:
            continue
        tg = {k: r.get(k) for k in ("company", "ckey", "country", "t", "year", "month", "stage", "amount_eur_m")}
        cur = set(S.comp_inv[r["ckey"]])
        e = {"t": r["t"], "n_past": S.n, "n_cp": len(cp),
             "company_first": any(x.get("path") == "company_first" for x in r.get("sources") or [])}
        leads = set(r["leads"])
        hop2 = handoff2(S, cur)
        for setting, outside in (("ALL", False), ("OUTSIDE", True)):
            cands = candidates(S, tg, cur, outside, hop2, n_hop2=N_HOP2)
            truth = leads - cur if outside else leads
            e[setting] = {"cands": cands, "X": features(S, tg, cands, list(cp), cur, hop2),
                          "y": np.array([c in truth for c in cands], dtype=float), "has_truth": bool(truth)}
        ex.setdefault(_key(tg), e)
    return ex


# ---------------- listwise conditional logit ----------------

def fit_clogit(groups, l2=1.0, iters=400, lr=0.05, hidden=0, seed=0):
    """groups: list of (X, y) with >=1 positive. Returns scorer f(X)->scores. Optional 1-hidden-layer MLP."""
    Xall = np.vstack([g[0] for g in groups])
    mu, sd = Xall.mean(0), Xall.std(0)
    sd[sd < 1e-9] = 1.0
    Xs = [(g[0] - mu) / sd for g in groups]
    ys = [g[1] for g in groups]
    d = Xall.shape[1]
    rng = np.random.default_rng(seed)
    if hidden:
        P = {"W1": rng.normal(0, 0.3, (d, hidden)), "b1": np.zeros(hidden), "w2": rng.normal(0, 0.3, hidden),
             "wl": np.zeros(d)}
    else:
        P = {"wl": np.zeros(d)}
    M = {k: np.zeros_like(v) for k, v in P.items()}
    V = {k: np.zeros_like(v) for k, v in P.items()}
    # concat for speed
    Xc = np.vstack(Xs)
    yc = np.concatenate(ys)
    gid = np.concatenate([np.full(len(y), i) for i, y in enumerate(ys)])
    G = len(groups)
    for it in range(1, iters + 1):
        if hidden:
            Hh = np.tanh(Xc @ P["W1"] + P["b1"])
            s = Xc @ P["wl"] + Hh @ P["w2"]
        else:
            s = Xc @ P["wl"]
        mx = np.full(G, -np.inf)
        np.maximum.at(mx, gid, s)
        e = np.exp(s - mx[gid])
        Z = np.bincount(gid, e, G)
        Zp = np.bincount(gid, e * yc, G)
        p_all = e / Z[gid]
        p_pos = e * yc / Zp[gid]
        ds = (p_all - p_pos) / G  # d loss / d score
        grads = {"wl": Xc.T @ ds + l2 * P["wl"] / G}
        if hidden:
            grads["w2"] = Hh.T @ ds + l2 * P["w2"] / G
            dH = np.outer(ds, P["w2"]) * (1 - Hh ** 2)
            grads["W1"] = Xc.T @ dH + l2 * P["W1"] / G
            grads["b1"] = dH.sum(0)
        for k in P:
            M[k] = 0.9 * M[k] + 0.1 * grads[k]
            V[k] = 0.999 * V[k] + 0.001 * grads[k] ** 2
            P[k] -= lr * (M[k] / (1 - 0.9 ** it)) / (np.sqrt(V[k] / (1 - 0.999 ** it)) + 1e-8)

    def score(X):
        Z = (X - mu) / sd
        s = Z @ P["wl"]
        if hidden:
            s = s + np.tanh(Z @ P["W1"] + P["b1"]) @ P["w2"]
        return s
    score.params = P
    return score


EX = None
N_HOP2 = 60
N_BASE = 28  # first 28 features = the original set


def make_rank(setting_cfg: dict):
    """setting_cfg: per setting dict(l2, hidden, cf_only, min_year, feats(list of indices or None))."""
    models = {}

    def get_model(setting, T):
        q = math.floor(T * 4) / 4
        cut = q - EPS
        key = (setting, q)
        if key not in models:
            cfg = setting_cfg[setting]
            fi = cfg.get("feats")
            groups = []
            for e in EX.values():
                if e["t"] >= cut or e["t"] < cfg.get("min_year", 0):
                    continue
                if cfg.get("cf_only") and not e["company_first"]:
                    continue
                g = e[setting]
                if g["y"].sum() == 0:
                    continue
                X = g["X"] if fi is None else g["X"][:, fi]
                groups.append((X, g["y"]))
            models[key] = fit_clogit(groups, l2=cfg.get("l2", 1.0), hidden=cfg.get("hidden", 0),
                                     iters=cfg.get("iters", 400)) if len(groups) >= 20 else None
        return models[key]

    def rank(ctx):
        tg = ctx.target
        e = EX[_key(tg)]
        # honesty checks: the cached features were built from exactly ctx.past / ctx.company_past
        assert e["n_past"] == len(ctx.past), (e["n_past"], len(ctx.past))
        assert e["n_cp"] == len(ctx.company_past)
        setting = "OUTSIDE" if ctx.outside_only else "ALL"
        g = e[setting]
        m = get_model(setting, tg["t"])
        if m is None or not g["cands"]:
            return list(g["cands"])
        fi = setting_cfg[setting].get("feats")
        X = g["X"] if fi is None else g["X"][:, fi]
        s = m(X)
        order = np.argsort(-s, kind="stable")
        return [g["cands"][i] for i in order]

    rank.models = models
    return rank


def pool_recall():
    """Diagnostic: share of test rounds with a true lead inside the candidate pool (= ceiling of this method)."""
    for setting in ("ALL", "OUTSIDE"):
        n = h = 0
        sizes = []
        for r in H.TEST:
            e = EX[_key({k: r.get(k) for k in ("ckey", "t", "stage", "amount_eur_m", "country")})][setting]
            if setting == "OUTSIDE" and not e["has_truth"]:
                continue
            n += 1
            h += e["y"].sum() > 0
            sizes.append(len(e["cands"]))
        print(f"candidate pool {setting}: recall {h}/{n} = {h / n:.3f}, mean size {sum(sizes) / len(sizes):.0f}")


VARIANTS = {
    "ltr_linear": {"ALL": {"l2": 1.0}, "OUTSIDE": {"l2": 1.0}},
    "ltr_linear_l2_10": {"ALL": {"l2": 10.0}, "OUTSIDE": {"l2": 10.0}},
    "ltr_linear_cf_only": {"ALL": {"l2": 1.0, "cf_only": True}, "OUTSIDE": {"l2": 1.0, "cf_only": True}},
    "ltr_mlp8": {"ALL": {"l2": 3.0, "hidden": 8, "iters": 600}, "OUTSIDE": {"l2": 3.0, "hidden": 8, "iters": 600}},
    "ltr_linear_since2015": {"ALL": {"l2": 1.0, "min_year": 2015}, "OUTSIDE": {"l2": 1.0, "min_year": 2015}},
    "ltr_base_feats": {"ALL": {"l2": 1.0, "feats": list(range(28))}, "OUTSIDE": {"l2": 1.0, "feats": list(range(28))}},
    "ltr_linear_l2_30": {"ALL": {"l2": 30.0}, "OUTSIDE": {"l2": 30.0}},
}


def main(names):
    global EX
    import time
    t0 = time.time()
    EX = build_examples()
    print(f"built {len(EX)} examples in {time.time() - t0:.1f}s", flush=True)
    pool_recall()
    results = {}
    for name in names:
        rk = make_rank(VARIANTS[name])
        results[name] = H.evaluate(rk, name)
        if name == "ltr_linear":
            # show the weights of the last ALL / OUTSIDE model (standardized features)
            for (setting, q), m in sorted(rk.models.items())[-1:] + [kv for kv in sorted(rk.models.items())
                                                                     if kv[0][0] == "ALL"][-1:]:
                if m is None:
                    continue
                w = m.params["wl"]
                top = sorted(zip(FEATS, w), key=lambda x: -abs(x[1]))[:10]
                print(setting, q, " ".join(f"{f}={v:+.2f}" for f, v in top))
    return results


if __name__ == "__main__":
    main(sys.argv[1:] or list(VARIANTS))
