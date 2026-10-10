"""The type-tag check ("labelled N times on the plans"), FINAL-A task 2. FINAL-G added every sheet up, so a floor drawn
on a ductwork plan and on its piping and controls plan counted a type twice. Ruling L1 (2026-10-10) replaces that
for sheets that show the same floor and area: they are one plan, and a type's tag counts the most of any one of them
(the sheets added up stay in `Placements.summed` and the item's `summed`, for a '*' note). Different floors add up.
Invented fixtures only."""
from pathlib import Path

from estimator.catalogue.documents import JobFolder
from estimator.catalogue.job import Catalogue
from estimator.catalogue.qualify import BidCheck
from estimator.catalogue.register import PageRecord
from estimator.catalogue.sheet_types import Sheet
from estimator.catalogue.tags import TagEntry
from estimator.reading.inventory import build_inventory, placements, plan_areas
from estimator.reading.schedules import Schedule, ScheduleRow
from estimator.writing import dossier

DOC = "Mech.pdf"


def _job(places, tags):
    """places: (sheet number, title, types, text) per page; the first is the schedule sheet."""
    sheets = tuple(Sheet(DOC, n, number, title, "Mechanical", types)
                   for n, (number, title, types, _) in enumerate(places, start=1))
    pages = tuple(PageRecord(DOC, n, "text", text, 0, True) for n, (*_, text) in enumerate(places, start=1))
    entries = [TagEntry(tag, "Electric Baseboard", ("M-601",), tuple(p[0] for p in places[1:]), 4) for tag in tags]
    return Catalogue(JobFolder("26-9999", Path("26-9999"), (), ()), pages, sheets, (),
                     BidCheck("Qualifies", "", (), (), ()), tuple(entries), ())


def _schedule(*tags):
    return Schedule(DOC, 1, "M-601", "ELECTRIC BASEBOARD SCHEDULE", ("TAG",),
                    tuple(ScheduleRow(tag, {"TAG": tag}, None, None) for tag in tags), False, (), ())


SCHEDULES = ("M-601", "MECHANICAL SCHEDULES", ("Schedules",), "SCHEDULES")
FOUR = "\n".join(["EBB-A"] * 4)


def test_a_type_tag_on_a_floor_drawn_twice_counts_the_most_of_one_sheet_and_says_the_sum():
    catalogue = _job([SCHEDULES, ("M-101", "HVAC DUCTWORK FIRST FLOOR PLAN", ("Plans",), FOUR),
                      ("M-201", "HVAC PIPING AND CONTROLS FIRST FLOOR PLAN", ("Plans",), FOUR)], ["EBB-A"])
    placed = placements(catalogue, ["EBB-A"])["EBB-A"]
    assert placed.total == 8                                  # every label summed, a cross-check only
    assert placed.most_on_one_sheet == 4
    assert (placed.count, placed.summed) == (4, 8)            # L1 (replaces FINAL-G's 8): one floor, one set of places
    items, _totals, _flags = build_inventory(catalogue, [_schedule("EBB-A")])
    item = next(i for i in items if i.tag == "EBB-A")
    assert (item.quantity, item.summed) == (4, 8)
    assert "labelled 8 times on the plans" in item.reason
    # every sheet is named with its own labels, never "same plan as"; the drop says both numbers
    assert "M-101 4, M-201 4" in item.reason and "same plan" not in item.reason
    assert "4 counted, 8 if the sheets were added up" in item.reason


def test_a_type_tag_on_two_floors_adds_up():
    catalogue = _job([SCHEDULES, ("M-201", "PIPING AND CONTROLS FIRST FLOOR PLAN", ("Plans",), FOUR),
                      ("M-202", "PIPING AND CONTROLS SECOND FLOOR PLAN", ("Plans",), FOUR)], ["EBB-A"])
    placed = placements(catalogue, ["EBB-A"])["EBB-A"]
    assert placed.total == 8
    assert "same plan" not in placed.plans_text()


def test_the_plan_areas_group_nothing_and_every_sheet_is_still_named():
    assert dossier.plan_areas is plan_areas
    catalogue = _job([SCHEDULES, ("M-101", "HVAC DUCTWORK FIRST FLOOR PLAN", ("Plans",), FOUR),
                      ("M-102", "HVAC DUCTWORK SECOND FLOOR PLAN", ("Plans",), FOUR),
                      ("M-201", "HVAC PIPING AND CONTROLS FIRST FLOOR PLAN", ("Plans",), FOUR),
                      ("M-202", "HVAC PIPING AND CONTROLS SECOND FLOOR PLAN", ("Plans",), FOUR)], ["EBB-A"])
    placed = placements(catalogue, ["EBB-A"])["EBB-A"]
    assert placed.total == 16                                 # two floors, each drawn twice: every label summed
    assert placed.plans_text() == "M-101 4, M-102 4, M-201 4, M-202 4"
    assert (placed.count, placed.summed) == (8, 16)           # L1: each floor counts once, the floors add up
