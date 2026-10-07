"""RND-14: the client words the renderer used to hard-code (the assumption's "because", the generic header, the
count note's labels and joiners, the house casing) come from the Playbook's wording.json when it sets them; with a
Playbook that leaves them out the text prints exactly as before. Invented systems and the sample Playbook only."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from bms.model import Assumption, Count, Device, Family, Header, Job, OtherCount, Ref, System
from bms.playbook import PlaybookError, load_playbook
from bms.render import render

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "tests" / "bms" / "fixtures" / "sample_playbook"
REF = Ref(source_id="S1", quote="q", where="M-1, Drawings.pdf page 1")

# every new optional key at the value the renderer uses without it (the defaults the report hands the estimator)
DEFAULTS = {
    "assumption": {"because": "because ", "leads": ["as ", "since ", "given that ", "because "]},
    "header": {"generic": "Qty ({n}) {name} {tags}"},
    "quantity": {"per": " per ", "and": " and ", "joiner": "; ",
                 "labels": {"plan_placements": "plan placements", "schedule_rows": "schedule rows",
                            "schedule": "the schedule", "riser": "the riser", "sheet_pictures": "the sheet pictures"}},
    "casing": {"acronyms": ["BMS", "VFD", "DDC", "ERV", "RTU", "HPAC", "SCR", "UUKL", "BACnet"],
               "small_words": ["a", "an", "and", "as", "at", "b", "between", "but", "by", "for", "from", "in", "into",
                               "it", "nor", "of", "on", "or", "per", "the", "thru", "to", "vs", "w", "with", "within"],
               "not_plural": ["points", "series", "status", "controls", "stairs", "chassis"],
               "acronym_before": {
                   "co": ["sensor", "sensors", "detector", "detectors", "detection", "monitor", "monitoring"],
                   "it": ["room", "rooms", "closet", "closets", "rack", "racks"],
                   "fa": ["relay", "relays", "panel", "panels", "interface", "shutdown", "alarm", "alarms", "system",
                          "interlock", "interlocks"]}},
}


def playbook_with(tmp_path: Path, change) -> object:
    """The sample Playbook copied to tmp_path, its wording.json changed by `change(data)`, loaded."""
    root = tmp_path / "playbook"
    shutil.copytree(SAMPLE, root)
    path = root / "wording.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return load_playbook(root)


def device(name="DDC Controller", qty: int | None = 2, **kw) -> Device:
    base = dict(id="X.d1", slot="controller", name=name, verb="Furnish and Install", furnished_by="AME",
                installed_by="AME", wired_by="AME", quantity=Count(value=qty), refs=(REF,))
    base.update(kw)
    return Device(**base)


def system(devices=(), families=None, **kw) -> System:
    base = dict(key="EF", name="Exhaust Fans", shape="", control="field",
                families=families or (Family("Exhaust Fan", ("EF-1", "EF-2"), Count(value=2)),), devices=tuple(devices))
    base.update(kw)
    return System(**base)


def job(*systems_) -> Job:
    return Job(name="Invented", systems=tuple(systems_),
               header=Header("00-0000", "Invented", "Invented", ("A",), "2026-10-04"))


def texts(draft) -> list[str]:
    return [l.text for l in draft.lines]


def assumed_job() -> Job:
    d = device(assumption=Assumption("one controller per fan", "the schedule lists one panel per fan"))
    return job(system([d]))


def counted_job() -> Job:
    count = Count(value=12, sources=(Ref("S1", "counted on the sheet picture", "M-101, Invented.pdf page 2"),),
                  others=(OtherCount(4, Ref("S2", "schedule rows 4", "equipment counts for EF")),
                          OtherCount(3, Ref("S3", "plan placements 3", "equipment counts for EF")),
                          OtherCount(2, Ref("S4", "plan placements 2", "equipment counts for EF"))))
    fam = Family("Exhaust Fan", ("EF-1", "EF-2"), count)
    return job(system([device(qty=12, name="co sensor"), device(id="X.d2", qty=12, name="exhaust fan status points"),
                       device(id="X.d3", qty=12, name="it room fa relay of the fan")], families=(fam,)))


# ---- the test the bug names ---------------------------------------------------------------------------------------

def test_the_assumption_reason_lead_comes_from_the_wording(tmp_path):
    pb = playbook_with(tmp_path, lambda d: d.update(assumption={"because": "since "}))
    out = texts(render(assumed_job(), pb))
    assert any("one controller per fan, since the schedule lists one panel per fan" in t for t in out), out
    assert not any("because" in t for t in out)


def test_without_the_key_the_reason_still_reads_because(tmp_path):
    pb = load_playbook(ROOT / "playbook")
    out = texts(render(assumed_job(), pb))
    assert any("one controller per fan, because the schedule lists one panel per fan" in t for t in out), out


def test_a_reason_starting_with_a_lead_from_the_wording_gets_no_second_lead(tmp_path):
    pb = playbook_with(tmp_path, lambda d: d.update(assumption={"leads": ["owing to "]}))
    d = device(assumption=Assumption("one per fan", "owing to the schedule"))
    out = texts(render(job(system([d])), pb))
    assert any("one per fan, owing to the schedule" in t for t in out), out


# ---- every default, set in the file, prints exactly what leaving it out prints ------------------------------------

def test_the_defaults_written_into_the_wording_print_byte_identical(tmp_path):
    def all_defaults(data):
        data["assumption"] = DEFAULTS["assumption"]
        data["casing"] = DEFAULTS["casing"]
        data["header"].update(DEFAULTS["header"])
        data["quantity"].update(DEFAULTS["quantity"])
    plain = load_playbook(SAMPLE)
    full = playbook_with(tmp_path, all_defaults)
    for j in (assumed_job(), counted_job()):
        a, b = render(j, plain), render(j, full)
        assert a.lines == b.lines
        assert a.scope == b.scope


def test_the_counted_job_prints_as_before_with_the_sample_playbook():
    out = texts(render(counted_job(), load_playbook(SAMPLE)))
    assert "Qty (12) Exhaust Fans EF-1, 2" in out
    assert any(t.startswith("Furnish and Install CO Sensor") for t in out), out
    assert any(t.startswith("Furnish and Install Exhaust Fan Status Points") for t in out), out
    assert any(t.startswith("Furnish and Install IT Room FA Relay of the Fan") for t in out), out
    [note] = [t for t in out if "(12) per M-101" in t]
    assert "(12) per M-101; 4 per schedule rows; 3 and 2 per plan placements" in note


# ---- each key changes its words ----------------------------------------------------------------------------------

def test_the_count_note_joiners_and_labels_come_from_the_wording(tmp_path):
    def change(data):
        data["quantity"].update({"per": " from ", "and": " & ", "joiner": " | ",
                                 "labels": {"schedule_rows": "the schedule's rows", "plan_placements": "the plans"}})
    out = texts(render(counted_job(), playbook_with(tmp_path, change)))
    [note] = [t for t in out if "(12) from M-101" in t]
    assert "(12) from M-101 | 4 from the schedule's rows | 3 & 2 from the plans" in note


def test_the_generic_header_comes_from_the_wording(tmp_path):
    pb = playbook_with(tmp_path, lambda d: d["header"].update(generic="{name} {tags} (Qty {n})"))
    out = texts(render(counted_job(), pb))
    assert "Exhaust Fans EF-1, 2 (Qty 12)" in out


def test_the_casing_lists_come_from_the_wording(tmp_path):
    def change(data):
        data["casing"] = {"acronyms": ["DDC", "EXH"], "small_words": ["the"], "not_plural": ["fans"],
                          "acronym_before": {"co": ["detector"]}}
    j = job(system([device(name="co sensor"), device(id="X.d2", name="exh fan status of the fans"),
                    device(id="X.d3", name="co detector")]))
    out = texts(render(j, playbook_with(tmp_path, change)))
    assert any(t.startswith("Furnish and Install Co Sensor") for t in out), out
    assert any(t.startswith("Furnish and Install CO Detector") for t in out), out
    assert any(t.startswith("Furnish and Install EXH Fan Status Of the Fans") for t in out), out


def test_the_not_plural_list_keeps_a_one_unit_header_word(tmp_path):
    pb = playbook_with(tmp_path, lambda d: d.update(casing={"not_plural": ["fans"]}))
    one = job(system([device(qty=1)], name="Exhaust Fans", families=(Family("Exhaust Fans", ("EF-1",), Count(value=1)),)))
    assert "Qty (1) Exhaust Fans EF-1" in texts(render(one, pb))
    assert "Qty (1) Exhaust Fan EF-1" in texts(render(one, load_playbook(SAMPLE)))


# ---- the loader checks the new keys ------------------------------------------------------------------------------

@pytest.mark.parametrize("change, message", [
    (lambda d: d.update(assumption={"because": "because {why} "}), "assumption.because"),
    (lambda d: d.update(assumption={"because": "  "}), "assumption.because"),
    (lambda d: d.update(assumption={"leads": "as "}), "assumption.leads"),
    (lambda d: d.update(assumption={"lead": "as "}), "assumption"),
    (lambda d: d["header"].update(generic="{name} {tags}"), "header.generic"),
    (lambda d: d["header"].update(generic="Qty ({n}) {name} {tag}"), "header.generic"),
    (lambda d: d["quantity"].update(per=" per {n} "), "quantity.per"),
    (lambda d: d["quantity"].update(labels={"risers": "the riser"}), "quantity.labels"),
    (lambda d: d["quantity"].update(labels={"riser": ""}), "quantity.labels"),
    (lambda d: d["quantity"].update(labels={"riser": "the {riser}"}), "quantity.labels.riser"),
    (lambda d: d.update(casing={"acronyms": "BMS"}), "casing.acronyms"),
    (lambda d: d.update(casing={"acronyms": ["B M S"]}), "casing.acronyms"),
    (lambda d: d.update(casing={"small_words": ["The"]}), "casing.small_words"),
    (lambda d: d.update(casing={"acronym_before": {"co": "sensor"}}), "casing.acronym_before"),
    (lambda d: d.update(casing={"capitals": []}), "casing"),
])
def test_a_malformed_new_key_is_refused(tmp_path, change, message):
    with pytest.raises(PlaybookError, match=message.replace(".", r"\.")):
        playbook_with(tmp_path, change)
