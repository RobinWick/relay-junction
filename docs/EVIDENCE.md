# Evidence: every number Lead Check claims, and how to check it

All numbers come from snapshot `20261114013628` (built 14 November 2026) unless stated. Cala is the only data source.

## Data

| Claim | Value | Where it comes from |
|---|---|---|
| Funding rounds | 5,200 | `pipeline/build_snapshot.py`, `stats.rounds` in the snapshot |
| Companies | 3,393 | `stats.companies` |
| Funds asked investor-first | 195 | `stats.funds_queried`, list in `pipeline/fetch_funds.py` |
| Investors after name canonicalisation | 5,971 | `stats.investors` |
| Cala entity IDs attached to records | 4,406 | `stats.entity_ids`, `app/merge.py` (`add_entities`) |
| Rounds with source documents from `/v1/knowledge/search` | 211 | `stats.sourced_rounds`, `pipeline/fetch_sources.py` |
| Rounds cross-checked in Cala's entity graph | 90 | `stats.graph_checked`, `pipeline/fetch_graph.py`, `app/graph.py` |
| Rounds seen from both query paths where both name a lead | 191, agreeing in 172 | `pipeline/validate.py` |

## Accuracy

| Claim | Value | Method |
|---|---|---|
| Hand check against press, 30 random rounds (2022+) | 22 of 26 verifiable correct, 2 partly, 2 wrong, 4 with no public source | `research/accuracy/accuracy.md`, one source URL per row in `accuracy.json`, sample drawn with `random.seed(14)` |
| Last lead of 11 sample funds | 9 of 11 correct, 2 missing a co-lead, none wrong | same file |
| Lead record carries signal | In 1,598 past rounds with a named lead, the investor with the stronger earlier lead record was the real lead 50% of the time, vs 36% for a random pick from the same cap table (95% CI 47 to 52%) | `pipeline/validate.py`, output `app/validation.json`, shown on the Method page |
| Lead comes back | Lifeline Ventures came back in the next round in 9 of 10 of its companies that raised again, and led 3 | `app/engine.py` (`lead_back`), shown in the app |
| Entity graph agreement | On 60 random rounds the graph had the round 7 times; where it marks `is_lead`, it agrees with our lead 6 of 6 | `pipeline/fetch_graph.py`, `pipeline/validate.py` (`graph_check`) |

## Prediction (why the product shows evidence, not odds)

Full write-up: `research/prediction/RESULTS.md`. Harness: `research/prediction/harness.py`. Methods: `research/prediction/methods/`.

- Test: 558 rounds found company-first (2021 to 2026), each predicted only from rounds dated before it.
- 8 method families (co-investment graph with personalised PageRank, hand-off edges, fund-profile fit, collaborative filtering, learning to rank, insider switch, narrowed tasks, size ladder), each audited by a separate agent for information leakage.
- Who leads the next round, current investors allowed: real lead in the top 5 in 27% (the "previous lead leads again" rule alone: 25%).
- Which new outside fund leads: top 5 in 4 to 5%, top 20 in 11 to 12%, random 0.15%. The audit found the fund crawl list was chosen by frequency, which inflated outside-fund results; the 4 to 5% figure is after removing that effect.
- Conclusion: the cap table is the strongest predictor; outside leads are not predictable enough to promise, so the app ranks evidence.

## Data quality findings for Cala

`data_quality/cala-data-quality.json`: 18 findings with examples and counts, including the per-round "did fund X lead" flag contradicting the lead investor field, round labels that differ between query paths, tranches split into several rows, placeholders in investor fields, one fund split across several entity IDs, and entity-graph coverage gaps for recent Nordic seed rounds.

## Where AI is used

- Gemini (`gemini-3.5-flash-lite`) only reads pasted lines the deterministic parser cannot match and returns fund names; the UI marks each one (`app/gemini.py`, `app/parse.py`).
- Verdicts, counts, conflicts and intro paths are deterministic counting (`app/engine.py`). Same input, same output.

## Security and cost controls

- Live Cala lookups are capped per visitor session and per day in Postgres (`app/live.py`, `live_usage` table), so a restart cannot reset the cap.
- Request bodies are capped at 64 KB, strict Content-Security-Policy and security headers, fund names validated before any paid call (`app/main.py`, `app/live.py`).
- No secrets in the repository; configuration comes from environment variables (Modal secret `relay-secrets`).
