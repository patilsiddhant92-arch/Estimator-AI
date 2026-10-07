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


def test_a_count_known_only_from_another_count_prints_that_count_and_its_source():
    """RND-7 (estimator ruling D9): the package prints the number the proposal prints (`Count.highest()`), and an
    other count keeps its source id, where and quote."""
    from bms.model import Count, OtherCount, Ref
    job = _job()
    dh = job.system("DH")
    count = Count(value=None, others=(OtherCount(2, Ref("S2", "invented quote", "Q-9.00, Invented.pdf page 1")),))
    job = job.with_system(dc.replace(dh, devices=(dc.replace(dh.devices[0], quantity=count),) + dh.devices[1:]))
    row = next(r for r in scope_rows(job) if r[1] == dh.devices[0].id)
    at = {h: i for i, h in enumerate(SCOPE_HEADINGS)}
    assert row[at["Quantity"]] == "2"
    assert "S2" in row[at["Other counts"]] and "invented quote" in row[at["Other counts"]]
    assert "Device id" in SCOPE_HEADINGS and "Line" not in SCOPE_HEADINGS
