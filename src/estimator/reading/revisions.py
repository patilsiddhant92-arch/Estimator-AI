"""Revisions: which issue of each drawing sheet governs, and what changed (design §9.8).

A sheet's issues are read from the revision table in its title block — rows of a number,
a description and a date ("4  ADDENDUM #1  02 26 25"). When the same sheet number is in
more than one document, the latest date governs; with no dates, an addendum document beats
a base one; when neither decides, the estimator is asked. Pages repeated inside one
document (typical floors) are not versions of each other.

The change log compares the governing page with each page it replaces: equipment tags
added or removed, and note lines added or removed (a changed schedule row is logged once).
Revision clouds are not used — they can't be told apart from watermarks.

The words and date forms are the reading list in assets/reading_lists/revisions.json.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

from estimator.catalogue.job import other_sets, repeats
from estimator.catalogue.pdf import Span, clean_text
from estimator.catalogue.register import PageRecord
from estimator.catalogue.tags import Equipment, find_tags, label_keys, line_labels, sheet_number_tags

ASSETS = Path(__file__).resolve().parents[3] / "assets"
REVISIONS = ASSETS / "reading_lists" / "revisions.json"
MERGE_GAP = 0.002          # runs of text this close on one row are one run (OCR splits words apart)
_NUMBER = re.compile(r"^(?:[A-Z]?\d{1,3}[A-Z]?|[A-Z])\.?$")
_LEADING_NUMBER = re.compile(r"^\s*([A-Z]?\d{1,3}[A-Z]?|[A-Z])\.?\s+(?=\S)")
_COUNT_WORDS = {2: "two", 3: "three", 4: "four", 5: "five"}


@dataclass(frozen=True)
class Issue:
    number: str         # "4", or "" when the row has no number
    description: str    # "ADDENDUM #1"
    date: date | None


@dataclass(frozen=True)
class SheetVersion:
    sheet: str
    document: str
    page: int
    issues: tuple[Issue, ...]   # from the title block's revision table, oldest first
    latest: date | None         # the latest issue date, else None
    source: str                 # "title block" | "document is an addendum" | "unknown"


@dataclass(frozen=True)
class Change:
    sheet: str
    what: str           # "tag added" | "tag removed" | "schedule row changed" | "note added" | "note removed"
    old: str
    new: str
    affects_controls: bool


@dataclass(frozen=True)
class Supersession:
    sheet: str
    current: SheetVersion
    replaced: tuple[SheetVersion, ...]
    changes: tuple[Change, ...]
    note: str


@dataclass(frozen=True)
class Revisions:
    dates: tuple[tuple[re.Pattern, str], ...]
    months: tuple[str, ...]
    issue_words: tuple[re.Pattern, ...]
    not_issues: tuple[re.Pattern, ...]
    controls_words: tuple[re.Pattern, ...]
    row_reach: float
    max_description: int
    min_line_chars: int

    @classmethod
    def load(cls, path: Path = REVISIONS) -> "Revisions":
        return _load(str(path))

    def is_issue(self, text: str) -> bool:
        return (any(p.search(text) for p in self.issue_words)
                and not any(p.search(text) for p in self.not_issues))

    def is_controls(self, text: str) -> bool:
        return any(p.search(text) for p in self.controls_words)


@lru_cache
def _load(path: str) -> Revisions:
    data = json.loads(Path(path).read_text(encoding="utf-8"))

    def compiled(patterns):
        return tuple(re.compile(p, re.I) for p in patterns)

    dates = tuple((re.compile(rf"(?<![0-9]){d['pattern']}(?![0-9])", re.I), d["order"]) for d in data["dates"])
    return Revisions(dates, tuple(data["months"]), compiled(data["issue_words"]), compiled(data["not_issues"]),
                     compiled(data["controls_words"]), float(data["row_reach"]), int(data["max_description"]),
                     int(data["min_line_chars"]))


@lru_cache
def _equipment() -> Equipment:
    return Equipment.load()


def _squash(text: str) -> str:
    return " ".join(clean_text(text).split())


def _natural(text: str) -> list:
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", text)]


# ---- dates -------------------------------------------------------------------------------------

def _date_match(text: str, reading: Revisions, today: date | None = None) -> tuple[re.Match, date] | None:
    """The first real date in the text, in any of the reading list's forms. A two-digit year past
    next year is last century's ("95" is 1995), and a date more than a year after today is not an
    issue date at all and is passed over."""
    today = today or date.today()
    latest = today + timedelta(days=366)
    for pattern, order in reading.dates:
        for match in pattern.finditer(text):
            parts = dict(zip(order, match.groups()))
            month = parts["m"]
            month = reading.months.index(month[:3].upper()) + 1 if month.isalpha() else int(month)
            year = int(parts["y"])
            if year < 100:
                year = year + 2000 if year + 2000 <= today.year + 1 else year + 1900
            if not 1990 <= year <= 2099:
                continue
            try:
                when = date(year, month, int(parts["d"]))
            except ValueError:
                continue
            if when > latest:
                continue
            return match, when
    return None


def parse_date(text: str, reading: Revisions | None = None, today: date | None = None) -> date | None:
    found = _date_match(clean_text(text), reading or Revisions.load(), today)
    return found[1] if found else None


def _short(when: date | None) -> str:
    return when.strftime("%m/%d/%y") if when else ""


# ---- the revision table ------------------------------------------------------------------------

def _center(span: Span) -> float:
    return (span.y0 + span.y1) / 2


def _gap(a: Span, b: Span) -> float:
    return max(0.0, b.x0 - a.x1, a.x0 - b.x1)


def _bands(spans: Sequence[Span]) -> list[list[Span]]:
    """Runs of text on the same row: their middles within half a line's height of each other."""
    bands: list[tuple[float, float, list[Span]]] = []
    for span in sorted(spans, key=_center):
        height = span.y1 - span.y0
        if bands and abs(_center(span) - bands[-1][0]) <= 0.5 * min(height, bands[-1][1]):
            bands[-1][2].append(span)
        else:
            bands.append((_center(span), height, [span]))
    return [_merged(sorted(band, key=lambda s: s.x0)) for _, _, band in bands]


def _merged(band: list[Span]) -> list[Span]:
    out: list[Span] = []
    for span in band:
        if out and -0.001 <= span.x0 - out[-1].x1 <= MERGE_GAP:
            last = out[-1]
            out[-1] = Span(f"{last.text} {span.text}", last.size, last.x0, min(last.y0, span.y0), span.x1,
                           max(last.y1, span.y1))
        else:
            out.append(span)
    return out


def _one_run(text: str, reading: Revisions) -> Issue | None:
    """A whole row carried in one run of text: "4  ADDENDUM #1  02 26 25"."""
    found = _date_match(text, reading)
    if not found:
        return None
    match, when = found
    rest = f"{text[:match.start()]} {text[match.end():]}".strip()
    number = _LEADING_NUMBER.match(rest)
    description = _squash(rest[number.end():] if number else rest).strip(" -–—:")
    if not description or len(description) > reading.max_description or not reading.is_issue(description):
        return None
    return Issue(number.group(1) if number else "", description, when)


def read_revision_table(spans: Sequence[Span], reading: Revisions | None = None) -> tuple[Issue, ...]:
    """Every issue row in a title block's text, oldest first."""
    reading = reading or Revisions.load()
    found: dict[tuple, Issue] = {}
    for band in _bands(spans):
        for described in band:
            text = _squash(described.text)
            if len(text) > reading.max_description + 12 or not reading.is_issue(text):
                continue
            if _date_match(text, reading):
                issue = _one_run(text, reading)
            else:
                issue = _beside(described, text, band, reading)
            if issue:
                found.setdefault((issue.number, issue.description, issue.date), issue)
    return tuple(sorted(found.values(), key=lambda i: (i.date or date.min, _natural(i.number))))


def _beside(described: Span, text: str, band: list[Span], reading: Revisions) -> Issue | None:
    """An issue whose date and number are separate runs on the same row."""
    if len(text) > reading.max_description:
        return None
    dates = [(s, when) for s in band if s is not described and not reading.is_issue(s.text)
             and _gap(described, s) <= reading.row_reach and (when := parse_date(s.text, reading))]
    if not dates:
        return None
    dated, when = min(dates, key=lambda d: (round(_gap(described, d[0]), 3), abs(d[0].size - described.size),
                                            abs(_center(d[0]) - _center(described))))
    numbers = [s for s in band if s is not described and s is not dated and _NUMBER.match(s.text.strip())
               and min(_gap(described, s), _gap(dated, s)) <= reading.row_reach]
    number = min(numbers, key=lambda s: min(_gap(described, s), _gap(dated, s)), default=None)
    return Issue(number.text.strip().rstrip(".") if number else "", text, when)


# ---- versions ----------------------------------------------------------------------------------

def _sheet_number(number: str) -> str:
    return " ".join(number.split()).upper()


def sheet_versions(catalogue, reading: Revisions | None = None) -> list[SheetVersion]:
    """Every numbered drawing sheet, with the issues its title block lists."""
    reading = reading or Revisions.load()
    kinds = {d.relative: d.kind for d in catalogue.job.documents}
    records = {(p.document, p.page): p for p in catalogue.pages}
    versions = []
    for sheet in catalogue.sheets:
        if not sheet.number:
            continue
        record = records.get((sheet.document, sheet.page))
        issues = read_revision_table(record.edge_spans if record else (), reading)
        dates = [i.date for i in issues if i.date]
        if issues:
            source = "title block"
        elif kinds.get(sheet.document) == "addendum":
            source = "document is an addendum"
        else:
            source = "unknown"
        versions.append(SheetVersion(_sheet_number(sheet.number), sheet.document, sheet.page, issues,
                                     max(dates) if dates else None, source))
    return versions


@dataclass(frozen=True)
class _Content:
    tags: tuple[str, ...]
    lines: tuple[str, ...]
    schedule: bool
    tag_set: frozenset[str] = frozenset()
    line_set: frozenset[str] = frozenset()

    def same_as(self, other: "_Content") -> bool:
        """No change between the two: the same tags and the same note lines."""
        return self.tag_set == other.tag_set and self.line_set == other.line_set


def _content(record: PageRecord | None, schedule: bool, exclude: frozenset[str], reading: Revisions) -> _Content:
    if record is None:
        return _Content((), (), schedule)
    text = clean_text(record.text)
    tags = tuple(dict.fromkeys(find_tags(text, _equipment(), exclude)))
    title_block = " ".join(_squash(s.text) for s in sorted(record.edge_spans, key=lambda s: (round(s.y0, 3), s.x0)))
    lines = (_squash(line) for line in text.splitlines())
    kept = tuple(dict.fromkeys(line for line in lines
                               if len(line) >= reading.min_line_chars and line not in title_block))
    return _Content(tags, kept, schedule, frozenset(tags), frozenset(kept))


def _changes(sheet: str, new: _Content, old: _Content, reading: Revisions) -> list[Change]:
    equipment = _equipment()

    # Every unit needs controls: a unit that comes or goes always changes the controls scope.
    changes = [Change(sheet, "tag added", "", t, True) for t in new.tags if t not in old.tag_set]
    changes += [Change(sheet, "tag removed", t, "", True) for t in old.tags if t not in new.tag_set]
    added = [line for line in new.lines if line not in old.line_set]
    removed = [line for line in old.lines if line not in new.line_set]
    if new.schedule and added and removed:
        # Each line's first tag is looked up once; a removed row pairs with the first added row
        # that starts with the same tag.
        waiting: dict[str, list[str]] = defaultdict(list)
        for line in added:
            first = find_tags(line, equipment)[:1]
            if first:
                waiting[first[0]].append(line)
        paired: set[str] = set()
        unpaired: list[str] = []
        for line in removed:
            first = find_tags(line, equipment)[:1]
            partner = waiting[first[0]].pop(0) if first and waiting.get(first[0]) else None
            if partner is None:
                unpaired.append(line)
                continue
            paired.add(partner)
            changes.append(Change(sheet, "schedule row changed", line, partner,
                                  reading.is_controls(line) or reading.is_controls(partner)))
        removed = unpaired
        added = [line for line in added if line not in paired]
    changes += [Change(sheet, "note added", "", line, reading.is_controls(line)) for line in added]
    changes += [Change(sheet, "note removed", line, "", reading.is_controls(line)) for line in removed]
    return changes


def _label(version: SheetVersion) -> str:
    if version.issues:
        last = version.issues[-1]
        return f"{last.description} ({_short(last.date)})" if last.date else last.description
    return version.document.rsplit("/", 1)[-1]


def _and(items: list[str]) -> str:
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} and {items[-1]}"


def _note(sheet: str, current: SheetVersion, replaced: Sequence[SheetVersion], changes: Sequence[Change]) -> str:
    head = f"{sheet}: {_label(current)} replaces {_and([_label(v) for v in replaced])}"
    if not changes:
        return f"{head} — no changes found in the text"
    controls = sum(c.affects_controls for c in changes)
    count = f"{len(changes)} change{'s' if len(changes) != 1 else ''}"
    affect = "none affect controls" if not controls else f"{controls} affect{'s' if controls == 1 else ''} controls"
    return f"{head} — {count}, {affect}"


def _governing(versions: Sequence[SheetVersion], kinds: dict[str, str]) -> SheetVersion | None:
    pool = list(versions)
    if all(v.latest for v in versions):
        top = max(v.latest for v in versions)
        pool = [v for v in versions if v.latest == top]
        if len(pool) == 1:
            return pool[0]
    addenda = [v for v in pool if kinds.get(v.document) == "addendum"]
    return addenda[0] if len(addenda) == 1 else None


def supersede(catalogue, versions: Sequence[SheetVersion],
              reading: Revisions | None = None) -> tuple[list[Supersession], list[str]]:
    """For each sheet number in more than one document: which one governs, what it replaces, and what changed."""
    reading = reading or Revisions.load()
    kinds = {d.relative: d.kind for d in catalogue.job.documents}
    records = {(p.document, p.page): p for p in catalogue.pages}
    schedules = {(s.document, s.page) for s in catalogue.sheets if "Schedules" in s.types}
    exclude = sheet_number_tags((s.number for s in catalogue.sheets), _equipment())
    # A marked-up copy of the set (a document repeating most of another's sheets) is not a competing version.
    copies = {(_sheet_number(number), document) for number, document in repeats(catalogue)[1]}
    # Another set of drawings with the same sheet numbers (a second building, `other_sets`) is read beside the
    # original: its sheets are never versions of the original's (REVIEW-FINAL6 F3).
    others = {(_sheet_number(number), document) for number, document in other_sets(catalogue)}
    by_sheet: dict[str, dict[str, SheetVersion]] = defaultdict(dict)
    for version in versions:
        if (version.sheet, version.document) in others:
            continue
        by_sheet[version.sheet].setdefault(version.document, version)   # a page repeated in one document is not a version

    contents: dict[tuple[str, int], _Content] = {}

    def content(v: SheetVersion) -> _Content:
        key = (v.document, v.page)
        if key not in contents:
            contents[key] = _content(records.get(key), key in schedules, exclude, reading)
        return contents[key]

    alike = _Alike(catalogue, reading)
    supersessions, flags = [], []
    for sheet in sorted(by_sheet, key=_natural):
        in_documents = list(by_sheet[sheet].values())
        if len(in_documents) < 2:
            continue
        rivals = [v for v in in_documents if (v.sheet, v.document) not in copies]
        if len(rivals) < 2 and _governing(in_documents, kinds) is None:
            continue    # the only rival is a marked-up copy of the same set: nothing to decide
        distinct: list[SheetVersion] = []
        for version in in_documents:
            # The same text at the same issue (a marked-up copy of the set) is one version, not two; the same labels
            # too, each as often (`_Alike`, as `governing_pages` reads them).
            if not any(content(version).same_as(content(kept))
                       and alike.label_counts((version.document, version.page))
                       == alike.label_counts((kept.document, kept.page))
                       and (version.latest is None or kept.latest is None or version.latest == kept.latest)
                       for kept in distinct):
                distinct.append(version)
        if len(distinct) < 2:
            continue
        current = _governing(distinct, kinds)
        if current is None and len([v for v in distinct if (v.sheet, v.document) not in copies]) < 2:
            continue
        if current is None:
            count = _COUNT_WORDS.get(len(distinct), str(len(distinct)))
            dates = {v.latest for v in distinct}
            why = (f"the same date ({_short(next(iter(dates)))})" if len(dates) == 1 and None not in dates
                   else "no dates to order them")
            # `governing_pages` reads each version nothing orders and sums them (REVIEW-FINAL7 F2)
            read = [v.document.rsplit("/", 1)[-1] for v in distinct if (v.sheet, v.document) not in copies]
            meanwhile = _and(read) + (", summed," if len(read) > 1 else "")
            flags.append(f"Sheet {sheet} is in {count} documents with {why} — check which governs; "
                         f"counted from {meanwhile} for now")
            continue
        replaced = sorted((v for v in distinct if v is not current),
                          key=lambda v: (v.latest or date.min, kinds.get(v.document) == "addendum", v.document))
        changes = tuple(dict.fromkeys(c for old in replaced
                                      for c in _changes(sheet, content(current), content(old), reading)))
        supersessions.append(Supersession(sheet, current, tuple(replaced), changes,
                                          _note(sheet, current, replaced, changes)))
    return supersessions, flags


class _Alike:
    """Whether two pages show one version of a sheet: the same tags and note lines (`_Content.same_as`) and the
    same labels, each as often (`line_labels`: a type drawn 3 times is not one drawn 4 times)."""

    def __init__(self, catalogue, reading: Revisions | None = None):
        self.reading = reading or Revisions.load()
        self.records = {(p.document, p.page): p for p in catalogue.pages}
        self.schedules = {(s.document, s.page) for s in catalogue.sheets if "Schedules" in s.types}
        self.exclude = sheet_number_tags((s.number for s in catalogue.sheets), _equipment())
        self.keys = label_keys(t.tag for t in getattr(catalogue, "tags", ()))
        self.contents: dict[tuple[str, int], _Content] = {}
        self.labels: dict[tuple[str, int], Counter] = {}

    def content(self, key: tuple[str, int]) -> _Content:
        if key not in self.contents:
            self.contents[key] = _content(self.records.get(key), key in self.schedules, self.exclude, self.reading)
        return self.contents[key]

    def label_counts(self, key: tuple[str, int]) -> Counter:
        if key not in self.labels:
            record = self.records.get(key)
            self.labels[key] = line_labels(record.text or "", self.keys) if record is not None else Counter()
        return self.labels[key]

    def __call__(self, a: tuple[str, int], b: tuple[str, int]) -> bool:
        return self.content(a).same_as(self.content(b)) and self.label_counts(a) == self.label_counts(b)


def governing_pages(catalogue, supersessions: Sequence[Supersession] = (),
                    typicals: Iterable[str | None] = ()) -> frozenset[tuple[str, int]]:
    """The drawing pages the readers read, as (document, page): every page with no sheet number, and for each sheet
    number the pages of the document that governs it: the later issue when a supersession decided it. When none
    did, the first document that carries it and isn't a marked-up copy of another (`repeats`), and beside it each
    other such document whose pages are another version (`_Alike`): two versions nothing orders are both read and
    summed, and `supersede` says "check which governs" (REVIEW-FINAL7 F2: an undated reissue that adds a unit
    never loses it). Inside one document a number on several pages with the same text on every page is read on its
    first page (one plan printed again); pages of one number with other text are all read (F7). A typical sheet
    (one plan standing for several floors) is read on its first page in each document (F3). A sheet of another set
    of drawings with the same numbers (`other_sets`: a second building) is read too, beside the governing one
    (REVIEW-FINAL6 F3): when in doubt, sum."""
    copies = {(_sheet_number(number), document) for number, document in repeats(catalogue)[1]}
    others = {(_sheet_number(number), document) for number, document in other_sets(catalogue)}
    current = {s.sheet: s.current.document for s in supersessions}
    typical = {_sheet_number(t) for t in typicals if t}
    texts = {(p.document, p.page): p.text for p in catalogue.pages}
    alike: _Alike | None = None
    keep: set[tuple[str, int]] = set()
    by_number: dict[str, list] = defaultdict(list)
    for sheet in catalogue.sheets:
        if sheet.number:
            by_number[_sheet_number(sheet.number)].append(sheet)
        else:
            keep.add((sheet.document, sheet.page))
    for number, sheets in by_number.items():
        documents = list(dict.fromkeys(s.document for s in sheets))
        rivals = [d for d in documents if (number, d) not in copies | others]
        pages = {d: [(s.document, s.page) for s in sheets if s.document == d] for d in documents}
        if number in current:
            governing = [current[number]]
        elif len(rivals) > 1:
            alike = alike or _Alike(catalogue)
            governing = []
            for document in rivals:
                if not any(all(any(alike(a, b) for b in pages[kept]) for a in pages[document]) for kept in governing):
                    governing.append(document)
        else:
            governing = rivals[:1] or documents[:1]
        for document in documents:
            if document not in governing and (number, document) not in others:
                continue
            mine = pages[document]
            if number in typical or len({texts.get(key, "") for key in mine}) == 1:
                mine = mine[:1]
            keep.update(mine)
    return frozenset(keep)
