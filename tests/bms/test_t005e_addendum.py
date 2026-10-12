"""T-005e addendum (lead, 2026-10-11): GEM v4 order and format, regression tests for the 26-0544 findings.

NOTES 2026-10-11 rule 4: every defect fixed here has a test built from an INVENTED copy of the failing pattern
(tests/bms/fixtures/t005e_addendum_job.json: invented names, tags, sheets and numbers; no job text).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path

import pytest
from docx import Document

from bms import order
from bms.labor import warranty_items, with_warranty
from bms.model import Job
from bms.playbook import load_playbook
from bms.render import printed_texts, render

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="module")
def house():
    return load_playbook()


@pytest.fixture
def job() -> Job:
    return Job.from_dict(json.loads((FIXTURES / "t005e_addendum_job.json").read_text(encoding="utf-8")))


@pytest.fixture
def draft(job, house):
    return render(job, house)


def lines(draft, key: str, kind: str | None = "line") -> list[str]:
    return [l.text for l in draft.lines if l.system_key == key and (kind is None or l.kind == kind)]


# ---- order (GEM v4 ~396-432; NOTES rule 7: catch-all slots in GEM order, not after the valves) ---------------------

def test_catch_all_lines_take_their_gem_place_among_the_template_lines(draft):
    assert lines(draft, "AHU") == [
        "Furnish and Install DDC Controller",
        "Furnish and Install Supply Air Temperature Sensor",
        "Furnish and Install Return Air CO2 Sensor",                  # catch-all sensor: with the sensors
        "Furnish Supply Fan Start/Stop and Status",
        "Furnish Supply Fan VFD Control",
        "Furnish Supply Fan VFD Fault",                               # catch-all point: with the fan signals
        "Furnish and Install Outside Air Damper Actuator (Qty. 4 Total) (4 per M-601; 2 per M-401)",   # ruling 15
        "Furnish and Wire Hot Water Control Valve and Actuator",      # written Furnish and Install (GEM v4 ~228)
        "Interlock with Associated Exhaust Fan Operation",            # other Wire / interlock (18)
        "Demolition of Existing Pneumatic Tubing and Sensors",        # plain work statement (19), lead ruling
        "Furnish BMS Communication Wiring to VFD Controls",           # the integration group (20): always last
        "Map Available Points Via Mfr. Provided BMS Interface",
    ]


def test_the_master_template_entry_sets_the_order_of_its_own_slots(draft):
    # the Master Template's Exhaust Fan prints its interlock first; a catch-all sensor goes in after the controller
    assert lines(draft, "EF") == [
        "Interlock with Associated AHU Operation", "Furnish and Install DDC Controller",
        "Furnish and Install Room Pressure Sensor", "Furnish Fan Start/Stop and Status",
        "Furnish and Install Motorized Damper Actuator"]


@pytest.mark.parametrize("template, p, expected", [
    ([18, 1, 8, 7], 2, 1.5),          # after the controller, before the fan signals
    ([1, 2, 8, 8, 14, 7, 16], 8, 3.5),  # after the template's last line of the same position
    ([1, 2, 8, 14, 7, 16], 7, 4.5),
    ([8, 16], 1, -0.5),               # nothing lower: first
    ([1, 2], 18, 1.5),                # nothing higher: last
])
def test_place_among_the_template_lines(template, p, expected):
    assert order.place(template, p) == expected


def test_the_vfd_integration_group_prints_first(job, house):
    from bms.model import Count, Device, Ref
    ref = Ref("Q1", "q", "23 09 93, Invented Specs.pdf page 7")

    def dev(n, slot, name):
        return Device(id=f"CHW.i{n}", slot=slot, name=name, verb="Furnish", furnished_by="AME", installed_by="AME",
                      wired_by="AME", quantity=Count(value=1), refs=(ref,))
    chw = job.system("CHW")
    extra = (dev(1, "comm_wiring", "BMS Communication Wiring to Chiller Factory Controls"),
             dev(2, "vfd_comm_wiring", "BMS Communication Wiring to VFD Controls"))
    out = lines(render(replace(job, systems=(replace(chw, devices=chw.devices + extra),)), house), "CHW")
    assert out.index("Furnish BMS Communication Wiring to VFD Controls") < out.index(
        "Furnish BMS Communication Wiring to Chiller Factory Controls")


# ---- format: group lines per entry, OR lines, one '*' note, quantity note on the line ------------------------------------

def test_the_master_template_group_line_over_stacked_headers(draft):
    # T-005e evening correction (lead, 2026-10-11): "no sub-headings" was wrong as a general rule; the Chilled Water
    # and Hot Water System entries print their group line over the stacked headers, so the blocks keep it
    assert lines(draft, "CHW", "header") == ["Chilled Water System", "Qty (1) Chiller CH-1",
                                             "Qty (2) Chilled Water Pump CHWP-1, 2"]
    assert lines(draft, "HW", "header") == ["Hot Water System", "Qty (2) Boiler B-1, 2",
                                            "Qty (2) Hot Water Pump HWP-1, 2"]
    assert [b.header for b in draft.scope.blocks if not b.numbered] == ["Chilled Water System", "Hot Water System"]


def test_alternatives_print_an_or_line_and_only_the_first_is_priced(draft):
    assert lines(draft, "FSD") == ["Necessary Low Voltage Interlock Wiring",
                                   "Low Voltage Interlock with Associated Unit Fan Starter", "OR",
                                   "Furnish Open / Close Status to BMS via FSD End Switch"]
    block = next(b for b in draft.scope.blocks if b.header.startswith("Qty (4) Fire / Smoke"))
    assert [i.quantity for i in block.items] == [4, 4, None, None]
    assert [l.device_id for l in draft.lines if l.text == "OR"] == [None]


def test_one_short_star_line_per_item_and_no_quantity_note(draft):
    # estimator ruling 14 (2026-10-11 afternoon): one short '*' line per item; ruling 15: no separate quantity note,
    # the family's other counts print on its header line
    assert lines(draft, "AHU", "note") == ["*Confirm quantity: invented damper count",
                                           "**Start/Stop via Fire Alarm System"]
    assert lines(draft, "AHU", "header") == ["Qty (2) Air Handling Units AHU-1, 2 (2 per M-601; 1 per M-201)"]
    assert not any(t.startswith("*Qty") for l in draft.lines for t in [l.text])


def test_a_device_quantity_prints_in_its_own_line(draft):
    # GEM v4 ~609 and estimator ruling 15: "Qty (#) <device>", its other counts after it
    damper = next(t for t in lines(draft, "AHU") if "Outside Air Damper" in t)
    assert damper == "Furnish and Install Outside Air Damper Actuator (Qty. 4 Total) (4 per M-601; 2 per M-401)"
    assert not any("M-401" in t for t in lines(draft, "AHU", "note"))


# ---- pumps (GEM v4 ~346-351), valves (~228, ~291-294) ------------------------------------------------------------

def test_a_pump_always_gets_vfd_control_fault_only_when_called(draft):
    chw = lines(draft, "CHW")
    assert chw[2:5] == ["Furnish Chilled Water Pump Start/Stop and Status", "Furnish Chilled Water Pump VFD Control",
                        "Furnish Chilled Water Pump VFD Fault"]
    assert not any("Speed Feedback" in t for t in chw)
    hw = lines(draft, "HW")
    assert hw.count("Furnish Hot Water Pump VFD Control") == 1          # written already: not added twice


def test_the_added_vfd_control_cites_the_start_stop_line_and_is_priced(draft):
    line = next(l for l in draft.lines if l.text == "Furnish Chilled Water Pump VFD Control")
    assert line.device_id == "CHW.d3.vfd" and line.quantity == 2


def test_no_vfd_control_is_added_on_factory_controls(job, house):
    rtu = job.system("RTU")
    from bms.model import Count, Device, Ref
    pump = Device(id="RTU.p", slot="other_point", name="Condensate Pump Start/Stop and Status", verb="Furnish",
                  furnished_by="AME", installed_by="AME", wired_by="AME", quantity=Count(value=1),
                  refs=(Ref("Q1", "q", "23 09 93, Invented Specs.pdf page 7"),))
    out = lines(render(replace(job, systems=(replace(rtu, devices=rtu.devices + (pump,)),)), house), "RTU")
    assert not any("VFD Control" in t for t in out)


def test_a_factory_unit_valve_is_not_a_line(draft):
    assert not any("Reheat Valve" in t for t in lines(draft, "RTU"))
    assert any(t.startswith("Hot Gas Reheat Valve: left out") for t in lines(draft, "RTU", "note"))
    assert not any("Reheat Valve" in i.text for b in draft.scope.blocks for i in b.items)


def test_printed_texts_leaves_out_or_lines_and_added_lines(job, house):
    from bms.citations import SourceIds
    ids = SourceIds.of_job(job)
    fsd = printed_texts(job.system("FSD"), house.shape("Fire / Smoke Dampers"), house, ids)
    assert "OR" not in [t for _, t in fsd]
    chw = printed_texts(job.system("CHW"), house.shape("Chilled Water System"), house, ids)
    assert "CHW.d3.vfd" not in [i for i, _ in chw]


# ---- the existing-BMS front end (template ~77-86): tie-in header, panel, graphics, training, warranty --------------

def test_the_existing_front_end_traces_its_tie_in_header_and_template_lines(draft):
    assert [(l.kind, l.text) for l in draft.lines if l.system_key == ""] == [
        ("header", "Seamlessly Tie in to the Existing Niagara N4 BMS"),
        ("line", "Furnish Network Level Control Panel"),
        ("line", "Furnish 3-D Graphics to match existing"),
        ("line", "Furnish Necessary Training on New Controls")]
    assert [i.text for i in draft.scope.front_end.items][0] == "Furnish Network Level Control Panel"   # the writer
    # prints the header from the mode: it is never an item


@dataclass(frozen=True)
class _Place:
    document: str = "Invented Specs.pdf"
    page: int = 9
    sheet: str | None = None
    section: str | None = "23 09 23"
    strength: str = "Division 23"


@dataclass(frozen=True)
class _Found:
    section: str
    item: str
    quote: str
    status: str = "Found"
    places: tuple = (_Place(),)
    amount: str = ""


@dataclass(frozen=True)
class _Overview:
    services: tuple = ()


WARRANTY = _Found("Services", "Warranty", "The invented warranty period shall be one year from acceptance.",
                  amount="one year")
NO_LENGTH = _Found("Services", "Warranty", "Provide an invented warranty.")


def test_the_warranty_prints_only_with_its_length(draft):
    assert [i.text for i in warranty_items(_Overview((WARRANTY,)))][0] == "Warranty scope of work-"
    assert warranty_items(_Overview((NO_LENGTH,))) == () and warranty_items(None) == ()
    out = with_warranty(draft, _Overview((WARRANTY,)))
    texts = [i.text for i in out.scope.front_end.items]
    assert texts[:4] == ["Furnish Network Level Control Panel", "Furnish 3-D Graphics to match existing",
                         "Furnish Necessary Training on New Controls", "Warranty scope of work-"]
    assert texts[4].startswith("a one-year preventative maintenance service contract")
    assert [l.text for l in out.lines if l.system_key == ""][-2] == "Warranty scope of work-"
    assert with_warranty(draft, _Overview((NO_LENGTH,))) is draft


# ---- the written proposal and price sheet ------------------------------------------------------------------------

def test_the_proposal_and_price_sheet_write_the_or_line(draft, tmp_path):
    from estimator.__main__ import ALIASES, PRICE_BOOK, PROPOSAL_TEMPLATE, WORKUP_TEMPLATE
    from estimator.price_sheet.price_book import PriceBook
    from estimator.price_sheet.write import write_price_sheet
    from estimator.proposal.write import write_proposal
    docx = write_proposal(draft.scope, PROPOSAL_TEMPLATE, tmp_path / "p.docx")
    write_price_sheet(draft.scope, WORKUP_TEMPLATE, PriceBook.load(PRICE_BOOK, ALIASES), tmp_path / "s.xlsx")
    text = [p.text.strip() for p in Document(str(docx)).paragraphs]
    fsd = text.index("Low Voltage Interlock with Associated Unit Fan Starter")
    assert text[fsd + 1] == "OR"


# ---- T-005e review (2026-10-11): should-fix items ----------------------------------------------------------------

@pytest.mark.parametrize("text, verb, expected", [
    ("Furnish Hot Water Valve Position Feedback", "Furnish", 10),     # GEM item 10, not the valves (16)
    ("Furnish and Wire Leak Detector", "Furnish and Wire", 4),        # by what it is, not by its verb
    ("Furnish and Wire Current Switch", "Furnish and Wire", 5),
    ("Furnish and Wire Outside Air Damper Actuator", "Furnish and Wire", 7),
    ("Furnish Heat Pump Start/Stop", "Furnish", 8),                   # a start/stop is a fan or pump signal
    ("Furnish and Install Relay Panel", "Furnish and Install", 6),    # a relay panel is relays, not a controller
    ("Furnish and Wire Steam Humidifier", "Furnish and Wire", 16),    # other Furnish and Wire devices: with the valves
])
def test_lines_get_their_gem_category_not_their_verb(text, verb, expected):
    assert order.position(text, verb) == expected


def test_an_overtime_ban_is_no_off_hours_work_but_a_call_beside_it_is():
    from bms.labor import calls_for_off_hours
    assert not calls_for_off_hours("Overtime is not permitted.")
    assert not calls_for_off_hours("No work after hours shall be allowed without the Owner's written approval.")
    assert calls_for_off_hours("No work in occupied areas by day; all such work shall be performed after hours.")
    assert calls_for_off_hours("Work in the lobby shall be done between 6:00 PM and 6:00 AM.")


def test_labor_conditions_reach_the_review_page_and_the_evidence_package_as_findings():
    from bms.labor import LABOR_RULE, labor_findings
    from estimator.scope import LaborCondition
    condition = LaborCondition(kind="prevailing-wage", text="DE Prevailing Wage Labor Rates Included (As per Spec "
                               "Section 00 73 46)", source="Spec Section 00 73 46",
                               quote="Pay the invented prevailing wage rates.")
    (finding,) = labor_findings((condition,))
    assert finding.rule == LABOR_RULE and finding.system_key == "" and finding.device_id is None
    assert finding.severity == "check" and "Spec Section 00 73 46" in finding.what and condition.quote in finding.what
    assert labor_findings(()) == ()
