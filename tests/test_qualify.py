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


def test_c2_or_approved_equal_alone_on_a_minor_component_does_not_block():
    # 26-0246: a duct humidity sensor names Siemens with "or approved equal" — that's a
    # component brand, not the BAS platform, and must not turn a real Qualifies into Open.
    pages = _pages("2.1 SYSTEM\nA. The BMS shall be built on the Tridium Niagara 4 Framework.",
                   "2.7 SENSORS\nA. Duct RH/T Sensor: Siemens Model Number 538-896 or Kele GEH series "
                   "or approved equal.")
    bid = check_bid(pages, [CONTROLS])
    assert bid.finding == "Qualifies"


def test_c2_a_basis_of_design_label_inside_the_approved_list_itself_still_qualifies():
    # 26-0334: "Vykon (Basis of Design)" is the first item of the very list that also names
    # Honeywell WEBS, Johnson Controls FX and Niagara N4 as acceptable — the list wins, it's
    # not a contrary requirement against itself.
    pages = _pages("2.1 ACCEPTABLE MANUFACTURERS\nA. Vykon (Basis of Design)\nB. Delta,\nC. Distech\n"
                   "D. Siemens (Talon),\nE. Schneider Electric (TAC)\nF. Honeywell (WEBS)\nG. Johnson Controls (FX)\n"
                   "H. Or approved equal Niagara N4 based (open protocol standard) manufacturers are acceptable.")
    bid = check_bid(pages, [CONTROLS])
    assert bid.finding == "Qualifies"


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


def test_m6_only_alone_is_no_longer_sole_source_wording():
    # N2/M6: a bare "only" is not one of the explicit sole-source phrases any more — it names
    # Automated Logic, but doesn't bar a substitution on its own.
    pages = _pages("A. The building automation system shall be Automated Logic WebCTRL only.")
    bid = check_bid(pages, [CONTROLS])
    assert bid.finding == "Open" and "Automated Logic" in bid.reason


def test_m6_a_stray_only_inside_an_unrelated_list_does_not_block():
    # 26-0445: "Mains: Circuit breaker or Lugs only." sits inside a components list naming three
    # interchangeable manufacturers — a list is the opposite of sole-sourcing.
    pages = _pages("2.2 SYSTEM\nA. The BMS shall be built on the Tridium Niagara 4 Framework.",
                   "2.9 POWER PANELBOARDS\nA. Manufacturers: Subject to compliance, provide products by one "
                   "of the following: Schneider Electric, Siemens.\nB. Mains: Circuit breaker or Lugs only.")
    bid = check_bid(pages, [CONTROLS])
    assert bid.finding == "Qualifies"


# I7: what the check couldn't read, and a list that runs over a page break.

def test_i7_unread_spec_pages_are_admitted_in_the_reason():
    pages = [PageRecord("spec.pdf", 1, "text", "2.1 SYSTEM\nA. The BMS shall use Tridium Niagara.", 0),
             PageRecord("spec.pdf", 2, "unreadable", "", 0)]
    bid = check_bid(pages, [CONTROLS])
    assert "1 page of the specs could not be read (page 2)" in bid.reason
    assert "the check could not see them" in bid.reason


def test_i7_a_drawing_pages_unreadable_status_is_not_counted_as_a_spec_page():
    pages = [PageRecord("Marked_Mech.pdf", 1, "unreadable", "", 0, True)]
    sheet = Sheet("Marked_Mech.pdf", 1, "M-101", "ROOF PLAN", "Mechanical", ("Plans",))
    bid = check_bid(pages, [], {("Marked_Mech.pdf", 1): sheet})
    assert "could not be read" not in bid.reason


def test_i7_a_list_that_runs_over_a_page_break_keeps_its_heading():
    # The review's Siemens / Automated Logic / Honeywell example: the heading and the first two
    # items are on one page, the third item alone on the next.
    pages = [PageRecord("spec.pdf", 1, "text", "2.2 CONTROL SYSTEM\nA. Acceptable manufacturers:\n"
                                               "1. Siemens.\n2. Automated Logic.", 0),
             PageRecord("spec.pdf", 2, "text", "3. Honeywell.", 0)]
    bid = check_bid(pages, [CONTROLS])
    assert bid.finding == "Qualifies"
    assert any(m.listed == ("Honeywell",) for m in bid.mentions)


# M3: the same passage quoted from more than one copy is listed once, with all its places.

def test_m3_the_same_quote_from_two_copies_is_listed_once_with_both_places():
    text = "2.1 MANUFACTURERS\nA. The BMS shall be built on the Tridium Niagara 4 Framework."
    pages = [PageRecord("1. Project Documents/spec.pdf", 1, "text", text, 0),
             PageRecord("2. Takeoffs/spec.pdf", 1, "text", text, 0)]
    sections = [SpecSection("23 09 23", "INSTRUMENTATION AND CONTROL FOR HVAC", "1. Project Documents/spec.pdf", 1, 5),
                SpecSection("23 09 23", "INSTRUMENTATION AND CONTROL FOR HVAC", "2. Takeoffs/spec.pdf", 1, 5)]
    bid = check_bid(pages, sections)
    assert len(bid.mentions) == 1
    # the two copies share a file name, so the folder is given to tell them apart
    assert "1. Project Documents/spec.pdf, page 1" in bid.reason
    assert "2. Takeoffs/spec.pdf, page 1" in bid.reason


# M11: the deciding passage is one with list or sole-source wording, when there is one.

def test_m11_a_casual_mention_loses_to_the_approved_list_elsewhere():
    pages = _pages("2.1 The Niagara programming tool may be used by the controls contractor for "
                   "commissioning.",
                   "2.3 CONTROL SYSTEM\nA. Acceptable manufacturers: 1. Siemens. 2. Tridium Niagara.")
    bid = check_bid(pages, [CONTROLS])
    assert bid.finding == "Qualifies"
    assert "spec.pdf, page 2" in bid.reason and "spec.pdf, page 1" not in bid.reason


# --- Bid-check fix round: the controller's principle, re-derived directly (final-rereview.md) ---

NARROW_CONTROLS = SpecSection("23 09 23", "INSTRUMENTATION AND CONTROL FOR HVAC", "spec.pdf", 1, 1)


def test_26_0246_a_warranty_clause_with_only_is_not_sole_source_the_approved_list_decides():
    # 26-0246 (M11/N2): a warranty clause's "...the product only." must not be read as
    # sole-source wording — the approved list is what decides, and is what gets cited.
    pages = _pages("2.1 WARRANTY\nA. The manufacturer's warranty is limited to the extent of the product only.",
                   "2.9 CONTROL SYSTEM\nA. Acceptable manufacturers: 1. Honeywell. 2. Siemens.")
    bid = check_bid(pages, [CONTROLS])
    assert bid.finding == "Qualifies"
    assert "Honeywell" in bid.reason and "spec.pdf, page 2" in bid.reason
    assert "product only" not in bid.reason


def test_b1_a_formal_sole_source_list_naming_only_another_manufacturer_does_not_qualify():
    pages = _pages("Acceptable manufacturers: 1. Siemens. No substitutions.")
    bid = check_bid(pages, [NARROW_CONTROLS])
    assert bid.finding == "Does not qualify" and "Siemens" in bid.reason


def test_b1b_a_valves_list_naming_honeywell_without_controls_words_does_not_rescue_the_block():
    # 26-0445-shaped: the valves list is about control valves, not the controls system, and has
    # no strong HVAC-controls words — it never counts, so it can't turn Does not qualify into
    # Qualifies (and Honeywell was never named anywhere, so it stays Does not qualify).
    pages = _pages("Acceptable manufacturers: 1. Siemens. No substitutions.",
                   "2.9 CONTROL VALVES\nA. Manufacturers: one of the following: Belimo, Honeywell.")
    bid = check_bid(pages, [NARROW_CONTROLS])
    assert bid.finding == "Does not qualify"


def test_b1c_only_beside_a_sole_source_phrase_still_blocks_on_the_phrase_alone():
    pages = _pages("Manufacturers: Siemens Industry only. No substitutions.",
                   "2.9 CONTROL VALVES\nA. Manufacturers: one of the following: Belimo, Honeywell.")
    bid = check_bid(pages, [NARROW_CONTROLS])
    assert bid.finding == "Does not qualify" and "Siemens" in bid.reason


def test_b2_basis_of_design_for_the_bas_and_a_separate_valves_list_is_open():
    pages = _pages("2.1 BAS\nA. The basis of design is Automated Logic WebCTRL.",
                   "2.9 CONTROL VALVES\nA. Acceptable manufacturers: Belimo, Honeywell.")
    bid = check_bid(pages, [CONTROLS])
    assert bid.finding == "Open"


def test_b2b_masterspec_hyphenated_basis_of_design_is_open():
    # N4: "Basis-of-Design Product" must be recognised, hyphenated, same as "basis of design".
    pages = _pages("2.1 BAS\nA. Basis-of-Design Product: Subject to compliance with requirements, "
                   "provide Siemens Desigo CC or comparable product.",
                   "2.9 CONTROL VALVES\nA. Acceptable manufacturers: Belimo, Honeywell.")
    bid = check_bid(pages, [CONTROLS])
    assert bid.finding == "Open" and "Siemens" in bid.reason


def test_b2c_a_basis_of_design_heading_without_a_colon_is_not_a_list():
    pages = _pages("2.1 MANUFACTURERS\nA. Basis of Design: Siemens Desigo CC, or approved equal.",
                   "2.9 CONTROL VALVES\nA. Acceptable manufacturers: Belimo, Honeywell.")
    bid = check_bid(pages, [CONTROLS])
    assert bid.finding == "Open"


def test_b3_niagara_with_a_sensor_brand_or_approved_equal_in_the_same_article_qualifies():
    pages = _pages("2.1 SYSTEM\nA. The BAS shall be built on the Tridium Niagara 4 Framework.\n"
                   "B. Room Sensor: Siemens QAA2012 or approved equal.")
    bid = check_bid(pages, [CONTROLS])
    assert bid.finding == "Qualifies"


def test_b3b_niagara_with_a_separate_basis_of_design_sensor_article_is_open():
    pages = _pages("2.1 SYSTEM\nA. The BAS shall be built on the Tridium Niagara 4 Framework.",
                   "2.7 SENSORS\nA. Basis of design: Siemens QAA2012, or approved equal.")
    bid = check_bid(pages, [CONTROLS])
    assert bid.finding == "Open"


def test_b4_reference_only_wording_is_no_longer_sole_source():
    pages = _pages("2.1 SYSTEM\nA. The BAS shall be built on the Tridium Niagara 4 Framework.\n"
                   "B. Room Sensor: Siemens QAA2012 or equal. Sensor locations shown are for reference only.")
    bid = check_bid(pages, [CONTROLS])
    assert bid.finding == "Qualifies"


def test_c2_3c_basis_of_design_and_a_valves_list_adjacent_on_one_page_is_open():
    # The two articles merge into one passage — the basis-of-design clause still blocks, since
    # AME's own line is not the one on this list (N3: exempt only when it is).
    pages = _pages("2.1 BAS\nA. Basis of design: Siemens Desigo CC, or approved equal.\n"
                   "2.3 CONTROL VALVES\nA. Manufacturers: Subject to compliance, provide products by one "
                   "of the following: Belimo, Honeywell.")
    bid = check_bid(pages, [CONTROLS])
    assert bid.finding == "Open"


def test_c2_4b_metasys_by_johnson_controls_word_order_is_not_the_approved_list_item():
    pages = _pages("Acceptable manufacturers: 1. Metasys by Johnson Controls. 2. Siemens Desigo.")
    bid = check_bid(pages, [CONTROLS])
    assert bid.finding == "Open"
    assert bid.others == ("Johnson Controls Metasys", "Siemens")


def test_c2_4c_metasys_on_the_next_line_is_not_the_approved_list_item():
    pages = _pages("Acceptable manufacturers:\n1. Johnson Controls, Inc.\nMetasys Building Automation System\n"
                   "2. Siemens Desigo.")
    bid = check_bid(pages, [CONTROLS])
    assert bid.finding == "Open"
    assert bid.others == ("Johnson Controls Metasys", "Siemens")


def test_s1_a_security_network_riser_of_another_discipline_is_not_a_controls_mention():
    # 26-0445-shaped (S1/N1): a security riser typed Network riser is Technology, not Mechanical
    # or Controls, and has no strong HVAC-controls words — it never reaches the bid check.
    pages = _pages("SECURITY SYSTEM NETWORK RISER. ACCESS CONTROL: APPROVED MANUFACTURERS: "
                   "HONEYWELL PRO-WATCH, LENEL.", document="Marked_Sec.pdf")
    sheet = Sheet("Marked_Sec.pdf", 1, "TY-501", "SECURITY SYSTEM NETWORK RISER", "Technology", ("Network riser",))
    bid = check_bid(pages, [], {("Marked_Sec.pdf", 1): sheet}, has_spec_book=True)
    assert bid.mentions == () and bid.finding != "Qualifies"


def test_s2_the_security_riser_plus_a_real_sole_source_spec_does_not_qualify():
    pages = (_pages("A. The building automation system shall be Automated Logic WebCTRL. No substitutions.")
            + _pages("SECURITY SYSTEM NETWORK RISER. ACCESS CONTROL: APPROVED MANUFACTURERS: "
                     "HONEYWELL PRO-WATCH, LENEL.", document="Marked_Sec.pdf"))
    sheet = Sheet("Marked_Sec.pdf", 1, "TY-501", "SECURITY SYSTEM NETWORK RISER", "Technology", ("Network riser",))
    bid = check_bid(pages, [CONTROLS], {("Marked_Sec.pdf", 1): sheet})
    assert bid.finding == "Does not qualify"


def test_s3_an_electrical_specifications_sheet_does_not_block_a_real_qualifies():
    pages = (_pages("A. The BAS shall be Honeywell WEBs.")
            + _pages("CIRCUIT BREAKERS SHALL BE SIEMENS. THIS DRAWING IS FOR REFERENCE ONLY.",
                     document="Marked_Elec.pdf"))
    sheet = Sheet("Marked_Elec.pdf", 1, "E-600.00", "ELECTRICAL SPECIFICATIONS", "Electrical", ("Specifications",))
    bid = check_bid(pages, [CONTROLS], {("Marked_Elec.pdf", 1): sheet})
    assert bid.finding == "Qualifies"


def test_s3b_the_electrical_sheet_alone_with_no_spec_book_is_open_not_does_not_qualify():
    pages = _pages("CIRCUIT BREAKERS SHALL BE SIEMENS. THIS DRAWING IS FOR REFERENCE ONLY.",
                   document="Marked_Elec.pdf")
    sheet = Sheet("Marked_Elec.pdf", 1, "E-600.00", "ELECTRICAL SPECIFICATIONS", "Electrical", ("Specifications",))
    bid = check_bid(pages, [], {("Marked_Elec.pdf", 1): sheet}, has_spec_book=False)
    assert bid.finding == "Open" and bid.mentions == ()


def test_a_fan_coil_schedule_with_a_basis_of_design_column_never_counts():
    # N6: a sheet typed Schedules never carries the controls system's own scope, whatever it says.
    pages = (_pages("Acceptable manufacturers: 1. Honeywell. 2. Siemens.")
            + _pages("BASIS OF DESIGN MANUFACTURER: TRANE UNITRANE. BACNET INTERFACE REQUIRED FOR BMS "
                     "INTEGRATION.", document="Marked_Mech.pdf"))
    sheet = Sheet("Marked_Mech.pdf", 1, "M-701.00", "FAN COIL UNIT SCHEDULE", "Mechanical", ("Schedules",))
    bid = check_bid(pages, [CONTROLS], {("Marked_Mech.pdf", 1): sheet})
    assert bid.finding == "Qualifies"
    assert all(m.document != "Marked_Mech.pdf" for m in bid.mentions)


def test_26_0436_a_schneider_switchgear_reference_only_note_has_no_effect():
    pages = _pages("MV RING - UPPER NETWORK DIAGRAM E501.01. GENERAL NOTES: 1. REFERENCE SCHNEIDER DRAWINGS "
                   "FOR PROJECT SPECIFIC DETAIL. 2. SCHNEIDER TO PROVIDE PROJECT SPECIFIC NETWORK ARC DRAWINGS. "
                   "NOTE: This Drawing Is Provided For Reference Only. Refer to Schneider EIC "
                   "(Interconnect Drawings) For Project Specific Detail.", document="Marked_Elec.pdf")
    sheet = Sheet("Marked_Elec.pdf", 1, "E501.01", "MV RING - UPPER NETWORK DIAGRAM", "Electrical",
                 ("Network riser", "Diagrams"))
    bid = check_bid(pages, [], {("Marked_Elec.pdf", 1): sheet}, has_spec_book=True)
    assert bid.mentions == ()


def test_26_0328_a_trane_unit_heater_schedule_with_a_basis_of_design_column_has_no_effect():
    pages = _pages("CABINET UNIT HEATER SCHEDULE. BASIS OF DESIGN: TRANE, OR APPROVED EQUAL.",
                   document="Marked_Mech.pdf")
    sheet = Sheet("Marked_Mech.pdf", 1, "M07-03.00", "CABINET UNIT HEATER SCHEDULE", "Mechanical", ("Schedules",))
    bid = check_bid(pages, [], {("Marked_Mech.pdf", 1): sheet}, has_spec_book=True)
    assert bid.mentions == ()


# --- Bid check fix round 2: sentence scope (D2, D6) and the 24 re-review passages ---

def test_a1_a_no_substitutions_fragment_binds_to_ames_own_line_not_a_sensor_in_the_next_item():
    # A1: "No substitutions." is its own sentence naming nobody, right after AME's own line —
    # it binds there, in the same clause, not to Siemens two clauses later on a sensor item.
    pages = _pages("A. The BAS shall be built on the Tridium Niagara N4 Framework. No substitutions.\n"
                   "B. Space temperature sensors: Siemens QAA2012 or approved equal.")
    bid = check_bid(pages, [CONTROLS])
    assert bid.finding == "Qualifies"
    assert "requires Siemens" not in bid.reason


def test_a1b_a_no_substitutions_fragment_binds_to_honeywell_webs_not_a_removed_system():
    pages = _pages("A. The BAS shall be Honeywell WEBs-N4. No substitutions.\n"
                   "B. Existing Siemens Apogee controllers shall be removed and turned over to the Owner.")
    bid = check_bid(pages, [CONTROLS])
    assert bid.finding == "Qualifies"
    assert "requires Siemens" not in bid.reason


def test_a12_a_basis_of_design_with_or_approved_equal_is_open_not_a_false_sole_source():
    # A12: "No substitutions" sits with Belden cable, a maker AME doesn't track — it never binds
    # to Siemens's own basis-of-design sentence two clauses earlier.
    pages = _pages("A. Basis of Design: Siemens Desigo CC, or approved equal.\n"
                   "2.2 WIRE AND CABLE\nA. Communication cable shall be Belden 9841. No substitutions.")
    bid = check_bid(pages, [CONTROLS])
    assert bid.finding == "Open"
    assert "Does not qualify" not in bid.finding
    assert "basis of design" in bid.reason


def test_a13_a_review_stamp_is_not_sole_source_wording():
    # A13: "REVIEWED - NO EXCEPTIONS TAKEN" is a review stamp, not a sole-source phrase — "no
    # exceptions" is no longer read as one at all.
    pages = _pages("The existing Siemens Apogee field panels shall be replaced. REVIEWED - NO EXCEPTIONS TAKEN")
    bid = check_bid(pages, [CONTROLS])
    assert bid.finding == "Open"
    assert "Siemens" in bid.reason and "none of the lines AME bids" in bid.reason


# --- Bid check fix round 2: a plain "shall be <maker>" counts against Qualifies too (D1) ---

def test_a2_a_shall_be_competitor_sentence_blocks_even_with_honeywell_on_a_sensor_list():
    pages = _pages("The BAS shall be Automated Logic WebCTRL to match the campus standard.\n"
                   "2.5 SENSORS\nHumidity sensors: Manufacturers: subject to compliance, one of the "
                   "following: 1. Honeywell H7655. 2. Vaisala. 3. BAPI.")
    bid = check_bid(pages, [CONTROLS])
    assert bid.finding == "Open"


def test_a2b_substitutions_are_not_permitted_is_sole_source_wording_too():
    pages = _pages("The BAS shall be Siemens Desigo CC. Substitutions are not permitted.\n"
                   "2.9 CONTROL VALVES\nManufacturers: one of the following: Belimo, Honeywell.")
    bid = check_bid(pages, [CONTROLS])
    assert bid.finding == "Open"


def test_a5b_extension_of_the_existing_metasys_blocks_even_with_a_valves_list():
    pages = _pages("The BAS shall be an extension of the existing Johnson Controls Metasys Extended "
                   "Architecture.\nCONTROL VALVES Acceptable manufacturers: Belimo, Honeywell.")
    bid = check_bid(pages, [CONTROLS])
    assert bid.finding == "Open"


def test_a9_extension_of_existing_metasys_beats_a_duct_sensor_list():
    pages = _pages("CONTROLS GENERAL NOTES: THE BAS SHALL BE AN EXTENSION OF THE EXISTING JOHNSON "
                   "CONTROLS METASYS SYSTEM.\n2. DUCT SENSORS: ACCEPTABLE MANUFACTURERS: HONEYWELL, "
                   "BAPI, VERIS.")
    bid = check_bid(pages, [CONTROLS])
    assert bid.finding == "Open"


def test_a16_a_proprietary_specification_with_niagara_jaces_is_open():
    pages = _pages("This is a proprietary specification. The BAS shall be Automated Logic WebCTRL.\n"
                   "B. The ALC system shall integrate the existing Niagara JACEs in Building B via "
                   "BACnet/IP.")
    bid = check_bid(pages, [CONTROLS])
    assert bid.finding == "Open"
    assert "Niagara N4" in bid.reason


def test_a17_niagara_based_systems_are_not_acceptable_rejects_ames_own_lines():
    pages = _pages("Niagara-based systems, including Honeywell WEBs, are not acceptable.\n"
                   "B. Acceptable manufacturers: Siemens, Automated Logic.")
    bid = check_bid(pages, [CONTROLS])
    assert bid.finding == "Open"


def test_a18_an_ame_line_limited_to_ebi_is_open_not_qualifies():
    # A18: Honeywell is on a genuine acceptable-manufacturers list, but limited to EBI (not the
    # WEBs line AME bids) — an AME line with a limit is uncertain, so Open, never Qualifies.
    pages = _pages("Acceptable manufacturers: 1. Siemens. 2. Automated Logic. 3. Honeywell (EBI only, "
                   "integrated with the existing Honeywell EBI front end).")
    bid = check_bid(pages, [CONTROLS])
    assert bid.finding == "Open"
