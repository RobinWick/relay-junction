"""Cross-check rounds against Cala's entity graph (FundingRound entities with is_lead edges).

Two groups of rounds:
- demo: the rounds behind the sample verdicts (same pick as fetch_sources.py), so the record sheet shows the check;
- sample: a seeded random sample of rounds with a named lead, for the agreement number on the Method page.
Writes data/graph.jsonl (one line per round). build_snapshot.py attaches it; validate.py counts agreement.
Usage: python3 fetch_graph.py <demo_rounds> <sample_rounds>
"""
from __future__ import annotations

import json
import random
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "app"))
sys.path.insert(0, str(HERE))
import cala_client as cala  # noqa: E402
from engine import Snapshot  # noqa: E402
from fetch_sources import pick, round_key  # noqa: E402
from graph import agreement, check_round  # noqa: E402

DATA = HERE.parents[1] / "cala" / "data"


def main(n_demo: int, n_sample: int) -> None:
    snap = Snapshot.from_dict(json.loads((DATA / "snapshot.json").read_text()))
    out = DATA / "graph.jsonl"
    done = {json.loads(line)["key"] for line in out.open()} if out.exists() else set()

    def eligible(r: dict) -> bool:
        return bool(r["stage"]) and round_key(r) not in done

    demo = [r for r in pick(snap, n_demo * 3) if eligible(r)][:n_demo]
    pool = [r for r in snap.rounds if r["leads"] and r["year"] >= 2019 and eligible(r) and r not in demo]
    random.Random(14).shuffle(pool)
    todo = [("demo", r) for r in demo] + [("sample", r) for r in pool[:n_sample]]
    print(f"graph: {len(done)} done, {len(todo)} to check ({len(demo)} demo)", flush=True)

    def one(group: str, r: dict) -> dict:
        g = check_round(cala.post, cala.search, snap.entities.get("c:" + r["ckey"]), r["company"], r["stage"], r["t"])
        return {"key": round_key(r), "group": group, "company": r["company"], "graph": g,
                "agreement": agreement([snap.name(k) for k in r["leads"]], g, r["t"])}

    with ThreadPoolExecutor(6) as pool_, out.open("a") as fh:
        futs = {pool_.submit(one, g, r): r for g, r in todo}
        for fut in as_completed(futs):
            r = futs[fut]
            try:
                rec = fut.result()
            except Exception as err:  # one failed check is not fatal
                print(f"graph FAIL {r['company']}: {type(err).__name__}: {str(err)[:120]}", flush=True)
                continue
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            print(f"graph {rec['group']} {r['company']} {r['year']}: {rec['agreement']}; paid {cala.live_calls}", flush=True)
    print(f"DONE paid {cala.live_calls}", flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 40, int(sys.argv[2]) if len(sys.argv) > 2 else 100)
