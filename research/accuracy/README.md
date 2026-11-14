# Press accuracy checks, pooled

Three random draws of 2022+ rounds that have a named lead, each checked by hand against press on 14 Nov 2026.

| Draw | File | Seed, pool | Drawn | Correct | Partly | Wrong | No public source |
|---|---|---|---|---|---|---|---|
| First | `accuracy.json` (group `random_30`), `accuracy.md` | `random.seed(14)`, 847 led rounds of the early 1,828-round snapshot | 30 | 22 | 2 | 2 | 4 |
| Lane A | `accuracy-2a.json`, `accuracy-2a.md` | `random.seed(1401)`, first 25 of `sample(pool, 50)`, pool 2,554 | 25 | 19 | 3 | 3 | 0 |
| Lane B | `accuracy-2b.json` | same draw, second 25 | 25 | 14 | 6 | 3 | 2 |
| **All** | | | **80** | **55** | **11** | **8** | **6** |

- **Lead exactly right in 55 of 74 verifiable rounds (74%, 95% CI 63 to 83%).**
- Right lead fund named (correct or partly) in 66 of 74 (89%, CI 80 to 94%). Wrong fund in 8 of 74.
- By query path in the current snapshot: investor-first only 35 of 50 (about 70%), company-first or both 18 of 22 (about 82%). Investor-first rows that credit the queried fund as lead are the weaker part.
- The 11 sample-fund rounds in `accuracy.json` (each fund's latest led round: 9 correct, 2 partly) are not random and stay out of the pooled figure.

Caveats:

- Lane B's verdicts mostly rest on search-result text that agreed across outlets, not on opened pages (`how_checked` in `accuracy-2b.json`). Lane A gives one source URL per row.
- Some misses were pipeline errors fixed since ("Not confirmed" and "no new lead disclosed" read as a lead). The figure above is as measured, not a projection after fixes.

`pipeline/validate.py` pools the three files for the Method page. Full write-up: `research/DEEP_CHECKS.md` section 1 (outside this repo).
