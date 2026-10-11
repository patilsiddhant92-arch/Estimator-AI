"""The equipment inventory: every tag in exactly one of the estimator's categories, by the
quantity rules (`D:\\Estimation Assistant\\Brain\\Quantity rules.txt`).

The schedule is the source of quantities. The other drawing sheets check it and never change
the count without saying so. A count that can't be read is None and PENDING, never a silent 1.

A schedule row whose tag is really a type (AC-3.0, GCF-A labelled nine times on one plan, a
schedule with a QUANTITY column) stands for several units: its quantity is the schedule's
QUANTITY column, else its labels on the plan sheets times each sheet's floors, else PENDING.

Plan sheets that show the same floor and area (a ductwork plan and a piping plan of one floor) are one plan: they
are not added together (lead ruling L1). When that makes a count lower than the sheets add up to, the item, the
family total and `Placements` keep the higher number in `summed`, and the item's reason, the family's flag and the
dossier's counts line say both. (The proposal's "*" quantity note names the family total's `summed` too: the planner
keeps it in `Count.added_up` (`bms.plan_read.Reader._total_sum`), apart from the Count's others, because
`Count.highest()` prints the highest number.)
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass, field, replace
from functools import lru_cache

from estimator.catalogue.job import (CONTROLS_DISCIPLINES, GENERIC_PLAN_WORDS, PLAN_DISCIPLINE_WORDS, TRADE_SYNONYMS,
                                     TRADE_WORDS, repeats, title_without_number, title_words)
from estimator.catalogue.sheet_types import is_demolition, work_words
from estimator.catalogue.tags import (DECIMAL_TYPE, Equipment, is_type_tag, label_key, label_keys, line_labels,
                                      plan_labels, tag_prefix)
from estimator.reading.revisions import governing_pages, typical_places
from estimator.reading.schedules import (BY_EYE, EQUIPMENT, Schedule, expand_tags, header_key, kind_from_title,
                                        quantity_header, vocabulary)

ON_PLANS = "CONFIRMED-on-plans"   # a tag series the trade plans show, on no readable schedule: priced, "check"
ON_PLANS_WHY = "not on a readable schedule — counted from the plans, check"
COUNTED = ("CONFIRMED", "MISSING", "DISCREPANCY", ON_PLANS)
TRADE_DISCIPLINES = ("Mechanical", "Controls", "Plumbing")
FROM_TEXT = "counted from the schedule sheet's text; the table itself couldn't be read — check the count"
READ_BY_EYE = "read by eye from a picture of the schedule — check the count"
TYPE_PLACED = 3        # labels on the plans (floors counted) that make a scheduled tag a type ...
TYPE_ON_ONE_SHEET = 4  # ... when one sheet alone holds this many (floors counted): a unit's tag can sit by its
                       # symbol and by its thermostat too (26-0478's UH-1, three times on H101)
# The dossier's counts line names, in the head the ledger quotes, why a family's plan placements are above every
# other count; the renderer reads these words back to print the Playbook's client wording for each cause
# (wording.json "count_causes"). Keep them free of the count labels' words (riser, schedule, picture).
COUNT_CAUSES_LEAD = "placements above the other counts, likely:"
# ("same plan as" and "one unit's tag on several plans" are retired, FINAL-H: a cause never says that sheets are one
# plan (ruling L1 counts the sheets of one floor and area once, and only the reading notes and the '*' note say so),
# and a unit's tag counts once on each plan since FINAL-G, so neither can be said)
COUNT_CAUSE_WORDS = {"typical": "a typical unit at each place",
                     "labelled_twice": "one unit labelled more than once"}
# (`is_type_tag` and the one label reader, `label_keys` / `line_labels`, live in estimator.catalogue.tags since
# FINAL-K, so the copy test in estimator.catalogue.job reads labels the same way; they are imported here unchanged)


def counted_per_place(tag: str, places: int, most_on_one_sheet: int, code: bool = False) -> bool:
    """Whether a tag's plan placements count every place it is drawn (summed over the sheets, never merged) rather
    than once for the unit (lead ruling, FINAL-G): a type's tag (`is_type_tag`), a schedule's type code (`code`),
    and a numbered tag drawn as a type is (TYPE_PLACED labels over the sheets and TYPE_ON_ONE_SHEET of them on one
    sheet), so a numbered type is never cut to one. `places` and `most_on_one_sheet` are the labels as drawn, the
    floors of a typical sheet NOT applied: those floors multiply a unit's tag, they never make it a type (a unit on
    a typical floor drawn twice would otherwise be summed, doubled)."""
    return (code or is_type_tag(tag)
            or (places >= TYPE_PLACED and most_on_one_sheet >= TYPE_ON_ONE_SHEET))
_A_TYPE = "A type, not one unit"
_RISER = re.compile(r"\bRISERS?\b", re.I)


@dataclass(frozen=True)
class InventoryItem:
    tag: str                   # the unit's tag; on a TYPE ONLY row, "Type-only: " and the schedule's title
    kind: str                  # from equipment.json; "" on a TYPE ONLY row
    category: str              # CONFIRMED | DISCREPANCY | EXTRA | MISSING | ORPHANED | EXISTING | TYPE ONLY | PENDING
    quantity: int | None       # 1 per scheduled tag; None when it can't be counted yet
    schedule: str | None       # "M-601 VAV BOX SCHEDULE"
    seen_on: tuple[str, ...]   # other sheets it appears on (from TagEntry.elsewhere)
    reason: str                # plain words
    action: str                # "" | "confirm" | "include pending" | "exclude pending"
    types: tuple[str, ...] = ()   # a TYPE ONLY row's type codes ("CD", "EG"); empty on every other row
    summed: int | None = None     # ruling L1: what `quantity` would be if the plan sheets of one floor and area were
                                  # added up, set only when that is above `quantity` (the reason says both numbers)
    summed_on: tuple[str, ...] = ()   # the plan sheets `summed` adds up (set with `summed`), for the family's flag


@dataclass(frozen=True)
class FamilyTotal:
    kind: str                  # "Variable Air Volume Box"
    prefix: str                # "VAV"
    scheduled: int             # confirmed + missing + discrepancy (a duplicate counted once and flagged)
    tags: str                  # "VAV-101 thru VAV-112, VAV-114"
    flags: tuple[str, ...]
    summed: int | None = None  # ruling L1: `scheduled` if the plan sheets of one floor and area were added up; set only
                               # when above `scheduled` (a flag of the family says both numbers)


def _natural(tag: str) -> list:
    return [(0, int(part), "") if part.isdigit() else (1, 0, part) for part in re.split(r"(\d+)", tag)]


def _name(document: str) -> str:
    return document.rsplit("/", 1)[-1]


def _place(schedule: Schedule) -> str:
    return schedule.sheet or f"{_name(schedule.document)} p.{schedule.page}"


def _label(schedule: Schedule) -> str:
    return f"{schedule.sheet} {schedule.title}" if schedule.sheet else f"{_place(schedule)} {schedule.title}"


def _list(places, limit: int = 6) -> str:
    places = list(places)
    return ", ".join(places[:limit]) + (" …" if len(places) > limit else "")


def _sheets(n: int) -> str:
    return "1 other drawing sheet" if n == 1 else f"{n} other drawing sheets"


def _names(sheets) -> str:
    """"M-201", "M-201 and M-301", "M-201, M-301 and M-401"."""
    sheets = list(sheets)
    return sheets[0] if len(sheets) == 1 else ", ".join(sheets[:-1]) + f" and {sheets[-1]}"


def compact_tags(tags) -> str:
    """Runs of three or more consecutive tags shown as "VAV-101 thru VAV-112"."""
    parts: list[str] = []
    run: list[tuple[str, int, int, str, str]] = []

    def close():
        if len(run) >= 3:
            parts.append(f"{run[0][3]} thru {run[-1][3]}")
        else:
            parts.extend(r[3] for r in run)
        run.clear()

    for tag in tags:
        m = re.match(r"^(.*?)(\d+)$", tag)
        if not m:
            close()
            parts.append(tag)
            continue
        stem, digits = m.groups()
        width = len(digits) if digits.startswith("0") else 0
        # CDU09 → CDU10 runs on (same width); VAV-9 → VAV-10 too (neither padded); VAV-9 → VAV-010 doesn't
        same_width = run and (len(run[-1][4]) == len(digits) or not (run[-1][1] or width))
        if run and not (run[-1][0] == stem and same_width and run[-1][2] + 1 == int(digits)):
            close()
        run.append((stem, width, int(digits), tag, digits))
    close()
    return ", ".join(parts)


def _one_copy_per_sheet(schedules: list[Schedule], flags: list[str] | None = None,
                        copies: Collection[tuple[str, str]] = ()) -> list[Schedule]:
    """The schedules come from the governing pages (`governing_pages`), which keep both documents' pages whenever
    nothing proves one replaces the other: a sheet number read from two documents is counted from both (RD-1, never
    the first document's alone). Only a sheet of a marked-up copy of the set (`copies`, (number, document) from
    `repeats`) is read once, from the original; each such sheet whose schedules are set aside is said in `flags`,
    with the rows set aside and the rows counted from the other documents."""
    kept = [s for s in schedules if (s.sheet, s.document) not in copies]
    if flags is not None:
        dropped: dict[tuple[str, str], list[Schedule]] = defaultdict(list)
        for s in schedules:
            if (s.sheet, s.document) in copies:
                dropped[(s.sheet, s.document)].append(s)
        for (sheet, document), set_aside in dropped.items():
            rows = sum(1 for s in set_aside for r in s.rows if r.tag)
            counted = [s for s in kept if s.sheet == sheet]
            read = sum(1 for s in counted for r in s.rows if r.tag)
            what = "1 schedule" if len(set_aside) == 1 else f"{len(set_aside)} schedules"
            where = ", ".join(dict.fromkeys(_name(s.document) for s in counted)) or "no other document"
            flags.append(f"{what} on {sheet} in {_name(document)} not counted ({_rows(rows)}) — a marked-up copy of "
                         f"the set; {sheet} counted from {where} ({_rows(read)})")
    return kept


def _listed_where(listed: list[tuple[str, str]]) -> str:
    """Where a tag is listed: its schedule sheets ("M-601, M-602"), each named with its document when the listings
    come from more than one document ("M-601 in Mech.pdf, M-601 in Mech reissue.pdf")."""
    if len({document for _, document in listed}) < 2:
        return _list(dict.fromkeys(place for place, _ in listed))
    return _list(dict.fromkeys(place if _name(document) in place else f"{place} in {_name(document)}"
                               for place, document in listed))


def _rows(n: int) -> str:
    return "1 tagged row" if n == 1 else f"{n} tagged rows"


@dataclass(frozen=True)
class Placements:
    """Where one tag is labelled: a line of a sheet's text that is the tag alone ("GCF-A"), never a note that
    names it ("TO EUH-1"). Plan sheets of the trades that carry controls scope, each sheet (document, page) counted
    once. `count` is the one counting rule (`plan_count`, FINAL-I, ruling L1), the same the dossier's counts line
    uses; `per_place` says whether the tag counts at every place (`counted_per_place`, the labels as drawn). `total`
    is every label summed, floors applied, a cross-check only.

    Ruling L1: sheets that show the same floor and area (`plan_groups`) are not added. Where that makes `count`
    lower than the sheets added up, both numbers are here: `count` and `summed`, with the sheets named in
    `same_plan`, so the item's reason, the family's flag and the counts line can say them."""
    on_plans: dict[str, int]                 # plan sheet → labels on it
    floors: dict[str, int]                   # plan sheet → the floors it stands for (1 when not typical)
    on_risers: dict[str, int] = field(default_factory=dict)   # riser diagram → labels on it, a cross-check
    count: int = 0                           # the plans' count by `plan_count`
    per_place: bool = False                  # counted at every place (a type), not once per plan group
    each_place: int = 0                      # the plans' count as a type's (`plan_count` per place): the count of a
                                             # row the schedule calls a type (REVIEW-FINAL6 F1)
    summed: int = 0                          # `count` if every sheet were its own plan: the sheets added up (L1)
    each_place_summed: int = 0               # `each_place` likewise
    same_plan: tuple[tuple[str, ...], ...] = ()   # the sheets (by name) of each plan group that shows this tag on 2 or
                                                  # more of them: counted as one plan, not added (L1)
    demolition: dict[str, int] = field(default_factory=dict)   # demolition sheet -> labels on it, left out of every
                                                               # new-work count (ruling 1 of 2026-10-11, T-005a), for
                                                               # the Demolition Scope block
    demolition_work: str = ""    # the documents' line naming work on this demolition unit (`demolition_work`), "" if
                                 # none: printed beside it in the Demolition Scope, never added to the new-work count

    @property
    def drawn(self) -> int:
        """The labels as drawn, the floors of a typical sheet NOT applied."""
        return sum(self.on_plans.values())

    @property
    def total(self) -> int:
        return sum(n * self.floors.get(sheet, 1) for sheet, n in self.on_plans.items())

    @property
    def most_on_one_sheet(self) -> int:
        return max((n * self.floors.get(sheet, 1) for sheet, n in self.on_plans.items()), default=0)

    def plans_text(self) -> str:
        """ "M-101 4, M-113 1 × 10 floors, M-201 4": each sheet and its labels."""
        return ", ".join(f"{sheet} {n}" + (f" × {self.floors[sheet]} floors" if self.floors.get(sheet, 1) > 1 else "")
                         for sheet, n in self.on_plans.items())

    def risers_text(self) -> str:
        return ", ".join(f"{sheet} {n}" for sheet, n in self.on_risers.items())

    def same_plan_note(self, counted: int, summed: int) -> str:
        """The plain words for a count that ruling L1 lowered: which sheets count as one plan, and both numbers.
        "M-201 and M-301 show one floor and area, so each counts as one plan, not added: 1 counted, 2 if the sheets
        were added up"."""
        numbers = f"{counted} counted, {summed} if the sheets were added up"
        if not self.same_plan:
            return numbers
        if not self.per_place:     # ruling 2 of 2026-10-11: a numbered unit tag is one unit in the job
            shows = "; ".join(f"{_names(group)} show the same unit tag" for group in self.same_plan)
            return f"{shows}, one unit in the job, not added: {numbers}"
        shows = "; ".join(f"{_names(group)} show one floor and area" for group in self.same_plan)
        return f"{shows}, so each counts as one plan, not added: {numbers}"


# ---- the plan areas: a hint, and the floor and area a title names (the dossier's counts line) -----------
# Which sheets MAY show one plan is read here to name them in the counts line's reading notes (`plan_area_doubts`);
# the hint itself never lowers a count. The floor and area a title names (`_area_read`) is also one of the tests of
# `plan_groups`, which does group sheets: the same floor and area for other trades (ruling L1), or the same title
# words with a floor among them and repeated unit tags (FINAL-I).

_ORDINALS = {word: n for n, word in enumerate(
    ("FIRST", "SECOND", "THIRD", "FOURTH", "FIFTH", "SIXTH", "SEVENTH", "EIGHTH", "NINTH", "TENTH", "ELEVENTH",
     "TWELFTH"), start=1)}
_NUMBER_WORDS = {word: n for n, word in enumerate(
    ("ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT", "NINE", "TEN", "ELEVEN", "TWELVE"), start=1)}
_ORDINAL = "|".join(_ORDINALS) + r"|\d{1,3}(?:ST|ND|RD|TH)"
_NUMBER = "|".join(_NUMBER_WORDS)
_FLOOR_WORD = r"(?:FLOOR|FLR|LEVEL|LVL)"
_FLOOR_NAMED = re.compile(
    rf"\b(?:(?P<ordinal>{_ORDINAL})\s+{_FLOOR_WORD}\b"
    rf"|{_FLOOR_WORD}\s*(?P<number>(?:{_NUMBER})\b|[A-Z]?\d{{1,3}}[A-Z]?\b)"
    r"|L-?(?P<short>\d{1,2})\b"
    r"|(?P<named>SUB-?CELLAR|CELLAR|BASEMENT|GROUND(?:\s+(?:FLOOR|FLR|LEVEL|LVL))?|(?:LOWER|UPPER)\s+LEVEL"
    r"|MEZZANINE|PENTHOUSE|ROOF|ATTIC)\b)", re.I)
# a title naming several floors ("FIRST AND SECOND FLOOR PLAN", "LEVELS 2 THRU 5"): no one floor can be read
_FLOOR_LIST = re.compile(rf"\b(?:FLOORS|LEVELS|FLRS|LVLS)\b|\b(?:{_ORDINAL})\b", re.I)
_FLOOR_LIST_TAIL = re.compile(rf"^\s*(?:,|&|\+|/|-|–|AND|THRU|THROUGH|TO)\s*(?:\d|(?:{_NUMBER}|{_ORDINAL})\b)", re.I)
# the parts of a floor that must match: TOWER 1, UNIT 1A, AREA B, DORM WING, NORTH, the LOWER ROOF, 1 OF 2
_PART_WORD = r"(?:TOWER|UNIT|WING|BUILDING|BLDG|AREA|PART|ZONE|SECTOR|PHASE|BLOCK|POD|SHEET|ANNEX)"
_PART = re.compile(
    rf"\b(?P<word>{_PART_WORD})\s*[-#]?\s*(?P<id>(?:{_NUMBER})\b|[A-Z]?\d{{1,3}}[A-Z]?\b|[A-Z]{{1,2}}\b)"
    rf"|\b(?P<before>[A-Z][A-Z0-9]*)\s+(?P<named>WING|TOWER|BUILDING|BLDG|ANNEX|HALL|PAVILION)\b"
    rf"(?:\s*[-#]?\s*(?P<named_id>(?:{_NUMBER})\b|[A-Z]?\d{{1,3}}[A-Z]?\b|[A-Z]{{1,2}}\b))?"
    r"|\b(?P<alone>NORTH(?:EAST|WEST)?|SOUTH(?:EAST|WEST)?|EAST|WEST|LOWER|UPPER|ANNEX|ADDITION)\b"
    r"|\b(?P<roof>HIGH|LOW)(?=\s+ROOF\b)"
    r"|\b(?P<of>\d{1,2}\s+OF\s+\d{1,2})\b", re.I)
_NOT_A_PART = frozenset({"PLAN", "PLANS", "AND", "THE", "OF", "HVAC", "MECHANICAL", "PIPING", "DUCTWORK", "DUCT",
                         "CONTROLS", "CONTROL", "PLUMBING", "ELECTRICAL", "BAS", "BMS", "DDC", "TEMPERATURE"})
_ENLARGED = re.compile(r"\b(?:ENLARGED|PARTIAL)\b", re.I)
AREA_OVERLAP = 0.6       # share of the smaller sheet's unit tags another sheet must repeat to hint one plan
AREA_SHARED = 3          # and at least this many tags: two tags in common prove nothing


def _number(word: str) -> str:
    word = word.upper()
    return str(_NUMBER_WORDS.get(word) or _ORDINALS.get(word) or word.lstrip("0") or "0")


def _floor(m: re.Match) -> str:
    if m.group("ordinal"):
        word = m.group("ordinal").upper()
        return str(_ORDINALS.get(word) or int(re.match(r"\d+", word).group(0)))
    if m.group("number"):
        return _number(m.group("number"))
    if m.group("short"):
        return _number(m.group("short"))
    named = re.sub(r"\W+", " ", m.group("named").upper())
    return "GROUND" if named.startswith("GROUND") else named


def _parts(text: str) -> tuple[str, ...]:
    parts = set()
    for m in _PART.finditer(text):
        if m.group("word"):
            ident = m.group("id").upper()
            if ident in _NOT_A_PART:
                continue
            parts.add(f"{m.group('word').upper()} {_number(ident) if ident in _NUMBER_WORDS else ident}")
        elif m.group("named"):
            before = m.group("before").upper()
            ident = (m.group("named_id") or "").upper()
            ident = "" if ident in _NOT_A_PART else _number(ident) if ident in _NUMBER_WORDS else ident
            words = [w for w in (before if before not in _NOT_A_PART else "", m.group("named").upper(), ident) if w]
            parts.add(" ".join(words))
        else:
            parts.add(re.sub(r"\s+", " ", m.group(0).upper()))
    return tuple(sorted(parts))


def _area_read(title: str | None) -> tuple[tuple, tuple, str] | None:
    """(the floors a plan's title names, the parts of it, the rest of the title with the floor words taken out), or
    None when no one floor can be read (`_area_key`)."""
    title = (title or "").upper()
    if _ENLARGED.search(title):
        return None
    floors, rest, end = [], [], 0
    for m in _FLOOR_NAMED.finditer(title):
        if _FLOOR_LIST_TAIL.match(title[m.end():]):
            return None
        floors.append(_floor(m))
        rest.append(title[end:m.start()] + (" ROOF" if m.group("named") == "ROOF" else ""))   # HIGH ROOF a part
        end = m.end()
    rest.append(title[end:])
    rest_text = " ".join(rest)
    if not floors or _FLOOR_LIST.search(rest_text):
        return None
    return tuple(floors), _parts(rest_text), rest_text


def _area_key(title: str | None) -> tuple | None:
    """The floor (and the parts of it) a plan's title names: "HVAC PIPING AND CONTROLS FIRST FLOOR PLAN",
    "HVAC 1ST FLR PLAN" and "LEVEL ONE PLAN" are all floor 1; "FIRST FLOOR PLAN - TOWER 2" is floor 1 of TOWER 2.
    None when no one floor can be read: the title names none, names several ("FIRST AND SECOND FLOOR PLAN"), or
    names an enlarged or partial plan (one that repeats part of a floor)."""
    read = _area_read(title)
    return None if read is None else read[:2]


def _unit_tags(tags) -> set:
    """The tags that hint two sheets show one plan: unit tags (a unit number in them), each at fewer places on the
    sheet than a type is (a tag at many places is a typical one, on every floor alike), when the counts are given.
    A type's tag never hints it, however few its places (REVIEW-FINAL4 F2)."""
    counts = tags if hasattr(tags, "items") else dict.fromkeys(tags, 1)
    return {tag for tag, n in counts.items() if not is_type_tag(tag) and n < TYPE_ON_ONE_SHEET}


_without_number = title_without_number     # catalogue/job.py, shared with supersession (FINAL-O)


def _plain_title(sheet) -> str:
    """The title's words, its own sheet number taken out (`_without_number`)."""
    return " ".join(re.findall(r"[A-Z0-9]+", _without_number(sheet)))


def _same_tags(a: set, b: set) -> bool:
    shared = len(a & b)
    return shared >= AREA_SHARED and shared >= AREA_OVERLAP * min(len(a), len(b))


def plan_areas(plans) -> dict[tuple[str, int], int]:
    """Retired (FINAL-G): every plan sheet is its own area, (document, page) -> its own number, given (sheet, the
    tags on it) for each plan sheet. It merges no sheet; which sheets may show one plan is a hint
    (`plan_area_doubts`), and the sheets that are one plan are `plan_groups` (ruling L1). Kept so callers keep one
    signature. Pure."""
    found: dict[tuple[str, int], int] = {}
    for sheet, _tags in plans:
        found.setdefault((sheet.document, sheet.page), len(found))
    return found


# ---- the plan groups and the one counting rule (ruling L1 of 2026-10-10, after FINAL-I) -----------------
# Ruling L1: plan sheets that show the same floor and area are not added together. A ductwork plan, a zoning plan, a
# piping plan and a controls plan of one floor draw the same units, each for its own trade. They are one "plan
# group": each tag counts the most of any one of them (a unit's tag once), and the floors and areas then add up.
# Two plan sheets are one plan group when they are in one document, are not two pages of one sheet number, and
#   (1) their titles name the same one floor, the same parts of it and the same other words, and name other trades
#       (`_same_floor_and_area`): no tag evidence is needed, so a floor with two units on two sheets counts two; or
#   (2) as before (FINAL-I), their titles have the same words with a floor among them and they repeat each other's
#       unit tags.
# Every other sheet is its own group, and the groups add up: two sheets of one trade with the same title could be the
# two halves of a floor, so they need the tag evidence of (2). When a count is lower than its sheets add up to, both
# numbers stay in the data (`Placements.summed`) and are said in the item's reason, the family's flag and the counts
# line: a count that is too low is the worst error, so a drop is never silent. (The proposal's "*" quantity note
# names the family total's sum too: the planner keeps it in `Count.added_up`, apart from the Count's others, because a
# Count prints its highest number.) `inventory.placements` and the dossier's counts line both count with
# `plan_groups` and `plan_count`, so the Evidence Package and the proposal never disagree.

_TRADE_WORDS = TRADE_WORDS
_FLOOR_TOKEN = re.compile(
    rf"^(?:FLOORS?|FLRS?|LEVELS?|LVLS?|TYPICAL|TYP|BASEMENT|CELLAR|SUBCELLAR|GROUND|MEZZANINE|MEZZ|PENTHOUSE|ROOF|ATTIC"
    rf"|{_ORDINAL}|L\d{{1,2}}|\d{{1,3}})$")


def _title_tokens(sheet) -> tuple[str, ...]:
    """The title's words IN ORDER (`catalogue.job.title_words`: its own sheet number and the trade and plan words
    taken out). Comparing in order can only split groups, so it can only raise a count."""
    return title_words(sheet)


@lru_cache(maxsize=None)
def _place_facts(title: str) -> tuple[tuple | None, tuple[str, ...], frozenset[str]]:
    """What a plan sheet's title says of the place and the trade (ruling L1), its own sheet number already taken
    out of it (`title_without_number`, so upper case): (the floors and parts it names, None when no one floor can
    be read (`_area_read`); the other words that name the place or the kind of plan, in order: KITCHEN, DEMOLITION,
    NEW WORK; the trades it names: PIPING, CONTROLS, ZONING). HVAC, MECHANICAL and PLAN name no trade. Two words for
    one trade are one trade (`TRADE_SYNONYMS`: DUCT is DUCTWORK, BAS is CONTROLS)."""
    words = re.findall(r"[A-Z0-9]+", title)
    trades = frozenset(TRADE_SYNONYMS.get(w, w) for w in words
                       if w in PLAN_DISCIPLINE_WORDS and w not in GENERIC_PLAN_WORDS)
    read = _area_read(title)
    if read is None:
        return None, (), trades
    floors, parts, rest = read
    other = tuple(w for w in re.findall(r"[A-Z0-9]+", _PART.sub(" ", rest)) if w not in PLAN_DISCIPLINE_WORDS)
    return (floors, parts), other, trades


def _facts(sheet):
    return _place_facts(title_without_number(sheet))


def _same_floor_and_area(document: str, a_facts, b_facts, twins: Collection = ()) -> bool:
    """Ruling L1: two plan sheets of one document show the same floor and area when their titles name the same one
    floor (written however: "1ST FLOOR", "FIRST FLOOR", "LEVEL 1"), the same parts of it (TOWER A, EAST WING) and
    the same other words, and they name other trades (a ductwork plan and a piping plan, a zoning plan and a
    controls plan). Two sheets of one trade with one title could be two halves of a floor, or two buildings: they are
    not this, and a floor and area that has two of them (`twins`: its (document, floor and parts, other words)) is
    too uncertain to say which of them the other trades' sheets show, so none of its sheets is this either."""
    (a_area, a_other, a_trades), (b_area, b_other, b_trades) = a_facts, b_facts
    return (a_area is not None and a_area == b_area and a_other == b_other and a_trades != b_trades
            and (document, a_area, a_other) not in twins)


def _one_plan(a, a_tags, b, b_tags, codes: Collection[str], a_facts=None, b_facts=None,
              twins: Collection = ()) -> bool:
    """Two plan sheets show one plan: the same document, and either the same floor and area for other trades
    (`_same_floor_and_area`, ruling L1: no tag evidence needed), or the same title words (`_title_tokens`) with a
    floor among them (so BASEMENT 1 and BASEMENT 2, BLDG. A and BLDG. B, TOWERS 1 AND 2 and 3 AND 4 never are), and
    at least AREA_SHARED unit tags repeated, AREA_OVERLAP of the smaller sheet's (a type's tag is never evidence).
    Two pages of one sheet number never are: alike on every page they are one plan for several floors
    (`plan_floors`), else each page is its own sheet, counted (REVIEW-FINAL7 F7: pages 1 and 3 alike, page 2 other,
    are three sheets). `a_facts`, `b_facts` and `twins` are given by `plan_groups`, so a title is read once."""
    if a.document != b.document or (a.number and a.number == b.number):
        return False
    if _same_floor_and_area(a.document, a_facts or _facts(a), b_facts or _facts(b), twins):
        return True
    words = _title_tokens(a)
    if not words or words != _title_tokens(b) or not any(_FLOOR_TOKEN.match(w) for w in words):
        return False
    units = [{t for t in _unit_tags(tags) if t not in codes} for tags in (a_tags, b_tags)]
    return _same_tags(*units)


def plan_groups(plans, codes: Collection[str] = ()) -> dict[tuple[str, int], tuple[tuple[str, int], ...]]:
    """(document, page) -> its plan group, the sheets' (document, page) in their order, given (sheet, the tags on it
    with their counts) for each plan sheet. Sheets are keyed by (document, page), never by sheet number: one number
    in two documents is two sheets. The sheets of one group show one plan (`_one_plan`, ruling L1): they are not
    added together. A sheet in no group of two or more is its own group. Pure."""
    keys = [(sheet.document, sheet.page) for sheet, _tags in plans]
    parent = {key: key for key in keys}
    facts = [_facts(sheet) for sheet, _tags in plans]       # each title read once, not once per pair of sheets
    seen = Counter((sheet.document, *fact) for (sheet, _tags), fact in zip(plans, facts) if fact[0] is not None)
    twins = {(document, area, other) for (document, area, other, _trades), n in seen.items() if n > 1}

    def root(key):
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    for i, (a, a_tags) in enumerate(plans):
        for j in range(i + 1, len(plans)):
            b, b_tags = plans[j]
            ka, kb = (a.document, a.page), (b.document, b.page)
            if (ka != kb and root(ka) != root(kb)
                    and _one_plan(a, a_tags, b, b_tags, codes, facts[i], facts[j], twins)):
                parent[root(kb)] = root(ka)
    members: dict[tuple[str, int], list] = defaultdict(list)
    for key in keys:
        if key not in members[root(key)]:
            members[root(key)].append(key)
    return {key: tuple(members[root(key)]) for key in keys}


_BUILDING = re.compile(
    r"\b(?:BUILDINGS?|BLDGS?|TOWERS?|PAVILIONS?)\b\.?\s*[-#]?\s*(?:NO\.?\s*)?[A-Z0-9]{1,6}"
    r"(?:\s*(?:,|AND|&)\s*[A-Z0-9]{1,6}\b)*"
    r"|\b[A-Z][A-Z0-9]*\s+(?:BUILDING|BLDG|TOWER|PAVILION)\b", re.I)
_NOT_A_BUILDING = re.compile(r"^(?:MECHANICAL|HVAC|PLAN|THE|AND|OF|NEW|EXISTING)\s", re.I)


def plan_buildings(sheets) -> dict[tuple[str, int], str]:
    """(document, page) -> the building a plan sheet shows, for ruling 2 of 2026-10-11 (T-005a): a numbered unit tag
    is one unit in the job, so it counts once however many plans show it, but a job of several buildings can reuse
    its tags in each (VAV-1 in BLDG. A and in BLDG. B). The building is what the title names with a building word
    (BUILDING 1000, BLDG. A, TOWERS 1 AND 2, NORTH TOWER), and the document as well when the same sheet number is in
    two documents (two identical buildings issued as two documents, REVIEW-FINAL5 F7). "" for every other sheet: the
    floors, wings and part plans of one building (EAST, AREA B, WEST WING, part plans at a match line) are one place."""
    sheets = list(sheets)
    documents: dict[str, set] = defaultdict(set)
    for s in sheets:
        if s.number:
            documents[s.number].add(s.document)
    found = {}
    for s in sheets:
        title = title_without_number(s) if s.number else (s.title or "").upper()
        named = [" ".join(m.group(0).upper().replace(".", "").split()) for m in _BUILDING.finditer(title)]
        named = [n for n in named if not _NOT_A_BUILDING.match(n)]
        twin = s.document if s.number and len(documents[s.number]) > 1 else ""
        found[(s.document, s.page)] = " / ".join(filter(None, [*named, twin]))
    return found


def plan_count(found, groups: dict, per_place: bool, buildings: dict | None = None) -> int:
    """The one counting rule (lead ruling, FINAL-I; ruling L1 for which sheets are one plan), given each plan sheet a
    tag is on as ((document, page), labels on it as drawn, the floors it stands for: a typical sheet's floor names,
    empty for one floor) and `plan_groups`.
    A unit's tag counts once in the whole job (ruling 2 of 2026-10-11), times the floors its typical sheets stand
    for, once in each building when the job has several (`buildings`, from `plan_buildings`). In each plan group a tag counted at every place (`counted_per_place`) the most labels
    of any one sheet of the group (one plan drawn again), each times the floors the group's sheets stand for, every
    floor once (two typical sheets of floors 2 to 5 are 4 floors, of floors 2 to 5 and 6 to 10 are 9). The groups
    are summed."""
    if not per_place:
        # Ruling 2 of 2026-10-11 (T-005a): a numbered unit tag (AHU-1, EF-3) is ONE unit in the whole job, however
        # many plans show it (the plans of other trades, part plans that overlap at a match line): once, times the
        # floors its typical sheets stand for (every floor once). The other labels are duplicates; the dossier's
        # counts line names them (`_summed_notes`).
        # A job of several buildings can reuse its tags in each (`plan_buildings`): once in each building.
        # A typical sheet already says each floor it stands for has its own unit of the tag; where the tag is on a
        # typical sheet, a plan of one floor (a plan group, `groups`) that shows it too is one floor more (FIRST FLOOR
        # PLAN beside TYPICAL FLOORS 2-4 is 4): when in doubt the higher count.
        floors_of: dict[str, set] = defaultdict(set)
        typical = {(buildings or {}).get(key, "") for key, _n, floors in found if floors}
        for key, _n, floors in found:
            building = (buildings or {}).get(key, "")
            floors_of[building].update(floors)
            if not floors and building in typical:
                floors_of[building].add(("plan", groups.get(key, (key,))))
        return sum(max(1, len(floors)) for floors in floors_of.values())
    by_group: dict[tuple, list] = defaultdict(list)
    for key, n, floors in found:
        by_group[groups.get(key, (key,))].append((n, frozenset(floors)))
    total = 0
    for entries in by_group.values():
        floors = max(1, len(frozenset().union(*(f for _n, f in entries))))
        total += max(n for n, _f in entries) * floors
    return total


def sheets_apart(found) -> int:
    """A numbered unit tag's count if each plan sheet that shows it showed its own unit: one per sheet, times the
    floors that sheet stands for. Ruling 2 of 2026-10-11 counts the tag once in the job (`plan_count`); the lead's
    ruling on the T-005a review keeps this higher number beside it, so the count's '*' note can print both numbers
    and the sheets (`Placements.summed`, `InventoryItem.summed`, `FamilyTotal.summed`)."""
    floors_of: dict[tuple, set] = defaultdict(set)
    for key, _n, floors in found:
        floors_of[key].update(floors)
    return sum(max(1, len(floors)) for floors in floors_of.values())


def plan_floors(catalogue, typicals: Sequence = ()) -> dict[tuple[str, str], frozenset[str]]:
    """(document, sheet number) -> the floors that plan stands for: a typical sheet's floor list (one with no
    number by (document, page), `sheet_floors`), else, for a sheet number on N pages of one document with the same
    text on every page, its N pages (one floor each). A sheet not listed stands for one floor. Pages of one number
    with other text are other sheets, each read and counted (`counting_pages`), never one plan times its pages
    (REVIEW-FINAL6 F6). A floor named by digits alone is one floor however it is written ("02" and "2", F9)."""
    # by (document, sheet number) (REVIEW-FINAL8 H4); a typical given with no document (by hand) stands for its
    # number in every document
    named = {(getattr(t, "document", None), t.sheet): frozenset(_floor_name(f) for f in t.floors)
             for t in typicals if t.sheet and t.floors}
    pages: dict[tuple[str, str], list[int]] = defaultdict(list)
    for s in catalogue.sheets:
        if s.number:
            pages[(s.document, s.number)].append(s.page)
    alike = _alike_pages(catalogue)
    found: dict[tuple[str, str], frozenset[str]] = {}
    for (document, number), on in pages.items():
        floors = (named.get((document, number)) or named.get((None, number))
                  or (frozenset(f"p.{page}" for page in on) if (document, number) in alike else frozenset()))
        if len(floors) > 1:
            found[(document, number)] = floors
    # a typical sheet with no number (RD-13) is keyed by its (document, page), as `typical_sheets` makes it: the
    # page of its document with no number and its title (`count_devices` multiplies its devices the same way)
    for t in typicals:
        if t.sheet or not t.floors or not getattr(t, "document", None):
            continue
        floors = frozenset(_floor_name(f) for f in t.floors)
        if len(floors) > 1:
            for s in catalogue.sheets:
                if not s.number and s.document == t.document and s.title == t.title:
                    found[(s.document, s.page)] = floors
    return found


def sheet_floors(floor_sets: dict, sheet) -> frozenset[str]:
    """The floors a plan sheet stands for in `plan_floors`: by (document, sheet number), or by (document, page) for
    a sheet with no number (RD-13); empty for one floor."""
    return floor_sets.get((sheet.document, sheet.number) if sheet.number else (sheet.document, sheet.page),
                          frozenset())


def _floor_name(floor: str) -> str:
    floor = str(floor).strip().upper()
    return str(int(floor)) if floor.isdigit() else floor


def _alike_pages(catalogue) -> set[tuple[str, str]]:
    """(document, sheet number) of each number on 2 or more pages of one document with the same text on every page:
    one plan printed again (a typical floor per page), read on its first page only."""
    texts = {(p.document, p.page): p.text for p in catalogue.pages}
    by_number: dict[tuple[str, str], set] = defaultdict(set)
    pages: dict[tuple[str, str], int] = defaultdict(int)
    for s in catalogue.sheets:
        if s.number:
            by_number[(s.document, s.number)].add(texts.get((s.document, s.page), ""))
            pages[(s.document, s.number)] += 1
    return {key for key, found in by_number.items() if pages[key] >= 2 and len(found) == 1}


def first_pages(catalogue) -> dict[tuple[str, int], int]:
    """(document, page) -> the first page of its sheet number in that document, for each page that only repeats it
    (the same number on several pages with the same text on every page, `_alike_pages`): such a page is counted on
    its first page, which the floors stand for. A page of one number with other text is its own sheet."""
    alike = _alike_pages(catalogue)
    first: dict[tuple[str, str], int] = {}
    for s in catalogue.sheets:
        if s.number and (s.document, s.number) in alike:
            first[(s.document, s.number)] = min(first.get((s.document, s.number), s.page), s.page)
    return {(s.document, s.page): first[(s.document, s.number)] for s in catalogue.sheets
            if s.number and (s.document, s.number) in alike and first[(s.document, s.number)] != s.page}


def counting_pages(catalogue, governing: Collection[tuple[str, int]]) -> frozenset[tuple[str, int]]:
    """The drawing pages the counts read: the governing pages (`governing_pages`), plus a plan sheet whose number is
    in another document too with exactly the same text, when the two documents are of one issue (the same revision,
    neither an addendum nor a duplicate file) and its document is not a marked-up copy of the set (`repeats`): two
    identical buildings issued as two documents are two sheets (REVIEW-FINAL5 F7), both counted and named as maybe
    one plan. Of a sheet number on several pages of one document with the same text on every page only the first
    page counts (`plan_floors` stands for the rest); pages of one number with other text all count (F6)."""
    copies = repeats(catalogue)[1]
    documents = {d.relative: d for d in getattr(catalogue.job, "documents", ())}

    def issue(document: str) -> tuple | None:
        """The issue a document belongs to (its revision); None for an addendum or a duplicate file, which reissue
        or repeat a sheet and never stand for another building."""
        d = documents.get(document)
        if d is None:
            return ("",)
        if d.kind == "addendum" or getattr(d, "duplicate_of", None):
            return None
        return (d.revision,)

    texts = {(p.document, p.page): p.text for p in catalogue.pages}
    read: dict[str, dict[str, set]] = defaultdict(lambda: defaultdict(set))   # number -> text -> issues read
    for s in catalogue.sheets:
        if s.number and (s.document, s.page) in governing:
            read[s.number][texts.get((s.document, s.page), "")].add(issue(s.document))
    keep = set(governing)
    for s in catalogue.sheets:
        key = (s.document, s.page)
        if (s.number and key not in governing and "Plans" in s.types and (s.number, s.document) not in copies
                and texts.get(key) and issue(s.document) is not None
                and issue(s.document) in read.get(s.number, {}).get(texts[key], ())):
            keep.add(key)
    repeated = first_pages(catalogue)
    return frozenset(key for key in keep if key not in repeated)


def sheet_labels(sheets) -> dict[tuple[str, int], str]:
    """(document, page) -> the sheet's name in the counts: its number ("M-101"), with its document's name when the
    same number is counted from two documents ("M-101 (Second Building.pdf)"), else the document and page. (Two
    pages of one number in one document with other text, both counted since FINAL-K, share the number's name: the
    evidence picks its sheets by number.)"""
    sheets = list(sheets)
    documents: dict[str, set] = defaultdict(set)
    for s in sheets:
        if s.number:
            documents[s.number].add(s.document)
    return {(s.document, s.page): (s.number if len(documents[s.number]) == 1 else f"{s.number} ({_name(s.document)})")
            if s.number else f"{_name(s.document)} p.{s.page}" for s in sheets}


def _named_apart(a, b) -> bool:
    """Both titles name parts (TOWER 1, DORM WING, NORTH) and not the same ones."""
    a_parts, b_parts = _parts((a.title or "").upper()), _parts((b.title or "").upper())
    return bool(a_parts) and bool(b_parts) and a_parts != b_parts


def plan_area_doubts(plans, areas: dict[tuple[str, int], int] | None = None
                     ) -> list[tuple[tuple[str, int], tuple[str, int]]]:
    """The pairs of plan sheets that MAY show one plan, a hint for the counts line's reading notes (both are
    counted, the higher count): their titles name the same readable floor and parts; or they are in one document
    with the same title text (its sheet number taken out); or they repeat each other's unit tags (`_unit_tags`)
    and their titles do not name two different floors. Never a pair whose titles name two different floors, or no
    floor and two different parts. `areas` is kept for the signature; every sheet is its own area now. Given
    (sheet, tags) per plan sheet. Pure."""
    sheets = [(sheet, _unit_tags(tags), _area_key(sheet.title), _plain_title(sheet)) for sheet, tags in plans]
    doubts = []
    for i, (a, a_units, a_key, a_title) in enumerate(sheets):
        for b, b_units, b_key, b_title in sheets[i + 1:]:
            ka, kb = (a.document, a.page), (b.document, b.page)
            if ka == kb:
                continue
            if a_key is not None and b_key is not None:
                maybe = a_key == b_key
            elif a_key is None and b_key is None and _named_apart(a, b):
                maybe = False                       # no floor, but two parts named apart (DORM WING, CLASSROOM WING)
            else:
                maybe = ((a.document == b.document and bool(a_title) and a_title == b_title)
                         or _same_tags(a_units, b_units))
            if maybe:
                doubts.append((ka, kb))
    return doubts


def placements(catalogue, tags: Iterable[str], typicals: Sequence = (),
               pages: Collection[tuple[str, int]] | None = None,
               groups: dict | None = None, admitted: Collection[tuple[str, int]] | None = None) -> dict[str, Placements]:
    """Each tag's labels on the plan sheets and on the riser diagrams, read from the counted pages of each sheet
    (`counting_pages`), and its count on the plans by the one counting rule (`plan_groups`, `plan_count`), the
    floors of each typical sheet applied (1.4). A type sized "X.0" is also labelled "X" (HRU-4).

    `groups` (takeoff pass Stage 2, Task 2.1): the plan groups to count by, in the form `plan_groups` returns
    ((document, page) -> the group's sheets), used in place of the code's own `plan_groups` when given: the takeoff
    register's areas (`bms.takeoff.area_groups`). A sheet in no given group is a group of its own.

    `admitted` (T-007b): the (document, page) of the sheets the takeoff register admits (`counts_units` true). The
    register decides: a page in it is read even when its title says demolition. A page not in it keeps the title
    check. None (no register): the title check stands for every page."""
    keys = label_keys(tags)
    if not keys:
        return {}
    asked = set(keys.values())
    for entry in catalogue.tags:               # every tag on the plans is evidence of which sheets show one plan
        keys.setdefault(label_key(entry.tag), entry.tag)
    floor_sets = plan_floors(catalogue, typicals)
    if pages is None:
        pages = governing_pages(catalogue, (), typical_places(typicals))
    pages = counting_pages(catalogue, pages)
    sheets = {(s.document, s.page): s for s in catalogue.sheets}
    read: list[tuple] = []
    demolished: list[tuple] = []          # ruling 1: demolition plans, read only to name what they leave out
    for record in catalogue.pages:
        sheet = sheets.get((record.document, record.page))
        if (sheet is None or (record.document, record.page) not in pages or sheet.discipline not in CONTROLS_DISCIPLINES
                or "Schedules" in sheet.types):
            continue
        riser = bool(_RISER.search(sheet.title or "")) or any("riser" in t for t in sheet.types)
        if is_demolition(sheet) and (record.document, record.page) not in (admitted or ()):
            if "Plans" in sheet.types or riser:
                demolished.append((sheet, record))
            continue
        if riser or "Plans" in sheet.types:
            read.append((sheet, record, riser))
    worked = demolition_work(catalogue, asked) if demolished else {}
    labels = sheet_labels([*(sheet for sheet, _r, _riser in read), *(sheet for sheet, _r in demolished)])
    tallies: dict[tuple[str, int], dict[str, int]] = {}
    evidence: dict[tuple[str, int], dict[str, int]] = {}
    for sheet, record, riser in read:
        # the one label reader (F7); on a plan, a unit named anywhere counts at least once (REVIEW-FINAL7 F4), and
        # the labels alone are the plan groups' evidence (the backstop never joins two plans)
        labelled = evidence[(sheet.document, sheet.page)] = line_labels(record.text, keys)
        tallies[(sheet.document, sheet.page)] = labelled if riser else plan_labels(record.text, keys, labelled)
    if groups is None:
        groups = plan_groups([(sheet, evidence[(sheet.document, sheet.page)])
                              for sheet, _r, riser in read if not riser])
    left_out: dict[str, dict[str, int]] = defaultdict(dict)   # tag -> demolition sheet -> labels, not counted
    for sheet, record in demolished:
        key = (sheet.document, sheet.page)
        for tag, n in plan_labels(record.text, keys, line_labels(record.text, keys)).items():
            if tag not in asked:
                continue
            # the lead's ruling on the T-005a review: a unit with named work is NOT added to the new-work count; it
            # stays here, its work kept beside it (`Placements.demolition_work`), for the Demolition Scope block
            left_out[tag][labels[key]] = left_out[tag].get(labels[key], 0) + n
    found: dict[str, list] = defaultdict(list)            # tag -> [((document, page), labels, floors)]
    buildings = plan_buildings(sheet for sheet, _r, riser in read if not riser)
    on_plans: dict[str, dict[str, int]] = defaultdict(dict)
    floors: dict[str, dict[str, int]] = defaultdict(dict)
    on_risers: dict[str, dict[str, int]] = defaultdict(dict)
    for sheet, _record, riser in read:
        key = (sheet.document, sheet.page)
        own = sheet_floors(floor_sets, sheet)
        for tag, n in tallies[key].items():
            if tag not in asked:
                continue
            if riser:
                on_risers[tag][labels[key]] = on_risers[tag].get(labels[key], 0) + n
                continue
            on_plans[tag][labels[key]] = on_plans[tag].get(labels[key], 0) + n
            floors[tag][labels[key]] = max(1, len(own))
            found[tag].append((key, n, own))

    def same_plan(mine: list, per_place: bool) -> tuple[tuple[str, ...], ...]:
        """The sheets of each plan group that show this tag on two or more of them (ruling L1). A numbered unit tag
        is one unit in the job (ruling 2 of 2026-10-11): every sheet that shows it is named, in one group."""
        if not per_place:
            names = tuple(dict.fromkeys(labels[key] for key, _n, _f in mine))
            return (names,) if len(names) >= 2 else ()
        shown = {key for key, _n, _f in mine}
        named = [tuple(dict.fromkeys(labels[key] for key in group if key in shown))
                 for group in dict.fromkeys(groups.get(key, (key,)) for key, _n, _f in mine)]
        return tuple(names for names in named if len(names) >= 2)

    def placed(tag: str) -> Placements:
        mine = found.get(tag, [])
        per_place = bool(mine) and counted_per_place(tag, sum(n for _k, n, _f in mine), max(n for _k, n, _f in mine))
        # `summed` and `each_place_summed` are the same two counts with every sheet its own plan (no groups): the
        # sheets added up, kept beside them so a drop that ruling L1 makes can print both numbers. A numbered unit
        # tag's `summed` is each sheet its own unit (`sheets_apart`): ruling 2 counts it once, and the lead's ruling
        # on the T-005a review keeps the higher number for the count's '*' note
        apart = plan_count(mine, {}, per_place, buildings) if mine else 0
        if mine and not per_place:
            apart = max(apart, sheets_apart(mine))
        return Placements(dict(on_plans.get(tag, {})), dict(floors.get(tag, {})), dict(on_risers.get(tag, {})),
                          plan_count(mine, groups, per_place, buildings) if mine else 0, per_place,
                          plan_count(mine, groups, True) if mine else 0,
                          apart,
                          plan_count(mine, {}, True) if mine else 0,
                          same_plan(mine, per_place), dict(left_out.get(tag, {})),
                          worked.get(tag, "") if tag in left_out else "")

    return {tag: placed(tag) for tag in set(on_plans) | set(on_risers) | set(left_out)}


# ---- ruling 1 of 2026-10-11 (T-005a): work named on a unit a demolition plan shows ----------------------------------

def demolition_work(catalogue, tags: Iterable[str]) -> dict[str, str]:
    """tag -> the first line of the documents (any page: a note, a keyed note, the spec) that names the tag and work
    on it (`sheet_types.work_words`: refurbish, relocate its sensor, new controls ...). The lead's ruling on the T-005a
    review: such a unit is still left out of the new-work counts, like every unit a demolition plan shows; the line is
    kept beside it (`Placements.demolition_work`) for the Demolition Scope block. A line that only removes a unit or
    keeps it ("REMOVE EXISTING AHU-6", "EXISTING TO REMAIN") names no work."""
    wanted = {t for t in tags if t}
    if not wanted:
        return {}
    words = work_words()
    names = "|".join(re.escape(t) for t in sorted(wanted, key=len, reverse=True))
    find = re.compile(rf"(?<![A-Za-z0-9\-])({names})(?![A-Za-z0-9]|-[A-Za-z0-9])", re.I)
    by_upper = {t.upper(): t for t in wanted}
    found: dict[str, str] = {}
    for record in getattr(catalogue, "pages", ()) or ():
        for line in (record.text or "").splitlines():
            if not any(w.search(line) for w in words):
                continue
            for match in find.finditer(line):
                tag = by_upper.get(match.group(1).upper())
                if tag is not None:
                    found.setdefault(tag, " ".join(line.split()))
    return found


# ---- a plan tag an air outlet schedule lists as a code: left out of the dossier's units, and said -------------------

NAMED_TAGS = 3         # the tags a reading note names; the others are counted ("and 4 more")


def _listing(schedule: Schedule) -> str:
    """A schedule as a note names it: its title and its sheet ("AIR OUTLET SCHEDULE (M-601)"), or only its sheet ("the
    schedule on M-601") when its title says nothing (none was found, or it is the bare word SCHEDULE)."""
    if kind_from_title(schedule.title) == EQUIPMENT:
        return f"the schedule on {_place(schedule)}"
    return f"{schedule.title} ({_place(schedule)})"


def air_outlet_codes(schedules: Iterable[Schedule], equipment: Equipment | None = None) -> dict[str, list[str]]:
    """Every tag a schedule of passive air devices (`Schedule.passive`) lists as a code in its key column -> the
    schedules that list it (`_listing`), in order. B1 reads as B-1, a boiler's tag, and SD-1 is a smoke damper's: the
    dossier leaves such a plan tag out of its units (HP 3) unless a unit schedule lists it too."""
    equipment = equipment or Equipment.load()
    found: dict[str, list[str]] = {}
    for schedule in schedules:
        if not (schedule.passive and schedule.headers):
            continue
        name = _listing(schedule)
        for row in schedule.rows:
            for tag in expand_tags(row.cells.get(schedule.headers[0], ""), equipment):
                if name not in found.setdefault(tag, []):
                    found[tag].append(name)
    return found


def air_outlet_notes(catalogue, schedules: Iterable[Schedule], typicals: Sequence = (),
                     pages: Collection[tuple[str, int]] | None = None) -> dict[str, str]:
    """prefix -> the reading note for the plan tags of that prefix that an air outlet schedule lists as codes
    (`air_outlet_codes`) and no unit schedule lists: the dossier leaves them out of its units, so a count is lowered,
    and the note names the tags, the schedules and both numbers: the labels on the counted plan sheets
    (`Placements.drawn`), and what counting the tags as units would give by the one counting rule (`Placements.count`:
    floors, plan groups, types). A tag labelled on no plan is no note. Never in a client cause's words. The one text of
    the dossier's counts line and of the reading flags (`read_job`)."""
    schedules = list(schedules)
    listed = air_outlet_codes(schedules)
    scheduled = {row.tag for s in schedules for row in s.rows if row.tag and not row.existing}
    lost = sorted((tag for tag in listed if tag not in scheduled), key=_natural)
    if not lost:
        return {}
    found = placements(catalogue, lost, typicals, pages)
    notes: dict[str, str] = {}
    for prefix in dict.fromkeys(tag_prefix(tag) for tag in lost):
        tags = [tag for tag in lost if tag_prefix(tag) == prefix and tag in found and found[tag].drawn]
        if not tags:
            continue
        labels = sum(found[tag].drawn for tag in tags)
        counted = sum(found[tag].count for tag in tags)
        named = ", ".join(tags[:NAMED_TAGS]) + (f" and {len(tags) - NAMED_TAGS} more" if len(tags) > NAMED_TAGS else "")
        where = _names(dict.fromkeys(name for tag in tags for name in listed[tag]))
        several = len(tags) > 1
        are, codes, units = ("are", "air-outlet codes", "units") if several else ("is", "an air-outlet code", "a unit")
        notes[prefix] = (f"{named} on the plans ({labels} label{'' if labels == 1 else 's'}) {are} listed as {codes} on "
                         f"{where}: not counted as {units}, 0 counted, {counted} if counted as units; check")
    return notes


def _count_in(cell: str | None) -> int | None:
    """A quantity cell's count: "719", "(2)", "2 EA"; None when it holds none."""
    match = re.search(r"\d+", (cell or "").replace(",", ""))
    return int(match.group(0)) if match and not re.search(r"\d\s*[./]\s*\d", cell or "") else None


def _as_type(tag: str, kind: str, schedule: Schedule, row, placed: Placements | None, label: str,
             seen: tuple[str, ...]) -> InventoryItem | None:
    """The row as a type, counted (1.3), or as several units counted on the plans, or None when it is one unit. It
    is a type when its tag has a decimal size, when its schedule has a QUANTITY column, or when the plans count it
    at every place (`counted_per_place`, the labels as drawn: a type's tag, or a numbered tag drawn as a type is).
    A unit's tag the plans count more than once (on plans the one counting rule adds up, or on a typical sheet's
    floors) is that many units. Either way the plans' count is the dossier's own rule (`plan_count`), so the
    Evidence Package and the proposal agree (REVIEW-FINAL5 F4); a row called a type by its decimal size or its
    QUANTITY column is counted as a type, at every place (`Placements.each_place`, REVIEW-FINAL6 F1)."""
    column = quantity_header(schedule)
    if getattr(row, "shares", 1) > 1:
        return None      # the row lists several tags ("A THRU C"): the tags are the count, one unit each
    as_type = False
    if DECIMAL_TYPE.match(tag):
        why, as_type = f"its tag has a decimal size, {tag}", True
    elif column:
        why, as_type = f"the schedule has a {column} column", True
    elif placed is not None and placed.per_place and is_type_tag(tag):
        why = f"its tag names a type, {tag}, labelled {placed.drawn} times on the plans"
    elif placed is not None and placed.per_place:
        why = f"it is labelled {placed.drawn} times on the plans"
    elif placed is not None and placed.count > 1:
        lowered = placed.summed > placed.count         # ruling L1: sheets of one floor and area counted once
        said = f"; {placed.same_plan_note(placed.count, placed.summed)}" if lowered else ""
        return InventoryItem(tag, kind, "CONFIRMED", placed.count, label, seen,
                             f"On the schedule ({label}) and counted {placed.count} times on the plans "
                             f"({placed.plans_text()}): a unit's tag counts once in the job, on each floor a typical "
                             f"plan stands for{said} — check the count", "confirm",
                             summed=placed.summed if lowered else None,
                             summed_on=tuple(placed.on_plans) if lowered else ())
    else:
        return None
    count = _count_in(row.cells.get(column)) if column else None
    action = ""
    summed = None
    if count is not None:
        how = f"quantity {count} from the schedule's {column} column"
    elif placed is not None and placed.count:
        count, action = max(placed.count, placed.each_place) if as_type else placed.count, "confirm"
        added = max(placed.summed, placed.each_place_summed) if as_type else placed.summed
        how = f"{count} counted on the plans ({placed.plans_text()})"
        if added > count:                              # ruling L1: both numbers, so a '*' note can print them
            how += f"; {placed.same_plan_note(count, added)}"
            summed = added
        how += " — check the count"
    else:
        how = "not counted on the plans yet — count it before pricing"
        action = "confirm"
    if placed is not None and placed.on_risers:
        how += (f"; the riser diagrams show {sum(placed.on_risers.values())} ({placed.risers_text()}), "
                f"a cross-check")
    return InventoryItem(tag, kind, "CONFIRMED" if count is not None else "PENDING", count, label, seen,
                         f"{_A_TYPE} ({why}): {how}", action, summed=summed,
                         summed_on=tuple(placed.on_plans) if summed and placed is not None else ())


def _type_rows(schedule: Schedule, known: Collection[str]) -> list[InventoryItem] | None:
    """A type-only schedule with a QUANTITY column (HEAT PUMP AIR CONDITIONING UNIT SCHEDULE: HPAC, 719):
    one counted item per type code. None when it has no such column, or a row can't be one."""
    column = quantity_header(schedule)
    key = schedule.headers[0] if schedule.headers else ""
    if not column or column == key:
        return None
    kind = kind_from_title(schedule.title)
    items = []
    for row in schedule.rows:
        code = header_key(row.cells.get(key))
        if not re.fullmatch(r"[A-Z][A-Z0-9\-]{0,11}", code) or code in known:
            return None
        count = _count_in(row.cells.get(column))
        how = (f"quantity {count} from the schedule's {column} column" if count is not None
               else f"its {column} cell gives no count — count it before pricing")
        items.append(InventoryItem(code, kind, "CONFIRMED" if count is not None else "PENDING", count,
                                   _label(schedule), (), f"{_A_TYPE} (the schedule has a {column} column): "
                                   f"{how}", "" if count is not None else "confirm"))
    return items or None


def _higher_quantity(held: InventoryItem, held_schedule: Schedule, other: InventoryItem,
                     other_schedule: Schedule) -> InventoryItem:
    """One type code counted by two type-only schedules (two versions of one schedule): the higher quantity counts,
    never the first document's alone; when they differ the note gives both, and their sum in case the two are
    two buildings' schedules. A quantity beats no quantity."""
    if other.quantity is None or (held.quantity is not None and other.quantity <= held.quantity):
        winner = held
    else:
        winner = other
    if held.quantity is None or other.quantity is None or held.quantity == other.quantity:
        return winner
    said = (f"{held.quantity} in {_name(held_schedule.document)}, {other.quantity} in "
            f"{_name(other_schedule.document)}")
    return replace(winner, reason=f"{winner.reason} — the schedules give other quantities ({said}); the higher, "
                                  f"{winner.quantity}, counted ({held.quantity + other.quantity} if they are two "
                                  f"buildings' schedules); confirm", action="confirm")


def build_inventory(catalogue, schedules: list[Schedule], typicals: Sequence = (),
                    pages: Collection[tuple[str, int]] | None = None
                    ) -> tuple[list[InventoryItem], list[FamilyTotal], list[str]]:
    """`typicals` (reading/devices.py) multiply a type's labels on a typical plan by its floors; `pages` are the
    governing pages they are read from (by default, worked out here)."""
    equipment = Equipment.load()
    dropped: list[str] = []
    schedules = _one_copy_per_sheet(list(schedules), dropped, repeats(catalogue)[1])
    entries = {t.tag: t for t in catalogue.tags}
    # A unit whose prefix isn't in the equipment list takes its kind from its schedule's title; the tag
    # index never looked for it, so the other sheets are searched for it here.
    new_kinds = {row.tag: row.kind for s in schedules for row in s.rows if row.tag and row.kind}
    new_places = _seen_on_pages(catalogue, new_kinds)

    def kind_of(tag: str) -> str:
        if tag in new_kinds:
            return new_kinds[tag]
        entry = entries.get(tag)
        return entry.kind if entry else equipment.prefixes.get(tag_prefix(tag), "Equipment")

    # A tag named only in the specifications — a paragraph or page reference, a model number — and on no
    # drawing sheet isn't a unit: it's left out, and listed once.
    drawing_places = {s.number or f"{_name(s.document)} p.{s.page}" for s in catalogue.sheets}
    spec_only = sorted((t.tag for t in catalogue.tags
                        if not t.on_schedules and not any(p in drawing_places for p in t.elsewhere)), key=_natural)

    has_schedule_sheet = any("Schedules" in s.types for s in catalogue.sheets)
    if not schedules and not has_schedule_sheet:
        items = [InventoryItem(t.tag, t.kind, "PENDING", None, None, t.elsewhere,
                               "No schedule in the set — the count has to come from the plans", "confirm")
                 for t in sorted(catalogue.tags, key=lambda t: _natural(t.tag)) if t.tag not in spec_only]
        return items, [], _left_out(spec_only, [])

    drawings = {s.number or f"{_name(s.document)} p.{s.page}" for s in catalogue.sheets if "Schedules" not in s.types}
    listings: dict[str, list[tuple[str, str]]] = defaultdict(list)
    listed_in: dict[str, list[tuple[str, str]]] = defaultdict(list)   # tag → (place, document) of each listing
    quantities: dict[str, list[tuple[int, str]]] = defaultdict(list)  # tag → (QUANTITY cell, document) per listing
    first_row: dict[str, tuple[Schedule, object]] = {}
    existing: set[str] = set()
    from_text: dict[str, str] = {}      # tag → the schedule it was counted under, from a sheet's text
    by_eye: set[str] = set()            # tags read from a picture of the schedule by the AI judge
    blocks: set[tuple] = set()
    for schedule in schedules:
        # One schedule set out in two blocks on the same sheet (fan data, then coil data), each
        # listing the same units in the same order, is one listing, not every unit twice.
        block = (schedule.document, schedule.page, tuple(row.tag for row in schedule.rows))
        if len(block[2]) >= 2 and block in blocks:
            continue
        blocks.add(block)
        for row in schedule.rows:
            if row.tag is None:
                continue
            listings[row.tag].append((_label(schedule), _place(schedule)))
            listed_in[row.tag].append((_place(schedule), schedule.document))
            first_row.setdefault(row.tag, (schedule, row))
            column = quantity_header(schedule)
            stated = _count_in(row.cells.get(column)) if column and getattr(row, "shares", 1) == 1 else None
            if stated is not None:
                quantities[row.tag].append((stated, schedule.document))
                held = first_row[row.tag]
                held_column = quantity_header(held[0])
                held_count = _count_in(held[1].cells.get(held_column)) if held_column else None
                if getattr(held[1], "shares", 1) == 1 and held_count is not None and stated > held_count:
                    first_row[row.tag] = (schedule, row)   # two versions list the type: the higher quantity
                                                           # counts, never the first document's (RD-1)
            if getattr(row, "shares", 1) > 1 and getattr(first_row[row.tag][1], "shares", 1) == 1:
                first_row[row.tag] = (schedule, row)   # named in a series ("A THRU C"): one unit, whatever another
                                                       # schedule's QUANTITY column says of its own row
            if schedule.from_text:
                from_text.setdefault(row.tag, _label(schedule))
            if schedule.source == BY_EYE:
                by_eye.add(row.tag)
            if row.existing:
                existing.add(row.tag)
    scheduled_prefixes = {tag_prefix(tag) for tag in listings}
    spec_only = [tag for tag in spec_only if tag not in listings]
    # What the schedules read from each sheet say outside their tag column: models, remarks, notes.
    read_places = {_place(schedule) for schedule in schedules}
    other_text: dict[str, str] = defaultdict(str)
    for schedule in schedules:
        key = schedule.headers[0] if schedule.headers else ""
        words = [v for row in schedule.rows for k, v in row.cells.items() if k != key and v] + list(schedule.notes)
        other_text[_place(schedule)] += " " + _compact(" ".join(words))

    def not_a_unit(entry) -> bool:
        """On schedule sheets whose schedules were read, in none of their tag columns, and either a one-letter
        prefix (B-7, P-212: too easily a model number or a phone number) or named inside another column or a
        note there (a model number, "AS LOW AS 8HZ") and on no plan."""
        if not entry.on_schedules or not all(p in read_places for p in entry.on_schedules):
            return False
        if tag_prefix(entry.tag) in equipment.schedule_only:
            return True
        return (any(_compact(entry.tag) in other_text[p] for p in entry.on_schedules)
                and not any(p in drawings for p in entry.elsewhere))

    mentioned: list[str] = []
    placed = placements(catalogue, listings, typicals, pages)
    on_plans, not_equipment = _plan_families(catalogue, [e for e in catalogue.tags if e.tag not in listings
                                                         and e.tag not in spec_only and not e.on_schedules],
                                             scheduled_prefixes)
    never: list[str] = []

    items: list[InventoryItem] = []
    for tag in sorted(set(listings) | set(entries), key=_natural):
        entry = entries.get(tag)
        kind = kind_of(tag)
        if tag in listings:
            own = list(dict.fromkeys(place for _, place in listings[tag]))
            seen = tuple(p for p in (entry.elsewhere if entry else new_places.get(tag, ())) if p not in own)
            on_drawings = [p for p in seen if p in drawings]
            label = listings[tag][0][0]
            where = _listed_where(listed_in[tag])
            typed = None if tag in existing else _as_type(tag, kind, *first_row[tag], placed.get(tag), label, seen)
            if typed is not None:
                if len(listings[tag]) > 1:       # never lose the listed-twice words (REVIEW-FINAL6 F8)
                    typed = replace(typed, reason=f"{typed.reason} — tag listed {len(listings[tag])} times on the "
                                                  f"schedules ({where}); confirm with the engineer how many units "
                                                  f"there are", action="confirm")
                stated = sorted(set(quantities.get(tag, ())), reverse=True)
                if len({n for n, _ in stated}) > 1:
                    said = ", ".join(f"{n} in {_name(d)}" for n, d in stated)
                    typed = replace(typed, reason=f"{typed.reason} — the schedules give other quantities ({said}); "
                                                  f"the higher, {stated[0][0]}, counted; confirm", action="confirm")
                items.append(typed)
            elif tag in existing:
                items.append(InventoryItem(tag, kind, "EXISTING", 0, label, seen,
                                           f"Marked existing on the schedule ({where}) — not new work; "
                                           f"confirm any removal or reuse scope separately", "confirm"))
            elif len(listings[tag]) > 1:
                items.append(InventoryItem(tag, kind, "DISCREPANCY", 1, label, seen,
                                           f"Tag listed {len(listings[tag])} times on the schedules ({where}) — "
                                           f"counted once; confirm with the engineer how many units there are",
                                           "confirm"))
            elif on_drawings:
                plans = placed.get(tag)
                # a series row ("VAV-1 THRU VAV-4", `shares` above 1): its tags are the count, one unit each, whatever
                # the plans draw, so no "N counted, M if the sheets were added up" is said of it
                series = getattr(first_row[tag][1], "shares", 1) > 1
                lowered = not series and plans is not None and plans.summed > plans.count     # ruling L1: both numbers
                said = f" — {plans.same_plan_note(plans.count, plans.summed)}" if lowered else ""
                items.append(InventoryItem(tag, kind, "CONFIRMED", 1, label, seen,
                                           f"On the schedule ({where}) and on {_sheets(len(on_drawings))} "
                                           f"({_list(on_drawings)}){said}", "confirm" if lowered else "",
                                           summed=plans.summed if lowered else None,
                                           summed_on=tuple(plans.on_plans) if lowered else ()))
            else:
                extra = f" (named only on {_list(seen)})" if seen else ""
                items.append(InventoryItem(tag, kind, "MISSING", 1, label, seen,
                                           f"On the schedule only; no plan shows it{extra} — confirm before pricing",
                                           "confirm"))
            if tag in from_text:
                item = items[-1]
                items[-1] = replace(item, reason=f"{item.reason} — {FROM_TEXT}")
            elif tag in by_eye:
                item = items[-1]
                items[-1] = replace(item, reason=f"{item.reason} — {READ_BY_EYE}")
            first_schedule, first = first_row[tag]
            column = quantity_header(first_schedule)
            stated = _count_in(first.cells.get(column)) if column and getattr(first, "shares", 1) > 1 else None
            if stated is not None and stated != first.shares:
                item = items[-1]
                items[-1] = replace(item, reason=f"{item.reason} — its schedule row lists {first.shares} tags but its "
                                                 f"{column} column says {stated}; check the count", action="confirm")
            continue
        if tag in spec_only:
            continue
        if not_a_unit(entry):
            mentioned.append(tag)
            continue
        seen = entry.elsewhere
        if entry.on_schedules:
            items.append(InventoryItem(tag, kind, "PENDING", None, None, seen,
                                       f"On schedule sheet {_list(entry.on_schedules)} but not read from a schedule "
                                       f"table — check the count by eye", "confirm"))
        elif tag in not_equipment:
            never.append(tag)
        elif tag in on_plans:
            items.append(InventoryItem(tag, kind, ON_PLANS, 1, None, seen, f"Shown on {_list(seen)} — {ON_PLANS_WHY}",
                                       "confirm"))
        elif entry.times == 1:
            items.append(InventoryItem(tag, kind, "ORPHANED", None, None, seen,
                                       f"Appears only once in the whole set ({_list(seen)}) and on no schedule — "
                                       f"unclear scope; don't price until confirmed", "exclude pending"))
        else:
            why = ("but not on any schedule" if tag_prefix(tag) in scheduled_prefixes
                   else "and no schedule lists this kind of equipment")
            items.append(InventoryItem(tag, kind, "EXTRA", None, None, seen,
                                       f"Shown on {_list(seen)} {why} — don't price until confirmed",
                                       "exclude pending"))

    # A type code a type-only schedule counts (`_type_rows`), by the schedule that first counted it: another version
    # of the schedule (RD-1) adds the codes it alone lists, and of a code both give a quantity the higher counts.
    typed_codes: dict[str, tuple[int, Schedule]] = {}
    for schedule in schedules:
        if not schedule.type_only or not schedule.rows:
            continue
        counted_types = _type_rows(schedule, {item.tag for item in items if item.tag not in typed_codes})
        if counted_types:
            for item in counted_types:
                if item.tag not in typed_codes:
                    typed_codes[item.tag] = (len(items), schedule)
                    items.append(item)
                    continue
                at, held = typed_codes[item.tag]
                items[at] = _higher_quantity(items[at], held, item, schedule)
                if items[at] is item:
                    typed_codes[item.tag] = (at, schedule)
            continue
        key = schedule.headers[0] if schedule.headers else ""
        codes = list(dict.fromkeys(row.cells.get(key, "") for row in schedule.rows if row.cells.get(key)))
        shown = ", ".join(codes[:8]) + (" …" if len(codes) > 8 else "")
        items.append(InventoryItem(f"Type-only: {schedule.title}", "", "TYPE ONLY", None, _label(schedule), (),
                                   f"Type-only schedule ({len(codes)} types: {shown}) — no unit tags, so count them "
                                   f"on the plans; no count yet", "confirm", tuple(codes)))

    totals = _totals(items, schedules, equipment, new_kinds, set(from_text))
    counts = {t.prefix: t.scheduled for t in totals}
    pairs = [f"check the pairing: {counts[a]} {a}, {counts[b]} {b} — one outdoor unit can serve several indoor "
             f"units, so this may be right" for a, b in vocabulary().pairs
             if counts.get(a) and counts.get(b) and counts[a] != counts[b]]
    return (items, totals, pairs + dropped + _new_prefix_flags(schedules) + _from_text_flags(from_text)
            + _left_out(spec_only, mentioned, sorted(never, key=_natural)))


def _plan_like(sheet) -> bool:
    """A plan (or a sheet no type was found for, such as 26-0478's P101 "WATER"), never a schedule, detail,
    diagram or demolition sheet."""
    return not sheet.types or ("Plans" in sheet.types and not {"Schedules", "Demolition"} & set(sheet.types))


def _plan_families(catalogue, entries, scheduled_prefixes) -> tuple[set[str], set[str]]:
    """Of the tags on no schedule, in families no readable schedule lists (1.5):
    - on the plans: the tags of a family that the mechanical, controls or plumbing plans show as a series (two or
      more distinct tags) or on two or more sheets: counted from the plans, to check;
    - not equipment: every tag of a family seen on no sheet of the trades that carry controls scope, only on
      architectural, electrical, technology or AV sheets (26-0478's SF-, CH- and CT- tags)."""
    place = {s.number or f"{_name(s.document)} p.{s.page}": s for s in catalogue.sheets}
    trade_plans = {p for p, s in place.items() if s.discipline in TRADE_DISCIPLINES and _plan_like(s)}
    controls = {p for p, s in place.items() if s.discipline in CONTROLS_DISCIPLINES}
    families: dict[str, list] = defaultdict(list)
    for entry in entries:
        prefix = tag_prefix(entry.tag)
        if prefix not in scheduled_prefixes:
            families[prefix].append(entry)
    on_plans: set[str] = set()
    not_equipment: set[str] = set()
    for family in families.values():
        shown = {e.tag: [p for p in e.elsewhere if p in trade_plans] for e in family}
        shown = {tag: where for tag, where in shown.items() if where}
        if len(shown) >= 2 or any(len(where) >= 2 for where in shown.values()):
            on_plans |= set(shown)
        if not any(p in controls for e in family for p in e.elsewhere):
            not_equipment |= {e.tag for e in family if any(p in place for p in e.elsewhere)}
    return on_plans, not_equipment


def _from_text_flags(from_text: dict[str, str]) -> list[str]:
    """One line per family counted from a schedule sheet's text."""
    by_prefix: dict[str, list[str]] = defaultdict(list)
    for tag, label in from_text.items():
        by_prefix[tag_prefix(tag)].append(label)
    return [f"{len(labels)} {prefix} counted from the text of {', '.join(dict.fromkeys(labels))} — the table itself "
            f"couldn't be read; check the count" for prefix, labels in by_prefix.items()]


def _compact(text: str) -> str:
    return re.sub(r"[\s\-‐‑–—#.]", "", text).upper()


def _left_out(spec_only: list[str], mentioned: list[str], never: list[str] = (), limit: int = 20) -> list[str]:
    def shown(tags: list[str]) -> str:
        return ", ".join(tags[:limit]) + (f" … ({len(tags)} in all)" if len(tags) > limit else "")

    flags = []
    if spec_only:
        flags.append(f"mentioned only in the specs, not on any drawing: {shown(spec_only)}")
    if mentioned:
        flags.append("named on a schedule sheet but not as a unit (inside a model number or a note, or a one-letter "
                     f"prefix outside a tag column): {shown(mentioned)}")
    if never:
        flags.append(f"named only on architectural, electrical, technology or AV sheets, so not equipment: "
                     f"{shown(list(never))}")
    return flags


def _seen_on_pages(catalogue, tags) -> dict[str, tuple[str, ...]]:
    """Every page each tag appears on, by sheet number (or document and page), however its dashes are written."""
    if not tags:
        return {}
    dash = "-‐‑–—"

    def spelled(tag: str) -> str:
        prefix, rest = tag.split("-", 1)
        rest = "".join(f"[{dash}]" if ch == "-" else re.escape(ch) for ch in rest)
        return rf"{re.escape(prefix)}[{dash}\s]?{rest}"

    pattern = re.compile(rf"(?<![A-Z0-9])(?:{'|'.join(spelled(t) for t in sorted(tags, key=len, reverse=True))})"
                         rf"(?![A-Z0-9])")
    canonical = {re.sub(rf"[{dash}\s]", "", t): t for t in tags}
    sheets = {(s.document, s.page): s for s in catalogue.sheets}
    places: dict[str, list[str]] = defaultdict(list)
    for record in catalogue.pages:
        sheet = sheets.get((record.document, record.page))
        place = sheet.number if sheet is not None and sheet.number else f"{_name(record.document)} p.{record.page}"
        for m in pattern.finditer(record.text):
            tag = canonical.get(re.sub(rf"[{dash}\s]", "", m.group(0)))
            if tag and place not in places[tag]:
                places[tag].append(place)
    return {tag: tuple(p) for tag, p in places.items()}


def _new_prefix_flags(schedules: list[Schedule]) -> list[str]:
    """One line per schedule that lists units whose prefix isn't in the equipment list yet."""
    flags = []
    for schedule in schedules:
        prefixes = list(dict.fromkeys(tag_prefix(row.tag) for row in schedule.rows if row.tag and row.kind))
        if prefixes:
            kind = next(row.kind for row in schedule.rows if row.kind)
            flags.append(f"{_label(schedule)}: {'prefix' if len(prefixes) == 1 else 'prefixes'} {', '.join(prefixes)} "
                         f"{'is' if len(prefixes) == 1 else 'are'}n't in the equipment list yet — counted as "
                         f"\"{kind}\" from the schedule's title; add {'it' if len(prefixes) == 1 else 'them'} to "
                         f"the equipment list if that's right")
    return flags


def _totals(items: list[InventoryItem], schedules: list[Schedule], equipment: Equipment,
            new_kinds: dict[str, str] | None = None, from_text: set[str] | None = None) -> list[FamilyTotal]:
    new_kinds = new_kinds or {}
    texted = {tag_prefix(tag) for tag in from_text or ()}
    kinds = {tag_prefix(tag): kind for tag, kind in new_kinds.items()}
    order: list[str] = []
    for schedule in schedules:
        for row in schedule.rows:
            if row.tag and tag_prefix(row.tag) not in order:
                order.append(tag_prefix(row.tag))
    by_prefix: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    quantity: dict[str, int] = {}
    added: dict[str, int] = {}       # tag → its quantity if the plan sheets of one floor and area were added (L1)
    added_on: dict[str, tuple[str, ...]] = {}     # tag → the plan sheets `added` adds up
    item_kinds: dict[str, str] = {}
    for item in items:
        if item.category != "TYPE ONLY":
            prefix = tag_prefix(item.tag)
            typed = item.reason.startswith(_A_TYPE)
            by_prefix[prefix]["TYPE PENDING" if typed and item.category == "PENDING" else item.category].append(item.tag)
            quantity[item.tag] = item.quantity or 0
            if item.summed:
                added[item.tag] = item.summed
                added_on[item.tag] = item.summed_on
            item_kinds.setdefault(prefix, item.kind)
    order += sorted(p for p in by_prefix if p not in order
                    and any(by_prefix[p].get(c) for c in ("PENDING", "TYPE PENDING", *COUNTED)))
    totals = []
    for prefix in order:
        groups = by_prefix[prefix]
        counted = sorted((t for c in COUNTED for t in groups.get(c, [])), key=_natural)
        flags = []
        wording = {
            "MISSING": "on the schedule only; no plan shows {them}",
            "DISCREPANCY": "listed twice (or more) on the schedules — counted once; confirm with the engineer",
            "EXTRA": "more on the drawings, not on a schedule — not counted",
            "ORPHANED": "seen only once in the set, not on a schedule — not counted",
            "EXISTING": "existing — not new work, not counted",
            "PENDING": "on a schedule sheet but not read from its table — check by eye, not counted",
            "TYPE PENDING": "a type the plans don't label — count by eye, not counted",
            ON_PLANS: ON_PLANS_WHY,
        }
        for category, text in wording.items():
            n = len(groups.get(category, []))
            if n:
                flags.append(f"{n} {text.format(them='it' if n == 1 else 'them')}")
        if prefix in texted:
            flags.append("counted from the schedule sheet's text — check the count")
        if prefix in kinds and prefix not in equipment.prefixes:
            flags.append(f"prefix {prefix} isn't in the equipment list yet — added from the schedule's title"
                         if kinds[prefix] != EQUIPMENT else
                         f"prefix {prefix} isn't in the equipment list yet, and its schedule's title doesn't say "
                         f"what it is — name it in the equipment list")
        kind = kinds.get(prefix) or equipment.prefixes.get(prefix) or item_kinds.get(prefix) or prefix
        scheduled = sum(quantity.get(t, 1) for t in counted)
        summed = sum(added.get(t) or quantity.get(t, 1) for t in counted)
        if summed > scheduled:           # ruling L1: the plan sheets of one floor and area were counted once
            lowered = sum(1 for t in counted if t in added)
            are = "tag is" if lowered == 1 else "tags are"
            # ruling 2 of 2026-10-11 and the lead's ruling on the T-005a review: a numbered unit tag is one unit in
            # the job, across floors and areas too; the sheets it is on are named with both numbers
            sheets = list(dict.fromkeys(s for t in counted for s in added_on.get(t, ())))
            on = f" ({_list(sheets)})" if sheets else ""
            flags.append(f"{lowered} {are} drawn on more than one plan sheet{on}, counted once, not "
                         f"added: {scheduled} units counted, {summed} if the sheets were added up — check")
        totals.append(FamilyTotal(kind, prefix, scheduled, compact_tags(counted), tuple(flags),
                                  summed if summed > scheduled else None))
    return totals
