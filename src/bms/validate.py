"""The validators (workstream 3, design §4.3): one small function per Playbook rule, on fields, never on text.

Every check reads Job fields only: verbs, parties, slot and its kind in the shape, refs, counts, flags and the
kind of each clarification. None reads the wording of a sentence. Each finding is named by a rule heading of the
repo Playbook (`playbook/rules.md`); `RULE` maps each check to it (tests/bms/test_rule_names.py holds the two
together).
"""
from __future__ import annotations

import re
from typing import Callable, Iterator

from bms.model import PARTIES, Count, Device, Finding, Job, System
from bms.playbook import Playbook, Shape

RULE = {
    "cites": "Every line cites this job",
    "higher": "Higher count prints",
    "one_note": "One clarification per block",
    "assumption": "Every assumption says why",
    "packaged": "Packaged units",
    "loose": "Shipped-loose devices",
    "damper": "Dampers under their fan",
    "heater": "Duct heaters in one place",
    "vrf": "VRF and split as one block",
    "unknown": "Never undershoot",
    "owner": "Every line carries its ownership",
    "once": "One system one block",
    "sequence": "Systems named only in the sequence",
    "slot": "Placing a device in a slot",
    "subline": "Sub-lines under their parent",
}

# a checker yields (device_id | None, severity, what, fix) for one system
Hit = tuple["str | None", str, str, str]


def _kind(shape: Shape | None, device: Device) -> str | None:
    return shape.slot_kinds.get(device.slot) if shape else None


def _words(system: System) -> str:
    return " ".join([system.shape, *(f.name for f in system.families)]).lower()


# System kind is read from the shape and family names, because the model has no typed kind field. Limits: a name
# that merely contains the word counts; "fan coil" and "fan powered" are excluded from fans by hand. A Playbook
# shape attribute for the kind would replace these guesses.
_NOT_A_FAN = ("fan coil", "fan powered", "fan-powered")


def _is_fan_system(system: System) -> bool:
    names = [system.shape, *(f.name for f in system.families)]
    return any(re.search(r"\bfan\b", n.lower()) and not any(x in n.lower() for x in _NOT_A_FAN) for n in names)


def _is_damper_block(system: System) -> bool:
    """A block that is only dampers: named for them, or every line of it a damper."""
    if "damper" in _words(system):
        return True
    return bool(system.devices) and all(_is_damper(d) for d in system.devices)


def _is_heater_system(system: System) -> bool:
    return "duct heater" in _words(system)


def _is_vrf(system: System) -> bool:
    words = _words(system)
    return "vrf" in words or "split" in words or ("indoor unit" in words and "condensing unit" in words)


def _is_damper(device: Device) -> bool:
    return "damper" in device.slot.lower()


def _is_duct_heater_line(device: Device) -> bool:
    return bool(re.search(r"duct_?heater", device.slot.lower())) or "duct heater" in device.name.lower()


def _sequence_only(system: System) -> bool:
    return bool(system.sequence_refs) and not system.devices


# ---- the rules, one small function each (system level) ------------------------------------------------------


def _cites(system, shape, job, playbook) -> Iterator[Hit]:
    for d in system.devices:
        if not d.refs or any(not r.source_id.strip() or not r.quote.strip() for r in d.refs):
            yield (d.id, "must_fix", f"{d.name} has no usable citation from this job",
                   "Cite the passage of this job's documents that calls for it, or delete the line.")


def _owners(system, shape, job, playbook) -> Iterator[Hit]:
    for d in system.devices:
        missing = [n for n, v in (("furnished by", d.furnished_by), ("installed by", d.installed_by),
                                  ("wired by", d.wired_by)) if v not in PARTIES]
        if missing:
            yield (d.id, "must_fix", f"{d.name} does not say who it is {', '.join(missing)}",
                   "Give the party that furnishes, installs and wires it.")


def _slots(system, shape, job, playbook) -> Iterator[Hit]:
    if shape is None:
        return
    for d in system.devices:
        if d.slot not in shape.slot_kinds:
            yield (d.id, "must_fix", f"{d.name} fills the slot '{d.slot}', which the {shape.name} shape does not have",
                   "Move it to a slot of the shape or delete it.")


def _sublines(system, shape, job, playbook) -> Iterator[Hit]:
    """A device of a sub-line slot (the shape's `under`) prints under its parent's line: the parent must be there."""
    if shape is None or not shape.under:
        return
    slots = {d.slot for d in system.devices}
    for d in system.devices:
        parent = shape.under.get(d.slot)
        if parent is not None and parent not in slots:
            yield (d.id, "must_fix", f"{d.name} prints under the '{parent}' line, which this block does not have",
                   f"Add the '{parent}' line the evidence calls for, or move this device to a line of its own.")


def _packaged(system, shape, job, playbook) -> Iterator[Hit]:
    if system.control != "packaged":
        return
    for d in system.devices:
        kind = _kind(shape, d)
        if kind == "point" and d.verb.startswith("Furnish"):
            yield (d.id, "must_fix", f"{d.name}: AME does not furnish points on a packaged unit",
                   "Take the point line out; AME integrates through the manufacturer's interface.")
        elif kind == "device" and d.furnished_by == "AME":
            yield (d.id, "must_fix", f"{d.name} is a device inside the packaged unit, which AME does not furnish",
                   "Delete the line, or if it ships loose, have the unit manufacturer furnish it.")
    if shape is None:
        return
    for slot in shape.slots_of_kind("integration"):
        n = sum(1 for d in system.devices if d.slot == slot)
        if n != 1:
            yield (None, "must_fix", f"The '{slot}' integration line is {'missing' if n == 0 else f'there {n} times'}",
                   "The integration lines appear exactly once in a packaged-control block.")


def _loose(system, shape, job, playbook) -> Iterator[Hit]:
    if system.control != "packaged":
        return
    for d in system.devices:
        loose = d.verb == "Install and Wire" or (_kind(shape, d) == "device" and d.furnished_by == "Unit Mfr.")
        if loose and (d.verb != "Install and Wire" or d.furnished_by != "Unit Mfr."
                      or d.installed_by != "AME" or d.wired_by != "AME"):
            yield (d.id, "must_fix", f"{d.name} ships loose with the unit but its ownership is not "
                   "'Install and Wire' by AME with the unit manufacturer furnishing",
                   "Set the verb to Install and Wire, furnished by Unit Mfr., installed and wired by AME.")


def _dampers(system, shape, job, playbook) -> Iterator[Hit]:
    """The model carries no link from a damper to a fan, so a damper is only a must_fix when its block is a
    stand-alone damper block; in a block with equipment of its own it is a check (a packaged unit's own
    economizer or mixing damper is left alone)."""
    if _is_fan_system(system) or system.control == "packaged" or not any(_is_fan_system(s) for s in job.systems):
        return
    severity = "must_fix" if _is_damper_block(system) else "check"
    for d in system.devices:
        if _is_damper(d):
            yield (d.id, severity, f"{d.name} is a damper in a block with no fan, while the job has a fan block",
                   "If it serves a fan, move it under that fan; if it belongs to this equipment, leave it.")


def _heaters(system, shape, job, playbook) -> Iterator[Hit]:
    if _is_heater_system(system):
        return
    for d in system.devices:
        if _is_duct_heater_line(d):
            yield (d.id, "must_fix", f"{d.name} is a duct heater line outside the duct heater block",
                   "Move it to the duct heater block.")


def _vrf(system, shape, job, playbook) -> Iterator[Hit]:
    if not _is_vrf(system):
        return
    comm: dict[str, list[Device]] = {}
    for d in system.devices:
        if "comm" in d.slot.lower():
            comm.setdefault(d.slot, []).append(d)
    # one line per communication-wiring slot: "VRF Communication Wiring" and the integration trio's BMS
    # communication wiring are different lines, each written once
    repeated = next((lines for lines in comm.values() if len(lines) > 1), None)
    if repeated:
        yield (repeated[1].id, "must_fix", "Communication wiring appears more than once in this VRF or split block",
               "Keep one communication wiring line per system.")
    elif not comm and system.devices:
        yield (None, "check", "This VRF or split block has no communication wiring line", "Add it once.")
    names = {f.name.lower() for f in system.families}
    indoor, outdoor = "indoor unit" in names, "condensing unit" in names
    if indoor != outdoor:
        want, lack = ("condensing unit", "indoor unit") if indoor else ("indoor unit", "condensing unit")
        other = [s for s in job.systems if s.key != system.key and _is_vrf(s)
                 and want in {f.name.lower() for f in s.families}
                 and lack not in {f.name.lower() for f in s.families}]
        if other:
            yield (None, "must_fix", f"The indoor and outdoor units of one system are split across blocks "
                   f"({system.key} and {other[0].key})", "Put the indoor, condensing and branch units in one block.")


def _count_problems(count: Count, label: str) -> Iterator[tuple[str, str]]:
    top = count.highest()
    if count.value is not None and top is not None and count.value < top:
        yield (f"{label} prints {count.value} but another source gives {top}",
               f"Print the higher count, {top}, and name the other in the note.")


def _higher(system, shape, job, playbook) -> Iterator[Hit]:
    for f in system.families:
        for what, fix in _count_problems(f.count, f"The {f.name} count"):
            yield (None, "must_fix", what, fix)
    for d in system.devices:
        for what, fix in _count_problems(d.quantity, f"{d.name}"):
            yield (d.id, "must_fix", what, fix)


def _unknown(system, shape, job, playbook) -> Iterator[Hit]:
    if _sequence_only(system):
        return
    if any(c.kind in ("per_drawings", "confirm") for c in system.clarifications):
        return
    for f in system.families:
        if f.count.value is None:
            yield (None, "check", f"The {f.name} count is unknown and carries no clarification",
                   "Add one 'per drawings' or 'confirm' clarification to the block.")
            return


def _one_note(system, shape, job, playbook) -> Iterator[Hit]:
    if len(system.clarifications) > 1:
        kinds = ", ".join(c.kind for c in system.clarifications)
        yield (None, "must_fix", f"The block has {len(system.clarifications)} clarifications ({kinds})",
               "Keep one '*' clarification per block and merge or drop the rest.")


def _assumption(system, shape, job, playbook) -> Iterator[Hit]:
    for d in system.devices:
        a = d.assumption
        if a is not None and (not a.what.strip() or not a.why.strip()):
            missing = "what" if not a.what.strip() else "why"
            yield (d.id, "must_fix", f"The assumption on {d.name} does not say {missing}",
                   "State what is assumed and why.")
        elif a is None and d.flag == "assumed":
            yield (d.id, "must_fix", f"{d.name} is flagged assumed but has no assumption",
                   "State what is assumed and why, or clear the flag.")


def _sequence(system, shape, job, playbook) -> Iterator[Hit]:
    if not _sequence_only(system):
        return
    for f in system.families:
        if f.count.value is not None:
            yield (None, "must_fix", f"{system.name} has only a sequence of operation but the {f.name} count is "
                   f"{f.count.value}", "A sequence-only system prints 'Qty (##)'; clear the count.")


_SYSTEM_RULES: tuple[tuple[str, Callable], ...] = (
    ("cites", _cites), ("owner", _owners), ("slot", _slots), ("subline", _sublines), ("packaged", _packaged), ("loose", _loose),
    ("damper", _dampers), ("heater", _heaters), ("vrf", _vrf), ("higher", _higher), ("unknown", _unknown),
    ("one_note", _one_note), ("assumption", _assumption), ("sequence", _sequence),
)

_FRONT_END_RULES = ("cites", "owner", "assumption", "one_note")


def validate(job: Job, playbook: Playbook) -> list[Finding]:
    """Every rule broken by the job, in system order then device order (the front end first, a system's own
    findings before its devices'). Never raises on a well-formed Job."""
    found: list[tuple[tuple[int, int, int], Finding]] = []

    def add(sys_index: int, system_key: str, order: dict[str, int], rule: str, hit: Hit) -> None:
        device_id, severity, what, fix = hit
        key = (sys_index, -1 if device_id is None else order.get(device_id, len(order)), len(found))
        found.append((key, Finding(RULE[rule], system_key, device_id, severity, what, fix)))  # type: ignore[arg-type]

    fe = job.front_end
    if fe is not None:
        order = {d.id: n for n, d in enumerate(fe.devices)}
        pseudo = System("", "Front end", "", "none", (), devices=fe.devices, clarifications=fe.clarifications)
        for rule, check in _SYSTEM_RULES:
            if rule in _FRONT_END_RULES:
                for hit in check(pseudo, None, job, playbook):
                    add(-1, "", order, rule, hit)

    # a device id used in more than one place is a device repeated
    owners: dict[str, list[str]] = {}
    for system in job.systems:
        for d in system.devices:
            owners.setdefault(d.id, []).append(system.key)
    for index, system in enumerate(job.systems):
        order = {d.id: n for n, d in enumerate(system.devices)}
        shape = playbook.shapes.get(system.shape)
        for rule, check in _SYSTEM_RULES:
            for hit in check(system, shape, job, playbook):
                add(index, system.key, order, rule, hit)
        seen: set[str] = set()
        for d in system.devices:
            if len(owners[d.id]) > 1 and d.id not in seen:
                others = sorted({k for k in owners[d.id] if k != system.key} or {system.key})
                add(index, system.key, order, "once",
                    (d.id, "must_fix", f"{d.name} is listed more than once ({system.key} and {', '.join(others)})",
                     "Keep it in the one block it belongs to."))
            seen.add(d.id)
    found.sort(key=lambda item: item[0])
    return [f for _, f in found]
