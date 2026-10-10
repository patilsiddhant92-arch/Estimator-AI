"""Review 018c (lead's reviewer of record) on lead/correct-018b: attacks on the decision lifecycle, the late apply
after the revise, and the "decision could not be applied" card. Invented data only: the sample fixture and the
invented job folder of test_run.py."""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from bms import review
from bms.model import Decision, Job

from test_run import _plant, _reach, job_folder  # noqa: F401  (job_folder is a fixture)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def job() -> Job:
    return Job.from_dict(json.loads((FIXTURES / "sample_job.json").read_text(encoding="utf-8")))


# ---- unit level: the "could not be applied" card -------------------------------------------------------------------



def test_attack_a_card_that_could_not_be_applied_never_sits_on_an_unrelated_line(job):
    """The deleted line is in no job any more and its old id EF.d1 now belongs to a different line. The card must
    not be a device question on that different line: its Delete button would delete the wrong line."""
    ef = job.system("EF")
    gone = dataclasses.replace(ef.devices[0], name="A line no run writes any more")
    decision = Decision("EF", "delete", device_id="EF.d1", was=gone)
    findings = review.unhonored_decisions(job, [decision], job)
    unrelated = next(d for d in ef.devices if d.id == "EF.d1")
    assert not _same(unrelated, gone)                                  # the precondition: d1 is another line
    assert all(f.device_id != "EF.d1" for f in findings), findings



def test_attack_an_accept_does_not_survive_a_count_change_in_the_same_run(job, monkeypatch):
    """The same saved file changes a family's count and accepts a device's quantity flag. The count change
    re-flags the device; the revise must not clear that new flag with the old accept."""
    from bms import ai, run

    ef = job.system("EF")
    family = ef.families[0]
    shown = dataclasses.replace(ef.devices[0], flag="quantity")
    decisions = [Decision("EF", "change", family_name=family.name,
                          count=dataclasses.replace(family.count, value=(family.count.value or 0) + 3)),
                 Decision("EF", "accept", device_id=shown.id, was=shown)]
    monkeypatch.setattr(ai, "revise_system", lambda system, *a, **k: system)
    monkeypatch.setattr(run, "flag_written_devices", lambda system: dataclasses.replace(system, devices=tuple(
        dataclasses.replace(d, flag="quantity") for d in system.devices)))
    out = run._revised(ef, [], "", None, None, decisions=decisions)
    assert next(d for d in out.devices if d.id == shown.id).flag == "quantity"


def _same(a, b) -> bool:
    return review._same_device((a,), b)


# ---- run level -----------------------------------------------------------------------------------------------------


def _run_with_reworded(job_folder, tmp_path, monkeypatch, names, words):
    """Runs to done where a must_fix makes the revise re-word every "Damper Actuator" line to words[run], run being
    the number of revise calls so far that saw a damper (so a later run can word it differently).
    Returns (out, cache, key, state) where state["wording"] can be changed between runs."""
    from bms import ai, run
    from bms.model import Finding

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out, cache = tmp_path / "out", tmp_path / "cache"
    assert _reach(job_folder, out, cache, "write").stage == "write"
    requests = sorted((cache / "judge-chat" / "requests").glob("*.json"))
    key = json.loads(requests[0].read_text(encoding="utf-8"))["plan_key"]
    _plant(cache, {key: names})
    real_validate = run.validate
    monkeypatch.setattr(run, "validate", lambda job, playbook: [*real_validate(job, playbook), Finding(
        "Every line cites this job", key, None, "must_fix", "invented must_fix", "invented fix")])
    state = {"wording": words, "add_back": False}

    def revise(system, findings, evidence, playbook, transport, **kw):
        devices = tuple(dataclasses.replace(d, name=state["wording"]) if d.name == "Damper Actuator" else d
                        for d in system.devices)
        if state["add_back"] and not any(d.name.startswith("Damper") for d in devices):
            devices = (*devices, dataclasses.replace(devices[-1], id=f"{system.key}.d9", name="Damper Actuator"))
        return dataclasses.replace(system, devices=devices)
    monkeypatch.setattr(ai, "revise_system", revise)
    first = _reach(job_folder, out, cache, "done")
    assert first.status == "done"
    return out, cache, key, state, first


def _system(result, key):
    return next(s for s in json.loads(result.job_file.read_text(encoding="utf-8"))["systems"] if s["key"] == key)


def _save(out, *decisions):
    (out / "decisions.json").write_text(json.dumps(list(decisions)), encoding="utf-8")


def test_guard_a_late_delete_of_one_of_two_identical_lines_removes_only_the_one_named(job_folder, tmp_path,
                                                                                         monkeypatch):
    """The revise words two damper lines the same. The estimator deletes the second one on the page. The late
    apply removes exactly that one, once, and keeps its twin under its own id."""
    out, cache, key, _state, first = _run_with_reworded(
        job_folder, tmp_path, monkeypatch, ("Controller", "Damper Actuator", "Damper Actuator"), "Damper, motorized")
    shown = _system(first, key)["devices"]
    twins = [d for d in shown if d["name"] == "Damper, motorized"]
    assert len(twins) == 2
    _save(out, {"system_key": key, "action": "delete", "device_id": twins[1]["id"], "was": twins[1],
                "reason": "invented"})
    again = _reach(job_folder, out, cache, "done")
    assert again.status == "done"
    final = _system(again, key)["devices"]
    assert [(d["id"], d["name"]) for d in final] == [(shown[0]["id"], "Controller"), (twins[0]["id"], "Damper, motorized")]
    assert not [f for f in again.findings if f.rule == "decision not honored"]


def test_guard_a_late_delete_when_the_revise_words_it_differently_is_shown_on_the_page(
        job_folder, tmp_path, monkeypatch):
    """QC and the revise are asked again and word the damper differently. The delete cannot be applied; the card
    says so on the review page. (The fake revise keeps ids, so this passes through the old-id fallback too.)"""
    out, cache, key, state, first = _run_with_reworded(
        job_folder, tmp_path, monkeypatch, ("Controller", "Start Stop", "Damper Actuator"), "Damper, motorized")
    damper = next(d for d in _system(first, key)["devices"] if d["name"] == "Damper, motorized")
    _save(out, {"system_key": key, "action": "delete", "device_id": damper["id"], "was": damper,
                "reason": "invented"})
    state["wording"] = "Damper, motor driven"
    again = _reach(job_folder, out, cache, "done")
    final = _system(again, key)["devices"]
    now = next(d for d in final if d["name"] == "Damper, motor driven")
    cards = [f for f in again.findings if f.rule == "decision not honored"]
    assert [f.what for f in cards] == [f"decision could not be applied: delete {damper['id']}"]
    assert cards[0].device_id in (None, now["id"])     # never on some other line
    assert "decision could not be applied" in again.review.read_text(encoding="utf-8")


def test_guard_an_early_delete_the_revise_brings_back_is_reported_once(job_folder, tmp_path, monkeypatch):
    """The delete matches the first write and is applied early. The revise puts the damper back word for word.
    RUN-1 (audit 2026-10-09): the estimator's delete is applied again after the revise, by the saved line, as after
    the count rewrite, so the damper stays deleted and no "decision not honored" card is raised (the old behaviour
    reported the run's own undo on every run)."""
    out, cache, key, state, first = _run_with_reworded(
        job_folder, tmp_path, monkeypatch, ("Controller", "Start Stop", "Damper Actuator"), "Damper Actuator")
    damper = next(d for d in _system(first, key)["devices"] if d["name"] == "Damper Actuator")
    _save(out, {"system_key": key, "action": "delete", "device_id": damper["id"], "was": damper,
                "reason": "invented"})
    state["add_back"] = True
    again = _reach(job_folder, out, cache, "done")
    final = _system(again, key)["devices"]
    assert [d for d in final if d["name"] == "Damper Actuator"] == []
    assert [f for f in again.findings if f.rule == "decision not honored"] == []



def test_attack_a_second_save_from_the_page_does_not_bring_a_deleted_line_back_in_silence(job_folder, tmp_path,
                                                                                            monkeypatch):
    """Run 1, the page saves a delete of the reworded damper; run 2 removes it. On run 2's page the estimator
    answers one other question and saves again, as the page says to (it overwrites decisions.json). Run 3 must
    not put the damper back without a word."""
    out, cache, key, _state, first = _run_with_reworded(
        job_folder, tmp_path, monkeypatch, ("Controller", "Start Stop", "Damper Actuator"), "Damper, motorized")
    damper = next(d for d in _system(first, key)["devices"] if d["name"] == "Damper, motorized")
    _save(out, {"system_key": key, "action": "delete", "device_id": damper["id"], "was": damper,
                "reason": "invented"})
    second = _reach(job_folder, out, cache, "done")
    assert not any(d["name"].startswith("Damper") for d in _system(second, key)["devices"])   # run 2 honored it
    controller = _system(second, key)["devices"][0]
    _save(out, {"system_key": key, "action": "accept", "device_id": controller["id"], "was": controller,
                "reason": "invented"})
    third = _reach(job_folder, out, cache, "done")
    back = any(d["name"].startswith("Damper") for d in _system(third, key)["devices"])
    assert not back or [f for f in third.findings if f.rule == "decision not honored"]
