# src/estimator/writing/brief.py
"""The job brief (design 2026-10-03 §2.1): one short text built from the ledger after the passes, given to every
write request and to the QC pass, so each system is written knowing the whole job: what the job is, every system
with its count, kind, packaged-or-field class and links, the sequence's general rules, and who owns the shared
items (a damper's actuator belongs to its fan; a duct heater's interlock belongs to the heater's own block when the
plan has one, else to the unit it serves). Duct heaters are written in one place: a unit served by a heater block is
told to write no duct heater line, and the heater block is told, per unit it serves, which rule decides its scope."""
from __future__ import annotations

import re

from estimator.writing.style import load_house_style

_MAKER = re.compile(r"\b(?:unit\s+mfr|manufacturer|factory|oem|packaged|comes?\s+with\s+the\s+unit|furnished\s+with\s+the\s+unit)\b", re.I)
_NOT_MAKER = re.compile(r"\bnot\s+by\b|\bnot\s+the\s+unit\s+mfr", re.I)
_SERVES = re.compile(r"serves?\s+([A-Z][A-Z0-9-]+)")
_SPACES = re.compile(r"\s+")


def _squash(text) -> str:
    return _SPACES.sub(" ", str(text or "")).strip()


def _names(system) -> list[str]:
    names = [system.key] + list(system.tags or ())
    names += [t.split("-")[0] for t in system.tags or () if "-" in t]
    return [n for n in dict.fromkeys(_squash(n) for n in names) if n]


def _word(name: str, text: str) -> bool:
    return re.search(rf"(?<![A-Za-z0-9]){re.escape(name)}(?![A-Za-z0-9])", text, re.I) is not None


def system_class(ledger, system) -> str:
    """"packaged" when a provider fact about the system says the unit maker or the factory controls it; else "field"."""
    names = _names(system)
    for fact in ledger.of_kind("provider"):
        value = _squash(fact.value)
        if any(_word(n, fact.subject) for n in names) and _MAKER.search(value) and not _NOT_MAKER.search(value):
            return "packaged"
    return "field"


def _system_of(plan, name: str):
    name = _squash(name)
    for system in plan.systems:
        if any(n.casefold() == name.casefold() for n in _names(system)):
            return system
    for system in plan.systems:
        if any(_word(n, name) for n in _names(system)):
            return system
    return None


def served_systems(ledger, plan, system) -> list:
    """The systems this one serves: the value of each link whose subject names this system (and whose value names
    another), and the "serves X" words of a provider or note fact about this system; each once, never itself."""
    names = _names(system)
    found: list[str] = []
    for fact in ledger.of_kind("link"):
        subject, value = _squash(fact.subject), _squash(fact.value)
        if any(_word(n, subject) for n in names) and not any(_word(n, value) for n in names):
            found.append(value)
        elif is_duct_heater(system) and any(_word(n, value) for n in names) and not any(_word(n, subject) for n in names):
            found.append(subject)           # the link may be written from the unit's side: the unit is the partner
    for fact in ledger.of_kind("provider") + ledger.of_kind("note"):
        if any(_word(n, fact.subject) for n in names):
            found += _SERVES.findall(_squash(fact.value))
    systems = []
    for name in found:
        other = _system_of(plan, name)
        if other is not None and other.key != system.key and other not in systems:
            systems.append(other)
    return systems


def served_class(ledger, plan, system) -> str:
    """"packaged" when a unit this system serves is packaged, "field" when every one is field, "" when the ledger
    names none (a duct heater's rule follows the unit it serves)."""
    classes = [system_class(ledger, other) for other in served_systems(ledger, plan, system)]
    if not classes:
        return ""
    return "packaged" if "packaged" in classes else "field"


def is_duct_heater(system, style=None) -> bool:
    """The system is a duct heater: its key, kind or header says so in the house style's duct heater words."""
    style = style or load_house_style()
    raw = (getattr(style, "packaged_units", None) or {}).get("duct_heater_words", ())
    patterns = [raw] if isinstance(raw, str) else list(raw)
    words = f"{system.key} {system.kind} {system.header}"
    return any(re.search(p, words, re.I) for p in patterns)


def shared_owners(ledger, plan) -> dict[str, str]:
    """item -> the key of the system that owns it, from the ledger's links."""
    owners: dict[str, str] = {}
    for fact in ledger.of_kind("link"):
        subject, value = _squash(fact.subject), _squash(fact.value)
        if _is_damper(subject):
            owner = _system_of(plan, value)
            if owner is not None:
                owners[f"damper actuator {subject}"] = owner.key
        if subject.upper().startswith("EDH") or "duct heater" in subject.lower():
            own = _system_of(plan, subject)          # the heater's own block writes it, when the plan has one
            owner = own if own is not None and is_duct_heater(own) else _system_of(plan, value)
            if owner is not None:
                owners[f"duct heater interlock {subject}"] = owner.key
    for system in plan.systems:
        if any("condensate" in _squash(ledger.facts[f].value).lower() for f in system.facts if f in ledger.facts):
            owners.setdefault("condensate pump float switch", system.key)
    return owners


def _heater_tags(ledger, heater, unit) -> list[str]:
    """The heater's tags a link pairs with the unit (from either side); all its tags when no link names one."""
    unit_names, tags = _names(unit), []
    for fact in ledger.of_kind("link"):
        subject, value = _squash(fact.subject), _squash(fact.value)
        for mine, other in ((subject, value), (value, subject)):
            if any(_word(n, other) for n in unit_names):
                tags += [t for t in heater.tags or () if _word(t, mine)]
    return list(dict.fromkeys(tags)) or list(heater.tags or ()) or [heater.key]


def heater_home(ledger, plan, system) -> tuple[str, str]:
    """For a unit a duct heater block of the plan serves: the heaters' tags and that block's header (joined with
    "and" when two heater blocks serve it), as the unit's writer and the house check name them; ("", "") else."""
    if is_duct_heater(system):
        return "", ""
    tags, headers = [], []
    for heater in plan.systems:
        if heater.key == system.key or not is_duct_heater(heater):
            continue
        if any(unit.key == system.key for unit in served_systems(ledger, plan, heater)):
            tags += _heater_tags(ledger, heater, system)
            headers.append(heater.header)
    if not headers:
        return "", ""
    return ", ".join(dict.fromkeys(tags)), " and ".join(dict.fromkeys(headers))


def heater_assignment(system, dossier, style=None) -> tuple[str, str]:
    """The one answer to "does the sequence give the BMS this duct heater's control?": the first sentence of the
    heater block's sequence paragraphs (its own section and the sections of the units it serves, as the plan gives
    them) that does (house_check.heater_control_sentence), with its source id; ("", "") when none does, or the
    system is not a duct heater. The brief and the house check both take this answer; neither reads it again."""
    style = style or load_house_style()
    if dossier is None or not is_duct_heater(system, style):
        return "", ""
    from estimator.writing.assemble import _dossier_sections_of, cited_text, source_ids, system_sections
    from estimator.writing.house_check import heater_control_sentence
    sections = _dossier_sections_of(dossier)
    ids = [sid for q in system_sections(system) if q in sections for sid in sections[q][1]]
    ids += [sid for sid in source_ids(system.sequence_sources) if sid not in ids]
    for sid in ids:
        sentence = heater_control_sentence(cited_text(dossier, sid), style)
        if sentence:
            return sentence, sid
    return "", ""


def heater_rules(ledger, plan, heater, assignment=("", "")) -> list[str]:
    """Per unit the duct heater block serves, the rule that decides the heater's scope and why: the sequence item
    `assignment` (heater_assignment) giving the BMS the heater's control (full scope, named), else the house rule
    (interlock only on a packaged unit, full scope under an AME DDC controller)."""
    from estimator.writing.house_check import heater_item
    item = heater_item(assignment)
    rules = []
    for unit in served_systems(ledger, plan, heater):
        if item:
            rules.append(f"{unit.key}: full field-DDC duct heater scope, as the sequence gives the BMS the heater's "
                         f"control ({item})")
        elif system_class(ledger, unit) == "packaged":
            rules.append(f"{unit.key}: interlock only, by the house rule (the unit has packaged/factory controls)")
        else:
            rules.append(f"{unit.key}: full field-DDC duct heater scope, by the house rule (the unit is under an AME "
                         "DDC controller)")
    return rules


def _is_damper(subject: str) -> bool:
    """A damper's tag or label: it leads with a damper prefix ("MD-1", "MD on EF-2 duct") or says "damper"."""
    style = load_house_style()
    prefixes = tuple(p.upper() for p in getattr(style, "packaged_units", {}).get("damper_prefixes", ("MD",)))
    lead = re.split(r"[\s\-(/,]", _squash(subject), maxsplit=1)[0].upper()
    return lead in prefixes or "damper" in subject.lower()


def _links(ledger, system) -> tuple[list[str], list[str]]:
    names = _names(system)
    serves, served = [], []
    for fact in ledger.of_kind("link"):
        s, v = _squash(fact.subject), _squash(fact.value)
        if any(_word(n, s) for n in names) and not any(_word(n, v) for n in names):
            served.append(v)
        elif any(_word(n, v) for n in names) and not any(_word(n, s) for n in names):
            if not _is_damper(s):  # a damper's link is the fan's shared item (section 4), not a unit it serves
                serves.append(s)
    return list(dict.fromkeys(serves)), list(dict.fromkeys(served))


def _cut(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    head = text[:limit]
    stop = max(head.rfind(". "), head.rfind("\n"))
    return (head[:stop + 1] if stop > 0 else head).rstrip() + " (cut)"


def job_brief(ledger, plan, templates=None, limit: int = 4000, assignments=None) -> str:
    """`assignments`: heater system key -> heater_assignment's answer, naming the sequence item that decides a duct
    heater block's scope (none given: the house rule decides)."""
    what = ledger.understanding.get("sequence") or ledger.understanding.get("schedules") or ""
    lines = [f"Job: {getattr(ledger, 'job_name', '') or ''}".rstrip(), "", "What the job is", _cut(_squash(what), 1200), "",
             "The systems (key | header | count | kind | packaged or field | links)"]
    for system in plan.systems:
        serves, served = _links(ledger, system)
        qty = f"Qty {system.quantity}" if system.quantity is not None else "Qty ##"
        parts = [system.key, system.header, qty, system.kind, system_class(ledger, system)]
        if is_duct_heater(system):
            units = served_systems(ledger, plan, system)
            if units:
                parts.append(f"serves: {', '.join(u.key for u in units)} ({served_class(ledger, plan, system)})")
                served = [v for v in served if _system_of(plan, v) not in units]
                parts.append("scope: " + "; ".join(heater_rules(ledger, plan, system,
                                                                 (assignments or {}).get(system.key))))
        if serves:
            parts.append("serves: " + ", ".join(serves))
        if served:
            parts.append("served by: " + ", ".join(served))
        tags, header = heater_home(ledger, plan, system)
        if header:
            parts.append(f"The duct heaters serving this unit ({tags}) are written in the {header} block; "
                         "write no duct heater line here.")
        lines.append(" | ".join(parts))
    general = [_squash(f.value) for f in ledger.of_kind("note") if f.subject.casefold() == "general"]
    if general:
        lines += ["", "Rules the sequence sets for the whole job"] + [f"- {g}" for g in general]
    owners = shared_owners(ledger, plan)
    if owners:
        lines += ["", "Who owns shared items (no other block writes them)"] + [f"- {item} — {key}" for item, key in owners.items()]
    text = "\n".join(lines)
    if len(text) > limit:
        head = text[:limit]
        text = head[:head.rfind("\n")].rstrip() + "\n(cut)"
    return text
