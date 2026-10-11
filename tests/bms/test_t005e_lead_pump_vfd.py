"""Lead ruling 2026-10-11 on T-005e: the Playbook wins over GEM v4 on pump VFD Control.
playbook/rules.md "Minimum points on AME-run equipment" (:181): "VFD Control when the equipment has a VFD". A pump the
documents show with no VFD gets no added VFD Control line; a pump with a VFD gets one. Invented fixtures only."""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from bms.model import Count, Device, Family, Job, Ref, System
from bms.playbook import load_playbook
from bms.render import render

FIXTURES = Path(__file__).resolve().parent / "fixtures"
PLAIN = Ref(source_id="S1", quote="start and stop the invented pumps", where="M-1, Drawings.pdf page 1")
WITH_VFD = Ref(source_id="S2", quote="each invented pump runs on a VFD", where="M-2, Drawings.pdf page 2")


@pytest.fixture(scope="module")
def house():
    return load_playbook()


@pytest.fixture
def job() -> Job:
    return Job.from_dict(json.loads((FIXTURES / "sample_job.json").read_text(encoding="utf-8")))


def dev(n, slot, name, ref=PLAIN, verb="Furnish"):
    return Device(id=f"HW.v{n}", slot=slot, name=name, verb=verb, furnished_by="AME", installed_by="AME",
                  wired_by="AME", quantity=Count(value=2), refs=(ref,))


def plant(*devices) -> System:
    return System(key="HW", name="Hot Water System", shape="Hot Water System", control="field",
                  families=(Family("Boiler", ("B-1", "B-2"), Count(value=2)),
                            Family("Hot Water Pump", ("HWP-1", "HWP-2"), Count(value=2))),
                  devices=(dev(0, "controller", "DDC Controller", verb="Furnish and Install"), *devices))


def lines(job, house, system):
    return [l.text for l in render(replace(job, systems=(system,)), house).lines
            if l.system_key == "HW" and l.kind == "line"]


def test_a_constant_speed_pump_gets_no_vfd_control_line(job, house):
    out = lines(job, house, plant(dev(1, "hw_pump_start_stop", "Hot Water Pump Start/Stop and Status")))
    assert "Furnish Hot Water Pump Start/Stop and Status" in out
    assert not any("VFD" in t for t in out)


def test_a_pump_whose_quote_names_a_vfd_gets_vfd_control(job, house):
    out = lines(job, house, plant(dev(1, "hw_pump_start_stop", "Hot Water Pump Start/Stop and Status", WITH_VFD)))
    assert out.count("Furnish Hot Water Pump VFD Control") == 1


def test_a_pump_with_a_vfd_fault_line_gets_vfd_control(job, house):
    out = lines(job, house, plant(dev(1, "hw_pump_start_stop", "Hot Water Pump Start/Stop and Status"),
                                  dev(2, "other_point", "Hot Water Pump VFD Fault")))
    assert out.count("Furnish Hot Water Pump VFD Control") == 1
