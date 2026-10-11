"""ws5, HP 25: the proposal's opening sentence names this job's existing system (or the plain fill-in when the
documents name none), never the template's sample name. Every job here is invented."""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from docx import Document

from bms.model import Count, Device, FrontEnd, Job, Ref
from bms.playbook import load_playbook
from bms.render import render

FIXTURES = Path(__file__).resolve().parent / "fixtures"
REF = Ref(source_id="S1", quote="q", where="M-1, Drawings.pdf page 1")
SAMPLE_OPENING_NAME = "District Wide"        # the red sample the proposal template carries in its second opening


@pytest.fixture(scope="module")
def playbook():
    return load_playbook(FIXTURES / "sample_playbook")


@pytest.fixture
def job() -> Job:
    return Job.from_dict(json.loads((FIXTURES / "sample_job.json").read_text(encoding="utf-8")))


def _link() -> Device:
    return Device(id="FE.d1", slot="link", name="Link", verb="Furnish and Install", furnished_by="AME",
                  installed_by="AME", wired_by="AME", quantity=Count(value=1), refs=(REF,))


def _opening_and_heading(job: Job, playbook, tmp_path) -> tuple[str, str]:
    from estimator.__main__ import PROPOSAL_TEMPLATE
    from estimator.proposal.write import write_proposal
    out = write_proposal(render(job, playbook).scope, PROPOSAL_TEMPLATE, tmp_path / "p.docx")
    texts = [" ".join(p.text.split()) for p in Document(str(out)).paragraphs if p.text.strip()]
    opening = next(t for t in texts if t.startswith("A.M.E., Inc, is pleased to provide a quotation"))
    heading = next(t for t in texts if t.startswith("Seamlessly Tie in to the Existing"))
    return opening, heading


def test_the_opening_prints_the_jobs_existing_system_not_the_templates_sample(job, playbook, tmp_path):
    front = FrontEnd(mode="extend-existing", existing_system_name="Acme Net", devices=(_link(),))
    opening, heading = _opening_and_heading(replace(job, front_end=front), playbook, tmp_path)
    assert SAMPLE_OPENING_NAME not in opening
    # T-005 ruling 4: a BMS that is not one of AME's three prints red between ***
    assert opening.endswith("an extension of the existing ***Acme Net*** BMS system.")
    assert heading == "Seamlessly Tie in to the Existing ***Acme Net*** BMS"


def test_the_opening_prints_the_plain_placeholder_when_the_documents_name_no_system(job, playbook, tmp_path):
    front = FrontEnd(mode="extend-existing", existing_system_name=None, devices=(_link(),))
    opening, heading = _opening_and_heading(replace(job, front_end=front), playbook, tmp_path)
    assert SAMPLE_OPENING_NAME not in opening and SAMPLE_OPENING_NAME not in heading
    # T-005 ruling 4: the fill-in prints red between ***
    assert opening.endswith("an extension of the existing ***[existing BMS name]*** BMS system.")
    assert heading == "Seamlessly Tie in to the Existing ***[existing BMS name]*** BMS"
