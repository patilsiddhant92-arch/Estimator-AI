"""REVIEW-FINAL3 (review of record for lead/final-c at rebuild 70a4672). Invented fixture and invented job folder only.

(1) The tightened L-D rule: a probe table run through the real intake (`ai._check_system`), the validator and the
    renderer on one job, so I, T and K are the same in all three; each probe must be refused, must_fix and cut, or
    accepted, silent and printed. Strict xfails record what does not agree.
(2) `_ids_in_changes`: an id in each client field of a hand-edited Change.
(3) The start-over note on a later run.
(4) tests/timing.py against quadratic stand-ins and noisy linear work.
(5) tests/procs.py and the autouse retry with real child processes."""
from __future__ import annotations

import dataclasses
import json
import random
import re
import subprocess
import sys
import time
import unicodedata
from dataclasses import replace
from pathlib import Path

import pytest

from bms import ai, run
from bms.citations import SourceIds, job_ids, job_sheets, job_tags
from bms.model import Assumption, Clarification, Count, Decision, Family, Job, OtherCount, Ref
from bms.playbook import load_playbook
from bms.render import render
from bms.validate import RULE, validate

from test_review_final import _cards, _decision, _drive
from test_run import job_folder  # noqa: F401  (job_folder is a fixture)

FIX = Path(__file__).resolve().parent / "fixtures"
SAMPLE = load_playbook(FIX / "sample_playbook")
EXTRA = ("S141", "C101", "S201", "S202", "S203", "F101", "S2010")     # issued ids the probes use
ZERO_WIDTH = "​‌‍⁠﻿­"


def _base() -> Job:
    return Job.from_dict(json.loads((FIX / "sample_job.json").read_text(encoding="utf-8")))


def _job(sheets=(), tag=None) -> Job:
    """The sample job with EXTRA issued (refs on a VRF device, which make no sheet), `sheets` made known (K: planner
    sequence refs whose where names them after a sheet word) and, when given, `tag` a tag of the job."""
    job = _base()

    def edit(s):
        if s.key != "VRF":
            return s
        d = s.devices[0]
        s = replace(s, devices=(replace(d, refs=d.refs + tuple(Ref(i, "q", "M-101, Drawings.pdf page 2")
                                                                for i in EXTRA)),) + s.devices[1:],
                    sequence_refs=s.sequence_refs + tuple(Ref("Q2", "q", f"Sheet {k}, Drawings.pdf page 5")
                                                          for k in sheets))
        if tag:
            s = replace(s, families=s.families + (Family("Cabinet", (tag,), Count(1)),))
        return s
    return replace(job, systems=tuple(edit(s) for s in job.systems))


def _with_note(job: Job, text: str) -> Job:
    return replace(job, systems=tuple(replace(s, clarifications=(Clarification("note", text),)) if s.key == "EF"
                                      else s for s in job.systems))


def _with_other_count(job: Job, where: str) -> Job:
    """EF's first device counted 2 on M-001 and 1 by a second source whose where the writer typed (R-4)."""
    def edit(s):
        if s.key != "EF":
            return s
        quantity = Count(2, (Ref("S6", "q", "M-001, Drawings.pdf page 1"),), (OtherCount(1, Ref("Q2", "q", where)),))
        return replace(s, devices=(replace(s.devices[0], quantity=quantity),) + s.devices[1:])
    return replace(job, systems=tuple(edit(s) for s in job.systems))


def _prints(job: Job, token: str) -> bool:
    printed = " | ".join(l.text for l in render(job, SAMPLE).lines if l.system_key == "EF")
    flat = unicodedata.normalize("NFKC", "".join(c for c in printed if c not in ZERO_WIDTH))
    return re.search(rf"(?<![A-Za-z0-9]){re.escape(token)}(?![0-9])", flat, re.IGNORECASE) is not None


def _verdicts(kind: str, probe: str, token: str, sheets=(), tag=None) -> tuple[str, str, str]:
    """(intake, validator, render) on one job: refused/accepted, must_fix/none, cut/prints."""
    job = _job(sheets, tag)
    job = _with_note(job, probe) if kind == "text" else _with_other_count(job, probe)
    system = job.system("EF")
    written, _ = ai._check_system(system.to_dict(), system, None, frozenset(job_ids(job)), (), (), [],
                                  job_tags(job), job_ids(job), tuple(job_sheets(job)))
    severities = [f.severity for f in validate(job, SAMPLE) if f.rule == RULE["ids"] and f.system_key == "EF"]
    return ("refused" if written is None else "accepted", "must_fix" if "must_fix" in severities else "none",
            "prints" if _prints(job, token) else "cut")


REFUSED = ("refused", "must_fix", "cut")
ACCEPTED = ("accepted", "none", "prints")

AGREEING = [
    # client text (a clarification); (kind, probe, the token looked for in print, K, a tag, the verdict)
    ("text", "Valves per sheet S141.", "S141", (), None, REFUSED),
    ("text", "Valves per sheet S141.", "S141", ("S141",), None, ACCEPTED),
    ("text", "Valves per Sheet C101.", "C101", (), None, REFUSED),
    ("text", "Valves per Sheet C101.", "C101", (), "C101", ACCEPTED),             # C101 is a real tag too
    ("text", "Valves per sheet S141.", "S141", (), "S141", ACCEPTED),             # S141 is a real tag too
    ("text", "See sheet S12 for the valves.", "S12", ("S12",), None, ACCEPTED),
    ("text", "See sheet S12 for the valves.", "S12", (), None, REFUSED),
    ("text", "Valves on sheets S201 thru S203.", "S203", ("S201", "S202", "S203"), None, ACCEPTED),
    ("text", "Valves on sheets S201 thru S203.", "S201", (), None, REFUSED),
    ("text", "Valves on sheets S201 thru S299.", "S299", ("S201",), None, ACCEPTED),  # unissued end of a range
    ("text", "Valves on sheets C2 thru C9.", "C9", (), None, ACCEPTED),
    ("text", "Valves per sheet M-101.", "M-101", (), None, ACCEPTED),
    ("text", "Valves per SHEET S141.", "S141", (), None, REFUSED),
    ("text", "Valves per sheet s141.", "s141", (), None, REFUSED),
    ("text", "Valves per dwg. S141.", "S141", (), None, REFUSED),
    ("text", "Valves per sheet: S141.", "S141", (), None, REFUSED),
    ("text", "Valves per sheet-S141.", "S141", (), None, REFUSED),
    ("text", "Valves per (sheet S141).", "S141", (), None, REFUSED),
    ("text", "Valves per sheet Ｓ141.", "S141", (), None, REFUSED),          # full-width S
    ("text", "Valves per sheet S​141.", "S141", (), None, REFUSED),         # zero-width space
    ("text", "Valves per sheet Ｓ141.", "S141", ("S141",), None, ACCEPTED),
    ("text", "Valves per sheets S12, S141 and S13.", "S141", ("S12", "S13"), None, REFUSED),
    ("text", "Valves per sheets S12 and S13.", "S13", (), None, REFUSED),
    ("text", "Valves per sheet S141A.", "S141A", (), None, ACCEPTED),             # unissued
    ("text", "Valves per sheet F101.", "F101", (), None, REFUSED),
    # a where the writer typed on a device quantity's other count (its place prints in the count note)
    ("where", "Sheet S141, Mechanical.pdf page 3", "S141", (), None, REFUSED),
    ("where", "Sheet S141, Mechanical.pdf page 3", "S141", ("S141",), None, ACCEPTED),
    ("where", "Sheet M401, Mechanical.pdf page 3", "M401", (), None, ACCEPTED),  # honest, no issued id
    ("where", "Sheet M-101, Mechanical.pdf page 3", "M-101", (), None, ACCEPTED),
    ("where", "M-101, Mechanical.pdf page 3", "M-101", (), None, ACCEPTED),
    ("where", "Sheet C2, Mechanical.pdf page 3", "C2", (), None, ACCEPTED),
    ("where", "sheet S141, Mechanical.pdf page 3", "S141", (), None, REFUSED),
    ("where", "Dwg S141, Mechanical.pdf page 3", "S141", (), None, REFUSED),
    ("where", "Mechanical schedule, sheet S141", "S141", (), None, REFUSED),
    ("where", "Sheet S141 (Mechanical), Mechanical.pdf page 3", "S141", (), None, REFUSED),
    ("where", "Sheet S１４１, Mechanical.pdf page 3", "S141", (), None, REFUSED),  # full-width digits
    ("where", "Sheet C101, Civil.pdf page 1", "C101", (), None, REFUSED),
    ("where", "Sheets S201 thru S203, Structural.pdf page 4", "S201", ("S201", "S202", "S203"), None, ACCEPTED),
    ("where", "Sheets S201 thru S203, Structural.pdf page 4", "S201", (), None, REFUSED),
    ("where", "Sheet F101, Fire.pdf page 2", "F101", (), None, REFUSED),
]


@pytest.mark.parametrize("kind, probe, token, sheets, tag, verdict", AGREEING)
def test_intake_validator_and_render_agree_on_each_probe(kind, probe, token, sheets, tag, verdict):
    assert _verdicts(kind, probe, token, sheets, tag) == verdict


@pytest.mark.parametrize("where", ["Sheet Ｓ141, Mechanical.pdf page 3", "Ｓ141, Mechanical.pdf page 3",
                                   "Sheet S​141, Mechanical.pdf page 3"])
def test_f1_a_disguised_issued_id_in_a_writers_where_never_prints(where):
    assert _verdicts("where", where, "S141")[2] == "cut"


@pytest.mark.parametrize("where, token", [("sheet s141, Mechanical.pdf page 3", "s141"),
                                          ("Sheet: S141, Mechanical.pdf page 3", "S141"),
                                          ("Sheet No. S141, Mechanical.pdf page 3", "S141"),
                                          ("Sheet S2010, Structural.pdf page 4", "S2010")])
def test_f3_every_sheet_form_of_an_issued_id_in_a_where_is_refused(where, token):
    assert _verdicts("where", where, token) == REFUSED


def test_f4_the_where_refusal_points_to_a_form_the_intake_accepts():
    job = _with_other_count(_job(), "Sheet S201, Structural.pdf page 4")     # S201 a real structural sheet
    system = job.system("EF")
    written, problems = ai._check_system(system.to_dict(), system, None, frozenset(job_ids(job)), (), (), [],
                                         job_tags(job), job_ids(job), tuple(job_sheets(job)))
    assert written is None
    said = " ".join(p for p in problems if "S201" in p)
    assert "the place the evidence gives" in said, said


def test_f5_a_tag_after_a_sheet_word_is_treated_alike_in_text_and_in_a_where():
    assert _verdicts("text", "Valves per Sheet C101.", "C101", (), "C101") == ACCEPTED
    assert _verdicts("where", "Sheet C101, Civil.pdf page 1", "C101", (), "C101") == ACCEPTED


def test_where_issued_stays_linear():
    from timing import grows_linearly
    ids = SourceIds.of([f"S{n}" for n in range(1, 400)], [], [f"S{n}" for n in range(1, 400, 2)])
    assert grows_linearly(lambda n: ids.where_issued("Sheets " + " and ".join(f"S{k % 399 + 1}" for k in range(n))
                                                     + ", Drawings.pdf page 1"), 2000)


# ---- (2) a hand-edited Change ------------------------------------------------------------------------------------

def _changed(job: Job, **fields) -> tuple[Job, Decision]:
    system = job.system("EF")
    device = dataclasses.replace(system.devices[0], flag="none", **fields)
    decision = Decision("EF", "change", device.id, device=device, was=system.devices[0])
    return job.with_system(dataclasses.replace(system, devices=(device,) + system.devices[1:])), decision


@pytest.mark.parametrize("fields", [
    {"name": "DDC Controller per Ｓ6"},                                          # full-width, in the name
    {"assumption": Assumption("one per fan per sheet S6", "the sequence says so")},  # a sheet word, in what
    {"assumption": Assumption("one per fan", "see S​6")},                      # zero-width, in why
    {"name": "DDC Controller per S6", "assumption": Assumption("one per fan", "per S7")},
])
def test_a_hand_edited_change_with_an_id_in_any_client_field_gets_the_card_and_matches_the_validator(fields):
    job, decision = _changed(_base(), **fields)
    found = run._ids_in_changes(job, [decision])
    assert [(d, device_id) for d, device_id, _ in found] == [(decision, "EF.d1")]
    must_fix = [f for f in validate(job, SAMPLE) if f.rule == RULE["ids"] and f.severity == "must_fix"]
    assert must_fix and all(f.device_id == "EF.d1" for f in must_fix)


def test_f2_a_hand_edited_change_whose_where_names_an_issued_id_gets_the_card():
    quantity = Count(2, (Ref("S6", "q", "M-001, Drawings.pdf page 1"),),
                     (OtherCount(1, Ref("Q2", "q", "Sheet S6, Mechanical.pdf page 3")),))
    job, decision = _changed(_base(), quantity=quantity)
    assert [f.severity for f in validate(job, SAMPLE) if f.rule == RULE["ids"] and f.device_id == "EF.d1"] \
        == ["must_fix"]
    assert run._ids_in_changes(job, [decision]) != []


# ---- (3) starting over ------------------------------------------------------------------------------------------

START_OVER = "to start over, delete both decisions.json and decisions history.json"


def test_the_start_over_note_stays_one_line_on_every_later_run_and_goes_once_decisions_json_is_back(
        job_folder, tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out, cache = tmp_path / "out", tmp_path / "cache"
    _drive(job_folder, out, cache, [])
    sensor = next(c for c in _cards(out) if c["level"] == "device")
    (out / "decisions.json").write_text(json.dumps([_decision(sensor, "accept")]), encoding="utf-8")
    run.estimate(job_folder, out, cache, "chat")
    (out / "decisions.json").unlink()
    for _ in range(2):                                   # still there on each run while decisions.json is gone
        notes = [m for m in run.estimate(job_folder, out, cache, "chat").messages if START_OVER in m]
        assert len(notes) == 1, notes
    (out / "decisions.json").write_text("[]", encoding="utf-8")        # an empty save: the file is there again
    assert not [m for m in run.estimate(job_folder, out, cache, "chat").messages if START_OVER in m]


# ---- (4) the growth check ----------------------------------------------------------------------------------------

def _quadratic(n):
    total = 0
    for i in range(n):
        for j in range(n):
            total += j
    return total


@pytest.mark.parametrize("n", [20, 120])
def test_grows_linearly_fails_quadratic_work_from_any_starting_size(n):
    from timing import grows_linearly
    assert not grows_linearly(_quadratic, n, attempts=1)


def test_grows_linearly_raises_the_base_until_a_hidden_quadratic_part_shows():
    from timing import grows_linearly

    def mostly_linear(n):                                # a linear part 50 times the quadratic one at n = 50
        total = 0
        for i in range(50 * n):
            total += i
        return total + _quadratic(n)
    assert not grows_linearly(mostly_linear, 50, attempts=1)


def test_grows_linearly_passes_linear_work_under_random_load():
    from timing import grows_linearly
    rng = random.Random(7)

    def noisy(n):
        total = 0
        for i in range(n):
            total += i
        if rng.random() < 0.3:                           # a burst of load on about a third of the runs
            time.sleep(0.02)
        return total
    assert grows_linearly(noisy, 200_000)


# ---- (5) the retry with real children ----------------------------------------------------------------------------

_CHILD = "import os, sys; open(sys.argv[1], 'a').write('x'); os._exit(int(sys.argv[2]))"


def test_a_real_child_failing_with_the_resource_code_is_run_three_times_then_reported(tmp_path):
    marks = tmp_path / "runs.txt"
    done = subprocess.run([sys.executable, "-c", _CHILD, str(marks), "-1073741502"])
    assert done.returncode == 3221225794 and marks.read_text() == "xxx"    # returned, never hidden
    marks.write_text("")
    with pytest.raises(subprocess.CalledProcessError) as raised:
        subprocess.run([sys.executable, "-c", _CHILD, str(marks), "-1073741502"], check=True)
    assert raised.value.returncode == 3221225794 and marks.read_text() == "xxx"


def test_a_real_child_failing_otherwise_runs_once_and_check_true_raises_with_its_output(tmp_path):
    marks = tmp_path / "runs.txt"
    with pytest.raises(subprocess.CalledProcessError) as raised:
        subprocess.run([sys.executable, "-c", _CHILD + "", str(marks), "1"], check=True, capture_output=True)
    assert raised.value.returncode == 1 and marks.read_text() == "x"
    with pytest.raises(subprocess.TimeoutExpired):
        subprocess.run([sys.executable, "-c", "import time; time.sleep(5)"], timeout=0.5)


def test_the_retry_is_one_layer_and_undone_with_the_tests_monkeypatch(monkeypatch):
    wrapped = subprocess.run
    assert wrapped.retries_resource_errors
    original = wrapped.__wrapped__
    assert not getattr(original, "retries_resource_errors", False)       # never a wrapper around a wrapper
    monkeypatch.undo()                                                    # what pytest does at teardown
    assert subprocess.run is original
