"""REVIEW-FINAL2 (reviewer of record): attacks on plan_areas counting, the inventory's type-tag check and the count
cause printed in the client's quantity note (rebuild 70a4672). Invented fixtures only.

A strict xfail is a finding: it asserts the right behaviour and fails on 70a4672; its marker comes off with the fix.
"""
from pathlib import Path

import pytest

from estimator.catalogue.documents import JobFolder
from estimator.catalogue.job import Catalogue
from estimator.catalogue.qualify import BidCheck
from estimator.catalogue.register import PageRecord
from estimator.catalogue.sheet_types import Sheet
from estimator.catalogue.tags import TagEntry
from estimator.reading.inventory import placements
from estimator.writing.dossier import build_dossier
from test_count_cause_note import _catalogue, _family_count, _note, _page, _reading, _sheet

TYPES = ["EBB-A", "EBB-B", "EBB-C", "EBB-D"]
# one floor's typical type tags: EBB-A at four places, EBB-B at two, EBB-C and EBB-D once each (8 heaters)
FLOOR = "\n".join(["EBB-A"] * 4 + ["EBB-B"] * 2 + ["EBB-C", "EBB-D"])


def _job(plans, schedule_tags):
    sheets = [_sheet(n, number, title) for n, (number, title, _t) in enumerate(plans, start=1)]
    pages = [_page(n, text) for n, (_n, _title, text) in enumerate(plans, start=1)]
    at = len(plans) + 1
    pages.append(_page(at, "SCHEDULE\n" + "\n".join(schedule_tags)))
    sheets.append(_sheet(at, "M-601", "SCHEDULES", types=("Schedules",)))
    tags = sorted({t for *_x, text in plans for t in text.split("\n")} | set(schedule_tags))
    return _catalogue(pages, sheets, tags), _reading("SCHEDULE", schedule_tags, at)


TWO_DIFFERENT_FLOORS = [
    pytest.param(("LEVEL ONE MECHANICAL PLAN", "LEVEL TWO MECHANICAL PLAN"), id="floor-named-in-words"),
    pytest.param(("MECHANICAL PLAN - DORM WING", "MECHANICAL PLAN - CLASSROOM WING"), id="no-floor-in-title"),
    pytest.param(("FIRST FLOOR PLAN - TOWER 1", "FIRST FLOOR PLAN - TOWER 2"), id="two-towers-one-document"),
    pytest.param(("LOWER ROOF PLAN", "UPPER ROOF PLAN"), id="lower-and-upper-roof"),
]


@pytest.mark.parametrize("titles", TWO_DIFFERENT_FLOORS)
def test_two_different_areas_with_the_same_typical_tags_add_up(titles, tmp_path):
    catalogue, reading = _job([("M-101", titles[0], FLOOR), ("M-102", titles[1], FLOOR)], TYPES)
    d = build_dossier(catalogue, reading, tmp_path)
    assert d.counts["EBB"]["plan_placements"] == 16          # 8 heaters on each of two different areas


def test_the_note_never_claims_a_floor_drawn_twice_for_two_different_floors(tmp_path):
    catalogue, reading = _job([("M-101", "LEVEL ONE MECHANICAL PLAN", FLOOR),
                               ("M-102", "LEVEL TWO MECHANICAL PLAN", FLOOR)], TYPES)
    note = _note(_family_count(catalogue, reading, "EBB", tmp_path), "Baseboard Heater", tuple(TYPES))
    assert note and "drawn on two plan sheets" not in note[0]


def _inventory_job(places, tags):
    sheets = tuple(Sheet("Mech.pdf", n, number, title, "Mechanical", types)
                   for n, (number, title, types, _) in enumerate(places, start=1))
    pages = tuple(PageRecord("Mech.pdf", n, "text", text, 0, True) for n, (*_, text) in enumerate(places, start=1))
    entries = [TagEntry(tag, "Electric Baseboard", ("M-601",), tuple(p[0] for p in places[1:]), 4) for tag in tags]
    return Catalogue(JobFolder("26-9999", Path("26-9999"), (), ()), pages, sheets, (),
                     BidCheck("Qualifies", "", (), (), ()), tuple(entries), ())


def test_the_inventory_adds_up_a_type_tag_on_two_towers_first_floors():
    four = "\n".join(["EBB-A"] * 4)
    catalogue = _inventory_job([("M-601", "MECHANICAL SCHEDULES", ("Schedules",), "SCHEDULES"),
                                ("M-101", "FIRST FLOOR PLAN - TOWER 1", ("Plans",), four),
                                ("M-102", "FIRST FLOOR PLAN - TOWER 2", ("Plans",), four)], ["EBB-A"])
    assert placements(catalogue, ["EBB-A"])["EBB-A"].total == 8


def test_the_same_floor_named_two_ways_in_one_document_is_one_plan_for_two_trades(tmp_path):
    """"LEVEL 1" and "FIRST FLOOR" name one floor. FINAL-I summed them, 12, because the title words differed; ruling L1
    reads the floor, however it is written ("LEVEL 02" and "2ND FLOOR" too), so the plan and the controls plan of a
    floor are one plan: 6, each pair named as one plan with the sum beside it."""
    boxes1, boxes2 = "VAV-1\nVAV-2\nVAV-3", "VAV-4\nVAV-5\nVAV-6"
    catalogue, reading = _job([("M-101", "HVAC LEVEL 1 PLAN", boxes1), ("M-102", "HVAC LEVEL 02 PLAN", boxes2),
                               ("M-201", "CONTROLS FIRST FLOOR PLAN", boxes1),
                               ("M-202", "CONTROLS 2ND FLOOR PLAN", boxes2)], [f"VAV-{n}" for n in range(1, 7)])
    d = build_dossier(catalogue, reading, tmp_path)
    assert d.counts["VAV"]["plan_placements"] == 6
    line = next(line for line in d.text.splitlines() if "] VAV (" in line)
    assert "M-101 and M-201 counted as one plan, 3 (6 if they are two places)" in line
    assert "M-102 and M-202 counted as one plan, 3 (6 if they are two places)" in line


def test_a_type_tag_once_on_each_of_two_floors_is_not_called_one_unit_shown_again(tmp_path):
    catalogue, reading = _job([("M-101", "HVAC FIRST FLOOR PLAN", "CUH-A\nVAV-1"),
                               ("M-102", "HVAC SECOND FLOOR PLAN", "CUH-A\nVAV-2")], ["CUH-A"])
    note = _note(_family_count(catalogue, reading, "CUH", tmp_path), "Cabinet Unit Heater", ("CUH-A",))
    # T-005e (ruling 15): the counts in brackets on the line, no "*Qty." note
    assert note and "(2 per plan placements" in note[0]
    assert "shown on several plans" not in note[0]


def test_the_cause_note_prints_no_tag_sheet_or_hint_on_a_merged_job(tmp_path):
    """Guard (passes): whatever cause prints, the client note carries no tag, sheet number or "check" hint."""
    catalogue, reading = _job([("M-101", "LEVEL ONE MECHANICAL PLAN", FLOOR),
                               ("M-102", "LEVEL TWO MECHANICAL PLAN", FLOOR + "\nEBB-A")], TYPES)
    (note,) = _note(_family_count(catalogue, reading, "EBB", tmp_path), "Baseboard Heater", ("EBB-A",))
    for banned in ("EBB-", "M-101", "M-102", "check", "schedule's quantity"):
        assert banned not in note
