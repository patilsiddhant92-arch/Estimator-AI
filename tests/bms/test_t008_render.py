"""T-008 tasks 1 and 3: valve families print no header of their own; a long "*" note prints one line per point.

Invented fixtures only.
"""
from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path

import pytest
from docx import Document

from bms.model import Assumption, Clarification, Count, Device, Family, FrontEnd, Job, Ref, System
from bms.playbook import load_playbook
from bms.render import LONG_CLARIFICATION, render, short_points

FIXTURES = Path(__file__).resolve().parent / "fixtures"
REF = Ref(source_id="S1", quote="q", where="M-1, Drawings.pdf page 1")


@pytest.fixture(scope="module")
def playbook():
    return load_playbook(FIXTURES / "sample_playbook")


@pytest.fixture
def job() -> Job:
    return Job.from_dict(json.loads((FIXTURES / "sample_job.json").read_text(encoding="utf-8")))


def dev(n, name, slot="controller", qty=5, key="AHU", **kw) -> Device:
    base = dict(id=f"{key}.d{n}", slot=slot, name=name, verb="Furnish and Install", furnished_by="AME",
                installed_by="AME", wired_by="AME", quantity=Count(value=qty), refs=(REF,))
    base.update(kw)
    return Device(**base)


def sys_(families, devices, key="AHU", name="Air Handling Units", **kw) -> System:
    base = dict(key=key, name=name, shape="", control="field", families=families, devices=tuple(devices),
                tech_hours=12)
    base.update(kw)
    return System(**base)


AHU = Family("Air Handling Unit", tuple(f"AHU-{i}" for i in range(1, 6)), Count(value=5))
CV = Family("Control Valve", tuple(f"CV-{i}" for i in range(1, 11)), Count(value=10))


def _headers(out, key):
    return [l.text for l in out.lines if l.system_key == key and l.kind == "header"]


# ---- task 1 --------------------------------------------------------------------------------------------------

def test_a_valve_family_under_an_ahu_prints_no_header_of_its_own(job, playbook):
    s = sys_((AHU, CV), [dev(1, "DDC Controller"), dev(2, "Hot Water Control Valve", "hot_water_valve", 10)])
    out = render(replace(job, systems=(s,)), playbook)
    assert len(_headers(out, "AHU")) == 1
    assert _headers(out, "AHU")[0].startswith("Qty (5) Air Handling Unit")
    assert not any("Control Valve" in h for h in _headers(out, "AHU"))
    block = next(b for b in out.scope.blocks if b.header.startswith("Qty (5) Air Handling Unit"))
    assert block.tech_hours == 12 and len(block.items) >= 2
    assert any("(Qty. 10 Total)" in i.text and "Control Valve" in i.text for i in block.items)


def test_a_valve_only_system_keeps_its_own_header(job, playbook):
    s = sys_((CV,), [dev(1, "Hot Water Control Valve", "hot_water_valve", 10, key="CV")], key="CV",
             name="Control Valves")
    out = render(replace(job, systems=(s,)), playbook)
    assert _headers(out, "CV") and _headers(out, "CV")[0].startswith("Qty (10) Control Valve")


# ---- task 3 --------------------------------------------------------------------------------------------------

def _words(text):
    return re.findall(r"[\w'-]+", text.lower())


P1 = "AME furnishes the controller for each invented unit and wires it to the existing network on the second floor"
P2 = "The mechanical contractor mounts the sensors in the ductwork and leaves the wiring ends at the unit panel"
P3 = "The owner supplies the network drops at each equipment room and confirms the addresses before turn on"


def test_three_points_print_three_star_lines():
    lines = short_points(f"*Confirm {P1}; {P2}; {P3}")
    assert len(lines) == 3 and all(l.startswith("*") for l in lines)
    assert not any(l.startswith("- ") for l in lines) and max(map(len, lines)) <= 160
    assert _words(" ".join(lines)) == _words(f"*Confirm {P1}; {P2}; {P3}")


def test_a_long_assumption_splits_at_because_and_lowers_the_word():
    what = "one invented sensor on each of the supply branches of the units shown on the plans"
    why = "The sequence names a sensor for every branch of every unit and the schedule gives no count of them"
    text = f"*Assumed: {what}, because {why[0].lower() + why[1:]}"
    assert len(text) > LONG_CLARIFICATION
    lines = short_points(text)
    assert len(lines) >= 2 and all(len(l) <= LONG_CLARIFICATION for l in lines)
    assert lines[1].startswith("*because the")
    assert _words(" ".join(lines)) == _words(text)


def test_a_reason_lowers_a_plain_word_after_because(job, playbook):
    from bms.render import _notes, SourceIds  # noqa: F401
    s = sys_((AHU,), [dev(1, "DDC Controller", assumption=Assumption("one controller per unit", "The schedule lists it"),
                          flag="assumed")])
    out = render(replace(job, systems=(s,)), playbook)
    assert any(l.text == "*one controller per unit, because the schedule lists it" for l in out.lines)


def test_a_tag_and_an_acronym_keep_their_case(job, playbook):
    s = sys_((AHU,), [dev(1, "DDC Controller", assumption=Assumption("one controller", "AHU-1 is the only unit"),
                          flag="assumed"),
                      dev(2, "Sensor", assumption=Assumption("one sensor", "BMS points list names it"), flag="assumed")])
    texts = [l.text for l in render(replace(job, systems=(s,)), playbook).lines]
    assert "*one controller, because AHU-1 is the only unit" in texts
    assert "*one sensor, because BMS points list names it" in texts


def test_a_short_note_stays_one_line():
    assert short_points("*Confirm integration by others.") == ["*Confirm integration by others."]
    text = "*" + "x " * 74
    assert len(text) <= LONG_CLARIFICATION and short_points(text) == [text.strip()]


def test_each_point_is_its_own_note_item_and_paragraph(job, playbook, tmp_path):
    from estimator.__main__ import PROPOSAL_TEMPLATE
    from estimator.proposal.write import write_proposal
    front = FrontEnd(mode="new-system", devices=(dev(1, "DDC Controller", key="FE"),),
                     clarifications=(Clarification("confirm", f"{P1}; {P2}; {P3}"),))
    draft = render(replace(job, front_end=front), playbook)
    notes = [i for i in draft.scope.front_end.items if i.kind == "note"]
    assert len(notes) == 3 and all(n.text.startswith("*") for n in notes)
    document = Document(str(write_proposal(draft.scope, PROPOSAL_TEMPLATE, tmp_path / "p.docx")))
    paragraphs = [p.text for p in document.paragraphs if p.text.startswith("*")]
    for point in (P1, P2, P3):
        assert sum(point in p for p in paragraphs) == 1
