# Lead Check

**Funds say they lead. Cala shows whether they did.**

Paste the funds you are meeting at Slush. For each one, Lead Check shows from Cala round data whether it actually leads rounds at your stage and size or mostly follows, when it last led, whether it already led a competitor's round, and whether one of your investors has sat with it on a small cap table. Every number opens the Cala record behind it.

Built at Junction 2026 (Espoo, 13 to 15 November 2026) for Cala's "Make Unicorns Real" challenge.

## The need

A seed or Series A founder going to Slush books a dozen 25-minute meetings out of thousands of investors. The question that matters is simple: which of these funds actually leads rounds like mine, and which only follows once someone else does? Fund websites list portfolio companies, not who led which round. That is the gap Lead Check fills, for the list the founder already has.

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
- **Record view.** Every count opens the rounds behind it. Each round shows the Cala query that returned it, the query path (investor-first, company-first, or both agreeing) and the raw Cala row.
- **Print my Slush sheet** (one A4 page) and **Copy as CSV**.

## How Cala is used

Cala is the only data source. We ask Cala two kinds of questions through `POST /v1/knowledge/query`:

1. **Investor-first:** "List every funding round that {fund} invested in, with … whether {fund} led the round." Cala's answer includes a per-round flag for whether the fund led. Large funds get one question per year when the open question is too broad.
2. **Company-first:** "List every funding round of {company} with announcement date, round type, amount, lead investor and all participating investors."

A round seen from both sides is merged when company, stage and date agree, and the record view says so. Investor names are canonicalised (for example "Point Nine Capital" and "Point Nine"). Grants, loans and prizes are excluded from lead counts.

The same investor-first question runs live from the app for funds a founder pastes that are not in the snapshot yet.

## What we tested

| Test | Result |
|---|---|
| In a round with a named lead, is the investor with the stronger earlier lead record the real lead? | See the Method page; recomputed on every data refresh (`pipeline/validate.py`) |
| Predicting a round's new lead from earlier rounds (top 5, held-out rounds) | 1.4%, the same as chance |

We first tried to predict who would lead a founder's next round. On held-out rounds it did no better than chance: most leads in the data led only one round we could see. So Lead Check reports what funds did, not odds about what they will do.

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
- **Modal**: serves the app (`modal_app.py`, FastAPI behind a passcode gate) and runs the live Cala lookups in the background within Cala's rate limit and a per-session budget.
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

MIT, see `LICENSE`. Data from [Cala](https://cala.ai). IBM Plex fonts under the SIL Open Font License (`app/static/fonts/OFL-IBM-Plex.txt`). Built by team Wicflow at Junction 2026.
