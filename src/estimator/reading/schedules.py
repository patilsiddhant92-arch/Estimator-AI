"""The equipment schedules on the drawing sheets, read table by table (build step 4, design §9.3).

A schedule lists one row per unit, so a unit's quantity is its tag: the schedule has no QTY
column. `page.find_tables()` finds each ruled table; one table can hold several schedules,
stacked or side by side, so a table is split at every header cell that names the tag column
(UNIT No., TAG, MARK, DESIGNATION). The words, patterns and limits live in
`assets/reading_lists/schedules.json`.
"""
from __future__ import annotations

import bisect
import hashlib
import json
import re
from collections.abc import Callable, Collection, Iterable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pymupdf

from estimator.catalogue.job import CONTROLS_DISCIPLINES
from estimator.catalogue.pdf import clean_text
from estimator.catalogue.tags import Equipment, find_tags, located_tags, sheet_number_tags, tag_prefix
from estimator.reading.pages import unreadable_page

ASSETS = Path(__file__).resolve().parents[3] / "assets"
SCHEDULES = ASSETS / "reading_lists" / "schedules.json"
_DASH = r"\-‐‑–—"   # escaped: it sits inside character classes

PageOpener = Callable[[str, int], pymupdf.Page]


@dataclass(frozen=True)
class ScheduleRow:
    tag: str | None            # canonical tag (find_tags), None on a type-only row
    cells: dict[str, str]      # header → cell text, as extracted
    manufacturer: str | None
    model: str | None
    existing: bool = False     # the row says EXISTING, EXIST., (E) or TO REMAIN: not new work
    kind: str | None = None    # set only when the tag's prefix isn't in equipment.json: the schedule's title says what it is
    shares: int = 1            # how many tags the schedule row lists ("A THRU C", several tags in one cell)


@dataclass(frozen=True)
class Schedule:
    document: str
    page: int
    sheet: str | None
    title: str                 # e.g. "VAV BOX SCHEDULE"
    headers: tuple[str, ...]
    rows: tuple[ScheduleRow, ...]
    type_only: bool            # no row has a tag
    notes: tuple[str, ...]     # numbered notes under / beside the table
    controls_by: tuple[str, ...]   # the note sentences that say who provides the unit controller
    from_text: bool = False    # counted from the sheet's text, because its table couldn't be read
    source: str = "table"      # "table", or BY_EYE: a picture of the schedule read by the AI judge (reading/pictures.py)
    passive: bool = False      # lists passive air devices by type (diffusers, grilles, air outlets: READ-3); its codes
                               # are never units, equipment families or controls systems, whatever their prefix


@dataclass(frozen=True)
class Vocabulary:
    tag_headers: frozenset[str]
    type_headers: frozenset[str]
    manufacturer_headers: tuple[str, ...]
    model_headers: tuple[str, ...]
    notes_headers: tuple[str, ...]
    basis: tuple[re.Pattern, ...]
    existing: re.Pattern
    controls: re.Pattern
    range_words: tuple[str, ...]
    notes_heading: re.Pattern
    note_number: re.Pattern
    schedule_text: re.Pattern
    header_line: re.Pattern
    border_share: float
    min_rows: int
    min_columns: int
    notes_below: float
    pairs: tuple[tuple[str, str], ...]
    not_schedules: re.Pattern   # tables keyed by tag that aren't equipment schedules (refrigerant calculations)
    type_titles: re.Pattern     # schedules that list types of air device or fixture, never units
    schedule_heading: re.Pattern   # a line of text that heads a schedule ("EXHAUST FAN SCHEDULE")
    quantity_headers: frozenset[str] = frozenset()   # a column that counts the units a row stands for (QTY)
    tag_header_pattern: re.Pattern | None = None     # a key header the exact list misses ("UNIT", "PUMP NO."), READ-5
    air_devices: re.Pattern | None = None            # words naming passive air devices (READ-3)


def _any(patterns: Iterable[str]) -> re.Pattern:
    return re.compile("|".join(f"(?:{p})" for p in patterns), re.I)


@lru_cache
def vocabulary(path: Path = SCHEDULES) -> Vocabulary:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    header_words = "|".join(r"\s+".join(re.escape(w) for w in h.split()) for h in data["tag_headers"])
    return Vocabulary(
        frozenset(data["tag_headers"]), frozenset(data["type_headers"]),
        tuple(data["manufacturer_headers"]), tuple(data["model_headers"]), tuple(data["notes_headers"]),
        tuple(re.compile(p, re.I) for p in data["basis_of_design"]),
        _any(data["existing_words"]), _any(data["controls_phrases"]), tuple(data["range_words"]),
        re.compile(data["notes_heading"], re.I), re.compile(data["note_number"]),
        re.compile(data["schedule_sheet_text"], re.I),
        re.compile(rf"(?mi)^\s*(?:{header_words})\s*[.:]?\s*$"),
        float(data["border_share"]), int(data["min_rows"]), int(data["min_columns"]), float(data["notes_below"]),
        tuple((a, b) for a, b in data["pairs"]), _any(data["not_schedules"]), _any(data["type_list_titles"]),
        re.compile(data["schedule_heading"]), frozenset(data.get("quantity_headers", ())),
        tag_header_pattern=re.compile(data["tag_header_pattern"]) if data.get("tag_header_pattern") else None,
        air_devices=_any(data["air_device_words"]) if data.get("air_device_words") else None,
    )


def _squash(text: str | None) -> str:
    return " ".join(clean_text(text or "").split())


def header_key(text: str | None) -> str:
    """A header cell as compared with the reading list: spaces squashed, capitals, no trailing stop."""
    return _squash(text).upper().rstrip(".:").strip()


def quantity_header(schedule: "Schedule", vocab: Vocabulary | None = None) -> str | None:
    """The schedule's column that counts the units a row stands for (QUANTITY, QTY., NO.), if it has one."""
    words = (vocab or vocabulary()).quantity_headers
    return next((h for h in schedule.headers if header_key(h) in words), None)


def _is(header: str, words: Iterable[str]) -> bool:
    key = header_key(header)
    return any(key == w or key.startswith(w + " ") for w in words)


# --- tags, with THRU ranges and comma lists expanded ------------------------------------------

_SPLIT = re.compile(r"^(.*?)(\d+)$")


def _one_tag(text: str, equipment: Equipment) -> str | None:
    found = find_tags(text, equipment, joined=True)
    return found[0] if len(found) == 1 else None


def _numbered(stem: str, first: str, n: int) -> str:
    width = len(first) if first.startswith("0") else 0
    return f"{stem}{str(n).zfill(width)}"


def expand_tags(text: str, equipment: Equipment | None = None, range_words: tuple[str, ...] | None = None) -> list[str]:
    """Every tag a cell names: "VAV-1 THRU VAV-12", "VAV-1 THRU 12" and "EF-1,2,3" give one tag per unit."""
    equipment = equipment or Equipment.load()
    words = "|".join(range_words or vocabulary().range_words)
    text = clean_text(text or "").upper()
    token = rf"[A-Z][A-Z0-9#{_DASH}]*\d"
    found: list[tuple[int, str]] = []
    spans: list[tuple[int, int]] = []
    for start, end, tags in located_tags(text, equipment):     # HEL03_04_FCU01, HEL03_04_TWAS01 THRU TWAS03
        found += [(start, tag) for tag in tags]
        spans.append((start, end))
    if spans:
        text = "".join(" " if any(a <= i < b for a, b in spans) else ch for i, ch in enumerate(text))
    for m in re.finditer(rf"(?<![A-Z0-9])({token})\s*(?:{words})\s*((?:[A-Z][A-Z0-9#{_DASH}]*)?\d+)(?![A-Z0-9])", text):
        first = _one_tag(m.group(1), equipment)
        if first is None or not _SPLIT.match(first):
            continue
        stem, low = _SPLIT.match(first).groups()
        if m.group(2).isdigit():
            high_stem, high = stem, m.group(2)
        else:
            last = _one_tag(m.group(2), equipment)
            if last is None or not _SPLIT.match(last):
                continue
            high_stem, high = _SPLIT.match(last).groups()
        if high_stem != stem or not 0 < int(high) - int(low) <= 200:
            continue
        found += [(m.start(), _numbered(stem, low, n)) for n in range(int(low), int(high) + 1)]
        spans.append(m.span())
    for m in re.finditer(rf"(?<![A-Z0-9])({token})((?:\s*[,&]\s*\d+(?![A-Z0-9{_DASH}]))+)", text):
        if any(a <= m.start() < b for a, b in spans):
            continue
        first = _one_tag(m.group(1), equipment)
        if first is None or not _SPLIT.match(first):
            continue
        stem, low = _SPLIT.match(first).groups()
        found.append((m.start(), first))
        found += [(m.start(), _numbered(stem, n, int(n))) for n in re.findall(r"\d+", m.group(2))]
        spans.append(m.span())
    rest = "".join(" " if any(a <= i < b for a, b in spans) else ch for i, ch in enumerate(text))
    by_code, by_name = equipment.patterns()
    found += [(m.start(), tag) for m in by_code.finditer(rest) for tag in find_tags(m.group(0), equipment, joined=True)[:1]]
    found += [(m.start(), tag) for m in by_name.finditer(rest) for tag in find_tags(m.group(0), equipment)[:1]]
    return [tag for _, tag in sorted(found, key=lambda f: f[0])]


_LOOSE = re.compile(rf"^([A-Z]{{2,6}})(\d*)((?:[{_DASH}][A-Z0-9]+)*)$")
_NO_TITLE = "Schedule (no title found)"


def _loose_one(text: str) -> tuple[str, str] | None:
    """(prefix, canonical tag) for a tag-shaped cell — two or more letters, then digits or a dash ("TXF-B",
    "DXF1-1"). A single letter ("A-1", "C-2") is a type code, never a unit's prefix, in a tag column."""
    m = _LOOSE.match(text)
    if not m or not (m.group(2) or m.group(3)):
        return None
    tail = re.sub(f"[{_DASH}]", "-", m.group(2) + m.group(3)).lstrip("-")
    return m.group(1), f"{m.group(1)}-{tail}"


def loose_tags(text: str, equipment: Equipment, range_words: tuple[str, ...] | None = None) -> list[str]:
    """Every tag a tag cell names when its prefix isn't in the equipment list: "TXF-B", "SPXF-A,B,C" (three
    fans), "XF-1 THRU XF-4" or "XF-1 THRU 4". Empty when the cell isn't tag-shaped, or its prefix is known
    (expand_tags reads those)."""
    words = "|".join(range_words or vocabulary().range_words)
    text = re.sub(r"^\(E\)\s*", "", clean_text(text or "").upper().strip())
    ranged = re.fullmatch(rf"(\S+)\s*(?:{words})\s*(\S+)", text)
    if ranged:
        first, last = _loose_one(ranged.group(1)), ranged.group(2)
        split = _SPLIT.match(first[1]) if first is not None and first[0] not in equipment.prefixes else None
        if split is None:
            return []
        stem, low = split.groups()
        if last.isdigit():
            high = last
        else:
            other = _loose_one(last)
            high = other[1][len(stem):] if other is not None and other[1].startswith(stem) else ""
        if not high.isdigit() or not 0 < int(high) - int(low) <= 200:
            return []
        return [_numbered(stem, low, n) for n in range(int(low), int(high) + 1)]
    parts = [part for part in re.split(r"\s*[,&]\s*", text) if part]
    first = _loose_one(parts[0]) if parts else None
    if first is None or first[0] in equipment.prefixes:
        return []
    tags = [first[1]]
    for part in parts[1:]:
        if re.fullmatch(r"[A-Z0-9]{1,3}", part) and "-" in first[1]:
            tags.append(f"{first[1].rsplit('-', 1)[0]}-{part}")       # "SPXF-A,B,C"
        elif (other := _loose_one(part)) is not None and other[0] == first[0]:
            tags.append(other[1])
        else:
            return []
    return tags


EQUIPMENT = "Equipment"


def unit_tags_in_cell(text: str | None, equipment: Equipment) -> list[str]:
    """The unit tags a key cell starts with ("EF-14-1", "(E) AHU-3", "VAV-1 THRU 5"); empty when the cell is not a
    unit's tag (a type code, a note, a line that only mentions a unit)."""
    text = _squash(text)
    if not text:
        return []
    tags = expand_tags(text, equipment)
    if not tags or not _compact(re.sub(r"^\(E\)\s*", "", text, flags=re.I)).startswith(_compact(tags[0])):
        return []
    return tags


def lists_air_devices(title: str, vocab: Vocabulary, also: Iterable[str] = (), described: Iterable[str] = ()) -> bool:
    """A schedule of passive air devices by type (READ-3): its title, or one of the lines `also` gives (its basis of
    design, a band row of its key column such as "RETURN AND EXHAUST GRILLE"), names air devices, or most of its
    description cells (`described`) do. Its codes (B1, CD, RG, LRD-A) are types, never units."""
    pattern = vocab.air_devices
    if pattern is None:
        return False
    if pattern.search(title or "") or any(pattern.search(t or "") for t in also):
        return True
    described = [d for d in described if d]
    return bool(described) and sum(bool(pattern.search(d)) for d in described) * 2 > len(described)


_DESCRIPTION_HEADER = re.compile(r"^(?:DESCRIPTION|TYPE|DEVICE|STYLE|KIND)\b")


def _one_letter_elsewhere(tag: str, cell: str, title: str, equipment: Equipment) -> bool:
    """A one-letter prefix written without its dash ("B1", "P2") under a schedule whose title names another kind of
    equipment (an AIR OUTLET SCHEDULE's B1 is no boiler, READ-3). An untitled schedule keeps it: a boiler schedule
    whose title wasn't found must not lose its boilers."""
    prefix = tag_prefix(tag)
    if len(prefix) != 1 or re.match(rf"\s*(?:\(E\)\s*)?{prefix}\s*[{_DASH}]", cell or "", re.I):
        return False
    kind = kind_from_title(title or _NO_TITLE)
    if kind == EQUIPMENT:
        return False
    name = equipment.prefixes.get(prefix, "")
    return not any(word in kind.upper() for word in name.upper().split() if len(word) > 2)


def kind_from_title(title: str) -> str:
    """What a schedule lists, from its title: "FAN SCHEDULE" → "Fan". A title that doesn't name a schedule
    (none was found, or a notes block was read in its place) says nothing: "Equipment"."""
    if (title == _NO_TITLE or len(title) > 60 or not re.search(r"\bSCHEDULES?\b", title, re.I)
            or re.match(r"\s*(?:\d|REMARKS?\b|NOTES?\b)", title, re.I)):
        return EQUIPMENT
    words = re.sub(r"\([^)]*\)", " ", title)
    words = " ".join(re.sub(r"\bSCHEDULES?\b", " ", words, flags=re.I).split()).strip(" -–—:,")
    return words.title() if words else EQUIPMENT


# --- the page's words, found by position --------------------------------------------------------

class _Words:
    def __init__(self, page: pymupdf.Page):
        words = [w for w in page.get_text("words") if w[4].strip()]
        if page.rotation:
            # Words come in the page's unrotated coordinates; its tables, as the sheet is viewed.
            matrix = page.rotation_matrix
            words = [(*pymupdf.Rect(w[:4]).transform(matrix), *w[4:]) for w in words]
            words = [(min(w[0], w[2]), min(w[1], w[3]), max(w[0], w[2]), max(w[1], w[3]), *w[4:]) for w in words]
        words.sort(key=lambda w: (w[1] + w[3]) / 2)
        self.words = words
        self.middles = [(w[1] + w[3]) / 2 for w in words]

    def band(self, y0: float, y1: float) -> list[tuple]:
        """The words whose middle is at or below y0 and above y1: each word falls in one row only."""
        a = bisect.bisect_left(self.middles, y0)
        b = bisect.bisect_left(self.middles, y1)
        return self.words[a:b]

    def starting_in(self, rect: tuple[float, float, float, float]) -> str:
        """The words that start inside a cell, whole even when they run past its right edge."""
        x0, y0, x1, y1 = rect
        chosen = [w for w in self.band(y0, y1) if x0 - 1 <= w[0] < x1]
        chosen.sort(key=lambda w: (round(w[1]), w[0]))
        return _squash(" ".join(w[4] for w in chosen))

    def lines(self, x0: float, y0: float, x1: float, y1: float) -> list[tuple[float, float, float, str]]:
        """Text lines (top, height, left, text) whose words start in the area, top to bottom."""
        groups: dict[tuple[int, int], list[tuple]] = {}
        for w in self.band(y0, y1):
            if x0 <= w[0] < x1:
                groups.setdefault((w[5], w[6]), []).append(w)
        out = []
        for ws in groups.values():
            ws.sort(key=lambda w: w[0])
            out.append((min(w[1] for w in ws), max(w[3] - w[1] for w in ws), ws[0][0], _squash(" ".join(w[4] for w in ws))))
        return sorted(out)


# --- one table, split into its schedules ------------------------------------------------------

@dataclass
class _Head:
    row: int
    col: int
    kind: str                   # "tag" | "type"
    title_row: int = -1
    title: str = ""
    basis: str | None = None
    end_col: int = 0
    end_row: int = 0


class _Grid:
    def __init__(self, table):
        self.bbox = tuple(table.bbox)
        self.texts = [[_squash(c) for c in row] for row in table.extract()]
        self.rects = [list(row.cells) for row in table.rows]
        # A row's own height runs to the next row's top: a merged cell can reach far into the rows below.
        tops = [row.bbox[1] for row in table.rows] + [table.bbox[3]]
        self.bands = [(tops[r], max(tops[r], min(tops[r + 1:]))) for r in range(len(table.rows))]
        self.n_rows = len(self.texts)
        self.n_cols = max((len(r) for r in self.texts), default=0)

    def text(self, r: int, c: int) -> str:
        return self.texts[r][c] if c < len(self.texts[r]) else ""

    def rect(self, r: int, c: int) -> tuple | None:
        return self.rects[r][c] if c < len(self.rects[r]) else None

    def row_box(self, r: int, c0: int, c1: int) -> tuple[float, float, float, float] | None:
        boxes = [self.rect(r, c) for c in range(c0, c1)]
        boxes = [b for b in boxes if b]
        if not boxes:
            return None
        top, bottom = self.bands[r]
        return (min(b[0] for b in boxes), max(top, min(b[1] for b in boxes)),
                max(b[2] for b in boxes), min(bottom, max(b[3] for b in boxes)))


def _tagged_below(grid: _Grid, r: int, c: int, vocab: Vocabulary, equipment: Equipment) -> tuple[int, int]:
    """(cells naming a unit, cells with text) in column c below row r, a notes line left out. A one-letter
    prefix written without its dash ("B1") is a type code here, never a unit. A column naming one unit in two
    rows or more is no key column (an ASSOCIATED CONDENSING UNIT column names each outdoor unit on every indoor
    unit's row): (0, cells) then."""
    tagged = filled = 0
    seen: set[str] = set()
    for row in range(r + 1, grid.n_rows):
        text = grid.text(row, c)
        if not text or vocab.notes_heading.match(text) or vocab.note_number.match(text):
            continue
        filled += 1
        tags = unit_tags_in_cell(text, equipment) or loose_tags(text, equipment)
        if tags and seen & set(tags):
            return 0, filled
        seen |= set(tags)
        tagged += bool(tags) and (len(tag_prefix(tags[0])) > 1 or bool(re.match(rf"[A-Z]\s*[{_DASH}]", text)))
    return tagged, filled


_BARE_KEY = re.compile(r"^(?:UNIT|TAG|MARK)(?: NO| NUMBER)?$")


def _heads(grid: _Grid, vocab: Vocabulary, equipment: Equipment | None = None) -> list[_Head]:
    """The schedules' key cells: a header the reading list names (TAG, UNIT NO., MARK ...), or, given the equipment
    list, one shaped like one ("UNIT", "AC UNIT", "PUMP NO.") over a column of unit tags (READ-5). A table with no
    such header whose first filled column is unit tags under a blank header (a "F A N  D A T A" band merged over
    it) is keyed by that column, its header the first row of labels above the tags."""
    heads = []
    for r in range(grid.n_rows - 1):
        row = [header_key(grid.text(r, c)) for c in range(grid.n_cols)]
        tagged = [c for c, key in enumerate(row) if key in vocab.tag_headers]
        if equipment is not None and vocab.tag_header_pattern is not None:
            first = next((c for c, key in enumerate(row) if key), None)
            for c, key in enumerate(row):
                if (c in tagged or not key or key in vocab.quantity_headers or key in vocab.type_headers
                        or not vocab.tag_header_pattern.match(key)):
                    continue
                if c != first and not _BARE_KEY.match(key):
                    continue    # "ASSOCIATED CONDENSING UNIT" further along a row names another unit, not the row's
                units, filled = _tagged_below(grid, r, c, vocab, equipment)
                if units and units * 2 >= filled:
                    tagged.append(c)
            tagged.sort()
        heads += [_Head(r, c, "tag") for c in tagged]
        if not tagged:
            first = next((c for c, key in enumerate(row) if key), None)
            if first is not None and row[first] in vocab.type_headers:
                heads.append(_Head(r, first, "type"))
    if heads or equipment is None:
        return heads
    return _blank_head(grid, vocab, equipment)


def _blank_head(grid: _Grid, vocab: Vocabulary, equipment: Equipment) -> list[_Head]:
    """The key column of a table whose key header is blank (READ-5): the first column with text below the header
    rows whose cells are mostly unit tags, its header cell empty. The header row is the first row above the first
    tag with two or more labels in it."""
    for c in range(grid.n_cols):
        rows = [r for r in range(grid.n_rows) if grid.text(r, c)]
        if not rows:
            continue
        first_tag = next((r for r in rows if unit_tags_in_cell(grid.text(r, c), equipment)), None)
        if first_tag is None or first_tag == 0:
            return []
        header = next((r for r in range(first_tag) if not grid.text(r, c)
                       and sum(bool(grid.text(r, k)) for k in range(grid.n_cols)) >= 2), None)
        if header is None:
            return []
        units, filled = _tagged_below(grid, header, c, vocab, equipment)
        return [_Head(header, c, "tag")] if units and units * 2 >= filled else []
    return []


def _title(grid: _Grid, words: _Words, head: _Head, vocab: Vocabulary) -> None:
    """The schedule's name: the row above its header (skipping a "BASIS OF DESIGN" line, which
    names the maker instead), or the text line just above the table."""
    head.title_row = head.row
    blocked = False
    for r in range(head.row - 1, max(-1, head.row - 4), -1):
        filled = [c for c in range(head.col, head.end_col) if grid.text(r, c)]
        if not filled:
            continue
        if len(filled) > 3:
            blocked = True
            break
        box = grid.row_box(r, head.col, head.end_col)
        text = (words.starting_in(box) if box else "") or " ".join(grid.text(r, c) for c in filled)
        if _LETTER_SPACED.match(text):
            continue        # a band over the columns ("F A N  D A T A"), never the schedule's name
        # each text line of the cell on its own: a smaller "MFR. (AS STD.) ..." line can sit a little above the
        # title in the same cell ("CONDENSATE PUMPS"), and its maker must not swallow the title
        lines = [line[3] for line in words.lines(box[0] - 1, box[1], box[2] + 1, box[3])] if box else []
        kept = []
        for line in lines or [text]:
            for pattern in vocab.basis:
                m = pattern.search(line)
                if m:
                    head.basis = head.basis or m.group(1).strip() or None
                    line = line[:m.start()].strip()
                    break
            if line:
                kept.append(line)
        text = " ".join(kept)
        head.title_row = r
        if text:
            head.title = text
            return
    if not blocked and head.row <= 3:
        box = grid.row_box(head.row, head.col, head.end_col) or grid.bbox
        if grid.rect(head.row, head.col) is None and head.col == 0:
            box = (grid.bbox[0], *box[1:])   # a blank key header merged away: the table's own left edge
        above = words.lines(box[0] - 2, grid.bbox[1] - 40, box[2], grid.bbox[1] + 1)
        above = [line for line in above if line[0] + line[1] <= grid.bbox[1] + 2]
        rows: list[list[tuple]] = []           # the lines side by side at one height are one line, left to right
        for line in above:
            if rows and abs(line[0] - rows[-1][0][0]) <= 2:
                rows[-1].append(line)
            else:
                rows.append([line])
        for row in reversed(rows):
            text = " ".join(part[3] for part in sorted(row, key=lambda part: part[2]))
            for pattern in vocab.basis:          # "MFR. (AS STD.) GREENHECK" names the maker, not the schedule
                m = pattern.search(text)
                if m:
                    head.basis = head.basis or m.group(1).strip() or None
                    text = text[:m.start()].strip()
                    break
            if text:
                head.title = text
                break


_LETTER_SPACED = re.compile(r"^(?:[A-Z0-9]\s){3,}")


def _labels(grid: _Grid, head: _Head) -> list[tuple[int, str]]:
    labels, seen = [], set()
    for c in range(head.col, head.end_col):
        label = grid.text(head.row, c)
        if not label:
            continue
        name, n = label, 2
        while name in seen:
            name, n = f"{label} ({n})", n + 1
        seen.add(name)
        labels.append((c, name))
    return labels


def _notes_from(lines: Iterable[str], vocab: Vocabulary) -> list[str]:
    notes: list[str] = []
    started = False
    for line in lines:
        if not line:
            continue
        heading = vocab.notes_heading.match(line)
        if heading:
            started = True
            line = line[heading.end():].strip()
            if not line:
                continue
        if vocab.note_number.match(line):
            started = True
            notes.append(line)
        elif started and notes:
            notes[-1] = f"{notes[-1]} {line}"
        elif started:
            notes.append(line)
    return notes


def _controls_by(notes: Iterable[str], remarks: Iterable[str], vocab: Vocabulary) -> tuple[str, ...]:
    found: list[str] = []
    for note in notes:
        body = vocab.note_number.sub("", note, count=1).strip()
        for sentence in re.split(r"(?<=[.;])\s+", body):
            if sentence and vocab.controls.search(sentence):
                found.append(sentence)
    found += [r for r in remarks if vocab.controls.search(r)]
    return tuple(dict.fromkeys(found))


def _schedule(grid: _Grid, words: _Words, head: _Head, vocab: Vocabulary, equipment: Equipment,
              where: tuple[str, int, str | None], other_tables: list[tuple]) -> Schedule:
    labels = _labels(grid, head)
    names = dict(labels)
    key_name = names.get(head.col, grid.text(head.row, head.col))
    maker_cols = [c for c, name in labels if _is(name, vocab.manufacturer_headers)]
    model_cols = [c for c, name in labels if _is(name, vocab.model_headers)]
    remark_cols = [c for c, name in labels if _is(name, vocab.notes_headers)]
    tagged: list[ScheduleRow] = []
    typed: list[ScheduleRow] = []
    # Rows whose tag cell is tag-shaped but has a prefix the equipment list doesn't know: units under a tag
    # column, unless most of the column is bare type letters (CD, EG, RG) or the schedule lists air devices.
    loose: list[tuple[int, list[ScheduleRow]]] = []
    bare = 0          # rows under the tag column that are bare type letters, neither tag-shaped nor a header
    kind = kind_from_title(head.title or _NO_TITLE)
    note_lines: list[str] = []
    in_notes = False
    # The tag column is as wide as its header cell. Its words are read by position, row band by
    # row band, so a tag split across two grid columns, or a cell merged over several rows, is
    # read once and whole.
    # a blank key header merged into a band above it has no cell of its own: the column's first cell below gives it
    head_rect = (grid.rect(head.row, head.col)
                 or next((grid.rect(r, head.col) for r in range(head.row + 1, grid.n_rows) if grid.rect(r, head.col)),
                         None)
                 or grid.bbox)
    tag_x0, tag_x1 = head_rect[0], head_rect[2]
    after = next((grid.rect(head.row, c) for c, _ in labels if c > head.col and grid.rect(head.row, c)), None)
    wide_x1 = after[2] if after else tag_x1
    passive = _passive(grid, head, labels, vocab, equipment)
    for r in range(head.row + 1, head.end_row):
        top, bottom = grid.bands[r]
        tag_text = words.starting_in((tag_x0, top, tag_x1, bottom))
        key_text = grid.text(r, head.col) or tag_text
        if not in_notes and vocab.notes_heading.match(key_text) and not expand_tags(key_text, equipment):
            in_notes = True
        if in_notes:
            note_lines.append(" ".join(grid.text(r, c) for c in range(head.col, head.end_col) if grid.text(r, c)))
            continue
        tags = expand_tags(tag_text, equipment) if _names_a_unit(tag_text, vocab, equipment) else []
        if tags and not _compact(re.sub(r"^\(E\)\s*", "", tag_text, flags=re.I)).startswith(_compact(tags[0])):
            tags = []   # a line of text that mentions a unit, not the unit's own row
        if passive or (tags and _one_letter_elsewhere(tags[0], tag_text, head.title, equipment)):
            tags = []   # an air device's type code (B1, CD) or a one-letter code under another kind's title (READ-3)
        if not tags and not passive and tag_text and wide_x1 > tag_x1 and _names_a_unit(tag_text, vocab):
            # A tag split over two columns ("VAV" | "-503"): kept only when it starts in the tag column,
            # never a tag named in the next column ("ST-1S" | "AHU-1 SUPPLY").
            joined = words.starting_in((tag_x0, top, wide_x1, bottom))
            found = expand_tags(joined, equipment)
            if found and _compact(found[0]).startswith(_compact(tag_text.split()[0])):
                tags, tag_text = found, joined
            if tags and _one_letter_elsewhere(tags[0], tag_text, head.title, equipment):
                tags = []
        tag_text = tag_text or key_text
        cells = {name: grid.text(r, c) for c, name in labels}
        cells[key_name] = tag_text
        maker = next((grid.text(r, c) for c in maker_cols if grid.text(r, c)), None) or head.basis
        model = next((grid.text(r, c) for c in model_cols if grid.text(r, c)), None)
        remarks = " ".join(grid.text(r, c) for c in remark_cols)
        existing = bool(vocab.existing.search(tag_text) or vocab.existing.search(remarks))
        found = ([] if tags or passive or head.kind != "tag" or not _names_a_unit(tag_text, vocab)
                 else loose_tags(tag_text, equipment))
        if tags:
            tagged += [ScheduleRow(tag, cells, maker, model, existing, shares=len(tags)) for tag in tags]
        elif found:
            loose.append((len(tagged), [ScheduleRow(tag, cells, maker, model, existing, kind, len(found))
                                        for tag in found]))
        if not tags and tag_text and len(tag_text) <= 12 and not vocab.note_number.match(tag_text):
            typed.append(ScheduleRow(None, cells, maker, model, existing))
            bare += not found and header_key(tag_text) not in vocab.tag_headers
    notes = _notes_from(note_lines, vocab)
    if not notes and head.end_row == grid.n_rows:
        box = grid.row_box(head.row, head.col, head.end_col) or grid.bbox
        below = words.lines(box[0] - 5, grid.bbox[3] - 1, box[2], grid.bbox[3] + vocab.notes_below)
        below = [line for line in below if not any(_inside(line[2] + 1, line[0] + line[1] / 2, t) for t in other_tables)]
        kept, last = [], None
        for top, height, _, text in below:
            if last is not None and top - last > 3 * max(height, 1):
                break
            if kept or vocab.notes_heading.match(text) or vocab.note_number.match(text):
                kept.append(text)
                last = top
        notes = _notes_from(kept, vocab)
    if loose and len(loose) > bare and not vocab.type_titles.search(head.title):
        for at, found in reversed(loose):
            tagged[at:at] = found
    rows = tuple(tagged) if tagged else tuple(typed)
    remarks = [row.cells.get(names[c], "") for row in rows for c in remark_cols]
    document, page, sheet = where
    return Schedule(document, page, sheet, head.title or "Schedule (no title found)",
                    tuple(name for _, name in labels), rows, not tagged, tuple(notes),
                    _controls_by(notes, [r for r in remarks if r], vocab), passive=passive)


def _passive(grid: _Grid, head: _Head, labels: list[tuple[int, str]], vocab: Vocabulary,
             equipment: Equipment) -> bool:
    """Whether the schedule under this head lists passive air devices by type (`lists_air_devices`): its title, its
    basis of design and the rows above its header, the short band rows of its key column ("RETURN AND EXHAUST
    GRILLE"), and its description cells."""
    above = [" ".join(grid.text(r, c) for c in range(head.col, head.end_col) if grid.text(r, c))
             for r in range(max(0, head.title_row), head.row)]
    bands = []
    for r in range(head.row + 1, head.end_row):
        text = grid.text(r, head.col)
        if (text and len(text) <= 40 and not vocab.notes_heading.match(text) and not vocab.note_number.match(text)
                and not unit_tags_in_cell(text, equipment)):
            bands.append(text)
    columns = [c for c, name in labels if c != head.col and _DESCRIPTION_HEADER.match(header_key(name))]
    described = [grid.text(r, c) for r in range(head.row + 1, head.end_row) for c in columns]
    return lists_air_devices(head.title, vocab, [head.basis or "", *above, *bands], described)


def _compact(text: str) -> str:
    return re.sub(rf"[\s{_DASH}#.]", "", text).upper()


def _names_a_unit(tag_text: str, vocab: Vocabulary, equipment: Equipment | None = None) -> bool:
    """A tag cell starts with the unit's tag and says little else ("VAV-1 THRU VAV-12", "(E) AHU-3"), or
    lists only tags (five FCUs in one cell); a numbered note or a sentence running through the column is not
    a unit's row."""
    if not tag_text or vocab.note_number.match(tag_text):
        return False
    words = tag_text.split()
    if len(words) <= 4:
        return True
    joiners = {w.upper() for w in vocab.range_words} | {"&", ",", "AND"}
    return equipment is not None and all(w.upper() in joiners or find_tags(w.strip(",;&"), equipment, joined=True)
                                         for w in words)


def _inside(x: float, y: float, box: tuple) -> bool:
    return box[0] <= x <= box[2] and box[1] <= y <= box[3]


def _split(grid: _Grid, words: _Words, vocab: Vocabulary, equipment: Equipment,
           where: tuple[str, int, str | None], other_tables: list[tuple]) -> list[Schedule]:
    heads = _heads(grid, vocab, equipment)
    for head in heads:
        same_column_below = [h.row for h in heads if h.col == head.col and h.row > head.row]
        limit = min(same_column_below, default=grid.n_rows)
        to_the_right = [h.col for h in heads if h.col > head.col and head.row - 3 <= h.row < limit]
        head.end_col = min(to_the_right, default=grid.n_cols)
    for head in heads:
        _title(grid, words, head, vocab)
    for head in heads:
        below = [h.title_row for h in heads if h.col == head.col and h.row > head.row]
        head.end_row = min(below, default=grid.n_rows)
    return [_schedule(grid, words, head, vocab, equipment, where, other_tables) for head in heads]


BY_EYE = "picture, read by eye"


def schedule_from_cells(title: str, headers: Iterable[str], rows: Iterable, notes: Iterable[str],
                        where: tuple[str, int, str | None], vocab: Vocabulary | None = None,
                        equipment: Equipment | None = None, source: str = BY_EYE) -> Schedule:
    """One schedule given cell by cell (a picture of it read by eye): the same Schedule and ScheduleRows the
    table reader makes. A row is a list of cells in the headers' order, or a {header: cell} mapping. The tag
    column is the one headed TAG, UNIT NO., MARK ...; a unit row is read from it as the table reader reads
    it, THRU ranges and unknown prefixes included."""
    vocab = vocab or vocabulary()
    equipment = equipment or Equipment.load()
    names: list[str] = []
    for n, header in enumerate(headers, start=1):
        label, count = _squash(str(header)) or f"COLUMN {n}", 2
        name = label
        while name in names:
            name, count = f"{label} ({count})", count + 1
        names.append(name)
    key = next((n for n in names if header_key(n) in vocab.tag_headers), None)
    by_tag = key is not None
    key = key or next((n for n in names if header_key(n) in vocab.type_headers), names[0] if names else "")
    makers = [n for n in names if _is(n, vocab.manufacturer_headers)]
    models = [n for n in names if _is(n, vocab.model_headers)]
    remark_names = [n for n in names if _is(n, vocab.notes_headers)]
    title = _squash(title) or _NO_TITLE
    kind = kind_from_title(title)
    tagged: list[ScheduleRow] = []
    typed: list[ScheduleRow] = []
    loose: list[tuple[int, list[ScheduleRow]]] = []
    bare = 0
    rows = list(rows)
    described = [n for n in names if n != key and _DESCRIPTION_HEADER.match(header_key(n))]

    def cells_of(raw) -> dict[str, str]:
        values = raw.get("cells", raw) if isinstance(raw, dict) else raw
        if isinstance(values, dict):
            return {name: _squash(str(values.get(name, "") or "")) for name in names}
        return {name: _squash(str(value or "")) for name, value in zip(names, values)}

    all_cells = [cells_of(raw) for raw in rows]
    bands = [c.get(key, "") for c in all_cells if c.get(key) and len(c.get(key, "")) <= 40
             and not unit_tags_in_cell(c.get(key), equipment)]
    passive = lists_air_devices(title, vocab, bands, [c.get(n, "") for c in all_cells for n in described])
    for cells in all_cells:
        tag_text = cells.get(key, "")
        if not any(cells.values()) or not tag_text or vocab.note_number.match(tag_text):
            continue
        tags = expand_tags(tag_text, equipment) if _names_a_unit(tag_text, vocab, equipment) else []
        if tags and not _compact(re.sub(r"^\(E\)\s*", "", tag_text, flags=re.I)).startswith(_compact(tags[0])):
            tags = []
        if passive or (tags and _one_letter_elsewhere(tags[0], tag_text, title, equipment)):
            tags = []
        maker = next((cells[n] for n in makers if cells.get(n)), None)
        model = next((cells[n] for n in models if cells.get(n)), None)
        remarks = " ".join(cells.get(n, "") for n in remark_names)
        existing = bool(vocab.existing.search(tag_text) or vocab.existing.search(remarks))
        found = ([] if tags or passive or not by_tag or not _names_a_unit(tag_text, vocab)
                 else loose_tags(tag_text, equipment))
        if tags:
            tagged += [ScheduleRow(tag, cells, maker, model, existing, shares=len(tags)) for tag in tags]
        elif found:
            loose.append((len(tagged), [ScheduleRow(tag, cells, maker, model, existing, kind, len(found))
                                        for tag in found]))
        if not tags and len(tag_text) <= 12:
            typed.append(ScheduleRow(None, cells, maker, model, existing))
            bare += not found and header_key(tag_text) not in vocab.tag_headers
    if loose and len(loose) > bare and not vocab.type_titles.search(title):
        for at, found in reversed(loose):
            tagged[at:at] = found
    out = tuple(tagged) if tagged else tuple(typed)
    notes = tuple(_squash(str(n)) for n in notes if _squash(str(n)))
    remarks = [row.cells.get(n, "") for row in out for n in remark_names]
    document, page, sheet = where
    return Schedule(document, page, sheet, title, tuple(names), out, not tagged, notes,
                    _controls_by(notes, [r for r in remarks if r], vocab), source=source, passive=passive)


def read_page(page: pymupdf.Page, where: tuple[str, int, str | None],
              vocab: Vocabulary | None = None, equipment: Equipment | None = None) -> list[Schedule]:
    return _read_tables(page, where, vocab, equipment)[0]


def _read_tables(page: pymupdf.Page, where: tuple[str, int, str | None], vocab: Vocabulary | None = None,
                 equipment: Equipment | None = None) -> tuple[list[Schedule], int]:
    """The page's schedules, and how many ruled tables of any size find_tables saw on it."""
    read = _read_page_tables(page, where, vocab, equipment)
    return read.schedules, read.tables


@dataclass
class _PageTables:
    schedules: list[Schedule]
    tables: int                          # ruled tables of any size find_tables saw
    unread: list[tuple[str, ...]]        # per table that names units in its cells but gave no unit row: those tags
    leftover: str                        # the page's text outside every table that gave unit rows, line by line


def _read_page_tables(page: pymupdf.Page, where: tuple[str, int, str | None], vocab: Vocabulary | None = None,
                      equipment: Equipment | None = None) -> _PageTables:
    """The page's schedules; how many tables it has; the tables that list units but could not be read (READ-4:
    a header the reader doesn't know, a table split it can't follow), each with the unit tags in its cells; and
    the page's text outside the tables that were read, for counting what those unread tables list."""
    vocab = vocab or vocabulary()
    equipment = equipment or Equipment.load()
    area = page.rect.width * page.rect.height
    found = page.find_tables().tables
    tables = [t for t in found if t.row_count >= vocab.min_rows and t.col_count >= vocab.min_columns]
    words = _Words(page)
    schedules: list[Schedule] = []
    read_boxes: list[tuple] = []
    unread: list[tuple[str, ...]] = []
    for table in tables:
        grid = _Grid(table)
        x0, y0, x1, y1 = grid.bbox
        border = (x1 - x0) * (y1 - y0) > vocab.border_share * area
        if border and not _heads(grid, vocab):
            continue   # the sheet's border and title block. When a schedule's rules run into the border it is kept
                       # (a header the reading list names; a header only shaped like one never keeps the border)
        others = [tuple(t.bbox) for t in tables if t is not table]
        split = _split(grid, words, vocab, equipment, where, others)
        schedules += split
        if any(row.tag for sch in split for row in sch.rows):
            read_boxes.append(grid.bbox)
        elif not any(sch.passive for sch in split):
            named = _units_in_cells(grid, equipment)
            if named:
                unread.append(named)
    return _PageTables(schedules, len(found), unread, _text_outside(words, read_boxes))


def _units_in_cells(grid: _Grid, equipment: Equipment) -> tuple[str, ...]:
    """The unit tags a table's cells start with, in order (a one-letter prefix only with its dash: "P-1", never
    a type code "B1")."""
    tags: list[str] = []
    for r in range(grid.n_rows):
        for c in range(grid.n_cols):
            text = grid.text(r, c)
            found = unit_tags_in_cell(text, equipment)
            if found and (len(tag_prefix(found[0])) > 1 or re.match(rf"[A-Z]\s*[{_DASH}]", text)):
                tags += found
    return tuple(dict.fromkeys(tags))


def _text_outside(words: _Words, boxes: list[tuple]) -> str:
    """The page's text lines, top to bottom, of the words whose middle is outside every box."""
    lines: dict[tuple[int, int], list[tuple]] = {}
    for w in words.words:
        x, y = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2
        if not any(_inside(x, y, box) for box in boxes):
            lines.setdefault((w[5], w[6]), []).append(w)
    ordered = sorted(lines.values(), key=lambda ws: (min(w[1] for w in ws), min(w[0] for w in ws)))
    return "\n".join(" ".join(w[4] for w in sorted(ws, key=lambda w: w[0])) for ws in ordered)


# --- a schedule sheet whose tables can't be read: its units counted from its text -------------------

_EDGE_JUNK = re.compile(r"^[\s|\[\]_{}!:;.,'`~-]+|[\s|\[\]_{}!:;,'`~-]+$")


def _heading(line: str, vocab: Vocabulary) -> str | None:
    line = " ".join(_EDGE_JUNK.sub("", line.upper()).split())
    return line if len(line) <= 90 and vocab.schedule_heading.match(line) else None


def schedules_from_text(text: str, where: tuple[str, int, str | None], vocab: Vocabulary | None = None,
                        equipment: Equipment | None = None, exclude: Collection[str] = ()) -> list[Schedule]:
    """The units a schedule sheet lists, counted from its text when its tables can't be read (a picture read
    by OCR): every distinct tag that starts a row, under the nearest "… SCHEDULE" heading above it. A tag
    further along a row is a model number or a unit it serves, and a tag written with a space ("AS 100") is
    words, not a unit; neither is counted. A "THRU" range gives one tag per unit. OCR's usual misreadings of
    a tag's digits ("RTU-t", "VAVS-3") are put right."""
    vocab = vocab or vocabulary()
    equipment = equipment or Equipment.load()
    groups: dict[str, list[ScheduleRow]] = {}
    seen: set[str] = set(exclude)
    title = _NO_TITLE
    for raw in clean_text(text).splitlines():
        heading = _heading(raw, vocab)
        if heading:
            title = heading
            continue
        line = raw.upper()
        existing = bool(vocab.existing.search(line))
        cell = _first_cell(line, equipment)
        tags = expand_tags(cell, equipment) if cell else []
        if not tags or not _compact(cell).startswith(_compact(tags[0])):
            continue
        prefix = tag_prefix(tags[0])
        spaced = cell[len(prefix):len(prefix) + 1].isspace() or (len(prefix) == 1 and not re.match(rf"{prefix}[{_DASH}]", cell))
        if spaced and "_" not in tags[0]:      # an underscore-joined tag starts with its location, not its prefix
            continue
        for tag in tags:
            if tag in seen:
                continue
            seen.add(tag)
            groups.setdefault(title, []).append(ScheduleRow(tag, {}, None, None, existing))
    document, page, sheet = where
    return [Schedule(document, page, sheet, title, (), tuple(rows), False, (), (), from_text=True)
            for title, rows in groups.items()]


_MISREAD = str.maketrans({"S": "5", "O": "0", "Q": "0", "I": "1", "L": "1", "T": "1", "|": "1", "!": "1"})


def _first_cell(line: str, equipment: Equipment) -> str:
    """A row's first cell: up to the first column rule or wide gap, at most four words, with OCR's misread
    digits in a tag put right ("RTU-t" → "RTU-1") when what follows a known prefix already has a digit or dash."""
    cell = re.split(r"[|\[\]]|\s{2,}", _EDGE_JUNK.sub("", line), maxsplit=1)[0]
    words = cell.split()[:4]
    if not words:
        return ""
    first = words[0]
    known = sorted((p for p in equipment.prefixes if len(p) >= 2), key=len, reverse=True)
    prefix = next((p for p in known if first.startswith(p)), None)
    if prefix is None and (inner := next((p for p in known if len(p) >= 3 and first[1:].startswith(p)), None)):
        first, prefix = first[1:], inner     # a table's rule read as a letter before the tag ("FRTU-3")
        words[0] = first
    rest = first[len(prefix):] if prefix else ""
    if prefix and rest and re.search(rf"[\d{_DASH}]", rest) and re.fullmatch(rf"[\dSOQILT|!{_DASH}]+", rest):
        words[0] = prefix + rest.translate(_MISREAD)
    return " ".join(words)


def _has_heading(text: str, vocab: Vocabulary) -> bool:
    return any(_heading(line, vocab) for line in text.splitlines())


def _is_schedule_sheet(sheet, text: str, vocab: Vocabulary) -> bool:
    if "Schedules" in sheet.types:
        return True
    return bool(vocab.schedule_text.search(text) and vocab.header_line.search(text))


def _plan_tags(catalogue) -> dict[str, set[str]]:
    """Prefix → the distinct tags of that family on the plan sheets of the trades that carry controls scope."""
    plans = {s.number or f"{s.document.rsplit('/', 1)[-1]} p.{s.page}" for s in catalogue.sheets
             if "Plans" in s.types and s.discipline in CONTROLS_DISCIPLINES}
    found: dict[str, set[str]] = {}
    for entry in catalogue.tags:
        if any(p in plans for p in entry.elsewhere):
            found.setdefault(tag_prefix(entry.tag), set()).add(entry.tag)
    return found


def _thin(found: list[Schedule], plan_tags: dict[str, set[str]]) -> bool:
    """Fewer units on the sheet's schedules than the plans show tags of those families."""
    tags = {row.tag for s in found for row in s.rows if row.tag}
    families = {tag_prefix(tag) for tag in tags}
    return bool(families) and len(tags) < len(set().union(*(plan_tags.get(f, set()) for f in families)))


def _by_eye(sheet, text: str, found: list[Schedule], page_opener, judge, image_dir: Path, plan_tags,
            vocab: Vocabulary, equipment: Equipment, flags: list[str] | None) -> list[Schedule]:
    """A Schedules sheet with pictures and no readable table, or thin schedules: its pictures read by eye (1.1).
    What the eye reads replaces what was counted from the sheet's text, or joins what its tables gave."""
    from estimator.reading.pictures import read_by_eye, render_pictures   # pictures builds on this module

    from_tables = [s for s in found if s.rows and not s.from_text]
    if from_tables and not _thin(from_tables, plan_tags):
        return found
    where = (sheet.document, sheet.page, sheet.number)
    try:
        page = page_opener(sheet.document, sheet.page)
        digest = getattr(page_opener, "digest", None)
        name = digest(sheet.document) if digest else hashlib.sha1(sheet.document.encode()).hexdigest()
        pictures = render_pictures(page, image_dir, f"{name[:16]}-p{sheet.page}")
    except Exception as error:
        if flags is not None:
            flags.append(unreadable_page(sheet.number, sheet.document, sheet.page, "its schedule pictures", error))
        return found
    if not pictures:
        return found
    hint = "; ".join(dict.fromkeys(h for line in text.splitlines() if (h := _heading(line, vocab))))[:400]
    eye, waiting = read_by_eye(judge, pictures, where, hint, vocab, equipment)
    name = sheet.number or f"{sheet.document.rsplit('/', 1)[-1]} page {sheet.page}"
    if flags is not None and waiting:
        flags.append(f"{name}: {waiting} of its {len(pictures)} schedule pictures not read by eye yet "
                     f"({judge.last_error or 'no answer'})" + ("; counted from the sheet's text meanwhile"
                                                               if not from_tables else ""))
    if not eye:
        return found
    if flags is not None:
        flags.append(f"{name}: {len(eye)} schedules read by eye from {len(pictures) - waiting} pictures of the sheet "
                     f"— check the counts")
    return from_tables + eye if from_tables else eye


def read_schedules(catalogue, page_opener: PageOpener, pages: Collection[tuple[str, int]] | None = None,
                   flags: list[str] | None = None, judge=None, image_dir: Path | None = None) -> list[Schedule]:
    """Every schedule on the drawing sheets that can carry controls scope, in page order. With
    `pages`, only those pages are read (the governing ones). A page that can't be read is skipped,
    with a line added to `flags`; the rest of the job is still read. With a `judge` and an `image_dir`, a
    Schedules sheet whose schedules are pictures is read by eye (reading/pictures.py)."""
    vocab = vocabulary()
    equipment = Equipment.load()
    records = {(p.document, p.page): p for p in catalogue.pages}
    sheet_numbers = sheet_number_tags((s.number for s in catalogue.sheets), equipment)
    plan_tags = _plan_tags(catalogue) if judge is not None and image_dir is not None else {}
    schedules: list[Schedule] = []
    for sheet in catalogue.sheets:
        if pages is not None and (sheet.document, sheet.page) not in pages:
            continue
        record = records.get((sheet.document, sheet.page))
        if record is None or record.status not in ("text", "ocr") or sheet.discipline not in CONTROLS_DISCIPLINES:
            continue
        text = clean_text(record.text)
        by_tables = _is_schedule_sheet(sheet, text, vocab)
        # Counted from the text when no table can be read: a schedule sheet, or a mechanical sheet whose
        # schedules are pictures read by OCR. Never a plan read from its text layer, which names every unit on it.
        by_text = "Schedules" in sheet.types or (record.status == "ocr" and sheet.discipline == "Mechanical"
                                                 and _has_heading(text, vocab))
        if not (by_tables or by_text):
            continue
        where = (sheet.document, sheet.page, sheet.number)
        found: list[Schedule] = []
        tables = 0
        unread: list[tuple[str, ...]] = []
        leftover = ""
        if by_tables:
            try:
                page = page_opener(sheet.document, sheet.page)
                read = _read_page_tables(page, where, vocab, equipment)
                found, tables, unread, leftover = read.schedules, read.tables, read.unread, read.leftover
                found = [s for s in found if not vocab.not_schedules.search(s.title)]
            except Exception as error:
                if flags is not None:
                    flags.append(unreadable_page(sheet.number, sheet.document, sheet.page, "schedules", error))
                if record.status != "ocr":
                    continue
        # A sheet read from its text layer is counted from its text only when find_tables saw no table on it
        # at all (a schedule set out without rules); one whose tables were read and weren't schedules isn't.
        if by_text and not any(s.rows for s in found) and (record.status == "ocr" or not tables):
            found = schedules_from_text(text, where, vocab, equipment, sheet_numbers)
        elif unread:
            # READ-4: a table that lists units but couldn't be read is never a silent zero. On a schedule sheet its
            # units are counted from the sheet's text outside the tables that were read (the whole OCR text, less
            # the units already read), flagged; on any other sheet it is flagged to be checked by eye.
            read_tags = {row.tag for s in found for row in s.rows if row.tag}
            counted: set[str] = set()
            if by_text:
                extra = schedules_from_text(leftover if record.status != "ocr" else text, where, vocab, equipment,
                                            set(sheet_numbers) | read_tags)
                found += extra
                counted = {row.tag for s in extra for row in s.rows if row.tag}
            if flags is not None:
                name = sheet.number or f"{sheet.document.rsplit('/', 1)[-1]} page {sheet.page}"
                for tags in unread:
                    missing = [t for t in tags if t not in read_tags]
                    if not missing:
                        continue
                    shown = ", ".join(missing[:6]) + (" …" if len(missing) > 6 else "")
                    how = ("counted from the sheet's text — check the count"
                           if all(t in counted for t in missing) else "check by eye, not all counted")
                    flags.append(f"{name}: a schedule table listing {shown} could not be read from its table "
                                 f"(its tag column wasn't recognised) — {how}")
        if judge is not None and image_dir is not None and "Schedules" in sheet.types:
            found = _by_eye(sheet, text, found, page_opener, judge, image_dir, plan_tags, vocab, equipment, flags)
        schedules += found
    return schedules
