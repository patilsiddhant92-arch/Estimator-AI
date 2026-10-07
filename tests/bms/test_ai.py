"""Workstream 5: the AI steps (write, QC, revise), their evidence and the two transports, tested with fake
transports and a fake Anthropic client against the invented fixtures (no real job text)."""
from __future__ import annotations

import copy
import dataclasses
import json
import os
import re
import sys
import time
from pathlib import Path

import pytest

from estimator.reading.schedules import Schedule, ScheduleRow
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


def test_an_invented_schedule_is_a_table_of_columns_and_this_systems_rows(job, dossier):
    """When the reading's schedule objects are in hand, the evidence shows that table (its columns and the rows
    for this system's tags) instead of the flat dossier lines, and each row keeps its source id."""
    rows = (
        ScheduleRow("EF-1", {"TAG": "EF-1", "CFM": "500", "VOLTS": "115"}, None, None),
        ScheduleRow("EF-2", {"TAG": "EF-2", "CFM": "400", "VOLTS": "208"}, None, None),
        ScheduleRow("EF-3", {"TAG": "EF-3", "CFM": "300", "VOLTS": "460"}, None, None),
        ScheduleRow("RTU-1", {"TAG": "RTU-1", "CFM": "2000", "VOLTS": "480"}, None, None),
    )
    schedule = Schedule("Drawings.pdf", 1, "M-001", "EXHAUST FAN SCHEDULE", ("TAG", "CFM", "VOLTS"), rows, False,
                        ("Fans furnished with backdraft dampers.",), ())
    text_with_image = dossier.text.replace(
        "[S27] EXHAUST FAN SCHEDULE — M-001, Drawings.pdf page 1 (3 rows)\n    Columns: TAG | CFM",
        "[S27] EXHAUST FAN SCHEDULE — M-001, Drawings.pdf page 1 (3 rows)\n    See image I7.\n    Columns: TAG | CFM",
    )
    held = dataclasses.replace(dossier, text=text_with_image, schedules=(schedule,))
    text = ai.evidence_for(skeleton(job.system("EF")), held)
    assert "    | TAG | CFM | VOLTS |" in text
    assert "    | --- | --- | --- |" in text
    assert "[S28] | EF-1 | 500 | 115 |" in text
    assert "[S29] | EF-2 | 400 | 208 |" in text
    assert "[S30] | EF-3 | 300 | 460 |" in text
    assert "[S27]" in text and "[S40]" in text and "Fans furnished with backdraft dampers." in text
    assert "See image I7." in text
    assert "Columns: TAG | CFM" not in text
    assert "RTU-1" not in text and "2000" not in text and "[S25]" not in text


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


def test_evidence_for_a_system_with_no_plan_sheets_has_no_plan_devices_of_other_systems(job, dossier):
    """DH has no plan placements, so it is on no sheet: the devices counted on the plans are not its evidence."""
    ids = _ids(ai.evidence_for(skeleton(job.system("DH")), dossier))
    assert {"S13", "S20"} <= ids
    assert not ids & {"S36", "S43"}


def test_evidence_for_a_packaged_system_leaves_out_another_systems_integration_passage(job, dossier):
    """S38 integrates the VRF system: it is the VRF's, not the rooftop units'."""
    assert "S38" not in _ids(ai.evidence_for(skeleton(job.system("RTU")), dossier))
    assert "S38" in _ids(ai.evidence_for(skeleton(job.system("VRF")), dossier))


def test_evidence_for_reads_the_sections_from_the_text_when_the_dossier_has_none(job, dossier):
    bare = dataclasses.replace(dossier, sections={})
    for held in (bare, dossier):
        text = ai.evidence_for(skeleton(job.system("EF")), held)
        assert {"S18", "S19"} <= _ids(text) and "--- [Q2] B. EXHAUST FANS ---" in text
    # a section the planner cited by its Q id (not named by its heading) is found without the sections too
    system = skeleton(job.system("DH"))
    system = dataclasses.replace(system, sequence_refs=system.sequence_refs + (Ref("Q2", "start and stop", "p. 10"),))
    for held in (bare, dossier):
        text = ai.evidence_for(system, held)
        assert {"S18", "S19"} <= _ids(text) and "--- [Q2] B. EXHAUST FANS ---" in text


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


def test_a_resumed_ask_does_not_rewrite_a_request_that_is_still_waiting(tmp_path):
    """A run killed after the request was written must not ask the same question again."""
    first = ai.ChatTransport(tmp_path, job="00-0000")
    with pytest.raises(ai.NoAnswer):
        _ask(first)
    (request_file,) = (tmp_path / "judge-chat" / "requests").glob("*.json")
    written = request_file.read_bytes()
    stamped = request_file.stat().st_mtime_ns
    again = ai.ChatTransport(tmp_path, job="00-0000")
    with pytest.raises(ai.NoAnswer) as missing:
        _ask(again)
    assert missing.value.waiting and again.waiting == 1
    assert request_file.read_bytes() == written and request_file.stat().st_mtime_ns == stamped
    assert len(list((tmp_path / "judge-chat" / "requests").glob("*.json"))) == 1


def test_a_cached_answer_clears_a_request_left_behind_by_a_killed_run(tmp_path):
    chat = ai.ChatTransport(tmp_path, job="00-0000")
    with pytest.raises(ai.NoAnswer):
        _ask(chat)
    (request_file,) = (tmp_path / "judge-chat" / "requests").glob("*.json")
    answer = Path(json.loads(request_file.read_text(encoding="utf-8"))["answer_file"])
    answer.parent.mkdir(parents=True)
    answer.write_text(json.dumps({"findings": ["one"]}), encoding="utf-8")
    assert _ask(ai.ChatTransport(tmp_path, job="00-0000")) == {"findings": ["one"]}
    request_file.write_text('{"key": "left-behind"}', encoding="utf-8")
    assert _ask(ai.ChatTransport(tmp_path, job="00-0000")) == {"findings": ["one"]}
    assert not request_file.exists()


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
    (lambda a: a["devices"][0]["quantity"].update(value=0), "quantity"),
    (lambda a: a["devices"][1]["quantity"].update(value=-1), "quantity"),
    (lambda a: a.update(devices=[], no_scope_reason=None, tech_hours=None), "no_scope_reason"),
])
def test_write_system_refuses_an_answer_it_cannot_use(job, raw, dossier, playbook, change, words):
    system = skeleton(job.system("EF"))
    transport = FakeTransport(_bad(raw, change))
    with pytest.raises(ai.NoAnswer) as refused:
        ai.write_system(system, ai.evidence_for(system, dossier), playbook, transport)
    assert words in refused.value.reason and "the answer for Exhaust Fans" in refused.value.reason


# ---- normalised on intake, not refused --------------------------------------------------------------------------

def _written(job, raw, dossier, playbook, change):
    system = skeleton(job.system("EF"))
    return ai.write_system(system, ai.evidence_for(system, dossier), playbook, FakeTransport(_bad(raw, change)))


@pytest.mark.parametrize("kind, text, cleaned", [
    ("confirm", "Confirm: the fan count", "the fan count"),
    ("confirm", "CONFIRM QUANTITIES the fans and dampers", "QUANTITIES the fans and dampers"),     # content kept
    ("confirm", "Confirm ownership: who wires the dampers", "ownership: who wires the dampers"),
    ("confirm", "** Confirm quantity: the dampers", "quantity: the dampers"),
    ("assumed", "Assumed: one damper per fan", "one damper per fan"),
    ("assumed", "Assumption one damper per fan", "one damper per fan"),
    ("note", "Confirmation of the fan count is by the owner", "Confirmation of the fan count is by the owner"),
    ("per_drawings", "Quantity per plumbing drawings", "plumbing"),
    ("per_drawings", "plumbing drawings", "plumbing"),
    ("per_drawings", "per electrical drawings", "electrical"),
    ("per_drawings", "Quantity per: Mechanical drawings", "mechanical"),
])
def test_a_label_in_a_clarification_is_stripped_not_refused(job, raw, dossier, playbook, kind, text, cleaned):
    written = _written(job, raw, dossier, playbook, lambda a: a.update(clarifications=[{"kind": kind, "text": text}]))
    (clarification,) = written.clarifications
    assert clarification.kind == kind and clarification.text == cleaned


@pytest.mark.parametrize("kind, text", [("per_drawings", "Quantity per drawings"), ("confirm", "Confirm:"),
                                        ("assumed", "** Assumed")])
def test_a_clarification_empty_after_its_label_is_dropped(job, raw, dossier, playbook, kind, text):
    written = _written(job, raw, dossier, playbook, lambda a: a.update(clarifications=[{"kind": kind, "text": text}]))
    assert written.clarifications == () and len(written.devices) == 3


def test_a_label_in_an_assumption_is_stripped(job, raw, dossier, playbook):
    written = _written(job, raw, dossier, playbook, lambda a: a["devices"][0].update(
        assumption={"what": "Assumed: one per fan", "why": "Assumption: the schedule lists three"}))
    assert written.devices[0].assumption.what == "one per fan"
    assert written.devices[0].assumption.why == "the schedule lists three"


def _refused(system, dossier, playbook, answer, **kw) -> str:
    """The reason the intake refuses `answer` (the writer is asked again with it)."""
    with pytest.raises(ai.NoAnswer) as refused:
        ai.write_system(system, ai.evidence_for(system, dossier), playbook, FakeTransport(answer), **kw)
    return refused.value.reason


def _with_no_source_other(system):
    """The system with a count record the plan check gave without a source (an empty Ref id, bms.counts)."""
    from bms.counts import NO_SOURCE_QUOTE
    from bms.model import OtherCount
    family, *rest = system.families
    count = dataclasses.replace(family.count, others=family.count.others + (OtherCount(9, Ref("", NO_SOURCE_QUOTE, "")),))
    return dataclasses.replace(system, families=(dataclasses.replace(family, count=count), *rest))


def test_a_count_with_no_source_prints_no_empty_fact_in_the_evidence(job, dossier):
    system = _with_no_source_other(skeleton(job.system("EF")))
    text = ai.evidence_for(system, dossier)
    assert not [line for line in text.splitlines() if line.startswith("[]")]
    assert "the count before the plan check" not in text


def test_a_device_citing_an_empty_source_id_is_refused(job, raw, dossier, playbook):
    system = _with_no_source_other(skeleton(job.system("EF")))
    answer = _bad(raw, lambda a: a["devices"][0].update(refs=[{"source_id": "", "quote": "x", "where": "y"}]))
    reason = _refused(system, dossier, playbook, answer)
    assert "not in this system's evidence" in reason


def test_a_source_id_in_client_text_is_refused_not_rewritten(job, raw, dossier, playbook):
    def change(a):
        a["devices"][2]["assumption"] = {"what": "one damper per fan", "why": "as shown on [S7]"}
        a["clarifications"] = [{"kind": "confirm", "text": "the fan count on S6 and the sequence in Q2"}]
    reason = _refused(skeleton(job.system("EF")), dossier, playbook, _bad(raw, change))
    assert "assumption why prints the source id S7" in reason
    assert "confirm clarification prints the source ids S6, Q2" in reason
    assert "name the document in words; cite it as a Ref, never print an id" in reason


@pytest.mark.parametrize("why, named", [
    ("per S141 and Q2", "S141, Q2"),
    ("the ledger fact F17", "F17"),
    ("the picture I9 shows it", "I9"),
    ("the schedule, see C4", "C4"),
    ("the schedule (S999)", "S999"),
])
def test_a_source_id_without_a_place_is_refused(job, raw, dossier, playbook, why, named):
    # the run issued these ids (refs that name no document)
    system = _with(skeleton(job.system("EF")), *(Ref(i, "x", "ledger fact") for i in ("S141", "F17", "I9", "C4",
                                                                                         "S999")))
    answer = _bad(raw, lambda a: a["devices"][0].update(assumption={"what": "one per fan", "why": why}))
    assert f"prints the source id{'s' if ',' in named else ''} {named}:" in _refused(system, dossier, playbook, answer)


def test_a_ledger_fact_id_is_refused(job, raw, dossier, playbook):
    def change(a):
        a["devices"][0]["refs"].append({"source_id": "F17", "quote": "x", "where": "ledger fact"})
        a["devices"][0]["assumption"] = {"what": "one per fan", "why": "the fans are on F17"}
    system = dataclasses.replace(skeleton(job.system("EF")), sequence_refs=skeleton(job.system("EF")).sequence_refs
                                 + (Ref("F17", "x", "ledger fact"),))
    assert "prints the source id F17" in _refused(system, dossier, playbook, _bad(raw, change))


def test_a_source_id_in_the_no_scope_reason_is_refused(job, raw, dossier, playbook):
    system = _with(skeleton(job.system("EF")), Ref("S999", "x", "ledger fact"))
    answer = _bad(raw, lambda a: a.update(devices=[], clarifications=[], tech_hours=None,
                                          no_scope_reason="The fans run on their own controls (S999)."))
    assert "no_scope_reason prints the source id S999" in _refused(system, dossier, playbook, answer)


def test_an_unknown_quantity_is_kept(job, raw, dossier, playbook):
    written = _written(job, raw, dossier, playbook, lambda a: a["devices"][0]["quantity"].update(value=None))
    assert written.devices[0].quantity.value is None


def test_every_cleanup_is_logged_beside_the_cache(job, raw, dossier, playbook, tmp_path):
    system = skeleton(job.system("EF"))
    evidence = ai.evidence_for(system, dossier)
    cache = tmp_path / "cache"
    with pytest.raises(ai.NoAnswer):
        ai.write_system(system, evidence, playbook, ai.ChatTransport(cache, job="00-0000"))
    (request_file,) = (cache / "judge-chat" / "requests").glob("*.json")
    answer = Path(json.loads(request_file.read_text(encoding="utf-8"))["answer_file"])
    answer.parent.mkdir(parents=True)
    answer.write_text(json.dumps(_bad(raw, lambda a: a.update(
        clarifications=[{"kind": "per_drawings", "text": "Quantity per plumbing drawings"}]))), encoding="utf-8")
    chat = ai.ChatTransport(cache, job="00-0000")
    written = ai.write_system(system, evidence, playbook, chat)
    assert written.clarifications[0].text == "plumbing"
    assert chat.answered_in_chat == 1 and chat.waiting == 0 and not request_file.exists()    # accepted first time
    (entry,) = json.loads((cache / "intake.json").read_text(encoding="utf-8"))
    assert entry["system"] == "Exhaust Fans" and "Quantity per plumbing drawings" in entry["change"]
    assert "plumbing" in entry["change"]
    again = ai.ChatTransport(cache, job="00-0000")                     # a new run starts a new log
    assert not (cache / "intake.json").exists()
    ai.write_system(system, evidence, playbook, again)                 # from the cache: cleaned and logged again
    assert len(json.loads((cache / "intake.json").read_text(encoding="utf-8"))) == 1


def test_a_clean_answer_logs_nothing(job, raw, dossier, playbook, tmp_path):
    system = skeleton(job.system("EF"))
    client = FakeClient(_Response(json.dumps(raw["systems"][1])))
    transport = ai.ApiTransport(tmp_path, model="claude-test", client=client)
    ai.write_system(system, ai.evidence_for(system, dossier), playbook, transport)
    assert transport.intake == [] and not (tmp_path / "intake.json").exists()


def test_the_writer_prompts_no_longer_threaten_refusal_for_labels():
    folder = ROOT / "src" / "bms" / "prompts"
    for name in ("write_system.md", "revise_system.md"):
        label_lines = [line for line in (folder / name).read_text(encoding="utf-8").splitlines()
                       if "label" in line.lower()]
        assert label_lines, name                                   # the label rule is still stated
        for line in label_lines:
            assert "refus" not in line.lower(), (name, line)
            assert '"Confirm"' in line and '"Assumed:"' in line, (name, line)
    write = (folder / "write_system.md").read_text(encoding="utf-8")
    # the intake keeps a per-drawings text's discipline word only, and the writer is told so
    assert ('Never start the text with a label ("Confirm", "Assumed:", "Note:", "Quantity"): the kind is the label '
            'and the renderer prints it. For per_drawings the text is the discipline word only ("plumbing", '
            '"electrical").') in write


# ---- the shared cleanup: only ids this run issued are source ids; each kind strips its own label ----------------

def _with(system: System, *refs: Ref, tags: tuple[str, ...] | None = None) -> System:
    """The skeleton with more refs issued (as sequence refs) and, when given, more tags on its first family."""
    families = system.families
    if tags is not None:
        families = (dataclasses.replace(families[0], tags=families[0].tags + tags),) + families[1:]
    return dataclasses.replace(system, sequence_refs=system.sequence_refs + refs, families=families)


def test_a_confirm_clarification_keeps_its_content_words(job, raw, dossier, playbook):
    """I3: only the bare label word (and its colon) comes off; 'ownership' and 'quantity' are content."""
    from bms.render import render
    house = load_playbook(ROOT / "playbook")
    for kind, text, cleaned, printed in [
        ("confirm", "Confirm ownership of the duct smoke detectors with the electrical contractor.",
         "ownership of the duct smoke detectors with the electrical contractor.",
         "*Confirm ownership of the duct smoke detectors with the electrical contractor"),
        ("confirm", "Confirm quantity: 4 invented dampers", "quantity: 4 invented dampers",
         "*Confirm quantity: 4 invented dampers"),
        ("confirm", "*Confirm: quantities of the invented dampers", "quantities of the invented dampers",
         "*Confirm quantities of the invented dampers"),
        ("note", "Confirm with the owner the invented fan count", "Confirm with the owner the invented fan count",
         "**Confirm with the owner the invented fan count"),
        ("note", "Assumption of the owner: invented fans", "Assumption of the owner: invented fans",
         "**Assumption of the owner: invented fans"),
    ]:
        written = _written(job, raw, dossier, playbook,
                           lambda a: a.update(clarifications=[{"kind": kind, "text": text}]))
        assert written.clarifications[0].text == cleaned, text
        out = render(dataclasses.replace(job, systems=(written,)), house)
        assert [l.text for l in out.lines if l.kind == "note"][0] == printed, text


def test_an_id_whose_where_names_no_place_is_refused(job, raw, dossier, playbook):
    """I4: 'Ledger fact F17' and 'Picture I3, file M-201.png' name no document; the id is refused, never printed."""
    system = _with(skeleton(job.system("EF")), Ref("F17", "x", "Ledger fact F17"),
                   Ref("I3", "x", "Picture I3, file M-201.png"))

    def change(a):
        a["devices"][0]["assumption"] = {"what": "one per fan", "why": "as stated in F17"}
        a["clarifications"] = [{"kind": "confirm", "text": "the actuator shown on I3"}]
    reason = _refused(system, dossier, playbook, _bad(raw, change))
    assert "prints the source id F17" in reason and "prints the source id I3" in reason


def test_tags_and_sheet_numbers_shaped_like_ids_survive_the_intake(job, raw, dossier, playbook):
    """I5: F1, F2 are not issued ids and C101 (unissued) reads as a sheet number."""
    system = skeleton(job.system("EF"))
    text = "Fans F1 and F2 serve the kitchen; see civil sheet C101."
    written = ai.write_system(system, ai.evidence_for(system, dossier), playbook, FakeTransport(
        _bad(raw, lambda a: a.update(clarifications=[{"kind": "note", "text": text}]))))
    assert written.clarifications[0].text == text


def test_an_issued_id_after_a_sheet_word_is_a_sheet_number_only_when_the_job_knows_the_sheet(job, raw, dossier,
                                                                                              playbook):
    """S ids number every dossier line, so a real sheet "C101" or "S12" collides with an issued id. The estimator's
    ruling of 2026-10-05 let the sheet word win; the lead's ruling on L-D (lead/final-c) keeps it a sheet only when
    it is a known sheet of the job (K, which the run passes as `sheets`), else it is refused like any issued id."""
    system = _with(skeleton(job.system("EF")), Ref("C101", "x", "ledger fact"))
    text = "Fans serve the kitchen; see civil sheet C101."
    answer = _bad(raw, lambda a: a.update(clarifications=[{"kind": "note", "text": text}]))
    written = ai.write_system(system, ai.evidence_for(system, dossier), playbook, FakeTransport(answer),
                              sheets=("C101",))
    assert written.clarifications[0].text == text
    assert "prints the source id C101" in _refused(system, dossier, playbook, answer)


def test_a_family_tag_shaped_like_an_id_survives_the_intake_even_when_issued(job, raw, dossier, playbook):
    tags = ("F1", "C2", "I3", "Q4", "S5")
    system = _with(skeleton(job.system("EF")), *(Ref(t, "x", "ledger fact") for t in tags), tags=tags)
    text = "the controls for units F1, C2, I3, Q4 and S5"
    written = ai.write_system(system, ai.evidence_for(system, dossier), playbook, FakeTransport(
        _bad(raw, lambda a: a.update(clarifications=[{"kind": "confirm", "text": text}]))))
    assert written.clarifications[0].text == text


# ---- a source id in client text: refused, never rewritten ----------------------------------------------------------

def test_an_unissued_id_joined_to_an_issued_one_is_refused_and_a_loose_one_kept(job, raw, dossier, playbook):
    """C1 under the ruling of 2026-10-05: S998 was never issued; joined to the issued Q2 it is a citation, refused.
    A lookalike on its own ("Fan C2 serves the lab", "see S998") is accepted as written."""
    def change(a):
        a["devices"][0]["assumption"] = {"what": "one per fan", "why": "the sequence, see Q2 and S998"}
        a["devices"][1]["assumption"] = {"what": "one per fan", "why": "Fan C2 serves the lab"}
    system = skeleton(job.system("EF"))
    reason = _refused(system, dossier, playbook, _bad(raw, change))
    assert "assumption why prints the source ids Q2, S998" in reason and "C2" not in reason
    written = ai.write_system(system, ai.evidence_for(system, dossier), playbook, FakeTransport(_bad(
        raw, lambda a: a["devices"][1].update(assumption={"what": "one per fan", "why": "Fan C2 serves the lab"}))))
    assert written.devices[1].assumption.why == "Fan C2 serves the lab"


@pytest.mark.parametrize("why, named", [
    ("per S141 and Q2", "S141, Q2"),         # the issued Q2, and S141 joined to it
    ("the schedule, see C4", ""),            # ruling 2026-10-05: an unissued lookalike after a cue word is accepted
    ("the schedule (S999)", ""),             # and in a bracket group
    ("the schedule [S998, S999]", ""),
])
def test_only_an_issued_id_or_one_joined_to_it_is_refused(job, raw, dossier, playbook, why, named):
    answer = _bad(raw, lambda a: a["devices"][0].update(assumption={"what": "one per fan", "why": why}))
    system = skeleton(job.system("EF"))
    if not named:
        written = ai.write_system(system, ai.evidence_for(system, dossier), playbook, FakeTransport(answer))
        assert written.devices[0].assumption.why == why
        return
    reason = _refused(system, dossier, playbook, answer)
    assert f"prints the source id{'s' if ',' in named else ''} {named}:" in reason


@pytest.mark.parametrize("text", ["the fans run (see C2 in the lab)", "the fans run (C2 in the lab)",
                                  "the fans run, see C2 in the lab"])
@pytest.mark.parametrize("tags", [(), ("C2",)], ids=["C2-no-tag", "C2-a-tag"])
def test_an_id_in_a_bracket_or_after_a_cue_word_at_intake(job, raw, dossier, playbook, text, tags):
    """The estimator's ruling of 2026-10-05 for "(see C2 in the lab)": C2 is no issued id, so it is accepted as
    written whether or not it is a tag of the job (before the ruling, C2 no tag was refused as a citation)."""
    system = skeleton(job.system("EF"))
    answer = _bad(raw, lambda a: a.update(clarifications=[{"kind": "note", "text": text}]))
    written = ai.write_system(system, ai.evidence_for(system, dossier), playbook, FakeTransport(answer), tags=tags)
    assert written.clarifications[0].text == text


def test_a_device_name_that_is_only_an_id_is_refused_with_a_plain_reason(job, raw, dossier, playbook):
    """m-4: no empty "Furnish and Install" line; the writer is asked again, told why."""
    system = _with(skeleton(job.system("EF")), Ref("F1", "x", "ledger fact"))
    answer = _bad(raw, lambda a: a["devices"][0].update(name="F1"))
    assert "name prints the source id F1" in _refused(system, dossier, playbook, answer)


def test_the_intake_protects_the_job_wide_tags_it_is_given(job, raw, dossier, playbook):
    """I2: C2 is issued in this system's evidence but is a fan tag of another system: the run passes every tag."""
    system = _with(skeleton(job.system("EF")), Ref("C2", "x", "ledger fact"))
    answer = _bad(raw, lambda a: a.update(clarifications=[{"kind": "note", "text": "Fan C2 serves the lab"}]))
    written = ai.write_system(system, ai.evidence_for(system, dossier), playbook, FakeTransport(answer),
                              tags=("EF-1", "C2"))
    assert written.clarifications[0].text == "Fan C2 serves the lab"


def test_the_intake_refuses_an_id_in_a_device_name_and_cleans_label_residue(job, raw, dossier, playbook):
    """I4: a device name with a source id is refused. M1: no punctuation is left after a label; 'Assumption-based'
    is a word, not a label."""
    named = _bad(raw, lambda a: a["devices"][0].update(name="Control Valve per Q2"))
    assert "name prints the source id Q2" in _refused(skeleton(job.system("EF")), dossier, playbook, named)

    def change(a):
        a["devices"][0]["assumption"] = {"what": "Assumption-based count", "why": "Assumed - two valves"}
        a["clarifications"] = [{"kind": "confirm", "text": "**Confirm**: ownership of valves"}]
    written = _written(job, raw, dossier, playbook, change)
    assert written.devices[0].assumption.what == "Assumption-based count"
    assert written.devices[0].assumption.why == "two valves"
    assert written.clarifications[0].text == "ownership of valves"


def test_a_block_with_nothing_to_scope_keeps_its_reason(job, raw, dossier, playbook):
    system = skeleton(job.system("EF"))
    answer = _bad(raw, lambda a: a.update(devices=[], clarifications=[], tech_hours=None,
                                          no_scope_reason="The fans run on their own controls; the sequence asks "
                                                          "nothing of the BMS."))
    written = ai.write_system(system, ai.evidence_for(system, dossier), playbook, FakeTransport(answer))
    assert written.devices == () and written.no_scope_reason.startswith("The fans run")


def test_a_block_with_lines_carries_no_no_scope_reason(job, raw, dossier, playbook):
    system = skeleton(job.system("EF"))
    answer = _bad(raw, lambda a: a.update(no_scope_reason="nothing to do"))
    written = ai.write_system(system, ai.evidence_for(system, dossier), playbook, FakeTransport(answer))
    assert len(written.devices) == 3 and written.no_scope_reason is None


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


_LAST_STAMP = [0]


def _stamp(path: Path, seconds: int) -> None:
    """Put the file's mtime `seconds` ahead of the clock, past any request written during this test.

    Never earlier than the last stamp, so a slow machine cannot make a later answer older than an earlier one."""
    mtime = max(time.time_ns() + seconds * 1_000_000_000, _LAST_STAMP[0] + 1_000_000_000)
    _LAST_STAMP[0] = mtime
    os.utime(path, ns=(mtime, mtime))


def test_a_check_refusal_stops_after_max_attempts_and_names_the_request(job, raw, dossier, playbook, tmp_path):
    """Three newer refused answers (the repo's max_attempts) stop the run. The message names the request.
    The same answer file is not read again: a re-run waits, and a newer good answer is accepted."""
    system = skeleton(job.system("EF"))
    evidence = ai.evidence_for(system, dossier)
    cache = tmp_path / "cache"
    with pytest.raises(ai.NoAnswer):
        ai.write_system(system, evidence, playbook, ai.ChatTransport(cache, job="00-0000"))
    (request_file,) = (cache / "judge-chat" / "requests").glob("*.json")
    answer = Path(json.loads(request_file.read_text(encoding="utf-8"))["answer_file"])
    answer.parent.mkdir(parents=True, exist_ok=True)
    answer.write_text(json.dumps(_bad(raw, lambda a: a["devices"][0].update(slot="gadget"))), encoding="utf-8")
    _stamp(answer, 10)
    for seconds in (20, 30):
        with pytest.raises(ai.NoAnswer) as refused:
            ai.write_system(system, evidence, playbook, ai.ChatTransport(cache, job="00-0000"))
        assert refused.value.waiting
        _stamp(answer, seconds)
    with pytest.raises(ai.NoAnswer) as stopped:
        ai.write_system(system, evidence, playbook, ai.ChatTransport(cache, job="00-0000"))
    assert not stopped.value.waiting
    assert "Stopped" in stopped.value.reason and "Exhaust Fans" in stopped.value.reason
    assert list((cache / "judge-chat" / "requests").glob("*.json")) == []

    with pytest.raises(ai.NoAnswer) as waiting:
        ai.write_system(system, evidence, playbook, ai.ChatTransport(cache, job="00-0000"))
    assert waiting.value.waiting and "Stopped" not in waiting.value.reason
    assert list((cache / "judge-chat" / "requests").glob("*.json"))

    answer.write_text(json.dumps(raw["systems"][1]), encoding="utf-8")
    _stamp(answer, 40)
    written = ai.write_system(system, evidence, playbook, ai.ChatTransport(cache, job="00-0000"))
    assert len(written.devices) == 3


def test_revise_source_id_refusal_is_actionable_and_stops_at_three(job, raw, dossier, playbook, tmp_path):
    """From Luna's review (luna/review-006 0d11239), unchanged: after the stop the API is not called a fourth time."""
    system = job.system("EF")
    bad = _bad(raw, lambda a: a["devices"][2].update(name="Motorized damper S999"))
    client = FakeClient(*(_Response(json.dumps(bad)) for _ in range(4)))
    transport = ai.ApiTransport(tmp_path, model="claude-test", client=client)
    finding = Finding("Every line cites this job", "EF", "EF.d3", "must_fix", "missing detail",
                      "name the document in words")
    args = (system, [finding], ai.evidence_for(system, dossier), playbook, transport)

    with pytest.raises(ai.NoAnswer) as retry:
        ai.revise_system(*args, ids=("S999",))
    assert len(client.calls) == 2
    retry_prompt = client.calls[1]["messages"][0]["content"][0]["text"]
    assert "S999" in retry_prompt and "name the document in words" in retry_prompt

    with pytest.raises(ai.NoAnswer) as stopped:
        ai.revise_system(*args, ids=("S999",))
    assert len(client.calls) == 3
    assert not stopped.value.waiting
    assert "Stopped" in stopped.value.reason and "Exhaust Fans (revise)" in stopped.value.reason
    assert "3 times" in stopped.value.reason and "S999" in stopped.value.reason

    with pytest.raises(ai.NoAnswer) as still_stopped:
        ai.revise_system(*args, ids=("S999",))
    assert len(client.calls) == 3
    assert "Stopped" in still_stopped.value.reason and "3 times" in still_stopped.value.reason


def test_a_new_api_transport_after_the_stop_does_not_call_again(job, raw, dossier, playbook, tmp_path):
    """The count is saved: a later run (a new transport on the same cache) is stopped before it calls."""
    system = skeleton(job.system("EF"))
    bad = _bad(raw, lambda a: a["devices"][0].update(slot="gadget"))
    client = FakeClient(*(_Response(json.dumps(bad)) for _ in range(5)))
    evidence = ai.evidence_for(system, dossier)
    for _ in range(2):
        with pytest.raises(ai.NoAnswer):
            ai.write_system(system, evidence, playbook, ai.ApiTransport(tmp_path, model="claude-test", client=client))
    assert len(client.calls) == 3
    with pytest.raises(ai.NoAnswer) as again:
        ai.write_system(system, evidence, playbook, ai.ApiTransport(tmp_path, model="claude-test", client=client))
    assert len(client.calls) == 3
    assert not again.value.waiting and "Stopped" in again.value.reason and "3 times" in again.value.reason


def test_a_chat_rerun_after_the_stop_with_the_same_refused_answer_records_no_new_refusal(job, raw, dossier,
                                                                                          playbook, tmp_path):
    """Chat waits again after a stop (by design: a newer answer starts a fresh count). The refused answer put
    back with its old time is not read again, so the counter stays at the cap."""
    system = skeleton(job.system("EF"))
    evidence = ai.evidence_for(system, dossier)
    cache = tmp_path / "cache"
    with pytest.raises(ai.NoAnswer):
        ai.write_system(system, evidence, playbook, ai.ChatTransport(cache, job="00-0000"))
    (request_file,) = (cache / "judge-chat" / "requests").glob("*.json")
    answer = Path(json.loads(request_file.read_text(encoding="utf-8"))["answer_file"])
    answer.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(_bad(raw, lambda a: a["devices"][0].update(slot="gadget")))
    stopped = None
    for seconds in (10, 20, 30):
        answer.write_text(text, encoding="utf-8")
        _stamp(answer, seconds)
        with pytest.raises(ai.NoAnswer) as stopped:
            ai.write_system(system, evidence, playbook, ai.ChatTransport(cache, job="00-0000"))
    assert stopped is not None and not stopped.value.waiting
    (counter,) = (cache / "judge" / "attempts").glob("*.json")
    saved = json.loads(counter.read_text(encoding="utf-8"))
    assert saved["attempts"] == 3
    answer.write_text(text, encoding="utf-8")
    os.utime(answer, ns=(saved["answer_mtime_ns"], saved["answer_mtime_ns"]))
    with pytest.raises(ai.NoAnswer) as waiting:
        ai.write_system(system, evidence, playbook, ai.ChatTransport(cache, job="00-0000"))
    assert waiting.value.waiting
    assert json.loads(counter.read_text(encoding="utf-8"))["attempts"] == 3


def test_a_second_prompt_keeps_its_refusal_count_when_the_first_succeeds(job, raw, dossier, playbook, tmp_path):
    """The first write and a later prompt do not share a counter. A success must not wipe the other count.
    A stop names the counter file, and the stale answer file is removed."""
    system = skeleton(job.system("EF"))
    evidence = ai.evidence_for(system, dossier)
    cache = tmp_path / "cache"
    chat = ai.ChatTransport(cache, job="00-0000")
    with pytest.raises(ai.NoAnswer):
        ai.write_system(system, evidence, playbook, chat)
    (request_file,) = (cache / "judge-chat" / "requests").glob("*.json")
    answer = Path(json.loads(request_file.read_text(encoding="utf-8"))["answer_file"])
    answer.parent.mkdir(parents=True, exist_ok=True)
    answer.write_text(json.dumps(_bad(raw, lambda a: a["devices"][0].update(slot="gadget"))), encoding="utf-8")
    _stamp(answer, 10)
    with pytest.raises(ai.NoAnswer):
        ai.write_system(system, evidence, playbook, ai.ChatTransport(cache, job="00-0000"))
    (counter,) = (cache / "judge" / "attempts").glob("*.json")
    assert json.loads(counter.read_text(encoding="utf-8"))["attempts"] == 1

    other = evidence + "\nA later invented sentence."
    with pytest.raises(ai.NoAnswer):
        ai.write_system(system, other, playbook, ai.ChatTransport(cache, job="00-0000"))
    other_request = next(path for path in (cache / "judge-chat" / "requests").glob("*.json")
                         if "later invented" in path.read_text(encoding="utf-8"))
    other_answer = Path(json.loads(other_request.read_text(encoding="utf-8"))["answer_file"])
    other_answer.parent.mkdir(parents=True, exist_ok=True)
    other_answer.write_text(json.dumps(raw["systems"][1]), encoding="utf-8")
    _stamp(other_answer, 20)
    ai.write_system(system, other, playbook, ai.ChatTransport(cache, job="00-0000"))
    assert counter.is_file() and json.loads(counter.read_text(encoding="utf-8"))["attempts"] == 1

    stopped = None
    for seconds in (30, 40, 50):
        answer.write_text(json.dumps(_bad(raw, lambda a: a["devices"][0].update(slot="gadget"))), encoding="utf-8")
        _stamp(answer, seconds)
        with pytest.raises(ai.NoAnswer) as stopped:
            ai.write_system(system, evidence, playbook, ai.ChatTransport(cache, job="00-0000"))
        if not stopped.value.waiting:
            break
    assert stopped is not None and not stopped.value.waiting
    assert "attempts" in stopped.value.reason and str(counter) in stopped.value.reason
    assert not answer.exists()


def test_a_locked_request_file_does_not_crash_a_cached_answer(job, raw, dossier, playbook, tmp_path, monkeypatch):
    system = skeleton(job.system("EF"))
    evidence = ai.evidence_for(system, dossier)
    cache = tmp_path / "cache"
    with pytest.raises(ai.NoAnswer):
        ai.write_system(system, evidence, playbook, ai.ChatTransport(cache, job="00-0000"))
    (request_file,) = (cache / "judge-chat" / "requests").glob("*.json")
    answer = Path(json.loads(request_file.read_text(encoding="utf-8"))["answer_file"])
    answer.parent.mkdir(parents=True, exist_ok=True)
    answer.write_text(json.dumps(raw["systems"][1]), encoding="utf-8")
    _stamp(answer, 10)
    written = ai.write_system(system, evidence, playbook, ai.ChatTransport(cache, job="00-0000"))
    assert len(written.devices) == 3

    real = Path.unlink

    def locked(self, *args, **kwargs):
        if self.parent.name == "requests":
            raise PermissionError("locked")
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", locked)
    (cache / "judge-chat" / "requests").mkdir(parents=True, exist_ok=True)
    request_file.write_text("{}", encoding="utf-8")
    again = ai.write_system(system, evidence, playbook, ai.ChatTransport(cache, job="00-0000"))
    assert len(again.devices) == 3


def test_the_api_stops_after_max_attempts_instead_of_calling_again(job, raw, dossier, playbook, tmp_path):
    system = skeleton(job.system("EF"))
    bad = _bad(raw, lambda a: a["devices"][0].update(slot="gadget"))
    client = FakeClient(*(_Response(json.dumps(bad)) for _ in range(4)))
    transport = ai.ApiTransport(tmp_path, model="claude-test", client=client)
    evidence = ai.evidence_for(system, dossier)
    with pytest.raises(ai.NoAnswer) as failed:
        ai.write_system(system, evidence, playbook, transport)
    assert len(client.calls) == 2 and not failed.value.waiting and "Stopped" not in failed.value.reason
    with pytest.raises(ai.NoAnswer) as stopped:
        ai.write_system(system, evidence, playbook, transport)
    assert len(client.calls) == 3
    assert not stopped.value.waiting and "Exhaust Fans" in stopped.value.reason and "Stopped" in stopped.value.reason


def test_write_system_through_the_api_retries_once_with_the_reason(job, raw, dossier, playbook, tmp_path):
    system = skeleton(job.system("EF"))
    bad = _bad(raw, lambda a: a["devices"][0].update(slot="gadget"))
    client = FakeClient(_Response(json.dumps(bad)), _Response(json.dumps(raw["systems"][1])))
    written = ai.write_system(system, ai.evidence_for(system, dossier), playbook,
                              ai.ApiTransport(tmp_path, model="claude-test", client=client))
    assert len(client.calls) == 2 and "gadget" in client.calls[1]["messages"][0]["content"][0]["text"]
    assert len(written.devices) == 3


def test_an_api_answer_that_passes_on_the_retry_is_reused_by_the_next_run(job, raw, dossier, playbook, tmp_path):
    """AI-7: the good answer to the retry is kept under the question itself, so identical inputs give the same job."""
    system = skeleton(job.system("EF"))
    evidence = ai.evidence_for(system, dossier)
    bad = _bad(raw, lambda a: a["devices"][0].update(slot="gadget"))
    good_a = raw["systems"][1]
    good_b = _bad(raw, lambda a: a["devices"][0].update(name="An invented other answer"))
    first = FakeClient(_Response(json.dumps(bad)), _Response(json.dumps(good_a)))
    one = ai.write_system(system, evidence, playbook, ai.ApiTransport(tmp_path, model="claude-test", client=first))
    assert len(first.calls) == 2
    second = FakeClient(_Response(json.dumps(good_b)))
    two = ai.write_system(system, evidence, playbook, ai.ApiTransport(tmp_path, model="claude-test", client=second))
    assert second.calls == []
    assert [d.name for d in two.devices] == [d.name for d in one.devices]


def test_a_schema_invalid_api_answer_is_counted_fed_back_and_stops(job, dossier, playbook, tmp_path):
    """AI-8: an answer that breaks the schema is a refusal like any other: the retry carries the reason, the count
    is saved, and at the cap the run stops without calling again."""
    system = skeleton(job.system("EF"))
    evidence = ai.evidence_for(system, dossier)
    client = FakeClient(*(_Response(json.dumps({"invented": 1})) for _ in range(4)))

    def run():
        return ai.write_system(system, evidence, playbook,
                               ai.ApiTransport(tmp_path, model="claude-test", client=client))

    with pytest.raises(ai.NoAnswer) as first:
        run()
    assert len(client.calls) == 2 and "Stopped" not in first.value.reason
    retry_prompt = client.calls[1]["messages"][0]["content"][0]["text"]
    assert "could not be used" in retry_prompt and "could not be read" in retry_prompt
    with pytest.raises(ai.NoAnswer) as third:
        run()
    assert len(client.calls) == 3 and "Stopped:" in third.value.reason and not third.value.waiting
    with pytest.raises(ai.NoAnswer) as after:
        run()
    assert len(client.calls) == 3 and "Stopped:" in after.value.reason and not after.value.waiting


def test_a_chat_rerun_without_a_new_answer_keeps_the_refusal_reason(job, raw, dossier, playbook, tmp_path):
    """AI-9: the reason a chat answer was refused stays in the request on a re-run with nothing new, and after
    a stop."""
    system = skeleton(job.system("EF"))
    evidence = ai.evidence_for(system, dossier)
    cache = tmp_path / "cache"
    with pytest.raises(ai.NoAnswer):
        ai.write_system(system, evidence, playbook, ai.ChatTransport(cache, job="00-0000"))
    (request_file,) = (cache / "judge-chat" / "requests").glob("*.json")
    answer = Path(json.loads(request_file.read_text(encoding="utf-8"))["answer_file"])
    answer.parent.mkdir(parents=True, exist_ok=True)
    answer.write_text(json.dumps(_bad(raw, lambda a: a["devices"][0].update(slot="gadget"))), encoding="utf-8")
    _stamp(answer, 10)
    with pytest.raises(ai.NoAnswer):
        ai.write_system(system, evidence, playbook, ai.ChatTransport(cache, job="00-0000"))
    assert "gadget" in json.loads(request_file.read_text(encoding="utf-8"))["previous_problem"]

    with pytest.raises(ai.NoAnswer) as waiting:
        ai.write_system(system, evidence, playbook, ai.ChatTransport(cache, job="00-0000"))
    assert waiting.value.waiting
    assert "gadget" in json.loads(request_file.read_text(encoding="utf-8"))["previous_problem"]

    for seconds in (20, 30):
        _stamp(answer, seconds)
        with pytest.raises(ai.NoAnswer) as stopped:
            ai.write_system(system, evidence, playbook, ai.ChatTransport(cache, job="00-0000"))
    assert "Stopped" in stopped.value.reason and not request_file.exists()
    with pytest.raises(ai.NoAnswer) as again:
        ai.write_system(system, evidence, playbook, ai.ChatTransport(cache, job="00-0000"))
    assert again.value.waiting
    assert "gadget" in json.loads(request_file.read_text(encoding="utf-8"))["previous_problem"]


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


# ---- duct heaters in one place --------------------------------------------------------------------------------------

def _tie():
    from bms.model import Served
    return Served(key="RTU", name="Rooftop Unit", tags=("RTU-1",), heaters=("DH-1",), heater_key="DH",
                  heater_name="Duct Heaters")


def _heated(job, key):
    return dataclasses.replace(job.system(key), serves=(_tie(),))


def test_the_writer_of_a_served_unit_writes_no_duct_heater_line(job, raw, dossier, playbook):
    system = skeleton(_heated(job, "RTU"))
    transport = FakeTransport(copy.deepcopy(raw["systems"][0]))
    written = ai.write_system(system, ai.evidence_for(system, dossier), playbook, transport)
    prompt = transport.asked[0]["prompt"]
    assert ("the duct heaters serving this unit (DH-1) are written in the Duct Heaters block; write no duct heater "
            "line here") in prompt
    assert '"serves"' not in prompt and written.serves == (_tie(),)


def test_a_served_units_duct_heater_line_is_refused(job, raw, dossier, playbook):
    system = skeleton(_heated(job, "RTU"))
    answer = copy.deepcopy(raw["systems"][0])
    answer["devices"][0]["name"] = "DH-1 Enable"
    with pytest.raises(ai.NoAnswer) as refused:
        ai.write_system(system, ai.evidence_for(system, dossier), playbook, FakeTransport(answer))
    assert "duct heater line" in refused.value.reason and "Duct Heaters block" in refused.value.reason


def test_the_writer_of_the_heater_block_writes_all_its_heaters_for_the_units_it_serves(job, raw, dossier, playbook):
    system = skeleton(_heated(job, "DH"))
    transport = FakeTransport(copy.deepcopy(raw["systems"][3]))
    written = ai.write_system(system, ai.evidence_for(system, dossier), playbook, transport)
    prompt = transport.asked[0]["prompt"]
    assert "this is the duct heater block" in prompt and "ALL its heaters (DH-1, DH-2; 2 in all)" in prompt
    assert "- Rooftop Unit (block RTU; tags RTU-1): DH-1" in prompt
    assert "a sentence of the sequence of operation gives the BMS the control" in prompt
    assert "discharge air temperature sensor, enable or SCR signal, status and alarm" in prompt
    assert "only the interlock of the heater to the served unit" in prompt and "the heater count" in prompt
    assert len(written.devices) == 2


def test_an_empty_heater_block_is_refused(job, raw, dossier, playbook):
    system = skeleton(_heated(job, "DH"))
    answer = copy.deepcopy(raw["systems"][3])
    answer.update(devices=[], tech_hours=None, no_scope_reason="The heaters are packaged.")
    with pytest.raises(ai.NoAnswer) as refused:
        ai.write_system(system, ai.evidence_for(system, dossier), playbook, FakeTransport(answer))
    assert "duct heater block and it has no lines" in refused.value.reason


def test_a_revise_is_told_where_the_heaters_are_written(job, raw, dossier, playbook):
    system = _heated(job, "RTU")
    finding = Finding("Packaged units", "RTU", None, "must_fix", "w", "f")
    transport = FakeTransport(copy.deepcopy(raw["systems"][0]))
    ai.revise_system(system, [finding], ai.evidence_for(system, dossier), playbook, transport)
    assert "are written in the Duct Heaters block" in transport.asked[0]["prompt"]


def test_qc_is_told_the_heaters_are_in_their_own_block(job, dossier, playbook):
    heated = job.with_system(_heated(job, "RTU")).with_system(_heated(job, "DH"))
    transport = FakeTransport({"findings": []})
    ai.qc_job(heated, ai.evidence_index(dossier), playbook, transport)
    prompt = transport.asked[0]["prompt"]
    assert "- the Duct Heaters block (DH) writes every duct heater, those of: Rooftop Unit (RTU)" in prompt
    plain = FakeTransport({"findings": []})
    ai.qc_job(job, ai.evidence_index(dossier), playbook, plain)
    assert "Duct heaters, written in one place" not in plain.asked[0]["prompt"]
    assert '"serves"' not in plain.asked[0]["prompt"]


def test_the_prompts_keep_duct_heaters_in_one_place():
    folder = ROOT / "src" / "bms" / "prompts"
    qc = (folder / "qc_job.md").read_text(encoding="utf-8")
    assert "heater lines belong to the duct heater block only" in qc
    assert "A finding that asks to move heater lines out of the duct heater block into a served unit's block is wrong" \
        in qc
    assert ("A duct heater block with no lines while a served unit's block carries heater lines is a \"must_fix\" "
            "finding against the served block") in qc
    write = (folder / "write_system.md").read_text(encoding="utf-8")
    assert "## Duct heaters in one place" in write and "with the heater count as the quantity" in write
    assert "duct heater block" in (folder / "revise_system.md").read_text(encoding="utf-8")


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


def test_the_writer_prompts_keep_texts_short_plain_and_free_of_source_ids_and_labels():
    folder = ROOT / "src" / "bms" / "prompts"
    for name in ("write_system.md", "revise_system.md"):
        text = (folder / name).read_text(encoding="utf-8")
        assert "25 words" in text and "40 words" in text, name
        assert "source id" in text and "in words" in text, name
        assert "label" in text and "renderer adds" in text.replace("renderer prints", "renderer adds"), name
        assert "no_scope_reason" in text, name


def test_client_text_never_names_a_playbook_rule_a_finding_or_a_source_id():
    folder = ROOT / "src" / "bms" / "prompts"
    for name in ("write_system.md", "revise_system.md", "qc_job.md"):
        text = (folder / name).read_text(encoding="utf-8")
        assert "never names a Playbook rule, a rule heading, a finding id or a source id" in text, name
        assert "the mechanical schedule" in text or name == "revise_system.md", name
    assert "the Playbook rule that led to it" not in (folder / "write_system.md").read_text(encoding="utf-8")


def test_an_assumption_naming_a_playbook_rule_is_refused(job, raw, dossier, playbook):
    system = skeleton(job.system("EF"))
    rule = next(iter(playbook.rules))
    answer = _bad(raw, lambda a: a["devices"][0].update(
        assumption={"what": "one per fan", "why": f"Playbook rule {rule}"}))
    with pytest.raises(ai.NoAnswer) as refused:
        ai.write_system(system, ai.evidence_for(system, dossier), playbook, FakeTransport(answer))
    assert "names the Playbook" in refused.value.reason


def test_the_qc_prompt_never_asks_for_integration_lines_on_factory_controlled_units():
    text = (ROOT / "src" / "bms" / "prompts" / "qc_job.md").read_text(encoding="utf-8")
    assert "factory controls" in text and "ECM fan is not a VFD" in text and "integration lines" in text
    assert "no_scope_reason" in text


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
    request.write_text(json.dumps({"key": "k", "kind": "count_tags", "step": "count", "schema": SCHEMA,
                                   "tiles": [[0, 0, 10, 10], [5, 0, 10, 10]]}), encoding="utf-8")
    good, bad, skipped = tmp_path / "good.json", tmp_path / "bad.json", tmp_path / "skipped.json"
    good.write_text(json.dumps({"patterns": [{"pattern": "EF-[0-9]+", "tiles_examined": [1, 2], "tags": [
        {"text": "EF-1", "count": 1, "boxes": [{"tile": 1, "x": 1, "y": 2, "width": 3, "height": 4}]}]}]}),
                    encoding="utf-8")
    bad.write_text(json.dumps({"patterns": [{"pattern": "EF-[0-9]+", "tiles_examined": [1, 2],
                                             "tags": [{"text": "EF-1"}]}]}), encoding="utf-8")
    skipped.write_text(json.dumps({"patterns": [{"pattern": "EF-[0-9]+", "tiles_examined": [1], "tags": []}]}),
                       encoding="utf-8")
    assert run_job.check_answer(good, request) is None
    assert "schema" in run_job.check_answer(bad, request)
    assert "tile 2" in run_job.check_answer(skipped, request)
    settings = json.loads((ROOT / ".claude" / "run-job.json").read_text(encoding="utf-8"))
    assert {"judge_model", "writer_model", "qc_model", "count_model", "max_attempts"} <= set(settings)
    skill = (ROOT / ".claude" / "skills" / "run-job" / "SKILL.md").read_text(encoding="utf-8")
    assert "count_tags" in skill and "count_model" in skill and "--app estimator" in skill


def test_answer_of_populates_late_fields_before_schema_check():
    from bms.ai import _answer_of, _question
    from bms.model import json_schema, System
    schema = json_schema(System)
    raw = {"key": "EF", "name": "Fans", "shape": "", "control": "none", "families": [], "sequence_refs": [],
           "devices": [], "clarifications": [], "tech_hours": None, "alternate": "base"}
    # Notice: 'serves' and 'no_scope_reason' are omitted from raw
    assert "serves" not in raw and "no_scope_reason" not in raw

    class FakeBlock:
        type = "text"
        text = json.dumps(raw)

    class FakeResponse:
        content = [FakeBlock()]
        stop_reason = "end_turn"

    q = _question("model", "write_system", "EF", "rules", "step", "prompt", schema, {}, ())
    answer = _answer_of(FakeResponse(), q)
    assert answer["serves"] == []
    assert answer["no_scope_reason"] is None


def test_a_chat_answer_file_fills_only_a_missing_late_field(tmp_path):
    """The chat file path fills serves and no_scope_reason only when the answer omits them. A present null is not
    replaced, and the schema rejects it."""
    from bms.ai import _read_answer

    schema = json_schema(System)
    raw = {"key": "EF", "name": "Fans", "shape": "", "control": "none", "families": [], "sequence_refs": [],
           "devices": [], "clarifications": [], "tech_hours": None, "alternate": "base"}
    path = tmp_path / "answer.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    answer, errors = _read_answer(path, schema)
    assert errors == []
    assert answer["serves"] == [] and answer["no_scope_reason"] is None

    path.write_text(json.dumps({**raw, "serves": None}), encoding="utf-8")
    rejected, problems = _read_answer(path, schema)
    assert rejected is None and any("serves" in problem for problem in problems)



# ---- AI-3 and AI-4: every quantity id and every quote is checked against the evidence ----------------------------

def _invented_quantity(answer):
    answer["devices"][2]["quantity"] = {"value": 7, "sources": [{"source_id": "F999", "quote": "x", "where": "y"}],
                                        "others": [{"value": 9, "ref": {"source_id": "I999", "quote": "x",
                                                                        "where": "y"}}]}


def test_a_quantity_citing_ids_the_evidence_lacks_is_refused(job, raw, dossier, playbook):
    reason = _refused(skeleton(job.system("EF")), dossier, playbook, _bad(raw, _invented_quantity))
    assert "F999" in reason and "I999" in reason


def test_a_quantity_keeps_the_plan_count_checks_own_records(job, raw, dossier, playbook):
    from bms.counts import NO_SOURCE_QUOTE
    def change(a):
        a["devices"][2]["quantity"]["others"] = [{"value": 9, "ref": {"source_id": "", "quote": NO_SOURCE_QUOTE,
                                                                      "where": ""}}]
    assert len(_written(job, raw, dossier, playbook, change).devices) == 3


def test_an_invented_quantity_id_from_the_earlier_answer_is_not_citable_in_a_revise(job, raw, dossier, playbook):
    raw["systems"][1]["devices"][2]["quantity"]["sources"].append({"source_id": "F999", "quote": "x", "where": "y"})
    system = Job.from_dict(raw).system("EF")
    answer = copy.deepcopy(raw["systems"][1])
    answer["devices"][2]["quantity"]["sources"].pop()
    answer["devices"][2]["refs"] = [{"source_id": "F999", "quote": "x", "where": "y"}]
    finding = Finding("Dampers under their fan", "EF", "EF.d3", "must_fix", "w", "f")
    with pytest.raises(ai.NoAnswer) as refused:
        ai.revise_system(system, [finding], ai.evidence_for(system, dossier), playbook, FakeTransport(answer))
    assert "F999" in refused.value.reason


def test_qc_finds_a_quantity_citing_an_id_no_source_or_planner_gave(job, raw, dossier, playbook):
    raw["systems"][1]["devices"][2]["quantity"]["others"] = [
        {"value": 9, "ref": {"source_id": "I999", "quote": "x", "where": "y"}}]
    raw["systems"][1]["devices"][0]["quantity"]["sources"].append({"source_id": "F999", "quote": "x", "where": "y"})
    findings = ai.qc_job(Job.from_dict(raw), ai.evidence_index(dossier), playbook, FakeTransport({"findings": []}))
    assert [(f.system_key, f.device_id, f.severity) for f in findings] == [("EF", "EF.d1", "must_fix"),
                                                                           ("EF", "EF.d3", "must_fix")]
    assert "F999" in findings[0].what and "I999" in findings[1].what


def test_qc_passes_a_ledger_fact_the_planner_gave_and_a_picture_of_the_job(job, raw, dossier, playbook):
    fact = {"source_id": "F17", "quote": "duct heaters by the electrical contractor", "where": "ledger fact"}
    raw["systems"][1]["sequence_refs"].append(fact)
    raw["systems"][1]["devices"][0]["refs"].append(fact)
    raw["systems"][1]["devices"][1]["refs"].append({"source_id": "I1", "quote": "the sheet", "where": "M-102"})
    findings = ai.qc_job(Job.from_dict(raw), ai.evidence_index(dossier), playbook, FakeTransport({"findings": []}))
    assert findings == []


def _misquoted(answer):
    answer["devices"][2]["refs"] = [{"source_id": "S7", "quote": "MD-1 shall be a smoke damper",
                                     "where": "M-101, Drawings.pdf page 2"}]


def test_a_write_answer_quoting_words_its_source_lacks_is_refused(job, raw, dossier, playbook):
    reason = _refused(skeleton(job.system("EF")), dossier, playbook, _bad(raw, _misquoted))
    assert "S7" in reason and "MD-1 shall be a smoke damper" in reason


def test_a_revise_answer_quoting_words_its_source_lacks_is_refused(job, raw, dossier, playbook):
    system = job.system("EF")
    finding = Finding("Dampers under their fan", "EF", "EF.d3", "must_fix", "w", "f")
    with pytest.raises(ai.NoAnswer) as refused:
        ai.revise_system(system, [finding], ai.evidence_for(system, dossier), playbook,
                         FakeTransport(_bad(raw, _misquoted)))
    assert "S7" in refused.value.reason and "MD-1 shall be a smoke damper" in refused.value.reason


def test_a_quote_of_a_sequence_section_is_checked_against_its_paragraphs(job, raw, dossier, playbook):
    def change(a):
        a["devices"][0]["refs"] = [{"source_id": "Q2", "quote": "when EF-1 runs, MD-1 shall open",
                                    "where": "23 09 93, Specs.pdf page 10"}]
    assert len(_written(job, raw, dossier, playbook, change).devices) == 3


def test_a_sequence_section_holds_only_its_own_paragraphs_at_intake(job, raw, dossier, playbook):
    system = skeleton(job.system("CUH"))
    answer = copy.deepcopy(next(s for s in raw["systems"] if s["key"] == "CUH"))
    answer["devices"][0]["refs"] = [{"source_id": "Q4", "quote": "A 1500", "where": "23 09 93, Specs.pdf page 12"}]
    reason = _refused(system, dossier, playbook, answer)
    assert "Q4" in reason and "A 1500" in reason


# ---- rewrite_for_count: the changed count reaches the lines already written (AI-1) ------------------------------------

def _ef_counted_at(job, value: int) -> System:
    """The written Exhaust Fans with the estimator's family count changed to `value` (same source, S6)."""
    system = job.system("EF")
    family = system.families[0]
    return dataclasses.replace(system, families=(dataclasses.replace(
        family, count=dataclasses.replace(family.count, value=value)),))


def test_a_count_rewrite_takes_the_new_count_onto_the_lines_already_written(job, raw, dossier, playbook):
    """EF 3 -> 5: the writer answers EF.d1 and EF.d2 at 5. Each kept line keeps its words and id but carries the
    new count; before AI-1 every kept id was put back as it was, still at 3, while the family said 5."""
    system = _ef_counted_at(job, 5)
    answer = copy.deepcopy(raw["systems"][1])
    for device in answer["devices"][:2]:
        device["quantity"]["value"] = 5
    answer["devices"][0]["name"] = "Changed without being asked"                 # words stay the kept line's
    transport = FakeTransport(answer)
    rewritten = ai.rewrite_for_count(system, ai.evidence_for(system, dossier), playbook, transport)
    (asked,) = transport.asked
    assert asked["extra"]["step"] == "decide"
    assert "Each line that carries a changed family's count carries the new count." in asked["prompt"]
    assert [(d.id, d.quantity.value) for d in rewritten.devices] == [("EF.d1", 5), ("EF.d2", 5), ("EF.d3", 2)]
    assert rewritten.devices[0].name == system.devices[0].name
    assert rewritten.devices[0].quantity.sources == system.devices[0].quantity.sources
    assert rewritten.devices[0].refs == system.devices[0].refs


def test_a_count_rewrite_takes_only_the_answers_number_never_its_sources_or_its_flag(job, raw, dossier, playbook):
    """A kept line skips the intake's checks, so only the count comes from the answer: its quantity sources stay
    the kept line's, and the answer neither clears nor raises a flag (the flags are the estimator's and
    `counts.flag_written_devices`')."""
    system = _ef_counted_at(job, 5)
    system = dataclasses.replace(system, devices=(dataclasses.replace(system.devices[0], flag="quantity"),
                                                  *system.devices[1:]))
    answer = copy.deepcopy(raw["systems"][1])
    answer["devices"][0]["quantity"] = {"value": 5, "sources": [{"source_id": "S999", "quote": "x", "where": "y"}],
                                        "others": []}
    answer["devices"][0]["flag"] = "none"
    answer["devices"][1]["flag"] = "quantity"
    answer["devices"][1]["quantity"]["value"] = 2          # a line citing no source takes only a family's count
    answer["devices"][2]["quantity"]["value"] = 1          # a line counted from its own sources keeps its count
    rewritten = ai.rewrite_for_count(system, ai.evidence_for(system, dossier), playbook, FakeTransport(answer))
    first = rewritten.devices[0]
    assert first.quantity.value == 5 and first.quantity.sources == system.devices[0].quantity.sources
    assert [d.flag for d in rewritten.devices] == ["quantity", "none", "none"]
    assert [d.quantity.value for d in rewritten.devices] == [5, 3, 2]


def test_a_revise_still_puts_an_untouched_line_back_exactly(job, raw, dossier, playbook):
    system = job.system("EF")
    answer = copy.deepcopy(raw["systems"][1])
    answer["devices"][0]["quantity"]["value"] = 7                                  # not asked: put back
    finding = Finding("Dampers under their fan", "EF", "EF.d3", "must_fix", "w", "f")
    revised = ai.revise_system(system, [finding], ai.evidence_for(system, dossier), playbook, FakeTransport(answer))
    assert revised.devices[0] == system.devices[0]


# ---- the prompts agree with the Playbook (ruling D5): integration, default party, relays ----------------------------

def _prompt(name: str) -> str:
    return (ROOT / "src" / "bms" / "prompts" / name).read_text(encoding="utf-8")


def test_the_qc_prompt_follows_the_playbooks_integration_rules():
    qc = _prompt("qc_job.md")
    assert "Ask for an integration line only when a cited source calls for the BMS to integrate that unit" not in qc
    assert ("Never ask for VFD or speed lines a factory-controlled unit does not have. The integration lines follow "
            'the Playbook\'s "Integration trio", "Integration lines cover monitoring" and "Integration lines last".') in qc


def test_the_writer_prompt_takes_the_playbook_default_and_flags_only_unclear_ownership():
    write = _prompt("write_system.md")
    assert "When the evidence does not say who furnishes, installs or wires a device, follow the Playbook, set flag" \
        not in write
    assert ('When the evidence names no party, take the default the Playbook gives ("Who owns what by default", "Three '
            'ownership questions"). Set flag "ownership" (with an assumption saying what you took and why) only in '
            'the cases the Playbook lists under "Unclear ownership is flagged".') in write


def test_the_writer_prompt_does_not_invite_a_relay_line_the_playbook_absorbs():
    write = _prompt("write_system.md")
    assert ("a relay it switches through) is called for by that sentence; cite it, unless the Playbook says another "
            'line already covers it ("Start/stop covers the relay and status switch") or it is inside a packaged '
            'unit ("Nothing inside the unit is a line").') in write
    assert "a relay it switches through) is called for by that sentence; cite it.\n" not in write


def test_the_writer_prompts_ownership_flag_is_the_playbooks_unclear_ownership():
    write = _prompt("write_system.md")
    assert '"ownership" (who furnishes, installs or wires is not in the evidence)' not in write
    assert '"ownership" (unclear ownership as the Playbook lists it:' in write

# ---- ids in a revise and a count rewrite: a renumbered answer loses no line and doubles none (AI-2) ------------------

_NEW_LINE = {"id": "EF.d2", "slot": "interlock", "name": "Exhaust Fan Interlock", "verb": "Furnish",
             "furnished_by": "AME", "installed_by": "AME", "wired_by": "AME",
             "quantity": {"value": None, "sources": [], "others": []},
             "refs": [{"source_id": "Q2", "quote": "exhaust fans shall start and stop on the BMS schedule",
                       "where": "23 09 93, Specs.pdf page 10"}],
             "assumption": None, "flag": "quantity"}


def _renumbered(raw) -> dict:
    """The EF answer with a new line inserted as d2 and the rest renumbered: d1, NEW(d2), old d2 as d3, old d3 as
    d4."""
    answer = copy.deepcopy(raw["systems"][1])
    old = answer["devices"]
    answer["devices"] = [old[0], copy.deepcopy(_NEW_LINE), dict(old[1], id="EF.d3"), dict(old[2], id="EF.d4")]
    return answer


def _pairs(system: System) -> list[tuple[str, str]]:
    return [(d.slot, d.name) for d in system.devices]


def test_a_revise_answer_that_renumbers_after_a_new_line_keeps_the_new_line_and_doubles_none(job, raw, dossier,
                                                                                             playbook):
    system = job.system("EF")
    answer = _renumbered(raw)
    answer["devices"][0]["name"] = "DDC Controller (fixed)"
    finding = Finding("Dampers under their fan", "EF", "EF.d1", "must_fix", "w", "f")
    revised = ai.revise_system(system, [finding], ai.evidence_for(system, dossier), playbook, FakeTransport(answer))
    pairs = _pairs(revised)
    assert ("interlock", "Exhaust Fan Interlock") in pairs                          # the added line is not lost
    assert len(pairs) == len(set(pairs)) == 4                                       # no line twice
    assert len({d.id for d in revised.devices}) == 4
    kept = {d.id: d for d in revised.devices}
    assert kept["EF.d2"] == system.devices[1] and kept["EF.d3"] == system.devices[2]
    assert "keep the ids given; a new line takes the next free number" in \
        (ROOT / "src" / "bms" / "prompts" / "revise_system.md").read_text(encoding="utf-8")


def test_a_count_rewrite_answer_that_renumbers_keeps_the_new_line_and_doubles_none(job, raw, dossier, playbook):
    system = _ef_counted_at(job, 5)
    answer = _renumbered(raw)
    for device in answer["devices"][:3]:
        device["quantity"]["value"] = 5 if device["slot"] != "interlock" else None
    transport = FakeTransport(answer)
    rewritten = ai.rewrite_for_count(system, ai.evidence_for(system, dossier), playbook, transport)
    pairs = _pairs(rewritten)
    assert ("interlock", "Exhaust Fan Interlock") in pairs
    assert len(pairs) == len(set(pairs)) == 4
    assert len({d.id for d in rewritten.devices}) == 4
    counts = {d.id: d.quantity.value for d in rewritten.devices}
    assert counts["EF.d1"] == 5 and counts["EF.d2"] == 5 and counts["EF.d3"] == 2   # AI-1: the new count reaches
    prompt = transport.asked[0]["prompt"]
    assert "keep the ids given; a new line takes the next free number" in prompt
    assert "EF.d2" in prompt                                                        # the kept lines by their ids


# ---- a device-only revise keeps the block's clarification, tech hours and no-scope reason (AI-10) -----------------

def test_a_device_only_revise_keeps_the_clarification_and_the_tech_hours(job, raw, dossier, playbook):
    system = job.system("EF")
    answer = copy.deepcopy(raw["systems"][1])
    answer["clarifications"] = [{"kind": "note", "text": "Fans carried at three"}]
    answer["tech_hours"] = 99.0
    answer["no_scope_reason"] = "nothing to scope"
    finding = Finding("Dampers under their fan", "EF", "EF.d3", "must_fix", "w", "f")
    revised = ai.revise_system(system, [finding], ai.evidence_for(system, dossier), playbook, FakeTransport(answer))
    assert revised.clarifications == system.clarifications
    assert revised.tech_hours == system.tech_hours
    assert revised.no_scope_reason == system.no_scope_reason


# ---- a QC finding about a device the job lacks is about no device in the revise (AI-16) ----------------------------

def test_a_finding_about_a_missing_device_does_not_open_the_whole_block(job, raw, dossier, playbook):
    system = job.system("EF")
    qc = {"findings": [
        Finding("Dampers under their fan", "EF", "EF.d3", "must_fix", "the damper line names no tags", "x").to_dict(),
        Finding("Dampers under their fan", "EF", "EF.d9", "must_fix", "a line the job lacks", "x").to_dict()]}
    findings = ai.qc_job(job, ai.evidence_index(dossier), playbook, FakeTransport(qc))
    assert findings[1].device_id is None                                            # the QC contract stays
    answer = copy.deepcopy(raw["systems"][1])
    answer["devices"][0]["name"] = "Changed without being asked"
    del answer["devices"][1]
    revised = ai.revise_system(system, findings, ai.evidence_for(system, dossier), playbook, FakeTransport(answer))
    assert revised.devices[0] == system.devices[0] and revised.devices[1] == system.devices[1]
