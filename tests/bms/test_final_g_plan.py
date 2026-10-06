"""FINAL-G: REVIEW-FINAL4's planner findings F3 (a split join needs an indoor unit and an outdoor unit), F4 (the
condensate pump question names only equipment that drains condensate) and F5 (a no-kind code already one of its
owner's tags still says where the owner's count came from). Invented ledgers only."""
from __future__ import annotations

from test_plan import SETTLED, _family, _ledger, _plan


def _match(ledger, section, prefix, sid):
    ledger.add("sequence_match", section, prefix, sid, section, "sequence", SETTLED)


def test_an_indoor_section_and_another_indoor_section_never_pair_even_with_an_outdoor_unit_elsewhere():
    """NORTH SPLITS: indoor units AC-1, AC-2. SOUTH SPLITS: indoor units SS-1, SS-2. A third section holds
    condensing units CU-5, CU-6 whose numbers pair with neither. The two indoor sections are two systems."""
    ledger = _ledger()
    _family(ledger, "AC", "Ductless Split Indoor Unit", "AC-1, AC-2", 2)
    _family(ledger, "SS", "Wall Mounted Indoor Unit", "SS-1, SS-2", 2)
    _family(ledger, "CU", "Condensing Unit", "CU-5, CU-6", 2)
    _match(ledger, "NORTH SPLITS", "AC", "Q3")
    _match(ledger, "SOUTH SPLITS", "SS", "Q4")
    _match(ledger, "EAST SPLITS", "CU", "Q5")
    job = _plan(ledger)
    assert len(job.systems) == 3
    assert not any("pair up by tag number" in q for q in job.questions)
    assert any("NORTH SPLITS" in q and "SOUTH SPLITS" in q and "share tag numbers" in q for q in job.questions)


def test_two_outdoor_only_sections_never_pair_but_an_outdoor_and_an_indoor_section_do():
    ledger = _ledger()
    _family(ledger, "IU", "Split System Indoor Unit", "IU-1, IU-2", 2)
    _family(ledger, "ODU", "Heat Pump Outdoor Unit", "ODU-1, ODU-2", 2)
    _match(ledger, "NORTH SPLITS", "IU", "Q3")
    _match(ledger, "SOUTH SPLITS", "ODU", "Q4")
    job = _plan(ledger)
    assert len(job.systems) == 1
    # two outdoor-only sections (both condensing units) are two systems
    ledger = _ledger()
    _family(ledger, "CU", "Condensing Unit", "CU-1, CU-2", 2)
    _family(ledger, "ACCU", "Air Cooled Condensing Unit", "ACCU-1, ACCU-2", 2)
    _match(ledger, "NORTH SPLITS", "CU", "Q3")
    _match(ledger, "SOUTH SPLITS", "ACCU", "Q4")
    job = _plan(ledger)
    assert len(job.systems) == 2
    assert not any("pair up by tag number" in q for q in job.questions)


def test_the_condensate_pump_question_names_neither_a_cooling_tower_nor_a_cooling_coil_pump():
    ledger = _ledger()
    _family(ledger, "CT", "Cooling Tower", "CT-1, CT-2", 2)
    _family(ledger, "CHWP", "Cooling Water Pump", "CHWP-1, CHWP-2", 2)
    _family(ledger, "FCU", "Fan Coil Unit", "FCU-1, FCU-2", 2)
    _family(ledger, "AC", "Air Conditioning Unit", "AC-1, AC-2", 2)
    _family(ledger, "ACCU", "Air Cooled Condensing Unit", "ACCU-1, ACCU-2", 2)
    _family(ledger, "CP", "Condensate Pump", "CP-1, CP-2", 2)
    (asked,) = [q for q in _plan(ledger).questions if "CP-1" in q]
    assert "Cooling Tower" not in asked and "Cooling Water Pump" not in asked
    assert "Fan Coil Unit (FCU-1, 2)" in asked


def test_a_no_kind_code_already_a_tag_of_its_owner_says_the_owner_count_is_its_own():
    """P-1 is one of P's tags and has its own count of 3; the P count printed is that 3. The question says so,
    so the estimator knows P could be more than 3."""
    ledger = _ledger()
    _family(ledger, "P", "Circulating Pump", "P-1, P-2", 2)
    ledger.add("family", "P-1", "type code on a schedule", "S1", "P-1 (type code on a schedule): schedule rows 1",
               "seed")
    ledger.add("count", "P-1", 3, "S1", "P-1 (type code on a schedule): schedule rows 3", "seed", SETTLED)
    job = _plan(ledger)
    (p,) = job.systems
    (asked,) = [q for q in job.questions if "P-1" in q]
    assert "one of the Circulating Pump (P) tags" in asked
    assert f"The P count ({p.families[0].count.value}) is taken from P-1's own count" in asked
