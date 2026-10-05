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


NUMBER = r"\d+(?:\.\d+)?[A-Z]?"     # a numbered tag part: 1, 12, 3A, 1.5, 3.0
LETTERS = r"[A-Z]{1,2}"             # a lettered tag part: A, B, AB


def is_tag(text: str) -> bool:
    """Whether the text is a whole tag (a letter prefix and a further part: EF-1, TXF-B, CAC-1.5,
    HEL03_04_FCU01), not a bare letter or number left over from a continued list ("B", "2")."""
    return re.fullmatch(r"[A-Z][A-Z0-9]*(?:[-_.][A-Z0-9.]+)+", canonical(text)) is not None


def family_tags(tags: Sequence[str]) -> list[str]:
    """The family's tags one by one, as the planner expands them (`estimator.writing.assemble.expand_tags`:
    "SPXF-A, B, C" is SPXF-A, SPXF-B and SPXF-C; "ACCU-12-1 thru 6" six tags), whole tags only."""
    from estimator.writing.assemble import expand_tags

    written = [str(t).strip() for t in tags or () if str(t).strip()]
    out: list[str] = []
    for tag in expand_tags(written):
        tag = tag.strip()
        if is_tag(tag) and tag not in out:
            out.append(tag)
    return out


def _spelled(tag: str) -> str:
    """One tag as a pattern allowing any dash, a space or nothing before a numbered part, a dash before a lettered
    part ("TXF-B", never "TXFB")."""
    parts = [p for p in re.split(f"[{DASHES}]", canonical(tag)) if p]
    spelled = re.escape(parts[0])
    for part in parts[1:]:
        joint = f"(?:[{DASHES}] ?| ?)" if part[0].isdigit() else f"[{DASHES}] ?"
        spelled += joint + re.escape(part)
    return spelled


def _generic(prefix: str, numbers: bool = True, letters: bool = False) -> str:
    """Any tag of a prefix: numbered (EF-1, EF 12, EF-3A, VAV-2-01, CAC-1.5) and, when the family letters its tags,
    lettered (TXF-B, SPXF-A)."""
    heads = ([f"(?:[{DASHES}] ?| ?){NUMBER}"] if numbers else []) + ([f"[{DASHES}] ?{LETTERS}"] if letters else [])
    part = f"(?:{NUMBER}|{LETTERS})" if letters else NUMBER
    return rf"{re.escape(prefix)}(?:{'|'.join(heads)})(?:[{DASHES}]{part})*"


def family_pattern(tags: Sequence[str], prefix_owners: dict[str, int]) -> str | None:
    """The pattern of one family's tags (a Python regular expression over the tag as printed), built from the
    family's expanded tags (`family_tags`): any tag of a prefix only this family has in the job, numbered or
    lettered as the family's own are — so a unit the plans show but the schedule left out still counts — and
    otherwise the family's own tags only. Never a bare letter or number. None when the family has no tags."""
    alternatives: list[str] = []
    generic: dict[str, set[str]] = {}            # prefix -> the kinds of its first part: "number", "letter"
    for tag in family_tags(tags):
        name = canonical(tag)
        prefix = tag_prefix(name)
        rest = name[len(prefix) + 1:]
        if "_" not in name and rest and prefix_owners.get(prefix, 0) == 1 and re.fullmatch(r"[A-Z]{2,8}", prefix):
            generic.setdefault(prefix, set()).add("number" if rest[0].isdigit() else "letter")
            alternative = prefix                 # placeholder, replaced once every tag's kind is known
        else:
            alternative = _spelled(tag)
        if alternative not in alternatives:
            alternatives.append(alternative)
    alternatives = [_generic(a, "number" in generic[a], "letter" in generic[a]) if a in generic else a
                    for a in alternatives]
    if not alternatives:
        return None
    return alternatives[0] if len(alternatives) == 1 else "|".join(f"(?:{a})" for a in alternatives)


def prefix_owners(families_tags: Iterable[Sequence[str]]) -> dict[str, int]:
    """How many families of the job have each tag prefix (over each family's expanded tags)."""
    owners: dict[str, int] = {}
    for tags in families_tags:
        for prefix in {tag_prefix(canonical(t)) for t in family_tags(tags)}:
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


MIN_TEXT_CHARS = 50


def has_text_layer(page: pymupdf.Page) -> bool:
    """Whether the page has a usable vector text layer (fewer characters indicates a raster/scanned sheet)."""
    text = page.get_text().strip()
    return len(text) >= MIN_TEXT_CHARS


def image_tokens(width: int, height: int) -> int:
    """Estimated image tokens for an image of given pixel dimensions (width * height / 750)."""
    return max(1, (width * height) // 750)


def token_savings(sheet_size: tuple[int, int], crop_boxes: Sequence[tuple[int, int, int, int]]) -> dict:
    """Calculate the image token savings of sending micro-crops vs full sheet tiles."""
    from bms.counts_vision import tile_grid
    grid = tile_grid(sheet_size[0], sheet_size[1])
    full_tokens = sum(image_tokens(w, h) for _, _, w, h in grid)
    crop_tokens = sum(image_tokens(w, h) for _, _, w, h in crop_boxes)
    saved = max(0, full_tokens - crop_tokens)
    pct = round((saved / full_tokens) * 100, 2) if full_tokens > 0 else 0.0
    return {
        "full_sheet_tokens": full_tokens,
        "micro_crop_tokens": crop_tokens,
        "tokens_saved": saved,
        "savings_pct": pct,
    }


def _extract_page_tags(page: pymupdf.Page, pattern: str, scale: float
                       ) -> tuple[list[tuple[str, tuple[int, int, int, int]]],
                                  list[tuple[str, tuple[int, int, int, int], str]]]:
    """Extract both single-line and stacked-line tags, partitioned into confident and ambiguous."""
    find = searcher(pattern)
    matrix = page.rotation_matrix
    confident: list[tuple[str, tuple[int, int, int, int]]] = []
    ambiguous: list[tuple[str, tuple[int, int, int, int], str]] = []
    seen_keys: set[tuple[str, tuple[int, int, int, int]]] = set()

    for block in page.get_text("rawdict").get("blocks", ()):
        lines = block.get("lines", ())
        line_data = []
        for line in lines:
            text, boxes = _line_chars(line)
            if not text.strip() or len(text.split()) > NOTE_WORDS:
                continue
            line_data.append((line, text, boxes))
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
                box = (x0, y0, max(1, x1 - x0), max(1, y1 - y0))
                tag = canonical(match.group(0))
                key = (tag, box)
                if key in seen_keys:
                    continue
                seen_keys.add(key)

                m_start, m_end = match.start(), match.end()
                is_surrounded = (
                    (m_start > 0 and text[m_start - 1] not in " \t") or
                    (m_end < len(text) and text[m_end] not in " \t")
                )
                if is_surrounded:
                    ambiguous.append((tag, box, "surrounded by punctuation or text"))
                elif len(text.split()) >= 3:
                    ambiguous.append((tag, box, "multi-word line near note threshold"))
                else:
                    confident.append((tag, box))

        # Check stacked lines within this block (e.g. VAV on line 1, 1 on line 2)
        for i in range(len(line_data) - 1):
            _l1, t1, b1 = line_data[i]
            _l2, t2, b2 = line_data[i + 1]
            s1, s2 = t1.strip(), t2.strip()
            for cand in (f"{s1}-{s2}", f"{s1}{s2}"):
                match = find.search(cand)
                if match:
                    chars1 = [b for b in b1 if b is not None]
                    chars2 = [b for b in b2 if b is not None]
                    if not chars1 or not chars2:
                        continue
                    rect = pymupdf.Rect(chars1[0])
                    for b in chars1[1:] + chars2:
                        rect |= b
                    rect = rect * matrix
                    rect.normalize()
                    x0, y0 = int(rect.x0 * scale), int(rect.y0 * scale)
                    x1, y1 = int(rect.x1 * scale + 0.999), int(rect.y1 * scale + 0.999)
                    box = (x0, y0, max(1, x1 - x0), max(1, y1 - y0))
                    tag = canonical(match.group(0))
                    key = (tag, box)
                    if key not in seen_keys:
                        seen_keys.add(key)
                        ambiguous.append((tag, box, "stacked lines in block"))
                    break

    return confident, ambiguous


def located_boxes(page: pymupdf.Page, pattern: str, scale: float) -> list[tuple[str, tuple[int, int, int, int]]]:
    """Every placed occurrence of the pattern's tags in the page's text layer: (the tag, its box (x, y, width,
    height) in pixels of the whole-sheet picture as the sheet is viewed, `scale` pixels per point). A tag inside a
    line of more than NOTE_WORDS words is a note naming it, not a placed tag, and is left out."""
    confident, ambiguous = _extract_page_tags(page, pattern, scale)
    return confident + [(t, b) for t, b, _ in ambiguous]


def classify_located_boxes(page: pymupdf.Page, pattern: str, scale: float
                            ) -> tuple[list[tuple[str, tuple[int, int, int, int]]],
                                       list[tuple[str, tuple[int, int, int, int], str]]]:
    """Classify placed tags from the page text layer into confident and ambiguous (with reason)."""
    return _extract_page_tags(page, pattern, scale)


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
