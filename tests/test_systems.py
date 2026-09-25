"""Systems and their bundles: the inventory grouped into systems, each with its evidence in one place."""
import json
from types import SimpleNamespace

from estimator.catalogue.register import PageRecord
from estimator.catalogue.sheet_types import Sheet
from estimator.catalogue.tags import TagEntry
from estimator.reading.devices import DeviceCount
from estimator.reading.inventory import InventoryItem
from estimator.reading.keynotes import Note
from estimator.reading.schedules import Schedule, ScheduleRow
from estimator.reading.sequences import POINTS, SEQUENCE, Backbone
from estimator.writing.systems import GROUPS_FILE, build_bundles, unbundled_flags
from estimator.writing.templates import load_templates, template_for

SPEC = "Specs/Specs.pdf"
DWG = "Drawings/Mech.pdf"


def _sheet(number, page, title, types=("Plans",), discipline="Mechanical"):
    return Sheet(DWG, page, number, title, discipline, tuple(types))


def _schedule(sheet, page, title, tags, headers=("TAG", "GPM"), notes=(), controls_by=(), existing=()):
    rows = tuple(ScheduleRow(tag, {"TAG": tag, "GPM": "2.0"}, None, None, tag in existing) for tag in tags)
    return Schedule(DWG, page, sheet, title, tuple(headers), rows, False, tuple(notes), tuple(controls_by))


def _item(tag, category="CONFIRMED", schedule="M-601 SCHEDULE", seen=("M-101",)):
    kinds = {"VAV": "Variable Air Volume Box", "CH": "Chiller", "CHWP": "Chilled Water Pump", "ET": "Expansion Tank",
             "KEF": "Kitchen Exhaust Fan", "MAU": "Makeup Air Unit", "EF": "Exhaust Fan", "AC": "Air Conditioning Unit"}
    quantity = {"CONFIRMED": 1, "MISSING": 1, "DISCREPANCY": 1, "EXISTING": 0}.get(category)
    return InventoryItem(tag, kinds[tag.split("-", 1)[0]], category, quantity, schedule, tuple(seen), "", "")


def _tag(tag, on_schedules=("M-601",), elsewhere=("M-101",)):
    return TagEntry(tag, "", tuple(on_schedules), tuple(elsewhere), len(on_schedules) + len(elsewhere))


def _job(items, schedules=(), sheets=(), tags=(), pages=(), backbone=(), notes=(), devices=()):
    catalogue = SimpleNamespace(pages=tuple(pages), sheets=tuple(sheets), tags=tuple(tags), sections=())
    reading = SimpleNamespace(schedules=tuple(schedules), inventory=tuple(items), notes=tuple(notes),
                              backbone=tuple(backbone), devices=tuple(devices), flags=())
    return catalogue, reading


def _by_key(bundles):
    return {b.key: b for b in bundles}


# --- the groupings file --------------------------------------------------------------------------

def test_every_group_names_a_master_template_system():
    groups = json.loads(GROUPS_FILE.read_text(encoding="utf-8"))["groups"]
    templates = load_templates()
    for group in groups:
        template = template_for("", group["name"], templates)
        assert template is not None and template.group, group["name"]


# --- grouping ------------------------------------------------------------------------------------

def test_a_chilled_water_group_forms_from_a_shared_schedule_sheet():
    tags = ["CH-1", "CH-2", "CHWP-1", "CHWP-2", "CHWP-3", "ET-1"]
    items = [_item(t) for t in tags]
    schedules = [_schedule("M-601", 5, "CHILLER SCHEDULE", ["CH-1", "CH-2"]),
                 _schedule("M-601", 5, "PUMP SCHEDULE", ["CHWP-1", "CHWP-2", "CHWP-3"]),
                 _schedule("M-602", 6, "EXPANSION TANK SCHEDULE", ["ET-1"])]
    entries = [_tag(t, on_schedules=("M-602",) if t == "ET-1" else ("M-601",)) for t in tags]
    bundles = _by_key(build_bundles(*_job(items, schedules, tags=entries)))

    plant = bundles["Chilled Water System"]
    assert plant.name == "Chilled Water System"
    assert [(f.prefix, f.quantity) for f in plant.families] == [("CH", 2), ("CHWP", 3)]
    assert {r.tag for r in plant.schedule_rows} == {"CH-1", "CH-2", "CHWP-1", "CHWP-2", "CHWP-3"}
    assert all(r.sheet == "M-601" for r in plant.schedule_rows)
    assert "M-601" in plant.sheets

    tank = bundles["ET"]
    assert [f.tags for f in tank.families] == [("ET-1",)]
    assert "ET-1 could belong to Chilled Water System — check" in tank.flags


def test_a_family_joins_through_another_joiner_that_is_linked():
    items = [_item(t) for t in ("CH-1", "CHWP-1", "ET-1")]
    schedules = [_schedule("M-601", 5, "CHILLER SCHEDULE", ["CH-1"]),
                 _schedule("M-601", 5, "PUMP SCHEDULE", ["CHWP-1"]),
                 _schedule("M-603", 7, "TANKS", ["ET-1"])]
    sheets = [_sheet("M-501", 9, "CHILLED WATER FLOW DIAGRAM", ("Water riser", "Diagrams"))]
    entries = [_tag("CH-1"), _tag("CHWP-1", elsewhere=("M-501",)), _tag("ET-1", ("M-603",), ("M-501",))]
    bundles = _by_key(build_bundles(*_job(items, schedules, sheets, entries)))
    assert [f.prefix for f in bundles["Chilled Water System"].families] == ["CH", "CHWP", "ET"]
    assert "ET" not in bundles


def test_an_electrical_riser_does_not_join_a_family_to_a_group():
    items = [_item("KEF-1"), _item("MAU-1")]
    schedules = [_schedule("M-601", 5, "KITCHEN FAN", ["KEF-1"]), _schedule("M-602", 6, "MAU", ["MAU-1"])]
    sheets = [_sheet("E-300", 9, "POWER RISER DIAGRAM", ("Diagrams",), discipline="Electrical")]
    entries = [_tag("KEF-1", ("M-601",), ("E-300",)), _tag("MAU-1", ("M-602",), ("E-300",))]
    bundles = _by_key(build_bundles(*_job(items, schedules, sheets, entries)))
    assert set(bundles) == {"Kitchen Exhaust", "MAU"}


def test_an_mau_for_a_garage_stands_alone():
    items = [_item("KEF-1"), _item("MAU-1")]
    schedules = [_schedule("M-601", 5, "KITCHEN EXHAUST FAN SCHEDULE", ["KEF-1"]),
                 _schedule("M-602", 6, "MAKEUP AIR UNIT SCHEDULE", ["MAU-1"])]
    entries = [_tag("KEF-1", ("M-601",)), _tag("MAU-1", ("M-602",))]
    bundles = _by_key(build_bundles(*_job(items, schedules, tags=entries)))
    assert [f.prefix for f in bundles["Kitchen Exhaust"].families] == ["KEF"]
    alone = bundles["MAU"]
    assert alone.name == "Makeup Air Unit"
    assert "MAU-1 could belong to Kitchen Exhaust — check" in alone.flags


def test_an_mau_in_the_kitchen_sequence_joins_kitchen_exhaust():
    items = [_item("KEF-1"), _item("MAU-1")]
    schedules = [_schedule("M-601", 5, "KITCHEN EXHAUST FAN SCHEDULE", ["KEF-1"]),
                 _schedule("M-602", 6, "MAKEUP AIR UNIT SCHEDULE", ["MAU-1"])]
    text = ("SECTION 23 09 93\n\nA. Kitchen hood: when the hood switch is on, start KEF-1.\n\n"
            "B. Makeup air unit MAU-1 shall run whenever KEF-1 runs.\n\nC. Toilet exhaust runs on schedule.")
    pages = [PageRecord(SPEC, 44, "text", text, 0)]
    backbone = [Backbone(SEQUENCE, "23 09 93 SEQUENCE OF OPERATIONS (Specs.pdf, pages 44–44)", SPEC, 44, 44,
                         "spec section")]
    entries = [_tag("KEF-1", ("M-601",)), _tag("MAU-1", ("M-602",))]
    bundles = _by_key(build_bundles(*_job(items, schedules, tags=entries, pages=pages, backbone=backbone)))
    assert "MAU" not in bundles
    kitchen = bundles["Kitchen Exhaust"]
    assert [f.prefix for f in kitchen.families] == ["KEF", "MAU"]
    assert kitchen.passages and "MAU-1 shall run" in kitchen.passages[0].text


def test_a_joiner_with_no_anchor_on_the_job_stands_alone_without_a_flag():
    items = [_item("MAU-1")]
    bundles = _by_key(build_bundles(*_job(items, [_schedule("M-602", 6, "MAU", ["MAU-1"])], tags=[_tag("MAU-1")])))
    assert list(bundles) == ["MAU"]
    assert not any("could belong" in f for f in bundles["MAU"].flags)


# --- quantities and categories ---------------------------------------------------------------------

def test_extra_and_orphaned_tags_are_kept_out_of_the_quantity():
    items = [_item("VAV-1"), _item("VAV-2"), _item("VAV-3"), _item("VAV-9", "EXTRA", None, ("M-101", "M-102")),
             _item("VAV-10", "EXTRA", None), _item("VAV-12", "ORPHANED", None)]
    schedules = [_schedule("M-601", 5, "VAV BOX SCHEDULE", ["VAV-1", "VAV-2", "VAV-3"])]
    bundles = _by_key(build_bundles(*_job(items, schedules)))
    vav = bundles["VAV"]
    (family,) = vav.families
    assert family.quantity == 3
    assert family.tags == ("VAV-1", "VAV-2", "VAV-3")
    assert family.categories == {"CONFIRMED": 3, "EXTRA": 2, "ORPHANED": 1}
    assert "2 more VAV tags on the drawings but not on the schedule (EXTRA) — not priced until confirmed" in vav.flags
    assert any(f.startswith("1 more VAV tag ") and "(ORPHANED)" in f for f in vav.flags)


def test_a_family_with_only_extra_tags_makes_no_bundle_but_is_reported():
    items = [_item("VAV-1"), _item("AC-1", "EXTRA", None), _item("AC-2", "ORPHANED", None)]
    catalogue, reading = _job(items, [_schedule("M-601", 5, "VAV BOX SCHEDULE", ["VAV-1"])])
    bundles = build_bundles(catalogue, reading)
    assert [b.key for b in bundles] == ["VAV"]
    (flag,) = unbundled_flags(reading)
    assert "AC-1" in flag and "AC-2" in flag and "not priced until confirmed" in flag


def test_type_only_schedules_make_no_bundle_and_are_flagged():
    type_only = InventoryItem("VAV-A, VAV-B", "VAV TYPE SCHEDULE", "TYPE ONLY", None, "M-601 VAV TYPE SCHEDULE",
                              (), "", "confirm")
    catalogue, reading = _job([_item("VAV-1"), type_only], [_schedule("M-601", 5, "VAV BOX SCHEDULE", ["VAV-1"])])
    bundles = build_bundles(catalogue, reading)
    assert [(b.key, b.families[0].tags) for b in bundles] == [("VAV", ("VAV-1",))]
    assert bundles[0].families[0].categories == {"CONFIRMED": 1}
    assert unbundled_flags(reading) == ["Type-only schedule VAV TYPE SCHEDULE — count from the plans"]


def test_pending_tags_make_a_bundle_with_no_quantity():
    items = [_item("VAV-1", "PENDING", None), _item("VAV-2", "PENDING", None)]
    (bundle,) = build_bundles(*_job(items))
    assert bundle.families[0].quantity is None
    assert bundle.families[0].tags == ("VAV-1", "VAV-2")
    assert any("(PENDING)" in f for f in bundle.flags)


def test_existing_units_form_their_own_bundle():
    items = [_item("VAV-1"), _item("VAV-2"), _item("VAV-3", "EXISTING")]
    schedules = [_schedule("M-601", 5, "VAV BOX SCHEDULE", ["VAV-1", "VAV-2", "VAV-3"], existing=("VAV-3",))]
    bundles = _by_key(build_bundles(*_job(items, schedules)))
    assert bundles["VAV"].families[0].quantity == 2
    assert {r.tag for r in bundles["VAV"].schedule_rows} == {"VAV-1", "VAV-2"}
    existing = bundles["Existing VAV"]
    assert existing.name == "Existing Variable Air Volume Box"
    assert existing.families[0].tags == ("VAV-3",)
    assert existing.families[0].categories == {"EXISTING": 1}
    assert [r.tag for r in existing.schedule_rows] == ["VAV-3"]
    assert list(bundles) == ["VAV", "Existing VAV"]


# --- evidence ------------------------------------------------------------------------------------

def _sequence_job():
    long_tail = "Modulate the damper to maintain the airflow setpoint. " * 80
    seq_44 = ("SECTION 23 09 93 SEQUENCE OF OPERATIONS\n\n"
              "3.01 GENERAL\nAll controls by the BMS.\n\n"
              "3.02 VARIABLE AIR VOLUME BOXES\nEach variable air volume box shall be controlled as follows.\n\n"
              "A. Occupied mode: VAV-1 thru VAV-3 maintain the space temperature and CO2 setpoints.\n"
              "B. Reheat: open the hot water valve on a call for heating.\n\n"
              "C. Unoccupied mode: the boxes close.\n\n"
              "3.03 EXHAUST FANS\nEF-1 runs in occupied mode.\n\n"
              "3.04 TERMINAL UNITS\nThe VAV boxes report the airflow. " + long_tail)
    points_60 = "POINTS LIST\n\nVAV-1 space temperature AI\n\nVAV-1 damper AO"
    pages = [PageRecord(SPEC, 44, "text", seq_44, 0), PageRecord(SPEC, 60, "text", points_60, 0)]
    backbone = [Backbone(SEQUENCE, "23 09 93 SEQUENCE OF OPERATIONS (Specs.pdf, page 44)", SPEC, 44, 44,
                         "spec section"),
                Backbone(POINTS, "23 09 94 POINTS LIST (Specs.pdf, page 60)", SPEC, 60, 60, "spec section"),
                Backbone(SEQUENCE, "23 09 93 SEQUENCE OF OPERATIONS (Copy.pdf, page 44)", "Copy.pdf", 44, 44,
                         "spec section", duplicate_of="23 09 93 SEQUENCE OF OPERATIONS (Specs.pdf, page 44)")]
    items = [_item(t) for t in ("VAV-1", "VAV-2", "VAV-3", "EF-1")]
    schedules = [_schedule("M-601", 5, "VAV BOX SCHEDULE", ["VAV-1", "VAV-2", "VAV-3"],
                           notes=("1. PROVIDE 24V TRANSFORMER.",), controls_by=("DDC BY TCC.",)),
                 _schedule("M-602", 6, "FAN SCHEDULE", ["EF-1"])]
    return _job(items, schedules, pages=pages, backbone=backbone)


def test_passages_prefer_the_sequence_and_exact_tags_and_keep_the_next_paragraph():
    bundles = _by_key(build_bundles(*_sequence_job()))
    passages = bundles["VAV"].passages
    first = passages[0]
    assert first.where == "23 09 93 SEQUENCE OF OPERATIONS, page 44"
    assert (first.document, first.page) == (SPEC, 44)
    assert first.text.startswith("A. Occupied mode: VAV-1 thru VAV-3")
    assert "B. Reheat: open the hot water valve" in first.text        # the paragraph after the hit
    assert "Unoccupied" not in first.text
    texts = [p.text for p in passages]
    assert any(t.startswith("3.02 VARIABLE AIR VOLUME BOXES") for t in texts)   # the kind name
    assert any("The VAV boxes report the airflow" in t for t in texts)          # the prefix
    assert not any("All controls by the BMS" in t for t in texts)
    assert not any("EF-1 runs" in t for t in texts)
    kinds = [p.where for p in passages]
    assert kinds.index("23 09 94 POINTS LIST, page 60") > max(
        i for i, w in enumerate(kinds) if w.startswith("23 09 93"))           # the sequence first
    assert all(p.document != "Copy.pdf" for p in passages)                     # a duplicate copy isn't read twice
    assert all(len(p.text) <= 3000 for p in passages)
    assert len(passages) <= 8


def test_at_most_eight_passages():
    text = "\n\n".join(f"{n}. VAV-1 step {n}." for n in range(1, 30))
    pages = [PageRecord(SPEC, 44, "text", text, 0)]
    backbone = [Backbone(SEQUENCE, "23 09 93 SEQUENCE OF OPERATIONS (Specs.pdf, page 44)", SPEC, 44, 44,
                         "spec section")]
    bundles = _by_key(build_bundles(*_job([_item("VAV-1")], pages=pages, backbone=backbone)))
    assert len(bundles["VAV"].passages) == 8


def test_another_tag_of_a_one_letter_prefix_is_not_a_passage():
    items = [InventoryItem("B-1", "Boiler", "CONFIRMED", 1, "M-601 BOILERS", (), "", "")]
    text = "A. Sheet B-2 shows the riser.\n\nB. Boiler B-1 runs on a call for heat."
    pages = [PageRecord(SPEC, 44, "text", text, 0)]
    backbone = [Backbone(SEQUENCE, "23 09 93 SEQUENCE OF OPERATIONS (Specs.pdf, page 44)", SPEC, 44, 44,
                         "spec section")]
    (bundle,) = build_bundles(*_job(items, pages=pages, backbone=backbone))
    assert [p.text for p in bundle.passages] == ["B. Boiler B-1 runs on a call for heat."]


def test_schedule_notes_controls_by_notes_and_devices_are_gathered():
    catalogue, reading = _sequence_job()
    notes = [Note("M-101", DWG, 1, "KEY NOTES", "1", "VAV-2 ABOVE CEILING, PROVIDE ACCESS.", True, ""),
             Note("M-101", DWG, 1, "KEY NOTES", "2", "ALL VARIABLE AIR VOLUME BOXES TO HAVE A SENSOR.", True, ""),
             Note("M-101", DWG, 1, "KEY NOTES", "3", "EXHAUST DUCT UP TO ROOF.", False, "")]
    devices = [DeviceCount("M-101", DWG, 1, "Temperature sensor", "T", 3, 1, 3, True),
               DeviceCount("M-900", DWG, 30, "Temperature sensor", "T", 9, 1, 9, True)]
    catalogue.tags = (_tag("VAV-1"), _tag("VAV-2"), _tag("VAV-3"), _tag("EF-1", ("M-602",), ("M-102",)))
    reading.notes, reading.devices = tuple(notes), tuple(devices)
    bundles = _by_key(build_bundles(catalogue, reading))
    vav = bundles["VAV"]
    assert vav.schedule_notes == ("1. PROVIDE 24V TRANSFORMER.",)
    assert vav.controls_by == ("DDC BY TCC.",)
    assert [n.number for n in vav.notes] == ["1", "2"]
    assert [d.sheet for d in vav.devices] == ["M-101"]
    assert vav.sheets == ("M-601", "M-101")
    assert bundles["EF"].schedule_notes == () and bundles["EF"].devices == ()
    row = vav.schedule_rows[0]
    assert (row.title, row.sheet, row.cells["GPM"]) == ("VAV BOX SCHEDULE", "M-601", "2.0")


def test_bundles_come_in_the_proposal_order():
    items = [_item("EF-1"), _item("VAV-1"), _item("CH-1")]
    schedules = [_schedule("M-601", 5, "FANS", ["EF-1"]), _schedule("M-601", 5, "VAV", ["VAV-1"]),
                 _schedule("M-602", 6, "CHILLERS", ["CH-1"])]
    keys = [b.key for b in build_bundles(*_job(items, schedules))]
    assert keys == ["VAV", "EF", "Chilled Water System"]
