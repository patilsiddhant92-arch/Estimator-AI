"""Equipment tags — the codes that name each unit (AHU-1, VAV-21-01, EF-3) — in every
spelling, and every place each one appears (design §9.3)."""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
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
        return _compiled_patterns(tuple(sorted(self.prefixes)), tuple(sorted(self.names)))

    def located(self) -> re.Pattern:
        return _located_pattern(tuple(sorted(self.prefixes)))


@lru_cache
def _compiled_patterns(prefixes: tuple[str, ...], names: tuple[str, ...]) -> tuple[re.Pattern, re.Pattern]:
    codes = "|".join(re.escape(p) for p in sorted(prefixes, key=len, reverse=True))
    decimal = r"(?:\.\d{1,2})?"     # a size or type written with a decimal: AC-3.0, HRU-4.0, AC-ATS-1.1
    rest = rf"\d[A-Z0-9]*(?:[{_DASH}][A-Z0-9]+)*{decimal}"
    # One or two words between the prefix and the number: AC-EMR-1, ACCU-LOBBY-2, AC-ATS-1.1.
    word_rest = rf"(?:[A-Z]{{2,8}}[{_DASH}]){{1,2}}\d[A-Z0-9]*(?:[{_DASH}]\d[A-Z0-9]*)*{decimal}"
    letter_rest = rf"[A-Z]{{1,2}}\d*(?:[{_DASH}][A-Z0-9]+)*"
    space = r"[^\S\r\n]"             # a line break only in a tag bubble (below): "648 SF" over room "01" is not SF-01
    sep = rf"(?:\s*(?:[{_DASH}#]|No\.?)\s*|{space})"
    by_code = re.compile(rf"(?<![A-Za-z0-9_])({codes})(?:{sep}?({rest})|[{_DASH}]({word_rest})|[{_DASH}]({letter_rest}))"
                         rf"(?![A-Za-z0-9])")
    names_pat = "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
    by_name = re.compile(rf"(?<![A-Za-z])({names_pat})\s*(?:No\.?|#)\s*(\d[A-Z0-9]*)(?![A-Za-z0-9])", re.I)
    return by_code, by_name


@lru_cache
def _bubble_pattern(prefixes: tuple[str, ...]) -> re.Pattern:
    """A tag drawn in a bubble: the prefix alone on one line, its number alone on the next ("CU" over "1")."""
    codes = "|".join(re.escape(p) for p in sorted(prefixes, key=len, reverse=True))
    rest = rf"\d[A-Z0-9]*(?:[{_DASH}][A-Z0-9]+)*(?:\.\d{{1,2}})?"
    return re.compile(rf"(?m)^[^\S\r\n]*({codes})[^\S\r\n]*\r?\n[^\S\r\n]*({rest})[^\S\r\n]*$")


_RANGE_WORDS = "THRU|THROUGH"   # as in schedules.json's range_words


@lru_cache
def _located_pattern(prefixes: tuple[str, ...]) -> re.Pattern:
    """A tag of two to five segments joined by underscores — a site code, a floor or area, sometimes a room
    or zone, then the unit: HEL03_04_FCU01, HEL03_04_NDH_CRAH01. Only the last segment names the kind; a
    "THRU" range after it ("… THRU TWAS03", "… THRU 03") is read with it."""
    codes = "|".join(re.escape(p) for p in sorted(prefixes, key=len, reverse=True))
    location = r"(?:[A-Z0-9]{1,10}_){1,4}"
    unit = rf"({codes})[{_DASH}]?(\d+)([A-Z]?)"
    high = rf"(?:({location})?({codes})[{_DASH}]?)?(\d+)"
    return re.compile(rf"(?<![A-Za-z0-9_{_DASH}.])({location}){unit}(?![A-Za-z0-9_])"
                      rf"(?:\s*(?:{_RANGE_WORDS})\s*{high}(?![A-Za-z0-9_]))?")


def located_tags(text: str, equipment: Equipment) -> list[tuple[int, int, list[str]]]:
    """(start, end, tags) for each underscore-joined tag in the text, a THRU range giving one tag per unit; the
    short end of a range takes the long end's location."""
    found = []
    done = 0
    for m in equipment.located().finditer(text):
        if m.start() < done:
            continue
        location, prefix, digits, letter = m.group(1), m.group(2), m.group(3), m.group(4)
        first = f"{location}{prefix}{digits}{letter}"
        high = m.group(7)
        same = m.group(5) in (None, location) and m.group(6) in (None, prefix)
        width = len(digits) if digits.startswith("0") else 0
        if high is None or letter or not same or not 0 < int(high) - int(digits) <= 200:
            end, tags = m.end(4), [first]
        else:
            end = m.end()
            tags = [f"{location}{prefix}{str(n).zfill(width)}" for n in range(int(digits), int(high) + 1)]
        # More of the same unit listed after it, written short: "… CRAC01, CRAC02", "… CRAC01 & 02".
        more = re.compile(rf"(?:\s*(?:[,&/]|AND\b)?\s*{re.escape(prefix)}[{_DASH}]?|\s*[,&]\s*)(\d+[A-Z]?)"
                          rf"(?![A-Za-z0-9_{_DASH}])")
        while (n := more.match(text, end)) is not None:
            tags.append(f"{location}{prefix}{n.group(1)}")
            end = n.end()
        found.append((m.start(), end, tags))
        done = end
    return found


def tag_prefix(tag: str) -> str:
    """The prefix that says what a tag is: "AHU" for AHU-1, "CRAH" for HEL03_04_NDH_CRAH01 (its last segment)."""
    if "_" in tag:
        m = re.match(r"[A-Z]+", tag.rsplit("_", 1)[1])
        if m:
            return m.group(0)
    return tag.split("-", 1)[0]


def tag_location(tag: str) -> str | None:
    """The location segments of an underscore-joined tag ("HEL03_04" for HEL03_04_FCU01); None for AHU-1."""
    if "_" not in tag:
        return None
    location, unit = tag.rsplit("_", 1)
    return location if re.match(r"[A-Z]", unit) else None


def _canonical(prefix: str, rest: str) -> str:
    return f"{prefix}-{re.sub(f'[{_DASH}]', '-', rest)}"


SERIES = 3   # a tag written with no dash (VAV07, CDU020) counts in free text only in a series this long


def find_tags(text: str, equipment: Equipment, exclude: frozenset[str] = frozenset(), joined: bool = False) -> list[str]:
    """Every tag in the text, in order. A tag written with no dash or space ("VAV07") could be part of a model
    number: it counts when `joined` (the text is a schedule's tag cell) or when the text holds a series of
    SERIES or more with its prefix written that way."""
    by_code, by_name = equipment.patterns()
    found: list[tuple[int, str]] = []
    located = located_tags(text, equipment)
    if located:
        found += [(start, tag) for start, _, tags in located for tag in tags]
        text = "".join(" " if any(a <= i < b for a, b, _ in located) else ch for i, ch in enumerate(text))
    run_together: list[tuple[int, str, str]] = []
    for m in by_code.finditer(text):
        if m.group(3) and m.group(1) in equipment.schedule_only:
            continue          # SS-WVA-6: a model number, not a split system named by a word
        tag = _canonical(m.group(1), m.group(2) or m.group(3) or m.group(4))
        if m.group(2) and text[m.end(1)].isdigit():
            run_together.append((m.start(), m.group(1), tag))
        else:
            found.append((m.start(), tag))
    series = Counter(prefix for _, prefix, _ in run_together)
    found += [(at, tag) for at, prefix, tag in run_together if joined or series[prefix] >= SERIES]
    found += [(m.start(), _canonical(equipment.names[m.group(1).upper()], m.group(2))) for m in by_name.finditer(text)]
    if "\n" in text:
        found += [(m.start(1), _canonical(m.group(1), m.group(2)))
                  for m in _bubble_pattern(tuple(sorted(equipment.prefixes))).finditer(text)]
    return [tag for _, tag in sorted(found) if tag not in exclude]


def sheet_number_tags(numbers: Iterable[str | None], equipment: Equipment) -> frozenset[str]:
    """What the job's own sheet numbers would read as, with and without their decimals ("P-101.00" and
    "P-101"), so neither spelling of a sheet number in the text is taken for a unit."""
    tags = {tag for number in numbers if number for tag in find_tags(number, equipment)}
    return frozenset(tags | {re.sub(r"\.\d+$", "", tag) for tag in tags})


@dataclass(frozen=True)
class TagEntry:
    tag: str
    kind: str                       # what it is, from the reading list: "Air Handling Unit"
    on_schedules: tuple[str, ...]   # the schedule sheets it appears on
    elsewhere: tuple[str, ...]      # every other sheet or spec page it appears on
    times: int                      # how many times it appears in all
    location: str | None = None     # an underscore-joined tag's site, floor or area segments: "HEL03_04"


def _place(record: PageRecord, sheet: Sheet | None) -> str:
    if sheet is not None and sheet.number:
        return sheet.number
    return f"{record.document.rsplit('/', 1)[-1]} p.{record.page}"


def _natural(tag: str) -> list:
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", tag)]


def index_tags(pages: Sequence[PageRecord], sheets: Mapping[tuple[str, int], Sheet],
               equipment: Equipment | None = None) -> list[TagEntry]:
    equipment = equipment or Equipment.load()
    exclude = sheet_number_tags((s.number for s in sheets.values()), equipment)
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
        prefix = tag_prefix(tag)
        if prefix in equipment.schedule_only and not on_schedules[tag]:
            continue
        entries.append(TagEntry(tag, equipment.prefixes[prefix], tuple(on_schedules[tag]), tuple(elsewhere[tag]),
                                times[tag], tag_location(tag)))
    return entries


def unlisted_prefixes(texts: Iterable[str], equipment: Equipment) -> Counter:
    counts: Counter = Counter()
    for text in texts:
        counts.update(m.group(1) for m in _TAG_SHAPED.finditer(text) if m.group(1) not in equipment.prefixes)
    return counts
