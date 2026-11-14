"""Handoff / stage-transition edges for predicting who leads a company's next round.

Edges are learned ONLY from ctx.past, incrementally in time order:
  for every past round r of company c and the company's earlier past rounds p (t_p < t_r - EPS),
  each investor A in p (weighted by role and recency) -> each lead B of r  ("handoff" A->B).
  Stage transitions: (lead L at stage S) -> lead B at the next round's stage.
Score(B) = sum_A w_A * n(A->B) / (out(A) + alpha)          (handoff, smoothed per source)
         + beta * stage-popularity(B | target stage, recent)  (Bayesian prior / backoff)
         + gamma * insider prior (ALL setting only: last lead again etc.)

Run: python3 methods/handoff_edges.py
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import harness  # noqa: E402

EPS = harness.EPS

class EdgeState:
    """Incremental edge statistics built only from rounds the method is shown (ctx.past), in time order."""

    def __init__(self) -> None:
        self.n_seen = 0
        self.by_company: dict[str, list[dict]] = defaultdict(list)
        # handoff edges: A -> B with timestamps (t of the round B led) and role of A
        self.edges: dict[str, dict[str, list[tuple[float, float]]]] = defaultdict(lambda: defaultdict(list))
        self.out: dict[str, list[tuple[float, float]]] = defaultdict(list)
        # stage-conditioned lead popularity: stage -> lead -> [t]
        self.stage_leads: dict[str | None, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        # country lead popularity
        self.country_leads: dict[str | None, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        # stage transition: (prev lead) -> next lead, only when prev round had leads
        self.trans: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        self.trans_out: dict[str, list[float]] = defaultdict(list)
        # (from stage, to stage) -> lead -> [t]
        self.stage_pair_leads: dict[tuple, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        # how often each investor leads at all vs appears
        self.lead_count: dict[str, list[float]] = defaultdict(list)
        self.cs_leads: dict[tuple, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        self.country_inv: dict[str | None, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        # co-investment edges in the SAME round: A (any role) -> B (lead), and A (lead) -> B (participant)
        self.coL: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        self.coL_out: dict[str, list[float]] = defaultdict(list)
        self.coP: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        self.coP_out: dict[str, list[float]] = defaultdict(list)

    def add(self, r: dict) -> None:
        t = r["t"]
        leads = r.get("leads") or []
        prev = [p for p in self.by_company[r["ckey"]] if p["t"] < t - EPS]
        inv = set(leads) | set(r.get("participants") or [])
        for a in inv:
            others = [b for b in leads if b != a]
            if others:
                self.coL_out[a].append(t)
                for b in others:
                    self.coL[a][b].append(t)
        for a in leads:
            parts = [b for b in (r.get("participants") or []) if b not in leads]
            if parts:
                self.coP_out[a].append(t)
                for b in parts:
                    self.coP[a][b].append(t)
        for a in inv:
            self.country_inv[r.get("country")][a].append(t)
        for l in leads:
            self.cs_leads[(r.get("country"), r.get("stage"))][l].append(t)
            self.stage_leads[r.get("stage")][l].append(t)
            self.country_leads[r.get("country")][l].append(t)
            self.lead_count[l].append(t)
        if prev and leads:
            last_t = max(p["t"] for p in prev)
            last_rounds = [p for p in prev if p["t"] >= last_t - EPS]
            # sources: investors in the immediately previous round (role weight), older rounds down-weighted
            src: dict[str, float] = {}
            for p in prev:
                rec = 1.0 if p in last_rounds else 0.35
                for a in p.get("participants") or []:
                    src[a] = max(src.get(a, 0), 0.6 * rec)
                for a in p.get("leads") or []:
                    src[a] = max(src.get(a, 0), 1.0 * rec)
            for a, w in src.items():
                self.out[a].append((t, w))
                for b in leads:
                    self.edges[a][b].append((t, w / len(leads)))
            pst = last_rounds[-1].get("stage")
            for p in last_rounds:
                for a in p.get("leads") or []:
                    self.trans_out[a].append(t)
                    for b in leads:
                        self.trans[a][b].append(t)
            for b in leads:
                self.stage_pair_leads[(pst, r.get("stage"))][b].append(t)
        self.by_company[r["ckey"]].append(r)

    def sync(self, past: list[dict]) -> None:
        if len(past) < self.n_seen:
            self.__init__()
        for r in past[self.n_seen:]:
            self.add(r)
        self.n_seen = len(past)


STATES: dict[str, EdgeState] = {}


def state_for(ctx: harness.Context, key: str) -> EdgeState:
    st = STATES.setdefault(key, EdgeState())
    st.sync(ctx.past)
    return st


def decay(ts, t: float, half: float) -> float:
    if half <= 0:
        return float(len(ts))
    return sum(0.5 ** ((t - x) / half) for x in ts)


def decay_w(tws, t: float, half: float) -> float:
    if half <= 0:
        return sum(w for _, w in tws)
    return sum(w * 0.5 ** ((t - x) / half) for x, w in tws)


def make_rank(alpha=2.0, beta=0.05, half=3.0, use_trans=0.5, use_pair=0.0, country_w=0.0,
              insider=True, ins_mode="lastlead", pop_half=2.0, src_mode="all", lead_rate=0.0,
              co_l=0.0, co_p=0.0, any_w=0.0, ins_bonus=0.0, cs_w=0.0, capp_w=0.0, hop2=0.0):
    key = f"{alpha}-{beta}-{half}-{use_trans}-{use_pair}-{country_w}-{insider}-{ins_mode}-{pop_half}-{src_mode}-{lead_rate}"

    def rank(ctx: harness.Context) -> list[str]:
        st = state_for(ctx, "shared")
        tgt = ctx.target
        t, stage, country = tgt["t"], tgt["stage"], tgt["country"]
        cp = ctx.company_past
        score: dict[str, float] = defaultdict(float)
        if cp:
            last_t = cp[-1]["t"]
            last = [p for p in cp if p["t"] >= last_t - EPS]
            src: dict[str, float] = {}
            for p in cp:
                rec = 1.0 if p in last else 0.35
                if src_mode == "last" and p not in last:
                    continue
                for a in p.get("participants") or []:
                    src[a] = max(src.get(a, 0), 0.6 * rec)
                for a in p.get("leads") or []:
                    src[a] = max(src.get(a, 0), 1.0 * rec)
            for a, w in src.items():
                outd = decay_w(st.out.get(a, ()), t, half)
                if outd <= 0:
                    continue
                for b, tws in st.edges[a].items():
                    score[b] += w * decay_w(tws, t, half) / (outd + alpha)
            if use_trans:
                for p in last:
                    for a in p.get("leads") or []:
                        outd = decay(st.trans_out.get(a, ()), t, half)
                        if outd <= 0:
                            continue
                        for b, ts in st.trans[a].items():
                            score[b] += use_trans * decay(ts, t, half) / (outd + alpha)
            for a, w in src.items():
                if co_l:
                    outd = decay(st.coL_out.get(a, ()), t, half)
                    if outd > 0:
                        for b, ts in st.coL[a].items():
                            score[b] += co_l * w * decay(ts, t, half) / (outd + alpha)
                if co_p:
                    outd = decay(st.coP_out.get(a, ()), t, half)
                    if outd > 0:
                        for b, ts in st.coP[a].items():
                            score[b] += co_p * w * decay(ts, t, half) / (outd + alpha)
            if hop2:
                # two hops: current investor a -> same-round co-investor x -> whoever x handed off to
                nb: dict[str, float] = defaultdict(float)
                for a, w in src.items():
                    for table, out in ((st.coL, st.coL_out), (st.coP, st.coP_out)):
                        outd = decay(out.get(a, ()), t, half)
                        if outd <= 0:
                            continue
                        for x, ts in table[a].items():
                            if x not in src:
                                nb[x] += w * decay(ts, t, half) / (outd + alpha)
                for x, wx in nb.items():
                    outd = decay_w(st.out.get(x, ()), t, half)
                    if outd <= 0:
                        continue
                    for b, tws in st.edges[x].items():
                        score[b] += hop2 * wx * decay_w(tws, t, half) / (outd + alpha)
            if ins_bonus and not ctx.outside_only:
                for a, w in src.items():
                    score[a] += ins_bonus * w
            if use_pair:
                pst = last[-1].get("stage")
                d = st.stage_pair_leads.get((pst, stage), {})
                tot = sum(decay(ts, t, pop_half) for ts in d.values()) or 1.0
                for b, ts in d.items():
                    score[b] += use_pair * decay(ts, t, pop_half) / tot
        # stage popularity prior (normalised to a distribution)
        d = st.stage_leads.get(stage, {})
        tot = sum(decay(ts, t, pop_half) for ts in d.values()) or 1.0
        for b, ts in d.items():
            score[b] += beta * decay(ts, t, pop_half) / tot
        if country_w and country:
            d = st.country_leads.get(country, {})
            tot = sum(decay(ts, t, pop_half) for ts in d.values()) or 1.0
            for b, ts in d.items():
                score[b] += country_w * decay(ts, t, pop_half) / tot
        for wgt, d in ((cs_w, st.cs_leads.get((country, stage), {})), (capp_w, st.country_inv.get(country, {}))):
            if not wgt or not d:
                continue
            vals = {b: decay(ts, t, pop_half) for b, ts in d.items()}
            tot = sum(vals.values()) or 1.0
            for b, v in vals.items():
                score[b] += wgt * v / tot
        if any_w:
            tot = 0.0
            vals = {}
            for b, ts in st.lead_count.items():
                v = decay(ts, t, pop_half)
                vals[b] = v
                tot += v
            for b, v in vals.items():
                score[b] += any_w * v / (tot or 1.0)
        if lead_rate:
            for b in list(score):
                score[b] *= (1 + lead_rate * min(1.0, decay(st.lead_count.get(b, ()), t, pop_half) / 5))
        ranked = sorted(score, key=score.get, reverse=True)
        if insider and not ctx.outside_only:
            if ins_mode == "lastlead":
                pre = []
                for o in reversed(cp):
                    pre += o.get("leads") or []
                ranked = pre[:1] + ranked
            elif ins_mode.startswith("k"):
                k = int(ins_mode[1:])
                pre = []
                for o in reversed(cp):
                    pre += o.get("leads") or []
                for o in reversed(cp):
                    pre += o.get("participants") or []
                dd = []
                for x in pre:
                    if x not in dd:
                        dd.append(x)
                ranked = dd[:k] + ranked
            elif ins_mode == "full":
                pre = []
                for o in reversed(cp):
                    pre += o.get("leads") or []
                for o in reversed(cp):
                    pre += o.get("participants") or []
                ranked = pre + ranked
            elif ins_mode == "lastleads_all":
                pre = []
                for o in reversed(cp):
                    pre += o.get("leads") or []
                ranked = pre + ranked
        return ranked[:100]

    rank.__name__ = key[:28]
    return rank


BEST = dict(co_l=0.3, country_w=0.1, cs_w=0.1, capp_w=0.05, pop_half=4.0, insider=False, ins_bonus=0.5)

if __name__ == "__main__":
    variants = {
        # pure handoff edges (A in round N -> lead of round N+1), no priors, no insider rule
        "handoff_only": dict(beta=0.0, use_trans=0.0, insider=False),
        # + stage transition edges + stage popularity prior
        "handoff+trans+stagepop": dict(insider=False),
        # best: + same-round co-lead edges, country / country x stage / country-appearance priors,
        #       insider bonus mixed into the same score (ALL only)
        "handoff_best": BEST,
        # priors only (handoff/co edges effectively off) for ablation
        "priors_only": dict(BEST, alpha=1e9, use_trans=0.0, co_l=0.0),
    }
    sel = sys.argv[1:] or list(variants)
    for name in sel:
        harness.evaluate(make_rank(**variants[name]), name)
    early = lambda r: r["year"] < 2025  # noqa: E731
    late = lambda r: r["year"] >= 2025  # noqa: E731
    for tag, sub in (("<2025", early), (">=2025", late)):
        harness.evaluate(make_rank(**BEST), f"best {tag}", subset=sub)
        harness.evaluate(harness.last_lead_again, f"last_lead_again {tag}", subset=sub)
        harness.evaluate(harness.stage_leads, f"stage_leads {tag}", subset=sub)
