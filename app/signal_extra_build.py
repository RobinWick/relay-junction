"""Build app/signal_extra.json: the side data Recount Signal needs that is not in the snapshot.

Run locally: cd relay/app && python3 signal_extra_build.py   (stdlib, local files only, 0 Cala calls)

The Modal image only ships relay/app, while the sector tags, discovery text, cohorts and the expansion people file
live in the wider repo (cala/, signal/data/load.py). This script folds them into one committed file:

  sectors       {ckey: [Cala sector tag]}   from cached 'industry=<Sector>' discovery answers (Cala returned the company
                                            for that slice; not a verified classification)
  text_sector   {ckey: [free text]}         sector, industry, focus, description fields of discovery rows (max 3, 160 chars)
  cohorts       {ckey: [{employer, evidence, founder}]}  employer cohorts; evidence 'worked_at' or 'query_match_only'
  exits         acquisition receipts of both exit files (relay/app/exits.json, cala/expansion/exits.json)
  checked_funds fund keys whose exits were looked up (outside this set: "not checked", never "no exit")
  founders      merged people.json (22) + expansion people (211); same name + shared company merged, flagged
Nothing is imputed: a missing field stays missing.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "signal" / "data"))

import load  # noqa: E402  (signal/data/load.py, local files only)

OUT = HERE / "signal_extra.json"
TEXT_FIELDS = ("sector", "industry", "sub_sector", "focus", "description")


def _sectors(snap_ckeys: set[str]) -> dict[str, list[str]]:
    return {ck: sorted({t["sector"] for t in tags}) for ck, tags in load.cala_sector_tags().items() if ck in snap_ckeys}


def _text_sector(snap_ckeys: set[str]) -> dict[str, list[str]]:
    out = {}
    for ck, rows in load.discovery_rows().items():
        if ck not in snap_ckeys:
            continue
        vals = []
        for row in rows:
            for k in TEXT_FIELDS:
                v = (row.get("row") or {}).get(k)
                if isinstance(v, str) and v.strip() and v.strip() not in ("-", "\u2014", "n/a", "N/A"):
                    v = v.strip()[:160].replace("\u2014", ",").replace("\u2013", " to ")
                    if v not in vals:
                        vals.append(v)
        if vals:
            out[ck] = vals[:3]
    return out


def _cohorts(snap_ckeys: set[str]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for ck, rows in load._cohorts().items():
        if ck in snap_ckeys:
            out[ck] = [{"employer": r["employer"], "evidence": r.get("evidence"), "founder": r.get("founder"),
                        "founded_year": r.get("founded_year")} for r in rows]
    return out


def _founders() -> list[dict]:
    merged: dict[tuple, dict] = {}
    order: list[tuple] = []
    for f in load.load_founders():
        name = f["name"].strip()
        bases = f.get("link_basis") or []
        roles = [{"org": r.get("org"), "role": r.get("role"), "since": r.get("since"), "until": r.get("until")}
                 for r in f.get("roles") or []]
        founded = [{"org": x.get("org"), "org_id": x.get("org_id")} for x in f.get("founded") or []]
        exits = [x if isinstance(x, (str, int, float)) else {k: x.get(k) for k in ("company", "acquirer", "year", "date")
                                                              if k in x} for x in f.get("prior_exits") or []]
        twin = any("twin" in (b or "") for b in bases)
        key = None
        for k in order:  # same name and a shared company: one person
            if k[0] == name.lower() and set(merged[k]["ckeys"]) & set(f["ckeys"]):
                key = k
                break
        if key is None:
            key = (name.lower(), f["id"])
            order.append(key)
            merged[key] = {"id": f["id"], "name": name, "ckeys": [], "roles": [], "founded": [], "prior_exits": [],
                           "description": (f.get("description") or "")[:300] or None, "files": [], "twin_link": False,
                           "link_basis": [], "merged_duplicate": False}
        else:
            merged[key]["merged_duplicate"] = True
        m = merged[key]
        m["files"] = sorted(set(m["files"]) | {f["file"]})
        m["ckeys"] = list(dict.fromkeys(m["ckeys"] + list(f["ckeys"])))
        m["roles"] += [r for r in roles if r not in m["roles"]]
        m["founded"] += [x for x in founded if x not in m["founded"]]
        m["prior_exits"] += [x for x in exits if x not in m["prior_exits"]]
        m["twin_link"] = m["twin_link"] or twin
        m["link_basis"] = sorted(set(m["link_basis"]) | {b for b in bases if b})
    return [merged[k] for k in order]


def _exits() -> list[dict]:
    keep = ("fund_key", "company", "ckey", "event_type", "date", "year", "value_usd", "acquirers", "file")
    return [{k: e.get(k) for k in keep} for e in load.exit_events()]


def _checked_funds() -> list[str]:
    app = load._json(load.EXITS_APP) or {"funds": {}}
    exp = load._json(load.EXITS_EXP) or {"exits": {}}
    return sorted(set(app["funds"]) | set(exp["exits"]))


def build() -> dict:
    snap = load.load_snapshot()
    ckeys = {r["ckey"] for r in snap["rounds"]}
    out = {"built_from_snapshot": snap["version"],
           "sources": ["cala/cache/api (industry discovery answers)", "cala/data/companies.json",
                       "cala/expansion/cohorts.json", "relay/app/people.json", "cala/expansion/people.json"],
           "sectors": _sectors(ckeys), "text_sector": _text_sector(ckeys), "cohorts": _cohorts(ckeys),
           "founders": _founders(), "exits": _exits(), "checked_funds": _checked_funds()}
    return out


if __name__ == "__main__":
    d = build()
    OUT.write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
    print({k: len(v) for k, v in d.items() if isinstance(v, (dict, list))}, f"{OUT.stat().st_size // 1024} KB")
