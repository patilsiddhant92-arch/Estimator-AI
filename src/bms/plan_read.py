"""The planner's reading of the ledger (workstream 2, private): refs, counts, tags, names, sequence matches and the
notes that name a system. Pure functions over the old app's Ledger and Dossier; no AI."""
from __future__ import annotations

import re
from dataclasses import dataclass, replace

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

# The kind the dossier's equipment counts give a prefix it knows no kind for (estimator.writing.dossier): the code
# was read off a schedule row, but nothing says what equipment it is.
NO_KIND = "type code on a schedule"

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
    added: tuple[str, ...] = ()            # tags only a later pass's tag list gives (on the plans, not the list)
    listed: int = 0                        # how many tags the fact's own list gives
    was: int | None = None                 # the count before those tags raised it
    added_refs: tuple[Ref, ...] = ()       # where the added tags are


class Reader:
    def __init__(self, ledger: Ledger, dossier_sources: dict | None = None, dossier_text: str = "") -> None:
        self.ledger = ledger
        self.dossier_sources = dict(dossier_sources or {})
        self.dossier_text = str(dossier_text or "")
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
        """The count a count fact gives: the highest number among its value, its contradictions and the clauses
        of an equipment counts line its quotes carry ("plan placements 55" beside "schedule rows 2"), the refs
        giving it, and every other different number with its ref. Count(None) when none is a number."""
        if fact is None:
            return Count(None)
        return self._count([fact], [])

    def _entries(self, fact: Fact) -> list[tuple[int, tuple[Ref, ...]]]:
        """Every number one count fact gives, each with its ref: its value and each contradiction, then each
        clause of a counts line in their quotes that gives another number from the same source."""
        said = [(fact.value, fact.source_id, fact.quote)]
        said += [(c.value, c.source_id, c.quote) for c in fact.contradictions]
        out: list[tuple[int, tuple[Ref, ...]]] = []
        seen: set[tuple[int, str]] = set()
        for value, sid, quote in said:
            n = number(value)
            # A 0 is no count: it never prints as a known "0" (the count falls to Qty (##) when nothing else gives one).
            if n and (n, squash(sid)) not in seen:
                seen.add((n, squash(sid)))
                out.append((n, (self.ref(sid, quote),)))
        for _, sid, quote in said:
            for clause, n in counts_clauses(quote):
                if (n, squash(sid)) not in seen:
                    seen.add((n, squash(sid)))
                    out.append((n, (self.ref(sid, clause),)))
        return out

    def _count(self, facts: list[Fact], extra: list[tuple[int, tuple[Ref, ...]]]) -> Count:
        """The Count of every number the facts and the extra entries give: the highest prints, its refs are the
        sources, every other number is kept with its ref."""
        entries = [e for f in facts for e in self._entries(f)] + list(extra)
        if not entries:
            return Count(None, (self.fact_ref(facts[0]),) if facts else ())
        top = max(n for n, _ in entries)
        sources = _unique([r for n, refs in entries if n == top for r in refs])
        others = _unique([OtherCount(n, refs[0]) for n, refs in entries if n != top])
        return Count(top, tuple(sources), tuple(others))

    def family_count(self, prefix: str, tags: tuple[str, ...]) -> Count:
        """The family's count from every source that gives one (the highest prints; never undershoot): each count
        fact about the prefix (its value, contradictions and counts-line clauses), the count facts about its tags
        (each tag's highest, summed over the tags), and the "TAG ×N" counts on the dossier's sheets (summed over
        sheets and tags)."""
        key = squash(prefix).casefold()
        own = [f for f in self.ledger.of_kind("count") if squash(f.subject).casefold() == key]
        extra = []
        by_tag = self._tag_count_facts(prefix, tags)
        if by_tag:
            total = sum(max(n for n, _ in entries) for entries in by_tag.values())
            refs = _unique([r for entries in by_tag.values() for _, rs in entries for r in rs])
            extra.append((total, tuple(refs)))
        on_sheets = self._tag_times_on_sheets(tags)
        if on_sheets:
            extra.append((sum(n for n, _ in on_sheets), tuple(_unique([r for _, r in on_sheets]))))
        if not own and not extra:
            return Count(None)
        return self._count(own, extra)

    def zero_only(self, prefix: str) -> bool:
        """True when the family's count facts give 0 and no other number (a schedule that says 0 for a family that
        lists tags): the zero is not printed, and the planner asks."""
        key = squash(prefix).casefold()
        facts = [f for f in self.ledger.of_kind("count") if squash(f.subject).casefold() == key]
        said = [number(v) for f in facts for v in [f.value] + [c.value for c in f.contradictions]]
        return 0 in said and not any(said_n for said_n in said if said_n)

    def _tag_count_facts(self, prefix: str, tags: tuple[str, ...]) -> dict[str, list[tuple[int, tuple[Ref, ...]]]]:
        """The numbers count facts give the family's tags (a subject that is one of its tags, or the prefix, a
        dash and more), by tag in capitals."""
        head = squash(prefix).casefold() + "-"
        mine = {t.casefold() for t in tags}
        found: dict[str, list[tuple[int, tuple[Ref, ...]]]] = {}
        for fact in self.ledger.of_kind("count"):
            subject = squash(fact.subject).casefold()
            if subject in mine or (subject.startswith(head) and len(subject) > len(head)
                                   and " " not in subject):
                entries = self._entries(fact)
                if entries:
                    found.setdefault(subject.upper(), []).extend(entries)
        return found

    def _tag_times_on_sheets(self, tags: tuple[str, ...]) -> list[tuple[int, Ref]]:
        """Each "TAG ×N" (or "TAG xN") the dossier's text gives one of the family's tags, with its ref (the
        source line's id, the words "TAG ×N"). Only tags with a dash are looked for."""
        wanted = [t for t in tags if "-" in t]
        if not wanted or not self.dossier_text:
            return []
        names = "|".join(re.escape(t) for t in sorted(wanted, key=len, reverse=True))
        pattern = re.compile(rf"(?<![A-Za-z0-9\-])(?:{names})(?:\s*×|\s+x)\s*(\d+)(?![A-Za-z0-9.])", re.I)
        found: list[tuple[int, Ref]] = []
        for line in self.dossier_text.splitlines():
            head = _SOURCE_LINE.match(line)
            if not head:
                continue
            said = list(pattern.finditer(head.group(2)))
            if said:
                quote = " ... ".join(squash(m.group(0)) for m in said)
                found.append((sum(int(m.group(1)) for m in said), self.ref(head.group(1), quote)))
        return found

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
        listed = tuple(expand([squash(unit.value)])) if unit is not None and squash(unit.value) else ()
        added, added_refs = self._added_tags(unit, listed)
        tags = listed + added
        count_fact = self.ledger.find("count", prefix)
        count = self.family_count(prefix, tags)
        was = count.value
        if added and count.value is not None and count.value < len(tags):
            # one per tag (never undershoot): the old number is kept beside it, and the planner asks with both
            raised = (self.fact_ref(unit), *added_refs)
            count = Count(len(tags), tuple(_unique(list(raised))),
                          tuple(_unique([*count.others, OtherCount(count.value, count.sources[0])]))
                          if count.sources else count.others)
        sequence_only = count_fact is None and fact.stage == "sequence"
        plan_only = not sequence_only and (count_fact is None or count_fact.state == ADDED)
        found = FamilyFacts(fact, prefix, short_name(fact.value, prefix), tags, count, plan_only, sequence_only,
                            added, len(listed), was, added_refs)
        self._families[prefix.casefold()] = found
        return found

    def _added_tags(self, unit: Fact | None, listed: tuple[str, ...]) -> tuple[tuple[str, ...], tuple[Ref, ...]]:
        """The tags a unit fact's contradictions give that its own list does not (a later pass saw "EF-1 thru 4"
        where the schedule lists EF-1 thru 3), brackets dropped and ranges expanded as `seen_tags` does, each once
        in ledger order, with the refs giving them. Only words with a letter and a digit and no space are tags."""
        if unit is None:
            return (), ()
        have = {t.upper() for t in listed}
        tags: list[str] = []
        refs: list[Ref] = []
        for c in unit.contradictions:
            text = squash(re.sub(r"\([^()]*\)", " ", str(c.value or "")))
            gave = False
            for tag in expand([text]) if text else []:
                tag = squash(tag)
                if (tag and " " not in tag and re.search(r"[A-Za-z]", tag) and re.search(r"\d", tag)
                        and tag.upper() not in have):
                    have.add(tag.upper())
                    tags.append(tag)
                    gave = True
            if gave:
                refs.append(self.ref(c.source_id, c.quote))
        return tuple(tags), tuple(_unique(refs))

    def rename(self, family: FamilyFacts, name: str) -> FamilyFacts:
        """The family under another name, kept so every later read of it gives that name."""
        renamed = replace(family, name=name)
        self._families[family.prefix.casefold()] = renamed
        return renamed

    def seen_tags(self) -> list[tuple[str, Ref]]:
        """The tags the ledger records as seen on the drawings but on no family's tag list: the values (and the
        contradicting values) of each unit fact whose subject is no family's prefix ("seen on plans, not
        scheduled"), brackets dropped, ranges expanded, each with its ref; each tag once, in ledger order."""
        prefixes = {squash(f.subject).casefold() for f in self.family_facts()}
        out: dict[str, tuple[str, Ref]] = {}
        for fact in self.ledger.of_kind("unit"):
            if squash(fact.subject).casefold() in prefixes:
                continue
            said = [(fact.value, fact.source_id, fact.quote)]
            said += [(c.value, c.source_id, c.quote) for c in fact.contradictions]
            for value, sid, quote in said:
                text = squash(re.sub(r"\([^()]*\)", " ", str(value or "")))
                for tag in expand([text]) if text else []:
                    tag = squash(tag)
                    if tag and re.search(r"[A-Za-z]", tag) and tag.upper() not in out:
                        out[tag.upper()] = (tag, self.ref(sid, quote))
        return list(out.values())

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


_SOURCE_LINE = re.compile(r"^\s*\[([A-Za-z]{1,4}\d+[a-z]?)\]\s?(.*)$")
_COUNTS_CLAUSE = re.compile(r"\b(schedule rows|quantity column total|distinct tags|plan placements|riser)\s+(\d+)\b",
                            re.I)


def counts_clauses(quote: str) -> list[tuple[str, int]]:
    """The numbered clauses of an equipment counts line ("schedule rows 2; ...; plan placements 55 (...); riser 1"),
    each as its words and its number ("plan placements 55", 55); a zero is no count. [] for any other quote."""
    return [(squash(m.group(0)), int(m.group(2))) for m in _COUNTS_CLAUSE.finditer(squash(quote))
            if int(m.group(2)) > 0]


def _unique(items: list) -> list:
    return list(dict.fromkeys(items))
