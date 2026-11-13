"""Merge company-first and investor-first Cala rows into one round list, then store a snapshot in Postgres.

Company-first rows: data/histories.jsonl (via normalize.py -> rounds.json).
Investor-first rows: data/funds.jsonl (fetch_funds.py), each row says whether the fund led.
A round seen on both paths is merged when company, stage and date (within ~2 months) agree.
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from merge import Builder, _field, canon, parse_date, split_investors  # noqa: E402,F401

DATA = Path(os.environ.get("RELAY_DATA_DIR", Path(__file__).resolve().parents[2] / "cala" / "data"))
def build() -> dict:
    b = Builder()
    b.company_first(DATA)
    b.investor_first(DATA)
    fund_keys = set()
    if (DATA / "funds.jsonl").exists():
        fund_keys = {canon(json.loads(l)["name"]) for l in (DATA / "funds.jsonl").open()}
    return b.snapshot(fund_keys)


def store(snap: dict) -> None:
    import psycopg
    from psycopg.types.json import Jsonb
    url = os.environ["RELAY_DATABASE_URL"]
    with psycopg.connect(url, connect_timeout=20) as conn:
        conn.execute("create table if not exists snapshot (version text primary key, created_at timestamptz default now(), "
                     "data jsonb not null)")
        conn.execute("insert into snapshot(version, data) values (%s, %s) on conflict (version) do update set data = excluded.data",
                     (snap["version"], Jsonb(snap)))
        conn.execute("delete from snapshot where version not in (select version from snapshot order by created_at desc limit 3)")
        conn.commit()


if __name__ == "__main__":
    s = build()
    out = DATA / "snapshot.json"
    out.write_text(json.dumps(s, ensure_ascii=False))
    print(s["stats"], "both-path rounds:", sum(1 for r in s["rounds"] if r["query_path"] == "both"))
    if "--store" in sys.argv:
        store(s)
        print("stored in Postgres, version", s["version"])
