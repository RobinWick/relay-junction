"""People and career facts from the Cala entity graph, for the founder career view.

Ethics rules this module follows (and the tests pin down):
- No quality or "best founder" score, no ranking of people by predicted success. Every number is a plain fact
  computed from dated Cala edges (tenure, employers, title level changes) with a neutral label, so it can be
  shown, filtered and charted, never sorted into a verdict.
- Every person carries the data source (Cala entity id, fetch date, per-edge source URL and date).
- Missing data is reported as a gap, never read as "no". Name collisions are flagged, not resolved silently.
- Cohort patterns are descriptive counts over this sample only, each with its n.

Pure functions: fetch_people.py passes in the raw cached responses, so tests need no network.
"""
from __future__ import annotations

import re
from statistics import median
from typing import Optional

PROVIDER = "Cala entity graph (api.cala.ai/v1/entities)"
QL_PROVIDER = "Cala knowledge query (api.cala.ai/v1/knowledge/query), rows carry no source URLs"
SNAPSHOT_DATE = "2026-11-14"
NOW_YEAR = 2026.87  # 14 Nov 2026, same clock as engine.Snapshot.now_t

# Title levels, highest match wins. A coarse, documented mapping of job titles; it says nothing about the person.
LEVELS = [
    (4, "Founder, C-level or partner",
     r"\b(co-?founder|founder|chief|ceo|cto|cfo|coo|cpo|cmo|cso|cco|partner|owner|president|managing director|"
     r"toimitusjohtaja|vd)\b"),
    (3, "Director, head or VP", r"\b(director|head|vp|vice president|general manager|gm)\b"),
    (2, "Senior, lead or manager", r"\b(senior|sr|lead|manager|principal|staff|product owner|team lead)\b"),
    (1, "Associate, engineer or specialist",
     r"\b(associate|engineer|developer|consultant|specialist|scientist|researcher|designer|analyst ii|"
     r"programmer|architect|officer|advisor|adviser)\b"),
    (0, "Intern, trainee or analyst", r"\b(intern|internship|trainee|student|analyst|assistant|junior|jr)\b"),
]
LEVEL_LABEL = {lvl: label for lvl, label, _ in LEVELS}

# Background tags: plain employer lists, matched on the employer name Cala gives. Each list states its source.
TAGS = {
    "consulting": {
        "label": "Management consulting",
        "names": ["mckinsey", "boston consulting", "bcg", "bain", "accenture", "deloitte", "pwc",
                  "pricewaterhouse", "ernst & young", "kpmg", "oliver wyman", "roland berger", "kearney",
                  "capgemini invent", "arthur d. little"],
        "source": "Hand list: MBB (McKinsey, BCG, Bain), the Big Four audit firms and other large strategy "
                  "firms. Not exhaustive.",
    },
    "big_tech": {
        "label": "Big tech",
        "names": ["google", "alphabet", "deepmind", "microsoft", "apple", "amazon", "aws", "meta platforms",
                  "facebook", "netflix", "nvidia", "intel", "ibm", "oracle", "sap", "salesforce", "samsung", "uber"],
        "source": "Hand list of the largest listed technology companies by market value. Not exhaustive.",
    },
    "nordic_unicorn": {
        "label": "Nordic unicorn alumni",
        "names": ["supercell", "rovio", "wolt", "spotify", "klarna", "skype", "king.com", "king digital", "mojang",
                  "izettle", "zettle", "kahoot", "northvolt", "trustly", "tink", "aiven", "oura", "relex", "kry",
                  "voi technology", "truecaller", "epidemic sound", "pleo", "trustpilot", "zendesk", "unity",
                  "smartly", "iqm", "lovable", "einride", "bolt", "wise", "pipedrive", "veriff"],
        "source": "Nordic and Baltic companies that reached a USD 1bn valuation, from Wikipedia's List of unicorn "
                  "startup companies (https://en.wikipedia.org/wiki/List_of_unicorn_startup_companies) and company "
                  "press releases. Hand list as of Nov 2026, includes companies that later exited or listed. "
                  "Not verified entry by entry in this lane.",
    },
    "nordic_incumbent": {
        "label": "Nokia or Ericsson",
        "names": ["nokia", "ericsson"],
        "source": "The two large Nordic telecom equipment makers. Hand list.",
    },
    "research": {
        "label": "University or research lab",
        "names": ["university", "yliopisto", "universitet", "institute of technology", "vtt", "cern", "max planck",
                  "research institute", "aalto", "kth", "dtu", "ntnu", "chalmers", "karolinska", "csc"],
        "source": "Employer name contains a university or public research lab name. Keyword list.",
    },
    "finance": {
        "label": "Investment banking or investing",
        "names": ["goldman sachs", "morgan stanley", "j.p. morgan", "jp morgan", "jpmorgan", "lazard", "rothschild",
                  "nordea markets", "carnegie", "ventures", "capital partners", "private equity"],
        "source": "Global investment banks and employers whose name says ventures or private equity. Keyword list.",
    },
}

# Sources that, in probes, attached facts about other people with the same name (see cala-capability.md).
COLLISION_DOMAINS = ("transfermarkt", "worldfootball", "fandom.com", "imdb.com", "wikitree", "findagrave",
                     "soccerway", "eliteprospects", "discogs")


# ---------- raw edge helpers ----------

def _edges(entity: dict, side: str, rel: str) -> list[dict]:
    return ((entity.get("relationships") or {}).get(side) or {}).get(rel) or []


def _prop(entity: dict, name: str) -> Optional[str]:
    p = (entity.get("properties") or {}).get(name)
    return p.get("value") if isinstance(p, dict) else None


def _sources(edge_props: dict) -> list[dict]:
    out = []
    for s in edge_props.get("sources") or []:
        url = s.get("document") if isinstance(s.get("document"), str) else ""
        out.append({"name": s.get("name") or "", "url": url or "", "date": s.get("date") or "",
                    "rank": s.get("source_rank") or ""})
    return out


def year_of(date: Optional[str]) -> Optional[float]:
    """'2015-07-01' -> 2015.5; None or junk -> None."""
    m = re.match(r"^(\d{4})(?:-(\d{2}))?", date or "")
    if not m:
        return None
    return int(m.group(1)) + ((int(m.group(2)) - 1) / 12 if m.group(2) else 0)


def level(role: str) -> Optional[int]:
    text = (role or "").lower()
    for lvl, _label, pattern in LEVELS:
        if re.search(pattern, text):
            return lvl
    return None


def tags_for(org: str) -> list[str]:
    name = (org or "").lower()
    return [t for t, spec in TAGS.items() if any(re.search(rf"(^|\W){re.escape(n)}(\W|$)", name) for n in spec["names"])]


# ---------- selection helpers used by fetch_people.py ----------

def founder_candidates(company: dict) -> list[tuple[str, str]]:
    """(person id, name) of a company's founders: FOUNDED edges first, then WORKS_AT roles that say founder."""
    out, seen = [], set()
    for e in _edges(company, "incoming", "FOUNDED"):
        if e.get("entity_type") == "Person" and e["id"] not in seen:
            seen.add(e["id"])
            out.append((e["id"], e.get("name") or ""))
    for e in _edges(company, "incoming", "WORKS_AT"):
        role = ((e.get("properties") or {}).get("role") or "").lower()
        if e.get("entity_type") == "Person" and "founder" in role and e["id"] not in seen:
            seen.add(e["id"])
            out.append((e["id"], e.get("name") or ""))
    return out


def earlier_founded(person: dict, skip_ids: set[str], skip_names: frozenset = frozenset()) -> list[tuple[str, str]]:
    """(company id, name) of companies this person founded other than the sample companies.

    Cala holds duplicate entities for one company (Lovable as both Organization and Company), so a founded
    entity whose squashed name equals a sample company's name is the same company, not an earlier one.
    """
    out: list[tuple[str, str]] = []
    founded = [(e["id"], e.get("name") or "") for e in _edges(person, "outgoing", "FOUNDED")
               if e.get("entity_type") in ("Company", "Organization")]
    via_role = [(e["id"], e.get("name") or "") for e in _edges(person, "outgoing", "WORKS_AT")
                if "founder" in ((e.get("properties") or {}).get("role") or "").lower()]
    for cid, name in founded + via_role:
        if cid in skip_ids or _squash(name) in skip_names or any(o[0] == cid for o in out):
            continue
        if any(_squash(o[1]) == _squash(name) for o in out):
            continue
        out.append((cid, name))
    return out


# ---------- per person ----------

def roles(person: dict) -> list[dict]:
    """Every WORKS_AT edge as a timeline row, oldest first; undated rows last."""
    rows = []
    for e in _edges(person, "outgoing", "WORKS_AT"):
        p = e.get("properties") or {}
        since, until = p.get("valid_since"), p.get("valid_until")
        y0, y1 = year_of(since), year_of(until)
        lvl = level(p.get("role") or "")
        rows.append({
            "org": e.get("name") or "", "org_id": e.get("id") or "", "role": p.get("role") or "",
            "level": lvl, "level_label": LEVEL_LABEL.get(lvl, "Not mapped"),
            "since": since, "until": until,
            "years": round(y1 - y0, 1) if y0 is not None and y1 is not None and y1 >= y0 else None,
            "open": y0 is not None and y1 is None,
            "tags": tags_for(e.get("name") or ""), "sources": _sources(p),
        })
    return sorted(rows, key=lambda r: (year_of(r["since"]) is None, year_of(r["since"]) or 0, r["org"]))


def merge_roles(rows: list[dict]) -> list[dict]:
    """Cala keeps one organisation under several entities ('CERN' and its Spanish name, 'Sana Labs' and
    'Sana Labs AB'), so one job can arrive as several edges. Keep each dated role once (org, title, start). An undated
    row is the same job when its org already has a row whose title contains its title ('CEO' in 'Co-Founder & CEO'),
    or when it has no title and its org already has a row; a row with a title wins over one without. A different
    undated title at the same org (a later CPO role with no start date) stays. Every count and gap is computed over
    the merged rows, so they agree with each other."""
    dated, seen = [], set()
    for r in rows:
        if r["since"]:
            key = (org_key(r["org"]), (r["role"] or "").lower(), r["since"])
            if key not in seen:
                seen.add(key)
                dated.append(r)
    titles: dict[str, list[str]] = {}
    for r in dated:
        titles.setdefault(org_key(r["org"]), []).append((r["role"] or "").lower())
    undated = [r for r in rows if not r["since"]]
    kept = []
    for r in sorted(undated, key=lambda r: not r["role"]):  # titled rows first, so they win
        k, t = org_key(r["org"]), (r["role"] or "").lower()
        have = titles.setdefault(k, [])
        if (t and any(t in x for x in have)) or (not t and (have or any(org_key(x["org"]) == k for x in kept))):
            continue
        have.append(t)
        kept.append(r)
    order = {id(r): i for i, r in enumerate(rows)}
    return dated + sorted(kept, key=lambda r: order[id(r)])


def _n(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def level_changes(rows: list[dict]) -> dict:
    """Title level changes between consecutive dated roles. Up and down are both counted, with dates."""
    dated = [r for r in rows if year_of(r["since"]) is not None and r["level"] is not None]
    ups, downs, steps = 0, 0, []
    for a, b in zip(dated, dated[1:]):
        if b["level"] > a["level"]:
            ups += 1
            steps.append({"from": a["role"], "to": b["role"], "at": b["since"], "org": b["org"], "dir": "up"})
        elif b["level"] < a["level"]:
            downs += 1
            steps.append({"from": a["role"], "to": b["role"], "at": b["since"], "org": b["org"], "dir": "down"})
    span = (year_of(dated[-1]["since"]) - year_of(dated[0]["since"])) if len(dated) >= 2 else None
    return {"level_ups": ups, "level_downs": downs, "steps": steps, "dated_roles": len(dated),
            "span_years": round(span, 1) if span is not None else None,
            # per year only when the dated span is at least a year, else the ratio is noise
            "level_ups_per_year": round(ups / span, 2) if span and span >= 1 else None}


def person_record(raw: dict, home: list[str], company_ids: dict[str, str], exits: dict[str, dict],
                  same_name: int, home_names_of: Optional[list[str]] = None) -> dict:
    """One person: timeline, metrics, tags, prior founding and exits, gaps. No score."""
    ent = raw["response"]
    all_rows = roles(ent)
    rows = merge_roles(all_rows)
    home_ids = {company_ids[k] for k in home if k in company_ids}
    home_names = frozenset(home_names_of or [])
    # Cala keeps duplicate entities of one company: an edge to an entity with the home company's name is home too
    home_ids |= {r["org_id"] for r in all_rows if _squash(r["org"]) in home_names}
    home_ids |= {e["id"] for e in _edges(ent, "outgoing", "FOUNDED") if _squash(e.get("name") or "") in home_names}
    founded = [{"org": e.get("name") or "", "org_id": e["id"], "sample": e["id"] in home_ids,
                "sources": _sources(e.get("properties") or {})} for e in _edges(ent, "outgoing", "FOUNDED")]
    closed = [r["years"] for r in rows if r["years"] is not None]
    # distinct by name, since one organisation can sit behind several Cala entity ids
    employers = {org_key(r["org"]) for r in rows} | {org_key(f["org"]) for f in founded}
    changes = level_changes(rows)

    home_starts = [year_of(r["since"]) for r in rows if r["org_id"] in home_ids and year_of(r["since"]) is not None]
    first_start = min((year_of(r["since"]) for r in rows
                       if r["org_id"] not in home_ids and year_of(r["since"]) is not None), default=None)
    before = (round(min(home_starts) - first_start, 1)
              if home_starts and first_start is not None and first_start <= min(home_starts) else None)
    outside = [r for r in rows if r["org_id"] not in home_ids]

    tag_evidence: dict[str, list[str]] = {}
    for r in outside:  # background tags come from roles outside the company itself
        for t in r["tags"]:
            tag_evidence.setdefault(t, [])
            if r["org"] not in tag_evidence[t]:
                tag_evidence[t].append(r["org"])

    role_of = {r["org_id"]: r["role"] for r in rows if "founder" in r["role"].lower()}
    other_founded = [{"org": name, "org_id": cid, "via_role": role_of.get(cid)}
                     for cid, name in earlier_founded(ent, home_ids, home_names)]
    prior_exits, exit_checked = [], []
    for f in other_founded:
        ex = exits.get(f["org_id"])
        if ex is None:
            continue
        exit_checked.append(f["org"])
        prior_exits += exit_events(ex["response"], f["org"])

    gaps = []
    if not rows:
        gaps.append("No WORKS_AT edges in Cala")
    undated = sum(1 for r in rows if not r["since"])
    if undated:
        gaps.append(f"{undated} of {_n(len(rows), 'role', 'roles')} {'has' if undated == 1 else 'have'} no start date")
    no_end = sum(1 for r in rows if r["since"] and not r["until"])
    if no_end:
        gaps.append(f"{_n(no_end, 'dated role has', 'dated roles have')} no end date (current, or end unknown)")
    if not (home_ids & ({r["org_id"] for r in all_rows} | {f["org_id"] for f in founded})):
        gaps.append("Record does not link back to the company it was found through: possible name collision")
    bad = sorted({s["name"] for r in all_rows for s in r["sources"] if any(d in s["url"] for d in COLLISION_DOMAINS)})
    if bad:
        gaps.append("Some sources look like other people with the same name: " + ", ".join(bad))
    if same_name > 1:
        gaps.append(f"{same_name} Cala person entities in this sample share this name")
    if other_founded and len(exit_checked) < len(other_founded):
        gaps.append("Exit check not run for every other company founded (call budget)")
    for org in exit_checked:
        if not any(x["org"] == org for x in prior_exits):
            gaps.append(f"{org}: no acquisition event in Cala. Absence in Cala is not proof there was none")

    return {
        "id": ent.get("id") or "", "name": ent.get("name") or _prop(ent, "name") or "",
        "description": ent.get("description") or _prop(ent, "description") or "",
        "linkedin_url": _prop(ent, "linkedin_url") or "",
        "companies": home,
        "source": {"provider": PROVIDER, "entity_id": ent.get("id") or "", "fetched": raw.get("fetched") or "",
                   "note": "Career edges as Cala holds them; each role lists its own source URL and date."},
        "roles": rows,
        "founded": founded,
        "metrics": {
            "employers": len(employers),
            "roles": len(rows),
            "roles_outside_company": len(outside),
            "roles_dated": changes["dated_roles"],
            "avg_tenure_years": round(sum(closed) / len(closed), 1) if closed else None,
            "avg_tenure_n": len(closed),
            "shortest_tenure_years": min(closed) if closed else None,
            "longest_tenure_years": max(closed) if closed else None,
            "level_ups": changes["level_ups"],
            "level_downs": changes["level_downs"],
            "level_ups_per_year": changes["level_ups_per_year"],
            "dated_span_years": changes["span_years"],
            "career_start": min((r["since"] for r in rows if r["since"]), default=None),
            "years_before_company": before,
        },
        "level_steps": changes["steps"],
        "tags": sorted(tag_evidence),
        "tag_evidence": tag_evidence,
        "prior_founder": {"value": bool(other_founded),
                          "companies": [{"org": f["org"], "org_id": f["org_id"],
                                         "via": f.get("via_role") or "FOUNDED edge"} for f in other_founded]},
        "prior_exits": prior_exits,
        "prior_exit_checked": exit_checked,
        "gaps": gaps,
    }


def exit_events(ent: dict, org: str) -> list[dict]:
    """MNA_COMPLETED events where the company was the target, with date and source."""
    out = []
    for e in _edges(ent, "outgoing", "PARTICIPATES_IN_CORPORATE_EVENT"):
        p = e.get("properties") or {}
        if e.get("name") == "MNA_COMPLETED" and (p.get("role") or "").upper() == "TARGET":
            out.append({"org": org, "event": "Acquired", "date": p.get("event_date") or "",
                        "event_id": e.get("id") or "", "sources": _sources(p)})
    return out


# ---------- per company ----------

def company_record(ckey: str, raw: Optional[dict], entity_id: str, rounds: list[dict]) -> dict:
    mine = sorted((r for r in rounds if r.get("ckey") == ckey), key=lambda r: r.get("t") or 0)
    base = {"ckey": ckey, "entity_id": entity_id,
            "name": mine[0]["company"] if mine else ckey, "country": mine[0].get("country") if mine else None,
            "rounds": [{"year": r.get("year"), "month": r.get("month"), "stage": r.get("stage"),
                        "amount_eur_m": r.get("amount_eur_m"), "leads": r.get("leads") or []} for r in mine]}
    if raw is None:
        return base | {"fetched": None, "founders": [], "founder_source": None,
                       "gaps": ["Company not fetched from Cala (call budget)"]}
    ent = raw["response"]
    via_founded = [pid for pid, _ in founder_candidates({"relationships": {"incoming": {
        "FOUNDED": _edges(ent, "incoming", "FOUNDED")}}})]
    all_cands = founder_candidates(ent)
    gaps = []
    if not via_founded:
        gaps.append("No FOUNDED edge in Cala" + ("; founders taken from WORKS_AT roles that say founder"
                                                  if all_cands else ""))
    cala_name = ent.get("name") or ""
    if cala_name and base["name"] and _squash(cala_name)[:5] != _squash(base["name"])[:5]:
        gaps.append(f"Cala entity is named '{cala_name}': check it is the same company")
    return base | {"fetched": raw.get("fetched"), "cala_name": cala_name,
                   "description": ent.get("description") or "",
                   "founders": [pid for pid, _ in all_cands],
                   "founder_names": {pid: n for pid, n in all_cands},
                   "founder_source": "FOUNDED" if via_founded else ("WORKS_AT role" if all_cands else None),
                   "exits": exit_events(ent, cala_name or base["name"]),
                   "gaps": gaps}


def _squash(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


LEGAL_SUFFIX = r"\b(oy|oyj|ab|publ|as|asa|aps|a/s|gmbh|ltd|limited|inc|llc|bv|sa|sas|plc)\b\.?"


def org_key(name: str) -> str:
    """One key per organisation across Cala's duplicate entities: 'Sana Labs AB' = 'Sana Labs', and
    'Organización Europea ... (CERN)' = 'CERN' (a parenthesised acronym wins)."""
    m = re.search(r"\(([A-Z][A-Z0-9&]{1,9})\)", name or "")
    if m:
        return m.group(1).lower()
    return _squash(re.sub(LEGAL_SUFFIX, "", (name or "").lower()))


# ---------- QL cohorts ----------

COHORT_ALIASES = {"bcg": ["bcg", "boston consulting"], "mckinsey": ["mckinsey"], "bain": ["bain"]}
WORKED_WORDS = r"(ex-|former|formerly|alumn|quit|left|previously|veteran|co-?founder|vp |head of|engineer|manager|" \
               r"developer|scientist|consultant|\d{4}\s*[-–]\s*\d{2,4})"


def _first(row: dict, *keys: str) -> str:
    for k in keys:
        if row.get(k) not in (None, ""):
            return str(row[k])
    return ""


def cohort_relation(employer: str, row: dict) -> tuple[str, str]:
    """How the row's own text ties the company to the employer: worked_at_stated, funded_by, sold_to or listed_only.

    The QL `previous_job=` filter returns founders who worked at the employer mixed with companies the employer
    funded (probe q02). Only the row's own words decide; a row that states no tie is 'listed_only'.
    """
    names = COHORT_ALIASES.get(employer.lower(), [employer.lower()])
    funding = _first(row, "funding", "investors", "backers").lower()
    people_text = " ".join([_first(row, "founders", "founder"), _first(row, "description", "note", "focus")]).lower()
    for n in names:
        sold = re.search(rf"sold [^.;]* to {re.escape(n)}", people_text)
        if sold:
            return "sold_to", sold.group(0)[:160]
    for n in names:
        for sentence in re.split(r"(?<=[.;)])\s+|,\s+(?=[A-Z])", people_text):
            if n in sentence and re.search(WORKED_WORDS, sentence):
                return "worked_at_stated", sentence.strip()[:160]
    for n in names:
        if n in funding or re.search(rf"(investment|funding|backed|backing|invested) (from|by) {re.escape(n)}",
                                     people_text):
            return "funded_by", (funding or people_text)[:160]
    return "listed_only", ""


def cohort_record(employer: str, raw: Optional[dict], snapshot_ckeys: dict[str, list[dict]]) -> dict:
    """A QL cohort, each row tagged by how its own text ties it to the employer, joined to our snapshot rounds."""
    if raw is None:
        return {"employer": employer, "fetched": None, "rows": [], "n": 0, "gaps": ["Query not run (call budget)"]}
    rows = []
    for r in raw["response"].get("results") or []:
        relation, evidence = cohort_relation(employer, r)
        company = _first(r, "name", "company")
        snap = snapshot_ckeys.get(_squash(company), [])
        rows.append({"company": company, "founded": _first(r, "founded_year", "year_founded", "founded") or None,
                     "founders": _first(r, "founders", "founder"),
                     "about": _first(r, "description", "sector", "focus"),
                     "location": _first(r, "location", "hq"),
                     "funding_text": _first(r, "funding"), "note": _first(r, "note", "status"),
                     "relation": relation, "evidence": evidence, "in_snapshot": bool(snap),
                     "snapshot_rounds": [{"year": x.get("year"), "stage": x.get("stage"),
                                          "amount_eur_m": x.get("amount_eur_m"), "leads": x.get("leads") or []}
                                         for x in sorted(snap, key=lambda x: x.get("t") or 0)]})
    count = lambda rel: sum(1 for r in rows if r["relation"] == rel)  # noqa: E731
    gaps = ["Rows are Cala QL output without source URLs: a stated prior job is a claim to check, not a fact",
            "The previous_job filter mixes founders who worked at the employer with companies it funded; each row "
            "is tagged by its own text: worked_at_stated, funded_by, sold_to or listed_only"]
    if not rows:
        gaps.append("Query returned no rows")
    return {"employer": employer, "query": (raw.get("body") or {}).get("input"), "fetched": raw.get("fetched"),
            "source": QL_PROVIDER, "rows": rows, "n": len(rows), "n_worked_at_stated": count("worked_at_stated"),
            "n_funded_by": count("funded_by"), "n_listed_only": count("listed_only"),
            "n_in_snapshot": sum(1 for r in rows if r["in_snapshot"]), "gaps": gaps}


# ---------- descriptive patterns ----------

def _share(people: list[dict], pred, label: str, note: str) -> dict:
    n = len(people)
    k = sum(1 for p in people if pred(p))
    return {"label": label, "count": k, "n": n, "share": round(k / n, 2) if n else None, "note": note}


def _med(people: list[dict], metric: str, label: str, note: str) -> dict:
    vals = [p["metrics"][metric] for p in people if p["metrics"].get(metric) is not None]
    return {"label": label, "median": round(median(vals), 2) if vals else None, "n": len(vals),
            "min": min(vals) if vals else None, "max": max(vals) if vals else None, "note": note}


def patterns(people: list[dict]) -> list[dict]:
    """Descriptive counts over the founders in this sample. Not a benchmark, not a prediction."""
    with_roles = [p for p in people if p["metrics"]["roles_outside_company"] or p["prior_founder"]["value"]]
    note = ("Founders in this sample whose Cala record shows any role or company outside the company they were "
            "found through; founders with no such record are not counted as 'no'")
    out = [_share(with_roles, lambda p, t=t: t in p["tags"], f"Worked at: {TAGS[t]['label']}", note) for t in TAGS]
    out.append(_share(with_roles, lambda p: p["prior_founder"]["value"], "Founded another company before or alongside",
                      note))
    out.append(_share(with_roles, lambda p: bool(p["prior_exits"]), "Another company they founded was acquired",
                      "Only checked where call budget allowed; see prior_exit_checked"))
    out += [
        _med(people, "years_before_company", "Years from first dated role to joining this company",
             "Only people with dated roles before and at the company"),
        _med(people, "avg_tenure_years", "Average tenure per closed role (years)", "Roles with start and end date"),
        _med(people, "employers", "Employers on record", "Distinct organisations in WORKS_AT and FOUNDED"),
        _med(people, "level_ups_per_year", "Title level changes up per year",
             "Dated span of at least one year; coarse title mapping"),
    ]
    return out


def coverage(comp: list[dict], people: list[dict], coh: list[dict]) -> dict:
    """How much of the sample Cala could fill: the honest denominator for every pattern above."""
    return {
        "companies_fetched": sum(1 for c in comp if c.get("fetched")),
        "companies_with_founder_edge": sum(1 for c in comp if c.get("founder_source") == "FOUNDED"),
        "founders_found": sum(len(c.get("founders") or []) for c in comp),
        "founders_fetched": len(people),
        "founders_with_any_role": sum(1 for p in people if p["roles"]),
        "founders_with_role_outside_company": sum(1 for p in people if p["metrics"]["roles_outside_company"]),
        "founders_with_dated_role": sum(1 for p in people if p["metrics"]["roles_dated"]),
        "cohort_rows": sum(k["n"] for k in coh),
        "cohort_rows_in_snapshot": sum(k.get("n_in_snapshot", 0) for k in coh),
        "cohort_rows_worked_at_stated": sum(k.get("n_worked_at_stated", 0) for k in coh),
        "note": "In-snapshot cohort matches are by company name only and may be a different company of the same name.",
    }


# ---------- top level ----------

def build(companies: dict[str, Optional[dict]], persons: dict[str, dict], exits: dict[str, dict],
          cohorts: dict[str, Optional[dict]], entities: dict[str, str], rounds: list[dict],
          calls_used: int = 0) -> dict:
    company_ids = {k: entities.get(f"c:{k}", "") for k in companies}
    comp = [company_record(k, raw, company_ids[k], rounds) for k, raw in companies.items()]
    home_of: dict[str, list[str]] = {}
    for c in comp:
        for pid in c["founders"]:
            home_of.setdefault(pid, []).append(c["ckey"])
    names = [(raw["response"].get("name") or "").strip().lower() for raw in persons.values()]
    people = []
    for pid, raw in persons.items():
        nm = (raw["response"].get("name") or "").strip().lower()
        homes = home_of.get(pid, [])
        hn = [_squash(c.get("cala_name") or c["name"]) for c in comp if c["ckey"] in homes]
        people.append(person_record(raw, homes, company_ids, exits, names.count(nm), hn))
    people.sort(key=lambda p: (p["companies"][:1], p["name"]))  # by company then name: never by any metric
    by_key: dict[str, list[dict]] = {}
    for r in rounds:
        by_key.setdefault(_squash(r.get("company") or ""), []).append(r)
    coh = [cohort_record(e, raw, by_key) for e, raw in cohorts.items()]
    for c in comp:  # cross-match: which cohort queries also returned this company, and how they tie it
        names = {_squash(c["name"]), _squash(c.get("cala_name") or "")} - {""}
        c["cohort_mentions"] = [{"employer": k["employer"], "relation": r["relation"], "evidence": r["evidence"]}
                                for k in coh for r in k["rows"] if _squash(r["company"]) in names]
    fetched = sorted({x for x in [p["source"]["fetched"] for p in people] + [c.get("fetched") for c in comp] if x})
    return {
        "generated": SNAPSHOT_DATE,
        "source": {"provider": "Cala", "graph": PROVIDER, "query": QL_PROVIDER, "calls_used": calls_used,
                   "fetched_from": fetched[0] if fetched else None, "fetched_to": fetched[-1] if fetched else None},
        "rules": ["No score or ranking of people. Metrics are facts from dated Cala edges with neutral labels.",
                  "Every person shows its Cala entity id, fetch date and the source of each role.",
                  "Missing dates and possible name collisions are listed as gaps, never filled in.",
                  "Patterns are descriptive counts over this sample with their n, not benchmarks."],
        "definitions": {
            "levels": [{"level": lvl, "label": label, "pattern": pat} for lvl, label, pat in LEVELS],
            "tags": TAGS,
            "metrics": {
                "employers": "Distinct organisations in the person's WORKS_AT and FOUNDED edges",
                "avg_tenure_years": "Mean of (valid_until minus valid_since) over roles that have both dates",
                "level_ups": "Times a dated role maps to a higher title level than the dated role before it",
                "level_ups_per_year": "level_ups divided by years between first and last dated role start; "
                                      "only when that span is at least one year",
                "years_before_company": "Years from the first dated role elsewhere to the first dated role at the "
                                        "company this person was found through",
                "roles_outside_company": "WORKS_AT edges to organisations other than the company the person was "
                                         "found through (background tags only use these)",
            },
        },
        "coverage": coverage(comp, people, coh),
        "companies": comp,
        "people": people,
        "cohorts": coh,
        "patterns": patterns(people),
    }
