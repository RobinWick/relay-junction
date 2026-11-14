"""Ask Cala's /v1/knowledge/search for a sourced answer about the rounds the demo shows.

Picks the rounds behind the sample list (last leads, led rounds, conflicts, ties, the lead-comes-back examples),
asks Cala one question per round, and writes data/sources.jsonl. build_snapshot.py attaches the answer,
the cited passages and their document URLs to the matching round, so the record view shows real sources.
Usage: python3 fetch_sources.py [budget]
"""
from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "app"))
sys.path.insert(0, str(HERE))
import cala_client as cala  # noqa: E402
from engine import Snapshot, conflicts, fund_profile, lead_comes_back, tie  # noqa: E402

DATA = HERE.parents[1] / "cala" / "data"
SAMPLE = ["Maki.vc", "Voima Ventures", "Creandum", "Inventure", "Speedinvest", "Northzone", "Icebreaker.vc",
          "byFounders", "Seedcamp", "Point Nine", "Superhero Capital", "FJ Labs", "Kvanted", "Lifeline Ventures"]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]


def round_key(r: dict) -> str:
    return f"{r['ckey']}|{r['year']}|{r['month']}|{r['stage'] or ''}"


def question(r: dict) -> str:
    stage = (r["stage"] or "funding").replace("series", "Series").replace("pre-seed", "pre-seed")
    return (f"Who led {r['company']}'s {stage} round announced around {MONTHS[r['month'] - 1]} {r['year']}, "
            f"how much was raised, and which investors took part?")


def pick(snap: Snapshot, limit: int) -> list[dict]:
    ids: list[int] = []
    keys = [k for k in (snap.match_fund(n) for n in SAMPLE) if k]
    lifeline = snap.match_fund("Lifeline Ventures")
    for k in keys:
        p = fund_profile(snap, k, "seed", 3.0)
        if p["last_lead"]:
            ids.append(p["last_lead"]["id"])
        ids += [x["id"] for x in p["rounds_led"][:2]]
        ids += [c["round"]["id"] for c in conflicts(snap, k, ["Lovable"])]
        t = tie(snap, k, [lifeline], None) if lifeline else None
        if t:
            ids.append(t["round"]["id"])
    lb = lead_comes_back(snap, lifeline) if lifeline else None
    if lb:
        ids += [e["from"]["id"] for e in lb["examples"]] + [e["next"]["id"] for e in lb["examples"]]
    seen, out = set(), []
    for i in ids:
        r = snap.rounds[i]
        if i not in seen:
            seen.add(i)
            out.append(r)
    return out[:limit]


def main(budget: int) -> None:
    snap = Snapshot.from_dict(json.loads((DATA / "snapshot.json").read_text()))
    out = DATA / "sources.jsonl"
    done = {json.loads(line)["key"] for line in out.open()} if out.exists() else set()
    todo = [r for r in pick(snap, budget * 2) if round_key(r) not in done][:budget]
    print(f"sources: {len(done)} done, {len(todo)} to ask", flush=True)
    with ThreadPoolExecutor(8) as pool, out.open("a") as fh:
        futs = {pool.submit(cala.post, "/knowledge/search", {"input": question(r)}): r for r in todo}
        for fut in as_completed(futs):
            r = futs[fut]
            try:
                res = fut.result()
            except Exception as err:  # keep going; one failed search is not fatal
                print(f"source FAIL {r['company']}: {type(err).__name__}", flush=True)
                continue
            fh.write(json.dumps({"key": round_key(r), "company": r["company"], "question": question(r),
                                 "response": res}, ensure_ascii=False) + "\n")
            fh.flush()
            n = sum(len(c.get("origins", [])) for c in res.get("context", []))
            print(f"source {r['company']} {r['year']}: {n} origins", flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 60)
