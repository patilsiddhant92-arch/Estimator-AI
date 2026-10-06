"""REVIEW-FINAL4 (reviewer of record): attacks on FINAL-D's planner changes (rebuild a3e1b1f). Invented ledgers only.

A strict xfail is a finding: it asserts the right behaviour and fails on a3e1b1f by assertion. The rest are guards.
"""
from __future__ import annotations

from test_plan import SETTLED, _family, _ledger, _plan


def _match(ledger, section, prefix, sid):
    ledger.add("sequence_match", section, prefix, sid, section, "sequence", SETTLED)


def test_two_indoor_only_split_sections_numbered_from_one_stay_two_blocks():
    """NORTH SPLITS holds indoor units AC-1, AC-2; SOUTH SPLITS holds indoor units SS-1, SS-2. No outdoor unit
    anywhere: nothing pairs as an indoor unit with its outdoor unit, so these are two systems."""
    ledger = _ledger()
    _family(ledger, "AC", "Ductless Split Indoor Unit", "AC-1, AC-2", 2)
    _family(ledger, "SS", "Ductless Split Indoor Unit", "SS-1, SS-2", 2)
    _match(ledger, "NORTH SPLITS", "AC", "Q3")
    _match(ledger, "SOUTH SPLITS", "SS", "Q4")
    job = _plan(ledger)
    assert len(job.systems) == 2
    assert not any("each indoor unit with the outdoor unit of its number" in q for q in job.questions)


def test_the_condensate_pump_question_never_names_a_cooling_tower():
    ledger = _ledger()
    _family(ledger, "CT", "Cooling Tower", "CT-1, CT-2", 2)
    _family(ledger, "AC", "Air Conditioning Unit", "AC-1, AC-2", 2)
    _family(ledger, "ACCU", "Air Cooled Condensing Unit", "ACCU-1, ACCU-2", 2)
    _family(ledger, "CP", "Condensate Pump", "CP-1, CP-2", 2)
    (asked,) = [q for q in _plan(ledger).questions if "CP-1" in q]
    assert "Cooling Tower" not in asked


# ---- guards (pass on a3e1b1f) ----------------------------------------------------------------------------------

def test_indoor_and_outdoor_sections_numbered_from_one_join_and_are_asked():
    ledger = _ledger()
    _family(ledger, "AC", "Air Conditioning Unit", "AC-1, AC-2, AC-3", 3)
    _family(ledger, "ACCU", "Air Cooled Condensing Unit", "ACCU-1, ACCU-2, ACCU-3", 3)
    _match(ledger, "NORTH SPLITS", "AC", "Q3")
    _match(ledger, "SOUTH SPLITS", "ACCU", "Q4")
    job = _plan(ledger)
    (split,) = job.systems
    assert sorted(t for f in split.families for t in f.tags) == ["AC-1", "AC-2", "AC-3", "ACCU-1", "ACCU-2", "ACCU-3"]
    assert any("pair up by tag number" in q and "Confirm" in q for q in job.questions)


def test_an_air_handler_in_its_own_section_never_joins_a_condensing_unit_of_its_number():
    ledger = _ledger()
    _family(ledger, "AHU", "Air Handling Unit", "AHU-1", 1)
    _family(ledger, "ACCU", "Air Cooled Condensing Unit", "ACCU-1", 1)
    _family(ledger, "AC", "Air Conditioning Unit", "AC-1", 1)
    _match(ledger, "AIR HANDLING UNITS", "AHU", "Q1")
    _match(ledger, "NORTH SPLITS", "ACCU", "Q3")
    _match(ledger, "NORTH SPLITS", "AC", "Q3")
    systems = {s.key: s for s in _plan(ledger).systems}
    assert [f.tags for f in systems["AHU"].families] == [("AHU-1",)]
    assert [r.source_id for r in systems["AHU"].sequence_refs] == ["Q1"]


def test_families_of_one_name_in_one_sequence_section_still_merge_and_are_asked():
    ledger = _ledger()
    _family(ledger, "EF", "Exhaust Fan", "EF-1", 1)
    _family(ledger, "KEF", "Exhaust Fan", "KEF-1", 1)
    _match(ledger, "EXHAUST FANS", "EF", "Q1")
    _match(ledger, "EXHAUST FANS", "KEF", "Q1")
    job = _plan(ledger)
    (ef,) = job.systems
    assert [f.tags for f in ef.families] == [("EF-1",), ("KEF-1",)]          # each keeps its own tags and count
    assert any("same name" in q and "confirm" in q for q in job.questions)
