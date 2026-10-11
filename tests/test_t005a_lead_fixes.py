"""The lead's rulings on the T-005a review (2026-10-11). Invented fixtures only.

(1) A numbered unit tag is one unit in the job, across areas and floors too, but the reduction prints: the higher
    number and the sheets it came from reach the count's '*' note data (`Count.added_up`, read by `bms.plan_read`),
    never only a dossier note.
(2) A demolition unit with named work is NOT added to the new-work count. It stays in `Placements.demolition`, with
    the work text kept beside it (`Placements.demolition_work`), for the Demolition Scope block."""
from estimator.ledger.facts import Ledger
from estimator.reading.inventory import build_inventory, placements
from estimator.writing.dossier import build_dossier

from bms.model import Count
from bms.plan_read import Reader
from test_dossier_plan_areas import DWG, _catalogue, _line, _page, _reading, _schedule, _sheet


def _two_floors(schedule=False):
    """EF-7 on the LEVEL 1 and LEVEL 2 plans of one building (no typical sheet), and EF-8 on LEVEL 1 only."""
    pages = [_page(DWG, 1, "EF-7\nEF-8"), _page(DWG, 2, "EF-7"), _page(DWG, 3, "EF SCHEDULE\nEF-7\nEF-8")]
    sheets = [_sheet(1, "M-171", "HVAC LEVEL 1 PLAN"), _sheet(2, "M-172", "HVAC LEVEL 2 PLAN"),
              _sheet(3, "M-671", "MECHANICAL SCHEDULES", types=("Schedules",))]
    schedules = [_schedule("EF SCHEDULE", ["EF-7", "EF-8"], 3, sheet="M-671")] if schedule else []
    return _catalogue(pages, sheets, ["EF-7", "EF-8"]), _reading(schedules), schedules


def test_a_unit_tag_on_two_floors_counts_once_and_the_note_names_both_numbers_and_sheets(tmp_path):
    catalogue, reading, _s = _two_floors(schedule=False)
    d = build_dossier(catalogue, reading, tmp_path)
    assert d.counts["EF"]["plan_placements"] == 2                      # EF-7 once, EF-8 once
    line = _line("EF", d)
    assert ("1 unit tag is drawn on more than one plan sheet (M-171, M-172), counted once, not added: 2 counted, 3 "
            "if the sheets were added up") in line


def test_the_planner_reads_the_higher_number_and_the_sheets_into_the_counts_star_note_data(tmp_path):
    catalogue, reading, _s = _two_floors(schedule=False)
    d = build_dossier(catalogue, reading, tmp_path)
    up = Reader(Ledger(), d.sources, d.text, d.families)._line_sum("EF")
    assert up is not None and up[0] == 3
    assert "M-171" in up[1].quote and "M-172" in up[1].quote and "2 counted" in up[1].quote
    count = Reader._with_sum(Count(2, (up[1],)), up)
    assert count.value == 2 and count.added_up is not None and count.added_up.value == 3


def test_a_scheduled_unit_tag_on_two_floors_keeps_its_sum_in_the_inventory_total():
    from test_inventory_same_floor import SCHEDULES, _catalogue as inventory_catalogue, _plan, _schedule as vav_schedule

    catalogue = inventory_catalogue([SCHEDULES, _plan("M-171", "HVAC LEVEL 1 PLAN", "VAV-7\nVAV-8"),
                                     _plan("M-172", "HVAC LEVEL 2 PLAN", "VAV-7")])
    placed = placements(catalogue, ["VAV-7", "VAV-8"])
    assert placed["VAV-7"].count == 1 and placed["VAV-7"].summed == 2
    assert "M-171 and M-172 show the same unit tag, one unit in the job" in placed["VAV-7"].same_plan_note(1, 2)
    _items, totals, _dropped = build_inventory(catalogue, [vav_schedule("VAV-7", "VAV-8")])
    [vav] = [t for t in totals if t.prefix == "VAV"]
    assert (vav.scheduled, vav.summed) == (2, 3)
    assert any("(M-171, M-172)" in f and "2 units counted, 3 if the sheets were added up" in f for f in vav.flags)
