"""python -m bms status, on invented run folders. No job text."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from bms.__main__ import main
from bms.status import check

from test_run import _reach, answer_all, job_folder  # noqa: F401  (job_folder is a fixture)

import bms

SRC = Path(bms.__file__).resolve().parents[1]      # the src/ these tests import, for a subprocess
RUN_STATE = "run state.json"          # bms.status.RUN_STATE, written last by bms.run.estimate


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _age(path: Path, seconds: float) -> None:
    """Set the file `seconds` older than now."""
    then = time.time() - seconds
    os.utime(path, (then, then))


def _finished(out: Path, cache: Path, quote: str = "00-0000") -> None:
    """An invented run folder whose last run finished: the outputs are newer than the ledger and the job."""
    _write(out / f"{quote} Ledger.json", {"job_name": "Invented A", "complete": True, "stopped_at": ""})
    _write(out / f"{quote} Job.json", {"name": "Invented", "systems": [
        {"key": "EF", "name": "Exhaust Fans", "devices": [{"id": "EF.d1"}]}]})
    _age(out / f"{quote} Ledger.json", 60)
    _age(out / f"{quote} Job.json", 50)
    for name in ("Review.html", f"{quote} Proposal.docx", f"{quote} Price Sheet.xlsx"):
        (out / name).write_text("invented", encoding="utf-8")
    cache.mkdir(parents=True, exist_ok=True)


def _code(out: Path, cache: Path, capsys) -> tuple[int, str]:
    code = main(["status", str(out), "--cache", str(cache)])
    return code, capsys.readouterr().out


# ---- the author's tests (TASK-022), with the real counter path and exit codes -------------------------------------

def test_an_empty_folder_says_there_is_no_run(tmp_path, capsys):
    assert main(["status", str(tmp_path)]) == 1
    assert "no run" in capsys.readouterr().out


def test_a_waiting_write_names_the_systems_the_requests_and_the_findings(tmp_path):
    out, cache = tmp_path / "out", tmp_path / "cache"
    _write(out / "00-0000 Ledger.json", {"job_name": "Invented A", "complete": True, "stopped_at": ""})
    _write(out / "00-0000 Job.json", {"name": "Invented", "systems": [
        {"key": "EF", "name": "Exhaust Fans", "devices": [{"id": "EF.d1"}]},
        {"key": "RTU", "name": "Rooftop Units", "no_scope_reason": "by others"}]})
    _write(cache / "judge-chat" / "requests" / "one.json",
           {"kind": "write_system", "step": "write", "system": "Exhaust Fans", "job": "Invented A",
            "answer_file": str(cache / "judge-chat" / "answers" / "one.json")})
    _write(cache / "judge-chat" / "requests" / "old" / "stale.json",
           {"kind": "write_system", "step": "write", "system": "Stale System", "job": "Invented A"})
    _write(cache / "judge" / "attempts" / "abc.json", {"attempts": 2})
    _write(cache / "intake.json", [{"system": "Exhaust Fans", "change": "took a label off"}])
    (out / "Review.html").write_text(
        '<span class="rule">Rule: Name the verb</span>'
        '<span class="rule">Rule: Name the verb</span>'
        '<span class="rule">Rule: A point needs a source</span>', encoding="utf-8")
    text = "\n".join(check(out, cache).lines)
    assert "Stage: write" in text
    assert "Systems written: Exhaust Fans, Rooftop Units." in text
    assert "1 write_system request(s): Exhaust Fans" in text
    assert "Stale System" not in text
    assert "Refusals: 1 question(s) have refused answers; the most for one question is 2." in text
    assert "Exhaust Fans: took a label off" in text
    assert "2 for Name the verb" in text and "1 for A point needs a source" in text


def test_reading_that_stopped_names_the_pass(tmp_path):
    out = tmp_path / "out"
    _write(out / "00-0000 Ledger.json", {"complete": False, "stopped_at": "scope"})
    text = "\n".join(check(out, tmp_path / "cache").lines)
    assert "Stage: read" in text and "scope" in text
    assert "none yet" in text


# ---- H1: an older review page is not "done" ------------------------------------------------------------------------

def test_an_older_review_page_with_a_reading_request_is_not_done(tmp_path, capsys):
    out, cache = tmp_path / "out", tmp_path / "cache"
    _finished(out, cache)
    for name in ("Review.html", "00-0000 Proposal.docx", "00-0000 Price Sheet.xlsx"):
        _age(out / name, 120)                                   # left by an earlier run
    _write(out / "00-0000 Ledger.json", {"job_name": "Invented A", "complete": False, "stopped_at": "scope"})
    _write(cache / "judge-chat" / "requests" / "r.json",
           {"kind": "read_pass", "system": "the scope pass", "job": "Invented A",
            "answer_file": str(cache / "judge-chat" / "answers" / "r.json")})
    code, text = _code(out, cache, capsys)
    assert "Stage: read" in text and "Stage: done" not in text
    assert code == 2


def test_an_older_review_page_and_no_request_is_not_done(tmp_path, capsys):
    out, cache = tmp_path / "out", tmp_path / "cache"
    _finished(out, cache)
    for name in ("Review.html", "00-0000 Proposal.docx", "00-0000 Price Sheet.xlsx"):
        _age(out / name, 120)
    _write(out / "00-0000 Job.json", {"name": "Invented", "systems": []})     # saved again since
    code, text = _code(out, cache, capsys)
    assert "Stage: done" not in text and "not finished" in text
    assert code == 1


def test_a_review_page_with_no_proposal_is_not_done(tmp_path, capsys):
    """The run wrote the review page, then failed before the proposal."""
    out, cache = tmp_path / "out", tmp_path / "cache"
    _finished(out, cache)
    code, text = _code(out, cache, capsys)
    assert "Stage: done." in text and code == 0
    (out / "00-0000 Proposal.docx").unlink()
    code, text = _code(out, cache, capsys)
    assert "Stage: done" not in text and code == 1


def test_a_fresh_run_state_that_stopped_is_shown_with_its_message(tmp_path, capsys):
    """M2: a run stopped after the most refusals leaves no request; the run's own last words name it."""
    out, cache = tmp_path / "out", tmp_path / "cache"
    _finished(out, cache)
    _write(out / "00-0000 Job.json", {"name": "Invented", "systems": []})
    _write(out / RUN_STATE, {"version": 1, "status": "waiting", "stage": "qc", "waiting": 0, "messages": [
        "Stopped: the request the QC pass was refused 3 times. It is not asked again."]})
    code, text = _code(out, cache, capsys)
    assert "Stage: qc" in text and "stopped" in text
    assert "the request the QC pass was refused 3 times" in text
    assert "nothing is waiting" not in text and "Stage: done" not in text
    assert code == 1


def test_a_run_state_older_than_the_job_is_not_trusted(tmp_path, capsys):
    out, cache = tmp_path / "out", tmp_path / "cache"
    _finished(out, cache)
    _write(out / RUN_STATE, {"version": 1, "status": "done", "stage": "done", "waiting": 0, "messages": []})
    for name in ("Review.html", "00-0000 Proposal.docx", "00-0000 Price Sheet.xlsx", RUN_STATE):
        _age(out / name, 40)
    _write(out / "00-0000 Job.json", {"name": "Invented", "systems": []})     # a later run is under way
    code, text = _code(out, cache, capsys)
    assert "Stage: done" not in text and "not finished" in text and code == 1


# ---- the real run writes its state last (end to end, invented job) --------------------------------------------------

def test_a_done_run_then_a_rerun_stopped_by_a_malformed_decisions_file(job_folder, tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out, cache = tmp_path / "out", tmp_path / "cache"
    assert _reach(job_folder, out, cache, "done").status == "done"
    code, text = _code(out, cache, capsys)
    assert code == 0 and "Stage: done." in text
    (out / "decisions.json").write_text("{", encoding="utf-8")
    from bms.run import estimate
    assert estimate(job_folder, out, cache, "chat").stage == "decisions"
    code, text = _code(out, cache, capsys)
    assert code == 1
    assert "Stage: done" not in text and "decisions.json" in text and "Stopped" in text


def test_a_run_stopped_after_the_most_refusals_names_the_request(job_folder, tmp_path, monkeypatch, capsys):
    from bms import ai, run
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out, cache = tmp_path / "out", tmp_path / "cache"
    assert _reach(job_folder, out, cache, "qc").stage == "qc"
    assert answer_all(cache)

    def refused(*_a, **_k):
        raise ai.NoAnswer("Stopped: the request the invented QC pass was refused 3 times. It is not asked again.",
                          waiting=False)

    monkeypatch.setattr(run.ai, "qc_job", refused)
    result = run.estimate(job_folder, out, cache, "chat")
    assert result.stage == "qc" and result.waiting == 0
    code, text = _code(out, cache, capsys)
    assert code == 1 and "the request the invented QC pass was refused 3 times" in text
    assert "nothing is waiting" not in text


# ---- M3: one table entry, no estimate stack -------------------------------------------------------------------------

def test_status_works_when_the_estimate_stack_cannot_import(tmp_path):
    out = tmp_path / "out"
    _finished(out, tmp_path / "cache")
    code = ("import sys; sys.modules['bms.run'] = None; sys.modules['estimator'] = None\n"
            "from bms.__main__ import main\n"
            f"rc = main(['status', {str(out)!r}, '--cache', {str(tmp_path / 'cache')!r}])\n"
            "sys.exit(rc)\n")
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                          env={**os.environ, "PYTHONPATH": str(SRC)})
    assert done.returncode == 0, done.stderr
    assert "Stage: done." in done.stdout
    from bms import __main__ as cli                 # the parser's own copy of the modes stays the run's
    from bms.run import MODES
    assert cli.MODES == MODES


def test_the_help_says_running_during_an_estimate_is_allowed(capsys):
    with pytest.raises(SystemExit):
        main(["status", "--help"])
    text = " ".join(capsys.readouterr().out.split())
    assert "while an estimate is running" in text and "a moment old" in text


# ---- M6: exit codes follow estimate ---------------------------------------------------------------------------------

def test_a_missing_folder_and_a_file_exit_1(tmp_path, capsys):
    assert main(["status", str(tmp_path / "nowhere")]) == 1
    assert "There is no folder" in capsys.readouterr().out
    (tmp_path / "a file.txt").write_text("x", encoding="utf-8")
    assert main(["status", str(tmp_path / "a file.txt")]) == 1
    assert "not a folder" in capsys.readouterr().out


def test_waiting_requests_exit_2(tmp_path, capsys):
    out, cache = tmp_path / "out", tmp_path / "cache"
    _write(out / "00-0000 Ledger.json", {"job_name": "Invented A", "complete": True})
    _write(out / "00-0000 Job.json", {"systems": [{"key": "EF", "name": "Exhaust Fans"}]})
    _write(cache / "judge-chat" / "requests" / "q.json",
           {"kind": "qc_job", "step": "qc", "system": "the QC pass", "job": "Invented A",
            "answer_file": str(cache / "judge-chat" / "answers" / "q.json")})
    code, text = _code(out, cache, capsys)
    assert code == 2 and "Stage: qc" in text and "waiting for 1 answer" in text


# ---- M4: only this job's requests ---------------------------------------------------------------------------------

def test_requests_for_another_job_are_not_this_runs(tmp_path, capsys):
    out, cache = tmp_path / "out", tmp_path / "cache"
    _finished(out, cache)
    _write(cache / "judge-chat" / "requests" / "b.json",
           {"kind": "qc_job", "step": "qc", "system": "the QC pass", "job": "Invented B",
            "answer_file": str(cache / "judge-chat" / "answers" / "b.json")})
    code, text = _code(out, cache, capsys)
    assert "Stage: qc" not in text and "1 request(s) for other jobs" in text
    assert code == 0


# ---- M5, M7: answered requests, planned systems -------------------------------------------------------------------

def test_an_answered_request_says_run_estimate_again(tmp_path, capsys):
    out, cache = tmp_path / "out", tmp_path / "cache"
    _write(out / "00-0000 Ledger.json", {"job_name": "Invented A", "complete": True})
    request = cache / "judge-chat" / "requests" / "q.json"
    answer = cache / "judge-chat" / "answers" / "q.json"
    _write(request, {"kind": "qc_job", "step": "qc", "system": "the QC pass", "job": "Invented A",
                     "answer_file": str(answer)})
    _age(request, 30)
    _write(answer, {"findings": []})
    code, text = _code(out, cache, capsys)
    assert "run estimate again" in text and "waiting for 1 answer" not in text and code == 2


def test_a_planned_system_is_not_called_written(tmp_path):
    out = tmp_path / "out"
    _write(out / "00-0000 Ledger.json", {"job_name": "Invented A", "complete": True})
    _write(out / "00-0000 Job.json", {"systems": [
        {"key": "EF", "name": "Exhaust Fans", "devices": [{"id": "EF.d1"}]},
        {"key": "RTU", "name": "Rooftop Units", "devices": []}]})
    text = "\n".join(check(out, tmp_path / "cache").lines)
    assert "Systems written: Exhaust Fans." in text
    assert "Systems planned, not written yet: Rooftop Units." in text


# ---- M1, M8, L1, L2: odd or half-written files never crash it --------------------------------------------------------

@pytest.mark.parametrize("name,body", [
    ("00-0000 Job.json", b"[1, 2]"),
    ("00-0000 Job.json", b'{"systems": 5}'),
    ("00-0000 Job.json", b'{"systems": [{"name": "half'),
    ("00-0000 Ledger.json", b"[1]"),
    ("00-0000 Ledger.json", b'{"complete": tr'),
    ("Review.html", b"\xff\xfe<span"),
])
def test_odd_run_files_are_reported_not_raised(tmp_path, name, body):
    out, cache = tmp_path / "out", tmp_path / "cache"
    _write(out / "00-0000 Ledger.json", {"job_name": "Invented A", "complete": True})
    (out / name).write_bytes(body)
    _write(cache / "judge" / "attempts" / "a.json", {"attempts": "two"})
    _write(cache / "judge" / "attempts" / "b.json", [3])
    _write(cache / "intake.json", [{"system": None, "change": None}, "odd", 3])
    (cache / "judge-chat" / "requests").mkdir(parents=True)
    (cache / "judge-chat" / "requests" / "half.json").write_text('{"kind": "qc_j', encoding="utf-8")
    text = "\n".join(check(out, cache).lines)
    assert text and "None" not in text


def test_a_truncated_ledger_is_named(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "00-0000 Ledger.json").write_text('{"complete": fa', encoding="utf-8")
    text = "\n".join(check(out, tmp_path / "cache").lines)
    assert "could not be read" in text and "pass pass" not in text


def test_a_locked_or_vanishing_file_is_named_not_raised(tmp_path, monkeypatch):
    """Windows: another program (or the estimate itself) holds the file, or swaps it away mid-read."""
    out, cache = tmp_path / "out", tmp_path / "cache"
    _finished(out, cache)
    _write(cache / "judge-chat" / "requests" / "gone.json", {"kind": "qc_job", "job": "Invented A"})
    real_bytes, real_text = Path.read_bytes, Path.read_text

    def blocked(self):
        if self.name == "Review.html":
            raise PermissionError(13, "The process cannot access the file", str(self))
        if self.name == "gone.json":
            raise FileNotFoundError(2, "No such file", str(self))
        return None

    monkeypatch.setattr(Path, "read_bytes", lambda self: blocked(self) or real_bytes(self))
    monkeypatch.setattr(Path, "read_text", lambda self, *a, **k: blocked(self) or real_text(self, *a, **k))
    text = "\n".join(check(out, cache).lines)
    assert "the review page could not be read" in text


# ---- L3, L4, L5 ------------------------------------------------------------------------------------------------------

def test_a_reading_request_alone_says_read(tmp_path, capsys):
    out, cache = tmp_path / "out", tmp_path / "cache"
    out.mkdir()
    _write(cache / "judge-chat" / "requests" / "r.json",
           {"kind": "read_pass", "system": "the scope pass", "job": "Invented A",
            "answer_file": str(cache / "judge-chat" / "answers" / "r.json")})
    code, text = _code(out, cache, capsys)
    assert "Stage: read." in text and code == 2


def test_the_newest_ledger_and_job_are_used(tmp_path):
    out = tmp_path / "out"
    _write(out / "Unknown Ledger.json", {"job_name": "Invented A", "complete": False, "stopped_at": "scope"})
    _write(out / "Unknown Job.json", {"systems": [{"key": "EF", "name": "Old Fans", "devices": [{"id": "x"}]}]})
    _age(out / "Unknown Ledger.json", 100)
    _age(out / "Unknown Job.json", 100)
    _write(out / "00-0000 Ledger.json", {"job_name": "Invented A", "complete": True})
    _write(out / "00-0000 Job.json", {"systems": [{"key": "EF", "name": "New Fans", "devices": [{"id": "x"}]}]})
    text = "\n".join(check(out, tmp_path / "cache").lines)
    assert "New Fans" in text and "Old Fans" not in text and "scope" not in text


def test_findings_are_read_from_the_rule_spans_only(tmp_path):
    out, cache = tmp_path / "out", tmp_path / "cache"
    _finished(out, cache)
    (out / "Review.html").write_text(
        '<p>quoted job text: Rule: not a finding</p><span class="rule">Rule: Wire &amp; tag</span>',
        encoding="utf-8")
    text = "\n".join(check(out, cache).lines)
    assert "1 for Wire & tag" in text and "not a finding" not in text


# ---- the takeoff pass (plan 2026-10-11, Task 1.5) -------------------------------------------------------------------

def test_a_waiting_takeoff_request_reports_the_takeoff_stage(tmp_path):
    out, cache = tmp_path / "out", tmp_path / "cache"
    _write(out / "00-0000 Ledger.json", {"job_name": "Invented A", "complete": True, "stopped_at": ""})
    _write(cache / "judge-chat" / "requests" / "t.json",
           {"kind": "takeoff_job", "step": "takeoff", "system": "Takeoff", "job": "Invented A",
            "answer_file": str(cache / "judge-chat" / "answers" / "t.json")})
    text = "\n".join(check(out, cache).lines)
    assert "Stage: takeoff" in text and "1 takeoff_job request(s): Takeoff" in text


def test_the_takeoff_stage_sorts_between_read_and_count():
    from bms.status import _KIND_STAGE, _ORDER, _STEP_STAGE
    assert _ORDER.index("read") < _ORDER.index("takeoff") == _ORDER.index("read") + 1 < _ORDER.index("count")
    assert _KIND_STAGE["takeoff_job"] == "takeoff" and _STEP_STAGE["takeoff"] == "takeoff"
