"""Write each system from the Master Template: lines, quantities, tech hours, confidence and review."""
import datetime as dt
import re
from pathlib import Path
from types import SimpleNamespace

from estimator.catalogue.overview import SpecOverview
from estimator.price_sheet.write import check_fit
from estimator.reading.devices import DeviceCount
from estimator.reading.inventory import InventoryItem
from estimator.reading.keynotes import Note
from estimator.reading.schedules import Schedule, ScheduleRow
from estimator.scope import Job
from estimator.writing.judge import Choice, Judgement
from estimator.writing.systems import BundleRow, Family, Passage, SystemBundle
from estimator.writing.templates import integration_trio, load_templates
from estimator.writing.write import build_job, tag_list, write_systems

TEMPLATES = load_templates()
DWG = "Drawings/Mech.pdf"
CATEGORY_WORDS = ("CONFIRMED", "DISCREPANCY", "ADDED", "EXTRA", "MISSING", "ORPHANED", "CONFLICT", "EXISTING",
                  "ASSUMPTION", "PENDING")


def _catalogue(overview=None):
    return SimpleNamespace(overview=overview or SpecOverview(), pages=(), sheets=(), sections=(), tags=())


def _rows(tags, headers, cells, title="VAV BOX SCHEDULE", sheet="M-601"):
    return tuple(BundleRow(t, title, sheet, DWG, 5, tuple(headers), {"TAG": t, **cells}, None, None) for t in tags)


def _bundle(prefix, kind, tags, rows=(), passages=(), controls_by=(), notes=(), devices=(), flags=(),
            quantity="count", schedule_notes=()):
    n = len(tags) if quantity == "count" else quantity
    family = Family(prefix, kind, tuple(tags), n, {"CONFIRMED": len(tags)})
    return SystemBundle(key=prefix, name=kind, families=(family,), schedule_rows=tuple(rows),
                        schedule_notes=tuple(schedule_notes), controls_by=tuple(controls_by), notes=tuple(notes),
                        passages=tuple(passages), devices=tuple(devices), sheets=("M-601", "M-101"),
                        flags=tuple(flags))


SEQUENCE = Passage("23 09 93 SEQUENCE OF OPERATIONS, page 44", "Specs.pdf", 44,
                   "VAV boxes: each VAV box shall maintain the space temperature and CO2 setpoints.")
VAV_TAGS = ["VAV-1", "VAV-2", "VAV-3"]


def _vav(**kw):
    rows = kw.pop("rows", _rows(VAV_TAGS, ("TAG", "MAX CFM", "HW GPM"), {"MAX CFM": "600", "HW GPM": "1.5"}))
    return _bundle("VAV", "Variable Air Volume Box", VAV_TAGS, rows=rows, passages=kw.pop("passages", (SEQUENCE,)),
                   **kw)


def _write(bundle, judge=None, catalogue=None, reading=None):
    [system] = write_systems(catalogue or _catalogue(), reading or SimpleNamespace(), [bundle], TEMPLATES, judge)
    return system


def _line(system, text):
    return next(line for line in system.lines if line.text == text)


def _printed(system):
    return [item.text for block in system.blocks for item in block.items]


# --- the VAV template ---------------------------------------------------------------------------

def test_a_hot_water_reheat_vav_with_a_co2_sequence():
    system = _write(_vav())
    assert system.printed
    [block] = system.blocks
    assert block.header == "Qty (3) Variable Air Volume Box VAV-1 thru 3"
    assert _printed(system)[:5] == [
        "Furnish DDC Controller to the Factory for Installation",
        "Furnish and Install Space Temperature / CO2 Sensor",
        "Furnish and Install Discharge Air Temperature Sensor",
        "Furnish and Wire Hot Water Control Valve and Actuator",
        "Furnish and Install VAV Transformer",
    ]
    assert all(item.quantity == 3 for item in block.items)
    assert block.tech_hours == 12          # 4 h per hot-water reheat VAV

    sensor = _line(system, "Furnish and Install Space Temperature / CO2 Sensor")
    assert sensor.category == "CONFIRMED" and sensor.client
    assert "23 09 93 SEQUENCE OF OPERATIONS, page 44" in sensor.evidence
    assert "CO2" in sensor.evidence
    assert sensor.source.startswith("rule: space_co2")

    valve = _line(system, "Furnish and Wire Hot Water Control Valve and Actuator")
    assert valve.category == "CONFIRMED" and valve.confidence == 0.8
    assert "M-601" in valve.evidence and "HW GPM" in valve.evidence

    ddc = _line(system, "Furnish DDC Controller to the Factory for Installation")
    assert (ddc.category, ddc.confidence, ddc.source) == ("ASSUMPTION", 0.5, "default")
    assert system.confidence == 0.5
    assert "Furnish Fan Enable" not in _printed(system)          # not fan powered: the schedule says nothing of it


def test_a_cooling_only_vav_is_three_hours_and_has_no_valve():
    rows = _rows(VAV_TAGS, ("TAG", "MAX CFM"), {"MAX CFM": "600"})
    system = _write(_vav(rows=rows))
    assert "Furnish and Wire Hot Water Control Valve and Actuator" not in _printed(system)
    assert "Furnish and Install Discharge Air Temperature Sensor" not in _printed(system)
    assert system.blocks[0].tech_hours == 9


def test_a_gpm_column_left_empty_does_not_make_a_reheat_vav():
    rows = _rows(VAV_TAGS, ("TAG", "HW GPM"), {"HW GPM": "-"})
    assert "Furnish and Wire Hot Water Control Valve and Actuator" not in _printed(_write(_vav(rows=rows)))


def test_with_no_sequence_the_sensor_is_the_default_and_the_sequence_only_lines_are_pending():
    system = _write(_vav(passages=()))
    sensor = _line(system, "Furnish and Install Space Temperature Sensor")
    assert sensor.category == "ASSUMPTION" and sensor.client
    # 24 V by the BMS can't be checked with no sequence and no notes: the choice falls to the default.
    assert _line(system, "Furnish and Install VAV Transformer").category == "ASSUMPTION"
    assert not any(line.category == "PENDING" and line.client for line in system.lines)


def test_a_line_that_cannot_be_checked_is_pending_and_not_printed():
    # The AHU's supply static line looks only in the sequence; with no sequence it can't be decided.
    rows = _rows(["AHU-1"], ("TAG", "CFM"), {"CFM": "5000"}, title="AIR HANDLING UNIT SCHEDULE")
    system = _write(_bundle("AHU", "Air Handling Unit", ["AHU-1"], rows=rows))
    line = _line(system, "Furnish and Install Supply Static Pressure Sensor")
    assert (line.category, line.client, line.quantity, line.confidence) == ("PENDING", False, 1, 0.0)
    assert "judgement pending" in line.evidence
    assert "Furnish and Install Supply Static Pressure Sensor" not in _printed(system)
    assert any(item.category == "PENDING" and "Supply Static Pressure Sensor" in item.decide for item in system.review)


def test_the_air_handler_is_two_hours_a_hardware_point():
    rows = _rows(["AHU-1", "AHU-2"], ("TAG", "CFM"), {"CFM": "5000"}, title="AIR HANDLING UNIT SCHEDULE")
    passage = Passage("23 09 93, page 50", "Specs.pdf", 50,
                      "AHU-1 and AHU-2: the supply fan shall run to hold the duct static pressure. "
                      "The mixed air temperature is monitored.")
    system = _write(_bundle("AHU", "Air Handling Unit", ["AHU-1", "AHU-2"], rows=rows, passages=(passage,)))
    printed = _printed(system)
    assert "Furnish and Install Supply Static Pressure Sensor" in printed
    assert "Furnish and Install Mixed Air Temperature Sensor" in printed
    points = [line for line in system.lines if line.client and line.text in printed and "DDC Controller" not in line.text
              and line.text.startswith(("Furnish and Install", "Furnish and Wire", "Furnish "))]
    assert system.blocks[0].tech_hours == 2 * sum(line.quantity for line in points)


# --- factory controls -----------------------------------------------------------------------------

def test_a_packaged_rtu_with_a_factory_control_package_gets_the_trio_and_the_install_and_wire_lines():
    rows = _rows(["RTU-1", "RTU-2"], ("TAG", "CFM"), {"CFM": "4000"}, title="ROOFTOP UNIT SCHEDULE")
    system = _write(_bundle("RTU", "Rooftop Unit", ["RTU-1", "RTU-2"], rows=rows,
                            controls_by=("UNIT SHALL BE PROVIDED WITH A FACTORY CONTROL PACKAGE.",)))
    printed = _printed(system)
    first, second, _ = integration_trio("")
    assert first in printed and second in printed
    assert "Install and wire mfr. Provided sensors shipped loose w/ unit" in printed
    trio = _line(system, first)
    assert trio.category == "CONFIRMED" and "FACTORY CONTROL PACKAGE" in trio.evidence
    assert system.blocks[0].tech_hours is None
    assert any("No tech hours in the Master Template for Packaged ERU / RTU / AHU — enter them" in str(item)
               for item in system.review)


def test_factory_controls_replace_the_ddc_controller_lines():
    system = _write(_vav(controls_by=("VAV CONTROLS BY UNIT MANUFACTURER.",)))
    printed = _printed(system)
    assert "Furnish DDC Controller to the Factory for Installation" not in printed
    first, second, third = integration_trio("Variable Air Volume Box")
    assert printed[:3] == [first, second, third]
    depths = [item.depth for item in system.blocks[0].items[:3]]
    assert depths == [1, 1, 2]


# --- quantities ------------------------------------------------------------------------------------

def test_a_counted_line_takes_the_device_count_on_the_systems_sheets():
    rows = _rows(["SPF-1"], ("TAG", "CFM"), {"CFM": "9000"}, title="FAN SCHEDULE")
    devices = (DeviceCount("M-101", DWG, 3, "Static pressure sensor", "SP", 4, 1, 4, True),)
    system = _write(_bundle("SPF", "Stair Pressurization Fan", ["SPF-1"], rows=rows, devices=devices))
    sensor = _line(system, "Furnish and Install Stairwell Pressure Sensor")
    assert (sensor.quantity, sensor.category, sensor.confidence) == (4, "CONFIRMED", 0.9)


def test_a_counted_line_with_no_count_falls_back_to_one_per_unit_as_an_assumption():
    rows = _rows(["SPF-1", "SPF-2"], ("TAG", "CFM"), {"CFM": "9000"}, title="FAN SCHEDULE")
    system = _write(_bundle("SPF", "Stair Pressurization Fan", ["SPF-1", "SPF-2"], rows=rows))
    sensor = _line(system, "Furnish and Install Stairwell Pressure Sensor")
    assert (sensor.quantity, sensor.category) == (2, "ASSUMPTION")


def test_a_system_whose_units_could_not_be_counted_is_not_printed():
    system = _write(_vav(quantity=None))
    assert not system.printed
    assert all(line.category == "PENDING" and not line.client for line in system.lines)
    assert any("could not be counted" in str(item) for item in system.review)


# --- the AI judge ----------------------------------------------------------------------------------

class FakeJudge:
    available = True
    last_error = None

    def __init__(self, choices, notes=(), dropped=()):
        self.choices, self.notes, self.dropped = choices, notes, dropped
        self.asked = []

    def judge(self, system, evidence, options, rules):
        self.asked.append((system, evidence, options, rules))
        return Judgement(tuple(c for c in self.choices if c.line in options), tuple(self.notes), "fake",
                         tuple(self.dropped))


def test_the_ai_overrides_an_assumption_and_a_disagreement_makes_a_review_line():
    judge = FakeJudge([
        Choice("Furnish DDC Controller to the Factory for Installation", True, None,
               "The sequence names the controller.", "each VAV box shall maintain", 0.9),
        Choice("Furnish and Wire Hot Water Control Valve and Actuator", False, None,
               "The boxes are cooling only.", "maintain the space temperature and CO2 setpoints", 0.9),
        Choice("Furnish and Install VAV Transformer", False, None, "no evidence", "", 0.3),
    ], notes=["**Space sensors mounted at 48 inches", "**VAV boxes maintain the space temperature"],
        dropped=["Furnish a coffee machine"])
    system = _write(_vav(), judge=judge)
    [(name, evidence, options, rules)] = judge.asked
    assert name == "VAV / Fan VAV"
    assert "23 09 93 SEQUENCE OF OPERATIONS, page 44" in evidence and "HW GPM" in evidence
    assert "Furnish Fan Enable" in options and len(options) == len(set(options))
    assert any("GPM" in rule for rule in rules)

    ddc = _line(system, "Furnish DDC Controller to the Factory for Installation")
    assert (ddc.category, ddc.confidence) == ("CONFIRMED", 0.9)
    assert ddc.source.startswith("AI:")

    valve = _line(system, "Furnish and Wire Hot Water Control Valve and Actuator")
    assert valve.category == "CONFIRMED" and valve.client          # the rule's answer is kept
    assert any("The rule and the AI disagree on Furnish and Wire Hot Water Control Valve and Actuator" in str(item)
               for item in system.review)

    transformer = _line(system, "Furnish and Install VAV Transformer")   # a weak answer changes nothing
    assert transformer.category == "ASSUMPTION"

    notes = [item.text for item in system.blocks[0].items if item.kind == "note"]
    assert notes == ["**VAV boxes maintain the space temperature"]   # only the note the evidence bears out
    assert any("Space sensors mounted at 48 inches" in str(item) for item in system.review)
    assert any("Furnish a coffee machine" in item.evidence for item in system.review)


def test_the_ai_can_decide_a_pending_line_from_a_drawing_note():
    rows = _rows(["AHU-1"], ("TAG", "CFM"), {"CFM": "5000"}, title="AIR HANDLING UNIT SCHEDULE")
    note = Note("M-101", DWG, 3, "KEY NOTES", "4", "PROVIDE DUCT PRESSURE SENSOR FOR AHU-1.", True, "")
    judge = FakeJudge([Choice("Furnish and Install Supply Static Pressure Sensor", True, None,
                              "A key note asks for it.", "PROVIDE DUCT PRESSURE SENSOR FOR AHU-1", 0.8)])
    system = _write(_bundle("AHU", "Air Handling Unit", ["AHU-1"], rows=rows, notes=(note,)), judge=judge)
    line = _line(system, "Furnish and Install Supply Static Pressure Sensor")
    assert (line.category, line.client, line.confidence) == ("ADDED", True, 0.7)
    assert "M-101" in line.evidence


def test_an_ai_that_fails_leaves_the_lines_pending_with_its_reason():
    class Down(FakeJudge):
        def judge(self, *args):
            self.last_error = "the AI service is busy (too many requests); try again later"
            return None
    rows = _rows(["AHU-1"], ("TAG", "CFM"), {"CFM": "5000"}, title="AIR HANDLING UNIT SCHEDULE")
    system = _write(_bundle("AHU", "Air Handling Unit", ["AHU-1"], rows=rows), judge=Down([]))
    line = _line(system, "Furnish and Install Supply Static Pressure Sensor")
    assert line.category == "PENDING" and "too many requests" in line.evidence


# --- no template, existing, flags -----------------------------------------------------------------

def test_a_missing_template_gives_a_pending_block_that_is_not_printed():
    system = _write(_bundle("GV", "Gravity Ventilator", ["GV-1"]))
    assert not system.printed
    assert system.blocks[0].header == "No Master Template entry for Gravity Ventilator — write this system by hand"
    assert any(item.category == "PENDING" and "No Master Template entry for Gravity Ventilator" in item.decide
               for item in system.review)


def test_existing_units_are_not_written_as_new_work():
    family = Family("VAV", "Variable Air Volume Box", ("VAV-9",), 1, {"EXISTING": 1})
    bundle = SystemBundle("Existing VAV", "Existing Variable Air Volume Box", (family,), (), (), (), (), (), (),
                          (), ("1 VAV tag marked existing on the schedule (VAV-9) — not new work; confirm any "
                               "removal or reuse scope",), existing=True)
    system = _write(bundle)
    assert not system.printed
    assert any("VAV-9" in str(item) for item in system.review)


def test_bundle_flags_reach_the_review_list_with_their_category():
    flag = "2 more VAV tags on the drawings but not on the schedule (EXTRA) — not priced until confirmed"
    system = _write(_vav(flags=(flag,)))
    [item] = [i for i in system.review if "on the drawings but not on the schedule" in i.decide]
    assert item.category == "EXTRA" and item.action == "not priced until confirmed"


def test_nothing_internal_reaches_the_client_blocks():
    judge = FakeJudge([Choice("Furnish DDC Controller to the Factory for Installation", True, None,
                              "The sequence names it.", "each VAV box shall maintain", 0.9)])
    systems = [_write(_vav(), judge=judge), _write(_vav(passages=())),
               _write(_bundle("RTU", "Rooftop Unit", ["RTU-1"], controls_by=("FACTORY CONTROL PACKAGE",)))]
    hints = [hint for t in TEMPLATES for hint in t.hints]
    for system in systems:
        for block in system.blocks:
            texts = [block.header] + [item.text for item in block.items]
            for text in texts:
                assert not any(re.search(rf"\b{word}\b", text) for word in CATEGORY_WORDS), text
                assert "confidence" not in text.lower() and "rule:" not in text and "AI:" not in text
                assert text not in hints and "tech hour" not in text.lower()


def test_tag_list_is_compact():
    assert tag_list(["VAV-21-01", "VAV-21-02", "VAV-21-03"]) == "VAV-21-01 thru 03"
    assert tag_list(["AHU-1", "AHU-2"]) == "AHU-1, 2"
    assert tag_list(["EF-3", "EF-8", "TEF-1"]) == "EF-3, 8, TEF-1"


# --- the job ---------------------------------------------------------------------------------------

def test_build_job_gives_a_job_that_fits_the_price_sheet():
    schedule = Schedule(DWG, 5, "M-601", "VAV BOX SCHEDULE", ("TAG", "HW GPM"),
                        tuple(ScheduleRow(t, {"TAG": t, "HW GPM": "1.5"}, None, None) for t in VAV_TAGS),
                        False, (), ())
    items = tuple(InventoryItem(t, "Variable Air Volume Box", "CONFIRMED", 1, "M-601 VAV BOX SCHEDULE", ("M-101",),
                                "", "") for t in VAV_TAGS)
    items += (InventoryItem("ZZ-1", "Mystery Box", "EXTRA", None, None, ("M-101",), "", ""),)
    catalogue = SimpleNamespace(job=SimpleNamespace(name="26-9999", root=Path("26-9999, 1 Test Street")),
                                overview=SpecOverview(), pages=(), sheets=(), sections=(), tags=())
    reading = SimpleNamespace(schedules=(schedule,), inventory=items, notes=(), backbone=(), devices=(), versions=(),
                              flags=())
    job, systems, flags = build_job(catalogue, reading, None, dt.date(2026, 9, 25))
    assert isinstance(job, Job)
    check_fit(job)
    assert job.header.reference == "1 Test Street"
    assert [b.header for b in job.blocks] == ["Qty (3) Variable Air Volume Box VAV-1 thru 3"]
    assert systems[0].bundle_key == "Front end"
    assert any("ZZ-1" in flag for flag in flags)            # a family on no schedule reaches the review list
