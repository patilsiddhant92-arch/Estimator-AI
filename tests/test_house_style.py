"""The house style as data: it agrees with the Master Template file, and it tells good lines from bad."""
import json

from estimator.writing.front_end import FRONT_END_FILE
from estimator.writing.style import STYLE_FILE, load_house_style
from estimator.writing.templates import TEMPLATES_FILE, load_templates

STYLE = load_house_style()
TEMPLATES_RAW = json.loads(TEMPLATES_FILE.read_text(encoding="utf-8"))


def test_the_verbs_and_the_trio_are_the_master_templates_own():
    assert list(STYLE.verbs) == TEMPLATES_RAW["verbs"]
    assert list(STYLE.trio) == TEMPLATES_RAW["integration_trio"]
    assert list(STYLE.trio_depths) == TEMPLATES_RAW["integration_trio_depths"]


def test_each_opening_without_a_verb_is_one_the_template_writes():
    front = json.loads(FRONT_END_FILE.read_text(encoding="utf-8"))
    no_verb = [line.text.lower() for t in load_templates() for line in t.lines if line.no_verb or line.depth > 1]
    no_verb += [h.lower() for h in front["headings"].values()]
    for start in STYLE.openings:
        assert any(text.startswith(start.lower() + " ") for text in no_verb), start


def test_the_file_holds_every_part_the_brief_asks_for():
    raw = json.loads(STYLE_FILE.read_text(encoding="utf-8"))
    for key in ("verbs", "trailing_forms", "integration_trio", "notes", "forbidden", "guide"):
        assert raw[key], key
    for form in ("(Furnished by Unit Mfr.)", "(Furnished by Others)", "(Qty. N Total)", "(as per sequence)"):
        assert form in STYLE.trailing_forms
    assert any("guidance" in line for line in STYLE.guide)       # the "How to use this template" section
    assert any("Qty (#) System Header" in line for line in STYLE.guide)


def test_every_line_the_master_template_writes_passes_the_check():
    for template in load_templates():
        for line in template.lines:
            text = " ".join(line.text.replace("{what}", "Chiller").replace("{unit}", "Alarm Panel").split())
            assert STYLE.check_line(text, line.depth) is None, (template.name, line.text)
            assert STYLE.check_line(text.lower() if line.no_verb else text, line.depth) is None


def test_the_estimators_openings_without_a_verb_are_accepted():
    for text in ("Map Available Points Via Mfr. Provided BMS Interface", "Monitor the following Alarms",
                 "Tie-in Ionization Device Alarm", "Tie into BMS", "Interlock Fan with Damper",
                 "Low Voltage Interlock Wiring between Indoor and Outdoor Unit",
                 "AME requires mfr. Rep to assist in integration, cost to be incurred by mech contractor",
                 "Seamlessly Tie in to the Existing Metasys BMS", "Re-commission unit to ensure proper operation",
                 "Demo and safe-off existing control wiring", "Extend communication bus to new unit location",
                 "Wire Leak Detector (Furnished by Others)", "Run 24V Power Loop to VAVs"):
        assert STYLE.check_line(text) is None, text


def test_a_template_line_is_written_in_the_templates_own_capitals():
    rep = "AME requires mfr. Rep to assist in integration, cost to be incurred by mech contractor"
    assert STYLE.template_form("AME Requires Mfr. Rep to Assist in Integration, cost to be Incurred by Mech "
                               "Contractor") == rep
    assert STYLE.template_form("map available points via mfr. provided bms interface") ==         "Map Available Points Via Mfr. Provided BMS Interface"
    assert STYLE.template_form("Furnish bms communication wiring to RTU factory controls") ==         "Furnish BMS Communication Wiring to RTU Factory Controls"
    assert STYLE.template_form("Furnish and Install Space Humidistat") == "Furnish and Install Space Humidistat"
    every = [line.text for t in load_templates() for line in t.lines if line.text.lower() == rep.lower()]
    assert every and set(every) == {rep}                       # the same everywhere in the Master Template


def test_a_long_note_giving_a_device_to_the_unit_takes_the_short_house_form():
    assert STYLE.short_note("**Demand-control ventilation controls are coming with the unit per equipment "
                            "schedule") == "*DEMAND-CONTROL VENTILATION CONTROLS BY UNIT MFR."
    assert STYLE.short_note("**Fan controller and space sensors furnished by the fan manufacturer per equipment "
                            "schedule") == "*FAN CONTROLLER AND SPACE SENSORS BY UNIT MFR."
    assert STYLE.short_note("**Start/Stop via Fire Alarm System") is None
    assert STYLE.same_note("**Systems to be started/commissioned by manufacturer's factory authorized personnel",
                           "**Branch circuit controllers to be started and commissioned by manufacturer's factory "
                           "authorized personnel")
    assert not STYLE.same_note("**Supply and return smoke detectors are coming with the unit per equipment schedule",
                               "**Refrigeration leak detection sensor is coming with the unit per equipment schedule")


def test_the_house_order_of_a_systems_lines_is_data():
    raw = json.loads(STYLE_FILE.read_text(encoding="utf-8"))
    assert raw["line_order"]["order"] == ["controller", "sensors", "points", "valves and dampers", "integration",
                                          "notes"]
    groups = {"Furnish DDC Controller to the Factory for Installation": "controller",
              "Install and wire Space Thermostat (Furnished by Unit Mfr.)": "controller",
              "Furnish and Install Space Temperature Sensor for High Temp. Alarm (Location: Room 1)": "sensors",
              "Furnish Fan Start / Stop and Status": "points",
              "Furnish and Wire Hot Water Control Valve and Actuator": "valves and dampers",
              "Furnish and Install Damper Actuator": "valves and dampers",
              "Furnish BMS Communication Wiring to RTU Factory Controls": "integration",
              "Map Available Points Via Mfr. Provided BMS Interface": "integration",
              "Low Voltage Interlock Wiring between Indoor and Outdoor Unit": None,
              "Furnish and Install VAV Transformer": None}
    for text, group in groups.items():
        assert STYLE.line_group(text) == group, text


def test_bad_lines_and_notes_are_named_in_plain_words():
    assert STYLE.check_line("Furnish and Install Occupancy Sensor") is None
    assert STYLE.check_line("Interlock with Associated AHU Operation") is None
    assert STYLE.check_line("Map Available Points Via Mfr. Provided BMS Interface") is None
    assert "verb" in STYLE.check_line("Occupancy Sensor")
    assert "tech hours" in STYLE.check_line("Furnish and Install Sensor (4 hours)")
    assert STYLE.check_line("Furnish and Install Sensor $120") is not None
    assert STYLE.check_line("Furnish and Install " + "Sensor " * 30) is not None
    assert STYLE.check_line("Furnish and Install Sensor (ASSUMPTION)") is not None
    assert STYLE.check_note("**Start/Stop via Fire Alarm System") is None
    assert STYLE.check_note("Start/Stop via Fire Alarm System") is not None
    assert STYLE.check_note("**Allow 8 hrs for the programming") is not None


def test_the_prompt_text_carries_the_rules():
    text = STYLE.prompt_text()
    for verb in STYLE.verbs:
        assert verb in text
    assert STYLE.trio[1] in text and "(Furnished by Unit Mfr.)" in text
    assert "Never write prices, tech hours" in text
    assert "Map" in text and "Re-commission" in text          # every opening the check accepts


def test_a_line_under_another_line_may_be_a_noun_phrase():
    style = load_house_style()
    assert style.check_line("Damper Actuator", depth=2) is None
    assert style.check_line("Damper Actuator") is not None
