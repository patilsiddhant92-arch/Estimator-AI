"""T-010 task 2 (estimator ruling 25, 2026-10-12): a contradiction between sources prints in red in the block, never
as a plain bracket alone. A count contradiction (a family's other counts differ from the printed count) and an owner
contradiction (a device flagged "ownership" whose line and cited passage name AME and the unit manufacturer) each
print one red "*" line after the block's other "*" lines; the line is in the traced lines too. Invented fixtures
only: no job text, no real sheet number, no real tag list."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from bms.model import (Assumption, Clarification, Count, Device, Family, Header, Job, OtherCount, Ref, SetAside,
                       System)
from bms.playbook import load_playbook
from bms.render import render

ROOT = Path(__file__).resolve().parents[2]
P901 = Ref("S1", "plan placements 55", "M-901, Invented Set.pdf page 2")
ROWS = Ref("S2", "schedule rows 1", "INVENTED FAN COIL SCHEDULE, Invented Set.pdf page 9")
P902 = Ref("S3", "located on the sheet text", "M-902, Invented Set.pdf page 3")
SEQ_MFR = Ref("S4", "THE FREEZESTAT SHALL BE FURNISHED BY THE UNIT MANUFACTURER",
              "23 09 93 Invented Sequence, Invented Spec.pdf page 4")
ROW_MFR = Ref("S5", "FILTER SWITCH FURNISHED BY THE UNIT MANUFACTURER",
              "INVENTED UNIT SCHEDULE, Invented Set.pdf page 9")
OWNER_WHAT = "this line has it furnished by AME"
OWNER_WHY = "the cited schedule or sequence says furnished by Unit Mfr.; confirm who will furnish it"


@pytest.fixture(scope="module")
def pb():
    return load_playbook(ROOT / "playbook")


def device(id="FC.d1", slot="controller", name="DDC Controller", qty=55, **kw) -> Device:
    base = dict(id=id, slot=slot, name=name, verb="Furnish and Install", furnished_by="AME", installed_by="AME",
                wired_by="AME", quantity=Count(value=qty), refs=(P901,))
    base.update(kw)
    return Device(**base)


def owner_device(id="FC.d2", name="Freezestat", refs=(SEQ_MFR,), **kw) -> Device:
    base = dict(id=id, slot="other_device", name=name, verb="Furnish and Wire", furnished_by="AME",
                installed_by="AME", wired_by="AME", refs=refs, flag="ownership",
                assumption=Assumption(OWNER_WHAT, OWNER_WHY))
    base.update(kw)
    return device(**base)


def contested(value=55, others=((1, ROWS), (1, P902))) -> Count:
    return Count(value=value, sources=(P901,), others=tuple(OtherCount(v, r) for v, r in others))


def system(families=None, devices=None, **kw) -> System:
    base = dict(key="FC", name="Fan Coil Units", shape="Fan Coil Unit", control="field",
                families=families or (Family("Fan Coil Unit", ("FC-1", "FC-2"), contested()),),
                devices=tuple(devices or (device(),)))
    base.update(kw)
    return System(**base)


def job(*systems, set_aside=()) -> Job:
    return Job(name="Invented", systems=tuple(systems), set_aside=tuple(set_aside),
               header=Header("00-0000", "Invented", "Invented", ("A",), "2026-10-04"))


def notes(block) -> list[tuple[str, bool]]:
    return [(i.runs[0].text, i.runs[0].red) for i in block.items if i.kind == "note"]


def last_block(draft, key_header: str):
    blocks = [b for b in draft.scope.blocks if b.items]
    (block,) = [b for b in blocks if any(key_header in h for h in [b.header])] or blocks[-1:]
    return block


def red_notes(draft) -> list[str]:
    return [i.runs[0].text for b in draft.scope.blocks for i in b.items if i.kind == "note" and i.runs[0].red]


def traced_notes(draft, key="FC") -> list[str]:
    return [l.text for l in draft.lines if l.kind == "note" and l.system_key == key]


def numbers(text: str) -> list[int]:
    return [int(n) for n in re.findall(r"(?<![-\w])(\d+)(?= per)", text)]


# ---- 1. a count contradiction prints one red "*" line, after the other "*" lines, and is traced ----------------

def test_a_contested_family_count_prints_one_red_star_line_after_the_other_notes(pb):
    s = system(clarifications=(Clarification("note", "Invented note text"),))
    draft = render(job(s), pb)
    (block,) = [b for b in draft.scope.blocks if b.items]
    items = notes(block)
    red = [t for t, r in items if r]
    assert len(red) == 1
    (line,) = red
    assert line.startswith("*")
    assert "55" in line and "1 per schedule rows" in line and "M-901" in line and "M-902" in line
    assert "schedule rows" in line
    assert line.index("55") < line.index("1 per")          # highest first
    assert items[-1] == (line, True)                       # after the block's other "*" lines
    assert any(not r for t, r in items)                    # the black note is still there, before it
    assert line in traced_notes(draft)
    assert traced_notes(draft)[-1] == line
    # the header bracket stays
    header = [l.text for l in draft.lines if l.kind == "header"][0]
    assert "(55 per M-901; 1 per schedule rows; 1 per M-902)" in header


# ---- 2. no red line for one count, for equal others, or for a sum that is alone --------------------------------

def test_one_count_or_equal_others_or_a_lone_sum_print_no_red_line(pb):
    one = system(families=(Family("Fan Coil Unit", ("FC-1",), Count(value=55, sources=(P901,))),))
    equal = system(families=(Family("Fan Coil Unit", ("FC-1",), contested(others=((55, ROWS),))),))
    summed = system(families=(Family("Fan Coil Unit", ("FC-1",),
                                     Count(value=55, sources=(P901,), added_up=OtherCount(60, P902))),))
    for s in (one, equal, summed):
        assert red_notes(render(job(s), pb)) == []


# ---- 3. two contested families in one block print one line each ------------------------------------------------

def test_two_contested_families_print_one_red_line_each(pb):
    rows = Ref("S8", "schedule rows 3", "INVENTED HEATER SCHEDULE, Invented Set.pdf page 9")
    families = (Family("Fan Coil Unit", ("FC-1",), contested()),
                Family("Cabinet Unit Heater", ("CH-1",), contested(value=7, others=((3, rows),))))
    draft = render(job(system(families=families)), pb)
    red = red_notes(draft)
    assert len(red) == 2
    assert "Fan Coil Unit" in red[0] and "55" in red[0]
    assert "Cabinet Unit Heater" in red[1] and "7" in red[1] and "3 per schedule rows" in red[1]
    assert all(t in traced_notes(draft) for t in red)


# ---- 4. an owner contradiction prints one red line naming both parties; the black *Assumed goes ----------------

def test_an_ownership_contest_prints_one_red_line_with_both_parties_and_no_black_assumed(pb):
    s = system(families=(Family("Fan Coil Unit", ("FC-1",), Count(value=55, sources=(P901,))),),
               devices=(device(), owner_device()))
    draft = render(job(s), pb)
    red = red_notes(draft)
    assert len(red) == 1
    (line,) = red
    assert line.startswith("*Freezestat")
    assert "AME" in line and "Unit Mfr." in line
    assert not any(t.startswith("*Assumed") for t in traced_notes(draft))
    assert traced_notes(draft).count(line) == 1
    assert sum("Unit Mfr." in t for t in traced_notes(draft)) == 1     # the contradiction prints once


def test_an_ownership_contest_cited_on_a_schedule_row_also_prints_red(pb):
    d = owner_device(name="Dirty Filter Switch", refs=(ROW_MFR,))
    s = system(families=(Family("Fan Coil Unit", ("FC-1",), Count(value=55, sources=(P901,))),),
               devices=(device(), d))
    red = red_notes(render(job(s), pb))
    assert len(red) == 1 and red[0].startswith("*Dirty Filter Switch") and "AME" in red[0] and "Unit Mfr." in red[0]


def test_an_ownership_flag_against_another_party_keeps_the_black_assumed_line(pb):
    """Ruling 25 names AME against the unit manufacturer: a contest with another party stays as it was."""
    ec = Ref("S6", "SWITCH WIRED BY THE ELECTRICAL CONTRACTOR", "M-903, Invented Set.pdf page 4")
    d = owner_device(name="Dirty Filter Switch", refs=(ec,),
                     assumption=Assumption("this line has it wired by AME",
                                           "the cited schedule or sequence says wired by Electrical Contractor"))
    s = system(families=(Family("Fan Coil Unit", ("FC-1",), Count(value=55, sources=(P901,))),),
               devices=(device(), d))
    draft = render(job(s), pb)
    assert red_notes(draft) == []
    assert any(t.startswith("*Assumed") for t in traced_notes(draft))


def test_an_ownership_contest_the_quotes_do_not_settle_is_read_from_the_assumption(pb):
    """No cited quote says who furnishes it: the assumption's what names AME and its why the unit manufacturer."""
    plain = Ref("S9", "FREEZESTAT AT COIL LEAVING AIR", "23 09 93 Invented Sequence, Invented Spec.pdf page 4")
    d = owner_device(refs=(plain,), assumption=Assumption("furnished by AME",
                                                          "the unit manufacturer may furnish it with the unit"))
    s = system(families=(Family("Fan Coil Unit", ("FC-1",), Count(value=55, sources=(P901,))),),
               devices=(device(), d))
    draft = render(job(s), pb)
    red = red_notes(draft)
    assert len(red) == 1 and red[0].startswith("*Freezestat: ") and "AME" in red[0] and "manufacturer" in red[0]
    assert not any(t.startswith("*Assumed") for t in traced_notes(draft))


# ---- 5. a plain "assumed" flag keeps its black *Assumed line ---------------------------------------------------

def test_an_assumed_flag_keeps_its_black_assumed_line(pb):
    d = device(id="FC.d2", slot="other_device", name="Freezestat", flag="assumed",
               assumption=Assumption("one freezestat per unit", "the sequence names a low limit on each unit"))
    s = system(families=(Family("Fan Coil Unit", ("FC-1",), Count(value=55, sources=(P901,))),),
               devices=(device(), d))
    draft = render(job(s), pb)
    assert red_notes(draft) == []
    black = [t for t, r in notes([b for b in draft.scope.blocks if b.items][0]) if not r]
    assert any(t.startswith("*Assumed") and "one freezestat per unit" in t for t in black)


# ---- 6. a long contradiction prints as short lines of 160 characters or less, no number lost --------------------

def test_a_long_count_contradiction_prints_as_short_lines_with_every_number(pb):
    others = tuple((n, Ref(f"S{10 + n}", "located on the sheet text", f"M-9{n:02d}, Invented Set.pdf page {n}"))
                   for n in range(1, 20))
    s = system(families=(Family("Fan Coil Unit", ("FC-1",), contested(value=55, others=others)),))
    draft = render(job(s), pb)
    red = red_notes(draft)
    assert len(red) > 1
    assert all(len(t) <= 160 and t.startswith("*") for t in red)
    joined = " ".join(red)
    for n in range(1, 20):
        assert f"{n} per M-9{n:02d}" in joined
    assert "55" in joined
    assert all(t in traced_notes(draft) for t in red)


def test_a_family_with_a_set_aside_and_other_counts_prints_both_lines(pb):
    """The set-aside line ("counted once") stays black; the count contradiction prints red after it."""
    aside = SetAside(family="FC", value=4, reason="same unit labelled again",
                     ref=Ref("S7", "FC-1 labelled again", "M-904, Invented Set.pdf page 5"), note="M-905")
    draft = render(job(system(), set_aside=(aside,)), pb)
    items = notes([b for b in draft.scope.blocks if b.items][0])
    black = [t for t, r in items if not r]
    red = [t for t, r in items if r]
    assert any("counted once" in t for t in black)
    assert len(red) == 1 and items[-1] == (red[0], True)


# ---- 7. the step adds nothing to the model ---------------------------------------------------------------------

def test_the_job_round_trips_unchanged(pb):
    s = system(devices=(device(), owner_device()))
    j = job(s)
    render(j, pb)
    assert Job.from_json(j.to_json()) == j
    assert Job.from_json(j.to_json()).to_json() == j.to_json()
