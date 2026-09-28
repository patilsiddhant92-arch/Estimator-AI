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
# A number with a building/phase prefix segment ("H3T-M-611", "HEL03-M-101"): the discipline letters
# are read from the segment after the prefix, not the prefix itself.
_PREFIXED_LETTERS = re.compile(r"^(?=[A-Z0-9]{1,6}-)[A-Z0-9]*[A-Z][A-Z0-9]*-([A-Z]{1,3})(?=[-\s.]?\d)")

# A document's file name marks a single discipline when one of these tokens is set off by
# "-", "_", space or ".": "M" / "MECH" / "MECHANICAL" and the like.
_FILENAME_DISCIPLINES = {
    "M": "Mechanical", "MECH": "Mechanical", "MECHANICAL": "Mechanical",
    "P": "Plumbing", "PLUMB": "Plumbing", "PLUMBING": "Plumbing",
    "E": "Electrical", "ELEC": "Electrical", "ELECTRICAL": "Electrical",
    "C": "Civil", "CIVIL": "Civil",
    "A": "Architectural", "ARCH": "Architectural",
    "FP": "Fire protection",
}
_FILENAME_TOKEN = re.compile(r"[-_ .]")


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
    prefixed = _PREFIXED_LETTERS.match(number or "")
    letters = prefixed or _LETTERS.match(number or "")
    if letters:
        code = letters.group(1)
        for length in range(len(code), 0, -1):
            if code[:length] in reading.by_letters:
                return reading.by_letters[code[:length]]
    return "Unknown"


def discipline_from_filename(name: str) -> str | None:
    """The single discipline a document's file name marks, when exactly one of its
    "-"/"_"/space/"."-separated tokens names one (design §9.2's document fallback)."""
    tokens = [t.upper() for t in _FILENAME_TOKEN.split(Path(name).stem) if t]
    found = {_FILENAME_DISCIPLINES[t] for t in tokens if t in _FILENAME_DISCIPLINES}
    return next(iter(found)) if len(found) == 1 else None


def classify_sheet(record: PageRecord, block: TitleBlock, reading: SheetTypes | None = None) -> Sheet:
    reading = reading or SheetTypes.load()
    return Sheet(record.document, record.page, block.number, block.title,
                 discipline_of(block.number, block.title, reading), types_of(block.title, reading),
                 block.source if block.title else None)
