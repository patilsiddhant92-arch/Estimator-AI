"""T-005d regression tests from an invented copy of the 26-0544 evidence defects (NOTES 2026-10-11 rule 4), read from
tests/bms/fixtures/t005d_evidence.json:

- a title-block phrase naming the system made every plan sheet a note of the unit and flooded the notes cap, so the
  control diagram sheet (its FUTURE item) never reached the writer;
- the general notes sheet's BMS notes sat past the 8,000-character cut of a sheet's text.
Invented fixtures only; no AI is asked."""
from __future__ import annotations

import json
from pathlib import Path

from estimator.writing import dossier as dossier_module
from estimator.writing.dossier import Dossier

from bms import ai
from bms.model import Count, Family, FrontEnd, System

F = json.loads((Path(__file__).resolve().parent / "fixtures" / "t005d_evidence.json").read_text("utf-8"))
FILLER = " ".join([F["filler_words"]] * F["filler_repeat"])
DOC = F["document"]


def _sheet_line(s: dict, body: str) -> str:
    return f"[S{s['sid']}] {s['number']}, {DOC} page {s['page']} {s['title']}: {F['title_block']} {body}"


def _general_notes_text() -> str:
    g = F["general_notes"]
    return " ".join([F["title_block"]] + [FILLER] * g["filler_blocks"] + [g["bms_note"]])


def _dossier() -> Dossier:
    g, c = F["general_notes"], F["controls_sheet"]
    lines = [f"JOB DOSSIER — {F['job']}", "== 7. NOTES ==", "--- 7c PLAN SHEET TEXT ---",
             "(Each mechanical, controls and plumbing sheet's own text, as printed.)",
             f"[S{g['sid']}] {g['number']}, {DOC} page {g['page']} {g['title']}: {_general_notes_text()}"]
    lines += [_sheet_line(s, FILLER) for s in F["plain_plans"]]
    lines += [_sheet_line(s, f"{FILLER} {F['keynote']} {FILLER}") for s in F["tagged_plans"]]
    lines.append(f"[S{c['sid']}] {c['number']}, {DOC} page {c['page']} {c['title']}: {c['text']}")
    return Dossier(F["job"], "\n".join(lines) + "\n", (), {}, (), {}, {}, {}, {})


def _unit() -> System:
    return System(key="AHU", name="Air Handling Units", shape="", control="field",
                  families=(Family("Air Handling Unit", (F["unit_tag"],), Count(1)),), sequence_refs=())


def test_fixture_the_general_notes_sheet_is_long_enough_to_be_cut_at_8000():
    text = _general_notes_text()
    assert text.index(F["general_notes"]["bms_note"]) > 8_000           # the pattern the fix is about


# ---- defect 1: the title-block phrase floods the notes cap -----------------------------------------------------------

def test_fixture_the_control_diagram_reaches_the_writer_before_the_plan_sheets():
    c = F["controls_sheet"]
    text = ai.evidence_for(_unit(), _dossier())
    assert f"[S{c['sid']}] {c['number']}" in text and F["future_quote"] in text
    controls = text.split("Controls sheets that name it", 1)[1].split("Notes that name it:", 1)[0]
    assert f"[S{c['sid']}]" in controls                             # its own block, whole, before the notes
    assert text.index("Controls sheets that name it") < text.index(f"[S{F['tagged_plans'][0]['sid']}]")


def test_fixture_a_sheet_named_only_by_its_title_block_is_not_a_note_of_the_unit():
    text = ai.evidence_for(_unit(), _dossier())
    for s in F["plain_plans"]:
        assert f"[S{s['sid']}]" not in text


def test_fixture_every_tagged_plan_fits_the_notes_block_as_excerpts():
    text = ai.evidence_for(_unit(), _dossier())
    assert all(f"[S{s['sid']}]" in text for s in F["tagged_plans"])
    assert "more passages name it" not in text
    first = next(l for l in text.splitlines() if l.startswith(f"[S{F['tagged_plans'][0]['sid']}]"))
    assert F["keynote"] in first and len(first) < 1_500


def test_fixture_the_future_item_is_listed_for_the_writer():
    text = ai.evidence_for(_unit(), _dossier())
    part = text.split("Items its passages mark FUTURE", 1)[1]
    assert f"[S{F['controls_sheet']['sid']}]" in part and F["future_quote"] in part


# ---- defect 2: the BMS notes past the 8,000-character cut -------------------------------------------------------------

def test_fixture_the_bms_notes_past_8000_characters_stay_in_the_sheet_text():
    g = F["general_notes"]

    class Sheet:
        document, page, number, title = DOC, g["page"], g["number"], g["title"]

    key = (DOC, g["page"])
    lines = dossier_module._sheet_text_lines({key: Sheet()}, {key: _general_notes_text()}, dossier_module._Ids(),
                                             dossier_module._SheetText(), "more sheet")
    assert g["bms_note"] in lines[0]


def test_fixture_the_front_end_writer_gets_the_bms_notes():
    front = FrontEnd(mode="extend-existing", existing_system_name="Zebra Controls", lines=("graphics",))
    text = ai.front_end_evidence(front, _dossier(), (), None)
    assert "CONNECT THE NEW AIR HANDLERS TO THE EXISTING ZEBRA CONTROLS BMS OVER BACNET MS/TP" in text
