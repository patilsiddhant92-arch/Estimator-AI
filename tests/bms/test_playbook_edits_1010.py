"""The Playbook edits the estimator approved on 2026-10-10 (with the answers of 2026-10-11): the new rules and topic,
the changed shapes and the exhaust fan tech hours. The repo Playbook (`playbook/`) and invented systems only. No job
data."""
from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path

import pytest

from bms.model import Count, Device, Family, Job, Ref, System
from bms.playbook import load_playbook
from bms.render import render
from bms.validate import validate

FIXTURES = Path(__file__).resolve().parent / "fixtures"
PLAYBOOK = load_playbook()
REF = Ref(source_id="S1", quote="q", where="M-1, Drawings.pdf page 1")
BASE_JOB = Job.from_dict(json.loads((FIXTURES / "sample_job.json").read_text(encoding="utf-8")))

FLOAT_SWITCH_LINE = "Tie-in Condensate Pump Float Switch (Furnished by Mfr.)"
LIGHTING_LINE = ("Interface Lighting Control System (By Others) With Front End BMS Via Manufacturer Provided BMS "
                 "Interface")
POWER_LOOP_LINE = "Run 24V Power Loop to VAVs (Mentioned 24 V Wiring Control by BMS Contractor)"


def plain(text: str) -> str:
    """A rule's text on one line."""
    return " ".join(text.split())


# ---- the new rules and the new topic -------------------------------------------------------------------------------

NEW_RULES = [
    ("Occupancy sensors are never dropped", "Evidence and citations"),
    ("Controls given to the mechanical contractor", "Ownership"),
    ("Schedule notes address the manufacturer", "Ownership"),
    ("Leak detectors", "Ownership"),
    ("Condensate pump float switch", "Ownership"),
    ("Local alarm panel", "Ownership"),
    ("Every block lists its end devices", "Ownership"),
    ("Unit control devices when AME provides the controls", "Packaged units"),
    ("Count every damper", "Dampers under their fan"),
    ("Damper actuators are Furnish and Install", "Dampers under their fan"),
    ("VAV lines", "VAV boxes and radiation"),
    ("Radiation valves tied to VAV zone thermostats", "VAV boxes and radiation"),
    ("Lighting control integration", "Front end"),
]


@pytest.mark.parametrize("name, topic", NEW_RULES)
def test_each_new_rule_is_in_its_topic(name, topic):
    assert PLAYBOOK.rule(name).topic == topic


AFTER = {       # a rule of the book -> the new rules that follow it, in order
    "Explicit assignment always wins": ["Controls given to the mechanical contractor",
                                        "Schedule notes address the manufacturer"],
    "Other trades in brackets": ["Leak detectors", "Condensate pump float switch", "Local alarm panel"],
    "Minimum points on AME-run equipment": ["Every block lists its end devices"],
    "Everything assigned is extracted": ["Occupancy sensors are never dropped"],
    "Factory-installed devices": ["Unit control devices when AME provides the controls"],
    "Dampers under their fan": ["Count every damper", "Damper actuators are Furnish and Install"],
    "Front end items by others": ["Lighting control integration"],
}


@pytest.mark.parametrize("rule", sorted(AFTER))
def test_the_new_rules_follow_the_rule_the_draft_names(rule):
    names = list(PLAYBOOK.rules)
    at = names.index(rule)
    assert names[at + 1:at + 1 + len(AFTER[rule])] == AFTER[rule]


def test_the_vav_topic_comes_just_before_vrf_and_split_systems():
    topics = list(PLAYBOOK.topics)
    assert topics.index("VAV boxes and radiation") + 1 == topics.index("VRF and split systems")
    assert [n for n, r in PLAYBOOK.rules.items() if r.topic == "VAV boxes and radiation"] == [
        "VAV lines", "Radiation valves tied to VAV zone thermostats"]


def _names_only(clause: str) -> bool:
    """`clause` is rule names of the book, joined by ", " and " and "."""
    if clause in PLAYBOOK.rules:
        return True
    for name in PLAYBOOK.rules:
        rest = clause[len(name):] if clause.startswith(name) else None
        if rest is not None:
            for joiner in (", and ", ", ", " and "):
                if rest.startswith(joiner) and _names_only(rest[len(joiner):]):
                    return True
    return False


def test_every_see_reference_names_rules_that_exist():
    broken = [(rule.name, clause) for rule in PLAYBOOK.rules.values()
              for clause in re.findall(r"\(see ([^)]+)\)", plain(rule.text)) if not _names_only(clause)]
    assert broken == []


def test_shipped_loose_devices_point_to_the_rule_for_a_unit_on_ame_controls():
    assert "see Unit control devices when AME provides the controls" in plain(PLAYBOOK.rule("Shipped-loose devices").text)


# ---- what the estimator's answers of 2026-10-11 changed in the draft ------------------------------------------------

def test_the_vav_power_loop_line_is_written_when_the_mechanical_drawings_or_specifications_mention_it():
    text = plain(PLAYBOOK.rule("VAV lines").text)
    assert f'"{POWER_LOOP_LINE}"' in text
    assert "The power loop line is written when the mechanical drawings or the specifications mention the 24 V " \
           "wiring for the VAVs." in text


def test_a_remote_duct_damper_on_a_riser_or_plan_is_ame_and_a_damper_only_in_a_schedule_is_factory():
    text = plain(PLAYBOOK.rule("Damper actuators are Furnish and Install").text)
    assert "On a unit with factory controls, a remote duct damper that a riser or a plan shows is AME's scope." in text
    assert "A damper that only a schedule shows is factory: the unit manufacturer furnishes it" in text
    inside = plain(PLAYBOOK.rule("Nothing inside the unit is a line").text)
    assert "a remote duct damper actuator that a riser or a plan shows" in inside
    assert "a damper actuator that the documents show" not in inside


def test_an_exhaust_fan_with_points_is_four_hours_per_fan_with_or_without_a_controller_of_its_own():
    assert "an exhaust fan with points is 4 hours per fan, with or without an AME controller of its own" in plain(
        PLAYBOOK.rule("Tech hours the shape cannot express").text)


def test_the_condensate_and_leak_devices_are_no_longer_listed_inside_the_unit():
    inside = plain(PLAYBOOK.rule("Nothing inside the unit is a line").text)
    assert "condensate devices" not in inside and "refrigerant leak detectors" not in inside
    assert "the leak detector at the unit, the local alarm panel module and the condensate pump float switch tie-in" \
        in inside


def test_the_mechanical_contractor_has_no_bracket_for_condensate_pumps_or_controls_items():
    text = plain(PLAYBOOK.rule("Other trades in brackets").text)
    assert "for condensate pumps and float switches" not in text
    assert '"(Furnished by Mfr.)" for the condensate pump float switch' in text
    # the loader still needs a bracket for every party (wording.json is not changed)
    assert PLAYBOOK.wording.owner_brackets["Mechanical Contractor"] == " (Furnished by Mechanical Contractor)"


def test_the_higher_count_rule_prints_the_other_counts_in_the_same_line():
    # ruling 15 of 2026-10-11: no separate quantity note; the other counts print in the line
    text = plain(PLAYBOOK.rule("Higher count prints").text)
    assert ("Every count that differs from the printed one prints in the same line "
            "(see Quantities print in the line).") in text
    assert "quantity note" not in text


# ---- the shapes -----------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("shape", ["VRF System", "Split System", "Computer Room Air Conditioning Unit"])
def test_the_float_switch_tie_in_is_fixed_text_with_the_mfr_bracket(shape):
    one = PLAYBOOK.shape(shape)
    assert one.wording["condensate_float_switch"] == FLOAT_SWITCH_LINE
    assert one.slot_kinds["condensate_float_switch"] == "interlock"


def test_front_end_has_the_lighting_interface_slot_after_it_infrastructure():
    front = PLAYBOOK.shape("Front End")
    order = front.line_order
    assert order[order.index("it_infrastructure") + 1] == "lighting_interface"
    assert front.slot_kinds["lighting_interface"] == "wiring"
    assert front.wording["lighting_interface"] == LIGHTING_LINE


def test_misc_monitoring_keeps_its_lighting_interface_slot():
    # the estimator kept it (answer a); the rule "Lighting control integration" says where the line is written
    misc = PLAYBOOK.shape("Misc Monitoring Systems")
    assert misc.line_order[misc.line_order.index("meter_comm_wiring") + 1] == "lighting_interface"
    assert misc.slot_kinds["lighting_interface"] == "wiring"
    assert misc.wording["lighting_interface"] == LIGHTING_LINE


def test_the_vav_power_loop_wording_has_the_template_bracket():
    vav = PLAYBOOK.shape("VAV / Fan VAV")
    assert vav.wording["power_loop"] == POWER_LOOP_LINE
    assert vav.slot_kinds["power_loop"] == "wiring"


def test_exhaust_fan_has_a_space_thermostat_slot_after_space_temperature():
    fan = PLAYBOOK.shape("Exhaust Fan")
    assert fan.line_order[fan.line_order.index("space_temperature") + 1] == "space_thermostat"
    assert fan.slot_kinds["space_thermostat"] == "device"
    assert fan.wording["space_thermostat"] == "{verb} {device}{owner}"


def test_an_exhaust_fan_with_points_and_no_controller_is_four_hours_per_fan():
    fan = PLAYBOOK.shape("Exhaust Fan")
    hours = fan.tech_hours
    assert hours.per == "unit" and hours.hours is None          # an interlock-only fan has none
    conditions = {slots: given for slots, given in hours.when}
    points = [slot for slot in fan.line_order if fan.slot_kinds[slot] == "point"]
    assert points == ["start_stop_status", "vfd_control", "other_point"]
    for slot in ["controller", *points]:
        assert conditions[(slot,)] == 4.0, slot
    assert set(conditions.values()) == {4.0} and ("interlock",) not in conditions


# ---- what the changed slots print, on invented systems --------------------------------------------------------------

def device(id_: str, slot: str, name: str, verb: str = "Furnish and Install", furnished="AME", installed="AME",
           wired="AME") -> Device:
    return Device(id=id_, slot=slot, name=name, verb=verb, furnished_by=furnished, installed_by=installed,
                  wired_by=wired, quantity=Count(value=2), refs=(REF,))


def printed(system: System) -> tuple[list[str], list]:
    """The lines the block prints and the must_fix findings of the validators, on the sample job with only this
    system."""
    job = replace(BASE_JOB, systems=(system,))
    lines = [line.text for line in render(job, PLAYBOOK).lines if line.system_key == system.key]
    return lines, [f for f in validate(job, PLAYBOOK) if f.severity == "must_fix" and f.system_key == system.key]


def test_an_exhaust_fan_prints_its_space_thermostat_and_points_with_no_controller_line():
    fans = System(key="EF", name="Exhaust Fans", shape="Exhaust Fan", control="field",
                  families=(Family("Exhaust Fan", ("EF-1", "EF-2"), Count(value=2)),),
                  devices=(device("EF.d1", "space_thermostat", "Space Thermostat"),
                           device("EF.d2", "start_stop_status", "Fan Start/Stop and Status", verb="Furnish"),
                           device("EF.d3", "vfd_control", "Fan VFD Control", verb="Furnish")))
    lines, must_fix = printed(fans)
    assert lines == ["Qty (2) Exhaust Fans EF-1, 2", "Furnish and Install Space Thermostat",
                     "Furnish Fan Start/Stop and Status", "Furnish Fan VFD Control"]
    assert must_fix == []


def test_a_vrf_block_prints_the_float_switch_tie_in_with_the_mfr_bracket():
    vrf = System(key="VRF", name="VRF Systems", shape="VRF System", control="integration",
                 families=(Family("VRF System", ("IDU-1", "IDU-2"), Count(value=2)),),
                 devices=(device("VRF.d1", "condensate_float_switch", "Condensate Pump Float Switch", verb="Wire",
                                 furnished="Unit Mfr.", installed="Unit Mfr."),))
    lines, must_fix = printed(vrf)
    assert FLOAT_SWITCH_LINE in lines
    assert not any("Mechanical Contractor" in line for line in lines) and must_fix == []


def test_a_vav_block_prints_the_factory_controller_and_the_power_loop_with_the_template_bracket():
    vav = System(key="VAV", name="VAV Boxes", shape="VAV / Fan VAV", control="field",
                 families=(Family("VAV Box", ("VAV-1", "VAV-2"), Count(value=2)),),
                 devices=(device("VAV.d1", "controller", "DDC Controller to the Factory for Installation",
                                 verb="Furnish", installed="Unit Mfr.", wired="Unit Mfr."),
                          device("VAV.d2", "power_loop", "24V Power Loop", verb="Wire")))
    lines, must_fix = printed(vav)
    assert lines == ["Qty (2) VAV Boxes VAV-1, 2", "Furnish DDC Controller to the Factory for Installation",
                     POWER_LOOP_LINE]
    assert must_fix == []


def test_a_misc_monitoring_block_still_prints_the_lighting_interface_line():
    misc = System(key="MM", name="Misc Monitoring Systems", shape="Misc Monitoring Systems", control="field",
                  families=(Family("Misc Monitoring", ("MM-1",), Count(value=1)),),
                  devices=(device("MM.d1", "lighting_interface", "Lighting Interface", verb="Wire"),))
    lines, must_fix = printed(misc)
    assert LIGHTING_LINE in lines and must_fix == []
