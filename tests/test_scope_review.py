"""The scope review sections of the Spec overview: potential scope AME needs to carry. Every case
here is a synthetic sentence; the words come from assets/reading_lists/scope_review.json."""
from estimator.catalogue.overview import (FOUND, NOT_FOUND, RULED_OUT, STANDARD_CLARIFICATION, STANDARD_EXCLUSION,
                                          build_overview, entries_without_a_template_line,
                                          template_lines_without_an_entry)
from estimator.catalogue.register import PageRecord
from estimator.catalogue.sheet_types import Sheet
from estimator.catalogue.spec_sections import SpecSection
from estimator.proposal.read import read_standard_lines
from conftest import PROPOSAL_TEMPLATE

DOC = "2. Takeoffs/1. Base Takeoff/Specs.pdf"
DRAWINGS = "2. Takeoffs/1. Base Takeoff/Drawings.pdf"


def _pages(*texts: str) -> list[PageRecord]:
    return [PageRecord(DOC, n, "text", t, 0) for n, t in enumerate(texts, start=1)]


def _controls_spec(*texts: str):
    """Each text on its own page of a 25 05 00 controls section."""
    return build_overview(_pages(*texts), [], (SpecSection("25 05 00", "INTEGRATED AUTOMATION", DOC, 1, len(texts)),))


def _line(overview, starts: str):
    return next((f for f in overview.standard_lines if f.item.startswith(starts)), None)


# --- the template's lines -----------------------------------------------------------------

def test_the_template_lines_are_read_from_the_proposal_template():
    clarifications, exclusions = read_standard_lines(PROPOSAL_TEMPLATE)
    assert clarifications[0].startswith("All labor will be performed during normal business working hours")
    assert "All water flow meters." in exclusions
    assert "All electric power meters." in exclusions
    assert not any(line.startswith("Exceptions and Exclusions") for line in clarifications + exclusions)


def test_every_template_line_has_an_entry_in_the_reading_list():
    assert template_lines_without_an_entry() == ()


def test_every_reading_list_entry_matches_a_template_line():
    assert entries_without_a_template_line() == ()


# --- the status of a row --------------------------------------------------------------------

def test_bacnet_ip_not_allowed_reads_ruled_out():
    overview = _controls_spec("Controllers shall be integrated via Modbus TCP. BACnet IP is not allowed anywhere "
                              "in the building.")
    bip = next(t for t in overview.topics if t.item == "BACnet/IP")
    assert bip.status == RULED_OUT
    assert bip.quote == "BACnet IP is not allowed anywhere in the building."
    assert bip.places and bip.places[0].page == 1
    assert not any(line.startswith("BACnet/IP") for line in overview.not_found)


def test_a_sentence_that_asks_for_it_reads_found():
    overview = _controls_spec("Provide BACnet/IP to each network controller.")
    assert next(t for t in overview.topics if t.item == "BACnet/IP").status == FOUND


def test_the_strongest_place_decides_ruled_out_over_a_weaker_mention():
    specs = PageRecord(DOC, 1, "text", "BACnet IP is not allowed anywhere in the building.", 0)
    drawing = PageRecord(DRAWINGS, 1, "text", "GATEWAY SHALL BE PROVIDED FOR BACNET IP INTEGRATION", 0)
    sheets = [Sheet(DRAWINGS, 1, "M-601", "SCHEDULES", "Mechanical", ())]
    overview = build_overview([specs, drawing], sheets, (SpecSection("25 05 00", "AUTOMATION", DOC, 1, 1),))
    bip = next(t for t in overview.topics if t.item == "BACnet/IP")
    assert bip.status == RULED_OUT and len(bip.places) == 2


def test_found_somewhere_on_the_strongest_level_is_found():
    overview = _controls_spec("BACnet IP is not allowed on the field bus.", "Provide a BACnet/IP router to the owner.")
    assert next(t for t in overview.topics if t.item == "BACnet/IP").status == FOUND


def test_not_found_has_no_places_and_no_quote():
    overview = _controls_spec("Nothing of interest here.")
    lon = next(t for t in overview.topics if t.item == "LonWorks")
    assert (lon.status, lon.places, lon.quote) == (NOT_FOUND, (), "")


# --- A. AME normally excludes this — the job asks for it --------------------------------------

def test_the_controls_contractor_furnishing_flow_meters_is_an_exclusion_hit():
    overview = _controls_spec("The BMS contractor shall furnish and install all chilled water flow meters.")
    found = _line(overview, "All water flow meters")
    assert found is not None and found.status == FOUND and found.section == STANDARD_EXCLUSION
    assert found.quote == "The BMS contractor shall furnish and install all chilled water flow meters."
    assert _line(overview, "The installation of dampers, valves, wells, water flow meters") is not None


def test_flow_meters_by_others_is_not_an_exclusion_hit():
    overview = _controls_spec("Flow meters by others.", "Flow meters shall be furnished and installed by others.",
                              "The Owner will provide the flow meters.",
                              "Flow meters shall be provided by the mechanical contractor.")
    assert _line(overview, "All water flow meters") is None


def test_valves_furnished_by_bms_but_installed_by_mechanical_is_not_an_installation_hit():
    overview = _controls_spec("Control valves shall be furnished by the BMS contractor and installed by the "
                              "mechanical contractor.")
    assert _line(overview, "The installation of control valves") is None
    assert _line(overview, "The installation of dampers, valves") is None


def test_an_exclusion_the_job_forbids_is_not_listed():
    overview = _controls_spec("The BMS contractor shall not provide power meters.")
    assert _line(overview, "All electric power meters") is None


def test_power_quality_meters_in_a_list_after_a_colon_are_a_hit():
    overview = _controls_spec("B. Power Quality Meters (PQM):\n1. Shall be installed at all transformer inlets.")
    found = _line(overview, "All electric power meters")
    assert found is not None
    assert "Shall be installed at all transformer inlets" in found.quote


def test_blue_bms_conduit_is_asked_for():
    overview = _controls_spec("All BMS conduit shall be of blue color.")
    assert _line(overview, "EMT or RGS conduit (if specified)") is not None


def test_gateways_and_hydrogen_detection():
    overview = _controls_spec("Provide all necessary protocol converters, gateways, or other interface devices.",
                              "Hydrogen detection panel shall be provided with a hardwired connection to the BMS.")
    assert _line(overview, "All equipment manufacturer integration/communication devices") is not None
    assert _line(overview, "Any gas detection system or components") is not None


def test_a_mechanical_spec_hit_needs_the_controls_contractor_named():
    mech = "2. Takeoffs/1. Base Takeoff/Mech Specs.pdf"
    pages = [PageRecord(mech, 1, "text", "Provide chilled water flow meters at each chiller.", 0),
             PageRecord(mech, 2, "text", "The BMS contractor shall provide flow meters at each chiller.", 0)]
    sections = (SpecSection("23 21 13", "HYDRONIC PIPING", mech, 1, 2),)
    found = _line(build_overview(pages, [], sections), "All water flow meters")
    assert found is not None and [p.page for p in found.places] == [2]
    assert found.places[0].strength == "Mechanical spec"


def test_a_clarification_is_listed_when_the_job_speaks_to_the_same_subject():
    overview = _controls_spec("All work in the data hall shall be performed after hours and on weekends.")
    found = _line(overview, "All labor will be performed during normal business working hours")
    assert found is not None and found.section == STANDARD_CLARIFICATION and found.status == FOUND


def test_a_clarification_the_job_forbids_reads_ruled_out():
    overview = _controls_spec("Plenum rated cable is not permitted in this building.")
    found = _line(overview, "All unexposed low voltage wiring outside of the mechanical equipment rooms")
    assert found is not None and found.status == RULED_OUT


def test_a_clarification_near_miss():
    overview = _controls_spec("The contractor shall coordinate with the architect.")
    assert overview.standard_lines == ()


def test_a_page_outside_the_places_searched_finds_nothing():
    pages = _pages("The BMS contractor shall furnish all water flow meters.")
    assert build_overview(pages, [], ()).standard_lines == ()


def test_a_title_block_issued_for_permit_is_not_a_permit_fee():
    overview = _controls_spec("ISSUE FOR PERMIT 1 03.13.2026 DESIGN DEVELOPMENT 1 Furnish and Install Controls",
                              "The BMS contractor shall obtain all required permits and pay all permit fees.")
    found = _line(overview, "Any Taxes and/or Permit Fees")
    assert found is not None and [p.page for p in found.places] == [2]


def test_patch_leads_are_not_patching():
    overview = _controls_spec("Provide project-specific installation kit (CAT6 patch leads, mounting hardware).")
    assert _line(overview, "All cutting, patching, and/or painting") is None
