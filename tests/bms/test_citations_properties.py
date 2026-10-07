"""Seeded property test of the source-id DETECTOR (bms.citations): 20,000 invented texts, random.Random(12345).
All data is invented.

The policy is detect and refuse, never rewrite. For every text exactly one of:
 (i)  no issued id (after normalisation) is in it, and it is accepted BYTE-IDENTICAL to the text with its label
      stripped; or
 (ii) it is refused, with a reason naming a token that is in the text.
Never anything in between. Also: idempotent, deterministic, fast; the renderer's safety net leaves no issued id.
A text is refused only when it holds an issued id. Under the lead's ruling on L-D (lead/final-c) a sheet word
changes nothing for an issued id ("sheet S141" is issued; these texts have no known sheets, K); it used to make one
a sheet number (the estimator's ruling of 2026-10-05).

The oracle below is written apart from citations.py (its own normalisation, token pattern and tag tokens)."""
from __future__ import annotations

import random
import re
import unicodedata

import pytest

from timing import grows_linearly
from bms import citations

SEED = 12345
N = 20_000
ISSUED = ("S141", "S998", "Q2", "F17", "I3", "C4", "S7", "C2", "F6")    # C2 and F6 are also tags: the tag wins
TAGS = ("EF-1", "F5-F8", "C2", "AHU-2")
TAG_TOKENS = frozenset({"F5", "F6", "F7", "F8", "C2"})                  # what the tags protect, by hand
UNISSUED = ("S999", "S145", "Q9", "F33", "I8", "C77", "S141A", "F12", "F1")
WORDS = ("valves", "fans", "the", "run", "on", "in", "open", "units", "two", "lab", "and", "of", "stay", "dampers",
         "controls", "by", "others", "kitchen", "serve", "outdoor", "design", "pumps")
CUES = ("per", "see", "from", "ref", "cited in", "refer to", "Per", "SEE")
JOINERS = (" and ", " or ", ", ", " to ", " thru ", "-", "–", "/", " through ")
SHEETS = ("sheet C101", "sheets C101 and C102", "dwg S501", "sheet M-101", "Sheet F101", "M-101.00")
STOPS = (".", ",", ";", ":", "!", "?")
LABELS = ("Note: ", "Assumed: ", "Confirm: ", "**Confirm**: ", "Assumed—", "Confirm ", "* ", "Assumption: ")
KINDS = ("note", "confirm", "assumed")
BRACKETS = ("()", "[]", "{}")
ZERO_WIDTH = "​‌‍⁠﻿­"
TOKEN = re.compile(r"(?<![0-9A-Za-z])[SQIFCsqifc][0-9]{1,4}[A-Za-z]?(?![0-9A-Za-z])")


def _full_width(token: str) -> str:
    return "".join(chr(ord(c) + 0xFEE0) if "!" <= c <= "~" else c for c in token)


def _an_id(rng: random.Random) -> str:
    token = rng.choice(ISSUED + UNISSUED)
    roll = rng.random()
    if roll < 0.12:
        token = token.lower()
    elif roll < 0.18:
        token = token[0] + rng.choice(ZERO_WIDTH) + token[1:]
    elif roll < 0.23:
        token = _full_width(token)
    return token


def _run(rng: random.Random) -> str:
    parts = [_an_id(rng)]
    for _ in range(rng.choice((0, 0, 1, 2))):
        parts += [rng.choice(JOINERS), _an_id(rng) if rng.random() < 0.7 else rng.choice(TAGS)]
    return "".join(parts)


def _unit(rng: random.Random) -> str:
    roll = rng.random()
    if roll < 0.38:
        return rng.choice(WORDS)
    if roll < 0.48:
        return rng.choice(TAGS)
    if roll < 0.54:
        return f"{rng.choice(('-20', '4', '-1', '12'))} {rng.choice(('F', 'units', 'spare'))}"
    if roll < 0.60:
        return rng.choice(SHEETS) if rng.random() < 0.7 else rng.choice(("sheet ", "sheets ", "dwg ")) + _an_id(rng)
    if roll < 0.80:
        return (rng.choice(CUES) + " " if rng.random() < 0.6 else "") + _run(rng)
    inner = rng.choice((lambda: rng.choice(CUES) + " " + _run(rng), lambda: _run(rng), lambda: rng.choice(TAGS),
                        lambda: rng.choice(WORDS) + " " + _run(rng), lambda: rng.choice(WORDS),
                        lambda: "(" + _run(rng) + ")", lambda: rng.choice(SHEETS)))()
    pair = rng.choice(BRACKETS)
    return pair[0] + inner + pair[1] + (rng.choice(WORDS) if rng.random() < 0.1 else "")


def _text(rng: random.Random) -> str:
    out = rng.choice(LABELS) if rng.random() < 0.2 else ""
    for n in range(rng.randint(1, 8)):
        unit = _unit(rng)
        glued = unit[:1] in "([{" and n and rng.random() < 0.3
        out += ("" if glued or not out or out.endswith(" ") else " ") + unit
        if rng.random() < 0.2:
            out += rng.choice(STOPS)
    return out + rng.choice((".", "", "!"))


_RNG = random.Random(SEED)
CASES = [(_RNG.choice(KINDS), _text(_RNG)) for _ in range(N)]


def _normal(text: str) -> str:
    """The oracle's own detection copy: NFKC, zero-width characters out."""
    return unicodedata.normalize("NFKC", "".join(c for c in text if c not in ZERO_WIDTH))




def _tokens(text: str) -> list[tuple[str, bool]]:
    """The oracle's tokens of `text`, each with whether it is an issued id (not a tag; a sheet word before it
    changes nothing, L-D)."""
    return [(t, t.upper() not in TAG_TOKENS and t.upper() in ISSUED) for t in TOKEN.findall(_normal(text))]


def _issued_in(text: str) -> list[str]:
    return [t for t, issued in _tokens(text) if issued]


def _named(reason: str) -> list[str]:
    found = re.search(r"source ids? (.+?): name the document", reason)
    return found.group(1).split(", ") if found else []


def _intake(ids, kind: str, text: str) -> tuple[str, str]:
    """What the intake does with one clarification text: (the text it would store, the reason it refuses)."""
    stored = citations.label_off(kind, text)
    return stored, ids.refusal(stored)


def _ids():
    return citations.SourceIds.of(ISSUED, TAGS)


def test_the_generator_covers_every_piece():
    texts = "".join(t for _, t in CASES)
    for piece in ("S141A", "s141", "​", "Ｓ", "[", "{", "(", "refer to", "sheets C101", "–", "**Confirm**"):
        assert piece in texts, piece
    refused = sum(1 for k, t in CASES if _intake(_ids(), k, t)[1])
    assert N // 5 < refused < N * 4 // 5, refused       # both outcomes are well represented


def test_every_text_is_either_accepted_unchanged_or_refused_naming_a_token():
    ids = _ids()
    failures = []
    for kind, text in CASES:
        stored, reason = _intake(ids, kind, text)
        label_off = citations.strip_label(kind, text)
        normal = _normal(stored)
        problems = []
        if reason:
            named = _named(reason)
            if not named or not all(re.search(rf"(?<![0-9A-Za-z]){re.escape(t)}(?![0-9A-Za-z])", normal)
                                    for t in named):
                problems.append(f"(ii) the reason names no token of the text: {reason!r}")
            if any(t.upper() in TAG_TOKENS for t in named):
                problems.append(f"(ii) a tag is named: {named}")
        else:
            if _issued_in(stored):
                problems.append(f"(i) accepted with an issued id: {_issued_in(stored)}")
            if stored != label_off:
                problems.append(f"(i) not byte-identical: {stored!r} != {label_off!r}")
        if _issued_in(stored) and not reason:
            problems.append("an issued id and no refusal")
        if reason and not _issued_in(stored):
            problems.append(f"refused with no issued id (a bracket or a cue word alone never refuses): {reason!r}")
        again = _intake(ids, kind, text)
        if again != (stored, reason):
            problems.append("not deterministic")
        if not reason and _intake(ids, kind, stored) != (stored, ""):
            problems.append(f"not idempotent: {_intake(ids, kind, stored)!r}")
        if problems:
            failures.append((kind, text, stored, problems))
    shown = "\n".join(f"{k} {t!a} -> {s!a}: {p}" for k, t, s, p in failures[:15])
    assert not failures, f"{len(failures)} of {N} texts break the policy:\n{shown}"


def test_the_detector_is_deterministic_across_fresh_instances():
    first = [_intake(_ids(), k, t) for k, t in CASES[:2000]]
    second = [_intake(citations.SourceIds.of(reversed(ISSUED), reversed(TAGS)), k, t) for k, t in CASES[:2000]]
    assert first == second


def test_the_safety_net_leaves_no_issued_id_and_takes_out_nothing_else():
    ids = _ids()
    failures = []
    for _, text in CASES:
        out = ids.without_issued(text)
        if _issued_in(out):
            failures.append((text, out, "issued id left"))
        elif not _issued_in(text) and out != text:
            failures.append((text, out, "changed a text with no issued id"))
        elif ids.without_issued(out) != out:
            failures.append((text, out, "not idempotent"))
        elif [t.upper() for t in TOKEN.findall(_normal(out))] != [t.upper() for t, issued in _tokens(text) if not issued]:
            failures.append((text, out, "a token other than an issued id was taken out"))
    shown = "\n".join(f"{t!a} -> {o!a}: {p}" for t, o, p in failures[:15])
    assert not failures, f"{len(failures)} of {N}:\n{shown}"


@pytest.mark.slow
def test_checking_texts_grows_linearly_with_the_number_of_texts():
    """No wall-clock limit (it flaked under load): 4 times the texts take well under 8 times as long."""
    ids = _ids()

    def check(n):
        for i in range(n):
            _intake(ids, *CASES[i % N])
    assert grows_linearly(check, 500)


@pytest.mark.slow
def test_runtime_grows_linearly_with_the_length_of_one_text():
    ids = _ids()

    def scan(n):
        text = " ".join(CASES[i % N][1] for i in range(n))
        ids.refusal(text)
        ids.without_issued(text)
    assert grows_linearly(scan, 1_000)
