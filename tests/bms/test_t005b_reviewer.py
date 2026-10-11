"""Reviewer of record tests for T-005b (2026-10-11). Invented data only."""
from __future__ import annotations

from pathlib import Path

from estimator.ledger.facts import SETTLED, Ledger
from estimator.writing.dossier import Dossier

from bms import review
from bms.model import Count, Device, Family, FrontEnd, Job, OtherCount, Ref, System
from bms.plan import one_count_question_per_family, plan_job
from bms.playbook import load_playbook

PLAYBOOK = load_playbook(Path(__file__).parent / "fixtures" / "sample_playbook")
SCHED = Ref("S1", "FAN rows 18", "M-801, Invented.pdf page 3")
PLANS = Ref("C1", "plan placements 20", "M-201, Invented.pdf page 1")
SOURCES = {"S1": "M-801, Invented.pdf page 3 (schedule)", "S2": "M-201, Invented.pdf page 1 (sheet text)",
           "S3": "23 09 00, Invented Specs.pdf page 2"}


def _family_count() -> Count:
    return Count(20, (PLANS,), (OtherCount(18, SCHED),))


def test_twenty_lines_and_one_family_count_question_give_one_card(tmp_path):
    tags = tuple(f"RF-{i}" for i in range(1, 21))
    devices = tuple(Device(id=f"RF.d{i}", slot="other_device", name=f"Invented Point {i}", verb="Furnish and Install",
                           furnished_by="AME", installed_by="AME", wired_by="AME", quantity=_family_count(),
                           refs=(PLANS,), flag="quantity") for i in range(1, 21))
    system = System(key="RF", name="Return Fan", shape="Air Handling Unit", control="field",
                    families=(Family("Return Fan", tags, _family_count()),), devices=devices)
    question = "Return Fan (RF): M-801 lists 18 (RF-1 thru 18); counted 20, confirm the count."
    asked = one_count_question_per_family([question, question, question.replace("20", "20 per M-201")])
    assert len(asked) == 1
    job = Job(name="Invented", systems=(system,), front_end=FrontEnd(mode="new-system"), questions=tuple(asked))
    cards = review._questions(job, ())
    assert [(c.level, c.family_name) for c in cards] == [("family", "Return Fan")]
    page = review.review_page(job, (), tmp_path).read_text(encoding="utf-8")
    assert page.count('class="qtitle"') == 1


def _ledger() -> Ledger:
    ledger = Ledger(SOURCES)
    ledger.job_name = "Invented Job"
    ledger.add("front_end", "mode", "new-system", "S3", "provide a new building automation system", "spec", SETTLED)
    ledger.add("family", "AHU", "Air Handling Unit", "S1", "AHU Air Handling Unit", "schedules", SETTLED)
    ledger.add("unit", "AHU", "AHU-7 thru 8", "S1", "Tags: AHU-7 thru 8", "schedules", SETTLED)
    ledger.add("count", "AHU", 2, "S1", "AHU rows 2", "schedules", SETTLED)
    ledger.add("family", "EF", "Exhaust Fan", "S1", "EF Exhaust Fan", "schedules", SETTLED)
    ledger.add("unit", "EF", "EF-3", "S1", "Tags: EF-3", "schedules", SETTLED)
    ledger.add("count", "EF", 1, "S1", "EF rows 1", "schedules", SETTLED)
    ledger.add("family", "CV", "Control Valve", "S1", "CV Control Valve", "schedules", SETTLED)
    ledger.add("unit", "CV", "CV-21 thru 24", "S1", "Tags: CV-21 thru 24", "schedules", SETTLED)
    ledger.add("count", "CV", 4, "S1", "CV rows 4", "schedules", SETTLED)
    for valve, unit in (("CV-21", "AHU-7"), ("CV-22", "AHU-7"), ("CV-23", "AHU-8"), ("CV-24", "AHU-8")):
        ledger.add("link", valve, unit, "S2", f"{valve} AT {unit} COIL", "plans", SETTLED)
    return ledger


def _plan(ledger: Ledger) -> Job:
    dossier = Dossier(job_name="Invented Job", text="", images=(), sources={}, families=(), device_totals={},
                      counts={}, stats={})
    return plan_job(ledger, None, dossier, PLAYBOOK)


def test_valves_linked_to_air_handlers_print_inside_the_air_handler_system():
    job = _plan(_ledger())
    keys = [s.key for s in job.systems]
    assert "CV" not in keys
    ahu = next(s for s in job.systems if "AHU-7" in [t for f in s.families for t in f.tags])
    valves = [f for f in ahu.families if f.name == "Control Valve"]
    assert len(valves) == 1 and valves[0].tags == ("CV-21", "CV-22", "CV-23", "CV-24")
    assert valves[0].count.value == 4
    assert not any("CV-2" in q for q in job.questions)


def _valve_counts(job: Job) -> list[tuple[int | None, tuple[int, ...]]]:
    return [(f.count.value, tuple(o.value for o in f.count.others)) for s in job.systems for f in s.families
            if f.name == "Control Valve"]


def _valve_questions(job: Job) -> list[str]:
    return [q for q in job.questions if q.startswith("Control Valve (CV):")]


def test_a_higher_valve_count_is_kept_when_the_valves_move_and_one_question_names_both_numbers():
    """The valve family has 4 tags and a higher count (6) from another source: the 6 prints (a too-low count is the
    worst error), and one question names both numbers."""
    ledger = _ledger()
    ledger.add("count", "CV", 6, "S2", "CV placements 6", "plans", SETTLED)
    job = _plan(ledger)
    assert "CV" not in [s.key for s in job.systems]
    assert [max((v or 0, *others)) for v, others in _valve_counts(job)] == [6]
    (asked,) = _valve_questions(job)
    assert "6" in asked and "4" in asked and asked.endswith("confirm the count.")


def test_a_lower_valve_count_is_named_in_one_question_when_the_valves_move():
    """The valve family has 4 tags and a lower count (3) from another source: 4 prints under the unit, and the 3 is
    not lost: one question names both numbers."""
    ledger = _ledger()
    ledger.add("count", "CV", 3, "S2", "CV placements 3", "plans", SETTLED)
    job = _plan(ledger)
    assert [v for v, _ in _valve_counts(job)] == [4]
    (asked,) = _valve_questions(job)
    assert "4" in asked and "3 per M-201" in asked and asked.endswith("confirm the count.")

