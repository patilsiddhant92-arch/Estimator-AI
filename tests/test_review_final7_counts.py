"""REVIEW-FINAL7 (reviewer of record): rebuild 1c45bed, lead/final-k. Attacks on the copy test (`document_repeats`),
the one label reader (`line_labels`), the F6 page rule and the typical sheets of another set. The lead's principle:
an undercount (a count below the true number of physical units) is the worst failure.

Each strict xfail asserts the right behaviour and fails on 1c45bed by assertion. The guards pin what holds. Invented
fixtures only (job 26-9999, invented sheets and tags)."""
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from estimator.catalogue.documents import Document
from estimator.catalogue.job import document_repeats
from estimator.catalogue.tags import label_keys, line_labels
from estimator.reading.devices import DeviceCount
from estimator.reading.inventory import placements
from estimator.reading.revisions import SheetVersion, governing_pages, supersede
from estimator.writing.dossier import build_dossier
from test_dossier_plan_areas import DWG, OTHER, _catalogue, _doc, _line, _page, _reading, _schedule, _sheet

REV = "Drawings/Mech Rev 1.pdf"


def _lines(*tags):
    return "\n".join(tags)


def _floor(n):
    return [f"VAV-{n}{k}" for k in (1, 2, 3)]


def _read(catalogue, schedules, reading=None):
    """Only the schedules on governing pages are read, as `read_job` reads them."""
    governing = governing_pages(catalogue, getattr(reading, "supersessions", ()),
                                [t.sheet for t in getattr(reading, "typicals", ())])
    reading = reading or _reading()
    reading.schedules = tuple(s for s in schedules if (s.document, s.page) in governing)
    return reading


# ---- (1) the copy test ---------------------------------------------------------------------------------------------

def _superset_job():
    """Mech.pdf: LEVEL 1 to 3 plans with AHU-1 to 3 (one each) and an AHU schedule. Second Building.pdf: the same
    sheet numbers, the same AHU-1 to 3, and VAV-11 to 33 that Mech.pdf never shows, with its own VAV schedule."""
    pages, sheets = [], []
    for document in (DWG, OTHER):
        for n in (1, 2, 3):
            tags = [f"AHU-{n}"] + (_floor(n) if document == OTHER else [])
            pages.append(_page(document, n, _lines(f"LEVEL {n} PLAN", *tags)))
            sheets.append(_sheet(n, f"M-10{n}", f"LEVEL {n} PLAN", document))
        sheets.append(_sheet(4, "M-601", "SCHEDULES", document, types=("Schedules",)))
    boxes = [t for n in (1, 2, 3) for t in _floor(n)]
    pages += [_page(DWG, 4, _lines("AHU SCHEDULE", "AHU-1", "AHU-2", "AHU-3")),
              _page(OTHER, 4, _lines("VAV SCHEDULE", *boxes))]
    catalogue = _catalogue(pages, sheets, ["AHU-1", "AHU-2", "AHU-3"] + boxes, [_doc(DWG, 4), _doc(OTHER, 4)])
    schedules = [_schedule("AHU SCHEDULE", ["AHU-1", "AHU-2", "AHU-3"], 4),
                 _schedule("VAV SCHEDULE", boxes, 4, document=OTHER)]
    return catalogue, schedules


def test_a_document_whose_plans_show_units_the_other_lacks_is_never_a_marked_up_copy(tmp_path):
    """A marked-up copy only adds clouds and text; it never shows a unit tag its original lacks. Here the 'copy'
    shows VAV-11 to 33, which Mech.pdf never shows: the VAV family must be on the counts line with its 9 units."""
    catalogue, schedules = _superset_job()
    assert all(not r.same for r in document_repeats(catalogue))
    d = build_dossier(catalogue, _read(catalogue, schedules), tmp_path)
    assert d.counts.get("VAV", {}).get("plan_placements", 0) >= 9
    assert d.counts["VAV"]["schedule_rows"] == 9


def _revision_job():
    """Mech.pdf (base) and Mech Rev 1.pdf (revision folder "1"), the same three plans; Rev 1 adds VAV-34 on M-103.
    No revision table dates on either."""
    pages, sheets, tags = [], [], set()
    for document in (DWG, REV):
        for n in (1, 2, 3):
            units = _floor(n) + (["VAV-34"] if document == REV and n == 3 else [])
            pages.append(_page(document, n, _lines(f"LEVEL {n} PLAN", *units)))
            sheets.append(_sheet(n, f"M-10{n}", f"LEVEL {n} PLAN", document))
            tags |= set(units)
    documents = [_doc(DWG, 3), Document(Path(REV), REV, "drawings", "1", 3)]
    return _catalogue(pages, sheets, sorted(tags), documents)


def test_an_undated_later_revision_that_adds_a_unit_counts_the_added_unit(tmp_path):
    catalogue = _revision_job()
    d = build_dossier(catalogue, _reading(), tmp_path)
    assert "34" in _line("VAV", d).split("Tags:", 1)[1]
    assert d.counts["VAV"]["plan_placements"] >= 10


def test_guard_a_dated_later_revision_governs_and_its_added_unit_is_counted(tmp_path):
    catalogue = _revision_job()
    versions = [SheetVersion(f"M-10{n}", document, n, (), day, "title block") for n in (1, 2, 3)
                for document, day in ((DWG, date(2025, 2, 12)), (REV, date(2025, 2, 26)))]
    supersessions, _flags = supersede(catalogue, versions)
    assert {s.current.document for s in supersessions} == {REV}
    reading = _reading()
    reading.supersessions, reading.versions = tuple(supersessions), tuple(versions)
    assert build_dossier(catalogue, reading, tmp_path).counts["VAV"]["plan_placements"] == 10


def _two_buildings(b_title):
    """Building A (Mech.pdf) and building B (Second Building.pdf), LEVEL 1 to 3, the same unit tags VAV-n1 to n3 on
    each (a numbering restarted per building); B's titles are b_title."""
    pages, sheets = [], []
    for document, title in ((DWG, "BUILDING A LEVEL {n} PLAN"), (OTHER, b_title)):
        for n in (1, 2, 3):
            pages.append(_page(document, n, _lines(title.format(n=n), *_floor(n))))
            sheets.append(_sheet(n, f"M-10{n}", title.format(n=n), document))
    tags = [t for n in (1, 2, 3) for t in _floor(n)]
    return _catalogue(pages, sheets, tags, [_doc(DWG, 3), _doc(OTHER, 3)])


def test_plans_whose_titles_name_another_building_are_not_a_marked_up_copy(tmp_path):
    d = build_dossier(_two_buildings("BUILDING B LEVEL {n} PLAN"), _reading(), tmp_path)
    assert d.counts["VAV"]["plan_placements"] == 18


def test_guard_the_same_titles_and_units_are_read_once_and_the_note_gives_the_summed_count(tmp_path):
    d = build_dossier(_two_buildings("BUILDING A LEVEL {n} PLAN"), _reading(), tmp_path)
    assert d.counts["VAV"]["plan_placements"] == 9
    assert "read once, 9; if it is another building, 18" in _line("VAV", d)


_NOTES = ["GENERAL NOTES: COORDINATE ALL WORK WITH OTHER TRADES BEFORE INSTALLATION AND VERIFY EVERY DIMENSION IN",
          "THE FIELD. PROVIDE ACCESS PANELS WHERE CONCEALED EQUIPMENT REQUIRES SERVICE. ROUTE ALL PIPING PARALLEL",
          "WITH BUILDING LINES AND KEEP CLEAR OF LIGHT FIXTURES. SEAL EVERY PENETRATION THROUGH RATED WALLS WITH AN",
          "APPROVED SYSTEM. REFER TO THE SPECIFICATIONS FOR SUBMITTAL REQUIREMENTS, START UP AND OWNER TRAINING."] * 2
_REV1 = "Drawings/Rev 1/Mech.pdf"


def _type_labels_job(notes=()):
    """RD-4. Mech.pdf and Rev 1/Mech.pdf (the same issue): M-101 to 103, the same titles and the same unit tags
    VAV-n1 to n3; each Rev 1 sheet labels EBB-A (a type tag) 4 times, each Mech.pdf sheet twice."""
    pages, sheets = [], []
    for document, heaters in ((DWG, 2), (_REV1, 4)):
        for n in (1, 2, 3):
            pages.append(_page(document, n, _lines(f"LEVEL {n} PLAN", *_floor(n), *["EBB-A"] * heaters, *notes)))
            sheets.append(_sheet(n, f"M-10{n}", f"LEVEL {n} PLAN", document))
    tags = [t for n in (1, 2, 3) for t in _floor(n)] + ["EBB-A"]
    return _catalogue(pages, sheets, tags, [_doc(DWG, 3), _doc(_REV1, 3)])


def test_a_document_that_labels_a_type_more_often_is_never_a_marked_up_copy_of_the_other():
    """More places of a type are something the other set lacks: Rev 1 is no copy of Mech.pdf and the flag names
    EBB-A. Was: a copy, Mech.pdf read alone, EBB-A 6 instead of 12, "probably a marked-up copy" with no counts."""
    catalogue = _type_labels_job()
    [found] = document_repeats(catalogue)
    assert found.same is False and "EBB-A" in found.why
    assert placements(catalogue, ["EBB-A"])["EBB-A"].count >= 12


def test_of_two_documents_the_one_labelling_a_type_more_often_is_the_original_and_read():
    """The same sheets with the same long notes (the text test passes both ways): Mech.pdf shows nothing Rev 1 lacks,
    so Mech.pdf is Rev 1's copy, as a document showing fewer units is (test_final_n_counts), and Rev 1 is read: EBB-A
    12, never Mech.pdf's 6."""
    catalogue = _type_labels_job(_NOTES)
    [found] = document_repeats(catalogue)
    assert (found.copy, found.original, found.same) == (DWG, _REV1, True)
    assert placements(catalogue, ["EBB-A"])["EBB-A"].count >= 12


# ---- (1b) a typical sheet of another set ---------------------------------------------------------------------------

def test_a_typical_sheet_of_another_set_is_read_and_its_floors_counted(tmp_path):
    """Each building has LEVEL 1, a TYPICAL FLOOR PLAN M-102 for floors 2 to 4, and LEVEL 5, with its own units
    (A: VAV-1 to 3 on the typical sheet; B: VAV-4 to 6). B is another set (other units). B's typical sheet stands
    for 3 floors: 9 units that must be counted."""
    pages, sheets, tags = [], [], set()
    for document, typical in ((DWG, ["VAV-1", "VAV-2", "VAV-3"]), (OTHER, ["VAV-4", "VAV-5", "VAV-6"])):
        for n, title in ((1, "LEVEL 1 PLAN"), (2, "TYPICAL FLOOR PLAN"), (3, "LEVEL 5 PLAN")):
            units = typical if n == 2 else [f"{t}{n}" for t in typical]
            pages.append(_page(document, n, _lines(title, *units)))
            sheets.append(_sheet(n, f"M-10{n}", title, document))
            tags |= set(units)
    catalogue = _catalogue(pages, sheets, sorted(tags), [_doc(DWG, 3), _doc(OTHER, 3)])
    reading = _reading()
    reading.typicals = (SimpleNamespace(sheet="M-102", floors=("2", "3", "4")),)
    assert (OTHER, 2) in governing_pages(catalogue, (), ["M-102"])
    assert placements(catalogue, ["VAV-4"], reading.typicals)["VAV-4"].count == 3
    assert build_dossier(catalogue, reading, tmp_path).counts["VAV"]["plan_placements"] == 30


# ---- (2) the one label reader --------------------------------------------------------------------------------------

def test_tags_joined_by_a_slash_or_an_ampersand_and_a_bracketed_tag_are_labels():
    keys = label_keys(["FCU-4", "FCU-5", "VAV-3"])
    assert line_labels("FCU-4 / FCU-5", keys) == {"FCU-4": 1, "FCU-5": 1}
    assert line_labels("FCU-4 & FCU-5", keys) == {"FCU-4": 1, "FCU-5": 1}
    assert line_labels("(VAV-3)\n[VAV-3]\nVAV-3.", keys) == {"VAV-3": 3}


def test_a_family_whose_labels_carry_their_air_flow_keeps_its_counts_line(tmp_path):
    """f5394a9 gave 3. 1c45bed gives no VAV counts line at all."""
    pages = [_page(DWG, 1, _lines("VAV-1 450 CFM", "VAV-2 300 CFM", "VAV-3 600 CFM"))]
    catalogue = _catalogue(pages, [_sheet(1, "M-101", "LEVEL 1 PLAN")], ["VAV-1", "VAV-2", "VAV-3"])
    assert build_dossier(catalogue, _reading(), tmp_path).counts.get("VAV", {}).get("plan_placements") == 3


def test_a_second_floor_labelled_with_air_flows_still_counts_its_units(tmp_path):
    """VAV-1 to 3 on LEVEL 1 (tags alone) and on LEVEL 2 ("VAV-1 450 CFM"): two floors, 6 boxes, the numbering
    reused per floor, a schedule of the 3 tags. f5394a9 gave 6. 1c45bed gives 3."""
    units = ["VAV-1", "VAV-2", "VAV-3"]
    pages = [_page(DWG, 1, _lines(*units)), _page(DWG, 2, _lines(*(f"{t} 450 CFM" for t in units))),
             _page(DWG, 9, _lines("VAV SCHEDULE", *units))]
    sheets = [_sheet(1, "M-101", "LEVEL 1 PLAN"), _sheet(2, "M-102", "LEVEL 2 PLAN"),
              _sheet(9, "M-601", "SCHEDULES", types=("Schedules",))]
    d = build_dossier(_catalogue(pages, sheets, units), _reading([_schedule("VAV SCHEDULE", units, 9)]), tmp_path)
    # T-005a (estimator ruling 2 of 2026-10-11): a numbered unit tag is one unit in the job, so 3 as the schedule
    # says, the second floor's labels still read (each named as a duplicate with both numbers)
    assert d.counts["VAV"]["plan_placements"] == 3
    assert "VAV-1 is on 2 plans (M-101, M-102), counted once, 1" in next(
        line for line in d.text.splitlines() if "] VAV (" in line)


# 32 invented plan texts: the inventory's plan count and the dossier's plan placements agree on every one (F7 closed)
_U = ["VAV-1", "VAV-2", "VAV-3"]
_AGREE = [
    ([("LEVEL 1 PLAN", _lines(*_U))], _U, "VAV"),
    ([("LEVEL 1 PLAN", _lines("VAV-1 (TYP)", "VAV-2", "VAV-3"))], _U, "VAV"),
    ([("LEVEL 1 PLAN", _lines("VAV-1 450 CFM", "VAV-2 300 CFM", "VAV-3 600 CFM"))], _U, "VAV"),
    ([("LEVEL 1 PLAN", _lines("VAV-1", "450 CFM", "VAV-2", "300 CFM", "VAV-3", "600 CFM"))], _U, "VAV"),
    ([("LEVEL 1 PLAN", _lines("VAV-1 OFFICE 101", "VAV-2 CONF 102", "VAV-3 LOBBY"))], _U, "VAV"),
    ([("LEVEL 1 PLAN", _lines("(VAV-1)", "(VAV-2)", "(VAV-3)"))], _U, "VAV"),
    ([("LEVEL 1 PLAN", _lines("[VAV-1]", "[VAV-2]", "[VAV-3]"))], _U, "VAV"),
    ([("LEVEL 1 PLAN", _lines("VAV-1.", "VAV-2.", "VAV-3."))], _U, "VAV"),
    ([("LEVEL 1 PLAN", _lines("VAV-1 / VAV-2", "VAV-3"))], _U, "VAV"),
    ([("LEVEL 1 PLAN", _lines("VAV-1 & VAV-2", "VAV-3"))], _U, "VAV"),
    ([("LEVEL 1 PLAN", _lines("VAV-1, VAV-2", "VAV-3"))], _U, "VAV"),
    ([("LEVEL 1 PLAN", _lines("VAV", "1", "VAV", "2", "VAV", "3"))], _U, "VAV"),
    ([("LEVEL 1 PLAN", _lines("VAV-", "1", "VAV-", "2", "VAV-", "3"))], _U, "VAV"),
    ([("LEVEL 1 PLAN", _lines("VAV-1 THRU VAV-3"))], _U, "VAV"),
    ([("LEVEL 1 PLAN", _lines("VAV-1 ABOVE CLG", "VAV-2 ABOVE CLG", "VAV-3 ABOVE CLG"))], _U, "VAV"),
    ([("ROOF PLAN", _lines("AHU-1 SUPPLY", "AHU-2 SUPPLY"))], ["AHU-1", "AHU-2"], "AHU"),
    ([("ROOF PLAN", _lines("EF-1 EXHAUST", "EF-2 EXHAUST"))], ["EF-1", "EF-2"], "EF"),
    ([("ROOF PLAN", _lines("EF-1 ON ROOF", "EF-2 ON ROOF"))], ["EF-1", "EF-2"], "EF"),
    ([("LEVEL 1 PLAN", _lines("TO VAV-1", "TO VAV-2", "TO VAV-3"))], _U, "VAV"),
    ([("LEVEL 1 PLAN", _lines("VAV-1", "TO VAV-1", "VAV-2", "VAV-3"))], _U, "VAV"),
    ([("LEVEL 1 PLAN", _lines("CUH-A (TYP. OF 4)"))], ["CUH-A"], "CUH"),
    ([("LEVEL 1 PLAN", _lines("CUH-A", "CUH-A", "CUH-A", "CUH-A"))], ["CUH-A"], "CUH"),
    ([("LEVEL 1 PLAN", _lines("CUH-A ENTRY", "CUH-A STAIR", "CUH-A VEST", "CUH-A CORR"))], ["CUH-A"], "CUH"),
    ([("LEVEL 1 PLAN", _lines("(N) VAV-1", "(E) VAV-2", "VAV-3 (EXISTING)"))], _U, "VAV"),
    ([("LEVEL 1 PLAN", _lines(*_U)), ("LEVEL 2 PLAN", _lines(*_U))], _U, "VAV"),
    ([("HVAC DUCTWORK FIRST FLOOR PLAN", _lines(*_U)), ("HVAC PIPING FIRST FLOOR PLAN", _lines(*_U))], _U, "VAV"),
    ([("HVAC DUCTWORK FIRST FLOOR PLAN", _lines(*_U)),
      ("HVAC PIPING FIRST FLOOR PLAN", _lines("VAV-1", "TO VAV-2", "TO VAV-3"))], _U, "VAV"),
    ([("HVAC DUCTWORK FIRST FLOOR PLAN", _lines(*_U)),
      ("HVAC PIPING FIRST FLOOR PLAN", _lines("VAV-1 HW", "VAV-2 HW", "VAV-3 HW"))], _U, "VAV"),
    ([("LEVEL 1 PLAN", _lines(*_U)), ("LEVEL 2 PLAN", _lines("VAV-1 450 CFM", "VAV-2 450 CFM", "VAV-3 450 CFM"))],
     _U, "VAV"),
    ([("LEVEL 1 PLAN", "FCU-1 / FCU-2"), ("LEVEL 2 PLAN", "FCU-1 / FCU-2")], ["FCU-1", "FCU-2"], "FCU"),
    ([("LEVEL 1 PLAN", _lines("VAV-1 SA", "VAV-2 SA", "VAV-3 SA"))], _U, "VAV"),
    ([("LEVEL 1 PLAN", _lines("VAV-1 x2", "VAV-2", "VAV-3"))], _U, "VAV"),
]


@pytest.mark.parametrize("plans, tags, family", _AGREE)
def test_guard_the_inventory_and_the_dossier_agree_on_every_plan_text(tmp_path, plans, tags, family):
    pages = [_page(DWG, n + 1, text) for n, (_title, text) in enumerate(plans)]
    sheets = [_sheet(n + 1, f"M-10{n + 1}", title) for n, (title, _text) in enumerate(plans)]
    catalogue = _catalogue(pages, sheets, tags)
    inventory = sum(p.count for tag, p in placements(catalogue, tags).items() if tag.startswith(family))
    dossier = build_dossier(catalogue, _reading(), tmp_path).counts.get(family, {}).get("plan_placements", 0)
    assert inventory == dossier


# ---- (3) F6 edge: pages 1 and 3 alike, page 2 other ----------------------------------------------------------------

def test_one_number_on_three_pages_where_only_two_are_alike_counts_every_page(tmp_path):
    """M-101 on pages 1, 2 and 3 of one document: pages 1 and 3 show VAV-1 to 3 (the same text), page 2 shows VAV-4 to
    7. When every page is alike the number is 3 floors (9). Here the alike pages must not count less: 10, and the
    units read the same pages as the devices (3 thermostats, one per page)."""
    first, second = _lines("VAV-1", "VAV-2", "VAV-3"), _lines("VAV-4", "VAV-5", "VAV-6", "VAV-7")
    pages = [_page(DWG, 1, first), _page(DWG, 2, second), _page(DWG, 3, first)]
    sheets = [_sheet(n, "M-101", "FLOOR PLAN") for n in (1, 2, 3)]
    catalogue = _catalogue(pages, sheets, [f"VAV-{n}" for n in range(1, 8)])
    reading = _reading()
    reading.devices = tuple(DeviceCount("M-101", DWG, n, "Thermostat", "T", 1, 1, 1, True) for n in (1, 2, 3))
    d = build_dossier(catalogue, reading, tmp_path)
    assert d.device_totals["T"] == 3
    assert d.counts["VAV"]["plan_placements"] == 7           # T-005a ruling 2: VAV-1 to 3 once in the job (was 10)
