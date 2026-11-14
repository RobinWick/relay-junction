"""Lead Pace Through the Cycle: a receipt, not a score (research/patterns/DECISION.md, feature 2).

For one fund and the founder's stage band, a yearly history 2019 to 2026 of the rounds it led and the rounds it
joined where another lead is named, with "N rounds, lead unknown" beside every year. One plain summary line is
written only from those counts and only when there are enough of them; otherwise it says nothing.

Rules (deterministic, no model, no probability shown):
  Counted nowhere : disputed rounds (dispute.py) and not-led rounds (accelerator, PIPE, hand-checked non-equity).
  Deduped first   : same company name (legal and generic words dropped), same stage, same year, and amounts within
                    5% or one unknown are one round (stopped-leading-check.py rule). Every merged id stays linked.
  Follow-on       : a round the fund joined without leading in a company it was already in. Shown apart, not in the
                    lead-known denominator (same rule as engine.fund_profile).
  Pause line      : a closed run of years with 0 leads at the band (the fund led at the band again later), holding
                    4+ lead-known rounds, after 2+ leads in 4+ lead-known rounds earlier in the window, and long
                    enough that the fund's own earlier lead share would give 0 leads in that many rounds at most 1
                    time in 5. One line, at most one run. A run still open today is never a line: that would be an
                    alert, and the months since the last lead at the founder's stage already say it as a fact.
  Overall line    : otherwise, 5+ lead-known rounds at the band since 2019. Fewer: no line.
Words never used: stopped, started, likely, score, rate. Every number links to /api/record/{id}.
"""
from __future__ import annotations

import re

from engine import STAGE_LABEL, STAGES, Snapshot, month_label, round_brief, stage_band
from merge import _date_precision, _survivor_rank

YEARS = range(2019, 2027)
FOLLOW_ON_GAP = 0.17  # same rule as engine.fund_profile: 2 months after the fund's first round in the company
AMOUNT_TOLERANCE = 0.05
MIN_PAUSE_KNOWN = 4
MIN_PRIOR_KNOWN = 4
MIN_PRIOR_LED = 2
CHANCE_GATE = 0.2
MIN_OVERALL_KNOWN = 5

# Recomputed by research/patterns/pace-context.py (exits 1 if any figure drifts); test_receipt_pace.py checks
# these against its pace-context.json. Population facts, shown with n, never as a per-fund number.
POPULATION_CONTEXT = [
    {"id": "lead_comes_back",
     "text": "Across companies with a full round history in Cala, the lead was back in the next round in 74% of "
             "cases (215 of 289) vs 55% for funds that only joined (324 of 589).",
     "numbers": {"lead_back": [215, 289], "participant_back": [324, 589]},
     "source": "research/patterns/pace-context.py"},
    {"id": "long_gap_new_lead",
     "text": "After more than 30 months between rounds, the old lead led the next round in 11% of cases (6 of 55) "
             "vs 22% (53 of 245) with a shorter gap, and was still in the round in 76% (42 of 55). Plan for a "
             "new lead.",
     "numbers": {"gap30_led_again": [6, 55], "no_gap30_led_again": [53, 245], "gap30_came_back": [42, 55],
                 "fisher_p": 0.09},
     "source": "research/patterns/pace-context.py"},
]

_DEDUP_CACHE: dict[int, tuple[Snapshot, dict]] = {}


def dedup_name(company: str) -> str:
    """Company name without legal and generic words: 'IQM' and 'IQM Quantum Computers', 'Voi' and 'VOI Technology'."""
    c = company.lower()
    c = re.sub(r"\b(technology|technologies|ab|oy|gmbh|ltd|inc|sas|bv|as|quantum computers)\b", "", c)
    return re.sub(r"[^a-z0-9]", "", c)


def _same_amount(a: float | None, b: float | None) -> bool:
    return not a or not b or abs(a - b) <= AMOUNT_TOLERANCE * max(a, b)


def _merge(members: list[dict]) -> dict:
    keep = dict(max(members, key=_survivor_rank))
    leads = set().union(*(set(m["leads"]) for m in members))
    keep["leads"] = sorted(leads)
    keep["participants"] = sorted(set().union(*(set(m["participants"]) for m in members)) - leads)
    keep["same_round_ids"] = sorted(m["id"] for m in members if m["id"] != keep["id"])
    return keep


def dedup_rounds(rounds: list[dict]) -> tuple[list[dict], int]:
    """Countable rounds (not disputed, not not-led) with duplicates folded. Returns (rounds, rounds merged away)."""
    groups: dict[tuple, list[list[dict]]] = {}
    for r in sorted(rounds, key=lambda r: r["id"]):
        if r.get("disputed") or r.get("not_led"):
            continue
        bucket = groups.setdefault((dedup_name(r["company"]), r["stage"], r["year"]), [])
        home = next((g for g in bucket if all(_same_amount(r.get("amount_eur_m"), m.get("amount_eur_m")) for m in g)), None)
        if home is None:
            bucket.append([r])
        else:
            home.append(r)
    out, merged = [], 0
    for bucket in groups.values():
        for g in bucket:
            out.append(_merge(g))
            merged += len(g) - 1
    return sorted(out, key=lambda r: r["id"]), merged


def _deduped(snap: Snapshot) -> dict:
    """Deduped rounds per investor, built once per snapshot."""
    hit = _DEDUP_CACHE.get(id(snap))
    if hit and hit[0] is snap:
        return hit[1]
    rounds, merged = dedup_rounds(snap.rounds)
    by_inv: dict[str, list[dict]] = {}
    for r in rounds:
        for k in set(r["leads"]) | set(r["participants"]):
            by_inv.setdefault(k, []).append(r)
    in_years = [r for r in rounds if r["year"] in YEARS]
    missing = sum(1 for r in in_years if not r["leads"])
    data = {"by_investor": by_inv, "merged": merged,
            "lead_missing_share": round(missing / len(in_years), 2) if in_years else None}
    _DEDUP_CACHE.clear()
    _DEDUP_CACHE[id(snap)] = (snap, data)
    return data


def band_label(stage: str) -> str:
    band = [s for s in STAGES if s in stage_band(stage)]
    if not band:
        return STAGE_LABEL.get(stage, stage)
    first, last = STAGE_LABEL[band[0]], STAGE_LABEL[band[-1]]
    return first if first == last else f"{first} to {last}"


def _span(a: int, b: int) -> str:
    return f"in {a}" if a == b else f"{a} to {b}"


def _rounds_word(n: int) -> str:
    return "round" if n == 1 else "rounds"


def classify_years(key: str, rounds: list[dict], stage: str) -> tuple[dict[int, dict], dict]:
    """Per year: ids of rounds led, joined (lead known), lead unknown and follow-on, at the founder's stage band."""
    band = stage_band(stage)
    first_t: dict[str, float] = {}
    for r in rounds:
        first_t[r["ckey"]] = min(first_t.get(r["ckey"], r["t"]), r["t"])
    years = {y: {"led": [], "joined": [], "lead_unknown": [], "follow_on": []} for y in YEARS}
    outside = {"stage_not_stated": [], "other_stage": []}
    for r in sorted(rounds, key=lambda r: r["t"]):
        if r["year"] not in YEARS:
            continue
        if not r["stage"]:
            outside["stage_not_stated"].append(r["id"])
            continue
        if r["stage"] not in band:
            outside["other_stage"].append(r["id"])
            continue
        cell = years[r["year"]]
        is_lead = key in r["leads"]
        if is_lead:
            cell["led"].append(r["id"])
        elif r["t"] > first_t[r["ckey"]] + FOLLOW_ON_GAP:
            cell["follow_on"].append(r["id"])
        elif not r["leads"]:
            cell["lead_unknown"].append(r["id"])
        else:
            cell["joined"].append(r["id"])
    return years, outside


def pause_run(years: dict[int, dict]) -> dict | None:
    """The one run of years with 0 leads that the counts can carry, or None (see module rules)."""
    ys = list(YEARS)
    led = {y: len(years[y]["led"]) for y in ys}
    known = {y: led[y] + len(years[y]["joined"]) for y in ys}
    best = None
    i = 0
    while i < len(ys):
        if led[ys[i]]:
            i += 1
            continue
        j = i
        while j + 1 < len(ys) and not led[ys[j + 1]]:
            j += 1
        run = [y for y in ys[i:j + 1]]
        while run and not known[run[0]]:
            run.pop(0)
        while run and not known[run[-1]]:
            run.pop()
        i = j + 1
        if not run:
            continue
        a, b = run[0], run[-1]
        n0 = sum(known[y] for y in run)
        prior_led = sum(led[y] for y in ys if y < a)
        prior_known = sum(known[y] for y in ys if y < a)
        if n0 < MIN_PAUSE_KNOWN or prior_led < MIN_PRIOR_LED or prior_known < MIN_PRIOR_KNOWN:
            continue
        if (1 - prior_led / prior_known) ** n0 > CHANCE_GATE:
            continue
        resumed = next((y for y in ys if y > b and led[y]), None)
        if resumed is None:
            continue
        cand = {"from": a, "to": b, "led": 0, "lead_known": n0, "resumed": resumed,
                "prior": {"led": prior_led, "lead_known": prior_known},
                "round_ids": [rid for y in run for rid in years[y]["joined"]],
                "resumed_round_ids": years[resumed]["led"]}
        if best is None or (n0, b) > (best["lead_known"], best["to"]):
            best = cand
    return best


def summary_line(years: dict[int, dict], stage: str) -> tuple[str | None, dict | None, str | None]:
    """(line, basis, withheld_reason). The line is built only from counts that clear the minimum n rules."""
    where = band_label(stage)
    run = pause_run(years)
    if run:
        a, b, n0 = run["from"], run["to"], run["lead_known"]
        line = (f"Paused leading at {where} {_span(a, b)} (0 of {n0} lead-known {_rounds_word(n0)}), "
                f"resumed {run['resumed']}.")
        return line, {"kind": "pause", **run}, None
    led = sum(len(c["led"]) for c in years.values())
    known = led + sum(len(c["joined"]) for c in years.values())
    unknown = sum(len(c["lead_unknown"]) for c in years.values())
    if known < MIN_OVERALL_KNOWN:
        return None, None, (f"Fewer than {MIN_OVERALL_KNOWN} lead-known rounds at {where} since {YEARS[0]} "
                            f"({known}), so no summary.")
    # every count covers the whole window, so the line names the same years as the strip's header
    a, b = YEARS[0], YEARS[-1]
    line = f"Led {led} of {known} lead-known rounds at {where}, {_span(a, b)}"
    line += f" ({unknown} more {_rounds_word(unknown)}, lead unknown)." if unknown else "."
    ids = [rid for c in years.values() for rid in c["led"] + c["joined"]]
    return line, {"kind": "overall", "from": a, "to": b, "led": led, "lead_known": known,
                  "lead_unknown": unknown, "round_ids": ids}, None


def last_lead_at_stage(snap: Snapshot, key: str, rounds: list[dict], stage: str) -> dict | None:
    """Most recent round the fund led at exactly the founder's stage, any year, with months since."""
    led = [r for r in rounds if key in r["leads"] and r["stage"] == stage]
    if not led:
        return None
    r = max(led, key=lambda r: r["t"])
    return {"round_id": r["id"], "record": f"/api/record/{r['id']}", "date": month_label(r),
            "months_ago": max(0, round((snap.now_t - r["t"]) * 12)), "date_approx": _date_precision(r) < 2,
            "stage": STAGE_LABEL.get(stage, stage)}


def _brief(snap: Snapshot, r: dict) -> dict:
    return {**round_brief(snap, r), "record": f"/api/record/{r['id']}",
            "same_round_ids": r.get("same_round_ids", []),
            "same_round_records": [f"/api/record/{i}" for i in r.get("same_round_ids", [])]}


def lead_pace(snap: Snapshot, key: str, stage: str, include_context: bool = True) -> dict:
    """The full receipt for one fund at the founder's stage. Pure over the snapshot; makes no Cala call."""
    if stage not in STAGES:
        raise ValueError(f"unknown stage {stage!r}")
    data = _deduped(snap)
    rounds = data["by_investor"].get(key, [])
    years, outside = classify_years(key, rounds, stage)
    line, basis, withheld = summary_line(years, stage)
    in_band = [rid for c in years.values() for ids in c.values() for rid in ids]
    shown = set(in_band)
    by_id = {r["id"]: r for r in rounds}
    lead_missing = data["lead_missing_share"]
    caveat = (f"Based on {len(in_band)} announced {_rounds_word(len(in_band))} in Cala at {band_label(stage)} "
              f"from {YEARS[0]} to {YEARS[-1]}. Leads are missing for "
              f"{round(100 * lead_missing) if lead_missing is not None else 'an unknown share'}% of rounds in "
              f"these years. This is not a statement about the fund's current capital.")
    last = last_lead_at_stage(snap, key, rounds, stage)
    if last:
        shown.add(last["round_id"])
    return {
        "fund": {"key": key, "name": snap.name(key), "queried": key in snap.fund_keys, "public": snap.is_hub(key)},
        "stage": stage, "stage_label": STAGE_LABEL[stage], "band": [s for s in STAGES if s in stage_band(stage)],
        "band_label": band_label(stage),
        "years": [{"year": y, **{k: list(v) for k, v in c.items()},
                   "counts": {"led": len(c["led"]), "joined": len(c["joined"]),
                              "lead_known": len(c["led"]) + len(c["joined"]),
                              "lead_unknown": len(c["lead_unknown"]), "follow_on": len(c["follow_on"])}}
                  for y, c in years.items()],
        "totals": {"led": sum(len(c["led"]) for c in years.values()),
                   "joined": sum(len(c["joined"]) for c in years.values()),
                   "lead_unknown": sum(len(c["lead_unknown"]) for c in years.values()),
                   "follow_on": sum(len(c["follow_on"]) for c in years.values()),
                   "stage_not_stated": len(outside["stage_not_stated"]),
                   "other_stage": len(outside["other_stage"])},
        "summary": line, "summary_basis": basis, "summary_withheld": withheld,
        "last_lead_at_stage": last,
        "rounds": {str(rid): _brief(snap, by_id[rid]) for rid in sorted(shown)},
        "stage_not_stated_ids": outside["stage_not_stated"],
        "caveat": caveat,
        "dedup": {"merged_in_snapshot": data["merged"]},
        "context": POPULATION_CONTEXT if include_context else [],
    }
