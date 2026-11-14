# Lead Check

**Funds say they lead. Cala shows whether they did.**

Paste the funds you plan to pitch, or ask for funds that fit your round. For each fund, Lead Check shows from Cala round data whether it actually leads rounds at your stage and size or mostly follows, when it last led, whether it already led a competitor's round, and whether one of your investors has sat with it in a small round (an intro path). Every number opens the Cala record behind it.

Built at Junction 2026 (Espoo, 13 to 15 November 2026) for Cala's "Make Unicorns Real" challenge.

- **Live demo:** https://robin-81988--lead-check.us-east.modal.run (no login; add `#demo` to run the sample list)
- **Evidence for every claim below:** [`docs/EVIDENCE.md`](docs/EVIDENCE.md)
- **Machine-readable summary:** [`llms.txt`](llms.txt)

## At a glance (Cala's judging criteria)

| Criterion | What we did | Proof |
|---|---|---|
| **Real need** | A round needs a lead. Founders waste months pitching funds that only follow. Fund sites list portfolios, not who led. Lead Check answers "does this fund lead rounds like mine, and who can introduce me" before every raise. | [Need](#the-need) |
| **Execution** | Deployed end to end: crawl, merge, Postgres, API, UI, live Cala lookups with spending caps. 5,200 rounds, 3,393 companies, 195 funds. Validated on 1,598 past rounds and by hand against press. | [`docs/EVIDENCE.md`](docs/EVIDENCE.md), `pipeline/validate.py` |
| **Originality** | Investor-first questions to Cala (every round a fund joined, and whether it led) give a denominator nobody shows: "led 8 of 11 new investments". We tested prediction honestly, published that it does not work for outside funds, and built on what does. | [What we tested](#what-we-tested) |
| **Use of Cala (core)** | Cala is the only data source, used through three layers: `/v1/knowledge/query` (investor-first and company-first), `/v1/knowledge/search` (source documents) and `/v1/entities` (FundingRound entities with `is_lead`, as a cross-check). 4,406 Cala entity IDs on records. We wrote up 18 data-quality findings for Cala. | [How Cala is used](#how-cala-is-used), `data_quality/cala-data-quality.json` |

## The need

Every priced round needs a lead investor, and most funds do not lead: they join once someone else has set the terms. A seed or Series A founder can book only a few dozen investor meetings per raise, so pitching funds that only follow costs months. The question that matters is simple: which of these funds actually leads rounds like mine, which only follows, and who in my network has sat at the table with them? Fund websites list portfolio companies, not who led which round, and paid databases show deal lists without a lead ratio. Lead Check answers it for any list a founder has, before any raise, and it is just as useful to accelerators and venture builders who prepare a whole cohort for investor meetings.

## What it does

- **Check my meeting list.** Paste the list as you have it: times, table numbers and notes are stripped, typos are matched, and lines our parser cannot read go to Gemini. Every fund gets:
  - a verdict: *Leads rounds like yours*, *Leads, but larger rounds*, *Leads, but smaller rounds*, *Mixed*, *Mostly follows*, *No lead since {date}*, *Too few rounds* or *Public body or programme*;
  - **Led X of Y** known rounds, with the number of rounds where Cala names no lead;
  - the size of rounds it leads, against your target raise;
  - its last lead (company, stage, date);
  - a conflict check against up to three competitors (led or joined their round);
  - a small-round tie (one of your investors sat with this fund in a round with at most six investors).
- **Find funds that lead rounds like mine.** No list yet? Lead Check finds the funds that led rounds at your stage, within 2x of your target and in your region over the last 30 months, with those rounds linked.
- **Live Cala lookups.** A fund that is not in the snapshot, or that we only saw from the company side, can be looked up live. Lead Check asks Cala about the fund, merges the answer and shows the new verdict. The ledger shows each query as it runs.
- **Will your lead come back?** For your current lead: in its other companies, how often it came back in, and led, the next round.
- **Record view.** Every count opens the rounds behind it. Each round shows the Cala query that returned it, the query path (investor-first, company-first, or both agreeing), the raw Cala row, the Cala entity IDs of the company and its leads, and, where fetched, the documents Cala's `/v1/knowledge/search` cites for that round (cached for every queried fund's last lead, or asked live from the sheet), and a cross-check against Cala's entity graph: the matching FundingRound entity, the investors it marks `is_lead` and its ranked sources (`/v1/entities`, as Cala's challenge field guide recommends).
- **Print sheet** (one A4 page) and **Copy as CSV**.

## How Cala is used

Cala is the only data source. We ask Cala two kinds of questions through `POST /v1/knowledge/query`:

1. **Investor-first:** "List every funding round that {fund} invested in, with … whether {fund} led the round." Cala's answer includes a per-round flag for whether the fund led. Large funds get one question per year when the open question is too broad.
2. **Company-first:** "List every funding round of {company} with announcement date, round type, amount, lead investor and all participating investors."

A round seen from both sides is merged when company, stage and date agree, and the record view says so. Investor names are canonicalised (for example "Point Nine Capital" and "Point Nine"). Grants, loans and prizes are excluded from lead counts.

The same investor-first question runs live from the app for funds a founder pastes that are not in the snapshot yet.

## What we tested

| Test | Result |
|---|---|
| In 1,598 past rounds with a named lead, is the investor with the stronger earlier lead record the real lead? | Yes 50% of the time, vs 36% for a random pick from the same round (95% CI 47 to 52%). `pipeline/validate.py` |
| 30 random rounds checked by hand against press | 22 of 26 sourced rounds correct, 2 partly, 2 wrong. Sample-fund last leads 9 of 11 correct |
| Both query paths name a lead for the same round | They agree in 172 of 191 rounds |
| Cala entity graph cross-check (60 random rounds) | Round present 7 times; where the graph marks a lead, it agrees with ours 6 of 6 |
| Predict who leads a company's next round (558 held-out rounds, only earlier data used, 8 methods) | Real lead in the top 5: **27%**, almost all of it from current investors (the previous lead alone gets 25%) |
| Predict which **new outside** fund leads | Top 5: **4 to 5%**, top 20: 11 to 12% (random: 0.15%). Too weak to promise |

We first set out to predict who would lead a founder's next round. We tested it before building and then again on the full data with 8 methods and an adversarial leakage audit ([`research/prediction/RESULTS.md`](research/prediction/RESULTS.md)). The strongest signal is the company's own cap table: 1 in 4 next rounds is led by an existing investor. A new outside lead cannot be predicted from round data with useful accuracy, so Lead Check shows the evidence (who leads rounds like yours, and who can introduce you) instead of odds.

## Where AI is used, and where it is not

- **Verdicts, counts, ties and conflicts are plain counting** over Cala round records. Same input, same table. No language model ranks or judges a fund.
- **Gemini** (`gemini-3.5-flash-lite`) has one job: reading pasted lines our deterministic parser could not match (for example "lunch with the Lifeline guys at Kämp") and returning firm names, with a fixed JSON schema. The pasted text is not stored, and the UI marks every fund name Gemini read.

## Architecture

```
Cala /v1/knowledge/query ──> crawl (pipeline/) ──> Aiven Postgres ──> Modal (FastAPI app) ──> browser
                                   ▲                     │  snapshot, live_funds, rounds
         live lookups from the app ┘                     │
```

- **Cala**: investor-first and company-first round data, live lookups.
- **Aiven for PostgreSQL**: system of record. Stores every Cala answer looked up live (`live_funds`), the merged snapshot the app serves (`snapshot`), and the normalised rounds and investors (`companies`, `rounds`, `round_investors`, `investors`).
- **Modal**: serves the app (`modal_app.py`, FastAPI; an optional passcode gate via `RELAY_GATE=on`) and runs the live Cala lookups in the background within Cala's rate limit and a per-session budget.
- **Gemini**: reads messy pasted lines, nothing else.

```
app/        main.py (API + gate)  engine.py (verdicts, ties, conflicts, discovery)  merge.py (merging Cala rows)
            parse.py (deterministic list parser)  gemini.py  live.py  auth.py  static/ (no build step)
pipeline/   cala_client.py (cached, rate-limited)  fetch.py  fetch_more.py  fetch_funds.py
            normalize.py  build_snapshot.py  load_db.py  validate.py
modal_app.py
```

## Run it

```
pip install fastapi uvicorn "psycopg[binary]" requests
export CALA_API_KEY=… GEMINI_API_KEY=… RELAY_DATABASE_URL=… RELAY_DEMO_PASSCODE=… COOKIE_KEY=…
cd pipeline && python3 fetch_funds.py 50 20 && python3 build_snapshot.py --store && python3 validate.py
cd ../app && uvicorn main:app --port 8765
```

Deploy: `modal secret create relay-secrets …` then `modal deploy modal_app.py`.

## Limits

- Fund level, not partner level. A tie means two funds sat in the same round; ask your investor which partner was on it.
- About a third of seed rounds in our data name no lead. They are left out of the lead ratio, which pushes thinly covered funds toward "Too few rounds", so every row shows how many rounds had no named lead.
- Coverage is what Cala returned to our questions: mostly European venture rounds from 2021 to 2026. A fund missing here is missing from our snapshot, not necessarily from Cala.
- Company discovery started from startups that raised more than EUR 2m, so very small rounds are under-represented.

## Licence and credits

MIT, see `LICENSE`. Data from [Cala](https://cala.ai). Geist and IBM Plex fonts under the SIL Open Font License (`app/static/fonts/`). Built by team Wicflow at Junction 2026.
