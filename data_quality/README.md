# Cala data-quality notes from Team Wicflow

A thank-you from Recount (Junction 2026). Recount counts, for each fund a founder plans to pitch, how often it actually led rounds like theirs. To count leads we asked Cala's `/v1/knowledge/query` two ways and compared the answers. These are the issues we had to clean up, with checkable examples. Some field drift comes from our own free-form prompts; we list it because a fixed schema would help every Cala user.

**Data checked (2026-11-14 01:50):** 1816 rows from 421 company-first answers ("List every funding round of X ..."), 1200 rows from 43 investor-first answers ("every round fund X invested in and whether X led it"). The investor-first crawl was still running, so counts are a snapshot. Full raw rows for every example are in `cala-data-quality.json`.

| Issue | Count | Example (raw Cala values) | Suggested fix |
|---|---|---|---|
| Lead flag contradicts lead field | 5 across paths, 10 in-row | Algorithmiq Series A, Jun 2023: investor-first `inventure_led: "No"`, company-first `lead_investor: "Inventure VC"` | One tri-state `led` boolean per investor per round |
| Round label differs by query path | 23 of 98 matched rounds | Einride, Oct 2025, $100M: `Series C` (via EQT Ventures) vs `Series D` (via Einride) | Canonical stage plus raw label |
| Lead flag type and key drift | 642 string values | `true` vs `"Yes (co-led)"`, `"Likely co-led"`, `"Unknown"`; `lifeline_led` and `lifeline_ventures_led` | Boolean plus `co_lead` flag |
| Field-name drift | 91 field sets | date under 4 names (`announcement_date`, `date`, `announced`, `announcement`); co-investors under 8 names | Fixed output schema |
| Investor spelling variants | 43 strings for 5 investors | `aws Gründerfonds` (13), `Austria Wirtschaftsservice (aws)` (2), `aws Gründungsfonds` (1) | Entity IDs inline in investor fields |
| One name, several entity IDs | 49 names | `Global Founders Capital`: 3 IDs; `Target Global`: 2 IDs | Merge or link IDs |
| Same company, two histories | 49 alias strings | IQM vs IQM Quantum Computers, Jul 2022: `€10 million` EIC round vs `€128 million` Series A2; Voi vs VOI Technology: Series A lead Vostok New Ventures vs Balderton | Company entity ID per row |
| Tranches as separate rows | 26 same-stage pairs within 3 months | Oura Series D: `$75 million` tranche plus `$200 million (total, inclusive of the $75 million Dexcom tranche)`; Kemaro: one round, 3 rows | `round_group_id`, cumulative-amount flag |
| Placeholders in investor fields | 120 lead, 386 participant | `"Not publicly disclosed"`, `"Pitchdrive (+ 3 others)"`, `"Not Practica"` (Sintra, Jun 2025) | null plus `lead_disclosed`, `additional_investor_count` |
| People and prose in investor fields | 260 rows | `"Martin Villig (Bolt co-founder)"`; LiveEO lead: `"Not disclosed as sole lead; DTCF, NordicNinja, Greencode, and Segenia Capital were key investors"` | `investor_type`, `note` fields |
| Truncated or non-date dates | 7 truncated, 11 non-date | Proxima Fusion Series A: `"11 June 5"`; Vivla: year with a zero-width space; Etsy (via Accel): date `"Early-stage"` | ISO date plus precision |
| Entity type inconsistent | 17 names | EIT InnoEnergy: Organization and EducationalInstitution | One type per ID |
| Country drift | 224 null, 87 annotated | `UK (London)` next to `United Kingdom (London)`; `South Africa / Estonia` | ISO code plus `hq_city` |
| Disagrees with press (added after a later press check) | 5 rows | Oura Series A, Nov 2016: Lifeline Ventures listed as investor, but TechCrunch, tech.eu and Lifeline's own page do not put it in that round; Atlas Bio: country UK, company is in Basel | Source per investor role; see `research/accuracy/lifeline-check.md` |

**Most important for us:** the lead flag and the round label. When the investor-first flag says a fund did not lead and the company-first answer names it as lead, a founder gets the wrong answer to "will this fund lead my round?". We now show both paths on every record ("investor-first / company-first / both agree") instead of picking one.

**What worked well:** every answer carries `entities[]` with IDs and mention text, which made most of these checks possible. An ambiguous query ("Elmo") was declined with an explanation instead of a guess.

**Method:** plain Python over the raw JSON answers, no LLM judging. Dates parsed to year and month; labels mapped to pre-seed, seed, Series A to F, growth; a cross-path match is the same company name with dates within 2 months. Spelling counts come from pattern matches on the comma-split investor fields, so they are lower bounds.

Files: `cala-data-quality.json` (19 findings: findings[] with type, description, count, examples[]), this README. The table above lists the main ones; the JSON has all 19. Contact: Team Wicflow, Junction 2026, Cala challenge.
