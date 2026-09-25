"""The equipment schedules on the drawing sheets, read table by table (build step 4, design §9.3).

A schedule lists one row per unit, so a unit's quantity is its tag: the schedule has no QTY
column. `page.find_tables()` finds each ruled table; one table can hold several schedules,
stacked or side by side, so a table is split at every header cell that names the tag column
(UNIT No., TAG, MARK, DESIGNATION). The words, patterns and limits live in
`assets/reading_lists/schedules.json`.
"""
from __future__ import annotations

import bisect
import json
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pymupdf

from estimator.catalogue.job import CONTROLS_DISCIPLINES
from estimator.catalogue.pdf import clean_text
from estimator.catalogue.tags import Equipment, find_tags

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
        tuple((a, b) for a, b in data["pairs"]),
    )


def _squash(text: str | None) -> str:
    return " ".join(clean_text(text or "").split())


def header_key(text: str | None) -> str:
    """A header cell as compared with the reading list: spaces squashed, capitals, no trailing stop."""
    return _squash(text).upper().rstrip(".:").strip()


def _is(header: str, words: Iterable[str]) -> bool:
    key = header_key(header)
    return any(key == w or key.startswith(w + " ") for w in words)


# --- tags, with THRU ranges and comma lists expanded ------------------------------------------

_SPLIT = re.compile(r"^(.*?)(\d+)$")


def _one_tag(text: str, equipment: Equipment) -> str | None:
    found = find_tags(text, equipment)
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
    found += [(m.start(), tag) for m in by_code.finditer(rest) for tag in find_tags(m.group(0), equipment)[:1]]
    found += [(m.start(), tag) for m in by_name.finditer(rest) for tag in find_tags(m.group(0), equipment)[:1]]
    return [tag for _, tag in sorted(found, key=lambda f: f[0])]


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


def _heads(grid: _Grid, vocab: Vocabulary) -> list[_Head]:
    heads = []
    for r in range(grid.n_rows - 1):
        row = [header_key(grid.text(r, c)) for c in range(grid.n_cols)]
        tagged = [c for c, key in enumerate(row) if key in vocab.tag_headers]
        heads += [_Head(r, c, "tag") for c in tagged]
        if not tagged:
            first = next((c for c, key in enumerate(row) if key), None)
            if first is not None and row[first] in vocab.type_headers:
                heads.append(_Head(r, first, "type"))
    return heads


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
    note_lines: list[str] = []
    in_notes = False
    # The tag column is as wide as its header cell. Its words are read by position, row band by
    # row band, so a tag split across two grid columns, or a cell merged over several rows, is
    # read once and whole.
    head_rect = grid.rect(head.row, head.col) or grid.bbox
    tag_x0, tag_x1 = head_rect[0], head_rect[2]
    after = next((grid.rect(head.row, c) for c, _ in labels if c > head.col and grid.rect(head.row, c)), None)
    wide_x1 = after[2] if after else tag_x1
    for r in range(head.row + 1, head.end_row):
        top, bottom = grid.bands[r]
        tag_text = words.starting_in((tag_x0, top, tag_x1, bottom))
        key_text = grid.text(r, head.col) or tag_text
        if not in_notes and vocab.notes_heading.match(key_text) and not expand_tags(key_text, equipment):
            in_notes = True
        if in_notes:
            note_lines.append(" ".join(grid.text(r, c) for c in range(head.col, head.end_col) if grid.text(r, c)))
            continue
        tags = expand_tags(tag_text, equipment)
        if not tags and wide_x1 > tag_x1:
            joined = words.starting_in((tag_x0, top, wide_x1, bottom))
            tags = expand_tags(joined, equipment)
            tag_text = joined if tags else tag_text
        tag_text = tag_text or key_text
        cells = {name: grid.text(r, c) for c, name in labels}
        cells[key_name] = tag_text
        maker = next((grid.text(r, c) for c in maker_cols if grid.text(r, c)), None) or head.basis
        model = next((grid.text(r, c) for c in model_cols if grid.text(r, c)), None)
        remarks = " ".join(grid.text(r, c) for c in remark_cols)
        existing = bool(vocab.existing.search(tag_text) or vocab.existing.search(remarks))
        if tags:
            tagged += [ScheduleRow(tag, cells, maker, model, existing) for tag in tags]
        elif tag_text and len(tag_text) <= 12 and not vocab.note_number.match(tag_text):
            typed.append(ScheduleRow(None, cells, maker, model, existing))
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
    rows = tuple(tagged) if tagged else tuple(typed)
    remarks = [row.cells.get(names[c], "") for row in rows for c in remark_cols]
    document, page, sheet = where
    return Schedule(document, page, sheet, head.title or "Schedule (no title found)",
                    tuple(name for _, name in labels), rows, not tagged, tuple(notes),
                    _controls_by(notes, [r for r in remarks if r], vocab))


def _inside(x: float, y: float, box: tuple) -> bool:
    return box[0] <= x <= box[2] and box[1] <= y <= box[3]


def _split(grid: _Grid, words: _Words, vocab: Vocabulary, equipment: Equipment,
           where: tuple[str, int, str | None], other_tables: list[tuple]) -> list[Schedule]:
    heads = _heads(grid, vocab)
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


def read_page(page: pymupdf.Page, where: tuple[str, int, str | None],
              vocab: Vocabulary | None = None, equipment: Equipment | None = None) -> list[Schedule]:
    vocab = vocab or vocabulary()
    equipment = equipment or Equipment.load()
    area = page.rect.width * page.rect.height
    tables = [t for t in page.find_tables().tables
              if t.row_count >= vocab.min_rows and t.col_count >= vocab.min_columns]
    words = _Words(page)
    schedules: list[Schedule] = []
    for table in tables:
        grid = _Grid(table)
        x0, y0, x1, y1 = grid.bbox
        if (x1 - x0) * (y1 - y0) > vocab.border_share * area and not _heads(grid, vocab):
            continue   # the sheet's border and title block. When a schedule's rules run into the border it is kept.
        others = [tuple(t.bbox) for t in tables if t is not table]
        schedules += _split(grid, words, vocab, equipment, where, others)
    return schedules


def _is_schedule_sheet(sheet, text: str, vocab: Vocabulary) -> bool:
    if "Schedules" in sheet.types:
        return True
    return bool(vocab.schedule_text.search(text) and vocab.header_line.search(text))


def read_schedules(catalogue, page_opener: PageOpener) -> list[Schedule]:
    """Every schedule on the drawing sheets that can carry controls scope, in page order."""
    vocab = vocabulary()
    equipment = Equipment.load()
    records = {(p.document, p.page): p for p in catalogue.pages}
    schedules: list[Schedule] = []
    for sheet in catalogue.sheets:
        record = records.get((sheet.document, sheet.page))
        if record is None or record.status != "text" or sheet.discipline not in CONTROLS_DISCIPLINES:
            continue
        if not _is_schedule_sheet(sheet, clean_text(record.text), vocab):
            continue
        page = page_opener(sheet.document, sheet.page)
        schedules += read_page(page, (sheet.document, sheet.page, sheet.number), vocab, equipment)
    return schedules
