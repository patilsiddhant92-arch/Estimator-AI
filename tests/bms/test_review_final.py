"""REVIEW-FINAL (whole-branch review of `rebuild` at 896ea3f against 68919e8): integration tests no single review of
record covered. The three-run lifecycle on the invented job folder of test_run.py (first run to done, decisions saved
from the page, a second and a third run), with Job.json, Review.html, the proposal, `run state.json` and
`python -m bms status` checked against each other at every step; the refusal counter against a Playbook that changes
between runs; and the two open findings as strict xfails (the failing input in the docstring).
Invented data only: the sample fixture and the invented job folder of test_run.py."""
from __future__ import annotations

import copy
import dataclasses
import json
import os
import re
from pathlib import Path

import docx
import pytest

from bms import ai, run
from bms.model import SEVERITIES, Decision, Device, Finding, Job, Ref, System
from bms.playbook import load_playbook
from bms.status import RUN_STATE, check

from test_ai import FakeClient, _bad, _Response, skeleton
from test_ai import dossier, raw  # noqa: F401  (fixtures)
from test_run import answer_all, job_folder  # noqa: F401  (job_folder is a fixture)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
_QDATA = re.compile(r'<script type="application/json" class="qdata">(.*?)</script>', re.S)
_RULE = re.compile(r'<span class="rule">Rule: (.*?)</span>')


# ---- the lifecycle harness -----------------------------------------------------------------------------------------

def _drive(job_folder, out, cache, steps):
    """Run, answer, run again until done. After every run, the run state and `bms status` must agree with what the
    run returned: done is exit 0 and "done"; waiting with requests is exit 2 and "waiting" at the same stage."""
    result = None
    for _ in range(25):
        result = run.estimate(job_folder, out, cache, "chat")
        state = json.loads((out / RUN_STATE).read_text(encoding="ascii"))
        status = check(out, cache)
        steps.append((result.status, result.stage, status.code))
        assert (state["status"], state["stage"], state["waiting"]) == (result.status, result.stage, result.waiting)
        assert state["quote"] and state["job"]
        if result.status == "done":
            assert status.code == 0 and status.lines[0].startswith("Stage: done."), status.lines
            return result
        assert result.waiting >= 1, result.messages
        assert status.code == 2 and status.lines[0].startswith(f"Stage: {result.stage}."), status.lines
        assert answer_all(cache)
    raise AssertionError(steps)


def _cards(out: Path) -> list[dict]:
    return [json.loads(found) for found in _QDATA.findall((out / "Review.html").read_text(encoding="utf-8"))]


def _proposal_lines(result) -> list[str]:
    return [p.text for p in docx.Document(str(result.proposal)).paragraphs if p.text.strip()]


def _job(result) -> dict:
    return json.loads(result.job_file.read_text(encoding="utf-8"))


def _decision(card: dict, action: str, *, device: dict | None = None, count: dict | None = None,
              reason: str = "") -> dict:
    """What the page's buildDecision saves for a card (review.py _SCRIPT_CORE)."""
    return {"system_key": card["system_key"], "action": action, "device_id": card["device_id"],
            "family_name": card["family_name"], "device": device, "count": count,
            "finding_rule": card["finding_rule"], "reason": reason,
            "was": copy.deepcopy(card["device"]) if card["level"] == "device" else None}


def _agree(result, out):
    """Job.json, the review page and the proposal tell the same story: every card names a line or family the job has,
    and every device of the job prints in the proposal under its own name."""
    job = _job(result)
    devices = {(s["key"], d["id"]): d for s in job["systems"] for d in s["devices"]}
    families = {(s["key"], f["name"]) for s in job["systems"] for f in s["families"]}
    for card in _cards(out):
        if card["level"] == "device":
            assert (card["system_key"], card["device_id"]) in devices, card
            assert card["device"] == devices[(card["system_key"], card["device_id"])]
        elif card["level"] == "family":
            assert (card["system_key"], card["family_name"]) in families, card
    printed = "\n".join(_proposal_lines(result))
    for device in devices.values():
        assert device["name"] in printed, device["name"]
    return job


# ---- (1) the three-run lifecycle -----------------------------------------------------------------------------------

def test_the_three_run_lifecycle_keeps_job_page_proposal_run_state_and_status_in_agreement(job_folder, tmp_path,
                                                                                           monkeypatch):
    """Run 1 waits at every stage and finishes. The estimator then changes the VAV family count (4 -> 5) and
    renames the flagged sensor with a count of 4 on the page. Run 2 asks the count rewrite once (stage write),
    then QC, and finishes with both decisions in Job.json, the proposal and the history, and no card left on the
    sensor. Run 3, with nothing new saved, finishes at once, asks nothing, and changes nothing."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out, cache = tmp_path / "out", tmp_path / "cache"
    steps: list = []
    first = _drive(job_folder, out, cache, steps)
    stages = [stage for _, stage, _ in steps]
    assert stages.index("read") < stages.index("count") < stages.index("write") < stages.index("qc")
    _agree(first, out)
    cards = _cards(out)
    family = next(c for c in cards if c["level"] == "family")
    sensor = next(c for c in cards if c["level"] == "device")
    assert sensor["device"]["flag"] == "quantity"

    count = dict(copy.deepcopy(family["count"]), value=5)
    renamed = copy.deepcopy(sensor["device"])
    renamed.update(name="Room Temperature Sensor", flag="none")
    renamed["quantity"]["value"] = 4
    (out / "decisions.json").write_text(json.dumps([
        _decision(family, "change", count=count, reason="5"),
        _decision(sensor, "change", device=renamed, reason="Room Temperature Sensor")]), encoding="utf-8")

    steps = []
    second = _drive(job_folder, out, cache, steps)
    assert [stage for _, stage, _ in steps] == ["write", "qc", "done"]       # the count rewrite, QC, the end
    job = _agree(second, out)
    system = next(s for s in job["systems"] if s["key"] == family["system_key"])
    assert next(f for f in system["families"] if f["name"] == family["family_name"])["count"]["value"] == 5
    assert [(d["name"], d["flag"], d["quantity"]["value"]) for d in system["devices"]] == [
        ("Room Temperature Sensor", "none", 4)]
    assert not [c for c in _cards(out) if c["level"] == "device"]
    assert not [f for f in second.findings if f.rule == "decision not honored"]
    printed = _proposal_lines(second)
    assert any("Room Temperature Sensor" in line and "4" in line for line in printed)
    assert not any("Space Temperature Sensor" in line for line in printed)
    history = json.loads((out / "decisions history.json").read_text(encoding="utf-8"))
    assert [(h["round"], h["decision"]["action"], h["took_effect"], bool(h.get("settled"))) for h in history] == [
        (1, "change", True, True), (1, "change", True, True)]

    page = (out / "Review.html").read_text(encoding="utf-8")
    saved_job = second.job_file.read_text(encoding="utf-8")
    steps = []
    third = _drive(job_folder, out, cache, steps)
    assert steps == [("done", "done", 0)]                                   # nothing asked again
    assert list((cache / "judge-chat" / "requests").glob("*.json")) == []
    assert third.job_file.read_text(encoding="utf-8") == saved_job
    assert _RULE.findall((out / "Review.html").read_text(encoding="utf-8")) == _RULE.findall(page)
    assert json.loads((out / "decisions history.json").read_text(encoding="utf-8")) == history
    assert _proposal_lines(third) == printed


# ---- (2) a delete next to a family-count change --------------------------------------------------------------------

@pytest.mark.xfail(strict=True, reason="REVIEW-FINAL F1: the count rewrite runs after the device decisions and is "
                                       "not followed by them, so it can write a deleted line back")
def test_a_delete_saved_with_a_family_count_change_stays_deleted(job_folder, tmp_path, monkeypatch):
    """Failing input: after a finished first run, one save holds a change of the VAV family count (4 -> 5) and a
    delete of the sensor line. run._estimate applies both to the written job (the sensor is gone), then, since the
    family count changed, asks ai.rewrite_for_count with the remaining devices (none). The writer, asked to write the
    system from its evidence, writes the sensor again; only standing accepts are applied after the rewrite, so the
    sensor is back in Job.json and in the proposal, and the page shows a must_fix "decision not honored: delete
    VAV.d1" that no further save can clear (every run applies the delete and asks the rewrite again). Asserting
    line: the sensor is not in the final job."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out, cache = tmp_path / "out", tmp_path / "cache"
    _drive(job_folder, out, cache, [])
    cards = _cards(out)
    family = next(c for c in cards if c["level"] == "family")
    sensor = next(c for c in cards if c["level"] == "device")
    count = dict(copy.deepcopy(family["count"]), value=5)
    (out / "decisions.json").write_text(json.dumps([
        _decision(family, "change", count=count, reason="5"), _decision(sensor, "delete")]), encoding="utf-8")
    second = _drive(job_folder, out, cache, [])
    system = next(s for s in _job(second)["systems"] if s["key"] == sensor["system_key"])
    assert [d["name"] for d in system["devices"]] == []


# ---- (3) the "check this system" card's severity -------------------------------------------------------------------

@pytest.mark.xfail(strict=True, reason="REVIEW-FINAL F2: the check card's severity 'should_fix' is no Severity "
                                       "of the model (must_fix | check)")
def test_the_check_this_system_finding_is_a_model_finding():
    """Failing input: run._check_this_system(an earlier delete) builds Finding(..., severity="should_fix"). The
    model's Severity is "must_fix" | "check" (model.SEVERITIES, the interfaces doc section 2.1), so the finding does not
    survive its own JSON round trip (ModelError at Finding.severity), and every reader that branches on the two
    values (the review page's rank, the revise's must_fix list) sees it only as "not must_fix". Asserting
    lines: the severity, then the round trip."""
    was = Device("EF.d3", "damper", "Damper Actuator", "Furnish and Install", "AME", "AME", "AME",
                 _count(), (Ref("S1", "invented", "invented place"),))
    finding = run._check_this_system(Decision("EF", "delete", device_id="EF.d3", was=was))
    assert finding.severity in SEVERITIES
    assert Finding.from_dict(finding.to_dict()) == finding


def _count():
    from bms.model import Count
    return Count(1, (Ref("S1", "invented", "invented place"),))


# ---- (4) the refusal counter against a Playbook that changes between runs -------------------------------------------

def test_a_stopped_question_stays_stopped_until_the_playbook_changes_then_counts_anew(raw, dossier, tmp_path):
    """Intended (the stop message): "a changed Playbook ... starts a new count". Three runs refuse the same answer:
    the third stops, a fourth with the same Playbook stops before any call; a fifth, after rules.md changed, asks
    the API again with a counter of its own (two counter files), and its refusal is counted from one, not stopped."""
    job = Job.from_dict(raw)
    system = skeleton(job.system("EF"))
    bad = _bad(raw, lambda a: a["devices"][0].update(slot="gadget"))
    client = FakeClient(*(_Response(json.dumps(bad)) for _ in range(8)))
    evidence = ai.evidence_for(system, dossier)
    playbook = load_playbook(FIXTURES / "sample_playbook")

    def ask(book) -> str:
        with pytest.raises(ai.NoAnswer) as failed:
            ai.write_system(system, evidence, book, ai.ApiTransport(tmp_path, model="claude-test", client=client))
        return failed.value.reason

    reasons = [ask(playbook) for _ in range(3)]
    assert reasons[-1].startswith("Stopped:") and len(client.calls) == 3
    assert ask(playbook).startswith("Stopped:") and len(client.calls) == 3          # not asked again
    changed = dataclasses.replace(playbook, rules_text=playbook.rules_text + "\nAn invented new sentence.\n")
    reason = ask(changed)
    assert len(client.calls) > 3, "the changed Playbook's question was not asked"
    assert not reason.startswith("Stopped:"), reason
    assert len(list(tmp_path.rglob("attempts/*.json"))) == 2


# ---- (5) a refused-answer stop, then the chat's next run -----------------------------------------------------------

def test_a_refusal_stop_is_exit_1_with_the_runs_words_and_the_next_chat_run_asks_again(job_folder, tmp_path,
                                                                                    monkeypatch):
    """The writer's answer is refused three times (a slot the shape does not have): the run stops at write with
    nothing waiting; the run state keeps the stop's words and status exits 1 naming them (not 2, not "running").
    The next chat run writes the request again and waits (exit 2): in chat mode the stop does not need the counter
    deleted, unlike what the stop message says (REVIEW-FINAL F4, wording only)."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out, cache = tmp_path / "out", tmp_path / "cache"
    from test_run import _answer, _reach
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
            stamp = path.stat().st_mtime_ns + 1_000_000                     # newer than its request, always
            os.utime(target, ns=(stamp, stamp))
        result = run.estimate(job_folder, out, cache, "chat")
    assert result.status == "waiting" and result.stage == "write" and result.waiting == 0
    assert result.messages[0].startswith("Stopped:")
    state = json.loads((out / RUN_STATE).read_text(encoding="ascii"))
    assert state["status"] == "waiting" and state["messages"] == list(result.messages)
    status = check(out, cache)
    assert status.code == 1 and any(line.strip().startswith("Stopped:") for line in status.lines)

    again = run.estimate(job_folder, out, cache, "chat")
    assert again.status == "waiting" and again.waiting == 1
    assert check(out, cache).code == 2
