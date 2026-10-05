"""The three gaps the review of record of cleanup round 4 left in the source-id detector (L-A, L-B, L-C). Invented
fixture only.

- L-A: the known sheets (K) come only from the planner's own wheres (sequence refs, family counts, the front end,
  the exceptions), never from a writer's device refs, so a where the writer types never makes an issued id a sheet.
- L-B: the run computes the whole plan's K once and passes it to every writer, the decision rewrite and the revise,
  so intake, validator and render agree on a sheet another system's where names.
- L-C: a documents tag written with a hyphen or underscore ("S-1", "AHU_S12") protects its plain form ("S1",
  "S12") and nothing else; a device name is never a tag.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import replace
from pathlib import Path

import pytest

from bms import ai, citations
from bms.model import Clarification, Count, Device, Family, Job, Ref, System
from bms.playbook import load_playbook
from bms.render import render
from bms.validate import RULE, validate

FIX = Path(__file__).resolve().parent / "fixtures"
SAMPLE = load_playbook(FIX / "sample_playbook")
ISSUED = ("S141", "Q12", "I3", "F7", "S12", "S13", "S1", "S4", "S101")
CITED = Ref("Q88", "q", "M-201, Invented.pdf page 9")
FAMILY = Family("Exhaust Fan", ("EF-1", "EF-2"), Count(2))


@pytest.fixture(scope="module")
def job() -> Job:
    base = Job.from_dict(json.loads((FIX / "sample_job.json").read_text(encoding="utf-8")))
    return _device_refs(base, [Ref(i, "q", "M-101, Drawings.pdf page 2") for i in ("S141", "Q12", "I3", "F7", "S101")])


def _device_refs(job: Job, refs, key="VRF") -> Job:
    def add(s):
        if s.key != key:
            return s
        return replace(s, devices=(replace(s.devices[0], refs=s.devices[0].refs + tuple(refs)),) + s.devices[1:])
    return replace(job, systems=tuple(add(s) for s in job.systems))


def _sequence_refs(job: Job, refs, key="VRF") -> Job:
    return replace(job, systems=tuple(replace(s, sequence_refs=s.sequence_refs + tuple(refs)) if s.key == key else s
                                      for s in job.systems))


def _tags(job: Job, key: str, tags) -> Job:
    def retag(s):
        if s.key != key:
            return s
        return replace(s, families=(replace(s.families[0], tags=tuple(tags)),) + s.families[1:])
    return replace(job, systems=tuple(retag(s) for s in job.systems))


def _intake(text: str, device_refs=(), sheets=(), tags=("EF-1", "EF-2")):
    """The real intake on one EF note clarification, the answer's device citing `device_refs` too: the stored text,
    or None when refused."""
    skeleton = System("EF", "Exhaust Fans", "Exhaust Fan", "field", (FAMILY,),
                      sequence_refs=tuple(Ref(i, "q", "M-101, Invented.pdf page 2") for i in ISSUED))
    device = Device("EF.d1", "controller", "DDC Controller", "Furnish and Install", "AME", "AME", "AME", Count(2),
                    (CITED, *device_refs))
    answer = System("EF", "Exhaust Fans", "Exhaust Fan", "field", (FAMILY,), devices=(device,),
                    clarifications=(Clarification("note", text),)).to_dict()
    known = frozenset({*ISSUED, CITED.source_id, *(r.source_id for r in device_refs)})
    extra = {"sheets": tuple(sheets)} if sheets else {}             # rebuild d73d6e6 had no sheets argument
    written, _ = ai._check_system(answer, skeleton, None, known, (), (), [], tags, (), **extra)
    return written.clarifications[0].text if written is not None else None


def _note(job: Job, text) -> Job:
    clar = (Clarification("note", text),) if text is not None else ()
    return replace(job, systems=tuple(replace(s, clarifications=clar) if s.key == "EF" else s for s in job.systems))


def _downstream(job: Job, text: str):
    """(the EF note's id findings, the EF lines the note adds to the proposal)."""
    before = [l.text for l in render(_note(job, None), SAMPLE).lines if l.system_key == "EF"]
    j = _note(job, text)
    found = [f.severity for f in validate(j, SAMPLE)
             if f.rule == RULE["ids"] and f.system_key == "EF" and f.device_id is None]
    added = " | ".join(l.text for l in render(j, SAMPLE).lines if l.system_key == "EF" and l.text not in before)
    return found, added


def _prints(printed: str, token: str) -> bool:
    flat = unicodedata.normalize("NFKC", printed).replace("​", "")
    return re.search(rf"(?<![A-Za-z0-9]){re.escape(token)}(?![0-9])", flat, re.IGNORECASE) is not None


# ---- L-A: a writer's device ref never makes a sheet --------------------------------------------------------------

@pytest.mark.parametrize("where", ["S141, Mechanical.pdf page 3", "Sheet S141, Mechanical.pdf page 3"])
def test_a_where_on_the_writers_own_device_ref_never_makes_an_issued_id_a_sheet_at_intake(where):
    assert _intake("Valves per S141.", device_refs=(Ref("Q12", "q", where),)) is None


@pytest.mark.parametrize("where", ["S141, Mechanical.pdf page 3", "Sheet S141, Mechanical.pdf page 3"])
def test_a_where_on_a_device_ref_never_protects_an_issued_id_but_a_planners_where_does(job, where):
    """SP3 and SP3b: a device ref's where is the writer's; validate and render ignore it as a sheet. The same where
    on the planner's sequence refs is the job's evidence, and S141 is a sheet number there (the ruling)."""
    found, printed = _downstream(_device_refs(job, [Ref("Q12", "q", where)]), "Valves per S141.")
    assert "must_fix" in found and not _prints(printed, "S141"), (found, printed)
    planned = _sequence_refs(job, [Ref("Q12", "q", where)])
    assert _downstream(planned, "Valves per S141.") == ([], "*Valves per S141")      # render drops the stop
    assert "S141" in citations.job_sheets(planned)


def test_the_jobs_known_sheets_come_from_the_planners_refs_only(job):
    j = _device_refs(job, [Ref("Q12", "q", "Sheet S13, Mechanical.pdf page 3")], key="RTU")
    j = _sequence_refs(j, [Ref("Q3", "q", "S101, Structural.pdf page 3")], key="RTU")
    sheets = citations.job_sheets(j)
    assert "S101" in sheets and "S13" not in sheets, sheets
    assert citations.SourceIds.of_job(j).sheets == sheets


# ---- L-B: one K for the whole plan, given to every writer --------------------------------------------------------

def test_a_sheet_the_run_passes_is_accepted_at_intake_and_the_writer_takes_it_keyword_only():
    assert _intake("Damper per S101") is None                          # no where names S101 as a sheet
    assert _intake("Damper per S101", sheets=("S101",)) == "Damper per S101"
    assert _intake("Valves per S141.", sheets=("S101",)) is None       # an issued id that is no sheet stays refused


def test_intake_validator_and_render_agree_on_a_sheet_only_another_systems_planner_ref_names(job):
    j = _sequence_refs(job, [Ref("Q3", "q", "Sheet S101, Structural.pdf page 3")])
    assert _downstream(j, "Damper per S101") == ([], "*Damper per S101")
    assert _intake("Damper per S101", sheets=citations.job_sheets(j)) == "Damper per S101"


# ---- L-C: hyphen and underscore tag forms ------------------------------------------------------------------------

@pytest.mark.parametrize("tags, protected", [
    (["S-1"], {"S1"}),
    (["S_1A"], {"S1A"}),
    (["AHU_S12"], {"S12"}),
    (["S-1", "EF-1", "CS-1", "SF-1", "IC-3", "FCU-1", "S-12345", "AHU_S12X3"], {"S1"}),
    (["S-12"], {"S12"}),                                # never S1
])
def test_a_hyphen_or_underscore_tag_protects_its_plain_form_and_nothing_else(tags, protected):
    assert citations.tag_tokens(tags) == frozenset(protected)


def test_a_hyphen_tag_protects_the_plain_form_in_every_stage_and_a_device_name_is_never_a_tag(job):
    """A documents tag "S-1" protects a writer's "S1" (S1 issued) at intake, in the validator and at render. A device
    named "S12" (one id-shaped token) never becomes a tag of the whole job: "Interlock per S12" stays must_fix."""
    j = _tags(job, "EF", ["EF-1", "S-1"])
    rtu = j.system("RTU")
    j = replace(j, systems=tuple(replace(s, devices=(replace(rtu.devices[0], name="S12"),) + rtu.devices[1:])
                                 if s.key == "RTU" else s for s in j.systems))
    assert _intake("Supply fan S1 on a VFD", tags=citations.job_tags(j)) == "Supply fan S1 on a VFD"
    assert _downstream(j, "Supply fan S1 on a VFD") == ([], "*Supply fan S1 on a VFD")
    assert "S12" not in citations.tag_tokens(citations.job_tags(j))
    assert _intake("Interlock per S12", tags=citations.job_tags(j)) is None
    found, printed = _downstream(j, "Interlock per S12")
    assert "must_fix" in found and not _prints(printed, "S12"), (found, printed)
