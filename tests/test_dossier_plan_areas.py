"""The plan placements of a family count each physical placement once (COUNT-DOUBLING, rule changed by FINAL-G).

A floor drawn twice — a ductwork plan and its piping and controls plan of the same floor — shows the same tags
twice. FINAL-G (lead ruling): a unit's tag (VAV-1) is one unit however many sheets show it, so it counts once with no
reading of titles; a type's tag (EBB-A) counts at every place on every sheet, never merged, so a floor drawn twice
may count it twice (the higher count) and the counts line names the two sheets as maybe one plan. Different floors
add up. Invented fixtures only."""
from pathlib import Path
from types import SimpleNamespace

from estimator.catalogue.documents import Document
from estimator.catalogue.overview import SpecOverview
from estimator.catalogue.register import PageRecord
from estimator.catalogue.sheet_types import Sheet
from estimator.catalogue.tags import TagEntry
from estimator.reading.inventory import plan_area_doubts
from estimator.reading.schedules import Schedule, ScheduleRow
from estimator.writing.dossier import build_dossier, plan_areas

DWG = "Drawings/Mech.pdf"
CTL = "Drawings/Controls.pdf"
OTHER = "Drawings/Second Building.pdf"


def _doc(relative, pages):
    return Document(Path(relative), relative, "drawings", "base", pages)


def _page(document, page, text):
    return PageRecord(document, page, "text", text, 0, True, ())


def _sheet(page, number, title, document=DWG, types=("Plans",)):
    return Sheet(document, page, number, title, "Mechanical", tuple(types))


def _catalogue(pages, sheets, tags, documents=None):
    documents = documents or [_doc(DWG, max(p.page for p in pages))]
    job = SimpleNamespace(name="26-9999", root=Path("."), documents=tuple(documents))
    return SimpleNamespace(job=job, pages=tuple(pages), sheets=tuple(sheets), sections=(),
                           tags=tuple(TagEntry(t, "", (), ("M-101",), 2) for t in tags), overview=SpecOverview(),
                           bid=None, flags=())


def _reading(schedules=()):
    return SimpleNamespace(schedules=tuple(schedules), totals=(), devices=(), typicals=(), notes=(), backbone=(),
                           versions=(), supersessions=(), inventory=(), legend=(), flags=())


def _schedule(title, tags, page, document=DWG, sheet="M-601"):
    rows = tuple(ScheduleRow(t, {"TAG": t}, None, None, False) for t in tags)
    return Schedule(document, page, sheet, title, ("TAG",), rows, False, (), (), False)


def _line(text, d):
    return next(line for line in d.text.splitlines() if f"] {text} (" in line)


BOXES = [f"VAV-{n}" for n in range(1, 7)]


def _overlay_job():
    """Two floors, each drawn twice: a ductwork plan (M-101, M-102) and a piping and controls plan (M-201, M-202)
    of the same floor. Floor one has VAV-1 to 3, floor two VAV-4 to 6; the schedule has six rows."""
    first, second = "\n".join(BOXES[:3]), "\n".join(BOXES[3:])
    pages = [_page(DWG, 1, first), _page(DWG, 2, second), _page(DWG, 3, first), _page(DWG, 4, second),
             _page(DWG, 5, "VAV SCHEDULE\n" + "\n".join(BOXES))]
    sheets = [_sheet(1, "M-101", "HVAC DUCTWORK FIRST FLOOR PLAN"),
              _sheet(2, "M-102", "HVAC DUCTWORK SECOND FLOOR PLAN"),
              _sheet(3, "M-201", "HVAC PIPING AND CONTROLS FIRST FLOOR PLAN"),
              _sheet(4, "M-202", "HVAC PIPING AND CONTROLS SECOND FLOOR PLAN"),
              _sheet(5, "M-601", "SCHEDULES", types=("Schedules",))]
    return _catalogue(pages, sheets, BOXES), _reading([_schedule("VAV SCHEDULE", BOXES, 5)])


def test_a_floor_drawn_on_a_ductwork_plan_and_its_controls_plan_counts_each_box_once(tmp_path):
    catalogue, reading = _overlay_job()
    d = build_dossier(catalogue, reading, tmp_path)
    assert d.counts["VAV"]["plan_placements"] == 6           # not 12: each floor is drawn twice
    assert d.counts["VAV"]["schedule_rows"] == 6
    line = _line("VAV", d)
    assert "plan placements 6 (" in line
    # every sheet the family is on is still listed (the evidence picks devices by these sheet numbers) ...
    for number in ("M-101", "M-102", "M-201", "M-202"):
        assert f"{number} 3" in line
    # ... never as "the same plan" (FINAL-G: each box counts once, no sheet is merged), and a unit-only family
    # needs no "may show one plan" note
    assert "same plan as" not in line
    assert "may show one plan" not in line


def test_the_sheets_that_may_show_one_plan_are_named_by_the_floor_their_titles_name(tmp_path):
    """FINAL-G: plan_areas never groups sheets any more; the floor the titles name is only the hint."""
    catalogue, _ = _overlay_job()
    plans = [(s, set(BOXES[:3] if s.page in (1, 3) else BOXES[3:])) for s in catalogue.sheets[:4]]
    areas = plan_areas(plans)
    assert len(set(areas.values())) == 4
    assert plan_area_doubts(plans, areas) == [((DWG, 1), (DWG, 3)), ((DWG, 2), (DWG, 4))]


def test_a_typical_type_tag_counts_per_place_and_floors_add_up(tmp_path):
    """EBB-A placed four times on the first floor and three times on the second: 7, even though both plans show the
    same tags (two different floors are never one plan)."""
    pages = [_page(DWG, 1, "\n".join(["EBB-A"] * 4 + ["EBB-B"])), _page(DWG, 2, "\n".join(["EBB-A"] * 3 + ["EBB-B"])),
             _page(DWG, 3, "EBB SCHEDULE\nEBB-A\nEBB-B")]
    sheets = [_sheet(1, "M-201", "PIPING AND CONTROLS FIRST FLOOR PLAN"),
              _sheet(2, "M-202", "PIPING AND CONTROLS SECOND FLOOR PLAN"),
              _sheet(3, "M-601", "SCHEDULES", types=("Schedules",))]
    catalogue = _catalogue(pages, sheets, ["EBB-A", "EBB-B"])
    d = build_dossier(catalogue, _reading([_schedule("EBB SCHEDULE", ["EBB-A", "EBB-B"], 3)]), tmp_path)
    assert d.counts["EBB"]["plan_placements"] == 4 + 1 + 3 + 1
    assert "same plan as" not in _line("EBB", d)


def test_a_typical_type_tag_on_a_floor_drawn_twice_counts_every_place_and_names_the_two_sheets(tmp_path):
    """FINAL-G: was 4 (the places of one drawing); a type's tag is never merged, so 8, the higher count, with the
    two sheets named as maybe one plan."""
    pages = [_page(DWG, 1, "\n".join(["EBB-A"] * 4)), _page(DWG, 2, "\n".join(["EBB-A"] * 4)),
             _page(DWG, 3, "EBB SCHEDULE\nEBB-A")]
    sheets = [_sheet(1, "M-101", "HVAC FIRST FLOOR PLAN"),
              _sheet(2, "M-201", "HVAC PIPING AND CONTROLS FIRST FLOOR PLAN"),
              _sheet(3, "M-601", "SCHEDULES", types=("Schedules",))]
    catalogue = _catalogue(pages, sheets, ["EBB-A"])
    d = build_dossier(catalogue, _reading([_schedule("EBB SCHEDULE", ["EBB-A"], 3)]), tmp_path)
    assert d.counts["EBB"]["plan_placements"] == 8
    assert "M-101 and M-201 may show one plan; both are counted, the higher count" in _line("EBB", d)


def test_a_plan_whose_title_names_no_floor_counts_each_box_once(tmp_path):
    """An enlarged plan with no floor in its title that shows three of the first floor's boxes: FINAL-G counts each
    box once (6 boxes, was 11 counted apart) whatever the titles say, so no "may show one plan" note is needed."""
    pages = [_page(DWG, 1, "VAV-1\nVAV-2\nVAV-3\nVAV-4"), _page(DWG, 2, "VAV-1\nVAV-2\nVAV-3"),
             _page(DWG, 3, "VAV-5\nVAV-6"), _page(DWG, 4, "VAV-5\nVAV-6")]
    sheets = [_sheet(1, "M-101", "HVAC FIRST FLOOR PLAN"), _sheet(2, "M-301", "ENLARGED MECHANICAL ROOM PLAN"),
              _sheet(3, "M-102", "HVAC SECOND FLOOR PLAN"), _sheet(4, "M-302", "ENLARGED PLAN SHEET 2")]
    catalogue = _catalogue(pages, sheets, [f"VAV-{n}" for n in range(1, 7)])
    d = build_dossier(catalogue, _reading(), tmp_path)
    assert d.counts["VAV"]["plan_placements"] == 6
    line = _line("VAV", d)
    assert "same plan as" not in line
    assert "may show one plan" not in line


def test_the_same_floor_in_another_document_counts_each_box_once_and_every_type_place(tmp_path):
    """Two documents each with a first floor plan, and a third set (another building). FINAL-G: each box counts
    once (6); the type tags add up over every sheet (2 + 2 + 3, was 2 + 3 with the first two merged), and the
    mechanical and controls sheets are named as maybe one plan."""
    documents = [_doc(DWG, 1), _doc(CTL, 1), _doc(OTHER, 1)]
    pages = [_page(DWG, 1, "VAV-1\nVAV-2\nVAV-3\nEBB-A\nEBB-A"), _page(CTL, 1, "VAV-1\nVAV-2\nVAV-3\nEBB-A\nEBB-A"),
             _page(OTHER, 1, "VAV-7\nVAV-8\nVAV-9\nEBB-A\nEBB-A\nEBB-A")]
    sheets = [_sheet(1, "M-101", "HVAC FIRST FLOOR PLAN"), _sheet(1, "C-101", "CONTROLS FIRST FLOOR PLAN", CTL),
              _sheet(1, "B-101", "FIRST FLOOR PLAN", OTHER)]
    tags = ["VAV-1", "VAV-2", "VAV-3", "VAV-7", "VAV-8", "VAV-9", "EBB-A"]
    d = build_dossier(_catalogue(pages, sheets, tags, documents), _reading(), tmp_path)
    assert d.counts["VAV"]["plan_placements"] == 6
    assert d.counts["EBB"]["plan_placements"] == 2 + 2 + 3
    assert "M-101 and C-101 may show one plan" in _line("EBB", d)


def test_a_unit_tag_on_the_plans_of_several_floors_is_one_unit(tmp_path):
    """EF-1 is one fan on the schedule and its tag is on three floors' plans (a duct or riser label). FINAL-G: a
    unit's tag is one unit, so 1 (was 3 with the cause "shown again" named); nothing is left to explain."""
    pages = [_page(DWG, 1, "EF-1"), _page(DWG, 2, "EF-1"), _page(DWG, 3, "EF-1"), _page(DWG, 4, "EF SCHEDULE\nEF-1")]
    sheets = [_sheet(1, "M-101", "HVAC FIRST FLOOR PLAN"), _sheet(2, "M-102", "HVAC SECOND FLOOR PLAN"),
              _sheet(3, "M-106", "HVAC ROOF PLAN"), _sheet(4, "M-601", "SCHEDULES", types=("Schedules",))]
    d = build_dossier(_catalogue(pages, sheets, ["EF-1"]), _reading([_schedule("EF SCHEDULE", ["EF-1"], 4)]), tmp_path)
    assert d.counts["EF"]["plan_placements"] == 1
    line = _line("EF", d)
    assert "M-101 1; M-102 1; M-106 1" in line                # every sheet still listed
    assert "likely" not in line


def test_a_type_tag_printed_twice_on_one_sheet_stays_the_higher_and_names_the_likely_cause(tmp_path):
    """FINAL-G: a unit's tag twice on one sheet (ACCU-1) is one unit now; a type's tag twice (EBB-B, below the
    typical rule) counts both places and the cause is named."""
    pages = [_page(DWG, 1, "EBB-B\nEBB-B\nEBB-C\nEBB-C"), _page(DWG, 2, "EBB SCHEDULE\nEBB-B\nEBB-C")]
    sheets = [_sheet(1, "M-106", "HVAC ROOF PLAN"), _sheet(2, "M-601", "SCHEDULES", types=("Schedules",))]
    d = build_dossier(_catalogue(pages, sheets, ["EBB-B", "EBB-C"]),
                      _reading([_schedule("EBB SCHEDULE", ["EBB-B", "EBB-C"], 2)]), tmp_path)
    assert d.counts["EBB"]["plan_placements"] == 4
    line = _line("EBB", d)
    assert "EBB-B 2 times on M-106" in line
    assert "likely one unit labelled more than once" in line


def test_no_cause_is_named_when_the_placements_are_not_above_the_other_counts(tmp_path):
    catalogue, reading = _overlay_job()
    d = build_dossier(catalogue, reading, tmp_path)
    assert "likely" not in _line("VAV", d)


def test_the_highest_number_on_the_counts_line_of_a_floor_drawn_twice_is_the_schedule_count(tmp_path):
    """The family count prints the highest clause of the counts line (bms.plan_read): with each floor drawn twice
    it is no longer twice the schedule."""
    from bms.plan_read import counts_clauses

    catalogue, reading = _overlay_job()
    d = build_dossier(catalogue, reading, tmp_path)
    assert max(n for _clause, n in counts_clauses(_line("VAV", d))) == 6


def test_a_floor_is_named_the_same_in_words_or_figures_and_its_parts_are_apart():
    """FINAL-G: the floor and parts the titles name are only the hint of `plan_area_doubts`; plan_areas never
    groups."""
    sheet = lambda page, title: _sheet(page, f"M-{page}", title)
    tags = {"VAV-1", "VAV-2", "VAV-3"}
    plans = [(sheet(1, "HVAC FIRST FLOOR PLAN"), tags), (sheet(2, "CONTROLS 1ST FLOOR PLAN"), tags),
             (sheet(3, "FIRST FLOOR PLAN - AREA A"), tags), (sheet(4, "FIRST FLOOR PLAN - AREA B"), tags),
             (sheet(5, "LEVEL 2 PLAN"), tags), (sheet(6, "SECOND FLOOR PLAN"), tags)]
    assert len(set(plan_areas(plans).values())) == 6
    doubts = plan_area_doubts(plans)
    assert ((DWG, 1), (DWG, 2)) in doubts and ((DWG, 5), (DWG, 6)) in doubts
    assert not {((DWG, 1), (DWG, 3)), ((DWG, 1), (DWG, 4)), ((DWG, 3), (DWG, 4)), ((DWG, 1), (DWG, 5))} & set(doubts)


def test_a_typical_type_tag_placed_many_times_is_named_a_typical_unit_not_a_repeated_label(tmp_path):
    """EBB-A at six places on each of two floors: 12 placements against one schedule row. The likely cause is a
    typical unit at each place (check the schedule's quantity), not one unit labelled again."""
    pages = [_page(DWG, 1, "\n".join(["EBB-A"] * 6)), _page(DWG, 2, "\n".join(["EBB-A"] * 6)),
             _page(DWG, 3, "EBB SCHEDULE\nEBB-A")]
    sheets = [_sheet(1, "M-201", "PIPING AND CONTROLS FIRST FLOOR PLAN"),
              _sheet(2, "M-202", "PIPING AND CONTROLS SECOND FLOOR PLAN"),
              _sheet(3, "M-601", "SCHEDULES", types=("Schedules",))]
    d = build_dossier(_catalogue(pages, sheets, ["EBB-A"]), _reading([_schedule("EBB SCHEDULE", ["EBB-A"], 3)]),
                      tmp_path)
    assert d.counts["EBB"]["plan_placements"] == 12
    line = _line("EBB", d)
    assert "EBB-A 12 places, 6 on M-201" in line
    assert "likely a typical unit placed at each place: check the schedule's quantity" in line
    assert "shown again" not in line
    assert "labelled more than once" not in line
