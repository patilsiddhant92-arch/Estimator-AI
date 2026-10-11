"""ws5, HP 17, through the whole run (chat mode, an invented job): a must_fix finding about a block's count reaches the
revise, the revise corrects the count from the evidence, and the final job carries the corrected count with every
earlier count still named. The estimator's own count is never changed by the revise."""
from __future__ import annotations

import dataclasses
import json

import pytest

import test_run
from bms import run
from bms.model import Finding, Job
from test_run import _evidence_ref, _reach, job_folder  # noqa: F401  (job_folder is a fixture)

NEW_COUNT = 9


def _revise_answer(request: dict) -> dict:
    """The block as the revise was given it, with its first family's count corrected to NEW_COUNT, citing the first
    source of the evidence."""
    prompt = request["prompt"]
    block = json.loads(prompt.split("The block as written:\n", 1)[1].split("\n\nThe findings", 1)[0])
    block["families"][0]["count"] = {"value": NEW_COUNT, "sources": [_evidence_ref(prompt)], "others": [],
                                     "added_up": None}
    return block


@pytest.fixture
def answering(monkeypatch):
    real = test_run._answer
    asked: list[dict] = []

    def answer(request: dict) -> dict:
        if request["kind"] == "write_system" and request.get("step") == "revise":
            asked.append(request)
            return _revise_answer(request)
        return real(request)
    monkeypatch.setattr(test_run, "_answer", answer)
    return asked


def _count_finding(job: Job, rule: str = "Higher count prints", fix: str = f"Set the count to {NEW_COUNT}."):
    return Finding(rule, job.systems[0].key, None, "must_fix", "The documents give a higher count.", fix)


def _run(job_folder, tmp_path, monkeypatch, decisions=None):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    real_validate = run.validate
    monkeypatch.setattr(run, "validate", lambda job, playbook: [*real_validate(job, playbook), _count_finding(job)])
    out, cache = tmp_path / "out", tmp_path / "cache"
    if decisions is not None:
        reached = _reach(job_folder, out, cache, "write")
        assert reached.stage == "write"
        (out / "decisions.json").write_text(json.dumps(decisions(Job.from_json(
            reached.job_file.read_text(encoding="utf-8")))), encoding="utf-8")
    result = _reach(job_folder, out, cache, "never")
    return result, Job.from_json(result.job_file.read_text(encoding="utf-8"))


def test_a_must_fix_about_the_count_is_corrected_by_the_revise(job_folder, tmp_path, monkeypatch, answering):
    result, job = _run(job_folder, tmp_path, monkeypatch)
    assert result.status == "done" and answering, "the revise was never asked"
    count = job.systems[0].families[0].count
    assert count.value == NEW_COUNT and count.highest() == NEW_COUNT
    assert count.others, "every earlier count stays in the others, with its source"
    assert "may correct" in answering[0]["prompt"]


def test_the_count_the_estimator_set_is_not_changed_by_the_revise(job_folder, tmp_path, monkeypatch, answering):
    def decisions(planned: Job) -> list[dict]:
        system = planned.systems[0]
        family = system.families[0]
        return [{"system_key": system.key, "action": "change", "family_name": family.name,
                 "count": dataclasses.replace(family.count, value=33, others=()).to_dict(), "reason": "invented"}]
    result, job = _run(job_folder, tmp_path, monkeypatch, decisions)
    assert result.status == "done"
    assert job.systems[0].families[0].count.value == 33                # the estimator's count, as they set it
    assert all("may correct" not in request["prompt"] for request in answering)
