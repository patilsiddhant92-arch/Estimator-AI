"""Integration: the revise round of `bms.run.estimate`, end to end on the invented job folder of test_run.py.

RUN-1: a line the estimator deleted does not come back when a whole-block must_fix sends the system to the revise
and the writer writes the line again. RUN-11: a must_fix finding that asks for a family count lets the revise
correct it, and the corrected count reaches Job.json, the proposal and the review page (with a check card naming
its source). RUN-2: an older decisions.json copied in again is not merged and the run says so. No real job data."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import docx
import pytest

HERE = Path(__file__).resolve().parent
for folder in (HERE, HERE.parent):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

from test_run import _answer, _evidence_ref, _plant, _reach, answer_all, job_folder  # noqa: E402,F401

from bms import ai, run  # noqa: E402
from bms.model import Finding  # noqa: E402
from bms.run import estimate  # noqa: E402


def _written(job_file: Path, key: str) -> dict:
    return next(s for s in json.loads(job_file.read_text(encoding="utf-8"))["systems"] if s["key"] == key)


def _key_with_family(job_file: Path) -> str:
    systems = json.loads(job_file.read_text(encoding="utf-8"))["systems"]
    return next(s["key"] for s in systems if s["families"] and s["families"][0]["count"]["value"])


def test_a_deleted_line_stays_deleted_through_a_whole_block_revise(job_folder, tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out, cache = tmp_path / "out", tmp_path / "cache"
    assert _reach(job_folder, out, cache, "write").stage == "write"
    requests = sorted((cache / "judge-chat" / "requests").glob("*.json"))
    key = json.loads(requests[0].read_text(encoding="utf-8"))["plan_key"]
    _plant(cache, {key: ("Controller", "Start Stop", "Damper Actuator")})
    written = estimate(job_folder, out, cache, "chat")
    damper = next(d for d in _written(written.job_file, key)["devices"] if d["name"] == "Damper Actuator")
    (out / "decisions.json").write_text(json.dumps([{
        "system_key": key, "action": "delete", "device_id": damper["id"], "was": damper,
        "reason": "invented"}]), encoding="utf-8")
    real_validate = run.validate
    monkeypatch.setattr(run, "validate", lambda job, playbook: [*real_validate(job, playbook), Finding(
        "Every line cites this job", key, None, "must_fix", "invented must_fix", "invented fix")])
    asked = []

    def writes_it_again(system, findings, evidence, playbook, transport, **kw):    # the writer's whole-block answer
        asked.append(kw)
        from bms.model import Device
        import dataclasses
        return dataclasses.replace(system, devices=(*system.devices, Device.from_dict(damper)))
    monkeypatch.setattr(ai, "revise_system", writes_it_again)
    done = _reach(job_folder, out, cache, "done")
    assert done.status == "done"
    assert [d["name"] for d in _written(done.job_file, key)["devices"]] == ["Controller", "Start Stop"]
    assert not [f for f in done.findings if f.rule == "decision not honored"]
    assert asked and [d.name for d in asked[0]["deleted"]] == ["Damper Actuator"]


def _corrects_the_count(key: str, value: int):
    """Answer every waiting request; the revise of `key` corrects its first family's count to `value`, citing the
    evidence's first source as the count's source, and carries the new count on its lines."""
    def answer(cache: Path) -> int:
        n = 0
        for path in sorted((cache / "judge-chat" / "requests").glob("*.json")):
            request = json.loads(path.read_text(encoding="utf-8"))
            reply = _answer(request)
            if request.get("kind") == "write_system" and request.get("step") == "revise" \
                    and request.get("plan_key") == key:
                block = json.loads(request["prompt"].split("The block as written:\n", 1)[1].split("\n\nThe findings")[0])
                ref = _evidence_ref(request["prompt"])
                block["families"][0]["count"] = {"value": value, "sources": [ref], "others": []}
                for device in block["devices"]:
                    device["quantity"] = {"value": value, "sources": [ref], "others": []}
                reply = block
            dest = Path(request["answer_file"])
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(json.dumps(reply), encoding="utf-8")
            n += 1
        return n
    return answer


def test_a_count_the_qc_finding_corrects_reaches_job_json_and_the_proposal(job_folder, tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out, cache = tmp_path / "out", tmp_path / "cache"
    written = _reach(job_folder, out, cache, "qc")
    key = _key_with_family(written.job_file)
    family = _written(written.job_file, key)["families"][0]
    old = family["count"]["value"]
    value = old + 3                                       # the finding shows the planner missed some
    real_validate = run.validate
    monkeypatch.setattr(run, "validate", lambda job, playbook: [*real_validate(job, playbook), Finding(
        "Never undershoot", key, None, "must_fix", f"the {family['name']} count of {old} misses three",
        f"Set the {family['name']} count to {value} per the documents.")] if job.system(key).families[0].count.value
        == old else real_validate(job, playbook))
    answer = _corrects_the_count(key, value)
    done = None
    for _ in range(25):
        answer(cache)
        done = estimate(job_folder, out, cache, "chat")
        if done.status == "done":
            break
    assert done is not None and done.status == "done", done
    final = _written(done.job_file, key)
    assert final["families"][0]["count"]["value"] == value                     # Job.json
    text = "\n".join(p.text for p in docx.Document(done.proposal).paragraphs)
    assert f"Qty ({value})" in text                                            # the proposal
    cards = [f for f in done.findings if f.system_key == key and "the revise corrected" in f.what]
    assert cards and cards[0].severity == "check" and f"from {old} to {value}" in cards[0].what
    assert "the revise corrected" in done.review.read_text(encoding="utf-8")


def test_an_older_decisions_file_copied_in_again_is_named_and_not_applied(job_folder, tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out, cache = tmp_path / "out", tmp_path / "cache"
    written = _reach(job_folder, out, cache, "qc")
    key = _key_with_family(written.job_file)
    family = _written(written.job_file, key)["families"][0]

    def save(n: int, page: str) -> str:
        text = json.dumps({"page": page, "decisions": [{
            "system_key": key, "action": "change", "family_name": family["name"],
            "count": dict(family["count"], value=n, others=[])}]})
        (out / "decisions.json").write_text(text, encoding="utf-8")
        return text
    older = save(family["count"]["value"] + 1, "page-a")
    answer_all(cache)
    estimate(job_folder, out, cache, "chat")
    save(family["count"]["value"] + 2, "page-b")
    answer_all(cache)
    estimate(job_folder, out, cache, "chat")
    (out / "decisions.json").write_text(older, encoding="utf-8")
    (out / "decisions (1).json").write_text(older, encoding="utf-8")
    result = None
    for _ in range(25):
        answer_all(cache)
        result = estimate(job_folder, out, cache, "chat")
        if result.status == "done":
            break
    assert any("earlier save" in m for m in result.messages), result.messages
    assert any("decisions (1).json" in m for m in result.messages)
    assert _written(result.job_file, key)["families"][0]["count"]["value"] == family["count"]["value"] + 2
