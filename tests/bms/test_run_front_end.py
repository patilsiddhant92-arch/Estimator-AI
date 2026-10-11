"""ws5, HP 22 / 186 / 192d, through the whole run (chat mode, an invented job): the front end the planner finds in the
documents is written through the AI writer like a system, QC reads it, a must_fix finding about one of its lines is
revised, and the proposal prints it. When the documents call for none, nothing is asked and a question says so."""
from __future__ import annotations

import dataclasses
import json
import re

import pytest
from docx import Document

import test_run
from bms import run
from bms.model import Job, Ref
from test_run import _reach, job_folder  # noqa: F401  (job_folder is a fixture)

FRONT_END_HEADING = "Front End Web Enabled BMS System"
DEFAULT_FRONT_END = ("Furnish 3-D Graphics", "Furnish Necessary Training on New Controls")


@pytest.fixture
def with_front_end(monkeypatch):
    """The planner finds a front end in this job's documents: it cites the first passage of the dossier."""
    real = run.plan_job

    def plan(ledger, catalogue, dossier, playbook):
        job = real(ledger, catalogue, dossier, playbook)
        found = re.search(r"^\[(S\d+)\]\s+(.+)$", dossier.text, re.M)
        sid, words = found.group(1), " ".join(found.group(2).split()[:5])
        front = dataclasses.replace(job.front_end, lines=("Furnish an operator workstation",),
                                    refs=(Ref(sid, words, dossier.sources.get(sid, "")),))
        return dataclasses.replace(job, front_end=front)
    monkeypatch.setattr(run, "plan_job", plan)


@pytest.fixture
def requests(monkeypatch):
    """Every request the fake answerer sees, as (kind, system name, step)."""
    seen: list[tuple] = []
    real = test_run._answer

    def answer(request: dict) -> dict:
        seen.append((request["kind"], request.get("system"), request.get("step")))
        return real(request)
    monkeypatch.setattr(test_run, "_answer", answer)
    return seen


def _run(job_folder, tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = _reach(job_folder, tmp_path / "out", tmp_path / "cache", "never")
    assert result.status == "done", result
    return result, Job.from_json(result.job_file.read_text(encoding="utf-8"))


def _proposal_lines(result) -> list[str]:
    return [" ".join(p.text.split()) for p in Document(str(result.proposal)).paragraphs if p.text.strip()]


def _block(request: dict) -> dict:
    """The block as the revise was given it."""
    return json.loads(request["prompt"].split("The block as written:\n", 1)[1].split("\n\nThe findings", 1)[0])


def test_the_front_end_the_planner_finds_is_written_and_printed(job_folder, tmp_path, monkeypatch, with_front_end,
                                                                 requests):
    result, job = _run(job_folder, tmp_path, monkeypatch)
    assert ("write_system", "Front End", "write") in requests
    (device,) = job.front_end.devices
    assert device.id == "FE.d1" and device.refs and device.refs[0].source_id == job.front_end.refs[0].source_id
    assert job.front_end.lines == ("Furnish an operator workstation",)            # the planner's fields stay
    lines = _proposal_lines(result)
    at = lines.index(FRONT_END_HEADING)
    # T-005e (ruling 19): the new front end prints the Master Template's default lines with the writer's line, in the
    # template's order; (ruling 15) the line's quantity prints in it, "Qty (##)" while unknown
    front = lines[at + 1:at + 2 + len(DEFAULT_FRONT_END)]
    assert set(DEFAULT_FRONT_END) <= set(front), lines
    assert any(line.startswith("Qty (##) Furnish and Install Space Temperature Sensor") for line in front), lines
    assert not [f for f in result.findings if f.system_key == "" and f.severity == "must_fix"]


def test_a_front_end_line_a_qc_finding_names_is_revised(job_folder, tmp_path, monkeypatch, with_front_end, requests):
    real = test_run._answer
    qc = []

    def answer(request: dict) -> dict:
        usual = real(request)                       # (it records the request)
        if request["kind"] == "qc_job" and not qc:
            qc.append(request)
            return {"findings": [{"rule": "Every line cites this job", "system_key": "", "device_id": "FE.d1",
                                  "severity": "must_fix", "what": "The workstation line is named too loosely.",
                                  "fix": "Name it as the documents do."}]}
        if request["kind"] == "write_system" and request.get("system") == "Front End (revise)":
            block = _block(request)
            block["devices"][0]["name"] = "Operator Workstation"
            return block
        return usual
    monkeypatch.setattr(test_run, "_answer", answer)
    result, job = _run(job_folder, tmp_path, monkeypatch)
    assert qc, "QC was never asked"
    assert ("write_system", "Front End (revise)", "revise") in requests
    assert [d.name for d in job.front_end.devices] == ["Operator Workstation"]
    # T-005e (ruling 15): the line's quantity prints in it, "Qty (##)" while unknown
    assert any(line.startswith("Qty (##) Furnish and Install Operator Workstation") for line in _proposal_lines(result))
    # the finding is closed: QC is not asked again, and the line it named changed
    assert not [f for f in result.findings if f.device_id == "FE.d1" and f.severity == "must_fix"]


def test_nothing_is_written_or_asked_when_the_documents_call_for_no_front_end(job_folder, tmp_path, monkeypatch,
                                                                              requests):
    result, job = _run(job_folder, tmp_path, monkeypatch)
    assert not [seen for seen in requests if seen[1] and seen[1].startswith("Front End")]
    assert job.front_end is not None and job.front_end.devices == () and job.front_end.lines == ()
    assert any("The documents call for no front-end equipment" in question for question in job.questions)
    lines = _proposal_lines(result)
    assert FRONT_END_HEADING in lines                                   # the template's heading stays
    assert not any(line.startswith(("Furnish Network Level", "Furnish PC Workstation", "Furnish BMS Server"))
                   for line in lines)                                    # no standard line stands in


def test_a_front_end_the_writer_finds_nothing_in_is_a_question_for_the_estimator(job_folder, tmp_path, monkeypatch,
                                                                                  with_front_end, requests):
    real = test_run._answer
    reason = "The owner furnishes the whole front end."

    def answer(request: dict) -> dict:
        if request["kind"] == "write_system" and request.get("system") == "Front End":
            written = real(request)
            return {**written, "devices": [], "clarifications": [], "no_scope_reason": reason}
        return real(request)
    monkeypatch.setattr(test_run, "_answer", answer)
    result, job = _run(job_folder, tmp_path, monkeypatch)
    assert job.front_end.devices == () and job.front_end.no_scope_reason == reason
    assert any(q.startswith("No front-end line was written: The owner furnishes the whole front end.")
               for q in job.questions)
