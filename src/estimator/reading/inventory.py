"""The equipment inventory: every tag in exactly one of the estimator's categories, by the
quantity rules (`D:\\Estimation Assistant\\Brain\\Quantity rules.txt`).

The schedule is the source of quantities. The other drawing sheets check it and never change
the count without saying so. A count that can't be read is None and PENDING, never a silent 1.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, replace

from estimator.catalogue.tags import Equipment
from estimator.reading.schedules import Schedule, vocabulary

COUNTED = ("CONFIRMED", "MISSING", "DISCREPANCY")
FROM_TEXT = "counted from the schedule sheet's text; the table itself couldn't be read — check the count"


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
    run: list[tuple[str, str, int, str]] = []

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
        if run and not (run[-1][0] == stem and run[-1][1] == width and run[-1][2] + 1 == int(digits)):
            close()
        run.append((stem, width, int(digits), tag))
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


def build_inventory(catalogue, schedules: list[Schedule]) -> tuple[list[InventoryItem], list[FamilyTotal], list[str]]:
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
        return entry.kind if entry else equipment.prefixes.get(tag.split("-", 1)[0], "Equipment")

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
    existing: set[str] = set()
    from_text: dict[str, str] = {}      # tag → the schedule it was counted under, from a sheet's text
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
            if schedule.from_text:
                from_text.setdefault(row.tag, _label(schedule))
            if row.existing:
                existing.add(row.tag)
    scheduled_prefixes = {tag.split("-", 1)[0] for tag in listings}
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
        if entry.tag.split("-", 1)[0] in equipment.schedule_only:
            return True
        return (any(_compact(entry.tag) in other_text[p] for p in entry.on_schedules)
                and not any(p in drawings for p in entry.elsewhere))

    mentioned: list[str] = []

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
            if tag in existing:
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
        elif entry.times == 1:
            items.append(InventoryItem(tag, kind, "ORPHANED", None, None, seen,
                                       f"Appears only once in the whole set ({_list(seen)}) and on no schedule — "
                                       f"unclear scope; don't price until confirmed", "exclude pending"))
        else:
            why = ("but not on any schedule" if tag.split("-", 1)[0] in scheduled_prefixes
                   else "and no schedule lists this kind of equipment")
            items.append(InventoryItem(tag, kind, "EXTRA", None, None, seen,
                                       f"Shown on {_list(seen)} {why} — don't price until confirmed",
                                       "exclude pending"))

    for schedule in schedules:
        if not schedule.type_only or not schedule.rows:
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
            + _left_out(spec_only, mentioned))


def _from_text_flags(from_text: dict[str, str]) -> list[str]:
    """One line per family counted from a schedule sheet's text."""
    by_prefix: dict[str, list[str]] = defaultdict(list)
    for tag, label in from_text.items():
        by_prefix[tag.split("-", 1)[0]].append(label)
    return [f"{len(labels)} {prefix} counted from the text of {', '.join(dict.fromkeys(labels))} — the table itself "
            f"couldn't be read; check the count" for prefix, labels in by_prefix.items()]


def _compact(text: str) -> str:
    return re.sub(r"[\s\-‐‑–—#.]", "", text).upper()


def _left_out(spec_only: list[str], mentioned: list[str], limit: int = 20) -> list[str]:
    def shown(tags: list[str]) -> str:
        return ", ".join(tags[:limit]) + (f" … ({len(tags)} in all)" if len(tags) > limit else "")

    flags = []
    if spec_only:
        flags.append(f"mentioned only in the specs, not on any drawing: {shown(spec_only)}")
    if mentioned:
        flags.append("named on a schedule sheet but not as a unit (inside a model number or a note, or a one-letter "
                     f"prefix outside a tag column): {shown(mentioned)}")
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
        prefixes = list(dict.fromkeys(row.tag.split("-", 1)[0] for row in schedule.rows if row.tag and row.kind))
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
    texted = {tag.split("-", 1)[0] for tag in from_text or ()}
    kinds = {tag.split("-", 1)[0]: kind for tag, kind in new_kinds.items()}
    order: list[str] = []
    for schedule in schedules:
        for row in schedule.rows:
            if row.tag and row.tag.split("-", 1)[0] not in order:
                order.append(row.tag.split("-", 1)[0])
    by_prefix: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for item in items:
        if item.category != "TYPE ONLY":
            by_prefix[item.tag.split("-", 1)[0]][item.category].append(item.tag)
    order += sorted(p for p in by_prefix if p not in order and by_prefix[p].get("PENDING"))
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
        }
        for category, text in wording.items():
            n = len(groups.get(category, []))
            if n:
                flags.append(f"{n} {text.format(them='it' if n == 1 else 'them')}")
        if prefix in texted:
            flags.append("counted from the schedule sheet's text — check the count")
        if prefix in kinds and prefix not in equipment.prefixes:
            flags.append(f"prefix {prefix} isn't in the equipment list yet — added from the schedule's title")
        totals.append(FamilyTotal(kinds.get(prefix) or equipment.prefixes.get(prefix, prefix), prefix, len(counted),
                                  compact_tags(counted), tuple(flags)))
    return totals
