"""Reviewer's tests for T-005e (invented fixtures only). Not part of the branch."""
from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from bms import order
from bms.labor import labor_conditions
from bms.model import Count, Device, Family, Job, Ref, System
from bms.playbook import load_playbook
from bms.render import render

FIXTURES = Path(__file__).resolve().parent / "fixtures"
REF = Ref(source_id="S1", quote="q", where="M-1, Drawings.pdf page 1")


@pytest.fixture(scope="module")
def house():
    return load_playbook()


@pytest.fixture
def job() -> Job:
    return Job.from_dict(json.loads((FIXTURES / "sample_job.json").read_text(encoding="utf-8")))


def dev(n, name, verb, slot, key, **kw):
    base = dict(id=f"{key}.d{n}", slot=slot, name=name, verb=verb, furnished_by="AME", installed_by="AME",
                wired_by="AME", quantity=Count(value=2), refs=(REF,))
    base.update(kw)
    return Device(**base)


def lines(draft, key):
    return [l.text for l in draft.lines if l.system_key == key and l.kind == "line"]


def ahu(devices):
    return System(key="AHU", name="Air Handling Units", shape="Air Handling Unit", control="field",
                  families=(Family("Air Handling Unit", ("AHU-1", "AHU-2"), Count(value=2)),), devices=tuple(devices))


# 1. GEM ~396-402: a Master Template entry is the frame; its own order wins. The Master Template's AHU entry prints
#    the fan signals, then the safety switches, then the dampers (Brain/Master Template.docx, AHU entry).
def test_master_template_entry_order_wins_over_the_standard_order(job, house):
    devices = [dev(1, "Outside Air Damper Actuator", "Furnish and Install", "oa_damper", "AHU"),
               dev(2, "Freezestat", "Furnish and Install", "freezestat", "AHU"),
               dev(3, "Supply Fan Start/Stop and Status", "Furnish", "supply_fan_start_stop", "AHU")]
    out = lines(render(replace(job, systems=(ahu(devices),)), house), "AHU")
    assert out == ["Furnish Supply Fan Start/Stop and Status", "Furnish and Install Freezestat",
                   "Furnish and Install Outside Air Damper Actuator"]


# 2. The catch-all slots (after the valves in shapes.json) take their GEM place: a leak detector, a relay and an
#    other-Wire line written in catch-all slots print before the valve, the Install and Wire and the integration.
def test_catch_all_slots_print_in_gem_order(job, house):
    devices = [dev(1, "BMS Communication Wiring to Factory Controls", "Furnish", "comm_wiring", "AHU"),
               dev(2, "Hot Water Control Valve and Actuator", "Furnish and Wire", "hot_water_valve", "AHU"),
               dev(3, "Space Thermostat", "Install and Wire", "other_install_and_wire", "AHU",
                   furnished_by="Unit Mfr."),
               dev(4, "Interposing Relay", "Furnish and Install", "other_device", "AHU"),
               dev(5, "Water Leak Detector", "Furnish and Install", "other_device", "AHU"),
               dev(6, "DDC Controller", "Furnish and Install", "controller", "AHU")]
    out = lines(render(replace(job, systems=(ahu(devices),)), house), "AHU")
    assert out[0] == "Furnish and Install DDC Controller"
    assert out.index("Furnish and Install Water Leak Detector") < out.index("Furnish and Install Interposing Relay")
    assert out.index("Furnish and Install Interposing Relay") < out.index(
        "Furnish and Wire Hot Water Control Valve and Actuator")
    assert out.index("Furnish and Wire Hot Water Control Valve and Actuator") < out.index(
        "Install and Wire Space Thermostat (Furnished by Unit Mfr.)")
    assert out[-1] == "Furnish BMS Communication Wiring to Factory Controls"


# 3. GEM item 10 names valve position feedback with the position-feedback signals, before the valves (16).
def test_valve_position_feedback_is_gem_position_10():
    assert order.position("Furnish Hot Water Valve Position Feedback", "Furnish") == 10


# 4. A device's place does not depend on its verb when the GEM names its category: a Furnish and Wire leak detector
#    is a leak detector (4), not a valve (16).
def test_furnish_and_wire_leak_detector_keeps_its_category():
    assert order.position("Furnish and Wire Leak Detector", "Furnish and Wire") == 4


# 5. A sentence that forbids off-hours work is not a call for it.
@dataclass(frozen=True)
class _Place:
    document: str = "Specs.pdf"
    page: int = 3
    sheet: str | None = None
    section: str | None = "01 10 00"


@dataclass(frozen=True)
class _Found:
    section: str
    item: str
    quote: str
    status: str = "Found"
    places: tuple = (_Place(),)


@dataclass(frozen=True)
class _Overview:
    conditions: tuple = ()
    standard_lines: tuple = ()


def test_a_ban_on_overtime_is_not_off_hours_work():
    row = _Found("Project conditions that change the price", "Working hours",
                 "No overtime work is permitted; work outside normal working hours is not allowed.")
    assert labor_conditions(_Overview(conditions=(row,))) == ()


def test_a_prevailing_wage_quote_gives_one_cited_condition():
    row = _Found("Project conditions that change the price", "Prevailing wage",
                 "Pay the prevailing wage rates of the State of Delaware.", places=(_Place(section="00 73 46"),))
    found = labor_conditions(_Overview(conditions=(row,)))
    assert [c.kind for c in found] == ["prevailing-wage"]
    assert found[0].text == "DE Prevailing Wage Labor Rates Included (As per Spec Section 00 73 46)"
