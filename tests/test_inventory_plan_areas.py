"""The type-tag check ("labelled N times on the plans") counts a floor drawn on two plan sheets once (FINAL-A,
task 2): the inventory's placements use the dossier's plan areas, so a typical type tag on a ductwork plan and on
the piping and controls plan of the same floor is not doubled. Different floors still add up. Invented fixtures
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


def test_a_type_tag_on_a_floor_drawn_twice_counts_the_places_of_one_drawing():
    catalogue = _job([SCHEDULES, ("M-101", "HVAC DUCTWORK FIRST FLOOR PLAN", ("Plans",), FOUR),
                      ("M-201", "HVAC PIPING AND CONTROLS FIRST FLOOR PLAN", ("Plans",), FOUR)], ["EBB-A"])
    placed = placements(catalogue, ["EBB-A"])["EBB-A"]
    assert placed.total == 4                                  # not 8: the floor is drawn twice
    assert placed.most_on_one_sheet == 4
    items, _totals, _flags = build_inventory(catalogue, [_schedule("EBB-A")])
    item = next(i for i in items if i.tag == "EBB-A")
    assert item.quantity == 4
    assert "labelled 4 times on the plans" in item.reason
    # the repeat sheet is still named, but as the same plan, never as more placements
    assert "M-201 4 same plan as M-101" in item.reason


def test_a_type_tag_on_two_floors_adds_up():
    catalogue = _job([SCHEDULES, ("M-201", "PIPING AND CONTROLS FIRST FLOOR PLAN", ("Plans",), FOUR),
                      ("M-202", "PIPING AND CONTROLS SECOND FLOOR PLAN", ("Plans",), FOUR)], ["EBB-A"])
    placed = placements(catalogue, ["EBB-A"])["EBB-A"]
    assert placed.total == 8
    assert "same plan" not in placed.plans_text()


def test_the_inventory_groups_the_plan_sheets_as_the_dossier_does():
    assert dossier.plan_areas is plan_areas
    catalogue = _job([SCHEDULES, ("M-101", "HVAC DUCTWORK FIRST FLOOR PLAN", ("Plans",), FOUR),
                      ("M-102", "HVAC DUCTWORK SECOND FLOOR PLAN", ("Plans",), FOUR),
                      ("M-201", "HVAC PIPING AND CONTROLS FIRST FLOOR PLAN", ("Plans",), FOUR),
                      ("M-202", "HVAC PIPING AND CONTROLS SECOND FLOOR PLAN", ("Plans",), FOUR)], ["EBB-A"])
    placed = placements(catalogue, ["EBB-A"])["EBB-A"]
    assert placed.total == 8                                  # two floors, each drawn twice
    assert placed.plans_text() == "M-101 4, M-102 4, M-201 4 same plan as M-101, M-202 4 same plan as M-102"
