"""Bug 4, the count overshoot (bms/counts.py `_located_count`, bms/counts_text.py `family_pattern`):

(a) a unit's tag (one numbered unit, not a type) drawn on several plan sheets that are not one plan group (a riser
    label on every floor, a phase 2 or roof plan reusing the tags) was counted once per sheet, raising the printed
    count. A numbered tag names one unit (`estimator.catalogue.tags.is_type_tag`; rule R1: tagged equipment counts
    from the schedule), so it counts once over the sheets;
(b) a room named after its unit ("AHU-9X", a mechanical room label) matched the family's generic numbered pattern,
    whose numbered part allowed any letter suffix, and was counted as one more AHU. A letter suffix is accepted only
    when the family's own tags carry one.

Each positive case has a negative partner that passes before and after the patch. Generic invented tags only."""
from collections import Counter

import pytest

from bms.counts import _located_count, _Sheet
from bms.counts_text import family_pattern, fits, prefix_owners, searcher


def _sheet(n, labels):
    return _Sheet(("Invented.pdf", n), f"X-90{n}, Invented.pdf page {n}", f"X-90{n} whole sheet (picture)",
                  labels=Counter(labels))


def _count(pattern, *sheet_labels, groups=None):
    return _located_count([_sheet(i, l) for i, l in enumerate(sheet_labels, 1)], pattern, groups)


# ---- (a) one unit's tag on several sheets ------------------------------------------------------------------------

ZR = family_pattern(["ZR-7"], {"ZR": 1})
EF = family_pattern(["EF-3"], {"EF": 1})
VAV = family_pattern(["VAV-1", "VAV-2"], {"VAV": 1})


def test_a_riser_label_counted_per_sheet_collapses_to_one():
    assert _count(ZR, {"ZR-7": 1}, {"ZR-7": 1}, {"ZR-7": 1}) == 1


def test_the_same_tag_on_a_phase_plan_and_a_roof_plan_counts_once():
    assert _count(EF, {"EF-3": 1}, {"EF-3": 1}) == 1


def test_a_phase_2_plan_reusing_the_phase_1_tags_counts_each_unit_once():
    assert _count(VAV, {"VAV-1": 1, "VAV-2": 1}, {"VAV-1": 1, "VAV-2": 1}) == 2


def test_the_sheets_in_one_plan_group_still_count_once():          # negative: passes before and after
    groups = {("Invented.pdf", 1): ("g",), ("Invented.pdf", 2): ("g",)}
    assert _count(EF, {"EF-3": 1}, {"EF-3": 1}, groups=groups) == 1


def test_two_different_tags_on_two_sheets_still_count_two():       # negative
    assert _count(VAV, {"VAV-1": 1}, {"VAV-2": 1}) == 2


def test_two_distinct_instance_tags_on_one_sheet_still_count_two():  # negative
    assert _count(VAV, {"VAV-1": 1, "VAV-2": 1}) == 2


def test_a_type_tag_on_two_separate_plans_still_counts_per_plan():  # negative: a type is many units
    ebb = family_pattern(["EBB-A"], {"EBB": 1})
    assert _count(ebb, {"EBB-A": 1}, {"EBB-A": 1}) == 2


# ---- (b) a room named after its unit -----------------------------------------------------------------------------

OWNERS = prefix_owners([["AHU-1", "AHU-2", "AHU-9"]])
AHU = family_pattern(["AHU-1", "AHU-2", "AHU-9"], OWNERS)


def test_a_room_label_is_not_one_of_the_family_s_tags():
    assert not fits(AHU, "AHU-9X")
    assert not searcher(AHU).search("MECH RM AHU-9X")


def test_a_room_label_on_the_sheet_is_not_counted():
    assert _count(AHU, {"AHU-1": 1, "AHU-2": 1, "AHU-9": 1, "AHU-9X": 1}) == 3


def test_a_scheduled_unit_whose_tag_looks_like_a_room_label_still_counts():   # negative
    pattern = family_pattern(["AHU-9X", "AHU-9Y"], prefix_owners([["AHU-9X", "AHU-9Y"]]))
    assert fits(pattern, "AHU-9X") and fits(pattern, "AHU-9Y")
    assert _count(pattern, {"AHU-9X": 1, "AHU-9Y": 1}) == 2


@pytest.mark.parametrize("tag", ["AHU-1", "AHU-9", "AHU-4", "AHU 12"])
def test_numbered_tags_of_the_family_s_own_prefix_still_fit(tag):            # negative: an unscheduled AHU-4 counts
    assert fits(AHU, tag)
