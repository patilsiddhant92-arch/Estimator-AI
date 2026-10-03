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
    assert vav.count_note == "*Qty. (14) per M-201; QUANTITY column total 12."
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


def _chillers(grouped: bool):
    """A CH family and a CHWP family, grouped into the plant or not, with no sequence match of their own."""
    ledger = Ledger(SOURCES)
    ledger.add("family", "CH", "Chiller", "[S6]", "CH: schedule rows 2", "seed", SETTLED)
    ledger.add("count", "CH", 2, "[S6]", "schedule rows 2", "seed", SETTLED)
    ledger.add("family", "CHWP", "Chilled Water Pump", "[S7]", "CHWP: schedule rows 2", "seed", SETTLED)
    ledger.add("count", "CHWP", 2, "[S7]", "schedule rows 2", "seed", SETTLED)
    if grouped:
        ledger.add("group", "Chilled Water Plant", "CH, CHWP", "[Q2]", "CHILLED WATER PLANT", "risers", SETTLED)
    return ledger


def test_an_exception_naming_chwp_does_not_reach_the_chiller_but_reaches_their_plant():
    ledger = _chillers(grouped=False)
    ledger.add("note", "exception", "EXCEPTION TO ANY WORK WITH CHWP-1", "[Q2]", "CHWP-1 by others", "sequence", SETTLED)
    ch, chwp = ledger_plan(ledger).systems
    assert ch.exception == "" and chwp.exception == "EXCEPTION TO ANY WORK WITH CHWP-1"
    ledger = _chillers(grouped=True)
    ledger.add("note", "exception", "EXCEPTION TO ANY WORK WITH CHWP-1", "[Q2]", "CHWP-1 by others", "sequence", SETTLED)
    (plant,) = ledger_plan(ledger).systems
    assert plant.exception == "EXCEPTION TO ANY WORK WITH CHWP-1"


def test_an_alternate_for_chwp_does_not_reach_the_chiller_but_reaches_their_plant():
    ledger = _chillers(grouped=False)
    ledger.add("note", "alternate", "add: CHWP", "[Q2]", "pumps priced as an add", "sequence", SETTLED)
    ch, chwp = ledger_plan(ledger).systems
    assert ch.alternate == "" and chwp.alternate == "add"
    ledger = _chillers(grouped=True)
    ledger.add("note", "alternate", "add: CHWP", "[Q2]", "pumps priced as an add", "sequence", SETTLED)
    (plant,) = ledger_plan(ledger).systems
    assert plant.alternate == "add"


def test_a_sequence_match_for_a_member_prefix_reaches_the_group():
    ledger = _chillers(grouped=True)
    match = ledger.add("sequence_match", "PUMPS", "CHWP", "[Q2]", "CHILLED WATER PUMPS", "sequence", SETTLED)
    (plant,) = ledger_plan(ledger).systems
    assert plant.sequence_section == "[Q2]" and plant.sequence_sources == ("[Q2]",)
    assert match.id in plant.facts


def test_a_highest_count_stored_as_text_with_spaces_still_plans():
    ledger = Ledger(SOURCES)
    ledger.add("family", "VAV", "Variable Air Volume Box", "[S5]", "VAV: schedule rows 14", "seed", SETTLED)
    count = ledger.add("count", "VAV", " 14", "[S5]", "QUANTITY column total 14", "seed", SETTLED)
    ledger.contradict(count.id, 12, "[S10]", "VAV-1 … VAV-12", "plans")
    (vav,) = ledger_plan(ledger).systems
    assert vav.quantity == 14 and vav.quantity_source == "[S5]" and vav.quantity_quote == "QUANTITY column total 14"
    assert vav.count_note == "*Qty. (14) per QUANTITY column total 14; M-201 lists (12)."


# --- from the seed, through the passes, to the plan ---------------------------------------------------------

from estimator.ledger.facts import ADDED
from estimator.ledger.passes import apply, pass_named
from estimator.ledger.seed import seed
from tests.test_ledger_seed import _dossier


def _read(*answers):
    """The seed of the test job, then each (pass name, facts) answer applied in turn."""
    ledger = seed(_dossier())
    for name, facts in answers:
        known = frozenset(ledger.sources) | frozenset(ledger.facts)
        assert apply(pass_named(name), ledger, {"facts": facts, "contradictions": [], "confirmations": [],
                                                "understanding": "ok"}, known) == []
    return ledger


def _by_key(plan):
    return {s.key: s for s in plan.systems}


def test_the_sequence_pass_answer_lands_on_the_systems_sequence_section():
    ledger = _read(("sequence", [{"kind": "sequence_match", "subject": "VAV BOXES", "value": "VAV", "source_id": "[Q1]",
                                  "quote": "VAV BOXES"}]))
    vav = _by_key(ledger_plan(ledger))["VAV"]
    assert vav.sequence_section == "[Q1]" and vav.sequence_sources == ("[Q1]",)


def test_the_schedules_pass_name_is_the_planned_header():
    ledger = _read(("schedules", [{"kind": "family", "subject": "EF", "value": "Toilet Exhaust Fan", "source_id": "[S4]",
                                   "quote": "TOILET EXHAUST FAN"}]))
    ef = _by_key(ledger_plan(ledger))["EF"]
    assert ef.header == "Toilet Exhaust Fan EF-1, EF-2" and ef.kind == "Toilet Exhaust Fan"


def test_two_questions_and_two_front_end_lines_all_reach_the_plan():
    ledger = _read(("spec", [
        {"kind": "note", "subject": "question", "value": "Is the existing BMS kept?", "source_id": "[S13]", "quote": "existing BMS"},
        {"kind": "note", "subject": "question", "value": "Who provides the VFDs?", "source_id": "[S13]", "quote": "VFDs"},
        {"kind": "front_end", "subject": "line", "value": "Provide a new Niagara N4 front end", "source_id": "[S13]", "quote": "Niagara N4"},
        {"kind": "front_end", "subject": "line", "value": "Provide one workstation", "source_id": "[S13]", "quote": "workstation"}]))
    assert len(ledger.of_kind("note")) + len(ledger.of_kind("front_end")) == 4
    plan = ledger_plan(ledger)
    assert plan.unresolved == ("Is the existing BMS kept?", "Who provides the VFDs?",          # then the sections
                               "Sequence section VAV BOXES matched no system; which system is it?",   # no pass matched
                               "Sequence section EXHAUST FANS matched no system; which system is it?")
    assert plan.front_end["lines"] == ["Provide a new Niagara N4 front end", "Provide one workstation"]


def test_a_corrected_count_prints_the_higher_of_the_pass_and_the_seed():
    ledger = _read(("schedules", [{"kind": "count", "subject": "EF", "value": 3, "source_id": "[S4]", "quote": "EF-1, EF-2, EF-3"}]))
    ef = _by_key(ledger_plan(ledger))["EF"]
    assert ef.quantity == 3 and ef.quantity_source == "[S4]" and "(2)" in ef.count_note
    ledger = _read(("schedules", [{"kind": "count", "subject": "EF", "value": 1, "source_id": "[S4]", "quote": "EF-1"}]))
    ef = _by_key(ledger_plan(ledger))["EF"]
    assert ef.quantity == 2 and ef.quantity_source == "[S6]" and "(1)" in ef.count_note


def test_why_a_family_is_flagged_follows_its_count_not_its_name():
    ledger = seed(_dossier())
    assert ledger.find("family", "VAV").state == ADDED
    plan = _by_key(ledger_plan(ledger))
    assert plan["VAV"].why.startswith("From the job ledger")          # a settled schedule count
    assert plan["EF"].why == "Seen on the drawings but on no schedule; confirm it exists."     # a plan count only
    assert plan["T"].why == "Seen on the drawings but on no schedule; confirm it exists."      # no count at all
    ledger.add("family", "OAF", "Outdoor Air Fan", "[Q2]", "OUTDOOR AIR FAN", "sequence")
    assert _by_key(ledger_plan(ledger))["OAF"].why == "Named in the sequence of operation; no drawing shows it."


def test_the_count_note_names_the_place_in_plain_words():
    ledger = _ledger()
    ledger.contradict("F2", 14, "[S10]", "VAV-1 … VAV-14", "plans")
    # S10 is "M-201, Drawings.pdf page 3 (sheet text)": the sheet number only; F2's own source is the counts line,
    # so its quote's words stand in for the place
    assert count_note(ledger, ledger.facts["F2"]) == "*Qty. (14) per M-201; QUANTITY column total 12."


def test_a_damper_linked_to_a_fan_joins_the_fan_and_leaves_the_damper_block():
    ledger = _ledger()
    ledger.add("family", "MD", "Motorized Damper", "[S10]", "MD", "plans")
    ledger.add("count", "MD", 3, "[S10]", "MD ×3", "plans")
    ledger.add("family", "EF", "Exhaust Fan", "[S10]", "EF-1", "plans")
    ledger.add("count", "EF", 1, "[S10]", "EF-1", "plans")
    ledger.add("link", "MD-1", "EF-1", "[S10]", "MD-1 at EF-1", "plans", SETTLED)
    plan = ledger_plan(ledger)
    ef = next(s for s in plan.systems if s.key == "EF")
    md = next(s for s in plan.systems if s.key == "MD")
    assert ef.linked_dampers == 1 and any(ledger.facts[f].kind == "link" for f in ef.facts)
    assert md.quantity == 2 and "no fan claims" in md.why
    assert 1 in system_counts(ef, ledger)


def test_when_every_damper_is_linked_there_is_no_damper_block():
    ledger = _ledger()
    ledger.add("family", "MD", "Motorized Damper", "[S10]", "MD", "plans")
    ledger.add("count", "MD", 1, "[S10]", "MD ×1", "plans")
    ledger.add("family", "EF", "Exhaust Fan", "[S10]", "EF-1", "plans")
    ledger.add("count", "EF", 1, "[S10]", "EF-1", "plans")
    ledger.add("link", "MD-1", "EF-1", "[S10]", "MD-1 at EF-1", "plans", SETTLED)
    assert [s.key for s in ledger_plan(ledger).systems if s.key == "MD"] == []


# --- groups are plants; a section that matched nothing is asked ----------------------------------------------

def _rtu_and_fan(both_matched: bool):
    ledger = Ledger(SOURCES)
    ledger.add("family", "RTU", "Rooftop Unit", "[S5]", "RTU: schedule rows 2", "seed", SETTLED)
    ledger.add("count", "RTU", 2, "[S5]", "schedule rows 2", "seed", SETTLED)
    ledger.add("family", "TXF", "Toilet Exhaust Fan", "[S6]", "TXF: schedule rows 3", "seed", SETTLED)
    ledger.add("count", "TXF", 3, "[S6]", "schedule rows 3", "seed", SETTLED)
    ledger.add("group", "corridor air", "RTU, TXF", "[S10]", "CS 1 TX 1", "risers", SETTLED)
    ledger.add("sequence_match", "ROOFTOP UNITS", "RTU", "[Q1]", "ROOFTOP UNITS", "sequence", SETTLED)
    if both_matched:
        ledger.add("sequence_match", "TOILET EXHAUST FANS", "TXF", "[Q2]", "TOILET EXHAUST FANS", "sequence", SETTLED)
    return ledger


def test_a_group_whose_families_match_two_sections_is_dropped_and_they_stand_alone():
    plan = ledger_plan(_rtu_and_fan(both_matched=True))
    assert [s.key for s in plan.systems] == ["RTU", "TXF"]
    assert all(s.group == "" for s in plan.systems)
    assert plan.systems[0].sequence_section == "[Q1]" and plan.systems[1].sequence_section == "[Q2]"
    assert len(plan.dropped) == 1 and "corridor air" in plan.dropped[0] and "RTU" in plan.dropped[0]
    assert "TXF" in plan.dropped[0]


def test_a_group_with_one_matched_family_is_kept():
    plan = ledger_plan(_rtu_and_fan(both_matched=False))
    assert [s.key for s in plan.systems] == ["corridor air"] and plan.dropped == ()


def test_a_damper_linked_to_a_fan_inside_a_group_joins_the_group():
    ledger = _ledger()
    ledger.add("family", "MD", "Motorized Damper", "[S10]", "MD", "plans")
    ledger.add("count", "MD", 2, "[S10]", "MD x2", "plans")
    ledger.add("family", "EF", "Exhaust Fan", "[S10]", "EF-1", "plans")
    ledger.add("count", "EF", 1, "[S10]", "EF-1", "plans")
    ledger.add("unit", "EF", "EF-1", "[S10]", "EF-1", "plans")
    ledger.add("group", "Garage Exhaust", "EF", "[S10]", "GARAGE EXHAUST", "risers", SETTLED)
    link = ledger.add("link", "MD on garage exhaust duct", "EF-1", "[S10]", "MD EF-1", "plans", SETTLED)
    plan = ledger_plan(ledger)
    garage = next(s for s in plan.systems if s.key == "Garage Exhaust")
    md = next(s for s in plan.systems if s.key == "MD")
    assert garage.linked_dampers == 1 and link.id in garage.facts
    assert md.quantity == 1


def test_a_damper_family_inside_a_group_gives_up_the_dampers_a_fan_claims():
    ledger = _ledger()
    ledger.add("family", "EF", "Exhaust Fan", "[S10]", "EF-1", "plans")
    ledger.add("count", "EF", 1, "[S10]", "EF-1", "plans")
    ledger.add("unit", "EF", "EF-1", "[S10]", "EF-1", "plans")
    ledger.add("family", "MD", "Motorized Damper", "[S10]", "MD", "plans")
    ledger.add("count", "MD", 1, "[S10]", "MD x1", "plans")
    ledger.add("group", "Shaft Ventilation", "EF, MD", "[S10]", "SHAFT VENTILATION", "risers", SETTLED)
    ledger.add("link", "MD-1", "EF-1", "[S10]", "MD-1 EF-1", "plans", SETTLED)
    (shaft,) = [s for s in ledger_plan(ledger).systems if s.key == "Shaft Ventilation"]
    assert shaft.linked_dampers == 1
    assert [f.header for f in shaft.families] == ["Exhaust Fan EF-1"]       # the one damper is the fan's


def test_a_sequence_section_that_matched_nothing_is_asked():
    ledger = _read(("sequence", [{"kind": "sequence_match", "subject": "VAV BOXES", "value": "VAV", "source_id": "[Q1]",
                                  "quote": "VAV BOXES"}]))
    plan = ledger_plan(ledger)
    assert plan.unresolved == ("Sequence section EXHAUST FANS matched no system; which system is it?",)


def test_a_damper_is_told_from_a_fire_or_smoke_damper_by_its_tag_and_phrases_not_bare_words():
    from estimator.ledger.to_plan import _is_motorized_damper
    assert _is_motorized_damper("MD on 88x40 smoke purge duct", ("MD",))
    assert _is_motorized_damper("motorized damper at the fire pump room louver", ("MD",))
    assert not _is_motorized_damper("FSD-1", ("MD",))
    assert not _is_motorized_damper("combination fire/smoke damper", ("MD",))
    assert not _is_motorized_damper("SD at the corridor", ("MD",))
