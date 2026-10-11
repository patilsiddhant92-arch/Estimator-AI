"""T-005a (estimator rulings 1 and 2 of 2026-10-11), after the first live run of 26-0544 printed AHU 21 for 5 units.

- Ruling 2: a numbered unit tag (AHU-1, EF-3) is ONE unit in the whole job, however many plan sheets show it (a
  ductwork plan, a piping plan, an equipment plan and a roof plan of one penthouse, or part plans that overlap at a
  match line): count distinct unit tags, never placements. The other labels are duplicates, named in the counts
  line. A TYPE tag (FCU-1 shown 55 times with one schedule row, EBB-A) still counts at every place.
- Ruling 1: a demolition plan shows the previous job's units. Its units are left out of every count, unless the
  documents name work on that unit (refurbishment, relocation of its sensors or thermostats). A unit left out so is
  named in the counts line with both numbers. Device labels (thermostats) are counted from new-work sheets only.

On 26-0544, AHU-1..5 were counted on each of M114.00, M214.00, M314.00 and M315.00 (20) plus AHU-6 from the
demolition sheet MD 315.00 (21). Invented fixtures only."""
from pathlib import Path
from types import SimpleNamespace

import pymupdf
import pytest

from estimator.catalogue.register import PageRecord
from estimator.catalogue.sheet_types import Sheet, SheetTypes, is_demolition, types_of
from estimator.reading.devices import count_devices
from estimator.reading.inventory import demolition_work, placements, plan_count
from estimator.writing.dossier import build_dossier
from pdfs import FILLER, Page, make_pdf
from test_dossier_plan_areas import DWG, _catalogue, _line, _page, _reading, _schedule, _sheet

DEMO = ("Plans", "Demolition")
UNITS = [f"AHU-{n}" for n in range(1, 6)]


# ---- sheet typing --------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("title", ["MECHANICAL DEMOLITION PENTHOUSE ROOF PLAN", "HVAC DEMO PLAN - LEVEL 2",
                                   "FIRST FLOOR PLAN - EXISTING TO BE REMOVED", "HVAC REMOVALS PLAN"])
def test_demolition_titles_are_typed_demolition(title):
    sheet = Sheet(DWG, 1, "MD-1", title, "Mechanical", types_of(title, SheetTypes.load()))
    assert "Demolition" in sheet.types and is_demolition(sheet)


def test_a_sheet_of_demolition_and_new_work_is_a_new_work_sheet():
    title = "HVAC DEMOLITION AND NEW WORK FIRST FLOOR PLAN"
    sheet = Sheet(DWG, 1, "M-101", title, "Mechanical", types_of(title, SheetTypes.load()))
    assert "Demolition" in sheet.types and not is_demolition(sheet)
    assert not is_demolition(_sheet(1, "M-101", "MECHANICAL CONSTRUCTION PENTHOUSE PLAN"))


# ---- ruling 2: a numbered unit tag is one unit in the whole job ------------------------------------------------------

def test_plan_count_counts_a_unit_tag_once_over_every_plan_group():
    found = [(("d", 1), 1, frozenset()), (("d", 2), 1, frozenset()), (("d", 3), 2, frozenset())]
    assert plan_count(found, {}, per_place=False) == 1
    # a type's tag still counts every place: the most of one sheet of each group, the groups added up
    assert plan_count(found, {}, per_place=True) == 4


def test_plan_count_still_multiplies_a_unit_tag_by_the_floors_of_a_typical_sheet():
    found = [(("d", 1), 1, frozenset({"2", "3", "4"})), (("d", 2), 1, frozenset({"4", "5"}))]
    assert plan_count(found, {}, per_place=False) == 4          # floors 2 to 5, every floor once


def _penthouse(extra_pages=(), extra_sheets=(), schedule=True):
    """26-0544's shape: AHU-1..5 on four new-work penthouse plans of four trades and titles (ductwork, piping,
    equipment, roof), the schedule on its own sheet, and whatever demolition sheets the test adds."""
    text = "\n".join(UNITS)
    pages = [_page(DWG, 1, text), _page(DWG, 2, text), _page(DWG, 3, text), _page(DWG, 4, text),
             _page(DWG, 5, "AHU SCHEDULE\n" + text), *extra_pages]
    sheets = [_sheet(1, "M114.00", "MECHANICAL CONSTRUCTION DUCTWORK PENTHOUSE PLAN"),
              _sheet(2, "M214.00", "MECHANICAL CONSTRUCTION PIPING PENTHOUSE PLAN"),
              _sheet(3, "M314.00", "MECHANICAL CONSTRUCTION EQUIPMENT PENTHOUSE PLAN"),
              _sheet(4, "M315.00", "MECHANICAL CONSTRUCTION PENTHOUSE ROOF PLAN"),
              _sheet(5, "M610.00", "MECHANICAL SCHEDULES", types=("Schedules",)), *extra_sheets]
    tags = UNITS + ["AHU-6"]
    reading = _reading([_schedule("AHU SCHEDULE", UNITS, 5, sheet="M610.00")] if schedule else [])
    return _catalogue(pages, sheets, tags), reading


def test_a_unit_on_four_plans_of_one_penthouse_counts_once_and_the_duplicates_are_named(tmp_path):
    catalogue, reading = _penthouse()
    d = build_dossier(catalogue, reading, tmp_path)
    assert d.counts["AHU"]["plan_placements"] == 5               # was 20: 5 tags x 4 plans
    line = _line("AHU", d)
    assert "AHU-1 is on 4 plans (M114.00, M214.00, M314.00 …), counted once, 1" in line
    assert "a numbered unit tag is one unit in the job" in line
    assert "if each plan's AHU-1 is its own unit (a type used once per plan), 4" in line     # both numbers, for the estimator


def test_part_plans_that_overlap_count_a_unit_once_with_a_note(tmp_path):
    """Two part plans of one floor overlap at a match line: EF-3 is drawn on both. One unit, said in the line."""
    pages = [_page(DWG, 1, "EF-1\nEF-2\nEF-3"), _page(DWG, 2, "EF-3\nEF-4")]
    sheets = [_sheet(1, "M-101A", "HVAC FIRST FLOOR PART PLAN A"), _sheet(2, "M-101B", "HVAC FIRST FLOOR PART PLAN B")]
    d = build_dossier(_catalogue(pages, sheets, ["EF-1", "EF-2", "EF-3", "EF-4"]), _reading(), tmp_path)
    assert d.counts["EF"]["plan_placements"] == 4
    assert "EF-3 is on 2 plans (M-101A, M-101B), counted once, 1" in _line("EF", d)


def test_a_type_tag_still_counts_at_every_place_on_new_work_plans(tmp_path):
    pages = [_page(DWG, 1, "\n".join(["FCU-1"] * 30)), _page(DWG, 2, "\n".join(["FCU-1"] * 25))]
    sheets = [_sheet(1, "M111.00", "MECHANICAL CONSTRUCTION DUCTWORK FIRST FLOOR PLAN"),
              _sheet(2, "M112.00", "MECHANICAL CONSTRUCTION DUCTWORK SECOND FLOOR PLAN")]
    d = build_dossier(_catalogue(pages, sheets, ["FCU-1"]), _reading(), tmp_path)
    assert d.counts["FCU"]["plan_placements"] == 55


def test_the_inventory_counts_a_unit_on_four_plans_once():
    catalogue, _reading_ = _penthouse()
    placed = placements(catalogue, UNITS)
    assert all(placed[tag].count == 1 for tag in UNITS)
    assert placed["AHU-1"].summed == 1                           # no sheets-added-up number for a unit's tag


# ---- ruling 1: demolition sheets ----------------------------------------------------------------------------------

def _with_demolition(note=""):
    pages = [_page(DWG, 6, "AHU-6\nEF-6\nAHU-1"), _page(DWG, 7, "\n".join(["FCU-1"] * 3))]
    sheets = [_sheet(6, "MD 315.00", "MECHANICAL DEMOLITION PENTHOUSE ROOF PLAN", types=DEMO),
              _sheet(7, "MD 111.00", "MECHANICAL DEMOLITION DUCTWORK FIRST FLOOR PLAN", types=DEMO)]
    if note:
        pages.append(_page(DWG, 8, f"GENERAL NOTES\n1. {note}"))
        sheets.append(_sheet(8, "M001.00", "MECHANICAL GENERAL NOTES AND LEGENDS", types=("Notes and legends",)))
    return pages, sheets


def test_a_unit_only_on_a_demolition_plan_is_left_out_and_named_with_both_numbers(tmp_path):
    pages, sheets = _with_demolition()
    catalogue, reading = _penthouse(pages, sheets)
    d = build_dossier(catalogue, reading, tmp_path)
    assert d.counts["AHU"]["plan_placements"] == 5               # was 21 on 26-0544
    line = _line("AHU", d)
    assert ("AHU-6 is on demolition sheets only (MD 315.00): left out of the count, 5; with the demolition sheets, "
            "6") in line
    assert "AHU-6" not in line.split("Tags:")[1].split(".")[0]   # not among the counted tags


def test_a_type_tag_on_a_demolition_plan_is_left_out_and_named_with_both_numbers(tmp_path):
    new = [_page(DWG, 1, "\n".join(["FCU-1"] * 5))]
    sheet = [_sheet(1, "M111.00", "MECHANICAL CONSTRUCTION DUCTWORK FIRST FLOOR PLAN")]
    pages, sheets = _with_demolition()
    d = build_dossier(_catalogue(new + pages, sheet + sheets, ["FCU-1", "AHU-1", "AHU-6", "EF-6"]), _reading(),
                      tmp_path)
    assert d.counts["FCU"]["plan_placements"] == 5
    assert ("FCU-1 has 3 more labels on demolition sheets (MD 111.00): left out of the count, 5; with the demolition "
            "sheets, 8") in _line("FCU", d)


def test_a_unit_on_a_demolition_plan_with_work_named_on_it_is_counted(tmp_path):
    pages, sheets = _with_demolition("REFURBISH EXISTING AHU-6 AND RELOCATE ITS SPACE SENSOR.")
    catalogue, reading = _penthouse(pages, sheets)
    assert set(demolition_work(catalogue, ["AHU-6", "EF-6"])) == {"AHU-6"}
    d = build_dossier(catalogue, reading, tmp_path)
    assert d.counts["AHU"]["plan_placements"] == 6
    line = _line("AHU", d)
    assert "AHU-6 is on demolition sheets only (MD 315.00), counted: the documents name work on it" in line


def test_the_inventory_leaves_a_demolition_unit_out():
    pages, sheets = _with_demolition()
    catalogue, _r = _penthouse(pages, sheets)
    placed = placements(catalogue, UNITS + ["AHU-6"])
    assert "AHU-6" not in placed or placed["AHU-6"].count == 0
    assert placed["AHU-1"].count == 1 and "MD 315.00" not in placed["AHU-1"].on_plans


def test_a_removal_line_names_no_work():
    pages = [_page(DWG, 1, "1. REMOVE EXISTING AHU-6 IN ITS ENTIRETY.\n2. EF-6 EXISTING TO REMAIN.")]
    catalogue = _catalogue(pages, [_sheet(1, "M001.00", "NOTES", types=("Notes and legends",))], ["AHU-6", "EF-6"])
    assert demolition_work(catalogue, ["AHU-6", "EF-6"]) == {}


# ---- devices (thermostats) from new-work sheets only ------------------------------------------------------------------

W, H = 3024, 2160


def test_thermostats_on_a_demolition_plan_are_not_counted_and_the_flag_says_both_numbers(tmp_path):
    new = Page(W, H, ((200, 300, FILLER, 12), (400, 500, "T", 12), (700, 500, "T", 12)))
    demo = Page(W, H, ((200, 300, FILLER, 12), (400, 500, "T", 12), (700, 500, "T", 12), (900, 800, "T", 12)))
    path = make_pdf(tmp_path / "Mech.pdf", new, demo)
    doc = pymupdf.open(str(path))
    try:
        sheets = (Sheet("Mech.pdf", 1, "M111.00", "MECHANICAL CONSTRUCTION FIRST FLOOR PLAN", "Mechanical", ("Plans",)),
                  Sheet("Mech.pdf", 2, "MD 111.00", "MECHANICAL DEMOLITION FIRST FLOOR PLAN", "Mechanical", DEMO))
        pages = tuple(PageRecord("Mech.pdf", i, "text", f"page {i}", 0, True) for i in (1, 2))
        catalogue = SimpleNamespace(pages=pages, sheets=sheets)
        counts, flags = count_devices(catalogue, lambda d, p: doc[p - 1], [], [], pages={("Mech.pdf", 1),
                                                                                          ("Mech.pdf", 2)})
    finally:
        doc.close()
    assert [(c.sheet, c.label, c.total) for c in counts] == [("M111.00", "T", 2)]
    assert any("'T' 3 more on demolition sheets (MD 111.00): left out of the count, 2; with them, 5" in f
               for f in flags)


# ---- the vision cross-check reads new-work plans only -------------------------------------------------------------

def test_the_cross_check_does_not_count_tags_on_a_demolition_plan(tmp_path):
    import json

    from bms import counts
    from bms.model import Job
    from estimator.catalogue.documents import Document

    texts_new = ((200, 200, FILLER, 10), (300, 400, "EF-1", 14), (900, 300, "EF-2", 14), (1500, 900, "EF-3", 14))
    texts_demo = ((200, 200, FILLER, 10), (300, 400, "EF-1", 14), (900, 300, "EF-5", 14), (1500, 900, "EF-6", 14),
                  (600, 700, "EF-7", 14))
    pdf = make_pdf(tmp_path / "job" / "Drawings.pdf", Page(1728, 1152, texts_new), Page(1728, 1152, texts_demo))
    document = Document(pdf, pdf.name, "drawings", "base", 2)
    job_ns = SimpleNamespace(name="26-9999", root=pdf.parent, documents=(document,))
    records = (PageRecord(pdf.name, 1, "text", "\n".join(t for *_x, t, _s in texts_new), 0, True),
               PageRecord(pdf.name, 2, "text", "\n".join(t for *_x, t, _s in texts_demo), 0, True))
    sheets = (Sheet(pdf.name, 1, "M-101", "FIRST FLOOR PLAN", "Mechanical", ("Plans",)),
              Sheet(pdf.name, 2, "MD-101", "FIRST FLOOR DEMOLITION PLAN", "Mechanical", DEMO))
    catalogue = SimpleNamespace(job=job_ns, pages=records, sheets=sheets, sections=(), tags=(), bid=None, flags=())
    sample = Path(__file__).resolve().parent / "bms" / "fixtures" / "sample_job.json"
    job = Job.from_dict(json.loads(sample.read_text(encoding="utf-8")))
    checked = counts.cross_check(job, catalogue, tmp_path / "cache")
    ef = next(f for f in checked.system("EF").families if f.name == "Exhaust Fan").count
    assert ef.value == 3                                          # not 6 with EF-5..7 from the demolition plan
    assert all("MD-101" not in (s.where or "") for s in ef.sources)
