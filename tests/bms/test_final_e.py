"""FINAL-E: the where checks read the same detection copy as `scan` (F1), the count note goes through the safety net
(F1), a hand-edited Change's where gets its card (F2), one sheet pattern and one set of sheet words (F3), the where
refusal's advice (F4), and a tag in a where as in text (F5). Invented fixture only."""
from __future__ import annotations

import pytest

from bms.citations import SourceIds, ref_sheets
from bms.model import Ref

from bms import ai, run
from bms.citations import job_ids, job_sheets, job_tags
from bms.validate import RULE, validate

from test_review_final3 import SAMPLE, _base, _changed, _job, _prints, _verdicts, _with_other_count

FULL_S = "Ｓ"            # a full-width S
ZW = "​"                # a zero-width space


# ---- F1: one detection copy for every where check ---------------------------------------------------------------

@pytest.mark.parametrize("where", [f"Sheet {FULL_S}141, Mechanical.pdf page 3", f"{FULL_S}141, Mechanical.pdf page 3",
                                   f"Sheet S{ZW}141, Mechanical.pdf page 3"])
def test_a_disguised_issued_id_in_a_where_is_no_place_and_is_found_by_where_issued(where):
    ids = SourceIds.of(["S141"])
    assert ids.sheet(where) == "" and ids.place(where) == ""
    if where.lower().startswith("sheet"):
        assert ids.where_issued(where) == ["S141"]


def test_a_disguised_id_in_a_section_part_is_no_place():
    assert SourceIds.of(["S141"]).place(f"Mechanical schedule {FULL_S}141, Mechanical.pdf page 3") == ""


def test_a_planner_where_with_a_full_width_sheet_makes_it_known():
    assert ref_sheets([Ref("Q2", "q", f"Sheet {FULL_S}101, Structural.pdf page 3")]) == frozenset({"S101"})
    known = SourceIds.of(["S101"], [], ["S101"])
    assert known.place(f"Sheet {FULL_S}101, Structural.pdf page 3") == "S101"     # printed as detection reads it


def test_the_count_note_goes_through_the_safety_net(monkeypatch):
    """Even when a place lets an issued id through, the count note never prints it (token only)."""
    job = _with_other_count(_job(), "Sheet M401, Mechanical.pdf page 3")
    assert _prints(job, "M401")
    real = SourceIds.sheet
    monkeypatch.setattr(SourceIds, "sheet", lambda self, where: "S141" if "M401" in where else real(self, where))
    assert not _prints(job, "S141")


# ---- F2: a hand-edited Change's where ----------------------------------------------------------------------------

def test_a_hand_edited_change_whose_device_ref_where_names_a_disguised_issued_id_gets_the_card():
    base = _base()
    device = base.system("EF").devices[0]
    refs = device.refs + (Ref("Q2", "q", f"Sheet {FULL_S}6, Mechanical.pdf page 3"),)
    job, decision = _changed(base, refs=refs)
    assert [f.severity for f in validate(job, SAMPLE) if f.rule == RULE["ids"] and f.device_id == "EF.d1"] \
        == ["must_fix"]
    assert [(device_id, tokens) for _, device_id, tokens in run._ids_in_changes(job, [decision])] \
        == [("EF.d1", ("S6",))]


# ---- F3: one sheet pattern, one set of sheet words ---------------------------------------------------------------

REFUSED = ("refused", "must_fix", "cut")
ACCEPTED = ("accepted", "none", "prints")


@pytest.mark.parametrize("probe, token, sheets, verdict", [
    ("Dwg No. S141, Mechanical.pdf page 3", "S141", (), REFUSED),
    ("Sheets: S141, Mechanical.pdf page 3", "S141", (), REFUSED),
    ("Sheet # S141, Mechanical.pdf page 3", "S141", (), REFUSED),
    ("Sheet S2010, Structural.pdf page 4", "S2010", ("S2010",), ACCEPTED),       # a known four-digit sheet prints
    ("sheet s141, Mechanical.pdf page 3", "s141", ("s141",), ACCEPTED),          # a known lower-case sheet prints
])
def test_intake_validator_and_render_agree_on_the_wider_sheet_forms(probe, token, sheets, verdict):
    assert _verdicts("where", probe, token, sheets) == verdict


def test_the_planner_names_sheets_in_every_sheet_form_and_a_decimal_is_no_id():
    refs = [Ref("Q2", "q", "Sheet S2010, Structural.pdf page 4"), Ref("Q3", "q", "sheet c101, Civil.pdf page 1"),
            Ref("Q4", "q", "Sheet No. F12, Fire.pdf page 2"), Ref("Q5", "q", "Sheet: Q7, Plumbing.pdf page 2"),
            Ref("Q6", "q", "Sheet S14.5, Structural.pdf page 5")]
    assert ref_sheets(refs) == frozenset({"S2010", "C101", "F12", "Q7"})
    assert SourceIds.of(["S14"]).where_issued("Sheet S14.5, Structural.pdf page 5") == []
    assert SourceIds.of(["S14"]).sheet("Sheet S14.5, Structural.pdf page 5") == "S14.5"
    found = SourceIds.of(["S141"]).scan("Valves per Sheet No. C2.")
    assert [(f.token, f.kind) for f in found] == [("C2", "sheet")]


# ---- F4: the where refusal's advice ------------------------------------------------------------------------------

def test_the_intake_and_the_validator_both_say_to_copy_the_where_as_the_evidence_gives_it():
    job = _with_other_count(_job(), "Sheet S201, Structural.pdf page 4")
    system = job.system("EF")
    written, problems = ai._check_system(system.to_dict(), system, None, frozenset(job_ids(job)), (), (), [],
                                         job_tags(job), job_ids(job), tuple(job_sheets(job)))
    said = " ".join(p for p in problems if "S201" in p)
    assert written is None and "copy the where exactly as the evidence gives it" in said
    assert "with no sheet word added" in said and "give the sheet number" not in said
    fixes = [f.fix for f in validate(job, SAMPLE) if f.rule == RULE["ids"] and f.device_id == "EF.d1"]
    assert len(fixes) == 1 and fixes[0].startswith("Copy the where exactly as the evidence gives it")


# ---- F5: a tag in a where, as in text ----------------------------------------------------------------------------

def test_a_tag_that_is_also_an_issued_id_reads_alike_in_text_and_in_a_where():
    ids = SourceIds.of(["C101", "S141"], ["C101"])
    assert ids.where_issued("Sheet C101, Civil.pdf page 1") == []
    assert ids.sheet("Sheet C101, Civil.pdf page 1") == "C101"
    assert ids.sheet("Fan C101 schedule, Civil.pdf page 1") == ""       # a tag is still a sheet only in sheet form
    assert ids.where_issued("Sheet S141, Civil.pdf page 1") == ["S141"]      # an issued id that is no tag still is
    assert [f.kind for f in ids.scan("Valves per Sheet C101.")] == []    # the text side: a tag, never reported
    assert _verdicts("where", "Sheet Ｃ101, Civil.pdf page 1", "C101", (), "C101") == ACCEPTED
