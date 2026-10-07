"""The validators (workstream 3, design §4.3): one small function per Playbook rule, on fields, never on text.

Every check reads Job fields only: verbs, parties, slot and its kind in the shape, refs, counts, flags and the
kind of each clarification. None judges the wording of a sentence; two only look at its surface (a source id in
it, its length). Each finding is named by a rule heading of the
repo Playbook (`playbook/rules.md`); `RULE` maps each check to it (tests/bms/test_rule_names.py holds the two
together).
"""
from __future__ import annotations

import re
from typing import Callable, Iterator

from bms import citations
from bms.citations import WHERE_ADVICE, SourceIds
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
    "left_out": "One system one block",
    "ids": "Assumption wording has no source ids",
    "long_note": "One clarification per block",
    "long_assumption": "Every assumption says why",
    "header_under": "Never undershoot",
}

LONG_TEXT = 220                       # a clarification or an assumption longer than this is a check

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


def _is_heater_system(system: System) -> bool:
    return "duct heater" in _words(system)


def _role(family_name: str) -> str | None:
    """The part of a VRF or split system a family is (rules.md "VRF and split as one block"): its indoor units,
    its outdoor (condensing) units, or its branch selectors or branch circuit controllers."""
    n = family_name.lower()
    if "indoor" in n:
        return "indoor"
    if "condensing" in n or "outdoor" in n or "heat pump" in n:
        return "outdoor"
    if "selector" in n or ("branch" in n and "controller" in n):
        return "branch"
    return None


def _roles(system: System) -> set[str]:
    return {r for r in (_role(f.name) for f in system.families) if r}


def _is_vrf(system: System) -> bool:
    """A VRF or split block: its shape or a family names it, or it has both indoor and outdoor units, or it has
    branch selectors. A heat pump alone is not one (an apartment heat pump is its own shape)."""
    words = _words(system)
    roles = _roles(system)
    return "vrf" in words or "split" in words or {"indoor", "outdoor"} <= roles or "branch" in roles


def _is_damper(device: Device) -> bool:
    return "damper" in device.slot.lower()


def _sequence_only(system: System) -> bool:
    """Named only in the sequence (rules.md "Systems named only in the sequence": "no drawing shows" it): the
    sequence cites it and no family count has a source or another count, with lines or without (VAL-4)."""
    return bool(system.sequence_refs) and all(not f.count.sources and not f.count.others for f in system.families)


# ---- the rules, one small function each (system level) ------------------------------------------------------


def _cites(system, shape, job, playbook) -> Iterator[Hit]:
    for d in system.devices:
        if not d.refs:
            yield (d.id, "must_fix", f"{d.name} has no usable citation from this job",
                   "Cite the passage of this job's documents that calls for it, or delete the line.")
        elif any(not r.source_id.strip() or not r.quote.strip() or not r.where.strip() for r in d.refs):
            # a ref missing only its place on a front-end device (system key "") is the planner's, which no writer
            # can fix (plan_read.where gives "" for an id not in the ledger): a check, not a must_fix
            placeless = all(r.source_id.strip() and r.quote.strip() for r in d.refs)
            severity = "check" if placeless and not system.key else "must_fix"
            yield (d.id, severity, f"a citation of {d.name} is missing its source id, quote or place",
                   "Cite the passage of this job's documents that calls for it, with its source id, the quote and "
                   "where it is, or delete the line.")


def _owners(system, shape, job, playbook) -> Iterator[Hit]:
    for d in system.devices:
        missing = [n for n, v in (("furnished by", d.furnished_by), ("installed by", d.installed_by),
                                  ("wired by", d.wired_by)) if v not in PARTIES]
        if missing:
            yield (d.id, "must_fix", f"{d.name} does not say who it is {', '.join(missing)}",
                   "Give the party that furnishes, installs and wires it.")
        else:
            yield from _verb(d, shape)


def _prints_verb(device: Device, shape: Shape | None) -> bool:
    """The line prints its verb: not an integration line (the house trio, whose rep line is the mechanical
    contractor's) and not a slot whose wording carries no {verb} ("VRF Communication Wiring", "Interlock with ...")."""
    if shape is None or device.slot not in shape.slot_kinds:
        return True
    if shape.slot_kinds[device.slot] == "integration":
        return False
    return "{verb}" in shape.wording.get(device.slot, "{verb}")


def _verb(d: Device, shape: Shape | None) -> Iterator[Hit]:
    """rules.md "Verb from the three answers": the verb follows from who furnishes, installs and wires (VAL-10).
    Furnish alone is a hardwired signal, so any AME furnishing fits it; Furnish and Wire is written for every valve
    "without exception" ("Verbs by device type"), so AME installing does not break it."""
    if not _prints_verb(d, shape):
        return
    f, i, w = (p == "AME" for p in (d.furnished_by, d.installed_by, d.wired_by))
    ok = {"Furnish and Install": f and i, "Furnish and Wire": f and w, "Furnish": f,
          "Install and Wire": not f and i and w, "Wire": not f and w}.get(d.verb)
    if not (f or i or w):
        yield (d.id, "must_fix", f"{d.name} is not AME's scope (another party furnishes, installs and wires "
               "it): move it to the exclusions", "Take the line out and name it in the exclusions.")
    elif ok is False:
        yield (d.id, "must_fix", f"{d.name}: the verb {d.verb} does not follow from who furnishes, installs and "
               f"wires it ({d.furnished_by}, {d.installed_by}, {d.wired_by})",
               "Set the verb from the three answers, or correct the party that furnishes, installs or wires it.")


def _slots(system, shape, job, playbook) -> Iterator[Hit]:
    if shape is None:
        if system.shape and system.shape not in playbook.shapes:     # the renderer cannot print this block
            yield (None, "must_fix", f"the shape '{system.shape}' is not in the Playbook",
                   "Set the shape to a Playbook shape name or leave it empty.")
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
    # a VRF or split system runs on its manufacturer's controls: the planner gives it "integration", and rules.md
    # "Point lines only on AME controllers" holds for it as for a packaged unit: no points, no AME controller (VAL-19)
    factory_vrf = system.control == "integration" and _is_vrf(system)
    if system.control != "packaged" and not factory_vrf:
        return
    for d in system.devices:
        kind = _kind(shape, d)
        if kind == "point" and d.verb.startswith("Furnish"):
            unit = "factory-controlled VRF or split system" if factory_vrf else "packaged unit"
            yield (d.id, "must_fix", f"{d.name}: AME does not furnish points on a {unit}",
                   "Take the point line out; AME integrates through the manufacturer's interface.")
        elif d.slot == "controller" and d.furnished_by == "AME":
            # rules.md "No AME controller on a packaged unit"
            yield (d.id, "must_fix", f"{d.name}: AME furnishes no DDC controller on a unit on factory controls",
                   "Delete the line; AME integrates through the manufacturer's interface.")
        elif factory_vrf:
            continue                    # the device check and the integration lines below are the packaged unit's
        elif kind == "device" and d.furnished_by == "AME":
            # the documents may give the device to the controls contractor ("Explicit assignment always wins",
            # "Mixed ownership device by device"); the model carries no such link, so a check (VAL-2)
            yield (d.id, "check", f"{d.name} is a device on the packaged unit that AME furnishes",
                   "If the documents give this device to the controls contractor, keep it; otherwise delete it.")
    # a block with no lines needs no integration lines (VAL-5); a VRF's integration lines are the VRF check's
    if factory_vrf or shape is None or not system.devices:
        return
    drive = _has_drive(system, shape)
    for slot in shape.slots_of_kind("integration"):
        if _is_drive_slot(slot) and not drive:
            continue
        n = sum(1 for d in system.devices if d.slot == slot)
        if n != 1:
            yield (None, "must_fix", f"The '{slot}' integration line is {'missing' if n == 0 else f'there {n} times'}",
                   "The integration lines appear exactly once in a packaged-control block.")


def _is_drive_slot(slot: str) -> bool:
    """A slot of the shape's VFD (drive) integration group: the Playbook's shapes name them vfd_comm_wiring,
    vfd_map_points and vfd_rep_assist (rules.md "Integration lines last": the VFD group comes first "when both
    apply")."""
    return slot.startswith("vfd_")


def _has_drive(system: System, shape: Shape) -> bool:
    """The block has a drive: a line in a slot of the shape that names a VFD (a VFD point such as vfd_control or
    supply_fan_vfd, or a line of the VFD integration group). Fields only: a drive the evidence names but no line
    carries is for the writer and the QC pass to catch, not this check."""
    return any("vfd" in d.slot.lower() for d in system.devices if d.slot in shape.slot_kinds)


def _loose(system, shape, job, playbook) -> Iterator[Hit]:
    if system.control != "packaged":
        return
    # shipped loose: the unit manufacturer furnishes it and AME installs it. A Wire line (the manufacturer mounts it,
    # AME wires it: "Factory-installed devices") and an Install and Wire line another trade furnishes ("Other
    # trades in brackets") are not shipped loose (VAL-1)
    for d in system.devices:
        loose = d.furnished_by == "Unit Mfr." and d.installed_by == "AME"
        if loose and (d.verb != "Install and Wire" or d.wired_by != "AME"):
            yield (d.id, "must_fix", f"{d.name} ships loose with the unit but its ownership is not "
                   "'Install and Wire' by AME with the unit manufacturer furnishing",
                   "Set the verb to Install and Wire, furnished by Unit Mfr., installed and wired by AME.")


def _dampers(system, shape, job, playbook) -> Iterator[Hit]:
    """The model carries no link from a damper to a fan, so this is never a must_fix: a damper block of its own is
    the Playbook's ("Untraced dampers in their own block", "Unclaimed dampers in their own block"), and a damper in
    a slot of the block's own shape (an air handler's oa_damper, a Motorized Dampers block's actuator) is where the
    shape puts it. Only a damper outside its shape's slots, in a block with no fan while the job has one, is a
    check (VAL-3)."""
    if _is_fan_system(system) or system.control == "packaged" or not any(_is_fan_system(s) for s in job.systems):
        return
    for d in system.devices:
        own = shape is not None and d.slot in shape.slot_kinds and not d.slot.startswith("other_")
        if _is_damper(d) and not own:
            yield (d.id, "check", f"{d.name} is a damper in a block with no fan, while the job has a fan block",
                   "If it serves a fan, move it under that fan; if it belongs to this equipment or no fan can be "
                   "traced, leave it.")


def _heater_words(playbook: Playbook) -> tuple[str, ...]:
    """The words that name a duct heater: "duct heater" and the kind words of the Playbook's duct heater shape."""
    words = {"duct heater"}
    for s in playbook.shapes.values():
        if "duct heater" in s.name.lower() or "duct heater" in s.kind_words:
            words.update(w for w in s.kind_words if w.strip())
    return tuple(sorted(words))


def _heater_lines(system: System, words: tuple[str, ...]) -> list[Device]:
    return [d for d in system.devices
            if re.search(r"duct_?heater", d.slot.lower()) or any(w in d.name.lower() for w in words)]


def _named(system: System) -> str:
    return f"{system.name} ({system.key})"


def _heaters(system, shape, job, playbook) -> Iterator[Hit]:
    """A duct heater is written in one place: when the job has a duct heater block, a heater line (by its slot or
    its words) in any other block is a must_fix; an empty heater block while another block carries the heater
    lines is a check naming both."""
    heater_blocks = [s for s in job.systems if _is_heater_system(s)]
    if not heater_blocks:
        return
    words = _heater_words(playbook)
    if _is_heater_system(system):
        if not system.devices:
            carriers = [s for s in job.systems if not _is_heater_system(s) and _heater_lines(s, words)]
            if carriers:
                yield (None, "check", f"{_named(system)} has no lines while "
                       f"{', '.join(_named(s) for s in carriers)} carries its duct heater lines",
                       "Write the heaters in one place: in this block, or under the unit each serves with this "
                       "block dropped.")
        return
    home = ", ".join(_named(s) for s in heater_blocks)
    for d in _heater_lines(system, words):
        yield (d.id, "must_fix", f"{d.name} is a duct heater line in {_named(system)}, while the job has the duct "
               f"heater block {home}", "Move it to the duct heater block, or drop that block and keep the heaters "
               "under the unit each serves.")


def _once_slots(shape: Shape | None) -> tuple[str, ...]:
    """The lines written once for a VRF or split system: every integration line and "VRF Communication Wiring"."""
    if shape is None:
        return ("comm_wiring", "map_points", "rep_assist", "vrf_comm_wiring")
    vrf_comm = ("vrf_comm_wiring",) if "vrf_comm_wiring" in shape.slot_kinds else ()
    return (*shape.slots_of_kind("integration"), *vrf_comm)


def _vrf(system, shape, job, playbook) -> Iterator[Hit]:
    """rules.md "VRF and split as one block": the indoor, outdoor and branch units in one block, and the integration
    lines and "VRF Communication Wiring" once (VAL-12). "VRF Communication Wiring" and the integration trio's BMS
    communication wiring are different lines, each written once."""
    if not _is_vrf(system):
        return
    for slot in _once_slots(shape):
        lines = [d for d in system.devices if d.slot == slot]
        if len(lines) > 1:
            yield (lines[1].id, "must_fix", f"The '{slot}' line appears {len(lines)} times in this VRF or split block",
                   "Write it once for the system.")
    # only a shape that has the line can miss it (a split system has none)
    if (shape is not None and "vrf_comm_wiring" in shape.slot_kinds and system.devices
            and not any(d.slot == "vrf_comm_wiring" for d in system.devices)):
        yield (None, "check", "This VRF block has no VRF Communication Wiring line", "Add it once.")
    # a block that is not a whole system (indoor and outdoor units) while another VRF or split block carries a part
    # it lacks: one system split across blocks. Two whole systems are two blocks, with branch selectors or without.
    roles = _roles(system)
    if not roles or {"indoor", "outdoor"} <= roles:
        return
    other = next((s for s in job.systems if s.key != system.key and _is_vrf(s) and _roles(s) - roles), None)
    if other is not None:
        lack = " and ".join(sorted(_roles(other) - roles))
        yield (None, "must_fix", f"The units of one VRF or split system are split across blocks ({system.key} has "
               f"no {lack} units, which {other.key} carries)", "Put the indoor, outdoor and branch units in one block.")


def _count_problems(count: Count, label: str) -> Iterator[tuple[str, str]]:
    top = count.highest()
    if count.value is None and top is not None:     # estimator ruling D9: None only when no count exists (VAL-18)
        yield (f"{label} prints 'Qty (##)' but a source gives {top}",
               f"Set the count to {top}, the highest, and name the other in the note.")
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
    family = next((f for f in system.families if f.count.value is None), None)
    if family is not None:
        yield (None, "check", f"The {family.name} count is unknown and carries no clarification",
               "Add one 'per drawings' or 'confirm' clarification to the block.")
    # a line whose wording prints its quantity, with the quantity unknown, prints "(Qty. ##)". The render module is
    # imported here, not at the top: `bms status` loads this module through the Playbook lint and must work when
    # the estimate stack (render, the price sheet) cannot import.
    from bms.render import line_form
    for d in system.devices:
        if d.quantity.highest() is None and "{qty}" in line_form(d, shape, playbook):
            yield (d.id, "check", f"{d.name}: its quantity is unknown and the block carries no clarification",
                   "Give the count from the evidence, or add one 'per drawings' or 'confirm' clarification to the "
                   "block.")


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
    """A sequence-only system prints "Qty (##)" and one 'per drawings' or 'confirm' clarification, with its lines or
    without: a count no source gives is a must_fix, a missing clarification a check (as an unknown count is)."""
    if not _sequence_only(system):
        return
    for f in system.families:
        if f.count.value is not None:
            yield (None, "must_fix", f"{system.name} has only a sequence of operation but the {f.name} count is "
                   f"{f.count.value}", "A sequence-only system prints 'Qty (##)'; clear the count.")
    if not any(c.kind in ("per_drawings", "confirm") for c in system.clarifications):
        yield (None, "check", f"{system.name} is named only in the sequence and carries no clarification",
               "Add one 'per drawings' clarification naming the drawings of the trade that shows it.")


def _left_out(system, shape, job, playbook) -> Iterator[Hit]:
    """A system with no lines prints nothing in the proposal (the renderer leaves it out): the estimator sees it."""
    if system.devices:
        return
    reason = ((system.no_scope_reason or "").strip()
              or "; ".join(c.text.strip() for c in system.clarifications if c.text.strip()))
    yield (None, "check", f"{system.name}: left out: no lines written"
           + (f"; the writer's reason: {reason}" if reason else "; the writer gave no reason"),
           "Write its lines from the evidence, or make it a named exception with its reason.")


def _id_hits(device_id, field: str, text: str, ids: SourceIds) -> Iterator[Hit]:
    """A client text checked with the shared detector (`SourceIds.scan`): an issued id in it is must_fix (the
    renderer takes the token out, so the sentence would print broken; the revise fixes it); an unissued token joined
    to an issued id ("S141 and S999", a citation) is a check (it prints as written). A tag, a sheet number and any
    other unissued lookalike ("Supply Fan F1", "(F1, F2)") are no finding (the estimator's ruling of 2026-10-05)."""
    found = ids.scan(text)
    issued = list(dict.fromkeys(f.token for f in found if f.kind == "issued"))
    if issued:
        yield (device_id, "must_fix", f"an id is in the client text of {field} ({', '.join(issued)})",
               "Name the document in words (\"the mechanical schedule\", \"sheet M-101\"); cite it as a Ref, never "
               "print an id.")
    other = list(dict.fromkeys(f.token for f in found if f.kind == "cited"))
    if other:
        yield (device_id, "check", f"{field} names {', '.join(other)}, which is no source id of this job and no tag; "
               "it prints as written", "Say what it is (a tag the schedule names), or take it out.")


def _where_hits(device, ids: SourceIds) -> Iterator[Hit]:
    """A where on a writer's device ref that names an issued id, after a sheet word or not ("Sheet S141,
    Mechanical.pdf page 3", "S141, Mechanical.pdf page 3", S141 no known sheet; `SourceIds.where_issued`): the
    renderer leaves the id out and with it the place, so the count note loses it; must_fix (L-D, FINAL-F)."""
    named = list(dict.fromkeys(t for r in citations.device_refs(device) for t in ids.where_issued(r.where)))
    if named:
        yield (device.id, "must_fix", f"a ref of {device.name} names the source id{'s' if len(named) > 1 else ''} "
               f"{', '.join(named)} as its place ({', '.join(named)} is no sheet of this job)",
               WHERE_ADVICE[0].upper() + WHERE_ADVICE[1:] + ".")


def _ids(system, shape, job, playbook) -> Iterator[Hit]:
    """Id-shaped tokens in wording that prints (clarifications, assumptions, device names, the reason a block has
    no lines): an issued id is must_fix, an unissued one joined to it a check (`bms.citations`, `_id_hits`)."""
    ids = SourceIds.of_job(job)
    for c in system.clarifications:
        yield from _id_hits(None, f"the {c.kind} clarification", c.text, ids)
    for d in system.devices:
        yield from _id_hits(d.id, f"the name of {d.name}", d.name, ids)
        if system.key:                    # a writer's device; the front end's refs are the planner's (K)
            yield from _where_hits(d, ids)
        a = d.assumption
        if a is not None:
            yield from _id_hits(d.id, f"the assumption on {d.name}", f"{a.what} {a.why}", ids)
    if not system.devices and system.no_scope_reason:
        yield from _id_hits(None, "the reason it has no lines", system.no_scope_reason, ids)


def _long_note(system, shape, job, playbook) -> Iterator[Hit]:
    for c in system.clarifications:
        if len(c.text.strip()) > LONG_TEXT:
            yield (None, "check", f"The {c.kind} clarification is {len(c.text.strip())} characters, over {LONG_TEXT}",
                   "Say it in fewer words; it prints whole.")


def _long_assumption(system, shape, job, playbook) -> Iterator[Hit]:
    for d in system.devices:
        a = d.assumption
        if a is None:
            continue
        size = len(f"{a.what.strip()}, because {a.why.strip()}")
        if size > LONG_TEXT:
            yield (d.id, "check", f"The assumption on {d.name} is {size} characters, over {LONG_TEXT}",
                   "Say what is assumed and why in fewer words; it prints whole.")


def _one_per_unit(slot: str) -> bool:
    """A slot written once per unit: the controller and a start/stop line. Any other line may total several per unit
    (two dampers on each fan), rules.md "Line quantity"."""
    return slot == "controller" or "start_stop" in slot


def _header_under(system, shape, job, playbook) -> Iterator[Hit]:
    """A device quantity above its family's header count, while the family names no other count: on a one-per-unit
    line the header undershoots (must_fix); on any other line it may be a total over the units, a check (VAL-9).
    Only a block with one family that prints a header (a damper family under a fan prints none)."""
    families = [f for f in system.families if "damper" not in f.name.lower()] or list(system.families)
    if len(families) != 1 or families[0].count.others:
        return
    header = families[0].count.highest()
    if header is None:
        return
    for d in system.devices:
        n = d.quantity.highest()
        if n is None or n <= header:
            continue
        if _one_per_unit(d.slot):
            yield (d.id, "must_fix", f"{d.name}: device quantity {n} is higher than the header count {header}: "
                   "print the higher count", f"Carry the {families[0].name} count at {n} with its source, or "
                   "correct the device quantity.")
        else:
            yield (d.id, "check", f"{d.name}: device quantity {n} is higher than the header count {header}",
                   f"If each {families[0].name} has more than one, keep the total; otherwise carry the "
                   f"{families[0].name} count at {n} with its source, or correct the device quantity.")


def _family_under(system, shape, job, playbook) -> Iterator[Hit]:
    """A device counted from a family (`counts.counted_from`: its quantity cites the family's count sources) whose
    quantity is below the family's printed count: the line may undershoot, and the line's quantity is what prints
    and prices (AI-1: a changed family count left the lines at the old one). A check, not a must_fix: a line can
    count fewer than its family (VFDs on 2 of 5 fans), and the run lifts a line a count rewrite left at the old
    count. A device of unknown count is not this check's."""
    from bms.counts import counted_from
    for d in system.devices:
        n = d.quantity.highest()
        if n is None:
            continue
        for f in system.families:
            header = f.count.highest()
            if header is not None and n < header and counted_from(d, f):
                yield (d.id, "check", f"{d.name}: device quantity {n} is counted from the {f.name} count but is "
                       f"lower than it ({header})", f"Carry the {f.name} count of {header} on the line, or cite the "
                       "source that gives the lower count.")
                break


_SYSTEM_RULES: tuple[tuple[str, Callable], ...] = (
    ("cites", _cites), ("owner", _owners), ("slot", _slots), ("subline", _sublines), ("packaged", _packaged), ("loose", _loose),
    ("damper", _dampers), ("heater", _heaters), ("vrf", _vrf), ("higher", _higher), ("unknown", _unknown),
    ("one_note", _one_note), ("assumption", _assumption), ("sequence", _sequence), ("left_out", _left_out),
    ("ids", _ids), ("long_note", _long_note), ("long_assumption", _long_assumption), ("header_under", _header_under),
    ("header_under", _family_under),
)

_FRONT_END_RULES = ("cites", "owner", "assumption", "one_note", "ids", "long_note", "long_assumption")


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

    # a device id used in more than one place is a device repeated, including the front end
    owners: dict[str, list[str]] = {}
    if fe is not None:
        for d in fe.devices:
            owners.setdefault(d.id, []).append("")
    for system in job.systems:
        for d in system.devices:
            owners.setdefault(d.id, []).append(system.key)

    def place(key: str) -> str:
        return "front end" if key == "" else key

    def duplicate(here: str, device: Device) -> Hit:
        others = sorted({place(k) for k in owners[device.id] if k != here} or {place(here)})
        return (device.id, "must_fix",
                f"{device.name} is listed more than once ({place(here)} and {', '.join(others)})",
                "Keep it in the one block it belongs to.")

    if fe is not None:
        order = {d.id: n for n, d in enumerate(fe.devices)}
        seen_front: set[str] = set()
        for d in fe.devices:
            if len(owners[d.id]) > 1 and d.id not in seen_front:
                add(-1, "", order, "once", duplicate("", d))
            seen_front.add(d.id)
    for index, system in enumerate(job.systems):
        order = {d.id: n for n, d in enumerate(system.devices)}
        shape = playbook.shapes.get(system.shape)
        for rule, check in _SYSTEM_RULES:
            for hit in check(system, shape, job, playbook):
                add(index, system.key, order, rule, hit)
        seen: set[str] = set()
        for d in system.devices:
            if len(owners[d.id]) > 1 and d.id not in seen:
                add(index, system.key, order, "once", duplicate(system.key, d))
            seen.add(d.id)
    ids = SourceIds.of_job(job)                   # a named exception prints too
    for exception in job.exceptions:
        # the whole job's finding (system key ""): no writer writes an exception, so no system's revise can fix it
        for hit in _id_hits(None, "the named exception", exception.text, ids):
            add(len(job.systems), "", {}, "ids", hit)
    found.sort(key=lambda item: item[0])
    return [f for _, f in found]
