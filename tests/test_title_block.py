import pytest

from estimator.catalogue.documents import find_documents
from estimator.catalogue.pdf import Span
from estimator.catalogue.register import read_document
from estimator.catalogue.title_block import SHEET_NUMBER, TitleBlock, read_title_block
from pdfs import FILLER, Page, make_pdf


@pytest.mark.parametrize("text", ["M001.00", "M-101", "M1.01", "M00-03", "TC00-00", "H-301", "M-111",
                                  "FP-101A", "MSK-001", "E-1.01", "M001.3", "M 101"])
def test_sheet_number_shapes(text):
    assert SHEET_NUMBER.fullmatch(text)


@pytest.mark.parametrize("text", ["275 HARTZ WAY", "2026", "PROJECT", "A", "SCALE: 1/8\"=1'-0\"", "15970",
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
    spans = [_span("TISHMAN SPEYER", 18.8, 0.874, 0.788), _span("DRAWING", 9.4, 0.832, 0.842),
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
    spans = [_span("CONTROLS AND DESIGN", 13.1, 0.913, 0.853), _span("275 HARTZ WAY", 13.1, 0.922, 0.860),
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
    spans = [_span("275 HARTZ WAY", 15.7, 0.90, 0.90), _span("REVISIONS", 10, 0.90, 0.80)]
    assert read_title_block(spans) == TitleBlock(None, None)


def test_small_text_shaped_like_a_number_is_not_the_sheet_number():
    assert read_title_block([_span("M-101", 8, 0.95, 0.95)]).number is None


def test_a_rotated_sheet_read_from_the_pdf(tmp_path):
    # Stored portrait and turned 90°, like most of 26-0246's mechanical sheets.
    sheet = Page(width=2160, height=3024, rotation=90,
                 texts=((200, 1500, FILLER, 10), (1650, 250, "HVAC GENERAL NOTES", 20), (1900, 150, "M001.00", 40)))
    make_pdf(tmp_path / "26-9999" / "2. Takeoffs" / "1. Base Takeoff" / "mech.pdf", sheet)
    [record] = read_document(find_documents(tmp_path / "26-9999").documents[0])
    assert read_title_block(record.edge_spans) == TitleBlock("M001.00", "HVAC GENERAL NOTES")
