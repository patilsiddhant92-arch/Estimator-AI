import pytest

from estimator.catalogue.pdf import clean_text
from estimator.catalogue.register import PageRecord
from estimator.catalogue.spec_sections import SpecSection, index_sections, is_controls_section, section_number


def _pages(document, *texts):
    return [PageRecord(document, n, "text", text, 0) for n, text in enumerate(texts, start=1)]


@pytest.mark.parametrize("raw, number", [("230923", "23 09 23"), ("23 09 23", "23 09 23"), ("23 05 00.1", "23 05 00.1"),
                                         ("15970", "15970"), ("250000", "25 00 00")])
def test_section_numbers(raw, number):
    assert section_number(raw) == number


@pytest.mark.parametrize("number, title, controls", [
    ("23 09 23", "", True), ("25 00 00", "INTEGRATED AUTOMATION", True), ("15970", "", True),
    ("15985", "SEQUENCE OF OPERATION", True), ("23 39 00", "BUILDING MANAGEMENT SYSTEMS", True),
    ("23 05 00", "COMMON WORK RESULTS FOR HVAC", False), ("15400", "PLUMBING", False),
    ("23 73 13", "MODULAR INDOOR CENTRAL-STATION AIR-HANDLING UNITS", False)])
def test_which_sections_are_controls(number, title, controls):
    assert is_controls_section(number, title) is controls


def test_an_old_style_section_from_header_to_end():
    pages = _pages("specs.pdf",
                   "SECTION 15970\nTEMPERATURE CONTROL SYSTEM (BACNET BMS/DDC)\nPART 1 - GENERAL\n15970 - 1",
                   "1.2 SUMMARY\nA. Work includes the BMS.\n15970 - 2",
                   "END OF SECTION 15970\n15970 - 3",
                   "SECTION 15985\nSEQUENCE OF OPERATION\n15985 - 1")
    assert index_sections(pages) == [
        SpecSection("15970", "TEMPERATURE CONTROL SYSTEM (BACNET BMS/DDC)", "specs.pdf", 1, 3),
        SpecSection("15985", "SEQUENCE OF OPERATION", "specs.pdf", 4, 4)]


def test_a_title_on_the_header_line_and_footers_without_headers():
    pages = _pages("manual.pdf",
                   "SECTION 23 09 23 - INSTRUMENTATION AND CONTROL FOR HVAC\nPART 1\n23 09 23 - 1",
                   "text\n23 09 23 - 2",
                   "more text\n230500-1",
                   "still common work\n230500-2")
    sections = index_sections(pages)
    assert [(s.number, s.title, s.first_page, s.last_page) for s in sections] == [
        ("23 09 23", "INSTRUMENTATION AND CONTROL FOR HVAC", 1, 2), ("23 05 00", "", 3, 4)]
    assert [s.controls for s in sections] == [True, False]


def test_control_characters_used_as_spaces():
    pages = _pages("k9.pdf", clean_text("SECTION\x04230500\nCOMMON\x04WORK\x04RESULTS\n230500\x04-\x041"))
    assert index_sections(pages) == [SpecSection("23 05 00", "COMMON WORK RESULTS", "k9.pdf", 1, 1)]


def test_a_table_of_contents_opens_nothing():
    toc = "TABLE OF CONTENTS\nSECTION 23 05 00 COMMON WORK\nSECTION 23 09 23 CONTROLS\nSECTION 23 73 13 AHUS"
    pages = _pages("manual.pdf", toc, "SECTION 23 05 00 - COMMON WORK RESULTS FOR HVAC\n23 05 00 - 1")
    assert [(s.number, s.first_page) for s in index_sections(pages)] == [("23 05 00", 2)]


def test_a_cross_reference_opens_nothing():
    body = "\n".join(["PART 1 - GENERAL", "1.1 RELATED WORK", "A. Drawings apply.", "B. Coordinate with the work",
                      "of other sections.", "C. Cabling:", "D. Wiring:", "E. Refer to Division 16.",
                      "SECTION 16727 DATA CABLING SYSTEM", "F. Grounding."])
    pages = _pages("specs.pdf", "SECTION 15970\nTEMPERATURE CONTROL SYSTEM\n15970 - 1",
                   body + "\n15970 - 2",                                              # too far down the page
                   "SECTION 15985, “SEQUENCE OF OPERATION”.\nSection 15985 applies.\n15970 - 3")   # punctuation; lower case
    assert index_sections(pages) == [SpecSection("15970", "TEMPERATURE CONTROL SYSTEM", "specs.pdf", 1, 3)]


def test_a_running_header_at_the_top_of_every_page():
    # 26-0356: the capitalised heading is the ninth line, below the running header.
    top = "Example Houses\nCommunity Center Upgrades\nRFQ No. 000000\nBid Documents\n09/10/2025\n"
    pages = _pages("rfq.pdf",
                   top + "Page 1 of 42\nSection 23 09 00\nInstrumentation and Controls for HVAC\n"
                         "SECTION 23 09 00\nINSTRUMENTATION AND CONTROLS FOR HVAC\nPART 1",
                   top + "Page 2 of 42\nSection 23 09 00\nInstrumentation and Controls for HVAC\n"
                         "controllers furnished in this section shall communicate over BACnet IP.")
    assert index_sections(pages) == [SpecSection("23 09 00", "Instrumentation and Controls for HVAC", "rfq.pdf", 1, 2)]


def test_number_page_and_title_on_one_line():
    # 26-0344: "230900-4" and the title share the page's first lines.
    pages = _pages("hvac.pdf",
                   "1 Invented Street Conversion\nExample Associates, Inc.\n230900-4        Instrumentation and Control of HVAC\n"
                   "50% CD\nF. Samples for Verification",
                   "1 Invented Street Conversion\nExample Associates, Inc.\n230900-5        Instrumentation and Control of HVAC\n"
                   "2.2 CONTROL SYSTEM")
    assert index_sections(pages) == [SpecSection("23 09 00", "Instrumentation and Control of HVAC", "hvac.pdf", 1, 2)]


def test_sections_do_not_run_across_documents():
    pages = _pages("a.pdf", "SECTION 230923\nCONTROLS\n230923 - 1") + _pages("b.pdf", "no header here")
    assert index_sections(pages) == [SpecSection("23 09 23", "CONTROLS", "a.pdf", 1, 1)]
