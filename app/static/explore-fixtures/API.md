# Explore API contract

The Explore UI (`/static/explore.html`) reads these endpoints. The JSON files in this folder have the exact
response shapes. They are generated and git-ignored (about 8 MB, and company keys trip gitleaks as false
positives), so run `python3 pipeline/build_explore_fixtures.py` once before you open the page in fixture mode.

**Flag.** By default the UI reads the fixtures. Open `/static/explore.html?data=api` to use the live endpoints.
When the API ships, set `DEFAULT_SOURCE = "api"` at the top of `explore.js`. The UI does not fall back to
fixtures when an API call fails. It shows the error instead.

Filtering and sorting run in the browser, so list endpoints return every item (194 funds, about 3,400
companies). Every response carries `source: {name, retrieved, note}`, and the UI shows it.

## GET /api/explore/meta  (fixture: meta.json)
```json
{ "source": {"name": "Cala round data", "retrieved": "2026-11-14", "note": "..."},
  "counts": {"funds": 194, "companies": 3383, "founders": 14},
  "countries": ["United States", "..."],          // normalised, most rounds first
  "stages": ["pre-seed", "seed", "series a", "...", "growth"],
  "founder_tags": ["Big tech", "Prior exit", "Repeat founder", "Strategy consulting", "..."],
  "investors": ["Accel", "..."],                   // names for autocomplete
  "levels": {"1": "Individual contributor", "...": "...", "6": "C-level or founder"} }
```

## GET /api/explore/funds  (funds.json)
`{items: Fund[], source}`, where each Fund is:
```json
{ "key": "northzone", "name": "Northzone",
  "rounds": 74, "led": 23, "joined": 27, "lead_unknown": 24,
  "lead_share": 0.46, "lead_known": 50,          // led / (led + joined); null when lead_known is 0
  "median_led_round_eur_m": 13.8, "last_lead": "2026-05", "months_since_last_lead": 6,
  "downturn_led": 8, "downturn_lead_known": 10,   // 2022 to 2023
  "exit_receipts": 1,
  "countries": {"Sweden": 15}, "stages_led": {"series a": 9}, "stages": {"series a": 20},
  "co_investors": [{"key": "eqt ventures", "name": "EQT Ventures", "shared_rounds": 8}] }
```
"Joined" means another investor led. "Unknown" means no lead is named, or the round is flagged `not_led`.
Rounds flagged `disputed` are skipped.

## GET /api/explore/funds/{key}  (fund-details.json, keyed by fund key)
A Fund plus:
- `pace`: `[{year, led, joined, unknown}]`, every year from the first round to the last
- `recent_rounds`: the latest 30 Rounds, each with `role` set to `led`, `joined` or `unknown`
- `exits`: acquisition receipts in the `app/receipt_exits.py` shape (`company, date, year, acquirers[{name}], value{status, display, label}, sources[{name, url, date}]`)
- `exits_caveat`: a string

## GET /api/explore/companies  (companies.json)
```json
{ "key": "safegrid", "name": "Safegrid", "country": "Finland", "rounds": 6,
  "last_round": "2025-04", "last_stage": "series a", "months_since_last_round": 19,
  "total_known_eur_m": 7.7,
  "investors": [{"key": "...", "name": "..."}],   // up to 12, most frequent first
  "last_leads": [{"key": "...", "name": "..."}] }
```

## GET /api/explore/companies/{key}  (company-details.json)
A Company plus `timeline`, a list of Rounds with the oldest first. A Round looks like this:
```json
{ "id": 12, "company": "...", "ckey": "...", "country": "...", "date": "2023-02", "year": 2023,
  "stage": "series a", "type": "Series A", "amount_eur_m": 5.7,
  "leads": [{"key","name"}], "participants": [{"key","name"}], "participants_total": 11,
  "lead_known": true, "source_path": "company_first" }
```

## GET /api/explore/founders  (founders.json)
`{items: Person[], source}`. The list items leave out `roles` and `stints`.

## GET /api/explore/founders/{id}  (founder-details.json)
```json
{ "id": "...", "name": "...", "sample": false, "country": "...", "company": "...", "company_stage": "seed",
  "career_start": "2014-09",
  "roles":  [{"org", "org_type", "title", "level": 1-6, "level_label", "start": "YYYY-MM", "end": "YYYY-MM"|null, "months", "current"}],
  "stints": [{"org", "org_type", "start", "end", "months", "roles"}],      // back-to-back roles at one org merged
  "founded": [{"company", "start", "status": "active|acquired|closed", "acquirer"}],
  "metrics": { "employers", "roles", "median_tenure_months", "shortest_tenure_months",
               "title_steps", "internal_title_steps", "months_per_title_step",
               "months_to_head_level", "companies_founded", "repeat_founder", "prior_exit" },
  "tags": ["Strategy consulting", "Repeat founder", "Prior exit"],
  "source": {"name": "...", "retrieved": "YYYY-MM-DD", "note": "..."} }
```
Metric definitions, as computed in `pipeline/build_explore_fixtures.py::person_record`:
- **Tenure**: months per employer stint. Back-to-back roles at one org count as one stint, and the current stint is excluded from the median.
- **Title step**: a role whose level is higher than the role before it, not counting roles at the person's own company.
- **Months per title step**: months from the first role to the start of the last title step, divided by the number of steps.
- **Tags**: the `org_type`s of employers before founding, plus `Repeat founder` (2 or more companies founded) and `Prior exit` (an earlier founded company was acquired).

Ethics rules: show these values as facts with neutral labels. Never add a score, a "best founder" label or a default sort by a metric. The list sorts by name by default. Every person view shows `source.name` and `source.retrieved`. The fixture people are invented (`sample: true`), and the real records come from Cala WORKS_AT and FOUNDED edges.

## POST /api/explore/ai-filters
Request: `{"role": "founder"|"investor", "view": "funds"|"companies"|"founders", "text": "..."}`
Response:
```json
{ "view": "founders",                       // may switch the investor tab
  "filters": { "tags": ["Strategy consulting"], "step": {"min": null, "max": 18}, "repeat": true },
  "engine": "claude-...",                    // shown to the user
  "unmatched": ["parts of the text no filter could express"] }
```
Valid filter keys and value types (the API must return only these):

| view | key | value |
|---|---|---|
| funds | q | string |
| funds | country, stage, co_investor | string[] (`stage` uses meta.stages values) |
| funds | lead_share | {min, max} in percent |
| funds | lead_known | number |
| funds | round | {min, max} in EUR m (median led round) |
| funds | last_lead | 6, 12, 18, 24 or 36 (months) |
| funds | downturn, exits | true |
| companies | q | string |
| companies | stage, country, investor | string[] |
| companies | last_round_after | "YYYY-MM" |
| companies | months_since, raised | {min, max} |
| companies | rounds | number |
| founders | q | string |
| founders | tags, country, stage | string[] |
| founders | tenure, step | {min, max} in months |
| founders | repeat, prior_exit | true |

The UI marks every returned key with an "AI" badge until the user edits that filter. In fixture mode,
`localAiFilters()` in explore.js stands in for this endpoint with keyword rules (`engine: "fixture-rules"`).
