"""The Evidence Package of the rebuilt app.

The estimator opens it to check every scope line against what the job's documents say. It is laid out for that job:

1. "Summary": the job at a glance (header, the numbers that need attention, one row per system with its lines,
   flagged lines, unknown quantities, findings and tech hours, each linked to its first scope line), the tab guide and
   the colour key.
2. "Scope lines": one row per printed device line and nothing else, so every filter works (EXCEL-01). Quantity is a
   number; who furnishes / installs / wires is colour coded; each row shows its open findings, its assumption and its
   first citation, with the full set on "Citations".
3. "Findings": every validator and QC finding left open, must fix first, each linked to its scope line.
4. "Counts": every family count with its sources and every other count, and how far apart they are.
5. "Citations": one row per citation (a device's refs, its quantity's sources and other counts, a family count's,
   a sequence passage, an exception), the same citation never twice for one line (EVID-01).
6. "System notes": what is not a device line: clarifications, systems left out with the writer's reason, sequence
   passages, exceptions and the open takeoff questions (internal, never for the client).

Then the old workbook's tabs (bid check, how the job was read, spec overview, the reading tabs, the catalogue), from
`estimator.evidence.workbook.write_evidence` (imported, not edited), restyled to match.

Plain data only: it writes what the Job holds, nothing is invented.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from estimator.evidence.workbook import write_evidence as write_old_evidence

from bms.model import Count, Device, Finding, Job, Ref, System
from bms.render import left_out_text

SUMMARY_TAB, SCOPE_TAB, FINDINGS_TAB = "Summary", "Scope lines", "Findings"
COUNTS_TAB, CITATIONS_TAB, NOTES_TAB = "Counts", "Citations", "System notes"
NEW_TABS = (SUMMARY_TAB, SCOPE_TAB, FINDINGS_TAB, COUNTS_TAB, CITATIONS_TAB, NOTES_TAB)

SCOPE_HEADINGS = ["#", "System", "Printed line", "Verb", "Furnished by", "Installed by", "Wired by", "Qty",
                  "Qty note", "Flag", "Open findings", "Assumption", "Cited at", "Quote", "Source ids", "Device",
                  "Slot", "Device id"]
FINDING_HEADINGS = ["#", "Severity", "Rule", "System", "Device id", "Printed line", "What", "Fix"]
COUNT_HEADINGS = ["System", "Family", "Tags", "Qty", "Counted from", "Other counts", "Spread", "Check"]
CITATION_HEADINGS = ["System", "Device id", "Line", "Used for", "Source id", "Sheet / section", "Document page",
                     "Quote"]
NOTE_HEADINGS = ["System", "Kind", "Text", "Cited at", "Quote"]
SYSTEM_HEADINGS = ["System", "Key", "Shape", "Control", "Alternate", "Equipment", "Lines", "Flagged",
                   "Qty unknown", "Must fix", "Check", "Tech hours", "Status"]

UNKNOWN_QTY = "Qty (##), not known"
WHOLE_JOB = "Whole job"
FRONT_END = "Front end"

# ---- look ----------------------------------------------------------------------------------------------------

FONT = "Calibri"
NAVY, INK, MUTED, RULE = "1F3864", "1F2937", "6B7280", "D0D7E2"
BAND = "F3F6FA"
_THIN = Side(style="thin", color=RULE)
_GRID = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
_HEAD_BOTTOM = Border(left=_THIN, right=_THIN, top=_THIN, bottom=Side(style="medium", color=NAVY))

PARTY_COLOURS = {                       # fill, text
    "AME": ("E3F4EA", "14532D"),
    "Unit Mfr.": ("FEF3C7", "92400E"),
    "Mechanical Contractor": ("FEF3C7", "92400E"),
    "Electrical Contractor": ("E0F2FE", "075985"),
    "FA": ("FCE7F3", "9D174D"),
    "Others": ("EDE9FE", "5B21B6"),
    "Owner": ("EDE9FE", "5B21B6"),
}
FLAG_COLOURS = {"quantity": ("FFEDD5", "9A3412"), "ownership": ("EDE9FE", "5B21B6"),
                "assumed": ("FEF9C3", "854D0E")}
SEVERITY_COLOURS = {"must_fix": ("FEE2E2", "991B1B"), "check": ("FEF3C7", "92400E")}
STATUS_COLOURS = {"Must fix": ("FEE2E2", "991B1B"), "Check": ("FEF3C7", "92400E"), "OK": ("E3F4EA", "14532D"),
                  "Left out": ("F3F4F6", "374151")}
TAB_COLOURS = {"estimate": NAVY, "reading": "0F766E", "catalogue": "9CA3AF"}
_READING = {"Bid check", "How the job was read", "Spec overview", "Equipment", "Schedules", "Devices on plans",
            "Notes", "Changes", "Sequence and points", "Job ledger", "Flags"}

_WIDTHS = {"#": 5, "System": 28, "Printed line": 60, "Verb": 16, "Furnished by": 21, "Installed by": 21,
           "Wired by": 21, "Qty": 7, "Qty note": 30, "Flag": 11, "Open findings": 34, "Assumption": 36,
           "Cited at": 26, "Quote": 46, "Source ids": 12, "Device": 30, "Slot": 16, "Device id": 12,
           "Severity": 10, "Rule": 26, "What": 52, "Fix": 44, "Family": 22, "Tags": 30, "Counted from": 30,
           "Other counts": 40, "Spread": 8, "Check": 30, "Line": 46, "Used for": 26, "Source id": 10,
           "Sheet / section": 18, "Document page": 26, "Kind": 22, "Text": 70, "Key": 8, "Shape": 22,
           "Control": 12, "Alternate": 10, "Equipment": 34, "Lines": 7, "Flagged": 8, "Qty unknown": 11,
           "Must fix": 9, "Tech hours": 10, "Status": 10}
_WRAP = {"System", "Printed line", "Qty note", "Open findings", "Assumption", "Quote", "What", "Fix", "Other counts",
         "Counted from", "Text", "Line", "Tags", "Equipment", "Check", "Device", "Cited at"}
_CENTRE = {"#", "Qty", "Flag", "Severity", "Source ids", "Source id", "Spread", "Lines", "Flagged", "Qty unknown",
           "Must fix", "Tech hours", "Status", "Key", "Alternate", "Control"}


def _fill(colour: str) -> PatternFill:
    return PatternFill("solid", fgColor=colour)


# ---- the rows (plain data, tested on their own) ---------------------------------------------------------------


def _ref(ref: Ref) -> str:
    return f'{ref.source_id or "-"} | {ref.where or "-"} | "{ref.quote}"'


def _unique(refs: Sequence[Ref]) -> list[Ref]:
    """The refs in order, each (source id, quote, where) once (EVID-01)."""
    seen: set[tuple[str, str, str]] = set()
    out: list[Ref] = []
    for ref in refs:
        key = (ref.source_id, ref.quote, ref.where)
        if key not in seen:
            seen.add(key)
            out.append(ref)
    return out


def split_where(where: str) -> tuple[str, str]:
    """"M-201, Drawings.pdf page 3" -> ("M-201", "Drawings.pdf page 3"); a where with no comma is all sheet."""
    head, sep, tail = (where or "").partition(",")
    return (head.strip(), tail.strip()) if sep else (head.strip(), "")


def quantity(count: Count) -> int | None:
    """The number the proposal prints (`Count.highest()`, estimator ruling D9); None when not known."""
    return count.highest()


def quantity_note(count: Count) -> str | None:
    """Why the quantity is what it is: unknown, or every other count with where it is."""
    if count.highest() is None:
        return UNKNOWN_QTY
    others = [f"{o.value} per {o.ref.where or o.ref.source_id}" for o in count.others]
    if not others:
        return None
    printed = count.highest()
    lead = f"{printed} printed (the highest)" if count.value != printed else f"{printed} printed"
    return f"{lead}; also " + "; ".join(others)


def _system_label(system: System) -> str:
    label = f"{system.name} ({system.key})"
    if system.alternate != "base":
        label += f", {system.alternate} alternate"
    return label


def _exception_label(job: Job, key: str) -> str:
    """An exception's System cell: the planned system's label when it names one (RUN-10), else its key as the
    exception names it, or "Whole job"."""
    for system in job.systems:
        if system.key == key:
            return _system_label(system)
    return key or WHOLE_JOB


def _findings_by_device(findings: Sequence[Finding]) -> dict[tuple[str, str], list[Finding]]:
    out: dict[tuple[str, str], list[Finding]] = defaultdict(list)
    for f in findings:
        if f.device_id:
            out[(f.system_key or "", f.device_id)].append(f)
    return out


def _owners(job: Job) -> list[tuple[str, str, Device]]:
    """(system key, label, device) for every device line, systems first, then the front end."""
    rows = [(s.key, _system_label(s), d) for s in job.systems for d in s.devices]
    if job.front_end is not None:
        rows += [("", FRONT_END, d) for d in job.front_end.devices]
    return rows


def scope_rows(job: Job, printed: dict[str, str] | None = None,
               findings: Sequence[Finding] = ()) -> list[list]:
    """The Scope lines rows: one per device line, systems in model order, then the front end. Nothing but device
    lines: counts, clarifications, left-out systems, sequences and exceptions are on their own tabs."""
    printed = printed or {}
    by_device = _findings_by_device(findings)
    rows: list[list] = []
    for n, (key, label, d) in enumerate(_owners(job), start=1):
        refs = _unique([*d.refs, *d.quantity.sources])
        first = refs[0]
        mine = by_device.get((key, d.id), []) or ([] if key else by_device.get(("", d.id), []))
        open_findings = "\n".join(f"[{'MUST FIX' if f.severity == 'must_fix' else 'check'}] {f.rule}: {f.what}"
                                  for f in mine) or None
        more = f" (+{len(refs) - 1} more)" if len(refs) > 1 else ""
        a = d.assumption
        rows.append([n, label, printed.get(d.id) or d.name, d.verb, d.furnished_by, d.installed_by, d.wired_by,
                     quantity(d.quantity), quantity_note(d.quantity), None if d.flag == "none" else d.flag,
                     open_findings, f"{a.what}. Why: {a.why}" if a is not None else None,
                     (first.where or "-") + more, first.quote,
                     ", ".join(dict.fromkeys(r.source_id for r in refs if r.source_id)) or None,
                     d.name, d.slot, d.id])
    return rows


def finding_rows(findings: Sequence[Finding], printed: dict[str, str] | None = None) -> list[list]:
    """Every finding, must fix first (otherwise in the order given)."""
    printed = printed or {}
    ordered = sorted(findings, key=lambda f: 0 if f.severity == "must_fix" else 1)
    return [[n, "Must fix" if f.severity == "must_fix" else "Check", f.rule, f.system_key or WHOLE_JOB, f.device_id,
             printed.get(f.device_id) if f.device_id else None, f.what, f.fix]
            for n, f in enumerate(ordered, start=1)]


def count_rows(job: Job) -> list[list]:
    rows: list[list] = []
    for system in job.systems:
        for family in system.families:
            c = family.count
            values = [v for v in (c.value, *(o.value for o in c.others)) if v is not None]
            spread = (max(values) - min(values)) if len(values) > 1 else 0
            check = None
            if c.highest() is None:
                check = "Not known: prints Qty (##)"
            elif spread:
                check = f"Sources disagree by {spread}: the higher prints"
            rows.append([_system_label(system), family.name, ", ".join(family.tags) or None, quantity(c),
                         "\n".join(r.where or r.source_id for r in _unique(c.sources)) or None,
                         "\n".join(f"{o.value} per {o.ref.where or o.ref.source_id}" for o in c.others) or None,
                         spread or None, check])
    return rows


def citation_rows(job: Job, printed: dict[str, str] | None = None) -> list[list]:
    """One row per citation and what it is used for; one citation used twice by a line is one row, its uses
    joined."""
    printed = printed or {}
    rows: list[list] = []

    def add(label, device_id, line, uses: list[tuple[str, Ref]]):
        merged: dict[tuple[str, str, str], list[str]] = {}
        for use, ref in uses:
            merged.setdefault((ref.source_id, ref.quote, ref.where), [])
            if use not in merged[(ref.source_id, ref.quote, ref.where)]:
                merged[(ref.source_id, ref.quote, ref.where)].append(use)
        for (source_id, quote, where), used in merged.items():
            sheet, page = split_where(where)
            rows.append([label, device_id, line, ", ".join(used), source_id or None, sheet or None, page or None,
                         quote])

    def device(label, d):
        add(label, d.id, printed.get(d.id) or d.name, [("calls for the line", r) for r in d.refs]
            + [("backs the quantity", r) for r in d.quantity.sources]
            + [(f"other count ({o.value})", o.ref) for o in d.quantity.others])

    for system in job.systems:                  # a system's counts, its sequence, then its lines, together
        label = _system_label(system)
        for family in system.families:
            c = family.count
            add(label, None, f"Count: {family.name}",
                [("family count", r) for r in c.sources]
                + [(f"other count ({o.value})", o.ref) for o in c.others])
        add(label, None, "Sequence of operation", [("sequence", r) for r in system.sequence_refs])
        for d in system.devices:
            device(label, d)
    if job.front_end is not None:
        for d in job.front_end.devices:
            device(FRONT_END, d)
    for exception in job.exceptions:
        add(_exception_label(job, exception.system_key), None, f"Exception: {exception.text}",
            [("exception", r) for r in exception.refs])
    return rows


def note_rows(job: Job) -> list[list]:
    """What is not a device line, system by system, then the front end, the exceptions and the open questions."""
    rows: list[list] = []
    for system in job.systems:
        label = _system_label(system)
        if not system.devices:              # it prints nothing in the proposal: the package says why
            rows.append([label, "Left out", left_out_text(system), None, None])
        for c in system.clarifications:
            rows.append([label, f"Clarification ({c.kind})", c.text, None, None])
        for r in _unique(system.sequence_refs):
            rows.append([label, "Sequence of operation", None, r.where, r.quote])
    if job.front_end is not None:
        for c in job.front_end.clarifications:
            rows.append([FRONT_END, f"Clarification ({c.kind})", c.text, None, None])
    for exception in job.exceptions:
        refs = _unique(exception.refs)
        rows.append([_exception_label(job, exception.system_key), "Exception", exception.text,
                     "\n".join(r.where for r in refs) or None, "\n".join(r.quote for r in refs) or None])
    for q in job.questions:
        rows.append([WHOLE_JOB, "Takeoff question (internal)", q, None, None])
    return rows


@dataclass(frozen=True)
class SystemSummary:
    label: str
    key: str
    shape: str
    control: str
    alternate: str
    equipment: str
    lines: int
    flagged: int
    unknown: int
    must_fix: int
    check: int
    tech_hours: float | None
    status: str


def _summary(label, key, shape, control, alternate, equipment, devices, tech_hours, findings) -> SystemSummary:
    must = sum(1 for f in findings if f.severity == "must_fix")
    check = len(findings) - must
    flagged = sum(1 for d in devices if d.flag != "none")
    unknown = sum(1 for d in devices if d.quantity.highest() is None)
    status = ("Must fix" if must else "Check" if (check or flagged or unknown) else
              "Left out" if not devices else "OK")
    return SystemSummary(label, key, shape, control, alternate, equipment, len(devices), flagged, unknown, must,
                         check, tech_hours, status)


def system_summaries(job: Job, findings: Sequence[Finding]) -> list[SystemSummary]:
    by_system: dict[str, list[Finding]] = defaultdict(list)
    for f in findings:
        by_system[f.system_key or ""].append(f)
    out = []
    for s in job.systems:
        equipment = "; ".join(f"{'##' if quantity(f.count) is None else quantity(f.count)} x {f.name}"
                              for f in s.families)
        out.append(_summary(_system_label(s), s.key, s.shape, s.control, s.alternate, equipment or None, s.devices,
                            s.tech_hours, by_system.get(s.key, [])))
    if job.front_end is not None or by_system.get(""):
        fe = job.front_end
        out.append(_summary(FRONT_END + " and whole job", "", "Front end", fe.mode if fe else "-", "base", None,
                            fe.devices if fe else (), fe.tech_hours if fe else None, by_system.get("", [])))
    return out


# ---- writing ---------------------------------------------------------------------------------------------------


def _header_row(ws: Worksheet, row: int, headings: list[str]) -> None:
    for col, heading in enumerate(headings, start=1):
        cell = ws.cell(row, col, heading)
        cell.font = Font(name=FONT, bold=True, color="FFFFFF", size=10)
        cell.fill = _fill(NAVY)
        cell.alignment = Alignment(horizontal="center" if heading in _CENTRE else "left", vertical="center",
                                   wrap_text=True)
        cell.border = _HEAD_BOTTOM
    ws.row_dimensions[row].height = 30


def _put(ws: Worksheet, row: int, col: int, value, heading: str, band: bool) -> None:
    cell = ws.cell(row, col)
    cell.value = value
    if isinstance(value, str) and value.startswith("="):
        cell.data_type = "s"
    cell.font = Font(name=FONT, size=10, color=INK)
    cell.border = _GRID
    cell.alignment = Alignment(horizontal="center" if heading in _CENTRE else "left", vertical="top",
                               wrap_text=heading in _WRAP)
    if band:
        cell.fill = _fill(BAND)


def _badge(cell, colours: tuple[str, str] | None, bold: bool = False) -> None:
    if colours is None:
        return
    fill, text = colours
    cell.fill = _fill(fill)
    cell.font = Font(name=FONT, size=10, color=text, bold=bold)


def _table(ws: Worksheet, headings: list[str], rows: list[list], start: int = 1, band_by: int | None = None,
           empty: str = "Nothing here.") -> tuple[int, int]:
    """A styled table at row `start`: navy header, grid, filters, frozen header. `band_by` (a 0-based column) shades
    every other run of rows that share that column (a system's lines read as one block). Returns (first data row,
    last data row)."""
    _header_row(ws, start, headings)
    if not rows:
        rows = [[empty] + [None] * (len(headings) - 1)]
    band, last = False, object()
    for i, row in enumerate(rows):
        r = start + 1 + i
        if band_by is not None and row[band_by] != last:
            band, last = (not band if i else False), row[band_by]
        for col, (heading, value) in enumerate(zip(headings, row), start=1):
            _put(ws, r, col, value, heading, band)
    end = start + len(rows)
    for col, heading in enumerate(headings, start=1):
        ws.column_dimensions[get_column_letter(col)].width = _WIDTHS.get(heading, 18)
    ws.freeze_panes = ws.cell(start + 1, 1)
    ws.auto_filter.ref = f"A{start}:{get_column_letter(len(headings))}{end}"
    ws.sheet_view.zoomScale = 90
    ws.sheet_view.showGridLines = False
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = f"{start}:{start}"
    return start + 1, end


def _col(headings: list[str], name: str) -> int:
    return headings.index(name) + 1


def _write_scope(ws: Worksheet, rows: list[list]) -> dict[str, int]:
    """The Scope lines tab; returns the row of each device id (for links)."""
    first, last = _table(ws, SCOPE_HEADINGS, rows, band_by=1, empty="No scope lines were written.")
    at = {h: _col(SCOPE_HEADINGS, h) for h in SCOPE_HEADINGS}
    rows_of: dict[str, int] = {}
    for i, row in enumerate(rows):
        r = first + i
        rows_of.setdefault(row[-1], r)
        for name in ("Furnished by", "Installed by", "Wired by"):
            _badge(ws.cell(r, at[name]), PARTY_COLOURS.get(row[at[name] - 1]))
        _badge(ws.cell(r, at["Flag"]), FLAG_COLOURS.get(row[at["Flag"] - 1]), bold=True)
        qty = ws.cell(r, at["Qty"])
        if row[at["Qty"] - 1] is None:
            qty.value = "##"
            _badge(qty, FLAG_COLOURS["quantity"], bold=True)
        else:
            qty.number_format = "0"
            qty.font = Font(name=FONT, size=10, color=INK, bold=True)
        if row[at["Open findings"] - 1]:
            severe = "[MUST FIX]" in row[at["Open findings"] - 1]
            _badge(ws.cell(r, at["Open findings"]), SEVERITY_COLOURS["must_fix" if severe else "check"])
        for name in ("Device", "Slot", "Device id", "Source ids", "#"):
            ws.cell(r, at[name]).font = Font(name=FONT, size=9, color=MUTED)
        ws.cell(r, at["Quote"]).font = Font(name=FONT, size=10, color=INK, italic=True)
    if rows:
        ws.column_dimensions.group(get_column_letter(at["Device"]), get_column_letter(at["Device id"]),
                                   hidden=False, outline_level=1)
    return rows_of


def _link(cell, sheet: str, row: int) -> None:
    cell.hyperlink = f"#'{sheet}'!A{row}"
    cell.font = Font(name=FONT, size=cell.font.size or 10, color="1D4ED8", underline="single",
                     bold=cell.font.bold)


def _write_findings(ws: Worksheet, rows: list[list], device_rows: dict[str, int]) -> None:
    first, _ = _table(ws, FINDING_HEADINGS, rows, empty="No findings left open.")
    sev, dev = _col(FINDING_HEADINGS, "Severity"), _col(FINDING_HEADINGS, "Device id")
    for i, row in enumerate(rows):
        r = first + i
        _badge(ws.cell(r, sev), SEVERITY_COLOURS["must_fix" if row[sev - 1] == "Must fix" else "check"], bold=True)
        if row[dev - 1] in device_rows:
            _link(ws.cell(r, dev), SCOPE_TAB, device_rows[row[dev - 1]])


def _write_counts(ws: Worksheet, rows: list[list]) -> None:
    first, _ = _table(ws, COUNT_HEADINGS, rows, band_by=0, empty="No equipment families were planned.")
    qty, check = _col(COUNT_HEADINGS, "Qty"), _col(COUNT_HEADINGS, "Check")
    for i, row in enumerate(rows):
        r = first + i
        if row[qty - 1] is None:
            ws.cell(r, qty).value = "##"
        ws.cell(r, qty).font = Font(name=FONT, size=10, bold=True, color=INK)
        if row[check - 1]:
            _badge(ws.cell(r, check), FLAG_COLOURS["quantity"])


def _write_citations(ws: Worksheet, rows: list[list], device_rows: dict[str, int]) -> None:
    first, _ = _table(ws, CITATION_HEADINGS, rows, band_by=2, empty="No citations.")
    dev, quote = _col(CITATION_HEADINGS, "Device id"), _col(CITATION_HEADINGS, "Quote")
    for i, row in enumerate(rows):
        r = first + i
        ws.cell(r, quote).font = Font(name=FONT, size=10, italic=True, color=INK)
        if row[dev - 1] in device_rows:
            _link(ws.cell(r, dev), SCOPE_TAB, device_rows[row[dev - 1]])


def _write_notes(ws: Worksheet, rows: list[list]) -> None:
    first, _ = _table(ws, NOTE_HEADINGS, rows, band_by=0, empty="No notes.")
    kind = _col(NOTE_HEADINGS, "Kind")
    for i, row in enumerate(rows):
        if row[kind - 1] == "Takeoff question (internal)":
            _badge(ws.cell(first + i, kind), SEVERITY_COLOURS["check"], bold=True)
        elif row[kind - 1] == "Left out":
            _badge(ws.cell(first + i, kind), STATUS_COLOURS["Left out"], bold=True)


_GUIDE = [
    (SCOPE_TAB, "Every printed line: who furnishes, installs and wires it, the quantity, its findings and its "
                "first citation."),
    (FINDINGS_TAB, "What the checks and the QC reviewer left open, must fix first."),
    (COUNTS_TAB, "Each equipment count, where it was counted, and every other count the documents give."),
    (CITATIONS_TAB, "Every quote each line rests on, one per row: filter by sheet or source id."),
    (NOTES_TAB, "Clarifications, systems left out and why, sequences, exceptions and the internal takeoff "
                "questions."),
    ("Bid check", "The tool's first reading of the bid documents (teal tabs: how the job was read; grey: the "
                  "document catalogue)."),
]


def _kpi(ws: Worksheet, row: int, first: int, last: int, label: str, value,
         colours: tuple[str, str] | None = None) -> None:
    """A number tile over columns first..last, two rows high: the number, then what it counts."""
    fill, text = colours or ("F3F6FA", NAVY)
    if last > first:
        ws.merge_cells(start_row=row, start_column=first, end_row=row, end_column=last)
        ws.merge_cells(start_row=row + 1, start_column=first, end_row=row + 1, end_column=last)
    top, bottom = ws.cell(row, first), ws.cell(row + 1, first)
    top.value, bottom.value = value, label
    top.font = Font(name=FONT, size=20, bold=True, color=text)
    bottom.font = Font(name=FONT, size=9, color=MUTED)
    white = Side(style="thick", color="FFFFFF")
    for r in (row, row + 1):
        for c in range(first, last + 1):
            ws.cell(r, c).fill = _fill(fill)
            ws.cell(r, c).border = Border(left=white if c == first else None, right=white if c == last else None)
    top.alignment = Alignment(horizontal="center", vertical="bottom")
    bottom.alignment = Alignment(horizontal="center", vertical="top", wrap_text=True)


# the tiles' columns on the Summary (balanced against the systems table's widths)
_TILES = [(1, 1), (2, 3), (4, 5), (6, 6), (7, 9), (10, 11), (12, 13)]


def _write_summary(ws: Worksheet, job: Job, findings: Sequence[Finding], summaries: list[SystemSummary],
                   device_rows: dict[str, int], first_device: dict[str, str]) -> None:
    ws.sheet_view.showGridLines = False
    ws.sheet_view.zoomScale = 90
    ncols = len(SYSTEM_HEADINGS)

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncols)
    title = ws.cell(1, 1, f"Evidence Package — {job.name}")
    title.font = Font(name=FONT, size=18, bold=True, color="FFFFFF")
    title.alignment = Alignment(vertical="center", indent=1)
    for c in range(1, ncols + 1):
        ws.cell(1, c).fill = _fill(NAVY)
    ws.row_dimensions[1].height = 34

    h = job.header
    facts = [("Quote", h.quote_number if h else None), ("Reference", h.reference if h else None),
             ("MEP engineer", h.mep_engineer if h else None), ("Date", h.date if h else None),
             ("Based on", "; ".join(h.based_on) if h and h.based_on else None),
             ("Written", dt.datetime.now().strftime("%Y-%m-%d %H:%M"))]
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=ncols)
    line = ws.cell(2, 1, "   ·   ".join(f"{k}: {v}" for k, v in facts if v))
    line.font = Font(name=FONT, size=10, color=MUTED)
    line.alignment = Alignment(indent=1, vertical="center", wrap_text=True)
    ws.row_dimensions[2].height = 30

    devices = [d for _, _, d in _owners(job)]
    must = sum(1 for f in findings if f.severity == "must_fix")
    hours = [s.tech_hours for s in summaries if s.tech_hours is not None]
    red, amber, green = SEVERITY_COLOURS["must_fix"], SEVERITY_COLOURS["check"], STATUS_COLOURS["OK"]
    kpis = [("Systems", len(job.systems), None),
            ("Scope lines", len(devices), None),
            ("Must fix", must, red if must else green),
            ("Checks", len(findings) - must, amber if len(findings) - must else green),
            ("Flagged lines", sum(1 for d in devices if d.flag != "none"), None),
            ("Lines with Qty (##)", sum(1 for d in devices if d.quantity.highest() is None), None),
            ("Tech hours", sum(hours) if hours else "-", None)]
    for (first, last), (label, value, colours) in zip(_TILES, kpis):
        _kpi(ws, 4, first, last, label, value, colours)
    ws.row_dimensions[4].height = 30
    ws.row_dimensions[5].height = 26

    start = 7
    ws.cell(start, 1, "Systems").font = Font(name=FONT, size=12, bold=True, color=NAVY)
    rows = [[s.label, s.key or "-", s.shape, s.control, s.alternate, s.equipment, s.lines, s.flagged, s.unknown,
             s.must_fix, s.check, s.tech_hours, s.status] for s in summaries]
    rows.append(["Total", None, None, None, None, None, sum(s.lines for s in summaries),
                 sum(s.flagged for s in summaries), sum(s.unknown for s in summaries),
                 sum(s.must_fix for s in summaries), sum(s.check for s in summaries),
                 sum(hours) if hours else None, None])
    first, last = _table(ws, SYSTEM_HEADINGS, rows, start=start + 1)
    ws.freeze_panes = None
    ws.auto_filter.ref = None
    for col, width in enumerate(_SUMMARY_WIDTHS, start=1):
        ws.column_dimensions[get_column_letter(col)].width = width
    status = _col(SYSTEM_HEADINGS, "Status")
    for i, s in enumerate(summaries):
        r = first + i
        _badge(ws.cell(r, status), STATUS_COLOURS.get(s.status), bold=True)
        if s.must_fix:
            _badge(ws.cell(r, _col(SYSTEM_HEADINGS, "Must fix")), SEVERITY_COLOURS["must_fix"], bold=True)
        target = first_device.get(s.key)
        if target in device_rows:
            _link(ws.cell(r, 1), SCOPE_TAB, device_rows[target])
        ws.cell(r, _col(SYSTEM_HEADINGS, "Tech hours")).number_format = "0.0"
    for c in range(1, ncols + 1):
        cell = ws.cell(last, c)
        cell.font = Font(name=FONT, size=10, bold=True, color=NAVY)
        cell.fill = _fill("E5EAF2")
        cell.border = Border(top=Side(style="medium", color=NAVY), bottom=_THIN, left=_THIN, right=_THIN)
    ws.cell(last, _col(SYSTEM_HEADINGS, "Tech hours")).number_format = "0.0"

    r = last + 2
    ws.cell(r, 1, "The tabs").font = Font(name=FONT, size=12, bold=True, color=NAVY)
    for tab, words in _GUIDE:
        r += 1
        cell = ws.cell(r, 1, tab)
        _link(cell, tab, 1)
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=ncols)
        ws.cell(r, 2, words).font = Font(name=FONT, size=10, color=INK)
        ws.cell(r, 2).alignment = Alignment(wrap_text=True, vertical="top")

    r += 2
    ws.cell(r, 1, "Colour key").font = Font(name=FONT, size=12, bold=True, color=NAVY)
    key = [("AME", PARTY_COLOURS["AME"]), ("Unit Mfr. / Mechanical", PARTY_COLOURS["Mechanical Contractor"]),
           ("Electrical", PARTY_COLOURS["Electrical Contractor"]), ("FA", PARTY_COLOURS["FA"]),
           ("Others / Owner", PARTY_COLOURS["Others"]), ("Must fix", SEVERITY_COLOURS["must_fix"]),
           ("Check / quantity", FLAG_COLOURS["quantity"]), ("Assumed", FLAG_COLOURS["assumed"])]
    for i, (label, colours) in enumerate(key):
        cell = ws.cell(r + 1 + i // 4, (1, 3, 6, 7)[i % 4])
        cell.value = label
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = Border(left=Side(style="thick", color="FFFFFF"), right=Side(style="thick", color="FFFFFF"),
                             top=Side(style="thick", color="FFFFFF"), bottom=Side(style="thick", color="FFFFFF"))
        _badge(cell, colours, bold=True)
        if i % 4 == 3:
            ws.merge_cells(start_row=cell.row, start_column=7, end_row=cell.row, end_column=9)
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True


_OLD_HEADING_FILL = "D9E1F2"
_SUMMARY_WIDTHS = [34, 8, 22, 12, 10, 34, 7, 8, 11, 9, 8, 10, 10]


def _restyle_old(ws: Worksheet) -> None:
    """The old tabs in the same look: navy headings, one font, no gridlines noise, a tab colour."""
    ws.sheet_view.zoomScale = 90
    for row in ws.iter_rows():
        for cell in row:
            fill = cell.fill.fgColor.rgb if cell.fill is not None and cell.fill.fill_type == "solid" else None
            if isinstance(fill, str) and fill.upper().endswith(_OLD_HEADING_FILL):
                cell.fill = _fill(NAVY)
                cell.font = Font(name=FONT, size=10, bold=True, color="FFFFFF")
            elif cell.value is not None:
                f = cell.font
                cell.font = Font(name=FONT, size=f.size if f.size and f.size > 11 else 10, bold=f.bold,
                                 italic=f.italic, color=f.color)
            if isinstance(cell.value, str) and len(cell.value) > 60 and cell.alignment.wrap_text is not True:
                cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True


def write_evidence(path: Path, catalogue, reading, ledger, job: Job, findings: Sequence[Finding] = (),
                   printed: dict[str, str] | None = None) -> Path:
    """The Evidence Package at `path`: the Summary and the Job's tabs first, then the old workbook (from the
    catalogue, reading and ledger), restyled. `printed` maps a device id to its printed line (from `bms.render`)."""
    path = Path(path)
    printed = printed or {}
    write_old_evidence(path, catalogue, reading, ledger=ledger)
    book = load_workbook(str(path))
    old = list(book.sheetnames)
    sheets = {title: book.create_sheet(title, at) for at, title in enumerate(NEW_TABS)}

    scope = scope_rows(job, printed, findings)
    device_rows = _write_scope(sheets[SCOPE_TAB], scope)
    _write_findings(sheets[FINDINGS_TAB], finding_rows(findings, printed), device_rows)
    _write_counts(sheets[COUNTS_TAB], count_rows(job))
    _write_citations(sheets[CITATIONS_TAB], citation_rows(job, printed), device_rows)
    _write_notes(sheets[NOTES_TAB], note_rows(job))
    first_device = {s.key: s.devices[0].id for s in job.systems if s.devices}
    if job.front_end is not None and job.front_end.devices:
        first_device[""] = job.front_end.devices[0].id
    _write_summary(sheets[SUMMARY_TAB], job, findings, system_summaries(job, findings), device_rows, first_device)

    for title in NEW_TABS:
        sheets[title].sheet_properties.tabColor = TAB_COLOURS["estimate"]
    for title in old:
        ws = book[title]
        _restyle_old(ws)
        ws.sheet_properties.tabColor = TAB_COLOURS["reading" if title in _READING else "catalogue"]
    book.active = 0
    for ws in book.worksheets:
        ws.sheet_view.tabSelected = ws.title == SUMMARY_TAB
    book.save(str(path))
    return path
