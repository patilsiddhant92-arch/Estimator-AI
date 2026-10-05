"""Review of record, cleanup round 4 (both fixes of the source-id detector): intake, validator and renderer must
agree on every probe text under the estimator's ruling of 2026-10-05. Invented fixture only.

Ruling: a sheet number or a tag is kept even when the job issued the same id; an unissued lookalike ("(F1, F2)",
"See C101", "(see S999)") is accepted as written; only an issued id, or an unissued token joined to one, is refused;
prose is never rewritten; render cuts the token only.
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
ISSUED = ("S141", "Q12", "I3", "F7", "S12", "S13", "S1", "S4")
TAGS = ("EF-1", "EF-2", "AHU-1", "VAV-4")
CITED = Ref("Q88", "q", "M-201, Invented.pdf page 9")
FAMILY = Family("Exhaust Fan", ("EF-1", "EF-2"), Count(2))


@pytest.fixture(scope="module")
def job() -> Job:
    """The invented fixture (S1..S14, Q1..Q4, I1 issued) with S141, Q12, I3 and F7 issued too (refs on VRF.d1)."""
    base = Job.from_dict(json.loads((FIX / "sample_job.json").read_text(encoding="utf-8")))
    return _with_refs(base, [Ref(i, "q", "M-101, Drawings.pdf page 2") for i in ("S141", "Q12", "I3", "F7")])


def _with_refs(job: Job, refs) -> Job:
    def add(s):
        if s.key != "VRF":
            return s
        return replace(s, devices=(replace(s.devices[0], refs=s.devices[0].refs + tuple(refs)),) + s.devices[1:])
    return replace(job, systems=tuple(add(s) for s in job.systems))


def _intake(text: str, issued=ISSUED, extra_refs=()):
    """The real intake on one EF note clarification: the stored text, or None when refused."""
    skeleton = System("EF", "Exhaust Fans", "Exhaust Fan", "field", (FAMILY,),
                      sequence_refs=tuple(Ref(i, "q", "M-101, Invented.pdf page 2") for i in issued) + tuple(extra_refs))
    device = Device("EF.d1", "controller", "DDC Controller", "Furnish and Install", "AME", "AME", "AME", Count(2),
                    (CITED,))
    answer = System("EF", "Exhaust Fans", "Exhaust Fan", "field", (FAMILY,), devices=(device,),
                    clarifications=(Clarification("note", text),)).to_dict()
    written, _ = ai._check_system(answer, skeleton, None, frozenset({*issued, CITED.source_id}), (), (), [], TAGS)
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
    return re.search(rf"(?<![A-Za-z0-9]){re.escape(unicodedata.normalize('NFKC', token))}(?![0-9])", flat,
                     re.IGNORECASE) is not None


@pytest.mark.parametrize("text", [
    "Fans (F1, F2) start/stop",                          # unissued lookalikes in brackets
    "Two valves (see S999).",                            # unissued, bracket + cue word
    "Existing controller (I30) stays",                   # unissued I in a bracket (not F/C)
    "Count per Q999 keynote",                            # unissued Q after a cue word
    "Per S141A the valve is two-way",                    # S141A is not the issued S141
    "Spare points per F9032 list",                       # four-digit unissued fact lookalike
    "Branch selector count per sheet S12 and S13",       # issued ids that are sheet numbers
    "Damper actuators per sheet S141 and S142.",
    "Sheets C101, S141 and C102 show the dampers",       # an issued id inside a sheet list
    "Dwg S141 shows two dampers",
])
def test_a_text_the_ruling_accepts_is_accepted_by_intake_unreported_and_printed_whole(job, text):
    assert _intake(text) == text
    found, printed = _downstream(job, text)
    assert found == [], found
    assert text.rstrip(".") in printed, printed


@pytest.mark.parametrize("text, issued", [
    ("Valves per S141.", "S141"),
    ("Valves per S141 and S999.", "S141"),
    ("Two valves (S141)", "S141"),
    ("Supply fan S1 on a VFD", "S1"),                    # a bare S1 that is no tag
    ("Interlock per S12", "S12"),                        # S12 with no sheet word is the id
    ("Fans (F1, F2) per S141", "S141"),
    ("Valves per S​141", "S141"),                   # zero-width inside the id
    ("Valves per Ｓ１４１", "S141"),     # full-width id
    ("Per S13 and sheet S12 the count is two", "S13"),
])
def test_a_text_with_an_issued_id_is_refused_must_fix_and_never_prints_the_id(job, text, issued):
    assert _intake(text) is None
    found, printed = _downstream(job, text)
    assert "must_fix" in found, found
    assert not _prints(printed, issued), printed


def test_a_device_named_by_an_issued_id_never_protects_that_id_in_another_text(job):
    """A device named "S12" (a stale name) is a must_fix, not a tag: "Interlock per S12" in another system's note
    is still must_fix and loses the token at render."""
    rtu = job.system("RTU")
    j = replace(job, systems=tuple(replace(s, devices=(replace(rtu.devices[0], name="S12"),) + rtu.devices[1:])
                                   if s.key == "RTU" else s for s in job.systems))
    assert "S12" not in citations.job_tags(j)
    found = {(f.system_key, f.device_id, f.severity) for f in validate(_note(j, "Interlock per S12"), SAMPLE)
             if f.rule == RULE["ids"]}
    assert ("RTU", "RTU.d1", "must_fix") in found and ("EF", None, "must_fix") in found, found
    ef = [l.text for l in render(_note(j, "Interlock per S12"), SAMPLE).lines if l.system_key == "EF"]
    assert not any(_prints(line, "S12") for line in ef), ef


@pytest.mark.xfail(strict=True, reason="lead report concern 2: the intake knows only the sheets of its own system's "
                                       "refs; render keeps the same text (safe direction: refused, never cut)")
def test_a_sheet_number_another_systems_ref_names_is_accepted_at_intake_too(job):
    j = _with_refs(job, [Ref("Q3", "q", "Sheet S101, Structural.pdf page 3"), Ref("S101", "q", "M-101, x.pdf page 2")])
    assert _downstream(j, "Damper per S101") == ([], "*Damper per S101")      # render keeps it as a sheet
    assert _intake("Damper per S101", issued=ISSUED + ("S101",)) == "Damper per S101"


@pytest.mark.xfail(strict=True, reason="lead report concern 3: a where the writer types, starting with another "
                                       "issued id and a file part, makes that id a sheet job-wide")
def test_a_where_starting_with_another_issued_id_never_protects_that_id(job):
    j = _with_refs(job, [Ref("Q12", "q", "S141, Mechanical.pdf page 3")])
    found, printed = _downstream(j, "Valves per S141.")
    assert "must_fix" in found and not _prints(printed, "S141"), (found, printed)
