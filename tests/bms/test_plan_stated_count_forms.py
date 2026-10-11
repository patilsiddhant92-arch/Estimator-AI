"""HP 8: a count stated beside a tag reads 4 in each of its four forms, "CUH-A (TYP. OF 4 PLACES)", "CUH-A(4)",
"4x CUH-A" and "CUH-A x4", in every reader of it: the label reader that the inventory and the dossier's counts line use
(`estimator.catalogue.tags`), and the planner's reading (`bms.plan_read`) of a group fact and of the dossier's sheet
text. Ruling L1 is kept: the same stated count on sheets of one floor and area counts once, and the sum is kept in
`Count.added_up`. A count that is out of reach is counted once and named, as before. Invented fixtures only."""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

import pytest

from estimator.catalogue.tags import label_keys, line_labels, plan_labels, unread_counts

from bms.model import OtherCount
from bms.plan_read import TIMES_AFTER, stated_number, times_form

from test_plan import L2_DUCT, L2_PIPE, L3_DUCT, _by_key, _counts_hold, _cuh_group, _cuh_job, _sheet_dossier

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_final_o_counts import MECH, _job, _read, _same        # noqa: E402

FOUR = ["CUH-A (TYP. OF 4 PLACES)", "CUH-A(4)", "4x CUH-A", "CUH-A x4"]
OTHER_WORDINGS = ["CUH-A (TYP OF 4 PLACES)", "CUH-A (TYPICAL OF 4 LOCATIONS)", "CUH-A TYP. OF 4 PLACES",
                  "CUH-A TYP OF 4 PLCS", "CUH-A(TYP. OF 4)", "CUH-A (TYP. OF 4.)", "4 x CUH-A", "4X CUH-A", "4×CUH-A",
                  "4xCUH-A", "4 × CUH-A", "CUH-A X4", "CUH-A ×4"]
KEYS = label_keys(["CUH-A", "CUH-B", "VAV-1", "VAV-3"])


# ---- the label reader: the inventory's and the dossier's counts line ------------------------------------------------

@pytest.mark.parametrize("line", FOUR + OTHER_WORDINGS)
def test_each_form_of_a_stated_count_is_four_places_for_the_label_reader(line):
    assert line_labels(line, KEYS) == Counter({"CUH-A": 4})
    assert plan_labels(line, KEYS) == Counter({"CUH-A": 4})            # a type's tag: no backstop adds to it
    assert unread_counts(line, KEYS) == []


@pytest.mark.parametrize("line, tag, n", [("2x VAV-3", "VAV-3", 2), ("VAV-3(2)", "VAV-3", 2)])
def test_a_unit_tag_takes_its_stated_count_in_the_new_forms_too(line, tag, n):
    assert line_labels(line, KEYS) == Counter({tag: n})


@pytest.mark.parametrize("line", ["4 CUH-A", "2-CUH-A", "CUH-A 4", "CUH-A 24X24", "CUH-A (0)", "CUH-A(0)",
                                  "0x CUH-A", "CUH-A (TYP. OF 0 PLACES)"])
def test_no_multiplier_reads_as_one_place_never_more(line):
    """A bare number, a dash, a size and a zero state no count: the tag is one place, as before."""
    assert line_labels(line, KEYS) == Counter({"CUH-A": 1})


@pytest.mark.parametrize("line", ["CUH-A (TYP. OF 60 PLACES)", "CUH-A(60)", "60x CUH-A", "CUH-A (TYP. OF FOUR PLACES)"])
def test_a_count_out_of_reach_is_one_place_and_named(line):
    assert line_labels(line, KEYS) == Counter({"CUH-A": 1})
    assert unread_counts(line, KEYS) == [("CUH-A", line)]


def test_a_note_in_brackets_beside_a_tag_is_still_no_count():
    assert line_labels("VAV-3 (OFFICE 101)", KEYS) == Counter({"VAV-3": 1})
    assert unread_counts("VAV-3 (OFFICE 101)", KEYS) == []


# ---- the planner's reading: a group fact ---------------------------------------------------------------------------

@pytest.mark.parametrize("form", FOUR + OTHER_WORDINGS)
def test_times_form_writes_each_stated_count_as_times_four(form):
    assert times_form(f"AHU, {form}", ["CUH-A"]) == "AHU, CUH-A ×4"


def test_times_form_reads_a_count_before_a_tag_inside_a_bracket_and_leaves_a_dash_alone():
    assert times_form("AHU, CUH (4x CUH-A, CUH-B)", ["CUH-A", "CUH-B"]) == "AHU, CUH (CUH-A ×4, CUH-B)"
    assert times_form("AHU, 2-CUH-A") == "AHU, 2-CUH-A"
    assert times_form("AHU, 0x CUH-A") == "AHU, 0x CUH-A"


@pytest.mark.parametrize("form", [f for f in FOUR if not f.startswith("4x")])
def test_stated_number_reads_four_from_the_forms_that_follow_the_tag(form):
    """TIMES_AFTER reads the forms after a tag; a count before the tag is read by `times_form` and the sheet reader."""
    found =re.compile(rf"(CUH-A){TIMES_AFTER}", re.I).search(form)
    assert found is not None and stated_number(found, 2) == 4 and found.group(0) == form


@pytest.mark.parametrize("value", ["AHU, CUH-A (TYP. OF 4 PLACES)", "AHU, CUH-A(4)", "AHU, 4x CUH-A", "AHU, CUH-A x4",
                                   "AHU, CUH (4x CUH-A)", "AHU, CUH (CUH-A (TYP. OF 4 PLACES))"])
def test_a_group_member_states_its_count_in_each_form(value):
    job = _cuh_group(value)
    systems = _by_key(job)
    cuh = next(f for f in systems["AHU-1 Plant"].families if f.name == "Cabinet Unit Heater")
    assert cuh.tags == ("CUH-A",) and cuh.count.value == 4
    assert systems["CUH"].families[0].tags == ("CUH-B",)
    _counts_hold(job)


# ---- the planner's reading: the dossier's sheet text, with ruling L1 -----------------------------------------------

@pytest.mark.parametrize("form", FOUR + OTHER_WORDINGS)
def test_a_sheet_that_states_a_count_in_any_form_gives_four(form):
    dossier = _sheet_dossier(("M-101", 3, L2_DUCT, f"{form} AT THE ENTRIES"))
    count = _cuh_job(dossier).systems[0].families[0].count
    assert count.value == 4 and count.added_up is None
    assert [(r.source_id, r.quote, r.where) for r in count.sources] == [("D7", form, "M-101, Drawings.pdf page 3")]


@pytest.mark.parametrize("form", FOUR)
def test_the_same_stated_count_on_two_sheets_of_one_floor_and_area_still_counts_once(form):
    dossier = _sheet_dossier(("M-101", 3, L2_DUCT, form), ("M-201", 4, L2_PIPE, form))
    count = _cuh_job(dossier).systems[0].families[0].count
    assert count.value == 4                                              # the sheets added up give 8
    assert count.added_up == OtherCount(8, count.sources[0])             # L1 keeps the sum, cited by the first sheet
    assert [r.source_id for r in count.sources] == ["D7", "D8"]


@pytest.mark.parametrize("form", FOUR)
def test_the_stated_counts_of_two_floors_add_up(form):
    dossier = _sheet_dossier(("M-101", 3, L2_DUCT, form), ("M-102", 5, L3_DUCT, form))
    count = _cuh_job(dossier).systems[0].families[0].count
    assert count.value == 8 and count.added_up is None


def test_the_forms_are_one_count_when_two_sheets_of_one_floor_word_it_differently():
    dossier = _sheet_dossier(("M-101", 3, L2_DUCT, "CUH-A (TYP. OF 4 PLACES)"), ("M-201", 4, L2_PIPE, "4x CUH-A"))
    count = _cuh_job(dossier).systems[0].families[0].count
    assert count.value == 4 and count.added_up.value == 8


def test_each_tag_counts_the_most_of_one_sheet_of_the_group_in_any_form():
    dossier = _sheet_dossier(("M-101", 3, L2_DUCT, "4x CUH-A CUH-B(2)"), ("M-201", 4, L2_PIPE, "CUH-A (TYP. OF 3 PLACES) 5x CUH-B"))
    assert _cuh_job(dossier).systems[0].families[0].count.value == 4 + 5


def test_a_count_before_a_tag_is_no_part_of_a_longer_tag_or_a_size():
    dossier = _sheet_dossier(("M-101", 3, L2_DUCT, "4x CUH-AB 24X24 CUH-A 3x CUH-A-1"))
    count = _cuh_job(dossier, count=2).systems[0].families[0].count
    assert count.value == 2 and count.others == ()


# ---- both sides: the inventory's placements and the dossier's counts line --------------------------------------------

@pytest.mark.parametrize("form", FOUR)
def test_each_form_counts_four_on_both_sides(tmp_path, form):
    catalogue = _job([(MECH, 1, "M-101", "HVAC LEVEL 1 PLAN", [form, "VAV-1"], ())])
    inventory, dossier, _flags, _s, _lines = _read(catalogue, tmp_path)
    _same(inventory, dossier, CUH=4)


@pytest.mark.parametrize("form", ["CUH-A (TYP. OF 60 PLACES)", "CUH-A(60)", "60x CUH-A"])
def test_a_count_out_of_reach_is_counted_once_and_named_on_the_counts_line(tmp_path, form):
    catalogue = _job([(MECH, 1, "M-101", "HVAC LEVEL 1 PLAN", [form], ())])
    inventory, dossier, _flags, _s, lines = _read(catalogue, tmp_path)
    _same(inventory, dossier, CUH=1)
    assert f"CUH-A on M-101 reads '{form}': the count beside it is not read" in lines["CUH"]
