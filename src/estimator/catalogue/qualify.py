"""The bid check: does the spec let AME bid this job? (design §8)

AME bids two Niagara N4 product lines, Honeywell WEBs and Johnson Controls FX. The check
finds every passage that names a controls manufacturer, quotes it word for word, and
sorts the job into Qualifies / Open / Does not qualify. The tool reports; the US team
decides. Every other controls manufacturer found is listed for them, whatever the finding.

The controller's principle (build step 3, bid-check fix round): a wrong Qualifies is the
costliest result, because it is the only one that doesn't hold the job for the US team; a
wrong Open only costs them a look. So Qualifies requires clear evidence and nothing against
it; anything contradictory or uncertain is Open, with every passage quoted. Does not qualify
is reserved for explicit sole-source wording for another manufacturer, with no AME line named
anywhere. Silent is Open.
"""
from __future__ import annotations

import bisect
import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from estimator.catalogue.register import PageRecord
from estimator.catalogue.sheet_types import Sheet
from estimator.catalogue.spec_sections import SpecSection

# A large sheet of one of these disciplines, typed one of these ways, carries controls-relevant
# prose even away from the specs — its own "spec section", in effect — so a passage on it is read
# the same way as one inside a controls spec section (C1, N1). A sheet typed Schedules never
# counts, whatever else it's typed or which discipline it's on (N6): the equipment maker and a
# "BASIS OF DESIGN" column on a schedule are not the controls system.
CONTROLS_SHEET_DISCIPLINES = ("Mechanical", "Controls")
SHEET_TYPES_LIKE_CONTROLS = ("Specifications", "Control diagrams", "Network riser", "Notes and legends")

# Honeywell and Johnson Controls generic mentions share a maker with one of AME's own lines
# (Honeywell WEBs, Johnson Controls FX). When both are named in the same passage, showing the
# generic name too ("Honeywell (not on a list, not WEBs)") contradicts the line already credited
# to AME (N5) — so it's dropped from that passage.
SAME_MAKER_OURS = {"Honeywell": "Honeywell WEBs", "Johnson Controls": "Johnson Controls FX"}

ASSETS = Path(__file__).resolve().parents[3] / "assets"
MANUFACTURERS = ASSETS / "reading_lists" / "manufacturers.json"
REACH = 350        # characters either side of a manufacturer's name that make up its passage
CARRY_LINES = 5    # lines of the previous page carried into this one's search text (I7): a list
                   # running over a page break keeps its heading

# Sentence scope (build step 3, bid-check fix round 2, D2/D6): sole-source, basis-of-design and
# rejection wording count only when they sit in the same sentence as a manufacturer's name. A
# sentence ends at ". ", "; ", or a new list item ("B.", "2.", "a."); a list item ("clause") is the
# coarser unit bounded only by a new list item, used when the wording's own sentence is a bare
# fragment ("No substitutions.") naming nobody — it then binds to the nearest name still in the
# same clause, not to a different clause's name (or a different page's) merely because both sit
# within REACH of each other.
_SENTENCE_END = re.compile(r"[.;]\s+")
_LIST_ITEM = re.compile(r"(?:^|\n)[ \t]*([A-Za-z]{1,2}|\d{1,3})\.[ \t]+", re.M)


def _clause_boundaries(text: str) -> list[int]:
    points = {0, len(text)}
    points.update(m.start(1) for m in _LIST_ITEM.finditer(text))
    return sorted(points)


def _sentence_boundaries(text: str) -> list[int]:
    points = {0, len(text)}
    points.update(m.end() for m in _SENTENCE_END.finditer(text))
    points.update(m.start(1) for m in _LIST_ITEM.finditer(text))
    return sorted(points)


def _span_at(boundaries: list[int], start: int, end: int) -> tuple[int, int]:
    lo = boundaries[max(bisect.bisect_right(boundaries, start) - 1, 0)]
    hi = boundaries[min(bisect.bisect_left(boundaries, end), len(boundaries) - 1)]
    return lo, hi


def _name_occurrences(names: Sequence["Named"], text: str) -> list[tuple[int, int, str]]:
    return [(m.start(), m.end(), n.name) for n in names for p in n.patterns for m in p.finditer(text)]


def _bind(bindable: list[tuple[int, int, str]], start: int, end: int,
         sentence_bounds: list[int], clause_bounds: list[int]) -> list[str]:
    """Which name(s) a sole-source/basis-of-design/rejection phrase belongs to: whichever
    manufacturer's name shares its sentence; failing that, whichever name is nearest to it (the
    one right before it, or else the first one) in the same clause; failing that, none at all."""
    s_lo, s_hi = _span_at(sentence_bounds, start, end)
    in_sentence = sorted({n for a, b, n in bindable if s_lo <= a < s_hi})
    if in_sentence:
        return in_sentence
    c_lo, c_hi = _span_at(clause_bounds, start, end)
    in_clause = [(a, n) for a, b, n in bindable if c_lo <= a < c_hi]
    if not in_clause:
        return []
    before = [(a, n) for a, n in in_clause if a < start]
    _, name = max(before, key=lambda x: x[0]) if before else min(in_clause, key=lambda x: x[0])
    return [name]


@dataclass(frozen=True)
class Named:
    name: str
    patterns: tuple[re.Pattern, ...]
    note: str = ""   # e.g. "not WEBs" — shown when this name is recorded only "in passing" (I9)

    def found_in(self, text: str) -> bool:
        return any(p.search(text) for p in self.patterns)


@dataclass(frozen=True)
class ReadingList:
    ours: tuple[Named, ...]
    listed: tuple[Named, ...]
    others: tuple[Named, ...]
    controls_words: re.Pattern
    list_words: re.Pattern
    sole_words: re.Pattern
    basis_words: re.Pattern
    not_controls_words: re.Pattern
    unacceptable_words: re.Pattern

    @classmethod
    def load(cls, path: Path = MANUFACTURERS) -> "ReadingList":
        data = json.loads(Path(path).read_text(encoding="utf-8"))

        def named(key):
            return tuple(Named(e["name"], tuple(re.compile(p, 0 if e.get("exact_case") else re.I) for p in e["patterns"]),
                               e.get("not_ours", "")) for e in data[key])

        def words(key):
            return re.compile("|".join(f"(?:{w})" for w in data[key]), re.I)

        return cls(named("platforms_we_bid"), named("on_an_approved_list"), named("other_manufacturers"),
                   words("controls_words"), words("list_words"), words("sole_words"), words("basis_words"),
                   words("not_controls_words"), words("unacceptable_words"))

    def all_names(self) -> tuple[Named, ...]:
        return self.ours + self.listed + self.others

    def is_metasys_shadowed(self, name: str, passage: str) -> bool:
        """Johnson Controls never counts on a list when the passage mentions Metasys anywhere,
        unless FX is named too — "Metasys by Johnson Controls" and "Johnson Controls, Inc." with
        Metasys on the next line both apply, since this looks anywhere in the passage, not only
        nearby."""
        if name != "Johnson Controls":
            return False
        metasys = next((n for n in self.others if n.name == "Johnson Controls Metasys"), None)
        fx = next((n for n in self.ours if n.name == "Johnson Controls FX"), None)
        return bool(metasys and metasys.found_in(passage) and not (fx and fx.found_in(passage)))


@dataclass(frozen=True)
class Mention:
    document: str
    page: int
    quote: str
    ours: tuple[str, ...]
    listed: tuple[str, ...]
    others: tuple[str, ...]
    sheet: str | None = None            # the sheet number, when the passage is on a drawing sheet
    passing: tuple[tuple[str, str], ...] = ()   # (name, note) — Honeywell/JCI named outside a list (I9)
    is_list: bool = False               # list wording ("acceptable manufacturers:") is in the passage
    also_at: tuple[tuple[str, int, str | None], ...] = ()   # (document, page, sheet) of the same quote elsewhere (M3)
    sole_for: tuple[str, ...] = ()       # other manufacturer(s) sole-sourced in their own sentence (D2)
    basis_for: tuple[str, ...] = ()      # other manufacturer(s) named basis of design in their own sentence
    rejected_ours: tuple[str, ...] = ()  # AME's own line(s) called unacceptable in their own sentence

    @property
    def named(self) -> str:
        """The "Manufacturers named" column: AME's own lines marked, so they aren't mistaken
        for another manufacturer's (M10)."""
        parts = [f"{n} (a line AME bids)" for n in self.ours]
        parts += list(self.listed)
        parts += list(self.others)
        parts += [f"{n} (not on a list, {note})" for n, note in self.passing]
        return ", ".join(parts)


@dataclass(frozen=True)
class BidCheck:
    finding: str                       # "Qualifies" | "Open" | "Does not qualify"
    reason: str                        # one plain sentence
    others: tuple[str, ...]            # every other controls manufacturer named — for the US team
    mentions: tuple[Mention, ...]
    controls_sections: tuple[str, ...]


def check_bid(pages: Sequence[PageRecord], sections: Sequence[SpecSection],
              sheets: Mapping[tuple[str, int], Sheet] | None = None, has_spec_book: bool = True,
              reading: ReadingList | None = None) -> BidCheck:
    """Every page is searched — the specs, and the drawings too (design §8): a job with no spec
    book at all can carry its whole specification on a drawing sheet (C1)."""
    reading = reading or ReadingList.load()
    sheets = sheets or {}
    controls = [s for s in sections if s.controls]
    texts = _carried_texts(pages)
    raw = [m for record in pages
           for m in _mentions(record, texts[(record.document, record.page)], controls,
                              sheets.get((record.document, record.page)), reading)]
    mentions = _dedupe(raw)
    others = tuple(sorted({name for m in mentions for name in m.others}))
    section_names = tuple(dict.fromkeys(f"{s.number} {s.title}".strip() for s in controls))   # each named once
    finding, reason = _judge(mentions, others)
    if not controls:
        if has_spec_book:
            reason += (" The specs have no controls section (23 09 xx, 159xx or Division 25) — the whole spec, "
                       "plus the drawings' notes and spec sheets, was searched.")
        else:
            reason += (" No spec book was found among the bid documents; the drawings' notes and spec sheets "
                       "were searched.")
    unread = sorted({r.page for r in pages if r.status == "unreadable" and sheets.get((r.document, r.page)) is None})
    if unread:
        word = "page" if len(unread) == 1 else "pages"
        reason += (f" {len(unread)} {word} of the specs could not be read ({word} {_page_ranges(unread)}) — "
                   "the check could not see them.")
    return BidCheck(finding, reason, others, tuple(mentions), section_names)


def _carried_texts(pages: Sequence[PageRecord]) -> dict[tuple[str, int], str]:
    """A list of acceptable manufacturers can run over a page break, and the heading that gives
    it meaning ("Acceptable manufacturers:") sits on the page before — carry the tail of each
    page's text into the next one so the search sees the whole list together (I7)."""
    texts: dict[tuple[str, int], str] = {}
    previous: PageRecord | None = None
    for record in pages:
        if previous is not None and previous.document == record.document and previous.page == record.page - 1:
            tail = [line for line in previous.text.split("\n") if line.strip()][-CARRY_LINES:]
            texts[(record.document, record.page)] = f"{chr(10).join(tail)}\n{record.text}" if tail else record.text
        else:
            texts[(record.document, record.page)] = record.text
        previous = record
    return texts


def _page_ranges(numbers: list[int]) -> str:
    runs: list[list[int]] = []
    for n in sorted(numbers):
        if runs and n == runs[-1][1] + 1:
            runs[-1][1] = n
        else:
            runs.append([n, n])
    return ", ".join(str(a) if a == b else f"{a}–{b}" for a, b in runs)


def _dedupe(mentions: list[Mention]) -> list[Mention]:
    """The same passage is often quoted from more than one copy of a document — list it once,
    with every place it was found (M3)."""
    groups: dict[str, list[Mention]] = {}
    for m in mentions:
        groups.setdefault(m.quote, []).append(m)
    merged = []
    for items in groups.values():
        first, rest = items[0], items[1:]
        merged.append(replace(first, also_at=tuple((m.document, m.page, m.sheet) for m in rest)) if rest else first)
    return merged


def _mentions(record: PageRecord, text: str, controls: Sequence[SpecSection], sheet: Sheet | None,
             reading: ReadingList) -> list[Mention]:
    if sheet is not None and "Schedules" in sheet.types:
        return []   # a sheet typed Schedules never carries the controls system's own scope (N6)
    in_controls_section = any(s.document == record.document and s.first_page <= record.page <= s.last_page
                              for s in controls)
    in_controls_sheet = (sheet is not None and sheet.discipline in CONTROLS_SHEET_DISCIPLINES
                         and any(t in sheet.types for t in SHEET_TYPES_LIKE_CONTROLS))
    windows = []
    for named in reading.all_names():
        for pattern in named.patterns:
            for match in pattern.finditer(text):
                start = text.rfind("\n", 0, max(0, match.start() - REACH)) + 1
                end = text.find("\n", min(len(text), match.end() + REACH))
                windows.append((start, len(text) if end == -1 else end))
    merged: list[list[int]] = []
    for start, end in sorted(windows):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    found = []
    for start, end in merged:
        passage = text[start:end]
        # A genuine controls spec section is read on its own terms — a security/fire-alarm word
        # inside it doesn't disqualify the passage. Everywhere else (a drawing sheet promoted by
        # its type, or any other page reached only by a strong HVAC-controls word) the security
        # exclusion applies (N1): it also covers a controls-typed sheet of another discipline,
        # which no longer reaches this point via in_controls_sheet at all.
        if in_controls_section:
            pass
        elif in_controls_sheet:
            if reading.not_controls_words.search(passage):
                continue
        elif reading.controls_words.search(passage) and not reading.not_controls_words.search(passage):
            pass
        else:
            continue
        ours = tuple(n.name for n in reading.ours if n.found_in(passage))
        approved = [n for n in reading.listed if n.found_in(passage)
                   and not reading.is_metasys_shadowed(n.name, passage)
                   and SAME_MAKER_OURS.get(n.name) not in ours]
        is_list = bool(reading.list_words.search(passage))
        listed = tuple(n.name for n in approved) if is_list else ()
        # Honeywell or Johnson Controls named outside a list — or on a list that turned out not to
        # be an approved-manufacturers list at all — is never one of AME's own lines, but it's
        # still worth recording, "named in passing", rather than vanishing without a trace (I9).
        passing = tuple((n.name, n.note) for n in approved if n.name not in listed)
        others = tuple(n.name for n in reading.others if n.found_in(passage))
        # D2/D6: sole-source, basis-of-design and rejection wording only count for the specific
        # manufacturer named in the same sentence (or, for a bare fragment like "No substitutions.",
        # the nearest name still in the same clause) — never for whichever name merely sits
        # somewhere in the same 350-character passage.
        bindable = _name_occurrences(reading.ours, passage) + _name_occurrences(reading.others, passage)
        sentence_bounds = _sentence_boundaries(passage)
        clause_bounds = _clause_boundaries(passage)
        own_names, other_names = set(ours), set(others)
        sole_for, basis_for, rejected_ours = set(), set(), set()
        for pattern, bucket, eligible in ((reading.sole_words, sole_for, other_names),
                                          (reading.basis_words, basis_for, other_names),
                                          (reading.unacceptable_words, rejected_ours, own_names)):
            for match in pattern.finditer(passage):
                for name in _bind(bindable, match.start(), match.end(), sentence_bounds, clause_bounds):
                    if name in eligible:
                        bucket.add(name)
        if ours or listed or others or passing:
            found.append(Mention(document=record.document, page=record.page,
                                 quote=" ".join(passage.split()), ours=ours, listed=listed, others=others,
                                 sheet=sheet.number if sheet is not None else None,
                                 passing=passing, is_list=is_list,
                                 sole_for=tuple(sorted(sole_for)), basis_for=tuple(sorted(basis_for)),
                                 rejected_ours=tuple(sorted(rejected_ours))))
    return found


def _place(document: str, page: int, sheet: str | None, ambiguous: bool) -> str:
    name = document if ambiguous else document.rsplit("/", 1)[-1]
    body = f"{name}, page {page}"
    return f"{sheet} ({body})" if sheet else body


def where(mention: Mention) -> str:
    """Every place the passage was found (M3): the folder is given only when two of them share
    a file name — most quotes have a single place, where this reads exactly as it always did."""
    places = [(mention.document, mention.page, mention.sheet)] + list(mention.also_at)
    basenames = Counter(document.rsplit("/", 1)[-1] for document, _, _ in places)
    return "; ".join(_place(document, page, sheet, basenames[document.rsplit("/", 1)[-1]] > 1)
                     for document, page, sheet in places)


# kept for any external code still importing the old private name
_where = where


def _deciding(qualifying: Sequence[Mention]) -> Mention:
    """Prefer a passage with list or sole-source wording as the one to cite — a casual mention
    naming AME's own product elsewhere (a programming tool, say) is not the approved list (M11)."""
    return (next((m for m in qualifying if m.is_list or m.sole_for), None)
            or next((m for m in qualifying if m.ours), None)
            or qualifying[0])


def _judge(mentions: Sequence[Mention], others: tuple[str, ...]) -> tuple[str, str]:
    qualifying = [m for m in mentions if m.ours or m.listed]
    # Another manufacturer sole-sourced in its own sentence — list wording no longer excuses it
    # (N3): "Acceptable manufacturers: 1. Siemens. No substitutions." blocks. D2/D6: the wording
    # is bound to the specific name in its own sentence (or clause), so a sole-source clause about
    # something else nearby (cable, rooftop units) never lands on a controls manufacturer it never
    # named, and one that lands on AME's own line is never misread as requiring a competitor.
    sole_blocking = [m for m in mentions if m.sole_for]
    # "Basis of design: Siemens, or approved equal" is a softer contrary requirement — it doesn't
    # rule AME out on its own, but it keeps a would-be Qualifies from winning outright. Exempt only
    # when the very same passage is a formal list that also names one of AME's own lines — AME's
    # own line being on that list is what the exemption is for (26-0334's "Vykon (Basis of Design)
    # ... Honeywell (WEBS) ... Johnson Controls (FX) ... Niagara N4 based ... are acceptable").
    basis_blocking = [m for m in mentions if m.basis_for and not (m.is_list and m.ours)]
    # The passage calls one of AME's own lines unacceptable outright, in its own sentence.
    unacceptable_blocking = [m for m in mentions if m.rejected_ours]
    contrary = sole_blocking or basis_blocking or unacceptable_blocking
    # Whether an AME line was named anywhere at all, qualifying or not — this is what keeps a
    # sole-source clause for another manufacturer from reading as "Does not qualify" when Honeywell
    # or Johnson Controls also turns up somewhere, even off an approved list (B1b/B1c).
    ame_named_anywhere = any(m.ours or m.listed or m.passing for m in mentions)

    if qualifying and contrary:
        first = _deciding(qualifying)
        name = ", ".join(first.ours or first.listed)
        against = sole_blocking[0] if sole_blocking else (unacceptable_blocking[0] if unacceptable_blocking else basis_blocking[0])
        if against in sole_blocking:
            clause = f"also requires {', '.join(against.sole_for)} with no substitutions"
        elif against in unacceptable_blocking:
            clause = (f"also calls {', '.join(against.rejected_ours)} unacceptable, requiring "
                      f"{', '.join(against.others)} instead" if against.others
                      else f"also calls {', '.join(against.rejected_ours)} unacceptable")
        else:
            clause = f"also names {', '.join(against.basis_for)} as the basis of design, or approved equal"
        return ("Open", f"The spec says two different things: it names {name} ({where(first)}) but {clause} "
                        f"({where(against)}). The US team decides.")
    if qualifying:
        first = _deciding(qualifying)
        if first.ours:
            return "Qualifies", f"The spec names {', '.join(first.ours)} ({where(first)})."
        verb = "is" if len(first.listed) == 1 else "are"
        return "Qualifies", f"{' and '.join(first.listed)} {verb} on the spec's list of acceptable manufacturers ({where(first)})."
    if sole_blocking and not ame_named_anywhere:
        # Does not qualify only for explicit sole-source wording for another manufacturer, with no
        # AME line named anywhere — the principle's one exception to "the US team decides".
        first = sole_blocking[0]
        return ("Does not qualify", f"The spec requires {', '.join(first.sole_for)} with no substitutions "
                                    f"({where(first)}). The US team decides.")
    if sole_blocking:
        first = sole_blocking[0]
        passing_names = sorted({name for m in mentions for name, _ in m.passing})
        extra = f" The spec also names {', '.join(passing_names)}, which is not a line AME bids." if passing_names else ""
        return ("Open", f"The spec requires {', '.join(first.sole_for)} with no substitutions ({where(first)})."
                        f"{extra} The US team decides.")
    if unacceptable_blocking:
        first = unacceptable_blocking[0]
        if first.others:
            return ("Open", f"The spec calls {', '.join(first.rejected_ours)} unacceptable and requires "
                            f"{', '.join(first.others)} instead ({where(first)}). The US team decides.")
        return ("Open", f"The spec calls {', '.join(first.rejected_ours)} unacceptable ({where(first)})."
                        f" The US team decides.")
    if basis_blocking:
        first = basis_blocking[0]
        return ("Open", f"The spec names {', '.join(first.basis_for)} as the basis of design, or approved equal "
                        f"({where(first)}). The US team decides.")
    # I9: Honeywell/Johnson Controls named — with or without sole-source wording — but never on a
    # real approved-manufacturers list: worth showing, never enough to qualify on its own.
    passing_only = [m for m in mentions if m.passing and not m.ours and not m.listed and not m.others]
    if passing_only:
        first = passing_only[0]
        names = ', '.join(name for name, _ in first.passing)
        verb = "is" if len(first.passing) == 1 else "are"
        return ("Open", f"The spec requires {names}, which {verb} not a line AME bids ({where(first)})."
                        f" The US team decides.")
    if others:
        return "Open", f"The spec names {', '.join(others)}, and none of the lines AME bids ({where(mentions[0])}). The US team decides."
    return "Open", "The spec names no controls manufacturer at all. The US team decides."
