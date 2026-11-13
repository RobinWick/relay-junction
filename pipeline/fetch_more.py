"""Widen discovery with country x sector slices, then fetch histories for new companies.

Stops when the credit budget for this run is used. Appends to data/companies.json and data/histories.jsonl.
"""
from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import cala_client as cala
from fetch import COUNTRIES, DATA, WORKERS, histories

SECTORS = ["Fintech", "Healthtech", "Climate", "Energy", "SaaS", "AI", "Deeptech", "Mobility",
           "Foodtech", "Gaming", "Cybersecurity", "Biotech", "Proptech", "Ecommerce", "Edtech", "Robotics"]
BIG = ["Sweden", "Finland", "Norway", "Denmark", "Germany", "France", "United Kingdom", "Netherlands",
       "Spain", "Switzerland", "Estonia", "Poland"]


def _one(country: str, sector: str) -> tuple[str, list[dict]]:
    q = f"startups.location={country}.industry={sector}.funding>2M"
    return country, cala.query(q).get("results", [])


def main(budget: int) -> None:
    path = DATA / "companies.json"
    companies = json.loads(path.read_text())
    seen = {c["name"].lower() for c in companies}
    jobs = [(c, s) for c in BIG for s in SECTORS]
    used = 0
    with ThreadPoolExecutor(WORKERS) as pool:
        futures = [pool.submit(_one, *j) for j in jobs]
        for fut in as_completed(futures):
            used += 1
            try:
                country, rows = fut.result()
            except RuntimeError as err:
                print(f"discover FAIL: {err}", flush=True)
                continue
            new = 0
            for row in rows:
                name = (row.get("name") or row.get("company") or "").strip()
                if name and name.lower() not in seen:
                    seen.add(name.lower())
                    companies.append({"name": name, "country": country, "band": "sector", "row": row})
                    new += 1
            print(f"discover {country}: {len(rows)} rows, {new} new, total {len(companies)}", flush=True)
    path.write_text(json.dumps(companies, ensure_ascii=False, indent=1))
    remaining = max(0, budget - used)
    print(f"DISCOVERED total {len(companies)}; history budget {remaining}", flush=True)
    histories(companies, limit=len(companies) if remaining >= len(companies) else 289 + remaining)
    print("DONE", flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 1300)
