"""The planner's reading of the ledger (workstream 2, private): refs, counts, tags, names, sequence matches and the
notes that name a system. Pure functions over the old app's Ledger and Dossier; no AI."""
from __future__ import annotations

import re
from dataclasses import dataclass

from estimator.ledger.facts import ADDED, Fact, Ledger, where_short

from bms.model import Count, OtherCount, Ref

_SPACES = re.compile(r"\s+")


def squash(text) -> str:
    return _SPACES.sub(" ", str(text or "")).strip()


def naming(name: str) -> re.Pattern:
    """The name as a whole word, any case: "CH" finds "CH" and "CH-1" but not "CHWP", "CHILLED" or "EACH"."""
    return re.compile(rf"(?<![A-Za-z0-9]){re.escape(name)}(?![A-Za-z0-9])", re.I)


def names_in(names, text: str) -> bool:
    text = squash(text)
    return any(naming(n).search(text) for n in names if n)


def number(value) -> int | None:
    """A count's value as a whole number (" 14" is 14); None when it is not one."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    text = str(value if value is not None else "").strip()
    return int(text) if text.isdigit() else None


def expand(tags) -> list[str]:
    from estimator.writing.assemble import expand_tags
    return expand_tags(tags)


def tag_words(tags) -> str:
    from estimator.writing.write import tag_list
    return tag_list(list(tags))


# ---- short names --------------------------------------------------------------------------------------------

_PLAN_ONLY_LEAD = re.compile(r"^seen on [^:,]*?,?\s*not scheduled\s*(?::|[-–—])\s*", re.I)
_PLAN_ONLY_WORDS = 8


def short_name(value, fallback: str = "") -> str:
    """A family's name. A plan-only value ("seen on plans, not scheduled: <description> (<reasoning>)") gives the
    description alone: no lead, no parenthetical (nested ones go whole), at most 8 words cut at a word; when
    nothing is left outside the brackets, what is inside the first one. Any other value is kept, squashed. Never
    empty: the fallback (the prefix) when the value is empty."""
    text = squash(value)
    lead = _PLAN_ONLY_LEAD.match(text)
    if not lead:
        return text or fallback
    description = text[lead.end():]
    rest, previous = description, None
    while previous != rest:
        previous, rest = rest, re.sub(r"\([^()]*\)", "", rest)
    rest = squash(re.sub(r"[()]", "", rest))
    if not rest:
        inner = re.search(r"\(([^()]*)\)", description)
        rest = squash(inner.group(1)) if inner else ""
    return " ".join(rest.split()[:_PLAN_ONLY_WORDS]) or text or fallback


# ---- the reader ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class FamilyFacts:
    """One family of the ledger as the planner reads it."""
    fact: Fact
    prefix: str
    name: str                   # the short name
    tags: tuple[str, ...]       # its own tags, expanded; () when the ledger lists none
    count: Count
    plan_only: bool             # seen on the drawings, on no schedule: its existence is a question
    sequence_only: bool         # named only by the sequence of operation, no count


class Reader:
    def __init__(self, ledger: Ledger, dossier_sources: dict | None = None) -> None:
        self.ledger = ledger
        self.dossier_sources = dict(dossier_sources or {})
        self._families: dict[str, FamilyFacts] = {}

    # refs
    def where(self, source_id: str, depth: int = 0) -> str:
        sid = squash(source_id).strip("[]")
        if sid in self.ledger.sources:
            return where_short(self.ledger.sources[sid])
        if sid in self.dossier_sources:
            return where_short(self.dossier_sources[sid])
        fact = self.ledger.facts.get(sid)
        if fact is not None and depth < 5:
            return self.where(fact.source_id, depth + 1)
        return ""

    def ref(self, source_id: str, quote: str) -> Ref:
        sid = squash(source_id).strip("[]")
        return Ref(source_id=sid, quote=squash(quote), where=self.where(sid))

    def fact_ref(self, fact: Fact) -> Ref:
        return self.ref(fact.source_id, fact.quote)

    # counts
    def count_of(self, fact: Fact | None) -> Count:
        """The count a count fact gives: the highest number among its value and its contradictions, the refs
        giving it, and every other different number with its ref. Count(None) when none is a number."""
        if fact is None:
            return Count(None)
        entries = [(fact.value, fact.source_id, fact.quote)]
        entries += [(c.value, c.source_id, c.quote) for c in fact.contradictions]
        numbers = [(n, sid, q) for v, sid, q in entries for n in [number(v)] if n is not None]
        if not numbers:
            return Count(None, (self.fact_ref(fact),))
        top = max(n for n, _, _ in numbers)
        sources = _unique([self.ref(sid, q) for n, sid, q in numbers if n == top])
        others = _unique([OtherCount(n, self.ref(sid, q)) for n, sid, q in numbers if n != top])
        return Count(top, tuple(sources), tuple(others))

    # families
    def family_facts(self) -> list[Fact]:
        """The family facts, the first of each subject (any case), in ledger order."""
        seen, out = set(), []
        for fact in self.ledger.of_kind("family"):
            key = squash(fact.subject).casefold()
            if key and key not in seen:
                seen.add(key)
                out.append(fact)
        return out

    def family(self, fact: Fact) -> FamilyFacts:
        prefix = squash(fact.subject)
        if prefix.casefold() in self._families:
            return self._families[prefix.casefold()]
        unit = self.ledger.find("unit", prefix)
        tags = tuple(expand([squash(unit.value)])) if unit is not None and squash(unit.value) else ()
        count_fact = self.ledger.find("count", prefix)
        count = self.count_of(count_fact)
        sequence_only = count_fact is None and fact.stage == "sequence"
        plan_only = not sequence_only and (count_fact is None or count_fact.state == ADDED)
        found = FamilyFacts(fact, prefix, short_name(fact.value, prefix), tags, count, plan_only, sequence_only)
        self._families[prefix.casefold()] = found
        return found

    def family_by_prefix(self, prefix: str) -> FamilyFacts | None:
        key = squash(prefix).casefold()
        fact = next((f for f in self.family_facts() if squash(f.subject).casefold() == key), None)
        return self.family(fact) if fact is not None else None

    # sequence matches
    def matches(self, *names: str) -> list[Fact]:
        """The sequence_match facts whose value is one of the names (any case), in the names' order, each once."""
        found: list[Fact] = []
        for name in names:
            key = squash(name).casefold()
            if not key:
                continue
            found += [f for f in self.ledger.of_kind("sequence_match")
                      if squash(f.value).casefold() == key and f not in found]
        return found

    # notes
    def note(self, subject: str, *names: str) -> Fact | None:
        """The first note of this subject naming one of the names as a whole word, the names tried in order."""
        notes = [f for f in self.ledger.of_kind("note") if squash(f.subject).casefold() == subject]
        for name in (squash(n) for n in names):
            if not name:
                continue
            pattern = naming(name)
            for fact in notes:
                if pattern.search(squash(fact.value)):
                    return fact
        return None

    def alternate(self, *names: str) -> str:
        fact = self.note("alternate", *names)
        value = squash(fact.value).casefold() if fact else ""
        return "add" if value.startswith("add") else "deduct" if value.startswith("deduct") else "base"

    def exception(self, *names: str) -> str:
        fact = self.note("exception", *names)
        return squash(fact.value) if fact else ""


def _unique(items: list) -> list:
    return list(dict.fromkeys(items))
