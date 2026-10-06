"""The equipment inventory: every tag in exactly one of the estimator's categories, by the
quantity rules (`D:\\Estimation Assistant\\Brain\\Quantity rules.txt`).

The schedule is the source of quantities. The other drawing sheets check it and never change
the count without saying so. A count that can't be read is None and PENDING, never a silent 1.

A schedule row whose tag is really a type (AC-3.0, GCF-A labelled nine times on one plan, a
schedule with a QUANTITY column) stands for several units: its quantity is the schedule's
QUANTITY column, else its labels on the plan sheets times each sheet's floors, else PENDING.
"""
from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass, field, replace

from estimator.catalogue.job import CONTROLS_DISCIPLINES
from estimator.catalogue.tags import Equipment, tag_prefix
from estimator.reading.revisions import governing_pages
from estimator.reading.schedules import (BY_EYE, EQUIPMENT, Schedule, header_key, kind_from_title, quantity_header,
                                        vocabulary)

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
COUNT_CAUSE_WORDS = {"typical": "a typical unit at each place",
                     "shown_again": "one unit's tag on several plans",
                     "labelled_twice": "one unit labelled more than once"}
SAME_PLAN = "same plan as"         # a plan sheet showing the plan another sheet of the line shows (counted once)
_DECIMAL_TYPE = re.compile(r"^[A-Z]+-\d+\.\d+$")   # AC-3.0, HRU-4.0: a size, not a unit number
_A_TYPE = "A type, not one unit"
_RISER = re.compile(r"\bRISERS?\b", re.I)
_LABEL_NOISE = re.compile(r"^\((?:N|NEW)\)\s*|\s*\(?\s*TYP(?:ICAL)?\.?\s*\)?$", re.I)


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


@dataclass(frozen=True)
class FamilyTotal:
    kind: str                  # "Variable Air Volume Box"
    prefix: str                # "VAV"
    scheduled: int             # confirmed + missing + discrepancy (a duplicate counted once and flagged)
    tags: str                  # "VAV-101 thru VAV-112, VAV-114"
    flags: tuple[str, ...]


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


def _one_copy_per_sheet(schedules: list[Schedule], flags: list[str] | None = None) -> list[Schedule]:
    """A sheet number read from two documents (a marked-up copy of the same set, an older issue) is
    read once: its schedules come from the first document that carries it. Every page of that
    document with the number is kept — a schedule sheet can run onto a second page. Each sheet
    whose schedules are dropped is said in `flags`."""
    first: dict[str, str] = {}
    for s in schedules:
        if s.sheet:
            first.setdefault(s.sheet, s.document)
    kept: list[Schedule] = []
    dropped: dict[tuple[str, str], int] = defaultdict(int)
    for s in schedules:
        if not s.sheet or first[s.sheet] == s.document:
            kept.append(s)
        else:
            dropped[(s.sheet, s.document)] += 1
    if flags is not None:
        for (sheet, document), n in dropped.items():
            what = "1 schedule" if n == 1 else f"{n} schedules"
            flags.append(f"{what} on {sheet} in {_name(document)} not counted — the same sheet was read from "
                         f"{_name(first[sheet])}")
    return kept


@dataclass(frozen=True)
class Placements:
    """Where one tag is labelled: a line of a sheet's text that is the tag alone ("GCF-A"), never a note that
    names it ("TO EUH-1"). Plan sheets of the trades that carry controls scope, each sheet counted once; the
    sheets of one plan area (`plan_areas`: a floor drawn on a ductwork plan and on its piping and controls plan)
    count the labels of the one sheet that shows the most, never their sum."""
    on_plans: dict[str, int]                 # plan sheet → labels on it
    floors: dict[str, int]                   # plan sheet → the floors it stands for (1 when not typical)
    on_risers: dict[str, int] = field(default_factory=dict)   # riser diagram → labels on it, a cross-check
    same_as: dict[str, str] = field(default_factory=dict)     # plan sheet → the earlier sheet showing its plan area

    def _first(self, sheet: str) -> str:
        return self.same_as.get(sheet, sheet)

    @property
    def total(self) -> int:
        best: dict[str, int] = {}
        for sheet, n in self.on_plans.items():
            area = self._first(sheet)
            best[area] = max(best.get(area, 0), n * self.floors.get(sheet, 1))
        return sum(best.values())

    @property
    def most_on_one_sheet(self) -> int:
        return max((n * self.floors.get(sheet, 1) for sheet, n in self.on_plans.items()), default=0)

    def plans_text(self) -> str:
        """ "M-101 4, M-113 1 × 10 floors, M-201 4 same plan as M-101": each sheet, a repeat of a plan area named so."""
        return ", ".join(f"{sheet} {n}" + (f" × {self.floors[sheet]} floors" if self.floors.get(sheet, 1) > 1 else "")
                         + (f" {SAME_PLAN} {self._first(sheet)}" if self._first(sheet) != sheet else "")
                         for sheet, n in self.on_plans.items())

    def risers_text(self) -> str:
        return ", ".join(f"{sheet} {n}" for sheet, n in self.on_risers.items())


def _label_key(text: str) -> str:
    return re.sub(r"[\s\-‐‑–—#]", "", _LABEL_NOISE.sub("", text.strip())).upper()


# ---- the plan areas: the sheets that show one plan (the dossier's counts and the type-tag check) -------
# Lead ruling (FINAL-D): an undercount is far worse than an overcount, so two sheets are one plan only when the
# evidence is clear; when it cannot be told they are counted apart (the higher count) and `plan_area_doubts` names
# them for the counts line.

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
    r"|\b(?P<before>[A-Z][A-Z0-9]*)\s+(?P<named>WING|TOWER|BUILDING|BLDG|ANNEX|HALL|PAVILION)\b"
    r"|\b(?P<alone>NORTH(?:EAST|WEST)?|SOUTH(?:EAST|WEST)?|EAST|WEST|LOWER|UPPER|ANNEX|ADDITION)\b"
    r"|\b(?P<roof>HIGH|LOW)(?=\s+ROOF\b)"
    r"|\b(?P<of>\d{1,2}\s+OF\s+\d{1,2})\b", re.I)
_NOT_A_PART = frozenset({"PLAN", "PLANS", "AND", "THE", "OF", "HVAC", "MECHANICAL", "PIPING", "DUCTWORK"})
_ENLARGED = re.compile(r"\b(?:ENLARGED|PARTIAL)\b", re.I)
AREA_OVERLAP = 0.6       # share of the smaller sheet's tags another sheet must repeat to be the same plan
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
            parts.add(m.group("named").upper() if before in _NOT_A_PART else f"{before} {m.group('named').upper()}")
        else:
            parts.add(re.sub(r"\s+", " ", m.group(0).upper()))
    return tuple(sorted(parts))


def _area_key(title: str | None) -> tuple | None:
    """The floor (and the parts of it) a plan's title names: "HVAC PIPING AND CONTROLS FIRST FLOOR PLAN",
    "HVAC 1ST FLR PLAN" and "LEVEL ONE PLAN" are all floor 1; "FIRST FLOOR PLAN - TOWER 2" is floor 1 of TOWER 2.
    None when no one floor can be read: the title names none, names several ("FIRST AND SECOND FLOOR PLAN"), or
    names an enlarged or partial plan (one that repeats part of a floor)."""
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
    return tuple(floors), _parts(rest_text)


def _evidence(tags) -> set:
    """The tags that can prove two sheets show one plan: each tag once on the sheet when the counts are given (a
    tag at several places is a typical type tag, on every floor alike), else every tag."""
    if hasattr(tags, "items"):
        return {tag for tag, n in tags.items() if n == 1}
    return set(tags)


def _plain_title(sheet) -> str:
    """The title's words, its own sheet number taken out ("M-301 MECHANICAL PLAN" is "MECHANICAL PLAN")."""
    title = (sheet.title or "").upper()
    if sheet.number:
        title = title.replace(sheet.number.upper(), " ")
    return " ".join(re.findall(r"[A-Z0-9]+", title))


def _same_tags(a: set, b: set) -> bool:
    shared = len(a & b)
    return shared >= AREA_SHARED and shared >= AREA_OVERLAP * min(len(a), len(b))


def plan_areas(plans) -> dict[tuple[str, int], int]:
    """Which plan sheets show the same plan area: (document, page) -> an area number, given (sheet, the tags on
    it) for each plan sheet (a set, or tag -> places on the sheet). Two sheets are one area only when the evidence
    is clear: their titles name the same readable floor and the same parts (TOWER 1, DORM WING, NORTH, LOWER ROOF)
    and they are in one document or repeat each other's unit tags (a tag once on each; a tag at several places
    proves nothing); or neither title names a floor and they are in one document with the same title text and
    repeat each other's unit tags. Anything else is two areas (the higher count). Pure."""
    areas: list[tuple[tuple | None, str, set, set]] = []      # (key, plain title, documents, unit tags so far)
    found: dict[tuple[str, int], int] = {}
    for sheet, tags in plans:
        key, title, evidence = _area_key(sheet.title), _plain_title(sheet), _evidence(tags)
        for number, (area_key, area_title, documents, area_tags) in enumerate(areas):
            if key is not None and area_key == key and (sheet.document in documents
                                                        or _same_tags(area_tags, evidence)):
                break
            if (key is None and area_key is None and title and area_title == title and sheet.document in documents
                    and _same_tags(area_tags, evidence)):
                break
        else:
            number = len(areas)
            areas.append((key, title, set(), set()))
        areas[number][2].add(sheet.document)
        areas[number][3].update(evidence)
        found[(sheet.document, sheet.page)] = number
    return found


def plan_area_doubts(plans, areas: dict[tuple[str, int], int]) -> list[tuple[tuple[str, int], tuple[str, int]]]:
    """The pairs of plan sheets `plan_areas` keeps apart that may still show one plan: they repeat each other's
    tags and their titles do not name two different floors or parts (one names no floor, or both name the same
    one). Counted apart, the higher count; the counts line names them so the estimator can check. Pure."""
    sheets = [(sheet, set(tags), _area_key(sheet.title)) for sheet, tags in plans]
    doubts = []
    for i, (a, a_tags, a_key) in enumerate(sheets):
        for b, b_tags, b_key in sheets[i + 1:]:
            ka, kb = (a.document, a.page), (b.document, b.page)
            if areas.get(ka) == areas.get(kb) or not _same_tags(a_tags, b_tags):
                continue
            if a_key is None or b_key is None or a_key == b_key:
                doubts.append((ka, kb))
    return doubts


def placements(catalogue, tags: Iterable[str], typicals: Sequence = (),
               pages: Collection[tuple[str, int]] | None = None) -> dict[str, Placements]:
    """Each tag's labels on the plan sheets (times each typical sheet's floors, 1.4) and on the riser
    diagrams, read from the governing page of each sheet. A type sized "X.0" is also labelled "X" (HRU-4)."""
    keys: dict[str, str] = {}
    for tag in tags:
        keys.setdefault(_label_key(tag), tag)
    for tag in list(keys.values()):
        if tag.endswith(".0"):
            keys.setdefault(_label_key(tag[:-2]), tag)
    if not keys:
        return {}
    floors = {t.sheet: len(t.floors) for t in typicals if t.sheet}
    if pages is None:
        pages = governing_pages(catalogue, (), [t.sheet for t in typicals])
    sheets = {(s.document, s.page): s for s in catalogue.sheets}
    plan_sheets: dict[str, object] = {}                       # place → its plan sheet, in page order
    on_plans: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    on_risers: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for record in catalogue.pages:
        sheet = sheets.get((record.document, record.page))
        if (sheet is None or (record.document, record.page) not in pages or sheet.discipline not in CONTROLS_DISCIPLINES
                or "Schedules" in sheet.types):
            continue
        riser = bool(_RISER.search(sheet.title or "")) or any("riser" in t for t in sheet.types)
        if not riser and "Plans" not in sheet.types:
            continue
        place = sheet.number or f"{_name(record.document)} p.{record.page}"
        bucket = on_risers if riser else on_plans
        if not riser:
            plan_sheets.setdefault(place, sheet)
        lines = record.text.splitlines()
        skip = False
        for n, line in enumerate(lines):
            if skip:
                skip = False
                continue
            tag = keys.get(_label_key(line))
            if tag is None and n + 1 < len(lines) and re.fullmatch(r"\s*[A-Z]{1,6}\s*", line):
                tag = keys.get(_label_key(line + lines[n + 1]))      # a tag bubble: "VAV" over "5-7"
                skip = tag is not None
            if tag is not None:
                bucket[tag][place] += 1
    # The plan areas, as the dossier's counts work them out: a floor drawn twice shows its tags twice.
    labelled: dict[str, set] = defaultdict(set)
    for tag, places in on_plans.items():
        for place in places:
            labelled[place].add(tag)
    areas = plan_areas([(sheet, {tag: on_plans[tag][place] for tag in labelled[place]})
                        for place, sheet in plan_sheets.items()])
    first: dict[int, str] = {}
    same_as: dict[str, str] = {}
    for place, sheet in plan_sheets.items():
        area = areas[(sheet.document, sheet.page)]
        first.setdefault(area, place)
        if first[area] != place:
            same_as[place] = first[area]

    def placed(tag: str) -> Placements:
        mine = dict(on_plans.get(tag, {}))
        # a sheet repeats the first sheet of its area that shows this tag (another sheet of the area may not)
        firsts: dict[str, str] = {}
        repeats: dict[str, str] = {}
        for place in mine:
            area = same_as.get(place, place)
            firsts.setdefault(area, place)
            if firsts[area] != place:
                repeats[place] = firsts[area]
        return Placements(mine, {s: floors.get(s, 1) for s in mine}, dict(on_risers.get(tag, {})), repeats)

    return {tag: placed(tag) for tag in set(on_plans) | set(on_risers)}


def _count_in(cell: str | None) -> int | None:
    """A quantity cell's count: "719", "(2)", "2 EA"; None when it holds none."""
    match = re.search(r"\d+", (cell or "").replace(",", ""))
    return int(match.group(0)) if match and not re.search(r"\d\s*[./]\s*\d", cell or "") else None


def _as_type(tag: str, kind: str, schedule: Schedule, row, placed: Placements | None, label: str,
             seen: tuple[str, ...]) -> InventoryItem | None:
    """The row as a type, counted (1.3), or None when it is one unit. It is a type when its tag has a decimal
    size, when its schedule has a QUANTITY column, or when the plans label it four or more times on one sheet
    (floors counted)."""
    column = quantity_header(schedule)
    if getattr(row, "shares", 1) > 1:
        return None      # the row lists several tags ("A THRU C"): the tags are the count, one unit each
    if _DECIMAL_TYPE.match(tag):
        why = f"its tag has a decimal size, {tag}"
    elif column:
        why = f"the schedule has a {column} column"
    elif placed is not None and placed.total >= TYPE_PLACED and placed.most_on_one_sheet >= TYPE_ON_ONE_SHEET:
        why = f"it is labelled {placed.total} times on the plans"
    else:
        return None
    count = _count_in(row.cells.get(column)) if column else None
    action = ""
    if count is not None:
        how = f"quantity {count} from the schedule's {column} column"
    elif placed is not None and placed.total:
        count, action = placed.total, "confirm"
        how = f"{count} counted on the plans ({placed.plans_text()}) — check the count"
    else:
        how = "not counted on the plans yet — count it before pricing"
        action = "confirm"
    if placed is not None and placed.on_risers:
        how += (f"; the riser diagrams show {sum(placed.on_risers.values())} ({placed.risers_text()}), "
                f"a cross-check")
    return InventoryItem(tag, kind, "CONFIRMED" if count is not None else "PENDING", count, label, seen,
                         f"{_A_TYPE} ({why}): {how}", action)


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


def build_inventory(catalogue, schedules: list[Schedule], typicals: Sequence = (),
                    pages: Collection[tuple[str, int]] | None = None
                    ) -> tuple[list[InventoryItem], list[FamilyTotal], list[str]]:
    """`typicals` (reading/devices.py) multiply a type's labels on a typical plan by its floors; `pages` are the
    governing pages they are read from (by default, worked out here)."""
    equipment = Equipment.load()
    dropped: list[str] = []
    schedules = _one_copy_per_sheet(list(schedules), dropped)
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
            first_row.setdefault(row.tag, (schedule, row))
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
            where = _list(own)
            typed = None if tag in existing else _as_type(tag, kind, *first_row[tag], placed.get(tag), label, seen)
            if typed is not None:
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
                items.append(InventoryItem(tag, kind, "CONFIRMED", 1, label, seen,
                                           f"On the schedule ({where}) and on {_sheets(len(on_drawings))} "
                                           f"({_list(on_drawings)})", ""))
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

    for schedule in schedules:
        if not schedule.type_only or not schedule.rows:
            continue
        counted_types = _type_rows(schedule, {item.tag for item in items})
        if counted_types:
            items += counted_types
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
    item_kinds: dict[str, str] = {}
    for item in items:
        if item.category != "TYPE ONLY":
            prefix = tag_prefix(item.tag)
            typed = item.reason.startswith(_A_TYPE)
            by_prefix[prefix]["TYPE PENDING" if typed and item.category == "PENDING" else item.category].append(item.tag)
            quantity[item.tag] = item.quantity or 0
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
        totals.append(FamilyTotal(kind, prefix, sum(quantity.get(t, 1) for t in counted), compact_tags(counted),
                                  tuple(flags)))
    return totals
