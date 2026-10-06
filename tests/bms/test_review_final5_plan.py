"""REVIEW-FINAL5 (reviewer of record): the FINAL-G planner fixes (split roles, the condensate question) attacked.

Each strict xfail asserts the right behaviour and fails on e91dc46 by assertion. Remove a marker when its fix lands.
Invented ledgers only."""
from __future__ import annotations


from test_plan import SETTLED, _family, _ledger, _plan


def _match(ledger, section, prefix, sid):
    ledger.add("sequence_match", section, prefix, sid, section, "sequence", SETTLED)


def test_an_indoor_unit_with_an_outdoor_air_kit_is_still_indoor_and_never_pairs_with_indoor_units():
    """NORTH SPLITS: AC-1, AC-2 "Ductless Split Indoor Unit with Outdoor Air Kit". SOUTH SPLITS: SS-1, SS-2 "Wall
    Mounted Indoor Unit". No outdoor unit anywhere. `_split_role` tests the outdoor words before "indoor", so AC
    reads as outdoor, the sections join, and the question claims they pair as indoor and outdoor units (REVIEW-FINAL4
    F3 again)."""
    ledger = _ledger()
    _family(ledger, "AC", "Ductless Split Indoor Unit with Outdoor Air Kit", "AC-1, AC-2", 2)
    _family(ledger, "SS", "Wall Mounted Indoor Unit", "SS-1, SS-2", 2)
    _match(ledger, "NORTH SPLITS", "AC", "Q3")
    _match(ledger, "SOUTH SPLITS", "SS", "Q4")
    job = _plan(ledger)
    assert len(job.systems) == 2
    assert not any("pair up by tag number" in q for q in job.questions)


def test_guard_split_roles_fall_back_to_the_prefix_when_the_names_say_neither():
    """Both kinds named only "Split System": ACCU and OU read as outdoor by prefix, AC and IU as indoor, so each
    pair of sections joins and the join is asked."""
    for indoor, outdoor in (("AC", "ACCU"), ("IU", "OU")):
        ledger = _ledger()
        _family(ledger, indoor, "Split System", f"{indoor}-1, {indoor}-2", 2)
        _family(ledger, outdoor, "Split System", f"{outdoor}-1, {outdoor}-2", 2)
        _match(ledger, "NORTH SPLITS", indoor, "Q3")
        _match(ledger, "SOUTH SPLITS", outdoor, "Q4")
        job = _plan(ledger)
        assert len(job.systems) == 1
        assert any("pair up by tag number" in q for q in job.questions)
        assert sorted(f.count.value for f in job.systems[0].families) == [2, 2]


def _condensate_question(other_prefix: str, other_name: str) -> str:
    ledger = _ledger()
    _family(ledger, other_prefix, other_name, f"{other_prefix}-1, {other_prefix}-2", 2)
    _family(ledger, "AC", "Air Conditioning Unit", "AC-1, AC-2", 2)
    _family(ledger, "ACCU", "Air Cooled Condensing Unit", "ACCU-1, ACCU-2", 2)
    _family(ledger, "CP", "Condensate Pump", "CP-1, CP-2", 2)
    (asked,) = [q for q in _plan(ledger).questions if "CP-1" in q]
    return asked


def test_the_condensate_question_never_names_a_rooftop_exhaust_fan():
    assert "Rooftop Exhaust Fan" not in _condensate_question("REF", "Rooftop Exhaust Fan")


def test_the_condensate_question_never_names_a_heat_recovery_chiller():
    assert "Heat Recovery Chiller" not in _condensate_question("HRC", "Heat Recovery Chiller")


def test_guard_the_condensate_question_falls_back_when_nothing_else_makes_condensate():
    asked = _condensate_question("B", "Condensing Boiler")
    assert "If they serve other equipment, they belong with that equipment instead." in asked
