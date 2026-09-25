import pytest

from estimator.catalogue.register import PageRecord
from estimator.catalogue.sheet_types import Sheet
from estimator.catalogue.tags import Equipment, TagEntry, find_tags, index_tags, unlisted_prefixes

EQUIPMENT = Equipment.load()


@pytest.mark.parametrize("written", ["AHU-1", "AHU 1", "AHU#1", "AHU–1", "AHU — 1", "AHU No. 1", "AHU1",
                                     "Air Handling Unit No. 1", "AIR HANDLING UNIT #1"])
def test_every_spelling_is_one_tag(written):
    assert find_tags(f"serves {written}, on the roof", EQUIPMENT) == ["AHU-1"]


def test_ahu_1_is_never_ahu_10():
    assert find_tags("AHU-1 and AHU-10 and AHU-1A", EQUIPMENT) == ["AHU-1", "AHU-10", "AHU-1A"]


@pytest.mark.parametrize("text, tags", [("VAV-21-01", ["VAV-21-01"]), ("CHLR-1CY40-A110", ["CHLR-1CY40-A110"]),
                                        ("CBH-A", ["CBH-A"]), ("ECUH-5", ["ECUH-5"]), ("EF-2 & 3", ["EF-2"])])
def test_tag_shapes(text, tags):
    assert find_tags(text, EQUIPMENT) == tags


@pytest.mark.parametrize("text, tags", [("AC-EMR-1", ["AC-EMR-1"]), ("ACCU-LOBBY-2", ["ACCU-LOBBY-2"]),
                                        ("AC-LAUNDRY-1", ["AC-LAUNDRY-1"]), ("AC-ATS-1.1", ["AC-ATS-1.1"]),
                                        ("AC-ATS-1.2 AND AC-ATS-1.1", ["AC-ATS-1.2", "AC-ATS-1.1"]),
                                        ("VAV-EAST-WING-3", ["VAV-EAST-WING-3"]), ("AC-IT-1", ["AC-IT-1"])])
def test_a_tag_can_have_word_segments_before_its_number(text, tags):
    assert find_tags(f"SERVES {text} IN THE ROOM", EQUIPMENT) == tags


@pytest.mark.parametrize("text, tags", [("AC-3.0", ["AC-3.0"]), ("HRU-4.0", ["HRU-4.0"]), ("EF-1.", ["EF-1"]),
                                        ("RTU-2.5X", ["RTU-2"])])
def test_a_decimal_type_suffix_stays_on_the_tag(text, tags):
    assert find_tags(f"{text} ", EQUIPMENT) == tags


@pytest.mark.parametrize("text", ["SEE M-101", "FLOOR 14", "SUITE 310", "SECTION 230900", "R454B", "ACME CORP",
                                  "EFFICIENCY 2", "ahu-1 in lower case", "AC-POWER", "AC-POWER TO PANEL",
                                  "AS-BUILT DRAWINGS", "AC-ELEVATOR-MACHINE-ROOM-1", "AC-EMERGENCYPOWER-1"])
def test_look_alikes_are_not_tags(text):
    assert find_tags(text, EQUIPMENT) == []


def test_a_sheet_number_with_a_decimal_is_not_a_tag_either_way():
    pages = [_record("plumb.pdf", 1, "SEE P-101 AND P-101.00 FOR PUMP P-1")]
    sheets = {("plumb.pdf", 1): Sheet("plumb.pdf", 1, "P-101.00", "PUMP SCHEDULE", "Plumbing", ("Schedules",))}
    assert [e.tag for e in index_tags(pages, sheets, EQUIPMENT)] == ["P-1"]


def test_the_jobs_own_sheet_numbers_are_not_tags():
    assert find_tags("SEE P-101 FOR PUMP P-1", EQUIPMENT, exclude=frozenset({"P-101"})) == ["P-1"]


def _record(document, page, text):
    return PageRecord(document, page, "text", text, 0)


def test_the_index_says_where_each_tag_appears():
    pages = [_record("mech.pdf", 1, "AIR HANDLING UNIT SCHEDULE\nAHU-1 AHU-2\nPUMP SCHEDULE P-1"),
             _record("mech.pdf", 2, "AHU-1 ON ROOF. AHU 1 CURB. EF-3. P-1 AND P-7. SEE P-101."),
             _record("spec.pdf", 4, "AHU-1 shall have a BACnet interface.")]
    sheets = {("mech.pdf", 1): Sheet("mech.pdf", 1, "M-601", "SCHEDULES", "Mechanical", ("Schedules",)),
              ("mech.pdf", 2): Sheet("mech.pdf", 2, "M-101", "FIRST FLOOR PLAN", "Mechanical", ("Plans",)),
              ("plumb.pdf", 1): Sheet("plumb.pdf", 1, "P-101", "PLUMBING PLAN", "Plumbing", ("Plans",))}
    assert index_tags(pages, sheets, EQUIPMENT) == [
        TagEntry("AHU-1", "Air Handling Unit", ("M-601",), ("M-101", "spec.pdf p.4"), 4),
        TagEntry("AHU-2", "Air Handling Unit", ("M-601",), (), 1),
        TagEntry("EF-3", "Exhaust Fan", (), ("M-101",), 1),
        TagEntry("P-1", "Pump", ("M-601",), ("M-101",), 2)]


def test_a_sheet_number_written_without_a_dash_is_never_read_as_a_tag():
    pages = [_record("plumb.pdf", 1, "SEE P101.00 AND PUMP P-1")]
    sheets = {("plumb.pdf", 1): Sheet("plumb.pdf", 1, "P101.00", "PUMP SCHEDULE", "Plumbing", ("Schedules",))}
    tags = [e.tag for e in index_tags(pages, sheets, EQUIPMENT)]
    assert tags == ["P-1"]


def test_a_sheet_numbered_ef101_is_not_counted_as_the_tag_ef_101():
    pages = [_record("mech.pdf", 1, "EF101 SERVES ROOM 204. EF-2 IS IN THE CORRIDOR.")]
    sheets = {("mech.pdf", 1): Sheet("mech.pdf", 1, "EF101", "MECHANICAL PLAN", "Mechanical", ("Plans",))}
    tags = [e.tag for e in index_tags(pages, sheets, EQUIPMENT)]
    assert tags == ["EF-2"]


def test_tags_sort_in_number_order():
    pages = [_record("mech.pdf", 1, "VAV-10 VAV-2 VAV-1 AHU-3")]
    tags = [e.tag for e in index_tags(pages, {}, EQUIPMENT)]
    assert tags == ["AHU-3", "VAV-1", "VAV-2", "VAV-10"]


def test_codes_with_an_unlisted_prefix_are_counted_for_the_learn_check():
    counts = unlisted_prefixes(["FFCH-548 FFCH-549 AHU-1 MUH-05", "XYZ-1"], EQUIPMENT)
    assert counts["FFCH"] == 2 and counts["MUH"] == 1 and counts["XYZ"] == 1 and "AHU" not in counts
