"""Review 018b (lead's reviewer): a run-level probe for the accepted quantity flag (SECONDARY-REVIEW-018 H1).
Invented job folder from test_run.py only."""
from __future__ import annotations

import dataclasses
import json

import pytest

from test_run import _reach, job_folder  # noqa: F401  (job_folder is a fixture)


# ---- H1 at run level: the device really is flagged, and the accept still sticks ------------------------------------


def test_probe_an_accepted_quantity_flag_sticks_through_a_whole_rerun(job_folder, tmp_path, monkeypatch):
    """Every written device is flagged "quantity" (as when counts disagree). The estimator accepts the first one
    on the page; the rerun to done keeps it cleared, keeps the others flagged and raises no "not honored"."""
    from bms import run

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    real = run.flag_written_devices
    monkeypatch.setattr(run, "flag_written_devices", lambda system: dataclasses.replace(real(system), devices=tuple(
        dataclasses.replace(d, flag="quantity") for d in system.devices)))
    folder = job_folder
    out, cache = tmp_path / "out", tmp_path / "cache"
    first = _reach(folder, out, cache, "done")
    assert first.status == "done"
    saved = json.loads(first.job_file.read_text(encoding="utf-8"))
    system = next(s for s in saved["systems"] if s["devices"])
    shown = system["devices"][0]
    assert all(d["flag"] == "quantity" for d in system["devices"])           # the precondition holds
    (out / "decisions.json").write_text(json.dumps([{
        "system_key": system["key"], "action": "accept", "device_id": shown["id"], "was": shown,
        "reason": "invented"}]), encoding="utf-8")
    again = _reach(folder, out, cache, "done")
    assert again.status == "done"
    after = next(s for s in json.loads(again.job_file.read_text(encoding="utf-8"))["systems"]
                 if s["key"] == system["key"])
    assert after["devices"][0]["flag"] == "none"
    assert all(d["flag"] == "quantity" for d in after["devices"][1:])
    assert not [f for f in again.findings if f.rule == "decision not honored"]


def test_attack_a_delete_of_a_line_the_revise_reworded_is_not_lost_in_silence(job_folder, tmp_path, monkeypatch):
    """The page shows the final job, after the revise re-worded the damper line. The estimator deletes it there.
    The next run must either remove that line or say on the review page that the decision was not honored."""
    from bms import ai, run
    from bms.model import Finding
    from test_run import _plant

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out, cache = tmp_path / "out", tmp_path / "cache"
    assert _reach(job_folder, out, cache, "write").stage == "write"
    requests = sorted((cache / "judge-chat" / "requests").glob("*.json"))
    key = json.loads(requests[0].read_text(encoding="utf-8"))["plan_key"]
    _plant(cache, {key: ("Controller", "Start Stop", "Damper Actuator")})

    real_validate = run.validate
    monkeypatch.setattr(run, "validate", lambda job, playbook: [*real_validate(job, playbook), Finding(
        "Every line cites this job", key, None, "must_fix", "invented must_fix", "invented fix")])

    def reword(system, findings, evidence, playbook, transport, **kw):   # stands for the cached revise answer
        return dataclasses.replace(system, devices=tuple(
            dataclasses.replace(d, name="Damper Actuator, motorized") if d.name == "Damper Actuator" else d
            for d in system.devices))
    monkeypatch.setattr(ai, "revise_system", reword)

    first = _reach(job_folder, out, cache, "done")
    assert first.status == "done"
    shown = next(s for s in json.loads(first.job_file.read_text(encoding="utf-8"))["systems"] if s["key"] == key)
    damper = next(d for d in shown["devices"] if d["name"] == "Damper Actuator, motorized")   # as on the page
    (out / "decisions.json").write_text(json.dumps([{
        "system_key": key, "action": "delete", "device_id": damper["id"], "was": damper,
        "reason": "invented"}]), encoding="utf-8")
    again = _reach(job_folder, out, cache, "done")
    assert again.status == "done"
    final = next(s for s in json.loads(again.job_file.read_text(encoding="utf-8"))["systems"] if s["key"] == key)
    still_there = any(d["name"].startswith("Damper") for d in final["devices"])
    flagged = [f for f in again.findings if f.rule == "decision not honored"]
    assert not still_there or flagged
