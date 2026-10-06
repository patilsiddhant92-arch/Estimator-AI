"""FINAL-I: the planner's split roles read the kind's own head noun (REVIEW-FINAL5 F5), and the condensate question
names only equipment that makes condensate (F6). Every test here fails on rebuild 36b6d5c by assertion. Invented
ledgers only."""
from __future__ import annotations

from test_plan import SETTLED, _family, _ledger, _plan


def _match(ledger, section, prefix, sid):
    ledger.add("sequence_match", section, prefix, sid, section, "sequence", SETTLED)


def test_a_condenser_water_connection_never_makes_an_indoor_unit_outdoor():
    """WSHP-style indoor units "with Condenser Water Connection" and wall indoor units, no outdoor unit anywhere:
    "Condenser" after "with" is not the kind's head noun, so both are indoor, two systems, no pairing question."""
    ledger = _ledger()
    _family(ledger, "AC", "Water Source Indoor Unit with Condenser Water Connection", "AC-1, AC-2", 2)
    _family(ledger, "SS", "Wall Mounted Indoor Unit", "SS-1, SS-2", 2)
    _match(ledger, "NORTH SPLITS", "AC", "Q3")
    _match(ledger, "SOUTH SPLITS", "SS", "Q4")
    job = _plan(ledger)
    assert len(job.systems) == 2
    assert not any("pair up by tag number" in q for q in job.questions)


def _condensate_question(other_prefix: str, other_name: str) -> str:
    ledger = _ledger()
    _family(ledger, other_prefix, other_name, f"{other_prefix}-1, {other_prefix}-2", 2)
    _family(ledger, "AC", "Air Conditioning Unit", "AC-1, AC-2", 2)
    _family(ledger, "ACCU", "Air Cooled Condensing Unit", "ACCU-1, ACCU-2", 2)
    _family(ledger, "CP", "Condensate Pump", "CP-1, CP-2", 2)
    (asked,) = [q for q in _plan(ledger).questions if "CP-1" in q]
    return asked


def test_the_condensate_question_names_a_dehumidifier():
    """A dehumidifier drains condensate: the question names it as the other equipment the pumps may serve."""
    assert "Dehumidifier" in _condensate_question("DH", "Dehumidifier")


def test_the_condensate_question_never_names_a_rooftop_relief_fan_or_a_heat_recovery_coil_loop():
    for prefix, name in (("RRF", "Rooftop Relief Fan"), ("HRL", "Heat Recovery Coil Loop Pump")):
        assert name not in _condensate_question(prefix, name)
