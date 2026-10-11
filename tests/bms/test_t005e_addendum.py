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
        "Furnish and Install Outside Air Damper Actuator (Qty. 4 per M-601; 2 per M-401)",
        "Furnish and Wire Hot Water Control Valve and Actuator",      # written Furnish and Install (GEM v4 ~228)
        "Interlock with Associated Exhaust Fan Operation",            # other Wire / interlock (18)
        "Furnish BMS Communication Wiring to VFD Controls",           # the integration group (19)
        "Map Available Points Via Mfr. Provided BMS Interface",
        "Demolition of Existing Pneumatic Tubing and Sensors",        # Miscellaneous Responsibilities (20)
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


# ---- format: no sub-headings, OR lines, one '*' note, quantity note on the line ------------------------------------

def test_no_sub_headings_over_stacked_headers(draft):
    assert lines(draft, "CHW", "header") == ["Qty (1) Chiller CH-1", "Qty (2) Chilled Water Pump CHWP-1, 2"]
    assert lines(draft, "HW", "header") == ["Qty (2) Boiler B-1, 2", "Qty (2) Hot Water Pump HWP-1, 2"]
    assert all(b.numbered for b in draft.scope.blocks)


def test_alternatives_print_an_or_line_and_only_the_first_is_priced(draft):
    assert lines(draft, "FSD") == ["Necessary Low Voltage Interlock Wiring",
                                   "Low Voltage Interlock with Associated Unit Fan Starter", "OR",
                                   "Furnish Open / Close Status to BMS via FSD End Switch"]
    block = next(b for b in draft.scope.blocks if b.header.startswith("Qty (4) Fire / Smoke"))
    assert [i.quantity for i in block.items] == [4, 4, None, None]
    assert [l.device_id for l in draft.lines if l.text == "OR"] == [None]


def test_one_star_note_per_block(draft):
    notes = lines(draft, "AHU", "note")
    assert notes == ["*Confirm quantity: invented damper count; Note: Start/Stop via Fire Alarm System; "
                     "Qty. (2) per M-601; 1 per M-201."]
    for key in ("AHU", "EF", "CHW", "HW", "FSD"):
        assert len([t for t in lines(draft, key, "note") if t.startswith("*")]) <= 1


def test_a_device_count_note_goes_on_its_own_line(draft):
    damper = next(t for t in lines(draft, "AHU") if "Outside Air Damper" in t)
    assert damper.endswith("(Qty. 4 per M-601; 2 per M-401)")
    assert "M-401" not in lines(draft, "AHU", "note")[0]


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
        ("header", "Seamlessly Tie in to the Existing Invented Net N9 BMS"),
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
