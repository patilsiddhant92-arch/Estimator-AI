# src/estimator/writing/brief.py
"""The job brief (design 2026-10-03 §2.1): one short text built from the ledger after the passes, given to every
write request and to the QC pass, so each system is written knowing the whole job: what the job is, every system
with its count, kind, packaged-or-field class and links, the sequence's general rules, and who owns the shared
items (a damper's actuator belongs to its fan, a duct heater's interlock to the unit it serves)."""
from __future__ import annotations

import re

from estimator.writing.style import load_house_style

_MAKER = re.compile(r"\b(?:unit\s+mfr|manufacturer|factory|oem|packaged|comes?\s+with\s+the\s+unit|furnished\s+with\s+the\s+unit)\b", re.I)
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
        if any(_word(n, fact.subject) for n in names) and _MAKER.search(_squash(fact.value)):
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


def shared_owners(ledger, plan) -> dict[str, str]:
    """item -> the key of the system that owns it, from the ledger's links."""
    style = load_house_style()
    damper_prefixes = tuple(getattr(style, "packaged_units", {}).get("damper_prefixes", ("MD",)))
    owners: dict[str, str] = {}
    for fact in ledger.of_kind("link"):
        subject, value = _squash(fact.subject), _squash(fact.value)
        prefix = subject.split("-")[0].upper()
        if prefix in damper_prefixes or "damper" in subject.lower():
            owner = _system_of(plan, value)
            if owner is not None:
                owners[f"damper actuator {subject}"] = owner.key
        if subject.upper().startswith("EDH") or "duct heater" in subject.lower():
            owner = _system_of(plan, value)
            if owner is not None:
                owners[f"duct heater interlock {subject}"] = owner.key
    for system in plan.systems:
        if any("condensate" in _squash(ledger.facts[f].value).lower() for f in system.facts if f in ledger.facts):
            owners.setdefault("condensate pump float switch", system.key)
    return owners


def _is_damper(subject: str) -> bool:
    style = load_house_style()
    prefixes = tuple(getattr(style, "packaged_units", {}).get("damper_prefixes", ("MD",)))
    return subject.split("-")[0].upper() in prefixes or "damper" in subject.lower()


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


def job_brief(ledger, plan, templates=None, limit: int = 4000) -> str:
    what = ledger.understanding.get("sequence") or ledger.understanding.get("schedules") or ""
    lines = [f"Job: {getattr(ledger, 'job_name', '') or ''}".rstrip(), "", "What the job is", _cut(_squash(what), 1200), "",
             "The systems (key | header | count | kind | packaged or field | links)"]
    for system in plan.systems:
        serves, served = _links(ledger, system)
        qty = f"Qty {system.quantity}" if system.quantity is not None else "Qty ##"
        parts = [system.key, system.header, qty, system.kind, system_class(ledger, system)]
        if serves:
            parts.append("serves: " + ", ".join(serves))
        if served:
            parts.append("served by: " + ", ".join(served))
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
