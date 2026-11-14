"""Shared parsing and merging of Cala rows (company-first and investor-first). Used by the app and the pipeline."""
from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone

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
    """Return (year, month); month defaults to 6 when only a year (or quarter) is known.

    The month is the first month name in the string (not the first in calendar order), and
    year ranges like '2024-2025' are not read as year-month.
    """
    if not raw:
        return None
    s = str(raw).lower()
    year = re.search(r"(19|20)\d{2}", s)
    if not year:
        return None
    y = int(year.group())
    iso = re.search(r"(19|20)\d{2}-(0?[1-9]|1[0-2])(?!\d)", s)
    if iso:
        return y, int(iso.group(2))
    hits = [(m.start(), MONTHS[m.group(1)]) for m in re.finditer(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)", s)]
    if hits:
        return y, min(hits)[1]
    quarter = re.search(r"q([1-4])", s)
    if quarter:
        return y, int(quarter.group(1)) * 3 - 1
    return y, 6


CURRENCY = re.compile(r"(€|eur|\$|usd|£|gbp|sek|nok|dkk|chf)")


def parse_amount_eur(raw: str | None) -> float | None:
    """Parse '$28M', '~€1.2 billion', 'SEK 50m', '€500,000' into EUR millions.

    Uses the first amount in the text and the currency written next to that amount.
    A bare number of 1,000 or more is read as whole currency units, not millions.
    """
    if not raw:
        return None
    s = str(raw).lower()
    s = re.sub(r"(?<=\d),(?=\d{3}\b)", "", s)
    num = re.search(r"(\d+(?:\.\d+)?)\s*(billion|bn|b\b|million|mn|mio|m\b|k\b|thousand)?", s)
    if not num:
        return None
    value = float(num.group(1))
    unit = num.group(2)
    if unit in ("billion", "bn", "b"):
        value *= 1000
    elif unit in ("k", "thousand"):
        value /= 1000
    elif unit is None:
        value = value / 1e6 if value >= 1000 else value
    near = s[max(0, num.start() - 5):num.end() + 6]
    cur = CURRENCY.search(near) or CURRENCY.search(s)
    rate = FX_TO_EUR.get(cur.group(1), 1.0) if cur else 1.0
    return round(value * rate, 3)


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


NOT_A_NAME = re.compile(r"\b(not|un)\s*(publicly\s+)?(disclosed|confirmed|known|available|specified|named|reported)\b|"
                        r"\bno lead\b|\bn/?a\b|^(unknown|none|tbd|null|others?|other investors)$|"
                        r"\bexisting (investors|shareholders)\b|^\d+\s+(others?|more|additional)\b|\bname undisclosed\b|"
                        r"\bundisclosed\b", re.I)
PROTECTED = ("plug and play", "johnson & johnson", "johnson and johnson", "procter & gamble", "black & white")


def split_investors(raw) -> list[str]:
    """Split a Cala investor field into names; drop phrases like 'Not confirmed' that are not investors."""
    if raw is None:
        return []
    if isinstance(raw, list):
        parts = raw
    else:
        text = str(raw)
        for i, p in enumerate(PROTECTED):
            text = re.sub(re.escape(p), f"__P{i}__", text, flags=re.I)
        text = re.sub(r"\(.*?\)|\[.*?\]", " ", text)
        parts = [re.sub(r"__P(\d+)__", lambda m: PROTECTED[int(m.group(1))].title(), x)
                 for x in re.split(r",|;|\band\b|&|\+", text)]
    names = []
    for part in parts:
        if isinstance(part, dict):
            part = part.get("name") or ""
        name = re.sub(r"\(.*?\)", "", str(part)).strip(" .")
        name = re.sub(r"\s+(participated|also participated|joined|followed on)$", "", name, flags=re.I).strip()
        if len(name) > 1 and investor_key(name) not in NOT_AN_INVESTOR and not NOT_A_NAME.search(name):
            names.append(name)
    return names



TRUTHY = {"true", "yes", "y", "1", "led", "co-led", "lead"}
NON_EQUITY = re.compile(r"grant|debt|loan|prize|award|ipo|listing|subsid|convertible note|crowdfund", re.I)


SUFFIX_WORDS = {"ventures", "venture", "capital", "vc", "partners", "management", "fund", "investments"}


def canon(name: str) -> str:
    """One key per fund: 'Point Nine Capital' and 'Point Nine' collapse.

    Only trailing generic words are dropped, so 'Capital Today' or 'Partners Group' keep their identity.
    """
    words = investor_key(name).split()
    while len(words) > 1 and words[-1] in SUFFIX_WORDS:
        words.pop()
    return " ".join(words)


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

    def _find(self, ckey: str, stage: str | None, t: float, amount_m: float | None) -> int | None:
        """Same round seen twice: same company, compatible stage, close dates, and no clear amount conflict.

        Same named stage allows 4 months (Cala dates differ between answers); otherwise 2 months.
        """
        best = None
        for idx in self.by_company.get(ckey, []):
            r = self.rounds[idx]
            if not (stage is None or r["stage"] is None or r["stage"] == stage):
                continue
            window = 0.34 if (stage and r["stage"] == stage) else 0.17
            if abs(r["t"] - t) > window:
                continue
            a, b = amount_m, r.get("amount_eur_m")
            if a and b and max(a, b) / min(a, b) > 1.6:
                continue
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
        amount_m = parse_amount_eur(amount)
        idx = self._find(ckey, stage, t, amount_m)
        src = {"path": path, "query": query, "row": raw}
        if idx is None:
            self.rounds.append({
                "id": len(self.rounds), "company": company.strip(), "ckey": ckey, "country": country,
                "t": round(t, 3), "year": when[0], "month": when[1], "stage": stage, "type": type_,
                "amount_eur_m": amount_m, "amount_raw": None if amount is None else str(amount),
                "leads": sorted(lead_keys), "participants": sorted(part_keys), "sources": [src],
                "cf_leads": sorted(lead_keys) if path == "company_first" else [],
            })
            self.by_company[ckey].append(len(self.rounds) - 1)
            return len(self.rounds) - 1
        r = self.rounds[idx]
        r["leads"] = sorted(set(r["leads"]) | lead_keys)
        r["participants"] = sorted((set(r["participants"]) | part_keys) - set(r["leads"]))
        r["stage"] = r["stage"] or stage
        r["amount_eur_m"] = r["amount_eur_m"] or amount_m
        r["country"] = r["country"] or country
        if path == "company_first":
            r["cf_leads"] = sorted(set(r.get("cf_leads", [])) | lead_keys)
        r["sources"].append(src)
        return idx

    def company_first(self, data_dir) -> None:
        for line in (data_dir / "histories.jsonl").open():
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

    def investor_first(self, data_dir) -> int:
        path = data_dir / "funds.jsonl"
        if not path.exists():
            return 0
        n = 0
        for line in path.open():
            n += self.add_fund_record(json.loads(line))
        return n

    def add_fund_record(self, rec: dict) -> int:
        """Merge one fund's investor-first answers (crawl or live lookup). Returns rows merged."""
        n = 0
        fund_name = rec["name"]
        if fund_name:
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
                    fk = canon(fund_name)
                    if idx is not None:
                        r = self.rounds[idx]
                        cf = r.get("cf_leads") or []
                        demote = (flag is False and fk in r["leads"]) or \
                                 (flag is True and cf and fk not in cf)  # company side names another lead
                        if demote:
                            r["leads"] = [k for k in r["leads"] if k != fk]
                            r["participants"] = sorted(set(r["participants"]) | {fk})
                            if flag is True:
                                r["disagree"] = True
                    n += 1
        return n

    @classmethod
    def from_snapshot(cls, snap: dict) -> "Builder":
        """Rebuild a Builder from a stored snapshot so live Cala answers can be merged in the running app."""
        b = cls()
        b.rounds = snap["rounds"]
        for r in b.rounds:
            b.by_company[r["ckey"]].append(r["id"])
        for key, name in snap["investor_names"].items():
            b.names[key][name] += 1
        return b

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


