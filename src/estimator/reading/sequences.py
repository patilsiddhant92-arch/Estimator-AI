"""Where the sequence of operation and points list sit — the backbone for step 5.

The sequence of operation is the most important document for scope (design §9.8, §10.2):
it decides which scope lines exist. This module only finds where it is — in a spec
section, on a drawing sheet, or carried (twice) as plain text inside a controls section
that isn't itself titled a sequence. Reading what it says is step 5's job, not this one.
"""
from __future__ import annotations

import difflib
import json
import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol

from estimator.catalogue.register import PageRecord
from estimator.catalogue.sheet_types import Sheet
from estimator.catalogue.spec_sections import SpecSection

ASSETS = Path(__file__).resolve().parents[3] / "assets"
SEQUENCES = ASSETS / "reading_lists" / "sequences.json"

SEQUENCE = "Sequence of operation"
POINTS = "Points list"
_SIMILAR = 0.90          # difflib ratio, first _DIFF_CHARS of the first page, for "carried twice"
_DIFF_CHARS = 2000


class _Catalogue(Protocol):
    """Only what this module reads off a Catalogue — kept loose so tests can pass a stand-in."""
    sections: Sequence[SpecSection]
    sheets: Sequence[Sheet]
    pages: Sequence[PageRecord]


@dataclass(frozen=True)
class Backbone:
    what: str              # "Sequence of operation" | "Points list"
    where: str             # "23 09 93 SEQUENCE OF OPERATIONS (Specs.pdf, pages 40–75)"
    document: str
    first_page: int
    last_page: int
    kind: str              # "spec section" | "spec pages" (no section heading) | "drawing sheet"
    duplicate_of: str | None = None   # the same text carried in another document


@dataclass(frozen=True)
class _Rules:
    sequence_numbers: tuple[re.Pattern, ...]
    points_numbers: tuple[re.Pattern, ...]
    sequence_title: re.Pattern
    points_title: re.Pattern
    sequence_heading: re.Pattern
    points_page_heading: re.Pattern
    points_page_top_lines: int
    points_page_not_heading: re.Pattern
    no_sequence_flag: str
    no_points_flag: str

    @classmethod
    def load(cls, path: Path = SEQUENCES) -> "_Rules":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            tuple(re.compile(p) for p in data["sequence_numbers"]),
            tuple(re.compile(p) for p in data["points_numbers"]),
            re.compile(data["sequence_title"], re.I),
            re.compile(data["points_title"], re.I),
            re.compile(data["sequence_heading"], re.M | re.I),
            re.compile(data["points_page_heading"], re.I),
            int(data["points_page_top_lines"]),
            re.compile(data["points_page_not_heading"]),
            data["no_sequence_flag"],
            data["no_points_flag"],
        )


def _name(document: str) -> str:
    return document.rsplit("/", 1)[-1]


def _pages_desc(first: int, last: int) -> str:
    return f"page {first}" if first == last else f"pages {first}–{last}"


def _label(number: str, title: str | None) -> str:
    return f"{number} {title}".strip() if title else number


def _core(number: str) -> str:
    return number.split(".", 1)[0]


def _is_sequence_section(section: SpecSection, rules: _Rules) -> bool:
    return (any(p.fullmatch(_core(section.number)) for p in rules.sequence_numbers)
            or bool(rules.sequence_title.search(section.title or "")))


def _is_points_section(section: SpecSection, rules: _Rules) -> bool:
    return (any(p.fullmatch(_core(section.number)) for p in rules.points_numbers)
            or bool(rules.points_title.search(section.title or "")))


def _section_backbone(what: str, section: SpecSection, prefix: str = "") -> Backbone:
    where = (f"{prefix}{_label(section.number, section.title)} "
             f"({_name(section.document)}, {_pages_desc(section.first_page, section.last_page)})")
    return Backbone(what, where, section.document, section.first_page, section.last_page, "spec section")


def _has_heading(pages_by_doc: dict[str, list[PageRecord]], section: SpecSection, rules: _Rules) -> bool:
    for record in pages_by_doc.get(section.document, ()):
        if section.first_page <= record.page <= section.last_page and rules.sequence_heading.search(record.text):
            return True
    return False


def _text_at(pages_by_key: dict[tuple[str, int], str], document: str, page: int) -> str:
    return pages_by_key.get((document, page), "")


def _carried_twice(pages_by_key: dict[tuple[str, int], str], primary: Backbone, section: SpecSection) -> bool:
    a = _text_at(pages_by_key, primary.document, primary.first_page)[:_DIFF_CHARS]
    b = _text_at(pages_by_key, section.document, section.first_page)[:_DIFF_CHARS]
    if not a or not b:
        return False
    return difflib.SequenceMatcher(None, a, b).ratio() >= _SIMILAR


def _spec_backbones(sections: Sequence[SpecSection], pages_by_doc: dict[str, list[PageRecord]],
                     pages_by_key: dict[tuple[str, int], str], rules: _Rules) -> list[Backbone]:
    found: list[Backbone] = []
    primaries: dict[tuple[str, str, str, bool], Backbone] = {}
    for section in sections:
        is_seq = _is_sequence_section(section, rules)
        is_pts = _is_points_section(section, rules)
        entries: list[tuple[str, bool]] = []
        if is_seq:
            entries.append((SEQUENCE, False))
        if is_pts:
            entries.append((POINTS, False))
        if not is_seq and section.controls and _has_heading(pages_by_doc, section, rules):
            entries.append((SEQUENCE, True))
        for what, inside in entries:
            backbone = _section_backbone(what, section, prefix="sequence inside " if inside else "")
            key = (what, section.number, section.title, inside)
            primary = primaries.get(key)
            if primary is None:
                primaries[key] = backbone
            elif _carried_twice(pages_by_key, primary, section):
                backbone = replace(backbone, duplicate_of=primary.where)
            found.append(backbone)
    return found


def _names_points_list(text: str, rules: _Rules) -> bool:
    top = [line for line in text.splitlines() if line.strip()][:rules.points_page_top_lines]
    return any(rules.points_page_heading.search(line) and not rules.points_page_not_heading.search(line)
               for line in top)


def _unheaded_points(sections: Sequence[SpecSection], pages_by_doc: dict[str, list[PageRecord]],
                     rules: _Rules) -> list[Backbone]:
    """A points list bound into a spec book as a spreadsheet export, between two sections, has no
    SECTION heading or page footer, so no section covers it. Its column headings name it; the pages
    after it carry on the list until the next section or a blank page."""
    covered: dict[str, set[int]] = defaultdict(set)
    for section in sections:
        covered[section.document].update(range(section.first_page, section.last_page + 1))
    found: list[Backbone] = []
    for document, pages in pages_by_doc.items():
        if document not in covered:
            continue                        # not a spec book
        run: list[int] = []
        for record in sorted(pages, key=lambda r: r.page):
            free = (record.page not in covered[document] and not record.large_sheet
                    and record.status in ("text", "ocr"))
            if free and run and record.page == run[-1] + 1:
                run.append(record.page)
                continue
            if run:
                found.append(_pages_backbone(document, run))
                run = []
            if free and _names_points_list(record.text, rules):
                run = [record.page]
        if run:
            found.append(_pages_backbone(document, run))
    return found


def _pages_backbone(document: str, run: list[int]) -> Backbone:
    where = f"Points list pages with no section heading ({_name(document)}, {_pages_desc(run[0], run[-1])})"
    return Backbone(POINTS, where, document, run[0], run[-1], "spec pages")


def _runs(sheets: list[Sheet]) -> list[list[Sheet]]:
    ordered = sorted(sheets, key=lambda s: (s.document, s.page))
    runs: list[list[Sheet]] = []
    for sheet in ordered:
        if runs and runs[-1][-1].document == sheet.document and runs[-1][-1].page == sheet.page - 1:
            runs[-1].append(sheet)
        else:
            runs.append([sheet])
    return runs


def _sheet_backbone(what: str, run: list[Sheet]) -> Backbone:
    first, last = run[0], run[-1]
    first_number = first.number or "(no sheet number)"
    last_number = last.number or "(no sheet number)"
    number = first_number if first_number == last_number else f"{first_number} to {last_number}"
    where = f"{number} {first.title} ({_name(first.document)}, {_pages_desc(first.page, last.page)})"
    return Backbone(what, where, first.document, first.page, last.page, "drawing sheet")


def _sheet_backbones(sheets: Sequence[Sheet], rules: _Rules) -> list[Backbone]:
    found: list[Backbone] = []
    seq_sheets = [s for s in sheets if s.title and rules.sequence_title.search(s.title)]
    pts_sheets = [s for s in sheets if s.title and rules.points_title.search(s.title)]
    found += [_sheet_backbone(SEQUENCE, run) for run in _runs(seq_sheets)]
    found += [_sheet_backbone(POINTS, run) for run in _runs(pts_sheets)]
    return found


def find_backbone(catalogue: _Catalogue) -> tuple[list[Backbone], list[str]]:
    rules = _Rules.load()
    pages_by_doc: dict[str, list[PageRecord]] = defaultdict(list)
    pages_by_key: dict[tuple[str, int], str] = {}
    for record in catalogue.pages:
        pages_by_doc[record.document].append(record)
        pages_by_key[(record.document, record.page)] = record.text
    found = _spec_backbones(catalogue.sections, pages_by_doc, pages_by_key, rules)
    found += _unheaded_points(catalogue.sections, pages_by_doc, rules)
    found += _sheet_backbones(catalogue.sheets, rules)
    has_sequence = any(b.what == SEQUENCE for b in found)
    has_points = any(b.what == POINTS for b in found)
    flags: list[str] = []
    if not has_sequence:
        flags.append(rules.no_sequence_flag)
    elif not has_points:
        flags.append(rules.no_points_flag)
    return found, flags
