"""Round 4 fixes, Part A (.superpowers/sdd/2026-09-26-whole-job-writing/round4-fixes.md): the header check,
keeping a count once it is known, panel headers, trimmed blocks, the front end, case and wording, job-wide
picture ids and stale requests."""
from __future__ import annotations

import json
from types import SimpleNamespace

from estimator.price_sheet.write import check_fit
from estimator.reading.inventory import FamilyTotal
from estimator.writing.assemble import (MAX_FRONT_END_LINES, assemble_job, check_scope, expand_tags, fold,
                                        plan_checks, polish_line, review_list, shape_header, system_pictures)
from estimator.writing.judge import Judge
from estimator.writing.style import load_house_style
from estimator.writing.whole_job import PlannedSystem as RealPlannedSystem, images_listing, parse_scope, write_prompt
from test_assemble import (IMAGE, JOB_READING, READING, TEMPLATES, TODAY, DossierImage, JobPlan, PlannedSystem,
                           WrittenLine, WrittenScope, _assemble, _dossier, _headers, _job_catalogue)
from test_front_end import ALL_FOUND, _overview as front_end_overview


def _system(key, header, tags=(), quantity=1, **kw):
    values = dict(kind=kw.pop("kind", header.split(" ")[0]), tags=tuple(tags), quantity=quantity,
                  quantity_source="S9", quantity_quote="Job 26-9999", sequence_sources=("S9",))
    values.update(kw)
    return PlannedSystem(key, header, **values)


def _line(text, quote="Job 26-9999", sid="S9", **kw):
    return WrittenLine(text, quote=quote, source_id=sid, **kw)


def _texts(block):
    return [i.text for i in block.items]


def _job(systems, scopes, dossier=None, front_end=None, catalogue=None):
    plan = JobPlan(tuple(systems), front_end or {})
    return assemble_job(catalogue or _job_catalogue(), JOB_READING, dossier or _dossier(), plan, scopes, TODAY,
                        TEMPLATES)


def _review(systems, general):
    return [item for s in systems for item in s.review] + list(general)


# --- 1. the header check ---------------------------------------------------------------------------------------

VAV_TAGS = tuple(f"VAV-4-{n}" for n in range(1, 8)) + tuple(f"VAV-5-{n}" for n in range(1, 9))
VAV_HEADER = "VAV Box w/ SCR Electric Reheat VAV-4-1 thru 4-7, VAV-5-1 thru 5-8"
VAV_FAMILY = (FamilyTotal("Variable Air Volume Box", "VAV", 15, "VAV-4-1 thru 4-7, VAV-5-1 thru 5-8", ()),)
VAV_COUNTS = {"VAV": {"schedule_rows": 5, "quantity_column": None, "plan_placements": 16, "riser": None,
                      "distinct_tags": 15}}


def test_a_range_written_with_its_floor_is_expanded_in_full():
    assert expand_tags("VAV-4-1 thru 4-7, VAV-5-1 thru 5-8") == list(VAV_TAGS)


def test_the_26_0478_vav_regression_a_descriptor_with_the_units_own_tags_is_never_a_second_header():
    vav = _system("VAV", VAV_HEADER, VAV_TAGS, 15, kind="VAV / Fan VAV")
    assert fold(vav).folded == ()
    assert shape_header(vav, 15).headers == (f"Qty (15) {VAV_HEADER}",)
    dossier = _dossier(families=VAV_FAMILY, counts=VAV_COUNTS)
    [check], _ = plan_checks(JobPlan((vav,)), dossier, READING)
    assert check.category == "CONFIRMED"
    lines = (_line("Furnish DDC Controller to the Factory for Installation"),
             _line("Furnish Electric Heat SCR Control – VAV-4-1, VAV-5-1"))
    job, systems, general = _job([vav], {"VAV": WrittenScope(lines)}, dossier=dossier)
    assert _headers(job) == [f"Qty (15) {VAV_HEADER}"]
    assert not any("tag list and quantity disagree" in r.decide for r in _review(systems, general))
    items = {i.text: i.quantity for i in job.blocks[0].items}
    assert items["Furnish Electric Heat SCR Control – VAV-4-1, VAV-5-1"] == 2


def test_a_header_whose_tags_do_not_add_up_to_its_quantity_prints_the_plans_header_with_a_review_row():
    fans = _system("EF", "Exhaust Fan EF-1, 2, 3", ("EF-1", "EF-2", "EF-3"), 4, kind="Exhaust Fan")
    job, systems, general = _job([fans], {"EF": WrittenScope((_line("Furnish Fan Start / Stop"),))})
    assert _headers(job) == ["Qty (4) Exhaust Fan EF-1, 2, 3"]
    assert any("tag list and quantity disagree" in r.decide for r in _review(systems, general))


def test_a_type_tag_counted_many_times_is_not_a_disagreement():
    heaters = _system("EUH", "Electric Unit Heater EUH-1, 2", ("EUH-1", "EUH-2"), 55, kind="EUH / CUH / UH")
    counts = {"EUH": {"schedule_rows": 2, "quantity_column": None, "plan_placements": 55, "riser": None,
                      "distinct_tags": 2}}
    dossier = _dossier(families=(FamilyTotal("Electric Unit Heater", "EUH", 2, "EUH-1, EUH-2", ()),), counts=counts)
    job, systems, general = _job([heaters], {"EUH": WrittenScope((_line("Furnish and Install Space Thermostat"),))},
                                 dossier=dossier)
    assert _headers(job) == ["Qty (55) Electric Unit Heater EUH-1, 2"]
    assert not any("tag list and quantity disagree" in r.decide for r in _review(systems, general))


AC_TAGS = ("AC-EMR-1", "AC-EMR-2", "AC-EMR-3", "AC-LOBBY-1", "AC-LOBBY-2", "AC-LAUNDRY-1", "AC-ATS-1.1", "AC-ATS-1.2",
           "AC-ARCS-1", "AC-MDF-1", "AC-IT-1")


def test_a_long_header_of_one_family_is_one_header_and_never_cut_into_an_includes_note():
    header = "Split System AC-EMR-1 thru 3, AC-LOBBY-1, 2, AC-LAUNDRY-1, AC-ATS-1.1, 1.2, AC-ARCS-1, AC-MDF-1, AC-IT-1"
    shape = shape_header(_system("AC", header, AC_TAGS, 11), 11)
    assert len(shape.headers) == 1 and shape.note == ""
    assert expand_tags(shape.headers[0].split("Split System ", 1)[1]) == list(AC_TAGS)


def test_descriptors_are_dropped_only_after_the_tags_are_compacted_and_the_tags_stay_in_the_header():
    tags = tuple(f"EF-{n}" for n in range(1, 13))
    header = ("Exhaust Fan EF-1, EF-2, EF-3, EF-4, EF-5, EF-6, EF-7, EF-8, EF-9, EF-10, EF-11, EF-12 "
              "(Interlocked with Space Thermostat)")
    shape = shape_header(_system("EF", header, tags, 12), 12)
    assert shape.headers == ("Qty (12) Exhaust Fan EF-1 thru 12 (Interlocked with Space Thermostat)",)
    long = "Exhaust Fan EF-1 thru 12 w/ Motorized Intake Damper, Line Voltage Thermostat and Speed Controller"
    shape = shape_header(_system("EF", long, tags, 12), 12)
    assert shape.headers == ("Qty (12) Exhaust Fan EF-1 thru 12",)
    assert "EF-" not in shape.note and "Motorized Intake Damper" in shape.note


def test_every_header_carries_the_equipments_name():
    split = _system("DS", "Split System DS-1, 2 | CU-1, 2", ("DS-1", "DS-2", "CU-1", "CU-2"), 2, kind="Split System")
    assert shape_header(split, 2).headers == ("Qty (2) Split System DS-1, 2", "Qty (2) Condensing Unit CU-1, 2")
    bare = _system("CU", "CU-1, 2", ("CU-1", "CU-2"), 2, kind="Split System")
    assert shape_header(bare, 2).headers == ("Qty (2) Condensing Unit CU-1, 2",)


# --- 2. keep a count once it is known ----------------------------------------------------------------------

FSD_COUNTS = {"FSD": {"schedule_rows": 0, "quantity_column": None, "plan_placements": 2, "riser": None,
                      "distinct_tags": 1},
              "MD": {"schedule_rows": 0, "quantity_column": None, "plan_placements": 2, "riser": None,
                     "distinct_tags": 1}}


def test_a_count_the_dossier_gives_is_printed_when_the_plan_gives_none():
    dampers = _system("FSD", "Fire / Smoke Damper FSD-1", ("FSD-1",), None, kind="Fire / Smoke Dampers",
                      quantity_quote="", quantity_source="")
    dossier = _dossier(counts=FSD_COUNTS)
    [check], _ = plan_checks(JobPlan((dampers,)), dossier, READING)
    assert check.category == "CONFIRMED-on-plans" and check.quantity == 2
    job, systems, general = _job([dampers], {"FSD": WrittenScope((_line("Furnish and Install Damper End Switch"),))},
                                 dossier=dossier)
    assert _headers(job) == ["Qty (2) Fire / Smoke Damper FSD-1"]
    rows = [r for r in _review(systems, general) if "counted from the plans" in r.decide]
    assert rows and "placements on the plans" in rows[0].decide + rows[0].evidence
    assert not any(r.decide.startswith("Give the count") for r in _review(systems, general))


def test_the_count_row_carries_the_systems_other_review_rows():
    dampers = _system("FSD", "Fire / Smoke Damper FSD-1", ("FSD-1",), None, kind="Fire / Smoke Dampers",
                      quantity_quote="", quantity_source="")
    scope = WrittenScope((_line("Furnish and Install Damper End Switch"),), review_notes=("Count the dampers.",))
    _, systems, general = _job([dampers], {"FSD": scope}, dossier=_dossier(counts=FSD_COUNTS))
    rows = [r for r in review_list(systems, general) if r.system == "Fire / Smoke Damper FSD-1"]
    assert len(rows) == 1 and "Count the dampers." in rows[0].evidence


def test_with_nothing_to_count_it_the_count_stays_to_fill():
    pumps = _system("PP", "Domestic Water Heaters", (), None, kind="Misc Monitoring Systems", quantity_quote="",
                    quantity_source="", sequence_sources=("S50",))
    dossier = _dossier(text=_dossier().text + "\n[S50] The BMS shall monitor the domestic water heaters.\n",
                       sources={**_dossier().sources, "S50": "23 09 93, Specs.pdf page 46"})
    job, _, _ = _job([pumps], {"PP": WrittenScope((_line("Monitor Domestic Water Heater Status"),))}, dossier=dossier)
    assert _headers(job) == ["Qty (##) Domestic Water Heaters"]


# --- 3. a panel's header counts panels ------------------------------------------------------------------------

def test_a_panel_prints_one_and_its_device_count_goes_on_the_device_line():
    gas = _system("GAS", "Gas Detection System (Parking Garage CO/NO)", (), 9, kind="Gas Detection",
                  quantity_quote="Job 26-9999")
    lines = (_line("Furnish and Install CO Control Panel with Audible and Strobe Alarm"),
             _line("Furnish and Install CO/NO Sensor"), _line("Monitor CO Level"))
    job, _, _ = _job([gas], {"GAS": WrittenScope(lines)})
    assert _headers(job) == ["Qty (1) Gas Detection System (Parking Garage CO/NO)"]
    items = {i.text: i.quantity for i in job.blocks[0].items}
    assert items["Furnish and Install CO/NO Sensor (Qty. 9 Total)"] == 9
    assert items["Monitor CO Level"] == 1


def test_a_panel_with_no_count_prints_one_and_the_stated_number_of_panels_wins():
    trace = _system("HT", "Heat Tracing Control Panel", (), None, kind="Misc Monitoring Systems", quantity_quote="",
                    quantity_source="")
    job, _, _ = _job([trace], {"HT": WrittenScope((_line("Furnish BMS Communication Wiring to Factory Controls"),))})
    assert _headers(job) == ["Qty (1) Heat Tracing Control Panel"]
    two = _system("FP", "Fire Pump Controller", (), 2, kind="Fire Pump Monitoring",
                  quantity_quote="Provide 2 fire pump controllers", quantity_source="S8")
    job, _, _ = _job([two], {"FP": WrittenScope((_line("Monitor Fire Pump Alarm"),))})
    assert _headers(job) == ["Qty (2) Fire Pump Controller"]


# --- 4. trim blocks ----------------------------------------------------------------------------------------------

def test_monitor_lines_are_never_merged_since_the_gem_round():
    fans = _system("EF", "Exhaust Fan EF-1, 2", ("EF-1", "EF-2"), 2, kind="Exhaust Fan")
    lines = (_line("Furnish and Install Current Switch"), _line("Monitor Fan Status"), _line("Monitor Fan Fail Alarm"),
             _line("Monitor High Temperature Alarm"))
    job, _, _ = _job([fans], {"EF": WrittenScope(lines)})
    texts = _texts(job.blocks[0])
    assert all(t in texts for t in ("Monitor Fan Status", "Monitor Fan Fail Alarm", "Monitor High Temperature Alarm"))
    assert "Monitor Fan Status, Fan Fail Alarm and High Temperature Alarm" not in texts


def test_monitor_lines_in_a_group_are_never_merged_since_the_gem_round():
    gas = _system("GAS", "Gas Detection System", (), 1, kind="Gas Detection", group="Garage")
    fan = _system("GXF", "Garage Exhaust Fan GXF-1", ("GXF-1",), 1, kind="Exhaust Fan", group="Garage")
    scopes = {"GAS": WrittenScope((_line("Monitor CO Level"), _line("Monitor High CO Level Alarm"))),
              "GXF": WrittenScope((_line("Monitor Fan Fail Alarm"), _line("Monitor Fan Start/Stop, Status and Fail")))}
    job, _, _ = _job([gas, fan], scopes)
    texts = [i.text for b in job.blocks for i in b.items]
    assert "Monitor CO Level" in texts and "Monitor High CO Level Alarm" in texts
    assert "Monitor Fan Fail Alarm" in texts and "Monitor Fan Start/Stop, Status and Fail" in texts


def test_type_tags_placed_more_often_than_listed_are_not_counted_from_their_own_tags():
    counts = {"AC": {"schedule_rows": 14, "quantity_column": None, "plan_placements": 27, "riser": 38,
                     "distinct_tags": 14}}
    families = (FamilyTotal("Air Conditioning Unit", "AC", 14, "AC-1 thru AC-14", ()),)
    indoor = _system("IDU", "VRF Indoor Unit AC-2, AC-3", ("AC-2", "AC-3"), None, kind="VRF System",
                     quantity_quote="", quantity_source="")
    [check], _ = plan_checks(JobPlan((indoor,)), _dossier(counts=counts, families=families), READING)
    assert check.category == "PENDING" and check.quantity is None


def test_same_meaning_lines_are_kept_since_the_gem_round():
    fans = _system("RX", "Refuse Room Exhaust Fan RXF-1", ("RXF-1",), 1, kind="Exhaust Fan")
    lines = (_line("Furnish Refrigerant Leak Detector Status"), _line("Monitor Refrigerant Leak Detector Status"),
             _line("Furnish BMS Communication Wiring to Factory Controls"),
             _line("Map Available Points Via Mfr. Provided BMS Interface"),
             _line("Map Available Points Via Mfr. Provided BMS Interface or Connect to Nearby DDC Controller"),
             _line("Monitor Glycol Feed System Pump Status", depth=2))
    job, _, _ = _job([fans], {"RX": WrittenScope(lines)})
    texts = _texts(job.blocks[0])
    assert sum(1 for t in texts if "Refrigerant Leak Detector Status" in t) == 2
    assert sum(1 for t in texts if t.startswith("Map Available Points")) == 2
    assert "Monitor Glycol Feed System Pump Status" in texts


def test_a_long_block_is_never_cut_and_no_longer_reviewed_for_its_length():
    fans = _system("EF", "Exhaust Fan EF-1, 2", ("EF-1", "EF-2"), 2, kind="Exhaust Fan")
    devices = ("Current Switch", "Damper Actuator", "Space Thermostat", "Duct Smoke Detector", "Static Pressure Sensor",
               "Airflow Station", "Hand-Off-Auto Switch", "Relay", "Temperature Sensor", "Humidity Sensor",
               "CO2 Sensor", "Pressure Switch", "Freeze Stat", "Filter Switch")
    lines = tuple(_line(f"Furnish and Install {d}") for d in devices)
    job, systems, general = _job([fans], {"EF": WrittenScope(lines)})
    assert sum(1 for i in job.blocks[0].items if i.kind == "line") == len(devices)
    assert not any(r.decide.startswith("long block") for r in _review(systems, general))   # no 9-line target


# --- 5. the front end ----------------------------------------------------------------------------------------------

def _front_texts(job):
    return [i.text for i in job.front_end.items if i.kind == "line" and i.depth == 1]


def test_the_front_end_holds_six_lines_and_the_spec_extras_go_to_the_review_list():
    assert MAX_FRONT_END_LINES == 6
    catalogue = _job_catalogue(overview=front_end_overview(ALL_FOUND), texts=["Provide one laptop computer."])
    plan_front = {"mode": "new-system", "lines": ["Furnish Web Page Host Device"], "notes": [], "sources": ["S9"]}
    job, systems, _ = _job([_system("EF", "Exhaust Fan EF-1, 2", ("EF-1", "EF-2"), 2)],
                           {"EF": WrittenScope((_line("Furnish Fan Start / Stop"),))}, front_end=plan_front,
                           catalogue=catalogue)
    texts = _front_texts(job)
    assert len(texts) == 8                 # round 5: the cap applies only to the lines the plan adds
    assert {"Furnish PC Workstation", "Furnish BMS Server", "Furnish Network Level Control Panel",
            "Furnish 3-D Graphics", "Furnish Necessary Training on New Controls", "IT Infrastructure"} <= set(texts)
    [row] = [r for r in systems[0].review if r.decide.startswith("Spec items the front end could add")]
    assert "Furnish Web Page Host Device" in row.evidence and "IT Infrastructure" not in row.evidence


def test_the_pc_workstation_is_always_printed_unless_the_owner_furnishes_it():
    job, _, _ = _job([_system("EF", "Exhaust Fan EF-1, 2", ("EF-1", "EF-2"), 2)],
                     {"EF": WrittenScope((_line("Furnish Fan Start / Stop"),))})
    assert "Furnish PC Workstation" in _front_texts(job)
    owner = _job_catalogue(overview=front_end_overview(who=["The operator workstation shall be owner furnished."]))
    job, _, _ = _job([_system("EF", "Exhaust Fan EF-1, 2", ("EF-1", "EF-2"), 2)],
                     {"EF": WrittenScope((_line("Furnish Fan Start / Stop"),))}, catalogue=owner)
    assert "Furnish PC Workstation" not in _front_texts(job)


def test_a_template_line_a_schedule_note_gives_to_the_unit_maker_is_a_by_unit_mfr_note():
    text = ("1. Job\n[S9] Job 26-9999\n\n4. Schedules\n[S3] EXHAUST FAN SCHEDULE: EF-9 | 500 CFM\n"
            "[S4] NOTE 3: MOTORIZED DAMPER ACTUATOR FURNISHED BY THE FAN MANUFACTURER.\n")
    dossier = _dossier(text=text, sources={"S3": "M-601, page 5", "S4": "M-601, page 5", "S9": "the job folder"})
    fan = _system("EF", "Exhaust Fan EF-9", ("EF-9",), 1, kind="Exhaust Fan", schedule_sources=("S3", "S4"),
                  quantity_quote="EF-9 | 500 CFM", quantity_source="S3")
    job, _, _ = _job([fan], {"EF": None}, dossier=dossier)       # not written yet: the Master Template's lines
    texts = _texts(job.blocks[0])
    assert not any(t.startswith("Furnish") and "Damper Actuator" in t for t in texts)
    assert "*DAMPER ACTUATOR BY UNIT MFR." in texts


# --- 6. case and wording ---------------------------------------------------------------------------------------------

def test_install_and_wire_takes_the_master_templates_form():
    assert polish_line("Install and Wire Space Humidity Sensor (Furnished by Unit Mfr.)") == [
        "Install and wire Space Humidity Sensor (Furnished by Unit Mfr.)"]
    assert polish_line("Install and wire Space Thermostat (Furnished by Unit Mfr.)") == [
        "Install and wire Space Thermostat (Furnished by Unit Mfr.)"]


def test_atc_contractor_wording_takes_the_house_verb_or_goes_to_review():
    style = load_house_style()
    assert style.house_opening("ATC Contractor to provide a relay for the fan interlock") == \
        "Furnish a relay for the fan interlock"
    assert style.house_opening("ATC Contractor to set up and initialize the fan controller setpoints") is None
    answer = {"lines": [{"text": "ATC Contractor to provide Relay for Fan Interlock", "depth": 1, "quantity": None,
                         "quote": "x", "source_id": "", "why": "", "confidence": 0.9},
                        {"text": "ATC Contractor to set up and initialize the fan controller setpoints", "depth": 1,
                         "quantity": None, "quote": "x", "source_id": "", "why": "", "confidence": 0.9}],
              "client_notes": ["**ATC Contractor to set up and initialize the fan controller setpoints"],
              "tech_hours": None, "review_notes": []}
    scope = parse_scope(answer, "m", style)
    assert [line.text for line in scope.lines] == ["Furnish Relay for Fan Interlock"]
    assert scope.client_notes == ()
    assert any("ATC Contractor" in r for r in scope.refused)


# --- 7. picture ids ----------------------------------------------------------------------------------------------------

def _pictures(n):
    return tuple(DossierImage(f"C:/cache/p{k}.png", f"H601 SCHEDULE {k}", "H601", "Mech.pdf", k)
                 for k in range(1, n + 1))


def test_a_write_request_keeps_the_job_wide_picture_ids(tmp_path):
    pictures = _pictures(17)
    text = "1. Job\n[S9] Job 26-9999\n\n4. Schedules\n[S3] UNIT HEATER SCHEDULE (see image I15)\n"
    dossier = _dossier(text=text, images=pictures, sources={"S3": "H601, page 19", "S9": "the job folder"})
    heaters = _system("UH", "Unit Heater UH-1", ("UH-1",), 1, schedule_sources=("S3", "I17"))
    assert [(sid, image.page) for sid, image in system_pictures(heaters, dossier)] == [("I17", 17), ("I15", 15)]
    real = RealPlannedSystem("UH", "Unit Heater UH-1", "EUH / CUH / UH", ("UH-1",), 1, "[S3]", "q", (),
                             ("[S3]", "[I17]"), "", "", "", "")
    prompt = write_prompt(real, "[S3] …", [pictures[16], pictures[14]], [], [], "STYLE", "", ["I17", "I15"])
    assert "- I17:" in prompt and "- I15:" in prompt and "- I1:" not in prompt
    assert [p["id"] for p in images_listing([pictures[16], pictures[14]], ["I17", "I15"])] == ["I17", "I15"]
    judge = Judge(tmp_path / "cache", mode="chat")
    judge.write_system(real, "[S3] …", [pictures[16], pictures[14]], [], [], "STYLE", image_ids=["I17", "I15"])
    (request,) = judge.requests_dir.glob("*.json")
    assert [p["id"] for p in json.loads(request.read_text(encoding="utf-8"))["images"]] == ["I17", "I15"]


def test_the_cross_check_maps_a_picture_id_to_the_job_wide_picture():
    pictures = _pictures(17)
    dossier = _dossier(images=pictures)
    heaters = _system("UH", "Unit Heater UH-1", ("UH-1",), 1, schedule_sources=("I17",))
    scope = WrittenScope((_line("Furnish and Install Space Thermostat", quote="THERMOSTAT", sid="I15"),),
                         review_notes=("The schedule on I15 names a thermostat.",))
    kept, review = check_scope(heaters, scope, dossier, TEMPLATES)
    assert kept[0].quoted and kept[0].confidence <= 0.7
    note = next(r for r in review if r.evidence == "the AI's note")
    assert "H601 page 15" in note.decide


# --- 8. stale requests -----------------------------------------------------------------------------------------------

def test_a_chat_run_moves_this_jobs_requests_it_does_not_ask_again_into_old(tmp_path):
    judge = Judge(tmp_path / "cache", mode="chat", job="26-0478, Somerville HS")
    requests = judge.requests_dir
    requests.mkdir(parents=True)
    mine = {"key": "a", "kind": "write_system", "job": "26-0478, Somerville HS", "prompt": "x"}
    theirs = {"key": "b", "kind": "write_system", "job": "26-0193, Fordham", "prompt": "x"}
    legacy = {"key": "c", "kind": "plan_job", "prompt": "The dossier:\n== 1. JOB ==\n[S1] Job: 26-0478, Somerville"}
    for name, data in (("a", mine), ("b", theirs), ("c", legacy)):
        (requests / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")
    judge.answers_dir.mkdir(parents=True)
    (judge.answers_dir / "z.json").write_text("{}", encoding="utf-8")
    moved = judge.retire_requests()
    assert moved == 2
    assert sorted(p.name for p in requests.glob("*.json")) == ["b.json"]
    assert sorted(p.name for p in (requests / "old").glob("*.json")) == ["a.json", "c.json"]
    assert (judge.answers_dir / "z.json").exists()
    assert judge.stale_requests() == 2
    # a question asked again is back in the requests folder, not in old
    real = RealPlannedSystem("UH", "Unit Heater UH-1", "EUH / CUH / UH", ("UH-1",), 1, "", "", (), (), "", "", "", "")
    judge.write_system(real, "evidence", [], [], [], "STYLE")
    (asked,) = [p for p in requests.glob("*.json") if p.name != "b.json"]
    assert json.loads(asked.read_text(encoding="utf-8"))["job"] == "26-0478, Somerville HS"
    (asked.parent / "old" / asked.name).write_text("{}", encoding="utf-8")
    Judge(tmp_path / "cache", mode="chat", job="26-0478, Somerville HS").write_system(real, "evidence", [], [], [],
                                                                                      "STYLE")
    assert not (asked.parent / "old" / asked.name).exists()
