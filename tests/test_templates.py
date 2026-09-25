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
