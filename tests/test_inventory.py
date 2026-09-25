"""The equipment inventory: every tag in exactly one of the estimator's categories (Quantity rules)."""
from pathlib import Path

from estimator.catalogue.documents import JobFolder
from estimator.catalogue.job import Catalogue
from estimator.catalogue.qualify import BidCheck
from estimator.catalogue.sheet_types import Sheet
from estimator.catalogue.tags import TagEntry
from estimator.reading.inventory import build_inventory, compact_tags
from estimator.reading.schedules import Schedule, ScheduleRow

DOC = "Mech.pdf"


def catalogue_with(tags, sheets=None):
    sheets = sheets if sheets is not None else (
        Sheet(DOC, 1, "M-601", "MECHANICAL SCHEDULES", "Mechanical", ("Schedules",)),
        Sheet(DOC, 2, "M-101", "FIRST FLOOR PLAN", "Mechanical", ("Plans",)),
        Sheet(DOC, 3, "M-102", "SECOND FLOOR PLAN", "Mechanical", ("Plans",)),
        Sheet(DOC, 4, "M-501", "AIR RISER DIAGRAM", "Mechanical", ("Air riser",)))
    return Catalogue(JobFolder("26-9999", Path("26-9999"), (), ()), (), sheets, (),
                     BidCheck("Qualifies", "", (), (), ()), tuple(tags), ())


def row(tag, existing=False):
    return ScheduleRow(tag, {"TAG": tag or ""}, None, None, existing)


def schedule(title, *rows, sheet="M-601", page=1, type_only=False):
    return Schedule(DOC, page, sheet, title, ("TAG",), tuple(rows), type_only, (), ())


def by_tag(items):
    return {item.tag: item for item in items}


def test_every_tag_lands_in_one_category():
    tags = [TagEntry("VAV-1", "Variable Air Volume Box", ("M-601",), ("M-101", "M-501"), 3),
            TagEntry("VAV-2", "Variable Air Volume Box", ("M-601",), (), 1),
            TagEntry("VAV-3", "Variable Air Volume Box", ("M-601",), ("M-102",), 3),
            TagEntry("VAV-9", "Variable Air Volume Box", (), ("M-101", "M-102"), 2),
            TagEntry("VAV-10", "Variable Air Volume Box", (), ("M-102",), 1),
            TagEntry("AHU-1", "Air Handling Unit", ("M-601",), ("M-101",), 2),
            TagEntry("EF-5", "Exhaust Fan", ("M-601",), ("M-101",), 2)]
    schedules = [schedule("VAV BOX SCHEDULE", row("VAV-1"), row("VAV-2"), row("VAV-3"), row("VAV-3")),
                 schedule("AIR HANDLING UNIT SCHEDULE", row("AHU-1", existing=True))]
    items, totals, pairs = build_inventory(catalogue_with(tags), schedules)
    got = by_tag(items)
    assert {tag: item.category for tag, item in got.items()} == {
        "VAV-1": "CONFIRMED", "VAV-2": "MISSING", "VAV-3": "DISCREPANCY", "VAV-9": "EXTRA",
        "VAV-10": "ORPHANED", "AHU-1": "EXISTING", "EF-5": "PENDING"}
    assert got["VAV-1"].quantity == 1 and got["VAV-1"].seen_on == ("M-101", "M-501") and got["VAV-1"].action == ""
    assert got["VAV-1"].schedule == "M-601 VAV BOX SCHEDULE"
    assert got["VAV-1"].reason == "On the schedule (M-601) and on 2 other drawing sheets (M-101, M-501)"
    assert got["VAV-2"].reason.startswith("On the schedule only; no plan shows it") and got["VAV-2"].action == "confirm"
    assert "listed 2 times" in got["VAV-3"].reason and got["VAV-3"].action == "confirm"
    assert got["VAV-9"].action == "exclude pending" and got["VAV-9"].quantity is None
    assert got["VAV-10"].action == "exclude pending" and "only once" in got["VAV-10"].reason
    assert got["AHU-1"].quantity == 0 and "not new work" in got["AHU-1"].reason
    assert got["EF-5"].quantity is None and got["EF-5"].action == "confirm"
    vav = next(t for t in totals if t.prefix == "VAV")
    assert vav.kind == "Variable Air Volume Box" and vav.scheduled == 3 and vav.tags == "VAV-1 thru VAV-3"
    assert any("listed twice" in f for f in vav.flags) and any("not on a schedule" in f for f in vav.flags)
    assert pairs == []


def test_a_tag_on_two_schedule_sheets_is_a_discrepancy():
    tags = [TagEntry("FCU-7-1", "Fan Coil Unit", ("M-601", "M-602"), ("M-101",), 3)]
    schedules = [schedule("FAN COIL UNIT SCHEDULE", row("FCU-7-1")),
                 schedule("FAN COIL UNIT SCHEDULE", row("FCU-7-1"), sheet="M-602", page=5)]
    items, totals, _ = build_inventory(catalogue_with(tags), schedules)
    [item] = items
    assert item.category == "DISCREPANCY" and "M-601" in item.reason and "M-602" in item.reason
    assert totals[0].scheduled == 1


def test_the_same_sheet_in_a_marked_up_copy_is_read_once():
    tags = [TagEntry("VAV-1", "Variable Air Volume Box", ("M-601",), ("M-101",), 3)]
    original = schedule("VAV BOX SCHEDULE", row("VAV-1"))
    copy = Schedule("Marked_Mech.pdf", 1, "M-601", "VAV BOX SCHEDULE", ("TAG",), (row("VAV-1"),), False, (), ())
    items, _, _ = build_inventory(catalogue_with(tags), [original, copy])
    assert [i.category for i in items] == ["CONFIRMED"]


def test_a_scheduled_tag_the_tag_index_never_saw_is_missing():
    items, totals, _ = build_inventory(catalogue_with([]), [schedule("VAV BOX SCHEDULE", row("VAV-1"), row("VAV-2"))])
    assert [(i.tag, i.category) for i in items] == [("VAV-1", "MISSING"), ("VAV-2", "MISSING")]
    assert totals[0].scheduled == 2


def test_no_schedule_in_the_set_leaves_every_tag_pending():
    sheets = (Sheet(DOC, 2, "M-101", "FIRST FLOOR PLAN", "Mechanical", ("Plans",)),)
    tags = [TagEntry("AHU-1", "Air Handling Unit", (), ("M-101",), 4), TagEntry("EF-1", "Exhaust Fan", (), ("M-101",), 1)]
    items, totals, _ = build_inventory(catalogue_with(tags, sheets), [])
    assert {(i.tag, i.category, i.quantity) for i in items} == {("AHU-1", "PENDING", None), ("EF-1", "PENDING", None)}
    assert all(i.reason.startswith("No schedule in the set") for i in items)
    assert totals == []


def test_a_type_only_schedule_is_counted_on_the_plans():
    rows = (ScheduleRow(None, {"TYPE": "CD"}, None, None), ScheduleRow(None, {"TYPE": "EG"}, None, None))
    diffusers = Schedule(DOC, 1, "M-601", "DIFFUSER SCHEDULE", ("TYPE",), rows, True, (), ())
    items, totals, _ = build_inventory(catalogue_with([]), [diffusers])
    [item] = items
    assert item.category == "TYPE ONLY" and item.quantity is None and item.action == "confirm"
    assert item.kind == "DIFFUSER SCHEDULE" and "CD, EG" in item.tag
    assert "count them on the plans" in item.reason


def test_unequal_pairs_say_check_the_pairing():
    tags = [TagEntry(t, "x", ("M-601",), ("M-101",), 2) for t in ("HP-1", "HP-2", "HP-3", "ACCU-1", "AC-1", "CU-1")]
    schedules = [schedule("HEAT PUMP SCHEDULE", row("HP-1"), row("HP-2"), row("HP-3")),
                 schedule("CONDENSING UNIT SCHEDULE", row("ACCU-1"), row("CU-1")),
                 schedule("AC SCHEDULE", row("AC-1"))]
    _, _, pairs = build_inventory(catalogue_with(tags), schedules)
    assert len(pairs) == 1 and pairs[0].startswith("check the pairing: 3 HP, 1 ACCU")


def test_compact_tag_lists():
    tags = [f"VAV-{n}" for n in range(101, 113)] + ["VAV-114"]
    assert compact_tags(tags) == "VAV-101 thru VAV-112, VAV-114"
    assert compact_tags(["VAV-21-01", "VAV-21-02", "VAV-21-03", "VAV-100A"]) == "VAV-21-01 thru VAV-21-03, VAV-100A"
    assert compact_tags(["EF-1", "EF-2"]) == "EF-1, EF-2"
