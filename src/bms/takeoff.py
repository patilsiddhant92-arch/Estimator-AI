"""The takeoff register.

HarkPro owns the reader in this module. Add that reader above the mark at the end of this file.
The Demolition Scope builder below the mark is T-G1.
"""
from __future__ import annotations

from bms.model import DemolitionLine, Unit

# HarkPro: the takeoff reader goes above this line.

# ---- Demolition Scope (T-G1) -------------------------------------------------------------------------------

# A unit of one of these statuses prints in the Demolition Scope. new and future do not.
_ACTION = {
    "demolish": "demo",
    "demolish_with_work": "demo",
    "existing_remain": "existing to remain",
    "relocate": "relocation",
}


def demolition_lines(units: tuple[Unit, ...]) -> tuple[DemolitionLine, ...]:
    """One Demolition Scope line per family and action, in the order the units first show that pair.

    demolish and demolish_with_work are "demo". existing_remain is "existing to remain". relocate is
    "relocation". new and future give no line. count is the sum of Unit.count. refs is the union of the
    units' refs, in first-seen order. note joins the reason text of each demolish_with_work unit with "; ".
    A blank reason is left out of the note.
    """
    groups: dict[tuple[str, str], dict] = {}
    order: list[tuple[str, str]] = []
    for unit in units:
        action = _ACTION.get(unit.status)
        if action is None:
            continue
        key = (unit.family, action)
        group = groups.get(key)
        if group is None:
            group = {"count": 0, "refs": [], "notes": []}
            groups[key] = group
            order.append(key)
        group["count"] += unit.count
        for ref in unit.refs:
            if ref not in group["refs"]:
                group["refs"].append(ref)
        if unit.status == "demolish_with_work" and unit.reason.strip():
            group["notes"].append(unit.reason.strip())
    lines = []
    for family, action in order:
        group = groups[(family, action)]
        lines.append(DemolitionLine(family, action, group["count"], tuple(group["refs"]),
                                    "; ".join(group["notes"])))
    return tuple(lines)
