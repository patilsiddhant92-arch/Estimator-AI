"""The Evidence Package's Scope lines rows (bms.evidence.scope_rows), on the invented sample job."""
from __future__ import annotations

import dataclasses as dc
import json
from pathlib import Path

from bms.evidence import SCOPE_HEADINGS, scope_rows
from bms.model import Job

FIX = Path(__file__).resolve().parent / "fixtures"


def _job() -> Job:
    return Job.from_dict(json.loads((FIX / "sample_job.json").read_text(encoding="utf-8")))


def test_a_system_with_no_lines_has_a_left_out_row_with_its_reason():
    """RND-8: a system the writer gave no lines prints nothing in the proposal; the Evidence Package keeps it,
    with the writer's reason."""
    job = _job()
    job = job.with_system(dc.replace(job.system("DH"), devices=(),
                                     no_scope_reason="the invented heaters are controlled by their own panel"))
    rows = [r for r in scope_rows(job) if r[2] == "left out"]
    assert len(rows) == 1 and len(rows[0]) == len(SCOPE_HEADINGS)
    assert "(DH)" in rows[0][0]
    assert "the invented heaters are controlled by their own panel" in rows[0][3]


def test_a_system_with_lines_has_no_left_out_row():
    assert [r for r in scope_rows(_job()) if r[2] == "left out"] == []
