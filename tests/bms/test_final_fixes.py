"""FINAL-FIXES (the lead's fixes for REVIEW-FINAL F1, F4, F5, F6, F7, F8): each test fails on rebuild 896ea3f.
Invented data only: the sample fixture, the sample Playbook and the invented job folder of test_run.py."""
from __future__ import annotations

import copy
import json
import os
import re
from dataclasses import replace
from pathlib import Path

import pytest

from bms import ai, run
from bms.model import Job, ScopeException
from bms.playbook import load_playbook
from bms.render import RenderError, render
from bms.status import RUN_STATE, check
from bms.validate import RULE, validate

from test_ai import FakeClient, _bad, _Response, skeleton
from test_ai import dossier, raw  # noqa: F401  (fixtures)
from test_render import S141, device, one, system
from test_review_final import _cards, _decision, _drive, _job
from test_run import _answer, _reach, job_folder  # noqa: F401  (job_folder is a fixture)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
ROOT = Path(__file__).resolve().parents[2]
_BROKEN = re.compile(r"times\. [a-z]")          # "refused 3 times. the answer ..."


@pytest.fixture
def sample_job() -> Job:
    return Job.from_dict(json.loads((FIXTURES / "sample_job.json").read_text(encoding="utf-8")))


# ---- F1: a delete next to a family-count change, saved in a later round -------------------------------------------

def test_a_delete_saved_after_a_change_and_a_count_change_stays_deleted(job_folder, tmp_path, monkeypatch):
    """Save 1 changes the VAV count (4 -> 5) and renames the sensor; save 2 deletes the renamed line (rebased onto
    the written line). The count rewrite of run 3 is asked with no devices and writes the sensor again: the delete
    is applied again after it, by the line's saved content, so the line stays gone and no "not honored" card is
    left."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out, cache = tmp_path / "out", tmp_path / "cache"
    _drive(job_folder, out, cache, [])
    cards = _cards(out)
    family = next(c for c in cards if c["level"] == "family")
    sensor = next(c for c in cards if c["level"] == "device")
    renamed = copy.deepcopy(sensor["device"])
    renamed.update(name="Room Temperature Sensor", flag="none")
    renamed["quantity"]["value"] = 4
    (out / "decisions.json").write_text(json.dumps([
        _decision(family, "change", count=dict(copy.deepcopy(family["count"]), value=5), reason="5"),
        _decision(sensor, "change", device=renamed, reason="Room Temperature Sensor")]), encoding="utf-8")
    second = _drive(job_folder, out, cache, [])
    line = next(d for s in _job(second)["systems"] for d in s["devices"] if s["key"] == sensor["system_key"])
    assert line["name"] == "Room Temperature Sensor"
    (out / "decisions.json").write_text(json.dumps([{
        "system_key": sensor["system_key"], "action": "delete", "device_id": line["id"], "family_name": None,
        "device": None, "count": None, "finding_rule": None, "reason": "", "was": line}]), encoding="utf-8")
    third = _drive(job_folder, out, cache, [])
    kept = next(s for s in _job(third)["systems"] if s["key"] == sensor["system_key"])
    assert kept["devices"] == []
    assert not [f for f in third.findings if f.rule == "decision not honored" and f.severity == "must_fix"]


def test_keep_deleted_takes_out_only_the_copies_the_delete_took(sample_job):
    """Two identical lines, one deleted: a rewrite that writes both again keeps one; one that writes one keeps it."""
    from bms.model import Decision
    from bms.review import keep_deleted
    line = sample_job.system("EF").devices[0]
    twins = (replace(line, id="EF.d1"), replace(line, id="EF.d2"))
    decided = sample_job.with_system(replace(sample_job.system("EF"), devices=twins[1:]))
    delete = Decision("EF", "delete", device_id="EF.d1", was=twins[0])
    again = replace(sample_job.system("EF"), devices=twins)
    assert [d.id for d in keep_deleted(decided, again, [delete]).devices] == ["EF.d1"]
    once = replace(sample_job.system("EF"), devices=twins[:1])
    assert keep_deleted(decided, once, [delete]) == once


# ---- F7: an estimator's change that prints an issued id -------------------------------------------------------------

def test_a_change_printing_an_issued_id_is_kept_as_written_and_names_the_id(job_folder, tmp_path, monkeypatch):
    """The estimator's line stays as they wrote it (the revise is not asked to rewrite it under its old name), and
    its card says the change prints a source id, naming the token, as a must_fix."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out, cache = tmp_path / "out", tmp_path / "cache"
    _drive(job_folder, out, cache, [])
    sensor = next(c for c in _cards(out) if c["level"] == "device")
    token = sensor["device"]["refs"][0]["source_id"]
    renamed = copy.deepcopy(sensor["device"])
    renamed.update(name=f"Room Temperature Sensor {token}", flag="none")
    (out / "decisions.json").write_text(json.dumps([_decision(sensor, "change", device=renamed, reason="x")]),
                                        encoding="utf-8")
    second = _drive(job_folder, out, cache, [])
    names = [d["name"] for s in _job(second)["systems"] for d in s["devices"] if s["key"] == sensor["system_key"]]
    assert names == [f"Room Temperature Sensor {token}"]
    cards = [f for f in second.findings if f"your change prints a source id ({token})" in f.what]
    assert len(cards) == 1 and cards[0].severity == "must_fix", [(f.rule, f.what) for f in second.findings]
    assert "name the document in words" in cards[0].what
    assert not [f for f in second.findings if "undid" in f.fix]


# ---- F4: the stop message, for chat and for the API -----------------------------------------------------------------

def test_the_chat_stop_message_says_the_next_run_asks_again_and_reads_as_sentences(job_folder, tmp_path,
                                                                                 monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out, cache = tmp_path / "out", tmp_path / "cache"
    assert _reach(job_folder, out, cache, "write").stage == "write"
    result = None
    for _ in range(3):
        for path in (cache / "judge-chat" / "requests").glob("*.json"):
            request = json.loads(path.read_text(encoding="utf-8"))
            answer = _answer(request)
            answer["devices"][0]["slot"] = "an_invented_slot"
            target = Path(request["answer_file"])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(answer), encoding="utf-8")
            stamp = path.stat().st_mtime_ns + 1_000_000
            os.utime(target, ns=(stamp, stamp))
        result = run.estimate(job_folder, out, cache, "chat")
    message = result.messages[0]
    assert message.startswith("Stopped:"), result.messages
    assert "delete" not in message, message
    assert "next run asks this question again" in message, message
    assert not _BROKEN.search(message), message


def test_the_api_stop_message_names_the_counter_to_delete_and_reads_as_sentences(raw, dossier, tmp_path):
    job = Job.from_dict(raw)
    target = skeleton(job.system("EF"))
    bad = _bad(raw, lambda a: a["devices"][0].update(slot="gadget"))
    client = FakeClient(*(_Response(json.dumps(bad)) for _ in range(8)))
    reasons = []
    for _ in range(4):                      # refusals counted across runs; the stop, then "not asked again"
        with pytest.raises(ai.NoAnswer) as failed:
            ai.write_system(target, ai.evidence_for(target, dossier), load_playbook(FIXTURES / "sample_playbook"),
                            ai.ApiTransport(tmp_path, model="claude-test", client=client))
        reasons.append(failed.value.reason)
    counter = next(tmp_path.rglob("attempts/*.json"))
    stops = [r for r in reasons if r.startswith("Stopped:")]
    assert any("could not be used" in r for r in stops) and any("not asked again" in r for r in stops), reasons
    for message in stops:
        assert f"delete {counter}" in message, message
        assert not _BROKEN.search(message), message


# ---- F5: status shows a refusal stop while other requests wait -------------------------------------------------------

def test_status_shows_a_stopped_request_while_other_requests_wait(tmp_path):
    out, cache = tmp_path / "out", tmp_path / "cache"
    for name, data in (("00-0000 Ledger.json", {"job_name": "Invented A", "complete": True}),
                       ("00-0000 Job.json", {"systems": [{"key": "EF", "name": "Exhaust Fans"}]})):
        (out / name).parent.mkdir(parents=True, exist_ok=True)
        (out / name).write_text(json.dumps(data), encoding="utf-8")
    request = cache / "judge-chat" / "requests" / "q.json"
    request.parent.mkdir(parents=True)
    request.write_text(json.dumps({"kind": "write_system", "step": "write", "system": "Exhaust Fans",
                                   "job": "Invented A", "answer_file": str(cache / "a.json")}), encoding="utf-8")
    (out / RUN_STATE).write_text(json.dumps({
        "version": 1, "status": "waiting", "stage": "write", "waiting": 1, "quote": "00-0000", "job": "Invented A",
        "messages": ["Stopped: the request Invented Pumps was refused 3 times. An invented reason."]}),
        encoding="ascii")
    status = check(out, cache)
    assert status.code == 2
    assert any("Stopped: the request Invented Pumps was refused 3 times" in line for line in status.lines), \
        status.lines


# ---- F6: a named exception that is only an issued id; a RenderError never leaves "running" -----------------------

def test_a_named_exception_made_only_of_an_issued_id_is_left_out_and_is_a_must_fix(sample_job):
    pb = load_playbook(ROOT / "playbook")
    job = replace(one(sample_job, system([device(name="Control Valve", refs=(S141,))])),
                  exceptions=(ScopeException("EF", "S141", (S141,)),
                              ScopeException("EF", "Fire alarm by others", ())))
    draft = render(job, pb)
    assert draft.scope.named_exceptions == ("Fire alarm by others",)
    assert [f for f in validate(job, pb) if f.rule == RULE["ids"] and f.severity == "must_fix" and f.system_key == ""]


def test_a_render_error_ends_the_run_state_with_the_message_not_running(job_folder, tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out, cache = tmp_path / "out", tmp_path / "cache"
    assert _reach(job_folder, out, cache, "qc").stage == "qc"
    from test_run import answer_all
    assert answer_all(cache)

    def broken(*_a, **_k):
        raise RenderError("an invented render problem")

    monkeypatch.setattr(run, "render", broken)
    with pytest.raises(RenderError):
        run.estimate(job_folder, out, cache, "chat")
    state = json.loads((out / RUN_STATE).read_text(encoding="ascii"))
    assert state["status"] != "running" and state["waiting"] == 0
    assert any(m.startswith("Stopped:") and "an invented render problem" in m for m in state["messages"])
    status = check(out, cache)
    assert status.code == 1 and any("an invented render problem" in line for line in status.lines)


# ---- F8: the missing-history note only when an earlier history was lost -----------------------------------------------

def test_the_missing_history_note_is_not_shown_on_the_first_save_but_is_when_a_history_was_lost(job_folder, tmp_path,
                                                                                               monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out, cache = tmp_path / "out", tmp_path / "cache"
    _drive(job_folder, out, cache, [])
    sensor = next(c for c in _cards(out) if c["level"] == "device")
    (out / "decisions.json").write_text(json.dumps([_decision(sensor, "accept")]), encoding="utf-8")
    second = run.estimate(job_folder, out, cache, "chat")         # the run that reads the first save
    assert not [m for m in second.messages if "no decisions history.json was found" in m], second.messages
    from test_run import answer_all
    answer_all(cache)
    _drive(job_folder, out, cache, [])
    (out / "decisions history.json").unlink()
    third = run.estimate(job_folder, out, cache, "chat")
    assert [m for m in third.messages if "no decisions history.json was found" in m], third.messages
