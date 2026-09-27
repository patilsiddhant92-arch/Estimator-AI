"""The estimate command: from a job folder to the proposal, the price sheet and the Evidence Package."""
import re

import openpyxl
import pytest
from docx import Document

from estimator.__main__ import _parser, ai_mode, main
from estimator.evidence.workbook import ESTIMATE_TABS, PLAN_TAB, TABS
from estimator.proposal.sections import scope_texts
from pdfs import FILLER, Page, make_pdf
from test_assemble import Dossier, FakeJudge, JobPlan, PlannedSystem, WrittenLine, WrittenScope
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
    assert main(["estimate", str(job), "--out", str(out), "--no-ai", "--workers", "1", "--method", "rules"]) == 0
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


def test_the_api_without_a_key_is_not_used_and_its_lines_say_why(job, tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out = tmp_path / "out"
    assert main(["estimate", str(job), "--out", str(out), "--ai", "api", "--workers", "1", "--method", "rules"]) == 0
    assert "AI: not used — no AI key set" in capsys.readouterr().out
    assert (out / "26-9999 Proposal.docx").exists()


@pytest.mark.parametrize("flags, key, mode", [
    ([], None, "chat"),                        # no key: the chat answers
    ([], "not-a-real-key", "api"),             # a key: the API answers
    (["--ai", "chat"], "not-a-real-key", "chat"),
    (["--ai", "api"], None, "api"),
    (["--ai", "off"], "not-a-real-key", "off"),
    (["--no-ai"], "not-a-real-key", "off"),     # the old flag still works
])
def test_the_ai_flag_picks_who_answers(flags, key, mode, monkeypatch):
    if key:
        monkeypatch.setenv("ANTHROPIC_API_KEY", key)
    else:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    args = _parser().parse_args(["estimate", "JOB", "--out", "OUT", *flags])
    assert ai_mode(args) == mode


def test_no_ai_and_ai_cannot_both_be_given(capsys):
    with pytest.raises(SystemExit):
        _parser().parse_args(["estimate", "JOB", "--out", "OUT", "--no-ai", "--ai", "chat"])


def test_in_chat_mode_the_questions_wait_in_the_requests_folder(job, tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("anthropic.Anthropic", lambda *a, **k: pytest.fail("the chat mode never calls the API"))
    out, cache = tmp_path / "out", tmp_path / "cache"
    assert main(["estimate", str(job), "--out", str(out), "--ai", "chat", "--cache", str(cache),
                 "--workers", "1", "--method", "rules"]) == 0
    printed = capsys.readouterr().out
    requests = cache / "judge-chat" / "requests"
    written = list(requests.glob("*.json"))
    assert written
    assert (f"AI: answered in the chat for 0 systems; {len(written)} waiting — requests in {requests}. "
            "Answer them, then run estimate again.") in printed
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
    assert review[0][:6] == ["Rank", "System", "Category", "What to decide", "Evidence", "Suggested action"]
    assert review[1][0] == 1
    assert any(row[2] == "ASSUMPTION" for row in review[1:])
    assert any(row[1] == "Cover page" for row in review[1:])            # the MEP engineer could not be read

    lines = [[c.value for c in row] for row in workbook["Scope lines"].iter_rows()]
    headings = lines[0]
    assert headings == ["System", "Line", "Quantity", "Tech hours", "Category", "Confidence", "Source", "Evidence",
                        "In the proposal?", "Reference line", "Flag"]
    valve = next(row for row in lines if row[1] == "Furnish and Wire Hot Water Control Valve and Actuator")
    assert (valve[2], valve[4], valve[8]) == (3, "CONFIRMED", "yes")
    assert "HW GPM" in valve[7]
    header = next(row for row in lines if row[1] and str(row[1]).startswith("Qty (3)"))
    assert header[3] == 12


# --- the whole-job method (the default) ----------------------------------------------------------------------

DOSSIER_TEXT = "\n".join([
    "1. Job", "[S1] 26-9999, 1 Test Street", "",
    "2. Sequence of operation",
    "[S2] A. VAV boxes: each VAV box shall maintain the space temperature and CO2 setpoints.", "",
    "4. Schedules", "[S3] M-601 VAV BOX SCHEDULE",
    "[S4] VAV-1 | OFFICE 101 | 600 | 1.5 | TITUS", "[S5] VAV-2 | OFFICE 102 | 700 | 1.5 | TITUS",
    "[S6] VAV-3 | OFFICE 103 | 500 | 1.0 | TITUS", "",
    "[S7] Exhaust fans EF-1 and EF-2 run on the line-voltage thermostat.", ""])


def _fake_dossier(catalogue, reading, cache_dir):
    return Dossier("26-9999", DOSSIER_TEXT, (), {"S2": "23 09 93 SEQUENCE OF OPERATIONS, 230993.pdf page 1",
                                                  "S3": "M-601 VAV BOX SCHEDULE, Mech.pdf page 1", "S7": "M-201"},
                   tuple(reading.totals), {}, {"VAV": {"schedule_rows": 3, "quantity_column": None,
                                                       "plan_placements": 3, "riser": None, "distinct_tags": 3}}, {})


JOB_PLAN = JobPlan((
    PlannedSystem("VAV", "Variable Air Volume Box VAV-1 thru 3", "Variable Air Volume Box", ("VAV-1", "VAV-2", "VAV-3"),
                  3, "S3", "M-601 VAV BOX SCHEDULE", ("S2",), ("S3", "S4", "S5", "S6"), why="three scheduled"),
    PlannedSystem("EF", "Exhaust Fan EF-1, 2", "Exhaust Fan", ("EF-1", "EF-2"), 2, "S7", "Exhaust fans EF-1 and EF-2",
                  ("S7",), exception="EXCEPTION TO ANY WORK WITH Qty (2) EF-1, 2 - LINE-VOLTAGE THERMOSTAT"),
))
SCOPES = {"VAV": WrittenScope((
    WrittenLine("Furnish DDC Controller to the Factory for Installation", quote="each VAV box shall maintain",
                source_id="S2", why="a VAV box controller"),
    WrittenLine("Furnish and Install Space Temperature / CO2 Sensor", quote="space temperature and CO2 setpoints",
                source_id="S2", why="the sequence names CO2"),
    WrittenLine("Furnish and Wire Hot Water Control Valve and Actuator (confidence 0.9)", quote="1.5",
                source_id="S4"),
    WrittenLine("Furnish and Install VAV Transformer", quote="each VAV box", source_id="S2"),
))}


@pytest.fixture
def whole_job(monkeypatch):
    monkeypatch.setattr("estimator.__main__.build_dossier", _fake_dossier)
    judges = []

    def make(cache, mode, job=None):
        judges.append(FakeJudge(JOB_PLAN, SCOPES, mode=mode))
        return judges[-1]

    monkeypatch.setattr("estimator.__main__.Judge", make)
    return judges


def test_whole_job_is_the_default_method():
    assert _parser().parse_args(["estimate", "JOB", "--out", "OUT"]).method == "whole-job"
    assert _parser().parse_args(["estimate", "JOB", "--out", "OUT", "--method", "rules"]).method == "rules"


def test_with_the_ai_off_the_whole_job_method_writes_the_dossier_and_the_evidence_package_only(
        job, tmp_path, capsys, whole_job):
    out = tmp_path / "out"
    assert main(["estimate", str(job), "--out", str(out), "--ai", "off", "--workers", "1"]) == 0
    printed = capsys.readouterr().out
    assert (out / "26-9999 Dossier.txt").read_text(encoding="utf-8") == DOSSIER_TEXT
    assert (out / "26-9999 Evidence Package.xlsx").exists()
    assert not (out / "26-9999 Proposal.docx").exists() and not (out / "26-9999 Price Sheet.xlsx").exists()
    assert "the AI writes the scope; run with --ai chat or api" in printed
    assert whole_job == []                                     # no judge was made


def test_the_whole_job_method_writes_the_planned_blocks_and_nothing_internal(job, tmp_path, capsys, whole_job):
    out = tmp_path / "out"
    assert main(["estimate", str(job), "--out", str(out), "--ai", "api", "--workers", "1"]) == 0
    printed = capsys.readouterr().out
    assert whole_job[0].asked == ["plan", "VAV"]              # the exception needs no scope
    proposal = out / "26-9999 Proposal.docx"
    assert proposal.exists() and (out / "26-9999 Price Sheet.xlsx").exists()
    text = _proposal_text(proposal)
    assert "Qty (3) Variable Air Volume Box VAV-1 thru 3" in text
    assert "Space Temperature / CO2 Sensor" in text
    assert "EXCEPTION TO ANY WORK WITH Qty (2) EF-1, 2 - LINE-VOLTAGE THERMOSTAT" in text
    assert "Hot Water Control Valve" not in text               # it named its confidence: dropped
    scope = "\n".join(scope_texts(proposal))
    for word in INTERNAL + ("[S", "whole job", "DISCREPANCY"):
        assert not re.search(rf"\b{re.escape(word)}" if word[0].isalpha() else re.escape(word), scope), word
    for word in ("confidence", "ASSUMPTION", "CONFIRMED", "rule:", "AI:", "tech hour", "PENDING", "AI (whole job)"):
        assert word not in text, word

    workbook = openpyxl.load_workbook(out / "26-9999 Evidence Package.xlsx")
    assert workbook.sheetnames[:4] == [TABS[0], *ESTIMATE_TABS, PLAN_TAB]
    plan = [[c.value for c in row] for row in workbook[PLAN_TAB].iter_rows()]
    vav = next(row for row in plan if row[0] == "VAV")
    assert (vav[4], vav[5], vav[11]) == (3, "CONFIRMED", 3)
    lines = [[c.value for c in row] for row in workbook["Scope lines"].iter_rows()]
    sensor = next(row for row in lines if row[1] == "Furnish and Install Space Temperature / CO2 Sensor")
    assert sensor[6] == "AI (whole job) [S2]" and sensor[8] == "yes"
    review = [[c.value for c in row] for row in workbook["Review list"].iter_rows()]
    assert any(row[3] and "dropped" in row[3] for row in review)

    assert "Systems planned: 2; 1 written in the proposal, 1 put in the exceptions." in printed
    assert "AI: 2 calls to fake-model, 0 answered from the cache at no cost." in printed
    assert f"Wrote {out / '26-9999 Dossier.txt'}" in printed


def test_in_chat_mode_the_whole_job_method_waits_for_the_answers(job, tmp_path, capsys, monkeypatch, whole_job):
    monkeypatch.setattr("estimator.__main__.Judge", lambda cache, mode, job=None: whole_job.append(_Waiting(mode)) or
                        whole_job[-1])
    out = tmp_path / "out"
    assert main(["estimate", str(job), "--out", str(out), "--ai", "chat", "--workers", "1"]) == 0
    printed = capsys.readouterr().out
    assert "1 request waiting — requests in requests. Answer them, then run estimate again." in printed
    assert (out / "26-9999 Evidence Package.xlsx").exists() and (out / "26-9999 Dossier.txt").exists()
    assert not (out / "26-9999 Proposal.docx").exists()


class _Waiting(FakeJudge):
    """The chat has not answered the plan yet."""

    def __init__(self, mode):
        super().__init__(None, {}, mode=mode)

    def plan_job(self, *args):
        self.waiting += 1
        return None
