"""Write the Evidence Package (.xlsx).

The bid check is the first tab, because it is the first thing the US team reads (design
§8). Every page of every bid document is on the Pages tab, so a page that couldn't be read
is visible, never missing.
"""
from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from estimator.catalogue.job import Catalogue

TABS = ("Bid check", "Flags", "Documents", "Pages", "Sheets", "Spec sections", "Equipment tags")
_KIND = {"drawings": "Drawings", "specs": "Specs", "addendum": "Addendum", "rfi": "RFI", "other": "Other",
         "unreadable": "Could not be opened", "password": "Password-protected"}
_READ_BY = {"text": "its text", "ocr": "OCR", "blank": "blank page", "unreadable": "could not be read"}
_FINDING = {"Qualifies": "C6EFCE", "Open": "FFEB9C", "Does not qualify": "FFC7CE"}
_HEADING = PatternFill("solid", fgColor="D9E1F2")
_BOLD = Font(bold=True)
_WIDEST = 80


def _append(ws, row: list) -> None:
    """openpyxl treats any string starting with "=" as a formula; an OCR'd quote or a sheet
    title that happens to start with "=" would otherwise make Excel "repair" the file (M1)."""
    ws.append(row)
    for cell in ws[ws.max_row]:
        if isinstance(cell.value, str) and cell.value.startswith("="):
            cell.data_type = "s"


def write_evidence(path: Path, catalogue: Catalogue) -> Path:
    workbook = Workbook()
    workbook.remove(workbook.active)
    _bid_check(workbook.create_sheet(TABS[0]), catalogue)
    _table(workbook.create_sheet(TABS[1]), ["What to look at"], [[f] for f in catalogue.flags] or [["Nothing to flag."]])
    _table(workbook.create_sheet(TABS[2]), ["Document", "What it is", "Revision", "Pages", "Same file as"],
           [[d.relative, _KIND[d.kind], d.revision, d.pages, d.duplicate_of] for d in catalogue.job.documents]
           + [[folder, "Left out — AME's own work, not a bid document", None, None, None] for folder in catalogue.job.left_out]
           + [[folder, "Left out — another job, catalogue it on its own", None, None, None] for folder in catalogue.job.nested_jobs]
           + [[f, f"Not read — not a PDF ({Path(f).suffix or 'no extension'})", None, None, None]
              for f in catalogue.job.other_files])
    numbers = {(s.document, s.page): s.number for s in catalogue.sheets}
    _table(workbook.create_sheet(TABS[3]), ["Document", "Page", "Read by", "Sheet number"],
           [[p.document, p.page, _READ_BY[p.status], numbers.get((p.document, p.page))] for p in catalogue.pages])
    _table(workbook.create_sheet(TABS[4]), ["Sheet number", "Title", "Discipline", "Type", "Document", "Page"],
           [[s.number, s.title, s.discipline, ", ".join(s.types) or None, s.document, s.page] for s in catalogue.sheets])
    _table(workbook.create_sheet(TABS[5]), ["Section", "Title", "Controls section", "Document", "First page", "Last page"],
           [[s.number, s.title, "yes" if s.controls else "no", s.document, s.first_page, s.last_page]
            for s in catalogue.sections])
    _table(workbook.create_sheet(TABS[6]), ["Tag", "What it is", "On schedules", "Also appears on", "Times found"],
           [[t.tag, t.kind, ", ".join(t.on_schedules) or None, ", ".join(t.elsewhere) or None, t.times]
            for t in catalogue.tags])
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(str(path))
    return path


def _bid_check(ws, catalogue: Catalogue) -> None:
    bid = catalogue.bid
    _append(ws, [f"Bid check — {catalogue.job.name}"])
    ws["A1"].font = Font(bold=True, size=14)
    _append(ws, [])
    _append(ws, ["Finding", bid.finding])
    ws["B3"].fill = PatternFill("solid", fgColor=_FINDING.get(bid.finding, "FFFFFF"))
    ws["B3"].font = _BOLD
    _append(ws, ["Why", bid.reason])
    _append(ws, ["Other controls manufacturers named (for the US team)", ", ".join(bid.others) or "none"])
    _append(ws, ["Controls sections in the specs", "; ".join(bid.controls_sections) or "none found"])
    _append(ws, ["The US team makes the final call. Every passage the check found is quoted below, word for word."])
    _append(ws, [])
    _append(ws, ["Document", "Page", "Manufacturers named", "What the spec says (word for word)"])
    for cell in ws[ws.max_row]:
        cell.font, cell.fill = _BOLD, _HEADING
    for m in bid.mentions:
        _append(ws, [m.document, m.page, m.named, m.quote])
        ws.cell(ws.max_row, 4).alignment = Alignment(wrap_text=True, vertical="top")
    for row in range(3, 7):
        ws.cell(row, 1).font = _BOLD
    ws.column_dimensions["A"].width = 52
    ws.column_dimensions["B"].width = 24
    ws.column_dimensions["C"].width = 30
    ws.column_dimensions["D"].width = 110


def _table(ws, headings: list[str], rows: list[list]) -> None:
    _append(ws, headings)
    for cell in ws[1]:
        cell.font, cell.fill = _BOLD, _HEADING
    for row in rows:
        _append(ws, row)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for index, heading in enumerate(headings, start=1):
        longest = max([len(heading)] + [len(str(r[index - 1])) for r in rows if r[index - 1] is not None])
        ws.column_dimensions[get_column_letter(index)].width = min(longest + 2, _WIDEST)
