"""Keynotes and general notes that add controls scope, read from drawing sheets.

Only the sheets an estimator would flip through for scope carry keyed or general notes
that matter here (design's "read the job the way the estimator does") — a numbered list
inside a spec section is a different animal (paragraphs, not keyed callouts) and isn't
read by this module. The block headings and the words that make a note controls-relevant
live in assets/reading_lists/keynotes.json, never in code.

Placements of the keynote numbers on the plans are never counted: the research behind this
build step found the numbers aren't enclosed in a shape on these jobs, so bare digits are
everywhere (dimensions, grid bubbles) and a placement count would be noise, not scope.

A note ends where the next one starts, and also at a blank line, at a heading, or where the
text runs into the title block (the page's `edge_spans`, the right and bottom fifth of the
sheet) — a note is quoted, so it must not carry the rest of the sheet with it. A note longer
than MAX_CHARS is cut there and ends " …".
"""
from __future__ import annotations

import json
import re
from collections.abc import Collection
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from estimator.catalogue.pdf import clean_text

ASSETS = Path(__file__).resolve().parents[3] / "assets"
KEYNOTES = ASSETS / "reading_lists" / "keynotes.json"

MAX_ITEMS = 60      # a block is cut off after this many items — see the plan's "Behaviour"
MAX_CHARS = 600     # a note longer than this is cut, and ends " …"
MIN_TITLE_BLOCK_LINE = 8   # characters: a shorter line is only taken for title-block text when it is a whole run
_ITEM = re.compile(r"^[ \t]*(\d{1,2}|[A-Z])[.)][ \t]+", re.M)
_HEADING_LINE = re.compile(r"^[A-Z][A-Z0-9 &/,'\-]{2,40}:$")   # a short line in capitals ending in a colon


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


@dataclass(frozen=True)
class _TitleBlock:
    """The page's title-block text, to tell when a note has run into it."""
    runs: frozenset[str]
    joined: str

    @classmethod
    def of(cls, record) -> "_TitleBlock":
        runs = [" ".join(clean_text(s.text).split()) for s in getattr(record, "edge_spans", ()) or ()]
        runs = [r for r in runs if r]
        return cls(frozenset(runs), " ".join(runs))

    def holds(self, line: str) -> bool:
        return bool(line) and (line in self.runs or (len(line) >= MIN_TITLE_BLOCK_LINE and line in self.joined))


_NO_TITLE_BLOCK = _TitleBlock(frozenset(), "")


def _note_body(body: str, rules: _Rules, title_block: _TitleBlock) -> str:
    """One item's text, up to a blank line, a heading or the title block, whitespace squashed."""
    lines = body.split("\n")
    while len(lines) > 1 and not lines[0].strip():
        lines.pop(0)            # the number stood alone on its line: the note starts on the next
    first, *rest = lines
    in_strip = title_block.holds(" ".join(first.split()))    # a notes block set in the strip itself
    kept = [first]
    for line in rest:
        squashed = " ".join(line.split())
        if not squashed:
            break
        if _HEADING_LINE.match(squashed) or rules.heading.match(squashed):
            break
        if not in_strip and title_block.holds(squashed):
            break
        kept.append(line)
    text = " ".join(" ".join(kept).split())
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS].rstrip() + " …"
    return text


def _items(block_text: str, rules: _Rules | None = None,
           title_block: _TitleBlock = _NO_TITLE_BLOCK) -> list[tuple[str, str]]:
    """(number, note text) pairs cut from one block's text, at most MAX_ITEMS. A leading
    newline is added so the first item is found even when it follows the heading on the
    same line — the split still behaves as "start of an item's line" for it."""
    rules = rules or _load(str(KEYNOTES))
    padded = "\n" + block_text
    matches = list(_ITEM.finditer(padded))[:MAX_ITEMS + 1]   # the one past the last ends the last
    items = []
    for index, match in enumerate(matches[:MAX_ITEMS]):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(padded)
        note_text = _note_body(padded[start:end], rules, title_block)
        if note_text:
            items.append((match.group(1), note_text))
    return items


def read_notes(catalogue, pages: Collection[tuple[str, int]] | None = None) -> list[Note]:
    """Every keyed and general note on the drawing sheets; with `pages`, on those pages only (the governing ones)."""
    rules = _load(str(KEYNOTES))
    by_sheet = {(sheet.document, sheet.page): sheet for sheet in catalogue.sheets}
    notes: list[Note] = []
    for record in catalogue.pages:
        sheet = by_sheet.get((record.document, record.page))
        if sheet is None:            # drawing sheets only — a spec page's notes aren't read here
            continue
        if pages is not None and (record.document, record.page) not in pages:
            continue
        text = clean_text(record.text)
        title_block = _TitleBlock.of(record)
        headings = list(rules.heading.finditer(text))
        for index, heading in enumerate(headings):
            block_name = _canonical(rules.blocks, heading.group(1))
            start = heading.end()
            end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
            for number, note_text in _items(text[start:end], rules, title_block):
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
