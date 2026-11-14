"""Validation numbers for the Method page, recomputed from the merged snapshot. Writes app/validation.json.

Within-round test: in each round with a named lead, rank the investors (that have history before this round)
by their lead record from strictly earlier rounds. Score 1 if the top-ranked investor really led this round.
Compare with picking one of the same investors at random. Ties at the top are averaged.
"""
from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from engine import HUBS  # noqa: E402

DATA = Path(__file__).resolve().parents[2] / "cala" / "data"
OUT = Path(__file__).resolve().parents[1] / "app" / "validation.json"


def wilson(k: float, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (c - m) / d, (c + m) / d


def within_round(rounds: list[dict]) -> dict:
    rounds = sorted(rounds, key=lambda r: r["t"])
    led = defaultdict(int)
    known = defaultdict(int)
    hits = rnd = 0.0
    n = 0
    i = 0
    while i < len(rounds):
        # rounds on the same date are scored before any of them updates the history
        j = i
        while j < len(rounds) and abs(rounds[j]["t"] - rounds[i]["t"]) < 1e-6:
            j += 1
        batch = rounds[i:j]
        for r in batch:
            if not r["leads"]:
                continue
            invs = [k for k in set(r["leads"]) | set(r["participants"]) if k not in HUBS and known[k] > 0]
            leads_in = [k for k in invs if k in r["leads"]]
            if len(invs) < 2 or not leads_in or len(leads_in) == len(invs):
                continue
            score = {k: (led[k] + 1) / (known[k] + 2) for k in invs}
            top = max(score.values())
            best = [k for k in invs if score[k] == top]
            hits += sum(1 for k in best if k in r["leads"]) / len(best)
            rnd += len(leads_in) / len(invs)
            n += 1
        for r in batch:
            if r["leads"]:
                for k in set(r["leads"]) | set(r["participants"]):
                    known[k] += 1
                    led[k] += k in r["leads"]
        i = j
    lo, hi = wilson(hits, n)
    return {"n": n, "hit": hits / n if n else 0, "random": rnd / n if n else 0, "ci_low": lo, "ci_high": hi}


def coverage(rounds: list[dict]) -> dict:
    by = defaultdict(lambda: [0, 0])
    for r in rounds:
        st = r["stage"] or "unlabelled"
        by[st][1] += 1
        by[st][0] += bool(r["leads"])
    return {k: {"with_lead": v[0], "total": v[1]} for k, v in by.items()}


def lead_comes_back(rounds: list[dict]) -> dict:
    by_co = defaultdict(list)
    for r in rounds:
        by_co[r["ckey"]].append(r)
    cases = came = led_again = 0
    for rs in by_co.values():
        rs.sort(key=lambda r: r["t"])
        for a, b in zip(rs, rs[1:]):
            if not a["leads"] or b["t"] - a["t"] < 0.17:
                continue
            for k in a["leads"]:
                if k in HUBS:
                    continue
                cases += 1
                came += k in b["leads"] or k in b["participants"]
                led_again += k in b["leads"]
    return {"cases": cases, "came_back": came, "led_again": led_again}


def graph_check() -> dict:
    """Agreement between our merged lead and Cala's entity graph, on the random sample from fetch_graph.py."""
    path = DATA / "graph.jsonl"
    recs = [json.loads(line) for line in path.open()] if path.exists() else []
    snap = json.loads((DATA / "snapshot.json").read_text())
    current = {f"{r['ckey']}|{r['year']}|{r['month']}|{r['stage'] or ''}": r["graph"]["agreement"]
               for r in snap["rounds"] if r.get("graph")}
    for r in recs:  # use the agreement as recomputed in the snapshot
        r["agreement"] = current.get(r["key"], r["agreement"])
    sample = [r for r in recs if r["group"] == "sample"]
    found = [r for r in sample if r["agreement"] != "not_in_graph"]
    with_lead = [r for r in found if r["agreement"] in ("agrees", "differs")]
    return {"sample": len(sample), "found": len(found), "found_with_lead": len(with_lead),
            "agrees": sum(r["agreement"] == "agrees" for r in with_lead),
            "differs": [{"company": r["company"], "key": r["key"]} for r in with_lead if r["agreement"] == "differs"][:20]}


def main() -> None:
    snap = json.loads((DATA / "snapshot.json").read_text())
    rounds = snap["rounds"]
    wr = within_round(rounds)
    cov = coverage(rounds)
    lcb = lead_comes_back(rounds)
    pct = lambda x: f"{round(100 * x)}%"
    rows = [
        {"test": "In a round with a named lead, the investor with the stronger earlier lead record is the real lead",
         "result": f"{pct(wr['hit'])} vs {pct(wr['random'])} for a random pick from the same cap table "
                   f"(95% CI {pct(wr['ci_low'])} to {pct(wr['ci_high'])})", "n": wr["n"]},
        {"test": "Predicting the next round's new lead from earlier rounds (top 5)",
         "result": "1.4%, the same as chance. So Recount reports what funds did, not odds.", "n": 140},
        {"test": "Seed rounds where Cala names the lead",
         "result": pct(cov.get("seed", {}).get("with_lead", 0) / max(1, cov.get("seed", {}).get("total", 1))),
         "n": cov.get("seed", {}).get("total", 0)},
        {"test": "Series A rounds where Cala names the lead",
         "result": pct(cov.get("series a", {}).get("with_lead", 0) / max(1, cov.get("series a", {}).get("total", 1))),
         "n": cov.get("series a", {}).get("total", 0)},
        {"test": "The lead of a round comes back in the company's next round",
         "result": f"{pct(lcb['came_back'] / max(1, lcb['cases']))} came back, {pct(lcb['led_again'] / max(1, lcb['cases']))} led again",
         "n": lcb["cases"]},
    ]
    acc_path = Path(__file__).resolve().parents[2] / "research" / "accuracy.json"
    accuracy = []
    if acc_path.exists():
        accuracy = json.loads(acc_path.read_text())
        rnd = [a for a in accuracy if a["group"] == "random_30"]
        smp = [a for a in accuracy if a["group"] == "sample_list"]
        cnt = lambda xs, v: sum(1 for a in xs if a["verdict"] == v)
        sourced = len(rnd) - cnt(rnd, "unverifiable")
        rows.insert(1, {"test": "Cala's named lead matches a public source (random rounds, checked by hand on 14 Nov)",
                        "result": f"{cnt(rnd, 'correct')} of {sourced} rounds where a source names the lead; "
                                  f"{cnt(rnd, 'partly')} partly right, {cnt(rnd, 'wrong')} wrong (one was our parsing, now fixed); "
                                  f"{cnt(rnd, 'unverifiable')} had no public source naming a lead",
                        "n": len(rnd)})
        rows.insert(2, {"test": "Most recent led round of each sample Nordic fund, checked by hand",
                        "result": f"{cnt(smp, 'correct')} of {len(smp)} correct; {cnt(smp, 'partly')} right fund but a co-lead missing",
                        "n": len(smp)})
        accuracy = [{"company": a["company"], "date": a["date"], "stage": a.get("stage"), "cala_leads": a.get("cala_leads"),
                     "verdict": a["verdict"], "source_url": a.get("source_url"), "note": a.get("note", "")[:240],
                     "group": a["group"]} for a in accuracy]
    graph = graph_check()
    if graph["sample"]:
        g = graph
        rows.insert(1, {"test": "Cala's entity graph (FundingRound entities with is_lead) checked against our merged lead, "
                                "random rounds with a named lead",
                        "result": f"round found in the graph for {g['found']} of {g['sample']}; where the graph marks a "
                                  f"lead, it agrees with ours in {g['agrees']} of {g['found_with_lead']}",
                        "n": g["sample"]})
    out = {"version": snap["version"], "rows": rows, "graph_check": graph, "within_round": wr, "coverage": cov, "lead_comes_back": lcb,
           "accuracy": accuracy,
           "note": "The prediction test ran on the first 289 companies before the investor-first crawl. The other counted rows are recomputed on every data rebuild; hand checks are dated."}
    OUT.write_text(json.dumps(out, indent=1))
    print(json.dumps({"within_round": wr, "lead_comes_back": lcb, "seed": cov.get("seed"), "a": cov.get("series a")}, indent=1))


if __name__ == "__main__":
    main()
