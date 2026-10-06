"""FINAL-D: the planner's joins never merge what the documents keep apart without asking (F2 split sections, F3
families of one name, F4 a no-kind code, F6 condensate pumps). Invented ledgers only."""
from __future__ import annotations

from test_plan import SETTLED, _family, _ledger, _plan


def _match(ledger, section, prefix, sid):
    ledger.add("sequence_match", section, prefix, sid, section, "sequence", SETTLED)


# ---- F2: two split sections are one block only when every unit of the smaller pairs with the other ----------

def test_split_sections_sharing_only_some_numbers_stay_apart_and_are_asked():
    ledger = _ledger()
    _family(ledger, "AC", "Air Conditioning Unit", "AC-1, AC-2", 2)
    _family(ledger, "ACCU", "Air Cooled Condensing Unit", "ACCU-1, ACCU-5", 2)
    _match(ledger, "NORTH SPLITS", "AC", "Q3")
    _match(ledger, "SOUTH SPLITS", "ACCU", "Q4")
    job = _plan(ledger)
    assert sorted(s.key for s in job.systems) == ["AC", "ACCU"]              # one family each: each its own block
    asked = [q for q in job.questions if "NORTH SPLITS" in q and "SOUTH SPLITS" in q]
    assert len(asked) == 1
    assert "share tag numbers" in asked[0] and "two Split System blocks" in asked[0] and asked[0].endswith("?")


def test_split_sections_each_paired_on_their_own_stay_apart_and_are_asked():
    ledger = _ledger()
    _family(ledger, "AC", "Ductless Split Indoor Unit", "AC-1, AC-2", 2)
    _family(ledger, "CU", "Condensing Unit", "CU-1, CU-2", 2)
    _family(ledger, "SS", "Indoor Unit", "SS-1", 1)
    _family(ledger, "ACCU", "Air Cooled Condensing Unit", "ACCU-1", 1)
    for prefix in ("AC", "CU"):
        _match(ledger, "NORTH SPLITS", prefix, "Q3")
    for prefix in ("SS", "ACCU"):
        _match(ledger, "SOUTH SPLITS", prefix, "Q4")
    job = _plan(ledger)
    assert len(job.systems) == 2
    assert any("NORTH SPLITS" in q and "SOUTH SPLITS" in q and "share tag numbers" in q for q in job.questions)


def test_an_indoor_section_and_its_outdoor_section_join_and_the_join_is_asked():
    ledger = _ledger()
    _family(ledger, "AC", "Air Conditioning Unit", "AC-109, AC-117", 2)
    _family(ledger, "ACCU", "Air Cooled Condensing Unit", "ACCU-109, ACCU-117", 2)
    _match(ledger, "NORTH SPLITS", "AC", "Q3")
    _match(ledger, "SOUTH SPLITS", "ACCU", "Q4")
    job = _plan(ledger)
    (split,) = job.systems
    assert [r.source_id for r in split.sequence_refs] == ["Q3", "Q4"]
    asked = [q for q in job.questions if "NORTH SPLITS" in q and "SOUTH SPLITS" in q]
    assert len(asked) == 1 and "pair up by tag number" in asked[0] and "Confirm" in asked[0]


# ---- F3: families of one name matched to different sequence sections stay apart --------------------------------

def test_families_of_one_name_in_different_sequence_sections_stay_apart_and_are_asked():
    ledger = _ledger()
    _family(ledger, "EF", "Exhaust Fan", "EF-1", 1)
    _family(ledger, "KEF", "Exhaust Fan", "KEF-1", 1)
    _family(ledger, "XF", "Exhaust Fans", "XF-1", 1)                      # matched to no section
    _match(ledger, "EXHAUST FANS", "EF", "Q1")
    _match(ledger, "KITCHEN EXHAUST", "KEF", "Q2")
    job = _plan(ledger)
    assert [s.key for s in job.systems] == ["EF", "KEF", "XF"]
    asked = [q for q in job.questions if "EF" in q and "KEF" in q]
    assert len(asked) == 1 and "its own sequence section" in asked[0] and "separate" in asked[0]
    assert not any("so they are planned as one" in q for q in job.questions)
    # one matched and one not: still one block, asked as before
    ledger = _ledger()
    _family(ledger, "EF", "Exhaust Fan", "EF-1", 1)
    _family(ledger, "KEF", "Exhaust Fan", "KEF-1", 1)
    _match(ledger, "EXHAUST FANS", "EF", "Q1")
    job = _plan(ledger)
    assert [s.key for s in job.systems] == ["EF"]
    assert any("same name" in q for q in job.questions)


# ---- F4: a no-kind code joins its owner once, and the question says what the code did ------------------------

NO_KIND = "type code on a schedule"


def test_a_no_kind_code_already_a_tag_of_its_owner_is_counted_once_and_asked_plainly():
    ledger = _ledger()
    _family(ledger, "P", "Circulating Pump", "P-1, P-2", 2)
    ledger.add("family", "P-1", NO_KIND, "S1", f"P-1 ({NO_KIND}): schedule rows 1", "seed")
    ledger.add("count", "P-1", 1, "S1", f"P-1 ({NO_KIND}): schedule rows 1", "seed", SETTLED)
    job = _plan(ledger)
    (p,) = job.systems
    assert [f.tags for f in p.families] == [("P-1", "P-2")]
    (asked,) = [q for q in job.questions if "P-1" in q]
    assert "one of the Circulating Pump (P) tags" in asked and "not again" in asked and "Confirm" in asked
    assert "not already in" not in asked


def test_a_no_kind_code_whose_count_the_owner_took_says_the_owner_count_includes_it():
    ledger = _ledger()
    _family(ledger, "GI", "Grease Interceptor", "GI-1 thru 3", 3)
    ledger.add("family", "GI-4", NO_KIND, "S1", f"GI-4 ({NO_KIND}): schedule rows 1", "seed")
    ledger.add("count", "GI-4", 9, "S1", f"GI-4 ({NO_KIND}): schedule rows 1", "seed", SETTLED)
    job = _plan(ledger)
    (asked,) = [q for q in job.questions if "GI-4" in q]
    assert "not already in" not in asked
    assert "The GI count (9) is taken from GI-4's own count, so it already includes GI-4" in asked
    assert "Confirm" in asked


# ---- F6: condensate pumps joined to a split block on their numbers alone name the other equipment they may serve

def test_condensate_pumps_joined_on_numbers_name_the_air_handling_units_they_may_belong_to():
    ledger = _ledger()
    _family(ledger, "AHU", "Air Handling Unit", "AHU-1, AHU-2", 2)
    _family(ledger, "AC", "Air Conditioning Unit", "AC-1, AC-2, AC-3", 3)
    _family(ledger, "ACCU", "Air Cooled Condensing Unit", "ACCU-1, ACCU-2, ACCU-3", 3)
    _family(ledger, "CP", "Condensate Pump", "CP-1, CP-2", 2)
    _family(ledger, "EF", "Exhaust Fan", "EF-1, EF-2", 2)                 # same numbers, makes no condensate
    job = _plan(ledger)
    (asked,) = [q for q in job.questions if "CP-1" in q]
    assert "Confirm" in asked
    assert "Exhaust Fan" not in asked
    assert "Air Handling Unit (AHU-1, 2)" in asked and "carry the same numbers" in asked
    assert "they belong in that block instead" in asked
    # with no other equipment of those numbers, the question still names the other possibility
    ledger = _ledger()
    _family(ledger, "AC", "Air Conditioning Unit", "AC-1, AC-2", 2)
    _family(ledger, "ACCU", "Air Cooled Condensing Unit", "ACCU-1, ACCU-2", 2)
    _family(ledger, "CP", "Condensate Pump", "CP-1, CP-2", 2)
    (asked,) = [q for q in _plan(ledger).questions if "CP-1" in q]
    assert "If they serve other equipment, they belong with that equipment instead." in asked
