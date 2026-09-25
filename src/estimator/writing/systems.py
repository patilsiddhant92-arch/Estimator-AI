"""The equipment grouped into systems, each with its evidence in one place (design §10.1).

A family is one tag prefix (VAV, EF, CH). A plant or multi-equipment group (chilled water,
kitchen exhaust, split systems) forms when one of its anchors is on the job; another family
joins it only when it shares a schedule sheet, a sequence passage, or a riser or control-diagram
sheet with a member. When in doubt a family stands alone, flagged. Everything else is a system
of its own family. Existing units make their own "Existing …" bundle. EXTRA and ORPHANED tags
are never in a quantity: they go into the flags.

The groupings, the sheet types that link families, the other names a family goes by and the
order of the systems live in assets/system_groups.json, never here.
"""
from __future__ import annotations

import json
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
_HEADING = re.compile(r"^[ \t]*(?:\d+(?:\.\d+)+|\d{1,3}[.)]|[A-Z][.)])[ \t]+", re.M)
_BLANK_LINE = re.compile(r"\n[ \t]*\n")


@dataclass(frozen=True)
class Passage:
    where: str      # "23 09 93 SEQUENCE OF OPERATIONS, page 44"
    document: str
    page: int
    text: str       # the paragraph mentioning the system and the one after it, up to 3000 characters


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
class _Rules:
    groups: tuple[_Group, ...]
    link_types: frozenset[str]
    link_disciplines: frozenset[str]
    also_called: dict[str, tuple[str, ...]]
    stages: tuple[_Stage, ...]


@lru_cache(maxsize=4)
def _rules(path: Path = GROUPS_FILE) -> _Rules:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    groups = tuple(_Group(g["name"], tuple(g["anchors"]), tuple(g.get("joiners", ()))) for g in data["groups"])
    stages = tuple(_Stage(frozenset(s.get("names", ())), frozenset(s.get("prefixes", ())))
                   for s in data["order"]["stages"])
    return _Rules(groups, frozenset(data["link_sheet_types"]), frozenset(data["link_disciplines"]),
                  {k: tuple(v) for k, v in data.get("also_called", {}).items()}, stages)


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

    @classmethod
    def of(cls, tags, prefixes, names) -> "_Matcher":
        long = sorted((p for p in prefixes if len(p) >= 3), key=len, reverse=True)
        words = (re.compile(rf"(?<![A-Za-z0-9])(?:{'|'.join(map(re.escape, long))})s?(?![A-Za-z0-9])")
                 if long else None)
        return cls(frozenset(tags), frozenset(prefixes), words, _names_pattern(names))

    def rank(self, text: str, found: frozenset[str]) -> int:
        if self.tags & found:
            return _TAG
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
                                        frozenset(find_tags(text, equipment))))
    return found


def _passages(matcher: _Matcher, paragraphs: list[_Paragraph]) -> tuple[Passage, ...]:
    hits = []
    for i, p in enumerate(paragraphs):
        rank = matcher.rank(p.text, p.found)
        if rank:
            hits.append((_WHAT_ORDER[p.what], -rank, i))
    covered: set[int] = set()
    chosen: list[Passage] = []
    for _, _, i in sorted(hits):
        if len(chosen) == MAX_PASSAGES:
            break
        if i in covered:
            continue
        p = paragraphs[i]
        parts = [i]
        after = i + 1
        if after < len(paragraphs) and (paragraphs[after].backbone, paragraphs[after].page) == (p.backbone, p.page):
            parts.append(after)
        covered.update(parts)
        text = "\n\n".join(paragraphs[j].text for j in parts)[:MAX_PASSAGE_CHARS]
        chosen.append(Passage(p.where, p.document, p.page, text))
    return tuple(chosen)


def _bundle(key: str, name: str, members: list[_Fam], matcher: _Matcher, schedules, reading,
            paragraphs: list[_Paragraph], has_sequence: bool, group: bool = False) -> SystemBundle:
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
    passages = _passages(matcher, paragraphs)
    flags = [f for m in members for f in m.flags]
    if has_sequence and not passages and not existing:
        flags.append(f"No passage of the sequence of operation names {name} — read the sequence for it by hand")
    return SystemBundle(
        key=key, name=name, families=tuple(m.family for m in members), schedule_rows=tuple(rows),
        schedule_notes=_unique(n for s in used for n in s.notes),
        controls_by=_unique(c for s in used for c in s.controls_by),
        notes=notes, passages=passages, devices=devices, sheets=sheets, flags=tuple(flags),
        group=group, existing=existing,
    )


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

    made: list[tuple[SystemBundle, int]] = []
    for group, members in formed:
        names = [group.name] + [n for m in members for n in (m.kind, *rules.also_called.get(m.prefix, ()))]
        matcher = _Matcher.of([t for m in members for t in m.evidence_tags], [m.prefix for m in members], names)
        bundle = _bundle(group.name, group.name, members, matcher, schedules, reading, paragraphs, has_sequence,
                         group=True)
        made.append((bundle, min(m.first_seen for m in members)))
    for fam in fams:
        if id(fam) in grouped:
            continue
        matcher = _Matcher.of(fam.evidence_tags, (fam.prefix,), (fam.kind, *rules.also_called.get(fam.prefix, ())))
        key, name = (f"Existing {fam.prefix}", f"Existing {fam.kind}") if fam.existing else (fam.prefix, fam.kind)
        made.append((_bundle(key, name, [fam], matcher, schedules, reading, paragraphs, has_sequence),
                     fam.first_seen))
    made.sort(key=lambda pair: _order(pair[0], pair[1], rules))
    return [bundle for bundle, _ in made]


def unbundled_flags(reading) -> list[str]:
    """The families with tags on the drawings but no unit on a schedule (only EXTRA or ORPHANED):
    they make no system, so they are reported here for the review list."""
    by_prefix: dict[str, list] = {}
    for item in reading.inventory:
        if item.category != "TYPE ONLY":
            by_prefix.setdefault(_prefix(item.tag), []).append(item)
    flags = []
    for prefix, items in by_prefix.items():
        categories = Counter(i.category for i in items)
        if set(categories) <= {"EXTRA", "ORPHANED"}:
            counts = ", ".join(f"{c} {categories[c]}" for c in ("EXTRA", "ORPHANED") if categories[c])
            flags.append(f"{compact_tags([i.tag for i in items])} ({items[0].kind}) on the drawings but on no "
                         f"schedule ({counts}) — no system written for {'it' if len(items) == 1 else 'them'}; "
                         f"not priced until confirmed")
    return flags
