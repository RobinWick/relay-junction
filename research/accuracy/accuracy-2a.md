# Press accuracy check, lane accuracy-a (second random draw)

Checked 14 Nov 2026 against snapshot version 20261114102039 (5,200 rounds). Raw results: `accuracy-2a.json` next to this file.

## Method

- Pool: rounds with at least one lead, year 2022 or later, key (company|YYYY-MM|stage) not already in `research/accuracy/accuracy.json`. Pool size 2,554.
- Draw: `random.seed(1401)`, first 25 of `random.sample(pool, 50)`.
- One press or primary source per round (URL in the JSON). Verdict grades the lead only. Date is graded on its own (`date_check`).

## Result

| Verdict | Count |
|---|---|
| correct | 19 |
| partly | 3 |
| wrong | 3 |
| unverifiable | 0 |

- **Lead correct in 19 of 25 (76%).** Correct or partly correct: 22 of 25 (88%).
- Pooled with the first random draw (22 of 26 verifiable): **41 of 51 verifiable rounds correct (80%)**. README and EVIDENCE quote only the first draw (22 of 26), and `research/accuracy/accuracy.md` line 110 says "about 85%". On the current snapshot it is closer to 76 to 80%.
- **Dates wrong in 4 of 25** even when the lead is right (Hopsworks, Esco, NymCard, PLATMA).
- **Stage missing in 3 of 25** (Attio, Imprint, NymCard), so these rounds never show up in a stage band.

## Wrong (3)

| Round | Cala lead | Press | Source |
|---|---|---|---|
| Green Eagle Solutions, Dec 2023, Series A, EUR 6M | Kibo Ventures | A&G Energy Transition Tech Fund led; Kibo followed on | tech.eu |
| Nozomi Networks, Mar 2024, Series E, $100M | Honeywell Ventures, Forward | Release names no lead; secondary press says Mitsubishi Electric and Schneider Electric. Honeywell and Forward only prior investors | helpnetsecurity.com |
| Sharp Performance, Oct 2026, Series A, $18M | Andreessen Horowitz | Hidden Variable led; a16z participated (a16z led the earlier seed) | pulse2.com |

## Partly (3)

- **Uzum, Mar 2024:** FinSight led, Xanara only participated. Cala counts Xanara as co-lead.
- **OneTrust, Jul 2023:** Generation led, Sands Capital participated. Cala counts Sands as co-lead.
- **PLATMA, 2024 pre-seed:** Almaz Capital and EA Group co-led. Cala shows EA Group as participant only.

Pattern: in all three "partly" cases Cala promotes a participant to co-lead, and in 2 of the 3 wrong cases Cala names the queried fund (Kibo) or an older lead (a16z) as the lead.

**By query path.** 22 of the 25 rounds come only from investor-first rows: 16 correct, 3 partly, 3 wrong (73% correct). The 3 company-first rounds were all correct. The first draw (`random.seed(14)`) was taken before the investor-first crawl, so it measured only company-first data. In the current 2022+ pool, 1,980 of 2,591 led rounds are investor-first only. **Fix:** report accuracy per path in README and EVIDENCE, and either weight investor-first leads lower or require company-first confirmation before a round counts toward "leads at your stage".

## Findings for the pipeline (evidence and fix)

1. **Queried fund is added as a participant even when it was not in the round.** Uzum 2024 lists Tencent as participant. Tencent did not invest in that round (TechCrunch); it led a later 2025 round. Cause: `app/merge.py` lines 350-351 append the investor-first query fund to `parts` whenever the row is not flagged as led. Rough count (first-token match, approximate): 253 of 2,343 investor-first rows do not name the queried fund anywhere in their lead or participant text, across 250 rounds. **Fix:** only add the queried fund when the row's own lead or participant text names it, or when the `*_led` flag is Yes; otherwise keep the row but do not attribute the fund.
2. **Year-only dates are placed in June and can be years off.** Esco's US$200M Series A (Vivo, Novo) was May 2021 (company release); Cala's row says "2026", stored as Jun 2026. PLATMA "2024" became Jun 2024 (real: Sep 2024). 375 of 5,200 rounds have only year-level dates in every source row. **Fix:** flag year-only rounds as `date_precision: year`, exclude them from "last lead" and recency claims, and prefer a sibling row with a month when one exists (PLATMA had one: "~Aug-Sep 2024").
3. **Whole-year date errors from Cala with the lead right.** Hopsworks (Cala: "Hapsworks", Mar 2022; real 29 Jun 2023), NymCard (Cala Mar 2026; real 19 Mar 2025). **Fix:** cannot be caught in the merge; surface the source date in the lead card so the founder can check it, and add these to the data-quality list.
4. **Null stage on rounds the press labels.** Attio ("Undisclosed stage"), Imprint ("Funding Round", press: Series D), NymCard (null, press: Series B). **Fix:** when `round_type` is generic, fall back to stage words in other source rows; otherwise show these under "stage unknown" rather than dropping them from counts.

## Smaller notes

- Attio: the blog reads "led by our existing partners Redpoint, Balderton and Point Nine, along with our new partner 01 Advisors". Whether 01 Advisors co-led is ambiguous; graded correct.
- ZAAN: Tencent Investment is the only investor named; the source never says "led".
- Photoroom: the release says Balderton and Aglae co-led; tech.eu describes Balderton alone as lead. Graded on the release.
- DREM: byFounders says it led a pre-seed; Cala says seed. The SEK 27M amount is only in a Nordic9 listing (unverified).
- Grid Online: Cala's participant "Grid.vc" looks like a garbled "Grid Invest"; J&T Ventures missing.
- Raw Cala text containing en or em dashes was normalised to "-" in the JSON.
