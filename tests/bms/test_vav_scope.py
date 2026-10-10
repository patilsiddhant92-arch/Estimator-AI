"""VAV boxes are field DDC: a factory-installed controller note is AME's DDC controller furnished to the factory,
never the integration lines; the box block prints the Master Template's lines and takes 3 tech hours per
cooling-only box, 4 per hot water reheat box. Every job here is invented; the Playbook is the repo's own."""
from __future__ import annotations

import copy
from pathlib import Path

from estimator.ledger.facts import SETTLED, Ledger
from estimator.writing.dossier import Dossier

from bms import ai
from bms.citations import SourceIds
from bms.model import Count, Device, Family, Job, Ref, System
from bms.plan import plan_job
from bms.playbook import load_playbook
from bms.render import printed_texts
from bms.validate import validate

PLAYBOOK = load_playbook()                      # the repo's playbook/
VAV_SHAPE = "VAV / Fan VAV"
REF = Ref("S3", "invented words", "M-501, Drawings.pdf page 6")

SOURCES = {
    "S3": "M-501, Drawings.pdf page 6 (schedule)",
    "S4": "23 09 00, Specs.pdf page 4",
}
FACTORY_NOTE = "boxes shipped with factory-installed open protocol controller card interfaced to the local control panel"


# ---- the planner: control class of a VAV block ----------------------------------------------------------------

def _ledger(*providers: str, prefix="VAV", name="Variable Air Volume Box", tags="VAV-1 thru 15", count=15) -> Ledger:
    ledger = Ledger(SOURCES)
    ledger.job_name = "Invented Job"
    ledger.add("front_end", "mode", "new-system", "S4", "provide a new building automation system", "spec", SETTLED)
    ledger.add("family", prefix, name, "S3", f"{prefix} {name}", "schedules", SETTLED)
    ledger.add("unit", prefix, tags, "S3", f"Tags: {tags}", "schedules", SETTLED)
    ledger.add("count", prefix, count, "S3", f"{prefix} rows {count}", "schedules", SETTLED)
    for text in providers:
        ledger.add("provider", prefix, text, "S3", text, "schedules", SETTLED)
    return ledger


def _plan(ledger: Ledger) -> Job:
    dossier = Dossier(job_name="Invented Job", text="", images=(), sources={}, families=(), device_totals={},
                      counts={}, stats={})
    return plan_job(ledger, None, dossier, PLAYBOOK)


def _vav(job: Job) -> System:
    (system,) = [s for s in job.systems if s.shape == VAV_SHAPE]
    return system


def test_a_factory_installed_controller_note_keeps_the_vav_block_field_ddc():
    job = _plan(_ledger(FACTORY_NOTE))
    vav = _vav(job)
    assert vav.control == "field"
    assert not any("VAV" in q and "manufacturer" in q for q in job.questions)


def test_factory_and_packaged_words_alone_never_make_a_vav_packaged():
    for words in ("factory mounted controls", "packaged with the unit", "factory furnished and installed DDC controller",
                  "the ATC contractor shall furnish DDC controllers to the VAV manufacturer for factory mounting"):
        assert _vav(_plan(_ledger(words))).control == "field", words


def test_a_fan_powered_box_with_a_factory_note_is_field_ddc_too():
    job = _plan(_ledger(FACTORY_NOTE, prefix="FPB", name="Fan Powered Box", tags="FPB-1 thru 4", count=4))
    assert _vav(job).control == "field"


def test_vav_controls_by_the_manufacturer_integrated_to_the_bms_are_packaged():
    job = _plan(_ledger("VAV controls furnished by the VAV manufacturer, integrated to the BMS via BACnet"))
    assert _vav(job).control == "packaged"


def test_vav_controls_by_the_manufacturer_with_no_integration_stay_field_and_ask():
    job = _plan(_ledger("controls by the unit mfr"))
    vav = _vav(job)
    assert vav.control == "field"
    (question,) = [q for q in job.questions if "VAV box controls" in q]
    assert "M-501" in question and "integrat" in question


def test_vav_controls_by_the_manufacturer_beside_an_ame_controller_sentence_ask():
    job = _plan(_ledger("VAV controls by the box manufacturer with BACnet interface",
                        "DDC controllers furnished by the ATC contractor"))
    assert _vav(job).control == "field"
    assert any("VAV box controls" in q and "controls contractor" in q for q in job.questions)


def test_a_rooftop_unit_on_factory_controls_is_still_packaged():
    job = _plan(_ledger("factory controls by the unit manufacturer", prefix="RTU", name="Rooftop Unit",
                        tags="RTU-1", count=1))
    (rtu,) = job.systems
    assert rtu.control == "packaged"


# ---- the shape: the Master Template's lines, word for word -------------------------------------------------------

def test_the_vav_shape_prints_the_master_template_lines_in_order():
    shape = PLAYBOOK.shapes[VAV_SHAPE]
    assert shape.line_order[:10] == ("controller", "space_sensor", "fan_enable", "discharge_temperature",
                                     "hot_water_valve", "electric_heat_enable", "electric_heat_scr", "power_loop",
                                     "transformer", "transformer_with_unit")
    assert shape.wording["controller"] == "Furnish DDC Controller to the Factory for Installation{qty}"
    assert shape.wording["power_loop"] == "Run 24V Power Loop to VAVs"
    assert shape.wording["transformer_with_unit"] == "24V VAV Transformer is Coming with the Unit"
    assert shape.wording["other_interlock"] == "Interlock with {device}{owner}"


def _dev(n, slot, name, verb="Furnish and Install", furnished="AME", installed="AME", wired="AME", qty=None):
    return Device(id=f"VAV.d{n}", slot=slot, name=name, verb=verb, furnished_by=furnished, installed_by=installed,
                  wired_by=wired, quantity=qty or Count(15, (REF,)), refs=(REF,))


def _cooling_only(hours=None) -> System:
    devices = (
        _dev(1, "controller", "Open Protocol Controller Card", verb="Furnish", installed="Unit Mfr.",
             wired="Unit Mfr."),
        _dev(2, "space_sensor", "Space Temperature Sensor", qty=Count(12, (REF,))),
        _dev(3, "space_sensor", "Space Temperature / CO2 Sensor", qty=Count(3, (REF,))),
        _dev(4, "power_loop", "24V Power Loop", verb="Wire", furnished="Electrical Contractor",
             installed="Electrical Contractor"),
        _dev(5, "transformer_with_unit", "24V VAV Transformer", verb="Wire",
             furnished="Unit Mfr.", installed="Unit Mfr.", wired="Unit Mfr."),
        _dev(6, "other_interlock", "Radiator Control Valves", verb="Wire", furnished="Others", installed="Others"),
    )
    return System(key="VAV", name="Variable Air Volume Box", shape=VAV_SHAPE, control="field",
                  families=(Family("Variable Air Volume Box", tuple(f"VAV-{i}" for i in range(1, 16)),
                                   Count(15, (REF,))),),
                  devices=devices, tech_hours=hours)


def test_a_cooling_only_vav_block_prints_the_ddc_lines_and_no_integration_line():
    system = _cooling_only()
    texts = [t for _, t in printed_texts(system, PLAYBOOK.shapes[VAV_SHAPE], PLAYBOOK, SourceIds.of(["S3"]))]
    assert texts == ["Furnish DDC Controller to the Factory for Installation",
                     "Furnish and Install Space Temperature Sensor (Qty. 12 Total)",
                     "Furnish and Install Space Temperature / CO2 Sensor (Qty. 3 Total)",
                     "Run 24V Power Loop to VAVs",
                     "24V VAV Transformer is Coming with the Unit",
                     "Interlock with Radiator Control Valves (Furnished by Others)"]
    assert not any("Map Available Points" in t or "Communication Wiring" in t for t in texts)
    must_fix = [f for f in validate(Job(name="Invented job", systems=(system,)), PLAYBOOK) if f.severity == "must_fix"]
    assert must_fix == []


# ---- tech hours: 3 per cooling-only box, 4 per hot water reheat box --------------------------------------------

def _rule_hours(system: System) -> float:
    """The VAV shape's tech hours rule applied to a block: hours per unit, the last condition whose slots are all
    filled winning."""
    rule = PLAYBOOK.shapes[system.shape].tech_hours
    assert rule.per == "unit"
    filled = {d.slot for d in system.devices}
    hours = rule.hours
    for slots, when in rule.when:
        if set(slots) <= filled:
            hours = when
    return hours * sum(f.count.value for f in system.families)


def test_a_cooling_only_vav_takes_3_hours_per_box():
    assert _rule_hours(_cooling_only()) == 45


def test_a_hot_water_reheat_vav_takes_4_hours_per_box():
    system = _cooling_only()
    reheat = System(**{**system.__dict__, "devices": system.devices + (
        _dev(7, "discharge_temperature", "Discharge Air Temperature Sensor"),
        _dev(8, "hot_water_valve", "Hot Water Control Valve and Actuator", verb="Furnish and Wire",
             installed="Mechanical Contractor"))})
    assert _rule_hours(reheat) == 60
    texts = [t for _, t in printed_texts(reheat, PLAYBOOK.shapes[VAV_SHAPE], PLAYBOOK, SourceIds.of(["S3"]))]
    assert texts[3:5] == ["Furnish and Install Discharge Air Temperature Sensor",
                          "Furnish and Wire Hot Water Control Valve and Actuator"]


# ---- the writer is told the VAV rules and the hours rule --------------------------------------------------------

class _Transport:
    def __init__(self, answer):
        self.answer, self.asked = answer, []

    def ask(self, kind, name, instructions, system_prompt, prompt, schema, extra=None, images=()):
        self.asked.append(dict(instructions=instructions, system_prompt=system_prompt, prompt=prompt))
        return copy.deepcopy(self.answer)


def test_the_writer_of_a_factory_note_vav_is_told_ddc_to_the_factory_and_3_hours_a_box():
    skeleton = _vav(_plan(_ledger(FACTORY_NOTE)))
    assert skeleton.control == "field"
    evidence = (f"[S3] VAV rows 15. VAV schedule note: {FACTORY_NOTE}. (M-501, Drawings.pdf page 6)\n"
                "[S4] Each VAV box shall maintain the space temperature setpoint. (23 09 00, Specs.pdf page 4)\n")
    ref = {"source_id": "S3", "quote": "factory-installed open protocol controller card", "where": "M-501"}
    count = skeleton.families[0].count.to_dict()
    answer = {**skeleton.to_dict(), "tech_hours": 45, "clarifications": [], "no_scope_reason": None, "devices": [
        {"id": "VAV.d1", "slot": "controller", "name": "Open Protocol Controller Card", "verb": "Furnish",
         "furnished_by": "AME", "installed_by": "Unit Mfr.", "wired_by": "Unit Mfr.", "quantity": count,
         "refs": [ref], "flag": "none", "assumption": None},
        {"id": "VAV.d2", "slot": "space_sensor", "name": "Space Temperature Sensor", "verb": "Furnish and Install",
         "furnished_by": "AME", "installed_by": "AME", "wired_by": "AME", "quantity": count,
         "refs": [{"source_id": "S4", "quote": "maintain the space temperature setpoint", "where": "23 09 00"}],
         "flag": "none", "assumption": None}]}
    transport = _Transport(answer)
    written = ai.write_system(skeleton, evidence, PLAYBOOK, transport)
    (asked,) = transport.asked
    prompt = asked["prompt"]
    assert "Furnish DDC Controller to the Factory for Installation" in prompt
    assert "3 hours per unit; 4 hours when the block has a device in each of: hot_water_valve" in prompt
    assert "### VAV boxes are field DDC" in asked["instructions"]
    assert "never the integration lines" in asked["system_prompt"]
    assert written.control == "field" and written.tech_hours == 45
    assert [d.slot for d in written.devices] == ["controller", "space_sensor"]
