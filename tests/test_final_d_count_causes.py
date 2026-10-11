"""FINAL-D F5: the likely cause of a high plan count is a true one. "One unit's tag shown on several plans" is said
only of a unit's tag (a number in it); a type's tag (CUH-A) once on each of two different floors is most likely a
typical unit on each plan: the estimator checks the schedule's quantity, and the client reads "a typical unit at
each place". "A floor drawn on two plan sheets" is never said (FINAL-G: no sheets are merged), and a unit's tag on
two floors' plans is one unit now, with no cause to name. Invented fixtures only."""
from estimator.writing.dossier import build_dossier
from test_count_cause_note import _catalogue, _family_count, _note, _page, _reading, _sheet
from test_dossier_plan_areas import _line


def _two_floors(tag_text):
    pages = [_page(1, tag_text + "\nVAV-1"), _page(2, tag_text + "\nVAV-2"), _page(3, "SCHEDULE\nCUH-A\nEF-1")]
    sheets = [_sheet(1, "M-101", "HVAC FIRST FLOOR PLAN"), _sheet(2, "M-102", "HVAC SECOND FLOOR PLAN"),
              _sheet(3, "M-601", "SCHEDULES", types=("Schedules",))]
    return _catalogue(pages, sheets, ["CUH-A", "EF-1", "VAV-1", "VAV-2"]), _reading("SCHEDULE", ["CUH-A", "EF-1"], 3)


def test_a_type_tag_once_on_each_of_two_floors_is_a_typical_unit_on_each_plan(tmp_path):
    catalogue, reading = _two_floors("CUH-A")
    line = _line("CUH", build_dossier(catalogue, reading, tmp_path))
    assert "plan placements 2" in line
    assert "likely: a typical unit at each place" in line
    assert "shown again" not in line and "one unit's tag on several plans" not in line
    assert "check the schedule's quantity" in line
    # ruling L1: the note counts sheets (two sheets can be one floor and area), so it says "sheets", never "plans"
    assert ("CUH-A on 2 different sheets (M-101, M-102), a type's tag — likely a typical unit placed on each floor "
            "or area they show: check the schedule's quantity") in line
    assert "different plans" not in line
    (note,) = _note(_family_count(catalogue, reading, "CUH", tmp_path), "Cabinet Unit Heater", ("CUH-A",))
    assert "(2) per plan placements (likely a typical unit at each place)" in note
    assert "drawn on two plan sheets" not in note
    # a unit's tag (a number in it) once on each of two floors: FINAL-I (lead ruling) adds the two floors' plans up,
    # 2 (FINAL-G 1), names EF-1 in the reading notes and claims no cause in the line's head. T-005a (estimator ruling 2
    # of 2026-10-11): a numbered unit tag is one unit in the job, 1, and the note names both numbers
    catalogue, reading = _two_floors("EF-1")
    line = _line("EF", build_dossier(catalogue, reading, tmp_path))
    assert "plan placements 1 (" in line and "once per plan), 2" in line
    assert "placements above the other counts, likely" not in line and "shown again" not in line
    assert "EF-1 is on 2 plans" in line.split("Reading notes:", 1)[1]
