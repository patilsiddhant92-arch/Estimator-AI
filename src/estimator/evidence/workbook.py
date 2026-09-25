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
from estimator.catalogue.overview import (FOUND, RULED_OUT, STANDARD_CLARIFICATION, STANDARD_EXCLUSION,
                                          short_place)
from estimator.catalogue.qualify import where

TABS = ("Bid check", "Spec overview", "Flags", "Documents", "Pages", "Sheets", "Spec sections", "Equipment tags")
_GREEN = PatternFill("solid", fgColor="C6EFCE")
_AMBER = PatternFill("solid", fgColor="FFEB9C")
_STATUS_FILL = {FOUND: _GREEN, RULED_OUT: _AMBER}
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
    _spec_overview(workbook.create_sheet(TABS[1]), catalogue)
    _table(workbook.create_sheet(TABS[2]), ["What to look at"], [[f] for f in catalogue.flags] or [["Nothing to flag."]])
    _table(workbook.create_sheet(TABS[3]), ["Document", "What it is", "Revision", "Pages", "Same file as"],
           [[d.relative, _KIND[d.kind], d.revision, d.pages, d.duplicate_of] for d in catalogue.job.documents]
           + [[folder, "Left out — AME's own work, not a bid document", None, None, None] for folder in catalogue.job.left_out]
           + [[folder, "Left out — another job, catalogue it on its own", None, None, None] for folder in catalogue.job.nested_jobs]
           + [[f, f"Not read — not a PDF ({Path(f).suffix or 'no extension'})", None, None, None]
              for f in catalogue.job.other_files])
    numbers = {(s.document, s.page): s.number for s in catalogue.sheets}
    _table(workbook.create_sheet(TABS[4]), ["Document", "Page", "Read by", "Sheet number"],
           [[p.document, p.page, _READ_BY[p.status], numbers.get((p.document, p.page))] for p in catalogue.pages])
    _table(workbook.create_sheet(TABS[5]), ["Sheet number", "Title", "Discipline", "Type", "Document", "Page"],
           [[s.number, s.title, s.discipline, ", ".join(s.types) or None, s.document, s.page] for s in catalogue.sheets])
    _table(workbook.create_sheet(TABS[6]), ["Section", "Title", "Controls section", "Document", "First page", "Last page"],
           [[s.number, s.title, "yes" if s.controls else "no", s.document, s.first_page, s.last_page]
            for s in catalogue.sections])
    _table(workbook.create_sheet(TABS[7]), ["Tag", "What it is", "On schedules", "Also appears on", "Times found"],
           [[t.tag, t.kind, ", ".join(t.on_schedules) or None, ", ".join(t.elsewhere) or None, t.times]
            for t in catalogue.tags])
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(str(path))
    return path


def _section_heading(ws, text: str) -> None:
    _append(ws, [text])
    for cell in ws[ws.max_row]:
        cell.font, cell.fill = _BOLD, _HEADING


_TOPIC_HEADINGS = ["What", "Status", "Where", "How strong", "What the job says (word for word)"]
_LINE_HEADINGS = ["AME's line (word for word)", "Status", "Where", "How strong", "What the job says (word for word)"]
_MAKER_HEADINGS = ["Category", "Manufacturer", "AME gets prices for it?", "Where", "How strong",
                   "What the job says (word for word)", "Basis of design / or equal", "Ask for a price from",
                   "Email draft"]


def _headings(ws, headings: list[str]) -> None:
    _append(ws, headings)
    for cell in ws[ws.max_row]:
        cell.font, cell.fill = _BOLD, _HEADING


def _status_cell(ws, column: int, status: str) -> None:
    cell = ws.cell(ws.max_row, column)
    if status in _STATUS_FILL:
        cell.fill = _STATUS_FILL[status]


def _found_row(ws, item: str, found) -> None:
    _append(ws, [item, found.status, short_place(found.places),
                found.places[0].strength if found.places else None, found.quote])
    _status_cell(ws, 2, found.status)
    ws.cell(ws.max_row, 1).alignment = Alignment(wrap_text=True, vertical="top")
    ws.cell(ws.max_row, 5).alignment = Alignment(wrap_text=True, vertical="top")


def _topic_table(ws, catalogue: Catalogue, heading: str, section: str) -> None:
    _section_heading(ws, heading)
    _headings(ws, _TOPIC_HEADINGS)
    for found in catalogue.overview.topics:
        if found.section == section:
            _found_row(ws, found.item, found)
    _append(ws, [])


def _standard_lines(ws, catalogue: Catalogue, heading: str) -> None:
    _section_heading(ws, heading)
    _append(ws, ["Each of AME's standard clarifications the job speaks to — read it to see whether the job agrees — "
                "and each standard exclusion the job asks the controls contractor to furnish, provide or install."])
    lines = catalogue.overview.standard_lines
    for kind, title in ((STANDARD_CLARIFICATION, "Clarifications — does the job agree?"),
                        (STANDARD_EXCLUSION, "Exclusions — the job asks the controls contractor for it")):
        _append(ws, [title])
        ws.cell(ws.max_row, 1).font = _BOLD
        rows = [f for f in lines if f.section == kind]
        if not rows:
            _append(ws, ["Nothing found — the job doesn't speak to any of these lines."])
            continue
        _headings(ws, _LINE_HEADINGS)
        for found in rows:
            _found_row(ws, found.item, found)
    _append(ws, [])


def _spec_overview(ws, catalogue: Catalogue) -> None:
    overview = catalogue.overview
    bid = catalogue.bid
    _append(ws, [f"Spec overview — {catalogue.job.name}"])
    ws["A1"].font = Font(bold=True, size=14)
    _append(ws, ["What the job says, found word for word. Nothing here is guessed: a row either quotes the "
                "job or says it wasn't found."])
    _append(ws, [])
    _section_heading(ws, "1. Controls platform")
    _append(ws, ["Bid check", bid.finding])
    ws.cell(ws.max_row, 1).font = _BOLD
    _append(ws, ["Why", bid.reason])
    ws.cell(ws.max_row, 1).font = _BOLD
    _append(ws, ["Other controls manufacturers named", ", ".join(bid.others) or "none"])
    ws.cell(ws.max_row, 1).font = _BOLD
    _append(ws, ["Controls sections in the specs", "; ".join(bid.controls_sections) or "none found"])
    ws.cell(ws.max_row, 1).font = _BOLD
    _append(ws, ["See the Bid check tab for every passage."])
    _append(ws, [])
    _standard_lines(ws, catalogue, "2. AME normally excludes this — the job asks for it")
    _topic_table(ws, catalogue, "3. Protocols", "Protocols")
    _topic_table(ws, catalogue, "4. Network and front end", "Network and front end")
    _topic_table(ws, catalogue, "5. Electrical and conduit", "Electrical and conduit")
    _section_heading(ws, "6. Manufacturers named on this job")
    _headings(ws, _MAKER_HEADINGS)
    for maker in overview.makers:
        if not maker.priced:
            ame, ask_for = "—", "A controls platform, not a device to price — see the Bid check tab"
        elif maker.ame_quotes:
            ame, ask_for = "Yes", "\n".join(maker.vendors)
        else:
            ame, ask_for = "No", "Not on AME's list — the estimator decides"
        _append(ws, [maker.category, maker.maker, ame, short_place(maker.places),
                    maker.places[0].strength if maker.places else None, maker.quote, maker.terms, ask_for,
                    maker.email_draft])
        row = ws.max_row
        ws.cell(row, 2).font = _BOLD
        if maker.ame_quotes:
            ws.cell(row, 2).fill = _GREEN
        for column in (6, 8, 9):
            ws.cell(row, column).alignment = Alignment(wrap_text=True, vertical="top")
    _append(ws, [])
    _section_heading(ws, "7. Searched for but not found")
    for line in overview.not_found or ["Nothing to report — everything on the reading lists was found."]:
        _append(ws, [line])
    ws.column_dimensions["A"].width = 40
    ws.column_dimensions["B"].width = 30
    ws.column_dimensions["C"].width = 34
    ws.column_dimensions["D"].width = 20
    ws.column_dimensions["E"].width = 60
    ws.column_dimensions["F"].width = 60
    ws.column_dimensions["G"].width = 60
    ws.column_dimensions["H"].width = 26
    ws.column_dimensions["I"].width = 40


def _bid_check(ws, catalogue: Catalogue) -> None:
    bid = catalogue.bid
    _append(ws, [f"Bid check — {catalogue.job.name}"])
    ws["A1"].font = Font(bold=True, size=14)
    _append(ws, ["This is the tool's first reading of the spec. Every passage it found is quoted "
                "below; the US team reads them and makes the call."])
    _append(ws, [])
    _append(ws, ["Finding", bid.finding])
    ws["B4"].fill = PatternFill("solid", fgColor=_FINDING.get(bid.finding, "FFFFFF"))
    ws["B4"].font = _BOLD
    _append(ws, ["Why", bid.reason])
    _append(ws, ["Other controls manufacturers named (for the US team)", ", ".join(bid.others) or "none"])
    _append(ws, ["Controls sections in the specs", "; ".join(bid.controls_sections) or "none found"])
    _append(ws, [])
    _append(ws, ["Where (every place it was found)", "Manufacturers named", "What the spec says (word for word)"])
    for cell in ws[ws.max_row]:
        cell.font, cell.fill = _BOLD, _HEADING
    for m in bid.mentions:
        _append(ws, [where(m), m.named, m.quote])
        ws.cell(ws.max_row, 3).alignment = Alignment(wrap_text=True, vertical="top")
    for row in range(4, 8):
        ws.cell(row, 1).font = _BOLD
    ws.column_dimensions["A"].width = 52
    ws.column_dimensions["B"].width = 30
    ws.column_dimensions["C"].width = 110


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
