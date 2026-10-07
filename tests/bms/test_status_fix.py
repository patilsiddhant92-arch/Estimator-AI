"""STATUS-FIX (REVIEW-STATUS F1-F4): the 'running' state written at the start of estimate, the quote and job in the
run state, the saved job of the ledger's own quote, and the wording when no request is found. Invented job only
(test_run's fixture) and invented folders; no job text."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from bms import run
from bms.__main__ import main
from bms.status import RUN_STATE

from test_run import _reach, job_folder  # noqa: F401  (job_folder is a fixture)

_NOT_ENDED = "the last run did not reach the end"


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _stamp(path: Path, ns: int) -> None:
    os.utime(path, ns=(ns, ns))


def _code(out: Path, cache: Path, capsys) -> tuple[int, str]:
    code = main(["status", str(out), "--cache", str(cache)])
    return code, capsys.readouterr().out


def _state(out: Path) -> dict:
    return json.loads((out / RUN_STATE).read_text(encoding="utf-8"))


def _finished(out: Path, cache: Path, quote: str = "00-0000", job: str = "Invented A", state: dict | None = None,
              at: int | None = None) -> int:
    """A finished run of `quote` in invented files, every file in one tick; `state` replaces the 'done' state."""
    at = at or time.time_ns() - 60_000_000_000
    _write(out / f"{quote} Ledger.json", {"job_name": job, "complete": True, "stopped_at": ""})
    _write(out / f"{quote} Job.json", {"systems": [{"key": "EF", "name": "Exhaust Fans", "devices": [{"id": "x"}]}]})
    for name in ("Review.html", f"{quote} Proposal.docx", f"{quote} Price Sheet.xlsx"):
        (out / name).write_text("invented", encoding="utf-8")
    _write(out / RUN_STATE, state or {"version": 1, "status": "done", "stage": "done", "waiting": 0, "messages": []})
    for path in out.iterdir():
        _stamp(path, at)
    cache.mkdir(parents=True, exist_ok=True)
    return at


# ---- F1: a 'running' state ------------------------------------------------------------------------------------------

def test_a_running_state_newer_than_the_ledger_is_not_finished(tmp_path, capsys):
    out, cache = tmp_path / "out", tmp_path / "cache"
    at = _finished(out, cache)
    _write(out / RUN_STATE, {"version": 1, "status": "running"})
    _stamp(out / RUN_STATE, at + 10_000_000_000)
    code, text = _code(out, cache, capsys)
    assert code == 1 and "Stage: done." not in text and _NOT_ENDED in text


def test_a_running_state_older_than_the_ledger_is_still_not_finished(tmp_path, capsys):
    """The run saved its ledger after it wrote 'running', then ended with an error: the plain reason is kept."""
    out, cache = tmp_path / "out", tmp_path / "cache"
    at = _finished(out, cache, state={"version": 1, "status": "running", "quote": "00-0000", "job": "Invented A"})
    _stamp(out / RUN_STATE, at - 10_000_000_000)
    code, text = _code(out, cache, capsys)
    assert code == 1 and "Stage: done." not in text and _NOT_ENDED in text


def test_a_crash_in_cataloguing_leaves_a_running_state_and_status_is_not_done(job_folder, tmp_path, monkeypatch,
                                                                              capsys):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out, cache = tmp_path / "out", tmp_path / "cache"
    assert _reach(job_folder, out, cache, "done").status == "done"

    def crash(*_a, **_k):
        raise RuntimeError("invented cataloguing crash")

    monkeypatch.setattr(run, "catalogue_job", crash)
    with pytest.raises(RuntimeError, match="invented cataloguing crash"):
        run.estimate(job_folder, out, cache, "chat")
    assert _state(out)["status"] == "running"
    assert not list(out.glob("*.tmp"))
    code, text = _code(out, cache, capsys)
    assert code == 1 and "Stage: done." not in text and _NOT_ENDED in text


def test_the_run_state_names_the_ledgers_quote_and_job(job_folder, tmp_path, monkeypatch, capsys):
    """Every state the run writes once the job is known (the running one too) names the ledger's quote and job."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out, cache = tmp_path / "out", tmp_path / "cache"
    seen: list[dict] = []
    real_read = run.read_ledger

    def read_and_look(*a, **k):                    # the running state, rewritten once the job is known
        seen.append(_state(out))
        return real_read(*a, **k)

    monkeypatch.setattr(run, "read_ledger", read_and_look)
    assert _reach(job_folder, out, cache, "done").status == "done"
    ledger_file = next(out.glob("* Ledger.json"))
    quote = ledger_file.name[:-len(" Ledger.json")]
    job = json.loads(ledger_file.read_text(encoding="utf-8"))["job_name"]
    assert seen and all((s["status"], s["quote"], s["job"]) == ("running", quote, job) for s in seen)
    state = _state(out)
    assert (state["status"], state["quote"], state["job"]) == ("done", quote, job)
    assert _code(out, cache, capsys)[0] == 0


# ---- F1: a state of another quote or job is not trusted -------------------------------------------------------------

def test_a_done_state_of_another_quote_is_not_trusted(tmp_path, capsys):
    """Job B's ledger and outputs are current, but the newest 'done' state is job A's: not done."""
    out, cache = tmp_path / "out", tmp_path / "cache"
    at = _finished(out, cache, quote="11-1111", job="Invented B")
    _write(out / RUN_STATE, {"version": 1, "status": "done", "stage": "done", "waiting": 0, "messages": [],
                             "quote": "00-0000", "job": "Invented B"})
    _stamp(out / RUN_STATE, at + 10_000_000_000)
    code, text = _code(out, cache, capsys)
    assert code == 1 and "Stage: done." not in text and "not finished" in text


def test_a_done_state_of_another_job_is_not_trusted(tmp_path, capsys):
    out, cache = tmp_path / "out", tmp_path / "cache"
    at = _finished(out, cache, quote="11-1111", job="Invented B")
    _write(out / RUN_STATE, {"version": 1, "status": "done", "stage": "done", "waiting": 0, "messages": [],
                             "quote": "11-1111", "job": "Invented A"})
    _stamp(out / RUN_STATE, at + 10_000_000_000)
    code, text = _code(out, cache, capsys)
    assert code == 1 and "Stage: done." not in text and "not finished" in text


# ---- F3: waiting, but no request in that cache folder ---------------------------------------------------------------

def test_waiting_with_no_request_in_the_cache_folder_says_so(tmp_path, capsys):
    out, cache = tmp_path / "out", tmp_path / "cache"
    _finished(out, cache, state={"version": 1, "status": "waiting", "stage": "qc", "waiting": 2, "messages": [],
                                 "quote": "00-0000", "job": "Invented A"})
    code, text = _code(out, cache, capsys)
    assert code == 2
    assert "no request was found in that cache folder (is --cache the one the run used?)" in text
    assert "waiting for 0 answer(s)" not in text


# ---- F4: the state is written in plain ASCII ------------------------------------------------------------------------

def test_the_run_state_is_written_in_ascii_and_reads_back_the_same(tmp_path):
    message = "Stopped: invented café – note"
    run._save_run_state(tmp_path, run.RunResult("waiting", "qc", messages=(message,)))
    raw = (tmp_path / RUN_STATE).read_bytes()
    assert raw.isascii()
    assert json.loads(raw)["messages"] == [message]
