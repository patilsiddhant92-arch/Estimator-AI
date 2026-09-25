"""The front end, the cover header and "based on", from hand-built Spec overviews, sheets and versions."""
import datetime as dt
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from estimator.catalogue.overview import FOUND, NOT_FOUND, RULED_OUT, Found, Place, SpecOverview
from estimator.catalogue.pdf import Span
from estimator.catalogue.qualify import BidCheck, Mention
from estimator.catalogue.register import PageRecord
from estimator.catalogue.sheet_types import Sheet
from estimator.catalogue.spec_sections import SpecSection
from estimator.proposal import layout
from estimator.reading.revisions import SheetVersion
from estimator.reading.schedules import Schedule
from estimator.reading.sequences import SEQUENCE, Backbone
from estimator.scope import FrontEnd, Header
from estimator.writing.front_end import FRONT_END_FILE, Evidence, front_end, job_header

SPEC = "Specs.pdf"
MECH = "Mech.pdf"
TODAY = dt.date(2026, 9, 25)
PLACE = Place(SPEC, 12, None, "23 09 23", "Controls spec")

TEMPLATE_TOPICS = ("BACnet/IP", "Operator workstation / front-end PC", "Server", "UPS", "Network switches",
                   "Tie-in to an existing system")


def _found(item, quote="", status=FOUND, section="Network and front end", amount=""):
    places = (PLACE,) if status != NOT_FOUND else ()
    return Found(section, item, places, quote if status != NOT_FOUND else "", status, amount)


def _overview(found=(), who=(), services=()):
    """found: {topic item: quote or (status, quote)}; everything else is Not found."""
    found = dict(found)
    topics = []
    for item in TEMPLATE_TOPICS:
        value = found.get(item)
        if value is None:
            topics.append(_found(item, status=NOT_FOUND))
        elif isinstance(value, tuple):
            topics.append(_found(item, value[1], status=value[0]))
        else:
            topics.append(_found(item, value))
    return SpecOverview(topics=tuple(topics),
                        who_does_what=tuple(_found("by the Owner", q, section="Who does what") for q in who),
                        services=tuple(services))


def _catalogue(overview=None, texts=(), folder="26-9999", sheets=(), pages=(), sections=None):
    """texts: words on a controls spec page (for the laptop / tablet search)."""
    records = [PageRecord(SPEC, 12, "text", text, 0) for text in texts] + list(pages)
    if sections is None:
        sections = (SpecSection("23 09 23", "Direct Digital Control System for HVAC", SPEC, 1, 50),)
    return SimpleNamespace(job=SimpleNamespace(name=folder.split(",")[0].strip(), root=Path("Learn") / folder),
                           pages=tuple(records), sheets=tuple(sheets), sections=tuple(sections),
                           overview=overview or _overview())


def _texts(fe: FrontEnd) -> list[str]:
    return [item.text for item in fe.items]


ALL_FOUND = {"Operator workstation / front-end PC": "Provide an operator workstation.",
             "Server": "Provide a BMS server.", "UPS": "Provide a UPS for the server.",
             "BACnet/IP": "The network shall be BACnet/IP."}


# --- the JSON ---------------------------------------------------------------------

def test_the_headings_match_what_the_proposal_writer_prints():
    data = json.loads(FRONT_END_FILE.read_text(encoding="utf-8"))
    assert data["headings"]["new-system"] == layout.NEW_SYSTEM_HEADING
    assert data["headings"]["extend-existing"].startswith(layout.EXISTING_SYSTEM_HEADING)


def test_the_wording_is_the_master_templates():
    data = json.loads(FRONT_END_FILE.read_text(encoding="utf-8"))
    new = [line["text"] for line in data["variants"]["new-system"]]
    assert new == ["Furnish Network Level Control Panel", "Furnish PC Workstation", "Furnish BMS Server",
                   "Furnish POT (Laptop or Tablet)",
                   "Furnish UPS – For workstation, server, network level control panel",
                   "Furnish 3-D Graphics", "Furnish Necessary Training on New Controls", "IT Infrastructure"]
    assert data["variants"]["new-system"][-1]["lines"] == ["Network Switches", "Panels", "Fiber – Ethernet"]
    assert [line["text"] for line in data["variants"]["extend-existing"]] == [
        "Furnish Network Level Control Panel", "Furnish 3-D Graphics to match existing",
        "Furnish Necessary Training on New Controls"]


# --- new versus extension ---------------------------------------------------------

def test_a_new_system_with_everything_found():
    fe, flags, evidence = front_end(_catalogue(_overview(ALL_FOUND), texts=["Provide one laptop computer."]))
    assert fe.mode == "new-system" and fe.existing_system_name is None
    assert _texts(fe) == ["Furnish Network Level Control Panel", "Furnish PC Workstation", "Furnish BMS Server",
                          "Furnish POT (Laptop or Tablet)",
                          "Furnish UPS – For workstation, server, network level control panel",
                          "Furnish 3-D Graphics", "Furnish Necessary Training on New Controls",
                          "IT Infrastructure", "Network Switches", "Panels", "Fiber – Ethernet"]
    assert [i.depth for i in fe.items][-4:] == [1, 2, 2, 2]
    assert all(run.bold for item in fe.items for run in item.runs)
    quantities = {item.text: item.quantity for item in fe.items}
    assert quantities["Furnish BMS Server"] == 1 and quantities["Furnish 3-D Graphics"] == 1
    assert quantities["Furnish Necessary Training on New Controls"] is None
    assert flags == []
    assert all(isinstance(e, Evidence) for e in evidence)
    server = next(e for e in evidence if e.line == "Furnish BMS Server")
    assert server.status == "CONFIRMED" and server.quote == "Provide a BMS server." and "23 09 23" in server.where
    graphics = next(e for e in evidence if e.line == "Furnish 3-D Graphics")
    assert graphics.status == "ASSUMPTION"


def test_a_new_system_with_nothing_found_keeps_only_the_defaults():
    fe, flags, _ = front_end(_catalogue())
    assert _texts(fe) == ["Furnish Network Level Control Panel", "Furnish 3-D Graphics",
                          "Furnish Necessary Training on New Controls"]


def test_the_portable_terminal_needs_its_words_in_the_controls_documents():
    assert "Furnish POT (Laptop or Tablet)" in _texts(front_end(_catalogue(texts=["A tablet for the operator."]))[0])
    assert "Furnish POT (Laptop or Tablet)" in _texts(front_end(_catalogue(texts=["Portable Operator Terminal"]))[0])
    assert "Furnish POT (Laptop or Tablet)" not in _texts(front_end(_catalogue(texts=["A tabletop display."]))[0])
    # a laptop in a page outside the controls documents doesn't count
    outside = PageRecord("Arch.pdf", 3, "text", "Provide a laptop.", 0)
    assert "Furnish POT (Laptop or Tablet)" not in _texts(front_end(_catalogue(pages=[outside]))[0])


def test_an_extension_of_an_existing_named_system():
    overview = _overview({"Tie-in to an existing system":
                          "Seamlessly integrate into the existing Honeywell WEBs Niagara front end.", **ALL_FOUND})
    fe, flags, evidence = front_end(_catalogue(overview))
    assert fe.mode == "extend-existing"
    assert fe.existing_system_name == "Honeywell / Niagara N4 / WEBs"
    assert _texts(fe) == ["Furnish Network Level Control Panel", "Furnish 3-D Graphics to match existing",
                          "Furnish Necessary Training on New Controls"]
    assert flags == []
    assert any(e.line.startswith("Seamlessly Tie in") and "Honeywell" in e.quote for e in evidence)


def test_an_extension_of_an_unnamed_system_is_flagged():
    overview = _overview({"Tie-in to an existing system": "Connect to the existing BMS in the building."})
    fe, flags, _ = front_end(_catalogue(overview))
    assert fe.mode == "extend-existing" and fe.existing_system_name == "[existing BMS name]"
    assert any("Name the existing BMS" in flag for flag in flags)


def test_a_ruled_out_tie_in_is_a_new_system():
    overview = _overview({"Tie-in to an existing system": (RULED_OUT, "Tie-in to the existing BMS is not allowed.")})
    assert front_end(_catalogue(overview))[0].mode == "new-system"


# --- the existing BMS name from the Bid check --------------------------------------

def _bid_check(*mentions):
    return BidCheck("Qualifies", "reason", (), tuple(mentions), ())


def _mention(quote, ours=(), listed=(), others=(), page=5):
    return Mention(document=SPEC, page=page, quote=quote, ours=ours, listed=listed, others=others)


def test_an_unnamed_tie_in_gets_its_name_from_the_bid_check():
    # 26-0478: the addendum names no manufacturer in the tie-in sentence itself, but the Bid check's
    # own passage does (test1-fixes.md 3.2).
    overview = _overview({"Tie-in to an existing system": "Connect to the existing BMS in the building."})
    bid_check = _bid_check(_mention("Existing BMS is a Johnson Controls Facility Explorer.",
                                    ours=("Johnson Controls FX",)))
    fe, flags, evidence = front_end(_catalogue(overview), bid_check=bid_check)
    assert fe.mode == "extend-existing" and fe.existing_system_name == "Johnson Controls"
    assert not any("Name the existing BMS" in f for f in flags)
    hit = next(e for e in evidence if e.line.startswith("Seamlessly Tie in"))
    assert "Johnson Controls Facility Explorer" in hit.quote and hit.status == "CONFIRMED"


def test_the_bid_check_is_not_used_when_the_tie_in_already_names_the_system():
    overview = _overview({"Tie-in to an existing system":
                          "Seamlessly integrate into the existing Honeywell WEBs Niagara front end."})
    bid_check = _bid_check(_mention("Also mentions Johnson Controls FX.", ours=("Johnson Controls FX",)))
    fe, _, _ = front_end(_catalogue(overview), bid_check=bid_check)
    assert fe.existing_system_name == "Honeywell / Niagara N4 / WEBs"


def test_no_bid_check_still_flags_the_unnamed_tie_in():
    overview = _overview({"Tie-in to an existing system": "Connect to the existing BMS in the building."})
    fe, flags, _ = front_end(_catalogue(overview))
    assert fe.existing_system_name == "[existing BMS name]"
    assert any("Name the existing BMS" in f for f in flags)


def test_a_bid_check_with_no_name_in_its_passages_still_flags():
    overview = _overview({"Tie-in to an existing system": "Connect to the existing BMS in the building."})
    bid_check = _bid_check(_mention("The spec names Siemens.", others=("Siemens",)))
    fe, flags, _ = front_end(_catalogue(overview), bid_check=bid_check)
    assert fe.existing_system_name == "[existing BMS name]"
    assert any("Name the existing BMS" in f for f in flags)


# --- by the owner, by others ------------------------------------------------------

def test_the_server_by_the_owner_is_a_client_note():
    who = ["The Owner will provide, install, and configure the following products: 1. Servers 2. Switches"]
    fe, flags, evidence = front_end(_catalogue(_overview(ALL_FOUND, who=who)))
    texts = _texts(fe)
    assert "Furnish BMS Server" not in texts
    assert "**BMS Server by Owner" in texts and "**Network Switches by Owner" in texts
    note = next(i for i in fe.items if i.text == "**BMS Server by Owner")
    assert note.kind == "note" and note.quantity is None
    assert "IT Infrastructure" not in texts          # the switches are the owner's too
    by_owner = next(e for e in evidence if e.line == "**BMS Server by Owner")
    assert by_owner.quote == who[0]


def test_approved_by_the_owner_is_not_provided_by_the_owner():
    who = ["Any server changes shall be approved by the Owner."]
    fe, _, _ = front_end(_catalogue(_overview(ALL_FOUND, who=who)))
    assert "Furnish BMS Server" in _texts(fe) and "**BMS Server by Owner" not in _texts(fe)


def test_a_location_determined_by_the_owner_is_not_furnished_by_the_owner():
    # test1-fixes.md 3.4: "Installed at a location determined by the owner" isn't enough — the server
    # is still furnished by the controls contractor.
    who = ["The server shall be installed at a location determined by the Owner."]
    fe, _, _ = front_end(_catalogue(_overview(ALL_FOUND, who=who)))
    assert "Furnish BMS Server" in _texts(fe) and "**BMS Server by Owner" not in _texts(fe)


def test_owner_furnished_is_enough_for_the_server_note():
    for phrase in ("provided by the owner", "owner furnished", "furnished by owner"):
        who = [f"The BMS server shall be {phrase}."]
        fe, _, _ = front_end(_catalogue(_overview(ALL_FOUND, who=who)))
        assert "**BMS Server by Owner" in _texts(fe), phrase


# --- the IT infrastructure lines --------------------------------------------------

def test_the_it_lines_need_bacnet_ip_found():
    without = {k: v for k, v in ALL_FOUND.items() if k != "BACnet/IP"}
    assert "IT Infrastructure" not in _texts(front_end(_catalogue(_overview(without)))[0])
    ruled_out = {**without, "BACnet/IP": (RULED_OUT, "BACnet IP is not allowed anywhere in the building.")}
    assert "IT Infrastructure" not in _texts(front_end(_catalogue(_overview(ruled_out)))[0])
    assert "IT Infrastructure" in _texts(front_end(_catalogue(_overview(ALL_FOUND)))[0])


def test_the_it_lines_are_left_out_when_the_network_is_by_others():
    who = ["Additionally, all BACnet/IP floor switches shall be furnished by FMSI and installed by TCC."]
    fe, _, _ = front_end(_catalogue(_overview(ALL_FOUND, who=who)))
    assert "IT Infrastructure" not in _texts(fe)
    assert "**Network Switches by Owner" not in _texts(fe)


def test_flow_switches_by_others_are_not_the_network():
    who = ["Flow switches shall be furnished by the mechanical contractor."]
    assert "IT Infrastructure" in _texts(front_end(_catalogue(_overview(ALL_FOUND, who=who)))[0])


def test_switches_furnished_by_the_controls_contractor_keep_the_it_lines():
    who = ["Managed switches shall be furnished by the TCC and installed by the Division 16 contractor."]
    assert "IT Infrastructure" in _texts(front_end(_catalogue(_overview(ALL_FOUND, who=who)))[0])


# --- warranty ---------------------------------------------------------------------

def _warranty(quote, amount):
    return Found("Services that cost hours", "Warranty", (PLACE,), quote, FOUND, amount)


def test_warranty_lines_with_the_length_stated():
    services = (_warranty("Provide a two (2) year warranty on all parts and labor.", "two (2) year"),)
    fe, flags, _ = front_end(_catalogue(_overview(services=services)))
    texts = _texts(fe)
    assert "Warranty scope of work-" in texts
    assert ("a two (2)-year preventative maintenance service contract covering all parts, materials, software, "
            "hardware, and all costs to provide software and hardware upgrades during the warranty period.") in texts
    assert not any(t.startswith("extend the maintenance") for t in texts)
    assert [i.depth for i in fe.items if "arrant" in i.text] == [1, 2]


def test_the_warranty_extension_with_its_years():
    services = (_warranty("The warranty is one year, then extend the maintenance service for four (4) additional "
                          "years.", "one year"),)
    texts = _texts(front_end(_catalogue(_overview(services=services)))[0])
    assert any(t.startswith("a one-year preventative") for t in texts)
    assert ("extend the maintenance service contract and the warranty for four additional years following the "
            "warranty period.") in texts


def test_a_warranty_with_no_length_is_flagged_not_printed():
    services = (_warranty("All work shall be under warranty.", ""),)
    fe, flags, _ = front_end(_catalogue(_overview(services=services)))
    assert not any("arrant" in t for t in _texts(fe))
    assert any("warranty" in flag.lower() for flag in flags)


# --- the header -------------------------------------------------------------------

def _sheet(number, page, discipline="Mechanical", document=MECH):
    return Sheet(document, page, number, "PLAN", discipline, ("Plans",))


def _version(number, page, latest, document=MECH):
    return SheetVersion(number, document, page, (), latest, "title block" if latest else "unknown")


def _title_block(*texts):
    return tuple(Span(t, 8.0, 0.85, 0.5 + i * 0.01, 0.95, 0.505 + i * 0.01) for i, t in enumerate(texts))


def test_the_header_from_the_folder_name_sheets_and_versions():
    sheets = [_sheet("M-001.00", 1), _sheet("M-101.00", 2), _sheet("M-701.00", 3),
              _sheet("E-101.00", 4, "Electrical"), _sheet("TC-001", 5, "Controls", "Controls.pdf")]
    versions = SimpleNamespace(versions=(
        _version("M-001.00", 1, dt.date(2026, 5, 1)), _version("M-101.00", 2, dt.date(2026, 6, 26)),
        _version("M-701.00", 3, None), _version("E-101.00", 4, dt.date(2026, 7, 1)),
        _version("TC-001", 5, dt.date(2026, 6, 1), "Controls.pdf")))
    firm = ("Project Architect/Engineer:", "HARTLAND ENGINEERING, DPC", "Architecture & Engineering")
    pages = [PageRecord(MECH, n, "text", "", 0, True, _title_block(*firm)) for n in (1, 2, 3)]
    catalogue = _catalogue(folder="26-0352, Tishman Speyer, 45 Rockefeller Suite 2100", sheets=sheets, pages=pages)
    header, flags = job_header(catalogue, versions, TODAY)
    assert isinstance(header, Header)
    assert header.quote_number == "26-0352"
    assert header.reference == "Tishman Speyer, 45 Rockefeller Suite 2100"
    assert header.mep_engineer == "HARTLAND ENGINEERING, DPC"
    assert header.date == TODAY and header.to == "All Bidders"
    assert header.based_on == ("M-001.00 Thru M-701.00 Dated: 06/26/2026", "TC-001 Dated: 06/01/2026")
    assert flags == []


def test_the_engineer_label_in_the_title_block_wins_even_with_no_corporate_suffix_word():
    # "GILLAN & HARTMANN, Inc." names no "engineer/consulting/associates" word of its own — only the
    # label beside it says what it is (test1-fixes.md 3.1, 26-0478's H601).
    pages = [PageRecord(MECH, 1, "text", "", 0, True, _title_block("ENGINEER", "GILLAN & HARTMANN, Inc."))]
    catalogue = _catalogue(folder="26-0478, Somerville HS", sheets=[_sheet("M-001", 1)], pages=pages)
    header, flags = job_header(catalogue, SimpleNamespace(versions=()), TODAY)
    assert header.mep_engineer == "GILLAN & HARTMANN, Inc."
    assert not any("engineer" in f.lower() for f in flags)


def test_the_mep_engineer_and_consulting_engineer_labels_are_recognised_too():
    for label in ("MEP ENGINEER", "MEP ENGINEER:", "CONSULTING ENGINEER"):
        pages = [PageRecord(MECH, 1, "text", "", 0, True, _title_block(label, "Doyle & Shea"))]
        catalogue = _catalogue(sheets=[_sheet("M-001", 1)], pages=pages)
        header, _ = job_header(catalogue, SimpleNamespace(versions=()), TODAY)
        assert header.mep_engineer == "Doyle & Shea", label


def test_another_title_block_label_beside_the_engineer_label_is_skipped():
    pages = [PageRecord(MECH, 1, "text", "", 0, True,
                        _title_block("ENGINEER", "SCALE:", "Doyle & Shea"))]
    catalogue = _catalogue(sheets=[_sheet("M-001", 1)], pages=pages)
    header, _ = job_header(catalogue, SimpleNamespace(versions=()), TODAY)
    assert header.mep_engineer == "Doyle & Shea"


def _spec_footer_pages(*, firm: str, count: int = 6) -> list[PageRecord]:
    return [PageRecord(SPEC, n, "text", f"Some spec text on page {n}.\n{firm}", 0) for n in range(1, count + 1)]


def test_the_engineer_falls_back_to_the_spec_page_footers():
    # 26-0193: no title-block label, but "MG Engineering D.P.C." is the most common name in the
    # spec's page footers (test1-fixes.md 3.1).
    pages = _spec_footer_pages(firm="MG Engineering D.P.C.")
    catalogue = _catalogue(folder="26-0193, Fordham Landing", sheets=[_sheet("M-001", 1)], pages=pages)
    header, flags = job_header(catalogue, SimpleNamespace(versions=()), TODAY)
    assert header.mep_engineer == "MG Engineering D.P.C."
    assert not any("engineer" in f.lower() for f in flags)


def test_the_spec_footer_fallback_is_the_most_common_name():
    pages = _spec_footer_pages(firm="MG Engineering D.P.C.", count=5)
    pages += [PageRecord(SPEC, 90, "text", "Odd page.\nSomeone Else Engineering, LLC", 0)]
    catalogue = _catalogue(sheets=[_sheet("M-001", 1)], pages=pages)
    header, _ = job_header(catalogue, SimpleNamespace(versions=()), TODAY)
    assert header.mep_engineer == "MG Engineering D.P.C."


def test_a_title_block_label_wins_over_the_spec_footer():
    pages = [PageRecord(MECH, 1, "text", "", 0, True, _title_block("ENGINEER", "Doyle & Shea"))]
    pages += _spec_footer_pages(firm="MG Engineering D.P.C.")
    catalogue = _catalogue(sheets=[_sheet("M-001", 1)], pages=pages)
    header, _ = job_header(catalogue, SimpleNamespace(versions=()), TODAY)
    assert header.mep_engineer == "Doyle & Shea"


def test_a_folder_with_only_a_number_and_no_firm_is_pending():
    sheets = [_sheet("M-001", 1), _sheet("M-002", 2)]
    versions = SimpleNamespace(versions=(_version("M-001", 1, None), _version("M-002", 2, None)))
    pages = [PageRecord(MECH, 1, "text", "", 0, True, _title_block("Engineer of Record:", "Texas Engineering Firm F-26237"))]
    header, flags = job_header(_catalogue(folder="26-0445", sheets=sheets, pages=pages), versions, TODAY)
    assert header.quote_number == "26-0445"
    assert header.reference == "[project name]"
    assert header.mep_engineer == "[MEP engineer]"
    assert header.based_on == ("M-001 Thru M-002 Dated: [date]",)
    assert len(flags) == 3
    assert any("project name" in f for f in flags) and any("engineer" in f.lower() for f in flags)
    assert any("date" in f.lower() for f in flags)


def test_sheets_sort_by_their_numbers_and_sets_split_by_letters():
    sheets = [_sheet("M-10", 1), _sheet("M-9", 2), _sheet("H-201", 3), _sheet("M-9", 4)]
    versions = SimpleNamespace(versions=tuple(_version(s.number, s.page, dt.date(2026, 3, 31)) for s in sheets))
    header, _ = job_header(_catalogue(folder="26-0246", sheets=sheets), versions, TODAY)
    assert header.based_on == ("M-9 Thru M-10 Dated: 03/31/2026", "H-201 Dated: 03/31/2026")


def test_no_mechanical_or_controls_sheets_is_pending():
    header, flags = job_header(_catalogue(folder="26-0001"), SimpleNamespace(versions=()), TODAY)
    assert header.based_on == ("[drawings the proposal is based on]",)
    assert any("based on" in f for f in flags)


def test_plumbing_sheets_are_part_of_based_on_too():
    sheets = [_sheet("P-101", 1, "Plumbing")]
    versions = SimpleNamespace(versions=(_version("P-101", 1, dt.date(2026, 4, 1), MECH),))
    header, flags = job_header(_catalogue(folder="26-0001", sheets=sheets), versions, TODAY)
    assert header.based_on == ("P-101 Dated: 04/01/2026",)
    assert not any("based on" in f for f in flags)


# --- "based on" and the controls spec sections --------------------------------------

def _schedule(document, page):
    return Schedule(document, page, None, "VAV BOX SCHEDULE", (), (), False, (), ())


def _backbone(document, first_page, last_page):
    return Backbone(SEQUENCE, "23 09 93 SEQUENCE OF OPERATIONS", document, first_page, last_page, "spec section")


def test_a_controls_spec_section_with_a_sequence_is_listed_with_its_date():
    sections = (SpecSection("23 09 93", "SEQUENCE OF OPERATIONS", SPEC, 40, 75),)
    pages = [PageRecord(SPEC, n, "text", "Some sequence text." if n != 75 else "Issued 06/26/2026", 0)
             for n in range(40, 76)]
    catalogue = _catalogue(folder="26-0001", sections=sections, pages=pages)
    reading = SimpleNamespace(versions=(), backbone=(_backbone(SPEC, 40, 75),), schedules=())
    header, flags = job_header(catalogue, reading, TODAY)
    assert header.based_on == ("23 09 93 SEQUENCE OF OPERATIONS Dated: 06/26/2026",)
    assert not any("based on" in f for f in flags)


def test_a_controls_spec_section_with_a_schedule_is_listed_too():
    sections = (SpecSection("23 09 23", "POINTS SCHEDULE", SPEC, 10, 12),)
    pages = [PageRecord(SPEC, n, "text", "Dated 01/15/2026", 0) for n in range(10, 13)]
    catalogue = _catalogue(folder="26-0001", sections=sections, pages=pages)
    reading = SimpleNamespace(versions=(), backbone=(), schedules=(_schedule(SPEC, 11),))
    header, _ = job_header(catalogue, reading, TODAY)
    assert header.based_on == ("23 09 23 POINTS SCHEDULE Dated: 01/15/2026",)


def test_a_controls_spec_section_with_neither_is_not_listed():
    sections = (SpecSection("23 09 00", "GENERAL REQUIREMENTS", SPEC, 1, 3),)
    pages = [PageRecord(SPEC, n, "text", "Dated 01/15/2026", 0) for n in (1, 2, 3)]
    catalogue = _catalogue(folder="26-0001", sections=sections, pages=pages)
    reading = SimpleNamespace(versions=(), backbone=(), schedules=())
    header, flags = job_header(catalogue, reading, TODAY)
    assert header.based_on == ("[drawings the proposal is based on]",)
    assert any("based on" in f for f in flags)


def test_an_undated_controls_spec_section_is_flagged():
    sections = (SpecSection("23 09 93", "SEQUENCE OF OPERATIONS", SPEC, 40, 41),)
    pages = [PageRecord(SPEC, n, "text", "No date printed anywhere on this page.", 0) for n in (40, 41)]
    catalogue = _catalogue(folder="26-0001", sections=sections, pages=pages)
    reading = SimpleNamespace(versions=(), backbone=(_backbone(SPEC, 40, 41),), schedules=())
    header, flags = job_header(catalogue, reading, TODAY)
    assert header.based_on == ("23 09 93 SEQUENCE OF OPERATIONS Dated: [date]",)
    assert any("23 09 93" in f and "date" in f.lower() for f in flags)


def test_based_on_with_no_schedules_or_backbone_attribute_is_unaffected():
    # A reading object that carries no .schedules / .backbone (older test fixtures) never breaks —
    # it just lists no spec sections.
    sheets = [_sheet("M-001", 1)]
    versions = SimpleNamespace(versions=(_version("M-001", 1, dt.date(2026, 1, 1)),))
    header, _ = job_header(_catalogue(folder="26-0001", sheets=sheets), versions, TODAY)
    assert header.based_on == ("M-001 Dated: 01/01/2026",)
