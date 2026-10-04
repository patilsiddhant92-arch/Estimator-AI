"""The final fix wave of house rules round 2 (2026-10-04), on invented jobs."""
from __future__ import annotations

from estimator.ledger.facts import SETTLED, Ledger
from estimator.ledger.to_plan import ledger_plan
from estimator.writing.assemble import _plain_assumption, system_template, tech_hours
from estimator.writing.style import load_house_style
from estimator.writing.templates import load_templates
from test_ledger_plan import VRF_SOURCES, _family_of

STYLE = load_house_style()
PLAN_ONLY = "Seen on the drawings but on no schedule; confirm it exists."


# --- a heat recovery unit is not a branch selector ------------------------------------------------------------

def test_a_heat_recovery_unit_with_a_fan_takes_the_packaged_entry_and_its_hours():
    ledger = Ledger(VRF_SOURCES)
    _family_of(ledger, "HRU", "Heat Recovery Unit", "HRU-1, HRU-2", 2)
    _family_of(ledger, "EF", "Exhaust Fan", "EF-1", 1)
    ledger.add("group", "Ventilation", "HRU, EF", "[S20]", "riser", "risers", SETTLED)
    (vent,) = ledger_plan(ledger).systems
    assert system_template(vent).name == "Packaged ERU / RTU / AHU"
    hours, _ = tech_hours(vent, 2, [], None)
    assert hours and hours > 0


def test_a_vrf_group_with_hru_branch_controllers_still_takes_the_vrf_entry():
    ledger = Ledger(VRF_SOURCES)
    _family_of(ledger, "HRU", "Branch Circuit Controller", "HRU-1", 1)
    _family_of(ledger, "IDU", "Indoor Unit", "IDU-1, IDU-2", 2)
    ledger.add("group", "Acme VRF", "HRU, IDU", "[S20]", "riser", "risers", SETTLED)
    (vrf,) = ledger_plan(ledger).systems
    assert system_template(vrf).name == "VRF System"
    ledger = Ledger(VRF_SOURCES)                     # no VRF word: the family's own name says branch controller
    _family_of(ledger, "HRU", "Branch Circuit Controller", "HRU-1", 1)
    _family_of(ledger, "IDU", "Indoor Unit", "IDU-1, IDU-2", 2)
    ledger.add("group", "Heat Pump Plant", "HRU, IDU", "[S20]", "riser", "risers", SETTLED)
    (plant,) = ledger_plan(ledger).systems
    assert system_template(plant).name == "VRF System"


# --- the reason may lead with "as", "since" or "given that" ---------------------------------------------------

def test_a_comma_as_reason_reads_as_a_reason():
    assert _plain_assumption("ASSUMED: duct static sensor shipped loose, as the schedule shows no factory sensor",
                             STYLE) == "Duct static sensor shipped loose, because the schedule shows no factory sensor"


def test_dash_as_and_dash_since_reasons_drop_their_lead_word():
    assert _plain_assumption("ASSUMED: sensor by AME — as the schedule shows none", STYLE) == \
        "Sensor by AME, because the schedule shows none"
    assert _plain_assumption("ASSUMED: sensor by AME — since the schedule shows none", STYLE) == \
        "Sensor by AME, because the schedule shows none"
    assert _plain_assumption("ASSUMED: sensor by AME, given that the schedule shows none", STYLE) == \
        "Sensor by AME, because the schedule shows none"


def test_an_as_with_no_comma_or_dash_is_no_reason():
    assert _plain_assumption("ASSUMED: thermostat furnished as part of the unit", STYLE) is None


def test_the_estimators_own_example_prints_with_its_reason():
    text = ("Duct static pressure sensor shipped loose by the unit manufacturer, as the schedule shows no factory "
            "sensor")
    assert _plain_assumption(text, STYLE) == ("Duct static pressure sensor shipped loose by the unit manufacturer, "
                                              "because the schedule shows no factory sensor")
    assert _plain_assumption(f"*Assumed: {text}".lstrip("*"), STYLE) == _plain_assumption(text, STYLE)


# --- a plan-only unit in a split block keeps its question -----------------------------------------------------

def test_a_plan_only_unit_gathered_into_a_split_block_keeps_its_existence_question():
    ledger = Ledger(VRF_SOURCES)
    _family_of(ledger, "AC", "Ductless Split Indoor Unit", "AC-1, AC-2", 2)
    _family_of(ledger, "ACCU", "Outdoor Unit", "ACCU-1, ACCU-2", None)        # seen on plans, not scheduled
    plan = ledger_plan(ledger)
    (split,) = plan.systems
    assert split.key == "Split System"
    assert PLAN_ONLY in split.why
    asks = [q for q in plan.unresolved if "ACCU-1" in q]
    assert asks == ["Outdoor Unit ACCU-1, ACCU-2 was seen on the drawings but is on no schedule; confirm it exists "
                    "(it is printed in the Split System block)"]
    assert not any("AC-1" in q and "ACCU" not in q for q in plan.unresolved)


# --- a bare tag range in a group is expanded ------------------------------------------------------------------

def test_a_bare_tag_range_member_takes_only_its_tags():
    ledger = Ledger(VRF_SOURCES)
    _family_of(ledger, "ACCU", "Condensing Unit", "ACCU-12-1, ACCU-12-2, ACCU-12-3, ACCU-14-1", 4)
    _family_of(ledger, "IDU", "Indoor Unit", "IDU-1", 1)
    ledger.add("group", "VRF-12", "ACCU-12-1 thru 3, IDU", "[S20]", "riser", "risers", SETTLED)
    systems = ledger_plan(ledger).systems
    vrf = next(s for s in systems if s.key == "VRF-12")
    assert vrf.families[0].tags == ("ACCU-12-1", "ACCU-12-2", "ACCU-12-3")
    rest = next(s for s in systems if s.key == "ACCU")
    assert rest.tags == ("ACCU-14-1",)


# --- the split system names an SS unit ------------------------------------------------------------------------

def test_the_split_system_names_an_ss_unit_an_indoor_unit():
    split = next(t for t in load_templates() if t.name == "Split System")
    assert split.family_names["SS"] == "Indoor Unit"
