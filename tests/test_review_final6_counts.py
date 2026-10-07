"""REVIEW-FINAL6 (reviewer of record for lead/final-i at rebuild f5394a9): the final counting rule, attacked for any
input where the plans' count falls below the true number of physical units. An undercount is the worst failure.

Each strict xfail asserts the right behaviour and fails by assertion on f5394a9; remove its marker when its fix
lands. The guards pass on f5394a9. Invented fixtures only (job 26-9999, invented sheets and tags)."""
from types import SimpleNamespace

import pytest

from estimator.reading.inventory import build_inventory, counting_pages
from estimator.reading.revisions import governing_pages
from estimator.reading.schedules import Schedule, ScheduleRow
from estimator.writing.dossier import build_dossier
from test_dossier_plan_areas import DWG, OTHER, _catalogue, _doc, _line, _page, _reading, _schedule, _sheet

UNITS = ["VAV-1", "VAV-2", "VAV-3"]


def _lines(*tags):
    return "\n".join(tags)


def _notes(line: str) -> str:
    return line.split("Reading notes:", 1)[1] if "Reading notes:" in line else ""


def _schedules_sheet(document=DWG, page=9):
    return _sheet(page, "M-601", "SCHEDULES", document, types=("Schedules",))


def _two_sheets(first: str, second: str, numbers=("M-101", "M-102")):
    """One document, the same three boxes on two plan sheets with these titles."""
    pages = [_page(DWG, 1, _lines(*UNITS)), _page(DWG, 2, _lines(*UNITS))]
    sheets = [_sheet(1, numbers[0], first), _sheet(2, numbers[1], second)]
    return _catalogue(pages, sheets, UNITS)


# ---- F1 HIGH (regression): a QUANTITY schedule's row with an empty cell is a type, yet counted once ----------------

def test_a_type_by_its_quantity_column_with_an_empty_cell_counts_every_place_on_the_plans(tmp_path):
    """The EXHAUST FAN SCHEDULE has a QUANTITY column; EF-1's cell is empty and EF-1 is drawn 3 times on M-101. The
    inventory says "A type, not one unit (the schedule has a QUANTITY column)", so it counts at every place: 3, as
    rebuild 36b6d5c counted. f5394a9 counts 1 ("1 counted on the plans (M-101 3)")."""
    schedule = Schedule(DWG, 9, "M-601", "EXHAUST FAN SCHEDULE", ("TAG", "QUANTITY"),
                        (ScheduleRow("EF-1", {"TAG": "EF-1", "QUANTITY": ""}, None, None, False),), False, (), (),
                        False)
    pages = [_page(DWG, 1, _lines("EF-1", "EF-1", "EF-1")), _page(DWG, 9, "SCHEDULE\nEF-1")]
    sheets = [_sheet(1, "M-101", "LEVEL 1 PLAN"), _schedules_sheet()]
    items, _totals, _flags = build_inventory(_catalogue(pages, sheets, ["EF-1"]), [schedule], ())
    item = next(i for i in items if i.tag == "EF-1")
    assert item.reason.startswith("A type, not one unit")
    assert item.quantity == 3


# ---- F2 HIGH: the title test sorts the words, so two places with the same words in another order group ------------

@pytest.mark.parametrize("first, second", [
    ("BUILDING 1 LEVEL 2 PLAN", "BUILDING 2 LEVEL 1 PLAN"),
    ("LEVEL 1 AREA 2 PLAN", "LEVEL 2 AREA 1 PLAN"),
    ("WING 3 FLOOR 4 PLAN", "WING 4 FLOOR 3 PLAN"),
])
def test_titles_with_the_same_words_in_another_order_are_two_places_and_add_up(tmp_path, first, second):
    """Building 1's level 2 and building 2's level 1 are two places, each with VAV-1 to 3: 6. f5394a9 groups them
    (the sorted words are equal and a floor word is among them) and counts 3."""
    d = build_dossier(_two_sheets(first, second), _reading(), tmp_path)
    assert d.counts["VAV"]["plan_placements"] == 6
    assert "counted as one plan" not in _line("VAV", d)


# ---- F3 HIGH: a second building issued as its own document with the same sheet numbers is dropped ----------------

def _two_buildings(same_tags: bool):
    """Two documents, each LEVEL 1 to 3 plans M-101 to M-103 and its own schedule M-601. Building A has VAV-n1 to
    n3 on level n; building B the same tags (same_tags) or VAV-n4 to n6."""
    a = [[f"VAV-{n}{k}" for k in (1, 2, 3)] for n in (1, 2, 3)]
    b = a if same_tags else [[f"VAV-{n}{k}" for k in (4, 5, 6)] for n in (1, 2, 3)]
    pages, sheets = [], []
    for document, floors in ((DWG, a), (OTHER, b)):
        for n, tags in enumerate(floors, start=1):
            pages.append(_page(document, n, _lines(*tags)))
            sheets.append(_sheet(n, f"M-10{n}", f"HVAC LEVEL {n} PLAN", document))
        pages.append(_page(document, 4, "SCHEDULE\n" + _lines(*(t for f in floors for t in f))))
        sheets.append(_schedules_sheet(document, 4))
    tags = sorted({t for f in a + b for t in f})
    return _catalogue(pages, sheets, tags, [_doc(DWG, 4), _doc(OTHER, 4)]), a, b


def test_a_second_building_with_the_same_sheet_numbers_and_other_tags_is_counted(tmp_path):
    """Building B repeats A's sheet numbers but shows VAV-14 to 36, none of A's tags: it is no marked-up copy.
    Its plans and its schedule must be read: 18 boxes. f5394a9 reads building A only (plan placements 9, and B's
    schedule page is not a governing page either), and only the two 'probably a marked-up copy' flags speak."""
    catalogue, a, b = _two_buildings(same_tags=False)
    pages = counting_pages(catalogue, governing_pages(catalogue))
    assert (OTHER, 1) in pages and (OTHER, 4) in governing_pages(catalogue)
    schedules = [_schedule("VAV SCHEDULE", [t for f in a for t in f], 4),
                 _schedule("VAV SCHEDULE", [t for f in b for t in f], 4, document=OTHER)]
    d = build_dossier(catalogue, _reading(schedules), tmp_path)
    assert d.counts["VAV"]["plan_placements"] == 18


def test_two_identical_buildings_read_as_a_marked_up_copy_are_named_on_the_counts_line(tmp_path):
    """The same two documents with the same tags and text: if this is kept as one marked-up copy, the counts line
    must still name the other document and the summed count, so the estimator can see the possible undercount (9,
    or 18 if Second Building.pdf is a second building). f5394a9 prints 9 and says nothing."""
    catalogue, a, _b = _two_buildings(same_tags=True)
    d = build_dossier(catalogue, _reading([_schedule("VAV SCHEDULE", [t for f in a for t in f], 4)]), tmp_path)
    line = _line("VAV", d)
    notes = _notes(line)
    assert d.counts["VAV"]["plan_placements"] == 18 or ("Second Building.pdf" in notes and "18" in notes)


# ---- F4 MEDIUM: a plan group made by stripping the sheet number out of the middle of a title -----------------------

def test_a_title_that_names_its_part_by_the_sheet_number_is_not_one_plan_with_another_part(tmp_path):
    """"WING MA1 FIRST FLOOR PLAN" (MA1) and "WING MB1 FIRST FLOOR PLAN" (MB1): the wing names differ, so 6.
    f5394a9 takes each sheet's own number out of its title, leaving "WING FIRST FLOOR" twice, and counts 3."""
    d = build_dossier(_two_sheets("WING MA1 FIRST FLOOR PLAN", "WING MB1 FIRST FLOOR PLAN", ("MA1", "MB1")),
                      _reading(), tmp_path)
    assert d.counts["VAV"]["plan_placements"] == 6


# ---- F5 MEDIUM: the group note gives only the low count ------------------------------------------------------------

def test_a_plan_group_note_gives_the_count_if_the_sheets_are_two_places(tmp_path):
    """Two sheets of one document both titled FIRST FLOOR PLAN with VAV-1 to 3 group by the ruling (3). They may be
    two identical buildings whose title block names the building elsewhere: the note must give the summed count, 6,
    beside the low one, as the may-show-one-plan and summed notes do for the other direction."""
    d = build_dossier(_two_sheets("FIRST FLOOR PLAN", "FIRST FLOOR PLAN", ("M-101", "M-201")), _reading(), tmp_path)
    assert d.counts["VAV"]["plan_placements"] == 3
    notes = _notes(_line("VAV", d))
    assert "M-101 and M-201 counted as one plan" in notes
    assert "6" in notes.split("M-101 and M-201 counted as one plan", 1)[1].split(";", 1)[0]


# ---- F6 MEDIUM: one sheet number on two pages of one document with other text --------------------------------------

def test_one_sheet_number_on_two_pages_with_other_text_counts_both_pages(tmp_path):
    """M-101 on page 1 (VAV-1 to 3) and on page 2 (VAV-4 to 7) of one document, with other text (repeated_plans
    would not call it one plan). Both pages are read: 7 boxes. f5394a9 reads page 1 only, times 2 pages: 6, and
    VAV-4 to 7 are on no counts line."""
    tags = [f"VAV-{n}" for n in range(1, 8)]
    pages = [_page(DWG, 1, _lines(*UNITS)), _page(DWG, 2, _lines(*tags[3:]))]
    sheets = [_sheet(1, "M-101", "FIRST FLOOR PLAN"), _sheet(2, "M-101", "SECOND FLOOR PLAN")]
    d = build_dossier(_catalogue(pages, sheets, tags), _reading(), tmp_path)
    assert d.counts["VAV"]["distinct_tags"] == 7
    assert d.counts["VAV"]["plan_placements"] >= 7


# ---- F7 MEDIUM (disclosed): tags in notes make the dossier group what the inventory sums ---------------------------

def test_the_inventory_and_the_dossier_agree_when_a_sheet_names_units_in_notes(tmp_path):
    """M-101 (ductwork) labels VAV-1 to 3; M-201 (piping, same floor title) labels VAV-1 and names VAV-2 and 3 only
    in notes ("TO VAV-2"). The dossier sees 3 shared tags and groups (3); the inventory sees 1 and sums (VAV-1 is 2,
    so 4). The proposal takes the lower number."""
    pages = [_page(DWG, 1, _lines(*UNITS)), _page(DWG, 2, _lines("VAV-1", "TO VAV-2", "TO VAV-3")),
             _page(DWG, 9, "SCHEDULE\n" + _lines(*UNITS))]
    sheets = [_sheet(1, "M-101", "HVAC DUCTWORK FIRST FLOOR PLAN"),
              _sheet(2, "M-201", "HVAC PIPING FIRST FLOOR PLAN"),
              _schedules_sheet()]
    catalogue, schedules = _catalogue(pages, sheets, UNITS), [_schedule("VAV SCHEDULE", UNITS, 9)]
    items, _totals, _flags = build_inventory(catalogue, schedules, ())
    d = build_dossier(catalogue, _reading(schedules), tmp_path)
    assert sum(i.quantity for i in items if i.tag in UNITS) == d.counts["VAV"]["plan_placements"]


# ---- F8 LOW (disclosed): a tag listed twice on the schedules loses its listed-twice reason -------------------------

def test_a_tag_listed_twice_on_the_schedules_keeps_saying_so_when_the_plans_count_it_twice(tmp_path):
    pages = [_page(DWG, 1, "EF-1"), _page(DWG, 2, "EF-1"), _page(DWG, 9, "SCHEDULE\nEF-1"),
             _page(DWG, 10, "SCHEDULE\nEF-1")]
    sheets = [_sheet(1, "M-101", "LEVEL 1 PLAN"), _sheet(2, "M-102", "LEVEL 2 PLAN"), _schedules_sheet(),
              _sheet(10, "M-602", "SCHEDULES", types=("Schedules",))]
    schedules = [_schedule("FAN SCHEDULE", ["EF-1"], 9), _schedule("FAN SCHEDULE 2", ["EF-1"], 10, sheet="M-602")]
    items, _totals, _flags = build_inventory(_catalogue(pages, sheets, ["EF-1"]), schedules, ())
    item = next(i for i in items if i.tag == "EF-1")
    assert item.quantity == 2
    assert "listed 2 times on the schedules" in item.reason


# ---- guards: what holds on f5394a9 ---------------------------------------------------------------------------------

@pytest.mark.parametrize("first, second", [
    ("BUILDING A FIRST FLOOR PLAN", "BUILDING B FIRST FLOOR PLAN"),
    ("FIRST FLOOR PLAN - EAST", "FIRST FLOOR PLAN - WEST"),
    ("LEVEL 1 PLAN", "LEVEL 2 PLAN"),
    ("FIRST FLOOR PLAN", "1ST FLOOR PLAN"),
])
def test_guard_two_places_one_document_whose_titles_differ_add_up(tmp_path, first, second):
    d = build_dossier(_two_sheets(first, second), _reading(), tmp_path)
    assert d.counts["VAV"]["plan_placements"] == 6
    assert "counted on each" in _notes(_line("VAV", d)) or "may show one plan" in _line("VAV", d)


def test_guard_one_title_on_two_typical_sheets_of_other_floors_counts_every_floor(tmp_path):
    """Both TYPICAL FLOOR PLAN, floors 2 to 5 and 6 to 9, the same boxes: one group of 8 floors, 24."""
    reading = _reading()
    reading.typicals = (SimpleNamespace(sheet="M-102", floors=("2", "3", "4", "5")),
                        SimpleNamespace(sheet="M-106", floors=("6", "7", "8", "9")))
    d = build_dossier(_two_sheets("TYPICAL FLOOR PLAN", "TYPICAL FLOOR PLAN", ("M-102", "M-106")), reading,
                      tmp_path)
    assert d.counts["VAV"]["plan_placements"] == 24


@pytest.mark.parametrize("tags", [["VAV-1A", "VAV-1B", "VAV-1C"], ["FCU-A", "FCU-B", "FCU-C"]])
def test_guard_letter_suffixed_tags_on_two_floors_add_up(tmp_path, tags):
    pages = [_page(DWG, 1, _lines(*tags)), _page(DWG, 2, _lines(*tags))]
    sheets = [_sheet(1, "M-101", "LEVEL 1 PLAN"), _sheet(2, "M-102", "LEVEL 2 PLAN")]
    d = build_dossier(_catalogue(pages, sheets, tags), _reading(), tmp_path)
    assert d.counts[tags[0].split("-")[0]]["plan_placements"] == 6


@pytest.mark.parametrize("titles", [
    ("FIRST FLOOR PLAN", "FIRST FLOOR PLAN"),
    ("HVAC DUCTWORK FIRST FLOOR PLAN", "HVAC PIPING FIRST FLOOR PLAN"),
    ("LEVEL 1 PLAN", "LEVEL 2 PLAN"),
    ("MECHANICAL PLAN", "MECHANICAL PLAN"),
])
def test_guard_the_plans_count_is_never_below_the_tags_they_show_nor_the_schedule_rows(tmp_path, titles):
    """Whatever the grouping, every unit's tag on the plans counts at least once, so the plans' count is never below
    the distinct tags they show, and with a schedule of those tags the schedule rows stand beside it."""
    tags = [f"VAV-{n}" for n in range(1, 6)]
    pages = [_page(DWG, 1, _lines(*tags[:4])), _page(DWG, 2, _lines(*tags[1:])),
             _page(DWG, 9, "SCHEDULE\n" + _lines(*tags))]
    sheets = [_sheet(1, "M-101", titles[0]), _sheet(2, "M-201", titles[1]), _schedules_sheet()]
    d = build_dossier(_catalogue(pages, sheets, tags), _reading([_schedule("VAV SCHEDULE", tags, 9)]), tmp_path)
    assert d.counts["VAV"]["plan_placements"] >= len(tags)
    assert d.counts["VAV"]["schedule_rows"] == len(tags)
