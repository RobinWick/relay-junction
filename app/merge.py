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
UNDISCLOSED = re.compile(r"undisclosed|not (?:publicly )?disclosed", re.I)
VALUATION = re.compile(r"valuation|valued|\bval\.|pre-money|post-money", re.I)


def parse_amount_eur(raw: str | None) -> float | None:
    """Parse '$28M', '~€1.2 billion', 'SEK 50m', '€500,000' into EUR millions.

    Uses the first amount in the text and the currency written next to that amount.
    A bare number of 1,000 or more is read as whole currency units, not millions.
    Returns None when the text says the amount is undisclosed, and never reads a valuation as the round size:
    only text before a valuation phrase counts ('Undisclosed (valuation >$500M)' -> None,
    'SEK 400 million (Valuation: SEK 5.0 billion)' -> SEK 400m).
    """
    if not raw or UNDISCLOSED.search(str(raw)):
        return None
    s = str(raw).lower()
    val = VALUATION.search(s)
    if val:
        s = s[:val.start()]
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
                        r"\bundisclosed\b|^not\b|\bno\s+(?:[\w-]+\s+){0,3}leads?\b|\bnot (explicitly|separately)\b|"
                        r"^(seed|led seed|first round|round ?\d+|pre-?seed|series [a-f]|lead|leads|co-?lead)$|"
                        r"^(multiple|several|various|many)\b|^participants?$|\bbroad syndicate\b|\bprivate investors\b|"
                        r"^an?\s+(prominent|undisclosed|unnamed|large|major|leading|well-known|group|number|consortium)\b|"
                        r"^(group|number|consortium|syndicate) of\b|\b[\w-]+[- ]based family office\b", re.I)
# trailing role words Cala writes into a name ('PhotonVentures, co-leads', 'NEA & others', 'X-led consortium')
NAME_TRAIL = re.compile(r"\s*[-\u2010-\u2015]*\s*\bco-?leads?\s*$|\s*(?:&|\band\b|\+)\s*others?\s*$|[-\u2010-\u2015\s]+led consortium\s*$"
                        r"|\s+(?:were|was|is|are)\s+(?:the\s+|key\s+)?(?:co-?)?(?:investors?|leads?)\s*$", re.I)
NAME_LEADIN = re.compile(r"^(?:round\s+)?(?:backed|led)\s+by\s+", re.I)
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
                 for x in re.split(r",|;|\band\b|\+", text)]
    fundish = re.compile(r"\b(ventures?|capital|partners|vc|fund|invest\w*|holdings?|labs)\b", re.I)
    expanded = []
    for part in parts:
        if isinstance(part, str) and "&" in part:
            sides = [x.strip() for x in part.split("&")]
            # 'Lifeline Ventures & Kvanted' is two funds; 'Larsen & Toubro Group' is one firm
            if len(sides) == 2 and (fundish.search(sides[0]) or fundish.search(sides[1])) and all(len(x) > 2 for x in sides):
                expanded.extend(sides)
                continue
        expanded.append(part)
    parts = expanded
    names = []
    for part in parts:
        if isinstance(part, dict):
            part = part.get("name") or ""
        name = re.sub(r"\(.*?\)", "", str(part)).strip(" .")
        name = re.sub(r"\s+(participated|also participated|joined|followed on)$", "", name, flags=re.I).strip()
        name = NAME_LEADIN.sub("", NAME_TRAIL.sub("", name)).strip(" .,-")
        if len(name) > 1 and investor_key(name) not in NOT_AN_INVESTOR and not NOT_A_NAME.search(name):
            names.append(name)
    return names



TRUTHY = {"true", "yes", "y", "1", "led", "co-led", "lead"}
NON_EQUITY = re.compile(r"grant|debt|loan|prize|award|ipo|listing|subsid|convertible note|crowdfund", re.I)


SUFFIX_WORDS = {"ventures", "venture", "capital", "vc", "partners", "management", "fund", "investments"}


ALIASES = {"vtt technical research centre of finland": "vtt", "92 ventures 92": "92", "92 ventures / 92 capital": "92",
           "harjavalta oy": "harjavalta", "point 9": "point nine", "creandum ab": "creandum",
           "european innovation council fund": "eic fund", "illusian founder office": "illusian"}


def canon(name: str) -> str:
    """One key per fund: 'Point Nine Capital' and 'Point Nine' collapse.

    Only trailing generic words are dropped, so 'Capital Today' or 'Partners Group' keep their identity.
    """
    key = investor_key(name)
    if key in ALIASES:
        return ALIASES[key]
    words = key.split()
    while len(words) > 1 and words[-1] in SUFFIX_WORDS:
        words.pop()
    out = " ".join(words)
    return ALIASES.get(out, out)


def company_key(name: str) -> str:
    s = re.sub(r"\(.*?\)", "", str(name).lower())
    s = re.sub(r"\b(oy|ab|as|gmbh|ltd|inc|sa|bv|aps|oyj|plc)\b", "", s)
    return re.sub(r"[^a-z0-9]", "", s)


def _field(row: dict, *names: str):
    for n in names:
        if row.get(n) not in (None, "", []):
            return row[n]
    return None


LEAD_FIELDS = ("lead_investor", "lead_investors", "lead")
PART_FIELDS = ("participating_investors", "all_participating_investors", "investors", "other_investors", "co_investors",
               "participants")


OPEN_LIST = re.compile(r"(?:,|\band\b|\+|\bplus\b|\bamong\b|\bincluding\b)\s*(\d+\s+)?(others?|more)\b|\betc\b|"
                       r"\bundisclosed\b|\bnot (fully |publicly )?disclosed\b", re.I)  # a list that says it is partial


def _compact(s: str) -> str:
    """Lower-case letters and digits only, accents folded, brackets kept ('Wingman Ventures (Founderful)')."""
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower())


def _names_fund(row: dict, fund_name: str, parts: list[str]) -> bool:
    """May the queried fund be put in this row's round as a participant?

    Yes when the row's lead or participant text names it. Also yes when the row lists no participants at all
    (field missing or 'Not disclosed'): the row comes from the fund's own answer and nothing in it says otherwise.
    No when the row lists participants and the fund is not among them (Tencent on Uzum's Mar 2024 round).
    """
    key = canon(fund_name)
    text = " ".join(str(row.get(f) or "") for f in LEAD_FIELDS + PART_FIELDS)
    if not parts or any(canon(x) == key for x in parts) or OPEN_LIST.search(text):
        return True
    flat = _compact(text)
    return any(len(c) >= 4 and c in flat for c in {key.replace(" ", ""), _compact(fund_name)})


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
        self.by_prefix: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
        self.names: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self.entities: dict[str, str] = {}  # "c:<company key>" / "i:<investor key>" -> Cala entity id

    def add_entities(self, entities: list | None) -> None:
        """Remember Cala's entity ids for the companies and funds a query answer mentions (first id wins)."""
        for e in entities or []:
            if not isinstance(e, dict) or e.get("entity_type") not in ("Company", "Organization") or not e.get("id"):
                continue
            for name in {e.get("name") or "", *(e.get("mentions") or [])}:
                if name.strip():
                    self.entities.setdefault("c:" + company_key(name), e["id"])
                    self.entities.setdefault("i:" + canon(name), e["id"])

    def _name(self, raw: str) -> str:
        k = canon(raw)
        self.names[k][raw.strip()] += 1
        return k

    def _candidates(self, ckey: str) -> list[int]:
        """Rounds of the same company, also under a longer or shorter name ('Marble' / 'Marble Cognition')."""
        out = list(self.by_company.get(ckey, []))
        if len(ckey) >= 5:
            for other, idxs in self.by_prefix.get(ckey[:5], {}).items():
                if other != ckey and (other.startswith(ckey) or ckey.startswith(other)):
                    out.extend(idxs)
        return out

    def _find(self, ckey: str, stage: str | None, t: float, amount_m: float | None) -> int | None:
        """Same round seen twice: same company, compatible stage, close dates, and no clear amount conflict.

        Same named stage allows 4 months (Cala dates differ between answers); otherwise 2 months.
        """
        best = None
        for idx in self._candidates(ckey):
            r = self.rounds[idx]
            b = r.get("amount_eur_m")
            same_money = bool(amount_m and b and max(amount_m, b) / min(amount_m, b) <= 1.15)
            if same_money and abs(r["t"] - t) <= 0.5:  # same amount within 6 months: one round, labels differ
                if best is None or abs(r["t"] - t) < abs(self.rounds[best]["t"] - t):
                    best = idx
                continue
            if r["ckey"] != ckey:
                continue
            new_leads = getattr(self, "_pending_leads", set())
            if new_leads and set(r["leads"]) == new_leads and abs(r["t"] - t) <= 0.17:
                # same company, same month, same named lead: one round with two stage labels (Roleo)
                if best is None or abs(r["t"] - t) < abs(self.rounds[best]["t"] - t):
                    best = idx
                continue
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
        self._pending_leads = lead_keys
        idx = self._find(ckey, stage, t, amount_m)
        src = {"path": path, "query": query, "row": raw}
        if idx is None:
            self.rounds.append({
                "id": len(self.rounds), "company": re.sub(r"\s*\(.*?\)", "", company).strip() or company.strip(),
                "ckey": ckey, "country": country,
                "t": round(t, 3), "year": when[0], "month": when[1], "stage": stage, "type": type_,
                "amount_eur_m": amount_m, "amount_raw": None if amount is None else str(amount),
                "leads": sorted(lead_keys), "participants": sorted(part_keys), "sources": [src],
                "cf_leads": sorted(lead_keys) if path == "company_first" else [],
            })
            self.by_company[ckey].append(len(self.rounds) - 1)
            self.by_prefix[ckey[:5]][ckey].append(len(self.rounds) - 1)
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
            self.add_entities(rec.get("entities"))
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
        """Merge one fund's investor-first answers (crawl or live lookup). Returns rows merged.

        The queried fund is attributed only when the row says so: its led flag is yes (then it is a lead), or its own
        lead or participant text names the fund. A row that never names the fund ('Uzum, Mar 2024' in Tencent's
        answer) keeps its round but does not put the fund in it.
        """
        n = 0
        fund_name = rec["name"]
        if fund_name:
            for q in rec["queries"]:
                self.add_entities(q.get("entities"))
                for row in q["rows"]:
                    company = _field(row, "company", "company_name", "startup", "name")
                    leads = split_investors(_field(row, *LEAD_FIELDS))
                    parts = split_investors(_field(row, *PART_FIELDS))
                    flag = _led_flag(row)
                    fund_in_leads = any(canon(x) == canon(fund_name) for x in leads)
                    if flag is True and not fund_in_leads:
                        leads.append(fund_name)
                    elif flag is not True and not fund_in_leads and _names_fund(row, fund_name, parts):
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
                        demote = (flag is False and fk in r["leads"] and fk not in cf) or \
                                 (flag is True and cf and fk not in cf)  # company side names another lead
                        if demote:
                            r["leads"] = [k for k in r["leads"] if k != fk]
                            r["participants"] = sorted(set(r["participants"]) | {fk})
                            if flag is True:
                                r["disagree"] = True
                    n += 1
        return n

    def fold_duplicates(self) -> int:
        """Fold rounds that are one round seen twice, so no round is counted twice. Returns rounds folded away.

        Same company (or one name a prefix of the other, 4+ letters) and compatible stage, and either
          A. the same named leads and the same amount (within 15% inside 6 months, else within 6%), up to 3 years
             apart: Cala dated one round twice
             (ConfidentialMind Nov 2023 and Apr 2026, Zenniz 'End of 2024' and Mar 2025, Solu and Solu Genomics), or
          B. one side names no lead, is within 2 months, and every investor it names is in the other round
             (Camphouse Jun 2026 told twice). A side with no lead and no amount in the same month may also carry
             a different stage label (Reduciner's 'Series A' row next to its May 2026 first round).
        The round with the more precise date survives (then more investors, then the later date).
        """
        by_family: dict[str, list[int]] = defaultdict(list)
        for r in self.rounds:
            by_family[r["ckey"][:4]].append(r["id"])
        gone: set[int] = set()
        for ids in by_family.values():
            for i in ids:
                for j in ids:
                    if i >= j or i in gone or j in gone:
                        continue
                    a, b = self.rounds[i], self.rounds[j]
                    if not _same_round(a, b):
                        continue
                    keep, drop = sorted((a, b), key=_survivor_rank, reverse=True)
                    _absorb(keep, drop)
                    gone.add(drop["id"])
        if not gone:
            return 0
        self.rounds = [r for r in self.rounds if r["id"] not in gone]
        self.by_company, self.by_prefix = defaultdict(list), defaultdict(lambda: defaultdict(list))
        for i, r in enumerate(self.rounds):
            r["id"] = i
            self.by_company[r["ckey"]].append(i)
            self.by_prefix[r["ckey"][:5]][r["ckey"]].append(i)
        return len(gone)

    @classmethod
    def from_snapshot(cls, snap: dict) -> "Builder":
        """Rebuild a Builder from a stored snapshot so live Cala answers can be merged in the running app."""
        b = cls()
        b.rounds = snap["rounds"]
        for r in b.rounds:
            b.by_company[r["ckey"]].append(r["id"])
            b.by_prefix[r["ckey"][:5]][r["ckey"]].append(r["id"])
        for key, name in snap["investor_names"].items():
            b.names[key][name] += 1
        b.entities = dict(snap.get("entities", {}))
        return b

    def snapshot(self, fund_keys: set[str]) -> dict:
        folded = self.fold_duplicates()
        for r in self.rounds:
            reason = r.get("not_led") or not_led_reason(r)
            if reason:
                mark_not_led(r, reason)
        names = {k: max(v.items(), key=lambda kv: kv[1])[0] for k, v in self.names.items()}
        for r in self.rounds:
            paths = {s["path"] for s in r["sources"]}
            r["query_path"] = "both" if len(paths) > 1 else paths.pop()
        companies = len({r["ckey"] for r in self.rounds})
        used = {"c:" + r["ckey"] for r in self.rounds} | {"i:" + k for k in names}
        entities = {k: v for k, v in self.entities.items() if k in used}
        return {
            "version": datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"),
            "retrieved": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "rounds": self.rounds, "investor_names": names, "fund_keys": sorted(fund_keys), "entities": entities,
            "stats": {"rounds": len(self.rounds), "companies": companies, "funds_queried": len(fund_keys),
                      "investors": len(names), "entity_ids": len(entities), "folded_duplicates": folded,
                      "not_led_rounds": sum(1 for r in self.rounds if r.get("not_led"))},
        }




DAY = re.compile(r"\b\d{1,2}(st|nd|rd|th)?\.?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)|"
                 r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2}\b(?!\d)|\b(19|20)\d\d-\d\d-\d\d\b", re.I)
VAGUE = re.compile(r"approx|~|\bend of\b|\bearly\b|\blate\b|\bmid\b|\bq[1-4]\b|\bh[12]\b|\baround\b|\bc\.", re.I)


def _date_precision(r: dict) -> int:
    """3 = day given, 2 = month, 1 = year, quarter or 'approximate', 0 = no date text."""
    best = 0
    for s in r.get("sources", []):
        row = s.get("row") or {}
        raw = str(_field(row, "date", "announcement_date", "announced", "year") or "")
        if not raw:
            continue
        if VAGUE.search(raw):
            p = 1
        elif DAY.search(raw):
            p = 3
        elif parse_date(raw) and (re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)", raw, re.I)
                                  or re.search(r"(19|20)\d\d-\d\d", raw)):
            p = 2
        else:
            p = 1
        best = max(best, p)
    return best


def _same_family(a: str, b: str) -> bool:
    return a == b or (min(len(a), len(b)) >= 4 and (a.startswith(b) or b.startswith(a)))


def _same_round(a: dict, b: dict) -> bool:
    if not _same_family(a["ckey"], b["ckey"]):
        return False
    dt = abs(a["t"] - b["t"])
    x, y = a.get("amount_eur_m"), b.get("amount_eur_m")
    if a["stage"] and b["stage"] and a["stage"] != b["stage"]:
        # only a bare echo (no lead, no amount, same month) may carry a wrong stage label: Reduciner May 2026
        bare = a if not (a["leads"] or x) else b if not (b["leads"] or y) else None
        if bare is None or dt > 0.09:
            return False
    if a["leads"] and b["leads"]:
        # months apart: the amount must be the same figure (FX rounding only); years apart: still one Cala text
        tolerance = 1.15 if dt <= 0.5 else 1.06
        return (set(a["leads"]) == set(b["leads"]) and bool(x and y) and max(x, y) / min(x, y) <= tolerance
                and dt <= 3.0)
    if dt > 0.17:
        return False
    for bare, full in ((a, b), (b, a)):
        named = set(bare["participants"])
        if not bare["leads"] and named and named <= set(full["leads"]) | set(full["participants"]):
            return True
    return False


def _survivor_rank(r: dict) -> tuple:
    return bool(r["leads"]), _date_precision(r), len(r["leads"]) + len(r["participants"]), r["t"]


def _absorb(keep: dict, drop: dict) -> None:
    keep["leads"] = sorted(set(keep["leads"]) | set(drop["leads"]))
    keep["participants"] = sorted((set(keep["participants"]) | set(drop["participants"])) - set(keep["leads"]))
    keep["cf_leads"] = sorted(set(keep.get("cf_leads", [])) | set(drop.get("cf_leads", [])))
    for f in ("stage", "amount_eur_m", "amount_raw", "country", "type"):
        if keep.get(f) in (None, ""):
            keep[f] = drop.get(f)
    keep["sources"] = keep["sources"] + drop["sources"]
    keep["disagree"] = keep.get("disagree") or drop.get("disagree")
    if not keep.get("disagree"):
        keep.pop("disagree", None)


PROGRAMME = re.compile(r"\baccelerator\b|\bincubat|support program|\bprogramme\b", re.I)
LISTED_ISSUE = re.compile(r"\bpipe\b|directed (share )?issues?|rights issues?|\bspac\b|public offering", re.I)


def not_led_reason(r: dict) -> str | None:
    """A round no fund 'leads' in the sense a founder means: an accelerator or support programme cheque, or a share
    issue by a listed company. Only when every source row's round type says so; a round that one source calls a
    seed keeps counting."""
    types = [str(_field(s.get("row") or {}, "round_type", "type", "round") or "") for s in r.get("sources", [])]
    types = [t for t in types if t.strip()] or [str(r.get("type") or "")]
    if all(PROGRAMME.search(t) for t in types):
        return "Accelerator or support programme, not a led round"
    if all(LISTED_ISSUE.search(t) for t in types):
        return "Share issue by a listed company (PIPE, directed or rights issue), not a led round"
    return None


def mark_not_led(r: dict, reason: str) -> None:
    """Keep the round on record but out of every lead count: named leads move to the investor list."""
    r["not_led"] = reason
    if r["leads"]:
        r["named_leads"] = sorted(set(r.get("named_leads", [])) | set(r["leads"]))
        r["participants"] = sorted(set(r["participants"]) | set(r["leads"]))
        r["leads"] = []


def round_key(r: dict) -> str:
    return f"{r['ckey']}|{r['year']}|{r['month']}|{r['stage'] or ''}"


def summarize_search(res: dict) -> dict:
    """Keep what the record view needs from a /v1/knowledge/search answer: the answer, its reasoning, and the
    documents it cites (https only), each with a short passage."""
    docs, seen = [], set()
    for ctx in res.get("context", []) or []:
        for o in ctx.get("origins", []) or []:
            doc = (o.get("document") or {})
            url = doc.get("url") or (o.get("source") or {}).get("url") or ""
            if not url.startswith("https://") or url in seen:
                continue
            seen.add(url)
            docs.append({"name": (doc.get("name") or (o.get("source") or {}).get("name") or url)[:160],
                         "site": ((o.get("source") or {}).get("name") or "")[:80], "url": url[:500],
                         "passage": (ctx.get("content") or "")[:420]})
    points = [e.get("content", "")[:300] for e in (res.get("explainability") or [])][:4]
    return {"answer": (res.get("content") or "")[:700], "points": points, "docs": docs[:5]}
