"""Workstream 4: the renderer, golden-text style, on the invented sample job and the sample Playbook only."""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from bms.model import (Assumption, Clarification, Count, Device, Family, FrontEnd, Job, OtherCount, Ref, System)
from bms.playbook import load_playbook
from bms.render import ProposalDraft, RenderedLine, RenderError, render

FIXTURES = Path(__file__).resolve().parent / "fixtures"
ROOT = Path(__file__).resolve().parents[2]
REF = Ref(source_id="S1", quote="q", where="M-1, Drawings.pdf page 1")


@pytest.fixture(scope="module")
def playbook():
    return load_playbook(FIXTURES / "sample_playbook")


@pytest.fixture
def job() -> Job:
    return Job.from_dict(json.loads((FIXTURES / "sample_job.json").read_text(encoding="utf-8")))


@pytest.fixture
def draft(job, playbook) -> ProposalDraft:
    return render(job, playbook)


def texts(draft: ProposalDraft, key: str) -> list[str]:
    return [l.text for l in draft.lines if l.system_key == key]


def device(slot="controller", name="DDC Controller", qty: int | None = 2, **kw) -> Device:
    base = dict(id="X.d1", slot=slot, name=name, verb="Furnish and Install", furnished_by="AME", installed_by="AME",
                wired_by="AME", quantity=Count(value=qty), refs=(REF,))
    base.update(kw)
    return Device(**base)


def system(devices=(), families=None, **kw) -> System:
    base = dict(key="EF", name="Exhaust Fans", shape="Exhaust Fan", control="field",
                families=families or (Family("Exhaust Fan", ("EF-1", "EF-2"), Count(value=2)),), devices=tuple(devices))
    base.update(kw)
    return System(**base)


def one(job: Job, sys: System) -> Job:
    return replace(job, systems=(sys,))


# ---- golden text ---------------------------------------------------------------------------------------------

def test_rooftop_block_golden(draft):
    assert texts(draft, "RTU") == [
        "Qty (2) Rooftop Units RTU-1, 2",
        "Furnish BMS Communication Wiring to RTU Factory Controls",
        "Map Available Points Via Mfr. Provided BMS Interface",
        "AME requires mfr. Rep to assist in integration, cost to be incurred by mech contractor",
        "Install and Wire Duct Smoke Detector (Furnished by Unit Mfr.)",
        "*one detector per unit, because the schedule note names a detector for each unit without a count",
        "*Unit count carried at 2; the roof plan shows 1",
        "*Qty. (2) per M-001; 1 per M-101.",
    ]


def test_exhaust_fan_block_golden(draft):
    assert texts(draft, "EF") == [
        "Qty (3) Exhaust Fans EF-1 thru 3",
        "Furnish and Install DDC Controller",
        "Furnish Fan Start / Stop and Status",
        "Furnish and Install Motorized Damper Actuator (Qty. 2)",
    ]


def test_vrf_stacks_one_header_per_family_over_one_set_of_lines(draft):
    assert texts(draft, "VRF")[:3] == ["Qty (4) Indoor Unit FCU-1 thru 4", "Qty (1) Condensing Unit CU-1",
                                       "Qty (2) Branch Selector BS-1, 2"]
    blocks = [b for b in draft.scope.blocks if b.header.startswith(("Qty (4) Indoor", "Qty (1) Cond", "Qty (2) Branch"))]
    assert [b.joined for b in blocks] == [False, True, True]
    assert blocks[0].items == () and blocks[1].items == () and blocks[2].items
    assert blocks[0].tech_hours == 6.0 and blocks[2].tech_hours is None
    assert "Furnish BMS Communication Wiring to VRF Factory Controls" in texts(draft, "VRF")
    assert "Wire BACnet Gateway (Furnished by Unit Mfr.)" in texts(draft, "VRF")


def test_unknown_count_prints_hashes_and_quantity_unknown(draft):
    cuh = texts(draft, "CUH")
    assert cuh[0] == "Qty (##) Cabinet Unit Heaters"
    assert cuh[1] == "Furnish and Install Space Temperature Sensor (Qty. ##)"
    assert cuh[2].startswith("*one sensor per heater, because ")
    assert cuh[3] == "*Cabinet unit heater quantity as per drawings"


def test_confirm_note_and_count_note_for_vrf(draft):
    notes = [l.text for l in draft.lines if l.system_key == "VRF" and l.kind == "note"]
    assert notes == ["*Branch selector count: 2 on the plan picture, 1 on the schedule - to be confirmed",
                     "*Qty. (2) per M-102; 1 per M-002."]


def test_front_end_exceptions_and_alternates(draft):
    scope = draft.scope
    assert [i.text for i in scope.front_end.items] == ["Furnish and Install BMS Server Software and Graphics"]
    assert scope.front_end.mode == "new-system" and scope.front_end.tech_hours == 8.0
    assert scope.named_exceptions == ("Fire alarm system by others",)
    assert [b.header for b in scope.blocks if "Duct Heaters" in b.header] == []
    assert len(scope.add_alternates) == 1 and scope.deduct_alternates == ()
    alt = scope.add_alternates[0].blocks[0]
    assert alt.header == "Qty (2) Duct Heaters DH-1, 2" and alt.tech_hours == 4.0
    assert [l.text for l in draft.lines if l.system_key == "DH"][0] == alt.header
    assert [l.system_key for l in draft.lines][-1] == "DH"          # alternates print after the base scope


def test_header_comes_from_the_job(draft):
    h = draft.scope.header
    assert (h.quote_number, h.reference, h.mep_engineer, h.to) == ("00-0000", "Sample Clinic (invented test job)",
                                                                  "Sample Engineering", "All Bidders")
    assert h.date.isoformat() == "2026-10-04" and len(h.based_on) == 2


# ---- the price sheet rows ------------------------------------------------------------------------------------

def test_tech_hours_go_on_the_block_header(draft):
    by_header = {b.header: b.tech_hours for b in draft.scope.blocks}
    assert by_header["Qty (2) Rooftop Units RTU-1, 2"] == 4.0
    assert by_header["Qty (3) Exhaust Fans EF-1 thru 3"] == 12.0
    assert by_header["Qty (##) Cabinet Unit Heaters"] is None


def test_item_quantities_price_only_what_ame_acts_on_and_never_under_a_hash_count(draft):
    blocks = {b.header: b for b in draft.scope.blocks}
    rtu = blocks["Qty (2) Rooftop Units RTU-1, 2"]
    assert [i.quantity for i in rtu.items][:4] == [2, 2, None, 2]      # the rep line is the mechanical contractor's
    assert [i.depth for i in rtu.items][:4] == [1, 1, 2, 1]            # the rep line sits one level in, under its map line
    assert all(i.quantity is None for i in blocks["Qty (##) Cabinet Unit Heaters"].items)
    assert all(i.quantity is None for i in rtu.items if i.kind == "note")


def test_rendered_lines_trace_to_devices(draft):
    by_id = {l.device_id: l for l in draft.lines if l.device_id}
    assert by_id["RTU.d4"].verb == "Install and Wire" and by_id["RTU.d4"].quantity == 2
    assert by_id["EF.d3"].quantity == 2 and by_id["CUH.d1"].quantity is None
    assert by_id["RTU.d1"].verb == "Furnish"                           # the trio line leads with its verb
    assert by_id["RTU.d2"].verb is None                                # "Map ..." has none
    assert {l.kind for l in draft.lines} == {"header", "line", "note"}
    assert all(l.device_id is None for l in draft.lines if l.kind != "line")


# ---- rules ---------------------------------------------------------------------------------------------------

def test_pure_same_job_same_text(job, playbook):
    assert render(job, playbook) == render(Job.from_dict(job.to_dict()), playbook)


def test_lines_follow_the_shape_order_not_the_device_order(job, playbook):
    ef = job.system("EF")
    shuffled = replace(ef, devices=tuple(reversed(ef.devices)))
    assert texts(render(one(job, shuffled), playbook), "EF")[1:] == [
        "Furnish and Install DDC Controller", "Furnish Fan Start / Stop and Status",
        "Furnish and Install Motorized Damper Actuator (Qty. 2)"]


def test_the_higher_count_prints_even_when_value_is_lower(job, playbook):
    fam = Family("Exhaust Fan", ("EF-1", "EF-2"), Count(value=2, others=(OtherCount(5, REF),)))
    out = render(one(job, system([device()], families=(fam,))), playbook)
    assert texts(out, "EF")[0] == "Qty (5) Exhaust Fans EF-1, 2"
    assert texts(out, "EF")[-1] == "*Qty. (5) per M-1; 2 per the documents."


def test_count_note_names_the_place_of_every_count(job, playbook):
    fam = Family("Exhaust Fan", ("EF-1",), Count(value=4, sources=(Ref("S1", "q", "M-201, Drawings.pdf page 3"),),
                                                 others=(OtherCount(3, Ref("S2", "q", "M-301, Specs.pdf page 8")),
                                                         OtherCount(5, Ref("S3", "q", "M-401, Drawings.pdf page 9")))))
    note = texts(render(one(job, system([device()], families=(fam,))), playbook), "EF")[-1]
    assert note == "*Qty. (5) per M-401; 4 per M-201; 3 per M-301."


def test_count_note_uses_sheet_numbers_never_file_names_and_folds_one_place(job, playbook):
    pb = load_playbook(ROOT / "playbook")
    fam = Family("Exhaust Fan", ("EF-1",), Count(
        value=7, sources=(Ref("S1", "q", "equipment counts for EF"),),
        others=(OtherCount(3, Ref("S2", "q", "Q-210.10, Invented Set - Combined.pdf page 15")),
                OtherCount(3, Ref("S3", "q", "Q-210.10 whole sheet, Invented Set - Combined.pdf page 15 (picture)")),
                OtherCount(2, Ref("S4", "q", "INVENTED SCHEDULE, Q-702.00, Invented Set - Combined.pdf page 51")),
                OtherCount(1, Ref("S5", "q", "Q-305.00, Invented Set.pdf page 4; Q-306.00, Invented Set.pdf page 5")),
                OtherCount(0, Ref("S6", "q", "Q-305.00 whole sheet, Invented Set.pdf page 4 (picture)")),
                OtherCount(4, Ref("S7", "q", "99 99 99 Invented Section, invented-spec_Rev_2.pdf page 3")))))
    out = texts(render(one(job, system([device(qty=7)], families=(fam,), shape="")), pb), "EF")
    qty = [t for t in out if t.startswith("*Qty.")]
    assert qty == ["*Qty. (7) per the documents; 3 per Q-210.10; 2 per Q-702.00; 1 and 0 per Q-305.00; "
                   "4 per 99 99 99 Invented Section."]
    assert not any(".pdf" in t for t in out)


def test_count_note_is_one_line_per_block_beside_the_confirm(job, playbook):
    pb = load_playbook(ROOT / "playbook")
    fam = Family("Exhaust Fan", ("EF-1",), Count(value=3, others=(OtherCount(2, Ref("S2", "q", "Q-1, A.pdf page 1")),)))
    d = device(qty=3, quantity=Count(3, others=(OtherCount(2, Ref("S2", "q", "Q-1, A.pdf page 1")),)))
    clar = (Clarification("confirm", "Confirm quantity: 3 fans carried per the schedule"),)
    out = texts(render(one(job, system([d], families=(fam,), shape="", clarifications=clar)), pb), "EF")
    assert out[-2:] == ["*Confirm quantity: 3 fans carried per the schedule", "*Qty. (3) per the documents; 2 per Q-1."]


# ---- the clarification labels (the text's own label is not printed twice) -------------------------------------

@pytest.mark.parametrize("kind, text, printed", [
    ("confirm", "Confirm ownership: invented relay by others", "*Confirm ownership: invented relay by others"),
    ("confirm", "Confirm quantity: 4 invented units", "*Confirm quantity: 4 invented units"),
    ("confirm", "*Confirm quantities: invented sensors", "*Confirm quantities: invented sensors"),
    ("confirm", "quantity: 4 invented units", "*Confirm quantity: 4 invented units"),
    ("confirm", "Assumed: invented panel by the maker", "*Confirm invented panel by the maker"),
    ("assumed", "*Assumed: one invented switch, as the sequence asks", "*Assumed: one invented switch, as the sequence asks"),
    ("assumed", "Assumed: one invented switch", "*Assumed: one invented switch"),
    ("per_drawings", "Quantity per plumbing drawings", "*Quantity per plumbing drawings"),
    ("per_drawings", "*Quantity per plumbing drawings", "*Quantity per plumbing drawings"),
    ("per_drawings", "plumbing", "*Quantity per plumbing drawings"),
    ("per_drawings", "quantity per the electrical drawings", "*Quantity per electrical drawings"),
    ("per_drawings", "Mechanical drawings", "*Quantity per mechanical drawings"),
])
def test_a_label_the_text_already_carries_prints_once(job, kind, text, printed):
    pb = load_playbook(ROOT / "playbook")
    out = texts(render(one(job, system([device()], clarifications=(Clarification(kind, text),))), pb), "EF")
    assert out[-1] == printed


def test_an_assumption_that_carries_its_own_label_prints_it_once(job):
    pb = load_playbook(ROOT / "playbook")
    a = device(assumption=Assumption("Assumed: one invented sensor", "the invented sequence asks for it"))
    out = texts(render(one(job, system([a])), pb), "EF")
    assert out[-1] == "*Assumed: one invented sensor, because the invented sequence asks for it"


def test_a_long_clarification_prints_whole(job):
    pb = load_playbook(ROOT / "playbook")
    long_text = "Confirm quantity: " + "invented words " * 30 + "end"
    out = texts(render(one(job, system([device()], clarifications=(Clarification("confirm", long_text),))), pb), "EF")
    assert out[-1] == "*" + long_text


# ---- source ids never print ----------------------------------------------------------------------------------

def test_source_ids_in_an_assumption_become_the_sheet_or_section_of_their_ref(job):
    pb = load_playbook(ROOT / "playbook")
    refs = (Ref("S41", "q", "Q-701.00, Invented Set.pdf page 50"),
            Ref("S7", "q", "sequence section B. Invented fans, 99 99 99 INVENTED SEQUENCE, invented.pdf page 3"))
    a = device(refs=refs, assumption=Assumption(
        "one invented controller", "S41 note 1 asks for it and S7 paragraph 2 names no party"))
    out = texts(render(one(job, system([a])), pb), "EF")
    assert out[-1] == ("*Assumed: one invented controller, because Q-701.00 asks for it and "
                       "sequence section B. Invented fans names no party")


def test_source_ids_with_no_ref_are_dropped_and_the_words_tidied(job):
    pb = load_playbook(ROOT / "playbook")
    a = device(assumption=Assumption("one invented sensor per S900", "the schedule (S901, S902) shows one per unit"))
    b = device(id="X.d2", slot="damper_actuator", name="Damper",
               assumption=Assumption("one damper", "the plan shows it in S903"))
    out = texts(render(one(job, system([a, b])), pb), "EF")
    assert out[-1] == ("*Assumed: one invented sensor, because the schedule shows one per unit; "
                       "one damper, because the plan shows it")
    assert "S9" not in out[-1] and "  " not in out[-1]


def test_source_ids_in_a_clarification_are_replaced_too(job):
    pb = load_playbook(ROOT / "playbook")
    d = device(refs=(Ref("S12", "q", "Q-100.00, Invented.pdf page 3"),))
    clar = (Clarification("confirm", "Confirm quantity: 4 invented units per S12, 2 per S99"),)
    out = texts(render(one(job, system([d], clarifications=clar)), pb), "EF")
    assert out[-1] == "*Confirm quantity: 4 invented units per Q-100.00, 2"


# ---- a system with no lines is left out ------------------------------------------------------------------------

def test_a_system_with_no_lines_prints_no_header_and_is_kept_for_the_evidence_package(job, playbook):
    empty = system([], key="EMPTY", name="Invented Units",
                   clarifications=(Clarification("note", "the invented units have no BMS work"),))
    out = render(replace(job, systems=(job.system("EF"), empty)), playbook)
    assert [b.header for b in out.scope.blocks] == ["Qty (3) Exhaust Fans EF-1 thru 3"]
    left = [l for l in out.lines if l.system_key == "EMPTY"]
    assert [(l.kind, l.device_id) for l in left] == [("note", None)]
    assert "no lines written" in left[0].text and "the invented units have no BMS work" in left[0].text


def test_an_alternate_with_no_lines_adds_no_alternate(job, playbook):
    empty = system([], key="EMPTY", alternate="add")
    out = render(replace(job, systems=(job.system("EF"), empty)), playbook)
    assert out.scope.add_alternates == ()


# ---- dampers under their fan ----------------------------------------------------------------------------------

def test_a_damper_family_under_a_fan_prints_no_header_of_its_own(job, playbook):
    ef = job.system("EF")
    fan_with_damper = replace(ef, families=ef.families + (Family("Motorized Damper", (), Count(value=2)),))
    damper_only = system([device(id="MD.d1", slot="damper_actuator", name="Motorized Damper Actuator", qty=4)],
                         key="MD", name="Motorized Dampers", shape="",
                         families=(Family("Motorized Damper", (), Count(value=4)),))
    out = render(replace(job, systems=(fan_with_damper, damper_only)), playbook)
    ef_lines = texts(out, "EF")
    assert [l.text for l in out.lines if l.system_key == "EF" and l.kind == "header"] == [
        "Qty (3) Exhaust Fans EF-1 thru 3"]
    assert ef_lines[1:] == ["Furnish and Install DDC Controller", "Furnish Fan Start / Stop and Status",
                            "Furnish and Install Motorized Damper Actuator (Qty. 2)"]
    assert texts(out, "MD")[0] == "Qty (4) Motorized Dampers"
    assert [b.header for b in out.scope.blocks] == ["Qty (3) Exhaust Fans EF-1 thru 3", "Qty (4) Motorized Dampers"]


# ---- the header never undershoots ------------------------------------------------------------------------------

def test_each_family_header_prints_its_highest_count(job, playbook):
    fams = (Family("Indoor Unit", ("IU-1",), Count(value=4, others=(OtherCount(6, REF), OtherCount(1, REF)))),
            Family("Condensing Unit", ("CU-1",), Count(value=None, others=(OtherCount(2, REF),))))
    out = render(one(job, system([device()], families=fams, shape="")), playbook)
    assert [l.text for l in out.lines if l.kind == "header"] == ["Qty (6) Indoor Unit IU-1", "Qty (2) Condensing Unit CU-1"]


def test_a_quantity_prints_only_when_it_differs_from_the_blocks_count(job, playbook):
    out = render(one(job, system([device(qty=2), device(qty=1, id="X.d2", slot="damper_actuator", name="Damper"),
                                  device(qty=2, id="X.d3", slot="damper_actuator", name="Damper B")])), playbook)
    assert texts(out, "EF")[1:] == ["Furnish and Install DDC Controller",
                                    "Furnish and Install Damper (Qty. 1)", "Furnish and Install Damper B"]


def test_every_assumption_says_why_and_a_reason_may_lead_with_its_own_word(job, playbook):
    a = device(assumption=Assumption("one per fan", "since the sequence names each fan"), flag="assumed")
    b = device(id="X.d2", slot="damper_actuator", name="Damper", assumption=Assumption("a damper per fan.", "the schedule"))
    note = texts(render(one(job, system([a, b])), playbook), "EF")[-1]
    assert note == "*one per fan, since the sequence names each fan; a damper per fan, because the schedule"


def test_an_assumption_without_its_why_is_refused(job, playbook):
    bad = device(assumption=Assumption("one per fan", "  "))
    with pytest.raises(RenderError, match="what and why"):
        render(one(job, system([bad])), playbook)


def test_one_star_line_per_kind_in_a_fixed_order(job, playbook):
    clar = (Clarification("note", "n1"), Clarification("per_drawings", "p1"), Clarification("confirm", "c1"),
            Clarification("confirm", "c2"), Clarification("assumed", "a1"), Clarification("note", "n2"))
    out = texts(render(one(job, system([device()], clarifications=clar)), playbook), "EF")
    assert out[2:] == ["*c1; c2 - to be confirmed", "*a1", "*p1 as per drawings", "*n1; n2"]


def test_owner_brackets_come_from_the_wording(job, playbook):
    d = device(furnished_by="Mechanical Contractor", installed_by="AME", verb="Install and Wire")
    assert texts(render(one(job, system([d])), playbook), "EF")[1] == (
        "Install and Wire DDC Controller (Furnished by Mechanical Contractor)")


def test_a_shapeless_system_prints_in_the_generic_form_in_device_order(job, playbook):
    d1 = device(name="Gas Detector", qty=3, furnished_by="Others", slot="x")
    d2 = device(id="X.d2", name="Panel", qty=None, slot="y")
    out = texts(render(one(job, system([d1, d2], shape="", families=(Family("Gas Detector", ("GD-1", "GD-2"),
                                                                              Count(value=3)),))), playbook), "EF")
    assert out == ["Qty (3) Exhaust Fans GD-1, 2", "Furnish and Install Gas Detector (Furnished by Others)",
                   "Furnish and Install Panel (Qty. ##)"]


def test_a_slot_the_shape_lacks_still_prints_after_the_known_slots(job, playbook):
    odd = device(id="X.d2", slot="not_a_slot", name="Extra Thing")
    out = texts(render(one(job, system([odd, device()])), playbook), "EF")
    assert out[1:] == ["Furnish and Install DDC Controller", "Furnish and Install Extra Thing"]


def test_a_system_with_no_families_prints_an_unknown_count(job, playbook):
    s = system([device()])
    out = render(one(job, replace(s, families=())), playbook)
    assert texts(out, "EF")[0] == "Qty (##) Exhaust Fans"
    assert out.scope.blocks[0].items[0].quantity is None


def test_unknown_shape_and_missing_header_are_refused(job, playbook):
    with pytest.raises(RenderError, match="shape"):
        render(one(job, system([device()], shape="No Such Shape")), playbook)
    with pytest.raises(RenderError, match="header"):
        render(replace(job, header=None), playbook)


def test_extend_existing_front_end_and_deduct_alternate(job, playbook):
    fe = FrontEnd(mode="extend-existing", existing_system_name="Old BMS", devices=(device(slot="x", name="Link", qty=1),),
                  clarifications=(Clarification("note", "tie to the old head end"),), tech_hours=2.0)
    out = render(replace(job, front_end=fe, systems=(system([device()], alternate="deduct"),)), playbook)
    assert out.scope.front_end.existing_system_name == "Old BMS"
    assert [i.text for i in out.scope.front_end.items] == ["Furnish and Install Link", "*tie to the old head end"]
    assert len(out.scope.deduct_alternates) == 1 and out.scope.blocks == ()


def test_nothing_internal_reaches_the_client_text(draft, job):
    printed = "\n".join(l.text for l in draft.lines)
    for system_ in job.systems:
        for d in system_.devices:
            for ref in d.refs:
                assert ref.source_id + " " not in printed and ref.quote not in printed
    assert "Is the existing lobby fan to be kept?" not in printed


# ---- the bridge to the old writers ---------------------------------------------------------------------------

def test_the_old_word_and_price_sheet_writers_take_the_draft(draft, tmp_path):
    from estimator.__main__ import ALIASES, PRICE_BOOK, PROPOSAL_TEMPLATE, WORKUP_TEMPLATE
    from estimator.price_sheet.price_book import PriceBook
    from estimator.price_sheet.write import check_fit, write_price_sheet
    from estimator.proposal.write import write_proposal
    check_fit(draft.scope)
    proposal = write_proposal(draft.scope, PROPOSAL_TEMPLATE, tmp_path / "p.docx")
    sheet = write_price_sheet(draft.scope, WORKUP_TEMPLATE, PriceBook.load(PRICE_BOOK, ALIASES), tmp_path / "s.xlsx")
    from docx import Document
    words = "\n".join(p.text for p in Document(str(proposal)).paragraphs)
    assert "Qty (3) Exhaust Fans EF-1 thru 3" in words and "Fire alarm system by others" in words
    assert "Qty (2) Duct Heaters DH-1, 2" in words
    assert sheet.exists()


# ---- sub-lines (the shape's "under") -------------------------------------------------------------------------

def test_sub_line_prints_one_level_in_directly_after_its_parent_with_no_verb():
    from bms.playbook import load_playbook as repo_playbook
    from bms.model import Header
    pb = repo_playbook()
    devices = (
        device(id="GD.d1", qty=1, slot="sensor", name="CO Sensor", verb="Furnish and Install"),
        device(id="GD.d2", qty=1, slot="panel", name="Gas Detection Panel", verb="Furnish and Install"),
        device(id="GD.d3", qty=1, slot="damper_actuator", name="Damper Actuator", verb="Furnish and Install"),
        device(id="GD.d4", qty=1, slot="horn_strobe", name="Horn / Strobe", verb="Furnish and Install"),
    )
    gd = System(key="GD", name="Gas Detection", shape="Gas Detection", control="field",
                families=(Family("Gas Detection", ("GD-1",), Count(value=1)),), devices=devices)
    j = Job(name="Invented", systems=(gd,), header=Header("00-0000", "Invented", "Invented", ("A",), "2026-10-04"))
    draft = render(j, pb)
    lines = [l for l in draft.lines if l.system_key == "GD" and l.kind == "line"]
    assert [l.device_id for l in lines] == ["GD.d2", "GD.d1", "GD.d4", "GD.d3"]
    assert [l.text for l in lines][:3] == ["Furnish and Install Gas Detection Panel", "CO Sensor", "Horn / Strobe"]
    assert [l.verb for l in lines][:3] == ["Furnish and Install", None, None]
    items = draft.scope.blocks[0].items
    assert [i.depth for i in items if i.kind == "line"] == [1, 2, 2, 1]
