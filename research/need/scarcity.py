"""Lead scarcity: how rare are investors who actually lead? Counted only from the cached Cala snapshot.

Run:  python3 research/need/scarcity.py      (from /Users/robinwickholm/junction-2026)
Writes research/need/scarcity.json next to this file and prints the headline numbers.

Read-only use of the app: imports engine.py and pipeline/validate.py, edits nothing. No API calls.

Definitions (also in SCARCITY.md):
  round set     : rounds with stage pre-seed or seed, year 2023..2026, not disputed, not not_led (same exclusions
                  as the engine). Country = first place named in the round's country field (text before "/" or "(").
  Nordic        : Finland, Sweden, Denmark, Norway, Iceland, Estonia.
  Europe        : the European country list below (EU, EEA, UK, Switzerland, Balkans, Ukraine, Baltics).
  rounds joined : rounds in the set where the investor is a named lead or participant.
  active list   : top 50 investors by rounds joined (ties broken by name), public bodies and programmes
                  (engine.HUBS) left out, because they do not lead equity rounds by design.
  lead share    : rounds led / rounds joined where a lead is named (the engine's ratio, without its follow-on rule;
                  a variant with the follow-on rule is also reported).
  leads mostly  : lead share >= 0.5 (engine LEAD_SHARE).
  mostly follows: 5+ rounds with a named lead and lead share < 0.15 (engine rule).
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict
from math import comb
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]  # relay/ (copied from junction-2026/research/need; paths adapted to this repo)
ROOT = REPO.parent
sys.path.insert(0, str(REPO / "app"))
sys.path.insert(0, str(REPO / "pipeline"))
from engine import LEAD_SHARE, Snapshot, fund_profile  # noqa: E402
from validate import lead_comes_back as validate_lead_comes_back  # noqa: E402

SNAPSHOT = Path(os.environ.get("RELAY_SNAPSHOT_PATH", str(ROOT / "cala" / "data" / "snapshot.json")))
VALIDATION = REPO / "app" / "validation.json"
OUT = Path(__file__).with_suffix(".json")

STAGES = {"pre-seed", "seed"}
YEARS = range(2023, 2027)
TOP_N = 50
FOLLOW_SHARE = 0.15  # engine "Mostly follows": known >= 5 and ratio < 0.15
FOLLOW_MIN_KNOWN = 5
LIST_SIZE = 14

NORDIC = {"finland", "sweden", "denmark", "norway", "iceland", "estonia"}
ALIASES = {"uk": "united kingdom", "england": "united kingdom", "scotland": "united kingdom",
           "czechia": "czech republic", "the netherlands": "netherlands"}
EUROPE = NORDIC | {
    "united kingdom", "ireland", "germany", "austria", "switzerland", "france", "netherlands", "belgium",
    "luxembourg", "spain", "portugal", "italy", "greece", "cyprus", "malta", "poland", "czech republic", "slovakia",
    "hungary", "romania", "bulgaria", "croatia", "slovenia", "serbia", "latvia", "lithuania", "ukraine",
    "liechtenstein", "monaco", "andorra", "bosnia and herzegovina", "north macedonia", "albania", "montenegro",
    "moldova", "europe",
}

# The sample list in relay/app/static/app.js (SAMPLE), fund lines only. Its 14th line is a coffee note, not a fund.
SAMPLE_FUNDS = ["Maki.vc", "Voima Ventures", "Creandum", "Inventure", "Speedinvest", "Northzone", "Icebreaker.vc",
                "byFounders", "Seedcamp", "Point Nine", "Business Finland", "Superhero Capital", "FJ Labs"]


def primary_country(raw: str | None) -> str | None:
    if not raw:
        return None
    first = raw.split("/")[0].split("(")[0].strip().lower()
    return ALIASES.get(first, first) or None


def in_scope(r: dict, countries: set[str] | None) -> bool:
    if r["stage"] not in STAGES or r["year"] not in YEARS or r.get("disputed") or r.get("not_led"):
        return False
    return countries is None or primary_country(r.get("country")) in countries


def investor_stats(rounds: list[dict], follow_on_rule: bool) -> dict[str, dict]:
    """Per investor: rounds joined, rounds with a named lead, rounds led. Optional engine follow-on rule:
    joining a company's later round (2+ months after first appearing there) without leading is skipped."""
    first_t: dict[tuple[str, str], float] = {}
    for r in rounds:
        for k in set(r["leads"]) | set(r["participants"]):
            first_t[(k, r["ckey"])] = min(first_t.get((k, r["ckey"]), r["t"]), r["t"])
    s: dict[str, dict] = defaultdict(lambda: {"joined": 0, "known": 0, "led": 0})
    for r in rounds:
        for k in set(r["leads"]) | set(r["participants"]):
            led = k in r["leads"]
            if follow_on_rule and not led and r["t"] > first_t[(k, r["ckey"])] + 0.17:
                continue
            s[k]["joined"] += 1
            if r["leads"]:
                s[k]["known"] += 1
                s[k]["led"] += led
    return s


def active_list(snap: Snapshot, rounds: list[dict], follow_on_rule: bool = False, hubs: bool = False) -> dict:
    s = investor_stats(rounds, follow_on_rule)
    keys = [k for k in s if hubs or not snap.is_hub(k)]
    top = sorted(keys, key=lambda k: (-s[k]["joined"], k))[:TOP_N]
    rows = []
    for k in top:
        known, led = s[k]["known"], s[k]["led"]
        share = led / known if known else None
        rows.append({"key": k, "name": snap.name(k), "joined": s[k]["joined"], "known": known, "led": led,
                     "share": round(share, 3) if share is not None else None,
                     "leads_mostly": share is not None and share >= LEAD_SHARE,
                     "mostly_follows": known >= FOLLOW_MIN_KNOWN and share is not None and share < FOLLOW_SHARE})
    judged = [r for r in rows if r["known"] >= 3]  # engine: fewer than 3 known rounds is "Too few rounds"
    return {
        "rounds": len(rounds), "rounds_with_lead": sum(bool(r["leads"]) for r in rounds),
        "investors_seen": len(s), "top_n": len(rows),
        "min_joined_in_top": rows[-1]["joined"] if rows else None,
        "judged": len(judged),
        "leads_mostly": sum(r["leads_mostly"] for r in judged),
        "below_half": sum(not r["leads_mostly"] for r in judged),
        "mostly_follows": sum(r["mostly_follows"] for r in judged),
        "median_share": sorted(r["share"] for r in judged)[len(judged) // 2] if judged else None,
        "rows": rows,
    }


def seats(rounds: list[dict]) -> dict:
    with_lead = [r for r in rounds if r["leads"]]
    lead = sum(len(r["leads"]) for r in with_lead)
    total = sum(len(r["leads"]) + len(r["participants"]) for r in with_lead)
    multi = [r for r in with_lead if len(r["leads"]) + len(r["participants"]) >= 2]
    return {"rounds_with_lead": len(with_lead), "lead_seats": lead, "all_seats": total,
            "lead_share": round(lead / total, 3) if total else None,
            "rounds_2plus_investors": len(multi),
            "lead_share_2plus": round(sum(len(r["leads"]) for r in multi)
                                      / sum(len(r["leads"]) + len(r["participants"]) for r in multi), 3) if multi else None}


def binom_at_least(n: int, p: float, k: int) -> float:
    return sum(comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k, n + 1))


def main() -> None:
    raw = json.loads(SNAPSHOT.read_text())
    snap = Snapshot.from_dict(raw)
    all_ok = [r for r in snap.rounds if not r.get("disputed") and not r.get("not_led")]
    nordic = [r for r in snap.rounds if in_scope(r, NORDIC)]
    europe = [r for r in snap.rounds if in_scope(r, EUROPE)]

    out: dict = {"snapshot_version": snap.version, "definitions": __doc__}
    out["a_nordic"] = active_list(snap, nordic)
    out["b_europe"] = active_list(snap, europe)
    out["sensitivity"] = {
        "nordic_engine_follow_on_rule": {k: v for k, v in active_list(snap, nordic, follow_on_rule=True).items() if k != "rows"},
        "europe_engine_follow_on_rule": {k: v for k, v in active_list(snap, europe, follow_on_rule=True).items() if k != "rows"},
        "nordic_with_public_bodies": {k: v for k, v in active_list(snap, nordic, hubs=True).items() if k != "rows"},
        "europe_with_public_bodies": {k: v for k, v in active_list(snap, europe, hubs=True).items() if k != "rows"},
    }
    out["c_seats"] = {"all_rounds_all_stages": seats(all_ok), "nordic_preseed_seed_2023_26": seats(nordic),
                      "europe_preseed_seed_2023_26": seats(europe)}

    stored = json.loads(VALIDATION.read_text())["lead_comes_back"]
    recomputed = validate_lead_comes_back(snap.rounds)
    out["d_lead_comes_back"] = {"validation_json": stored, "recomputed_now": recomputed,
                                "led_again_share": round(stored["led_again"] / stored["cases"], 3),
                                "came_back_share": round(stored["came_back"] / stored["cases"], 3)}

    # (e) a 14-fund list drawn like the Nordic active list
    a = out["a_nordic"]
    p_below = a["below_half"] / a["judged"]
    p_follow = a["mostly_follows"] / a["judged"]
    p_lead = a["leads_mostly"] / a["judged"]
    out["e_list_of_14"] = {
        "basis": "Nordic active list (a), judged investors",
        "expected_below_half": round(LIST_SIZE * p_below, 1),
        "expected_mostly_follows_engine": round(LIST_SIZE * p_follow, 1),
        "expected_lead_mostly": round(LIST_SIZE * p_lead, 1),
        "p_at_least_half_below_half": round(binom_at_least(LIST_SIZE, p_below, LIST_SIZE // 2), 3),
    }
    # the actual sample list, run through the engine as the app does (seed, EUR 3m)
    sample = []
    for name in SAMPLE_FUNDS:
        key = snap.match_fund(name)
        if not key:
            sample.append({"name": name, "key": None})
            continue
        p = fund_profile(snap, key, "seed", 3.0)
        sample.append({"name": name, "key": key, "verdict": p["verdict"], "label": p["verdict_label"],
                       "led": p["led"], "known": p["known"]})
    out["e_sample_list"] = {"funds": sample, "verdicts": dict(Counter(x.get("verdict") for x in sample))}

    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    for part in ("a_nordic", "b_europe"):
        print(part, {k: v for k, v in out[part].items() if k != "rows"})
    print("sensitivity", json.dumps(out["sensitivity"], indent=1))
    print("c", json.dumps(out["c_seats"], indent=1))
    print("d", out["d_lead_comes_back"])
    print("e", out["e_list_of_14"])
    print("sample", out["e_sample_list"]["verdicts"])
    for x in sample:
        print("  ", x)


if __name__ == "__main__":
    main()
