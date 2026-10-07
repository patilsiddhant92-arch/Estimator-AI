"""RUN-12: a state file held open for a moment is written on a retry; the running state always names a stage; a
decisions file that cannot be read stops with plain words. Invented data only."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from bms import run, status
from bms.model import ModelError
from bms.review import DECISIONS_FILE, DECISIONS_HISTORY, load_decisions, load_history
from bms.status import RUN_STATE


def _no_wait(monkeypatch):
    monkeypatch.setattr(run.time, "sleep", lambda s: None)


def test_a_state_swap_refused_twice_is_written_on_the_third_try(tmp_path, monkeypatch):
    _no_wait(monkeypatch)
    real, calls = run.os.replace, []

    def flaky(src, dst):
        calls.append(1)
        if len(calls) <= 2:
            raise PermissionError("held open")
        return real(src, dst)

    monkeypatch.setattr(run.os, "replace", flaky)
    run._write_run_state(tmp_path, {"version": 1, "status": "running", "stage": "read"})
    assert len(calls) == 3
    assert json.loads((tmp_path / RUN_STATE).read_text(encoding="ascii"))["stage"] == "read"
    assert not (tmp_path / (RUN_STATE + ".tmp")).exists()


def test_a_state_swap_always_refused_is_let_go_and_leaves_no_temporary_file(tmp_path, monkeypatch):
    _no_wait(monkeypatch)
    calls = []

    def locked(src, dst):
        calls.append(1)
        raise PermissionError("held open")

    monkeypatch.setattr(run.os, "replace", locked)
    run._write_run_state(tmp_path, {"version": 1, "status": "running", "stage": "read"})
    assert len(calls) == 5
    assert not (tmp_path / RUN_STATE).exists()
    assert not (tmp_path / (RUN_STATE + ".tmp")).exists()


def test_the_running_state_always_names_a_stage(tmp_path):
    run._save_running(tmp_path)
    assert json.loads((tmp_path / RUN_STATE).read_text(encoding="ascii"))["stage"] == "read"


def test_status_reads_a_state_file_that_is_whole_on_the_second_look(tmp_path, monkeypatch):
    monkeypatch.setattr(status.time, "sleep", lambda s: None)
    path = tmp_path / RUN_STATE
    path.write_text("{}", encoding="ascii")
    real, calls = Path.read_bytes, []

    def flaky(self):
        if self == path and not calls:
            calls.append(1)
            raise PermissionError("held open")
        return real(self)

    monkeypatch.setattr(Path, "read_bytes", flaky)
    assert status._dict(path) == ({}, "")
    assert calls


@pytest.mark.parametrize("name, load", [(DECISIONS_FILE, load_decisions), (DECISIONS_HISTORY, load_history)])
def test_a_decisions_file_that_cannot_be_opened_stops_in_plain_words(tmp_path, monkeypatch, name, load):
    (tmp_path / name).write_text("[]", encoding="utf-8")
    real = Path.read_text

    def locked(self, *a, **k):
        if self.name == name:
            raise PermissionError("held open")
        return real(self, *a, **k)

    monkeypatch.setattr(Path, "read_text", locked)
    with pytest.raises(ModelError) as caught:
        load(tmp_path)
    assert f"could not read {name}: close it if it is open and run again" in str(caught.value)
