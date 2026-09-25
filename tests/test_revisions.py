from datetime import date
from pathlib import Path

import pytest

from estimator.catalogue.documents import Document, JobFolder
from estimator.catalogue.job import Catalogue
from estimator.catalogue.pdf import Span
from estimator.catalogue.qualify import BidCheck
from estimator.catalogue.register import PageRecord
from estimator.catalogue.sheet_types import Sheet
from estimator.reading.revisions import (Issue, Revisions, parse_date, read_revision_table, sheet_versions,
                                         supersede)

BASE = "2. Takeoffs/1. Base Takeoff/Mech.pdf"
ADDENDUM = "2. Takeoffs/2. Addendum 1/Addendum 1.pdf"
OTHER = "2. Takeoffs/1. Base Takeoff/Mech reissue.pdf"


def _row(y: float, *cells: tuple[float, str], size: float = 9.4) -> list[Span]:
    return [Span(text, size, x, y, x + 0.03, y + 0.005) for x, text in cells]


def _table(*rows: tuple[str, str, str]) -> tuple[Span, ...]:
    """A title-block revision table: number, description and date columns, newest row on top, headings below."""
    spans: list[Span] = []
    for i, (number, description, when) in enumerate(rows):
        spans += _row(0.70 + i * 0.01, (0.83, number), (0.87, description), (0.92, when))
    spans += _row(0.70 + len(rows) * 0.01, (0.83, "NO."), (0.87, "DESCRIPTION"), (0.92, "DATE"))
    return tuple(spans)


FOUR_ROWS = _table(("4", "ADDENDUM #1", "02 26 25"), ("3", "ISSUED FOR BID", "02/12/25"),
                   ("2", "ISSUED FOR PRICING", "01-30-2025"), ("1", "ISSUED FOR PERMIT", "JAN 15, 2025"))


def _catalogue(*pages: tuple[str, int, str, str, tuple[Span, ...]], kinds: dict[str, str] | None = None) -> Catalogue:
    """pages: (document, page, sheet number, text, title-block spans)."""
    kinds = kinds or {}
    relatives = list(dict.fromkeys(p[0] for p in pages))
    documents = tuple(Document(Path(r), r, kinds.get(r, "drawings"), "base", 1) for r in relatives)
    job = JobFolder("26-9999", Path("26-9999"), documents, ())
    records = tuple(PageRecord(doc, page, "text", text, 0, True, spans) for doc, page, _, text, spans in pages)
    sheets = tuple(Sheet(doc, page, number, "MECHANICAL PLAN", "Mechanical", ("Plans",)) for doc, page, number, _, _ in pages)
    bid = BidCheck("Not stated", "", (), (), ())
    return Catalogue(job, records, sheets, (), bid, (), ())


@pytest.mark.parametrize("text, expected", [
    ("02 26 25", date(2025, 2, 26)), ("02/26/25", date(2025, 2, 26)), ("02-26-2025", date(2025, 2, 26)),
    ("2/26/2025", date(2025, 2, 26)), ("FEB 26, 2025", date(2025, 2, 26)), ("2025-02-26", date(2025, 2, 26)),
    ("06.04.26", date(2026, 6, 4)), ("5.22.2026", date(2026, 5, 22)), ("30jan26", date(2026, 1, 30)),
    ("ISSUED FOR BID", None), ("13/45/25", None),
])
def test_date_forms(text, expected):
    assert parse_date(text, Revisions.load()) == expected


def test_a_four_row_revision_table_is_read_oldest_first():
    issues = read_revision_table(FOUR_ROWS, Revisions.load())
    assert [i.number for i in issues] == ["1", "2", "3", "4"]
    assert issues[-1] == Issue("4", "ADDENDUM #1", date(2025, 2, 26))
    assert issues[0] == Issue("1", "ISSUED FOR PERMIT", date(2025, 1, 15))


def test_a_row_carried_in_one_run_of_text_is_read_too():
    spans = (Span("4  ADDENDUM #1  02 26 25", 9.4, 0.83, 0.70, 0.95, 0.705),
             Span("3  ISSUED FOR BID  02 12 25", 9.4, 0.83, 0.71, 0.95, 0.715))
    assert read_revision_table(spans, Revisions.load()) == (Issue("3", "ISSUED FOR BID", date(2025, 2, 12)),
                                                            Issue("4", "ADDENDUM #1", date(2025, 2, 26)))


def test_a_plot_stamp_in_a_bigger_font_does_not_beat_the_rows_own_date():
    spans = tuple(_row(0.70, (0.83, "2"), (0.87, "ISSUED FOR BID"), (0.85, "06.04.26"))
                  + [Span("06.08.26", 10.0, 0.85, 0.6996, 0.88, 0.7046)])
    assert read_revision_table(spans, Revisions.load()) == (Issue("2", "ISSUED FOR BID", date(2026, 6, 4)),)


def test_headings_and_labels_are_not_issues():
    spans = tuple(_row(0.70, (0.83, "Date of issue:"), (0.90, "05/22/2026")) + _row(0.72, (0.83, "ISSUE/REVISION")))
    assert read_revision_table(spans, Revisions.load()) == ()


def test_sheet_versions_read_the_title_block():
    catalogue = _catalogue((BASE, 1, "M-201", "PLAN", FOUR_ROWS))
    [version] = sheet_versions(catalogue)
    assert (version.sheet, version.document, version.page) == ("M-201", BASE, 1)
    assert version.latest == date(2025, 2, 26)
    assert version.source == "title block"
    assert len(version.issues) == 4


def test_the_later_date_governs():
    early = _table(("3", "ISSUED FOR BID", "02/12/25"))
    late = _table(("4", "ADDENDUM #1", "02/26/25"), ("3", "ISSUED FOR BID", "02/12/25"))
    catalogue = _catalogue((OTHER, 1, "M-201", "PLAN", late), (BASE, 1, "M-201", "PLAN", early))
    supersessions, flags = supersede(catalogue, sheet_versions(catalogue))
    assert flags == []
    [s] = supersessions
    assert s.sheet == "M-201"
    assert s.current.document == OTHER
    assert [v.document for v in s.replaced] == [BASE]
    assert s.note.startswith("M-201: ADDENDUM #1 (02/26/25) replaces ISSUED FOR BID (02/12/25)")


def test_with_no_dates_the_addendum_governs():
    catalogue = _catalogue((BASE, 1, "M-201", "OLD PLAN TEXT HERE", ()), (ADDENDUM, 1, "M-201", "NEW PLAN TEXT HERE", ()),
                           kinds={ADDENDUM: "addendum"})
    versions = sheet_versions(catalogue)
    assert {v.document: v.source for v in versions} == {BASE: "unknown", ADDENDUM: "document is an addendum"}
    [s], flags = supersede(catalogue, versions)
    assert flags == []
    assert s.current.document == ADDENDUM
    assert s.note.startswith("M-201: Addendum 1.pdf replaces Mech.pdf")


def test_with_no_dates_and_two_base_documents_it_asks():
    catalogue = _catalogue((BASE, 1, "M-201", "OLD PLAN TEXT HERE", ()), (OTHER, 1, "M-201", "NEW PLAN TEXT HERE", ()))
    supersessions, flags = supersede(catalogue, sheet_versions(catalogue))
    assert supersessions == []
    assert flags == ["Sheet M-201 is in two documents with no dates to order them — check which governs"]


def test_pages_repeated_in_one_document_are_not_versions():
    catalogue = _catalogue((BASE, 1, "M-110", "TYPICAL FLOOR 10", ()), (BASE, 2, "M-110", "TYPICAL FLOOR 11", ()))
    assert supersede(catalogue, sheet_versions(catalogue)) == ([], [])


def test_the_same_issue_twice_is_not_a_version():
    table = _table(("3", "ISSUED FOR BID", "02/12/25"))
    marked = "2. Takeoffs/1. Base Takeoff/Marked_Mech.pdf"
    catalogue = _catalogue((BASE, 1, "M-201", "PLAN", table), (marked, 1, "M-201", "PLAN", table))
    assert supersede(catalogue, sheet_versions(catalogue)) == ([], [])


def test_the_change_log():
    old_table = _table(("3", "ISSUED FOR BID", "02/12/25"))
    new_table = _table(("4", "ADDENDUM #1", "02/26/25"), ("3", "ISSUED FOR BID", "02/12/25"))
    old_text = "\n".join(["VAV-1 SERVES OFFICE 101", "COORDINATE DUCT ROUTING WITH ARCHITECT.", "SCALE: NTS",
                          "3 ISSUED FOR BID 02/12/25"])
    new_text = "\n".join(["VAV-1   SERVES OFFICE 101", "VAV-2", "PROVIDE SPACE TEMPERATURE SENSOR BY CONTROLS CONTRACTOR.",
                          "SCALE: NTS", "4 ADDENDUM #1 02/26/25", "3 ISSUED FOR BID 02/12/25"])
    catalogue = _catalogue((BASE, 1, "M-201", old_text, old_table), (ADDENDUM, 1, "M-201", new_text, new_table),
                           kinds={ADDENDUM: "addendum"})
    [s], _ = supersede(catalogue, sheet_versions(catalogue))
    changes = {(c.what, c.old, c.new): c.affects_controls for c in s.changes}
    assert changes == {
        ("tag added", "", "VAV-2"): True,
        ("note added", "", "PROVIDE SPACE TEMPERATURE SENSOR BY CONTROLS CONTRACTOR."): True,
        ("note removed", "COORDINATE DUCT ROUTING WITH ARCHITECT.", ""): False,
    }
    assert all(c.sheet == "M-201" for c in s.changes)
    assert s.note == "M-201: ADDENDUM #1 (02/26/25) replaces ISSUED FOR BID (02/12/25) — 3 changes, 2 affect controls"


def test_a_changed_schedule_row_is_logged_as_one_change():
    old = "VAV-1 400 CFM 8 INCH INLET\nVAV-2 600 CFM 10 INCH INLET"
    new = "VAV-1 450 CFM 8 INCH INLET\nVAV-2 600 CFM 10 INCH INLET"
    catalogue = _catalogue((BASE, 1, "M-601", old, ()), (ADDENDUM, 1, "M-601", new, ()), kinds={ADDENDUM: "addendum"})
    catalogue = Catalogue(catalogue.job, catalogue.pages,
                          tuple(Sheet(s.document, s.page, s.number, "SCHEDULES", "Mechanical", ("Schedules",))
                                for s in catalogue.sheets),
                          (), catalogue.bid, (), ())
    [s], _ = supersede(catalogue, sheet_versions(catalogue))
    assert [(c.what, c.old, c.new) for c in s.changes] == [
        ("schedule row changed", "VAV-1 400 CFM 8 INCH INLET", "VAV-1 450 CFM 8 INCH INLET")]


def test_a_tag_added_or_removed_always_affects_controls():
    """Every unit needs controls, so a unit that comes or goes changes the controls scope."""
    old_table = _table(("3", "ISSUED FOR BID", "02/12/25"))
    new_table = _table(("4", "ADDENDUM #1", "02/26/25"), ("3", "ISSUED FOR BID", "02/12/25"))
    catalogue = _catalogue((BASE, 1, "M-201", "EF-1 ON ROOF", old_table), (ADDENDUM, 1, "M-201", "P-2 IN BASEMENT", new_table),
                           kinds={ADDENDUM: "addendum"})
    [s], _ = supersede(catalogue, sheet_versions(catalogue))
    tags = {(c.what, c.old or c.new): c.affects_controls for c in s.changes if c.what.startswith("tag")}
    assert tags == {("tag added", "P-2"): True, ("tag removed", "EF-1"): True}


def test_a_marked_up_copy_of_the_set_is_not_a_competing_version():
    """A document that repeats most of another's sheets is a marked-up copy: its sheets at the same
    date aren't a question of which governs, even though the markup changes their text."""
    table = _table(("3", "ISSUED FOR BID", "02/12/25"))
    marked = "2. Takeoffs/1. Base Takeoff/Marked_Mech.pdf"
    pages = []
    for page, number in enumerate(("M-201", "M-202", "M-203"), start=1):
        pages.append((BASE, page, number, f"PLAN {number}", table))
        pages.append((marked, page, number, f"PLAN {number}\nCHECK THIS DAMPER - ESTIMATOR", table))
    catalogue = _catalogue(*pages)
    assert supersede(catalogue, sheet_versions(catalogue)) == ([], [])


def test_two_different_sets_at_the_same_date_still_ask():
    table = _table(("3", "ISSUED FOR BID", "02/12/25"))
    catalogue = _catalogue((BASE, 1, "M-201", "OLD PLAN TEXT HERE", table), (OTHER, 1, "M-201", "NEW PLAN TEXT HERE", table),
                           (OTHER, 2, "M-301", "ANOTHER SHEET", table), (OTHER, 3, "M-302", "AND ANOTHER", table))
    _, flags = supersede(catalogue, sheet_versions(catalogue))
    assert flags == ["Sheet M-201 is in two documents with the same date (02/12/25) — check which governs"]
