# Lifeline lead card, sample ties and Creandum seeds: press check

Checked 14 Nov 2026 with free web search only (no Cala calls). Data: `cala/data/snapshot.json` (version 20261114013628), `lead_comes_back()` in `app/engine.py`, which the sample shows as:

> In the data, Lifeline Ventures led 10 rounds whose company raised again. It joined the next round in 9 of 10 and led it in 3.

The UI shows only the counts, not the company names. `docs/EVIDENCE.md` line 25 says "9 of 10 of its companies": that is wrong wording, the 10 cases are 10 rounds in 8 companies (Vensum Power and Steady Energy count twice).

## Verdict

- **Led it in 3: holds.** All three (Vensum Power 2023 and 2026, Steady Energy 2024) are in press, each as lead or co-lead.
- **Joined the next round in 9 of 10: the number is roughly right, but one "yes" and one "no" are not supported.**
  - Oura counts as "came back" for the Nov 2016 Series A. No source puts Lifeline in that round: TechCrunch and tech.eu name only Joi Ito and Jaan Tallinn, and Lifeline's own portfolio page says the 2016 Series A was "Led by David Shuman and Harpreet Rai" and lists Lifeline again only from the 2021 Series C.
  - Ambio counts as "did not come back" because Cala has a Jan 2024 "Seed, Undisclosed, investors not disclosed" row, dated "(approximate)", which Cala's own answer attributes to PitchBook. No press source and not Lifeline's page. Lifeline's page shows Ambio's next round as the Oct 2026 seed led by b2venture "with Lifeline Ventures", so the real answer is probably "came back".
  - Verda is one of the 10 (Apr 2026 USD 117m, then Sep 2026 Series B). Both facts hold in press, but the Apr 2026 round was equity plus debt with Lifeline leading the equity, and Lifeline's own page labels its 2026 Verda investment "Series B". SCRIPT.md item 9 says never show Verda.
- **Without Verda and with the two disputed cases removed**, the press-confirmed record is: Lifeline came back in 7 of 7 confirmed next rounds and led 3. With Verda, 8 of 8.

## The 10 cases

| # | Company | Round Lifeline led (Cala) | Next round (Cala) | In next? | Led next? | Press check |
|---|---|---|---|---|---|---|
| 1 | Aiven | Seed, Aug 2017, USD 1m, lead Lifeline | Series A, May 2019, ~USD 9m, lead Earlybird, Lifeline in | yes | no | Confirmed. Seed 2017 by Lifeline (Aiven one-pager, Lifeline page). Series A EUR 8m led by Earlybird with Lifeline and Risto Siilasmaa (Aiven press release). Cala's month (Aug) differs from June 2017 elsewhere. |
| 2 | Hyperion Robotics | Seed, Oct 2022, EUR 3m, lead Lifeline | Series A, Jul 2026, EUR 6.4m, co-led Course Corrected and EIC Fund, Lifeline in | yes | no | Confirmed. Company release: Lifeline participated as existing investor. Press mostly calls it growth funding, not Series A. |
| 3 | Vensum Power | Seed, Nov 2019, EUR 1m, lead Lifeline | Seed, May 2023, EUR 3.8m, lead Lifeline | yes | yes | 2019 round: only Lifeline's own page ("2019 Lifeline Ventures Seed round"); amount EUR 1m not found in press. 2023 round confirmed: tech.eu, led by Lifeline. |
| 4 | Vensum Power | Seed, May 2023, EUR 3.8m, lead Lifeline | Series A, Nov 2026, EUR 9m, co-led Lifeline, L&T, Eviny | yes | yes (co-lead) | Confirmed: tech.eu 6 Nov 2026. Never call Lifeline the sole lead. |
| 5 | Steady Energy | Seed, Jun 2023, EUR 2m, co-led Lifeline, VTT, Yes VC | Series A, Mar 2024, EUR 10m, co-led Lifeline, Yes VC | yes | yes (co-lead) | Confirmed (AIN, BeBeez). Lifeline's own page labels these "Pre-seed 2023" and "Seed 2024", not seed and Series A. |
| 6 | Steady Energy | Series A, Mar 2024, EUR 10m | Series B, Mar 2025, EUR 22m, lead 92 Ventures, Lifeline in | yes | no | Confirmed (AIN, Roschier). Lifeline's page says "Led by 92 Ventures, and Lifeline Ventures", which reads as a co-lead; press names 92 Ventures as lead. Cala puts the Jul 2025 investors (Tesi, LocalTapiola, Move Energy, Valo) on the Mar 2025 row. |
| 7 | Ambio | Pre-seed, Jun 2023, ~USD 1.3m, lead Lifeline | Seed, Jan 2024, undisclosed, no investors | **no** | no | Pre-seed by Lifeline: Lifeline page confirms, amount not found. The Jan 2024 round: not found anywhere; Cala's answer cites PitchBook, date "approximate". Real next round: Oct 2026 EUR 5.1m led by b2venture with Lifeline (tech.eu). **Disputed.** |
| 8 | P2X Solutions | Seed, May 2021, EUR 2m, lead Lifeline | Series A, Dec 2021, ~EUR 20m equity, lead Enersense, Lifeline in | yes | no | Confirmed: Nordic9 (seed), FuelCellsWorks (8 Dec 2021 agreement with Enersense, "Lifeline Ventures will participate"). Lifeline's page dates it 2022. |
| 9 | Oura | Seed, Nov 2015, USD 2.3m, lead Lifeline | Series A, Nov 2016, EUR 5m, no lead, Lifeline listed | **yes** | no | Seed confirmed. Lifeline in the 2016 Series A: **not supported**. TechCrunch and tech.eu name Joi Ito and Jaan Tallinn only; Lifeline's own page names other leads and does not list itself. **Disputed.** |
| 10 | Verda | "Series A (follow-on)", Apr 2026, USD 117m, lead Lifeline | Series B, Sep 2026, USD 189m, lead Emergence, Lifeline in | yes | no | Facts confirmed: TNW (equity led by Lifeline plus debt from Nordic lenders, no series label), tech.eu (Series B led by Emergence, Lifeline in). Label and amount are wrong as an equity Series A. **Never show** (SCRIPT.md item 9). |

## Sample ties

**Reduciner (Voima Ventures row tie): holds, with one caveat.**
- Lifeline and Voima were both in Reduciner's first funding round, announced 5 May 2026, EUR 3.6m: equity from Voima Ventures, Lifeline Ventures and the Mikko Kodisoja Foundation, and VTT's in-kind investment of technology and IP. So "4 investors" holds if VTT counts; 3 equity investors.
- Caveat: Cala marks Lifeline and Voima as co-leads (investor-first path). tech.eu and VTT name no lead and no stage label ("first funding round"). Cala also has a second row for the same date labelled "Series A" (Voima, no amount). Do not say "co-led" or "seed" out loud.

**Ovido (Kvanted row tie): holds. The deck's 4 is right; SCRIPT.md's 5 is wrong.**
- EUR 2.4m seed, June 2025, co-led by Lifeline Ventures and Kvanted, with Illusian, and support from Business Finland (BeBeez, Ovido's blog, tech.eu). That is 4 names; tech.eu lists only the first 3. Illusian appears once ("Illusian Founder Office" in one Cala row is the same firm).
- The app computes 4 (`n_investors: 4`) from the current snapshot. SCRIPT.md item 7 still says "5-investor": change it to 4 or drop the count. Business Finland gave R&D support, not equity, so "3 equity investors" is the strict count.

## Creandum seed leads dated Oct 2026

| Company | Cala | Press | Verdict |
|---|---|---|---|
| Ares Intelligence | Seed, 30 Oct 2026, ~USD 2.9m, lead Creandum, Lakestar participant, UK | GBP 2.5m, co-led by Creandum and Lakestar, London (StartupMag, Nordic9; Nordic9 calls it pre-seed) | Creandum lead correct. Lakestar is a co-lead, not a participant. |
| Machenta | Seed, 27 Oct 2026, USD 40m, co-led Creandum and USV, UK | USD 40m seed co-led by Creandum and Union Square Ventures, Imperial College spinout, London (The AI Insider, TechFundingNews) | Correct. |
| Atlas Bio | Seed, 27 Oct 2026, USD 10m, lead Creandum, UK | USD 10m seed led by Creandum; company is Basel, Switzerland; total USD 12.5m with an earlier USD 2.5m pre-seed (tech.eu) | Lead and amount correct. Country wrong (Switzerland, not UK). |
| Turba Labs | "Seed & Series A", 6 Oct 2026, USD 52m, co-led Creandum and Cusp Capital, US | "nearly USD 52m in combined seed and Series A financing, led by Creandum and Cusp Capital" (Nordic9, Dealroom) | Leads correct. It is two rounds in one figure; our pipeline stores it as one seed of EUR 47.8m. Do not use it as a seed size. |

## What to do with this

- **On stage with the Lifeline partner**: do not show or say "9 of 10" as "your own record" without the two caveats. If the card stays on screen, the safe spoken line is "led three of the next rounds" (confirmed) and nothing about Oura or Ambio. Never name Verda.
- **EVIDENCE.md line 25**: "9 of 10 of its companies" should read "9 of 10 rounds (8 companies)", or better be cut until the Oura and Ambio rows are fixed.
- **SCRIPT.md item 7**: Ovido count is 4, not 5.
- Data-quality finding added: `data_quality/cala-data-quality.json`, type `disagrees_with_press` (Verda label, Oura participant, Ambio round, Atlas Bio country, Ares Intelligence co-lead). Turba Labs is not in it: Cala's row says "Seed & Series A" correctly, and storing it as one seed is our pipeline's mistake. Not synced: `app/static/cala-data-quality.json` (the copy the app serves) and the README table in `data_quality/`.

## Sources

- Aiven: https://aiven.io/press/aiven-closes-8-million-series-a-round , https://cdn.mediactive-network.net/events/vivatech/uploads/services/surcouche/Aiven-Company-OnePage-1_1623769192_BRKF77.pdf , https://nordic9.com/news/aiven-closes-a-1m-equity-investment-for-professional-cloud-hosting-and-database-management-services-news5464083109
- Hyperion Robotics: https://www.hyperionrobotics.com/2022/10/ , https://nordic9.com/news/hyperion-robotics-raised-a-3-million-funding-round-led-by-lifeline-ventures/ , https://www.hyperionrobotics.com/hyperion-robotics-raises-7-4-million-to-scale/ , https://tech.eu/2026/07/16/hyperion-robotics-secures-74m-to-expand-robotic-construction/
- Vensum Power: https://tech.eu/2023/05/26/finnish-start-up-vensum-raises-3-8-million-to-develop-software-controlled-power-converters/ , https://tech.eu/2026/11/06/vensum-power-raises-eur9m-to-cut-power-losses-in-ai-data-centres-ev-charging-and-energy-storage/
- Steady Energy: https://en.ain.ua/2023/06/27/steady-energy-raises-2m , https://en.ain.ua/2024/03/21/steady-energy-secures-a-10m-investment , https://en.ain.ua/2025/03/28/finnish-steady-energy-secures-eur22m-in-funding-led-by-92-ventures , https://www.roschier.com/newsroom/roschier-advises-steady-energy-in-its-b-round-financing , https://siliconcanals.com/steady-energy-secures-e32m/
- Ambio: https://tech.eu/2026/10/15/from-slush-to-sustainable-materials-ambio-raises-eur51m-for-ai-powered-plastics-procurement/ , https://bebeez.eu/2026/10/14/finnish-startup-secures-e5-1-million-seed-to-make-recycled-plastics-procurement-more-reliable/
- P2X Solutions: https://nordic9.com/news/p2x-solutions-announced-raising-2-million-from-lifeline-ventures/ , https://fuelcellsworks.com/?p=76449
- Oura: https://techcrunch.com/2016/11/29/oura-ring-raises-e5-million-to-take-its-smart-jewelry-mainstream/ , https://tech.eu/2016/11/30/ouraring-raises-5million/ , https://www.multivu.com/players/uk/7992251-ouraring-series-a-wellness-ring/
- Verda: https://thenextweb.com/news/verda-117m-funding-lifeline-ventures-ai-cloud , https://tech.eu/2026/09/22/verda-raises-189m-to-advance-its-ai-cloud-and-expand-compute-capacity
- Lifeline Ventures portfolio page (rounds per company, primary source for Lifeline's own record): https://www.lifelineventures.com/companies/
- Reduciner: https://tech.eu/2026/05/05/deeptech-startup-reduciner-secures-eur36m-to-convert-emissions-into-value/ , https://www.vttresearch.com/en/news-and-ideas/deep-tech-startup-reduciner-introduces-novel-technology-turn-captured-carbon
- Ovido: https://tech.eu/2025/06/17/ovido-raises-eur24m-to-democratize-supply-chain-data-management/ , https://bebeez.eu/2025/06/17/helsinkis-ovido-secures-seed-funding-to-expand-ai-powered-compliance-platform/ , https://ovido.eu/blogs/say-hello-to-ovido
- Ares Intelligence: https://www.startupmag.co.uk/funding/ares-intelligence-2026-seed-funding/ , https://nordic9.com/news/ares-intelligence-closed-a-25-million-pre-see/
- Machenta: https://theaiinsider.tech/2026/10/27/imperial-college-london-spinout-machenta-raises-40m-in-seed-funding-for-instant-learning-robots/ , https://techfundingnews.com/machenta-40m-seed-creandum-usv-simulation-robot-learning/
- Atlas Bio: https://tech.eu/2026/10/27/swiss-startup-atlas-bio-secures-125m-to-tackle-drug-developments-70-failure-rate-and-move-beyond-animal-testing/
- Turba Labs: https://nordic9.com/news/turba-labs-raised-nearly-52m-in-combined-seed/ , https://dealroom.co/news/160619-turba-labs-raises-52m-to-double-ai-compute-without-new-data-centers/

How each source was read: opened and read directly were Lifeline's portfolio page, TechCrunch, tech.eu and the Ouraring release (Oura), TNW (Verda Apr 2026), Hyperion's own release (2026), tech.eu and VTT (Reduciner), tech.eu and BeBeez (Ovido), tech.eu (Ambio). All other rows rest on web-search result text quoting those pages, not on a full read. The two disputed Lifeline cases (Oura, Ambio) and the Verda caveat rest on directly read pages.
