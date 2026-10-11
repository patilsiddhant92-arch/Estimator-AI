"""The quantity note names the likely cause of a high plan count in plain words (FINAL-A, task 1).

The dossier's counts line names why the plan placements are above every other count (a typical unit at each
place, a type's tag labelled more than once). FINAL-G: a unit's tag counts once however many sheets show it, so
"one unit's tag on several plans" and "a floor drawn on two plan sheets counted once" are never a cause any more. The
cause reaches the ledger's count fact (the head of the line) and the client's "*Qty." note prints it in the
Playbook's words (`wording.json` "count_causes"), never the estimator's hints (tags, sheets, "check ..."). Invented
fixtures only."""
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from bms.model import Count, Device, Family, Header, Job, OtherCount, Ref, System
from bms.playbook import PlaybookError, load_playbook
from bms.plan_read import Reader
from bms.render import render
from estimator.catalogue.documents import Document
from estimator.catalogue.overview import SpecOverview
from estimator.catalogue.register import PageRecord
from estimator.catalogue.sheet_types import Sheet
from estimator.catalogue.tags import TagEntry
from estimator.ledger.seed import seed
from estimator.reading.schedules import Schedule, ScheduleRow
from estimator.writing.dossier import build_dossier

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PLAYBOOK = ROOT / "tests" / "bms" / "fixtures" / "sample_playbook"
DWG = "Drawings/Mech.pdf"


def _page(page, text):
    return PageRecord(DWG, page, "text", text, 0, True, ())


def _sheet(page, number, title, types=("Plans",)):
    return Sheet(DWG, page, number, title, "Mechanical", tuple(types))


def _catalogue(pages, sheets, tags):
    job = SimpleNamespace(name="26-9999", root=Path("."),
                          documents=(Document(Path(DWG), DWG, "drawings", "base", max(p.page for p in pages)),))
    return SimpleNamespace(job=job, pages=tuple(pages), sheets=tuple(sheets), sections=(),
                           tags=tuple(TagEntry(t, "", (), ("M-101",), 2) for t in tags), overview=SpecOverview(),
                           bid=None, flags=())


def _reading(title, tags, page):
    rows = tuple(ScheduleRow(t, {"TAG": t}, None, None, False) for t in tags)
    schedule = Schedule(DWG, page, "M-601", title, ("TAG",), rows, False, (), (), False)
    return SimpleNamespace(schedules=(schedule,), totals=(), devices=(), typicals=(), notes=(), backbone=(),
                           versions=(), supersessions=(), inventory=(), legend=(), flags=())


def _family_count(catalogue, reading, prefix, tmp_path) -> Count:
    d = build_dossier(catalogue, reading, tmp_path)
    ledger = seed(d)
    return Reader(ledger, d.sources, d.text).count_of(ledger.find("count", prefix))


def _note(count: Count, name="Exhaust Fan", tags=("EF-1",)) -> list[str]:
    pb = load_playbook(ROOT / "playbook")
    controller = Device(id="X.d1", slot="controller", name="DDC Controller", verb="Furnish and Install",
                        furnished_by="AME", installed_by="AME", wired_by="AME", quantity=Count(count.highest()),
                        refs=(Ref("S1", "q", "M-1, Drawings.pdf page 1"),))
    system = System(key="X", name=name, shape="", control="field", families=(Family(name, tags, count),),
                    devices=(controller,))
    job = Job(name="Invented", systems=(system,), header=Header("00-0000", "Invented", "Invented", ("A",),
                                                                "2026-10-04"))
    # T-005e: estimator ruling 15 (2026-10-11 afternoon): the other counts print in the line itself (the family's
    # header), no separate "*Qty." note: the header's bracket of counts
    header = next(line.text for line in render(job, pb).lines if line.kind == "header")
    return [header[header.index(" (", header.index(")")) + 1:]] if " (" in header[header.index(")"):] else []


def _sheets_and_schedule(*plans):
    sheets = [_sheet(n, number, title) for n, (number, title, _text) in enumerate(plans, start=1)]
    pages = [_page(n, text) for n, (_number, _title, text) in enumerate(plans, start=1)]
    return pages, sheets, len(plans) + 1


def test_a_unit_tag_on_several_floors_plans_counts_on_each_and_claims_no_cause(tmp_path):
    """T-005a (estimator ruling 2 of 2026-10-11): a numbered unit tag is one unit in the job, so EF-1 on three
    floors' plans is 1 (FINAL-I added them up, 3), as the schedule says: no other count, no note, no cause."""
    pages, sheets, at = _sheets_and_schedule(("M-101", "HVAC FIRST FLOOR PLAN", "EF-1"),
                                             ("M-102", "HVAC SECOND FLOOR PLAN", "EF-1"),
                                             ("M-106", "HVAC ROOF PLAN", "EF-1"))
    pages.append(_page(at, "EF SCHEDULE\nEF-1"))
    sheets.append(_sheet(at, "M-601", "SCHEDULES", types=("Schedules",)))
    count = _family_count(_catalogue(pages, sheets, ["EF-1"]), _reading("EF SCHEDULE", ["EF-1"], at), "EF", tmp_path)
    assert count.highest() == 1
    assert _note(count) == []


def test_a_type_tag_printed_twice_on_one_sheet_prints_one_unit_labelled_more_than_once(tmp_path):
    """FINAL-G: a unit's tag twice on a sheet (ACCU-1) is one unit now; a type's tag twice (EBB-B) keeps the cause."""
    pages, sheets, at = _sheets_and_schedule(("M-106", "HVAC ROOF PLAN", "EBB-B\nEBB-B\nEBB-C\nEBB-C"))
    pages.append(_page(at, "EBB SCHEDULE\nEBB-B\nEBB-C"))
    sheets.append(_sheet(at, "M-601", "SCHEDULES", types=("Schedules",)))
    count = _family_count(_catalogue(pages, sheets, ["EBB-B", "EBB-C"]),
                          _reading("EBB SCHEDULE", ["EBB-B", "EBB-C"], at), "EBB", tmp_path)
    assert _note(count, "Baseboard Heater", ("EBB-B", "EBB-C")) == [
        "(4 per plan placements (likely one unit labelled more than once on a sheet); 2 per schedule rows)"]


def test_a_typical_type_tag_prints_a_typical_unit_at_each_place(tmp_path):
    pages, sheets, at = _sheets_and_schedule(("M-201", "PIPING AND CONTROLS FIRST FLOOR PLAN", "\n".join(["EBB-A"] * 6)),
                                             ("M-202", "PIPING AND CONTROLS SECOND FLOOR PLAN", "\n".join(["EBB-A"] * 6)))
    pages.append(_page(at, "EBB SCHEDULE\nEBB-A"))
    sheets.append(_sheet(at, "M-601", "SCHEDULES", types=("Schedules",)))
    count = _family_count(_catalogue(pages, sheets, ["EBB-A"]), _reading("EBB SCHEDULE", ["EBB-A"], at), "EBB",
                          tmp_path)
    assert _note(count, "Baseboard Heater", ("EBB-A",)) == [
        "(12 per plan placements (likely a typical unit at each place); 1 per schedule rows)"]


def test_a_floor_drawn_twice_is_never_named_as_a_cause(tmp_path):
    """EF-1 on two floors, each floor drawn on a ductwork plan and a controls plan. Ruling L1: each floor's two sheets
    show one floor and area, one plan group, however few tags they repeat (3 on the first floor, 1 on the second):
    4, printed with no cause (FINAL-I added the second floor's sheets up: 5). T-005a (ruling 2): a numbered unit tag
    is one unit in the job, so EF-1 on both floors is one unit: 3, as the schedule says, and no note."""
    pages, sheets, at = _sheets_and_schedule(("M-101", "HVAC DUCTWORK FIRST FLOOR PLAN", "EF-1\nEF-2\nEF-3"),
                                             ("M-201", "HVAC PIPING AND CONTROLS FIRST FLOOR PLAN", "EF-1\nEF-2\nEF-3"),
                                             ("M-102", "HVAC DUCTWORK SECOND FLOOR PLAN", "EF-1"),
                                             ("M-202", "HVAC PIPING AND CONTROLS SECOND FLOOR PLAN", "EF-1"))
    pages.append(_page(at, "EF SCHEDULE\nEF-1\nEF-2\nEF-3"))
    sheets.append(_sheet(at, "M-601", "SCHEDULES", types=("Schedules",)))
    tags = ["EF-1", "EF-2", "EF-3"]
    count = _family_count(_catalogue(pages, sheets, tags), _reading("EF SCHEDULE", tags, at), "EF", tmp_path)
    assert count.highest() == 3
    assert _note(count, tags=tuple(tags)) == []


def test_the_note_never_carries_the_estimators_hints(tmp_path):
    pages, sheets, at = _sheets_and_schedule(("M-201", "PIPING AND CONTROLS FIRST FLOOR PLAN", "\n".join(["EBB-A"] * 6)),
                                             ("M-202", "PIPING AND CONTROLS SECOND FLOOR PLAN", "\n".join(["EBB-A"] * 6)))
    pages.append(_page(at, "EBB SCHEDULE\nEBB-A"))
    sheets.append(_sheet(at, "M-601", "SCHEDULES", types=("Schedules",)))
    count = _family_count(_catalogue(pages, sheets, ["EBB-A"]), _reading("EBB SCHEDULE", ["EBB-A"], at), "EBB",
                          tmp_path)
    [note] = _note(count, "Baseboard Heater", ("EBB-A",))
    assert "(likely a typical unit at each place)" in note          # the cause prints, in the client's words ...
    for hint in ("check", "EBB-A", "M-201", "M-202", "places,", "Reading notes", "schedule's quantity"):
        assert hint not in note


def test_the_cause_goes_with_the_placements_clause_even_when_another_count_prints():
    head = ("EF (Exhaust Fan): schedule rows 1; QUANTITY column total —; distinct tags 1; plan placements 3 "
            "(M-101 1; M-102 1; M-106 1); riser 5; placements above the other counts, likely: one unit labelled "
            "more than once")
    count = Count(5, (Ref("S5", "riser 5", "equipment counts for EF"),),
                  (OtherCount(3, Ref("S5", "plan placements 3", "equipment counts for EF")),
                   OtherCount(1, Ref("S5", head, "equipment counts for EF"))))
    assert _note(count) == ["(5 per the riser; 3 per plan placements (likely one unit labelled more than once "
                            "on a sheet); 1 per schedule rows)"]


def test_no_cause_prints_when_no_counts_line_names_one():
    count = Count(3, (Ref("S5", "plan placements 3", "equipment counts for EF"),),
                  (OtherCount(1, Ref("S5", "schedule rows 1", "equipment counts for EF")),))
    assert _note(count) == ["(3 per plan placements; 1 per schedule rows)"]


def test_the_counts_line_head_names_the_cause_for_the_ledger(tmp_path):
    pages, sheets, at = _sheets_and_schedule(("M-106", "HVAC ROOF PLAN", "EBB-B\nEBB-B"))
    pages.append(_page(at, "EBB SCHEDULE\nEBB-B"))
    sheets.append(_sheet(at, "M-601", "SCHEDULES", types=("Schedules",)))
    d = build_dossier(_catalogue(pages, sheets, ["EBB-B"]), _reading("EBB SCHEDULE", ["EBB-B"], at), tmp_path)
    fact = seed(d).find("count", "EBB")
    assert fact.quote.endswith("; placements above the other counts, likely: one unit labelled more than once")
    assert "Reading notes" in next(line for line in d.text.splitlines() if "] EBB (" in line)


# ---- the Playbook slot ----------------------------------------------------------------------------------------

def test_the_playbook_gives_every_cause_its_client_words():
    causes = load_playbook(ROOT / "playbook").wording.count_causes
    assert set(causes) == {"form", "joiner", "typical", "labelled_twice"}         # FINAL-H: the retired two removed
    assert "{causes}" in causes["form"]


@pytest.mark.parametrize("change, message", [
    (lambda d: d.pop("count_causes"), "count_causes is missing"),
    (lambda d: d["count_causes"].pop("typical"), "count_causes must have exactly"),
    (lambda d: d["count_causes"].update(form="(causes)"), r"\{causes\}"),
    (lambda d: d["count_causes"].update(typical=""), "count_causes"),
])
def test_a_malformed_count_causes_slot_is_refused(tmp_path, change, message):
    folder = tmp_path / "pb"
    shutil.copytree(SAMPLE_PLAYBOOK, folder)
    data = json.loads((folder / "wording.json").read_text(encoding="utf-8"))
    change(data)
    (folder / "wording.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(PlaybookError, match=message):
        load_playbook(folder)
