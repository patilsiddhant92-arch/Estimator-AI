"""The coverage gate reports ledger facts the written job never cites (invented fixtures only)."""
from estimator.ledger.facts import Ledger

from bms.coverage import coverage
from bms.model import (Clarification, Count, Device, Family, FrontEnd, Job, Ref, ScopeException, System)


def _ledger():
    ledger = Ledger({"S1": "M-1, Plans.pdf page 2 (x)", "S2": "Spec 23 09 00"})
    ledger.add("family", "AHU", "Air handler", "S1", "AHU-1 and AHU-2 are scheduled", "seed")
    ledger.add("family", "ZZ", "Gizmo", "S1", "ZZ-1 gizmo shown", "seed")
    ledger.add("count", "AHU", 2, "S1", "AHU-1 and AHU-2 are scheduled", "schedules")
    return ledger


def _ref(quote="AHU-1 and AHU-2 are scheduled", sid="S1"):
    return Ref(sid, quote, "M-1")


def _device(refs):
    return Device("AHU.d1", "slot", "Supply fan status", "Furnish", "AME", "AME", "AME", Count(2), refs)


def _job(**kw):
    system = System("AHU", "Air Handlers", "shape", "field", (Family("Air handler", ("AHU-1", "AHU-2"), Count(2)),),
                    devices=(_device((_ref(),)),))
    return Job("j", systems=(system,), **kw)


def test_a_fact_the_job_cites_gives_no_finding():
    names = [f.what for f in coverage(_job(), _ledger())]
    assert len(names) == 1 and "ZZ" in names[0] and "AHU" not in names[0]


def test_an_uncited_fact_is_a_check_finding_with_place_and_fix():
    (finding,) = coverage(_job(), _ledger())
    assert (finding.rule, finding.severity, finding.system_key, finding.device_id) == ("coverage", "check", "", None)
    assert "M-1, Plans.pdf page 2" in finding.what and "ZZ-1 gizmo shown" in finding.what
    assert "not scope" in finding.fix


def test_a_question_an_exception_or_a_clarification_cites_it():
    for extra in ({"questions": ("Is the ZZ gizmo ours?",)},
                  {"exceptions": (ScopeException("", "ZZ gizmos are by others"),)}):
        assert coverage(_job(**extra), _ledger()) == []
    system = _job().systems[0]
    system = System(**{**system.__dict__, "clarifications": (Clarification("note", "ZZ is excluded"),)})
    assert coverage(Job("j", systems=(system,)), _ledger()) == []


def test_a_ref_with_the_same_source_and_quote_cites_it():
    ledger = Ledger({"S1": "M-1"})
    ledger.add("device", "Odd point", "yes", "S1", "ODD POINT ON PANEL", "details")
    job = Job("j", systems=(_job().systems[0].__class__(
        "X", "X", "s", "field", (), devices=(_device((_ref("odd point on panel"),)),)),))
    assert coverage(job, ledger) == []


def test_a_unit_is_cited_by_its_tag_in_the_value():
    ledger = Ledger({"S1": "M-1"})
    ledger.add("unit", "Unit one", "AHU-1", "S1", "AHU-1 row", "schedules")
    assert coverage(_job(), ledger) == []
    ledger.add("unit", "Unit two", "RTU-9", "S1", "RTU-9 row", "schedules")
    assert len(coverage(_job(), ledger)) == 1


def test_kinds_that_are_not_scope_are_ignored():
    ledger = Ledger({"S1": "M-1"})
    for kind in ("count", "location", "provider", "link", "group", "note"):
        ledger.add(kind, "QQ", "v", "S1", "QQ words", "plans")
    assert coverage(_job(), ledger) == []


def test_a_front_end_fact_is_cited_by_a_front_end_block_only():
    ledger = Ledger({"S1": "M-1"})
    ledger.add("front_end", "mode", "new-system", "S1", "new BMS head end", "spec")
    assert len(coverage(_job(), ledger)) == 1
    job = _job(front_end=FrontEnd("new-system", devices=(_device((_ref("x"),)),)))
    assert coverage(job, ledger) == []


def test_the_gate_never_changes_the_job():
    job = _job()
    before = job.to_json()
    coverage(job, _ledger(), None)
    assert job.to_json() == before
