"""The order of points inside a block and the Master Template's front-end format (T-005e, GEM v4, estimator 2026-10-11).

- `position(text, verb, slot, slot_kind)`: a printed line's place in the GEM v4 standard order (1 the DDC controller
  ... 18 other Wire, 19 the integration group, 20 the Miscellaneous Responsibilities), from `assets/gem_order.json`'s
  rules (first match wins).
- `is_catch_all(slot, line_order)`: the line is placed by the standard order (a catch-all slot, or a slot the shape
  lacks); every other slot of a shape prints in the shape's line order (its Master Template entry, GEM v4 ~396-402).
- `place(template, p)`: where a line of position `p` goes among a block's template lines (their positions, in print
  order): after the last of the same position, else after the first of a lower position and before the next of a
  higher one.
- `integration_rank(slot)`: 0 for the VFD group's slots (first when both groups apply), else 1.
- `alternatives(shape_name)`, `alternative_word()`: the Master Template's "OR" groups of slots.
- `minimum_points()`, `valve_rules()`: the words of the pump minimum and the valve rules.
- `front_end_rank(text)`, `front_end_entry(text)`, `existing_lines()`: the Master Template's front-end order and its
  "Extension of Existing" lines.

The words live in the asset, never here. Pure functions; the asset is read once.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

ASSET = Path(__file__).resolve().parents[2] / "assets" / "gem_order.json"
INTEGRATION = 19                    # the integration group: always last within the scope (GEM v4 ~430, ~433-437)
MISCELLANEOUS = 20                  # the Miscellaneous Responsibilities: after the integration lines (GEM v4 ~466)


@dataclass(frozen=True)
class _Rule:
    position: int
    words: tuple[re.Pattern, ...]
    not_words: tuple[re.Pattern, ...]
    verbs: frozenset[str]
    slots: frozenset[str]
    slot_kinds: frozenset[str]

    def matches(self, text: str, verb: str | None, slot: str, slot_kind: str | None) -> bool:
        if self.verbs and (verb or "") not in self.verbs:
            return False
        if self.slots and slot not in self.slots:
            return False
        if self.slot_kinds and (slot_kind or "") not in self.slot_kinds:
            return False
        if self.words and not any(w.search(text) for w in self.words):
            return False
        if any(w.search(text) for w in self.not_words):
            return False
        return True


@dataclass(frozen=True)
class _Order:
    rules: tuple[_Rule, ...]
    default: int
    catch_all: frozenset[str]
    integration_first: frozenset[str]
    front_end: tuple[tuple[str, tuple[re.Pattern, ...]], ...]
    existing: tuple[tuple[str, str], ...]
    alternatives: dict
    alternative_word: str
    data: dict


def _patterns(words) -> tuple[re.Pattern, ...]:
    return tuple(re.compile(w, re.I) for w in words or ())


def _rule(entry: dict) -> _Rule:
    return _Rule(int(entry["position"]), _patterns(entry.get("words")), _patterns(entry.get("not_words")),
                 frozenset(entry.get("verbs", ())), frozenset(entry.get("slots", ())),
                 frozenset(entry.get("slot_kinds", ())))


@lru_cache(maxsize=4)
def load(path: str = str(ASSET)) -> _Order:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    front = data["front_end"]
    alternatives = data.get("alternatives", {})
    return _Order(rules=tuple(_rule(r) for r in data["rules"]), default=int(data.get("default_position", 11)),
                  catch_all=frozenset(data.get("catch_all_slots", {}).get("slots", ())),
                  integration_first=frozenset(data.get("integration", {}).get("first_slots", ())),
                  front_end=tuple((e["name"], _patterns(e["words"])) for e in front["order"]),
                  existing=tuple((line["text"], line["match"]) for line in front["existing_lines"]["lines"]),
                  alternatives={name: tuple(frozenset(g) for g in groups)
                                for name, groups in alternatives.get("groups", {}).items()},
                  alternative_word=alternatives.get("word", "OR"), data=data)


def position(text: str, verb: str | None = None, slot: str = "", slot_kind: str | None = None) -> int:
    """The line's GEM position (1-20): the first rule of the asset it matches, else the default. `text` is the line
    as printed (verb included), `verb` the device's verb when the line prints it (None for a fixed wording)."""
    order = load()
    text = (text or "").strip()
    for rule in order.rules:
        if rule.matches(text, verb, slot, slot_kind):
            return rule.position
    return order.default


def is_catch_all(slot: str, line_order) -> bool:
    """The line is placed by the standard order: its slot is a catch-all slot, or one the shape lacks."""
    return slot in load().catch_all or slot not in tuple(line_order or ())


def place(template: list[int], p: int) -> float:
    """Where a line of position `p` goes among the template lines (their positions, in print order), as a place
    between two indexes (k - 0.5 prints after template line k - 1 and before line k): after the last template line of
    the same position; else after the first template line of a lower position and before the next one of a higher
    position; else first (no lower one) or last (no higher one after it)."""
    same = [k for k, q in enumerate(template) if q == p]
    if same:
        return same[-1] + 0.5
    lower = next((k for k, q in enumerate(template) if q < p), None)
    if lower is None:
        return -0.5
    higher = next((k for k in range(lower + 1, len(template)) if template[k] > p), None)
    return (higher - 0.5) if higher is not None else len(template) - 0.5


def integration_rank(slot: str) -> int:
    """0 for a slot of the VFD group (it prints first when both groups apply), else 1."""
    return 0 if slot in load().integration_first else 1


def alternatives(shape_name: str | None) -> tuple[frozenset, ...]:
    """The Master Template's "OR" groups of slots for this shape (each a set of slots), () for none."""
    return load().alternatives.get(shape_name or "", ())


def alternative_word() -> str:
    return load().alternative_word


def minimum_points() -> dict:
    return load().data.get("minimum_points", {})


def valve_rules() -> dict:
    return load().data.get("valves", {})


def front_end_entry(text: str) -> str:
    """The Master Template front-end entry a line is (its name in the asset), "" for none."""
    text = (text or "").strip()
    for name, words in load().front_end:
        if any(w.search(text) for w in words):
            return name
    return ""


def front_end_rank(text: str) -> int:
    """The line's place in the Master Template's front-end order; a line no entry matches ranks after them all."""
    names = [name for name, _ in load().front_end]
    entry = front_end_entry(text)
    return names.index(entry) if entry else len(names)


def existing_lines() -> tuple[tuple[str, str], ...]:
    """The Master Template's "Extension of Existing" lines in its order: (the line's text, the entry it matches)."""
    return load().existing
