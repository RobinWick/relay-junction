"""Tests for dispute.py on the two false alarms press found (run: cd app && python3 test_dispute.py)."""
from dispute import dispute, source_leads

NAMES = {"industrifonden": "Industrifonden", "nordic foodtech": "Nordic FoodTech VC", "coatue": "Coatue", "gic": "GIC",
         "altimeter": "Altimeter Capital", "sequoia": "Sequoia Capital", "practica": "Practica Capital",
         "inventure": "Inventure"}
KNOWN = set(NAMES)


def test_as_colead_with_unicode_hyphen_is_a_lead():
    src = {"answer": "**Lead investor:** **Industrifonden**, with **Nordic Foodtech VC** as co-lead.",
           "points": ["Industrifonden was the lead investor, with Nordic Foodtech VC acting as co‑lead."]}
    assert source_leads(src, KNOWN) == {"industrifonden", "nordic foodtech"}
    r = {"leads": ["nordic foodtech"], "type": "Seed", "stage": "seed", "amount_eur_m": 5.15, "source": src}
    assert dispute(r, NAMES, KNOWN) is None


def test_source_about_another_round_is_not_a_dispute():
    src = {"answer": "Anthropic announced a $65 billion Series H. The round was co-led by:\n- Altimeter Capital\n- Sequoia Capital",
           "points": []}
    r = {"leads": ["coatue", "gic"], "type": "Series G", "stage": None, "amount_eur_m": 27600.0, "source": src}
    assert dispute(r, NAMES, KNOWN) is None


def test_real_dispute_still_flagged_when_only_the_stage_label_differs():
    src = {"answer": "Roleo raised EUR 2.9 million in a seed round led by Practica Capital, with participation from Inventure.",
           "points": []}
    r = {"leads": ["inventure"], "type": "Series A", "stage": "series a", "amount_eur_m": 2.9, "source": src}
    d = dispute(r, NAMES, KNOWN)
    assert d == {"source_leads": ["Practica Capital"], "not_lead_in_source": ["Inventure"]}


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
