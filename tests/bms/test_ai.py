"""Workstream 5: the AI steps (write, QC, revise), their evidence and the two transports, tested with fake
transports and a fake Anthropic client against the invented fixtures (no real job text)."""
from __future__ import annotations

import copy
import dataclasses
import json
import re
import sys
from pathlib import Path

import pytest

from estimator.writing.dossier import Dossier, DossierImage
from estimator.writing.judge import _key

from bms import ai
from bms.model import Finding, Job, Ref, System, json_schema, schema_errors
from bms.playbook import load_playbook

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"
ROOT = HERE.parents[1]
WS5 = FIXTURES / "ws5"
PNG = b"\x89PNG\r\n\x1a\n" + b"invented picture bytes"


# ---- fixtures -----------------------------------------------------------------------------------------------

@pytest.fixture
def raw() -> dict:
    return json.loads((FIXTURES / "sample_job.json").read_text(encoding="utf-8"))


@pytest.fixture
def job(raw) -> Job:
    return Job.from_dict(raw)


@pytest.fixture
def playbook():
    return load_playbook(FIXTURES / "sample_playbook")


@pytest.fixture
def dossier(tmp_path) -> Dossier:
    data = json.loads((WS5 / "dossier.json").read_text(encoding="utf-8"))
    images = []
    for image in data["images"]:
        path = tmp_path / image["path"]
        path.write_bytes(PNG)
        images.append(DossierImage(str(path), image["what"], image["sheet"], image["document"], image["page"]))
    sections = {q: (heading, tuple(ids)) for q, (heading, ids) in data["sections"].items()}
    return Dossier(data["job_name"], "\n".join(data["text_lines"]) + "\n", tuple(images), dict(data["sources"]), (),
                   {}, {}, {}, sections)


def skeleton(system: System) -> System:
    """What the planner hands the writer: devices, clarifications and tech hours empty."""
    return dataclasses.replace(system, devices=(), clarifications=(), tech_hours=None)


class FakeTransport:
    """Answers from a queue; records every question."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.asked: list[dict] = []
        self.waiting = 0
        self.last_error = None

    def ask(self, kind, name, instructions, system_prompt, prompt, schema, extra=None, images=()):
        self.asked.append(dict(kind=kind, name=name, instructions=instructions, system_prompt=system_prompt,
                               prompt=prompt, schema=schema, extra=extra, images=tuple(images)))
        if not self.answers:
            raise ai.NoAnswer("no answer queued", waiting=True)
        return copy.deepcopy(self.answers.pop(0))


# ---- the evidence -----------------------------------------------------------------------------------------------

def _ids(text: str) -> set[str]:
    return set(re.findall(r"^\[([A-Z]{1,3}\d+)\]", text, re.M))


def test_evidence_for_a_fan_system_gives_its_passages_with_their_ids(job, dossier):
    text = ai.evidence_for(skeleton(job.system("EF")), dossier)
    ids = _ids(text)
    assert {"S18", "S19"} <= ids and "--- [Q2] B. EXHAUST FANS ---" in text        # its sequence section, whole
    assert {"S22", "S27", "S28", "S29", "S30", "S40", "S6", "S7", "S8", "S16"} <= ids
    assert "    Columns: TAG | CFM" in text                                         # a schedule keeps its columns
    assert not ids & {"S17", "S20", "S23", "S25", "S9", "S2", "S37", "S14", "S1"}  # other systems' passages
    assert text == ai.evidence_for(skeleton(job.system("EF")), dossier)           # deterministic


def test_evidence_for_a_vrf_group_names_its_picture_and_its_range(job, dossier):
    text = ai.evidence_for(skeleton(job.system("VRF")), dossier)
    ids = _ids(text)
    assert {"S9", "S10", "S11", "S12", "S31", "S35", "S38", "I1"} <= ids
    assert re.search(r"^\[I1\] Picture: .+ File: .+I1\.png$", text, re.M)


def test_evidence_for_a_system_without_tags_uses_its_section_and_its_name(job, dossier):
    text = ai.evidence_for(skeleton(job.system("CUH")), dossier)
    ids = _ids(text)
    assert {"S21", "S41", "S42"} <= ids                 # its sequence section; its schedule by its title
    assert "S18" not in ids


def test_evidence_lists_ledger_facts_the_planner_cited(job, dossier):
    system = skeleton(job.system("DH"))
    system = dataclasses.replace(system, sequence_refs=system.sequence_refs + (
        Ref("F17", "duct heaters by the electrical contractor", "ledger fact"),))
    text = ai.evidence_for(system, dossier)
    assert "[F17]" in text and "duct heaters by the electrical contractor" in text


def test_evidence_index_has_every_source(dossier):
    index = ai.evidence_index(dossier)
    assert set(dossier.sources) <= set(index)
    assert index["S7"] == "KEYED NOTES 1: MD-1 interlocked with EF-1."
    assert "Columns: TAG | CFM" in index["S27"]
    assert "B. EXHAUST FANS" in index["Q2"] and "When EF-1 runs, MD-1 shall open." in index["Q2"]
    assert "M-102" in index["I1"]


# ---- the chat transport -------------------------------------------------------------------------------------

SCHEMA = {"type": "object", "properties": {"findings": {"type": "array", "items": {"type": "string"}}},
          "required": ["findings"], "additionalProperties": False}


def _ask(transport, prompt="the question", images=(), extra=None):
    return transport.ask(ai.QC_JOB, "QC", "RULES", "STEP", prompt, SCHEMA, extra or {"step": "qc"}, images)


def test_chat_writes_a_request_then_reads_the_answer_and_caches_it(tmp_path):
    chat = ai.ChatTransport(tmp_path, job="00-0000")
    with pytest.raises(ai.NoAnswer) as missing:
        _ask(chat)
    assert missing.value.waiting and chat.waiting == 1
    key = _key(ai.CHAT_MODEL, "the question", "RULES\n\nSTEP")
    request_file = tmp_path / "judge-chat" / "requests" / f"{key}.json"
    request = json.loads(request_file.read_text(encoding="utf-8"))
    assert list(request) == ["key", "kind", "system", "job", "system_prompt", "prompt", "step", "schema",
                             "answer_file"]
    assert request["system_prompt"] == "RULES\n\nSTEP" and request["job"] == "00-0000"
    assert request["answer_file"] == str(tmp_path / "judge-chat" / "answers" / f"{key}.json")

    Path(request["answer_file"]).parent.mkdir(parents=True)
    Path(request["answer_file"]).write_text(json.dumps({"findings": ["one"]}), encoding="utf-8")
    again = ai.ChatTransport(tmp_path, job="00-0000")
    assert _ask(again) == {"findings": ["one"]}
    assert not request_file.exists() and again.waiting == 0
    cached = json.loads((tmp_path / "judge" / f"{key}.json").read_text(encoding="utf-8"))
    assert cached == {"version": 1, "kind": ai.QC_JOB, "model": ai.CHAT_MODEL, "answer": {"findings": ["one"]}}
    Path(request["answer_file"]).unlink()
    assert _ask(ai.ChatTransport(tmp_path, job="00-0000")) == {"findings": ["one"]}     # from the cache


def test_chat_refuses_an_answer_that_breaks_the_schema(tmp_path):
    chat = ai.ChatTransport(tmp_path, job="00-0000")
    with pytest.raises(ai.NoAnswer):
        _ask(chat)
    key = _key(ai.CHAT_MODEL, "the question", "RULES\n\nSTEP")
    answer = tmp_path / "judge-chat" / "answers" / f"{key}.json"
    answer.parent.mkdir(parents=True)
    answer.write_text(json.dumps({"findings": "none"}), encoding="utf-8")
    with pytest.raises(ai.NoAnswer) as missing:
        _ask(ai.ChatTransport(tmp_path, job="00-0000"))
    assert missing.value.waiting and "the answer for QC could not be read" in missing.value.reason
    request = json.loads((tmp_path / "judge-chat" / "requests" / f"{key}.json").read_text(encoding="utf-8"))
    assert "findings" in request["previous_problem"]
    assert not (tmp_path / "judge" / f"{key}.json").exists()


def test_chat_asked_again_takes_the_request_out_of_old(tmp_path):
    key = _key(ai.CHAT_MODEL, "the question", "RULES\n\nSTEP")
    old = tmp_path / "judge-chat" / "requests" / "old" / f"{key}.json"
    old.parent.mkdir(parents=True)
    old.write_text("{}", encoding="utf-8")
    with pytest.raises(ai.NoAnswer):
        _ask(ai.ChatTransport(tmp_path, job="00-0000"))
    assert not old.exists()


def test_chat_lists_pictures_and_a_changed_picture_is_a_new_question(tmp_path):
    picture = tmp_path / "p.png"
    picture.write_bytes(PNG)
    chat = ai.ChatTransport(tmp_path, job="00-0000")
    with pytest.raises(ai.NoAnswer):
        _ask(chat, images=[picture])
    requests = list((tmp_path / "judge-chat" / "requests").glob("*.json"))
    assert len(requests) == 1
    assert json.loads(requests[0].read_text(encoding="utf-8"))["images"] == [str(picture)]
    picture.write_bytes(PNG + b"changed")
    with pytest.raises(ai.NoAnswer):
        _ask(chat, images=[picture])
    assert len(list((tmp_path / "judge-chat" / "requests").glob("*.json"))) == 2


# ---- the API transport ----------------------------------------------------------------------------------------

class _Block:
    def __init__(self, text):
        self.type, self.text = "text", text


class _Response:
    def __init__(self, text, stop="end_turn", model="claude-test"):
        self.content, self.stop_reason, self.model = [_Block(text)], stop, model


class _Stream:
    def __init__(self, response):
        self.response = response

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self.response


class FakeClient:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls: list[dict] = []
        self.messages = self

    def stream(self, **params):
        self.calls.append(params)
        return _Stream(self.responses.pop(0))


def test_api_caches_the_playbook_streams_and_answers_in_the_schema(tmp_path):
    client = FakeClient(_Response(json.dumps({"findings": ["a"]})))
    api = ai.ApiTransport(tmp_path, model="claude-test", client=client)
    picture = tmp_path / "p.png"
    picture.write_bytes(PNG)
    assert _ask(api, images=[picture]) == {"findings": ["a"]}
    (call,) = client.calls
    assert call["model"] == "claude-test"
    assert call["system"][0] == {"type": "text", "text": "RULES", "cache_control": {"type": "ephemeral"}}
    assert call["system"][1] == {"type": "text", "text": "STEP"}
    assert call["output_config"] == {"format": {"type": "json_schema", "schema": SCHEMA}}
    assert "temperature" not in call
    content = call["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": "the question"}
    assert any(block["type"] == "image" for block in content)
    assert _ask(api, images=[picture]) == {"findings": ["a"]}               # from the cache: no second call
    assert len(client.calls) == 1
    cached = list((tmp_path / "judge").glob("*.json"))
    assert json.loads(cached[0].read_text(encoding="utf-8"))["model"] == "claude-test"


@pytest.mark.parametrize("response, words", [
    (_Response(json.dumps({"findings": "x"})), "could not be read"),
    (_Response("{not json"), "could not be read"),
    (_Response("{}", stop="max_tokens"), "cut off"),
    (_Response("{}", stop="refusal"), "declined"),
])
def test_api_refuses_an_unusable_answer(tmp_path, response, words):
    api = ai.ApiTransport(tmp_path, model="claude-test", client=FakeClient(response))
    with pytest.raises(ai.NoAnswer) as failed:
        _ask(api)
    assert not failed.value.waiting and words in failed.value.reason and api.last_error
    assert not list((tmp_path / "judge").glob("*.json"))


def test_api_without_a_key_says_so(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ai.NoAnswer) as failed:
        _ask(ai.ApiTransport(tmp_path, model="claude-test"))
    assert "key" in failed.value.reason and not failed.value.waiting


def test_api_model_comes_from_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("ESTIMATOR_MODEL", "claude-from-env")
    assert ai.ApiTransport(tmp_path, client=FakeClient()).model == "claude-from-env"


# ---- write_system -------------------------------------------------------------------------------------------------

def test_write_system_asks_once_and_keeps_the_skeleton(job, raw, dossier, playbook):
    system = skeleton(job.system("EF"))
    answer = copy.deepcopy(raw["systems"][1])
    answer["name"] = "Something else"
    answer["families"] = []
    answer["alternate"] = "add"
    transport = FakeTransport(answer)
    evidence = ai.evidence_for(system, dossier)
    written = ai.write_system(system, evidence, playbook, transport)
    (asked,) = transport.asked
    assert asked["kind"] == ai.WRITE_SYSTEM and asked["name"] == "Exhaust Fans"
    assert asked["extra"]["step"] == "write" and asked["extra"]["plan_key"] == "EF"
    assert asked["schema"] == json_schema(System)
    assert asked["instructions"] == playbook.rules_text
    assert evidence.strip() in asked["prompt"] and "damper_actuator" in asked["prompt"]
    assert written.name == "Exhaust Fans" and written.families == system.families and written.alternate == "base"
    assert [d.id for d in written.devices] == ["EF.d1", "EF.d2", "EF.d3"] and written.tech_hours == 12.0


def test_write_system_attaches_the_pictures_its_evidence_names(job, raw, dossier, playbook):
    system = skeleton(job.system("VRF"))
    transport = FakeTransport(copy.deepcopy(raw["systems"][2]))
    ai.write_system(system, ai.evidence_for(system, dossier), playbook, transport)
    (asked,) = transport.asked
    assert [Path(p).name for p in asked["images"]] == ["I1.png"]
    assert asked["extra"]["images"][0]["id"] == "I1"


def _bad(raw, change):
    answer = copy.deepcopy(raw["systems"][1])
    change(answer)
    return answer


@pytest.mark.parametrize("change, words", [
    (lambda a: a["devices"][0].update(refs=[{"source_id": "S999", "quote": "x", "where": "y"}]), "S999"),
    (lambda a: a["devices"][0].update(slot="gadget"), "gadget"),
    (lambda a: a.update(clarifications=[{"kind": "note", "text": "a"}, {"kind": "note", "text": "b"}]),
     "clarification"),
    (lambda a: a["devices"][0].update(assumption={"what": "one per fan", "why": " "}), "why"),
    (lambda a: a["devices"][0].update(verb="Provide"), "verb"),
])
def test_write_system_refuses_an_answer_it_cannot_use(job, raw, dossier, playbook, change, words):
    system = skeleton(job.system("EF"))
    transport = FakeTransport(_bad(raw, change))
    with pytest.raises(ai.NoAnswer) as refused:
        ai.write_system(system, ai.evidence_for(system, dossier), playbook, transport)
    assert words in refused.value.reason and "the answer for Exhaust Fans" in refused.value.reason


def test_write_system_drops_a_ref_outside_the_evidence_when_another_holds(job, raw, dossier, playbook):
    system = skeleton(job.system("EF"))
    answer = _bad(raw, lambda a: a["devices"][0]["refs"].append({"source_id": "S999", "quote": "x", "where": "y"}))
    written = ai.write_system(system, ai.evidence_for(system, dossier), playbook, FakeTransport(answer))
    assert [r.source_id for r in written.devices[0].refs] == ["Q2"]


def test_write_system_gives_every_device_a_unique_id_of_its_system(job, raw, dossier, playbook):
    system = skeleton(job.system("EF"))
    answer = _bad(raw, lambda a: [a["devices"][1].update(id="EF.d1"), a["devices"][2].update(id="x7")])
    written = ai.write_system(system, ai.evidence_for(system, dossier), playbook, FakeTransport(answer))
    assert [d.id for d in written.devices] == ["EF.d1", "EF.d2", "EF.d3"]


def test_write_system_through_the_chat_rejects_and_asks_again(job, raw, dossier, playbook, tmp_path):
    system = skeleton(job.system("EF"))
    evidence = ai.evidence_for(system, dossier)
    cache = tmp_path / "cache"
    with pytest.raises(ai.NoAnswer):
        ai.write_system(system, evidence, playbook, ai.ChatTransport(cache, job="00-0000"))
    (request_file,) = (cache / "judge-chat" / "requests").glob("*.json")
    request = json.loads(request_file.read_text(encoding="utf-8"))
    assert request["kind"] == "write_system" and request["step"] == "write" and request["plan_key"] == "EF"
    assert request["system_prompt"].startswith(playbook.rules_text + "\n\n")
    answer = Path(request["answer_file"])
    answer.parent.mkdir(parents=True)
    answer.write_text(json.dumps(_bad(raw, lambda a: a["devices"][0].update(
        refs=[{"source_id": "S999", "quote": "x", "where": "y"}]))), encoding="utf-8")
    chat = ai.ChatTransport(cache, job="00-0000")
    with pytest.raises(ai.NoAnswer) as refused:
        ai.write_system(system, evidence, playbook, chat)
    assert refused.value.waiting and chat.waiting == 1
    again = json.loads(request_file.read_text(encoding="utf-8"))                    # asked again, with the reason
    assert "S999" in again["previous_problem"]
    assert not list((cache / "judge").glob("*.json"))                             # the bad answer is not kept
    answer.write_text(json.dumps(raw["systems"][1]), encoding="utf-8")
    written = ai.write_system(system, evidence, playbook, ai.ChatTransport(cache, job="00-0000"))
    assert len(written.devices) == 3 and not request_file.exists()


def test_write_system_through_the_api_retries_once_with_the_reason(job, raw, dossier, playbook, tmp_path):
    system = skeleton(job.system("EF"))
    bad = _bad(raw, lambda a: a["devices"][0].update(slot="gadget"))
    client = FakeClient(_Response(json.dumps(bad)), _Response(json.dumps(raw["systems"][1])))
    written = ai.write_system(system, ai.evidence_for(system, dossier), playbook,
                              ai.ApiTransport(tmp_path, model="claude-test", client=client))
    assert len(client.calls) == 2 and "gadget" in client.calls[1]["messages"][0]["content"][0]["text"]
    assert len(written.devices) == 3


def test_a_shapeless_system_takes_any_slot(job, raw, dossier, playbook):
    system = dataclasses.replace(skeleton(job.system("EF")), shape="")
    answer = _bad(raw, lambda a: a["devices"][0].update(slot="fan_controller"))
    transport = FakeTransport(answer)
    written = ai.write_system(system, ai.evidence_for(system, dossier), playbook, transport)
    assert written.devices[0].slot == "fan_controller" and written.shape == ""
    assert "no shape" in transport.asked[0]["prompt"].lower()


# ---- revise_system --------------------------------------------------------------------------------------------------

def test_revise_without_must_fix_returns_the_system_unasked(job, playbook):
    transport = FakeTransport()
    system = job.system("EF")
    findings = [Finding("Higher count prints", "EF", "EF.d1", "check", "w", "f"),
                Finding("Packaged units", "RTU", "RTU.d1", "must_fix", "w", "f")]
    assert ai.revise_system(system, findings, "evidence", playbook, transport) is system
    assert transport.asked == []


def test_revise_fixes_the_must_fix_only_and_keeps_everything_else(job, raw, dossier, playbook):
    system = job.system("EF")
    answer = copy.deepcopy(raw["systems"][1])
    answer["devices"][2]["name"] = "Motorized Damper Actuator (MD-1, MD-2)"         # the fix
    answer["devices"][0]["name"] = "Changed without being asked"                    # not asked: put back
    del answer["devices"][1]                                                          # not asked: put back
    transport = FakeTransport(answer)
    finding = Finding("Dampers under their fan", "EF", "EF.d3", "must_fix", "the damper line names no tags",
                      "name the dampers as the plan does")
    revised = ai.revise_system(system, [finding], ai.evidence_for(system, dossier), playbook, transport)
    (asked,) = transport.asked
    assert asked["kind"] == ai.WRITE_SYSTEM and asked["extra"]["step"] == "revise"
    assert asked["name"] == "Exhaust Fans (revise)" and "the damper line names no tags" in asked["prompt"]
    assert [d.id for d in revised.devices] == ["EF.d1", "EF.d2", "EF.d3"]
    assert revised.devices[0] == system.devices[0] and revised.devices[1] == system.devices[1]
    assert revised.devices[2].name == "Motorized Damper Actuator (MD-1, MD-2)"


def test_revise_for_the_whole_block_may_drop_a_line(job, raw, dossier, playbook):
    system = job.system("EF")
    answer = copy.deepcopy(raw["systems"][1])
    del answer["devices"][1]
    finding = Finding("Every line cites this job", "EF", None, "must_fix", "the start/stop line has no source",
                      "remove it")
    revised = ai.revise_system(system, [finding], ai.evidence_for(system, dossier), playbook, FakeTransport(answer))
    assert [d.id for d in revised.devices] == ["EF.d1", "EF.d3"]


# ---- qc_job ----------------------------------------------------------------------------------------------------------

def test_qc_asks_once_with_the_rule_names_and_checks_the_quotes(job, dossier, playbook):
    index = ai.evidence_index(dossier)
    answer = {"findings": [
        Finding("Higher count prints", "VRF", "VRF.d2", "check", "the map line has no count", "give it").to_dict(),
        Finding("Packaged units", "RTU", "RTU.d9", "must_fix", "a device the job lacks", "x").to_dict()]}
    transport = FakeTransport(answer)
    findings = ai.qc_job(job, index, playbook, transport)
    (asked,) = transport.asked
    assert asked["kind"] == ai.QC_JOB and asked["name"] == "QC" and asked["extra"]["step"] == "qc"
    items = asked["schema"]["properties"]["findings"]["items"]
    assert items["properties"]["rule"]["enum"] == list(playbook.rules)
    assert schema_errors(answer, asked["schema"]) == []
    assert "S7" in asked["prompt"] and "MD-1 interlocked with EF-1" in asked["prompt"]
    assert findings[0] == Finding("Higher count prints", "VRF", "VRF.d2", "check", "the map line has no count",
                                  "give it")
    assert findings[1].device_id is None and "RTU.d9" in findings[1].what
    assert len(findings) == 2                       # every quote of the fixture is in its source


def test_qc_finds_a_quote_its_source_does_not_hold(job, raw, dossier, playbook):
    raw["systems"][1]["devices"][2]["refs"][0]["quote"] = "MD-1 shall be a smoke damper"
    raw["systems"][1]["devices"][0]["refs"].append({"source_id": "S998", "quote": "x", "where": "y"})
    findings = ai.qc_job(Job.from_dict(raw), ai.evidence_index(dossier), playbook, FakeTransport({"findings": []}))
    assert [(f.rule, f.system_key, f.device_id, f.severity) for f in findings] == [
        ("Every line cites this job", "EF", "EF.d1", "must_fix"),
        ("Every line cites this job", "EF", "EF.d3", "must_fix")]
    assert "S998" in findings[0].what and "S7" in findings[1].what


def test_qc_leaves_the_plan_count_checks_own_refs_alone(raw, dossier, playbook):
    """bms.counts records its counts as refs ("C<n>", "located on the sheet text"): the app's own count, not words
    of a document, so the quote check passes them."""
    from bms.counts import LOCATED_QUOTE, NO_SOURCE_QUOTE, SEEN_QUOTE
    count = raw["systems"][0]["families"][0]["count"]
    count["others"] = [{"value": 9, "ref": {"source_id": "C1", "quote": SEEN_QUOTE, "where": "M-1 (picture)"}},
                       {"value": 8, "ref": {"source_id": "C2", "quote": LOCATED_QUOTE, "where": "M-1"}},
                       {"value": 7, "ref": {"source_id": "", "quote": NO_SOURCE_QUOTE, "where": ""}}]
    findings = ai.qc_job(Job.from_dict(raw), ai.evidence_index(dossier), playbook, FakeTransport({"findings": []}))
    assert findings == []


def test_qc_splits_a_long_job_into_parts(job, dossier, playbook, monkeypatch):
    monkeypatch.setattr(ai, "QC_PART_LIMIT", 2_000)
    transport = FakeTransport(*[{"findings": []}] * 10)
    assert ai.qc_job(job, ai.evidence_index(dossier), playbook, transport) == []
    names = [a["name"] for a in transport.asked]
    assert len(names) > 1 and names[0] == f"QC (part 1 of {len(names)})"
    for key in ("RTU", "EF", "VRF", "DH", "CUH"):
        assert sum(f'"key": "{key}"' in a["prompt"] for a in transport.asked) == 1


def test_qc_waits_when_the_chat_has_not_answered(job, dossier, playbook):
    with pytest.raises(ai.NoAnswer):
        ai.qc_job(job, ai.evidence_index(dossier), playbook, FakeTransport())


# ---- the prompts ------------------------------------------------------------------------------------------------------

def test_prompts_are_plain_and_carry_no_example_lines():
    folder = ROOT / "src" / "bms" / "prompts"
    for name in ("write_system.md", "revise_system.md", "qc_job.md"):
        text = (folder / name).read_text(encoding="utf-8")
        assert text.strip() and all(ord(c) < 0x2000 or c in "“”‘’—–…" for c in text), name
        assert not re.search(r"\b(?:Qty \(\d+\)|RTU-\d|AHU-\d|EF-\d)", text), name    # no example block lines


# ---- the run-job tool -------------------------------------------------------------------------------------------------

def test_run_job_check_holds_a_rebuilt_answer_to_its_whole_schema(tmp_path, raw):
    sys.path.insert(0, str(ROOT / "tools"))
    import run_job
    request, answer = tmp_path / "r.json", tmp_path / "a.json"
    request.write_text(json.dumps({"key": "k", "kind": ai.WRITE_SYSTEM, "step": "write",
                                   "schema": json_schema(System)}), encoding="utf-8")
    system = copy.deepcopy(raw["systems"][1])
    system["devices"][0]["verb"] = "Provide"
    answer.write_text(json.dumps(system), encoding="utf-8")
    assert "verb" in run_job.check_answer(answer, request)
    answer.write_text(json.dumps(raw["systems"][1]), encoding="utf-8")
    assert run_job.check_answer(answer, request) is None


def test_run_job_lists_the_reason_a_rebuilt_answer_was_refused(tmp_path):
    sys.path.insert(0, str(ROOT / "tools"))
    import run_job
    (tmp_path / "a.json").write_text(json.dumps(
        {"key": "a", "kind": "write_system", "step": "write", "job": "00-0000", "system": "Exhaust Fans",
         "previous_problem": "device EF.d1 cites S999", "answer_file": str(tmp_path / "none.json")}),
        encoding="utf-8")
    (waiting,) = run_job.waiting_requests(tmp_path, "00-0000", {})
    assert waiting["problem"] == "device EF.d1 cites S999" and waiting["step"] == "write"


def test_the_skill_sends_revise_requests_to_the_writer_and_passes_the_problem_on():
    text = (ROOT / ".claude" / "skills" / "run-job" / "SKILL.md").read_text(encoding="utf-8")
    assert "revise" in text and "writer_model" in text and "previous_problem" in text and "--app bms" in text


def test_the_repo_playbook_drives_the_qc_schema(job):
    playbook = load_playbook()
    schema = ai._qc_schema(job, playbook)
    assert schema["properties"]["findings"]["items"]["properties"]["rule"]["enum"] == list(playbook.rules)
    assert ai._citation_rule(playbook) in playbook.rules


def test_run_job_status_can_drive_the_rebuilt_app():
    sys.path.insert(0, str(ROOT / "tools"))
    import run_job
    assert run_job.estimate_command(Path("J"), Path("O"), Path("C"), "bms")[1:4] == ["-m", "bms", "estimate"]
    assert run_job.estimate_command(Path("J"), Path("O"), Path("C"), "estimator")[1:3] == ["-m", "estimator"]


def test_run_job_runs_the_rebuilt_app_by_default_and_checks_count_answers(tmp_path):
    sys.path.insert(0, str(ROOT / "tools"))
    import run_job
    from bms.counts_vision import SCHEMA
    assert run_job.estimate_command(Path("J"), Path("O"), Path("C"))[1:4] == ["-m", "bms", "estimate"]
    request = tmp_path / "r.json"
    request.write_text(json.dumps({"key": "k", "kind": "count_tags", "step": "count", "schema": SCHEMA}),
                       encoding="utf-8")
    good, bad = tmp_path / "good.json", tmp_path / "bad.json"
    good.write_text(json.dumps({"patterns": [{"pattern": "EF-[0-9]+", "tags": [
        {"text": "EF-1", "count": 1, "boxes": [{"tile": 1, "x": 1, "y": 2, "width": 3, "height": 4}]}]}]}),
                    encoding="utf-8")
    bad.write_text(json.dumps({"patterns": [{"pattern": "EF-[0-9]+", "tags": [{"text": "EF-1"}]}]}),
                   encoding="utf-8")
    assert run_job.check_answer(good, request) is None
    assert "schema" in run_job.check_answer(bad, request)
    settings = json.loads((ROOT / ".claude" / "run-job.json").read_text(encoding="utf-8"))
    assert {"judge_model", "writer_model", "qc_model", "count_model", "max_attempts"} <= set(settings)
    skill = (ROOT / ".claude" / "skills" / "run-job" / "SKILL.md").read_text(encoding="utf-8")
    assert "count_tags" in skill and "count_model" in skill and "--app estimator" in skill
