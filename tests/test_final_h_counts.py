"""FINAL-H (2) and (3). Invented fixtures only.

(2) A numbered unit's tag counts once however many plan sheets show it (FINAL-G), so a numbered TYPE used once per
    floor cannot be told apart and would be 1: the counts line's reading notes (the estimator's and the writers'
    hint, never the client's note) say so for each such tag on 2 or more plan sheets. Nothing lowers a count: a
    schedule's QUANTITY column above the plan placements still prints, the higher count, flagged.
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
NOTE = ("EBB-1 appears on 10 plan sheets: counted as one unit; if it is a type used on each floor, check the "
        "schedule's quantity")


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

def test_a_numbered_tag_on_ten_plan_sheets_is_one_unit_with_a_reading_note(tmp_path):
    pages, sheets = _floors()
    catalogue = _catalogue(pages, sheets, ["EBB-1"])
    d = build_dossier(catalogue, _reading(), tmp_path)
    assert d.counts["EBB"]["plan_placements"] == 1
    line = _line("EBB", d)
    assert NOTE in line and line.index("Reading notes:") < line.index(NOTE)
    # the estimator's hint never reaches the client's note
    count = _family_count(catalogue, _reading(), "EBB", tmp_path / "again")
    for text in _note(count, "Electric Baseboard", ("EBB-1",)):
        assert "appears" not in text and "check" not in text and "EBB-1" not in text
    # controls: a numbered tag on one plan sheet, and a type's tag (counted at every place), get no such note
    one = build_dossier(_catalogue([_page(1, "EF-1\nEF-2")], [_sheet(1, "M-101", "HVAC ROOF PLAN")],
                                   ["EF-1", "EF-2"]), _reading(), tmp_path / "one")
    assert "appears on" not in _line("EF", one)
    pages, sheets = _floors("EBB-A")
    typed = build_dossier(_catalogue(pages, sheets, ["EBB-A"]), _reading(), tmp_path / "typed")
    assert typed.counts["EBB"]["plan_placements"] == 10
    assert "appears on" not in _line("EBB", typed)


def test_the_notes_name_at_most_three_tags(tmp_path):
    tags = [f"VAV-{n}" for n in range(1, 6)]
    text = "\n".join(tags)
    pages = [_page(1, text), _page(2, text)]
    sheets = [_sheet(1, "M-101", "HVAC DUCTWORK FIRST FLOOR PLAN"), _sheet(2, "M-201", "HVAC PIPING FIRST FLOOR PLAN")]
    d = build_dossier(_catalogue(pages, sheets, tags), _reading(), tmp_path)
    line = _line("VAV", d)
    assert d.counts["VAV"]["plan_placements"] == 5
    for tag in tags[:3]:
        assert f"{tag} appears on 2 plan sheets: counted as one unit" in line
    assert "VAV-4 appears" not in line and "2 more tags so" in line


def test_a_tag_on_a_typical_sheet_says_it_counts_once_per_floor(tmp_path):
    """A unit's tag on a typical sheet (5 floors) and on an enlarged plan counts 5 (once per floor), so the note
    says that instead of "one unit"."""
    pages = [_page(1, "VAV-1"), _page(2, "VAV-1")]
    sheets = [_sheet(1, "M-102", "TYPICAL FLOOR PLAN"), _sheet(2, "M-501", "ENLARGED PLAN")]
    reading = _reading()
    reading.typicals = (SimpleNamespace(sheet="M-102", floors=tuple(range(2, 7))),)
    d = build_dossier(_catalogue(pages, sheets, ["VAV-1"]), reading, tmp_path)
    assert d.counts["VAV"]["plan_placements"] == 5
    line = _line("VAV", d)
    assert ("VAV-1 appears on 2 plan sheets: counted as one unit on each of the 5 floors its typical sheet stands "
            "for") in line


def test_nothing_lowers_a_count_the_schedules_quantity_wins(tmp_path):
    """EBB-1 once on each of 10 floor plans (one placement) and a QUANTITY of 10 on its schedule row: the family's
    count is 10, the higher count, with the plan placements kept as the other count; the note is there too."""
    pages, sheets = _floors()
    pages.append(_page(11, "EBB SCHEDULE\nEBB-1"))
    sheets.append(_sheet(11, "M-601", "SCHEDULES", types=("Schedules",)))
    catalogue = _catalogue(pages, sheets, ["EBB-1"])
    reading = _reading([_quantity_schedule("EBB-1", 10, 11)])
    d = build_dossier(catalogue, reading, tmp_path)
    assert d.counts["EBB"]["plan_placements"] == 1 and d.counts["EBB"]["quantity_column"] == 10
    assert NOTE in _line("EBB", d)
    count = _family_count(catalogue, reading, "EBB", tmp_path / "again")
    assert count.value == 10 and count.highest() == 10
    assert 1 in {o.value for o in count.others}                  # the plan placements, kept as the other count


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
