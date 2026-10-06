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
- the printed count is the highest; every other count is kept with its source; unknown is None (Qty (##));
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
from bms.plan_groups import family_of_tag, members, part_count, parts, split_apart
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
        self.reader = Reader(ledger, getattr(dossier, "sources", None) or {}, getattr(dossier, "text", "") or "")
        self.dossier = dossier
        self.questions: list[str] = []
        self._texts: dict[str, str] | None = None

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
        if _DUCT_HEATER_WORDS.search(f"{family.prefix} {family.name}"):
            return True
        shape = self.playbook.shape_for(family.name, [family.prefix])
        return shape is not None and _DUCT_HEATER_WORDS.search(f"{shape.name} {' '.join(shape.kind_words)}") is not None

    def is_damper(self, subject: str) -> bool:
        """A motorized damper's tag or label: it leads with a damper prefix or says "damper". A fire or smoke
        damper is not one (those stay where they are); a smoke purge duct is not a smoke damper."""
        text = squash(subject)
        if _lead(text) in _FIRE_SMOKE_PREFIXES or _FIRE_SMOKE_WORDS.search(text):
            return False
        return _lead(text) in DAMPER_PREFIXES or "damper" in text.casefold()

    # -- step 1: families and groups

    def drafts(self) -> list[_Draft]:
        reader = self.reader
        kept = []
        for group in self.ledger.of_kind("group"):
            apart = split_apart(reader, group)
            if apart:
                self.questions.append(
                    f"The documents group {', '.join(apart)} as “{_group_name(reader, group)}”, but each matches "
                    "its own sequence section, so each is planned as its own system; confirm they are separate systems.")
                continue
            kept.append(group)
        claims_of = parts(reader, kept)
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

    def _join_owner(self, drafts: list[_Draft], family: FamilyFacts, owner: FamilyFacts) -> None:
        """A code with no kind of its own that is a tag of another family ("GI-4" of GI) is a part of that family:
        it joins the block holding the family, with its own count, under the family's name, and is asked. A code
        that is already one of the family's own tags (P-1 of P-1, P-2) is not added again; the question says so.
        When the family's count was read from the code's own count, the question says the count includes it."""
        head = f"{family.prefix} is on a schedule with no kind of equipment given for it; "
        if family.prefix.upper() in {t.upper() for t in owner.tags}:
            self.questions.append(
                f"{head}it is one of the {owner.name} ({owner.prefix}) tags, so it is counted with the "
                f"{owner.name} units, not again. Confirm it is one of them.")
            return
        draft = self._holding(drafts, owner)
        if draft is None:
            drafts.append(self._single(family))
        else:
            draft.families.append(_Fam(family.name, family.tags or (family.prefix,), family.count, family))
            draft.prefixes.append(family.prefix)
            draft.matches += [m for m in self.reader.matches(family.prefix) if m not in draft.matches]
        own = set(family.count.sources)
        if owner.count.value is not None and own and own & set(owner.count.sources):
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
                    count = Count(number, family.count.sources)
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
        all."""
        draft = self._single(family)
        if not claims:
            return draft
        if any(tags is None for _, tags in claims):
            return None
        taken = {t.upper() for _, tags in claims for t in tags}
        left = tuple(t for t in family.tags if t.upper() not in taken)
        if not left:
            return None
        count = family.count
        numbers = [part_count(self.reader, family, tags, group)[0] for group, tags in claims]
        if count.value is not None and None not in numbers and count.value - sum(numbers) >= len(left):
            count = Count(count.value - sum(numbers), count.sources)
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
                count = Count(len(left), count.sources, count.others)
                said = f"its count is {len(left)}, one per tag left"
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
        loose = [d for d in drafts if d.kind == "single" and _lead(d.key) in prefixes]
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
        splits = [d for d in drafts if d.kind == "split" or (d.kind == "single" and _lead(d.key) in prefixes)]
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
                      and mine & _family_suffixes(d.families)]
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
        # are one block only when every unit of the smaller pairs by tag suffix with a unit of another prefix in the
        # other (AC-109 with ACCU-109) and none pairs inside its own section; the join is asked. Sections sharing
        # some numbers but not so (both numbering from 1) stay apart and are asked (FINAL-D F2).
        joined: list[list[str]] = [[n] for n in names]
        units = lambda names_: {(_lead(d.key), s) for n in names_ for d in by_section[n] for s in _suffixes(d)}  # noqa: E731
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
        damper_keys = {d.key.upper() for d in drafts if d.kind == "single" and d.key.upper() in DAMPER_PREFIXES}
        grouped = {f.source.prefix.upper() for d in drafts if d.kind != "single" for f in d.families
                   if f.source is not None and f.source.prefix.upper() in DAMPER_PREFIXES}
        claims: dict[int, dict[str, list[Fact]]] = {}      # target draft -> damper prefix -> links
        links_of: dict[str, list[Fact]] = {}               # damper prefix -> links
        found: list[tuple[Fact, _Draft]] = []
        for link in self.ledger.of_kind("link"):
            subject = squash(link.subject)
            if not self.is_damper(subject):
                continue
            value = squash(link.value)
            target = next((d for d in drafts if d.key.upper() not in damper_keys
                           and names_in([n for n in d.names() if n.upper() not in DAMPER_PREFIXES], value)), None)
            if target is not None:
                found.append((link, target))
        linked = {squash(link.subject).upper() for link, _ in found}
        found += self._schedule_links(drafts, damper_keys | grouped, linked)
        for link, target in found:
            subject = squash(link.subject)
            prefix = _lead(subject)
            if prefix not in damper_keys and prefix not in grouped:
                prefix = next(iter(sorted(damper_keys)), "") or next(iter(sorted(grouped)), "") or prefix
            claims.setdefault(id(target), {}).setdefault(prefix, []).append(link)
            links_of.setdefault(prefix, []).append(link)
        if not claims:
            return drafts
        out: list[_Draft] = []
        for draft in drafts:
            if draft.kind != "single":
                draft.families = self._less_dampers(draft.families, links_of)
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
        tags = tuple(dict.fromkeys(squash(l.subject) for l in links if _TAG.match(squash(l.subject))))
        return _Fam(name, tags, Count(len(links), tuple(dict.fromkeys(self.reader.fact_ref(l) for l in links))),
                    family, moved=True)

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

    def _less_dampers(self, families: list[_Fam], links_of: dict[str, list[Fact]]) -> list[_Fam]:
        kept = []
        for fam in families:
            links = links_of.get(fam.source.prefix.upper(), []) if fam.source is not None and not fam.moved else []
            if links and fam.count.value is not None:
                left = fam.count.value - len(links)
                if left <= 0:
                    continue
                claimed = {squash(l.subject).upper() for l in links}
                fam = _Fam(fam.name, tuple(t for t in fam.tags if t.upper() not in claimed), Count(left, fam.count.sources),
                           fam.source)
            kept.append(fam)
        return kept

    def _unclaimed(self, draft: _Draft, links: list[Fact], drafts: list[_Draft], claims: dict) -> _Draft | None:
        family = draft.families[0]
        total = family.count.value
        claimed_tags = {squash(l.subject).upper() for l in links}
        locations = [f for f in self.ledger.of_kind("location") if naming(draft.key).search(squash(f.subject))]
        refs = tuple(dict.fromkeys([*family.count.sources, *(self.reader.fact_ref(f) for f in locations + links)]))
        sheets = list(dict.fromkeys(r.where.split(",")[0].strip() for r in refs if r.where))
        owners = [d.key for d in drafts if id(d) in claims and draft.key.upper() in claims[id(d)]]
        if total is not None:
            left = total - len(links)
            if left <= 0:
                return None
            count = Count(left, family.count.sources)
            self.questions.append(
                f"{family.name} ({draft.key}): {left} of the {total} are linked to no fan; {len(links)} are "
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

    def system(self, draft: _Draft, keys: set[str]) -> System:
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
            if shape is not None and shape is self.split_shape() and _is_condensate(draft):
                shape = None                            # a pump block's name may say "split ac"; it is no split unit
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
                      control=self._control(draft, vrf),
                      families=tuple(Family(_one(f.name) if _is_one([f]) else f.name, tuple(f.tags), f.count)
                                     for f in families),
                      sequence_refs=tuple(dict.fromkeys(refs)), alternate=draft.alternate)

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

    def _control(self, draft: _Draft, vrf: bool) -> str:
        """packaged when a provider fact about the system says the unit maker or the factory controls it;
        integration when one says the BMS integrates it (or the system is a VRF group and none says otherwise);
        none when one says no controls are in the contract; else field. Global points are integration."""
        if draft.kind == "global":
            return "integration"
        names = draft.names()
        found = [squash(f.value) for f in self.ledger.of_kind("provider") if names_in(names, f.subject)]
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


def _family_suffixes(families) -> set[str]:
    """The families' tags without their family's prefix: CP-21 of CP gives "21"."""
    out = set()
    for fam in families:
        prefix = (fam.source.prefix if fam.source is not None else "").upper()
        for tag in fam.tags:
            if prefix and tag.upper().startswith(prefix + "-"):
                out.add(tag.upper()[len(prefix) + 1:])
    return out


def _pair_up(a: set[tuple[str, str]], b: set[tuple[str, str]]) -> bool:
    """Two sections' units ((prefix, tag suffix) each) are one split system: every unit of the smaller one has a
    partner of another prefix with its suffix in the other, and none has one in its own section."""
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
    for draft in drafts:
        if draft is heater or draft.kind in ("heaters", "global") or not names_in(draft.names(), text):
            continue
        tags = [t for t in draft.tags() if naming(t).search(text)]
        out.append((draft, tags or draft.tags()))
    return out


def _draft_named(drafts: list[_Draft], text: str) -> _Draft | None:
    text = squash(text)
    for draft in drafts:
        if any(n.casefold() == text.casefold() for n in draft.names()):
            return draft
    for draft in drafts:
        if names_in(draft.names(), text):
            return draft
    return None


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
        key = next((s.key for s, d in zip(systems, drafts) if names_in(d.names(), text)), "")
        out.append(ScopeException(system_key=key, text=text, refs=(planner.reader.fact_ref(fact),)))
    return tuple(out)


def _unmatched_sections(planner: _Planner, drafts: list[_Draft]) -> list[str]:
    used = {m.id for d in drafts for m in d.matches}
    sections: dict[str, list[Fact]] = {}
    for fact in planner.ledger.of_kind("sequence_match"):
        sections.setdefault(squash(fact.subject).casefold(), []).append(fact)
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
    systems = _with_served([planner.system(d, keys) for d in drafts], drafts)
    planner.family_questions(systems, drafts)
    planner.lost(drafts)
    front_end = _front_end(planner)
    questions = own + planner.questions + _unmatched_sections(planner, drafts)
    name = ledger.job_name or getattr(dossier, "job_name", "") or ""
    return Job(name=name, systems=tuple(systems), front_end=front_end,
               exceptions=_exceptions(planner, systems, drafts),
               questions=tuple(dict.fromkeys(q for q in questions if q)))
