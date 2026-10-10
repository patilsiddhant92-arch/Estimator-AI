"""The planner: the ledger becomes the Job skeleton. Every ledger here is invented."""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from estimator.ledger.facts import SETTLED, Ledger
from estimator.writing.dossier import Dossier

from bms.model import Count, Job, OtherCount, Ref
from bms.plan import plan_job
from bms.plan_read import short_name
from bms.playbook import Shape, TechHours, load_playbook

PLAYBOOK = load_playbook(Path(__file__).parent / "fixtures" / "sample_playbook")

SOURCES = {
    "S1": "equipment counts for FAN (schedules and plans)",
    "S2": "M-101, Drawings.pdf page 2 (sheet text)",
    "S3": "M-501, Drawings.pdf page 6 (schedule)",
    "S4": "23 09 00, Specs.pdf page 4",
    "S5": "M-601, Drawings.pdf page 9 (sheet text)",
    "Q1": "sequence section “EXHAUST FANS”, Specs.pdf page 40",
    "Q2": "sequence section “HEATING PLANT”, Specs.pdf page 41",
    "Q3": "sequence section “NORTH SPLITS”, Specs.pdf page 42",
    "Q4": "sequence section “SOUTH SPLITS”, Specs.pdf page 43",
    "Q5": "sequence section “ROOFTOP UNITS”, Specs.pdf page 44",
}


def _dossier() -> Dossier:
    return Dossier(job_name="Invented Job", text="", images=(), sources={"D9": "A-100, Drawings.pdf page 1 (sheet)"},
                   families=(), device_totals={}, counts={}, stats={})


def _plan(ledger: Ledger, playbook=PLAYBOOK) -> Job:
    return plan_job(ledger, None, _dossier(), playbook)


def _family(ledger, prefix, name, tags=None, count=None, source="S3", state=SETTLED, stage="schedules"):
    ledger.add("family", prefix, name, source, f"{prefix} {name}", stage, state)
    if tags:
        ledger.add("unit", prefix, tags, source, f"Tags: {tags}", stage, state)
    if count is not None:
        return ledger.add("count", prefix, count, source, f"{prefix} rows {count}", stage, state)
    return None


def _ledger() -> Ledger:
    ledger = Ledger(SOURCES)
    ledger.job_name = "Invented Job"
    ledger.add("front_end", "mode", "new-system", "S4", "provide a new building automation system", "spec", SETTLED)
    return ledger


def _by_key(job: Job) -> dict:
    return {s.key: s for s in job.systems}


# ---- the basics ---------------------------------------------------------------------------------------------------

def test_one_system_per_family_with_shape_count_and_sequence():
    ledger = _ledger()
    _family(ledger, "EF", "Exhaust Fan", "EF-1 thru 3", 3)
    match = ledger.add("sequence_match", "EXHAUST FANS", "EF", "Q1", "EXHAUST FANS", "sequence", SETTLED)
    job = _plan(ledger)
    (ef,) = job.systems
    assert job.name == "Invented Job" and job.header is None
    assert (ef.key, ef.name, ef.shape, ef.control, ef.alternate) == ("EF", "Exhaust Fan", "Exhaust Fan", "field", "base")
    (family,) = ef.families
    assert family.name == "Exhaust Fan" and family.tags == ("EF-1", "EF-2", "EF-3")
    assert family.count == Count(3, (Ref("S3", "EF rows 3", "M-501, Drawings.pdf page 6"),))
    assert ef.sequence_refs == (Ref("Q1", "EXHAUST FANS", "sequence section “EXHAUST FANS”, Specs.pdf page 40"),)
    assert ef.devices == () and ef.clarifications == () and ef.tech_hours is None
    assert job.questions == ()
    assert match.id
    assert Job.from_dict(job.to_dict()) == job


def test_an_unknown_kind_has_no_shape():
    ledger = _ledger()
    _family(ledger, "GLY", "Glycol Feeder", "GLY-1", 1)
    (gly,) = _plan(ledger).systems
    assert gly.shape == ""


def test_the_higher_count_prints_and_every_other_count_is_kept_with_its_source():
    ledger = _ledger()
    count = _family(ledger, "EF", "Exhaust Fan", "EF-1 thru 3", 3)
    ledger.contradict(count.id, 4, "S2", "EF-1 EF-2 EF-3 EF-4", "plans")
    ledger.contradict(count.id, 2, "S5", "EF x2", "risers")
    (ef,) = _plan(ledger).systems
    family = ef.families[0]
    assert family.count.value == 4
    assert family.count.sources == (Ref("S2", "EF-1 EF-2 EF-3 EF-4", "M-101, Drawings.pdf page 2"),)
    assert family.count.others == (OtherCount(3, Ref("S3", "EF rows 3", "M-501, Drawings.pdf page 6")),
                                   OtherCount(2, Ref("S5", "EF x2", "M-601, Drawings.pdf page 9")))
    assert family.count.highest() == 4


def test_a_zero_count_with_tags_is_not_printed_as_zero():
    ledger = _ledger()
    _family(ledger, "EF", "Exhaust Fan", "EF-1, EF-2", 0)
    job = _plan(ledger)
    value = job.systems[0].families[0].count.value
    assert value is None or value >= 2
    assert any("gives 0 for EF" in q and "EF-1" in q for q in job.questions)


def test_a_count_given_as_text_still_counts():
    ledger = _ledger()
    count = _family(ledger, "EF", "Exhaust Fan", "EF-1", " 5")
    ledger.contradict(count.id, 2, "S2", "EF x2", "plans")
    assert _plan(ledger).systems[0].families[0].count.value == 5


def test_a_ref_through_the_dossier_and_a_fact_id_finds_its_place():
    ledger = Ledger(dict(SOURCES))
    ledger.add("front_end", "mode", "new-system", "S4", "new system", "spec", SETTLED)
    first = ledger.add("family", "EF", "Exhaust Fan", "S2", "EF", "plans", SETTLED)
    ledger.add("count", "EF", 1, first.id, "EF-1 per F1", "plans", SETTLED)
    (ef,) = _plan(ledger).systems
    assert ef.families[0].count.sources[0] == Ref(first.id, "EF-1 per F1", "M-101, Drawings.pdf page 2")


def test_front_end_questions_and_alternates_come_from_the_ledger():
    ledger = _ledger()
    ledger.add("front_end", "existing_name", "Acme Net", "S4", "existing Acme Net", "spec", SETTLED)
    _family(ledger, "EF", "Exhaust Fan", "EF-1", 1)
    _family(ledger, "UH", "Unit Heater", "UH-1", 1)
    ledger.add("note", "question", "Is the lobby fan kept?", "S4", "lobby fan", "spec", SETTLED)
    ledger.add("note", "alternate", "add: UH", "S4", "unit heaters as an add", "spec", SETTLED)
    ledger.add("note", "alternate", "deduct: EF-1", "S4", "fan as a deduct", "spec", SETTLED)
    job = _plan(ledger)
    assert job.front_end.mode == "new-system" and job.front_end.existing_system_name is None
    assert job.questions == ("Is the lobby fan kept?",)
    systems = _by_key(job)
    assert systems["UH"].alternate == "add" and systems["EF"].alternate == "deduct"


def test_an_existing_system_is_named_and_a_missing_mode_is_asked():
    ledger = Ledger(SOURCES)
    ledger.add("front_end", "mode", "extend-existing", "S4", "extend the existing BMS", "spec", SETTLED)
    ledger.add("front_end", "existing_name", "Acme Net", "S4", "existing Acme Net", "spec", SETTLED)
    job = _plan(ledger)
    assert job.front_end.mode == "extend-existing" and job.front_end.existing_system_name == "Acme Net"
    job = _plan(Ledger(SOURCES))
    assert job.front_end.mode == "new-system"
    assert any("new or extends an existing" in q for q in job.questions)


def test_exceptions_name_their_system_and_keep_their_source():
    ledger = _ledger()
    _family(ledger, "CH", "Chiller", "CH-1", 1)
    _family(ledger, "CHWP", "Chilled Water Pump", "CHWP-1", 1)
    ledger.add("note", "exception", "Exception to any work with CHWP-1 (by others)", "S4", "CHWP-1 by others",
               "spec", SETTLED)
    ledger.add("note", "exception", "Fire alarm by others", "S4", "fire alarm by others", "spec", SETTLED)
    job = _plan(ledger)
    first, second = job.exceptions
    assert first.system_key == "CHWP" and first.text == "Exception to any work with CHWP-1 (by others)"
    assert first.refs == (Ref("S4", "CHWP-1 by others", "23 09 00, Specs.pdf page 4"),)
    assert second.system_key == ""
    assert [s.key for s in job.systems] == ["CH", "CHWP"]          # the system stays; never undershoot


def test_an_exception_loses_the_ledgers_bracket_form_of_an_id_at_plan_time():
    """The ledger's own "[S4]" form is a known format, taken out by the planner; any other id-shaped token is left
    for the validator to report (never a sentence rewrite)."""
    ledger = _ledger()
    _family(ledger, "CH", "Chiller", "CH-1", 1)
    ledger.add("note", "exception", "Fire alarm by others [S4] per [q12]", "S4", "fire alarm by others", "spec",
               SETTLED)
    ledger.add("note", "exception", "Sprinklers by others per S4", "S4", "sprinklers by others", "spec", SETTLED)
    ledger.add("note", "exception", "[S4]", "S4", "x", "spec", SETTLED)
    job = _plan(ledger)
    assert [x.text for x in job.exceptions] == ["Fire alarm by others per", "Sprinklers by others per S4"]


def test_control_class_from_the_provider_facts():
    ledger = _ledger()
    _family(ledger, "RTU", "Rooftop Unit", "RTU-1, RTU-2", 2)
    _family(ledger, "EF", "Exhaust Fan", "EF-1", 1)
    _family(ledger, "BLR", "Boiler", "BLR-1", 1)
    _family(ledger, "FP", "Fire Pump", "FP-1", 1)
    _family(ledger, "CRU", "Condensing Rack", "CRU-1", 1)
    ledger.add("provider", "RTU", "factory controls by the unit manufacturer", "S4", "factory controls", "spec", SETTLED)
    ledger.add("provider", "EF-1", "controls not by the unit mfr", "S4", "not by the unit mfr", "spec", SETTLED)
    ledger.add("provider", "BLR", "BMS to integrate over BACnet", "S4", "BACnet", "spec", SETTLED)
    ledger.add("provider", "FP", "not in contract", "S4", "N.I.C.", "spec", SETTLED)
    systems = _by_key(_plan(ledger))
    assert systems["RTU"].control == "packaged" and systems["RTU"].shape == "Rooftop Unit"
    assert systems["EF"].control == "field"
    assert systems["BLR"].control == "integration"
    assert systems["FP"].control == "none"
    assert systems["CRU"].control == "field"


# ---- names ----------------------------------------------------------------------------------------------------------

def test_short_names_drop_the_plan_only_lead_and_brackets():
    assert short_name("seen on plans, not scheduled: Glycol feed skid for the snow melt loop and boiler room "
                      "(pump symbol)") == "Glycol feed skid for the snow melt loop"
    assert short_name("seen on the risers, not scheduled - Sump Pump (drain)") == "Sump Pump"
    assert short_name("seen on plans not scheduled: Sump Pump") == "Sump Pump"
    assert short_name("seen on plans, not scheduled: Pump (a (b) c) end") == "Pump end"
    assert short_name("seen on plans, not scheduled: (pump)") == "pump"
    assert short_name("seen on plans, not scheduled: ()") == "seen on plans, not scheduled: ()"
    assert short_name("", "GLY") == "GLY"
    assert short_name("Exhaust  Fan (roof)") == "Exhaust Fan (roof)"


def test_a_plan_only_family_has_a_short_name_and_an_existence_question():
    ledger = _ledger()
    ledger.add("family", "SP", "seen on plans, not scheduled: Sump Pump (drain riser)", "S2", "SP", "plans")
    ledger.add("count", "SP", 2, "S2", "SP x2", "plans")
    job = _plan(ledger)
    (sp,) = job.systems
    assert sp.name == "Sump Pump" and sp.families[0].name == "Sump Pump" and sp.families[0].count.value == 2
    assert job.questions == ("Sump Pump (SP) is seen on the drawings but on no schedule; confirm it exists "
                             "(it is in the Sump Pump block).",)


def test_a_sequence_only_family_has_no_count_and_asks_how_many():
    ledger = _ledger()
    ledger.add("family", "CUH", "Cabinet Unit Heater", "Q2", "cabinet unit heaters shall cycle", "sequence", SETTLED)
    ledger.add("sequence_match", "HEATING PLANT", "CUH", "Q2", "HEATING PLANT", "sequence", SETTLED)
    job = _plan(ledger)
    (cuh,) = job.systems
    assert cuh.families[0].count == Count(None) and cuh.families[0].tags == ()
    assert cuh.shape == "Unit Heater" and len(cuh.sequence_refs) == 1
    assert len(job.questions) == 1 and "sequence of operation" in job.questions[0] and "Qty (##)" in job.questions[0]


# ---- sequence sections --------------------------------------------------------------------------------------------

def test_a_sequence_section_that_matched_no_system_is_asked():
    ledger = _ledger()
    _family(ledger, "EF", "Exhaust Fan", "EF-1", 1)
    ledger.add("sequence_match", "EXHAUST FANS", "EF", "Q1", "EXHAUST FANS", "sequence", SETTLED)
    ledger.add("sequence_match", "HEATING PLANT", "", "Q2", "HEATING PLANT", "seed")
    ledger.add("sequence_match", "ROOFTOP UNITS", "RTU", "Q5", "ROOFTOP UNITS", "sequence", SETTLED)
    ledger.add("sequence_match", "B. BACnet object list", "", "Q3", "B. BACnet object list", "seed")
    job = _plan(ledger)
    assert job.questions == (
        "Sequence section ROOFTOP UNITS matched no system (it named RTU); which system is it?",
        "These sequence sections describe no equipment of their own, so no block was written for them: "
        "HEATING PLANT; B. BACnet object list. Confirm none of them needs a block of its own.")


def test_an_unmatched_section_sharing_a_heading_with_a_matched_one_is_still_asked():
    ledger = _ledger()
    _family(ledger, "EF", "Exhaust Fan", "EF-1", 1)
    ledger.add("sequence_match", "1. OCCUPIED MODE", "EF", "Q1", "1. OCCUPIED MODE", "sequence", SETTLED)
    ledger.add("sequence_match", "1. OCCUPIED MODE", "RTU", "Q5", "1. OCCUPIED MODE", "sequence", SETTLED)
    job = _plan(ledger)
    assert job.questions == (
        "Sequence section 1. OCCUPIED MODE matched no system (it named RTU); which system is it?",)


def test_a_global_points_section_becomes_a_global_points_system():
    ledger = _ledger()
    _family(ledger, "EF", "Exhaust Fan", "EF-1", 1)
    ledger.add("sequence_match", "EXHAUST FANS", "EF", "Q1", "EXHAUST FANS", "sequence", SETTLED)
    ledger.add("sequence_match", "1.2 Global system points", "", "Q2", "1.2 Global system points", "seed")
    ledger.add("sequence_match", "A. General", "", "Q3", "A. General", "seed")
    job = _plan(ledger)
    ef, points = job.systems
    assert (points.key, points.name, points.control) == ("Global Points", "Global Points", "integration")
    assert points.sequence_refs == (Ref("Q2", "1.2 Global system points",
                                        "sequence section “HEATING PLANT”, Specs.pdf page 41"),)
    (family,) = points.families
    assert family.name == "Global Points" and family.count.value == 1
    assert not any("Global" in q for q in job.questions)
    assert job.questions == ("These sequence sections describe no equipment of their own, so no block was written "
                             "for them: A. General. Confirm none of them needs a block of its own.",)


# ---- nothing is ever dropped ------------------------------------------------------------------------------------------

def _tags_in(job: Job) -> set[str]:
    return {t.upper() for s in job.systems for f in s.families for t in f.tags}


def test_plan_only_units_of_a_split_family_and_a_vrf_group_lose_no_tag():
    ledger = _vrf()
    # the plans pass records units seen on the plans but on no schedule, as one unit fact and its contradictions
    seen = ledger.add("unit", "seen on plans, not scheduled", "CU-ELEC-R", "S2", "CU-ELEC-R", "plans")
    ledger.contradict(seen.id, "AC-ELEC-R", "S5", "AC-ELEC-R ELEC ROOM", "plans")
    ledger.contradict(seen.id, "CU-LAUNDRY", "S2", "CU-LAUNDRY", "plans")
    ledger.contradict(seen.id, "ZZ-1, ZZ-2 (circled tags at the shaft)", "S2", "ZZ-1 ZZ-2", "plans")
    job = _plan(ledger)
    every = ["CU-1", "CU-2", "CU-3", "CU-4", "CU-5", "CU-6", "BS-1", "AC-1", "AC-2", "AC-9",
             "CU-ELEC-R", "AC-ELEC-R", "CU-LAUNDRY"]
    assert set(every) <= _tags_in(job)
    split = _by_key(job)["Split System"]
    seen_cu = [f for f in split.families if "CU-ELEC-R" in f.tags]
    assert seen_cu and seen_cu[0].tags == ("CU-ELEC-R", "CU-LAUNDRY") and seen_cu[0].count.value == 2
    assert any("CU-ELEC-R" in q and "no schedule" in q for q in job.questions)
    assert any("ZZ-1" in q and "ZZ-2" in q for q in job.questions)          # no family owns them: asked, not lost


def test_every_family_and_tag_of_the_ledger_is_in_a_system_or_a_question():
    ledger = _vrf()
    _family(ledger, "MD", "Motorized Damper", "MD-1, MD-2", 2)
    _family(ledger, "EF", "Exhaust Fan", "EF-1", 1)
    ledger.add("link", "MD (roof)", "EF-1", "S2", "MD EF-1", "plans", SETTLED)
    ledger.add("link", "MD (shaft)", "EF-1", "S2", "MD EF-1 shaft", "plans", SETTLED)
    job = _plan(ledger)
    text = " ".join(job.questions)
    for fact in ledger.of_kind("unit"):
        from bms.plan_read import expand
        for tag in expand([fact.value]):
            assert tag.upper() in _tags_in(job) or tag in text, tag


def test_an_emergency_generator_on_the_plans_and_in_the_sequence_is_one_system():
    ledger = _ledger()
    ledger.add("family", "GEN", "seen on plans, not scheduled: Emergency Generator (roof)", "S2", "GEN-1", "plans")
    ledger.add("unit", "GEN", "GEN-1", "S2", "GEN-1", "plans")
    ledger.add("family", "GEN", "Emergency generator", "Q2", "the emergency generator shall", "sequence")
    ledger.add("sequence_match", "A. Emergency generator", "GEN", "Q2", "A. Emergency generator", "sequence",
               SETTLED)
    job = _plan(ledger)
    (gen,) = job.systems
    assert gen.families[0].tags == ("GEN-1",) and len(gen.sequence_refs) == 1


# ---- specific names for generic kinds ---------------------------------------------------------------------------------

def test_a_generic_fan_takes_its_sequence_sections_words():
    ledger = _ledger()
    _family(ledger, "RXF", "Fan", "RXF-R-1", 1)
    ledger.add("sequence_match", "F. Refuse room exhaust fans", "RXF", "Q1", "F. Refuse room exhaust fans",
               "sequence", SETTLED)
    (rxf,) = _plan(ledger).systems
    assert rxf.name == "Refuse Room Exhaust Fan" and rxf.families[0].name == "Refuse Room Exhaust Fan"


def test_a_long_section_title_is_cut_at_its_first_joint_and_to_six_words():
    ledger = _ledger()
    _family(ledger, "GXF", "Fan", "GXF-C-1", 1)
    ledger.add("sequence_match", "I. Parking Garage Fans and Associated CO Control System", "GXF", "Q1", "I.",
               "sequence", SETTLED)
    assert _plan(ledger).systems[0].name == "Parking Garage Fan"


def test_a_generic_fan_with_no_section_takes_its_location():
    ledger = _ledger()
    _family(ledger, "GCF", "Fan", "GCF-A", 1)
    ledger.add("location", "GCF-A", "cellar parking garage (M-100)", "S2", "GARAGE DUCT UP GCF-A", "plans", SETTLED)
    assert _plan(ledger).systems[0].name == "Cellar Parking Garage Fan"


def test_a_generic_kind_with_nothing_specific_keeps_its_kind_and_a_specific_kind_is_kept():
    ledger = _ledger()
    _family(ledger, "ZF", "Fan", "ZF-1", 1)
    _family(ledger, "EF", "Exhaust Fan", "EF-1", 1)
    ledger.add("sequence_match", "HEATING PLANT", "EF", "Q2", "HEATING PLANT", "sequence", SETTLED)
    zf, ef = _plan(ledger).systems
    assert zf.name == "Fan" and ef.name == "Exhaust Fan"


# ---- groups ---------------------------------------------------------------------------------------------------

def test_a_group_is_one_system_with_its_families_and_member_sequence():
    ledger = _ledger()
    _family(ledger, "B", "Boiler", "B-1, B-2", 2)
    _family(ledger, "HWP", "Hot Water Pump", "HWP-1, HWP-2", 2)
    _family(ledger, "EF", "Exhaust Fan", "EF-1", 1)
    ledger.add("group", "Heating Plant", "B, HWP", "S5", "HEATING PLANT riser", "risers", SETTLED)
    ledger.add("sequence_match", "HEATING PLANT", "HWP", "Q2", "HEATING PLANT", "sequence", SETTLED)
    ledger.add("note", "alternate", "add: HWP", "S4", "pumps as an add", "spec", SETTLED)
    job = _plan(ledger)
    plant, ef = job.systems
    assert plant.key == "Heating Plant" and plant.name == "Heating Plant"
    assert [(f.name, f.tags, f.count.value) for f in plant.families] == [("Boiler", ("B-1", "B-2"), 2),
                                                                         ("Hot Water Pump", ("HWP-1", "HWP-2"), 2)]
    assert plant.alternate == "add" and len(plant.sequence_refs) == 1
    assert ef.key == "EF" and job.questions == ()


def test_a_group_whose_families_match_their_own_sections_is_not_kept():
    ledger = _ledger()
    _family(ledger, "RTU", "Rooftop Unit", "RTU-1", 1)
    _family(ledger, "EF", "Exhaust Fan", "EF-1", 1)
    ledger.add("group", "corridor air", "RTU, EF", "S5", "corridor air", "risers", SETTLED)
    ledger.add("sequence_match", "ROOFTOP UNITS", "RTU", "Q5", "ROOFTOP UNITS", "sequence", SETTLED)
    ledger.add("sequence_match", "EXHAUST FANS", "EF", "Q1", "EXHAUST FANS", "sequence", SETTLED)
    job = _plan(ledger)
    assert [s.key for s in job.systems] == ["RTU", "EF"]
    assert len(job.questions) == 1 and "corridor air" in job.questions[0] and "RTU, EF" in job.questions[0]


def test_a_group_with_one_matched_family_is_kept():
    ledger = _ledger()
    _family(ledger, "RTU", "Rooftop Unit", "RTU-1", 1)
    _family(ledger, "EF", "Exhaust Fan", "EF-1", 1)
    ledger.add("group", "corridor air", "RTU, EF", "S5", "corridor air", "risers", SETTLED)
    ledger.add("sequence_match", "ROOFTOP UNITS", "RTU", "Q5", "ROOFTOP UNITS", "sequence", SETTLED)
    assert [s.key for s in _plan(ledger).systems] == ["corridor air"]


def test_a_group_with_a_blank_subject_is_named_by_its_members():
    ledger = _ledger()
    _family(ledger, "BS", "Branch Selector", "BS-1", 1)
    _family(ledger, "AC", "Indoor Unit", "AC-1", 1)
    ledger.add("group", "  ", "BS, AC", "S5", "riser", "risers", SETTLED)
    (system,) = _plan(ledger).systems
    assert system.key == "BS / AC" and system.name == "BS / AC"


def _vrf(cu_count=6) -> Ledger:
    """Six condensing units of which the riser takes four, a branch selector, three indoor types of which two are
    on the riser (their counts on a link)."""
    ledger = _ledger()
    _family(ledger, "CU", "Condensing Unit", "CU-1 thru 6", cu_count, source="S5")
    _family(ledger, "BS", "Branch Selector Box", "BS-1", 2, source="S5")
    _family(ledger, "AC", "Variable Refrigerant Flow Ductless Wall Mounted Indoor Unit", "AC-1, AC-2, AC-9", 5,
            source="S5")
    ledger.add("group", "VRF-A", "CU (CU-1 thru 4), BS (BS-1 x2), AC (AC-1, AC-2)", "S5", "VRF-A riser", "risers",
               SETTLED)
    ledger.add("link", "BS-1", "AC-1 x3, AC-2 x1", "S5", "BS-1 serves AC-1 x3, AC-2 x1", "plans", SETTLED)
    return ledger


def test_a_vrf_group_is_one_system_with_indoor_condensing_and_branch_selector_families():
    job = _plan(_vrf())
    vrf, split = job.systems
    assert vrf.key == "VRF-A" and vrf.shape == "VRF System" and vrf.control == "integration"
    cu, bs, ac = vrf.families
    assert (cu.name, cu.tags, cu.count.value) == ("Condensing Unit", ("CU-1", "CU-2", "CU-3", "CU-4"), 4)
    assert (bs.name, bs.tags, bs.count.value) == ("Branch Selector", ("BS-1",), 2)
    assert (ac.name, ac.tags, ac.count.value) == ("Indoor Unit", ("AC-1", "AC-2"), 4)
    assert ac.count.sources == (Ref("S5", "BS-1 serves AC-1 x3, AC-2 x1", "M-601, Drawings.pdf page 9"),)
    assert cu.count.sources == (Ref("S5", "CU rows 6", "M-601, Drawings.pdf page 9"),)
    # the rest of CU and AC are split units no group took: one Split System
    assert split.key == "Split System" and split.alternate == "base"
    rest_cu, rest_ac = split.families
    assert (rest_cu.tags, rest_cu.count.value) == (("CU-5", "CU-6"), 2)
    assert (rest_ac.tags, rest_ac.count.value) == (("AC-9",), 1)
    assert rest_ac.name == "Indoor Unit"                              # a long description takes the role word
    # each reduced rest names the count it was reduced from (PLN-3): one question per family, both numbers
    cu_q, ac_q = job.questions
    assert cu_q.startswith("Condensing Unit (CU): 6 per M-601;") and "prints 2" in cu_q
    assert "Indoor Unit (AC): 5 per M-601;" in ac_q and "prints 1" in ac_q


def test_type_tags_with_no_stated_count_are_unknown_and_asked_and_the_rest_never_undershoots():
    job = _plan(_vrf(cu_count=8))                  # eight units over six tags: the tags are types
    vrf, split = job.systems
    cu = vrf.families[0]
    assert cu.tags == ("CU-1", "CU-2", "CU-3", "CU-4") and cu.count.value is None
    assert any("CU" in q and "VRF-A" in q and "CU-1 thru 4" in q and "Qty (##)" in q for q in job.questions)
    assert split.families[0].tags == ("CU-5", "CU-6") and split.families[0].count.value == 8


def test_the_rest_keeps_the_family_count_unless_one_per_remaining_tag_is_left():
    ledger = _ledger()
    _family(ledger, "AC", "Indoor Unit", "AC-1, AC-2, AC-3", 3, source="S5")
    _family(ledger, "BS", "Branch Selector", "BS-1", 1, source="S5")
    ledger.add("group", "VRF-C", "BS, AC (AC-1 x2)", "S5", "VRF-C riser", "risers", SETTLED)
    vrf, ac = _plan(ledger).systems
    assert vrf.families[0].count.value == 2
    assert ac.key == "AC" and ac.families[0].tags == ("AC-2", "AC-3") and ac.families[0].count.value == 3


def test_every_count_a_fact_gives_a_tag_is_summed():
    ledger = _vrf()
    ledger.add("link", "BS-2", "AC-1 x3; BS-2 serves AC-1 x2", "S5", "AC-1 x3; AC-1 x2", "plans", SETTLED)
    vrf = _plan(ledger).systems[0]
    assert vrf.families[2].tags == ("AC-1", "AC-2") and vrf.families[2].count.value == 3 + 1 + 3 + 2
    assert len(vrf.families[2].count.sources) == 2


def test_a_member_listing_every_tag_or_none_takes_the_whole_family():
    ledger = _ledger()
    _family(ledger, "ODU", "Outdoor Unit", "ODU-1, ODU-2", 2, source="S5")
    _family(ledger, "IDU", "Indoor Unit", "IDU-1 thru 3", 3, source="S5")
    ledger.add("group", "Heat Pump VRF", "ODU (ODU-1, ODU-2), IDU", "S5", "VRF riser", "risers", SETTLED)
    (vrf,) = _plan(ledger).systems
    assert [f.tags for f in vrf.families] == [("ODU-1", "ODU-2"), ("IDU-1", "IDU-2", "IDU-3")]
    assert [f.count.value for f in vrf.families] == [2, 3]
    assert [f.name for f in vrf.families] == ["Condensing Unit", "Indoor Unit"]


def test_bare_tags_and_bare_tag_ranges_in_a_group_join_their_family():
    ledger = _ledger()
    _family(ledger, "ACCU", "Air Cooled Condensing Unit", "ACCU-1", 1, source="S5")
    _family(ledger, "WAC", "Wall Air Conditioner", "WAC-1.0, WAC-1.5, WAC-2.0", 3, source="S5")
    _family(ledger, "FCU", "Fan Coil", "FCU-1 thru 6", 6, source="S5")
    ledger.add("group", "VRF-1", "ACCU (ACCU-1), WAC-1.0, WAC-1.5, FCU-2 thru 4", "S5", "VRF riser", "risers", SETTLED)
    vrf, wac, fcu = _plan(ledger).systems
    assert vrf.key == "VRF-1"
    assert [(f.tags, f.count.value) for f in vrf.families] == [(("ACCU-1",), 1), (("WAC-1.0", "WAC-1.5"), 2),
                                                               (("FCU-2", "FCU-3", "FCU-4"), 3)]
    assert wac.key == "WAC" and wac.families[0].tags == ("WAC-2.0",) and wac.families[0].count.value == 1
    assert fcu.key == "FCU" and fcu.families[0].tags == ("FCU-1", "FCU-5", "FCU-6")


def test_a_listed_tag_not_the_familys_own_is_ignored():
    ledger = _ledger()
    _family(ledger, "BS", "Branch Selector", "BS-1", 1, source="S5")
    _family(ledger, "AC", "Indoor Unit", "AC-1, AC-9", 2, source="S5")
    ledger.add("group", "VRF-B", "BS, AC (AC-1, AC-99)", "S5", "VRF-B riser", "risers", SETTLED)
    vrf, ac = _plan(ledger).systems
    assert vrf.families[1].tags == ("AC-1",) and vrf.families[1].count.value == 1
    assert ac.key == "AC" and ac.families[0].tags == ("AC-9",)


def test_an_hru_is_a_branch_selector_only_when_its_name_or_the_group_says_so():
    ledger = _ledger()
    _family(ledger, "HRU", "Heat Recovery Unit", "HRU-1", 1, source="S5")
    _family(ledger, "IDU", "Indoor Unit", "IDU-1", 1, source="S5")
    ledger.add("group", "Heat Pump Plant", "HRU, IDU", "S5", "riser", "risers", SETTLED)
    (plant,) = _plan(ledger).systems
    assert plant.shape != "VRF System" and plant.families[0].name == "Heat Recovery Unit"
    ledger = _ledger()
    _family(ledger, "HRU", "Heat Recovery Unit", "HRU-1", 1, source="S5")
    _family(ledger, "IDU", "Indoor Unit", "IDU-1", 1, source="S5")
    ledger.add("group", "VRF Heat Pump Plant", "HRU, IDU", "S5", "riser", "risers", SETTLED)
    (plant,) = _plan(ledger).systems
    assert plant.shape == "VRF System" and plant.families[0].name == "Branch Selector"
    ledger = _ledger()
    _family(ledger, "HRU", "Branch Selector", "HRU-1", 1, source="S5")
    _family(ledger, "IDU", "Indoor Unit", "IDU-1", 1, source="S5")
    ledger.add("group", "Heat Pump Plant", "HRU, IDU", "S5", "riser", "risers", SETTLED)
    (plant,) = _plan(ledger).systems
    assert plant.shape == "VRF System" and plant.control == "integration"


def test_a_plan_only_family_inside_a_group_keeps_its_existence_question():
    ledger = _ledger()
    _family(ledger, "BS", "Branch Selector", "BS-1", 1, source="S5")
    ledger.add("family", "IDU", "seen on plans, not scheduled: Indoor Unit (ceiling)", "S2", "IDU", "plans")
    ledger.add("unit", "IDU", "IDU-1, IDU-2", "S2", "IDU-1 IDU-2", "plans")
    ledger.add("group", "VRF-D", "BS, IDU", "S5", "VRF-D riser", "risers", SETTLED)
    job = _plan(ledger)
    (vrf,) = job.systems
    assert vrf.families[1].count.value is None
    assert job.questions == ("Indoor Unit (IDU-1, 2) is seen on the drawings but on no schedule; confirm it "
                             "exists (it is in the VRF-D block).",)


# ---- split systems ---------------------------------------------------------------------------------------------

def test_split_units_no_group_took_are_one_block_and_a_lone_one_stays_alone():
    ledger = _ledger()
    _family(ledger, "AC", "Ductless Split Indoor Unit", "AC-1, AC-2", 2)
    _family(ledger, "EF", "Exhaust Fan", "EF-1", 1)
    _family(ledger, "ACCU", "Outdoor Unit", "ACCU-1, ACCU-2", 2)
    split, ef = _plan(ledger).systems
    assert split.key == "Split System" and [f.tags for f in split.families] == [("AC-1", "AC-2"), ("ACCU-1", "ACCU-2")]
    assert [f.name for f in split.families] == ["Ductless Split Indoor Unit", "Outdoor Unit"]
    assert ef.key == "EF"
    ledger = _ledger()
    _family(ledger, "CU", "Condensing Unit", "CU-1", 1)
    (cu,) = _plan(ledger).systems
    assert cu.key == "CU"


def test_split_units_in_two_sequence_sections_make_two_blocks_joining_by_tag_suffix():
    ledger = _ledger()
    _family(ledger, "AC", "Indoor Unit", "AC-NORTH-1", 1)
    _family(ledger, "CU", "Condensing Unit", "CU-NORTH-1", 1)
    _family(ledger, "SS", "Indoor Unit", "SS-SOUTH-1", 1)
    _family(ledger, "ACCU", "Outdoor Unit", "ACCU-SOUTH-1", 1)
    _family(ledger, "OU", "Outdoor Unit", "OU-SOUTH-1", 1)                       # matched to no section
    ledger.add("sequence_match", "NORTH SPLITS", "AC", "Q3", "NORTH SPLITS", "sequence", SETTLED)
    ledger.add("sequence_match", "NORTH SPLITS", "CU", "Q3", "NORTH SPLITS", "sequence", SETTLED)
    ledger.add("sequence_match", "SOUTH SPLITS", "SS", "Q4", "SOUTH SPLITS", "sequence", SETTLED)
    ledger.add("sequence_match", "SOUTH SPLITS", "ACCU", "Q4", "SOUTH SPLITS", "sequence", SETTLED)
    job = _plan(ledger)
    north, south = job.systems
    assert north.key == "Split System — NORTH SPLITS" and [f.tags[0] for f in north.families] == ["AC-NORTH-1",
                                                                                                    "CU-NORTH-1"]
    assert south.key == "Split System — SOUTH SPLITS"
    assert [f.tags[0] for f in south.families] == ["SS-SOUTH-1", "ACCU-SOUTH-1", "OU-SOUTH-1"]
    assert {r.source_id for r in north.sequence_refs} == {"Q3"} and {r.source_id for r in south.sequence_refs} == {"Q4"}
    assert job.questions == ()


def test_split_units_with_different_alternates_or_exceptions_stay_apart():
    ledger = _ledger()
    _family(ledger, "AC", "Indoor Unit", "AC-1", 1)
    _family(ledger, "ACCU", "Outdoor Unit", "ACCU-1", 1)
    _family(ledger, "SS", "Indoor Unit", "SS-1", 1)
    _family(ledger, "CU", "Condensing Unit", "CU-1", 1)
    ledger.add("note", "alternate", "add: SS", "S4", "SS as an add", "spec", SETTLED)
    ledger.add("note", "alternate", "add: CU", "S4", "CU as an add", "spec", SETTLED)
    base, add = _plan(ledger).systems
    assert base.key == "Split System" and base.alternate == "base"
    assert add.key == "Split System (add alternate)" and add.alternate == "add"
    assert [f.tags for f in add.families] == [("SS-1",), ("CU-1",)]
    ledger = _ledger()
    _family(ledger, "AC", "Indoor Unit", "AC-1", 1)
    _family(ledger, "ACCU", "Outdoor Unit", "ACCU-1", 1)
    ledger.add("note", "exception", "Exception to any work with AC-1", "S4", "AC-1 by others", "spec", SETTLED)
    ac, accu = _plan(ledger).systems
    assert (ac.key, accu.key) == ("AC", "ACCU")


def test_a_plan_only_split_unit_keeps_its_existence_question_in_the_block():
    ledger = _ledger()
    _family(ledger, "AC", "Indoor Unit", "AC-1", 1)
    ledger.add("family", "ACCU", "seen on plans, not scheduled: Outdoor Unit", "S2", "ACCU", "plans")
    job = _plan(ledger)
    (split,) = job.systems
    assert split.key == "Split System" and split.families[1].count == Count(None)
    assert job.questions == ("Outdoor Unit (ACCU) is seen on the drawings but on no schedule; confirm it exists "
                             "(it is in the Split System block).",)


def test_a_split_block_never_takes_the_vrf_shape():
    ledger = _ledger()
    _family(ledger, "AC", "Indoor Unit", "AC-1", 1)
    _family(ledger, "CU", "Condensing Unit", "CU-1", 1)
    (split,) = _plan(ledger).systems
    assert split.key == "Split System" and split.shape == ""


def test_a_split_unit_named_by_its_full_tag_joins_the_split_block():
    ledger = _ledger()
    _family(ledger, "AC", "Indoor Unit", "AC-1", 1)
    ledger.add("family", "ACCU-ROOF", "seen on plans, not scheduled: condensing unit on the roof", "S2", "ACCU-ROOF",
               "plans")
    ledger.add("unit", "ACCU-ROOF", "ACCU-ROOF", "S2", "ACCU-ROOF", "plans")
    ledger.add("count", "ACCU-ROOF", 1, "S2", "ACCU-ROOF", "plans")
    job = _plan(ledger)
    (split,) = job.systems
    assert split.key == "Split System" and [f.tags for f in split.families] == [("AC-1",), ("ACCU-ROOF",)]
    assert job.questions == ("condensing unit on the roof (ACCU-ROOF) is seen on the drawings but on no schedule; "
                             "confirm it exists (it is in the Split System block).",)


def test_a_split_block_takes_the_playbooks_split_shape_when_there_is_one():
    split_shape = Shape(name="Split System", prefixes=("AC", "ACCU"), kind_words=("split system",), header="{name}",
                        family_names=("Indoor Unit", "Outdoor Unit"), line_order=("comm",), slot_kinds={"comm": "wiring"},
                        wording={"comm": "{verb} {device}"}, tech_hours=TechHours("unit", 1.0))
    playbook = dataclasses.replace(PLAYBOOK, shapes={**PLAYBOOK.shapes, "Split System": split_shape})
    ledger = _ledger()
    _family(ledger, "AC", "Indoor Unit", "AC-1", 1)
    _family(ledger, "ACCU", "Outdoor Unit", "ACCU-1", 1)
    _family(ledger, "CU", "Condensing Unit", "CU-1", 1)          # not a split prefix of this Playbook
    split, cu = _plan(ledger, playbook).systems
    assert split.shape == "Split System" and [f.tags for f in split.families] == [("AC-1",), ("ACCU-1",)]
    assert cu.key == "CU"


# ---- dampers -----------------------------------------------------------------------------------------------------

def test_a_damper_linked_to_a_fan_moves_under_the_fan_and_the_rest_stay_a_damper_system():
    ledger = _ledger()
    _family(ledger, "MD", "Motorized Damper", "MD-1 thru 3", 3, source="S2")
    _family(ledger, "EF", "Exhaust Fan", "EF-1", 1)
    link = ledger.add("link", "MD-1", "EF-1", "S2", "MD-1 at EF-1", "plans", SETTLED)
    ledger.add("location", "MD-2", "corridor", "S5", "MD-2 corridor", "plans", SETTLED)
    job = _plan(ledger)
    md, ef = job.systems
    assert ef.key == "EF" and [f.name for f in ef.families] == ["Exhaust Fan", "Motorized Damper"]
    damper = ef.families[1]
    assert damper.tags == ("MD-1",) and damper.count == Count(1, (Ref("S2", "MD-1 at EF-1", "M-101, Drawings.pdf page 2"),))
    assert md.key == "MD" and md.families[0].tags == ("MD-2", "MD-3") and md.families[0].count.value == 2
    assert md.families[0].count.sources == (Ref("S2", "MD rows 3", "M-101, Drawings.pdf page 2"),)
    assert any("Motorized Damper (MD): 2 of the 3" in q and "EF" in q and "M-101" in q and "M-601" in q for q in job.questions)
    assert link.id


def test_when_every_damper_is_claimed_there_is_no_damper_system():
    ledger = _ledger()
    _family(ledger, "MD", "Motorized Damper", "MD-1", 1, source="S2")
    _family(ledger, "EF", "Exhaust Fan", "EF-1", 1)
    ledger.add("link", "MD-1", "EF-1", "S2", "MD-1 at EF-1", "plans", SETTLED)
    job = _plan(ledger)
    assert [s.key for s in job.systems] == ["EF"] and job.questions == ()


def test_a_plan_only_damper_claimed_by_a_fan_keeps_its_existence_question_in_the_fans_block():
    ledger = _ledger()
    ledger.add("family", "MD", "seen on plans, not scheduled: Motorized Damper", "S2", "MD", "plans")
    ledger.add("count", "MD", 1, "S2", "MD x1", "plans")
    ledger.add("unit", "MD", "MD-1", "S2", "MD-1", "plans")
    _family(ledger, "EF", "Exhaust Fan", "EF-1", 1)
    ledger.add("link", "MD-1", "EF-1", "S2", "MD-1 at EF-1", "plans", SETTLED)
    job = _plan(ledger)
    (ef,) = job.systems
    assert [f.name for f in ef.families] == ["Exhaust Fan", "Motorized Damper"]
    assert job.questions == ("Motorized Damper (MD-1) is seen on the drawings but on no schedule; confirm it exists "
                             "(it is in the Exhaust Fan block).",)


def test_a_damper_moved_under_a_fan_brings_its_sequence_with_it():
    ledger = _ledger()
    _family(ledger, "MD", "Motorized Damper", "MD-1", 1, source="S2")
    _family(ledger, "EF", "Exhaust Fan", "EF-1", 1)
    ledger.add("link", "MD-1", "EF-1", "S2", "MD-1 at EF-1", "plans", SETTLED)
    ledger.add("sequence_match", "EXHAUST FANS", "MD", "Q1", "EXHAUST FANS", "sequence", SETTLED)
    job = _plan(ledger)
    (ef,) = job.systems
    assert [r.source_id for r in ef.sequence_refs] == ["Q1"]
    assert job.questions == ()


_DAMPER_SCHEDULE = "\n".join([
    "== 4. SCHEDULES ==",
    "[S6] MOTORIZED DAMPER SCHEDULE — M-501, Drawings.pdf page 6 (4 rows)",
    "    Columns: TAG | SERVES | ACTUATOR",
    "[S7] MD-1 | SPF-1 | 24V AC",
    "[S8] MD-2 | — | 24V AC",
    "[S9] MD-3 | EF-1 | 24V AC",
    "[S10] MD-4 | SPF-1, EF-1 | 24V AC",
])


def _damper_dossier() -> Dossier:
    sources = {"S7": "MOTORIZED DAMPER SCHEDULE row MD-1, M-501, Drawings.pdf page 6",
               "S9": "MOTORIZED DAMPER SCHEDULE row MD-3, M-501, Drawings.pdf page 6"}
    return Dossier(job_name="Invented Job", text=_DAMPER_SCHEDULE, images=(), sources=sources, families=(),
                   device_totals={}, counts={}, stats={})


def test_a_damper_schedule_row_naming_a_fans_tag_moves_the_damper_under_that_fan():
    ledger = _ledger()
    _family(ledger, "MD", "Motorized Damper", "MD-1 thru 4", 4, source="S2")
    _family(ledger, "SPF", "Stair Pressurization Fan", "SPF-1", 1)
    _family(ledger, "EF", "Exhaust Fan", "EF-1", 1)
    _family(ledger, "AC", "Air Conditioning Unit", "AC-1", 1)            # "AC" in the actuator column is no tag
    ledger.add("link", "MD-3", "EF-1", "S2", "MD-3 at EF-1", "plans", SETTLED)   # a ledger link wins over the row
    job = plan_job(ledger, None, _damper_dossier(), PLAYBOOK)
    systems = _by_key(job)
    spf = systems["SPF"]
    assert [f.name for f in spf.families] == ["Stair Pressurization Fan", "Motorized Damper"]
    assert spf.families[1].tags == ("MD-1",)
    assert spf.families[1].count == Count(1, (Ref("S7", "MD-1 | SPF-1 | 24V AC", _damper_dossier().sources["S7"]),))
    ef = systems["EF"]
    assert ef.families[1].tags == ("MD-3",) and [r.source_id for r in ef.families[1].count.sources] == ["S2"]
    assert len(systems["AC"].families) == 1
    # MD-2 serves nothing and MD-4 names two systems: both stay in the damper block
    assert systems["MD"].families[0].tags == ("MD-2", "MD-4") and systems["MD"].families[0].count.value == 2


def test_the_leftover_damper_count_cites_only_the_familys_count():
    ledger = _ledger()
    _family(ledger, "MD", "Motorized Damper", "MD-1 thru 3", 3, source="S2")
    _family(ledger, "EF", "Exhaust Fan", "EF-1", 1)
    ledger.add("link", "MD-1", "EF-1", "S2", "MD-1 at EF-1", "plans", SETTLED)
    ledger.add("location", "MD-2", "corridor", "S5", "MD-2 corridor", "plans", SETTLED)
    md = _by_key(_plan(ledger))["MD"]
    assert md.families[0].count == Count(2, (Ref("S2", "MD rows 3", "M-101, Drawings.pdf page 2"),))


def test_a_damper_linked_to_a_fan_in_a_group_joins_the_group_and_a_fire_damper_never_moves():
    ledger = _ledger()
    _family(ledger, "MD", "Motorized Damper", None, 2, source="S2")
    _family(ledger, "EF", "Exhaust Fan", "EF-1", 1)
    ledger.add("group", "Garage Exhaust", "EF", "S5", "GARAGE EXHAUST", "risers", SETTLED)
    ledger.add("link", "MD on garage exhaust duct", "EF-1", "S2", "MD EF-1", "plans", SETTLED)
    ledger.add("link", "FSD-1", "EF-1", "S2", "FSD-1 at EF-1", "plans", SETTLED)
    ledger.add("link", "combination fire/smoke damper", "EF-1", "S2", "fire/smoke damper EF-1", "plans", SETTLED)
    job = _plan(ledger)
    md, garage = job.systems
    assert garage.key == "Garage Exhaust"
    damper = garage.families[1]
    assert damper.name == "Motorized Damper" and damper.tags == () and damper.count.value == 1
    assert md.families[0].count.value == 1


def test_a_damper_family_inside_a_group_gives_up_the_dampers_a_fan_claims():
    ledger = _ledger()
    _family(ledger, "EF", "Exhaust Fan", "EF-1", 1)
    _family(ledger, "MD", "Motorized Damper", "MD-1", 1, source="S2")
    ledger.add("group", "Shaft Ventilation", "EF, MD", "S5", "SHAFT VENTILATION", "risers", SETTLED)
    ledger.add("link", "MD-1", "EF-1", "S2", "MD-1 EF-1", "plans", SETTLED)
    (shaft,) = _plan(ledger).systems
    assert [(f.name, f.tags, f.count.value) for f in shaft.families] == [("Exhaust Fan", ("EF-1",), 1),
                                                                         ("Motorized Damper", ("MD-1",), 1)]


def test_a_damper_family_with_no_count_stays_unknown_and_asks():
    ledger = _ledger()
    ledger.add("family", "MD", "Motorized Damper", "S2", "MD", "plans", SETTLED)
    _family(ledger, "EF", "Exhaust Fan", "EF-1", 1)
    ledger.add("link", "MD-1", "EF-1", "S2", "MD-1 at EF-1", "plans", SETTLED)
    job = _plan(ledger)
    md = _by_key(job)["MD"]
    assert md.families[0].count.value is None
    assert any("how many are there in all" in q and "(MD)" in q for q in job.questions)


def test_a_damper_link_is_credited_to_the_family_of_its_tag():
    # PLN-2: "CD-1 damper" does not lead with MD, but its tag is CD's: CD-1 moves under the fan and MD keeps both
    ledger = _ledger()
    _family(ledger, "EF", "Exhaust Fan", "EF-1", 1)
    _family(ledger, "MD", "Motorized Damper", "MD-1, MD-2", 2, source="S2")
    _family(ledger, "CD", "Motorized Control Damper", "CD-1", 1, source="S2")
    ledger.add("link", "CD-1 damper", "EF-1", "S2", "CD-1 damper at EF-1", "plans", SETTLED)
    job = _plan(ledger)
    systems = _by_key(job)
    ef = systems["EF"]
    assert [(f.name, f.tags, f.count.value) for f in ef.families] == [("Exhaust Fan", ("EF-1",), 1),
                                                                      ("Motorized Control Damper", ("CD-1",), 1)]
    md = systems["MD"]
    assert md.families[0].tags == ("MD-1", "MD-2") and md.families[0].count.value == 2
    assert "CD" not in systems
    assert not any("1 of the 2" in q for q in job.questions)


def test_a_damper_family_with_another_prefix_moves_under_its_fan():
    # PLN-5: a damper family the ledger names a damper moves under its fan whatever its prefix
    ledger = _ledger()
    _family(ledger, "EF", "Exhaust Fan", "EF-1", 1)
    _family(ledger, "CD", "Motorized Control Damper", "CD-1, CD-2", 2, source="S2")
    ledger.add("link", "CD-1", "EF-1", "S2", "CD-1 at EF-1", "plans", SETTLED)
    job = _plan(ledger)
    systems = _by_key(job)
    ef = systems["EF"]
    assert [(f.name, f.tags, f.count.value) for f in ef.families] == [("Exhaust Fan", ("EF-1",), 1),
                                                                      ("Motorized Control Damper", ("CD-1",), 1)]
    cd = systems["CD"]
    assert cd.families[0].tags == ("CD-2",) and cd.families[0].count.value == 1
    assert any("Motorized Control Damper (CD): 1 of the 2" in q for q in job.questions)


def test_a_damper_tag_written_without_its_dash_or_in_brackets_still_moves():
    ledger = _ledger()
    _family(ledger, "EF", "Exhaust Fan", "EF-1, EF-2", 2)
    _family(ledger, "MD", "Motorized Damper", "MD-1 thru 3", 3, source="S2")
    ledger.add("link", "MD1", "EF-1", "S2", "MD1 at EF-1", "plans", SETTLED)
    ledger.add("link", "damper (MD-2)", "EF-2", "S2", "damper (MD-2) at EF-2", "plans", SETTLED)
    job = _plan(ledger)
    ef = _by_key(job)["EF"]
    assert ef.families[1].tags == ("MD-1", "MD-2") and ef.families[1].count.value == 2
    md = _by_key(job)["MD"]
    assert md.families[0].tags == ("MD-3",) and md.families[0].count.value == 1


def test_a_fans_tag_in_a_damper_links_subject_is_not_the_dampers_tag():
    ledger = _ledger()
    _family(ledger, "MD", "Motorized Damper", None, 2, source="S2")
    _family(ledger, "EF", "Exhaust Fan", "EF-1", 1)
    ledger.add("link", "damper at EF-1", "EF-1", "S2", "damper at EF-1", "plans", SETTLED)
    ef = _by_key(_plan(ledger))["EF"]
    assert [(f.name, f.tags, f.count.value) for f in ef.families] == [("Exhaust Fan", ("EF-1",), 1),
                                                                      ("Motorized Damper", (), 1)]


# ---- duct heaters ------------------------------------------------------------------------------------------------

def test_duct_heaters_are_one_system_carrying_the_served_units_sequence():
    ledger = _ledger()
    _family(ledger, "RTU", "Rooftop Unit", "RTU-1", 1)
    _family(ledger, "EDH", "Electric Duct Heater", "EDH-1", 1)
    _family(ledger, "DH", "Duct Heater", "DH-1, DH-2", 2)
    ledger.add("sequence_match", "ROOFTOP UNITS", "RTU", "Q5", "ROOFTOP UNITS", "sequence", SETTLED)
    ledger.add("link", "RTU-1", "EDH-1", "S2", "EDH-1 in RTU-1 supply duct", "plans", SETTLED)
    job = _plan(ledger)
    rtu, heaters = job.systems
    assert heaters.key == "Duct Heaters" and heaters.shape == "Duct Heater"
    assert [f.tags for f in heaters.families] == [("EDH-1",), ("DH-1", "DH-2")]
    assert [r.source_id for r in heaters.sequence_refs] == ["Q5"]
    assert [r.source_id for r in rtu.sequence_refs] == ["Q5"]
    assert not any("matched no system" in q for q in job.questions)


def test_a_single_duct_heater_family_keeps_its_key_and_reads_the_unit_it_serves():
    ledger = _ledger()
    _family(ledger, "AHU", "Air Handling Unit", "AHU-1", 1)
    _family(ledger, "EDH", "Electric Duct Heater", "EDH-1", 1)
    ledger.add("sequence_match", "HEATING PLANT", "AHU", "Q2", "HEATING PLANT", "sequence", SETTLED)
    ledger.add("provider", "EDH", "serves AHU-1", "S2", "EDH-1 serves AHU-1", "plans", SETTLED)
    ahu, edh = _plan(ledger).systems
    assert edh.key == "EDH" and edh.shape == "Duct Heater" and [r.source_id for r in edh.sequence_refs] == ["Q2"]


def test_duct_heaters_with_different_alternates_stay_apart():
    ledger = _ledger()
    _family(ledger, "EDH", "Electric Duct Heater", "EDH-1", 1)
    _family(ledger, "DH", "Duct Heater", "DH-1", 1)
    _family(ledger, "XDH", "Duct Heater", "XDH-1", 1)
    ledger.add("note", "alternate", "add: XDH", "S4", "XDH as an add", "spec", SETTLED)
    base, add = _plan(ledger).systems
    assert base.key == "Duct Heaters" and len(base.families) == 2
    assert add.key == "XDH" and add.alternate == "add"


def _heater_ledger() -> Ledger:
    ledger = _ledger()
    _family(ledger, "ERV", "Energy Recovery Ventilator", "ERV-1, ERV-2", 2)
    _family(ledger, "MUA", "Make-Up Air Unit", "MUA-1", 1)
    _family(ledger, "EF", "Exhaust Fan", "EF-1", 1)
    _family(ledger, "EDH", "Electric Duct Heater", "EDH-3-1, EDH-3-2, EDH-4-1", 3)
    ledger.add("sequence_match", "ROOFTOP UNITS", "ERV", "Q5", "ROOFTOP UNITS", "sequence", SETTLED)
    ledger.add("location", "ERV-2", "fourth floor, beside EDH-4-1 (M-104)", "S2", "ERV-2 EDH-4-1", "plans", SETTLED)
    ledger.add("location", "EDH-3-1, 3-2", "third floor make-up air and MUA-1 (M-103)", "S2", "EDH-3-1 MUA-1", "plans",
               SETTLED)
    ledger.add("note", "ERV", "the BMS starts the duct heater whenever the ventilator runs",
               "S4", "starts the duct heater", "spec", SETTLED)
    ledger.add("location", "EF-1", "level 1 roof (M-101)", "S2", "EF-1", "plans", SETTLED)
    return ledger


def test_a_duct_heater_block_lists_each_unit_it_serves_and_each_served_unit_names_it():
    from bms.model import Served
    job = _plan(_heater_ledger())
    erv, mua, ef, edh = job.systems
    to_erv = Served("ERV", "Energy Recovery Ventilator", ("ERV-1", "ERV-2"), ("EDH-4-1",), "EDH", "Electric Duct Heater")
    to_mua = Served("MUA", "Make-Up Air Unit", ("MUA-1",), ("EDH-3-1", "EDH-3-2"), "EDH", "Electric Duct Heater")
    assert edh.serves == (to_erv, to_mua)
    assert erv.serves == (to_erv,) and mua.serves == (to_mua,) and ef.serves == ()
    assert [r.source_id for r in edh.sequence_refs] == ["Q5"]
    assert Job.from_dict(job.to_dict()) == job


def test_a_linked_heater_names_the_served_units_tag_and_its_own():
    ledger = _ledger()
    _family(ledger, "RTU", "Rooftop Unit", "RTU-1, RTU-2", 2)
    _family(ledger, "EDH", "Electric Duct Heater", "EDH-1", 1)
    _family(ledger, "DH", "Duct Heater", "DH-1, DH-2", 2)
    ledger.add("link", "RTU-1", "EDH-1", "S2", "EDH-1 in RTU-1 supply duct", "plans", SETTLED)
    rtu, heaters = _plan(ledger).systems
    (tie,) = heaters.serves
    assert (tie.key, tie.tags, tie.heaters, tie.heater_key, tie.heater_name) == \
        ("RTU", ("RTU-1",), ("EDH-1",), "Duct Heaters", "Duct Heaters")
    assert rtu.serves == (tie,)


def test_a_unit_whose_sequence_speaks_of_a_duct_heater_is_served():
    ledger = _ledger()
    _family(ledger, "OAF", "Outdoor Air Fan", "OAF-1", 1)
    _family(ledger, "EDH", "Electric Duct Heater", "EDH-1, EDH-2", 2)
    ledger.add("sequence_match", "OUTDOOR AIR FAN", "OAF", "Q4", "OUTDOOR AIR FAN", "sequence", SETTLED)
    text = ("--- [Q4] OUTDOOR AIR FAN ---\n"
            "[S50] The fan shall run in occupied mode and the electric duct heater shall hold the discharge air "
            "temperature.\n")
    dossier = dataclasses.replace(_dossier(), text=text)
    oaf, edh = plan_job(ledger, None, dossier, PLAYBOOK).systems
    (tie,) = edh.serves
    assert (tie.key, tie.tags, tie.heaters) == ("OAF", ("OAF-1",), ())
    assert oaf.serves == (tie,) and [r.source_id for r in edh.sequence_refs] == ["Q4"]


def test_a_heater_serving_no_named_unit_has_no_ties():
    ledger = _ledger()
    _family(ledger, "EDH", "Electric Duct Heater", "EDH-1", 1)
    (edh,) = _plan(ledger).systems
    assert edh.serves == ()


# ---- name case and number ----------------------------------------------------------------------------------------------

def test_acronyms_stay_upper_case_in_a_specific_name():
    ledger = _ledger()
    _family(ledger, "ITF", "Fan", "ITF-1", 1)
    ledger.add("sequence_match", "C. It closet relief fan", "ITF", "Q1", "C. It closet relief fan", "sequence",
               SETTLED)
    _family(ledger, "RXF", "Fan", "RXF-1", 1)
    ledger.add("sequence_match", "F. VRF ROOM EXHAUST FAN", "RXF", "Q2", "F.", "sequence", SETTLED)
    itf, rxf = _plan(ledger).systems
    assert itf.name == "IT Closet Relief Fan" and itf.families[0].name == "IT Closet Relief Fan"
    assert rxf.name == "VRF Room Exhaust Fan"


def test_a_plural_kind_is_singular_for_one_unit():
    ledger = _ledger()
    _family(ledger, "EF", "Exhaust Fans", "EF-1", None)
    _family(ledger, "KF", "Kitchen Fans", None, 1)
    _family(ledger, "TF", "Toilet Fans", "TF-1, TF-2", 2)
    ef, kf, tf = _plan(ledger).systems
    assert ef.name == "Exhaust Fan" and ef.families[0].name == "Exhaust Fan"
    assert kf.name == "Kitchen Fan"
    assert tf.name == "Toilet Fans"


# ---- the whole -----------------------------------------------------------------------------------------------------

def test_keys_are_unique_and_the_plan_is_pure():
    ledger = _ledger()
    _family(ledger, "EF", "Exhaust Fan", "EF-1", 1)
    _family(ledger, "BS", "Branch Selector", "BS-1", 1)
    _family(ledger, "AC", "Indoor Unit", "AC-1", 1)
    ledger.add("group", "EF", "BS, AC", "S5", "riser", "risers", SETTLED)     # a group named as a family
    first = _plan(ledger)
    keys = [s.key for s in first.systems]
    assert len(keys) == len(set(keys)) == 2
    assert _plan(ledger) == first


def test_every_ref_cites_a_known_source_with_its_words():
    job = _plan(_vrf())
    refs = [r for s in job.systems for f in s.families for r in (*f.count.sources, *(o.ref for o in f.count.others))]
    refs += [r for s in job.systems for r in s.sequence_refs]
    assert refs and all(r.source_id in SOURCES and r.quote and r.where for r in refs)


@pytest.mark.parametrize("value", ["", "   "])
def test_an_empty_family_name_falls_back_to_its_prefix(value):
    ledger = _ledger()
    ledger.add("family", "GLY", value or "x", "S3", "GLY", "schedules", SETTLED)
    ledger.facts[next(iter(f.id for f in ledger.of_kind("family")))] = dataclasses.replace(
        ledger.of_kind("family")[0], value=value)
    (gly,) = _plan(ledger).systems
    assert gly.name == "GLY"


# ---- the higher count wins: every source of a count is read (never undershoot) -------------------------------------

_COUNTS_LINE = ("UHX (Unit Heater): schedule rows 2; QUANTITY column total —; distinct tags 2; plan placements 31 "
                "(M-101 20; M-102 11); riser —")


def test_plan_placements_in_the_counts_line_beat_the_schedule_rows():
    # the seed's count fact holds the schedule rows (types); the plans place 31 units: 31 prints
    ledger = _ledger()
    ledger.add("family", "UHX", "Unit Heater", "S1", _COUNTS_LINE, "seed", SETTLED)
    ledger.add("unit", "UHX", "UHX-1, 2", "S1", "Tags: UHX-1, 2", "seed", SETTLED)
    ledger.add("count", "UHX", 2, "S1", _COUNTS_LINE, "seed", SETTLED)
    (uhx,) = _plan(ledger).systems
    count = uhx.families[0].count
    where = "equipment counts for FAN"
    assert count.value == 31
    assert count.sources == (Ref("S1", "plan placements 31", where),)
    assert count.others == (OtherCount(2, Ref("S1", _COUNTS_LINE, where)),)


def test_a_riser_or_quantity_column_in_the_counts_line_counts_too():
    line = "ZF (Fan): schedule rows 1; QUANTITY column total 6; distinct tags 1; plan placements 0; riser 8"
    ledger = _ledger()
    ledger.add("family", "ZF", "Fan", "S1", line, "seed", SETTLED)
    ledger.add("count", "ZF", 6, "S1", line, "seed", SETTLED)
    count = _plan(ledger).systems[0].families[0].count
    assert count.value == 8 and count.sources[0].quote == "riser 8"
    assert {o.value for o in count.others} == {6, 1}


def test_a_later_count_fact_of_the_same_family_is_read():
    ledger = _ledger()
    _family(ledger, "UHX", "Unit Heater", "UHX-1, 2", 2)
    ledger.add("count", "UHX", 14, "S2", "UHX-1 UHX-2 (14 placed)", "plans", "added")
    count = _plan(ledger).systems[0].families[0].count
    assert count.value == 14 and count.sources == (Ref("S2", "UHX-1 UHX-2 (14 placed)", "M-101, Drawings.pdf page 2"),)
    assert count.others == (OtherCount(2, Ref("S3", "UHX rows 2", "M-501, Drawings.pdf page 6")),)


def test_a_count_fact_about_a_tag_counts_for_its_family():
    ledger = _ledger()
    _family(ledger, "GX", "Garage Fan", "GX-A", 1)
    ledger.add("count", "GX-A", 9, "S2", "GX-A x9", "plans", SETTLED)
    count = _plan(ledger).systems[0].families[0].count
    assert count.value == 9 and count.sources == (Ref("S2", "GX-A x9", "M-101, Drawings.pdf page 2"),)
    assert count.others == (OtherCount(1, Ref("S3", "GX rows 1", "M-501, Drawings.pdf page 6")),)


def test_a_tag_times_count_on_a_sheet_of_the_dossier_counts():
    ledger = _ledger()
    _family(ledger, "GX", "Garage Fan", "GX-A, GX-B", 2)
    dossier = Dossier(job_name="Invented Job",
                      text=("[D7] P-100, Drawings.pdf page 3 GARAGE PLAN: DUCT UP GX-A ×9 TAPS GX-B ×3 FSD 20x10\n"
                            "[D8] P-101, Drawings.pdf page 4 LEVEL 1 PLAN: GX-B x2 GX-BB ×40\n"),
                      images=(), sources={"D7": "P-100, Drawings.pdf page 3 (sheet text)",
                                          "D8": "P-101, Drawings.pdf page 4 (sheet text)"},
                      families=(), device_totals={}, counts={}, stats={})
    count = plan_job(ledger, None, dossier, PLAYBOOK).systems[0].families[0].count
    assert count.value == 9 + 3 + 2
    assert [r.source_id for r in count.sources] == ["D7", "D8"]
    assert count.sources[0] == Ref("D7", "GX-A ×9 ... GX-B ×3", "P-100, Drawings.pdf page 3")
    assert count.others == (OtherCount(2, Ref("S3", "GX rows 2", "M-501, Drawings.pdf page 6")),)


def test_schedule_rows_of_types_make_a_groups_part_unknown_when_the_plans_place_more():
    # rows 2 = tags 2 looked like unit tags; the plans place 31, so the tags are types: the part is asked, not 1
    ledger = _ledger()
    ledger.add("family", "UHX", "Unit Heater", "S1", _COUNTS_LINE, "seed", SETTLED)
    ledger.add("unit", "UHX", "UHX-1, 2", "S1", "Tags: UHX-1, 2", "seed", SETTLED)
    ledger.add("count", "UHX", 2, "S1", _COUNTS_LINE, "seed", SETTLED)
    _family(ledger, "BS", "Branch Selector", "BS-1", 1, source="S5")
    ledger.add("group", "VRF-Z", "BS, UHX (UHX-1)", "S5", "VRF-Z riser", "risers", SETTLED)
    vrf, rest = _plan(ledger).systems
    assert vrf.families[0].tags == ("UHX-1",) and vrf.families[0].count.value is None
    assert rest.families[0].tags == ("UHX-2",) and rest.families[0].count.value == 31


# ---- planner fixes: the dossier's no-kind name, families of one name, a generic kind, split pairs -------------------

def test_the_no_kind_name_is_the_dossiers_own_fallback():
    from bms.plan_read import NO_KIND
    dossier_py = Path(__file__).resolve().parents[2] / "src" / "estimator" / "writing" / "dossier.py"
    assert f'"{NO_KIND}"' in dossier_py.read_text(encoding="utf-8")


def test_a_code_with_no_kind_that_is_a_tag_of_a_family_joins_that_familys_block_and_is_asked():
    from bms.plan_read import NO_KIND
    ledger = _ledger()
    _family(ledger, "GI", "Grease Interceptor", "GI-1 thru 3", 3)
    ledger.add("family", "GI-4", NO_KIND, "S1", f"GI-4 ({NO_KIND}): schedule rows 1", "seed")
    ledger.add("count", "GI-4", 2, "S1", f"GI-4 ({NO_KIND}): schedule rows 1", "seed", SETTLED)
    job = _plan(ledger)
    (gi,) = job.systems
    assert gi.key == "GI" and NO_KIND not in gi.name
    assert [(f.name, f.tags) for f in gi.families] == [("Grease Interceptor", ("GI-1", "GI-2", "GI-3")),
                                                       ("Grease Interceptor", ("GI-4",))]
    assert gi.families[1].count.value == 2
    asked = [q for q in job.questions if "GI-4" in q]
    assert len(asked) == 1 and "Grease Interceptor (GI)" in asked[0] and "no kind" in asked[0]


def test_a_code_with_no_kind_and_no_family_keeps_a_block_named_by_its_code_and_is_asked():
    from bms.plan_read import NO_KIND
    ledger = _ledger()
    ledger.add("family", "ZQ", NO_KIND, "S1", f"ZQ ({NO_KIND}): schedule rows 1", "seed")
    ledger.add("count", "ZQ", 1, "S1", f"ZQ ({NO_KIND}): schedule rows 1", "seed", SETTLED)
    job = _plan(ledger)
    (zq,) = job.systems
    assert zq.name == "ZQ" and [f.name for f in zq.families] == ["ZQ"]
    assert len([q for q in job.questions if "ZQ" in q]) == 1


def test_two_families_of_one_name_are_one_block_keeping_each_familys_tags_and_count():
    ledger = _ledger()
    _family(ledger, "TEF", "Toilet Exhaust Fan", "TEF-1", 1)
    _family(ledger, "EF", "Exhaust Fan", "EF-1", 1)
    _family(ledger, "TX", "Toilet Exhaust Fans", "TX-1, TX-2", 2)
    ledger.add("sequence_match", "EXHAUST FANS", "TX", "Q1", "EXHAUST FANS", "sequence", SETTLED)
    job = _plan(ledger)
    assert [s.key for s in job.systems] == ["TEF", "EF"]
    tef = job.systems[0]
    assert tef.name == "Toilet Exhaust Fan"
    assert [(f.tags, f.count.value) for f in tef.families] == [(("TEF-1",), 1), (("TX-1", "TX-2"), 2)]
    assert [r.source_id for r in tef.sequence_refs] == ["Q1"]
    assert any("TEF" in q and "TX" in q and "same name" in q for q in job.questions)
    # families of one generic kind, or of different alternates, stay apart
    ledger = _ledger()
    _family(ledger, "ZF", "Fan", "ZF-1", 1)
    _family(ledger, "YF", "Fan", "YF-1", 1)
    _family(ledger, "TEF", "Toilet Exhaust Fan", "TEF-1", 1)
    _family(ledger, "TX", "Toilet Exhaust Fan", "TX-1", 1)
    ledger.add("note", "alternate", "add: TX", "S4", "TX as an add", "spec", SETTLED)
    assert [s.key for s in _plan(ledger).systems] == ["ZF", "YF", "TEF", "TX"]


def test_a_family_with_only_a_generic_kind_name_is_asked_what_it_is():
    ledger = _ledger()
    _family(ledger, "P", "Pump", "P-1, P-1F, P-2", 3)
    _family(ledger, "EF", "Exhaust Fan", "EF-1", 1)
    job = _plan(ledger)
    assert [s.key for s in job.systems] == ["P", "EF"]
    asked = [q for q in job.questions if "P-1" in q]
    assert len(asked) == 1 and "only the general name" in asked[0]
    assert not any("EF-1" in q for q in job.questions)


def test_an_indoor_unit_and_its_outdoor_unit_in_two_sequence_sections_are_one_split_block():
    ledger = _ledger()
    _family(ledger, "AC", "Air Conditioning Unit", "AC-109, AC-117", 2)
    _family(ledger, "ACCU", "Air Cooled Condensing Unit", "ACCU-109, ACCU-117", 2)
    _family(ledger, "SS", "Indoor Unit", "SS-EAST-1", 1)
    _family(ledger, "CU", "Condensing Unit", "CU-EAST-1", 1)
    ledger.add("sequence_match", "NORTH SPLITS", "AC", "Q3", "NORTH SPLITS", "sequence", SETTLED)
    ledger.add("sequence_match", "SOUTH SPLITS", "ACCU", "Q4", "SOUTH SPLITS", "sequence", SETTLED)
    ledger.add("sequence_match", "ROOFTOP UNITS", "SS", "Q5", "ROOFTOP UNITS", "sequence", SETTLED)
    ledger.add("sequence_match", "ROOFTOP UNITS", "CU", "Q5", "ROOFTOP UNITS", "sequence", SETTLED)
    pair, east = _plan(ledger).systems
    assert pair.key == "Split System — NORTH SPLITS / SOUTH SPLITS"
    assert [f.tags for f in pair.families] == [("AC-109", "AC-117"), ("ACCU-109", "ACCU-117")]
    assert [r.source_id for r in pair.sequence_refs] == ["Q3", "Q4"]
    assert east.key == "Split System — ROOFTOP UNITS" and [f.tags[0] for f in east.families] == ["SS-EAST-1",
                                                                                                    "CU-EAST-1"]
    ledger = _ledger()                       # the pair alone: the one block is the plain Split System
    _family(ledger, "AC", "Air Conditioning Unit", "AC-109", 1)
    _family(ledger, "ACCU", "Air Cooled Condensing Unit", "ACCU-109", 1)
    ledger.add("sequence_match", "NORTH SPLITS", "AC", "Q3", "NORTH SPLITS", "sequence", SETTLED)
    ledger.add("sequence_match", "SOUTH SPLITS", "ACCU", "Q4", "SOUTH SPLITS", "sequence", SETTLED)
    (split,) = _plan(ledger).systems
    assert split.key == "Split System" and len(split.families) == 2


# ---- a reduced count names the count it came from (PLN-3) ---------------------------------------------------------

def _counts_hold(job: Job) -> None:
    """Every family prints its own value: nothing in `others` is higher (render prints the highest) or equal."""
    for system in job.systems:
        for family in system.families:
            count = family.count
            assert count.value == count.highest(), (system.key, family.name, count)
            assert all(o.value != count.value for o in count.others), (system.key, family.name, count)


def test_a_rest_block_names_the_count_it_was_reduced_from():
    # (a) the rest of a contradicted family: 10 per the schedule, 9 per the plans; a group takes EF-1 and EF-2
    ledger = _ledger()
    _family(ledger, "AHU", "Air Handling Unit", "AHU-1", 1)
    count = _family(ledger, "EF", "Exhaust Fan", "EF-1 thru 10", 10)
    ledger.contradict(count.id, 9, "S2", "EF x9", "plans")
    ledger.add("group", "AHU-1 Plant", "AHU, EF (EF-1, EF-2)", "S5", "AHU-1 PLANT riser", "risers", SETTLED)
    job = _plan(ledger)
    _counts_hold(job)
    rest = _by_key(job)["EF"].families[0]
    assert rest.tags[0] == "EF-3" and rest.count.value == 8
    asked = [q for q in job.questions if "EF" in q and "AHU-1 Plant" in q]
    assert len(asked) == 1 and "10" in asked[0] and "9" in asked[0] and "8" in asked[0]

    # (b) a link repeating the group's own "HRU-1 x3" is not counted twice: the rest keeps 9 of the 12
    ledger = _ledger()
    _family(ledger, "AHU", "Air Handling Unit", "AHU-1", 1)
    _family(ledger, "HRU", "Heat Recovery Unit", "HRU-1 thru 4", 12)
    ledger.add("group", "AHU-1 Plant", "AHU, HRU (HRU-1 x3)", "S5", "AHU-1 PLANT riser", "risers", SETTLED)
    ledger.add("link", "HRU-1 x3", "AHU-1", "S5", "HRU-1 x3 to AHU-1", "plans", SETTLED)
    ledger.add("link", "RTU-7", "EF-4 x5", "S5", "RTU-7 with EF-4 x5", "plans", SETTLED)     # not about the group
    job = _plan(ledger)
    _counts_hold(job)
    plant, hru = _by_key(job)["AHU-1 Plant"], _by_key(job)["HRU"]
    assert plant.families[1].count.value == 3
    assert hru.families[0].count.value in (9, 12)
    assert any("12" in q and "AHU-1 Plant" in q for q in job.questions)

    # (c) a group's damper family gives up a damper its fan claims: 3 per the schedule, 2 per the plans
    ledger = _ledger()
    _family(ledger, "EF", "Exhaust Fan", "EF-1", 1)
    count = _family(ledger, "MD", "Motorized Damper", "MD-1 thru 3", 3, source="S2")
    ledger.contradict(count.id, 2, "S5", "MD x2", "plans")
    ledger.add("group", "Shaft Ventilation", "EF, MD", "S5", "SHAFT VENTILATION", "risers", SETTLED)
    ledger.add("link", "MD-1", "EF-1", "S2", "MD-1 EF-1", "plans", SETTLED)
    job = _plan(ledger)
    _counts_hold(job)
    (shaft,) = job.systems
    own = next(f for f in shaft.families if f.tags == ("MD-2", "MD-3"))
    assert own.count.value == 2
    asked = [q for q in job.questions if "(MD)" in q and "3" in q]
    assert len(asked) == 1 and "2" in asked[0]

    # (d) a general-kind block gives up tags: 3 per the schedule, 2 per the plans, one per tag left
    ledger = _ledger()
    count = _family(ledger, "P", "Pump", "P-1, SPX-1, SPX-2", 3)
    ledger.contradict(count.id, 2, "S2", "P x2", "plans")
    _family(ledger, "SPX", "Sump Pump", "SPX-1, SPX-2", 2)
    job = _plan(ledger)
    _counts_hold(job)
    pump = _by_key(job)["P"].families[0]
    assert pump.tags == ("P-1",) and pump.count.value == 1
    asked = [q for q in job.questions if "SPX-1" in q and "general name" in q]
    assert len(asked) == 1 and "3" in asked[0] and "2 per" in asked[0]


# ---- tags a later pass adds to a family are kept (PLN-1) -----------------------------------------------------------

def test_tags_a_later_pass_adds_to_a_family_are_kept():
    # the schedule lists EF-1 thru 3 and counts 3; the plans pass contradicts the tag list with EF-1 thru 4
    ledger = _ledger()
    _family(ledger, "EF", "Exhaust Fan", "EF-1 thru 3", 3)
    unit = ledger.find("unit", "EF")
    ledger.contradict(unit.id, "EF-1 thru 4", "S2", "EF-1 EF-2 EF-3 EF-4", "plans")
    job = _plan(ledger)
    _counts_hold(job)
    (ef,) = job.systems
    (family,) = ef.families
    assert family.tags == ("EF-1", "EF-2", "EF-3", "EF-4")
    assert family.count.value >= 4
    assert 3 in {o.value for o in family.count.others}             # the old number is kept with its source
    asked = [q for q in job.questions if "EF-4" in q]
    assert len(asked) == 1 and "counted 4" in asked[0] and "lists 3" in asked[0]


def test_a_shorter_schedule_tag_list_keeps_the_seeds_plan_tags_in_the_plan():
    # LDG-4 through the planner: the seed's "VAV-1 thru 12" (scheduled and on the plans), the schedules pass's
    # "VAV-1 thru 10": VAV-11 and VAV-12 are still the family's tags
    from estimator.ledger.passes import apply, pass_named
    from estimator.ledger.seed import seed
    from tests.test_ledger_seed import _dossier as _seed_dossier

    ledger = seed(_seed_dossier())
    answer = {"facts": [{"kind": "unit", "subject": "VAV", "value": "VAV-1 thru 10", "source_id": "[S4]",
                         "quote": "VAV-1 thru VAV-10"}],
              "contradictions": [], "confirmations": [], "understanding": "Ten VAV boxes scheduled."}
    assert apply(pass_named("schedules"), ledger, answer, frozenset(ledger.sources) | frozenset(ledger.facts)) == []
    job = _plan(ledger)
    tags = _tags_in(job)
    assert {"VAV-11", "VAV-12"} <= tags
    vav = next(f for s in job.systems for f in s.families if "VAV-1" in f.tags)
    assert vav.count.value is None or vav.count.value >= 12
    assert any("VAV-11" in q and "10" in q for q in job.questions)


# ---- a tag names its own block; a VRF group stays whole; a clear name beats a prefix (PLN-4, 6, 7, 8) ------------

def test_a_link_exception_or_provider_naming_a_tag_lands_on_the_block_holding_that_tag():
    """A group holding EF-1 does not take what the documents say of EF-2: the block holding EF-2 does (PLN-4)."""
    ledger = _ledger()
    _family(ledger, "EF", "Exhaust Fan", "EF-1, EF-2", 2)
    _family(ledger, "AHU", "Air Handling Unit", "AHU-1", 1)
    _family(ledger, "MD", "Motorized Damper", "MD-1, MD-2", 2, source="S2")
    ledger.add("group", "AHU-1 Plant", "AHU, EF (EF-1)", "S5", "AHU-1 plant riser", "risers", SETTLED)
    ledger.add("link", "MD-1", "EF-2", "S2", "MD-1 at EF-2", "plans", SETTLED)
    ledger.add("note", "exception", "EF-2 controls by others", "S4", "EF-2 by others", "spec", SETTLED)
    ledger.add("provider", "EF-2", "furnished with the unit", "S4", "furnished with the unit", "spec", SETTLED)
    job = _plan(ledger)
    systems = _by_key(job)
    plant, ef = systems["AHU-1 Plant"], systems["EF"]
    assert [f.tags for f in plant.families] == [("EF-1",), ("AHU-1",)]
    assert [f.tags for f in ef.families] == [("EF-2",), ("MD-1",)]
    assert systems["MD"].families[0].tags == ("MD-2",)
    (exception,) = job.exceptions
    assert exception.system_key == "EF"
    assert ef.control == "packaged" and plant.control == "field"
    # a provider fact naming the family by its prefix alone still reaches every block of the family
    ledger.add("provider", "AHU", "factory controls by the unit manufacturer", "S4", "factory", "spec", SETTLED)
    assert _by_key(_plan(ledger))["AHU-1 Plant"].control == "packaged"


def test_a_vrf_group_with_indoor_and_outdoor_sections_stays_one_block():
    """A VRF group's indoor and outdoor units each matching a sequence section of their own are still one VRF block
    carrying both sections; the join is asked, naming every member (PLN-6)."""
    ledger = _ledger()
    _family(ledger, "CU", "VRF Condensing Unit", "CU-1", 1)
    _family(ledger, "FCU", "VRF Indoor Unit", "FCU-1 thru 4", 4)
    _family(ledger, "BS", "Branch Selector Box", "BS-1", 1)
    ledger.add("group", "VRF System", "CU, FCU, BS", "S5", "VRF riser", "risers", SETTLED)
    ledger.add("sequence_match", "VRF OUTDOOR UNITS", "CU", "Q1", "VRF OUTDOOR UNITS", "sequence", SETTLED)
    ledger.add("sequence_match", "VRF INDOOR UNITS", "FCU", "Q2", "VRF INDOOR UNITS", "sequence", SETTLED)
    job = _plan(ledger)
    (vrf,) = job.systems
    assert vrf.key == "VRF System" and vrf.shape == "VRF System" and vrf.control == "integration"
    assert {f.name for f in vrf.families} == {"Indoor Unit", "Condensing Unit", "Branch Selector"}
    assert {r.source_id for r in vrf.sequence_refs} == {"Q1", "Q2"}
    (asked,) = [q for q in job.questions if "VRF System" in q]
    assert all(p in asked for p in ("CU", "FCU", "BS")) and "onfirm" in asked


def test_a_group_split_apart_names_every_member_in_its_question():
    ledger = _ledger()
    _family(ledger, "RTU", "Rooftop Unit", "RTU-1", 1)
    _family(ledger, "EF", "Exhaust Fan", "EF-1", 1)
    _family(ledger, "UH", "Unit Heater", "UH-1", 1)
    ledger.add("group", "corridor air", "RTU, EF, UH", "S5", "corridor air", "risers", SETTLED)
    ledger.add("sequence_match", "ROOFTOP UNITS", "RTU", "Q5", "ROOFTOP UNITS", "sequence", SETTLED)
    ledger.add("sequence_match", "EXHAUST FANS", "EF", "Q1", "EXHAUST FANS", "sequence", SETTLED)
    job = _plan(ledger)
    assert [s.key for s in job.systems] == ["RTU", "EF", "UH"]
    (asked,) = [q for q in job.questions if "corridor air" in q]
    assert "RTU, EF, UH" in asked


def _with_shapes(*shapes):
    return dataclasses.replace(PLAYBOOK, shapes={**PLAYBOOK.shapes, **{s.name: s for s in shapes}})


def _shape(name, prefixes, kind_words):
    return Shape(name=name, prefixes=prefixes, kind_words=kind_words, header="{name}", family_names=(name,),
                 line_order=("comm",), slot_kinds={"comm": "wiring"}, wording={"comm": "{verb} {device}"},
                 tech_hours=TechHours("unit", 1.0))


def test_condensate_pumps_joining_a_lone_split_unit_keep_its_split_shape():
    """A lone split unit is its own block; condensate pumps of its number join it, and it keeps the split shape:
    only a block of condensate pumps alone never takes it (PLN-7)."""
    playbook = _with_shapes(_shape("Split System", ("AC", "ACCU"), ("split system",)))
    ledger = _ledger()
    _family(ledger, "AC", "Air Conditioning Unit", "AC-21", 1)
    _family(ledger, "CP", "Condensate Pump", "CP-21", 1)
    job = _plan(ledger, playbook)
    (ac,) = job.systems
    assert ac.key == "AC" and [f.tags for f in ac.families] == [("AC-21",), ("CP-21",)]
    assert ac.shape == "Split System"


def test_a_family_named_otherwise_is_not_gathered_by_prefix():
    """A Dehumidifier tagged DH is no duct heater, an Air Curtain tagged AC no split unit: a clear family name beats
    a prefix when the planner gathers blocks (PLN-8). A VRF indoor unit no group took is still a split unit."""
    playbook = _with_shapes(_shape("Air Curtain", ("ACU",), ("air curtain",)))
    ledger = _ledger()
    _family(ledger, "SS", "Indoor Unit", "SS-1", 1)
    _family(ledger, "ACCU", "Outdoor Unit", "ACCU-1", 1)
    _family(ledger, "IU", "VRF Indoor Unit", "IU-1", 1)
    _family(ledger, "AC", "Air Curtain", "AC-1", 1)
    _family(ledger, "EDH", "Electric Duct Heater", "EDH-1", 1)
    _family(ledger, "RH", "Reheat Duct Heater", "RH-1", 1)
    _family(ledger, "DH", "Dehumidifier", "DH-1", 1)
    systems = _by_key(_plan(ledger, playbook))
    assert [f.tags for f in systems["Split System"].families] == [("SS-1",), ("ACCU-1",), ("IU-1",)]
    assert [f.tags for f in systems["Duct Heaters"].families] == [("EDH-1",), ("RH-1",)]
    assert systems["AC"].families[0].tags == ("AC-1",)
    assert systems["DH"].families[0].tags == ("DH-1",)
    # a heater with only a general name still joins by its prefix
    ledger = _ledger()
    _family(ledger, "EDH", "Electric Duct Heater", "EDH-1", 1)
    _family(ledger, "DH", "Heater", "DH-1", 1)
    assert [f.tags for f in _by_key(_plan(ledger))["Duct Heaters"].families] == [("EDH-1",), ("DH-1",)]


def test_a_plant_group_with_a_condensing_boiler_and_a_fan_coil_is_still_split_apart():
    """Only a split, condensing or branch prefix makes a member a VRF or split system's outdoor unit (PLN-6)."""
    ledger = _ledger()
    _family(ledger, "B", "Condensing Boiler", "B-1", 1)
    _family(ledger, "FCU", "Fan Coil Unit", "FCU-1", 1)
    ledger.add("group", "Heating Plant", "B, FCU", "S5", "heating plant", "risers", SETTLED)
    ledger.add("sequence_match", "HEATING PLANT", "B", "Q2", "HEATING PLANT", "sequence", SETTLED)
    ledger.add("sequence_match", "ROOFTOP UNITS", "FCU", "Q5", "ROOFTOP UNITS", "sequence", SETTLED)
    assert [s.key for s in _plan(ledger).systems] == ["B", "FCU"]


def test_a_ducted_split_indoor_unit_scheduled_as_an_air_handling_unit_stays_a_split_unit():
    playbook = _with_shapes(_shape("Air Handling Unit", ("AHU",), ("air handling unit",)))
    ledger = _ledger()
    _family(ledger, "SS", "Air Handling Unit", "SS-1", 1)
    _family(ledger, "ACCU", "Outdoor Unit", "ACCU-1", 1)
    (split,) = _plan(ledger, playbook).systems
    assert split.key == "Split System"


def test_a_block_refused_by_its_name_takes_the_shape_its_name_gives_with_the_real_playbook():
    """PLN-8: an Air Curtain tagged AC is never a Split System, a Dehumidifier tagged DH never a Duct Heater; each
    takes the shape its name gives (or none). Real split units and duct heaters keep theirs."""
    playbook = load_playbook()
    ledger = _ledger()
    _family(ledger, "AC", "Air Curtain", "AC-1", 1)
    _family(ledger, "DH", "Dehumidifier", "DH-1", 1)
    _family(ledger, "SS", "Indoor Unit", "SS-1", 1)
    _family(ledger, "ACCU", "Outdoor Unit", "ACCU-1", 1)
    _family(ledger, "EDH", "Electric Duct Heater", "EDH-1", 1)
    systems = _by_key(_plan(ledger, playbook))
    assert systems["AC"].shape == "Air Curtain"
    assert systems["DH"].shape not in ("Duct Heater", "Split System")
    by_name = playbook.shape_for("Dehumidifier", [])
    assert systems["DH"].shape == (by_name.name if by_name is not None else "")
    assert systems["Split System"].shape == "Split System" and systems["EDH"].shape == "Duct Heater"

# ---- a group member's stated count in any form; a later group listing a family whole (PLN-9, PLN-11, PLN-12) -------

def _cuh_group(value: str) -> Job:
    ledger = _ledger()
    _family(ledger, "AHU", "Air Handling Unit", "AHU-1", 1)
    _family(ledger, "CUH", "Cabinet Unit Heater", "CUH-A, CUH-B", 6)
    ledger.add("group", "AHU-1 Plant", value, "S5", "AHU-1 PLANT riser", "risers", SETTLED)
    return _plan(ledger)


@pytest.mark.parametrize("value", ["AHU, CUH-A (TYP. OF 4)", "AHU, CUH (CUH-A (4))", "AHU, CUH-A 4 PLACES",
                                   "AHU, CUH-A x4", "AHU, CUH (CUH-Ax4)"])
def test_group_member_multiplier_forms(value):
    job = _cuh_group(value)
    systems = _by_key(job)
    plant = systems["AHU-1 Plant"]
    cuh = next(f for f in plant.families if f.name == "Cabinet Unit Heater")
    assert cuh.tags == ("CUH-A",) and cuh.count.value == 4
    assert systems["CUH"].families[0].tags == ("CUH-B",)
    _counts_hold(job)


def test_a_nested_bracket_member_listing_every_tag_takes_the_family():
    plant = _by_key(_cuh_group("AHU, CUH (CUH-A (4), CUH-B)"))
    assert "CUH" not in plant
    cuh = next(f for f in plant["AHU-1 Plant"].families if f.name == "Cabinet Unit Heater")
    assert cuh.tags == ("CUH-A", "CUH-B")


def test_a_group_member_naming_no_family_is_asked():
    job = _cuh_group("AHU, CUH (CUH-A x4), BOILER ROOM KIT")
    asked = [q for q in job.questions if "BOILER ROOM KIT" in q]
    assert len(asked) == 1 and "AHU-1 Plant" in asked[0]


def test_a_later_group_listing_a_family_whole_takes_the_untaken_tags():
    ledger = _ledger()
    _family(ledger, "AHU", "Air Handling Unit", "AHU-1", 1)
    _family(ledger, "RTU", "Rooftop Unit", "RTU-1", 1)
    _family(ledger, "EF", "Exhaust Fan", "EF-1 thru 3", 3)
    ledger.add("group", "AHU-1 Plant", "AHU, EF (EF-1)", "S5", "AHU-1 PLANT riser", "risers", SETTLED)
    ledger.add("group", "RTU-1 Plant", "RTU, EF", "S5", "RTU-1 PLANT riser", "risers", SETTLED)
    job = _plan(ledger)
    _counts_hold(job)
    systems = _by_key(job)
    assert "EF" not in systems
    ahu = next(f for f in systems["AHU-1 Plant"].families if f.name == "Exhaust Fan")
    rtu = next(f for f in systems["RTU-1 Plant"].families if f.name == "Exhaust Fan")
    assert ahu.tags == ("EF-1",) and rtu.tags == ("EF-2", "EF-3")
    assert ahu.count.value + rtu.count.value == 3
    asked = [q for q in job.questions if "AHU-1 Plant" in q and "RTU-1 Plant" in q and "(EF)" in q]
    assert asked and "3" in asked[0]


def test_a_stated_count_in_another_form_on_a_sheet_of_the_dossier_counts():
    ledger = _ledger()
    _family(ledger, "CUH", "Cabinet Unit Heater", "CUH-A")
    dossier = Dossier(job_name="Invented Job",
                      text=("[S2] CUH-A (TYP. OF 4)\n[D8] P-101, Drawings.pdf page 4 LEVEL 1: CUH-A 2 PLACES\n"
                            "[D9] P-102, Drawings.pdf page 5 LEVEL 2: CUH-A (450) NOTE 7\n"),   # over STATED_MOST
                      images=(), sources={"S2": SOURCES["S2"], "D8": "P-101, Drawings.pdf page 4 (sheet text)",
                                          "D9": "P-102, Drawings.pdf page 5 (sheet text)"},
                      families=(), device_totals={}, counts={}, stats={})
    count = plan_job(ledger, None, dossier, PLAYBOOK).systems[0].families[0].count
    assert count.value >= 4 and count.value == 6
    assert count.sources[0] == Ref("S2", "CUH-A (TYP. OF 4)", "M-101, Drawings.pdf page 2")


# ---- ruling L1 (ws23): stated counts on the plan sheets of one floor and area are not added ------------------------

def _sheet_dossier(*sheets) -> Dossier:
    """A dossier of 7c sheet-text lines, one per (number, page, title, text): "[Dn] M-101, Drawings.pdf page 3 TITLE:
    text", each with its source "M-101, Drawings.pdf page 3 (sheet text)"."""
    lines, sources = [], {}
    for n, (number, page, title, text) in enumerate(sheets, start=7):
        where = f"{number}, Drawings.pdf page {page}"
        lines.append(f"[D{n}] {where} {title}: {text}")
        sources[f"D{n}"] = f"{where} (sheet text)"
    return Dossier(job_name="Invented Job", text="\n".join(lines) + "\n", images=(), sources=sources, families=(),
                   device_totals={}, counts={}, stats={})


def _cuh_job(dossier: Dossier, count=None):
    ledger = _ledger()
    _family(ledger, "CUH", "Cabinet Unit Heater", "CUH-A, CUH-B", count)
    return plan_job(ledger, None, dossier, PLAYBOOK)


L2_DUCT = "LEVEL 2 HVAC DUCTWORK PLAN"
L2_PIPE = "LEVEL 2 HVAC PIPING PLAN"
L3_DUCT = "LEVEL 3 HVAC DUCTWORK PLAN"


def test_the_same_stated_count_on_two_sheets_of_one_floor_and_area_counts_once():
    dossier = _sheet_dossier(("M-101", 3, L2_DUCT, "CUH-A (TYP. OF 4) AT THE ENTRIES"),
                             ("M-201", 4, L2_PIPE, "CUH-A (TYP. OF 4) PIPED"))
    count = _cuh_job(dossier).systems[0].families[0].count
    assert count.value == 4                                              # the sheets added up gave 8
    assert [r.source_id for r in count.sources] == ["D7", "D8"]           # both sheets still cite it


def test_the_stated_counts_of_two_floors_add_up():
    dossier = _sheet_dossier(("M-101", 3, L2_DUCT, "CUH-A (TYP. OF 4)"), ("M-201", 4, L2_PIPE, "CUH-A (TYP. OF 4)"),
                             ("M-102", 5, L3_DUCT, "CUH-A (TYP. OF 4)"))
    assert _cuh_job(dossier).systems[0].families[0].count.value == 8      # level 2 once, level 3 once


def test_each_tag_counts_the_most_of_one_sheet_of_the_group_and_the_tags_add_up():
    dossier = _sheet_dossier(("M-101", 3, L2_DUCT, "CUH-A (TYP. OF 4) CUH-B x2"),
                             ("M-201", 4, L2_PIPE, "CUH-A (TYP. OF 3) CUH-B x5"))
    assert _cuh_job(dossier).systems[0].families[0].count.value == 4 + 5


def test_two_sheets_of_one_trade_and_one_title_could_be_the_halves_of_a_floor_so_their_counts_add_up():
    dossier = _sheet_dossier(("M-101", 3, L2_DUCT, "CUH-A (TYP. OF 4)"), ("M-102", 4, L2_DUCT, "CUH-A (TYP. OF 4)"))
    assert _cuh_job(dossier).systems[0].families[0].count.value == 8


def test_a_twin_sheet_that_states_nothing_still_stops_the_other_trades_sheet_from_being_one_plan():
    # the same floor drawn twice for ductwork (one of them states no count) and once for piping: which of the two the
    # piping plan shows is not known, so nothing is grouped (`plan_groups` sees every sheet of the dossier)
    dossier = _sheet_dossier(("M-101", 3, L2_DUCT, "CUH-A (TYP. OF 4)"), ("M-102", 4, L2_DUCT, "GENERAL NOTES ONLY"),
                             ("M-201", 5, L2_PIPE, "CUH-A (TYP. OF 4)"))
    assert _cuh_job(dossier).systems[0].families[0].count.value == 8


@pytest.mark.parametrize("title", ["LEVEL 2 HVAC DETAILS", "LEVEL 2 HVAC SCHEDULES", "LEVEL 2 HVAC RISER DIAGRAM"])
def test_a_sheet_that_is_no_plan_is_never_grouped_with_a_plan(title):
    dossier = _sheet_dossier(("M-101", 3, L2_DUCT, "CUH-A (TYP. OF 4)"), ("M-501", 4, title, "CUH-A (TYP. OF 4)"))
    assert _cuh_job(dossier).systems[0].families[0].count.value == 8


def test_a_line_that_is_no_sheet_text_is_never_grouped():
    dossier = Dossier(job_name="Invented Job", text="[S2] CUH-A (TYP. OF 4)\n[S4] CUH-A (TYP. OF 4)\n", images=(),
                      sources={"S2": SOURCES["S2"], "S4": SOURCES["S4"]}, families=(), device_totals={}, counts={},
                      stats={})
    assert _cuh_job(dossier).systems[0].families[0].count.value == 8


def test_the_drop_is_recorded_on_the_family_with_both_numbers_and_the_sheets():
    from bms.plan_read import AddedUp, Reader

    dossier = _sheet_dossier(("M-101", 3, L2_DUCT, "CUH-A (TYP. OF 4)"), ("M-201", 4, L2_PIPE, "CUH-A (TYP. OF 4)"),
                             ("M-102", 5, L3_DUCT, "CUH-A (TYP. OF 4)"))
    ledger = _ledger()
    _family(ledger, "CUH", "Cabinet Unit Heater", "CUH-A")
    reader = Reader(ledger, dossier.sources, dossier.text)
    family = reader.family_by_prefix("CUH")
    assert family.count.value == 8
    assert family.added_up == AddedUp(counted=8, summed=12, sheets=(("M-101", "M-201"),))
    nothing_lowered = _sheet_dossier(("M-101", 3, L2_DUCT, "CUH-A (TYP. OF 4)"), ("M-102", 5, L3_DUCT, "CUH-A (TYP. OF 4)"))
    assert Reader(ledger, nothing_lowered.sources, nothing_lowered.text).family_by_prefix("CUH").added_up is None


def test_a_count_lowered_by_the_rule_below_what_the_sheets_add_up_to_is_asked_with_both_numbers():
    dossier = _sheet_dossier(("M-101", 3, L2_DUCT, "CUH-A (TYP. OF 4)"), ("M-201", 4, L2_PIPE, "CUH-A (TYP. OF 4)"))
    job = _cuh_job(dossier)
    [asked] = [q for q in job.questions if "if the sheets were added up" in q]
    assert "Cabinet Unit Heater (CUH)" in asked and "M-101 and M-201 show one floor and area" in asked
    assert "4 counted, 8 if the sheets were added up" in asked


def test_the_dossiers_own_counts_line_is_not_read_as_a_stated_count():
    # its reading note says "CUH-A 4 places, 4 on M-101" (a type tag's placements), which reads like a stated count
    # ("CUH-A 4 PLACES"), but those placements are the two sheets' counts again, not more units
    counts_line = ("[S1] CUH (Cabinet Unit Heater): schedule rows 0; plan placements 4 (M-101 4; M-201 4); riser —; "
                   "placements above the other counts, likely: a typical unit at each place. Tags: CUH-A. Reading "
                   "notes: the 4 placements on the plans are above the other counts: CUH-A 4 places, 4 on M-101 — "
                   "likely a typical unit placed at each place: check the schedule's quantity.")
    sheets = _sheet_dossier(("M-101", 3, L2_DUCT, "CUH-A (TYP. OF 4)"), ("M-201", 4, L2_PIPE, "CUH-A (TYP. OF 4)"))
    dossier = dataclasses.replace(sheets, text=counts_line + "\n" + sheets.text,
                                  sources={**sheets.sources, "S1": SOURCES["S1"].replace("FAN", "CUH")})
    count = _cuh_job(dossier).systems[0].families[0].count
    assert count.value == 4
    assert [r.source_id for r in count.sources] == ["D7", "D8"]


def test_the_rule_reads_the_sheet_text_lines_the_dossier_builder_writes(tmp_path):
    # the line shape `_plan_sheet` reads is the one `build_dossier` writes in 7c, not only the one these tests invent
    import sys

    from bms.plan_read import AddedUp, Reader

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from estimator.writing.dossier import build_dossier
    from test_dossier_plan_areas import DWG, _catalogue, _page, _reading, _sheet

    pages = [_page(DWG, 1, "CUH-A (TYP. OF 4)"), _page(DWG, 2, "CUH-A (TYP. OF 4)")]
    sheets = [_sheet(1, "M-101", L2_DUCT), _sheet(2, "M-201", L2_PIPE)]
    built = build_dossier(_catalogue(pages, sheets, ["CUH-A"]), _reading(), tmp_path)
    ledger = _ledger()
    _family(ledger, "CUH", "Cabinet Unit Heater", "CUH-A")
    family = Reader(ledger, built.sources, built.text).family_by_prefix("CUH")
    assert family.count.value == 4
    assert family.added_up == AddedUp(4, 8, (("M-101", "M-201"),))


def test_no_question_when_the_printed_count_is_not_below_what_the_sheets_add_up_to():
    dossier = _sheet_dossier(("M-101", 3, L2_DUCT, "CUH-A (TYP. OF 4)"), ("M-201", 4, L2_PIPE, "CUH-A (TYP. OF 4)"))
    job = _cuh_job(dossier, count=9)                                      # a schedule quantity above the sum prints
    assert job.systems[0].families[0].count.value == 9
    assert not any("if the sheets were added up" in q for q in job.questions)
