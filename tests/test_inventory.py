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


def test_one_schedule_set_out_in_two_blocks_is_one_listing():
    tags = [TagEntry(t, "Air Handling Unit", ("M-601",), ("M-101",), 3) for t in ("AHU-1", "AHU-2")]
    fans = schedule("AIR HANDLING UNIT SCHEDULE", row("AHU-1"), row("AHU-2"))
    coils = schedule("", row("AHU-1"), row("AHU-2"))
    items, totals, _ = build_inventory(catalogue_with(tags), [fans, coils])
    assert [i.category for i in items] == ["CONFIRMED", "CONFIRMED"]
    assert totals[0].scheduled == 2


def test_the_same_sheet_in_a_marked_up_copy_is_read_once():
    tags = [TagEntry("VAV-1", "Variable Air Volume Box", ("M-601",), ("M-101",), 3)]
    original = schedule("VAV BOX SCHEDULE", row("VAV-1"))
    copy = Schedule("Marked_Mech.pdf", 1, "M-601", "VAV BOX SCHEDULE", ("TAG",), (row("VAV-1"),), False, (), ())
    items, _, _ = build_inventory(catalogue_with(tags), [original, copy])
    assert [i.category for i in items] == ["CONFIRMED"]


def test_a_copy_in_another_document_is_dropped_and_said():
    tags = [TagEntry("VAV-1", "Variable Air Volume Box", ("M-601",), ("M-101",), 3)]
    original = schedule("VAV BOX SCHEDULE", row("VAV-1"))
    copy = Schedule("Marked_Mech.pdf", 1, "M-601", "VAV BOX SCHEDULE", ("TAG",), (row("VAV-1"),), False, (), ())
    _, _, flags = build_inventory(catalogue_with(tags), [original, copy])
    assert flags == ["1 schedule on M-601 in Marked_Mech.pdf not counted — the same sheet was read from Mech.pdf"]


def test_a_later_page_with_the_same_number_in_one_document_is_still_read():
    """A schedule sheet that runs onto a second page under the same number is not a copy."""
    tags = [TagEntry(t, "Variable Air Volume Box", ("M-601",), ("M-101",), 2) for t in ("VAV-1", "VAV-2")]
    first = schedule("VAV BOX SCHEDULE", row("VAV-1"), page=1)
    second = schedule("VAV BOX SCHEDULE (CONTINUED)", row("VAV-2"), page=5)
    items, totals, flags = build_inventory(catalogue_with(tags), [first, second])
    assert [(i.tag, i.category) for i in items] == [("VAV-1", "CONFIRMED"), ("VAV-2", "CONFIRMED")]
    assert totals[0].scheduled == 2 and flags == []


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
    assert item.tag == "Type-only: DIFFUSER SCHEDULE" and item.kind == "" and item.types == ("CD", "EG")
    assert item.schedule == "M-601 DIFFUSER SCHEDULE"
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


def test_a_unit_whose_prefix_is_not_in_the_equipment_list_takes_its_kind_from_the_schedule():
    from estimator.catalogue.register import PageRecord
    sheets = (Sheet(DOC, 1, "M-702", "MECHANICAL SCHEDULES", "Mechanical", ("Schedules",)),
              Sheet(DOC, 2, "M-101", "FIRST FLOOR PLAN", "Mechanical", ("Plans",)))
    pages = (PageRecord(DOC, 1, "text", "FAN SCHEDULE TXF-B TXF-2", 0, True),
             PageRecord(DOC, 2, "text", "EXHAUST TO TXF‐B ABOVE\nTXF-2 ON ROOF", 0, True))
    catalogue = Catalogue(JobFolder("26-9999", Path("26-9999"), (), ()), pages, sheets, (),
                          BidCheck("Qualifies", "", (), (), ()), (), ())
    rows = [ScheduleRow("TXF-B", {"TAG": "TXF-B"}, None, None, kind="Fan"),
            ScheduleRow("TXF-2", {"TAG": "TXF-2"}, None, None, kind="Fan"),
            ScheduleRow("RPXF-1", {"TAG": "RPXF-1"}, None, None, kind="Fan")]
    items, totals, flags = build_inventory(catalogue, [Schedule(DOC, 1, "M-702", "FAN SCHEDULE", ("TAG",), tuple(rows),
                                                                False, (), ())])
    got = by_tag(items)
    assert {t: (i.kind, i.category) for t, i in got.items()} == {
        "TXF-B": ("Fan", "CONFIRMED"), "TXF-2": ("Fan", "CONFIRMED"), "RPXF-1": ("Fan", "MISSING")}
    assert got["TXF-B"].seen_on == ("M-101",)
    by_prefix = {t.prefix: t for t in totals}
    assert (by_prefix["TXF"].kind, by_prefix["TXF"].scheduled) == ("Fan", 2)
    assert "prefix TXF isn't in the equipment list yet — added from the schedule's title" in by_prefix["TXF"].flags
    assert any("RPXF" in f and "TXF" in f and "FAN SCHEDULE" in f for f in flags)


# --- tags that aren't units: named only in the specs, or only inside a schedule's other columns -------

def test_a_tag_named_only_in_the_specs_is_left_out_and_listed_once():
    tags = [TagEntry("VAV-1", "Variable Air Volume Box", ("M-601",), ("M-101",), 2),
            TagEntry("CT-580", "Cooling Tower", (), ("Specs.pdf p.12", "Specs.pdf p.40"), 2),
            TagEntry("CH-4", "Chiller", (), ("Specs.pdf p.20",), 1),
            TagEntry("EF-9", "Exhaust Fan", (), ("M-101", "Specs.pdf p.7"), 2)]
    items, _, flags = build_inventory(catalogue_with(tags), [schedule("VAV BOX SCHEDULE", row("VAV-1"))])
    assert set(by_tag(items)) == {"VAV-1", "EF-9"}
    assert "mentioned only in the specs, not on any drawing: CH-4, CT-580" in flags


def test_with_no_schedule_in_the_set_spec_only_tags_are_still_left_out():
    tags = [TagEntry("RTU-1", "Rooftop Unit", (), ("M-101", "Specs.pdf p.3"), 2),
            TagEntry("AC-20", "Air Conditioning Unit", (), ("Specs.pdf p.344",), 1)]
    sheets = (Sheet(DOC, 2, "M-101", "FIRST FLOOR PLAN", "Mechanical", ("Plans",)),)
    items, _, flags = build_inventory(catalogue_with(tags, sheets), [])
    assert [i.tag for i in items] == ["RTU-1"]
    assert flags == ["mentioned only in the specs, not on any drawing: AC-20"]


def test_a_tag_inside_a_model_number_on_the_schedule_sheet_is_not_a_unit():
    tags = [TagEntry("EF-1", "Exhaust Fan", ("M-601",), ("M-101",), 2),
            TagEntry("B-7", "Boiler", ("M-601",), (), 1),
            TagEntry("SP-A390", "Sump Pump", ("M-601",), (), 1),
            TagEntry("P-212", "Pump", ("M-601",), ("M-101", "M-102"), 3),     # a phone number in the title block
            TagEntry("EF-5", "Exhaust Fan", ("M-601",), ("M-101",), 2)]
    fans = Schedule(DOC, 1, "M-601", "FAN SCHEDULE", ("TAG", "MODEL"),
                    (ScheduleRow("EF-1", {"TAG": "EF-1", "MODEL": "USF-15-B7"}, None, None),
                     ScheduleRow("EF-2", {"TAG": "EF-2", "MODEL": "SP-A390"}, None, None)), False, (), ())
    items, _, flags = build_inventory(catalogue_with(tags), [fans])
    got = by_tag(items)
    assert "B-7" not in got and "SP-A390" not in got and "P-212" not in got
    assert got["EF-5"].category == "PENDING"          # on the schedule sheet, in no table read: still counted by eye
    assert ("named on a schedule sheet but not as a unit (inside a model number or a note, or a one-letter "
            "prefix outside a tag column): B-7, P-212, SP-A390") in flags


def test_units_counted_from_a_schedule_sheets_text_say_so_and_are_flagged_once_per_family():
    tags = [TagEntry("RTU-1", "Rooftop Unit", ("H601",), ("M-101",), 3),
            TagEntry("RTU-2", "Rooftop Unit", ("H601",), (), 1)]
    rooftop = Schedule(DOC, 1, "H601", "ROOFTOP UNIT SCHEDULE", (), (row("RTU-1"), row("RTU-2")), False, (), (),
                       from_text=True)
    sheets = (Sheet(DOC, 1, "H601", "HVAC SCHEDULES", "Mechanical", ("Schedules",)),
              Sheet(DOC, 2, "M-101", "FIRST FLOOR PLAN", "Mechanical", ("Plans",)))
    items, totals, flags = build_inventory(catalogue_with(tags, sheets), [rooftop])
    got = by_tag(items)
    assert (got["RTU-1"].category, got["RTU-2"].category) == ("CONFIRMED", "MISSING")
    for item in got.values():
        assert item.reason.endswith("counted from the schedule sheet's text; the table itself couldn't be read "
                                    "— check the count")
    [total] = totals
    assert total.scheduled == 2
    assert "counted from the schedule sheet's text — check the count" in total.flags
    assert [f for f in flags if "RTU" in f] == [
        "2 RTU counted from the text of H601 ROOFTOP UNIT SCHEDULE — the table itself couldn't be read; check the count"]


# --- a row whose tag is really a type: counted, never 1 per row (26-0193: AC-3.0, GCF-A, EUH-1, HPAC) ---------

def _type_job():
    from estimator.catalogue.register import PageRecord
    from estimator.reading.devices import TypicalSheet
    places = [("M-701", "MECHANICAL SCHEDULES", ("Schedules",), "SCHEDULES"),
              ("M-100", "CELLAR PLAN", ("Plans",), "GCF-A\nGCF\nA\nGCF-A\nEUH-1\nTO EUH-1\nRTU-1 ABOVE\nAHU-1"),
              ("M-101", "LEVEL 01 PLAN", ("Plans",), "AC-3.0\nAC-3.0\nRTU-1\nEUH-1\nEUH-1 (TYP.)\nAHU-1\nAHU-1"),
              ("M-113", "LEVEL 13 TO 22 PLAN", ("Plans",), "AC-3.0\nEUH-1"),
              ("M-611", "REFRIGERANT RISER DIAGRAM", ("Water riser", "Diagrams"), "AC-3.0\nAC-3.0\nAC-3.0"),
              ("E-101", "LEVEL 01 POWER PLAN", ("Plans",), "EUH-1\nEUH-1\nEUH-1")]
    sheets = tuple(Sheet(DOC, n, number, title, "Electrical" if number.startswith("E") else "Mechanical", types)
                   for n, (number, title, types, _) in enumerate(places, start=1))
    pages = tuple(PageRecord(DOC, n, "text", text, 0, True) for n, (*_, text) in enumerate(places, start=1))
    tags = [TagEntry("AC-3.0", "Air Conditioning Unit", ("M-701",), ("M-101", "M-113", "M-611"), 7),
            TagEntry("GCF-A", "Fan", ("M-701",), ("M-100",), 4),
            TagEntry("EUH-1", "Electric Unit Heater", ("M-701",), ("M-100", "M-101", "M-113", "E-101"), 9),
            TagEntry("RTU-1", "Rooftop Unit", ("M-701",), ("M-100", "M-101"), 3),
            TagEntry("AHU-1", "Air Handling Unit", ("M-701",), ("M-100", "M-101"), 4)]
    catalogue = Catalogue(JobFolder("26-9999", Path("26-9999"), (), ()), pages, sheets, (),
                          BidCheck("Qualifies", "", (), (), ()), tuple(tags), ())
    typical = TypicalSheet("M-113", "LEVEL 13 TO 22 PLAN", tuple(str(n) for n in range(13, 23)), "")
    return catalogue, [typical]


def _sched(title, headers, *rows, type_only=False):
    return Schedule(DOC, 1, "M-701", title, headers,
                    tuple(ScheduleRow(tag, cells, None, None) for tag, cells in rows), type_only, (), ())


def test_a_type_row_is_counted_from_its_placements_on_the_plans_times_the_floors():
    catalogue, typicals = _type_job()
    schedules = [_sched("VRF INDOOR UNIT SCHEDULE", ("TAG",), ("AC-3.0", {"TAG": "AC-3.0"}), ("AC-4.0", {"TAG": "AC-4.0"})),
                 _sched("FAN SCHEDULE", ("TAG",), ("GCF-A", {"TAG": "GCF-A"})),
                 _sched("ELECTRIC UNIT HEATER SCHEDULE", ("UNIT NO.",), ("EUH-1", {"UNIT NO.": "EUH-1"})),
                 _sched("ROOFTOP UNIT SCHEDULE", ("TAG",), ("RTU-1", {"TAG": "RTU-1"})),
                 _sched("AIR HANDLING UNIT SCHEDULE", ("TAG",), ("AHU-1", {"TAG": "AHU-1"}))]
    items, totals, _ = build_inventory(catalogue, schedules, typicals)
    got = by_tag(items)
    # AC-3.0: a decimal size is a type. 2 on M-101, 1 on M-113 x 10 floors; the riser diagram shows 3.
    assert (got["AC-3.0"].category, got["AC-3.0"].quantity) == ("CONFIRMED", 12)
    assert "decimal" in got["AC-3.0"].reason and "M-113 1 × 10 floors" in got["AC-3.0"].reason
    assert "riser" in got["AC-3.0"].reason and "M-611 3" in got["AC-3.0"].reason
    assert got["AC-3.0"].action == "confirm"
    # AC-4.0: a type placed nowhere on the plans: PENDING, never 1.
    assert (got["AC-4.0"].category, got["AC-4.0"].quantity) == ("PENDING", None)
    # GCF-A is labelled 3 times on one plan: 3 fans of that type.
    assert (got["GCF-A"].category, got["GCF-A"].quantity) == ("CONFIRMED", 3)
    assert "labelled 3 times" in got["GCF-A"].reason
    # EUH-1: 1 on M-100 ("TO EUH-1" is a note, not a label), 2 on M-101, 1 on M-113 x 10; an electrical plan's
    # labels are that trade's own.
    assert got["EUH-1"].quantity == 13
    # RTU-1 is labelled once per plan: one unit.
    assert (got["RTU-1"].category, got["RTU-1"].quantity) == ("CONFIRMED", 1)
    # AHU-1 is labelled three times, but twice at most on one sheet (a plan and its enlarged plan): one unit.
    assert (got["AHU-1"].category, got["AHU-1"].quantity) == ("CONFIRMED", 1)
    scheduled = {t.prefix: t.scheduled for t in totals}
    assert scheduled == {"AC": 12, "GCF": 3, "EUH": 13, "RTU": 1, "AHU": 1}


def test_a_schedules_quantity_column_gives_a_types_count():
    catalogue, typicals = _type_job()
    schedules = [_sched("HEAT PUMP AIR CONDITIONING UNIT SCHEDULE", ("UNIT NO.", "SERVICE", "QUANTITY"),
                        (None, {"UNIT NO.": "HPAC", "SERVICE": "RESIDENTIAL UNITS", "QUANTITY": "719"}), type_only=True),
                 _sched("FAN SCHEDULE", ("TAG", "QTY."), ("GCF-A", {"TAG": "GCF-A", "QTY.": "(2)"}))]
    items, totals, _ = build_inventory(catalogue, schedules, typicals)
    got = by_tag(items)
    assert (got["HPAC"].kind, got["HPAC"].category, got["HPAC"].quantity) == (
        "Heat Pump Air Conditioning Unit", "CONFIRMED", 719)
    assert "QUANTITY column" in got["HPAC"].reason
    assert not [i for i in items if i.category == "TYPE ONLY"]
    assert got["GCF-A"].quantity == 2 and "QTY." in got["GCF-A"].reason      # the column, not the 3 labels
    scheduled = {t.prefix: t.scheduled for t in totals}
    assert (scheduled["HPAC"], scheduled["GCF"]) == (719, 2)
    assert next(t.kind for t in totals if t.prefix == "HPAC") == "Heat Pump Air Conditioning Unit"


# --- a tag series on the trade plans but on no readable schedule is counted, "check" (26-0478) -------------

def _plans_job(tags):
    sheets = (Sheet(DOC, 1, "H601", "HVAC SCHEDULES", "Mechanical", ("Schedules",)),
              Sheet(DOC, 2, "H101", "HVAC FLOOR PLAN", "Mechanical", ("Plans",)),
              Sheet(DOC, 3, "H111", "HVAC ROOF PLAN", "Mechanical", ("Plans",)),
              Sheet(DOC, 4, "P101", "WATER", "Plumbing", ()),
              Sheet(DOC, 5, "H501", "HVAC DETAILS", "Mechanical", ("Details",)),
              Sheet(DOC, 6, "E201", "POWER PLAN", "Electrical", ("Plans",)),
              Sheet(DOC, 7, "A101", "FLOOR PLAN", "Architectural", ("Plans",)),
              Sheet(DOC, 8, "AV7.1", "AV PLAN", "Technology", ("Plans",)))
    return catalogue_with(tags, sheets)


def test_a_tag_series_on_the_trade_plans_is_confirmed_on_plans_not_extra():
    tags = [TagEntry("RTU-1", "Rooftop Unit", ("H601",), ("H111",), 2),
            TagEntry("UH-1", "Unit Heater", (), ("H101", "E201"), 2),
            TagEntry("UH-2", "Unit Heater", (), ("H101",), 1),                  # once, but in a run of two
            TagEntry("CU-1", "Condensing Unit", (), ("H111", "E201"), 2),        # one tag, on one trade plan only
            TagEntry("DWH-1", "Domestic Water Heater", (), ("P101", "H101"), 2),  # one tag on two trade sheets
            TagEntry("ET-1", "Expansion Tank", (), ("H501", "P101"), 2),         # a detail sheet is not a plan
            TagEntry("RTU-10", "Rooftop Unit", (), ("A101", "E201"), 2)]         # its family is on a schedule
    items, totals, _ = build_inventory(_plans_job(tags), [schedule("ROOFTOP UNIT SCHEDULE", row("RTU-1"), sheet="H601")])
    got = by_tag(items)
    for tag in ("UH-1", "UH-2", "DWH-1"):
        assert (got[tag].category, got[tag].quantity, got[tag].action) == ("CONFIRMED-on-plans", 1, "confirm")
        assert got[tag].reason.endswith("not on a readable schedule — counted from the plans, check")
    assert got["CU-1"].category == "EXTRA" and got["ET-1"].category == "EXTRA" and got["RTU-10"].category == "EXTRA"
    by_prefix = {t.prefix: t for t in totals}
    assert by_prefix["UH"].scheduled == 2 and by_prefix["UH"].tags == "UH-1, UH-2"
    assert any("counted from the plans, check" in f for f in by_prefix["UH"].flags)


def test_a_family_seen_only_on_architectural_electrical_or_av_sheets_is_never_equipment():
    tags = [TagEntry("RTU-1", "Rooftop Unit", ("H601",), ("H111",), 2),
            TagEntry("SF-1", "Supply Fan", (), ("A101", "E201"), 3),
            TagEntry("SF-2", "Supply Fan", (), ("A101",), 2),
            TagEntry("CH-1", "Chiller", (), ("AV7.1",), 1)]
    items, totals, flags = build_inventory(_plans_job(tags), [schedule("ROOFTOP UNIT SCHEDULE", row("RTU-1"), sheet="H601")])
    assert [i.tag for i in items] == ["RTU-1"]
    assert {t.prefix for t in totals} == {"RTU"}
    assert ("named only on architectural, electrical, technology or AV sheets, so not equipment: CH-1, SF-1, SF-2"
            in flags)