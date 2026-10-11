"""T-005d (rulings 6, 7, 10 of 2026-10-11 and the coverage addendum): what reaches the writer and what its intake
does with marks, stated facts and long flags. Invented fixtures only; no AI is asked (a fake transport answers).

Found on the 26-0544 run: the control diagram sheet (its FUTURE sensors, the outside air sensor) reached no writer,
because every plan sheet "named" the air handlers through the project title in its title block and the notes block
was full before the diagram's turn; the general notes sheet's BMS notes were cut off at 8,000 characters."""
from __future__ import annotations

import copy
import dataclasses
import inspect
from pathlib import Path

import pytest

from estimator.ledger.facts import Fact
from estimator.writing import dossier as dossier_module
from estimator.writing.dossier import Dossier

from bms import ai, ai_evidence
from bms.model import Count, Family, FrontEnd, System, json_schema
from bms.playbook import load_playbook

FIXTURES = Path(__file__).resolve().parent / "fixtures"

TITLE_BLOCK = "COUNTY OF INVENTED REPLACEMENT OF AIR HANDLING UNITS AT THE INVENTED HALL"
FILLER = " ".join(["lorem ipsum dolor sit amet consectetur"] * 70)          # about 2,700 characters, no tag


def _plan_sheet(sid: int, number: str, page: int) -> str:
    return (f"[S{sid}] {number}, Plans.pdf page {page} MECHANICAL CONSTRUCTION PLAN: {TITLE_BLOCK} {FILLER} "
            f"KEY NOTE 3 CONNECT AHU-1 CONDENSATE TO FLOOR DRAIN {FILLER}")


TEXT_LINES = [
    "JOB DOSSIER — Invented Hall",
    "== 1. JOB ==",
    "[S1] Who does what (by the Owner) — “The owner furnishes the network switches.”",
    "[S2] Service: Shop drawings — “Any installing contractor not listed as prequalified in the Approved Integrator's "
    "section shall submit credentials.”",
    "== 2. SEQUENCE OF OPERATION ==",
    "--- 23 09 93, Specs.pdf page 4 ---",
    "--- [Q1] A. AIR HANDLING UNIT AHU-1 ---",
    "[S3] A. AIR HANDLING UNIT AHU-1",
    "[S4] The BMS shall modulate the supply fan VFD of AHU-1 to hold the duct static pressure set point.",
    "[S5] C. Training of the Owner's personnel in the operation of all system controls.",
    "== 4. SCHEDULES ==",
    "[S10] AIR HANDLING UNITS — M-601, Plans.pdf page 6 (1 row)",
    "    Columns: TAG | CFM",
    "[S11] AHU-1 | 5000",
    "[S12] Note: 1. DRAIN PAN LEVEL SENSOR.",
    "[S13] Note: 2. DISCHARGE AIR TEMPERATURE SENSOR - MOUNTED IN SUPPLY DUCT.",
    "[S14] Note: 3. SPACE SENSOR SHIPPED LOOSE FOR FIELD INSTALLATION.",
    "[S15] Note: 4. UNIT-MOUNTED NON-FUSED DISCONNECT SWITCH.",
    "[S16] Note: 5. CONTROLLER FURNISHED BY THE CONTROLS CONTRACTOR FOR FACTORY MOUNTING.",
    "== 7. NOTES ==",
    "[S20] KEY NOTES 1: EXTEND AHU-1 CONDENSATE TO THE NEAREST DRAIN.",
    "[S21] KEY NOTES 1: EXTEND AHU-1 CONDENSATE TO THE NEAREST DRAIN.",
    "--- 7c PLAN SHEET TEXT ---",
    "(Each mechanical, controls and plumbing sheet's own text, as printed.)",
    f"[S30] M-001, Plans.pdf page 1 MECHANICAL GENERAL NOTES: {TITLE_BLOCK} {FILLER} BUILDING MANAGEMENT SYSTEM (BMS) "
    "NOTES: 1. INTEGRATE NEW HVAC EQUIPMENT INTO THE EXISTING ACME CONTROLS BMS VIA BACNET.",
    f"[S31] M-100, Plans.pdf page 2 MECHANICAL BASEMENT PLAN: {TITLE_BLOCK} {FILLER}",
    _plan_sheet(32, "M-101", 3),
    _plan_sheet(33, "M-102", 4),
    _plan_sheet(34, "M-103", 5),
    _plan_sheet(35, "M-104", 6),
    _plan_sheet(36, "M-105", 7),
    "[S40] M-701, Plans.pdf page 9 MECHANICAL CONTROL DIAGRAMS: AHU-1 Control Schematic SUPPLY FAN VFD SPEED AO "
    "FREEZESTAT BI SUPPLY AIR DUCT DPS H L [FUTURE] SUPPLY AIR STATIC PRESSURE AI LOCATED 3/4 DISTANCE DOWN LONGEST "
    "DUCT RUN INSTALL OUTDOOR AIR TEMPERATURE SENSOR ON NORTH FACE OF PENTHOUSE WALL",
]
SECTIONS = {"Q1": ("A. AIR HANDLING UNIT AHU-1", ("S3", "S4", "S5"))}


@pytest.fixture
def dossier() -> Dossier:
    return Dossier("Invented Hall", "\n".join(TEXT_LINES) + "\n", (), {}, (), {}, {}, {}, SECTIONS)


@pytest.fixture
def playbook():
    return load_playbook(FIXTURES / "sample_playbook")


def ahu() -> System:
    return System(key="AHU", name="Air Handling Units", shape="", control="field",
                  families=(Family("Air Handling Unit", ("AHU-1",), Count(1)),), sequence_refs=())


class FakeTransport:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.asked: list[dict] = []
        self.waiting = 0
        self.notes: list[tuple[str, str]] = []

    def ask(self, kind, name, instructions, system_prompt, prompt, schema, extra=None, images=()):
        self.asked.append(dict(prompt=prompt, schema=schema, system_prompt=system_prompt))
        if not self.answers:
            raise ai.NoAnswer("no answer queued", waiting=True)
        return copy.deepcopy(self.answers.pop(0))

    def note_intake(self, name, change):
        self.notes.append((name, change))


def _device(n: int, name: str, sid: str, quote: str, where: str, **more) -> dict:
    device = {"id": f"AHU.d{n}", "slot": "sensor", "name": name, "verb": "Furnish and Install",
              "furnished_by": "AME", "installed_by": "AME", "wired_by": "AME",
              "quantity": {"value": 1, "sources": [], "others": [], "added_up": None},
              "refs": [{"source_id": sid, "quote": quote, "where": where}], "assumption": None, "flag": "none",
              "mark": "", "mark_note": ""}
    device.update(more)
    return device


def _answer(*devices, clarifications=()) -> dict:
    data = ahu().to_dict()
    data.update(devices=list(devices), clarifications=list(clarifications), tech_hours=None, no_scope_reason=None)
    return data


FUTURE_SENSOR = ("Supply Air Static Pressure Sensor", "S40", "[FUTURE] SUPPLY AIR STATIC PRESSURE",
                 "M-701, Plans.pdf page 9")


def _write(dossier, playbook, *answers, system=None):
    system = system or ahu()
    transport = FakeTransport(*answers)
    written = ai.write_system(system, ai.evidence_for(system, dossier), playbook, transport)
    return written, transport


# ---- the evidence: the control diagram and the BMS notes reach the writer ----------------------------------------

def test_the_control_diagram_sheet_reaches_the_writer_before_the_plan_sheets(dossier):
    text = ai.evidence_for(ahu(), dossier)
    assert "[S40] M-701" in text and "[FUTURE] SUPPLY AIR STATIC PRESSURE" in text
    controls = text.split("Controls sheets that name it", 1)[1].split("Notes that name it:", 1)[0]
    assert "[S40] M-701" in controls and "[S32]" not in controls    # the controls sheet first, whole, own block
    assert text.index("Controls sheets that name it") < text.index("[S32]")


def test_a_title_block_phrase_does_not_make_a_plan_sheet_name_a_tagged_system(dossier):
    text = ai.evidence_for(ahu(), dossier)
    assert "[S31]" not in text                                  # only the project title names air handling units


def test_a_long_plan_sheet_text_is_given_as_excerpts_about_the_system(dossier):
    text = ai.evidence_for(ahu(), dossier)
    line = next(l for l in text.splitlines() if l.startswith("[S32]"))
    assert "(excerpts about it)" in line and "CONNECT AHU-1 CONDENSATE TO FLOOR DRAIN" in line
    assert len(line) < 1_500
    index = ai._sent_index(text)                                # a quote from an excerpt passes the intake
    assert ai.quote_in("CONNECT AHU-1 CONDENSATE TO FLOOR DRAIN", index["S32"])
    full = ai.evidence_index(dossier)                           # and the QC's check of the whole source
    assert ai.quote_in("CONNECT AHU-1 CONDENSATE TO FLOOR DRAIN", full["S32"])


def test_every_plan_sheet_that_names_the_system_fits_the_notes_block(dossier):
    text = ai.evidence_for(ahu(), dossier)
    assert all(f"[S{n}]" in text for n in range(32, 37))
    assert "more passages name it" not in text


def test_a_note_repeated_word_for_word_is_given_once(dossier):
    text = ai.evidence_for(ahu(), dossier)
    assert "[S20]" in text and "[S21]" not in text


def test_the_future_items_are_listed_for_the_writer(dossier):
    text = ai.evidence_for(ahu(), dossier)
    part = text.split("Items its passages mark FUTURE", 1)[1]
    assert part.splitlines()[1].startswith("[S40] “") and "[FUTURE] SUPPLY AIR STATIC PRESSURE" in part
    assert "FUTURE AS PER" in text


def test_the_end_devices_of_the_unit_schedule_are_listed(dossier):
    text = ai.evidence_for(ahu(), dossier)
    part = text.split("End devices its unit schedules list", 1)[1]
    loose = next(l for l in part.splitlines() if l.startswith("- shipped loose"))
    listed = next(l for l in part.splitlines() if l.startswith("- names an end device"))
    assert "S13" in loose and "S14" in loose
    assert "S12" in listed and "notice" in listed
    assert "S15" not in part                                    # a disconnect switch is no end device


def test_the_stated_ids_are_the_sequence_and_schedule_passages(dossier):
    stated = ai_evidence.stated_ids(ai.evidence_for(ahu(), dossier))
    assert {"S4", "S11", "S12", "S16"} <= stated and "S40" not in stated and "S20" not in stated


def _ledger():
    class Ledger:
        pass
    ledger = Ledger()
    ledger.sources = {"S40": "M-701, Plans.pdf page 9 (sheet text)", "S5": "23 09 93, Specs.pdf page 4",
                      "S99": "M-702, Plans.pdf page 10"}
    ledger.facts = {
        "F1": Fact("F1", "device", "outdoor air temperature sensor", "AHU-1", "S40",
                   "INSTALL OUTDOOR AIR TEMPERATURE SENSOR ON NORTH FACE OF PENTHOUSE WALL", "details"),
        "F2": Fact("F2", "device", "pump start/stop", "P-1", "S99", "PUMP START/ STOP", "details"),
        "F3": Fact("F3", "front_end", "training", None, "S5",
                   "Training of the Owner's personnel in the operation of all system controls", "spec"),
        "F4": Fact("F4", "note", "a free note", "AHU-1", "S40", "AHU-1 Control Schematic", "details"),
    }
    return ledger


def test_the_controls_facts_of_the_system_are_a_checklist(dossier):
    text = ai.system_evidence(ahu(), dossier, _ledger())
    part = text.split("Controls facts the reading found about it", 1)[1]
    assert "[S40] “INSTALL OUTDOOR AIR TEMPERATURE SENSOR ON NORTH FACE OF PENTHOUSE WALL” — M-701, Plans.pdf page 9" \
        in part and "read as: device outdoor air temperature sensor = AHU-1" in part
    assert "PUMP START" not in part and "Training" not in part and "a free note" not in part
    assert ai.evidence_for(ahu(), dossier) == ai.system_evidence(ahu(), dossier)     # no ledger: no checklist


def test_the_front_end_gets_its_facts_its_bms_notes_training_and_the_integrator_passage(dossier):
    front = FrontEnd(mode="extend-existing", existing_system_name="Acme Controls", lines=("graphics",))
    text = ai.front_end_evidence(front, dossier, (), _ledger())
    assert "INTEGRATE NEW HVAC EQUIPMENT INTO THE EXISTING ACME CONTROLS BMS VIA BACNET" in text      # past 2,700
    assert "[S5] C. Training" in text and "[S2]" in text and "prequalified" in text
    facts = text.split("Controls facts the reading found about it", 1)[1]
    assert "read as: front end training" in facts and "OUTDOOR AIR" not in facts


def test_the_run_writes_from_the_evidence_with_the_ledger():
    from bms import run
    source = inspect.getsource(run._estimate)
    assert "ai.system_evidence(s, dossier, ledger)" in source
    assert "ai.front_end_evidence(job.front_end, dossier, taken, ledger)" in source


def test_a_plan_sheet_text_is_not_cut_at_8000_characters():
    assert dossier_module.PLAN_TEXT_LIMIT >= 20_000

    class Sheet:
        document, page, number, title = "Plans.pdf", 1, "M-001", "GENERAL NOTES"

    text = FILLER * 4 + " BMS NOTES: 1. INTEGRATE INTO THE EXISTING BMS."          # about 11,000 characters
    lines = dossier_module._sheet_text_lines({("Plans.pdf", 1): Sheet()}, {("Plans.pdf", 1): text},
                                             dossier_module._Ids(), dossier_module._SheetText(), "more sheet")
    assert "INTEGRATE INTO THE EXISTING BMS" in lines[0]


# ---- the intake: marks (ruling 7) --------------------------------------------------------------------------------

def test_a_line_quoting_a_future_passage_is_marked_future_with_its_source(dossier, playbook):
    written, transport = _write(dossier, playbook, _answer(_device(1, *FUTURE_SENSOR)))
    (device,) = written.devices
    assert device.mark == "future" and device.mark_note == "FUTURE AS PER sheet M-701"
    assert transport.notes and "marked future" in transport.notes[0][1]


@pytest.mark.parametrize("mark, note, want_mark, want_note", [
    ("future", "control schematic on sheet M-701", "future", "FUTURE AS PER control schematic on sheet M-701"),
    ("future", "(FUTURE AS PER control schematic on sheet M-701)", "future",
     "FUTURE AS PER control schematic on sheet M-701"),
    ("Future", "FUTURE AS PER sheet M-701", "future", "FUTURE AS PER sheet M-701"),
    ("notice", "", "notice", ""),
])
def test_a_mark_is_made_usable_on_intake(dossier, playbook, mark, note, want_mark, want_note):
    name, sid, quote, where = FUTURE_SENSOR
    written, _ = _write(dossier, playbook, _answer(_device(1, name, sid, quote, where, mark=mark, mark_note=note)))
    assert (written.devices[0].mark, written.devices[0].mark_note) == (want_mark, want_note)


def test_an_unmarked_line_keeps_no_mark_note(dossier, playbook):
    written, _ = _write(dossier, playbook, _answer(_device(
        1, "Drain Pan Level Sensor", "S12", "DRAIN PAN LEVEL SENSOR", "M-601, Plans.pdf page 6", mark_note="stray")))
    assert written.devices[0].mark == "" and written.devices[0].mark_note == ""


def test_a_notice_line_for_a_device_furnished_with_the_unit(dossier, playbook):
    written, _ = _write(dossier, playbook, _answer(_device(
        1, "Drain Pan Level Sensor", "S12", "DRAIN PAN LEVEL SENSOR", "M-601, Plans.pdf page 6", mark="notice")))
    assert written.devices[0].mark == "notice"


@pytest.mark.parametrize("change, words", [
    (dict(mark="later"), "mark"),
    (dict(mark="future", mark_note="FUTURE AS PER S40"), "S40"),
    (dict(mark="future", mark_note="FUTURE AS PER " + "the control schematic " * 10), "mark_note"),
])
def test_a_bad_mark_is_refused(dossier, playbook, change, words):
    with pytest.raises(ai.NoAnswer) as refused:
        _write(dossier, playbook, _answer(_device(1, *FUTURE_SENSOR, **change)))
    assert words in refused.value.reason


def test_an_answer_written_before_marks_existed_is_still_used(dossier, playbook):
    device = _device(1, "Drain Pan Level Sensor", "S12", "DRAIN PAN LEVEL SENSOR", "M-601, Plans.pdf page 6")
    del device["mark"], device["mark_note"]
    written, _ = _write(dossier, playbook, _answer(device))
    assert written.devices[0].mark == "" and written.devices[0].mark_note == ""


def test_the_writer_schema_asks_for_the_marks(dossier, playbook):
    _, transport = _write(dossier, playbook, _answer(_device(1, *FUTURE_SENSOR)))
    items = transport.asked[0]["schema"]["properties"]["devices"]["items"]
    assert {"mark", "mark_note"} <= set(items["properties"])     # required or optional (T-005c decides)
    assert transport.asked[0]["schema"] == json_schema(System)


# ---- the intake: stated, never assumed (ruling 6) ------------------------------------------------------------------

def test_an_assumption_a_cited_schedule_states_is_dropped(dossier, playbook):
    device = _device(1, "Unit Controller", "S16", "CONTROLLER FURNISHED BY THE CONTROLS CONTRACTOR FOR FACTORY MOUNTING",
                     "M-601, Plans.pdf page 6", flag="assumed",
                     assumption={"what": "controller furnished by AME to the unit manufacturer for factory mounting",
                                 "why": "the schedule note states the controls contractor furnishes it"})
    written, transport = _write(dossier, playbook, _answer(device))
    assert written.devices[0].assumption is None and written.devices[0].flag == "none"
    assert any("dropped" in change for _, change in transport.notes)


def test_an_assumption_on_a_line_citing_no_schedule_or_sequence_is_kept(dossier, playbook):
    device = _device(1, "Condensate Alarm", "S20", "EXTEND AHU-1 CONDENSATE TO THE NEAREST DRAIN",
                     "M-101, Plans.pdf page 3", flag="assumed",
                     assumption={"what": "one alarm per unit", "why": "the schedule shows one drain per unit"})
    written, _ = _write(dossier, playbook, _answer(device))
    assert written.devices[0].assumption is not None and written.devices[0].flag == "assumed"


# ---- the intake: short flags (addendum) ----------------------------------------------------------------------------

def test_a_long_assumption_is_shortened_to_points_never_refused(dossier, playbook):
    """T-005d should fix 4: a long flag text no longer stops the run after max attempts; it is cut to points."""
    what = "one sensor per unit. " + "the sensor sits in the supply duct. " * 8
    why = "the control schematic shows one sensor. " + "the schedule is silent on the count. " * 8
    device = _device(1, *FUTURE_SENSOR, flag="assumed", assumption={"what": what, "why": why})
    written, transport = _write(dossier, playbook, _answer(device))
    assumption = written.devices[0].assumption
    assert len(assumption.what) + len(assumption.why) <= ai.ASSUMPTION_LIMIT
    assert assumption.what.startswith("one sensor per unit") and assumption.why.startswith("the control schematic")
    assert any("shortened" in change for _, change in transport.notes)


def test_a_long_clarification_is_shortened_to_points_never_refused(dossier, playbook):
    text = "; ".join(f"sensor {n} is listed on the unit schedule" for n in range(1, 30))
    written, transport = _write(dossier, playbook, _answer(_device(1, *FUTURE_SENSOR),
                                                           clarifications=[{"kind": "note", "text": text}]))
    shown = written.clarifications[0].text
    assert len(shown) <= ai.CLARIFICATION_LIMIT and shown.startswith("sensor 1 is listed on the unit schedule; sensor 2")
    assert any("shortened" in change for _, change in transport.notes)


def test_one_long_point_is_cut_at_a_word():
    shown = ai._points("x" * 20 + " " + "word " * 200, 60)
    assert len(shown) <= 60 and shown.endswith(" …")


# ---- the prompts -----------------------------------------------------------------------------------------------

def test_the_writer_prompts_carry_the_rulings():
    write = (ai.PROMPTS / "write_system.md").read_text(encoding="utf-8")
    assert "## Stated, never assumed" in write and "FUTURE AS PER" in write and '"notice"' in write
    assert "## End devices on unit schedules" in write and "## Every controls fact ends somewhere" in write
    assert "outside air temperature sensor" in write and "changeover aquastat" in write
    front = (ai.PROMPTS / "write_front_end.md").read_text(encoding="utf-8")
    assert "prequalified integrator" in front and "training" in front and "mark_note" in front
    assert "mark_note" in (ai.PROMPTS / "revise_system.md").read_text(encoding="utf-8")
    assert "FUTURE" in (ai.PROMPTS / "qc_job.md").read_text(encoding="utf-8")
