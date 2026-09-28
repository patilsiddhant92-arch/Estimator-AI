"""The next batch (.superpowers/sdd/2026-09-26-whole-job-writing/next-batch-brief.md): clarifications in brackets at
the end of their line, the AME practice rules in the GEM prompt, the estimator's corrections read back, the
--documents input folder, the scoreboard and the requests folder cleaned. Synthetic data only."""
from __future__ import annotations

from estimator.writing.assemble import maker_line, with_clarifications
from test_gem_round2 import STANDARD_NOTE, Contradiction, _assemble, _gl, _items, _planned, _scope, _scope_lines

EDH = _planned("EDH", "Electric Duct Heater EDH-1 thru 3", ("EDH-1", "EDH-2", "EDH-3"), 3, kind="Electric Duct Heater")
EDH_HEADER = "Qty (3) Electric Duct Heater EDH-1 thru 3"


# --- 1. clarifications in brackets at the end of their line -----------------------------------------------------------

def test_a_clarification_goes_in_brackets_at_the_end_of_its_line():
    assert with_clarifications("Furnish and Install EDH DDC Controller (Qty. 3 Total)",
                               ["*Assumed: One electric duct heater DDC controller per heater assumed"]) == (
        "Furnish and Install EDH DDC Controller (Qty. 3 Total) "
        "(*Assumed: One electric duct heater DDC controller per heater assumed)")
    assert with_clarifications("Furnish Heater Enable", []) == "Furnish Heater Enable"
    twice = with_clarifications("Furnish X", ["*Confirm quantity: X", "*Confirm quantity: X"])
    assert twice == "Furnish X (*Confirm quantity: X)"


def test_the_assumed_confirm_quantity_and_standard_notes_print_on_their_lines_never_as_star_lines():
    scope = _scope(_gl("Furnish and Install EDH DDC Controller (Qty. 3 Total)", quantity=3, quote="Job 26-9999",
                       flag="orange", flag_text="One electric duct heater DDC controller per heater assumed"),
                   _gl("Furnish and Install Airflow Switch", flag="red", flag_text="No count on the drawings"))
    job, systems, _, _ = _assemble([EDH], {"EDH": scope})
    items = _items(job, EDH_HEADER)
    texts = [t for _, t in items]
    assert ("Furnish and Install EDH DDC Controller (Qty. 3 Total) "
            "(*Assumed: One electric duct heater DDC controller per heater assumed)") in texts
    assert any(t.startswith("Furnish and Install Airflow Switch (Qty. per Mechanical Schedule) (*Confirm quantity: ")
               for t in texts)
    assert not any(kind == "note" and t.startswith("*") and not t.startswith("**") for kind, t in items)
    scope_texts = [line.text for line in _scope_lines(systems)]
    assert not any(t.startswith("*Assumed") or t.startswith("*Confirm") for t in scope_texts)


def test_a_c5_assumption_goes_in_the_brackets_of_the_line_it_names():
    scope = _scope(_gl("Furnish and Install EDH DDC Controller"),
                   contradictions=(Contradiction("C5", "One EDH DDC controller per heater assumed", (), "orange"),))
    job, _, _, _ = _assemble([EDH], {"EDH": scope})
    texts = [t for _, t in _items(job, EDH_HEADER)]
    assert any(t.startswith("Furnish and Install EDH DDC Controller (*Assumed: ") for t in texts), texts


def test_a_manufacturer_device_ame_does_nothing_with_is_its_own_bracketed_line():
    assert maker_line("*REFRIGERANT LEAK DETECTION BY UNIT MFR.") == "(*Refrigerant Leak Detection by Unit Mfr.)"
    assert maker_line("*VAV CONTROLLER AND CO2 SENSOR BY UNIT MFR.") == "(*VAV Controller and CO2 Sensor by Unit Mfr.)"
    assert maker_line("**Owner to provide the network drop") == "**Owner to provide the network drop"


def test_the_furnished_by_unit_mfr_line_stays_in_the_house_form():
    scope = _scope(_gl("Install and Wire Space Thermostat (Furnished by Unit Mfr.)"),
                   quick_scan={"unit_type": "Factory/OEM Controls"})
    job, _, _, _ = _assemble([EDH], {"EDH": scope})
    (text,) = [t for kind, t in _items(job, EDH_HEADER) if kind == "line"]
    assert text.lower() == "install and wire space thermostat (furnished by unit mfr.)"


def test_the_standard_note_is_a_bracket_too():
    assert with_clarifications("Furnish and Install VAV Transformer", [STANDARD_NOTE]) == (
        "Furnish and Install VAV Transformer (*Assumed per AME standard — confirm)")
