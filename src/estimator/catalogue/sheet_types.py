"""What kind of sheet a drawing is — its discipline and its types — read from its title block.

The rules are the reading list in assets/reading_lists/sheet_types.json (design §9.2: the
reading lists are data). Type comes from the title's words; a sheet can have several.
Discipline comes from the title's words first, then from the sheet number's letters,
because firms use the letters differently.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from estimator.catalogue.register import PageRecord
from estimator.catalogue.title_block import TitleBlock

ASSETS = Path(__file__).resolve().parents[3] / "assets"
SHEET_TYPES = ASSETS / "reading_lists" / "sheet_types.json"
TYPES = ("Schedules", "Plans", "Details", "Air riser", "Water riser", "Network riser", "Control diagrams", "Diagrams",
         "Sections and elevations", "Demolition", "Specifications", "Notes and legends")
_LETTERS = re.compile(r"^([A-Z]{1,3})")


@dataclass(frozen=True)
class Sheet:
    document: str
    page: int
    number: str | None
    title: str | None
    discipline: str
    types: tuple[str, ...]
    title_source: str | None = None     # "title block", "drawing index" or "beside the sheet number"


@dataclass(frozen=True)
class SheetTypes:
    types: tuple[tuple[str, tuple[re.Pattern, ...]], ...]
    by_title: tuple[tuple[str, tuple[re.Pattern, ...]], ...]
    by_letters: dict[str, str]

    @classmethod
    def load(cls, path: Path = SHEET_TYPES) -> "SheetTypes":
        data = json.loads(Path(path).read_text(encoding="utf-8"))

        def rules(key):
            return tuple((e["name"], tuple(re.compile(p, re.I) for p in e["patterns"])) for e in data[key])

        return cls(rules("types"), rules("disciplines_by_title"), data["disciplines_by_letters"])


def types_of(title: str | None, reading: SheetTypes) -> tuple[str, ...]:
    if not title:
        return ()
    return tuple(name for name, patterns in reading.types if any(p.search(title) for p in patterns))


def discipline_of(number: str | None, title: str | None, reading: SheetTypes) -> str:
    if title:
        for name, patterns in reading.by_title:
            if any(p.search(title) for p in patterns):
                return name
    letters = _LETTERS.match(number or "")
    if letters:
        code = letters.group(1)
        for length in range(len(code), 0, -1):
            if code[:length] in reading.by_letters:
                return reading.by_letters[code[:length]]
    return "Unknown"


def classify_sheet(record: PageRecord, block: TitleBlock, reading: SheetTypes | None = None) -> Sheet:
    reading = reading or SheetTypes.load()
    return Sheet(record.document, record.page, block.number, block.title,
                 discipline_of(block.number, block.title, reading), types_of(block.title, reading),
                 block.source if block.title else None)
