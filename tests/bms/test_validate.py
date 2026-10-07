"""Workstream 3: the validators, on the invented sample job and small variations of it."""
from __future__ import annotations

import dataclasses as dc
import json
from pathlib import Path

import pytest

from bms.model import Assumption, Clarification, Count, Device, Family, Job, OtherCount, Ref, System
from bms.playbook import load_playbook
from bms.validate import RULE, validate

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


def test_every_rule_name_is_a_heading_of_the_repo_playbook():
    assert {k for k, v in RULE.items() if v not in load_playbook().rules} == set()


def test_an_ame_device_on_a_packaged_unit_is_a_check_and_the_trio_twice_is_must_fix(job):
    """VAL-2, rules "Packaged units" (AME's work includes "any device the documents explicitly give to the controls
    contractor"), "Explicit assignment always wins" and "Mixed ownership device by device": an AME-furnished device
    on a packaged unit may be the documents' own assignment, so it is a check; the trio twice stays a must_fix."""
    s = job.system("RTU")
    extra = Device("RTU.d9", "map_points", "Points", "Furnish", "AME", "AME", "AME", Count(2), (REF,))
    j = edit(job, "RTU", devices=s.devices + (extra,))
    j = edit_device(j, "RTU", "RTU.d4", furnished_by="AME", verb="Furnish and Install")
    found = [f for f in validate(j, PB) if f.rule == "Packaged units"]
    got = rules(found)
    assert ("Packaged units", "RTU", "RTU.d4", "check") in got
    assert ("Packaged units", "RTU", "RTU.d4", "must_fix") not in got
    assert ("Packaged units", "RTU", None, "must_fix") in got
    check = next(f for f in found if f.device_id == "RTU.d4")
    assert "controls contractor" in check.fix


def test_an_ame_ddc_controller_on_a_packaged_unit_is_must_fix(job):
    """VAL-2, rule "No AME controller on a packaged unit": "Never write 'Furnish and Install DDC Controller' for a
    unit on factory controls"; the controller slot stays a must_fix."""
    d = Device("RTU.d9", "controller", "DDC Controller", "Furnish and Install", "AME", "AME", "AME", Count(2), (REF,))
    j = edit(job, "RTU", devices=job.system("RTU").devices + (d,))
    assert ("Packaged units", "RTU", "RTU.d9", "must_fix") in rules(validate(j, PB))


def test_an_empty_packaged_block_with_a_reason_needs_no_integration_lines(job):
    """VAL-5, rule "Packaged units": the three integration lines are AME's work on a packaged unit it writes; a block
    left out with its reason has no lines, so no trio is missing."""
    j = edit(job, "RTU", devices=(), no_scope_reason="the documents give the unit no BMS connection")
    assert rules(validate(j, PB), "Packaged units") == []


def test_packaged_trio_missing(job):
    s = job.system("RTU")
    j = edit(job, "RTU", devices=tuple(d for d in s.devices if d.slot != "rep_assist"))
    assert ("Packaged units", "RTU", None, "must_fix") in rules(validate(j, PB))


def test_a_packaged_point_furnished_is_must_fix(job):
    shape = PB.shapes["Rooftop Unit"]
    shape2 = dc.replace(shape, slot_kinds={**shape.slot_kinds, "map_points": "point"})
    pb2 = dc.replace(PB, shapes={**PB.shapes, "Rooftop Unit": shape2})
    assert ("Packaged units", "RTU", "RTU.d2", "must_fix") in rules(validate(job, pb2))


# The repo shapes give every packaged shape a drive group (the integration slots vfd_comm_wiring, vfd_map_points,
# vfd_rep_assist) before its factory controls group; the sample Rooftop Unit gets the same here.
_VFD_GROUP = ("vfd_comm_wiring", "vfd_map_points", "vfd_rep_assist")


def _pb_with_drive_group():
    shape = PB.shapes["Rooftop Unit"]
    order = ("vfd_control", "shipped_loose", *_VFD_GROUP, "comm_wiring", "map_points", "rep_assist")
    kinds = {**shape.slot_kinds, "vfd_control": "point", **{s: "integration" for s in _VFD_GROUP}}
    shape2 = dc.replace(shape, line_order=order, slot_kinds=kinds,
                        under={**shape.under, "vfd_rep_assist": "vfd_map_points"})
    return dc.replace(PB, shapes={**PB.shapes, "Rooftop Unit": shape2})


def _vfd_line(slot, n):
    return Device(f"RTU.v{n}", slot, "Invented VFD line", "Wire", "AME", "AME", "AME", Count(1), (REF,))


def test_the_vfd_integration_lines_are_required_only_on_a_packaged_unit_with_a_drive(job):
    pb = _pb_with_drive_group()
    # no drive in the block: the factory controls group alone is complete
    assert rules(validate(job, pb), "Packaged units") == []
    # a VFD line in the block: the whole drive group is required
    j = edit(job, "RTU", devices=(_vfd_line("vfd_control", 1),) + job.system("RTU").devices)
    got = [f for f in validate(j, pb) if f.rule == "Packaged units"]
    assert {f.what for f in got} == {f"The '{s}' integration line is missing" for s in _VFD_GROUP}
    assert {f.severity for f in got} == {"must_fix"}
    # a part of the drive group: the rest of it is required
    j = edit(job, "RTU", devices=job.system("RTU").devices + (_vfd_line("vfd_comm_wiring", 1),))
    got = [f.what for f in validate(j, pb) if f.rule == "Packaged units"]
    assert sorted(got) == [f"The '{s}' integration line is missing" for s in ("vfd_map_points", "vfd_rep_assist")]
    # the factory controls group is still required whether or not there is a drive
    j = edit(job, "RTU", devices=tuple(d for d in job.system("RTU").devices if d.slot != "map_points"))
    assert [f.what for f in validate(j, pb) if f.rule == "Packaged units"] == [
        "The 'map_points' integration line is missing"]


def test_a_packaged_cabinet_heater_of_the_repo_playbook_with_no_drive_is_clean():
    repo = load_playbook()
    lines = tuple(Device(f"CUH.d{n}", slot, "Invented line", "Furnish", "AME", "AME", "AME", Count(2), (REF,))
                  for n, slot in enumerate(("comm_wiring", "map_points", "rep_assist"), 1))
    system = System("CUH", "Cabinet Unit Heater", "EUH / CUH / UH", "packaged",
                    (Family("Cabinet Unit Heater", ("CUH-1", "CUH-2"), Count(2, (REF,))),), devices=lines)
    assert [f.what for f in validate(Job("Invented", (system,)), repo) if f.rule == "Packaged units"] == []


def test_shipped_loose_must_be_install_and_wire(job):
    j = edit_device(job, "RTU", "RTU.d4", verb="Furnish and Install", furnished_by="Unit Mfr.")
    assert ("Shipped-loose devices", "RTU", "RTU.d4", "must_fix") in rules(validate(j, PB))


def test_a_wire_line_and_an_install_and_wire_line_by_other_trades_are_not_shipped_loose():
    """VAL-1, rules "Factory-installed devices" ("Wire <device> (Furnished by Unit Mfr.)" when the sequence gives the
    wiring to AME), "Shipped-loose devices", "Verb from the three answers" (another party furnishes and installs, AME
    only wires: Wire; another party furnishes, AME installs and wires: Install and Wire) and "Other trades in
    brackets" ("(Furnished by Mechanical Contractor)" for condensate pumps and float switches)."""
    repo = load_playbook()
    lines = (Device("PU.d1", "other_wire", "Filter Differential Pressure Switch", "Wire", "Unit Mfr.", "Unit Mfr.",
                    "AME", Count(2, (REF,)), (REF,)),
             Device("PU.d2", "other_install_and_wire", "Condensate Float Switch", "Install and Wire",
                    "Mechanical Contractor", "AME", "AME", Count(2, (REF,)), (REF,)))
    system = System("PU", "Packaged Units", "Packaged ERU / RTU / AHU", "packaged",
                    (Family("Packaged Unit", ("PU-1", "PU-2"), Count(2, (REF,))),), devices=lines)
    assert rules(validate(Job("Invented", (system,)), repo), "Shipped-loose devices") == []


def test_damper_in_a_system_without_a_fan(job):
    d = Device("DH.d9", "damper_actuator", "Damper Actuator", "Furnish and Install", "AME", "AME", "AME",
               Count(1), (REF,))
    j = edit(job, "DH", devices=job.system("DH").devices + (d,))
    assert ("Dampers under their fan", "DH", "DH.d9", "check") in rules(validate(j, PB))


def test_a_stand_alone_damper_block_is_at_most_a_check(job):
    """VAL-3, rules "Untraced dampers in their own block" (when a damper's fan cannot be traced, the dampers form one
    Motorized Dampers block of their own) and "Unclaimed dampers in their own block": a damper block the Playbook
    allows is never a must_fix; one of an unknown shape is at most a check."""
    d = Device("DM.d1", "damper_actuator", "Damper Actuator", "Furnish and Install", "AME", "AME", "AME",
               Count(1), (REF,))
    dm = dc.replace(job.system("DH"), key="DM", name="Dampers", shape="Damper Block", devices=(d,))
    j = dc.replace(job, systems=job.systems + (dm,))
    assert rules(validate(j, PB), "Dampers under their fan") == [("Dampers under their fan", "DM", "DM.d1", "check")]


def _repo_system(key, shape, family, devices, control="field"):
    return System(key, f"Invented {shape}", shape, control, (Family(family, (f"{key}-1",), Count(1, (REF,))),),
                  devices=tuple(Device(f"{key}.d{n}", slot, "Invented Device", "Furnish and Install", "AME", "AME",
                                       "AME", Count(1, (REF,)), (REF,)) for n, slot in enumerate(devices, 1)))


def test_a_motorized_dampers_block_beside_a_fan_block_is_no_must_fix():
    """VAL-3, rules "Untraced dampers in their own block" and "Unclaimed dampers in their own block" (stair-top vent
    dampers have their own block): the Motorized Dampers and Stair / Elevator Vent blocks of the repo Playbook are
    allowed beside an exhaust fan block; their dampers fill their own shape's slot, so no finding."""
    repo = load_playbook()
    j = Job("Invented", (_repo_system("EF", "Exhaust Fan", "Exhaust Fan", ("controller", "start_stop_status")),
                         _repo_system("MD", "Motorized Dampers", "Motorized Damper", ("damper_actuator",)),
                         _repo_system("SV", "Stair / Elevator Vent", "Stair / Elevator Vent", ("damper_actuator",))))
    assert rules(validate(j, repo), "Dampers under their fan") == []
    assert [f for f in validate(j, repo) if f.severity == "must_fix"] == []


def test_an_rtu_with_its_own_damper_and_a_fan_system_stays_clean(job):
    d = Device("RTU.d9", "economizer_damper", "Economizer Damper", "Furnish and Install", "AME", "AME", "AME",
               Count(1), (REF,))
    j = edit(job, "RTU", devices=job.system("RTU").devices + (d,))
    assert rules(validate(j, PB), "Dampers under their fan") == []


def test_an_air_handler_with_its_own_outside_air_damper_has_no_damper_finding():
    """VAL-3, rule "Dampers under their fan": a damper actuator is written in the block of the fan or unit it serves
    ("the unit's outside air damper"); an air handler's own oa_damper slot is where the Playbook puts it, even when
    it is the block's only damper line, and even with an exhaust fan block in the job."""
    repo = load_playbook()
    j = Job("Invented", (_repo_system("EF", "Exhaust Fan", "Exhaust Fan", ("controller", "start_stop_status")),
                         _repo_system("AHU", "Air Handling Unit", "Air Handling Unit", ("controller", "oa_damper")),
                         _repo_system("AH2", "Air Handling Unit", "Air Handling Unit", ("oa_damper",))))
    assert rules(validate(j, repo), "Dampers under their fan") == []


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


def _heater_point(dev_id="EF.d9"):
    return Device(dev_id, "other_point", "Invented Electric Duct Heater Status", "Furnish", "AME", "AME", "AME",
                  Count(1), (REF,))


def test_a_duct_heater_device_by_its_words_in_a_served_unit_is_must_fix(job):
    j = edit(job, "EF", devices=job.system("EF").devices + (_heater_point(),))
    assert ("Duct heaters in one place", "EF", "EF.d9", "must_fix") in rules(validate(j, PB))


def test_a_duct_heater_device_with_no_heater_system_in_the_job_is_left_alone(job):
    j = edit(job, "EF", devices=job.system("EF").devices + (_heater_point(),))
    j = dc.replace(j, systems=tuple(s for s in j.systems if s.key != "DH"))
    assert rules(validate(j, PB), "Duct heaters in one place") == []


def test_an_empty_heater_system_while_another_carries_the_heaters_is_a_check_naming_both(job):
    j = edit(job, "EF", devices=job.system("EF").devices + (_heater_point(),))
    j = edit(j, "DH", devices=())
    found = [f for f in validate(j, PB) if f.rule == "Duct heaters in one place"]
    assert ("Duct heaters in one place", "DH", None, "check") in rules(found)
    check = next(f for f in found if f.severity == "check")
    assert "DH" in check.what and "EF" in check.what


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


def test_a_block_with_a_sourced_count_and_no_lines_is_not_sequence_only(job):
    """VAL-4, rule "Systems named only in the sequence": a system the sequence names but no drawing shows. A family
    count with a source is a drawing or schedule showing it, so an empty block with its reason is left out, not
    sequence-only."""
    j = edit(job, "DH", devices=(), clarifications=(), no_scope_reason="the duct heaters are by others")
    assert rules(validate(j, PB), RULE["sequence"]) == []
    assert [r for r in rules(validate(j, PB)) if r[1] == "DH"] == [(RULE["left_out"], "DH", None, "check")]


def test_a_sequence_only_system_prints_qty_hash_with_its_clarification(job):
    """VAL-4, rule "Systems named only in the sequence": printed with its integration lines, "Qty (##)", and the
    clarification "*Quantity per plumbing drawings" (or the drawings of the trade that shows it). A family with no
    counted source and a sequence reference is sequence-only, with lines or without."""
    rtu = Family("Rooftop Unit", ("RTU-1",), Count(None))
    j = edit(job, "RTU", families=(rtu,), clarifications=())
    assert rules(validate(j, PB), RULE["sequence"]) == [(RULE["sequence"], "RTU", None, "check")]
    j2 = edit(j, "RTU", clarifications=(Clarification("per_drawings", "Quantity per mechanical drawings"),))
    assert rules(validate(j2, PB), RULE["sequence"]) == []
    # a count no source gives is invented: clear it
    j3 = edit(j2, "RTU", families=(Family("Rooftop Unit", ("RTU-1",), Count(2)),))
    assert rules(validate(j3, PB), RULE["sequence"]) == [(RULE["sequence"], "RTU", None, "must_fix")]


def test_ownership_must_be_a_known_party(job):
    j = edit_device(job, "EF", "EF.d1", furnished_by="")
    assert (RULE["owner"], "EF", "EF.d1", "must_fix") in rules(validate(j, PB))


def test_a_front_end_device_that_repeats_an_id_is_a_duplicate(job):
    from bms.model import FrontEnd
    device = job.system("EF").devices[0]
    front = job.front_end or FrontEnd(mode="new-system")
    shared = dc.replace(job, front_end=dc.replace(front, devices=front.devices + (device,)))
    got = rules(validate(shared, PB), RULE["once"])
    assert (RULE["once"], "EF", device.id, "must_fix") in got
    assert (RULE["once"], "", device.id, "must_fix") in got
    twice = dc.replace(job, front_end=FrontEnd(mode="new-system", devices=(device, device)))
    front_only = rules(validate(twice, PB), RULE["once"])
    assert (RULE["once"], "", device.id, "must_fix") in front_only


def test_a_device_in_two_systems(job):
    d = job.system("EF").devices[0]
    j = edit(job, "DH", devices=job.system("DH").devices + (d,))
    got = rules(validate(j, PB), RULE["once"])
    assert (RULE["once"], "EF", "EF.d1", "must_fix") in got
    assert (RULE["once"], "DH", "EF.d1", "must_fix") in got


def test_no_ref_is_must_fix(job):
    bad = dc.replace(job.system("EF").devices[0])
    object.__setattr__(bad, "refs", ())
    j = edit(job, "EF", devices=(bad,) + job.system("EF").devices[1:])
    assert ("Every line cites this job", "EF", "EF.d1", "must_fix") in rules(validate(j, PB))


def test_slot_not_in_shape(job):
    j = edit_device(job, "EF", "EF.d1", slot="nonsense")
    assert (RULE["slot"], "EF", "EF.d1", "must_fix") in rules(validate(j, PB))


def test_order_is_system_then_device(job):
    j = edit_device(job, "EF", "EF.d3", furnished_by="")
    j = edit_device(j, "EF", "EF.d1", furnished_by="")
    j = edit(j, "RTU", clarifications=(Clarification("note", "a"), Clarification("note", "b")))
    got = [(f.system_key, f.device_id) for f in validate(j, PB)]
    assert got == [("RTU", None), ("EF", "EF.d1"), ("EF", "EF.d3")]


def test_a_system_with_no_lines_is_a_check_with_the_writers_reason(job):
    j = edit(job, "DH", devices=(), clarifications=(Clarification("note", "the invented heaters have no BMS work"),))
    found = [f for f in validate(j, PB) if f.rule == RULE["left_out"]]
    assert [(f.system_key, f.device_id, f.severity) for f in found] == [("DH", None, "check")]
    assert "left out: no lines written" in found[0].what
    assert "the invented heaters have no BMS work" in found[0].what


def test_render_validate_and_the_intake_share_one_cleanup_module():
    """M1: one module holds the id pattern, the issued-ids decision, the label stripper and the place lookup."""
    import inspect

    import bms.ai as ai_mod
    import bms.render as render_mod
    import bms.validate as validate_mod
    from bms import citations
    for name in ("SourceIds", "strip_label", "per_drawings_text", "clarification_text"):
        assert hasattr(citations, name), name
    assert "from bms.render import" not in inspect.getsource(ai_mod)
    for module, copies in ((ai_mod, ("_ONE_SOURCE", "_SOURCE_RUN", "_SOURCE_ID", "_BRACKETED", "_LEAD_LABEL",
                                     "_strip_lead", "_discipline", "_place_of", "_without_ids", "_NOT_A_PLACE")),
                           (render_mod, ("_ONE_ID", "_ID_GROUP", "_SHEET", "_LABEL", "_PER", "_no_ids", "_place",
                                         "_strip_labels", "_per_drawings_text", "_DANGLING", "_TRADE")),
                           (validate_mod, ("_SOURCE_ID",))):
        for name in copies:
            assert not hasattr(module, name), (module.__name__, name)
    source = inspect.getsource(validate_mod) + inspect.getsource(render_mod) + inspect.getsource(ai_mod)
    assert "[SQIFC]" not in source


@pytest.mark.parametrize("issued", [(), (Ref("F1", "x", "ledger fact"),)])
def test_tags_and_sheet_numbers_shaped_like_ids_are_no_check(job, issued):
    """I5: a family tag (issued or not) or an unissued sheet number is never reported."""
    vrf = job.system("VRF")
    j = edit(job, "VRF", families=(dc.replace(vrf.families[0], tags=("F1", "F2")),) + vrf.families[1:],
             clarifications=(Clarification("note", "Fans F1 and F2 serve the kitchen; see civil sheet C101."),),
             sequence_refs=vrf.sequence_refs + issued)
    assert rules(validate(j, PB), RULE["ids"]) == []


def _ids_found(j):
    return [f for f in validate(j, PB) if f.rule == RULE["ids"]]


def test_an_unissued_lookalike_is_no_finding_and_one_joined_to_an_issued_id_is_a_check(job):
    """The estimator's ruling of 2026-10-05 (secondary review M2): 'Fan C2 serves the lab' prints as written and is
    no finding (C2 is more likely a tag); 'per S9 and S999' cites S999 beside the issued S9, so S999 is a check."""
    j = edit(job, "VRF", clarifications=(Clarification("note", "Fan C2 serves the lab"),))
    assert _ids_found(j) == []
    j2 = edit(job, "VRF", clarifications=(Clarification("note", "the units per S9 and S999"),))
    assert sorted((f.severity, "S999" in f.what) for f in _ids_found(j2)) == [("check", True), ("must_fix", False)]


def test_an_issued_id_in_any_case_is_must_fix(job):
    """I3: 's9' is the issued S9."""
    j = edit(job, "VRF", clarifications=(Clarification("note", "the units per s9"),))
    assert [f.severity for f in _ids_found(j)] == ["must_fix"]


def test_issued_ids_in_device_names_and_named_exceptions_are_must_fix(job):
    """I4: a device name and a named exception print too."""
    j = edit_device(job, "RTU", "RTU.d4", name="Smoke Detector per S12")
    assert (RULE["ids"], "RTU", "RTU.d4", "must_fix") in rules(validate(j, PB))
    j2 = dc.replace(job, exceptions=(dc.replace(job.exceptions[0], text="Fire alarm system by others per S14"),))
    # FA is no planned system: the finding is the whole job's, so the review page and the revise find no block
    assert [(f.system_key, f.severity) for f in _ids_found(j2) if "S14" in f.what] == [("", "must_fix")]
    # an exception of a planned system is the whole job's too (secondary review M4): no writer writes an exception,
    # so a system revise could never fix it
    j3 = dc.replace(job, exceptions=(dc.replace(job.exceptions[0], system_key="EF", text="Fans by others per S14"),))
    assert [(f.system_key, f.severity) for f in _ids_found(j3) if "S14" in f.what] == [("", "must_fix")]


def test_a_tag_range_shaped_like_ids_is_no_check(job):
    """I1: the family tag 'F1-F4' protects F1 to F4, even when F1 is issued."""
    vrf = job.system("VRF")
    j = edit(job, "VRF", families=(dc.replace(vrf.families[0], tags=("F1-F4",)),) + vrf.families[1:],
             clarifications=(Clarification("note", "Fans F1 thru F4 and F2 serve the kitchen"),),
             sequence_refs=(Ref("F1", "x", "ledger fact"),))
    assert _ids_found(j) == []


def test_a_family_tag_shaped_like_an_issued_id_is_no_check(job):
    tags = ("F1", "C2", "I3", "Q4", "S5")
    vrf = job.system("VRF")
    j = edit(job, "VRF", families=(dc.replace(vrf.families[0], tags=tags),) + vrf.families[1:],
             clarifications=(Clarification("confirm", "the controls for units F1, C2, I3, Q4 and S5"),),
             sequence_refs=tuple(Ref(t, "x", "ledger fact") for t in tags))
    assert rules(validate(j, PB), RULE["ids"]) == []


def test_q_i_f_and_c_ids_in_wording_are_a_check(job):
    j = edit_device(job, "RTU", "RTU.d4", assumption=Assumption("one detector", "Q3, I12, F8 and C2a say so"))
    assert (RULE["ids"], "RTU", "RTU.d4", "check") in rules(validate(j, PB))


def test_issued_source_ids_in_assumption_or_clarification_wording_are_must_fix(job):
    j = edit_device(job, "RTU", "RTU.d4", assumption=Assumption("one detector per unit", "S12 note 2 says so"))
    assert (RULE["ids"], "RTU", "RTU.d4", "must_fix") in rules(validate(j, PB))
    j2 = edit(job, "VRF", clarifications=(Clarification("confirm", "Branch selector count per S41"),),
              sequence_refs=(Ref("S41", "q", "M-002, Invented.pdf page 3"),))      # an id the run issued
    assert (RULE["ids"], "VRF", None, "must_fix") in rules(validate(j2, PB))
    j3 = edit(job, "VRF", clarifications=(Clarification("confirm", "count per the SD-12 sheet; 5S7 is not an id"),))
    assert rules(validate(j3, PB), RULE["ids"]) == []
    assert RULE["ids"] == "Assumption wording has no source ids"


def test_a_long_clarification_or_assumption_is_a_check(job):
    long_text = "x" * 221
    j = edit(job, "VRF", clarifications=(Clarification("confirm", long_text),))
    assert (RULE["long_note"], "VRF", None, "check") in rules(validate(j, PB))
    assert rules(validate(edit(job, "VRF", clarifications=(Clarification("confirm", "x" * 220),)), PB),
                 RULE["long_note"]) == []
    j2 = edit_device(job, "RTU", "RTU.d4", assumption=Assumption("y" * 120, "z" * 120))
    assert (RULE["long_assumption"], "RTU", "RTU.d4", "check") in rules(validate(j2, PB))


def test_a_one_per_unit_line_above_the_header_count_is_must_fix_and_any_other_line_a_check(job):
    """VAL-9, rules "Never undershoot" and "Line quantity" ("Identical lines for several units are one line with the
    total"): a controller or a start/stop line is one per unit, so its quantity above the header count means the
    header undershoots (must_fix); a damper line may total several per unit, so above the header is a check."""
    j = edit_device(job, "EF", "EF.d1", quantity=Count(9))
    found = [f for f in validate(j, PB) if f.rule == RULE["header_under"]]
    assert [(f.system_key, f.device_id, f.severity) for f in found] == [("EF", "EF.d1", "must_fix")]
    assert found[0].what.endswith("device quantity 9 is higher than the header count 3: print the higher count")
    j2 = edit_device(job, "EF", "EF.d3", quantity=Count(9))
    found2 = [f for f in validate(j2, PB) if f.rule == RULE["header_under"]]
    assert [(f.system_key, f.device_id, f.severity) for f in found2] == [("EF", "EF.d3", "check")]
    assert "print the higher count" not in found2[0].what


def test_three_fans_with_six_damper_actuators_is_no_must_fix(job):
    """VAL-9, rule "Line quantity": identical lines for several units are one line with the total; two dampers on
    each of 3 fans print as one line of 6, which never forces the fan count to 6."""
    j = edit_device(job, "EF", "EF.d3", quantity=Count(6, (REF,)))
    assert [f for f in validate(j, PB) if f.severity == "must_fix"] == []


def test_an_unknown_printed_count_with_a_known_other_is_must_fix(job):
    """VAL-18, rules "Higher count prints" and "Never undershoot" (estimator ruling D9: a count's value is the highest
    whenever any count exists; None only when no count exists at all)."""
    fam = Family("Exhaust Fan", ("EF-1",), Count(None, (), (OtherCount(5, REF),)))
    found = [f for f in validate(edit(job, "EF", families=(fam,)), PB) if f.rule == RULE["higher"]]
    assert [(f.system_key, f.device_id, f.severity) for f in found] == [("EF", None, "must_fix")]
    assert "5" in found[0].fix


def test_a_device_quantity_at_or_below_the_header_count_is_clean(job):
    j = edit_device(job, "EF", "EF.d3", quantity=Count(3))
    assert rules(validate(j, PB), RULE["header_under"]) == []
    # the header already prints the family's highest count: a device at that count is clean
    fam = Family("Exhaust Fan", ("EF-1",), Count(3, (), (OtherCount(9, REF),)))
    j2 = edit_device(edit(job, "EF", families=(fam,)), "EF", "EF.d3", quantity=Count(9))
    assert rules(validate(j2, PB), RULE["header_under"]) == []


def test_a_damper_family_under_a_fan_does_not_set_the_header_count(job):
    ef = job.system("EF")
    j = edit(job, "EF", families=ef.families + (Family("Motorized Damper", (), Count(1)),))
    assert rules(validate(j, PB), RULE["header_under"]) == []


def test_front_end_is_checked(job):
    fe2 = dc.replace(job.front_end, clarifications=(Clarification("note", "a"), Clarification("note", "b")))
    got = rules(validate(dc.replace(job, front_end=fe2), PB))
    assert ("One clarification per block", "", None, "must_fix") in got


def test_a_line_counted_from_a_family_below_its_printed_count_is_a_check(job):
    """AI-1: the Exhaust Fan count is 5 but EF.d1, counted from it (its quantity cites the family's source S6),
    still carries 3. Device quantity is what prints and prices: a possible silent undershoot, a check (a line can
    count fewer than its family). A line not counted from the family (EF.d2 cites no source, EF.d3 its dampers)
    is not this check's."""
    s = job.system("EF")
    family = s.families[0]
    j = edit(job, "EF", families=(dc.replace(family, count=dc.replace(family.count, value=5)),))
    got = rules(validate(j, PB), "Never undershoot")
    assert got == [("Never undershoot", "EF", "EF.d1", "check")]
    j = edit_device(j, "EF", "EF.d1", quantity=dc.replace(s.devices[0].quantity, value=5))
    assert rules(validate(j, PB), "Never undershoot") == []


# ---- VAL-6, VAL-7, VAL-13, VAL-15 ------------------------------------------------------------------------------

def test_a_system_with_no_lines_gives_the_writers_no_scope_reason(job):
    """VAL-6: the writer's reason for a block with no lines is its no_scope_reason, not only a clarification."""
    j = edit(job, "DH", devices=(), no_scope_reason="the invented heaters are controlled by their own panel")
    found = [f for f in validate(j, PB) if f.rule == RULE["left_out"]]
    assert [(f.system_key, f.device_id, f.severity) for f in found] == [("DH", None, "check")]
    assert "the invented heaters are controlled by their own panel" in found[0].what
    assert "gave no reason" not in found[0].what


def test_a_shape_not_in_the_playbook_is_a_must_fix(job):
    """VAL-7: a shape name the Playbook does not have would stop the render; the validator says so first."""
    j = edit(job, "EF", shape="Exhaust Fann")
    got = [f for f in validate(j, PB) if f.rule == RULE["slot"]]
    assert [(f.system_key, f.device_id, f.severity) for f in got] == [("EF", None, "must_fix")]
    assert "Exhaust Fann" in got[0].what and "not in the Playbook" in got[0].what
    assert rules(validate(edit(job, "EF", shape=""), PB), RULE["slot"]) == []      # no shape is an untemplated system


def test_a_citation_with_no_place_is_a_must_fix(job):
    """VAL-13: a ref with an empty where cites no place of this job."""
    j = edit_device(job, "EF", "EF.d1", refs=(Ref("S9", "quote", ""),))
    got = rules(validate(j, PB), RULE["cites"])
    assert got == [(RULE["cites"], "EF", "EF.d1", "must_fix")]
    what = [f.what for f in validate(j, PB) if f.rule == RULE["cites"]][0]
    assert "missing its source id, quote or place" in what


def test_an_unknown_device_quantity_with_no_clarification_is_a_check(job):
    """VAL-15: a line whose wording prints its quantity, with the quantity unknown, prints "(Qty. ##)": the block
    needs a confirm or per-drawings clarification."""
    j = edit_device(job, "EF", "EF.d1", quantity=Count(None))
    assert rules(validate(j, PB), RULE["unknown"]) == [(RULE["unknown"], "EF", "EF.d1", "check")]
    # with a confirm clarification, or on a line whose wording prints no quantity, it is clean
    j2 = edit(j, "EF", clarifications=(Clarification("confirm", "confirm the controller count"),))
    assert rules(validate(j2, PB), RULE["unknown"]) == []
    j3 = edit_device(job, "EF", "EF.d2", quantity=Count(None))
    assert rules(validate(j3, PB), RULE["unknown"]) == []


def test_a_front_end_citation_with_no_place_is_a_check(job):
    """VAL-13: a front-end ref comes from the planner, which no writer can fix: an empty where there is a check;
    an empty source id or quote stays a must_fix."""
    fe = job.front_end
    d = dc.replace(fe.devices[0], refs=(Ref("S9", "quote", ""),))
    j = dc.replace(job, front_end=dc.replace(fe, devices=(d,) + fe.devices[1:]))
    assert rules(validate(j, PB), RULE["cites"]) == [(RULE["cites"], "", d.id, "check")]
    d2 = dc.replace(d, refs=(Ref("", "quote", ""),))
    j2 = dc.replace(job, front_end=dc.replace(fe, devices=(d2,) + fe.devices[1:]))
    assert rules(validate(j2, PB), RULE["cites"]) == [(RULE["cites"], "", d2.id, "must_fix")]
