"""narrow_tasks: product-realistic narrower questions on the shared lead-prediction backtest.

Scorer (all statistics from ctx.past only, cached per time cut):
  insider part: previous lead(s) of the company > earlier leads > participants (recency-weighted)
  outside part: stage-group lead popularity (3y, decayed), same-country leads, co-investment with the
                company's current investors, and "follow-on lead" (f led a later round of a company where a
                current investor of the target was already on the cap table).
Narrow questions:
  (a) per stage group, (b) Nordic companies, (c) candidate universe = funds with >=3 leads in last 3y,
  (d) binary "will a current investor lead?" with a numpy logistic model trained on earlier test-like rounds.
Run: python3 methods/narrow_tasks.py

AUDITED COPY (2026-11-14). Leak fixed: 72% of ctx.past (3752/5200 rounds) exists only because 195 funds were
crawled investor-first in 2026, and that fund list was chosen partly by counting appearances in company-first
rounds of ALL years, including the 2021-2026 test rounds (cala/fetch_funds.py fund_list). Every outside signal
(stage/country/global popularity, follow, coinv, lead_n3 universe, reup) was dominated by those rows, so a fund
looked "active" in the past partly because it leads in the test set. Fix: statistics use only rounds that have a
company_first source (AUDIT_PAST=cf, default). AUDIT_PAST=cf_ins also strips investor-first-only rows from the
insider (company_past) part. AUDIT_PAST=all reproduces the original. Cache is keyed by (cut, t0), not cut.
"""
from __future__ import annotations

import os

import bisect
import math
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import harness as H  # noqa: E402
import numpy as np  # noqa: E402

NORDIC = {"Finland", "Sweden", "Denmark", "Norway", "Iceland", "Estonia"}


def stage_group(s):
    if s in ("pre-seed", "seed"):
        return "seed"
    if s == "series a":
        return "a"
    if s in ("series b", "series c", "series d", "series e", "series f", "growth"):
        return "b+"
    return "none"


# ---------------- per-cut statistics (only rounds strictly before the cut) ----------------
_CACHE: dict[tuple, dict] = {}
AUDIT_PAST = os.environ.get("AUDIT_PAST", "cf")
assert AUDIT_PAST in ("cf", "cf_ins", "all"), AUDIT_PAST


def is_cf(o) -> bool:
    return any(x.get("path") == "company_first" for x in o.get("sources") or [])


def keep(rows):
    return rows if AUDIT_PAST == "all" else [o for o in rows if is_cf(o)]


def company_past_for(ctx):
    return [o for o in ctx.company_past if is_cf(o)] if AUDIT_PAST == "cf_ins" else ctx.company_past


def stats_for(ctx) -> dict:
    t0 = ctx.test["t"]
    key = (len(ctx.past), t0)
    if key in _CACHE:
        return _CACHE[key]
    past = keep(ctx.past)
    lead_stage = defaultdict(lambda: defaultdict(float))   # group -> fund -> decayed count
    lead_country = defaultdict(lambda: defaultdict(float))
    lead_all = defaultdict(float)
    lead_n3 = defaultdict(int)                             # raw lead count in last 3 years
    by_company = defaultdict(list)
    inv_rounds = defaultdict(list)                         # fund -> list of round idx
    for i, o in enumerate(past):
        by_company[o["ckey"]].append(o)
        age = t0 - o["t"]
        w = math.exp(-age / 2.0)
        g = stage_group(o.get("stage"))
        for l in o.get("leads") or []:
            lead_all[l] += w
            lead_stage[g][l] += w
            if o.get("country"):
                lead_country[o["country"]][l] += w
            if age <= 3:
                lead_n3[l] += 1
        for x in H.investors(o):
            inv_rounds[x].append(i)
    # follow-on: for each fund A, which funds led a LATER round of a company A was already in
    follow = defaultdict(lambda: defaultdict(float))
    coinv = defaultdict(lambda: defaultdict(float))
    reup_opp, reup_led = defaultdict(int), defaultdict(int)   # fund already on cap table -> led the next round?
    for rs in by_company.values():
        seen: set[str] = set()
        for o in rs:
            if o.get("leads"):
                for a in seen:
                    reup_opp[a] += 1
                    reup_led[a] += a in o["leads"]
            for l in o.get("leads") or []:
                for a in seen:
                    if a != l:
                        follow[a][l] += 1
            inv = H.investors(o)
            for a in inv:
                for b in inv:
                    if a != b:
                        coinv[a][b] += 1
            seen |= inv
    st = dict(lead_stage=lead_stage, lead_country=lead_country, lead_all=lead_all, lead_n3=lead_n3,
              follow=follow, coinv=coinv, reup_opp=reup_opp, reup_led=reup_led)
    _CACHE.clear() if len(_CACHE) > 4 else None
    _CACHE[key] = st
    return st


# ---------------- scorer ----------------
W_DEFAULT = dict(ins_last=100.0, ins_lead=40.0, ins_part=10.0, stage=1.0, country=1.5, follow=2.0, coinv=0.5, glob=0.2)


def norm(d: dict) -> dict:
    m = max(d.values()) if d else 0
    return {k: v / m for k, v in d.items()} if m else {}


def score(ctx, W=W_DEFAULT) -> dict:
    st = stats_for(ctx)
    tg = ctx.target
    s = defaultdict(float)
    # insiders
    cp = company_past_for(ctx)
    if cp:
        ins = defaultdict(float)
        for l in cp[-1].get("leads") or []:
            ins[l] += W["ins_last"]
        for j, o in enumerate(reversed(cp)):
            dec = 0.7 ** j
            for l in o.get("leads") or []:
                ins[l] += W["ins_lead"] * dec
            for p in o.get("participants") or []:
                ins[p] += W["ins_part"] * dec
        a = W.get("reup", 0.0)
        for f, v in ins.items():
            rate = (st["reup_led"].get(f, 0) + 0.25) / (st["reup_opp"].get(f, 0) + 1.0)
            s[f] += v * (1 - a + a * 4 * rate)
    # outside signals (each normalised to max 1 then weighted)
    g = stage_group(tg.get("stage"))
    for f, v in norm(st["lead_stage"].get(g, {})).items():
        s[f] += W["stage"] * v
    for f, v in norm(st["lead_country"].get(tg.get("country"), {})).items():
        s[f] += W["country"] * v
    for f, v in norm(st["lead_all"]).items():
        s[f] += W["glob"] * v
    fol, co = defaultdict(float), defaultdict(float)
    cur = set().union(*(H.investors(o) for o in cp)) if AUDIT_PAST == "cf_ins" else ctx.current
    for a in cur:
        for f, v in st["follow"].get(a, {}).items():
            fol[f] += v
        for f, v in st["coinv"].get(a, {}).items():
            co[f] += v
    for f, v in norm(fol).items():
        s[f] += W["follow"] * v
    for f, v in norm(co).items():
        s[f] += W["coinv"] * v
    return s


def make_rank(W=W_DEFAULT, universe_min=None):
    def rank(ctx):
        s = score(ctx, W)
        if universe_min is not None:
            uni = universe(ctx, universe_min)
            s = {f: v for f, v in s.items() if f in uni}
        return sorted(s, key=s.get, reverse=True)[:50]
    return rank


def universe(ctx, k=3) -> set[str]:
    """Funds that led >= k rounds in the 3 years before the target (from ctx.past)."""
    return {f for f, n in stats_for(ctx)["lead_n3"].items() if n >= k}


# ---------------- (d) binary: will a current investor lead? ----------------
def bin_features(company_past: list[dict], t: float, stage, st: dict) -> list[float]:
    lead_n3 = st["lead_n3"]
    last = company_past[-1]
    cur = set().union(*(H.investors(o) for o in company_past))
    last_leads = last.get("leads") or []
    sg = stage_group(stage)
    return [
        1.0,
        math.log1p(len(cur)),
        math.log1p(len(company_past)),
        1.0 if last_leads else 0.0,
        min(5.0, t - last["t"]),
        math.log1p(max((lead_n3.get(l, 0) for l in cur), default=0)),   # most active current lead-er
        math.log1p(sum(lead_n3.get(l, 0) for l in last_leads)),
        1.0 if sg == "seed" else 0.0,
        1.0 if sg == "a" else 0.0,
        1.0 if sg == "b+" else 0.0,
        1.0 if stage_group(last.get("stage")) == sg and sg != "none" else 0.0,  # same stage again (extension)
        math.log1p(float((last.get("amount_eur_m") or 0))),
        max((reup(st, f) for f in last_leads), default=0.0),          # last lead's historic re-lead rate
        max((reup(st, f) for f in cur), default=0.0),
        sum(reup(st, f) for f in cur),
    ]


def reup(st, f):
    return (st["reup_led"].get(f, 0) + 0.25) / (st["reup_opp"].get(f, 0) + 1.0)


def fit_logreg(X, y, l2=3.0, iters=50):
    X, y = np.asarray(X), np.asarray(y, dtype=float)
    w = np.zeros(X.shape[1])
    for _ in range(iters):  # Newton steps
        p = 1 / (1 + np.exp(-np.clip(X @ w, -30, 30)))
        g = X.T @ (p - y) + l2 * np.r_[0, w[1:]]
        Hm = (X * (p * (1 - p))[:, None]).T @ X + l2 * np.diag(np.r_[0, np.ones(len(w) - 1)])
        step = np.linalg.solve(Hm, g)
        w -= step
        if not np.all(np.isfinite(step)) or np.abs(step).max() < 1e-6:
            break
    return w


def test_like_examples():
    """Every lead-named company-first round with an earlier round of the same company (any year), sorted by t."""
    ex = []
    for r in H.ROUNDS:
        if not r.get("leads"):
            continue
        if not any(x.get("path") == "company_first" for x in r.get("sources") or []):
            continue
        cp = [o for o in H.BY_COMPANY[r["ckey"]] if o["t"] < r["t"] - H.EPS]
        if cp:
            ex.append((r, cp))
    return ex


def auc(scores, labels):
    pos = [s for s, l in zip(scores, labels) if l]
    neg = [s for s, l in zip(scores, labels) if not l]
    if not pos or not neg:
        return float("nan")
    c = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return c / (len(pos) * len(neg))


def run_binary():
    ex = test_like_examples()
    feats = []  # time-correct features: each example uses stats from rounds strictly before itself
    for o, ocp in ex:
        octx = H.context(o, False)
        feats.append((o["t"], bin_features(ocp, o["t"], o.get("stage"), stats_for(octx)),
                      1 if set(o["leads"]) & octx.current else 0))
    preds, labels, rule, prior = [], [], [], []
    for r in H.TEST:
        ctx = H.context(r, False)
        cut_t = r["t"] - H.EPS
        X = [f for t, f, _ in feats if t < cut_t]
        y = [l for t, _, l in feats if t < cut_t]
        x = bin_features(ctx.company_past, r["t"], r.get("stage"), stats_for(ctx))
        if len(y) >= 30 and 0 < sum(y) < len(y):
            Xa = np.asarray(X)
            mu, sd = Xa.mean(0), Xa.std(0) + 1e-9
            mu[0], sd[0] = 0.0, 1.0  # keep intercept
            w = fit_logreg((Xa - mu) / sd, y)
            p = float(1 / (1 + np.exp(-np.clip(np.dot(w, (np.asarray(x) - mu) / sd), -30, 30))))
        else:
            p = (sum(y) + 1) / (len(y) + 2)
        prior.append((sum(y) + 1) / (len(y) + 2))
        preds.append(p)
        labels.append(1 if set(r["leads"]) & ctx.current else 0)
        rule.append(x[-3])  # last lead's historic re-lead rate alone
    n = len(labels)
    base = sum(labels) / n
    acc = sum((p >= 0.5) == bool(l) for p, l in zip(preds, labels)) / n
    maj = max(base, 1 - base)
    brier = sum((p - l) ** 2 for p, l in zip(preds, labels)) / n
    brier0 = sum((q - l) ** 2 for q, l in zip(prior, labels)) / n
    a = auc(preds, labels)
    # bootstrap AUC CI
    rng = np.random.default_rng(0)
    P, L = np.array(preds), np.array(labels)
    boots = []
    for _ in range(300):
        idx = rng.integers(0, n, n)
        boots.append(auc(P[idx].tolist(), L[idx].tolist()))
    boots = sorted(b for b in boots if not math.isnan(b))
    lo, hi = boots[int(0.025 * len(boots))], boots[int(0.975 * len(boots)) - 1]
    # top-decile precision: how often an insider leads when model is most confident
    order = np.argsort(-P)
    top = order[: n // 5]
    bot = order[-(n // 5):]
    out = dict(n=n, base_rate=round(base, 3), auc=round(a, 3), auc_ci=(round(lo, 3), round(hi, 3)),
               acc=round(acc, 3), acc_ci=tuple(round(v, 3) for v in H.wilson(round(acc * n), n)),
               majority_acc=round(maj, 3), brier=round(brier, 4), brier_prior=round(brier0, 4),
               top20pct_rate=round(float(L[top].mean()), 3), bottom20pct_rate=round(float(L[bot].mean()), 3),
               rule_reup_rate_auc=round(auc(rule, labels), 3))
    print("BINARY current-investor-leads:", out, flush=True)
    return out


# ---------------- (c) universe-restricted evaluation with coverage ----------------
def run_universe(rank_fn, k=3):
    """Two numbers: rank restricted to the universe on all rounds, and hit@k conditional on a true lead being in it."""
    print(f"-- universe: funds with >={k} leads in last 3y", flush=True)
    H.evaluate(make_rank(W_BEST, universe_min=k), f"univ{k}_all_rounds")

    def in_univ(r):
        ctx = H.context(r, False)
        return bool(set(r["leads"]) & universe(ctx, k))  # evaluation-only predicate (defines the subset)

    def in_univ_out(r):
        ctx = H.context(r, True)
        return bool((set(r["leads"]) - ctx.current) & universe(ctx, k))

    cov_all = sum(in_univ(r) for r in H.TEST)
    print(f"coverage ALL: {cov_all}/{len(H.TEST)} test rounds have a true lead in the universe", flush=True)
    sizes = [len(universe(H.context(r, False), k)) for r in H.TEST[::25]]
    print(f"mean universe size (sampled): {sum(sizes)/len(sizes):.0f}", flush=True)
    H.evaluate(make_rank(W_BEST, universe_min=k), f"univ{k}_cond_ALL", subset=in_univ)
    H.evaluate(make_rank(W_BEST, universe_min=k), f"univ{k}_cond_OUT", subset=in_univ_out)


VARIANTS = {
    "default": W_DEFAULT,
    "no_follow": {**W_DEFAULT, "follow": 0.0, "coinv": 0.0},
    "follow_heavy": {**W_DEFAULT, "follow": 4.0, "coinv": 1.0},
    "country_heavy": {**W_DEFAULT, "country": 3.0},
    "reup": {**W_DEFAULT, "reup": 1.0},
    "reup_half_follow": {**W_DEFAULT, "reup": 0.5, "follow": 4.0, "coinv": 1.0},
}
W_BEST = W_DEFAULT

if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    if which.startswith("variant:"):
        name = which.split(":", 1)[1]
        H.evaluate(make_rank(VARIANTS[name]), f"nt_{name}")
    if which in ("variants", "all"):
        for name, W in VARIANTS.items():
            H.evaluate(make_rank(W), f"nt_{name}")
    if which in ("subsets", "all"):
        rk = make_rank(W_BEST)
        for g in ("seed", "a", "b+"):
            H.evaluate(rk, f"nt_stage_{g}", subset=lambda r, g=g: stage_group(r.get("stage")) == g)
            H.evaluate(H.last_lead_again, f"base_lastlead_{g}", subset=lambda r, g=g: stage_group(r.get("stage")) == g)
            H.evaluate(H.stage_leads, f"base_stage_{g}", subset=lambda r, g=g: stage_group(r.get("stage")) == g)
        H.evaluate(rk, "nt_nordic", subset=lambda r: r.get("country") in NORDIC)
        H.evaluate(H.last_lead_again, "base_lastlead_nordic", subset=lambda r: r.get("country") in NORDIC)
        H.evaluate(H.stage_leads, "base_stage_nordic", subset=lambda r: r.get("country") in NORDIC)
    if which in ("universe", "all"):
        run_universe(make_rank(W_BEST))
    if which.startswith("universe:"):
        run_universe(make_rank(W_BEST), k=int(which.split(":")[1]))
    if which in ("binary", "all"):
        run_binary()
