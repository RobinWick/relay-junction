"""Turn a messy pasted meeting list into fund names. Deterministic first; leftovers can go to Gemini."""
from __future__ import annotations

import re

from engine import Snapshot

SPLIT_LINES = re.compile(r"[\n;]+|(?<=\S)\s*[•·▪●]\s*")
NOISE = re.compile(
    r"(\b\d{1,2}[:.]\d{2}\b(\s*[-–]\s*\d{1,2}[:.]\d{2})?|\b(mon|tue|wed|thu|fri|sat|sun)[a-z]*\b|\b\d{1,2}\s*(am|pm)\b|"
    r"\b\d{1,2}(st|nd|rd|th)?\.?\s*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\b|"
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*\d{1,2}(st|nd|rd|th)?\b|\b\d{1,2}[./]\d{1,2}\.?\b|"
    r"\S+@\S+|https?://\S+|\b(table|booth|room|stage|meeting|slush|zoom|teams)\s*#?\s*\w*\b)", re.I)
SEGMENT_SPLIT = re.compile(r"\s+[-–|/]\s+|\s+@\s+|\s+at\s+|\(|\)|,|:")


def candidates(line: str) -> list[str]:
    clean = NOISE.sub(" ", line)
    clean = re.sub(r"^\s*(\d+[.)]|[-*+])\s*", "", clean).strip()
    parts = [p.strip(" .-") for p in SEGMENT_SPLIT.split(clean) if p and p.strip(" .-")]
    return [clean] + [p for p in parts if p != clean]


def parse_list(snap: Snapshot, text: str, limit: int = 40) -> dict:
    """Returns matched fund keys (in pasted order) and lines nothing matched."""
    matched, unmatched, seen = [], [], set()
    for raw in SPLIT_LINES.split(text or ""):
        line = raw.strip()
        if len(line) < 2:
            continue
        hit = None
        for cand in candidates(line):
            if len(cand) < 2:
                continue
            hit = snap.match_fund(cand)
            if hit:
                break
        if hit:
            if hit not in seen:
                seen.add(hit)
                matched.append({"key": hit, "pasted": line})
        else:
            unmatched.append(line)
        if len(matched) + len(unmatched) >= limit:
            break
    return {"matched": matched, "unmatched": unmatched}
