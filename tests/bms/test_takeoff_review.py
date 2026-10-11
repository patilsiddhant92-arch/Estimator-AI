"""Reviewer's tests for T-006 (takeoff pass, Stage 1). Invented fixture only ("Invented Hall", 00-1111)."""
from __future__ import annotations

import copy
import dataclasses

import pytest

import takeoff_fixture as fx
from bms import ai, takeoff
from bms.model import Unit


def _check(answer, ledger=None, index=None):
    ledger = ledger or fx.ledger()
    index = ai.evidence_index(fx.dossier()) if index is None else index
    return takeoff.check_answer(answer, ledger, fx.catalogue(), fx.reading(), index)


def _unit(answer, tag):
    return next(u for u in answer["units"] if u["tag"] == tag)


def test_the_prompt_lists_every_sheet_of_the_fixture_exactly_once():
    text = takeoff.prompt(fx.ledger(), fx.catalogue(), fx.reading(), fx.dossier())
    lines = [line for line in text.splitlines() if line.startswith(f"{fx.DOC} | page ")]
    pages = sorted(row["page"] for row in fx.sheets())
    assert [int(line.split(" | ")[1].split()[1]) for line in lines] == pages
    for row in fx.sheets():
        assert sum(1 for line in lines if f" | {row['number']} | " in line) == 1, row["number"]


@pytest.mark.parametrize("status", ["demolish", "existing_remain", "future", "demolish_with_work"])
def test_a_scheduled_tag_set_aside_without_a_ref_beyond_its_schedule_is_refused(status):
    answer = fx.answer()
    _unit(answer, "EF-2").update(status=status, reason="Shown for removal.")   # F6 cites only the EF schedule
    value, problems = _check(answer)
    assert value is None and any("EF-2" in p and status in p for p in problems), problems


def test_a_scheduled_tag_answered_only_by_its_label_still_needs_a_row():
    answer = fx.answer()
    unit = _unit(answer, "AHU-4")
    unit["tag"], unit["labels"] = "AHU-04", ["AHU-04"]                # not the schedule's tag, not its plain form
    value, problems = _check(answer)
    assert value is None and any("AHU-4" in p for p in problems), problems


def test_citing_the_schedules_own_row_does_not_set_a_scheduled_unit_aside():
    ledger = copy.deepcopy(fx.ledger())
    ledger.sources["S90"] = "AIR HANDLING UNIT SCHEDULE row AHU-5, M-601, Mech.pdf page 1"   # the dossier's form
    index = {**ai.evidence_index(fx.dossier()), "S90": "AHU-5 | 2000 | 1"}
    answer = fx.answer()
    _unit(answer, "AHU-5").update(status="demolish", reason="Removed.",
                                  refs=[{"source_id": "S90", "quote": "AHU-5", "where": "M-601"}])
    value, problems = _check(answer, ledger, index)
    assert value is None and any("AHU-5" in p for p in problems), problems


def test_an_answer_that_gives_with_plant_is_kept_and_a_saved_row_without_it_loads():
    answer = fx.answer()
    assert all(u["with_plant"] is False for u in answer["units"])    # the prompt asks for it on every unit row
    _unit(answer, "ERU-1")["with_plant"] = True
    value, problems = _check(answer)
    assert problems == [] and next(u for u in value.units if u.tag == "ERU-1").with_plant is True
    del _unit(answer, "ERU-1")["with_plant"]                            # strict schema: the AI gives every key
    value, problems = _check(answer)
    assert value is None and any("with_plant" in p for p in problems), problems
    row = {k: v for k, v in fx.answer()["units"][0].items() if k != "with_plant"}
    assert Unit.from_dict(row).with_plant is False                     # a register saved before the field loads


def test_a_relocated_scheduled_unit_is_not_counted_without_a_cited_passage():
    answer = fx.answer()
    _unit(answer, "EF-4").update(status="relocate", reason="Moved.")  # ruling 17: relocation is not new work
    value, problems = _check(answer)
    assert value is None and any("EF-4" in p and "relocate" in p for p in problems), problems


def _ahu5_aside(source_id, label, text, quote="AHU-5"):
    """AHU-5 set aside (demolish) on one invented passage: `label` is its source's name in the ledger (the dossier's
    form), `text` the passage."""
    ledger = copy.deepcopy(fx.ledger())
    ledger.sources[source_id] = label
    index = {**ai.evidence_index(fx.dossier()), source_id: text}
    answer = fx.answer()
    _unit(answer, "AHU-5").update(status="demolish", reason="Removed.",
                                  refs=[{"source_id": source_id, "quote": quote, "where": "M-601"}])
    return _check(answer, ledger, index)


def test_a_schedule_note_is_a_passage_beyond_the_row():
    value, problems = _ahu5_aside("S91", "AIR HANDLING UNIT SCHEDULE notes, M-601, Mech.pdf page 1",
                                  "Note: AHU-5 IS EXISTING TO BE REMOVED", quote="AHU-5 IS EXISTING TO BE REMOVED")
    assert problems == [] and value is not None


def test_a_fact_resting_on_the_units_own_row_does_not_set_it_aside():
    ledger = copy.deepcopy(fx.ledger())
    ledger.sources["S90"] = "AIR HANDLING UNIT SCHEDULE row AHU-5, M-601, Mech.pdf page 1"
    fact = ledger.facts["F3"]
    ledger.facts["F3"] = dataclasses.replace(fact, source_id="S90")
    answer = fx.answer()
    _unit(answer, "AHU-5").update(status="existing_remain", reason="Existing.")     # cites F3
    value, problems = _check(answer, ledger)
    assert value is None and any("AHU-5" in p for p in problems), problems


def test_a_schedule_with_no_sheet_number_is_still_the_schedule():
    ledger = copy.deepcopy(fx.ledger())
    ledger.sources["S1"] = "AIR HANDLING UNIT SCHEDULE, Mech.pdf page 1"           # the dossier's form, no sheet
    reading = fx.reading()
    ahu = next(s for s in reading.schedules if s.title == "AIR HANDLING UNIT SCHEDULE")
    reading.schedules = tuple(dataclasses.replace(s, sheet="") if s is ahu else s for s in reading.schedules)
    answer = fx.answer()
    _unit(answer, "AHU-5").update(status="demolish", reason="Removed.")              # cites F3, from S1
    value, problems = takeoff.check_answer(answer, ledger, fx.catalogue(), reading, ai.evidence_index(fx.dossier()))
    assert value is None and any("AHU-5" in p for p in problems), problems
