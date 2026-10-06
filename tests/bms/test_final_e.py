"""FINAL-E: the where checks read the same detection copy as `scan` (F1), the count note goes through the safety net
(F1), a hand-edited Change's where gets its card (F2), one sheet pattern and one set of sheet words (F3), the where
refusal's advice (F4), and a tag in a where as in text (F5). Invented fixture only."""
from __future__ import annotations

import pytest

from bms.citations import SourceIds, ref_sheets
from bms.model import Ref

from bms import run
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
