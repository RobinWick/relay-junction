# Backtest: 20 real Nordic seed rounds, replayed the day before

Script: `research/need/backtest.py` (run `python3 research/need/backtest.py` from `junction-2026/`). Output with every row: `research/need/backtest.json`. Snapshot version 20261114133847, cached data only, no Cala calls. The engine (`relay/app/engine.py`) is imported unchanged.

## What was tested

The founder pastes the funds that ended up in their round into Recount the day before it closed. Recount only sees rounds dated strictly before that round (time cut as in `harness.py`, t < round t minus 0.01, so same-month rounds are not "the past"), with the engine's "now" set to the round date. Each fund gets `fund_profile` (stage = the round's stage, target = the round's actual amount), grouped and ordered the way the app does it (`app.js` groupOf and rankRows, with no LinkedIn network, no competitors). The founder's own investors for the "Ask X" tie are the company's investors in earlier rounds before the cut. Paste order is alphabetical, so the answer cannot leak through list order.

Sample: Nordic country, seed or pre-seed, 2025 or 2026, a named lead, 3+ investors, found company-first (not because we asked about a fund), not disputed, not a not-led round. That gives 33 rounds at 31 companies. One round per company, 20 companies drawn with `random.seed(1415)`.

**This measures whether Recount separates leaders from followers on a real list. It does not measure whether Recount finds new funds: the list is the eventual cap table, so the lead is always on it.**

## Results (n = 20 rounds, 157 listed names)

| Measure | Result | 95% CI (Wilson) |
|---|---|---|
| Eventual lead in "Pitch first" | **5 of 20** | 11% to 47% |
| Same, without a target amount | 6 of 20 | 15% to 52% |
| Lead ranked first by a lead verdict (Pitch first or "Leads, but a different size") | **5 of 20** | 11% to 47% |
| Lead ranked first, any reason | 8 of 20 (3 of these are tie-breaks inside "Too few rounds", not a verdict) | 22% to 61% |
| Random order would put a lead first | 4.65 of 20 expected | |
| Lead had any verdict other than "Too few rounds" | 11 of 20 | |
| Of those 11: lead in Pitch first / ranked first by a verdict | 5 of 11 / 5 of 11 | 21% to 72% |
| Funds Recount put in Pitch first | 8, of which **6 led** that round | 41% to 93% |
| Funds called "Mostly follows" | 5 of 157; **0 of the 5 led** | 0% to 43% |
| Eventual lead called "Mostly follows" | 0 of 20 | |
| Listed names with "Too few rounds" | 122 of 157 (78%) | |
| Listed names with no round at all before the cut | 74 of 157 | |

Read it plainly:

- When Recount says "Pitch first", it is usually right: 6 of the 8 funds it put there led. The other two (byFounders at Lovable, Navigare Ventures at TeraSi) were in the round as participants.
- It never told a founder to deprioritise the fund that went on to lead (0 of 20 leads called "Mostly follows").
- But most of the time it has nothing to say. 78% of names on a real seed cap table get "Too few rounds", because those lists are mostly named angels and small or foreign funds with little earlier history in the data. In 9 of 20 rounds the lead itself was "Too few rounds" (Accel at Polar, Systemiq Capital at eComID, Primary Venture Partners at Zero, Extantia Capital at Renasens, among others).
- Real misses where the lead had history: NordicNinja VC at Redpine ("Mixed", led 5 of 5 but under 2 at seed), Andreessen Horowitz at Stilta ("Mixed", led 4 of 9), Brighteye Ventures and Day One Capital at imagiLabs ("No lead since Jul 2023" and "Mixed"), Join Capital at TeraSi ("No lead since Jan 2024"), Almi Invest at Fintower (public body, not judged).

## Intro path from earlier investors

13 of 20 companies had earlier investors in the data before the cut.

- The app's tie rule (a current investor and the eventual lead in the same small round, 6 or fewer investors, last 4 years, no public bodies): **0 of 13**.
- Any shared earlier round, no limits: 4 of 13, and none passes the app's rule: Ipercept (Almi Invest with Luminar at Debricked, Jun 2020: public body and older than 4 years), Polar (SV Angel with Accel at GoCardless, Feb 2012), TeraSi (Onsight Ventures with Join Capital at Semron, 10 investors), Lovable (byFounders with Creandum at Monta, 9 investors).
- The lead was already an investor: 1 of 13 (Creandum at Lovable).

Honest conclusion: on these 20 rounds, a co-investor tie did not predict who led. Do not claim the "Ask X" feature explains real seed leads.

## Three examples for the deck (each lead checked with one web search)

1. **Intric (Sweden), pre-seed, Feb 2026, about EUR 3.8M.** List of 4: byFounders, Look Up Ventures, Mattias Miksche, Carl-Henric Svanberg. Recount, using only data before Feb 2026: byFounders "Leads rounds like yours" (led 12 of 15), ranked first; the other three "Too few rounds". byFounders led. Press: https://nordic9.com/news/intric-raised-a-38m-pre-seed-round-led-by-byfounders/ (Intric's own release: https://intric.ai/en/news/n/intric-raises-eur-3-8-million-to-scale-secure-and-independent-ai-capabilities-for).
2. **IPercept (Sweden), seed, May 2025, EUR 5M.** List of 5: Luminar Ventures, J12 Ventures, RunwayFBU, Backstage Invest, AI.Fund. Recount: Luminar "Leads rounds like yours" (led 9 of 11), ranked first; J12 "Mixed" (led 4 of 11). Press names Luminar as lead: https://bebeez.eu/2025/05/06/swedish-deeptech-startup-nabs-e5m-to-democratize-predictive-maintenance-in-european-factories/ and https://vestbee.com/insights/articles/i-percept-secures-5-m. Caveat: Seedtable's allocation table lists J12 as lead, so one source disagrees.
3. **Oplane (Sweden), seed, Jun 2026, EUR 4.5M.** List of 5: Seed Capital, Icebreaker.vc (existing investor), Emil Eifrem, Joakim Nydrén, Robert Lagerström. Recount: Seed Capital "Leads at your stage" (led 3 of 3, size unclear), ranked first; Icebreaker.vc "Mixed" (led 3 of 7). Seed Capital led. Press: https://tech.eu/2026/06/02/oplane-raises-eur45m-to-bring-security-to-ai-development-teams/. Caveat: 3 of 3 is thin evidence.

Backup, not fully checked: **Reduciner (Finland), seed, May 2026, EUR 3.6M.** Recount put Voima Ventures (led 11 of 11) and Lifeline Ventures (led 24 of 27) both in Pitch first, the VTT and foundation entries "Too few rounds". Press confirms Voima and Lifeline as the equity investors (https://tech.eu/2026/05/05/deeptech-startup-reduciner-secures-eur36m-to-convert-emissions-into-value/), but my one search did not confirm "led by" wording, so do not put "led" on a slide without a second check.

Honest miss worth showing next to the hits: **Redpine (Sweden), seed, Apr 2026.** Recount ranked Luminar Ventures first ("Leads, but smaller rounds", with an "Ask" tie); NordicNinja VC, the lead in Cala's data, got "Mixed" and rank 11 of 12. Not press-checked.

## All 20 rounds (lead as Cala reports it; only the examples above were press-checked)

| Company | Country | Date | Stage | EUR M | Lead(s) in Cala | Listed | Lead rank | Lead verdict |
|---|---|---|---|---|---|---|---|---|
| eComID | Sweden | Aug 2026 | seed | 15.64 | Systemiq Capital | 19 | 18 | Too few rounds |
| Engrate | Sweden | Jun 2025 | seed | 2.5 | Maniv (listed twice as Maniv / Maniv Mobility) | 5 | 3 | Too few rounds |
| Fintower | Sweden | Feb 2026 | seed | 1.5 | Almi Invest | 6 | 6 | Public body |
| Green Voltis | Sweden | Aug 2025 | seed | n/a | DeepMind Capital | 5 | 3 | Too few rounds |
| Hybridity | Sweden | Mar 2025 | seed | 2.0 | Stefan Lennhammer (angel) | 3 | 3 | Too few rounds |
| imagiLabs | Sweden | Jun 2026 | seed | 4.14 | Brighteye Ventures, Day One Capital | 13 | 12 | No lead since Jul 2023 / Mixed |
| Intric | Sweden | Feb 2026 | pre-seed | 3.57 | byFounders | 4 | 1 | Leads rounds like yours |
| IPercept | Sweden | May 2025 | seed | 5.0 | Luminar Ventures | 5 | 1 | Leads rounds like yours |
| Lovable | Sweden | Jan 2025 | seed | 13.8 | Creandum | 8 | 2 | Leads rounds like yours |
| Oplane | Sweden | Jun 2026 | seed | 4.5 | Seed Capital | 5 | 1 | Leads at your stage |
| Polar | Sweden | Jun 2025 | seed | 9.2 | Accel | 15 | 1 (tie-break) | Too few rounds |
| Redpine | Sweden | Apr 2026 | seed | 6.8 | NordicNinja VC | 12 | 11 | Mixed |
| Reduciner | Finland | May 2026 | seed | 3.6 | Lifeline Ventures, Voima Ventures | 4 | 1 | Leads rounds like yours (both) |
| Renasens | Sweden | Mar 2026 | seed | 10.0 | Extantia Capital | 3 | 2 | Too few rounds |
| Sapient Perception | Denmark | Apr 2026 | pre-seed | 2.0 | Balnord, FORWARD.one | 3 | 1 (tie-break) | Too few rounds |
| Stilta | Sweden | May 2026 | seed | 9.66 | Andreessen Horowitz | 10 | 9 | Mixed |
| Studio 555 | Sweden | Jun 2025 | seed | 4.0 | Failup Ventures, HOF Capital | 5 | 1 (tie-break) | Too few rounds |
| TeraSi | Sweden | Sep 2026 | seed | 11.0 | Join Capital, NATO Innovation Fund | 14 | 3 | Too few rounds / No lead since Jan 2024 |
| Vexlum | Finland | Feb 2026 | seed | 6.0 | Kvanted | 5 | 1 | Leads, but smaller rounds |
| Zero | Finland | Sep 2026 | seed | 8.93 | Primary Venture Partners | 13 | 5 | Too few rounds |

Full per-fund rows (verdict, led of known, tie) are printed by the script and stored in `backtest.json`.

## Caveats

- **n = 20 from a pool of 31.** Intervals are wide. Treat every number as "about", not as a rate.
- **The list is the eventual cap table.** This only tests ranking on a list that already contains the lead. A real founder's list also contains funds that said no; that harder case is not tested here.
- **Leads are Cala's labels.** Only Intric, IPercept and Oplane were press-checked (IPercept with one disagreeing source). The other 17 leads are as Cala reports them.
- **Fund histories were collected in Nov 2026.** The time cut removes later rounds, but which funds we queried investor-first was decided with today's knowledge. Funds we queried (byFounders, Lifeline, Luminar) have rich pre-cut history; funds we did not (Accel, Systemiq, Primary) mostly show "Too few rounds". This flatters the hits and partly explains the misses.
- **Month-level dates.** Snapshot dates are months, and the parser sets month 6 when only a year is known; five sampled rounds are dated June and may be imputed.
- **Messy lists.** Cala's participant fields include angels, duplicates (Maniv / Maniv Mobility, Evany / Eviny Ventures) and leftovers like "plus founders" or "Returning backers from the pre-seed". A founder would not paste those; they inflate the "Too few rounds" count but do not change any lead result.
- **Target = actual amount.** The size check uses the amount the round ended up at, which the founder would only roughly know. Without a target, the lead lands in Pitch first in 6 of 20 instead of 5 (Vexlum's Kvanted moves up).

## One-line claim that is safe to make

On 20 randomly drawn real Nordic seed rounds from 2025 and 2026, replayed with only the data available the day before, 6 of the 8 funds Recount put in "Pitch first" went on to lead, and Recount never labelled the eventual lead "Mostly follows"; but on most seed cap tables it says "Too few rounds" for most names.
