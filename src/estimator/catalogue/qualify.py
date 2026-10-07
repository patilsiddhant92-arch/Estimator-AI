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

# D7: Rockwell/Allen-Bradley and Schneider make plenty of things that are not controls systems
# (motor starters, medium-voltage switchgear) — they count as controls manufacturers only in a
# sentence that also carries a BMS/BAS/PLC/DDC/building-automation word of its own.
PLC_GATED_OTHERS = {"Rockwell Automation (Allen-Bradley)", "Schneider Electric"}

# D3: before any "Does not qualify", every page of every document is searched for one of AME's
# lines, unfiltered by controls context — an addendum item or pre-bid answer with no controls word
# of its own still counts, where the ordinary controls-context gate in _mentions would drop it.
_AME_ANYWHERE = re.compile(r"\bWEBs(?:[- ]?N4)?\b|\bWEBStation\b|\bNiagara\b|\bTridium\b|\bJACE\b|"
                           r"\bJohnson\s+Controls\b[^\n]{0,60}?\bFX\b|\bFacility\s+Explorer\b|\bHoneywell\b", re.I)
_QUOTE_REACH = 150   # characters either side of the match, for the quote cited alongside it

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


# D5/item 6: what to call a components list when a name is only ever named on one — "on a sensor
# list", not the generic "not WEBs"/"not FX" note, and never worded as though it were a
# requirement ("names Honeywell", never "requires Honeywell").
_COMPONENT_CATEGORIES = (
    ("power meter", re.compile(r"power\s+meters?", re.I)),
    ("sensor", re.compile(r"sensors?", re.I)),
    ("transmitter", re.compile(r"transmitters?", re.I)),
    ("valve", re.compile(r"valves?", re.I)),
    ("damper", re.compile(r"dampers?", re.I)),
    ("actuator", re.compile(r"actuators?", re.I)),
    ("meter", re.compile(r"meters?", re.I)),
    ("wire and cable", re.compile(r"\bwire\b|\bcable\b", re.I)),
    ("access control", re.compile(r"access\s+control", re.I)),
    ("card reader", re.compile(r"card\s+readers?", re.I)),
    ("security", re.compile(r"\bsecurity\b", re.I)),
    ("video", re.compile(r"\bvideo\b", re.I)),
    ("intrusion", re.compile(r"intrusion", re.I)),
    ("fire alarm", re.compile(r"fire\s+alarm", re.I)),
)


def _component_category(line: str) -> str:
    return next((name for name, pattern in _COMPONENT_CATEGORIES if pattern.search(line)), "component")


def _heading_kind(text: str, pos: int, reading: "ReadingList") -> tuple[str | None, str | None]:
    """The nearest article or list heading above a position (D1, item 3): a components list
    (sensors, valves, cable, access control, security...) is never evidence for Qualifies, even
    inside a controls section — only a heading about the control system itself is, or a bare
    "acceptable manufacturers" heading with no component word of its own. Scans every line above,
    not just the nearest one: a components article's own heading ("2.5 SENSORS") governs even when
    a plain list-introducing line ("Manufacturers: one of the following:") sits closer to the
    names — a component word anywhere above always wins, since the principle's bias is against a
    false Qualifies. Returns (kind, the governing line), the line given so a "component" kind can
    say which one."""
    lines = [line for line in text[:pos].split("\n") if line.strip()]
    component = next((line for line in reversed(lines) if reading.component_heading_words.search(line)), None)
    if component is not None:
        return "component", component
    system = next((line for line in reversed(lines) if reading.system_heading_words.search(line)), None)
    if system is not None:
        return "system", system
    generic = next((line for line in reversed(lines) if reading.list_words.search(line)), None)
    if generic is not None:
        return "generic_list", generic
    return None, None


def _list_eligible(named: Named, passage: str, reading: "ReadingList") -> bool:
    """A name counts toward Qualifies from at least one occurrence whose governing heading is
    about the control system itself (or unclear) — never one where every occurrence sits only
    under a components heading."""
    return any(_heading_kind(passage, match.start(), reading)[0] != "component"
              for pattern in named.patterns for match in pattern.finditer(passage))


def _component_note(named: Named, passage: str, reading: "ReadingList") -> str | None:
    """When a name is only ever found under a components heading, the category to name it by
    ("on a sensor list") — None when at least one occurrence isn't (it keeps its usual note)."""
    kinds = [_heading_kind(passage, match.start(), reading)
            for pattern in named.patterns for match in pattern.finditer(passage)]
    if kinds and all(kind == "component" for kind, _ in kinds):
        return f"on a {_component_category(kinds[0][1])} list"
    return None


def _plc_context_eligible(named: Named, passage: str, sentence_bounds: list[int], reading: "ReadingList") -> bool:
    """Rockwell/Allen-Bradley and Schneider only count as controls manufacturers in a sentence
    that also carries a BMS/BAS/PLC/DDC/building-automation word of its own (D7) — otherwise
    they're just motor starters or switchgear, named for something else entirely."""
    if named.name not in PLC_GATED_OTHERS:
        return True
    for pattern in named.patterns:
        for match in pattern.finditer(passage):
            s_lo, s_hi = _span_at(sentence_bounds, match.start(), match.end())
            if reading.plc_context_words.search(passage[s_lo:s_hi]):
                return True
    return False


def _bind(bindable: list[tuple[int, int, str]], start: int, end: int,
         sentence_bounds: list[int], clause_bounds: list[int]) -> list[str]:
    """Which name(s) a sole-source/basis-of-design/rejection phrase belongs to: whichever
    manufacturer's name shares its sentence; failing that, a bare fragment ("No substitutions.")
    still binds to the name in the sentence immediately before it, provided that sentence is in
    the same clause — never reaching back further, across other sentences about something else
    entirely, to a name several sentences earlier in a long unlettered paragraph."""
    s_lo, s_hi = _span_at(sentence_bounds, start, end)
    in_sentence = sorted({n for a, b, n in bindable if s_lo <= a < s_hi})
    if in_sentence:
        return in_sentence
    c_lo, _ = _span_at(clause_bounds, start, end)
    if s_lo <= c_lo:
        return []   # the trigger's sentence opens its clause — no earlier sentence here to bind to
    index = bisect.bisect_left(sentence_bounds, s_lo)
    prev_lo = sentence_bounds[index - 1]
    if prev_lo < c_lo:
        return []   # the previous sentence belongs to an earlier clause
    in_previous = sorted({n for a, b, n in bindable if prev_lo <= a < s_lo})
    # A bare fragment can only sensibly continue a single antecedent — when the sentence before it
    # names several different manufacturers (a list of alternatives), which one it means is
    # genuinely ambiguous, so it binds to none of them rather than all of them.
    return in_previous if len(in_previous) == 1 else []


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
    requires_words: re.Pattern
    system_heading_words: re.Pattern
    component_heading_words: re.Pattern
    plc_context_words: re.Pattern

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
                   words("not_controls_words"), words("unacceptable_words"), words("requires_words"),
                   words("system_heading_words"), words("component_heading_words"), words("plc_context_words"))

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

    def is_ebi_shadowed(self, name: str, passage: str) -> bool:
        """Honeywell never counts on a list when the passage limits it to EBI (Enterprise
        Buildings Integrator, not the WEBs line AME bids) — "Honeywell (EBI only...)" is an AME
        line with a limit, so it stays uncertain rather than qualifying (A18)."""
        if name != "Honeywell":
            return False
        webs = next((n for n in self.ours if n.name == "Honeywell WEBs"), None)
        return bool(re.search(r"\bEBI\b", passage) and not (webs and webs.found_in(passage)))


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
    requires_for: tuple[str, ...] = ()   # other manufacturer(s) required as the system ("shall be", D1)
    in_context: bool = False            # a genuine controls section or controls-sheet, not a passing mention (D5)

    @property
    def named(self) -> str:
        """The "Manufacturers named" column: AME's own lines marked, so they aren't mistaken
        for another manufacturer's (M10)."""
        parts = [f"{n} (a line AME bids)" for n in self.ours]
        parts += list(self.listed)
        parts += list(self.others)
        parts += [f"{n} ({note})" if note.startswith("on a ") else f"{n} (not on a list, {note})"
                 for n, note in self.passing]
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
    finding, reason = _judge(mentions, others, _ame_anywhere(pages))
    if not controls:
        if has_spec_book:
            reason += (" The specs have no controls section (23 09 xx, 159xx or Division 25) — the whole spec, "
                       "plus the drawings' notes and spec sheets, was searched.")
        else:
            reason += (" No spec book was found among the bid documents; the drawings' notes and spec sheets "
                       "were searched.")
    # by (document, page): page 2 of two documents is two pages, each named with its document (RD-14)
    unread: dict[str, set[int]] = {}
    for r in pages:
        if r.status == "unreadable" and sheets.get((r.document, r.page)) is None:
            unread.setdefault(r.document, set()).add(r.page)
    if unread:
        total = sum(len(on) for on in unread.values())
        word = "page" if total == 1 else "pages"
        where = [(f"{'page' if len(on) == 1 else 'pages'} {_page_ranges(sorted(on))}", document.rsplit("/", 1)[-1])
                 for document, on in unread.items()]
        if len(where) == 1:
            listed = f" ({where[0][0]}) in {where[0][1]}"
        else:
            listed = ": " + ", ".join(f"{on} of {name}" for on, name in where)
        reason += f" {total} {word} of the specs could not be read{listed} — the check could not see them."
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


def _ame_anywhere(pages: Sequence[PageRecord]) -> str | None:
    """Every page of every document, unfiltered — an AME line found here, however it's worded or
    wherever it sits, quoted alongside where it turned up (D3)."""
    for record in pages:
        match = _AME_ANYWHERE.search(record.text)
        if match:
            start = record.text.rfind("\n", 0, max(0, match.start() - _QUOTE_REACH)) + 1
            end = record.text.find("\n", min(len(record.text), match.end() + _QUOTE_REACH))
            quote = " ".join(record.text[start:len(record.text) if end == -1 else end].split())
            return f"{_place(record.document, record.page, None, False)}: \"{quote}\""
    return None


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


_CONTROLS_SCHEDULE_PREFIXES = ("TC", "IC", "BMS", "BAS", "ATC")


def _mentions(record: PageRecord, text: str, controls: Sequence[SpecSection], sheet: Sheet | None,
             reading: ReadingList) -> list[Mention]:
    # A sheet typed Schedules never carries the controls system's own scope (N6) — the equipment
    # maker and a "BASIS OF DESIGN" column on a fan-coil or unit-heater schedule are not the
    # controls system. But a schedule that is itself a controls schedule — its discipline is
    # Controls, or its sheet number starts TC, IC, BMS, BAS or ATC — still counts (D4): dropping
    # every Schedules-typed sheet let a TC- control-schedule sole-source clause go unseen.
    if (sheet is not None and "Schedules" in sheet.types and sheet.discipline != "Controls"
       and not (sheet.number or "").startswith(_CONTROLS_SCHEDULE_PREFIXES)):
        return []
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
        # An AME line named with a limit ("Honeywell (EBI only...)") stays uncertain rather than
        # qualifying outright — it falls to "named in passing" like any other unlisted mention,
        # never simply vanishing (A18). A name that only ever turns up under a components heading
        # (sensors, valves, cable, access control...) is never list evidence either, even inside a
        # controls section (D1, item 3) — a heading or article about the control system itself is
        # what the list must be about, not the parts that hang off it.
        listed = tuple(n.name for n in approved if not reading.is_ebi_shadowed(n.name, passage)
                       and _list_eligible(n, passage, reading)) if is_list else ()
        # Honeywell or Johnson Controls named outside a list — or on a list that turned out not to
        # be an approved-manufacturers list at all — is never one of AME's own lines, but it's
        # still worth recording, "named in passing", rather than vanishing without a trace (I9).
        # When it's only ever named on a components list, say which kind (D5, item 6).
        passing = tuple((n.name, _component_note(n, passage, reading) or n.note)
                        for n in approved if n.name not in listed)
        sentence_bounds = _sentence_boundaries(passage)
        # Rockwell/Allen-Bradley and Schneider are named for all sorts of things besides a
        # controls system (motor starters, medium-voltage switchgear) — they only count as
        # "other controls manufacturers" in a sentence that also carries its own BMS/BAS/PLC/DDC/
        # building-automation word (D7).
        others = tuple(n.name for n in reading.others
                       if n.found_in(passage) and _plc_context_eligible(n, passage, sentence_bounds, reading))
        # D2/D6: sole-source, basis-of-design and rejection wording only count for the specific
        # manufacturer named in the same sentence (or, for a bare fragment like "No substitutions.",
        # the nearest name still in the same clause) — never for whichever name merely sits
        # somewhere in the same 350-character passage.
        bindable = _name_occurrences(reading.ours, passage) + _name_occurrences(reading.others, passage)
        clause_bounds = _clause_boundaries(passage)
        own_names, other_names = set(ours), set(others)
        # A genuine controls section, or a genuinely spec-like sheet (typed Specifications or
        # Control diagrams), is already read on its own terms — everywhere else, including a
        # Notes-and-legends or Network-riser sheet that's merely promoted for reachability, a bare
        # "shall be <maker>", sole-source or basis-of-design phrase counts against Qualifies only
        # when its own sentence is plainly about the control system (a BMS/BAS/DDC/building-
        # automation word, or the literal word "system"), not whichever equipment happens to sit
        # in the same 350-character window (D1: A8's Trane rooftop units on an M- notes sheet,
        # A11's Siemens switchboards on an E- sheet, each reached only through a nearby "BMS"/"DDC"
        # two sentences later).
        system_context = in_controls_section or (sheet is not None and sheet.discipline in CONTROLS_SHEET_DISCIPLINES
                                                 and any(t in sheet.types for t in ("Specifications", "Control diagrams")))

        def _about_the_system(start: int, end: int) -> bool:
            s_lo, s_hi = _span_at(sentence_bounds, start, end)
            sentence = passage[s_lo:s_hi]
            # A sentence naming several manufacturers as alternatives ("Sensor models shall be
            # Distech..., JCI... or Schneider... or approved equal") is a components list, not a
            # requirement for any one of them — whatever section it sits in. Only a sentence that
            # names a single candidate can be a genuine requirement for the system.
            if len({n.name for n in reading.all_names() if n.found_in(sentence)}) > 1:
                return False
            if system_context:
                return True
            return bool(reading.controls_words.search(sentence) or re.search(r"\bsystem\b", sentence, re.I))

        sole_for, basis_for, rejected_ours, requires_for = set(), set(), set(), set()
        for pattern, bucket, eligible, gated in ((reading.sole_words, sole_for, other_names, True),
                                                 (reading.basis_words, basis_for, other_names, True),
                                                 (reading.unacceptable_words, rejected_ours, own_names, False),
                                                 (reading.requires_words, requires_for, other_names, True)):
            for match in pattern.finditer(passage):
                if gated and not _about_the_system(match.start(), match.end()):
                    continue
                for name in _bind(bindable, match.start(), match.end(), sentence_bounds, clause_bounds):
                    if name in eligible:
                        bucket.add(name)
        if ours or listed or others or passing:
            found.append(Mention(document=record.document, page=record.page,
                                 quote=" ".join(passage.split()), ours=ours, listed=listed, others=others,
                                 sheet=sheet.number if sheet is not None else None,
                                 passing=passing, is_list=is_list,
                                 sole_for=tuple(sorted(sole_for)), basis_for=tuple(sorted(basis_for)),
                                 rejected_ours=tuple(sorted(rejected_ours)),
                                 requires_for=tuple(sorted(requires_for)), in_context=system_context))
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
    return (next((m for m in qualifying if m.is_list or m.sole_for or m.requires_for), None)
            or next((m for m in qualifying if m.ours), None)
            or qualifying[0])


def _deciding_other(candidates: Sequence[Mention]) -> Mention:
    """Prefer the passage that names a maker for the control system itself as the one to cite: a
    genuine controls section or controls-sheet passage, or one with list, sole-source or "shall
    be" wording, over a passing mention elsewhere (D5: 26-0352 cites M-601.00's Distech, not
    M-600.00's motor starters)."""
    signal = lambda m: m.is_list or m.sole_for or m.requires_for or m.basis_for
    return (next((m for m in candidates if m.in_context and signal(m)), None)
            or next((m for m in candidates if m.in_context), None)
            or next((m for m in candidates if signal(m)), None)
            or candidates[0])


def _judge(mentions: Sequence[Mention], others: tuple[str, ...], ame_anywhere: str | None = None) -> tuple[str, str]:
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
    # A plain requirement for another maker's system — "The BAS shall be Automated Logic WebCTRL",
    # "an extension of the existing Johnson Controls Metasys system" — counts against a Qualifies
    # too, whatever the wording, even with no sole-source phrase at all (D1). It never on its own
    # produces Does not qualify — only explicit sole-source wording does that.
    requires_blocking = [m for m in mentions if m.requires_for]
    contrary = sole_blocking or basis_blocking or unacceptable_blocking or requires_blocking
    # Whether an AME line was named anywhere at all, qualifying or not — this is what keeps a
    # sole-source clause for another manufacturer from reading as "Does not qualify" when Honeywell
    # or Johnson Controls also turns up somewhere, even off an approved list (B1b/B1c). D3: this
    # also covers a page the controls-context filter dropped entirely — an addendum item or
    # pre-bid answer naming an AME line with no controls word of its own still counts.
    ame_named_anywhere = any(m.ours or m.listed or m.passing for m in mentions) or ame_anywhere is not None

    if qualifying and contrary:
        first = _deciding(qualifying)
        name = ", ".join(first.ours or first.listed)
        against = (sole_blocking[0] if sole_blocking
                  else unacceptable_blocking[0] if unacceptable_blocking
                  else basis_blocking[0] if basis_blocking else requires_blocking[0])
        if against in sole_blocking:
            clause = f"also requires {', '.join(against.sole_for)} with no substitutions"
        elif against in unacceptable_blocking:
            clause = (f"also calls {', '.join(against.rejected_ours)} unacceptable, requiring "
                      f"{', '.join(against.others)} instead" if against.others
                      else f"also calls {', '.join(against.rejected_ours)} unacceptable")
        elif against in basis_blocking:
            clause = f"also names {', '.join(against.basis_for)} as the basis of design, or approved equal"
        else:
            clause = f"also requires {', '.join(against.requires_for)} for the system"
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
        if passing_names:
            extra = f" The spec also names {', '.join(passing_names)}, which is not a line AME bids."
        elif ame_anywhere is not None:
            extra = f" An AME line also turns up elsewhere in the documents, at {ame_anywhere}."
        else:
            extra = ""
        return ("Open", f"The spec requires {', '.join(first.sole_for)} with no substitutions ({where(first)})."
                        f"{extra} The US team decides.")
    if requires_blocking:
        # Never Does not qualify on its own — a bare "shall be <maker>" is a real requirement to
        # flag, but not the explicit sole-source wording the principle reserves that for.
        first = requires_blocking[0]
        passing_names = sorted({name for m in mentions for name, _ in m.passing})
        extra = f" The spec also names {', '.join(passing_names)}, which is not a line AME bids." if passing_names else ""
        return ("Open", f"The spec requires {', '.join(first.requires_for)} for the system ({where(first)})."
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
    # real approved-manufacturers list: worth showing, never enough to qualify on its own. D5/item
    # 6: worded as a plain mention, never as a requirement — "names Honeywell (on a sensor list)".
    passing_only = [m for m in mentions if m.passing and not m.ours and not m.listed and not m.others]
    if passing_only:
        first = next((m for m in passing_only if m.in_context), None) or passing_only[0]
        names = ', '.join(f"{name} ({note})" if note else name for name, note in first.passing)
        verb = "is" if len(first.passing) == 1 else "are"
        return ("Open", f"The spec names {names}, which {verb} not a line AME bids ({where(first)})."
                        f" The US team decides.")
    if others:
        # Don't say "none of the lines AME bids" when an AME line was in fact named somewhere —
        # just not in this same passage (A3).
        first = _deciding_other([m for m in mentions if m.others])
        if ame_named_anywhere:
            return ("Open", f"The spec names {', '.join(others)} ({where(first)})."
                            f" An AME line is also named elsewhere in the documents. The US team decides.")
        return "Open", f"The spec names {', '.join(others)}, and none of the lines AME bids ({where(first)}). The US team decides."
    return "Open", "The spec names no controls manufacturer at all. The US team decides."
