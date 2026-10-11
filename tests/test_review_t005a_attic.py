"""Reviewer's test for T-005a (lead review, 2026-10-11). Invented fixture: five heat recovery units HRU-1..5 in one
attic, drawn on four new-work plans (a ductwork plan, a piping plan, and part plans A and B that share HRU-3), one
demolition plan that shows the five units plus HRU-6, and a schedule of five rows. Rulings 1 and 2 of 2026-10-11."""
from estimator.reading.inventory import build_inventory, placements
from bms.plan_read import counts_clauses
from estimator.writing.dossier import build_dossier
from test_dossier_plan_areas import DWG, _catalogue, _line, _page, _reading, _schedule, _sheet

UNITS = [f"HRU-{n}" for n in range(1, 6)]


def _attic(schedule_tags=UNITS):
    pages = [_page(DWG, 1, "\n".join(UNITS)),
             _page(DWG, 2, "\n".join(UNITS)),
             _page(DWG, 3, "HRU-1\nHRU-2\nHRU-3"),
             _page(DWG, 4, "HRU-3\nHRU-4\nHRU-5"),
             _page(DWG, 5, "\n".join(UNITS + ["HRU-6"])),
             _page(DWG, 6, "HRU SCHEDULE\n" + "\n".join(schedule_tags))]
    sheets = [_sheet(1, "M-401", "HVAC ATTIC DUCTWORK PLAN"),
              _sheet(2, "M-402", "HVAC ATTIC PIPING PLAN"),
              _sheet(3, "M-403", "HVAC ATTIC PART PLAN A"),
              _sheet(4, "M-404", "HVAC ATTIC PART PLAN B"),
              _sheet(5, "MD-401", "HVAC ATTIC DEMOLITION PLAN", types=("Plans", "Demolition")),
              _sheet(6, "M-601", "MECHANICAL SCHEDULES", types=("Schedules",))]
    schedule = _schedule("HRU SCHEDULE", list(schedule_tags), 6, sheet="M-601")
    return _catalogue(pages, sheets, UNITS + ["HRU-6"]), _reading([schedule]), schedule


def test_five_units_on_four_attic_plans_and_a_demolition_plan_count_five_and_the_demolition_count_is_recorded(tmp_path):
    catalogue, reading, schedule = _attic()
    d = build_dossier(catalogue, reading, tmp_path)
    assert d.counts["HRU"]["plan_placements"] == 5
    line = _line("HRU", d)
    # the demolition-only unit is named with both numbers, not silently dropped
    assert "HRU-6 is on demolition sheets only (MD-401): left out of the count, 5; with the demolition sheets, 6" in line
    # the shared tag of the part plans is named as a duplicate with both numbers
    assert "HRU-3 is on 4 plans" in line and "counted once, 1" in line
    # the inventory agrees: five units, HRU-6 not among them
    items, totals, _dropped = build_inventory(catalogue, [schedule])
    hru = [i for i in items if i.tag.startswith("HRU-")]
    print("HRU ITEMS", [(i.tag, i.category, i.quantity) for i in hru])
    assert sum(i.quantity or 0 for i in hru) == 5               # one per scheduled unit; HRU-6 adds nothing
    assert "HRU-6" not in {i.tag for i in hru if i.quantity}
    # the inventory's placements keep the demolition labels apart (recorded, not counted)
    placed = placements(catalogue, UNITS + ["HRU-6"])
    assert all(placed[t].count == 1 for t in UNITS)
    assert placed["HRU-6"].count == 0 and placed["HRU-6"].demolition == {"MD-401": 1}
    # the numbers the planner reads from the counts line: record what reaches the bms Count (for the review)
    print("CLAUSES", counts_clauses(line))


def test_a_scheduled_unit_seen_only_on_a_demolition_plan_is_not_dropped(tmp_path):
    """The schedule is the floor: HRU-6 on the schedule stays a unit even if only a demolition plan draws it."""
    catalogue, reading, schedule = _attic(UNITS + ["HRU-6"])
    d = build_dossier(catalogue, reading, tmp_path)
    line = _line("HRU", d)
    assert "schedule rows 6" in line
    items, _totals, _dropped = build_inventory(catalogue, [schedule])
    six = [i for i in items if i.tag == "HRU-6"]
    print("HRU-6 ITEMS", [(i.category, i.quantity, i.reason) for i in six])
    assert six and all((i.quantity or 0) >= 1 for i in six)
    print("CLAUSES", counts_clauses(line))
    assert max(n for _c, n in counts_clauses(line)) >= 6


def test_a_numbered_tag_on_two_floor_plans_with_no_typical_is_counted_once_with_both_numbers(tmp_path):
    """Adversarial: EF-1 on LEVEL 1 and LEVEL 2 plans (no typical sheet, a one-row schedule with no QTY column).
    The lead's ruling on the review: 1 counted, and the 2 with both sheets in a note the planner reads."""
    pages = [_page(DWG, 1, "EF-1"), _page(DWG, 2, "EF-1"), _page(DWG, 3, "EF SCHEDULE\nEF-1")]
    sheets = [_sheet(1, "M-101", "HVAC LEVEL 1 PLAN"), _sheet(2, "M-102", "HVAC LEVEL 2 PLAN"),
              _sheet(3, "M-601", "MECHANICAL SCHEDULES", types=("Schedules",))]
    d = build_dossier(_catalogue(pages, sheets, ["EF-1"]),
                      _reading([_schedule("EF SCHEDULE", ["EF-1"], 3, sheet="M-601")]), tmp_path)
    line = _line("EF", d)
    print("EF LINE", line)
    assert d.counts["EF"]["plan_placements"] == 1
    assert "if each plan's EF-1 is its own unit (a type used once per plan), 2" in line
    assert ("drawn on more than one plan sheet (M-101, M-102), counted once, not added: 1 counted, 2 if the sheets "
            "were added up") in line
    print("CLAUSES", counts_clauses(line))


def test_a_family_drawn_only_on_a_demolition_plan_is_named_somewhere(tmp_path):
    """Ruling 1: a unit left out is named with both numbers. UH-1 is only on the demolition plan, with no schedule.
    Records today's behavior (review finding 5, open): UH-1 is only in the sheet's own text line, with no counts line."""
    catalogue, reading, _schedule_ = _attic()
    pages = list(catalogue.pages)
    pages[4] = _page(DWG, 5, chr(10).join(UNITS + ["HRU-6", "UH-1"]))
    catalogue.pages = tuple(pages)
    from estimator.catalogue.tags import TagEntry
    catalogue.tags = (*catalogue.tags, TagEntry("UH-1", "", (), ("M-101",), 2))
    d = build_dossier(catalogue, reading, tmp_path)
    print("UH IN TEXT", [l[:200] for l in d.text.splitlines() if "UH-1" in l])
    assert "UH-1" in d.text
