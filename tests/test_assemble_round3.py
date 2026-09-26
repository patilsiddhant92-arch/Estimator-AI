"""Round 3 fixes, Part A (.superpowers/sdd/2026-09-26-whole-job-writing/round3-fixes.md): folded units,
dedupe after merging, the house order, tech hours by the nearest template, line totals and the review list
in plain words."""
from __future__ import annotations

import re

from estimator.price_sheet.write import check_fit
from estimator.reading.inventory import FamilyTotal
from estimator.writing.assemble import assemble_job, plan_checks, review_list, tech_hours
from estimator.writing.judge import TechHoursHint
from estimator.writing.write import ReviewItem
from test_assemble import (JOB_READING, READING, SOURCES, TEMPLATES, TODAY, VAV_LINES, JobPlan, PlannedSystem,
                           WrittenLine, WrittenScope, _assemble, _dossier, _headers, _job_catalogue, _vav)


def _system(key, header, tags=(), quantity=1, **kw):
    values = dict(kind=kw.pop("kind", header.split(" ")[0]), tags=tuple(tags), quantity=quantity,
                  quantity_source="S9", quantity_quote="Job 26-9999", sequence_sources=("S9",))
    values.update(kw)
    return PlannedSystem(key, header, **values)


def _line(text, quote="Job 26-9999", sid="S9", **kw):
    return WrittenLine(text, quote=quote, source_id=sid, **kw)


def _block(job, word):
    return next(b for b in job.blocks if word in b.header)


def _texts(block):
    return [i.text for i in block.items]


# --- 1. folded units ------------------------------------------------------------------------------------------

ERV_TAGS = ("ERV-1", "ERV-2", "ERV-3", "EDH-1", "EDH-2", "EDH-3")
ERV_HEADER = "Energy Recovery Ventilator ERV-1 thru 3 w/ Electric Duct Heater EDH-1 thru 3"
FOLD_FAMILIES = (FamilyTotal("Energy Recovery Ventilator", "ERV", 3, "ERV-1 thru ERV-3", ()),
                 FamilyTotal("Electric Duct Heater", "EDH", 3, "EDH-1 thru EDH-3", ()))
FOLD_COUNTS = {"ERV": {"schedule_rows": 3, "quantity_column": None, "plan_placements": 3, "riser": None,
                       "distinct_tags": 3},
               "EDH": {"schedule_rows": 3, "quantity_column": None, "plan_placements": 0, "riser": None,
                       "distinct_tags": 3}}


def _fold_dossier():
    return _dossier(families=FOLD_FAMILIES, counts=FOLD_COUNTS)


def test_folded_units_are_not_counted_toward_the_parents_quantity():
    erv = _system("ERV", ERV_HEADER, ERV_TAGS, 3, kind="Energy Recovery Ventilator")
    [check], _ = plan_checks(JobPlan((erv,)), _fold_dossier(), READING)
    assert check.category == "CONFIRMED"
    assert 6 not in check.counts.values()


def _fold_job(lines):
    erv = _system("ERV", ERV_HEADER, ERV_TAGS, 3, kind="Energy Recovery Ventilator")
    plan = JobPlan((erv,))
    return assemble_job(_job_catalogue(), JOB_READING, _fold_dossier(), plan, {"ERV": WrittenScope(lines)}, TODAY,
                        TEMPLATES)


def test_folded_units_get_their_own_stacked_header_with_the_lines_the_judge_wrote():
    lines = (_line("Install and wire Discharge Air Temperature Sensor (Furnished by Unit Mfr.)"),
             _line("Furnish and Install DDC Controller for Electric Duct Heater EDH-1 thru 3"))
    job, systems, _ = _fold_job(lines)
    check_fit(job)
    assert _headers(job) == ["Qty (3) Energy Recovery Ventilator ERV-1 thru 3", "Qty (3) Electric Duct Heater EDH-1 thru 3"]
    assert job.blocks[1].joined
    texts = [i.text for b in job.blocks for i in b.items]
    assert not any(t.startswith("**Includes") for t in texts)
    written = next(s for s in systems if s.bundle_key == "ERV")
    assert not any(line.category == "ASSUMPTION" for line in written.lines)


def test_folded_units_with_no_line_of_their_own_get_the_nearest_templates_lines_as_assumptions():
    job, systems, _ = _fold_job((_line("Install and wire Discharge Air Temperature Sensor (Furnished by Unit Mfr.)"),))
    assert _headers(job)[1] == "Qty (3) Electric Duct Heater EDH-1 thru 3"
    written = next(s for s in systems if s.bundle_key == "ERV")
    added = [line for line in written.lines if line.category == "ASSUMPTION"]
    assert added and all(line.quantity == 3 for line in added)
    assert any("Electric Duct Heater" in r.decide for r in written.review)


# --- 2. dedupe after merging, and the house order ----------------------------------------------------------------

def test_near_duplicate_lines_with_the_same_verb_are_one_line_keeping_the_best_evidence():
    lines = VAV_LINES + (
        WrittenLine("Furnish and Install Discharge Air Temperature Sensor (Location: Each Box)", quote="not in there"),
        _line("Install Discharge Air Temperature Sensor", quote="hold the discharge air temperature", sid="S1"))
    job, systems, _ = _assemble([_vav()], {"VAV": WrittenScope(lines)})
    texts = _texts(job.blocks[0])
    assert texts.count("Furnish and Install Discharge Air Temperature Sensor") == 1
    assert "Furnish and Install Discharge Air Temperature Sensor (Location: Each Box)" not in texts
    assert "Install Discharge Air Temperature Sensor" in texts                     # another verb: kept


def test_duplicates_naming_different_tags_add_their_counts_and_others_do_not():
    fans = _system("EF", "Exhaust Fan EF-1, 2", ("EF-1", "EF-2"), 2, kind="Exhaust Fan")
    lines = (_line("Furnish Fan Start / Stop – EF-1"), _line("Furnish Fan Start / Stop – EF-2"),
             _line("Furnish and Install Damper Actuator", quantity=2, quote="Job 26-9999 two"),
             _line("Furnish and Install Damper Actuator (Location: Each Fan)", quantity=2, quote="Job 26-9999 two"))
    job, _, _ = _assemble([fans], {"EF": WrittenScope(lines)})
    items = {i.text: i.quantity for i in job.blocks[0].items}
    start = [t for t in items if t.startswith("Furnish Fan Start / Stop")]
    assert len(start) == 1 and items[start[0]] == 2
    damper = [t for t in items if t.startswith("Furnish and Install Damper Actuator")]
    assert len(damper) == 1 and items[damper[0]] == 2


def test_duplicate_client_notes_are_one():
    scope = WrittenScope(VAV_LINES, client_notes=(
        "**Boxes to be started and commissioned by factory authorized personnel per equipment schedule",
        "**VAV boxes to be started/commissioned by factory authorized personnel per equipment schedule"))
    job, _, _ = _assemble([_vav(schedule_sources=("S3", "I1"))], {"VAV": scope})
    notes = [i.text for i in job.blocks[0].items if i.kind == "note"]
    assert len(notes) == 1


def test_a_group_is_one_set_of_lines_under_its_stacked_headers():
    indoor = _system("IDU", "VRF Indoor Unit AC-1 thru 3", ("AC-1", "AC-2", "AC-3"), 3, kind="VRF Indoor Unit",
                     group="VRF System")
    outdoor = _system("ODU", "VRF Outdoor Unit ACCU-1", ("ACCU-1",), 1, kind="VRF Outdoor Unit", group="VRF System")
    scopes = {"IDU": WrittenScope((_line("Install and wire Programmable Thermostat (Furnished by Unit Mfr.)"),
                                   _line("Furnish BMS Communication Wiring to Factory Controls"),
                                   _line("Map Available Points Via Mfr. Provided BMS Interface"))),
              "ODU": WrittenScope((_line("Furnish BMS Communication Wiring to VRF Factory Controls"),
                                   _line("Map Available Points Via Mfr. Provided BMS Interface"),
                                   _line("AME Requires Mfr. Rep to Assist in Integration, cost to be Incurred by "
                                         "Mech Contractor", depth=2)))}
    job, _, _ = _assemble([indoor, outdoor], scopes)
    last = job.blocks[1]
    texts = _texts(last)
    assert sum(1 for t in texts if "Communication Wiring" in t) == 1
    assert texts.count("Map Available Points Via Mfr. Provided BMS Interface") == 1
    assert "AME requires mfr. Rep to assist in integration, cost to be incurred by mech contractor" in texts


def test_lines_are_in_the_house_order_with_their_sub_lines_and_notes_last():
    lines = (_line("Map Available Points Via Mfr. Provided BMS Interface"),
             _line("Furnish and Wire Hot Water Control Valve and Actuator"),
             _line("Furnish Fan Start / Stop and Status"),
             _line("Interlock Fan with Valve", depth=2),
             _line("Furnish and Install Space Temperature Sensor"),
             _line("Furnish DDC Controller to the Factory for Installation"))
    scope = WrittenScope(lines, client_notes=("**Maintain the CO2 setpoints",))
    job, _, _ = _assemble([_vav()], {"VAV": scope})
    assert _texts(job.blocks[0]) == ["Furnish DDC Controller to the Factory for Installation",
                                     "Furnish and Install Space Temperature Sensor",
                                     "Furnish Fan Start / Stop and Status", "Interlock Fan with Valve",
                                     "Furnish and Wire Hot Water Control Valve and Actuator",
                                     "Map Available Points Via Mfr. Provided BMS Interface",
                                     "**Maintain the CO2 setpoints"]


ROOMS = ("[S30] High temperature alarm in the Fire Pump Room, Electric Room and Garage: provide a room temperature "
         "sensor in each.")


def test_the_same_device_for_the_same_rooms_is_written_once_in_the_dedicated_system():
    text = _dossier().text + "\n" + ROOMS + "\n\n"
    dossier = _dossier(text=text, sources=dict(SOURCES, S30="23 09 23, Specs.pdf page 11"))
    fans = _system("EF", "Exhaust Fan EF-1, 2", ("EF-1", "EF-2"), 2, kind="Exhaust Fan", sequence_sources=("S2", "S30"))
    alarms = _system("TA", "Misc Monitoring Systems - Room Temperature Alarms", (), 3, kind="Misc Monitoring Systems",
                     sequence_sources=("S30",), quantity_source="S30", quantity_quote="Fire Pump Room, Electric Room")
    ef_lines = (_line("Furnish and Wire Fan Start/Stop", quote="Exhaust fans EF-1 and EF-2", sid="S2"),
                _line("Furnish and Install Space Temperature Sensor for High Temp. Alarm (Location: Fire Pump Room, "
                      "Electric Room, Garage)", quote="provide a room temperature sensor in each", sid="S30"))
    ta_lines = (_line("Furnish and Install Dedicated Room Temperature Sensor", quote="provide a room temperature "
                      "sensor in each", sid="S30"),
                _line("Fire Pump Room (Location: Room 008)", depth=2, quote="Fire Pump Room", sid="S30"),
                _line("Electric Room (Location: Room 009)", depth=2, quote="Electric Room", sid="S30"),
                _line("Garage (Location: Room 111)", depth=2, quote="Garage", sid="S30"))
    job, systems, _ = assemble_job(_job_catalogue(), JOB_READING, dossier, JobPlan((fans, alarms)),
                                   {"EF": WrittenScope(ef_lines), "TA": WrittenScope(ta_lines)}, TODAY, TEMPLATES)
    assert not any("Temperature Sensor" in t for t in _texts(_block(job, "Exhaust")))
    assert "Furnish and Install Dedicated Room Temperature Sensor" in _texts(_block(job, "Room Temperature"))
    assert any("Temperature Sensor" in r.decide for s in systems for r in s.review)


# --- 4. tech hours ------------------------------------------------------------------------------------------------

def test_a_system_takes_its_nearest_templates_rule_on_its_own_count():
    fan = _system("RXF", "Refuse Room Exhaust Fan RXF-1, 2", ("RXF-1", "RXF-2"), 2, kind="Refuse Room Exhaust Fan")
    hours, note = tech_hours(fan, 2, [], None, TEMPLATES, "the fan runs on a VFD to hold the static pressure")
    assert hours == 8.0                                      # the Exhaust Fan rule: 4 h a fan with DDC points
    assert note.category == "ASSUMPTION" and "Exhaust Fan" in note.decide    # not the system's own entry
    hours, note = tech_hours(fan, 2, [], TechHoursHint("unit", 3.0, "Exhaust Fan"), TEMPLATES, "started locally")
    assert hours is None and note is not None                 # the template gives none: no hours, never the AI's


def test_systems_with_no_template_rule_get_no_hours_and_one_review_row_lists_them():
    planned = [_system("ZC", "Zamboni Charger", (), 1, kind="Zamboni Charger"),
               _system("ICE", "Ice Resurfacer Dock", (), 1, kind="Ice Resurfacer Dock")]
    scopes = {"ZC": WrittenScope((_line("Furnish Charger Status"),),
                                 tech_hours_hint=TechHoursHint("unit", 2.0, "Fuel Oil Pump System")),
              "ICE": WrittenScope((_line("Furnish Dock Status"),))}
    job, systems, review = _assemble(planned, scopes)
    assert all(b.tech_hours is None for b in job.blocks if b.header.startswith(("Qty (1) Zamboni", "Qty (1) Ice")))
    rows = [r for r in review_list(systems, review) if "tech hours" in r.decide.lower()]
    assert len(rows) == 1 and "Zamboni Charger" in rows[0].decide and "Ice Resurfacer Dock" in rows[0].decide


def test_per_hardware_point_counts_only_the_hardware_point_lines():
    ahu = PlannedSystem("AHU", "Air Handling Unit AHU-1", "Air Handling Unit", ("AHU-1",), 1)
    lines = [("Furnish and Install Supply Air Temperature Sensor", 1), ("Furnish and Wire Supply Fan Start/Stop", 1),
             ("Furnish High Supply Air Temperature Alarm at BMS", 1), ("Map Available Points", None),
             ("Interlock Fan with Damper", 1), ("Furnish BMS Communication Wiring to AHU Factory Controls", 1)]
    hours, _ = tech_hours(ahu, 1, lines, None, TEMPLATES)
    assert hours == 4.0


def test_a_monitoring_block_of_four_sensors_never_gets_sixty_four_hours():
    alarms = _system("TA", "Misc Monitoring Systems - Room Temperature Alarms", (), 4, kind="Misc Monitoring Systems")
    lines = (_line("Furnish and Install Dedicated Room Temperature Sensor (Qty. 4 Total)"),
             _line("Fire Pump Room (Location: Room 008)", depth=2), _line("Water Heater Room (Location: Room 008A)", depth=2),
             _line("Electric Room (Location: Room 009)", depth=2), _line("Garage (Location: Room 111)", depth=2),
             _line("Necessary Low Voltage Wiring from Each Room Temperature Sensor to Nearby DDC Controller"),
             _line("Furnish High Space Temperature Alarm at BMS – Above 95 Deg F (adj.)"),
             _line("Furnish Low Space Temperature Alarm at BMS – Below 45 Deg F (adj.)"))
    job, _, _ = _assemble([alarms], {"TA": WrittenScope(lines)})
    block = _block(job, "Room Temperature")
    assert block.tech_hours == 8.0                             # 2 h a monitored sensor, 4 sensors
    rooms = [i for i in block.items if i.depth == 2]
    assert all(i.quantity == 1 for i in rooms)


def test_the_fire_pump_system_counts_the_pumps_it_names():
    pump = _system("FP", "Fire Pump Controller Monitoring (Fire Pump and Jockey Pump)", (), 1,
                   kind="Misc Monitoring Systems")
    lines = (_line("Map Available Points Via Mfr. Provided BMS Interface or Connect to Nearby DDC Controller"),
             _line("Fire Pump & Jockey Pump Common Fault Alarm Monitoring"),
             _line("Furnish BMS Communication Wiring to Fire Pump Controller Factory Controls"))
    job, _, _ = _assemble([pump], {"FP": WrittenScope(lines)})
    assert _block(job, "Fire Pump").tech_hours == 4.0            # 2 h a pump, 2 pumps


# --- 5. line totals ---------------------------------------------------------------------------------------------

def test_a_point_line_whose_count_differs_from_one_a_unit_carries_its_total():
    fans = _system("DXF", "Dryer Exhaust Fan DXF-1 thru 10", tuple(f"DXF-{n}" for n in range(1, 11)), 10,
                   kind="Dryer Exhaust Fan")
    lines = (_line("Furnish and Install Current Sensor for Each Dryer", quantity=30, quote="Job 26-9999 30 dryers"),
             _line("Furnish Fan Start / Stop"),
             _line("Furnish and Install Duct Static Pressure Sensor (Qty. 2 Total)"))
    job, systems, _ = _assemble([fans], {"DXF": WrittenScope(lines)})
    items = {i.text: i.quantity for i in job.blocks[0].items}
    assert items["Furnish and Install Current Sensor for Each Dryer (Qty. 30 Total)"] == 30
    assert items["Furnish Fan Start / Stop"] == 10
    assert items["Furnish and Install Duct Static Pressure Sensor (Qty. 2 Total)"] == 2
    written = next(s for s in systems if s.bundle_key == "DXF")
    assert any(line.text.endswith("(Qty. 30 Total)") for line in written.lines)


# --- 7. the review list in plain words ------------------------------------------------------------------------------

_SOURCE_ID = re.compile(r"\[\s*[SI]\d+\s*\]|\b[SI]\d+\b")


def test_the_review_list_names_places_never_source_ids():
    general = [ReviewItem("The plan", "", "Is the valve in [S1] the one on S3?", "the AI's question", "Decide it"),
               ReviewItem("The plan", "", "The picture I1 shows two boxes", "[S4]; [S5]", "")]
    job, systems, review = _assemble([_vav()], {"VAV": WrittenScope(VAV_LINES, review_notes=("See [S3] and I1",))})
    ranked = review_list(systems, review + general, _dossier())
    for row in ranked:
        for text in (row.decide, row.evidence, row.action):
            assert not _SOURCE_ID.search(text), text
    question = next(r for r in ranked if r.decide.startswith("Is the valve"))
    assert "23 09 93 page 44" in question.decide and "M-601 page 5" in question.decide


def test_the_master_template_rows_are_one_line_per_system_in_one_row():
    lines = VAV_LINES[1:3]
    fans = _system("EF", "Exhaust Fan EF-1, 2", ("EF-1", "EF-2"), 2, kind="Exhaust Fan")
    job, systems, review = _assemble([_vav(), fans], {"VAV": WrittenScope(lines),
                                                      "EF": WrittenScope((_line("Furnish Fan Start / Stop"),))})
    ranked = review_list(systems, review, _dossier())
    rows = [r for r in ranked if "Master Template" in r.decide and "left out" in r.decide]
    assert len(rows) == 1
    per_system = rows[0].evidence.split("\n")
    assert len(per_system) == 2
    assert per_system[0].startswith("Variable Air Volume Box") and per_system[1].startswith("Exhaust Fan")


# --- 6. the front end: the standard lines stay, and the review says which line was printed and why -----------

def test_the_front_end_review_says_which_line_was_printed_and_why():
    from test_front_end import ALL_FOUND, _overview
    who = ["The owner shall provide a connection to the Internet via the customer's intranet to a corporate server."]
    catalogue = _job_catalogue(overview=_overview(ALL_FOUND, who=who))
    plan_front = {"mode": "new-system", "existing_name": "", "sources": ["S9"], "notes": [],
                  "lines": ["Furnish BMS Server / Operator Workstation (Location as Determined by Owner)"]}
    job, systems, review = _assemble([_vav()], {"VAV": WrittenScope(VAV_LINES)}, catalogue=catalogue,
                                     front_end=plan_front)
    texts = [i.text for i in job.front_end.items]
    assert "Furnish BMS Server" in texts and "Furnish PC Workstation" in texts
    assert "**BMS Server by Owner" not in texts
    [row] = [r for r in systems[0].review if r.decide.startswith("Printed “Furnish PC Workstation”")]
    assert "the specification calls for it" in row.decide and "left out" in row.decide
    assert "[S9]" not in row.evidence


def test_integration_lines_every_system_carries_stay_in_every_system():
    rtu = _system("RTU", "Rooftop Unit RTU-1, 2", ("RTU-1", "RTU-2"), 2, kind="Rooftop Unit")
    fans = _system("DF", "Destratification Fan DF-1, 2", ("DF-1", "DF-2"), 2, kind="Destratification Fan")
    trio = (_line("Furnish BMS Communication Wiring to Factory Controls"),
            _line("Map Available Points Via Mfr. Provided BMS Interface"),
            _line("AME requires mfr. Rep to assist in integration, cost to be incurred by mech contractor", depth=2))
    job, _, _ = _assemble([rtu, fans], {"RTU": WrittenScope(trio), "DF": WrittenScope(trio)})
    for block in job.blocks:
        assert "Map Available Points Via Mfr. Provided BMS Interface" in _texts(block), block.header


def test_a_folded_tag_list_with_a_shared_stem_is_read_whole_and_its_lines_follow_the_parents():
    from estimator.writing.assemble import fold
    dryer = _system("DXF", "Dryer Exhaust Fan DXF-1-1, 2 w/ Electric Duct Heater EDH-1-2, 1-3",
                    ("DXF-1-1", "DXF-1-2", "EDH-1-2", "EDH-1-3"), 2, kind="Dryer Exhaust Fan")
    assert fold(dryer).parent == ("DXF-1-1", "DXF-1-2")
    assert fold(dryer).folded == (("Electric Duct Heater", ("EDH-1-2", "EDH-1-3")),)
    lines = (_line("Furnish and Install DDC Controller for Electric Duct Heater EDH-1-2, 1-3"),
             _line("Furnish and Install Duct Static Pressure Sensor"), _line("Furnish Fan Start / Stop"))
    job, _, _ = _assemble([dryer], {"DXF": WrittenScope(lines)})
    assert _headers(job) == ["Qty (2) Dryer Exhaust Fan DXF-1-1, 2", "Qty (2) Electric Duct Heater EDH-1-2, 3"]
    assert _texts(job.blocks[1])[-1].startswith("Furnish and Install DDC Controller for Electric Duct Heater")


def test_interlock_wiring_lines_saying_the_same_thing_are_one():
    vrf = _system("VRF", "VRF Outdoor Unit ACCU-1, 2", ("ACCU-1", "ACCU-2"), 2, kind="VRF Outdoor Unit")
    lines = (_line("Low Voltage Interlock Wiring between Indoor Units, Branch Circuit Controllers and Condensing Units"),
             _line("Interlock Wiring between each Branch Circuit Controller, its Indoor Units and Condensing Unit"),
             _line("Low Voltage Interlock Wiring between Indoor and Outdoor Units"))
    job, _, _ = _assemble([vrf], {"VRF": WrittenScope(lines)})
    assert len([t for t in _texts(job.blocks[0]) if "Interlock Wiring" in t]) == 2
