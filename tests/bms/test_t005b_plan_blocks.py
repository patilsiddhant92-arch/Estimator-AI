"""T-005b: blocks and questions of the planner (estimator rulings 8, 9 and 11 of 2026-10-11, and the T-005 addendum).

- Control valves go under the unit they serve, tied by a tag reference, a schedule's "serves" column or plan
  proximity text; a valve nothing ties is asked about (and stays in a block until answered: a count is never lost).
- Pumps are their own blocks split by service (chilled water, hot water), each with its own shape lookup.
- A count question is asked once per family.
- Demolition work the documents give the controls contractor reaches the block it is about (the writer prints it as
  a removal line); work naming no block is asked.
- A unit the documents put off the BMS is asked about before its valves and sensors print.
Every ledger here is invented."""
from __future__ import annotations

import dataclasses
from pathlib import Path

from estimator.ledger.facts import SETTLED, Ledger
from estimator.writing.dossier import Dossier

from bms.model import Count, Job, Ref
from bms.plan import plan_job
from bms.playbook import Shape, TechHours, load_playbook

PLAYBOOK = load_playbook(Path(__file__).parent / "fixtures" / "sample_playbook")

SOURCES = {
    "S1": "M-101, Drawings.pdf page 2 (sheet text)",
    "S2": "M-501, Drawings.pdf page 6 (schedule)",
    "S3": "M-601, Drawings.pdf page 9 (control diagram)",
    "S4": "23 09 00, Specs.pdf page 4",
    "S5": "MD-101, Drawings.pdf page 12 (demolition plan)",
    "Q1": "sequence section “CHILLED WATER PUMPS”, Specs.pdf page 40",
    "Q2": "sequence section “A. General”, Specs.pdf page 40",
    "Q3": "sequence section “HOT WATER PUMPS”, Specs.pdf page 41",
    "Q4": "sequence section “A. General”, Specs.pdf page 41",
    "Q5": "sequence section “PUMP ALARMS”, Specs.pdf page 42",
}


def _shape(name, prefixes, kind_words):
    return Shape(name=name, prefixes=prefixes, kind_words=kind_words, header="{name}", family_names=(name,),
                 line_order=("comm",), slot_kinds={"comm": "wiring"}, wording={"comm": "{verb} {device}"},
                 tech_hours=TechHours("unit", 1.0))


PLANT = dataclasses.replace(PLAYBOOK, shapes={
    **PLAYBOOK.shapes,
    "Chilled Water System": _shape("Chilled Water System", ("CHWP",), ("chilled water plant", "chilled water system")),
    "Hot Water System": _shape("Hot Water System", ("HWP",), ("hot water plant", "boiler plant")),
    "Air Handling Unit": _shape("Air Handling Unit", ("AHU",), ("air handling unit",)),
})


def _dossier(text: str = "", sources: dict | None = None) -> Dossier:
    return Dossier(job_name="Invented Job", text=text, images=(), sources=sources or {}, families=(),
                   device_totals={}, counts={}, stats={})


def _ledger() -> Ledger:
    ledger = Ledger(SOURCES)
    ledger.job_name = "Invented Job"
    ledger.add("front_end", "mode", "new-system", "S4", "provide a new building automation system", "spec", SETTLED)
    ledger.add("front_end", "line", "Furnish an operator workstation", "S4", "provide one operator workstation",
               "spec", SETTLED)
    return ledger


def _family(ledger, prefix, name, tags=None, count=None, source="S2"):
    ledger.add("family", prefix, name, source, f"{prefix} {name}", "schedules", SETTLED)
    if tags:
        ledger.add("unit", prefix, tags, source, f"Tags: {tags}", "schedules", SETTLED)
    if count is not None:
        return ledger.add("count", prefix, count, source, f"{prefix} rows {count}", "schedules", SETTLED)
    return None


def _plan(ledger: Ledger, playbook=PLAYBOOK, dossier: Dossier | None = None) -> Job:
    return plan_job(ledger, None, dossier or _dossier(), playbook)


def _by_key(job: Job) -> dict:
    return {s.key: s for s in job.systems}


def _units(ledger) -> None:
    _family(ledger, "AHU", "Air Handling Unit", "AHU-1 thru 2", 2)
    _family(ledger, "ERV", "Energy Recovery Ventilator", "ERV-1", 1)


# ---- ruling 8: control valves under the unit they serve ----------------------------------------------------------

def test_valves_a_fact_ties_to_a_unit_by_tag_reference_go_under_that_unit():
    ledger = _ledger()
    _units(ledger)
    _family(ledger, "CV", "Control Valve", "CV-1 thru 3", 3)
    ledger.add("device", "AHU heating and cooling valve outputs (CV-1 thru 2)", 2, "S3", "HEATING VALVE", "details",
               SETTLED)
    ledger.add("device", "ERV coil valve output (CV-3) and freezestat", 1, "S3", "AO COOLING VALVE", "details", SETTLED)
    job = _plan(ledger, PLANT)
    systems = _by_key(job)
    assert list(systems) == ["AHU", "ERV"]                         # no Control Valve block of its own
    ahu, erv = systems["AHU"], systems["ERV"]
    assert [(f.name, f.tags) for f in ahu.families] == [("Air Handling Unit", ("AHU-1", "AHU-2")),
                                                        ("Control Valve", ("CV-1", "CV-2"))]
    assert ahu.families[1].count == Count(2, (Ref("S3", "HEATING VALVE", "M-601, Drawings.pdf page 9"),))
    assert [(f.name, f.tags, f.count.value) for f in erv.families][1] == ("Control Valve", ("CV-3",), 1)
    assert not any("CV-" in q for q in job.questions)


def test_a_valve_schedules_serves_column_ties_the_valve_to_its_unit():
    text = "\n".join(["== 4. SCHEDULES ==",
                      "[S7] CONTROL VALVE SCHEDULE — M-501, Drawings.pdf page 6 (2 rows)",
                      "    Columns: TAG | SERVES | SIZE",
                      "[S8] CV-1 | AHU-1 | 2 IN",
                      "[S9] CV-2 | ERV-1 | 1 IN"])
    sources = {"S8": "CONTROL VALVE SCHEDULE row CV-1, M-501, Drawings.pdf page 6",
               "S9": "CONTROL VALVE SCHEDULE row CV-2, M-501, Drawings.pdf page 6"}
    ledger = _ledger()
    _units(ledger)
    _family(ledger, "CV", "Control Valve", "CV-1, CV-2", 2)
    systems = _by_key(_plan(ledger, PLANT, _dossier(text, sources)))
    assert list(systems) == ["AHU", "ERV"]
    assert systems["AHU"].families[1].tags == ("CV-1",)
    assert systems["AHU"].families[1].count.sources[0].source_id == "S8"
    assert systems["ERV"].families[1].tags == ("CV-2",)


def test_plan_proximity_text_and_a_tag_holding_the_units_tag_tie_valves_too():
    ledger = _ledger()
    _units(ledger)
    _family(ledger, "CV", "Control Valve", "CV-1, CV-AHU-2", 2)
    ledger.add("location", "CV-1", "at the AHU-1 heating coil", "S1", "CV-1 AT AHU-1 HTG COIL", "plans", SETTLED)
    systems = _by_key(_plan(ledger, PLANT))
    assert list(systems) == ["AHU", "ERV"]
    assert systems["AHU"].families[1].tags == ("CV-1", "CV-AHU-2") and systems["AHU"].families[1].count.value == 2


def test_a_valve_nothing_ties_is_asked_and_its_count_is_kept():
    ledger = _ledger()
    _units(ledger)
    _family(ledger, "CV", "Control Valve", "CV-1 thru 4", 4)
    ledger.add("device", "AHU heating valve output (CV-1)", 1, "S3", "HEATING VALVE", "details", SETTLED)
    ledger.add("note", "CV-2", "serves AHU-1 and ERV-1", "S1", "CV-2 AHU-1 / ERV-1", "plans", SETTLED)  # two units
    job = _plan(ledger, PLANT)
    systems = _by_key(job)
    assert systems["AHU"].families[1].tags == ("CV-1",)
    left = systems["CV"].families[0]
    assert left.tags == ("CV-2", "CV-3", "CV-4") and left.count.value == 3       # 4 less the one placed: never lost
    (asked,) = [q for q in job.questions if "CV-2" in q]
    assert "CV-2 thru 4" in asked and "which unit" in asked.lower() and "more than one unit" in asked


def test_valves_counted_by_type_move_whole_only_when_they_all_serve_one_unit():
    ledger = _ledger()
    _units(ledger)
    _family(ledger, "CV", "Control Valve", "CV-A", 6)               # one type tag, six valves
    ledger.add("device", "AHU coil valves (CV-A)", 6, "S3", "CV-A TYP", "details", SETTLED)
    systems = _by_key(_plan(ledger, PLANT))
    assert list(systems) == ["AHU", "ERV"]
    assert systems["AHU"].families[1].tags == ("CV-A",) and systems["AHU"].families[1].count.value == 6


def test_a_balancing_valve_is_no_control_valve():
    ledger = _ledger()
    _units(ledger)
    _family(ledger, "BV", "Balancing Valve", "BV-1", 1)
    ledger.add("location", "BV-1", "at AHU-1", "S1", "BV-1 AHU-1", "plans", SETTLED)
    assert "BV" in _by_key(_plan(ledger, PLANT))


def test_valves_under_a_unit_the_documents_put_off_the_bms_are_asked():
    ledger = _ledger()
    _family(ledger, "FCU", "Fan Coil Unit", "FCU-1 thru 3", 3)
    _family(ledger, "CV", "Control Valve", "CV-1 thru 3", 3)
    ledger.add("device", "FCU valves (CV-1 thru 3)", 3, "S3", "FCU 2-WAY VALVE", "details", SETTLED)
    ledger.add("note", "FCU", "FCUs run on a remote wall thermostat; no BMS points are listed", "S4",
               "FAN COIL UNITS: STAND-ALONE THERMOSTAT", "spec", SETTLED)
    job = _plan(ledger, PLANT)
    fcu = _by_key(job)["FCU"]
    assert fcu.families[1].tags == ("CV-1", "CV-2", "CV-3")
    (asked,) = [q for q in job.questions if "not on the BMS" in q]
    assert "FCU" in asked and "CV-1" in asked and "23 09 00" in asked and "pipe" in asked


def test_a_unit_off_the_bms_is_asked_even_with_no_valves():
    ledger = _ledger()
    _family(ledger, "FCU", "Fan Coil Unit", "FCU-1 thru 3", 3)
    ledger.add("provider", "FCU", "stand-alone thermostat by the unit manufacturer, not connected to the BMS", "S4",
               "NOT CONNECTED TO BMS", "spec", SETTLED)
    job = _plan(ledger, PLANT)
    assert sum("not on the BMS" in q for q in job.questions) == 1


# ---- ruling 9: pumps split by service ---------------------------------------------------------------------------

def _pumps(ledger, tags="P-1 thru 4", count=4) -> None:
    _family(ledger, "P", "Pump", tags, count)
    ledger.add("sequence_match", "SEQUENCE OF OPERATION - CHILLED WATER PUMPS, P-1,3", "P", "Q1",
               "CHILLED WATER PUMPS, P-1,3", "sequence", SETTLED)
    ledger.add("sequence_match", "A. General:", "P", "Q2", "A. General:", "sequence", SETTLED)
    ledger.add("sequence_match", "SEQUENCE OF OPERATION - HOT WATER PUMPS, P-2,4", "P", "Q3",
               "HOT WATER PUMPS, P-2,4", "sequence", SETTLED)
    ledger.add("sequence_match", "A. General:", "P", "Q4", "A. General:", "sequence", SETTLED)


def test_pumps_split_by_service_each_with_its_own_shape_and_sequence():
    ledger = _ledger()
    _pumps(ledger)
    job = _plan(ledger, PLANT)
    chw, hw = job.systems
    assert (chw.name, chw.shape, chw.families[0].name, chw.families[0].tags) == (
        "Chilled Water Pump", "Chilled Water System", "Chilled Water Pump", ("P-1", "P-3"))
    assert (hw.name, hw.shape, hw.families[0].name, hw.families[0].tags) == (
        "Hot Water Pump", "Hot Water System", "Hot Water Pump", ("P-2", "P-4"))
    assert chw.families[0].count.value == 2 and hw.families[0].count.value == 2
    assert chw.key != hw.key
    assert [r.source_id for r in chw.sequence_refs] == ["Q1", "Q2"]
    assert [r.source_id for r in hw.sequence_refs] == ["Q3", "Q4"]
    assert not any("P-" in q for q in job.questions)


def test_a_schedule_row_gives_a_pumps_service():
    text = "\n".join(["== 4. SCHEDULES ==",
                      "[S7] PUMP SCHEDULE — M-501, Drawings.pdf page 6 (2 rows)",
                      "    Columns: TAG | SERVICE | GPM",
                      "[S8] P-1 | CHILLED WATER | 300",
                      "[S9] P-2 | HEATING HOT WATER | 200"])
    ledger = _ledger()
    _family(ledger, "P", "Pump", "P-1, P-2", 2)
    job = _plan(ledger, PLANT, _dossier(text, {}))
    assert [(s.name, s.families[0].tags) for s in job.systems] == [("Chilled Water Pump", ("P-1",)),
                                                                   ("Hot Water Pump", ("P-2",))]


def test_pumps_of_one_service_take_its_name_and_shape():
    ledger = _ledger()
    _family(ledger, "P", "Pump", "P-1, P-2", 2)
    ledger.add("sequence_match", "CHILLED WATER PUMPS P-1, P-2", "P", "Q1", "CHILLED WATER PUMPS", "sequence", SETTLED)
    (chw,) = _plan(ledger, PLANT).systems
    assert (chw.name, chw.shape, chw.families[0].tags) == ("Chilled Water Pump", "Chilled Water System", ("P-1", "P-2"))


def test_a_pump_with_no_service_stays_and_is_asked():
    ledger = _ledger()
    _pumps(ledger, "P-1 thru 5", 5)
    ledger.add("sequence_match", "PUMP ALARMS", "P", "Q5", "PUMP ALARMS", "sequence", SETTLED)
    job = _plan(ledger, PLANT)
    names = [s.name for s in job.systems]
    assert names[:2] == ["Chilled Water Pump", "Hot Water Pump"]
    rest = job.systems[2]
    assert rest.families[0].tags == ("P-5",)
    assert any("P-5" in q and "service" in q for q in job.questions)
    # a section that says no service is read by every pump block
    assert all("Q5" in [r.source_id for r in s.sequence_refs] for s in job.systems)


def test_condensate_pumps_are_never_split_by_service():
    ledger = _ledger()
    _family(ledger, "CP", "Condensate Pump", "CP-1", 1)
    ledger.add("note", "CP-1", "drains the chilled water coil pan", "S1", "CP-1 CHW COIL", "plans", SETTLED)
    (cp,) = _plan(ledger, PLANT).systems
    assert cp.name == "Condensate Pump"


# ---- ruling 11: a count question once per family ------------------------------------------------------------------

def test_count_questions_on_one_family_are_one_question():
    from bms.plan import one_count_question_per_family
    questions = ["Air Handling Unit (AHU): M-501 lists 5 (AHU-1 thru 5); AHU-6 is also on M-101; counted 6 (the count "
                 "gave 5), confirm the count.",
                 "Exhaust Fan (EF): something else; confirm the count.",
                 "Air Handling Unit (AHU): the highest count is 6 per M-101; 21 if every sheet is added up; confirm the "
                 "count.",
                 "What is the existing BMS?"]
    merged = one_count_question_per_family(questions)
    assert len(merged) == 3
    assert merged[0].startswith("Air Handling Unit (AHU): M-501 lists 5") and "21 if every sheet" in merged[0]
    assert merged[0].count("confirm the count") == 1
    assert merged[1:] == questions[1:2] + questions[3:]


# ---- addendum: demolition work reaches its block ------------------------------------------------------------------

def test_demolition_work_on_a_unit_reaches_its_block_and_work_naming_none_is_asked():
    ledger = _ledger()
    _family(ledger, "FCU", "Fan Coil Unit", "FCU-1 thru 3", 3)
    remove = ledger.add("note", "FCU", "Existing FCUs and associated controls are removed and disposed of", "S5",
                        "REMOVE AND DISPOSE OF EXISTING FAN COIL UNIT AND ASSOCIATED CONTROLS.", "plans", SETTLED)
    ledger.add("note", "general", "Obsolete controls at the existing temperature control center are removed", "S5",
               "REMOVE OBSOLETE CONTROLS AT THE EXISTING TCMC.", "plans", SETTLED)
    ledger.add("note", "FCU", "Existing ductwork is removed", "S5", "REMOVE EXISTING DUCTWORK.", "plans", SETTLED)
    job = _plan(ledger, PLANT)
    (fcu,) = job.systems
    assert [r.source_id for r in fcu.sequence_refs] == ["S5"]
    assert fcu.sequence_refs[0].quote == remove.quote
    (asked,) = [q for q in job.questions if "TCMC" in q]
    assert "removal" in asked and "MD-101" in asked
    assert not any("DUCTWORK" in q for q in job.questions)
