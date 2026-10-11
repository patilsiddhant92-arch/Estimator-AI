"""T-005a regression tests from an invented copy of the 26-0544 counting defects (NOTES 2026-10-11 rule 4), read
from tests/bms/fixtures/t005a_counting.json:

- a numbered unit tag on four penthouse plans of four trades counted 4x (AHU 21 for 5 units on the job);
- a unit drawn only on a demolition plan counted (and a type tag's demolition labels added to its count).

Also NOTES rule 5: the seams the lead's whole-job takeoff pass will call with explicit sources stay callable:
`inventory.placements(..., pages=...)`, `inventory.plan_count(..., groups=...)` and `plan_read.Reader._count(...)`.
Invented fixtures only."""
from __future__ import annotations

import json
from pathlib import Path

from bms.model import Ref
from bms.plan_read import Reader
from estimator.ledger.facts import Ledger
from estimator.reading.inventory import demolition_work, placements, plan_count
from estimator.writing.dossier import build_dossier
from test_dossier_plan_areas import _catalogue, _line, _page, _reading, _schedule, _sheet

FIXTURE = json.loads((Path(__file__).resolve().parent / "fixtures" / "t005a_counting.json").read_text("utf-8"))
DWG = FIXTURE["document"]
UNITS = FIXTURE["units"]
DEMO_UNIT = FIXTURE["demolition_only_unit"]
TYPE = FIXTURE["type_tag"]
N = len(UNITS)


def _job(demolition=True, work_note=False):
    text = "\n".join(UNITS)
    pages, sheets = [], []
    for s in FIXTURE["penthouse_plans"]:
        pages.append(_page(DWG, s["page"], text))
        sheets.append(_sheet(s["page"], s["number"], s["title"]))
    sch = FIXTURE["schedule"]
    pages.append(_page(DWG, sch["page"], sch["heading"] + "\n" + text))
    sheets.append(_sheet(sch["page"], sch["number"], sch["title"], types=("Schedules",)))
    tp = FIXTURE["type_plan"]
    pages.append(_page(DWG, tp["page"], "\n".join([TYPE] * tp["labels"])))
    sheets.append(_sheet(tp["page"], tp["number"], tp["title"]))
    if demolition:
        for s in FIXTURE["demolition_plans"]:
            pages.append(_page(DWG, s["page"], "\n".join(s["text"])))
            sheets.append(_sheet(s["page"], s["number"], s["title"], types=("Plans", "Demolition")))
    if work_note:
        w = FIXTURE["work_note"]
        pages.append(_page(DWG, w["page"], w["text"]))
        sheets.append(_sheet(w["page"], w["number"], w["title"], types=("Notes and legends",)))
    reading = _reading([_schedule(sch["heading"], UNITS, sch["page"], sheet=sch["number"])])
    return _catalogue(pages, sheets, UNITS + [DEMO_UNIT, TYPE]), reading


def _plans(n):
    return [s["number"] for s in FIXTURE["penthouse_plans"][:n]]


# ---- defect 1: a unit on four penthouse plans counted once per plan ----------------------------------------------------

def test_fixture_unit_on_four_penthouse_plans_counts_once(tmp_path):
    catalogue, reading = _job(demolition=False)
    d = build_dossier(catalogue, reading, tmp_path)
    assert d.counts["AHU"]["plan_placements"] == N                  # not 4 x N
    line = _line("AHU", d)
    first = UNITS[0]
    assert f"{first} is on 4 plans ({', '.join(_plans(3))} …), counted once, 1" in line
    assert f"if each plan's {first} is its own unit (a type used once per plan), 4" in line


def test_fixture_inventory_counts_each_unit_once():
    catalogue, _r = _job(demolition=False)
    placed = placements(catalogue, UNITS)
    assert all(placed[tag].count == 1 for tag in UNITS)


# ---- defect 2: a demolition-only unit counted ----------------------------------------------------------------------

def test_fixture_demolition_only_unit_is_left_out_with_both_numbers(tmp_path):
    catalogue, reading = _job()
    d = build_dossier(catalogue, reading, tmp_path)
    assert d.counts["AHU"]["plan_placements"] == N
    demo = FIXTURE["demolition_plans"][0]["number"]
    assert (f"{DEMO_UNIT} is on demolition sheets only ({demo}): left out of the count, {N}; with the demolition "
            f"sheets, {N + 1}") in _line("AHU", d)


def test_fixture_type_tag_labels_on_a_demolition_plan_are_left_out(tmp_path):
    catalogue, reading = _job()
    d = build_dossier(catalogue, reading, tmp_path)
    new = FIXTURE["type_plan"]["labels"]
    demo = FIXTURE["demolition_plans"][1]
    more = len(demo["text"])
    assert d.counts["FCU"]["plan_placements"] == new
    assert (f"{TYPE} has {more} more labels on demolition sheets ({demo['number']}): left out of the count, {new}; "
            f"with the demolition sheets, {new + more}") in _line("FCU", d)


def test_fixture_demolition_unit_with_work_named_is_not_added_and_keeps_its_work(tmp_path):
    # the lead's ruling on the T-005a review: kept for the Demolition Scope block, never in the new-work count
    catalogue, reading = _job(work_note=True)
    assert set(demolition_work(catalogue, [DEMO_UNIT])) == {DEMO_UNIT}
    d = build_dossier(catalogue, reading, tmp_path)
    assert d.counts["AHU"]["plan_placements"] == N
    placed = placements(catalogue, UNITS + [DEMO_UNIT])
    assert placed[DEMO_UNIT].count == 0 and placed[DEMO_UNIT].demolition
    assert "REFURBISH EXISTING " + DEMO_UNIT in placed[DEMO_UNIT].demolition_work


def test_fixture_removal_line_names_no_work():
    pages = [_page(DWG, 1, FIXTURE["removal_note"])]
    catalogue = _catalogue(pages, [_sheet(1, "M002.00", "NOTES", types=("Notes and legends",))], [DEMO_UNIT, TYPE])
    assert demolition_work(catalogue, [DEMO_UNIT, TYPE]) == {}


def test_fixture_inventory_leaves_the_demolition_unit_out():
    catalogue, _r = _job()
    placed = placements(catalogue, UNITS + [DEMO_UNIT])
    assert DEMO_UNIT not in placed or placed[DEMO_UNIT].count == 0
    assert FIXTURE["demolition_plans"][0]["number"] not in placed[UNITS[0]].on_plans


# ---- NOTES rule 5: the seams stay callable with explicit sources ------------------------------------------------------

def test_seam_placements_reads_only_the_pages_it_is_given():
    catalogue, _r = _job()
    two = {(DWG, s["page"]) for s in FIXTURE["penthouse_plans"][:2]}
    placed = placements(catalogue, UNITS, pages=two)
    assert placed[UNITS[0]].count == 1
    assert set(placed[UNITS[0]].on_plans) <= set(_plans(2))
    only_demo = {(DWG, FIXTURE["demolition_plans"][0]["page"])}
    placed = placements(catalogue, UNITS + [DEMO_UNIT], pages=only_demo)
    assert DEMO_UNIT not in placed or placed[DEMO_UNIT].count == 0


def test_seam_plan_count_takes_explicit_groups():
    a, b, c = (DWG, 1), (DWG, 2), (DWG, 3)
    found = [(a, 3, frozenset()), (b, 2, frozenset()), (c, 4, frozenset())]
    assert plan_count(found, groups={}, per_place=True) == 9                 # three groups added up
    joined = {a: (a, b), b: (a, b), c: (c,)}
    assert plan_count(found, groups=joined, per_place=True) == 7             # a and b one plan: 3 (most) + 4
    assert plan_count(found, groups=joined, per_place=False) == 1            # a unit's tag: once in the job


def test_seam_plan_read_count_takes_an_explicit_list_of_sources():
    reader = Reader(Ledger())
    r1, r2, r3 = (Ref("S1", "AHU-11", "M117.00"), Ref("S2", "AHU-11", "M217.00"), Ref("S3", "QTY 2", "M612.00"))
    count = reader._count([], [(1, (r1,)), (1, (r2,)), (2, (r3,))])
    assert count.value == 2 and count.sources == (r3,)
    assert [(o.value, o.ref) for o in count.others] == [(1, r1), (1, r2)]   # each other source kept
    assert reader._count([], []).value is None
