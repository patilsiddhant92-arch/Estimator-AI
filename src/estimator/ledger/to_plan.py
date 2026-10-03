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


def place_words(where: str, quote: str) -> str:
    """A count's place in plain words: the counts line's own words ("schedule rows 16") when the source is the
    equipment counts, else the sheet number alone ("M-201"), never the document and page."""
    where = _squash(where)
    if where.casefold().startswith(_COUNTS_LINE) and _squash(quote):
        return _squash(quote)
    return where_short(where).split(",", 1)[0].strip()


def _other_count(where: str, quote: str, value) -> str:
    """Another count in the note: the counts line's words carry their number; a sheet "lists" it."""
    place = place_words(where, quote)
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
    place = place_words(ledger.sources.get(sid.strip("[]"), sid), quote)
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


def _group_system(ledger: Ledger, group: Fact, members: list[Fact]) -> PlannedSystem:
    families, ids = [], [group.id]
    for member in members:
        family, member_ids = _family(ledger, member)
        families.append(family)
        ids += member_ids
    prefixes = [m.subject for m in members]
    matched = _matches(ledger, group.subject, *prefixes)
    sequence = tuple(_bracket(m.source_id) for m in matched)
    tags =tuple(t for f in families for t in f.tags)
    notes = [count_note(ledger, ledger.find("count", m.subject)) for m in members if ledger.find("count", m.subject)]
    return PlannedSystem(key=_squash(group.subject), header=_squash(group.subject), kind=_squash(group.subject),
                         tags=tags, quantity=None, quantity_source="", quantity_quote="", sequence_sources=sequence,
                         schedule_sources=tuple(_bracket(ledger.find("count", m.subject).source_id) for m in members
                                                if ledger.find("count", m.subject)),
                         group=_squash(group.subject), alternate=_alternate(ledger, group.subject, *prefixes),
                         exception=_note(ledger, "exception", group.subject, *prefixes),
                         why=f"From the job ledger: {len(ids) + len(matched)} facts.",
                         sequence_section=", ".join(sequence), families=tuple(families),
                         count_note=" ".join(n for n in notes if n), facts=tuple(ids + [m.id for m in matched]))


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


def _is_motorized_damper(subject: str, prefixes: tuple[str, ...]) -> bool:
    """A motorized damper's tag or label: its prefix is a damper prefix ("MD-1") or it says "damper"; a fire or
    smoke damper is not one (those stay where they are)."""
    words = _squash(subject).casefold()
    if "fire" in words or "smoke" in words:
        return False
    return _squash(subject).split("-")[0].upper() in prefixes or "damper" in words


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


def _link_dampers(ledger: Ledger, systems: list[PlannedSystem]) -> list[PlannedSystem]:
    """A motorized damper linked to a fan joins that fan: the link and the damper's unit and location facts go to
    the fan's facts and the fan counts it. The damper family keeps only the dampers no fan claims, naming the sheets
    to look at; when every damper is claimed, there is no damper system."""
    prefixes = _damper_prefixes()
    damper_keys = {s.key.upper() for s in systems if not s.group and s.key.upper() in prefixes}
    joined: dict[str, list[str]] = {}
    links_of: dict[str, list[Fact]] = {}
    for link in ledger.of_kind("link"):
        subject = _squash(link.subject)
        if not _is_motorized_damper(subject, prefixes):
            continue
        value = _squash(link.value)
        target = next((s for s in systems if s.key.upper() not in damper_keys
                       and any(_naming(n).search(value) for n in _names_of(s))), None)
        if target is None:
            continue
        own = [f.id for f in ledger.about(subject) if f.kind in ("unit", "location")]
        joined.setdefault(target.key, []).extend([link.id, *own])
        family = subject.split("-")[0].upper()
        family = family if family in damper_keys else next(iter(sorted(damper_keys)), "")
        links_of.setdefault(family, []).append(link)
    if not joined:
        return systems
    planned: list[PlannedSystem] = []
    for system in systems:
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


def ledger_plan(ledger: Ledger) -> JobPlan:
    groups = ledger.of_kind("group")
    member_of: dict[str, Fact] = {}
    for group in groups:
        for prefix in (p.strip() for p in _squash(group.value).split(",")):
            if prefix:
                member_of.setdefault(prefix.casefold(), group)
    systems: list[PlannedSystem] = []
    placed: set[str] = set()
    for fact in ledger.of_kind("family"):
        group = member_of.get(fact.subject.casefold())
        if group is None:
            systems.append(_system(ledger, fact))
        elif group.id not in placed:
            placed.add(group.id)
            members = [f for f in ledger.of_kind("family") if member_of.get(f.subject.casefold()) is group]
            systems.append(_group_system(ledger, group, members))
    systems = _link_dampers(ledger, systems)
    questions = tuple(_squash(f.value) for f in ledger.of_kind("note") if f.subject.casefold() == "question")
    return JobPlan(systems=tuple(systems), front_end=_front_end(ledger), unresolved=questions, model="ledger")


def entry_text(system: PlannedSystem, ledger: Ledger) -> str:
    """The system's ledger entry: its facts, one line each, for the write prompt."""
    return ledger.table(list(getattr(system, "facts", ()) or ()))


def system_counts(system: PlannedSystem, ledger: Ledger) -> frozenset[int]:
    """Every number a scope line for this system may carry: its count and device facts' values, printed or not, and
    the count of dampers linked to it."""
    numbers: set[int] = set()
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
