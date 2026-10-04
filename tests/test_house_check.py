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


EDH = PlannedSystem("EDH", "Electric Duct Heater EDH-1", "Electric Duct Heater", ("EDH-1",), 1, "[S5]", "1", (), (), "", "", "", "", facts=("F1",))
HEATER_LINES = ("Furnish Electric Duct Heater SCR Control", "Wire Electric Duct Heater Interlock to Unit Enable")


def test_a_duct_heater_serving_a_packaged_unit_keeps_only_its_interlock():
    out = house_check(_scope(*map(_line, HEATER_LINES)), EDH, "field", {}, STYLE, heater_class="packaged")
    assert [l.text for l in out.lines] == ["Wire Electric Duct Heater Interlock to Unit Enable"]


def test_a_duct_heater_serving_a_field_unit_keeps_its_full_scope():
    out = house_check(_scope(*map(_line, HEATER_LINES)), EDH, "field", {}, STYLE, heater_class="field")
    assert [l.text for l in out.lines] == list(HEATER_LINES) and out.refused == () and out.changed == ()


def test_a_duct_heater_serving_an_unknown_unit_is_kept_in_full_and_says_so():
    out = house_check(_scope(*map(_line, HEATER_LINES)), EDH, "field", {}, STYLE)
    assert [l.text for l in out.lines] == list(HEATER_LINES)
    assert out.changed == ("duct heater kept in full: the unit it serves is not known",)


# --- duct heaters written in one place (house rules round 2) ----------------------------------------------------

BMS_ITEM = ("The BMS will provide field installed controls for the electric duct heater.", "S31")
FULL_HEATER = ("Furnish Electric Duct Heater SCR Control", "Furnish and Install Electric Duct Heater Discharge Air Temperature Sensor",
               "Wire Electric Duct Heater Interlock to Unit Enable")


def test_a_sequence_giving_the_bms_the_heater_keeps_full_scope_on_a_packaged_unit():
    out = house_check(_scope(*map(_line, FULL_HEATER)), EDH, "field", {}, STYLE, heater_class="packaged",
                      heater_assignment=BMS_ITEM)
    assert [l.text for l in out.lines] == list(FULL_HEATER) and out.refused == ()
    assert out.changed == ("duct heater kept in full: the sequence gives the BMS the heater's control ([S31] “The BMS "
                           "will provide field installed controls for the electric duct heater.”)",)


def test_without_that_sentence_the_heater_on_a_packaged_unit_is_interlock_only():
    out = house_check(_scope(*map(_line, FULL_HEATER)), EDH, "field", {}, STYLE, heater_class="packaged",
                      heater_assignment=("", ""))
    assert [l.text for l in out.lines] == ["Wire Electric Duct Heater Interlock to Unit Enable"]


def test_a_heater_line_in_the_served_units_block_is_refused():
    ERV = PlannedSystem("ERV", "Energy Recovery Ventilator ERV-1", "Energy Recovery Ventilator", ("ERV-1",), 1, "[S9]",
                        "1", (), (), "", "", "", "", facts=("F1",))
    scope = _scope(_line("Wire Electric Duct Heater Interlock to Unit Enable"), _line("Furnish BMS Communication Wiring to Factory Controls"))
    out = house_check(scope, ERV, "packaged", {"duct heater interlock EDH-1": "EDH"}, STYLE,
                      heater_home=("EDH-1", "Electric Duct Heater EDH-1"))
    assert [l.text for l in out.lines] == ["Furnish BMS Communication Wiring to Factory Controls"]
    assert out.refused == ("“Wire Electric Duct Heater Interlock to Unit Enable”: the duct heaters serving this unit "
                           "(EDH-1) are written in the Electric Duct Heater EDH-1 block; left out here",)


NOT_AN_ASSIGNMENT = (
    "The duct heater shall be enabled by the unit controller and its status monitored by the BMS.",
    "The duct heater, provided by Division 23, shall be interlocked with the ERV and monitored by the BMS.",
    "The duct heater interlock shall be wired to the BMS controller.",
    "The electric duct heater SCR control is by the heater mfr and alarms are reported to the BMS.",
    "Duct heater controls by others, not by BMS.",
    "The duct heater interlock is wired by the controls contractor.",
    "The BMS will provide the supply fan controls.",
    "The BMS shall provide an enable signal to the duct heater.",
    "The duct heater shall be provided with field installed controls by Division 26.",
    "The BMS shall provide an interlock to the duct heater.",
    "The controls contractor shall provide the duct heater control signal.",
    "The BMS shall monitor the duct heater status; heater controls by the heater manufacturer.",
    "The duct heater controls shall be furnished by the electrical contractor and enabled by the BMS.",
)
AN_ASSIGNMENT = (
    "The BMS will provide field installed controls for the electric duct heater serving the OA intake of the unit.",
    "The BMS shall control the electric duct heater to maintain discharge air temperature.",
    "The controls contractor shall provide the electric duct heater controls.",
    "The electric duct heater shall be controlled by the BMS.",
)


def test_the_heater_control_sentence_needs_an_assignment_to_the_bms():
    from estimator.writing.house_check import heater_control_sentence
    for sentence in NOT_AN_ASSIGNMENT:
        assert heater_control_sentence(sentence, STYLE) == "", sentence
    for sentence in AN_ASSIGNMENT:
        assert heater_control_sentence(sentence, STYLE) == sentence, sentence
    assert heater_control_sentence("[S30] The fans run. " + AN_ASSIGNMENT[1], STYLE) == AN_ASSIGNMENT[1]
