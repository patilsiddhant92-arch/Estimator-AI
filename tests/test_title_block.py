import pytest

from estimator.catalogue.documents import find_documents
from estimator.catalogue.pdf import Span
from estimator.catalogue.register import read_document
from estimator.catalogue.title_block import SHEET_NUMBER, TitleBlock, read_title_block
from pdfs import FILLER, Page, make_pdf


@pytest.mark.parametrize("text", ["M001.00", "M-101", "M1.01", "M00-03", "TC00-00", "H-301", "M-111",
                                  "FP-101A", "MSK-001", "E-1.01", "M001.3", "M 101", "P01-00A1.1",
                                  "H3T-M-611", "H5-P-501", "HEL03-M-101", "H3-C-876"])
def test_sheet_number_shapes(text):
    assert SHEET_NUMBER.fullmatch(text)


@pytest.mark.parametrize("text", ["1 INVENTED WAY", "2026", "PROJECT", "A", "SCALE: 1/8\"=1'-0\"", "15970",
                                  "ISSUED FOR CONSTRUCTION", "03/31/2026"])
def test_not_sheet_numbers(text):
    assert not SHEET_NUMBER.fullmatch(text)


def _span(text, size, x, y, w=0.05, h=0.012):
    return Span(text, size, x, y, x + w, y + h)


def test_a_title_block_with_the_title_above_the_number():
    spans = [_span("HVAC SCHEDULES SHEET 3", 20.4, 0.91, 0.851, w=0.07),
             _span("M006.00", 41, 0.935, 0.92, h=0.02),
             _span("PROJECT NO.", 8, 0.90, 0.96), _span("139717", 9, 0.95, 0.96),
             _span("SCA", 30, 0.90, 0.02)]
    assert read_title_block(spans) == TitleBlock("M006.00", "HVAC SCHEDULES SHEET 3")


def test_a_title_over_several_lines():
    lines = ["LEVEL 02 -", "OVERALL PLAN -", "MASTER", "MECHANICAL", "EQUIPMENT"]
    spans = [_span(t, 24.9, 0.935, 0.84 + i * 0.022) for i, t in enumerate(lines)]
    spans.append(_span("M00-03", 45.1, 0.933, 0.973, h=0.02))
    assert read_title_block(spans) == TitleBlock("M00-03", "LEVEL 02 - OVERALL PLAN - MASTER MECHANICAL EQUIPMENT")


def test_the_largest_number_wins_over_a_cross_reference():
    spans = [_span("SEE M-101", 10, 0.90, 0.90), _span("M-101", 10, 0.90, 0.91),
             _span("MECHANICAL PLAN", 22, 0.94, 0.88), _span("M-111", 50, 0.94, 0.94, h=0.02)]
    assert read_title_block(spans).number == "M-111"


def test_labels_dates_and_revisions_are_not_part_of_the_title():
    spans = [_span("SHEET TITLE:", 9.5, 0.89, 0.786), _span("FIRST FLOOR PLAN", 22, 0.90, 0.80, w=0.08),
             _span("DATE: 06/22/2026", 9, 0.90, 0.83), _span("SHEET NO.", 9, 0.89, 0.90),
             _span("M-101", 50, 0.94, 0.93, h=0.02)]
    assert read_title_block(spans) == TitleBlock("M-101", "FIRST FLOOR PLAN")


def test_the_title_under_its_label_not_the_permit_number_beside_it():
    # 26-0246's plumbing sheets: a larger DOB permit number sits between the title and the sheet number.
    spans = [_span("Project:", 8.6, 0.887, 0.788), _span("PS Q517 @ 1 BEACH 39TH", 20.4, 0.890, 0.793, w=0.08),
             _span("Drawing Title:", 8.6, 0.887, 0.846), _span("PLUMBING AND DRAINAGE", 20.4, 0.890, 0.851, w=0.09),
             _span("FIRST FLOOR PLAN", 20.4, 0.890, 0.862, w=0.06), _span("DOB NOW #:", 8.6, 0.887, 0.885),
             _span("Q01333361-S2", 29.4, 0.890, 0.897, w=0.05), _span("P101.00", 41.1, 0.942, 0.924, h=0.02)]
    assert read_title_block(spans) == TitleBlock("P101.00", "PLUMBING AND DRAINAGE FIRST FLOOR PLAN")


def test_a_label_split_over_two_lines():
    # 26-0352: "DRAWING" and "TITLE" are two small lines, the title beside them.
    spans = [_span("HARBOR POINT", 18.8, 0.874, 0.788), _span("DRAWING", 9.4, 0.832, 0.842),
             _span("TITLE", 9.4, 0.832, 0.849), _span("MECHANICAL 21ST FLOOR PLAN", 16.9, 0.857, 0.857, w=0.09),
             _span("SEAL & SIGNATURE", 9.4, 0.832, 0.886), _span("M-100.00", 25.1, 0.926, 0.930, h=0.014)]
    assert read_title_block(spans) == TitleBlock("M-100.00", "MECHANICAL 21ST FLOOR PLAN")


def test_a_title_as_large_as_the_sheet_number():
    # 26-0344: title and sheet number are both 19.4 pt, and a column of 9 pt notes sits alongside.
    spans = [_span("MECHANICAL", 19.4, 0.946, 0.857), _span("6TH FLOOR", 19.4, 0.947, 0.872),
             _span("PLAN", 19.4, 0.946, 0.886), _span("ALL DUCT SHALL FOLLOW SMACNA", 9.0, 0.859, 0.730),
             _span("Drawing No.", 9.7, 0.947, 0.926), _span("M-106.00", 19.4, 0.947, 0.945, h=0.014)]
    assert read_title_block(spans) == TitleBlock("M-106.00", "MECHANICAL 6TH FLOOR PLAN")


def test_an_address_just_smaller_than_the_title_is_left_out():
    # 26-0436's controls sheets: the firm's address is 13.1 pt, the title 15.6 pt.
    spans = [_span("CONTROLS AND DESIGN", 13.1, 0.913, 0.853), _span("1 INVENTED WAY", 13.1, 0.922, 0.860),
             _span("SECOND FLOOR RAS", 15.6, 0.914, 0.885), _span("INSTRUMENT LOCATION", 15.6, 0.910, 0.894),
             _span("IC015", 36.7, 0.922, 0.972, h=0.02)]
    assert read_title_block(spans) == TitleBlock("IC015", "SECOND FLOOR RAS INSTRUMENT LOCATION")


def test_a_file_path_on_the_sheet_edge_is_not_part_of_the_title():
    spans = [_span("TYPICAL DETAILS - 1", 20.4, 0.890, 0.862), _span("C:\\Revit\\EL139717_CENTRAL.rvt", 12.7, 0.994, 0.779),
             _span("E701.00", 41.1, 0.942, 0.924, h=0.02)]
    assert read_title_block(spans).title == "TYPICAL DETAILS - 1"


def test_stamps_and_disclaimers_are_not_titles():
    # Seen by the fact sheet on 26-0436/26-0437 sheets with no title label.
    disclaimer = "THIS DRAWING IS NOT TO BE USED AS BUILDING CONSTRUCTION DRAWING AND NO RESPONSIBILITY IS ACCEPTED FOR ITS USE"
    spans = [_span("NOT FOR CONSTRUCTION", 15.5, 0.908, 0.800), _span("INTERNAL FR - OFFICIAL USE /", 19.0, 0.896, 0.820),
             _span(disclaimer, 14, 0.90, 0.85, w=0.09), _span("M-121", 50.5, 0.940, 0.933, h=0.02)]
    assert read_title_block(spans) == TitleBlock("M-121", None)


def test_no_number_and_no_title():
    spans = [_span("1 INVENTED WAY", 15.7, 0.90, 0.90), _span("REVISIONS", 10, 0.90, 0.80)]
    assert read_title_block(spans) == TitleBlock(None, None)


def test_small_text_shaped_like_a_number_is_not_the_sheet_number():
    assert read_title_block([_span("M-101", 8, 0.95, 0.95)]).number is None


def test_a_keyplan_grid_label_loses_to_the_real_sheet_number():
    # 26-0445's plumbing sheets: a 40 pt keyplan grid cell "D1" outsizes the real 36 pt sheet number,
    # but "P01-00A1.1" carries two digits in a row and "D1" does not.
    spans = [_span("D1", 40, 0.30, 0.90), _span("PIPING PLAN - UNDERSLAB - SEGMENT A1.1", 20, 0.90, 0.85, w=0.09),
             _span("P01-00A1.1", 36, 0.94, 0.93, h=0.02)]
    assert read_title_block(spans).number == "P01-00A1.1"


def test_a_grid_line_label_loses_to_the_real_sheet_number():
    # 26-0445's mechanical sheets: a grid line "B.9" is picked up instead of the real sheet number.
    spans = [_span("B.9", 40, 0.30, 0.90), _span("M-302", 36, 0.94, 0.93, h=0.02)]
    assert read_title_block(spans).number == "M-302"


def test_a_sheet_whose_only_candidate_has_no_double_digit_still_reads_it():
    assert read_title_block([_span("M1", 50, 0.94, 0.93, h=0.02)]).number == "M1"


def test_a_rotated_sheet_read_from_the_pdf(tmp_path):
    # Stored portrait and turned 90°, like most of 26-0246's mechanical sheets.
    sheet = Page(width=2160, height=3024, rotation=90,
                 texts=((200, 1500, FILLER, 10), (1650, 250, "HVAC GENERAL NOTES", 20), (1900, 150, "M001.00", 40)))
    make_pdf(tmp_path / "26-9999" / "2. Takeoffs" / "1. Base Takeoff" / "mech.pdf", sheet)
    [record] = read_document(find_documents(tmp_path / "26-9999").documents[0])
    assert read_title_block(record.edge_spans) == TitleBlock("M001.00", "HVAC GENERAL NOTES")


# --- the drawing index, and the line beside the number, when the title block gives no title ----------

from estimator.catalogue.title_block import index_key, read_drawing_index   # noqa: E402

_INDEX_PAGE = """DRAWING INDEX
GENERAL
G001
TITLE SHEET
G002
GENERAL NOTES, ABBREVIATIONS, & LEGENDS
HVAC
H001
LEGEND, ABBREVIATIONS, GENERAL NOTES
H101
HVAC NEW WORK FLOOR PLAN
H601
HVAC SCHEDULES
E-201 ELECTRICAL NEW WORK
E-202 ELECTRICAL NEW WORK - ROOF POWER
"""


def test_the_drawing_index_pairs_each_number_with_its_title():
    index = read_drawing_index([_INDEX_PAGE])
    assert index[index_key("H601")] == "HVAC SCHEDULES"
    assert index[index_key("H101")] == "HVAC NEW WORK FLOOR PLAN"
    assert index[index_key("E201")] == "ELECTRICAL NEW WORK"            # "<number> <title>" on one line, too
    assert index[index_key("E-202")] == "ELECTRICAL NEW WORK - ROOF POWER"
    assert index_key("GENERAL") not in index


def test_a_page_with_a_few_number_lines_is_not_an_index():
    plan = "RTU-1\nGYMNASIUM\nRTU-2\nWEIGHT ROOM\nM-101\nSEE PLAN FOR CONTINUATION\n"
    assert read_drawing_index([plan]) == {}


def test_a_sheet_with_no_title_in_its_title_block_takes_the_index_title():
    spans = [_span("Drawing Name", 8.7, 0.913, 0.754), _span("HVAC SCHEDULES", 17.4, 0.915, 0.763),
             _span("Revisions", 8.7, 0.913, 0.867), _span("H601", 46, 0.923, 0.957, h=0.03)]
    block = read_title_block(spans, {index_key("H601"): "HVAC SCHEDULES"})
    assert (block.number, block.title, block.source) == ("H601", "HVAC SCHEDULES", "drawing index")


def test_with_no_index_the_capitalised_line_before_the_number_is_the_title():
    spans = [_span("AS NOTED", 17.4, 0.915, 0.736), _span("HVAC SCHEDULES", 17.4, 0.915, 0.763),
             _span("H601", 46, 0.923, 0.957, h=0.03), _span("Drawing Number:", 8.7, 0.913, 0.943)]
    block = read_title_block(spans)
    assert (block.number, block.title, block.source) == ("H601", "HVAC SCHEDULES", "beside the sheet number")


@pytest.mark.parametrize("before", ["Drawing Number:", "SCALE: AS NOTED", "08/27/2026", "Checked By",
                                    "A VERY LONG LINE OF CAPITALS THAT IS A NOTE AND NOT A TITLE AT ALL, SURELY"])
def test_a_label_or_a_long_line_before_the_number_is_not_a_title(before):
    spans = [_span(before, 9, 0.915, 0.94), _span("H601", 46, 0.923, 0.957, h=0.03)]
    assert read_title_block(spans) == TitleBlock("H601", None)


def test_a_title_block_title_is_marked_as_such():
    spans = [_span("HVAC SCHEDULES SHEET 3", 20.4, 0.91, 0.851, w=0.07), _span("M006.00", 41, 0.935, 0.92, h=0.02)]
    assert read_title_block(spans).source == "title block"


# --- prefixed sheet numbers, and the label-then-value layout (synthetic, ~11.5 pt throughout) ----------


def test_a_prefixed_number_in_the_size_based_layout():
    # No labels at all: the largest text above the number is still the title, and the prefixed
    # number still wins over the size threshold on its own (11.5 pt is below MIN_NUMBER_SIZE,
    # so this only works once the number is large enough — here it is, unlike the labelled case below).
    spans = [_span("CHILLED WATER PIPING FLOW DIAGRAM", 20.4, 0.90, 0.85, w=0.09),
             _span("H3T-M-611", 41, 0.935, 0.92, h=0.02)]
    block = read_title_block(spans)
    assert block.number == "H3T-M-611"
    assert block.title == "CHILLED WATER PIPING FLOW DIAGRAM"


def test_the_labelled_layout_reads_a_small_prefixed_number_and_title():
    # Synthetic version of the real shape: a small "SHEET NAME" label, 2-3 lines of ~11.5 pt title text,
    # then a small "SHEET NUMBER" label, then the ~11.5 pt prefixed number directly below it — all of it
    # below MIN_NUMBER_SIZE / MIN_TITLE_SIZE (12 pt), so only the labelled reading finds it.
    spans = [
        _span("SHEET NAME", 8, 0.90, 0.780),
        _span("MECHANICAL - TECHNOLOGY CHILLED WATER PIPING", 11.5, 0.90, 0.795, w=0.09),
        _span("FLOW DIAGRAM - ITE BLOCK - 3 CDU CONFIGURATION", 11.5, 0.90, 0.808, w=0.09),
        _span("SHEET NUMBER", 8, 0.90, 0.900),
        _span("H3T-M-611", 11.5, 0.90, 0.915),
    ]
    block = read_title_block(spans)
    assert block.number == "H3T-M-611"
    assert block.title == ("MECHANICAL - TECHNOLOGY CHILLED WATER PIPING "
                            "FLOW DIAGRAM - ITE BLOCK - 3 CDU CONFIGURATION")


def test_an_existing_unprefixed_number_still_reads_the_same():
    spans = [_span("HVAC SCHEDULES SHEET 3", 20.4, 0.91, 0.851, w=0.07), _span("M006.00", 41, 0.935, 0.92, h=0.02)]
    assert read_title_block(spans) == TitleBlock("M006.00", "HVAC SCHEDULES SHEET 3")


# --- RD-10: one sheet, however its number is spaced; never a revision mark ----------------------------

from estimator.catalogue.title_block import sheet_key   # noqa: E402


@pytest.mark.parametrize("text", ["M-101-A", "M2.1-B"])
def test_a_sheet_number_with_a_lettered_part_is_a_sheet_number(text):
    assert SHEET_NUMBER.fullmatch(text)


def test_a_lettered_sheet_number_is_read_whole_from_the_title_block():
    spans = [_span("HVAC LEVEL 1 PLAN", 20.4, 0.91, 0.851, w=0.07), _span("M-101-A", 41, 0.935, 0.92, h=0.02)]
    assert read_title_block(spans) == TitleBlock("M-101-A", "HVAC LEVEL 1 PLAN")


def test_a_revision_mark_is_never_the_sheet_number():
    assert read_title_block([_span("REV 2", 41, 0.935, 0.92, h=0.02)]) == TitleBlock(None, None)
    # a two-digit revision mark would beat a short real number on the two-digits rule
    spans = [_span("REV 12", 41, 0.935, 0.92, h=0.02), _span("M1", 30, 0.935, 0.96, h=0.02)]
    assert read_title_block(spans).number == "M1"
    labelled = [_span("SHEET NO", 8, 0.90, 0.900), _span("NO 3", 11.5, 0.90, 0.915), _span("M-101", 11.5, 0.90, 0.93)]
    assert read_title_block(labelled).number == "M-101"


def test_a_revision_mark_is_never_a_drawing_index_line():
    index = read_drawing_index(["DRAWING INDEX\nM-101 HVAC LEVEL 1 PLAN\nM-102 HVAC LEVEL 2 PLAN\n"
                                "M-103 HVAC LEVEL 3 PLAN\nM-601 HVAC SCHEDULES\nREV 2 HVAC REVISED PIPING\n"])
    assert index_key("M-101") in index and index_key("REV 2") not in index


@pytest.mark.parametrize("a, b", [("M-101", "M101"), ("M-101", "M 101"), ("m-101", "M101"), ("C-7.0", "C7.0"),
                                  ("M-101-A", "M101-A")])
def test_one_sheet_however_its_number_is_spaced(a, b):
    assert sheet_key(a) == sheet_key(b) == index_key(a)


@pytest.mark.parametrize("a, b", [("M-1.01", "M-101"), ("M1-01", "M-101"), ("M-101-A", "M-101")])
def test_another_sheet_keeps_its_own_key(a, b):
    assert sheet_key(a) != sheet_key(b)
