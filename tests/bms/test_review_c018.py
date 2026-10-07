"""Review 018d (lead's reviewer of record) on lead/correct-018c c972c34: attacks on the decisions history
(`merge_decisions`), chained-edit rebasing and the silence rule. Invented data only: the sample fixture and the
invented job folder of test_run.py."""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from bms import review
from bms.model import Decision, Job, ModelError

from test_review_018c import _run_with_reworded, _save, _system
from test_run import _reach, job_folder  # noqa: F401  (job_folder is a fixture)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def job() -> Job:
    return Job.from_dict(json.loads((FIXTURES / "sample_job.json").read_text(encoding="utf-8")))


def _copies(job: Job, key: str, line) -> int:
    return sum(1 for d in job.system(key).devices if review._same_device((d,), line))


def _applied(job: Job, history) -> Job:
    return review.apply_decisions(job, [h.decision for h in history])


# ---- (1) the history: two identical lines across two saves -------------------------------------------------------


@pytest.mark.parametrize("second", ["accept", "delete"])
def test_attack_a_later_save_on_one_twin_does_not_undo_the_delete_of_the_other(job, second):
    """The writer wrote one line twice (EF.d1 and EF.d9). Round 1 deletes the copy EF.d9; run 2's page shows only
    EF.d1. Round 2 accepts (or deletes) EF.d1. Round 1's delete is about a different line and must stand."""
    ef = job.system("EF")
    x = ef.devices[0]
    twin = dataclasses.replace(x, id="EF.d9")
    doubled = job.with_system(dataclasses.replace(ef, devices=(*ef.devices, twin)))
    round1 = [Decision("EF", "delete", device_id="EF.d9", was=twin)]
    round2 = [Decision("EF", second, device_id=x.id, was=x)]
    history = review.merge_decisions(review.merge_decisions([], round1), round2)
    want = 1 if second == "accept" else 0
    assert _copies(_applied(doubled, history), "EF", x) == want, [h.decision for h in history]


# ---- (2) chained edits: the rebased decision keeps the replacement key of the line it no longer names ------------


def test_attack_a_newer_answer_on_the_line_a_rebased_delete_names_replaces_it(job):
    """Round 1 changes X to Y; round 2 deletes Y (kept as delete X). X comes back and its "not honored" card
    is on it; round 3 keeps it (accept X). The newest answer on the line must win: X stays."""
    x = job.system("EF").devices[0]
    y = dataclasses.replace(x, name="Controller, renamed")
    history = review.merge_decisions([], [Decision("EF", "change", device_id=x.id, was=x, device=y)])
    history = review.merge_decisions(history, [Decision("EF", "delete", device_id=x.id, was=y)])
    assert [h.decision.action for h in history] == ["delete"]
    assert history[0].decision.was == x                               # the precondition: rebased onto X
    history = review.merge_decisions(history, [Decision("EF", "accept", device_id=x.id, was=x)])
    assert _copies(_applied(job, history), "EF", x) == 1, [h.decision for h in history]


def test_guard_x_to_y_then_y_back_to_x_lands_as_x_with_no_card(job):
    x = job.system("EF").devices[0]
    y = dataclasses.replace(x, name="Controller, renamed")
    history = review.merge_decisions([], [Decision("EF", "change", device_id=x.id, was=x, device=y)])
    history = review.merge_decisions(history, [Decision("EF", "change", device_id=x.id, was=y, device=x)])
    decisions = [h.decision for h in history]
    after = review.apply_decisions(job, decisions)
    assert after == job
    assert review.unhonored_decisions(job, decisions, after) == []
    assert review.merge_decisions(history, [h.as_saved for h in history if h.round == 2]) == history


@pytest.mark.parametrize("text", ['[1]', '[{"round": 1}]', '{"decision": {}}',
                                  '[{"decision": {"system_key": "EF", "action": "delete"}, "round": null}]',
                                  '[{"decision": [], "round": 1}]'])
def test_guard_a_malformed_history_of_any_shape_is_refused_in_words(tmp_path, text):
    (tmp_path / review.DECISIONS_HISTORY).write_text(text, encoding="utf-8")
    with pytest.raises(ModelError, match="decisions history.json"):
        review.load_history(tmp_path)


# ---- (5) the silence rule -------------------------------------------------------------------------------------


def _dampers(result, key):
    system = result if isinstance(result, dict) else _system(result, key)
    return [d for d in system["devices"] if d["name"].startswith("Damper")]


def _two_saves_then_reword(job_folder, tmp_path, monkeypatch, first_decision):
    """Round 1 decides the reworded damper (run 2 applies it); round 2 accepts the controller; the revise then words
    the damper differently, as a re-asked AI may. Returns run 3."""
    out, cache, key, state, first = _run_with_reworded(
        job_folder, tmp_path, monkeypatch, ("Controller", "Start Stop", "Damper Actuator"), "Damper, motorized")
    (damper,) = _dampers(first, key)
    _save(out, {"system_key": key, "device_id": damper["id"], "was": damper, "reason": "x", **first_decision(damper)})
    second = _system(_reach(job_folder, out, cache, "done"), key)     # read now: run 3 rewrites Job.json
    controller = second["devices"][0]
    _save(out, {"system_key": key, "action": "accept", "device_id": controller["id"], "was": controller,
                "reason": "x"})
    state["wording"] = "Damper, motor driven"
    return key, second, _reach(job_folder, out, cache, "done")


def test_attack_a_deleted_line_the_revise_rewords_after_a_second_save_does_not_come_back_in_silence(
        job_folder, tmp_path, monkeypatch):
    key, second, third = _two_saves_then_reword(job_folder, tmp_path, monkeypatch, lambda d: {"action": "delete"})
    assert not _dampers(second, key)                                 # run 2 honored the delete
    back = _dampers(third, key)
    cards = [f for f in third.findings if f.rule == "decision not honored"]
    assert not back or cards, (back, third.findings)


def test_attack_a_changed_line_the_revise_rewords_after_a_second_save_is_not_lost_in_silence(
        job_folder, tmp_path, monkeypatch):
    key, second, third = _two_saves_then_reword(
        job_folder, tmp_path, monkeypatch,
        lambda d: {"action": "change", "device": dict(d, name="Damper, as the estimator wrote it", flag="none")})
    assert [d["name"] for d in _dampers(second, key)] == ["Damper, as the estimator wrote it"]
    names = [d["name"] for d in _dampers(third, key)]
    cards = [f for f in third.findings if f.rule == "decision not honored"]
    assert "Damper, as the estimator wrote it" in names or cards, (names, third.findings)
