"""Fix run 2026-10-10, row 16 (HarkPro 203, ruling L2): the highest count prints (the schedule's count does not take
its place), so the validator asks for a count whose `value` is the highest and keeps every other count in `others`,
where the proposal's note names it with its place. The finding says the numbers it is about and what prints.
Invented data only: the sample fixtures."""
from __future__ import annotations

import dataclasses as dc
import itertools
import json
from pathlib import Path

import pytest

from bms.model import Count, Family, Job, OtherCount, Ref
from bms.playbook import load_playbook
from bms.validate import RULE, _count_problems, validate

FIX = Path(__file__).resolve().parent / "fixtures"
PB = load_playbook(FIX / "sample_playbook")
PLAN = Ref("S1", "located on the sheet text", "M-101, Invented Set.pdf page 2")
SCHEDULE = Ref("S2", "quantity column total 4", "M-601, Invented Set.pdf page 9")


@pytest.fixture
def job() -> Job:
    return Job.from_dict(json.loads((FIX / "sample_job.json").read_text(encoding="utf-8")))


def edit(job: Job, key: str, **changes) -> Job:
    return job.with_system(dc.replace(job.system(key), **changes))


def higher(job: Job):
    return [f for f in validate(job, PB) if f.rule == RULE["higher"]]


def test_a_count_that_is_the_highest_is_clean_whatever_other_counts_it_names(job):
    family = Family("Exhaust Fan", ("EF-1", "EF-2"), Count(6, (PLAN,), (OtherCount(4, SCHEDULE), OtherCount(2, PLAN))))
    assert higher(edit(job, "EF", families=(family,))) == []


def test_a_value_below_another_count_is_must_fix_and_names_both_numbers_and_what_prints(job):
    family = Family("Exhaust Fan", ("EF-1", "EF-2"), Count(4, (SCHEDULE,), (OtherCount(6, PLAN),)))
    (found,) = higher(edit(job, "EF", families=(family,)))
    assert (found.system_key, found.device_id, found.severity) == ("EF", None, "must_fix")
    assert found.what == ("The Exhaust Fan count carries 4, but another source gives 6. "
                          "The proposal prints 6, the highest.")
    assert found.fix == "Set the count to 6, the highest, with its source. Keep 4 as another count, with its source."


def test_a_value_below_another_count_with_no_source_is_the_same_finding(job):
    family = Family("Exhaust Fan", ("EF-1", "EF-2"), Count(4, (), (OtherCount(6, PLAN),)))
    (found,) = higher(edit(job, "EF", families=(family,)))
    assert found.severity == "must_fix" and "carries 4" in found.what and "gives 6" in found.what


def test_a_device_quantity_below_another_count_is_must_fix_on_that_line(job):
    system = job.system("EF")
    line = dc.replace(system.devices[1], quantity=Count(2, (), (OtherCount(3, PLAN),)))
    edited = edit(job, "EF", devices=(system.devices[0], line, *system.devices[2:]))
    (found,) = higher(edited)
    assert (found.system_key, found.device_id, found.severity) == ("EF", "EF.d2", "must_fix")
    assert found.what == ("Fan Start / Stop and Status carries 2, but another source gives 3. "
                          "The proposal prints 3, the highest.")


def test_an_unknown_count_with_a_known_other_names_the_highest_and_what_prints(job):
    family = Family("Exhaust Fan", ("EF-1",), Count(None, (), (OtherCount(5, PLAN), OtherCount(3, SCHEDULE))))
    (found,) = higher(edit(job, "EF", families=(family,)))
    assert found.severity == "must_fix"
    assert found.what == ("The Exhaust Fan count carries no number, but a source gives 5. "
                          "The proposal prints 5, the highest.")
    assert found.fix == "Set the count to 5, the highest, with its source. Keep every other count with its source."


def test_no_count_at_all_is_not_this_rules_finding(job):
    family = Family("Exhaust Fan", ("EF-1",), Count(None))
    assert higher(edit(job, "EF", families=(family,))) == []


def _every_count():
    values = (None, 0, 3, 5)
    others = [()] + [((v, r),) for v in (0, 2, 3, 5, 7) for r in (PLAN, SCHEDULE)]
    others += [((a, PLAN), (b, SCHEDULE)) for a, b in itertools.product((2, 5, 7), repeat=2)]
    for value in values:
        for sources in ((), (PLAN,)):
            if value is None and sources:
                continue
            for extra in others:
                yield Count(value, sources, tuple(OtherCount(v, r) for v, r in extra))


def test_the_validator_asks_for_exactly_the_counts_whose_value_is_not_the_highest():
    """A count whose `value` is the highest needs nothing: the note names the others. Any other count is a
    must_fix, so the number that prints always has a count that says it."""
    checked = 0
    for count in _every_count():
        top = count.highest()
        wrong = top is not None and (count.value is None or count.value < top)
        assert bool(list(_count_problems(count, "The count"))) == wrong, count
        checked += 1
    assert checked > 100
