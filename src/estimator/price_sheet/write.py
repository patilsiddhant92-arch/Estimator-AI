"""Fill the AME price workup template from a Job.

The template's own formulas do all the arithmetic — material total, labour,
project management, engineering, tax, markup, sell price. The tool types only
into the input columns (hours, quantity, scope, unit price) and never touches a
formula cell. A line the price book can't price is left without a price and
marked PRICE PENDING, and the Summary says how many there are, so an incomplete
total is never mistaken for a complete one.
"""
from __future__ import annotations

from pathlib import Path

from openpyxl.styles import Font

from estimator.files import open_workbook
from estimator.price_sheet.price_book import PriceBook
from estimator.price_sheet.rows import FIRST_ROW, FLAG, HOURS, LAST_ROW, QUANTITY, SCOPE, UNIT_PRICE, Sheet, sheet_plan
from estimator.scope import Job

PRICE_PENDING = "PRICE PENDING"
PRICE_NEEDS_REVIEW = "PRICE NEEDS REVIEW"   # the price book's own note questions this price
QUANTITY_PENDING = "QUANTITY PENDING"       # a "Qty (##)" block: its count is still to fill, its lines are unpriced
BASE_LABEL = "Base Bid"
MAX_SHEETS = 10
_FLAG_FONT = Font(bold=True, color="C00000")


class PriceSheetError(ValueError):
    """The job doesn't fit the price workup template."""


def check_fit(job: Job) -> list[Sheet]:
    """Refuse a job that doesn't fit the price workup template — too many sheets, or too many
    rows on one of them — before anything is written. Returns the sheet plan, so a caller that
    already checked doesn't have to compute it twice."""
    plan = sheet_plan(job)
    if len(plan) > MAX_SHEETS:
        raise PriceSheetError(f"the job needs {len(plan)} price sheets; the template has {MAX_SHEETS}")
    room = LAST_ROW - FIRST_ROW + 1
    for sheet in plan:
        if len(sheet.rows) > room:
            raise PriceSheetError(f"{sheet.title} needs {len(sheet.rows)} rows; the template has room for {room}")
    return plan


def write_price_sheet(job: Job, template_path: Path, book: PriceBook, out_path: Path) -> Path:
    plan = check_fit(job)
    workbook = open_workbook(template_path)    # formulas kept as formulas
    pending = 0
    for index, sheet in enumerate(plan):
        template_title = f"Price Sheet {index + 1}"
        if sheet.title != template_title:
            _rename_sheet(workbook, template_title, sheet.title)
        pending += _fill(workbook[sheet.title], sheet, book)
    counts = sum(1 for sheet in plan for row in sheet.rows if row.count_pending)
    _fill_summary(workbook["Summary"], job, plan, pending, counts)
    workbook.calculation.fullCalcOnLoad = True
    out_path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(str(out_path))
    return out_path


def _fill(ws, sheet: Sheet, book: PriceBook) -> int:
    pending = 0
    for offset, row in enumerate(sheet.rows):
        r = FIRST_ROW + offset
        if row.text:
            ws.cell(r, SCOPE).value = row.text
        if row.hours is not None:
            ws.cell(r, HOURS).value = row.hours
        if row.count_pending:
            _flag(ws, r, QUANTITY_PENDING)     # its lines carry no quantity, so none of them is priced
        if row.quantity is not None:
            ws.cell(r, QUANTITY).value = row.quantity
            match = book.lookup(row.item.text)
            if match is None:
                _flag(ws, r, PRICE_PENDING)
                pending += 1
            else:
                ws.cell(r, UNIT_PRICE).value = match.price
                if match.needs_review:
                    _flag(ws, r, PRICE_NEEDS_REVIEW)
    return pending


def _flag(ws, row: int, text: str) -> None:
    cell = ws.cell(row, FLAG)
    cell.value = text
    cell.font = _FLAG_FONT


def _rename_sheet(workbook, old: str, new: str) -> None:
    """Rename a sheet and every reference to it. openpyxl, unlike Excel, doesn't follow a rename."""
    workbook[old].title = new
    old_ref, new_ref = f"'{old}'!", f"'{new}'!"
    for ws in workbook.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and cell.value.startswith("=") and old_ref in cell.value:
                    cell.value = cell.value.replace(old_ref, new_ref)
    names = list(workbook.defined_names.values())
    for ws in workbook.worksheets:
        names += list(ws.defined_names.values())
    for defined in names:
        if defined.attr_text and old_ref in defined.attr_text:
            defined.attr_text = defined.attr_text.replace(old_ref, new_ref)


def _fill_summary(ws, job: Job, plan: list[Sheet], pending: int, counts: int = 0) -> None:
    ws["B7"] = job.header.reference
    ws["B9"] = job.header.quote_number
    ws["B15"] = job.header.date
    for index, sheet in enumerate(plan):
        ws.cell(21 + index, 2).value = BASE_LABEL if index == 0 else sheet.title
    said = []
    if pending:
        lines, have = ("line", "has") if pending == 1 else ("lines", "have")
        said.append(f"{pending} {lines} with a quantity {have} no price yet — marked {PRICE_PENDING} "
                    f"in column H of the price sheets. The totals above leave them out.")
    if counts:
        blocks, have = ("block", "has") if counts == 1 else ("blocks", "have")
        said.append(f"{counts} {blocks} {have} no count yet — Qty (##), marked {QUANTITY_PENDING}; their lines "
                    "are not priced until the count is typed in.")
    if said:
        cell = ws["B34"]
        cell.value = " ".join(said)
        cell.font = _FLAG_FONT
