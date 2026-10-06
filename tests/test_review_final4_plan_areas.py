"""REVIEW-FINAL4 (reviewer of record): attacks on FINAL-D's plan areas (rebuild a3e1b1f). Invented fixtures only.

A strict xfail is a finding: it asserts the right behaviour and fails on a3e1b1f by assertion; its marker comes off
with the fix. The rest are guards that pass.

Lead ruling: an undercount is the worst failure, so two sheets are one plan only on clear evidence.
- F1: two sheets of one document whose titles give the same floor key are merged with no tag test at all, so every
  floor or part form the word list does not read is a silent undercount (the doubt flag never sees a merged pair).
- F2: a type's tag placed once on a sheet (EBB-C, CUH-A) counts as a unit tag, so typical floors that each carry a
  few single-placed types are proven "one plan".
"""
from collections import Counter

import pytest

from estimator.reading.inventory import placements, plan_area_doubts
from estimator.writing.dossier import build_dossier, plan_areas
from test_dossier_plan_areas import DWG, OTHER, _catalogue, _doc, _line, _page, _reading, _sheet

# one typical floor of an invented dorm: 8 heaters (EBB-A at 4 places, EBB-B at 2, EBB-C and EBB-D once)
TYPICAL = "EBB-A\nEBB-A\nEBB-A\nEBB-A\nEBB-B\nEBB-B\nEBB-C\nEBB-D"
TYPICAL_TAGS = ["EBB-A", "EBB-B", "EBB-C", "EBB-D"]
TYPICAL_COUNTS = Counter({"EBB-A": 4, "EBB-B": 2})


def _apart(one, other, tags):
    sheets = [_sheet(1, "M-101", one), _sheet(2, "M-102", other)]
    found = plan_areas([(s, tags) for s in sheets])
    return found[(DWG, 1)] != found[(DWG, 2)]


TWO_AREAS_ONE_DOCUMENT = [
    ("BASEMENT 1 MECHANICAL PLAN", "BASEMENT 2 MECHANICAL PLAN"),          # the basement's number is dropped
    ("LOWER LEVEL 1 PLAN", "LOWER LEVEL 2 PLAN"),                          # so is the lower level's
    ("BASEMENT PLAN", "SUB-BASEMENT PLAN"),                                # SUB-BASEMENT reads as BASEMENT
    ("FIRST FLOOR PLAN BLDG. A", "FIRST FLOOR PLAN BLDG. B"),              # the period stops the building's id
    ("FIRST FLOOR PLAN - BUILDING 1000", "FIRST FLOOR PLAN - BUILDING 2000"),   # four digits are not read
    ("FIRST FLOOR PLAN - TOWERS 1 AND 2", "FIRST FLOOR PLAN - TOWERS 3 AND 4"),  # both read "TOWER S"
    ("FIRST FLOOR PLAN - UNITS 1-4", "FIRST FLOOR PLAN - UNITS 5-8"),      # both read "UNIT S"
    ("FIRST FLOOR PLAN - SUITE 3", "FIRST FLOOR PLAN - SUITE 4"),          # part words not in the list
    ("FIRST FLOOR PLAN - CONCOURSE A", "FIRST FLOOR PLAN - CONCOURSE B"),
    ("FIRST FLOOR PLAN - SECTION A", "FIRST FLOOR PLAN - SECTION B"),
    ("LEVEL 1 PLAN - PODIUM", "LEVEL 1 PLAN - TOWER"),
    ("FIRST FLOOR - HALL A", "FIRST FLOOR - HALL B"),
]


@pytest.mark.xfail(strict=True, reason="REVIEW-FINAL4 F1: one document plus one floor key merges with no tag test")
@pytest.mark.parametrize("titles", TWO_AREAS_ONE_DOCUMENT)
def test_two_areas_of_one_document_on_typical_tags_are_never_one_plan(titles):
    assert _apart(*titles, TYPICAL_COUNTS), titles


@pytest.mark.xfail(strict=True, reason="REVIEW-FINAL4 F1: BASEMENT 1 and BASEMENT 2 are merged, 8 heaters lost")
def test_the_dossier_adds_up_the_heaters_of_two_basements(tmp_path):
    pages = [_page(DWG, 1, TYPICAL), _page(DWG, 2, TYPICAL)]
    sheets = [_sheet(1, "M-101", "BASEMENT 1 MECHANICAL PLAN"), _sheet(2, "M-102", "BASEMENT 2 MECHANICAL PLAN")]
    d = build_dossier(_catalogue(pages, sheets, TYPICAL_TAGS), _reading(), tmp_path)
    assert d.counts["EBB"]["plan_placements"] == 16
    assert "same plan as" not in _line("EBB", d)


@pytest.mark.xfail(strict=True, reason="REVIEW-FINAL4 F1: the inventory merges BASEMENT 1 and 2 as well")
def test_the_inventory_adds_up_a_type_tag_on_two_basements():
    pages = [_page(DWG, 1, TYPICAL), _page(DWG, 2, TYPICAL)]
    sheets = [_sheet(1, "M-101", "BASEMENT 1 MECHANICAL PLAN"), _sheet(2, "M-102", "BASEMENT 2 MECHANICAL PLAN")]
    found = placements(_catalogue(pages, sheets, ["EBB-A"]), ["EBB-A"], (), {(DWG, 1), (DWG, 2)})
    assert found["EBB-A"].total == 8


@pytest.mark.xfail(strict=True, reason="REVIEW-FINAL4 F2: types placed once on each sheet prove 'one plan'")
def test_two_buildings_first_floors_with_single_placed_types_add_up(tmp_path):
    """One document per building, each with a FIRST FLOOR PLAN of the same typical floor. EBB-C, EBB-D and CUH-A
    are each placed once on each sheet: they are types (no unit number), not proof of one plan."""
    text = TYPICAL + "\nCUH-A"
    documents = [_doc(DWG, 1), _doc(OTHER, 1)]
    pages = [_page(DWG, 1, text), _page(OTHER, 1, text)]
    sheets = [_sheet(1, "M-101", "FIRST FLOOR PLAN"), _sheet(1, "B-101", "FIRST FLOOR PLAN", OTHER)]
    d = build_dossier(_catalogue(pages, sheets, TYPICAL_TAGS + ["CUH-A"], documents), _reading(), tmp_path)
    assert d.counts["EBB"]["plan_placements"] == 16


@pytest.mark.xfail(strict=True, reason="REVIEW-FINAL4 F2: the no-floor branch also takes single-placed types")
def test_two_sheets_of_one_title_naming_no_floor_on_single_placed_types_are_not_one_plan():
    tags = Counter({"EBB-A": 4, "EBB-B": 2, "EBB-C": 1, "EBB-D": 1, "CUH-A": 1})
    sheets = [_sheet(1, "M-101", "BUILDING A MECHANICAL PLAN"), _sheet(2, "M-102", "BUILDING A MECHANICAL PLAN")]
    plans = [(s, tags) for s in sheets]
    found = plan_areas(plans)
    # apart (the higher count) or, at the least, named as a doubt
    assert found[(DWG, 1)] != found[(DWG, 2)] or plan_area_doubts(plans, found)


# ---- guards (pass on a3e1b1f) ----------------------------------------------------------------------------------

@pytest.mark.parametrize("titles", [("LEVEL I PLAN", "LEVEL II PLAN"), ("MEZZANINE PLAN", "PENTHOUSE PLAN"),
                                    ("L1 PLAN", "L2 PLAN"), ("FIRST & SECOND FLOOR PLAN", "FIRST FLOOR PLAN"),
                                    ("LEVEL 1 & 2 PLAN", "LEVEL 1 PLAN"), ("LEVEL B1", "LEVEL B2")])
def test_unusual_floor_forms_on_typical_tags_stay_apart_without_a_doubt(titles):
    sheets = [_sheet(1, "M-101", titles[0]), _sheet(2, "M-102", titles[1])]
    plans = [(s, TYPICAL_COUNTS) for s in sheets]
    found = plan_areas(plans)
    assert found[(DWG, 1)] != found[(DWG, 2)]
    if titles[0].startswith("LEVEL I"):
        assert plan_area_doubts(plans, found) == []          # roman numerals read as no floor: no noise either


def test_typical_floors_on_distinct_floor_titles_add_up_over_every_floor(tmp_path):
    """Three floors of one typical dorm, the same heaters on each: the total is the sum over the floors."""
    titles = ["FIRST FLOOR PLAN", "SECOND FLOOR PLAN", "THIRD FLOOR PLAN"]
    pages = [_page(DWG, n, TYPICAL) for n in (1, 2, 3)]
    sheets = [_sheet(n, f"M-10{n}", t) for n, t in enumerate(titles, start=1)]
    d = build_dossier(_catalogue(pages, sheets, TYPICAL_TAGS), _reading(), tmp_path)
    assert d.counts["EBB"]["plan_placements"] == 24
    assert "may show one plan" not in _line("EBB", d)
