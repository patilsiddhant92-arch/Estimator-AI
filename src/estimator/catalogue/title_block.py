"""A drawing sheet's number and title, read from its title block.

Measured on the nine Learn jobs (step-3-facts.md §3): the title block is always a strip
along the right and/or bottom edge of the sheet as viewed, and the sheet number is the
largest text in it with a sheet number's shape. The title is the largest text directly
above the number, in the same column (a line centred in the strip begins left of the number's
column and runs on over the number: it is in the column too, unless it is the value of another field,
such as the project's name, or stands apart from the lines below it: `_title_stack`).

When the title block gives no title, the sheet's title is taken from the drawing index (the
cover sheet's list of sheet numbers and titles), and failing that from the capitalised line
written just before the sheet number in the title block's text.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from estimator.catalogue.pdf import Span

SHEET_NUMBER = re.compile(
    r"(?:(?=[A-Z0-9]{1,6}-)[A-Z0-9]*[A-Z][A-Z0-9]*-)?"     # an optional building/phase prefix ("H3T-", "HEL03-")
    r"[A-Z]{1,3}[-\s.]?\d{1,4}(?:-\d{1,3}(?:[A-Z]\d{0,3})?)?(?:\.\d{1,3})?(?:-[A-Z])?[A-Z]?"
)
_REVISION_MARK = re.compile(r"^(?:REV|NO)(?![A-Z])", re.I)   # "REV 2", "NO 3": a revision row's mark, never a sheet
MIN_NUMBER_SIZE = 12      # points: sheet numbers measured 19–56 pt; a cross-reference is ~10
MIN_TITLE_SIZE = 12       # points: titles measured 15–25 pt; labels, names and notes are 7–10
LABEL_SIZE = 12           # labels ("DRAWING TITLE:", "SCALE", "Drawing No.:") are smaller than this
TITLE_REACH = 0.18        # how far above the number, as a fraction of the sheet's height, a title can start
COLUMN_SLACK = 0.06       # how far left of the number's column a title line can begin
CENTRED_REACH = 0.18      # a line centred in the strip (HP 1) may begin this far left of its reference (the sheet
                          # number, or the label above the title) when it runs on over the reference's left edge: a
                          # strip is no wider than this, so a line that begins further left is a note across the sheet
CENTRED_GAP = 1.0         # a centred line joins the title only when it is within this many line heights of the line
                          # below it: the lines of one title stand close, a project name stands apart or under a label
LABEL_REACH = 0.03        # a line that begins at most this far below a small label's top may be that label's value
SAME_SIZE = 0.9           # title lines are within 10% of the title's largest line
MAX_TITLE_CHARS = 90      # a longer line is a paragraph — a disclaimer or a note — not a title line
_TITLE_LABEL = re.compile(r"^(?:SHEET\s*(?:TITLE|NAME)|DRAWING\s*TITLE|TITLE)\s*:?$", re.I)
_NUMBER_LABEL = re.compile(r"^(?:SHEET|DRAWING|DWG)\s*(?:NUMBER|NO)\s*[:.]{0,2}$", re.I)
# The small label of a field whose value is a large line that is no title: the project's name, its owner, the firms
# that drew it, its address. A line under such a label is that field's value (`_owned`).
_OTHER_FIELD = re.compile(r"^(?:PROJECT|PROJ|CLIENT|OWNER|ARCHITECT|ENGINEER|CONSULTANT|SITE|LOCATION|ADDRESS)\b", re.I)
_NOT_TITLE = re.compile(
    r"^(?:(?:SHEET|DRAWING|DWG)\s*(?:NO\.?|NUMBER|TITLE|NAME)|SCALE|DATE|REV|REVISION|REVISIONS|PROJECT|PROJ|DRAWN|CHECKED|"
    r"ISSUED|JOB|SEAL|KEY PLAN|NORTH|TRUE NORTH|NOT FOR CONSTRUCTION|INTERNAL|THIS DRAWING|COPYRIGHT|PRINCIPAL)\b"
    r"|^[\d/.\-: ]+$|^[A-Z]:\\", re.I)   # the last: a file path printed on the sheet edge


BESIDE_CHARS = 60         # the line just before the sheet number is a title only when shorter than this
INDEX_PAIRS = 8           # a page listing this many sheet numbers, each with a title, is a drawing index
INDEX_PAIRS_HEADED = 4    # … or this many, under a heading that names it one
_INDEX_HEADING = re.compile(r"\b(?:DRAWING|SHEET)S?\s+(?:INDEX|LIST)\b|\bLIST\s+OF\s+(?:DRAWINGS|SHEETS)\b"
                            r"|\bINDEX\s+OF\s+(?:DRAWINGS|SHEETS)\b", re.I)
_NUMBER_THEN_TITLE = re.compile(rf"^({SHEET_NUMBER.pattern})\s+(\S.*)$")
TITLE_BLOCK, DRAWING_INDEX, BESIDE_NUMBER = "title block", "drawing index", "beside the sheet number"


@dataclass(frozen=True)
class TitleBlock:
    number: str | None
    title: str | None
    # Where the title came from — TITLE_BLOCK, DRAWING_INDEX or BESIDE_NUMBER; not part of what the block reads.
    source: str | None = field(default=None, compare=False)


def sheet_key(number: str) -> str:
    """A sheet number as two sheet numbers are compared (estimator ruling D8): "M-101", "M101" and "M 101" are one
    sheet, in any case. Only a space or dash between the letters and the digits is passed over; the dot between
    digits is kept ("M-1.01" is another sheet than "M-101"), and so is a dash between digits ("M1-01"). A sheet
    number is always shown as printed; this key is for comparing only."""
    return re.sub(r"(?<=[A-Z])[\s\-‐‑–—]+(?=\d)", "", " ".join(number.split()).upper())


def index_key(number: str) -> str:
    """A sheet number as the drawing index and the title block are compared (`sheet_key`): "C-7.0" and "C7.0" are
    one sheet."""
    return sheet_key(number)


def _is_number(text: str) -> bool:
    """Text with a sheet number's shape that is no revision mark ("REV 2" has the shape)."""
    return bool(SHEET_NUMBER.fullmatch(text)) and not _REVISION_MARK.match(text)


def _index_title(text: str) -> str | None:
    text = " ".join(text.split())
    if (len(text) > MAX_TITLE_CHARS or len(re.findall(r"[A-Za-z]", text)) < 3 or SHEET_NUMBER.fullmatch(text)
            or _NOT_TITLE.search(text) or text.endswith(":")):
        return None
    return text


def _index_pairs(text: str) -> dict[str, str]:
    lines = [" ".join(line.split()) for line in text.splitlines()]
    lines = [line for line in lines if line]
    pairs: dict[str, str] = {}
    for n, line in enumerate(lines):
        if _is_number(line) and re.search(r"\d", line):
            title = _index_title(lines[n + 1]) if n + 1 < len(lines) else None
            number = line
        else:
            m = _NUMBER_THEN_TITLE.match(line)
            if not m or _REVISION_MARK.match(m.group(1)):
                continue
            number, title = m.group(1), _index_title(m.group(2))
        if title:
            pairs.setdefault(index_key(number), title)
    return pairs


def read_drawing_index(texts: Iterable[str]) -> dict[str, str]:
    """Sheet number (as index_key gives it) → title, from every page that lists the drawings: many lines of a
    sheet number with its title, beside it or on the line below. A page under a "DRAWING INDEX" heading
    comes first, then the longest list; the first title found for a number is kept."""
    found = []
    for text in texts:
        pairs = _index_pairs(text)
        headed = bool(_INDEX_HEADING.search(text))
        if len(pairs) >= INDEX_PAIRS or (headed and len(pairs) >= INDEX_PAIRS_HEADED):
            found.append((not headed, -len(pairs), pairs))
    index: dict[str, str] = {}
    for _, _, pairs in sorted(found, key=lambda f: f[:2]):
        for key, title in pairs.items():
            index.setdefault(key, title)
    return index


def read_title_block(spans: Sequence[Span], index: Mapping[str, str] | None = None) -> TitleBlock:
    number = _number_by_label(spans)
    if number is None:
        numbers = [s for s in spans if s.size >= MIN_NUMBER_SIZE and _is_number(s.text)]
        if not numbers:
            return TitleBlock(None, None)
        # A real sheet number almost always carries two digits in a row somewhere ("M00-03", "P01-00A1.1");
        # a keyplan grid label or grid line ("D1", "B.9", "V4") does not — prefer the real number over those,
        # then the larger text, then whichever sits lower on the sheet.
        number = max(numbers, key=lambda s: (bool(re.search(r"\d{2}", s.text)), s.size, s.y0))
    text = " ".join(number.text.split())
    title = _title_by_label(spans, number) or _title_above(spans, number)
    if title:
        return TitleBlock(text, title, TITLE_BLOCK)
    if index and index.get(index_key(text)):
        return TitleBlock(text, index[index_key(text)], DRAWING_INDEX)
    title = _title_beside(spans, number)
    return TitleBlock(text, title, BESIDE_NUMBER) if title else TitleBlock(text, None)


def _number_by_label(spans: Sequence[Span]) -> Span | None:
    """When the strip labels the sheet number ("SHEET NUMBER", "SHEET NO", "DRAWING NUMBER",
    "DRAWING NO", "DWG NO"), the sheet-number-shaped text directly below it or to its right on
    the same line is the number, whatever its size."""
    label = next((s for s in spans if _NUMBER_LABEL.match(s.text.strip()) and s.size < LABEL_SIZE), None)
    if label is None:
        return None
    candidates = [
        s for s in spans
        if s is not label and _is_number(" ".join(s.text.split()))
        and ((label.y0 - 0.004 <= s.y0 <= label.y0 + 0.10 and label.x0 - 0.01 <= s.x0 <= label.x0 + 0.12)
             or (abs(s.y0 - label.y0) < 0.006 and s.x0 > label.x0))
    ]
    return min(candidates, key=lambda s: (round(s.y0, 3), s.x0)) if candidates else None


def _title_beside(spans: Sequence[Span], number: Span) -> str | None:
    """The line written just before the sheet number, when it is in capitals, short, and not a label."""
    at = next(n for n, s in enumerate(spans) if s is number)
    if at == 0:
        return None
    text = " ".join(spans[at - 1].text.split())
    if (len(text) >= BESIDE_CHARS or text != text.upper() or len(re.findall(r"[A-Z]", text)) < 3
            or text.endswith(":") or _NOT_TITLE.search(text) or _TITLE_LABEL.match(text) or SHEET_NUMBER.fullmatch(text)):
        return None
    return text


def _join(lines: list[Span]) -> str:
    return " ".join(" ".join(s.text.split()) for s in sorted(lines, key=lambda s: (round(s.y0, 3), s.x0)))


def _is_label(span: Span) -> bool:
    text = span.text.strip()
    return span.size < LABEL_SIZE and (text.endswith(":") or bool(_NOT_TITLE.search(text))
                                       or text.upper() in {"DRAWING", "SHEET", "TITLE", "NAME"})


def _centre(span: Span) -> float:
    return (span.x0 + span.x1) / 2


def _under_label(span: Span, label: Span) -> bool:
    """A line sits in the column of the label above it (HP 1): it begins at most 0.01 left of the label and at most 0.12
    right of it (left-aligned), or it is a title line centred under a centred label — it begins further left (up to
    CENTRED_REACH) because it is longer than the label, and its centre lies on the label. A line of another column,
    beside the title block's own, has its centre elsewhere, so it is never taken."""
    if label.x0 - 0.01 <= span.x0 <= label.x0 + 0.12:
        return True
    return (label.x0 - CENTRED_REACH <= span.x0 < label.x0 - 0.01
            and label.x0 - 0.01 <= _centre(span) <= label.x1 + 0.01)


def _title_by_label(spans: Sequence[Span], number: Span) -> str | None:
    """Most title blocks label the title — "DRAWING TITLE:", "SHEET TITLE:", or "DRAWING" and "TITLE" on
    two lines. The title is the large text just below the label, in its column, up to the next label."""
    for label in (s for s in spans if _TITLE_LABEL.match(s.text.strip()) and s.size < LABEL_SIZE):
        below = sorted((s for s in spans
                        if s is not label and label.y0 - 0.004 <= s.y0 <= label.y0 + 0.10 and s.y0 < number.y0
                        and _under_label(s, label)),
                       key=lambda s: (round(s.y0, 3), s.x0))
        lines: list[Span] = []
        for span in below:
            if _is_label(span):
                if lines:
                    break
                continue
            if len(span.text) <= MAX_TITLE_CHARS and not SHEET_NUMBER.fullmatch(span.text):
                lines.append(span)
        if lines:
            return _join(lines)
    return None


def _in_column(span: Span, number: Span) -> bool:
    """A line sits in the sheet number's column (HP 1): it begins at most COLUMN_SLACK left of the number and not right
    of its right edge, or it is a line centred in the strip — it begins further left (up to CENTRED_REACH) and runs on
    over the number's left edge. A line of a column beside the number's ends before the number begins, and a line
    right of the number begins after it, so neither is taken."""
    if number.x0 - COLUMN_SLACK <= span.x0 <= number.x1:
        return True
    return number.x0 - CENTRED_REACH <= span.x0 < number.x0 - COLUMN_SLACK and span.x1 > number.x0


def _centred_only(span: Span, number: Span) -> bool:
    """The line is in the number's column by the centred rule alone (`_in_column`): it begins left of COLUMN_SLACK."""
    return not (number.x0 - COLUMN_SLACK <= span.x0 <= number.x1)


def _owned(span: Span, spans: Sequence[Span]) -> bool:
    """The line is the value of another field (HP 1): the nearest large line under the small label of a field that is
    no title ("PROJECT:", "OWNER:", `_OTHER_FIELD`), in the label's column. A project name is such a line, often larger
    than the title; the title lines under it are not the label's."""
    def in_column(s: Span, label: Span) -> bool:
        return s.x0 < label.x1 + 0.01 and label.x0 - 0.01 < s.x1

    for label in spans:
        if (label is span or label.size >= LABEL_SIZE or not _OTHER_FIELD.match(label.text.strip())
                or not (label.y0 - 0.004 <= span.y0 <= label.y0 + LABEL_REACH) or not in_column(span, label)):
            continue
        if not any(s is not span and s.size >= MIN_TITLE_SIZE and label.y0 - 0.004 <= s.y0 < span.y0
                   and in_column(s, label) for s in spans):
            return True
    return False


def _apart(upper: Span, lower: Span) -> bool:
    """`upper` stands further above `lower` than the lines of one title do: more than CENTRED_GAP line heights apart."""
    return lower.y0 - upper.y1 > CENTRED_GAP * max(upper.y1 - upper.y0, lower.y1 - lower.y0)


def _title_stack(above: Sequence[Span], number: Span, spans: Sequence[Span]) -> list[Span]:
    """The lines of `above` that can be the title, the line nearest the number first. A line in the column by the old
    rule always stays. A line in it by the centred rule alone (HP 1) stays only when it is no other field's value
    (`_owned`) and is close above the line kept below it (`_apart`): a large project name stands apart from the title
    or under its own label, and would otherwise be the title, or join it."""
    kept: list[Span] = []
    for s in sorted(above, key=lambda s: s.y0, reverse=True):
        if _centred_only(s, number) and (_owned(s, spans) or (kept and _apart(s, kept[-1]))):
            continue
        kept.append(s)
    return kept


def _title_above(spans: Sequence[Span], number: Span) -> str | None:
    """With no label, the title is the largest text directly above the sheet number, in its column (`_in_column`)."""
    above = _title_stack([s for s in spans
                          if s is not number
                          and s.y1 <= number.y0 + 0.005 and s.y0 >= number.y0 - TITLE_REACH
                          and _in_column(s, number)
                          and MIN_TITLE_SIZE <= s.size <= number.size
                          and len(s.text) <= MAX_TITLE_CHARS
                          and not _NOT_TITLE.search(s.text)
                          and not SHEET_NUMBER.fullmatch(s.text)], number, spans)
    if not above:
        return None
    largest = max(s.size for s in above)
    return _join([s for s in above if s.size >= largest * SAME_SIZE])
