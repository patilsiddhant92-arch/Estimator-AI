"""RUN-5: a device or family decision on a system (or a family) the job no longer has is a check saying it is not
applied, never skipped in silence and never a must_fix the estimator cannot clear; a system delete among the
decisions covers it (the estimator took the system out), and a delete has nothing left to do. Invented data only:
tests/bms/fixtures/sample_job.json."""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from bms import review
from bms.model import Decision, Job

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def job() -> Job:
    return Job.from_dict(json.loads((FIXTURES / "sample_job.json").read_text(encoding="utf-8")))


def _without(job: Job, key: str) -> Job:
    return dataclasses.replace(job, systems=tuple(s for s in job.systems if s.key != key))


def _rename(job: Job) -> Decision:
    line = job.system("EF").devices[0]
    return Decision("EF", "change", device_id=line.id, device=dataclasses.replace(line, name="Renamed Fan"),
                    was=line)


def test_a_device_decision_on_a_system_the_job_no_longer_has_is_a_check(job):
    decision = _rename(job)
    gone = _without(job, "EF")
    cards = review.unhonored_decisions(gone, [decision], gone)
    assert [(c.severity, c.what, c.system_key, c.device_id) for c in cards] == [
        ("check", f"this saved decision (change {decision.device_id}) is for the EF system, which this run no "
                  "longer has; it is not applied", "EF", None)]
    assert "merged or renamed" in cards[0].fix and cards[0].fix != review._GONE_OTHER


def test_a_family_decision_on_a_system_the_job_no_longer_has_is_a_check(job):
    family = job.system("EF").families[0]
    decision = Decision("EF", "change", family_name=family.name,
                        count=dataclasses.replace(family.count, value=7, others=()))
    gone = _without(job, "EF")
    cards = review.unhonored_decisions(gone, [decision], gone)
    assert [(c.severity, c.what) for c in cards] == [
        ("check", f"this saved decision (change {family.name}) is for the EF system, which this run no longer "
                  "has; it is not applied")]


def test_a_family_decision_on_a_family_the_system_no_longer_has_is_a_check(job):
    family = job.system("EF").families[0]
    decision = Decision("EF", "accept", family_name="Supply Fan")
    cards = review.unhonored_decisions(job, [decision], job)
    assert [(c.severity, c.what) for c in cards] == [
        ("check", "this saved decision (accept Supply Fan) is for the Supply Fan count of the EF system, which "
                  "this run no longer has; it is not applied")]
    assert family.name != "Supply Fan"


def test_a_delete_on_a_system_the_job_no_longer_has_makes_no_card(job):
    line = job.system("EF").devices[0]
    gone = _without(job, "EF")
    assert review.unhonored_decisions(gone, [Decision("EF", "delete", device_id=line.id, was=line)], gone) == []


def test_a_system_delete_in_the_history_covers_its_decisions(job):
    gone = _without(job, "EF")
    family = job.system("EF").families[0]
    decisions = [Decision("EF", "delete"), _rename(job),
                 Decision("EF", "accept", family_name=family.name)]
    assert review.unhonored_decisions(gone, decisions, gone) == []
