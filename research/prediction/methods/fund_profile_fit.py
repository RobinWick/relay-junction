"""Fund-profile fit: score each past investor by how well its recent lead profile fits the target round.

For candidate i and target round T, every past participation e of i (strictly before T) is a kernel vote:
    vote(e) = role(e) * time_decay(T.t - e.t) * stage_sim(e, T) * amount_sim(e, T) * country_sim(e, T)
role = 1 for a lead, `alpha` for a non-lead participation.
Variants:
  - "mult" (kernel): score = sum(vote)  -> dimensions multiply inside each past round
  - "add": score = activity * (1 + ws*stage_share + wa*amount_fit + wc*country_share) with per-candidate profile shares
  - optional lead-share factor (leads / all rounds), recency-of-last-lead factor
ALL setting: insiders get boosts (previous lead of this company, other current investors).

Information rule: everything is computed from ctx.past (a prefix of the time-sorted rounds) at call time.
The only global structure is an investor-key -> integer index map (no statistics) and per-round parsed fields.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import harness as H  # noqa: E402

# ---------- static parsing (no statistics) ----------
STAGE_ORD = {"pre-seed": 0, "seed": 1, "series a": 2, "series b": 3, "series c": 4, "series d": 5,
             "growth": 5.5, "series e": 6, "series f": 7}
CNORM = {"UK": "United Kingdom", "USA": "United States", "US": "United States",
         "Spain (Barcelona)": "Spain"}
REGION = {}
for c in ("Sweden", "Finland", "Denmark", "Norway", "Iceland"):
    REGION[c] = "nordics"
for c in ("Estonia", "Latvia", "Lithuania"):
    REGION[c] = "baltics"
for c in ("Germany", "Austria", "Switzerland"):
    REGION[c] = "dach"
for c in ("Netherlands", "Belgium", "Luxembourg"):
    REGION[c] = "benelux"
for c in ("United Kingdom", "Ireland"):
    REGION[c] = "ukie"
for c in ("Spain", "Portugal", "Italy", "Greece"):
    REGION[c] = "south"
for c in ("Poland", "Czech Republic", "Czechia", "Hungary", "Romania", "Bulgaria", "Croatia", "Slovakia",
          "Slovenia", "Ukraine", "Serbia"):
    REGION[c] = "cee"
REGION["France"] = "france"
REGION["United States"] = "us"
REGION["Canada"] = "us"
SUPER = {"nordics": "north", "baltics": "north", "dach": "west", "benelux": "west", "france": "west",
         "ukie": "west", "south": "west", "cee": "north", "us": "us"}


def norm_country(c):
    if not c:
        return None
    c = c.strip()
    return CNORM.get(c, c)


KEYS: dict[str, int] = {}
for _r in H.ROUNDS:
    for _k in sorted(H.investors(_r)):
        KEYS.setdefault(_k, len(KEYS))
INV = np.array(list(KEYS), dtype=object)
NI = len(KEYS)

_c_ids: dict[str, int] = {}
_reg_ids: dict[str, int] = {}
_sup_ids: dict[str, int] = {}


def _cid(d, k):
    if k is None:
        return -1
    return d.setdefault(k, len(d))


# flattened participation entries in time order
e_inv, e_lead, e_t, e_stage, e_amt, e_c, e_reg, e_sup, e_round = [], [], [], [], [], [], [], [], []
ROUND_OFF = [0]
for ri, r in enumerate(H.ROUNDS):
    leads = set(r.get("leads") or [])
    c = norm_country(r.get("country"))
    reg = REGION.get(c) if c else None
    sup = SUPER.get(reg) if reg else None
    st = STAGE_ORD.get(r.get("stage"), np.nan)
    a = r.get("amount_eur_m")
    la = math.log(a) if a and a > 0 else np.nan
    for k in sorted(H.investors(r)):
        e_inv.append(KEYS[k]); e_lead.append(k in leads); e_t.append(r["t"]); e_stage.append(st)
        e_amt.append(la); e_c.append(_cid(_c_ids, c)); e_reg.append(_cid(_reg_ids, reg)); e_sup.append(_cid(_sup_ids, sup))
        e_round.append(ri)
    ROUND_OFF.append(len(e_inv))
E_INV = np.array(e_inv); E_LEAD = np.array(e_lead, dtype=bool); E_T = np.array(e_t)
E_STAGE = np.array(e_stage, dtype=float); E_AMT = np.array(e_amt, dtype=float)
E_C = np.array(e_c); E_REG = np.array(e_reg); E_SUP = np.array(e_sup); E_ROUND = np.array(e_round)


def _offset(ctx) -> int:
    """Number of entries belonging to ctx.past (a prefix of H.ROUNDS)."""
    n = len(ctx.past)
    assert n == 0 or ctx.past[-1] is H.ROUNDS[n - 1]
    return ROUND_OFF[n]


# ---------- scoring ----------
DEFAULT = dict(
    mode="mult", tau=2.0, alpha=0.25, stage_a=0.7, stage_unk=0.5, amt_s=1.0, amt_unk=0.6,
    c_same=1.0, c_reg=0.5, c_sup=0.25, c_other=0.12, c_unk=0.3,
    stage_a_later=None, gen_pow=0.0, lead_share_pow=0.0, recency_tau=0.0, max_age=8.0,
    ws=1.0, wa=1.0, wc=1.0,
    b_lastlead=50.0, b_anylead=10.0, b_current=2.0, insider_mode="mult",
)


def scores(ctx, p) -> np.ndarray:
    off = _offset(ctx)
    tg = ctx.target
    T = tg["t"]
    sl = slice(0, off)
    age = T - E_T[sl]
    keep = age <= p["max_age"]
    inv = E_INV[sl][keep]
    lead = E_LEAD[sl][keep]
    age = age[keep]
    w_time = np.exp(-age / p["tau"])
    role = np.where(lead, 1.0, p["alpha"])

    # stage similarity
    ts = STAGE_ORD.get(tg.get("stage"))
    est = E_STAGE[sl][keep]
    if ts is None:
        s_sim = np.full(len(est), p["stage_unk"])
    else:
        d = est - ts  # >0: candidate's past round was later-stage than the target
        a_dn = p["stage_a"] if p["stage_a_later"] is None else p["stage_a_later"]
        k = np.where(d > 0, a_dn, p["stage_a"]) * np.abs(d)
        s_sim = np.where(np.isnan(d), p["stage_unk"], np.exp(-np.nan_to_num(k)))

    # amount similarity (log distance)
    a = tg.get("amount_eur_m")
    eam = E_AMT[sl][keep]
    if a and a > 0:
        d = np.abs(eam - math.log(a))
        a_sim = np.where(np.isnan(d), p["amt_unk"], np.exp(-0.5 * (d / p["amt_s"]) ** 2))
    else:
        a_sim = np.full(len(eam), p["amt_unk"])

    # country similarity
    c = norm_country(tg.get("country"))
    reg = REGION.get(c) if c else None
    sup = SUPER.get(reg) if reg else None
    ec, er, es = E_C[sl][keep], E_REG[sl][keep], E_SUP[sl][keep]
    if c is None:
        c_sim = np.full(len(ec), p["c_unk"])
    else:
        cid = _c_ids.get(c, -2); rid = _reg_ids.get(reg, -2) if reg else -2; sid = _sup_ids.get(sup, -2) if sup else -2
        c_sim = np.where(ec == cid, p["c_same"],
                np.where(er == rid, p["c_reg"],
                np.where(es == sid, p["c_sup"],
                np.where(ec < 0, p["c_unk"], p["c_other"]))))

    if p["mode"] == "mult":
        v = role * w_time * s_sim * a_sim * c_sim
        sc = np.bincount(inv, weights=v, minlength=NI)
    else:  # additive profile fit
        w = role * w_time
        act = np.bincount(inv, weights=w, minlength=NI)
        den = act + 0.5
        st_share = np.bincount(inv, weights=w * s_sim, minlength=NI) / den
        am_share = np.bincount(inv, weights=w * a_sim, minlength=NI) / den
        c_share = np.bincount(inv, weights=w * c_sim, minlength=NI) / den
        sc = act * (1 + p["ws"] * st_share + p["wa"] * am_share + p["wc"] * c_share)

    if p["gen_pow"]:
        act = np.bincount(inv, weights=role * w_time, minlength=NI)
        sc = sc / (act + 1.0) ** p["gen_pow"]
    if p["lead_share_pow"]:
        nl = np.bincount(inv, weights=lead * w_time, minlength=NI)
        na = np.bincount(inv, weights=w_time, minlength=NI)
        sc = sc * ((nl + 0.2) / (na + 1.0)) ** p["lead_share_pow"]
    if p["recency_tau"]:
        last = np.full(NI, -1e9)
        np.maximum.at(last, inv[lead], E_T[sl][keep][lead])
        sc = sc * (0.3 + np.exp(-np.clip(T - last, 0, 50) / p["recency_tau"]))
    return sc


def insider_adjust(ctx, sc, p):
    if ctx.outside_only:
        return sc
    sc = sc.copy()
    base = sc.max() if sc.max() > 0 else 1.0
    last_leads = set()
    for o in reversed(ctx.company_past):
        if o.get("leads"):
            last_leads = set(o["leads"]); break
    any_leads = set().union(*(set(o.get("leads") or []) for o in ctx.company_past)) if ctx.company_past else set()
    for k in ctx.current:
        i = KEYS[k]
        if p["insider_mode"] == "mult":
            f = p["b_lastlead"] if k in last_leads else p["b_anylead"] if k in any_leads else p["b_current"]
            sc[i] = sc[i] * f + 1e-6 * f
        else:  # additive bump relative to the top outside score
            b = p["b_lastlead"] if k in last_leads else p["b_anylead"] if k in any_leads else p["b_current"]
            sc[i] = sc[i] + b * base
    return sc


def make_rank(**kw):
    p = dict(DEFAULT); p.update(kw)

    def rank(ctx):
        sc = insider_adjust(ctx, scores(ctx, p), p)
        if ctx.outside_only:
            for k in ctx.current:
                sc[KEYS[k]] = -1
        top = np.argpartition(-sc, 60)[:60]
        top = top[np.argsort(-sc[top])]
        return [INV[i] for i in top if sc[i] > 0]
    return rank


# Hyperparameters chosen by coordinate descent on the EARLY half of the test set only (t < 2024.333);
# the late half (t >= 2024.333) is the held-out check. Sweep script lived in the session scratchpad.
OUTSIDE_BEST = {"mode": "mult", "tau": 3.0, "alpha": 0.0, "c_sup": 0.05}
ALL_BEST = {"mode": "mult", "tau": 5.0, "alpha": 0.1, "c_sup": 0.05, "c_reg": 0.2, "stage_a": 1.2,
            "insider_mode": "add", "b_lastlead": 200, "b_anylead": 100, "b_current": 10}
LATE = lambda r: r["t"] >= 2024.333  # noqa: E731

if __name__ == "__main__":
    import json
    if len(sys.argv) > 1:
        H.evaluate(make_rank(**(json.loads(sys.argv[2]) if len(sys.argv) > 2 else {})), sys.argv[1])
    else:
        H.evaluate(make_rank(), "fpf_default")
        H.evaluate(make_rank(mode="add"), "fpf_additive_default")
        H.evaluate(make_rank(**OUTSIDE_BEST), "fpf_outside_tuned")
        H.evaluate(make_rank(**ALL_BEST), "fpf_all_tuned")
        print("--- held-out late half (t >= 2024.333) ---")
        H.evaluate(make_rank(**OUTSIDE_BEST), "fpf_outside_tuned_late", subset=LATE)
        H.evaluate(make_rank(**ALL_BEST), "fpf_all_tuned_late", subset=LATE)
        H.evaluate(H.last_lead_again, "last_lead_again_late", subset=LATE)
        H.evaluate(H.stage_leads, "stage_leads_late", subset=LATE)
