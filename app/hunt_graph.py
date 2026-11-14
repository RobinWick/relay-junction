"""Graph-family candidate signals for Recount Signal (signal hunt, family 'graph').

Every function is pure and point-in-time: it takes the full round list plus as_of (decimal year) and reads only
equity rounds with t < as_of. Nothing is imputed: a signal that cannot be computed is None.

    from hunt_graph import compute_all
    vals = compute_all(rounds, as_of=2022.0)   # {ckey: {"syndicate_pagerank": float|None, ...}}

Signals (higher = hypothesised better)
  syndicate_pagerank   mean PageRank (x node count) of the latest round's investors on the co-investment graph
  co_investor_quality  share of latest-round investors (with >= 3 observable early bets, own company excluded) whose
                       early bets raised again within 24 months more often than the pooled base rate
  smart_money_early    1 if a top-decile graduation fund (early bet -> Series B+ within 36 months, own company
                       excluded) was on a pre-seed/seed round dated on or before the company's largest round, else 0
  contrarian           1 if strong backer (top-quartile 24m graduation) AND latest syndicate <= 3 AND the latest
                       round has no outside lead (no lead named, or every lead was already a backer), else 0
  syndicate_novelty    share of latest-round investor pairs that never co-invested in any round dated before it
"""
from __future__ import annotations

from collections import defaultdict
from itertools import combinations
from typing import Optional

from signal_score import COLLAPSE_YEARS, EARLY, LATE, investors, is_equity

KEYS = ["syndicate_pagerank", "co_investor_quality", "smart_money_early", "contrarian", "syndicate_novelty"]
MIN_BETS = 3          # observable early bets an investor needs before its track record counts
MIN_BETS_SMART = 3    # observable early bets a fund needs to be ranked for smart_money_early (5 left only 7 funds)
SMALL_SYNDICATE = 3
PRIOR_K = 5           # shrinkage strength toward the pooled rate
DAMPING = 0.85


# ---------------------------------------------------------------- point-in-time slice
def equity_before(rounds: list[dict], as_of: float) -> list[dict]:
    return sorted((r for r in rounds if r["t"] < as_of and is_equity(r)), key=lambda r: (r["t"], r["id"]))


def by_company(eq: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for r in eq:
        out[r["ckey"]].append(r)
    return out


# ---------------------------------------------------------------- 1 PageRank on the co-investment graph
def pagerank(eq: list[dict], iters: int = 60) -> dict[str, float]:
    """Weighted undirected co-investment graph: each round adds 1/(k-1) between each pair of its k investors."""
    w: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    nodes: set[str] = set()
    for r in eq:
        inv = investors(r)
        nodes.update(inv)
        if len(inv) < 2:
            continue
        e = 1.0 / (len(inv) - 1)
        for a, b in combinations(inv, 2):
            w[a][b] += e
            w[b][a] += e
    n = len(nodes)
    if not n:
        return {}
    strength = {a: sum(nb.values()) for a, nb in w.items()}
    pr = {a: 1.0 / n for a in nodes}
    for _ in range(iters):
        dangling = sum(pr[a] for a in nodes if not strength.get(a))
        nxt = {a: (1 - DAMPING) / n + DAMPING * dangling / n for a in nodes}
        for a, nb in w.items():
            share = DAMPING * pr[a] / strength[a]
            for b, x in nb.items():
                nxt[b] += share * x
        pr = nxt
    return {a: v * n for a, v in pr.items()}  # x n so 1.0 = average node, comparable across as_of


# ---------------------------------------------------------------- investor track records
def early_track(cos: dict[str, list[dict]], as_of: float, horizon: float, late_only: bool) -> dict[str, dict[str, int]]:
    """{investor: {company: hit}} over first early entries whose horizon closed before as_of.
    hit (24m, late_only False): any later round of that company in [entry + 3 months, entry + horizon].
    hit (36m, late_only True): a Series B or later round in (entry, entry + horizon]."""
    out: dict[str, dict[str, int]] = defaultdict(dict)
    for ck, rs in cos.items():
        first: dict[str, float] = {}
        for r in rs:
            if r.get("stage") in EARLY:
                for k in investors(r):
                    first.setdefault(k, r["t"])
        for k, te in first.items():
            if te + horizon > as_of:
                continue
            if late_only:
                hit = any(te < x["t"] <= te + horizon and x.get("stage") in LATE for x in rs)
            else:
                hit = any(te + COLLAPSE_YEARS <= x["t"] <= te + horizon for x in rs)
            out[k][ck] = int(hit)
    return out


def pooled_rate(track: dict[str, dict[str, int]]) -> float:
    n = sum(len(v) for v in track.values())
    h = sum(sum(v.values()) for v in track.values())
    return h / n if n else 0.5


def rate_excluding(track: dict[str, dict[str, int]], inv: str, ck: str) -> Optional[tuple[int, int]]:
    """(bets, hits) of an investor with the company being scored removed."""
    t = track.get(inv)
    if not t:
        return None
    n = len(t) - (1 if ck in t else 0)
    h = sum(t.values()) - t.get(ck, 0)
    return n, h


def shrunk(n: int, h: int, p0: float) -> float:
    return (h + PRIOR_K * p0) / (n + PRIOR_K)


def quantile(sorted_vals: list[float], q: float) -> Optional[float]:
    if not sorted_vals:
        return None
    return sorted_vals[min(len(sorted_vals) - 1, int(q * len(sorted_vals)))]


# ---------------------------------------------------------------- per-company signals
def latest(rs: list[dict]) -> Optional[dict]:
    return rs[-1] if rs else None


def sig_pagerank(rs: list[dict], pr: dict[str, float]) -> Optional[float]:
    last = latest(rs)
    inv = investors(last) if last else []
    return sum(pr.get(k, 0.0) for k in inv) / len(inv) if inv else None


def sig_co_investor_quality(rs: list[dict], ck: str, track24: dict, p0: float) -> tuple[Optional[float], int]:
    last = latest(rs)
    rated = good = 0
    for k in (investors(last) if last else []):
        nh = rate_excluding(track24, k, ck)
        if nh and nh[0] >= MIN_BETS:
            rated += 1
            good += int(nh[1] / nh[0] > p0)
    return (good / rated if rated else None), rated


def sig_smart_money_early(rs: list[dict], ck: str, track36: dict, p0: float, cut: Optional[float]) -> Optional[float]:
    seedish = [r for r in rs if r.get("stage") in ("pre-seed", "seed") and investors(r)]
    if not seedish or cut is None:
        return None
    sized = [r for r in rs if r.get("amount_eur_m")]
    big = max(sized, key=lambda r: (r["amount_eur_m"], r["t"])) if sized else rs[-1]
    for r in seedish:
        if r["t"] > big["t"]:
            continue
        for k in investors(r):
            nh = rate_excluding(track36, k, ck)
            if nh and nh[0] >= MIN_BETS_SMART and shrunk(nh[0], nh[1], p0) >= cut:
                return 1.0
    return 0.0


def sig_contrarian(rs: list[dict], ck: str, track24: dict, p0: float, strong_cut: Optional[float]) -> Optional[float]:
    last = latest(rs)
    if not last or not investors(last) or strong_cut is None:
        return None
    backers = {k for r in rs for k in investors(r)}
    rates = [shrunk(*nh, p0) for k in backers if (nh := rate_excluding(track24, k, ck)) and nh[0] >= MIN_BETS]
    if not rates:
        return None
    strong = max(rates) >= strong_cut
    small = len(investors(last)) <= SMALL_SYNDICATE
    before = {k for r in rs[:-1] for k in investors(r)}
    outside_lead = any(k not in before for k in (last.get("leads") or []))
    return 1.0 if strong and small and not outside_lead else 0.0


def pair_first_seen(eq: list[dict]) -> dict[frozenset, float]:
    """{investor pair: earliest round date where both invested}."""
    first: dict[frozenset, float] = {}
    for r in eq:
        for p in combinations(investors(r), 2):
            fp = frozenset(p)
            if fp not in first or r["t"] < first[fp]:
                first[fp] = r["t"]
    return first


def sig_syndicate_novelty(rs: list[dict], first_seen: dict[frozenset, float]) -> Optional[float]:
    last = latest(rs)
    inv = investors(last) if last else []
    if len(inv) < 2:
        return None
    pairs = {frozenset(p) for p in combinations(inv, 2)}
    return sum(1 for p in pairs if first_seen.get(p, last["t"]) >= last["t"]) / len(pairs)


# ---------------------------------------------------------------- all companies at one as_of
def compute_all(rounds: list[dict], as_of: float) -> dict[str, dict]:
    eq = equity_before(rounds, as_of)
    cos = by_company(eq)
    pr = pagerank(eq)
    first_seen = pair_first_seen(eq)
    track24 = early_track(cos, as_of, 2.0, late_only=False)
    track36 = early_track(cos, as_of, 3.0, late_only=True)
    p24, p36 = pooled_rate(track24), pooled_rate(track36)
    r24 = sorted(shrunk(len(v), sum(v.values()), p24) for v in track24.values() if len(v) >= MIN_BETS)
    r36 = sorted(shrunk(len(v), sum(v.values()), p36) for v in track36.values() if len(v) >= MIN_BETS_SMART)
    strong_cut, smart_cut = quantile(r24, 0.75), quantile(r36, 0.90)
    out = {}
    for ck, rs in cos.items():
        q, rated = sig_co_investor_quality(rs, ck, track24, p24)
        out[ck] = {"syndicate_pagerank": sig_pagerank(rs, pr),
                   "co_investor_quality": q, "co_investor_quality_rated": rated,
                   "smart_money_early": sig_smart_money_early(rs, ck, track36, p36, smart_cut),
                   "contrarian": sig_contrarian(rs, ck, track24, p24, strong_cut),
                   "syndicate_novelty": sig_syndicate_novelty(rs, first_seen)}
    out["__meta__"] = {"as_of": as_of, "nodes": len(pr), "p24": round(p24, 3), "p36": round(p36, 3),
                       "investors_rated_24m": len(r24), "funds_ranked_36m": len(r36),
                       "strong_cut_24m": strong_cut, "smart_cut_36m": smart_cut}
    return out
