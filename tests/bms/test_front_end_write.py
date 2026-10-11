"""ws5, HP 22 / 186 / 192d: the front end is planned from the job's evidence, written through the AI writer like a
system, checked and revised like one. Every job here is invented: tests/bms/fixtures."""
from __future__ import annotations

import copy
import dataclasses
from pathlib import Path

import pytest

from estimator.ledger.facts import SETTLED, Ledger
from estimator.writing.dossier import Dossier

from bms import ai
from bms.model import Clarification, Finding, FrontEnd, Job, Ref
from bms.plan import plan_job
from bms.playbook import load_playbook
from test_ai import FakeTransport
from test_ai import dossier, job, playbook, raw  # noqa: F401  (fixtures)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
S1 = {"source_id": "S1", "quote": "provide a new building management system with graphics",
      "where": "23 09 23, Specs.pdf page 2"}


@pytest.fixture
def front(job) -> FrontEnd:
    """What the planner hands the front end's writer: the planner's fields only."""
    return dataclasses.replace(job.front_end, devices=(), clarifications=(), tech_hours=None)


def _device(number=1, name="3-D Graphics", ref=S1, **kw) -> dict:
    return {"id": f"FE.d{number}", "slot": "graphics", "name": name, "verb": "Furnish", "furnished_by": "AME",
            "installed_by": "AME", "wired_by": "AME",
            "quantity": {"value": 1, "sources": [ref], "others": [], "added_up": None}, "refs": [ref],
            "assumption": None, "flag": "none", **kw}


def _answer(devices=None, clarifications=(), reason=None, **kw) -> dict:
    devices = [_device()] if devices is None else devices
    return {"key": "FE", "name": "Front End", "shape": "", "control": "integration", "families": [],
            "sequence_refs": [], "devices": devices, "clarifications": list(clarifications), "tech_hours": None,
            "alternate": "base", "no_scope_reason": reason, **kw}


def _write(front, dossier, playbook, answer, **kw):
    transport = FakeTransport(answer)
    written = ai.write_front_end(front, ai.front_end_evidence(front, dossier), playbook, transport, **kw)
    return written, transport


# ---- the plan -------------------------------------------------------------------------------------------------------

SOURCES = {"S4": "23 09 00, Specs.pdf page 4", "S5": "23 09 23, Specs.pdf page 5", "S6": "27 00 00, Specs.pdf page 6"}


def _plan(ledger: Ledger) -> Job:
    dossier = Dossier(job_name="Invented Job", text="", images=(), sources={}, families=(), device_totals={},
                      counts={}, stats={})
    return plan_job(ledger, None, dossier, load_playbook(FIXTURES / "sample_playbook"))


def _ledger() -> Ledger:
    ledger = Ledger(dict(SOURCES))
    ledger.add("front_end", "mode", "new-system", "S4", "provide a new building automation system", "spec", SETTLED)
    return ledger


NO_FRONT_END = "The documents call for no front-end equipment"


def test_the_plan_carries_what_the_documents_say_about_the_front_end_with_its_citations():
    ledger = _ledger()
    ledger.add("front_end", "line", "Furnish an operator workstation", "S4", "provide one operator workstation",
               "spec", SETTLED)
    ledger.add("front_end", "line", "Furnish a network level control panel", "S5", "a network level panel", "spec",
               SETTLED)
    ledger.add("front_end", "note", "**PC workstation by owner", "S5", "the owner furnishes the workstation", "spec",
               SETTLED)
    front = _plan(ledger).front_end
    assert front.lines == ("Furnish an operator workstation", "Furnish a network level control panel")
    assert front.notes == ("**PC workstation by owner",)
    assert front.refs == (Ref("S4", "provide one operator workstation", "23 09 00, Specs.pdf page 4"),
                          Ref("S5", "a network level panel", "23 09 23, Specs.pdf page 5"),
                          Ref("S5", "the owner furnishes the workstation", "23 09 23, Specs.pdf page 5"))
    assert front.devices == () and front.clarifications == () and front.tech_hours is None
    assert not [q for q in _plan(ledger).questions if NO_FRONT_END in q]


def test_the_plan_carries_the_provider_facts_about_front_end_items_and_no_other():
    ledger = _ledger()
    ledger.add("provider", "BMS server", "provided by the owner", "S6", "the owner provides the BMS server", "network",
               SETTLED)
    ledger.add("provider", "Network switches", "by others", "S6", "network switches by others", "network", SETTLED)
    ledger.add("provider", "VFD", "furnished by the mechanical contractor", "S6", "VFDs by Division 23", "network",
               SETTLED)
    ledger.add("provider", "Float switch", "by the pump manufacturer", "S6", "float switch by the mfr", "network",
               SETTLED)
    front = _plan(ledger).front_end
    assert front.lines == ("BMS server: provided by the owner", "Network switches: by others")
    assert [r.quote for r in front.refs] == ["the owner provides the BMS server", "network switches by others"]


def test_the_plan_asks_a_question_and_writes_no_front_end_when_the_documents_call_for_none():
    front_job = _plan(_ledger())
    front = front_job.front_end
    assert (front.lines, front.notes, front.refs) == ((), (), ())
    assert len([q for q in front_job.questions if NO_FRONT_END in q]) == 1


# ---- the front end as a block ----------------------------------------------------------------------------------------

def test_the_front_end_is_a_block_of_its_own_with_the_planners_refs(front):
    system = ai.front_end_system(front)
    assert (system.key, system.name, system.shape) == ("FE", "Front End", "")
    assert system.sequence_refs == front.refs and system.families == () and system.alternate == "base"


def test_the_front_ends_key_avoids_the_keys_of_the_jobs_systems_and_follows_its_lines(front, job):
    assert ai.front_end_system(front, {"FE"}).key == "FE2"
    assert ai.front_end_system(front, {"FE", "FE2"}).key == "FE3"
    written = dataclasses.replace(front, devices=job.front_end.devices)             # its lines are FE.d1 ...
    assert ai.front_end_system(written, {"FE"}).key == "FE"


def test_the_front_end_evidence_carries_the_passages_the_planner_cited(front, dossier):
    text = ai.front_end_evidence(front, dossier)
    assert "[S1] The contractor shall provide a new building management system with graphics." in text
    assert "[S6]" not in text and "[S18]" not in text                                # other systems' passages
    assert text == ai.front_end_evidence(front, dossier)                             # deterministic


# ---- the writer ------------------------------------------------------------------------------------------------------

def test_the_front_end_is_written_like_a_system(front, dossier, playbook):
    written, transport = _write(front, dossier, playbook, _answer())
    (asked,) = transport.asked
    assert asked["kind"] == ai.WRITE_SYSTEM and asked["name"] == "Front End"
    assert asked["extra"]["step"] == "write" and asked["extra"]["plan_key"] == "FE"
    assert asked["system_prompt"] == ai._instructions("write_front_end")
    prompt = asked["prompt"]
    assert "mode new-system" in prompt and "Furnish the BMS server software and graphics" in prompt
    assert "Furnish Network Level Control Panel" in prompt and "house wording and order only" in prompt
    assert "[S1] The contractor shall provide" in prompt.split("The evidence:", 1)[1]
    assert [d.id for d in written.devices] == ["FE.d1"] and written.devices[0].refs[0].source_id == "S1"
    assert (written.mode, written.existing_system_name, written.lines, written.refs) == (
        front.mode, front.existing_system_name, front.lines, front.refs)          # the planner's fields stay


def test_the_front_end_answer_cannot_change_the_planners_fields(front, dossier, playbook):
    answer = _answer(key="XX", name="Renamed", control="none", sequence_refs=[], alternate="add")
    written, _ = _write(front, dossier, playbook, answer)
    assert (written.mode, written.refs, written.lines, written.notes) == (front.mode, front.refs, front.lines,
                                                                        front.notes)
    assert [d.id for d in written.devices] == ["FE.d1"]


def test_a_front_end_note_goes_in_its_one_clarification(front, dossier, playbook):
    answer = _answer(clarifications=[{"kind": "note", "text": "PC Workstation by Owner"}])
    written, _ = _write(front, dossier, playbook, answer)
    assert written.clarifications == (Clarification("note", "PC Workstation by Owner"),)


def test_a_front_end_with_no_line_says_why(front, dossier, playbook):
    reason = "The documents give the whole front end to the owner."
    written, _ = _write(front, dossier, playbook, _answer(devices=[], reason=reason))
    assert written.devices == () and written.no_scope_reason == reason


@pytest.mark.parametrize("answer, words", [
    (_answer([_device(ref={**S1, "source_id": "S999"})]), "S999"),
    (_answer([_device(ref={**S1, "quote": "provide a workstation for every office"})]), "provide a workstation"),
    (_answer(devices=[], reason=None), "no_scope_reason"),
    (_answer(clarifications=[{"kind": "note", "text": "a"}, {"kind": "note", "text": "b"}]), "clarification"),
    (_answer([_device(name="Graphics per S1")]), "S1"),
    (_answer([_device(slot="")]), "slot"),
])
def test_the_front_end_answer_is_refused_for_what_a_systems_answer_is_refused_for(front, dossier, playbook, answer,
                                                                                    words):
    with pytest.raises(ai.NoAnswer) as refused:
        _write(front, dossier, playbook, answer)
    assert words in refused.value.reason and "Front End" in refused.value.reason


def test_nothing_is_asked_when_the_documents_call_for_no_front_end(front, dossier, playbook):
    empty = dataclasses.replace(front, lines=(), notes=(), refs=())
    written, transport = _write(empty, dossier, playbook, _answer())
    assert written is empty and transport.asked == []


def test_a_front_end_already_written_is_not_asked_again(job, dossier, playbook):
    written, transport = _write(job.front_end, dossier, playbook, _answer())
    assert written is job.front_end and transport.asked == []


# ---- which findings are about the front end ---------------------------------------------------------------------------

def test_a_finding_about_a_front_end_line_is_about_the_front_end(job):
    front = job.front_end
    assert ai.is_front_end_finding(Finding("Every line cites this job", "", "FE.d1", "must_fix", "w", "f"), front)
    assert not ai.is_front_end_finding(Finding("Every line cites this job", "", "EF.d1", "must_fix", "w", "f"), front)
    assert not ai.is_front_end_finding(Finding("Every line cites this job", "EF", "FE.d1", "must_fix", "w", "f"), front)
    assert not ai.is_front_end_finding(Finding("r", "", "FE.d1", "must_fix", "w", "f"), None)


def test_a_finding_about_no_line_is_about_the_front_end_unless_it_is_about_an_exception(job, playbook):
    front = job.front_end
    block = Finding("One clarification per block", "", None, "must_fix", "The block has 2 clarifications (note, "
                    "confirm)", "Keep one.")
    named = Finding("Assumption wording has no source ids", "", None, "must_fix",
                    "an id is in the client text of the named exception (S1)", "Name the document in words.")
    assert ai.is_front_end_finding(block, front, playbook)
    assert not ai.is_front_end_finding(named, front, playbook)
    says = dataclasses.replace(named, what="the front end names the BMS server twice")
    assert ai.is_front_end_finding(says, front, playbook)


def test_a_finding_under_a_rule_of_the_front_end_part_is_about_the_front_end(job):
    real = load_playbook()
    exception_ish = Finding("Front end items by others", "", None, "must_fix", "an exception names the server",
                            "named exception")
    assert real.rules["Front end items by others"].topic.casefold() == ai.FRONT_END_TOPIC
    assert ai.is_front_end_finding(exception_ish, job.front_end, real)


# ---- the revise ------------------------------------------------------------------------------------------------------

def test_the_front_end_is_revised_for_its_findings_only(job, dossier, playbook):
    front = job.front_end
    evidence = ai.front_end_evidence(front, dossier)
    findings = [Finding("Every line cites this job", "", "FE.d1", "must_fix", "the name is vague", "name it as the "
                        "documents do"),
                Finding("Packaged units", "RTU", "RTU.d1", "must_fix", "w", "f"),          # another block's
                Finding("Every line cites this job", "", "FE.d1", "check", "w", "f")]
    answer = _answer([_device(name="BMS Server Software")])
    answer["devices"][0].update(slot="server", verb="Furnish and Install", quantity=front.devices[0].quantity.to_dict())
    transport = FakeTransport(answer)
    revised = ai.revise_front_end(front, findings, evidence, playbook, transport)
    (asked,) = transport.asked
    assert asked["name"] == "Front End (revise)" and asked["extra"] == {"step": "revise", "plan_key": "FE",
                                                                          "images": []}
    assert "the name is vague" in asked["prompt"] and "Packaged units" not in asked["prompt"]
    assert asked["system_prompt"] == ai._instructions("revise_system")
    assert revised.devices[0].name == "BMS Server Software" and revised.devices[0].id == "FE.d1"
    assert (revised.mode, revised.lines, revised.refs, revised.tech_hours) == (front.mode, front.lines, front.refs,
                                                                               front.tech_hours)


def test_the_revise_of_the_front_end_asks_nothing_without_a_front_end_finding(job, dossier, playbook):
    front = job.front_end
    transport = FakeTransport()
    findings = [Finding("Packaged units", "RTU", "RTU.d1", "must_fix", "w", "f"),
                Finding("Every line cites this job", "", "FE.d1", "check", "w", "f")]
    assert ai.revise_front_end(front, findings, "evidence", playbook, transport) is front
    assert transport.asked == []


def test_the_revise_of_an_empty_front_end_the_documents_do_not_call_for_asks_nothing(front, playbook):
    empty = dataclasses.replace(front, lines=(), notes=(), refs=())
    transport = FakeTransport()
    finding = Finding("Every line cites this job", "", None, "must_fix", "w", "f")
    assert ai.revise_front_end(empty, [finding], "evidence", playbook, transport) is empty
    assert transport.asked == []


# ---- the QC pass's mechanical check ----------------------------------------------------------------------------------

def test_a_front_end_line_may_cite_a_ledger_fact_the_planner_cited_for_the_front_end(job, playbook):
    ref = Ref("F9", "the owner provides the server", "27 00 00, Specs.pdf page 6")
    device = dataclasses.replace(job.front_end.devices[0], refs=(ref,))
    cited = dataclasses.replace(job.front_end, devices=(device,), refs=(ref,))
    other = dataclasses.replace(job.front_end, devices=(device,), refs=())
    index = {"S1": "x"}
    about_f9 = lambda found: [f for f in found if "F9" in f.what]                      # noqa: E731
    assert not about_f9(ai.quote_findings(dataclasses.replace(job, front_end=cited), index, playbook))
    assert about_f9(ai.quote_findings(dataclasses.replace(job, front_end=other), index, playbook))
