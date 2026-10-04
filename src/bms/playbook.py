"""The Playbook (rebuild design §4.1): the one rule book, read from `playbook/`.

- `rules.md`  — every practice rule in plain words; "## " per topic, "### " per rule (its short name is the rule id
  a Finding names). Loaded whole as the cached instructions of every AI step (`Playbook.rules_text`).
- `shapes.json` — one shape per system type: header form, family names, line order, slot kinds, wording per slot,
  tech-hour rule. Shape only, never content.
- `wording.json` — verbs, owner brackets, integration trio, clarification forms, header and quantity forms.

`load_playbook(root)` reads and checks all three; a malformed file raises `PlaybookError` naming the file and the
problem. The format of each file is documented in its own "$format" object (rules.md: its top comment).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from bms.model import CLARIFICATION_KINDS, PARTIES, VERBS

DEFAULT_ROOT = Path(__file__).resolve().parents[2] / "playbook"
TECH_HOUR_BASES = ("unit", "hardware_point", "indoor_unit", "panel", "fan", "fixed", "line")
SLOT_KINDS = ("device", "point", "interlock", "integration", "wiring")
SAMPLE_MARK = "<!-- sample -->"


class PlaybookError(ValueError):
    """A Playbook file that cannot be used; the message names the file and what is wrong."""


@dataclass(frozen=True)
class Rule:
    topic: str          # its "## " heading
    name: str           # its "### " heading: the id a Finding.rule names
    text: str           # its plain sentences (the sample marker removed)
    sample: bool = False


@dataclass(frozen=True)
class TechHours:
    per: str                                        # one of TECH_HOUR_BASES
    hours: float | None                             # per item; None: none unless a `when` holds
    when: tuple[tuple[tuple[str, ...], float], ...] = ()   # (slots that must all have a device, hours)


@dataclass(frozen=True)
class Shape:
    name: str
    prefixes: tuple[str, ...]
    kind_words: tuple[str, ...]
    header: str
    family_names: tuple[str, ...]
    line_order: tuple[str, ...]
    slot_kinds: dict[str, str]
    wording: dict[str, str]
    tech_hours: TechHours
    under: dict[str, str] = field(default_factory=dict)    # sub-line slot -> its parent slot (prints one level in)
    order: int = 10                                        # block order in the scope: lower prints first (DEFAULT_ORDER)

    def parent_of(self, slot: str) -> str | None:
        """The slot a sub-line slot prints under, or None for a line of its own."""
        return self.under.get(slot)

    def slots_of_kind(self, kind: str) -> tuple[str, ...]:
        return tuple(s for s in self.line_order if self.slot_kinds[s] == kind)


@dataclass(frozen=True)
class Wording:
    verbs: tuple[str, ...]
    owner_brackets: dict[str, str]                  # party -> " (Furnished by …)"
    integration_trio: tuple[str, ...]               # the three lines; {what} names the equipment
    integration_depths: tuple[int, ...]
    clarifications: dict[str, str]                  # kind -> "*{text} …"
    header: dict[str, str]                          # count, unknown_count, tags_joiner
    quantity: dict[str, str]                        # line, unknown, others_note
    draft: tuple[str, ...] = ()


@dataclass(frozen=True)
class Playbook:
    rules_text: str                                 # rules.md whole: the cached instructions of every AI step
    topics: tuple[str, ...]
    rules: dict[str, Rule]                          # by name, in file order
    shapes: dict[str, Shape]                        # by name, in file order
    wording: Wording
    root: Path

    def rule(self, name: str) -> Rule:
        try:
            return self.rules[name]
        except KeyError:
            raise KeyError(f"no Playbook rule named {name!r}") from None

    def shape(self, name: str) -> Shape:
        try:
            return self.shapes[name]
        except KeyError:
            raise KeyError(f"no Playbook shape named {name!r}") from None

    def shape_for(self, system_kind: str, prefixes) -> Shape | None:
        """The shape for a system: the first shape (file order) one of whose prefixes is one of `prefixes`
        (compared upper case, without dashes or spaces); else the first whose kind words appear in `system_kind`
        (lower case, whole words, a plural s / es allowed); else None (an untemplated system — it is still written, from its evidence)."""
        wanted = {_plain_prefix(p) for p in prefixes or () if p}
        for shape in self.shapes.values():
            if wanted & set(shape.prefixes):
                return shape
        kind = " ".join(re.findall(r"[a-z0-9]+", (system_kind or "").lower()))
        for shape in self.shapes.values():
            if any(re.search(rf"\b{re.escape(w)}(?:s|es)?\b", kind) for w in shape.kind_words):
                return shape
        return None


def _plain_prefix(prefix: str) -> str:
    return re.sub(r"[\s\-_]", "", str(prefix)).upper()


def load_playbook(root: Path = DEFAULT_ROOT) -> Playbook:
    """The Playbook in `root` (default: the repo's `playbook/`). Raises PlaybookError on a malformed file."""
    root = Path(root)
    rules_text, topics, rules = _load_rules(root / "rules.md")
    shapes = _load_shapes(root / "shapes.json")
    wording = _load_wording(root / "wording.json")
    return Playbook(rules_text, topics, rules, shapes, wording, root)


# ---- rules.md ------------------------------------------------------------------------------------------------

def _load_rules(path: Path) -> tuple[str, tuple[str, ...], dict[str, Rule]]:
    text = _read(path)
    body = re.sub(r"<!--(?!\s*sample\s*-->).*?-->", "", text, flags=re.S)   # comments out, sample marks kept
    topics: list[str] = []
    rules: dict[str, Rule] = {}
    topic: str | None = None
    current: tuple[str, list[str]] | None = None

    def close() -> None:
        if current is None:
            return
        name, lines = current
        joined = "\n".join(lines).strip()
        sample = SAMPLE_MARK in joined
        joined = joined.replace(SAMPLE_MARK, "").strip()
        if not joined:
            raise PlaybookError(f"{path.name}: rule {name!r} has no text")
        rules[name] = Rule(topic or "", name, joined, sample)

    for n, line in enumerate(body.splitlines(), start=1):
        if line.startswith("### "):
            close()
            name = line[4:].strip()
            if topic is None:
                raise PlaybookError(f"{path.name} line {n}: rule {name!r} is not under a topic (## heading)")
            if not name:
                raise PlaybookError(f"{path.name} line {n}: a rule with no name")
            if name in rules:
                raise PlaybookError(f"{path.name} line {n}: rule {name!r} appears twice")
            current = (name, [])
        elif line.startswith("## "):
            close()
            current = None
            topic = line[3:].strip()
            if not topic or topic in topics:
                raise PlaybookError(f"{path.name} line {n}: topic {topic!r} is empty or appears twice")
            topics.append(topic)
        elif line.startswith("#### "):
            raise PlaybookError(f"{path.name} line {n}: only ## topics and ### rules are allowed")
        elif current is not None:
            current[1].append(line)
    close()
    if not topics:
        raise PlaybookError(f"{path.name}: no topic (## heading)")
    return text, tuple(topics), rules


# ---- shapes.json ---------------------------------------------------------------------------------------------

def _strings(value, where: str, path: Path, allow_empty: bool = True) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
        raise PlaybookError(f"{path.name}: {where} must be a list of non-empty texts")
    if not allow_empty and not value:
        raise PlaybookError(f"{path.name}: {where} must not be empty")
    return tuple(value)


def _text_map(value, where: str, path: Path) -> dict[str, str]:
    if not isinstance(value, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in value.items()):
        raise PlaybookError(f"{path.name}: {where} must map names to texts")
    return dict(value)


_SHAPE_KEYS = {"name", "applies_to", "header", "family_names", "line_order", "slot_kinds", "wording", "tech_hours"}
_OPTIONAL_SHAPE_KEYS = {"under", "order"}
DEFAULT_ORDER = 10          # a shape with no "order": the equipment blocks


def _load_shapes(path: Path) -> dict[str, Shape]:
    data = _json(path)
    if not isinstance(data.get("$format"), dict):
        raise PlaybookError(f"{path.name}: the \"$format\" object is missing")
    raw = data.get("shapes")
    if not isinstance(raw, list):
        raise PlaybookError(f"{path.name}: \"shapes\" must be a list")
    shapes: dict[str, Shape] = {}
    for n, entry in enumerate(raw):
        where = f"shapes[{n}]"
        if not isinstance(entry, dict):
            raise PlaybookError(f"{path.name}: {where} must be an object")
        missing, extra = _SHAPE_KEYS - set(entry), set(entry) - _SHAPE_KEYS - _OPTIONAL_SHAPE_KEYS
        if missing or extra:
            raise PlaybookError(f"{path.name}: {where} " + "; ".join(
                part for part in (f"is missing {', '.join(sorted(missing))}" if missing else "",
                                  f"has unknown {', '.join(sorted(extra))}" if extra else "") if part))
        name = entry["name"]
        if not isinstance(name, str) or not name.strip():
            raise PlaybookError(f"{path.name}: {where}.name must be a non-empty text")
        where = f"shape {name!r}"
        if name in shapes:
            raise PlaybookError(f"{path.name}: {where} appears twice")
        applies = entry["applies_to"]
        if not isinstance(applies, dict) or set(applies) != {"prefixes", "kind_words"}:
            raise PlaybookError(f"{path.name}: {where}.applies_to must have exactly prefixes and kind_words")
        prefixes = _strings(applies["prefixes"], f"{where}.applies_to.prefixes", path)
        if any(p != _plain_prefix(p) for p in prefixes):
            raise PlaybookError(f"{path.name}: {where}.applies_to.prefixes must be upper case with no dash or space")
        kind_words = _strings(applies["kind_words"], f"{where}.applies_to.kind_words", path)
        if any(w != w.lower() for w in kind_words):
            raise PlaybookError(f"{path.name}: {where}.applies_to.kind_words must be lower case")
        header = entry["header"]
        if not isinstance(header, str) or "{n}" not in header:
            raise PlaybookError(f"{path.name}: {where}.header must be a text with {{n}}")
        family_names = _strings(entry["family_names"], f"{where}.family_names", path, allow_empty=False)
        line_order = _strings(entry["line_order"], f"{where}.line_order", path, allow_empty=False)
        if len(set(line_order)) != len(line_order):
            raise PlaybookError(f"{path.name}: {where}.line_order names a slot twice")
        slot_kinds = _text_map(entry["slot_kinds"], f"{where}.slot_kinds", path)
        wording = _text_map(entry["wording"], f"{where}.wording", path)
        for label, mapping in (("slot_kinds", slot_kinds), ("wording", wording)):
            if set(mapping) != set(line_order):
                raise PlaybookError(f"{path.name}: {where}.{label} must cover exactly the slots of line_order")
        bad = sorted(k for k, v in slot_kinds.items() if v not in SLOT_KINDS)
        if bad:
            raise PlaybookError(f"{path.name}: {where}.slot_kinds: {', '.join(bad)} not one of {SLOT_KINDS}")
        under = _under(entry.get("under", {}), where, path, line_order)
        order = entry.get("order", DEFAULT_ORDER)
        if isinstance(order, bool) or not isinstance(order, int) or order < 0:
            raise PlaybookError(f"{path.name}: {where}.order must be a whole number, 0 or more")
        shapes[name] = Shape(name, prefixes, kind_words, header, family_names, line_order, slot_kinds, wording,
                             _tech_hours(entry["tech_hours"], where, path, set(line_order)), under, order)
    return shapes


def _under(raw, where: str, path: Path, line_order: tuple[str, ...]) -> dict[str, str]:
    """The optional sub-line map: slot -> the parent slot it prints one level in under. Both are slots of the shape
    and the parent comes earlier in line_order (so a chain never loops)."""
    under = _text_map(raw, f"{where}.under", path)
    position = {slot: n for n, slot in enumerate(line_order)}
    for slot, parent in under.items():
        if slot not in position or parent not in position:
            raise PlaybookError(f"{path.name}: {where}.under: {slot!r} -> {parent!r} names a slot not in line_order")
        if position[parent] >= position[slot]:
            raise PlaybookError(f"{path.name}: {where}.under: the parent {parent!r} must come before {slot!r} in "
                                "line_order")
    return under


def _tech_hours(raw, where: str, path: Path, slots: set[str]) -> TechHours:
    if not isinstance(raw, dict) or set(raw) != {"per", "hours", "when"}:
        raise PlaybookError(f"{path.name}: {where}.tech_hours must have exactly per, hours and when")
    if raw["per"] not in TECH_HOUR_BASES:
        raise PlaybookError(f"{path.name}: {where}.tech_hours.per must be one of {TECH_HOUR_BASES}")
    hours = raw["hours"]
    if hours is not None and (isinstance(hours, bool) or not isinstance(hours, (int, float)) or hours < 0):
        raise PlaybookError(f"{path.name}: {where}.tech_hours.hours must be a number or null")
    when = []
    if not isinstance(raw["when"], list):
        raise PlaybookError(f"{path.name}: {where}.tech_hours.when must be a list")
    for cond in raw["when"]:
        if (not isinstance(cond, dict) or set(cond) != {"if", "hours"}
                or isinstance(cond["hours"], bool) or not isinstance(cond["hours"], (int, float))):
            raise PlaybookError(f"{path.name}: {where}.tech_hours.when entries must be {{\"if\": [...], \"hours\": n}}")
        named = _strings(cond["if"], f"{where}.tech_hours.when.if", path, allow_empty=False)
        if not set(named) <= slots:
            raise PlaybookError(f"{path.name}: {where}.tech_hours.when names a slot not in line_order")
        when.append((named, float(cond["hours"])))
    return TechHours(raw["per"], None if hours is None else float(hours), tuple(when))


# ---- wording.json --------------------------------------------------------------------------------------------

def _load_wording(path: Path) -> Wording:
    data = _json(path)
    if not isinstance(data.get("$format"), dict):
        raise PlaybookError(f"{path.name}: the \"$format\" object is missing")
    for key in ("verbs", "owner_brackets", "integration_trio", "clarifications", "header", "quantity"):
        if key not in data:
            raise PlaybookError(f"{path.name}: {key} is missing")
    verbs = _strings(data["verbs"], "verbs", path)
    if verbs != VERBS:
        raise PlaybookError(f"{path.name}: verbs must be exactly {list(VERBS)}")
    brackets = _text_map(data["owner_brackets"], "owner_brackets", path)
    wanted = set(PARTIES) - {"AME"}
    if set(brackets) != wanted:
        raise PlaybookError(f"{path.name}: owner_brackets must name exactly {sorted(wanted)}")
    trio = data["integration_trio"]
    if not isinstance(trio, dict) or set(trio) != {"lines", "depths"}:
        raise PlaybookError(f"{path.name}: integration_trio must have exactly lines and depths")
    lines = _strings(trio["lines"], "integration_trio.lines", path)
    depths = trio["depths"]
    if len(lines) != 3 or not isinstance(depths, list) or len(depths) != 3 or any(d not in (1, 2) for d in depths):
        raise PlaybookError(f"{path.name}: integration_trio needs three lines and three depths of 1 or 2")
    forms = _text_map(data["clarifications"], "clarifications", path)
    if set(forms) != set(CLARIFICATION_KINDS) or not all(f.startswith("*") and "{text}" in f for f in forms.values()):
        raise PlaybookError(f"{path.name}: clarifications must give a \"*…{{text}}…\" form for each of "
                            f"{list(CLARIFICATION_KINDS)}")
    header = _text_map(data["header"], "header", path)
    if set(header) != {"count", "unknown_count", "tags_joiner"}:
        raise PlaybookError(f"{path.name}: header must have exactly count, unknown_count and tags_joiner")
    quantity = _text_map(data["quantity"], "quantity", path)
    if set(quantity) != {"line", "unknown", "others_note"}:
        raise PlaybookError(f"{path.name}: quantity must have exactly line, unknown and others_note")
    draft = _strings(data.get("$draft", []), "$draft", path)
    return Wording(verbs, brackets, lines, tuple(depths), forms, header, quantity, draft)


# ---- files ---------------------------------------------------------------------------------------------------

def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        raise PlaybookError(f"{path}: cannot be read ({error.strerror or error})") from None


def _json(path: Path) -> dict:
    try:
        data = json.loads(_read(path))
    except ValueError as error:
        raise PlaybookError(f"{path.name}: not valid JSON ({error})") from None
    if not isinstance(data, dict):
        raise PlaybookError(f"{path.name}: must be a JSON object")
    return data
