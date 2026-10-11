"""The coverage gate reports ledger facts the written job never cites (invented fixtures only)."""
from estimator.ledger.facts import Ledger

from bms.coverage import coverage
from bms.model import (Clarification, Count, Device, Family, FrontEnd, Job, OtherCount, Ref, ScopeException, System)


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
    for extra in ({"questions": ("Is the ZZ-1 gizmo ours?",)},
                  {"exceptions": (ScopeException("", "ZZ-1 gizmos are by others"),)}):
        assert coverage(_job(**extra), _ledger()) == []
    system = _job().systems[0]
    system = System(**{**system.__dict__, "clarifications": (Clarification("note", "ZZ-1 is excluded"),)})
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


# ---- T-001 review fixes (the lead's 03bf985, re-done here) ------------------------------------------------------

def test_an_empty_value_prints_no_empty_brackets():
    for value in (None, ""):
        ledger = Ledger({"S1": "M-1"})
        ledger.add("device", "Odd sensor", value, "S1", "odd sensor shown", "plans")
        (finding,) = coverage(_job(), ledger)
        assert "(None)" not in finding.what and "()" not in finding.what
        assert "\u201cOdd sensor\u201d was read" in finding.what


def test_a_unit_whose_value_is_none_is_not_cited_by_the_word_none():
    ledger = Ledger({"S1": "M-1"})
    ledger.add("unit", "QX", None, "S1", "QX units", "schedules")
    ledger.add("unit", "None", None, "S1", "None units", "schedules")
    job = _job(questions=("None of the gizmos are shown.",))
    found = coverage(job, ledger)
    assert len(found) == 2 and all("(None)" not in f.what for f in found)


def test_the_count_refs_of_a_family_cite_its_fact():
    ledger = Ledger({"S1": "M-1"})
    ledger.add("family", "QF", "Gizmo", "S1", "QF gizmo count", "schedules")
    other = Ledger({"S1": "M-1"})
    other.add("family", "QG", "Gadget", "S1", "QG gadget count", "schedules")
    ref = _ref("QF gizmo count")
    for count in (Count(2, sources=(ref,)), Count(2, others=(OtherCount(3, ref),)),
                  Count(2, added_up=OtherCount(4, ref))):
        system = System("Q", "Gizmos", "shape", "field", (Family("Gizmo", (), count),),
                        devices=(_device((_ref("x"),)),))
        assert coverage(Job("j", systems=(system,)), ledger) == []
        assert len(coverage(Job("j", systems=(system,)), other)) == 1


def test_the_count_refs_of_a_line_cite_its_fact():
    ledger = Ledger({"S1": "M-1"})
    ledger.add("device", "Odd sensor", 3, "S1", "odd sensor qty 3", "plans")
    device = Device("Q.d1", "slot", "Sensor", "Furnish", "AME", "AME", "AME",
                    Count(3, sources=(_ref("odd sensor qty 3"),)), (_ref("x"),))
    system = System("Q", "Q", "shape", "field", (), devices=(device,))
    assert coverage(Job("j", systems=(system,)), ledger) == []


def test_a_tag_inside_a_longer_tag_is_not_a_citation():
    ledger = Ledger({"S1": "M-1"})
    ledger.add("unit", "EF", "EF-1", "S1", "Tags: EF-1", "seed")
    for words in ("EF-10 is by others", "EF-1A is by others", "XEF-1 is by others", "EF-1-2 is by others",
                  "EF-1.5 is by others"):
        assert len(coverage(_job(questions=(words,)), ledger)) == 1, words
    for words in ("EF-1 is by others", "Is ef-1 ours?", "(EF-1)", "EF-1."):
        assert coverage(_job(questions=(words,)), ledger) == [], words


# ---- T-001b: a family or unit fact is never cited by its bare prefix -------------------------------------------

def _vav_ledger():
    ledger = Ledger({"S1": "M-1", "S2": "M-2"})
    ledger.add("family", "VAV", "VAV box", "S1", "VAV (equipment): 3 schedule rows", "seed")
    ledger.add("unit", "VAV", "VAV-1 thru 3", "S1", "Tags: VAV-1 thru 3", "seed")
    return ledger


def _plain_job(**kw):
    return Job("j", systems=(System("Q", "Gizmos", "shape", "field", (), devices=(_device((_ref("x", "S2"),)),)),),
               **kw)


def test_the_bare_prefix_cites_no_family_or_unit_fact():
    for words in ("Are the VAV boxes ours?", "VAV", "vav controllers by others", "VAV-10 is by others"):
        found = coverage(_plain_job(questions=(words,)), _vav_ledger())
        assert len(found) == 2, words


def test_a_family_named_by_the_prefix_does_not_cite_it():
    system = System("VAV", "VAV Boxes", "shape", "field", (Family("VAV", (), Count(3)),),
                    devices=(_device((_ref("x", "S2"),)),))
    assert len(coverage(Job("j", systems=(system,)), _vav_ledger())) == 2


def test_one_of_its_own_tags_cites_a_family_and_a_unit_fact():
    for words in ("VAV-1 is by others", "Is VAV-3 ours?", "vav-2"):
        assert coverage(_plain_job(questions=(words,)), _vav_ledger()) == [], words


def test_a_range_in_the_fact_is_expanded():
    ledger = Ledger({"S1": "M-1"})
    ledger.add("unit", "EF", "EF-1 thru 3, EF-7 (roof)", "S1", "Tags: EF-1 thru 3, EF-7 (roof)", "seed")
    for words in ("EF-2 is by others", "EF-7 is by others"):
        assert coverage(_plain_job(questions=(words,)), ledger) == [], words
    for words in ("EF-4 is by others", "EF is by others", "roof fans"):
        assert len(coverage(_plain_job(questions=(words,)), ledger)) == 1, words


def test_a_range_in_the_job_is_expanded():
    ledger = Ledger({"S1": "M-1"})
    ledger.add("unit", "EF", "EF-2", "S1", "Tags: EF-2", "seed")
    system = System("EF", "Exhaust Fans", "shape", "field", (Family("Fan", ("EF-1 thru 3",), Count(3)),),
                    devices=(_device((_ref("x", "S1"),)),))
    assert coverage(Job("j", systems=(system,)), ledger) == []
    clarified = System("Q", "Q", "shape", "field", (), devices=(_device((_ref("x", "S1"),)),),
                       clarifications=(Clarification("note", "EF-1 thru 3 are by others"),))
    assert coverage(Job("j", systems=(clarified,)), ledger) == []
    beyond = System("Q", "Q", "shape", "field", (), devices=(_device((_ref("x", "S1"),)),),
                    clarifications=(Clarification("note", "EF-3 thru 5 are by others"),))
    assert len(coverage(Job("j", systems=(beyond,)), ledger)) == 1


def test_a_unit_value_that_is_only_the_prefix_gives_no_tag():
    ledger = Ledger({"S1": "M-1"})
    ledger.add("unit", "QV", "QV", "S1", "QV units", "schedules")
    assert len(coverage(_plain_job(questions=("QV units are ours",)), ledger)) == 1


def test_a_family_with_no_tags_is_cited_by_its_ref_only():
    ledger = Ledger({"S1": "M-1"})
    ledger.add("family", "QW", "Gizmo", "S1", "QW (equipment): 2 schedule rows", "seed")
    assert len(coverage(_plain_job(questions=("QW gizmos are ours",)), ledger)) == 1
    job = Job("j", systems=(System("Q", "Q", "shape", "field", (),
                                   devices=(_device((_ref("QW (equipment): 2 schedule rows"),)),)),))
    assert coverage(job, ledger) == []


def test_a_family_takes_the_tags_its_own_quote_names():
    ledger = Ledger({"S1": "M-1"})
    ledger.add("family", "QW", "Gizmo", "S1", "QW-4 gizmo shown, see QX-1", "plans")
    assert coverage(_plain_job(questions=("Is QW-4 ours?",)), ledger) == []
    assert len(coverage(_plain_job(questions=("Is QX-1 ours?",)), ledger)) == 1


def test_a_served_unit_tag_or_heater_cites_its_fact():
    ledger = Ledger({"S1": "M-1"})
    ledger.add("unit", "QH", "QH-1 thru 2", "S1", "Tags: QH-1 thru 2", "seed")
    from bms.model import Served
    for served in (Served("A", "A", ("QH-2",), (), "H", "H"), Served("A", "A", (), ("QH-1",), "H", "H")):
        system = System("H", "H", "shape", "field", (), devices=(_device((_ref("x"),)),), serves=(served,))
        assert coverage(Job("j", systems=(system,)), ledger) == []


def test_device_and_sequence_facts_still_cite_by_their_subject():
    ledger = Ledger({"S1": "M-1"})
    ledger.add("device", "Smoke detector", 2, "S1", "smoke det", "plans")
    assert coverage(_plain_job(questions=("Is the smoke detector ours?",)), ledger) == []
