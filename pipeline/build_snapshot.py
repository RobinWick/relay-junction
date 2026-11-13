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

sys.path.insert(0, str(Path(__file__).parent))
from normalize import parse_amount_eur, parse_date, split_investors, stage_of, investor_key  # noqa: E402

DATA = Path(os.environ.get("RELAY_DATA_DIR", Path(__file__).resolve().parents[2] / "cala" / "data"))
TRUTHY = {"true", "yes", "y", "1", "led", "co-led", "lead"}
NON_EQUITY = re.compile(r"grant|debt|loan|prize|award|ipo|listing|subsid|convertible note|crowdfund", re.I)


def canon(name: str) -> str:
    """One key per fund: 'Point Nine Capital' and 'Point Nine' collapse; legal suffixes are dropped."""
    key = investor_key(name)
    core = re.sub(r"\b(ventures?|venture partners|capital|vc|partners|management)\b", "", key)
    core = re.sub(r"\s+", " ", core).strip()
    return core or key


def company_key(name: str) -> str:
    s = re.sub(r"\(.*?\)", "", str(name).lower())
    s = re.sub(r"\b(oy|ab|as|gmbh|ltd|inc|sa|bv|aps|oyj|plc)\b", "", s)
    return re.sub(r"[^a-z0-9]", "", s)


def _field(row: dict, *names: str):
    for n in names:
        if row.get(n) not in (None, "", []):
            return row[n]
    return None


def _led_flag(row: dict):
    for k, v in row.items():
        kl = k.lower()
        if kl.endswith("_led") or kl in ("led", "fund_led", "led_round", "is_lead") or (kl.startswith("led_by") and "investor" not in kl):
            if v is None:
                return None
            if isinstance(v, bool):
                return v
            s = str(v).strip().lower()
            if s.startswith(("yes", "true", "co-led", "led")):
                return True
            if s.startswith(("no", "false")):
                return False
    return None


class Builder:
    def __init__(self) -> None:
        self.rounds: list[dict] = []
        self.by_company: dict[str, list[int]] = defaultdict(list)
        self.names: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    def _name(self, raw: str) -> str:
        k = canon(raw)
        self.names[k][raw.strip()] += 1
        return k

    def _find(self, ckey: str, stage: str | None, t: float) -> int | None:
        best = None
        for idx in self.by_company.get(ckey, []):
            r = self.rounds[idx]
            if abs(r["t"] - t) <= 0.17 and (stage is None or r["stage"] is None or r["stage"] == stage):
                if best is None or abs(r["t"] - t) < abs(self.rounds[best]["t"] - t):
                    best = idx
        return best

    def add(self, *, company: str, country, when, type_, amount, leads, parts, path, query, raw) -> int | None:
        if not company or not when:
            return None
        if type_ and NON_EQUITY.search(str(type_)):
            return None
        t = when[0] + (when[1] - 1) / 12
        ckey = company_key(company)
        stage = stage_of(type_)
        lead_keys = {self._name(n) for n in leads}
        part_keys = {self._name(n) for n in parts} - lead_keys
        idx = self._find(ckey, stage, t)
        src = {"path": path, "query": query, "row": raw}
        if idx is None:
            self.rounds.append({
                "id": len(self.rounds), "company": company.strip(), "ckey": ckey, "country": country,
                "t": round(t, 3), "year": when[0], "month": when[1], "stage": stage, "type": type_,
                "amount_eur_m": parse_amount_eur(amount), "amount_raw": None if amount is None else str(amount),
                "leads": sorted(lead_keys), "participants": sorted(part_keys), "sources": [src],
            })
            self.by_company[ckey].append(len(self.rounds) - 1)
            return len(self.rounds) - 1
        r = self.rounds[idx]
        r["leads"] = sorted(set(r["leads"]) | lead_keys)
        r["participants"] = sorted((set(r["participants"]) | part_keys) - set(r["leads"]))
        r["stage"] = r["stage"] or stage
        r["amount_eur_m"] = r["amount_eur_m"] or parse_amount_eur(amount)
        r["country"] = r["country"] or country
        r["sources"].append(src)
        return idx

    def company_first(self) -> None:
        for line in (DATA / "histories.jsonl").open():
            rec = json.loads(line)
            q = ("List every funding round of {} with announcement date, round type, amount, lead investor and all "
                 "participating investors").format(rec["name"])
            for row in rec["rounds"]:
                self.add(company=rec["name"], country=rec["country"],
                         when=parse_date(_field(row, "date", "announcement_date", "announced", "year")),
                         type_=_field(row, "round_type", "type", "round"),
                         amount=_field(row, "amount", "amount_raised", "size"),
                         leads=split_investors(_field(row, "lead_investor", "lead_investors", "lead")),
                         parts=split_investors(_field(row, "participating_investors", "all_participating_investors",
                                                      "investors", "participants", "other_investors")),
                         path="company_first", query=q, raw=row)

    def investor_first(self) -> int:
        n = 0
        path = DATA / "funds.jsonl"
        if not path.exists():
            return 0
        for line in path.open():
            rec = json.loads(line)
            fund_name = rec["name"]
            for q in rec["queries"]:
                for row in q["rows"]:
                    company = _field(row, "company", "company_name", "startup", "name")
                    leads = split_investors(_field(row, "lead_investor", "lead_investors", "lead"))
                    parts = split_investors(_field(row, "participating_investors", "all_participating_investors",
                                                   "investors", "other_investors"))
                    flag = _led_flag(row)
                    fund_in_leads = any(canon(x) == canon(fund_name) for x in leads)
                    if flag is True and not fund_in_leads:
                        leads.append(fund_name)
                    elif flag is not True and not fund_in_leads:
                        parts.append(fund_name)
                    idx = self.add(company=company, country=_field(row, "country", "company_country"),
                                   when=parse_date(_field(row, "announcement_date", "date", "announced")),
                                   type_=_field(row, "round_type", "type", "round"),
                                   amount=_field(row, "amount", "amount_raised"), leads=leads, parts=parts,
                                   path="investor_first", query=q["q"], raw=row)
                    if idx is not None and flag is False and canon(fund_name) in self.rounds[idx]["leads"]:
                        # the fund's own answer says it did not lead: trust the investor-first flag
                        r = self.rounds[idx]
                        r["leads"] = [k for k in r["leads"] if k != canon(fund_name)]
                        r["participants"] = sorted(set(r["participants"]) | {canon(fund_name)})
                    n += 1
        return n

    def snapshot(self, fund_keys: set[str]) -> dict:
        names = {k: max(v.items(), key=lambda kv: kv[1])[0] for k, v in self.names.items()}
        for r in self.rounds:
            paths = {s["path"] for s in r["sources"]}
            r["query_path"] = "both" if len(paths) > 1 else paths.pop()
        companies = len({r["ckey"] for r in self.rounds})
        return {
            "version": datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"),
            "retrieved": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "rounds": self.rounds, "investor_names": names, "fund_keys": sorted(fund_keys),
            "stats": {"rounds": len(self.rounds), "companies": companies, "funds_queried": len(fund_keys),
                      "investors": len(names)},
        }


def build() -> dict:
    b = Builder()
    b.company_first()
    b.investor_first()
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
