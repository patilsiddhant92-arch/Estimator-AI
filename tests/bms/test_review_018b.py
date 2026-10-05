"""Review 018b (lead's reviewer): probes for the three earlier blockers and attacks on the decision post-check.
Invented fixture data only (tests/bms/fixtures/sample_job.json)."""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from bms import review
from bms.model import Count, Decision, Job

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def job() -> Job:
    return Job.from_dict(json.loads((FIXTURES / "sample_job.json").read_text(encoding="utf-8")))


def _ef(job, *devices):
    return job.with_system(dataclasses.replace(job.system("EF"), devices=tuple(devices)))


# ---- probes: the three earlier blockers --------------------------------------------------------------------------


def test_probe_revise_with_an_accept_and_no_job_does_not_raise(job, monkeypatch):
    """Blocker 1: `_revised` with accept decisions built a Job with the system as its name (IndexError)."""
    from bms import ai, run

    ef = job.system("EF")
    monkeypatch.setattr(ai, "revise_system", lambda system, *a, **k: dataclasses.replace(system, devices=tuple(
        dataclasses.replace(d, flag="quantity") if d.id == "EF.d1" else d for d in system.devices)))
    out = run._revised(ef, [], "", None, None, decisions=[Decision("EF", "accept", device_id="EF.d1")])
    assert out.key == "EF"
    assert next(d for d in out.devices if d.id == "EF.d1").flag == "none"


def test_probe_deleting_one_of_two_identical_lines_removes_the_one_named(job):
    """Blocker 2: `was` matches both twins; the named id must go and its twin stay (ids d2 and d3 here)."""
    ef = job.system("EF")
    first, twin_a = ef.devices[0], ef.devices[2]
    twin_b = dataclasses.replace(twin_a, id="EF.d4")
    dup = _ef(job, first, twin_a, twin_b)
    decision = Decision("EF", "delete", device_id="EF.d4", was=twin_b)
    applied = review.apply_decisions(dup, [decision])
    assert [d.id for d in applied.system("EF").devices] == ["EF.d1", "EF.d3"]
    assert review.unhonored_decisions(dup, [decision], applied) == []


def test_probe_a_stale_snapshot_never_falls_back_to_the_reused_id(job):
    """Blocker 3: the snapshot names a line no longer on the job; the id now belongs to a different line."""
    ef = job.system("EF")
    gone = dataclasses.replace(ef.devices[2], name="Gone line")
    for action, extra in (("delete", {}), ("accept", {}),
                          ("change", {"device": dataclasses.replace(ef.devices[0], name="Edited")})):
        decision = Decision("EF", action, device_id="EF.d1", was=gone, **extra)
        applied = review.apply_decisions(job, [decision])
        assert applied.system("EF").devices == ef.devices, action


# ---- attacks --------------------------------------------------------------------------------------------------------


def test_attack_a_delete_whose_snapshot_no_longer_matches_is_reported(job):
    """The page shows the revised job; the next run applies decisions to the first write. When the revise
    re-worded the line the estimator deleted, the delete cannot be applied. It must not vanish in silence:
    the line is still in the final job, so the review page has to say the decision was not honored."""
    ef = job.system("EF")
    revised_damper = dataclasses.replace(ef.devices[2], name="Motorized Damper Actuator (revised wording)")
    decision = Decision("EF", "delete", device_id="EF.d3", was=revised_damper)
    final = _ef(job, ef.devices[0], ef.devices[1], revised_damper)   # the cached revise brings it back
    assert review.apply_decisions(job, [decision]) == job            # nothing could be applied
    assert review.unhonored_decisions(job, [decision], final), "a lost delete must show on the review page"


def test_attack_a_change_with_a_snapshot_is_not_honored_when_the_line_is_dropped(job):
    """A change is honored only while the changed line is in the final job. With `was` set (every decision
    the page now saves) the check only asks whether the old line is gone, so dropping the line passes."""
    ef = job.system("EF")
    old = ef.devices[0]
    new = dataclasses.replace(old, quantity=Count(5, old.quantity.sources))
    decision = Decision("EF", "change", device_id=old.id, device=new, was=old)
    applied = review.apply_decisions(job, [decision])
    assert applied.system("EF").devices[0] == new
    assert review.unhonored_decisions(job, [decision], applied) == []
    dropped = _ef(job, *ef.devices[1:])
    assert review.unhonored_decisions(job, [decision], dropped), "the changed line is gone"


def test_attack_the_same_change_without_a_snapshot_is_caught(job):
    """Control for the attack above: the old id-only path does catch a dropped changed line."""
    ef = job.system("EF")
    old = ef.devices[0]
    new = dataclasses.replace(old, quantity=Count(5, old.quantity.sources))
    decision = Decision("EF", "change", device_id=old.id, device=new)
    assert review.unhonored_decisions(job, [decision], _ef(job, *ef.devices[1:]))


def test_qc_whole_system_finding_assertion_removed_by_the_branch_still_holds():
    """78b25bc removed this assertion from test_a_qc_must_fix_the_revise_left_as_it_was_stays_open."""
    from bms.model import Finding
    from bms.run import _untouched

    job = Job.from_dict(json.loads((FIXTURES / "sample_job.json").read_text(encoding="utf-8")))
    ef = job.system("EF")
    changed = job.with_system(dataclasses.replace(ef, devices=(dataclasses.replace(ef.devices[0], name="New"),
                                                               *ef.devices[1:])))
    on = lambda device=None, key="EF": Finding("Every line cites this job", key, device, "must_fix", "w", "f")
    assert not _untouched(on(None), job, changed) and _untouched(on(None, "RTU"), job, changed)
