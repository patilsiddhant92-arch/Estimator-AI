"""The planner's groups (workstream 2, private): how a group fact reads its members, which part of each family it
takes, how many units that part holds, and when a group is not one plant. Pure; no AI.

A member is "PREFIX", "PREFIX (TAG-1, TAG-2 x3, TAG-4 thru 6)", or a bare tag or tag range of a family
("WAC-1.0", "ACCU-12-1 thru 3"); commas inside brackets do not part members."""
from __future__ import annotations

import re

from estimator.ledger.facts import Fact

from bms.plan_read import FamilyFacts, Reader, expand, squash

_OUTSIDE_BRACKETS = re.compile(r",(?![^()]*\))")
_MEMBER = re.compile(r"^([^()]*?)\s*\(([^()]*)\)$")
_TIMES = re.compile(r"(?:\s*×|\s+x)\s*\d+\s*$", re.I)        # "HRU-3 x3", "HRU-3×3"; never the X of "TX1"
_TAG_TIMES = re.compile(r"(?<![A-Za-z0-9])([A-Za-z]{1,6}(?:-[A-Za-z0-9.]+)+)(?:\s*×|\s+x)\s*(\d+)(?![A-Za-z0-9])",
                        re.I)

Claim = tuple[Fact, "tuple[str, ...] | None"]       # (the group, the tags it takes, None for the whole family)


def family_of_tag(reader: Reader, tag: str) -> FamilyFacts | None:
    """The family a bare tag belongs to ("WAC-1.0" is WAC's): the longest prefix it starts with, then a dash."""
    key = tag.casefold()
    owners = [f for f in reader.family_facts()
              if key.startswith(squash(f.subject).casefold() + "-") and len(key) > len(squash(f.subject)) + 1]
    if not owners:
        return None
    return reader.family(max(owners, key=lambda f: len(squash(f.subject))))


def members(reader: Reader, group: Fact) -> list[tuple[FamilyFacts, tuple[str, ...] | None]]:
    """The group's members in its order, each family once: (the family, the tags it lists, or None when it lists
    none). A member naming no family is left out."""
    found: dict[str, list] = {}
    for piece in (p.strip() for p in _OUTSIDE_BRACKETS.split(squash(group.value))):
        if not piece:
            continue
        m = _MEMBER.match(piece)
        head, listed = (m.group(1).strip(), m.group(2)) if m else (_TIMES.sub("", piece).strip(), "")
        family = reader.family_by_prefix(head) if head else None
        tags = expand([_TIMES.sub("", t).strip() for t in listed.split(",") if t.strip()]) if listed else []
        if family is None and head and not listed:
            family = family_of_tag(reader, head)
            tags = expand([head]) or [head]
        if family is None:
            continue
        entry = found.setdefault(family.prefix.casefold(), [family, []])
        if entry[1] is not None:
            entry[1] = entry[1] + [t for t in tags if t not in entry[1]] if tags else None
    return [(family, tuple(tags) if tags is not None else None) for family, tags in found.values()]


def split_apart(reader: Reader, group: Fact) -> list[str]:
    """The member prefixes of a group whose families each match their own sequence section (two or more distinct
    sections among them): such a group is not one plant and is not kept. [] when the group holds."""
    matched = [family.prefix for family, _ in members(reader, group) if reader.matches(family.prefix)]
    values = {squash(m.subject).casefold() for m in reader.matches(*matched)}
    return matched if len(values) >= 2 else []


def parts(reader: Reader, groups: list[Fact]) -> dict[str, list[Claim]]:
    """What each family gives the groups, by family prefix (any case): (the group, None) when the group takes the
    whole family (a member listing no tags, none of the family's own, or all of them); (the group, its tags) when
    the listed tags that are the family's own are a proper part of them (a listed tag not the family's own is
    ignored). A family the first group took whole is no later group's; a tag is taken once."""
    out: dict[str, list[Claim]] = {}
    for group in groups:
        for family, listed in members(reader, group):
            claims = out.setdefault(family.prefix.casefold(), [])
            if any(tags is None for _, tags in claims):
                continue
            mine = {t.upper() for t in family.tags}
            wanted = {t.upper() for t in listed or ()} & mine
            if not wanted or wanted == mine:
                if not claims:
                    claims.append((group, None))
                continue
            taken = {t.upper() for _, tags in claims for t in tags or ()}
            tags = tuple(t for t in family.tags if t.upper() in wanted and t.upper() not in taken)
            if tags:
                claims.append((group, tags))
    return out


def stated(reader: Reader, group: Fact) -> dict[str, tuple[int, tuple[Fact, ...]]]:
    """The unit counts the group fact and the link facts give a tag ("HRU-3 x3"), by tag in capitals: every
    mention summed, within a fact and across the facts, each fact read once."""
    found: dict[str, tuple[int, tuple[Fact, ...]]] = {}
    for fact in (group, *reader.ledger.of_kind("link")):
        text = squash(fact.value) if fact is group else f"{squash(fact.subject)} {squash(fact.value)}"
        for m in _TAG_TIMES.finditer(text):
            tag = m.group(1).upper()
            total, facts = found.get(tag, (0, ()))
            found[tag] = (total + int(m.group(2)), facts if fact in facts else facts + (fact,))
    return found


def part_count(reader: Reader, family: FamilyFacts, tags: tuple[str, ...], group: Fact) -> tuple[int | None, list[Fact]]:
    """The units a group's part of a family holds, and the facts stating them: each tag's stated count ("x3"); one
    for a tag no fact counts only when the tags are unit tags (the family's count is no more than its distinct
    tags); None when a tag has no count and the tags are type tags, or the family has no count: never a guess
    that undershoots."""
    counts = stated(reader, group)
    printed = family.count.value
    unit_tags = printed is not None and printed <= len({t.upper() for t in family.tags})
    total, used = 0, []
    for tag in tags:
        if tag.upper() in counts:
            n, facts = counts[tag.upper()]
            total += n
            used += [f for f in facts if f not in used]
        elif unit_tags:
            total += 1
        else:
            return None, used
    return total, used
