"""Reviewer's tests for T-005d (2026-10-11). Invented fixtures only. Each test states a rule of the T-005 rulings or
the root cause; a failing test is a review finding, not a test to fix by tuning."""
from __future__ import annotations

import copy
from pathlib import Path

import pytest

from estimator.ledger.facts import Fact
from estimator.writing.dossier import Dossier

from bms import ai, ai_evidence
from bms.model import Count, Family, System
from bms.playbook import load_playbook

FIXTURES = Path(__file__).resolve().parent / "fixtures"

LINES = [
    "JOB DOSSIER — Invented Library",
    "== 1. JOB ==",
    "[S1] Who does what (by the Owner) — “The owner furnishes the network switches.”",
    "== 2. SEQUENCE OF OPERATION ==",
    "--- 23 09 93, Specs.pdf page 3 ---",
    "--- [Q1] A. GENERAL ---",
    "[S2] A. GENERAL",
    "[S3] Provide one outside air temperature sensor for global use by all systems.",
    "[S4] Provide a changeover aquastat on the common supply main to index heating or cooling mode.",
    "--- [Q2] B. AIR HANDLING UNIT ZZ-7 ---",
    "[S5] B. AIR HANDLING UNIT ZZ-7",
    "[S6] The BMS shall modulate the supply fan VFD of ZZ-7 to hold duct static pressure.",
    "== 4. SCHEDULES ==",
    "[S10] AIR HANDLING UNITS — M-601, Plans.pdf page 6 (1 row)",
    "    Columns: TAG | CONTROLS",
    "[S11] ZZ-7 | UNIT CONTROLLER FURNISHED BY THE UNIT MANUFACTURER, FACTORY MOUNTED",
    "[S12] Note: 1. SMOKE DETECTOR QUANTITY BY OTHERS.",
    "== 7. NOTES ==",
    "--- 7c PLAN SHEET TEXT ---",
    "[S20] M-701, Plans.pdf page 9 CONTROL DIAGRAMS: ZZ-7 CONTROL SCHEMATIC " + "SUPPLY FAN VFD AO STATUS BI " * 500,
    "[S21] M-101, Plans.pdf page 3 MECHANICAL PLAN: ZZ-7 CAP FOR FUTURE CONNECTION BY OTHERS.",
]
SECTIONS = {"Q1": ("A. GENERAL", ("S2", "S3", "S4")), "Q2": ("B. AIR HANDLING UNIT ZZ-7", ("S5", "S6"))}


@pytest.fixture
def dossier() -> Dossier:
    return Dossier("Invented Library", "\n".join(LINES) + "\n", (), {}, (), {}, {}, {}, SECTIONS)


@pytest.fixture
def playbook():
    return load_playbook(FIXTURES / "sample_playbook")


def zz() -> System:
    return System(key="ZZ", name="Air Handling Units", shape="", control="field",
                  families=(Family("Air Handling Unit", ("ZZ-7",), Count(1)),), sequence_refs=())


class _Ledger:
    sources = {"S3": "23 09 93, Specs.pdf page 3", "S4": "23 09 93, Specs.pdf page 3"}
    facts = {
        "F1": Fact("F1", "device", "outside air temperature sensor", None, "S3",
                   "Provide one outside air temperature sensor for global use by all systems.", "spec"),
        "F2": Fact("F2", "device", "changeover aquastat", None, "S4",
                   "Provide a changeover aquastat on the common supply main", "spec"),
    }


class _Fake:
    def __init__(self, *answers):
        self.answers, self.notes = list(answers), []

    def ask(self, kind, name, instructions, system_prompt, prompt, schema, extra=None, images=()):
        if not self.answers:
            raise ai.NoAnswer("no answer queued", waiting=True)
        return copy.deepcopy(self.answers.pop(0))

    def note_intake(self, name, change):
        self.notes.append((name, change))


def _device(name, sid, quote, where, **more):
    d = {"id": "ZZ.d1", "slot": "sensor", "name": name, "verb": "Furnish and Install", "furnished_by": "AME",
         "installed_by": "AME", "wired_by": "AME", "quantity": {"value": 1, "sources": [], "others": [],
                                                                  "added_up": None},
         "refs": [{"source_id": sid, "quote": quote, "where": where}], "assumption": None, "flag": "none",
         "mark": "", "mark_note": ""}
    d.update(more)
    return d


def _write(dossier, playbook, device):
    data = zz().to_dict()
    data.update(devices=[device], clarifications=[], tech_hours=None, no_scope_reason=None)
    t = _Fake(data)
    return ai.write_system(zz(), ai.system_evidence(zz(), dossier, _Ledger()), playbook, t), t


# ---- root cause: a job-wide fact that names no unit tag must reach the system's writer -------------------------

def test_a_global_outside_air_sensor_in_the_sequence_reaches_the_ahu_evidence(dossier):
    text = ai.system_evidence(zz(), dossier, _Ledger())
    assert "outside air temperature sensor" in text


def test_a_changeover_aquastat_in_the_general_sequence_reaches_the_ahu_evidence(dossier):
    text = ai.system_evidence(zz(), dossier, _Ledger())
    assert "changeover aquastat" in text


# ---- ruling 6: a schedule that states the fact never gives an "Assumed" line ----------------------------------

def test_an_assumption_against_a_stated_schedule_fact_is_not_kept(dossier, playbook):
    """The 26-0544 pattern with invented words: the schedule states who furnishes the controller; the writer assumes
    otherwise and gives the spec as the reason."""
    device = _device("Unit Controller", "S11", "UNIT CONTROLLER FURNISHED BY THE UNIT MANUFACTURER, FACTORY MOUNTED",
                     "M-601, Plans.pdf page 6", flag="assumed",
                     assumption={"what": "controller furnished by AME to the unit manufacturer for factory mounting",
                                 "why": "the controls specification has the contractor furnish unit controllers"})
    written, _ = _write(dossier, playbook, device)
    line = written.devices[0]
    # never "Assumed" against the stated row ...
    assert line.flag != "assumed"
    # ... and never a silent contradiction (lead fix 1): the line says AME, the row says the unit manufacturer, so the
    # line keeps an ownership flag whose words name both parties, for the review page
    assert line.furnished_by == "AME" and line.flag == "ownership"
    assert line.assumption is not None
    words = f"{line.assumption.what} {line.assumption.why}"
    assert "AME" in words and "Unit Mfr." in words


def test_an_ownership_assumption_the_stated_row_agrees_with_is_dropped(dossier, playbook):
    """The line already follows the row (furnished and mounted by the manufacturer): the assumption is not needed."""
    device = _device("Unit Controller", "S11", "UNIT CONTROLLER FURNISHED BY THE UNIT MANUFACTURER, FACTORY MOUNTED",
                     "M-601, Plans.pdf page 6", flag="assumed", verb="Wire", furnished_by="Unit Mfr.",
                     installed_by="Unit Mfr.",
                     assumption={"what": "controller furnished by the unit manufacturer",
                                 "why": "the controls specification has the contractor furnish unit controllers"})
    written, _ = _write(dossier, playbook, device)
    assert written.devices[0].assumption is None and written.devices[0].flag == "none"


def test_the_review_page_shows_the_ownership_flag_with_both_parties(dossier, playbook):
    from bms import review
    device = _device("Unit Controller", "S11", "UNIT CONTROLLER FURNISHED BY THE UNIT MANUFACTURER, FACTORY MOUNTED",
                     "M-601, Plans.pdf page 6", flag="assumed",
                     assumption={"what": "controller furnished by AME to the unit manufacturer for factory mounting",
                                 "why": "the controls specification has the contractor furnish unit controllers"})
    written, _ = _write(dossier, playbook, device)
    import dataclasses
    import json
    from bms.model import Job
    job = Job.from_dict(json.loads((FIXTURES / "sample_job.json").read_text(encoding="utf-8")))
    job = dataclasses.replace(job, systems=(*job.systems, written))
    (card,) = [q for q in review._questions(job, []) if q.system_key == "ZZ" and q.device_id == "ZZ.d1"]
    text = " ".join(card.notes)
    assert "Who furnishes, installs or wires this line is not settled." in text
    assert "AME" in text and "Unit Mfr." in text


def test_an_assumption_that_says_the_schedule_does_not_state_the_value_is_kept(dossier, playbook):
    """The schedule note gives no count: the assumption is real and must stay flagged."""
    device = _device("Duct Smoke Detector", "S12", "SMOKE DETECTOR QUANTITY BY OTHERS", "M-601, Plans.pdf page 6",
                     flag="assumed", assumption={"what": "one detector per unit",
                                                 "why": "the schedule does not state the quantity"})
    written, _ = _write(dossier, playbook, device)
    assert written.devices[0].assumption is not None and written.devices[0].flag == "assumed"


# ---- the controls sheet the fix puts first must reach the writer when it is long --------------------------------

def test_a_long_control_diagram_sheet_reaches_the_writer(dossier):
    assert len(LINES[-2]) > ai_evidence.NOTES_LIMIT
    text = ai.system_evidence(zz(), dossier, _Ledger())
    assert "[S20]" in text


# ---- ruling 7: only an item the documents mark FUTURE is marked future ------------------------------------------

def test_a_future_word_about_something_else_does_not_mark_the_line(dossier, playbook):
    device = _device("Unit Controller", "S21", "ZZ-7 CAP FOR FUTURE CONNECTION BY OTHERS", "M-101, Plans.pdf page 3")
    written, _ = _write(dossier, playbook, device)
    assert written.devices[0].mark == ""


# ---- lead fix 2: job-wide means no system's; the outside air sensor has one owner, the Global Points block ------

def _plan_job_with_a_heater_section():
    from estimator.ledger.facts import SETTLED, Ledger
    from bms.plan import GLOBAL_POINTS, plan_job
    lines = list(LINES)
    i = lines.index("== 4. SCHEDULES ==")
    lines[i:i] = ["--- [Q3] C. CABINET UNIT HEATERS ---", "[S7] C. CABINET UNIT HEATERS",
                  "[S8] Each cabinet unit heater shall cycle its fan on its own space thermostat."]
    sections = dict(SECTIONS, Q3=("C. CABINET UNIT HEATERS", ("S7", "S8")))
    dossier = Dossier("Invented Library", "\n".join(lines) + "\n", (), {}, (), {}, {}, {}, sections)
    ledger = Ledger({"S3": "23 09 93, Specs.pdf page 3", "S11": "M-601, Plans.pdf page 6 (schedule)",
                     "S13": "M-602, Plans.pdf page 7 (schedule)", "S8": "23 09 93, Specs.pdf page 3", "S20": "23 09 00, Specs.pdf page 2",
                     "Q1": "sequence section “A. GENERAL”, Specs.pdf page 3",
                     "Q2": "sequence section “B. AIR HANDLING UNIT ZZ-7”, Specs.pdf page 3",
                     "Q3": "sequence section “C. CABINET UNIT HEATERS”, Specs.pdf page 3"})
    ledger.job_name = "Invented Library"
    ledger.add("front_end", "mode", "new-system", "S20", "provide a new building automation system", "spec", SETTLED)
    ledger.add("front_end", "line", "Furnish an operator workstation", "S20", "provide one operator workstation",
               "spec", SETTLED)
    ledger.add("family", "ZZ", "Air Handling Unit", "S11", "ZZ Air Handling Unit", "schedules", SETTLED)
    ledger.add("unit", "ZZ", "ZZ-7", "S11", "Tags: ZZ-7", "schedules", SETTLED)
    ledger.add("count", "ZZ", 1, "S11", "ZZ rows 1", "schedules", SETTLED)
    ledger.add("family", "CUH", "Cabinet Unit Heater", "S13", "CUH Cabinet Unit Heater", "schedules", SETTLED)
    ledger.add("unit", "CUH", "CUH-1", "S13", "Tags: CUH-1", "schedules", SETTLED)
    ledger.add("count", "CUH", 1, "S13", "CUH rows 1", "schedules", SETTLED)
    ledger.add("sequence_match", "A. GENERAL", "", "Q1", "A. GENERAL", "sequence", SETTLED)
    ledger.add("sequence_match", "B. AIR HANDLING UNIT ZZ-7", "ZZ", "Q2", "B. AIR HANDLING UNIT ZZ-7", "sequence",
               SETTLED)
    ledger.add("sequence_match", "C. CABINET UNIT HEATERS", "CUH", "Q3", "C. CABINET UNIT HEATERS", "sequence",
               SETTLED)
    ledger.add("device", "outside air temperature sensor", None, "S3",
               "Provide one outside air temperature sensor for global use by all systems.", "sequence", SETTLED)
    playbook = load_playbook(FIXTURES / "sample_playbook")
    job = plan_job(ledger, None, Dossier("Invented Library", "", (), {}, (), {}, {}, {}), playbook)
    by_key = {s.key: s for s in job.systems}
    return job, by_key, GLOBAL_POINTS, dossier, ledger


def test_the_ahu_writer_sees_the_general_section_and_not_the_heater_section():
    _job, by_key, _gp, dossier, ledger = _plan_job_with_a_heater_section()
    ahu = next(s for s in by_key.values() if any("ZZ-7" in f.tags for f in s.families))
    text = ai.system_evidence(ahu, dossier, ledger)
    assert "changeover aquastat on the common supply main" in text          # the GENERAL section
    assert "cabinet unit heater shall cycle" not in text                    # that family's writer only
    heater = next(s for s in by_key.values() if any("CUH-1" in f.tags for f in s.families))
    assert "cabinet unit heater shall cycle" in ai.system_evidence(heater, dossier, ledger)


def test_the_outside_air_sensor_is_owned_by_the_global_points_block_once():
    _job, by_key, gp, dossier, ledger = _plan_job_with_a_heater_section()
    assert gp in by_key                                                     # the plan gives it one owner
    text = ai.system_evidence(by_key[gp], dossier, ledger)
    assert text.count("Provide one outside air temperature sensor for global use by all systems.") == 1


def test_a_heater_fact_with_no_tag_is_not_a_job_wide_fact():
    from estimator.ledger.facts import SETTLED
    _job, by_key, _gp, dossier, ledger = _plan_job_with_a_heater_section()
    ledger.add("device", "cabinet unit heater space thermostat", None, "S8",
               "Each cabinet unit heater shall cycle its fan on its own space thermostat.", "sequence", SETTLED)
    ahu = next(s for s in by_key.values() if any("ZZ-7" in f.tags for f in s.families))
    assert "cabinet unit heater space thermostat" not in ai.system_evidence(ahu, dossier, ledger)


def test_a_section_that_names_another_family_is_not_job_wide_but_general_ones_are():
    seq = ai_evidence.parse("\n".join([
        "== 2. SEQUENCE OF OPERATION ==", "--- 23 09 93, Specs.pdf page 3 ---",
        "--- [Q1] A. GENERAL ---", "[S2] A. GENERAL", "[S3] All systems shall be scheduled by the BMS.",
        "--- [Q4] D. GENERAL - EXHAUST FANS ---", "[S9] D. GENERAL - EXHAUST FANS", "[S10] Fans shall run in occupied mode.",
        "--- [Q5] E. NIGHT SETBACK ---", "[S11] E. NIGHT SETBACK", "[S12] Space set points shall reset at night.",
        "--- [Q6] F. UNIT HEATERS ---", "[S13] F. UNIT HEATERS", "[S14] Heaters cycle on their thermostats."]))
    chosen = ai_evidence._job_wide_sections([e for e in seq if e.part == ai_evidence.SEQUENCE], {}, set(), [])
    ids = {e.sid for e in chosen if e.sid}
    assert {"S3", "S12"} <= ids and not ids & {"S10", "S14"}
