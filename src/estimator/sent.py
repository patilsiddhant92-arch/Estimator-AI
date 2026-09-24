"""Turn what was actually sent for a past job — its proposal and its price workup — into a Job.

The proposal gives the scope. The workup gives the tech hours on each block and
the quantity on each line. The two are matched row by row, because the workup
is the proposal pasted into Excel.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from estimator.price_sheet.rows import align, read_sent_rows, sheet_plan
from estimator.proposal.read import read_proposal
from estimator.scope import Job


@dataclass(frozen=True)
class ImportReport:
    matched: int
    unmatched_ours: tuple[str, ...]      # proposal lines with no workup row: no hours or quantity taken
    unmatched_theirs: tuple[str, ...]    # workup rows that match nothing in the proposal: ignored


def job_from_sent(proposal: Path, workup: Path, template: Path) -> tuple[Job, ImportReport]:
    job = read_proposal(proposal, template)
    sent = read_sent_rows(workup)
    data = job.model_dump()
    matched, lost_ours, lost_theirs = 0, [], []
    for sheet in sheet_plan(job):
        ours = [row for row in sheet.rows if row.text]
        theirs = sent.get(sheet.title, [])
        pairs = align([row.text for row in ours], [row.text for row in theirs])
        matched += len(pairs)
        for a, b in pairs:
            row, found = ours[a], theirs[b]
            if not row.ref:
                continue
            target = _at(data, row.ref)
            if row.item is None:
                if found.hours is not None:
                    target["tech_hours"] = found.hours
            elif row.item.kind == "line" and found.quantity is not None:
                target["quantity"] = found.quantity
        paired_ours = {a for a, _ in pairs}
        paired_theirs = {b for _, b in pairs}
        lost_ours += [ours[a].text for a in range(len(ours)) if a not in paired_ours]
        lost_theirs += [theirs[b].text for b in range(len(theirs)) if b not in paired_theirs]
    return Job.model_validate(data), ImportReport(matched, tuple(lost_ours), tuple(lost_theirs))


def _at(data: dict, ref: tuple) -> dict:
    node = data
    for step in ref:
        node = node[step]
    return node
