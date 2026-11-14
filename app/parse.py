"""Turn a messy pasted meeting list into fund names. Deterministic first; leftovers can go to Gemini.

Per line: drop times, dates, emails and table numbers, turn URLs into their host name, split into segments
(comma, slash, tab, '+', '<>', ' - ', '@', brackets; 'and' or '&' when the part is not one name), then match every segment, so one line can give
several funds. Inside a longer segment, known fund names are found as word runs ('Lunch with Maki.vc team').
Weak hits (a first name, a generic word, a person-shaped key, a typo match, almost no history) are dropped when the
same line has a strong one; a weak name alone on its line ('Felix') is still what was typed.
"""
from __future__ import annotations

import re

from engine import Snapshot, norm
from merge import investor_key

LINE_LIMIT = 40  # funds checked per paste; the rest is reported as skipped_lines
TEXT_LIMIT = 8000  # characters read per paste

SPLIT_LINES = re.compile(r"[\n;]+|(?<=\S)\s*[\u2022\u00b7\u25aa\u25cf\u25e6\u2192]\s*")
DAYS = (r"mon|monday|tue|tues|tuesday|wed|wednesday|thu|thur|thurs|thursday|fri|friday|sat|saturday|sun|sunday|"
        r"maanantai\w*|tiistai\w*|keskiviikko\w*|torstai\w*|perjantai\w*|lauantai\w*|sunnuntai\w*|"
        r"mandag|m\u00e5ndag|tisdag|onsdag|torsdag|fredag|l\u00f6rdag|s\u00f6ndag")
MONTHS = r"jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec"
NOISE = re.compile(
    r"(^\s*\[[^\]]*\]\s*[^:]{1,30}:|\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}[./]\d{1,2}\.(\d{2,4})?|\b\d{1,2}[./]\d{1,2}\b|"
    r"\b\d{1,2}[:.]\d{2}\b(\s*[-\u2013]\s*\d{1,2}[:.]\d{2})?|\b(" + DAYS + r")\b\.?|"
    r"\b(ma|ti|ke|to|pe|la|su)\b\.?(?=\s*\d)|\b\d{1,2}\s*(am|pm)\b|"
    r"\b\d{1,2}(st|nd|rd|th)?\.?\s*(" + MONTHS + r")[a-z]*\.?(?![a-z])|"
    r"\b(" + MONTHS + r")[a-z]*\.?\s*\d{1,2}(st|nd|rd|th)?\b|\b20\d\d\b|\bklo\b|"
    r"\S+@\S+|\b(table|booth|room|hall|tier|stage)\s*#?\s*\w*\d\w*\b)", re.I)
URL = re.compile(r"(?:https?://)?(?:www\.)?([a-z0-9-]+)\.(?:com|vc|fi|se|io|co|eu|net|capital|ventures|dk|no|de)\b(?:/\S*)?",
                 re.I)
SEGMENT_SPLIT = re.compile(r"\s+[-\u2013\u2014|/]\s+|[|\t]|\s+@\s+|\s*<>\s*|\s+x\s+|\(|\)|,|:|\s+[+]\s+|"
                           r"(?<=[a-z])-(?=[A-Z])|(?<=\w)/(?=[A-Z])|(?<=\w)\|(?=\w)")
# 'and' splits only a segment that is not itself a fund name, so 'Plug and Play' stays whole
AND_SPLIT = re.compile(r"\s+(?:and|&|och|ja|og|und)\s+", re.I)
FUNDISH = {"capital", "ventures", "venture", "partners", "vc", "fund", "invest", "investments", "holdings", "group",
           "labs", "equity", "growth", "angels"}
VEHICLE = re.compile(r"(\s+fund)?\s+([ivx]{1,4}|\d{1,2})$|\s+(gp|management|holding|holdings|publ|aps|kg|ky|ab|oy)$", re.I)
GLUED = re.compile(r"(ventures|capital|partners|vc)$", re.I)
INFLECT = re.compile(r"(?:'s|\u2019s|:n|:lle|:lta|:lt\u00e4|lle|lta|lt\u00e4|lla|ll\u00e4|sta|st\u00e4|ssa|ss\u00e4|in|n)$", re.I)
GENERIC = {"fund", "funds", "capital", "ventures", "venture", "company", "investment", "investments", "investor",
           "investors", "seed", "preseed", "pre seed", "angel", "angels", "lead", "partner", "partners", "founders",
           "founder", "yes", "no", "insight", "index", "change", "speed", "spark", "world", "true", "better", "join",
           "space", "scale", "earth", "momentum", "peak", "summit", "first", "nordic", "friends", "play", "concept",
           "wave", "plug", "status", "stage", "booked", "team", "intro", "coffee", "lunch", "dinner", "call", "meeting",
           "city", "owner", "name", "notes", "note", "contact", "email", "series", "round", "tbd", "maybe", "follow up",
           "declined", "pending", "done", "todo", "deck", "pitch", "demo", "slush", "zoom", "teams", "google meet"}
FIRST_NAMES = set("""
felix robin max johan timo mikko miki ilkka kasper paul jari juha carlos anna maria ville emil fredrik erik lars petteri
tuomas antti jussi matti pekka heikki kari markus jukka sami mika janne teemu tommi juho lauri eero aleksi henri joonas
otto oskari elias leo eino olli kalle jani marko risto sakari tapio veikko jaakko hanna laura sanna sara emma linnea
elina johanna katja kaisa minna noora paula riikka tiina saara aino ella helmi venla iida oona karl nils per anders
magnus henrik oscar gustav axel william viktor jonas daniel alexander david michael john james peter thomas mark adam
andrew chris christian martin simon tom ben sam jack harry george oliver alex sebastian nicolas lucas hugo louis
pierre jan jakob tobias stefan andreas niklas philipp florian julia lisa sophie sofia ida maja astrid ingrid karin
kristina sarah jessica emily kate claire rachel nina eva lena
""".split())
MAX_N = 5


def _weak(snap: Snapshot, key: str, typed: str, fuzzy: bool) -> bool:
    """Weak: fuzzy hit, a lone generic word or first name as typed, a person-shaped key, or almost no history."""
    t = investor_key(typed).split()
    return (fuzzy or " ".join(t) in GENERIC or (len(t) == 1 and (t[0] in GENERIC or t[0] in FIRST_NAMES))
            or (len(t) == 2 and t[0] in FIRST_NAMES and t[1] not in FUNDISH) or len(snap.by_investor.get(key, [])) < 2)


def _exact(snap: Snapshot, text: str) -> str | None:
    k = norm(text)
    if not k:
        return None
    if k in snap.by_investor:
        return k
    if snap._compact is None:
        snap.match_fund("x")  # builds the compact index
    return snap._compact.get(k.replace(" ", ""))


def _lookup(snap: Snapshot, text: str, inner: bool = False) -> tuple[str, str, bool] | None:
    """(key, typed, fuzzy). Tries cheap variants (&->and, fund vehicle, glued 'ventures', Finnish case endings) and
    prefers any exact hit over a typo (fuzzy) one. Inner n-grams are matched exactly only."""
    tries = [text.replace("&", " and "), text]
    v = VEHICLE.sub("", text).strip()
    while v and v != tries[-1]:
        tries.append(v)
        v = VEHICLE.sub("", v).strip()
    if " " not in text.strip():
        tries += [GLUED.sub("", text), INFLECT.sub("", text)]
    fuzzy = None
    for t in tries:
        if len(t.strip()) < 2:
            continue
        k = _exact(snap, t) if inner else snap.match_fund(t)
        if not k:
            continue
        c = norm(t)
        if c == k or c.replace(" ", "") == k.replace(" ", ""):
            return k, t, False
        fuzzy = fuzzy or (k, t, True)
    return fuzzy


def _segment_keys(snap: Snapshot, seg: str, whole: bool = True) -> list[tuple[str, bool, bool]]:
    """(key, weak, whole) for one segment: the whole segment first, then its 'and' parts, else greedy longest-first
    word runs. `whole` is True only when the hit is the entire segment as typed."""
    hit = _lookup(snap, seg)
    if hit:
        return [(hit[0], _weak(snap, *hit), whole)]
    parts = AND_SPLIT.split(seg)
    if len(parts) > 1:
        return [h for p in parts if p.strip() for h in _segment_keys(snap, p.strip(), whole=False)]
    toks, out, i = seg.split(), [], 0
    while i < len(toks):
        for n in range(min(MAX_N, len(toks) - i), 0, -1):
            gram = " ".join(toks[i:i + n]).strip(" .,-*")
            hit = _lookup(snap, gram, inner=True) if len(gram) >= 4 else None
            # a run inside a sentence must look like a name: typed with a capital, a dot or a digit
            if (hit and not _weak(snap, *hit) and len(snap.by_investor[hit[0]]) >= 3
                    and re.search(r"[A-Z.\d]", gram)):
                out.append((hit[0], False, False))
                i += n
                break
        else:
            i += 1
    return out


def line_keys(snap: Snapshot, line: str) -> list[str]:
    clean = URL.sub(lambda m: m.group(1), line)
    clean = NOISE.sub(" ", clean)
    clean = re.sub(r"^\s*(\d+[.)]|[-*+>])\s*", "", clean).strip()
    segs = [s.strip(" .-*|#>") for s in SEGMENT_SPLIT.split(clean) if s and s.strip(" .-*|#>")]
    found = [h for s in segs for h in _segment_keys(snap, s)]
    strong = [k for k, weak, _ in found if not weak]
    if strong:
        return list(dict.fromkeys(strong))
    if len(segs) == 1 and len(found) == 1 and found[0][2]:
        return [found[0][0]]  # a weak name alone on its own line ('Felix', 'Plural') is still what was typed
    return []


def parse_list(snap: Snapshot, text: str, limit: int = LINE_LIMIT, defer: frozenset = frozenset()) -> dict:
    """Matched fund keys (in pasted order), lines nothing matched, and how many lines were not read.

    Every fund on a line counts ('Creandum, Northzone, Inventure' gives three). At most `limit` funds and `limit`
    unmatched lines are kept, and only the first TEXT_LIMIT characters are read (cut at a line break, never inside
    a name). skipped_lines counts the non-empty lines left out, so the page can say so. Lines in `defer` are left
    unmatched on purpose (the sample's messy line has a saved Gemini answer, so the demo shows that step).
    """
    text = text or ""
    skipped = 0
    if len(text) > TEXT_LIMIT:
        head = text[:TEXT_LIMIT]
        cut = head.rfind("\n")
        head = head[:cut] if cut > 0 else head
        skipped += sum(1 for x in SPLIT_LINES.split(text[len(head):]) if len(x.strip()) >= 2)
        text = head
    matched, unmatched, seen = [], [], set()
    for raw in SPLIT_LINES.split(text):
        line = raw.strip()
        if len(line) < 2:
            continue
        if len(matched) >= limit:
            skipped += 1
            continue
        keys = [] if line in defer else line_keys(snap, line)
        for k in keys:
            if k not in seen and len(matched) < limit:
                seen.add(k)
                matched.append({"key": k, "pasted": line})
        if not keys:
            if len(unmatched) >= limit:
                skipped += 1
            else:
                unmatched.append(line)
    return {"matched": matched, "unmatched": unmatched, "skipped_lines": skipped}
