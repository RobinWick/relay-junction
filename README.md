# Recount

**Funds say they lead. Cala shows whether they did.**

Recount checks the funds a founder plans to pitch against Cala's funding-round records. For each fund it counts how many rounds it led at your stage, out of those where Cala names a lead, what size those rounds were, when it last led, and whether it backed a competitor. Then it looks for a way in: one of your investors who sat with that fund in a small round, or a LinkedIn connection at a company the fund backed, matched in your browser. Every number opens the Cala record behind it. Counting, not AI.

Built at Junction 2026 (Espoo, 13 to 15 November 2026) for Cala's "Make Unicorns Real" challenge.

- **Live demo:** https://robin-81988--recount.us-east.modal.run (no login; add `#demo` to load the sample)
- **Evidence for every number below:** [`docs/EVIDENCE.md`](docs/EVIDENCE.md)
- **Machine-readable summary:** [`llms.txt`](llms.txt)

## Check us in 60 seconds

1. **Open the demo and click "Try a sample"** (or open it with `#demo`). The sample is a seed founder raising EUR 3m, with Lifeline Ventures as an investor, Lovable as a competitor and 14 pasted lines.
2. **Read the summary line:** "8 of 14 mostly lead Seed rounds, 5 of them at a size like your EUR 3m. 2 lead, but a different size. 2 backed Lovable. You have a way in to 2." The funds sit in three groups: "Pitch first", "Leads, but a different size" and "Mostly follows or sometimes leads". (The last pasted line is messy and goes to Gemini for the fund name. If Gemini is unavailable, that line shows as not recognised and the summary reads 7 of 13, 4 at your size, way in to 1.)
3. **Click "Try with a sample network".** A made-up file of 9 connections, every match marked "Sample", is matched in your browser: "way in to 2" becomes "way in to 8". Click **Map** to see the same ways in as lines from you, through your investor or a contact, to each fund, in the list's groups and order. Hover Voima Ventures for the rounds behind its two lines.
4. **Open Voima Ventures.** It "Led 13 of 13" rounds with a named lead near your stage, and the pane says 7 more had no named lead. Under "How to get in": your investor Lifeline Ventures and Voima Ventures were both in Reduciner's round of May 2026, with 4 investors in total.
5. **Click Reduciner** to open the round record: "Found by: Asking about the fund and about the company, both agree", the Cala entity IDs, the source documents from Cala search, and the raw Cala rows. Every count in the app opens a record like this.

## At a glance (Cala's judging criteria)

| Criterion | What we did | One number | Proof |
|---|---|---|---|
| **Real need** | A round needs a lead, and the last lead rarely leads again, so most founders must find a new lead each round. Fund sites list portfolios, not who led. Recount answers "does this fund lead rounds like mine, and how do I get in" for any list, before any raise. | The lead of a round came back in the company's next round 60% of the time but led it again only 17% (1,489 cases) | `app/validation.json`, [Need](#the-need) |
| **Execution** | Deployed end to end: crawl, merge, Postgres, API, UI, live Cala lookups with spending caps. Wrong amounts and leads the source disputes are caught and left out. | 5,200 rounds, 3,393 companies, 195 funds; hand check 22 of 26 leads correct against press | [`docs/EVIDENCE.md`](docs/EVIDENCE.md), `pipeline/validate.py` |
| **Originality** | A lead count at your stage and size with its denominator and the rounds behind it, plus a way in from the same round records and your LinkedIn export, read in the browser. We tested prediction honestly and published that it does not work for outside funds. | Next outside lead in the top 5: 4 to 5% vs 0.15% random (462 rounds), so Recount shows evidence, not odds | [`research/prediction/RESULTS.md`](research/prediction/RESULTS.md), [How this differs](#how-this-differs-from-existing-tools) |
| **Use of Cala as the core** | Cala is the only data source, through three layers: `/v1/knowledge/query` (investor-first and company-first), `/v1/knowledge/search` (source documents) and `/v1/entities` (FundingRound entities, as a cross-check). We wrote up 19 data-quality findings for Cala. | Where both query paths name a lead, they share it in 172 of 191 rounds | [How Cala is used](#how-cala-is-used), `data_quality/cala-data-quality.json` |

## The need

Every priced round needs a lead investor, and most funds do not lead: they join once someone else has set the terms. The previous lead is rarely the answer: in our data the lead of a round came back in the next round 60% of the time but led it only 17% of the time. A seed or Series A founder can book only a few dozen investor meetings per raise, so pitching funds that only follow costs months. The question is simple: which of these funds actually leads rounds like mine, which only follows, and how do I get in? Fund websites list portfolio companies, not who led which round. Recount answers it for any list a founder has, and it is just as useful to accelerators and venture builders who prepare a whole cohort for investor meetings.

## What it does

- **Check a list.** Paste the funds you plan to pitch as you have them: times, table numbers and notes are stripped, typos are matched, and lines our parser cannot read go to Gemini. Set your stage, target raise, investors and up to three competitors. Funds are sorted into three groups: **Pitch first**, **Leads, but a different size**, and **Mostly follows or sometimes leads** (plus **Too little data to tell**). Each fund gets:
  - a verdict: *Leads rounds like yours*, *Leads at your stage, size unclear*, *Leads larger rounds*, *Leads smaller rounds*, *Sometimes leads*, *Mostly follows*, *No lead since {date}*, *Too little data* or *Public funder, not a lead*;
  - a **lead record**, "Led X of Y named", with a bar for led, joined and lead unnamed, and the number of rounds where Cala names no lead;
  - the size of rounds it leads, against your target raise. With fewer than 5 sized led rounds the range is grey and marked "size unclear";
  - its last lead (company, stage, date);
  - a **Led {competitor}** tag when it led or joined one of your competitors' rounds;
  - a **Way in** (see below).
- **Find funds for me.** No list yet? Recount finds the funds that led rounds at your stage, within 2x of your target and in your region over the last 30 months, with those rounds linked.
- **Live Cala lookups.** A fund that is not in the snapshot can be looked up live: Recount asks Cala about the fund, merges the answer and shows the new verdict.
- **Will your lead come back?** For your current lead: in its other companies, how often it came back in, and led, the next round.
- **Record view.** Every count opens the rounds behind it. Each round shows how it was found (asking about the fund, about the company, or both agreeing), the raw Cala rows, the Cala entity IDs of the company and its leads, the documents Cala's `/v1/knowledge/search` cites for that round where fetched, and a cross-check against Cala's entity graph where one was run. A round whose own source text names a different lead is marked **disputed** and left out of every fund's count.
- **Print sheet** (one A4 page) and **Copy as CSV**.

### The way in

- **From round records.** One of your investors and the fund were both in the same equity round with at most six investors, in the last four years: "Ask Lifeline Ventures ... Ask which partner was on that deal." (`tie` in `app/engine.py`)
- **From your LinkedIn connections.** Add the `Connections.csv` file from LinkedIn's data export. The file is parsed in your browser (`parseConnections` in `app/static/app.js`): only first name, last name, company and position are kept, in memory, for that page. URLs and emails are never read, nothing is uploaded or stored, and no API route receives the file. Each connection's company is matched by name to the companies a fund led or joined in our data. A same-company match is a lead to check, not proof that the person knows anyone at the fund. Short or ordinary-word company names are shown only as "same name", and a title counts as founder level only when it starts with founder, CEO, CTO, managing director or partner.
- **The Map.** The same ways in drawn as a flow: you on the left, the people who can introduce you in the middle (your investors, and your contacts grouped by company), the funds on the right in the list's groups and order. A solid thick line is someone at a company the fund led, a dashed line someone at a company it only joined, a dotted line your investor in a small round with it: the order the list ranks ways in. A fund with no line keeps its place and says "no way in found", which means no path yet, not a bad fund. Hovering a fund or a person shows the round behind each line. (`drawFlow` in `app/static/app.js`)

## How this differs from existing tools

From public pages read on 14 November 2026. Logged-in features were not checked, so "not shown" means not visible on the public pages, not proof of absence.

| Tool | What its public pages show | Source |
|---|---|---|
| Crunchbase | Its documented prediction API returns whether and when a company is likely to raise (`probability_score`, `probability_score_timeseries`), with no investor fields. A "Potential Investors" feature could not be verified. | https://data.crunchbase.com/docs/anticipate-whats-next-for-your-icp-fit-accounts |
| Dealroom | Investor pages with KPIs, portfolio analysis and rankings; a Startup Journey report that scores co-investors on follow-on conversion. No lead ratio or "who led" view on the public pages. Premium from EUR 250 per seat per month. | https://dealroom.co/investors, https://dealroom.co/startup-journey-europe/, https://dealroom.co/pricing |
| Metal | The closest tool. Follow-On Intelligence shows which of your existing investors typically follow on; investors are ranked by stage, thesis, "lead inclination" and similar factors; intro paths via Gmail and LinkedIn. No method or accuracy published. | https://www.metal.so/investor-relations/next-round-intelligence/follow-on-intelligence, https://www.metal.so/llms.txt |
| Signal by NFX | Free. Firm pages list the firms that co-invest with a firm, by name only, with no lead or follow role and no round order. | https://signal.nfx.com/firms/ourcrowd |
| OpenVC | Free investor directory with deck tracking and a CRM. No follow-on data found. | https://www.roundfunded.com/en/alternatives/openvc |
| Shizune | Free investor database (LatAm focus) with an overall lead/follow share per investor, for example 38% lead, 62% follow. No co-investor names. | https://shizune.co/investors/venture-capital-investors-latam |

What Recount adds: the lead count at the founder's own stage and size, with how many rounds had no named lead; every count opens the Cala rounds and source documents behind it; the way in comes from the same round records plus a LinkedIn export read in the browser, with no inbox or account connection; and a published test of next-lead prediction.

## How Cala is used

Cala is the only data source. We ask Cala two kinds of questions through `POST /v1/knowledge/query`:

1. **Investor-first** (195 funds): "List every funding round that {fund} invested in, with ... whether {fund} led the round." Cala's answer includes a per-round flag for whether the fund led. Large funds get one question per year when the open question is too broad.
2. **Company-first** (421 companies asked, 410 returned a history): "List every funding round of {company} with announcement date, round type, amount, lead investor and all participating investors."

A round seen from both sides is merged when company, stage and date agree, and the record view says so. Investor names are canonicalised (for example "Point Nine Capital" and "Point Nine"). Grants, loans and prizes are excluded from lead counts.

- `POST /v1/knowledge/search` gives the documents behind 211 rounds, fetched ahead of time for each queried fund's last lead; any other round can ask live from its record. The cached source text is also how 12 of those 211 rounds were found to be disputed (`app/dispute.py`, no extra Cala call).
- `/v1/entities` was checked for 90 rounds; Cala's graph had 12 of them. 4,406 Cala entity IDs are attached to records.
- The same investor-first question runs live from the app for funds a founder pastes that are not in the snapshot yet.

## What we tested

| Test | Result |
|---|---|
| In 1,599 past rounds with a named lead, is the investor with the stronger earlier lead record the real lead? | Yes 50% of the time, vs 36% for a random pick from the same round (95% CI 47 to 52%). `pipeline/validate.py` |
| 30 random rounds checked by hand against press (drawn from the first 1,828 rounds, before the investor-first crawl) | 22 of 26 sourced rounds correct, 2 partly, 2 wrong, 4 with no public source. Sample-fund last leads 9 of 11 correct, 2 missing a co-lead |
| Both query paths name a lead for the same round | They share it in 172 of 191 rounds |
| Cala entity graph cross-check (60 random rounds) | Round present 7 times; where the graph marks a lead, it agrees with ours 6 of 6 |
| A round's own Cala source text names a different lead | 12 of 211 sourced rounds, marked disputed and left out of every count |
| Predict who leads a company's next round (558 held-out rounds, only earlier data used, 8 methods) | Real lead in the top 5: **26 to 27%**, almost all of it from current investors |
| Predict which **new outside** fund leads (462 rounds) | Top 5: **4 to 5%** (random: 0.15%); top 20: 11 to 12%. Too weak to promise |

We first set out to predict who would lead a founder's next round. We tested it before building and then again on the full data with 8 methods and an adversarial leakage audit ([`research/prediction/RESULTS.md`](research/prediction/RESULTS.md), baselines in [`research/prediction/baselines.txt`](research/prediction/baselines.txt)). The strongest signal is the company's own cap table: a current investor leads about 1 in 4 next rounds; the previous round's lead itself about 1 in 6 (17%). A new outside lead cannot be predicted from round data with useful accuracy, so Recount shows the evidence (who leads rounds like yours, and how to get in) instead of odds.

## Where AI is used, and where it is not

- **Verdicts, counts, ties and conflicts are plain counting** over Cala round records. Same input, same list. No language model ranks or judges a fund.
- **Gemini** (`gemini-3.5-flash-lite`) has one job: reading pasted lines our deterministic parser could not match (for example "lunch with the Lifeline guys at Kämp") and returning firm names, with a fixed JSON schema. The pasted text is not stored, and the UI marks every fund name Gemini read.

## Architecture

```
Cala /v1/knowledge/query ──> crawl (pipeline/) ──> Aiven Postgres ──> Modal (FastAPI app) ──> browser
                                   ▲                     │  snapshot, live_funds, rounds
         live lookups from the app ┘                     │
```

- **Cala**: investor-first and company-first round data, source documents, entity cross-check, live lookups.
- **Aiven for PostgreSQL**: system of record. Stores every Cala answer looked up live (`live_funds`), the merged snapshot the app serves (`snapshot`), and the normalised rounds and investors (`companies`, `rounds`, `round_investors`, `investors`).
- **Modal**: serves the app (`modal_app.py`, FastAPI) and runs the live Cala lookups in the background, under our own client limit of 10 requests a minute, with a per-session budget and a daily cap.
- **Gemini**: reads messy pasted lines, nothing else.
- **Browser**: reads the LinkedIn connections file and matches it locally.

```
app/        main.py (API)  engine.py (verdicts, ties, conflicts, discovery)  merge.py (merging Cala rows)
            dispute.py (rounds the source disputes)  parse.py (deterministic list parser)  gemini.py  live.py
            graph.py  static/ (no build step; app.js parses the LinkedIn file in the browser)
pipeline/   cala_client.py (cached, rate-limited)  fetch.py  fetch_more.py  fetch_funds.py  fetch_sources.py
            fetch_graph.py  normalize.py  build_snapshot.py  load_db.py  validate.py
modal_app.py
```

## Run it

```
pip install fastapi uvicorn "psycopg[binary]" requests
export CALA_API_KEY=… GEMINI_API_KEY=… RELAY_DATABASE_URL=… COOKIE_KEY=…
cd pipeline && python3 fetch.py && python3 fetch_funds.py 50 20 && python3 build_snapshot.py --store && python3 validate.py
cd ../app && uvicorn main:app --port 8765
```

`fetch.py` and `fetch_funds.py` spend Cala credits; every request is cached. To run the app from a local snapshot file instead of Postgres, set `RELAY_SNAPSHOT_PATH`. Deploy: `modal secret create relay-secrets …` then `modal deploy modal_app.py`.

## Limits

- Fund level, not partner level. A tie means two funds sat in the same round; ask your investor which partner was on it.
- About a third of seed rounds in our data name no lead (Cala names the lead in 68% of 1,418 seed rounds). They are left out of the lead ratio, which pushes thinly covered funds toward "Too little data", so every row shows how many rounds had no named lead.
- Answers to "which rounds did this fund invest in" name rounds a fund led more often than rounds it only joined, so the lead share is an upper bound.
- Size verdicts need 5 or more sized led rounds; below that the range is shown in grey as "size unclear".
- The disputed-round check is a text rule over the 211 rounds with cached source documents. Rounds without a cached source are not checked.
- A LinkedIn match is a person at a company the fund backed, matched by company name. It is not proof of a relationship.
- Coverage is what Cala returned to our questions: mostly European venture rounds from 2021 to 2026. A fund missing here is missing from our snapshot, not necessarily from Cala.
- Company discovery started from startups that raised more than EUR 2m, so very small rounds are under-represented.

## Licence and credits

MIT, see `LICENSE`. Data from [Cala](https://cala.ai). Geist and Geist Mono fonts under the SIL Open Font License (`app/static/fonts/`). Built by team Wicflow at Junction 2026.
