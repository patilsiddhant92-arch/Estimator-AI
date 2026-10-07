"""Review of record, source-id detector gaps (lead/detector-gaps): extra probes the author's tests do not cover.
Invented fixture only.

- The hyphen and underscore tag forms protect only an id-shaped part of a tag, never a longer number, a part glued
  to a letter or digit, or a doubled separator; the read is linear in the length of the tags.
- The narrower K (planner's wheres only): a sheet number that only a writer's device ref names, and that is also an
  issued id, is refused at intake, must_fix in the validator and cut at render: the three stages agree (it used to be
  kept by all three on rebuild d73d6e6).
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import replace
from pathlib import Path

import pytest

from timing import grows_linearly
from bms import ai, citations
from bms.model import Clarification, Count, Device, Job, Ref
from bms.playbook import load_playbook
from bms.render import render
from bms.validate import RULE, validate

FIX = Path(__file__).resolve().parent / "fixtures"
SAMPLE = load_playbook(FIX / "sample_playbook")


@pytest.fixture(scope="module")
def job() -> Job:
    return Job.from_dict(json.loads((FIX / "sample_job.json").read_text(encoding="utf-8")))


def _device_refs(job: Job, refs, key: str) -> Job:
    def add(s):
        if s.key != key:
            return s
        return replace(s, devices=(replace(s.devices[0], refs=s.devices[0].refs + tuple(refs)),) + s.devices[1:])
    return replace(job, systems=tuple(add(s) for s in job.systems))


def _note(job: Job, text) -> Job:
    clar = (Clarification("note", text),) if text is not None else ()
    return replace(job, systems=tuple(replace(s, clarifications=clar) if s.key == "EF" else s for s in job.systems))


def _downstream(job: Job, text: str):
    before = [l.text for l in render(_note(job, None), SAMPLE).lines if l.system_key == "EF"]
    j = _note(job, text)
    found = [f.severity for f in validate(j, SAMPLE)
             if f.rule == RULE["ids"] and f.system_key == "EF" and f.device_id is None]
    added = " | ".join(l.text for l in render(j, SAMPLE).lines if l.system_key == "EF" and l.text not in before)
    return found, added


def _intake(job: Job, text: str, device_refs=()):
    """The real intake on an EF note, given what the run gives it (job ids, job tags, the plan's K)."""
    skeleton = replace(job.system("EF"), devices=(), clarifications=())
    device = Device("EF.d1", "controller", "DDC Controller", "Furnish and Install", "AME", "AME", "AME", Count(2),
                    (Ref("S2", "q", "M-101, Invented.pdf page 1"), *device_refs))
    answer = replace(skeleton, devices=(device,), clarifications=(Clarification("note", text),)).to_dict()
    ids = citations.job_ids(job)
    known = frozenset({*ids, "S2", *(r.source_id for r in device_refs)})
    written, _ = ai._check_system(answer, skeleton, None, known, (), (), [], citations.job_tags(job), ids,
                                  sheets=tuple(citations.job_sheets(job)))
    return written.clarifications[0].text if written is not None else None


def _prints(printed: str, token: str) -> bool:
    flat = unicodedata.normalize("NFKC", printed)
    return re.search(rf"(?<![A-Za-z0-9]){re.escape(token)}(?![0-9])", flat, re.IGNORECASE) is not None


# ---- hyphen and underscore tag forms -------------------------------------------------------------------------------

@pytest.mark.parametrize("tag", ["S-12345", "XS-1", "1S-1", "S--1", "S__1", "S-1A2", "AHU_S12X3", "EF-1", "CS-1",
                                 "S\u20101", "S\u20131", "S-\u200b1", "S\u00ad1",
                                 # the estimator's ruling (lead/detector-fix3, R-2): a tag is protected only in the
                                 # form it is written, so a hyphen or underscore between the letter and the digits
                                 # protects no plain id
                                 "s-1", "\uff33\uff0d\uff11", "Fan F-1/F-2", "S_1_2", "S-1.5", "S-1/2", "EF-S-1",
                                 "F-1", "C-1", "Q-1", "I-1", "S_1A", "S-12", "S-1-2", "F-1 thru F-4", "C-1 to 4",
                                 "S-0001"])
def test_a_tag_form_that_is_no_plain_id_part_protects_nothing(tag):
    """A longer number, a letter or digit glued in front, a doubled separator, a trailing digit-letter-digit, a
    unicode hyphen or dash (NFKC keeps it), and a hyphen or underscore between the letter and the digits (also in a
    range) never make a protected id."""
    assert citations.tag_tokens([tag]) == frozenset(), tag


@pytest.mark.parametrize("tag, protected", [("AHU-S1", {"S1"}), ("_S1", {"S1"}), ("S1_", {"S1"}),
                                            ("AHU_S12", {"S12"}), ("Fan F1/F2", {"F1", "F2"}),
                                            ("F1 thru F-3", {"F1"})])
def test_a_tag_part_after_a_separator_protects_its_plain_form(tag, protected):
    """Only where the scanner itself reads the plain id inside the written tag ("AHU_S12": the underscore is a
    boundary for the scanner)."""
    assert citations.tag_tokens([tag]) == frozenset(protected)


@pytest.mark.slow
def test_reading_the_tag_forms_is_linear_in_the_length_of_the_tags():
    for piece in ("S-1_", "S-", "_S", "S-1-", "AHU_S12"):
        # growth, not a wall-clock limit (it flaked under load)
        assert grows_linearly(lambda n, piece=piece: citations.tag_tokens([piece * (n // len(piece))]), 20_000), piece


# ---- the narrower K: a sheet only a writer's device ref names -------------------------------------------------------

@pytest.mark.parametrize("where, token", [("C2, Controls.pdf page 4", "C2"),
                                          ("Sheet C2, Controls.pdf page 4", "C2"),
                                          ("S101, Structural.pdf page 3", "S101")])
def test_a_sheet_only_a_writers_device_ref_names_is_refused_must_fix_and_cut_alike(job, where, token):
    j = _device_refs(job, [Ref(token, "q", "M-101, Invented.pdf page 2")], "VRF")       # the token is issued
    j = _device_refs(j, [Ref("Q2", "q", where)], "RTU")                               # only a device ref names it
    assert token not in citations.job_sheets(j)
    text = f"Points per {token}"
    assert _intake(j, text) is None
    assert _intake(j, text, device_refs=(Ref("Q2", "q", where),)) is None              # its own device ref too
    found, printed = _downstream(j, text)
    assert "must_fix" in found and not _prints(printed, token), (found, printed)
    # the lead's ruling on L-D (lead/final-c): a sheet word is no way out for an issued id any more; it is refused,
    # must_fix and cut alike. It prints only once a planner's where names it as a sheet (K).
    assert _intake(j, f"Points per sheet {token}") is None
    found, printed = _downstream(j, f"Points per sheet {token}")
    assert "must_fix" in found and not _prints(printed, token), (found, printed)
