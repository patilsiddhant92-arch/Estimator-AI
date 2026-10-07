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


# ---- the one label reader (FINAL-K, REVIEW-FINAL6 F7; FINAL-N, REVIEW-FINAL7 F4 and F6) -------------------------
# A tag is placed on a plan where a line of the sheet's text starts with it ("GCF-A", "EF-1 (TYP)", "VAV-3 450 CFM",
# "AHU-1 SUPPLY", "(VAV-3)", a bubble "VAV" over "5-7", "VAV-" over "3"), whatever words follow, unless the line is
# a long note; a tag named after a word ("TO EUH-1", "SEE AHU-1") places nothing there. On a counted plan sheet a
# unit's tag named anywhere is placed at least once (`plan_labels`). Every rule here can only raise a count (lead
# ruling: an undercount is the worst failure). The inventory's placements and the dossier's counts line both read
# labels so, and the copy test (`document_repeats`) too.

DECIMAL_TYPE = re.compile(r"^[A-Z]+-\d+\.\d+$")    # AC-3.0, HRU-4.0: a size, not a unit number
_TYPE_FORM = re.compile(r"-[A-Z]{1,2}$", re.I)     # CUH-A, EBB-B: a type's tag, no unit number in it
_LABEL_NOISE = re.compile(r"^\((?:N|NEW)\)\s*|\s*\(?\s*TYP(?:ICAL)?\.?\s*\)?$", re.I)
_DIGIT_BREAK = re.compile(r"(?<=\d)[\s\-‐‑–—]+(?=\d)")   # the break between two digit groups: "VAV-1-11", "VAV 1 - 11"
_BUBBLE_HEAD = re.compile(r"\s*[A-Z]{1,6}\s*")
# beside tags on one line, what is no word of a note: a symbol's letter (T, S), a number (450), (E), TYP, AND.
_LABEL_FILLER = re.compile(r"\W*(?:[A-Z0-9]|\d+|TYP(?:ICAL)?|NEW|EXIST(?:ING)?|AND)\W*", re.I)
_LABEL_SPLIT = re.compile(r"[\s,;/&+]+")          # "FCU-4 / FCU-5", "FCU-4&FCU-5", "VAV-1, VAV-2": joiners, no words
_BRACKETS = "()[]{}<>"
_RANGE_WORD = frozenset({"THRU", "THROUGH"})
RANGE_SPAN = 200                                   # the most units a "VAV-1 THRU VAV-n" range reads (`located_tags`)
# a word that makes the tag after it a reference, not a label: "AHU-1 SUPPLY TO VAV-3", "VAV-3 SERVED BY AHU-1"
_REFERENCE_WORDS = frozenset({"TO", "FROM", "SEE", "PER", "BY", "SERVING", "SERVES", "SERVED", "FEEDS", "FEED",
                              "FEEDING", "CONNECT", "CONNECTS", "CONNECTED", "VIA", "FOR", "OF", "WITH", "AS",
                              "REFER", "SIMILAR", "SAME"})
NOTE_WORDS = 12                                    # a line with more words than this is a note, never a label line
_SPLIT_TAG = re.compile(rf"[{_DASH}][^\S\r\n]*\r?\n[^\S\r\n]*")   # a tag split over two lines: "VAV-" over "3"
_NUMBERED = re.compile(r"^(.*?)(\d+)$")
_COUNT_BEFORE = re.compile(r"^\d+\s*[-xX×*]\s*(?=[A-Z])")
# a count stated after a tag, the line's only other words (FINAL-O, REVIEW-FINAL8 H3, ruled: a stated multiplier is a
# placement count): "CUH-A (TYP. OF 4)", "CUH-A TYP OF 4", "CUH-A x4", "CUH-A (4)", "CUH-A 4 PLACES"
STATED_MOST = 50                                   # the most places a stated count reads; more is one place, said
_HEAD_AND_REST = re.compile(r"^\s*(\S+)\s+(.*?\S)\s*$")
_STATED = (re.compile(r"^TYP(?:ICAL)?\.?\s*OF\s+(?P<n>[^\s()]+)\.?$", re.I),
           re.compile(r"^[X×]\s*(?P<n>\d+)$", re.I),
           re.compile(r"^(?P<n>\d+)\s*(?:PLACES|PLCS?|LOCATIONS)\.?$", re.I))
_STATED_IN_BRACKETS = re.compile(r"^(?P<n>\d+)$")


def is_type_tag(tag: str) -> bool:
    """A tag that names a kind used at many places, not one unit: a letter suffix with no unit number (EBB-A,
    CUH-A) or a decimal size (AC-3.0). Every other tag (VAV-101, EF-3, ACCU-109) names one unit."""
    return bool(_TYPE_FORM.search(tag) or DECIMAL_TYPE.match(tag.upper()))


def label_key(text: str) -> str:
    """A label's spelling-free key: "VAV-1", "VAV 1", "(N) VAV-1" and "VAV-1 TYP." are all VAV1. The break between two
    digit groups stays (VAV-1-11 is VAV1-11, VAV-11-1 is VAV11-1), so two different tags never share a key."""
    t = _DIGIT_BREAK.sub("|", _LABEL_NOISE.sub("", text.strip()))      # "|" stands for the kept break
    return re.sub(r"[\s\-‐‑–—#]", "", t).replace("|", "-").upper()


def label_keys(tags: Iterable[str]) -> dict[str, str]:
    """Each tag's label key -> the tag (the first tag of a key wins); a type sized "X.0" is also labelled "X"."""
    keys: dict[str, str] = {}
    tags = list(tags)
    for tag in tags:
        keys.setdefault(label_key(tag), tag)
    for tag in tags:
        if tag.endswith(".0"):
            keys.setdefault(label_key(tag[:-2]), tag)
    return keys


def _bare(token: str) -> str:
    """A token without the brackets round it and a trailing full stop or colon: "(VAV-3)", "[VAV-3]", "VAV-3."."""
    previous = None
    while token != previous:
        previous, token = token, token.strip(_BRACKETS).rstrip(".:;")
    return token


def _key_tag(text: str, keys: Mapping[str, str]) -> str | None:
    key = label_key(text)
    return keys.get(key) if key else None


def _token_tag(token: str, keys: Mapping[str, str]) -> str | None:
    bare = _bare(token)
    counted = _COUNT_BEFORE.sub("", bare)        # "2-VAV-3", "2xVAV-3": the tag after a count
    return _key_tag(token, keys) or _key_tag(bare, keys) or (_key_tag(counted, keys) if counted != bare else None)


def _range_members(low: str, high: str, keys: Mapping[str, str]) -> list[str]:
    """The tags a "VAV-1 THRU VAV-5" (or "VAV-1 THRU 5") range names between its ends, each in `keys`; with a bare
    number for its high end, that end too. None when the ends are not one numbered series, or the span is over
    RANGE_SPAN."""
    a = _NUMBERED.match(low)
    b = _NUMBERED.match(high if not high.isdigit() else f"{a.group(1) if a else ''}{high}")
    if a is None or b is None or label_key(a.group(1)) != label_key(b.group(1)):
        return []
    first, last = int(a.group(2)), int(b.group(2))
    if not 0 < last - first <= RANGE_SPAN:
        return []
    width = len(a.group(2)) if a.group(2).startswith("0") else 0
    numbers = list(range(first + 1, last)) + ([last] if high.isdigit() else [])
    found = (_key_tag(f"{a.group(1)}{str(k).zfill(width)}", keys) for k in numbers)
    return [tag for tag in found if tag is not None]


def _items(line: str, keys: Mapping[str, str]) -> list[tuple[str, str]]:
    """A line's tokens as (kind, value): "tag" (the tag), "range" (THRU), "fill" (no word of a note: a symbol's
    letter, a number, TYP, (E), a joiner) or "word". A prefix and its number apart ("VAV 1") are one tag."""
    tokens = [t for t in _LABEL_SPLIT.split(line) if t]
    items: list[tuple[str, str]] = []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        tag = _token_tag(token, keys)
        if tag is None and i + 1 < len(tokens) and _token_tag(tokens[i + 1], keys) is None:
            pair = _key_tag(_bare(token) + _bare(tokens[i + 1]), keys)
            if pair is not None:
                items.append(("tag", pair))
                i += 2
                continue
        bare = _bare(token).upper()
        if tag is not None:
            items.append(("tag", tag))
        elif bare in _RANGE_WORD:
            items.append(("range", bare))
        elif not bare or _LABEL_FILLER.fullmatch(bare):
            items.append(("fill", bare))
        else:
            items.append(("word", bare))
        i += 1
    return items


def _line_tally(line: str, keys: Mapping[str, str]) -> Counter:
    """One line's labels. The tag alone; else, when the line's first token that is no symbol or number is a tag and
    the line has at most NOTE_WORDS words, that tag and every other tag on it not named after a reference word
    (TO, FROM, SEE, SERVED BY …), and a THRU range's members between its ends."""
    tag = _key_tag(line, keys)
    if tag is not None:
        return Counter({tag: 1})
    items = _items(line, keys)
    content = [(n, item) for n, item in enumerate(items) if item[0] != "fill"]
    if not content or content[0][1][0] != "tag" or sum(kind == "word" for kind, _ in items) > NOTE_WORDS:
        return Counter()
    tally: Counter = Counter()
    previous: tuple[str, str] | None = None
    for at, (kind, value) in content:
        if kind == "tag" and not (previous and previous[0] == "word" and previous[1] in _REFERENCE_WORDS):
            tally[value] += 1
        elif kind == "range" and previous and previous[0] == "tag" and at + 1 < len(items):
            high_kind, high = items[at + 1]
            if high_kind == "tag" or (high_kind == "fill" and high.isdigit()):
                tally.update(_range_members(previous[1], high, keys))
        previous = (kind, value)
    return tally


def _stated(line: str, keys: Mapping[str, str]) -> tuple[str, int | None] | None:
    """(the tag, its stated count) of a line that is a tag and a count of its places and nothing else; the count is
    None when it is not read (not a number, zero, or over STATED_MOST). None when the line is no such line."""
    found = _HEAD_AND_REST.match(line)
    if found is None:
        return None
    tag = _token_tag(found.group(1), keys)
    if tag is None:
        return None
    rest, bracketed = found.group(2).strip(), False
    if rest.startswith("(") and rest.endswith(")"):
        rest, bracketed = rest[1:-1].strip(), True
    patterns = _STATED + ((_STATED_IN_BRACKETS,) if bracketed else ())
    match = next((m for m in (p.match(rest) for p in patterns) if m), None)
    if match is None:
        return None
    n = match.group("n")
    return tag, (int(n) if n.isdigit() and 0 < int(n) <= STATED_MOST else None)


def unread_counts(text: str, keys: Mapping[str, str]) -> list[tuple[str, str]]:
    """(tag, the line) for each line that states a count of a tag's places the reader does not read (over
    STATED_MOST, zero, or not a number: "CUH-A (TYP. OF 60)", "CUH-A TYP. OF FOUR"); `line_labels` counts such a line
    as one place, and the counts line says so (FINAL-O H3)."""
    found = []
    for line in text.splitlines():
        stated = _stated(line, keys)
        if stated is not None and stated[1] is None:
            found.append((stated[0], " ".join(line.split())))
    return found


def line_labels(text: str, keys: Mapping[str, str]) -> Counter:
    """Each tag's labels in a sheet's text (`label_keys` gives `keys`): a line that is the tag alone, a bubble (a
    prefix alone over its number), a tag split over two lines ("VAV-" over "3"), and the tags of a line that starts
    with a tag (`_line_tally`: "VAV-1 VAV-1 T T", "EF-1 450", "AHU-1 (E)", "VAV-3 450 CFM", "EF-2 ON ROOF",
    "FCU-4 / FCU-5", "VAV-1 THRU VAV-5"). Never a tag after a word of a note ("TO EUH-1"), nor in a long note. A tag
    with a stated count of its places and nothing else ("CUH-A (TYP. OF 4)", "x4", "(4)", "4 PLACES", `_stated`) is
    that many labels, up to STATED_MOST; a count not read is one (`unread_counts`)."""
    tally: Counter = Counter()
    lines = text.splitlines()
    skip = False
    for n, line in enumerate(lines):
        if skip:
            skip = False
            continue
        tag = _key_tag(line, keys)
        if tag is None and n + 1 < len(lines) and _BUBBLE_HEAD.fullmatch(line):
            tag = _key_tag(line + lines[n + 1], keys)      # a tag bubble: "VAV" over "5-7"
            skip = tag is not None
        if tag is not None:
            tally[tag] += 1
            continue
        stated = _stated(line, keys)
        if stated is not None:
            tally[stated[0]] += stated[1] or 1      # "CUH-A (TYP. OF 4)": 4 places (FINAL-O H3)
            continue
        mine = _line_tally(line, keys)
        if n + 1 < len(lines) and _SPLIT_TAG.search(line + "\n"):
            # a tag split over two lines, "VAV-" over "3": read joined, and kept only where it reads more
            apart = mine + _line_tally(lines[n + 1], keys)
            joined = _line_tally(line.rstrip() + lines[n + 1].lstrip(), keys)
            if joined - apart:
                tally.update(apart | joined)
                skip = True
                continue
        tally.update(mine)
    return tally


def named_tags(text: str, keys: Mapping[str, str]) -> set[str]:
    """Every tag of `keys` the text names, a label or not ("TO VAV-3", "OFFICE 101 VAV-3", a tag split over two
    lines)."""
    found = set(line_labels(text, keys))
    for line in _SPLIT_TAG.sub("-", text).splitlines():
        tag = _key_tag(line, keys)
        if tag is not None:
            found.add(tag)
        found |= {value for kind, value in _items(line, keys) if kind == "tag"}
    return found


def plan_labels(text: str, keys: Mapping[str, str], labels: Counter | None = None) -> Counter:
    """A counted plan sheet's labels (`line_labels`), with the backstop (REVIEW-FINAL7 F4): a unit's tag
    (`is_type_tag` false) the sheet names anywhere and labels nowhere counts once, so a unit shown on a plan is never
    lost however its label is written. A type's tag counts only where it is labelled (its places decide its count).
    `labels`: the text's `line_labels`, when the caller has them already."""
    tally = Counter(line_labels(text, keys) if labels is None else labels)
    for tag in named_tags(text, keys):
        if not tally[tag] and not is_type_tag(tag):
            tally[tag] = 1
    return tally
