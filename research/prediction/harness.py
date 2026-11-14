"""Honest backtest: can past Cala round data predict who leads a company's next round?

Test set (fixed, shared by every method):
- rounds found company-first (so the round was NOT discovered because we asked about one of its investors),
- with a named lead, year >= 2021, and at least one earlier round of the same company in the data.
Information rule: a method may only use rounds dated strictly before the test round (t < test_t - EPS).
Candidates: every investor seen in any earlier round (any role). Insiders (current investors) are allowed.

Two scores per method:
- ALL:      hit@k if any true lead is in the top k.
- OUTSIDE:  only test rounds with at least one lead who is NOT a current investor; current investors are removed
            from the ranking and a hit means an outside lead is in the top k. This is the "new fund" question.

A method is a function  rank(ctx) -> list[str] of investor keys, best first, where ctx is a Context.
Run: python3 harness.py            (runs the baselines)
     from harness import evaluate; evaluate(my_rank, "name")
"""
from __future__ import annotations

import bisect
import json
import math
import random
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

SNAP = Path(__file__).resolve().parents[2] / "cala" / "data" / "snapshot.json"
EPS = 0.01  # about 4 days: same-day duplicates of the test round are not "the past"
KS = (1, 5, 10, 20)


def _load():
    s = json.loads(SNAP.read_text())
    rounds = sorted(s["rounds"], key=lambda r: r["t"])
    return s, rounds


SNAPSHOT, ROUNDS = _load()
TIMES = [r["t"] for r in ROUNDS]
FUND_KEYS = set(SNAPSHOT["fund_keys"])
BY_COMPANY: dict[str, list[dict]] = defaultdict(list)
for _r in ROUNDS:
    BY_COMPANY[_r["ckey"]].append(_r)


def investors(r: dict) -> set[str]:
    return set(r.get("leads") or []) | set(r.get("participants") or [])


@dataclass
class Context:
    test: dict                     # the round to predict (do NOT read its leads/participants)
    past: list[dict]               # all rounds strictly before the test round, oldest first
    company_past: list[dict]       # this company's earlier rounds, oldest first
    current: set[str]              # investors in the company's earlier rounds
    outside_only: bool             # True: current investors will be removed from your ranking anyway
    extra: dict = field(default_factory=dict)

    @property
    def target(self) -> dict:
        """What the method may know about the test round: company, country, date, stage, amount."""
        r = self.test
        return {k: r.get(k) for k in ("company", "ckey", "country", "t", "year", "month", "stage", "amount_eur_m")}


def test_set() -> list[dict]:
    out = []
    for r in ROUNDS:
        if not r.get("leads") or r["year"] < 2021:
            continue
        if not any(x.get("path") == "company_first" for x in r.get("sources") or []):
            continue
        if any(o["t"] < r["t"] - EPS for o in BY_COMPANY[r["ckey"]]):
            out.append(r)
    return out


TEST = test_set()


def context(r: dict, outside_only: bool) -> Context:
    cut = bisect.bisect_left(TIMES, r["t"] - EPS)
    past = ROUNDS[:cut]
    cp = [o for o in BY_COMPANY[r["ckey"]] if o["t"] < r["t"] - EPS]
    cur = set().union(*(investors(o) for o in cp)) if cp else set()
    return Context(r, past, cp, cur, outside_only)


def wilson(h: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = h / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - m) / d, (c + m) / d)


def evaluate(rank, name: str, verbose: bool = True, subset=None) -> dict:
    """Runs both settings. subset: optional predicate on the test round (e.g. stage == 'seed')."""
    res = {"method": name}
    for setting in ("ALL", "OUTSIDE"):
        outside = setting == "OUTSIDE"
        hits = {k: 0 for k in KS}
        n = 0
        pool_sizes = []
        ceiling = 0
        for r in TEST:
            if subset and not subset(r):
                continue
            ctx = context(r, outside)
            truth = set(r["leads"])
            if outside:
                truth -= ctx.current
                if not truth:
                    continue
            seen = set().union(*(investors(o) for o in ctx.past)) if ctx.past else set()
            pool = seen - ctx.current if outside else seen
            pool_sizes.append(len(pool))
            ceiling += bool(truth & pool)
            ranked = [x for x in rank(ctx) if not (outside and x in ctx.current)]
            dedup, s = [], set()
            for x in ranked:
                if x not in s:
                    s.add(x)
                    dedup.append(x)
            n += 1
            for k in KS:
                hits[k] += bool(truth & set(dedup[:k]))
        mean_pool = sum(pool_sizes) / max(1, len(pool_sizes))
        out = {"n": n, "ceiling": round(ceiling / max(1, n), 3), "mean_pool": round(mean_pool)}
        for k in KS:
            lo, hi = wilson(hits[k], n)
            out[f"hit@{k}"] = round(hits[k] / max(1, n), 3)
            out[f"ci@{k}"] = (round(lo, 3), round(hi, 3))
        out["random@5"] = round(5 / mean_pool, 4) if mean_pool else None
        res[setting] = out
        if verbose:
            print(f"{name:28s} {setting:7s} n={n:4d} " + " ".join(f"@{k}={out[f'hit@{k}']:.3f}" for k in KS)
                  + f"  CI@5={out['ci@5']}  ceiling={out['ceiling']}  random@5={out['random@5']}", flush=True)
    return res


# ---------------- baselines ----------------

def popular_leads(ctx: Context) -> list[str]:
    """Most frequent lead in all past rounds."""
    c = defaultdict(float)
    for o in ctx.past:
        for l in o.get("leads") or []:
            c[l] += 1
    return sorted(c, key=c.get, reverse=True)[:50]


def stage_leads(ctx: Context) -> list[str]:
    """Most frequent lead at the target stage in the last 4 years, then any stage."""
    st, t = ctx.test.get("stage"), ctx.test["t"]
    c = defaultdict(float)
    for o in ctx.past:
        if t - o["t"] > 4:
            continue
        for l in o.get("leads") or []:
            c[l] += 3 if o.get("stage") == st else 0.2
    return sorted(c, key=c.get, reverse=True)[:50]


def last_lead_again(ctx: Context) -> list[str]:
    """Insider rule: the previous round's lead(s), then other current investors, then stage popularity."""
    out = []
    for o in reversed(ctx.company_past):
        out += o.get("leads") or []
    for o in reversed(ctx.company_past):
        out += o.get("participants") or []
    return out + stage_leads(ctx)


def random_rank(ctx: Context) -> list[str]:
    seen = sorted(set().union(*(investors(o) for o in ctx.past))) if ctx.past else []
    rnd = random.Random(ctx.test["id"])
    rnd.shuffle(seen)
    return seen[:50]


if __name__ == "__main__":
    print(f"test rounds: {len(TEST)}; snapshot rounds {len(ROUNDS)}; funds queried {len(FUND_KEYS)}", flush=True)
    for fn in (random_rank, popular_leads, stage_leads, last_lead_again):
        evaluate(fn, fn.__name__)
    sys.exit(0)
