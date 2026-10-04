"""Tag patterns and the located-text count (workstream 6): where a family's tags sit in a PDF page's text layer,
as boxes in the pixels of that sheet's whole-sheet picture."""
from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

import pymupdf

from estimator.catalogue.pdf import clean_text
from estimator.catalogue.tags import tag_prefix

DASHES = "-‐‑–—"
NOTE_WORDS = 5      # a line of more words than this is a note or a sentence that names a tag, not a placed tag


def canonical(text: str) -> str:
    """A tag as one spelling: upper case, every dash a plain "-", no spaces, and a dash between the letters and
    the number ("EF 3", "EF–3" and "EF3" are all "EF-3"); an underscore-joined tag is kept as it is."""
    tag = re.sub(f"[{DASHES}]", "-", text.strip().upper())
    tag = re.sub(r"\s*-\s*", "-", tag)
    if "_" not in tag:
        joined = re.fullmatch(r"([A-Z]{1,8})\s*(\d.*)", tag)
        if joined:
            tag = f"{joined.group(1)}-{joined.group(2)}"
    return re.sub(r"\s+", "", tag)


def natural(tag: str) -> list:
    """Sort key: EF-2 before EF-10."""
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", tag)]


def _spelled(tag: str) -> str:
    """One tag as a pattern allowing any dash, a space or nothing between its parts."""
    parts = [re.escape(p) for p in re.split(f"[{DASHES}]", canonical(tag)) if p]
    return f"(?:[{DASHES}] ?| ?)".join(parts)


def _generic(prefix: str) -> str:
    """Any numbered tag of a prefix: EF-1, EF 12, EF-3A, VAV-2-01."""
    return rf"{re.escape(prefix)}(?:[{DASHES}] ?| ?)\d+[A-Z]?(?:[{DASHES}]\d+[A-Z]?)*"


def family_pattern(tags: Sequence[str], prefix_owners: dict[str, int]) -> str | None:
    """The pattern of one family's tags (a Python regular expression over the tag as printed): any numbered tag of
    a prefix only this family has in the job — so a unit the plans show but the schedule left out still counts —
    and otherwise the family's own tags only. None when the family has no tags."""
    alternatives: list[str] = []
    for tag in tags:
        tag = tag.strip()
        if not tag:
            continue
        prefix = tag_prefix(canonical(tag))
        if "_" not in tag and prefix and prefix_owners.get(prefix, 0) == 1 and re.fullmatch(r"[A-Z]{2,8}", prefix):
            alternative = _generic(prefix)
        else:
            alternative = _spelled(tag)
        if alternative not in alternatives:
            alternatives.append(alternative)
    if not alternatives:
        return None
    return alternatives[0] if len(alternatives) == 1 else "|".join(f"(?:{a})" for a in alternatives)


def prefix_owners(families_tags: Iterable[Sequence[str]]) -> dict[str, int]:
    """How many families of the job have each tag prefix."""
    owners: dict[str, int] = {}
    for tags in families_tags:
        for prefix in {tag_prefix(canonical(t)) for t in tags if t.strip()}:
            owners[prefix] = owners.get(prefix, 0) + 1
    return owners


def searcher(pattern: str) -> re.Pattern:
    """The pattern found inside running text: not part of a longer word or tag."""
    return re.compile(rf"(?<![A-Za-z0-9_])(?:{pattern})(?![A-Za-z0-9])")


def fits(pattern: str, text: str) -> bool:
    """Whether a tag (as read) is one of the pattern's tags."""
    try:
        return re.fullmatch(f"(?:{pattern})", canonical(text)) is not None or \
            re.fullmatch(f"(?:{pattern})", text.strip()) is not None
    except re.error:
        return False


def located_boxes(page: pymupdf.Page, pattern: str, scale: float) -> list[tuple[str, tuple[int, int, int, int]]]:
    """Every placed occurrence of the pattern's tags in the page's text layer: (the tag, its box (x, y, width,
    height) in pixels of the whole-sheet picture as the sheet is viewed, `scale` pixels per point). A tag inside a
    line of more than NOTE_WORDS words is a note naming it, not a placed tag, and is left out."""
    find = searcher(pattern)
    matrix = page.rotation_matrix
    found: list[tuple[str, tuple[int, int, int, int]]] = []
    for block in page.get_text("rawdict").get("blocks", ()):
        for line in block.get("lines", ()):
            text, boxes = _line_chars(line)
            if not text.strip() or len(text.split()) > NOTE_WORDS:
                continue
            for match in find.finditer(text):
                chars = [b for b in boxes[match.start():match.end()] if b is not None]
                if not chars:
                    continue
                rect = pymupdf.Rect(chars[0])
                for box in chars[1:]:
                    rect |= box
                rect = rect * matrix
                rect.normalize()
                x0, y0 = int(rect.x0 * scale), int(rect.y0 * scale)
                x1, y1 = int(rect.x1 * scale + 0.999), int(rect.y1 * scale + 0.999)
                found.append((canonical(match.group(0)), (x0, y0, max(1, x1 - x0), max(1, y1 - y0))))
    return found


def _line_chars(line: dict) -> tuple[str, list[pymupdf.Rect | None]]:
    """A rawdict line as text and one box per character; a space where two spans stand apart."""
    text: list[str] = []
    boxes: list[pymupdf.Rect | None] = []
    last_x1 = None
    for span in line.get("spans", ()):
        size = span.get("size", 10) or 10
        chars = span.get("chars", ())
        if chars and last_x1 is not None and text and text[-1] != " " and \
                chars[0]["bbox"][0] - last_x1 > 0.25 * size:
            text.append(" ")
            boxes.append(None)
        for char in chars:
            c = clean_text(char.get("c", ""))
            if not c:
                continue
            text.append(c[0])
            boxes.append(pymupdf.Rect(char["bbox"]) if not c.isspace() else None)
            last_x1 = char["bbox"][2]
    return "".join(text), boxes
