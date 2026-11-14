"""Merge the exits lane cache (cala/expansion/raw/exits) into app/exits.json. No Cala calls.

Each fund's receipts are built by receipt_exits.build_fund, so every rule there holds (MNA_COMPLETED as TARGET,
INVESTED_IN link with a source, 6 year vintage gate, unit normalisation). On top, receipts that look wrong are
dropped and listed under "dropped" with the reason:
  - twin entities: the event lists more than one TARGET, or the same fund shows the same company (by name) twice
    within a year
  - IPO-like: the event reads as an IPO or listing, or the target was already a listed company (delisted,
    per-share price, take-private), so the venture stake was not sold in this deal
  - funding round stored as an acquisition
  - no buyer named on the event

Run: python3 pipeline/build_exits_expansion.py   (from relay/)
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
import receipt_exits as rx  # noqa: E402

LANE = ROOT.parent / "cala/expansion"
RAW = LANE / "raw/exits"
SNAPSHOT = ROOT.parent / "cala/data/snapshot.json"
OUT = ROOT / "app/exits.json"
TODAY = date(2026, 11, 14)
EXTRA_IDS = {"creandum": ["6ba00a20-2cb4-4559-8fe2-f39484a9e5f6"]}  # Creandum exists twice in Cala

IPO = re.compile(r"\b(ipo|initial public offering|went public|go public|going public|spac|direct listing)\b", re.I)
PUBLIC = re.compile(r"delist|take-private|taken private|per share|/share|\bnyse\b|nasdaq|\blse\b|stock exchange", re.I)
FUNDING = re.compile(r"\b(rais|funding round|series [a-f]\b|seed round|seed funding|investment round|financing|"
                     r"growth equity|capital injection|invest(ed|ment) in)", re.I)
ACQ = re.compile(r"acqui|merg|takeover|bought|purchase|buyout|took over", re.I)


def norm(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"\b(oy|ab|as|aps|inc|ltd|limited|gmbh|sa|bv|plc|llc|corp|corporation|group|holding|holdings|oyj)\b",
               "", s)
    return re.sub(r"[^a-z0-9]", "", s)


def raw(tag: str) -> dict | None:
    p = RAW / f"{tag}.json"
    if not p.exists():
        return None
    d = json.loads(p.read_text())
    return d.get("response") if d.get("status") == 200 else None


def fund_edges(ids: list[str]) -> list[dict]:
    edges = []
    for eid in ids:
        for page in sorted(RAW.glob(f"fund_{eid}_o*.json")):
            r = raw(page.stem)
            edges += (((r or {}).get("relationships") or {}).get("outgoing") or {}).get("INVESTED_IN") or []
    return edges


def why_suspicious(r: dict, event: dict | None) -> str | None:
    desc = r.get("description") or ""
    targets = [p for p in (((event or {}).get("relationships") or {}).get("incoming") or {})
               .get("PARTICIPATES_IN_CORPORATE_EVENT") or [] if (p.get("properties") or {}).get("role") == "TARGET"]
    if len({p.get("id") for p in targets}) > 1:
        return f"twin entities: event lists {len(targets)} TARGET participants"
    if IPO.search(desc) and not ACQ.search(desc):
        return "IPO-like: the event reads as an IPO or listing"
    if PUBLIC.search(desc):
        return "IPO-like: the target was already a listed company"
    if desc and FUNDING.search(desc) and not ACQ.search(desc):
        return "funding round stored as acquisition"
    if not r.get("acquirers"):
        return "no buyer named on the event"
    return None


def build() -> dict:
    snap = json.loads(SNAPSHOT.read_text())
    by_id = {v: k[2:] for k, v in snap["entities"].items() if k.startswith("i:")}
    fund_ids: dict[str, list[str]] = {}
    for p in RAW.glob("fund_*_o0.json"):
        eid = p.stem[len("fund_"):-len("_o0")]
        k = by_id.get(eid) or next((fk for fk, extra in EXTRA_IDS.items() if eid in extra), None)
        if k:
            fund_ids.setdefault(k, []).append(eid)
    old = rx.load(OUT)
    funds, dropped = {}, []
    for k, ids in sorted(fund_ids.items()):
        edges = fund_edges(ids)
        fund_raw = {"id": ids[0], "relationships": {"outgoing": {"INVESTED_IN": edges}}}
        companies = []
        for cid in dict.fromkeys(e["id"] for e in edges):
            comp = raw(f"co_{cid}")
            if not comp:
                continue
            evs = [raw(f"ev_{e['id']}") for e in rx.target_events(comp)]
            companies.append({"company": comp, "events": [e for e in evs if e]})
        if not companies:
            continue
        name = snap["investor_names"].get(k, k)
        f = rx.build_fund(k, name, ids, fund_raw, companies, TODAY)
        events = {c["company"]["id"]: {e["id"]: e for e in c["events"]} for c in companies}
        seen: dict[str, int] = {}
        for bucket in ("receipts", "undisclosed"):
            keep = []
            for r in f[bucket]:
                reason = why_suspicious(r, events.get(r["company_entity"], {}).get(r["event_entity"]))
                twin = seen.get(norm(r["company"] or ""))
                if twin is not None and abs(twin - r["year"]) <= 1:
                    reason = reason or "twin entities: same company acquired twice within a year for this fund"
                seen[norm(r["company"] or "")] = r["year"]
                if reason:
                    dropped.append({"fund": k, "company": r["company"], "date": r["date"],
                                    "event_entity": r["event_entity"], "reason": reason})
                    continue
                keep.append(r)
            f[bucket] = keep
        funds[k] = f
    for k, prev in (old.get("funds") or {}).items():
        funds.setdefault(k, prev)
    return {"version": 1, "built": TODAY.isoformat(), "caveat": rx.CAVEAT, "value_label": rx.VALUE_LABEL,
            "funds": funds, "dropped": dropped}


if __name__ == "__main__":
    out = build()
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    n = sum(len(f["receipts"]) + len(f["undisclosed"]) for f in out["funds"].values())
    with_any = [k for k, f in out["funds"].items() if f["receipts"] or f["undisclosed"]]
    print(f"wrote {OUT}: {n} receipts across {len(with_any)} funds ({len(out['funds'])} funds checked), "
          f"{len(out['dropped'])} dropped")
    for k in with_any:
        f = out["funds"][k]
        print(f"  {k}: {len(f['receipts'])} disclosed + {len(f['undisclosed'])} undisclosed")
    for d in out["dropped"]:
        print(f"  DROPPED {d['fund']} / {d['company']} {d['date']}: {d['reason']}")
