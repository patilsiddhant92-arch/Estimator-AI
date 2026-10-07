"""RUN-9: deleting both decisions.json and decisions history.json starts over: the run state's decision count goes
back to 0, so the first new save is a first save and no "no decisions history.json was found" note is printed.
Invented data only: the invented job folder of test_run.py."""
from __future__ import annotations

import json

from bms.review import DECISIONS_FILE, DECISIONS_HISTORY
from bms.status import RUN_STATE
from test_review_final import _cards, _decision, _drive
from test_run import job_folder  # noqa: F401  (a fixture)


def _decisions(out) -> int:
    return json.loads((out / RUN_STATE).read_text(encoding="ascii"))["decisions"]


def _save_accept(out) -> None:
    family = next(c for c in _cards(out) if c["level"] == "family")
    (out / DECISIONS_FILE).write_text(json.dumps([_decision(family, "accept")]), encoding="utf-8")


def test_deleting_both_decision_files_starts_the_count_over(job_folder, tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out, cache = tmp_path / "out", tmp_path / "cache"
    _drive(job_folder, out, cache, [])
    _save_accept(out)
    _drive(job_folder, out, cache, [])
    assert _decisions(out) == 1

    (out / DECISIONS_FILE).unlink()
    (out / DECISIONS_HISTORY).unlink()
    _drive(job_folder, out, cache, [])
    assert _decisions(out) == 0

    _save_accept(out)
    result = _drive(job_folder, out, cache, [])
    assert result.messages == ()
    assert _decisions(out) == 1
