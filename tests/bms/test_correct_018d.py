"""CORRECT-018d (lead): the review of record's findings on the decisions history (REVIEW-018d F1 to F6). Each test
here fails on rebuild 7befe74. Invented data only: the sample fixture and the invented job folder of test_run.py."""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from bms import ai, review
from bms.model import Count, Decision, Job, ModelError, Ref

from test_ai import FakeClient, _bad, _Response, skeleton
from test_ai import dossier, playbook, raw  # noqa: F401  (fixtures)
from test_review_018c import _run_with_reworded, _save, _system
from test_run import _reach, job_folder  # noqa: F401  (job_folder is a fixture)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def job() -> Job:
    return Job.from_dict(json.loads((FIXTURES / "sample_job.json").read_text(encoding="utf-8")))


def _copies(job: Job, key: str, line) -> int:
    return sum(1 for d in job.system(key).devices if review._same_device((d,), line))


# ---- F1: twin lines are told apart by id ------------------------------------------------------------------------


def test_f1_with_the_written_job_twins_still_keep_both_decisions(job):
    """run.py passes the written job. Two lines of it have the content, so the id decides: round 2's accept of
    EF.d1 does not replace round 1's delete of its twin EF.d9."""
    ef = job.system("EF")
    x = ef.devices[0]
    twin = dataclasses.replace(x, id="EF.d9")
    doubled = job.with_system(dataclasses.replace(ef, devices=(*ef.devices, twin)))
    history = review.merge_decisions([], [Decision("EF", "delete", device_id="EF.d9", was=twin)], job=doubled)
    history = review.merge_decisions(history, [Decision("EF", "accept", device_id=x.id, was=x)], job=doubled)
    assert [h.decision.action for h in history] == ["delete", "accept"]
    assert _copies(review.apply_decisions(doubled, [h.decision for h in history]), "EF", x) == 1


# ---- F2 / F2b: the silence rule is for deletes only, and a system asked again gets a "check" card ----------------


def _dampers(result, key):
    system = result if isinstance(result, dict) else _system(result, key)
    return [d for d in system["devices"] if d["name"].startswith("Damper")]


def _two_saves(job_folder, tmp_path, monkeypatch, first_decision, wording="Damper, motor driven"):
    out, cache, key, state, first = _run_with_reworded(
        job_folder, tmp_path, monkeypatch, ("Controller", "Start Stop", "Damper Actuator"), "Damper, motorized")
    (damper,) = _dampers(first, key)
    _save(out, {"system_key": key, "device_id": damper["id"], "was": damper, "reason": "x", **first_decision(damper)})
    second = _system(_reach(job_folder, out, cache, "done"), key)     # read now: run 3 rewrites Job.json
    controller = second["devices"][0]
    _save(out, {"system_key": key, "action": "accept", "device_id": controller["id"], "was": controller,
                "reason": "x"})
    state["wording"] = wording
    return out, cache, key, damper, second, _reach(job_folder, out, cache, "done")


def test_f2_a_delete_whose_line_came_back_reworded_is_a_should_fix_check_card_on_the_system(
        job_folder, tmp_path, monkeypatch):
    out, cache, key, damper, second, third = _two_saves(job_folder, tmp_path, monkeypatch,
                                                         lambda d: {"action": "delete"})
    assert not _dampers(second, key)
    assert [d["name"] for d in _dampers(third, key)] == ["Damper, motor driven"]
    cards = [f for f in third.findings if f.rule == "decision not honored"]
    assert [(f.severity, f.device_id, f.what) for f in cards] == [
        ("should_fix", None, f"check this system: an earlier delete of {damper['name']} may have come back re-worded")]
    assert "may have come back re-worded" in third.review.read_text(encoding="utf-8")


def test_f2b_an_accept_whose_line_is_in_no_job_keeps_its_could_not_be_applied_card(job_folder, tmp_path,
                                                                                    monkeypatch):
    out, cache, key, damper, second, third = _two_saves(job_folder, tmp_path, monkeypatch,
                                                         lambda d: {"action": "accept"})
    cards = [(f.severity, f.what) for f in third.findings if f.rule == "decision not honored"]
    assert ("must_fix", f"decision could not be applied: accept {damper['id']}") in cards


# ---- F3: a newer answer replaces a rebased change too ---------------------------------------------------------------


def test_f3_a_delete_of_the_line_a_rebased_change_names_replaces_it(job):
    """Change X to Y, then Y to Z (kept as change X to Z). X comes back; round 3 deletes X. Only the delete is kept:
    neither X nor Z is in the job."""
    x = job.system("EF").devices[0]
    y = dataclasses.replace(x, name="Controller, renamed")
    z = dataclasses.replace(x, name="Controller, renamed again")
    history = review.merge_decisions([], [Decision("EF", "change", device_id=x.id, was=x, device=y)])
    history = review.merge_decisions(history, [Decision("EF", "change", device_id=x.id, was=y, device=z)])
    assert [(h.decision.action, h.decision.was) for h in history] == [("change", x)]
    history = review.merge_decisions(history, [Decision("EF", "delete", device_id=x.id, was=x)])
    assert [h.decision.action for h in history] == ["delete"]
    after = review.apply_decisions(job, [h.decision for h in history])
    assert _copies(after, "EF", x) == 0 and _copies(after, "EF", z) == 0


# ---- F5: a count change is scoped to its own family ---------------------------------------------------------------


@pytest.fixture
def two_families(job) -> Job:
    """VRF with its first line counted by the Indoor Unit family (S9) and its second by the Condensing Unit (S10)."""
    vrf = job.system("VRF")
    d1, d2, *rest = vrf.devices
    s9 = Ref("S9", "FCU-1 THRU FCU-4", "M-002, Drawings.pdf page 3")
    s10 = Ref("S10", "CU-1", "M-002, Drawings.pdf page 3")
    d1 = dataclasses.replace(d1, quantity=dataclasses.replace(d1.quantity, sources=(s9,)), flag="quantity")
    d2 = dataclasses.replace(d2, quantity=dataclasses.replace(d2.quantity, sources=(s10,)), flag="quantity")
    return job.with_system(dataclasses.replace(vrf, devices=(d1, d2, *rest)))


def test_f5_an_accept_stands_when_only_another_family_count_changed(two_families):
    from bms import run
    job = two_families
    d1, d2 = job.system("VRF").devices[:2]
    count = Decision("VRF", "change", family_name="Indoor Unit", count=Count(6))
    own = Decision("VRF", "accept", device_id=d1.id, was=d1)
    other = Decision("VRF", "accept", device_id=d2.id, was=d2)
    entries = [review.SavedDecision(count, 1), review.SavedDecision(own, 1), review.SavedDecision(other, 1)]
    assert run._standing_accepts(entries, "VRF", job) == [other]


def test_f5_the_honored_check_exempts_an_accept_of_an_unknown_family_when_any_count_changed(two_families):
    """VRF.d3 cites no family's count. A count change of a VRF family drops its accept (the rewrite flags the
    system again), so the honored check must not call the re-flagged line "not honored"."""
    job = two_families
    d3 = dataclasses.replace(job.system("VRF").devices[2], flag="quantity")
    job = job.with_system(dataclasses.replace(job.system("VRF"), devices=(*job.system("VRF").devices[:2], d3)))
    decisions = [Decision("VRF", "change", family_name="Indoor Unit", count=Count(6)),
                 Decision("VRF", "accept", device_id=d3.id, was=d3)]
    after = review.apply_decisions(job, decisions[:1])         # the rewrite: count changed, d3 flagged again
    assert review.unhonored_decisions(job, decisions, after) == []


def test_f5_the_honored_check_still_cards_a_reflagged_accept_whose_own_family_did_not_change(two_families):
    job = two_families
    d2 = job.system("VRF").devices[1]
    decisions = [Decision("VRF", "change", family_name="Indoor Unit", count=Count(6)),
                 Decision("VRF", "accept", device_id=d2.id, was=d2)]
    after = review.apply_decisions(job, decisions[:1])         # d2 left flagged: the accept was lost
    assert [f.what for f in review.unhonored_decisions(job, decisions, after)] == [
        f"decision not honored: accept {d2.id}"]
    # and the run keeps that accept, so it is applied again after the rewrite
    from bms import run
    entries = [review.SavedDecision(d, 1) for d in decisions]
    assert run._standing_accepts(entries, "VRF", job) == [decisions[1]]


# ---- F6: the history file ---------------------------------------------------------------------------------------------


def test_f6_a_torn_write_of_the_history_leaves_the_earlier_history_readable(job, tmp_path, monkeypatch):
    d1 = job.system("EF").devices[0]
    first = [review.SavedDecision(Decision("EF", "delete", device_id=d1.id, was=d1), 1, took_effect=True)]
    review.save_history(tmp_path, first)
    real = Path.write_text

    def torn(self, text, *args, **kwargs):
        real(self, text[: len(text) // 2], *args, **kwargs)
        raise OSError("disk full (invented)")
    monkeypatch.setattr(Path, "write_text", torn)
    with pytest.raises(ModelError):             # CORRECT-018f F4: the failed save stops in words
        review.save_history(tmp_path, [*first, review.SavedDecision(Decision("EF", "accept", device_id="EF.d2"), 2)])
    monkeypatch.setattr(Path, "write_text", real)
    assert review.load_history(tmp_path) == first


def test_f6_a_bad_history_names_only_the_history_and_what_deleting_it_loses(tmp_path):
    (tmp_path / review.DECISIONS_HISTORY).write_text("[{not json", encoding="utf-8")
    with pytest.raises(ModelError) as error:
        review.load_history(tmp_path)
    text = str(error.value)
    assert f"delete only {review.DECISIONS_HISTORY}" in text
    assert f"Delete it and {review.DECISIONS_FILE}" not in text
    assert "earlier saves are not applied" in text


def test_f6_a_run_without_a_history_says_so_in_one_line(job_folder, tmp_path, monkeypatch):
    out, cache, key, _state, first = _run_with_reworded(
        job_folder, tmp_path, monkeypatch, ("Controller", "Start Stop", "Damper Actuator"), "Damper, motorized")
    controller = _system(first, key)["devices"][0]
    _save(out, {"system_key": key, "action": "accept", "device_id": controller["id"], "was": controller,
                "reason": "x"})

    def notes() -> list[str]:
        """The note lines of every run until done (a run may stop to wait for answers first)."""
        from bms.run import estimate
        from test_run import answer_all
        seen: list[str] = []
        for _ in range(25):
            result = estimate(job_folder, out, cache, "chat")
            seen += [m for m in result.messages if review.DECISIONS_HISTORY in m]
            if result.status == "done":
                return seen
            assert answer_all(cache)
        raise AssertionError(result)
    assert len(notes()) == 1                                    # the first save: no history yet
    assert notes() == []                                        # the history is there now
    (out / review.DECISIONS_HISTORY).unlink()
    assert len(notes()) == 1                                    # the history deleted alone: said, not silent


# ---- F4: the API's refusal counter -------------------------------------------------------------------------------------


@pytest.mark.parametrize("fix", ["model", "rules"])
def test_f4_a_new_model_or_a_fixed_playbook_starts_a_new_count(job, raw, dossier, playbook, tmp_path, fix):
    system = skeleton(job.system("EF"))
    bad = _bad(raw, lambda a: a["devices"][0].update(slot="gadget"))
    client = FakeClient(*(_Response(json.dumps(bad)) for _ in range(3)), _Response(json.dumps(raw["systems"][1])))
    evidence = ai.evidence_for(system, dossier)
    for _ in range(2):
        with pytest.raises(ai.NoAnswer):
            ai.write_system(system, evidence, playbook, ai.ApiTransport(tmp_path, model="claude-test", client=client))
    assert len(client.calls) == 3
    with pytest.raises(ai.NoAnswer) as stopped:
        ai.write_system(system, evidence, playbook, ai.ApiTransport(tmp_path, model="claude-test", client=client))
    assert "A new prompt starts a new count" not in stopped.value.reason
    model = "claude-test-2" if fix == "model" else "claude-test"
    fixed = playbook if fix == "model" else dataclasses.replace(
        playbook, rules_text=playbook.rules_text + "\n\nAn invented fix to the rules.")
    ai.write_system(system, evidence, fixed, ai.ApiTransport(tmp_path, model=model, client=client))
    assert len(client.calls) == 4
