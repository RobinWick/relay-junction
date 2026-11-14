"""Collaborative filtering for "who leads the next round".

Rows = companies, columns = investors, all built from ctx.past only (rounds strictly before the test round).
Components (each a dict investor -> score, normalised to max 1, then mixed):
  trans : item->item transition. For every current investor i (idf-weighted, recent rounds weighted more),
          look at other companies where i invested in some round r, and score the LEADS of those companies'
          LATER rounds (stage-matched to the target stage). "Funds that follow my investors in."
  ucf   : user-based CF. Similarity(target, X) = idf-weighted overlap of investor sets (cosine); score leads of
          X's rounds at a stage similar to the target, weighted by similarity^alpha.
  cooc  : co-investor CF. Investors that co-invest with the current investors, weighted by how often they lead
          at the target stage.
  prior : recent stage/country popularity of leads (backoff only).
For ALL, insiders (last lead, then other current investors) are given an extra boost from the insider rule.
Run: python3 methods/collab_filter.py
"""
from __future__ import annotations

import math
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import harness  # noqa: E402

STAGE_ORD = {"pre-seed": 0, "seed": 1, "series a": 2, "series b": 3, "series c": 4, "series d": 5,
             "series e": 6, "series f": 7, "growth": 6}


def stage_sim(a, b) -> float:
    if a is None or b is None:
        return 0.35
    d = abs(STAGE_ORD.get(a, 3) - STAGE_ORD.get(b, 3))
    return math.exp(-1.0 * d)


def inv(r: dict) -> set:
    return harness.investors(r)


class Index:
    """Everything derived from ctx.past (strictly earlier rounds)."""

    def __init__(self, past: list[dict]):
        self.by_co: dict[str, list[dict]] = defaultdict(list)
        self.deg: dict[str, int] = defaultdict(int)          # number of companies an investor appears in
        self.inv_rounds: dict[str, list[tuple[str, int]]] = defaultdict(list)  # investor -> (ckey, idx in co list)
        for r in past:
            self.by_co[r["ckey"]].append(r)
        for ck, rs in self.by_co.items():
            seen = set()
            for j, r in enumerate(rs):
                for i in inv(r):
                    self.inv_rounds[i].append((ck, j))
                    seen.add(i)
            for i in seen:
                self.deg[i] += 1
        self.n_co = max(1, len(self.by_co))
        self.co_inv = {ck: set().union(*(inv(r) for r in rs)) for ck, rs in self.by_co.items()}

    def idf(self, i: str) -> float:
        return math.log(1 + self.n_co / (1 + self.deg.get(i, 0)))


def norm(d: dict) -> dict:
    if not d:
        return d
    m = max(d.values())
    return {k: v / m for k, v in d.items()} if m > 0 else d


def current_weights(ctx, ix: Index, recency: float) -> dict:
    """Weight of each current investor: idf * recency of the company round they were in (+ lead bonus)."""
    w = defaultdict(float)
    n = len(ctx.company_past)
    for k, r in enumerate(ctx.company_past):
        rw = recency ** (n - 1 - k)
        for i in inv(r):
            b = 1.5 if i in (r.get("leads") or []) else 1.0
            w[i] = max(w[i], rw * b * ix.idf(i))
    return w


def comp_trans(ctx, ix: Index, cw: dict, P: dict) -> dict:
    tgt_stage, tck, T = ctx.test.get("stage"), ctx.test["ckey"], ctx.test["t"]
    s = defaultdict(float)
    for i, wi in cw.items():
        occ = ix.inv_rounds.get(i, [])
        if not occ:
            continue
        acc = defaultdict(float)
        for ck, j in occ:
            if ck == tck:
                continue
            rs = ix.by_co[ck]
            later = rs[j + 1: j + 1 + P["horizon"]]
            for step, r2 in enumerate(later):
                ls = r2.get("leads") or []
                if not ls:
                    continue
                sw = stage_sim(r2.get("stage"), tgt_stage) * (P["step_decay"] ** step)
                sw *= math.exp(-P["time_decay"] * max(0.0, T - r2["t"]))
                for l in ls:
                    if l == i and not P["self_follow"]:
                        continue
                    acc[l] += sw / len(ls)
        # normalise by how active the investor is, so one huge fund does not dominate
        z = len(occ) ** P["occ_pow"]
        for l, v in acc.items():
            s[l] += wi * v / z
    return s


def comp_trans2(ctx, ix: Index, cw: dict, P: dict) -> dict:
    """Two hops: co-investors of current investors (weighted), then their later-round leads."""
    tck = ctx.test["ckey"]
    nb = defaultdict(float)
    for i, wi in cw.items():
        acc = defaultdict(float)
        for ck, j in ix.inv_rounds.get(i, []):
            if ck == tck:
                continue
            for o in inv(ix.by_co[ck][j]):
                if o != i and o not in cw:
                    acc[o] += 1.0
        z = sum(acc.values()) or 1.0
        for o, v in acc.items():
            nb[o] += wi * v / z
    top = dict(sorted(nb.items(), key=lambda kv: kv[1], reverse=True)[:P.get("hop_k", 30)])
    top = {o: v * ix.idf(o) for o, v in top.items()}
    return comp_trans(ctx, ix, top, P)


def comp_ucf(ctx, ix: Index, cw: dict, P: dict) -> dict:
    tgt_stage, tck, T = ctx.test.get("stage"), ctx.test["ckey"], ctx.test["t"]
    cand = defaultdict(float)
    for i, wi in cw.items():
        for ck, _ in ix.inv_rounds.get(i, []):
            if ck != tck:
                cand[ck] = 0.0
    if not cand:
        return {}
    na = math.sqrt(sum(v * v for v in cw.values())) or 1.0
    s = defaultdict(float)
    for ck in cand:
        other = ix.co_inv[ck]
        dot = sum(cw[i] * ix.idf(i) for i in other if i in cw)
        nb = math.sqrt(sum(ix.idf(i) ** 2 for i in other)) or 1.0
        sim = dot / (na * nb)
        if sim <= 0:
            continue
        sim = sim ** P["alpha"]
        for r in ix.by_co[ck]:
            ls = r.get("leads") or []
            if not ls:
                continue
            sw = stage_sim(r.get("stage"), tgt_stage) * math.exp(-P["time_decay"] * max(0.0, T - r["t"]))
            for l in ls:
                s[l] += sim * sw / len(ls)
    return s


def comp_cooc(ctx, ix: Index, cw: dict, P: dict, lead_stage: dict) -> dict:
    tck = ctx.test["ckey"]
    s = defaultdict(float)
    for i, wi in cw.items():
        acc = defaultdict(float)
        for ck, j in ix.inv_rounds.get(i, []):
            if ck == tck:
                continue
            r = ix.by_co[ck][j]
            for o in inv(r):
                if o != i:
                    acc[o] += 1.0
        z = sum(acc.values()) or 1.0
        for o, v in acc.items():
            s[o] += wi * v / z
    # only investors who actually lead at (or near) this stage are useful
    return {o: v * (lead_stage.get(o, 0.0) + P["cooc_floor"]) for o, v in s.items()}


def lead_stage_prior(ctx, P: dict) -> dict:
    st, T, ctry = ctx.test.get("stage"), ctx.test["t"], ctx.test.get("country")
    amt = ctx.test.get("amount_eur_m")
    c = defaultdict(float)
    for o in ctx.past:
        if T - o["t"] > 4:
            continue
        ls = o.get("leads") or []
        for l in ls:
            w = stage_sim(o.get("stage"), st) * math.exp(-P.get("prior_decay", 0.0) * (T - o["t"]))
            if ctry and o.get("country") == ctry:
                w *= P["country_boost"]
            a2 = o.get("amount_eur_m")
            if P.get("amt_sigma") and amt and a2:
                w *= 0.3 + math.exp(-(math.log(amt / a2) ** 2) / (2 * P["amt_sigma"] ** 2))
            c[l] += w
    return c


def make_rank(P: dict):
    def rank(ctx) -> list[str]:
        ix = Index(ctx.past)
        cw = current_weights(ctx, ix, P["recency"])
        prior_raw = lead_stage_prior(ctx, P)
        prior = norm(prior_raw)
        parts = {"prior": prior}
        if cw:
            parts["trans"] = norm(comp_trans(ctx, ix, cw, P))
            parts["ucf"] = norm(comp_ucf(ctx, ix, cw, P))
            parts["cooc"] = norm(comp_cooc(ctx, ix, cw, P, prior))
            if P["w"].get("trans2"):
                parts["trans2"] = norm(comp_trans2(ctx, ix, cw, P))
        score = defaultdict(float)
        excl = ctx.current if ctx.outside_only else set()
        for name, d in parts.items():
            w = P["w"].get(name, 0.0)
            if not w:
                continue
            if P.get("fusion") == "rrf":
                srt = sorted((k for k in d if k not in excl), key=d.get, reverse=True)[:300]
                for rk, k in enumerate(srt):
                    score[k] += w / (P["rrf_k"] + rk)
            else:
                for k, v in d.items():
                    score[k] += w * v
        if not ctx.outside_only and P["insider"] > 0:
            top = max(score.values()) if score else 1.0
            # insider rule: most recent lead first, then other current investors
            n = len(ctx.company_past)
            for k, r in enumerate(ctx.company_past):
                rw = P["recency"] ** (n - 1 - k)
                for l in r.get("leads") or []:
                    score[l] += P["insider"] * top * rw
                for p in r.get("participants") or []:
                    score[p] += P["insider"] * top * 0.35 * rw
        return sorted(score, key=score.get, reverse=True)[:100]
    return rank


BASE = dict(recency=0.6, horizon=2, step_decay=0.6, time_decay=0.15, self_follow=False, occ_pow=0.5,
            alpha=1.0, cooc_floor=0.05, country_boost=2.0, insider=3.0,
            w={"trans": 1.0, "ucf": 0.6, "cooc": 0.3, "prior": 0.15})


def variant(**kw) -> dict:
    P = dict(BASE)
    P["w"] = dict(BASE["w"])
    for k, v in kw.items():
        if k.startswith("w_"):
            P["w"][k[2:]] = v
        else:
            P[k] = v
    return P


R = dict(fusion="rrf", rrf_k=3, w_trans=1.0, w_ucf=1.0, w_cooc=0.7, w_prior=1.0)
VARIANTS = {
    "final": variant(**R, prior_decay=0.5, amt_sigma=1.0, w_trans2=0.5, horizon=3),
    "final_noprior": variant(**dict(R, w_prior=0.0), prior_decay=0.5, amt_sigma=1.0, w_trans2=0.5, horizon=3),
    "po_base": variant(w_trans=0, w_ucf=0, w_cooc=0, w_prior=1.0),
    "po_decay": variant(w_trans=0, w_ucf=0, w_cooc=0, w_prior=1.0, prior_decay=0.5),
    "po_amt": variant(w_trans=0, w_ucf=0, w_cooc=0, w_prior=1.0, amt_sigma=1.0),
    "po_c4": variant(w_trans=0, w_ucf=0, w_cooc=0, w_prior=1.0, country_boost=4.0, prior_decay=0.5),
    "rrf_t2": variant(**R, w_trans2=0.5),
    "rrf_t2b": variant(**R, w_trans2=1.0, hop_k=60),
    "rrf_h3": variant(**R, horizon=3),
    "rrf_dec": variant(**R, prior_decay=0.5, amt_sigma=1.0),
    "rrf": variant(fusion="rrf", rrf_k=3, w_trans=1.0, w_ucf=1.0, w_cooc=0.7, w_prior=0.5),
    "rrf_k10": variant(fusion="rrf", rrf_k=10, w_trans=1.0, w_ucf=1.0, w_cooc=0.7, w_prior=0.5),
    "rrf_k1": variant(fusion="rrf", rrf_k=1, w_trans=1.0, w_ucf=1.0, w_cooc=0.7, w_prior=0.5),
    "rrf_p1": variant(fusion="rrf", rrf_k=3, w_trans=1.0, w_ucf=1.0, w_cooc=0.7, w_prior=1.0),
    "rrf_p02": variant(fusion="rrf", rrf_k=3, w_trans=1.0, w_ucf=1.0, w_cooc=0.5, w_prior=0.25),
    "base": variant(),
    "trans_only": variant(w_ucf=0, w_cooc=0, w_prior=0.0),
    "ucf_only": variant(w_trans=0, w_cooc=0, w_prior=0.0),
    "cooc_only": variant(w_trans=0, w_ucf=0, w_prior=0.0),
    "prior_only": variant(w_trans=0, w_ucf=0, w_cooc=0, w_prior=1.0),
}

if __name__ == "__main__":
    names = sys.argv[1:] or ["final"]
    for nm in names:
        if nm.startswith("split:"):
            v = nm.split(":")[1]
            harness.evaluate(make_rank(VARIANTS[v]), f"cf_{v}_<=2023", subset=lambda r: r["year"] <= 2023)
            harness.evaluate(make_rank(VARIANTS[v]), f"cf_{v}_>=2024", subset=lambda r: r["year"] >= 2024)
            continue
        harness.evaluate(make_rank(VARIANTS[nm]), f"cf_{nm}")
