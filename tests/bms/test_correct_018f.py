"""CORRECT-018f (lead): the review of record's findings on the decisions history (REVIEW-018e F1 to F4). Each test
here fails on rebuild fc71a61. Invented data only: the sample fixture and the invented job folder of test_run.py."""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from bms import review
from bms.model import Count, Decision, Job, ModelError, Ref

from test_review_018c import _run_with_reworded, _save, _system
from test_run import _reach, job_folder  # noqa: F401  (job_folder is a fixture)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def job() -> Job:
    return Job.from_dict(json.loads((FIXTURES / "sample_job.json").read_text(encoding="utf-8")))


def _copies(job: Job, key: str, line) -> int:
    return sum(1 for d in job.system(key).devices if review._same_device((d,), line))


def _dampers(system: dict) -> list[dict]:
    return [d for d in system["devices"] if d["name"].startswith("Damper")]


# ---- F1: the system digest is saved only once every output is written -----------------------------------------------

def test_f1_a_run_that_crashes_at_the_last_output_keeps_the_old_digest(job_folder, tmp_path, monkeypatch):
    """Round 1 deletes the damper (run 2 honors it and settles the system). Round 2 accepts the controller and the
    revise words the damper again. Run 3 crashes while writing the proposal and price sheet (the last output): the
    history keeps the digests run 2 stored, so the next run still sees the system was asked again."""
    from bms import run
    out, cache, key, state, first = _run_with_reworded(
        job_folder, tmp_path, monkeypatch, ("Controller", "Start Stop", "Damper Actuator"), "Damper, motorized")
    (damper,) = _dampers(_system(first, key))
    _save(out, {"system_key": key, "action": "delete", "device_id": damper["id"], "was": damper, "reason": "x"})
    second = _system(_reach(job_folder, out, cache, "done"), key)
    settled = {entry.decision: entry.settled for entry in review.load_history(out)}
    assert all(settled.values())
    controller = second["devices"][0]
    _save(out, {"system_key": key, "action": "accept", "device_id": controller["id"], "was": controller,
                "reason": "x"})
    state["wording"] = "Damper, motor driven"

    def crash(*args, **kwargs):
        raise OSError("the proposal could not be written (invented)")
    monkeypatch.setattr(run, "_build", crash)
    with pytest.raises(OSError):
        _reach(job_folder, out, cache, "done")
    after = review.load_history(out)
    assert [entry.settled for entry in after if entry.decision in settled] == list(settled.values())
    assert [entry.settled for entry in after if entry.decision not in settled] == [None]


# ---- F2: an accept of a line citing two families -------------------------------------------------------------------

@pytest.fixture
def two_counts(job) -> Job:
    """VRF.d1's quantity cites both the Indoor Unit count (S9) and the Condensing Unit count (S10)."""
    vrf = job.system("VRF")
    d1, *rest = vrf.devices
    s9 = Ref("S9", "FCU-1 THRU FCU-4", "M-002, Drawings.pdf page 3")
    s10 = Ref("S10", "CU-1", "M-002, Drawings.pdf page 3")
    d1 = dataclasses.replace(d1, quantity=dataclasses.replace(d1.quantity, sources=(s9, s10)), flag="quantity")
    return job.with_system(dataclasses.replace(vrf, devices=(d1, *rest)))


def _second_family(job: Job, accept: Decision) -> str:
    cited = review.accept_family(job, accept)
    return next(name for name in ("Indoor Unit", "Condensing Unit") if name != cited)


def test_f2_the_honored_check_lets_a_count_change_of_either_cited_family_re_flag_an_accepted_line(two_counts):
    """The accept of VRF.d1 is honored when a count change of the second family it cites flags the line again:
    the estimator answers the new count, not the old accept."""
    d1 = two_counts.system("VRF").devices[0]
    accept = Decision("VRF", "accept", device_id=d1.id, was=d1)
    other = _second_family(two_counts, accept)
    vrf = two_counts.system("VRF")
    after = two_counts.with_system(dataclasses.replace(vrf, families=tuple(
        dataclasses.replace(f, count=Count(2)) if f.name == other else f for f in vrf.families)))
    assert after.system("VRF").devices[0].flag == "quantity"
    assert review.unhonored_decisions(two_counts, [accept], after) == []


def test_f2_the_revise_does_not_re_apply_an_accept_whose_second_family_count_changed(two_counts, monkeypatch):
    """`_revised` keeps the flag the revise raised on VRF.d1 when the same decisions change the count of the second
    family the line cites."""
    from bms import ai, run
    d1 = two_counts.system("VRF").devices[0]
    accept = Decision("VRF", "accept", device_id=d1.id, was=d1)
    count = Decision("VRF", "change", family_name=_second_family(two_counts, accept), count=Count(2))
    monkeypatch.setattr(ai, "revise_system", lambda system, *a, **kw: system)
    monkeypatch.setattr(run, "flag_written_devices", lambda system: system)
    revised = run._revised(two_counts.system("VRF"), [], "", None, None, two_counts, decisions=[count, accept])
    assert revised.devices[0].flag == "quantity"


# ---- F3: the delete of one twin never takes the only copy ------------------------------------------------------------

def _twins(job: Job) -> tuple[Job, Decision]:
    """EF.d1 written twice (EF.d1 and EF.d9); the estimator deletes EF.d9."""
    ef = job.system("EF")
    x = ef.devices[0]
    twins = job.with_system(dataclasses.replace(ef, devices=(*ef.devices, dataclasses.replace(x, id="EF.d9"))))
    return twins, Decision("EF", "delete", device_id="EF.d9", was=x)


def test_f3_the_history_keeps_how_many_copies_the_estimator_saw(job, tmp_path):
    twins, delete = _twins(job)
    (entry,) = review.merge_decisions([], [delete], job=twins)
    assert entry.copies == 2
    review.save_history(tmp_path, [entry])
    assert review.load_history(tmp_path) == [entry]


def test_f3_a_twin_delete_on_a_job_with_one_copy_left_is_not_applied_and_gets_a_card(job):
    """Seen: two copies. A later write writes the line once (no EF.d9). The delete is not applied by content: the
    copy stays, and a must_fix "could not be applied" card sits on it."""
    twins, delete = _twins(job)
    history = review.merge_decisions([], [delete], job=twins)
    copies = review.copies_seen(history)
    x = delete.was
    after = review.apply_decisions(job, [delete], copies=copies)
    assert _copies(after, "EF", x) == 1
    cards = review.unhonored_decisions(job, [delete], after, copies=copies)
    assert [(c.severity, c.what, c.device_id) for c in cards] == [
        ("must_fix", "decision could not be applied: delete EF.d9", job.system("EF").devices[0].id)]


def test_f3_a_twin_delete_whose_id_now_holds_another_line_is_not_applied_by_content(job):
    """Seen: two copies (EF.d1, EF.d2). A later write writes the line once and EF.d2 is now another line. The
    delete matches no line by id and content and one copy is left: nothing is deleted."""
    ef = job.system("EF")
    x, y = ef.devices[0], ef.devices[1]
    twins = job.with_system(dataclasses.replace(ef, devices=(x, dataclasses.replace(x, id="EF.d2"),
                                                             *(dataclasses.replace(d, id=f"EF.d{n}")
                                                               for n, d in enumerate(ef.devices[1:], start=3)))))
    delete = Decision("EF", "delete", device_id="EF.d2", was=x)
    copies = review.copies_seen(review.merge_decisions([], [delete], job=twins))
    assert y.id == "EF.d2" and not review._same_device((y,), x)
    after = review.apply_decisions(job, [delete], copies=copies)
    assert after == job
    assert review.unhonored_decisions(job, [delete], after, copies=copies)[0].what == (
        "decision could not be applied: delete EF.d2")


# ---- F4: a history held by another program stops the run in words ---------------------------------------------------

def _refuse(monkeypatch):
    def refuse(src, dst):
        raise PermissionError(13, "Access is denied (invented)", str(dst))
    monkeypatch.setattr(review.os, "replace", refuse)


def test_f4_save_history_that_cannot_swap_the_file_names_it_and_leaves_no_temporary_file(job, tmp_path,
                                                                                           monkeypatch):
    d1 = job.system("EF").devices[0]
    first = [review.SavedDecision(Decision("EF", "delete", device_id=d1.id, was=d1), 1, took_effect=True)]
    review.save_history(tmp_path, first)
    _refuse(monkeypatch)
    with pytest.raises(ModelError) as failed:
        review.save_history(tmp_path, [*first, review.SavedDecision(Decision("EF", "accept", device_id="EF.d2"), 2)])
    assert review.DECISIONS_HISTORY in str(failed.value) and "close" in str(failed.value).lower()
    assert sorted(p.name for p in tmp_path.iterdir()) == [review.DECISIONS_HISTORY]
    monkeypatch.undo()
    assert review.load_history(tmp_path) == first


def test_f4_a_run_whose_history_cannot_be_saved_stops_in_plain_words(job_folder, tmp_path, monkeypatch):
    """The estimator's save comes in while another program holds decisions history.json: the run stops with a
    message naming the file, no traceback, and no 'decisions history.json.tmp' is left in the folder."""
    from bms import run
    out, cache, key, _state, first = _run_with_reworded(
        job_folder, tmp_path, monkeypatch, ("Controller", "Start Stop", "Damper Actuator"), "Damper, motorized")
    (damper,) = _dampers(_system(first, key))
    _save(out, {"system_key": key, "action": "delete", "device_id": damper["id"], "was": damper, "reason": "x"})
    _refuse(monkeypatch)
    result = run.estimate(job_folder, out, cache, "chat")
    assert result.status == "waiting"
    assert any(m.startswith("Stopped:") and review.DECISIONS_HISTORY in m for m in result.messages)
    assert not list(out.glob("*.tmp"))
