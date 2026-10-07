"""Integration: the rule names the validators and the AI prompts cite are the repo Playbook's, every validator check
can be reached, and every shape slot without a {verb} is a sub-line or house text that carries its own verb.

All jobs here are invented; the Playbook is the repo's own (`playbook/`)."""
from __future__ import annotations

from pathlib import Path

import pytest

from bms.model import Assumption, Clarification, Count, Device, Family, Job, OtherCount, Ref, System
from bms.playbook import load_playbook
from bms.validate import RULE, validate

ROOT = Path(__file__).resolve().parents[2]
PLAYBOOK = load_playbook()
REF = Ref("S1", "invented words", "M-1, Invented.pdf page 1")


def dev(id_: str, slot: str, name: str = "Invented Device", verb: str = "Furnish and Install", furnished="AME",
        installed="AME", wired="AME", qty: Count | None = None, refs=(REF,), **kw) -> Device:
    return Device(id=id_, slot=slot, name=name, verb=verb, furnished_by=furnished, installed_by=installed,
                  wired_by=wired, quantity=qty or Count(1, (REF,)), refs=refs, **kw)


def sysm(key: str, shape: str, devices=(), control="field", count: Count | None = None, family="Invented Unit",
         **kw) -> System:
    return System(key=key, name=f"Invented {shape}", shape=shape, control=control,
                  families=(Family(family, (f"{key}-1",), count or Count(1, (REF,))),), devices=tuple(devices), **kw)


def job(*systems: System) -> Job:
    return Job(name="Invented job", systems=systems)


# ---- the names ----------------------------------------------------------------------------------------------------

def test_every_validator_rule_name_is_a_repo_playbook_rule():
    missing = sorted(name for name in RULE.values() if name not in PLAYBOOK.rules)
    assert missing == []


def test_every_rule_name_the_ai_prompts_quote_is_a_repo_playbook_rule():
    """A quoted phrase in a prompt that starts with a capital and has a space is a rule citation."""
    from bms.playbook_lint import prompt_rule_names     # the one reading, shared with the Playbook linter
    quoted = prompt_rule_names(ROOT / "src" / "bms" / "prompts")
    assert quoted and sorted(q for q in quoted if q not in PLAYBOOK.rules) == []


def test_the_ai_citation_rule_is_a_repo_playbook_rule():
    from bms import ai
    assert ai._citation_rule(PLAYBOOK) == RULE["cites"]


# ---- every check can be reached -------------------------------------------------------------------------------------

def _cites():
    return job(sysm("EF", "Exhaust Fan", [dev("EF.d1", "controller", refs=(Ref("S1", " ", "M-1"),))]))


def _owner():
    return job(sysm("EF", "Exhaust Fan", [dev("EF.d1", "controller", furnished="Nobody")]))


def _slot():
    return job(sysm("EF", "Exhaust Fan", [dev("EF.d1", "no_such_slot")]))


def _subline():
    return job(sysm("GD", "Gas Detection", [dev("GD.d1", "sensor", name="Invented Sensor")]))


def _packaged():
    return job(sysm("RTU", "Packaged ERU / RTU / AHU", [dev("RTU.d1", "other_point", verb="Furnish")],
                    control="packaged"))


def _loose():
    # shipped loose (the unit manufacturer furnishes, AME installs) but not written Install and Wire (VAL-1)
    return job(sysm("RTU", "Packaged ERU / RTU / AHU",
                    [dev("RTU.d1", "shipped_loose", verb="Wire", furnished="Unit Mfr.")],
                    control="packaged"))


def _damper():
    # a damper in an untemplated block (no shape) beside a fan block; a Motorized Dampers block is allowed (VAL-3)
    return job(sysm("EF", "Exhaust Fan", [dev("EF.d1", "controller")], family="Exhaust Fan"),
               sysm("IU", "", [dev("IU.d1", "damper_actuator")]))


def _heater():
    return job(sysm("EF", "Exhaust Fan", [dev("EF.d1", "other_device", name="Duct Heater Enable")]),
               sysm("DH", "Duct Heater", [dev("DH.d1", "controller")], family="Duct Heater"))


def _vrf():
    return job(sysm("VRF", "VRF System", [dev("VRF.d1", "vrf_comm_wiring", verb="Wire"),
                                          dev("VRF.d2", "vrf_comm_wiring", verb="Wire")], family="Indoor Unit"))


def _higher():
    return job(sysm("EF", "Exhaust Fan", [dev("EF.d1", "controller")],
                    count=Count(1, (REF,), (OtherCount(3, REF),))))


def _unknown():
    return job(sysm("EF", "Exhaust Fan", [dev("EF.d1", "controller")], count=Count(None)))


def _one_note():
    return job(sysm("EF", "Exhaust Fan", [dev("EF.d1", "controller")],
                    clarifications=(Clarification("note", "One."), Clarification("confirm", "Two."))))


def _assumption():
    return job(sysm("EF", "Exhaust Fan", [dev("EF.d1", "controller", assumption=Assumption("one per fan", " "),
                                              flag="assumed")]))


def _sequence():
    # no source counts it, only the sequence names it, yet it prints a count (VAL-4)
    return job(sysm("IE", "Integrated Equipment", [], count=Count(2), sequence_refs=(REF,)))


def _once():
    return job(sysm("EF", "Exhaust Fan", [dev("EF.d1", "controller")]),
               sysm("TEF", "Toilet Exhaust Fan", [dev("EF.d1", "other_device")]))


def _left_out():
    return job(sysm("EF", "Exhaust Fan", []))


def _ids():
    return job(sysm("EF", "Exhaust Fan", [dev("EF.d1", "controller", assumption=Assumption("one", "S1 says so"))]))


def _long_note():
    return job(sysm("EF", "Exhaust Fan", [dev("EF.d1", "controller")],
                    clarifications=(Clarification("note", "invented " * 30),)))


def _long_assumption():
    return job(sysm("EF", "Exhaust Fan", [dev("EF.d1", "controller",
                                              assumption=Assumption("invented " * 15, "invented " * 15))]))


def _header_under():
    return job(sysm("EF", "Exhaust Fan", [dev("EF.d1", "controller", qty=Count(4, (REF,)))]))


TRIGGERS = {"cites": _cites, "owner": _owner, "slot": _slot, "subline": _subline, "packaged": _packaged,
            "loose": _loose, "damper": _damper, "heater": _heater, "vrf": _vrf, "higher": _higher,
            "unknown": _unknown, "one_note": _one_note, "assumption": _assumption, "sequence": _sequence,
            "once": _once, "left_out": _left_out, "ids": _ids, "long_note": _long_note,
            "long_assumption": _long_assumption, "header_under": _header_under}


def test_every_check_has_a_trigger():
    assert set(TRIGGERS) == set(RULE)


@pytest.mark.parametrize("check", sorted(TRIGGERS))
def test_every_check_is_reachable_with_the_repo_playbook(check):
    found = validate(TRIGGERS[check](), PLAYBOOK)
    assert RULE[check] in {f.rule for f in found}, [f.rule for f in found]


def test_a_subline_with_its_parent_is_clean():
    clean = job(sysm("GD", "Gas Detection", [dev("GD.d1", "panel", name="Gas Detection Panel"),
                                            dev("GD.d2", "sensor", name="Invented Sensor")]))
    assert RULE["subline"] not in {f.rule for f in validate(clean, PLAYBOOK)}


# ---- sub-lines: every slot without a {verb} -------------------------------------------------------------------------

# House text that carries its own verb (Interlock, Tie-in, Map, Monitor, a wiring phrase, a work statement), the
# wordings a slot with no {verb} and no "under" may have.
OWN_VERB_TEXT = {
    "Run 24V Power Loop to VAVs",
    "Interlock with {device}{owner}",
    "Interlock with Associated {device} Operation",
    "Interlock wiring to {device}{owner}",
    "Interlock wiring b/w {device}",
    "Interlock w/ {device}{owner}",
    "Interlock Fan Operation with {device}",
    "Low Voltage Control Interlock w/ {device}",
    "Tie-in {device}{owner}",
    "Tie in Mfr. {device}",
    "Tie into BMS",
    "Tie-in mfr. Provided Sensors and End-Devices via Terminal Strip",
    "Map Available Points Via Mfr. Provided BMS Interface",
    "Map Available Points Via Mfr. Provided BMS Interface or Connect to Nearby DDC Controller",
    "Monitor the following Alarms",
    "Demo and safe-off existing control wiring prior to relocation of unit",
    "Extend control wiring for relocated existing thermostat",
    "Extend communication bus to new unit location",
    "Re-commission unit to ensure proper operation",
    "Necessary Low Voltage Interlock Wiring",
    "Low Voltage Interlock with Associated Unit Fan Starter",
    "Necessary Control Wiring w/ Mfr. Provided Terminal Strip",
    "Condenser Interlock Wiring",
    "Boiler Trim Wiring",
    "Necessary Low Voltage Control Wiring Mfr. Provided Controls",
    "Necessary Control Wiring to / from Fuel Oil Management Panel",
    "Interface Lighting Control System (By Others) With Front End BMS Via Manufacturer Provided BMS Interface",
    "VRF Communication Wiring",
    "Low Voltage Interlock Wiring between Indoor and Outdoor Unit",
}
# Slots whose device name is the whole line, printed at the first level with no verb as the Master Template prints
# them: a plain work statement (rule "Miscellaneous responsibilities": its name carries its verb), a monitored item,
# and the Refrigeration Monitoring devices (depth 1 in assets/system_templates.json).
NAME_IS_THE_LINE = {
    ("*", "other_wiring"),
    ("Misc Monitoring Systems", "monitored_item"),
    ("Refrigeration Monitoring System", "horn_strobe"),
    ("Refrigeration Monitoring System", "pull_station"),
    ("Refrigeration Monitoring System", "remote_sensor"),
}


def _unexplained():
    for shape in PLAYBOOK.shapes.values():
        for slot in shape.line_order:
            wording = shape.wording[slot]
            if "{verb}" in wording or slot in shape.under or wording in OWN_VERB_TEXT:
                continue
            if ("*", slot) in NAME_IS_THE_LINE or (shape.name, slot) in NAME_IS_THE_LINE:
                continue
            yield shape.name, slot, wording


def test_every_slot_has_a_verb_or_a_parent_or_carries_its_own_verb():
    assert list(_unexplained()) == []


def test_sub_lines_follow_the_master_template_depth():
    """Every slot set "under" a parent has no {verb}; the named sub-lines of the controller ruling are all set."""
    for shape in PLAYBOOK.shapes.values():
        for slot, parent in shape.under.items():
            assert "{verb}" not in shape.wording[slot], (shape.name, slot)
            assert shape.line_order.index(parent) < shape.line_order.index(slot)
    want = {("Gas Detection", "sensor"): "panel", ("Gas Detection", "horn_strobe"): "panel",
            ("HVAC Alarm Panel w/ Auto Dialer", "monitored_alarm"): "monitor_heading",
            ("Unit Ventilators", "terminal_strip_device"): "terminal_strip_tie_in",
            ("Misc Monitoring Systems", "monitored_detail"): "monitored_item",
            ("Misc Monitoring Systems", "meter_comm_wiring"): "meter"}
    for (name, slot), parent in want.items():
        assert PLAYBOOK.shape(name).under.get(slot) == parent
    for shape in PLAYBOOK.shapes.values():
        if "rep_assist" in shape.line_order and "map_points" in shape.line_order:
            assert shape.under.get("rep_assist") == "map_points", shape.name


def test_the_loader_rejects_a_bad_under(tmp_path):
    import json
    import shutil
    from bms.playbook import PlaybookError
    sample = ROOT / "tests" / "bms" / "fixtures" / "sample_playbook"
    for name in ("rules.md", "wording.json"):
        shutil.copy(sample / name, tmp_path / name)
    data = json.loads((sample / "shapes.json").read_text(encoding="utf-8"))
    data["shapes"][0]["under"] = {"map_points": "rep_assist"}          # the parent after the sub-line
    (tmp_path / "shapes.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(PlaybookError, match="must come before"):
        load_playbook(tmp_path)
    data["shapes"][0]["under"] = {"nowhere": "map_points"}
    (tmp_path / "shapes.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(PlaybookError, match="not in line_order"):
        load_playbook(tmp_path)


def test_vrf_communication_wiring_and_the_trio_comm_line_are_two_lines_not_a_repeat():
    vrf = job(sysm("VRF", "VRF System", [dev("VRF.d1", "vrf_comm_wiring", verb="Wire"),
                                         dev("VRF.d2", "comm_wiring", verb="Furnish"),
                                         dev("VRF.d3", "map_points", verb="Furnish")], family="Indoor Unit"))
    assert RULE["vrf"] not in {f.rule for f in validate(vrf, PLAYBOOK) if f.severity == "must_fix"}
