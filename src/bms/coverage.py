"""The coverage gate: a fact the ledger read that nothing in the written job cites. Pure and report-only: it never
adds a line or text to the job."""
from __future__ import annotations

from estimator.ledger.facts import Fact, Ledger, where_short

from bms.model import Count, Finding, Job, Ref
from bms.plan_read import names_in, squash

RULE = "coverage"

# Kinds that call for scope: what is there to price or to say. Left out: count (a number about a family, which the
# family fact already covers), location (where, not what), provider and link (who and how, not a thing), group
# (planning detail), note (free text; a note has no subject to cite).
SCOPE_KINDS = ("family", "unit", "device", "sequence_match", "front_end")


def _count_refs(count: Count) -> list[Ref]:
    return [*count.sources, *(other.ref for other in count.others)]


def _refs(job: Job) -> list[Ref]:
    """Every ref the job holds: sequence refs, line refs, the refs of each family's and line's count (its sources and
    its other counts: the planner cites a family's schedule row there) and the exceptions' refs."""
    refs: list[Ref] = []
    devices = []
    for system in job.systems:
        refs.extend(system.sequence_refs)
        for family in system.families:
            refs.extend(_count_refs(family.count))
        devices.extend(system.devices)
    if job.front_end:
        devices.extend(job.front_end.devices)
    for device in devices:
        refs.extend(device.refs)
        refs.extend(_count_refs(device.quantity))
    for exception in job.exceptions:
        refs.extend(exception.refs)
    return refs


def _text(job: Job) -> str:
    """Every word the job writes that a fact could be named in."""
    parts: list[str] = list(job.questions)
    devices = []
    for system in job.systems:
        parts += [system.key, system.name, system.no_scope_reason or ""]
        for family in system.families:
            parts += [family.name, *family.tags]
        parts += [c.text for c in system.clarifications]
        devices.extend(system.devices)
        for served in system.serves:
            parts += [served.name, *served.tags, *served.heaters]
    if job.front_end:
        parts += [job.front_end.existing_system_name or "", *(c.text for c in job.front_end.clarifications)]
        devices.extend(job.front_end.devices)
    for device in devices:
        parts += [device.name, device.slot, device.assumption.what if device.assumption else ""]
    for exception in job.exceptions:
        parts += [exception.system_key, exception.text]
    return squash(" ".join(parts))


def _same(a: str, b: str) -> bool:
    a, b = squash(a).casefold(), squash(b).casefold()
    return bool(a) and bool(b) and (a in b or b in a)


def _said(value) -> str:
    """A fact's value as one line of text; "" when it has none (None or blank), so "(None)" and "()" never print and
    the word "None" never names a unit. A 0 is a value."""
    return "" if value is None else " ".join(str(value).split())


def _cited(fact: Fact, refs: list[Ref], text: str, front_end: bool) -> bool:
    if fact.kind == "front_end" and front_end:
        return True
    if any(r.source_id == fact.source_id and _same(r.quote, fact.quote) for r in refs):
        return True
    names = [fact.subject]
    if fact.kind == "unit":
        names.append(_said(fact.value))
    return names_in(names, text)


def coverage(job: Job, ledger: Ledger, dossier=None) -> list[Finding]:
    """One `check` Finding per fact of a scope kind that no ref, family, tag, line, clarification, exception,
    question or front end of the job cites. `dossier` is accepted for the run's call and is not needed."""
    refs, text = _refs(job), _text(job)
    front_end = bool(job.front_end and (job.front_end.devices or job.front_end.clarifications))
    found: list[Finding] = []
    for fact in ledger.facts.values():
        if fact.kind not in SCOPE_KINDS or _cited(fact, refs, text, front_end):
            continue
        where = where_short(ledger.sources.get(fact.source_id, "")) or f"source {fact.source_id}"
        value = _said(fact.value)
        shown = f" ({value})" if value else ""
        found.append(Finding(
            rule=RULE, system_key="", device_id=None, severity="check",
            what=f"{fact.id}: the {fact.kind.replace('_', ' ')} \u201c{fact.subject}\u201d{shown} was read "
                 f"at {where} \u2014 \u201c{fact.quote}\u201d \u2014 and the job cites it nowhere.",
            fix="Add a line, a clarification, an exception or a question that cites it, or mark it as not scope."))
    return found
