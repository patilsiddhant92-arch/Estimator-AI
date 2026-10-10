"""The equipment schedules on the drawing sheets, read table by table (build step 4, design §9.3).

A schedule lists one row per unit, so a unit's quantity is its tag: the schedule has no QTY
column. `page.find_tables()` finds each ruled table; one table can hold several schedules,
stacked or side by side, so a table is split at every header cell that names the tag column
(UNIT No., TAG, MARK, DESIGNATION; also UNIT, PUMP NO. or a blank header over a column of unit tags).
A schedule of air devices (diffusers, grilles, louvers) lists types: its codes are never units. The
words, patterns and limits live in `assets/reading_lists/schedules.json`.
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
    passive: bool = False      # lists passive air devices by type (diffusers, grilles, louvers: `lists_air_devices`):
                               # its codes (B1, SD-1, CD) are never units, families or controls systems, whatever the prefix


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
    tag_header_pattern: re.Pattern | None = None     # a key header the exact list misses ("UNIT", "PUMP NO.")
    bare_tag_header: re.Pattern | None = None        # the keys that may head a column past the first (UNIT, TAG)
    description_headers: tuple[str, ...] = ()        # a column that says what each row is (DESCRIPTION, TYPE)
    air_devices: re.Pattern | None = None            # words naming passive air devices (diffusers, grilles ...)
    not_air_devices: re.Pattern | None = None        # title words that say the schedule lists other equipment too
    notes_beside: float = 0.0                        # how far right of a table its notes are looked for
    notes_beside_above: float = 0.0                  # how far above a table's top a note beside it may start


def _any(patterns: Iterable[str]) -> re.Pattern:
    return re.compile("|".join(f"(?:{p})" for p in patterns), re.I)


@lru_cache
def vocabulary(path: Path = SCHEDULES) -> Vocabulary:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    header_words = "|".join(r"\s+".join(re.escape(w) for w in h.split()) for h in data["tag_headers"])
    shaped = data.get("tag_header_pattern")
    if shaped:
        # A line that is only a key-shaped header makes a sheet a schedule sheet too, but never a bare NO. or one
        # that starts like a title block's ("SHEET NO.").
        skip = "|".join(re.escape(w) for w in data.get("not_header_lines", ()))
        header_words += rf"|(?!(?:NO|NUMBER)\s*[.:]?\s*$)" + (rf"(?!(?:{skip})\b)" if skip else "") + rf"(?:{shaped})"
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
        tag_header_pattern=re.compile(shaped, re.I) if shaped else None,
        bare_tag_header=re.compile(data["bare_tag_header_pattern"], re.I) if data.get("bare_tag_header_pattern") else None,
        description_headers=tuple(data.get("description_headers", ())),
        air_devices=_any(data["air_device_words"]) if data.get("air_device_words") else None,
        not_air_devices=_any(data["air_device_exceptions"]) if data.get("air_device_exceptions") else None,
        notes_beside=float(data.get("notes_beside", 0)), notes_beside_above=float(data.get("notes_beside_above", 0)),
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


def _unit_tags(text: str | None, vocab: Vocabulary, equipment: Equipment, loose: bool = True) -> list[str]:
    """The unit tags a cell is made of ("EF-1", "(E) AHU-3", "VAV-1 THRU VAV-5", and with `loose` a tag whose
    prefix the equipment list lacks, "TXF-B"); empty when it is a type code, a note, or a line that only
    mentions a unit."""
    text = _squash(text)
    if not text or not _names_a_unit(text, vocab, equipment):
        return []
    tags = expand_tags(text, equipment)
    if tags and _compact(re.sub(r"^\(E\)\s*", "", text, flags=re.I)).startswith(_compact(tags[0])):
        return tags
    return loose_tags(text, equipment) if loose else []


def _is_unit_cell(text: str, tags: list[str]) -> bool:
    """A cell of unit tags in a column read for its key: a one-letter prefix written without its dash ("B1") is a
    type code there, never a unit."""
    return bool(tags) and (len(tag_prefix(tags[0])) > 1 or bool(re.match(rf"\s*(?:\(E\)\s*)?[A-Z]\s*[{_DASH}]", text, re.I)))


def _units_in(cells: Iterable[str], vocab: Vocabulary, equipment: Equipment) -> tuple[int, int]:
    """(cells naming a unit, cells with text) in a column below its header, a notes line left out. A column that
    names one unit in two rows is no key column (an ASSOCIATED CONDENSING UNIT column names the same outdoor unit
    on several indoor units' rows): (0, cells with text) then."""
    units = filled = 0
    seen: set[str] = set()
    for text in cells:
        if not text or vocab.notes_heading.match(text) or vocab.note_number.match(text):
            continue
        filled += 1
        tags = _unit_tags(text, vocab, equipment)
        if tags and seen & set(tags):
            return 0, filled
        seen |= set(tags)
        units += _is_unit_cell(text, tags)
    return units, filled


def _units_below(grid: _Grid, r: int, c: int, vocab: Vocabulary, equipment: Equipment) -> tuple[int, int]:
    return _units_in((grid.text(row, c) for row in range(r + 1, grid.n_rows)), vocab, equipment)


def _key_shaped(key: str, first: bool, vocab: Vocabulary) -> bool:
    """A header the exact list misses that is shaped like a key ("UNIT", "AC UNIT NO.", "PUMP NO."): never a
    quantity or a type header; past the first column only a bare key (UNIT, TAG, MARK), because a column of
    ASSOCIATED CONDENSING UNIT names another unit, not the row's."""
    if (vocab.tag_header_pattern is None or not key or key in vocab.tag_headers or key in vocab.quantity_headers
            or key in vocab.type_headers or not vocab.tag_header_pattern.fullmatch(key)):
        return False
    return first or bool(vocab.bare_tag_header and vocab.bare_tag_header.fullmatch(key))


def _shaped_keys(grid: _Grid, r: int, row: list[str], vocab: Vocabulary, equipment: Equipment) -> list[int]:
    """The columns of header row r with a key-shaped header over a column that is mostly unit tags (HP 4)."""
    first = next((c for c, key in enumerate(row) if key), None)
    found = []
    for c, key in enumerate(row):
        if _key_shaped(key, c == first, vocab):
            units, filled = _units_below(grid, r, c, vocab, equipment)
            if units and units * 2 >= filled:
                found.append(c)
    return found


def _blank_head(grid: _Grid, vocab: Vocabulary, equipment: Equipment) -> list[_Head]:
    """The key column of a table with no key header at all, when its key header is blank (HP 4): the first column
    with any text, if its cells are mostly unit tags. Its header row is the first row above the first tag that
    has a blank cell there and labels in two columns or more."""
    for c in range(grid.n_cols):
        rows = [r for r in range(grid.n_rows) if grid.text(r, c)]
        if not rows:
            continue
        first_tag = next((r for r in rows if _unit_tags(grid.text(r, c), vocab, equipment)), None)
        if first_tag is None:
            return []
        header = next((r for r in range(first_tag) if not grid.text(r, c)
                       and sum(bool(grid.text(r, k)) for k in range(grid.n_cols)) >= 2), None)
        if header is None:
            return []
        units, filled = _units_below(grid, header, c, vocab, equipment)
        return [_Head(header, c, "tag")] if units and units * 2 >= filled else []
    return []


def _heads(grid: _Grid, vocab: Vocabulary, equipment: Equipment | None = None) -> list[_Head]:
    """The schedules' key cells: a header the reading list names (TAG, UNIT NO., MARK ...). With the equipment list
    also one shaped like a key ("UNIT", "AC UNIT NO.", "PUMP NO.") over a column of unit tags and, in a table with
    no key header at all, a blank header over a column of unit tags (HP 4, HP 21)."""
    heads = []
    for r in range(grid.n_rows - 1):
        row = [header_key(grid.text(r, c)) for c in range(grid.n_cols)]
        tagged = [c for c, key in enumerate(row) if key in vocab.tag_headers]
        if equipment is not None:
            tagged = sorted({*tagged, *_shaped_keys(grid, r, row, vocab, equipment)})
        heads += [_Head(r, c, "tag") for c in tagged]
        if not tagged:
            first = next((c for c, key in enumerate(row) if key), None)
            if first is not None and row[first] in vocab.type_headers:
                heads.append(_Head(r, first, "type"))
    if heads or equipment is None:
        return heads
    return _blank_head(grid, vocab, equipment)


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
        for pattern in vocab.basis:
            m = pattern.search(text)
            if m:
                head.basis = head.basis or m.group(1).strip() or None
                text = text[:m.start()].strip()
                break
        head.title_row = r
        if text:
            head.title = text
            return
    if not blocked and head.row <= 3:
        box = grid.row_box(head.row, head.col, head.end_col) or grid.bbox
        above = words.lines(box[0] - 2, grid.bbox[1] - 40, box[2], grid.bbox[1] + 1)
        above = [line for line in above if line[0] + line[1] <= grid.bbox[1] + 2]
        if above:
            head.title = above[-1][3]


def _labels(grid: _Grid, head: _Head) -> list[tuple[int, str]]:
    labels, seen = [], set()
    for c in range(head.col, head.end_col):
        label = grid.text(head.row, c)
        if not label and c == head.col:
            label = f"COLUMN {c + 1}"     # a key column with a blank header still leads the columns (HP 4)
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
    # A key header merged into a band above it has no cell of its own: the column's first cell below gives its width.
    head_rect = (grid.rect(head.row, head.col)
                 or next((grid.rect(r, head.col) for r in range(head.row + 1, grid.n_rows) if grid.rect(r, head.col)), None)
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
        if passive:
            tags = []   # an air device's type code (B1, SD-1, CD), whatever its prefix: never a unit (HP 3, HP 20)
        if not tags and not passive and tag_text and wide_x1 > tag_x1 and _names_a_unit(tag_text, vocab):
            # A tag split over two columns ("VAV" | "-503"): kept only when it starts in the tag column,
            # never a tag named in the next column ("ST-1S" | "AHU-1 SUPPLY").
            joined = words.starting_in((tag_x0, top, wide_x1, bottom))
            found = expand_tags(joined, equipment)
            if found and _compact(found[0]).startswith(_compact(tag_text.split()[0])):
                tags, tag_text = found, joined
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
    if not notes:
        bottom = head.end_row == grid.n_rows
        if bottom:
            box = grid.row_box(head.row, head.col, head.end_col) or grid.bbox
            below = words.lines(box[0] - 5, grid.bbox[3] - 1, box[2], grid.bbox[3] + vocab.notes_below)
            notes = _notes_from(_kept_lines(below, other_tables, vocab), vocab)
        if head.end_col == grid.n_cols:        # the schedule on the table's right edge: notes may stand beside it
            beside = _beside(grid, words, head, vocab, other_tables, bottom)
            notes += _notes_from(_kept_lines(beside, other_tables, vocab, from_the_start=True), vocab)
    if loose and len(loose) > bare and not vocab.type_titles.search(head.title) and not passive:
        for at, found in reversed(loose):
            tagged[at:at] = found
    rows = tuple(tagged) if tagged else tuple(typed)
    remarks = [row.cells.get(names[c], "") for row in rows for c in remark_cols]
    document, page, sheet = where
    return Schedule(document, page, sheet, head.title or "Schedule (no title found)",
                    tuple(name for _, name in labels), rows, not tagged, tuple(notes),
                    _controls_by(notes, [r for r in remarks if r], vocab), passive=passive)


_FIRST_NOTE = re.compile(r"^\s*(?:\(?0?1[.)]|\*)")


def _kept_lines(lines: list[tuple[float, float, float, str]], other_tables: list[tuple], vocab: Vocabulary,
                from_the_start: bool = False) -> list[str]:
    """The notes block among text lines (top, height, left, text), top to bottom: from the first line that is a
    NOTES heading or a numbered note to the first wide gap. A line inside another table is that table's. With
    `from_the_start` a block begins only at a heading or at note 1: a later number beside a table is more likely
    the tail of a block that began beside another."""
    lines = [line for line in lines if not any(_inside(line[2] + 1, line[0] + line[1] / 2, t) for t in other_tables)]
    kept, last = [], None
    for top, height, _, text in lines:
        if last is not None and top - last > 3 * max(height, 1):
            break
        starts = vocab.notes_heading.match(text) or (_FIRST_NOTE if from_the_start else vocab.note_number).match(text)
        if kept or starts:
            kept.append(text)
            last = top
    return kept


def _beside(grid: _Grid, words: _Words, head: _Head, vocab: Vocabulary, other_tables: list[tuple],
            bottom: bool) -> list[tuple[float, float, float, str]]:
    """The text lines to the right of a schedule on the table's right edge, where notes may stand beside it (HP 46):
    from just above the schedule's title to the foot of its rows, and on past the table's bottom edge for the
    schedule at the bottom (a notes block can be longer than the table). The area stops at the next table to the
    right and at `notes_beside` points."""
    if vocab.notes_beside <= 0:
        return []
    top = grid.bands[head.title_row if 0 <= head.title_row < head.row else head.row][0] - vocab.notes_beside_above
    foot = grid.bands[head.end_row - 1][1] if head.end_row > head.row else grid.bbox[3]
    if bottom:
        foot = max(foot, grid.bbox[3]) + vocab.notes_below
    left = grid.bbox[2]
    limit = min([left + vocab.notes_beside, *(t[0] for t in other_tables if t[0] >= left - 1 and t[1] < foot and t[3] > top)])
    return words.lines(left, top, limit, foot)


# --- a schedule of passive air devices: its codes are types, never units (HP 3, HP 20) ------------------------

def lists_air_devices(title: str, vocab: Vocabulary, also: Iterable[str] = (), described: Iterable[str] = ()) -> bool:
    """A schedule of passive air devices by type (diffusers, grilles, registers, louvers, air outlets, silencers): its
    title, or one of the lines `also` gives (the lines between its title and its header, a band row of its key
    column such as "RETURN AND EXHAUST GRILLES"), names air devices, or most of its description cells (`described`)
    do. A title that also names equipment a controller serves (a damper, a fan, a unit) never does. Its codes (B1,
    SD-1, CD, LRD-A) are types, never units: B is a boiler's prefix and SD a smoke damper's."""
    pattern = vocab.air_devices
    if pattern is None or (vocab.not_air_devices is not None and vocab.not_air_devices.search(title or "")):
        return False
    if pattern.search(title or "") or any(pattern.search(line or "") for line in also):
        return True
    described = [d for d in described if d]
    return bool(described) and sum(bool(pattern.search(d)) for d in described) * 2 > len(described)


def _air_bands(keys: Iterable[str], vocab: Vocabulary, equipment: Equipment) -> list[str]:
    """The key cells that head a group of air devices ("RETURN AND EXHAUST GRILLES"): short text that names air
    devices and is no unit tag and no note, with another row after it. A line of text under the last row is a
    note, never a band."""
    keys = list(keys)
    last = max((i for i, text in enumerate(keys) if text), default=-1)
    return [text for i, text in enumerate(keys)
            if text and i < last and len(text) <= 40 and vocab.air_devices and vocab.air_devices.search(text)
            and not vocab.notes_heading.match(text) and not vocab.note_number.match(text)
            and not _unit_tags(text, vocab, equipment)]


def _passive(grid: _Grid, head: _Head, labels: list[tuple[int, str]], vocab: Vocabulary, equipment: Equipment) -> bool:
    """Whether the schedule under this head lists passive air devices by type (`lists_air_devices`): its title, its
    basis of design and the lines above its header, the band rows of its key column, and its description cells."""
    above = [" ".join(grid.text(r, c) for c in range(head.col, head.end_col) if grid.text(r, c))
             for r in range(max(0, head.title_row), head.row)]
    keys = [grid.text(r, head.col) for r in range(head.row + 1, head.end_row)]
    columns = [c for c, name in labels if c != head.col and _is(name, vocab.description_headers)]
    described = [grid.text(r, c) for r in range(head.row + 1, head.end_row) for c in columns]
    return lists_air_devices(head.title, vocab, [head.basis or "", *above, *_air_bands(keys, vocab, equipment)], described)


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
    all_cells: list[dict[str, str]] = []
    for raw in rows:
        values = raw.get("cells", raw) if isinstance(raw, dict) else raw
        if isinstance(values, dict):
            all_cells.append({name: _squash(str(values.get(name, "") or "")) for name in names})
        else:
            all_cells.append({name: _squash(str(value or "")) for name, value in zip(names, values)})
    key = next((n for n in names if header_key(n) in vocab.tag_headers), None)
    if key is None:         # a key-shaped header ("UNIT", "PUMP NO.") over a column of unit tags (HP 4)
        for position, name in enumerate(names):
            if _key_shaped(header_key(name), position == 0, vocab):
                units, filled = _units_in((c.get(name, "") for c in all_cells), vocab, equipment)
                if units and units * 2 >= filled:
                    key = name
                    break
    by_tag = key is not None
    key = key or next((n for n in names if header_key(n) in vocab.type_headers), names[0] if names else "")
    makers = [n for n in names if _is(n, vocab.manufacturer_headers)]
    models = [n for n in names if _is(n, vocab.model_headers)]
    remark_names = [n for n in names if _is(n, vocab.notes_headers)]
    title = _squash(title) or _NO_TITLE
    kind = kind_from_title(title)
    described = [c.get(n, "") for c in all_cells for n in names if n != key and _is(n, vocab.description_headers)]
    passive = lists_air_devices(title, vocab, _air_bands([c.get(key, "") for c in all_cells], vocab, equipment), described)
    tagged: list[ScheduleRow] = []
    typed: list[ScheduleRow] = []
    loose: list[tuple[int, list[ScheduleRow]]] = []
    bare = 0
    for cells in all_cells:
        tag_text = cells.get(key, "")
        if not any(cells.values()) or not tag_text or vocab.note_number.match(tag_text):
            continue
        tags = expand_tags(tag_text, equipment) if _names_a_unit(tag_text, vocab, equipment) else []
        if tags and not _compact(re.sub(r"^\(E\)\s*", "", tag_text, flags=re.I)).startswith(_compact(tags[0])):
            tags = []
        if passive:
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


@dataclass(frozen=True)
class _Unread:
    tags: tuple[str, ...]      # the unit tags the table's cells are made of
    lines: tuple[str, ...]     # its text, a row to a line ("AC-1 | OFFICE | 4000"), the lines above it first


@dataclass(frozen=True)
class _PageTables:
    schedules: list[Schedule]
    tables: int                # ruled tables of any size find_tables saw
    unread: list[_Unread]      # tables that name units in their cells but gave no row: no key column was found


def _read_page_tables(page: pymupdf.Page, where: tuple[str, int, str | None], vocab: Vocabulary | None = None,
                      equipment: Equipment | None = None) -> _PageTables:
    """The page's schedules, how many tables find_tables saw, and the tables that list units but gave no row at
    all (HP 4: a key header the reader does not know), so a table is never a silent zero."""
    vocab = vocab or vocabulary()
    equipment = equipment or Equipment.load()
    area = page.rect.width * page.rect.height
    found = page.find_tables().tables
    tables = [t for t in found if t.row_count >= vocab.min_rows and t.col_count >= vocab.min_columns]
    words = _Words(page)
    schedules: list[Schedule] = []
    unread: list[_Unread] = []
    for table in tables:
        grid = _Grid(table)
        x0, y0, x1, y1 = grid.bbox
        if (x1 - x0) * (y1 - y0) > vocab.border_share * area and not _heads(grid, vocab):
            # the sheet's border and title block. When a schedule's rules run into the border it is kept, by a header
            # the reading list names: a header only shaped like a key never keeps the border.
            continue
        others = [tuple(t.bbox) for t in tables if t is not table]
        split = _split(grid, words, vocab, equipment, where, others)
        schedules += split
        if not any(s.rows or s.passive for s in split) and (tags := _units_in_cells(grid, vocab, equipment)):
            lines = _table_lines(grid, words)
            if not any(vocab.not_schedules.search(line) for line in lines):
                unread.append(_Unread(tags, lines))
    return _PageTables(schedules, len(found), unread)


def _units_in_cells(grid: _Grid, vocab: Vocabulary, equipment: Equipment) -> tuple[str, ...]:
    """The unit tags a table's cells are made of, in reading order. A prefix the equipment list lacks is no unit
    here, and a one-letter prefix only with its dash ("P-1", never the type code "B1")."""
    tags: list[str] = []
    for r in range(grid.n_rows):
        for c in range(grid.n_cols):
            text = grid.text(r, c)
            found = _unit_tags(text, vocab, equipment, loose=False)
            if _is_unit_cell(text, found):
                tags += found
    return tuple(dict.fromkeys(tags))


def _table_lines(grid: _Grid, words: _Words) -> tuple[str, ...]:
    """A table's text a row to a line, cells joined by " | ", as OCR gives a table: the text lines just above the
    table (its title) first."""
    x0, y0, x1, _ = grid.bbox
    above = [text for top, height, _, text in words.lines(x0 - 2, y0 - 40, x1, y0 + 1) if top + height <= y0 + 2]
    rows = [" | ".join(cell for cell in row if cell) for row in grid.texts]
    return tuple(above + [row for row in rows if row])


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
    a tag's digits ("RTU-t", "VAVS-3") are put right. Under a heading that names air devices ("AIR OUTLET
    SCHEDULE") nothing is counted: those codes (B1, SD-1) are types."""
    vocab = vocab or vocabulary()
    equipment = equipment or Equipment.load()
    groups: dict[str, list[ScheduleRow]] = {}
    seen: set[str] = set(exclude)
    title = _NO_TITLE
    passive = False
    for raw in clean_text(text).splitlines():
        heading = _heading(raw, vocab)
        if heading:
            title = heading
            passive = lists_air_devices(title, vocab)    # a diffuser schedule: its codes (B1, SD-1) are no units
            continue
        if passive:
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


def _sheet_name(sheet) -> str:
    return sheet.number or f"{sheet.document.rsplit('/', 1)[-1]} page {sheet.page}"


def _passive_flags(found: list[Schedule], sheet, vocab: Vocabulary) -> list[str]:
    """A schedule set aside as a list of air devices by something other than its title (its description cells, a band
    row, a line under its title) is said, so a list wrongly set aside is seen: its codes are given no unit."""
    lines = []
    for schedule in found:
        if schedule.passive and not (vocab.air_devices and vocab.air_devices.search(schedule.title)):
            key = schedule.headers[0] if schedule.headers else ""
            codes = list(dict.fromkeys(row.cells[key] for row in schedule.rows if row.cells.get(key)))
            shown = ", ".join(codes[:6]) + (" …" if len(codes) > 6 else "")
            lines.append(f"{_sheet_name(sheet)}: {schedule.title} lists air devices by type ({shown}): read as passive "
                         f"devices, never as units; check")
    return lines


_BLANK_KEY = re.compile(r"COLUMN \d+")      # the name `_labels` gives a key column with no header text


def _blank_key_flags(found: list[Schedule], sheet) -> list[str]:
    """A schedule whose unit column has no header is read by its cells alone: said, so it is looked at."""
    return [f"{_sheet_name(sheet)}: {schedule.title} has no header over its unit column; its first column is read as "
            f"the unit tags — check"
            for schedule in found if schedule.headers and _BLANK_KEY.fullmatch(schedule.headers[0])
            and schedule.source == "table" and any(row.tag for row in schedule.rows)]


def _unread_tables(sheet, found: list[Schedule], unread: list[_Unread], by_text: bool, vocab: Vocabulary,
                   equipment: Equipment, sheet_numbers: Collection[str], flags: list[str] | None) -> list[Schedule]:
    """The units of the tables that name units but gave no row (HP 4: no key column was found). On a schedule sheet
    they are counted from the table's own text, as a sheet's text is counted when its tables cannot be read, so the
    sheet is pictured for a look; on any other sheet a plan names units for other reasons and nothing is counted.
    Either way a flag names the units: a table is never a silent zero."""
    where = (sheet.document, sheet.page, sheet.number)
    read = {row.tag for s in found for row in s.rows if row.tag}
    extra: list[Schedule] = []
    for item in unread:
        missing = [tag for tag in item.tags if tag not in read]
        if not missing:
            continue
        counted: set[str] = set()
        if by_text:
            more = schedules_from_text("\n".join(item.lines), where, vocab, equipment, set(sheet_numbers) | read)
            extra += more
            counted = {row.tag for s in more for row in s.rows if row.tag}
            read |= counted
        if flags is not None:
            shown = ", ".join(missing[:6]) + (" …" if len(missing) > 6 else "")
            how = ("counted from its text — check the count" if all(tag in counted for tag in missing)
                   else "check it by eye, not all of it counted" if counted else "check it by eye, none of it counted")
            flags.append(f"{_sheet_name(sheet)}: a schedule table listing {shown} could not be read as a schedule "
                         f"(its tag column was not recognised) — {how}")
    return extra


def read_schedules(catalogue, page_opener: PageOpener, pages: Collection[tuple[str, int]] | None = None,
                   flags: list[str] | None = None, judge=None, image_dir: Path | None = None) -> list[Schedule]:
    """Every schedule on the drawing sheets that can carry controls scope, in page order. With
    `pages`, only those pages are read (the governing ones). A page that can't be read is skipped,
    with a line added to `flags`; the rest of the job is still read. With a `judge` and an `image_dir`, a
    Schedules sheet whose schedules are pictures is read by eye (reading/pictures.py). A table that names
    units but has no key column the reader knows is counted from its text on a schedule sheet, and flagged
    on any sheet; a schedule set aside as a list of air devices by its cells, not its title, is flagged too."""
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
        unread: list[_Unread] = []
        if by_tables:
            try:
                page = page_opener(sheet.document, sheet.page)
                read = _read_page_tables(page, where, vocab, equipment)
                found, tables, unread = read.schedules, read.tables, read.unread
                found = [s for s in found if not vocab.not_schedules.search(s.title)]
            except Exception as error:
                if flags is not None:
                    flags.append(unreadable_page(sheet.number, sheet.document, sheet.page, "schedules", error))
                if record.status != "ocr":
                    continue
        if flags is not None:
            flags += _passive_flags(found, sheet, vocab) + _blank_key_flags(found, sheet)
        # A sheet read from its text layer is counted from its text only when find_tables saw no table on it
        # at all (a schedule set out without rules); one whose tables were read and weren't schedules isn't.
        if by_text and not any(s.rows for s in found) and (record.status == "ocr" or not tables):
            found = schedules_from_text(text, where, vocab, equipment, sheet_numbers)
        elif unread:
            found = found + _unread_tables(sheet, found, unread, by_text, vocab, equipment, sheet_numbers, flags)
        if judge is not None and image_dir is not None and "Schedules" in sheet.types:
            found = _by_eye(sheet, text, found, page_opener, judge, image_dir, plan_tags, vocab, equipment, flags)
        schedules += found
    return schedules
