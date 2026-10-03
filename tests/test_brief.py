# tests/test_brief.py
"""The job brief every write request and the QC pass share."""
from estimator.ledger.facts import SETTLED, Ledger
from estimator.ledger.to_plan import ledger_plan
from estimator.writing.brief import job_brief, shared_owners, system_class
from estimator.writing.templates import load_templates

SOURCES = {"S5": "equipment counts for RTU (schedules and plans)", "S6": "equipment counts for EF (schedules and plans)",
           "S7": "equipment counts for MD (schedules and plans)", "S10": "M-201, Drawings.pdf page 3 (sheet text)",
           "S20": "RTU SCHEDULE, Drawings.pdf page 12", "Q1": "sequence section “RTU”, Specs.pdf page 4"}


def _ledger():
    L = Ledger(SOURCES)
    L.add("family", "RTU", "Rooftop Unit", "[S5]", "RTU", "schedules", SETTLED)
    L.add("count", "RTU", 2, "[S5]", "schedule rows 2", "seed", SETTLED)
    L.add("unit", "RTU", "RTU-1, 2", "[S5]", "Tags: RTU-1, 2", "seed", SETTLED)
    L.add("provider", "RTU controller", "unit mfr: DDC microprocessor controls with unit mounted panel", "[S20]", "DDC MICROPROCESSOR CONTROLS", "schedules", SETTLED)
    L.add("family", "EF", "Exhaust Fan", "[S6]", "EF", "schedules", SETTLED)
    L.add("count", "EF", 3, "[S6]", "schedule rows 3", "seed", SETTLED)
    L.add("unit", "EF", "EF-1 thru 3", "[S6]", "Tags: EF-1 thru 3", "seed", SETTLED)
    L.add("family", "MD", "Motorized Damper", "[S7]", "MD", "schedules")
    L.add("count", "MD", 4, "[S7]", "plan placements 4", "seed")
    L.add("link", "MD-1", "EF-1", "[S10]", "MD-1 EF-1", "plans", SETTLED)
    L.add("link", "EF", "RTU-1", "[S10]", "EF-1 interlocked with RTU-1", "risers", SETTLED)
    L.add("note", "general", "fire/smoke dampers are controlled by the fire alarm system", "[Q1]", "Fire/smoke dampers shall be controlled through the fire alarm system", "sequence", SETTLED)
    L.understanding = {"schedules": "Two rooftop units and three fans.", "sequence": "Two packaged rooftop units serve the corridors; three exhaust fans interlock with them."}
    L.job_name = "26-9999"
    return L


def test_system_class_reads_the_provider_facts():
    L = _ledger(); plan = ledger_plan(L)
    rtu = next(s for s in plan.systems if s.key == "RTU"); ef = next(s for s in plan.systems if s.key == "EF")
    assert system_class(L, rtu) == "packaged"
    assert system_class(L, ef) == "field"


def test_shared_owners_follow_the_links():
    L = _ledger(); plan = ledger_plan(L)
    owners = shared_owners(L, plan)
    assert owners["damper actuator MD-1"] == "EF"


def test_the_brief_has_the_four_parts_in_order_and_fits_the_limit():
    L = _ledger(); plan = ledger_plan(L)
    text = job_brief(L, plan, load_templates())
    i = [text.index(h) for h in ("What the job is", "The systems", "Rules the sequence sets", "Who owns shared items")]
    assert i == sorted(i)
    assert "Two packaged rooftop units serve the corridors" in text
    assert "RTU | Rooftop Unit RTU-1, 2 | Qty 2 | Rooftop Unit | packaged" in text
    assert "EF | Exhaust Fan EF-1 thru 3 | Qty 3 | Exhaust Fan | field | served by: RTU-1" in text
    assert "fire/smoke dampers are controlled by the fire alarm system" in text
    assert "damper actuator MD-1 — EF" in text
    short = job_brief(L, plan, load_templates(), limit=300)
    assert len(short) <= 310 and short.rstrip().endswith("(cut)")
