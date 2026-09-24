"""How Word draws a paragraph: its bullet or number, its indent, its emphasis.

Proposals are copy-pasted between jobs, so the same visual level turns up
built from several different lists and styles. Everything here reads what Word
actually draws rather than what the style is called.
"""
from __future__ import annotations

from collections.abc import Iterator

from docx.document import Document as DocxDocument
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph


def _left(pPr) -> int | None:
    """The left indent written on a paragraph-properties element, in twips."""
    if pPr is None:
        return None
    ind = pPr.find(qn("w:ind"))
    if ind is None:
        return None
    value = ind.get(qn("w:left"))
    if value is None:
        value = ind.get(qn("w:start"))
    return int(value) if value is not None else None


class WordLists:
    """The document's lists and styles, resolved the way Word resolves them."""

    def __init__(self, document: DocxDocument) -> None:
        self._styles = {s.get(qn("w:styleId")): s for s in document.styles.element.findall(qn("w:style"))}
        numbering = document.part.numbering_part.element
        self._list_to_definition = {
            int(n.get(qn("w:numId"))): n.find(qn("w:abstractNumId")).get(qn("w:val"))
            for n in numbering.findall(qn("w:num"))
        }
        self._definitions = {a.get(qn("w:abstractNumId")): a for a in numbering.findall(qn("w:abstractNum"))}

    # lists ----------------------------------------------------------------------

    def _level(self, list_id: int, level: int):
        definition = self._definitions.get(self._list_to_definition.get(list_id))
        if definition is None:
            return None
        for lvl in definition.findall(qn("w:lvl")):
            if lvl.get(qn("w:ilvl")) == str(level):
                return lvl
        return None

    def has_level(self, list_id: int, level: int) -> bool:
        return self._level(list_id, level) is not None

    def level_indent(self, list_id: int, level: int) -> int | None:
        lvl = self._level(list_id, level)
        return _left(lvl.find(qn("w:pPr"))) if lvl is not None else None

    # styles ---------------------------------------------------------------------

    def _style_chain(self, style_id: str | None) -> Iterator:
        seen: set[str] = set()
        while style_id and style_id not in seen:
            seen.add(style_id)
            style = self._styles.get(style_id)
            if style is None:
                return
            yield style
            based_on = style.find(qn("w:basedOn"))
            style_id = based_on.get(qn("w:val")) if based_on is not None else None

    def style_numbering(self, style_id: str) -> tuple[int, int] | None:
        """The list a style numbers its paragraphs with, if it has one."""
        for style in self._style_chain(style_id):
            pPr = style.find(qn("w:pPr"))
            numPr = pPr.find(qn("w:numPr")) if pPr is not None else None
            if numPr is not None:
                num_id = numPr.find(qn("w:numId"))
                ilvl = numPr.find(qn("w:ilvl"))
                list_id = int(num_id.get(qn("w:val"))) if num_id is not None else 0
                level = int(ilvl.get(qn("w:val"))) if ilvl is not None else 0
                return None if list_id == 0 else (list_id, level)
        return None

    # paragraphs -----------------------------------------------------------------

    @staticmethod
    def written_numbering(paragraph: Paragraph) -> tuple[int, int] | None:
        """The list and level written on the paragraph itself — list 0 ("no number") included."""
        pPr = paragraph._p.pPr
        if pPr is None or pPr.numPr is None or pPr.numPr.numId is None:
            return None
        level = pPr.numPr.ilvl.val if pPr.numPr.ilvl is not None else 0
        return int(pPr.numPr.numId.val), int(level)

    def numbering(self, paragraph: Paragraph) -> tuple[int, int] | None:
        """The list and level Word draws for this paragraph; None if it has no bullet or number."""
        written = self.written_numbering(paragraph)
        if written is not None:
            return None if written[0] == 0 else written
        return self.style_numbering(paragraph.style.style_id)

    def left_indent(self, paragraph: Paragraph) -> int:
        """Where Word starts the paragraph's text, in twips (1440 twips = one inch)."""
        written = _left(paragraph._p.pPr)
        if written is not None:
            return written
        numbering = self.numbering(paragraph)
        if numbering is not None:
            from_list = self.level_indent(*numbering)
            if from_list is not None:
                return from_list
        for style in self._style_chain(paragraph.style.style_id):
            from_style = _left(style.find(qn("w:pPr")))
            if from_style is not None:
                return from_style
        return 0


def merged_runs(paragraph: Paragraph) -> list[tuple[str, bool]]:
    """The paragraph's text as (text, bold) stretches, trimmed at both ends.

    A run of pure whitespace joins whatever comes before it, so a bold space
    between two plain words doesn't split the line into three pieces.
    """
    stretches: list[list] = []
    for content in paragraph.iter_inner_content():
        for run in (content.runs if hasattr(content, "runs") else [content]):
            if not run.text:
                continue
            bold = run.bold is True
            if stretches and (stretches[-1][1] == bold or not run.text.strip()):
                stretches[-1][0] += run.text
            else:
                stretches.append([run.text, bold])
    while stretches and not stretches[0][0].strip():
        stretches.pop(0)
    while stretches and not stretches[-1][0].strip():
        stretches.pop()
    if stretches:
        stretches[0][0] = stretches[0][0].lstrip()
        stretches[-1][0] = stretches[-1][0].rstrip()
    return [(text, bold) for text, bold in stretches]


def visible_text(paragraph: Paragraph) -> str:
    """Every character of text in the paragraph's XML, wherever it sits."""
    parts = []
    for element in paragraph._p.iter(qn("w:t"), qn("w:noBreakHyphen")):
        parts.append((element.text or "") if element.tag == qn("w:t") else "-")
    return "".join(parts)


def deleted_text(paragraph: Paragraph) -> str:
    """The words a tracked deletion removed from this paragraph — stored as <w:delText>, which
    neither python-docx's own p.text nor visible_text() ever look at."""
    return "".join(element.text or "" for element in paragraph._p.iter(qn("w:delText")))


def field_result_text(paragraph: Paragraph, instruction: str) -> str | None:
    """The text Word last displayed for a field such as DATE, or None if there is none."""
    state, code, shown = None, "", []
    for run in paragraph._p.findall(qn("w:r")):
        char = run.find(qn("w:fldChar"))
        if char is not None:
            kind = char.get(qn("w:fldCharType"))
            if kind == "begin":
                state, code, shown = "code", "", []
            elif kind == "separate":
                state = "shown"
            elif kind == "end":
                if code.strip().upper().startswith(instruction.upper()):
                    return "".join(shown)
                state = None
            continue
        if state == "code":
            instr = run.find(qn("w:instrText"))
            if instr is not None and instr.text:
                code += instr.text
        elif state == "shown":
            shown.extend(t.text or "" for t in run.findall(qn("w:t")))
    for simple in paragraph._p.findall(qn("w:fldSimple")):
        if (simple.get(qn("w:instr")) or "").strip().upper().startswith(instruction.upper()):
            return "".join(t.text or "" for t in simple.iter(qn("w:t")))
    return None
