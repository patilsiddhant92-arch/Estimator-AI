"""Where the sequence of operation and points list sit (Task 5, build step 4).

Built straight from SpecSection / Sheet / PageRecord objects — no PDFs needed, per the
plan's Global Constraints. A tiny stand-in plays the part of a Catalogue: find_backbone
only reads .sections, .sheets and .pages off it.
"""
from dataclasses import dataclass

from estimator.catalogue.register import PageRecord
from estimator.catalogue.sheet_types import Sheet
from estimator.catalogue.spec_sections import SpecSection
from estimator.reading.sequences import POINTS, SEQUENCE, Backbone, find_backbone

FILLER = "GENERAL NOTES: ALL DUCTWORK SHALL BE SUPPORTED FROM THE STRUCTURE ABOVE. " * 20


@dataclass
class FakeCatalogue:
    sections: tuple = ()
    sheets: tuple = ()
    pages: tuple = ()


def page(document: str, number: int, text: str) -> PageRecord:
    return PageRecord(document=document, page=number, status="text", text=text, rotation=0)


def sheet(document: str, number_: int, sheet_number: str | None, title: str | None) -> Sheet:
    return Sheet(document=document, page=number_, number=sheet_number, title=title,
                 discipline="Controls", types=("Control diagrams",))


def test_a_2309_93_spec_section_is_the_sequence():
    section = SpecSection(number="23 09 93", title="SEQUENCE OF OPERATIONS",
                           document="Specs.pdf", first_page=40, last_page=75)
    catalogue = FakeCatalogue(sections=(section,), pages=(page("Specs.pdf", 40, FILLER),))
    found, flags = find_backbone(catalogue)
    assert found == [Backbone(SEQUENCE, "23 09 93 SEQUENCE OF OPERATIONS (Specs.pdf, pages 40–75)",
                               "Specs.pdf", 40, 75, "spec section", None)]
    assert flags == ["No points list found — the sequence is not cross-checked"]


def test_a_drawing_sheet_can_be_both_kinds():
    combined = sheet("Marked_IC.pdf", 173, "M-805", "BMS DOAS POINTS LIST AND SEQUENCE OF OPERATIONS")
    catalogue = FakeCatalogue(sheets=(combined,), pages=(page("Marked_IC.pdf", 173, FILLER),))
    found, flags = find_backbone(catalogue)
    assert len(found) == 2
    by_what = {b.what: b for b in found}
    assert set(by_what) == {SEQUENCE, POINTS}
    for backbone in found:
        assert backbone.kind == "drawing sheet"
        assert backbone.where == "M-805 BMS DOAS POINTS LIST AND SEQUENCE OF OPERATIONS (Marked_IC.pdf, page 173)"
        assert backbone.document == "Marked_IC.pdf"
        assert backbone.first_page == backbone.last_page == 173
        assert backbone.duplicate_of is None
    assert flags == []


def test_a_run_of_sheets_is_one_backbone_item():
    run = [sheet("IC.pdf", n, f"IC04-{n - 9:02d}", "POINTS LIST") for n in (10, 11, 12, 13)]
    catalogue = FakeCatalogue(sheets=tuple(run), pages=tuple(page("IC.pdf", n, FILLER) for n in (10, 11, 12, 13)))
    found, flags = find_backbone(catalogue)
    assert len(found) == 1
    [backbone] = found
    assert backbone.what == POINTS
    assert backbone.first_page == 10 and backbone.last_page == 13
    assert backbone.where == "IC04-01 to IC04-04 POINTS LIST (IC.pdf, pages 10–13)"
    assert flags == ["No sequence of operation found — step 5 has no backbone for this job; scope comes from the drawings"]


def test_a_repeated_spec_section_across_two_documents_is_a_duplicate():
    text = ("SEQUENCE OF OPERATIONS\nA. THE AHU SHALL START AND STOP ON A TIME SCHEDULE.\n" + FILLER)
    first = SpecSection(number="23 09 93", title="SEQUENCE OF OPERATIONS",
                         document="Specs.pdf", first_page=100, last_page=110)
    second = SpecSection(number="23 09 93", title="SEQUENCE OF OPERATIONS",
                          document="FullSet.pdf", first_page=500, last_page=510)
    catalogue = FakeCatalogue(sections=(first, second),
                              pages=(page("Specs.pdf", 100, text), page("FullSet.pdf", 500, text)))
    found, flags = find_backbone(catalogue)
    assert len(found) == 2
    assert found[0].duplicate_of is None
    assert found[1].duplicate_of == found[0].where
    assert flags == ["No points list found — the sequence is not cross-checked"]


def test_two_unrelated_sections_with_the_same_number_are_not_marked_duplicate():
    first = SpecSection(number="23 09 93", title="SEQUENCE OF OPERATIONS",
                         document="Specs.pdf", first_page=100, last_page=110)
    second = SpecSection(number="23 09 93", title="SEQUENCE OF OPERATIONS",
                          document="Addendum1.pdf", first_page=1, last_page=5)
    catalogue = FakeCatalogue(sections=(first, second),
                              pages=(page("Specs.pdf", 100, "A. THE AHU RUNS 24/7 ON A FIXED SCHEDULE. " + FILLER),
                                     page("Addendum1.pdf", 1, "B. THE VAV BOXES MODULATE TO SETPOINT. " + FILLER)))
    found, flags = find_backbone(catalogue)
    assert [b.duplicate_of for b in found] == [None, None]


def test_a_controls_section_not_titled_a_sequence_still_counts_by_its_heading():
    # "instrumentation and control" makes this a controls section (spec_sections.is_controls_section)
    # without the word "sequence" in its title, so it only counts because of the in-page heading.
    section = SpecSection(number="23 05 00", title="INSTRUMENTATION AND CONTROL FOR HVAC",
                           document="Specs.pdf", first_page=1, last_page=3)
    text = "SEQUENCE OF OPERATION\n" + FILLER
    catalogue = FakeCatalogue(sections=(section,), pages=(page("Specs.pdf", 2, text),))
    found, flags = find_backbone(catalogue)
    assert len(found) == 1
    [backbone] = found
    assert backbone.what == SEQUENCE
    assert backbone.where.startswith("sequence inside 23 05 00 INSTRUMENTATION AND CONTROL FOR HVAC")


def test_a_job_with_none_is_flagged_and_finds_nothing():
    catalogue = FakeCatalogue()
    found, flags = find_backbone(catalogue)
    assert found == []
    assert flags == ["No sequence of operation found — step 5 has no backbone for this job; scope comes from the drawings"]


def test_sequence_and_points_together_raise_no_flag():
    seq = SpecSection(number="23 09 93", title="SEQUENCE OF OPERATIONS",
                       document="Specs.pdf", first_page=1, last_page=2)
    pts = SpecSection(number="25 60 00", title="POINTS SCHEDULE",
                       document="Specs.pdf", first_page=3, last_page=4)
    catalogue = FakeCatalogue(sections=(seq, pts), pages=(page("Specs.pdf", 1, FILLER), page("Specs.pdf", 3, FILLER)))
    found, flags = find_backbone(catalogue)
    assert {b.what for b in found} == {SEQUENCE, POINTS}
    assert flags == []


POINTS_HEADER = ("QTS CAMPUS\n26061 Issue for Construction\nV1.0\n05.29.26\n\"X\"\nfor Macro\nSorting\n"
                 "Point List Group ID\nfor Macro Sorting\nPOINT DESCRIPTION\nX\nCDU\nFacility Water Flowrate\nAI\n")


def test_points_list_pages_between_sections_with_no_heading_are_found():
    """A points list exported from a spreadsheet and bound into the spec book between two sections
    carries no SECTION heading and no page footer. Its column headings name it; the pages after it,
    up to the next section or a blank page, carry on the same list."""
    before = SpecSection("25 08 00", "INTEGRATED AUTOMATION COMMISSIONING", "Specs.pdf", 1, 2)
    after = SpecSection("26 05 00", "COMMON WORK RESULTS FOR ELECTRICAL", "Specs.pdf", 7, 8)
    pages = (page("Specs.pdf", 1, FILLER), page("Specs.pdf", 2, FILLER),
             PageRecord("Specs.pdf", 3, "blank", "This page intentionally left blank.", 0),
             page("Specs.pdf", 4, POINTS_HEADER), page("Specs.pdf", 5, "X\nUPS\nInput Real Power A\nkW\n15 min\n"),
             page("Specs.pdf", 6, "X\nUPS\nOutput Real Power A\nkW\n15 min\n"),
             page("Specs.pdf", 7, FILLER), page("Specs.pdf", 8, FILLER))
    catalogue = FakeCatalogue(sections=(before, after), pages=pages)
    found, _ = find_backbone(catalogue)
    assert found == [Backbone(POINTS, "Points list pages with no section heading (Specs.pdf, pages 4–6)",
                              "Specs.pdf", 4, 6, "spec pages", None)]


def test_a_contents_page_naming_the_points_list_section_is_not_the_list():
    before = SpecSection("25 08 00", "INTEGRATED AUTOMATION COMMISSIONING", "Specs.pdf", 2, 2)
    contents = "TABLE OF CONTENTS\nDIVISION 25\n25 08 00 COMMISSIONING\n25 60 10 MECHANICAL EQUIPMENT POINTS LIST\n"
    catalogue = FakeCatalogue(sections=(before,), pages=(page("Specs.pdf", 1, contents), page("Specs.pdf", 2, FILLER)))
    found, _ = find_backbone(catalogue)
    assert [b.what for b in found] == []
