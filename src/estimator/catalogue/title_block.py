"""A drawing sheet's number and title, read from its title block.

Measured on the nine Learn jobs (step-3-facts.md §3): the title block is always a strip
along the right and/or bottom edge of the sheet as viewed, and the sheet number is the
largest text in it with a sheet number's shape. The title is the largest text directly
above the number, in the same column.
"""
from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from estimator.catalogue.pdf import Span

SHEET_NUMBER = re.compile(r"[A-Z]{1,3}[-\s.]?\d{1,4}(?:-\d{1,3}(?:[A-Z]\d{0,3})?)?(?:\.\d{1,3})?[A-Z]?")
MIN_NUMBER_SIZE = 12      # points: sheet numbers measured 19–56 pt; a cross-reference is ~10
MIN_TITLE_SIZE = 12       # points: titles measured 15–25 pt; labels, names and notes are 7–10
LABEL_SIZE = 12           # labels ("DRAWING TITLE:", "SCALE", "Drawing No.:") are smaller than this
TITLE_REACH = 0.18        # how far above the number, as a fraction of the sheet's height, a title can start
COLUMN_SLACK = 0.06       # how far left of the number's column a title line can begin
SAME_SIZE = 0.9           # title lines are within 10% of the title's largest line
MAX_TITLE_CHARS = 90      # a longer line is a paragraph — a disclaimer or a note — not a title line
_TITLE_LABEL = re.compile(r"^(?:(?:SHEET|DRAWING)\s*)?TITLE\s*:?$", re.I)
_NOT_TITLE = re.compile(
    r"^(?:(?:SHEET|DRAWING|DWG)\s*(?:NO\.?|NUMBER|TITLE)|SCALE|DATE|REV|REVISION|REVISIONS|PROJECT|PROJ|DRAWN|CHECKED|"
    r"ISSUED|JOB|SEAL|KEY PLAN|NORTH|TRUE NORTH|NOT FOR CONSTRUCTION|INTERNAL|THIS DRAWING|COPYRIGHT|PRINCIPAL)\b"
    r"|^[\d/.\-: ]+$|^[A-Z]:\\", re.I)   # the last: a file path printed on the sheet edge


@dataclass(frozen=True)
class TitleBlock:
    number: str | None
    title: str | None


def read_title_block(spans: Sequence[Span]) -> TitleBlock:
    numbers = [s for s in spans if s.size >= MIN_NUMBER_SIZE and SHEET_NUMBER.fullmatch(s.text)]
    if not numbers:
        return TitleBlock(None, None)
    # A real sheet number almost always carries two digits in a row somewhere ("M00-03", "P01-00A1.1");
    # a keyplan grid label or grid line ("D1", "B.9", "V4") does not — prefer the real number over those,
    # then the larger text, then whichever sits lower on the sheet.
    number = max(numbers, key=lambda s: (bool(re.search(r"\d{2}", s.text)), s.size, s.y0))
    return TitleBlock(" ".join(number.text.split()), _title_by_label(spans, number) or _title_above(spans, number))


def _join(lines: list[Span]) -> str:
    return " ".join(" ".join(s.text.split()) for s in sorted(lines, key=lambda s: (round(s.y0, 3), s.x0)))


def _is_label(span: Span) -> bool:
    text = span.text.strip()
    return span.size < LABEL_SIZE and (text.endswith(":") or bool(_NOT_TITLE.search(text))
                                       or text.upper() in {"DRAWING", "SHEET", "TITLE"})


def _title_by_label(spans: Sequence[Span], number: Span) -> str | None:
    """Most title blocks label the title — "DRAWING TITLE:", "SHEET TITLE:", or "DRAWING" and "TITLE" on
    two lines. The title is the large text just below the label, in its column, up to the next label."""
    for label in (s for s in spans if _TITLE_LABEL.match(s.text.strip()) and s.size < LABEL_SIZE):
        below = sorted((s for s in spans
                        if s is not label and label.y0 - 0.004 <= s.y0 <= label.y0 + 0.10 and s.y0 < number.y0
                        and label.x0 - 0.01 <= s.x0 <= label.x0 + 0.12),
                       key=lambda s: (round(s.y0, 3), s.x0))
        lines: list[Span] = []
        for span in below:
            if _is_label(span):
                if lines:
                    break
                continue
            if span.size >= MIN_TITLE_SIZE and len(span.text) <= MAX_TITLE_CHARS and not SHEET_NUMBER.fullmatch(span.text):
                lines.append(span)
        if lines:
            return _join(lines)
    return None


def _title_above(spans: Sequence[Span], number: Span) -> str | None:
    """With no label, the title is the largest text directly above the sheet number, in its column."""
    above = [s for s in spans
             if s is not number
             and s.y1 <= number.y0 + 0.005 and s.y0 >= number.y0 - TITLE_REACH
             and number.x0 - COLUMN_SLACK <= s.x0 <= number.x1
             and MIN_TITLE_SIZE <= s.size <= number.size
             and len(s.text) <= MAX_TITLE_CHARS
             and not _NOT_TITLE.search(s.text)
             and not SHEET_NUMBER.fullmatch(s.text)]
    if not above:
        return None
    largest = max(s.size for s in above)
    return _join([s for s in above if s.size >= largest * SAME_SIZE])
