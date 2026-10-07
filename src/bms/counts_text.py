"""Tag patterns and the located-text count (workstream 6): where a family's tags sit in a PDF page's text layer,
as boxes in the pixels of that sheet's whole-sheet picture."""
from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Sequence

import pymupdf

from estimator.catalogue.pdf import clean_text
from estimator.catalogue.tags import NOTE_WORDS, RANGE_SPAN, label_keys, line_labels, plan_labels, tag_prefix

DASHES = "-‐‑–—"
# NOTE_WORDS (from estimator.catalogue.tags): a line of more words than this is a note, never a label line


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
    """One tag as a pattern allowing any dash, a space or nothing before the first numbered part, any dash or a
    space before a later one (VAV-1-01 is never "VAV-101"), a dash before a lettered part ("TXF-B", never
    "TXFB")."""
    parts = [p for p in re.split(f"[{DASHES}]", canonical(tag)) if p]
    spelled = re.escape(parts[0])
    for n, part in enumerate(parts[1:]):
        if not part[0].isdigit():
            joint = f"[{DASHES}] ?"
        else:
            joint = f"(?:[{DASHES}] ?| ?)" if n == 0 else f"(?:[{DASHES}] ?| )"
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
    """The pattern found inside running text: not part of a longer word or tag (VAV-1 is not found in VAV-10,
    VAV-1-01 or XVAV-1, CAC-1 not in CAC-1.5; a full stop or comma after a tag still ends it)."""
    return re.compile(rf"(?<![A-Za-z0-9_])(?:{pattern})(?![A-Za-z0-9]|[{DASHES}.][A-Za-z0-9])")


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

        # a tag split over two lines of this block: a bare prefix over its number ("VAV" over "1"), or a tag
        # ending in a dash over the rest ("VAV-" over "3"); never a tag over a number below it ("EF-1" over "450 CFM")
        for i in range(len(line_data) - 1):
            _l1, t1, b1 = line_data[i]
            _l2, t2, b2 = line_data[i + 1]
            tag = _stacked(t1, t2, pattern, find)
            if tag is None:
                continue
            chars = [b for b in b1 + b2 if b is not None]
            if not chars:
                continue
            rect = pymupdf.Rect(chars[0])
            for b in chars[1:]:
                rect |= b
            rect = rect * matrix
            rect.normalize()
            x0, y0 = int(rect.x0 * scale), int(rect.y0 * scale)
            x1, y1 = int(rect.x1 * scale + 0.999), int(rect.y1 * scale + 0.999)
            box = (x0, y0, max(1, x1 - x0), max(1, y1 - y0))
            if (tag, box) not in seen_keys:
                seen_keys.add((tag, box))
                ambiguous.append((tag, box, "stacked lines in block"))

    return confident, ambiguous


_BARE_PREFIX = re.compile(r"[A-Z]{1,8}")
_ENDS_IN_DASH = re.compile(rf"[A-Z][A-Z0-9]*(?:[{DASHES}][A-Z0-9.]+)*[{DASHES}]")
_BARE_PART = re.compile(rf"(?:{NUMBER}|{LETTERS})(?:[{DASHES}](?:{NUMBER}|{LETTERS}))*")


def _stacked(first: str, second: str, pattern: str, find: re.Pattern) -> str | None:
    """The tag two consecutive lines make together, or None: the first line a bare prefix ("VAV") or a tag ending in
    a dash ("VAV-"), the second a bare number or letter part ("1", "3A", "B"), and the two joined the whole of one
    of the pattern's tags. Never where either line holds a tag already (EF-1 over "450 CFM" is EF-1 alone)."""
    first, second = first.strip(), second.strip()
    if not first or not second or find.search(first) or find.search(second):
        return None
    if not _BARE_PART.fullmatch(second):
        return None
    if _ENDS_IN_DASH.fullmatch(first):
        joined = first + second
    elif _BARE_PREFIX.fullmatch(first):
        joined = f"{first}-{second}"
    else:
        return None
    try:
        return canonical(joined) if re.fullmatch(f"(?:{pattern})", joined) else None
    except re.error:
        return None


def _page_lines(page: pymupdf.Page) -> list[list[str]]:
    """The page's text as it is drawn: each rawdict block's lines (`_line_chars`), block by block."""
    return [[_line_chars(line)[0] for line in block.get("lines", ())]
            for block in page.get_text("rawdict").get("blocks", ())]


_RANGE_AFTER = re.compile(rf"\s*(?:THRU|THROUGH)\s*", re.I)


def _range_tags(text: str, pattern: str, find: re.Pattern) -> set[str]:
    """The tags between the ends of each "VAV-1 THRU VAV-5" (or "VAV-1 THRU 5") range of a line whose ends are the
    pattern's tags, so `line_labels` can read the range's members of a family that does not list them."""
    found: set[str] = set()
    for low in find.finditer(text):
        after = _RANGE_AFTER.match(text, low.end())
        if after is None:
            continue
        high = find.match(text, after.end())
        number = re.match(r"\d+(?![A-Za-z0-9])", text[after.end():]) if high is None else None
        if high is None and number is None:
            continue
        a = re.fullmatch(r"(.*?)(\d+)", canonical(low.group(0)))
        b = re.fullmatch(r"(.*?)(\d+)", canonical(high.group(0)) if high else f"{a.group(1) if a else ''}"
                                                                        f"{number.group(0)}")
        if a is None or b is None or a.group(1) != b.group(1) or not 0 < int(b.group(2)) - int(a.group(2)) <= RANGE_SPAN:
            continue
        width = len(a.group(2)) if a.group(2).startswith("0") else 0
        for n in range(int(a.group(2)), int(b.group(2)) + 1):
            tag = f"{a.group(1)}{str(n).zfill(width)}"
            if fits(pattern, tag):
                found.add(tag)
    return found


def located_labels(page: pymupdf.Page, pattern: str, listed: Iterable[str] = ()) -> Counter:
    """Each of the pattern's tags placed on the page's text layer and how many places it is labelled, read by the
    planner's one label reader (`estimator.catalogue.tags.line_labels` over each block's lines, and `plan_labels`):
    a tag alone or starting a line of at most NOTE_WORDS words ("EF-2 ON ROOF ABOVE CORRIDOR SECOND FLOOR"), a
    bubble or a tag split over two lines, a THRU range's members ("VAV-1 THRU VAV-5" is five), a stated count of
    places ("CUH-A (TYP. OF 4)" is four), never a tag after a word like TO or SEE. `listed` are the families' own
    tags: one of them that is a unit's tag named anywhere on the page and labelled nowhere counts once (the
    `plan_labels` backstop); a tag the pattern finds that no family lists counts only where it is labelled."""
    return located_tallies(page, pattern, listed)[0]


def located_tallies(page: pymupdf.Page, pattern: str, listed: Iterable[str] = ()) -> tuple[Counter, Counter]:
    """(`located_labels`, the labels alone without the backstop): the labels alone are the evidence of which plan
    sheets show one plan (`estimator.reading.inventory.plan_groups`), never the backstop."""
    find = searcher(pattern)
    blocks = _page_lines(page)
    found = {canonical(t) for t in listed if fits(pattern, t)}
    for lines in blocks:
        for n, text in enumerate(lines):
            found |= {canonical(m.group(0)) for m in find.finditer(text)}
            found |= _range_tags(text, pattern, find)
            if n + 1 < len(lines) and (tag := _stacked(text, lines[n + 1], pattern, find)) is not None:
                found.add(tag)
    keys = label_keys(sorted(found, key=natural))
    labels: Counter = Counter()
    for lines in blocks:
        labels.update(line_labels("\n".join(lines), keys))
    own = label_keys(sorted({canonical(t) for t in listed if fits(pattern, t)}, key=natural))
    page_text = "\n".join(line for lines in blocks for line in lines)
    tally = plan_labels(page_text, own, labels) if own else labels

    def mine(counter: Counter) -> Counter:
        return Counter({tag: n for tag, n in counter.items() if n > 0 and fits(pattern, tag)})

    return mine(tally), mine(labels)


def located_boxes(page: pymupdf.Page, pattern: str, scale: float) -> list[tuple[str, tuple[int, int, int, int]]]:
    """Every placed occurrence of the pattern's tags in the page's text layer: (the tag, its box (x, y, width,
    height) in pixels of the whole-sheet picture as the sheet is viewed, `scale` pixels per point). A tag inside a
    line of more than NOTE_WORDS words is a note naming it, not a placed tag, and is left out. These are where the
    tags are; how many places each is labelled is `located_labels`."""
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
