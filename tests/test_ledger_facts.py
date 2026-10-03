# tests/test_ledger_facts.py
"""The job ledger: facts that lock, contradictions beside them, the higher count printed."""
import json

import pytest

from estimator.ledger.facts import ADDED, CONTRADICTED, SETTLED, Fact, Ledger, where_short

SOURCES = {"S41": "M-601 VAV BOX SCHEDULE, Drawings.pdf page 12", "S60": "equipment counts for VAV (schedules and plans)",
           "S12": "M-201, Drawings.pdf page 3 (sheet text)", "Q7": "sequence section “VAV BOXES”, Specs.pdf page 44"}


def _ledger():
    return Ledger(dict(SOURCES))


def test_a_fact_is_added_with_its_source_quote_and_stage():
    ledger = _ledger()
    fact = ledger.add("count", "VAV", 12, "[S41]", "QUANTITY 12", "schedules", SETTLED)

    assert fact.id == "F1"
    assert fact.source_id == "S41"            # brackets stripped, so every id is stored one way
    assert fact.state == SETTLED
    assert ledger.facts["F1"] is fact
    assert ledger.find("count", "VAV") is fact


def test_a_fact_needs_a_known_source_and_a_quote():
    ledger = _ledger()
    with pytest.raises(ValueError, match="source"):
        ledger.add("count", "VAV", 12, "[S99]", "QUANTITY 12", "schedules")
    with pytest.raises(ValueError, match="quote"):
        ledger.add("count", "VAV", 12, "[S41]", "", "schedules")
    with pytest.raises(ValueError, match="kind"):
        ledger.add("guess", "VAV", 12, "[S41]", "QUANTITY 12", "schedules")
    with pytest.raises(ValueError, match="pass"):
        ledger.add("count", "VAV", 12, "[S41]", "QUANTITY 12", "dreams")


def test_a_settled_fact_never_changes_its_value_a_contradiction_sits_beside_it():
    ledger = _ledger()
    fact = ledger.add("count", "VAV", 12, "[S41]", "QUANTITY 12", "schedules", SETTLED)
    after = ledger.contradict("F1", 14, "[S12]", "VAV-1 … VAV-14", "plans")

    assert after.value == 12
    assert after.state == CONTRADICTED
    assert after.contradictions[0].value == 14
    assert after.contradictions[0].source_id == "S12"
    assert after.contradictions[0].stage == "plans"
    assert ledger.facts["F1"] is after and fact is not after


def test_the_same_value_again_is_not_a_contradiction():
    ledger = _ledger()
    ledger.add("count", "VAV", 12, "[S41]", "QUANTITY 12", "schedules", SETTLED)
    after = ledger.contradict("F1", 12, "[S12]", "twelve boxes", "plans")
    assert after.state == SETTLED and after.contradictions == ()


def test_the_printed_count_is_the_highest_value():
    ledger = _ledger()
    ledger.add("count", "VAV", 12, "[S41]", "QUANTITY 12", "schedules", SETTLED)
    ledger.contradict("F1", 14, "[S12]", "VAV-1 … VAV-14", "plans")
    ledger.contradict("F1", 10, "[S60]", "distinct tags 10", "plans")
    assert ledger.printed_count("F1") == 14
    ledger.add("provider", "RTU", "unit mfr", "[S41]", "controller by unit mfr", "schedules", SETTLED)
    assert ledger.printed_count("F2") is None


def test_settling_an_added_fact():
    ledger = _ledger()
    ledger.add("device", "OCC", 21, "[S60]", "21 in all", "seed")
    assert ledger.facts["F1"].state == ADDED
    assert ledger.settle("F1").state == SETTLED


def test_the_table_lists_each_fact_in_one_line():
    ledger = _ledger()
    ledger.add("count", "VAV", 12, "[S41]", "QUANTITY 12", "schedules", SETTLED)
    ledger.contradict("F1", 14, "[S12]", "VAV-1 … VAV-14", "plans")
    ledger.add("sequence_match", "VAV BOXES", "VAV", "[Q7]", "VAV BOXES", "sequence", SETTLED)
    text = ledger.table()
    assert "F1 count VAV = 12 [S41] “QUANTITY 12” (contradicted, schedules; plans says 14 [S12] “VAV-1 … VAV-14”)" in text
    assert "F2 sequence_match VAV BOXES = VAV [Q7] “VAV BOXES” (settled, sequence)" in text
    assert ledger.table(["F2"]).count("\n") == 0


def test_the_ledger_round_trips_through_json(tmp_path):
    ledger = _ledger()
    ledger.add("count", "VAV", 12, "[S41]", "QUANTITY 12", "schedules", SETTLED)
    ledger.contradict("F1", 14, "[S12]", "VAV-1 … VAV-14", "plans")
    ledger.understanding["schedules"] = "Twelve VAV boxes on one schedule."
    ledger.complete = False
    ledger.stopped_at = "plans"
    ledger.job_name = "26-9999"
    ledger.refused = {"schedules": ["count T = 3 has no quote; left out"]}
    path = tmp_path / "ledger.json"
    ledger.save(path)

    back = Ledger.load(path)
    assert back.facts["F1"] == ledger.facts["F1"]
    assert back.understanding == {"schedules": "Twelve VAV boxes on one schedule."}
    assert back.sources == SOURCES
    assert back.complete is False and back.stopped_at == "plans"
    assert back.job_name == "26-9999" and back.refused == {"schedules": ["count T = 3 has no quote; left out"]}
    assert json.loads(path.read_text(encoding="utf-8"))["facts"][0]["id"] == "F1"


def test_where_short_drops_the_parenthetical():
    assert where_short("M-201, Drawings.pdf page 3 (sheet text)") == "M-201, Drawings.pdf page 3"
    assert where_short("equipment counts for VAV (schedules and plans)") == "equipment counts for VAV"


def test_resolving_an_added_fact_takes_the_passs_value_and_settles_it():
    ledger = _ledger()
    ledger.add("count", "VAV", 2, "[S60]", "plan placements 2", "seed")
    fact = ledger.resolve("F1", 3, "[S41]", "QUANTITY 3", "schedules")
    assert fact.id == "F1" and ledger.facts["F1"] is fact
    assert (fact.value, fact.source_id, fact.quote, fact.stage, fact.state) == (3, "S41", "QUANTITY 3", "schedules", SETTLED)


def test_resolving_refuses_a_settled_fact_an_empty_quote_or_an_unknown_source():
    ledger = _ledger()
    ledger.add("count", "VAV", 12, "[S41]", "QUANTITY 12", "schedules", SETTLED)
    ledger.add("count", "EF", 2, "[S60]", "plan placements 2", "seed")
    with pytest.raises(ValueError, match="only a fact still waiting"):
        ledger.resolve("F1", 14, "[S12]", "VAV-1 … VAV-14", "plans")
    with pytest.raises(ValueError, match="quote"):
        ledger.resolve("F2", 3, "[S41]", "  ", "schedules")
    with pytest.raises(ValueError, match="source"):
        ledger.resolve("F2", 3, "[S99]", "three", "schedules")
    with pytest.raises(ValueError, match="pass"):
        ledger.resolve("F2", 3, "[S41]", "three", "dreams")
    assert ledger.facts["F2"].value == 2 and ledger.facts["F2"].state == ADDED


def test_find_value_matches_the_subject_loosely_and_the_value_exactly():
    ledger = _ledger()
    ledger.add("note", "question", "Is the  existing BMS kept?", "[S41]", "existing BMS", "spec", SETTLED)
    assert ledger.find_value("note", "QUESTION", "Is the existing BMS kept?").id == "F1"
    assert ledger.find_value("note", "question", "is the existing bms kept?") is None
    assert ledger.find_value("front_end", "question", "Is the existing BMS kept?") is None
