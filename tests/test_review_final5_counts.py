"""REVIEW-FINAL5 (reviewer of record): the FINAL-G counting rule (rebuild e91dc46) attacked for undercounts.

The rule under review: a unit's tag counts once over every plan sheet (times the most floors of any typical sheet it
is on); a type's tag, a type code and a numbered tag drawn as a type is (3 places with 4 on one sheet, as drawn) are
summed over the sheets; no title is read to merge; `plan_area_doubts` only writes a hint.

Each strict xfail asserts the right behaviour and fails on e91dc46 by assertion. Remove a marker when its fix lands.
Guards pin what is right now. Invented fixtures only: no job was run and no job data was read."""
from types import SimpleNamespace


from estimator.reading.inventory import build_inventory
from estimator.writing.dossier import build_dossier
from test_dossier_plan_areas import DWG, OTHER, _catalogue, _doc, _line, _page, _reading, _schedule, _sheet

BOXES = [f"VAV-{n}" for n in range(1, 6)]


def _lines(*tags):
    return "\n".join(tags)


def _typicals(reading, *pairs):
    reading.typicals = tuple(SimpleNamespace(sheet=sheet, floors=tuple(floors)) for sheet, floors in pairs)
    return reading


def _notes(line: str) -> str:
    return line.split("Reading notes:", 1)[1] if "Reading notes:" in line else ""


# ---- F1 HIGH: a unit's tag on two typical sheets of separate floors keeps only the larger sheet's floors ----------

def test_a_unit_tag_on_two_typical_sheets_of_separate_floors_counts_every_floor(tmp_path):
    """A low-rise typical plan stands for floors 2 to 5 and a high-rise typical plan for floors 6 to 10; each shows
    VAV-1 to 5. The typical multiplier already says each floor has its own VAV-1, and the two floor lists share no
    floor, so there are 5 x 9 = 45 boxes (a3e1b1f gave 45). e91dc46 keeps only the larger sheet's 5 floors: 25."""
    reading = _typicals(_reading(), ("M-102", range(2, 6)), ("M-106", range(6, 11)))
    pages = [_page(DWG, 1, _lines(*BOXES)), _page(DWG, 2, _lines(*BOXES))]
    sheets = [_sheet(1, "M-102", "TYPICAL LOW-RISE FLOOR PLAN"), _sheet(2, "M-106", "TYPICAL HIGH-RISE FLOOR PLAN")]
    d = build_dossier(_catalogue(pages, sheets, BOXES), reading, tmp_path)
    assert d.counts["VAV"]["plan_placements"] == 45


def test_a_first_floor_plan_beside_a_typical_plan_of_other_floors_adds_its_floor(tmp_path):
    """FIRST FLOOR PLAN (M-101) and a typical plan standing for floors 2 to 4 (M-102) each show VAV-1 to 5. Floor 1
    is not one of the typical floors, so its boxes are 5 more: 20 (a3e1b1f gave 20). e91dc46 gives 15."""
    reading = _typicals(_reading(), ("M-102", (2, 3, 4)))
    pages = [_page(DWG, 1, _lines(*BOXES)), _page(DWG, 2, _lines(*BOXES))]
    sheets = [_sheet(1, "M-101", "FIRST FLOOR PLAN"), _sheet(2, "M-102", "TYPICAL FLOOR PLAN (FLOORS 2-4)")]
    d = build_dossier(_catalogue(pages, sheets, BOXES), reading, tmp_path)
    assert d.counts["VAV"]["plan_placements"] == 20


def test_guard_a_typical_floor_drawn_twice_for_the_same_floors_is_not_doubled(tmp_path):
    """The other side of F1: a ductwork and a piping plan of the SAME typical floors (2 to 5) are one set of floors,
    so 5 x 4 = 20, never 40. A fix for F1 must keep this."""
    reading = _typicals(_reading(), ("M-102", range(2, 6)), ("M-202", range(2, 6)))
    pages = [_page(DWG, 1, _lines(*BOXES)), _page(DWG, 2, _lines(*BOXES))]
    sheets = [_sheet(1, "M-102", "TYPICAL FLOOR DUCTWORK PLAN"), _sheet(2, "M-202", "TYPICAL FLOOR PIPING PLAN")]
    d = build_dossier(_catalogue(pages, sheets, BOXES), reading, tmp_path)
    assert d.counts["VAV"]["plan_placements"] == 20


# ---- F2 HIGH: two buildings the titles name apart, reusing one unit numbering --------------------------------------

def test_unit_tags_reused_by_two_buildings_the_titles_name_apart_count_in_each(tmp_path):
    """Two identical buildings, one document each: "BUILDING A FIRST FLOOR PLAN" and "BUILDING B FIRST FLOOR PLAN",
    each with AHU-1 to 3. The titles name two parts apart (`_named_apart` reads them so), so these are 6 units
    (a3e1b1f gave 6). e91dc46 gives 3, and its only note backs the low count ("each unit's tag is counted once")."""
    ahus = ["AHU-1", "AHU-2", "AHU-3"]
    pages = [_page(DWG, 1, _lines(*ahus)), _page(OTHER, 1, _lines(*ahus))]
    sheets = [_sheet(1, "A-M101", "BUILDING A FIRST FLOOR PLAN"),
              _sheet(1, "B-M101", "BUILDING B FIRST FLOOR PLAN", OTHER)]
    d = build_dossier(_catalogue(pages, sheets, ahus, [_doc(DWG, 1), _doc(OTHER, 1)]), _reading(), tmp_path)
    assert d.counts["AHU"]["plan_placements"] == 6


def test_guard_type_tags_of_two_buildings_on_their_own_sheet_numbers_add_up(tmp_path):
    text = _lines(*(["EBB-A"] * 4 + ["EBB-B"] * 2 + ["EBB-C"]))
    pages = [_page(DWG, 1, text), _page(OTHER, 1, text)]
    sheets = [_sheet(1, "A-M101", "BUILDING A FIRST FLOOR PLAN"),
              _sheet(1, "B-M101", "BUILDING B FIRST FLOOR PLAN", OTHER)]
    d = build_dossier(_catalogue(pages, sheets, ["EBB-A", "EBB-B", "EBB-C"], [_doc(DWG, 1), _doc(OTHER, 1)]),
                      _reading(), tmp_path)
    assert d.counts["EBB"]["plan_placements"] == 14


# ---- F3 HIGH (disclosed, needs a ruling): a numbered type below the threshold drops to one, and nothing says so ----

def test_a_numbered_tag_once_on_each_of_ten_floor_plans_is_named_as_maybe_a_type(tmp_path):
    """EBB-1 once on each of LEVEL 1 to LEVEL 10's plans, no schedule: it counts 1 (a3e1b1f gave 10). Whatever the
    lead rules on the count, the reading notes must name EBB-1 and the ten plans, so the estimator can see it may be
    a type placed on every floor; e91dc46 only says the labels add up to 10 and that each unit's tag counts once."""
    pages = [_page(DWG, n, "EBB-1") for n in range(1, 11)]
    sheets = [_sheet(n, f"M-1{n:02d}", f"HVAC LEVEL {n} PLAN") for n in range(1, 11)]
    d = build_dossier(_catalogue(pages, sheets, ["EBB-1"]), _reading(), tmp_path)
    notes = _notes(_line("EBB", d))
    assert "EBB-1" in notes and "type" in notes


def test_a_numbered_tag_three_times_on_one_sheet_keeps_the_typical_caveat(tmp_path):
    """FCU-1 at three places on one plan (one short of the type rule) counts 1. a3e1b1f counted 3 and said "likely
    one unit labelled more than once ..., unless it is a typical unit placed at each of those places". The count is
    the lead's ruling; the caveat naming FCU-1 is the estimator's only pointer to the possible undercount."""
    pages = [_page(DWG, 1, _lines("FCU-1", "FCU-1", "FCU-1", "FCU-2"))]
    sheets = [_sheet(1, "M-101", "HVAC LEVEL 1 PLAN")]
    d = build_dossier(_catalogue(pages, sheets, ["FCU-1", "FCU-2"]), _reading(), tmp_path)
    notes = _notes(_line("FCU", d))
    assert "FCU-1" in notes and "typical" in notes


def test_guard_a_numbered_tag_four_times_on_one_sheet_counts_every_place(tmp_path):
    pages = [_page(DWG, 1, _lines("FCU-1", "FCU-1", "FCU-1", "FCU-1", "FCU-2"))]
    sheets = [_sheet(1, "M-101", "HVAC LEVEL 1 PLAN")]
    d = build_dossier(_catalogue(pages, sheets, ["FCU-1", "FCU-2"]), _reading(), tmp_path)
    assert d.counts["FCU"]["plan_placements"] == 5


# ---- F4 MEDIUM: the inventory and the dossier count one tag differently -------------------------------------------

def _scheduled_job(plan_texts, titles, tags, typicals=()):
    pages = [_page(DWG, n, text) for n, text in enumerate(plan_texts, 1)]
    page = len(pages) + 1
    pages.append(_page(DWG, page, "SCHEDULE\n" + _lines(*tags)))
    sheets = [_sheet(n, number, title) for n, (number, title) in enumerate(titles, 1)]
    sheets.append(_sheet(page, "M-601", "SCHEDULES", types=("Schedules",)))
    schedules = [_schedule("UNIT SCHEDULE", tags, page)]
    reading = _typicals(_reading(schedules), *typicals)
    catalogue = _catalogue(pages, sheets, tags)
    items, _totals, _flags = build_inventory(catalogue, schedules, reading.typicals)
    return {i.tag: i for i in items}, catalogue, reading


def test_the_inventory_and_the_dossier_agree_on_a_tag_on_a_typical_sheet(tmp_path):
    """FCU-1 (scheduled, no QUANTITY column) drawn three times on a typical plan standing for 10 floors. The
    inventory (the Evidence Package) says "A type, not one unit", 30; the dossier (the ledger, the proposal) counts
    one unit per floor, 10. The two counts of one tag must agree."""
    items, catalogue, reading = _scheduled_job([_lines("FCU-1", "FCU-1", "FCU-1")],
                                               [("M-102", "TYPICAL FLOOR PLAN")], ["FCU-1"],
                                               [("M-102", range(2, 12))])
    d = build_dossier(catalogue, reading, tmp_path)
    assert items["FCU-1"].quantity == d.counts["FCU"]["plan_placements"]


def test_the_inventory_counts_a_scheduled_type_tag_at_every_place():
    """EBB-A on the schedule (no QUANTITY column), drawn once on LEVEL 1 and once on LEVEL 2: a type's tag, which
    the dossier sums (2). The inventory calls it one unit, CONFIRMED 1."""
    items, _catalogue_, _reading_ = _scheduled_job(["EBB-A", "EBB-A"],
                                                   [("M-101", "LEVEL 1 PLAN"), ("M-102", "LEVEL 2 PLAN")], ["EBB-A"])
    assert items["EBB-A"].quantity == 2


# ---- guards: the doubling stays fixed, and a job without repeated tags gets no new notes ---------------------------

def test_guard_a_58_box_job_drawn_on_ductwork_and_piping_plans_counts_each_box_once(tmp_path):
    """Two floors, each drawn on a ductwork plan and on a piping plan, 29 distinct boxes a floor: 58, never 116."""
    first = [f"VAV-1{n:02d}" for n in range(1, 30)]
    second = [f"VAV-2{n:02d}" for n in range(1, 30)]
    pages = [_page(DWG, 1, _lines(*first)), _page(DWG, 2, _lines(*second)), _page(DWG, 3, _lines(*first)),
             _page(DWG, 4, _lines(*second))]
    sheets = [_sheet(1, "M-101", "HVAC DUCTWORK FIRST FLOOR PLAN"),
              _sheet(2, "M-102", "HVAC DUCTWORK SECOND FLOOR PLAN"),
              _sheet(3, "M-201", "HVAC PIPING FIRST FLOOR PLAN"), _sheet(4, "M-202", "HVAC PIPING SECOND FLOOR PLAN")]
    d = build_dossier(_catalogue(pages, sheets, first + second), _reading(), tmp_path)
    assert d.counts["VAV"]["plan_placements"] == 58
    line = _line("VAV", d)
    assert "same plan as" not in line and "may show one plan" not in line


def test_guard_a_job_with_no_repeated_tags_gets_neither_new_note(tmp_path):
    boxes = ["VAV-1", "VAV-2", "VAV-3", "VAV-4"]
    pages = [_page(DWG, 1, _lines("VAV-1", "VAV-2", "EBB-A")), _page(DWG, 2, _lines("VAV-3", "VAV-4")),
             _page(DWG, 3, "VAV SCHEDULE\n" + _lines(*boxes))]
    sheets = [_sheet(1, "M-101", "HVAC FIRST FLOOR PLAN"), _sheet(2, "M-102", "HVAC SECOND FLOOR PLAN"),
              _sheet(3, "M-601", "SCHEDULES", types=("Schedules",))]
    d = build_dossier(_catalogue(pages, sheets, boxes + ["EBB-A"]),
                      _reading([_schedule("VAV SCHEDULE", boxes, 3)]), tmp_path)
    assert d.counts["VAV"]["plan_placements"] == 4
    for prefix in ("VAV", "EBB"):
        line = _line(prefix, d)
        assert "the labels on the plan sheets add up to" not in line and "may show one plan" not in line
