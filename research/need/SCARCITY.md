# Lead scarcity: is the problem real?

Source: cached Cala snapshot `cala/data/snapshot.json`, version 20261114133847 (5,146 rounds). No API calls.
Every number below comes from `research/need/scarcity.py` (run from `/Users/robinwickholm/junction-2026`), which
writes `research/need/scarcity.json`. Lane (d) also reads `relay/app/validation.json` and recomputes it.

## Slide headlines (each true as defined)

1. **About half of the most active Nordic seed investors do not lead.** Of the 47 most active investors in Nordic
   pre-seed and seed rounds 2023 to 2026 that have 3+ rounds with a named lead, 23 led at least half of those
   rounds and 24 did not. (Top 50 by rounds joined, public bodies left out; 350 rounds, 255 with a named lead.)
2. **Only 3 in 10 names on a seed announcement led the round.** In the 255 Nordic pre-seed and seed rounds
   2023 to 2026 with a named lead, 308 of 1,042 named investor seats (30%) are lead seats. Europe: 1,006 of 3,252
   (31%, 779 rounds).
3. **Your last lead rarely leads again.** Across 1,405 cases where a named lead's company raised a next round
   (2+ months later), the lead joined that next round in 840 (60%) but led it in 212 (15%).
4. **A 14-fund list holds about 7 that lead less than half the time.** Drawn at the rate of headline 1 (24 of 47),
   a 14-name list is expected to hold 7.1 investors who lead under half their rounds, and 1.2 that meet the
   strict "Mostly follows" rule (under 15% led, 5+ rounds).
5. **You cannot tell which from the name.** The demo's own 13-fund sample list, run through the engine at seed,
   EUR 3m: 9 lead at that stage, 2 are Mixed, 1 Mostly follows, 1 is a public body.

Honest framing for the deck: the data does **not** show that leads are almost extinct. It shows a coin flip:
among the investors a founder is most likely to list, roughly half lead and half do not, and only about 30% of
the names on announcements are leads. The need is sorting the list, which is what Recount does.

## Definitions

- **Round set**: stage `pre-seed` or `seed`, year 2023 to 2026 (2026 runs to the snapshot date), not `disputed`,
  not `not_led` (the engine's exclusions).
- **Country**: the first place named in the round's `country` field (text before `/` or `(`), lower case, with
  UK, England and Scotland folded to United Kingdom.
- **Nordic**: Finland, Sweden, Denmark, Norway, Iceland, Estonia. **Europe**: EU and EEA countries, UK,
  Switzerland, Balkans, Ukraine (full list in the script).
- **Rounds joined**: rounds in the set where the investor is a named lead or participant.
- **Active list**: top 50 investors by rounds joined, ties by name. Public bodies and programmes (engine `HUBS`,
  for example Business Finland, EIC) are left out because they do not lead equity rounds by design.
- **Lead share**: rounds led / rounds joined that have a named lead. Co-leads count as led.
- **Judged**: 3+ rounds with a named lead (the engine's "Too few rounds" floor).
- **Leads mostly**: lead share >= 0.5 (engine `LEAD_SHARE`). **Mostly follows**: 5+ rounds with a named lead and
  lead share < 0.15 (engine rule).

## Results

### (a) Nordic, pre-seed and seed, 2023 to 2026

| | value |
|---|---|
| Rounds in set / with named lead | 350 / 255 |
| Distinct investors seen | 747 |
| Top 50 cutoff | 4+ rounds joined |
| Judged (3+ known) | 47 |
| Lead at least half | 23 (49%) |
| Lead under half | 24 (51%) |
| Mostly follows (strict) | 4 |
| Median lead share | 0.455 |

Sensitivity: with the engine's follow-on rule (a later round in a company the investor already backed, not led,
is skipped), 24 of 46 lead at least half. With public bodies kept in, 22 of 48.

### (b) Europe, pre-seed and seed, 2023 to 2026

| | value |
|---|---|
| Rounds in set / with named lead | 997 / 779 |
| Distinct investors seen | 1,952 |
| Top 50 cutoff | 10+ rounds joined |
| Judged | 50 |
| Lead at least half | 30 (60%) |
| Lead under half | 20 (40%) |
| Mostly follows (strict) | 8 |
| Median lead share | 0.607 |

Sensitivity: follow-on rule 29 of 50; public bodies kept in 27 of 50.

### (c) Lead seats

Rounds with a named lead, seats = named leads + named participants.

| Scope | rounds | lead seats | all seats | lead share | rounds with 2+ investors: lead share |
|---|---|---|---|---|---|
| All rounds, all stages | 3,214 | 4,216 | 14,228 | 29.6% | 26.6% (2,619 rounds) |
| Nordic pre-seed and seed 2023 to 2026 | 255 | 308 | 1,042 | 29.6% | 27.0% (218 rounds) |
| Europe pre-seed and seed 2023 to 2026 | 779 | 1,006 | 3,252 | 30.9% | 28.6% (673 rounds) |

### (d) Does the last lead lead again?

`validation.json` `lead_comes_back` (recomputed now from the same snapshot with `relay/pipeline/validate.py`,
identical): 1,405 cases, came back 840 (59.8%), led again 212 (15.1%). A case is one named lead (not a public body)
of one round, paired with the same company's next round 2+ months later, all stages.

### (e) A 14-fund list

From (a): p(lead under half) = 24/47, p(strict Mostly follows) = 4/47, p(lead at least half) = 23/47.
Expected in 14 names: 7.1 under half, 1.2 strict Mostly follows, 6.9 lead at least half. (A binomial with
independent draws, a simplification, gives 64% that 7 or more of the 14 lead under half.)

The real sample list in `relay/app/static/app.js` has 14 lines, 13 of them funds (the 14th is a coffee note).
Engine verdicts at seed, EUR 3m:

| Fund | Verdict | led / known |
|---|---|---|
| Maki.vc | Leads rounds like yours | 8 / 11 |
| Voima Ventures | Leads rounds like yours | 13 / 13 |
| Creandum | Leads, but larger rounds | 17 / 25 |
| Inventure | Leads at your stage, size unclear | 5 / 7 |
| Speedinvest | Leads rounds like yours | 26 / 47 |
| Northzone | Leads, but larger rounds | 13 / 22 |
| Icebreaker.vc | Mixed | 3 / 9 |
| byFounders | Leads at your stage, size unclear | 18 / 25 |
| Seedcamp | Mixed | 6 / 23 |
| Point Nine | Leads at your stage, size unclear | 6 / 8 |
| Business Finland | Public body or programme | 0 / 12 |
| Superhero Capital | Leads rounds like yours | 16 / 26 |
| FJ Labs | Mostly follows | 3 / 35 |

The sample was picked to show the product, so it is lead-heavy (9 of 13) and is not evidence of scarcity on its
own. Headline 4 uses the counted rate, not the sample.

## Caveats (say these if asked)

- **Selection bias.** The snapshot was built by querying 194 named funds (investor-first) plus company histories.
  35 of the Nordic top 50 and 46 of the Europe top 50 are queried funds. Funds chosen because they are known seed
  investors probably lead more than the average name on a founder's list, so the "about half" figure is more
  likely an upper bound on leaders than a lower one. We have not proven that.
- **Lead named means named in Cala's answer.** 95 of 350 Nordic rounds have no named lead and are left out of
  every share.
- **Angels and generic names.** The top lists include individual angels (for example in the Nordic list) and one
  generic key ("Business Angels" in Europe). They were kept: a founder's list contains them too.
- **Small n per investor.** The Nordic top 50 cutoff is 4 rounds joined; individual shares are noisy. Use the
  counts, not any one investor's share, on a slide.
- **Not externally verified.** Per-fund numbers are counts in the snapshot, not checked against press for this
  write-up.
