from estimator.catalogue.overview import Place, build_overview, short_place
from estimator.catalogue.register import PageRecord
from estimator.catalogue.sheet_types import Sheet
from estimator.catalogue.spec_sections import SpecSection

DOC = "2. Takeoffs/1. Base Takeoff/Specs.pdf"


def _page(text: str, page: int = 1, document: str = DOC) -> PageRecord:
    return PageRecord(document, page, "text", text, 0)


def _found(overview, section: str, item: str):
    return next(t for t in overview.topics if t.section == section and t.item == item)


def test_a_controls_spec_sentence_is_found():
    page = _page("Provide BACnet MS/TP to each VAV controller.")
    sections = (SpecSection("23 09 23", "INSTRUMENTATION AND CONTROL FOR HVAC", DOC, 1, 1),)
    overview = build_overview([page], [], sections)
    tp = _found(overview, "Protocols", "BACnet MS/TP")
    assert tp.places[0].strength == "Controls spec"
    assert tp.quote == "Provide BACnet MS/TP to each VAV controller."
    any_mention = _found(overview, "Protocols", "BACnet (any mention)")
    assert any_mention.places


def test_a_page_outside_any_scope_is_not_searched():
    page = _page("Provide BACnet MS/TP to each VAV controller.")
    overview = build_overview([page], [], [])
    tp = _found(overview, "Protocols", "BACnet MS/TP")
    assert tp.places == () and tp.quote == ""
    assert any("BACnet MS/TP" in line for line in overview.not_found)


def test_electrical_drawing_needs_a_controls_word_in_the_same_sentence():
    page_with = _page("All BMS wiring shall be in EMT conduit.", page=1)
    page_without = _page("Provide EMT for all feeders.", page=2)
    sheets = [Sheet(DOC, 1, "E-101", "ELECTRICAL PLAN", "Electrical", ()),
              Sheet(DOC, 2, "E-102", "ELECTRICAL PLAN", "Electrical", ())]
    overview = build_overview([page_with, page_without], sheets, [])
    emt = _found(overview, "Electrical and conduit", "EMT conduit")
    assert len(emt.places) == 1
    assert emt.places[0].strength == "Electrical drawing" and emt.places[0].page == 1
    assert emt.quote == "All BMS wiring shall be in EMT conduit."


def test_carrier_sense_is_not_a_maker_but_a_rooftop_unit_is():
    controls_page = _page("Carrier Sense Multiple Access is not used here.", page=1)
    sections = (SpecSection("23 09 23", "INSTRUMENTATION AND CONTROL FOR HVAC", DOC, 1, 1),)
    mech_sheet_doc = "2. Takeoffs/1. Base Takeoff/Mech.pdf"
    mech_page = _page("CARRIER 48TC ROOFTOP UNIT", page=1, document=mech_sheet_doc)
    mech_sheet = Sheet(mech_sheet_doc, 1, "M-101", "MECHANICAL PLAN", "Mechanical", ())
    overview = build_overview([controls_page, mech_page], [mech_sheet], sections)
    carrier = next((m for m in overview.makers if m.maker == "Carrier"), None)
    assert carrier is not None
    assert carrier.places[0].document == mech_sheet_doc


def test_new_york_is_not_york_but_a_chiller_is():
    mech_doc = "2. Takeoffs/1. Base Takeoff/Mech.pdf"
    page1 = _page("New York, NY 10001", page=1, document=mech_doc)
    page2 = _page("YORK YCAL CHILLER", page=2, document=mech_doc)
    sheet1 = Sheet(mech_doc, 1, "M-001", "COVER SHEET", "Mechanical", ())
    sheet2 = Sheet(mech_doc, 2, "M-002", "SCHEDULES", "Mechanical", ())
    overview = build_overview([page1, page2], [sheet1, sheet2], [])
    york = [m for m in overview.makers if m.maker == "York"]
    assert len(york) == 1
    assert york[0].places[0].page == 2


def test_unit_price_is_not_price_industries_but_a_vav_box_is():
    mech_doc = "2. Takeoffs/1. Base Takeoff/Mech.pdf"
    page1 = _page("UNIT PRICE", page=1, document=mech_doc)
    page2 = _page("PRICE SDV VAV BOX", page=2, document=mech_doc)
    sheet1 = Sheet(mech_doc, 1, "M-001", "SCHEDULES", "Mechanical", ())
    sheet2 = Sheet(mech_doc, 2, "M-002", "SCHEDULES", "Mechanical", ())
    overview = build_overview([page1, page2], [sheet1, sheet2], [])
    price = [m for m in overview.makers if m.maker == "Price Industries"]
    assert len(price) == 1
    assert price[0].places[0].page == 2


def test_belimo_or_approved_equal_ame_quotes_it():
    page = _page("Actuators shall be Belimo or approved equal.")
    sections = (SpecSection("23 09 23", "INSTRUMENTATION AND CONTROL FOR HVAC", DOC, 1, 1),)
    overview = build_overview([page], [], sections)
    belimo = next(m for m in overview.makers if m.maker == "Belimo")
    assert belimo.ame_quotes is True
    assert belimo.terms == "Or approved equal"
    assert any("Broudy Precision — jchandler@broudyprecision.com; tsanroman@broudyprecision.com" == v for v in belimo.vendors)
    assert belimo.email_draft.startswith("Could you please provide the pricing for the Belimo - Actuators and dampers?")


def test_airflow_stations_vendors_include_technical_air_and_awacp():
    page = _page("Airflow stations shall be Ebtron.")
    sections = (SpecSection("23 09 23", "INSTRUMENTATION AND CONTROL FOR HVAC", DOC, 1, 1),)
    overview = build_overview([page], [], sections)
    ebtron = next(m for m in overview.makers if m.maker == "Ebtron")
    vendor_names = [v.split(" — ")[0] for v in ebtron.vendors]
    assert "Technical Air" in vendor_names and "AWACP" in vendor_names


def test_trane_on_a_mechanical_sheet_is_not_ame_quoted():
    mech_doc = "2. Takeoffs/1. Base Takeoff/Mech.pdf"
    page = _page("Trane", page=1, document=mech_doc)
    sheet = Sheet(mech_doc, 1, "M-101", "SCHEDULES", "Mechanical", ())
    overview = build_overview([page], [sheet], [])
    trane = next(m for m in overview.makers if m.maker == "Trane")
    assert trane.ame_quotes is False
    assert trane.vendors == ()
    assert trane.email_draft == ""


def test_the_strongest_place_comes_first_and_short_place_shows_it():
    mech_doc = "2. Takeoffs/1. Base Takeoff/Specs.pdf"
    mech_page = _page("Trane units are acceptable.", page=5, document=mech_doc)
    controls_page = _page("Trane units are acceptable.", page=40, document=mech_doc)
    sections = (
        SpecSection("23 05 00", "COMMON WORK RESULTS", mech_doc, 5, 5),
        SpecSection("23 09 23", "INSTRUMENTATION AND CONTROL FOR HVAC", mech_doc, 40, 40),
    )
    overview = build_overview([mech_page, controls_page], [], sections)
    trane = next(m for m in overview.makers if m.maker == "Trane")
    assert trane.places[0].strength == "Controls spec" and trane.places[0].page == 40
    assert short_place(trane.places) == "Specs.pdf · 23 09 23 · page 40  (+1 other)"


def test_no_gas_detection_maker_is_asked_about():
    page = _page("Nothing relevant here at all, just general notes about the job.")
    overview = build_overview([page], [], [])
    assert "No gas detection maker named — ask the engineer if the job needs one" in overview.not_found


def test_clean_text_runs_before_matching():
    page = _page("BACnet\x04MS/TP shall be provided.")
    sections = (SpecSection("23 09 23", "INSTRUMENTATION AND CONTROL FOR HVAC", DOC, 1, 1),)
    overview = build_overview([page], [], sections)
    tp = _found(overview, "Protocols", "BACnet MS/TP")
    assert tp.places


# The Learn check (real jobs, D:\Estimation Assistant\Learn) surfaced these false hits; each fix
# is a not_before/not_after word or a tighter pattern in the reading lists, never a job special-case.

def test_armstrong_armaflex_insulation_is_not_the_pump_maker():
    sections = (SpecSection("23 09 23", "INSTRUMENTATION AND CONTROL FOR HVAC", DOC, 1, 2),)
    no_hit = _page("Provide two coats of Armstrong Armaflex insulation on all exposed piping.")
    hit = _page("Pumps shall be Armstrong Series 4200 or approved equal.", page=2)
    overview = build_overview([no_hit, hit], [], sections)
    armstrong = [m for m in overview.makers if m.maker == "Armstrong"]
    assert len(armstrong) == 1 and armstrong[0].places[0].page == 2


def test_carrier_pipe_is_not_the_equipment_maker():
    sections = (SpecSection("23 09 23", "INSTRUMENTATION AND CONTROL FOR HVAC", DOC, 1, 3),)
    no_hit_singular = _page("Schedule 40 steel Carrier Pipe cleaned bare metal.")
    no_hit_plural = _page("Weld Carrier Pipes together at the joint.", page=2)
    hit = _page("Provide a Carrier chiller for the mechanical room.", page=3)
    overview = build_overview([no_hit_singular, no_hit_plural, hit], [], sections)
    carrier = [m for m in overview.makers if m.maker == "Carrier"]
    assert len(carrier) == 1 and carrier[0].places[0].page == 3


def test_price_based_on_and_price_as_are_not_price_industries():
    sections = (SpecSection("23 09 23", "INSTRUMENTATION AND CONTROL FOR HVAC", DOC, 1, 4),)
    no_hit_1 = _page("SUBMIT HIS PROPOSAL PRICE BASED ON SPECIFIED MANUFACTURER OR SUPPLIER.")
    no_hit_2 = _page("RESTROOM MANAGEMENT SYSTEM (PRICE AS ADD ALTERNATE).", page=2)
    no_hit_3 = _page("ADDITIONS OR DEDUCTIONS TO THE CONTRACT PROPOSAL PRICE; FOR ACCEPTANCE.", page=3)
    hit = _page("PRICE SDV VAV BOX", page=4)
    overview = build_overview([no_hit_1, no_hit_2, no_hit_3, hit], [], sections)
    price = [m for m in overview.makers if m.maker == "Price Industries"]
    assert len(price) == 1 and price[0].places[0].page == 4


def test_above_air_flow_direction_is_not_the_equipment_maker():
    sections = (SpecSection("23 09 23", "INSTRUMENTATION AND CONTROL FOR HVAC", DOC, 1, 2),)
    no_hit = _page("Threaded rod to structure above air flow direction, no scale.")
    hit = _page("Provide an Above Air PTHP unit at each mechanical closet.", page=2)
    overview = build_overview([no_hit, hit], [], sections)
    above_air = [m for m in overview.makers if m.maker == "Above Air"]
    assert len(above_air) == 1 and above_air[0].places[0].page == 2


def test_a_server_room_is_not_the_bms_server():
    sections = (SpecSection("23 09 23", "INSTRUMENTATION AND CONTROL FOR HVAC", DOC, 1, 2),)
    no_hit = _page("All exposed ducts in IT/server rooms shall be insulated.")
    hit = _page("TCC to provide network cable and integration to the BACnet Server.", page=2)
    overview = build_overview([no_hit, hit], [], sections)
    server = _found(overview, "Network and front end", "Server")
    assert [p.page for p in server.places] == [2]


def test_start_ups_is_not_a_ups():
    sections = (SpecSection("23 09 23", "INSTRUMENTATION AND CONTROL FOR HVAC", DOC, 1, 3),)
    no_hit_lower = _page("The Contractor shall schedule preliminary start-ups and testing.")
    no_hit_caps = _page("3.4 EQUIPMENT START-UPS", page=2)
    hit = _page("Provide UPS backup power to the control panel.", page=3)
    overview = build_overview([no_hit_lower, no_hit_caps, hit], [], sections)
    ups = _found(overview, "Network and front end", "UPS")
    assert [p.page for p in ups.places] == [3]


def test_a_controls_platform_maker_is_not_a_device_to_price():
    page = _page("The BAS shall be Honeywell WEBs N4.")
    sections = (SpecSection("23 09 23", "INSTRUMENTATION AND CONTROL FOR HVAC", DOC, 1, 1),)
    overview = build_overview([page], [], sections)
    honeywell = next(m for m in overview.makers if m.maker == "Honeywell")
    assert honeywell.priced is False
    assert honeywell.ame_quotes is False and honeywell.vendors == () and honeywell.email_draft == ""


def test_the_spec_overview_looks_for_a_sensaphone_or_auto_dialer():
    import json
    import re
    from pathlib import Path
    data = json.loads((Path(__file__).resolve().parents[1] / "assets" / "reading_lists" / "spec_overview.json")
                      .read_text(encoding="utf-8"))
    [topic] = [t for t in data["topics"] if t["item"] == "Auto dialer / Sensaphone"]
    assert topic["section"] == "Network and front end"
    for text in ("Provide a Sensaphone", "an auto dialer", "the auto-dialer", "AUTODIALER"):
        assert any(re.search(p, text, re.I) for p in topic["patterns"]), text
    assert not any(re.search(p, "the automatic dialog", re.I) for p in topic["patterns"])
