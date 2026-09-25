"""AME's house style as data (assets/house_style.json): the verbs a scope line starts with, the
trailing forms, the integration trio and when it applies, the note rules, what may never be
written, and a short plain-English guide for the AI.

`check_line` and `check_note` say, in plain words, why something the AI wrote breaks the house
style (None when it is fine), so the judge can drop it and list it.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

ASSETS = Path(__file__).resolve().parents[3] / "assets"
STYLE_FILE = ASSETS / "house_style.json"


def _squash(text: str) -> str:
    return " ".join((text or "").split())


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
        return any(low.startswith(start.lower() + " ") for start in self.no_verb_starts)

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
        if depth < 2 and not (self.verb(text) or self.is_trio(text) or self.starts_without_verb(text)):
            return "it does not start with a house verb (" + ", ".join(self.verbs) + ")"
        return None

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


@lru_cache(maxsize=2)
def _load(path: Path) -> HouseStyle:
    raw = json.loads(path.read_text(encoding="utf-8"))
    trio = raw["integration_trio"]
    return HouseStyle(
        header=raw["header"],
        verbs=tuple(raw["verbs"]),
        no_verb_starts=tuple(raw["no_verb_starts"]["starts"]),
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
    )


def load_house_style(path: Path | str = STYLE_FILE) -> HouseStyle:
    return _load(Path(path).resolve())
