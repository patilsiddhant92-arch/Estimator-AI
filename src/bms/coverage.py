"""The coverage gate: a fact the ledger read that nothing in the written job cites. Pure and report-only: it never
adds a line or text to the job."""
from __future__ import annotations

import re

from estimator.ledger.facts import Fact, Ledger, where_short

from bms.model import Count, Finding, Job, Ref
from bms.plan_read import expand, names_in, squash

RULE = "coverage"

# Kinds that call for scope: what is there to price or to say. Left out: count (a number about a family, which the
# family fact already covers), location (where, not what), provider and link (who and how, not a thing), group
# (planning detail), note (free text; a note has no subject to cite).
SCOPE_KINDS = ("family", "unit", "device", "sequence_match", "front_end")

# A family or unit fact's subject is the tag prefix ("VAV"), so its subject is never a citation: only a ref with its
# source and quote, or one of its own tags, cites it (T-001b).
TAGGED_KINDS = ("family", "unit")


def _count_refs(count: Count | None) -> list[Ref]:
    if count is None:
        return []
    return [*count.sources, *(o.ref for o in count.others), *([count.added_up.ref] if count.added_up else [])]


def _count_refs(count: Count | None) -> list[Ref]:
    if count is None:
        return []
    return [*count.sources, *(o.ref for o in count.others), *([count.added_up.ref] if count.added_up else [])]


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


# ---- tags (T-001b) ---------------------------------------------------------------------------------------------

_A_TAG = r"[A-Za-z]{1,6}(?:-?\d[A-Za-z0-9.]*|-[A-Za-z0-9]+)(?:-[A-Za-z0-9.]+)*"
_RANGE = re.compile(rf"(?<![A-Za-z0-9\-])({_A_TAG}\s+thru\s+(?:{_A_TAG}|\d+[A-Za-z]?))(?![A-Za-z0-9])", re.I)


def _tags(text) -> list[str]:
    """Each tag a fact's value states, brackets dropped and ranges expanded ("EF-1 thru 3, EF-7 (roof)" is EF-1,
    EF-2, EF-3, EF-7); a piece with no letter is not a tag."""
    text = squash(re.sub(r"\([^()]*\)", " ", str(text if text is not None else "")))
    return [t for t in (squash(t) for t in (expand([text]) if text else [])) if re.search(r"[A-Za-z]", t)]


def _own_tags(fact: Fact, ledger: Ledger) -> list[str]:
    """A unit fact's tags are its value's. A family fact's are the tags of the unit facts on its prefix, and the
    tags its own quote names that begin with its prefix. Never the bare prefix itself."""
    prefix = squash(fact.subject).casefold()
    if fact.kind == "unit":
        tags = _tags(fact.value)
    else:
        tags = [t for u in ledger.facts.values() if u.kind == "unit" and squash(u.subject).casefold() == prefix
                for t in _tags(u.value)]
        tags += [t for t in re.findall(rf"(?<![A-Za-z0-9\-]){_A_TAG}", fact.quote)
                 if t.casefold().startswith(prefix + "-") or re.fullmatch(rf"{re.escape(prefix)}\d.*", t, re.I)]
    return list(dict.fromkeys(t for t in tags if t.casefold() != prefix))


def _tag_in(tag: str, text: str) -> bool:
    """The tag as a whole tag: "EF-1" is not in "EF-10", "EF-1A", "XEF-1", "EF-1-2" or "EF-1.5"."""
    return bool(re.search(rf"(?<![A-Za-z0-9\-]){re.escape(tag)}(?![A-Za-z0-9]|-[A-Za-z0-9]|\.\d)", text, re.I))


def _with_ranges(text: str) -> str:
    """The job's text with every "TAG thru N" it writes followed by each tag of the range."""
    extra = [t for m in _RANGE.finditer(text) for t in expand([m.group(1)])]
    return f"{text} {' '.join(extra)}" if extra else text


def _same(a: str, b: str) -> bool:
    a, b = squash(a).casefold(), squash(b).casefold()
    return bool(a) and bool(b) and (a in b or b in a)


def _said(value) -> str:
    """A fact's value as one line of text; "" when it has none (None or blank), so "(None)" and "()" never print and
    the word "None" never names a unit. A 0 is a value."""
    return "" if value is None else " ".join(str(value).split())


def _cited(fact: Fact, refs: list[Ref], text: str, front_end: bool, ledger: Ledger) -> bool:
    if fact.kind == "front_end" and front_end:
        return True
    if any(r.source_id == fact.source_id and _same(r.quote, fact.quote) for r in refs):
        return True
    if fact.kind in TAGGED_KINDS:
        return any(_tag_in(tag, text) for tag in _own_tags(fact, ledger))
    return names_in([fact.subject], text)


def coverage(job: Job, ledger: Ledger, dossier=None) -> list[Finding]:
    """One `check` Finding per fact of a scope kind that no ref, family, tag, line, clarification, exception,
    question or front end of the job cites. A family or unit fact is cited only by a ref with its source and quote or
    by one of its own tags, never by its bare prefix. `dossier` is accepted for the run's call and is not needed."""
    refs, text = _refs(job), _with_ranges(_text(job))
    front_end = bool(job.front_end and (job.front_end.devices or job.front_end.clarifications))
    found: list[Finding] = []
    for fact in ledger.facts.values():
        if fact.kind not in SCOPE_KINDS or _cited(fact, refs, text, front_end, ledger):
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
