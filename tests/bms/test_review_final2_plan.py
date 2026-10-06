"""REVIEW-FINAL2 (reviewer of record): attacks on the planner fixes (lead/validator-planner-fixes, lead/final-b) and
the validator's VFD group on rebuild 70a4672. Invented ledgers only.

A strict xfail is a finding: it asserts the right behaviour and fails on 70a4672; its marker comes off with the fix.
"""
from __future__ import annotations

import pytest

from bms.model import Count, Device, Family, Job, Ref, System
from bms.playbook import load_playbook
from bms.validate import validate
from test_plan import SETTLED, _family, _ledger, _plan

NO_KIND = "type code on a schedule"
REF = Ref("S9", "invented quote", "invented place")


def test_two_split_sections_numbered_from_one_stay_two_blocks():
    ledger = _ledger()
    _family(ledger, "AC", "Ductless Split Indoor Unit", "AC-1, AC-2", 2)
    _family(ledger, "CU", "Condensing Unit", "CU-1, CU-2", 2)
    _family(ledger, "SS", "Indoor Unit", "SS-1", 1)
    _family(ledger, "ACCU", "Air Cooled Condensing Unit", "ACCU-1", 1)
    for prefix in ("AC", "CU"):
        ledger.add("sequence_match", "NORTH SPLITS", prefix, "Q3", "NORTH SPLITS", "sequence", SETTLED)
    for prefix in ("SS", "ACCU"):
        ledger.add("sequence_match", "SOUTH SPLITS", prefix, "Q4", "SOUTH SPLITS", "sequence", SETTLED)
    job = _plan(ledger)
    assert len(job.systems) == 2
    assert all(len({r.source_id for r in s.sequence_refs}) == 1 for s in job.systems)


def test_two_families_of_one_name_in_their_own_sequence_sections_stay_apart():
    ledger = _ledger()
    _family(ledger, "EF", "Exhaust Fan", "EF-1", 1)
    _family(ledger, "KEF", "Exhaust Fan", "KEF-1", 1)
    ledger.add("sequence_match", "EXHAUST FANS", "EF", "Q1", "EXHAUST FANS", "sequence", SETTLED)
    ledger.add("sequence_match", "HEATING PLANT", "KEF", "Q2", "HEATING PLANT", "sequence", SETTLED)
    assert sorted(s.key for s in _plan(ledger).systems) == ["EF", "KEF"]


@pytest.mark.xfail(strict=True, reason="REVIEW-FINAL2 F4: a no-kind code that is already one of its owner's tags "
                   "joins the block as a second family with the same tag")
def test_a_no_kind_code_that_is_already_a_tag_of_its_owner_is_not_listed_twice():
    ledger = _ledger()
    _family(ledger, "P", "Circulating Pump", "P-1, P-2", 2)
    ledger.add("family", "P-1", NO_KIND, "S1", f"P-1 ({NO_KIND}): schedule rows 1", "seed")
    ledger.add("count", "P-1", 1, "S1", f"P-1 ({NO_KIND}): schedule rows 1", "seed", SETTLED)
    tags = [t for s in _plan(ledger).systems for f in s.families for t in f.tags]
    assert len(tags) == len(set(tags))


def test_an_ahu_and_a_condensing_unit_sharing_a_number_are_not_joined():
    """Guard (passes): the split joins act on split prefixes only; AHU-1 never joins ACCU-1's block by its suffix."""
    ledger = _ledger()
    _family(ledger, "AHU", "Air Handling Unit", "AHU-1", 1)
    _family(ledger, "ACCU", "Air Cooled Condensing Unit", "ACCU-1", 1)
    _family(ledger, "AC", "Air Conditioning Unit", "AC-5", 1)
    systems = {s.key: s for s in _plan(ledger).systems}
    assert [f.tags for f in systems["AHU"].families] == [("AHU-1",)]
    assert all("AHU-1" not in f.tags for f in systems["Split System"].families)


def test_condensate_pumps_joined_on_numbers_alone_are_always_asked():
    """Guard (passes) for F6: pumps numbered 1 and 2 join a split block whose units are numbered 1 to 3 on their
    numbers alone (they could be the AHUs' pumps); the move is never silent and keeps the pumps' count."""
    ledger = _ledger()
    _family(ledger, "AHU", "Air Handling Unit", "AHU-1, AHU-2", 2)
    _family(ledger, "AC", "Air Conditioning Unit", "AC-1, AC-2, AC-3", 3)
    _family(ledger, "ACCU", "Air Cooled Condensing Unit", "ACCU-1, ACCU-2, ACCU-3", 3)
    _family(ledger, "CP", "Condensate Pump", "CP-1, CP-2", 2)
    job = _plan(ledger)
    pumps = [f for s in job.systems for f in s.families if f.name == "Condensate Pump"]
    assert [(f.tags, f.count.value) for f in pumps] == [(("CP-1", "CP-2"), 2)]
    assert any("CP-1" in q and "Confirm" in q for q in job.questions)


def _repo_packaged_shape_with_a_fan_drive(playbook):
    return next(s for s in playbook.shapes.values() if "supply_fan_vfd" in s.slot_kinds
                and "vfd_rep_assist" in s.slot_kinds)


def test_a_repo_packaged_block_with_a_fan_drive_and_a_missing_drive_line_is_must_fix():
    """(3) on the repo Playbook: a supply fan VFD line makes the drive group required; leaving out its rep line is
    must_fix, and the block without a drive needs no drive group."""
    playbook = load_playbook()
    shape = _repo_packaged_shape_with_a_fan_drive(playbook)
    trio = [s for s in shape.slots_of_kind("integration") if not s.startswith("vfd_")]
    slots = ["supply_fan_vfd", "vfd_comm_wiring", "vfd_map_points", *trio]
    lines = tuple(Device(f"X.d{n}", slot, "Invented line", "Wire", "AME", "AME", "AME", Count(1), (REF,))
                  for n, slot in enumerate(slots, 1))
    system = System("X", "Invented Unit", shape.name, "packaged", (Family("Invented Unit", ("X-1",), Count(1, (REF,))),),
                    devices=lines)
    got = [(f.what, f.severity) for f in validate(Job("Invented", (system,)), playbook) if f.rule == "Packaged units"]
    assert got == [("The 'vfd_rep_assist' integration line is missing", "must_fix")]
    no_drive = System("X", "Invented Unit", shape.name, "packaged", system.families,
                      devices=tuple(d for d in lines if "vfd" not in d.slot))
    assert [f for f in validate(Job("Invented", (no_drive,)), playbook) if f.rule == "Packaged units"] == []
