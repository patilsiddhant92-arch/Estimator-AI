"""The devices marked on the plans, the job's legend, and typical floors (build step 4, Task 2)."""
from types import SimpleNamespace

import pymupdf
import pytest

from estimator.catalogue.register import PageRecord
from estimator.catalogue.sheet_types import Sheet
from estimator.reading.devices import (DeviceCount, LegendEntry, count_devices, read_legend, typical_sheets)
from pdfs import FILLER, Page, make_pdf

W, H = 3024, 2160
DOC = "Mech.pdf"


def _plan(*texts):
    return Page(width=W, height=H, texts=((200, 300, FILLER, 12), *texts))


PLAN = _plan((400, 500, "T", 12), (700, 500, "T", 12), (900, 800, "T", 12),
             (400, 900, "OCC", 12), (1200, 900, "OCC", 12),
             (1500, 1000, "TOTAL TSTAT TT", 12),          # not whole-word matches
             (2700, 1000, "T", 12),                       # in the title-block strip on the right
             (600, 2050, "T", 12))                        # in the strip along the bottom
LEGEND = _plan((200, 500, "T  THERMOSTAT OR TEMPERATURE SENSOR", 12),
               (1200, 500, "OCC", 12), (1300, 500, "OCCUPANCY SENSOR", 12),
               (200, 600, "ALL WORK SHALL BE COORDINATED WITH THE ARCHITECT", 12))
PLAN_WITH_TB = _plan((400, 500, "T", 12), (800, 500, "TB", 12), (900, 700, "TB", 12))
EMPTY_PLAN = _plan((400, 500, "ROOM 101", 12))
SCHEDULE = _plan((400, 500, "T", 12))


@pytest.fixture
def opener(tmp_path):
    """Build one synthetic PDF per test from the pages given; return the opener and a catalogue maker."""
    opened: dict[str, pymupdf.Document] = {}

    def build(sheets: list[tuple[Page, str | None, str | None, tuple[str, ...]]], texts: list[str] | None = None):
        path = make_pdf(tmp_path / DOC, *(page for page, *_ in sheets))
        opened[DOC] = pymupdf.open(str(path))
        sheet_rows = tuple(Sheet(DOC, i, number, title, "Mechanical", types)
                           for i, (_, number, title, types) in enumerate(sheets, start=1))
        texts = texts or [f"page {i}" for i in range(1, len(sheets) + 1)]
        pages = tuple(PageRecord(DOC, i, "text", texts[i - 1], 0, True) for i in range(1, len(sheets) + 1))
        return SimpleNamespace(pages=pages, sheets=sheet_rows)

    def open_page(document: str, page: int) -> pymupdf.Page:
        return opened[document][page - 1]

    yield build, open_page
    for doc in opened.values():
        doc.close()


def _by_label(counts):
    return {c.label: c for c in counts}


def test_labels_on_a_plan_are_counted_outside_the_title_block(opener):
    build, open_page = opener
    catalogue = build([(PLAN, "M-201", "MECHANICAL SECOND FLOOR PLAN", ("Plans",)),
                       (SCHEDULE, "M-601", "MECHANICAL SCHEDULES", ("Schedules",))])
    counts, flags = count_devices(catalogue, open_page, [], [])
    found = _by_label(counts)
    assert set(found) == {"T", "OCC"}
    assert found["T"] == DeviceCount("M-201", DOC, 1, "Thermostat / temperature sensor", "T", 3, 1, 3, False)
    assert (found["OCC"].device, found["OCC"].count, found["OCC"].total) == ("Occupancy sensor", 2, 2)
    assert flags == []


def test_the_legend_pairs_each_code_with_its_meaning(opener):
    build, open_page = opener
    catalogue = build([(LEGEND, "M-002", "MECHANICAL NOTES, SYMBOLS AND ABBREVIATIONS", ("Notes and legends",))])
    legend = read_legend(catalogue, open_page)
    assert LegendEntry("T", "THERMOSTAT OR TEMPERATURE SENSOR", "M-002") in legend
    assert LegendEntry("OCC", "OCCUPANCY SENSOR", "M-002") in legend
    assert not any(e.code == "ALL" for e in legend)


def test_a_legend_row_in_the_bottom_strip_is_still_read(opener):
    build, open_page = opener
    low = _plan((200, 1900, "CO2", 12), (300, 1900, "CARBON DIOXIDE SENSOR", 12))
    catalogue = build([(low, "M-002", "MECHANICAL LEGEND", ("Notes and legends",))])
    assert read_legend(catalogue, open_page) == [LegendEntry("CO2", "CARBON DIOXIDE SENSOR", "M-002")]


def test_a_notes_sheet_without_legend_in_its_title_is_not_a_legend(opener):
    build, open_page = opener
    catalogue = build([(LEGEND, "M-001", "MECHANICAL GENERAL NOTES", ("Notes and legends",))])
    assert read_legend(catalogue, open_page) == []


def test_a_label_missing_from_the_legend_is_flagged(opener):
    build, open_page = opener
    catalogue = build([(LEGEND, "M-002", "MECHANICAL LEGEND AND PLAN", ("Notes and legends", "Plans")),
                       (PLAN_WITH_TB, "M-201", "MECHANICAL SECOND FLOOR PLAN", ("Plans",))])
    legend = read_legend(catalogue, open_page)
    counts, flags = count_devices(catalogue, open_page, legend, [])
    assert {(c.sheet, c.label) for c in counts} == {("M-201", "T"), ("M-201", "TB")}   # the legend sheet isn't counted
    found = _by_label(counts)
    assert found["T"].in_legend is True
    assert (found["TB"].in_legend, found["TB"].count) == (False, 2)
    assert flags == ["'TB' counted on M-201 but not in the job's legend — check what it means"]


def test_typical_floor_titles():
    sheets = (Sheet(DOC, 1, "M-110.00", "MECHANICAL 10TH-16TH FLOOR PLAN TYPICAL", "Mechanical", ("Plans",)),
              Sheet(DOC, 2, "M-112.00", "MECHANICAL 12TH-14TH FLOOR PLAN TYPICAL", "Mechanical", ("Plans",)),
              Sheet(DOC, 3, "M-118.00", "MECHANICAL 18TH - 21ST ERV LEVEL FLOOR PLAN TYP.", "Mechanical", ("Plans",)),
              Sheet(DOC, 4, "M-102.00", "MECHANICAL 2ND THRU 5TH FLOOR PLAN TYPICAL", "Mechanical", ("Plans",)),
              Sheet(DOC, 5, "P-118.00", "PLUMBING 18TH - 19ST FLOOR PLAN TYPICAL", "Plumbing", ("Plans",)),
              Sheet(DOC, 6, "P-109.00", "PLUMBING 9th-12th FLOOR PLAN TYPICAL", "Plumbing", ("Plans",)),
              Sheet(DOC, 7, "M-121.00", "MECHANICAL 21ST FLOOR PLAN TYPICAL", "Mechanical", ("Plans",)),
              Sheet(DOC, 8, "M-130.00", "MECHANICAL 30TH-32ND FLOOR PLAN", "Mechanical", ("Plans",)))
    pages = tuple(PageRecord(DOC, i, "text", "x", 0, True) for i in range(1, 9))
    found = {t.sheet: t for t in typical_sheets(SimpleNamespace(pages=pages, sheets=sheets))}
    assert set(found) == {"M-110.00", "M-112.00", "M-118.00", "M-102.00", "P-118.00", "P-109.00"}
    assert found["M-110.00"].floors == ("10", "11", "12", "13", "14", "15", "16")
    assert found["M-110.00"].title == "MECHANICAL 10TH-16TH FLOOR PLAN TYPICAL"
    assert found["M-112.00"].floors == ("12", "13", "14")
    assert "Floor 13 may not exist — check the floor list" in found["M-112.00"].note
    assert found["M-118.00"].floors == ("18", "19", "20", "21")
    assert found["M-118.00"].note == "Typical plan M-118.00 → floors 18–21: 4 floors. Check the floor list."
    assert found["M-102.00"].floors == ("2", "3", "4", "5")
    assert found["P-118.00"].floors == ("18", "19")
    assert len(found["P-109.00"].floors) == 4


def test_a_typical_sheet_repeated_per_floor_is_counted_once_and_multiplied(opener):
    build, open_page = opener
    title = "MECHANICAL 10TH-16TH FLOOR PLAN TYPICAL"
    catalogue = build([(PLAN, "M-110.00", title, ("Plans",)), (PLAN, "M-110.00", title, ("Plans",))],
                      texts=["same text", "same text"])
    typicals = typical_sheets(catalogue)
    [typical] = typicals
    assert "on 2 pages" in typical.note and "7 floors" in typical.note
    counts, _ = count_devices(catalogue, open_page, [], typicals)
    [t] = [c for c in counts if c.label == "T"]
    assert (t.page, t.count, t.floors, t.total) == (1, 3, 7, 21)


def test_a_typical_sheet_on_one_page_says_nothing_about_pages():
    sheets = (Sheet(DOC, 1, "M-110.00", "MECHANICAL 10TH-16TH FLOOR PLAN TYPICAL", "Mechanical", ("Plans",)),)
    pages = (PageRecord(DOC, 1, "text", "x", 0, True),)
    [typical] = typical_sheets(SimpleNamespace(pages=pages, sheets=sheets))
    assert typical.note == "Typical plan M-110.00 → floors 10–16: 7 floors. Floor 13 may not exist — check the floor list."


def test_a_plan_printed_on_one_page_per_floor_is_counted_once_and_multiplied(opener):
    """26-0193: M-113.00 "LEVEL 13 TO 22 MECHANICAL PLAN" is the same page ten times, one per floor."""
    build, open_page = opener
    title = "LEVEL 13 TO 15 MECHANICAL PLAN"
    catalogue = build([(PLAN, "M-113.00", title, ("Plans",))] * 3, texts=["same plan"] * 3)
    [typical] = typical_sheets(catalogue)
    assert typical.sheet == "M-113.00" and typical.floors == ("13", "14", "15")
    assert "on 3 pages" in typical.note and "multiplied by 3" in typical.note
    assert "may not exist" not in typical.note      # a page for floor 13 is there
    counts, _ = count_devices(catalogue, open_page, [], [typical])
    [t] = [c for c in counts if c.label == "T"]
    assert (t.page, t.count, t.floors, t.total) == (1, 3, 3, 9)


def test_a_plan_repeated_with_no_floor_range_is_multiplied_by_its_pages(opener):
    build, open_page = opener
    catalogue = build([(PLAN, "M-104.00", "MECHANICAL PLAN", ("Plans",))] * 2, texts=["same plan"] * 2)
    [typical] = typical_sheets(catalogue)
    assert len(typical.floors) == 2 and "on 2 pages" in typical.note and "multiplied by 2" in typical.note
    counts, _ = count_devices(catalogue, open_page, [], [typical])
    assert [c.total for c in counts if c.label == "T"] == [6]


def test_a_sheet_number_on_pages_with_different_text_is_not_a_repeated_plan(opener):
    build, _ = opener
    catalogue = build([(PLAN, "M-104.00", "MECHANICAL PLAN", ("Plans",))] * 2, texts=["part A", "part B"])
    assert typical_sheets(catalogue) == []


def test_a_typical_plan_can_name_its_floors_as_levels():
    sheets = (Sheet(DOC, 1, "M-113.00", "LEVEL 13 TO 22 TYPICAL MECHANICAL PLAN", "Mechanical", ("Plans",)),
              Sheet(DOC, 2, "M-130.00", "LEVELS 30 - 32 MECHANICAL PLAN", "Mechanical", ("Plans",)))
    pages = tuple(PageRecord(DOC, i, "text", "x", 0, True) for i in (1, 2))
    found = {t.sheet: t for t in typical_sheets(SimpleNamespace(pages=pages, sheets=sheets))}
    assert set(found) == {"M-113.00"} and len(found["M-113.00"].floors) == 10


def test_no_labels_on_any_plan_is_flagged(opener):
    build, open_page = opener
    catalogue = build([(EMPTY_PLAN, "M-201", "MECHANICAL SECOND FLOOR PLAN", ("Plans",))])
    counts, flags = count_devices(catalogue, open_page, [], [])
    assert counts == []
    assert flags == ["No device labels found on the plan sheets (1 sheet searched) — "
                     "device quantities will come from the sequence and point list"]


def test_only_sheets_that_carry_controls_scope_are_counted(opener):
    """An architectural or electrical plan carries its own T and OCC labels (lighting sensors,
    thermostats by others) — noise for the controls count. Only the controls disciplines count."""
    from dataclasses import replace

    build, open_page = opener
    catalogue = build([(PLAN, "M-201", "MECHANICAL SECOND FLOOR PLAN", ("Plans",)),
                       (PLAN, "E-201", "ELECTRICAL SECOND FLOOR PLAN", ("Plans",)),
                       (PLAN, "A-201", "ARCHITECTURAL SECOND FLOOR PLAN", ("Plans",))])
    disciplines = {"M-201": "Mechanical", "E-201": "Electrical", "A-201": "Architectural"}
    catalogue.sheets = tuple(replace(s, discipline=disciplines[s.number]) for s in catalogue.sheets)
    counts, _ = count_devices(catalogue, open_page, [], [])
    assert {c.sheet for c in counts} == {"M-201"}


# ---- one count per sheet number, whatever the set holds (review findings 1, 5 and 6) -----------

TWO_T = _plan((400, 500, "T", 12), (700, 500, "T", 12))
TYPICAL = "MECHANICAL 10TH-16TH FLOOR PLAN TYPICAL"


def _two_documents(tmp_path, base_pages, addendum_pages):
    """A base set and an addendum, each [(Page, number, title)]; returns the catalogue and an opener."""
    docs = {"Base/Mech.pdf": base_pages, "Addendum 1/Mech.pdf": addendum_pages}
    opened = {name: pymupdf.open(str(make_pdf(tmp_path / name, *(p for p, *_ in pages))))
              for name, pages in docs.items()}
    sheets = tuple(Sheet(name, i, number, title, "Mechanical", ("Plans",))
                   for name, pages in docs.items() for i, (_, number, title) in enumerate(pages, start=1))
    records = tuple(PageRecord(name, i, "text", f"{name} page {i}", 0, True)
                    for name, pages in docs.items() for i in range(1, len(pages) + 1))
    return SimpleNamespace(pages=records, sheets=sheets), (lambda document, page: opened[document][page - 1])


def test_a_typical_sheet_in_the_base_set_and_an_addendum_is_counted_once(tmp_path):
    """2 thermostats on a typical floor over 7 floors is 14, not 28."""
    catalogue, open_page = _two_documents(tmp_path, [(TWO_T, "M-110", TYPICAL)], [(TWO_T, "M-110", TYPICAL)])
    typicals = typical_sheets(catalogue)
    counts, _ = count_devices(catalogue, open_page, [], typicals)
    assert [(c.document, c.label, c.total) for c in counts] == [("Base/Mech.pdf", "T", 14)]


def test_the_governing_page_is_the_one_counted(tmp_path):
    catalogue, open_page = _two_documents(tmp_path, [(TWO_T, "M-201", "SECOND FLOOR PLAN")],
                                          [(PLAN, "M-201", "SECOND FLOOR PLAN")])
    counts, _ = count_devices(catalogue, open_page, [], [], pages={("Addendum 1/Mech.pdf", 1)})
    assert {(c.document, c.label, c.total) for c in counts} == {("Addendum 1/Mech.pdf", "T", 3),
                                                                ("Addendum 1/Mech.pdf", "OCC", 2)}


def test_a_typical_sheet_printed_per_floor_with_different_text_is_counted_on_its_first_page(opener):
    build, open_page = opener
    catalogue = build([(PLAN, "M-110.00", TYPICAL, ("Plans",)), (PLAN, "M-110.00", TYPICAL, ("Plans",))],
                      texts=["floor 10", "floor 11"])
    counts, _ = count_devices(catalogue, open_page, [], typical_sheets(catalogue))
    [t] = [c for c in counts if c.label == "T"]
    assert (t.page, t.count, t.floors, t.total) == (1, 3, 7, 21)


def test_a_page_that_cannot_be_read_is_skipped_and_flagged(opener):
    build, open_page = opener
    catalogue = build([(PLAN, "M-201", "MECHANICAL SECOND FLOOR PLAN", ("Plans",)),
                       (PLAN, "M-202", "MECHANICAL THIRD FLOOR PLAN", ("Plans",))])

    def flaky(document, page):
        if page == 2:
            raise RuntimeError("code=2: broken content stream")
        return open_page(document, page)

    counts, flags = count_devices(catalogue, flaky, [], [])
    assert {c.sheet for c in counts} == {"M-201"}
    assert flags == ["M-202 (Mech.pdf page 2) could not be read for devices — code=2: broken content stream; "
                     "check it by hand"]


def test_a_legend_page_that_cannot_be_read_is_skipped_and_flagged(opener):
    build, _ = opener
    catalogue = build([(LEGEND, "M-002", "MECHANICAL LEGEND", ("Notes and legends",))])

    def broken(document, page):
        raise RuntimeError("cannot open broken document")

    flags: list[str] = []
    assert read_legend(catalogue, broken, flags=flags) == []
    assert flags == ["M-002 (Mech.pdf page 1) could not be read for the legend — cannot open broken document; "
                     "check it by hand"]
