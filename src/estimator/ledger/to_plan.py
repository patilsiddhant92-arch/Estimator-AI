"""From the ledger to the systems the writer takes (design 2026-09-29 §3): one PlannedSystem per family or group,
in ledger order, its quantity the printed (highest) count with a "*" note when the count is contradicted, and the
ids of the facts it rests on. The writer, the checks and the Evidence Package read a JobPlan as before."""
from __future__ import annotations

import re
from dataclasses import replace

from estimator.ledger.facts import ADDED, CONTRADICTED, Fact, Ledger, where_short
from estimator.writing.whole_job import Family, JobPlan, PlannedSystem

_SPACES = re.compile(r"\s+")


def _squash(text) -> str:
    return _SPACES.sub(" ", str(text or "")).strip()


def _bracket(sid: str) -> str:
    return f"[{sid}]" if sid else ""


def _same(value, printed) -> bool:
    """A value is the printed count when it reads as that number (" 14" is 14)."""
    return str(value).strip() == str(printed)


def _naming(name: str) -> re.Pattern:
    """The name as a whole word: "CH" finds "CH" and "CH-1" but not "CHWP", "CHILLED" or "EACH"."""
    return re.compile(rf"(?<![A-Za-z0-9]){re.escape(name)}(?![A-Za-z0-9])", re.I)


def _printed(ledger: Ledger, fact: Fact) -> tuple[int | None, str, str]:
    """(the printed count, its source id in brackets, its quote): the highest value's; the fact's own source and
    quote when no contradiction holds it."""
    printed = ledger.printed_count(fact.id)
    if printed is None:
        return None, _bracket(fact.source_id), fact.quote
    if _same(fact.value, printed):
        return printed, _bracket(fact.source_id), fact.quote
    other = next((c for c in fact.contradictions if _same(c.value, printed)), None)
    if other is None:
        return printed, _bracket(fact.source_id), fact.quote
    return printed, _bracket(other.source_id), other.quote


_COUNTS_LINE = "equipment counts for"


_SHEET_NUMBER = re.compile(r"^[A-Z][A-Z0-9.\-]*\d[A-Z0-9.\-]*$")


def _clause(quote: str, number) -> str:
    """The clause of a counts line ("; " between clauses) holding the number, without the line's "PREFIX (kind): "
    head: "schedule rows 16". The whole quote when no clause holds it."""
    quote = _squash(quote)
    if number is None:
        return quote
    holds = re.compile(rf"(?<![\w.\-]){re.escape(str(number).strip())}(?![\w.])")
    for clause in quote.split("; "):
        clause = re.sub(r"^[^:;]*\):\s*", "", clause).strip()
        if holds.search(clause):
            return clause
    return quote


def place_words(where: str, quote: str, number=None) -> str:
    """A count's place in plain words: the counts line's clause holding the number ("schedule rows 16") when the
    source is the equipment counts, else the sheet number alone ("M-201", "M-102.00" from a sheet's text or its
    picture), never the document and page."""
    where = _squash(where)
    if where.casefold().startswith(_COUNTS_LINE) and _squash(quote):
        return _clause(quote, number)
    place = where_short(where).split(",", 1)[0].strip()
    first = place.split(" ", 1)[0]
    return first if _SHEET_NUMBER.match(first) else place


def _other_count(where: str, quote: str, value) -> str:
    """Another count in the note: the counts line's words carry their number; a sheet "lists" it."""
    place = place_words(where, quote, value)
    counts_line = _squash(where).casefold().startswith(_COUNTS_LINE) and _squash(quote)
    return place if counts_line else f"{place} lists ({value})"


def count_note(ledger: Ledger, fact: Fact) -> str:
    """The "*" note under a system whose count is contradicted: the printed count and its place, then each other
    count and its place, in plain words ("*Qty. (14) per M-201; QUANTITY column total 12."). "" when the fact is not
    contradicted or none of its values is a number."""
    if fact.state != CONTRADICTED:
        return ""
    printed, sid, quote = _printed(ledger, fact)
    if printed is None:
        return ""
    others = [(fact.value, fact.source_id, fact.quote)] + [(c.value, c.source_id, c.quote) for c in fact.contradictions]
    others = [(_squash(v), s, q) for v, s, q in others if not _same(v, printed)]
    place = place_words(ledger.sources.get(sid.strip("[]"), sid), quote, printed)
    rest = "; ".join(_other_count(ledger.sources.get(s.strip("[]"), s), q, v) for v, s, q in others)
    return f"*Qty. ({printed}) per {place}; {rest}."


def _tags(ledger: Ledger, prefix: str) -> tuple[str, ...]:
    from estimator.writing.assemble import expand_tags
    unit = ledger.find("unit", prefix)
    if unit is None or not _squash(unit.value):
        return (prefix,)
    return tuple(expand_tags([_squash(unit.value)]) or (prefix,))


def _matches(ledger: Ledger, *names: str) -> list[Fact]:
    """The sequence_match facts whose value is one of the names, in the names' order, each fact once."""
    found: list[Fact] = []
    for name in names:
        key = _squash(name).casefold()
        found += [f for f in ledger.of_kind("sequence_match")
                  if _squash(f.value).casefold() == key and f not in found]
    return found


def _note(ledger: Ledger, subject: str, *names: str) -> str:
    """The first note of this subject naming one of the names as a whole word, the names tried in order."""
    notes = [f for f in ledger.of_kind("note") if f.subject.casefold() == subject]
    for name in (_squash(n) for n in names):
        if not name:
            continue
        naming = _naming(name)
        for fact in notes:
            if naming.search(_squash(fact.value)):
                return _squash(fact.value)
    return ""


def _alternate(ledger: Ledger, *names: str) -> str:
    value = _note(ledger, "alternate", *names).casefold()
    return "add" if value.startswith("add") else "deduct" if value.startswith("deduct") else ""


def _family(ledger: Ledger, fact: Fact) -> tuple[Family, list[str]]:
    prefix = fact.subject
    tags = _tags(ledger, prefix)
    unit = ledger.find("unit", prefix)
    header = f"{_squash(fact.value)} {_squash(unit.value) if unit else prefix}".strip()
    count = ledger.find("count", prefix)
    quantity, source, quote = _printed(ledger, count) if count else (None, "", "")
    ids = [f.id for f in ledger.about(prefix)]
    return Family(header, tags, quantity, source, quote), ids


def _system(ledger: Ledger, fact: Fact) -> PlannedSystem:
    prefix = fact.subject
    family, ids = _family(ledger, fact)
    count = ledger.find("count", prefix)
    matched = _matches(ledger, prefix)
    sequence = tuple(_bracket(m.source_id) for m in matched)
    note = count_note(ledger, count) if count else ""
    if count is None and fact.stage == "sequence":
        why = "Named in the sequence of operation; no drawing shows it."
    elif count is None or count.state == ADDED:     # no schedule settled a count: the name alone proves nothing
        why = "Seen on the drawings but on no schedule; confirm it exists."
    else:
        why = f"From the job ledger: {len(ids) + len(matched)} facts."
    return PlannedSystem(key=prefix, header=family.header, kind=_squash(fact.value), tags=family.tags,
                         quantity=family.quantity, quantity_source=family.quantity_source,
                         quantity_quote=family.quantity_quote, sequence_sources=sequence,
                         schedule_sources=(_bracket(count.source_id),) if count else (), group="",
                         alternate=_alternate(ledger, prefix), exception=_note(ledger, "exception", prefix), why=why,
                         sequence_section=", ".join(sequence), families=(), count_note=note,
                         facts=tuple(ids + [m.id for m in matched]))


def _front_end(ledger: Ledger) -> dict:
    facts = ledger.of_kind("front_end")
    by = lambda subject: [f for f in facts if f.subject.casefold() == subject]      # noqa: E731
    mode = next((_squash(f.value) for f in by("mode")), "")
    return {"mode": mode if mode in ("new-system", "extend-existing") else "",
            "existing_name": next((_squash(f.value) for f in by("existing_name")), ""),
            "lines": [_squash(f.value) for f in by("line")],
            "notes": [_squash(f.value) for f in by("note")],
            "sources": sorted({_bracket(f.source_id) for f in facts if f.source_id})}


def _damper_prefixes() -> tuple[str, ...]:
    from estimator.writing.style import load_house_style
    style = load_house_style()
    return tuple(p.upper() for p in getattr(style, "packaged_units", {}).get("damper_prefixes", ("MD",)))


_FIRE_SMOKE_PREFIXES = ("FSD", "FD", "SD")
_FIRE_SMOKE_WORDS = re.compile(r"\bfire\s+dampers?\b|\bsmoke\s+dampers?\b|\bfire\s*/\s*smoke\b|\bfire\s+smoke\b", re.I)


def _lead(subject: str) -> str:
    """A tag or label's leading token in capitals: "MD-1" and "MD on 88x40 duct" both lead with "MD"."""
    return re.split(r"[\s\-(/,]", _squash(subject), maxsplit=1)[0].upper()


def _is_motorized_damper(subject: str, prefixes: tuple[str, ...]) -> bool:
    """A motorized damper's tag or label: it leads with a damper prefix ("MD-1", "MD on 88x40 smoke purge duct") or
    says "damper". A fire or smoke damper is not one (those stay where they are): it leads with FSD, FD or SD, or
    says "fire damper", "smoke damper", "fire/smoke" or "fire smoke". A smoke purge duct is not a smoke damper."""
    text = _squash(subject)
    if _lead(text) in _FIRE_SMOKE_PREFIXES or _FIRE_SMOKE_WORDS.search(text):
        return False
    return _lead(text) in prefixes or "damper" in text.casefold()


def _names_of(system: PlannedSystem) -> list[str]:
    """What a link's value may call the system: its key, its tags and their prefixes."""
    names = [system.key, *system.tags, *(t.split("-")[0] for t in system.tags)]
    return [n for n in dict.fromkeys(_squash(n) for n in names) if n]


def _sheets(ledger: Ledger, facts: list[Fact]) -> list[str]:
    """The sheet numbers the facts cite, in order, each once."""
    sheets: list[str] = []
    for fact in facts:
        sid = fact.source_id.strip("[]")
        sheet = place_words(ledger.sources.get(sid, ""), fact.quote) if sid in ledger.sources else ""
        if sheet and sheet not in sheets:
            sheets.append(sheet)
    return sheets


def _family_prefix(family: Family) -> str:
    """A family's prefix, from its first tag ("MD-1" or "MD")."""
    return _lead(family.tags[0]) if family.tags else ""


def _less_dampers(system: PlannedSystem, links_of: dict[str, list[Fact]]) -> PlannedSystem:
    """A group holding a damper family gives up the dampers a fan claims: the family's count drops by the links,
    and the family (with its tags) leaves the group when every damper is claimed."""
    families, changed = [], False
    for family in system.families:
        links = links_of.get(_family_prefix(family), [])
        if links and family.quantity is not None:
            changed = True
            left = family.quantity - len(links)
            if left <= 0:
                continue
            family = replace(family, quantity=left)
        families.append(family)
    if not changed:
        return system
    return replace(system, families=tuple(families), tags=tuple(t for f in families for t in f.tags))


def _link_dampers(ledger: Ledger, systems: list[PlannedSystem]) -> list[PlannedSystem]:
    """A motorized damper linked to a fan joins that fan (or the group the fan is in): the link and the damper's
    unit and location facts go to the fan's facts and the fan counts it. The damper family, alone or inside a group,
    keeps only the dampers no fan claims, naming the sheets to look at; when every damper is claimed, there is no
    damper system (or no damper family in the group)."""
    prefixes = _damper_prefixes()
    damper_keys = {s.key.upper() for s in systems if not s.group and s.key.upper() in prefixes}
    grouped = {_family_prefix(f) for s in systems if s.group for f in s.families} & set(prefixes)
    joined: dict[str, list[str]] = {}
    links_of: dict[str, list[Fact]] = {}
    for link in ledger.of_kind("link"):
        subject = _squash(link.subject)
        if not _is_motorized_damper(subject, prefixes):
            continue
        value = _squash(link.value)
        target = next((s for s in systems if s.key.upper() not in damper_keys
                       and any(_naming(n).search(value) for n in _names_of(s) if n.upper() not in prefixes)), None)
        if target is None:
            continue
        own = [f.id for f in ledger.about(subject) if f.kind in ("unit", "location")]
        joined.setdefault(target.key, []).extend([link.id, *own])
        family = _lead(subject)
        if family not in damper_keys and family not in grouped:
            family = next(iter(sorted(damper_keys)), "") or next(iter(sorted(grouped)), "")
        links_of.setdefault(family, []).append(link)
    if not joined:
        return systems
    planned: list[PlannedSystem] = []
    for system in systems:
        if system.group:
            system = _less_dampers(system, links_of)
        if system.key in joined:
            ids = joined[system.key]
            facts = tuple(dict.fromkeys([*system.facts, *ids]))
            count = sum(1 for f in ids if ledger.facts[f].kind == "link")
            system = replace(system, facts=facts, linked_dampers=system.linked_dampers + count)
        elif system.key.upper() in links_of and not system.group:
            links = links_of[system.key.upper()]
            if system.quantity is not None:
                left = system.quantity - len(links)
                if left <= 0:
                    continue
                system = replace(system, quantity=left)
            locations = [f for f in ledger.of_kind("location") if _naming(system.key).search(_squash(f.subject))]
            sheets = _sheets(ledger, locations + links)
            why = "Dampers no fan claims" + (f"; see {', '.join(sheets)}." if sheets else ".")
            system = replace(system, why=why)
        planned.append(system)
    return planned


SPLIT_SYSTEM = "Split System"       # the Master Template entry the split units no group took are written under
_LONG_NAME_WORDS = 4                # a family name longer than this is a description: the template's word replaces it
_OUTSIDE_BRACKETS = re.compile(r",(?![^()]*\))")
_MEMBER = re.compile(r"^([^()]*?)\s*\(([^()]*)\)$")
_TIMES = re.compile(r"(?:\s*×|\s+x)\s*\d+\s*$", re.I)        # "HRU-3 x3", "HRU-3×3"; never the X of "TX1"
_TAG_TIMES = re.compile(r"(?<![A-Za-z0-9])([A-Za-z]{1,6}(?:-[A-Za-z0-9.]+)+)(?:\s*×|\s+x)\s*(\d+)(?![A-Za-z0-9])",
                        re.I)


def _family_facts(ledger: Ledger) -> dict[str, Fact]:
    """The family facts by subject (any case), the first of a subject kept."""
    return {f.subject.casefold(): f for f in reversed(ledger.of_kind("family"))}


def _family_of_tag(families: dict[str, Fact], tag: str) -> Fact | None:
    """The family a bare tag belongs to ("WAC-1.0" is the WAC family's): the longest subject it starts with, then a
    dash."""
    key = tag.casefold()
    owners = [s for s in families if key.startswith(s + "-") and len(key) > len(s) + 1]
    return families[max(owners, key=len)] if owners else None


def _members(ledger: Ledger, group: Fact) -> list[tuple[Fact, tuple[str, ...] | None]]:
    """A group's members in the group's order, each family once: (its family fact, the tags it lists, or None when
    it lists none). A member is "PREFIX", "PREFIX (TAG-1, TAG-2 x3, TAG-4 thru 6)" or a bare tag of a family
    ("WAC-1.0"); commas inside brackets do not part members. A member naming no family is left out."""
    from estimator.writing.assemble import expand_tags
    families = _family_facts(ledger)
    found: dict[str, list] = {}
    for piece in (p.strip() for p in _OUTSIDE_BRACKETS.split(_squash(group.value))):
        m = _MEMBER.match(piece)
        head, listed = (m.group(1).strip(), m.group(2)) if m else (_TIMES.sub("", piece), "")
        fact = families.get(head.casefold())
        tags = expand_tags([_TIMES.sub("", t) for t in listed.split(",") if t.strip()]) if listed else []
        if fact is None and head and not listed:
            fact, tags = _family_of_tag(families, head), [head]
        if fact is None:
            continue
        entry = found.setdefault(fact.subject.casefold(), [fact, []])
        if entry[1] is not None:
            entry[1] = entry[1] + [t for t in tags if t not in entry[1]] if tags else None
    return [(fact, tuple(tags) if tags is not None else None) for fact, tags in found.values()]


def _parts(ledger: Ledger, groups: list[Fact]) -> dict[str, list[tuple[Fact, tuple[str, ...] | None]]]:
    """What each family gives the groups, by family subject (any case): (the group, None) when the group takes the
    whole family (a member listing no tags, or tags that are not a proper part of the family's own); (the group,
    its tags) when the group takes only the tags it lists, the rest staying a system of its own. A family the first
    group took whole is no later group's; a tag is taken once."""
    parts: dict[str, list[tuple[Fact, tuple[str, ...] | None]]] = {}
    for group in groups:
        for fact, listed in _members(ledger, group):
            claims = parts.setdefault(fact.subject.casefold(), [])
            if any(tags is None for _, tags in claims):
                continue
            own = _tags(ledger, fact.subject)
            wanted = {t.upper() for t in listed or ()}
            if not wanted or not wanted < {t.upper() for t in own}:
                if not claims:
                    claims.append((group, None))
                continue
            taken = {t.upper() for _, tags in claims for t in tags or ()}
            tags = tuple(t for t in own if t.upper() in wanted and t.upper() not in taken)
            if tags:
                claims.append((group, tags))
    return parts


def _stated(ledger: Ledger, group: Fact) -> dict[str, tuple[int, tuple[Fact, ...]]]:
    """The unit counts the group fact and the link facts give a tag ("HRU-3 x3"), by tag in capitals: summed across
    the facts, each fact read once."""
    found: dict[str, tuple[int, tuple[Fact, ...]]] = {}
    for fact in (group, *ledger.of_kind("link")):
        text = _squash(fact.value) if fact is group else f"{_squash(fact.subject)} {_squash(fact.value)}"
        seen: set[str] = set()
        for m in _TAG_TIMES.finditer(text):
            tag = m.group(1).upper()
            if tag in seen:
                continue
            seen.add(tag)
            number, facts = found.get(tag, (0, ()))
            found[tag] = (number + int(m.group(2)), facts + (fact,))
    return found


def _part_count(ledger: Ledger, fact: Fact, tags: tuple[str, ...], group: Fact) -> tuple[int | None, list[Fact]]:
    """The units a group's part of a family holds, and the facts stating them: each tag's stated count ("x3"); one
    for a tag no fact counts when the tags are unit tags (the family's count is no more than its distinct tags);
    None when a tag has no count and the tags are type tags (or the family has no count): never a guess that
    undershoots."""
    stated = _stated(ledger, group)
    own = {t.upper() for t in _tags(ledger, fact.subject)}
    printed = _family(ledger, fact)[0].quantity
    unit_tags = printed is not None and printed <= len(own)
    total, used = 0, []
    for tag in tags:
        if tag.upper() in stated:
            number, facts = stated[tag.upper()]
            total += number
            used += [f for f in facts if f not in used]
        elif unit_tags:
            total += 1
        else:
            return None, used
    return total, used


def _part_family(fact: Fact, family: Family, tags: tuple[str, ...], count: int | None, used: list[Fact]) -> Family:
    """The group's part of a family: its own tags and count, the count's source the first fact stating one (the
    family's own count when the tags are unit tags)."""
    from estimator.writing.write import tag_list
    if count is None:
        source, quote = "", ""
    elif used:
        source, quote = _bracket(used[0].source_id), used[0].quote
    else:
        source, quote = family.quantity_source, family.quantity_quote
    return Family(f"{_squash(fact.value)} {tag_list(list(tags))}".strip(), tags, count, source, quote)


def _group_system(ledger: Ledger, group: Fact, parts: dict) -> tuple[PlannedSystem, list[str]]:
    """The group's system, its families in ledger order (the whole family, or the part the group lists), and the
    questions its parts with no count raise."""
    from estimator.writing.write import tag_list
    name = _squash(group.subject)
    families, ids, members, asks = [], [group.id], [], []
    for fact in ledger.of_kind("family"):
        for owner, tags in parts.get(fact.subject.casefold(), []):
            if owner is not group:
                continue
            family, member_ids = _family(ledger, fact)
            if tags is not None:
                count, used = _part_count(ledger, fact, tags, group)
                family = _part_family(fact, family, tags, count, used)
                member_ids = member_ids + [f.id for f in used]
                if count is None:
                    asks.append(f"How many {fact.subject} units does the group “{name}” take ({tag_list(list(tags))})? "
                                "No sheet gives their count, so the header reads Qty (##).")
            families.append(family)
            ids += [i for i in member_ids if i not in ids]
            members.append(fact)
    prefixes = [m.subject for m in members]
    matched = _matches(ledger, group.subject, *prefixes)
    sequence = tuple(_bracket(m.source_id) for m in matched)
    tags = tuple(t for f in families for t in f.tags)
    counts = [ledger.find("count", p) for p in prefixes]
    notes = [f"{p}: {note}" for p, c in zip(prefixes, counts) if c for note in [count_note(ledger, c)] if note]
    system = PlannedSystem(key=name, header=name, kind=name, tags=tags, quantity=None, quantity_source="",
                           quantity_quote="", sequence_sources=sequence,
                           schedule_sources=tuple(_bracket(c.source_id) for c in counts if c), group=name,
                           alternate=_alternate(ledger, group.subject, *prefixes),
                           exception=_note(ledger, "exception", group.subject, *prefixes),
                           why=f"From the job ledger: {len(ids) + len(matched)} facts.",
                           sequence_section=", ".join(sequence), families=tuple(families),
                           count_note="\n".join(notes), facts=tuple(ids + [m.id for m in matched]))
    return system, asks


def _rest_system(ledger: Ledger, fact: Fact, claims: list) -> PlannedSystem | None:
    """The family as a system of its own: whole when no group took it; the tags no group listed when groups took
    parts of it, its count the family's printed count less the parts' counts when both are known and that leaves at
    least one unit per remaining tag, else the family's printed count unchanged. None when groups took it all."""
    from estimator.writing.write import tag_list
    system = _system(ledger, fact)
    if not claims:
        return system
    if any(tags is None for _, tags in claims):
        return None
    taken = {t.upper() for _, tags in claims for t in tags}
    left = tuple(t for t in system.tags if t.upper() not in taken)
    if not left:
        return None
    quantity = system.quantity
    counts = [_part_count(ledger, fact, tags, group)[0] for group, tags in claims]
    if quantity is not None and None not in counts and quantity - sum(counts) >= len(left):
        quantity = quantity - sum(counts)
    return replace(system, header=f"{system.kind} {tag_list(list(left))}".strip(), tags=left, quantity=quantity)


def _split_prefixes() -> frozenset[str]:
    """The split system unit prefixes: the Master Template's Split System entry's applies_to prefixes."""
    from estimator.writing.templates import load_templates
    template = next((t for t in load_templates() if t.name == SPLIT_SYSTEM), None)
    return frozenset(template.prefixes) if template else frozenset()


def _suffixes(system: PlannedSystem) -> set[str]:
    """A system's tags without their prefix: AC-LOBBY-1 gives "LOBBY-1"."""
    head = system.key.upper() + "-"
    return {t.upper()[len(head):] for t in system.tags if t.upper().startswith(head)}


def _split_system(ledger: Ledger, name: str, members: list[PlannedSystem]) -> PlannedSystem:
    """One block of split units: one family per unit system, in order, with their facts, sources and notes."""
    families = tuple(Family(s.header, s.tags, s.quantity, s.quantity_source, s.quantity_quote) for s in members)
    prefixes = [s.key for s in members]
    facts = tuple(dict.fromkeys(f for s in members for f in s.facts))
    sequence = tuple(dict.fromkeys(x for s in members for x in s.sequence_sources))
    return PlannedSystem(key=name, header=name, kind=name, tags=tuple(t for f in families for t in f.tags),
                         quantity=None, quantity_source="", quantity_quote="", sequence_sources=sequence,
                         schedule_sources=tuple(dict.fromkeys(x for s in members for x in s.schedule_sources)),
                         group=name, alternate=_alternate(ledger, name, *prefixes),
                         exception=_note(ledger, "exception", name, *prefixes),
                         why=f"From the job ledger: {len(facts)} facts.", sequence_section=", ".join(sequence),
                         families=families,
                         count_note="\n".join(f"{s.key}: {s.count_note}" for s in members if s.count_note),
                         facts=facts)


def _gather_splits(ledger: Ledger, systems: list[PlannedSystem]) -> list[PlannedSystem]:
    """The split units no group took (their prefix one of the Split System template's) become one "Split System"
    block; one per sequence section ("Split System — LOBBY") when their sequence matches name two or more
    sections, a unit matched to none joining the block whose units share a tag suffix with it, else the first. A
    lone unit with no partner stays on its own."""
    prefixes = _split_prefixes()
    loose = [s for s in systems if not s.group and not s.families and s.key.upper() in prefixes]
    if len(loose) < 2:
        return systems
    section = {s.key: next((_squash(m.subject) for m in _matches(ledger, s.key)), "") for s in loose}
    names = list(dict.fromkeys(n for n in section.values() if n))
    if len(names) < 2:
        gathered = {SPLIT_SYSTEM: loose}
    else:
        by_section = {n: [s for s in loose if section[s.key] == n] for n in names}
        for system in (s for s in loose if not section[s.key]):
            near = next((n for n in names if _suffixes(system) & set().union(*map(_suffixes, by_section[n]))),
                        names[0])
            by_section[near].append(system)
        gathered = {f"{SPLIT_SYSTEM} — {n}": sorted(m, key=systems.index) for n, m in by_section.items()}
    out = list(systems)
    for name, members in gathered.items():
        if len(members) < 2:
            continue
        out[out.index(members[0])] = _split_system(ledger, name, members)
        out = [s for s in out if s not in members[1:]]
    return out


def _template_names(system: PlannedSystem) -> PlannedSystem:
    """A group's family whose name is a long description takes the Master Template's word for its prefix
    ("Indoor Unit AC-1, 2")."""
    if not system.families:
        return system
    from estimator.writing.assemble import _split_kind, system_template
    template = system_template(system)
    names = getattr(template, "family_names", None) or {}
    families = []
    for family in system.families:
        words, rest = _split_kind(family.header)
        word = names.get(_family_prefix(family))
        if word and rest and len(words.split()) > _LONG_NAME_WORDS:
            family = replace(family, header=f"{word} {rest}")
        families.append(family)
    return replace(system, families=tuple(families))


def _split_group(ledger: Ledger, group: Fact) -> list[str]:
    """The families of a group that each match their own sequence section (two or more distinct sequence_match
    values among its members): such a group is not one plant, so it is not kept. [] when the group holds."""
    matched = [fact.subject for fact, _ in _members(ledger, group) if _matches(ledger, fact.subject)]
    values = {_squash(m.value).casefold() for m in _matches(ledger, *matched)}
    return matched if len(values) >= 2 else []


def ledger_plan(ledger: Ledger) -> JobPlan:
    kept: list[Fact] = []
    dropped: list[str] = []
    for group in ledger.of_kind("group"):
        split = _split_group(ledger, group)
        if split:
            dropped.append(f"The group “{_squash(group.subject)}” is not kept: its families {', '.join(split)} each "
                           "match their own sequence section, so each is written on its own.")
            continue
        kept.append(group)
    parts = _parts(ledger, kept)
    systems: list[PlannedSystem] = []
    asks: list[str] = []
    placed: set[str] = set()
    for fact in ledger.of_kind("family"):
        claims = parts.get(fact.subject.casefold(), [])
        for group, _ in claims:
            if group.id not in placed:
                placed.add(group.id)
                system, questions = _group_system(ledger, group, parts)
                systems.append(system)
                asks += questions
        rest = _rest_system(ledger, fact, claims)
        if rest is not None:
            systems.append(rest)
    systems = [_template_names(s) for s in _gather_splits(ledger, systems)]
    systems = _link_dampers(ledger, systems)
    questions = [_squash(f.value) for f in ledger.of_kind("note") if f.subject.casefold() == "question"] + asks
    taken = {i for s in systems for i in s.facts}
    for f in ledger.of_kind("sequence_match"):
        if f.id in taken:
            continue
        named = f" (it named {_squash(f.value)})" if _squash(f.value) else ""
        questions.append(f"Sequence section {_squash(f.subject)} matched no system{named}; which system is it?")
    return JobPlan(systems=tuple(systems), front_end=_front_end(ledger), unresolved=tuple(questions), model="ledger",
                   dropped=tuple(dropped))


def entry_text(system: PlannedSystem, ledger: Ledger) -> str:
    """The system's ledger entry: its facts, one line each, for the write prompt."""
    return ledger.table(list(getattr(system, "facts", ()) or ()))


def system_counts(system: PlannedSystem, ledger: Ledger) -> frozenset[int]:
    """Every number a scope line for this system may carry: its count and device facts' values, printed or not, the
    count of dampers linked to it, and its own planned quantity (a damper block's count is what no fan claims)."""
    numbers: set[int] = set()
    if isinstance(getattr(system, "quantity", None), int):
        numbers.add(system.quantity)
    if getattr(system, "linked_dampers", 0):
        numbers.add(system.linked_dampers)          # "Damper Actuator (Qty. n Total)" under the fan
    for fid in getattr(system, "facts", ()) or ():
        fact = ledger.facts.get(fid)
        if fact is None or fact.kind not in ("count", "device"):
            continue
        for value in (fact.value, *(c.value for c in fact.contradictions)):
            if isinstance(value, int) and not isinstance(value, bool):
                numbers.add(value)
            elif str(value).strip().isdigit():
                numbers.add(int(str(value).strip()))
    return frozenset(numbers)
