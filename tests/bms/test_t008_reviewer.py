"""T-008 reviewer's own tests (invented fixtures only)."""
from __future__ import annotations

import re
from dataclasses import replace

import pytest

from bms.labor import labor_conditions, with_labor
from bms.model import Count, Family
from bms.render import LONG_CLARIFICATION, render, short_points
from estimator.ledger.facts import Ledger
from test_t008_labor import _ledger, _note, _Overview, _written
from test_t008_render import AHU, CV, _headers, dev, job, playbook, sys_  # noqa: F401  (fixtures)

DAMPER = Family("Smoke Damper", ("SD-1", "SD-2"), Count(value=2))


# ---- task 1 -------------------------------------------------------------------------------------------------------

def test_reviewer_unit_with_damper_and_valve_families_prints_one_header(job, playbook):
    s = sys_((DAMPER, AHU, CV), [dev(1, "DDC Controller"), dev(2, "Smoke Damper End Switch", "damper", 2),
                                 dev(3, "Hot Water Control Valve", "hot_water_valve", 10)])
    headers = _headers(render(replace(job, systems=(s,)), playbook), "AHU")
    assert len(headers) == 1 and headers[0].startswith("Qty (5)")
    assert not any("Damper" in h or "Control Valve" in h for h in headers)


def test_reviewer_a_damper_and_valve_only_block_keeps_its_headers(job, playbook):
    s = sys_((DAMPER, CV), [dev(1, "Smoke Damper End Switch", "damper", 2),
                            dev(2, "Hot Water Control Valve", "hot_water_valve", 10)], key="DV", name="Dampers")
    assert len(_headers(render(replace(job, systems=(s,)), playbook), "DV")) == 2


# ---- task 2 -------------------------------------------------------------------------------------------------------

CONDITIONAL = "If no times are listed therein then the working hours shall be 6:00 pm - 6:00 am."


def test_reviewer_overview_and_ledger_both_finding_it_print_one_line(job, playbook):
    conditions = labor_conditions(_Overview(), ledger=_ledger(CONDITIONAL), notes=(_note("DURING OFF HOURS"),))
    assert [c.kind for c in conditions] == ["off-hours"]
    draft = with_labor(render(job, playbook), conditions)
    assert sum("Off-Hours Labor" in line.text for line in draft.lines) == 1


def _fact_ledger(*facts):
    """(kind, stage, where, quote) facts; each its own source."""
    ledger = Ledger({f"S{i}": where for i, (_, _, where, _) in enumerate(facts)})
    for i, (kind, stage, _, quote) in enumerate(facts):
        ledger.add(kind, "hours", "x", f"S{i}", quote, stage)
    return ledger


@pytest.mark.parametrize("text", ["Provide space sensor with after-hours override button.",
                                  "Unoccupied 6:00 PM to 6:00 AM: the unit shall stop.",
                                  "During night hours the unit shall index to unoccupied.",
                                  "Night setback shall apply after hours."])
def test_reviewer_a_control_sequence_in_a_key_note_or_fact_is_no_off_hours_call(text):
    assert labor_conditions(None, notes=(_note(text, controls=True),)) == ()
    assert labor_conditions(None, ledger=_fact_ledger(("note", "spec", "M-101, D.pdf page 1", text))) == ()


def test_reviewer_a_sequence_fact_never_counts_even_with_work_words():
    quote = "The contractor shall perform the work 6:00 PM to 6:00 AM."
    assert labor_conditions(None, ledger=_fact_ledger(("sequence_match", "sequence", "23 09 93, S.pdf page 4", quote),
                                                      ("note", "spec", "23 09 93 Sequence of Operations, S.pdf page 5",
                                                       quote))) == ()


@pytest.mark.parametrize("text", ["If no hours are listed therein then the working hours shall be 6:00 pm - 6:00 am.",
                                  "Working hours: 6:00 PM - 6:00 AM.",
                                  "PERFORM ALL SHUTDOWNS AND TIE-INS DURING OFF HOURS."])
def test_reviewer_a_work_condition_in_a_fact_or_key_note_is_a_call(text):
    assert [c.kind for c in labor_conditions(None, notes=(_note(text),))] == ["off-hours"]
    assert [c.kind for c in labor_conditions(
        None, ledger=_fact_ledger(("note", "spec", "01 14 00, D.pdf page 9", text)))] == ["off-hours"]


def test_reviewer_overview_fact_and_note_together_give_one_red_line_and_one_row(job, playbook, tmp_path):
    conditions = labor_conditions(_Overview(), ledger=_ledger(CONDITIONAL),
                                  notes=(_note("PERFORM ALL SHUTDOWNS DURING OFF HOURS."),))
    document, workbook = _written(job, playbook, tmp_path, conditions)
    paras = [p for p in document.paragraphs if p.text.startswith("Off-Hours Labor")]
    assert len(paras) == 1 and all(str(r.font.color.rgb) == "FF0000" for r in paras[0].runs if r.text.strip())
    ws = workbook["Price Sheet 1"]
    rows = [r for r in range(6, 397) if isinstance(ws.cell(r, 4).value, str) and "Off-Hours Labor" in ws.cell(r, 4).value]
    assert len(rows) == 1 and str(ws.cell(rows[0], 4).font.color.rgb).endswith("FF0000")


# ---- task 3 -------------------------------------------------------------------------------------------------------

def test_reviewer_three_points_and_a_because_keep_every_word_in_order():
    text = ("*Assumed: " + "one invented sensor in each invented room " * 3 + "; " + "two invented relays " * 4
            + ", because The invented schedule " + "shows invented rows " * 5)
    lines = short_points(text)
    assert len(lines) >= 3 and all(l.startswith("*") and not l.startswith("*- ") for l in lines)
    assert all(len(l) <= 160 for l in lines)
    assert any(l.startswith("*because the invented") for l in lines)
    norm = lambda s: re.sub(r"[*;,.]", " ", s).lower().split()
    assert norm(" ".join(lines)) == norm(text)


@pytest.mark.parametrize("label", ["Assumed", "Confirm quantity", "Note"])
def test_reviewer_a_label_never_prints_alone(label):
    text = f"*{label}: " + "one invented sensor in each invented room " * 4
    assert len(text) > LONG_CLARIFICATION
    assert short_points(text) == [text.strip()]                      # "Label: text" stays one line (review 3A)


def test_reviewer_a_long_left_side_that_is_no_label_still_splits_at_its_colon():
    text = "*Confirm the invented riser diagram on the invented sheet: " + "two invented sensors per floor " * 4
    lines = short_points(text)
    assert len(lines) == 2 and lines[0].endswith("sheet:") and lines[1].startswith("*two invented")


@pytest.mark.xfail(strict=True, reason="review 3B, next commit")
def test_reviewer_a_quoted_passage_is_never_split():
    quote = '"Provide one invented sensor per zone; see Sheet M-101. Typical for all floors: east and west."'
    text = "*Confirm per the invented spec " + quote + "; the invented riser shows " + "two more sensors " * 5
    lines = short_points(text)
    assert any(quote in line for line in lines)              # the quote whole, its own punctuation kept (review 3B)
    assert len(lines) == 2


# ---- task 2, source text (review 2B) ------------------------------------------------------------------------------

@pytest.mark.parametrize("where, said", [
    ("01 14 00, Invented Bid Binder.pdf page 182 (a spec page)", "Spec Section 01 14 00"),
    ("011400 Work Restrictions, Invented Binder.pdf page 3", "Spec Section 01 14 00"),
    ("M-101, Drawings.pdf page 3 (a sheet)", "Sheet M-101"),
    ("M501.01 schedule, Drawings.pdf page 7", "Sheet M501.01"),
    ("Invented Drawings.pdf page 3", "the documents"),
])
def test_reviewer_a_fact_source_names_the_section_or_sheet_never_the_file(where, said):
    (found,) = labor_conditions(None, ledger=_fact_ledger(("note", "spec", where, CONDITIONAL)))
    assert found.source == said and ".pdf" not in found.text
