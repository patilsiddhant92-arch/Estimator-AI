"""FINAL-I: the final counting rule (lead ruling after REVIEW-FINAL5), shared by the inventory and the dossier.

- Plan sheets are one plan group only when they are in one document, their titles have the same words (the sheet
  number and the trade and plan words taken out) with a floor among them, and they repeat at least 3 unit tags,
  0.6 of the smaller sheet's. A group of 2+ sheets is named in the reading notes.
- In a group a unit's tag counts once, a type's tag the most labels of one sheet, each times the floors the group
  stands for, every floor once. Every other sheet is its own group, and the groups add up: when in doubt, sum.
- Sheets are keyed by (document, page): one sheet number in two documents with the same text is two sheets (F7).
Every test here fails on rebuild 36b6d5c by assertion. Invented fixtures only."""
from types import SimpleNamespace

import pytest

from estimator.reading.inventory import build_inventory
from estimator.writing.dossier import build_dossier
from test_dossier_plan_areas import DWG, OTHER, _catalogue, _doc, _line, _page, _reading, _schedule, _sheet

UNITS = ["VAV-1", "VAV-2", "VAV-3"]


def _lines(*tags):
    return "\n".join(tags)


def _notes(line: str) -> str:
    return line.split("Reading notes:", 1)[1] if "Reading notes:" in line else ""


@pytest.mark.parametrize("first, second", [
    ("HVAC BASEMENT 1 PLAN", "HVAC BASEMENT 2 PLAN"),
    ("FIRST FLOOR PLAN - BLDG. A", "FIRST FLOOR PLAN - BLDG. B"),
    ("SUITE 3 FLOOR PLAN", "SUITE 4 FLOOR PLAN"),
    ("TOWERS 1 AND 2 LEVEL 5 PLAN", "TOWERS 3 AND 4 LEVEL 5 PLAN"),
    ("BUILDING 1000 FLOOR PLAN", "BUILDING 2000 FLOOR PLAN"),
])
def test_titles_with_other_words_are_never_one_plan_and_add_up(tmp_path, first, second):
    """One document, the same three boxes on both sheets: the titles' words differ, so the sheets are two plan
    groups and add up (6); the rebuild counted each box once over the set (3)."""
    pages = [_page(DWG, 1, _lines(*UNITS)), _page(DWG, 2, _lines(*UNITS))]
    sheets = [_sheet(1, "M-101", first), _sheet(2, "M-102", second)]
    d = build_dossier(_catalogue(pages, sheets, UNITS), _reading(), tmp_path)
    assert d.counts["VAV"]["plan_placements"] == 6
    assert "counted as one plan" not in _line("VAV", d)


def test_a_floor_drawn_on_a_ductwork_and_a_piping_plan_is_one_group_and_a_type_counts_once_there(tmp_path):
    """"HVAC DUCTWORK FIRST FLOOR PLAN" and "HVAC PIPING AND CONTROLS FIRST FLOOR PLAN" are both FIRST FLOOR, and
    repeat three unit tags: one plan group. A type's tag counts the most labels of one sheet (4, the rebuild summed
    8), each box once, and the group is named for a check."""
    text = _lines(*UNITS, "EBB-A", "EBB-A", "EBB-A", "EBB-A")
    pages = [_page(DWG, 1, text), _page(DWG, 2, text)]
    sheets = [_sheet(1, "M-101", "HVAC DUCTWORK FIRST FLOOR PLAN"),
              _sheet(2, "M-201", "HVAC PIPING AND CONTROLS FIRST FLOOR PLAN")]
    d = build_dossier(_catalogue(pages, sheets, UNITS + ["EBB-A"]), _reading(), tmp_path)
    assert d.counts["VAV"]["plan_placements"] == 3
    assert d.counts["EBB"]["plan_placements"] == 4
    for prefix, one, apart in (("VAV", 3, 6), ("EBB", 4, 8)):
        line = _line(prefix, d)
        assert (f"M-101 and M-201 counted as one plan, {one} ({apart} if they are two places): same floor title, "
                "same units; check") in _notes(line)                # FINAL-K: both counts (REVIEW-FINAL6 F5)
        assert "same plan as" not in line and "may show one plan" not in line


def test_one_title_with_too_few_unit_tags_in_common_is_two_plans(tmp_path):
    """The same title, but only two unit tags repeated: too little to be one plan, so the sheets add up (4)."""
    pages = [_page(DWG, 1, _lines("VAV-1", "VAV-2")), _page(DWG, 2, _lines("VAV-1", "VAV-2"))]
    sheets = [_sheet(1, "M-101", "HVAC FIRST FLOOR PLAN"), _sheet(2, "M-201", "CONTROLS FIRST FLOOR PLAN")]
    d = build_dossier(_catalogue(pages, sheets, ["VAV-1", "VAV-2"]), _reading(), tmp_path)
    assert d.counts["VAV"]["plan_placements"] == 4
    assert "M-101 and M-201 may show one plan" in _line("VAV", d)


def test_a_group_of_two_typical_sheets_counts_every_floor_they_name_once(tmp_path):
    """A ductwork and a piping plan of one typical floor, floors 2 to 5 and floors 4 to 7 (the lists overlap): one
    group standing for floors 2 to 7, so 3 boxes x 6 floors = 18 (the rebuild took the larger list, 12)."""
    pages = [_page(DWG, 1, _lines(*UNITS)), _page(DWG, 2, _lines(*UNITS))]
    sheets = [_sheet(1, "M-102", "TYPICAL FLOOR DUCTWORK PLAN"), _sheet(2, "M-202", "TYPICAL FLOOR PIPING PLAN")]
    reading = _reading()
    reading.typicals = (SimpleNamespace(sheet="M-102", floors=("2", "3", "4", "5")),
                        SimpleNamespace(sheet="M-202", floors=("4", "5", "6", "7")))
    d = build_dossier(_catalogue(pages, sheets, UNITS), reading, tmp_path)
    assert d.counts["VAV"]["plan_placements"] == 18


def test_one_sheet_number_in_two_documents_with_the_same_text_is_two_sheets(tmp_path):
    """REVIEW-FINAL5 F7: two identical buildings issued as two one-sheet documents, both "M-101 FIRST FLOOR PLAN"
    with the same text. Both are counted (AHU 6, EBB 14; the rebuild read the first only: 3, 7), each named by its
    document, and the pair named as maybe one plan."""
    text = _lines("AHU-1", "AHU-2", "AHU-3", *(["EBB-A"] * 4), "EBB-B", "EBB-B", "EBB-C")
    pages = [_page(DWG, 1, text), _page(OTHER, 1, text)]
    sheets = [_sheet(1, "M-101", "FIRST FLOOR PLAN"), _sheet(1, "M-101", "FIRST FLOOR PLAN", OTHER)]
    tags = ["AHU-1", "AHU-2", "AHU-3", "EBB-A", "EBB-B", "EBB-C"]
    d = build_dossier(_catalogue(pages, sheets, tags, [_doc(DWG, 1), _doc(OTHER, 1)]), _reading(), tmp_path)
    assert d.counts["AHU"]["plan_placements"] == 6
    assert d.counts["EBB"]["plan_placements"] == 14
    line = _line("AHU", d)
    assert "M-101 (Mech.pdf) 3; M-101 (Second Building.pdf) 3" in line
    assert "M-101 (Mech.pdf) and M-101 (Second Building.pdf) may show one plan" in line
    # a marked-up copy of the set (a document repeating 3 or more of another's sheets) is still read once
    numbers = ["M-101", "M-102", "M-103"]
    pages = [_page(d_, n, f"AHU-{n}") for d_ in (DWG, OTHER) for n in (1, 2, 3)]
    sheets = [_sheet(n, numbers[n - 1], f"HVAC LEVEL {n} PLAN", d_) for d_ in (DWG, OTHER) for n in (1, 2, 3)]
    d = build_dossier(_catalogue(pages, sheets, tags[:3], [_doc(DWG, 3), _doc(OTHER, 3)]), _reading(), tmp_path)
    assert d.counts["AHU"]["plan_placements"] == 3


def _scheduled(plan_texts, titles, tags, typicals=(), documents=None):
    pages = [_page(document, page, text) for (document, page), text in plan_texts]
    pages.append(_page(DWG, 9, "SCHEDULE\n" + _lines(*tags)))
    sheets = [_sheet(page, number, title, document) for ((document, page), _t), (number, title)
              in zip(plan_texts, titles)]
    sheets.append(_sheet(9, "M-601", "SCHEDULES", types=("Schedules",)))
    schedules = [_schedule("UNIT SCHEDULE", tags, 9)]
    reading = _reading(schedules)
    reading.typicals = tuple(SimpleNamespace(sheet=s, floors=tuple(f)) for s, f in typicals)
    catalogue = _catalogue(pages, sheets, tags, documents or [_doc(DWG, 9)])
    items, _totals, _flags = build_inventory(catalogue, schedules, reading.typicals)
    return {i.tag: i.quantity for i in items}, catalogue, reading


@pytest.mark.parametrize("case, expected", [
    ("a unit's tag on two floors' plans", {"VAV-1": 2}),
    ("a type's tag on one floor drawn twice", {"EBB-A": 4, "VAV-1": 1, "VAV-2": 1, "VAV-3": 1}),
    ("a unit's tag on two typical sheets of other floors", {"VAV-1": 9}),
    ("one sheet number in two documents", {"AHU-1": 2}),
])
def test_the_inventory_and_the_dossier_count_every_tag_alike(tmp_path, case, expected):
    """REVIEW-FINAL5 F4: the Evidence Package (the inventory) and the proposal (the dossier) count with one rule, so
    each scheduled tag's quantity is the dossier's count of it, and both are the rule's count."""
    if case == "a unit's tag on two floors' plans":
        got, catalogue, reading = _scheduled([((DWG, 1), "VAV-1"), ((DWG, 2), "VAV-1")],
                                             [("M-101", "LEVEL 1 PLAN"), ("M-102", "LEVEL 2 PLAN")], ["VAV-1"])
    elif case == "a type's tag on one floor drawn twice":
        text = _lines(*UNITS, *(["EBB-A"] * 4))
        got, catalogue, reading = _scheduled([((DWG, 1), text), ((DWG, 2), text)],
                                             [("M-101", "HVAC DUCTWORK LEVEL 1 PLAN"),
                                              ("M-201", "HVAC PIPING LEVEL 1 PLAN")], UNITS + ["EBB-A"])
    elif case == "a unit's tag on two typical sheets of other floors":
        got, catalogue, reading = _scheduled([((DWG, 1), "VAV-1"), ((DWG, 2), "VAV-1")],
                                             [("M-102", "TYPICAL LOW-RISE FLOOR PLAN"),
                                              ("M-106", "TYPICAL HIGH-RISE FLOOR PLAN")], ["VAV-1"],
                                             [("M-102", ("2", "3", "4", "5")), ("M-106", ("6", "7", "8", "9", "10"))])
    else:
        got, catalogue, reading = _scheduled([((DWG, 1), "AHU-1"), ((OTHER, 1), "AHU-1")],
                                             [("M-101", "FIRST FLOOR PLAN"), ("M-101", "FIRST FLOOR PLAN")],
                                             ["AHU-1"], documents=[_doc(DWG, 9), _doc(OTHER, 1)])
    d = build_dossier(catalogue, reading, tmp_path)
    for tag, n in expected.items():
        assert got[tag] == n, (case, tag)
    by_family: dict = {}
    for tag, n in got.items():
        by_family[tag.split("-")[0]] = by_family.get(tag.split("-")[0], 0) + n
    for prefix, n in by_family.items():
        assert d.counts[prefix]["plan_placements"] == n, (case, prefix)


def test_a_unit_tag_labelled_twice_on_one_sheet_is_named_as_maybe_a_typical_unit(tmp_path):
    """REVIEW-FINAL5 F3: FCU-1 twice on one plan (below the type rule) counts once there, and the reading notes name
    it so the estimator can check whether it is a typical unit at each place."""
    pages = [_page(DWG, 1, _lines("FCU-1", "FCU-1", "FCU-2"))]
    d = build_dossier(_catalogue(pages, [_sheet(1, "M-101", "HVAC LEVEL 1 PLAN")], ["FCU-1", "FCU-2"]), _reading(),
                      tmp_path)
    assert d.counts["FCU"]["plan_placements"] == 2
    assert "FCU-1 2 times on M-101, counted as one unit: if it is a typical unit placed at each of those places" in \
        _notes(_line("FCU", d))
