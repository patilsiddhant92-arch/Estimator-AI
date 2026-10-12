"""REVIEW-FINAL6 (reviewer of record for lead/final-j at rebuild f5394a9): the job's source sheets
(`Job.source_sheets`) are a known sheet only in a where and right after a sheet word in client text; a bare issued
id in client text stays refused. A probe table of 50+ rows through the real intake (`ai._check_system`), the
validator and the renderer on one job, plus the quantity note (read as a where) and how the source sheets are
derived. Rows are guards (they pass on f5394a9) unless marked xfail. Invented fixture only."""
from __future__ import annotations

import re
from dataclasses import replace

import pytest

from bms import ai
from bms.citations import ONE_ID, job_ids, job_sheets, job_tags, source_sheets
from bms.model import Ref
from bms.render import render
from bms.validate import RULE, validate

from test_review_final3 import SAMPLE, _job, _prints, _with_note, _with_other_count

SOURCE = ("S201", "S202")             # the job's source sheets; both are issued ids of the test job too
REFUSED = ("refused", "must_fix", "cut")
ACCEPTED = ("accepted", "none", "prints")
NO_PLACE = ("accepted", "none", "cut")  # accepted, and not printed: a where that is no place
SILENT = ("accepted", "none", "cut")    # a device ref's own where: accepted, never printed


def _with_name(job, text):
    def edit(s):
        if s.key != "EF":
            return s
        return replace(s, devices=(replace(s.devices[0], name=text),) + s.devices[1:])
    return replace(job, systems=tuple(edit(s) for s in job.systems))


def _with_ref_where(job, where):
    def edit(s):
        if s.key != "EF":
            return s
        d = s.devices[0]
        return replace(s, devices=(replace(d, refs=d.refs + (Ref("Q2", "q", where),)),) + s.devices[1:])
    return replace(job, systems=tuple(edit(s) for s in job.systems))


_PUT = {"text": _with_note, "name": _with_name, "where": _with_other_count, "refwhere": _with_ref_where}


def _job_with(kind, probe, source=SOURCE):
    return _PUT[kind](replace(_job(), source_sheets=tuple(source)), probe)


def _verdicts(kind, probe, token, source=SOURCE):
    job = _job_with(kind, probe, source)
    system = job.system("EF")
    written, _ = ai._check_system(system.to_dict(), system, None, frozenset(job_ids(job)), (), (), [],
                                  job_tags(job), job_ids(job), tuple(job_sheets(job)), tuple(job.source_sheets))
    severities = [f.severity for f in validate(job, SAMPLE) if f.rule == RULE["ids"] and f.system_key == "EF"]
    return ("refused" if written is None else "accepted", "must_fix" if "must_fix" in severities else "none",
            "prints" if _prints(job, token) else "cut")


PROBES = [
    # client text: sheet lists carried by and / or / , / to / thru / a dash / a slash
    ("text", "Valves per sheet S201 or S202.", "S202", ACCEPTED),
    ("text", "Valves per sheet S201/S202.", "S202", ACCEPTED),
    ("text", "Valves per sheet S201-S202.", "S202", ACCEPTED),
    ("text", "Valves per sheet S201 to S202.", "S202", ACCEPTED),
    ("text", "Valves per sheets S201 thru S202.", "S202", ACCEPTED),
    ("text", "Valves per SHEETS S201 AND S202.", "S202", ACCEPTED),
    ("text", "Valves on sheets S201 and M-101.", "S201", ACCEPTED),
    # client text: a sheet word right before it, in its forms
    ("text", "Valves per sheet#S201.", "S201", ACCEPTED),
    ("text", "Valves per sheet  S201.", "S201", ACCEPTED),
    ("text", "Valves per sheet\nS201.", "S201", ACCEPTED),
    ("text", "Valves per dwg S201.", "S201", ACCEPTED),
    ("text", "Valves per sheet no S201.", "S201", ACCEPTED),
    ("text", "Valves per sheet S201's notes.", "S201", ACCEPTED),
    ("text", "Valves per sheet S201.", "S201", ACCEPTED),                 # no-break space
    ("text", "Valves per ｓｈｅｅｔ S201.", "S201", ACCEPTED),  # full-width "sheet"
    ("text", "Sheet S201 valves.", "S201", ACCEPTED),
    ("text", "Valves per cut sheet S201.", "S201", ACCEPTED),               # by the ruling: any sheet word
    # client text: tokens that are no source sheet
    ("text", "Valves per sheet S201A.", "S201A", ACCEPTED),                 # unissued, after a sheet word
    ("text", "Valves per sheet S20.", "S20", ACCEPTED),
    ("text", "Valves per sheet S-201.", "S-201", ACCEPTED),                 # no id shape
    ("text", "Valves per sheet S2010.", "S2010", REFUSED),                  # issued, no source sheet
    ("text", "Valves per sheets S201,S202,S203.", "S203", REFUSED),
    ("text", "Valves per sheet S201, S141.", "S141", REFUSED),
    # client text: a bare source sheet stays an issued id, however it is dressed
    ("text", "Valves per sheet S201, and see S202.", "S202", REFUSED),     # the list is broken
    ("text", "Valves per sheet S201 and per S202.", "S202", REFUSED),
    ("text", "Valves per sheet S201 (S202).", "S202", REFUSED),
    ("text", "Valves per sheets S201,                                  S202.", "S202", REFUSED),   # past the window
    ("text", "Valves per the S201 sheet.", "S201", REFUSED),
    ("text", "Valves per datasheet S201.", "S201", REFUSED),                # "sheet" inside a word
    ("text", "Valves per worksheet S201.", "S201", REFUSED),
    ("text", "Valves per sheet [S201].", "S201", REFUSED),                  # the ledger's own bracket form
    ("text", "Valves per drawing S201.", "S201", REFUSED),                  # "drawing" names a picture id
    # a device's name is client text too
    ("name", "Valve per sheet S201", "S201", ACCEPTED),
    ("name", "Valve sheet S201 and S202", "S202", ACCEPTED),
    ("name", "Valve per S201", "S201", REFUSED),
    ("name", "Valve S202", "S202", REFUSED),
    # a typed where (an other count's): a source sheet is a sheet wherever it stands
    ("where", "Structural.pdf page 3, S201", "S201", ACCEPTED),
    ("where", "S201", "S201", ACCEPTED),
    ("where", "per S201", "S201", ACCEPTED),
    ("where", "S201 and S202", "S201", ACCEPTED),
    ("where", "Valve schedule mentions s201 twice", "s201", ACCEPTED),
    ("where", "GENERAL NOTES 3, S201, Structural.pdf page 3", "S201", ACCEPTED),
    ("where", "S201 and S141", "S141", REFUSED),
    ("where", "S201-S141", "S141", REFUSED),
    ("where", "Valve schedule, S141", "S141", REFUSED),
    ("where", "Valve schedule S141 rows, Structural.pdf page 3", "S141", REFUSED),
    ("where", "Ledger S201", "S201", NO_PLACE),                              # a ledger fact is no place
    ("where", "S201.png", "S201", NO_PLACE),                                 # a picture is no place
    ("where", "Structural.pdf page 3 (S201)", "S201", NO_PLACE),             # a bracketed part is read out
    ("where", "Valve schedule, S999", "S999", NO_PLACE),                     # its id-shaped part is no place
    # a device ref's own where: checked as a where, never printed
    ("refwhere", "S201, Structural.pdf page 3", "S201", SILENT),
    ("refwhere", "Structural schedule, S201", "S201", SILENT),
    ("refwhere", "S141, Structural.pdf page 3", "S141", REFUSED),
    ("refwhere", "S201 and S141", "S141", REFUSED),
]


@pytest.mark.parametrize("kind, probe, token, verdict", PROBES,
                         ids=[f"{p[0]}-{n}" for n, p in enumerate(PROBES)])
def test_guard_intake_validator_and_render_agree_on_a_source_sheet(kind, probe, token, verdict):
    assert _verdicts(kind, probe, token) == verdict


@pytest.mark.parametrize("kind, probe, token", [
    ("text", "Valves per sheet S201.", "S201"),
    ("where", "S201, Structural.pdf page 3", "S201"),
    ("where", "GENERAL NOTES 3, S201, Structural.pdf page 3", "S201"),
])
def test_guard_with_no_source_sheet_an_issued_id_is_refused_everywhere(kind, probe, token):
    assert _verdicts(kind, probe, token, source=()) == REFUSED


def test_guard_probe_table_shape():
    """GUARD: the table itself only (its size and mix)."""
    assert len(PROBES) >= 40
    assert {p[0] for p in PROBES} == set(_PUT)
    assert sum(1 for p in PROBES if p[3] == REFUSED) >= 15


@pytest.mark.parametrize("where", [p[1] for p in PROBES if p[0] == "where"])
def test_guard_the_quantity_note_never_prints_an_id_that_is_no_known_sheet(where):
    """The quantity note is read as a where (`without_issued(..., place=True)`). It is built from places, the
    Playbook's labels and numbers; a writer's words reach it only through `place`, which drops any part holding an
    id-shaped token. So every id-shaped token it prints is a known sheet (here: a source sheet)."""
    job = _job_with("where", where)
    # T-005e (ruling 15): the counts print on the "Qty (#)" lines, no "*Qty." note
    note = " ".join(l.text for l in render(job, SAMPLE).lines if l.system_key == "EF" and ("Qty (" in l.text or "(Qty." in l.text))
    printed = {m.group(0).upper() for m in ONE_ID.finditer(note)}
    assert printed <= set(SOURCE), (where, note)


def test_a_source_sheet_after_another_sheet_in_a_sheet_list_is_a_sheet():
    """"Valves on sheets M-101 and S201." is the same list as "sheets S201 and M-101", which is accepted."""
    assert _verdicts("text", "Valves on sheets M-101 and S201.", "S201") == ACCEPTED


def test_the_dossiers_own_note_and_sequence_wheres_give_their_sheet_as_a_source_sheet():
    """The dossier writes "<block> <n>, <sheet>, <file> page <p>" for a note and "sequence section “…”, <sheet>,
    <file> page <p>" for a section (`dossier._place`). Their sheet is a sheet of the job; when it is also an issued
    id and no other source names it first, a writer copying that where exactly is refused, and the place is lost."""
    found = source_sheets({"Q3": "sequence section “VALVES”, S201, Structural.pdf page 3",
                           "S7": "GENERAL NOTES 3, S202, Structural.pdf page 3"})
    assert set(found) == {"S201", "S202"}


def test_guard_a_where_naming_its_own_source_id_first_gives_no_source_sheet():
    assert source_sheets({"S201": "S201, Structural.pdf page 3"}) == ()
    assert re.fullmatch(r"S\d+", source_sheets({"S9": "S201, Structural.pdf page 3"})[0])
