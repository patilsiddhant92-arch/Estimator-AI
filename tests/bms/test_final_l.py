"""FINAL-L (REVIEW-FINAL6 part B, B1 to B4): the id detector's sheet lists, the dossier's own where forms, the
small false refusals, and two disguises of an issued id.

- B1: after a sheet word, a list of sheet numbers keeps every member sheet-listed, whatever order: "sheets M-101
  and S201" as "sheets S201 and M-101".
- B2: `source_sheets()` (and `ref_sheets`) read the sheet the dossier's own note and sequence wheres name second:
  "GENERAL NOTES 3, S201, Structural.pdf page 3", "sequence section “VALVES”, S201, Structural.pdf page 3".
- B3: "sheet (S201)", "sheet-S201", "S201; S202", "S201 & S202", "sht. S201" and a long gap of white space between
  the sheet word and the id are sheet-listed forms.
- B4: a Cyrillic or Greek look-alike letter or digit reads as its ASCII form in the detection copy, and a zero-width
  character glued between a word and an id is a token boundary there; the renderer cuts the original characters.

Every probe goes through the real intake (`ai._check_system`), the validator and the renderer on one job (the
reviewer's `_verdicts`). Tests named `test_guard_...` pin behaviour unchanged from rebuild f5394a9 (they pass there);
every other test fails there. Invented fixture only."""
from __future__ import annotations

import re
import time
import unicodedata

import pytest

from bms import ai
from bms.citations import SourceIds, job_ids, job_sheets, job_tags, ref_sheets, source_sheets
from bms.render import render
from bms.validate import RULE, validate

from test_review_final3 import SAMPLE, ZERO_WIDTH
from test_review_final6_ids import ACCEPTED, NO_PLACE, REFUSED, SOURCE, _job_with, _verdicts

ZW = "​"
# the test's own reading of a look-alike (an oracle independent of the detector's table)
LOOK = {"Ѕ": "S", "ѕ": "s", "Ϲ": "C", "С": "C", "с": "c", "І": "I", "Ι": "I",
        "О": "0", "Ο": "0", "о": "0", "і": "1"}


def _seen(text: str) -> str:
    """What the eye reads: look-alikes as ASCII, zero-width characters out, NFKC."""
    text = "".join(LOOK.get(c, c) for c in text if c not in ZERO_WIDTH)
    return unicodedata.normalize("NFKC", text)


def _shown(job, token: str) -> bool:
    """`token` reads in EF's printed lines to the eye, glued to a word or not."""
    printed = _seen(" | ".join(l.text for l in render(job, SAMPLE).lines if l.system_key == "EF"))
    return re.search(rf"{re.escape(token)}(?![0-9])", printed, re.IGNORECASE) is not None


def _disguised(kind, probe, token, source=SOURCE):
    """`_verdicts`, with the render column read by the eye (`_shown`)."""
    intake, validator, _ = _verdicts(kind, probe, token, source)
    return intake, validator, "prints" if _shown(_job_with(kind, probe, source), token) else "cut"


# ---- B1: a sheet list keeps every member, whatever order -----------------------------------------------------------

B1 = [
    ("text", "Valves on sheets M-101 and S201.", "S201"),
    ("text", "Valves on sheets M-101, M-102 and S202.", "S202"),
    ("text", "Valves on sheets M-101 and S201 and S202.", "S202"),
    ("text", "Valves on sheets M-101.00/S201.", "S201"),
    ("text", "Valves on sheet M2 or S201.", "S201"),
    ("name", "Valve sheets M-101 and S201", "S201"),
]


@pytest.mark.parametrize("kind, probe, token", B1, ids=[f"{p[0]}-{n}" for n, p in enumerate(B1)])
def test_a_source_sheet_in_a_sheet_list_after_a_non_id_sheet_number_is_a_sheet(kind, probe, token):
    assert _verdicts(kind, probe, token) == ACCEPTED


@pytest.mark.parametrize("probe, token", [
    ("Valves on M-101 and S201.", "S201"),                  # no sheet word: a bare source id
    ("Valves on sheets M-101 and S141.", "S141"),           # issued and no source sheet: a sheet word changes nothing
    ("Valves on sheets M-101 and see S201.", "S201"),       # the list is broken
])
def test_guard_a_sheet_list_never_carries_past_its_own_members(probe, token):
    assert _verdicts("text", probe, token) == REFUSED


# ---- B2: the dossier's own note and sequence wheres name their sheet -----------------------------------------------

def test_the_dossiers_note_and_section_wheres_give_their_sheet():
    found = source_sheets({"Q3": "sequence section “VALVES”, S201, Structural.pdf page 3",
                           "S7": "GENERAL NOTES 3, S202, Structural.pdf page 3",
                           "Q4": "sequence section “FANS, PUMPS”, C501, Structural.pdf page 4"})
    assert set(found) == {"S201", "S202", "C501"}
    assert ref_sheets([{"source_id": "Q3", "where": "sequence section “VALVES”, S201, Drawings.pdf page 5"}]) \
        == frozenset({"S201"})


def test_a_writer_copying_the_dossiers_note_where_exactly_is_accepted_and_keeps_its_sheet():
    where = "GENERAL NOTES 3, S201, Structural.pdf page 3"
    source = source_sheets({"S7": where})
    assert _verdicts("where", where, "S201", source) == ACCEPTED
    job = _job_with("where", where, source)
    # T-005e (ruling 15): the counts print on the "Qty (#)" lines, no "*Qty." note
    note = " ".join(l.text for l in render(job, SAMPLE).lines if l.system_key == "EF" and "Qty (" in l.text)
    assert "S201" in note


@pytest.mark.parametrize("sid, where", [
    ("S201", "GENERAL NOTES 3, S201, Structural.pdf page 3"),          # its own source id: not trusted
    ("S9", "Valve schedule, S201"),                                    # no file part after it
    ("S9", "Valve schedule S141 rows, S201, Structural.pdf page 3"),   # a label holding an id
])
def test_guard_a_second_place_sheet_needs_a_plain_label_and_a_file_part(sid, where):
    assert source_sheets({sid: where}) == ()


# ---- B3: the small false refusals ------------------------------------------------------------------------------

B3 = [
    ("text", "Valves per sheet (S201).", "S201"),
    ("text", "Valves per sheet-S201.", "S201"),
    ("text", "Valves per sheets S201; S202.", "S202"),
    ("text", "Valves per sheets S201 & S202.", "S202"),
    ("text", "Valves per sht. S201.", "S201"),
    ("text", "Valves per shts S201 and S202.", "S202"),
    ("text", "Valves per sheet" + " " * 40 + "S201.", "S201"),
    ("text", "Valves per sheet no.\n\n" + " " * 38 + "S201.", "S201"),
    ("name", "Valve sht S201", "S201"),
]


@pytest.mark.parametrize("kind, probe, token", B3, ids=[f"{p[0]}-{n}" for n, p in enumerate(B3)])
def test_the_small_sheet_forms_are_sheet_listed(kind, probe, token):
    assert _verdicts(kind, probe, token) == ACCEPTED


@pytest.mark.parametrize("probe, token", [
    ("Valves per sheet (S141).", "S141"),
    ("Valves per sheets S201; S141.", "S141"),
    ("Valves per sheets S201 & S141.", "S141"),
    ("Valves per sht. S141.", "S141"),
    ("Valves per sheet" + " " * 40 + "S141.", "S141"),
    ("Valves per sheet (see S201).", "S201"),
])
def test_guard_the_small_forms_never_make_an_issued_id_a_sheet(probe, token):
    assert _verdicts("text", probe, token) == REFUSED


# ---- B4: look-alike letters and zero-width glue -----------------------------------------------------------------

B4 = [
    ("text", "Valves per Ѕ141.", "S141"),               # Cyrillic capital DZE for S
    ("text", "Valves per ѕ141.", "S141"),               # its lower case
    ("text", "Valves per Ϲ101.", "C101"),               # Greek lunate sigma for C
    ("text", "Valves per С101.", "C101"),               # Cyrillic ES for C
    ("text", "Valves per S2О1.", "S201"),               # Cyrillic O for a zero
    ("text", "Valves per S14І.", "S141"),               # Cyrillic I for a one
    ("text", "Valves per" + ZW + "S141.", "S141"),           # zero-width glue after a word
    ("text", "Valves per⁠S141.", "S141"),
    ("text", "Valves per﻿S141 and C101.", "S141"),
    ("text", "Valves per sheet S201,Ѕ141.", "S141"),
    ("name", "Valve per Ѕ141", "S141"),
    ("name", "Valve per" + ZW + "S141", "S141"),
    ("where", "Ѕ141, Structural.pdf page 3", "S141"),
    ("where", "Valve schedule per" + ZW + "S141", "S141"),
    ("where", "Structural.pdf page 3, Ι1", "I1"),               # Greek IOTA for I
    ("refwhere", "Ѕ141, Structural.pdf page 3", "S141"),
    ("refwhere", "Valve schedule per" + ZW + "S141", "S141"),
]


@pytest.mark.parametrize("kind, probe, token", B4, ids=[f"{p[0]}-{n}" for n, p in enumerate(B4)])
def test_a_disguised_issued_id_is_refused_and_never_shows(kind, probe, token):
    job = _job_with(kind, probe)
    assert token.upper() in {i.upper() for i in job_ids(job)}
    assert _disguised(kind, probe, token) == REFUSED


@pytest.mark.parametrize("where", [p[1] for p in B4 if p[0] == "where"])
def test_a_disguised_id_never_shows_in_the_quantity_note(where):
    job = _job_with("where", where)
    # T-005e (ruling 15): the counts print on the "Qty (#)" lines, no "*Qty." note
    note = " ".join(l.text for l in render(job, SAMPLE).lines if l.system_key == "EF" and "Qty (" in l.text)
    assert not re.search(r"[SQIFC]\d", _seen(note), re.IGNORECASE), note


def test_a_disguised_source_sheet_in_a_where_prints_as_its_ascii_sheet():
    where = "Ѕ201, Structural.pdf page 3"
    assert _verdicts("where", where, "S201") == ACCEPTED
    # T-005e (ruling 15): the counts print on the "Qty (#)" lines, no "*Qty." note
    note = " ".join(l.text for l in render(_job_with("where", where), SAMPLE).lines
                    if l.system_key == "EF" and "Qty (" in l.text)
    assert "S201" in note and "Ѕ" not in note


def test_the_renderer_cuts_the_original_characters_of_a_disguised_id():
    ids = SourceIds.of(["S141", "C101"])
    assert ids.without_issued("Valves per Ѕ141 now.") == "Valves per now."
    assert ids.without_issued("Valves per S2О1 now.") == "Valves per S2О1 now."   # S201: not issued here
    cut = ids.without_issued("Valves per" + ZW + "S141 now.")
    assert "S141" not in cut and cut.startswith("Valves per")
    found = ids.scan("per Ѕ141")
    assert [(f.token, f.start, f.end, f.kind) for f in found] == [("S141", 4, 8, "issued")]
    found = ids.scan("per" + ZW + "S141")
    assert [(f.token, f.start, f.end, f.kind) for f in found] == [("S141", 4, 8, "issued")]


@pytest.mark.parametrize("text", [
    "Valves per S" + ZW + "141.",                             # zero-width inside the id: still glued
    "Valves per S1" + ZW + "41.",
])
def test_guard_a_zero_width_inside_an_id_still_glues_it(text):
    assert SourceIds.of(["S141"]).refusal(text)


@pytest.mark.parametrize("text", [
    "Контроль by others.",   # a Cyrillic word with no id in it
    "Valves at 20 µA.",
    "Fan Σ-1 serves the lab.",
])
def test_guard_plain_words_with_foreign_letters_name_no_id(text):
    ids = SourceIds.of(["S141", "C101", "S1"])
    assert ids.refusal(text) == ""


def test_the_scan_stays_linear_on_long_sheet_lists():
    ids = SourceIds.of(["S141"], source_sheets=["S201"])
    small = "Valves on sheets " + "M-101 and " * 2_000 + "S201. per Ѕ141 " * 50
    large = "Valves on sheets " + "M-101 and " * 40_000 + "S201. per Ѕ141 " * 1_000
    def best(text):
        times = []
        for _ in range(3):
            start = time.perf_counter()
            ids.scan(text)
            times.append(time.perf_counter() - start)
        return min(times)

    one, many = best(small), best(large)               # 20 times the text: linear is about 20 times the time
    found = ids.scan(large)
    assert found[0].kind == "sheet" and found[1].kind == "issued"
    assert many < max(one, 0.005) * 60
