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
2. CALL P 212.555.0100 FOR SERVICE.
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


# --- a schedule of air devices lists types, never units (HP 3, HP 20) -----------------------------------------

def _outlet_rows(title="AIR OUTLET SCHEDULE", key="DESIGNATION"):
    return [[title, "", ""], [key, "DESCRIPTION", "NECK SIZE"],
            ["B1", "LINEAR SUPPLY DIFFUSER", "8"], ["B2", "LINEAR SUPPLY DIFFUSER", "10"],
            ["B3", "LINEAR RETURN DIFFUSER", "12"], ["B4", "CURVED LINEAR DIFFUSER", "8"]]


def test_an_air_outlet_schedules_b1_to_b4_are_types_never_boilers(tmp_path):
    catalogue, opener = catalogue_for(tmp_path, grid(200, 200, [90, 200, 80], _outlet_rows()))
    flags: list[str] = []
    [schedule] = read_schedules(catalogue, opener, flags=flags)
    assert schedule.passive and schedule.type_only
    assert [row.tag for row in schedule.rows] == [None, None, None, None]
    assert [row.cells["DESIGNATION"] for row in schedule.rows] == ["B1", "B2", "B3", "B4"]
    assert flags == []              # its title says what it lists: nothing to check


def test_an_air_device_schedule_titled_only_schedule_is_known_by_its_description_cells(tmp_path):
    """Said in a flag, since only its cells tell what it lists and a list wrongly set aside would give no unit."""
    catalogue, opener = catalogue_for(tmp_path, grid(200, 200, [90, 200, 80], _outlet_rows("SCHEDULE")))
    flags: list[str] = []
    [schedule] = read_schedules(catalogue, opener, flags=flags)
    assert schedule.passive and schedule.type_only
    assert [row.tag for row in schedule.rows] == [None] * 4
    assert len(flags) == 1 and flags[0].startswith("M-601: ") and "(B1, B2, B3, B4)" in flags[0] and "never as units" in flags[0]


def test_an_air_device_schedule_with_no_title_is_known_by_its_description_cells(tmp_path):
    rows = _outlet_rows()[1:]
    lines, texts = grid(200, 200, [90, 200, 80], rows)
    catalogue, opener = catalogue_for(tmp_path, (lines, texts))
    [schedule] = read_schedules(catalogue, opener)
    assert schedule.passive and [row.tag for row in schedule.rows] == [None] * 4


def test_an_air_device_schedule_is_known_by_the_band_rows_of_its_key_column(tmp_path):
    """Grille and diffuser codes (RG-1, SD-1, B2) under bands that name the devices; SD is a smoke damper's prefix."""
    rows = [["SCHEDULE", "", ""], ["TAG", "SERVICE", "MODEL"],
            ["RETURN AND EXHAUST GRILLES", "", ""], ["RG-1", "RETURN", "350RL"], ["EG-1", "EXHAUST", "350RL"],
            ["SUPPLY DIFFUSERS", "", ""], ["SD-1", "SUPPLY", "OMNI"], ["B2", "SUPPLY", "OMNI"]]
    catalogue, opener = catalogue_for(tmp_path, grid(200, 200, [200, 90, 80], rows))
    [schedule] = read_schedules(catalogue, opener)
    assert schedule.passive and schedule.type_only
    assert not any(row.tag for row in schedule.rows)


def test_a_louver_schedule_is_passive_too(tmp_path):
    rows = [["LOUVER SCHEDULE", "", ""], ["TAG", "SIZE", "FREE AREA"], ["L-1", "48X24", "9"], ["L-2", "36X36", "11"]]
    catalogue, opener = catalogue_for(tmp_path, grid(200, 200, [90, 90, 80], rows))
    [schedule] = read_schedules(catalogue, opener)
    assert schedule.passive and schedule.type_only


def test_a_boiler_schedule_keeps_its_boilers_and_a_pump_schedule_its_pumps(tmp_path):
    for title, codes in (("BOILER SCHEDULE", ["B-1", "B-2"]), ("PUMP SCHEDULE", ["P1", "P2"])):
        rows = [[title, "", ""], ["TAG", "SERVICE", "GPM"]] + [[code, "HEATING", "40"] for code in codes]
        catalogue, opener = catalogue_for(tmp_path, grid(200, 200, [90, 120, 70], rows))
        [schedule] = read_schedules(catalogue, opener)
        assert not schedule.passive and len([row for row in schedule.rows if row.tag]) == 2, title


def test_a_schedule_naming_dampers_with_its_louvers_keeps_its_units(tmp_path):
    """Motorized dampers carry controls scope: a title that names them as well as louvers is not an air-device list."""
    rows = [["LOUVER AND DAMPER SCHEDULE", "", ""], ["TAG", "SIZE", "SERVICE"], ["MD-1", "48X24", "OUTDOOR AIR"],
            ["MD-2", "36X36", "RELIEF"]]
    catalogue, opener = catalogue_for(tmp_path, grid(200, 200, [90, 90, 90], rows))
    [schedule] = read_schedules(catalogue, opener)
    assert not schedule.passive and [row.tag for row in schedule.rows] == ["MD-1", "MD-2"]


def test_one_description_naming_a_diffuser_does_not_make_a_unit_schedule_passive(tmp_path):
    rows = [["TERMINAL UNIT SCHEDULE", "", ""], ["TAG", "DESCRIPTION", "MAX CFM"],
            ["VAV-1", "SINGLE DUCT BOX WITH DIFFUSER", "600"], ["VAV-2", "SINGLE DUCT BOX", "700"],
            ["VAV-3", "SINGLE DUCT BOX", "500"]]
    catalogue, opener = catalogue_for(tmp_path, grid(200, 200, [90, 200, 70], rows))
    [schedule] = read_schedules(catalogue, opener)
    assert not schedule.passive and [row.tag for row in schedule.rows] == ["VAV-1", "VAV-2", "VAV-3"]


def test_a_remarks_column_naming_a_diffuser_never_makes_a_unit_schedule_passive(tmp_path):
    rows = [["SCHEDULE", "", ""], ["TAG", "SERVICE", "REMARKS"], ["EF-1", "TOILETS", "ABOVE CEILING DIFFUSER"],
            ["EF-2", "JANITOR", "NEAR RETURN GRILLE"]]
    catalogue, opener = catalogue_for(tmp_path, grid(200, 200, [90, 120, 150], rows))
    [schedule] = read_schedules(catalogue, opener)
    assert not schedule.passive and [row.tag for row in schedule.rows] == ["EF-1", "EF-2"]


def test_a_schedule_read_by_eye_of_air_outlets_lists_no_units():
    from estimator.reading.schedules import schedule_from_cells
    schedule = schedule_from_cells("LINEAR DIFFUSER SCHEDULE", ["DESIGNATION", "DESCRIPTION"],
                                   [["B1", "SLOT DIFFUSER"], ["B2", "SLOT DIFFUSER"]], [], ("Mech.pdf", 4, "M-601"))
    assert schedule.passive and schedule.type_only and [row.tag for row in schedule.rows] == [None, None]
    untitled = schedule_from_cells("", ["DESIGNATION", "DESCRIPTION"],
                                   [["B1", "SLOT DIFFUSER"], ["B2", "RETURN GRILLE"]], [], ("Mech.pdf", 4, "M-601"))
    assert untitled.passive and [row.tag for row in untitled.rows] == [None, None]
    boilers = schedule_from_cells("BOILER SCHEDULE", ["TAG", "DESCRIPTION"], [["B-1", "CONDENSING"], ["B-2", "CONDENSING"]],
                                  [], ("Mech.pdf", 4, "M-601"))
    assert not boilers.passive and [row.tag for row in boilers.rows] == ["B-1", "B-2"]


# --- a band row or a line above the header that names air devices never sets a list of units aside (review) --------

def test_a_fan_schedule_under_a_band_row_that_names_air_devices_keeps_its_four_units(tmp_path):
    """EF-1 to EF-4 are fans a controller serves: a band row of their key column ("EXHAUST GRILLES AND LOUVERS") never sets
    the schedule aside, and a schedule that is kept is nothing to flag."""
    rows = [["SCHEDULE", "", ""], ["TAG", "SERVICE", "CFM"], ["EXHAUST GRILLES AND LOUVERS", "", ""],
            ["EF-1", "TOILETS", "300"], ["EF-2", "JANITOR", "150"], ["EF-3", "KITCHEN", "900"], ["EF-4", "LOBBY", "250"]]
    catalogue, opener = catalogue_for(tmp_path, grid(200, 200, [200, 90, 80], rows))
    flags: list[str] = []
    [schedule] = read_schedules(catalogue, opener, flags=flags)
    assert not schedule.passive and not schedule.type_only
    assert [row.tag for row in schedule.rows] == ["EF-1", "EF-2", "EF-3", "EF-4"]
    assert flags == []


def test_a_line_above_the_header_that_names_air_devices_never_sets_a_fan_schedule_aside(tmp_path):
    rows = [["SCHEDULE", "", ""], ["BASIS OF DESIGN: GRILLES AND LOUVERS BY OTHERS", "", ""], ["TAG", "SERVICE", "CFM"],
            ["EF-1", "TOILETS", "300"], ["EF-2", "JANITOR", "150"]]
    catalogue, opener = catalogue_for(tmp_path, grid(200, 200, [300, 90, 80], rows))
    [schedule] = read_schedules(catalogue, opener)
    assert not schedule.passive and [row.tag for row in schedule.rows] == ["EF-1", "EF-2"]


def test_a_grille_schedule_with_band_rows_stays_set_aside_when_its_codes_are_outlet_codes(tmp_path):
    """RG, SG and SD are air outlet code prefixes (`air_outlet_codes`): they never count against the band rows, so the list
    of grilles and registers is still no list of units, and it is said, since only its band rows tell what it lists."""
    rows = [["SCHEDULE", "", ""], ["TAG", "SERVICE", "MODEL"], ["RETURN GRILLES AND REGISTERS", "", ""],
            ["RG-1", "RETURN", "350RL"], ["RG-2", "RETURN", "350RL"], ["SG-1", "SUPPLY", "280"], ["SD-1", "SUPPLY", "OMNI"]]
    catalogue, opener = catalogue_for(tmp_path, grid(200, 200, [200, 90, 80], rows))
    flags: list[str] = []
    [schedule] = read_schedules(catalogue, opener, flags=flags)
    assert schedule.passive and schedule.type_only and not any(row.tag for row in schedule.rows)
    assert len(flags) == 1 and "never as units" in flags[0]


def test_a_schedule_read_by_eye_with_fans_under_an_air_device_band_keeps_its_units():
    from estimator.reading.schedules import schedule_from_cells
    cells = [["EXHAUST GRILLES AND LOUVERS", ""], ["EF-1", "TOILETS"], ["EF-2", "JANITOR"]]
    schedule = schedule_from_cells("", ["TAG", "SERVICE"], cells, [], ("Mech.pdf", 4, "M-601"))
    assert not schedule.passive and [row.tag for row in schedule.rows] == ["EF-1", "EF-2"]
    grilles = schedule_from_cells("", ["TAG", "SERVICE"], [["RETURN GRILLES", ""], ["RG-1", "RETURN"], ["SD-1", "SUPPLY"]],
                                  [], ("Mech.pdf", 4, "M-601"))
    assert grilles.passive and [row.tag for row in grilles.rows] == [None, None]


def test_an_air_device_schedule_that_holds_a_fan_tag_is_set_aside_by_its_title_but_flagged(tmp_path):
    """The title still decides, so nothing is read as a unit; but a fan's tag in the key column is said, so that a fan
    schedule titled as grilles is looked at: the dossier counts none of its fans."""
    rows = [["GRILLE AND LOUVER SCHEDULE", "", ""], ["TAG", "SIZE", "FREE AREA"], ["RG-1", "24X12", "1"],
            ["EF-1", "48X24", "9"], ["EF-2", "36X36", "11"]]
    catalogue, opener = catalogue_for(tmp_path, grid(200, 200, [90, 90, 80], rows))
    flags: list[str] = []
    [schedule] = read_schedules(catalogue, opener, flags=flags)
    assert schedule.passive and [row.tag for row in schedule.rows] == [None] * 3
    assert len(flags) == 1 and flags[0].startswith("M-601: GRILLE AND LOUVER SCHEDULE")
    assert "EF-1, EF-2" in flags[0] and "never as units" in flags[0] and flags[0].endswith("check")


def test_a_titled_air_device_schedule_whose_codes_are_types_is_nothing_to_flag(tmp_path):
    """B1 is a type code (a boiler's prefix, written with no dash), SD an air outlet's code prefix: neither is a unit's tag
    outside the air outlets' codes."""
    rows = [["AIR OUTLET SCHEDULE", "", ""], ["DESIGNATION", "DESCRIPTION", "NECK SIZE"],
            ["B1", "LINEAR SUPPLY DIFFUSER", "8"], ["SD-1", "SUPPLY DIFFUSER", "10"], ["CD", "CEILING DIFFUSER", "12"]]
    catalogue, opener = catalogue_for(tmp_path, grid(200, 200, [90, 200, 80], rows))
    flags: list[str] = []
    [schedule] = read_schedules(catalogue, opener, flags=flags)
    assert schedule.passive and flags == []


# --- a key column the reading list does not name: UNIT, PUMP NO., AC UNIT NO., or no header at all (HP 4, HP 21) ---

def test_a_unit_header_and_a_pump_no_header_are_read(tmp_path):
    ac = grid(200, 200, [90, 120, 70], [["UNIT", "SERVICE", "CFM"], ["AC-1", "OFFICE", "4000"],
                                        ["AC-2", "OFFICE", "6000"]])
    pumps = grid(200, 300, [90, 120, 70], [["CONDENSATE PUMPS", "", ""], ["PUMP No.", "SERVICE", "GPH"],
                                           ["CP-1", "AC-1", "70"], ["CP-2", "AC-2", "70"]])
    catalogue, opener = catalogue_for(tmp_path, (ac[0] + pumps[0], ac[1] + pumps[1] + ((200, 192, "AC UNITS", 10),)))
    schedules = {s.title: s for s in read_schedules(catalogue, opener)}
    assert {title: [r.tag for r in s.rows] for title, s in schedules.items()} == {
        "AC UNITS": ["AC-1", "AC-2"], "CONDENSATE PUMPS": ["CP-1", "CP-2"]}
    assert not any(s.type_only for s in schedules.values())
    assert schedules["AC UNITS"].headers == ("UNIT", "SERVICE", "CFM")
    assert schedules["AC UNITS"].rows[0].cells["SERVICE"] == "OFFICE"


def test_an_ac_unit_no_header_is_read(tmp_path):
    lines, texts = grid(200, 200, [90, 120, 70], [["AC UNIT NO.", "SERVICE", "CFM"], ["AC-1", "OFFICE", "4000"],
                                                  ["AC-2", "LOBBY", "6000"]])
    catalogue, opener = catalogue_for(tmp_path, (lines, texts + ((200, 192, "SPLIT SYSTEM AC SCHEDULE", 10),)))
    [schedule] = read_schedules(catalogue, opener)
    assert schedule.title == "SPLIT SYSTEM AC SCHEDULE" and [r.tag for r in schedule.rows] == ["AC-1", "AC-2"]


def test_a_blank_key_header_is_read_when_its_column_is_unit_tags(tmp_path):
    rows = [["EXHAUST FANS", "", "", ""], ["", "CFM", "RPM", "VOLTS"], ["EF-1", "250", "980", "115"],
            ["EF-2", "300", "1000", "115"]]
    catalogue, opener = catalogue_for(tmp_path, grid(200, 200, [90, 70, 70, 70], rows))
    flags: list[str] = []
    [schedule] = read_schedules(catalogue, opener, flags=flags)
    assert schedule.title == "EXHAUST FANS" and [r.tag for r in schedule.rows] == ["EF-1", "EF-2"]
    assert flags == ["M-601: EXHAUST FANS has no header over its unit column; its first column is read as the unit "
                     "tags — check"]
    assert schedule.rows[0].cells["CFM"] == "250" and schedule.rows[1].cells["VOLTS"] == "115"
    # the key column stays the first column, so whoever reads `headers[0]` as the unit column still finds the unit
    assert len(schedule.headers) == 4 and schedule.headers[1:] == ("CFM", "RPM", "VOLTS")
    assert schedule.rows[0].cells[schedule.headers[0]] == "EF-1"


def test_a_blank_key_header_with_the_title_above_the_table_is_read(tmp_path):
    rows = [["", "CFM", "RPM"], ["EF-1", "250", "980"], ["EF-2", "300", "1000"]]
    lines, texts = grid(200, 200, [90, 70, 70], rows)
    catalogue, opener = catalogue_for(tmp_path, (lines, texts + ((200, 192, "EXHAUST FAN SCHEDULE", 10),)))
    [schedule] = read_schedules(catalogue, opener)
    assert schedule.title == "EXHAUST FAN SCHEDULE" and [r.tag for r in schedule.rows] == ["EF-1", "EF-2"]


def test_a_unit_header_over_words_is_not_a_key_column(tmp_path):
    lines, texts = grid(200, 200, [90, 120, 70], [["UNIT", "SERVICE", "CFM"], ["CFM PER SQ FT", "OFFICE", "0.8"],
                                                  ["GPM PER TON", "LOBBY", "2.4"]])
    catalogue, opener = catalogue_for(tmp_path, (lines, texts))
    flags: list[str] = []
    assert read_schedules(catalogue, opener, flags=flags) == [] and flags == []


def test_a_sheet_no_column_is_not_a_key_column(tmp_path):
    lines, texts = grid(200, 200, [60, 120, 70], [["SHEET NO.", "TITLE", "REV"], ["M-101", "FIRST FLOOR PLAN", "2"],
                                                  ["M-102", "SECOND FLOOR PLAN", "1"]])
    catalogue, opener = catalogue_for(tmp_path, (lines, texts))
    assert read_schedules(catalogue, opener) == []


def test_two_unit_columns_side_by_side_are_two_schedules(tmp_path):
    """A split system: the indoor unit's UNIT column, then the outdoor unit's UNIT column under its own band."""
    rows = [["SPLIT SYSTEMS", "", "", "", ""], ["UNIT", "SERVICE", "OUTDOOR SECTION", "", ""],
            ["", "", "UNIT", "CFM", "VOLTS"], ["AC-1", "OFFICE", "ACCU-1", "1500", "208"]]
    catalogue, opener = catalogue_for(tmp_path, grid(200, 200, [90, 90, 90, 60, 60], rows))
    tags = sorted(row.tag for s in read_schedules(catalogue, opener) for row in s.rows if row.tag)
    assert tags == ["AC-1", "ACCU-1"]


def test_an_associated_unit_column_never_splits_the_schedule(tmp_path):
    """ASSOCIATED CONDENSING UNIT names one outdoor unit on several rows: it is no key column."""
    rows = [["INDOOR UNIT SCHEDULE", "", ""], ["TAG", "ASSOCIATED CONDENSING UNIT", "CFM"],
            ["IDU-1", "CU-1", "300"], ["IDU-2", "CU-1", "300"], ["IDU-3", "CU-1", "400"]]
    catalogue, opener = catalogue_for(tmp_path, grid(200, 200, [90, 200, 70], rows))
    [schedule] = read_schedules(catalogue, opener)
    assert [row.tag for row in schedule.rows] == ["IDU-1", "IDU-2", "IDU-3"]


def test_a_pump_schedule_on_a_plan_sheet_with_a_pump_no_header_is_read(tmp_path):
    """The sheet is no schedule sheet by its type: the word SCHEDULE and a key header line make it one."""
    lines, texts = grid(200, 300, [90, 120, 70], [["PUMP SCHEDULE", "", ""], ["PUMP NO.", "SERVICE", "GPM"],
                                                  ["P-1", "HEATING", "40"], ["P-2", "HEATING", "40"]])
    catalogue, opener = catalogue_for(tmp_path, (lines, texts), title="HEATING PIPING PLAN", types=("Plans",))
    [schedule] = read_schedules(catalogue, opener)
    assert schedule.title == "PUMP SCHEDULE" and [r.tag for r in schedule.rows] == ["P-1", "P-2"]


def test_a_sheet_no_label_in_a_title_block_does_not_make_a_plan_a_schedule_sheet(tmp_path):
    catalogue, _ = catalogue_for(tmp_path, ((), ((100, 100, "SEE SCHEDULE ON M-601", 10), (2300, 1500, "SHEET NO.", 10),
                                                 (2300, 1520, "DRAWING NO.", 10))),
                                 title="FLOOR PLAN", types=("Plans",))

    def never_opened(document, page):
        raise AssertionError("a plan with a title block is not opened as a schedule sheet")

    flags: list[str] = []
    assert read_schedules(catalogue, never_opened, flags=flags) == [] and flags == []


# --- a table that names units but cannot be read is never a silent zero --------------------------------------

def test_a_table_that_names_units_but_has_no_key_column_is_counted_from_its_text_and_flagged(tmp_path):
    """A header the reading list cannot take for a key column ("EQUIPMENT"): the units the table lists are counted
    from its text, flagged, so the sheet is pictured for a look; they are not dropped without a word."""
    lines, texts = grid(200, 200, [90, 120, 70], [["EQUIPMENT", "SERVICE", "CFM"], ["AC-1", "OFFICE", "4000"],
                                                  ["AC-2", "LOBBY", "6000"]])
    catalogue, opener = catalogue_for(tmp_path, (lines, texts + ((200, 192, "AC UNIT SCHEDULE", 10),)))
    flags: list[str] = []
    schedules = read_schedules(catalogue, opener, flags=flags)
    assert [(s.title, [r.tag for r in s.rows], s.from_text) for s in schedules] == [
        ("AC UNIT SCHEDULE", ["AC-1", "AC-2"], True)]
    assert len(flags) == 1
    assert "M-601" in flags[0] and "AC-1, AC-2" in flags[0] and "could not be read" in flags[0] and "check" in flags[0]


def test_one_readable_table_never_hides_an_unreadable_one_on_the_same_sheet(tmp_path):
    good = grid(200, 200, [90, 120, 70], [["TAG", "SERVES", "MAX CFM"], ["VAV-1", "OFFICE 101", "600"],
                                          ["VAV-2", "OFFICE 102", "700"]])
    other = grid(200, 400, [90, 120, 70], [["EQUIPMENT", "SERVICE", "CFM"], ["EF-1", "TOILETS", "300"],
                                           ["EF-2", "JANITOR", "150"]])
    titles = ((200, 192, "VAV SCHEDULE", 10), (200, 392, "EXHAUST FAN SCHEDULE", 10))
    catalogue, opener = catalogue_for(tmp_path, (good[0] + other[0], good[1] + other[1] + titles))
    flags: list[str] = []
    schedules = read_schedules(catalogue, opener, flags=flags)
    assert sorted(r.tag for s in schedules for r in s.rows) == ["EF-1", "EF-2", "VAV-1", "VAV-2"]
    assert {s.title: s.from_text for s in schedules} == {"VAV SCHEDULE": False, "EXHAUST FAN SCHEDULE": True}
    assert len(flags) == 1 and "EF-1, EF-2" in flags[0] and "could not be read" in flags[0]


def test_an_unreadable_table_on_a_sheet_that_is_not_a_schedule_sheet_is_flagged_not_counted(tmp_path):
    """On a plan sheet the units of a table that cannot be read are named in a flag only: a plan names units for
    other reasons, so nothing is counted from its text."""
    good = grid(200, 300, [90, 120, 70], [["PUMP SCHEDULE", "", ""], ["PUMP NO.", "SERVICE", "GPM"],
                                          ["P-1", "HEATING", "40"], ["P-2", "HEATING", "40"]])
    other = grid(200, 500, [90, 120, 70], [["EQUIPMENT", "SERVICE", "CFM"], ["AC-1", "OFFICE", "4000"],
                                           ["AC-2", "LOBBY", "6000"]])
    catalogue, opener = catalogue_for(tmp_path, (good[0] + other[0], good[1] + other[1]),
                                      title="HEATING PIPING PLAN", types=("Plans",))
    flags: list[str] = []
    schedules = read_schedules(catalogue, opener, flags=flags)
    assert [(s.title, [r.tag for r in s.rows], s.from_text) for s in schedules] == [("PUMP SCHEDULE", ["P-1", "P-2"], False)]
    assert len(flags) == 1 and "AC-1, AC-2" in flags[0] and "could not be read" in flags[0]


def test_a_table_that_lists_no_units_is_not_flagged(tmp_path):
    lines, texts = grid(200, 200, [90, 120, 70], [["ITEM", "NOTE", "QTY"], ["BRACKET", "WALL", "4"], ["HANGER", "ROD", "8"]])
    catalogue, opener = catalogue_for(tmp_path, (lines, texts))
    flags: list[str] = []
    assert read_schedules(catalogue, opener, flags=flags) == [] and flags == []


def test_a_type_schedule_is_not_an_unreadable_table(tmp_path):
    """Its rows are types (VAV-A): read, as type rows, so there is nothing to flag."""
    lines, texts = grid(200, 200, [90, 120, 70], [["VAV TYPE SCHEDULE", "", ""], ["TYPE", "SERVICE", "CFM"],
                                                  ["VAV-A", "OFFICES", "600"], ["VAV-B", "CORRIDORS", "300"]])
    catalogue, opener = catalogue_for(tmp_path, (lines, texts))
    flags: list[str] = []
    [schedule] = read_schedules(catalogue, opener, flags=flags)
    assert [row.tag for row in schedule.rows] == ["VAV-A", "VAV-B"] and flags == []


def test_a_passive_schedule_is_not_an_unreadable_table(tmp_path):
    catalogue, opener = catalogue_for(tmp_path, grid(200, 200, [90, 200, 80], _outlet_rows()))
    flags: list[str] = []
    read_schedules(catalogue, opener, flags=flags)
    assert flags == []


# --- notes beside a schedule table, not only under it (HP 46) ---------------------------------------------------

def _ef_table():
    return grid(200, 200, [90, 120, 70], [["UNIT NO.", "SERVICE", "CFM"], ["EF-1", "TOILETS", "300"],
                                          ["EF-2", "JANITOR", "150"]])


def test_notes_beside_a_schedule_table_are_read_as_its_notes(tmp_path):
    lines, texts = _ef_table()
    beside = ((500, 212, "NOTES:", 8), (500, 224, "1. PROVIDE MOTORIZED DAMPER WITH ACTUATOR AND END SWITCH.", 8),
              (500, 236, "2. FAN RUNS WITH THE BMS TIME SCHEDULE.", 8))
    catalogue, opener = catalogue_for(tmp_path, (lines, texts + ((200, 192, "EXHAUST FAN SCHEDULE", 10),) + beside))
    [schedule] = read_schedules(catalogue, opener)
    assert schedule.notes == ("1. PROVIDE MOTORIZED DAMPER WITH ACTUATOR AND END SWITCH.",
                              "2. FAN RUNS WITH THE BMS TIME SCHEDULE.")
    assert schedule.controls_by == ("FAN RUNS WITH THE BMS TIME SCHEDULE.",)


def test_notes_beside_a_table_that_run_on_below_its_bottom_edge_are_read_whole(tmp_path):
    lines, texts = _ef_table()
    beside = ((500, 212, "NOTES:", 8), (500, 224, "1. PROVIDE MOTORIZED DAMPER.", 8), (500, 236, "2. PROVIDE END SWITCH.", 8),
              (500, 248, "3. PROVIDE ACTUATOR FOR THE", 8), (500, 260, "DAMPER, TWO POSITION.", 8),
              (500, 272, "4. WIRE THE FAN TO THE BMS.", 8))
    catalogue, opener = catalogue_for(tmp_path, (lines, texts + beside))
    [schedule] = read_schedules(catalogue, opener)
    assert schedule.notes == ("1. PROVIDE MOTORIZED DAMPER.", "2. PROVIDE END SWITCH.",
                              "3. PROVIDE ACTUATOR FOR THE DAMPER, TWO POSITION.", "4. WIRE THE FAN TO THE BMS.")


def test_notes_beside_a_table_and_notes_under_it_are_both_read(tmp_path):
    lines, texts = _ef_table()
    under = ((200, 262, "NOTES:", 8), (200, 274, "1. UNDER THE TABLE.", 8))
    beside = ((500, 212, "NOTES:", 8), (500, 224, "1. BESIDE THE TABLE.", 8))
    catalogue, opener = catalogue_for(tmp_path, (lines, texts + under + beside))
    [schedule] = read_schedules(catalogue, opener)
    assert schedule.notes == ("1. UNDER THE TABLE.", "1. BESIDE THE TABLE.")


def test_a_note_far_to_the_right_of_a_table_is_not_its_note(tmp_path):
    """The notes of another part of the sheet, a column away from the table."""
    lines, texts = _ef_table()
    far = ((1900, 212, "NOTES:", 8), (1900, 224, "1. FOR THE REST OF THE SHEET.", 8))
    catalogue, opener = catalogue_for(tmp_path, (lines, texts + far))
    [schedule] = read_schedules(catalogue, opener)
    assert schedule.notes == ()


def test_a_neighbouring_table_is_never_taken_for_the_notes_beside_a_schedule(tmp_path):
    lines, texts = _ef_table()
    neighbour = grid(500, 200, [200, 60, 60], [["TAG", "SERVES", "MAX CFM"], ["VAV-1", "OFFICE 101", "600"],
                                               ["NOTES:", "", ""], ["1. VAV NOTE", "", ""]])
    catalogue, opener = catalogue_for(tmp_path, (lines + neighbour[0], texts + neighbour[1]))
    by_first = {s.rows[0].tag: s for s in read_schedules(catalogue, opener)}
    assert by_first["EF-1"].notes == ()
    assert by_first["VAV-1"].notes == ("1. VAV NOTE",)


def test_notes_beside_the_lower_schedule_of_two_stacked_schedules_are_its_own(tmp_path):
    rows = [["FANS", "", ""], ["UNIT No.", "SERVICE", "CFM"], ["EF-21-IT", "IT ROOM", "250"], ["EF-22", "TOILET", "100"],
            ["VARIABLE AIR VOLUME BOX SCHEDULE", "", ""], ["TAG", "INLET", "MAX CFM"],
            ["VAV-21-01", "8\"", "600"], ["VAV-21-02", "9\"", "700"]]
    lines, texts = grid(200, 200, [120, 120, 70], rows)
    beside = ((540, 280, "NOTES:", 8), (540, 292, "1. BOXES ARE FACTORY CONTROLLED.", 8))
    catalogue, opener = catalogue_for(tmp_path, (lines, texts + beside))
    fans, vavs = read_schedules(catalogue, opener)
    assert fans.notes == () and vavs.notes == ("1. BOXES ARE FACTORY CONTROLLED.",)


def test_a_notes_block_beside_two_tables_one_above_the_other_is_the_notes_of_the_one_it_begins_beside(tmp_path):
    """The block's heading lines up with the upper table; its tail runs on beside the lower one, which does not
    claim note 5 as the start of notes of its own."""
    upper = grid(200, 200, [90, 120, 70], [["UNIT NO.", "SERVICE", "CFM"], ["EF-1", "TOILETS", "300"],
                                           ["EF-2", "JANITOR", "150"]])
    lower = grid(200, 270, [90, 120, 70], [["TAG", "SERVES", "MAX CFM"], ["VAV-1", "OFFICE 101", "600"],
                                           ["VAV-2", "OFFICE 102", "700"]])
    beside = tuple((500, 212 + 12 * n, text, 8) for n, text in enumerate(
        ["NOTES:", "1. ONE.", "2. TWO.", "3. THREE.", "4. FOUR.", "5. FIVE.", "6. SIX."]))
    catalogue, opener = catalogue_for(tmp_path, (upper[0] + lower[0], upper[1] + lower[1] + beside))
    by_first = {s.rows[0].tag: s for s in read_schedules(catalogue, opener)}
    assert by_first["EF-1"].notes == ("1. ONE.", "2. TWO.", "3. THREE.", "4. FOUR.", "5. FIVE.", "6. SIX.")
    assert by_first["VAV-1"].notes == ()


def test_a_diffuser_schedule_in_ocr_text_gives_no_units():
    """The codes of an air outlet schedule read by OCR (B1 is a boiler's tag, SD-1 a smoke damper's) are counted
    under no heading; the fan schedule after it still is."""
    text = """AIR OUTLET SCHEDULE
B1 | LINEAR DIFFUSER | 8
B2 | LINEAR DIFFUSER | 10
SD-1 | SUPPLY DIFFUSER | 12
EXHAUST FAN SCHEDULE
EF-1 THRU 3 | ROOF | 400
"""
    schedules = schedules_from_text(text, ("Mech.pdf", 6, "H601"))
    assert [(s.title, [r.tag for r in s.rows]) for s in schedules] == [("EXHAUST FAN SCHEDULE", ["EF-1", "EF-2", "EF-3"])]


def test_a_garbled_heading_after_an_air_outlet_schedule_never_hides_the_units_that_follow():
    """The skipping that an air outlet heading starts ends at the first row of a unit of other equipment, though no
    heading ended it (OCR misread the fan schedule's own). Its rows are no air outlet schedule's: their title is unknown."""
    text = """AIR OUTLET SCHEDULE
CD-1 | CEILING DIFFUSER | 8
RG-1 | RETURN GRILLE | 12
EXHAUS7 FAN SCHEDLE
EF-1 | ROOF | 400
EF-2 | ROOF | 400
EF-3 | ROOF | 400
"""
    schedules = schedules_from_text(text, ("Mech.pdf", 6, "H601"))
    assert [row.tag for s in schedules for row in s.rows] == ["EF-1", "EF-2", "EF-3"]
    assert all(s.from_text and "AIR OUTLET" not in s.title for s in schedules)


def test_the_header_line_of_an_air_outlet_schedule_itself_does_not_end_the_skipping():
    text = """AIR OUTLET SCHEDULE
MARK | DESCRIPTION | NECK
SD-1 | SUPPLY DIFFUSER | 12
SD-2 | SUPPLY DIFFUSER | 10
"""
    assert schedules_from_text(text, ("Mech.pdf", 6, "H601")) == []


def test_a_tag_header_line_after_an_air_outlet_schedule_ends_the_skipping_too():
    """SD is an air outlet's code prefix and a smoke damper's: no row of it ends the skipping, but the header line of the
    next table, whose heading OCR misread, tells that a schedule of units starts."""
    text = """AIR OUTLET SCHEDULE
MARK | DESCRIPTION | NECK
CD-1 | CEILING DIFFUSER | 8
RG-1 | RETURN GRILLE | 12
SMOKE DAMPER SCHEDLE
MARK | SIZE | ACTUATOR
SD-1 | 24X12 | 120V
SD-2 | 12X12 | 120V
"""
    schedules = schedules_from_text(text, ("Mech.pdf", 6, "H601"))
    assert [row.tag for s in schedules for row in s.rows] == ["SD-1", "SD-2"]


def test_a_row_of_an_air_outlet_code_after_an_air_outlet_heading_is_still_skipped_beside_a_later_unit():
    text = """AIR OUTLET SCHEDULE
B1 | LINEAR DIFFUSER | 8
SD-1 | SUPPLY DIFFUSER | 12
GARBLED HEADING
AHU-1 | ROOF | 8000
"""
    schedules = schedules_from_text(text, ("Mech.pdf", 6, "H601"))
    assert [row.tag for s in schedules for row in s.rows] == ["AHU-1"]


# --- an air outlet schedule with a plain title is known by its codes (HP 3, HP 20) -----------------------------------

_OUTLET_CODES = ["RG-1", "CD-1", "SD-1", "SG-1", "EG-1", "TG-1", "LD-1"]


def _plain_rows(codes, columns=("NECK SIZE", "FACE SIZE")):
    return [["SCHEDULE", "", ""], ["MARK", *columns]] + [[code, "8", "24X24"] for code in codes]


def test_an_air_outlet_schedule_with_a_plain_title_and_no_description_is_known_by_its_codes(tmp_path):
    """RG-1, CD-1, SD-1, SG-1, EG-1, TG-1, LD-1: no air device word anywhere and no description column, so the codes say what
    it lists. Said in a flag, since a list wrongly set aside would give no unit."""
    catalogue, opener = catalogue_for(tmp_path, grid(200, 200, [90, 80, 80], _plain_rows(_OUTLET_CODES)))
    flags: list[str] = []
    [schedule] = read_schedules(catalogue, opener, flags=flags)
    assert schedule.passive and schedule.type_only
    assert [row.tag for row in schedule.rows] == [None] * 7
    assert len(flags) == 1 and "(RG-1, CD-1, SD-1, SG-1, EG-1, TG-1 …)" in flags[0] and "never as units" in flags[0]


def test_an_equipment_schedule_with_a_plain_title_is_still_read_as_units(tmp_path):
    codes = ["AHU-1", "FCU-1", "EF-1"]
    catalogue, opener = catalogue_for(tmp_path, grid(200, 200, [90, 80, 80], _plain_rows(codes, ("SERVICE", "CFM"))))
    flags: list[str] = []
    [schedule] = read_schedules(catalogue, opener, flags=flags)
    assert not schedule.passive and not schedule.type_only
    assert [row.tag for row in schedule.rows] == codes and flags == []


def test_one_kind_of_code_alone_is_no_air_outlet_list(tmp_path):
    """SD is a smoke damper's prefix as well as a supply diffuser's: a list of SD codes only keeps its units."""
    codes = ["SD-1", "SD-2", "SD-3"]
    catalogue, opener = catalogue_for(tmp_path, grid(200, 200, [90, 80, 80], _plain_rows(codes, ("SIZE", "ACTUATOR"))))
    [schedule] = read_schedules(catalogue, opener)
    assert not schedule.passive and [row.tag for row in schedule.rows] == codes


def test_a_type_column_naming_dampers_says_the_codes_are_no_air_outlets(tmp_path):
    """Two kinds of outlet code (SD, LD), but the type column says the equipment is dampers: its units are kept."""
    rows = [["SCHEDULE", "", ""], ["MARK", "TYPE", "SIZE"], ["SD-1", "SMOKE DAMPER", "24X12"],
            ["SD-2", "SMOKE DAMPER", "12X12"], ["LD-1", "MOTORIZED DAMPER", "48X24"]]
    catalogue, opener = catalogue_for(tmp_path, grid(200, 200, [90, 140, 80], rows))
    [schedule] = read_schedules(catalogue, opener)
    assert not schedule.passive and [row.tag for row in schedule.rows] == ["SD-1", "SD-2", "LD-1"]


def test_a_description_column_that_names_no_air_device_keeps_the_units_whatever_the_codes(tmp_path):
    """SD and LD can be a smoke detector's and a leak detector's: a description column decides by its words alone, and
    these name no air device, so the codes are never read for it."""
    rows = [["SCHEDULE", "", ""], ["MARK", "DESCRIPTION", "LOCATION"], ["SD-1", "SMOKE DETECTOR", "MECH ROOM"],
            ["LD-1", "LEAK DETECTOR", "BOILER ROOM"], ["LD-2", "LEAK DETECTOR", "CHILLER ROOM"]]
    catalogue, opener = catalogue_for(tmp_path, grid(200, 200, [90, 140, 120], rows))
    flags: list[str] = []
    [schedule] = read_schedules(catalogue, opener, flags=flags)
    assert not schedule.passive and [row.tag for row in schedule.rows] == ["SD-1", "LD-1", "LD-2"] and flags == []


def test_a_code_that_is_no_air_outlet_code_keeps_the_schedule_a_list_of_units(tmp_path):
    """One code in the key column is a fan's, the others look like outlets' codes: all of them must be outlet codes."""
    codes = ["RG-1", "CD-1", "EF-1"]
    catalogue, opener = catalogue_for(tmp_path, grid(200, 200, [90, 80, 80], _plain_rows(codes)))
    [schedule] = read_schedules(catalogue, opener)
    assert not schedule.passive and "EF-1" in [row.tag for row in schedule.rows]


def test_a_plain_titled_air_outlet_schedule_read_by_eye_is_known_by_its_codes():
    from estimator.reading.schedules import schedule_from_cells
    where = ("Mech.pdf", 4, "M-601")
    outlets = schedule_from_cells("", ["MARK", "NECK SIZE"], [[code, "8"] for code in _OUTLET_CODES], [], where)
    assert outlets.passive and outlets.type_only and [row.tag for row in outlets.rows] == [None] * 7
    units = schedule_from_cells("", ["MARK", "CFM"], [["AHU-1", "900"], ["FCU-1", "300"], ["EF-1", "100"]], [], where)
    assert not units.passive and [row.tag for row in units.rows] == ["AHU-1", "FCU-1", "EF-1"]


# --- a table over most of the sheet is read by any key header, and never dropped without a word ----------------------

# the sheet's border, and a title block of two columns under its first cell: three columns in all, as a table must have
_BORDER = ((20, 20, 2572, 20), (20, 1708, 2572, 1708), (20, 20, 20, 1708), (2572, 20, 2572, 1708),
           (2300, 20, 2300, 1708), (2300, 1400, 2572, 1400), (2300, 1550, 2572, 1550), (2436, 1400, 2436, 1708))


def _large_table(rows):
    """A schedule table over most of the sheet: 1800 by 1600 points of 2592 by 1728, past the border share."""
    return grid(100, 100, [800, 600, 400], rows, height=400)


def test_a_schedule_table_over_most_of_the_sheet_is_read_whatever_its_key_header(tmp_path):
    """TAG has always kept a table that large; UNIT, PUMP NO. and a blank key header give the same rows."""
    for key in ("TAG", "UNIT", "PUMP NO.", ""):
        rows = [["EXHAUST FANS", "", ""], [key, "SERVICE", "CFM"], ["EF-1", "TOILETS", "300"], ["EF-2", "JANITOR", "150"]]
        catalogue, opener = catalogue_for(tmp_path, _large_table(rows))
        flags: list[str] = []
        [schedule] = read_schedules(catalogue, opener, flags=flags)
        assert [row.tag for row in schedule.rows] == ["EF-1", "EF-2"] and not schedule.from_text, key
        assert not any("most of the sheet" in flag for flag in flags), key


def test_a_table_over_most_of_the_sheet_that_still_cannot_be_read_is_flagged_not_dropped(tmp_path):
    """A header no list knows (EQUIPMENT): the table is no border, since it names units; the units are counted from its
    text and a flag says so, like a smaller table of the same kind."""
    rows = [["EXHAUST FANS", "", ""], ["EQUIPMENT", "SERVICE", "CFM"], ["EF-1", "TOILETS", "300"], ["EF-2", "JANITOR", "150"]]
    catalogue, opener = catalogue_for(tmp_path, _large_table(rows))
    flags: list[str] = []
    schedules = read_schedules(catalogue, opener, flags=flags)
    assert sorted(row.tag for s in schedules for row in s.rows) == ["EF-1", "EF-2"] and all(s.from_text for s in schedules)
    assert len(flags) == 1
    assert "M-601" in flags[0] and "EF-1, EF-2" in flags[0] and "could not be read" in flags[0]
    assert "most of the sheet" in flags[0] and "check" in flags[0]


def test_a_sheet_border_table_that_names_no_unit_is_dropped_without_a_flag(tmp_path):
    texts = ((2310, 1450, "ACME ENGINEERS", 10), (2310, 1600, "M-601 MECHANICAL SCHEDULES", 10),
             (100, 100, "GENERAL NOTES: ALL DUCTWORK SHALL BE SUPPORTED FROM THE STRUCTURE ABOVE.", 10))
    catalogue, opener = catalogue_for(tmp_path, (_BORDER, texts))
    flags: list[str] = []
    assert read_schedules(catalogue, opener, flags=flags) == [] and flags == []


def test_a_title_blocks_sheet_number_cell_never_keeps_the_sheet_border_or_is_flagged(tmp_path):
    """The title block has a SHEET NUMBER label over the plumbing sheet's own number, P-101 (a pump's tag shape): the
    border is still dropped, and the sheet's own number is no unit a flag names."""
    texts = ((2310, 1380, "ACME ENGINEERS", 10), (2310, 1450, "SHEET NUMBER", 10), (2310, 1600, "P-101", 10),
             (100, 100, "GENERAL NOTES: ALL PIPING SHALL BE SUPPORTED FROM THE STRUCTURE ABOVE.", 10))
    catalogue, opener = catalogue_for(tmp_path, (_BORDER, texts), sheet="P-101", title="PLUMBING SCHEDULES",
                                      discipline="Plumbing")
    flags: list[str] = []
    assert read_schedules(catalogue, opener, flags=flags) == [] and flags == []
