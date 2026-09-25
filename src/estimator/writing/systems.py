"""The equipment grouped into systems, each with its evidence in one place (design §10.1).

A family is one tag prefix (VAV, EF, CH). A plant or multi-equipment group (chilled water,
kitchen exhaust, split systems) forms when one of its anchors is on the job; another family
joins it only when it shares a schedule sheet, a sequence passage, or a riser or control-diagram
sheet with a member. When in doubt a family stands alone, flagged. Everything else is a system
of its own family. Existing units make their own "Existing …" bundle. EXTRA and ORPHANED tags
are never in a quantity: they go into the flags.

Every lettered or numbered heading of the sequence of operation names a system ("FIRE PUMP",
"DOMESTIC WATER HEATERS"). A heading that names a bundle puts its section (the heading and the
paragraphs under it) first among that bundle's passages. A heading that names none makes a
system of its own: its quantity is the tags its paragraph names, else PENDING, and its evidence is
its section and any points list naming it.

The groupings, the sheet types that link families, the other names a family goes by, how a
sequence heading is told from a sentence, and the order of the systems live in
assets/system_groups.json, never here.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from estimator.catalogue.tags import Equipment, find_tags
from estimator.reading.inventory import COUNTED, _one_copy_per_sheet, compact_tags
from estimator.reading.sequences import POINTS, SEQUENCE

ASSETS = Path(__file__).resolve().parents[3] / "assets"
GROUPS_FILE = ASSETS / "system_groups.json"

MAX_PASSAGES = 8
MAX_PASSAGE_CHARS = 3000
_TAG, _PREFIX, _NAME = 3, 2, 1          # how strongly a paragraph names a system
_WHAT_ORDER = {SEQUENCE: 0, POINTS: 1}
# A numbered heading starts a paragraph: "3.02", "A.", "1)", "a." — and "A.General", written with no space.
_HEADING = re.compile(r"^[ \t]*(?:\d+(?:\.\d+)+|\d{1,3}[.)]|[A-Za-z][.)])(?:[ \t]+|$|(?=[A-Z][a-z]))", re.M)
_MARKER = re.compile(r"^[ \t]*(?:(?P<decimal>\d+(?:\.\d+)+)|(?P<number>\d{1,3})(?P<nclose>[.)])"
                     r"|(?P<upper>[A-Z])(?P<uclose>[.)])|(?P<lower>[a-z])(?P<lclose>[.)]))(?:[ \t]+|$|(?=[A-Z][a-z]))",
                     re.M)
_BLANK_LINE = re.compile(r"\n[ \t]*\n")
_ANY_TAG = re.compile(r"(?<![A-Za-z0-9])([A-Z]{1,6})[-‐‑–—](\d{1,3}[A-Z]?(?:[-.]\d{1,3}[A-Z]?)?)(?![A-Za-z0-9])")
_MORE_NUMBERS = re.compile(r"\s*(?:,|&|\band\b)\s*(\d{1,3}[A-Z]?)(?![A-Za-z0-9\-‐‑–—])")
_THRU = re.compile(r"\s*(?:thru|through|to)\s+(?:([A-Z]{1,6})[-‐‑–—])?(\d{1,3})(?![A-Za-z0-9])", re.I)
_MAX_RANGE = 60
_NEW_SYSTEM_ORDER = 10_000


@dataclass(frozen=True)
class Passage:
    where: str      # "23 09 93 SEQUENCE OF OPERATIONS, page 44"
    document: str
    page: int
    text: str       # the paragraph mentioning the system and the one after it, up to 3000 characters
    section: str = ""   # the sequence heading this passage sits under, when it is the system's own section


@dataclass(frozen=True)
class Family:
    prefix: str
    kind: str
    tags: tuple[str, ...]          # the units counted (or, with none counted, the ones still PENDING)
    quantity: int | None           # the scheduled count; None when nothing could be counted yet
    categories: dict[str, int]     # every tag of the prefix by category, EXTRA and ORPHANED included


@dataclass(frozen=True)
class BundleRow:
    """One schedule row of a bundle's units, with its schedule's title and sheet."""
    tag: str
    title: str
    sheet: str | None
    document: str
    page: int
    headers: tuple[str, ...]
    cells: dict[str, str]
    manufacturer: str | None
    model: str | None


@dataclass(frozen=True)
class SystemBundle:
    key: str                       # "VAV", "Chilled Water System", "Existing VAV"
    name: str                      # "Variable Air Volume Box", "Chilled Water System"
    families: tuple[Family, ...]
    schedule_rows: tuple[BundleRow, ...]
    schedule_notes: tuple[str, ...]
    controls_by: tuple[str, ...]
    notes: tuple                   # step 4 Notes naming one of the tags, the prefix or the kind
    passages: tuple[Passage, ...]  # sequence first, then points list; exact tags before the kind name
    devices: tuple                 # step 4 DeviceCounts on sheets where these tags appear
    sheets: tuple[str, ...]        # every sheet any of its tags is on
    flags: tuple[str, ...]
    group: bool = False
    existing: bool = False
    own: tuple[Passage, ...] = ()  # the sequence paragraphs that are this system's own: its heading's section
    heading: str = ""              # the sequence heading that made this system, when no schedule did
    siblings: tuple[str, ...] = () # tags of the same family written as another system (a split)


# --- the groupings file --------------------------------------------------------------------------

@dataclass(frozen=True)
class _Group:
    name: str
    anchors: tuple[str, ...]
    joiners: tuple[str, ...]

    @property
    def prefixes(self) -> tuple[str, ...]:
        return self.anchors + self.joiners


@dataclass(frozen=True)
class _Stage:
    names: frozenset[str]
    prefixes: frozenset[str]


@dataclass(frozen=True)
class _Headings:
    """How a heading of the sequence is told from a sentence, and matched to a bundle."""
    article: re.Pattern
    max_words: int
    max_chars: int
    sentence_words: frozenset[str]
    not_systems: frozenset[str]
    generic_words: frozenset[str]
    equipment_nouns: frozenset[str]
    describing_columns: tuple[str, ...]
    cut_at: re.Pattern
    dropped_first_words: frozenset[str]


@dataclass(frozen=True)
class _Rules:
    groups: tuple[_Group, ...]
    link_types: frozenset[str]
    link_disciplines: frozenset[str]
    also_called: dict[str, tuple[str, ...]]
    stages: tuple[_Stage, ...]
    headings: _Headings


@lru_cache(maxsize=4)
def _rules(path: Path = GROUPS_FILE) -> _Rules:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    groups = tuple(_Group(g["name"], tuple(g["anchors"]), tuple(g.get("joiners", ()))) for g in data["groups"])
    stages = tuple(_Stage(frozenset(s.get("names", ())), frozenset(s.get("prefixes", ())))
                   for s in data["order"]["stages"])
    h = data["sequence_headings"]
    headings = _Headings(
        re.compile(h["article"], re.I), int(h["max_title_words"]), int(h["max_title_chars"]),
        frozenset(w.lower() for w in h["sentence_words"]), frozenset(_plain(n) for n in h["not_systems"]),
        frozenset(w.lower() for w in h["generic_words"]), frozenset(w.lower() for w in h["equipment_nouns"]),
        tuple(c.upper() for c in h["describing_columns"]),
        re.compile(r"\s+(?:" + "|".join(re.escape(w) for w in h["main_phrase_ends_at"]) + r")\s+", re.I),
        frozenset(w.lower() for w in h["dropped_first_words"]))
    return _Rules(groups, frozenset(data["link_sheet_types"]), frozenset(data["link_disciplines"]),
                  {k: tuple(v) for k, v in data.get("also_called", {}).items()}, stages, headings)


# --- small helpers ---------------------------------------------------------------------------------

def _prefix(tag: str) -> str:
    return tag.split("-", 1)[0]


def _name(document: str) -> str:
    return document.rsplit("/", 1)[-1]


def _place(sheet: str | None, document: str, page: int) -> str:
    return sheet or f"{_name(document)} p.{page}"


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _unique(values) -> tuple:
    return tuple(dict.fromkeys(v for v in values if v))


def _where(backbone_where: str, page: int) -> str:
    label = re.sub(r"\s*\([^()]*\)\s*$", "", backbone_where).strip()
    return f"{label}, page {page}"


def _paragraphs(text: str) -> list[str]:
    """Paragraphs split on blank lines and at numbered headings ("3.02", "A.", "1)")."""
    found = []
    for block in _BLANK_LINE.split(text or ""):
        cuts = sorted({0, *(m.start() for m in _HEADING.finditer(block))})
        for start, end in zip(cuts, cuts[1:] + [len(block)]):
            paragraph = block[start:end].strip()
            if paragraph:
                found.append(paragraph)
    return found


def _names_pattern(names) -> re.Pattern | None:
    bodies = []
    for name in dict.fromkeys(n.strip() for n in names if n and n.strip()):
        body = r"[\s\-]+".join(re.escape(w) for w in re.split(r"[\s\-]+", name))
        bodies.append(rf"{body}(?:e?s)?")
    if not bodies:
        return None
    return re.compile(rf"(?<![A-Za-z0-9])(?:{'|'.join(bodies)})(?![A-Za-z0-9])", re.I)


@dataclass(frozen=True)
class _Matcher:
    """How strongly a piece of text names a system: an exact tag, the prefix, or a name for it."""
    tags: frozenset[str]
    prefixes: frozenset[str]
    words: re.Pattern | None       # the prefix as a word ("VAV boxes"), three letters or more, capitals
    names: re.Pattern | None       # the kind, the other names it goes by, the group's name
    siblings: frozenset[str] = frozenset()   # the family's tags written as another system

    @classmethod
    def of(cls, tags, prefixes, names, siblings=()) -> "_Matcher":
        long = sorted((p for p in prefixes if len(p) >= 3), key=len, reverse=True)
        words = (re.compile(rf"(?<![A-Za-z0-9])(?:{'|'.join(map(re.escape, long))})s?(?![A-Za-z0-9])")
                 if long else None)
        return cls(frozenset(tags), frozenset(prefixes), words, _names_pattern(names), frozenset(siblings))

    def rank(self, text: str, found: frozenset[str]) -> int:
        if self.tags & found:
            return _TAG
        if self.siblings & found:
            return 0                # it names the units of the family written as another system
        # Another tag of the prefix counts, except for one-letter prefixes (B, P): "B-2" is too often not a boiler.
        if (any(len(_prefix(t)) > 1 and _prefix(t) in self.prefixes for t in found)
                or (self.words and self.words.search(text))):
            return _PREFIX
        if self.names and self.names.search(text):
            return _NAME
        return 0


@dataclass(frozen=True)
class _Paragraph:
    what: str
    backbone: int
    where: str
    document: str
    page: int
    index: int                      # its place among the page's paragraphs
    text: str
    found: frozenset[str]

    @property
    def style(self) -> str | None:
        return _style(self.text)


# --- the families ----------------------------------------------------------------------------------

@dataclass
class _Fam:
    prefix: str
    kind: str
    family: Family
    evidence_tags: tuple[str, ...]      # every tag of the prefix this bundle speaks for
    row_tags: frozenset[str]
    places: list[str] = field(default_factory=list)
    schedule_places: set[str] = field(default_factory=set)
    flags: list[str] = field(default_factory=list)
    existing: bool = False
    first_seen: int = 0


def _category_flags(prefix: str, groups: dict[str, list[str]]) -> list[str]:
    flags = []
    n = len(groups.get("EXTRA", ()))
    if n:
        flags.append(f"{n} more {prefix} {'tag' if n == 1 else 'tags'} on the drawings but not on the schedule "
                     f"(EXTRA) — not priced until confirmed")
    n = len(groups.get("ORPHANED", ()))
    if n:
        flags.append(f"{n} more {prefix} {'tag' if n == 1 else 'tags'} seen only once in the set and on no "
                     f"schedule (ORPHANED) — not priced until confirmed")
    n = len(groups.get("PENDING", ()))
    if n:
        flags.append(f"{_plural(n, prefix + ' tag')} on a schedule sheet but not read from its table (PENDING) — "
                     f"count {'it' if n == 1 else 'them'} by eye before pricing")
    n = len(groups.get("DISCREPANCY", ()))
    if n:
        flags.append(f"{_plural(n, prefix + ' tag')} listed more than once on the schedules (DISCREPANCY) — "
                     f"counted once; confirm with the engineer")
    n = len(groups.get("MISSING", ()))
    if n:
        flags.append(f"{_plural(n, prefix + ' tag')} on the schedule but on no plan (MISSING) — counted; "
                     f"confirm before pricing")
    return flags


def _families(catalogue, reading, schedules) -> list[_Fam]:
    by_prefix: dict[str, list] = {}
    for item in reading.inventory:
        if item.category != "TYPE ONLY":
            by_prefix.setdefault(_prefix(item.tag), []).append(item)
    order = list(dict.fromkeys(_prefix(r.tag) for s in schedules for r in s.rows if r.tag))
    order += [p for p in by_prefix if p not in order]
    entries = {t.tag: t for t in catalogue.tags}

    rows_at: dict[str, list[str]] = {}
    for schedule in schedules:
        for row in schedule.rows:
            if row.tag:
                rows_at.setdefault(row.tag, []).append(_place(schedule.sheet, schedule.document, schedule.page))

    fams: list[_Fam] = []
    for position, prefix in enumerate(order):
        items = by_prefix.get(prefix)
        if not items:
            continue
        groups: dict[str, list[str]] = {}
        for item in items:
            groups.setdefault(item.category, []).append(item.tag)
        kind = items[0].kind
        counted = [i for i in items if i.category in COUNTED]
        pending = [i for i in items if i.category == "PENDING"]
        existing = [i for i in items if i.category == "EXISTING"]
        made = []
        if counted or pending:
            own = counted or pending
            quantity = sum(i.quantity or 0 for i in counted) if counted else None
            categories = dict(Counter(i.category for i in items if i.category != "EXISTING"))
            tags = tuple(i.tag for i in items if i.category != "EXISTING")
            made.append(_Fam(prefix, kind, Family(prefix, kind, tuple(i.tag for i in own), quantity, categories),
                             tags, frozenset(tags), flags=_category_flags(prefix, groups), first_seen=position))
        if existing:
            tags = tuple(i.tag for i in existing)
            made.append(_Fam(prefix, kind, Family(prefix, kind, tags, len(tags), {"EXISTING": len(tags)}),
                             tags, frozenset(tags), existing=True, first_seen=position,
                             flags=[f"{_plural(len(tags), prefix + ' tag')} marked existing on the schedule "
                                    f"({compact_tags(tags)}) — not new work; confirm any removal or reuse scope"]))
        for fam in made:
            places: list[str] = []
            for tag in fam.evidence_tags:
                places += rows_at.get(tag, [])
            fam.schedule_places = set(places)
            for tag in fam.evidence_tags:
                entry = entries.get(tag)
                if entry is not None:
                    places += list(entry.on_schedules) + list(entry.elsewhere)
            fam.places = list(dict.fromkeys(places))
        fams += made
    return fams


# --- grouping -----------------------------------------------------------------------------------------

def _link_places(catalogue, rules: _Rules) -> set[str]:
    return {_place(s.number, s.document, s.page) for s in catalogue.sheets
            if set(s.types) & rules.link_types and s.discipline in rules.link_disciplines}


def _co_mentioned(fams: list[_Fam], paragraphs: list[_Paragraph], rules: _Rules) -> set[frozenset[str]]:
    """Pairs of families named in the same sequence passage (a paragraph and the one after it)."""
    matchers = {f.prefix: _Matcher.of(f.evidence_tags, (f.prefix,), (f.kind, *rules.also_called.get(f.prefix, ())))
                for f in fams}
    by_page: dict[tuple[int, int], list[_Paragraph]] = {}
    for p in paragraphs:
        if p.what == SEQUENCE:
            by_page.setdefault((p.backbone, p.page), []).append(p)
    pairs: set[frozenset[str]] = set()
    for page in by_page.values():
        named = [{prefix for prefix, m in matchers.items() if m.rank(p.text, p.found)} for p in page]
        for i, here in enumerate(named):
            window = here | (named[i + 1] if i + 1 < len(named) else set())
            pairs.update(frozenset((a, b)) for a in window for b in window if a < b)
    return pairs


def _group(fams: list[_Fam], catalogue, paragraphs: list[_Paragraph], rules: _Rules):
    new = {f.prefix: f for f in fams if not f.existing}
    links = _link_places(catalogue, rules)
    mentioned = _co_mentioned(list(new.values()), paragraphs, rules)

    def linked(a: _Fam, b: _Fam) -> bool:
        return bool(a.schedule_places & b.schedule_places
                    or (set(a.places) & set(b.places) & links)
                    or frozenset((a.prefix, b.prefix)) in mentioned)

    formed: list[tuple[_Group, list[_Fam]]] = []
    for group in rules.groups:
        members = [new[p] for p in group.anchors if p in new]
        if not members:
            continue
        grew = True
        while grew:
            grew = False
            for prefix in group.joiners:
                fam = new.get(prefix)
                if fam is not None and fam not in members and any(linked(fam, m) for m in members):
                    members.append(fam)
                    grew = True
        members.sort(key=lambda f: group.prefixes.index(f.prefix))
        for fam in members:
            del new[fam.prefix]
        formed.append((group, members))
    for fam in new.values():
        for group, _ in formed:
            if fam.prefix in group.joiners:
                fam.flags.append(f"{compact_tags(fam.family.tags)} could belong to {group.name} — check")
    return formed


# --- the evidence ---------------------------------------------------------------------------------------

def _backbone_paragraphs(catalogue, reading, equipment: Equipment) -> list[_Paragraph]:
    texts = {(r.document, r.page): r.text for r in catalogue.pages}
    found: list[_Paragraph] = []
    for n, backbone in enumerate(reading.backbone):
        if backbone.duplicate_of or backbone.what not in _WHAT_ORDER:
            continue
        for page in range(backbone.first_page, backbone.last_page + 1):
            where = _where(backbone.where, page)
            for index, text in enumerate(_paragraphs(texts.get((backbone.document, page), ""))):
                found.append(_Paragraph(backbone.what, n, where, backbone.document, page, index, text,
                                        frozenset(find_tags(text, equipment)) | frozenset(_tags_in(text, equipment))))
    return found


def _passages(matcher: _Matcher, paragraphs: list[_Paragraph], first: tuple[Passage, ...] = (),
              covered: frozenset[int] = frozenset()) -> tuple[Passage, ...]:
    """The system's own sections first, then each paragraph naming it with the one after it: the
    sequence before the points list, exact tags before the prefix before the kind name."""
    chosen: list[Passage] = list(first[:MAX_PASSAGES])
    seen = {_plain(paragraphs[i].text) for i in covered}
    hits = []
    for i, p in enumerate(paragraphs):
        rank = matcher.rank(p.text, p.found)
        if rank:
            hits.append((_WHAT_ORDER[p.what], -rank, i))
    taken: set[int] = set(covered)
    for _, _, i in sorted(hits):
        if len(chosen) == MAX_PASSAGES:
            break
        if i in taken or _plain(paragraphs[i].text) in seen:
            continue
        p = paragraphs[i]
        parts = [i]
        after = i + 1
        if after < len(paragraphs) and (paragraphs[after].backbone, paragraphs[after].page) == (p.backbone, p.page):
            parts.append(after)
        taken.update(parts)
        seen.update(_plain(paragraphs[j].text) for j in parts)
        text = "\n\n".join(paragraphs[j].text for j in parts)[:MAX_PASSAGE_CHARS]
        chosen.append(Passage(p.where, p.document, p.page, text))
    return tuple(chosen)


def _bundle(key: str, name: str, members: list[_Fam], matcher: _Matcher, schedules, reading,
            paragraphs: list[_Paragraph], has_sequence: bool, group: bool = False,
            sections: tuple[tuple[str, tuple[int, ...]], ...] = (), heading: str = "",
            extra_flags: tuple[str, ...] = (), own: tuple[int, ...] = ()) -> SystemBundle:
    row_tags = frozenset().union(*(m.row_tags for m in members))
    existing = any(m.existing for m in members)
    rows: list[BundleRow] = []
    used = []
    for schedule in schedules:
        mine = [r for r in schedule.rows if r.tag in row_tags and bool(r.existing) == existing]
        if not mine:
            continue
        used.append(schedule)
        rows += [BundleRow(r.tag, schedule.title, schedule.sheet, schedule.document, schedule.page,
                           tuple(schedule.headers), dict(r.cells), r.manufacturer, r.model) for r in mine]
    sheets = _unique(p for m in members for p in m.places)
    on_sheets = set(sheets)
    devices = tuple(d for d in reading.devices if _place(d.sheet, d.document, d.page) in on_sheets)
    notes = tuple(n for n in reading.notes if matcher.rank(n.text, frozenset(find_tags(n.text, _equipment()))))
    if own:          # a split: the paragraphs its units open come first, and are its own
        title = compact_tags([t for m in members for t in m.family.tags])
        first, covered = _section_passages(paragraphs, ((title, own), *sections))
        mine, _ = _section_passages(paragraphs, ((title, own),))
    else:
        first, covered = _section_passages(paragraphs, sections)
        mine = first
    passages = _passages(matcher, paragraphs, first, covered)
    flags = [*extra_flags, *(f for m in members for f in m.flags)]
    if has_sequence and not passages and not existing:
        flags.append(f"No passage of the sequence of operation names {name} — read the sequence for it by hand")
    return SystemBundle(
        key=key, name=name, families=tuple(m.family for m in members), schedule_rows=tuple(rows),
        schedule_notes=_unique(n for s in used for n in s.notes),
        controls_by=_unique(c for s in used for c in s.controls_by),
        notes=notes, passages=passages, devices=devices, sheets=sheets, flags=tuple(flags),
        group=group, existing=existing, own=mine, heading=heading, siblings=tuple(sorted(matcher.siblings)),
    )


def _section_passages(paragraphs: list[_Paragraph], sections) -> tuple[tuple[Passage, ...], frozenset[int]]:
    """Each heading's section as passages of up to 3000 characters, a paragraph the job carries twice
    (a revised copy, a sheet repeating the spec) read once."""
    chosen: list[Passage] = []
    seen: set[str] = set()
    covered: set[int] = set()
    for title, indexes in sections:
        chunk: list[int] = []

        def flush():
            if chunk:
                first = paragraphs[chunk[0]]
                text = "\n\n".join(paragraphs[i].text for i in chunk)[:MAX_PASSAGE_CHARS]
                chosen.append(Passage(first.where, first.document, first.page, text, section=title))
                chunk.clear()

        for i in indexes:
            covered.add(i)
            key = _plain(paragraphs[i].text)
            if not key or key in seen:
                continue
            seen.add(key)
            length = sum(len(paragraphs[j].text) + 2 for j in chunk)
            if chunk and length + len(paragraphs[i].text) > MAX_PASSAGE_CHARS:
                flush()
            chunk.append(i)
        flush()
    return tuple(chosen), frozenset(covered)


# --- the sequence's headings ---------------------------------------------------------------------

def _plain(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", (text or "").casefold()))


def _singular(word: str) -> str:
    low = word.lower()
    if len(low) > 4 and low.endswith("ies"):
        return low[:-3] + "y"
    if len(low) > 3 and low.endswith("s") and not low.endswith(("ss", "us", "is")):
        return low[:-1]
    return low


def _style(text: str) -> str | None:
    """The numbering a paragraph starts with: "1.1", "A.", "1.", "1)", "a." or "a)"."""
    m = _MARKER.match(text or "")
    if not m:
        return None
    if m.group("decimal"):
        return "1.1"
    if m.group("number"):
        return "1" + m.group("nclose")
    if m.group("upper"):
        return "A" + m.group("uclose")
    return "a" + m.group("lclose")


def _after_marker(text: str) -> str:
    m = _MARKER.match(text or "")
    return (text[m.end():] if m else text or "").lstrip()


def _first_line(text: str) -> str:
    return _after_marker(text).split("\n", 1)[0].strip()


def _title(text: str, h: _Headings) -> str | None:
    """The heading's title ("Domestic Water Heaters (DWH-1, DWH-2)"), or None when the paragraph
    opens with a sentence, not a title."""
    first = _first_line(text)
    head, colon, _ = first.partition(":")
    title = (head if colon else first).strip().rstrip(" .;,")
    bare = " ".join(re.sub(r"\([^()]*\)", " ", title).split())
    if not bare or len(bare) > h.max_chars or (not colon and len(first) > h.max_chars):
        return None
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9/&'’%-]*", bare)
    if not words or len(words) > h.max_words or not re.search(r"[A-Za-z]{2}", bare):
        return None
    if any(w.lower() in h.sentence_words for w in words) or _plain(bare) in h.not_systems:
        return None
    return title


def _main_phrase(title: str, h: _Headings) -> str:
    bare = " ".join(re.sub(r"\([^()]*\)", " ", title).split())
    return h.cut_at.split(bare, 1)[0].strip()


def _head_noun(phrase: str, h: _Headings) -> str | None:
    words = re.findall(r"[A-Za-z]+", phrase or "")
    last = _singular(words[-1]) if words else ""
    return last if last in h.equipment_nouns else None


def _parts(title: str, h: _Headings) -> list[str]:
    """The things a heading names: two when it joins two pieces of equipment with "and"."""
    main = _main_phrase(title, h)
    pieces = re.split(r"\s+(?:and|&)\s+", main, maxsplit=1, flags=re.I)
    if len(pieces) == 2 and all(_head_noun(p, h) for p in pieces):
        return pieces
    return [main]


def _words(phrase: str, h: _Headings, acronyms: bool = True) -> set[str]:
    """The words of a name that tell one system from another: "Toilet exhaust fans" → {toilet}."""
    out = set()
    for raw in re.findall(r"[A-Za-z0-9]+", phrase or ""):
        if raw.isdigit():
            continue
        low = _singular(raw)
        if low in h.generic_words or raw.lower() in h.generic_words:
            continue
        if len(raw) < 3 and not (acronyms and raw.isupper() and len(raw) == 2):
            continue
        out.add(low)
    return out


_SMALL_WORDS = {"and", "or", "of", "for", "with", "the", "to", "in", "on", "at", "by", "a", "an", "w/"}


def _title_case(text: str) -> str:
    caps = text.upper() == text
    out = []
    for n, word in enumerate(text.split()):
        letters = re.sub(r"[^A-Za-z]", "", word)
        if n and word.lower() in _SMALL_WORDS:
            out.append(word.lower())
        elif (caps and 0 < len(letters) <= 2) or (not caps and len(letters) > 1 and letters.isupper()):
            out.append(word)                                   # CO, IT, BMS
        else:
            out.append(word[:1].upper() + (word[1:].lower() if caps else word[1:]))
    return " ".join(out)


def _kind_of(title: str, h: _Headings, prefixes: set[str]) -> str:
    """The system's kind as a header names it: "Unit Heaters (UH, Electric)" → "Unit Heater (Electric)"."""
    def note(m):
        words = [w for w in re.split(r"[,\s]+", m.group(1)) if w and w not in prefixes and not _ANY_TAG.fullmatch(w)]
        return f" ({' '.join(words)})" if words and len(words) <= 3 else " "

    text = " ".join(re.sub(r"\s*\(([^()]*)\)", note, title).split())
    words = [w for w in text.split()]
    while words and words[0].lower() in h.dropped_first_words and len(words) > 1:
        words.pop(0)                                           # "Associated CO Control System"
    text = " ".join(words)
    cut = h.cut_at.search(text)
    paren = text.find(" (")
    end = min(i for i in (cut.start() if cut else len(text), paren if paren >= 0 else len(text), len(text)))
    main, rest = text[:end], text[end:]
    pieces = main.rsplit(" ", 1)
    last = pieces[-1]
    if re.fullmatch(r"[A-Za-z]+", last) and _singular(last) != last.lower():
        cut_to = len(last) - (3 if last.lower().endswith("ies") and len(last) > 4 else 1)
        last = last[:cut_to] + ("y" if last.lower().endswith("ies") and len(last) > 4 else "")
    main = " ".join([*pieces[:-1], last])
    return _title_case(main + rest)


def _tags_in(text: str, equipment: Equipment, allowed: set[str] | None = None,
             spans: list | None = None) -> list[str]:
    """Every tag the text names, with lists and ranges written short read out in full:
    "RTU-1,2,3" → RTU-1, RTU-2, RTU-3; "VAV-1 thru VAV-4" → VAV-1 … VAV-4. A prefix the reading
    lists don't know counts only when `allowed` names it."""
    found: list[str] = []
    for m in _ANY_TAG.finditer(text or ""):
        prefix = m.group(1)
        if prefix not in equipment.prefixes and not (allowed and prefix in allowed):
            continue
        tag = f"{prefix}-{m.group(2)}"
        found.append(tag)
        stem = tag[: tag.rfind("-") + 1]
        end = m.end()
        while True:
            more = _MORE_NUMBERS.match(text, end)
            if more:
                found.append(stem + more.group(1))
                end = more.end()
                continue
            thru = _THRU.match(text, end)
            if thru and (thru.group(1) in (None, prefix)):
                last = re.match(r"(\d+)$", found[-1][len(stem):])
                if last and int(thru.group(2)) > int(last.group(1)) and int(thru.group(2)) - int(last.group(1)) <= _MAX_RANGE:
                    width = len(last.group(1)) if last.group(1).startswith("0") else 0
                    found += [f"{stem}{n:0{width}d}" for n in range(int(last.group(1)) + 1, int(thru.group(2)) + 1)]
                end = thru.end()
                continue
            break
        if spans is not None:
            spans.append((m.start(), end))
    return list(dict.fromkeys(found))


def _lead(text: str, equipment: Equipment) -> tuple[list[str], str]:
    """The tags a paragraph opens with and any title words after them:
    "4. DF-1,2,3,4 Destratification Fans: …" → ([DF-1 … DF-4], "Destratification Fans")."""
    first = _first_line(text)
    pieces = re.split(r":|\bshall\b|\bwill\b|\bserving\b|\bis\b|\bare\b", first, maxsplit=1)
    head = pieces[0]
    lead = _ANY_TAG.match(head.lstrip())
    if not lead or len(pieces) < 2:        # a line of a points table ("VAV-1 space temperature AI") leads nothing
        return [], ""
    spans: list = []
    tags = _tags_in(head, equipment, allowed={lead.group(1)}, spans=spans)
    rest = head
    for start, end in sorted(spans, reverse=True):
        rest = rest[:start] + " " + rest[end:]
    rest = re.sub(r"(?<![A-Za-z])(?:and|thru|through)(?![A-Za-z])|[,&]", " ", rest, flags=re.I)
    return tags, " ".join(rest.split())


@dataclass
class _Spec:
    """A system before its bundle is made: its families, how text names it, its sections."""
    key: str
    name: str
    members: list
    matcher: _Matcher
    first_seen: int
    group: bool = False
    words: frozenset[str] = frozenset()
    heads: frozenset[str] = frozenset()
    sections: list = field(default_factory=list)       # (title, paragraph indexes)
    heading: str = ""
    flags: list = field(default_factory=list)
    own: tuple[int, ...] = ()                          # a split's own paragraphs (those its tags open)
    split: bool = False

    @property
    def existing(self) -> bool:
        return any(m.existing for m in self.members)


def _describe(spec: _Spec, names, schedules, h: _Headings) -> None:
    """The words and head nouns a heading can name this system by."""
    words: set[str] = set()
    heads = set()
    for name in names:
        words |= _words(name, h, acronyms=False)
        head = _head_noun(name, h)
        if head:
            heads.add(head)
    tags = set(spec.matcher.tags)
    for schedule in schedules:
        rows = [r for r in schedule.rows if r.tag in tags]
        if not rows:
            continue
        words |= _words(re.sub(r"\bSCHEDULES?\b", " ", schedule.title or "", flags=re.I), h, acronyms=False)
        for row in rows:
            for header, cell in row.cells.items():
                if any(re.search(rf"\b{re.escape(c)}\b", (header or "").upper()) for c in h.describing_columns):
                    words |= _words(cell, h, acronyms=False)
    spec.words, spec.heads = frozenset(words), frozenset(heads)


def _title_names(title: str, spec: _Spec, h: _Headings, equipment: Equipment) -> bool:
    return bool(_strong(title, [spec], equipment)) or any(_passes(part, spec, h) for part in _parts(title, h))


def _strong(title: str, specs, equipment: Equipment) -> list[_Spec]:
    """The systems a title names by one of their tags or their prefix written in capitals."""
    tags = set(_tags_in(title, equipment))
    tokens = set(_CAPITALS.findall(title))
    return [s for s in specs if tags & s.matcher.tags or tokens & s.matcher.prefixes]


_CAPITALS = re.compile(r"(?<![A-Za-z0-9])[A-Z][A-Z0-9]{1,5}(?![A-Za-z0-9])")


def _bracket_prefixes(title: str, equipment: Equipment) -> set[str]:
    """Tag prefixes a title names in brackets: "Cabinet Unit Heaters (CUH)" → {CUH}."""
    inside = " ".join(re.findall(r"\(([^()]*)\)", title))
    return {t for t in _CAPITALS.findall(inside) if t in equipment.prefixes}


def _passes(part: str, spec: _Spec, h: _Headings) -> bool:
    words = _words(part, h)
    if not words:
        return False
    head = _head_noun(part, h)
    if head is None:
        return words <= spec.words          # "Heat tracing" names no piece of equipment: every word must match
    if spec.heads and head not in spec.heads:
        return False
    return len(words & spec.words) >= max(1, math.ceil(len(words) / 2))


def _match(title: str, section: list[int], specs: list[_Spec], paragraphs: list[_Paragraph], h: _Headings,
           equipment: Equipment) -> tuple[list[_Spec], list[str]]:
    """The systems a heading names, and the parts of it that name none (each a system of its own)."""
    strong = _strong(title, specs, equipment)
    if strong:
        return strong, []
    if _bracket_prefixes(title, equipment):
        return [], [title]                     # "Unit Heaters (UH, Electric)": a family on no schedule
    named: dict[int, int] = {}
    for i in section:
        for s in specs:
            if s.matcher.rank(paragraphs[i].text, paragraphs[i].found) >= _PREFIX:
                named[id(s)] = named.get(id(s), 0) + 1
    matched: list[_Spec] = []
    unmatched: list[str] = []
    for part in _parts(title, h):
        passing = [s for s in specs if _passes(part, s, h)]
        chosen = [s for s in passing if id(s) in named] or passing
        if chosen:
            matched += [s for s in chosen if s not in matched]
        elif _words(part, h):
            unmatched.append(part)
    if not matched and named:
        top = max(named.values())
        return [s for s in specs if named.get(id(s)) == top], []
    return matched, unmatched


def _depths(paragraphs: list[_Paragraph], indexes: list[int]) -> dict[int, int]:
    """How deep each paragraph of one sequence sits in its outline; text with no numbering sits
    under the heading before it."""
    depths: dict[int, int] = {}
    stack: list[str] = []
    for i in indexes:
        style = paragraphs[i].style
        if style is None:
            depths[i] = len(stack)
            continue
        if style == "1.1":
            stack = [style]
        elif style in stack:
            del stack[stack.index(style) + 1:]
        else:
            stack.append(style)
        depths[i] = len(stack) - 1
    return depths


def _under(i: int, indexes: list[int], depths: dict[int, int], paragraphs) -> list[int]:
    """The paragraph and those under it, up to the next heading at its level or above."""
    start = indexes.index(i)
    out = [i]
    for j in indexes[start + 1:]:
        if paragraphs[j].style is not None and depths[j] <= depths[i]:
            break
        out.append(j)
    return out


def _article_scope(paragraphs: list[_Paragraph], indexes: list[int], depths: dict[int, int],
                   h: _Headings) -> list[int]:
    """The paragraphs under a SEQUENCES OF OPERATION article of a larger section, when it has one.
    The article's number can be lost from the text: a line of its own titled like it counts too,
    up to the next numbered article."""
    scope: list[int] = []
    for n, i in enumerate(indexes):
        p = paragraphs[i]
        if p.style == "1.1" and h.article.search(_first_line(p.text)):
            under = _under(i, indexes, depths, paragraphs)[1:]
        elif any(h.article.fullmatch(line.strip()) for line in p.text.split("\n")):
            under = []
            for j in indexes[n + 1:]:
                if paragraphs[j].style == "1.1":
                    break
                under.append(j)
        else:
            continue
        if any(paragraphs[j].style for j in under):
            scope += [j for j in under if j not in scope]
    return scope


def _sequence_sections(paragraphs: list[_Paragraph], specs: list[_Spec], h: _Headings,
                       equipment: Equipment) -> list[tuple[str, list[int]]]:
    """Each system heading of each sequence, with the paragraphs under it."""
    by_backbone: dict[int, list[int]] = {}
    for i, p in enumerate(paragraphs):
        if p.what == SEQUENCE:
            by_backbone.setdefault(p.backbone, []).append(i)
    found: list[tuple[str, list[int]]] = []
    for indexes in by_backbone.values():
        depths = _depths(paragraphs, indexes)
        scope = _article_scope(paragraphs, indexes, depths, h)
        articles = bool(scope)
        scope = scope or indexes
        candidates: dict[str, list[tuple[int, str]]] = {}
        for n, i in enumerate(scope):
            style = paragraphs[i].style
            if style is None or (style == "1.1" and articles):
                continue
            title = _title(paragraphs[i].text, h)
            if title and ":" not in _first_line(paragraphs[i].text):
                # A title with no colon is a heading only with text under it, not a one-line item.
                below = "\n" in _after_marker(paragraphs[i].text).strip()
                deeper = n + 1 < len(scope) and depths[scope[n + 1]] > depths[i]
                title = title if below or deeper else None
            if title:
                candidates.setdefault(style, []).append((i, title))
        levels = sorted(candidates, key=lambda s: min(depths[i] for i, _ in candidates[s]))
        chosen = next((s for s in levels if any(_title_names(t, spec, h, equipment)
                                                 for _, t in candidates[s] for spec in specs)), None)
        if chosen is None:
            chosen = next((s for s in levels if len(candidates[s]) >= 2), None)
        if chosen is None:
            continue
        for i, title in candidates[chosen]:
            found.append((title, _under(i, scope, depths, paragraphs)))
    return found


def _short(title: str) -> str:
    """The title without a long note in brackets: "Rooftop Units with Heat Recovery (Heat Recovery
    where indicated on schedules)" → "Rooftop Units with Heat Recovery"."""
    return " ".join(re.sub(r"\s*\((?:[^()\s]+\s+){3,}[^()]*\)", " ", title).split())


def _read_headings(specs: list[_Spec], paragraphs: list[_Paragraph], rules: _Rules, equipment: Equipment,
                   entries: dict) -> list[_Spec]:
    """Every heading of the sequence names a system: its section goes to the systems it names, and
    a heading naming none makes a system of its own. A heading inside a section that opens with the
    tags of another family ("4. DF-1,2,3,4 Destratification Fans:" under "Fans") is read the same
    way. Returns the new systems."""
    h = rules.headings
    live = [s for s in specs if not s.existing]
    new: dict[str, _Spec] = {}
    known = {p for s in live for p in s.matcher.prefixes}

    def add_new(title: str, part: str, section: list[int], heading_text: str) -> None:
        named_prefixes = _bracket_prefixes(title, equipment) - known
        lead_tags, _ = _lead(heading_text, equipment)
        allowed = named_prefixes | {_prefix(t) for t in lead_tags}
        tags = [t for t in _tags_in(heading_text, equipment, allowed=allowed) if _prefix(t) not in known]
        if named_prefixes:
            tags = [t for t in tags if _prefix(t) in named_prefixes]
        kind = _kind_of(part, h, set(_CAPITALS.findall(title)))
        spec = new.get(_plain(kind))
        if spec is None:
            spec = _new_spec(kind, part, tags, min(named_prefixes, default=""), paragraphs[section[0]].where,
                             entries, len(new))
            new[_plain(kind)] = spec
        spec.sections.append((spec.heading, section))

    for title, section in _sequence_sections(paragraphs, live, h, equipment):
        matched, unmatched = _match(title, section, live, paragraphs, h, equipment)
        prefixes = {p for s in matched for p in s.matcher.prefixes}
        depths = _depths(paragraphs, section)
        taken: set[int] = set()
        for i in section[1:]:
            if i in taken:
                continue
            tags, words = _lead(paragraphs[i].text, equipment)
            if not tags or not words or {_prefix(t) for t in tags} & prefixes:
                continue
            under = _under(i, section, depths, paragraphs)
            taken.update(under)
            owners = [s for s in live if set(tags) & s.matcher.tags]
            if owners:
                for s in owners:
                    s.sections.append((f"{' '.join(tags[:1])} {words}".strip(), under))
            else:
                add_new(words, words, under, paragraphs[i].text)
        rest = [i for i in section if i not in taken]
        for spec in matched:
            mine = rest
            if spec.matcher.siblings:        # a split: not the paragraphs its family's other units open
                theirs: set[int] = set()
                for i in rest:
                    tags, _ = _lead(paragraphs[i].text, equipment)
                    if set(tags) & spec.matcher.siblings and not set(tags) & spec.matcher.tags:
                        theirs.update(_under(i, section, depths, paragraphs))
                mine = [i for i in rest if i not in theirs]
            spec.sections.append((_short(title), mine))
        for part in unmatched:
            add_new(title, part, rest, paragraphs[section[0]].text)
    return list(new.values())


def _split(spec: _Spec, paragraphs: list[_Paragraph], equipment: Equipment, rules: _Rules, entries: dict,
           quantities: dict[str, int]) -> list[_Spec]:
    """A family the sequence splits: each set of its units that opens paragraphs of its own
    ("RTU-4 and RTU-5 shall …", "EF-4: …") becomes a system of its own; the rest stay together.
    The sets opening the most paragraphs win; one overlapping a set already taken stays with it."""
    if spec.group or len(spec.members) != 1:
        return [spec]
    [fam] = spec.members
    counted = list(fam.family.tags)
    if fam.existing or len(counted) < 2 or fam.family.quantity is None:
        return [spec]
    by_backbone: dict[int, list[int]] = {}
    for i, p in enumerate(paragraphs):
        if p.what == SEQUENCE:
            by_backbone.setdefault(p.backbone, []).append(i)
    opened: dict[frozenset[str], list[int]] = {}
    led: dict[frozenset[str], set[str]] = {}
    times: Counter = Counter()
    for indexes in by_backbone.values():
        depths = _depths(paragraphs, indexes)
        for i in indexes:
            tags, _ = _lead(paragraphs[i].text, equipment)
            subset = frozenset(tags) & frozenset(counted)
            if subset and len(subset) < len(counted):
                have = opened.setdefault(subset, [])
                have += [j for j in _under(i, indexes, depths, paragraphs) if j not in have]
                led.setdefault(subset, set()).update(tags)
                times[subset] += 1
    if not opened:
        return [spec]
    ranked = sorted(opened, key=lambda s: (-times[s], -len(s), min(counted.index(t) for t in s)))
    chosen: list[frozenset[str]] = []
    for subset in ranked:
        if not any(subset & c for c in chosen):
            chosen.append(subset)
    rest = [t for t in counted if not any(t in c for c in chosen)]
    pieces = [(sorted(c, key=counted.index), True) for c in chosen] + ([(rest, False)] if rest else [])
    pieces.sort(key=lambda piece: counted.index(piece[0][0]))
    others = [t for t in fam.evidence_tags if t not in counted]
    made: list[_Spec] = []
    names = (fam.kind, *rules.also_called.get(fam.prefix, ()))
    for n, (tags, own) in enumerate(pieces):
        extra = [t for t in others if own and t in led.get(frozenset(tags), set())]
        evidence = tuple(tags) + tuple(extra)
        family = Family(fam.prefix, fam.kind, tuple(tags), sum(quantities.get(t, 1) for t in tags),
                        {"CONFIRMED": len(tags)})
        part = _Fam(fam.prefix, fam.kind, family, evidence, frozenset(evidence), existing=False,
                    first_seen=fam.first_seen)
        places: list[str] = []
        for tag in evidence:
            entry = entries.get(tag)
            if entry is not None:
                places += list(entry.on_schedules) + list(entry.elsewhere)
        part.places = list(dict.fromkeys([p for p in fam.places if p in fam.schedule_places] + places))
        part.schedule_places = set(fam.schedule_places)
        part.flags = []
        siblings = [t for t in fam.evidence_tags if t not in evidence]
        matcher = _Matcher.of(evidence, (fam.prefix,), names, siblings)
        piece = _Spec(compact_tags(tags), fam.kind, [part], matcher, fam.first_seen, split=True)
        piece.words, piece.heads = spec.words, spec.heads
        if own:
            where = paragraphs[opened[frozenset(tags)][0]].where
            one = len(tags) == 1
            piece.own = tuple(opened[frozenset(tags)])
            piece.flags.append(f"{compact_tags(tags)} written as a system of {'its' if one else 'their'} own — the "
                               f"sequence gives {'it' if one else 'them'} {'its' if one else 'their'} own paragraph "
                               f"({where}); check the split")
        made.append(piece)
    # The family's flags (EXTRA, ORPHANED, …) stay with the units left together, else the first part.
    holder = next((m for m, (_, own) in zip(made, pieces) if not own), made[0])
    holder.members[0].flags = list(fam.flags)
    # Tags of the family no part claimed (EXTRA ones no paragraph opens) go with the holder.
    claimed = {t for m in made for t in m.matcher.tags}
    loose = [t for t in others if t not in claimed]
    if loose:
        h_fam = holder.members[0]
        h_fam.evidence_tags = h_fam.evidence_tags + tuple(loose)
        h_fam.row_tags = frozenset(h_fam.evidence_tags)
        holder.matcher = _Matcher.of(h_fam.evidence_tags, (fam.prefix,), names,
                                     [t for t in fam.evidence_tags if t not in h_fam.evidence_tags])
    for m in made:                     # each part's siblings are the tags the other parts hold
        mine = set(m.matcher.tags)
        m.matcher = _Matcher.of(m.matcher.tags, (fam.prefix,), names, [t for t in fam.evidence_tags if t not in mine])
    return made


def _new_spec(kind: str, title: str, tags: list[str], prefix: str, where: str, entries: dict, n: int) -> _Spec:
    by_prefix: dict[str, list[str]] = {}
    for tag in tags:
        by_prefix.setdefault(_prefix(tag), []).append(tag)
    members = []
    for code, own in (by_prefix.items() if by_prefix else [(prefix, [])]):
        family = Family(code, kind, tuple(own), len(own) if own else None, {"SEQUENCE": len(own)} if own else {})
        fam = _Fam(code, kind, family, tuple(own), frozenset(own), first_seen=_NEW_SYSTEM_ORDER + n)
        places: list[str] = []
        for tag in own:
            entry = entries.get(tag)
            if entry is not None:
                places += list(entry.on_schedules) + list(entry.elsewhere)
        fam.places = list(dict.fromkeys(places))
        members.append(fam)
    names = (kind, title)
    matcher = _Matcher.of(tags, tuple(by_prefix) or ((prefix,) if prefix else ()), names)
    if tags:
        flag = (f"System made from the sequence heading “{title}” ({where}), on no readable schedule — its count is "
                f"the tags the sequence names ({compact_tags(tags)}); check it against the plans")
    else:
        flag = (f"System made from the sequence heading “{title}” ({where}), on no readable schedule and naming no "
                f"tags (PENDING) — count the units, then price it")
    return _Spec(kind, kind, members, matcher, _NEW_SYSTEM_ORDER + n, heading=title, flags=[flag])


@lru_cache(maxsize=1)
def _equipment() -> Equipment:
    return Equipment.load()


def _order(bundle: SystemBundle, first_seen: int, rules: _Rules) -> tuple[int, int]:
    if bundle.existing:
        return len(rules.stages) + 1, first_seen
    prefixes = {f.prefix for f in bundle.families}
    for n, stage in enumerate(rules.stages):
        if bundle.name in stage.names or (not bundle.group and prefixes & stage.prefixes):
            return n, first_seen
    for n, stage in enumerate(rules.stages):
        if prefixes & stage.prefixes:
            return n, first_seen
    return len(rules.stages), first_seen


def build_bundles(catalogue, reading) -> list[SystemBundle]:
    """Every system on the job with its evidence, in the order the proposal lists them."""
    rules = _rules()
    equipment = _equipment()
    schedules = _one_copy_per_sheet(list(reading.schedules))
    paragraphs = _backbone_paragraphs(catalogue, reading, equipment)
    has_sequence = any(b.what == SEQUENCE for b in reading.backbone)
    fams = _families(catalogue, reading, schedules)
    formed = _group(fams, catalogue, paragraphs, rules)
    grouped = {id(m) for _, members in formed for m in members}

    specs: list[_Spec] = []
    for group, members in formed:
        names = [group.name] + [n for m in members for n in (m.kind, *rules.also_called.get(m.prefix, ()))]
        matcher = _Matcher.of([t for m in members for t in m.evidence_tags], [m.prefix for m in members], names)
        spec = _Spec(group.name, group.name, members, matcher, min(m.first_seen for m in members), group=True)
        _describe(spec, names, schedules, rules.headings)
        specs.append(spec)
    for fam in fams:
        if id(fam) in grouped:
            continue
        names = (fam.kind, *rules.also_called.get(fam.prefix, ()))
        matcher = _Matcher.of(fam.evidence_tags, (fam.prefix,), names)
        key, name = (f"Existing {fam.prefix}", f"Existing {fam.kind}") if fam.existing else (fam.prefix, fam.kind)
        spec = _Spec(key, name, [fam], matcher, fam.first_seen)
        _describe(spec, names, schedules, rules.headings)
        specs.append(spec)
    entries = {t.tag: t for t in catalogue.tags}
    quantities = {i.tag: i.quantity for i in reading.inventory if i.category in COUNTED and i.quantity is not None}
    specs = [piece for spec in specs for piece in _split(spec, paragraphs, equipment, rules, entries, quantities)]
    keys = {s.key for s in specs}
    for spec in _read_headings(specs, paragraphs, rules, equipment, entries):
        while spec.key in keys:
            spec.key += " (sequence)"
        keys.add(spec.key)
        specs.append(spec)

    made = [(_bundle(s.key, s.name, s.members, s.matcher, schedules, reading, paragraphs, has_sequence,
                     group=s.group, sections=tuple((t, tuple(i)) for t, i in s.sections), heading=s.heading,
                     extra_flags=tuple(s.flags), own=s.own), s.first_seen) for s in specs]
    made.sort(key=lambda pair: _order(pair[0], pair[1], rules))
    return [bundle for bundle, _ in made]


def unbundled_flags(reading) -> list[str]:
    """What makes no system, for the review list: each type-only schedule (its "tag" is a list of
    type codes and its kind the schedule title, not a unit), and the families with tags on the
    drawings but no unit on a schedule (only EXTRA or ORPHANED)."""
    flags = [f"Type-only schedule {item.schedule or item.kind or 'with no title'} — count from the plans"
             for item in reading.inventory if item.category == "TYPE ONLY"]
    by_prefix: dict[str, list] = {}
    for item in reading.inventory:
        if item.category != "TYPE ONLY":
            by_prefix.setdefault(_prefix(item.tag), []).append(item)
    for prefix, items in by_prefix.items():
        categories = Counter(i.category for i in items)
        if set(categories) <= {"EXTRA", "ORPHANED"}:
            counts = ", ".join(f"{c} {categories[c]}" for c in ("EXTRA", "ORPHANED") if categories[c])
            flags.append(f"{compact_tags([i.tag for i in items])} ({items[0].kind}) on the drawings but on no "
                         f"schedule ({counts}) — no system written for {'it' if len(items) == 1 else 'them'}; "
                         f"not priced until confirmed")
    return flags
