"""Round 5 fixes (.superpowers/sdd/2026-09-26-whole-job-writing/round5-fixes.md): assembly only. Location lists
are not tags, repeated points are removed by meaning, nothing right is lost, systems with nothing behind them
become questions, the front end's contradictions and cap, and the review list's order."""
from __future__ import annotations

import dataclasses

from estimator.catalogue.overview import FOUND, Found, Place
from estimator.catalogue.register import PageRecord
from estimator.price_sheet.write import check_fit
from estimator.reading.inventory import FamilyTotal
from estimator.writing.assemble import (MAX_FRONT_END_LINES, TIER_FIRST, TIER_QUESTION, TIER_REST, assemble_job,
                                        check_scope, plan_checks, polish_line, review_list, shape_header)
from estimator.writing.write import ReviewItem
from test_assemble import (IMAGE, JOB_READING, READING, TEMPLATES, TEXT, TODAY, SOURCES, JobPlan, PlannedSystem,
                           WrittenLine, WrittenScope, _dossier, _headers, _job_catalogue)
from test_front_end import ALL_FOUND, SPEC, _overview as front_end_overview


def _system(key, header, tags=(), quantity=1, **kw):
    values = dict(kind=kw.pop("kind", header.split(" ")[0]), tags=tuple(tags), quantity=quantity,
                  quantity_source="S9", quantity_quote="Job 26-9999", sequence_sources=("S9",))
    values.update(kw)
    return PlannedSystem(key, header, **values)


def _line(text, quote="Job 26-9999", sid="S9", **kw):
    return WrittenLine(text, quote=quote, source_id=sid, **kw)


def _job(systems, scopes, dossier=None, front_end=None, catalogue=None, unresolved=()):
    plan = JobPlan(tuple(systems), front_end or {}, tuple(unresolved))
    return assemble_job(catalogue or _job_catalogue(), JOB_READING, dossier or _dossier(), plan, scopes, TODAY,
                        TEMPLATES)


def _review(systems, general):
    return [item for s in systems for item in s.review] + list(general)


def _texts(job):
    return [i.text for b in job.blocks for i in b.items]


def _lines(block):
    return [i.text for i in block.items if i.kind == "line"]


# --- 1. location lists aren't tags --------------------------------------------------------------------------------

ROOMS = ("Fire Pump Room 008", "Water Heater Room 008A", "Electric Room 009", "Garage 111")
ROOM_ALARMS = "Misc Monitoring - Room Temperature Alarms"


def _room_alarms(**kw):
    return _system("MISC-TEMP", ROOM_ALARMS, ROOMS, 4, kind="Misc Monitoring Systems", **kw)


def test_a_system_whose_tags_are_rooms_prints_one_header_with_the_plans_total():
    shape = shape_header(_room_alarms(), 4)
    assert shape.headers == (f"Qty (4) {ROOM_ALARMS}",)
    scope = WrittenScope((_line("Tie into Nearby DDC Controller"),
                          _line("Furnish and Install Room Temperature Sensor", depth=2),
                          _line("Monitor High Space Temperature Alarm", depth=2)))
    job, systems, general = _job([_room_alarms()], {"MISC-TEMP": scope})
    check_fit(job)
    assert _headers(job) == [f"Qty (4) {ROOM_ALARMS}"]
    first = job.blocks[0].items[0]
    assert first.text == "(Location: Fire Pump Room 008, Water Heater Room 008A, Electric Room 009, Garage 111)"
    assert not any("tag list and quantity disagree" in r.decide for r in _review(systems, general))


def test_the_location_line_is_not_repeated_when_a_line_already_lists_the_rooms():
    listed = "Furnish and Install Room Temperature Sensor (Location: " + ", ".join(ROOMS) + ")"
    scope = WrittenScope((_line("Tie into Nearby DDC Controller"), _line(listed, depth=2)))
    job, _, _ = _job([_room_alarms()], {"MISC-TEMP": scope})
    assert sum(1 for t in _texts(job) if "(Location:" in t) == 1


def test_names_that_are_neither_tags_nor_rooms_give_one_header_and_no_location_line():
    pumps = _system("FP", "Fire Pump and Jockey Pump Monitoring", ("Fire Pump", "Jockey Pump", "JPCP"), 2,
                    kind="Misc Monitoring Systems")
    job, _, _ = _job([pumps], {"FP": WrittenScope((_line("Monitor Fire Pump Common Fault Alarm"),))})
    assert _headers(job) == ["Qty (2) Fire Pump and Jockey Pump Monitoring"]
    assert not any("(Location:" in t for t in _texts(job))


# --- 2. repeated points, removed by meaning -----------------------------------------------------------------------

ERV = _system("ERV", "Energy Recovery Ventilator ERV-C-1, ERV-1-1, ERV-2-1", ("ERV-C-1", "ERV-1-1", "ERV-2-1"), 3,
              kind="Packaged ERU", group="ERV")
EDH = _system("EDH", "Electric Duct Heater EDH-C-1, EDH-1-1, EDH-2-1", ("EDH-C-1", "EDH-1-1", "EDH-2-1"), 3,
              kind="Electric duct heater", group="ERV")
ERV_LINES = (
    _line("Install and Wire Discharge Air Temperature Sensor (Furnished by Unit Mfr.)", confidence=0.85),
    _line("Furnish and Install DDC Controller for Electric Duct Heater (as per sequence)", confidence=0.75),
    _line("Electric Duct Heater Signal (0-100%)", depth=2, confidence=0.85),
    _line("Electric Duct Heater Status", depth=2, confidence=0.85),
    _line("Electric Duct Heater Alarm", depth=2, confidence=0.85),
    _line("Furnish and Install Duct Heater Discharge Air Temperature Sensor (Low Temp Alarm)", depth=2,
          confidence=0.8),
    _line("Furnish BMS Communication Wiring to Factory Controls (Qty. 3 Total)", quantity=3, confidence=0.9))
EDH_LINES = (
    _line("Furnish and Install DDC Controller", confidence=0.6),
    _line("Furnish and Install EDH Discharge Air Temperature Sensor", confidence=0.85),
    _line("Furnish EDH Status", confidence=0.8),
    _line("Monitor EDH Alarm", confidence=0.8),
    _line("Furnish EDH Modulating Control Signal (0-100%) to SCR Controller", confidence=0.8),
    _line("Interlock Wiring between EDH and ERV Unit Operation", confidence=0.7))


def _erv_job():
    return _job([ERV, EDH], {"ERV": WrittenScope(ERV_LINES), "EDH": WrittenScope(EDH_LINES)})


def test_the_erv_with_its_duct_heater_points_keeps_every_line_the_judge_wrote_since_the_gem_round():
    job, systems, general = _erv_job()
    texts = _texts(job)  # the GEM round: the only consolidation is the GEM's (identical lines across units); nothing else is merged
    assert sum(1 for t in texts if t.endswith("Status")) == 2
    assert sum(1 for t in texts if t.endswith("Alarm")) == 2
    assert sum(1 for t in texts if "DDC Controller" in t) == 2
    assert "Install and wire Discharge Air Temperature Sensor (Furnished by Unit Mfr.)" in texts   # the unit's own
    assert "Interlock Wiring between EDH and ERV Unit Operation" in texts
    assert "Furnish BMS Communication Wiring to Factory Controls (Qty. 3 Total)" in texts


def test_no_line_is_removed_as_a_repeat_by_meaning():
    job, systems, general = _erv_job()
    assert not any(r.decide.startswith("Repeated lines printed once") for r in _review(systems, general))
    for kept in ("Furnish EDH Status", "Monitor EDH Alarm", "Furnish and Install DDC Controller"):
        assert kept in _texts(job)


GARAGE = dict(group="Parking Garage CO")


def test_a_garage_block_with_vfd_speed_control_in_two_wordings_keeps_both():
    exhaust = _system("GXF", "Garage Exhaust Fan GXF-C-1", ("GXF-C-1",), 1, kind="Exhaust Fan", **GARAGE)
    circulation = _system("GCF", "Garage Circulation Fan GCF-A", ("GCF-A",), 9, kind="Exhaust Fan", **GARAGE)
    scopes = {"GXF": WrittenScope((_line("Furnish and Install DDC Controller"),
                                   _line("Furnish Fan Start / Stop and Status", confidence=0.9),
                                   _line("Furnish Fan VFD Speed Control", confidence=0.9))),
              "GCF": WrittenScope((_line("Furnish and Install DDC Controller"), _line("Furnish Fan Start / Stop"),
                                   _line("Furnish Fan VFD Speed Control, VFD Speed Feedback and VFD Fault",
                                         confidence=0.8)))}
    job, _, _ = _job([exhaust, circulation], scopes)
    texts = _texts(job)
    assert sum(1 for t in texts if "VFD Speed Control" in t) == 2  # the GEM round: the only consolidation is the GEM's (identical lines across units); nothing else is merged
    assert "Furnish Fan VFD Speed Control, VFD Speed Feedback and VFD Fault" in texts
    assert "Furnish Fan Start / Stop and Status" in texts and "Furnish Fan Start / Stop" in texts
    assert sum(1 for t in texts if "DDC Controller" in t) == 1                   # word for word: printed once


def test_a_dryer_block_with_the_make_up_air_interlock_in_three_wordings_keeps_them():
    dryer = _system("DXF", "Dryer Exhaust Fan DXF-1-1, 2", ("DXF-1-1", "DXF-1-2"), 2, kind="Dryer Exhaust Fan",
                    group="Dryer Exhaust")
    make_up = _system("MUAF", "Laundry Make-up Air Fan MUAF-1-1, 2", ("MUAF-1-1", "MUAF-1-2"), 2,
                      kind="Dryer Exhaust Fan", group="Dryer Exhaust")
    scopes = {"DXF": WrittenScope((_line("Interlock Wiring between Dryers and Dryer Exhaust Fan Controls"),
                                   _line("Interlock with Make-Up Air System (as per sequence)", confidence=0.7),
                                   _line("Interlock Dryer Exhaust Fan with Make-Up Air Fan", confidence=0.6))),
              "MUAF": WrittenScope((_line("Interlock Wiring between Make-Up Air Fan and Dryer Exhaust System "
                                          "Operation", confidence=0.75),))}
    job, _, _ = _job([dryer, make_up], scopes)
    texts = _texts(job)
    assert sum(1 for t in texts if "Make-Up Air" in t) == 3  # the GEM round: the only consolidation is the GEM's (identical lines across units); nothing else is merged
    assert "Interlock Wiring between Make-Up Air Fan and Dryer Exhaust System Operation" in texts
    assert "Interlock Wiring between Dryers and Dryer Exhaust Fan Controls" in texts


def test_a_point_for_the_parent_and_the_folded_unit_stays_once_per_unit_when_the_tags_differ():
    job, _, _ = _job([ERV, EDH], {"ERV": WrittenScope((_line("Monitor Duct Heater Alarm – EDH-C-1"),)),
                                  "EDH": WrittenScope((_line("Furnish Electric Duct Heater Alarm – EDH-1-1"),))})
    named = " ".join(_texts(job))
    assert "EDH-C-1" in named and "1-1" in named


def test_the_same_device_for_different_locations_is_not_a_repeat():
    fans = _system("EF", "Exhaust Fan EF-1, 2", ("EF-1", "EF-2"), 2, kind="Exhaust Fan")
    lines = (_line("Furnish and Install Space Temperature Sensor (Location: Gym)"),
             _line("Furnish and Install Space Temperature Sensor (Location: Weight Room)"))
    job, _, _ = _job([fans], {"EF": WrittenScope(lines)})
    assert sum(1 for t in _texts(job) if "Space Temperature Sensor" in t) == 2


# --- 3. nothing right may be lost ------------------------------------------------------------------------------

def _warranty_catalogue(sentence, quote="Provide all submittals and system warranty.", page_text=None, **kw):
    place = Place(SPEC, 12, None, "23 09 23", "Controls spec")
    services = (Found("Services that cost hours", "Warranty", (place,), quote, FOUND, ""),)
    pages = [PageRecord(SPEC, 12, "text", page_text if page_text is not None else sentence, 0)]
    return _job_catalogue(overview=front_end_overview(services=services, **kw), pages=pages)


def _fan():
    return _system("EF", "Exhaust Fan EF-1, 2", ("EF-1", "EF-2"), 2, kind="Exhaust Fan")


def test_a_warranty_term_the_spec_names_prints_the_extended_warranty_block():
    catalogue = _warranty_catalogue("A. Warrant labor and materials for specified control system free from defects "
                                    "for a period of 24 months after project substantial completion.")
    job, systems, general = _job([_fan()], {"EF": WrittenScope((_line("Furnish Fan Start / Stop"),))},
                                 catalogue=catalogue)
    block = next(b for b in job.blocks if b.header == "Qty (1) Extended Warranty")
    assert any("24-month" in t for t in _lines(block))
    warranty = next(s for s in systems if s.bundle_key == "Extended Warranty")
    assert any("24 months" in line.evidence for line in warranty.lines)
    assert not any("Say how long the warranty is" in r.decide for r in _review(systems, general))


def test_a_standard_year_or_a_makers_warranty_prints_no_block():
    text = ("Warranty shall cover all costs for parts and labor for a period of one year from acceptance. "
            "Five-year manufacturers warranty.")
    job, _, _ = _job([_fan()], {"EF": WrittenScope((_line("Furnish Fan Start / Stop"),))},
                     catalogue=_warranty_catalogue(text))
    assert not any(b.header == "Qty (1) Extended Warranty" for b in job.blocks)


def test_with_no_term_found_the_warranty_goes_to_the_review_list():
    job, systems, general = _job([_fan()], {"EF": WrittenScope((_line("Furnish Fan Start / Stop"),))},
                                 catalogue=_warranty_catalogue("All work shall be under warranty."))
    assert not any(b.header == "Qty (1) Extended Warranty" for b in job.blocks)
    assert any("warranty" in r.decide.lower() for r in _review(systems, general))


def test_a_stated_total_is_never_stripped_by_a_repeat():
    fans = _fan()
    lines = (_line("Furnish and Install Current Switch (Qty. 9 Total)", confidence=0.6),
             _line("Furnish and Install Current Switch", confidence=0.95))
    job, _, _ = _job([fans], {"EF": WrittenScope(lines)})
    assert "Furnish and Install Current Switch (Qty. 9 Total)" in _texts(job)


def test_a_quantity_with_a_quote_is_kept_when_the_quote_is_not_found():
    kept, _ = check_scope(_fan(), WrittenScope((_line("Furnish and Install Current Switch", quantity=4,
                                                      quote="four current switches on the fans"),)), _dossier())
    assert kept[0].quantity == 4


def _polished(text):
    return polish_line(text)[0]


def test_assembly_keeps_every_judge_line_that_passed_the_checks():
    fans = _system("EF", "Exhaust Fan EF-1, 2", ("EF-1", "EF-2"), 2, kind="Exhaust Fan")
    fan_lines = (_line("Furnish and Install Current Switch"), _line("Monitor Fan Status"),
                 _line("Monitor Fan Fail Alarm"), _line("Furnish Fan Start / Stop (as per sequence)"),
                 _line("Furnish Fan Start / Stop"), _line("Install and Wire Space Thermostat (Furnished by Unit Mfr.)"))
    scopes = {"ERV": WrittenScope(ERV_LINES), "EDH": WrittenScope(EDH_LINES), "EF": WrittenScope(fan_lines)}
    job, systems, general = _job([ERV, EDH, fans], scopes)
    printed = _texts(job)
    said = " ".join(f"{r.decide} {r.evidence}" for r in _review(systems, general))
    for line in ERV_LINES + EDH_LINES + fan_lines:
        text = _polished(line.text)
        merged = text.startswith("Monitor ") and any(text[len("Monitor "):] in t for t in printed)
        assert text in printed or merged or f"“{text}”" in said, text


# --- 4. extra systems with nothing behind them --------------------------------------------------------------------

EXTRA_TEXT = TEXT + "\n".join([
    "5. Sequences", "[S20] a. Mechanical room supply fan: MVF", "",
    "[S31] 3. In a normal condition, the exhaust fan, make-up air fan, and recirculatory fans will run continuously.",
    "", "[S32] g. Make-Up Fan Start/Stop", "",
    "[S40] 1. The BMS shall monitor the status of all plumbing pumps.", ""])
EXTRA_SOURCES = dict(SOURCES, S20="23 09 93 SEQUENCE OF OPERATIONS, Specs.pdf page 6",
                     S31="23 09 93 SEQUENCE OF OPERATIONS, Specs.pdf page 8",
                     S32="23 09 93 SEQUENCE OF OPERATIONS, Specs.pdf page 9",
                     S40="23 09 93 SEQUENCE OF OPERATIONS, Specs.pdf page 10")


def _extra_dossier():
    return _dossier(text=EXTRA_TEXT, sources=EXTRA_SOURCES)


def _unseen(key, header, tags, seq):
    return _system(key, header, tags, None, kind="Supply fan", quantity_source="", quantity_quote="",
                   sequence_sources=seq)


MAKE_UP = _unseen("MUA", "Garage Make-up Air Fan", (), ("S31", "S32"))
MVF = _unseen("MVF", "Mechanical Room Supply Fan MVF", ("MVF",), ("S20",))
PUMPS = _unseen("PP", "Plumbing Pumps", (), ("S40",))


def test_a_system_with_nothing_behind_it_is_a_top_question_not_a_block():
    scopes = {k: WrittenScope((_line("Furnish Make-Up Fan Start / Stop and Status"),)) for k in ("MUA", "MVF")}
    unresolved = ("Is there a garage make-up air fan? The garage sequence lists make-up fan points, but no fan is "
                  "scheduled.",)
    job, systems, general = _job([MAKE_UP, MVF, _fan()], dict(scopes, EF=WrittenScope((_line("Furnish Fan Start"),))),
                                 dossier=_extra_dossier(), unresolved=unresolved)
    assert _headers(job) == ["Qty (2) Exhaust Fan EF-1, 2"]
    ranked = review_list(systems, general, _extra_dossier())
    top = ranked[:2]
    assert {r.decide.split(" exist")[0] for r in top} == {"Does Garage Make-up Air Fan", "Does Mechanical Room Supply "
                                                                                        "Fan MVF"}
    make_up = next(r for r in top if "Garage" in r.decide)
    assert make_up.decide.startswith("Does Garage Make-up Air Fan exist on this job? The plan wrote it from 23 09 93 "
                                     "page 8")
    assert make_up.decide.endswith("no schedule or count shows it.")
    assert make_up.tier == TIER_FIRST
    assert not any(r.evidence == "the AI's question" and "garage make-up air fan" in r.decide.lower() for r in ranked)
    checks, _ = plan_checks(JobPlan((MAKE_UP, MVF, _fan())), _extra_dossier(), READING)
    assert [c.goes.startswith("held back") for c in checks] == [True, True, False]


def test_a_system_whose_sequence_paragraph_names_it_still_prints():
    job, _, _ = _job([PUMPS], {"PP": WrittenScope((_line("Monitor Pump Status"),))}, dossier=_extra_dossier())
    assert _headers(job) == ["Qty (##) Plumbing Pumps"]


def test_a_system_with_a_schedule_row_still_prints():
    scheduled = _unseen("MUA", "Garage Make-up Air Fan", (), ("S31",))
    scheduled = dataclasses.replace(scheduled, schedule_sources=("S3",))
    job, _, _ = _job([scheduled], {"MUA": WrittenScope((_line("Furnish Fan Start / Stop"),))}, dossier=_extra_dossier())
    assert _headers(job) == ["Qty (##) Garage Make-up Air Fan"]


# --- 5. the front end ---------------------------------------------------------------------------------------------

def _front_texts(job):
    return [i.text for i in job.front_end.items]


def _with_front(front, catalogue):
    return _job([_fan()], {"EF": WrittenScope((_line("Furnish Fan Start / Stop"),))}, front_end=front,
                catalogue=catalogue)


COMPUTERS = "**Computers and related equipment (PC, monitors, routers, printers) by others"


def test_a_client_note_contradicting_a_line_the_documents_support_is_removed():
    catalogue = _job_catalogue(overview=front_end_overview(ALL_FOUND))
    front = {"mode": "new-system", "lines": [], "notes": [COMPUTERS], "sources": ["S9"]}
    job, systems, _ = _with_front(front, catalogue)
    assert "Furnish PC Workstation" in _front_texts(job) and COMPUTERS not in _front_texts(job)
    assert any(COMPUTERS in r.decide and "Furnish PC Workstation" in r.decide for r in systems[0].review)


def test_a_client_note_the_documents_support_in_the_same_sentence_wins():
    catalogue = _job_catalogue(overview=front_end_overview(
        who=["Computers and printers for the BMS shall be furnished by others."]))
    front = {"mode": "new-system", "lines": [], "notes": [COMPUTERS], "sources": ["S9"]}
    job, systems, _ = _with_front(front, catalogue)
    assert COMPUTERS in _front_texts(job) and "Furnish PC Workstation" not in _front_texts(job)
    assert any(COMPUTERS in r.decide and "Furnish PC Workstation" in r.decide for r in systems[0].review)


def test_the_cap_applies_only_to_lines_added_from_the_plan():
    catalogue = _job_catalogue(overview=front_end_overview(ALL_FOUND))
    front = {"mode": "new-system", "lines": ["Furnish Web Page Host Device",
                                             "Furnish and Install Network Switches with Fiber Optic Backbone"],
             "notes": [], "sources": ["S9"]}
    job, systems, _ = _with_front(front, catalogue)
    lines = [i.text for i in job.front_end.items if i.kind == "line" and i.depth == 1]
    assert {"IT Infrastructure", "Furnish UPS – For workstation, server, network level control panel"} <= set(lines)
    assert len(lines) > MAX_FRONT_END_LINES
    assert "Furnish and Install Network Switches with Fiber Optic Backbone" in lines      # the spec calls for it
    assert "Furnish Web Page Host Device" not in lines
    [row] = [r for r in systems[0].review if r.decide.startswith("Spec items the front end could add")]
    assert "Furnish Web Page Host Device" in row.evidence


def test_a_ups_line_the_spec_calls_for_goes_past_the_cap_on_an_extension():
    found = {"Tie-in to an existing system": "Extend the existing Johnson Controls system.",
             "UPS": "Each BMS panel shall be provided with an integral 750 VA UPS."}
    catalogue = _job_catalogue(overview=front_end_overview(found))
    front = {"mode": "extend-existing", "lines": [
        "Extend Existing Johnson Controls BMS to the New Building", "Furnish and Install Qty (1) Network Controller",
        "Furnish and Install LCD Access at Master Panels (Qty. 2 Total)",
        "Furnish and Install 750 VA UPS/Battery Back-up at Each BMS Panel"], "notes": [], "sources": ["S9"]}
    job, _, _ = _with_front(front, catalogue)
    lines = [i.text for i in job.front_end.items if i.kind == "line" and i.depth == 1]
    assert "Furnish and Install 750 VA UPS/Battery Back-up at Each BMS Panel" in lines
    assert "Furnish and Install LCD Access at Master Panels (Qty. 2 Total)" not in lines
    assert len(lines) == MAX_FRONT_END_LINES + 1


# --- 6. the review list's order -----------------------------------------------------------------------------------

def test_a_discrepancy_only_from_an_unread_schedule_is_ranked_low():
    families = (FamilyTotal("Exhaust Fan", "EF", 2, "EF-1, EF-4", ()),)
    counts = {"EF": {"schedule_rows": 1, "quantity_column": None, "plan_placements": 0, "riser": None,
                     "distinct_tags": 2}}
    fans = _system("EF", "Exhaust Fan EF-1, 2, 3", ("EF-1", "EF-2", "EF-3"), 3, kind="Exhaust Fan",
                   schedule_sources=("I1",))
    dossier = _dossier(families=families, counts=counts)
    job, systems, general = _job([fans], {"EF": WrittenScope((_line("Furnish Fan Start / Stop"),))}, dossier=dossier,
                                 unresolved=("Are the hoods by others?",))
    ranked = review_list(systems, general, dossier)
    [row] = [r for r in ranked if r.category == "DISCREPANCY" and "by its own tags" in r.decide]
    assert row.tier == TIER_REST
    assert ranked[0].decide == "Are the hoods by others?"


def test_the_ais_notes_are_one_row_per_block():
    scopes = {"ERV": WrittenScope(ERV_LINES, review_notes=("The ERV has factory controls.",)),
              "EDH": WrittenScope(EDH_LINES, review_notes=("The heaters run off the ERV controller.",))}
    _, systems, general = _job([ERV, EDH], scopes)
    rows = [r for r in review_list(systems, general) if r.decide.startswith("The AI's notes")]
    assert len(rows) == 1
    assert "factory controls" in rows[0].decide and "run off the ERV controller" in rows[0].decide


def test_the_order_is_cannot_write_then_quantity_then_question_then_note():
    items = [ReviewItem("X", "", "a note", "", ""),
             ReviewItem("The plan", "", "Are the hoods by others?", "the AI's question", ""),
             ReviewItem("Y", "PENDING", "Give the count for Qty (##) Y", "", "", tier=2),
             ReviewItem("Z", "ASSUMPTION", "System written with fallback lines — check Qty (1) Z", "", "", tier=1)]
    ranked = review_list([], items)
    assert [r.system for r in ranked] == ["Z", "Y", "The plan", "X"]
    assert ranked[2].tier == 0 or ranked[2].tier == TIER_QUESTION
