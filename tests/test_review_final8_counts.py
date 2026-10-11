"""REVIEW-FINAL8 (final bounded gate): rebuild b76d9c1. The undercount invariant as a seeded property test over
invented plan sets, and the regression table of every failing input of REVIEW-FINAL2, 4, 5, 6 and 7.

The oracle is written from the generator, never from the code under test: the generator knows which lines it wrote
as labels (the ruled forms: a tag alone, a tag that starts a short line, a comma list), which as notes (a reference
word before the tag, a note over twelve words), which documents are a marked-up copy, a reissue or another
building, and so the true lower bound of each family. Invented fixtures only (job 26-9999, invented sheets and
tags); no job is run."""
from __future__ import annotations

import random
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import pytest

from estimator.catalogue.documents import Document
from estimator.catalogue.tags import TagEntry
from estimator.reading.devices import typical_sheets
from estimator.reading.inventory import placements
from estimator.reading.revisions import governing_pages, sheet_versions, supersede
from estimator.writing.dossier import build_dossier
from test_dossier_plan_areas import _page, _reading, _sheet

FAMILIES = ("VAV", "AHU", "EF", "EBB", "CUH")
TYPES = ("EBB-A", "CUH-A")
ORDINAL = {1: "FIRST", 2: "SECOND", 3: "THIRD", 4: "FOURTH"}
LONG_NOTE = "CONTRACTOR SHALL COORDINATE THE FINAL LOCATION OF {t} WITH THE CEILING GRID AND LIGHTING SHOWN"


# ---- the generator ---------------------------------------------------------------------------------------------------

@dataclass
class Plan:
    """One drawn plan page as the generator wrote it: what is labelled, what is only named in notes."""
    document: str
    page: int
    number: str
    title: str
    building: int
    floors: int = 1                                  # the floors it stands for (a typical sheet)
    labels: Counter = field(default_factory=Counter)   # tag -> label lines naming it
    noted: set = field(default_factory=set)            # unit tags only in notes on this page
    lines: list = field(default_factory=list)
    role: str = "plan"                               # plan, overlay, alike (a repeat of the page before), copy,
                                                     # reissue, addendum


def _unit(tag: str) -> bool:
    return tag not in TYPES


def _prefix(tag: str) -> str:
    return tag.split("-")[0]


def _label_line(rng, tag: str) -> str:
    return rng.choice((tag, f"{tag} 450 CFM", f"{tag} OFFICE 1{rng.randint(0, 9)}", f"{tag} (N)", f"{tag} TYP"))


def _note_line(rng, tag: str) -> str:
    return rng.choice((f"TO {tag}", f"SEE {tag}", f"DUCT FROM {tag}", LONG_NOTE.format(t=tag)))


def _fill(rng, plan: Plan, units: list[str], types: dict[str, int], noted_share: float = 0.15) -> None:
    """Writes the plan's lines: each unit labelled (now and then a comma pair, now and then only a note), each type
    labelled at its places, and some reference notes beside the labels."""
    lines = [plan.title]
    todo = list(units)
    rng.shuffle(todo)
    while todo:
        tag = todo.pop()
        if rng.random() < noted_share:
            lines.append(_note_line(rng, tag))
            plan.noted.add(tag)
            continue
        if todo and rng.random() < 0.15:
            other = todo.pop()
            lines.append(f"{tag}, {other}")
            plan.labels[tag] += 1
            plan.labels[other] += 1
        else:
            lines.append(_label_line(rng, tag))
            plan.labels[tag] += 1
        if rng.random() < 0.2:
            lines.append(_note_line(rng, tag))       # a note beside the label: never a second label
    for tag, places in types.items():
        for _ in range(places):
            lines.append(rng.choice((tag, f"{tag} ENTRY", f"{tag} STAIR")))
            plan.labels[tag] += 1
    head, rest = lines[:1], lines[1:]
    rng.shuffle(rest)
    plan.lines = head + rest


@dataclass
class Case:
    seed: int
    plans: list = field(default_factory=list)
    documents: dict = field(default_factory=dict)      # relative -> (kind, revision)
    copies: dict = field(default_factory=dict)         # copy document -> its original
    reused: bool = False                               # the buildings' tags restart (VAV-11 in both)
    apart: bool = True                                 # the buildings' titles name them apart

    def tags(self) -> list[str]:
        return sorted({t for p in self.plans for t in (*p.labels, *p.noted)})


def generate(seed: int) -> Case:
    rng = random.Random(seed)
    case = Case(seed)
    buildings = rng.choice((1, 1, 2))
    case.reused = buildings == 2 and rng.random() < 0.4
    one_document = buildings == 2 and rng.random() < 0.4
    case.apart = buildings == 1 or one_document or rng.random() < 0.6
    for b in range(buildings):
        document = "Drawings/Mech.pdf" if b == 0 or one_document else "Drawings/Second Building.pdf"
        case.documents.setdefault(document, ("drawings", "base"))
        base = 100 if b == 0 or not one_document else 300
        part = f"BUILDING {'AB'[b]} " if case.apart and buildings == 2 else ""
        digit = 1 if case.reused else b + 1
        floors = rng.randint(1, 3)
        page = 1 + max((p.page for p in case.plans if p.document == document), default=0)
        for f in range(1, floors + 1):
            name = rng.choice((f"LEVEL {f}", f"{ORDINAL[f]} FLOOR"))
            units = [f"VAV-{digit}{f}{k}" for k in range(1, rng.randint(1, 4) + 1)]
            if f == 1:
                units.append(f"AHU-{digit}")
            if f == floors:
                units += [f"EF-{digit}{k}" for k in range(1, rng.randint(0, 2) + 1)]
            types = {t: rng.randint(0, 4) for t in TYPES if rng.random() < 0.5}
            plan = Plan(document, page, f"M-{base + f}", f"{part}HVAC {name} PLAN", b)
            _fill(rng, plan, units, types)
            case.plans.append(plan)
            page += 1
            roll = rng.random()
            if roll < 0.2:                           # the same floor's piping plan: the same units, read again
                overlay = Plan(document, page, f"M-{base + 100 + f}", f"{part}HVAC PIPING {name} PLAN", b,
                               role="overlay")
                _fill(rng, overlay, units, {t: n for t, n in types.items() if rng.random() < 0.5},
                      noted_share=0.4)
                case.plans.append(overlay)
                page += 1
            elif roll < 0.3:                         # the same page printed again under its number
                again = Plan(document, page, plan.number, plan.title, b, labels=Counter(plan.labels),
                             noted=set(plan.noted), lines=list(plan.lines), role="alike")
                case.plans.append(again)
                page += 1
            elif roll < 0.4:                         # another page under the same number, other units
                more = [f"VAV-{digit}{f}{k}" for k in range(5, 5 + rng.randint(1, 3))]
                other = Plan(document, page, plan.number, plan.title, b)
                _fill(rng, other, more, {})
                case.plans.append(other)
                page += 1
        if rng.random() < 0.3:                       # a typical sheet for three more floors
            low = floors + 1
            units = [f"VAV-{digit}9{k}" for k in range(1, rng.randint(1, 3) + 1)]
            plan = Plan(document, page, f"M-{base + 50}", f"{part}HVAC TYPICAL FLOOR PLAN LEVEL {low} TO {low + 2}",
                        b, floors=3)
            _fill(rng, plan, units, {t: rng.randint(1, 3) for t in TYPES if rng.random() < 0.5})
            case.plans.append(plan)
    first = [p for p in case.plans if p.document == "Drawings/Mech.pdf" and p.building == 0]
    extra = rng.random()
    if extra < 0.2 and len({p.number for p in first}) >= 3:  # a marked-up copy of the set
        copy = "Drawings/Marked_Mech.pdf"
        case.documents[copy] = ("drawings", "base")
        case.copies[copy] = "Drawings/Mech.pdf"
        for p in first:
            case.plans.append(Plan(copy, p.page, p.number, p.title, p.building, p.floors, Counter(p.labels),
                                   set(p.noted), p.lines + ["CLOUD 1 VERIFY IN FIELD PER RFI 12"], role="copy"))
    elif extra < 0.4:                                # an undated reissue (Rev 1) or an addendum that adds a unit
        addendum = rng.random() < 0.5
        document = "Addendum/Mech Addendum 1.pdf" if addendum else "Drawings/Mech Rev 1.pdf"
        case.documents[document] = ("addendum", "base") if addendum else ("drawings", "1")
        reissued = [p for p in first if p.role == "plan" and p.floors == 1][:rng.randint(1, 3)]
        for page, p in enumerate(reissued, start=1):
            added = f"VAV-{p.number[-1]}{p.number[-1]}8" if rng.random() < 0.7 else None
            lines = p.lines + ([_label_line(rng, added)] if added else []) + ["REVISED PER ADDENDUM"]
            labels = Counter(p.labels) + (Counter({added: 1}) if added else Counter())
            case.plans.append(Plan(document, page, p.number, p.title, p.building, 1, labels, set(p.noted), lines,
                                   role="addendum" if addendum else "reissue"))
    return case


# ---- the catalogue, read the way read_job reads it ---------------------------------------------------------------

def catalogue_of(case: Case):
    pages = [_page(p.document, p.page, "\n".join(p.lines)) for p in case.plans]
    sheets = [_sheet(p.page, p.number, p.title, p.document) for p in case.plans]
    counts = Counter(p.document for p in case.plans)
    documents = tuple(Document(Path(d), d, kind, revision, max(p.page for p in case.plans if p.document == d))
                      for d, (kind, revision) in case.documents.items() if counts[d])
    job = SimpleNamespace(name="26-9999", root=Path("."), documents=documents)
    from estimator.catalogue.overview import SpecOverview
    return SimpleNamespace(job=job, pages=tuple(pages), sheets=tuple(sheets), sections=(),
                           tags=tuple(TagEntry(t, "", (), ("M-101",), 2) for t in case.tags()),
                           overview=SpecOverview(), bid=None, flags=())


def read(case: Case, tmp_path):
    """Both sides on the production path: the supersessions and typicals `read_job` works out, the same governing
    pages for the inventory's placements and the dossier's counts line."""
    catalogue = catalogue_of(case)
    supersessions, _flags = supersede(catalogue, sheet_versions(catalogue))
    typicals = typical_sheets(catalogue)
    reading = _reading()
    reading.supersessions, reading.typicals = tuple(supersessions), tuple(typicals)
    pages = governing_pages(catalogue, supersessions, [t.sheet for t in typicals])
    placed = placements(catalogue, case.tags(), typicals, pages)
    d = build_dossier(catalogue, reading, tmp_path)
    inventory = Counter()
    for tag, p in placed.items():
        inventory[_prefix(tag)] += p.count
    lines = {prefix: next((line for line in d.text.splitlines() if f"] {prefix} (" in line), "") for prefix in FAMILIES}
    dossier = {prefix: (d.counts.get(prefix) or {}).get("plan_placements", 0) for prefix in FAMILIES}
    counted = ({tag for tag, p in placed.items() if p.count},
               {prefix: (d.counts.get(prefix) or {}).get("distinct_tags", 0) for prefix in FAMILIES})
    return inventory, dossier, lines, counted


# ---- the oracle, from the generator alone --------------------------------------------------------------------------

def _physical(case: Case) -> list[Plan]:
    """The plans that are physically distinct drawings: a marked-up copy and a page printed again are not (the
    repeated page stands for one more floor, as the generator meant it), and a base page an addendum reissues is
    replaced by the addendum's (the addendum governs, ruled). An undated reissue is summed with its base (FINAL-N)."""
    replaced = {(p.number, p.building) for p in case.plans if p.role == "addendum"}
    return [p for p in case.plans if p.role not in ("copy", "alike")
            and not (p.role in ("plan", "overlay") and p.document == "Drawings/Mech.pdf" and p.building == 0
                     and (p.number, p.building) in replaced)]


def truth(case: Case) -> dict[str, int]:
    """The lower bound of each family: each building's distinct unit tags (a unit on two plans of one floor, or on a
    reissue, is one unit), and each type's places on one drawing of each floor, times the floors a typical stands
    for. Buildings add up."""
    bound: Counter = Counter()
    for b in {p.building for p in case.plans}:
        mine = [p for p in case.plans if p.building == b and p.role != "copy"]
        units = {t for p in mine for t in (*p.labels, *p.noted) if _unit(t)}
        for tag in units:
            bound[_prefix(tag)] += 1
        by_floor: dict = defaultdict(Counter)        # one floor drawn twice (plan and overlay): the higher
        for p in _physical(case):
            if p.building != b:
                continue
            floor = (re.sub(r"PIPING ", "", p.title), p.number if p.role == "plan" and p.floors > 1 else "")
            for tag in TYPES:
                by_floor[floor][tag] = max(by_floor[floor][tag], p.labels[tag] * p.floors)
        for places in by_floor.values():
            for tag, n in places.items():
                bound[_prefix(tag)] += n
    return {k: v for k, v in bound.items() if v}


def distinct(case: Case) -> dict[str, int]:
    """Property (i) as worded: the distinct tags named on the plans (copies aside)."""
    found: Counter = Counter()
    for tag in {t for p in case.plans if p.role != "copy" for t in (*p.labels, *p.noted)}:
        found[_prefix(tag)] += 1
    return dict(found)


def plain(case: Case) -> dict[str, int]:
    """The plain per-sheet sum: on each physically distinct drawing each unit's tag labelled or named (the ruled
    backstop: a unit named anywhere counts once there) counted once and each type at every label, times the floors
    the sheet stands for (a page printed again is one more floor)."""
    again = Counter((p.document, p.number) for p in case.plans if p.role == "alike")
    total: Counter = Counter()
    for p in _physical(case):
        floors = p.floors * (1 + again[(p.document, p.number)] if p.role == "plan" else 1)
        for tag in {*p.labels, *p.noted}:
            n = p.labels[tag] if not _unit(tag) else 1
            total[_prefix(tag)] += n * floors
    return {k: v for k, v in total.items() if v}


NOTE_NUMBER = re.compile(r"\d+")


def violations(case: Case, inventory, dossier, lines, counted) -> list[tuple[str, str, str]]:
    """(severity, family, what) for each break of the invariant. HIGH: a side below the distinct tags, a unit tag on
    a plan that neither side counts at all, or a side below the true bound with no reading note on the counts line.
    LIMIT: below the bound with a note (a flagged undercount), below the plain sum with no note giving it, or the two
    sides differing."""
    found = []
    bound, tags, summed = truth(case), distinct(case), plain(case)
    named = {t for p in case.plans if p.role != "copy" for t in (*p.labels, *p.noted)}
    for tag in sorted(named - counted[0]):
        found.append(("HIGH", _prefix(tag), f"inventory never counts {tag}, on a plan"))
    for prefix, n in tags.items():
        if counted[1].get(prefix, 0) < n:
            found.append(("HIGH", prefix, f"dossier names {counted[1].get(prefix, 0)} of the {n} distinct tags"))
    for prefix in FAMILIES:
        line = lines[prefix]
        notes = line.split("Reading notes:", 1)[1] if "Reading notes:" in line else ""
        numbers = {int(n) for n in NOTE_NUMBER.findall(notes)}
        for side, count in (("inventory", inventory.get(prefix, 0)), ("dossier", dossier.get(prefix, 0))):
            if count < tags.get(prefix, 0):
                found.append(("HIGH", prefix, f"{side} {count} below the {tags[prefix]} distinct tags"))
            elif count < bound.get(prefix, 0):
                severity = "LIMIT" if notes else "HIGH"
                found.append((severity, prefix, f"{side} {count} below the true {bound[prefix]}"
                              + (" (noted)" if notes else " with no note")))
        count = dossier.get(prefix, 0)
        if count < summed.get(prefix, 0) and summed[prefix] not in numbers:
            found.append(("LIMIT", prefix, f"dossier {count} below the plain sum {summed[prefix]}, not said"))
        if inventory.get(prefix, 0) != count:
            found.append(("LIMIT", prefix, f"inventory {inventory.get(prefix, 0)} and dossier {count} differ"))
    return found


CASES = 2000


def test_the_oracle_reads_a_known_job_right():
    """The overlay job of test_dossier_plan_areas by hand: two floors each drawn twice, six boxes, truth 6; the
    plain sum 12 (each box on two drawings)."""
    case = Case(0, documents={"Drawings/Mech.pdf": ("drawings", "base")})
    for f, boxes in ((1, ["VAV-11", "VAV-12", "VAV-13"]), (2, ["VAV-21", "VAV-22", "VAV-23"])):
        for role, number in (("plan", f"M-10{f}"), ("overlay", f"M-20{f}")):
            title = f"HVAC {'PIPING ' if role == 'overlay' else ''}LEVEL {f} PLAN"
            case.plans.append(Plan("Drawings/Mech.pdf", len(case.plans) + 1, number, title, 0,
                                   labels=Counter(boxes), lines=[title, *boxes], role=role))
    assert truth(case) == {"VAV": 6} and plain(case) == {"VAV": 12} and distinct(case) == {"VAV": 6}


def _run(tmp_path, keep) -> tuple[list, Counter, int]:
    high, limits, n = [], Counter(), 0
    for seed in range(CASES):
        case = generate(seed)
        if not keep(case):
            continue
        n += 1
        found = violations(case, *read(case, tmp_path))
        high += [(seed, *v) for v in found if v[0] == "HIGH"]
        limits.update(f"{v[1]}: {re.sub(r'[0-9]+', 'n', v[2])}" for v in found if v[0] == "LIMIT")
    print(f"\n{n} cases; KNOWN LIMITS (by kind):", dict(limits.most_common()))
    return high, limits, n


def _known(case: Case) -> bool:
    """A case of H1/H2 (an addendum reissue) or H4 (a number printed again alike in one document, and on several
    pages of other text in another)."""
    if any(p.role == "addendum" for p in case.plans):
        return True
    again = {p.number for p in case.plans if p.role == "alike"}
    pages = Counter((p.document, p.number) for p in case.plans if p.role == "plan")
    return any(pages[(p.document, p.number)] >= 2 and p.number in again and not any(
        q.role == "alike" and (q.document, q.number) == (p.document, p.number) for q in case.plans)
        for p in case.plans)


def test_the_undercount_invariant_holds_on_2000_invented_plan_sets(tmp_path):
    high, _limits, _n = _run(tmp_path, lambda case: True)
    shown = "\n".join(f"seed {s}: {f} {w}" for s, _h, f, w in high[:20])
    assert not high, f"{len(high)} HIGH breaks:\n{shown}"


def test_guard_the_invariant_holds_on_every_other_invented_plan_set(tmp_path):
    """Marked-up copies, undated reissues, overlays, typical sheets, repeated pages, two buildings, notes and labels
    with words beside them: no silent undercount, no side below the distinct tags and no unit or type on a plan that
    is never counted, once the H1, H2 and H4 shapes are set aside."""
    high, _limits, n = _run(tmp_path, lambda case: not _known(case))
    assert n > 1500 and not high, high[:10]


# ---- HIGH: an addendum's reissue of one sheet number supersedes every page of that number --------------------------

ADDENDUM = "Addendum/Mech Addendum 1.pdf"


def _minimal(plans, documents):
    case = Case(0, documents=documents)
    for document, page, number, title, building, tags, role in plans:
        case.plans.append(Plan(document, page, number, title, building, labels=Counter(tags), lines=[title, *tags],
                               role=role))
    return case


def _addendum_over_another_building():
    """Building A (Mech.pdf) and building B (Second Building.pdf) each have their own LEVEL 1 plan M-101, with their
    own units; the titles name the buildings. An addendum reissues building A's M-101 and adds VAV-18."""
    return _minimal([("Drawings/Mech.pdf", 1, "M-101", "BUILDING A HVAC LEVEL 1 PLAN", 0,
                      ["VAV-11", "VAV-12", "AHU-1"], "plan"),
                     ("Drawings/Second Building.pdf", 1, "M-101", "BUILDING B HVAC LEVEL 1 PLAN", 1,
                      ["VAV-21", "VAV-22", "AHU-2"], "plan"),
                     (ADDENDUM, 1, "M-101", "BUILDING A HVAC LEVEL 1 PLAN", 0,
                      ["VAV-11", "VAV-12", "AHU-1", "VAV-18"], "addendum")],
                    {"Drawings/Mech.pdf": ("drawings", "base"), "Drawings/Second Building.pdf": ("drawings", "base"),
                     ADDENDUM: ("addendum", "base")})


def _addendum_over_the_other_page_of_a_number():
    """M-101 is on two pages of Mech.pdf with other text (FINAL-K: two sheets, both read): page 1 VAV-11 and 12,
    page 2 VAV-15 and 16. An addendum reissues page 1's plan (its text and VAV-18)."""
    return _minimal([("Drawings/Mech.pdf", 1, "M-101", "HVAC LEVEL 1 PLAN", 0, ["VAV-11", "VAV-12"], "plan"),
                     ("Drawings/Mech.pdf", 2, "M-101", "HVAC LEVEL 1 PLAN", 0, ["VAV-15", "VAV-16"], "plan"),
                     (ADDENDUM, 1, "M-101", "HVAC LEVEL 1 PLAN", 0, ["VAV-11", "VAV-12", "VAV-18"], "addendum")],
                    {"Drawings/Mech.pdf": ("drawings", "base"), ADDENDUM: ("addendum", "base")})


def test_an_addendum_to_one_building_never_drops_another_buildings_sheet_of_the_same_number(tmp_path):
    case = _addendum_over_another_building()
    inventory, dossier, *_rest = read(case, tmp_path)
    assert min(inventory["VAV"], dossier["VAV"]) >= 5 and min(inventory["AHU"], dossier["AHU"]) >= 2


def test_an_addendum_reissuing_one_page_of_a_number_never_drops_its_other_page(tmp_path):
    case = _addendum_over_the_other_page_of_a_number()
    inventory, dossier, *_rest = read(case, tmp_path)
    assert inventory["VAV"] >= 5 and dossier["VAV"] >= 5


def test_guard_the_two_addendum_cases_count_every_unit(tmp_path):
    """What the two xfails saw on b76d9c1: the low count, no reading note and no supersession flag. FINAL-O fixed
    both (H1, H2), so this guard pinned the old, wrong count; it now pins the fix: both cases count every unit, and
    the one-page reissue of a two-page number says which page it kept."""
    for case, right in ((_addendum_over_another_building(), {"VAV": 5, "AHU": 2}),
                        (_addendum_over_the_other_page_of_a_number(), {"VAV": 5})):
        inventory, dossier, lines, _counted = read(case, tmp_path)
        catalogue = catalogue_of(case)
        _supersessions, flags = supersede(catalogue, sheet_versions(catalogue))
        assert all(dossier[f] == inventory[f] == n for f, n in right.items())
        assert all(n >= truth(case)[f] for f, n in right.items())
    assert flags == ["addendum reissues M-101 (1 page); base has 2 pages (Mech.pdf): unmatched page kept (p.2), "
                     "counted; check"]


# ---- CHECK 2: every failing input of REVIEW-FINAL2, 4, 5, 6 and 7, as a table row on b76d9c1 ------------------------
# Each row is the reviewer's own invented input, built with the reviewer's own helpers, and read on BOTH sides on the
# production path (the supersessions `read_job` works out, the same governing pages for the inventory). `truth` is
# the count the report states as right; `either` is the other count where the report leaves the truth open (a ruling
# decides): a count below it must carry a reading note that gives it.

import test_dossier_plan_areas as base                        # noqa: E402
import test_review_final2_counts as r2                        # noqa: E402
import test_review_final4_plan_areas as r4                    # noqa: E402
import test_review_final5_counts as r5                        # noqa: E402
import test_review_final6_counts as r6                        # noqa: E402
import test_review_final7_counts as r7                        # noqa: E402


def both(catalogue, reading, family: str, tmp_path) -> tuple[int, int, str]:
    """(inventory plan count, dossier plan placements, the counts line) of one family."""
    if not getattr(reading, "supersessions", ()):
        reading.supersessions = tuple(supersede(catalogue, sheet_versions(catalogue))[0])
    typicals = tuple(getattr(reading, "typicals", ()))
    pages = governing_pages(catalogue, reading.supersessions, [t.sheet for t in typicals])
    tags = sorted({t.tag for t in catalogue.tags if _prefix(t.tag) == family})
    inventory = sum(p.count for p in placements(catalogue, tags, typicals, pages).values())
    d = build_dossier(catalogue, reading, tmp_path)
    line = next((line for line in d.text.splitlines() if f"] {family} (" in line), "")
    return inventory, (d.counts.get(family) or {}).get("plan_placements", 0), line


def _r2(titles):
    return lambda: r2._job([("M-101", titles[0], r2.FLOOR), ("M-102", titles[1], r2.FLOOR)], r2.TYPES)


def _same_floor_two_ways():
    boxes1, boxes2 = "VAV-1\nVAV-2\nVAV-3", "VAV-4\nVAV-5\nVAV-6"
    return r2._job([("M-101", "HVAC LEVEL 1 PLAN", boxes1), ("M-102", "HVAC LEVEL 02 PLAN", boxes2),
                    ("M-201", "CONTROLS FIRST FLOOR PLAN", boxes1), ("M-202", "CONTROLS 2ND FLOOR PLAN", boxes2)],
                   [f"VAV-{n}" for n in range(1, 7)])


def _r2_towers():
    four = "\n".join(["EBB-A"] * 4)
    catalogue = r2._inventory_job([("M-601", "MECHANICAL SCHEDULES", ("Schedules",), "SCHEDULES"),
                                   ("M-101", "FIRST FLOOR PLAN - TOWER 1", ("Plans",), four),
                                   ("M-102", "FIRST FLOOR PLAN - TOWER 2", ("Plans",), four)], ["EBB-A"])
    return catalogue, base._reading()


def _r4_one_document(titles, text=r4.TYPICAL, tags=r4.TYPICAL_TAGS):
    def build():
        pages = [base._page(base.DWG, 1, text), base._page(base.DWG, 2, text)]
        sheets = [base._sheet(1, "M-101", titles[0]), base._sheet(2, "M-102", titles[1])]
        return base._catalogue(pages, sheets, tags), base._reading()
    return build


def _r4_two_buildings():
    text = r4.TYPICAL + "\nCUH-A"
    pages = [base._page(base.DWG, 1, text), base._page(base.OTHER, 1, text)]
    sheets = [base._sheet(1, "M-101", "FIRST FLOOR PLAN"), base._sheet(1, "B-101", "FIRST FLOOR PLAN", base.OTHER)]
    return (base._catalogue(pages, sheets, r4.TYPICAL_TAGS + ["CUH-A"], [base._doc(base.DWG, 1),
                                                                        base._doc(base.OTHER, 1)]), base._reading())


def _r5_low_high():
    pages = [base._page(base.DWG, 1, "\n".join(r5.BOXES)), base._page(base.DWG, 2, "\n".join(r5.BOXES))]
    sheets = [base._sheet(1, "M-102", "TYPICAL LOW-RISE FLOOR PLAN"),
              base._sheet(2, "M-106", "TYPICAL HIGH-RISE FLOOR PLAN")]
    return base._catalogue(pages, sheets, r5.BOXES), r5._typicals(base._reading(), ("M-102", range(2, 6)),
                                                                  ("M-106", range(6, 11)))


def _r5_first_and_typical():
    pages = [base._page(base.DWG, 1, "\n".join(r5.BOXES)), base._page(base.DWG, 2, "\n".join(r5.BOXES))]
    sheets = [base._sheet(1, "M-101", "FIRST FLOOR PLAN"), base._sheet(2, "M-102", "TYPICAL FLOOR PLAN (FLOORS 2-4)")]
    return base._catalogue(pages, sheets, r5.BOXES), r5._typicals(base._reading(), ("M-102", (2, 3, 4)))


def _r5_two_buildings_ahu():
    ahus = ["AHU-1", "AHU-2", "AHU-3"]
    pages = [base._page(base.DWG, 1, "\n".join(ahus)), base._page(base.OTHER, 1, "\n".join(ahus))]
    sheets = [base._sheet(1, "A-M101", "BUILDING A FIRST FLOOR PLAN"),
              base._sheet(1, "B-M101", "BUILDING B FIRST FLOOR PLAN", base.OTHER)]
    return (base._catalogue(pages, sheets, ahus, [base._doc(base.DWG, 1), base._doc(base.OTHER, 1)]),
            base._reading())


def _r5_ebb1_ten_plans():
    pages = [base._page(base.DWG, n, "EBB-1") for n in range(1, 11)]
    sheets = [base._sheet(n, f"M-1{n:02d}", f"HVAC LEVEL {n} PLAN") for n in range(1, 11)]
    return base._catalogue(pages, sheets, ["EBB-1"]), base._reading()


def _r5_fcu_three():
    pages = [base._page(base.DWG, 1, "FCU-1\nFCU-1\nFCU-1\nFCU-2")]
    return base._catalogue(pages, [base._sheet(1, "M-101", "HVAC LEVEL 1 PLAN")], ["FCU-1", "FCU-2"]), base._reading()


def _r5_fcu_typical():
    _items, catalogue, reading = r5._scheduled_job(["FCU-1\nFCU-1\nFCU-1"], [("M-102", "TYPICAL FLOOR PLAN")],
                                                   ["FCU-1"], [("M-102", range(2, 12))])
    return catalogue, reading


def _r5_ebb_scheduled():
    _items, catalogue, reading = r5._scheduled_job(["EBB-A", "EBB-A"],
                                                   [("M-101", "LEVEL 1 PLAN"), ("M-102", "LEVEL 2 PLAN")], ["EBB-A"])
    return catalogue, reading


def _r6_two_sheets(first, second, numbers=("M-101", "M-102")):
    return lambda: (r6._two_sheets(first, second, numbers), base._reading())


def _r6_buildings(same_tags):
    def build():
        catalogue, a, b = r6._two_buildings(same_tags)
        schedules = [base._schedule("VAV SCHEDULE", [t for f in a for t in f], 4)]
        if not same_tags:
            schedules.append(base._schedule("VAV SCHEDULE", [t for f in b for t in f], 4, document=base.OTHER))
        return catalogue, r7._read(catalogue, schedules)
    return build


def _r6_number_two_pages():
    tags = [f"VAV-{n}" for n in range(1, 8)]
    pages = [base._page(base.DWG, 1, "\n".join(r6.UNITS)), base._page(base.DWG, 2, "\n".join(tags[3:]))]
    sheets = [base._sheet(1, "M-101", "FIRST FLOOR PLAN"), base._sheet(2, "M-101", "SECOND FLOOR PLAN")]
    return base._catalogue(pages, sheets, tags), base._reading()


def _r6_notes_overlay():
    pages = [base._page(base.DWG, 1, "\n".join(r6.UNITS)), base._page(base.DWG, 2, "VAV-1\nTO VAV-2\nTO VAV-3")]
    sheets = [base._sheet(1, "M-101", "HVAC DUCTWORK FIRST FLOOR PLAN"),
              base._sheet(2, "M-201", "HVAC PIPING FIRST FLOOR PLAN")]
    return base._catalogue(pages, sheets, r6.UNITS), base._reading()


def _r7_superset():
    catalogue, schedules = r7._superset_job()
    return catalogue, r7._read(catalogue, schedules)


def _r7_typical_other_set():
    pages, sheets, tags = [], [], set()
    for document, typical in ((base.DWG, ["VAV-1", "VAV-2", "VAV-3"]), (base.OTHER, ["VAV-4", "VAV-5", "VAV-6"])):
        for n, title in ((1, "LEVEL 1 PLAN"), (2, "TYPICAL FLOOR PLAN"), (3, "LEVEL 5 PLAN")):
            units = typical if n == 2 else [f"{t}{n}" for t in typical]
            pages.append(base._page(document, n, "\n".join([title, *units])))
            sheets.append(base._sheet(n, f"M-10{n}", title, document))
            tags |= set(units)
    catalogue = base._catalogue(pages, sheets, sorted(tags), [base._doc(base.DWG, 3), base._doc(base.OTHER, 3)])
    reading = base._reading()
    reading.typicals = (SimpleNamespace(sheet="M-102", floors=("2", "3", "4")),)
    return catalogue, reading


def _r7_three_pages():
    first, second = "VAV-1\nVAV-2\nVAV-3", "VAV-4\nVAV-5\nVAV-6\nVAV-7"
    pages = [base._page(base.DWG, 1, first), base._page(base.DWG, 2, second), base._page(base.DWG, 3, first)]
    sheets = [base._sheet(n, "M-101", "FLOOR PLAN") for n in (1, 2, 3)]
    return base._catalogue(pages, sheets, [f"VAV-{n}" for n in range(1, 8)]), base._reading()


def _r7_row(plans, tags):
    def build():
        pages = [base._page(base.DWG, n + 1, text) for n, (_title, text) in enumerate(plans)]
        sheets = [base._sheet(n + 1, f"M-10{n + 1}", title) for n, (title, _text) in enumerate(plans)]
        return base._catalogue(pages, sheets, tags), base._reading()
    return build


# REVIEW-FINAL7's 32 plan texts (its section 2 table, the guard's _AGREE list), in order, with the truth the report
# states or implies: (truth, the other count where it is open). Row 19 "TO VAV-n" only: the report calls losing it
# intended (0, or 3 by the backstop); row 21 "CUH-A (TYP. OF 4)": four places (its rule 4, LOW, "read as 4"); row 32
# "VAV-1 x2": one box labelled twice, or two boxes (3 or 4).
_R7_TRUTH = [(3, None)] * 15 + [(2, None)] * 3 + [(0, 3), (3, None), (4, None), (4, None), (4, None), (3, None),
                                                  (6, None), (3, None), (3, None), (3, None), (6, None), (4, None),
                                                  (3, None), (3, 4)]

ROWS = [
    *[(f"FINAL2 F1 {t[0]} / {t[1]}", _r2(t), "EBB", 16, None) for t in [p.values[0] for p in r2.TWO_DIFFERENT_FLOORS]],
    ("FINAL2 F1 two towers' first floors, EBB-A x4 each", _r2_towers, "EBB", 8, None),
    ("FINAL2 LEVEL 1 / FIRST FLOOR named two ways (6 boxes)", _same_floor_two_ways, "VAV", 6, None),
    ("FINAL2 F5 CUH-A once on each of two floors", lambda: r2._job(
        [("M-101", "HVAC FIRST FLOOR PLAN", "CUH-A\nVAV-1"), ("M-102", "HVAC SECOND FLOOR PLAN", "CUH-A\nVAV-2")],
        ["CUH-A"]), "CUH", 2, None),
    *[(f"FINAL4 F1 {t[0]} / {t[1]}", _r4_one_document(t), "EBB", 16, None) for t in r4.TWO_AREAS_ONE_DOCUMENT],
    ("FINAL4 F2 two buildings' FIRST FLOOR PLAN, single-placed types", _r4_two_buildings, "EBB", 16, None),
    ("FINAL4 F2 BUILDING A MECHANICAL PLAN twice, single-placed types",
     _r4_one_document(("BUILDING A MECHANICAL PLAN", "BUILDING A MECHANICAL PLAN"), r4.TYPICAL + "\nCUH-A",
                      r4.TYPICAL_TAGS + ["CUH-A"]), "EBB", 8, 16),
    ("FINAL5 F1 typical floors 2-5 and 6-10, VAV-1 to 5", _r5_low_high, "VAV", 45, None),
    ("FINAL5 F1 FIRST FLOOR beside a typical of floors 2-4", _r5_first_and_typical, "VAV", 20, None),
    ("FINAL5 F2 two buildings reuse AHU-1 to 3", _r5_two_buildings_ahu, "AHU", 6, None),
    ("FINAL5 F3 EBB-1 once on each of ten plans", _r5_ebb1_ten_plans, "EBB", 10, None),
    ("FINAL5 F3 FCU-1 three times on one plan", _r5_fcu_three, "FCU", 2, 4),
    ("FINAL5 F4 FCU-1 x3 on a typical of 10 floors", _r5_fcu_typical, "FCU", 10, 30),
    ("FINAL5 F4 scheduled EBB-A once on each of two floors", _r5_ebb_scheduled, "EBB", 2, None),
    *[(f"FINAL6 F2 {a} / {b}", _r6_two_sheets(a, b), "VAV", 6, None)
      for a, b in (("BUILDING 1 LEVEL 2 PLAN", "BUILDING 2 LEVEL 1 PLAN"),
                   ("LEVEL 1 AREA 2 PLAN", "LEVEL 2 AREA 1 PLAN"), ("WING 3 FLOOR 4 PLAN", "WING 4 FLOOR 3 PLAN"))],
    ("FINAL6 F3 second building, same numbers, other tags", _r6_buildings(False), "VAV", 18, None),
    ("FINAL6 F3 two identical buildings", _r6_buildings(True), "VAV", 9, 18),
    ("FINAL6 F4 WING MA1 / WING MB1 FIRST FLOOR",
     _r6_two_sheets("WING MA1 FIRST FLOOR PLAN", "WING MB1 FIRST FLOOR PLAN", ("MA1", "MB1")), "VAV", 6, None),
    ("FINAL6 F5 FIRST FLOOR PLAN twice in one document",
     _r6_two_sheets("FIRST FLOOR PLAN", "FIRST FLOOR PLAN", ("M-101", "M-201")), "VAV", 3, 6),
    ("FINAL6 F6 M-101 on two pages with other text", _r6_number_two_pages, "VAV", 7, None),
    ("FINAL6 F7 piping plan names VAV-2 and 3 in notes", _r6_notes_overlay, "VAV", 3, None),
    ("FINAL7 F1 a 'copy' showing VAV-11 to 33 the other lacks", _r7_superset, "VAV", 9, None),
    ("FINAL7 F2 undated Rev 1 adds VAV-34", lambda: (r7._revision_job(), base._reading()), "VAV", 10, None),
    ("FINAL7 F3 a typical sheet of another set", _r7_typical_other_set, "VAV", 30, None),
    ("FINAL7 F5 BUILDING A / BUILDING B titles, tags reused",
     lambda: (r7._two_buildings("BUILDING B LEVEL {n} PLAN"), base._reading()), "VAV", 18, None),
    ("FINAL7 F5 guard: same titles and units",
     lambda: (r7._two_buildings("BUILDING A LEVEL {n} PLAN"), base._reading()), "VAV", 9, 18),
    ("FINAL7 F7 M-101 on three pages, 1 and 3 alike", _r7_three_pages, "VAV", 10, None),
    *[(f"FINAL7 table {n + 1}: " + " | ".join(text.replace("\n", " / ") for _t, text in plans),
       _r7_row(plans, tags), family, low, other)
      for n, ((plans, tags, family), (low, other)) in enumerate(zip(r7._AGREE, _R7_TRUTH))],
]


def _status(inventory: int, dossier: int, line: str, truth_: int, either: int | None) -> str:
    notes = line.split("Reading notes:", 1)[1] if "Reading notes:" in line else ""
    if min(inventory, dossier) < truth_:
        return "BELOW, noted" if notes else "BELOW, SILENT"
    if either is not None and min(inventory, dossier) < either:
        return "ok, the other count said" if str(either) in notes else "ok, the other count not said"
    return "ok"


_H3 = pytest.mark.xfail(strict=True, reason="REVIEW-FINAL8 H3 (the label reader): 'CUH-A (TYP. OF 4)' reads as "
                       "one place; REVIEW-FINAL7 names four places right (its rule 4, LOW), FINAL-N left it (concern "
                       "3), and the counts line says nothing: 1 where 4 is right, silent")
TABLE = [pytest.param(*row, id=row[0][:70]) for row in ROWS]   # FINAL-O H3: row 21 reads 4 places; _H3 kept unused


@pytest.mark.parametrize("name, build, family, truth_, either", TABLE)
def test_regression_table_row(tmp_path, name, build, family, truth_, either):
    catalogue, reading = build()
    inventory, dossier, line = both(catalogue, reading, family, tmp_path)
    status = _status(inventory, dossier, line, truth_, either)
    print(f"\nROW | {name} | {family} | {inventory} | {dossier} | {truth_}"
          f"{'' if either is None else ' or ' + str(either)} | {status}")
    assert status != "BELOW, SILENT", (name, inventory, dossier, line)


# REVIEW-FINAL7 section 2's probe: the 24 single lines it found lost (no label) on 1c45bed
_LOST = ["AHU-1 SUPPLY", "EF-2 EXHAUST", "EF-2 ON ROOF", "RTU-1 ON ROOF", "VAV-3 450 CFM", "VAV-3 OFFICE 101",
         "VAV-3 RM 101", "VAV-101 (OFFICE 101)", "VAV-3 SA", "VAV-3 ABOVE CLG", "VAV-3 x2", "2-VAV-3", "(VAV-3)",
         "[VAV-3]", "<VAV-3>", "VAV-3.", "VAV-3:", "FCU-4 / FCU-5", "FCU-4/FCU-5", "FCU-4 & FCU-5",
         "VAV-1 THRU VAV-5", "VAV-\n3", "CUH-A (TYP. OF 4)", "CUH-A TYP OF 4"]


@pytest.mark.parametrize("line", _LOST)
def test_guard_every_line_the_final7_probe_lost_is_a_label_of_each_tag_it_names(line):
    from estimator.catalogue.tags import label_keys, line_labels
    tags = ["AHU-1", "EF-2", "RTU-1", "VAV-3", "VAV-101", "FCU-4", "FCU-5", "VAV-1", "VAV-2", "VAV-4", "VAV-5", "CUH-A"]
    named = {t for t in tags if re.search(rf"(?<![A-Z0-9]){re.escape(t)}(?![0-9])", line.replace("-\n", "-"))}
    named |= {"VAV-2", "VAV-3", "VAV-4"} if "THRU" in line else set()
    found = line_labels(line, label_keys(tags))
    assert named and all(found.get(t, 0) >= 1 for t in named), (line, found)


def test_a_number_printed_again_in_one_document_never_drops_another_documents_other_page(tmp_path):
    inventory, dossier, lines, counted = read(_typical_number_in_another_document(), tmp_path)
    assert inventory["VAV"] >= 8 and dossier["VAV"] >= 8 and counted[1]["VAV"] == 8


def _typical_number_in_another_document():
    """Mech.pdf prints M-101 (VAV-11, 12) on pages 1 and 2 with the same text: one plan for two floors. Second
    Building.pdf has its own M-101 on two pages of other text: VAV-21 on page 1, VAV-25 to 29 on page 2."""
    mech, other = "Drawings/Mech.pdf", "Drawings/Second Building.pdf"
    return _minimal([(mech, 1, "M-101", "HVAC LEVEL 1 PLAN", 0, ["VAV-11", "VAV-12"], "plan"),
                     (mech, 2, "M-101", "HVAC LEVEL 1 PLAN", 0, ["VAV-11", "VAV-12"], "alike"),
                     (other, 1, "M-101", "HVAC LEVEL 1 PLAN", 1, ["VAV-21"], "plan"),
                     (other, 2, "M-101", "HVAC LEVEL 1 PLAN", 1, [f"VAV-2{k}" for k in range(5, 10)], "plan")],
                    {mech: ("drawings", "base"), other: ("drawings", "base")})


def test_guard_the_h4_case_counts_every_page_by_its_own_documents_floors(tmp_path):
    """Pinned b76d9c1's silent low count (6, 6, 3 distinct tags); FINAL-O H4 keys the typical sheet and its floors by
    (document, sheet number): Mech.pdf's M-101, printed twice alike, is 2 floors (VAV-11, 12: 4); Second Building.pdf's
    two pages of other text are each read once (1 + 5): 10, the code's own floors rule, every tag named."""
    inventory, dossier, lines, counted = read(_typical_number_in_another_document(), tmp_path)
    assert (inventory["VAV"], dossier["VAV"], counted[1]["VAV"]) == (10, 10, 8)


# ---- CHECK 2, the rest: inputs the reports give in prose, and the inventory items the Evidence Package prices ------

def _r4_prose(titles):
    return _r4_one_document(titles)


def _r4_no_common_tags():
    """REVIEW-FINAL4 F1: "the same happens with no tags in common at all": BASEMENT 1 and 2, other heaters on each."""
    other = r4.TYPICAL.replace("EBB-A", "EBB-E").replace("EBB-B", "EBB-F").replace("EBB-C", "EBB-G").replace(
        "EBB-D", "EBB-H")
    pages = [base._page(base.DWG, 1, r4.TYPICAL), base._page(base.DWG, 2, other)]
    sheets = [base._sheet(1, "M-101", "BASEMENT 1 MECHANICAL PLAN"),
              base._sheet(2, "M-102", "BASEMENT 2 MECHANICAL PLAN")]
    tags = r4.TYPICAL_TAGS + ["EBB-E", "EBB-F", "EBB-G", "EBB-H"]
    return base._catalogue(pages, sheets, tags), base._reading()


def _r5_f7(family_text, tags):
    """REVIEW-FINAL5 F7: two identical buildings issued as two documents, both M-101 FIRST FLOOR PLAN, same text."""
    def build():
        pages = [base._page(base.DWG, 1, family_text), base._page(base.OTHER, 1, family_text)]
        sheets = [base._sheet(1, "M-101", "FIRST FLOOR PLAN"), base._sheet(1, "M-101", "FIRST FLOOR PLAN", base.OTHER)]
        return (base._catalogue(pages, sheets, tags, [base._doc(base.DWG, 1), base._doc(base.OTHER, 1)]),
                base._reading())
    return build


PROSE_ROWS = [
    *[(f"FINAL4 F1 (prose) {a} / {b}", _r4_prose((a, b)), "EBB", 16, None)
      for a, b in (("FIRST FLOOR PLAN - QUADRANT A", "FIRST FLOOR PLAN - QUADRANT B"),
                   ("FIRST FLOOR PLAN - EXISTING", "FIRST FLOOR PLAN - NEW"),
                   ("FIRST FLOOR PLAN - OPTION 1", "FIRST FLOOR PLAN - OPTION 2"),
                   ("FIRST FLOOR PLAN - LEFT", "FIRST FLOOR PLAN - RIGHT"),
                   ("FIRST FLOOR PLAN - GYM", "FIRST FLOOR PLAN - LIBRARY"),
                   ("FIRST FLOOR PLAN - A", "FIRST FLOOR PLAN - B"))],
    ("FINAL4 F1 (prose) BASEMENT 1 / 2 with no tags in common", _r4_no_common_tags, "EBB", 16, None),
    ("FINAL5 F7 (prose) two identical buildings, AHU-1 to 3",
     _r5_f7("AHU-1\nAHU-2\nAHU-3", ["AHU-1", "AHU-2", "AHU-3"]),
     "AHU", 3, 6),
    ("FINAL5 F7 (prose) two identical buildings, EBB types of 7", _r5_f7(
        "\n".join(["EBB-A"] * 4 + ["EBB-B"] * 2 + ["EBB-C"]), ["EBB-A", "EBB-B", "EBB-C"]), "EBB", 14, None),
]


@pytest.mark.parametrize("name, build, family, truth_, either", PROSE_ROWS, ids=[r[0][:70] for r in PROSE_ROWS])
def test_regression_table_prose_row(tmp_path, name, build, family, truth_, either):
    catalogue, reading = build()
    inventory, dossier, line = both(catalogue, reading, family, tmp_path)
    status = _status(inventory, dossier, line, truth_, either)
    print(f"\nROW | {name} | {family} | {inventory} | {dossier} | {truth_}"
          f"{'' if either is None else ' or ' + str(either)} | {status}")
    assert status != "BELOW, SILENT", (name, inventory, dossier, line)


def _items(catalogue, schedules, typicals=()):
    from estimator.reading.inventory import build_inventory
    supersessions = supersede(catalogue, sheet_versions(catalogue))[0]
    pages = governing_pages(catalogue, supersessions, [t.sheet for t in typicals])
    items, _totals, _flags = build_inventory(catalogue, schedules, typicals, pages)
    return {i.tag: i for i in items}


def _f6_f1():
    from estimator.reading.schedules import Schedule, ScheduleRow
    schedule = Schedule(base.DWG, 9, "M-601", "EXHAUST FAN SCHEDULE", ("TAG", "QUANTITY"),
                        (ScheduleRow("EF-1", {"TAG": "EF-1", "QUANTITY": ""}, None, None, False),), False, (), (),
                        False)
    pages = [base._page(base.DWG, 1, "EF-1\nEF-1\nEF-1"), base._page(base.DWG, 9, "SCHEDULE\nEF-1")]
    sheets = [base._sheet(1, "M-101", "LEVEL 1 PLAN"), r6._schedules_sheet()]
    return base._catalogue(pages, sheets, ["EF-1"]), [schedule], (), ["EF-1"]


def _f6_f7():
    pages = [base._page(base.DWG, 1, "\n".join(r6.UNITS)), base._page(base.DWG, 2, "VAV-1\nTO VAV-2\nTO VAV-3"),
             base._page(base.DWG, 9, "SCHEDULE\n" + "\n".join(r6.UNITS))]
    sheets = [base._sheet(1, "M-101", "HVAC DUCTWORK FIRST FLOOR PLAN"),
              base._sheet(2, "M-201", "HVAC PIPING FIRST FLOOR PLAN"), r6._schedules_sheet()]
    return base._catalogue(pages, sheets, r6.UNITS), [base._schedule("VAV SCHEDULE", r6.UNITS, 9)], (), r6.UNITS


def _f6_f8():
    pages = [base._page(base.DWG, 1, "EF-1"), base._page(base.DWG, 2, "EF-1"),
             base._page(base.DWG, 9, "SCHEDULE\nEF-1"),
             base._page(base.DWG, 10, "SCHEDULE\nEF-1")]
    sheets = [base._sheet(1, "M-101", "LEVEL 1 PLAN"), base._sheet(2, "M-102", "LEVEL 2 PLAN"), r6._schedules_sheet(),
              base._sheet(10, "M-602", "SCHEDULES", types=("Schedules",))]
    schedules = [base._schedule("FAN SCHEDULE", ["EF-1"], 9), base._schedule("FAN SCHEDULE 2", ["EF-1"], 10,
                                                                             sheet="M-602")]
    return base._catalogue(pages, sheets, ["EF-1"]), schedules, (), ["EF-1"]


def _f5_f4_typical():
    _items_, catalogue, reading = r5._scheduled_job(["FCU-1\nFCU-1\nFCU-1"], [("M-102", "TYPICAL FLOOR PLAN")],
                                                    ["FCU-1"], [("M-102", range(2, 12))])
    return catalogue, reading.schedules, reading.typicals, ["FCU-1"]


def _f5_f4_type():
    _items_, catalogue, reading = r5._scheduled_job(["EBB-A", "EBB-A"],
                                                    [("M-101", "LEVEL 1 PLAN"), ("M-102", "LEVEL 2 PLAN")], ["EBB-A"])
    return catalogue, reading.schedules, reading.typicals, ["EBB-A"]


# (name, build, truth of the items' quantities, the other count where open)
ITEM_ROWS = [
    ("FINAL6 F1 EF-1 empty QUANTITY cell, drawn 3 times", _f6_f1, 3, None),
    ("FINAL6 F7 piping plan names VAV-2 and 3 in notes, schedule of 3", _f6_f7, 3, None),
    ("FINAL6 F8 EF-1 on two plans, listed on two schedules", _f6_f8, 1, None),      # T-005a ruling 2: one unit
    ("FINAL5 F4 FCU-1 x3 on a typical of 10 floors", _f5_f4_typical, 10, 30),
    ("FINAL5 F4 scheduled EBB-A once on each of two floors", _f5_f4_type, 2, None),
]


@pytest.mark.parametrize("name, build, truth_, either", ITEM_ROWS, ids=[r[0][:70] for r in ITEM_ROWS])
def test_regression_table_inventory_item_row(tmp_path, name, build, truth_, either):
    """The Evidence Package's own number: the inventory items' quantities, beside the dossier's plan placements."""
    catalogue, schedules, typicals, tags = build()
    items = _items(catalogue, schedules, typicals)
    quantity = sum(items[t].quantity or 0 for t in tags if t in items)
    reading = base._reading(schedules)
    reading.typicals = tuple(typicals)
    d = build_dossier(catalogue, reading, tmp_path)
    family = _prefix(tags[0])
    dossier = (d.counts.get(family) or {}).get("plan_placements", 0)
    print(f"\nROW | {name} | {family} | items {quantity} | {dossier} | {truth_}"
          f"{'' if either is None else ' or ' + str(either)} | {'ok' if min(quantity, dossier) >= truth_ else 'BELOW'}")
    assert min(quantity, dossier) >= truth_, (name, quantity, dossier)
