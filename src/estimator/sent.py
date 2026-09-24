"""Turn what was actually sent for a past job — its proposal and its price workup — into a Job.

The proposal gives the scope. The workup gives the tech hours on each block, line
and note, and the quantity on each line. The two are matched row by row, because
the workup is the proposal pasted into Excel. Anything on a matched row that
still doesn't land in the Job — a quantity on a note, an hours or quantity cell
that isn't a number, a fractional quantity — is never dropped silently: it is
named in `ImportReport.ignored`, in plain words, row by row.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from estimator.price_sheet.rows import SentRow, align, read_sent_rows, sheet_plan
from estimator.proposal.read import read_proposal
from estimator.scope import Job


@dataclass(frozen=True)
class ImportReport:
    matched: int
    unmatched_ours: tuple[str, ...]      # proposal lines with no workup row: no hours or quantity taken
    unmatched_theirs: tuple[str, ...]    # workup rows that match nothing in the proposal: ignored
    ignored: tuple[str, ...]             # non-empty hours/quantity cells on a matched row with nowhere to go


def job_from_sent(proposal: Path, workup: Path, template: Path) -> tuple[Job, ImportReport]:
    job = read_proposal(proposal, template)
    sent = read_sent_rows(workup)
    return import_matches(job, sent)


def import_matches(job: Job, sent: dict[str, list[SentRow]]) -> tuple[Job, ImportReport]:
    """Match a Job's own rows (its own price sheet layout) against a workup's rows, sheet by
    sheet, and take every hours/quantity cell that has somewhere in the Job to land."""
    data = job.model_dump()
    matched, lost_ours, lost_theirs, ignored = 0, [], [], []
    for sheet in sheet_plan(job):
        ours = [row for row in sheet.rows if row.text]
        theirs = sent.get(sheet.title, [])
        pairs = align([row.text for row in ours], [row.text for row in theirs])
        matched += len(pairs)
        for a, b in pairs:
            row, found = ours[a], theirs[b]
            if not row.ref:
                ignored += _stray(sheet.title, found)
                continue
            target = _at(data, row.ref)
            note = _take_hours(target, found, sheet.title)
            if note:
                ignored.append(note)
            if row.item is not None and row.item.kind == "line":
                note = _take_quantity(target, found, sheet.title)
                if note:
                    ignored.append(note)
            elif not _empty(found.quantity_raw):
                place = "a note" if row.item is not None else "a header"
                ignored.append(f"{sheet.title} row {found.row}: quantity {_show(found.quantity_raw)} "
                                f"is on {place}, which has no quantity")
        paired_ours = {a for a, _ in pairs}
        paired_theirs = {b for _, b in pairs}
        lost_ours += [ours[a].text for a in range(len(ours)) if a not in paired_ours]
        lost_theirs += [theirs[b].text for b in range(len(theirs)) if b not in paired_theirs]
    return Job.model_validate(data), ImportReport(matched, tuple(lost_ours), tuple(lost_theirs), tuple(ignored))


def _empty(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _show(value: object) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value:g}"
    return repr(value)


def _take_hours(target: dict, found: SentRow, sheet: str) -> str | None:
    if _empty(found.hours_raw):
        return None
    if found.hours is None:
        return f"{sheet} row {found.row}: hours {_show(found.hours_raw)} is not a number"
    if found.hours < 0:
        return f"{sheet} row {found.row}: hours {_show(found.hours_raw)} can't be negative"
    target["tech_hours"] = found.hours
    return None


def _take_quantity(target: dict, found: SentRow, sheet: str) -> str | None:
    if _empty(found.quantity_raw):
        return None
    if not isinstance(found.quantity_raw, (int, float)) or isinstance(found.quantity_raw, bool):
        return f"{sheet} row {found.row}: quantity {_show(found.quantity_raw)} is not a number"
    if found.quantity is None:
        return f"{sheet} row {found.row}: quantity {_show(found.quantity_raw)} is not a whole number"
    if found.quantity < 0:
        return f"{sheet} row {found.row}: quantity {_show(found.quantity_raw)} can't be negative"
    target["quantity"] = found.quantity
    return None


def _stray(sheet: str, found: SentRow) -> list[str]:
    """Hours or a quantity on a row the proposal has no place for at all (ref == ())."""
    out = []
    if not _empty(found.hours_raw):
        out.append(f"{sheet} row {found.row}: hours {_show(found.hours_raw)} on a line the job has no place for")
    if not _empty(found.quantity_raw):
        out.append(f"{sheet} row {found.row}: quantity {_show(found.quantity_raw)} on a line the job has no place for")
    return out


def _at(data: dict, ref: tuple) -> dict:
    node = data
    for step in ref:
        node = node[step]
    return node
