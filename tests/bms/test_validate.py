"""Workstream 3: the validators, on the invented sample job and small variations of it."""
from __future__ import annotations

import dataclasses as dc
import json
from pathlib import Path

import pytest

from bms.model import Assumption, Clarification, Count, Device, Family, Job, OtherCount, Ref
from bms.playbook import load_playbook
from bms.validate import RULE, RULES_NEEDING_A_HEADING, validate

FIX = Path(__file__).resolve().parent / "fixtures"
PB = load_playbook(FIX / "sample_playbook")
REF = Ref("S9", "invented quote", "invented place")


@pytest.fixture
def job() -> Job:
    return Job.from_dict(json.loads((FIX / "sample_job.json").read_text(encoding="utf-8")))


def edit(job, key, **changes):
    return job.with_system(dc.replace(job.system(key), **changes))


def edit_device(job, key, dev_id, **changes):
    s = job.system(key)
    return edit(job, key, devices=tuple(dc.replace(d, **changes) if d.id == dev_id else d for d in s.devices))


def rules(findings, rule=None):
    return [(f.rule, f.system_key, f.device_id, f.severity) for f in findings if rule is None or f.rule == rule]


def test_the_sample_job_is_clean(job):
    assert validate(job, PB) == []


def test_rule_names_of_the_sample_playbook():
    for name in ("cites", "higher", "one_note", "assumption", "packaged", "loose", "damper", "heater", "vrf"):
        assert RULE[name] in PB.rules


def test_rule_names_without_a_playbook_heading_are_listed():
    missing = {k for k, v in RULE.items() if v not in PB.rules}
    assert missing == set(RULES_NEEDING_A_HEADING)


def test_packaged_internal_device_and_trio_twice(job):
    s = job.system("RTU")
    extra = Device("RTU.d9", "map_points", "Points", "Furnish", "AME", "AME", "AME", Count(2), (REF,))
    j = edit(job, "RTU", devices=s.devices + (extra,))
    j = edit_device(j, "RTU", "RTU.d4", furnished_by="AME", verb="Furnish and Install")
    got = rules(validate(j, PB), "Packaged units")
    assert ("Packaged units", "RTU", "RTU.d4", "must_fix") in got
    assert ("Packaged units", "RTU", None, "must_fix") in got


def test_packaged_trio_missing(job):
    s = job.system("RTU")
    j = edit(job, "RTU", devices=tuple(d for d in s.devices if d.slot != "rep_assist"))
    assert ("Packaged units", "RTU", None, "must_fix") in rules(validate(j, PB))


def test_a_packaged_point_furnished_is_must_fix(job):
    shape = PB.shapes["Rooftop Unit"]
    shape2 = dc.replace(shape, slot_kinds={**shape.slot_kinds, "map_points": "point"})
    pb2 = dc.replace(PB, shapes={**PB.shapes, "Rooftop Unit": shape2})
    assert ("Packaged units", "RTU", "RTU.d2", "must_fix") in rules(validate(job, pb2))


def test_shipped_loose_must_be_install_and_wire(job):
    j = edit_device(job, "RTU", "RTU.d4", verb="Furnish and Install", furnished_by="Unit Mfr.")
    assert ("Shipped-loose devices", "RTU", "RTU.d4", "must_fix") in rules(validate(j, PB))


def test_damper_in_a_system_without_a_fan(job):
    d = Device("DH.d9", "damper_actuator", "Damper Actuator", "Furnish and Install", "AME", "AME", "AME",
               Count(1), (REF,))
    j = edit(job, "DH", devices=job.system("DH").devices + (d,))
    assert ("Dampers under their fan", "DH", "DH.d9", "check") in rules(validate(j, PB))


def test_a_stand_alone_damper_block_is_must_fix(job):
    d = Device("DM.d1", "damper_actuator", "Damper Actuator", "Furnish and Install", "AME", "AME", "AME",
               Count(1), (REF,))
    dm = dc.replace(job.system("DH"), key="DM", name="Dampers", shape="Damper Block", devices=(d,))
    j = dc.replace(job, systems=job.systems + (dm,))
    assert ("Dampers under their fan", "DM", "DM.d1", "must_fix") in rules(validate(j, PB))


def test_an_rtu_with_its_own_damper_and_a_fan_system_stays_clean(job):
    d = Device("RTU.d9", "economizer_damper", "Economizer Damper", "Furnish and Install", "AME", "AME", "AME",
               Count(1), (REF,))
    j = edit(job, "RTU", devices=job.system("RTU").devices + (d,))
    assert rules(validate(j, PB), "Dampers under their fan") == []


def test_an_air_handler_with_a_damper_is_only_a_check(job):
    d = Device("DH.d9", "mixing_damper", "Mixing Damper", "Furnish and Install", "AME", "AME", "AME",
               Count(1), (REF,))
    j = edit(job, "DH", devices=job.system("DH").devices + (d,))
    assert all(f[3] == "check" for f in rules(validate(j, PB), "Dampers under their fan"))


def test_damper_with_no_fan_system_anywhere_is_left_alone(job):
    j = Job(job.name, systems=tuple(s for s in job.systems if s.key != "EF"))
    d = Device("DH.d9", "damper_actuator", "Damper Actuator", "Furnish and Install", "AME", "AME", "AME",
               Count(1), (REF,))
    j = edit(j, "DH", devices=j.system("DH").devices + (d,))
    assert rules(validate(j, PB), "Dampers under their fan") == []


def test_duct_heater_outside_the_heater_block(job):
    d = Device("EF.d9", "duct_heater_control", "Duct Heater Signal", "Furnish", "AME", "AME", "AME",
               Count(1), (REF,))
    j = edit(job, "EF", devices=job.system("EF").devices + (d,))
    assert ("Duct heaters in one place", "EF", "EF.d9", "must_fix") in rules(validate(j, PB))


def test_vrf_comm_wiring_twice_and_split_blocks(job):
    s = job.system("VRF")
    twice = dc.replace(s.devices[0], id="VRF.d9")
    j = edit(job, "VRF", devices=s.devices + (twice,))
    assert ("VRF and split as one block", "VRF", "VRF.d9", "must_fix") in rules(validate(j, PB))
    fam = {f.name: f for f in s.families}
    a = dc.replace(s, key="V1", families=(fam["Indoor Unit"],), devices=())
    b = dc.replace(s, key="V2", families=(fam["Condensing Unit"],), devices=())
    j2 = Job(job.name, systems=(a, b))
    assert [r for r in rules(validate(j2, PB), "VRF and split as one block") if r[2] is None and r[3] == "must_fix"]


def test_a_lower_count_is_must_fix(job):
    bad = Family("Rooftop Unit", ("RTU-1",), Count(1, (), (OtherCount(2, REF),)))
    j = edit(job, "RTU", families=(bad,))
    assert ("Higher count prints", "RTU", None, "must_fix") in rules(validate(j, PB))


def test_unknown_count_needs_a_clarification(job):
    j = edit(job, "CUH", clarifications=())
    assert [r for r in rules(validate(j, PB)) if r[1] == "CUH"]
    j2 = edit(job, "CUH", clarifications=(Clarification("confirm", "x"),))
    assert validate(j2, PB) == []


def test_two_clarifications_in_a_block(job):
    j = edit(job, "CUH", clarifications=(Clarification("confirm", "x"), Clarification("per_drawings", "y")))
    assert ("One clarification per block", "CUH", None, "must_fix") in rules(validate(j, PB))
    j2 = edit(job, "CUH", clarifications=(Clarification("note", "x"), Clarification("note", "y")))
    assert ("One clarification per block", "CUH", None, "must_fix") in rules(validate(j2, PB))


def test_assumption_needs_what_and_why(job):
    j = edit_device(job, "RTU", "RTU.d4", assumption=Assumption("a duct smoke detector ships loose", " "))
    assert ("Every assumption says why", "RTU", "RTU.d4", "must_fix") in rules(validate(j, PB))
    j2 = edit_device(job, "EF", "EF.d1", flag="assumed", assumption=None)
    assert ("Every assumption says why", "EF", "EF.d1", "must_fix") in rules(validate(j2, PB))


def test_sequence_only_system_prints_no_count(job):
    j = edit(job, "DH", devices=(), clarifications=())
    assert [r for r in rules(validate(j, PB)) if r[1] == "DH" and r[3] == "must_fix"]
    j2 = edit(job, "DH", devices=(), families=(Family("Duct Heater", ("DH-1",), Count(None)),))
    assert rules(validate(j2, PB)) == []


def test_ownership_must_be_a_known_party(job):
    j = edit_device(job, "EF", "EF.d1", furnished_by="")
    assert ("Every line carries its owners", "EF", "EF.d1", "must_fix") in rules(validate(j, PB))


def test_a_device_in_two_systems(job):
    d = job.system("EF").devices[0]
    j = edit(job, "DH", devices=job.system("DH").devices + (d,))
    got = rules(validate(j, PB), "A device sits in one block")
    assert ("A device sits in one block", "EF", "EF.d1", "must_fix") in got
    assert ("A device sits in one block", "DH", "EF.d1", "must_fix") in got


def test_no_ref_is_must_fix(job):
    bad = dc.replace(job.system("EF").devices[0])
    object.__setattr__(bad, "refs", ())
    j = edit(job, "EF", devices=(bad,) + job.system("EF").devices[1:])
    assert ("Every line cites this job", "EF", "EF.d1", "must_fix") in rules(validate(j, PB))


def test_slot_not_in_shape(job):
    j = edit_device(job, "EF", "EF.d1", slot="nonsense")
    assert ("Lines follow the block's shape", "EF", "EF.d1", "must_fix") in rules(validate(j, PB))


def test_order_is_system_then_device(job):
    j = edit_device(job, "EF", "EF.d3", furnished_by="")
    j = edit_device(j, "EF", "EF.d1", furnished_by="")
    j = edit(j, "RTU", clarifications=(Clarification("note", "a"), Clarification("note", "b")))
    got = [(f.system_key, f.device_id) for f in validate(j, PB)]
    assert got == [("RTU", None), ("EF", "EF.d1"), ("EF", "EF.d3")]


def test_front_end_is_checked(job):
    fe2 = dc.replace(job.front_end, clarifications=(Clarification("note", "a"), Clarification("note", "b")))
    got = rules(validate(dc.replace(job, front_end=fe2), PB))
    assert ("One clarification per block", "", None, "must_fix") in got
