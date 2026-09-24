import openpyxl
import pytest

from estimator.__main__ import main
from estimator.catalogue.job import catalogue_job, summary_lines
from pdfs import FILLER, Page, make_pdf

SCHEDULE = Page(width=3024, height=2160, texts=((200, 300, FILLER, 12), (300, 400, "AIR HANDLING UNIT SCHEDULE", 18),
                                                (300, 450, "AHU-1  AHU-2", 12), (2640, 1860, "HVAC SCHEDULES", 20),
                                                (2800, 2000, "M-601", 40)))
PLAN = Page(width=3024, height=2160, texts=((200, 300, FILLER, 12), (900, 900, "AHU-1 ON ROOF", 12),
                                            (2640, 1860, "ROOF PLAN", 20), (2800, 2000, "M-101", 40)))
NO_NUMBER = Page(width=3024, height=2160, texts=((200, 300, FILLER, 12),))
SPEC = Page(texts=((72, 72, "SECTION 23 09 23 - INSTRUMENTATION AND CONTROL FOR HVAC\n"
                            "2.1 SYSTEM\nA. The BMS shall be built on the Tridium Niagara 4 Framework.\n23 09 23 - 1", 10),))


@pytest.fixture
def job(tmp_path):
    root = tmp_path / "26-9999, 1 Test Street"
    base = root / "2. Takeoffs" / "1. Base Takeoff"
    make_pdf(base / "Mech.pdf", SCHEDULE, PLAN, NO_NUMBER)
    make_pdf(base / "Marked_230923.pdf", SPEC)
    (base / "broken.pdf").write_bytes(b"not a pdf")
    return root


def test_every_stage_runs(job, tmp_path):
    result = catalogue_job(job, tmp_path / "cache")
    assert result.job.name == "26-9999"
    assert [p.status for p in result.pages] == ["text", "text", "text", "text"]
    assert [(s.number, s.title) for s in result.sheets] == [("M-601", "HVAC SCHEDULES"), ("M-101", "ROOF PLAN"), (None, None)]
    assert "Schedules" in result.sheets[0].types and "Plans" in result.sheets[1].types
    assert [(s.number, s.controls) for s in result.sections] == [("23 09 23", True)]
    assert result.bid.finding == "Qualifies"
    [ahu1, ahu2] = result.tags
    assert (ahu1.tag, ahu1.on_schedules, ahu1.elsewhere) == ("AHU-1", ("M-601",), ("M-101",))
    assert ahu2.tag == "AHU-2"


def test_the_flags(job, tmp_path):
    flags = catalogue_job(job, tmp_path / "cache").flags
    assert any("broken.pdf could not be opened" in f for f in flags)
    assert any("Mech.pdf: no sheet number found on 1 of 3 sheets (page 3)" in f for f in flags)


def test_the_summary_is_in_plain_words(job, tmp_path):
    lines = summary_lines(catalogue_job(job, tmp_path / "cache"))
    assert lines[0] == "26-9999 — 3 documents, 4 pages: 0 read by OCR, 0 blank, 0 could not be read."
    assert lines[1].startswith("Bid check: Qualifies — The spec names Niagara N4")


def test_the_command_writes_the_evidence_package(job, tmp_path, capsys):
    out = tmp_path / "out"
    assert main(["catalogue", str(job), "--out", str(out), "--workers", "1"]) == 0
    package = out / "26-9999 Evidence Package.xlsx"
    assert openpyxl.load_workbook(package).sheetnames[0] == "Bid check"
    printed = capsys.readouterr().out
    assert "Bid check: Qualifies" in printed and f"Wrote {package}" in printed


def test_a_missing_job_folder_is_plain(tmp_path, capsys):
    assert main(["catalogue", str(tmp_path / "nowhere"), "--out", str(tmp_path / "out")]) == 1
    assert capsys.readouterr().err.strip() == f"Stopped: can't find {tmp_path / 'nowhere'}"


def test_an_addendum_of_drawing_sheets_still_gets_a_sheet_number(tmp_path):
    # I5: a reissued sheet in "Addendum 1.pdf" is a large page, whatever the document's kind.
    root = tmp_path / "26-9999"
    base = root / "2. Takeoffs" / "1. Base Takeoff"
    reissue = Page(width=3024, height=2160, texts=((200, 300, FILLER, 12), (2640, 1860, "REVISED ROOF PLAN", 20),
                                                   (2800, 2000, "M-101", 40)))
    make_pdf(base / "Addendum 1.pdf", reissue)
    result = catalogue_job(root, tmp_path / "cache")
    [sheet] = result.sheets
    assert sheet.number == "M-101" and sheet.document.endswith("Addendum 1.pdf")


def test_a_blank_drawing_sheet_is_flagged(tmp_path):
    root = tmp_path / "26-9999"
    base = root / "2. Takeoffs" / "1. Base Takeoff"
    make_pdf(base / "Mech.pdf", Page(width=3024, height=2160))
    result = catalogue_job(root, tmp_path / "cache")
    assert any("Mech.pdf" in f and "blank drawing page" in f for f in result.flags)
