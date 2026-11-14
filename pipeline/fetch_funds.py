"""Investor-first crawl: ask Cala about each fund's rounds (did it lead or follow), not about startups.

Big funds answer "too complex" to the open query, so they fall back to one query per year (2023-2026).
Stops at a hard paid-call budget. Writes data/funds.jsonl (one line per fund).
"""
from __future__ import annotations

import json
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import cala_client as cala
from fetch import DATA, WORKERS
from normalize import investor_key

OPEN_Q = ("List every funding round that {f} invested in, with company name, company country, announcement date, "
          "round type, amount, lead investor, all participating investors, and whether {f} led the round")
YEAR_Q = ("Funding rounds {f} invested in during {y}, with company, company country, date, round type, amount, "
          "lead investor, participating investors and whether {f} led")
YEARS = [2023, 2024, 2025, 2026]

HUBS = {  # public bodies, programmes, crossovers: never "leads at your stage" introducers (spec 4.3)
    "european innovation council", "eic fund", "eic", "european investment bank", "eib", "european investment fund", "eif",
    "business finland", "tekes", "htgf", "high tech grunderfonds", "cdti", "eifo", "innosuisse", "vinnova", "bpifrance",
    "austria wirtschaftsservice", "aws", "ffg", "venture kick", "y combinator", "plug and play", "blackrock",
    "j p morgan", "jp morgan", "salesforce ventures", "tiger global", "insight partners", "techstars", "500 global",
    "innovate uk", "british business bank", "kfw", "almi", "innovation norway", "eu", "horizon 2020", "european union",
}
NORDIC = [
    "Lifeline Ventures", "Maki.vc", "Inventure", "Icebreaker.vc", "Voima Ventures", "NordicNinja", "Creandum",
    "Northzone", "EQT Ventures", "byFounders", "Kvanted", "Superhero Capital", "Change Ventures", "Plural",
    "Seedcamp", "Point Nine", "Speedinvest", "Lifeline", "Open Ocean", "Reaktor Ventures", "Butterfly Ventures",
    "Nordic Makers", "Antler", "Contrarian Ventures", "Practica Capital", "Specialist VC", "Kinnevik", "Industrifonden",
    "Luminar Ventures", "Wellstreet", "Spintop Ventures", "J12 Ventures", "Alliance Venture", "Investinor",
    "Sisu Game Ventures", "Vendep Capital", "Tesi", "Nordic Foodtech VC", "Expedition Growth Capital", "Balderton Capital",
    "Atomico", "Index Ventures", "Accel", "Lakestar", "HV Capital", "Cherry Ventures", "La Famiglia", "Project A Ventures",
    "Paua Ventures", "Notion Capital", "LocalGlobe", "Hoxton Ventures", "Molten Ventures", "Lightspeed Venture Partners",
]


def fund_list(top_n: int) -> list[tuple[str, str]]:
    data = json.loads((DATA / "rounds.json").read_text())
    joined: dict[str, int] = {}
    for co in data["companies"]:
        for r in co["rounds"]:
            for k in set(r["leads"] + r["participants"]):
                joined[k] = joined.get(k, 0) + 1
    names = data["investor_names"]
    junk = re.compile(r"\b(angel|individual|undisclosed|disclosed|founder|existing|shareholder|europa|council|"
                      r"innvierte|grunderfonds|gr nderfonds|almi|eit|government|ministry|bank|amf)\b")

    def core(key: str) -> str:  # 'point nine capital' and 'point nine' are one fund
        return re.sub(r"\b(ventures?|capital|vc|partners|fund|management|invest(ments)?)\b", "", key).replace(" ", "")

    picked: dict[str, tuple[str, str]] = {}
    for name in NORDIC:
        picked.setdefault(core(investor_key(name)), (investor_key(name), name))
    for key, _ in sorted(joined.items(), key=lambda kv: -kv[1]):
        if len(picked) >= top_n + len(NORDIC):
            break
        if key in HUBS or not key or junk.search(key) or len(key.split()) == 2 and key.istitle():
            continue
        picked.setdefault(core(key), (key, names.get(key, key)))
    return list(picked.values())


def _rows(res: dict) -> list[dict]:
    rows = res.get("results", []) or []
    return [] if (len(rows) == 1 and "error" in rows[0]) else rows


def fetch_fund(key: str, name: str, budget_left) -> dict:
    queries = []
    res = cala.query(OPEN_Q.format(f=name))
    rows = _rows(res)
    queries.append({"q": OPEN_Q.format(f=name), "rows": rows, "entities": res.get("entities", [])})
    if not rows and budget_left() > len(YEARS):
        for y in YEARS:
            r = cala.query(YEAR_Q.format(f=name, y=y))
            queries.append({"q": YEAR_Q.format(f=name, y=y), "year": y, "rows": _rows(r), "entities": r.get("entities", [])})
    return {"key": key, "name": name, "queries": queries}


def main(budget: int, top_n: int) -> None:
    funds = fund_list(top_n)
    out = DATA / "funds.jsonl"
    done = {json.loads(l)["key"] for l in out.open()} if out.exists() else set()
    todo = [f for f in funds if f[0] not in done]
    print(f"funds: {len(funds)} picked, {len(done)} done, {len(todo)} to fetch, budget {budget}", flush=True)
    lock = threading.Lock()

    def budget_left() -> int:
        return budget - cala.live_calls

    with ThreadPoolExecutor(WORKERS) as pool, out.open("a") as fh:
        futures = {}
        for key, name in todo:
            futures[pool.submit(lambda k=key, n=name: fetch_fund(k, n, budget_left) if budget_left() > 1 else None)] = name
        for fut in as_completed(futures):
            try:
                rec = fut.result()
            except Exception as err:  # one fund failing must not stop the crawl
                print(f"fund FAIL {futures[fut]}: {type(err).__name__}: {err}", flush=True)
                continue
            if rec is None:
                continue
            with lock:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                fh.flush()
            n = sum(len(q["rows"]) for q in rec["queries"])
            print(f"fund {rec['name']}: {n} rows via {len(rec['queries'])} queries; paid so far {cala.live_calls}", flush=True)
    print(f"DONE paid {cala.live_calls}", flush=True)


if __name__ == "__main__":
    main(budget=int(sys.argv[1]) if len(sys.argv) > 1 else 420, top_n=int(sys.argv[2]) if len(sys.argv) > 2 else 140)
