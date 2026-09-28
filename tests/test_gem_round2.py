"""The GEM round, part 2 (.superpowers/sdd/2026-09-26-whole-job-writing/gem-round-2-fixes.md): assembly only. Nothing
internal reaches the client, one client-facing "*" per decision, the manufacturer's devices in their blocks, the
stacked headers' counts, the Misc Monitoring Systems block, phantom systems as questions, AME's standard lines, and a
review list of one row per decision."""
from __future__ import annotations

import dataclasses
import json
import re

from estimator.writing.assemble import TIER_FIRST, assemble_job, review_list, template_options
from estimator.writing.style import load_house_style
from estimator.writing.templates import TEMPLATES_FILE, load_templates
from estimator.writing.whole_job import Contradiction, Family, JobPlan, PlannedSystem, QcCheck, WrittenLine, WrittenScope
from test_assemble import JOB_READING, SOURCES, TEMPLATES, TEXT, TODAY, _dossier, _headers, _job_catalogue

STYLE = load_house_style()
STANDARD = "AME standard line (Master Template)"
STANDARD_NOTE = "*Assumed per AME standard — confirm"


def _gl(text, reference="Job 26-9999", flag="", flag_text="", quote="Job 26-9999", sid="S9", depth=1, quantity=None):
    return WrittenLine(text, depth, quantity, quote, sid, reference, 0.85, reference, flag, flag_text)


def _scope(*lines, **kw):
    return WrittenScope(tuple(lines), kw.pop("client_notes", ()), None, kw.pop("review_notes", ()), "m", **kw)


def _planned(key, header, tags=(), quantity=1, **kw):
    values = dict(key=key, header=header, kind=kw.pop("kind", header.split(" ")[0]), tags=tuple(tags),
                  quantity=quantity, quantity_source="S9", quantity_quote="Job 26-9999", sequence_sources=("S9",),
                  schedule_sources=(), group="", alternate="", exception="", why="")
    values.update(kw)
    return PlannedSystem(**values)


def _assemble(systems, scopes, dossier=None, unresolved=()):
    plan = JobPlan(tuple(systems), {}, tuple(unresolved), "m")
    dossier = dossier or _dossier()
    job, written, general = assemble_job(_job_catalogue(), JOB_READING, dossier, plan, scopes, TODAY, TEMPLATES)
    return job, written, general, review_list(written, general, dossier)


def _items(job, header):
    at = next(n for n, b in enumerate(job.blocks) if b.header == header)
    for block in job.blocks[at:]:
        if block.items:
            return [(i.kind, i.text) for i in block.items]
    return []


def _printed(job):
    """Every header, line, note and exception the proposal prints."""
    texts = [b.header for b in job.blocks] + [i.text for b in job.blocks for i in b.items]
    texts += [i.text for i in job.front_end.items] + list(job.named_exceptions)
    for alternate in job.add_alternates + job.deduct_alternates:
        texts += [b.header for b in alternate.blocks] + [i.text for b in alternate.blocks for i in b.items]
    return texts


FANS = _planned("EF", "Exhaust Fan EF-1, 2", ("EF-1", "EF-2"), 2, kind="Exhaust Fan")


# --- 1. nothing internal reaches the client -------------------------------------------------------------------------

LEAKY = _scope(
    _gl("Furnish and Install Space Temperature Sensor (S170)", flag="orange",
        flag_text="ASSUMED: CC furnishes it per the factory-controls rule (S170) \U0001F7E0"),
    _gl("Furnish Fan Start/Stop and Status", reference="Mandatory minimum point — per GEM"),
    _gl("Furnish and Install Current Switch [Q7]", flag="red", flag_text="CONFIRM QUANTITY: no count (C6), S480"),
    _gl("Wire Fire Alarm Stop Relay to Fan (Relay Furnished by FA)", flag="yellow",
        flag_text="CONFIRM QUANTITY: I14 shows one relay; Quick Scan says no FA interface"),
    _gl("Controls Contractor requires mfr. rep to assist in integration, cost to be incurred by mech contractor",
        depth=2),
    contradictions=(Contradiction("C5", "Space temperature sensor furnished by CC — field DDC default applied",
                                  ("no party",), "orange"),
                    Contradiction("C5", "Controls contractor term inferred - the sequence says only 'the BMS'", (),
                                  "orange")),
    misc_responsibilities=("Provide additional controllers and wiring as required (S170). \U0001F7E0",
                           "Program the fan schedule at the BMS (S209).",
                           "Wiring from the fan smoke detector to the fire alarm panel is by the Fire Alarm Contractor "
                           "(S214) \U0001F534"),
    client_notes=("** Quantity per GEM Quick Scan, see QC-04",),
    qc=(QcCheck("QC-04", "Fan: Start/Stop yes", False, "none"),),
    exclusions=("Fan disconnect switch (C3)",))


def test_nothing_the_gem_writes_for_the_estimator_reaches_the_client():
    job, systems, general, ranked = _assemble([FANS], {"EF": LEAKY})
    printed = _printed(job)
    for text in printed:
        assert STYLE.internal(text) is None, text
        for word in ("CC", "C1", "C5", "C6", "QC-", "GEM", "Quick Scan", "Mandatory minimum", "field DDC default",
                     "factory-controls rule", "term inferred", "ASSUMED:", "CONFIRM QUANTITY"):
            assert not re.search(rf"\b{re.escape(word)}" if word[0].isalpha() else re.escape(word), text), (word, text)
        assert not re.search(r"(?<![\w-])[SIQ]\d{1,4}\b", text), text
        assert not re.search("[\U0001F300-\U0001FAFF◊]", text), text
    lines = [t for kind, t in _items(job, "Qty (2) Exhaust Fan EF-1, 2") if kind == "line"]
    assert "Furnish and Install Space Temperature Sensor" in lines
    assert "Furnish and Install Current Switch (Qty. per Mechanical Schedule)" in lines
    assert "AME requires mfr. Rep to assist in integration, cost to be incurred by mech contractor" in lines


def test_an_exception_and_a_front_end_line_carry_no_source_id_either():
    fan = dataclasses.replace(FANS, exception="EXCEPTION TO ANY WORK WITH Qty (2) EF-1, 2 - LINE-VOLTAGE THERMOSTAT "
                                              "(S170)")
    job, _, _, _ = _assemble([fan], {})
    assert job.named_exceptions == ("EXCEPTION TO ANY WORK WITH Qty (2) EF-1, 2 - LINE-VOLTAGE THERMOSTAT",)
    front = {"mode": "", "existing_name": "", "sources": ["S9"],
             "lines": ["Extend the BMS Network to the New Building via Fiber Optic Cable (S170) \U0001F7E0"],
             "notes": ["**Owner to provide the IT LAN drop per CC coordination (S171)"]}
    plan = JobPlan((FANS,), front, (), "m")
    job, _, _ = assemble_job(_job_catalogue(), JOB_READING, _dossier(), plan,
                             {"EF": _scope(_gl("Furnish Fan Start/Stop and Status"))}, TODAY, TEMPLATES)
    texts = [i.text for i in job.front_end.items]
    assert "Extend the BMS Network to the New Building via Fiber Optic Cable" in texts
    assert "**Owner to provide the IT LAN drop per AME coordination" in texts
    for text in texts:
        assert STYLE.internal(text) is None, text


# --- 2. the "*" lines: client-facing only, one per decision ---------------------------------------------------------

def test_an_assumption_prints_once_under_its_line_in_plain_words():
    scope = _scope(_gl("Furnish and Install Heavy-Gauge Ventilated Wire Guard for Space Sensors (Qty. 9 Total)",
                       flag="orange", flag_text="Assumed CC furnishes the guards (sequence names no party; the "
                                                "requirement sits in the ATC spec section)."),
                   _gl("Furnish Fan Start/Stop and Status"),
                   contradictions=(Contradiction("C5", "Wire guards for gymnasium and weight room sensors furnished by "
                                                       "CC", ("wire guard",), "orange"),))
    job, _, _, _ = _assemble([FANS], {"EF": scope})
    items = _items(job, "Qty (2) Exhaust Fan EF-1, 2")
    guard = items.index(("line", "Furnish and Install Heavy-Gauge Ventilated Wire Guard for Space Sensors (Qty. 9 Total)"))
    assert items[guard + 1] == ("note", "*Assumed: Wire guards for gymnasium and weight room sensors furnished by AME")
    assert sum(t.startswith("*Assumed") for _, t in items) == 1


def test_a_red_line_asks_for_its_quantity_and_a_yellow_line_prints_no_star():
    scope = _scope(_gl("Furnish and Install RTU-3 Roll-Up Door Position Sensor (Qty. per Drawing)", flag="red",
                       flag_text="Quantity: no drawing count of the roll-up doors"),
                   _gl("Install and wire Space Thermostat (Furnished by Unit Mfr., Shipped Loose)", flag="yellow",
                       flag_text="Confirm the manufacturer ships the thermostat loose (S172)."))
    job, systems, general, ranked = _assemble([FANS], {"EF": scope})
    items = _items(job, "Qty (2) Exhaust Fan EF-1, 2")
    door = items.index(("line", "Furnish and Install RTU-3 Roll-Up Door Position Sensor (Qty. per Drawing)"))
    assert items[door + 1] == ("note", "*Confirm quantity: RTU-3 Roll-Up Door Position Sensor")
    stat = items.index(("line", "Install and wire Space Thermostat (Furnished by Unit Mfr., Shipped Loose)"))
    assert stat + 1 == len(items) or not items[stat + 1][1].startswith("*")
    assert any("Space Thermostat" in r.decide for r in ranked)                 # the ownership question stays


def test_an_assumption_matching_no_line_is_reviewed_not_printed():
    scope = _scope(_gl("Furnish Fan Start/Stop and Status"),
                   contradictions=(Contradiction("C5", "Outdoor air CO2 reference taken as a software value", (),
                                                 "orange"),))
    job, _, _, ranked = _assemble([FANS], {"EF": scope})
    assert not any(t.startswith("*") for _, t in _items(job, "Qty (2) Exhaust Fan EF-1, 2"))
    assert any("Outdoor air CO2 reference" in r.decide for r in ranked)


def test_only_owner_by_others_and_master_template_clarifications_print_as_double_star_notes():
    scope = _scope(_gl("Furnish Fan Start/Stop and Status"),
                   misc_responsibilities=("Program the fan schedule and the fail alarm at the BMS.",
                                          "Set up and initialize the fan controller setpoints.",
                                          "Coordinate with the Balancer for the minimum fan speeds.",
                                          "Wiring from the unit smoke detectors to the fire alarm panel is by the Fire "
                                          "Alarm Contractor.",
                                          "Start/Stop via Fire Alarm System",
                                          "Owner to provide fixed IP address for remote access",
                                          "Line-voltage power, disconnects and heater installation are by others."),
                   client_notes=("** Quantity is based on the 15 terminals on the schedule; clarify a 16th.",))
    job, systems, _, _ = _assemble([FANS], {"EF": scope})
    notes = [t for kind, t in _items(job, "Qty (2) Exhaust Fan EF-1, 2") if kind == "note"]
    assert "**Wiring from the unit smoke detectors to the fire alarm panel is by the Fire Alarm Contractor." in notes
    assert "**Start/Stop via Fire Alarm System" in notes
    assert "**Owner to provide fixed IP address for remote access" in notes
    for gone in ("Program", "Set up", "Coordinate", "Quantity is based", "Line-voltage power"):
        assert not any(gone in n for n in notes), gone
    lines = [line for s in systems for line in s.lines]
    kept = next(line for line in lines if line.text.startswith("**Program the fan schedule"))
    assert kept.client is False                                              # the Evidence Package keeps it


# --- 3. the manufacturer's devices go into their blocks --------------------------------------------------------------

RTUS = _planned("RTU", "Packaged Rooftop Unit RTU-1, 2", ("RTU-1", "RTU-2"), 2, kind="Packaged Rooftop Unit")
VAVS = _planned("VAV", "VAV Box VAV-1 thru 3", ("VAV-1", "VAV-2", "VAV-3"), 3, kind="VAV Box")


def test_a_device_the_unit_manufacturer_furnishes_prints_in_its_block_not_on_the_review_list():
    rtu = _scope(_gl("Furnish BMS Communication Wiring to Factory Controls"),
                 exclusions=("Supply, outside and exhaust airflow measuring stations (furnished with the unit, schedule "
                             "note 4).",
                             "Factory supply and return smoke detectors, A2L refrigerant gas sensors and condensate high "
                             "level switches (by the unit manufacturer).",
                             "Wiring from unit smoke detectors to the building fire alarm panel (by the Fire Alarm "
                             "Contractor)."))
    vav = _scope(_gl("Furnish DDC Controller to the Factory for Installation"),
                 exclusions=("Refrigerant leak detection sensors (factory-provided with the rooftop units).",))
    job, _, _, ranked = _assemble([RTUS, VAVS], {"RTU": rtu, "VAV": vav})
    notes = [t for kind, t in _items(job, "Qty (2) Packaged Rooftop Unit RTU-1, 2") if kind == "note"]
    for note in ("*AIRFLOW MEASURING STATIONS BY UNIT MFR.", "*SMOKE DETECTORS BY UNIT MFR.",
                 "*REFRIGERANT LEAK DETECTION BY UNIT MFR."):
        assert note in notes, note
    assert not any("BY UNIT MFR" in t for _, t in _items(job, "Qty (3) VAV Box VAV-1 thru 3"))
    listed = " ".join(f"{r.decide} {r.evidence}" for r in ranked)
    assert "airflow measuring stations" not in listed.lower()
    assert "fire alarm panel" in listed.lower()


# --- 4. structure ----------------------------------------------------------------------------------------------------

def _garage(**kw):
    families = kw.pop("families", (
        Family("CO/NO Control Panel", (), 1, "S9", "Job 26-9999"),
        Family("CO Sensor", (), 9, "S9", "Job 26-9999"),
        Family("Garage Exhaust Fan GXF-C-1", ("GXF-C-1",), 1, "S9", "Job 26-9999"),
        Family("Nitrogen Dioxide Sensor", (), None, "", ""),
        Family("Garage Make-Up Air Fan", (), None, "", "")))
    return _planned("GAR", "Garage CO/NO Detection System", ("GXF-C-1",), 1, kind="CO Detection System",
                    families=families, **kw)


def test_a_stacked_header_prints_its_familys_count_never_one_and_hashes_when_nothing_counts_it():
    scope = _scope(_gl("Furnish and Install CO/NO Control Panel"), _gl("Furnish and Install CO Sensor"),
                   _gl("Furnish Garage Exhaust Fan Start/Stop and Status"),
                   _gl("Furnish and Install Nitrogen Dioxide Sensor (Qty. per Drawing)"))
    job, _, _, _ = _assemble([_garage()], {"GAR": scope})
    headers = _headers(job)
    assert headers[:4] == ["Qty (1) CO/NO Control Panel", "Qty (9) CO Sensor", "Qty (1) Garage Exhaust Fan GXF-C-1",
                           "Qty (##) Nitrogen Dioxide Sensor"]


def test_a_familys_count_the_gems_line_gives_goes_on_its_header():
    families = (Family("CO/NO Control Panel", (), 1, "S9", "Job 26-9999"), Family("CO Sensor", (), None, "", ""))
    scope = _scope(_gl("Furnish and Install CO/NO Control Panel"),
                   _gl("Furnish and Install CO Sensor (Qty. 9 Total)", quantity=9))
    job, _, _, _ = _assemble([_garage(families=families)], {"GAR": scope})
    assert _headers(job) == ["Qty (1) CO/NO Control Panel", "Qty (9) CO Sensor"]


def test_a_phantom_family_is_not_printed_and_becomes_the_top_question():
    scope = _scope(_gl("Furnish Garage Exhaust Fan Start/Stop and Status"),
                   _gl("Furnish Garage Make-Up Air Fan Start/Stop and Status (Qty. per Mechanical Schedule)",
                       flag="red", flag_text="no count"))
    job, _, _, ranked = _assemble([_garage()], {"GAR": scope})
    printed = " ".join(_printed(job))
    assert "Make-Up Air Fan" not in printed
    assert ranked[0].tier == TIER_FIRST and "Garage Make-Up Air Fan" in ranked[0].decide
    assert "exist" in ranked[0].decide


OUTDOOR_TEXT = TEXT + "\n[S30] D. Outdoor Air Fan: the outdoor air fan shall run in the occupied mode.\n"


def test_a_phantom_system_is_not_printed_even_when_the_sequence_has_a_section_for_it():
    dossier = _dossier(text=OUTDOOR_TEXT, sources=dict(SOURCES, S30="23 09 93, Specs.pdf page 46"))
    fan = _planned("OAF", "Outdoor Air Fan", (), None, kind="Supply Fan", quantity_source="", quantity_quote="",
                   sequence_sources=("S30",), sequence_section="Q9")
    job, _, _, ranked = _assemble([fan, FANS], {"OAF": _scope(_gl("Furnish Outdoor Air Fan Start/Stop and Status")),
                                                "EF": _scope(_gl("Furnish Fan Start/Stop and Status"))},
                                  dossier=dossier)
    assert _headers(job) == ["Qty (2) Exhaust Fan EF-1, 2"]
    assert ranked[0].tier == TIER_FIRST and ranked[0].decide.startswith("Does Outdoor Air Fan exist on this job?")


def _monitored(key, header, lines, **kw):
    return _planned(key, header, (), None, kind=kw.pop("kind", header), quantity_source="", quantity_quote="",
                    **kw), _scope(*(_gl(t) for t in lines))


def test_monitor_only_systems_stack_under_one_misc_monitoring_block():
    pumps, pumps_scope = _monitored("PP", "Plumbing Pumps", ["Furnish and Install Current Switch for Pump Status"])
    heaters, heaters_scope = _monitored("DWH", "Domestic Water Heaters",
                                        ["Furnish BMS Communication Wiring to Factory Controls",
                                         "Map Available Points Via Mfr. Provided BMS Interface"])
    generator = _planned("GEN", "Emergency Generator", (), 1, kind="Generator")
    gen_scope = _scope(_gl("Furnish and Install Emergency Generator BMS Interface"))
    glycol, glycol_scope = _monitored("GLY", "Domestic Water Glycol System",
                                      ["Furnish and Install DDC Controller", "Furnish Glycol System Alarm"])
    job, systems, _, _ = _assemble([FANS, pumps, heaters, glycol, generator],
                                   {"EF": _scope(_gl("Furnish Fan Start/Stop and Status")), "PP": pumps_scope,
                                    "DWH": heaters_scope, "GLY": glycol_scope, "GEN": gen_scope})
    headers = _headers(job)
    assert headers == ["Qty (2) Exhaust Fan EF-1, 2", "Qty (##) Plumbing Pumps", "Qty (##) Domestic Water Heaters",
                       "Qty (1) Emergency Generator", "Qty (##) Domestic Water Glycol System"]
    misc = next(s for s in systems if s.bundle_key == "Misc Monitoring Systems")
    assert [b.header for b in misc.blocks] == headers[1:4]
    assert [b.joined for b in misc.blocks] == [False, True, True]
    texts = [i.text for i in misc.blocks[-1].items]
    assert "Furnish and Install Current Switch for Pump Status" in texts and \
        "Furnish and Install Emergency Generator BMS Interface" in texts


# --- 5. AME's standard lines the GEM leaves out -----------------------------------------------------------------------

def _scope_lines(systems):
    return [line for s in systems for line in s.lines]


def test_the_standard_lines_are_data_and_stay_out_of_the_templates_options():
    raw = json.loads(TEMPLATES_FILE.read_text(encoding="utf-8"))
    marked = {s["name"]: [line["text"] for line in s["lines"] if line.get("standard")] for s in raw["systems"]}
    assert "Furnish and Install VAV Transformer" in marked["VAV / Fan VAV"]
    assert "Low Voltage Interlock Wiring between Indoor and Outdoor Unit" in marked["Split System"]
    assert "Furnish and Install Damper Actuator" in marked["Exhaust Fan"]
    assert "Furnish Fan Start / Stop and Status" in marked["Exhaust Fan"]
    packaged = next(t for t in load_templates() if t.name == "Packaged ERU / RTU / AHU")
    assert "Furnish and Install Damper Actuator" in [line.text for line in packaged.standard_lines]
    assert "Furnish and Install Damper Actuator" not in template_options(RTUS, load_templates())


def test_a_vav_without_a_transformer_line_gets_the_standard_one_marked_as_an_assumption():
    vav = _planned("VAV", "Variable Air Volume Box VAV-1 thru 3", ("VAV-1", "VAV-2", "VAV-3"), 3,
                   kind="Variable Air Volume Box")
    job, systems, _, _ = _assemble([vav], {"VAV": _scope(_gl("Furnish DDC Controller to the Factory for Installation"))})
    items = _items(job, "Qty (3) Variable Air Volume Box VAV-1 thru 3")
    at = items.index(("line", "Furnish and Install VAV Transformer"))
    assert items[at + 1] == ("note", STANDARD_NOTE)
    line = next(l for l in _scope_lines(systems) if l.text == "Furnish and Install VAV Transformer")
    assert (line.category, line.reference) == ("ASSUMPTION", STANDARD)


def test_a_transformer_the_unit_brings_is_the_by_unit_mfr_line_and_one_the_gem_wrote_is_not_added():
    vav = _planned("VAV", "Variable Air Volume Box VAV-1 thru 3", ("VAV-1", "VAV-2", "VAV-3"), 3,
                   kind="Variable Air Volume Box")
    scope = _scope(_gl("Furnish DDC Controller to the Factory for Installation"),
                   exclusions=("VAV terminals, SCR electric heating coils and control power transformers (by the "
                               "terminal manufacturer, schedule notes 3 and 4).",))
    job, _, _, _ = _assemble([vav], {"VAV": scope})
    texts = [t for _, t in _items(job, "Qty (3) Variable Air Volume Box VAV-1 thru 3")]
    assert "24V Transformer by Unit Mfr." in texts and "Furnish and Install VAV Transformer" not in texts
    written = _scope(_gl("Furnish DDC Controller to the Factory for Installation"), _gl("Run 24V Transformer Wiring"))
    job, _, _, _ = _assemble([vav], {"VAV": written})
    assert not any("VAV Transformer" in t for _, t in _items(job, "Qty (3) Variable Air Volume Box VAV-1 thru 3"))


def test_a_split_system_gets_its_indoor_outdoor_interlock_unless_the_gem_wrote_or_excluded_it():
    split = _planned("SS", "Split System CU-1, 2", ("CU-1", "CU-2"), 2, kind="Split System")
    job, _, _, _ = _assemble([split], {"SS": _scope(_gl("Furnish BMS Communication Wiring to Factory Controls"))})
    items = _items(job, "Qty (2) Split System CU-1, 2")
    at = items.index(("line", "Wire Low Voltage Interlock between Indoor and Outdoor Unit"))
    assert items[at + 1] == ("note", STANDARD_NOTE)
    excluded = _scope(_gl("Furnish BMS Communication Wiring to Factory Controls"),
                      exclusions=("Indoor-to-outdoor unit interconnect wiring and refrigerant piping (mechanical "
                                  "contractor).",))
    job, _, _, _ = _assemble([split], {"SS": excluded})
    assert not any("Indoor and Outdoor" in t for _, t in _items(job, "Qty (2) Split System CU-1, 2"))


DAMPER_TEXT = TEXT + ("\n[S31] B. Exhaust fans EF-1 and EF-2: the motorized damper shall open when the fan starts; the "
                      "damper end switch shall prove the damper open.\n")


def test_a_fan_with_a_damper_gets_the_damper_actuator_and_on_field_ddc_its_start_stop():
    dossier = _dossier(text=DAMPER_TEXT, sources=dict(SOURCES, S31="23 09 93, Specs.pdf page 45"))
    fans = dataclasses.replace(FANS, sequence_sources=("S31",))
    scope = _scope(_gl("Furnish and Install DDC Controller"),
                   quick_scan={"unit_type": "Field-Installed DDC", "controller": "CC Furnishes and Installs DDC "
                                                                                 "Controller"})
    job, _, _, _ = _assemble([fans], {"EF": scope}, dossier=dossier)
    texts = [t for _, t in _items(job, "Qty (2) Exhaust Fan EF-1, 2")]
    assert "Furnish and Install Damper Actuator w/ End Switch" in texts
    assert "Furnish Fan Start / Stop and Status" in texts
    wrote = _scope(_gl("Furnish and Install DDC Controller"), _gl("Furnish Exhaust Fan Start/Stop and Status"),
                   _gl("Furnish and Install Associated Damper Actuator Interlocked with the Fan"),
                   quick_scan={"unit_type": "Field-Installed DDC"})
    job, _, _, _ = _assemble([fans], {"EF": wrote}, dossier=dossier)
    texts = [t for _, t in _items(job, "Qty (2) Exhaust Fan EF-1, 2")]
    assert not any(t.startswith("Furnish and Install Damper Actuator") for t in texts)
    assert "Furnish Fan Start / Stop and Status" not in texts


FACTORY = {"unit_type": "Factory/OEM Controls", "controller": "Factory Controls — No CC DDC Controller",
           "blanket_wiring_clause": "No"}
FANS_DF = _planned("DF", "Destratification Fan DF-1 thru 4", ("DF-1", "DF-2", "DF-3", "DF-4"), 4,
                   kind="Destratification Fan")


def test_a_factory_units_device_ame_installs_and_wires_is_its_own_unit_mfr_line():
    remote = ("Mounting and wiring of the manufacturer's remote wall-mounted BACnet interface controller (and its "
              "wiring to the fans) — no party named; not carried")
    scope = _scope(_gl("Furnish BMS Communication Wiring to Factory Controls"),
                   quick_scan=FACTORY, contradictions=(Contradiction("C4", remote, (), "yellow"),),
                   exclusions=("Mounting of the remote wall-mounted BACnet interface controller and its wiring to the "
                               "fans (not assigned to the controls contractor).",
                               "Fire alarm relay and fire alarm panel programming (Fire Alarm Contractor)."))
    job, systems, _, _ = _assemble([FANS_DF], {"DF": scope})
    items = _items(job, "Qty (4) Destratification Fan DF-1 thru 4")
    text = "Install and Wire Remote Wall-Mounted BACnet Interface Controller (Furnished by Unit Mfr.)"
    at = items.index(("line", text))
    assert at + 1 == len(items) or not items[at + 1][1].startswith("*")        # no "*Assumed"
    assert [t for _, t in items].count(text) == 1
    line = next(l for l in _scope_lines(systems) if l.text == text)
    assert line.reference.startswith("Mounting and wiring of the manufacturer's remote")


def test_a_factory_units_device_wired_by_ame_is_a_wire_line_and_one_another_trade_wires_is_not_written():
    scope = _scope(_gl("Furnish BMS Communication Wiring to Factory Controls"), quick_scan=FACTORY,
                   contradictions=(Contradiction("C4", "Wiring of the unit condensate overflow switch to the factory "
                                                       "controller — no party named", (), "yellow"),
                                   Contradiction("C4", "Unit smoke detector alarm wiring to the building fire alarm "
                                                       "panel", (), "yellow")),
                   exclusions=("Wiring from unit smoke detectors to the building fire alarm panel (by the Fire Alarm "
                               "Contractor).",
                               "Factory supply and return smoke detectors (by the unit manufacturer)."))
    job, _, _, _ = _assemble([RTUS], {"RTU": scope})
    items = _items(job, "Qty (2) Packaged Rooftop Unit RTU-1, 2")
    assert ("line", "Wire Unit Condensate Overflow Switch (Furnished by Unit Mfr.)") in items
    assert not any("Smoke Detector" in t and kind == "line" for kind, t in items)
    assert ("note", "*SMOKE DETECTORS BY UNIT MFR.") in items


def test_a_device_the_documents_give_to_ame_on_a_factory_unit_keeps_its_own_verb():
    scope = _scope(_gl("Furnish and Install Discharge Air Temperature Sensor (Qty. 2 Total)", quantity=2),
                   _gl("Furnish BMS Communication Wiring to Factory Controls"), quick_scan=FACTORY,
                   contradictions=(Contradiction("C1", "Discharge Air Temperature Sensor — furnished by the ATC "
                                                       "Contractor per the sequence; the schedule shows a factory "
                                                       "sensor shipped loose", (), "yellow"),))
    job, _, _, _ = _assemble([RTUS], {"RTU": scope})
    texts = [t for _, t in _items(job, "Qty (2) Packaged Rooftop Unit RTU-1, 2")]
    assert "Furnish and Install Discharge Air Temperature Sensor (Qty. 2 Total)" in texts
    assert not any("Discharge Air Temperature Sensor (Furnished by Unit Mfr.)" in t for t in texts)


# --- 6. the review list: one row per decision ------------------------------------------------------------------------

def test_the_rows_of_one_assumption_are_one_row():
    scope = _scope(_gl("Furnish and Install Cabinet Unit Heater Lock-Out Interlock Relay (Qty. 4 Total)", flag="orange",
                       flag_text="Provide names no party; carried by CC."),
                   _gl("Furnish and Install Discharge Air Temperature Sensor", flag="yellow",
                       flag_text="Confirm whether the factory sensor satisfies this"),
                   _gl("Furnish and Install Current Switch (Qty. per Drawing)", flag="red", flag_text="no count"),
                   contradictions=(Contradiction("C5", "Cabinet unit heater lock-out interlock relays carried by CC",
                                                 (), "orange"),
                                   Contradiction("C1", "Discharge Air Temperature Sensor", ("by ATC", "by mfr"),
                                                 "yellow"),
                                   Contradiction("C6", "Current switch quantity", (), "red")),
                   review_notes=("C5 orange: interlock relays carried by CC though heading L names no party",),
                   qc=(QcCheck("QC-08", "relays 2 vs 1", False, "added"),))
    _, _, _, ranked = _assemble([FANS], {"EF": scope})
    mine = [r for r in ranked if r.system == "Exhaust Fan EF-1, 2" and not r.decide.startswith(("No tech hours",
                                                                                                  "Usually present"))]
    relay = [r for r in mine if "relay" in f"{r.decide} {r.evidence}".lower()]
    assert len(relay) == 1 and relay[0].category == "ASSUMPTION"
    assert len([r for r in mine if "Discharge Air Temperature Sensor" in r.decide]) == 1
    assert len([r for r in mine if "Current Switch" in r.decide or "Current switch" in r.decide]) == 1
    assert not any("QC-08" in r.decide for r in ranked)


def test_the_exclusions_are_one_row_per_job_without_what_the_standard_exclusions_cover():
    first = _scope(_gl("Furnish Fan Start/Stop and Status"),
                   exclusions=("Fire alarm relays by the Fire Alarm Contractor.",
                               "Line-voltage power wiring, disconnects and convenience outlets (by the Electrical "
                               "Contractor)."))
    second = _scope(_gl("Furnish BMS Communication Wiring to Factory Controls"),
                    exclusions=("Condensate piping, gas piping, curbs and ductwork (by the Mechanical Contractor).",
                                "Unit smoke detector wiring to the fire alarm panel (by the Fire Alarm Contractor)."))
    _, _, _, ranked = _assemble([FANS, RTUS], {"EF": first, "RTU": second})
    rows = [r for r in ranked if "xclusion" in r.decide]
    assert len(rows) == 1
    said = f"{rows[0].decide} {rows[0].evidence}"
    assert "Fire alarm relays" in said and "Unit smoke detector wiring" in said
    assert "convenience outlets" not in said and "Condensate piping" not in said


def test_the_same_row_for_two_systems_is_one_row():
    c4 = Contradiction("C4", "Unit smoke detector alarm wiring to the building fire alarm panel", (), "yellow")
    other = _planned("RTU2", "Packaged Rooftop Unit RTU-3", ("RTU-3",), 1, kind="Packaged Rooftop Unit")
    scopes = {k: _scope(_gl("Furnish BMS Communication Wiring to Factory Controls"), contradictions=(c4,))
              for k in ("RTU", "RTU2")}
    _, _, _, ranked = _assemble([RTUS, other], scopes)
    rows = [r for r in ranked if "Unit smoke detector alarm wiring" in r.decide]
    assert len(rows) == 1 and "RTU-1, 2" in rows[0].system and "RTU-3" in rows[0].system
