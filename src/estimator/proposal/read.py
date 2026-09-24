"""Read a proposal written on the AME template back into a Job.

Used to turn the proposal an estimator actually sent into test data and, from
build step 2, to score the tool against past jobs. It reads what Word draws —
bullets, numbering, indent — rather than what the styles are called, because
copy-paste between proposals leaves the same visual level built from several
different lists and styles.
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import docx
from docx.document import Document as DocxDocument
from docx.oxml.ns import qn
from docx.table import _Cell
from docx.text.paragraph import Paragraph

from estimator.proposal import layout
from estimator.proposal.word import WordLists, field_result_text, merged_runs, visible_text
from estimator.scope import Alternate, Block, FrontEnd, Header, Item, Job, Run
from estimator.text import squash


class ProposalFormatError(ValueError):
    """The proposal doesn't follow the template closely enough to be read safely."""


# --- the cover page ---------------------------------------------------------------

def read_cover(document: DocxDocument) -> Header:
    """The table on the cover page: to, date, quote number, reference, engineer, drawings."""
    table = document.tables[0]
    values: dict[str, object] = {}
    for tc in table._tbl.iter(qn("w:tc")):
        lines = [p for p in _Cell(tc, table).paragraphs if p.text.strip()]
        if not lines:
            continue
        first = squash(lines[0].text)
        if first.startswith("To:"):
            values["to"] = first[len("To:"):].strip()
        elif first.startswith("Date:"):
            values["date"] = _date(field_result_text(lines[0], "DATE") or first[len("Date:"):])
        elif first.startswith("Quote"):
            values["quote_number"] = re.sub(r"^Quote\s*#?\s*:\s*", "", first)
        elif first.startswith("Reference"):
            joined = " ".join(squash(p.text) for p in lines)
            values["reference"] = re.sub(r"^Reference\s*:\s*", "", joined)
        elif first.startswith("MEP Engineer:"):
            values["mep_engineer"] = first[len("MEP Engineer:"):].strip()
        elif first.startswith("Based on Plans and Specs:"):
            rest = first[len("Based on Plans and Specs:"):].strip()
            values["based_on"] = tuple(([rest] if rest else []) + [squash(p.text) for p in lines[1:]])
    missing = {"to", "date", "quote_number", "reference", "mep_engineer", "based_on"} - values.keys()
    if missing:
        raise ProposalFormatError(f"the cover page is missing {sorted(missing)}")
    return Header(**values)


def _date(text: str) -> dt.date:
    try:
        return dt.datetime.strptime(squash(text), "%m/%d/%Y").date()
    except ValueError as error:
        raise ProposalFormatError(f"can't read the date {text!r}") from error


# --- the exclusions ---------------------------------------------------------------

def _exclusions(document: DocxDocument) -> list[str]:
    texts = [squash(p.text) for p in document.paragraphs if p.text.strip()]
    start = next((i for i, t in enumerate(texts) if t.startswith(layout.EXCLUSIONS)), None)
    end = next((i for i, t in enumerate(texts) if t.startswith(layout.BASE_PRICE)), None)
    if start is None or end is None or end <= start:
        raise ProposalFormatError("can't find the exclusions list")
    return texts[start + 1 : end]


def read_named_exceptions(document: DocxDocument, template_path: Path) -> tuple[str, ...]:
    """Exclusions this job added after the template's standard list."""
    standard = _exclusions(docx.Document(str(template_path)))
    sent = _exclusions(document)
    if sent[: len(standard)] != standard:
        raise ProposalFormatError(
            "the standard exclusions were edited, reordered or cut in this proposal; the tool can "
            "only add exceptions after the standard list, so it can't reproduce this one")
    return tuple(sent[len(standard):])
