"""RND-6, RND-9, RND-11, RND-12: alternate labels, fixed house lines, assumption checks and the count-cause
words, on invented systems and the repo Playbook only."""
from __future__ import annotations

from pathlib import Path

import pytest

from bms.model import Assumption, Count, Device, Family, Header, Job, OtherCount, Ref, System
from bms.playbook import load_playbook
from bms.render import RenderError, render
from estimator.reading.inventory import COUNT_CAUSES_LEAD

ROOT = Path(__file__).resolve().parents[2]
REF = Ref(source_id="S1", quote="q", where="M-1, Drawings.pdf page 1")
S141 = Ref("S141", "q", "M-101, Invented.pdf page 2")


@pytest.fixture(scope="module")
def pb():
    return load_playbook(ROOT / "playbook")


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


def job(*systems_) -> Job:
    return Job(name="Invented", systems=tuple(systems_),
               header=Header("00-0000", "Invented", "Invented", ("A",), "2026-10-04"))


def texts(draft, key: str) -> list[str]:
    return [l.text for l in draft.lines if l.system_key == key]


# ---- RND-9: each alternate is numbered, adds and deducts apart ---------------------------------------------------

def test_alternates_are_numbered_adds_and_deducts_apart(pb):
    def alt(key, name, tag, side):
        return system([device(id=f"{key}.d1", qty=1)], key=key, name=name, alternate=side, shape="",
                      families=(Family(name, (tag,), Count(value=1)),))
    out = render(job(alt("A1", "Invented Fan", "IF-1", "add"), alt("A2", "Invented Heater", "IH-1", "add"),
                     alt("D1", "Invented Pump", "IP-1", "deduct")), pb).scope
    assert [a.label for a in out.add_alternates] == ["ALT #1: Invented Fan IF-1", "ALT #2: Invented Heater IH-1"]
    assert [a.label for a in out.deduct_alternates] == ["ALT #1: Invented Pump IP-1"]
    assert all("ALT #:" != a.label for a in out.add_alternates + out.deduct_alternates)


# ---- RND-11: another shape's fixed wording is not this device's -------------------------------------------------

def test_a_name_matching_another_shapes_fixed_wording_keeps_its_verb_and_owner(pb):
    d = device(slot="other_wire", name="Condenser Interlock Wiring", verb="Wire", furnished_by="Others",
               installed_by="Others", qty=2)
    out = render(job(system([d])), pb)
    line = next(l for l in out.lines if l.kind == "line")
    assert line.text == "Wire Condenser Interlock Wiring" + pb.wording.owner_brackets["Others"]
    assert line.text == "Wire Condenser Interlock Wiring (Furnished by Others)"
    assert line.verb == "Wire"


def test_the_shapes_own_fixed_wording_keeps_the_owner_bracket(pb):
    uv = pb.shape("Unit Ventilators")
    fixed = uv.wording["condenser_interlock"]
    d = device(slot="other_wire", name=fixed, verb="Wire", furnished_by="Others", installed_by="Others", qty=2)
    s = system([d], key="UV", name="Unit Ventilators", shape="Unit Ventilators",
               families=(Family("Unit Ventilator", ("UV-1", "UV-2"), Count(value=2)),))
    line = next(l for l in render(job(s), pb).lines if l.kind == "line")
    assert line.text == fixed + pb.wording.owner_brackets["Others"]
    assert line.verb is None


# ---- RND-12: what and why are checked after they are cleaned --------------------------------------------------

@pytest.mark.parametrize("what, why", [
    ("one sensor per unit", "S141"),
    ("Assumed:", "the schedule lists one per unit"),
])
def test_an_assumption_empty_after_cleaning_is_refused(pb, what, why):
    d = device(refs=(S141,), assumption=Assumption(what, why))
    with pytest.raises(RenderError, match="what and why"):
        render(job(system([d])), pb)


# ---- RND-6: the cause words print when the printed count also has a sheet source -------------------------------

def test_the_cause_words_print_when_the_printed_count_has_a_sheet_too(pb):
    words = pb.wording.count_causes["typical"]
    counts_line = f"EF: plan placements 12; schedule rows 1; {COUNT_CAUSES_LEAD} a typical unit at each place"
    count = Count(value=12, sources=(Ref("S1", "counted on the sheet picture", "M-101, Invented.pdf page 2"),),
                  others=(OtherCount(12, Ref("S2", counts_line, "equipment counts for EF")),
                          OtherCount(1, Ref("S3", "schedule rows 1", "equipment counts for EF"))))
    fam = Family("Exhaust Fan", ("EF-1",), count)
    out = texts(render(job(system([device(qty=12)], families=(fam,), shape="")), pb), "EF")
    [note] = [t for t in out if t.startswith("*Qty.")]
    assert words in note
    assert note.startswith("*Qty. (12) per M-101")


def test_the_alternate_label_form_comes_from_the_wording_when_set(pb):
    from dataclasses import replace
    custom = replace(pb, wording=replace(pb.wording, alternate_label="Alternate {k} - {name}"))
    s = system([device(id="A1.d1", qty=1)], key="A1", name="Invented Fan", alternate="add", shape="",
               families=(Family("Invented Fan", ("IF-1",), Count(value=1)),))
    assert [a.label for a in render(job(s), custom).scope.add_alternates] == ["Alternate 1 - Invented Fan IF-1"]
