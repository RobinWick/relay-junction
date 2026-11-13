"""Load normalized Cala round data into Aiven Postgres (schema `relay`). Idempotent: full reload in one transaction.

Usage: RELAY_DATABASE_URL=... python3 load_db.py [path/to/rounds.json]
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

DEFAULT_ROUNDS = Path(__file__).resolve().parents[2] / "cala" / "data" / "rounds.json"

SCHEMA = """
create table if not exists companies (
  id serial primary key,
  name text not null unique,
  country text,
  entity_ids text[] not null default '{}'
);
create table if not exists investors (
  key text primary key,
  name text not null
);
create table if not exists rounds (
  id serial primary key,
  company_id int not null references companies(id) on delete cascade,
  t double precision not null,
  year int not null,
  month int not null,
  stage text,
  type text,
  amount_eur_m double precision,
  amount_raw text,
  source jsonb not null
);
create table if not exists round_investors (
  round_id int not null references rounds(id) on delete cascade,
  investor_key text not null references investors(key),
  role text not null check (role in ('lead', 'participant')),
  primary key (round_id, investor_key)
);
create index if not exists rounds_company_t on rounds(company_id, t);
create index if not exists ri_investor on round_investors(investor_key);
"""


def load(rounds_path: Path) -> dict:
    data = json.loads(rounds_path.read_text())
    url = os.environ.get("RELAY_DATABASE_URL")
    if not url:
        sys.exit("RELAY_DATABASE_URL missing")
    with psycopg.connect(url, connect_timeout=20) as conn, conn.cursor() as cur:
        cur.execute(SCHEMA)
        cur.execute("truncate round_investors, rounds, companies, investors restart identity cascade")
        cur.executemany("insert into investors(key, name) values (%s, %s)",
                        [(k, v) for k, v in data["investor_names"].items() if k])
        n_rounds = 0
        for co in data["companies"]:
            cur.execute("insert into companies(name, country, entity_ids) values (%s, %s, %s) "
                        "on conflict (name) do nothing returning id",
                        (co["name"], co["country"], [e for e in co.get("entity_ids", []) if e]))
            row = cur.fetchone()
            if not row:
                continue
            for r in co["rounds"]:
                cur.execute("insert into rounds(company_id, t, year, month, stage, type, amount_eur_m, amount_raw, source) "
                            "values (%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id",
                            (row[0], r["t"], r["year"], r["month"], r["stage"], r["type"], r["amount_eur_m"],
                             None if r["amount_raw"] is None else str(r["amount_raw"]), Jsonb(r["raw"])))
                rid = cur.fetchone()[0]
                n_rounds += 1
                links = [(rid, k, "lead") for k in r["leads"] if k] + \
                        [(rid, k, "participant") for k in r["participants"] if k]
                cur.executemany("insert into round_investors values (%s,%s,%s) on conflict do nothing", links)
        conn.commit()
        counts = {t: cur.execute(f"select count(*) from {t}").fetchone()[0]
                  for t in ("companies", "investors", "rounds", "round_investors")}
    return counts


if __name__ == "__main__":
    print(load(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_ROUNDS))
