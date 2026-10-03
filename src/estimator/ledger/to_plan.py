"""From the ledger to the systems the writer takes (design 2026-09-29 §3): one PlannedSystem per family or group,
in ledger order, its quantity the printed (highest) count with a "*" note when the count is contradicted, and the
ids of the facts it rests on. The writer, the checks and the Evidence Package read a JobPlan as before."""
from __future__ import annotations

import re

from estimator.ledger.facts import CONTRADICTED, Fact, Ledger, where_short
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


def count_note(ledger: Ledger, fact: Fact) -> str:
    """The "*" note under a system whose count is contradicted: the printed count and its place, then each other
    count and its place. "" when the fact is not contradicted or none of its values is a number."""
    if fact.state != CONTRADICTED:
        return ""
    printed, sid, _quote = _printed(ledger, fact)
    if printed is None:
        return ""
    others = [(fact.value, fact.source_id)] + [(c.value, c.source_id) for c in fact.contradictions]
    others = [(_squash(v), s) for v, s in others if not _same(v, printed)]
    place = where_short(ledger.sources.get(sid.strip("[]"), sid))
    rest = "; ".join(f"{where_short(ledger.sources.get(s, s))} lists ({v})" for v, s in others)
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
    why = ("Seen on the drawings but on no schedule; confirm it exists." if fact.state == "added"
           else f"From the job ledger: {len(ids) + len(matched)} facts.")
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
    questions = tuple(_squash(f.value) for f in ledger.of_kind("note") if f.subject.casefold() == "question")
    return JobPlan(systems=tuple(systems), front_end=_front_end(ledger), unresolved=questions, model="ledger")


def entry_text(system: PlannedSystem, ledger: Ledger) -> str:
    """The system's ledger entry: its facts, one line each, for the write prompt."""
    return ledger.table(list(getattr(system, "facts", ()) or ()))


def system_counts(system: PlannedSystem, ledger: Ledger) -> frozenset[int]:
    """Every number a scope line for this system may carry: its count and device facts' values, printed or not."""
    numbers: set[int] = set()
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
