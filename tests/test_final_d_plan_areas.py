"""FINAL-D F1: plan sheets are one plan only when the evidence is clear (lead ruling: an undercount is far worse
than an overcount, so the higher count wins when it cannot be told). Two sheets are one plan when their titles
name the same readable floor (in words or figures) and the same part, and they are in one document or repeat each
other's unit tags; a sheet whose title names no readable floor joins only a sheet of the same document with the
same title text. Sheets that may show one plan but are not proven so are counted apart and the counts line says
so. Invented fixtures only."""
from collections import Counter

from estimator.writing.dossier import build_dossier, plan_areas
from test_dossier_plan_areas import CTL, DWG, _catalogue, _doc, _line, _page, _reading, _sheet

UNITS = {"VAV-1", "VAV-2", "VAV-3"}


def _areas(*titles, tags=UNITS, documents=None):
    documents = documents or [DWG] * len(titles)
    sheets = [_sheet(n, f"M-{100 + n}", title, document)
              for n, (title, document) in enumerate(zip(titles, documents), start=1)]
    found = plan_areas([(sheet, tags) for sheet in sheets])
    return [found[(s.document, s.page)] for s in sheets]


ONE_FLOOR = [
    ("HVAC LEVEL ONE PLAN", "CONTROLS FIRST FLOOR PLAN"),
    ("HVAC 1ST FLR PLAN", "CONTROLS FIRST FLOOR PLAN"),
    ("HVAC L2 PLAN", "CONTROLS LEVEL 2 PLAN"),
    ("HVAC LEVEL TWO PLAN", "CONTROLS SECOND LEVEL PLAN"),
    ("HVAC GROUND FLOOR PLAN", "CONTROLS GROUND LEVEL PLAN"),
    ("HVAC LOWER LEVEL PLAN", "CONTROLS LOWER LEVEL PLAN"),
    ("HVAC ROOF PLAN", "CONTROLS ROOF PLAN"),
    ("FIRST FLOOR PLAN - TOWER ONE", "CONTROLS FIRST FLOOR PLAN - TOWER 1"),
    ("HVAC FIRST FLOOR PLAN TOWER 2", "CONTROLS FIRST FLOOR PLAN - TOWER TWO"),
    ("HVAC TOWER 2 FIRST FLOOR PLAN", "CONTROLS TOWER 2 FIRST FLOOR PLAN"),
]


def test_one_floor_named_in_words_or_figures_is_one_plan():
    """The titles alone say so (no tags repeated): one document, one floor, one part."""
    for one, other in ONE_FLOOR:
        a, b = _areas(one, other, tags=set())
        assert a == b, (one, other)


DIFFERENT = [
    ("LEVEL ONE MECHANICAL PLAN", "LEVEL TWO MECHANICAL PLAN"),
    ("1ST FLR MECHANICAL PLAN", "2ND FLR MECHANICAL PLAN"),
    ("GROUND FLOOR PLAN", "FIRST FLOOR PLAN"),
    ("FIRST FLOOR PLAN - DORM WING", "FIRST FLOOR PLAN - CLASSROOM WING"),
    ("FIRST FLOOR PLAN - TOWER 1", "FIRST FLOOR PLAN - TOWER 2"),
    ("FIRST FLOOR PLAN - UNIT 1A", "FIRST FLOOR PLAN - UNIT 1B"),
    ("FIRST FLOOR PLAN - BUILDING A", "FIRST FLOOR PLAN - BUILDING B"),
    ("FIRST FLOOR PLAN - NORTH", "FIRST FLOOR PLAN - SOUTH"),
    ("FIRST FLOOR PLAN - EAST", "FIRST FLOOR PLAN - WEST"),
    ("FIRST FLOOR PLAN - ANNEX", "FIRST FLOOR PLAN"),
    ("LOWER ROOF PLAN", "UPPER ROOF PLAN"),
    ("HIGH ROOF PLAN", "LOW ROOF PLAN"),
    ("FIRST AND SECOND FLOOR PLAN", "SECOND FLOOR PLAN"),
    ("LEVELS 2 THRU 5 PLAN", "LEVEL 2 PLAN"),
    # a word before the part word keeps the part's number (no dash before TOWER)
    ("FIRST FLOOR PLAN TOWER 1", "FIRST FLOOR PLAN TOWER 2"),
    ("HVAC TOWER 1 FIRST FLOOR PLAN", "HVAC TOWER 2 FIRST FLOOR PLAN"),
    ("EAST WING 1 FIRST FLOOR PLAN", "EAST WING 2 FIRST FLOOR PLAN"),
    ("RESIDENCE TOWER A FIRST FLOOR PLAN", "RESIDENCE TOWER B FIRST FLOOR PLAN"),
]


def test_two_different_floors_or_parts_are_never_one_plan():
    """Even when both sheets repeat the same tags (a typical floor of a dorm or a tower)."""
    for one, other in DIFFERENT:
        a, b = _areas(one, other)
        assert a != b, (one, other)


def test_sheets_naming_no_floor_are_one_plan_only_with_the_same_title_in_one_document():
    assert len(set(_areas("MECHANICAL PLAN - DORM WING", "MECHANICAL PLAN - CLASSROOM WING"))) == 2
    assert len(set(_areas("ENLARGED MECHANICAL ROOM PLAN", "HVAC FIRST FLOOR PLAN"))) == 2
    a, b = _areas("MECHANICAL PLAN", "MECHANICAL  PLAN")                   # one title, one document: one plan
    assert a == b
    assert len(set(_areas("MECHANICAL PLAN", "MECHANICAL PLAN", documents=[DWG, CTL]))) == 2
    assert len(set(_areas("MECHANICAL PLAN", "MECHANICAL PLAN", tags=set()))) == 2   # no tags repeated


def test_a_title_holding_its_own_sheet_number_compares_without_it():
    sheets = [_sheet(1, "M-301", "M-301 MECHANICAL PLAN"), _sheet(2, "M-302", "M-302 MECHANICAL PLAN")]
    found = plan_areas([(s, UNITS) for s in sheets])
    assert found[(DWG, 1)] == found[(DWG, 2)]
    sheets[1] = _sheet(2, "M-302", "M-302 PIPING PLAN")                     # another title: not proven one plan
    found = plan_areas([(s, UNITS) for s in sheets])
    assert found[(DWG, 1)] != found[(DWG, 2)]


def test_an_enlarged_plan_repeating_a_floors_tags_is_counted_apart_and_the_line_says_so(tmp_path):
    """Cannot tell: the enlarged plan names no floor, so it is not proven to be the first floor drawn again; both
    are counted (the higher count) and the counts line names the two sheets for the estimator."""
    pages = [_page(DWG, 1, "VAV-1\nVAV-2\nVAV-3\nVAV-4"), _page(DWG, 2, "VAV-1\nVAV-2\nVAV-3")]
    sheets = [_sheet(1, "M-101", "HVAC FIRST FLOOR PLAN"), _sheet(2, "M-301", "ENLARGED MECHANICAL ROOM PLAN")]
    d = build_dossier(_catalogue(pages, sheets, [f"VAV-{n}" for n in range(1, 5)]), _reading(), tmp_path)
    assert d.counts["VAV"]["plan_placements"] == 4 + 3
    line = _line("VAV", d)
    assert "same plan as" not in line
    assert "M-101 and M-301 may show one plan" in line and "both are counted" in line
    # the flag never holds a client cause's words (bms.render reads them after the line's head)
    (flag,) = [note for note in line.split("; ") if "may show one plan" in note]
    for words in ("same plan as", "a typical unit at each place", "one unit's tag on several plans",
                  "one unit labelled more than once"):
        assert words not in flag
    # two floors the titles name apart are known to be two plans: no flag
    pages = [_page(DWG, 1, "VAV-1\nVAV-2\nVAV-3"), _page(DWG, 2, "VAV-1\nVAV-2\nVAV-3")]
    sheets = [_sheet(1, "M-101", "HVAC FIRST FLOOR PLAN"), _sheet(2, "M-102", "HVAC SECOND FLOOR PLAN")]
    d = build_dossier(_catalogue(pages, sheets, sorted(UNITS)), _reading(), tmp_path)
    assert d.counts["VAV"]["plan_placements"] == 6
    assert "may show one plan" not in _line("VAV", d)


def test_the_same_floor_in_two_documents_on_typical_type_tags_alone_is_counted_apart_and_flagged(tmp_path):
    """Two documents each with a first floor plan showing the same type tags, each at several places: those tags
    prove nothing (a typical unit is at each place on every floor of every building), so the plans add up, and the
    line names them as maybe one plan."""
    documents = [_doc(DWG, 1), _doc(CTL, 1)]
    text = "EBB-A\nEBB-A\nEBB-A\nEBB-B\nEBB-B\nEBB-C\nEBB-C"
    pages = [_page(DWG, 1, text), _page(CTL, 1, text)]
    sheets = [_sheet(1, "M-101", "HVAC FIRST FLOOR PLAN"), _sheet(1, "C-101", "CONTROLS FIRST FLOOR PLAN", CTL)]
    d = build_dossier(_catalogue(pages, sheets, ["EBB-A", "EBB-B", "EBB-C"], documents), _reading(), tmp_path)
    assert d.counts["EBB"]["plan_placements"] == 14
    assert "M-101 and C-101 may show one plan" in _line("EBB", d)
    # plan_areas itself: tag -> places; unit tags (once on each sheet) still prove one plan
    sheets = [_sheet(1, "M-101", "HVAC FIRST FLOOR PLAN"), _sheet(1, "C-101", "CONTROLS FIRST FLOOR PLAN", CTL)]
    found = plan_areas([(s, Counter({"EBB-A": 4, "EBB-B": 2, "EBB-C": 2})) for s in sheets])
    assert found[(DWG, 1)] != found[(CTL, 1)]
    found = plan_areas([(s, Counter({"VAV-1": 1, "VAV-2": 1, "VAV-3": 1, "EBB-A": 4})) for s in sheets])
    assert found[(DWG, 1)] == found[(CTL, 1)]
