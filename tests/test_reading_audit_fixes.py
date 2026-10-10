"""Regression tests for the reading-layer audit fixes of 2026-10-09 (READ-1 to READ-5). Invented fixtures only.

READ-1  a title centred over the sheet number is read whole, never cut to its last line ("1 OF 2").
READ-2  one floor's plans of several trades (ductwork, piping, zoning, controls) are one set of placements: the most
        of any one sheet, never the sum.
READ-3  a schedule of passive air devices by type (diffusers, grilles, air outlets) never gives units, families or
        controls systems, whatever its codes look like (B1 is no boiler, CD/RG/LRD-A no equipment).
READ-4  a table that lists units but could not be read never blocks the text count of its sheet and never gives a
        silent zero: its units are counted from the sheet's text outside the tables that were read, and flagged.
READ-5  key headers the exact list misses ("UNIT", "AC UNIT", "PUMP NO.", a blank header under a letter-spaced band)
        are read when the column below them is unit tags.
"""
from pathlib import Path

from estimator.catalogue.pdf import Span
from estimator.catalogue.title_block import read_title_block
from estimator.reading.inventory import build_inventory, plan_groups
from estimator.reading.schedules import (Schedule, ScheduleRow, lists_air_devices, read_schedules,
                                         schedule_from_cells, vocabulary)
from estimator.writing.dossier import build_dossier
from test_dossier_plan_areas import DWG, _catalogue, _page, _reading, _sheet
from test_schedules import catalogue_for, grid


# ---- READ-1: centred titles ------------------------------------------------------------------------------------

NUMBER = Span("M-401.00", 22.5, 0.939, 0.946, 0.972, 0.959)


def test_a_centred_two_line_title_is_read_whole_not_cut_to_its_last_line():
    spans = [Span("MECHANICAL SCHEDULES SHEET", 16.9, 0.877, 0.825, 0.973, 0.835),
             Span("1 OF 2", 16.9, 0.916, 0.838, 0.934, 0.848), NUMBER]
    assert read_title_block(spans).title == "MECHANICAL SCHEDULES SHEET 1 OF 2"


def test_a_centred_one_line_title_starting_well_left_of_the_number_is_read():
    spans = [Span("MECHANICAL DETAILS SHEET 1 OF 3", 16.9, 0.873, 0.831, 0.977, 0.841), NUMBER]
    assert read_title_block(spans).title == "MECHANICAL DETAILS SHEET 1 OF 3"


def test_a_centred_floor_plan_title_keeps_its_floor_words():
    spans = [Span("MECHANICAL 9TH FLOOR PIPING AND", 16.9, 0.870, 0.825, 0.981, 0.835),
             Span("CONTROLS PLAN", 16.9, 0.900, 0.838, 0.949, 0.848), NUMBER]
    assert read_title_block(spans).title == "MECHANICAL 9TH FLOOR PIPING AND CONTROLS PLAN"


def test_a_line_of_the_column_beside_the_number_is_never_its_title():
    """A line that ends before the number's column begins sits in another column of the title block."""
    spans = [Span("ACME ENGINEERS", 16.9, 0.800, 0.830, 0.900, 0.840),
             Span("HEATING PLAN", 16.9, 0.930, 0.830, 0.975, 0.840), NUMBER]
    assert read_title_block(spans).title == "HEATING PLAN"


# ---- READ-3: air-device type schedules -------------------------------------------------------------------------

def _outlet_page(title="AIR OUTLET SCHEDULE"):
    rows = [[title, "", ""], ["DESIGNATION", "DESCRIPTION", "NECK SIZE"],
            ["B1", "LINEAR SUPPLY DIFFUSER", "8"], ["B2", "LINEAR SUPPLY DIFFUSER", "10"],
            ["B3", "LINEAR RETURN DIFFUSER", "12"], ["B4", "CURVED LINEAR DIFFUSER", "8"]]
    return grid(200, 200, [90, 200, 80], rows)


def test_an_air_outlet_schedules_b1_to_b4_are_types_never_boilers(tmp_path):
    catalogue, opener = catalogue_for(tmp_path, _outlet_page())
    [schedule] = read_schedules(catalogue, opener)
    assert schedule.passive and schedule.type_only
    assert [row.tag for row in schedule.rows] == [None, None, None, None]
    _items, totals, flags = build_inventory(catalogue, [schedule])
    assert not [t for t in totals if t.prefix == "B"]
    assert any("lists air-device types (B1, B2, B3, B4)" in f and "not counted" in f for f in flags)


def test_an_untitled_diffuser_schedule_is_known_by_its_basis_line_and_band_rows(tmp_path):
    rows = [["MFR. (AS STD.) ACME DIFFUSERS REGISTERS AND GRILLES", "", ""], ["TYPE", "SERVICE", "MODEL"],
            ["RETURN AND EXHAUST GRILLES", "", ""], ["RG", "RETURN", "350RL"], ["EG", "EXHAUST", "350RL"],
            ["LRD-A", "RETURN", "FL-15"], ["SUPPLY DIFFUSERS", "", ""], ["CD", "SUPPLY", "OMNI"]]
    catalogue, opener = catalogue_for(tmp_path, grid(200, 200, [200, 90, 80], rows))
    [schedule] = read_schedules(catalogue, opener)
    assert schedule.passive and schedule.type_only and not any(row.tag for row in schedule.rows)
    items, _totals, flags = build_inventory(catalogue, [schedule])
    assert not [i for i in items if i.category == "TYPE ONLY"]       # no type-only item: never a controls system
    assert any("lists air-device types (RG, EG, LRD-A, CD" in f for f in flags)


def test_an_air_device_schedules_codes_never_become_dossier_families(tmp_path):
    """The codes' labels on the plans (B-1 placed many times) give no family on the counts line, so no system."""
    pages = [_page(DWG, 1, "\n".join(["B-1"] * 5 + ["B-2"] * 3 + ["CD"] * 4)), _page(DWG, 2, "AIR OUTLET SCHEDULE")]
    sheets = [_sheet(1, "M-101", "HVAC FIRST FLOOR PLAN"), _sheet(2, "M-601", "SCHEDULES", types=("Schedules",))]
    rows = tuple(ScheduleRow(None, {"DESIGNATION": code, "DESCRIPTION": "DIFFUSER"}, None, None, False)
                 for code in ("B1", "B2", "CD"))

    def outlet(passive):
        return Schedule(DWG, 2, "M-601", "Schedule (no title found)", ("DESIGNATION", "DESCRIPTION"), rows, True,
                        (), (), passive=passive)

    catalogue = _catalogue(pages, sheets, ["B-1", "B-2"])
    d = build_dossier(catalogue, _reading([outlet(True)]), tmp_path / "a")
    assert "B" not in d.counts and "CD" not in d.counts
    control = build_dossier(catalogue, _reading([outlet(False)]), tmp_path / "b")
    assert "CD" in control.counts          # the same codes without the air-device mark would be families


def test_a_schedule_read_by_eye_of_air_outlets_lists_no_units():
    schedule = schedule_from_cells("LINEAR DIFFUSER SCHEDULE", ["DESIGNATION", "DESCRIPTION"],
                                   [["B1", "SLOT DIFFUSER"], ["B2", "SLOT DIFFUSER"]], [], ("Mech.pdf", 4, "M-601"))
    assert schedule.passive and [row.tag for row in schedule.rows] == [None, None]


def test_a_boiler_schedule_keeps_its_boilers_and_a_pump_schedule_its_pumps(tmp_path):
    for title, codes in (("BOILER SCHEDULE", ["B-1", "B-2"]), ("PUMP SCHEDULE", ["P1", "P2"])):
        rows = [[title, "", ""], ["TAG", "SERVICE", "GPM"]] + [[code, "HEATING", "40"] for code in codes]
        catalogue, opener = catalogue_for(tmp_path, grid(200, 200, [90, 120, 70], rows))
        [schedule] = read_schedules(catalogue, opener)
        assert not schedule.passive and len([row for row in schedule.rows if row.tag]) == 2, title


def test_a_one_letter_code_without_its_dash_under_another_kinds_title_is_no_unit(tmp_path):
    rows = [["TERMINAL UNIT SCHEDULE", "", ""], ["TAG", "SERVICE", "CFM"], ["B1", "OFFICE", "400"],
            ["B2", "OFFICE", "500"]]
    catalogue, opener = catalogue_for(tmp_path, grid(200, 200, [90, 120, 70], rows))
    [schedule] = read_schedules(catalogue, opener)
    assert not any(row.tag and row.tag.startswith("B-") for row in schedule.rows)


def test_air_device_words_are_found_in_the_title_the_basis_or_most_descriptions():
    vocab = vocabulary()
    assert lists_air_devices("SUPPLY AIR OUTLET SCHEDULE", vocab)
    assert lists_air_devices("Schedule (no title found)", vocab, ["ACME DIFFUSERS AND GRILLES"])
    assert lists_air_devices("Schedule (no title found)", vocab, (), ["SLOT DIFFUSER", "RETURN GRILLE", "x"])
    assert not lists_air_devices("VAV BOX SCHEDULE", vocab, (), ["PROVIDE WITH DIFFUSER", "OFFICE", "OFFICE"])


# ---- READ-5: key headers the exact list misses -----------------------------------------------------------------

def test_a_unit_header_and_a_pump_no_header_are_read(tmp_path):
    ac = grid(200, 200, [90, 120, 70], [["UNIT", "SERVICE", "CFM"], ["AC-3-1", "OFFICE", "4000"],
                                        ["AC-3-2", "OFFICE", "6000"]])
    pumps = grid(200, 300, [90, 120, 70], [["CONDENSATE PUMPS", "", ""], ["PUMP No.", "SERVICE", "GPH"],
                                           ["CP-1", "AC-3-1", "70"], ["CP-2", "AC-3-2", "70"]])
    catalogue, opener = catalogue_for(tmp_path, (ac[0] + pumps[0], ac[1] + pumps[1] + ((200, 192, "AC UNITS", 10),)))
    schedules = read_schedules(catalogue, opener)
    assert {s.title: [r.tag for r in s.rows] for s in schedules} == {"AC UNITS": ["AC-3-1", "AC-3-2"],
                                                                    "CONDENSATE PUMPS": ["CP-1", "CP-2"]}


def test_two_unit_columns_side_by_side_are_two_schedules(tmp_path):
    """A split system: the indoor unit's UNIT column, then the outdoor unit's UNIT column under its own band."""
    rows = [["SPLIT SYSTEMS", "", "", "", ""], ["UNIT", "SERVICE", "OUTDOOR SECTION", "", ""],
            ["", "", "UNIT", "CFM", "VOLTS"], ["AC-3-1", "OFFICE", "ACCU-3-1", "1500", "208"]]
    catalogue, opener = catalogue_for(tmp_path, grid(200, 200, [90, 90, 90, 60, 60], rows))
    tags = sorted(row.tag for s in read_schedules(catalogue, opener) for row in s.rows if row.tag)
    assert tags == ["AC-3-1", "ACCU-3-1"]


def test_an_associated_unit_column_never_splits_the_schedule(tmp_path):
    """ASSOCIATED CONDENSING UNIT names one outdoor unit on several rows: it is no key column."""
    rows = [["INDOOR UNIT SCHEDULE", "", ""], ["TAG", "ASSOCIATED CONDENSING UNIT", "CFM"],
            ["IDU-1", "CU-1", "300"], ["IDU-2", "CU-1", "300"], ["IDU-3", "CU-1", "400"]]
    catalogue, opener = catalogue_for(tmp_path, grid(200, 200, [90, 200, 70], rows))
    [schedule] = read_schedules(catalogue, opener)
    assert [row.tag for row in schedule.rows] == ["IDU-1", "IDU-2", "IDU-3"]


def test_a_blank_key_header_under_a_letter_spaced_band_is_read_with_the_title_above(tmp_path):
    rows = [["F A N D A T A", "", "", ""], ["", "CFM", "RPM", "VOLTS"], ["EF-3-1", "250", "980", "115"]]
    lines, texts = grid(200, 200, [90, 70, 70, 70], rows)
    catalogue, opener = catalogue_for(tmp_path, (lines, texts + ((200, 192, "EXHAUST FANS", 10),)))
    [schedule] = read_schedules(catalogue, opener)
    assert schedule.title == "EXHAUST FANS" and [row.tag for row in schedule.rows] == ["EF-3-1"]


def test_a_maker_line_above_the_table_is_not_its_title(tmp_path):
    rows = [["UNIT NO.", "SERVICE", "CFM"], ["EF-1", "TOILETS", "300"]]
    lines, texts = grid(200, 200, [90, 120, 70], rows)
    texts += ((200, 180, "EXHAUST FAN SCHEDULE", 10), (200, 193, "MFR. (AS STD.) ACME", 7))
    catalogue, opener = catalogue_for(tmp_path, (lines, texts))
    [schedule] = read_schedules(catalogue, opener)
    assert schedule.title == "EXHAUST FAN SCHEDULE" and schedule.rows[0].tag == "EF-1"


# ---- READ-4: one good table never blocks the others ------------------------------------------------------------

def test_a_table_that_cannot_be_read_beside_one_that_can_is_counted_from_text_and_flagged(tmp_path):
    good = grid(200, 200, [90, 120, 70], [["UNIT NO.", "SERVICE", "CFM"], ["VAV-1", "OFFICE", "300"],
                                          ["VAV-2", "OFFICE", "400"]])
    # a key header no rule can know, and a band merged over it: the table can't be read
    bad = grid(600, 200, [90, 120, 70], [["ITEM", "SERVICE", "CFM"], ["EF-7", "TOILETS", "300"],
                                         ["EF-8", "JANITOR", "200"]])
    catalogue, opener = catalogue_for(tmp_path, (good[0] + bad[0], good[1] + bad[1]))
    flags: list[str] = []
    schedules = read_schedules(catalogue, opener, flags=flags)
    from_text = [row.tag for s in schedules if s.from_text for row in s.rows]
    assert from_text == ["EF-7", "EF-8"]
    assert [row.tag for s in schedules if not s.from_text for row in s.rows] == ["VAV-1", "VAV-2"]
    assert any("EF-7, EF-8 could not be read from its table" in f and "counted from the sheet's text" in f
               for f in flags)
    _items, totals, _flags = build_inventory(catalogue, schedules)
    ef = next(t for t in totals if t.prefix == "EF")
    assert ef.scheduled == 2 and any("text" in f for f in ef.flags)      # never a silent zero


def test_a_service_column_naming_read_units_is_not_counted_again(tmp_path):
    """The units a read table already lists are never counted a second time from the text."""
    good = grid(200, 200, [90, 120, 70], [["UNIT NO.", "SERVICE", "CFM"], ["AC-1", "OFFICE", "300"]])
    bad = grid(600, 200, [90, 120, 70], [["ITEM", "SERVES", "GPH"], ["", "AC-1", "70"]])
    catalogue, opener = catalogue_for(tmp_path, (good[0] + bad[0], good[1] + bad[1]))
    schedules = read_schedules(catalogue, opener, flags=[])
    assert sorted(row.tag for s in schedules for row in s.rows if row.tag) == ["AC-1"]


# ---- READ-2: one floor's plans of several trades are one set of placements -------------------------------------

def _plans(*titles, document=DWG):
    return [(_sheet(n, f"M-{n}00", title, document), {}) for n, title in enumerate(titles, start=1)]


def test_a_floors_ductwork_piping_and_zoning_plans_are_one_plan_group():
    plans = _plans("FLOOR 30 - MECHANICAL DUCTWORK PLAN", "FLOOR 30 - MECHANICAL PIPING PLAN",
                   "FLOOR 30 - MECHANICAL ZONING PLAN", "FLOOR 31 - MECHANICAL DUCTWORK PLAN")
    groups = plan_groups(plans)
    assert groups[(DWG, 1)] == ((DWG, 1), (DWG, 2), (DWG, 3))
    assert groups[(DWG, 4)] == ((DWG, 4),)                       # another floor is never joined


def test_a_floor_plan_and_its_piping_and_controls_plan_are_one_plan_group():
    groups = plan_groups(_plans("MECHANICAL 9TH FLOOR PLAN", "MECHANICAL 9TH FLOOR PIPING AND CONTROLS PLAN"))
    assert len(groups[(DWG, 1)]) == 2


def test_a_demolition_an_enlarged_or_another_parts_plan_stays_apart():
    for other in ("FLOOR 30 - MECHANICAL DEMOLITION PLAN", "FLOOR 30 - ENLARGED MECHANICAL PIPING PLAN",
                  "FLOOR 30 - MECHANICAL PIPING PLAN - AREA B"):
        title = "FLOOR 30 - MECHANICAL DUCTWORK PLAN" + (" - AREA A" if "AREA" in other else "")
        groups = plan_groups(_plans(title, other))
        assert groups[(DWG, 1)] == ((DWG, 1),), other


def test_two_documents_plans_of_one_floor_are_never_joined():
    plans = [(_sheet(1, "M-100", "FLOOR 2 - DUCTWORK PLAN"), {}),
             (_sheet(1, "M-200", "FLOOR 2 - ZONING PLAN", document="Drawings/Controls.pdf"), {})]
    assert len(plan_groups(plans)[(DWG, 1)]) == 1


def test_a_type_labelled_on_a_floors_ductwork_and_zoning_plans_counts_the_most_of_one_sheet(tmp_path):
    """VAV-A labelled 10 times on the ductwork plan and 9 times on the zoning plan of one floor: 10, never 19;
    another floor adds up."""
    pages = [_page(DWG, 1, "\n".join(["VAV-A"] * 10)), _page(DWG, 2, "\n".join(["VAV-A"] * 9)),
             _page(DWG, 3, "\n".join(["VAV-A"] * 4)), _page(DWG, 4, "TERMINAL BOX SCHEDULE\nVAV-A")]
    sheets = [_sheet(1, "M-521", "FLOOR 21 - MECHANICAL DUCTWORK PLAN"),
              _sheet(2, "M-721", "FLOOR 21 - MECHANICAL ZONING PLAN"),
              _sheet(3, "M-522", "FLOOR 22 - MECHANICAL DUCTWORK PLAN"),
              _sheet(4, "M-401", "SCHEDULES", types=("Schedules",))]
    rows = (ScheduleRow("VAV-A", {"TAG": "VAV-A"}, None, None, False),)
    schedule = Schedule(DWG, 4, "M-401", "TERMINAL BOX SCHEDULE", ("TAG",), rows, False, (), ())
    d = build_dossier(_catalogue(pages, sheets, ["VAV-A"]), _reading([schedule]), tmp_path)
    assert d.counts["VAV"]["plan_placements"] == 10 + 4
