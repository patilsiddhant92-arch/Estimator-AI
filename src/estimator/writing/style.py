"""AME's house style as data (assets/house_style.json): the verbs a scope line starts with, the
trailing forms, the integration trio and when it applies, the note rules, what may never be
written, and a short plain-English guide for the AI.

`check_line` and `check_note` say, in plain words, why something the AI wrote breaks the house
style (None when it is fine), so the judge can drop it and list it.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

ASSETS = Path(__file__).resolve().parents[3] / "assets"
STYLE_FILE = ASSETS / "house_style.json"
TEMPLATES_FILE = ASSETS / "system_templates.json"
_TRIO_LEAD = "furnish bms communication wiring to "
_TOP = "  top level  "           # the key under which the template forms keep the lines written at the top level


def _squash(text: str) -> str:
    return " ".join((text or "").split())


def _key(text: str) -> str:
    """A line as the Master Template's lines are looked up: spaces squashed, case and a trailing stop ignored."""
    return _squash(text).casefold().rstrip(".-– ")


@dataclass(frozen=True)
class HouseStyle:
    header: str
    verbs: tuple[str, ...]
    no_verb_starts: tuple[str, ...]
    trailing_forms: tuple[str, ...]
    trio: tuple[str, str, str]
    trio_depths: tuple[int, ...]
    trio_applies_when: tuple[str, ...]
    trio_rule: str
    note_start: str
    note_rule: str
    note_examples: tuple[str, ...]
    forbidden_words: tuple[str, ...]
    category_words: tuple[str, ...]
    forbidden_patterns: tuple[str, ...]
    max_line_length: int
    guide: tuple[str, ...]
    also_accepted: tuple = ()            # openings without a verb the check accepts, beyond what the AI is told
    template_forms: dict = field(default=None, hash=False, compare=False)   # the Master Template's own lines, by _key: the form it writes them in
    long_note: int = 90                  # a "comes with the unit" note longer than this takes the short house form
    by_unit_mfr: str = "*{item} BY UNIT MFR."
    by_unit_mfr_patterns: tuple = ()
    duplicate_share: float = 0.7
    boilerplate_words: frozenset = frozenset()
    line_order: tuple = ()               # the groups, in the house order
    order_checks: tuple = ()             # (group, "text" | "device", compiled patterns), in the order they are tried
    device_ends: str = r"\s*\("
    software_points: tuple = ()
    same_opening: dict = field(default=None, hash=False, compare=False)   # opening -> its family's first

    @property
    def openings(self) -> tuple[str, ...]:
        """Every opening a line may have without a verb."""
        return self.no_verb_starts + self.also_accepted

    # -- the Master Template's own lines
    def template_form(self, text: str) -> str:
        """The line in the form the Master Template writes it (its capitals), when it is one of its lines,
        or the first integration line naming any equipment; else the line as given."""
        forms = self.template_forms or {}
        key = _key(text)
        if key in forms:
            return forms[key]
        squashed = _squash(text)
        low = squashed.casefold()
        if low.startswith(_TRIO_LEAD) and low.endswith("factory controls"):
            middle = squashed[len(_TRIO_LEAD):len(squashed) - len("factory controls")].strip()
            return _squash(self.trio[0].replace("{what}", middle))
        return text

    def is_template_line(self, text: str) -> bool:
        """The line is one the Master Template writes at the top level (under the header), word for word."""
        return _key(text) in (self.template_forms or {}).get(_TOP, ())

    # -- the house order of a system's lines
    def _device(self, text: str) -> str:
        """The device a line names: after its verb or its opening, before "for", "to", a bracket or a dash."""
        text = _squash(text)
        verb = self.verb(text)
        if verb:
            text = text[len(verb):]
        else:
            low = text.lower()
            start = next((s for s in sorted(self.openings, key=len, reverse=True)
                          if low.startswith(s.lower() + " ")), "")
            text = text[len(start):]
        return re.split(self.device_ends, text.strip(), maxsplit=1, flags=re.I)[0]

    def line_group(self, text: str) -> str | None:
        """The house-order group of a scope line (controller, sensors, points, valves and dampers,
        integration), or None when no group's words are in it."""
        device = None
        wiring = self.verb(text) is None      # an interlock, a tie-in, low-voltage wiring: only integration moves it
        for group, where, patterns in self.order_checks:
            if wiring and group != "integration":
                continue
            if where == "device":
                device = self._device(text) if device is None else device
                if any(p.search(device) for p in patterns):
                    return group
            elif any(p.search(_squash(text)) for p in patterns) or (group == "integration" and self.is_trio(text)):
                return group
        return None

    def line_rank(self, text: str) -> int | None:
        group = self.line_group(text)
        return None if group is None else self.line_order.index(group)

    def is_software_point(self, text: str) -> bool:
        return any(p.search(text or "") for p in self.software_points)

    # -- checking what the AI wrote
    def verb(self, text: str) -> str | None:
        """The house verb the line starts with, as written, or None."""
        low = _squash(text).lower()
        for verb in sorted(self.verbs, key=len, reverse=True):
            if low.startswith(verb.lower() + " "):
                return text.strip()[: len(verb)]
        return None

    def is_trio(self, text: str) -> bool:
        low = _squash(text).lower().rstrip(".")
        lead = self.trio[0].split("{what}")[0].strip().lower()
        return ((low.startswith(lead + " ") and low.endswith("controls"))
                or low in (self.trio[1].lower(), self.trio[2].lower()))

    def starts_without_verb(self, text: str) -> bool:
        low = _squash(text).lower()
        return any(low.startswith(start.lower() + " ") for start in self.openings)

    def forbidden(self, text: str) -> str | None:
        """What in the text the client must never see, or None."""
        low = text.lower()
        for word in self.forbidden_words:
            if word.lower() in low:
                return f"it names “{word}”"
        for word in self.category_words:
            if re.search(rf"\b{re.escape(word)}\b", text):
                return f"it names the category word {word}"
        for pattern in self.forbidden_patterns:
            if re.search(pattern, text, re.I):
                return "it names tech hours"
        return None

    def check_line(self, text: str, depth: int = 1) -> str | None:
        """Why the scope line breaks the house style, or None when it is fine. A line under
        another line (depth 2 or more) may be a plain noun phrase — the Master Template writes
        "Damper Actuator" under its parent line — so only a top-level line needs a house verb."""
        text = _squash(text)
        if not text:
            return "it is empty"
        if len(text) > self.max_line_length:
            return f"it is longer than {self.max_line_length} characters"
        bad = self.forbidden(text)
        if bad:
            return bad
        if depth < 2 and not (self.verb(text) or self.is_trio(text) or self.starts_without_verb(text)
                              or self.is_template_line(text)):
            return "it does not start with a house verb (" + ", ".join(self.verbs) + ")"
        return None

    def by_unit_mfr_item(self, note: str) -> str | None:
        """The item a note gives to the unit (“… are coming with the unit per equipment schedule”, “… furnished
        by the fan manufacturer”), or None when it says no such thing."""
        text = _squash(note).lstrip("*").strip()
        for pattern in self.by_unit_mfr_patterns:
            m = re.search(pattern, text, re.I)
            if m and m.start() > 0:
                item = text[:m.start()].strip(" ,.-–")
                if item.count("(") != item.count(")") or re.search(r"\b(?:is|are|shall|will|be|by)\b", item, re.I):
                    return None                  # a clause ("heaters are controlled by …"), not an item
                return item or None
        return None

    def short_note(self, note: str) -> str | None:
        """The house form "*<ITEM> BY UNIT MFR." of a long note giving a device to the unit, else None."""
        item = self.by_unit_mfr_item(note)
        return self.by_unit_mfr.format(item=item.upper()) if item else None

    def note_words(self, note: str) -> frozenset[str]:
        """A note's words, for finding a duplicate: the boilerplate ("coming with the unit per equipment
        schedule") left out, plurals as singulars."""
        words = re.findall(r"[a-z0-9]+", _squash(note).casefold())
        return frozenset(w[:-1] if len(w) > 3 and w.endswith("s") else w for w in words
                         if w not in self.boilerplate_words)

    def same_note(self, a: str, b: str) -> bool:
        """Two notes that say the same thing: most of the shorter one's words are in the other."""
        wa, wb = self.note_words(a), self.note_words(b)
        if not wa or not wb:
            return _key(a) == _key(b)
        return len(wa & wb) / min(len(wa), len(wb)) >= self.duplicate_share

    def check_note(self, text: str) -> str | None:
        text = _squash(text)
        if not text.startswith(self.note_start) or not text.lstrip("*").strip():
            return f"a note must start with “{self.note_start}”"
        if len(text) > self.max_line_length:
            return f"it is longer than {self.max_line_length} characters"
        return self.forbidden(text)

    # -- for the AI's prompt
    def prompt_text(self) -> str:
        trio = "\n".join(f"  {'  ' * (d - 1)}{line}" for line, d in zip(self.trio, self.trio_depths))
        parts = ["How AME writes a system (the house style):",
                 *[f"- {line}" for line in self.guide],
                 f"- The header is \"{self.header}\"; the writer fills in the count and the tags.",
                 "- A line starts with one of these verbs: " + "; ".join(self.verbs) + ".",
                 "- Without a verb, only an interlock, a tie-in or low-voltage wiring line, starting: "
                 + "; ".join(self.no_verb_starts) + ".",
                 "- A line may end with one of these forms: " + "; ".join(self.trailing_forms) + ".",
                 "- The integration trio, when " + "; or ".join(self.trio_applies_when) + ":",
                 trio,
                 f"  {self.trio_rule}",
                 f"- Notes: {self.note_rule}",
                 f"- A line is at most {self.max_line_length} characters.",
                 "- Never write prices, tech hours, confidence, category words ("
                 + ", ".join(self.category_words) + ") or \"rule:\"."]
        return "\n".join(parts)


def _template_forms(trio: tuple[str, ...]) -> dict[str, str]:
    """The Master Template's lines (assets/system_templates.json), by _key, in its own form. The integration
    trio's form comes first: it is how the template writes those lines everywhere."""
    forms: dict = {_key(line): line for line in trio if "{" not in line}
    top = set()
    try:
        raw = json.loads(TEMPLATES_FILE.read_text(encoding="utf-8"))
    except OSError:
        raw = {}
    for system in raw.get("systems", ()):
        for line in system.get("lines", ()):
            text = _squash(line.get("text", ""))
            if text and "{" not in text:
                forms.setdefault(_key(text), text)
                if int(line.get("depth", 1)) < 2:
                    top.add(_key(text))
    forms[_TOP] = frozenset(top)
    return forms


def _order(raw: dict) -> tuple[tuple, tuple]:
    order = raw.get("line_order") or {}
    groups = order.get("groups", {})
    checks = []
    for name in order.get("checked_in_this_order", ()):
        for where, patterns in groups.get(name, {}).items():
            checks.append((name, where, tuple(re.compile(p, re.I) for p in patterns)))
    return tuple(order.get("order", ())), tuple(checks)


@lru_cache(maxsize=2)
def _load(path: Path) -> HouseStyle:
    raw = json.loads(path.read_text(encoding="utf-8"))
    trio = raw["integration_trio"]
    notes = raw["notes"]
    line_order, order_checks = _order(raw)
    return HouseStyle(
        header=raw["header"],
        verbs=tuple(raw["verbs"]),
        no_verb_starts=tuple(raw["no_verb_starts"]["starts"]),
        also_accepted=tuple(raw["no_verb_starts"].get("also_accepted", ())),
        trailing_forms=tuple(raw["trailing_forms"]),
        trio=tuple(trio["lines"]),
        trio_depths=tuple(trio["depths"]),
        trio_applies_when=tuple(trio["applies_when"]),
        trio_rule=trio["rule"],
        note_start=raw["notes"]["start"],
        note_rule=raw["notes"]["rule"],
        note_examples=tuple(raw["notes"]["examples"]),
        forbidden_words=tuple(raw["forbidden"]["words"]),
        category_words=tuple(raw["forbidden"]["category_words"]),
        forbidden_patterns=tuple(raw["forbidden"]["patterns"]),
        max_line_length=int(raw["max_line_length"]),
        guide=tuple(raw["guide"]),
        template_forms=_template_forms(tuple(trio["lines"])),
        long_note=int(notes.get("long", 90)),
        by_unit_mfr=notes.get("by_unit_mfr", "*{item} BY UNIT MFR."),
        by_unit_mfr_patterns=tuple(notes.get("by_unit_mfr_patterns", ())),
        duplicate_share=float(notes.get("duplicate_share", 0.7)),
        boilerplate_words=frozenset(notes.get("boilerplate_words", ())),
        line_order=line_order,
        order_checks=order_checks,
        device_ends=(raw.get("line_order") or {}).get("device_ends", r"\s*\("),
        software_points=tuple(re.compile(p, re.I) for p in (raw.get("software_points") or {}).get("patterns", ())),
        same_opening={o.lower(): family[0].lower() for family in (raw.get("same_opening") or {}).get("families", ())
                      for o in family},
    )


def load_house_style(path: Path | str = STYLE_FILE) -> HouseStyle:
    return _load(Path(path).resolve())
