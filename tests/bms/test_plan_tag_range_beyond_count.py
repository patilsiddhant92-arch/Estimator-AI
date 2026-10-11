"""HP 7: a family whose tags go beyond the count the schedule gives is never left at the lower count in silence. The
higher count prints (one per tag), the schedule's count stays in `Count.others` with its source, and the planner asks
one question that names both numbers and the extra tags. Two ways the extra tags reach the family: its own tag list is
longer than its count (the plans' range is in the list), or a later pass's list adds them ("EF-1 thru EF-5" where the
schedule lists "EF-1 thru EF-3"), in any wording of the range. Every ledger here is invented."""
from __future__ import annotations

import pytest

from bms.model import OtherCount, Ref
from bms.plan_read import expand

from test_plan import _family, _ledger, _plan

SCHEDULE = Ref("S3", "EF rows 3", "M-501, Drawings.pdf page 6")
FIVE = ("EF-1", "EF-2", "EF-3", "EF-4", "EF-5")


def _asked(job, tag):
    return [q for q in job.questions if tag in q]


# ---- the family's own tag list is longer than its count -------------------------------------------------------------

def test_a_tag_list_longer_than_the_schedules_count_prints_one_per_tag_and_keeps_the_count():
    ledger = _ledger()
    _family(ledger, "EF", "Exhaust Fan", "EF-1 thru EF-5", 3)
    (ef,) = _plan(ledger).systems
    (family,) = ef.families
    assert family.tags == FIVE
    assert family.count.value == 5 and family.count.highest() == 5
    assert family.count.sources == (Ref("S3", "Tags: EF-1 thru EF-5", "M-501, Drawings.pdf page 6"),)
    assert family.count.others == (OtherCount(3, SCHEDULE),)               # the schedule's count, with its source


def test_the_planner_asks_once_naming_both_numbers_and_the_extra_tags():
    ledger = _ledger()
    _family(ledger, "EF", "Exhaust Fan", "EF-1 thru EF-5", 3)
    job = _plan(ledger)
    [asked] = _asked(job, "EF-4")
    assert asked == ("Exhaust Fan (EF): M-501 lists 5 (EF-1 thru EF-5), but the count is 3 per M-501; EF-4, EF-5 are "
                     "beyond that count; counted 5 (the count gave 3), confirm the count.")


def test_one_tag_beyond_the_count_is_named_alone():
    ledger = _ledger()
    _family(ledger, "EF", "Exhaust Fan", "EF-1, EF-2, EF-3", 2)
    job = _plan(ledger)
    assert job.systems[0].families[0].count.value == 3
    [asked] = _asked(job, "EF-3")
    assert "EF-3 is beyond that count" in asked and "counted 3 (the count gave 2)" in asked


@pytest.mark.parametrize("tags, count", [("EF-1 thru 3", 3), ("EF-1 thru 3", 5), ("EF-1", 5)])
def test_a_count_that_covers_the_listed_tags_is_not_asked(tags, count):
    ledger = _ledger()
    _family(ledger, "EF", "Exhaust Fan", tags, count)
    job = _plan(ledger)
    assert job.systems[0].families[0].count.value == count and job.systems[0].families[0].count.others == ()
    assert job.questions == ()


def test_the_tags_of_a_type_family_name_kinds_not_units_so_they_do_not_raise_the_count():
    ledger = _ledger()
    _family(ledger, "CUH", "Cabinet Unit Heater", "CUH-A, CUH-B, CUH-C", 2)
    job = _plan(ledger)
    assert job.systems[0].families[0].count.value == 2
    assert not any("beyond that count" in q for q in job.questions)


def test_a_family_with_no_count_stays_unknown_and_is_not_given_one_per_tag():
    ledger = _ledger()
    _family(ledger, "EF", "Exhaust Fan", "EF-1 thru EF-5", None)
    count = _plan(ledger).systems[0].families[0].count
    assert count.value is None


def test_a_listed_tag_that_is_no_tag_is_not_a_unit():
    ledger = _ledger()
    _family(ledger, "EF", "Exhaust Fan", "EF-1, EF-2, roof fans", 2)
    job = _plan(ledger)
    assert job.systems[0].families[0].count.value == 2
    assert not any("beyond that count" in q for q in job.questions)


# ---- a later pass's list adds tags, in any wording of the range ------------------------------------------------------

@pytest.mark.parametrize("said", ["EF-1 thru EF-5", "EF-1 THRU 5", "EF-1 through EF-5", "EF-1 THROUGH 5",
                                  "EF-1 to EF-5", "EF-1 TO 5", "EF-1 - EF-5", "EF-1 – EF-5"])
def test_a_range_the_plans_show_beyond_the_schedule_adds_its_tags_in_any_wording(said):
    ledger = _ledger()
    _family(ledger, "EF", "Exhaust Fan", "EF-1 thru EF-3", 3)
    unit = ledger.find("unit", "EF")
    ledger.contradict(unit.id, said, "S2", f"{said} on the plans", "plans")
    job = _plan(ledger)
    (family,) = job.systems[0].families
    assert family.tags == FIVE
    assert family.count.value == 5
    assert family.count.others == (OtherCount(3, SCHEDULE),)
    [asked] = _asked(job, "EF-4")
    assert asked == ("Exhaust Fan (EF): M-501 lists 3 (EF-1 thru EF-3); EF-4, EF-5 are also on M-101; counted 5 "
                     "(the count gave 3), confirm the count.")


def test_a_range_that_is_not_one_numbered_series_is_not_read_as_a_range():
    ledger = _ledger()
    _family(ledger, "EF", "Exhaust Fan", "EF-1 thru EF-3", 3)
    unit = ledger.find("unit", "EF")
    ledger.contradict(unit.id, "EF-1 to VAV-9", "S2", "EF-1 to VAV-9", "plans")
    (family,) = _plan(ledger).systems[0].families
    assert "EF-9" not in family.tags and "EF-4" not in family.tags and family.count.value == 3


def test_a_list_beyond_the_count_that_a_later_pass_also_adds_to_is_asked_once():
    ledger = _ledger()
    _family(ledger, "EF", "Exhaust Fan", "EF-1 thru EF-5", 3)
    unit = ledger.find("unit", "EF")
    ledger.contradict(unit.id, "EF-1 thru EF-6", "S2", "EF-1 thru EF-6", "plans")
    job = _plan(ledger)
    (family,) = job.systems[0].families
    assert family.tags == (*FIVE, "EF-6") and family.count.value == 6
    assert family.count.others == (OtherCount(3, SCHEDULE),)
    [asked] = _asked(job, "EF-6")
    assert "lists 5 (EF-1 thru EF-5)" in asked and "counted 6 (the count gave 3)" in asked
    assert len([q for q in job.questions if "EF-4" in q or "EF-6" in q]) == 1


# ---- the range words, read as the Reader reads every tag list --------------------------------------------------------

@pytest.mark.parametrize("text, tags", [
    ("EF-1 through EF-3", ["EF-1", "EF-2", "EF-3"]),
    ("EF-1 to 3", ["EF-1", "EF-2", "EF-3"]),
    ("EF-1 - EF-3", ["EF-1", "EF-2", "EF-3"]),
    ("EF-1 to EF-2, EF-7", ["EF-1", "EF-2", "EF-7"]),
    ("VAV-4-1 to VAV-4-3", ["VAV-4-1", "VAV-4-2", "VAV-4-3"]),
    ("AHU-1 to VAV-3", ["AHU-1 to VAV-3"]),               # two prefixes are no one series: left as written
    ("EF-1 to roof", ["EF-1 to roof"]),                   # no end of a range: left as written
    ("VAV-3 - 4 PLACES", ["VAV-3 - 4 PLACES"]),           # a bare number after a dash is no high end
])
def test_expand_reads_through_to_and_a_spaced_dash_as_thru(text, tags):
    assert expand([text]) == tags
