# Lead accuracy spot-check

Checked 14 Nov 2026 against an early snapshot (1,828 rounds, before the investor-first crawl). Raw results: `accuracy.json` next to this file. Each round is keyed by company + date + stage, so it can be found again in the current snapshot (5,200 rounds). A later press check of the sample lead card, ties and Creandum seeds is in `lifeline-check.md`.

## Headline

- **Random sample: lead correct in 22 of 30 checked.** Of the 26 we could verify, 22 correct, 2 partly (a co-lead missing or an accelerator counted as a lead) and 2 wrong. 4 had no source naming a lead.
- **Sample-list funds (each fund's most recent led round): lead correct in 9 of 11 checked.** The other 2 were partly right: the fund did lead, but other co-leads were left out. None were wrong.
- **Combined: 31 of 41.**

Pitch-safe line: "We spot-checked 41 Cala lead calls against press releases: 31 matched outright, 4 were partly right, 2 were wrong, and 4 had no public source naming a lead."

## Method

- Pool: rounds with at least one lead key, dated 2022 or later (847 rounds). We drew 30 at random using `random.seed(14); random.sample(pool, 30)`.
- Sample-list funds: for each of Maki.vc, Lifeline Ventures, Creandum, Inventure, Speedinvest, Northzone, Icebreaker.vc, byFounders, Seedcamp, Point Nine and Superhero Capital, we took the round with the highest `t` where the fund is in `leads[]`.
- Each round is keyed by company + date + stage, because round ids will change.
- Each named lead was checked against a primary source where one exists (company or fund release, law-firm deal note) or reputable press (tech.eu, Sifted-tier outlets, EU-Startups, Nordic9, AIN). One URL per row is listed in the JSON.
- Verdicts:
  - **correct**: the source names the same lead(s).
  - **partly**: right fund, but a co-lead is missing, or the round is not really a led round.
  - **wrong**: the source contradicts the lead.
  - **unverifiable**: no public source names a lead.
- `error_source` says whether the error came from Cala's row (`cala`) or from our own parsing of it (`pipeline`).

## Random 30

| Company | Date | Stage | Amount (Cala) | Cala lead(s) | Verdict |
|---|---|---|---|---|---|
| AMSilk | 2025-09 | series d | EUR 52M | ATHOS | correct |
| Aventix | 2026-09 | pre-seed | ~EUR 1.2M | Voima Ventures | partly |
| Nivoda | 2024-11 | series c | $51M | Northzone | correct |
| NewOrbit | 2026-06 | series a | $18.5M | Voyager Ventures | correct |
| Ivy | 2023-08 | series a | $20M | Valar Ventures | correct |
| Outpost24 | 2025-12 | growth | undisclosed | Vitruvian Partners | correct |
| ICEYE | 2025-12 | series e | EUR 150M | General Catalyst | correct |
| Fracttal | 2023-10 | series b | ~$10M | Kayyak Ventures | correct |
| ConfidentialMind | 2023-11 | seed | EUR 3.5M | D11Z Ventures, Lifeline Ventures | unverifiable |
| xMoney | 2025-09 | n/a | $21.5M | Sui Foundation | correct |
| Qida | 2023-03 | series b | EUR 18M | Kibo Ventures | correct |
| Intergrid | 2023-09 | pre-seed | EUR 1M | Lifeline Ventures | correct |
| Value.Space | 2023-04 | seed | not disclosed | Specialist VC | unverifiable |
| Codesphere | 2024-05 | series a | ~$18M (EUR 16.5M) | Creandum | correct |
| Qred AB | 2022-12 | n/a | SEK 111M | Nordic Capital | correct |
| TuringDream | 2025-06 | seed | EUR 6M | Adara Ventures, HWK | correct |
| Stegra | 2024-01 | n/a | ~EUR 300M | Temasek | **wrong** |
| Spring Health | 2023-04 | series d | $71M | "Not confirmed" | **wrong** |
| Moonlight AI | 2026-05 | seed | EUR 2.8M | Lotus One, MEDIN Fund, VP Venture Partners | correct |
| Haelixa | 2026-02 | seed | EUR 2M | Verve Ventures, Zuercher Kantonalbank | correct |
| Beside | 2025-11 | series a | $20M | EQT Ventures | correct |
| Makersite | 2022-10 | series a | EUR 18M | Hitachi Ventures, Translink Capital | correct |
| Brickken | 2025-01 | seed | $2.5M | Cryptoplaza | unverifiable |
| Mews | 2026-01 | series d | $300M | EQT Growth | correct |
| Camphouse | 2023-10 | series a | EUR 7M | eEquity, Fairpoint Capital | unverifiable |
| Pixelgen Technologies | 2022-12 | seed | ~$6M | Navigare Ventures | correct |
| Vugene | 2025-05 | pre-seed | EUR 1M | Superhero Capital | correct |
| Biorce | 2024-11 | seed | EUR 3.5M | Mustard Seed Maze, YZR Capital | correct |
| Stilta | 2026-01 | n/a | ~$500K | Y Combinator | partly |
| Koll | 2025-01 | seed | EUR 400K | Superhero Capital | correct |

## Sample-list funds (most recent led round)

| Fund | Company | Date | Stage | Amount (Cala) | Cala lead(s) | Verdict |
|---|---|---|---|---|---|---|
| Maki.vc | Sono | 2026-06 | seed | $1M | Maki.vc | correct |
| Lifeline Ventures | Vensum Power | 2026-11 | series a | EUR 9M | Eviny, "Larsen", Lifeline, "Toubro Group" | correct (parser split) |
| Creandum | Ancep | 2026-11 | n/a | $8.5M | Creandum | correct |
| Inventure | Hamina Wireless | 2025-07 | seed | undisclosed | Inventure | correct |
| Speedinvest | Emmi AI | 2025-04 | seed | EUR 15M | 3VC, PUSH VC, Serena, Speedinvest | correct |
| Northzone | Blitzy | 2026-05 | series b | $200M | Northzone | correct |
| Icebreaker.vc | FleetBrains | 2025-03 | pre-seed | $860K | Icebreaker.vc | correct |
| byFounders | Fluencify | 2026-09 | pre-seed | EUR 3.7M | byFounders | correct |
| Seedcamp | Marble | 2026-11 | seed | $4M | Seedcamp | partly |
| Point Nine | TesterArmy (now e2e) | 2026-11 | seed | $8M | Point Nine | partly |
| Superhero Capital | KineDB | 2026-10 | pre-seed | EUR 850K | Superhero Capital | correct |

## Wrong cases

1. **Stegra, Jan 2024, ~EUR 300M (Cala: Temasek).** Stegra's own release of 22 Jan 2024 (then called H2 Green Steel) says close to EUR 300M of equity came from new shareholders Microsoft Climate Innovation Fund, Mubea and Siemens Financial Services, plus IMAS Foundation and Just Climate. It names no lead and does not mention Temasek. Temasek does appear in Stegra's later 2026 round, so Cala likely moved it into the wrong round. Error source: Cala.
2. **Spring Health, Apr 2023, $71M Series D (Cala: "Not confirmed").** Cala's raw row is honest: `lead_investor: "Not confirmed"`. The investors were never officially disclosed (Behavioral Health Business, 12 Apr 2023). The bug is ours: the parser turned "Not confirmed" into an investor key, so the round counts as led. Error source: pipeline. **Fix:** treat strings like "Not confirmed", "Not disclosed", "Unknown" and "N/A" as no lead. This round should land in "lead unknown in Z".

## Partly right

- **Aventix (Voima Ventures).** bionity, 1 Oct 2026: led by Kost Capital and Voima Ventures. Kost Capital is missing.
- **Stilta (Y Combinator).** This is YC's standard W26 deal (~$500K), an accelerator cheque rather than a led round. As recorded, YC shows up as "leads at pre-seed". **Fix:** exclude accelerator and incubator `round_type` rows from lead counts. Stilta's real seed ($10.5M, May 2026) was led by a16z.
- **Marble (Seedcamp).** Marble Cognition's $3.75M pre-seed was co-led by Heartcore and Seedcamp (IT Brief, Nov 2026). Cala lists only Seedcamp and says it was a $4M seed.
- **TesterArmy / e2e (Point Nine).** The Recursive (3 Nov 2026) says the round was "led by Credo Ventures, KAYA, Point Nine, Baobab Ventures and Script Capital". Cala names only Point Nine, which makes Point Nine look like a sole lead.

## Unverifiable

- **ConfidentialMind (Lifeline + D11Z, "Nov 2023 seed EUR 3.5M").** No such round was found. The company's first priced round was a EUR 1.5M pre-seed led by Failup Ventures in Jun 2024. Lifeline and D11Z show up as investors in an Apr 2026 seed (aggregators only, no lead stated). The date looks wrong.
- **Value.Space (Specialist VC).** Tech.eu, AIN and Inventure all list Specialist VC among the participants but name no lead. The snapshot also merged an Apr 2023 accelerator row into the 9 May 2023 seed, so the stored date and amount ("Not disclosed") come from the wrong row.
- **Brickken (Cryptoplaza).** The company's release names no lead, and Cryptoplaza is not among the investors it lists. Only Seedtable, which estimates allocations, marks Cryptoplaza as lead.
- **Camphouse (eEquity, Fairpoint).** A EUR 7M round on 19 Oct 2023 from these two investors is confirmed by the tech.eu funding database and by Mergr. No press release names a lead.

## Other data issues seen (lead correct)

- **Vensum Power.** The parser split "Larsen & Toubro Group" into two investors, "Larsen" and "Toubro Group". **Fix:** do not split names on "&".
- **Stage and size drift.** Lead was right, but stage or size was off in several rounds:
  - Qida: EUR 18M is Series A per CB Insights, not B.
  - Haelixa: pre-Series A per press, not seed.
  - Sono: $1.5M pre-seed, not $1M seed.
  - Vugene: seed per most press, not pre-seed.
  - Marble: pre-seed, not seed.

  "Round sizes it leads" and "Leads at your stage" depend on these fields, so treat them as roughly right, not exact.

## What this means for the product

- The headline claim holds. When Cala names a lead, this first draw matched public sources in 22 of 26 verifiable rounds. Pooled with two later draws (`accuracy-2a`, `accuracy-2b`, see `README.md` in this folder) the lead is exactly right in 55 of 74 verifiable random rounds (74%, 95% CI 63 to 83%), and the right lead fund is named in 66 of 74 (89%). Investor-first-only rows are weaker (about 70%) than company-first or both (about 82%). For the sample-list funds, the named fund really did lead every time (11 of 11), though 2 of those rounds had co-leads we did not show.
- The most common error is a **missing co-lead**, not a wrong fund. That inflates "sole lead" impressions but not "Led X of Y".
- Two cheap pipeline fixes remove 2 of the 8 problems:
  - treat "Not confirmed"-style strings as no lead;
  - exclude accelerator rows from lead counts.

  Also stop splitting names on "&".
