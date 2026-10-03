"""The ledger becomes the systems the writer takes: one per family or group, the higher count printed with its
note, each system carrying the ids of the facts it rests on."""
from estimator.ledger.facts import SETTLED, Ledger
from estimator.ledger.to_plan import count_note, entry_text, ledger_plan, system_counts
from estimator.writing.whole_job import JobPlan, PlannedSystem

SOURCES = {"S5": "equipment counts for VAV (schedules and plans)", "S6": "equipment counts for CH (schedules and plans)",
           "S7": "equipment counts for CHWP (schedules and plans)", "S10": "M-201, Drawings.pdf page 3 (sheet text)",
           "S13": "23 09 00, Specs.pdf page 4", "Q1": "sequence section “VAV BOXES”, Specs.pdf page 44",
           "Q2": "sequence section “CHILLED WATER PLANT”, Specs.pdf page 50"}


def _ledger():
    ledger = Ledger(SOURCES)
    ledger.add("family", "VAV", "Variable Air Volume Box", "[S5]", "VAV: schedule rows 12", "seed", SETTLED)
    ledger.add("count", "VAV", 12, "[S5]", "QUANTITY column total 12", "seed", SETTLED)
    ledger.add("unit", "VAV", "VAV-1 thru 12", "[S5]", "Tags: VAV-1 thru 12", "seed", SETTLED)
    ledger.add("family", "CH", "Chiller", "[S6]", "CH: schedule rows 2", "seed", SETTLED)
    ledger.add("count", "CH", 2, "[S6]", "schedule rows 2", "seed", SETTLED)
    ledger.add("family", "CHWP", "Chilled Water Pump", "[S7]", "CHWP: schedule rows 2", "seed", SETTLED)
    ledger.add("count", "CHWP", 2, "[S7]", "schedule rows 2", "seed", SETTLED)
    ledger.add("group", "Chilled Water Plant", "CH, CHWP", "[Q2]", "CHILLED WATER PLANT", "risers", SETTLED)
    ledger.add("sequence_match", "VAV BOXES", "VAV", "[Q1]", "VAV BOXES", "sequence", SETTLED)
    ledger.add("sequence_match", "CHILLED WATER PLANT", "Chilled Water Plant", "[Q2]", "CHILLED WATER PLANT", "sequence", SETTLED)
    ledger.add("device", "OCC", 21, "[S10]", "OCC 21 in all", "plans", SETTLED)
    ledger.add("front_end", "mode", "new-system", "[S13]", "provide a new BMS", "spec", SETTLED)
    ledger.add("front_end", "line", "Provide a new Niagara N4 front end", "[S13]", "Niagara N4", "spec", SETTLED)
    ledger.add("note", "question", "Is the existing BMS kept?", "[S13]", "existing BMS", "spec", SETTLED)
    return ledger


def test_families_and_groups_become_systems_in_ledger_order():
    plan = ledger_plan(_ledger())
    assert isinstance(plan, JobPlan) and plan.model == "ledger"
    vav, plant = plan.systems
    assert vav.key == "VAV" and vav.header == "Variable Air Volume Box VAV-1 thru 12" and vav.kind == "Variable Air Volume Box"
    assert vav.tags == tuple(f"VAV-{n}" for n in range(1, 13))
    assert vav.quantity == 12 and vav.quantity_source == "[S5]" and vav.quantity_quote == "QUANTITY column total 12"
    assert vav.sequence_section == "[Q1]" and vav.sequence_sources == ("[Q1]",) and vav.schedule_sources == ("[S5]",)
    assert vav.count_note == "" and "F1" in vav.facts and "F9" in vav.facts
    assert plant.group == "Chilled Water Plant" and plant.key == "Chilled Water Plant" and plant.quantity is None
    assert [f.header for f in plant.families] == ["Chiller CH", "Chilled Water Pump CHWP"]
    assert [f.quantity for f in plant.families] == [2, 2]
    assert plant.sequence_section == "[Q2]"


def test_the_higher_count_is_printed_with_its_note():
    ledger = _ledger()
    ledger.contradict("F2", 14, "[S10]", "VAV-1 … VAV-14", "plans")
    plan = ledger_plan(ledger)
    vav = plan.systems[0]
    assert vav.quantity == 14 and vav.quantity_source == "[S10]" and vav.quantity_quote == "VAV-1 … VAV-14"
    assert vav.count_note == "*Qty. (14) per M-201, Drawings.pdf page 3; equipment counts for VAV lists (12)."
    assert count_note(ledger, ledger.facts["F2"]) == vav.count_note
    assert system_counts(vav, ledger) == frozenset({12, 14})


def test_front_end_and_questions_come_from_the_ledger():
    plan = ledger_plan(_ledger())
    assert plan.front_end == {"mode": "new-system", "existing_name": "", "lines": ["Provide a new Niagara N4 front end"],
                              "notes": [], "sources": ["[S13]"]}
    assert plan.unresolved == ("Is the existing BMS kept?",)


def test_exceptions_alternates_and_unconfirmed_families():
    ledger = _ledger()
    ledger.add("note", "exception", "EXCEPTION TO ANY WORK WITH Qty (12) VAV-1 THRU 12 - INTEGRAL THERMOSTAT", "[Q1]", "integral thermostat", "sequence", SETTLED)
    ledger.add("family", "HPAC", "Apartment Heat Pump", "[S10]", "seen on plans, not scheduled: HPAC", "plans")
    ledger.add("count", "HPAC", 120, "[S10]", "HPAC x120", "plans")
    ledger.add("note", "alternate", "add: HPAC", "[Q1]", "priced per apartment", "sequence", SETTLED)
    plan = ledger_plan(ledger)
    vav, plant, hpac = plan.systems
    assert vav.exception.startswith("EXCEPTION TO ANY WORK WITH Qty (12) VAV-1")
    assert hpac.alternate == "add" and hpac.quantity == 120 and hpac.tags == ("HPAC",)
    assert hpac.why == "Seen on the drawings but on no schedule; confirm it exists."


def test_the_entry_text_lists_the_systems_facts_only():
    ledger = _ledger()
    vav = ledger_plan(ledger).systems[0]
    text = entry_text(vav, ledger)
    assert "F1 family VAV" in text and "F9 sequence_match VAV BOXES" in text
    assert "F4 family CH" not in text


def test_planned_system_defaults_keep_old_callers_working():
    system = PlannedSystem("K", "H", "kind", ("T",), 1, "[S1]", "one", (), (), "", "", "", "why")
    assert system.count_note == "" and system.facts == ()
