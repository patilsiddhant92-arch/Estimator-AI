"""The Master Template as data: assets/system_templates.json and its loader."""
import json

import pytest

from estimator.writing.templates import (
    ASSETS,
    QUANTITIES,
    TECH_HOUR_BASES,
    SystemTemplate,
    integration_trio,
    load_templates,
    nearest_templates,
    template_for,
)

RAW = json.loads((ASSETS / "system_templates.json").read_text(encoding="utf-8"))
TEMPLATES = load_templates()
VERBS = tuple(RAW["verbs"])
EQUIPMENT = json.loads((ASSETS / "reading_lists" / "equipment.json").read_text(encoding="utf-8"))


def _starts_with_verb(text: str) -> bool:
    return any(text.lower().startswith(verb.lower() + " ") for verb in VERBS)


def test_every_system_in_the_json_loads():
    assert len(TEMPLATES) == len(RAW["systems"])
    assert all(isinstance(t, SystemTemplate) for t in TEMPLATES)
    names = [t.name for t in TEMPLATES]
    assert len(names) == len(set(names)), "system names are unique"
    for template in TEMPLATES:
        assert template.lines, template.name
        assert template.header.strip(), template.name
        assert template.prefixes or template.kinds, f"{template.name} applies to nothing"


def test_the_main_systems_are_there():
    names = {t.name for t in TEMPLATES}
    for name in ["VAV / Fan VAV", "Fan Coil Unit", "Air Handling Unit", "Packaged ERU / RTU / AHU",
                 "Chilled Water System", "Hot Water System", "Condenser Water System", "Heat Exchanger System",
                 "Kitchen Exhaust Ventilation", "Gas Detection", "VRF System", "Split System", "Global Points"]:
        assert name in names


def test_every_line_starts_with_a_verb_or_is_a_trio_line_or_a_note():
    for template in TEMPLATES:
        for line in template.lines:
            ok = _starts_with_verb(line.text) or line.trio or line.quantity == "none" or line.depth > 1 or line.no_verb
            assert ok, f"{template.name}: {line.text!r}"
            if line.no_verb:
                assert not _starts_with_verb(line.text), f"{template.name}: {line.text!r} has a verb, drop no_verb"


def test_line_texts_are_clean():
    for template in TEMPLATES:
        for line in template.lines:
            assert line.text == line.text.strip(), line.text
            assert "  " not in line.text, line.text
            assert "#" not in line.text and "**" not in line.text and "→" not in line.text, line.text
            assert "tech hour" not in line.text.lower(), line.text
            assert line.quantity in QUANTITIES, line.text
            assert line.depth in (1, 2), line.text


def test_every_condition_named_by_a_line_is_defined_and_has_somewhere_to_look():
    for template in TEMPLATES:
        for name, condition in template.conditions.items():
            assert condition.name == name
            assert (condition.schedule or condition.sequence or condition.notes or condition.prefix
                    or condition.spec_overview), f"{template.name}: {name} looks nowhere"
        used = set()
        for line in template.lines:
            used.update(line.when)
            used.update(line.unless)
        for th in (template.tech_hours, *template.extra_tech_hours):
            for when, _ in th.overrides:
                used.update(when)
        missing = used - set(template.conditions)
        assert not missing, f"{template.name}: undefined conditions {missing}"


def test_every_line_is_either_a_default_or_has_a_condition():
    for template in TEMPLATES:
        for line in template.lines:
            assert line.default or line.when, f"{template.name}: {line.text!r} is never chosen"


def test_choice_groups_have_exactly_one_default():
    for template in TEMPLATES:
        groups: dict[str, list] = {}
        for line in template.lines:
            if line.choice:
                groups.setdefault(line.choice, []).append(line)
        for group, lines in groups.items():
            assert len(lines) >= 2, f"{template.name}: choice {group} has only one line"
            defaults = [line for line in lines if line.default]
            assert len(defaults) == 1, f"{template.name}: choice {group} has {len(defaults)} defaults"


def test_hints_never_appear_in_any_line_text():
    for template in TEMPLATES:
        texts = [line.text for line in template.lines] + list(template.client_notes)
        for hint in template.hints:
            assert hint.strip()
            for text in texts:
                assert hint not in text, f"{template.name}: hint {hint!r} is in {text!r}"
        for line in template.lines:
            assert line.text not in template.hints


def test_tech_hours_are_well_formed():
    for template in TEMPLATES:
        for th in (template.tech_hours, *template.extra_tech_hours):
            assert th.per in TECH_HOUR_BASES, template.name
            assert th.hours is None or th.hours >= 0
            for when, hours in th.overrides:
                assert when and hours >= 0


def test_vav_rules_follow_the_template():
    vav = template_for("VAV", "", TEMPLATES)
    assert vav is not None and vav.name == "VAV / Fan VAV"
    assert vav.tech_hours.per == "unit" and vav.tech_hours.hours == 3
    assert (("reheat_hot_water",), 4) in vav.tech_hours.overrides
    texts = [line.text for line in vav.lines]
    assert texts[0] == "Furnish DDC Controller to the Factory for Installation"
    sensors = [line for line in vav.lines if line.choice == "space_sensor"]
    assert [line.text for line in sensors if line.default] == ["Furnish and Install Space Temperature Sensor"]
    t_h_co2 = next(line for line in sensors if "Humidity / CO2" in line.text)
    assert set(t_h_co2.when) == {"space_humidity", "space_co2"}
    fan = next(line for line in vav.lines if line.text == "Furnish Fan Enable")
    assert fan.when == ("fan_powered",)
    assert "FPB" in vav.conditions["fan_powered"].prefix


def test_hardware_points_follow_the_verb():
    ahu = template_for("AHU", "", TEMPLATES)
    assert ahu is not None and ahu.tech_hours.per == "hardware_point" and ahu.tech_hours.hours == 2
    by_text = {line.text: line for line in ahu.lines}
    assert by_text["Furnish and Install Mixed Air Temperature Sensor"].hardware_point
    assert by_text["Furnish Supply Fan VFD control"].hardware_point
    assert not by_text["Furnish and Install DDC Controller"].hardware_point
    chw = next(t for t in TEMPLATES if t.name == "Chilled Water System")
    for line in chw.lines:
        if line.trio:
            assert not line.hardware_point, line.text


def test_template_for_picks_by_prefix_and_by_kind():
    assert template_for("VAV", "Variable Air Volume Box", TEMPLATES).name == "VAV / Fan VAV"
    assert template_for("FPB", "", TEMPLATES).name == "VAV / Fan VAV"
    assert template_for("fcu", "", TEMPLATES).name == "Fan Coil Unit"
    assert template_for("RTU", "", TEMPLATES).name == "Packaged ERU / RTU / AHU"
    assert template_for("", "Chilled Water System", TEMPLATES).name == "Chilled Water System"
    assert template_for("", "boiler plant", TEMPLATES).name == "Hot Water System"
    # a family standing alone prefers its own template over a plant group
    assert template_for("HP", "", TEMPLATES).group is False
    # the kind decides before the prefix: an existing FCU is not a new FCU
    assert template_for("FCU", "Existing Fan Coil Unit", TEMPLATES).name.startswith("Existing Fan Coil Unit")


def test_template_for_gives_none_for_an_unknown_prefix():
    assert template_for("ZZQ", "", TEMPLATES) is None
    assert template_for("ZZQ", "Mystery Box", TEMPLATES) is None


def test_group_systems_are_marked():
    groups = {t.name for t in TEMPLATES if t.group}
    for name in ["Chilled Water System", "Condenser Water System", "Hot Water System", "Heat Exchanger System",
                 "Geothermal System", "Kitchen Exhaust Ventilation", "Gas Detection", "Split System", "VRF System",
                 "Stair Pressurization Fans"]:
        assert name in groups, name
    for template in TEMPLATES:
        if template.group:
            assert len(template.prefixes) + len(template.kinds) >= 2, template.name


def test_integration_trio():
    first, second, third = integration_trio("Chiller")
    assert first == "Furnish BMS Communication Wiring to Chiller Factory Controls"
    assert second == "Map Available Points Via Mfr. Provided BMS Interface"
    assert third == "AME requires mfr. Rep to assist in integration, cost to be incurred by mech contractor"
    assert integration_trio("")[0] == "Furnish BMS Communication Wiring to Factory Controls"


def test_trio_lines_are_marked():
    packaged = template_for("RTU", "", TEMPLATES)
    trio = [line for line in packaged.lines if line.trio]
    assert [line.text.split(" ")[0] for line in trio] == ["Furnish", "Map", "AME"]
    assert trio[-1].depth == 2


def test_load_templates_rejects_a_bad_choice_group(tmp_path):
    bad = json.loads(json.dumps(RAW))
    vav = next(s for s in bad["systems"] if s["name"] == "VAV / Fan VAV")
    for line in vav["lines"]:
        if line.get("choice") == "space_sensor":
            line["default"] = True
    path = tmp_path / "t.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="space_sensor"):
        load_templates(path)


def test_load_templates_rejects_an_unknown_condition(tmp_path):
    bad = json.loads(json.dumps(RAW))
    bad["systems"][0]["lines"][0]["when"] = ["no_such_condition"]
    path = tmp_path / "t.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="no_such_condition"):
        load_templates(path)


def test_prefixes_are_upper_case_and_mostly_known():
    known = set(EQUIPMENT["prefixes"])
    for template in TEMPLATES:
        for prefix in template.prefixes:
            assert prefix == prefix.upper()
    missing = {p for t in TEMPLATES for p in t.prefixes} - known
    assert not missing, f"prefixes the template needs that equipment.json doesn't list: {sorted(missing)}"


def _nearest(kind, prefix, k=3):
    return [t.name for t in nearest_templates(kind, prefix, TEMPLATES, k=k)]


def test_the_nearest_templates_to_an_electric_duct_heater_are_the_heaters_and_the_electric_heat_lines():
    nearest = _nearest("Electric Duct Heater", "EDH")
    assert nearest[0] == "EUH / CUH / UH"                 # "Electric" in its kinds
    assert "VAV / Fan VAV" in nearest                      # its electric heat lines
    assert _nearest("Electric Duct Heater", "EDH") == nearest   # the same every time


def test_the_nearest_templates_follow_the_words_and_the_prefix():
    assert _nearest("Occupancy Sensor", "OCC")[0] == "VAV / Fan VAV"
    assert _nearest("Chilled Water Pump", "CHWP")[0] == "Chilled Water System"
    assert _nearest("Hot Water Heater", "EWH")[0] == "Hot Water System"
    assert _nearest("Motorized Damper", "MD")[0] == "Fire / Smoke Dampers"
    assert _nearest("", "VAV") == ["VAV / Fan VAV"]       # only the prefix to go on
    assert _nearest("Xyzzy", "QQ") == []                  # nothing shared: none chosen
    assert len(_nearest("Electric Heater", "EH", k=2)) == 2


def test_a_packaged_unit_is_sixteen_tech_hours_each():
    [packaged] = [t for t in TEMPLATES if t.name == "Packaged ERU / RTU / AHU"]
    assert (packaged.tech_hours.per, packaged.tech_hours.hours) == ("unit", 16)
    assert "tech hour: 16 hour each (estimator, 2026-09-25)" in packaged.hints


def _split_and_vrf():
    return (next(t for t in TEMPLATES if t.name == "Split System"),
            next(t for t in TEMPLATES if t.name == "VRF System"))


def _holds(template, name, evidence):
    from estimator.writing.write import _word
    return any(_word(w).search(evidence) for w in template.conditions[name].sequence)


def _bms_sensor_line(template):
    return next(line for line in template.lines if "Space Temperature Sensor (BMS Monitoring)" in line.text)


def test_the_split_bms_space_sensor_is_not_a_default():
    split, _ = _split_and_vrf()
    line = _bms_sensor_line(split)
    assert not line.default and line.when == ("bms_space_sensor",)
    assert "Furnish and Install Space Temperature Sensor (BMS Monitoring)" not in [
        l.text for l in split.lines if l.default]


def test_a_sequence_naming_a_bms_furnished_space_sensor_brings_the_line():
    split, _ = _split_and_vrf()
    for text in ["The BMS contractor shall provide a space temperature sensor for each unit.",
                 "A space temperature sensor furnished by the BMS monitors each room.",
                 "The BMS shall furnish a space temperature sensor at every indoor unit."]:
        assert _holds(split, "bms_space_sensor", text), text


def test_the_bms_wiring_the_manufacturers_sensor_does_not_bring_the_line():
    split, _ = _split_and_vrf()
    for text in ["The BMS contractor shall wire the manufacturer's space temperature sensor.",
                 "Wire the unit mfr. space temperature sensor to the controller.",
                 "The BMS contractor shall wire the manufacturer's space temperature sensor to the BMS.",
                 "BMS space temperature sensor furnished by unit mfr. is wired by the BMS contractor."]:
        assert not _holds(split, "bms_space_sensor", text), text


def test_the_split_system_takes_ceiling_and_outdoor_units_and_names_them():
    split, vrf = _split_and_vrf()
    assert {"CAC", "ODU"} <= set(split.prefixes)
    assert template_for("CAC", "", TEMPLATES).name == "Split System"
    assert template_for("ODU", "", TEMPLATES).name in {"Split System", "VRF System"}
    names = split.family_names
    assert names["CU"] == "Condensing Unit" and names["ODU"] == "Outdoor Unit"
    assert names["CAC"] == "Indoor Unit" and names["AC"] == "Indoor Unit"
    for prefix in ("AC", "IDU", "WAC"):
        assert vrf.family_names[prefix] == "Indoor Unit"
    for prefix in ("ACCU", "ODU"):
        assert vrf.family_names[prefix] == "Condensing Unit"
    for prefix in ("BS", "HRU", "BC"):
        assert vrf.family_names[prefix] == "Branch Selector"


def test_the_split_hints_agree_with_the_family_names():
    split, _ = _split_and_vrf()
    text = " ".join(split.hints)
    assert "Indoor Unit AC-" in text and "Condensing Unit CU-" in text and "Outdoor Unit ODU-" in text
    assert "Split System Indoor Unit" not in text


def test_every_indoor_unit_line_of_the_split_system_counts_a_ceiling_unit():
    split, _ = _split_and_vrf()
    for line in split.lines:
        if line.of:
            assert "CAC" in line.of and "ODU" not in line.of, line.text
    assert "CAC" in split.tech_hours.of and "ODU" not in split.tech_hours.of
