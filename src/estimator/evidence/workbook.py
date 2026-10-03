"""Write the Evidence Package (.xlsx).

The bid check is the first tab, because it is the first thing the US team reads (design
§8). Every page of every bid document is on the Pages tab, so a page that couldn't be read
is visible, never missing.
"""
from __future__ import annotations

import re
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from estimator.catalogue.job import Catalogue
from estimator.catalogue.overview import (FOUND, RULED_OUT, STANDARD_CLARIFICATION, STANDARD_EXCLUSION,
                                          short_place)
from estimator.catalogue.qualify import where
from estimator.reading.job import JobReading

TABS = ("Bid check", "Spec overview", "Flags", "Documents", "Pages", "Sheets", "Spec sections", "Equipment tags")
# The reading of the job (build step 4), written after the Spec overview when a reading is given.
READING_TABS = ("Equipment", "Schedules", "Devices on plans", "Notes", "Changes", "Sequence and points")
# The written scope (build step 5), right after the bid check when the systems are given.
ESTIMATE_TABS = ("Review list", "Scope lines")
# The whole-job method: every system the AI planned, with its quantity checked against the counts.
PLAN_TAB = "Plan"
READ_TAB = "How the job was read"
LEDGER_TAB = "Job ledger"
# The GEM's own checks per system (the whole-job method): its Quick Scan, its contradiction scan and its Self-QC.
GEM_TAB = "GEM QC"
# The estimator's corrections, read back by `estimator corrections` (estimator.corrections).
DECISION, CHANGE_TO = "Estimator decision", "Change to / why"
DECISIONS = ("keep", "delete", "change")
_DECISION_NOTE = ('keep, delete or change. For "change": the new text, then "why:" and the reason; for keep or '
                  'delete: the reason. Read back by: estimator corrections EVIDENCE.xlsx')
_GREEN = PatternFill("solid", fgColor="C6EFCE")
_AMBER = PatternFill("solid", fgColor="FFEB9C")
_GREY = PatternFill("solid", fgColor="D9D9D9")
_CATEGORY_FILL = {"CONFIRMED": _GREEN, "EXISTING": _GREY}   # every other category needs a look: amber
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


def write_evidence(path: Path, catalogue: Catalogue, reading: JobReading | None = None,
                   systems=None, review_flags=(), plan=None, ledger=None) -> Path:
    """The Evidence Package. With the written systems (build step 5), the review list and every
    scope line come right after the bid check; `review_flags` are the review items that belong to
    no system: a family on the drawings but on no schedule, as a flag's text, or a ReviewItem (the
    whole-job method). `plan` is the whole-job plan's checked systems (PlanCheck), for the Plan tab."""
    workbook = Workbook()
    workbook.remove(workbook.active)
    _bid_check(workbook.create_sheet(TABS[0]), catalogue)
    if ledger is not None:
        _how_read(workbook.create_sheet(READ_TAB), ledger)
    if systems is not None:
        flags = list(catalogue.flags) + list(reading.flags if reading is not None else ())
        _review_list(workbook.create_sheet(ESTIMATE_TABS[0]), systems, review_flags, flags)
        _scope_lines(workbook.create_sheet(ESTIMATE_TABS[1]), systems)
    if plan is not None:
        _plan(workbook.create_sheet(PLAN_TAB), plan)
    if ledger is not None:
        _ledger(workbook.create_sheet(LEDGER_TAB), ledger)
    gem = [record for system in systems or () for record in getattr(system, "gem", ()) or ()]
    if gem:
        _gem(workbook.create_sheet(GEM_TAB), gem)
    _spec_overview(workbook.create_sheet(TABS[1]), catalogue)
    if reading is not None:
        _write_reading(workbook, reading)
    flags = list(catalogue.flags) + list(reading.flags if reading is not None else ())
    _table(workbook.create_sheet(TABS[2]), ["What to look at"], [[f] for f in flags] or [["Nothing to flag."]])
    _table(workbook.create_sheet(TABS[3]), ["Document", "What it is", "Revision", "Pages", "Same file as"],
           [[d.relative, _KIND[d.kind], d.revision, d.pages, d.duplicate_of] for d in catalogue.job.documents]
           + [[folder, "Left out — AME's own work, not a bid document", None, None, None] for folder in catalogue.job.left_out]
           + [[folder, "Left out — another job, catalogue it on its own", None, None, None] for folder in catalogue.job.nested_jobs]
           + [[f, f"Not read — not a PDF ({Path(f).suffix or 'no extension'})", None, None, None]
              for f in catalogue.job.other_files])
    numbers = {(s.document, s.page): s.number for s in catalogue.sheets}
    _table(workbook.create_sheet(TABS[4]), ["Document", "Page", "Read by", "Sheet number"],
           [[p.document, p.page, _READ_BY[p.status], numbers.get((p.document, p.page))] for p in catalogue.pages])
    _table(workbook.create_sheet(TABS[5]), ["Sheet number", "Title", "Discipline", "Type", "Document", "Page",
                                            "Title read from"],
           [[s.number, s.title, s.discipline, ", ".join(s.types) or None, s.document, s.page,
             _TITLE_FROM.get(s.title_source, s.title_source)] for s in catalogue.sheets])
    _table(workbook.create_sheet(TABS[6]), ["Section", "Title", "Controls section", "Document", "First page", "Last page"],
           [[s.number, s.title, "yes" if s.controls else "no", s.document, s.first_page, s.last_page]
            for s in catalogue.sections])
    _table(workbook.create_sheet(TABS[7]), ["Tag", "What it is", "On schedules", "Also appears on", "Times found"],
           [[t.tag, t.kind, ", ".join(t.on_schedules) or None, ", ".join(t.elsewhere) or None, t.times]
            for t in catalogue.tags])
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(str(path))
    return path


def _how_read(ws, ledger) -> None:
    """One row per reading pass, in the estimator's order: what the tool understood after it, and what it refused."""
    from estimator.ledger.passes import PASSES
    _headings(ws, ["Pass", "What the tool understood", "What it refused"])
    for p in PASSES:
        refused = "; ".join(ledger.refused.get(p.name, ()) or ()) or None
        _append(ws, [p.title, ledger.understanding.get(p.name) or "(not read)", refused])
        for column in (2, 3):
            ws.cell(ws.max_row, column).alignment = Alignment(wrap_text=True, vertical="top")
    _widths(ws, [30, 90, 60])


def _ledger(ws, ledger) -> None:
    """Every fact of the job ledger: its value, the count that prints, its state and pass, where it comes from and
    the words that state it, then the other values later passes found."""
    _headings(ws, ["Id", "Kind", "Subject", "Value", "Printed count", "State", "Pass", "Source", "Where", "Quote",
                   "Other values"])
    ws.freeze_panes = "A2"
    for fact in ledger.facts.values():
        others = "; ".join(f"{c.stage} says {c.value} [{c.source_id}] “{c.quote}”" for c in fact.contradictions) or None
        _append(ws, [fact.id, fact.kind, fact.subject, fact.value, ledger.printed_count(fact.id), fact.state, fact.stage,
                     fact.source_id, ledger.sources.get(fact.source_id) or None, fact.quote, others])
        for column in (10, 11):
            ws.cell(ws.max_row, column).alignment = Alignment(wrap_text=True, vertical="top")
    if not ledger.facts:
        _append(ws, ["", "The ledger holds no facts."])
    ws.auto_filter.ref = ws.dimensions
    _widths(ws, [8, 14, 24, 30, 12, 12, 10, 8, 40, 50, 50])


def _section_heading(ws, text: str) -> None:
    _append(ws, [text])
    for cell in ws[ws.max_row]:
        cell.font, cell.fill = _BOLD, _HEADING


_TOPIC_HEADINGS = ["What", "Status", "Where", "How strong", "What the job says (word for word)"]
_LINE_HEADINGS = ["AME's line (word for word)", "Status", "Where", "How strong", "What the job says (word for word)"]
_WHO_HEADINGS = ["Who does it (the job's words)", "Status", "Where", "How strong", "What the job says (word for word)"]
_SYSTEM_HEADINGS = ["System", "Status", "Protocol named in the same sentence", "Where", "How strong",
                    "What the job says (word for word)"]
_TITLE_FROM = {"title block": "the title block", "drawing index": "the drawing index",
               "beside the sheet number": "the line beside the sheet number"}
_SERVICE_HEADINGS = ["Service", "Status", "Amount stated", "Where", "How strong", "What the job says (word for word)"]
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


def _found_row_with(ws, found, extra: str) -> None:
    """A row with one more column after the status: the protocol, or the amount stated."""
    _append(ws, [found.item, found.status, extra or None, short_place(found.places),
                found.places[0].strength if found.places else None, found.quote])
    _status_cell(ws, 2, found.status)
    ws.cell(ws.max_row, 1).alignment = Alignment(wrap_text=True, vertical="top")
    ws.cell(ws.max_row, 6).alignment = Alignment(wrap_text=True, vertical="top")


def _topic_table(ws, heading: str, rows, intro: str | None = None) -> None:
    _section_heading(ws, heading)
    if intro:
        _append(ws, [intro])
    _headings(ws, _TOPIC_HEADINGS)
    for found in rows:
        _found_row(ws, found.item, found)
    _append(ws, [])


def _who_does_what(ws, catalogue: Catalogue, heading: str) -> None:
    overview = catalogue.overview
    _section_heading(ws, heading)
    _append(ws, ["Every sentence that gives work to someone other than the controls contractor — the owner, others, "
                "another trade or the equipment maker — and any responsibility matrix."])
    if not overview.who_does_what:
        _append(ws, ["Nothing found — the job doesn't give any work to someone else in the places searched."])
        _append(ws, [])
        return
    _headings(ws, _WHO_HEADINGS)
    for found in overview.who_does_what:
        _found_row(ws, found.item, found)
    if overview.who_does_what_more:
        _append(ws, [f"…and {overview.who_does_what_more} more; see the Pages tab"])
    _append(ws, [])


def _other_systems(ws, catalogue: Catalogue, heading: str) -> None:
    _section_heading(ws, heading)
    _append(ws, ["Each other system the job asks to be integrated, monitored or connected to the controls, "
                "with the protocol named in the same sentence."])
    rows = catalogue.overview.integrations
    if not rows:
        _append(ws, ["Nothing found — the job doesn't name another system to connect to."])
        _append(ws, [])
        return
    _headings(ws, _SYSTEM_HEADINGS)
    for found in rows:
        _found_row_with(ws, found, found.protocol)
    _append(ws, [])


def _services(ws, catalogue: Catalogue, heading: str) -> None:
    _section_heading(ws, heading)
    _headings(ws, _SERVICE_HEADINGS)
    for found in catalogue.overview.services:
        _found_row_with(ws, found, found.amount)
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
    _who_does_what(ws, catalogue, "3. Who does what")
    _other_systems(ws, catalogue, "4. Other systems to connect to")
    _services(ws, catalogue, "5. Services that cost hours")
    _topic_table(ws, "6. Special systems", overview.special_systems)
    _topic_table(ws, "7. Project conditions that change the price", overview.conditions,
                 "Searched in the general requirements (Division 1) too.")
    for number, section in ((8, "Protocols"), (9, "Network and front end"), (10, "Electrical and conduit")):
        _topic_table(ws, f"{number}. {section}", [t for t in overview.topics if t.section == section])
    _section_heading(ws, "11. Manufacturers named on this job")
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
    _section_heading(ws, "12. Searched for but not found")
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


# ---- the reading of the job (build step 4) --------------------------------------------------------

def _yes(value: bool) -> str:
    return "yes" if value else "no"


def _widths(ws, widths: list[int]) -> None:
    for index, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(index)].width = width


def _write_reading(workbook, reading: JobReading) -> None:
    _equipment(workbook.create_sheet(READING_TABS[0]), reading)
    _table(workbook.create_sheet(READING_TABS[1]),
           ["Schedule", "Sheet", "Units listed", "Who provides the unit controller (the schedule's notes)",
            "Types only, no unit tags", "Document", "Page", "Read from"],
           [[s.title, s.sheet, len(s.rows), "\n".join(s.controls_by) or None, _yes(s.type_only), s.document, s.page,
             "the sheet's text — the table couldn't be read; check the count" if s.from_text else "the table"]
            for s in reading.schedules] or [["No schedule read from the drawings"] + [None] * 7])
    _devices(workbook.create_sheet(READING_TABS[2]), reading)
    notes = sorted(reading.notes, key=lambda n: not n.controls)
    _table(workbook.create_sheet(READING_TABS[3]),
           ["Sheet", "Notes block", "Number", "Adds controls scope", "Note", "Who does it", "Placements on the plan",
            "Document", "Page"],
           [[n.sheet, n.block, n.number, _yes(n.controls), n.text, n.who or None, "not counted", n.document, n.page]
            for n in notes] or [["No keyed or general notes found on the drawings"] + [None] * 8])
    _changes(workbook.create_sheet(READING_TABS[4]), reading)
    _table(workbook.create_sheet(READING_TABS[5]),
           ["What", "Where", "Kind", "Document", "First page", "Last page", "Same text as"],
           [[b.what, b.where, b.kind, b.document, b.first_page, b.last_page, b.duplicate_of] for b in reading.backbone]
           or [["Nothing found", "No sequence of operation or points list in the specs or on the drawings",
                None, None, None, None, None]])


def _equipment(ws, reading: JobReading) -> None:
    _section_heading(ws, "Units on the schedules, by kind")
    _append(ws, ["The schedule is the source of quantities: one row per unit. The other drawing sheets check it; "
                "a unit they don't confirm is flagged, never counted silently."])
    _headings(ws, ["What it is", "Tag prefix", "Units scheduled", "Tags", "To look at"])
    for total in reading.totals:
        _append(ws, [total.kind, total.prefix, total.scheduled, total.tags, "\n".join(total.flags) or None])
    if not reading.totals:
        _append(ws, ["No units read from a schedule."])
    _append(ws, [])
    _section_heading(ws, "Every item")
    _headings(ws, ["Tag", "What it is", "Category", "Why", "Schedule", "Also appears on", "Action", "Quantity"])
    for item in reading.inventory:
        _append(ws, [item.tag, item.kind, item.category, item.reason, item.schedule, ", ".join(item.seen_on) or None,
                    item.action or None, item.quantity])
        ws.cell(ws.max_row, 3).fill = _CATEGORY_FILL.get(item.category, _AMBER)
        ws.cell(ws.max_row, 4).alignment = Alignment(wrap_text=True, vertical="top")
    if not reading.inventory:
        _append(ws, ["No equipment tags found."])
    _widths(ws, [30, 14, 16, 60, 34, 34, 16, 10])


def _devices(ws, reading: JobReading) -> None:
    _section_heading(ws, "Device labels counted on the plans")
    _append(ws, ["Each label counted where it stands on a plan sheet of the trades that carry controls scope, "
                "outside the title block; a typical plan counts once per floor."])
    _headings(ws, ["Sheet", "Device", "Label", "Count on the sheet", "Floors", "Total", "In the job's legend",
                   "Document", "Page"])
    has_legend = bool(reading.legend)
    for d in reading.devices:
        _append(ws, [d.sheet, d.device, d.label, d.count, d.floors, d.total,
                    _yes(d.in_legend) if has_legend else "no legend in the set", d.document, d.page])
    if not reading.devices:
        _append(ws, ["No device labels found on the plans."])
    _append(ws, [])
    _section_heading(ws, "The job's legend")
    _headings(ws, ["Code", "What it means", "Sheet"])
    for entry in reading.legend:
        _append(ws, [entry.code, entry.meaning, entry.sheet])
    if not has_legend:
        _append(ws, ["No legend sheet found."])
    _append(ws, [])
    _section_heading(ws, "Typical floor plans")
    _headings(ws, ["What it says", "Sheet", "Title", "Floors"])
    for typical in reading.typicals:
        _append(ws, [typical.note, typical.sheet, typical.title, len(typical.floors)])
    if not reading.typicals:
        _append(ws, ["No typical floor plan found."])
    _widths(ws, [44, 34, 12, 18, 10, 10, 22, 50, 8])


_READ_FROM = {"title block": "the title block", "document is an addendum": "the document is an addendum",
              "unknown": "not found"}


def _changes(ws, reading: JobReading) -> None:
    _section_heading(ws, "Sheets replaced by a later issue — the latest date governs")
    if not reading.supersessions:
        _append(ws, ["No sheet is in more than one issue — nothing replaced."])
    for supersession in reading.supersessions:
        _append(ws, [supersession.note])
        ws.cell(ws.max_row, 1).font = _BOLD
        _headings(ws, ["Sheet", "What changed", "Was", "Now", "Affects controls"])
        for change in supersession.changes:
            _append(ws, [change.sheet, change.what, change.old or None, change.new or None,
                        _yes(change.affects_controls)])
        _append(ws, [])
    _append(ws, [])
    _section_heading(ws, "The issues each sheet's title block lists")
    _headings(ws, ["Sheet", "Latest issue", "Latest date", "Read from", "Document", "Page"])
    for version in reading.versions:
        last = version.issues[-1] if version.issues else None
        _append(ws, [version.sheet, last.description if last else None,
                    version.latest.strftime("%m/%d/%Y") if version.latest else None,
                    _READ_FROM.get(version.source, version.source), version.document, version.page])
    _widths(ws, [30, 28, 60, 60, 16, 50])


# ---- the written scope (build step 5) --------------------------------------------------------------

_RED = PatternFill("solid", fgColor="FFC7CE")
_LINE_FILL = {"CONFIRMED": _GREEN, "ADDED": _GREEN, "ASSUMPTION": _AMBER, "PENDING": _RED, "CONFLICT": _RED}
_REVIEW_ORDER = ("PENDING", "CONFLICT", "DISCREPANCY", "MISSING", "EXTRA", "ORPHANED", "EXISTING", "ASSUMPTION", "")
_FLAG_CATEGORY = re.compile(r"\b(EXTRA|ORPHANED|PENDING|DISCREPANCY|MISSING|CONFLICT|EXISTING)\b")


_SPEC_ONLY = "mentioned only in the specs"     # stays on the Flags tab, never on the review list


def _review_list(ws, systems, review_flags, flags) -> None:
    """Everything the estimator decides before the proposal goes out, the most urgent first, each
    with its rank, then the flags from cataloguing and reading the job. Items already ranked (the
    whole-job method's review list) keep their order; the rest are ordered by their category."""
    rows = []                                   # (rank, category order, arrival, row)
    order = {c: n for n, c in enumerate(_REVIEW_ORDER)}
    items = [item for system in systems for item in system.review] + list(review_flags)
    for n, item in enumerate(items):
        if isinstance(item, str):              # a flag's text: a family on the drawings but on no schedule
            decide, _, action = item.partition(" — ")
            found = _FLAG_CATEGORY.search(decide)
            row = ["Not on a schedule", found.group(1) if found else "", decide, None, action or None]
            rank = 0
        else:
            row = [item.system, item.category, item.decide, item.evidence or None, item.action or None]
            rank = getattr(item, "rank", 0) or 0
        rows.append((rank or 10 ** 9, order.get(row[1], len(order)), n, row))
    rows.sort(key=lambda r: r[:3])
    table = [[k, *row] for k, (*_, row) in enumerate(rows, start=1)]
    table += [[None, "Reading the job", "", flag, None, "See the Flags tab"] for flag in flags
              if _SPEC_ONLY not in flag]
    _table(ws, ["Rank", "System", "Category", "What to decide", "Evidence", "Suggested action", DECISION, CHANGE_TO],
           [row + [None, None] for row in table] or [[None, "", "", "Nothing to review.", None, None, None, None]])
    for r in range(2, ws.max_row + 1):
        fill = _LINE_FILL.get(ws.cell(r, 3).value)
        if fill is not None:
            ws.cell(r, 3).fill = fill
        for column in (4, 5, 6, 8):
            ws.cell(r, column).alignment = Alignment(wrap_text=True, vertical="top")
    _decision_columns(ws, 7)
    _widths(ws, [7, 30, 14, 70, 60, 44, 12, 50])


def _decision_columns(ws, column: int) -> None:
    """The estimator's two columns: a keep / delete / change choice, then the new text or the reason."""
    letter, last = get_column_letter(column), max(ws.max_row, 2)
    choice = DataValidation(type="list", formula1='"' + ",".join(DECISIONS) + '"', allow_blank=True,
                            showErrorMessage=False, prompt=_DECISION_NOTE, showInputMessage=True)
    ws.add_data_validation(choice)
    choice.add(f"{letter}2:{letter}{last + 500}")
    for c in (column, column + 1):
        ws.cell(1, c).fill = _AMBER


def _scope_lines(ws, systems) -> None:
    """Every line the tool wrote or left PENDING, with its category, confidence, source and evidence."""
    _headings(ws, ["System", "Line", "Quantity", "Tech hours", "Category", "Confidence", "Source", "Evidence",
                   "In the proposal?", "Reference line", "Flag", DECISION, CHANGE_TO])
    ws.freeze_panes = "A2"
    for system in systems:
        headers = [(b.header, b.tech_hours) for b in system.blocks] or [(system.bundle_key, None)]
        for header, hours in headers:
            _append(ws, [system.bundle_key, header, None, hours, None, None, None, None, _yes(system.printed)])
            ws.cell(ws.max_row, 2).font = _BOLD
        for line in system.lines:
            _append(ws, [line.system, line.text, line.quantity, line.tech_hours, line.category,
                        round(line.confidence, 2), line.source, line.evidence, _yes(line.client),
                        getattr(line, "reference", "") or None, getattr(line, "flag", "") or None])
            ws.cell(ws.max_row, 2).alignment = Alignment(indent=line.depth, wrap_text=True, vertical="top")
            fill = _LINE_FILL.get(line.category)
            if fill is not None:
                ws.cell(ws.max_row, 5).fill = fill
            ws.cell(ws.max_row, 8).alignment = Alignment(wrap_text=True, vertical="top")
            ws.cell(ws.max_row, 10).alignment = Alignment(wrap_text=True, vertical="top")
            flag = _FLAG_FILL.get(getattr(line, "flag", "") or "")
            if flag is not None:
                ws.cell(ws.max_row, 11).fill = flag
    _decision_columns(ws, 12)
    ws.auto_filter.ref = ws.dimensions
    _widths(ws, [26, 60, 10, 11, 13, 11, 44, 70, 16, 60, 10, 12, 50])


_FLAG_FILL = {"red": _RED, "yellow": PatternFill("solid", fgColor="FFFF99"), "orange": PatternFill("solid",
              fgColor="FFD8A8"), "green": _GREEN}


def _gem(ws, records) -> None:
    """The GEM's own checks, system by system: its Quick Scan, its System Explanation, its Contradiction and
    Assumption scan and its Self-QC table, as it answered them."""
    for record in records:
        _section_heading(ws, record.get("system") or "System")
        _append(ws, ["Quick Scan"])
        ws.cell(ws.max_row, 1).font = _BOLD
        for key, value in (record.get("quick_scan") or {}).items():
            _append(ws, [key.replace("_", " ").upper(), value])
        if record.get("explanation"):
            _append(ws, ["System Explanation", record["explanation"]])
            ws.cell(ws.max_row, 1).font = _BOLD
            ws.cell(ws.max_row, 2).alignment = Alignment(wrap_text=True, vertical="top")
        _append(ws, ["Contradictions and assumptions"])
        ws.cell(ws.max_row, 1).font = _BOLD
        contradictions = record.get("contradictions") or ()
        if not contradictions:
            _append(ws, ["", "No contradictions or unresolved assumptions identified."])
        for c in contradictions:
            _append(ws, [c.type, c.item, " / ".join(c.quotes), c.flag or None])
        _append(ws, ["Self-QC"])
        ws.cell(ws.max_row, 1).font = _BOLD
        for q in record.get("qc") or ():
            _append(ws, [q.check, q.evidence, "PASS" if q.passed else "FAIL", q.fix or None])
            ws.cell(ws.max_row, 3).fill = _GREEN if q.passed else _RED
        for title, key in (("Miscellaneous responsibilities", "misc_responsibilities"), ("Exclusions", "exclusions")):
            if record.get(key):
                _append(ws, [title, "\n".join(record[key])])
                ws.cell(ws.max_row, 1).font = _BOLD
        _append(ws, [])
    _widths(ws, [34, 80, 40, 30])


_PLAN_FILL = {"CONFIRMED": _GREEN, "CONFIRMED-on-plans": _AMBER, "ASSUMPTION": _AMBER, "DISCREPANCY": _RED,
              "PENDING": _RED}
_PLAN_COUNTS = ("schedule_rows", "quantity_column", "distinct_tags", "plan_placements", "riser")


def _families_text(system, check) -> str:
    """ "Dryer Exhaust Fan DXF-1-1, 2 (2); Make-up Air Fan MUAF-1-1, 2 (##)": each family with the count printed."""
    families = getattr(system, "families", ()) or ()
    checks = getattr(check, "families", ()) or ()
    out = []
    for n, family in enumerate(families):
        count = checks[n].quantity if n < len(checks) and checks[n].quantity is not None else family.quantity
        out.append(f"{family.header} ({'##' if count is None else count})")
    return "; ".join(out)


def _plan(ws, checks) -> None:
    """Every system the AI planned: its quantity, where it comes from and the words that state it,
    the counts it was checked against, and its category."""
    _headings(ws, ["Key", "System", "Kind", "Tags", "Quantity", "Category", "Quantity source", "Where",
                   "The words that state it", "Schedule rows", "QUANTITY column", "Distinct tags",
                   "Placements on the plans", "Riser", "Group", "Alternate", "Exception", "Goes in", "Why",
                   "Sequence section", "Families"])
    ws.freeze_panes = "A2"
    for check in checks:
        s = check.system
        tags = ", ".join(s.tags) if not isinstance(s.tags, str) else s.tags
        printed = getattr(check, "quantity", None)          # the count the header prints (the plan's, counted, panels)
        _append(ws, [s.key, s.header, s.kind, tags or None, printed if printed is not None else s.quantity, check.category, s.quantity_source or None,
                     check.where or None, s.quantity_quote or None,
                     *[check.columns.get(c) for c in _PLAN_COUNTS],
                     s.group or None, s.alternate or None, s.exception or None, check.goes, s.why or None,
                     getattr(s, "sequence_section", "") or None, _families_text(s, check) or None])
        fill = _PLAN_FILL.get(check.category)
        if fill is not None:
            ws.cell(ws.max_row, 6).fill = fill
        for column in (2, 9, 19):
            ws.cell(ws.max_row, column).alignment = Alignment(wrap_text=True, vertical="top")
    if not checks:
        _append(ws, ["", "The AI planned no system."])
    ws.auto_filter.ref = ws.dimensions
    _widths(ws, [12, 44, 26, 30, 10, 14, 14, 40, 50, 10, 10, 10, 12, 8, 20, 10, 40, 20, 50, 14, 50])
