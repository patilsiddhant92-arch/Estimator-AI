"""The phrasing bank: how systems were actually written in the Learn jobs' issued proposals.

assets/phrasing_bank.json is built once by tools/build_phrasing_bank.py and committed; the tool
never reads the Learn folder at run time. Each entry is one block: its job, header, the tag
prefixes and the other words of the header, its lines (text and depth) and its notes. It holds no
tech hours and no prices.

When a system has no Master Template entry, a few blocks like it are shown to the AI as examples
of the house wording.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

ASSETS = Path(__file__).resolve().parents[3] / "assets"
BANK_FILE = ASSETS / "phrasing_bank.json"
MAX_EXAMPLES = 4
_PREFIX_WEIGHT = 10
# Words that say nothing about what a system is.
STOP_WORDS = frozenset({"qty", "and", "the", "of", "for", "to", "with", "w", "by", "a", "an", "in", "on", "at",
                        "thru", "system", "systems", "new", "typ", "typical", "all", "per"})


def stem(word: str) -> str:
    """A rough stem, so "Heaters", "Heater" and "Heating" all meet "heat"."""
    word = _singular(word)
    for ending in ("ing", "er"):
        if len(word) > len(ending) + 3 and word.endswith(ending):
            return word[: -len(ending)]
    return word


def words(text: str, stemmed: bool = False) -> set[str]:
    """The meaningful words of a kind or a header, lower case and singular (and roughly stemmed,
    "heater" to "heat", when asked)."""
    found = set()
    for word in re.findall(r"[A-Za-z]+", text or ""):
        word = word.lower()
        if word in STOP_WORDS or len(word) < 2:
            continue
        found.add(stem(word) if stemmed else _singular(word))
    return found


def _singular(word: str) -> str:
    return word[:-1] if len(word) > 3 and word.endswith("s") and not word.endswith("ss") else word


@lru_cache(maxsize=2)
def _load(path: Path) -> tuple[dict, ...]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return tuple(data["blocks"])


def load_bank(path: Path | str = BANK_FILE) -> tuple[dict, ...]:
    """Every block in the bank; empty when the file is missing."""
    try:
        return _load(Path(path).resolve())
    except (OSError, ValueError, KeyError):
        return ()


def examples_for(prefixes, kind: str, bank, k: int = MAX_EXAMPLES) -> list[dict]:
    """Up to k blocks like this system: the same tag prefix first, then the most kind words shared.

    Deterministic: ties keep the bank's order. A block that shares neither is never chosen."""
    wanted_prefixes = {p.upper() for p in prefixes or () if p}
    wanted_words = words(kind)
    scored = []
    for order, entry in enumerate(bank):
        same_prefix = len(wanted_prefixes & {p.upper() for p in entry.get("prefixes", ())})
        shared = len(wanted_words & words(" ".join(entry.get("kind_words", ()))))
        score = _PREFIX_WEIGHT * same_prefix + shared
        if score and (entry.get("lines") or entry.get("notes")):
            scored.append((-score, order, entry))
    scored.sort(key=lambda item: item[:2])
    return [entry for _, _, entry in scored[:k]]
