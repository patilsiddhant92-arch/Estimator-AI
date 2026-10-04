"""Seeded property test for the shared client-text cleanup (bms.citations): 20,000 invented texts, the render
cleanup and the intake cleanup, eight properties each. All data is invented.

The generator writes clean text (single spaces, no space before a stop, no empty bracket) and puts a cue word only
before an id, a tag or a sheet, so every property break it finds comes from the cleanup, not from the input."""
from __future__ import annotations

import random
import re
import time

import pytest

from bms import ai
from bms.citations import ONE_ID, SourceIds, clarification_text
from bms.model import Count, Family, Ref, System

SEED = 12345
N = 20_000
REFS = (Ref("S141", "q", "M-101, Invented.pdf page 2"), Ref("S998", "q", "23 09 93, Specs.pdf page 10"),
        Ref("Q2", "q", "M-001, Invented.pdf page 1"), Ref("F17", "q", "Ledger fact F17"),
        Ref("I3", "q", "I3 picture, M-201.png"), Ref("C4", "q", "equipment counts for EF"),
        Ref("S7", "q", "ledger fact"), Ref("C2", "q", "M-002, Invented.pdf page 3"))
ISSUED = tuple(r.source_id for r in REFS)
TAGS = ("EF-1", "F5-F8", "C2", "AHU-2")              # C2 is a tag and an issued id: the tag wins
UNISSUED = ("S999", "S145", "Q9", "F33", "I8", "C77", "S141A")
WORDS = ("valves", "fans", "the", "run", "on", "in", "open", "units", "two", "lab", "and", "of", "stay", "dampers",
         "controls", "by", "others", "kitchen", "serve", "outdoor", "design")
CUES = ("per", "see", "from", "ref", "cited in", "refer to")
JOINERS = (" and ", " or ", ", ", " to ", " thru ", "-", "–", "/")
STOPS = (".", ",", ";", ":")
LABELS = ("Note: ", "Assumed: ", "Confirm: ", "Note: - ", "Assumed—")
IDS = SourceIds.of(ISSUED, TAGS)
CUE_AT_END = re.compile(r"\b(?:per|see|from|ref|refer to|cited in)\s*(?:[.,;:)\]]|$)", re.IGNORECASE)


def _an_id(rng: random.Random) -> str:
    token = rng.choice(ISSUED + UNISSUED)
    token = token.lower() if rng.random() < 0.15 else token
    return token + (f" note {rng.randint(1, 3)}" if rng.random() < 0.05 else "")


def _run(rng: random.Random) -> str:
    """One id, or a run of ids and tags joined."""
    parts = [_an_id(rng)]
    for _ in range(rng.choice((0, 0, 1, 2))):
        parts += [rng.choice(JOINERS), _an_id(rng) if rng.random() < 0.7 else rng.choice(TAGS)]
    return "".join(parts)


def _unit(rng: random.Random) -> str:
    roll = rng.random()
    if roll < 0.40:
        return rng.choice(WORDS)
    if roll < 0.50:
        return rng.choice(TAGS)
    if roll < 0.58:
        return f"{rng.choice(('-20', '4', '-1', '12'))} {rng.choice(('F', 'units', 'spare'))}"
    if roll < 0.62:
        return f"sheet {rng.choice(('C101', 'S501'))}"
    if roll < 0.80:
        cue = rng.choice(CUES) + " " if rng.random() < 0.6 else ""
        return cue + _run(rng)
    # a bracket, round or square, holding a cited run, a tag or words
    inner = rng.choice((lambda: rng.choice(CUES) + " " + _run(rng), lambda: _run(rng), lambda: rng.choice(TAGS),
                        lambda: rng.choice(WORDS) + " " + _run(rng), lambda: "(" + _run(rng) + ")"))()
    bracket = ("(" + inner + ")") if rng.random() < 0.5 else ("[" + inner + "]")
    return bracket + (rng.choice(WORDS) if rng.random() < 0.1 else "")        # sometimes glued to the next word


def _text(rng: random.Random) -> str:
    out = rng.choice(LABELS) if rng.random() < 0.15 else ""
    for n in range(rng.randint(1, 8)):
        unit = _unit(rng)
        glued = unit.startswith("[") and n and rng.random() < 0.3       # a bracket glued to the word before
        out += ("" if glued or not out or out.endswith(" ") else " ") + unit
        if rng.random() < 0.2:
            out += rng.choice(STOPS)
    return out + (rng.choice((".", "")))


_RNG = random.Random(SEED)
TEXTS = [_text(_RNG) for _ in range(N)]

SKELETON = System("EF", "Exhaust Fans", "Exhaust Fan", "field", (Family("Exhaust Fan", TAGS, Count(2)),),
                  sequence_refs=REFS)


def _render(text: str) -> str:
    """What the renderer prints for a note clarification's text (before its form)."""
    return clarification_text("note", text, IDS, REFS)


def _intake(text: str) -> str:
    """What the intake keeps of a note clarification's text ("" when it drops it)."""
    answer = {"devices": [], "clarifications": [{"kind": "note", "text": text}], "no_scope_reason": None}
    ai._normalise(answer, SKELETON, set(), [], frozenset(ISSUED), TAGS)
    return answer["clarifications"][0]["text"] if answer["clarifications"] else ""


def _tag_in(tag: str, text: str) -> bool:
    return re.search(rf"(?<![\w-]){re.escape(tag)}(?![\w-])", text) is not None


def _breaks(text: str, out: str, again: str, repeat: str) -> list[str]:
    found = []
    left = [t for t in ONE_ID.findall(out) if IDS.is_id(t)]
    if left:
        found.append(f"(i) issued id left: {left}")
    lost = [t for t in TAGS if _tag_in(t, text) and not _tag_in(t, out)]
    if lost:
        found.append(f"(ii) tag lost: {lost}")
    if re.search(r"\(\s*\)|\[\s*\]", out):
        found.append("(iii) empty bracket")
    if "  " in out or re.search(r"\s[,.;:)\]]", out):
        found.append("(iv) spacing")
    if CUE_AT_END.search(out):
        found.append("(v) trailing cue word")
    if again != out:
        found.append(f"(vi) not idempotent: {again!r}")
    if repeat != out:
        found.append("(vii) not deterministic")
    return found


@pytest.mark.parametrize("name, cleanup", [("render", _render), ("intake", _intake)])
def test_the_cleanup_keeps_every_property_on_20000_seeded_texts(name, cleanup):
    start = time.perf_counter()
    failures = []
    for text in TEXTS:
        out = cleanup(text)
        problems = _breaks(text, out, cleanup(out), cleanup(text))
        if problems:
            failures.append((text, out, problems))
    took = time.perf_counter() - start
    shown = "\n".join(f"{t!r} -> {o!r}: {p}" for t, o, p in failures[:15])
    assert not failures, f"{len(failures)} of {N} texts break a property ({name}):\n{shown}"
    assert took < 10.0 * 3, took          # three cleanups per text here; (viii) is timed alone below


@pytest.mark.parametrize("name, cleanup", [("render", _render), ("intake", _intake)])
def test_the_cleanup_of_20000_seeded_texts_takes_under_10_seconds(name, cleanup):
    start = time.perf_counter()
    for text in TEXTS:
        cleanup(text)
    assert time.perf_counter() - start < 10.0
