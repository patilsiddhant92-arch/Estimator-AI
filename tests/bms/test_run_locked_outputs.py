"""RUN-4: a locked output, a template or fit error, or a missing job folder ends the run as stopped, in plain words:
the run state is never left "running", status exits 1 naming the stop, and the command prints the stop and the
step it reached, never a traceback. Invented job only (test_run's fixture); no job text."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from bms import run
from bms.__main__ import main
from bms.status import RUN_STATE, check
from estimator.price_sheet.write import PriceSheetError

from test_run import _reach, answer_all, job_folder  # noqa: F401  (job_folder is a fixture)

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from run_job import stage_of  # noqa: E402


def _state(out: Path) -> dict:
    return json.loads((out / RUN_STATE).read_text(encoding="ascii"))


def _to_the_render(job_folder, out, cache):
    assert _reach(job_folder, out, cache, "qc").stage == "qc"
    assert answer_all(cache)


def test_a_locked_proposal_stops_the_run_naming_the_file(job_folder, tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out, cache = tmp_path / "out", tmp_path / "cache"
    _to_the_render(job_folder, out, cache)
    locked = out / "00-0000 Proposal.docx"

    def build(*_a, **_k):
        raise PermissionError(13, "Permission denied", str(locked))

    monkeypatch.setattr(run, "_build", build)
    with pytest.raises(PermissionError):
        run.estimate(job_folder, out, cache, "chat")
    state = _state(out)
    assert state["status"] != "running" and state["waiting"] == 0 and state["stage"] == "render"
    assert any(m.startswith("Stopped:") and locked.name in m and "close it" in m for m in state["messages"])
    found = check(out, cache)
    assert found.code == 1
    text = "\n".join(found.lines)
    assert locked.name in text and "may still" not in text


def test_the_command_prints_the_stop_and_its_step_with_no_traceback(job_folder, tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out, cache = tmp_path / "out", tmp_path / "cache"
    _to_the_render(job_folder, out, cache)

    def build(*_a, **_k):
        raise PermissionError(13, "Permission denied", str(out / "00-0000 Price Sheet.xlsx"))

    monkeypatch.setattr(run, "_build", build)
    capsys.readouterr()
    code = main(["estimate", str(job_folder), "--out", str(out), "--cache", str(cache)])
    text = capsys.readouterr().out
    assert code == 1
    assert "Stopped:" in text and "00-0000 Price Sheet.xlsx" in text and "Traceback" not in text
    assert "Stopped at the render step." in text and stage_of(text) == "render"


def test_a_job_that_does_not_fit_the_price_sheet_stops_in_words(job_folder, tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out, cache = tmp_path / "out", tmp_path / "cache"
    _to_the_render(job_folder, out, cache)

    def build(*_a, **_k):
        raise PriceSheetError("the job needs 11 price sheets; the template has 10")

    monkeypatch.setattr(run, "_build", build)
    capsys.readouterr()
    code = main(["estimate", str(job_folder), "--out", str(out), "--cache", str(cache)])
    text = capsys.readouterr().out
    assert code == 1 and "11 price sheets" in text and stage_of(text) == "render"
    assert _state(out)["status"] != "running" and check(out, cache).code == 1


def test_a_render_error_is_printed_on_the_console_with_its_step(job_folder, tmp_path, monkeypatch, capsys):
    from bms.render import RenderError
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out, cache = tmp_path / "out", tmp_path / "cache"
    _to_the_render(job_folder, out, cache)

    def broken(*_a, **_k):
        raise RenderError("an invented render problem")

    monkeypatch.setattr(run, "render", broken)
    capsys.readouterr()
    code = main(["estimate", str(job_folder), "--out", str(out), "--cache", str(cache)])
    text = capsys.readouterr().out
    assert code == 1 and "an invented render problem" in text and stage_of(text) == "render"


def test_a_missing_job_folder_stops_with_a_plain_line(tmp_path, capsys):
    out = tmp_path / "out"
    missing = tmp_path / "no such job"
    code = main(["estimate", str(missing), "--out", str(out)])
    text = capsys.readouterr().out
    assert code == 1
    assert "Stopped:" in text and "no such job" in text and "Traceback" not in text
    assert stage_of(text) == "read"
    assert _state(out)["status"] != "running" and check(out, out / ".cache").code == 1
