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
from pathlib import Path

import docx
from docx.document import Document as DocxDocument
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, Twips
from docx.table import _Cell
from docx.text.paragraph import Paragraph

from estimator.proposal import layout
from estimator.proposal.layout import ParagraphFormat
from estimator.proposal.word import WordLists
from estimator.scope import Alternate, Block, Header, Item, Job, Run
from estimator.text import squash

_XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"


class TemplateError(ValueError):
    """The template has changed in a way the tool doesn't recognise."""


def write_proposal(job: Job, template_path: Path, out_path: Path) -> Path:
    if job.front_end.items or job.blocks or job.add_alternates or job.deduct_alternates or job.named_exceptions:
        raise NotImplementedError("writing the scope of work is added in the next task")
    document = docx.Document(str(template_path))
    check_template(document)
    _fill_cover(document, job.header)
    _keep_front_end(document, job)
    _set_scope_suffix(document, job.scope_heading_suffix)
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


def _set_existing_name(heading: Paragraph, name: str) -> None:
    runs = heading._p.findall(qn("w:r"))
    red = []
    for run in runs:
        colour = run.find(f"{qn('w:rPr')}/{qn('w:color')}")
        if colour is not None and (colour.get(qn("w:val")) or "").upper() == layout.EXISTING_NAME_COLOUR:
            red.append(run)
    if not red:
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
    return existing_heading


def _set_scope_suffix(document: DocxDocument, suffix: str) -> None:
    if not suffix:
        return
    heading = _paragraph(document, layout.SCOPE_HEADING)
    runs = heading._p.findall(qn("w:r"))
    extra = copy.deepcopy(runs[-1])
    _set_run_text(extra, suffix if heading.text.endswith((" ", "\xa0")) else f" {suffix}")
    runs[-1].addnext(extra)
