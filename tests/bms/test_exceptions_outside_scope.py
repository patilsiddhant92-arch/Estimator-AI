"""ws5, HP 24: when the job's documents put equipment or work outside AME's scope (by others, existing to remain, not in
contract), the planner makes a named exception that cites them, and the renderer prints it as an EXCEPTION line in the
job's own words. No line of fixed text: the form is the Playbook's; a Playbook that gives none gets a question for the
estimator, and no EXCEPTION line is written from code. Every job here is invented."""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from estimator.ledger.facts import SETTLED, Ledger
from estimator.writing.dossier import Dossier

from bms import plan
from bms.model import Header, Job, Ref, ScopeException, System
from bms.plan import plan_job
from bms.plan_read import squash
from bms.playbook import Rule, load_playbook
from bms.render import left_out_text, render

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SAMPLE = load_playbook(FIXTURES / "sample_playbook")
SOURCES = {"S3": "M-501, Drawings.pdf page 6 (schedule)", "S4": "23 09 00, Specs.pdf page 4",
           "S5": "M-101, Drawings.pdf page 2 (sheet text)"}
FRAME = "EXCEPTION TO ANY WORK WITH"
# An invented Playbook that words the form of a named exception: the sample Playbook gives none, the repo's does.
FORM_RULE = Rule("Exceptions and alternates", "Named exceptions",
                 "A unit the documents leave with no BMS work is a named exception in the estimator's form: "
                 '"EXCEPTION TO ANY WORK WITH Qty (n) <tags> - <reason>".')
FORMED = dataclasses.replace(SAMPLE, rules={**SAMPLE.rules, FORM_RULE.name: FORM_RULE})


def _ledger() -> Ledger:
    ledger = Ledger(dict(SOURCES))
    ledger.add("front_end", "mode", "new-system", "S4", "provide a new system", "spec", SETTLED)
    ledger.add("front_end", "line", "Furnish an operator workstation", "S4", "provide a workstation", "spec", SETTLED)
    return ledger


def _family(ledger: Ledger, prefix: str, name: str, tags: str, count: int) -> None:
    ledger.add("family", prefix, name, "S3", f"{prefix} {name}", "schedules", SETTLED)
    ledger.add("unit", prefix, tags, "S3", f"Tags: {tags}", "schedules", SETTLED)
    ledger.add("count", prefix, count, "S3", f"{prefix} rows {count}", "schedules", SETTLED)


def _plan(ledger: Ledger, playbook=FORMED) -> Job:
    dossier = Dossier(job_name="Invented Job", text="", images=(), sources={}, families=(), device_totals={},
                      counts={}, stats={})
    return plan_job(ledger, None, dossier, playbook)


def _provider(ledger: Ledger, subject: str, value: str, quote: str, source: str = "S4") -> None:
    ledger.add("provider", subject, value, source, quote, "spec", SETTLED)


# ---- the plan --------------------------------------------------------------------------------------------------------

def test_a_block_the_documents_leave_out_of_the_contract_gets_an_exception_that_cites_them():
    ledger = _ledger()
    _family(ledger, "FP", "Fire Pump", "FP-1", 1)
    _provider(ledger, "FP", "not in contract", "N.I.C.")
    (exception,) = _plan(ledger).exceptions
    assert exception.system_key == "FP"
    assert exception.text == f"{FRAME} Qty (1) FP-1 - not in contract"
    assert exception.refs == (Ref("S4", "N.I.C.", "23 09 00, Specs.pdf page 4"),)


def test_controls_by_others_names_the_equipment_as_the_header_does_and_the_documents_reason():
    ledger = _ledger()
    _family(ledger, "EF", "Exhaust Fan", "EF-1, EF-2", 2)
    _provider(ledger, "EF", "controls by others (see sheet E-501)", "exhaust fan controls by others", "S5")
    (exception,) = _plan(ledger).exceptions
    assert exception.text == f"{FRAME} Qty (2) EF-1, 2 - controls by others (see sheet E-501)"
    assert exception.refs == (Ref("S5", "exhaust fan controls by others", "M-101, Drawings.pdf page 2"),)


def test_existing_equipment_that_stays_as_it_is_gets_an_exception():
    ledger = _ledger()
    _family(ledger, "UH", "Unit Heater", "UH-1", 1)
    _provider(ledger, "UH", "existing unit heater to remain", "existing UH-1 to remain")
    (exception,) = _plan(ledger).exceptions
    assert exception.system_key == "UH" and exception.text.endswith("Qty (1) UH-1 - existing unit heater to remain")


def test_the_reason_is_the_documents_never_a_fixed_text():
    """Two blocks, two reasons: each line carries its own fact's words and no other."""
    ledger = _ledger()
    _family(ledger, "FP", "Fire Pump", "FP-1", 1)
    _family(ledger, "UH", "Unit Heater", "UH-1", 1)
    _provider(ledger, "FP", "N.I.C.", "fire pump N.I.C.")
    _provider(ledger, "UH", "BMS work by others, per the sprinkler drawings", "heater BMS work by others")
    texts = [x.text for x in _plan(ledger).exceptions]
    assert texts == [f"{FRAME} Qty (1) FP-1 - N.I.C.",
                     f"{FRAME} Qty (1) UH-1 - BMS work by others, per the sprinkler drawings"]
    source = Path(plan.__file__).read_text(encoding="utf-8")
    assert "BY MECHANICAL CONTRACTOR" not in source and "NOT CONTROLS CONTRACTOR" not in source


@pytest.mark.parametrize("subject, value", [
    ("RTU", "factory controls by the unit manufacturer"),         # packaged: the BMS integrates it
    ("EF", "furnished by others"),                                  # who furnishes the equipment: the BMS still controls it
    ("EF", "controls not by others"),
    ("BLR", "BMS to integrate over BACnet"),
    ("BMS server", "not in contract"),                              # a front-end item: the front end's note carries it
    ("Network switches", "by others"),
    ("GEN-9", "not in contract"),                                   # equipment no block of the plan holds
])
def test_a_provider_fact_that_leaves_the_bms_work_with_ame_makes_no_exception(subject, value):
    ledger = _ledger()
    _family(ledger, "RTU", "Rooftop Unit", "RTU-1", 1)
    _family(ledger, "EF", "Exhaust Fan", "EF-1, EF-2", 2)
    _family(ledger, "BLR", "Boiler", "BLR-1", 1)
    _provider(ledger, subject, value, "the sentence")
    assert _plan(ledger).exceptions == ()


def test_the_readings_own_exception_line_stands_and_none_is_made_for_the_same_block():
    ledger = _ledger()
    _family(ledger, "CHWP", "Chilled Water Pump", "CHWP-1", 1)
    ledger.add("note", "exception", "Exception to any work with CHWP-1 (by others)", "S4", "CHWP-1 by others", "spec",
               SETTLED)
    _provider(ledger, "CHWP", "controls by others", "CHWP controls by others")
    (exception,) = _plan(ledger).exceptions
    assert exception.text == "Exception to any work with CHWP-1 (by others)"


def test_facts_that_give_one_reason_for_a_block_make_one_exception_citing_each():
    ledger = _ledger()
    _family(ledger, "FP", "Fire Pump", "FP-1", 1)
    _provider(ledger, "FP", "not in contract", "fire pump not in contract")
    _provider(ledger, "FP-1", "Not In Contract", "FP-1 NIC", "S5")
    (exception,) = _plan(ledger).exceptions
    assert [r.source_id for r in exception.refs] == ["S4", "S5"]


def test_the_form_is_the_playbooks_own_when_a_rule_gives_one():
    real = load_playbook()
    assert plan._FORM_IN_RULE.search(squash(real.rules["Named exceptions"].text))      # the repo Playbook words it
    ledger = _ledger()
    _family(ledger, "FP", "Fire Pump", "FP-1", 1)
    _provider(ledger, "FP", "not in contract", "N.I.C.")
    assert _plan(ledger, real).exceptions[0].text == f"{FRAME} Qty (1) FP-1 - not in contract"
    other = Rule("Exceptions and alternates", "Named exceptions",
                 'A named exception reads "EXCEPTION FOR Qty (n) <tags> BECAUSE <reason>" in the estimator\'s form.')
    changed = dataclasses.replace(SAMPLE, rules={**SAMPLE.rules, other.name: other})
    assert _plan(ledger, changed).exceptions[0].text == "EXCEPTION FOR Qty (1) FP-1 BECAUSE not in contract"


def test_an_unknown_count_prints_hashes():
    ledger = _ledger()
    ledger.add("family", "FP", "Fire Pump", "S3", "FP Fire Pump", "schedules", SETTLED)
    _provider(ledger, "FP", "not in contract", "N.I.C.")
    assert _plan(ledger).exceptions[0].text == f"{FRAME} Qty (##) Fire Pump - not in contract"


# ---- a Playbook that gives no form: a question, never a line from code ------------------------------------------------

def _asked(job: Job) -> list[str]:
    """The questions about the form of a named exception."""
    return [q for q in job.questions if "named exception" in q]


def test_a_playbook_without_the_form_gives_a_question_and_no_exception_line():
    assert "Named exceptions" not in SAMPLE.rules                      # the sample Playbook words no form
    ledger = _ledger()
    _family(ledger, "FP", "Fire Pump", "FP-1", 1)
    _provider(ledger, "FP", "not in contract", "N.I.C.")
    job = _plan(ledger, SAMPLE)
    (exception,) = job.exceptions
    assert exception.system_key == "FP" and exception.text == ""                         # no line written from code
    assert exception.refs == (Ref("S4", "N.I.C.", "23 09 00, Specs.pdf page 4"),)         # its citation stays
    (question,) = _asked(job)
    # it names the item, the documents' reason and the citation (where and quote); it holds no EXCEPTION line
    for named in ("Qty (1) FP-1", "not in contract", "23 09 00, Specs.pdf page 4", '"N.I.C."'):
        assert named in question, named
    assert FRAME not in question


def test_each_item_without_a_form_is_asked_about_with_its_own_citation():
    ledger = _ledger()
    _family(ledger, "FP", "Fire Pump", "FP-1", 1)
    _family(ledger, "UH", "Unit Heater", "UH-1", 1)
    _provider(ledger, "FP", "N.I.C.", "fire pump N.I.C.")
    _provider(ledger, "UH", "BMS work by others, per the sprinkler drawings", "heater BMS work by others", "S5")
    job = _plan(ledger, SAMPLE)
    assert [x.text for x in job.exceptions] == ["", ""] and [x.system_key for x in job.exceptions] == ["FP", "UH"]
    fp, uh = _asked(job)
    assert "Qty (1) FP-1" in fp and "fire pump N.I.C." in fp and "23 09 00, Specs.pdf page 4" in fp
    assert "Qty (1) UH-1" in uh and "heater BMS work by others" in uh and "M-101, Drawings.pdf page 2" in uh
    assert "UH-1" not in fp and "FP-1" not in uh


def test_facts_that_give_one_reason_are_one_question_naming_each_citation():
    ledger = _ledger()
    _family(ledger, "FP", "Fire Pump", "FP-1", 1)
    _provider(ledger, "FP", "not in contract", "fire pump not in contract")
    _provider(ledger, "FP-1", "Not In Contract", "FP-1 NIC", "S5")
    job = _plan(ledger, SAMPLE)
    (question,) = _asked(job)
    assert "fire pump not in contract" in question and "FP-1 NIC" in question
    assert [r.source_id for r in job.exceptions[0].refs] == ["S4", "S5"]


def test_no_exception_line_reaches_the_proposal_without_a_form():
    ledger = _ledger()
    _family(ledger, "FP", "Fire Pump", "FP-1", 1)
    _provider(ledger, "FP", "not in contract", "N.I.C.")
    job = dataclasses.replace(_plan(ledger, SAMPLE), header=Header("00-0000", "Invented", "Engineer", ("M-1",),
                                                                     "2026-10-04"))
    draft = render(job, SAMPLE)
    assert draft.scope.named_exceptions == ()
    assert not [line for line in draft.lines if FRAME in line.text]


def test_a_playbook_that_gives_the_form_asks_nothing_about_it():
    ledger = _ledger()
    _family(ledger, "FP", "Fire Pump", "FP-1", 1)
    _provider(ledger, "FP", "not in contract", "N.I.C.")
    assert _asked(_plan(ledger, FORMED)) == []


def test_the_code_holds_no_fixed_exception_wording():
    assert not hasattr(plan, "EXCEPTION_FORM")
    assert FRAME not in Path(plan.__file__).read_text(encoding="utf-8")


# ---- the render ------------------------------------------------------------------------------------------------------

@pytest.fixture
def job() -> Job:
    return Job.from_dict(json.loads((FIXTURES / "sample_job.json").read_text(encoding="utf-8")))


def _left_out(job: Job) -> System:
    return dataclasses.replace(job.system("EF"), key="FP", name="Fire Pumps", devices=(), clarifications=(),
                               no_scope_reason="The controls are not in the contract.", tech_hours=None)


def test_a_left_out_block_with_an_exception_prints_the_exception_line_as_its_note():
    system = System("FP", "Fire Pumps", "", "none", (), no_scope_reason="The controls are not in the contract.")
    line = f"{FRAME} Qty (1) FP-1 - not in contract"
    assert left_out_text(system, (line,)) == line
    assert left_out_text(system, (line, "EXCEPTION TWO")) == f"{line}\nEXCEPTION TWO"
    assert left_out_text(system) == "Fire Pumps: left out, no lines written (The controls are not in the contract)"


def test_the_exception_prints_in_the_proposal_and_notes_the_left_out_block(job):
    line = f"{FRAME} Qty (1) FP-1 - not in contract"
    asked = dataclasses.replace(job, systems=(*job.systems, _left_out(job)), exceptions=(
        *job.exceptions, ScopeException("FP", line, (Ref("S4", "N.I.C.", "23 09 00, Specs.pdf page 4"),))))
    draft = render(asked, SAMPLE)
    assert [l.text for l in draft.lines if l.system_key == "FP"] == [line]
    assert draft.scope.named_exceptions == ("Fire alarm system by others", line)
    plain = render(dataclasses.replace(job, systems=(*job.systems, _left_out(job))), SAMPLE)
    assert [l.text for l in plain.lines if l.system_key == "FP"] == [
        "Fire Pumps: left out, no lines written (The controls are not in the contract)"]
    assert plain.scope.named_exceptions == ("Fire alarm system by others",)


def test_an_exception_about_no_block_prints_among_the_exceptions_only(job):
    line = f"{FRAME} Qty (1) GEN-9 - not in contract"
    asked = dataclasses.replace(job, exceptions=(*job.exceptions, ScopeException("", line)))
    draft = render(asked, SAMPLE)
    assert draft.scope.named_exceptions[-1] == line
    assert not [l for l in draft.lines if l.text == line]


def test_the_exception_the_documents_make_reaches_the_word_proposal(tmp_path):
    """Plan, render and write: a fire pump the documents leave out of the contract prints its EXCEPTION line among
    the proposal's exceptions, with no block of its own."""
    from docx import Document
    from estimator.__main__ import PROPOSAL_TEMPLATE
    from estimator.proposal.write import write_proposal
    from bms.model import Header
    ledger = _ledger()
    _family(ledger, "FP", "Fire Pump", "FP-1", 1)
    _provider(ledger, "FP", "not in contract", "N.I.C.")
    job = dataclasses.replace(_plan(ledger), header=Header("00-0000", "Invented", "Engineer", ("M-1",), "2026-10-04"))
    out = write_proposal(render(job, SAMPLE).scope, PROPOSAL_TEMPLATE, tmp_path / "p.docx")
    lines = [" ".join(p.text.split()) for p in Document(str(out)).paragraphs if p.text.strip()]
    line = f"{FRAME} Qty (1) FP-1 - not in contract"
    assert line in lines and lines.index(line) < next(i for i, t in enumerate(lines) if t.startswith("Base Price:"))
    assert not [t for t in lines if t.startswith("Qty (1) Fire Pump")]


def test_the_exception_line_prints_no_word_the_client_never_sees():
    """The reason keeps the documents' own casing: EXISTING in capitals is a flag word the Playbook keeps off the
    client's page, so the validator reports nothing about the line."""
    from bms.validate import validate
    ledger = _ledger()
    _family(ledger, "UH", "Unit Heater", "UH-1", 1)
    _provider(ledger, "UH", "existing unit heater to remain", "existing UH-1 to remain")
    job = _plan(ledger)
    assert not [f for f in validate(job, SAMPLE) if "named exception" in f.what]
