"""The planner's reading of the ledger (workstream 2, private): refs, counts, tags, names, sequence matches and the
notes that name a system. Pure functions over the old app's Ledger and Dossier; no AI."""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from functools import lru_cache

from estimator.catalogue.tags import STATED_MOST
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
# `_STATED`, ruled FINAL-O: a stated multiplier is a placement count): "CUH-A (TYP. OF 4)", "CUH-A TYP OF 4",
# "CUH-A (4)", "CUH-A 4 PLACES", "CUH-A x4", "CUH-A×4", and "CUH-Ax4" (a small x only, and only after a known tag:
# `times_form`). The catalogue's patterns are anchored to the whole rest of a line, so they cannot scan a group
# fact or a sheet's text; these are the same forms, unanchored. The count is the first group that matched. As in the
# catalogue, a TYP, bracket or PLACES count over STATED_MOST is not read ("CD-1 (200)" is a size or a note, not 200
# places); "x" and "×" are read at any size, as before.
TIMES_AFTER = (r"(?:\s*\(\s*TYP(?:ICAL)?\.?\s*OF\s+(\d+)\s*\.?\s*\)"
               r"|\s+TYP(?:ICAL)?\.?\s*OF\s+(\d+)"
               r"|\s*\(\s*(\d+)\s*\)"
               r"|\s+(\d+)\s*(?:PLACES|PLCS?|LOCATIONS)\.?"
               r"|\s*×\s*(\d+)"
               r"|\s+x\s*(\d+))"
               r"(?![A-Za-z0-9]|\.\d)")                     # never the X of "TX1", nor a decimal such as "x4.5"
GLUED_TIMES = r"(?-i:x)(\d+)(?![A-Za-z0-9]|\.\d)"            # "CUH-Ax4": a small x glued to a tag
_A_TAG = r"[A-Za-z]{1,6}(?:-[A-Za-z0-9.]+)+"
_TAG_STATED = re.compile(rf"(?<![A-Za-z0-9\-])({_A_TAG}){TIMES_AFTER}", re.I)
_TAG_GLUED = re.compile(rf"(?<![A-Za-z0-9\-])({_A_TAG}){GLUED_TIMES}")


_CAPPED_FORMS = 4                                            # TIMES_AFTER's first four forms: TYP, bracket, PLACES


def stated_number(match: re.Match, first: int = 1) -> int | None:
    """The count a match of TIMES_AFTER (then GLUED_TIMES) read: its first group, from group `first` on, that
    matched. None when a TYP, bracket or PLACES count is 0 or over STATED_MOST: not read."""
    at, said = next((n, g) for n, g in enumerate(match.groups()[first - 1:]) if g is not None)
    n = int(said)
    return None if at < _CAPPED_FORMS and not 0 < n <= STATED_MOST else n


def times_form(text: str, known=()) -> str:
    """The text with each count stated after a tag written as "TAG ×N" (TIMES_AFTER), so one reading of "×N" reads
    every form; a bracket that only states a count goes, so "CUH (CUH-A (4), CUH-B)" lists two tags. A glued
    "CUH-Ax4" is split only when CUH-A is one of the `known` tags and "CUH-Ax4" itself is not (a tag such as
    "VAV-2X1" stays whole)."""
    keys = {t.casefold() for t in known}
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
class AddedUp:
    """Ruling L1: the counts stated after a family's tags on the dossier's plan sheets ("CUH-A (TYP. OF 4)") are not
    added over sheets that show one floor and area. They count `counted`; added up the sheets give `summed`, which is
    above it. `sheets` are the places of each group of 2 or more such sheets that state a count."""
    counted: int
    summed: int
    sheets: tuple[tuple[str, ...], ...] = ()

    def note(self) -> str:
        """The plain words for the drop, both numbers: "M-101 and M-201 show one floor and area, so the counts stated
        for its tags on them count once, not added: 4 counted, 8 if the sheets were added up"."""
        numbers = f"{self.counted} counted, {self.summed} if the sheets were added up"
        if not self.sheets:
            return f"the counts stated for its tags on sheets of one floor and area count once, not added: {numbers}"
        shows = "; ".join(f"{_names(group)} show one floor and area" for group in self.sheets)
        return f"{shows}, so the counts stated for its tags on them count once, not added: {numbers}"


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
    added_up: AddedUp | None = None        # ruling L1 lowered the stated counts on the plan sheets: both numbers


@dataclass(frozen=True)
class _PlanSheet:
    """A plan sheet as one dossier line of its own text (7c) names it, in the shape `inventory.plan_groups` reads."""
    document: str
    page: int
    number: str | None
    title: str


_SHEET_TEXT = "(sheet text)"          # how the dossier's source for a sheet's own text (7c) ends
_COUNTS_SOURCE = "equipment counts for "     # how the dossier's source for a family's equipment counts line begins
_PLACE = re.compile(r"^(?:(?P<number>[^,]+), )?(?P<document>.+?) page (?P<page>\d+)$")


@lru_cache(maxsize=1)
def _sheet_types():
    from estimator.catalogue.sheet_types import SheetTypes

    return SheetTypes.load()


def _plan_sheet(where: str, text: str) -> _PlanSheet | None:
    """The plan sheet a dossier line of sheet text gives: `where` is its place ("M-101, Drawings.pdf page 3"), `text`
    the line after its id ("M-101, Drawings.pdf page 3 LEVEL 2 PIPING PLAN: ..."); the title is the words between the
    place and the colon. None when the line does not begin with its place, or the title is no plan's (`types_of`)."""
    from estimator.catalogue.sheet_types import types_of

    place = _PLACE.match(where)
    if place is None or not text.startswith(where):
        return None
    title = text[len(where):].split(":", 1)[0].strip()
    if not title or "Plans" not in types_of(title, _sheet_types()):
        return None
    return _PlanSheet(place.group("document"), int(place.group("page")), place.group("number"), title)


def _names(places) -> str:
    """"M-101", "M-101 and M-201", "M-101, M-201 and M-301"."""
    places = list(places)
    return places[0] if len(places) == 1 else ", ".join(places[:-1]) + f" and {places[-1]}"


class Reader:
    def __init__(self, ledger: Ledger, dossier_sources: dict | None = None, dossier_text: str = "") -> None:
        self.ledger = ledger
        self.dossier_sources = dict(dossier_sources or {})
        self.dossier_text = str(dossier_text or "")
        self._families: dict[str, FamilyFacts] = {}
        self._plans: dict[str, _PlanSheet] | None = None
        self._groups: dict | None = None

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
        (each tag's highest, summed over the tags), and the "TAG ×N" counts on the dossier's sheets (ruling L1: each
        tag's highest over the sheets of one floor and area, summed over the floors and areas and the tags)."""
        return self._family_count(prefix, tags)[0]

    def _family_count(self, prefix: str, tags: tuple[str, ...]) -> tuple[Count, AddedUp | None]:
        """`family_count` and, when ruling L1 made the stated counts on the plan sheets lower than the sheets add up
        to, both numbers (`AddedUp`)."""
        key = squash(prefix).casefold()
        own = [f for f in self.ledger.of_kind("count") if squash(f.subject).casefold() == key]
        extra = []
        added_up = None
        by_tag = self._tag_count_facts(prefix, tags)
        if by_tag:
            total = sum(max(n for n, _ in entries) for entries in by_tag.values())
            refs = _unique([r for entries in by_tag.values() for _, rs in entries for r in rs])
            extra.append((total, tuple(refs)))
        stated = self._stated_on_plans(tags)
        if stated is not None:
            counted, refs, added_up = stated
            extra.append((counted, refs))
        if not own and not extra:
            return Count(None), None
        return self._count(own, extra), added_up

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

    def _tag_times_on_sheets(self, tags: tuple[str, ...]) -> list[tuple[str, dict[str, int], Ref]]:
        """Each dossier line that states a count after one of the family's tags ("TAG ×N", "TAG xN", "TAGxN",
        "TAG (TYP. OF N)", "TAG (N)", "TAG N PLACES": TIMES_AFTER): (its source id, the count stated for each tag on
        it in capitals, summed over the line, its ref: the source line's id, the words as printed). Only tags with a
        dash are looked for. The dossier's own equipment counts lines are not read: their reading notes name a type
        tag's placements ("CUH-A 4 places, 4 on M-101"), which TIMES_AFTER also reads as a stated count, and those
        placements are the plan sheets' counts again, not more units (the counts line's `plan placements` clause is
        read from the count facts: `counts_clauses`)."""
        wanted = [t for t in tags if "-" in t]
        if not wanted or not self.dossier_text:
            return []
        names = "|".join(re.escape(t) for t in sorted(wanted, key=len, reverse=True))
        pattern = re.compile(rf"(?<![A-Za-z0-9\-])({names})(?:{TIMES_AFTER}|{GLUED_TIMES})", re.I)
        found: list[tuple[str, dict[str, int], Ref]] = []
        for line in self.dossier_text.splitlines():
            head = _SOURCE_LINE.match(line)
            if not head or self.dossier_sources.get(head.group(1), "").startswith(_COUNTS_SOURCE):
                continue
            said = [m for m in pattern.finditer(head.group(2)) if stated_number(m, 2) is not None]
            if said:
                per_tag: dict[str, int] = {}
                for m in said:
                    per_tag[m.group(1).upper()] = per_tag.get(m.group(1).upper(), 0) + stated_number(m, 2)
                quote = " ... ".join(squash(m.group(0)) for m in said)
                found.append((head.group(1), per_tag, self.ref(head.group(1), quote)))
        return found

    # -- ruling L1: the plan sheets of the dossier, and which of them show one floor and area

    def _plan_sheets(self) -> dict[str, _PlanSheet]:
        """Source id -> the plan sheet whose own text (7c) a dossier line gives: a line whose source ends "(sheet text)"
        and whose words begin with that source's place, then its title (`_plan_sheet`). Every such sheet, whether or not
        it states a count, because two sheets of one trade and one title make their floor too uncertain to group
        (`inventory.plan_groups`)."""
        if self._plans is None:
            found: dict[str, _PlanSheet] = {}
            for line in self.dossier_text.splitlines():
                head = _SOURCE_LINE.match(line)
                source = self.dossier_sources.get(head.group(1), "") if head else ""
                if head and source.endswith(_SHEET_TEXT):
                    sheet = _plan_sheet(where_short(source), head.group(2))
                    if sheet is not None:
                        found[head.group(1)] = sheet
            self._plans = found
        return self._plans

    def _plan_groups(self) -> dict:
        """(document, page) -> its plan group, over every plan sheet of the dossier (`inventory.plan_groups`, no tag
        evidence: only the same floor and area for other trades, ruling L1, groups them)."""
        if self._groups is None:
            from estimator.reading.inventory import plan_groups

            sheets = {(s.document, s.page): s for s in self._plan_sheets().values()}
            self._groups = plan_groups([(sheet, {}) for sheet in sheets.values()])
        return self._groups

    def _stated_on_plans(self, tags: tuple[str, ...]) -> tuple[int, tuple[Ref, ...], AddedUp | None] | None:
        """The counts the dossier states after the family's tags (`_tag_times_on_sheets`) by ruling L1: for each tag the
        most stated on one sheet of a group of sheets that show one floor and area, added over the groups and the tags
        (a line that is no plan sheet's text is a group of its own); (the count, the refs of every line that states
        one, both numbers when the rule made the count lower than the lines add up to). None when none states one."""
        lines = self._tag_times_on_sheets(tags)
        if not lines:
            return None
        plans, groups = self._plan_sheets(), self._plan_groups()

        def group_of(source_id: str):
            sheet = plans.get(source_id)
            return groups.get((sheet.document, sheet.page), ((sheet.document, sheet.page),)) if sheet else (source_id,)

        most: dict[tuple, dict[str, int]] = {}
        places: dict[tuple, list[str]] = {}
        for source_id, per_tag, _ref in lines:
            slot = most.setdefault(group_of(source_id), {})
            for tag, n in per_tag.items():
                slot[tag] = max(slot.get(tag, 0), n)
            if source_id in plans:
                sheet = plans[source_id]
                places.setdefault(group_of(source_id), []).append(
                    sheet.number or where_short(self.dossier_sources[source_id]))
        counted = sum(n for slot in most.values() for n in slot.values())
        summed = sum(n for _id, per_tag, _ref in lines for n in per_tag.values())
        same = tuple(tuple(dict.fromkeys(names)) for names in places.values() if len(set(names)) >= 2)
        refs = tuple(_unique([ref for _id, _per_tag, ref in lines]))
        return counted, refs, AddedUp(counted, summed, same) if summed > counted else None

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
        count, added_up = self._family_count(prefix, tags)
        was = count.value
        if added and count.value is not None and count.value < len(tags):
            # one per tag (never undershoot): the old number is kept beside it, and the planner asks with both
            raised = (self.fact_ref(unit), *added_refs)
            count = Count(len(tags), tuple(_unique(list(raised))),
                          tuple(_unique([*count.others, OtherCount(count.value, count.sources[0])]))
                          if count.sources else count.others)
        sequence_only = count_fact is None and fact.stage == "sequence"
        plan_only = not sequence_only and (count_fact is None or not count_fact.was_settled)
        found = FamilyFacts(fact, prefix, short_name(fact.value, prefix), tags, count, plan_only, sequence_only,
                            added, len(listed), was, added_refs, added_up)
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
