# Evidence: every number Recount claims, and how to check it

All numbers come from snapshot `20261114102039` (built 14 November 2026) and `app/validation.json` of the same version, unless stated. Cala is the only data source.

## Data

| Claim | Value | Where it comes from |
|---|---|---|
| Funding rounds | 5,200 | `pipeline/build_snapshot.py`, `stats.rounds` in the snapshot |
| Companies | 3,393 | `stats.companies` |
| Funds asked investor-first | 195 | `stats.funds_queried`, list in `pipeline/fetch_funds.py` |
| Companies asked company-first | 421 asked, 410 returned a round history | `pipeline/fetch.py` (one line per company in its `histories.jsonl` output); 410 is the number of companies with a company-first round in the snapshot |
| Investors after name canonicalisation | 5,971 | `stats.investors` |
| Cala entity IDs attached to records | 4,406 | `stats.entity_ids`, `app/merge.py` (`add_entities`) |
| Rounds with source documents from `/v1/knowledge/search` | 211 | `stats.sourced_rounds`, `pipeline/fetch_sources.py` |
| Rounds disputed by their own source text | 12 of the 211 | `stats.disputed_rounds`, `app/dispute.py`, called from `pipeline/build_snapshot.py` (`flag_disputes`) |
| Rounds cross-checked in Cala's entity graph | 90, of which the graph had 12 | `stats.graph_checked`, `pipeline/fetch_graph.py`, `app/graph.py` |
| Rounds seen from both query paths where both name a lead | 191, sharing a lead in 172 | counted from the raw rows of each `both` round in the snapshot; the count is printed by `pitch/deck/build.py` (outside this repo), not by `pipeline/validate.py` |

## Accuracy

| Claim | Value | Method |
|---|---|---|
| Hand check against press, 30 random rounds (2022+) | 22 of 26 verifiable correct, 2 partly, 2 wrong, 4 with no public source | `research/accuracy/accuracy.md`, one source URL per row in `accuracy.json`, sample drawn with `random.seed(14)` from the first 1,828 rounds, before the investor-first crawl |
| Last lead of 11 sample funds | 9 of 11 correct, 2 missing a co-lead, none wrong | same file |
| Lead record carries signal | In 1,599 past rounds with a named lead, the investor with the stronger earlier lead record was the real lead 50% of the time, vs 36% for a random pick from the same cap table (95% CI 47 to 52%) | `pipeline/validate.py`, output `app/validation.json`, shown on the Method page |
| The lead comes back | Across 1,489 cases, the lead of a round came back in the company's next round 60% of the time and led it again 17% of the time | `pipeline/validate.py` (`lead_comes_back` in `app/validation.json`); per fund in the app via `app/engine.py` (`lead_comes_back`) |
| Entity graph agreement | On 60 random rounds the graph had the round 7 times; where it marks `is_lead`, it agrees with our lead 6 of 6 | `pipeline/fetch_graph.py`, `pipeline/validate.py` (`graph_check`) |
| Sample lead card checked against press | The sample's "Will your lead come back?" card (Lifeline Ventures, 10 rounds in 8 companies) holds on "led 3"; two of its 10 cases are not supported by press, so we do not quote the card as a fact | `research/accuracy/lifeline-check.md` |

## Way in

| Claim | Value | Where it comes from |
|---|---|---|
| Co-round tie | One of the founder's investors and the fund in the same equity round with 2 to 6 investors, in the last 4 years, round size at most EUR 50m | `app/engine.py` (`tie`) |
| LinkedIn connections are read in the browser | `Connections.csv` is parsed client-side; only first name, last name, company and position are kept, in memory; URLs and emails are never read | `app/static/app.js` (`parseConnections`, `setNetwork`) |
| Nothing is uploaded | No API route receives the file: `/api/check` gets the fund list and round settings, returns each fund's portfolio, and the match runs in the browser | `app/main.py` (routes), `app/static/app.js` (`networkMatches`) |
| Matching rule | Company name match to companies the fund led or joined; short or ordinary-word names shown only as "same name"; a match is a lead to check, not proof of a relationship | `app/engine.py` (`portfolio`, `weak_name`), `app/static/app.js` (`wayIn`) |
| Sample summary | "way in to 2" without a network, "way in to 8" with the made-up sample network (14 funds, Gemini reading the last line) | run the sample in the app |

## Prediction (why the product shows evidence, not odds)

Full write-up: `research/prediction/RESULTS.md`. Harness: `research/prediction/harness.py` (reads `RELAY_SNAPSHOT_PATH`). Baselines: `research/prediction/baselines.txt`. Methods: `research/prediction/methods/`.

- Test: 558 rounds found company-first (2021 to 2026), each predicted only from rounds dated before it.
- 8 method families (co-investment graph with personalised PageRank, hand-off edges, fund-profile fit, collaborative filtering, learning to rank, insider switch, narrowed tasks, size ladder), each audited by a separate agent for information leakage.
- Who leads the next round, current investors allowed: real lead in the top 5 in 26 to 27%. A current investor leads about 1 in 4 next rounds; the previous round's lead itself about 1 in 6 (17%, `previous_lead_only` in `baselines.txt`).
- Which new outside fund leads (462 rounds): top 5 in 4 to 5%, top 20 in 11 to 12%, random 0.15%. The audit found the fund crawl list was chosen by frequency, which inflated outside-fund results; the 4 to 5% figure is after removing that effect.
- Conclusion: the cap table is the strongest predictor; outside leads are not predictable enough to promise, so the app shows evidence.

## Data quality findings for Cala

`data_quality/cala-data-quality.json`: 19 findings with examples and counts, including the per-round "did fund X lead" flag contradicting the lead investor field, round labels that differ between query paths, tranches split into several rows, placeholders in investor fields, one fund split across several entity IDs, entity-graph coverage gaps for recent Nordic seed rounds, and five rows that disagree with press.

## Where AI is used

- Gemini (`gemini-3.5-flash-lite`) only reads pasted lines the deterministic parser cannot match and returns fund names; the UI marks each one (`app/gemini.py`, `app/parse.py`).
- Verdicts, counts, conflicts and ties are deterministic counting (`app/engine.py`). Same input, same output.

## Security and cost controls

- Live Cala lookups are capped per visitor session and per day in Postgres (`app/live.py`, `live_usage` table), so a restart cannot reset the cap.
- Request bodies are capped at 64 KB, strict Content-Security-Policy and security headers, fund names validated before any paid call (`app/main.py`, `app/live.py`).
- No secrets in the repository; configuration comes from environment variables (Modal secret `relay-secrets`).
