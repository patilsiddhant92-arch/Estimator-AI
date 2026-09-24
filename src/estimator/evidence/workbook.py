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
         "unreadable": "Could not be opened"}
_READ_BY = {"text": "its text", "ocr": "OCR", "blank": "blank page", "unreadable": "could not be read"}
_FINDING = {"Qualifies": "C6EFCE", "Open": "FFEB9C", "Does not qualify": "FFC7CE"}
_HEADING = PatternFill("solid", fgColor="D9E1F2")
_BOLD = Font(bold=True)
_WIDEST = 80


def write_evidence(path: Path, catalogue: Catalogue) -> Path:
    workbook = Workbook()
    workbook.remove(workbook.active)
    _bid_check(workbook.create_sheet(TABS[0]), catalogue)
    _table(workbook.create_sheet(TABS[1]), ["What to look at"], [[f] for f in catalogue.flags] or [["Nothing to flag."]])
    _table(workbook.create_sheet(TABS[2]), ["Document", "What it is", "Revision", "Pages", "Same file as"],
           [[d.relative, _KIND[d.kind], d.revision, d.pages, d.duplicate_of] for d in catalogue.job.documents]
           + [[folder, "Left out — AME's own work, not a bid document", None, None, None] for folder in catalogue.job.left_out])
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
    ws.append([f"Bid check — {catalogue.job.name}"])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append([])
    ws.append(["Finding", bid.finding])
    ws["B3"].fill = PatternFill("solid", fgColor=_FINDING.get(bid.finding, "FFFFFF"))
    ws["B3"].font = _BOLD
    ws.append(["Why", bid.reason])
    ws.append(["Other controls manufacturers named (for the US team)", ", ".join(bid.others) or "none"])
    ws.append(["Controls sections in the specs", "; ".join(bid.controls_sections) or "none found"])
    ws.append(["The US team makes the final call. Every passage the check found is quoted below, word for word."])
    ws.append([])
    ws.append(["Document", "Page", "Manufacturers named", "What the spec says (word for word)"])
    for cell in ws[ws.max_row]:
        cell.font, cell.fill = _BOLD, _HEADING
    for m in bid.mentions:
        ws.append([m.document, m.page, ", ".join(m.ours + m.listed + m.others), m.quote])
        ws.cell(ws.max_row, 4).alignment = Alignment(wrap_text=True, vertical="top")
    for row in range(3, 7):
        ws.cell(row, 1).font = _BOLD
    ws.column_dimensions["A"].width = 52
    ws.column_dimensions["B"].width = 24
    ws.column_dimensions["C"].width = 30
    ws.column_dimensions["D"].width = 110


def _table(ws, headings: list[str], rows: list[list]) -> None:
    ws.append(headings)
    for cell in ws[1]:
        cell.font, cell.fill = _BOLD, _HEADING
    for row in rows:
        ws.append(row)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for index, heading in enumerate(headings, start=1):
        longest = max([len(heading)] + [len(str(r[index - 1])) for r in rows if r[index - 1] is not None])
        ws.column_dimensions[get_column_letter(index)].width = min(longest + 2, _WIDEST)
