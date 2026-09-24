"""Equipment tags — the codes that name each unit (AHU-1, VAV-21-01, EF-3) — in every
spelling, and every place each one appears (design §9.3)."""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from estimator.catalogue.register import PageRecord
from estimator.catalogue.sheet_types import Sheet

ASSETS = Path(__file__).resolve().parents[3] / "assets"
EQUIPMENT = ASSETS / "reading_lists" / "equipment.json"
_DASH = "-‐‑–—"
_TAG_SHAPED = re.compile(rf"(?<![A-Za-z0-9])([A-Z]{{2,5}})[{_DASH}]\d")


@dataclass(frozen=True)
class Equipment:
    prefixes: dict[str, str]
    names: dict[str, str]
    schedule_only: frozenset[str]

    @classmethod
    def load(cls, path: Path = EQUIPMENT) -> "Equipment":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(data["prefixes"], data["names"], frozenset(data["schedule_only"]))

    def patterns(self) -> tuple[re.Pattern, re.Pattern]:
        codes = "|".join(re.escape(p) for p in sorted(self.prefixes, key=len, reverse=True))
        rest = rf"\d[A-Z0-9]*(?:[{_DASH}][A-Z0-9]+)*"
        letter_rest = rf"[A-Z]{{1,2}}\d*(?:[{_DASH}][A-Z0-9]+)*"
        sep = rf"(?:\s*(?:[{_DASH}#]|No\.?)\s*|\s)"
        by_code = re.compile(rf"(?<![A-Za-z0-9])({codes})(?:{sep}?({rest})|[{_DASH}]({letter_rest}))(?![A-Za-z0-9])")
        names = "|".join(re.escape(n) for n in sorted(self.names, key=len, reverse=True))
        by_name = re.compile(rf"(?<![A-Za-z])({names})\s*(?:No\.?|#)\s*(\d[A-Z0-9]*)(?![A-Za-z0-9])", re.I)
        return by_code, by_name


def _canonical(prefix: str, rest: str) -> str:
    return f"{prefix}-{re.sub(f'[{_DASH}]', '-', rest)}"


def find_tags(text: str, equipment: Equipment, exclude: frozenset[str] = frozenset()) -> list[str]:
    by_code, by_name = equipment.patterns()
    found = [(m.start(), _canonical(m.group(1), m.group(2) or m.group(3))) for m in by_code.finditer(text)]
    found += [(m.start(), _canonical(equipment.names[m.group(1).upper()], m.group(2))) for m in by_name.finditer(text)]
    return [tag for _, tag in sorted(found) if tag not in exclude]


@dataclass(frozen=True)
class TagEntry:
    tag: str
    kind: str                       # what it is, from the reading list: "Air Handling Unit"
    on_schedules: tuple[str, ...]   # the schedule sheets it appears on
    elsewhere: tuple[str, ...]      # every other sheet or spec page it appears on
    times: int                      # how many times it appears in all


def _place(record: PageRecord, sheet: Sheet | None) -> str:
    if sheet is not None and sheet.number:
        return sheet.number
    return f"{record.document.rsplit('/', 1)[-1]} p.{record.page}"


def _natural(tag: str) -> list:
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", tag)]


def index_tags(pages: Sequence[PageRecord], sheets: Mapping[tuple[str, int], Sheet],
               equipment: Equipment | None = None) -> list[TagEntry]:
    equipment = equipment or Equipment.load()
    exclude = frozenset(_canonical(*n.split("-", 1)) if "-" in n else n
                        for n in (s.number for s in sheets.values() if s.number))
    on_schedules: dict[str, list[str]] = defaultdict(list)
    elsewhere: dict[str, list[str]] = defaultdict(list)
    times: Counter = Counter()
    for record in pages:
        sheet = sheets.get((record.document, record.page))
        place = _place(record, sheet)
        is_schedule = sheet is not None and "Schedules" in sheet.types
        for tag in find_tags(record.text, equipment, exclude):
            times[tag] += 1
            bucket = on_schedules if is_schedule else elsewhere
            if place not in bucket[tag]:
                bucket[tag].append(place)
    entries = []
    for tag in sorted(times, key=_natural):
        prefix = tag.split("-", 1)[0]
        if prefix in equipment.schedule_only and not on_schedules[tag]:
            continue
        entries.append(TagEntry(tag, equipment.prefixes[prefix], tuple(on_schedules[tag]), tuple(elsewhere[tag]), times[tag]))
    return entries


def unlisted_prefixes(texts: Iterable[str], equipment: Equipment) -> Counter:
    counts: Counter = Counter()
    for text in texts:
        counts.update(m.group(1) for m in _TAG_SHAPED.finditer(text) if m.group(1) not in equipment.prefixes)
    return counts
