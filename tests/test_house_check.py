"""The packaged-unit doctrine in code: internal devices and monitored points are not lines on a packaged unit,
shipped-loose devices are installed and wired, duct heaters are interlock-only, shared items stay with their owner."""
from estimator.writing.house_check import house_check
from estimator.writing.style import load_house_style
from estimator.writing.whole_job import PlannedSystem, WrittenLine, WrittenScope


def _line(text, quote="BMS contractor shall connect the DDC controller to the BMS network"):
    return WrittenLine(text=text, depth=1, quantity=None, quote=quote, source_id="S2", why="", confidence=0.8,
                       reference="", flag="", flag_text="", fact_ids=("F1",))


def _scope(*lines):
    return WrittenScope(lines=tuple(lines), client_notes=(), tech_hours_hint=None, review_notes=(), model="m")


RTU = PlannedSystem("RTU", "Rooftop Unit RTU-1, 2", "Rooftop Unit", ("RTU-1", "RTU-2"), 2, "[S5]", "2", (), (), "", "", "", "", facts=("F1",))
STYLE = load_house_style()


def test_internal_devices_and_monitored_points_are_refused_on_a_packaged_unit():
    scope = _scope(_line("Wire DX Cooling Control (Each Stage)"), _line("Furnish Supply Fan Status"),
                   _line("Furnish BMS Communication Wiring to Factory Controls"),
                   _line("Install and Wire Space Temperature Sensor (Furnished by Unit Mfr.)"))
    out = house_check(scope, RTU, "packaged", {}, STYLE)
    assert [l.text for l in out.lines] == ["Furnish BMS Communication Wiring to Factory Controls",
                                           "Install and Wire Space Temperature Sensor (Furnished by Unit Mfr.)"]
    assert any("inside the unit" in r for r in out.refused)
    assert any("monitored point on a packaged unit" in r for r in out.refused)


def test_an_internal_device_the_sequence_assigns_to_the_controls_contractor_stays():
    scope = _scope(_line("Furnish and Wire Hot Water Control Valve and Actuator",
                         quote="The BMS contractor shall furnish and wire the hot water control valve"))
    out = house_check(scope, RTU, "packaged", {}, STYLE)
    assert len(out.lines) == 1 and out.refused == ()


def test_a_shipped_loose_wire_line_becomes_install_and_wire():
    scope = _scope(_line("Wire Supply Air Temperature Sensor (Furnished by Unit Mfr.)"))
    out = house_check(scope, RTU, "packaged", {}, STYLE)
    assert out.lines[0].text == "Install and Wire Supply Air Temperature Sensor (Furnished by Unit Mfr.)"
    assert out.changed and "shipped-loose" in out.changed[0]


def test_duct_heater_full_scope_is_cut_to_the_interlock_on_a_packaged_unit():
    scope = _scope(_line("Furnish Electric Duct Heater SCR Control"), _line("Wire Electric Duct Heater Auxiliary Contact for Remote Unit Shutdown"),
                   _line("Furnish and Install Electric Duct Heater Discharge Air Temperature Sensor"))
    out = house_check(scope, RTU, "packaged", {}, STYLE)
    assert [l.text for l in out.lines] == ["Wire Electric Duct Heater Auxiliary Contact for Remote Unit Shutdown"]


def test_a_field_ddc_system_keeps_its_point_lines():
    scope = _scope(_line("Furnish Fan Start / Stop and Status"), _line("Furnish and Install Damper Actuator"))
    out = house_check(scope, RTU, "field", {}, STYLE)
    assert len(out.lines) == 2 and out.refused == ()


def test_an_item_another_block_owns_is_refused_here():
    scope = _scope(_line("Furnish and Install Damper Actuator MD-1"), _line("Tie in Condensate Pump Float Switch"))
    out = house_check(scope, RTU, "field", {"damper actuator MD-1": "EF", "condensate pump float switch": "RTU"}, STYLE)
    assert [l.text for l in out.lines] == ["Tie in Condensate Pump Float Switch"]
    assert out.refused == ("“Furnish and Install Damper Actuator MD-1” is written under EF; left out here",)


def test_a_shaft_leak_detector_is_not_an_internal_device():
    scope = _scope(_line("Furnish and Install Refrigerant Leak Detector",
                         quote="Provide Refrigerant leak detector within each refrigerant shaft"))
    out = house_check(scope, RTU, "packaged", {}, STYLE)
    assert len(out.lines) == 1 and out.refused == ()


def test_an_internal_device_is_refused_when_the_quote_names_the_contractor_but_not_the_device():
    scope = _scope(_line("Wire DX Cooling Control (Each Stage)",
                         quote="The BMS contractor shall connect the DDC controller to the BMS network"))
    out = house_check(scope, RTU, "packaged", {}, STYLE)
    assert out.lines == () and any("inside the unit" in r for r in out.refused)
