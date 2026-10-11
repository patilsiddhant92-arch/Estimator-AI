"""Lead ruling 2026-10-11 on T-005e: the Playbook wins over GEM v4 on the place of the plain work statements.
playbook/rules.md "Standard order" (:604) and "Integration lines last" (:486): wiring runs and plain work statements
print before the integration group, which is always last in the block. Invented fixtures only."""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from bms import order
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


def dev(n, slot, name, verb="Furnish"):
    return Device(id=f"AHU.m{n}", slot=slot, name=name, verb=verb, furnished_by="AME", installed_by="AME",
                  wired_by="AME", quantity=Count(value=2), refs=(REF,))


def test_a_plain_work_statement_prints_before_the_integration_lines(job, house):
    devices = (dev(1, "comm_wiring", "BMS Communication Wiring to Factory Controls"),
               dev(2, "map_points", "Map Available Points Via Mfr. Provided BMS Interface"),
               dev(3, "other_wiring", "Coordination of Functional Testing with the Invented Commissioning Agent"),
               dev(4, "controller", "DDC Controller", "Furnish and Install"))
    ahu = System(key="AHU", name="Air Handling Units", shape="Air Handling Unit", control="field",
                 families=(Family("Air Handling Unit", ("AHU-1", "AHU-2"), Count(value=2)),), devices=devices)
    out = [l.text for l in render(replace(job, systems=(ahu,)), house).lines
           if l.system_key == "AHU" and l.kind == "line"]
    misc = next(t for t in out if t.startswith("Coordination of Functional Testing"))
    assert out.index(misc) < out.index("Furnish BMS Communication Wiring to Factory Controls")
    assert out[-1].startswith("Map Available Points")                      # the integration group stays last


def test_the_misc_position_comes_before_the_integration_position():
    assert order.MISCELLANEOUS < order.INTEGRATION
    assert order.position("Coordination of Testing", None, "other_wiring", "wiring") == order.MISCELLANEOUS
    assert order.position("anything", "Furnish", "comm_wiring", "integration") == order.INTEGRATION
