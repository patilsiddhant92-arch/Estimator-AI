"""The type-tag check ("labelled N times on the plans"), FINAL-A task 2, rule changed by FINAL-G: no two plan sheets
are ever merged, so a type's tag counts at every place on every sheet, floors applied. A floor drawn on a ductwork
plan and on its piping and controls plan may so count a type twice: the higher count, never an undercount (the
merge read titles, and every title form it did not read lost units). Different floors add up. Invented fixtures
only."""
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


def test_a_type_tag_on_a_floor_drawn_twice_counts_every_place():
    catalogue = _job([SCHEDULES, ("M-101", "HVAC DUCTWORK FIRST FLOOR PLAN", ("Plans",), FOUR),
                      ("M-201", "HVAC PIPING AND CONTROLS FIRST FLOOR PLAN", ("Plans",), FOUR)], ["EBB-A"])
    placed = placements(catalogue, ["EBB-A"])["EBB-A"]
    assert placed.total == 8                                  # FINAL-G: was 4 (merged); the higher count
    assert placed.most_on_one_sheet == 4
    items, _totals, _flags = build_inventory(catalogue, [_schedule("EBB-A")])
    item = next(i for i in items if i.tag == "EBB-A")
    assert item.quantity == 8
    assert "labelled 8 times on the plans" in item.reason
    # every sheet is named with its own labels, never "same plan as"
    assert "M-101 4, M-201 4" in item.reason and "same plan" not in item.reason


def test_a_type_tag_on_two_floors_adds_up():
    catalogue = _job([SCHEDULES, ("M-201", "PIPING AND CONTROLS FIRST FLOOR PLAN", ("Plans",), FOUR),
                      ("M-202", "PIPING AND CONTROLS SECOND FLOOR PLAN", ("Plans",), FOUR)], ["EBB-A"])
    placed = placements(catalogue, ["EBB-A"])["EBB-A"]
    assert placed.total == 8
    assert "same plan" not in placed.plans_text()


def test_the_inventory_never_groups_the_plan_sheets():
    assert dossier.plan_areas is plan_areas
    catalogue = _job([SCHEDULES, ("M-101", "HVAC DUCTWORK FIRST FLOOR PLAN", ("Plans",), FOUR),
                      ("M-102", "HVAC DUCTWORK SECOND FLOOR PLAN", ("Plans",), FOUR),
                      ("M-201", "HVAC PIPING AND CONTROLS FIRST FLOOR PLAN", ("Plans",), FOUR),
                      ("M-202", "HVAC PIPING AND CONTROLS SECOND FLOOR PLAN", ("Plans",), FOUR)], ["EBB-A"])
    placed = placements(catalogue, ["EBB-A"])["EBB-A"]
    assert placed.total == 16                                 # two floors, each drawn twice: every sheet counts
    assert placed.plans_text() == "M-101 4, M-102 4, M-201 4, M-202 4"
