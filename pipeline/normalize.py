"""Turn raw Cala round histories into clean rounds with parsed dates, EUR amounts and canonical investors."""
from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

DATA = Path(__file__).parent / "data"

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
FX_TO_EUR = {"€": 1.0, "eur": 1.0, "$": 0.92, "usd": 0.92, "£": 1.17, "gbp": 1.17,
             "sek": 0.087, "nok": 0.085, "dkk": 0.134, "chf": 1.04}
NOT_AN_INVESTOR = {"", "not disclosed", "undisclosed", "unknown", "n a", "na", "none", "null",
                   "founders", "various", "others", "angel investors", "angels", "existing investors",
                   "multiple investors", "unnamed investors", "private investors"}
LEGAL_SUFFIX = re.compile(r"\b(ab|oy|oyj|ltd|limited|llc|llp|lp|gmbh|inc|sa|sas|bv|nv|as|asa|ag|plc|co)\b")
STAGES = ["pre-seed", "seed", "series a", "series b", "series c", "series d", "series e", "series f", "growth"]


def parse_date(raw: str | None) -> tuple[int, int] | None:
    """Return (year, month); month defaults to 6 when only a year (or quarter) is known."""
    if not raw:
        return None
    s = str(raw).lower()
    year = re.search(r"(19|20)\d{2}", s)
    if not year:
        return None
    y = int(year.group())
    iso = re.search(r"(19|20)\d{2}-(\d{1,2})", s)
    if iso:
        return y, max(1, min(12, int(iso.group(2))))
    for name, num in MONTHS.items():
        if re.search(rf"\b{name}", s):
            return y, num
    quarter = re.search(r"q([1-4])", s)
    if quarter:
        return y, int(quarter.group(1)) * 3 - 1
    return y, 6


def parse_amount_eur(raw: str | None) -> float | None:
    """Parse '$28M', '~€1.2 billion', 'SEK 50m' into EUR millions."""
    if not raw:
        return None
    s = str(raw).lower().replace(",", "")
    num = re.search(r"(\d+(?:\.\d+)?)\s*(billion|bn|b\b|million|mn|m\b|k\b|thousand)?", s)
    if not num:
        return None
    value = float(num.group(1))
    unit = num.group(2) or "m"
    if unit in ("billion", "bn", "b"):
        value *= 1000
    elif unit in ("k", "thousand"):
        value /= 1000
    rate = next((r for sym, r in FX_TO_EUR.items() if sym in s), 1.0)
    return round(value * rate, 2)


def stage_of(raw: str | None) -> str | None:
    s = (raw or "").lower()
    if "pre-seed" in s or "preseed" in s or "pre seed" in s:
        return "pre-seed"
    if "seed" in s:
        return "seed"
    m = re.search(r"series\s*([a-f])", s)
    if m:
        return f"series {m.group(1)}"
    if any(w in s for w in ("growth", "late", "pre-ipo", "private equity")):
        return "growth"
    return None


def investor_key(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = re.sub(r"\(.*?\)", " ", s.lower())
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = LEGAL_SUFFIX.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def split_investors(raw) -> list[str]:
    if raw is None:
        return []
    parts = raw if isinstance(raw, list) else re.split(r",|;|\band\b|&|\+", str(raw))
    names = []
    for part in parts:
        if isinstance(part, dict):
            part = part.get("name") or ""
        name = re.sub(r"\(.*?\)", "", str(part)).strip(" .")
        if investor_key(name) not in NOT_AN_INVESTOR and len(name) > 1:
            names.append(name)
    return names


def _field(row: dict, *names: str):
    for n in names:
        if row.get(n) not in (None, ""):
            return row[n]
    return None


def normalize() -> list[dict]:
    """Return companies with chronologically sorted, cleaned rounds; also writes data/rounds.json."""
    display: dict[str, Counter] = defaultdict(Counter)
    companies = []
    for line in (DATA / "histories.jsonl").open():
        rec = json.loads(line)
        rounds = []
        for row in rec["rounds"]:
            when = parse_date(_field(row, "date", "announcement_date", "announced", "year"))
            if not when:
                continue
            leads = split_investors(_field(row, "lead_investor", "lead_investors", "lead"))
            parts = split_investors(_field(row, "participating_investors", "investors", "participants"))
            for n in leads + parts:
                display[investor_key(n)][n] += 1
            raw_type = _field(row, "round_type", "type", "round")
            rounds.append({
                "year": when[0], "month": when[1], "t": when[0] + (when[1] - 1) / 12,
                "type": raw_type, "stage": stage_of(raw_type),
                "amount_eur_m": parse_amount_eur(_field(row, "amount", "amount_raised", "size")),
                "amount_raw": _field(row, "amount", "amount_raised", "size"),
                "leads": sorted({investor_key(n) for n in leads}),
                "participants": sorted({investor_key(n) for n in parts} - {investor_key(n) for n in leads}),
                "raw": row,
            })
        rounds.sort(key=lambda r: r["t"])
        companies.append({"name": rec["name"], "country": rec["country"], "rounds": rounds,
                          "entity_ids": [e.get("id") for e in rec.get("entities", []) if e.get("entity_type") == "Company"]})
    names = {k: c.most_common(1)[0][0] for k, c in display.items()}
    out = {"companies": companies, "investor_names": names}
    (DATA / "rounds.json").write_text(json.dumps(out, ensure_ascii=False))
    return companies


if __name__ == "__main__":
    cos = normalize()
    rounds = [r for c in cos for r in c["rounds"]]
    print(f"{len(cos)} companies, {len(rounds)} dated rounds, "
          f"{sum(1 for r in rounds if r['leads'])} with lead, "
          f"{sum(1 for r in rounds if r['participants'])} with participants")
