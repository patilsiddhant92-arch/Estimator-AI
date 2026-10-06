"""FINAL-D F1, rule changed by FINAL-G: plan sheets are never merged as one plan any more (lead ruling after
REVIEW-FINAL4: deciding one plan from titles and tags cannot be made safe; an unread title form was a silent
undercount). A unit's tag counts once whatever the sheets; a type's tag counts at every place on every sheet. Which
sheets MAY show one plan (`plan_area_doubts`) is only a hint the counts line names: the same readable floor (in
words or figures) and part, one document with one title, or repeated unit tags; never two floors or parts the titles
name apart. These tests were plan_areas merge tests; each now pins the same title readings as the hint, and
plan_areas keeps every sheet apart. Invented fixtures only."""
from collections import Counter

from estimator.reading.inventory import plan_area_doubts
from estimator.writing.dossier import build_dossier, plan_areas
from test_dossier_plan_areas import CTL, DWG, _catalogue, _doc, _line, _page, _reading, _sheet

UNITS = {"VAV-1", "VAV-2", "VAV-3"}


def _maybe_one_plan(*titles, tags=UNITS, documents=None):
    documents = documents or [DWG] * len(titles)
    sheets = [_sheet(n, f"M-{100 + n}", title, document)
              for n, (title, document) in enumerate(zip(titles, documents), start=1)]
    plans = [(sheet, tags) for sheet in sheets]
    found = plan_areas(plans)
    assert len(set(found.values())) == len(sheets)                     # never merged (FINAL-G)
    return bool(plan_area_doubts(plans, found))                         # the hint: may they show one plan?


ONE_FLOOR = [
    ("HVAC LEVEL ONE PLAN", "CONTROLS FIRST FLOOR PLAN"),
    ("HVAC 1ST FLR PLAN", "CONTROLS FIRST FLOOR PLAN"),
    ("HVAC L2 PLAN", "CONTROLS LEVEL 2 PLAN"),
    ("HVAC LEVEL TWO PLAN", "CONTROLS SECOND LEVEL PLAN"),
    ("HVAC GROUND FLOOR PLAN", "CONTROLS GROUND LEVEL PLAN"),
    ("HVAC LOWER LEVEL PLAN", "CONTROLS LOWER LEVEL PLAN"),
    ("HVAC ROOF PLAN", "CONTROLS ROOF PLAN"),
    ("FIRST FLOOR PLAN - TOWER ONE", "CONTROLS FIRST FLOOR PLAN - TOWER 1"),
    ("HVAC FIRST FLOOR PLAN TOWER 2", "CONTROLS FIRST FLOOR PLAN - TOWER TWO"),
    ("HVAC TOWER 2 FIRST FLOOR PLAN", "CONTROLS TOWER 2 FIRST FLOOR PLAN"),
]


def test_one_floor_named_in_words_or_figures_may_be_one_plan():
    """The titles alone hint it (no tags repeated): one floor, one part."""
    for one, other in ONE_FLOOR:
        assert _maybe_one_plan(one, other, tags=set()), (one, other)


DIFFERENT = [
    ("LEVEL ONE MECHANICAL PLAN", "LEVEL TWO MECHANICAL PLAN"),
    ("1ST FLR MECHANICAL PLAN", "2ND FLR MECHANICAL PLAN"),
    ("GROUND FLOOR PLAN", "FIRST FLOOR PLAN"),
    ("FIRST FLOOR PLAN - DORM WING", "FIRST FLOOR PLAN - CLASSROOM WING"),
    ("FIRST FLOOR PLAN - TOWER 1", "FIRST FLOOR PLAN - TOWER 2"),
    ("FIRST FLOOR PLAN - UNIT 1A", "FIRST FLOOR PLAN - UNIT 1B"),
    ("FIRST FLOOR PLAN - BUILDING A", "FIRST FLOOR PLAN - BUILDING B"),
    ("FIRST FLOOR PLAN - NORTH", "FIRST FLOOR PLAN - SOUTH"),
    ("FIRST FLOOR PLAN - EAST", "FIRST FLOOR PLAN - WEST"),
    ("FIRST FLOOR PLAN - ANNEX", "FIRST FLOOR PLAN"),
    ("LOWER ROOF PLAN", "UPPER ROOF PLAN"),
    ("HIGH ROOF PLAN", "LOW ROOF PLAN"),
    ("FIRST AND SECOND FLOOR PLAN", "SECOND FLOOR PLAN"),
    ("LEVELS 2 THRU 5 PLAN", "LEVEL 2 PLAN"),
    # a word before the part word keeps the part's number (no dash before TOWER)
    ("FIRST FLOOR PLAN TOWER 1", "FIRST FLOOR PLAN TOWER 2"),
    ("HVAC TOWER 1 FIRST FLOOR PLAN", "HVAC TOWER 2 FIRST FLOOR PLAN"),
    ("EAST WING 1 FIRST FLOOR PLAN", "EAST WING 2 FIRST FLOOR PLAN"),
    ("RESIDENCE TOWER A FIRST FLOOR PLAN", "RESIDENCE TOWER B FIRST FLOOR PLAN"),
]


# a title naming several floors reads as no one floor: repeating unit tags, it may show one of them again
SEVERAL = {("FIRST AND SECOND FLOOR PLAN", "SECOND FLOOR PLAN"), ("LEVELS 2 THRU 5 PLAN", "LEVEL 2 PLAN")}


def test_two_different_floors_or_parts_are_never_named_as_one_plan():
    """Even when both sheets repeat the same unit tags (a typical floor of a dorm or a tower)."""
    for one, other in DIFFERENT:
        assert _maybe_one_plan(one, other) == ((one, other) in SEVERAL), (one, other)


def test_sheets_naming_no_floor_may_be_one_plan_on_one_title_or_repeated_unit_tags():
    assert not _maybe_one_plan("MECHANICAL PLAN - DORM WING", "MECHANICAL PLAN - CLASSROOM WING")   # parts apart
    assert _maybe_one_plan("ENLARGED MECHANICAL ROOM PLAN", "HVAC FIRST FLOOR PLAN")   # repeats the floor's units
    assert not _maybe_one_plan("ENLARGED MECHANICAL ROOM PLAN", "HVAC FIRST FLOOR PLAN", tags=set())
    assert _maybe_one_plan("MECHANICAL PLAN", "MECHANICAL  PLAN", tags=set())          # one title, one document
    assert _maybe_one_plan("MECHANICAL PLAN", "MECHANICAL PLAN", documents=[DWG, CTL])  # repeated unit tags
    assert not _maybe_one_plan("MECHANICAL PLAN", "MECHANICAL PLAN", tags=set(), documents=[DWG, CTL])


def test_a_title_holding_its_own_sheet_number_compares_without_it():
    sheets = [_sheet(1, "M-301", "M-301 MECHANICAL PLAN"), _sheet(2, "M-302", "M-302 MECHANICAL PLAN")]
    assert plan_area_doubts([(s, set()) for s in sheets]) == [((DWG, 1), (DWG, 2))]
    sheets[1] = _sheet(2, "M-302", "M-302 PIPING PLAN")                     # another title, no tags: no hint
    assert plan_area_doubts([(s, set()) for s in sheets]) == []


def test_an_enlarged_plan_repeating_a_floors_tags_counts_each_box_once_and_names_the_types_sheets(tmp_path):
    """The enlarged plan names no floor and repeats the first floor's boxes and heaters. FINAL-G: each box counts
    once (4, was 4 + 3); the heaters' type tag counts every place (2 + 2) and its line names the two sheets."""
    pages = [_page(DWG, 1, "VAV-1\nVAV-2\nVAV-3\nVAV-4\nEBB-A\nEBB-A"),
             _page(DWG, 2, "VAV-1\nVAV-2\nVAV-3\nEBB-A\nEBB-A")]
    sheets = [_sheet(1, "M-101", "HVAC FIRST FLOOR PLAN"), _sheet(2, "M-301", "ENLARGED MECHANICAL ROOM PLAN")]
    d = build_dossier(_catalogue(pages, sheets, [f"VAV-{n}" for n in range(1, 5)] + ["EBB-A"]), _reading(), tmp_path)
    assert d.counts["VAV"]["plan_placements"] == 4
    assert "may show one plan" not in _line("VAV", d)
    assert d.counts["EBB"]["plan_placements"] == 4
    line = _line("EBB", d)
    assert "same plan as" not in line
    assert "M-101 and M-301 may show one plan" in line and "both are counted" in line
    # the flag never holds a client cause's words (bms.render reads them after the line's head)
    (flag,) = [note for note in line.split("; ") if "may show one plan" in note]
    for words in ("same plan as", "a typical unit at each place", "one unit's tag on several plans",
                  "one unit labelled more than once"):
        assert words not in flag
    # two floors the titles name apart are known to be two plans: no flag
    pages = [_page(DWG, 1, "VAV-1\nVAV-2\nVAV-3"), _page(DWG, 2, "VAV-1\nVAV-2\nVAV-3")]
    sheets = [_sheet(1, "M-101", "HVAC FIRST FLOOR PLAN"), _sheet(2, "M-102", "HVAC SECOND FLOOR PLAN")]
    d = build_dossier(_catalogue(pages, sheets, sorted(UNITS)), _reading(), tmp_path)
    assert d.counts["VAV"]["plan_placements"] == 3                     # FINAL-G: each box once (was 6)
    assert "may show one plan" not in _line("VAV", d)


def test_the_same_floor_in_two_documents_on_typical_type_tags_alone_is_counted_apart_and_flagged(tmp_path):
    """Two documents each with a first floor plan showing the same type tags, each at several places: those tags
    prove nothing (a typical unit is at each place on every floor of every building), so the plans add up, and the
    line names them as maybe one plan."""
    documents = [_doc(DWG, 1), _doc(CTL, 1)]
    text = "EBB-A\nEBB-A\nEBB-A\nEBB-B\nEBB-B\nEBB-C\nEBB-C"
    pages = [_page(DWG, 1, text), _page(CTL, 1, text)]
    sheets = [_sheet(1, "M-101", "HVAC FIRST FLOOR PLAN"), _sheet(1, "C-101", "CONTROLS FIRST FLOOR PLAN", CTL)]
    d = build_dossier(_catalogue(pages, sheets, ["EBB-A", "EBB-B", "EBB-C"], documents), _reading(), tmp_path)
    assert d.counts["EBB"]["plan_placements"] == 14
    assert "M-101 and C-101 may show one plan" in _line("EBB", d)
    # plan_areas itself never merges them now (FINAL-G), on type tags or on unit tags; the hint names them
    sheets = [_sheet(1, "M-101", "HVAC FIRST FLOOR PLAN"), _sheet(1, "C-101", "CONTROLS FIRST FLOOR PLAN", CTL)]
    for tags in (Counter({"EBB-A": 4, "EBB-B": 2, "EBB-C": 2}), Counter({"VAV-1": 1, "VAV-2": 1, "VAV-3": 1})):
        plans = [(s, tags) for s in sheets]
        found = plan_areas(plans)
        assert found[(DWG, 1)] != found[(CTL, 1)]
        assert plan_area_doubts(plans, found) == [((DWG, 1), (CTL, 1))]
