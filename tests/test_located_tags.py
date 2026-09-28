"""Tags joined by underscores — a site code, a floor or area, sometimes a zone, then the unit
(SITE01_02_FCU03) — and tags written with no dash (CDU020). All data here is made up."""
import pytest

from estimator.catalogue.register import PageRecord
from estimator.catalogue.tags import Equipment, index_tags, tag_location, tag_prefix, find_tags
from estimator.reading.inventory import build_inventory, compact_tags
from estimator.reading.schedules import expand_tags, schedule_from_cells
from estimator.writing.write import tag_list
from tests.test_inventory import catalogue_with

EQUIPMENT = Equipment.load()
WHERE = ("Mech.pdf", 1, "M-601")


@pytest.mark.parametrize("text, tag", [
    ("ZUL07_02_CH01", "ZUL07_02_CH01"), ("ZUL07_02_FCU12", "ZUL07_02_FCU12"),
    ("ZUL07_B3_VAV21", "ZUL07_B3_VAV21"), ("ZUL07_B3_EF04", "ZUL07_B3_EF04"),
    ("ZUL07_02_HU03", "ZUL07_02_HU03"), ("ZUL07_02_DOAU01", "ZUL07_02_DOAU01"),
    ("ZUL07_02_EUH09", "ZUL07_02_EUH09"), ("ZUL07_02_NDH_CRAH14", "ZUL07_02_NDH_CRAH14"),
    ("ZUL07_02_NELEC3_CRAH02", "ZUL07_02_NELEC3_CRAH02"), ("ZUL07_02_CHPA01_FCU05", "ZUL07_02_CHPA01_FCU05"),
    ("ZUL07_02_FCU05A", "ZUL07_02_FCU05A")])
def test_an_underscore_tag_is_read_whole(text, tag):
    assert find_tags(f"SERVES {text} IN THE ROOM", EQUIPMENT) == [tag]


def test_the_kind_comes_from_the_last_segment_and_the_rest_is_the_location():
    assert tag_prefix("ZUL07_02_NDH_CRAH14") == "CRAH" and tag_location("ZUL07_02_NDH_CRAH14") == "ZUL07_02_NDH"
    assert tag_prefix("ZUL07_02_FCU12") == "FCU" and tag_location("ZUL07_02_FCU12") == "ZUL07_02"
    assert tag_prefix("AHU-1") == "AHU" and tag_location("AHU-1") is None
    assert tag_prefix("A15") == "A15"          # a type code on a schedule stays as it is
    pages = [PageRecord("mech.pdf", 1, "text", "ZUL07_02_CHPA01_FCU05 ON ROOF", 0)]
    [entry] = index_tags(pages, {}, EQUIPMENT)
    assert entry.kind == "Fan Coil Unit" and entry.location == "ZUL07_02_CHPA01"


def test_a_location_segment_is_never_the_kind():
    """NDH and CHPA01 are places: no tag is read from them alone."""
    assert find_tags("ZUL07_02_NDH ZUL07_02_CHPA01", EQUIPMENT) == []


def test_new_prefixes_are_known():
    for prefix, kind in {"TWAS": "Air Separator", "TST": "Thermal Storage Tank", "HU": "Humidifier",
                         "DOAU": "Dedicated Outdoor Air Unit", "CDU": "Coolant Distribution Unit"}.items():
        assert EQUIPMENT.prefixes[prefix] == kind
    for place in ("NDH", "SDH", "CHPA"):
        assert place not in EQUIPMENT.prefixes


def test_a_thru_range_takes_the_long_ends_location():
    expected = ["ZUL07_04_TWAS01", "ZUL07_04_TWAS02", "ZUL07_04_TWAS03"]
    assert find_tags("ZUL07_04_TWAS01 THRU TWAS03", EQUIPMENT) == expected
    assert expand_tags("ZUL07_04_TWAS01 THRU TWAS03", EQUIPMENT) == expected
    assert expand_tags("ZUL07_04_TWAS01 THRU ZUL07_04_TWAS03", EQUIPMENT) == expected
    assert expand_tags("ZUL07_04_TWAS01 THRU 03", EQUIPMENT) == expected


@pytest.mark.parametrize("text", ["SS-WVA-6", "400301033-M-ZUL07", "H3T-M-601", "ZUL07_M-601.PDF",
                                  "20260101-ZUL07-TFO-M-IFR", "MODEL 24VAV10", "ZUL07_02"])
def test_look_alikes_are_not_underscore_tags(text):
    assert [t for t in find_tags(f"SEE {text} HERE", EQUIPMENT) if "_" in t] == []
    entries = index_tags([PageRecord("m.pdf", 1, "text", f"MODEL {text}", 0)], {}, EQUIPMENT)
    assert [e.tag for e in entries if "_" in e.tag or e.tag == "SS-WVA-6"] == []


def test_a_model_number_is_not_a_unit():
    assert find_tags("UNIT MODEL SS-WVA-6, 480V", EQUIPMENT) == []


def test_a_tag_with_no_dash_counts_only_in_a_series():
    assert find_tags("PROVIDE CDU020 PER DETAIL", EQUIPMENT) == []
    assert find_tags("VAV07 SERVES THE LAB", EQUIPMENT) == []
    assert find_tags("VAV07 VAV08 VAV09", EQUIPMENT) == ["VAV-07", "VAV-08", "VAV-09"]
    assert find_tags("CDU020 AND VAV-07", EQUIPMENT) == ["VAV-07"]


def test_a_tag_with_no_dash_counts_in_a_schedules_tag_column():
    schedule = schedule_from_cells("COOLANT DISTRIBUTION UNIT SCHEDULE", ["MARK", "SERVES", "MODEL"],
                                   [["CDU020", "HALL A", "XR-500"]], [], WHERE)
    assert [r.tag for r in schedule.rows] == ["CDU-020"]


def test_an_underscore_schedule_reads_its_rows():
    schedule = schedule_from_cells("FAN COIL UNIT SCHEDULE", ["TAG", "AREA SERVED", "MODEL"],
                                   [["ZUL07_02_FCU01", "ROOM 1", "SS-WVA-6"],
                                    ["ZUL07_02_FCU02", "ROOM 2", "SS-WVA-6"],
                                    ["ZUL07_02_NDH_CRAH01", "HALL", "CR-9"]], [], WHERE)
    assert [r.tag for r in schedule.rows] == ["ZUL07_02_FCU01", "ZUL07_02_FCU02", "ZUL07_02_NDH_CRAH01"]
    assert not schedule.type_only


def test_a_row_listing_several_tags_counts_those_tags():
    schedule = schedule_from_cells("AIR SEPARATOR SCHEDULE", ["TAG", "QTY", "MODEL"],
                                   [["ZUL07_04_TWAS01 THRU TWAS03", "3", "AS-9"],
                                    ["ZUL07_04_FCU01 ZUL07_04_FCU02 ZUL07_04_FCU03 ZUL07_04_FCU04 ZUL07_04_FCU05",
                                     "5", "F-1"]], [], WHERE)
    tags = [r.tag for r in schedule.rows]
    assert tags[:3] == ["ZUL07_04_TWAS01", "ZUL07_04_TWAS02", "ZUL07_04_TWAS03"] and len(tags) == 8
    items, totals, _ = build_inventory(catalogue_with([]), [schedule])
    got = {t.prefix: t.scheduled for t in totals}
    assert got == {"TWAS": 3, "FCU": 5}


def test_a_quantity_column_counts_a_row():
    schedule = schedule_from_cells("COOLANT DISTRIBUTION UNIT SCHEDULE", ["MARK", "QUANTITY", "SERVES"],
                                   [["CDU020", "4", "HALL A"]], [], WHERE)
    items, totals, _ = build_inventory(catalogue_with([]), [schedule])
    [cdu] = [t for t in totals if t.prefix == "CDU"]
    assert cdu.scheduled == 4 and cdu.kind == "Coolant Distribution Unit"


def test_underscore_tags_are_compacted():
    tags = ["ZUL07_04_FCU01", "ZUL07_04_FCU02", "ZUL07_04_FCU03", "ZUL07_04_FCU04"]
    assert tag_list(tags) == "ZUL07_04_FCU01 thru 04"
    assert tag_list(tags + ["ZUL07_04_FCU06", "ZUL07_05_FCU01"]) == "ZUL07_04_FCU01 thru 04, 06, ZUL07_05_FCU01"
    assert compact_tags(tags) == "ZUL07_04_FCU01 thru ZUL07_04_FCU04"


def test_a_tag_named_in_a_series_row_is_one_unit_even_when_another_schedule_gives_its_row_a_quantity():
    """A connection schedule groups ZUL07_01_CDU01 with a QUANTITY 3 (the units on its feeder); the unit
    schedule names it in the row "CDU01 THRU CDU03" (QUANTITY 3). It is one unit."""
    feeders = schedule_from_cells("COOLANT DISTRIBUTION UNIT SCHEDULE", ["MARK", "QUANTITY", "SERVES"],
                                  [["ZUL07_01_CDU01", "3", "HALL 1"]], [], ("Elec.pdf", 3, "E-601"))
    units = schedule_from_cells("COOLANT DISTRIBUTION UNIT SCHEDULE", ["MARK", "QUANTITY", "SERVES"],
                                [["ZUL07_01_CDU01 THRU CDU03", "3", "HALL 1"]], [], WHERE)
    items, totals, _ = build_inventory(catalogue_with([]), [feeders, units])
    [cdu] = [t for t in totals if t.prefix == "CDU"]
    assert cdu.scheduled == 3


def test_zero_padded_tags_run_on_past_nine():
    tags = [f"ZUL07_01_CDU{n:02d}" for n in range(1, 13)]
    assert compact_tags(tags) == "ZUL07_01_CDU01 thru ZUL07_01_CDU12"
    assert compact_tags(["VAV-8", "VAV-9", "VAV-10"]) == "VAV-8 thru VAV-10"


@pytest.mark.parametrize("cell", ["ZUL07_A1_MMRA_CRAC01 CRAC02", "ZUL07_A1_MMRA_CRAC01, CRAC02",
                                  "ZUL07_A1_MMRA_CRAC01 & 02", "ZUL07_A1_MMRA_CRAC01\nCRAC02"])
def test_a_short_tag_listed_after_a_long_one_takes_its_location(cell):
    assert expand_tags(cell, EQUIPMENT) == ["ZUL07_A1_MMRA_CRAC01", "ZUL07_A1_MMRA_CRAC02"]


def test_a_different_unit_after_a_long_tag_keeps_its_own_name():
    assert find_tags("ZUL07_01_FCU01 AND VAV-02", EQUIPMENT) == ["ZUL07_01_FCU01", "VAV-02"]
