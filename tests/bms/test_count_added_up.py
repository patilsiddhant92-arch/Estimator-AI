"""Ruling L1 (fix run 2026-10-10, countsum): plan sheets of one floor and area are not added together. When that makes
a family's count lower than the sheets add up to, the Count keeps the plain sum in `added_up`: it is never the printed
count (`Count.highest()` prints, ruling L2), and the client's "*Qty." note names both numbers, as the review page and
the Evidence Package do. Invented data only: the sample fixtures and invented sheets."""
from __future__ import annotations

import copy
import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from estimator.ledger.facts import SETTLED
from estimator.reading.inventory import build_inventory
from estimator.writing.dossier import Dossier

from bms import ai, counts, review
from bms.evidence import SCOPE_HEADINGS, scope_rows
from bms.model import Count, Decision, Family, Job, OtherCount, Ref
from bms.playbook import load_playbook
from bms.plan import _reduced, plan_job
from bms.plan_read import Reader
from bms.render import render
from bms.validate import RULE, _count_problems, validate

from test_ai import FakeTransport, skeleton
from test_ai import dossier, raw  # noqa: F401  (fixtures)
from test_counts import _family as family_of
from test_counts import _plan as counted_plan
from test_counts import _sample_job
from test_plan import L2_DUCT, L2_PIPE, L3_DUCT, PLAYBOOK, _cuh_job, _family, _ledger, _sheet_dossier
from test_render_count_notes import PLAN, SCHEDULE, STATED, block, device, family, headers, notes
from test_review_typed_counts import NODE, decide
from test_review_typed_counts import device_card, family_card

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_inventory_same_floor import SCHEDULES, _schedule as inventory_schedule      # noqa: E402
from test_inventory_same_floor import _catalogue as inventory_catalogue               # noqa: E402
from test_inventory_same_floor import _plan as inventory_plan                         # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"
PB = load_playbook(FIXTURES / "sample_playbook")
SUM = OtherCount(9, STATED)           # the sheets added up: 9, above the printed 6
SAID = "9 if every sheet of the same floor and area is added up"


@pytest.fixture
def job() -> Job:
    return Job.from_dict(json.loads((FIXTURES / "sample_job.json").read_text(encoding="utf-8")))


@pytest.fixture(scope="module")
def playbook():
    return PB


def edit(job: Job, key: str, **changes) -> Job:
    return job.with_system(replace(job.system(key), **changes))


# ---- the plan: the sum is kept only when it is above the printed count ----------------------------------------------

def test_a_family_the_rule_lowered_carries_the_sum_beside_the_printed_count():
    dossier = _sheet_dossier(("M-101", 3, L2_DUCT, "CUH-A (TYP. OF 4)"), ("M-201", 4, L2_PIPE, "CUH-A (TYP. OF 4)"))
    count = _cuh_job(dossier).systems[0].families[0].count
    assert count.value == 4 and count.highest() == 4                     # the printed count is the one-plan count
    assert count.added_up == OtherCount(8, count.sources[0])             # the sheets added up, from a sheet that states it
    assert count.sources[0].source_id == "D7" and count.sources[0].where == "M-101, Drawings.pdf page 3"
    assert count.others == ()                                            # the sum is no other count: it would print


def test_the_sum_stays_on_the_family_the_job_saves_and_loads():
    dossier = _sheet_dossier(("M-101", 3, L2_DUCT, "CUH-A (TYP. OF 4)"), ("M-201", 4, L2_PIPE, "CUH-A (TYP. OF 4)"))
    job = _cuh_job(dossier)
    assert Job.from_dict(json.loads(json.dumps(job.to_dict()))) == job
    assert job.systems[0].families[0].count.added_up.value == 8


def test_the_sum_is_every_stated_count_added_over_every_sheet():
    dossier = _sheet_dossier(("M-101", 3, L2_DUCT, "CUH-A (TYP. OF 4)"), ("M-201", 4, L2_PIPE, "CUH-A (TYP. OF 4)"),
                             ("M-102", 5, L3_DUCT, "CUH-A (TYP. OF 4)"))
    count = _cuh_job(dossier).systems[0].families[0].count
    assert count.value == 8 and count.added_up == OtherCount(12, count.sources[0])      # 4 + 4 counted, 12 added up


def test_two_floors_that_add_up_leave_no_sum_to_name():
    dossier = _sheet_dossier(("M-101", 3, L2_DUCT, "CUH-A (TYP. OF 4)"), ("M-102", 5, L3_DUCT, "CUH-A (TYP. OF 4)"))
    count = _cuh_job(dossier).systems[0].families[0].count
    assert count.value == 8 and count.added_up is None


def test_one_sheet_that_states_a_count_leaves_no_sum_to_name():
    dossier = _sheet_dossier(("M-101", 3, L2_DUCT, "CUH-A (TYP. OF 4)"))
    count = _cuh_job(dossier).systems[0].families[0].count
    assert count.value == 4 and count.added_up is None


@pytest.mark.parametrize("scheduled", [8, 9, 20])
def test_no_sum_is_kept_when_the_printed_count_is_not_below_it(scheduled):
    """A schedule quantity at or above the sheets' sum prints (the highest prints); the sum is then no number to name."""
    dossier = _sheet_dossier(("M-101", 3, L2_DUCT, "CUH-A (TYP. OF 4)"), ("M-201", 4, L2_PIPE, "CUH-A (TYP. OF 4)"))
    count = _cuh_job(dossier, count=scheduled).systems[0].families[0].count
    assert count.value == scheduled and count.added_up is None


def test_a_schedule_quantity_between_the_two_numbers_prints_and_the_sum_is_kept():
    dossier = _sheet_dossier(("M-101", 3, L2_DUCT, "CUH-A (TYP. OF 4)"), ("M-201", 4, L2_PIPE, "CUH-A (TYP. OF 4)"))
    count = _cuh_job(dossier, count=6).systems[0].families[0].count
    assert count.value == 6 and count.added_up.value == 8
    assert [o.value for o in count.others] == [4]                        # the one-plan count is another count, named


def test_a_part_of_a_family_never_carries_the_whole_family_sum():
    count = Count(6, (PLAN,), (OtherCount(4, SCHEDULE),), SUM)
    part = _reduced(count, 5)                     # a group's part: another number of its own, sources of the family
    assert part.value == 5 and part.added_up is None


# ---- the plan: the dossier's family totals, scheduled units counted once for the sheets of one floor and area --------

COUNTS_LINE = "equipment counts for VAV (schedules and plans)"
FOUR = "\n".join(f"VAV-{n}" for n in range(1, 5))
TWO_TRADES = (inventory_plan("M-201", "LEVEL 4 HVAC DUCTWORK PLAN", FOUR),
              inventory_plan("M-301", "LEVEL 4 HVAC ZONING PLAN", FOUR))


def vav_totals(*plans):
    """The family totals the inventory gives four scheduled VAV boxes drawn on `plans`."""
    catalogue = inventory_catalogue([SCHEDULES, *plans])
    return build_inventory(catalogue, [inventory_schedule(*[f"VAV-{n}" for n in range(1, 5)])])[1]


def vav_job(totals, count=4, sources=None, group=None, sheets=()):
    """The planned job of a ledger that lists the four boxes with `count`, and the dossier whose counts line holds the
    totals' flags (the reading notes of the line, as `build_dossier` writes them). `group` is a group fact's value (it
    takes part of the family: "VAV (VAV-1, VAV-2)"); `sheets` are (number, page, title, text) lines of sheet text."""
    ledger = _ledger()
    _family(ledger, "VAV", "Variable Air Volume Box", "VAV-1 thru 4", count)
    if group:
        ledger.add("group", "Group A", group, "S5", "Group A riser", "risers", SETTLED)
    notes_line = "; ".join(flag for total in totals for flag in total.flags)
    text = f"[S9] VAV (Variable Air Volume Box): schedule rows 4; plan placements 4. Reading notes: {notes_line}.\n"
    where = {"S9": COUNTS_LINE} if sources is None else dict(sources)
    for n, (number, page, title, said) in enumerate(sheets, start=7):
        text += f"[D{n}] {number}, Drawings.pdf page {page} {title}: {said}\n"
        where[f"D{n}"] = f"{number}, Drawings.pdf page {page} (sheet text)"
    dossier = Dossier(job_name="Invented Job", text=text, images=(), sources=where, families=tuple(totals),
                      device_totals={}, counts={}, stats={})
    return plan_job(ledger, None, dossier, PLAYBOOK), dossier


def test_scheduled_units_drawn_on_two_plans_of_one_floor_carry_the_inventorys_sum():
    totals = vav_totals(*TWO_TRADES)
    assert (totals[0].scheduled, totals[0].summed) == (4, 8)                 # counted once; 8 if the sheets were added
    job, dossier = vav_job(totals)
    count = job.systems[0].families[0].count
    assert count.value == 4 and count.added_up.value == 8 and count.others == ()
    ref = count.added_up.ref                        # cited by the family's counts line, in the words of its flag
    assert (ref.source_id, ref.where) == ("S9", "equipment counts for VAV")
    assert "4 units counted, 8 if the sheets were added up" in ref.quote and ref.quote in dossier.text
    assert Job.from_dict(json.loads(json.dumps(job.to_dict()))) == job


def test_units_drawn_on_one_plan_have_no_sum_to_name():
    totals = vav_totals(inventory_plan("M-201", "LEVEL 4 HVAC DUCTWORK PLAN", FOUR))
    assert totals[0].summed is None
    assert vav_job(totals)[0].systems[0].families[0].count.added_up is None


@pytest.mark.parametrize("printed", [8, 9, 20])
def test_a_printed_count_not_below_the_inventorys_sum_names_none(printed):
    count = vav_job(vav_totals(*TWO_TRADES), count=printed)[0].systems[0].families[0].count
    assert count.value == printed and count.added_up is None


def test_a_printed_count_between_the_two_numbers_still_names_the_sum():
    count = vav_job(vav_totals(*TWO_TRADES), count=6)[0].systems[0].families[0].count
    assert count.value == 6 and count.added_up.value == 8


def test_a_sum_the_dossier_cannot_cite_is_not_kept():
    """No counts line for the family among the dossier's sources: there is no place to cite, so no sum is kept."""
    count = vav_job(vav_totals(*TWO_TRADES), sources={})[0].systems[0].families[0].count
    assert count.value == 4 and count.added_up is None


# ---- a family split between blocks: no block keeps the sum, so one question names both numbers -------------------

TAKES_TWO = "VAV (VAV-1, VAV-2)"             # a group that takes two of the four boxes: the family is in two blocks
ADDED_8 = "8 if every sheet of the same floor and area is added up"


def sum_questions(job: Job) -> list[str]:
    return [q for q in job.questions if "added up" in q]


def test_a_family_split_between_blocks_names_the_inventorys_sum_in_one_question():
    """Each part's count is made smaller (`_reduced`), which leaves the sum out of both blocks: the planner asks, once,
    with the printed count and the sum, each with its place, and the blocks the family is in."""
    job, _ = vav_job(vav_totals(*TWO_TRADES), group=TAKES_TWO)
    assert len(job.systems) == 2
    assert [f.count.added_up for s in job.systems for f in s.families] == [None, None]     # no block's note has it
    [asked] = sum_questions(job)
    assert "Variable Air Volume Box (VAV)" in asked
    assert "4 per M-501" in asked and ADDED_8 in asked                  # both numbers, each with its place
    assert "per equipment counts for VAV" in asked
    assert all(system.name in asked for system in job.systems)          # the blocks the family is in


def test_a_family_in_one_block_leaves_its_sum_to_that_blocks_note():
    """The block's family keeps the sum (its "*" note and its review card name both numbers): no question repeats it."""
    job, _ = vav_job(vav_totals(*TWO_TRADES))
    assert job.systems[0].families[0].count.added_up.value == 8
    assert sum_questions(job) == []


def test_a_group_that_takes_the_whole_family_keeps_the_sum_in_its_block():
    job, _ = vav_job(vav_totals(*TWO_TRADES), group="VAV")
    (group,) = job.systems
    assert group.families[0].count.added_up.value == 8
    assert sum_questions(job) == []


def test_a_split_family_whose_sum_the_sheets_state_is_asked_once():
    """The stated counts' own question already names both numbers: the sum is not asked a second time."""
    sheets = _sheet_dossier(("M-101", 3, L2_DUCT, "CUH-A (TYP. OF 4)"), ("M-201", 4, L2_PIPE, "CUH-A (TYP. OF 4)"))
    ledger = _ledger()
    _family(ledger, "CUH", "Cabinet Unit Heater", "CUH-A, CUH-B, CUH-C, CUH-D")
    ledger.add("group", "Group A", "CUH (CUH-A, CUH-B)", "S5", "Group A riser", "risers", SETTLED)
    job = plan_job(ledger, None, sheets, PLAYBOOK)
    assert len(job.systems) == 2
    assert [f.count.added_up for s in job.systems for f in s.families] == [None, None]
    [asked] = sum_questions(job)
    assert "M-101 and M-201 show one floor and area" in asked and "4 counted, 8 if the sheets were added up" in asked


def test_a_split_family_with_a_higher_inventory_sum_is_asked_once_with_both_sums():
    """The sheets state 3 (6 added up) and the schedule's units are 4 (8 added up): the higher sum is the one kept, and
    the one question names it beside the stated counts' sum, since no block's note does."""
    stated = (("M-101", 3, L2_DUCT, "VAV-1 ×3"), ("M-201", 4, L2_PIPE, "VAV-1 ×3"))
    job, _ = vav_job(vav_totals(*TWO_TRADES), group=TAKES_TWO, sheets=stated)
    assert [f.count.added_up for s in job.systems for f in s.families] == [None, None]
    [asked] = sum_questions(job)
    assert "3 counted, 6 if the sheets were added up" in asked and ADDED_8 in asked
    assert "4 per M-501" in asked and "per equipment counts for VAV" in asked


class _CountedSources(dict):
    """The dossier's sources, counting every scan of them."""
    scans = 0

    def items(self):
        self.scans += 1
        return super().items()


def test_a_familys_counts_line_is_found_without_a_scan_of_the_sources_for_each_family():
    vav = vav_totals(*TWO_TRADES)[0]
    totals = [vav, replace(vav, prefix="CUH"), replace(vav, prefix="EF")]
    line = "equipment counts for {} (schedules and plans)"
    where = {"D4": "M-101, Drawings.pdf page 2 (sheet text)", "S7": line.format("CUH"), "S8": line.format("VAV"),
             "S9": line.format("VAV"), "S6": line.format("EF")}
    reader = Reader(_ledger(), where, "", totals)
    reader.dossier_sources = _CountedSources(where)
    cited = [reader._total_sum(prefix)[1].source_id for prefix in ("VAV", "CUH", "EF")]
    assert cited == ["S8", "S7", "S6"]                  # each family's own line; the first of two lines of one family
    assert reader.dossier_sources.scans == 1            # every family's line came from one scan
    assert reader._total_sum("VAV") == reader._total_sum("VAV") and reader.dossier_sources.scans == 1


def test_the_note_names_the_sheets_of_a_floor_as_the_inventory_names_them():
    from bms.plan_read import AddedUp

    assert "M-101 and M-201 show one floor and area, so" in AddedUp(4, 8, (("M-101", "M-201"),)).note()
    note = AddedUp(4, 12, (("M-101", "M-201", "M-301"), ("M-102", "M-202"))).note()
    assert "M-101, M-201 and M-301 show one floor and area; M-102 and M-202 show one floor and area, so" in note


def test_the_higher_of_two_sums_is_the_one_kept():
    first, second = Ref("D7", "CUH-A (TYP. OF 4)", "M-101"), Ref("S9", "a flag", "equipment counts for VAV")
    count = Count(6, (PLAN,))
    assert Reader._with_sum(count, (8, first), (12, second)).added_up == OtherCount(12, second)
    assert Reader._with_sum(count, (12, first), (8, second)).added_up == OtherCount(12, first)
    assert Reader._with_sum(count, (8, first), None).added_up == OtherCount(8, first)
    assert Reader._with_sum(count, None, None) is count
    assert Reader._with_sum(count, (6, first), (5, second)) is count        # neither is above the printed count
    assert Reader._with_sum(Count(None), (8, first)).added_up is None       # no printed count: no note to make


# ---- the counts step keeps the sum while it is above the printed count -------------------------------------------------

def test_the_picture_count_keeps_the_sum_while_it_is_above_the_printed_count(tmp_path):
    _, catalogue = counted_plan(tmp_path)                    # EF-1 to EF-4 on the plan: 4 against the schedule's 3
    job = _sample_job()
    ef = family_of(job, "EF", "Exhaust Fan")
    sheets = OtherCount(9, ef.count.sources[0])
    summed = job.with_system(replace(job.system("EF"), families=(replace(ef, count=replace(ef.count, added_up=sheets)),)))
    checked = counts.cross_check(summed, catalogue, tmp_path / "cache")
    count = family_of(checked, "EF", "Exhaust Fan").count
    assert count.value == 4 and count.added_up == sheets
    assert counts.cross_check(checked, catalogue, tmp_path / "cache") == checked      # twice changes nothing more


def test_the_picture_count_drops_the_sum_when_it_is_no_longer_above(tmp_path):
    _, catalogue = counted_plan(tmp_path)
    job = _sample_job()
    ef = family_of(job, "EF", "Exhaust Fan")
    summed = job.with_system(replace(job.system("EF"), families=(
        replace(ef, count=replace(ef.count, added_up=OtherCount(4, ef.count.sources[0]))),)))
    count = family_of(counts.cross_check(summed, catalogue, tmp_path / "cache"), "EF", "Exhaust Fan").count
    assert count.value == 4 and count.added_up is None                   # the plan reads 4: nothing is left to add


# ---- the writer: the planner's sum stays on the family ----------------------------------------------------------------

def test_the_writer_is_shown_the_sum_and_the_family_keeps_it(job, raw, dossier, playbook):
    """The skeleton wins: the answer's family count (the writer cannot know the sheets) is put back as the planner set
    it, sum and all, and the prompt shows the writer the sum beside the count."""
    system = skeleton(job.system("EF"))
    family_ef = system.families[0]
    summed = replace(family_ef, count=replace(family_ef.count, added_up=OtherCount(9, family_ef.count.sources[0])))
    system = replace(system, families=(summed,))
    answer = copy.deepcopy(raw["systems"][1])
    answer["families"][0]["count"]["added_up"] = {"value": 99, "ref": {"source_id": "S6", "quote": "q", "where": "w"}}
    transport = FakeTransport(answer)
    written = ai.write_system(system, ai.evidence_for(system, dossier), playbook, transport)
    assert written.families == system.families and written.families[0].count.added_up.value == 9
    assert '"added_up": {' in transport.asked[0]["prompt"]


# ---- the client's note: both numbers, the printed count the highest -------------------------------------------------

def test_the_note_names_both_numbers_and_the_printed_count_stays_the_highest(job, playbook):
    count = Count(6, (PLAN,), (), SUM)
    system = block([family(count)], [device(Count(6))])
    draft = render(replace(job, systems=(system,)), playbook)
    shown = [l.text for l in draft.lines if l.system_key == "EF"]
    # the header: the highest, never the sum; T-005e (ruling 15): the other counts in brackets on it, no "*Qty." note
    assert shown[0] == f"Qty (6) Exhaust Fans EF-1, 2 (6 per M-101; {SAID})"
    assert not any(t.startswith("*Qty.") for t in shown)
    assert [l.quantity for l in draft.lines if l.system_key == "EF" and l.kind == "line"] == [6]
    assert "(9)" not in "\n".join(shown) and "Qty. 9" not in "\n".join(shown)


def test_the_note_puts_the_sum_after_every_other_count(job, playbook):
    count = Count(6, (PLAN,), (OtherCount(4, SCHEDULE),), SUM)
    system = block([family(count)], [device(Count(6))])
    assert notes(job, playbook, system) == []                                  # T-005e (ruling 15)
    assert headers(job, playbook, system) == [f"6 per M-101; 4 per M-601; {SAID}"]


def test_a_count_with_no_place_still_names_the_sum(job, playbook):
    count = Count(6, (), (), SUM)
    system = block([family(count)], [device(Count(6))])
    assert notes(job, playbook, system) == []                                  # T-005e (ruling 15)
    assert headers(job, playbook, system) == [f"6; {SAID}"]


@pytest.mark.parametrize("printed", [9, 10])
def test_a_sum_not_above_the_printed_count_prints_no_note(job, playbook, printed):
    count = Count(printed, (PLAN,), (), SUM)
    assert notes(job, playbook, block([family(count)], [device(Count(printed))])) == []


def test_an_unknown_count_names_no_sum(job, playbook):
    count = Count(None, (), (), SUM)
    assert notes(job, playbook, block([family(count)], [device(Count(None))])) == []


@pytest.mark.parametrize("carried", [
    Count(6, (PLAN,), (OtherCount(4, SCHEDULE),), SUM),              # the line carries the family's count whole
    Count(6, (PLAN,), (OtherCount(4, SCHEDULE),)),                   # the line carries it without the sum
], ids=["with the sum", "without the sum"])
def test_a_line_that_carries_the_family_count_adds_no_second_note(job, playbook, carried):
    count = Count(6, (PLAN,), (OtherCount(4, SCHEDULE),), SUM)
    system = block([family(count)], [device(carried)])
    assert notes(job, playbook, system) == []                                  # T-005e (ruling 15)
    assert headers(job, playbook, system) == [f"6 per M-101; 4 per M-601; {SAID}"]
    draft = render(replace(job, systems=(system,)), playbook)
    assert [l.text for l in draft.lines if l.device_id == "X.d1"] == ["Furnish and Install DDC Controller"]


def test_a_sum_on_a_line_alone_never_prints(job, playbook):
    """The sum is the planner's, set on the family from the sheets; a line a writer gave one prints none."""
    system = block([family(Count(6, (PLAN,)))], [device(Count(6, (PLAN,), (), SUM))])
    assert notes(job, playbook, system) == []


def test_each_family_of_a_block_names_its_own_sum(job, playbook):
    system = block([family(Count(6, (PLAN,), (), SUM), "Indoor Unit", ("IU-1",)),
                    family(Count(2, (SCHEDULE,)), "Branch Selector", ("BS-1",))], [device(Count(6))])
    assert notes(job, playbook, system) == []                                  # T-005e (ruling 15)
    assert headers(job, playbook, system) == [f"6 per M-101; {SAID}", ""]


def test_a_front_end_line_names_no_sum(job, playbook):
    line = replace(job.front_end.devices[0], quantity=Count(3, (PLAN,), (), OtherCount(5, STATED)))
    draft = render(replace(job, front_end=replace(job.front_end, devices=(line,))), playbook)
    assert [l.text for l in draft.lines if l.system_key == "" and l.kind == "note"] == []


def test_the_planned_sum_reaches_the_clients_note(job, playbook):
    """From the sheets to the note: planned, given a line, rendered. The header and the line keep the printed 4."""
    dossier = _sheet_dossier(("M-101", 3, L2_DUCT, "CUH-A (TYP. OF 4)"), ("M-201", 4, L2_PIPE, "CUH-A (TYP. OF 4)"))
    planned = _cuh_job(dossier)
    (system,) = planned.systems
    line = replace(device(Count(4, system.families[0].count.sources)), refs=system.families[0].count.sources)
    shown = replace(planned, header=job.header, systems=(replace(system, devices=(line,)),))
    draft = render(shown, playbook)
    text = [l.text for l in draft.lines if l.system_key == system.key]
    assert text[0].startswith("Qty (4)")
    # T-005e (ruling 15): the sum in brackets on the header, no "*Qty." note
    assert text[0].endswith("(4 per M-101; 8 if every sheet of the same floor and area is added up)")
    assert not any(t.startswith("*Qty.") for t in text)


# ---- the validator: the sum is no count, so it is no count problem ---------------------------------------------------

def test_a_sum_above_the_printed_count_raises_no_finding(job):
    family_with_sum = Family("Exhaust Fan", ("EF-1", "EF-2", "EF-3"), Count(6, (PLAN,), (), SUM))
    plain = Family("Exhaust Fan", ("EF-1", "EF-2", "EF-3"), Count(6, (PLAN,)))
    devices = tuple(replace(d, quantity=Count(6, (PLAN,))) for d in job.system("EF").devices)
    with_sum = edit(job, "EF", families=(family_with_sum,), devices=devices)
    without = edit(job, "EF", families=(plain,), devices=devices)
    assert validate(with_sum, PB) == validate(without, PB)
    assert [f for f in validate(with_sum, PB) if f.rule == RULE["higher"]] == []


def test_the_sum_does_not_make_the_printed_count_a_count_below_the_highest():
    assert list(_count_problems(Count(6, (PLAN,), (), SUM), "The Exhaust Fan count")) == []
    assert list(_count_problems(Count(6, (PLAN,), (OtherCount(4, SCHEDULE),), SUM), "The Exhaust Fan count")) == []
    assert len(list(_count_problems(Count(4, (SCHEDULE,), (OtherCount(6, PLAN),), SUM), "The Exhaust Fan count"))) == 1


# ---- the review page: the card, the words and the typed count ---------------------------------------------------------

def summed_job(job: Job, count: Count | None = None) -> Job:
    count = count or Count(6, (PLAN,), (), SUM)
    return edit(job, "EF", families=(Family("Exhaust Fan", ("EF-1", "EF-2", "EF-3"), count),))


def test_a_family_with_a_sum_gets_a_card_that_names_both_numbers(job):
    cards = [q for q in review._questions(summed_job(job), []) if q.level == "family" and q.system_key == "EF"]
    (card,) = cards
    assert card.rank == review.RANK_FLAGGED and card.title == "How many Exhaust Fan units?"
    assert card.family_name == "Exhaust Fan" and card.count.added_up == SUM
    (said,) = card.notes
    assert "6 prints" in said and "9 if every sheet is added up" in said and "one floor and area" in said


def test_a_card_for_other_counts_and_a_sum_says_both(job):
    count = Count(6, (PLAN,), (OtherCount(4, SCHEDULE),), SUM)
    (card,) = [q for q in review._questions(summed_job(job, count), []) if q.level == "family" and q.system_key == "EF"]
    assert len(card.notes) == 2
    assert "different counts" in card.notes[0] and "9 if every sheet is added up" in card.notes[1]


def test_a_sum_not_above_the_printed_count_gets_no_card(job):
    asked = review._questions(summed_job(job, Count(9, (PLAN,), (), SUM)), [])
    assert [q for q in asked if q.level == "family" and q.system_key == "EF"] == []


def test_the_page_shows_the_sum_where_it_shows_the_other_counts(job, tmp_path):
    text = review.review_page(summed_job(job, Count(6, (PLAN,), (OtherCount(4, SCHEDULE),), SUM)), [],
                              tmp_path).read_text(encoding="utf-8")
    assert "The other counts:" in text and "If every sheet of the same floor and area is added up:" in text
    assert '<li>9: <span class="src">S6</span> "EF-1 (TYP. OF 4)"' in text
    assert "Printed count: 6" in text


def test_a_typed_family_count_settles_the_sum_as_it_settles_the_other_counts(job):
    family = Family("Exhaust Fan", ("EF-1", "EF-2", "EF-3"), Count(6, (PLAN,), (OtherCount(4, SCHEDULE),), SUM))
    decision = Decision("EF", "change", family_name="Exhaust Fan", reason="5 units")
    count = review._new_count(decision, family)
    assert count.value == 5 and count.others == () and count.added_up is None and count.sources == (PLAN,)
    applied = review.apply_decisions(summed_job(job, family.count), [decision])
    assert applied.system("EF").families[0].count == count


def test_a_count_typed_as_a_rename_settles_the_sum_too(job):
    line = replace(job.system("EF").devices[0], name="3 units", quantity=Count(3, (PLAN,), (), SUM))
    was = replace(line, name="Exhaust Fan Controller")
    read = review._read_count_name(Decision("EF", "change", device_id=line.id, device=line, reason="3 units", was=was))
    assert read.device.name == "Exhaust Fan Controller" and read.device.quantity.added_up is None


@NODE
def test_the_page_settles_the_sum_when_a_count_is_typed(job, tmp_path):
    """The page builds a typed count as `_new_count` does: the other counts and the sum go, the sources stay."""
    summed = summed_job(job, Count(6, (PLAN,), (OtherCount(4, SCHEDULE),), SUM))
    card = family_card(summed, "EF", "Exhaust Fan")
    assert card["count"]["added_up"]["value"] == 9
    made = decide(tmp_path, card, {"action": "change", "text": "5 units"})
    assert made["count"]["value"] == 5 and made["count"]["others"] == [] and made["count"]["added_up"] is None
    assert made["count"]["sources"] == card["count"]["sources"]
    line = replace(summed.system("EF").devices[0], quantity=Count(6, (PLAN,), (), SUM))
    on_line = edit(summed, "EF", devices=(line, *summed.system("EF").devices[1:]))
    made = decide(tmp_path, device_card(on_line, "EF", line.id), {"action": "change", "text": "3"})
    assert made["device"]["quantity"]["value"] == 3 and made["device"]["quantity"]["added_up"] is None


# ---- the Evidence Package -------------------------------------------------------------------------------------------

def test_the_package_shows_the_sum_beside_the_printed_count(job):
    count = Count(6, (PLAN,), (OtherCount(4, SCHEDULE),), SUM)
    row = next(r for r in scope_rows(summed_job(job, count)) if r[2] == "count" and "Exhaust Fan" in r[5])
    at = {h: i for i, h in enumerate(SCOPE_HEADINGS)}
    assert row[at["Quantity"]] == "6"                                    # the number the proposal prints
    other = row[at["Other counts"]].split("\n")
    assert other[0].startswith("4 per S2 | M-601") and other[1].startswith(f"{SAID}, per S6 | M-102")
    assert 'EF-1 (TYP. OF 4)' in other[1]


def test_the_package_shows_nothing_extra_without_a_sum(job):
    rows = scope_rows(summed_job(job, Count(6, (PLAN,), (OtherCount(4, SCHEDULE),))))
    row = next(r for r in rows if r[2] == "count" and "Exhaust Fan" in r[5])
    assert "added up" not in row[SCOPE_HEADINGS.index("Other counts")]
