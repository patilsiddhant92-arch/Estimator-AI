"""The Playbook rulings of 2026-10-11 (1 to 19, approved by the estimator): the new rules, the changed sentences and
the two pump shapes. The repo Playbook (`playbook/`) and invented systems only. No job data."""
from __future__ import annotations

import json
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


def plain(text: str) -> str:
    """A rule's text on one line."""
    return " ".join(text.split())


# ---- the rules the rulings add or change: (ruling, rule, its topic, the sentences of its text) --------------------

RULINGS = [
    (2, "One unit on two part plans counts once", "Counts and quantities",
     ('Count it once. The other labels are duplicates of the same unit. A short "*" line gives both numbers.',)),
    (3, "Proposal header", "Shapes and wording",
     ('"Quote #" is the job number and "Reference" is the project name, both from the name of the job folder, never '
      'the takeoff folder.', 'When the job folder gives no project name, print "***" in red and ask the estimator.')),
    (4, "Existing BMS the house works with", "Front end",
     ("AME works only with Honeywell WEBS, Johnson FX and Niagara Tridium. Those names print plain.",
      'Any other name prints in red as "***<name>***" wherever it appears')),
    (4, "No front end called for", "Front end",
     ('When the documents call for no front end, the front end of the proposal says "No front end information '
      'found".',)),
    (6, "A stated fact is not an assumption", "Clarifications and assumptions",
     ('write it as stated and cite it. Never print "Assumed" for it.',)),
    (7, "Red flags for the estimator", "Clarifications and assumptions",
     ('then "(FUTURE AS PER <source>)" in red font, naming the sheet or section.',
      "Red marks what the estimator must see.")),
    (8, "Valves under their unit", "Shapes and wording",
     ("never in a separate valve system. The plans, risers and sequence show which unit.",)),
    (8, "One system one block", "Shapes and wording",
     ("except as the VRF and split rule, the dampers rules and the valves rule say.",)),
    (10, "Shipped-loose devices", "Shipped-loose devices",
     ("A unit schedule (an ERV, an RTU or any other unit) can list end devices shipped loose, in a column or a note. "
      "Read it, and write each one as a line.",)),
    (11, "Questions for the estimator", "Clarifications and assumptions",
     ("A question is asked once. A question that holds for a whole family is asked once for the family, never per "
      "unit or per line.",)),
    (12, "Off-hours work and prevailing wage", "Exceptions and alternates",
     ("add each to the proposal and to the price sheet, highlighted red. Never exclude either one silently.",
      'The standard exclusion "All off-hours or overtime labor" does not stand against it.')),
    (14, "One clarification per block", "Clarifications and assumptions",
     ('Each "*" line is one short line, never a paragraph.',
      'Several "*" lines in one block are fine when each is a different item.',
      'A "*" line that the estimator must see prints in red.')),
    (15, "Quantities print in the line", "Counts and quantities",
     ('The block heading keeps "Qty (n) <system>".',
      'A device line ends with "(Qty. N Total)" when its count is known and differs from the block count, or when '
      'the line carries a note (ruling 24), for example "Furnish and Install Space Temperature Sensor (Qty. 33 '
      'Total)".',
      'There is no separate quantity note.')),
    (15, "Never undershoot", "Counts and quantities",
     ('An unknown count prints "Qty (##)" in a header, and "(Qty. ##)" at the end of a device line (ruling 24), '
      'flagged to confirm.',)),
    (15, "Line quantity", "Counts and quantities",
     ('at the end of the line (ruling 24), as "<device line> (Qty. N Total)", when the count is known and differs '
      'from the block\'s count, or when the line carries a note. When the count equals the block\'s count and the '
      'line carries no note, the line has no quantity words.',
      'one line with the total ("Furnish Chiller Enable (Qty. 6 Total)"), never one line per tag.')),
    (15, "Line form", "Shapes and wording",
     ('ends with "(Qty. N Total)" (ruling 24; see Line quantity).',
      'Details go after the device in brackets: the owner, "(as per sequence)", "(Location: ...)".')),
    (15, "Untemplated systems", "Shapes and wording",
     ('in the house form "<verb> <device><owner> (Qty. N Total)" (the quantity at the end, ruling 24, see Line '
      'quantity)',)),
    (15, "Higher count prints", "Counts and quantities",
     ("Every count that differs from the printed one prints in the same line (see Quantities print in the line).",)),
    (16, "Tech hours never print", "Tech hours",
     ('The Master Template\'s tech-hour lines ("**tech hour: ...") are guidance for the estimate, not lines of the '
      'proposal.',)),
    (17, "Demolition Scope", "Counts and quantities",
     ("Their count never goes into the new-work blocks.",
      'It prints in one block headed "Demolition Scope", the last block of the scope')),
    (17, "Never undershoot", "Counts and quantities",
     ("The only exceptions, here and in Higher count prints, are the units on demolition sheets, whose count moves "
      'to Demolition Scope with its number, and a duplicate label of one unit on two part plans, which a short "*" '
      'line names with both numbers.',)),
    (18, "Pumps by plant or by service", "Shapes and wording",
     ("the pumps are part of the plant block.",
      "each service is its own block: chilled water pumps in one, hot water pumps in another.")),
    (19, "Front end lines cite the specification", "Front end",
     ("The house front end lines are the standard lines that the Master Template's front end section defines, with "
      "the reason for each.",
      "Every other front end line (PC workstation, BMS server, portable operator terminal, UPS, IT infrastructure) "
      "is written only when this job's specification calls for it, with its citation.")),
    (19, "No standard or fallback lines", "Evidence and citations",
     ("The front end house lines are the one exception.",)),
    (19, "Template gives shape only", "Shapes and wording", ("The front end house lines are the one exception.",)),
]


@pytest.mark.parametrize("ruling, name, topic, sentences", RULINGS, ids=[f"{n}: {r}" for n, r, _, _ in RULINGS])
def test_the_ruling_text_loads_under_the_rule_name(ruling, name, topic, sentences):
    rule = PLAYBOOK.rule(name)
    assert rule.topic == topic
    assert [s for s in sentences if s not in plain(rule.text)] == []


def test_ruling_24_names_the_end_form_on_the_device_line_rules():
    holding = [n for n, rule in PLAYBOOK.rules.items()
               if "(Qty. N Total)" in plain(rule.text) or "(Qty. ##)" in plain(rule.text)]
    assert holding == ["Never undershoot", "Line quantity", "Quantities print in the line", "Line form",
                       "Untemplated systems"]
    assert all("ruling 24" in plain(PLAYBOOK.rule(name).text) for name in holding)
    assert not any("never used" in plain(rule.text) for rule in PLAYBOOK.rules.values())


def test_the_separate_quantity_note_is_gone_from_every_rule_but_the_one_that_says_there_is_none():
    assert [n for n, rule in PLAYBOOK.rules.items() if "quantity note" in plain(rule.text)] == [
        "Quantities print in the line"]


# ---- ruling 18: the pump shapes for remote pumps; the plant shapes keep their pump slots ---------------------------

PUMPS = [       # (plant shape, its pump-only shape, the pump slots, a slot only the plant has)
    ("Chilled Water System", "Chilled Water Pumps",
     ("pump_start_stop", "pump_vfd_control", "pump_vfd_feedback", "pump_vfd_alarm"), "chiller_enable"),
    ("Hot Water System", "Hot Water Pumps", ("hw_pump_start_stop", "hw_pump_vfd"), "boiler_enable"),
]


@pytest.mark.parametrize("plant, pumps, pump_slots, plant_slot", PUMPS, ids=[p[1] for p in PUMPS])
def test_a_pump_only_shape_beside_the_plant_shape_that_keeps_its_pump_slots(plant, pumps, pump_slots, plant_slot):
    plant_shape, pump_shape = PLAYBOOK.shape(plant), PLAYBOOK.shape(pumps)
    assert set(pump_slots) <= set(plant_shape.line_order) and plant_slot in plant_shape.line_order
    assert pump_shape.line_order[:len(pump_slots)] == pump_slots and plant_slot not in pump_shape.line_order
    assert pump_shape.tech_hours == plant_shape.tech_hours and pump_shape.header == plant_shape.header
    assert pump_shape.prefixes == ()        # each prefix names one shape: the plant keeps CHWP, PCHWP, SCHWP, HWP


def test_remote_pumps_are_picked_by_name_and_a_plant_prefix_still_picks_the_plant_shape():
    def pick(kind, prefixes):
        return PLAYBOOK.shape_for(kind, prefixes).name

    assert pick("Chilled Water Pumps", ["P"]) == "Chilled Water Pumps"
    assert pick("Hot Water Pump", []) == "Hot Water Pumps"
    assert pick("Chilled Water Pumps", ["CHWP"]) == "Chilled Water System"
    assert pick("Hot Water Pumps", ["HWP"]) == "Hot Water System"


def _pump_device(id_: str, slot: str, name: str) -> Device:
    return Device(id=id_, slot=slot, name=name, verb="Furnish", furnished_by="AME", installed_by="AME", wired_by="AME",
                  quantity=Count(value=2), refs=(REF,))


@pytest.mark.parametrize("shape, key, tags, slots, header", [
    ("Chilled Water Pumps", "CHP", ("P-1", "P-2"), ("pump_start_stop", "pump_vfd_control"),
     "Qty (2) Chilled Water Pumps P-1, 2"),
    ("Hot Water Pumps", "HWP", ("P-3", "P-4"), ("hw_pump_start_stop", "hw_pump_vfd"), "Qty (2) Hot Water Pumps P-3, 4"),
])
def test_a_remote_pump_block_prints_its_pump_lines_and_passes_the_validators(shape, key, tags, slots, header):
    system = System(key=key, name=shape, shape=shape, control="field",
                    families=(Family(shape.removesuffix("s"), tags, Count(value=2)),),
                    devices=(_pump_device(f"{key}.d1", slots[0], "Pump Start/Stop"),
                             _pump_device(f"{key}.d2", slots[1], "Pump VFD Speed Control")))
    job = replace(BASE_JOB, systems=(system,))
    lines = [line.text for line in render(job, PLAYBOOK).lines if line.system_key == key]
    assert lines == [header, "Furnish Pump Start/Stop", "Furnish Pump VFD Speed Control"]
    assert [f for f in validate(job, PLAYBOOK) if f.severity == "must_fix" and f.system_key == key] == []
