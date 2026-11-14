"""Lane 2: real-company backtest of Recount on Nordic seed / pre-seed rounds (2025-2026).

Question: if the founder had pasted the funds that ended up in their round into Recount the day before,
would Recount have put the eventual lead in "Pitch first" and ranked it first?

Sample (all from the cached Cala snapshot, no API calls):
  - country in the Nordics (engine.REGIONS["nordics"]), stage seed or pre-seed, year 2025 or 2026
  - a named lead and at least 3 investors (leads + participants)
  - found company-first (a source with path == "company_first"), so the round was not found by asking about a fund
  - not disputed, not a not-led round
  - one round per company (its earliest eligible round); 20 companies drawn with random.seed(1415)

Time cut (same rule as relay/research/prediction/harness.py): Recount only sees rounds with t < round_t - EPS,
and the engine's "now" is the round date. Snapshot dates are month granular, so rounds in the same month are
not "the past".

Engine use: relay/app/engine.py is imported unchanged. fund_profile gives each listed fund its verdict;
the app's grouping (app.js groupOf) and ordering (app.js rankRows, without a LinkedIn network, competitors
or "like you" rounds) are mirrored below. The founder's own investors for the way-in tie are the company's
investors in its earlier rounds before the cut. The paste order (last sort key) is alphabetical, so the
answer cannot leak through list order.

Run: python3 research/need/backtest.py   (writes research/need/backtest.json next to this file)
"""
from __future__ import annotations

import json
import math
import random
import os
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]  # relay/ (copied from junction-2026/research/need; paths adapted to this repo)
ROOT = REPO.parent
sys.path.insert(0, str(REPO / "app"))
import engine  # noqa: E402  (read-only use of the app's engine)
from engine import Snapshot, fund_profile, tie  # noqa: E402

SNAP_PATH = Path(os.environ.get("RELAY_SNAPSHOT_PATH", str(ROOT / "cala" / "data" / "snapshot.json")))
OUT = Path(__file__).with_name("backtest.json")
EPS = 0.01  # harness.py: about 4 days
SEED = 1415
N_PICK = 20
NORDICS = engine.REGIONS["nordics"]
GROUPS = ["pitch", "size", "few", "avoid"]


def group_of(verdict: str) -> str:
    """app.js groupOf."""
    return {"leads": "pitch", "leads_size": "size", "few": "few"}.get(verdict, "avoid")


def lead_score(p: dict) -> float:
    """app.js leadScore: Wilson lower bound (z = 1) of led / known."""
    n, z = p["known"], 1
    if not n:
        return -1
    q = p["led"] / n
    return (q + z * z / (2 * n) - z * math.sqrt(q * (1 - q) / n + z * z / (4 * n * n))) / (1 + z * z / n)


def investors(r: dict) -> set[str]:
    return set(r["leads"]) | set(r["participants"])


def is_nordic(r: dict) -> bool:
    c = str(r.get("country") or "").lower()
    return any(n in c for n in NORDICS)


def eligible(r: dict) -> bool:
    return (is_nordic(r) and r["stage"] in ("seed", "pre-seed") and r["year"] in (2025, 2026)
            and bool(r["leads"]) and len(investors(r)) >= 3
            and any(s.get("path") == "company_first" for s in r["sources"])
            and not r.get("disputed") and not r.get("not_led"))


def cut_snapshot(full: Snapshot, t_cut: float) -> Snapshot:
    """Same Snapshot object shape, but the indexes only hold rounds strictly before the cut; now_t = round date.

    snap.rounds keeps the full list because ids index into it; every lookup goes through the cut indexes.
    """
    s = Snapshot(rounds=full.rounds, names=full.names, fund_keys=full.fund_keys, stats=full.stats,
                 retrieved=full.retrieved, version=full.version, entities=full.entities)
    by_inv: dict[str, list[int]] = defaultdict(list)
    by_co: dict[str, list[int]] = defaultdict(list)
    for r in full.rounds:
        if r["t"] < t_cut - EPS:
            for k in investors(r):
                by_inv[k].append(r["id"])
            by_co[r["ckey"]].append(r["id"])
    s.by_investor, s.by_company = dict(by_inv), dict(by_co)
    s.now_t = t_cut
    return s


def any_shared_round(s: Snapshot, a: str, b: str, own_ckey: str) -> dict | None:
    """Loosest tie: a and b in any same earlier round of another company (no size or age limit)."""
    shared = set(s.by_investor.get(a, [])) & set(s.by_investor.get(b, []))
    rs = [s.rounds[i] for i in shared if s.rounds[i]["ckey"] != own_ckey]
    if not rs:
        return None
    r = max(rs, key=lambda x: x["t"])
    return {"investor": s.name(a), "company": r["company"], "date": engine.month_label(r), "rid": r["id"],
            "n_investors": len(investors(r))}


def run_round(full: Snapshot, r: dict, use_target: bool) -> dict:
    s = cut_snapshot(full, r["t"])
    listed = sorted(investors(r), key=lambda k: s.name(k).lower())
    earlier = [full.rounds[i] for i in s.by_company.get(r["ckey"], [])]
    my_inv = sorted(set().union(*(investors(x) for x in earlier))) if earlier else []
    target = r["amount_eur_m"] if use_target else None
    rows = []
    for idx, k in enumerate(listed):
        p = fund_profile(s, k, r["stage"], target)
        t = tie(s, k, my_inv, r["company"])
        way = 2 if t else 0  # app.js wayIn without a network: a tie is strength 2
        rows.append({"key": k, "name": s.name(k), "verdict": p["verdict"], "label": p["verdict_label"],
                     "group": group_of(p["verdict"]), "led": p["led"], "known": p["known"],
                     "led_at_stage": p["led_at_stage"], "score": lead_score(p), "way": way, "idx": idx,
                     "is_lead": k in r["leads"], "tie": t, "history": len(s.by_investor.get(k, []))})
    rows.sort(key=lambda x: (GROUPS.index(x["group"]), -x["way"], -x["score"], x["idx"]))
    for pos, x in enumerate(rows, 1):
        x["rank"] = pos
    leads = [x for x in rows if x["is_lead"]]
    pitch = [x for x in rows if x["group"] == "pitch"]
    intro = {}
    for lk in r["leads"]:
        already = lk in my_inv
        t_small = tie(s, lk, my_inv, r["company"])
        t_any = None
        for a in my_inv:
            if a != lk:
                t_any = t_any or any_shared_round(s, a, lk, r["ckey"])
        intro[s.name(lk)] = {"already_investor": already, "small_round_tie": t_small, "any_shared_round": t_any}
    return {
        "n_listed": len(rows), "n_leads": len(leads),
        "lead_in_pitch": any(x["group"] == "pitch" for x in leads),
        "lead_ranked_first": rows[0]["is_lead"],
        # first AND placed there by a lead verdict, not by a tie-break inside "Too few rounds"
        "lead_first_by_verdict": rows[0]["is_lead"] and rows[0]["group"] in ("pitch", "size"),
        "lead_has_verdict": any(x["verdict"] != "few" for x in leads),
        "lead_verdicts": [x["label"] for x in leads],
        "n_no_history": sum(x["history"] == 0 for x in rows),
        "best_lead_rank": min(x["rank"] for x in leads),
        "n_pitch": len(pitch), "n_pitch_that_led": sum(x["is_lead"] for x in pitch),
        "n_follows": sum(x["verdict"] == "follows" for x in rows),
        "lead_called_follows": any(x["verdict"] == "follows" for x in leads),
        "n_few": sum(x["verdict"] == "few" for x in rows),
        "random_first_chance": len(leads) / len(rows),
        "earlier_rounds": len(earlier), "earlier_investors": [s.name(k) for k in my_inv],
        "intro": intro,
        "rows": [{k: v for k, v in x.items() if k not in ("score", "idx", "key")} for x in rows],
    }


def main() -> None:
    raw = json.loads(SNAP_PATH.read_text())
    full = Snapshot.from_dict(raw)
    first: dict[str, dict] = {}
    for r in sorted(full.rounds, key=lambda x: (x["t"], x["id"])):
        if eligible(r) and r["ckey"] not in first:
            first[r["ckey"]] = r
    pool = sorted(first)
    random.seed(SEED)
    picked = sorted(random.sample(pool, min(N_PICK, len(pool))))
    cases = []
    for ck in picked:
        r = first[ck]
        main_run = run_round(full, r, use_target=True)
        no_target = run_round(full, r, use_target=False)
        cases.append({"company": r["company"], "ckey": ck, "rid": r["id"], "country": r["country"],
                      "date": engine.month_label(r), "t": r["t"], "stage": r["stage"],
                      "amount_eur_m": r["amount_eur_m"], "amount_raw": r.get("amount_raw"),
                      "leads": [full.name(k) for k in r["leads"]],
                      "participants": [full.name(k) for k in r["participants"]],
                      "with_target": main_run,
                      "no_target": {k: no_target[k] for k in ("lead_in_pitch", "lead_ranked_first", "best_lead_rank",
                                                              "n_pitch", "n_follows", "lead_called_follows")}})

    def tot(key: str, sub: str = "with_target") -> int:
        return sum(bool(c[sub][key]) for c in cases)

    n = len(cases)
    w = [c["with_target"] for c in cases]
    has_earlier = [c for c in cases if c["with_target"]["earlier_investors"]]

    def intro_any(c: dict, field: str) -> bool:
        return any(v[field] for v in c["with_target"]["intro"].values())

    summary = {
        "snapshot_version": raw["version"], "seed": SEED, "eligible_rounds": sum(eligible(r) for r in full.rounds),
        "eligible_companies": len(pool), "n": n,
        "lead_in_pitch": tot("lead_in_pitch"), "lead_ranked_first": tot("lead_ranked_first"),
        "random_first_expected": round(sum(x["random_first_chance"] for x in w), 2),
        "lead_called_follows": tot("lead_called_follows"),
        "lead_first_by_verdict": tot("lead_first_by_verdict"),
        "lead_has_verdict": tot("lead_has_verdict"),
        "funds_no_history": sum(x["n_no_history"] for x in w),
        "size_group_funds": sum(sum(y["group"] == "size" for y in x["rows"]) for x in w),
        "size_group_that_led": sum(sum(y["group"] == "size" and y["is_lead"] for y in x["rows"]) for x in w),
        "follows_that_led": sum(sum(y["verdict"] == "follows" and y["is_lead"] for y in x["rows"]) for x in w),
        "funds_listed": sum(x["n_listed"] for x in w), "funds_follows": sum(x["n_follows"] for x in w),
        "funds_few": sum(x["n_few"] for x in w), "funds_pitch": sum(x["n_pitch"] for x in w),
        "pitch_that_led": sum(x["n_pitch_that_led"] for x in w),
        "rounds_with_any_pitch": sum(x["n_pitch"] > 0 for x in w),
        "no_target": {"lead_in_pitch": tot("lead_in_pitch", "no_target"),
                      "lead_ranked_first": tot("lead_ranked_first", "no_target")},
        "with_earlier_investors": len(has_earlier),
        "lead_already_investor": sum(intro_any(c, "already_investor") for c in has_earlier),
        "small_round_tie": sum(intro_any(c, "small_round_tie") for c in has_earlier),
        "any_shared_round": sum(intro_any(c, "any_shared_round") for c in has_earlier),
    }
    OUT.write_text(json.dumps({"summary": summary, "cases": cases}, indent=1, ensure_ascii=False))
    print(json.dumps(summary, indent=1))
    print()
    for c in cases:
        x = c["with_target"]
        print(f"{c['company']:28s} {c['country']:8s} {c['date']} {c['stage']:8s} {str(c['amount_eur_m']):>6s}M "
              f"leads={c['leads']} listed={x['n_listed']} pitch={x['n_pitch']} lead_in_pitch={x['lead_in_pitch']} "
              f"first={x['lead_ranked_first']} lead_rank={x['best_lead_rank']} follows={x['n_follows']} "
              f"lead_follows={x['lead_called_follows']} earlier={x['earlier_rounds']}")
        for row in x["rows"]:
            print(f"    {row['rank']:2d}. {row['name'][:34]:34s} {row['label'][:34]:34s} led {row['led']}/{row['known']}"
                  f"{'  LEAD' if row['is_lead'] else ''}{'  tie' if row['tie'] else ''}")


if __name__ == "__main__":
    main()
