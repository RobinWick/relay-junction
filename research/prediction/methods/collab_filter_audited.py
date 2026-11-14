"""Audited copy of collab_filter.py: same model, but the past is stripped of the 2026-chosen fund crawl.

Why: 72% of snapshot rounds come from the investor_first crawl (cala/fetch_funds.py). The crawled funds were picked
in 2026 = a hand list (NORDIC) + the most frequent investors in ALL company-first rounds, test years included. So
the past is denser exactly for funds that go on to lead test rounds, which inflates popularity/CF scores for them.
Fix: rank only from rounds that have a company_first source (company_past/current too). Harness untouched.
Run: python3 methods/collab_filter_audited.py final        (also: po_base, stage, final_full, split:final)
"""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness  # noqa: E402
import collab_filter as cf  # noqa: E402


def company_first(r: dict) -> bool:
    return any(x.get("path") == "company_first" for x in r.get("sources") or [])


def clean_ctx(ctx: harness.Context) -> harness.Context:
    past = [r for r in ctx.past if company_first(r)]
    cp = [r for r in ctx.company_past if company_first(r)]
    cur = set().union(*(harness.investors(r) for r in cp)) if cp else set()
    # ctx.current is kept for the harness' own exclusion; the method only sees the clean insider set
    return replace(ctx, past=past, company_past=cp, current=cur | ctx.current if ctx.outside_only else cur)


def audited(rank):
    def wrapped(ctx):
        return rank(clean_ctx(ctx))
    return wrapped


RANKERS = {
    "final": audited(cf.make_rank(cf.VARIANTS["final"])),
    "final_noprior": audited(cf.make_rank(cf.VARIANTS["final_noprior"])),
    "po_base": audited(cf.make_rank(cf.VARIANTS["po_base"])),
    "stage": audited(harness.stage_leads),
    "final_full": cf.make_rank(cf.VARIANTS["final"]),  # unaudited reference
    "stage_full": harness.stage_leads,
}

if __name__ == "__main__":
    for nm in sys.argv[1:] or ["final"]:
        if nm.startswith("split:"):
            v = nm.split(":")[1]
            harness.evaluate(RANKERS[v], f"aud_{v}_<=2023", subset=lambda r: r["year"] <= 2023)
            harness.evaluate(RANKERS[v], f"aud_{v}_>=2024", subset=lambda r: r["year"] >= 2024)
            continue
        harness.evaluate(RANKERS[nm], f"aud_{nm}")
