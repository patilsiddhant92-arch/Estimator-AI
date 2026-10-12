"""T-010 task 1 (ruling 23, HarkPro/inbox/T-010.md): who furnishes the freezestat and the dirty-filter switch.

On a unit with AME's DDC the line is "Furnish and Wire <device>", or "Wire <device> (Furnished by Unit Mfr.)" only
when a cited sequence or controls-diagram passage gives the device to the unit manufacturer; on a packaged unit a
freezestat line needs a cited sequence or controls-diagram passage that names it. The intake check refuses every
other form with a reason that quotes the Playbook rule. Invented fixtures only: no job text."""
from __future__ import annotations

import copy
import subprocess
import sys
from pathlib import Path

import pytest

from bms import ai, ai_evidence
from bms.model import Count, Device, Family, Ref, System
from bms.playbook import load_playbook

ROOT = Path(__file__).resolve().parents[2]
PLAYBOOK = load_playbook()
AME_RULE = "Freezestat and filter switch on a unit with AME controls"
PACKAGED_RULE = "Freezestat on a packaged unit"

SEQ_FS = "A LOW LIMIT FREEZESTAT STOPS THE SUPPLY FAN OF QZ-1"
SEQ_MFR = "FREEZESTAT AND DIRTY FILTER SWITCH FURNISHED BY THE UNIT MANUFACTURER, WIRED BY THE CONTROLS CONTRACTOR"
SCHED_ROW = "QZ-1 | FREEZESTAT | DIRTY FILTER SWITCH"
SCHED_NOTE = "FREEZESTAT AND DIRTY FILTER SWITCH FURNISHED WITH THE UNIT BY THE UNIT MANUFACTURER"
DIAG_MFR = "FREEZESTAT FS-1 FURNISHED BY THE UNIT MANUFACTURER, WIRED BY THE CONTROLS CONTRACTOR"
DIAG_FS = "FREEZESTAT FS-1 AT THE COOLING COIL"

EVIDENCE = "\n".join([
    "System: Invented Unit QZ (QZ-1)",
    "",
    "The sequence of operation for this system:",
    f"[S1] {SEQ_FS}.",
    f"[S2] {SEQ_MFR}.",
    "",
    "Its schedule rows and the schedules' notes:",
    f"[S5] | {SCHED_ROW} |",
    f"[S6] Note: {SCHED_NOTE}.",
    "",
    "Controls sheets that name it (control diagrams, points, sequences):",
    f"[S8] CONTROL DIAGRAM QZ-1: {DIAG_MFR}.",
    f"[S9] CONTROL DIAGRAM QZ-1 ALTERNATE VIEW: {DIAG_FS}.",
    "",
    "Notes that name it:",
    "[S11] QZ-1 SERVES THE INVENTED WING.",
    "",
])
WHERE = {"S1": "Seq of Ops, Invented.pdf page 1", "S2": "Seq of Ops, Invented.pdf page 1",
         "S5": "M-901, Invented.pdf page 3", "S6": "M-901, Invented.pdf page 3",
         "S8": "M-950, Invented.pdf page 9", "S9": "M-950, Invented.pdf page 9",
         "S11": "M-101, Invented.pdf page 2"}
QUOTE = {"S1": SEQ_FS, "S2": SEQ_MFR, "S5": SCHED_ROW, "S6": SCHED_NOTE, "S8": DIAG_MFR, "S9": DIAG_FS,
         "S11": "QZ-1 SERVES THE INVENTED WING"}


def _unit(control="field") -> System:
    return System(key="QZ", name="Invented Unit QZ", shape="", control=control,
                  families=(Family("Invented Unit", ("QZ-1",), Count(1)),), sequence_refs=())


class _Fake:
    """An API-like transport: a refused answer is asked once more now, with the reason."""

    def __init__(self, *answers):
        self.answers, self.notes, self.refusals = list(answers), [], []

    def ask(self, kind, name, instructions, system_prompt, prompt, schema, extra=None, images=()):
        if not self.answers:
            raise ai.NoAnswer("no answer queued", waiting=True)
        return copy.deepcopy(self.answers.pop(0))

    def refuse(self, reason):
        self.refusals.append(reason)
        return True

    def note_intake(self, name, change):
        self.notes.append((name, change))


def _device(name, slot, verb, cites, n=1, furnished="AME", installed="AME", wired="AME", **more):
    d = {"id": f"QZ.d{n}", "slot": slot, "name": name, "verb": verb, "furnished_by": furnished,
         "installed_by": installed, "wired_by": wired,
         "quantity": {"value": 1, "sources": [], "others": [], "added_up": None},
         "refs": [{"source_id": sid, "quote": QUOTE[sid], "where": WHERE[sid]} for sid in cites],
         "assumption": None, "flag": "none", "mark": "", "mark_note": ""}
    d.update(more)
    return d


def _answer(system, *devices):
    data = system.to_dict()
    data.update(devices=list(devices), clarifications=[], tech_hours=None, no_scope_reason=None)
    return data


def _check(system, *devices, keep=()):
    """The intake check as `_ask_system` runs it on the evidence above."""
    known = ai_evidence.cited_ids(EVIDENCE)
    return ai._check_system(_answer(system, *devices), system, None, known, keep, keep, [],
                            index=ai._sent_index(EVIDENCE), stated=ai_evidence.stated_ids(EVIDENCE),
                            diagram=ai_evidence.sequence_and_diagram_ids(EVIDENCE),
                            rules=PLAYBOOK.rules)


def _first_sentence(name):
    text = " ".join(PLAYBOOK.rules[name].text.split())
    return text.split(". ", 1)[0] + "."


def _furnish_and_wire(name, slot, cites=("S5",), n=1):
    return _device(name, slot, "Furnish and Wire", cites, n=n, installed="Unit Mfr.")


def _wire_by_mfr(name, slot, cites, n=1):
    return _device(name, slot, "Wire", cites, n=n, furnished="Unit Mfr.", installed="Unit Mfr.")


# ---- 1. a unit with AME's DDC: "Furnish and Wire" is accepted --------------------------------------------------------

def test_furnish_and_wire_is_accepted_on_a_unit_with_ame_ddc():
    written, problems = _check(_unit(), _furnish_and_wire("Freezestat", "freezestat"),
                               _furnish_and_wire("Dirty Filter Switch", "filter_dp", n=2))
    assert problems == []
    assert [d.verb for d in written.devices] == ["Furnish and Wire", "Furnish and Wire"]
    assert all(d.furnished_by == "AME" and d.wired_by == "AME" for d in written.devices)


# ---- 2. the same unit: another verb, or the manufacturer on a schedule row alone, is refused -------------------------

def test_furnish_and_install_freezestat_is_refused_with_the_rule_quoted():
    written, problems = _check(_unit(), _device("Freezestat", "freezestat", "Furnish and Install", ("S5",)))
    assert written is None
    reason = " ".join(problems)
    assert f'"{AME_RULE}"' in reason and _first_sentence(AME_RULE) in reason


def test_install_and_wire_by_the_manufacturer_on_a_schedule_row_alone_is_refused():
    device = _device("Dirty Filter Switch", "filter_dp", "Install and Wire", ("S5", "S6"), furnished="Unit Mfr.")
    written, problems = _check(_unit(), device)
    assert written is None
    assert any(f'"{AME_RULE}"' in p and _first_sentence(AME_RULE) in p for p in problems)


# ---- 3. "Wire ... (Furnished by Unit Mfr.)" needs a sequence or controls-diagram passage ----------------------------

def test_wire_by_the_manufacturer_is_accepted_on_a_sequence_passage():
    written, problems = _check(_unit(), _wire_by_mfr("Freezestat", "freezestat", ("S2",)))
    assert problems == [] and written.devices[0].furnished_by == "Unit Mfr."


def test_wire_by_the_manufacturer_is_accepted_on_a_controls_diagram_passage():
    written, problems = _check(_unit(), _wire_by_mfr("Freezestat", "freezestat", ("S8",)))
    assert problems == [] and written.devices[0].verb == "Wire"


def test_wire_by_the_manufacturer_is_refused_on_a_schedule_row_or_note_only():
    for cites in (("S5",), ("S6",), ("S5", "S6")):
        written, problems = _check(_unit(), _wire_by_mfr("Freezestat", "freezestat", cites))
        assert written is None and any(f'"{AME_RULE}"' in p for p in problems), cites


def test_a_sequence_passage_that_names_no_manufacturer_does_not_move_the_device():
    written, problems = _check(_unit(), _wire_by_mfr("Freezestat", "freezestat", ("S1",)))
    assert written is None and any(f'"{AME_RULE}"' in p for p in problems)


# ---- 4. a packaged unit: a freezestat line needs a sequence or controls-diagram passage that names it ---------------

def test_a_packaged_freezestat_on_a_schedule_row_only_is_refused_with_the_second_rule():
    device = _wire_by_mfr("Freezestat", "freezestat", ("S5",))
    written, problems = _check(_unit("packaged"), device)
    assert written is None
    assert any(f'"{PACKAGED_RULE}"' in p and _first_sentence(PACKAGED_RULE) in p for p in problems)


def test_a_packaged_freezestat_on_a_sequence_passage_that_names_it_is_accepted():
    written, problems = _check(_unit("packaged"), _wire_by_mfr("Freezestat", "freezestat", ("S1",)))
    assert problems == [] and written.devices[0].name == "Freezestat"


def test_a_packaged_freezestat_on_a_controls_diagram_passage_that_names_it_is_accepted():
    written, problems = _check(_unit("packaged"), _wire_by_mfr("Low Limit Freezestat", "other_device", ("S9",)))
    assert problems == []


def test_a_packaged_filter_switch_is_not_checked_by_ruling_23():
    written, problems = _check(_unit("packaged"), _wire_by_mfr("Dirty Filter Switch", "filter_dp", ("S5",)))
    assert problems == []


def test_a_packaged_unit_with_an_ame_furnished_controller_takes_the_ame_ddc_rule():
    controller = _device("DDC Controller", "controller", "Furnish", ("S11",), installed="Unit Mfr.",
                         wired="Unit Mfr.")
    fs = _device("Freezestat", "freezestat", "Furnish and Install", ("S5",), n=2)
    written, problems = _check(_unit("packaged"), controller, fs)
    assert written is None
    assert any(f'"{AME_RULE}"' in p for p in problems) and not any(f'"{PACKAGED_RULE}"' in p for p in problems)
    written, problems = _check(_unit("packaged"), controller, _furnish_and_wire("Freezestat", "freezestat", n=2))
    assert problems == []


def test_another_control_value_is_not_checked():
    for control in ("integration", "none"):
        written, problems = _check(_unit(control), _device("Freezestat", "freezestat", "Furnish and Install",
                                                           ("S5",)))
        assert problems == [], control


# ---- 5. other devices and kept devices are not checked ---------------------------------------------------------------

def test_another_device_is_not_checked():
    written, problems = _check(_unit(), _device("Space Temperature Sensor", "space_temperature",
                                                "Furnish and Install", ("S11",)))
    assert problems == []


def test_a_kept_device_is_never_refused():
    kept = Device(id="QZ.d1", slot="freezestat", name="Freezestat", verb="Furnish and Install", furnished_by="AME",
                  installed_by="AME", wired_by="AME", quantity=Count(1), refs=(Ref("S5", SCHED_ROW, WHERE["S5"]),))
    written, problems = _check(_unit(), kept.to_dict(), keep=(kept,))
    assert problems == [] and written.devices[0].verb == "Furnish and Install"


# ---- 6. the kind detector (README checklist 5) -------------------------------------------------------------------

@pytest.mark.parametrize("name", ["Freezestat", "Low Limit Freezestat", "Dirty Filter Switch",
                                  "Filter Differential Pressure Switch", "Freeze Stat", "Filter Status"])
def test_the_detector_finds_the_two_devices(name):
    assert ai.owned_device_kind(name) is not None


@pytest.mark.parametrize("name", ["Discharge Air Temperature Sensor", "Duct Smoke Detector",
                                  "Filter Section Access Door", "Freeze Protection Pump", "Oil Filter Housing"])
def test_the_detector_leaves_other_devices(name):
    assert ai.owned_device_kind(name) is None


def test_the_detector_reads_the_slot_too():
    assert ai.owned_device_kind("Coil Low Temperature Safety", "freezestat") == "freezestat"
    assert ai.owned_device_kind("Pre-Filter Monitor", "filter_dp") == "filter switch"
    assert ai.owned_device_kind("Freezestat") == "freezestat"
    assert ai.owned_device_kind("Dirty Filter Switch") == "filter switch"


# ---- 7. the ids of the sequence and controls-sheet blocks --------------------------------------------------------------

def test_the_sequence_and_diagram_ids_are_those_two_blocks_only():
    assert ai_evidence.sequence_and_diagram_ids(EVIDENCE) == frozenset({"S1", "S2", "S8", "S9"})
    assert ai_evidence.sequence_and_diagram_ids("") == frozenset()


# ---- 8. through write_system: a wrong owner is refused and a corrected answer is taken --------------------------------

def test_write_system_refuses_the_wrong_owner_and_takes_the_corrected_answer():
    bad = _answer(_unit(), _device("Freezestat", "freezestat", "Furnish and Install", ("S5",)))
    good = _answer(_unit(), _furnish_and_wire("Freezestat", "freezestat"))
    t = _Fake(bad, good)
    written = ai.write_system(_unit(), EVIDENCE, PLAYBOOK, t)
    assert written.devices[0].verb == "Furnish and Wire"
    assert len(t.refusals) == 1 and f'"{AME_RULE}"' in t.refusals[0]


# ---- 9. the Playbook, the prompt and the linter --------------------------------------------------------------------

def test_the_two_rules_are_in_packaged_units_after_the_template_rule():
    names = [n for n, rule in PLAYBOOK.rules.items() if rule.topic == "Packaged units"]
    assert names[-3:] == ["Template is the ideal case", AME_RULE, PACKAGED_RULE]
    assert "Furnish and Wire <device>" in PLAYBOOK.rules[AME_RULE].text
    assert "freezestat" in PLAYBOOK.rules[PACKAGED_RULE].text


def test_the_writer_prompt_names_both_rules():
    text = (ROOT / "src" / "bms" / "prompts" / "write_system.md").read_text(encoding="utf-8")
    ownership = text.split("## Ownership", 1)[1].split("\n## ", 1)[0]
    assert f'"{AME_RULE}"' in ownership and f'"{PACKAGED_RULE}"' in ownership


def test_the_playbook_lints_clean():
    from bms.playbook_lint import lint_playbook
    assert lint_playbook() == []
    out = subprocess.run([sys.executable, "-m", "bms", "playbook-lint"], cwd=ROOT, capture_output=True, text=True,
                         env={"PYTHONPATH": str(ROOT / "src"), "PATH": ""})
    assert out.returncode == 0, out.stdout + out.stderr


def test_a_point_line_of_the_shape_is_not_the_device():
    shaped = System(key="QZ", name="Invented Unit QZ", shape="Air Handling Unit", control="field",
                    families=(Family("Air Handling Unit", ("QZ-1",), Count(1)),), sequence_refs=())
    shape = PLAYBOOK.shapes["Air Handling Unit"]
    point = next(slot for slot, kind in shape.slot_kinds.items() if kind == "point")
    known = ai_evidence.cited_ids(EVIDENCE)
    for slot, refused in ((point, False), ("freezestat", True)):
        device = _device("Freezestat", slot, "Furnish and Install", ("S5",))
        _, problems = ai._check_system(_answer(shaped, device), shaped, shape, known, (), (), [],
                                       diagram=ai_evidence.sequence_and_diagram_ids(EVIDENCE), rules=PLAYBOOK.rules)
        assert any(f'"{AME_RULE}"' in p for p in problems) is refused, (slot, problems)


# ---- review fixes (independent review of T-010 task 1) --------------------------------------------------------------

def test_a_passage_naming_both_devices_counts_for_the_filter_switch_too():
    """M1: S2 names the freezestat and the dirty-filter switch; it gives each to the unit manufacturer."""
    written, problems = _check(_unit(), _wire_by_mfr("Dirty Filter Switch", "filter_dp", ("S2",)))
    assert problems == [] and written.devices[0].furnished_by == "Unit Mfr."


@pytest.mark.parametrize("name, slot, cites", [("Freezestat", "freezestat", ("S2",)),
                                               ("Freezestat", "freezestat", ("S8",)),
                                               ("Dirty Filter Switch", "filter_dp", ("S2",))])
def test_furnish_and_wire_is_refused_when_the_sequence_or_diagram_gives_it_to_the_manufacturer(name, slot, cites):
    """M2: a cited sequence or controls-diagram passage says the unit manufacturer furnishes the device."""
    written, problems = _check(_unit(), _furnish_and_wire(name, slot, cites))
    assert written is None
    assert any(f'"{AME_RULE}"' in p and _first_sentence(AME_RULE) in p for p in problems)
