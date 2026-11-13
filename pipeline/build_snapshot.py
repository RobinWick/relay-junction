"""Merge company-first, investor-first and live Cala rows into one round list, then store a snapshot in Postgres.

Company-first rows: data/histories.jsonl (crawl).
Investor-first rows: data/funds.jsonl (fetch_funds.py), each row says whether the fund led.
Live rows: table `live_funds` in Aiven (funds looked up from the app), so a rebuild never drops them.
A round seen on several paths is merged when company, stage and date (within ~2 months) agree.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from merge import Builder, canon  # noqa: E402

DATA = Path(os.environ.get("RELAY_DATA_DIR", Path(__file__).resolve().parents[2] / "cala" / "data"))


def live_records() -> list[dict]:
    url = os.environ.get("RELAY_DATABASE_URL")
    if not url:
        return []
    import psycopg
    with psycopg.connect(url, connect_timeout=20) as conn:
        exists = conn.execute("select to_regclass('live_funds')").fetchone()[0]
        if not exists:
            return []
        return [row[0] for row in conn.execute("select data from live_funds order by id")]


def build() -> dict:
    b = Builder()
    b.company_first(DATA)
    b.investor_first(DATA)
    fund_keys = set()
    if (DATA / "funds.jsonl").exists():
        fund_keys = {canon(json.loads(line)["name"]) for line in (DATA / "funds.jsonl").open()}
    for rec in live_records():
        b.add_fund_record(rec)
        fund_keys.add(canon(rec["name"]))
    return b.snapshot(fund_keys)


def store(snap: dict) -> None:
    import psycopg
    from psycopg.types.json import Jsonb
    with psycopg.connect(os.environ["RELAY_DATABASE_URL"], connect_timeout=20) as conn:
        conn.execute("create table if not exists snapshot (version text primary key, created_at timestamptz default now(), "
                     "data jsonb not null)")
        conn.execute("insert into snapshot(version, data) values (%s, %s) on conflict (version) do update set data = excluded.data",
                     (snap["version"], Jsonb(snap)))
        conn.execute("delete from snapshot where version not in (select version from snapshot order by created_at desc limit 3)")
        conn.commit()


if __name__ == "__main__":
    s = build()
    (DATA / "snapshot.json").write_text(json.dumps(s, ensure_ascii=False))
    print(s["stats"], "both-path rounds:", sum(1 for r in s["rounds"] if r["query_path"] == "both"))
    if "--store" in sys.argv:
        store(s)
        print("stored in Postgres, version", s["version"])
