"""Point-in-time backtest of the Recount Signal score (signal/DESIGN.md section 5).

Run: cd relay/app && python3 signal_backtest.py   (stdlib, local files only, 0 Cala calls, about a minute)
Writes signal_backtest.json next to this file (read by the API) and prints a summary.

Rules
  * For cutoff year C the score is computed with as_of = C + 1: only rounds dated before 1 Jan C+1 are read, and every
    peer pool, backer graduation rate, lead supply count and exit count is rebuilt from those rounds alone.
  * Population: ranked companies (stage on last equity round) with an equity round in C-2..C.
  * Outcomes: next_round_24m = an equity round in [C+1, C+3); graduate_b_plus_36m = last stage pre-seed, seed or A
    and a Series B or later round in [C+1, C+4).
  * Headline stratum: full-history companies (asked company-first). All-company numbers are inflated by coverage.
  * Split: validation cutoffs 2018 to 2020 (weight choice, at most 3 candidates); held-out cutoffs 2021 to 2023 for
    next round and 2021 to 2022 for graduation. The held-out numbers are computed once for the chosen weights.
    Caveat: the design debate looked at 2018 to 2023 before the candidates were written, so held-out is not pristine.
"""
from __future__ import annotations

import json
import math
import os
import random
from collections import defaultdict
from pathlib import Path

from merge import company_key
from signal_score import (DEFAULT_WEIGHTS, EARLY, KEYS, LATE, TIER, ScoreInputs, build_context, clamp_weights,
                          score_all)

APP = Path(__file__).parent
ROOT = APP.parent.parent
SNAPSHOT = Path(os.environ.get("RELAY_SNAPSHOT_PATH") or ROOT / "cala" / "data" / "snapshot.json")
EXITS_APP = APP / "exits.json"
EXITS_EXP = ROOT / "cala" / "expansion" / "exits.json"
OUT = APP / "signal_backtest.json"

VALID = [2018, 2019, 2020]
HELD = {"next_round_24m": [2021, 2022, 2023], "graduate_b_plus_36m": [2021, 2022]}
B = 1000
SEED = 7


# ---------------------------------------------------------------- inputs
def load_inputs() -> tuple[ScoreInputs, dict]:
    snap = json.loads(SNAPSHOT.read_text())
    exits, checked = [], set()
    if EXITS_APP.exists():
        app = json.loads(EXITS_APP.read_text())
        for fk, f in app["funds"].items():
            checked.add(fk)
            for r in f.get("receipts", []):
                exits.append({"fund_key": fk, "ckey": company_key(r["company"]), "year": r.get("year")})
    if EXITS_EXP.exists():
        exp = json.loads(EXITS_EXP.read_text())
        for fk, evs in exp["exits"].items():
            checked.add(fk)
            for r in evs:
                exits.append({"fund_key": fk, "ckey": company_key(r["company"]),
                              "year": int(r["date"][:4]) if r.get("date") else None})
    inp = ScoreInputs(snap["rounds"], snap["investor_names"], set(snap["fund_keys"]), exits, checked)
    return inp, {"snapshot_version": snap["version"], "retrieved": snap["retrieved"]}


# ---------------------------------------------------------------- stats
def auc(scores: list[float], ys: list[bool]):
    n1 = sum(ys)
    n0 = len(ys) - n1
    if not n1 or not n0:
        return None
    order = sorted(range(len(scores)), key=lambda i: scores[i])
    rank_sum, i = 0.0, 0
    while i < len(order):
        j = i
        while j < len(order) and scores[order[j]] == scores[order[i]]:
            j += 1
        mid = (i + j + 1) / 2
        rank_sum += mid * sum(1 for k in order[i:j] if ys[k])
        i = j
    return (rank_sum - n1 * (n1 + 1) / 2) / (n1 * n0)


def r3(x):
    return None if x is None else round(x, 3)


def cluster_ci(rows: list[dict], key: str, y: str, rng: random.Random, b: int = B):
    by = defaultdict(list)
    for r in rows:
        by[r["ck"]].append(r)
    keys = sorted(by)
    vals = []
    for _ in range(b):
        s = [r for k in (rng.choice(keys) for _ in keys) for r in by[k]]
        a = auc([r[key] for r in s], [r[y] for r in s])
        if a is not None:
            vals.append(a)
    vals.sort()
    return [r3(vals[int(0.05 * len(vals))]), r3(vals[int(0.95 * len(vals)) - 1])] if vals else None


def null_band(rows: list[dict], key: str, y: str, rng: random.Random, b: int = B):
    """Permutation null: shuffle labels within each cutoff, 5th to 95th percentile of AUC."""
    by = defaultdict(list)
    for r in rows:
        by[r["C"]].append(r)
    vals = []
    for _ in range(b):
        sc, ys = [], []
        for C in sorted(by):
            lab = [r[y] for r in by[C]]
            rng.shuffle(lab)
            sc += [r[key] for r in by[C]]
            ys += lab
        a = auc(sc, ys)
        if a is not None:
            vals.append(a)
    vals.sort()
    return [r3(vals[int(0.05 * len(vals))]), r3(vals[int(0.95 * len(vals)) - 1])]


def top_rates(rows: list[dict], key: str, y: str) -> dict:
    """Top decile / quartiles formed within each cutoff (ties broken by company key), pooled."""
    by = defaultdict(list)
    for r in rows:
        by[r["C"]].append(r)
    top, q1, q4, p50, p100 = [], [], [], {}, {}
    for C, rs in sorted(by.items()):
        rs = sorted(rs, key=lambda r: (-r[key], r["ck"]))
        n = len(rs)
        top += rs[:math.ceil(0.1 * n)]
        q1 += rs[:math.ceil(0.25 * n)]
        q4 += rs[n - math.ceil(0.25 * n):]
        base_c = sum(r[y] for r in rs) / n
        for k, d in ((50, p50), (100, p100)):
            if n >= k * 2:
                d[C] = {"precision": r3(sum(r[y] for r in rs[:k]) / k), "base": r3(base_c), "n": n}
    base = sum(r[y] for r in rows) / len(rows)
    pos = sum(r[y] for r in rows)
    tr = sum(r[y] for r in top) / len(top)
    return {"n": len(rows), "positives": pos, "base_rate": r3(base), "top_decile_n": len(top), "top_decile_rate": r3(tr),
            "lift": r3(tr / base) if base else None,
            "share_of_positives_in_top_decile": r3(sum(r[y] for r in top) / pos) if pos else None,
            "top_quartile_rate": r3(sum(r[y] for r in q1) / len(q1)),
            "bottom_quartile_rate": r3(sum(r[y] for r in q4) / len(q4)),
            "precision_at_50": p50, "precision_at_100": p100}


def summarize(rows: list[dict], key: str, y: str, rng: random.Random, full: bool = True) -> dict:
    s = [r for r in rows if r.get(y) is not None and r.get(key) is not None]
    if not s:
        return {"n": 0}
    out = {"n": len(s), "companies": len({r["ck"] for r in s}), "auc": r3(auc([r[key] for r in s], [r[y] for r in s])),
           "per_cutoff": {C: r3(auc([r[key] for r in s if r["C"] == C], [r[y] for r in s if r["C"] == C]))
                          for C in sorted({r["C"] for r in s})}}
    last = {}
    for r in sorted(s, key=lambda r: r["C"]):
        last[r["ck"]] = r
    one = list(last.values())
    out["one_row_per_company"] = {"n": len(one), "auc": r3(auc([r[key] for r in one], [r[y] for r in one]))}
    if full:
        out["cluster_ci90"] = cluster_ci(s, key, y, rng)
        out.update(top_rates(s, key, y))
    return out


# ---------------------------------------------------------------- rows
CANDIDATES = {
    "default": None,  # DESIGN.md 1.1 frozen defaults (signal_score.DEFAULT_WEIGHTS), not signal_weights.json
    "measured_only": {k: 0.0 for k in KEYS if TIER[k] == "thesis"},
    "thesis_max": {"backer_graduation": 0.15, "named_angels": 0.08, "insider_follow_on": 0.07},
}


def build_rows(inp: ScoreInputs, cutoffs: list[int], weight_sets: dict[str, dict]) -> list[dict]:
    by_c = defaultdict(list)
    for r in inp.rounds:
        if not r.get("not_led") and not r.get("disputed"):
            by_c[r["ckey"]].append(r)
    rng = random.Random(SEED)
    rows = []
    for C in cutoffs:
        as_of = C + 1.0
        ctx = build_context(inp, as_of)
        runs = {name: score_all(inp, as_of, w, ctx=ctx) for name, w in weight_sets.items()}
        base = runs["default"]
        for ck in sorted(base.rows):
            row = base.rows[ck]
            if not row["ranked"]:
                continue
            pre = ctx.by_company[ck]
            if pre[-1]["t"] < C - 2:
                continue
            later = [r for r in by_c[ck] if as_of <= r["t"]]
            rec = {"ck": ck, "C": C, "full": row["history_depth"] == "full_history", "stage": row["last_stage"],
                   "y_next": any(r["t"] < as_of + 2 for r in later),
                   "y_grad": (any(r["t"] < as_of + 3 and r.get("stage") in LATE for r in later)
                              if row["last_stage"] in EARLY and C <= 2022 else None),
                   "n_rounds": len(pre), "recency": pre[-1]["t"], "random": rng.random()}
            for name, run in runs.items():
                rec["s_" + name] = run.rows[ck]["raw_score"]
            for p in row["components"]:
                rec["v_" + p["key"]] = p["value"]  # as used (missing = 0.5)
                rec["p_" + p["key"]] = p["value"] if p["present"] else None  # present only
            rows.append(rec)
    return rows


def verdict(results: dict) -> dict:
    """DESIGN.md 5.4, decided before the run. Held-out, full history, chosen weights."""
    nx, gr = (results[y]["held_out"] for y in ("next_round_24m", "graduate_b_plus_36m"))
    def passes(h):
        s = h["signal"]
        return s["auc"] > s["null_band90"][1] and s["cluster_ci90"][0] > 0.5
    gap_next = nx["signal"]["auc"] - nx["size_for_stage_baseline"]["auc"]
    gap_grad = gr["signal"]["auc"] - gr["size_for_stage_baseline"]["auc"]
    if (passes(nx) or passes(gr)) and gap_next >= -0.01:
        v = "pass"
    elif min(nx["signal"]["auc"], gr["signal"]["auc"]) <= 0.5 or (gap_next < -0.01 and gap_grad < -0.01):
        v = "fail"
    else:
        v = "weak"
    s = nx["signal"]
    lines = {
        "pass": (f"The thesis mix ranks full-history companies at AUC {gr['signal']['auc']} on reaching Series B+ within 36 months "
                 f"and {s['auc']} on raising again within 24 months (base rate {round(100 * s['base_rate'])}%). "
                 f"Modest lift, measured on held-out years."),
        "weak": (f"The 13 part thesis mix scored AUC {s['auc']} on raising again within 24 months, inside the noise "
                 f"band ({s['null_band90'][0]} to {s['null_band90'][1]}). That is why the ranking uses size for stage "
                 f"alone."),
        "fail": f"The thesis mix did not beat chance in our backtest (AUC {s['auc']}). It is shown as a transparent summary only.",
    }
    return {"verdict": v, "line": lines[v], "gap_vs_size_alone": {"next_round_24m": r3(gap_next),
                                                                   "graduate_b_plus_36m": r3(gap_grad)}}


def main() -> dict:
    inp, meta = load_inputs()
    weight_sets = {name: clamp_weights(o, base=DEFAULT_WEIGHTS) for name, o in CANDIDATES.items()}
    rows = build_rows(inp, sorted(set(VALID) | set(HELD["next_round_24m"])), weight_sets)
    rng = random.Random(SEED)
    FH = [r for r in rows if r["full"]]
    out = {"meta": {**meta, "built_by": "signal_backtest.py", "bootstrap": B, "seed": SEED,
                    "validation_cutoffs": VALID, "held_out_cutoffs": HELD,
                    "rows_total": len(rows), "rows_full_history": len(FH),
                    "weights": {name: {k: round(v, 4) for k, v in w.items()} for name, w in weight_sets.items()}}}

    # 1. weight choice on validation only (at most 3 candidates)
    val = [r for r in FH if r["C"] in VALID]
    sel = {}
    for name in weight_sets:
        a1 = auc([r["s_" + name] for r in val], [r["y_next"] for r in val])
        g = [r for r in val if r["y_grad"] is not None]
        a2 = auc([r["s_" + name] for r in g], [r["y_grad"] for r in g])
        sel[name] = {"next_round_24m": r3(a1), "graduate_b_plus_36m": r3(a2), "mean": r3((a1 + a2) / 2),
                     "n_next": len(val), "n_grad": len(g)}
    chosen = max(sel, key=lambda k: (sel[k]["mean"], k == "default"))
    out["selection"] = {"criterion": "mean of validation AUC (next round, graduation), full history", "candidates": sel,
                        "chosen": chosen}
    for r in rows:
        r["signal"] = r["s_" + chosen]

    # 2. held-out results, chosen weights, plus baselines and per component
    results = {}
    for y, ykey in (("next_round_24m", "y_next"), ("graduate_b_plus_36m", "y_grad")):
        held = [r for r in FH if r["C"] in HELD[y] and r[ykey] is not None]
        vrows = [r for r in FH if r["C"] in VALID and r[ykey] is not None]
        res = {"held_out": {}, "validation": {}}
        res["held_out"]["signal"] = summarize(held, "signal", ykey, rng)
        res["held_out"]["signal"]["null_band90"] = null_band(held, "signal", ykey, rng)
        for b in ("v_size_for_stage", "n_rounds", "recency", "random"):
            res["held_out"][b.replace("v_", "") + "_baseline"] = summarize(held, b, ykey, rng, full=b == "v_size_for_stage")
        res["validation"]["signal"] = summarize(vrows, "signal", ykey, rng, full=False)
        comps = {}
        for k in KEYS:
            comps[k] = {"present_only": summarize(held, "p_" + k, ykey, rng, full=False),
                        "as_used_with_neutral": summarize(held, "v_" + k, ykey, rng, full=False)}
        res["held_out"]["components"] = comps
        other = {name: summarize(held, "s_" + name, ykey, rng, full=False) for name in weight_sets if name != chosen}
        res["held_out"]["not_chosen_candidates_for_transparency"] = other
        allc = [r for r in rows if r["C"] in HELD[y] and r[ykey] is not None]
        res["held_out_all_companies_inflated_by_coverage"] = summarize(allc, "signal", ykey, rng, full=False)
        res["held_out_all_companies_inflated_by_coverage"].update(top_rates(allc, "signal", ykey))
        results[y] = res
    out["results"] = results
    out["verdict"] = verdict(results)
    OUT.write_text(json.dumps(out, indent=1, default=str))
    return out


if __name__ == "__main__":
    o = main()
    print(json.dumps(o["selection"], indent=1))
    print(json.dumps(o["verdict"], indent=1))
    for y, res in o["results"].items():
        s = res["held_out"]["signal"]
        print(y, {k: s.get(k) for k in ("n", "companies", "auc", "cluster_ci90", "null_band90", "base_rate",
                                        "top_decile_rate", "lift", "top_decile_n", "per_cutoff")})
        print("  size alone", {k: res["held_out"]["size_for_stage_baseline"].get(k) for k in ("auc", "cluster_ci90", "lift")})
        for b in ("n_rounds_baseline", "recency_baseline", "random_baseline"):
            print("  ", b, res["held_out"][b]["auc"])
