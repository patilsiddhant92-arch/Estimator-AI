"""The bid check: does the spec let AME bid this job? (design §8)

AME bids two Niagara N4 product lines, Honeywell WEBs and Johnson Controls FX. The check
finds every passage that names a controls manufacturer, quotes it word for word, and
sorts the job into Qualifies / Open / Does not qualify. The tool reports; the US team
decides. Every other controls manufacturer found is listed for them, whatever the finding.
"""
from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from estimator.catalogue.register import PageRecord
from estimator.catalogue.spec_sections import SpecSection

ASSETS = Path(__file__).resolve().parents[3] / "assets"
MANUFACTURERS = ASSETS / "reading_lists" / "manufacturers.json"
REACH = 350        # characters either side of a manufacturer's name that make up its passage


@dataclass(frozen=True)
class Named:
    name: str
    patterns: tuple[re.Pattern, ...]

    def found_in(self, text: str) -> bool:
        return any(p.search(text) for p in self.patterns)


@dataclass(frozen=True)
class ReadingList:
    ours: tuple[Named, ...]
    listed: tuple[Named, ...]
    others: tuple[Named, ...]
    controls_words: re.Pattern
    list_words: re.Pattern
    sole_words: re.Pattern

    @classmethod
    def load(cls, path: Path = MANUFACTURERS) -> "ReadingList":
        data = json.loads(Path(path).read_text(encoding="utf-8"))

        def named(key):
            return tuple(Named(e["name"], tuple(re.compile(p, 0 if e.get("exact_case") else re.I) for p in e["patterns"]))
                         for e in data[key])

        def words(key):
            return re.compile("|".join(f"(?:{w})" for w in data[key]), re.I)

        return cls(named("platforms_we_bid"), named("on_an_approved_list"), named("other_manufacturers"),
                   words("controls_words"), words("list_words"), words("sole_words"))

    def all_names(self) -> tuple[Named, ...]:
        return self.ours + self.listed + self.others


@dataclass(frozen=True)
class Mention:
    document: str
    page: int
    quote: str
    ours: tuple[str, ...]
    listed: tuple[str, ...]
    others: tuple[str, ...]
    sole: bool


@dataclass(frozen=True)
class BidCheck:
    finding: str                       # "Qualifies" | "Open" | "Does not qualify"
    reason: str                        # one plain sentence
    others: tuple[str, ...]            # every other controls manufacturer named — for the US team
    mentions: tuple[Mention, ...]
    controls_sections: tuple[str, ...]


def check_bid(pages: Sequence[PageRecord], sections: Sequence[SpecSection],
              reading: ReadingList | None = None) -> BidCheck:
    reading = reading or ReadingList.load()
    controls = [s for s in sections if s.controls]
    mentions = [m for record in pages for m in _mentions(record, controls, reading)]
    others = tuple(sorted({name for m in mentions for name in m.others}))
    section_names = tuple(dict.fromkeys(f"{s.number} {s.title}".strip() for s in controls))   # each named once
    finding, reason = _judge(mentions, others)
    if not controls:
        reason += " The specs have no controls section (23 09 xx, 159xx or Division 25) — the whole spec was searched."
    return BidCheck(finding, reason, others, tuple(mentions), section_names)


def _mentions(record: PageRecord, controls: Sequence[SpecSection], reading: ReadingList) -> list[Mention]:
    in_controls = any(s.document == record.document and s.first_page <= record.page <= s.last_page for s in controls)
    text = record.text
    windows = []
    for named in reading.all_names():
        for pattern in named.patterns:
            for match in pattern.finditer(text):
                start = text.rfind("\n", 0, max(0, match.start() - REACH)) + 1
                end = text.find("\n", min(len(text), match.end() + REACH))
                windows.append((start, len(text) if end == -1 else end))
    merged: list[list[int]] = []
    for start, end in sorted(windows):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    found = []
    for start, end in merged:
        passage = text[start:end]
        if not (in_controls or reading.controls_words.search(passage)):
            continue
        ours = tuple(n.name for n in reading.ours if n.found_in(passage))
        listed = tuple(n.name for n in reading.listed if n.found_in(passage)) if reading.list_words.search(passage) else ()
        others = tuple(n.name for n in reading.others if n.found_in(passage))
        if ours or listed or others:
            found.append(Mention(record.document, record.page, " ".join(passage.split()),
                                 ours, listed, others, bool(reading.sole_words.search(passage))))
    return found


def _where(mention: Mention) -> str:
    return f"{mention.document.rsplit('/', 1)[-1]}, page {mention.page}"


def _judge(mentions: Sequence[Mention], others: tuple[str, ...]) -> tuple[str, str]:
    qualifying = [m for m in mentions if m.ours or m.listed]
    blocking = [m for m in mentions if m.sole and m.others and not m.ours]
    if qualifying and blocking:
        return ("Open", f"The spec says two different things: it names {', '.join(qualifying[0].ours or qualifying[0].listed)} "
                        f"({_where(qualifying[0])}) but also requires {', '.join(blocking[0].others)} with no substitutions "
                        f"({_where(blocking[0])}). The US team decides.")
    if qualifying:
        first = next((m for m in qualifying if m.ours), qualifying[0])
        if first.ours:
            return "Qualifies", f"The spec names {', '.join(first.ours)} ({_where(first)})."
        verb = "is" if len(first.listed) == 1 else "are"
        return "Qualifies", f"{' and '.join(first.listed)} {verb} on the spec's list of acceptable manufacturers ({_where(first)})."
    if blocking:
        return ("Does not qualify", f"The spec requires {', '.join(blocking[0].others)} with no substitutions "
                                    f"({_where(blocking[0])}). The US team decides.")
    if others:
        return "Open", f"The spec names {', '.join(others)}, and none of the lines AME bids ({_where(mentions[0])}). The US team decides."
    return "Open", "The spec names no controls manufacturer at all. The US team decides."
