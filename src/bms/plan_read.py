"""The planner's reading of the ledger (workstream 2, private): refs, counts, tags, names, sequence matches and the
notes that name a system. Pure functions over the old app's Ledger and Dossier; no AI."""
from __future__ import annotations

import re
from dataclasses import dataclass, replace

from estimator.catalogue.tags import STATED_MOST, is_type_tag
from estimator.ledger.facts import Fact, Ledger, where_short

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


# the words that make a system a bid alternate: "ADD ALTERNATE", "ADD ALT", "ADDITIVE ALTERNATE #2", "DEDUCT ALT. 1",
# "DEDUCTIVE ALTERNATE"; or one numbered only ("ALTERNATE #1", "ALT. NO. 2"), read as an add
_ALT = r"alt(?:ernate)?s?\b\.?"
_ALT_NUMBER = r"(?:\s*(?:#|no\.?|number)\s*\d+)"
_ADD_ALT = re.compile(rf"\badd(?:itive|ed)?\s+{_ALT}(?:{_ALT_NUMBER})?", re.I)
_DEDUCT_ALT = re.compile(rf"\bdeduct(?:ive|ed)?\s+{_ALT}(?:{_ALT_NUMBER})?", re.I)
_NUMBERED_ALT = re.compile(rf"\b{_ALT}{_ALT_NUMBER}", re.I)
_NOT_ALT = re.compile(r"\bno\s+(?:add\s+|deduct\s+)?alternates?\b|\bnot\s+(?:an?\s+)?(?:add\s+|deduct\s+)?alternate\b",
                      re.I)


def alternate_words(text: str) -> tuple[str, str, bool] | None:
    """The bid alternate a text names: ("add" | "deduct", the words, numbered-only), or None. "ADD ALTERNATE",
    "ADD ALT", "DEDUCT ALTERNATE" say the side; "ALTERNATE #1" alone is read as an add (numbered-only True)."""
    text = squash(text)
    if not text or _NOT_ALT.search(text):
        return None
    for kind, pattern in (("deduct", _DEDUCT_ALT), ("add", _ADD_ALT)):
        m = pattern.search(text)
        if m:
            return kind, m.group(0), False
    m = _NUMBERED_ALT.search(text)
    return ("add", m.group(0), True) if m else None


def _sentence_with(text: str, phrase: str) -> str:
    """The exact words of `text` around `phrase`: the whole text when short, else the sentence holding it."""
    text = squash(text)
    if len(text) <= 160:
        return text
    at = text.find(phrase)
    start = max(text.rfind(". ", 0, at) + 2, 0) if at >= 0 else 0
    end = text.find(". ", at)
    return text[start:(end + 1 if end >= 0 else len(text))].strip()


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


# A count stated after a tag, in every form the catalogue reads on a line of its own (`estimator.catalogue.tags`
# `_STATED`, ruled FINAL-O: a stated multiplier is a placement count): "CUH-A (TYP. OF 4)", "CUH-A (TYP. OF 4
# PLACES)", "CUH-A (TYP. 4)", "CUH-A TYP OF 4", "CUH-A, TYP. OF 4", "CUH-A TYP. (4)", "CUH-A (4)", "CUH-A (4 TOTAL)",
# "CUH-A (4X)", "CUH-A 4 PLACES", "CUH-A (QTY 4)", "CUH-A QTY. 4", "CUH-A x4", "CUH-A×4", and "CUH-Ax4" (a small x
# only, and only after a known tag: `times_form`) (PLAN-4, PLAN-5). The catalogue's patterns are anchored to the
# whole rest of a line, so they cannot scan a group fact or a sheet's text; these are the same forms, unanchored.
# The count is the first group that matched. As in the catalogue, a TYP, bracket, PLACES or QTY count over
# STATED_MOST is not read ("CD-1 (200)" is a size or a note, not 200 places); "x" and "×" are read at any size, as
# before.
_PLACES = r"(?:PLACES|PLCS?|LOCATIONS|LOCS?|TOTAL)"
TIMES_AFTER = (rf"(?:\s*\(\s*TYP(?:ICAL)?\.?\s*(?:OF\s+)?(\d+)\s*(?:{_PLACES}\.?)?\s*\.?\s*\)"
               rf"|\s*,?\s+(?:[-‐‑–—]\s+)?TYP(?:ICAL)?\.?\s*(?:OF\s+)?(?:\(\s*(\d+)\s*\)|(\d+)(?:\s*{_PLACES}\.?)?)"
               rf"|\s*\(\s*(\d+)\s*(?:{_PLACES}|X|×)?\.?\s*\)"
               rf"|\s+(\d+)\s*{_PLACES}\.?"
               r"|\s*\(\s*(?:QTY|QUANTITY)\.?\s*:?\s*(\d+)\s*\)|\s+(?:QTY|QUANTITY)\.?\s*:?\s*(\d+)"
               r"|\s*×\s*(\d+)"
               r"|\s+x\s*(\d+))"
               r"(?![A-Za-z0-9]|\.\d)")                     # never the X of "TX1", nor a decimal such as "x4.5"
GLUED_TIMES = r"(?-i:x)(\d+)(?![A-Za-z0-9]|\.\d)"            # "CUH-Ax4": a small x glued to a tag
_A_TAG = r"[A-Za-z]{1,6}(?:-[A-Za-z0-9.]+)+"
_TAG_STATED = re.compile(rf"(?<![A-Za-z0-9\-])({_A_TAG}){TIMES_AFTER}", re.I)
_TAG_GLUED = re.compile(rf"(?<![A-Za-z0-9\-])({_A_TAG}){GLUED_TIMES}")
# a count before a tag, "4x CUH-A", "4 × CUH-A" (PLAN-4): read as "CUH-A ×4" up to STATED_MOST
_COUNT_THEN_TAG = re.compile(rf"(?<![A-Za-z0-9.\-])(\d+)\s*[x×]\s*({_A_TAG})(?![A-Za-z0-9])", re.I)


_CAPPED_FORMS = 7                                            # TIMES_AFTER's forms before "×" and "x": capped


def stated_number(match: re.Match, first: int = 1) -> int | None:
    """The count a match of TIMES_AFTER (then GLUED_TIMES) read: its first group, from group `first` on, that
    matched. None when a TYP, bracket, PLACES or QTY count is 0 or over STATED_MOST: not read."""
    at, said = next((n, g) for n, g in enumerate(match.groups()[first - 1:]) if g is not None)
    n = int(said)
    return None if at < _CAPPED_FORMS and not 0 < n <= STATED_MOST else n


def times_form(text: str, known=()) -> str:
    """The text with each count stated after a tag written as "TAG ×N" (TIMES_AFTER), so one reading of "×N" reads
    every form; a bracket that only states a count goes, so "CUH (CUH-A (4), CUH-B)" lists two tags. A count before
    a tag ("4x CUH-A") is written "CUH-A ×4" too. A glued "CUH-Ax4" is split only when CUH-A is one of the `known`
    tags and "CUH-Ax4" itself is not (a tag such as "VAV-2X1" stays whole)."""
    keys = {t.casefold() for t in known}
    text = _COUNT_THEN_TAG.sub(lambda m: f"{m.group(2)} ×{m.group(1)}" if 0 < int(m.group(1)) <= STATED_MOST
                               else m.group(0), text)
    text = _TAG_STATED.sub(lambda m: m.group(0) if stated_number(m, 2) is None
                           else f"{m.group(1)} ×{stated_number(m, 2)}", text)
    return _TAG_GLUED.sub(lambda m: f"{m.group(1)} ×{m.group(2)}"
                          if m.group(1).casefold() in keys and m.group(0).casefold() not in keys else m.group(0), text)


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
    duplicates: tuple[str, ...] = ()       # tags the schedule's own list gives more than once (Quantity rules R7)


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
        """The count a count fact gives (`_count`): the schedule's quantity when the fact is a schedule's, else the
        highest number among its value, its contradictions and the clauses of an equipment counts line its quotes
        carry ("plan placements 55" beside "schedule rows 2"), the refs giving it, and every other different number
        with its ref; a schedule of types with no quantity is read as `_count` reads it (the subject's unit fact
        gives the tags). Count(None) when none is a number."""
        if fact is None:
            return Count(None)
        unit = self.ledger.find("unit", squash(fact.subject))
        tags = expand([squash(unit.value)]) if unit is not None and squash(unit.value) else []
        return self._count([fact], [], bool(tags) and all(is_type_tag(t) for t in tags))

    def _entries(self, fact: Fact) -> list[tuple[int, tuple[Ref, ...], bool]]:
        """Every number one count fact gives, each with its ref and whether it is the equipment schedule's: its
        value and each contradiction, then each clause of a counts line in their quotes that gives another number
        from the same source. The schedule's numbers are the value of a count the schedules settled
        (`is_schedule`) and a contradiction the schedules pass gave; a counts line's clauses ("plan placements",
        "distinct tags", "riser") check it."""
        mine = is_schedule(fact)
        said = [(fact.value, fact.source_id, fact.quote, mine)]
        said += [(c.value, c.source_id, c.quote, c.stage == "schedules") for c in fact.contradictions]
        out: list[tuple[int, tuple[Ref, ...], bool]] = []
        seen: set[tuple[int, str]] = set()
        for value, sid, quote, scheduled in said:
            n = number(value)
            # A 0 is no count: it never prints as a known "0" (the count falls to Qty (##) when nothing else gives one).
            if n and (n, squash(sid)) not in seen:
                seen.add((n, squash(sid)))
                out.append((n, (self.ref(sid, quote),), scheduled))
        for _, sid, quote, _scheduled in said:
            for clause, n in counts_clauses(quote):
                if (n, squash(sid)) not in seen:
                    seen.add((n, squash(sid)))
                    out.append((n, (self.ref(sid, clause),), False))
        return out

    def _count(self, facts: list[Fact], extra: list[tuple[int, tuple[Ref, ...], bool]],
               types: bool = False) -> Count:
        """The Count of every number the facts and the extra entries give (the estimator's count ruling): when a
        schedule gives one, the first schedule number prints (basis "schedule") and every other number is kept
        with its ref as a DISCREPANCY flag, never raising or lowering it; with no schedule the highest prints
        (basis "highest"), every other number kept with its ref as a CONFLICT flag. The refs of every entry giving
        the printed number are its sources (a plan count that agrees confirms the schedule). `types`: the family's
        tags are all types' (CUH-A, AC-3.0): a schedule of types gives a count only where it states a quantity
        ("QUANTITY column total 4", "qty 4"); its rows are types, not units, and the plans' count is the quantity
        (Quantity rules R8: a typical schedule, quantity from the plans)."""
        entries = [e for f in facts for e in self._entries(f)] + list(extra)
        if types:
            entries = [(n, refs, schedule and any(_STATED_QUANTITY.search(r.quote) for r in refs))
                       for n, refs, schedule in entries]
        if not entries:
            return Count(None, (self.fact_ref(facts[0]),) if facts else ())
        scheduled = [n for n, _refs, schedule in entries if schedule]
        top = scheduled[0] if scheduled else max(n for n, _refs, _s in entries)
        sources = _unique([r for n, refs, _s in entries if n == top for r in refs])
        others = _unique([OtherCount(n, refs[0]) for n, refs, _s in entries if n != top])
        return Count(top, tuple(sources), tuple(others), "schedule" if scheduled else "highest")

    def family_count(self, prefix: str, tags: tuple[str, ...]) -> Count:
        """The family's count from every source that gives one (`_count`: the schedule's quantity when a schedule
        gives one, else the highest; every other number kept and flagged): each count fact about the prefix (its
        value, contradictions and counts-line clauses), the count facts about its tags (each tag's highest, summed
        over the tags; the schedule's when every one is a schedule's), and the "TAG ×N" counts on the dossier's
        sheets (summed over sheets and tags)."""
        key = squash(prefix).casefold()
        own = [f for f in self.ledger.of_kind("count") if squash(f.subject).casefold() == key]
        extra = []
        by_tag = self._tag_count_facts(prefix, tags)
        if by_tag:
            total = sum(max(n for n, _r, _s in entries) for entries in by_tag.values())
            refs = _unique([r for entries in by_tag.values() for _, rs, _s in entries for r in rs])
            scheduled = all(any(s for _n, _r, s in entries) for entries in by_tag.values())
            if scheduled:
                total = sum(next(n for n, _r, s in entries if s) for entries in by_tag.values())
            extra.append((total, tuple(refs), scheduled))
        on_sheets = self._tag_times_on_sheets(tags)
        if on_sheets:
            extra.append((sum(n for n, _ in on_sheets), tuple(_unique([r for _, r in on_sheets])), False))
        if not own and not extra:
            return Count(None)
        return self._count(own, extra, bool(tags) and all(is_type_tag(t) for t in tags))

    def zero_only(self, prefix: str) -> bool:
        """True when the family's count facts give 0 and no other number (a schedule that says 0 for a family that
        lists tags): the zero is not printed, and the planner asks."""
        key = squash(prefix).casefold()
        facts = [f for f in self.ledger.of_kind("count") if squash(f.subject).casefold() == key]
        said = [number(v) for f in facts for v in [f.value] + [c.value for c in f.contradictions]]
        return 0 in said and not any(said_n for said_n in said if said_n)

    def _tag_count_facts(self, prefix: str, tags: tuple[str, ...]
                         ) -> dict[str, list[tuple[int, tuple[Ref, ...], bool]]]:
        """The numbers count facts give the family's tags (a subject that is one of its tags, or the prefix, a
        dash and more), by tag in capitals."""
        head = squash(prefix).casefold() + "-"
        mine = {t.casefold() for t in tags}
        found: dict[str, list[tuple[int, tuple[Ref, ...], bool]]] = {}
        for fact in self.ledger.of_kind("count"):
            subject = squash(fact.subject).casefold()
            if subject in mine or (subject.startswith(head) and len(subject) > len(head)
                                   and " " not in subject):
                entries = self._entries(fact)
                if entries:
                    found.setdefault(subject.upper(), []).extend(entries)
        return found

    def _tag_times_on_sheets(self, tags: tuple[str, ...]) -> list[tuple[int, Ref]]:
        """Each count the dossier's text states after one of the family's tags ("TAG ×N", "TAG xN", "TAGxN",
        "TAG (TYP. OF N)", "TAG (N)", "TAG N PLACES": TIMES_AFTER), with its ref (the source line's id, the words
        as printed). Only tags with a dash are looked for."""
        wanted = [t for t in tags if "-" in t]
        if not wanted or not self.dossier_text:
            return []
        names = "|".join(re.escape(t) for t in sorted(wanted, key=len, reverse=True))
        pattern = re.compile(rf"(?<![A-Za-z0-9\-])(?:{names})(?:{TIMES_AFTER}|{GLUED_TIMES})", re.I)
        found: list[tuple[int, Ref]] = []
        for line in self.dossier_text.splitlines():
            head = _SOURCE_LINE.match(line)
            if not head:
                continue
            said = [m for m in pattern.finditer(head.group(2)) if stated_number(m) is not None]
            if said:
                quote = " ... ".join(squash(m.group(0)) for m in said)
                found.append((sum(stated_number(m) for m in said), self.ref(head.group(1), quote)))
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
        """The family as the planner reads it. Its tags are the unit fact's list (each tag once) and the tags a
        later pass added; its count is `family_count`. A list of unit tags (`is_type_tag` false) longer than the
        count (PLAN-3: "VAV-1 thru 5" beside a count of 3) is one more count, one per tag: with a schedule the
        schedule's count stays the working count and the list's is a DISCREPANCY beside it; with none the list's
        count prints, the old number kept beside it. A tag the schedule's own list gives twice is a duplicate tag
        on the schedule (Quantity rules R7): a DISCREPANCY the planner asks about, never a silent 1 or 2."""
        prefix = squash(fact.subject)
        if prefix.casefold() in self._families:
            return self._families[prefix.casefold()]
        unit = self.ledger.find("unit", prefix)
        listed = tuple(expand([squash(unit.value)])) if unit is not None and squash(unit.value) else ()
        duplicates = listed_twice(unit.value) if unit is not None and is_schedule(unit) else ()
        added, added_refs = self._added_tags(unit, listed)
        tags = listed + added
        count_fact = self.ledger.find("count", prefix)
        count = self.family_count(prefix, tags)
        was = count.value
        units = len({t.upper() for t in tags if not is_type_tag(t)})
        if count.value is not None and units > count.value:
            # one per unit tag: with a schedule a DISCREPANCY beside its count; with none it prints, the old kept
            raised = (self.fact_ref(unit), *added_refs)
            if count.basis == "schedule":
                if not any(o.value == units for o in count.others):
                    count = replace(count, others=(*count.others, OtherCount(units, raised[0])))
            else:
                count = Count(units, tuple(_unique(list(raised))),
                              tuple(_unique([*count.others, OtherCount(count.value, count.sources[0])]))
                              if count.sources else count.others)
        if duplicates and count.value is not None:
            distinct = len(listed)
            if distinct != count.value and not any(o.value == distinct for o in count.others):
                count = replace(count, others=(*count.others, OtherCount(distinct, self.fact_ref(unit))))
        sequence_only = count_fact is None and fact.stage == "sequence"
        plan_only = not sequence_only and (count_fact is None or not count_fact.was_settled)
        found = FamilyFacts(fact, prefix, short_name(fact.value, prefix), tags, count, plan_only, sequence_only,
                            added, len(listed), was, added_refs, duplicates)
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
        return self.alternate_cited(*names)[0]

    def alternate_cited(self, *names: str, tags=()) -> tuple[str, Ref | None, bool]:
        """The alternate the documents make of the system these names (and `tags`) call, with its citation, and
        whether the documents only number it ("ALTERNATE #1", read as an add, a question for the estimator).

        An "alternate" note naming it wins (its value "add" or "deduct"). Else the first of these that names an
        alternate ("ADD ALTERNATE", "ADD ALT", "ADDITIVE ALTERNATE", "DEDUCT ALTERNATE", "ALTERNATE #1",
        "ALT. NO. 2"): the title or a note of a schedule that lists one of its tags or is the source of its family
        fact; a fact whose subject is one of its names (its value, its quote or its source's place); a note of any
        other subject (a plan or schedule note) naming it. ("base", None, False) when none does: never invented."""
        fact = self.note("alternate", *names)
        value = squash(fact.value).casefold() if fact else ""
        if value.startswith(("add", "deduct")):
            return ("add" if value.startswith("add") else "deduct"), self.fact_ref(fact), False
        keys = {squash(n).casefold() for n in names if squash(n)}
        own = {squash(t).upper() for t in tags if squash(t)}
        # (source id, the words read, the quote to cite: None for the words themselves, cut to their sentence)
        said: list[tuple[str, str, str | None]] = []
        cited = set()
        for f in self.ledger.facts.values():
            if squash(f.subject).casefold() in keys:
                cited.add(squash(f.source_id).strip("[]"))
                # the source's place carries a schedule's title ("M-400.00 <TITLE>, <file> page 7"): cited by
                # the fact's own quote, the source's exact words
                said += [(f.source_id, squash(f.quote), None), (f.source_id, self.where(f.source_id), squash(f.quote))]
        said = [(sid, words, None) for sid, words in self._schedule_alternates(own, cited)] + said
        for f in self.ledger.of_kind("note"):
            if squash(f.subject).casefold() in ("alternate", "exception", "question"):
                continue
            if names_in(keys, squash(f.value)) or names_in(keys, squash(f.quote)) or names_in(own, squash(f.value)):
                said.append((f.source_id, squash(f.quote), None))
        for sid, words, quote in said:
            found = alternate_words(words)
            if found is not None and (quote is None or quote):
                kind, phrase, numbered = found
                return kind, self.ref(sid, quote or _sentence_with(words, phrase)), numbered
        return "base", None, False

    def _schedule_alternates(self, tags: set[str], cited: set[str]) -> list[tuple[str, str]]:
        """The title and the notes of each dossier schedule listing one of `tags` (a row's first cell) or whose
        title entry is a cited source, as (source id, words), the title first."""
        from bms import ai_evidence           # the dossier's own reader (no cycle: ai_evidence needs only the model)
        entries = [e for e in ai_evidence.parse(self.dossier_text) if e.part == ai_evidence.SCHEDULES]
        out: list[tuple[str, str]] = []
        for title, rows, notes in ai_evidence._schedule_blocks(entries):
            firsts = {squash(re.sub(r"^\[[A-Za-z]{1,4}\d+[a-z]?\]\s?", "", r.text.split("\n", 1)[0]).split("|", 1)[0]).upper()
                      for r in rows}
            if not (firsts & tags or title.sid in cited):
                continue
            first = re.sub(r"^\[[A-Za-z]{1,4}\d+[a-z]?\]\s?", "", title.text.split("\n", 1)[0])
            out.append((title.sid, squash(first.split(" — ", 1)[0])))
            out += [(n.sid, squash(n.body)) for n in notes]
        return out

    def exception(self, *names: str) -> str:
        fact = self.note("exception", *names)
        return squash(fact.value) if fact else ""


_SOURCE_LINE = re.compile(r"^\s*\[([A-Za-z]{1,4}\d+[a-z]?)\]\s?(.*)$")
# a schedule's stated quantity in a count's quote: its QUANTITY column ("QUANTITY column total 4", "QTY 4", "qty: 4")
_STATED_QUANTITY = re.compile(r"\b(?:QUANTITY(?:\s+column\s+total)?|QTY)\.?\s*:?\s*\d", re.I)
_COUNTS_CLAUSE = re.compile(r"\b(schedule rows|quantity column total|distinct tags|plan placements|riser)\s+(\d+)\b",
                            re.I)


def listed_twice(value) -> tuple[str, ...]:
    """The tags a tag list gives more than once ("FCU-7-1, FCU-7-1, FCU-7-2", "VAV-1 thru 3, VAV-2"), in order:
    each comma piece that is a whole tag or range is expanded alone, so a repeat is seen (`expand` keeps one)."""
    seen: dict[str, int] = {}
    for piece in squash(value).split(","):
        piece = piece.strip()
        if not re.match(r"^[A-Za-z]", piece):
            continue                      # "AHU-1, 2, 3": a bare number continues the piece before it
        for tag in expand([piece]):
            seen[tag.upper()] = seen.get(tag.upper(), 0) + 1
    return tuple(tag for tag, n in seen.items() if n > 1)


def is_schedule(fact: Fact | None) -> bool:
    """Whether a fact is the equipment schedule's: settled by the seed (a schedule's rows or QUANTITY column) or by
    the schedules pass. Only that pass settles a count or a tag list (`estimator.ledger.passes`); a later pass's
    different number is a contradiction beside it."""
    return fact is not None and fact.was_settled and fact.stage in ("seed", "schedules")


def counts_clauses(quote: str) -> list[tuple[str, int]]:
    """The numbered clauses of an equipment counts line ("schedule rows 2; ...; plan placements 55 (...); riser 1"),
    each as its words and its number ("plan placements 55", 55); a zero is no count. [] for any other quote."""
    return [(squash(m.group(0)), int(m.group(2))) for m in _COUNTS_CLAUSE.finditer(squash(quote))
            if int(m.group(2)) > 0]


def _unique(items: list) -> list:
    return list(dict.fromkeys(items))
