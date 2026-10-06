"""lead/final-c (2) and (3). Invented data only: the sample fixture and the invented job folder of test_run.py.

(2) A page Change sets a line's name, quantity and verb/parties (Literal fields, never free text); decisions.json is
    a file a person can edit, so its device can carry any assumption too. Every client text of the changed line
    (name, assumption what and why) goes through the shared detector: one that prints an issued id gets the
    "your change prints a source id" card and is not handed to the revise, which would write the line back.
    A Decision has no clarification field: no Change can set one.
(3) A run that finds a decisions history but no decisions.json still applies the history; it says so in one plain
    line, and what starting over takes (delete both files)."""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from bms import run
from bms.model import Assumption, Decision, Job

from test_review_final import _cards, _decision, _drive
from test_run import job_folder  # noqa: F401  (job_folder is a fixture)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def sample_job() -> Job:
    return Job.from_dict(json.loads((FIXTURES / "sample_job.json").read_text(encoding="utf-8")))


def _changed(job: Job, **fields) -> tuple[Job, Decision]:
    system = job.system("EF")
    device = dataclasses.replace(system.devices[0], flag="none", **fields)
    decision = Decision("EF", "change", device.id, device=device, was=system.devices[0])
    return job.with_system(dataclasses.replace(system, devices=(device,) + system.devices[1:])), decision


@pytest.mark.parametrize("assumption", [Assumption("one per fan", "the sequence, see S6"),
                                        Assumption("one per fan per S6", "the sequence says so")])
def test_a_change_whose_assumption_prints_an_issued_id_gets_the_card(sample_job, assumption):
    job, decision = _changed(sample_job, assumption=assumption)
    assert run._ids_in_changes(job, [decision]) == [(decision, "EF.d1", ("S6",))]


def test_a_change_whose_name_prints_an_issued_id_still_gets_the_card(sample_job):
    job, decision = _changed(sample_job, name="DDC Controller per S6")
    assert run._ids_in_changes(job, [decision]) == [(decision, "EF.d1", ("S6",))]


def test_a_clean_change_gets_no_card(sample_job):
    job, decision = _changed(sample_job, name="DDC Controller, wall mounted",
                             assumption=Assumption("one per fan", "the sequence says so"))
    assert run._ids_in_changes(job, [decision]) == []


def test_a_decision_has_no_clarification_field():
    assert not [f for f in dataclasses.fields(Decision) if "clarification" in f.name]


# ---- (3) starting over ------------------------------------------------------------------------------------------

START_OVER = "to start over, delete both decisions.json and decisions history.json"


def test_a_history_without_decisions_json_says_it_still_applies_and_how_to_start_over(job_folder, tmp_path,
                                                                                    monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out, cache = tmp_path / "out", tmp_path / "cache"
    _drive(job_folder, out, cache, [])
    sensor = next(c for c in _cards(out) if c["level"] == "device")
    (out / "decisions.json").write_text(json.dumps([_decision(sensor, "accept")]), encoding="utf-8")
    second = run.estimate(job_folder, out, cache, "chat")
    assert (out / "decisions history.json").is_file()
    assert not [m for m in second.messages if START_OVER in m], second.messages
    (out / "decisions.json").unlink()
    third = run.estimate(job_folder, out, cache, "chat")
    notes = [m for m in third.messages if START_OVER in m]
    assert len(notes) == 1 and "\n" not in notes[0], third.messages
    assert "still applied" in notes[0] and "1 decision" in notes[0], notes


def test_no_history_and_no_decisions_json_says_nothing_about_starting_over(job_folder, tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out, cache = tmp_path / "out", tmp_path / "cache"
    first = _drive(job_folder, out, cache, [])
    assert not [m for m in first.messages if START_OVER in m], first.messages
