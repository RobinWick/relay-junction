"""Timing / momentum candidate signals for Recount Signal (signal hunt, family 'timing').

Pure, point-in-time functions: every value is computed from rounds with t < as_of only (equity rounds, disputed and
programme rounds removed, same rules as signal_score.build_context). Nothing is imputed: a signal without enough data
is None.

    from hunt_timing import timing_signals
    vals = timing_signals(rounds, as_of=2022.0)   # {ckey: {signal_key: float | None}}

Signals (raw values; direction is chosen on validation cutoffs by the runner, never here):
  overdue            months since last round / median gap of that stage (gaps from dated raises before as_of)
  cadence_vs_cohort  last gap between raises, percentile within companies whose last raise has the same stage and year
  step_up_vs_peers   last sized raise / previous sized raise, percentile within companies with the same last stage
  recency_x_size     size-for-stage percentile x recency (1 at 0 months since last round, 0 at 36 months or more)
  syndicate_growth   log2((1 + investors on last raise) / (1 + investors on the raise before))
"""
from __future__ import annotations

import math
import statistics
from collections import defaultdict
from typing import Optional

from merge import _date_precision
from signal_score import MIN_PEERS, collapse, investors, is_equity, midrank_pct

KEYS = ["overdue", "cadence_vs_cohort", "step_up_vs_peers", "recency_x_size", "syndicate_growth"]
RECENCY_HORIZON_MONTHS = 36.0
MIN_GAPS = 5


def equity_before(rounds: list[dict], as_of: float) -> dict[str, list[dict]]:
    """{ckey: equity rounds dated before as_of, sorted by (t, id)}."""
    by: dict[str, list[dict]] = defaultdict(list)
    for r in sorted((r for r in rounds if r["t"] < as_of and is_equity(r)), key=lambda r: (r["t"], r["id"])):
        by[r["ckey"]].append(r)
    return dict(by)


def dated_raises(rs: list[dict]) -> list[list[dict]]:
    return collapse([r for r in rs if _date_precision(r) >= 2])


def stage_gap_medians(by: dict[str, list[dict]]) -> dict[str, float]:
    """Median months between consecutive dated raises, keyed by the stage of the earlier raise (>= MIN_GAPS gaps)."""
    gaps: dict[str, list[float]] = defaultdict(list)
    for rs in by.values():
        raises = dated_raises(rs)
        for a, b in zip(raises, raises[1:]):
            st = next((r["stage"] for r in a if r.get("stage")), None)
            if st:
                gaps[st].append((b[0]["t"] - a[0]["t"]) * 12)
    return {s: statistics.median(v) for s, v in gaps.items() if len(v) >= MIN_GAPS}


def overdue(rs: list[dict], as_of: float, gap_med: dict[str, float]) -> Optional[float]:
    if not rs or not rs[-1].get("stage"):
        return None
    med = gap_med.get(rs[-1]["stage"])
    if not med:
        return None
    return (as_of - rs[-1]["t"]) * 12 / med


def last_gap(rs: list[dict]) -> Optional[tuple[float, str, int]]:
    """(months between the last two dated raises, stage of last raise, year of last raise)."""
    raises = dated_raises(rs)
    if len(raises) < 2:
        return None
    st = next((r["stage"] for r in raises[-1] if r.get("stage")), None)
    if not st:
        return None
    return (raises[-1][0]["t"] - raises[-2][0]["t"]) * 12, st, raises[-1][0]["year"]


def step_ratio(rs: list[dict]) -> Optional[tuple[float, str]]:
    """(last sized raise / previous sized raise, stage of the last sized raise)."""
    sized = [max((r for r in g if r.get("amount_eur_m")), key=lambda r: r["amount_eur_m"])
             for g in collapse(rs) if any(r.get("amount_eur_m") for r in g)]
    if len(sized) < 2 or not sized[-1].get("stage"):
        return None
    return sized[-1]["amount_eur_m"] / sized[-2]["amount_eur_m"], sized[-1]["stage"]


def size_pools(by: dict[str, list[dict]], as_of: float) -> tuple[dict, dict]:
    """({(stage, year): amounts}, {stage: amounts in the 4 years before as_of}), same pools as signal_score."""
    sy: dict[tuple, list[float]] = defaultdict(list)
    recent: dict[str, list[float]] = defaultdict(list)
    for xs in by.values():
        for x in xs:
            if x.get("stage") and x.get("amount_eur_m"):
                sy[(x["stage"], x["year"])].append(x["amount_eur_m"])
                if x["t"] >= as_of - 4:
                    recent[x["stage"]].append(x["amount_eur_m"])
    return dict(sy), dict(recent)


def size_pct(rs: list[dict], pools: tuple[dict, dict]) -> Optional[float]:
    """Size for stage as in signal_score: last round with stage and amount, percentile within same stage +-1 year,
    falling back to same stage in the 4 years before as_of."""
    sized = [r for r in rs if r.get("stage") and r.get("amount_eur_m")]
    if not sized:
        return None
    r = sized[-1]
    sy, recent = pools
    pool = sorted(a for y in (r["year"] - 1, r["year"], r["year"] + 1) for a in sy.get((r["stage"], y), []))
    if len(pool) < MIN_PEERS:
        pool = sorted(recent.get(r["stage"], []))
    if len(pool) < MIN_PEERS:
        return None
    return midrank_pct(r["amount_eur_m"], pool)


def recency_x_size(rs: list[dict], size: Optional[float], as_of: float) -> Optional[float]:
    if size is None or not rs:
        return None
    months = (as_of - rs[-1]["t"]) * 12
    return size * max(0.0, 1 - months / RECENCY_HORIZON_MONTHS)


def syndicate_growth(rs: list[dict]) -> Optional[float]:
    raises = collapse(rs)
    if len(raises) < 2:
        return None
    prev = {k for r in raises[-2] for k in investors(r)}
    cur = {k for r in raises[-1] for k in investors(r)}
    if not prev or not cur:
        return None  # a raise that names nobody is missing data, not zero investors
    return math.log2((1 + len(cur)) / (1 + len(prev)))


def _pct(groups: dict, key, fallback, v: float) -> Optional[float]:
    pool = groups.get(key, [])
    if len(pool) < MIN_PEERS:
        pool = groups.get(fallback, [])
    return midrank_pct(v, pool) if len(pool) >= MIN_PEERS else None


def timing_signals(rounds: list[dict], as_of: float) -> dict[str, dict[str, Optional[float]]]:
    """All five timing signals for every company with an equity round before as_of."""
    by = equity_before(rounds, as_of)
    gap_med = stage_gap_medians(by)
    pools = size_pools(by, as_of)

    gaps = {ck: last_gap(rs) for ck, rs in by.items()}
    steps = {ck: step_ratio(rs) for ck, rs in by.items()}
    gap_pool: dict[tuple, list[float]] = defaultdict(list)
    step_pool: dict[tuple, list[float]] = defaultdict(list)
    for g in gaps.values():
        if g:
            gap_pool[(g[1], g[2])].append(g[0])
            gap_pool[(g[1],)].append(g[0])
    for s in steps.values():
        if s:
            step_pool[(s[1],)].append(math.log(s[0]))
            step_pool[("all",)].append(math.log(s[0]))
    for v in list(gap_pool.values()) + list(step_pool.values()):
        v.sort()

    out: dict[str, dict[str, Optional[float]]] = {}
    for ck, rs in by.items():
        g, s = gaps[ck], steps[ck]
        out[ck] = {
            "overdue": overdue(rs, as_of, gap_med),
            "cadence_vs_cohort": _pct(gap_pool, (g[1], g[2]), (g[1],), g[0]) if g else None,
            "step_up_vs_peers": _pct(step_pool, (s[1],), ("all",), math.log(s[0])) if s else None,
            "recency_x_size": recency_x_size(rs, size_pct(rs, pools), as_of),
            "syndicate_growth": syndicate_growth(rs),
        }
    return out
