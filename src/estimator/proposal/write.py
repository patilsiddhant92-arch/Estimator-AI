"""Fill the AME proposal template with a Job.

The template is the team's own file, used as it is. Everything the tool does
not write — the clarifications, the exclusions, the cover and back pages, the
signature — stays exactly as the team wrote it (the template-owns-the-
boilerplate guarantee). The tool writes only fields of the Job, into the places
named below, so nothing internal can reach the client document (the
nothing-internal-reaches-the-client guarantee).
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import re
from functools import lru_cache
from pathlib import Path

from docx.document import Document as DocxDocument
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor, Twips
from docx.table import _Cell
from docx.text.paragraph import Paragraph
from docx.text.run import Run as DocxRun

from estimator.files import open_docx
from estimator.proposal import layout
from estimator.proposal.layout import ParagraphFormat
from estimator.proposal.word import WordLists
from estimator.scope import Alternate, Block, Header, Item, Job, LaborCondition, Run
from estimator.text import squash

_XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
RED = RGBColor(0xFF, 0x00, 0x00)        # a run the estimator must notice (`Run.red`, T-005e)

# T-005e: the template's working-hours clarification and off-hours exclusion, and what replaces them when the job's
# documents call for off-hours work or prevailing wage (`Job.labor_conditions`), in red, citing the documents
NORMAL_HOURS = "All labor will be performed during normal business working hours"
OFF_HOURS_EXCLUSION = "All off-hours or overtime labor"
OFF_HOURS_CLARIFICATION = "All labor for the off-hours work the documents call for is included (As per {source})."
WAGE_CLARIFICATION = "All labor is priced at prevailing wage rates, as the documents require (As per {source})."


class TemplateError(ValueError):
    """The template has changed in a way the tool doesn't recognise."""


# --- red marks (T-005 rulings 3, 4 and 7, estimator 2026-10-11) -------------------------------------------------------

# A value the estimator must complete or look at prints in red with *** (the header's placeholder, an existing BMS that
# is not one of AME's three, the "[existing BMS name]" fill-in). AME's three are the bid check's "platforms_we_bid"
# (Honeywell WEBs, Johnson Controls FX / Facility Explorer, Niagara / Tridium): one list, read, never typed here.
STARS = "***"
_MANUFACTURERS = Path(__file__).resolve().parents[3] / "assets" / "reading_lists" / "manufacturers.json"


@lru_cache(maxsize=1)
def _ame_patterns() -> tuple[re.Pattern, ...]:
    data = json.loads(_MANUFACTURERS.read_text(encoding="utf-8"))
    return tuple(re.compile(p, re.I) for line in data["platforms_we_bid"] for p in line["patterns"])


def ame_bms(name: str | None) -> bool:
    """True when the existing BMS's name names one of the three lines AME works with (any part of a joined name
    "Honeywell / Niagara N4" will do); False for any other maker, a bare "Honeywell" or "Johnson Controls", and the
    bracket fill-in."""
    return bool(name) and any(p.search(name) for p in _ame_patterns())


def _paint_red(run) -> None:
    """A run (its w:r element) in red; python-docx keeps the run properties in their schema order."""
    DocxRun(run, None).font.color.rgb = RGBColor.from_string(layout.EXISTING_NAME_COLOUR)


def write_proposal(job: Job, template_path: Path, out_path: Path) -> Path:
    document = open_docx(template_path)
    check_template(document)
    _fill_cover(document, job.header)
    heading = _keep_front_end(document, job)
    _set_scope_suffix(document, job.scope_heading_suffix)
    _write_scope(heading, job)
    _write_alternates(document, layout.ADD_ALTERNATES, job.add_alternates)
    _write_alternates(document, layout.DEDUCT_ALTERNATES, job.deduct_alternates)
    _add_named_exceptions(document, job.named_exceptions)
    _write_labor_conditions(document, job.labor_conditions)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    document.save(str(out_path))
    return out_path


def check_template(document: DocxDocument) -> None:
    """Refuse a template the tool doesn't recognise, rather than fill it wrongly."""
    lists = WordLists(document)
    texts = [squash(p.text) for p in document.paragraphs]
    problems = []
    for prefix, expected in (
        (layout.OPENING, 2), (layout.SCOPE_HEADING, 2), (layout.NEW_SYSTEM_HEADING, 1),
        (layout.EXISTING_SYSTEM_HEADING, 1), (layout.ADD_ALTERNATES, 1), (layout.DEDUCT_ALTERNATES, 1),
        (layout.CLARIFICATIONS, 1), (layout.EXCLUSIONS, 1), (layout.BASE_PRICE, 1),
    ):
        found = sum(1 for t in texts if t.startswith(prefix))
        if found != expected:
            problems.append(f"expected {expected} paragraph(s) starting {prefix!r}, found {found}")
    if texts.count(layout.OR_LINE) != 1:
        problems.append("expected one 'OR' line between the two openings")
    if texts.count(layout.ALTERNATE_LABEL) != 2:
        problems.append(f"expected two {layout.ALTERNATE_LABEL!r} lines")
    for list_id, levels in ((layout.BLOCK_LINE_LIST, range(4, 9)),
                            (layout.FRONT_END_LIST["new-system"], (1, 2)),
                            (layout.FRONT_END_LIST["extend-existing"], (1, 2))):
        for level in levels:
            if not lists.has_level(list_id, level):
                problems.append(f"list {list_id} has no level {level}")
    if lists.style_numbering(layout.OUTLINE_STYLE) is None:
        problems.append(f"style {layout.OUTLINE_STYLE} no longer numbers its paragraphs")
    if problems:
        raise TemplateError("the proposal template has changed: " + "; ".join(problems))


# --- the cover page ---------------------------------------------------------------

def _fill_cover(document: DocxDocument, header: Header) -> None:
    table = document.tables[0]
    cells = [_Cell(tc, table) for tc in table._tbl.iter(qn("w:tc"))]

    def cell(label: str) -> _Cell:
        for candidate in cells:
            if candidate.paragraphs and squash(candidate.paragraphs[0].text).startswith(label):
                return candidate
        raise TemplateError(f"the cover page has no {label!r}")

    _set_after_label(cell("To:").paragraphs[0], "To:", header.to)
    _set_date(cell("Date:").paragraphs[0], header.date)
    _set_after_label(cell("Quote").paragraphs[0], "Quote #:", header.quote_number)
    _set_after_label(cell("Reference").paragraphs[0], "Reference:", header.reference)
    _set_after_label(cell("MEP Engineer:").paragraphs[0], "MEP Engineer:", header.mep_engineer)
    _set_lines(cell("Based on Plans and Specs:"), header.based_on)


def _run_text(run) -> str:
    return "".join(t.text or "" for t in run.findall(qn("w:t")))


def _set_run_text(run, text: str) -> None:
    """Replace a run's text, keeping its formatting."""
    for child in list(run):
        if child.tag != qn("w:rPr"):
            run.remove(child)
    t = OxmlElement("w:t")
    t.text = text
    t.set(_XML_SPACE, "preserve")
    run.append(t)


def _replace_text(paragraph: Paragraph, text: str) -> None:
    """Give a paragraph new text in the format of its first run."""
    runs = paragraph._p.findall(qn("w:r"))
    if not runs:
        raise TemplateError(f"nothing to write into in {paragraph.text!r}")
    _set_run_text(runs[0], text)
    for run in runs[1:]:
        run.getparent().remove(run)


def _set_after_label(paragraph: Paragraph, label: str, value: str) -> None:
    """Replace whatever follows a red label like "Quote #:" with the value, in the value's own colour."""
    runs = paragraph._p.findall(qn("w:r"))
    seen = ""
    for index, run in enumerate(runs):
        seen += _run_text(run)
        if squash(seen).endswith(label):
            break
    else:
        raise TemplateError(f"{label!r} not found in {paragraph.text!r}")
    rest = runs[index + 1:]
    while rest and not _run_text(rest[0]).strip():
        rest = rest[1:]
    if not rest:
        raise TemplateError(f"nothing to fill after {label!r}")
    _set_run_text(rest[0], value)
    if STARS in value:                   # a placeholder to complete (T-005 ruling 3): red
        _paint_red(rest[0])
    for run in rest[1:]:
        run.getparent().remove(run)


def _us_date(when: dt.date) -> str:
    return f"{when.month}/{when.day}/{when.year}"


def _set_date(paragraph: Paragraph, when: dt.date) -> None:
    """Write the date as text. The template's DATE field would show today's date every time the file opened."""
    runs = paragraph._p.findall(qn("w:r"))
    kinds = []
    for run in runs:
        char = run.find(qn("w:fldChar"))
        kinds.append(char.get(qn("w:fldCharType")) if char is not None else None)
    if "begin" not in kinds:
        _set_after_label(paragraph, "Date:", _us_date(when))
        return
    begin = kinds.index("begin")
    end = kinds.index("end", begin)
    separate = kinds.index("separate", begin, end)
    written = copy.deepcopy(runs[separate + 1])
    _set_run_text(written, _us_date(when))
    runs[begin].addprevious(written)
    for run in runs[begin : end + 1]:
        run.getparent().remove(run)


def _set_lines(cell: _Cell, lines: tuple[str, ...]) -> None:
    """Fill the placeholder line under "Based on Plans and Specs:", one paragraph per line."""
    placeholder = next((p for p in cell.paragraphs[1:] if "#" in p.text), None)
    if placeholder is None:
        raise TemplateError("the cover page has no placeholder line under 'Based on Plans and Specs:'")
    _replace_text(placeholder, lines[0])
    previous = placeholder._p
    for line in lines[1:]:
        clone = copy.deepcopy(placeholder._p)
        _replace_text(Paragraph(clone, placeholder._parent), line)
        previous.addnext(clone)
        previous = clone


# --- the front-end choice ---------------------------------------------------------

def _paragraph(document: DocxDocument, prefix: str) -> Paragraph:
    for paragraph in document.paragraphs:
        if squash(paragraph.text).startswith(prefix):
            return paragraph
    raise TemplateError(f"the template has no paragraph starting {prefix!r}")


def _delete_between(first: Paragraph, last: Paragraph) -> None:
    element = first._p.getnext()
    while element is not None and element is not last._p:
        following = element.getnext()
        if element.tag == qn("w:tbl"):
            raise TemplateError("a table sits inside the front-end block of the template")
        element.getparent().remove(element)
        element = following
    if element is None:
        raise TemplateError("the front-end block runs to the end of the template")


def _delete_from_until(first: Paragraph, stop: Paragraph) -> None:
    """Delete first and everything up to (not including) stop.

    Walks once to validate before deleting anything, so a refusal — stop never
    reached, or a table in the way — leaves the in-memory document untouched.
    """
    elements = []
    element = first._p
    while element is not None and element is not stop._p:
        if element.tag == qn("w:tbl"):
            raise TemplateError("a table sits inside the front-end block of the template")
        elements.append(element)
        element = element.getnext()
    if element is None:
        raise TemplateError("the front-end block runs to the end of the template")
    for element in elements:
        element.getparent().remove(element)


def _set_existing_name(heading: Paragraph, name: str, *, required: bool = True) -> None:
    """Write `name` over the red sample in a paragraph. `required`: a paragraph with no red sample is a changed
    template (refused); otherwise there is nothing to replace and it is left as it is. A name that is not one of AME's
    three (`ame_bms`), the bracket fill-in included, prints red between *** (T-005 ruling 4); one of the three prints
    in the paragraph's own colour."""
    paint = not ame_bms(name)
    if paint:
        name = f"{STARS}{name}{STARS}"
    runs = heading._p.findall(qn("w:r"))
    red = []
    for run in runs:
        colour = run.find(f"{qn('w:rPr')}/{qn('w:color')}")
        if colour is not None and (colour.get(qn("w:val")) or "").upper() == layout.EXISTING_NAME_COLOUR:
            red.append(run)
    if not red:
        if not required:
            return
        raise TemplateError("the red placeholder for the existing system's name is gone")
    # The placeholder carries the spaces either side of the name ("Honeywell / Niagara N4 "); keep them.
    original = "".join(_run_text(run) for run in red)
    before = original[: len(original) - len(original.lstrip())]
    after = original[len(original.rstrip()):]
    model = runs[0].find(qn("w:rPr"))
    first = red[0]
    old = first.find(qn("w:rPr"))
    if old is not None:
        first.remove(old)
    if model is not None:
        first.insert(0, copy.deepcopy(model))
    _set_run_text(first, f"{before}{name}{after}")
    if paint:
        _paint_red(first)
    for run in red[1:]:
        run.getparent().remove(run)


def _keep_front_end(document: DocxDocument, job: Job) -> Paragraph:
    """Keep the job's opening and front-end heading; remove the other opening and every default line.

    Returns the kept front-end heading: the job's own front-end lines go straight after it.
    """
    openings = [p for p in document.paragraphs if squash(p.text).startswith(layout.OPENING)]
    new_heading = _paragraph(document, layout.NEW_SYSTEM_HEADING)
    existing_heading = _paragraph(document, layout.EXISTING_SYSTEM_HEADING)
    add_heading = _paragraph(document, layout.ADD_ALTERNATES)
    if job.front_end.mode == "new-system":
        _delete_between(new_heading, add_heading)
        return new_heading
    _delete_from_until(openings[0], openings[1])
    _delete_between(existing_heading, add_heading)
    _set_existing_name(existing_heading, job.front_end.existing_system_name)
    # HP 25: the opening sentence ("... an extension of the existing District Wide BMS system.") carries a red sample
    # name too. It names this job's existing system, never the template's sample.
    _set_existing_name(openings[1], job.front_end.existing_system_name, required=False)
    return existing_heading


def _set_scope_suffix(document: DocxDocument, suffix: str) -> None:
    if not suffix:
        return
    heading = _paragraph(document, layout.SCOPE_HEADING)
    runs = heading._p.findall(qn("w:r"))
    extra = copy.deepcopy(runs[-1])
    _set_run_text(extra, suffix if heading.text.endswith((" ", "\xa0")) else f" {suffix}")
    runs[-1].addnext(extra)


# --- the scope of work ------------------------------------------------------------

def _mark_formatting(pPr, fmt: ParagraphFormat) -> None:
    """Bold and/or size a format sets also belong on the paragraph mark (pPr's own rPr).

    Word draws a list number or bullet from the paragraph mark's formatting, not from
    the runs that follow it — so without this, a bold 12pt header numbers itself in
    whatever plain, small font the style's mark otherwise falls back to.
    """
    rPr = pPr.find(qn("w:rPr"))
    if rPr is None:
        rPr = OxmlElement("w:rPr")
        anchor = pPr.find(qn("w:sectPr"))
        if anchor is None:
            anchor = pPr.find(qn("w:pPrChange"))
        if anchor is not None:
            anchor.addprevious(rPr)
        else:
            pPr.append(rPr)
    if fmt.bold:
        rPr.get_or_add_b()
    if fmt.size is not None:
        rPr.sz_val = Pt(fmt.size)


def _apply(paragraph: Paragraph, fmt: ParagraphFormat, runs: tuple[Run, ...]) -> None:
    paragraph.style = fmt.style
    if fmt.list_id is not None:
        numPr = paragraph._p.get_or_add_pPr().get_or_add_numPr()
        numPr.get_or_add_ilvl().val = fmt.level
        numPr.get_or_add_numId().val = fmt.list_id
    if fmt.indent is not None:
        paragraph.paragraph_format.left_indent = Twips(fmt.indent)
    if fmt.space_after is not None:
        paragraph.paragraph_format.space_after = Pt(fmt.space_after)
    if fmt.bold or fmt.size is not None:
        _mark_formatting(paragraph._p.get_or_add_pPr(), fmt)
    for part in runs:
        run = paragraph.add_run(part.text)        # a "\n" in the text is a line break (short points, T-005 ruling 5)
        if fmt.bold or part.bold:
            run.bold = True
        if part.red:                               # a line the estimator must notice (T-005 ruling 7)
            run.font.color.rgb = RGBColor.from_string(layout.EXISTING_NAME_COLOUR)
        if fmt.size is not None:
            run.font.size = Pt(fmt.size)
        if fmt.font is not None:
            run.font.name = fmt.font
            rFonts = run._r.get_or_add_rPr().get_or_add_rFonts()
            rFonts.set(qn("w:eastAsia"), fmt.font)
            rFonts.set(qn("w:cs"), fmt.font)


def _insert_after(cursor: Paragraph, fmt: ParagraphFormat, runs: tuple[Run, ...] = ()) -> Paragraph:
    element = OxmlElement("w:p")
    cursor._p.addnext(element)
    paragraph = Paragraph(element, cursor._parent)
    _apply(paragraph, fmt, runs)
    return paragraph


def _front_end_format(mode: str, item: Item) -> ParagraphFormat:
    return layout.FRONT_END_NOTE if item.kind == "note" else layout.front_end_line(mode, item.depth)


def _block_format(item: Item) -> ParagraphFormat:
    return layout.BLOCK_NOTE if item.kind == "note" else layout.block_line(item.depth)


def _write_block(cursor: Paragraph, block: Block) -> Paragraph:
    if not block.joined:
        cursor = _insert_after(cursor, layout.BLANK)
    fmt = layout.BLOCK_HEADER if block.numbered else layout.GROUP_HEADING
    cursor = _insert_after(cursor, fmt, (Run(text=block.header, bold=True),))
    for item in block.items:
        cursor = _insert_after(cursor, _block_format(item), item.runs)
    return cursor


def _write_scope(heading: Paragraph, job: Job) -> None:
    """The job's front-end lines straight after the kept heading, then every block, then a blank line."""
    cursor = heading
    for item in job.front_end.items:
        if item.kind == "note":
            cursor = _insert_after(cursor, layout.FRONT_END_NOTE_GAP)
        cursor = _insert_after(cursor, _front_end_format(job.front_end.mode, item), item.runs)
    for block in job.blocks:
        cursor = _write_block(cursor, block)
    _insert_after(cursor, layout.BLANK)


def _label_under(document: DocxDocument, section: str) -> Paragraph:
    paragraphs = document.paragraphs
    start = next(i for i, p in enumerate(paragraphs) if squash(p.text).startswith(section))
    for paragraph in paragraphs[start + 1 :]:
        text = squash(paragraph.text)
        if text == layout.ALTERNATE_LABEL:
            return paragraph
        if text:
            break
    raise TemplateError(f"no {layout.ALTERNATE_LABEL!r} line under {section!r}")


def _write_alternates(document: DocxDocument, section: str, alternates: tuple[Alternate, ...]) -> None:
    if not alternates:
        return
    label = _label_under(document, section)
    untouched_label = copy.deepcopy(label._p)
    cursor = label
    for index, alternate in enumerate(alternates):
        if index:
            cursor = _insert_after(cursor, layout.BLANK)
            element = copy.deepcopy(untouched_label)
            cursor._p.addnext(element)
            cursor = Paragraph(element, cursor._parent)
        _replace_text(cursor, alternate.label)
        for block in alternate.blocks:
            cursor = _write_block(cursor, block)


def _add_named_exceptions(document: DocxDocument, exceptions: tuple[str, ...]) -> None:
    if not exceptions:
        return
    paragraphs = document.paragraphs
    base = next(i for i, p in enumerate(paragraphs) if squash(p.text).startswith(layout.BASE_PRICE))
    last = next(p for p in reversed(paragraphs[:base]) if p.text.strip())
    cursor = last._p
    for text in exceptions:
        clone = copy.deepcopy(last._p)
        _replace_text(Paragraph(clone, last._parent), text)
        cursor.addnext(clone)
        cursor = clone


# --- off-hours work and prevailing wage (T-005e) --------------------------------------------------------------------

def _make_red(paragraph: Paragraph) -> None:
    for run in paragraph.runs:
        run.font.color.rgb = RED


def _clarification_after(cursor: Paragraph, text: str) -> Paragraph:
    """A red clarification like the template's own (a copy of `cursor`'s paragraph, its text replaced), after it."""
    clone = copy.deepcopy(cursor._p)
    added = Paragraph(clone, cursor._parent)
    _replace_text(added, text)
    _make_red(added)
    cursor._p.addnext(clone)
    return added


def _write_labor_conditions(document: DocxDocument, conditions: tuple[LaborCondition, ...]) -> None:
    """When the job's documents call for off-hours work or prevailing wage, the proposal says so in red, citing them,
    and never excludes it in silence: the working-hours clarification becomes the off-hours one, the off-hours
    exclusion is taken out (the scope's "Labor Conditions" line carries it), and a prevailing-wage clarification follows
    the first clarification. Nothing changes when there is no condition."""
    if not conditions:
        return
    paragraphs = document.paragraphs
    start = next(i for i, p in enumerate(paragraphs) if squash(p.text).startswith(layout.CLARIFICATIONS))
    first = next((p for p in paragraphs[start + 1:] if squash(p.text)), None)
    if first is None:
        raise TemplateError("the clarifications section has no line")
    by_kind = {c.kind: c for c in conditions}
    cursor = first
    off = by_kind.get("off-hours")
    if off is not None:
        text = OFF_HOURS_CLARIFICATION.format(source=off.source)
        normal = next((p for p in paragraphs[start + 1:] if squash(p.text).startswith(NORMAL_HOURS)), None)
        if normal is not None:
            _replace_text(normal, text)
            _make_red(normal)
            cursor = normal
        else:
            cursor = _clarification_after(first, text)
        for paragraph in document.paragraphs:
            if squash(paragraph.text).startswith(OFF_HOURS_EXCLUSION):
                paragraph._p.getparent().remove(paragraph._p)
    wage = by_kind.get("prevailing-wage")
    if wage is not None:
        _clarification_after(cursor, WAGE_CLARIFICATION.format(source=wage.source))
