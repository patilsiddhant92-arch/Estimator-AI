"""T-010 lead fixes (2026-10-12, after the review of record): the Playbook sentence for the freezestat and the
dirty-filter switch, the owner passages and the low-limit names of the intake check, and the contradiction lines in
the Evidence Package. Invented fixtures only: no job text."""
from __future__ import annotations

import dataclasses as dc

import pytest

import test_t010_ownership as own
from bms import ai, ai_evidence

SEQUENCE = "Seq of Ops, Invented.pdf page 1"
UNIT_RULE = "Unit control devices when AME provides the controls"


def _plain(name: str) -> str:
    return " ".join(own.PLAYBOOK.rules[name].text.split())


# ---- the three Playbook rules agree --------------------------------------------------------------------------------

def test_the_unit_control_devices_rule_names_the_exception_in_one_sentence():
    text = _plain(UNIT_RULE)
    sentence = ('The freezestat and the dirty-filter switch are the exception: they are "Furnish and Wire" by AME, '
                'unless the sequence or the controls diagram says the unit manufacturer furnishes them; on a packaged '
                'unit with factory controls a freezestat is a line only when the sequence or the controls diagram '
                'names it.')
    assert text.count(sentence) == 1 and text.endswith(sentence)
    assert 'They are "Furnish and Install"' in text          # the rule still says it for the other devices


def test_the_three_rules_say_the_same_about_the_two_devices():
    ame, packaged = _plain(own.AME_RULE), _plain(own.PACKAGED_RULE)
    assert "On a unit whose DDC AME provides" in ame
    assert 'The line is "Furnish and Wire <device>".' in ame
    assert 'the line is then "Wire <device> (Furnished by Unit Mfr.)"' in ame
    assert "a sequence or a controls diagram that says the unit manufacturer furnishes the device" in ame
    assert "A schedule row or a schedule note alone does not give the device to the unit manufacturer." in ame
    assert "On a packaged unit with factory controls" in packaged      # a packaged unit whose controller AME furnishes
    assert "unless the sequence or the controls diagram names it" in packaged     # follows the AME rule instead


# ---- should fix 1: owner passages the unit manufacturer's exception reads --------------------------------------------

def _problems(quote, verb, furnished, name="Freezestat", slot="freezestat"):
    """The check as `_check_system` calls it on a unit with AME's DDC: one device citing one sequence passage."""
    device = own._device(name, slot, verb, [], furnished=furnished, installed="Unit Mfr.")
    device["refs"] = [{"source_id": "S1", "quote": quote, "where": SEQUENCE}]
    return ai._freezestat_filter_problems(own._unit(), None, [device], set(), frozenset({"S1"}), own.PLAYBOOK.rules)


MAKER_PASSAGES = [
    "{} SHALL BE FURNISHED BY THE UNIT MANUFACTURER",
    "THE UNIT MANUFACTURER SHALL FURNISH THE {}",
    "THE UNIT MANUFACTURER WILL PROVIDE THE {}",
    "THE {} IS FACTORY FURNISHED AND WIRED BY THE CONTROLS CONTRACTOR",
    "{} FACTORY PROVIDED AND FIELD WIRED BY THE CONTROLS CONTRACTOR",
]
DEVICES = [("LOW LIMIT FREEZESTAT", "Low Limit Freezestat", "freezestat"),
           ("DIRTY FILTER SWITCH", "Dirty Filter Switch", "filter_dp")]


@pytest.mark.parametrize("passage", MAKER_PASSAGES)
@pytest.mark.parametrize("words, name, slot", DEVICES)
def test_a_passage_that_gives_the_furnishing_to_the_unit_maker_moves_the_device_to_wire(passage, words, name, slot):
    quote = passage.format(words)
    assert _problems(quote, "Wire", "Unit Mfr.", name, slot) == []
    (problem,) = _problems(quote, "Furnish and Wire", "AME", name, slot)
    assert f'"{own.AME_RULE}"' in problem and own._first_sentence(own.AME_RULE) in problem


@pytest.mark.parametrize("passage", ["THE CONTROLS CONTRACTOR SHALL FURNISH THE {}",
                                     "THE UNIT MANUFACTURER SHALL NOT FURNISH THE {}",
                                     "THE {} IS FACTORY INSTALLED AND WIRED BY THE CONTROLS CONTRACTOR",
                                     "THE {} SHALL BE FURNISHED BY THE CONTROLS CONTRACTOR, INSTALLED AT THE FACTORY"])
def test_a_passage_that_does_not_give_the_furnishing_to_the_unit_maker_leaves_furnish_and_wire(passage):
    quote = passage.format("LOW LIMIT FREEZESTAT")
    assert _problems(quote, "Furnish and Wire", "AME") == []
    assert _problems(quote, "Wire", "Unit Mfr.") != []


def test_a_passage_with_two_furnishers_does_not_settle_it():
    quote = "THE UNIT MANUFACTURER SHALL FURNISH THE LOW LIMIT FREEZESTAT, WHICH THE CONTROLS CONTRACTOR SHALL FURNISH"
    assert _problems(quote, "Furnish and Wire", "AME") == []


def test_a_passage_about_the_other_device_does_not_move_this_one():
    quote = "THE UNIT MANUFACTURER SHALL FURNISH THE DIRTY FILTER SWITCH"
    assert _problems(quote, "Furnish and Wire", "AME", "Low Limit Freezestat", "freezestat") == []


def test_the_reader_of_stated_parties_is_unchanged():
    """The split into `_party_sets` keeps `stated_parties`: the other checks read it as before."""
    assert ai.stated_parties("FURNISHED BY THE UNIT MANUFACTURER, WIRED BY THE CONTROLS CONTRACTOR") == {
        "furnished_by": "Unit Mfr.", "wired_by": "AME"}
    assert ai.stated_parties("FACTORY FURNISHED AND WIRED BY THE CONTROLS CONTRACTOR") == {"wired_by": "AME"}
    assert ai.stated_parties("THE UNIT MANUFACTURER SHALL FURNISH THE FREEZESTAT") == {}


# ---- should fix 2: a freezestat by the words of its name -------------------------------------------------------------

@pytest.mark.parametrize("name", ["Low Limit Thermostat", "low-limit", "Low-Limit Stat", "Freeze Protection Thermostat",
                                  "Freeze-Protection Switch", "Low Temperature Detection Thermostat",
                                  "Low Temp Cutout", "Coil Low Limit Freezestat"])
def test_the_detector_finds_the_freezestat_by_its_words(name):
    assert ai.owned_device_kind(name) == "freezestat"
    assert ai.owned_device_kind(name, "thermostat") == "freezestat"       # a slot that is no freezestat slot


@pytest.mark.parametrize("name", ["Freeze Protection Pump", "Low Pressure Switch", "Low Temperature Sensor",
                                  "Low Water Cutoff", "Discharge Air Temperature Sensor"])
def test_the_detector_leaves_the_devices_that_only_sound_alike(name):
    assert ai.owned_device_kind(name) is None


def test_a_low_limit_thermostat_on_a_unit_with_ame_ddc_follows_the_ame_rule_without_the_slot():
    """The check reads the name: the writer put the device in a slot that is not the shape's freezestat slot."""
    for verb, refused in (("Furnish and Install", True), ("Furnish and Wire", False)):
        device = own._device("Low Limit Thermostat", "thermostat", verb, ("S5",))
        _, problems = own._check(own._unit(), device)
        assert any(f'"{own.AME_RULE}"' in p for p in problems) is refused, (verb, problems)


def _packaged_problems(passage_id: str) -> list[str]:
    """The intake check on a packaged unit for a "Freeze Protection Thermostat" line that cites `passage_id`; S9 (a
    controls-diagram passage) names a freeze protection thermostat in this evidence."""
    quote = "FREEZE PROTECTION THERMOSTAT FS-1 AT THE COOLING COIL"
    evidence = own.EVIDENCE.replace(own.DIAG_FS, quote)
    device = own._device("Freeze Protection Thermostat", "thermostat", "Wire", (passage_id,), furnished="Unit Mfr.")
    for ref in device["refs"]:
        ref["quote"] = quote if ref["source_id"] == "S9" else ref["quote"]
    system = own._unit("packaged")
    known = ai_evidence.cited_ids(evidence)
    _, problems = ai._check_system(own._answer(system, device), system, None, known, (), (), [],
                                   index=ai._sent_index(evidence), stated=ai_evidence.stated_ids(evidence),
                                   diagram=ai_evidence.sequence_and_diagram_ids(evidence), rules=own.PLAYBOOK.rules)
    return problems


def test_a_freeze_protection_thermostat_on_a_packaged_unit_needs_a_passage_that_names_it():
    assert any(f'"{own.PACKAGED_RULE}"' in p for p in _packaged_problems("S5")), "a schedule row alone"
    assert _packaged_problems("S9") == []


# ---- the contradiction lines reach the Evidence Package, with their citations ----------------------------------------

import test_t010_contradictions as con                       # noqa: E402  (the invented contested counts and owners)
from bms.evidence import SCOPE_HEADINGS, FlaggedLine, flagged_lines, scope_rows      # noqa: E402
from bms.model import Clarification, Count, Family, OtherCount        # noqa: E402
from bms.playbook import load_playbook                                 # noqa: E402
from bms.render import contradiction_refs, render                      # noqa: E402

AT = {h: i for i, h in enumerate(SCOPE_HEADINGS)}
CITATIONS = "Citations (id, where, quote)"


@pytest.fixture(scope="module")
def pb():
    return load_playbook(con.ROOT / "playbook")


def _contested_job():
    """One block: a family count of 55 contested by a schedule (1) and a plan sheet (7), and a freezestat whose owner
    the cited sequence contests."""
    count = Count(value=55, sources=(con.P901,), others=(OtherCount(1, con.ROWS), OtherCount(7, con.P902)))
    return con.job(con.system(families=(Family("Fan Coil Unit", ("FC-1",), count),),
                              devices=(con.device(), con.owner_device()),
                              clarifications=(Clarification("note", "Invented note text"),)))


def test_a_count_contradiction_line_is_in_the_scope_rows_with_every_source_it_names(pb):
    job = _contested_job()
    draft = render(job, pb)
    flagged = flagged_lines(job, pb, draft.lines)
    (counts,) = [f for f in flagged if "counts differ" in f.text]
    assert counts.refs == (con.P901, con.ROWS, con.P902)         # the count's sources first, then each other count's
    rows = scope_rows(job, {}, flagged)
    (row,) = [r for r in rows if r[AT["Kind"]] == "contradiction" and "counts differ" in r[AT["Printed line"]]]
    assert row[AT["Printed line"]] == counts.text and counts.text.startswith("*") and len(row) == len(SCOPE_HEADINGS)
    assert row[AT["System"]] == "Fan Coil Units (FC)" and row[AT["Device id"]] is None
    for ref in (con.P901, con.ROWS, con.P902):
        for part in (ref.source_id, ref.quote, ref.where):
            assert part in row[AT[CITATIONS]], (part, row[AT[CITATIONS]])
    assert con.numbers(row[AT["Printed line"]]) == [55, 7, 1]       # every number of the bracket is on the sheet


def test_an_owner_contradiction_line_is_in_the_scope_rows_with_the_devices_refs(pb):
    job = _contested_job()
    flagged = flagged_lines(job, pb, render(job, pb).lines)
    (owner,) = [f for f in flagged if f.text.startswith("*Freezestat")]
    assert owner.refs == (con.SEQ_MFR,)
    (row,) = [r for r in scope_rows(job, {}, flagged) if r[AT["Printed line"]] == owner.text]
    assert row[AT["Kind"]] == "contradiction" and con.SEQ_MFR.source_id in row[AT[CITATIONS]]
    assert con.SEQ_MFR.quote in row[AT[CITATIONS]]


def test_the_flagged_rows_sit_under_their_block_after_its_devices_and_clarifications(pb):
    job = _contested_job()
    rows = scope_rows(job, {}, flagged_lines(job, pb, render(job, pb).lines))
    kinds = [r[AT["Kind"]] for r in rows]
    first = kinds.index("contradiction")
    assert set(kinds[first:]) <= {"contradiction", "flagged note", "sequence"}
    assert max(i for i, k in enumerate(kinds) if k == "device") < first
    assert max(i for i, k in enumerate(kinds) if k.startswith("clarification")) < first


def test_a_star_note_that_is_no_contradiction_is_listed_without_citations_and_a_device_line_is_not_repeated(pb):
    job = _contested_job()
    draft = render(job, pb)
    flagged = flagged_lines(job, pb, draft.lines)
    black = [f for f in flagged if not f.refs]
    assert black and all(f.text.startswith("*") for f in flagged)
    rows = scope_rows(job, {}, flagged)
    assert all(r[AT[CITATIONS]] is None for r in rows if r[AT["Kind"]] == "flagged note")
    device_lines = {l.text for l in draft.lines if l.device_id}
    assert device_lines and not device_lines & {f.text for f in flagged}


def test_every_line_contradiction_refs_names_is_a_line_render_prints(pb):
    job = _contested_job()
    printed = {(l.system_key, l.text) for l in render(job, pb).lines}
    named = contradiction_refs(job, pb)
    assert named and set(named) <= printed
    empty = dc.replace(con.system(), devices=())            # a system with no lines prints no block
    assert contradiction_refs(con.job(empty), pb) == {}


def test_a_flagged_line_of_no_block_is_a_whole_job_row_and_no_flagged_line_changes_the_other_rows(pb):
    job = _contested_job()
    plain = scope_rows(job)
    rows = scope_rows(job, {}, [FlaggedLine("nowhere", "*An invented note"), FlaggedLine("", "*Another invented note")])
    assert rows[:len(plain)] == plain and len(rows) == len(plain) + 2
    assert [(r[AT["System"]], r[AT["Kind"]], r[AT["Printed line"]]) for r in rows[len(plain):]] == [
        ("Whole job", "flagged note", "*An invented note"), ("Whole job", "flagged note", "*Another invented note")]
