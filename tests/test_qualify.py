from estimator.catalogue.qualify import ReadingList, check_bid
from estimator.catalogue.register import PageRecord
from estimator.catalogue.sheet_types import Sheet
from estimator.catalogue.spec_sections import SpecSection

CONTROLS = SpecSection("23 09 23", "INSTRUMENTATION AND CONTROL FOR HVAC", "spec.pdf", 1, 5)


def _pages(*texts, document="spec.pdf"):
    return [PageRecord(document, n, "text", t, 0) for n, t in enumerate(texts, start=1)]


def test_niagara_named_qualifies():
    pages = _pages("2.1 SYSTEM\nA. The BMS shall be built on the Tridium Niagara 4 Framework.")
    bid = check_bid(pages, [CONTROLS])
    assert bid.finding == "Qualifies"
    assert "Niagara N4" in bid.reason and "spec.pdf, page 1" in bid.reason
    assert bid.others == () and bid.controls_sections == ("23 09 23 INSTRUMENTATION AND CONTROL FOR HVAC",)
    assert "Tridium Niagara 4 Framework" in bid.mentions[0].quote


def test_an_approved_list_with_honeywell_qualifies_and_names_the_others():
    pages = _pages("2.2 CONTROL SYSTEM\nA. Available Manufacturers:\n1. Alerton Inc.\n2. Automated Logic Corporation.\n"
                   "3. Honeywell International Inc.\n4. Siemens Building Technologies.")
    bid = check_bid(pages, [CONTROLS])
    assert bid.finding == "Qualifies" and "Honeywell" in bid.reason
    assert bid.others == ("Alerton", "Automated Logic", "Siemens")


def test_another_manufacturer_as_basis_of_design_is_open():
    pages = _pages("2.1 MANUFACTURERS\nA. Basis of design: Siemens Desigo CC building automation system, or approved equal.")
    bid = check_bid(pages, [CONTROLS])
    assert bid.finding == "Open" and "Siemens" in bid.reason and bid.others == ("Siemens",)


def test_another_manufacturer_sole_source_does_not_qualify():
    pages = _pages("A. The building automation system shall be Automated Logic WebCTRL. No substitutions.")
    bid = check_bid(pages, [CONTROLS])
    assert bid.finding == "Does not qualify" and "Automated Logic" in bid.reason


def test_both_at_once_is_open_for_the_us_team():
    pages = _pages("A. The BMS shall be Automated Logic WebCTRL. No substitutions.",
                    "B. Integration to the owner's Niagara supervisor is required.")
    bid = check_bid(pages, [CONTROLS])
    assert bid.finding == "Open" and "two" in bid.reason


def test_silent_is_open():
    pages = _pages("PART 3 - EXECUTION\nA. Install the BMS per the drawings.")
    bid = check_bid(pages, [CONTROLS])
    assert (bid.finding, bid.others, bid.mentions) == ("Open", (), ())
    assert "names no controls manufacturer" in bid.reason


def test_no_controls_section_is_said_in_the_reason():
    bid = check_bid(_pages("Plumbing fixtures shall be by Kohler."), [])
    assert bid.finding == "Open" and "no controls section" in bid.reason


def test_a_name_outside_controls_is_ignored():
    pages = _pages("2.3 PACKAGED ROOFTOP UNITS\nA. Manufacturers: Trane, Carrier, Daikin.", document="hvac equipment.pdf")
    rooftop = SpecSection("23 74 13", "PACKAGED ROOFTOP UNITS", "hvac equipment.pdf", 1, 1)
    bid = check_bid(pages, [rooftop])
    assert (bid.finding, bid.others) == ("Open", ())


def test_a_name_with_controls_words_outside_a_controls_section_counts():
    pages = _pages("Unit controls shall be BACnet compatible for integration to the Siemens BMS.", document="equipment.pdf")
    bid = check_bid(pages, [])
    assert bid.others == ("Siemens",)


def test_metasys_is_not_the_line_we_bid():
    pages = _pages("A. The BMS shall be a Johnson Controls Metasys system.")
    bid = check_bid(pages, [CONTROLS])
    assert bid.finding == "Open" and bid.others == ("Johnson Controls Metasys",)


def test_names_in_capitals_are_found():
    pages = _pages("2.1 MANUFACTURERS\nA. SIEMENS BUILDING TECHNOLOGIES — BASIS OF DESIGN FOR THE BMS.")
    assert check_bid(pages, [CONTROLS]).others == ("Siemens",)


def test_carrier_in_lower_case_is_an_ordinary_word():
    pages = _pages("A. The BMS contractor shall coordinate with the telecom carrier for the internet connection.")
    assert check_bid(pages, [CONTROLS]).others == ()


def test_carrier_sense_is_a_network_term():
    pages = _pages("1. The BACnet IP network shall employ Carrier Sense Multiple Access/Collision Detection.")
    assert check_bid(pages, [CONTROLS]).others == ()


def test_a_drawing_specifications_sheet_is_searched_when_there_is_no_spec_book():
    # C1 / 26-0352: the specs live on a drawing sheet (typed Specifications), and the job has
    # no spec book at all — Distech must still be found, and named for the US team.
    pages = _pages("MECHANICAL SPECIFICATIONS SHEET 1 OF 2\nPROVIDE DISTECH ALLURE EC-SMART-AIR SERIES "
                   "DISTECH MICROPROCESSOR CONTROLLERS AND RELAYS.", document="Marked_Mech.pdf")
    sheet = Sheet("Marked_Mech.pdf", 1, "M-601.00", "MECHANICAL SPECIFICATIONS SHEET 1 OF 2", "Mechanical",
                 ("Specifications",))
    bid = check_bid(pages, [], {("Marked_Mech.pdf", 1): sheet}, has_spec_book=False)
    assert bid.others == ("Distech Controls",)
    assert bid.finding == "Open"
    assert "No spec book was found among the bid documents" in bid.reason
    assert any(m.sheet == "M-601.00" for m in bid.mentions)


def test_a_drawing_passage_is_quoted_by_its_sheet_number():
    pages = _pages("2.1 SYSTEM\nA. The BMS shall be built on the Tridium Niagara 4 Framework.", document="Marked_Mech.pdf")
    sheet = Sheet("Marked_Mech.pdf", 1, "M-601.00", "MECHANICAL SPECIFICATIONS", "Mechanical", ("Specifications",))
    bid = check_bid(pages, [], {("Marked_Mech.pdf", 1): sheet})
    assert "M-601.00 (Marked_Mech.pdf, page 1)" in bid.reason


def test_a_plans_sheet_with_a_controls_word_still_counts():
    pages = _pages("CONTROLS NOTE: THE BMS SHALL BE A JOHNSON CONTROLS METASYS SYSTEM.", document="Marked_Mech.pdf")
    sheet = Sheet("Marked_Mech.pdf", 1, "M-401", "ROOF PLAN", "Mechanical", ("Plans",))
    bid = check_bid(pages, [], {("Marked_Mech.pdf", 1): sheet})
    assert bid.others == ("Johnson Controls Metasys",)


def test_a_plans_sheet_without_a_controls_word_is_not_searched():
    pages = _pages("UNIT SCHEDULE: TRANE ROOFTOP UNIT MODEL RT-100.", document="Marked_Mech.pdf")
    sheet = Sheet("Marked_Mech.pdf", 1, "M-401", "ROOF PLAN", "Mechanical", ("Plans",))
    bid = check_bid(pages, [], {("Marked_Mech.pdf", 1): sheet})
    assert bid.mentions == ()


def test_the_reading_list_file_loads():
    reading = ReadingList.load()
    assert {"Honeywell WEBs", "Johnson Controls FX", "Niagara N4"} == {p.name for p in reading.ours}


ACCESS_CONTROL_TEXT = ("Access control panels and equipment shall be from a manufacturer with at least 5 years "
                       "of experience. Approved manufacturers: 1) Controllers/Panels: Honeywell 2) Readers: HID. "
                       "The access control system shall integrate with the BMS.")


def test_an_access_control_passage_outside_controls_is_not_a_mention():
    # 26-0445: this names Honeywell, but it's the building's security system, not HVAC controls.
    pages = _pages(ACCESS_CONTROL_TEXT, document="security.pdf")
    bid = check_bid(pages, [CONTROLS])
    assert bid.finding != "Qualifies"
    assert bid.mentions == ()


def test_the_same_access_control_passage_inside_a_controls_section_still_counts():
    pages = _pages(ACCESS_CONTROL_TEXT)
    bid = check_bid(pages, [CONTROLS])
    assert bid.finding == "Qualifies"
    assert bid.mentions != ()


# C2: "Qualifies" must never win over a contrary requirement in the same passage, a component
# list, or a Metasys list.

def test_c2_unacceptable_ours_with_another_manufacturer_required_is_open():
    pages = _pages("Systems based on Tridium Niagara or Honeywell WEBs shall be unacceptable. "
                   "The BAS shall be Siemens Desigo. No substitutions.")
    bid = check_bid(pages, [CONTROLS])
    assert bid.finding == "Open" and "two" in bid.reason
    assert "Siemens" in bid.reason


def test_c2_existing_ours_system_to_be_removed_and_replaced_is_open():
    pages = _pages("The existing building automation system is Honeywell WEBs and shall be removed. "
                   "The new BAS shall be Siemens Desigo. No substitutions.")
    bid = check_bid(pages, [CONTROLS])
    assert bid.finding == "Open" and "two" in bid.reason


def test_c2_a_separate_basis_of_design_article_beats_an_approved_list_elsewhere():
    pages = _pages("2.1 BAS\nA. Basis of design: Siemens Desigo CC, or approved equal.",
                   "2.3 CONTROL VALVES\nA. Manufacturers: Subject to compliance, provide products by one "
                   "of the following: Belimo, Honeywell.")
    bid = check_bid(pages, [CONTROLS])
    assert bid.finding == "Open"
    assert "Honeywell" in bid.reason and "Siemens" in bid.reason and "basis of design" in bid.reason


def test_c2_johnson_controls_metasys_does_not_read_as_the_approved_list_item():
    pages = _pages("Acceptable manufacturers: 1. Johnson Controls Metasys. 2. Siemens Desigo.")
    bid = check_bid(pages, [CONTROLS])
    assert bid.finding == "Open"
    assert bid.others == ("Johnson Controls Metasys", "Siemens")


# I9: Honeywell/Johnson Controls named outside a list is recorded, never counted toward
# Qualifies, and a sole-source word beside it gives Open.

def test_i9_honeywell_named_in_passing_is_recorded_not_dropped():
    pages = _pages("A. Coordinate with the owner's existing Honeywell system for tie-ins.")
    bid = check_bid(pages, [CONTROLS])
    assert bid.finding != "Qualifies"
    [mention] = bid.mentions
    assert mention.passing == (("Honeywell", "not WEBs"),)
    assert mention.named == "Honeywell (not on a list, not WEBs)"


def test_i9_honeywell_named_in_passing_with_sole_source_wording_is_open():
    pages = _pages("The BAS shall be Honeywell Enterprise Buildings Integrator (EBI). No substitutions.")
    bid = check_bid(pages, [CONTROLS])
    assert bid.finding == "Open"
    assert "Honeywell" in bid.reason and "not a line AME bids" in bid.reason


# M6: more sole-source wordings.

def test_m6_substitutions_will_not_be_accepted_is_sole_source():
    pages = _pages("A. The building automation system shall be Automated Logic WebCTRL. "
                   "Substitutions will not be accepted.")
    bid = check_bid(pages, [CONTROLS])
    assert bid.finding == "Does not qualify" and "Automated Logic" in bid.reason


def test_m6_only_at_the_end_of_a_sentence_is_sole_source():
    pages = _pages("A. The building automation system shall be Automated Logic WebCTRL only.")
    bid = check_bid(pages, [CONTROLS])
    assert bid.finding == "Does not qualify" and "Automated Logic" in bid.reason
