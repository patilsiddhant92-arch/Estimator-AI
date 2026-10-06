"""FINAL-G: plan placements that cannot undercount by construction (lead ruling after REVIEW-FINAL4).

- A unit's tag (a unit number in it: VAV-101, EF-3, ACCU-109) is one unit however many plan sheets show it and however
  many times one sheet labels it: the family's placements count each distinct unit tag once (times the floors of a
  typical sheet), with no reading of titles at all.
- A type's tag (EBB-A, CUH-A, a schedule's type code, AC-3.0) counts at every place it is drawn, summed over the
  sheets and never merged: where one plan is drawn twice that is an overcount, kept (the higher count) and named.
- Which sheets may show one plan is only a hint for the counts line's reading notes; it never lowers a count, and
  "same plan as" (the old merge's words, read back as the client cause "a floor drawn on two plan sheets counted
  once") is never printed.
Invented fixtures only."""
from collections import Counter

from estimator.reading.inventory import placements, plan_area_doubts
from estimator.writing.dossier import build_dossier, plan_areas
from test_dossier_plan_areas import CTL, DWG, OTHER, _catalogue, _doc, _line, _page, _reading, _schedule, _sheet

BOXES = [f"VAV-{n}" for n in range(1, 6)]


def test_a_unit_tag_on_two_sheets_of_two_documents_adds_up_and_is_named(tmp_path):
    """A ductwork plan and its controls plan of one area, in two documents. FINAL-I (lead ruling, the final counting
    rule): sheets of two documents are never one plan group, so the groups add up, 10 (FINAL-G counted each box once,
    5, which lost numbered types placed once per floor); the higher count is named as maybe one plan."""
    text = "\n".join(BOXES)
    pages = [_page(DWG, 1, text), _page(CTL, 1, text)]
    sheets = [_sheet(1, "M-101", "DUCTWORK PLAN - SUITE 3"), _sheet(1, "C-101", "CONTROLS PLAN - SUITE 3", CTL)]
    d = build_dossier(_catalogue(pages, sheets, BOXES, [_doc(DWG, 1), _doc(CTL, 1)]), _reading(), tmp_path)
    assert d.counts["VAV"]["plan_placements"] == 10
    line = _line("VAV", d)
    assert "same plan as" not in line
    assert "M-101 5" in line and "C-101 5" in line            # every sheet still listed for the evidence
    assert "M-101 and C-101 may show one plan; both are counted, the higher count" in line


def test_a_unit_tag_printed_twice_on_one_sheet_is_one_unit(tmp_path):
    pages = [_page(DWG, 1, "ACCU-1\nACCU-1\nACCU-2\nACCU-2"), _page(DWG, 2, "ACCU SCHEDULE\nACCU-1\nACCU-2")]
    sheets = [_sheet(1, "M-106", "HVAC ROOF PLAN"), _sheet(2, "M-601", "SCHEDULES", types=("Schedules",))]
    d = build_dossier(_catalogue(pages, sheets, ["ACCU-1", "ACCU-2"]),
                      _reading([_schedule("ACCU SCHEDULE", ["ACCU-1", "ACCU-2"], 2)]), tmp_path)
    assert d.counts["ACCU"]["plan_placements"] == 2
    assert "likely" not in _line("ACCU", d)                  # nothing above the other counts left to explain


def test_a_unit_tag_on_the_plans_of_three_floors_counts_on_each_and_is_named(tmp_path):
    """FINAL-I (lead ruling): three floors' plans are three plan groups and add up, 3 (FINAL-G gave 1, which lost a
    numbered type used once per floor); the reading note names EF-1 and says it may be one unit."""
    pages = [_page(DWG, 1, "EF-1"), _page(DWG, 2, "EF-1"), _page(DWG, 3, "EF-1")]
    sheets = [_sheet(1, "M-101", "HVAC FIRST FLOOR PLAN"), _sheet(2, "M-102", "HVAC SECOND FLOOR PLAN"),
              _sheet(3, "M-106", "HVAC ROOF PLAN")]
    d = build_dossier(_catalogue(pages, sheets, ["EF-1"]), _reading(), tmp_path)
    assert d.counts["EF"]["plan_placements"] == 3
    assert "EF-1 is on 3 plans (M-101, M-102, M-106), counted on each, 3" in _line("EF", d)


def test_type_tags_on_a_floor_drawn_twice_add_up_and_the_line_names_the_two_sheets(tmp_path):
    """EBB types on the first floor's ductwork plan and on its controls plan, one document. FINAL-I (lead ruling):
    the same floor title and three unit tags repeated make one plan group, so a type counts the most labels of one
    sheet, 8 (FINAL-G summed, 16), and each box once; the line names the group for a check."""
    text = "EBB-A\nEBB-A\nEBB-A\nEBB-A\nEBB-B\nEBB-B\nEBB-C\nEBB-D\nVAV-1\nVAV-2\nVAV-3"
    pages = [_page(DWG, 1, text), _page(DWG, 2, text)]
    sheets = [_sheet(1, "M-101", "HVAC DUCTWORK FIRST FLOOR PLAN"),
              _sheet(2, "M-201", "HVAC PIPING AND CONTROLS FIRST FLOOR PLAN")]
    tags = ["EBB-A", "EBB-B", "EBB-C", "EBB-D", "VAV-1", "VAV-2", "VAV-3"]
    d = build_dossier(_catalogue(pages, sheets, tags), _reading(), tmp_path)
    assert d.counts["EBB"]["plan_placements"] == 8
    assert d.counts["VAV"]["plan_placements"] == 3
    line = _line("EBB", d)
    assert "same plan as" not in line and "may show one plan" not in line
    assert "M-101 and M-201 counted as one plan: same floor title, same units; check" in line
    assert "may show one plan" not in _line("VAV", d)


def test_a_numbered_tag_placed_at_many_places_counts_every_place(tmp_path):
    """FCU-1 at five places on each of two sheets of one floor: a numbered type (the inventory's rule, 3 places and
    4 on one sheet), so every place counts (10, the higher count) and the cause is named; before, merged (5)."""
    text = "\n".join(["FCU-1"] * 5)
    pages = [_page(DWG, 1, text), _page(DWG, 2, text)]
    sheets = [_sheet(1, "M-101", "HVAC DUCTWORK FIRST FLOOR PLAN"),
              _sheet(2, "M-201", "HVAC PIPING AND CONTROLS FIRST FLOOR PLAN")]
    d = build_dossier(_catalogue(pages, sheets, ["FCU-1"]), _reading(), tmp_path)
    assert d.counts["FCU"]["plan_placements"] == 10
    line = _line("FCU", d)
    assert "likely a typical unit placed at each place" in line
    assert "M-101 and M-201 may show one plan" in line


def test_a_unit_tag_on_a_typical_floor_drawn_twice_counts_once_per_floor(tmp_path):
    """A typical floor plan standing for 10 floors is drawn twice (ductwork and piping), each with VAV-1 to 3: 30
    boxes (3 on each of 10 floors), never 60. The floors multiply a unit's tag; they never make it a type."""
    from types import SimpleNamespace
    text = "VAV-1\nVAV-2\nVAV-3"
    pages = [_page(DWG, 1, text), _page(DWG, 2, text)]
    sheets = [_sheet(1, "M-102", "TYPICAL FLOOR DUCTWORK PLAN"), _sheet(2, "M-202", "TYPICAL FLOOR PIPING PLAN")]
    floors = tuple(range(2, 12))
    reading = _reading()
    reading.typicals = (SimpleNamespace(sheet="M-102", floors=floors), SimpleNamespace(sheet="M-202", floors=floors))
    d = build_dossier(_catalogue(pages, sheets, ["VAV-1", "VAV-2", "VAV-3"]), reading, tmp_path)
    assert d.counts["VAV"]["plan_placements"] == 30


def test_plan_areas_never_groups_sheets_and_the_doubts_name_the_hint():
    """plan_areas is retired: every sheet is its own area (nothing is ever merged). plan_area_doubts names the
    pairs that may show one plan: one readable floor and part, one document with one title, or repeated unit tags;
    never two floors the titles name apart."""
    tags = Counter({"VAV-1": 1, "VAV-2": 1, "VAV-3": 1, "EBB-A": 4})
    sheets = [_sheet(1, "M-101", "HVAC FIRST FLOOR PLAN"), _sheet(1, "C-101", "CONTROLS FIRST FLOOR PLAN", CTL),
              _sheet(2, "M-102", "HVAC SECOND FLOOR PLAN"), _sheet(3, "M-301", "ENLARGED PLAN"),
              _sheet(1, "B-101", "SECOND FLOOR PLAN", OTHER)]
    plans = [(s, tags) for s in sheets]
    found = plan_areas(plans)
    assert len(set(found.values())) == len(sheets)
    doubts = {(a[0], a[1], b[0], b[1]) for a, b in plan_area_doubts(plans, found)}
    assert (DWG, 1, CTL, 1) in doubts                          # one floor named the same way
    assert (DWG, 1, DWG, 3) in doubts                          # the enlarged plan repeats the floor's unit tags
    assert (DWG, 2, OTHER, 1) in doubts                        # second floor in two documents
    assert (DWG, 1, DWG, 2) not in doubts                      # two floors the titles name apart


def test_the_inventory_sums_a_type_tag_over_two_sheets_of_one_floor():
    """The type-tag check counts every place, never the most on one sheet of a merged area: 8, not 4."""
    four = "\n".join(["EBB-A"] * 4)
    pages = [_page(DWG, 1, four), _page(DWG, 2, four)]
    sheets = [_sheet(1, "M-101", "HVAC DUCTWORK FIRST FLOOR PLAN"),
              _sheet(2, "M-201", "HVAC PIPING AND CONTROLS FIRST FLOOR PLAN")]
    found = placements(_catalogue(pages, sheets, ["EBB-A"]), ["EBB-A"], (), {(DWG, 1), (DWG, 2)})
    assert found["EBB-A"].total == 8
    assert found["EBB-A"].plans_text() == "M-101 4, M-201 4"
