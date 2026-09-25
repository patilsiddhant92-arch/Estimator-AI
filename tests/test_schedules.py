"""Reading the equipment schedules off a drawing sheet: one table per schedule, one row per unit."""
import itertools
from pathlib import Path

import pymupdf

from estimator.catalogue.documents import Document, JobFolder
from estimator.catalogue.job import Catalogue
from estimator.catalogue.qualify import BidCheck
from estimator.catalogue.register import PageRecord
from estimator.catalogue.sheet_types import Sheet
from estimator.reading.schedules import expand_tags, read_schedules
from pdfs import Page, make_pdf

DOC = "2. Takeoffs/1. Base Takeoff/Mech.pdf"
WIDTH, HEIGHT = 2592, 1728
_NAMES = itertools.count()


def grid(x0, y0, widths, rows, height=16):
    """A ruled table: every row and column drawn with lines, each cell's text inside it."""
    xs = [x0]
    for w in widths:
        xs.append(xs[-1] + w)
    lines = [(xs[0], y0 + r * height, xs[-1], y0 + r * height) for r in range(len(rows) + 1)]
    lines += [(x, y0, x, y0 + len(rows) * height) for x in xs]
    texts = [(xs[c] + 3, y0 + r * height + height * 0.7, text, 8)
             for r, row in enumerate(rows) for c, text in enumerate(row) if text]
    return tuple(lines), tuple(texts)


def catalogue_for(tmp_path: Path, *pages: tuple[tuple, tuple], sheet="M-601", title="MECHANICAL SCHEDULES",
                  types=("Schedules",), discipline="Mechanical"):
    path = make_pdf(tmp_path / f"Mech{next(_NAMES)}.pdf", *(Page(WIDTH, HEIGHT, texts, lines=lines) for lines, texts in pages))
    document = Document(path, DOC, "drawings", "base", len(pages))
    job = JobFolder("26-9999", tmp_path, (document,), ())
    opened = pymupdf.open(path)
    records = tuple(PageRecord(DOC, n, "text", opened[n - 1].get_text(), 0, large_sheet=True) for n in range(1, len(pages) + 1))
    sheets = tuple(Sheet(DOC, n, sheet if n == 1 else f"{sheet}-{n}", title, discipline, types) for n in range(1, len(pages) + 1))
    catalogue = Catalogue(job, records, sheets, (), BidCheck("Qualifies", "", (), (), ()), (), ())
    return catalogue, (lambda document, page: opened[page - 1])


VAV_ROWS = [["VAV BOX SCHEDULE", "", "", "", ""],
            ["TAG", "SERVES", "MAX CFM", "MANUFACTURER", "MODEL"],
            ["VAV-1", "OFFICE 101", "600", "TITUS", "DESV"],
            ["VAV-2", "OFFICE 102", "700", "TITUS", "DESV"],
            ["VAV-3", "OFFICE 103", "500", "TITUS", "DESV"]]


def vav_page():
    lines, texts = grid(200, 200, [90, 120, 70, 100, 70], VAV_ROWS)
    notes = ((200, 300, "NOTES:", 8),
             (200, 312, "1. DIGITAL CONTROLS FURNISHED BY TEMPERATURE CONTROL CONTRACTOR.", 8),
             (200, 324, "2. PROVIDE HANGERS AT EACH CORNER.", 8))
    return lines, texts + notes


def test_a_vav_schedule_is_read_row_by_row_with_its_notes(tmp_path):
    catalogue, opener = catalogue_for(tmp_path, vav_page())
    [schedule] = read_schedules(catalogue, opener)
    assert schedule.sheet == "M-601" and schedule.page == 1 and schedule.document == DOC
    assert schedule.title == "VAV BOX SCHEDULE"
    assert schedule.headers == ("TAG", "SERVES", "MAX CFM", "MANUFACTURER", "MODEL")
    assert [row.tag for row in schedule.rows] == ["VAV-1", "VAV-2", "VAV-3"]
    assert schedule.rows[0].cells["SERVES"] == "OFFICE 101"
    assert schedule.rows[0].manufacturer == "TITUS" and schedule.rows[0].model == "DESV"
    assert not schedule.type_only
    assert schedule.notes[0].startswith("1. DIGITAL CONTROLS FURNISHED")
    assert schedule.controls_by == ("DIGITAL CONTROLS FURNISHED BY TEMPERATURE CONTROL CONTRACTOR.",)


def test_a_sheet_turned_on_its_side_is_read_as_viewed(tmp_path):
    """Most real sheets are stored portrait and turned 270°: the words must line up with the table."""
    doc = pymupdf.open()
    page = doc.new_page(width=HEIGHT, height=WIDTH)
    page.set_rotation(270)
    matrix = page.derotation_matrix
    lines, texts = vav_page()
    for x0, y0, x1, y1 in lines:
        page.draw_line(pymupdf.Point(x0, y0) * matrix, pymupdf.Point(x1, y1) * matrix)
    for x, y, text, size in texts:
        page.insert_text(pymupdf.Point(x, y) * matrix, text, fontsize=size, rotate=270)
    path = tmp_path / "turned.pdf"
    doc.save(str(path))
    opened = pymupdf.open(path)
    record = PageRecord(DOC, 1, "text", opened[0].get_text(), 270, large_sheet=True)
    sheet = Sheet(DOC, 1, "M-601", "MECHANICAL SCHEDULES", "Mechanical", ("Schedules",))
    catalogue = Catalogue(JobFolder("26-9999", tmp_path, (), ()), (record,), (sheet,), (),
                          BidCheck("Qualifies", "", (), (), ()), (), ())
    [schedule] = read_schedules(catalogue, lambda document, n: opened[n - 1])
    assert [row.tag for row in schedule.rows] == ["VAV-1", "VAV-2", "VAV-3"]
    assert schedule.title == "VAV BOX SCHEDULE"
    assert schedule.controls_by == ("DIGITAL CONTROLS FURNISHED BY TEMPERATURE CONTROL CONTRACTOR.",)


def test_the_title_can_sit_just_above_the_table(tmp_path):
    lines, texts = grid(200, 200, [90, 120, 70], [["UNIT NO.", "SERVICE", "CFM"], ["EF-1", "TOILETS", "300"],
                                                  ["EF-2", "JANITOR", "150"]])
    catalogue, opener = catalogue_for(tmp_path, (lines, texts + ((200, 192, "EXHAUST FAN SCHEDULE", 10),)))
    [schedule] = read_schedules(catalogue, opener)
    assert schedule.title == "EXHAUST FAN SCHEDULE"
    assert [row.tag for row in schedule.rows] == ["EF-1", "EF-2"]


def test_a_tag_cell_spanning_split_rows_is_read_once(tmp_path):
    """Some columns split each unit's row in two (summer / winter); the tag cell spans both."""
    xs = (200, 290, 410, 480)
    lines = [(200, 200, 480, 200), (200, 216, 480, 216), (200, 248, 480, 248), (200, 280, 480, 280),
             (290, 232, 480, 232), (290, 264, 480, 264)] + [(x, 200, x, 280) for x in xs]
    texts = ((203, 211, "TAG", 8), (293, 211, "SERVES", 8), (413, 211, "CFM", 8),
             (203, 235, "AHU-1", 8), (293, 227, "GYM", 8), (413, 227, "900", 8), (413, 243, "700", 8),
             (203, 267, "AHU-2", 8), (293, 259, "CAFE", 8), (413, 259, "800", 8), (413, 275, "600", 8),
             (200, 192, "AIR HANDLING UNIT SCHEDULE", 10))
    catalogue, opener = catalogue_for(tmp_path, (tuple(lines), texts))
    [schedule] = read_schedules(catalogue, opener)
    assert [row.tag for row in schedule.rows] == ["AHU-1", "AHU-2"]


def test_a_tag_named_in_the_next_column_is_not_the_units_tag(tmp_path):
    lines, texts = grid(200, 200, [60, 120, 70], [["UNIT NO.", "SERVICE", "CFM"], ["ST-1S", "AHU-1 SUPPLY", "900"],
                                                  ["ST-1R", "AHU-1 RETURN", "800"]])
    catalogue, opener = catalogue_for(tmp_path, (lines, texts + ((200, 192, "DUCT SILENCER SCHEDULE", 10),)))
    [schedule] = read_schedules(catalogue, opener)
    assert schedule.type_only and [row.tag for row in schedule.rows] == [None, None]


def test_a_note_row_naming_a_unit_is_not_a_second_listing(tmp_path):
    lines, texts = grid(200, 200, [90, 120, 70], [["UNIT NO.", "SERVICE", "CFM"], ["EF-1", "TOILETS", "300"],
                                                  ["1. EF-1 SHALL RUN", "", ""], ["EF-1 TO RUN WITH AHU-1", "", ""]])
    catalogue, opener = catalogue_for(tmp_path, (lines, texts + ((200, 192, "FAN SCHEDULE", 10),)))
    [schedule] = read_schedules(catalogue, opener)
    assert [row.tag for row in schedule.rows] == ["EF-1"]


def test_a_refrigerant_calculation_table_is_not_a_schedule(tmp_path):
    lines, texts = grid(200, 200, [90, 120, 70], [["EQUIPMENT TAG", "ROOM", "AREA"], ["AC-1", "OFFICE", "300"],
                                                  ["ACCU-1", "ROOF", "900"]])
    catalogue, opener = catalogue_for(tmp_path, (lines, texts + ((200, 192, "REFRIGERANT CONCENTRATION CALCULATION", 10),)))
    assert read_schedules(catalogue, opener) == []


def test_a_whole_sheet_border_table_is_dropped(tmp_path):
    border = ((20, 20, 2572, 20), (20, 1708, 2572, 1708), (20, 20, 20, 1708), (2572, 20, 2572, 1708),
              (2300, 20, 2300, 1708), (2300, 1400, 2572, 1400), (2300, 1550, 2572, 1550))
    border_text = ((2310, 1450, "ACME ENGINEERS", 10), (2310, 1600, "M-601 MECHANICAL SCHEDULES", 10),
                   (100, 100, "GENERAL NOTES: ALL DUCTWORK SHALL BE SUPPORTED FROM THE STRUCTURE ABOVE.", 10))
    catalogue, opener = catalogue_for(tmp_path, (border, border_text))
    assert read_schedules(catalogue, opener) == []
    lines, texts = vav_page()
    catalogue, opener = catalogue_for(tmp_path, (border + lines, border_text + texts))
    [schedule] = read_schedules(catalogue, opener)
    assert [row.tag for row in schedule.rows] == ["VAV-1", "VAV-2", "VAV-3"]


def test_small_tables_are_not_schedules(tmp_path):
    lines, texts = grid(200, 200, [90, 120], [["TAG", "CFM"], ["VAV-1", "600"]])
    catalogue, opener = catalogue_for(tmp_path, (lines, texts))
    assert read_schedules(catalogue, opener) == []


def test_thru_and_comma_lists_expand_into_separate_tags():
    assert expand_tags("VAV-1 THRU VAV-4") == ["VAV-1", "VAV-2", "VAV-3", "VAV-4"]
    assert expand_tags("VAV-1 THRU 3") == ["VAV-1", "VAV-2", "VAV-3"]
    assert expand_tags("EF-1,2,3") == ["EF-1", "EF-2", "EF-3"]
    assert expand_tags("VAV-21-01 THRU VAV-21-03") == ["VAV-21-01", "VAV-21-02", "VAV-21-03"]
    assert expand_tags("AHU-1") == ["AHU-1"]
    assert expand_tags("OFFICE 101") == []


def test_a_tag_cell_with_words_before_the_number_is_one_unit():
    assert expand_tags("AC-EMR-1") == ["AC-EMR-1"]
    assert expand_tags("ACCU-LOBBY-2") == ["ACCU-LOBBY-2"]
    assert expand_tags("AC-ATS-1.2") == ["AC-ATS-1.2"]
    assert expand_tags("AC-POWER") == []


def test_a_thru_row_gives_one_row_per_unit(tmp_path):
    lines, texts = grid(200, 200, [120, 120, 70], [["TAG", "SERVES", "CFM"], ["VAV-1 THRU VAV-3", "OFFICES", "600"],
                                                   ["EF-1,2", "TOILETS", "300"]])
    catalogue, opener = catalogue_for(tmp_path, (lines, texts + ((200, 192, "VAV BOX SCHEDULE", 10),)))
    [schedule] = read_schedules(catalogue, opener)
    assert [row.tag for row in schedule.rows] == ["VAV-1", "VAV-2", "VAV-3", "EF-1", "EF-2"]


def test_a_tag_listed_twice_is_kept_twice(tmp_path):
    lines, texts = grid(200, 200, [90, 120, 70], [["TAG", "SERVES", "CFM"], ["FCU-7-1", "LOBBY", "600"],
                                                  ["FCU-7-1", "LOBBY", "650"], ["FCU-7-2", "HALL", "400"]])
    catalogue, opener = catalogue_for(tmp_path, (lines, texts))
    [schedule] = read_schedules(catalogue, opener)
    assert [row.tag for row in schedule.rows] == ["FCU-7-1", "FCU-7-1", "FCU-7-2"]


def test_a_type_only_diffuser_schedule(tmp_path):
    lines, texts = grid(200, 200, [60, 120, 90, 90], [["DIFFUSER SCHEDULE", "", "", ""],
                                                      ["TYPE", "SERVICE", "FACE SIZE", "MODEL"],
                                                      ["CD", "SUPPLY", "24X24", "OMNI"],
                                                      ["EG", "EXHAUST", "12X12", "350RL"],
                                                      ["RG", "RETURN", "24X24", "350RL"]])
    catalogue, opener = catalogue_for(tmp_path, (lines, texts))
    [schedule] = read_schedules(catalogue, opener)
    assert schedule.type_only
    assert schedule.title == "DIFFUSER SCHEDULE"
    assert [row.tag for row in schedule.rows] == [None, None, None]
    assert [row.cells["TYPE"] for row in schedule.rows] == ["CD", "EG", "RG"]


def test_an_existing_row_is_marked(tmp_path):
    lines, texts = grid(200, 200, [90, 120, 120], [["TAG", "SERVES", "REMARKS"], ["AHU-1", "GYM", "EXISTING TO REMAIN"],
                                                   ["AHU-2", "CAFE", "NEW"], ["(E) AHU-3", "HALL", ""]])
    catalogue, opener = catalogue_for(tmp_path, (lines, texts + ((200, 192, "AIR HANDLING UNIT SCHEDULE", 10),)))
    [schedule] = read_schedules(catalogue, opener)
    assert [(row.tag, row.existing) for row in schedule.rows] == [("AHU-1", True), ("AHU-2", False), ("AHU-3", True)]


def test_two_schedules_stacked_in_one_table_are_split(tmp_path):
    rows = [["FANS", "", ""], ["UNIT No.", "SERVICE", "CFM"], ["EF-21-IT", "IT ROOM", "250"], ["EF-22", "TOILET", "100"],
            ["VARIABLE AIR VOLUME BOX SCHEDULE", "", ""], ["TAG", "INLET", "MAX CFM"],
            ["VAV-21-01", "8\"", "600"], ["VAV-21-02", "9\"", "700"]]
    lines, texts = grid(200, 200, [120, 120, 70], rows)
    catalogue, opener = catalogue_for(tmp_path, (lines, texts))
    fans, vavs = read_schedules(catalogue, opener)
    assert fans.title == "FANS" and [r.tag for r in fans.rows] == ["EF-21-IT", "EF-22"]
    assert vavs.title == "VARIABLE AIR VOLUME BOX SCHEDULE" and [r.tag for r in vavs.rows] == ["VAV-21-01", "VAV-21-02"]


def test_only_controls_disciplines_and_schedule_sheets_are_read(tmp_path):
    catalogue, opener = catalogue_for(tmp_path, vav_page(), discipline="Electrical")
    assert read_schedules(catalogue, opener) == []
    catalogue, opener = catalogue_for(tmp_path, ((), ((200, 200, "MECHANICAL FLOOR PLAN - SEE SCHEDULE ON M-601", 10),)),
                                      title="FLOOR PLAN", types=("Plans",))
    assert read_schedules(catalogue, opener) == []


def test_a_page_that_cannot_be_read_is_skipped_and_flagged(tmp_path):
    """One bad page never stops the run: it is skipped and said in plain words (review finding 5)."""
    catalogue, opener = catalogue_for(tmp_path, vav_page(), vav_page())

    def flaky(document, page):
        if page == 1:
            raise RuntimeError("find_tables failed")
        return opener(document, page)

    flags: list[str] = []
    [schedule] = read_schedules(catalogue, flaky, flags=flags)
    assert schedule.page == 2
    assert flags == ["M-601 (Mech.pdf page 1) could not be read for schedules — find_tables failed; check it by hand"]


def test_only_the_pages_given_are_read(tmp_path):
    catalogue, opener = catalogue_for(tmp_path, vav_page(), vav_page())
    assert [s.page for s in read_schedules(catalogue, opener, pages={(DOC, 2)})] == [2]


# --- a tag column counts every unit, whatever its prefix ----------------------------------------------

def test_a_tag_column_counts_units_whose_prefix_is_not_in_the_equipment_list(tmp_path):
    lines, texts = grid(200, 200, [90, 140, 70], [["FAN SCHEDULE", "", ""],
                                                  ["TAG", "SERVICE", "CFM"],
                                                  ["TXF-B", "TOILET EXHAUST", "400"],
                                                  ["SPXF-A,B,C", "SMOKE PURGE", "9000"],
                                                  ["DXF1-1", "DRYER EXHAUST", "200"],
                                                  ["EF-4", "GENERAL EXHAUST", "300"]])
    catalogue, opener = catalogue_for(tmp_path, (lines, texts))
    [schedule] = read_schedules(catalogue, opener)
    assert not schedule.type_only
    assert [row.tag for row in schedule.rows] == ["TXF-B", "SPXF-A", "SPXF-B", "SPXF-C", "DXF-1-1", "EF-4"]
    assert [row.kind for row in schedule.rows] == ["Fan"] * 5 + [None]    # EF is in the equipment list
    assert schedule.rows[1].cells["SERVICE"] == "SMOKE PURGE"


def test_a_tag_column_of_type_letters_stays_type_only(tmp_path):
    lines, texts = grid(200, 200, [60, 160, 90], [["AIR DEVICE SCHEDULE", "", ""],
                                                  ["TAG", "APPLICATION", "MODEL"],
                                                  ["CD", "CEILING DIFFUSER", "OMNI"],
                                                  ["EG", "EXHAUST GRILLE", "350RL"],
                                                  ["RG", "RETURN GRILLE", "350RL"],
                                                  ["LD-A", "LINEAR DIFFUSER", "ML"]])
    catalogue, opener = catalogue_for(tmp_path, (lines, texts))
    [schedule] = read_schedules(catalogue, opener)
    assert schedule.type_only and [row.tag for row in schedule.rows] == [None] * 4


def test_air_devices_under_a_tag_header_are_types_not_units(tmp_path):
    lines, texts = grid(200, 200, [60, 160, 90], [["GRILLES, REGISTERS, & DIFFUSERS SCHEDULE", "", ""],
                                                  ["TAG", "APPLICATION", "MODEL"],
                                                  ["LG-6", "LINEAR BAR GRILLE", "LBG"],
                                                  ["LD-A", "LINEAR DIFFUSER", "ML"],
                                                  ["LR-A", "LINEAR RETURN", "ML"]])
    catalogue, opener = catalogue_for(tmp_path, (lines, texts))
    [schedule] = read_schedules(catalogue, opener)
    assert schedule.type_only


# --- schedules whose tables can't be read are counted from the sheet's text ---------------------------

from estimator.reading.schedules import schedules_from_text   # noqa: E402

_OCR_TEXT = """HVAC SCHEDULES
H601
ROOFTOP UNIT SCHEDULE (1 OF 2)
TAG | AREA SERVED | CFM
| RTU-1 | GYMNASIUM | 8000
[RTu2 | GYMNASIUM | 8000
| RTU-t | WEIGHT ROOM | 4800 | TRANE | SS-120VXMR
PROVIDE AS 100 PERCENT OUTDOOR AIR
EXHAUST FAN SCHEDULE
EF-1 THRU 3 | ROOF | 400 | GREENHECK | SP-A390
NOTES:
1. RTU-1 SHALL BE PROVIDED WITH A FACTORY CONTROLLER.
2. CALL P 212.643.9055 FOR SERVICE.
"""


def test_units_are_counted_from_the_text_under_the_nearest_schedule_heading():
    schedules = schedules_from_text(_OCR_TEXT, ("Mech.pdf", 6, "H601"))
    assert [(s.title, [r.tag for r in s.rows]) for s in schedules] == [
        ("ROOFTOP UNIT SCHEDULE (1 OF 2)", ["RTU-1", "RTU-2"]),       # "RTU-t" is RTU-1 again, misread
        ("EXHAUST FAN SCHEDULE", ["EF-1", "EF-2", "EF-3"])]            # never the model number SP-A390
    assert all(s.from_text and not s.type_only for s in schedules)


def _ocr_catalogue(tmp_path, text, types=("Schedules",), status="ocr", discipline="Mechanical"):
    path = make_pdf(tmp_path / f"Mech{next(_NAMES)}.pdf", Page(WIDTH, HEIGHT, ((100, 100, "HVAC SCHEDULES", 12),)))
    document = Document(path, DOC, "drawings", "base", 1)
    job = JobFolder("26-9999", tmp_path, (document,), ())
    opened = pymupdf.open(path)
    records = (PageRecord(DOC, 1, status, text, 0, large_sheet=True),)
    sheets = (Sheet(DOC, 1, "H601", "HVAC SCHEDULES" if "Schedules" in types else "HVAC FLOOR PLAN", discipline, types),)
    catalogue = Catalogue(job, records, sheets, (), BidCheck("Qualifies", "", (), (), ()), (), ())
    return catalogue, (lambda document, page: opened[page - 1])


def test_a_schedule_sheet_read_by_ocr_with_no_readable_table_is_counted_from_its_text(tmp_path):
    catalogue, opener = _ocr_catalogue(tmp_path, _OCR_TEXT)
    schedules = read_schedules(catalogue, opener)
    assert [s.title for s in schedules] == ["ROOFTOP UNIT SCHEDULE (1 OF 2)", "EXHAUST FAN SCHEDULE"]
    assert schedules[0].sheet == "H601" and schedules[0].from_text


def test_a_plan_sheet_read_from_its_text_layer_is_not_counted_from_its_text(tmp_path):
    # A plan names every unit on it; only a schedule sheet, or a picture of a schedule, is counted from text.
    catalogue, opener = _ocr_catalogue(tmp_path, _OCR_TEXT, types=("Plans",), status="text")
    assert read_schedules(catalogue, opener) == []


def test_a_mechanical_sheet_with_a_pictured_schedule_is_counted_from_its_text(tmp_path):
    catalogue, opener = _ocr_catalogue(tmp_path, _OCR_TEXT, types=("Plans",), status="ocr")
    assert [s.title for s in read_schedules(catalogue, opener)] == ["ROOFTOP UNIT SCHEDULE (1 OF 2)",
                                                                    "EXHAUST FAN SCHEDULE"]


def test_one_letter_codes_in_a_tag_column_are_types_not_units(tmp_path):
    lines, texts = grid(200, 200, [60, 160, 90], [["TERMINAL DEVICE SCHEDULE", "", ""],
                                                  ["TAG", "DESCRIPTION", "MODEL"],
                                                  ["A-1", "SUPPLY DIFFUSER", "OMNI"],
                                                  ["C-2", "RETURN GRILLE", "350RL"],
                                                  ["R-1", "RETURN REGISTER", "350RL"]])
    catalogue, opener = catalogue_for(tmp_path, (lines, texts))
    [schedule] = read_schedules(catalogue, opener)
    assert schedule.type_only


def test_a_kind_comes_only_from_a_title_that_names_a_schedule():
    from estimator.reading.schedules import kind_from_title
    assert kind_from_title("DRYER EXHAUST & MAKE-UP AIR FAN SCHEDULE") == "Dryer Exhaust & Make-Up Air Fan"
    assert kind_from_title("ROOFTOP UNIT SCHEDULE (1 OF 2)") == "Rooftop Unit"
    assert kind_from_title("REMARKS: 1. PROVIDE UNIT WITH FACTORY WIRED DISCONNECT SWITCH.") == "Equipment"
    assert kind_from_title("Schedule (no title found)") == "Equipment"
