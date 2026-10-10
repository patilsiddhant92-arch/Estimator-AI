"""RUN-11 under the estimator's count ruling (2026-10-09): the revise may correct a family count only with cited
evidence and consistent with the schedule basis. A count the schedule gave stays the schedule's (a corrected
schedule reading, never a plan DISCREPANCY made the working count); a count no schedule gave may become the
schedule's by citing it, the plan figure then kept as a DISCREPANCY flag. The corrected count's basis and printed
count agree, on the family, its lines and the check card. Every job here is invented."""
from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from test_core_run_fixes import (COUNT_FINDING, PB, R_PLACED, R_ROWS, VEVIDENCE, Rewrites, _corrected,  # noqa: E402
                                 _planned, job_of)

from bms import ai, run  # noqa: E402
from bms.model import Count, Finding, OtherCount, Ref, System  # noqa: E402
from bms.render import render  # noqa: E402
from bms.validate import RULE, validate  # noqa: E402

R_MISREAD = Ref("S3", "EXHAUST FAN SCHEDULE (ADD ALTERNATE) EF-1 EF-2", "M-3")


def _answer(system: System, count: Count) -> System:
    answer = _corrected(system, value=count.value, sources=count.sources, others=count.others)
    answer["families"][0]["count"] = count.to_dict()
    return System.from_dict(answer)


def _scheduled(value=3) -> System:
    """As the planner left it with a schedule count (basis "schedule") misread as `value`, the plans' 4 beside it."""
    system = _planned()
    count = Count(value, (R_MISREAD,), (OtherCount(4, R_PLACED),), "schedule")
    return dataclasses.replace(system, families=(dataclasses.replace(system.families[0], count=count),),
                               devices=(dataclasses.replace(system.devices[0], quantity=count),))


def test_a_count_no_schedule_gave_becomes_the_schedules_and_keeps_the_plan_figure_as_a_discrepancy():
    system = _planned()                                             # 4 from the plans, basis "highest"
    answer = _answer(system, Count(2, (R_ROWS,), (OtherCount(4, R_PLACED),), "schedule"))
    revised = run._revised(system, [COUNT_FINDING], VEVIDENCE, PB, Rewrites(answer))
    count = revised.families[0].count
    assert (count.value, count.basis, count.printed(), count.flag()) == (2, "schedule", 2, "DISCREPANCY")
    assert [o.value for o in count.others] == [4]                   # the plan figure is never dropped silently
    assert revised.devices[0].quantity.basis == "schedule" and revised.devices[0].quantity.printed() == 2
    j = job_of(revised)
    assert [f for f in validate(j, PB) if f.severity == "must_fix"] == []
    assert render(j, PB).scope.blocks[0].header.startswith("Qty (2)")
    cards = run.revise_corrections(system, revised, [COUNT_FINDING], VEVIDENCE)
    assert len(cards) == 1 and "from 4 to 2" in cards[0].what and "the schedule's count" in cards[0].what


def test_a_schedule_count_is_never_turned_into_the_highest():
    system = _scheduled()
    answer = _answer(system, Count(4, (R_PLACED,), (), "highest"))
    with pytest.raises(ai.NoAnswer) as refused:
        ai.revise_system(system, [COUNT_FINDING], VEVIDENCE, PB, Rewrites(answer))
    assert "working count" in str(refused.value.reason)


def test_a_plan_discrepancy_is_never_made_the_schedules_count():
    system = _scheduled()
    answer = _answer(system, Count(4, (R_PLACED,), (OtherCount(3, R_MISREAD),), "schedule"))
    with pytest.raises(ai.NoAnswer) as refused:
        ai.revise_system(system, [COUNT_FINDING], VEVIDENCE, PB, Rewrites(answer))
    assert "DISCREPANCY" in str(refused.value.reason)


def test_a_misread_schedule_count_is_corrected_and_the_higher_plan_count_stays_beside_it():
    system = _scheduled(3)
    answer = _answer(system, Count(2, (R_ROWS,), (OtherCount(4, R_PLACED), OtherCount(3, R_MISREAD)), "schedule"))
    revised = ai.revise_system(system, [COUNT_FINDING], VEVIDENCE, PB, Rewrites(answer))
    count = revised.families[0].count
    assert (count.value, count.basis, count.printed()) == (2, "schedule", 2)
    assert [o.value for o in count.others] == [4]                   # the misread 3 goes, the plans' 4 stays a flag


def test_an_answer_that_leaves_the_basis_out_keeps_the_skeletons():
    system = _scheduled(3)
    answer = _answer(system, Count(2, (R_ROWS,), (OtherCount(4, R_PLACED),), "schedule"))
    writer = Rewrites(answer)
    del writer.answer["families"][0]["count"]["basis"]           # an answer written before the basis field
    revised = ai.revise_system(system, [COUNT_FINDING], VEVIDENCE, PB, writer)
    assert revised.families[0].count.basis == "schedule" and revised.families[0].count.value == 2


def test_a_finding_under_the_old_or_new_count_rule_names_opens_the_count():
    for rule in (RULE["higher"], RULE["unknown"], "Higher count prints", "Never undershoot"):
        finding = Finding(rule, "EF", None, "must_fix", "the count is wrong", "Check it.")
        assert ai._revisions([finding]) == {"count"}
