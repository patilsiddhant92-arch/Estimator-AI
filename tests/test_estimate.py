"""The estimate command: from a job folder to the proposal, the price sheet and the Evidence Package."""
import re

import openpyxl
import pytest
from docx import Document

from estimator.__main__ import main
from estimator.evidence.workbook import ESTIMATE_TABS, TABS
from estimator.proposal.sections import scope_texts
from pdfs import FILLER, Page, make_pdf
from test_schedules import grid

W, H = 3024, 2160
VAV_ROWS = [["VAV BOX SCHEDULE", "", "", "", ""],
            ["TAG", "SERVES", "MAX CFM", "HW GPM", "MANUFACTURER"],
            ["VAV-1", "OFFICE 101", "600", "1.5", "TITUS"],
            ["VAV-2", "OFFICE 102", "700", "1.5", "TITUS"],
            ["VAV-3", "OFFICE 103", "500", "1.0", "TITUS"]]
INTERNAL = ("confidence", "ASSUMPTION", "CONFIRMED", "rule:", "AI:", "tech hour", "PENDING", "ADDED", "EXTRA")


def _schedule_sheet() -> Page:
    lines, texts = grid(300, 300, [90, 120, 70, 70, 100], VAV_ROWS)
    return Page(W, H, ((200, 200, FILLER, 12), *texts,
                       (2640, 1860, "HVAC SCHEDULES", 20), (2800, 2000, "M-601", 40)), lines=lines)


PLAN = Page(W, H, ((200, 300, FILLER, 12), (900, 900, "VAV-1", 12), (900, 1000, "VAV-2", 12),
                   (900, 1100, "VAV-3", 12), (2640, 1860, "SECOND FLOOR PLAN", 20), (2800, 2000, "M-201", 40)))
SEQUENCE = Page(texts=((72, 72, "SECTION 23 09 93 - SEQUENCE OF OPERATIONS\n\n"
                                "A. VAV boxes: each VAV box shall maintain the space temperature and CO2 "
                                "setpoints.\n\n23 09 93 - 1", 10),))


@pytest.fixture
def job(tmp_path):
    root = tmp_path / "26-9999, 1 Test Street"
    base = root / "2. Takeoffs" / "1. Base Takeoff"
    make_pdf(base / "Mech.pdf", _schedule_sheet(), PLAN)
    make_pdf(base / "230993.pdf", SEQUENCE)
    return root


@pytest.fixture
def estimated(job, tmp_path, capsys):
    out = tmp_path / "out"
    assert main(["estimate", str(job), "--out", str(out), "--no-ai", "--workers", "1"]) == 0
    return out, capsys.readouterr().out


def _proposal_text(path) -> str:
    document = Document(str(path))
    texts = [p.text for p in document.paragraphs]
    texts += [cell.text for table in document.tables for row in table.rows for cell in row.cells]
    return "\n".join(texts)


def test_the_estimate_writes_the_proposal_the_price_sheet_and_the_evidence_package(estimated):
    out, printed = estimated
    proposal, sheet = out / "26-9999 Proposal.docx", out / "26-9999 Price Sheet.xlsx"
    package = out / "26-9999 Evidence Package.xlsx"
    assert proposal.exists() and sheet.exists() and package.exists()

    text = _proposal_text(proposal)
    assert "Qty (3)" in text
    assert "Discharge Air Temperature Sensor" in text
    assert "Space Temperature / CO2 Sensor" in text

    names = openpyxl.load_workbook(package).sheetnames
    assert names[:3] == [TABS[0], *ESTIMATE_TABS]
    assert ESTIMATE_TABS == ("Review list", "Scope lines")

    assert "Systems written: 1 in the proposal" in printed
    assert "PENDING" in printed and "review list" in printed.lower()
    assert "AI: not used" in printed


def test_without_a_key_the_ai_is_not_used_and_its_lines_say_why(job, tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out = tmp_path / "out"
    assert main(["estimate", str(job), "--out", str(out), "--workers", "1"]) == 0
    assert "AI: not used — no AI key set" in capsys.readouterr().out
    assert (out / "26-9999 Proposal.docx").exists()


def test_nothing_internal_reaches_the_proposal(estimated):
    out, _ = estimated
    scope = "\n".join(scope_texts(out / "26-9999 Proposal.docx"))
    for word in INTERNAL:
        assert not re.search(rf"\b{re.escape(word)}", scope), word
    whole = _proposal_text(out / "26-9999 Proposal.docx")
    for word in ("confidence", "ASSUMPTION", "CONFIRMED", "rule:", "AI:", "tech hour", "PENDING"):
        assert word not in whole, word


def test_the_evidence_package_lists_the_review_and_every_scope_line(estimated):
    out, _ = estimated
    workbook = openpyxl.load_workbook(out / "26-9999 Evidence Package.xlsx")
    review = [[c.value for c in row] for row in workbook["Review list"].iter_rows()]
    assert review[0][:5] == ["System", "Category", "What to decide", "Evidence", "Suggested action"]
    assert any(row[1] == "ASSUMPTION" for row in review[1:])
    assert any(row[0] == "Cover page" for row in review[1:])            # the MEP engineer could not be read

    lines = [[c.value for c in row] for row in workbook["Scope lines"].iter_rows()]
    headings = lines[0]
    assert headings == ["System", "Line", "Quantity", "Tech hours", "Category", "Confidence", "Source", "Evidence",
                        "In the proposal?"]
    valve = next(row for row in lines if row[1] == "Furnish and Wire Hot Water Control Valve and Actuator")
    assert (valve[2], valve[4], valve[8]) == (3, "CONFIRMED", "yes")
    assert "HW GPM" in valve[7]
    header = next(row for row in lines if row[1] and str(row[1]).startswith("Qty (3)"))
    assert header[3] == 12
