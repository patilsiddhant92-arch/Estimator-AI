"""A proposal's parts as plain text — for checking one proposal against another."""
from __future__ import annotations

from pathlib import Path

import docx
from docx.oxml.ns import qn
from docx.table import _Cell

from estimator.proposal import layout
from estimator.text import squash


def _texts(path: Path) -> list[str]:
    return [squash(p.text) for p in docx.Document(str(path)).paragraphs if p.text.strip()]


def _index(texts: list[str], prefix: str) -> int:
    return next(i for i, t in enumerate(texts) if t.startswith(prefix))


def scope_texts(path: Path) -> list[str]:
    """Every line from SCOPE OF WORK down to, not including, the clarifications."""
    texts = _texts(path)
    return texts[_index(texts, layout.SCOPE_HEADING) : _index(texts, layout.CLARIFICATIONS)]


def scope_blank_pattern(path: Path) -> list[tuple[str, bool]]:
    """Every non-blank line from SCOPE OF WORK down to the clarifications, paired with whether a
    blank line sits immediately before it — the layout a words-only comparison can't see: which
    headers run straight on from what came before (joined), and which stand behind a gap.

    Consecutive blank paragraphs count as one gap: the tool always writes a single blank line
    (layout.BLANK), so where a sent proposal happens to carry two or three Enter presses in a
    row, that is still one gap, not a difference in grouping.
    """
    texts = [squash(p.text) for p in docx.Document(str(path)).paragraphs]
    start = next(i for i, t in enumerate(texts) if t.startswith(layout.SCOPE_HEADING))
    end = next(i for i, t in enumerate(texts) if t.startswith(layout.CLARIFICATIONS))
    pairs, gap = [], False
    for text in texts[start:end]:
        if text.strip():
            pairs.append((text, gap))
            gap = False
        else:
            gap = True
    return pairs


def closing_texts(path: Path) -> list[str]:
    """Every line from the clarifications to the end — the part the template owns."""
    texts = _texts(path)
    return texts[_index(texts, layout.CLARIFICATIONS) :]


def opening_texts(path: Path) -> list[str]:
    """Every line before the opening sentence — the heading area the template owns."""
    texts = _texts(path)
    return texts[: _index(texts, layout.OPENING)]


def cover_lines(path: Path) -> list[str]:
    """The cover page table, line by line."""
    document = docx.Document(str(path))
    table = document.tables[0]
    return [squash(p.text) for tc in table._tbl.iter(qn("w:tc")) for p in _Cell(tc, table).paragraphs if p.text.strip()]
