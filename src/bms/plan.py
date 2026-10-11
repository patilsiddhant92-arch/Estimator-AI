"""The planner (workstream 2): the job ledger to the Job skeleton (design §4.2, §5 row 2).

Pure, no AI. Reads the old app's Ledger (and the Dossier's source places as a fallback); the Catalogue is taken for
the contract and not needed. The behaviours are those the estimator approved in the old planner:

- one system per family, in ledger order; a group fact is one system (placed where its first member is), reading
  its members with their tags; a part of a family a group lists leaves the rest a system of its own;
- a group whose families each match their own sequence section is not one plant: its families stand alone;
- a VRF group is one system with indoor, condensing and branch-selector families;
- split units no group took are one Split System per sequence section and per same alternate and exception;
  sections whose units share a tag suffix (an indoor unit and its outdoor unit) are one block;
- duct heaters are one system that also carries the sequence of the units they serve;
- a motorized damper linked to a fan (a link fact, or its schedule row naming the fan's tag) moves under that fan;
  dampers no fan claims stay a damper system;
- families of one name (not a general kind alone) are one block; a code the dossier gives no kind joins the family
  it is a tag of; a family with only a general kind for a name is asked what it is, and gives up the tags of other
  families the ledger names by their own kind;
- condensate pumps carrying the tag numbers of one split block's units are planned in that block (their float
  switch tie-in); a condensate pump block never takes the split shape;
- the printed count is the highest; every other count is kept with its source; unknown is None (Qty (##)); the sum
  of the sheets of one floor and area, when ruling L1 left it above the printed count, is kept apart in
  `Count.added_up` (never printed as the count; the proposal's "*" note names both numbers); a family split between
  blocks carries it in none, so one question names both numbers (`added_up_counts`);
- unscheduled and sequence-only families, parts with no count, unmatched sequence sections and the ledger's own
  questions become plain-words questions.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace

from estimator.catalogue.job import Catalogue
from estimator.ledger.facts import Fact, Ledger
from estimator.writing.dossier import Dossier, sections_in

from bms import ai_evidence
from bms.citations import without_ledger_brackets
from bms.model import Count, Family, FrontEnd, Job, Ref, ScopeException, Served, System
from bms.plan_groups import family_of_tag, members, part_count, parts, split_apart, unread
from bms.plan_read import NO_KIND, FamilyFacts, Reader, naming, names_in, squash, tag_words
from bms.playbook import Playbook, Shape

GLOBAL_POINTS = "Global Points"
_GLOBAL_WORDS = re.compile(r"\bglobal\b|\bsystem\s+points\b|\bbuilding[\s-]*wide\b", re.I)
SPLIT_SYSTEM = "Split System"
VRF_SYSTEM = "VRF System"
DUCT_HEATERS = "Duct Heaters"

# The words that tell a kind of equipment; the Playbook's shapes come first wherever they say it.
SPLIT_PREFIXES = frozenset({"CU", "ACCU", "AC", "CAC", "OU", "ODU", "SS", "IU"})
DAMPER_PREFIXES = ("MD",)
_FIRE_SMOKE_PREFIXES = ("FSD", "FD", "SD")
_FIRE_SMOKE_WORDS = re.compile(r"\bfire\s+dampers?\b|\bsmoke\s+dampers?\b|\bfire\s*/\s*smoke\b|\bfire\s+smoke\b", re.I)
_DUCT_HEATER_WORDS = re.compile(r"\b(?:electric\s+)?duct\s+heaters?\b|\bedh\b", re.I)
_VRF_WORDS = re.compile(r"\bvrf\b|\bvrv\b|variable\s+refrigerant", re.I)
_BRANCH_WORDS = re.compile(r"\bbranch\b|\bbc\s+controller\b", re.I)
_INDOOR_WORDS = re.compile(r"\bindoor\b|\bfan\s+coil\b|\bwall\s*mount|\bcassette\b|\bductless\b|\bair\s+handler\b", re.I)
_CONDENSING_WORDS = re.compile(r"\bcondens(?!ate)|\boutdoor\s+unit\b|\bheat\s+pump\s+unit\b", re.I)
_INDOOR_PREFIXES = frozenset({"AC", "IDU", "WAC", "IU", "CAC", "SS", "FCU", "DFCU"})
_CONDENSING_PREFIXES = frozenset({"CU", "ACCU", "ODU", "OU", "HPCU"})
_BRANCH_PREFIXES = frozenset({"BS", "BC", "BSB"})
_ROLE_WORDS = {"indoor": ("indoor",), "condensing": ("condens", "outdoor"), "branch": ("branch", "selector")}
_ROLE_NAMES = {"indoor": "Indoor Unit", "condensing": "Condensing Unit", "branch": "Branch Selector"}
_LONG_NAME_WORDS = 4

_MAKER = re.compile(r"\b(?:unit\s+mfr|manufacturer|factory|oem|packaged|comes?\s+with\s+the\s+unit|"
                    r"furnished\s+with\s+the\s+unit)\b", re.I)
_NOT_MAKER = re.compile(r"\bnot\s+by\b|\bnot\s+the\s+unit\s+mfr", re.I)
_INTEGRATION = re.compile(r"\bbacnet\b|\bmodbus\b|\blonworks\b|\bgateway\b|\bintegrat|\bnetwork\s+interface\b", re.I)
_NO_CONTROLS = re.compile(r"\bnot\s+in\s+contract\b|\bn\.?\s?i\.?\s?c\.?(?![a-z])|\bno\s+(?:bms\s+|ddc\s+)?controls?\b|"
                          r"\bcontrols?\s+(?:are\s+|is\s+)?by\s+others\b", re.I)
_SERVES = re.compile(r"serves?\s+([A-Z][A-Z0-9-]+)")
_NOTE_TOPICS = frozenset({"question", "exception", "alternate"})     # notes about the job, not about a system
_TAG = re.compile(r"^[A-Za-z]{1,6}(?:-[A-Za-z0-9.]+)+$")


# ---- the working form of a system -----------------------------------------------------------------------------


@dataclass
class _Fam:
    """A family as the planner builds it: the model's family plus what it was read from."""
    name: str
    tags: tuple[str, ...]
    count: Count
    source: FamilyFacts | None = None          # None for a damper under its fan when the ledger has no damper family
    moved: bool = False                         # a damper family moved under the system its links name


@dataclass
class _Tie:
    """A unit a duct heater system serves: the unit's system, its tags the documents tie to heaters, the heaters."""
    unit: _Draft
    tags: list[str]
    heaters: list[str]


@dataclass
class _Draft:
    key: str
    name: str
    kind: str                                   # "single", "group", "split", "heaters", "dampers"
    families: list[_Fam]
    prefixes: list[str]
    matches: list[Fact] = field(default_factory=list)
    alternate: str = "base"
    exception: str = ""
    words: str = ""                             # the group's own words (its subject and members)
    extra_refs: list[Ref] = field(default_factory=list)
    ties: list[_Tie] = field(default_factory=list)  # a duct heater system: the units it serves

    def tags(self) -> list[str]:
        return [t for f in self.families for t in f.tags]

    def names(self) -> list[str]:
        """What a fact may call this system: its key, its prefixes, its tags and their prefixes."""
        tags = self.tags()
        names = [self.key, *self.prefixes, *tags, *(t.split("-")[0] for t in tags if "-" in t)]
        return [n for n in dict.fromkeys(squash(n) for n in names) if n]


def _lead(subject: str) -> str:
    """A tag or label's leading token in capitals: "MD-1" and "MD on 88x40 duct" both lead with "MD"."""
    return re.split(r"[\s\-(/,]", squash(subject), maxsplit=1)[0].upper()


# ---- the planner ------------------------------------------------------------------------------------------------


class _Planner:
    def __init__(self, ledger: Ledger, dossier: Dossier | None, playbook: Playbook) -> None:
        self.ledger = ledger
        self.playbook = playbook
        self.reader = Reader(ledger, getattr(dossier, "sources", None) or {}, getattr(dossier, "text", "") or "",
                             getattr(dossier, "families", ()) or ())
        self.dossier = dossier
        self.questions: list[str] = []
        self._texts: dict[str, str] | None = None
        self._damper_prefixes: frozenset[str] | None = None

    def texts(self) -> dict[str, str]:
        """Every dossier source id -> its text (a sequence section: its heading and its paragraphs)."""
        if self._texts is None:
            dossier = self.dossier
            text = str(getattr(dossier, "text", "") or "")
            sections = getattr(dossier, "sections", None) or sections_in(text)
            self._texts = ai_evidence.index(text, dict(getattr(dossier, "sources", None) or {}), dict(sections))
        return self._texts

    # -- shapes and kinds

    def _shape_by_kind(self, *words: str, unless: str = "") -> Shape | None:
        """The first Playbook shape whose name or kind words say every one of `words` (whole words), and not
        `unless`."""
        for shape in self.playbook.shapes.values():
            text = f"{shape.name} {' '.join(shape.kind_words)}".casefold()
            says = all(re.search(rf"\b{re.escape(w)}", text) for w in words)
            if says and not (unless and re.search(rf"\b{re.escape(unless)}\b", text)):
                return shape
        return None

    def split_shape(self) -> Shape | None:
        return self._shape_by_kind("split", unless="vrf")

    def split_prefixes(self) -> frozenset[str]:
        """The split prefixes are the Playbook's split shape's; the constant stands in only while the Playbook
        has no split shape (or one with no prefixes)."""
        shape = self.split_shape()
        return frozenset(shape.prefixes) if shape is not None and shape.prefixes else SPLIT_PREFIXES

    def is_duct_heater(self, family: FamilyFacts) -> bool:
        """A duct heater family: its name says so, or says the kind words of a Playbook shape for duct heaters. Its
        prefix (EDH, or a duct heater shape's prefix) counts only when the name gives no kind of its own: a general
        kind ("Heater", "Unit"), its code, or a heater no other shape's kind words name ("Electric Heater"). A
        Dehumidifier tagged DH is no duct heater (PLN-8)."""
        name = squash(family.name)
        heater_shapes = [s for s in self.playbook.shapes.values()
                         if _DUCT_HEATER_WORDS.search(f"{s.name} {' '.join(s.kind_words)}")]
        if _DUCT_HEATER_WORDS.search(name) or any(_says_kind(s, name) for s in heater_shapes):
            return True
        low = name.casefold()
        general = not low or low in _GENERIC_KINDS or low in (NO_KIND, family.prefix.casefold()) or (
            re.search(r"\bheaters?$", low) is not None and
            not any(_says_kind(s, name) for s in self.playbook.shapes.values() if s not in heater_shapes))
        if not general:
            return False
        if _DUCT_HEATER_WORDS.search(family.prefix):
            return True
        shape = self.playbook.shape_for(family.name, [family.prefix])
        return shape is not None and shape in heater_shapes

    def named_otherwise(self, draft: _Draft) -> bool:
        """A unit with a split unit's prefix whose ledger name says another kind of equipment (the kind words of a
        Playbook shape that is neither the split shape nor a VRF shape, "Air Curtain") and nothing of a split unit
        (the split shape's kind words, "split", an indoor or outdoor unit's words, "air handling" of a ducted indoor
        unit): it is no split unit (PLN-8)."""
        split = self.split_shape()
        for name in (squash(f.source.name) for f in draft.families if f.source is not None):
            if (split is not None and _says_kind(split, name)) or re.search(r"\bsplit\b|\bair\s+handl", name, re.I) or \
                    _INDOOR_WORDS.search(name) or _CONDENSING_WORDS.search(name):
                return False
            if any(_says_kind(s, name) for s in self.playbook.shapes.values()
                   if s is not split and not _VRF_WORDS.search(f"{s.name} {' '.join(s.kind_words)}")):
                return True
        return False

    def damper_shape(self) -> Shape | None:
        return self._shape_by_kind("damper", unless="fire")

    def damper_prefixes(self) -> frozenset[str]:
        """The motorized damper prefixes: every family whose ledger name says "damper" (not a fire or smoke
        damper), and the Playbook's damper shape's prefixes; the constant stands in only while the Playbook has
        no damper shape (or one with no prefixes)."""
        if self._damper_prefixes is None:
            shape = self.damper_shape()
            found = set(shape.prefixes) if shape is not None and shape.prefixes else set(DAMPER_PREFIXES)
            for fact in self.reader.family_facts():
                family = self.reader.family(fact)
                if family.prefix.upper() in _FIRE_SMOKE_PREFIXES or _FIRE_SMOKE_WORDS.search(family.name):
                    continue
                if "damper" in family.name.casefold():
                    found.add(family.prefix.upper())
            self._damper_prefixes = frozenset(found)
        return self._damper_prefixes

    def tag_in(self, subject: str) -> tuple[str, FamilyFacts | None]:
        """The tag a link's subject holds and the family it is a tag of ("CD-1 damper", "(MD-1)" and "MD1" hold
        CD-1, MD-1 and MD-1), read as family_of_tag reads a tag. A damper family's tag comes before another
        family's ("EF-1 damper MD-3" holds MD-3). When the family lists the tag, its own spelling is kept.
        ("", None) when the subject holds no tag of any family."""
        found: list[tuple[str, FamilyFacts]] = []
        for word in re.split(r"[\s,;()\[\]/]+", squash(subject)):
            word = word.strip(".:")
            if not word:
                continue
            tries = [word]
            bare = re.match(r"^([A-Za-z]{1,6})(\d[A-Za-z0-9.]*)$", word)
            if bare:
                tries.append(f"{bare.group(1)}-{bare.group(2)}")
            for tag in tries:
                family = family_of_tag(self.reader, tag)
                if family is not None:
                    key = tag.upper().replace("-", "")
                    found.append((next((t for t in family.tags if t.upper().replace("-", "") == key), tag), family))
                    break
        dampers = self.damper_prefixes()
        return next((f for f in found if f[1].prefix.upper() in dampers), found[0] if found else ("", None))

    def is_damper(self, subject: str) -> bool:
        """A motorized damper's tag or label: it leads with a damper prefix, holds a tag of a damper family, or
        says "damper". A fire or smoke damper is not one (those stay where they are); a smoke purge duct is not a
        smoke damper."""
        text = squash(subject)
        if _lead(text) in _FIRE_SMOKE_PREFIXES or _FIRE_SMOKE_WORDS.search(text):
            return False
        _, family = self.tag_in(text)
        if family is not None and family.prefix.upper() in self.damper_prefixes():
            return True
        return _lead(text) in self.damper_prefixes() or "damper" in text.casefold()

    # -- step 1: families and groups

    def drafts(self) -> list[_Draft]:
        reader = self.reader
        kept = []
        for group in self.ledger.of_kind("group"):
            apart = split_apart(reader, group)
            if apart:
                every = ", ".join(f.prefix for f, _ in members(reader, group))
                name = _group_name(reader, group)
                if self._one_refrigerant_system(group):
                    sections = ", ".join(dict.fromkeys(squash(m.subject) for m in reader.matches(*apart)))
                    self.questions.append(
                        f"The documents group {every} as “{name}”, and its families match separate sequence sections "
                        f"({sections}); a VRF or split system is one block, so it is planned as one block carrying "
                        "each section's sequence. Confirm it is one system.")
                    kept.append(group)
                    continue
                self.questions.append(
                    f"The documents group {every} as “{name}”, but its families match their own sequence sections, "
                    "so each is planned as its own system; confirm they are separate systems.")
                continue
            kept.append(group)
            for piece in unread(reader, group):
                self.questions.append(
                    f"The documents group “{piece}” with “{_group_name(reader, group)}”, but no equipment family "
                    "of the documents is named by it, so it is in no block of this plan. What is it, and is it "
                    "part of this system?")
        claims_of = parts(reader, kept, self.questions)
        drafts: list[_Draft] = []
        placed: set[str] = set()
        no_kind: list[tuple[FamilyFacts, FamilyFacts]] = []
        for fact in reader.family_facts():
            family = reader.family(fact)
            claims = claims_of.get(family.prefix.casefold(), [])
            if not claims and squash(family.name).casefold() == NO_KIND:
                owner = family_of_tag(reader, family.prefix)
                if owner is not None:
                    no_kind.append((reader.rename(family, owner.name), owner))
                    continue
                family = reader.rename(family, family.prefix)
                self.questions.append(
                    f"{family.prefix} is on a schedule with no kind of equipment given for it, and no family of the "
                    f"documents has it as a tag; it is planned as its own block named {family.prefix}. What is it, "
                    "and is it in the BMS scope?")
            for group, _ in claims:
                if group.id not in placed:
                    placed.add(group.id)
                    drafts.append(self._group(group, claims_of))
            rest = self._rest(family, claims)
            if rest is not None:
                drafts.append(rest)
        for family, owner in no_kind:
            self._join_owner(drafts, family, owner)
        return drafts

    def _one_refrigerant_system(self, group: Fact) -> bool:
        """A VRF or split group (the house rule: one system, one block): its words say VRF or a branch selector, or
        its members hold a branch selector or a condensing unit together with an indoor unit (PLN-6). Only a member
        with a split, condensing or branch prefix is read as a condensing unit or a branch selector here: a
        Condensing Boiler with a fan coil is no split system."""
        found = members(self.reader, group)
        words = f"{_group_name(self.reader, group)} {squash(group.value)} " + \
            " ".join(f"{f.prefix} {f.name}" for f, _ in found)
        if _VRF_WORDS.search(words) or _BRANCH_WORDS.search(words):
            return True
        refrigerant = self.split_prefixes() | _CONDENSING_PREFIXES | _BRANCH_PREFIXES
        roles = {role for f, _ in found for role in [self._role(_Fam(f.name, f.tags, f.count, f), words)]
                 if role == "indoor" or _lead(f.prefix) in refrigerant}
        return "indoor" in roles and bool(roles & {"branch", "condensing"})

    def _join_owner(self, drafts: list[_Draft], family: FamilyFacts, owner: FamilyFacts) -> None:
        """A code with no kind of its own that is a tag of another family ("GI-4" of GI) is a part of that family:
        it joins the block holding the family, with its own count, under the family's name, and is asked. A code
        that is already one of the family's own tags (P-1 of P-1, P-2) is not added again; the question says so.
        When the family's count was read from the code's own count, the question says so in either case."""
        head = f"{family.prefix} is on a schedule with no kind of equipment given for it; "
        own = set(family.count.sources)
        taken = owner.count.value is not None and bool(own & set(owner.count.sources))
        if family.prefix.upper() in {t.upper() for t in owner.tags}:
            # when the owner's count is the code's own count, say so: the owner could be that count and more
            # (REVIEW-FINAL4 F5)
            source = (f" The {owner.prefix} count ({owner.count.value}) is taken from {family.prefix}'s own count, "
                      f"so check that it counts every {owner.name} unit, not only {family.prefix}." if taken else "")
            self.questions.append(
                f"{head}it is one of the {owner.name} ({owner.prefix}) tags, so it is counted with the "
                f"{owner.name} units, not again.{source} Confirm it is one of them.")
            return
        draft = self._holding(drafts, owner)
        if draft is None:
            drafts.append(self._single(family))
        else:
            draft.families.append(_Fam(family.name, family.tags or (family.prefix,), family.count, family))
            draft.prefixes.append(family.prefix)
            draft.matches += [m for m in self.reader.matches(family.prefix) if m not in draft.matches]
        if taken:
            said = (f"The {owner.prefix} count ({owner.count.value}) is taken from {family.prefix}'s own count, so it "
                    f"already includes {family.prefix}. Confirm {family.prefix} is one of them and that the "
                    f"{owner.prefix} count is right.")
        else:
            said = f"Confirm it is one, and that its count is not already in the {owner.prefix} count."
        self.questions.append(
            f"{head}its code is a tag of {owner.name} ({owner.prefix}), so it is planned with the {owner.name} "
            f"units. {said}")

    def specific_name(self, family: FamilyFacts) -> str:
        """The family's name; for a generic kind ("Fan", "Unit", "Equipment") the best specific words the ledger
        holds: its sequence section's title, else the place its tags are on, cut to at most six words with no tag
        text, in Title Case, the kind word added when the words lack it. The kind alone when nothing specific."""
        kind = squash(family.name)
        if kind.casefold() not in _GENERIC_KINDS:
            return family.name
        kind_word = _singular(kind.split()[-1]).casefold()
        for match in self.reader.matches(family.prefix):
            words = _specific_words(match.subject, family, cut_place=False)
            if words:
                return _with_kind(words, kind, kind_word)
        own = {t.casefold() for t in family.tags} | {family.prefix.casefold()}
        for fact in self.ledger.of_kind("location"):
            named = [t for t in re.findall(r"[A-Za-z]{1,6}-[A-Za-z0-9.\-]+", squash(fact.subject))]
            if not named or not all(t.casefold() in own or _lead(t) == family.prefix.upper() for t in named):
                continue
            words = _specific_words(fact.value, family, cut_place=True)
            if words:
                return _with_kind(words, kind, kind_word)
        return family.name

    def _single(self, family: FamilyFacts) -> _Draft:
        reader = self.reader
        name = self.specific_name(family)
        return _Draft(key=family.prefix, name=name, kind="single",
                      families=[_Fam(name, family.tags, family.count, family)], prefixes=[family.prefix],
                      matches=reader.matches(family.prefix), alternate=reader.alternate(family.prefix),
                      exception=reader.exception(family.prefix))

    def _group(self, group: Fact, claims_of: dict) -> _Draft:
        reader = self.reader
        name = _group_name(reader, group)
        families: list[_Fam] = []
        for fact in reader.family_facts():
            family = reader.family(fact)
            for owner, tags in claims_of.get(family.prefix.casefold(), []):
                if owner is not group:
                    continue
                if tags is None:
                    families.append(_Fam(family.name, family.tags, family.count, family))
                    continue
                number, used = part_count(reader, family, tags, group)
                if number is None:
                    count = Count(None)
                    self.questions.append(
                        f"How many {family.prefix} units does “{name}” take ({tag_words(tags)})? No sheet gives "
                        "their count, so the block reads Qty (##).")
                elif used:
                    count = Count(number, tuple(dict.fromkeys(reader.fact_ref(f) for f in used)))
                else:
                    count = _reduced(family.count, number)       # one per tag; _rest asks with both numbers
                families.append(_Fam(family.name, tags, count, family))
        prefixes = [f.source.prefix for f in families if f.source is not None]
        member_words = " ".join(f"{f.prefix} {f.name}" for f, _ in members(reader, group))
        said = squash(group.subject)
        named = (said,) if said else ()
        return _Draft(key=name, name=name, kind="group", families=families, prefixes=list(dict.fromkeys(prefixes)),
                      matches=reader.matches(*named, *prefixes), alternate=reader.alternate(*named, *prefixes),
                      exception=reader.exception(*named, *prefixes),
                      words=f"{name} {squash(group.value)} {member_words}")

    def _rest(self, family: FamilyFacts, claims: list) -> _Draft | None:
        """The family as a system of its own: whole when no group took it; the tags no group listed when groups
        took parts of it, its count the family's less the parts' when both are known and at least one per
        remaining tag is left, else the family's count unchanged (never undershoot). None when groups took it
        all. A count made smaller here (the rest's, or a part's counted one per tag from the family's count) is
        asked, naming the family's numbers and each part's, so both numbers are always in front of the estimator."""
        draft = self._single(family)
        if not claims:
            return draft
        if any(tags is None for _, tags in claims):
            return None
        taken = {t.upper() for _, tags in claims for t in tags}
        left = tuple(t for t in family.tags if t.upper() not in taken)
        count = family.count
        results = [part_count(self.reader, family, tags, group) for group, tags in claims]
        numbers = [n for n, _ in results]
        new = None
        if left and count.value is not None and None not in numbers and count.value - sum(numbers) >= len(left):
            new = count.value - sum(numbers)
        from_family = any(n is not None and not used for n, used in results)
        if count.value is not None and (new is not None or from_family):
            parts_said = "; ".join(
                f"“{_group_name(self.reader, group)}” takes {n if n is not None else 'an unknown number'} "
                f"({tag_words(tags)})" for (group, tags), n in zip(claims, numbers))
            if not left:
                rest = ""
            elif new is not None:
                rest = f", so the rest ({tag_words(left)}) prints {new}"
            else:
                rest = f"; the rest ({tag_words(left)}) keeps {count.value}, as no smaller count is sure"
            self.questions.append(f"{family.name} ({family.prefix}): {_came_from(count, new or 0)}; {parts_said}"
                                  f"{rest}. Confirm the counts.")
        if not left:
            return None
        if new is not None:
            count = _reduced(count, new)
        draft.families = [_Fam(family.name, left, count, family)]
        return draft

    # -- step 1b: a block named only by a general kind keeps no tag another family owns

    def general_kind_tags(self, drafts: list[_Draft]) -> None:
        """A single block whose ledger name is only a general kind ("Pump") gives up each tag of another prefix
        whose own family the ledger names by a kind of its own ("SPX-1" of a Sump Pump family): that family's block
        holds it, so no tag is in two blocks. The count drops by the tags given up only when it is one per tag;
        else it is kept (never undershoot). A question names the tags and where they are."""
        for draft in drafts:
            if draft.kind != "single" or len(draft.families) != 1:
                continue
            fam = draft.families[0]
            source = fam.source
            if source is None or squash(source.name).casefold() not in _GENERIC_KINDS:
                continue
            moved: dict[str, list[str]] = {}
            for tag in fam.tags:
                owner = family_of_tag(self.reader, tag)
                if owner is None or owner.prefix.casefold() == source.prefix.casefold():
                    continue
                kind = squash(owner.name).casefold()
                if kind in _GENERIC_KINDS or kind == NO_KIND or tag.upper() not in {t.upper() for t in owner.tags}:
                    continue
                moved.setdefault(owner.name, []).append(tag)
            if not moved:
                continue
            gone = {t for tags in moved.values() for t in tags}
            left = tuple(t for t in fam.tags if t not in gone)
            count = fam.count
            if count.value is not None and count.value == len(fam.tags):
                said = f"its count is {len(left)}, one per tag left, from {_came_from(count, len(left))}"
                count = _reduced(count, len(left))
            else:
                said = (f"its count of {count.value} is kept as the documents give it; confirm it does not include "
                        "them" if count.value is not None else "its count is not known")
            fam.tags, fam.count = left, count
            where = "; ".join(f"{', '.join(tags)} in the {name} block" for name, tags in moved.items())
            self.questions.append(
                f"{draft.name} ({source.prefix}) has only the general name “{source.name}”, and its list also gives "
                f"tags of other families the documents name by their own kind: {where}. They are planned there "
                f"only, not twice; {said}.")

    # -- step 2: split units

    def gather_splits(self, drafts: list[_Draft]) -> list[_Draft]:
        """The split units no group took become one Split System block; one per sequence section when their
        matches name two or more sections (a unit matched to none joins the block sharing a tag suffix with it,
        else the first). Only units with the same alternate and the same exception share a block. A lone unit
        stays on its own."""
        prefixes = self.split_prefixes()
        loose = [d for d in drafts if d.kind == "single" and _lead(d.key) in prefixes and not self.named_otherwise(d)]
        out, used = list(drafts), set()
        for alternate, exception in dict.fromkeys((d.alternate, d.exception) for d in loose):
            alike = [d for d in loose if (d.alternate, d.exception) == (alternate, exception)]
            for name, block in self._split_blocks(alike, drafts).items():
                if len(block) < 2:
                    continue
                if alternate != "base":
                    name = f"{name} ({alternate} alternate)"
                number, base = 2, name
                while name in used:
                    name, number = f"{base} {number}", number + 1
                used.add(name)
                merged = _Draft(key=name, name=name, kind="split", families=[f for d in block for f in d.families],
                                prefixes=list(dict.fromkeys(p for d in block for p in d.prefixes)),
                                matches=list(dict.fromkeys(m for d in block for m in d.matches)),
                                alternate=alternate, exception=exception)
                out[out.index(block[0])] = merged
                out = [d for d in out if d not in block[1:]]
        return self._condensate_pumps(out, prefixes)

    def _condensate_pumps(self, drafts: list[_Draft], prefixes: frozenset[str]) -> list[_Draft]:
        """Condensate pumps whose tags carry the numbers of one split block's units (CP-21 with AC-21 and ACCU-21)
        are planned in that block, never as a block of their own: the house rule writes their float switch tie-in
        in the split / VRF block, furnished by the mechanical contractor (ame_practice.txt, VRF SYSTEMS and
        OWNERSHIP ANSWERS (3)). Pumps that share only some numbers, or numbers of two blocks, stay apart and are
        asked. Each move is asked to be confirmed."""
        splits = [d for d in drafts if d.kind == "split" or (d.kind == "single" and _lead(d.key) in prefixes
                                                              and not self.named_otherwise(d))]
        out = list(drafts)
        for pump in [d for d in drafts if d.kind == "single" and _lead(d.key) not in prefixes and _is_condensate(d)]:
            mine = _family_suffixes(pump.families)
            if not mine:
                continue
            sharing = [d for d in splits if d.alternate == pump.alternate and mine & _family_suffixes(d.families)]
            if not sharing:
                continue
            label = f"{pump.name} ({tag_words(pump.tags())})"
            whole = len(sharing) == 1 and mine <= _family_suffixes(sharing[0].families) and \
                len(mine) == len(pump.tags())
            if not whole:
                self.questions.append(
                    f"{label} share some tag numbers with the split units of {', '.join(d.name for d in sharing)}, "
                    "but not all of them with one block, so they are planned as a block of their own. Are they the "
                    "condensate pumps of those split units? If so, their float switch tie-in (Furnished by "
                    "Mechanical Contractor) belongs in the split block.")
                continue
            block = sharing[0]
            # numbers alone are weak evidence: other equipment carrying the pumps' numbers is named as the other
            # possibility (FINAL-D F6)
            others = [d for d in drafts if d is not pump and d not in splits and not _is_condensate(d)
                      and _makes_condensate(d) and mine & _family_suffixes(d.families)]
            if others:
                alternative = (f"They could instead be the pumps of the "
                               f"{' or the '.join(f'{d.name} ({tag_words(d.tags())})' for d in others)}, which "
                               "carry the same numbers; if so, they belong in that block instead.")
            else:
                alternative = "If they serve other equipment, they belong with that equipment instead."
            block.families += pump.families
            block.prefixes += [p for p in pump.prefixes if p not in block.prefixes]
            block.matches += [m for m in pump.matches if m not in block.matches]
            out.remove(pump)
            self.questions.append(
                f"{label} carry the tag numbers of the split units of {block.name}, so they are planned in that "
                "block for the condensate pump float switch tie-in (Furnished by Mechanical Contractor), as the "
                "house rule for split and VRF systems writes it. Confirm each pump serves the split unit with its "
                f"number. {alternative}")
        return out

    def _split_blocks(self, loose: list[_Draft], drafts: list[_Draft]) -> dict[str, list[_Draft]]:
        if len(loose) < 2:
            return {}
        section = {id(d): next((squash(m.subject) for m in d.matches), "") for d in loose}
        names = list(dict.fromkeys(n for n in section.values() if n))
        if len(names) < 2:
            return {SPLIT_SYSTEM: loose}
        by_section = {n: [d for d in loose if section[id(d)] == n] for n in names}
        for draft in (d for d in loose if not section[id(d)]):
            mine = _suffixes(draft)
            near = next((n for n in names if mine & set().union(*map(_suffixes, by_section[n]))), names[0])
            by_section[near].append(draft)
        # an indoor unit and its outdoor unit are one block (house rule "VRF and split as one block"): two sections
        # are one block only when every unit of the smaller pairs by tag suffix with a unit of the other role in the
        # other (indoor AC-109 with outdoor ACCU-109, the roles read from the ledger's kind names) and none pairs
        # inside its own section; the join is asked. Sections sharing some numbers but not so (both numbering from
        # 1, or both indoor units only) stay apart and are asked (FINAL-D F2, REVIEW-FINAL4 F3).
        joined: list[list[str]] = [[n] for n in names]
        units = lambda names_: {(_split_role(d), s)  # noqa: E731
                                for n in names_ for d in by_section[n] for s in _suffixes(d)}
        merging = True
        while merging:
            merging = False
            for a in range(len(joined)):
                for b in range(a + 1, len(joined)):
                    if _pair_up(units(joined[a]), units(joined[b])):
                        self.questions.append(
                            f"The split units of {' and '.join(joined[a] + joined[b])} pair up by tag number (each "
                            "indoor unit with the outdoor unit of its number), so they are planned as one Split "
                            "System block carrying each section's sequence. Confirm they are one system.")
                        joined[a] += joined.pop(b)
                        merging = True
                        break
                if merging:
                    break
        for a in range(len(joined)):
            for b in range(a + 1, len(joined)):
                shared = {s for _, s in units(joined[a])} & {s for _, s in units(joined[b])}
                if shared:
                    self.questions.append(
                        f"The split units of {' and '.join(joined[a])} and of {' and '.join(joined[b])} share tag "
                        f"numbers ({', '.join(sorted(shared, key=_natural_key))}), but they do not pair up as one "
                        "indoor unit and its outdoor unit each, so they are planned as two Split System blocks, one "
                        "for each sequence. Are any of them one split system?")
        if len(joined) == 1:
            return {SPLIT_SYSTEM: sorted(loose, key=drafts.index)}
        return {f"{SPLIT_SYSTEM} — {' / '.join(group)}": sorted((d for n in group for d in by_section[n]),
                                                                  key=drafts.index)
                for group in joined}

    # -- step 3: duct heaters in one place

    def gather_heaters(self, drafts: list[_Draft]) -> list[_Draft]:
        """Every duct heater family no group took is in one Duct Heaters system (one per alternate)."""
        heaters = [d for d in drafts if d.kind == "single" and self.is_duct_heater(d.families[0].source)]
        out = list(drafts)
        for alternate in dict.fromkeys(d.alternate for d in heaters):
            block = [d for d in heaters if d.alternate == alternate]
            if len(block) == 1:
                block[0].kind = "heaters"
                continue
            name = DUCT_HEATERS if alternate == "base" else f"{DUCT_HEATERS} ({alternate} alternate)"
            merged = _Draft(key=name, name=name, kind="heaters", families=[f for d in block for f in d.families],
                            prefixes=list(dict.fromkeys(p for d in block for p in d.prefixes)),
                            matches=list(dict.fromkeys(m for d in block for m in d.matches)), alternate=alternate,
                            exception=next((d.exception for d in block if d.exception), ""))
            out[out.index(block[0])] = merged
            out = [d for d in out if d not in block[1:]]
        return out

    def heater_sequences(self, drafts: list[_Draft]) -> None:
        """A duct heater system reads the sequence of the units it serves: their sequence matches join its own. It
        keeps the units it serves (with their tags and the heaters serving them) for the served list of each."""
        for heater in (d for d in drafts if d.kind == "heaters"):
            heater.ties = self._served(heater, drafts)
            for tie in heater.ties:
                heater.matches += [m for m in tie.unit.matches if m not in heater.matches]

    def _served(self, heater: _Draft, drafts: list[_Draft]) -> list[_Tie]:
        """The units the heater system serves, in plan order, from: a link between a heater and a unit; a provider or
        note about the heaters that says "serves <unit>"; a note about the heaters naming a unit; a location naming
        heater tags and a unit; a note about a unit that speaks of its duct heater; a unit whose sequence section
        speaks of a duct heater."""
        names = heater.names()
        found: list[tuple[str, str]] = []                # (the text naming the unit, the text naming the heaters)
        for fact in self.ledger.of_kind("link"):
            subject, value = squash(fact.subject), squash(fact.value)
            if names_in(names, subject) and not names_in(names, value):
                found.append((value, subject))
            elif names_in(names, value) and not names_in(names, subject):
                found.append((subject, value))
        for fact in self.ledger.of_kind("provider"):
            if names_in(names, fact.subject):
                found += [(unit, squash(fact.subject)) for unit in _SERVES.findall(squash(fact.value))]
        for fact in self.ledger.of_kind("note"):
            subject, value = squash(fact.subject), squash(fact.value)
            if subject.casefold() in _NOTE_TOPICS:
                continue
            if names_in(names, subject):
                found.append((value, f"{subject} {value}"))
            elif _DUCT_HEATER_WORDS.search(value) or _heaters_named(heater, value):
                found.append((subject, value))
        for fact in self.ledger.of_kind("location"):
            text = f"{squash(fact.subject)} {squash(fact.value)}"
            if _heaters_named(heater, text):
                found.append((text, text))
        named = [(_units_named(drafts, heater, unit_text), _heaters_named(heater, heater_text))
                 for unit_text, heater_text in found]
        for unit in drafts:
            if unit is heater or unit.kind in ("heaters", "global"):
                continue
            for match in unit.matches:
                text = self.texts().get(match.source_id, "")
                if _DUCT_HEATER_WORDS.search(text) or _heaters_named(heater, text):
                    named.append(([(unit, unit.tags())], _heaters_named(heater, text)))
        ties: dict[int, _Tie] = {}
        for units, heaters in named:
            for unit, tags in units:
                tie = ties.setdefault(id(unit), _Tie(unit, [], []))
                tie.tags += [t for t in tags if t not in tie.tags]
                tie.heaters += [t for t in heaters if t not in tie.heaters]
        out = sorted(ties.values(), key=lambda t: drafts.index(t.unit))
        for tie in out:
            tie.tags = [t for t in tie.unit.tags() if t in tie.tags]
            tie.heaters = [t for t in heater.tags() if t in tie.heaters]
        return out

    # -- step 4: dampers under their fan

    def link_dampers(self, drafts: list[_Draft]) -> list[_Draft]:
        """A motorized damper linked to a fan (or any other system) moves under it: that system takes a damper
        family whose count is its links, each link a source. The damper family, alone or in a group, keeps only
        the dampers no system claims; when every damper is claimed it is gone. The dampers no fan claims stay a
        damper system citing the sheets that show them, and a question says the total.

        A damper's link is a ledger link fact, or, for a damper tag no link fact names, its row of a schedule in the
        dossier whose other cells name the tag of exactly one other system (the row is the link's source)."""
        prefixes = self.damper_prefixes()
        damper_keys = {d.key.upper() for d in drafts if d.kind == "single" and d.key.upper() in prefixes}
        grouped = {f.source.prefix.upper() for d in drafts if d.kind != "single" for f in d.families
                   if f.source is not None and f.source.prefix.upper() in prefixes}
        claims: dict[int, dict[str, list[Fact]]] = {}      # target draft -> damper prefix -> links
        links_of: dict[str, list[Fact]] = {}               # damper prefix -> links
        found: list[tuple[Fact, _Draft]] = []
        for link in self.ledger.of_kind("link"):
            subject = squash(link.subject)
            if not self.is_damper(subject):
                continue
            value = squash(link.value)
            target = next(iter(_named([d for d in drafts if d.key.upper() not in damper_keys], value, prefixes)),
                          None)
            if target is not None:
                found.append((link, target))
        linked = {squash(link.subject).upper() for link, _ in found}
        found += self._schedule_links(drafts, damper_keys | grouped, linked)
        for link, target in found:
            # a link holding a tag of a damper family is that family's; only a link with no such tag falls back
            # to its leading word, and then to the damper family when there is only one
            subject = squash(link.subject)
            _, family = self.tag_in(subject)
            prefix = family.prefix.upper() if family is not None and family.prefix.upper() in prefixes else ""
            if not prefix:
                prefix = _lead(subject)
                every = damper_keys | grouped
                if prefix not in every and len(every) == 1:
                    prefix = next(iter(every))
            claims.setdefault(id(target), {}).setdefault(prefix, []).append(link)
            links_of.setdefault(prefix, []).append(link)
        if not claims:
            return drafts
        out: list[_Draft] = []
        for draft in drafts:
            if draft.kind != "single":
                draft.families = self._less_dampers(draft, links_of, drafts, claims)
            if id(draft) in claims:
                for prefix, links in claims[id(draft)].items():
                    draft.families.append(self._damper_family(prefix, links))
                    own = next((d for d in drafts if d.kind == "single" and d.key.upper() == prefix), None)
                    if own is not None:
                        draft.matches += [m for m in own.matches if m not in draft.matches]
            elif draft.kind == "single" and draft.key.upper() in links_of:
                draft = self._unclaimed(draft, links_of[draft.key.upper()], drafts, claims)
                if draft is None:
                    continue
            out.append(draft)
        return out

    def _damper_family(self, prefix: str, links: list[Fact]) -> _Fam:
        family = self.reader.family_by_prefix(prefix)
        name = family.name if family is not None else "Motorized Damper"
        tags = tuple(dict.fromkeys(t for t in (self.link_tag(l) for l in links) if t))
        return _Fam(name, tags, Count(len(links), tuple(dict.fromkeys(self.reader.fact_ref(l) for l in links))),
                    family, moved=True)

    def link_tag(self, link: Fact) -> str:
        """The damper tag a link names: the damper family's tag its subject holds, else the subject when it is a
        tag itself. A fan's tag in the subject ("damper at EF-1") is not the damper's."""
        tag, family = self.tag_in(link.subject)
        if family is not None and family.prefix.upper() in self.damper_prefixes():
            return tag
        subject = squash(link.subject)
        return subject if _TAG.match(subject) else ""

    def _schedule_links(self, drafts: list[_Draft], damper_prefixes: set[str],
                        linked: set[str]) -> list[tuple[Fact, _Draft]]:
        """The dossier's schedule rows that tie a damper to its system: a row whose first cell is a damper tag of
        the plan (one no link fact already places) and whose other cells name a tag of exactly one other system.
        Each becomes a link (the row's source id, its words as the quote). Only whole tags count: a prefix or key
        in a cell ("24V AC") names nothing."""
        text = str(getattr(self.dossier, "text", "") or "")
        if not text or not damper_prefixes:
            return []
        others = [d for d in drafts if d.key.upper() not in damper_prefixes]
        out: list[tuple[Fact, _Draft]] = []
        for entry in ai_evidence.parse(text):
            if entry.part != ai_evidence.SCHEDULES or not entry.sid:
                continue
            body = entry.body.split("\n", 1)[0]
            if "|" not in body:
                continue
            first, rest = (squash(c) for c in body.split("|", 1))
            tag = squash(re.sub(r"\(EXISTING\)", "", first, flags=re.I))
            if not _TAG.match(tag) or _lead(tag) not in damper_prefixes or not self.is_damper(tag) \
                    or tag.upper() in linked:
                continue
            named = [d for d in others if any(naming(t).search(rest) for t in d.tags())]
            if len(named) != 1:
                continue
            linked.add(tag.upper())
            out.append((Fact(f"{entry.sid}:link", "link", tag, rest, entry.sid, squash(body), "schedules"), named[0]))
        return out

    def _less_dampers(self, draft: _Draft, links_of: dict[str, list[Fact]], drafts: list[_Draft],
                      claims: dict) -> list[_Fam]:
        """A group's damper families less the dampers a fan claims; a count made smaller is asked, with both
        numbers."""
        kept = []
        for fam in draft.families:
            prefix = fam.source.prefix.upper() if fam.source is not None and not fam.moved else ""
            links = links_of.get(prefix, []) if prefix else []
            if links and fam.count.value is not None:
                left = fam.count.value - len(links)
                if left <= 0:
                    continue
                claimed = {self.link_tag(l).upper() for l in links}
                tags = tuple(t for t in fam.tags if t.upper() not in claimed)
                owners = [d.key for d in drafts if id(d) in claims and prefix in claims[id(d)]]
                self.questions.append(
                    f"{fam.name} ({fam.source.prefix}) in {draft.name}: {_came_from(fam.count, left)}; {len(links)} "
                    f"{'is' if len(links) == 1 else 'are'} planned under {'its' if len(links) == 1 else 'their'} fan "
                    f"in {', '.join(owners) or 'another block'}, so the {draft.name} block keeps {left}"
                    f"{f' ({tag_words(tags)})' if tags else ''}. Confirm the count.")
                fam = _Fam(fam.name, tags, _reduced(fam.count, left), fam.source)
            kept.append(fam)
        return kept

    def _unclaimed(self, draft: _Draft, links: list[Fact], drafts: list[_Draft], claims: dict) -> _Draft | None:
        family = draft.families[0]
        total = family.count.value
        claimed_tags = {self.link_tag(l).upper() for l in links}
        locations = [f for f in self.ledger.of_kind("location") if naming(draft.key).search(squash(f.subject))]
        refs = tuple(dict.fromkeys([*family.count.sources, *(self.reader.fact_ref(f) for f in locations + links)]))
        sheets = list(dict.fromkeys(r.where.split(",")[0].strip() for r in refs if r.where))
        owners = [d.key for d in drafts if id(d) in claims and draft.key.upper() in claims[id(d)]]
        if total is not None:
            left = total - len(links)
            if left <= 0:
                return None
            count = _reduced(family.count, left)
            also = _also(family.count, left)
            self.questions.append(
                f"{family.name} ({draft.key}): {left} of the {total} are linked to no fan"
                f"{f' (the documents also give {also})' if also else ''}; {len(links)} are "
                f"under {', '.join(owners)}. Which equipment do the other {left} serve? "
                f"See {', '.join(sheets) or 'the plans'}.")
        else:
            count = Count(None, family.count.sources)
            self.questions.append(
                f"{family.name} ({draft.key}): how many are there in all? {len(links)} are under "
                f"{', '.join(owners)}; the rest are linked to no fan. See {', '.join(sheets) or 'the plans'}.")
        draft.kind = "dampers"
        draft.families = [_Fam(family.name, tuple(t for t in family.tags if t.upper() not in claimed_tags), count,
                               family.source)]
        return draft

    # -- step 5: the systems

    def system(self, draft: _Draft, keys: set[str], drafts: list[_Draft]) -> System:
        vrf = draft.kind == "group" and self._is_vrf(draft)
        if draft.kind == "split":
            # by kind words only: a split unit's prefix (CU, AC) may also be a VRF shape's, and a split block
            # never takes the VRF shape
            shape = self.split_shape() or self.playbook.shape_for(SPLIT_SYSTEM, ())
        elif vrf:
            shape = self._shape_by_kind("vrf") or self.playbook.shape_for(VRF_SYSTEM, draft.prefixes)
        elif draft.kind == "heaters":
            shape = self._shape_by_kind("duct heater") or self.playbook.shape_for(draft.name, draft.prefixes)
        elif draft.kind == "global":
            shape = self._shape_by_kind("global")
        else:
            shape = self.playbook.shape_for(draft.name, draft.prefixes)
            if shape is not None and self._refused_by_name(draft, shape):
                # a block the planner did not gather by its prefix takes the shape its name gives, or none: an Air
                # Curtain tagged AC is no Split System, a Dehumidifier tagged DH no Duct Heater (PLN-8)
                shape = self.playbook.shape_for(draft.name, [])
            if shape is not None and shape is self.split_shape() and _all_condensate(draft):
                # a pump block's name may say "split ac"; it is no split unit. A lone split unit its pumps joined
                # keeps the shape (PLN-7)
                shape = None
        families = draft.families
        if vrf or draft.kind == "split":
            families = [self._role_named(f, draft, shape, vrf) for f in families]
        key, number = draft.key, 2
        while key in keys:
            key, number = f"{draft.key} {number}", number + 1
        keys.add(key)
        refs = [self.reader.fact_ref(m) for m in draft.matches] + draft.extra_refs
        name = _one(draft.name) if _is_one(families) else draft.name
        return System(key=key, name=name, shape=shape.name if shape is not None else "",
                      control=self._control(draft, vrf, drafts),
                      families=tuple(Family(_one(f.name) if _is_one([f]) else f.name, tuple(f.tags), f.count)
                                     for f in families),
                      sequence_refs=tuple(dict.fromkeys(refs)), alternate=draft.alternate)

    def _refused_by_name(self, draft: _Draft, shape: Shape) -> bool:
        """The prefix picked a shape the planner's gathering refused the block by its name: the split shape for a
        unit named otherwise (`named_otherwise`), or a duct heater shape for a block with no duct heater family
        (`is_duct_heater`)."""
        if shape is self.split_shape() and _lead(draft.key) in self.split_prefixes() and self.named_otherwise(draft):
            return True
        heater = _DUCT_HEATER_WORDS.search(f"{shape.name} {' '.join(shape.kind_words)}") is not None
        sources = [f.source for f in draft.families if f.source is not None]
        return heater and bool(sources) and not any(self.is_duct_heater(s) for s in sources)

    def _role(self, fam: _Fam, words: str) -> str:
        source = fam.source
        prefix = _lead(source.prefix) if source is not None else ""
        name = fam.name
        if _CONDENSATE.search(name):
            return ""                                   # a condensate pump is no indoor, outdoor or branch unit
        says_vrf =_VRF_WORDS.search(f"{words} {name}") or _BRANCH_WORDS.search(f"{words} {name}")
        if re.search(r"branch\s+(?:selector|controller|box)|\bbc\s+controller\b|\bselector\s+box", name, re.I) \
                or prefix in _BRANCH_PREFIXES or (prefix == "HRU" and says_vrf):
            return "branch"
        if _INDOOR_WORDS.search(name):
            return "indoor"
        if _CONDENSING_WORDS.search(name):
            return "condensing"
        if prefix in _INDOOR_PREFIXES:
            return "indoor"
        if prefix in _CONDENSING_PREFIXES:
            return "condensing"
        return ""

    def _is_vrf(self, draft: _Draft) -> bool:
        if _VRF_WORDS.search(draft.words):
            return True
        return any(self._role(f, draft.words) == "branch" for f in draft.families)

    def _role_named(self, fam: _Fam, draft: _Draft, shape: Shape | None, vrf: bool) -> _Fam:
        """A VRF family takes its role's name (the shape's family name for it, else the plain role word); a split
        unit keeps the document's name unless it is a long description."""
        role = self._role(fam, draft.words)
        if not role:
            return fam
        if not vrf and len(fam.name.split()) <= _LONG_NAME_WORDS:
            return fam
        names = shape.family_names if shape is not None else ()
        word = next((n for n in names if any(w in n.casefold() for w in _ROLE_WORDS[role])), _ROLE_NAMES[role])
        return replace(fam, name=word)

    def _control(self, draft: _Draft, vrf: bool, drafts: list[_Draft]) -> str:
        """packaged when a provider fact about the system says the unit maker or the factory controls it;
        integration when one says the BMS integrates it (or the system is a VRF group and none says otherwise);
        none when one says no controls are in the contract; else field. Global points are integration. A provider
        fact naming a tag is about the system holding that tag only (`_named`, PLN-4)."""
        if draft.kind == "global":
            return "integration"
        found = [squash(f.value) for f in self.ledger.of_kind("provider")
                 if any(d is draft for d in _named(drafts, f.subject))]
        if any(_MAKER.search(v) and not _NOT_MAKER.search(v) for v in found):
            return "packaged"
        if any(_INTEGRATION.search(v) for v in found):
            return "integration"
        if any(_NO_CONTROLS.search(v) for v in found):
            return "none"
        return "integration" if vrf else "field"

    # -- step 4b: units seen on the drawings but on no schedule join their family's system

    def place_seen(self, drafts: list[_Draft]) -> None:
        """Each tag the ledger records as seen on the drawings but on no family's tag list, and in no system yet,
        joins the system holding its family (the family whose prefix it starts with; the system holding the
        family's rest before a group's part), as a part of that family counted one per tag from the drawings; it
        asks for confirmation where it lands. Tags no family owns are asked, never dropped."""
        held = {t.upper() for d in drafts for t in d.tags()}
        found: dict[tuple[int, str], list[tuple[str, Ref]]] = {}
        owners: dict[str, FamilyFacts] = {}
        orphans: list[tuple[str, Ref]] = []
        for tag, ref in self.reader.seen_tags():
            if tag.upper() in held:
                continue
            family = family_of_tag(self.reader, tag)
            draft = self._holding(drafts, family) if family is not None else None
            if draft is None:
                orphans.append((tag, ref))
                continue
            owners[family.prefix] = family
            found.setdefault((id(draft), family.prefix), []).append((tag, ref))
            held.add(tag.upper())
        for draft in drafts:
            for (key, prefix), seen in found.items():
                if key != id(draft):
                    continue
                family = owners[prefix]
                tags = tuple(t for t, _ in seen)
                count = Count(len(tags), tuple(dict.fromkeys(r for _, r in seen)))
                draft.families.append(_Fam(self.specific_name(family), tags, count,
                                           replace(family, plan_only=True, sequence_only=False)))
        if orphans:
            sheets = list(dict.fromkeys(r.where.split(",")[0].strip() for _, r in orphans if r.where))
            self.questions.append(
                f"Equipment tagged {', '.join(t for t, _ in orphans)} is seen on the drawings but on no schedule, "
                f"and no scheduled family has its prefix; which system is it in, and is it in the BMS scope? "
                f"See {', '.join(sheets) or 'the plans'}.")

    @staticmethod
    def _holding(drafts: list[_Draft], family: FamilyFacts) -> _Draft | None:
        holding = [d for d in drafts for f in d.families
                   if f.source is not None and f.source.prefix == family.prefix and not f.moved]
        return next((d for d in holding if d.kind != "group"), holding[0] if holding else None)

    # -- tags a later pass added to a family's list

    def added_tags(self) -> None:
        """Each family whose tag list a later pass contradicted with tags the list lacks (the plans show EF-4
        where the schedule lists EF-1 thru 3) keeps those tags (the Reader joins both lists) and is asked once,
        naming both numbers: how many the list gives and how many were counted. A family whose own list gives more
        unit tags than its count (the list is EF-1 thru 5, the count 3: the plans' range is in the list) is asked
        once too, naming the count, the tags beyond it and the count raised to one per tag (HP 7)."""
        for fact in self.reader.family_facts():
            family = self.reader.family(fact)
            if not family.added and not family.beyond:
                continue
            unit = self.reader.ledger.find("unit", family.prefix)
            if not family.added:
                said = next((o for o in family.count.others if o.value == family.was), None)
                self.questions.append(
                    f"{family.name} ({family.prefix}): {_places((self.reader.fact_ref(unit),))} lists "
                    f"{family.count.value} ({squash(unit.value)}), but the count is {family.was} per "
                    f"{_places((said.ref,)) if said else 'the documents'}; {', '.join(family.beyond)} "
                    f"{'is' if len(family.beyond) == 1 else 'are'} beyond that count; counted {family.count.value} "
                    f"(the count gave {family.was}), confirm the count.")
                continue
            head = (f"{family.name} ({family.prefix}): {_places((self.reader.fact_ref(unit),))} lists "
                    f"{family.listed} ({squash(unit.value)}); {', '.join(family.added)} "
                    f"{'is' if len(family.added) == 1 else 'are'} also on {_places(family.added_refs)}")
            if family.count.value is None:
                self.questions.append(f"{head}; no count is known (Qty (##)): how many are there?")
            elif family.was is not None and family.count.value != family.was:
                self.questions.append(f"{head}; counted {family.count.value} (the count gave {family.was}), "
                                      "confirm the count.")
            else:
                self.questions.append(f"{head}; counted {family.count.value}, confirm the count includes "
                                      f"{', '.join(family.added)}.")

    # -- counts ruling L1 made lower than the plan sheets add up to

    def added_up_counts(self, systems: list[System], drafts: list[_Draft]) -> None:
        """Each family whose printed count is below a sum ruling L1 left out of it is asked once, naming both numbers
        and where each is: a drop from the sum is never silent. Two sums can be left out of a family's count. The
        counts stated for its tags on the plan sheets of one floor and area (`AddedUp`) are asked whenever the printed
        count is below them: the question names the sheets. The highest sum of all (`Count.added_up`, which also holds
        the sum of the scheduled units that the dossier's family total gives) is asked when no block carries it: a
        block that holds the family's own count carries it, and its "*" note and its review card name both numbers; a
        family split between blocks (or reduced, `_reduced`) leaves it in none of them. A family with both is asked
        once."""
        held: dict[str, list[str]] = {}         # family prefix -> the blocks it is in
        carried: set[str] = set()               # the prefixes whose count a block carries with its sum
        for system, draft in zip(systems, drafts):
            for fam in draft.families:
                if fam.source is not None:
                    key = fam.source.prefix.casefold()
                    held.setdefault(key, []).append(system.name)
                    if fam.count.added_up is not None:
                        carried.add(key)
        for fact in self.reader.family_facts():
            family = self.reader.family(fact)
            key = family.prefix.casefold()
            stated, up = family.added_up, family.count.added_up
            said = []
            if stated is not None and (family.count.value is None or family.count.value < stated.summed):
                said.append(stated.note())
            if up is not None and key not in carried and not (said and up.value <= stated.summed):
                said.append(_left_out(family.count, held.get(key, [])))
            if said:
                self.questions.append(f"{family.name} ({family.prefix}): {'; '.join(said)}; confirm the count.")

    # -- the invariant: nothing the ledger holds is dropped

    def lost(self, drafts: list[_Draft]) -> None:
        """Every family of the ledger and every tag it lists ends up in a system or in a question: whatever the
        steps above left in neither is asked here, by family, with its tags."""
        present = {t.upper() for d in drafts for t in d.tags()}
        sources = {f.source.prefix.casefold() for d in drafts for f in d.families if f.source is not None}
        asked = " ".join(self.questions)
        for fact in self.reader.family_facts():
            family = self.reader.family(fact)
            missing = [t for t in family.tags if t.upper() not in present and not naming(t).search(asked)]
            if family.tags and not missing:
                continue
            if not family.tags and (family.prefix.casefold() in sources or family.prefix.upper() in present):
                continue             # its code is a block's family, or a tag a block holds (P-1 of P: F4)
            what = ", ".join(missing) if missing else family.prefix
            self.questions.append(f"{family.name} ({what}) is in the documents but in no block of this plan; "
                                  "which system is it in?")

    # -- step 6: global points

    def global_points(self, drafts: list[_Draft]) -> list[_Draft]:
        """A sequence section no system took whose title says it lists points for the whole job (global points,
        system points, building-wide points) is one "Global Points" system: that section its sequence, control
        integration, one set for the job."""
        used = {m.id for d in drafts for m in d.matches}
        found = [f for f in self.ledger.of_kind("sequence_match")
                 if f.id not in used and _GLOBAL_WORDS.search(squash(f.subject))]
        if not found:
            return []
        refs = tuple(dict.fromkeys(self.reader.fact_ref(f) for f in found))
        return [_Draft(key=GLOBAL_POINTS, name=GLOBAL_POINTS, kind="global",
                       families=[_Fam(GLOBAL_POINTS, (), Count(1, refs[:1]))], prefixes=[], matches=found)]

    # -- the questions each family raises where it lands

    def family_questions(self, systems: list[System], drafts: list[_Draft]) -> None:
        for system, draft in zip(systems, drafts):
            for fam in draft.families:
                source = fam.source
                if source is None:
                    continue
                label = f"{source.name} ({tag_words(fam.tags) if fam.tags else source.prefix})"
                if source.plan_only:
                    self.questions.append(f"{label} is seen on the drawings but on no schedule; confirm it exists "
                                          f"(it is in the {system.name} block).")
                elif fam.tags and fam.count.value is None and self.reader.zero_only(source.prefix):
                    self.questions.append(f"The schedule gives 0 for {source.prefix} but lists {tag_words(fam.tags)}; "
                                          f"confirm the count (the {system.name} block reads Qty (##)).")
                elif source.sequence_only and fam.count.value is None:
                    self.questions.append(f"{label} is named in the sequence of operation but no drawing or schedule "
                                          f"shows it; how many are there? The {system.name} block reads Qty (##).")
            if draft.kind == "single" and squash(draft.name).casefold() in _GENERIC_KINDS and draft.tags():
                self.questions.append(
                    f"{system.name} ({tag_words(draft.tags())}) has only the general name “{system.name}”: the "
                    "documents give no kind for it, so its block may gather other equipment of that kind. What are "
                    "these units, and are they in the BMS scope?")

    # -- families of one name are one block

    def merge_named(self, drafts: list[_Draft]) -> list[_Draft]:
        """Two or more families of one name (any case, plural or singular, punctuation aside) with the same alternate
        and the same exception are one block: the first one's key and name, each family kept with its own tags and
        count, their sequences together; a question asks to confirm. A general kind alone ("Fan", "Pump") is never
        a reason to merge, nor are families matched to different sequence sections: the documents keep those apart,
        so each stays its own block and a question asks to confirm (FINAL-D F3)."""
        out = list(drafts)
        singles = [d for d in drafts if d.kind == "single"]
        by_name: dict[tuple[str, str, str], list[_Draft]] = {}
        for draft in singles:
            name = _same_name(draft.name)
            if name and name not in _GENERIC_KINDS:
                by_name.setdefault((name, draft.alternate, draft.exception), []).append(draft)
        for block in by_name.values():
            if len(block) < 2:
                continue
            sections = {frozenset(squash(m.subject) for m in d.matches) for d in block if d.matches}
            if len(sections) > 1:
                self.questions.append(
                    f"{', '.join(d.key for d in block)} carry the same name, “{block[0].name}”, but each matches its "
                    "own sequence section, so they are planned as separate blocks; confirm they are separate "
                    "systems.")
                continue
            first = block[0]
            for other in block[1:]:
                first.families += other.families
                first.prefixes += [p for p in other.prefixes if p not in first.prefixes]
                first.matches += [m for m in other.matches if m not in first.matches]
                first.extra_refs += [r for r in other.extra_refs if r not in first.extra_refs]
            out = [d for d in out if d not in block[1:]]
            self.questions.append(
                f"{', '.join(d.key for d in block)} carry the same name, “{first.name}”, so they are planned as one "
                f"{first.name} block; confirm they are the same kind of equipment.")
        return out


_GENERIC_KINDS = ai_evidence.GENERAL_KINDS
_ENUMERATOR = re.compile(r"^\s*(?:[A-Za-z]|\d+(?:\.\d+)*|[ivxIVX]+)[.)]\s+")
_JOINT = re.compile(r"\s+(?:and|with|for|&|including)\s+|[,:;(/]", re.I)
_LEVEL = re.compile(r"\b(?:level|floor|lvl)\s+\w+\b|\b(?:typ\.?|typical)\b", re.I)
_SPECIFIC_WORDS = 6
_ACRONYMS = frozenset({"IT", "VRF", "ERV", "RTU", "HPAC", "DDC", "BMS", "VFD", "CO", "NO", "FSD", "MUAF", "DXF", "UH",
                       "EUH", "EDH", "AHU", "VAV"})
_PLURAL_KINDS = frozenset({"fans", "pumps", "units", "dampers", "devices", "coils", "valves"})


def _says_kind(shape: Shape, name: str) -> bool:
    """The name says one of the shape's kind words (whole words, a plural s / es allowed), as `shape_for` reads
    them."""
    kind = " ".join(re.findall(r"[a-z0-9]+", (name or "").lower()))
    return any(re.search(rf"\b{re.escape(w)}(?:s|es)?\b", kind) for w in shape.kind_words)


def _reduced(count: Count, new: int) -> Count:
    """A family's count made smaller for one block (a group's part, the rest after the parts, the dampers no fan
    took): `new` prints, citing the sources of the number it came from. The family's other counts below `new` are
    kept; those at or above it are whole-family numbers that would print in its place (the highest prints), so they
    leave `others`; the planner's question names them and the number it came from (`_came_from`). The family's
    `added_up` (ruling L1) is the sum of the whole family's sheets, not of this part: it is left out, and the
    planner's question (`added_up_counts`) still names both numbers."""
    return Count(new, count.sources, tuple(o for o in count.others if o.value < new))


def _places(refs) -> str:
    """The sheets the refs are on ("M-501"), else "the documents"."""
    sheets = list(dict.fromkeys(r.where.split(",")[0].strip() for r in refs if r.where))
    return " and ".join(sheets) or "the documents"


def _also(count: Count, new: int) -> str:
    """The family's other counts a reduction to `new` takes out of `others` ("9 per M-101"), "" when none."""
    return ", ".join(f"{o.value} per {_places((o.ref,))}" for o in count.others if o.value >= new)


def _came_from(count: Count, new: int) -> str:
    """The numbers a reduced count came from, as a question says them: "10 per M-501 (also 9 per M-101)"."""
    also = _also(count, new)
    return f"{count.value} per {_places(count.sources)}" + (f" (also {also})" if also else "")


def _left_out(count: Count, blocks: list[str]) -> str:
    """The words for the sum ruling L1 left out of a family's count (`Count.added_up`) when no block's note names it:
    the highest count and the sum, each with its place, and the blocks the family is in, each with only part of it."""
    up = count.added_up
    parts = list(dict.fromkeys(blocks))
    held = f"the count in each block it is in ({', '.join(parts)}) is only part of the family's, " if parts else ""
    return (f"the highest count is {count.value} per {_places(count.sources)}; {up.value} if every sheet of the same "
            f"floor and area is added up (per {_places((up.ref,))}); {held}so no block's note names the {up.value}")


def _same_name(name: str) -> str:
    """A name as two families of one name compare it: lower case, words only, the last word singular."""
    words = re.findall(r"[a-z0-9]+", squash(name).casefold())
    if words:
        words[-1] = _singular(words[-1])
    return " ".join(words)


def _singular(word: str) -> str:
    low = word.casefold()
    return word[:-1] if low.endswith("s") and not low.endswith("ss") and len(word) > 3 else word


def _title(word: str, shouting: bool = False) -> str:
    """A word in Title Case; an acronym ("IT", "VRF") upper-case; a short upper-case word kept when the text it is
    from is not all upper-case (there its capitals say it is an acronym)."""
    if word.upper() in _ACRONYMS:
        return word.upper()
    if word.isupper() and len(word) <= 4 and not shouting:
        return word
    return word[:1].upper() + word[1:].lower()


def _one(name: str) -> str:
    """The name with a plural kind word at its end singular ("Exhaust Fans" -> "Exhaust Fan")."""
    words = name.split()
    if words and (words[-1].casefold() in _PLURAL_KINDS or re.search(r"[a-z](?:er|or)s$", words[-1], re.I)):
        words[-1] = words[-1][:-1]
    return " ".join(words)


def _is_one(families) -> bool:
    """One unit: its families hold one tag in all, or their count is 1."""
    tags = {t.upper() for f in families for t in f.tags}
    values = [f.count.value for f in families]
    return len(tags) == 1 or (None not in values and sum(values) == 1)


def _specific_words(text, family: FamilyFacts, cut_place: bool) -> list[str]:
    """A title or a place in at most six words: no enumerator, cut at its first joint ("and", "with", a comma),
    no tag text, no level words for a place, the last word singular; [] when nothing is left."""
    text = _ENUMERATOR.sub("", squash(text))
    text = _JOINT.split(text, maxsplit=1)[0]
    if cut_place:
        text = _LEVEL.sub(" ", text)
    tags = {t.casefold() for t in family.tags} | {family.prefix.casefold()}
    words = [w for w in text.split() if w.casefold() not in tags and not re.search(r"\d", w)]
    words = words[:_SPECIFIC_WORDS]
    if not words:
        return []
    words[-1] = _singular(words[-1])
    shouting = text.upper() == text
    return [_title(w, shouting) for w in words]


def _with_kind(words: list[str], kind: str, kind_word: str) -> str:
    """The words with the kind's last word added when they do not say it (at most six words in all)."""
    if kind_word not in {w.casefold() for w in words}:
        words = words[:_SPECIFIC_WORDS - 1] + [_title(_singular(kind.split()[-1]))]
    return " ".join(words)


def _group_name(reader: Reader, group: Fact) -> str:
    """The group's own words; when it has none, its members' prefixes ("BS / AC"); never empty."""
    return (squash(group.subject) or " / ".join(dict.fromkeys(f.prefix for f, _ in members(reader, group)))
            or squash(group.value) or "Group")


_CONDENSATE = re.compile(r"\bcondensate\s+pumps?\b", re.I)


def _is_condensate(draft: _Draft) -> bool:
    """A block of condensate pumps: its name or its family's ledger name says so."""
    names = [draft.name, *(f.name for f in draft.families), *(f.source.name for f in draft.families if f.source)]
    return any(_CONDENSATE.search(squash(n)) for n in names)


def _all_condensate(draft: _Draft) -> bool:
    """A block of condensate pumps only: every family's name or ledger name says so (a lone split unit its pumps
    joined is not one, PLN-7)."""
    return bool(draft.families) and all(
        _CONDENSATE.search(squash(f.name)) or (f.source is not None and _CONDENSATE.search(squash(f.source.name)))
        for f in draft.families)


_CONDENSATE_SOURCE = re.compile(
    # equipment whose cooling coil drains condensate; never "cooling" alone (a cooling tower makes none,
    # REVIEW-FINAL4 F4); never "rooftop" or "heat recovery" alone (a rooftop exhaust fan and a heat recovery chiller
    # make none, REVIEW-FINAL5 F6)
    r"\b(?:air[- ]handl\w*|fan[- ]coil|heat[- ]pump|roof[- ]?top (?:unit|air)\w*|dedicated outdoor|"
    r"unit ventilator|(?:energy|heat) recovery (?:unit|ventilator)\w*|makeup air|make-up air|air condition\w*|"
    r"indoor unit|cooling coil|dehumidif\w*|computer room)\b", re.I)
_CONDENSATE_PREFIXES = frozenset({"AHU", "FCU", "FC", "HP", "WSHP", "RTU", "DOAS", "DOA", "UV", "ERV", "HRU", "MAU",
                                  "CRAC", "CRAH"})


def _makes_condensate(draft: _Draft) -> bool:
    """Equipment that makes condensate (an air handling unit, a fan coil, a heat pump, a rooftop unit ...): the only
    other equipment a condensate pump is named as maybe serving."""
    names = [draft.name, *(f.name for f in draft.families), *(f.source.name for f in draft.families if f.source)]
    prefixes = {p.upper() for p in draft.prefixes} | {_lead(draft.key)}
    return bool(prefixes & _CONDENSATE_PREFIXES) or any(_CONDENSATE_SOURCE.search(squash(n)) for n in names)


def _family_suffixes(families) -> set[str]:
    """The families' tags without their family's prefix: CP-21 of CP gives "21"."""
    out = set()
    for fam in families:
        prefix = (fam.source.prefix if fam.source is not None else "").upper()
        for tag in fam.tags:
            if prefix and tag.upper().startswith(prefix + "-"):
                out.add(tag.upper()[len(prefix) + 1:])
    return out


# A split unit's role is read from the kind's own head noun (REVIEW-FINAL5 F5): "outdoor air" and "outside air" are
# taken out first, and so is what follows "with", "for" or "serving" ("Indoor Unit with Outdoor Air Kit" is indoor).
_OUTSIDE_AIR = re.compile(r"\b(?:outdoor|outside)[\s-]+air\b", re.I)
_MODIFIER = re.compile(r"\s(?:with|w/|c/w|for|serving|including)(?:\s|$).*$", re.I)
_OUTDOOR = re.compile(r"\b(?:outdoor\s+unit|condensing\s+unit|condenser)s?\b", re.I)
_OUTDOOR_PREFIXES = frozenset({"ACCU", "CU", "ODU", "OU"})


def _split_role(draft: _Draft) -> str:
    """A split unit's role, from the kind names the ledger gives its families, read as the kind's own head noun
    ("outdoor air" and anything after "with" taken out): "outdoor" when one names an Outdoor Unit, a Condensing Unit
    or a Condenser (or says Outdoor and not Indoor), or when the names say neither and its prefix is an outdoor
    unit's (ACCU, CU, ODU, OU); else "indoor" (an indoor unit, an air conditioning unit)."""
    names = [draft.name, *(f.name for f in draft.families), *(f.source.name for f in draft.families if f.source)]
    heads = [_MODIFIER.sub("", _OUTSIDE_AIR.sub(" ", squash(n))) for n in names]
    indoor = [bool(re.search(r"\bindoor\b", head, re.I)) for head in heads]
    if any(_OUTDOOR.search(head) or (re.search(r"\boutdoor\b", head, re.I) and not inside)
           for head, inside in zip(heads, indoor)):
        return "outdoor"
    if any(indoor):
        return "indoor"
    return "outdoor" if _lead(draft.key) in _OUTDOOR_PREFIXES else "indoor"


def _pair_up(a: set[tuple[str, str]], b: set[tuple[str, str]]) -> bool:
    """Two sections' units ((role, tag suffix) each, `_split_role`) are one split system: every unit of the smaller
    one has a partner of the other role (an indoor unit's outdoor unit) with its suffix in the other, and none has
    one in its own section."""
    small, other = (a, b) if len(a) <= len(b) else (b, a)
    if not small:
        return False
    return all(not any(s == s2 and p2 != p for p2, s2 in small) and any(s == s2 and p2 != p for p2, s2 in other)
               for p, s in small)


def _natural_key(text: str) -> list:
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", text)]


def _suffixes(draft: _Draft) -> set[str]:
    """A unit's tags without their prefix: AC-LOBBY-1 gives "LOBBY-1"."""
    head = draft.key.upper() + "-"
    return {t.upper()[len(head):] for t in draft.tags() if t.upper().startswith(head)}


def _heaters_named(heater: _Draft, text: str) -> list[str]:
    """The heater system's tags the text names, in their order: each tag whole, and once one is whole, the others
    written short after it ("EDH-1-1, 1-2" names EDH-1-2 too)."""
    text = squash(text)
    tags = heater.tags()
    named = {t for t in tags if naming(t).search(text)}
    if named:
        for tag in tags:
            rest = tag.partition("-")[2]
            if tag not in named and rest and not rest.isdigit() and \
                    re.search(rf"(?<![\w.\-]){re.escape(rest)}(?![\w.\-])", text, re.I):
                named.add(tag)
    return [t for t in tags if t in named]


def _units_named(drafts: list[_Draft], heater: _Draft, text: str) -> list[tuple[_Draft, list[str]]]:
    """The systems (not a duct heater system, not global points) the text names, the heater tags left out, each with
    its tags the text names (all its tags when it names the unit by its prefix or name only)."""
    text = squash(text)
    for tag in heater.tags():
        text = naming(tag).sub(" ", text)
    out = []
    units = [d for d in drafts if d is not heater and d.kind not in ("heaters", "global")]
    named = {id(d) for d in _named(units, text)}
    for draft in (d for d in units if id(d) in named):
        tags = [t for t in draft.tags() if naming(t).search(text)]
        out.append((draft, tags or draft.tags()))
    return out


def _named(drafts: list[_Draft], text: str, skip=frozenset()) -> list[_Draft]:
    """The systems a text names, those holding a tag it names whole first, then those it names by their key, a
    prefix or a tag's prefix, each in plan order (PLN-4). A word that heads a tag the text names and a system holds
    ("EF" of "EF-2") names that tag only: a group holding EF-1 is not named by "EF-2", the block holding EF-2 is.
    Names in `skip` (the damper prefixes, for a damper's link) name nothing."""
    text = squash(text)
    held = {id(d): [t for t in d.tags() if naming(t).search(text)] for d in drafts}
    tags = {t.upper() for found in held.values() for t in found}
    heads = lambda name: any(t.startswith(name.upper() + "-") for t in tags)  # noqa: E731
    return [d for d in drafts if held[id(d)]] + [
        d for d in drafts if not held[id(d)]
        and names_in([n for n in d.names() if n.upper() not in skip and not heads(n)], text)]


def _with_served(systems: list[System], drafts: list[_Draft]) -> list[System]:
    """Each duct heater system lists the units it serves; each served unit's system carries its own entry, naming
    the duct heater system that writes its heaters (the heaters are written in one place)."""
    of = {id(d): s for s, d in zip(systems, drafts)}
    serves: dict[int, list[Served]] = {}
    for system, draft in zip(systems, drafts):
        for tie in draft.ties:
            unit = of[id(tie.unit)]
            entry = Served(key=unit.key, name=unit.name, tags=tuple(tie.tags), heaters=tuple(tie.heaters),
                           heater_key=system.key, heater_name=system.name)
            serves.setdefault(id(draft), []).append(entry)
            serves.setdefault(id(tie.unit), []).append(entry)
    return [replace(s, serves=tuple(serves[id(d)])) if id(d) in serves else s for s, d in zip(systems, drafts)]


def _front_end(planner: _Planner) -> FrontEnd:
    facts = planner.ledger.of_kind("front_end")
    by = lambda subject: [squash(f.value) for f in facts if squash(f.subject).casefold() == subject]  # noqa: E731
    mode = next((m for m in by("mode") if m in ("new-system", "extend-existing")), "")
    existing = next((n for n in by("existing_name") if n), None)
    if not mode:
        planner.questions.append("The documents do not say whether the BMS is new or extends an existing one; "
                                 "which is it? The plan assumes a new system.")
        mode = "new-system"
    return FrontEnd(mode=mode, existing_system_name=existing if mode == "extend-existing" else None)


def _exceptions(planner: _Planner, systems: list[System], drafts: list[_Draft]) -> tuple[ScopeException, ...]:
    out = []
    for fact in planner.ledger.of_kind("note"):
        if squash(fact.subject).casefold() != "exception":
            continue
        text = without_ledger_brackets(fact.value)      # the ledger's "[S14]" form; any other id is validate's
        if not text:
            continue
        named = _named(drafts, text)
        key = next((s.key for s, d in zip(systems, drafts) if named and d is named[0]), "")
        out.append(ScopeException(system_key=key, text=text, refs=(planner.reader.fact_ref(fact),)))
    return tuple(out)


def _unmatched_sections(planner: _Planner, drafts: list[_Draft]) -> list[str]:
    used = {m.id for d in drafts for m in d.matches}
    sections: dict[str, list[Fact]] = {}        # by section id: a heading can repeat under each system
    for fact in planner.ledger.of_kind("sequence_match"):
        sections.setdefault(fact.source_id, []).append(fact)
    asks, general = [], []
    for facts in sections.values():
        if any(f.id in used for f in facts):
            continue
        named = [squash(f.value) for f in facts if squash(f.value)]
        if not named:
            general.append(squash(facts[0].subject))
            continue
        asks.append(f"Sequence section {squash(facts[0].subject)} matched no system (it named "
                    f"{', '.join(dict.fromkeys(named))}); which system is it?")
    if general:
        asks.append("These sequence sections describe no equipment of their own, so no block was written for them: "
                    f"{'; '.join(general)}. Confirm none of them needs a block of its own.")
    return asks


def plan_job(ledger: Ledger, catalogue: Catalogue, dossier: Dossier, playbook: Playbook) -> Job:
    """The Job skeleton from the completed ledger (`ledger.complete` is True).

    Contract:
    - One System per block the job calls for, each with `key` (unique), `name`, `shape` (a Playbook shape name via
      `playbook.shape_for(kind, prefixes)`, or "" when no shape applies), `control`, `families` (each with its tags
      and a Count whose `value` is the highest count any source gives, `sources` the refs giving it, `others` every
      different count with its ref; `value` None when no count is known), `sequence_refs` (the sequence passages,
      as Refs) and `alternate`.
    - `devices`, `clarifications` are empty and `tech_hours` None: `write_system` fills them.
    - Groups the practice rules keep together are one System: a VRF / split group with its indoor, condensing and
      branch-selector families; dampers linked to a fan are under that fan's system (not a system of their own);
      duct heaters in one place.
    - A system the documents name but AME does not do goes to `Job.exceptions`; open questions to `Job.questions`.
    - `Job.front_end` is set (mode from the ledger's front_end facts); `Job.header` stays None (the run sets it).
    - Every Ref's `source_id` is a ledger / dossier source id ("S41", "I2", "Q7", "F17"), its `quote` the exact
      words, its `where` the place (`ledger.sources[source_id]`, shortened by `estimator.ledger.facts.where_short`).
    - Pure: the same ledger, catalogue, dossier and Playbook give the same Job. No AI call.
    """
    planner = _Planner(ledger, dossier, playbook)
    own = [squash(f.value) for f in ledger.of_kind("note") if squash(f.subject).casefold() == "question"]
    drafts = planner.drafts()
    planner.general_kind_tags(drafts)
    drafts = planner.gather_splits(drafts)
    drafts = planner.gather_heaters(drafts)
    drafts = planner.link_dampers(drafts)
    planner.place_seen(drafts)
    drafts = planner.merge_named(drafts)
    planner.heater_sequences(drafts)
    drafts += planner.global_points(drafts)
    keys: set[str] = set()
    systems = _with_served([planner.system(d, keys, drafts) for d in drafts], drafts)
    planner.family_questions(systems, drafts)
    planner.added_tags()
    planner.added_up_counts(systems, drafts)
    planner.lost(drafts)
    front_end = _front_end(planner)
    questions = own + planner.questions + _unmatched_sections(planner, drafts)
    name = ledger.job_name or getattr(dossier, "job_name", "") or ""
    return Job(name=name, systems=tuple(systems), front_end=front_end,
               exceptions=_exceptions(planner, systems, drafts),
               questions=tuple(dict.fromkeys(q for q in questions if q)))
