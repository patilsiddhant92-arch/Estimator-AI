"""Keynotes and general notes that add controls scope, read from drawing sheets.

Only the sheets an estimator would flip through for scope carry keyed or general notes
that matter here (design's "read the job the way the estimator does") — a numbered list
inside a spec section is a different animal (paragraphs, not keyed callouts) and isn't
read by this module. The block headings and the words that make a note controls-relevant
live in assets/reading_lists/keynotes.json, never in code.

Placements of the keynote numbers on the plans are never counted: the research behind this
build step found the numbers aren't enclosed in a shape on these jobs, so bare digits are
everywhere (dimensions, grid bubbles) and a placement count would be noise, not scope.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from estimator.catalogue.pdf import clean_text

ASSETS = Path(__file__).resolve().parents[3] / "assets"
KEYNOTES = ASSETS / "reading_lists" / "keynotes.json"

MAX_ITEMS = 60      # a block is cut off after this many items — see the plan's "Behaviour"
_ITEM = re.compile(r"^[ \t]*(\d{1,2}|[A-Z])[.)][ \t]+", re.M)


@dataclass(frozen=True)
class Note:
    sheet: str | None
    document: str
    page: int
    block: str          # "KEY NOTES" | "GENERAL NOTES" | "CONTROLS NOTES" | ...
    number: str          # "7" or "A"
    text: str            # the note, whitespace squashed
    controls: bool       # it names controls scope
    who: str             # "by others" / "by the electrical contractor" / ... / "" — the first such phrase


@dataclass(frozen=True)
class _Rules:
    blocks: tuple[str, ...]
    heading: re.Pattern
    controls_words: tuple[re.Pattern, ...]
    who_phrases: tuple[tuple[re.Pattern, str], ...]


def _word_pattern(word: str) -> re.Pattern:
    """A controls word, matched whole, tolerating a plural on a single word. A phrase of
    several words ("temperature control", "by others") is matched literally instead."""
    parts = word.split()
    if len(parts) > 1:
        body = r"\s+".join(re.escape(p) for p in parts)
        return re.compile(rf"\b{body}\b", re.I)
    return re.compile(rf"\b{re.escape(word)}s?\b", re.I)


def _phrase_pattern(phrase: str) -> re.Pattern:
    body = r"\s+".join(re.escape(p) for p in phrase.split())
    return re.compile(rf"\b{body}\b", re.I)


@lru_cache
def _load(path: str) -> _Rules:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    blocks = tuple(data["blocks"])
    heading = re.compile(r"^[ \t]*(" + "|".join(re.escape(b) for b in blocks) + r")[ \t]*:?", re.M | re.I)
    controls_words = tuple(_word_pattern(w) for w in data["controls_words"])
    who_phrases = tuple((_phrase_pattern(p), p) for p in data["who_phrases"])
    return _Rules(blocks, heading, controls_words, who_phrases)


def _canonical(blocks: tuple[str, ...], matched: str) -> str:
    upper = matched.strip().upper()
    for name in blocks:
        if name == upper:
            return name
    return upper


def _who(text: str, who_phrases: tuple[tuple[re.Pattern, str], ...]) -> str:
    hits = sorted((m.start(), phrase) for pattern, phrase in who_phrases for m in pattern.finditer(text))
    return hits[0][1] if hits else ""


def _is_controls(text: str, controls_words: tuple[re.Pattern, ...]) -> bool:
    return any(pattern.search(text) for pattern in controls_words)


def _items(block_text: str) -> list[tuple[str, str]]:
    """(number, note text) pairs cut from one block's text, at most MAX_ITEMS. A leading
    newline is added so the first item is found even when it follows the heading on the
    same line — the split still behaves as "start of an item's line" for it."""
    padded = "\n" + block_text
    matches = list(_ITEM.finditer(padded))[:MAX_ITEMS]
    items = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(padded)
        note_text = " ".join(padded[start:end].split())
        if note_text:
            items.append((match.group(1), note_text))
    return items


def read_notes(catalogue) -> list[Note]:
    rules = _load(str(KEYNOTES))
    by_sheet = {(sheet.document, sheet.page): sheet for sheet in catalogue.sheets}
    notes: list[Note] = []
    for record in catalogue.pages:
        sheet = by_sheet.get((record.document, record.page))
        if sheet is None:            # drawing sheets only — a spec page's notes aren't read here
            continue
        text = clean_text(record.text)
        headings = list(rules.heading.finditer(text))
        for index, heading in enumerate(headings):
            block_name = _canonical(rules.blocks, heading.group(1))
            start = heading.end()
            end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
            for number, note_text in _items(text[start:end]):
                notes.append(Note(
                    sheet=sheet.number,
                    document=record.document,
                    page=record.page,
                    block=block_name,
                    number=number,
                    text=note_text,
                    controls=_is_controls(note_text, rules.controls_words),
                    who=_who(note_text, rules.who_phrases),
                ))
    return notes
