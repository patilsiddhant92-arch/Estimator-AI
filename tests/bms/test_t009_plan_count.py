"""T-009 task 1 (estimator ruling 21): a thermostat or space sensor that the plans draw prints the plan count as its
quantity, even when the sequence calls for more (one per unit). A "*Verify" line names the sheets and the other
number. Every job, sheet and number here is invented ("Invented Hall", `takeoff_fixture`)."""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest
import takeoff_fixture as fx
from test_takeoff import PLAYBOOK, _extended_ledger, _extended_register, _written

from bms import takeoff
from bms.model import Count, Decision, Device, Job, OtherCount, Ref
from bms.plan import plan_job
from bms.playbook import load_playbook
from bms.render import render
from bms.validate import validate

SEQUENCE = Ref("S1", "one thermostat per fan coil unit", "M-701, Mech.pdf page 10")
VERIFY = "*Verify: 30 thermostats drawn on M-201 and M-202; the sequence calls for one per fan coil unit (55)"
SENSOR = "FCU.d2"


@pytest.fixture(scope="module")
def planned(tmp_path_factory) -> Job:
    from bms.counts import cross_check

    job = plan_job(_extended_ledger(), fx.catalogue(), fx.dossier(), PLAYBOOK, register=_extended_register())
    job = takeoff.attach(job, _extended_register())
    job = takeoff.attach_device_set_asides(job, fx.reading().devices, fx.dossier().sheet_pages)
    job = takeoff.attach_demolition(job)
    return cross_check(job, fx.catalogue(), tmp_path_factory.mktemp("cache"))


def _sequence_writer(job: Job, quantity: Count | None = None) -> Job:
    """The stand-in writer of `test_takeoff._written`, with the space sensor line one per fan coil unit (55), the
    sequence as its source."""
    written = _written(job)
    quantity = quantity or Count(55, (SEQUENCE,))
    systems = []
    for system in written.systems:
        devices = tuple(dataclasses.replace(d, quantity=quantity, flag="none") if d.id == SENSOR else d
                        for d in system.devices)
        systems.append(dataclasses.replace(system, devices=devices))
    return dataclasses.replace(written, systems=tuple(systems))


def _step(job: Job, devices=None) -> Job:
    return takeoff.apply_plan_counts(job, fx.reading().devices if devices is None else devices,
                                     fx.dossier().sheet_pages)


def _line(job: Job, device_id: str = SENSOR) -> Device:
    return next(d for s in job.systems for d in s.devices if d.id == device_id)


def _fcu_notes(job: Job) -> list[str]:
    draft = render(job, PLAYBOOK)
    block = next(b for b in draft.scope.blocks if b.header.startswith("Qty (55) Fan Coil Unit"))
    return [i.runs[0].text for i in block.items if i.kind == "note"]


def _printed(job: Job, device_id: str = SENSOR):
    draft = render(job, PLAYBOOK)
    (line,) = [x for x in draft.lines if x.device_id == device_id]
    return line


# 1. the line and the "*Verify" line, the flag
def test_the_fan_coil_block_prints_the_plan_count_and_the_verify_line(planned):
    job = _step(_sequence_writer(planned))
    line = _printed(job)
    assert line.text == "Qty (30) Furnish and Install Space Temperature Sensor" and line.quantity == 30
    assert VERIFY in _fcu_notes(job)
    assert _line(job).flag == "quantity"


# 2. 30, not 39: the demolition sheet is not in the plan count and not in the line
def test_the_plan_count_is_thirty_and_the_demolition_sheet_is_not_named(planned):
    job = _step(_sequence_writer(planned))
    quantity = _line(job).quantity
    assert quantity.value == 30 and quantity.highest() == 30 and quantity.others == ()
    assert [r.where for r in quantity.sources] == ["M-201, Mech.pdf page 7", "M-202, Mech.pdf page 8"]
    assert all(r.source_id for r in quantity.sources)          # the dossier knows each sheet's text
    notes = _fcu_notes(job)
    assert not any("MD-201" in n or "39" in n for n in notes if n.startswith("*Verify"))
    assert "MD-201" not in _printed(job).text


def test_the_other_number_and_its_citation_stay_in_the_job_as_a_set_aside(planned):
    job = _step(_sequence_writer(planned))
    (aside,) = [a for a in job.set_aside if a.reason == "plan count prints"]
    assert (aside.family, aside.value, aside.ref) == (SENSOR, 55, SEQUENCE)
    assert aside.note == "55 not printed (M-701, Mech.pdf page 10); the plan count 30 of thermostats prints"
    # the demolition-sheet set-aside is still there beside it
    assert [(a.family, a.value, a.reason) for a in job.set_aside] == [("T", 9, "demolition sheet"),
                                                                       (SENSOR, 55, "plan count prints")]


# 3. the register's number is the number that prints
def test_the_register_text_number_is_the_number_that_prints(planned):
    job = _step(_sequence_writer(planned))
    text = takeoff.register_text(job, job.system("FCU"), _extended_ledger(), devices=fx.reading().devices)
    assert "Thermostats: 30 on the new-work sheets; 9 set aside (demolition sheet)" in text
    assert _printed(job).quantity == 30


# 4. no plan count: the highest prints, the bracket names the other counts, no Verify line
@pytest.mark.parametrize("devices", [
    (),
    tuple(dataclasses.replace(d, sheet="M-999", page=99) for d in fx.reading().devices),     # none on the block's areas
    tuple(dataclasses.replace(d, count=0, total=0) for d in fx.reading().devices),           # a plan count of 0
])
def test_no_plan_count_leaves_the_line_alone(planned, devices):
    other = OtherCount(40, Ref("S1", "one thermostat per fan coil unit", "M-601, Mech.pdf page 1"))
    job = _sequence_writer(planned, Count(55, (SEQUENCE,), (other,)))
    after = _step(job, devices)
    assert after == job
    line = _printed(after)
    assert line.quantity == 55 and "(55 per M-701; 40 per M-601)" in line.text
    assert not any(n.startswith("*Verify") for n in _fcu_notes(after))


# 5. a plan count that is not below another number
def test_a_plan_count_not_below_the_other_numbers_changes_nothing(planned):
    devices = tuple(dataclasses.replace(d, count=d.count * 2, total=d.total * 2) if d.sheet != "MD-201" else d
                    for d in fx.reading().devices)                       # 28 + 32 = 60, the sequence gives 55
    job = _sequence_writer(planned)
    after = _step(job, devices)
    assert after == job
    assert not any(n.startswith("*Verify") for n in _fcu_notes(after))
    assert _printed(after).quantity == 55


# 6. another kind of device keeps the highest-prints rule
def test_another_kind_of_device_prints_the_highest_count(planned):
    job = _sequence_writer(planned)
    extra = [Device("FCU.d3", "discharge_temperature", "Discharge Air Temperature Sensor", "Furnish and Install",
                    "AME", "AME", "AME", Count(55, (SEQUENCE,)), (SEQUENCE,)),
             Device("FCU.d4", "other_device", "Space Pressure Sensor", "Furnish and Install", "AME", "AME", "AME",
                    Count(55, (SEQUENCE,)), (SEQUENCE,))]
    system = job.system("FCU")
    job = job.with_system(dataclasses.replace(system, devices=(*system.devices, *extra)))
    after = _step(job)
    for device_id in ("FCU.d3", "FCU.d4"):
        assert _line(after, device_id) == _line(job, device_id)
        assert _line(after, device_id).quantity.highest() == 55
    assert _line(after).quantity.highest() == 30        # and the sensor line is the plan count


# 7. the kind detector
@pytest.mark.parametrize("name", ["Space Temperature Sensor", "Space Thermostat", "Zone Temperature Sensor",
                                  "Wall Mounted Room Thermostat", "Thermostat"])
def test_the_kind_detector_matches_thermostats_and_space_sensors(name):
    assert takeoff.is_plan_counted_kind(name, "other_device")


@pytest.mark.parametrize("name", ["Discharge Air Temperature Sensor", "Space Pressure Sensor",
                                  "Outside Air Humidity Sensor", "Space Temperature and Humidity Sensor",
                                  "Extend control wiring for relocated existing thermostat", "Return Air CO2 Sensor"])
def test_the_kind_detector_leaves_other_kinds_out(name):
    assert not takeoff.is_plan_counted_kind(name, "other_device")


@pytest.mark.parametrize("slot", ["space_sensor", "space_temperature", "space_thermostat", "thermostat",
                                  "alternate_thermostat", "mau_space_temperature", "remote_space_sensor",
                                  "bms_space_sensor"])
def test_the_kind_detector_takes_the_playbook_slots(slot):
    assert takeoff.is_plan_counted_kind("Sensor", slot)


def test_every_slot_of_the_detector_is_a_slot_of_the_playbook_shapes():
    shapes = json.loads((Path(__file__).resolve().parents[2] / "playbook" / "shapes.json").read_text("utf-8"))
    slots = {s for shape in shapes["shapes"] for s in shape["line_order"]}
    assert takeoff.PLAN_COUNT_SLOTS <= slots


def test_the_labels_come_from_the_data_file_and_leave_t_h_and_ts_out():
    labels = takeoff.plan_count_labels()
    assert labels == ("T", "TB")
    assert not {"TS", "T/H", "CO2"} & set(labels)


# 8. the validator does not ask for the 55 again
def test_the_validator_does_not_ask_for_the_sequence_number(planned):
    findings = validate(_step(_sequence_writer(planned)), PLAYBOOK)
    mine = [f for f in findings if f.device_id == SENSOR]      # (the stand-in writer's own wiring finding is not ours)
    assert not [f for f in mine if f.rule in ("Higher count prints", "Never undershoot")]
    assert not [f for f in mine if "highest" in f.what or "carries 30" in f.what or "quantity" in f.what]


# 9. idempotent, and it reads back from its JSON
def test_the_step_run_twice_gives_the_same_job_and_reads_back(planned):
    once = _step(_sequence_writer(planned))
    twice = _step(once)
    assert twice == once
    assert Job.from_json(once.to_json()) == once
    assert _step(Job.from_json(once.to_json())) == once


# 10. a typed count stays
def test_a_typed_count_keeps_the_count_the_estimator_typed(planned):
    once = _step(_sequence_writer(planned))
    typed = dataclasses.replace(_line(once), quantity=Count(33, (SEQUENCE,)))
    decision = Decision("FCU", "change", device_id=SENSOR, device=typed, was=_line(once))
    from bms.review import apply_decisions

    after = apply_decisions(once, [decision])
    assert _line(after).quantity.value == 33


def test_a_line_the_estimator_typed_is_skipped_by_name(planned):
    job = _sequence_writer(planned)
    after = takeoff.apply_plan_counts(job, fx.reading().devices, fx.dossier().sheet_pages,
                                      typed=frozenset({("FCU", SENSOR)}))
    assert after == job


# 11. a long sheet list prints as two lines, none over 160 characters, every sheet named
def test_a_plan_count_on_twelve_sheets_prints_as_two_short_star_lines(planned):
    rows = []
    sheets = []
    base = [s for s in planned.sheets if s.number == "M-201"][0]
    for n in range(12):
        number = f"M-3{n:02d}"
        sheets.append(dataclasses.replace(base, page=20 + n, number=number))
        rows.append(dataclasses.replace(fx.reading().devices[0], sheet=number, page=20 + n, count=3, total=3))
    job = _sequence_writer(planned)
    job = dataclasses.replace(job, sheets=(*job.sheets, *sheets))
    pages = dict(fx.dossier().sheet_pages)
    pages.update({f"S9{n:02d}": ("Mech.pdf", 20 + n) for n in range(12)})
    after = takeoff.apply_plan_counts(job, tuple(rows), pages)
    assert _line(after).quantity.value == 36
    verify = [n for n in _fcu_notes(after) if n.startswith("*Verify")]
    assert len(verify) == 2 and all(len(n) <= 160 for n in verify)
    text = " ".join(verify)
    assert all(f"M-3{n:02d}" in text for n in range(12))
    assert "the sequence calls for one per fan coil unit (55)" in text


# 12. the Playbook rule
def test_the_playbook_has_the_rule_in_counts_and_quantities():
    playbook = load_playbook(Path(__file__).resolve().parents[2] / "playbook")
    names = list(playbook.rules)
    name = "Thermostats drawn on plans print the plan count"
    assert playbook.rule(name).topic == "Counts and quantities"
    assert names.index(name) == names.index("Quantities print in the line") + 1
    assert "Higher count prints" in names and "Never undershoot" in names


def test_the_three_prompts_name_the_rule():
    root = Path(__file__).resolve().parents[2] / "src" / "bms" / "prompts"
    for name in ("write_system.md", "qc_job.md", "revise_system.md"):
        assert "Thermostats drawn on plans print the plan count" in (root / name).read_text("utf-8"), name


def test_the_run_calls_the_step_once_after_the_writers_and_before_the_decisions():
    source = (Path(__file__).resolve().parents[2] / "src" / "bms" / "run.py").read_text("utf-8")
    assert source.count("takeoff.apply_plan_counts(") == 1
    call = source.index("takeoff.apply_plan_counts(")
    assert source.index("ai.write_system(") < call < source.index("history = merge_decisions(")


def test_no_source_of_the_other_numbers_is_lost(planned):
    """Every number and every source that gives it stays as a set-aside (checklist 4): two sources of 55, a 40 and the
    sum ruling L1 left out."""
    second = Ref("S2", "one per unit", "M-601, Mech.pdf page 1")
    count = Count(55, (SEQUENCE, second), (OtherCount(40, second),), OtherCount(70, second))
    after = _step(_sequence_writer(planned, count))
    asides = [(a.value, a.ref) for a in after.set_aside if a.reason == "plan count prints"]
    assert asides == [(70, second), (55, SEQUENCE), (55, second), (40, second)]
    assert _line(after).quantity.others == () and _line(after).quantity.added_up is None
    (note,) = [n for n in _fcu_notes(after) if n.startswith("*Verify")]
    assert note == ("*Verify: 30 thermostats drawn on M-201 and M-202; 70 per M-601; "
                    "the sequence calls for one per fan coil unit (55); 40 per M-601")
