"""Shared-Round Intro Path: funds that lead at the founder's next stage and have already sat in a small round with
one of the founder's investors. Receipts only: the rounds, never a score, rate or probability.

Rules (research/patterns/DECISION.md #1, research/patterns/warm-path-stress.md):
  A shared round is an equity round with 2 to 6 named investors, at most 50M EUR (unknown amount allowed, as in
  engine.tie), dated in the last 4 years, not the founder's own company, not disputed, not a programme cheque or
  non-equity round, and not a round whose date looks defaulted (year only, quarter, or a June with no June in the text).
  Company aliases (IQM / IQM Quantum Computers, Leya / Legora) and same-round echoes are merged before any count.
  A round is "confirmed" when one company-first Cala row names both funds, or two independent sources each name both.
  Otherwise it is "one_sided" and ranks below every confirmed tie.
  Suggested funds must lead at the next stage by engine.fund_profile (verdict "leads" or "leads_size").
  Order: confirmed shared companies, then all shared companies, then the most recent shared round, then rounds led at
  the next stage. The order is a sort, not a score, and no number for it is returned.
Pure functions over an engine.Snapshot: no network, no Cala calls.
"""
from __future__ import annotations

import re

from engine import STAGE_LABEL, STAGES, WINDOW_YEARS, Snapshot, fund_profile, round_brief
from merge import NON_EQUITY, _compact, _date_precision, _same_family, canon, company_key, split_investors

MIN_INVESTORS, MAX_INVESTORS, MAX_AMOUNT_EUR_M = 2, 6, 50.0
ECHO_YEARS = 0.17  # two rows of one company and stage within about 2 months are one round
COMPANY_ALIASES = {"iqmquantumcomputers": "iqm", "leya": "legora", "leyaai": "legora"}  # warm-path-stress.md #6
LEADS_VERDICTS = {"leads", "leads_size"}
FOOTNOTE = ("A shared round is not a relationship. Ties are only visible for funds in our data. About 94% of next "
            "leads in our data had no prior tie with the seed lead (320 of 342 outside handoffs).")
RULES = ("Shared round: equity, 2 to 6 named investors, at most 50M EUR, last 4 years, precise date, not disputed, "
         "not your own company. Confirmed: one company-first source, or two independent sources, name both funds. "
         "One-sided ties rank below confirmed ones. Order: confirmed shared companies, shared companies, most recent "
         "shared round, rounds led at your next stage.")
FOOTNOTE_SOURCE = "research/patterns/warm-path-stress.md (T1 baseline, warm_path_stress_out.json)"
QUERIED_FUND = re.compile(r"(?:round that|rounds) (.+?) invested in", re.I)  # both investor-first query wordings


def next_stage_of(stage: str) -> str | None:
    """The stage after the founder's current one ('seed' -> 'series a'), None at the end or for unknown input."""
    if stage not in STAGES or stage == STAGES[-1]:
        return None
    return STAGES[STAGES.index(stage) + 1]


def resolve_funds(snap: Snapshot, names: list[str]) -> tuple[list[str], list[str]]:
    """Typed names or stored keys -> (fund keys in input order without repeats, names that matched nothing)."""
    keys, unmatched = [], []
    for n in names:
        k = snap.match_fund(n) if n else None
        if k is None:
            unmatched.append(n)
        elif k not in keys:
            keys.append(k)
    return keys, unmatched


def _company(ckey: str) -> str:
    return COMPANY_ALIASES.get(ckey, ckey)


def _excluded(snap: Snapshot, key: str) -> bool:
    return snap.is_hub(key) or snap.is_crossover(key)


def _date_ok(r: dict) -> bool:
    """False when the date is year-only or vague, or a June that no source text spells out (defaulted)."""
    if _date_precision(r) < 2:
        return False
    if r["month"] != 6:
        return True
    raws = " ".join(str(v) for s in r.get("sources", []) for f, v in (s.get("row") or {}).items()
                    if "date" in f.lower() or f.lower() == "announced")
    return bool(re.search(r"jun|-06-|-06\b|/06/|\.06\.", raws, re.I))


def names_fund(source: dict, key: str) -> bool:
    """Does one Cala source row name fund `key` as lead or investor? An investor-first row names its queried fund."""
    row = source.get("row") or {}
    fields = [v for f, v in row.items() if v and ("investor" in f.lower() or "lead" in f.lower()
                                                  or f.lower() in ("participants", "co_investors"))]
    named = {canon(x) for v in fields for x in split_investors(v if isinstance(v, list) else str(v))}
    if source.get("path") == "investor_first":
        m = QUERIED_FUND.search(source.get("query") or "")
        if m:
            named.add(canon(m.group(1)))
    if key in named:
        return True
    probe = key.replace(" ", "")  # 'NordicNinja + others' style text that the splitter keeps whole
    return len(probe) >= 4 and probe in _compact(" ".join(str(v) for v in fields))


def confirmation(rounds: list[dict], a: str, b: str) -> str:
    """'company_first' | 'two_sources' | 'one_sided' for funds a and b in one (possibly merged) round."""
    both = [s for r in rounds for s in r.get("sources", []) if names_fund(s, a) and names_fund(s, b)]
    if any(s.get("path") == "company_first" for s in both):
        return "company_first"
    if len({s.get("query") for s in both}) >= 2:
        return "two_sources"
    return "one_sided"


def _echo(a: dict, b: dict) -> bool:
    """Same round under two company spellings or two rows (merge._same_round is stricter on leads; this is for counts)."""
    ca, cb = _company(a["ckey"]), _company(b["ckey"])
    if not _same_family(ca, cb) or abs(a["t"] - b["t"]) > ECHO_YEARS:
        return False
    if a["stage"] and b["stage"] and a["stage"] != b["stage"]:
        return False
    x, y = a.get("amount_eur_m"), b.get("amount_eur_m")
    return not (x and y and max(x, y) / min(x, y) > 1.15)


def dedupe_rounds(rounds: list[dict]) -> list[list[dict]]:
    """Group echoes of one round. Each group is ordered best row first: company-first, then most investors."""
    groups: list[list[dict]] = []
    for r in sorted(rounds, key=lambda r: r["t"]):
        g = next((g for g in groups if any(_echo(r, x) for x in g)), None)
        if g is None:
            groups.append([r])
        else:
            g.append(r)
    rank = lambda r: (r.get("query_path") in ("company_first", "both"), len(r["leads"]) + len(r["participants"]))  # noqa: E731
    return [sorted(g, key=rank, reverse=True) for g in groups]


def _qualifies(snap: Snapshot, group: list[dict], my_ckey: str) -> bool:
    if any(r.get("disputed") or r.get("not_led") for r in group):
        return False
    best = group[0]
    if _company(best["ckey"]) == my_ckey or any(_company(r["ckey"]) == my_ckey for r in group):
        return False
    if NON_EQUITY.search(str(best.get("type") or "")):
        return False
    investors = set().union(*(set(r["leads"]) | set(r["participants"]) for r in group))
    if not MIN_INVESTORS <= len(investors) <= MAX_INVESTORS:
        return False
    amount = best.get("amount_eur_m") or next((r["amount_eur_m"] for r in group if r.get("amount_eur_m")), None)
    if amount and amount > MAX_AMOUNT_EUR_M:
        return False
    return snap.now_t - best["t"] <= WINDOW_YEARS and _date_ok(best)


def _receipt(snap: Snapshot, group: list[dict], fund: str, mine: list[str]) -> dict:
    best = group[0]
    leads = sorted(set().union(*(set(r["leads"]) for r in group)))
    investors = sorted(set().union(*(set(r["leads"]) | set(r["participants"]) for r in group)))
    with_keys = [k for k in mine if k in investors]
    level = max((confirmation(group, fund, k) for k in with_keys),
                key=["one_sided", "two_sources", "company_first"].index)
    brief = round_brief(snap, best)
    return {"rid": best["id"], "echo_rids": [r["id"] for r in group[1:]], "company": best["company"],
            "ckey": _company(best["ckey"]), "date": brief["date"], "t": best["t"], "stage": brief["stage"],
            "amount_eur_m": brief["amount_eur_m"], "amount_raw": brief["amount_raw"], "n_investors": len(investors),
            "investors": [snap.name(k) for k in investors], "leads": [snap.name(k) for k in leads],
            "with": [snap.name(k) for k in with_keys], "fund_led": fund in leads, "confirmation": level,
            "sources": sorted({s.get("path") for r in group for s in r.get("sources", [])})}


def shared_rounds(snap: Snapshot, fund: str, my_investors: list[str], my_company: str | None) -> list[dict]:
    """Every qualifying shared round between `fund` and any of the founder's investors, deduped, newest first."""
    mine = [k for k in my_investors if k != fund and not _excluded(snap, k)]
    if not mine or _excluded(snap, fund):
        return []
    fund_ids = set(snap.by_investor.get(fund, []))
    my_ids = set().union(*(set(snap.by_investor.get(k, [])) for k in mine))
    fund_rows = [snap.rounds[i] for i in fund_ids]
    raw = [snap.rounds[i] for i in fund_ids & my_ids]
    # an echo row may carry only one of the two funds: pull in the fund's own echo rows of the same rounds
    raw += [r for r in fund_rows if r["id"] not in my_ids and any(_echo(r, x) for x in raw)]
    raw += [snap.rounds[i] for i in my_ids - fund_ids if any(_echo(snap.rounds[i], x) for x in raw)]
    my_ckey = _company(company_key(my_company or "")) if my_company else ""
    out = []
    for group in dedupe_rounds(raw):
        investors = set().union(*(set(r["leads"]) | set(r["participants"]) for r in group))
        if fund not in investors or not investors & set(mine) or not _qualifies(snap, group, my_ckey):
            continue
        out.append(_receipt(snap, group, fund, mine))
    return sorted(out, key=lambda x: -x["t"])


def lead_record(snap: Snapshot, fund: str, stage: str, target_m: float | None) -> dict:
    """The fund's lead record at `stage` from engine.fund_profile: counts with their denominators and the rounds."""
    p = fund_profile(snap, fund, stage, target_m)
    at_stage = [r for r in p["rounds_led"] if r["stage"] == STAGE_LABEL.get(stage)]
    return {"stage": STAGE_LABEL.get(stage, stage), "verdict": p["verdict"], "verdict_label": p["verdict_label"],
            "led_at_stage": p["led_at_stage"], "led": p["led"], "known": p["known"], "unknown": p["unknown"],
            "window_years": WINDOW_YEARS, "last_lead": p["last_lead"], "rounds_led_at_stage": at_stage,
            "size": p["size"]}


def _entry(snap: Snapshot, fund: str, receipts: list[dict], record: dict) -> dict:
    confirmed = {r["ckey"] for r in receipts if r["confirmation"] != "one_sided"}
    latest = receipts[0] if receipts else None
    return {"key": fund, "name": snap.name(fund), "lead_record": record, "shared_rounds": receipts,
            "shared_companies": len({r["ckey"] for r in receipts}), "confirmed_companies": len(confirmed),
            "one_sided_only": bool(receipts) and not confirmed,
            "latest_shared": {"date": latest["date"], "t": latest["t"], "rid": latest["rid"]} if latest else None}


def _order(e: dict) -> tuple:
    latest = e["latest_shared"]["t"] if e["latest_shared"] else 0.0
    return (-e["confirmed_companies"], -e["shared_companies"], -latest, -e["lead_record"]["led_at_stage"], e["name"])


def intro_paths(snap: Snapshot, my_investors: list[str], next_stage: str, target_m: float | None = None,
                my_company: str | None = None, my_lead: str | None = None, limit: int = 10) -> dict:
    """Funds that lead at `next_stage` and already sat in a small round with the founder's lead or investors.

    my_investors / my_lead: typed names or fund keys (the lead is added to the investors if missing).
    next_stage: an engine.STAGES value ('series a'). target_m: the founder's next round in EUR millions, or None.
    """
    if next_stage not in STAGES:
        raise ValueError(f"next_stage must be one of {STAGES}, got {next_stage!r}")
    keys, unmatched = resolve_funds(snap, ([my_lead] if my_lead else []) + list(my_investors))
    lead_key = snap.match_fund(my_lead) if my_lead else None
    mine = [k for k in keys if not _excluded(snap, k)]
    candidates: set[str] = set()
    for k in mine:
        for rid in snap.by_investor.get(k, []):
            r = snap.rounds[rid]
            n = len(r["leads"]) + len(r["participants"])
            if n <= MAX_INVESTORS + 2:  # cheap prefilter; echo merging can only grow a round by a couple of names
                candidates |= (set(r["leads"]) | set(r["participants"])) - set(keys)
    entries = []
    for f in sorted(candidates):
        if _excluded(snap, f):
            continue
        record = lead_record(snap, f, next_stage, target_m)
        if record["verdict"] not in LEADS_VERDICTS:
            continue
        receipts = shared_rounds(snap, f, mine, my_company)
        if receipts:
            entries.append(_entry(snap, f, receipts, record))
    entries.sort(key=_order)
    return {"next_stage": STAGE_LABEL[next_stage], "lead": snap.name(lead_key) if lead_key else None,
            "investors": [{"key": k, "name": snap.name(k), "excluded": _excluded(snap, k)} for k in keys],
            "unmatched": unmatched, "suggestions": entries[:limit], "more": max(0, len(entries) - limit),
            "rules": RULES,
            "footnote": FOOTNOTE, "footnote_source": FOOTNOTE_SOURCE}


def pasted_fund_receipts(snap: Snapshot, funds: list[str], my_investors: list[str], next_stage: str,
                         target_m: float | None = None, my_company: str | None = None,
                         my_lead: str | None = None) -> dict:
    """The same shared-round receipts for funds the founder already pasted, whatever their verdict.

    Funds with no qualifying shared round are kept with an empty list, so the UI can say "no shared small round found".
    """
    if next_stage not in STAGES:
        raise ValueError(f"next_stage must be one of {STAGES}, got {next_stage!r}")
    mine, unmatched_mine = resolve_funds(snap, ([my_lead] if my_lead else []) + list(my_investors))
    targets, unmatched = resolve_funds(snap, funds)
    mine = [k for k in mine if not _excluded(snap, k)]
    entries = [_entry(snap, f, shared_rounds(snap, f, mine, my_company), lead_record(snap, f, next_stage, target_m))
               for f in targets]
    return {"next_stage": STAGE_LABEL[next_stage], "funds": entries, "unmatched": unmatched,
            "unmatched_investors": unmatched_mine, "footnote": FOOTNOTE, "footnote_source": FOOTNOTE_SOURCE}

