"""Round 2 fixes (.superpowers/sdd/2026-09-26-whole-job-writing/round2-fixes.md, Part 1): the assembly
never loses what the AI planned, a line's quantity comes from the line, the front end keeps its
deterministic base, the review list is ranked and short."""
from __future__ import annotations

from types import SimpleNamespace

from estimator.price_sheet.write import check_fit
from estimator.reading.inventory import FamilyTotal
from estimator.writing.assemble import (MAX_FRONT_END_LINES, assemble_job, check_plan, check_scope, expand_tags,
                                        line_quantity, polish_line, review_list, shape_header)
from estimator.writing.judge import MAX_HEADER
from estimator.writing.write import ReviewItem, tag_list
from test_assemble import (EF_SCOPE, JOB_READING, READING, TEMPLATES, TODAY, VAV_LINES, JobPlan, PlannedSystem,
                           WrittenLine, WrittenScope, _assemble, _dossier, _ef, _headers, _job_catalogue, _vav)
from test_front_end import _overview as front_end_overview


def _system(key, header, tags=(), quantity=1, **kw):
    values = dict(kind=kw.pop("kind", header.split(" ")[0]), tags=tuple(tags), quantity=quantity,
                  quantity_source="S9", quantity_quote="Job 26-9999", sequence_sources=("S9",))
    values.update(kw)
    return PlannedSystem(key, header, **values)


def _all_items(job):
    return [i for b in job.blocks for i in b.items]


# --- 1. never drop a planned system -----------------------------------------------------------------------

ERV_TAGS = ("ERV-C-1", "ERV-1-1", "ERV-2-1", "EDH-C-1", "EDH-1-1", "EDH-2-1")
ERV_HEADER = ("Energy Recovery Ventilator ERV-C-1, ERV-1-1, ERV-2-1 w/ Electric Duct Heater EDH-C-1, EDH-1-1, "
              "EDH-2-1")
AC_TAGS = ("AC-EMR-1", "AC-EMR-2", "AC-EMR-3", "AC-LOBBY-1", "AC-LOBBY-2", "AC-LAUNDRY-1", "AC-ATS-1.1", "AC-ATS-1.2",
           "AC-ARCS-1", "AC-MDF-1", "AC-IT-1")


def test_a_long_header_folds_the_tagged_units_after_with_into_their_own_stacked_header():
    shape = shape_header(_system("ERV", ERV_HEADER, ERV_TAGS, 3), 3)        # round 3: folded units
    assert shape.headers == ("Qty (3) Energy Recovery Ventilator ERV-C-1, ERV-1-1, ERV-2-1",
                             "Qty (3) Electric Duct Heater EDH-C-1, EDH-1-1, EDH-2-1")
    assert shape.note == "" and shape.folded == 1
    untagged = shape_header(_system("OAF", "Outdoor Air Fan w/ Electric Duct Heater", (), None), None)
    assert untagged.headers == ("Qty (##) Outdoor Air Fan w/ Electric Duct Heater",) and untagged.folded == 0


def test_a_long_header_moves_its_descriptors_into_the_first_note():
    header = "Plumbing Pumps (Domestic Water Pump, HW Circulator, Ejector Pumps, Elevator Sump, Sewage Pumps)"
    shape = shape_header(_system("PP", header, (), None), None)
    assert shape.headers == ("Qty (##) Plumbing Pumps",)
    assert shape.note == "**Includes Domestic Water Pump, HW Circulator, Ejector Pumps, Elevator Sump, Sewage Pumps"
    short = shape_header(_vav(), 3)                                                   # a short header is kept
    assert short.headers == ("Qty (3) Variable Air Volume Box VAV-1 thru 3",) and short.note == ""


def test_a_header_with_a_pipe_becomes_two_stacked_headers():
    split = _system("DS", "Split System Indoor Unit DS-1, 2 | Outdoor Unit CU-1, 2", ("DS-1", "DS-2", "CU-1", "CU-2"), 2)
    shape = shape_header(split, 2)
    assert shape.headers == ("Qty (2) Split System Indoor Unit DS-1, 2", "Qty (2) Outdoor Unit CU-1, 2")
    assert not any("|" in h for h in shape.headers)


def test_a_header_still_too_long_is_one_header_per_family_and_a_family_is_never_cut():
    header = "Split System Indoor Unit " + tag_list(AC_TAGS)            # round 4: one family, one header
    assert len(header) > MAX_HEADER
    shape = shape_header(_system("AC", header, AC_TAGS, 11), 11)
    assert len(shape.headers) == 1 and shape.note == ""
    shown = expand_tags(shape.headers[0].split("Split System Indoor Unit ", 1)[1])
    assert shown == list(AC_TAGS) and shape.quantities == (11,)
    two = _system("AC", "Split System " + tag_list(AC_TAGS) + ", " + tag_list(["ACCU-1", "ACCU-2"]),
                  AC_TAGS + ("ACCU-1", "ACCU-2"), 13)
    shape = shape_header(two, 13)
    assert len(shape.headers) == 2 and shape.quantities == (11, 2)
    assert all(h.split(") ", 1)[1].startswith("Split System ") for h in shape.headers)


def test_a_long_header_system_is_printed_with_its_headers_stacked():
    erv = _system("ERV", ERV_HEADER, ERV_TAGS, 3)
    ac = _system("AC", "Split System Indoor Unit " + tag_list(AC_TAGS), AC_TAGS, 11)
    line = WrittenLine("Furnish and Install Space Temperature Sensor", quote="Job 26-9999", source_id="S9")
    job, systems, review = _assemble([erv, ac], {"ERV": WrittenScope((line,)), "AC": WrittenScope((line,))})
    check_fit(job)
    headers = _headers(job)
    assert headers[:2] == ["Qty (3) Energy Recovery Ventilator ERV-C-1, ERV-1-1, ERV-2-1",
                           "Qty (3) Electric Duct Heater EDH-C-1, EDH-1-1, EDH-2-1"]
    assert job.blocks[1].joined and job.blocks[0].items == ()
    stacked = [b for b in job.blocks if "Split System Indoor Unit" in b.header]
    assert len(stacked) == 1 and stacked[0].items


def test_a_system_whose_lines_were_all_refused_falls_back_to_the_master_template():
    pump = _system("FP", "Fire Pump Controller Monitoring (Fire Pump and Jockey Pump)", (), 1,
                   kind="Misc Monitoring Systems", quantity_source="S8", quantity_quote="Provide two fire pumps",
                   sequence_sources=("S8",))
    refused = ("“Fire Pump & Jockey Pump Alarm Monitoring (as per sequence)” — it does not start with a house verb",)
    job, systems, review = _assemble([_vav(), pump], {"VAV": WrittenScope(VAV_LINES),
                                                      "FP": WrittenScope((), refused=refused)})
    block = next(b for b in job.blocks if "Fire Pump" in b.header)
    texts = [i.text for i in block.items]
    assert "Map Available Points Via Mfr. Provided BMS Interface or Connect to Nearby DDC Controller" in texts
    assert "Fire Pump & Jockey Pump Common Fault Alarm Monitoring" in texts          # the evidence names the fire pump
    written = next(s for s in systems if s.bundle_key == "FP")
    assert written.printed and all(line.category == "ASSUMPTION" for line in written.lines if line.client)
    top = review_list(systems, review)[0]
    assert top.decide.startswith("System written with fallback lines — check") and "Fire Pump" in top.decide


def test_with_no_template_the_refused_lines_are_rewritten_with_a_verb():
    odd = _system("ODD", "Zamboni Charger", (), 1, kind="Zamboni Charger")
    refused = ("“Zamboni Charger Status (Furnished by Others)” — it does not start with a house verb",
               "“Charger Alarm” — it does not start with a house verb",
               "“Furnish Charger at $400” — it names “$”")
    job, systems, review = _assemble([odd], {"ODD": WrittenScope((), refused=refused)})
    block = next(b for b in job.blocks if "Zamboni" in b.header)
    texts = [i.text for i in block.items]
    assert texts == ["Wire Zamboni Charger Status (Furnished by Others)", "Furnish Charger Alarm"]
    assert review_list(systems, review)[0].decide.startswith("System written with fallback lines — check")


def test_nothing_planned_vanishes():
    group_a = _system("CH", "Chiller CH-1, 2", ("CH-1", "CH-2"), 2, group="Plant")
    group_b = _system("CHWP", "Chilled Water Pump CHWP-1, 2", ("CHWP-1", "CHWP-2"), None, group="Plant",
                      quantity_quote="", quantity_source="")
    planned = [
        _vav(), _ef(exception="EXCEPTION TO ANY WORK WITH Qty (2) EF-1, 2 - LINE-VOLTAGE THERMOSTAT"),
        _system("CUH", "Cabinet Unit Heater CUH-1", ("CUH-1",), 12, alternate="add"),
        _system("ERV", ERV_HEADER, ERV_TAGS, 3), _system("PP", "Plumbing Pumps", (), None, quantity_quote="",
                                                         quantity_source=""),
        _system("FP", "Fire Pump", (), 1, kind="Misc Monitoring Systems"),
        _system("NEW", "Gas Booster Pump", (), 1), group_a, group_b,
    ]
    line = WrittenLine("Furnish and Install Space Temperature Sensor", quote="Job 26-9999", source_id="S9")
    scopes = {"VAV": WrittenScope(VAV_LINES), "CUH": WrittenScope((line,)), "ERV": WrittenScope((line,)),
              "PP": WrittenScope((line,)), "FP": WrittenScope((), refused=("“Pump” — it does not start with a verb",)),
              "NEW": None, "CH": WrittenScope((line,)), "CHWP": WrittenScope((line,))}
    job, systems, review = _assemble(planned, scopes)
    check_fit(job)
    printed = [b.header for b in job.blocks] + [b.header for a in job.add_alternates + job.deduct_alternates
                                                for b in a.blocks]
    for system in planned:
        if system.exception:
            assert system.exception in job.named_exceptions
            continue
        first = system.header.split(" w/ ")[0].split(" ")[0]
        if system.key in ("PP", "CHWP"):   # nothing on the drawings shows it: the top question, never lost
            name = system.header
            assert any(r.decide.startswith(f"Does {name} exist") for r in review_list(systems, review))
            continue
        assert any(first in header for header in printed), system.key


# --- 2. no quantity: Qty (##) ------------------------------------------------------------------------------

def test_no_quantity_prints_qty_hash_hash_with_the_count_to_give_at_the_top():
    job, systems, review = _assemble([_vav(quantity=None, quantity_quote="", quantity_source=""), _ef()],
                                     {"VAV": WrittenScope(VAV_LINES), "EF": EF_SCOPE}, dossier=_dossier(counts={}))
    check_fit(job)
    assert _headers(job) == ["Qty (##) Variable Air Volume Box VAV-1 thru 3", "Qty (2) Exhaust Fan EF-1, 2"]
    assert all(i.quantity is None for i in job.blocks[0].items)
    vav = next(s for s in systems if s.bundle_key == "VAV")
    assert vav.printed
    top = review_list(systems, review)[0]
    assert top.decide == "Give the count for Qty (##) Variable Air Volume Box VAV-1 thru 3"
    assert top.rank == 1


# --- 3. a line's quantity comes from the line ------------------------------------------------------------------

UH = _system("UH", "Unit Heater UH-1 thru 7", tuple(f"UH-{n}" for n in range(1, 8)), 7)


def test_a_line_naming_a_subset_takes_its_own_count():
    assert line_quantity("Furnish and Install Space Thermostat – Electric Unit Heaters UH-1 thru 6", "", None, UH, 7) == 6
    assert line_quantity("Furnish and Install Space Thermostat – Gas-Fired Unit Heater UH-7", "", None, UH, 7) == 1
    assert line_quantity("Furnish and Install Roll-Up Door Switch – UH-3 only", "", None, UH, 7) == 1
    assert line_quantity("Furnish and Install CO Sensor (Qty. 9 Total)", "", None, UH, 7) == 9
    assert line_quantity("Furnish and Install CO2 Sensor (Location: Team Room 106A, 108A)", "", None, UH, 7) == 2
    assert line_quantity("Furnish and Install Space Temperature Sensor (Location: Fire Pump Room, Water Heater "
                         "Room, Electric Room, Garage)", "", None, UH, 7) == 4
    assert line_quantity("Furnish and Install Space Sensor (Location: Elevator Lobby, Min. Two Floors Below Roof)",
                         "", None, UH, 7) == 7                         # one place described, not a list of rooms
    assert line_quantity("Furnish and Install Discharge Air Temperature Sensor", "", None, UH, 7) == 7
    assert line_quantity("Furnish and Install Discharge Air Temperature Sensor", "", None, UH, None) is None
    assert line_quantity("Furnish and Install Sensor", "two sensors", 2, UH, 7) == 2      # the AI's, from its quote


def test_two_lines_splitting_a_system_by_subset_take_their_subset_counts():
    lines = (WrittenLine("Furnish and Install Space Thermostat; Wire to Heater Control Circuit – Electric Unit "
                         "Heaters UH-1 thru 6", quote="Job 26-9999", source_id="S9"),
             WrittenLine("Furnish and Install Space Thermostat; Wire to Heater Control Circuit – Gas-Fired Unit "
                         "Heater UH-7", quote="Job 26-9999", source_id="S9"))
    job, _, _ = _assemble([UH], {"UH": WrittenScope(lines)})
    items = {(i.text, i.quantity) for i in job.blocks[0].items}
    assert items == {("Furnish and Install Space Thermostat", 7),
                     ("Wire to Heater Control Circuit – Electric Unit Heaters UH-1 thru 6", 6),
                     ("Wire to Heater Control Circuit – Gas-Fired Unit Heater UH-7", 1)}


# --- 4. picture evidence --------------------------------------------------------------------------------------

def test_a_quote_from_a_picture_is_accepted_at_point_seven_at_most():
    lines = VAV_LINES + (WrittenLine("Furnish and Install Duct Smoke Detector", quote="SD-1 shown on the schedule "
                                     "picture only", source_id="I1", confidence=0.95),)
    kept, review = check_scope(_vav(), WrittenScope(lines), _dossier(), TEMPLATES)
    smoke = next(k for k in kept if "Smoke" in k.text)
    assert smoke.quoted and smoke.confidence == 0.7
    assert not any("not in the job's documents" in i.decide for i in review)


def test_a_client_note_resting_on_a_picture_is_not_rejected():
    scope = WrittenScope(VAV_LINES, client_notes=("**Boxes shown with integral airflow rings on the schedule",))
    job, _, _ = _assemble([_vav(schedule_sources=("S3", "I1"))], {"VAV": scope})     # the plan cites picture I1
    assert "**Boxes shown with integral airflow rings on the schedule" in [i.text for i in _all_items(job)]


def test_a_note_giving_a_device_to_the_unit_manufacturer_is_a_by_unit_mfr_note():
    text = _dossier().text + "\n[S22] Refrigerant leak detection comes with each fan.\n\n"
    ef =_ef(sequence_sources=("S2", "S22"))
    scope = WrittenScope(EF_SCOPE.lines, client_notes=("**Refrigerant leak detection furnished by the unit "
                                                       "manufacturer",))
    job, _, _ = assemble_job(_job_catalogue(), JOB_READING, _dossier(text=text), JobPlan((ef,)), {"EF": scope},
                             TODAY, TEMPLATES)
    assert "*REFRIGERANT LEAK DETECTION BY UNIT MFR." in [i.text for i in _all_items(job)]


# --- 5. one device, one place ----------------------------------------------------------------------------------

def test_the_same_device_for_the_same_rooms_stays_in_the_system_whose_evidence_names_them():
    text = _dossier().text + "\n[S20] RTU-4 and RTU-5 serve the team rooms.\n\n" \
                             "[S21] VAV-1 serves Team Room 106A and VAV-2 serves Team Room 108A, each with a CO2 " \
                             "sensor.\n\n"
    dossier = _dossier(text=text)
    rtu = _system("RTU", "Rooftop Unit RTU-4, 5", ("RTU-4", "RTU-5"), 2, sequence_sources=("S20",),
                  quantity_source="S20", quantity_quote="RTU-4 and RTU-5")
    vav = _vav(sequence_sources=("S1", "S21"))
    co2_rtu = WrittenLine("Furnish and Install Space CO2 Sensor (Location: Team Room 106A, 108A) (Qty. 2 Total)",
                          quote="RTU-4 and RTU-5 serve the team rooms", source_id="S20")
    co2_vav = WrittenLine("Furnish and Install Space Temperature / CO2 Sensor (Location: Team Room 106A and Team "
                          "Room 108A)", quote="each with a CO2 sensor", source_id="S21")
    fan = WrittenLine("Furnish and Wire Supply Fan Start/Stop", quote="RTU-4 and RTU-5", source_id="S20")
    plan = JobPlan((rtu, vav))
    job, systems, review = assemble_job(_job_catalogue(), JOB_READING, dossier, plan,
                                        {"RTU": WrittenScope((co2_rtu, fan)), "VAV": WrittenScope(VAV_LINES + (co2_vav,))},
                                        TODAY, TEMPLATES)
    rtu_block = next(b for b in job.blocks if "Rooftop" in b.header)
    vav_block = next(b for b in job.blocks if "Variable Air Volume" in b.header)
    assert not any("CO2" in i.text for i in rtu_block.items)
    assert any("Team Room" in i.text for i in vav_block.items)
    assert any("CO2" in i.decide and "Rooftop Unit" in i.decide for s in systems for i in s.review)


# --- 6. the front end ---------------------------------------------------------------------------------------------

def _front(lines, notes=(), **kw):
    plan_front = {"mode": "new-system", "existing_name": "", "lines": list(lines), "notes": list(notes),
                  "sources": ["S9"]}
    return _assemble([_vav()], {"VAV": WrittenScope(VAV_LINES)}, front_end=plan_front, **kw)


def test_a_plan_front_end_line_is_added_only_when_it_adds_something_new():
    job, systems, _ = _front(["Furnish Training on the New Controls", "Furnish Submittal Drawings (Qty. 8 Sets)"])
    texts = [i.text for i in job.front_end.items]
    assert "Furnish Training on the New Controls" not in texts            # near-duplicate of the template's line
    assert "Furnish Submittal Drawings (Qty. 8 Sets)" in texts


def test_front_end_contradictions_keep_the_deterministic_answer():
    who = ["The Owner will provide, install, and configure the following products: 1. Servers"]
    catalogue = _job_catalogue(overview=front_end_overview(who=who))
    job, systems, _ = _front(["Furnish BMS Server / Operator Workstation (Location as Determined by Owner)",
                              "Furnish Browser-Based Graphics with Animation and Trending"], catalogue=catalogue)
    texts = [i.text for i in job.front_end.items]
    assert "**BMS Server by Owner" in texts
    assert not any(t.startswith("Furnish BMS Server") for t in texts)
    assert not any("Browser-Based Graphics" in t for t in texts)
    front = systems[0]
    assert any("server" in i.decide.lower() and "kept" in i.decide for i in front.review)
    assert any("graphics" in i.decide.lower() for i in front.review)


def test_the_warranty_never_goes_into_the_front_end():
    job, systems, _ = _front(["Furnish 24-Month Warranty on Controls Labor and Materials",
                              "Furnish Startup, Commissioning and As-Built Documentation and One-Year Warranty"])
    texts = [i.text for i in job.front_end.items]
    assert not any("arranty" in t for t in texts)
    assert "Furnish Startup, Commissioning and As-Built Documentation" in texts
    warranty = next(b for b in job.blocks if b.header == "Qty (1) Extended Warranty")
    assert [i.text for i in warranty.items] == ["Furnish 24-Month Warranty on Controls Labor and Materials"]


def test_the_front_end_is_capped_and_the_rest_go_to_the_review_list():
    words = ("Lighting", "Elevator", "Generator", "Meter", "Chiller", "Boiler", "Pump", "Fountain", "Kitchen",
             "Laundry", "Pool", "Solar", "Battery", "Security", "Parking")
    job, systems, _ = _front([f"Furnish {w} Gateway" for w in words])
    assert sum(1 for i in job.front_end.items if i.kind == "line" and i.depth == 1) == MAX_FRONT_END_LINES
    [row] = [i for i in systems[0].review if i.decide.startswith("Spec items the front end could add")]
    assert "Furnish Parking Gateway" in row.evidence


# --- 7. house-style polish -------------------------------------------------------------------------------------

def test_the_polish():
    assert polish_line("Furnish and Install Damper Actuator (as per sequence)") == ["Furnish and Install Damper Actuator"]
    assert polish_line("Furnish Electric Heat SCR Control (AO)") == ["Furnish Electric Heat SCR Control"]
    assert polish_line("Furnish and Install Relay; Wire to Fan Starter") == ["Furnish and Install Relay",
                                                                            "Wire to Fan Starter"]
    assert polish_line("Furnish and Install Relay; see the detail") == ["Furnish and Install Relay; see the detail"]


def test_duplicate_lines_and_notes_in_a_block_are_removed():
    lines = VAV_LINES + (WrittenLine("Furnish and Install Space Temperature / CO2 Sensor (as per sequence)",
                                     quote="space temperature and CO2 setpoints", source_id="S1"),)
    scope = WrittenScope(lines, client_notes=("**Maintain the CO2 setpoints", "**Maintain the CO2 setpoints."))
    job, _, _ = _assemble([_vav()], {"VAV": scope})
    texts = [i.text for i in job.blocks[0].items]
    assert texts.count("Furnish and Install Space Temperature / CO2 Sensor") == 1
    assert sum(1 for t in texts if t.startswith("**Maintain")) == 1


# --- 9. the review list, ranked and short ------------------------------------------------------------------------

def test_the_review_list_is_ranked_and_merged():
    general = [ReviewItem("The plan", "", "Are the hoods by others?", "the AI's question", "Decide it"),
               ReviewItem("The plan", "DISCREPANCY", "Equipment on the drawings the plan didn't write: X", "", "")]
    systems = [SimpleNamespace(bundle_key=k, review=(
        ReviewItem(k, "", f"No tech hours for {k} — enter them", "No Master Template rule fits it", "Type them"),
        ReviewItem(k, "", f"The quote for “Furnish {k} Sensor” is not in the job's documents", "“x”", "Check"),
        ReviewItem(k, "", "The fans run all day", "the AI's note", ""),
        ReviewItem(k, "", "Tech hours: no entry was named, so none suggested", "the AI's note", ""),
    )) for k in ("EF", "UH", "CUH")]
    ranked = review_list(systems, general)
    assert [r.rank for r in ranked] == list(range(1, len(ranked) + 1))
    assert ranked[0].category == "DISCREPANCY" and ranked[1].decide == "Are the hoods by others?"
    [hours] = [r for r in ranked if r.decide.startswith("No tech hours")]
    assert all(k in hours.decide for k in ("EF", "UH", "CUH"))
    assert sum(1 for r in ranked if "not in the job's documents" in r.decide) == 1
    assert sum(1 for r in ranked if r.evidence == "the AI's note" or "The AI's notes" in r.decide) == 3


def test_the_review_list_tab_has_a_rank_column_and_drops_spec_only_flags():
    import openpyxl
    from estimator.evidence.workbook import _review_list
    job, systems, review = _assemble([_vav(), _ef()], {"VAV": WrittenScope(VAV_LINES), "EF": EF_SCOPE})
    ranked = review_list(systems, review)
    assert len(ranked) <= 60
    ws = openpyxl.Workbook().active
    _review_list(ws, [], ranked, ["mentioned only in the specs, not on any drawing: AHU-9", "a page could not be read"])
    rows = [[c.value for c in row] for row in ws.iter_rows()]
    assert rows[0][0] == "Rank"
    assert [r[0] for r in rows[1:len(ranked) + 1]] == list(range(1, len(ranked) + 1))
    assert [r[3] for r in rows[1:len(ranked) + 1]] == [r.decide for r in ranked]
    assert not any("mentioned only in the specs" in str(r[3]) for r in rows)
    assert any(r[3] == "a page could not be read" for r in rows)


# --- 10. the equipment the plan didn't write skips reading noise ----------------------------------------------------

def test_families_that_are_only_reading_noise_are_not_reviewed():
    families = (FamilyTotal("Variable Air Volume Box", "VAV", 3, "VAV-1 thru VAV-3", ()),
                FamilyTotal("Boiler", "B", 0, "", ()), FamilyTotal("Cooling Tower", "CT", 0, "", ()),
                FamilyTotal("Return Fan", "RF", 2, "RF-1, RF-2", ()),
                FamilyTotal("Cabinet Unit Heater", "CUH", 1, "CUH-1", ()))
    counts = dict(_dossier().counts, RF={"schedule_rows": 2, "quantity_column": None, "plan_placements": 0,
                                         "riser": None, "distinct_tags": 2})
    schedule = SimpleNamespace(document="Plumb.pdf", page=2, sheet="P502", title="PLUMBING FIXTURE SCHEDULE",
                               rows=(SimpleNamespace(tag="RF-1"), SimpleNamespace(tag="RF-2")))
    reading = SimpleNamespace(inventory=(), schedules=(schedule,))
    catalogue = SimpleNamespace(sheets=(SimpleNamespace(document="Plumb.pdf", page=2, discipline="Plumbing"),))
    review = check_plan(JobPlan((_vav(),)), _dossier(families=families, counts=counts), reading, catalogue)
    [item] = [i for i in review if i.decide.startswith("Equipment on the drawings the plan didn't write")]
    assert "Cabinet Unit Heater CUH-1" in item.decide
    for noise in ("Boiler", "Cooling Tower", "Return Fan"):
        assert noise not in item.decide
