"""Controls concepts: the shared device vocabulary the coverage gate matches on.

`concepts(text)` gives the concept keys a text names. Patterns run in order and each match is blanked out before
the next pattern runs, so "fire/smoke damper" is a fire/smoke item and not a control damper, and "radiator control
valve" is perimeter radiation and not a generic control valve.

PRIMARY concepts are things that print as a scope line of their own: a fact naming one must have that concept
covered. SECONDARY concepts are context (a panel the device lands on, a status point, "integration" in general);
a fact naming only secondary concepts is accounted when any one of them is covered.
"""
from __future__ import annotations

import re

# key, label, primary?, patterns
_TABLE: list[tuple[str, str, bool, list[str]]] = [
    ("lighting_integration", "Lighting control integration (Lutron / lighting system)", True,
     [r"lutron", r"\bvive\b", r"lighting (?:control|system|vendor|shop|occupancy|panel)\w*"]),
    ("fire_smoke", "Fire / smoke damper or detector", True,
     [r"(?:combination\s+)?fire\s*/?\s*smoke\s+dampers?", r"fire\s+dampers?", r"smoke\s+(?:dampers?|detectors?)",
      r"\bfsd\b"]),
    ("local_alarm", "Local alarm / RAM (remote alarm) module", True,
     [r"local\s+alarm", r"\bram\b", r"remote\s+alarm", r"alarm\s+(?:panel|module)", r"a/v\s+alarm"]),
    ("leak", "Leak detector / leak sensor", True, [r"leak\w*", r"drip\s+pan"]),
    ("high_water", "Float switch / high water alarm", True,
     [r"float\w*(?:\s+switch)?", r"high[\s-]+water", r"overflow"]),
    ("radiation", "Radiator / perimeter heat valve", True,
     [r"(?:perimeter\s+)?(?:steam\s+)?radiat(?:or|ion)s?(?:\s+control)?(?:\s+valves?)?",
      r"perimeter\s+(?:steam|heat\w*|radiation)(?:\s+systems?)?", r"steam\s+systems?"]),
    ("interlock", "Interlock", True, [r"interlock\w*"]),
    ("dp_switch", "Differential pressure / airflow switch", True,
     [r"differential\s+pressure\s+switch\w*", r"air\s*flow\s+switch\w*", r"\bafs-?\d+\b"]),
    ("occupancy", "Occupancy sensor", True, [r"occupan\w*", r"\bocc\b"]),
    ("co2", "CO2 sensor", True, [r"\bco2\b", r"co₂", r"carbon\s+dioxide", r"demand\s+control\s+ventilation"]),
    ("humidity", "Humidity sensor", True, [r"humidity", r"humidistat"]),
    ("thermostat", "Space temperature sensor / thermostat", True,
     [r"thermostat\w*", r"space\s+temp\w*(?:\s+sensors?)?", r"(?:zone\s+)?temperature\s+sensors?", r"zone\s+sensors?",
      r"space\s+sensors?", r"^t$"]),
    ("damper", "Control / motorized damper and actuator", True,
     [r"(?:motorized\s+|control\s+|outside\s+air\s+)?dampers?(?:\s+actuators?)?", r"actuators?", r"^m$",
      r"^m\s*\("]),
    ("pressure", "Pressure sensor", True,
     [r"(?:duct\s+|static\s+|building\s+)?pressure\s+sensors?", r"static\s+pressure", r"^sp$"]),
    ("valve", "Control valve", True, [r"control\s+valves?", r"valve\s+actuators?"]),
    ("current_switch", "Current switch / status sensor", True, [r"current\s+(?:switch|sensor|transducer)\w*"]),
    ("meter", "Meter", True, [r"\bmeters?\b", r"\bbtu\b"]),
    ("panel", "Control panel", False, [r"control\s+panels?", r"\blcp\b", r"\bpanels?\b"]),
    ("controller", "DDC controller", False, [r"controllers?", r"\bddc\b", r"open\s+protocol"]),
    ("transformer", "Transformer", False, [r"transformers?"]),
    ("graphics", "Graphics / programming", False, [r"graphic\w*", r"programming"]),
    ("integration", "BMS integration / communication / points", False,
     [r"integrat\w*", r"communication\w*", r"interface", r"\bbacnet\b", r"\bmodbus\b", r"map(?:ping)?\s+(?:all\s+)?"
      r"(?:available\s+)?points", r"bms\s+connection", r"monitor\s+status"]),
    ("status", "Status point", False, [r"\bstatus\b"]),
    ("alarm", "Alarm point", False, [r"alarms?"]),
    ("controls", "Controls (general)", False,
     [r"\batc\b", r"controls?\s+(?:contractor|vendor|manufacturer|wiring|system)", r"\bbms\b", r"\bbas\b",
      r"temperature\s+controls?", r"automatic\s+controls?", r"control\s+wiring"]),
]

LABELS = {k: label for k, label, _, _ in _TABLE}
PRIMARY = frozenset(k for k, _, primary, _ in _TABLE if primary)
SECONDARY = frozenset(k for k, _, primary, _ in _TABLE if not primary)
_COMPILED = [(k, [re.compile(p, re.I) for p in pats]) for k, _, _, pats in _TABLE]


def concepts(text: str) -> set[str]:
    """The concept keys `text` names."""
    work = " ".join(str(text or "").split())
    found: set[str] = set()
    for key, pats in _COMPILED:
        for pat in pats:
            if pat.search(work):
                found.add(key)
                work = pat.sub(" ", work)
    return found


def subject_concepts(subject: str) -> set[str]:
    """Concepts of a short subject: a bare device symbol ("T", "SP", "M", "OCC") counts too."""
    return concepts(subject.strip())


def is_relevant(found: set[str]) -> bool:
    return bool(found)
