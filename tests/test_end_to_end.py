import openpyxl

from conftest import TEST_JOB_FILE
from estimator.__main__ import main
from estimator.price_sheet.rows import read_sent_rows
from estimator.proposal.read import read_proposal
from estimator.proposal.sections import closing_texts, cover_lines, opening_texts, scope_texts
from estimator.text import strip_list_marker


def _build(tmp_path):
    main(["build", str(TEST_JOB_FILE), "--out", str(tmp_path)])
    return tmp_path / "26-0246 Proposal.docx", tmp_path / "26-0246 Price Sheet.xlsx"


def test_the_proposal_matches_what_was_sent(tmp_path, sent_proposal, proposal_template, test_job, without_prices):
    proposal, _ = _build(tmp_path)
    assert scope_texts(proposal) == scope_texts(sent_proposal)
    assert closing_texts(proposal) == closing_texts(sent_proposal)
    assert opening_texts(proposal) == opening_texts(sent_proposal)
    assert read_proposal(proposal, proposal_template) == without_prices(test_job)


def test_the_cover_page_differs_only_where_the_sent_copy_left_the_template(tmp_path, sent_proposal):
    proposal, _ = _build(tmp_path)
    ours, sent = cover_lines(proposal), cover_lines(sent_proposal)
    assert len(ours) == len(sent)
    assert [i for i, (a, b) in enumerate(zip(ours, sent)) if a != b] == [2]
    assert (ours[2], sent[2]) == ("Quote #: 26-0246", "Quote: 26-0246")   # the template's label; the sent copy was edited


def test_the_price_sheet_is_the_proposal_row_for_row(tmp_path):
    proposal, sheet = _build(tmp_path)
    rows = read_sent_rows(sheet)
    in_sheet = [strip_list_marker(r.text) for title in ("Price Sheet 1", "ADD ALT", "DEDUCT ALT") for r in rows[title]]
    assert in_sheet == scope_texts(proposal)


def test_hours_and_quantities_reach_the_price_sheet(tmp_path):
    _, sheet = _build(tmp_path)
    ws = openpyxl.load_workbook(str(sheet))["Price Sheet 1"]
    assert (ws["D6"].value, ws["B6"].value) == ("SCOPE OF WORK – PREWAILING WAGE", 140)
    header = next(r for r in range(6, 397) if ws.cell(r, 4).value == "1.  *Qty (1) BACnet Data Cabinet")
    assert ws.cell(header, 2).value == 10
    assert (ws.cell(header + 1, 4).value, ws.cell(header + 1, 3).value) == ("o  Furnish and Install UPS", 1)


def test_the_alternates_are_numbered_as_the_proposal_numbers_them(tmp_path):
    _, sheet = _build(tmp_path)
    wb = openpyxl.load_workbook(str(sheet))
    assert "45.  *Qty (1) Can Wash Kitchen Exhaust Fan EF-9" in [c.value for c in wb["ADD ALT"]["D"]]
    assert "46.  Qty (1) Shower Room Exhaust Fan EF-2" in [c.value for c in wb["DEDUCT ALT"]["D"]]
