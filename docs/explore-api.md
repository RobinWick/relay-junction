# Explore page API

`/explore` serves `app/static/explore.html`. Its script reads the endpoints below, served by
`app/explore_views.py` with shapes built in `app/explore_shapes.py` from the live snapshot, `app/exits.json` and
`app/people.json`. They are cached until one of those changes.

Filtering and sorting run in the browser, so list endpoints return every item (194 funds, about 3,400 companies,
22 founders). Every response carries `source: {name, retrieved, note}`, and the page shows it.

The server-filtered, paged API in `app/explore_api.py` (`/api/explore/funds`, `/fund/{key}`, `/companies`,
`/company/{ckey}`, `/people`, `/person/{id}`, `/options`, `/ai-filters`) stays available for other clients.

## GET /api/explore/ui/meta
`{source, counts{funds, companies, founders}, countries[], stages[], founder_tags[], investors[], levels{"0".."4"},
people_coverage}`. `founder_tags` are people.py tag labels. `levels` are people.py title levels.
`people_coverage` is people.json's coverage block (how many founders have any role, a dated role, and so on).

## GET /api/explore/ui/funds and /funds/{key}
Fund: `key, name, rounds, led, joined, lead_unknown, lead_share, lead_known, median_led_round_eur_m, last_lead,
months_since_last_lead, downturn_led, downturn_lead_known, exit_receipts, countries{}, stages_led{}, stages{},
co_investors[{key, name, shared_rounds}]`. "Joined" means another investor led. "Unknown" means no lead is named,
or the round is flagged `not_led`. Disputed rounds are skipped.

The detail adds `pace [{year, led, joined, unknown}]`, `recent_rounds` (latest 30, each with `role`), `exits`
(receipts from app/exits.json in the receipt_exits.py shape) and `exits_caveat`. A key outside the queried fund
list still gets a detail page, so Check can link any fund it shows.

## GET /api/explore/ui/companies and /companies/{key}
Company: `key, name, country, rounds, last_round, last_stage, last_amount_eur_m, months_since_last_round,
total_known_eur_m, investors[], leads[], last_leads[], founders[{id, name}], founder_tags[], repeat_founder`.
The detail adds `timeline`, a list of rounds with the oldest first.

## GET /api/explore/ui/founders and /founders/{id}
`{items, source, coverage, cohorts}`. Items leave out `roles`, `undated_roles`, `level_steps` and `tag_evidence`.

Person: `id, name, country, company, company_key, company_stage, description (birth year removed), linkedin_url,
career_start, roles[{org, org_type, title, level, level_label, start, end, months, current, sources[]}],
undated_roles[], level_steps[], founded[{company, how, exit}], metrics{employers, roles, roles_dated,
roles_outside_company, avg_tenure_years, avg_tenure_n, shortest_tenure_years, longest_tenure_years, level_ups,
level_ups_per_year, years_before_company, companies_founded, repeat_founder, prior_exit}, tags[], tag_evidence{},
gaps[], source{name, retrieved, entity_id, note}`. Metric definitions are people.py's (people.json
`definitions.metrics`). `org_type` is "Own company", a background tag label, or "Employer".

Cohorts: Cala's "founder previously worked at X" queries, one per employer, rows tagged by what their own text
says (`relation_label`), with `ckey` set when the company is in our round data. Rows carry no source URLs.

Ethics rules: values are facts with neutral labels. No score, no "best founder", no ordering of people by a
metric: the founders table sorts by name or company only. Every person view shows its source, entity id and date.

## POST /api/explore/ui/ai-filters
Request `{role: founder|investor, view: funds|companies|founders, text}`. Runs explore_api's Gemini step (same
rate limits, enums and keyword fallback) and renames its query params to the page's filter keys. Response
`{view, filters, unmatched[], engine, explanation, notice, filled_by_keywords}`.

| view | key | value |
|---|---|---|
| funds | country, stage, co_investor | string[] |
| funds | lead_share | {min, max} in percent |
| funds | lead_known | number |
| funds | round | {min, max} in EUR m (median led round) |
| funds | last_lead | 6, 12, 18, 24 or 36 (months) |
| funds | downturn, exits | true |
| companies | stage, country, investor, lead, founder_tags | string[] |
| companies | last_round_after | "YYYY-MM" |
| companies | months_since, last_amount | {min, max} |
| companies | repeat | true |
| founders | tags | string[] |
| founders | tenure | {min, max} in years |
| founders | ups | {min, max} level-ups per year |
| founders | repeat, prior_exit | true |
