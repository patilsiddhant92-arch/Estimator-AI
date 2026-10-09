"""The 4-tab Evidence workbook (critique.md, "Evidence Package, 22 tabs -> 4").

1. Summary            the job, base and alternate totals (lines, tech hours, price or PRICE PENDING), the coverage
                      gate result and how many decisions are open. Totals only: no per-line or per-block rows.
2. Scope              one row per printed line, under a header row per block (the block's qty and tech hours), and
                      the block's printed "*" / "**" notes. Qty, verb, owners, unit and extended price, source sheet
                      and source ids. No quotes (they are on Sources).
3. Questions & Flags  one list: coverage gaps, count gaps, flagged lines (with the assumption's why), the job's
                      questions, ledger contradictions. Severity first. Source ids, no quotes.
4. Sources            one citation table: source id, sheet, document page, quote, and what uses it.

Marks are coloured the house way: ** red EE0000, *Confirm orange ED7D31, *Assumed blue 2F5597.
`write_debug()` writes the raw ledger and the full coverage table to a separate workbook.
"""
from __future__ import annotations

from collections import OrderedDict
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from . import appio
from .concepts import LABELS

RED, ORANGE, BLUE = "EE0000", "ED7D31", "2F5597"
HEAD_FILL = PatternFill("solid", fgColor="1F3864")
BLOCK_FILL = PatternFill("solid", fgColor="D9E1F2")
MUST_FILL = PatternFill("solid", fgColor="FCE4E4")
HEAD_FONT = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
BODY_FONT = Font(name="Calibri", size=10)
BOLD = Font(name="Calibri", size=10, bold=True)
THIN = Border(bottom=Side(style="thin", color="BFBFBF"))
WRAP = Alignment(wrap_text=True, vertical="top")
TOP = Alignment(vertical="top")
PENDING = "PRICE PENDING"


def mark_of(text: str) -> tuple[str, str | None]:
    """("**", red) / ("*Confirm", orange) / ("*Assumed", blue) / ("*", None) for a note's text."""
    t = (text or "").lstrip()
    if t.startswith("**"):
        return "**", RED
    low = t.lower()
    if low.startswith("*confirm"):
        return "*Confirm", ORANGE
    if low.startswith("*assumed"):
        return "*Assumed", BLUE
    return ("*", None) if t.startswith("*") else ("", None)


def _flag_mark(flag: str) -> tuple[str, str | None]:
    if flag in ("quantity", "ownership"):
        return "*Confirm", ORANGE
    if flag == "assumed":
        return "*Assumed", BLUE
    return "", None


def _note_text(c: dict) -> str:
    kind, text = c.get("kind", ""), c.get("text", "")
    lead = {"confirm": "*Confirm", "assumed": "*Assumed:", "per_drawings": "*Per drawings:", "note": "**"}.get(kind, "*")
    return f"{lead} {text}".strip()


# ---- sheet helpers ------------------------------------------------------------------------------------------


def _table(ws, headings: list[str], widths: list[int], freeze: str = "A2") -> None:
    ws.append(headings)
    for col, (h, w) in enumerate(zip(headings, widths), 1):
        cell = ws.cell(1, col)
        cell.font, cell.fill, cell.alignment = HEAD_FONT, HEAD_FILL, Alignment(vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(col)].width = w
    ws.row_dimensions[1].height = 28
    ws.freeze_panes = freeze


def _finish(ws, ncols: int, wrap_cols: set[int]) -> None:
    for row in ws.iter_rows(min_row=2, max_row=ws.max_row, max_col=ncols):
        for cell in row:
            if cell.font is None or not cell.font.bold:
                cell.font = Font(name="Calibri", size=10, color=cell.font.color if cell.font else None,
                                 bold=cell.font.bold if cell.font else False)
            cell.alignment = WRAP if cell.column in wrap_cols else TOP
            cell.border = THIN
    if ws.max_row >= 1:
        ws.auto_filter.ref = f"A1:{get_column_letter(ncols)}{max(ws.max_row, 2)}"


def _colour(cell, colour: str | None, bold: bool = False) -> None:
    if colour:
        cell.font = Font(name="Calibri", size=10, color=colour, bold=bold)


# ---- the content --------------------------------------------------------------------------------------------


class _Cites:
    """Every citation used, keyed (source id, quote), with what uses it."""

    def __init__(self, ledger: dict) -> None:
        self.ledger = ledger
        self.rows: "OrderedDict[tuple[str, str], dict]" = OrderedDict()

    def add(self, source_id: str, quote: str, where: str, used_by: str) -> str:
        sid = str(source_id or "").strip().strip("[]")
        if not sid:
            return ""
        where = appio.where(self.ledger, sid) or where or ""
        key = (sid, " ".join(str(quote or "").split()))
        row = self.rows.setdefault(key, {"id": sid, "where": where, "quote": key[1], "used": []})
        if used_by and used_by not in row["used"]:
            row["used"].append(used_by)
        return sid


def _evidence(ledger: dict, refs, limit: int = 4) -> str:
    """The proof itself, readable without chasing ids: one line per citation, 'Where: "quote"'."""
    out = []
    for r in refs or []:
        quote = " ".join(str(r.get("quote") or "").split())
        where = appio.where(ledger, str(r.get("source_id", "")).strip("[]")) or r.get("where", "") or ""
        if not quote and not where:
            continue
        text = f'{where}: \u201c{quote}\u201d' if quote else where
        if text not in out:
            out.append(text)
    more = len(out) - limit
    return "\n".join(out[:limit] + ([f"(+{more} more)"] if more > 0 else []))


def _tag_run(tags: list[str]) -> str:
    """"VAV-1 thru VAV-15" for a long run of tags, else the tags joined."""
    return f"{tags[0]} thru {tags[-1]}" if len(tags) > 4 else ", ".join(tags)


def _sheet_of(ledger: dict, refs) -> str:
    sheets = []
    for r in refs or []:
        sheet, _ = appio.split_where(appio.where(ledger, r.get("source_id", "")) or r.get("where", ""))
        if sheet and sheet not in sheets:
            sheets.append(sheet)
    return ", ".join(sheets)


def build(job: dict, ledger: dict, coverage=None, printed: dict[str, str] | None = None, prices=None,
          notes: dict[str, list[str]] | None = None) -> dict:
    """Everything the four tabs show, as plain rows (tested on its own; `write` only lays it out). `notes` are the
    block notes as the app prints them (`appio.printed_notes`); without them the raw clarifications are shown and the
    lines' assumptions go to Questions & Flags instead."""
    if printed is None:
        printed = appio.printed_texts(job)
        notes = appio.printed_notes(job) if notes is None else notes
    prices = prices if prices is not None else appio.Prices()
    cites = _Cites(ledger)
    lines = appio.job_lines(job, printed)
    by_system: dict[str, list] = {}
    for line in lines:
        by_system.setdefault(line.system_key, []).append(line)

    scope, questions = [], []
    totals = {"base": {"lines": 0, "hours": 0.0, "priced": 0.0, "pending": 0},
              "add": {"lines": 0, "hours": 0.0, "priced": 0.0, "pending": 0},
              "deduct": {"lines": 0, "hours": 0.0, "priced": 0.0, "pending": 0}}
    n = 0
    fe = job.get("front_end") or {}
    blocks = [("FE", "Front end" + (f" ({fe.get('mode')}: {fe.get('existing_system_name')})"
                                    if fe.get("existing_system_name") else ""), "base", None, fe.get("tech_hours"),
               fe.get("clarifications") or [], None)]
    for s in job.get("systems") or []:
        tags = ", ".join(_tag_run(f.get("tags") or []) for f in s.get("families") or [] if f.get("tags"))
        blocks.append((s.get("key", ""), f"{s.get('name', '')} {tags}".strip(), s.get("alternate", "base"),
                       appio.system_quantity(s), s.get("tech_hours"), s.get("clarifications") or [],
                       s.get("no_scope_reason") if not s.get("devices") else None))
    for key, name, alternate, qty, hours, block_notes, left_out in blocks:
        rows = by_system.get(key, [])
        if not rows and not block_notes and not (notes or {}).get(key) and not left_out and key == "FE":
            continue
        t = totals.setdefault(alternate, {"lines": 0, "hours": 0.0, "priced": 0.0, "pending": 0})
        t["hours"] += float(hours or 0)
        scope.append({"type": "block", "block": key, "text": f"{name}" + (" (left out)" if left_out else ""),
                      "alternate": alternate, "qty": qty, "hours": hours})
        for line in rows:
            n += 1
            sids = [cites.add(r.get("source_id"), r.get("quote"), r.get("where"), line.id) for r in line.refs]
            unit = prices.unit(line.text)
            ext = unit * line.quantity if unit is not None and line.quantity is not None else None
            mark, colour = _flag_mark(line.flag)
            t["lines"] += 1
            if ext is None:
                t["pending"] += 1
            else:
                t["priced"] += ext
            scope.append({"type": "line", "n": n, "id": line.id, "block": key, "text": line.text, "verb": line.verb,
                          "furnished": line.furnished_by, "installed": line.installed_by, "wired": line.wired_by,
                          "qty": line.quantity, "unit": unit, "ext": ext, "mark": mark, "colour": colour,
                          "sheet": _sheet_of(ledger, line.refs), "sources": ", ".join(s for s in sids if s),
                          "evidence": _evidence(ledger, line.refs),
                          "alternate": alternate})
            if line.flag != "none":
                shown = notes is not None and line.assumption      # the *Assumed note on Scope carries the why
                questions.append({"severity": "Check", "kind": f"Line flag: {line.flag}", "block": key,
                                  "about": f"Scope #{n}: {line.text}",
                                  "what": (f"{line.flag} to confirm (the reason is in the block's *Assumed note)"
                                           if shown else line.assumption or f"{line.flag} to confirm"),
                                  "fix": "Confirm or change the line on review.",
                                  "sources": ", ".join(s for s in sids if s),
                                  "evidence": _evidence(ledger, line.refs)})
        texts = (notes or {}).get(key, []) if notes is not None else [_note_text(c) for c in block_notes]
        for text in texts:
            mark, colour = mark_of(text)
            scope.append({"type": "note", "block": key, "text": text, "mark": mark, "colour": colour,
                          "alternate": alternate})
        if left_out:
            scope.append({"type": "note", "block": key, "text": f"Left out: {left_out}", "mark": "", "colour": None,
                          "alternate": alternate})

    if coverage is not None:
        for f in coverage.unaccounted:
            sid = cites.add(f.source_id, f.quote, f.citation, f.fact_id)
            sug = "; ".join(f"{g.line_id} {g.text}" + (f" [{g.ruling}]" if g.ruling else "")
                            for g in f.suggestions[:2])
            questions.append({"severity": "Must fix" if f.severity == "must_fix" else "Check",
                              "kind": "Coverage: not in the proposal" if f.status == "unaccounted"
                              else "Coverage: partly in the proposal",
                              "block": ", ".join(sorted({c.sink_id.split(".")[0] for c in f.covered_by})) or "",
                              "about": f.fact_id,
                              "what": f"{f.subject} = {f.value}. Missing: "
                                      + ", ".join(LABELS.get(c, c) for c in f.uncovered),
                              "fix": (f"Add a line ({sug})" if sug else "Add a line, an exception, a clarification "
                                      "or dismiss it with a reason."), "sources": sid,
                              "evidence": _evidence(ledger, [{"source_id": f.source_id, "quote": f.quote,
                                                              "where": f.citation}])})
        for g in coverage.count_gaps:
            fact = next((f for f in coverage.facts if f.fact_id == g["fact_id"]), None)
            sid = cites.add(fact.source_id, fact.quote, fact.citation, g["fact_id"]) if fact else ""
            questions.append({"severity": "Must fix" if g.get("severity") == "must_fix" else "Check",
                              "kind": f"Count gap ({g.get('ruling', '')})", "block": ", ".join(
                sorted({i.split('.')[0] for i in g["lines"]})), "about": f"{g['fact_id']} vs {', '.join(g['lines'])}",
                "what": f"{g['label']}: the documents count {g['fact_count']}, the proposal prints {g['printed']}.",
                "fix": "Confirm the count; the higher count prints unless a ruling says otherwise.", "sources": sid,
                "evidence": _evidence(ledger, [{"source_id": fact.source_id, "quote": fact.quote,
                                                "where": fact.citation}]) if fact else ""})
        for rf in coverage.rulings:
            scope_n = next((r["n"] for r in scope if r["type"] == "line" and r["id"] == rf.line_id), None)
            questions.append({"severity": "Must fix" if rf.severity == "must_fix" else "Check",
                              "kind": f"Against ruling {rf.ruling}", "block": rf.line_id.split(".")[0],
                              "about": (f"Scope #{scope_n}: " + next((r["text"] for r in scope if r["type"] == "line"
                                                                       and r["id"] == rf.line_id), ""))
                              if scope_n else rf.line_id,
                              "what": rf.what, "fix": rf.fix, "sources": ""})
    for q in job.get("questions") or []:
        questions.append({"severity": "Check", "kind": "Question", "block": "", "about": "",
                          "what": q if isinstance(q, str) else str(q), "fix": "", "sources": ""})
    for e in job.get("exceptions") or []:
        sids = [cites.add(r.get("source_id"), r.get("quote"), r.get("where"), f"exception {e.get('system_key')}")
                for r in e.get("refs") or []]
        questions.append({"severity": "Check", "kind": "Exception printed", "block": e.get("system_key", ""),
                          "about": "", "what": e.get("text", ""), "fix": "Confirm the exception.",
                          "sources": ", ".join(s for s in sids if s)})
    for f in appio.fact_list(ledger):
        for c in f.get("contradictions") or []:
            s1 = cites.add(f.get("source_id"), f.get("quote"), "", f["id"])
            s2 = cites.add(c.get("source_id"), c.get("quote"), "", f["id"])
            questions.append({"severity": "Check", "kind": "Sources disagree", "block": f.get("subject", ""),
                              "about": f["id"], "what": f"{f.get('subject')}: {f.get('value')} vs {c.get('value')} "
                              f"({c.get('stage')})", "fix": "The higher count prints; confirm.",
                              "sources": ", ".join(x for x in (s1, s2) if x),
                              "evidence": _evidence(ledger, [f, c])})
    order = {"Must fix": 0, "Check": 1}
    questions.sort(key=lambda q: order.get(q["severity"], 2))
    header = job.get("header") or {}
    summary = {"job": job.get("name") or ledger.get("job_name", ""), "quote": header.get("quote_number", ""),
               "reference": header.get("reference", ""), "date": header.get("date", ""),
               "based_on": ", ".join(header.get("based_on") or []), "totals": totals,
               "coverage": None if coverage is None else coverage.summary(),
               "must_fix": sum(q["severity"] == "Must fix" for q in questions),
               "checks": sum(q["severity"] == "Check" for q in questions),
               "notes_to_confirm": sum(1 for r in scope if r["type"] == "note" and r["mark"] == "*Confirm")}
    return {"summary": summary, "scope": scope, "questions": questions, "sources": list(cites.rows.values())}


# ---- writing ------------------------------------------------------------------------------------------------


def _money(ws, cell, value) -> None:
    cell.value = value
    cell.number_format = '"$"#,##0.00'


def write(path, job: dict, ledger: dict, coverage=None, printed=None, prices=None, notes=None) -> Path:
    data = build(job, ledger, coverage, printed, prices, notes)
    wb = Workbook()

    # 1. Summary
    ws = wb.active
    ws.title = "Summary"
    s = data["summary"]
    ws.column_dimensions["A"].width = 24
    for col, width in zip("BCDE", (22, 14, 16, 24)):
        ws.column_dimensions[col].width = width
    ws["A1"] = f"Evidence: {s['job']}"
    ws["A1"].font = Font(name="Calibri", size=14, bold=True)
    info = [("Quote", s["quote"]), ("Reference", s["reference"]), ("Date", s["date"]), ("Based on", s["based_on"])]
    r = 3
    for k, v in info:
        ws.cell(r, 1, k).font = BOLD
        ws.cell(r, 2, v).font = BODY_FONT
        r += 1
    r += 1
    for col, h in enumerate(["Bid part", "Scope lines", "Tech hours", "Priced total", "Price pending lines"], 1):
        c = ws.cell(r, col, h)
        c.font, c.fill = HEAD_FONT, HEAD_FILL
    for part in ("base", "add", "deduct"):
        t = s["totals"].get(part)
        if not t or (part != "base" and not t["lines"] and not t["hours"]):
            continue
        r += 1
        ws.cell(r, 1, {"base": "Base bid", "add": "Add alternates", "deduct": "Deduct alternates"}[part])
        ws.cell(r, 2, t["lines"])
        ws.cell(r, 3, t["hours"] or None)
        _money(ws, ws.cell(r, 4), t["priced"] or None)
        pend = ws.cell(r, 5, f"{t['pending']} {PENDING}" if t["pending"] else "none")
        if t["pending"]:
            _colour(pend, ORANGE, True)
    r += 2
    ws.cell(r, 1, "Coverage gate").font = BOLD
    cov = s["coverage"]
    if cov is None:
        ws.cell(r, 2, "not run")
    else:
        c = ws.cell(r, 2, "PASS" if cov["passed"] else "FAIL")
        _colour(c, None if cov["passed"] else RED, True)
        ws.cell(r, 3, f"{cov['relevant_facts']} controls facts: {cov['accounted']} accounted, {cov['dismissed']} "
                      f"dismissed, {cov['partial'] + cov['unaccounted']} open ({cov['must_fix']} must fix); "
                      f"{cov['count_gaps']} count gaps; {cov['ruling_flags']} lines against the rulings")
    r += 1
    ws.cell(r, 1, "Decisions needed").font = BOLD
    c = ws.cell(r, 2, f"{s['must_fix']} must fix, {s['checks']} to check (Questions & Flags); "
                      f"{s['notes_to_confirm']} *Confirm notes (Scope)")
    _colour(c, RED if s["must_fix"] else None, bool(s["must_fix"]))
    r += 2
    ws.cell(r, 1, "Marks").font = BOLD
    for i, (m, col, what) in enumerate([("**", RED, "client note"), ("*Confirm", ORANGE, "to confirm"),
                                        ("*Assumed", BLUE, "assumed, with why")]):
        c = ws.cell(r + i, 2, f"{m}  {what}")
        _colour(c, col, True)

    # 2. Scope
    ws = wb.create_sheet("Scope")
    heads = ["#", "Block / line", "Alt", "Verb", "Furnished by", "Installed by", "Wired by", "Qty", "Tech hrs",
             "Unit price", "Ext. price", "Mark", "Evidence (where it says so, word for word)"]
    _table(ws, heads, [5, 62, 7, 19, 15, 15, 15, 6, 8, 15, 12, 10, 100])
    for row in data["scope"]:
        if row["type"] == "block":
            ws.append(["", row["text"], row["alternate"], "", "", "", "", row["qty"], row["hours"]])
            for col in range(1, len(heads) + 1):
                cell = ws.cell(ws.max_row, col)
                cell.fill, cell.font = BLOCK_FILL, BOLD
        elif row["type"] == "line":
            ws.append([row["n"], row["text"], row["alternate"], row["verb"], row["furnished"], row["installed"],
                       row["wired"], row["qty"], None, row["unit"], row["ext"], row["mark"], row["evidence"]])
            rr = ws.max_row
            for col in (10, 11):
                ws.cell(rr, col).number_format = '"$"#,##0.00'
            if row["unit"] is None:
                ws.cell(rr, 10).value = PENDING
                ws.cell(rr, 10).font = Font(name="Calibri", size=9, color=ORANGE)
            if row["colour"]:
                _colour(ws.cell(rr, 12), row["colour"], True)
        else:
            ws.append(["", row["text"], row["alternate"], "", "", "", "", None, None, None, None, row["mark"]])
            rr = ws.max_row
            _colour(ws.cell(rr, 2), row["colour"])
            _colour(ws.cell(rr, 12), row["colour"], True)
    _finish(ws, len(heads), {2, 13})
    _recolour(ws, data["scope"])

    # 3. Questions & Flags
    ws = wb.create_sheet("Questions & Flags")
    heads = ["#", "Severity", "Kind", "Block", "About", "What", "Suggested fix", "Evidence"]
    _table(ws, heads, [5, 10, 26, 10, 40, 70, 48, 80])
    for i, q in enumerate(data["questions"], 1):
        ws.append([i, q["severity"], q["kind"], q["block"], q["about"], q["what"], q["fix"], q.get("evidence", "")])
    _finish(ws, len(heads), {3, 5, 6, 7, 8})
    for rr in range(2, ws.max_row + 1):
        if ws.cell(rr, 2).value == "Must fix":
            _colour(ws.cell(rr, 2), RED, True)
            for col in range(1, len(heads) + 1):
                ws.cell(rr, col).fill = MUST_FILL

    # 4. Sources
    ws = wb.create_sheet("Sources")
    heads = ["Sheet", "Document page", "Quote", "Proves (Scope line)"]
    _table(ws, heads, [14, 36, 90, 60])
    num = {r["id"]: f'#{r["n"]} {r["text"]}' for r in data["scope"] if r["type"] == "line"}
    for src in sorted(data["sources"], key=lambda x: (appio.split_where(x["where"])[0], x["quote"])):
        sheet, doc = appio.split_where(src["where"])
        ws.append([sheet, doc, src["quote"], "\n".join(num.get(u, u) for u in src["used"])])
    _finish(ws, len(heads), {2, 3, 4})

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(path))
    return path


def _recolour(ws, rows) -> None:
    """`_finish` resets fonts; put the block rows' bold and the marks' colours back."""
    for i, row in enumerate(rows, 2):
        if row["type"] == "block":
            for col in range(1, ws.max_column + 1):
                ws.cell(i, col).font = BOLD
        elif row.get("colour"):
            _colour(ws.cell(i, 12), row["colour"], True)
            if row["type"] == "note":
                _colour(ws.cell(i, 2), row["colour"])
        if row["type"] == "line" and row.get("unit") is None:
            ws.cell(i, 10).font = Font(name="Calibri", size=9, color=ORANGE)


def _id_key(sid: str):
    import re
    m = re.match(r"([A-Za-z]+)(\d+)", sid or "")
    return (m.group(1), int(m.group(2))) if m else (sid, 0)


def write_debug(path, job: dict, ledger: dict, coverage=None) -> Path:
    """The raw ledger (facts and sources) and the full coverage table, for debugging: not for the estimator."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Ledger facts"
    heads = ["Id", "Kind", "Subject", "Value", "Source id", "Where", "Quote", "Stage", "State", "Contradictions"]
    _table(ws, heads, [7, 10, 28, 40, 9, 40, 70, 9, 10, 30])
    for f in appio.fact_list(ledger):
        ws.append([f.get("id"), f.get("kind"), f.get("subject"), str(f.get("value")), f.get("source_id"),
                   appio.where(ledger, f.get("source_id", "")), f.get("quote"), f.get("stage"), f.get("state"),
                   "; ".join(f"{c.get('value')} [{c.get('source_id')}]" for c in f.get("contradictions") or [])])
    _finish(ws, len(heads), {3, 4, 6, 7})
    ws = wb.create_sheet("Ledger sources")
    _table(ws, ["Source id", "Where"], [10, 110])
    for k, v in (ledger.get("sources") or {}).items():
        ws.append([k, v if isinstance(v, str) else str(v)])
    _finish(ws, 2, {2})
    if coverage is not None:
        ws = wb.create_sheet("Coverage")
        heads = ["Fact", "Kind", "Subject", "Status", "Severity", "Concepts", "Covered by", "Uncovered", "Count",
                 "Printed"]
        _table(ws, heads, [7, 10, 30, 12, 10, 30, 50, 30, 7, 7])
        for f in coverage.facts:
            ws.append([f.fact_id, f.kind, f.subject, f.status, f.severity, ", ".join(f.concepts),
                       "; ".join(f"{c.concept}:{c.sink_id} ({c.method})" for c in f.covered_by),
                       ", ".join(f.uncovered), f.count, f.printed_count])
        _finish(ws, len(heads), {3, 6, 7, 8})
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(path))
    return path


def run(ledger_path, job_path, out_dir, coverage_result=None, debug: bool = False, lines_path=None) -> list[Path]:
    ledger, job = appio.load_json(ledger_path), appio.load_json(job_path)
    printed = appio.printed_texts(job)
    if coverage_result is None:
        from . import coverage
        from .doctrine import load_lines
        coverage_result = coverage.check(ledger, job, load_lines(lines_path), printed=printed)
    name = job.get("name") or "job"
    out = [write(Path(out_dir) / f"{name} Evidence (HarkPro).xlsx", job, ledger, coverage_result, printed,
                 notes=appio.printed_notes(job))]
    if debug:
        out.append(write_debug(Path(out_dir) / f"{name} Evidence debug (HarkPro).xlsx", job, ledger, coverage_result))
    return out
