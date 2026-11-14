"""Flag rounds whose own cached Cala source text names a different lead. Uses only text already stored; no Cala call.

A source about another round of the company (its stage and amount both disagree with the record, see
different_round) is never used. Otherwise a round is disputed when all three hold:
  1. the source answer names a lead that is a known investor in our data and is not in the round's leads,
  2. at least one of the round's leads is not named as a lead by the source,
  3. that lead is still mentioned in the source text (so the text is about this round and gives the fund another role).
Disputed rounds stay in the data and on the record, but fund_profile leaves them out of lead counts.
"""
from __future__ import annotations

import re

from merge import ALIASES, canon, parse_amount_eur, split_investors

INLINE = re.compile(r"(?:co-?\s?)?lead (?:investors?|backers?)\**\s*(?:was|were|is|are|:)\**\s*(.+)"
                    r"|\b(?:co-?\s?)?led by:?\s+(.+)", re.I)
HEADER = re.compile(r"^\s*(?:#+\s*)?\**\s*(?:co-?\s?)?leads?(?: investors?| backers?)?\s*:?\s*\**\s*:?\s*$"
                    r"|\b(?:co-?\s?)?led by:?\s*\**:?\s*$", re.I)
BULLET = re.compile(r"^\s*(?:[-*\u2022]|\d+\.)\s+(.+)")
TAGGED = re.compile(r"^\s*(?:[-*\u2022|]|\d+\.)\s*\**([^*|()]+?)\**\s*(?:\((?:co-?\s?)?lead\)|\|\s*(?:co-?\s?)?lead(?: investor)?\s*\|)", re.I)
STOP = re.compile(r"\b(?:with participation|participation from|alongside|joined by|with (?:support|backing|existing|follow)"
                  r"|while|who|which|according|as (?:the|a)|in (?:a|the|its)|on \d|announced)\b|,\s*(?:an?|the)\s|[.;(:]", re.I)
CUT = 690  # summarize_search keeps 700 characters of the answer; a lead list running to the end may be cut
# 'X as co-lead', 'with X acting as co-lead': the name sits before the role
AS_COLEAD = re.compile(r"\s+(?:acting|joining|serving|coming in)?\s*as\s+(?:the\s+|a\s+)?co-?\s?leads?\b", re.I)
BEFORE = re.compile(r",|;|:|\.\s|\bwith\b|\band\b|\bwhile\b|\bwhere\b", re.I)
DASHES = str.maketrans({c: "-" for c in "\u2010\u2011\u2012\u2013\u2014\u2015\u2212"})


def _norm(text: str) -> str:
    """Unicode hyphens (U+2011 in 'co-lead') and narrow spaces as plain ASCII, so every pattern sees them."""
    return (text or "").translate(DASHES).replace("\u202f", " ").replace("\u00a0", " ")


def _names(segment: str, known: set[str]) -> set[str]:
    text = STOP.split(segment.replace("**", "").strip(" :"))[0]
    return {k for k in (canon(n) for n in split_investors(text)) if len(k) > 2 and k in known}


def _as_colead(line: str, known: set[str]) -> set[str]:
    out: set[str] = set()
    for m in AS_COLEAD.finditer(line):
        before = BEFORE.split(line[:m.start()].replace("**", ""))[-1]
        out |= {k for k in (canon(n) for n in split_investors(before)) if len(k) > 2 and k in known}
    return out


def source_leads(src: dict, known: set[str]) -> set[str]:
    """Investor keys the source text names as lead or co-lead (only names we already know as investors)."""
    answer = _norm(src.get("answer"))
    out = _scan(answer.splitlines(), known, cut=len(answer) >= CUT)
    if out is None:
        return set()  # the answer's lead list is cut off, so we cannot tell who else it names
    return out | (_scan([_norm(p) for p in src.get("points") or []], known, cut=False) or set())


def _scan(lines: list[str], known: set[str], cut: bool) -> set[str] | None:
    out: set[str] = set()
    in_list = False
    for line in lines:
        if in_list:
            b = BULLET.match(line)
            if b:
                out |= _names(b.group(1), known)
                continue
            if line.strip():
                in_list = False
        if HEADER.search(line):
            in_list = True
            continue
        m = INLINE.search(line)
        if m:
            out |= _names(m.group(1) or m.group(2), known)
        t = TAGGED.match(line)
        if t:
            out |= _names(t.group(1), known)
        out |= _as_colead(line, known)
    return None if (cut and in_list) else out


# same body under keys merge.canon keeps apart, plus every merge alias, so a snapshot built before an alias was
# added still compares 'k' and 'kfund' (Symbe) as one fund
EQUIV = {**ALIASES, "european innovation council": "eic fund", "eic": "eic fund"}


def _same(a: str, b: str) -> bool:
    a, b = EQUIV.get(a, a), EQUIV.get(b, b)
    a2, b2 = a.replace(" ", ""), b.replace(" ", "")
    if a2 == b2:
        return True
    if min(len(a2), len(b2)) >= 4 and (a2.startswith(b2) or b2.startswith(a2)):
        return True
    return bool(re.search(rf"\b{re.escape(b)}\b", a) or re.search(rf"\b{re.escape(a)}\b", b))


def _mentioned(key: str, name: str, text: str) -> bool:
    flat = re.sub(r"[^a-z0-9]", "", text.lower())
    return any(len(x) >= 4 and x in flat for x in (key.replace(" ", ""), re.sub(r"[^a-z0-9]", "", name.lower())))


STAGE_WORD = re.compile(r"\bpre-?\s?seed\b|\bseed\b|\bseries\s+([a-k])\b", re.I)
MONEY = re.compile(r"(?:[$\u20ac\u00a3]|\b(?:usd|eur|gbp|sek|nok|dkk|chf))\s?\d[\d.,]*\s*(?:billion|bn|million|mn|m|k)?\b"
                   r"|\b\d[\d.,]*\s*(?:billion|bn|million|mn|m)\b\s*(?:usd|eur|gbp|sek|nok|dkk|dollars|euros)?", re.I)


def _stages(text: str) -> set[str]:
    out = set()
    for m in STAGE_WORD.finditer(_norm(text)):
        w = m.group(0).lower()
        out.add(f"series {m.group(1).lower()}" if m.group(1) else ("pre-seed" if w.startswith("pre") else "seed"))
    return out


def different_round(r: dict, text: str) -> bool:
    """True when the source text is about another round of the company: every check we can make disagrees.

    Stage: the source names stages and none is the record's (Anthropic: record Series G, source Series H).
    Amount: the source names amounts and none is within 0.5x to 2x of the record's (USD 30bn against USD 65bn).
    A source that agrees on either one is about this round (Roleo: same EUR 2.9m, but called seed, not Series A).
    """
    checks = []
    mine, theirs = _stages(f"{r.get('type') or ''} {r.get('stage') or ''}"), _stages(text)
    if mine and theirs:
        checks.append(not (mine & theirs))
    amt = r.get("amount_eur_m")
    sums = [a for a in (parse_amount_eur(m.group(0)) for m in MONEY.finditer(_norm(text))) if a]
    if amt and sums:
        checks.append(not any(0.5 <= a / amt <= 2.0 for a in sums))
    return bool(checks) and all(checks)


def dispute(r: dict, names: dict[str, str], known: set[str]) -> dict | None:
    """{'source_leads': [...], 'not_lead_in_source': [...]} when the round's source contradicts its lead, else None."""
    src = r.get("source")
    if not src or not r["leads"]:
        return None
    if different_round(r, (src.get("answer") or "") + " " + " ".join(src.get("points") or [])):
        return None
    named = source_leads(src, known)
    extra = [k for k in named if not any(_same(k, o) for o in r["leads"])]
    if not extra:
        return None
    text = _norm((src.get("answer") or "") + " " + " ".join(src.get("points") or []))
    demoted = [o for o in r["leads"] if len(o) >= 3 and not any(_same(k, o) for k in named)
               and _mentioned(o, names.get(o, o), text)]
    if not demoted:
        return None
    return {"source_leads": sorted(names.get(k, k) for k in extra),
            "not_lead_in_source": sorted(names.get(k, k) for k in demoted)}
