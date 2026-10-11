"""ws5, HP 9: an existing BMS the documents do not name renders with plain words (the fill-in) and the planner asks
for the name. Every job here is invented."""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from estimator.ledger.facts import SETTLED, Ledger
from estimator.writing.dossier import Dossier

from bms.model import Device, FrontEnd, Job, Count, Ref
from bms.plan import plan_job
from bms.playbook import load_playbook
from bms.render import UNNAMED_EXISTING, render

FIXTURES = Path(__file__).resolve().parent / "fixtures"
REF = Ref(source_id="S1", quote="q", where="M-1, Drawings.pdf page 1")


@pytest.fixture(scope="module")
def playbook():
    return load_playbook(FIXTURES / "sample_playbook")


@pytest.fixture
def job() -> Job:
    return Job.from_dict(json.loads((FIXTURES / "sample_job.json").read_text(encoding="utf-8")))


def _link() -> Device:
    return Device(id="FE.d1", slot="link", name="Link", verb="Furnish and Install", furnished_by="AME",
                  installed_by="AME", wired_by="AME", quantity=Count(value=1), refs=(REF,))


# ---- HP 9: the render does not crash on an existing BMS with no name ------------------------------------------------

@pytest.mark.parametrize("name", [None, "", "   "])
def test_an_existing_bms_with_no_name_renders_with_the_plain_placeholder(job, playbook, name):
    front = FrontEnd(mode="extend-existing", existing_system_name=name, devices=(_link(),))
    draft = render(replace(job, front_end=front), playbook)
    assert draft.scope.front_end.mode == "extend-existing"
    assert draft.scope.front_end.existing_system_name == UNNAMED_EXISTING == "[existing BMS name]"
    assert [i.text for i in draft.scope.front_end.items][-1] == "Furnish and Install Link"     # (T-005e: after the
    # Master Template's existing-BMS lines)


def test_a_named_existing_bms_prints_its_own_name(job, playbook):
    front = FrontEnd(mode="extend-existing", existing_system_name="  Acme  Net ", devices=(_link(),))
    assert render(replace(job, front_end=front), playbook).scope.front_end.existing_system_name == "Acme Net"


def test_a_new_system_prints_no_existing_name_even_when_the_model_holds_one(job, playbook):
    front = FrontEnd(mode="new-system", existing_system_name="Acme Net", devices=(_link(),))
    assert render(replace(job, front_end=front), playbook).scope.front_end.existing_system_name is None


def test_the_placeholder_is_the_one_the_front_end_data_file_holds():
    from estimator.writing.front_end import FRONT_END_FILE, _load
    assert UNNAMED_EXISTING == _load(FRONT_END_FILE)["existing_systems"]["unnamed"]


# ---- HP 9: the planner asks for the name ----------------------------------------------------------------------------

def _plan(ledger: Ledger) -> Job:
    dossier = Dossier(job_name="Invented Job", text="", images=(), sources={}, families=(), device_totals={},
                      counts={}, stats={})
    return plan_job(ledger, None, dossier, load_playbook(FIXTURES / "sample_playbook"))


SOURCES = {"S4": "23 09 00, Specs.pdf page 4"}


def test_the_planner_asks_for_the_name_of_an_existing_bms_the_documents_do_not_name():
    ledger = Ledger(SOURCES)
    ledger.add("front_end", "mode", "extend-existing", "S4", "extend the existing BMS", "spec", SETTLED)
    job = _plan(ledger)
    assert job.front_end.mode == "extend-existing" and job.front_end.existing_system_name is None
    asked = [q for q in job.questions if UNNAMED_EXISTING in q]      # it says what the proposal prints meanwhile
    assert len(asked) == 1 and "name" in asked[0] and "existing" in asked[0]


def test_the_planner_does_not_ask_when_the_documents_name_it():
    ledger = Ledger(SOURCES)
    ledger.add("front_end", "mode", "extend-existing", "S4", "extend the existing Acme Net BMS", "spec", SETTLED)
    ledger.add("front_end", "existing_name", "Acme Net", "S4", "existing Acme Net", "spec", SETTLED)
    job = _plan(ledger)
    assert job.front_end.existing_system_name == "Acme Net"
    assert not [q for q in job.questions if UNNAMED_EXISTING in q]


def test_a_blank_name_in_the_ledger_is_no_name():
    ledger = Ledger(SOURCES)
    ledger.add("front_end", "mode", "extend-existing", "S4", "extend the existing BMS", "spec", SETTLED)
    ledger.add("front_end", "existing_name", "   ", "S4", "existing", "spec", SETTLED)
    job = _plan(ledger)
    assert job.front_end.existing_system_name is None
    assert [q for q in job.questions if UNNAMED_EXISTING in q]
