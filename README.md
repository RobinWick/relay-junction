# Recount

**The right investors for founders, the right companies for investors, all from Cala.**

Recount counts Cala's funding-round, M&A and people records. Founders see which funds actually lead rounds like theirs, how each fund led year by year, who bought the companies it backed, and a way in. Investors get a quick, sourced background check on any fund, company or founder. Every round and receipt opens the Cala record behind it.

Built at Junction 2026 (Espoo, 13 to 15 November 2026) for Cala's "Make Unicorns Real" challenge, by Team Moonshot.

## Links

| What | Where |
|---|---|
| Recount (fund check, receipts, Explore) | https://robin-81988--recount.us-east.modal.run (no login; "Try a sample", or add `#demo`) |
| Explore (funds, companies, founders) | https://robin-81988--recount.us-east.modal.run/explore |
| Recount Signal (company ranking + Lab) | https://robin-81988--recount-signal.us-east.modal.run/signal (Lab tab: `#/lab`) |
| Pitch video and deck | Link and PDF in the Junction submission |
| Evidence for every number | [`docs/EVIDENCE.md`](docs/EVIDENCE.md) |
| Plain-text summary for AI readers | [`llms.txt`](llms.txt), also served at `/llms.txt` on both apps |
| Code | `main` = Recount. Branch [`feat/signal`](https://github.com/RobinWick/relay-junction/tree/feat/signal) = `main` plus Recount Signal |

## How it maps to the judging criteria

| Criterion | What we did | Numbers (each traceable to a file in this repo) |
|---|---|---|
| **Real need** | Every priced round needs a lead, and a fund's name does not say whether it leads. Fund sites list portfolios, not who led, and not how a fund behaved in the downturn. The question comes back before every raise. | Of the 47 most active Nordic pre-seed/seed investors we could judge (2023 to 2026), 24 led under half their rounds; 308 of 1,042 named seats (30%) were leads (`research/need/SCARCITY.md`). A round's lead came back in the next round 60% of the time but led it only 15% (1,405 cases, `app/validation.json`). |
| **Execution** | Deployed end to end: Cala crawl, merge, Aiven Postgres, FastAPI on Modal, live Cala lookups with spending caps. Fund check, three receipts (lead pace, who bought its companies, intro path), Explore, founder pages, and Signal with its Lab. Tests run before every deploy. | 5,146 rounds, 3,390 companies, 194 funds asked investor-first. 20 exit receipts across 13 funds (14 distinct deals, 17 receipts with a disclosed value). Hand check of 80 random Cala lead calls against press: right lead fund 66 of 74 (89%), exactly right 55 of 74 (74%) (`research/accuracy/`). |
| **Originality** | We tried to build a "magic score" and tested it on years the model never saw. One signal held up, so Signal ranks on that one only and the Lab tab shows every signal that failed. Everything else is a receipt you can open: lead share at your stage year by year, acquisitions with their source, founder careers with their coverage stated. | 35 signals tested, 1 kept (round size for stage), 26 noise, 8 not testable (`app/signal_lab.json`, on `feat/signal`). Next outside lead in the top 5: 4 to 5% vs 0.15% random (462 rounds), so Recount shows evidence, not odds (`research/prediction/RESULTS.md`). |
| **Use of Cala as the core** | Cala is the only data source: `/v1/knowledge/query` (investor-first and company-first), `/v1/knowledge/search` (source documents), `/v1/entities` (INVESTED_IN, CorporateEvent MNA_COMPLETED, FOUNDED/WORKS_AT/IS_CEO_OF/IS_CTO_OF). We wrote up data-quality findings for Cala. | Where both query paths name a lead they agree in 176 of 192 rounds. Source documents for 209 rounds; 9 disputed rounds left out of every count. 19 data-quality findings (`data_quality/cala-data-quality.json`). |

## Check us in 60 seconds

1. **Open the demo and click "Try a sample"** (or open it with `#demo`). The sample is a seed founder raising EUR 3m, with Lifeline Ventures as an investor, Lovable as a competitor and 14 pasted lines.
2. **Read the summary line:** "8 of 14 mostly lead Seed rounds, 5 of them at a size like your EUR 3m. 2 lead, but a different size. 2 backed Lovable. You have a way in to 2." (The last pasted line is messy and goes to Gemini for the fund name. If Gemini is unavailable, that line shows as not recognised and the summary reads 7 of 13, 4 at your size, way in to 1.)
3. **Click "Try with a sample network".** A made-up file of 9 connections, every match marked "Sample", is matched in your browser: "way in to 2" becomes "way in to 8". Click **Map** to see the ways in as lines from you, through your investor or a contact, to each fund.
4. **Open Voima Ventures.** It "Led 13 of 13" rounds with a named lead near your stage, and the pane says 7 more had no named lead. Under "How to get in": your investor Lifeline Ventures and Voima Ventures were both in Reduciner's round of May 2026, with 4 investors in total.
5. **Click Reduciner** to open the round record: how it was found ("both agree"), the Cala entity IDs, the source documents from Cala search, and the raw Cala rows.
6. **Open Signal and click the Lab tab** to see all 35 tested signals, the one that held up, and the rule used to decide.

## Receipts, Explore and founder pages

- **Receipt 1, lead pace.** Per fund and year, 2019 to 2026: led, joined under another lead, lead unknown. Unknowns are shown, never hidden. (`app/receipt_pace.py`)
- **Receipt 2, who bought its companies.** Completed acquisitions of companies the fund backed (Cala `INVESTED_IN` edge, then `CorporateEvent` `MNA_COMPLETED` with role `TARGET`): buyer, deal value, date and source. Example: Zettle, bought by PayPal for 2.2B USD in 2018. Values are labelled "deal value, not return". 20 exit receipts across 13 funds in this build (14 distinct deals; one deal can appear for several funds). (`app/receipt_exits.py`, `app/exits.json`)
- **Receipt 3, intro path.** A fund that leads at your next stage and sat with one of your investors in a small round (2 to 6 investors, at most EUR 50m, last 4 years). Here is the round; ask your investor. (`app/receipt_intro.py`)
- **Explore.** Filters for funds, companies and founders. Type a sentence and Gemini sets filters from fixed lists; each filter it set is marked and editable. A request to rank or score people gets a plain refusal line. (`app/explore_api.py`, `app/explore_views.py`)
- **Founder pages.** Careers from Cala people data with the coverage stated on screen: 22 founders fetched, 2 with a dated role, 1 with a role outside their own company. Thin, and the page says so. (`app/people.py`, `app/people.json`)

## Recount Signal

Signal lists companies, funds and founders from Cala's funding record and ranks the companies. Before choosing what to rank on, we tested 35 candidate signals, including a learned model, on held-out years (2021 to 2023) after tuning on 2018 to 2020, with multiple-test correction.

- **Kept:** 1 signal, round size for stage (percentile of the last sized round among rounds of the same stage in nearby years). Next round within 24 months: AUC 0.55 (90% CI 0.505 to 0.598, n = 571). It held up, but only just.
- **Failed:** 26 were noise, 8 had too few rows to test. The 13-part "thesis mix" showed no measured lift over size for stage alone.
- **So:** the default ranking uses size for stage only, and says so on screen. The Lab tab lists every signal, its result and the rule.
- 2,662 of 3,390 companies have a sized, staged round and are ranked; the others have no rank.
- Gemini can turn a typed sentence into filters. It never sees company rows and never produces a company, number or score; the server validates its answer against the filter catalogue, and a keyword parser answers when Gemini is unavailable. (`app/signal_chat.py`)

Code on branch `feat/signal`: `app/signal_*.py`, `app/static/signal.*`, `modal_signal.py`. Lab data: `app/signal_lab.json`.

## The need

Every priced round needs a lead investor, and a fund's name does not tell a founder whether it leads. Counted from the same Cala snapshot ([`research/need/`](research/need/)):

- **About half of the most active Nordic seed investors do not lead.** Of the 50 investors that joined the most Nordic pre-seed and seed rounds from 2023 to 2026 (public bodies left out), 47 have 3 or more rounds with a named lead: 23 led at least half of them and 24 did not. Base: 350 rounds, 255 with a named lead ([`SCARCITY.md`](research/need/SCARCITY.md), [`scarcity.py`](research/need/scarcity.py)).
- **Only 3 in 10 names on a seed round led it.** In those 255 Nordic rounds, 308 of 1,042 named investor seats (30%) are lead seats; across Europe 1,006 of 3,252 (31%) in 779 rounds.
- **The previous lead is rarely the answer.** In 1,405 cases the lead of a round came back in the company's next round 60% of the time but led it only 15% of the time (`app/validation.json`).
- **Recount separates the two on real lists.** We replayed 20 randomly drawn real Nordic pre-seed and seed rounds from 2025 and 2026, with Recount seeing only rounds dated before each one: 6 of the 8 funds it put in Pitch first went on to lead (95% CI 41% to 93%), and it never called the eventual lead Mostly follows (0 of 20). It also had nothing to say about most names: 122 of 157 got Too few rounds. Press-checked examples: Intric (byFounders, Feb 2026), IPercept (Luminar Ventures, May 2025; one source names J12 as lead) and Oplane (Seed Capital, Jun 2026) ([`BACKTEST.md`](research/need/BACKTEST.md), [`backtest.py`](research/need/backtest.py)).

Caveats: the snapshot was built partly from 194 funds we chose as known seed investors, so "about half lead" is more likely an upper bound than a floor; the replay is 20 rounds, and its lists are the eventual cap tables, so it tests sorting, not finding new funds.

A seed or Series A founder can book only a few dozen investor meetings per raise, so pitching funds that only follow costs months. The question is simple: which of these funds actually leads rounds like mine, which only follows, and how do I get in? Fund websites list portfolio companies, not who led which round. Recount answers it for any list a founder has, and it is just as useful to accelerators and venture builders who prepare a whole cohort for investor meetings.

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

1. **Investor-first** (194 funds): "List every funding round that {fund} invested in, with ... whether {fund} led the round." Cala's answer includes a per-round flag for whether the fund led. Large funds get one question per year when the open question is too broad.
2. **Company-first** (421 companies asked, 410 returned a history): "List every funding round of {company} with announcement date, round type, amount, lead investor and all participating investors."

A round seen from both sides is merged when company, stage and date agree, and the record view says so. Investor names are canonicalised (for example "Point Nine Capital" and "Point Nine"). Grants, loans and prizes are excluded from lead counts.

- `POST /v1/knowledge/search` gives the documents behind 209 rounds, fetched ahead of time for each queried fund's last lead; any other round can ask live from its record. The cached source text is also how 9 of those 209 rounds were found to be disputed (`app/dispute.py`, no extra Cala call).
- `/v1/entities` was checked for 90 rounds; Cala's graph had 12 of them. 4,414 Cala entity IDs are attached to records.
- The same investor-first question runs live from the app for funds a founder pastes that are not in the snapshot yet.
- **M&A:** `/v1/entities` fund `INVESTED_IN` edges, then `CorporateEvent` `MNA_COMPLETED` with role `TARGET`: acquirer, value, date and source URL (`pipeline/fetch_exits.py`, `app/receipt_exits.py`).
- **People:** `/v1/entities` `FOUNDED`, `WORKS_AT`, `IS_CEO_OF` and `IS_CTO_OF` edges with dates and sources, plus background cohorts from `/v1/knowledge/query` (`pipeline/fetch_people.py`, `app/people.py`).

## What we tested

| Test | Result |
|---|---|
| In 1,584 past rounds with a named lead, is the investor with the stronger earlier lead record the real lead? | Yes 48% of the time, vs 36% for a random pick from the same round (95% CI 46 to 51%). `pipeline/validate.py` |
| 80 random 2022+ rounds checked by hand against press, three draws (`random.seed(14)` and `random.seed(1401)`) | Lead exactly right in 55 of 74 verifiable (74%, 95% CI 63 to 83%), 11 partly, 8 wrong, 6 with no public source; right lead fund named in 66 of 74 (89%). By query path: investor-first only about 70% (35 of 50), company-first or both about 82% (18 of 22). Sample-fund last leads (not random) 9 of 11 correct, 2 missing a co-lead. [`research/accuracy/`](research/accuracy/) |
| Both query paths name a lead for the same round | They share it in 176 of 192 rounds |
| Cala entity graph cross-check (60 random rounds) | Round present 7 times; where the graph marks a lead, it agrees with ours 6 of 6 |
| A round's own Cala source text names a different lead | 9 of 209 sourced rounds in this build, marked disputed and left out of every count. Of the first 12 flagged, 10 confirmed by press; the 2 false alarms (OlsAro, Anthropic) are fixed |
| Predict who leads a company's next round (558 held-out rounds, only earlier data used, 8 methods) | Real lead in the top 5: **26 to 27%**, almost all of it from current investors |
| Predict which **new outside** fund leads (462 rounds) | Top 5: **4 to 5%** (random: 0.15%); top 20: 11 to 12%. Too weak to promise |

We first set out to predict who would lead a founder's next round. We tested it before building and then again on the full data with 8 methods and an adversarial leakage audit ([`research/prediction/RESULTS.md`](research/prediction/RESULTS.md), baselines in [`research/prediction/baselines.txt`](research/prediction/baselines.txt)). The strongest signal is the company's own cap table: a current investor leads about 1 in 4 next rounds; the previous round's lead itself about 1 in 6 (17%). A new outside lead cannot be predicted from round data with useful accuracy, so Recount shows the evidence (who leads rounds like yours, and how to get in) instead of odds.

## Where AI is used, and where it is not

- **Verdicts, counts, lead pace, receipts, ties, timelines and the Signal ranking are plain counting** over Cala records. Same input, same output. No language model ranks or judges a fund, company or person.
- **Gemini** (`gemini-3.5-flash-lite`) has two bounded jobs, both under a fixed JSON schema: (1) reading pasted lines our deterministic parser could not match (for example "lunch with the Lifeline guys at Kämp") and returning firm names; (2) in Explore and Signal, turning a typed sentence into filter values from fixed lists. Our code re-checks every value against those lists, the UI marks what Gemini set, and Gemini never sees result rows. Pasted text is not stored.

## Architecture

```
Cala /v1/knowledge/query  ┐
Cala /v1/knowledge/search ├─> crawl + merge (pipeline/, app/merge.py) ─> Aiven Postgres ─> FastAPI on Modal ─> browser
Cala /v1/entities         ┘                                                   ▲      │
                                         live Cala lookups from the app ──────┘      └─ Gemini: parsing and filters only
```

- **Cala**: the only data source. Rounds (investor-first and company-first), source documents, entity cross-check, M&A events, people edges, live lookups.
- **Aiven for PostgreSQL**: system of record. The merged snapshot the apps serve (`snapshot`), normalised rounds and investors (`companies`, `rounds`, `round_investors`, `investors`), every live Cala answer (`live_funds`) and the daily spending cap.
- **Modal**: two apps from one codebase. `recount` (`modal_app.py`, from `main`) and `recount-signal` (`modal_signal.py`, from `feat/signal`). Live Cala lookups run in the background under our own limit of 10 requests a minute, with a per-session budget and a daily cap.
- **Browser**: reads the LinkedIn connections file and matches it locally. Nothing is uploaded.

```
app/        main.py (API)  engine.py (verdicts, ties, conflicts, discovery)  merge.py (merging Cala rows)
            dispute.py  parse.py (deterministic list parser)  gemini.py  live.py  graph.py
            receipt_pace.py  receipt_exits.py  receipt_intro.py  explore_api.py  explore_views.py  people.py
            signal_*.py (feat/signal only)  static/ (no build step)
pipeline/   cala_client.py (cached, rate-limited)  fetch*.py  normalize.py  build_snapshot.py  load_db.py  validate.py
research/   need/  accuracy/  prediction/
```

## Run it locally

```
pip install fastapi uvicorn "psycopg[binary]" requests
export CALA_API_KEY=... GEMINI_API_KEY=... RELAY_DATABASE_URL=... COOKIE_KEY=...
cd pipeline && python3 fetch.py && python3 fetch_funds.py 50 20 && python3 build_snapshot.py --store && python3 validate.py
cd ../app && uvicorn main:app --port 8765
```

`fetch.py` and `fetch_funds.py` spend Cala credits; every request is cached. To run the app from a local snapshot file instead of Postgres, set `RELAY_SNAPSHOT_PATH`. Without `GEMINI_API_KEY` the app still runs; messy pasted lines show as not recognised and typed filters fall back to a keyword parser where one exists.

Tests: `python3 app/test_<name>.py` runs a file without pytest (`app/minitest.py`); `python3 -m pytest app` works too.

Deploy: `modal secret create relay-secrets ...`, then `modal deploy modal_app.py` (Recount) or, on `feat/signal`, `modal deploy modal_signal.py` (Signal).

## Limits, stated plainly

- Fund level, not partner level. A tie means two funds sat in the same round; ask your investor which partner was on it.
- About a third of seed rounds in our data name no lead (Cala names the lead in 68% of 1,401 seed rounds). They are left out of the lead ratio and counted on every row, which pushes thinly covered funds toward "Too little data".
- Answers to "which rounds did this fund invest in" name rounds a fund led more often than rounds it only joined, so the lead share is an upper bound.
- Size verdicts need 5 or more sized led rounds; below that the range is grey and marked "size unclear".
- The disputed-round check is a text rule over the 209 rounds with cached source documents. Other rounds are not checked.
- "No exit found in Cala" does not mean no exit. Deal value is not the fund's return.
- Founder career data is thin (22 founders fetched, 2 with a dated role) and every page states its coverage.
- Signal's one kept signal is weak (AUC 0.55 on held-out years). It orders a list; it does not predict success.
- A LinkedIn match is a person at a company the fund backed, matched by company name. It is not proof of a relationship.
- Coverage is what Cala returned to our questions: mostly European venture rounds from 2019 to 2026. A fund missing here is missing from our snapshot, not necessarily from Cala. Company discovery started from startups that raised more than EUR 2m, so very small rounds are under-represented.

## Licence and credits

MIT, see `LICENSE`. Data from [Cala](https://cala.ai). Geist and Geist Mono fonts under the SIL Open Font License (`app/static/fonts/`). Built by Team Moonshot at Junction 2026.
