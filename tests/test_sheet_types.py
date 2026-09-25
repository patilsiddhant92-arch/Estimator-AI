import pytest

from estimator.catalogue.register import PageRecord
from estimator.catalogue.sheet_types import Sheet, SheetTypes, TYPES, classify_sheet, discipline_of, types_of
from estimator.catalogue.title_block import TitleBlock

READING = SheetTypes.load()


@pytest.mark.parametrize("title, types", [
    ("HVAC SCHEDULES SHEET 3", ("Schedules",)),
    ("HVAC VENTILATION SCHEDULES SHEET 2", ("Schedules",)),
    ("HVAC FIRST FLOOR PLAN", ("Plans",)),
    ("HVAC PIPING AND CONTROLS SECOND FLOOR PLAN", ("Plans",)),
    ("MECHANICAL 21ST FLOOR CONTROLS PLAN", ("Plans",)),
    ("HVAC AIR RISER DIAGRAM 1", ("Air riser", "Diagrams")),
    ("MECHANICAL HOT WATER AND STEAM RISER DIAGRAM", ("Water riser", "Diagrams")),
    ("MECHANICAL CONDENSER WATER RISER DIAGRAM", ("Water riser", "Diagrams")),
    ("HVAC CONTROL DIAGRAM SHEET 2 NETWORK ARCHITECTURE DIAGRAM", ("Network riser", "Control diagrams", "Diagrams")),
    ("HVAC CONTROL DIAGRAM SHEET 5 VAV BOX CONTROL DIAGRAMS", ("Control diagrams", "Diagrams")),
    ("MECHANICAL CONTROLS - II", ("Control diagrams",)),
    ("SECOND FLOOR RAS INSTRUMENT LOCATION", ("Plans", "Control diagrams")),   # a floor plan of instrument locations
    ("HVAC DETAILS SHEET 1", ("Details",)),
    ("HVAC SECTIONS AND ENLARGED PLAN SHEET 4", ("Plans", "Sections and elevations")),
    ("MECHANICAL 21ST FLOOR DEMOLITION PLAN", ("Plans", "Demolition")),
    ("MECHANICAL SPECIFICATIONS SHEET 1 OF 3", ("Specifications",)),
    ("HVAC SYMBOLS, ABBREVIATIONS, AND NOTES", ("Notes and legends",)),
    ("COVER SHEET AND DRAWING LIST", ("Notes and legends",)),
    ("ELECTRICAL - 21ST FLOOR LIGHTING RCP", ("Plans",)),
    ("PLUMBING SANITARY RISER DIAGRAM SHEET 3 OF 3", ("Water riser", "Diagrams")),
    ("ONE LINE DIAGRAM", ("Diagrams",)),
    ("MECHANICAL AIR FLOW DIAGRAMS", ("Air riser", "Diagrams")),
    ("CHILLED WATER FLOW DIAGRAM - DATA HALL 1100 & 2100", ("Water riser", "Diagrams")),
    ("SANITARY PIPING RISER DIAGRAM - SEGMENT E2", ("Water riser", "Diagrams")),
    ("LEVEL 01 - SECTOR D", ("Plans",)),
    ("HVAC - LEVEL ONE - OVERALL", ("Plans",)),
    ("FIRST FLOOR - POWER SYSTEMS", ("Plans",)),
    ("MECHANICAL VENTILATION COMPLIANCE", ("Notes and legends",)),
    ("ISOMETRIC VIEWS", ("Diagrams",)),
    ("CHILLED WATER PLANT 2 DCIM BMS/EPMS DIAGRAM", ("Network riser", "Control diagrams", "Diagrams")),
    ("PLUMBING AND DRAINAGE DRAWINGS LISTS AND SPECIAL INSPECTIONS", ("Notes and legends",)),
    ("MECHANICAL STEAM PRV STATION", ("Details",)),
    ("HVAC CHIMNEY VENT ANALYSIS", ()),
    (None, ()),
])
def test_types_from_the_title(title, types):
    assert types_of(title, READING) == types


@pytest.mark.parametrize("number, title, discipline", [
    ("M006.00", "HVAC SCHEDULES SHEET 3", "Mechanical"),
    ("H200.00", "SUB-SLAB DEPRESSURIZATION PLAN", "Mechanical"),
    ("H-100.00", "SECOND FLOOR ASBESTOS ABATEMENT PLAN", "Hazardous materials"),
    ("MD-103.00", "ROOF DEMOLITION PLAN", "Mechanical"),
    ("P101.00", "PLUMBING AND DRAINAGE FIRST FLOOR PLAN", "Plumbing"),
    ("E701.00", "TYPICAL DETAILS - 1", "Electrical"),
    ("IC015", "SECOND FLOOR RAS INSTRUMENT LOCATION", "Controls"),
    ("M00-03", "LEVEL 02 - OVERALL PLAN - MASTER MECHANICAL EQUIPMENT", "Mechanical"),
    ("T-001.00", "COVER SHEET AND DRAWING LIST", "Unknown"),     # T is a title sheet on one job, technology on another
    ("X-1", "SOMETHING", "Unknown"),
    (None, None, "Unknown"),
])
def test_discipline_from_the_title_first_then_the_letters(number, title, discipline):
    assert discipline_of(number, title, READING) == discipline


def test_a_sheet_record():
    record = PageRecord("mech.pdf", 6, "text", "…", 90)
    assert classify_sheet(record, TitleBlock("M006.00", "HVAC SCHEDULES SHEET 3"), READING) == \
        Sheet("mech.pdf", 6, "M006.00", "HVAC SCHEDULES SHEET 3", "Mechanical", ("Schedules",))


def test_the_type_names_are_the_reading_lists():
    assert tuple(t for t, _ in READING.types) == TYPES
