# Can Cala data predict who leads your next round? Re-test, 14.11 11:00-11:40

Harness: `harness.py`. Test: 558 rounds found company-first (2021-2026), each predicted only from rounds before it.
8 method families ran in parallel (`methods/`), each checked by an adversarial audit.

## Honest numbers (after the leak fix)

| Question | Top 1 | Top 5 | Top 20 | Simple baseline | Random |
|---|---|---|---|---|---|
| Who leads the next round (current investors allowed) | 16% | 26-27% | 30-33% | "last lead again" (previous lead, then other current investors) 25% top 5; previous lead only 17% | about 0% |
| Which NEW outside fund leads | 1% | 4-5% | 11-12% | stage popularity 2% top 5 | 0.15% top 5 |

- Best methods: learning-to-rank (OUTSIDE top 5 6.9%, audit found no leak in the code) and the co-investment graph
  (6.3%, 5.0% after the crawl fix, 3.8% on the 2024-26 holdout).
- Series B and later are easier: top 5 36% (insiders re-lead more often).
- "Will a current investor lead?" as yes/no: AUC 0.63, weak.

## The leak the audits found

The 195 funds we asked Cala about were picked by how often they appear in company-first rounds, including the
test rounds. So funds that led test rounds have richer past data because they led test rounds. Restricting the
past to company-first rounds removes most of the outside-fund gain (several methods fall back to the 2% baseline).
Treat the OUTSIDE 6-7% as an upper bound; 4-5% is the defensible figure.

## Verdict

- Predicting a new outside lead stays weak: about 1 in 20 in the top 5, 1 in 9 in the top 20.
- The strongest predictor is your own cap table: a current investor leads about 1 in 4 next rounds; the
  previous round's lead itself about 1 in 6 (17%, `previous_lead_only` in `baselines.txt`).
- Pitch line (true): "We tested prediction on 558 real rounds. A current investor leads about 1 in 4 next rounds; the previous lead itself about 1 in 6.
  A new outside lead can't be predicted from round data (about 5%), so we show the evidence instead."
