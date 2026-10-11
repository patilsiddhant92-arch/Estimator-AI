"""Reviewer's acceptance tests for hark/T-007 core (Tasks 2.1-2.3). Invented fixture only. Not committed."""
import dataclasses

import pytest

import takeoff_fixture as fx
import test_takeoff as tt
from bms import takeoff
from bms.model import Unit
from bms.plan import plan_job


def _fams(job):
    return {f.name: f for s in job.systems for f in s.families}


def _family_questions(job, prefix, name):
    return [q for q in job.questions if q.startswith(f"How many {prefix} units?") or q.startswith(f"{name} ({prefix})")]


def test_acceptance_register_prints_new_work_counts():
    job = tt._plan_registered()
    f = _fams(job)
    assert [f[n].count.value for n in ("Air Handling Unit", "Exhaust Fan", "Energy Recovery Unit", "Fan Coil Unit")] \
        == [5, 5, 1, 55]


def test_acceptance_ahu_header_is_ahu_1_thru_5_and_ahu_6_out():
    job = tt._plan_registered()
    assert _fams(job)["Air Handling Unit"].tags == tuple(f"AHU-{n}" for n in range(1, 6))
    assert not [t for s in job.systems for fm in s.families for t in fm.tags if t == "AHU-6"]


def test_acceptance_higher_code_counts_set_aside_both_numbers_one_question_each():
    ledger = tt._ledger_with_placements(AHU=(21, "M-401 5; M-402 5; M-403 3; M-404 3; MD-401 5"),
                                        EF=(16, "M-401 5; M-403 3; M-404 3; MD-401 5"),
                                        ERU=(3, "M-401 1; M-402 1; M-404 1"))
    job = tt._plan_registered(ledger)
    aside = {(a.family, a.value): a for a in job.set_aside}
    assert {("AHU", 21), ("EF", 16), ("ERU", 3)} <= set(aside)
    for (fam, n), a in aside.items():
        assert str(n) in a.note and a.ref.source_id            # both numbers and a source
    for prefix, name in (("AHU", "Air Handling Unit"), ("EF", "Exhaust Fan"), ("ERU", "Energy Recovery Unit")):
        assert len(_family_questions(job, prefix, name)) == 1, job.questions


@pytest.mark.xfail(strict=True, reason="deferred follow-up (review S2): the set-aside reason comes from today's code count")
def test_acceptance_demolition_part_of_dropped_count_is_named():
    """The dropped 21 includes MD-401's 5 (a demolition sheet). Expect the set-aside to name the demolition sheet."""
    ledger = tt._ledger_with_placements(AHU=(21, "M-401 5; M-402 5; M-403 3; M-404 3; MD-401 5"))
    job = tt._plan_registered(ledger)
    reasons = {a.reason for a in job.set_aside if a.family == "AHU"}
    assert "demolition sheet" in reasons, reasons


def test_acceptance_ahu_5_demolish_prints_4_one_question():
    register, problems = tt._check(tt._answer_with(AHU_5="demolish"))
    assert problems == []
    job = tt._plan_registered(register=register)
    assert _fams(job)["Air Handling Unit"].count.value == 4
    assert [a.value for a in job.set_aside if a.family == "AHU"] == [5]
    assert len(_family_questions(job, "AHU", "Air Handling Unit")) == 1, job.questions


def test_no_register_equals_plan_without_keyword():
    a = plan_job(fx.ledger(), fx.catalogue(), fx.dossier(), tt.PLAYBOOK)
    b = plan_job(fx.ledger(), fx.catalogue(), fx.dossier(), tt.PLAYBOOK, register=None, typicals=())
    assert a == b


# ---- adversarial: counts must not drop in the block moves ----

def _pump_ledger(count):
    data = tt._extended_ledger().to_dict()
    for fact in data["facts"]:
        if fact["kind"] == "count" and fact["subject"] == "P":
            fact["value"] = count
            fact["quote"] = f"P (Pump): schedule rows {count}"
    from estimator.ledger.facts import Ledger
    return Ledger.from_dict(data)


def _pump_total(job):
    return sum(f.count.value or 0 for s in job.systems for f in s.families if any(t.startswith("P-") for t in f.tags))


def test_pump_count_above_tags_survives_the_plant_move_and_split():
    """The schedule says 6 pumps for P-1 thru 4 (invented); the register's units add up to 4. 6 prints (no split, T-005b's
    guard), the 4 is set aside with both numbers, and one question asks about the pumps."""
    job = plan_job(_pump_ledger(6), fx.catalogue(), fx.dossier(), tt.PLAYBOOK, register=tt._extended_register())
    assert _pump_total(job) == 6
    aside = [a for a in job.set_aside if a.family == "P"]
    assert [a.value for a in aside] == [4] and "6" in aside[0].note and "4" in aside[0].note
    asked = [q for q in job.questions if q.startswith("Pump (P):")]
    assert len(asked) == 1 and "6" in asked[0] and "4" in asked[0], job.questions


def test_a_plant_move_never_lowers_a_count():
    """No services in the register (invented): only the plant pumps move. A schedule of 6 for 4 tags keeps 6."""
    changes = {f"P_{n}": {"service": ""} for n in range(1, 5)}
    job = plan_job(_pump_ledger(6), fx.catalogue(), fx.dossier(), tt.PLAYBOOK,
                   register=tt._extended_register(**changes))
    assert _pump_total(job) == 6
    assert [a.value for a in job.set_aside if a.family == "P"] == [4]
    assert len([q for q in job.questions if q.startswith("Pump (P):")]) == 1


def test_the_plant_move_counts_each_unit_by_its_register_count():
    changes = {f"P_{n}": {"service": ""} for n in range(1, 5)}
    changes["P_3"] = {"service": "", "count": 2}
    job = plan_job(_pump_ledger(5), fx.catalogue(), fx.dossier(), tt.PLAYBOOK,
                   register=tt._extended_register(**changes))
    boiler = next(s for s in job.systems if s.key == "B")
    assert [(f.tags, f.count.value) for f in boiler.families][1] == (("P-3", "P-4"), 3)
    assert _pump_total(job) == 5 and not [a for a in job.set_aside if a.family == "P"]


def test_type_tag_pump_with_quantity_two_keeps_two_after_split():
    """P-1 is one tag with two pumps (register count 2, duty/standby, invented)."""
    register = tt._extended_register(P_1={"count": 2})
    job = plan_job(_pump_ledger(5), fx.catalogue(), fx.dossier(), tt.PLAYBOOK, register=register)
    chilled = next(s for s in job.systems if s.name == "Chilled Water Pump")
    assert chilled.families[0].count.value == 2
    assert _pump_total(job) == 5 and not [a for a in job.set_aside if a.family == "P"]


def test_split_by_service_splits_only_pumps():
    """Valves that serve no unit but carry two services (invented) are not pumps: the task's decision splits pumps."""
    ch = {f"CV_{n}": {"serves": "", "service": "chilled water" if n < 3 else "hot water"} for n in range(1, 6)}
    job = plan_job(tt._extended_ledger(), fx.catalogue(), fx.dossier(), tt.PLAYBOOK,
                   register=tt._extended_register(**ch))
    names = [s.name for s in job.systems]
    assert "Chilled Water Control Valve" not in names and "Hot Water Control Valve" not in names, names
    valves = [f for s in job.systems for f in s.families if f.name == "Control Valve"]
    assert [(f.tags, f.count.value) for f in valves] == [(tuple(f"CV-{n}" for n in range(1, 6)), 5)]


def test_valves_that_serve_air_handlers_in_two_blocks_go_under_each():
    """The register's serves ties each valve to its unit (link_valves, T-005b), even across two blocks (invented)."""
    register = tt._extended_register(CV_1={"serves": "ERU-1"})
    job = plan_job(tt._extended_ledger(), fx.catalogue(), fx.dossier(), tt.PLAYBOOK, register=register)
    fams = {(s.name, f.name): f for s in job.systems for f in s.families}
    assert fams[("Energy Recovery Unit", "Control Valve")].tags == ("CV-1",)
    assert fams[("Air Handling Unit", "Control Valve")].tags == tuple(f"CV-{n}" for n in range(2, 6))
    assert not [s for s in job.systems if s.key == "CV"]
