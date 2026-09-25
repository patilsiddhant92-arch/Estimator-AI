"""The estimator's Master Template as data (assets/system_templates.json).

Each system says how its block looks: the header, the lines to choose from and
when each one applies, the "**" notes printed for the client, the hints that
are never printed, and the tech hours. The wording is the template's own; edit
it in the JSON, never here.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

ASSETS = Path(__file__).resolve().parents[3] / "assets"
TEMPLATES_FILE = ASSETS / "system_templates.json"

QUANTITIES = ("per_unit", "one", "counted", "none")
TECH_HOUR_BASES = ("unit", "hardware_point", "indoor_unit", "panel", "fan", "fixed", "line")
HARDWARE_VERBS = ("furnish and install", "furnish and wire", "furnish")
_PLACES = ("schedule", "sequence", "notes", "prefix", "spec_overview")


@dataclass(frozen=True)
class Condition:
    """Somewhere to look and the words that make it hold (any one word, in any one place)."""

    name: str
    schedule: tuple[str, ...] = ()
    sequence: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    prefix: tuple[str, ...] = ()
    spec_overview: tuple[str, ...] = ()


@dataclass(frozen=True)
class TemplateLine:
    text: str
    depth: int
    when: tuple[str, ...]
    unless: tuple[str, ...]
    choice: str | None
    default: bool
    quantity: str
    hardware_point: bool
    verb: str | None = None          # the scope verb the line starts with, as written
    trio: bool = False               # one of the three integration lines
    no_verb: bool = False            # the template writes this line without a verb (an interlock, a tie-in, ...)
    of: tuple[str, ...] = ()         # per_unit counts only these families (plant and group systems)


@dataclass(frozen=True)
class TechHours:
    per: str
    hours: float | None              # None: the template gives no hours for this system
    overrides: tuple[tuple[tuple[str, ...], float], ...] = ()
    of: tuple[str, ...] = ()         # which families to count for per unit / panel / fan / indoor_unit


@dataclass(frozen=True)
class ExceptionRule:
    """When the front end prints `front_end_line` and the job calls for this system, the system is
    not written as a block: its template line `exception` goes into the proposal's exceptions."""

    front_end_line: str
    exception: str                   # one of the system's own template lines, word for word
    called_for: Condition            # where the job asks for the system
    review: str                      # the review line; {where} is where the job asks for it


@dataclass(frozen=True)
class SystemTemplate:
    name: str
    prefixes: tuple[str, ...]
    kinds: tuple[str, ...]
    group: bool
    header: str
    conditions: dict[str, Condition]
    lines: tuple[TemplateLine, ...]
    client_notes: tuple[str, ...]
    hints: tuple[str, ...]
    tech_hours: TechHours
    extra_tech_hours: tuple[TechHours, ...] = ()   # added to tech_hours (gas detection: per panel and per fan)
    family_names: dict[str, str] = field(default_factory=dict)  # the template's own name for a family in a group header
    becomes_exception_when: ExceptionRule | None = None


@lru_cache(maxsize=4)
def _raw(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _verb(text: str, verbs: tuple[str, ...]) -> str | None:
    low = text.lower()
    for verb in sorted(verbs, key=len, reverse=True):
        if low.startswith(verb.lower() + " "):
            return text[: len(verb)]
    return None


def _is_trio(text: str, trio: tuple[str, ...]) -> bool:
    low = text.lower()
    lead = trio[0].split("{what}")[0].strip().lower()   # "furnish bms communication wiring to"
    return (low.startswith(lead + " ") and low.endswith("controls")) or low in (trio[1].lower(), trio[2].lower())


def _condition(name: str, raw: dict, where: str) -> Condition:
    unknown = set(raw) - set(_PLACES)
    if unknown:
        raise ValueError(f"{where}: condition {name} has unknown places {sorted(unknown)}")
    return Condition(name, *(tuple(raw.get(place, ())) for place in _PLACES))


def _tech_hours(raw: dict, where: str) -> TechHours:
    per = raw.get("per")
    if per not in TECH_HOUR_BASES:
        raise ValueError(f"{where}: tech hours per {per!r} is not one of {TECH_HOUR_BASES}")
    overrides = tuple((tuple(o["if"]), float(o["hours"])) for o in raw.get("when", ()))
    hours = raw.get("hours")
    return TechHours(per, None if hours is None else float(hours), overrides, tuple(raw.get("of", ())))


def _system(raw: dict, top: dict) -> SystemTemplate:
    name = raw["name"]
    verbs = tuple(top["verbs"])
    trio = tuple(top["integration_trio"])
    not_points = tuple(s.lower() for s in top.get("not_hardware_points_containing", ()))
    conditions = {n: _condition(n, c, name) for n, c in raw.get("conditions", {}).items()}
    lines = []
    for item in raw["lines"]:
        text = item["text"]
        where = f"{name}: {text!r}"
        quantity = item.get("quantity", "per_unit")
        if quantity not in QUANTITIES:
            raise ValueError(f"{where}: quantity {quantity!r} is not one of {QUANTITIES}")
        when, unless = tuple(item.get("when", ())), tuple(item.get("unless", ()))
        for cond in when + unless:
            if cond not in conditions:
                raise ValueError(f"{where}: condition {cond} is not defined")
        verb = _verb(text, verbs)
        is_trio = item.get("trio", _is_trio(text, trio))
        hardware = item.get("hardware_point")
        if hardware is None:
            hardware = (not is_trio and verb is not None and verb.lower() in HARDWARE_VERBS
                        and not any(s in text.lower() for s in not_points))
        lines.append(TemplateLine(
            text=text, depth=int(item.get("depth", 1)), when=when, unless=unless,
            choice=item.get("choice"), default=bool(item.get("default", False)), quantity=quantity,
            hardware_point=bool(hardware), verb=verb, trio=bool(is_trio),
            no_verb=bool(item.get("no_verb", False)), of=tuple(item.get("of", ())),
        ))
    groups: dict[str, list[TemplateLine]] = {}
    for line in lines:
        if line.choice:
            groups.setdefault(line.choice, []).append(line)
    for group, members in groups.items():
        defaults = sum(1 for m in members if m.default)
        if len(members) < 2 or defaults != 1:
            raise ValueError(f"{name}: choice {group} needs two or more lines and exactly one default "
                             f"(has {len(members)} lines, {defaults} defaults)")
    tech = raw.get("tech_hours") or {"per": "unit", "hours": None}
    tech_list = tech if isinstance(tech, list) else [tech]
    parsed = [_tech_hours(t, name) for t in tech_list]
    for th in parsed:
        for when, _ in th.overrides:
            for cond in when:
                if cond not in conditions:
                    raise ValueError(f"{name}: tech hours condition {cond} is not defined")
    applies = raw.get("applies_to", {})
    rule = None
    if raw.get("becomes_exception_when"):
        r = raw["becomes_exception_when"]
        if r["exception"] not in [line.text for line in lines]:
            raise ValueError(f"{name}: the exception {r['exception']!r} is not one of the system's template lines")
        rule = ExceptionRule(r["front_end_line"], r["exception"],
                             _condition("called_for", r["called_for"], name), r["review"])
    return SystemTemplate(
        name=name,
        prefixes=tuple(p.upper() for p in applies.get("prefixes", ())),
        kinds=tuple(applies.get("kinds", ())),
        group=bool(raw.get("group", False)),
        header=raw.get("header", "Qty ({n}) {kind} {tags}"),
        conditions=conditions,
        lines=tuple(lines),
        client_notes=tuple(raw.get("client_notes", ())),
        hints=tuple(raw.get("hints", ())),
        tech_hours=parsed[0],
        extra_tech_hours=tuple(parsed[1:]),
        family_names=dict(raw.get("family_names", {})),
        becomes_exception_when=rule,
    )


def load_templates(path: Path | str = TEMPLATES_FILE) -> tuple[SystemTemplate, ...]:
    """Every system in the Master Template file, checked. A bad entry raises ValueError naming it."""
    top = json.loads(Path(path).read_text(encoding="utf-8"))
    return tuple(_system(raw, top) for raw in top["systems"])


def template_for(prefix: str, kind: str, templates) -> SystemTemplate | None:
    """The template for a family or a group.

    The kind (or group name) decides first, matched against a template's name
    and its kinds. Then the tag prefix: a family standing alone prefers its own
    template over a plant group that also lists the prefix.
    """
    wanted = (kind or "").strip().lower()
    if wanted:
        for template in templates:
            if template.name.lower() == wanted or wanted in (k.lower() for k in template.kinds):
                return template
    code = (prefix or "").strip().upper()
    if not code:
        return None
    matches = [t for t in templates if code in t.prefixes]
    alone = [t for t in matches if not t.group]
    return (alone or matches or [None])[0]


def integration_trio(what: str) -> tuple[str, str, str]:
    """The three integration lines that go together, for "Chiller", "Rooftop Unit", or "" (plain factory controls)."""
    first, second, third = _raw(TEMPLATES_FILE.resolve())["integration_trio"]
    first = " ".join(first.replace("{what}", (what or "").strip()).split())
    return first, second, third
