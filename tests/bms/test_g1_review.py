"""Reviewer's tests for T-G1 (the Demolition Scope). Every name here is invented."""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from bms.model import Job, Ref, Unit
from bms.playbook import load_playbook
from bms.render import render
from bms.takeoff import attach_demolition

FIXTURES = Path(__file__).resolve().parent / "fixtures"
PLAYBOOK = load_playbook(FIXTURES / "sample_playbook")
WORK = Ref("S7", "AHU-4 remove existing controls", "MD-102, Invented.pdf page 3")
SHOWN = Ref("S8", "AHU-5 to be removed", "MD-102, Invented.pdf page 3")


def _sample() -> Job:
    return Job.from_dict(json.loads((FIXTURES / "sample_job.json").read_text(encoding="utf-8")))


def _job(*units: Unit) -> Job:
    return attach_demolition(replace(_sample(), units=units, demolition=()))


def test_named_work_prints_its_line_red_last_and_the_evidence_row_cites_the_ref(tmp_path):
    import sys

    import openpyxl

    from bms.evidence import DEMOLITION_TAB, write_evidence

    job = _job(Unit("AHU", "AHU-4", ("AHU-4",), "demolish_with_work", 1, (), (WORK,),
                    reason="existing controls removed"))
    out = render(job, PLAYBOOK)
    block = out.scope.blocks[-1]
    assert block.header == "Demolition Scope"
    assert [item.text for item in block.items] == ["Qty (1) AHU demo, existing controls removed"]
    assert block.items[0].runs[0].red
    assert ("", "line", "Qty (1) AHU demo, existing controls removed", 1) in [
        (l.system_key, l.kind, l.text, l.quantity) for l in out.lines]

    tests = Path(__file__).resolve().parents[1]
    if str(tests) not in sys.path:
        sys.path.insert(0, str(tests))
    from test_evidence import _catalogue
    path = write_evidence(tmp_path / "e.xlsx", _catalogue(), None, None, job)
    rows = [[c.value for c in row] for row in openpyxl.load_workbook(path)[DEMOLITION_TAB].iter_rows()]
    assert rows[1][:4] == ["AHU", "demo", 1, "existing controls removed"]
    assert 'S7 | "AHU-4 remove existing controls" | MD-102, Invented.pdf page 3' in rows[1][4]


def test_named_work_gets_its_own_line_apart_from_plain_demo():
    """Ruling: named demolition work on a unit gets its own line with the work named."""
    job = _job(Unit("AHU", "AHU-5", ("AHU-5",), "demolish", 1, (), (SHOWN,)),
               Unit("AHU", "AHU-4", ("AHU-4",), "demolish_with_work", 1, (), (WORK,),
                    reason="existing controls removed"))
    texts = [item.text for item in render(job, PLAYBOOK).scope.blocks[-1].items]
    assert texts == ["Qty (1) AHU demo", "Qty (1) AHU demo, existing controls removed"]


def test_the_demolition_heading_takes_no_number():
    job = _job(Unit("AHU", "AHU-5", ("AHU-5",), "demolish", 1, (), (SHOWN,)))
    assert render(job, PLAYBOOK).scope.blocks[-1].numbered is False
