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
    assert 2 in system_counts(md, ledger)          # the dampers no fan claims: a count its lines may carry


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


# --- the count notes read as the house writes them ------------------------------------------------------------

COUNTS_QUOTE = ("VAV (Variable Air Volume Box): schedule rows 16; QUANTITY column total —; distinct tags 15; "
                "plan placements 15 (M-101.00 5; M-102.00 10); riser —")


def test_a_counts_line_place_is_the_clause_holding_the_number():
    from estimator.ledger.to_plan import place_words
    where = "equipment counts for VAV (schedules and plans)"
    assert place_words(where, COUNTS_QUOTE, 16) == "schedule rows 16"
    assert place_words(where, COUNTS_QUOTE, 15) == "distinct tags 15"
    assert place_words("M-101.00, Drawings.pdf page 4 (sheet text)", "VAV-1") == "M-101.00"
    assert place_words("M-102.00 SECOND FLOOR PLAN — whole sheet for the Plans pass, Drawings.pdf page 5 (picture)",
                       "VAV-1") == "M-102.00"


def test_a_counts_line_note_names_the_schedule_rows_and_the_other_count():
    ledger = Ledger(SOURCES)
    ledger.add("family", "VAV", "Variable Air Volume Box", "[S5]", COUNTS_QUOTE, "seed", SETTLED)
    count = ledger.add("count", "VAV", 16, "[S5]", COUNTS_QUOTE, "seed", SETTLED)
    ledger.contradict(count.id, 15, "[S5]", "distinct tags 15", "plans")
    assert count_note(ledger, ledger.facts[count.id]) == "*Qty. (16) per schedule rows 16; distinct tags 15."


def test_a_contradicted_group_gives_one_note_per_family():
    ledger = _chillers(grouped=True)
    ledger.contradict(ledger.find("count", "CH").id, 3, "[S10]", "CH-1 CH-2 CH-3", "plans")
    ledger.contradict(ledger.find("count", "CHWP").id, 4, "[S10]", "CHWP-1 … CHWP-4", "plans")
    (plant,) = ledger_plan(ledger).systems
    assert plant.count_note.split("\n") == ["CH: *Qty. (3) per M-201; schedule rows 2.",
                                            "CHWP: *Qty. (4) per M-201; schedule rows 2."]


def test_a_match_valued_with_a_dropped_group_is_asked_about_and_the_split_is_listed():
    ledger = _rtu_and_fan(both_matched=True)
    ledger.add("sequence_match", "CORRIDOR AIR", "corridor air", "[Q1]", "CORRIDOR AIR", "sequence", SETTLED)
    plan = ledger_plan(ledger)
    assert ("Sequence section CORRIDOR AIR matched no system (it named corridor air); which system is it?"
            in plan.unresolved)
    assert "TXF" in plan.dropped[0]


# --- VRF and split systems: a group reads its members with their tags; split units are one block ----------------

from estimator.writing.assemble import system_template

VRF_SOURCES = dict(SOURCES, S20="M-601, Drawings.pdf page 9 (sheet text)", Q5="sequence section “LOBBY SPLIT”, "
                   "Specs.pdf page 60", Q6="sequence section “GYM SPLITS”, Specs.pdf page 61")


def _family_of(ledger, prefix, name, tags, count):
    ledger.add("family", prefix, name, "[S20]", f"{prefix}: schedule", "seed", SETTLED)
    ledger.add("unit", prefix, tags, "[S20]", f"Tags: {tags}", "seed", SETTLED)
    if count is not None:
        ledger.add("count", prefix, count, "[S20]", f"{prefix} x{count}", "seed", SETTLED)


def _vrf(cu_count=6):
    """An invented VRF job: the riser takes four of six condensing units, the branch selector, and two of three
    indoor unit types (their counts on a link); the other units are not on the VRF."""
    ledger = Ledger(VRF_SOURCES)
    _family_of(ledger, "CU", "Condensing Unit", "CU-1 thru 6", cu_count)
    _family_of(ledger, "BS", "Branch Selector", "BS-1", 2)
    _family_of(ledger, "AC", "Variable Refrigerant Flow Ductless Wall Mounted Indoor Unit", "AC-1, AC-2, AC-9", 5)
    group = ledger.add("group", "VRF-A", "CU (CU-1 thru 4), BS (BS-1 x2), AC (AC-1, AC-2)", "[S20]", "VRF-A riser",
                       "risers", SETTLED)
    link = ledger.add("link", "BS-1", "AC-1 x3, AC-2 x1", "[S20]", "BS-1 serves AC-1 x3, AC-2 x1", "plans", SETTLED)
    return ledger, group, link


def test_a_vrf_group_takes_the_listed_parts_of_its_families():
    ledger, group, link = _vrf()
    plan = ledger_plan(ledger)
    vrf, split = plan.systems
    assert vrf.key == "VRF-A" and vrf.group == "VRF-A"
    cu, bs, ac = vrf.families
    assert cu.tags == ("CU-1", "CU-2", "CU-3", "CU-4") and cu.quantity == 4      # unit tags: one unit each
    assert cu.header == "Condensing Unit CU-1 thru 4"
    assert bs.tags == ("BS-1",) and bs.quantity == 2                               # the whole family
    assert ac.tags == ("AC-1", "AC-2") and ac.quantity == 4                        # type tags counted by the link
    assert ac.header == "Indoor Unit AC-1, 2"                 # the template's word for a long description
    assert link.id in vrf.facts and group.id in vrf.facts
    assert not any("CU" in q or "AC" in q for q in plan.unresolved)
    assert split.key == "Split System" and split.group == "Split System"
    rest_cu, rest_ac = split.families
    assert rest_cu.tags == ("CU-5", "CU-6") and rest_cu.quantity == 2
    assert rest_ac.tags == ("AC-9",) and rest_ac.quantity == 1
    assert ledger.find("family", "AC").id in split.facts and ledger.find("family", "AC").id in vrf.facts


def test_type_tags_with_no_stated_count_print_qty_to_fill_and_ask():
    ledger, _, _ = _vrf(cu_count=8)              # eight units over six tags: the tags are types
    plan = ledger_plan(ledger)
    vrf, split = plan.systems
    cu = vrf.families[0]
    assert cu.tags == ("CU-1", "CU-2", "CU-3", "CU-4") and cu.quantity is None
    assert any("CU" in q and "VRF-A" in q and "CU-1 thru 4" in q for q in plan.unresolved)
    assert split.families[0].tags == ("CU-5", "CU-6") and split.families[0].quantity == 8    # never undershoots


def test_a_member_listing_every_tag_or_none_takes_the_whole_family():
    ledger = Ledger(VRF_SOURCES)
    _family_of(ledger, "ODU", "Outdoor Unit", "ODU-1, ODU-2", 2)
    _family_of(ledger, "IDU", "Indoor Unit", "IDU-1 thru 3", 3)
    ledger.add("group", "Heat Pump VRF", "ODU (ODU-1, ODU-2), IDU", "[S20]", "VRF riser", "risers", SETTLED)
    (vrf,) = ledger_plan(ledger).systems
    assert [f.tags for f in vrf.families] == [("ODU-1", "ODU-2"), ("IDU-1", "IDU-2", "IDU-3")]
    assert [f.quantity for f in vrf.families] == [2, 3]


def test_bare_tags_in_a_group_join_their_family():
    ledger = Ledger(VRF_SOURCES)
    _family_of(ledger, "ACCU", "Air Cooled Condensing Unit", "ACCU-1", 1)
    _family_of(ledger, "WAC", "Wall Air Conditioner", "WAC-1.0, WAC-1.5, WAC-2.0", 3)
    ledger.add("group", "VRF-1", "ACCU (ACCU-1), WAC-1.0, WAC-1.5", "[S20]", "VRF riser", "risers", SETTLED)
    vrf, wac = ledger_plan(ledger).systems
    assert vrf.key == "VRF-1" and vrf.families[1].tags == ("WAC-1.0", "WAC-1.5") and vrf.families[1].quantity == 2
    assert wac.key == "WAC" and wac.tags == ("WAC-2.0",) and wac.quantity == 1


def test_split_units_no_group_took_are_one_block_and_a_lone_one_stays_alone():
    ledger = Ledger(VRF_SOURCES)
    _family_of(ledger, "AC", "Ductless Split Indoor Unit", "AC-1, AC-2", 2)
    _family_of(ledger, "EF", "Exhaust Fan", "EF-1", 1)
    _family_of(ledger, "ACCU", "Outdoor Unit", "ACCU-1, ACCU-2", None)        # seen on plans, not scheduled
    split, ef = ledger_plan(ledger).systems
    assert split.key == "Split System" and [f.tags for f in split.families] == [("AC-1", "AC-2"), ("ACCU-1", "ACCU-2")]
    assert ef.key == "EF"
    ledger = Ledger(VRF_SOURCES)
    _family_of(ledger, "CU", "Condensing Unit", "CU-1", 1)
    (cu,) = ledger_plan(ledger).systems
    assert cu.key == "CU" and cu.group == ""


def test_split_units_in_two_sequence_sections_make_two_split_blocks():
    ledger = Ledger(VRF_SOURCES)
    _family_of(ledger, "AC", "Indoor Unit", "AC-LOBBY-1", 1)
    _family_of(ledger, "CU", "Condensing Unit", "CU-LOBBY-1", 1)
    _family_of(ledger, "SS", "Indoor Unit", "SS-GYM-1", 1)
    _family_of(ledger, "ACCU", "Outdoor Unit", "ACCU-GYM-1", 1)
    _family_of(ledger, "OU", "Outdoor Unit", "OU-GYM-1", 1)                    # matched to no section
    ledger.add("sequence_match", "LOBBY SPLIT", "AC", "[Q5]", "LOBBY SPLIT", "sequence", SETTLED)
    ledger.add("sequence_match", "LOBBY SPLIT", "CU", "[Q5]", "LOBBY SPLIT", "sequence", SETTLED)
    ledger.add("sequence_match", "GYM SPLITS", "SS", "[Q6]", "GYM SPLITS", "sequence", SETTLED)
    ledger.add("sequence_match", "GYM SPLITS", "ACCU", "[Q6]", "GYM SPLITS", "sequence", SETTLED)
    plan = ledger_plan(ledger)
    lobby, gym = plan.systems
    assert lobby.key == "Split System — LOBBY SPLIT" and [f.tags[0] for f in lobby.families] == ["AC-LOBBY-1", "CU-LOBBY-1"]
    assert gym.key == "Split System — GYM SPLITS"
    assert [f.tags[0] for f in gym.families] == ["SS-GYM-1", "ACCU-GYM-1", "OU-GYM-1"]    # OU shares "GYM-1"
    assert lobby.sequence_section == "[Q5]" and gym.sequence_section == "[Q6]"
    assert not any("matched no system" in q for q in plan.unresolved)
    assert system_template(lobby).name == system_template(gym).name == "Split System"


def test_the_vrf_group_takes_the_vrf_template_and_the_split_group_the_split_template():
    vrf, split = ledger_plan(_vrf()[0]).systems
    assert system_template(vrf).name == "VRF System" and system_template(split).name == "Split System"
    single = PlannedSystem("ODU", "Acme VRF system ODU-1", "Acme VRF system", ("ODU-1",), 1, "", "", (), (), "", "",
                           "", "why")
    assert system_template(single).name == "VRF System"
    ledger = Ledger(VRF_SOURCES)
    _family_of(ledger, "HRU", "Heat Recovery Unit", "HRU-1", 1)
    _family_of(ledger, "IDU", "Indoor Unit", "IDU-1", 1)
    ledger.add("group", "Heat Pump Plant", "HRU, IDU", "[S20]", "riser", "risers", SETTLED)
    (plant,) = ledger_plan(ledger).systems
    assert system_template(plant).name == "VRF System"


def test_every_count_a_fact_gives_a_tag_is_summed():
    ledger, _, _ = _vrf()
    ledger.add("link", "BS-2", "AC-1 x3; BS-2 serves AC-1 x2", "[S20]", "AC-1 x3; AC-1 x2", "plans", SETTLED)
    vrf = ledger_plan(ledger).systems[0]
    assert vrf.families[2].tags == ("AC-1", "AC-2") and vrf.families[2].quantity == 3 + 1 + 3 + 2


def test_split_units_with_different_alternates_or_exceptions_stay_apart():
    ledger = Ledger(VRF_SOURCES)
    _family_of(ledger, "AC", "Indoor Unit", "AC-1", 1)
    _family_of(ledger, "ACCU", "Outdoor Unit", "ACCU-1", 1)
    ledger.add("note", "alternate", "add: ACCU", "[S20]", "ACCU priced as an add", "spec", SETTLED)
    ac, accu = ledger_plan(ledger).systems
    assert (ac.key, ac.alternate) == ("AC", "") and (accu.key, accu.alternate) == ("ACCU", "add")
    ledger = Ledger(VRF_SOURCES)
    _family_of(ledger, "AC", "Indoor Unit", "AC-1", 1)
    _family_of(ledger, "ACCU", "Outdoor Unit", "ACCU-1", 1)
    ledger.add("note", "exception", "EXCEPTION TO ANY WORK WITH AC-1", "[S20]", "AC-1 by others", "spec", SETTLED)
    ac, accu = ledger_plan(ledger).systems
    assert ac.exception == "EXCEPTION TO ANY WORK WITH AC-1" and accu.exception == "" and accu.group == ""


def test_a_listed_tag_not_the_familys_own_is_ignored_for_the_split():
    ledger = Ledger(VRF_SOURCES)
    _family_of(ledger, "BS", "Branch Selector", "BS-1", 1)
    _family_of(ledger, "AC", "Indoor Unit", "AC-1, AC-9", 2)
    ledger.add("group", "VRF-B", "BS, AC (AC-1, AC-99)", "[S20]", "VRF-B riser", "risers", SETTLED)
    vrf, ac = ledger_plan(ledger).systems
    assert vrf.families[1].tags == ("AC-1",) and vrf.families[1].quantity == 1
    assert ac.key == "AC" and ac.tags == ("AC-9",) and ac.quantity == 1


def test_split_units_sharing_an_alternate_gather_into_their_own_block():
    ledger = Ledger(VRF_SOURCES)
    _family_of(ledger, "AC", "Indoor Unit", "AC-1", 1)
    _family_of(ledger, "ACCU", "Outdoor Unit", "ACCU-1", 1)
    _family_of(ledger, "SS", "Indoor Unit", "SS-1", 1)
    _family_of(ledger, "CU", "Condensing Unit", "CU-1", 1)
    ledger.add("note", "alternate", "add: SS", "[S20]", "SS priced as an add", "spec", SETTLED)
    ledger.add("note", "alternate", "add: CU", "[S20]", "CU priced as an add", "spec", SETTLED)
    base, add = ledger_plan(ledger).systems
    assert base.key == "Split System" and base.alternate == "" and [f.tags for f in base.families] == [("AC-1",), ("ACCU-1",)]
    assert add.key == "Split System (add alternate)" and add.alternate == "add"
    assert [f.tags for f in add.families] == [("SS-1",), ("CU-1",)]
    assert system_template(add).name == "Split System"


# --- the leftovers: short plan-only names, clean quantity notes ------------------------------------------------

def test_a_plan_only_family_value_gives_a_short_header_and_kind():
    ledger = Ledger(SOURCES)
    value = ("seen on plans, not scheduled: Glycol makeup feed skid for the snow melt loop and boiler room "
             "(shown on M-201 with a pump symbol)")
    ledger.add("family", "GLY", value, "[S10]", "GLY", "plans")
    (system,) = ledger_plan(ledger).systems
    assert system.kind == "Glycol makeup feed skid for the snow melt"
    assert "(" not in system.header and "seen on" not in system.header and system.header.startswith(system.kind)
    assert value in system.why
    ledger = Ledger(SOURCES)
    ledger.add("family", "SUMP", "seen on the risers, not scheduled: Sump Pump (drain riser)", "[S10]", "SUMP", "risers")
    (sump,) = ledger_plan(ledger).systems
    assert sump.kind == "Sump Pump"


def test_a_counts_line_quote_is_said_as_plan_placements_without_the_sheet_list():
    from estimator.ledger.to_plan import place_words
    quote = ("VAV (Variable Air Volume Box): schedule rows 15; QUANTITY column total —; distinct tags 15; "
             "plan placements 16 (M-101.00 5; M-102.00 11); riser —")
    where = "equipment counts for VAV (schedules and plans)"
    assert place_words(where, quote, 16) == "plan placements 16"
    assert place_words(where, quote, 15) == "schedule rows 15"


def test_a_damper_block_that_lost_dampers_to_fans_says_so():
    ledger = _ledger()
    ledger.add("family", "MD", "Motorized Damper", "[S10]", "MD", "plans")
    ledger.add("count", "MD", 3, "[S10]", "MD ×3", "plans")
    ledger.add("family", "EF", "Exhaust Fan", "[S10]", "EF-1", "plans")
    ledger.add("count", "EF", 1, "[S10]", "EF-1", "plans")
    ledger.add("link", "MD-1", "EF-1", "[S10]", "MD-1 at EF-1", "plans", SETTLED)
    md = next(s for s in ledger_plan(ledger).systems if s.key == "MD")
    assert md.count_note == "*Qty. (2) not claimed by a fan; (3) per M-201, 1 of them listed under their fans."


def test_a_count_note_never_prints_an_empty_or_unbalanced_bracket():
    ledger = Ledger({"S5": "equipment counts for VAV (schedules and plans)", "S9": ", Drawings.pdf page 3"})
    ledger.add("family", "VAV", "Variable Air Volume Box", "[S9]", "VAV", "seed", SETTLED)
    count = ledger.add("count", "VAV", 14, "[S9]", "VAV x14", "seed", SETTLED)
    quote = ("VAV (Variable Air Volume Box): schedule rows 12; QUANTITY column total —; "
             "plan placements 16 (M-101.00 5; M-102.00 11)")
    ledger.contradict(count.id, 16, "[S5]", quote, "plans")
    note = count_note(ledger, ledger.facts[count.id])
    assert note == "*Qty. (16) per plan placements 16; lists (14)."
    assert "()" not in note and note.count("(") == note.count(")")


def test_other_count_with_no_place_never_prints_a_bare_bracket():
    from estimator.ledger.to_plan import _other_count
    assert _other_count(", Drawings.pdf page 3", "VAV x14", 14) == "lists (14)"


def test_tidy_drops_empty_pairs_and_only_the_offending_bracket():
    from estimator.ledger.to_plan import _tidy
    assert _tidy("*Qty. (14) per ( ); lists ().") == "*Qty. (14) per; lists."
    assert _tidy("*Qty. (14) per M-201 (sheet 3; lists 12.") == "*Qty. (14) per M-201 sheet 3; lists 12."
    assert _tidy("*Qty. (14) per M-201) lists 12.") == "*Qty. (14) per M-201 lists 12."


def test_a_plan_only_name_never_comes_out_empty():
    from estimator.ledger.to_plan import _short_name
    assert _short_name("seen on plans, not scheduled: (pump)") == "pump"
    assert _short_name("seen on plans, not scheduled: ()") == "seen on plans, not scheduled: ()"
    assert _short_name("seen on plans, not scheduled: (a) (b)") == "a"


def test_the_plan_only_lead_needs_no_comma_and_takes_a_dash():
    from estimator.ledger.to_plan import _short_name
    assert _short_name("seen on plans not scheduled: Sump Pump") == "Sump Pump"
    assert _short_name("seen on the risers, not scheduled - Sump Pump (drain)") == "Sump Pump"


def test_a_nested_parenthetical_is_dropped_whole():
    from estimator.ledger.to_plan import _short_name
    assert _short_name("seen on plans, not scheduled: Pump (a (b) c) end") == "Pump end"
