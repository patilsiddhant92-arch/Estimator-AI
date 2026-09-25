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
