"""REVIEW-STATUS (review of record for lead/status-command): the run state estimate writes last, and status on
invented run folders. Invented job only (test_run's fixture); no job text."""
from __future__ import annotations

import inspect
import json
import os
import time
from pathlib import Path

import pytest

from bms import run
from bms.__main__ import main
from bms.status import RUN_STATE, check

from test_run import _reach, answer_all, job_folder  # noqa: F401  (job_folder is a fixture)


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _stamp(path: Path, ns: int) -> None:
    os.utime(path, ns=(ns, ns))


def _snapshot(*roots: Path) -> dict[str, tuple[int, int]]:
    """Every file and folder under `roots`: (size, mtime_ns)."""
    seen = {}
    for root in roots:
        if not root.exists():
            continue
        for path in [root, *root.rglob("*")]:
            st = path.stat()
            seen[str(path)] = (st.st_size if path.is_file() else -1, st.st_mtime_ns)
    return seen


def _state(out: Path) -> dict:
    return json.loads((out / RUN_STATE).read_text(encoding="utf-8"))


def _code(out: Path, cache: Path, capsys) -> tuple[int, str]:
    code = main(["status", str(out), "--cache", str(cache)])
    return code, capsys.readouterr().out


# ---- 1. estimate: the same contract, the state written whole on every normal exit ----------------------------------

def test_estimate_keeps_its_contract_signature():
    sig = inspect.signature(run.estimate)
    assert list(sig.parameters) == ["job_folder", "out", "cache", "mode"]
    assert sig.parameters["mode"].default == "chat"
    assert sig.return_annotation in ("RunResult", run.RunResult)
    with pytest.raises(ValueError):
        run.estimate(Path("nowhere"), Path("nowhere"), Path("nowhere"), "both")


def test_every_normal_exit_writes_the_state_whole_and_status_agrees(job_folder, tmp_path, monkeypatch, capsys):
    """Waiting at each stage, then done: the state is the result, no temporary file is left, status exits as
    estimate's command would (2 waiting, 0 done), and a status run in between changes no file."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out, cache = tmp_path / "out", tmp_path / "cache"
    for _ in range(25):
        result = run.estimate(job_folder, out, cache, "chat")
        state = _state(out)
        assert (state["status"], state["stage"], state["waiting"]) == (result.status, result.stage, result.waiting)
        assert state["messages"] == list(result.messages)
        assert not list(out.glob("*.tmp"))
        before = _snapshot(out, cache)
        code, text = _code(out, cache, capsys)
        assert _snapshot(out, cache) == before                 # status is read-only
        if result.status == "done":
            assert code == 0 and "Stage: done." in text
            break
        assert code == 2 and f"Stage: {result.stage}." in text
        assert f"waiting for {result.waiting} answer(s)" in text
        assert answer_all(cache)
        code, text = _code(out, cache, capsys)                 # answered, not run again
        assert code == 2 and "run estimate again" in text
    else:
        raise AssertionError("never done")


def test_a_state_that_cannot_be_written_never_blocks_the_result(job_folder, tmp_path, monkeypatch, capsys):
    """A locked run state (Windows: another program holds it): the run's result comes back unchanged, no
    temporary file is left, and status does not claim the run is done from the older state."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out, cache = tmp_path / "out", tmp_path / "cache"
    first = _reach(job_folder, out, cache, "write")
    assert first.status == "waiting" and _state(out)["stage"] == first.stage
    assert answer_all(cache)

    def locked(src, dst):
        raise PermissionError(13, "The process cannot access the file", str(dst))

    class LockedOs:                                         # only bms.run's os; every other module's stays real
        def __getattr__(self, name):
            return locked if name == "replace" else getattr(os, name)

    monkeypatch.setattr(run, "os", LockedOs())
    result = _reach(job_folder, out, cache, "done")
    monkeypatch.undo()
    assert result.status == "done" and result.proposal is not None and result.proposal.is_file()
    assert _state(out)["stage"] == first.stage                  # the old state stays, older than the ledger
    assert not list(out.glob("*.tmp"))
    code, text = _code(out, cache, capsys)
    assert code == 1 and "Stage: done" not in text and "not finished" in text


def test_a_crash_in_render_raises_as_before_and_status_is_not_done(job_folder, tmp_path, monkeypatch, capsys):
    """After a finished run, a re-run that crashes while rendering: the same exception reaches the caller, no ending
    state but "running" is written, and status (old review page) does not say done."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out, cache = tmp_path / "out", tmp_path / "cache"
    assert _reach(job_folder, out, cache, "done").status == "done"
    old = (out / RUN_STATE).stat().st_mtime_ns
    time.sleep(0.05)

    class Boom(RuntimeError):
        pass

    def crash(*_a, **_k):
        raise Boom("invented render crash")

    monkeypatch.setattr(run, "render", crash)
    with pytest.raises(Boom):
        run.estimate(job_folder, out, cache, "chat")
    assert (out / RUN_STATE).stat().st_mtime_ns != old and _state(out)["status"] == "running"   # STATUS-FIX F1
    code, text = _code(out, cache, capsys)
    assert code == 1 and "Stage: done" not in text and "not finished" in text


def test_a_model_error_from_the_pipeline_still_raises(job_folder, tmp_path, monkeypatch):
    from bms.model import ModelError
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    def bad(*_a, **_k):
        raise ModelError("invented bad plan")

    out, cache = tmp_path / "out", tmp_path / "cache"
    real_plan, planned = run.plan_job, []

    def plan_once(*a, **k):                                   # the run got past reading
        planned.append(1)
        return real_plan(*a, **k)

    monkeypatch.setattr(run, "plan_job", plan_once)
    for _ in range(10):                                       # reading and the takeoff ask first; answer them
        if run.estimate(job_folder, out, cache, "chat").stage not in ("read", "takeoff") or planned:
            break
        assert answer_all(cache)
    assert planned
    old = (out / RUN_STATE).stat().st_mtime_ns
    time.sleep(0.05)
    monkeypatch.setattr(run, "plan_job", bad)
    with pytest.raises(ModelError, match="invented bad plan"):
        run.estimate(job_folder, out, cache, "chat")
    assert (out / RUN_STATE).stat().st_mtime_ns != old and _state(out)["status"] == "running"   # STATUS-FIX F1


def test_a_crash_before_the_ledger_is_saved_is_not_done(job_folder, tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out, cache = tmp_path / "out", tmp_path / "cache"
    assert _reach(job_folder, out, cache, "done").status == "done"

    def crash(*_a, **_k):
        raise RuntimeError("invented reading crash")

    monkeypatch.setattr(run, "read_job", crash)
    with pytest.raises(RuntimeError):
        run.estimate(job_folder, out, cache, "chat")
    code, text = _code(out, cache, capsys)
    assert code != 0 and "Stage: done." not in text


def test_status_mid_run_never_says_done(job_folder, tmp_path, monkeypatch):
    """Status called while the estimate is rendering (ledger and job just saved, old outputs and old state on
    disk): never done, never raises, changes nothing."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out, cache = tmp_path / "out", tmp_path / "cache"
    assert _reach(job_folder, out, cache, "done").status == "done"
    real, seen = run.render, []

    def render_and_look(*a, **k):
        before = _snapshot(out, cache)
        seen.append(check(out, cache))
        assert _snapshot(out, cache) == before
        return real(*a, **k)

    monkeypatch.setattr(run, "render", render_and_look)
    assert run.estimate(job_folder, out, cache, "chat").status == "done"
    assert seen and seen[0].code == 1 and not any(line.startswith("Stage: done.") for line in seen[0].lines)


# ---- 2. status on invented folders ----------------------------------------------------------------------------------

def _finished(out: Path, cache: Path, quote: str = "00-0000", at: int | None = None) -> int:
    at = at or time.time_ns() - 60_000_000_000
    _write(out / f"{quote} Ledger.json", {"job_name": "Invented A", "complete": True, "stopped_at": ""})
    _write(out / f"{quote} Job.json", {"systems": [{"key": "EF", "name": "Exhaust Fans", "devices": [{"id": "x"}]}]})
    for name in ("Review.html", f"{quote} Proposal.docx", f"{quote} Price Sheet.xlsx"):
        (out / name).write_text("invented", encoding="utf-8")
    _write(out / RUN_STATE, {"version": 1, "status": "done", "stage": "done", "waiting": 0, "messages": []})
    for path in out.iterdir():
        _stamp(path, at)
    cache.mkdir(parents=True, exist_ok=True)
    return at


def test_ties_on_a_coarse_clock_still_say_done(tmp_path, capsys):
    """Every file of one run in the same clock tick (a 2-second file system): done."""
    out, cache = tmp_path / "out", tmp_path / "cache"
    _finished(out, cache, at=1_700_000_000_000_000_000)
    code, text = _code(out, cache, capsys)
    assert code == 0 and "Stage: done." in text


def test_a_state_newer_than_a_ledger_of_another_quote_without_its_outputs_is_not_done(tmp_path, capsys):
    """Job A finished; then a ledger for another quote (job B) and a 'done' state newer than it, but none of B's
    outputs: not done (A's review page is not B's)."""
    out, cache = tmp_path / "out", tmp_path / "cache"
    at = _finished(out, cache)
    _write(out / "11-1111 Ledger.json", {"job_name": "Invented B", "complete": True})
    _stamp(out / "11-1111 Ledger.json", at + 10_000_000_000)
    _stamp(out / RUN_STATE, at + 20_000_000_000)
    code, text = _code(out, cache, capsys)
    assert code == 1 and "Stage: done." not in text


def test_a_new_job_still_reading_is_not_shown_the_old_jobs_systems(tmp_path, capsys):
    out, cache = tmp_path / "out", tmp_path / "cache"
    at = _finished(out, cache)
    _write(out / "11-1111 Ledger.json", {"job_name": "Invented B", "complete": False, "stopped_at": "scope"})
    _stamp(out / "11-1111 Ledger.json", at + 10_000_000_000)
    code, text = _code(out, cache, capsys)
    assert code == 1 and "Reading stopped at the scope pass" in text
    assert "Exhaust Fans" not in text


def test_a_half_written_newest_state_is_not_trusted(tmp_path, capsys):
    out, cache = tmp_path / "out", tmp_path / "cache"
    at = _finished(out, cache)
    (out / RUN_STATE).write_text('{"version": 1, "status": "do', encoding="utf-8")
    _stamp(out / RUN_STATE, at + 1)
    code, text = _code(out, cache, capsys)
    assert code == 1 and "Stage: done." not in text


def test_status_on_a_waiting_folder_creates_and_changes_nothing(tmp_path, capsys):
    out, cache = tmp_path / "out", tmp_path / "cache"
    _write(out / "00-0000 Ledger.json", {"job_name": "Invented A", "complete": True})
    _write(cache / "judge-chat" / "requests" / "q.json",
           {"kind": "qc_job", "step": "qc", "system": "the QC pass", "job": "Invented A",
            "answer_file": str(cache / "judge-chat" / "answers" / "q.json")})
    before = _snapshot(tmp_path)
    code, _ = _code(out, cache, capsys)
    assert code == 2 and _snapshot(tmp_path) == before
    code, _ = _code(tmp_path / "no such folder", cache, capsys)
    assert code == 1 and not (tmp_path / "no such folder").exists() and _snapshot(tmp_path) == before


# ---- review additions: the state write's own failures ------------------------------------------------------------

def test_a_read_only_out_folder_never_blocks_the_state_write(tmp_path, monkeypatch):
    """The temporary file itself cannot be written (a read-only folder): no exception, nothing left behind."""
    real = Path.write_text

    def read_only(self, *a, **k):
        if self.name.endswith(".tmp"):
            raise PermissionError(13, "Access is denied", str(self))
        return real(self, *a, **k)

    monkeypatch.setattr(Path, "write_text", read_only)
    run._save_run_state(tmp_path, run.RunResult("done", "done"))
    assert list(tmp_path.iterdir()) == []


def test_a_message_that_cannot_be_encoded_never_blocks_the_result(tmp_path):
    run._save_run_state(tmp_path, run.RunResult("waiting", "qc", messages=("Stopped: invented \ud800",)))
    assert not list(tmp_path.glob("*.tmp"))
