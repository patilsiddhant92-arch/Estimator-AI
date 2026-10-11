"""Ruling L1 (HP 2, 49, 183): plan sheets that show the same floor and area are not added together. A ductwork plan, a
zoning plan, a piping plan and a controls plan of one floor are one set of placements: each tag counts the most of any
one of those sheets (a unit's tag once), and the floors and areas then add up. When that count is below what the
sheets add up to, both numbers stay in the data (`Placements.summed`, `InventoryItem.summed`, `FamilyTotal.summed`)
and the reason says them, so a '*' note can print. Invented fixtures only.

T-005a (estimator ruling 2 of 2026-10-11): a numbered unit tag is ONE unit in the whole job, however many plans show it.
So a unit's tag counts once whatever the groups, and has no "if the sheets were added up" number: its other labels
are duplicates, named in the dossier's counts line. A type's tag keeps ruling L1 and its sum."""
from pathlib import Path

import pytest

from estimator.catalogue.documents import JobFolder
from estimator.catalogue.job import Catalogue
from estimator.catalogue.qualify import BidCheck
from estimator.catalogue.register import PageRecord
from estimator.catalogue.sheet_types import Sheet
from estimator.catalogue.tags import TagEntry
from estimator.reading.inventory import build_inventory, placements, plan_groups
from estimator.reading.schedules import Schedule, ScheduleRow

DOC = "Mech.pdf"
SCHEDULES = ("M-601", "VAV SCHEDULE", ("Schedules",), "SCHEDULES")


def _sheet(page, title, number=None, document=DOC):
    return Sheet(document, page, number or f"M-{100 + page}", title, "Mechanical", ("Plans",))


def _groups(*titles, tags=None, documents=None):
    """plan_groups over one plan sheet per title (one document unless `documents` names each sheet's)."""
    sheets = [_sheet(n, title, document=(documents[n - 1] if documents else DOC)) for n, title in enumerate(titles, 1)]
    found = plan_groups([(sheet, dict(tags or {})) for sheet in sheets])
    return [found[(sheet.document, sheet.page)] for sheet in sheets]


def _one_group(groups):
    return len(set(groups)) == 1 and len(groups[0]) == len(groups)


def _apart(groups):
    return all(len(group) == 1 for group in groups)


# ---- which sheets are one plan (`plan_groups`) ----------------------------------------------------------

@pytest.mark.parametrize("one, other", [
    ("LEVEL 4 HVAC DUCTWORK PLAN", "LEVEL 4 HVAC PIPING PLAN"),
    ("LEVEL 4 HVAC DUCTWORK PLAN", "LEVEL 4 HVAC ZONING PLAN"),
    ("LEVEL 4 MECHANICAL ZONING PLAN", "LEVEL 4 CONTROLS PLAN"),
    ("FLOOR 30 - MECHANICAL ZONING PLAN", "FLOOR 30 - MECHANICAL DUCTWORK PLAN"),
    ("MECHANICAL 14TH FLOOR PIPING AND CONTROLS PLAN", "MECHANICAL 14TH FLOOR DUCTWORK PLAN"),
    ("HVAC 1ST FLOOR PIPING PLAN", "HVAC FIRST FLOOR DUCTWORK PLAN"),         # one floor, written two ways
    ("HVAC PIPING PLAN - LEVEL 2", "HVAC DUCTWORK PLAN - L-2"),
    ("LEVEL 2 AIRFLOW PLAN", "LEVEL 2 BALANCING PLAN"),
    ("MECHANICAL PLAN LEVEL 2", "MECHANICAL PIPING PLAN LEVEL 2"),            # a plan that names no trade, and a piping plan
    ("ROOF DUCTWORK PLAN", "ROOF PIPING PLAN"),
    ("BASEMENT HVAC PLAN", "BASEMENT HVAC PIPING PLAN"),
    ("LEVEL 3 EAST WING DUCTWORK PLAN", "LEVEL 3 EAST WING PIPING PLAN"),      # the same area of the floor
    ("LEVEL 3 NEW WORK DUCTWORK PLAN", "LEVEL 3 NEW WORK PIPING PLAN"),
])
def test_the_plans_of_one_floor_and_area_for_other_trades_are_one_plan_with_no_tag_evidence(one, other):
    assert _one_group(_groups(one, other))                                    # no tags at all on either sheet


def test_three_trades_of_one_floor_are_one_group_and_another_floor_is_its_own():
    groups = _groups("LEVEL 4 HVAC DUCTWORK PLAN", "LEVEL 4 HVAC ZONING PLAN", "LEVEL 4 CONTROLS PLAN",
                     "LEVEL 5 HVAC DUCTWORK PLAN")
    assert groups[0] == groups[1] == groups[2] and len(groups[0]) == 3
    assert len(groups[3]) == 1 and groups[3] != groups[0]


@pytest.mark.parametrize("one, other", [
    ("LEVEL 4 HVAC DUCTWORK PLAN", "LEVEL 5 HVAC PIPING PLAN"),                       # another floor
    ("LEVEL 4 NORTH WING DUCTWORK PLAN", "LEVEL 4 SOUTH WING PIPING PLAN"),            # another part of the floor
    ("LEVEL 4 TOWER A DUCTWORK PLAN", "LEVEL 4 TOWER B PIPING PLAN"),
    ("LEVEL 4 DUCTWORK PLAN - AREA 1", "LEVEL 4 PIPING PLAN - AREA 2"),
    ("LEVEL 4 KITCHEN DUCTWORK PLAN", "LEVEL 4 OFFICE PIPING PLAN"),                  # another place named in the title
    ("LEVEL 4 DEMOLITION PIPING PLAN", "LEVEL 4 DUCTWORK PLAN"),                       # another kind of plan
    ("LEVEL 4 ENLARGED DUCTWORK PLAN", "LEVEL 4 ENLARGED PIPING PLAN"),                # repeats part of a floor
    ("LEVELS 2 THRU 5 DUCTWORK PLAN", "LEVELS 2 THRU 5 PIPING PLAN"),                  # several floors: no one floor read
    ("LEVEL 4 HVAC DUCTWORK PLAN", "LEVEL 4 HVAC DUCTWORK PLAN"),                      # no other trade: it could be a half
    ("HVAC DUCTWORK PLAN", "HVAC PIPING PLAN"),                                        # no floor named
])
def test_sheets_of_another_floor_or_area_or_with_no_other_trade_stay_apart_without_tag_evidence(one, other):
    assert _apart(_groups(one, other))


@pytest.mark.parametrize("one, other", [
    ("LEVEL 4 HVAC DUCTWORK PLAN", "LEVEL 4 HVAC DUCT PLAN"),
    ("LEVEL 4 HVAC PIPING PLAN", "LEVEL 4 HVAC PIPE PLAN"),
    ("LEVEL 4 CONTROLS PLAN", "LEVEL 4 CONTROL PLAN"),
    ("LEVEL 4 BMS PLAN", "LEVEL 4 CONTROLS PLAN"),
    ("LEVEL 4 BAS PLAN", "LEVEL 4 DDC PLAN"),
    ("LEVEL 4 AIRFLOW BALANCE PLAN", "LEVEL 4 AIRFLOW BALANCING PLAN"),
    ("LEVEL 4 HYDRONICS PLAN", "LEVEL 4 HYDRONIC PLAN"),
])
def test_two_wordings_of_one_trade_are_one_trade_so_the_sheets_are_not_one_plan_on_their_titles(one, other):
    # DUCT and DUCTWORK name one trade: two such sheets could be the halves of a floor, so each counts (a count that
    # is too low is the worst error)
    assert _apart(_groups(one, other))


def test_a_floor_with_two_wordings_of_one_trade_is_too_uncertain_to_group_its_other_trades():
    assert _apart(_groups("LEVEL 3 HVAC DUCTWORK PLAN", "LEVEL 3 HVAC DUCT PLAN", "LEVEL 3 HVAC PIPING PLAN"))


@pytest.mark.parametrize("one, other", [
    ("LEVEL 4 HVAC DUCT PLAN", "LEVEL 4 HVAC PIPE PLAN"),               # two trades, each in its short form
    ("LEVEL 4 DUCT PLAN", "LEVEL 4 CONTROL PLAN"),
    ("LEVEL 4 BMS PLAN", "LEVEL 4 HVAC DUCTWORK PLAN"),
])
def test_two_trades_in_their_short_forms_are_still_one_plan(one, other):
    assert _one_group(_groups(one, other))


def test_a_floor_drawn_in_two_documents_is_two_sheets():
    assert _apart(_groups("LEVEL 4 HVAC DUCTWORK PLAN", "LEVEL 4 HVAC PIPING PLAN", documents=["A.pdf", "B.pdf"]))


def test_shared_unit_tags_still_make_two_sheets_of_one_title_one_plan():
    # the earlier rule stays for sheets that name no other trade: the same title words and repeated unit tags
    tags = {"VAV-1": 1, "VAV-2": 1, "VAV-3": 1, "VAV-4": 1}
    assert _one_group(_groups("LEVEL 4 HVAC DUCTWORK PLAN", "LEVEL 4 HVAC DUCTWORK PLAN", tags=tags))


# ---- the counts, and both numbers (`placements`) -------------------------------------------------------

def _catalogue(places, kind="Variable Air Volume Box"):
    """places: (sheet number, title, types, text) per page; the first is the schedule sheet."""
    sheets = tuple(Sheet(DOC, n, number, title, "Mechanical", types)
                   for n, (number, title, types, _) in enumerate(places, start=1))
    pages = tuple(PageRecord(DOC, n, "text", text, 0, True) for n, (*_, text) in enumerate(places, start=1))
    tags = sorted({line for *_, text in places for line in text.splitlines() if "-" in line})
    entries = [TagEntry(tag, kind, ("M-601",), tuple(p[0] for p in places[1:]), 4) for tag in tags]
    return Catalogue(JobFolder("26-9999", Path("26-9999"), (), ()), pages, sheets, (),
                     BidCheck("Qualifies", "", (), (), ()), tuple(entries), ())


def _schedule(*tags):
    return Schedule(DOC, 1, "M-601", "VAV SCHEDULE", ("TAG",),
                    tuple(ScheduleRow(tag, {"TAG": tag}, None, None) for tag in tags), False, (), ())


def _plan(number, title, text):
    return (number, title, ("Plans",), text)


EIGHT = "\n".join(f"VAV-{n}" for n in range(1, 9))


def test_a_unit_on_the_ductwork_and_the_zoning_plan_of_one_floor_counts_once_and_the_sum_is_kept():
    catalogue = _catalogue([SCHEDULES, _plan("M-201", "LEVEL 4 HVAC DUCTWORK PLAN", EIGHT),
                            _plan("M-301", "LEVEL 4 HVAC ZONING PLAN", EIGHT)])
    placed = placements(catalogue, ["VAV-1"])["VAV-1"]
    assert (placed.count, placed.summed) == (1, 1)                       # T-005a: one unit in the job, no sum
    assert placed.same_plan == (("M-201", "M-301"),)
    assert placed.on_plans == {"M-201": 1, "M-301": 1}                    # every sheet still named with its own labels


def test_two_floors_each_drawn_for_two_trades_add_up_by_floor():
    catalogue = _catalogue([SCHEDULES, _plan("M-201", "LEVEL 4 HVAC DUCTWORK PLAN", "VAV-1"),
                            _plan("M-301", "LEVEL 4 HVAC ZONING PLAN", "VAV-1"),
                            _plan("M-202", "LEVEL 5 HVAC DUCTWORK PLAN", "VAV-1"),
                            _plan("M-302", "LEVEL 5 HVAC ZONING PLAN", "VAV-1")])
    placed = placements(catalogue, ["VAV-1"])["VAV-1"]
    assert (placed.count, placed.summed) == (1, 1)                       # T-005a: one unit in the job (was 2, 4)
    assert placed.same_plan == (("M-201", "M-301"), ("M-202", "M-302"))


def test_three_plans_of_one_floor_count_once_where_they_added_up_to_three():
    catalogue = _catalogue([SCHEDULES, _plan("M-201", "LEVEL 4 HVAC DUCTWORK PLAN", "VAV-1"),
                            _plan("M-301", "LEVEL 4 HVAC ZONING PLAN", "VAV-1"),
                            _plan("M-401", "LEVEL 4 CONTROLS PLAN", "VAV-1")])
    placed = placements(catalogue, ["VAV-1"])["VAV-1"]
    assert (placed.count, placed.summed) == (1, 1)                       # T-005a: no sum for a unit's tag
    assert placed.same_plan == (("M-201", "M-301", "M-401"),)


def test_a_type_labelled_on_both_plans_of_a_floor_counts_the_most_of_one_sheet():
    four = "\n".join(["EBB-A"] * 4)
    catalogue = _catalogue([SCHEDULES, _plan("M-101", "HVAC DUCTWORK FIRST FLOOR PLAN", four),
                            _plan("M-201", "HVAC PIPING AND CONTROLS FIRST FLOOR PLAN", four)])
    placed = placements(catalogue, ["EBB-A"])["EBB-A"]
    assert (placed.count, placed.summed) == (4, 8)
    assert placed.total == 8                                              # every label summed stays a cross-check
    assert placed.most_on_one_sheet == 4


def test_a_type_on_a_floor_with_another_sheet_of_it_adds_the_floors_up():
    four = "\n".join(["EBB-A"] * 4)
    catalogue = _catalogue([SCHEDULES, _plan("M-101", "HVAC DUCTWORK FIRST FLOOR PLAN", four),
                            _plan("M-201", "HVAC PIPING FIRST FLOOR PLAN", four),
                            _plan("M-102", "HVAC DUCTWORK SECOND FLOOR PLAN", four),
                            _plan("M-202", "HVAC PIPING SECOND FLOOR PLAN", four)])
    placed = placements(catalogue, ["EBB-A"])["EBB-A"]
    assert (placed.count, placed.summed) == (8, 16)


def test_sheets_of_other_floors_are_added_and_there_is_no_second_number():
    catalogue = _catalogue([SCHEDULES, _plan("M-201", "LEVEL 4 HVAC DUCTWORK PLAN", "VAV-1"),
                            _plan("M-202", "LEVEL 5 HVAC DUCTWORK PLAN", "VAV-1")])
    placed = placements(catalogue, ["VAV-1"])["VAV-1"]
    assert (placed.count, placed.summed, placed.same_plan) == (1, 1, ())  # T-005a: one unit in the job (was 2)


# ---- the inventory: the item, the family and the words ---------------------------------------------------

def test_every_unit_of_a_floor_drawn_for_two_trades_counts_once_and_says_both_numbers():
    tags = [f"VAV-{n}" for n in range(1, 5)]
    four = "\n".join(tags)
    catalogue = _catalogue([SCHEDULES, _plan("M-201", "LEVEL 4 HVAC DUCTWORK PLAN", four),
                            _plan("M-301", "LEVEL 4 HVAC ZONING PLAN", four)])
    items, totals, _flags = build_inventory(catalogue, [_schedule(*tags)])
    # T-005a (ruling 2): one unit each in the job, and no sheets-added-up number for a unit's tag
    assert [(i.tag, i.category, i.quantity, i.summed) for i in items] == [(t, "CONFIRMED", 1, None) for t in tags]
    assert "if the sheets were added up" not in items[0].reason
    [total] = totals
    assert (total.prefix, total.scheduled, total.summed) == ("VAV", 4, None)


def test_a_unit_on_one_sheet_only_has_no_second_number():
    catalogue = _catalogue([SCHEDULES, _plan("M-201", "LEVEL 4 HVAC DUCTWORK PLAN", "VAV-1")])
    items, totals, _flags = build_inventory(catalogue, [_schedule("VAV-1")])
    [item] = items
    assert (item.quantity, item.summed) == (1, None)
    assert "one floor and area" not in item.reason
    assert totals[0].summed is None and not any("one floor and area" in f for f in totals[0].flags)


def test_a_type_drawn_for_two_trades_of_a_floor_says_both_numbers_in_its_row():
    four = "\n".join(["EBB-A"] * 4)
    catalogue = _catalogue([SCHEDULES, _plan("M-101", "HVAC DUCTWORK FIRST FLOOR PLAN", four),
                            _plan("M-201", "HVAC PIPING AND CONTROLS FIRST FLOOR PLAN", four)], kind="Electric Baseboard")
    schedule = Schedule(DOC, 1, "M-601", "ELECTRIC BASEBOARD SCHEDULE", ("TAG",),
                        (ScheduleRow("EBB-A", {"TAG": "EBB-A"}, None, None),), False, (), ())
    items, totals, _flags = build_inventory(catalogue, [schedule])
    [item] = items
    assert (item.quantity, item.summed) == (4, 8)
    assert "labelled 8 times on the plans" in item.reason                  # the labels as drawn
    assert "M-101 4, M-201 4" in item.reason                              # every sheet named with its own labels
    assert "M-101 and M-201 show one floor and area" in item.reason
    assert "4 counted" in item.reason and "8 if the sheets were added up" in item.reason
    assert (totals[0].scheduled, totals[0].summed) == (4, 8)


def test_a_series_row_is_one_unit_a_tag_and_gets_no_plan_sum_note():
    # "VAV-1 THRU VAV-4": the tags are the count, one unit each, whatever the plans draw (`shares` above 1): "1 counted,
    # 2 if the sheets were added up" would say the plans decide a count they do not decide
    tags = [f"VAV-{n}" for n in range(1, 5)]
    four = "\n".join(tags)
    catalogue = _catalogue([SCHEDULES, _plan("M-201", "LEVEL 4 HVAC DUCTWORK PLAN", four),
                            _plan("M-301", "LEVEL 4 HVAC ZONING PLAN", four)])
    series = Schedule(DOC, 1, "M-601", "VAV SCHEDULE", ("TAG",),
                      tuple(ScheduleRow(tag, {"TAG": "VAV-1 THRU VAV-4"}, None, None, shares=4) for tag in tags),
                      False, (), ())
    items, totals, _flags = build_inventory(catalogue, [series])
    assert [(i.tag, i.category, i.quantity, i.summed, i.action) for i in items] == [
        (t, "CONFIRMED", 1, None, "") for t in tags]
    assert not any("added up" in i.reason or "one floor and area" in i.reason for i in items)
    [total] = totals
    assert (total.scheduled, total.summed) == (4, None)
    assert not any("one floor and area" in f or "added up" in f for f in total.flags)


def test_a_unit_drawn_on_two_floors_each_for_two_trades_is_two_and_says_four():
    catalogue = _catalogue([SCHEDULES, _plan("M-201", "LEVEL 4 HVAC DUCTWORK PLAN", "VAV-1"),
                            _plan("M-301", "LEVEL 4 HVAC ZONING PLAN", "VAV-1"),
                            _plan("M-202", "LEVEL 5 HVAC DUCTWORK PLAN", "VAV-1"),
                            _plan("M-302", "LEVEL 5 HVAC ZONING PLAN", "VAV-1")])
    items, totals, _flags = build_inventory(catalogue, [_schedule("VAV-1")])
    [item] = items
    assert (item.quantity, item.summed) == (1, None)                     # T-005a: one unit in the job (was 2, 4)
    assert (totals[0].scheduled, totals[0].summed) == (1, None)


def test_two_sheets_of_one_trade_and_floor_make_that_floor_too_uncertain_to_group_without_tag_evidence():
    # two ductwork sheets with one title (the halves of a floor, or two buildings) and a piping plan of the floor:
    # which of them the piping plan shows is not known, so a type is never cut to the most of one of them
    assert _apart(_groups("LEVEL 3 HVAC DUCTWORK PLAN", "LEVEL 3 HVAC DUCTWORK PLAN", "LEVEL 3 HVAC PIPING PLAN"))


def test_twins_in_one_document_do_not_stop_another_documents_floor_from_grouping():
    groups = _groups("LEVEL 3 HVAC DUCTWORK PLAN", "LEVEL 3 HVAC DUCTWORK PLAN",
                     "LEVEL 3 HVAC DUCTWORK PLAN", "LEVEL 3 HVAC PIPING PLAN",
                     documents=["A.pdf", "A.pdf", "B.pdf", "B.pdf"])
    assert len(groups[0]) == len(groups[1]) == 1
    assert groups[2] == groups[3] and len(groups[2]) == 2


def test_twins_still_group_by_the_tag_evidence_they_always_had():
    tags = {"VAV-1": 1, "VAV-2": 1, "VAV-3": 1, "VAV-4": 1}
    groups = _groups("LEVEL 3 HVAC DUCTWORK PLAN", "LEVEL 3 HVAC DUCTWORK PLAN", "LEVEL 3 HVAC PIPING PLAN", tags=tags)
    assert groups[0] == groups[1] == groups[2] and len(groups[0]) == 3          # shared unit tags: one plan, as before


# ---- the dossier's counts line counts with the same groups, and names both numbers ----------------------------

def test_a_floor_of_two_units_drawn_for_two_trades_counts_two_not_four(tmp_path):
    from estimator.writing.dossier import build_dossier
    from test_dossier_plan_areas import DWG, _catalogue as dossier_catalogue, _line, _page, _reading
    from test_dossier_plan_areas import _sheet as dossier_sheet

    pages = [_page(DWG, 1, "EF-1\nEF-2"), _page(DWG, 2, "EF-1\nEF-2")]
    sheets = [dossier_sheet(1, "M-101", "LEVEL 4 HVAC DUCTWORK PLAN"), dossier_sheet(2, "M-201", "LEVEL 4 HVAC PIPING PLAN")]
    d = build_dossier(dossier_catalogue(pages, sheets, ["EF-1", "EF-2"]), _reading(), tmp_path)
    assert d.counts["EF"]["plan_placements"] == 2                       # two units; two sheets of one floor added up gave 4
    assert "EF-1 is on 2 plans (M-101, M-201), counted once, 1" in _line("EF", d)     # T-005a: duplicates named


def test_eight_boxes_on_three_plans_of_one_floor_count_eight_and_the_next_floor_adds(tmp_path):
    from estimator.writing.dossier import build_dossier
    from test_dossier_plan_areas import DWG, _catalogue as dossier_catalogue, _line, _page, _reading
    from test_dossier_plan_areas import _sheet as dossier_sheet

    floor4 = "\n".join(f"VAV-{n}" for n in range(1, 9))
    floor5 = "\n".join(f"VAV-{n}" for n in range(9, 17))
    pages = [_page(DWG, 1, floor4), _page(DWG, 2, floor4), _page(DWG, 3, floor4), _page(DWG, 4, floor5),
             _page(DWG, 5, floor5)]
    sheets = [dossier_sheet(1, "M-101", "LEVEL 4 HVAC DUCTWORK PLAN"), dossier_sheet(2, "M-201", "LEVEL 4 HVAC ZONING PLAN"),
              dossier_sheet(3, "M-301", "LEVEL 4 CONTROLS PLAN"), dossier_sheet(4, "M-102", "LEVEL 5 HVAC DUCTWORK PLAN"),
              dossier_sheet(5, "M-202", "LEVEL 5 HVAC ZONING PLAN")]
    d = build_dossier(dossier_catalogue(pages, sheets, [f"VAV-{n}" for n in range(1, 17)]), _reading(), tmp_path)
    assert d.counts["VAV"]["plan_placements"] == 16                     # not 40
    line = _line("VAV", d)
    # T-005a (ruling 2): units only, one unit each in the job however the sheets group: the duplicates are named per
    # tag, and no group note says another number
    assert "counted as one plan" not in line
    assert "VAV-1 is on 3 plans (M-101, M-201, M-301), counted once, 1" in line


@pytest.mark.parametrize("text, said", [
    ("EF-1\nEF-2", "a unit's tag is counted once in the job, however often the plan labels it"),
    ("EBB-A\nEBB-A", "a type's tag counts the most labels of one sheet of each floor and area, however often the plan "
                     "labels it"),
    ("EBB-A\nEBB-A\nEBB-1\nEBB-1", "a type's tag counts the most labels of one sheet of each floor and area, a unit's "
                                   "tag once in the job, however often the plan labels it"),
])
def test_the_counts_lines_notes_say_floor_and_area_not_the_earlier_rules_words(tmp_path, text, said):
    from estimator.writing.dossier import build_dossier
    from test_dossier_plan_areas import DWG, _catalogue as dossier_catalogue, _line, _page, _reading
    from test_dossier_plan_areas import _sheet as dossier_sheet

    pages = [_page(DWG, 1, text), _page(DWG, 2, text)]
    sheets = [dossier_sheet(1, "M-101", "LEVEL 4 HVAC DUCTWORK PLAN"), dossier_sheet(2, "M-201", "LEVEL 4 HVAC PIPING PLAN")]
    tags = sorted(set(text.split("\n")))
    d = build_dossier(dossier_catalogue(pages, sheets, tags), _reading(), tmp_path)
    prefix = tags[0].split("-")[0]
    notes = _line(prefix, d).split("Reading notes:", 1)[1]
    if "EBB-A" in text:          # T-005a: a group note only where a type's count depends on the group
        assert "M-101 and M-201 counted as one plan, " in notes and "): same floor and area; check" in notes
    assert f"the labels on the plan sheets add up to {2 * len(text.split(chr(10)))}; {said}" in notes
    assert "same floor title" not in notes and "same units" not in notes and "on each plan" not in notes


def test_the_family_flag_reaches_the_dossiers_counts_line_with_both_numbers(tmp_path):
    from types import SimpleNamespace

    from estimator.writing.dossier import build_dossier

    tags = [f"VAV-{n}" for n in range(1, 5)]
    four = "\n".join(tags)
    catalogue = _catalogue([SCHEDULES, _plan("M-201", "LEVEL 4 HVAC DUCTWORK PLAN", four),
                            _plan("M-301", "LEVEL 4 HVAC ZONING PLAN", four)])
    items, totals, _flags = build_inventory(catalogue, [_schedule(*tags)])
    reading = SimpleNamespace(schedules=(_schedule(*tags),), totals=tuple(totals), devices=(), typicals=(), notes=(),
                              backbone=(), versions=(), supersessions=(), inventory=tuple(items), legend=(), flags=())
    line = next(line for line in build_dossier(catalogue, reading, tmp_path).text.splitlines() if "] VAV (" in line)
    assert "plan placements 4 (M-201 4; M-301 4)" in line
    # T-005a (ruling 2): no sheets-added-up number for unit tags; the duplicates are named per tag
    assert "if the sheets were added up" not in line
    assert "VAV-1 is on 2 plans (M-201, M-301), counted once, 1" in line
