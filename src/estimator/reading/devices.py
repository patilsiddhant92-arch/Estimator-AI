"""The devices marked on the plans, the job's legend, and typical floors (design §9.4).

A device on a plan is a short text label next to a drawn symbol — T, OCC, CO2, SP. The
labels and what they mean are the reading list in assets/reading_lists/devices.json. A
label is counted where it stands as a whole word, exact-case, in the page's own text:
the estimator's markup annotations are never in it. Words in the title-block strip (the
right and bottom fifth of the sheet as viewed) are left out, and a legend sheet is not
counted at all — its labels explain the symbols, they aren't devices. Only the sheets of the
disciplines that carry controls scope are counted: an architectural or electrical plan's T or
OCC is that trade's own.

A typical plan stands for several floors. Its title names the range ("10TH-16TH ... TYPICAL"),
and each label on it counts once per floor in that range. A set often repeats such a sheet
on one page per floor with identical text; that is still one sheet, counted once.
"""
from __future__ import annotations

import json
import re
from bisect import bisect_left, bisect_right
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pymupdf

from estimator.catalogue.job import CONTROLS_DISCIPLINES
from estimator.catalogue.pdf import clean_text
from estimator.catalogue.register import EDGE
from estimator.catalogue.sheet_types import SHEET_TYPES

ASSETS = Path(__file__).resolve().parents[3] / "assets"
DEVICES = ASSETS / "reading_lists" / "devices.json"
ROW_BAND = 0.6          # a legend's meaning sits within this share of the code's height, above or below its middle
RUN_GAP = 1.0           # a gap wider than the word's height ends a run of text
MAX_CODE = 5            # characters: a legend code is short
_CODE_SHAPE = re.compile(r"^(?=.*[A-Z])[A-Z0-9/\-]+$")
_PUNCTUATION = "()[]{},;:\"'"

PageOpener = Callable[[str, int], pymupdf.Page]


@dataclass(frozen=True)
class LegendEntry:
    code: str
    meaning: str
    sheet: str | None


@dataclass(frozen=True)
class DeviceCount:
    sheet: str | None
    document: str
    page: int
    device: str            # "Occupancy sensor"
    label: str             # "OCC"
    count: int             # words on the sheet, outside its title block and legend area
    floors: int            # typical-floor multiplier (1 when not typical)
    total: int             # count * floors
    in_legend: bool        # the job's legend defines this label


@dataclass(frozen=True)
class TypicalSheet:
    sheet: str | None
    title: str
    floors: tuple[str, ...]   # e.g. ("10", "11", ..., "16")
    note: str                 # "Typical plan M-110.00 → floors 10–16: 7 floors. Check the floor list."


@dataclass(frozen=True)
class DeviceList:
    labels: dict[str, str]
    legend_decides: frozenset[str]
    plan_type: str
    legend_type: str
    legend_title: tuple[re.Pattern, ...]
    typical_words: tuple[re.Pattern, ...]
    floor_range: re.Pattern
    unlucky_floor: int

    @classmethod
    def load(cls, path: Path = DEVICES, sheet_types: Path = SHEET_TYPES) -> "DeviceList":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        known = {t["name"] for t in json.loads(Path(sheet_types).read_text(encoding="utf-8"))["types"]}
        for key in ("plan_type", "legend_type"):
            if data[key] not in known:
                raise ValueError(f"devices.json names the sheet type '{data[key]}', which sheet_types.json doesn't have")
        return cls(dict(data["labels"]), frozenset(data["legend_decides"]), data["plan_type"], data["legend_type"],
                   tuple(re.compile(p, re.I) for p in data["legend_title_words"]),
                   tuple(re.compile(p, re.I) for p in data["typical_words"]),
                   re.compile(data["floor_range"], re.I), int(data["unlucky_floor"]))


@lru_cache
def _default_list() -> DeviceList:
    return DeviceList.load()


@dataclass(frozen=True)
class _Word:
    text: str
    x0: float        # points, on the sheet as viewed
    y0: float
    x1: float
    y1: float
    edge: bool       # in the title-block strip

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def middle(self) -> float:
        return (self.y0 + self.y1) / 2


def _words(page: pymupdf.Page) -> list[_Word]:
    """Every word on the page, placed as the sheet is viewed (a drawing is often stored rotated)."""
    width, height = page.rect.width, page.rect.height
    matrix = page.rotation_matrix
    words = []
    for x0, y0, x1, y1, text, *_ in page.get_text("words"):
        box = pymupdf.Rect(x0, y0, x1, y1) * matrix
        edge = box.x0 / width >= EDGE or box.y0 / height >= EDGE
        # Some exports use a control character as the space between words; split on it too.
        parts = [p.strip(_PUNCTUATION) for p in clean_text(text).split()]
        words += [_Word(p, box.x0, box.y0, box.x1, box.y1, edge) for p in parts if p]
    return words


def _is_plan(sheet, reading: DeviceList) -> bool:
    return reading.plan_type in sheet.types


def _is_legend(sheet, reading: DeviceList) -> bool:
    return reading.legend_type in sheet.types and any(p.search(sheet.title or "") for p in reading.legend_title)


# ---- the legend -------------------------------------------------------------------------------

def _runs(words: list[_Word], gap: float) -> list[list[_Word]]:
    runs: list[list[_Word]] = []
    for word in sorted(words, key=lambda w: w.x0):
        if runs and word.x0 - runs[-1][-1].x1 <= gap:
            runs[-1].append(word)
        else:
            runs.append([word])
    return runs


def _code_like(text: str) -> bool:
    return len(text) <= MAX_CODE and bool(_CODE_SHAPE.match(text))


def _legend_entries(words: list[_Word], sheet: str | None, reading: DeviceList) -> list[LegendEntry]:
    """Pair each short code with the longest text run to its right in the same row band. A code starts
    its run; a code that isn't a known device label stands alone, or it is just the first word of a
    sentence. The search to the right stops at the next code, which starts the legend's next column."""
    entries: list[LegendEntry] = []
    by_middle = sorted(words, key=lambda w: w.middle)
    middles = [w.middle for w in by_middle]
    for word in words:
        if not _code_like(word.text):
            continue
        reach = ROW_BAND * word.height
        band = [w for w in by_middle[bisect_left(middles, word.middle - reach):bisect_right(middles, word.middle + reach)]
                if w is not word]
        gap = RUN_GAP * word.height
        if any(w.x1 <= word.x0 + 0.1 and word.x0 - w.x1 <= gap for w in band):
            continue                                  # a word just to its left: it's inside a line of text
        runs = _runs([word] + [w for w in band if w.x0 >= word.x1 - 0.1], gap)
        own, *rest = runs
        if len(own) > 1 and word.text not in reading.labels:
            continue                                  # "ALL WORK SHALL ..." — a sentence, not a code
        candidates = [own[1:]] if len(own) > 1 else []
        for run in rest:
            head = run[0].text
            if _code_like(head) and (len(run) == 1 or head in reading.labels):
                if candidates:
                    break                             # the next column's code
            candidates.append(run)
            if len(own) > 1:
                break                                 # the meaning shares the code's run; one more run at most
        candidates = [c for c in candidates if any(sum(ch.isalpha() for ch in w.text) >= 2 for w in c)]
        if candidates:
            meaning = " ".join(w.text for w in max(candidates, key=lambda c: len(" ".join(w.text for w in c))))
            entries.append(LegendEntry(word.text, meaning, sheet))
    return entries


def read_legend(catalogue, page_opener: PageOpener, reading: DeviceList | None = None) -> list[LegendEntry]:
    """Every code a legend sheet explains (a notes-and-legends sheet with LEGEND or SYMBOL in its title)."""
    reading = reading or _default_list()
    found: dict[tuple[str, str, str | None], LegendEntry] = {}
    for sheet in catalogue.sheets:
        if not _is_legend(sheet, reading):
            continue
        # The whole sheet is read, title-block strip included: a legend often runs down into it.
        words = _words(page_opener(sheet.document, sheet.page))
        for entry in _legend_entries(words, sheet.number, reading):
            found.setdefault((entry.code, entry.meaning, entry.sheet), entry)
    return list(found.values())


# ---- typical floors ---------------------------------------------------------------------------

def _pages_of(catalogue) -> dict[tuple[str, int], str]:
    return {(p.document, p.page): p.text for p in catalogue.pages}


def typical_sheets(catalogue, reading: DeviceList | None = None) -> list[TypicalSheet]:
    """Plans whose title names a floor range and says TYPICAL. A sheet repeated on several pages
    (one per floor) is one typical sheet; its floor range, not its page count, is the multiplier."""
    reading = reading or _default_list()
    pages_by_number: dict[str | None, list] = defaultdict(list)
    first: dict[str | None, object] = {}
    for sheet in catalogue.sheets:
        title = sheet.title or ""
        if not _is_plan(sheet, reading) or not any(p.search(title) for p in reading.typical_words):
            continue
        match = reading.floor_range.search(title)
        if not match:
            continue
        key = sheet.number or f"{sheet.document} p.{sheet.page}"
        pages_by_number[key].append(sheet)
        first.setdefault(key, sheet)
    typicals = []
    for key, sheet in first.items():
        low, high = sorted(int(n) for n in reading.floor_range.search(sheet.title).groups())
        floors = tuple(str(n) for n in range(low, high + 1))
        name = sheet.number or f"on {sheet.document.rsplit('/', 1)[-1]} page {sheet.page}"
        note = f"Typical plan {name} → floors {low}–{high}: {len(floors)} floors."
        repeated = len(pages_by_number[key])
        if repeated > 1 and repeated != len(floors):
            note += (f" The sheet is on {repeated} pages in the set, not {len(floors)} — counted once and "
                     f"multiplied by the {len(floors)} floors.")
        note += (f" Floor {reading.unlucky_floor} may not exist — check the floor list."
                 if low <= reading.unlucky_floor <= high else " Check the floor list.")
        typicals.append(TypicalSheet(sheet.number, sheet.title, floors, note))
    return typicals


# ---- counting ---------------------------------------------------------------------------------

def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def count_devices(catalogue, page_opener: PageOpener, legend: Sequence[LegendEntry],
                  typicals: Sequence[TypicalSheet], reading: DeviceList | None = None
                  ) -> tuple[list[DeviceCount], list[str]]:
    """Each device label on each plan sheet, with its typical-floor multiplier, and the flags: a label
    the job's legend doesn't define, or no labels on any plan at all."""
    reading = reading or _default_list()
    meanings: dict[str, str] = {}
    for entry in legend:
        meanings.setdefault(entry.code, entry.meaning)
    floors_of = {(t.sheet, t.title): len(t.floors) for t in typicals}
    texts = _pages_of(catalogue)
    seen: set[tuple[str, str | None, str]] = set()
    counts: list[DeviceCount] = []
    searched = 0
    for sheet in catalogue.sheets:
        if not _is_plan(sheet, reading) or _is_legend(sheet, reading):
            continue
        if sheet.discipline not in CONTROLS_DISCIPLINES:
            continue    # an architectural or electrical plan's labels are its own trade's, not controls devices
        if sheet.number:
            # The same sheet on several pages of one document with identical text (a typical plan
            # printed once per floor) is one sheet.
            copy = (sheet.document, sheet.number, texts.get((sheet.document, sheet.page), ""))
            if copy in seen:
                continue
            seen.add(copy)
        searched += 1
        tally: dict[str, int] = defaultdict(int)
        for word in _words(page_opener(sheet.document, sheet.page)):
            if not word.edge and word.text in reading.labels:
                tally[word.text] += 1
        floors = floors_of.get((sheet.number, sheet.title), 1)
        for label in sorted(tally, key=lambda l: (-tally[l], l)):
            device = reading.labels[label]
            if label in reading.legend_decides and label in meanings:
                device = meanings[label].capitalize()
            counts.append(DeviceCount(sheet.number, sheet.document, sheet.page, device, label, tally[label],
                                      floors, tally[label] * floors, label in meanings))
    flags: list[str] = []
    if legend:
        missing: dict[str, list[str]] = defaultdict(list)
        for count in counts:
            if not count.in_legend:
                where = count.sheet or f"{count.document.rsplit('/', 1)[-1]} page {count.page}"
                if where not in missing[count.label]:
                    missing[count.label].append(where)
        flags += [f"'{label}' counted on {', '.join(where)} but not in the job's legend — check what it means"
                  for label, where in missing.items()]
    if not counts:
        flags.append(f"No device labels found on the plan sheets ({_plural(searched, 'sheet')} searched) — "
                     "device quantities will come from the sequence and point list")
    return counts, flags
