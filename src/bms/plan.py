"""The planner (workstream 2): the job ledger to the Job skeleton (design §4.2, §5 row 2).

Pure, no AI. Reads the old app's Ledger (and the Dossier's source places as a fallback); the Catalogue is taken for
the contract and not needed. The behaviours are those the estimator approved in the old planner:

- one system per family, in ledger order; a group fact is one system (placed where its first member is), reading
  its members with their tags; a part of a family a group lists leaves the rest a system of its own;
- a group whose families each match their own sequence section is not one plant: its families stand alone;
- a VRF group is one system with indoor, condensing and branch-selector families;
- split units no group took are one Split System per sequence section and per same alternate and exception;
- duct heaters are one system that also carries the sequence of the units they serve;
- a motorized damper linked to a fan moves under that fan; dampers no fan claims stay a damper system;
- the printed count is the highest; every other count is kept with its source; unknown is None (Qty (##));
- unscheduled and sequence-only families, parts with no count, unmatched sequence sections and the ledger's own
  questions become plain-words questions.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace

from estimator.catalogue.job import Catalogue
from estimator.ledger.facts import Fact, Ledger
from estimator.writing.dossier import Dossier

from bms.model import Count, Family, FrontEnd, Job, Ref, ScopeException, System
from bms.plan_groups import members, part_count, parts, split_apart
from bms.plan_read import FamilyFacts, Reader, naming, names_in, squash, tag_words
from bms.playbook import Playbook, Shape

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
_CONDENSING_WORDS = re.compile(r"\bcondens|\boutdoor\s+unit\b|\bheat\s+pump\s+unit\b", re.I)
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
        self.reader = Reader(ledger, getattr(dossier, "sources", None) or {})
        self.dossier = dossier
        self.questions: list[str] = []

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
        for fact in reader.family_facts():
            family = reader.family(fact)
            claims = claims_of.get(family.prefix.casefold(), [])
            for group, _ in claims:
                if group.id not in placed:
                    placed.add(group.id)
                    drafts.append(self._group(group, claims_of))
            rest = self._rest(family, claims)
            if rest is not None:
                drafts.append(rest)
        return drafts

    def _single(self, family: FamilyFacts) -> _Draft:
        reader = self.reader
        return _Draft(key=family.prefix, name=family.name, kind="single",
                      families=[_Fam(family.name, family.tags, family.count, family)], prefixes=[family.prefix],
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
        return {f"{SPLIT_SYSTEM} — {n}": sorted(block, key=drafts.index) for n, block in by_section.items()}

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
        """A duct heater system reads the sequence of the units it serves: their sequence matches join its own."""
        for heater in (d for d in drafts if d.kind == "heaters"):
            for unit in self._served(heater, drafts):
                heater.matches += [m for m in unit.matches if m not in heater.matches]

    def _served(self, heater: _Draft, drafts: list[_Draft]) -> list[_Draft]:
        names = heater.names()
        found: list[str] = []
        for fact in self.ledger.of_kind("link"):
            subject, value = squash(fact.subject), squash(fact.value)
            if names_in(names, subject) and not names_in(names, value):
                found.append(value)
            elif names_in(names, value) and not names_in(names, subject):
                found.append(subject)
        for fact in self.ledger.of_kind("provider") + self.ledger.of_kind("note"):
            if names_in(names, fact.subject):
                found += _SERVES.findall(squash(fact.value))
        units: list[_Draft] = []
        for text in found:
            unit = _draft_named(drafts, text)
            if unit is not None and unit is not heater and unit not in units:
                units.append(unit)
        return units

    # -- step 4: dampers under their fan

    def link_dampers(self, drafts: list[_Draft]) -> list[_Draft]:
        """A motorized damper linked to a fan (or any other system) moves under it: that system takes a damper
        family whose count is its links, each link a source. The damper family, alone or in a group, keeps only
        the dampers no system claims; when every damper is claimed it is gone. The dampers no fan claims stay a
        damper system citing the sheets that show them, and a question says the total."""
        damper_keys = {d.key.upper() for d in drafts if d.kind == "single" and d.key.upper() in DAMPER_PREFIXES}
        grouped = {f.source.prefix.upper() for d in drafts if d.kind != "single" for f in d.families
                   if f.source is not None and f.source.prefix.upper() in DAMPER_PREFIXES}
        claims: dict[int, dict[str, list[Fact]]] = {}      # target draft -> damper prefix -> links
        links_of: dict[str, list[Fact]] = {}               # damper prefix -> links
        for link in self.ledger.of_kind("link"):
            subject = squash(link.subject)
            if not self.is_damper(subject):
                continue
            value = squash(link.value)
            target = next((d for d in drafts if d.key.upper() not in damper_keys
                           and names_in([n for n in d.names() if n.upper() not in DAMPER_PREFIXES], value)), None)
            if target is None:
                continue
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
        else:
            shape = self.playbook.shape_for(draft.name, draft.prefixes)
        families = draft.families
        if vrf or draft.kind == "split":
            families = [self._role_named(f, draft, shape, vrf) for f in families]
        key, number = draft.key, 2
        while key in keys:
            key, number = f"{draft.key} {number}", number + 1
        keys.add(key)
        refs = [self.reader.fact_ref(m) for m in draft.matches] + draft.extra_refs
        return System(key=key, name=draft.name, shape=shape.name if shape is not None else "",
                      control=self._control(draft, vrf),
                      families=tuple(Family(f.name, tuple(f.tags), f.count) for f in families),
                      sequence_refs=tuple(dict.fromkeys(refs)), alternate=draft.alternate)

    def _role(self, fam: _Fam, words: str) -> str:
        source = fam.source
        prefix = _lead(source.prefix) if source is not None else ""
        name = fam.name
        says_vrf = _VRF_WORDS.search(f"{words} {name}") or _BRANCH_WORDS.search(f"{words} {name}")
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
        none when one says no controls are in the contract; else field."""
        names = draft.names()
        found = [squash(f.value) for f in self.ledger.of_kind("provider") if names_in(names, f.subject)]
        if any(_MAKER.search(v) and not _NOT_MAKER.search(v) for v in found):
            return "packaged"
        if any(_INTEGRATION.search(v) for v in found):
            return "integration"
        if any(_NO_CONTROLS.search(v) for v in found):
            return "none"
        return "integration" if vrf else "field"

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


def _group_name(reader: Reader, group: Fact) -> str:
    """The group's own words; when it has none, its members' prefixes ("BS / AC"); never empty."""
    return (squash(group.subject) or " / ".join(dict.fromkeys(f.prefix for f, _ in members(reader, group)))
            or squash(group.value) or "Group")


def _suffixes(draft: _Draft) -> set[str]:
    """A unit's tags without their prefix: AC-LOBBY-1 gives "LOBBY-1"."""
    head = draft.key.upper() + "-"
    return {t.upper()[len(head):] for t in draft.tags() if t.upper().startswith(head)}


def _draft_named(drafts: list[_Draft], text: str) -> _Draft | None:
    text = squash(text)
    for draft in drafts:
        if any(n.casefold() == text.casefold() for n in draft.names()):
            return draft
    for draft in drafts:
        if names_in(draft.names(), text):
            return draft
    return None


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
        text = squash(fact.value)
        key = next((s.key for s, d in zip(systems, drafts) if names_in(d.names(), text)), "")
        out.append(ScopeException(system_key=key, text=text, refs=(planner.reader.fact_ref(fact),)))
    return tuple(out)


def _unmatched_sections(planner: _Planner, drafts: list[_Draft]) -> list[str]:
    used = {m.id for d in drafts for m in d.matches}
    sections: dict[str, list[Fact]] = {}
    for fact in planner.ledger.of_kind("sequence_match"):
        sections.setdefault(squash(fact.subject).casefold(), []).append(fact)
    asks = []
    for facts in sections.values():
        if any(f.id in used for f in facts):
            continue
        named = [squash(f.value) for f in facts if squash(f.value)]
        it = f" (it named {', '.join(dict.fromkeys(named))})" if named else ""
        asks.append(f"Sequence section {squash(facts[0].subject)} matched no system{it}; which system is it?")
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
    drafts = planner.gather_splits(drafts)
    drafts = planner.gather_heaters(drafts)
    drafts = planner.link_dampers(drafts)
    planner.heater_sequences(drafts)
    keys: set[str] = set()
    systems = [planner.system(d, keys) for d in drafts]
    planner.family_questions(systems, drafts)
    front_end = _front_end(planner)
    questions = own + planner.questions + _unmatched_sections(planner, drafts)
    name = ledger.job_name or getattr(dossier, "job_name", "") or ""
    return Job(name=name, systems=tuple(systems), front_end=front_end,
               exceptions=_exceptions(planner, systems, drafts),
               questions=tuple(dict.fromkeys(q for q in questions if q)))
