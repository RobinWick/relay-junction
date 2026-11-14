"""Lead dynamics candidate signals (signal hunt, family 'lead'). Pure, point-in-time, stdlib only.

    from hunt_lead import lead_signals
    vals = lead_signals(rounds, as_of)   # {ckey: {signal_key: value or None}}

Only rounds with t < as_of that are equity (not not_led, not disputed) are read. Every fund history is taken from
rounds dated strictly before the company's latest round, so nothing after as_of (or after the round) leaks in.
Missing stays None: no lead named, no stage, no amount, or too little fund history.

Signals (value semantics; direction is chosen later on validation years, never here)
  lead_stretch        1 if a lead of the latest round led it at an amount above that lead's own p75 led size at that
                      stage (needs >= 3 prior sized led rounds at the stage), else 0.
  lead_stage_stretch  1 if a lead of the latest round has never led a round this late before (needs >= 2 prior
                      staged leads), else 0.
  new_outside_lead    1 if a lead of the latest round never invested in an earlier raise of the company, else 0
                      (needs an earlier raise >= 3 months before; first-round companies are None).
  lead_strength       log1p of the most rounds any latest-round lead led at the same stage in the 48 months before
                      the latest round (this round excluded).
  lead_upgrade        1 if the latest lead's median led size beats the previous led raise's lead median (each lead
                      needs >= 2 prior sized led rounds; best-known lead of each raise), else 0.
  insider_lead        1 if a lead of the latest round invested in an earlier raise of the company, else 0.
"""
from __future__ import annotations

import math
import statistics
from collections import defaultdict
from typing import Optional

from signal_score import COLLAPSE_YEARS, STAGE_IX, investors, is_equity, is_hub

KEYS = ["lead_stretch", "lead_stage_stretch", "new_outside_lead", "lead_strength", "lead_upgrade", "insider_lead"]
MIN_STRETCH_HISTORY = 3
MIN_STAGE_HISTORY = 2
MIN_UPGRADE_HISTORY = 2
STRENGTH_WINDOW = 4.0  # years


def _p75(xs: list[float]) -> float:
    s = sorted(xs)
    pos = 0.75 * (len(s) - 1)
    lo = math.floor(pos)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def _leads(r: dict) -> list[str]:
    return [k for k in dict.fromkeys(r.get("leads") or []) if not is_hub(k)]


def equity_before(rounds: list[dict], as_of: float) -> list[dict]:
    return sorted((r for r in rounds if r["t"] < as_of and is_equity(r)), key=lambda r: (r["t"], r["id"]))


def lead_history(eq: list[dict]) -> dict[str, list[dict]]:
    """{fund: [led rounds sorted by t]} from point-in-time equity rounds."""
    led: dict[str, list[dict]] = defaultdict(list)
    for r in eq:
        for k in _leads(r):
            led[k].append(r)
    return dict(led)


def _prior(led: dict[str, list[dict]], k: str, before: dict) -> list[dict]:
    """Rounds fund k led strictly before round `before` (other companies and this one, round itself excluded)."""
    return [x for x in led.get(k, []) if x["t"] < before["t"] and x["id"] != before["id"]]


def lead_stretch(led: dict, last: dict) -> Optional[float]:
    if not last.get("stage") or not last.get("amount_eur_m"):
        return None
    seen, hit = False, False
    for k in _leads(last):
        sizes = [x["amount_eur_m"] for x in _prior(led, k, last) if x.get("stage") == last["stage"] and x.get("amount_eur_m")]
        if len(sizes) >= MIN_STRETCH_HISTORY:
            seen = True
            hit = hit or last["amount_eur_m"] > _p75(sizes)
    return (1.0 if hit else 0.0) if seen else None


def lead_stage_stretch(led: dict, last: dict) -> Optional[float]:
    if last.get("stage") not in STAGE_IX:
        return None
    seen, hit = False, False
    for k in _leads(last):
        ix = [STAGE_IX[x["stage"]] for x in _prior(led, k, last) if x.get("stage") in STAGE_IX]
        if len(ix) >= MIN_STAGE_HISTORY:
            seen = True
            hit = hit or STAGE_IX[last["stage"]] > max(ix)
    return (1.0 if hit else 0.0) if seen else None


def _insider_split(rs: list[dict]) -> Optional[tuple[int, int]]:
    """(# latest leads that were earlier investors, # that were not); None without lead or earlier raise."""
    last = rs[-1]
    leads = _leads(last)
    earlier = [r for r in rs if r["t"] <= last["t"] - COLLAPSE_YEARS]
    if not leads or not earlier:
        return None
    before = {k for r in earlier for k in investors(r)}
    ins = sum(1 for k in leads if k in before)
    return ins, len(leads) - ins


def new_outside_lead(rs: list[dict]) -> Optional[float]:
    s = _insider_split(rs)
    return None if s is None else (1.0 if s[1] > 0 else 0.0)


def insider_lead(rs: list[dict]) -> Optional[float]:
    s = _insider_split(rs)
    return None if s is None else (1.0 if s[0] > 0 else 0.0)


def lead_strength(led: dict, last: dict) -> Optional[float]:
    leads = _leads(last)
    if not leads or not last.get("stage"):
        return None
    best = max(sum(1 for x in _prior(led, k, last) if x.get("stage") == last["stage"]
                   and x["t"] >= last["t"] - STRENGTH_WINDOW) for k in leads)
    return math.log1p(best)


def _lead_median(led: dict, r: dict, at: dict, own: str) -> Optional[float]:
    """Highest median led size among r's leads, from rounds led before `at`, excluding company `own`."""
    meds = []
    for k in _leads(r):
        sizes = [x["amount_eur_m"] for x in led.get(k, []) if x["t"] < at["t"] and x["ckey"] != own and x.get("amount_eur_m")]
        if len(sizes) >= MIN_UPGRADE_HISTORY:
            meds.append(statistics.median(sizes))
    return max(meds) if meds else None


def lead_upgrade(led: dict, rs: list[dict]) -> Optional[float]:
    last = rs[-1]
    prev = next((r for r in reversed(rs) if r["t"] <= last["t"] - COLLAPSE_YEARS and _leads(r)), None)
    if prev is None or not _leads(last):
        return None
    a = _lead_median(led, last, last, last["ckey"])
    b = _lead_median(led, prev, last, last["ckey"])
    if a is None or b is None:
        return None
    return 1.0 if a > b else 0.0


def company_signals(led: dict, rs: list[dict]) -> dict[str, Optional[float]]:
    if not rs:
        return {k: None for k in KEYS}
    last = rs[-1]
    return {"lead_stretch": lead_stretch(led, last), "lead_stage_stretch": lead_stage_stretch(led, last),
            "new_outside_lead": new_outside_lead(rs), "lead_strength": lead_strength(led, last),
            "lead_upgrade": lead_upgrade(led, rs), "insider_lead": insider_lead(rs)}


def lead_signals(rounds: list[dict], as_of: float, ckeys: Optional[set[str]] = None) -> dict[str, dict]:
    """{ckey: {signal: value}} using only equity rounds dated before as_of."""
    eq = equity_before(rounds, as_of)
    led = lead_history(eq)
    by_c: dict[str, list[dict]] = defaultdict(list)
    for r in eq:
        by_c[r["ckey"]].append(r)
    return {ck: company_signals(led, rs) for ck, rs in by_c.items() if ckeys is None or ck in ckeys}
