"""The order of points inside a block and the Master Template's front-end format (T-005e, estimator 2026-10-11).

- `position(text, verb, slot, slot_kind)`: a printed line's place in the GEM v3.2 order of points (1 the DDC
  controller ... 20 the integration lines), from `assets/gem_order.json`'s rules (first match wins). The renderer
  sorts a block's lines by it, then by the shape's slot order (the Master Template's), then by the writer's order.
- `front_end_rank(text)`: a front-end line's place in the Master Template's front-end order (network level control
  panel, workstation, server, POT, UPS, graphics, training, IT infrastructure, then the rest).
- `existing_lines()`: the Master Template's "Extension of Existing" lines, each with the front-end entry it matches.
- `sub_heading(shape_name)`: the Master Template's unnumbered sub-heading over a stacked block of that shape, or "".

The words live in the asset, never here. Pure functions; the asset is read once.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

ASSET = Path(__file__).resolve().parents[2] / "assets" / "gem_order.json"
INTEGRATION = 20                    # the integration lines' position: always last within a block


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
    front_end: tuple[tuple[str, tuple[re.Pattern, ...]], ...]
    existing: tuple[tuple[str, str], ...]
    sub_headings: dict


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
    return _Order(rules=tuple(_rule(r) for r in data["rules"]), default=int(data.get("default_position", 11)),
                  front_end=tuple((e["name"], _patterns(e["words"])) for e in front["order"]),
                  existing=tuple((line["text"], line["match"]) for line in front["existing_lines"]["lines"]),
                  sub_headings={k: v for k, v in data.get("sub_headings", {}).items() if k != "about"})


def position(text: str, verb: str | None = None, slot: str = "", slot_kind: str | None = None) -> int:
    """The line's GEM position (1-20): the first rule of the asset it matches, else the default. `text` is the line
    as printed (verb included), `verb` the device's verb when the line prints it (None for a fixed wording)."""
    order = load()
    text = (text or "").strip()
    for rule in order.rules:
        if rule.matches(text, verb, slot, slot_kind):
            return rule.position
    return order.default


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


def sub_heading(shape_name: str | None) -> str:
    """The Master Template's unnumbered sub-heading over a stacked block of this shape, "" for none."""
    return load().sub_headings.get(shape_name or "", "") if shape_name else ""
