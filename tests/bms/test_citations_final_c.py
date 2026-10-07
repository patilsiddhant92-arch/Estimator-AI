"""L-D tightened (the lead's ruling, lead/final-c, review R-4): a sheet word no longer makes an issued source id
printable. An issued id after a sheet word, in client text or in a where the writer typed on a device ref, prints
only when it is a known sheet of the job (K, `job_sheets`: the planner's wheres); otherwise the intake refuses it,
the validator reports must_fix and the renderer cuts it, like any issued id. Tags, known sheets and unissued sheet
numbers after a sheet word stay accepted. Invented fixture only."""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import replace
from pathlib import Path

import pytest

from bms import ai, citations
from bms.citations import SourceIds
from bms.model import Clarification, Count, Device, Family, Job, OtherCount, Ref, System
from bms.playbook import load_playbook
from bms.render import render
from bms.validate import RULE, validate

FIX = Path(__file__).resolve().parent / "fixtures"
SAMPLE = load_playbook(FIX / "sample_playbook")
ISSUED = ("S141", "Q12", "S12", "S13")
CITED = Ref("Q88", "q", "M-201, Invented.pdf page 9")
FAMILY = Family("Exhaust Fan", ("EF-1", "EF-2"), Count(2))


@pytest.fixture(scope="module")
def job() -> Job:
    base = Job.from_dict(json.loads((FIX / "sample_job.json").read_text(encoding="utf-8")))
    return _device_refs(base, [Ref("S141", "q", "M-101, Drawings.pdf page 2")], key="VRF")


def _device_refs(job: Job, refs, key="EF") -> Job:
    def add(s):
        if s.key != key:
            return s
        return replace(s, devices=(replace(s.devices[0], refs=s.devices[0].refs + tuple(refs)),) + s.devices[1:])
    return replace(job, systems=tuple(add(s) for s in job.systems))


def _sequence_refs(job: Job, refs, key="VRF") -> Job:
    return replace(job, systems=tuple(replace(s, sequence_refs=s.sequence_refs + tuple(refs)) if s.key == key else s
                                      for s in job.systems))


def _other_count(job: Job, where: str, source_id="S141", key="EF") -> Job:
    """The first device of `key` counted 2 on M-001 and, by a second source whose ref has `where`, 1: the R-4 case
    (the quantity note prints "1 per <the place of where>")."""
    def add(s):
        if s.key != key:
            return s
        d = s.devices[0]
        quantity = Count(2, (Ref("S6", "q", "M-001, Drawings.pdf page 1"),), (OtherCount(1, Ref(source_id, "q", where)),))
        return replace(s, devices=(replace(d, quantity=quantity),) + s.devices[1:])
    return replace(job, systems=tuple(add(s) for s in job.systems))


def _note(job: Job, text) -> Job:
    clar = (Clarification("note", text),) if text is not None else ()
    return replace(job, systems=tuple(replace(s, clarifications=clar) if s.key == "EF" else s for s in job.systems))


def _ef_lines(job: Job) -> str:
    return " | ".join(l.text for l in render(job, SAMPLE).lines if l.system_key == "EF")


def _id_findings(job: Job, device=False):
    return [f for f in validate(job, SAMPLE) if f.rule == RULE["ids"] and f.system_key == "EF"
            and (f.device_id is not None) == device]


def _prints(printed: str, token: str) -> bool:
    flat = unicodedata.normalize("NFKC", printed)
    return re.search(rf"(?<![A-Za-z0-9]){re.escape(token)}(?![0-9])", flat, re.IGNORECASE) is not None


def _intake(text: str = "Valves as shown.", device_refs=(), sheets=(), others=()):
    """The real intake on one EF answer: the stored note, or None when refused; and the problems."""
    skeleton = System("EF", "Exhaust Fans", "Exhaust Fan", "field", (FAMILY,),
                      sequence_refs=tuple(Ref(i, "q", "M-101, Invented.pdf page 2") for i in ISSUED))
    quantity = Count(2, (), tuple(OtherCount(3, r) for r in others))
    device = Device("EF.d1", "controller", "DDC Controller", "Furnish and Install", "AME", "AME", "AME", quantity,
                    (CITED, *device_refs))
    answer = System("EF", "Exhaust Fans", "Exhaust Fan", "field", (FAMILY,), devices=(device,),
                    clarifications=(Clarification("note", text),)).to_dict()
    known = frozenset({*ISSUED, CITED.source_id, *(r.source_id for r in (*device_refs, *others))})
    written, problems = ai._check_system(answer, skeleton, None, known, (), (), [], ("EF-1", "EF-2"), (),
                                         sheets=tuple(sheets))
    return (written.clarifications[0].text if written is not None else None), problems


# ---- the detector ------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("text", ["Valves per sheet S12.", "See sheets S12 and C2.", "(sheet S12)", "Dwg S12",
                                  "per Sheet s12"])
def test_an_issued_id_after_a_sheet_word_is_issued_unless_it_is_a_known_sheet(text):
    ids = SourceIds.of(["S12"], [], [])
    assert "S12" in ids.refusal(text).upper(), text
    assert [f.kind for f in ids.scan(text) if f.token.upper() == "S12"] == ["issued"]
    known = SourceIds.of(["S12"], [], ["S12"])
    assert known.refusal(text) == "", text
    assert [f.kind for f in known.scan(text) if f.token.upper() == "S12"] == ["sheet"]


def test_an_unissued_number_after_a_sheet_word_and_a_tag_stay_accepted():
    ids = SourceIds.of(["S141", "F1"], ["F1"], [])
    assert ids.refusal("See sheet C2 and sheets C101, C102.") == ""
    assert ids.refusal("Fan F1 per sheet C2") == ""
    # a list after a sheet word: only the issued member is named; the unissued sheets beside it are not citations
    assert ids.refusal("sheets C101, S141 and C102") == f"prints the source id S141: {citations.REFUSAL}"
    assert ids.refusal("per sheet S12 and S13") == ""                       # nothing here is issued


def test_known_sheets_after_a_sheet_word_stay_accepted_while_an_issued_one_beside_them_is_named():
    ids = SourceIds.of(["S12", "S13", "S141"], [], ["S12", "S13"])
    assert ids.refusal("per sheet S12 and S13") == ""
    assert ids.refusal("per sheets S12, S141 and S13") == f"prints the source id S141: {citations.REFUSAL}"
    assert ids.without_issued("per sheets S12, S141 and S13") == "per sheets S12, and S13"


def test_the_place_of_a_where_never_prints_an_issued_id_after_a_sheet_word_unless_it_is_known():
    ids = SourceIds.of(["S141"], [], [])
    assert ids.place("Sheet S141, Mechanical.pdf page 3") == ""
    assert ids.sheet("Sheet S141, Mechanical.pdf page 3") == ""
    assert SourceIds.of(["S141"], [], ["S141"]).place("Sheet S141, Mechanical.pdf page 3") == "S141"
    assert ids.place("Sheet C2, Mechanical.pdf page 3") == "C2"               # unissued: a sheet number
    assert ids.place("Sheet M-101, Mechanical.pdf page 3") == "M-101"
    assert ids.where_issued("Sheet S141, Mechanical.pdf page 3") == ["S141"]
    assert ids.where_issued("Sheet C2, Mechanical.pdf page 3") == []
    assert SourceIds.of(["S141"], [], ["S141"]).where_issued("Sheet S141, Mechanical.pdf page 3") == []


@pytest.mark.slow
def test_the_detector_stays_linear_on_a_long_sheet_list():
    from timing import grows_linearly
    ids = SourceIds.of([f"S{n}" for n in range(1, 400)], [], [f"S{n}" for n in range(1, 400, 2)])
    assert grows_linearly(lambda n: ids.scan("sheets " + ", ".join(f"S{k % 900 + 1}" for k in range(n))), 2000)


# ---- client text: intake, validator and renderer agree -------------------------------------------------------------

def test_an_issued_id_after_a_sheet_word_is_refused_at_intake():
    text, problems = _intake("Valves per sheet S141.")
    assert text is None and any("S141" in p for p in problems), problems


def test_a_known_sheet_after_a_sheet_word_is_accepted_at_intake():
    assert _intake("Valves per sheet S12 and S13.", sheets=("S12", "S13"))[0] == "Valves per sheet S12 and S13."
    assert _intake("Valves per sheet C2.")[0] == "Valves per sheet C2."


def test_an_issued_id_after_a_sheet_word_is_must_fix_and_cut_at_render(job):
    j = _note(job, "Valves per sheet S141.")
    assert [f.severity for f in _id_findings(j)] == ["must_fix"]
    assert not _prints(_ef_lines(j), "S141"), _ef_lines(j)


def test_known_sheets_after_a_sheet_word_print_with_no_finding(job):
    j = _sequence_refs(job, [Ref("Q2", "q", "Sheet S12, Drawings.pdf page 5"),
                             Ref("Q2", "q", "Sheet S13, Drawings.pdf page 6")])
    assert {"S12", "S13"} <= citations.job_sheets(j)
    j = _note(j, "Valves per sheet S12 and S13.")
    assert _id_findings(j) == []
    assert "sheet S12 and S13" in _ef_lines(j)


# ---- a where the writer typed (R-4) ------------------------------------------------------------------------------

def test_r4_a_writers_where_naming_an_issued_id_after_a_sheet_word_prints_no_place(job):
    j = _other_count(job, "Sheet S141, Mechanical.pdf page 3")
    printed = _ef_lines(j)
    # the count with no place is left out of the quantity note; here that leaves no other count, so no note
    assert "per M-001" not in printed, printed
    assert not _prints(printed, "S141"), printed
    assert "per ;" not in printed and "per )" not in printed and not re.search(r"\bper\s*$", printed), printed


def test_r4_a_writers_where_naming_an_issued_id_after_a_sheet_word_is_must_fix(job):
    j = _other_count(job, "Sheet S141, Mechanical.pdf page 3")
    found = _id_findings(j, device=True)
    assert [f.severity for f in found] == ["must_fix"] and "S141" in found[0].what, found


@pytest.mark.parametrize("where", ["Sheet S141, Mechanical.pdf page 3", "Mechanical schedule, sheet S141"])
def test_r4_a_writers_where_naming_an_issued_id_after_a_sheet_word_is_refused_at_intake(where):
    text, problems = _intake(others=(Ref("Q12", "q", where),))
    assert text is None and any("S141" in p for p in problems), problems
    text, problems = _intake(device_refs=(Ref("Q12", "q", where),))
    assert text is None and any("S141" in p for p in problems), problems


def test_r4_a_writers_where_naming_a_known_sheet_or_an_unissued_one_stays_accepted(job):
    assert _intake(others=(Ref("Q12", "q", "Sheet S141, Mechanical.pdf page 3"),), sheets=("S141",))[0] is not None
    assert _intake(others=(Ref("Q12", "q", "Sheet C2, Mechanical.pdf page 3"),))[0] is not None
    assert _intake(others=(Ref("Q12", "q", "M-101, Mechanical.pdf page 3"),))[0] is not None
    known = _sequence_refs(job, [Ref("Q2", "q", "Sheet S141, Drawings.pdf page 5")])
    j = _other_count(known, "Sheet S141, Mechanical.pdf page 3")
    assert _id_findings(j, device=True) == []
    assert "1 per S141" in _ef_lines(j), _ef_lines(j)
