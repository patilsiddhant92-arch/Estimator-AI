"""Determinism and robustness tests (TASK-013).

Covers:
1. Render purity: same Job + Playbook gives identical output; shuffled input order where order is not
   meaningful gives identical output.
2. Job model round-trip: Job.to_dict() and JSON serialization round-trips losslessly, including edge cases and unicode.
3. Validate robustness: validate() never raises an exception on odd but valid jobs (empty families,
   Count None everywhere, shapeless systems, extreme string lengths, unicode and special characters).
"""
from __future__ import annotations

import copy
import json
import random
from pathlib import Path

import pytest

from bms.model import (
    Assumption,
    Clarification,
    Count,
    Device,
    ScopeException,
    Family,
    FrontEnd,
    Header,
    Job,
    OtherCount,
    Ref,
    Served,
    System,
)
from bms.playbook import load_playbook
from bms.render import render
from bms.validate import validate

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
SAMPLE_JOB_PATH = FIXTURES / "sample_job.json"
SAMPLE_PLAYBOOK_PATH = FIXTURES / "sample_playbook"


def _load_sample_job() -> Job:
    return Job.from_dict(json.loads(SAMPLE_JOB_PATH.read_text(encoding="utf-8")))


def _load_sample_playbook():
    return load_playbook(SAMPLE_PLAYBOOK_PATH)


# ===================================================================================================================
# 1. RENDER DETERMINISM & PURITY
# ===================================================================================================================

def test_render_is_strictly_pure():
    """Calling render() repeatedly on the same Job and Playbook produces byte-identical output."""
    playbook = _load_sample_playbook()
    job = _load_sample_job()

    first_draft = render(job, playbook)
    for _ in range(5):
        next_draft = render(job, playbook)
        assert next_draft.scope == first_draft.scope
        assert next_draft.lines == first_draft.lines
        assert [l.text for l in next_draft.lines] == [l.text for l in first_draft.lines]


def test_render_determinism_with_shuffled_system_order():
    """Systems with distinct block orders (equipment vs sequence-only) sort deterministically regardless of input order."""
    playbook = _load_sample_playbook()
    job = _load_sample_job()

    # RTU is equipment (order 10)
    rtu = job.system("RTU")
    # Make a sequence-only system whose count is None (rendered at SEQUENCE_ONLY_ORDER = 20)
    ref = Ref("S1", "quote", "where")
    seq_only = System(
        key="SEQ", name="Sequence Only Unit", shape="Exhaust Fan", control="field",
        families=(Family("Exhaust Fan", ("SEQ-1",), Count(None, (ref,))),),
        sequence_refs=(ref,),
        devices=(Device("SEQ.d1", "controller", "Sequence Controller", "Furnish", "AME", "AME", "AME",
                        Count(None, (ref,)), (ref,)),),
    )

    # Order 1: [seq_only, rtu]
    job1 = Job(name=job.name, systems=(seq_only, rtu), header=job.header)
    # Order 2: [rtu, seq_only]
    job2 = Job(name=job.name, systems=(rtu, seq_only), header=job.header)

    draft1 = render(job1, playbook)
    draft2 = render(job2, playbook)

    # In both drafts, RTU (order 10) must render before SEQ (order 20)
    assert [b.header for b in draft1.scope.blocks] == [b.header for b in draft2.scope.blocks]
    assert [l.text for l in draft1.lines] == [l.text for l in draft2.lines]
    assert draft1.scope.blocks[0].header.startswith("Qty (2) Rooftop Units")
    assert draft1.scope.blocks[1].header.startswith("Qty (##) Sequence Only Unit")


def test_render_determinism_with_shuffled_devices_across_slots():
    """Devices with distinct slots sort by shape.line_order, immune to input order in System.devices."""
    import dataclasses
    playbook = _load_sample_playbook()
    job = _load_sample_job()

    # RTU system has devices with different slots: comm_wiring, controller, etc.
    rtu = job.system("RTU")
    assert len(rtu.devices) > 1

    shuffled_devices = list(rtu.devices)
    shuffled_devices.reverse()
    assert shuffled_devices != list(rtu.devices)

    job_shuffled_rtu = job.with_system(dataclasses.replace(rtu, devices=tuple(shuffled_devices)))

    draft_orig = render(job, playbook)
    draft_shuffled = render(job_shuffled_rtu, playbook)

    # Output lines for RTU must remain identical
    rtu_orig_lines = [l.text for l in draft_orig.lines if l.system_key == "RTU"]
    rtu_shuffled_lines = [l.text for l in draft_shuffled.lines if l.system_key == "RTU"]
    assert rtu_shuffled_lines == rtu_orig_lines


def test_render_with_unicode_and_symbols():
    """Render processes special unicode characters, math symbols, and smart punctuation cleanly."""
    playbook = _load_sample_playbook()
    job = _load_sample_job()

    unicode_header = Header(
        quote_number="00-0000",
        reference="Café & Clinic — Phase 2 [Ref: ΔP / ±0.05\" w.g.]",
        mep_engineer="Ingénierie & Associés — Montréal",
        based_on=("M-001 Spécifications techniques", "23 09 93 Séquence d'opérations"),
        date="2026-10-04",
        to="À tous les soumissionnaires",
    )
    unicode_job = Job(name=job.name, systems=job.systems, header=unicode_header, front_end=job.front_end)

    draft = render(unicode_job, playbook)
    assert draft.scope.header.reference == unicode_header.reference
    assert draft.scope.header.mep_engineer == unicode_header.mep_engineer


# ===================================================================================================================
# 2. JOB MODEL ROUND-TRIP (to_dict / from_dict / JSON)
# ===================================================================================================================

def test_sample_job_json_lossless_round_trip():
    """The canonical sample job round trips through to_dict, json serialization, and from_dict."""
    job = _load_sample_job()
    raw_dict = job.to_dict()

    json_str = json.dumps(raw_dict, indent=2)
    loaded_dict = json.loads(json_str)

    restored = Job.from_dict(loaded_dict)
    assert restored == job
    assert restored.to_dict() == raw_dict


def test_job_round_trip_with_all_edge_cases():
    """Job serialization accurately preserves optional None fields, alternates, and serves."""
    ref = Ref("S1", "invented quote", "M-101 page 1")
    count_with_others = Count(
        value=None,
        sources=(ref,),
        others=(OtherCount(5, Ref("C1", "counted", "M-102 page 2")),),
    )

    dev = Device(
        id="SYS.d1",
        slot="controller",
        name="Custom Controller (24V)",
        verb="Furnish and Install",
        furnished_by="AME",
        installed_by="AME",
        wired_by="AME",
        quantity=count_with_others,
        refs=(ref,),
        assumption=Assumption("one per panel", "typical practice"),
        flag="quantity",
    )

    served = Served(
        key="AHU-1", name="Air Handler 1", tags=("AHU-1",), heaters=("DH-1", "DH-2"),
        heater_key="DH", heater_name="Duct Heaters"
    )

    sys_base = System(
        key="SYS1",
        name="System One",
        shape="Exhaust Fan",
        control="field",
        families=(Family("Fan Family", ("EF-1", "EF-2"), count_with_others),),
        sequence_refs=(ref,),
        devices=(dev,),
        clarifications=(Clarification("note", "Specific note"),),
        tech_hours=4.5,
        alternate="base",
        serves=(served,),
        no_scope_reason=None,
    )

    sys_add = System(
        key="SYS2",
        name="Alternate Add System",
        shape="",
        control="packaged",
        families=(),
        sequence_refs=(),
        devices=(),
        clarifications=(),
        tech_hours=None,
        alternate="add",
        serves=(),
        no_scope_reason="Supplied by mechanical contractor",
    )

    job = Job(
        name="Edge Case Job",
        systems=(sys_base, sys_add),
        header=None,
        front_end=None,
        exceptions=(ScopeException("ELEC", "Line voltage wiring by electrical contractor", (ref,)),),
        questions=("Review quantity",),
    )

    dumped = json.dumps(job.to_dict())
    restored = Job.from_dict(json.loads(dumped))

    assert restored == job
    assert restored.systems[0].serves == (served,)
    assert restored.systems[1].no_scope_reason == "Supplied by mechanical contractor"
    assert restored.systems[0].devices[0].quantity.value is None
    assert restored.systems[0].devices[0].quantity.others[0].value == 5
    assert restored.header is None
    assert restored.front_end is None


def test_job_round_trip_with_unicode_in_all_fields():
    """Unicode characters across all fields survive serialization without corruption."""
    ref = Ref("S99", "température de consigne ≥ 21°C ± 0.5°C", "Spéc. §23, p. 12")
    dev = Device(
        id="VAV.d1",
        slot="controller",
        name="Régulateur VAV terminal — modèle «Alpha»",
        verb="Furnish",
        furnished_by="AME",
        installed_by="AME",
        wired_by="AME",
        quantity=Count(1, (ref,)),
        refs=(ref,),
        assumption=Assumption("calibré en usine", "norme ISO-9001"),
        flag="assumed",
    )
    sysm = System(
        key="VAV",
        name="Boîtes à volume d'air variable (VAV)",
        shape="",
        control="none",
        families=(Family("Boîte VAV", ("VAV-1",), Count(1, (ref,))),),
        sequence_refs=(ref,),
        devices=(dev,),
    )
    job = Job(
        name="Projet Hôpital Sainte-Jeanne d'Arc",
        systems=(sysm,),
        header=Header("99-9999", "Clinique d'oncologie — Aile B", "Ing. Lemieux", ("M-1",), "2026-10-04", "Tous"),
        exceptions=(ScopeException("ELEC", "Câblage 120V par l'électricien", (ref,)),),
    )

    round_tripped = Job.from_dict(json.loads(json.dumps(job.to_dict())))
    assert round_tripped == job
    assert round_tripped.name == "Projet Hôpital Sainte-Jeanne d'Arc"
    assert round_tripped.systems[0].devices[0].name == "Régulateur VAV terminal — modèle «Alpha»"
    assert "≥ 21°C" in round_tripped.systems[0].devices[0].refs[0].quote


# ===================================================================================================================
# 3. VALIDATE ROBUSTNESS (Never raises on odd but valid jobs)
# ===================================================================================================================

def test_validate_never_raises_on_empty_job():
    """An empty job without systems or header validates without exceptions."""
    playbook = load_playbook()
    job = Job("Completely Empty Job", systems=())
    findings = validate(job, playbook)
    assert isinstance(findings, list)


def test_validate_never_raises_on_empty_families_and_devices():
    """Systems with empty families, empty devices, and empty refs do not crash validate()."""
    playbook = load_playbook()
    systems = (
        System("EF", "Exhaust Fans", "Exhaust Fan", "field", families=(), sequence_refs=(), devices=()),
        System("RTU", "Rooftops", "Packaged ERU / RTU / AHU", "packaged", families=(), sequence_refs=(), devices=()),
        System("CUSTOM", "Custom Unshaped", "", "none", families=(), sequence_refs=(), devices=()),
    )
    job = Job("Bare Systems Job", systems=systems)
    findings = validate(job, playbook)
    assert isinstance(findings, list)
    # A system with no lines produces a 'check' finding under left_out
    assert any("left out" in f.what for f in findings)


def test_validate_never_raises_on_count_none_everywhere():
    """A job where every Count is value=None does not trigger TypeError or crashes in validators."""
    playbook = load_playbook()
    ref = Ref("S1", "quote", "where")
    count_none = Count(None, (ref,), (OtherCount(None, ref),))

    dev = Device(
        id="EF.d1", slot="controller", name="Fan Controller", verb="Furnish",
        furnished_by="AME", installed_by="AME", wired_by="AME",
        quantity=count_none, refs=(ref,),
    )
    system = System(
        key="EF", name="Exhaust Fans", shape="Exhaust Fan", control="field",
        families=(Family("Exhaust Fan", ("EF-1",), count_none),),
        sequence_refs=(ref,), devices=(dev,),
    )
    job = Job("Count None Job", systems=(system,))

    findings = validate(job, playbook)
    assert isinstance(findings, list)


def test_validate_never_raises_on_extreme_string_lengths():
    """Extremely long text in names, assumptions, and clarifications does not crash validate()."""
    playbook = load_playbook()
    ref = Ref("S1", "q" * 2000, "w" * 500)
    dev = Device(
        id="EF.d1", slot="controller", name="Super Long Name " * 100, verb="Furnish",
        furnished_by="AME", installed_by="AME", wired_by="AME",
        quantity=Count(1, (ref,)), refs=(ref,),
        assumption=Assumption("Long assumption what " * 50, "Long assumption why " * 50),
    )
    clar = Clarification("note", "Extremely long note text " * 100)
    system = System(
        key="EF", name="Exhaust Fans", shape="Exhaust Fan", control="field",
        families=(Family("Exhaust Fan", ("EF-1",), Count(1, (ref,))),),
        sequence_refs=(ref,), devices=(dev,), clarifications=(clar,),
    )
    job = Job("Extreme Length Job", systems=(system,))

    findings = validate(job, playbook)
    assert isinstance(findings, list)
    # Long notes and assumptions are flagged by long_note / long_assumption rules
    assert any("220" in f.what or "long" in f.what.lower() for f in findings)


def test_validate_never_raises_on_unicode_and_punctuation_edge_cases():
    """Punctuation, quotes, slashes, brackets, math symbols, and non-ASCII text validate smoothly."""
    playbook = load_playbook()
    ref = Ref("S1", "«Citation spéciale» [100% compliant] ~ ±5° / ΔP <= 0.2\" w.g. <html>", "P. 1 / (Annexe B)")
    dev = Device(
        id="SYS.d1", slot="controller", name="Sonde d'humidité & Température [0-100% RH / 4-20mA]",
        verb="Furnish and Install", furnished_by="AME", installed_by="AME", wired_by="AME",
        quantity=Count(1, (ref,)), refs=(ref,),
        assumption=Assumption("Installation selon devis", "Règle de l'art §4.2"),
    )
    system = System(
        key="SYS", name="Système de Climatisation", shape="", control="none",
        families=(Family("Famille Unité", ("FCU-01",), Count(1, (ref,))),),
        sequence_refs=(ref,), devices=(dev,),
    )
    job = Job("Projet Unicode", systems=(system,))

    findings = validate(job, playbook)
    assert isinstance(findings, list)


def test_validate_never_raises_on_front_end_variations():
    """FrontEnd in various modes (null, new-system, existing-system) validates cleanly."""
    playbook = load_playbook()
    ref = Ref("S1", "bms", "specs")
    dev = Device(
        id="FE.d1", slot="server", name="Workstation", verb="Furnish",
        furnished_by="AME", installed_by="AME", wired_by="AME",
        quantity=Count(1, (ref,)), refs=(ref,),
    )

    for mode, name in [("new-system", None), ("existing-system", "Tridium Niagara"), ("new-system", "Legacy")]:
        fe = FrontEnd(mode=mode, existing_system_name=name, devices=(dev,), clarifications=())
        job = Job("FrontEnd Variations", systems=(), front_end=fe)
        findings = validate(job, playbook)
        assert isinstance(findings, list)


def test_one_device_id_in_two_systems_is_a_finding_not_an_exception():
    """A repeated device id is the 'listed more than once' finding. validate and render both return."""
    playbook = load_playbook()
    ref = Ref("S1", "quote", "where")
    device = Device(
        id="EF.d1", slot="controller", name="Fan Controller", verb="Furnish",
        furnished_by="AME", installed_by="AME", wired_by="AME",
        quantity=Count(1, (ref,)), refs=(ref,),
    )
    systems = (
        System("EF", "Exhaust Fans", "Exhaust Fan", "field", families=(), sequence_refs=(), devices=(device,)),
        System("RTU", "Rooftops", "Packaged ERU / RTU / AHU", "packaged", families=(), sequence_refs=(),
               devices=(device,)),
    )
    job = Job("Repeated id", systems=systems, header=Header("99-9999", "Invented", "A. Engineer", ("M-1",),
                                                             "2026-10-04"))
    findings = validate(job, playbook)
    assert isinstance(findings, list)
    assert any(f.severity == "must_fix" and "more than once" in f.what and f.device_id == "EF.d1" for f in findings)
    draft = render(job, playbook)
    assert [line.device_id for line in draft.lines].count("EF.d1") == 2
