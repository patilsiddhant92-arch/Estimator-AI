"""CORRECT-018c (lead): the decisions work finished. Each test here fails on b664d93. Invented data only: the
sample fixture and the invented job folder of test_run.py."""
from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path

import pytest

from bms import review
from bms.model import Count, Decision, Job

from test_review_018c import _run_with_reworded, _save, _system
from test_run import _reach, job_folder  # noqa: F401  (job_folder is a fixture)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def job() -> Job:
    return Job.from_dict(json.loads((FIXTURES / "sample_job.json").read_text(encoding="utf-8")))


def _question_html(page: str, text: str) -> str:
    """The one question block on the page whose text holds `text`."""
    blocks = re.split(r'(?=<div class="q[ "])', page)
    (block,) = [b for b in blocks if text in b]
    return block


# ---- (1) and (8): the "could not be applied" card ------------------------------------------------------------------


def test_a_card_that_could_not_be_applied_sits_at_system_level_with_no_delete_button(job, tmp_path):
    """No line has the saved content: the card is about the system, with no device buttons and no
    "Delete this system" (a Delete there would remove the whole system, not the line)."""
    gone = dataclasses.replace(job.system("EF").devices[0], name="A line no run writes any more")
    findings = review.unhonored_decisions(job, [Decision("EF", "delete", device_id="EF.d1", was=gone)], job)
    assert [(f.device_id, f.severity) for f in findings] == [(None, "must_fix")]
    block = _question_html(review.review_page(job, findings, tmp_path).read_text(encoding="utf-8"),
                           "decision could not be applied")
    assert 'data-act="delete"' not in block
    assert '"device_id": null' in block


def test_a_delete_whose_line_is_gone_from_every_job_says_it_may_have_been_removed_or_reworded(job):
    gone = dataclasses.replace(job.system("EF").devices[0], name="A line no run writes any more")
    (finding,) = review.unhonored_decisions(job, [Decision("EF", "delete", device_id="EF.d1", was=gone)], job)
    assert finding.severity == "must_fix"
    assert finding.what == "decision could not be applied: delete EF.d1"
    assert "may have been removed or re-worded" in finding.fix


# ---- (6): the "not honored" card is on the line that came back, also with twins --------------------------------------


def test_the_not_honored_card_with_twins_sits_on_the_copy_the_decision_did_not_keep(job):
    """Two identical lines, one deleted; the writer returns two copies again. The card is on the copy that is
    not the twin the estimator kept (EF.d9), so a Delete on the card removes the extra copy."""
    system = job.system("EF")
    first = system.devices[0]
    doubled = job.with_system(dataclasses.replace(system, devices=(*system.devices, dataclasses.replace(
        first, id="EF.d9"))))
    after = job.with_system(dataclasses.replace(system, devices=(
        dataclasses.replace(first, id="EF.d9"), *system.devices[1:], dataclasses.replace(first, id="EF.d12"))))
    findings = review.unhonored_decisions(doubled, [Decision("EF", "delete", device_id=first.id)], after)
    assert [(f.what, f.device_id) for f in findings] == [(f"decision not honored: delete {first.id}", "EF.d12")]


# ---- (3): an accept and a count change from the same save ------------------------------------------------------------


def test_only_an_accept_saved_after_the_count_change_stands_once_the_count_is_rewritten():
    from bms import run

    count = Decision("EF", "change", family_name="Exhaust Fans", count=Count(5))
    same_save = Decision("EF", "accept", device_id="EF.d1")
    later_save = Decision("EF", "accept", device_id="EF.d2")
    other = Decision("CUH", "accept", device_id="CUH.d1")
    entries = [review.SavedDecision(count, 1), review.SavedDecision(same_save, 1),
               review.SavedDecision(later_save, 2), review.SavedDecision(other, 1)]
    assert run._standing_accepts(entries, "EF") == [later_save]
    assert run._standing_accepts(entries, "CUH") == [other]


# ---- (2): decisions accumulate across saves ---------------------------------------------------------------------------


def test_reading_the_same_file_again_adds_no_round_and_a_new_save_wins_per_line(job):
    ef = job.system("EF")
    d1, d2 = ef.devices[0], ef.devices[1]
    first = [Decision("EF", "delete", device_id=d1.id, was=d1), Decision("EF", "accept", device_id=d2.id, was=d2)]
    history = review.merge_decisions([], first)
    assert [(h.decision, h.round) for h in history] == [(first[0], 1), (first[1], 1)]
    assert review.merge_decisions(history, first) == history                      # a plain re-run
    second = [Decision("EF", "delete", device_id="EF.d1", was=d2)]                 # same line as the accept
    merged = review.merge_decisions(history, second)
    assert [(h.decision, h.round) for h in merged] == [(first[0], 1), (second[0], 2)]
    assert review.merge_decisions(merged, []) == merged                            # no file: the history stands


def test_two_decisions_on_one_line_in_one_save_are_both_kept(job):
    old = job.system("EF").devices[0]
    both = [Decision("EF", "change", device_id=old.id, was=old, device=dataclasses.replace(old, name="Changed")),
            Decision("EF", "delete", device_id=old.id, was=old)]
    assert [h.decision for h in review.merge_decisions([], both)] == both


def test_the_history_round_trips_and_a_malformed_one_is_refused_in_words(job, tmp_path):
    d1 = job.system("EF").devices[0]
    entries = [review.SavedDecision(Decision("EF", "delete", device_id=d1.id, was=d1), 1, took_effect=True)]
    review.save_history(tmp_path, entries)
    assert review.load_history(tmp_path) == entries
    out = tmp_path / "out"
    out.mkdir()
    (out / review.DECISIONS_HISTORY).write_text("[{not json", encoding="utf-8")
    with pytest.raises(review.ModelError, match=re.escape(review.DECISIONS_HISTORY)):
        review.load_history(out)


def _damper(result, key, prefix="Damper"):
    return [d for d in _system(result, key)["devices"] if d["name"].startswith(prefix)]


def test_a_carried_delete_that_took_effect_stays_silent_when_its_line_is_gone(job_folder, tmp_path, monkeypatch):
    """Run 2 honored the delete. On run 3 the revise drops the damper, so no job has the saved line: the carried
    delete took effect before, so it makes no "could not be applied" card."""
    from bms import ai
    out, cache, key, _state, first = _run_with_reworded(
        job_folder, tmp_path, monkeypatch, ("Controller", "Start Stop", "Damper Actuator"), "Damper, motorized")
    (damper,) = _damper(first, key)
    _save(out, {"system_key": key, "action": "delete", "device_id": damper["id"], "was": damper, "reason": "x"})
    second = _reach(job_folder, out, cache, "done")
    assert not _damper(second, key)
    controller = _system(second, key)["devices"][0]
    _save(out, {"system_key": key, "action": "accept", "device_id": controller["id"], "was": controller,
                "reason": "x"})
    real = ai.revise_system
    monkeypatch.setattr(ai, "revise_system", lambda system, *a, **k: dataclasses.replace(
        real(system, *a, **k), devices=tuple(d for d in real(system, *a, **k).devices
                                             if not d.name.startswith("Damper"))))
    third = _reach(job_folder, out, cache, "done")
    assert not _damper(third, key)
    assert not [f for f in third.findings if f.rule == "decision not honored"]
    history = json.loads((out / review.DECISIONS_HISTORY).read_text(encoding="utf-8"))
    assert [(h["round"], h["decision"]["action"]) for h in history] == [(1, "delete"), (2, "accept")]


def test_a_carried_decision_that_never_took_effect_keeps_its_card(job_folder, tmp_path, monkeypatch):
    out, cache, key, _state, first = _run_with_reworded(
        job_folder, tmp_path, monkeypatch, ("Controller", "Start Stop", "Damper Actuator"), "Damper, motorized")
    (damper,) = _damper(first, key)
    ghost = dict(damper, name="A line no run writes any more")
    _save(out, {"system_key": key, "action": "delete", "device_id": damper["id"], "was": ghost, "reason": "x"})
    second = _reach(job_folder, out, cache, "done")
    cards = [f.what for f in second.findings if f.rule == "decision not honored"]
    assert cards == [f"decision could not be applied: delete {damper['id']}"]
    controller = _system(second, key)["devices"][0]
    _save(out, {"system_key": key, "action": "accept", "device_id": controller["id"], "was": controller,
                "reason": "x"})
    third = _reach(job_folder, out, cache, "done")
    assert [f.what for f in third.findings if f.rule == "decision not honored"] == cards


def test_the_page_says_earlier_decisions_are_kept(job, tmp_path):
    page = review.review_page(job, [], tmp_path).read_text(encoding="utf-8")
    assert "Decisions saved earlier are kept" in page
