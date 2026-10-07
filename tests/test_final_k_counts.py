"""FINAL-K: REVIEW-FINAL6 part A, the counting rule made safe wherever it reduces a count (lead ruling: an undercount
is the worst failure; a reduction must be provably safe, otherwise sum). These tests add to the reviewer's own
(tests/test_review_final6_counts.py) and each fails on rebuild f5394a9 by assertion. Invented fixtures only (job
26-9999, invented sheets and tags)."""
from pathlib import Path
from types import SimpleNamespace

from estimator.catalogue.documents import Document
from estimator.catalogue.job import repeats
from estimator.reading.devices import DeviceCount
from estimator.reading.inventory import build_inventory, counting_pages, placements, plan_floors
from estimator.reading.revisions import governing_pages, sheet_versions, supersede
from estimator.reading.schedules import Schedule, ScheduleRow
from estimator.writing.dossier import build_dossier
from test_dossier_plan_areas import DWG, OTHER, _catalogue, _doc, _line, _page, _reading, _schedule, _sheet

UNITS = ["VAV-1", "VAV-2", "VAV-3"]


def _lines(*tags):
    return "\n".join(tags)


def _notes(line: str) -> str:
    return line.split("Reading notes:", 1)[1] if "Reading notes:" in line else ""


def _head(line: str) -> str:
    return line.split("Reading notes:", 1)[0]


def _schedules_sheet(document=DWG, page=9, number="M-601"):
    return _sheet(page, number, "SCHEDULES", document, types=("Schedules",))


# ---- F1: a type by its QUANTITY column, the dossier's side ---------------------------------------------------------

def _quantity_schedule():
    return Schedule(DWG, 9, "M-601", "EXHAUST FAN SCHEDULE", ("TAG", "QUANTITY"),
                    (ScheduleRow("EF-1", {"TAG": "EF-1", "QUANTITY": ""}, None, None, False),), False, (), (), False)


def test_a_type_by_its_quantity_column_counts_every_place_in_the_dossier_too_with_the_typical_cause(tmp_path):
    """The dossier gives what the inventory gives (3, not 1), and its head names the typical cause, never "one
    unit labelled more than once" beside a count of 3."""
    pages = [_page(DWG, 1, _lines("EF-1", "EF-1", "EF-1")), _page(DWG, 9, "SCHEDULE\nEF-1")]
    sheets = [_sheet(1, "M-101", "LEVEL 1 PLAN"), _schedules_sheet()]
    d = build_dossier(_catalogue(pages, sheets, ["EF-1"]), _reading([_quantity_schedule()]), tmp_path)
    assert d.counts["EF"]["plan_placements"] == 3
    head = _head(_line("EF", d))
    assert "a typical unit at each place" in head
    assert "one unit labelled more than once" not in head


def test_a_type_by_its_quantity_column_on_a_plan_drawn_twice_counts_one_plans_places(tmp_path):
    """Drawn 3 times on M-101 and 3 times on its piping plan of the same floor (one plan group): 3, not 6, not 1."""
    text = _lines("EF-1", "EF-1", "EF-1", *UNITS)
    pages = [_page(DWG, 1, text), _page(DWG, 2, text), _page(DWG, 9, "SCHEDULE\nEF-1")]
    sheets = [_sheet(1, "M-101", "HVAC DUCTWORK FIRST FLOOR PLAN"),
              _sheet(2, "M-201", "HVAC PIPING FIRST FLOOR PLAN"), _schedules_sheet()]
    catalogue = _catalogue(pages, sheets, ["EF-1", *UNITS])
    items, _totals, _flags = build_inventory(catalogue, [_quantity_schedule()], ())
    assert next(i for i in items if i.tag == "EF-1").quantity == 3
    d = build_dossier(catalogue, _reading([_quantity_schedule()]), tmp_path)
    assert d.counts["EF"]["plan_placements"] == 3


# ---- F5: a type's note never contradicts its count -----------------------------------------------------------------

def test_a_type_tags_note_gives_its_count_not_every_label_summed(tmp_path):
    """EBB-A drawn 4 times on each of two same-titled sheets that repeat 4 of 5 boxes: one plan group, 4. The note
    must not say "EBB-A 8 places" beside 4, nor say of a type that "a unit's tag is counted once"."""
    first = _lines("EBB-A", "EBB-A", "EBB-A", "EBB-A", "VAV-1", "VAV-2", "VAV-3", "VAV-4", "VAV-5")
    second = _lines("EBB-A", "EBB-A", "EBB-A", "EBB-A", "VAV-1", "VAV-2", "VAV-3", "VAV-4")
    pages = [_page(DWG, 1, first), _page(DWG, 2, second)]
    sheets = [_sheet(1, "M-101", "FIRST FLOOR PLAN"), _sheet(2, "M-201", "FIRST FLOOR PLAN")]
    tags = ["EBB-A"] + [f"VAV-{n}" for n in range(1, 6)]
    d = build_dossier(_catalogue(pages, sheets, tags), _reading(), tmp_path)
    assert d.counts["EBB"]["plan_placements"] == 4
    notes = _notes(_line("EBB", d))
    assert "8 places" not in notes
    assert "a unit's tag is counted once" not in notes
    assert "counted as one plan, 4 (8 if they are two places)" in notes


# ---- F6: one sheet number on two pages with other text, everywhere it is read --------------------------------------

def _two_pages_one_number():
    tags = [f"VAV-{n}" for n in range(1, 8)]
    pages = [_page(DWG, 1, _lines(*UNITS)), _page(DWG, 2, _lines(*tags[3:])),
             _page(DWG, 9, "SCHEDULE\n" + _lines(*tags))]
    sheets = [_sheet(1, "M-101", "FIRST FLOOR PLAN"), _sheet(2, "M-101", "SECOND FLOOR PLAN"), _schedules_sheet()]
    return _catalogue(pages, sheets, tags), tags


def test_one_sheet_number_on_two_pages_with_other_text_is_two_sheets_of_one_floor_each(tmp_path):
    """No "x 2 floors" for pages that are not one plan: the inventory counts VAV-1 once (not 2), and both pages are
    counting pages; the same number with the same text on two pages still stands for two floors."""
    catalogue, tags = _two_pages_one_number()
    assert plan_floors(catalogue) == {}
    assert {(DWG, 1), (DWG, 2)} <= counting_pages(catalogue, governing_pages(catalogue))
    items, _totals, _flags = build_inventory(catalogue, [_schedule("VAV SCHEDULE", tags, 9)], ())
    assert {i.tag: i.quantity for i in items if i.tag in tags} == dict.fromkeys(tags, 1)
    same = _catalogue([_page(DWG, 1, _lines(*UNITS)), _page(DWG, 2, _lines(*UNITS))],
                      [_sheet(1, "M-113", "TYPICAL PLAN"), _sheet(2, "M-113", "TYPICAL PLAN")], UNITS)
    assert plan_floors(same) == {(DWG, "M-113"): frozenset({"p.1", "p.2"})}


def test_devices_on_the_second_page_of_a_sheet_number_with_other_text_are_counted(tmp_path):
    catalogue, tags = _two_pages_one_number()
    reading = _reading([_schedule("VAV SCHEDULE", tags, 9)])
    reading.devices = (DeviceCount("M-101", DWG, 1, "Thermostat", "T", 1, 1, 1, True),
                       DeviceCount("M-101", DWG, 2, "Thermostat", "T", 2, 1, 2, True))
    d = build_dossier(catalogue, reading, tmp_path)
    assert d.device_totals["T"] == 3


# ---- F7: tags named only in notes are no placements, on either side ------------------------------------------------

def test_a_tag_labelled_once_and_named_in_three_notes_is_one_placement_with_no_cause(tmp_path):
    pages = [_page(DWG, 1, _lines("EF-1", "TO EF-1", "TO EF-1", "TO EF-1")), _page(DWG, 9, "SCHEDULE\nEF-1")]
    sheets = [_sheet(1, "M-101", "LEVEL 1 PLAN"), _schedules_sheet()]
    catalogue, schedules = _catalogue(pages, sheets, ["EF-1"]), [_schedule("FAN SCHEDULE", ["EF-1"], 9)]
    items, _totals, _flags = build_inventory(catalogue, schedules, ())
    assert next(i for i in items if i.tag == "EF-1").quantity == 1
    d = build_dossier(catalogue, _reading(schedules), tmp_path)
    assert d.counts["EF"]["plan_placements"] == 1
    head = _head(_line("EF", d))
    assert "a typical unit at each place" not in head and "placements above the other counts" not in head
    # and a schedule printed on a plan sheet, its row on one line ("VAV-1 500 CFM", no label), is not taken off
    # the labels: the unit still counts on that plan
    pages = [_page(DWG, 1, _lines("VAV-1", "VAV-1 500 CFM"))]
    sheets = [_sheet(1, "M-101", "LEVEL 1 PLAN")]
    rows = (ScheduleRow("VAV-1", {"TAG": "VAV-1"}, None, None, False),)
    on_plan = Schedule(DWG, 1, "M-101", "VAV SCHEDULE", ("TAG",), rows, False, (), (), False)
    d = build_dossier(_catalogue(pages, sheets, ["VAV-1"]), _reading([on_plan]), tmp_path)
    assert d.counts["VAV"]["plan_placements"] == 1


def test_a_line_of_tags_alone_is_each_tag_labelled_and_a_note_is_none():
    from estimator.catalogue.tags import label_keys, line_labels   # FINAL-K: the one label reader
    keys = label_keys(["VAV-1", "VAV-2", "EF-1"])
    assert line_labels("VAV-1  VAV-2\nTO EF-1\nEF-1 (TYP)\nVAV\n1", keys) == {"VAV-1": 2, "VAV-2": 1, "EF-1": 1}
    # symbols beside a tag on its line are no note; FINAL-N (REVIEW-FINAL7 F4, the lead's ruling): words after a tag
    # that starts its line are no note either ("VAV-2 ABOVE", "VAV-2 500 CFM" are labels; was no label)
    assert line_labels("VAV-1 VAV-1 T T\nEF-1 450\nVAV-2 ABOVE\nVAV-2 500 CFM", keys) == {"VAV-1": 2, "EF-1": 1,
                                                                                           "VAV-2": 2}


# ---- F8: listed twice on the schedules -----------------------------------------------------------------------------

def test_a_tag_listed_twice_and_counted_twice_on_the_plans_asks_to_confirm(tmp_path):
    pages = [_page(DWG, 1, "EF-1"), _page(DWG, 2, "EF-1"), _page(DWG, 9, "SCHEDULE\nEF-1"),
             _page(DWG, 10, "SCHEDULE\nEF-1")]
    sheets = [_sheet(1, "M-101", "LEVEL 1 PLAN"), _sheet(2, "M-102", "LEVEL 2 PLAN"), _schedules_sheet(),
              _sheet(10, "M-602", "SCHEDULES", types=("Schedules",))]
    schedules = [_schedule("FAN SCHEDULE", ["EF-1"], 9), _schedule("FAN SCHEDULE 2", ["EF-1"], 10, sheet="M-602")]
    items, _totals, _flags = build_inventory(_catalogue(pages, sheets, ["EF-1"]), schedules, ())
    item = next(i for i in items if i.tag == "EF-1")
    assert item.action == "confirm" and "confirm with the engineer" in item.reason


# ---- F9: one floor in two spellings --------------------------------------------------------------------------------

def test_floors_02_and_2_are_one_floor_in_a_plan_groups_union(tmp_path):
    pages = [_page(DWG, 1, _lines(*UNITS)), _page(DWG, 2, _lines(*UNITS))]
    sheets = [_sheet(1, "M-102", "TYPICAL FLOOR DUCTWORK PLAN"), _sheet(2, "M-202", "TYPICAL FLOOR PIPING PLAN")]
    reading = _reading()
    reading.typicals = (SimpleNamespace(sheet="M-102", floors=("2", "3")),
                        SimpleNamespace(sheet="M-202", floors=("02", "03")))
    d = build_dossier(_catalogue(pages, sheets, UNITS), reading, tmp_path)
    assert d.counts["VAV"]["plan_placements"] == 6


# ---- F2 / F4: the title test reads the words in order, the sheet number only at an edge ----------------------------

def test_guard_a_sheet_number_at_the_start_or_end_of_a_title_is_still_taken_out(tmp_path):
    """"M-101 HVAC DUCTWORK FIRST FLOOR PLAN" and "HVAC PIPING FIRST FLOOR PLAN M-201" are one plan group: 3."""
    pages = [_page(DWG, 1, _lines(*UNITS)), _page(DWG, 2, _lines(*UNITS))]
    sheets = [_sheet(1, "M-101", "M-101 HVAC DUCTWORK FIRST FLOOR PLAN"),
              _sheet(2, "M-201", "HVAC PIPING FIRST FLOOR PLAN M-201")]
    d = build_dossier(_catalogue(pages, sheets, UNITS), _reading(), tmp_path)
    assert d.counts["VAV"]["plan_placements"] == 3


# ---- F3: a second building issued as its own document --------------------------------------------------------------

def _two_sets(b_tags, b_kind="drawings", b_text=None):
    """Mech.pdf: M-101 to M-103 with VAV-n1 to n3 on level n. Second Building.pdf: the same numbers, with
    b_tags(n)."""
    pages, sheets, tags = [], [], set()
    for document, tags_of in ((DWG, lambda n: [f"VAV-{n}{k}" for k in (1, 2, 3)]), (OTHER, b_tags)):
        for n in (1, 2, 3):
            pages.append(_page(document, n, (b_text or _lines)(*tags_of(n)) if document == OTHER else
                               _lines(*tags_of(n))))
            sheets.append(_sheet(n, f"M-10{n}", f"HVAC LEVEL {n} PLAN", document))
            tags |= set(tags_of(n))
    documents = [_doc(DWG, 3), Document(Path(OTHER), OTHER, b_kind, "base", 3)]
    return _catalogue(pages, sheets, sorted(tags), documents)


def test_two_documents_of_the_same_size_never_each_claim_the_other():
    catalogue = _two_sets(lambda n: [f"VAV-{n}{k}" for k in (1, 2, 3)])
    lines, covered = repeats(catalogue)
    assert len(lines) == 1 and {document for _number, document in covered} == {OTHER}


def test_a_document_with_the_same_sheet_numbers_and_other_units_is_another_set_read_and_summed(tmp_path):
    catalogue = _two_sets(lambda n: [f"VAV-{n}{k}" for k in (4, 5, 6)])
    lines, covered = repeats(catalogue)
    assert not covered
    assert any("Second Building.pdf repeats 3 sheets of Mech.pdf" in line and "counted" in line for line in lines)
    assert supersede(catalogue, sheet_versions(catalogue)) == ([], [])
    assert {(OTHER, 1), (OTHER, 2), (OTHER, 3)} <= governing_pages(catalogue)
    assert placements(catalogue, ["VAV-14"])["VAV-14"].count == 1


def test_an_addendum_with_the_same_sheet_numbers_and_the_same_units_is_never_a_copy():
    """An addendum reissues the sheets: supersession decides which governs, the copy rule never sets it aside."""
    catalogue = _two_sets(lambda n: [f"VAV-{n}{k}" for k in (1, 2, 3)], b_kind="addendum")
    assert repeats(catalogue) == ([], set())
    # the same text at the same issue is one version: read once, from the base set (no supersession to decide)
    assert (DWG, 1) in governing_pages(catalogue) and (OTHER, 1) not in governing_pages(catalogue)


def test_another_sets_schedule_is_counted_by_the_inventory(tmp_path):
    """Each building's own schedule M-601: both are read, 6 rows, never "not counted, the same sheet was read"."""
    a, b = ["VAV-11", "VAV-12", "VAV-13"], ["VAV-14", "VAV-15", "VAV-16"]
    pages, sheets = [], []
    for document, tags in ((DWG, a), (OTHER, b)):
        for n in (1, 2, 3):
            pages.append(_page(document, n, _lines(*tags) if n == 1 else f"HVAC LEVEL {n}"))
            sheets.append(_sheet(n, f"M-10{n}", f"HVAC LEVEL {n} PLAN", document))
        pages.append(_page(document, 4, "SCHEDULE\n" + _lines(*tags)))
        sheets.append(_schedules_sheet(document, 4))
    catalogue = _catalogue(pages, sheets, a + b, [_doc(DWG, 4), _doc(OTHER, 4)])
    schedules = [_schedule("VAV SCHEDULE", a, 4), _schedule("VAV SCHEDULE", b, 4, document=OTHER)]
    items, totals, flags = build_inventory(catalogue, schedules, ())
    assert sum(i.quantity or 0 for i in items if i.tag.startswith("VAV")) == 6
    assert not any("not counted" in f for f in flags)
