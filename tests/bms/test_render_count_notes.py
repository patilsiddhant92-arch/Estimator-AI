"""Fix run 2026-10-10, row 16 (HarkPro 203, ruling L2): the highest count prints, and every other count that differs
(schedule, plan, sequence, stated, a count with no place) prints with both numbers and where each one is: in the
block's "*Qty." note then, in brackets on the header line itself now (T-005e, ruling 15). No count difference is
silent. Invented data only: the sample fixtures."""
from __future__ import annotations

import itertools
import json
import re
from dataclasses import replace
from pathlib import Path

import pytest

from bms.model import Count, Device, Family, Job, OtherCount, Ref, System
from bms.playbook import load_playbook
from bms.render import render

FIXTURES = Path(__file__).resolve().parent / "fixtures"
PLAN = Ref("S1", "located on the sheet text", "M-101, Invented Set.pdf page 2")
SCHEDULE = Ref("S2", "quantity column total 4", "M-601, Invented Set.pdf page 9")
ROWS = Ref("S3", "schedule rows 4", "INVENTED EQUIPMENT SCHEDULE, Invented Set.pdf page 9")
PLACEMENTS = Ref("S4", "plan placements 4", "equipment counts for EF")
SEQUENCE = Ref("S5", "two fans run in sequence", "23 09 93 Invented Sequence, Invented Spec.pdf page 4")
STATED = Ref("S6", "EF-1 (TYP. OF 4)", "M-102, Invented Set.pdf page 3")
NO_PLACE = Ref("", "the count before the plan check, given without a source", "")


@pytest.fixture(scope="module")
def playbook():
    return load_playbook(FIXTURES / "sample_playbook")


@pytest.fixture
def job() -> Job:
    return Job.from_dict(json.loads((FIXTURES / "sample_job.json").read_text(encoding="utf-8")))


def device(quantity: Count, id: str = "X.d1") -> Device:
    return Device(id=id, slot="controller", name="DDC Controller", verb="Furnish and Install", furnished_by="AME",
                  installed_by="AME", wired_by="AME", quantity=quantity, refs=(PLAN,))


def block(families, devices, **kw) -> System:
    base = dict(key="EF", name="Exhaust Fans", shape="Exhaust Fan", control="field", families=tuple(families),
                devices=tuple(devices))
    base.update(kw)
    return System(**base)


def family(count: Count, name: str = "Exhaust Fan", tags=("EF-1", "EF-2")) -> Family:
    return Family(name, tags, count)


def notes(job: Job, playbook, system: System, key: str | None = None) -> list[str]:
    draft = render(replace(job, systems=(system,)), playbook)
    return [l.text for l in draft.lines if l.kind == "note" and l.system_key == (key if key is not None else system.key)]


def headers(job: Job, playbook, system: System) -> list[str]:
    """T-005e (ruling 15, 2026-10-11 afternoon): the other counts print in brackets on the header line itself, no
    separate "*Qty." note. The bracket of each header line of the block ("" when it has none)."""
    draft = render(replace(job, systems=(system,)), playbook)
    out = []
    for l in draft.lines:
        if l.kind == "header" and l.system_key == system.key:
            m = re.search(r"\(([^()]*)\)$", l.text)
            out.append(m.group(1) if m else "")
    return out


def numbers(text: str) -> set[int]:
    return {int(n) for n in re.findall(r"\d+", text)}


# ---- the highest prints; the other counts are named --------------------------------------------------------------

def test_the_highest_count_prints_and_the_lower_ones_are_named_with_their_places(job, playbook):
    count = Count(value=6, sources=(PLAN,), others=(OtherCount(4, SCHEDULE),))
    system = block([family(count)], [device(Count(value=6))])
    draft = render(replace(job, systems=(system,)), playbook)
    text = [l.text for l in draft.lines if l.system_key == "EF"]
    # T-005e (ruling 15): the other counts in brackets on the header, no "*Qty." note
    assert text[0] == "Qty (6) Exhaust Fans EF-1, 2 (6 per M-101; 4 per M-601)"
    assert not any(t.startswith("*Qty.") for t in text)


@pytest.mark.parametrize("other, place", [
    (SCHEDULE, "M-601"),                           # the schedule, by its sheet
    (ROWS, "schedule rows"),                       # the schedule, no sheet: what its quote counted
    (PLACEMENTS, "plan placements"),               # the plan, counted by the placements
    (PLAN, "M-101"),                               # a plan sheet
    (SEQUENCE, "23 09 93 Invented Sequence"),      # the sequence of operations, by its section
    (STATED, "M-102"),                             # a count stated by the sheet ("TYP. OF 4")
    (NO_PLACE, "elsewhere in the documents"),      # a count the documents give with no place
])
def test_every_kind_of_other_count_prints_with_its_number_and_its_place(job, playbook, other, place):
    count = Count(value=9, sources=(Ref("S9", "q", "M-900, Invented Set.pdf page 1"),),
                  others=(OtherCount(4, other),))
    system = block([family(count)], [device(Count(value=9))])
    assert notes(job, playbook, system) == []                # T-005e (ruling 15): no separate quantity note
    found = headers(job, playbook, system)                   # T-005e (ruling 15): in brackets on the header
    expected = f"9 per M-900; 4 {place}" if place == "elsewhere in the documents" else \
        f"9 per M-900; 4 per {place}"
    assert found == [expected]


def test_an_alternate_block_names_its_other_counts_too(job, playbook):
    count = Count(value=6, sources=(PLAN,), others=(OtherCount(4, SCHEDULE),))
    system = block([family(count)], [device(Count(value=6))], alternate="add")
    draft = render(replace(job, systems=(system,)), playbook)
    items = [i.runs[0].text for b in draft.scope.add_alternates[0].blocks for i in b.items if i.kind == "note"]
    assert items == []                                       # T-005e (ruling 15): no separate quantity note
    heads = [l.text for l in draft.lines if l.system_key == "EF" and l.kind == "header"]
    assert heads == ["Qty (6) Exhaust Fans EF-1, 2 (6 per M-101; 4 per M-601)"]      # T-005e (ruling 15)


def test_a_front_end_line_names_its_other_counts(job, playbook):
    line = replace(job.front_end.devices[0], quantity=Count(value=3, sources=(PLAN,),
                                                            others=(OtherCount(1, SCHEDULE),)))
    front = replace(job.front_end, devices=(line,))
    draft = render(replace(job, front_end=front), playbook)
    # T-005e addendum: a device's other counts print on its own line (GEM v4 ~609), not in a "*" note
    assert [l.text for l in draft.lines if l.system_key == "" and l.kind == "note"] == []
    assert [l.text for l in draft.lines if l.system_key == "" and l.kind == "line"][0].endswith(
        "Furnish and Install BMS Server Software and Graphics (Qty. 3 Total) (3 per M-101; 1 per M-601)")     # ruling 24


# ---- the silent cases this run closed ------------------------------------------------------------------------------

def test_a_printed_count_below_the_highest_with_no_source_is_named(job, playbook):
    """`value` 4 cites nothing and another source gives 6: the header prints 6 (the highest), and the 4 used to
    vanish. It prints now, with the plain words for a count that has no place."""
    count = Count(value=4, sources=(), others=(OtherCount(6, PLAN),))
    system = block([family(count)], [device(Count(value=6))])
    assert notes(job, playbook, system) == []                # T-005e (ruling 15): on the header, no note
    assert headers(job, playbook, system) == ["6 per M-101; 4 elsewhere in the documents"]


def test_a_device_quantity_below_the_highest_with_no_source_is_named(job, playbook):
    quantity = Count(value=2, sources=(), others=(OtherCount(5, PLAN),))
    system = block([family(Count(value=5, sources=(PLAN,)))], [device(quantity)])
    assert notes(job, playbook, system) == []           # T-005e addendum: on the device's own line (GEM v4 ~609)
    draft = render(replace(job, systems=(system,)), playbook)
    assert [l.text for l in draft.lines if l.device_id == "X.d1"] == [
        "Furnish and Install DDC Controller (Qty. 5 Total) (5 per M-101; 2 elsewhere in the documents)"]


def test_a_zero_below_the_highest_is_named_not_dropped(job, playbook):
    count = Count(value=0, sources=(), others=(OtherCount(3, PLAN),))
    system = block([family(count)], [device(Count(value=3))])
    assert notes(job, playbook, system) == []                # T-005e (ruling 15): on the header, no note
    assert headers(job, playbook, system) == ["3 per M-101; 0 elsewhere in the documents"]


def test_two_families_with_the_same_counts_each_name_their_own_note(job, playbook):
    """Two families that read the same numbers from the same sheets printed one part, under the first family only:
    the second family's counts were dropped."""
    same = Count(value=6, sources=(PLAN,), others=(OtherCount(4, SCHEDULE),))
    system = block([family(same, "Indoor Unit", ("IU-1",)), family(same, "Branch Selector", ("BS-1",))],
                   [device(Count(value=6))])
    # T-005e (ruling 15): each family's counts on its own header, no "*Qty." note
    assert notes(job, playbook, system) == []
    assert headers(job, playbook, system) == ["6 per M-101; 4 per M-601", "6 per M-101; 4 per M-601"]


def test_a_line_that_carries_its_familys_count_still_prints_it_once(job, playbook):
    same = Count(value=6, sources=(PLAN,), others=(OtherCount(4, SCHEDULE),))
    system = block([family(same)], [device(same)])
    assert notes(job, playbook, system) == []                # T-005e (ruling 15): on the header, once
    assert headers(job, playbook, system) == ["6 per M-101; 4 per M-601"]
    draft = render(replace(job, systems=(system,)), playbook)
    assert [l.text for l in draft.lines if l.device_id == "X.d1"] == ["Furnish and Install DDC Controller"]


# ---- no count difference is silent: every shape of a Count ----------------------------------------------------------

def _every_count():
    refs = (PLAN, SCHEDULE, NO_PLACE)
    values = (None, 0, 3, 5)
    others = [()]
    others += [((v, r),) for v in (0, 2, 3, 5, 7) for r in refs]
    others += [((a, r1), (b, r2)) for a, b in itertools.product((2, 5, 7), repeat=2)
               for r1, r2 in itertools.product((PLAN, NO_PLACE), repeat=2)]
    for value in values:
        for sources in ((), (PLAN,)):
            if value is None and sources:
                continue
            for extra in others:
                count = Count(value, sources, tuple(OtherCount(v, r) for v, r in extra))
                said = ([value] if value is not None else []) + [v for v, _ in extra]
                if said and any(n != max(said) for n in said):
                    yield count


def test_no_count_difference_is_silent(job, playbook):
    """For every Count that holds two different numbers, the header's bracket holds each number that does not print
    as the header's count (T-005e, ruling 15: the bracket on the header replaces the block's note)."""
    silent = []
    checked = 0
    for count in _every_count():
        said = ([count.value] if count.value is not None else []) + [o.value for o in count.others]
        top = max(said)
        system = block([family(count)], [device(Count(value=top))])
        shown = numbers(" ".join(headers(job, playbook, system)))     # T-005e (ruling 15)
        missing = {n for n in said if n != top} - shown
        checked += 1
        if missing:
            silent.append((count, sorted(missing)))
    assert checked > 200
    assert not silent, f"{len(silent)} counts print a number nowhere; the first: {silent[0]}"
