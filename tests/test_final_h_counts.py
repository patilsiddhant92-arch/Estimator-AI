"""FINAL-H (2) and (3). Invented fixtures only.

(2) FINAL-I (lead ruling) replaces FINAL-G's "a numbered unit's tag counts once over the set", which made a
    numbered TYPE used once per floor 1: plans that are not one plan group add up, so EBB-1 on ten floors' plans is
    10, and the counts line's reading notes (the estimator's and the writers' hint, never the client's note) name
    each numbered tag counted on 2 or more plans, since it may be one unit shown again. Nothing lowers a count: a
    schedule's QUANTITY column still prints when it is the higher count.
(3) The retired count causes ("same plan as", "shown again") are gone from the renderer, the inventory's words and
    the Playbook's count_causes slot; the loader takes exactly the remaining keys."""
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from bms import render as render_module
from bms.playbook import COUNT_CAUSE_KEYS, PlaybookError, load_playbook
from bms.playbook_lint import lint_playbook
from estimator.reading import inventory
from estimator.reading.schedules import Schedule, ScheduleRow
from estimator.writing.dossier import build_dossier
from test_count_cause_note import DWG, ROOT, SAMPLE_PLAYBOOK, _catalogue, _family_count, _note, _page, _sheet

FLOORS = range(1, 11)
NOTE = ("EBB-1 is on 10 plans (M-101, M-102, M-103 …), counted on each, 10: likely a type used on each plan; if it "
        "is one unit shown on several plans, it is 1: check the schedule's quantity")


def _floors(text="EBB-1"):
    pages = [_page(n, text) for n in FLOORS]
    sheets = [_sheet(n, f"M-1{n:02d}", f"HVAC FLOOR {n} PLAN") for n in FLOORS]
    return pages, sheets


def _reading(schedules=()):
    return SimpleNamespace(schedules=tuple(schedules), totals=(), devices=(), typicals=(), notes=(), backbone=(),
                           versions=(), supersessions=(), inventory=(), legend=(), flags=())


def _quantity_schedule(tag, quantity, page):
    row = ScheduleRow(tag, {"TAG": tag, "QUANTITY": str(quantity)}, None, None, False)
    return Schedule(DWG, page, "M-601", "EBB SCHEDULE", ("TAG", "QUANTITY"), (row,), False, (), (), False)


def _line(prefix, d):
    return next(line for line in d.text.splitlines() if f"] {prefix} (" in line)


# ---- (2) the reading note ----------------------------------------------------------------------------------------

def test_a_numbered_tag_on_ten_plan_sheets_counts_on_each_with_a_reading_note(tmp_path):
    pages, sheets = _floors()
    catalogue = _catalogue(pages, sheets, ["EBB-1"])
    d = build_dossier(catalogue, _reading(), tmp_path)
    assert d.counts["EBB"]["plan_placements"] == 10          # FINAL-I: ten plans add up (FINAL-G 1)
    line = _line("EBB", d)
    assert NOTE in line and line.index("Reading notes:") < line.index(NOTE)
    # the estimator's hint never reaches the client's note
    count = _family_count(catalogue, _reading(), "EBB", tmp_path / "again")
    for text in _note(count, "Electric Baseboard", ("EBB-1",)):
        assert "counted on each" not in text and "check" not in text and "EBB-1" not in text
    # controls: a numbered tag on one plan sheet, and a type's tag (counted at every place), get no such note
    one = build_dossier(_catalogue([_page(1, "EF-1\nEF-2")], [_sheet(1, "M-101", "HVAC ROOF PLAN")],
                                   ["EF-1", "EF-2"]), _reading(), tmp_path / "one")
    assert "counted on each" not in _line("EF", one)
    pages, sheets = _floors("EBB-A")
    typed = build_dossier(_catalogue(pages, sheets, ["EBB-A"]), _reading(), tmp_path / "typed")
    assert typed.counts["EBB"]["plan_placements"] == 10
    assert "counted on each" not in _line("EBB", typed)


def test_the_notes_name_at_most_three_tags(tmp_path):
    """FINAL-I: two floors' plans repeating five boxes add up (10), and at most three tags are named. A ductwork and
    a piping plan of one floor are one plan group instead (5), named once, with no tag counted on each."""
    tags = [f"VAV-{n}" for n in range(1, 6)]
    text = "\n".join(tags)
    pages = [_page(1, text), _page(2, text)]
    sheets = [_sheet(1, "M-101", "HVAC FIRST FLOOR PLAN"), _sheet(2, "M-102", "HVAC SECOND FLOOR PLAN")]
    d = build_dossier(_catalogue(pages, sheets, tags), _reading(), tmp_path)
    line = _line("VAV", d)
    assert d.counts["VAV"]["plan_placements"] == 10
    for tag in tags[:3]:
        assert f"{tag} is on 2 plans (M-101, M-102), counted on each, 2" in line
    assert "VAV-4 is on" not in line and "2 more tags so" in line
    sheets = [_sheet(1, "M-101", "HVAC DUCTWORK FIRST FLOOR PLAN"), _sheet(2, "M-201", "HVAC PIPING FIRST FLOOR PLAN")]
    d = build_dossier(_catalogue(pages, sheets, tags), _reading(), tmp_path / "group")
    line = _line("VAV", d)
    assert d.counts["VAV"]["plan_placements"] == 5
    assert "M-101 and M-201 counted as one plan" in line and "counted on each" not in line


def test_a_tag_on_a_typical_sheet_says_it_counts_once_per_floor(tmp_path):
    """A unit's tag on a typical sheet (5 floors) and on an enlarged plan: FINAL-I, two plan groups (the titles
    differ) that add up, 5 + 1 (FINAL-G 5), and the note names both plans."""
    pages = [_page(1, "VAV-1"), _page(2, "VAV-1")]
    sheets = [_sheet(1, "M-102", "TYPICAL FLOOR PLAN"), _sheet(2, "M-501", "ENLARGED PLAN")]
    reading = _reading()
    reading.typicals = (SimpleNamespace(sheet="M-102", floors=tuple(range(2, 7))),)
    d = build_dossier(_catalogue(pages, sheets, ["VAV-1"]), reading, tmp_path)
    assert d.counts["VAV"]["plan_placements"] == 6
    line = _line("VAV", d)
    assert "VAV-1 is on 2 plans (M-102, M-501), counted on each, 6" in line


def test_nothing_lowers_a_count_the_schedules_quantity_wins(tmp_path):
    """EBB-1 once on each of 10 floor plans and a QUANTITY of 12 on its schedule row: the family's count is 12, the
    higher count, with the plan placements (10, FINAL-I; FINAL-G 1) kept as the other count; the note is there too."""
    pages, sheets = _floors()
    pages.append(_page(11, "EBB SCHEDULE\nEBB-1"))
    sheets.append(_sheet(11, "M-601", "SCHEDULES", types=("Schedules",)))
    catalogue = _catalogue(pages, sheets, ["EBB-1"])
    reading = _reading([_quantity_schedule("EBB-1", 12, 11)])
    d = build_dossier(catalogue, reading, tmp_path)
    assert d.counts["EBB"]["plan_placements"] == 10 and d.counts["EBB"]["quantity_column"] == 12
    assert NOTE in _line("EBB", d)
    count = _family_count(catalogue, reading, "EBB", tmp_path / "again")
    assert count.value == 12 and count.highest() == 12
    assert 10 in {o.value for o in count.others}                  # the plan placements, kept as the other count


# ---- (3) the retired count causes --------------------------------------------------------------------------------

def test_the_retired_causes_are_gone():
    assert COUNT_CAUSE_KEYS == ("form", "joiner", "typical", "labelled_twice")
    assert set(inventory.COUNT_CAUSE_WORDS) == {"typical", "labelled_twice"}
    assert not hasattr(inventory, "SAME_PLAN")
    assert not hasattr(render_module, "_SAME_PLAN_ON_LINE")
    for root in (ROOT / "playbook", SAMPLE_PLAYBOOK):
        causes = load_playbook(root).wording.count_causes
        assert set(causes) == set(COUNT_CAUSE_KEYS)
        described = json.loads((root / "wording.json").read_text(encoding="utf-8"))["$format"]["count_causes"]
        assert "same_plan" not in described and "shown_again" not in described
    assert lint_playbook(ROOT / "playbook") == []                   # the linter passes the repo playbook


@pytest.mark.parametrize("extra", ["same_plan", "shown_again"])
def test_a_wording_file_that_still_carries_a_retired_cause_is_refused(tmp_path, extra):
    folder = tmp_path / "pb"
    shutil.copytree(SAMPLE_PLAYBOOK, folder)
    data = json.loads((folder / "wording.json").read_text(encoding="utf-8"))
    data["count_causes"] = {"form": "({causes})", "joiner": ", ", "typical": "a typical unit at each place",
                            "labelled_twice": "one unit labelled more than once"}
    (folder / "wording.json").write_text(json.dumps(data), encoding="utf-8")
    assert set(load_playbook(folder).wording.count_causes) == set(COUNT_CAUSE_KEYS)   # exactly these four load
    data["count_causes"][extra] = "some words"
    (folder / "wording.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(PlaybookError, match="count_causes must have exactly"):
        load_playbook(folder)
