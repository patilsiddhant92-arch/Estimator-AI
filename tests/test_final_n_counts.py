"""FINAL-N: REVIEW-FINAL7 F1 to F7, the lead's own tests beside the reviewer's (tests/test_review_final7_counts.py).
Lead ruling: an undercount is the worst failure; a count is reduced or text dropped only where it is provably safe,
otherwise the sheets are summed and the estimator told. Each test fails on rebuild 1c45bed. Invented fixtures only
(job 26-9999, invented sheets and tags)."""
import inspect
from pathlib import Path

from estimator.catalogue.documents import Document
from estimator.catalogue.job import document_repeats, repeats
from estimator.catalogue.tags import TagEntry, label_keys, line_labels
from estimator.reading.inventory import placements, plan_groups
from estimator.reading.revisions import governing_pages, sheet_versions, supersede
from estimator.writing.dossier import build_dossier
from test_dossier_plan_areas import DWG, OTHER, _catalogue, _doc, _line, _page, _reading, _sheet

REV = "Drawings/Mech Rev 1.pdf"


def _lines(*tags):
    return "\n".join(tags)


def _floor(n):
    return [f"VAV-{n}{k}" for k in (1, 2, 3)]


def _keys(*tags):
    return label_keys(tags)


# ---- F4: the label reader, each rule only raising a count ----------------------------------------------------------

def test_a_thru_range_counts_both_ends_and_each_listed_member_between():
    """The rule: "VAV-1 THRU VAV-5" is a label of each end and of each numbered tag between that the job lists (a
    range never invents a tag); "VAV-1 THRU 3" reads its bare high end too; a span over RANGE_SPAN and a range
    after a reference word ("SEE VAV-1 THRU VAV-5") place no member."""
    keys = _keys(*(f"VAV-{n}" for n in range(1, 6)))
    assert line_labels("VAV-1 THRU VAV-5", keys) == dict.fromkeys((f"VAV-{n}" for n in range(1, 6)), 1)
    assert line_labels("VAV-1 THROUGH 3", keys) == {"VAV-1": 1, "VAV-2": 1, "VAV-3": 1}
    assert line_labels("VAV-1 THRU VAV-5", _keys("VAV-1", "VAV-5")) == {"VAV-1": 1, "VAV-5": 1}
    assert line_labels("VAV-1 THRU VAV-900", _keys("VAV-1", "VAV-2", "VAV-900")) == {"VAV-1": 1, "VAV-900": 1}
    assert line_labels("SEE VAV-1 THRU VAV-5", keys) == {}


def test_a_tag_split_over_two_lines_is_one_label_and_the_next_lines_own_label_is_kept():
    keys = _keys("VAV-3", "VAV-4")
    assert line_labels("VAV-\n3", keys) == {"VAV-3": 1}
    assert line_labels("VAV-\n3 VAV-4", keys) == {"VAV-3": 1, "VAV-4": 1}
    assert line_labels("SUPPLY AIR -\nVAV-4", keys) == {"VAV-4": 1}     # a dash ending a note takes nothing away


def test_a_tag_after_a_reference_word_is_no_label_and_a_long_note_is_none():
    keys = _keys("AHU-1", "VAV-3", "VAV-4")
    assert line_labels("AHU-1 SUPPLY TO VAV-3", keys) == {"AHU-1": 1}
    assert line_labels("VAV-3 SERVED BY AHU-1", keys) == {"VAV-3": 1}
    assert line_labels("VAV-3 450 CFM VAV-4 300 CFM", keys) == {"VAV-3": 1, "VAV-4": 1}
    assert line_labels("VAV 3 450 CFM\n2-VAV-4", keys) == {"VAV-3": 1, "VAV-4": 1}
    note = "VAV-3 SHALL BE RELOCATED BY THE CONTRACTOR TO SUIT THE NEW CEILING GRID LAYOUT SHOWN ON ARCHITECTURAL"
    assert line_labels(note, keys) == {}


def test_a_unit_named_only_in_notes_on_a_plan_counts_once_on_both_sides_and_a_type_never(tmp_path):
    """The backstop (REVIEW-FINAL7 F4 step 3): a unit's tag a counted plan names anywhere counts at least once; a
    type's tag counts only where labelled (its places are its count)."""
    from estimator.catalogue.tags import plan_labels
    keys = _keys("VAV-3", "CUH-A")
    assert plan_labels("TO VAV-3\nSEE VAV-3\nINSTALL CUH-A", keys) == {"VAV-3": 1}
    pages = [_page(DWG, 1, _lines("TO VAV-1", "TO VAV-2", "FROM VAV-3"))]
    catalogue = _catalogue(pages, [_sheet(1, "M-101", "LEVEL 1 PLAN")], ["VAV-1", "VAV-2", "VAV-3"])
    assert {t: p.count for t, p in placements(catalogue, ["VAV-1", "VAV-2", "VAV-3"]).items()} == {
        "VAV-1": 1, "VAV-2": 1, "VAV-3": 1}
    assert build_dossier(catalogue, _reading(), tmp_path).counts["VAV"]["plan_placements"] == 3


def test_the_backstop_never_joins_two_plans_into_one_group_and_the_sum_is_said(tmp_path):
    """A ductwork plan labels VAV-1 to 3; its piping plan labels VAV-1 and names VAV-2 and 3 in notes. The labels
    alone are the plan groups' evidence, so the backstop's names never make the two one plan: summed (each named
    unit once on each plan, 6; 1c45bed 4), and the counts line names the tags counted on each plan. (The titles name
    one trade: ruling L1 would make a ductwork plan and a piping plan of one floor one plan outright, and this test is
    about the tag evidence.)"""
    pages = [_page(DWG, 1, _lines("VAV-1", "VAV-2", "VAV-3")), _page(DWG, 2, _lines("VAV-1", "TO VAV-2", "TO VAV-3"))]
    sheets = [_sheet(1, "M-101", "HVAC FIRST FLOOR PLAN"), _sheet(2, "M-201", "HVAC FIRST FLOOR PLAN")]
    d = build_dossier(_catalogue(pages, sheets, ["VAV-1", "VAV-2", "VAV-3"]), _reading(), tmp_path)
    assert d.counts["VAV"]["plan_placements"] == 6
    assert "VAV-2 is on 2 plans" in _line("VAV", d) and "counted on each" in _line("VAV", d)


# ---- F1 / F2 / F5: the copy test -----------------------------------------------------------------------------------

def _pair(b_document=OTHER, b_revision="base", b_text=None, b_title="LEVEL {n} PLAN", a_text=None):
    pages, sheets, tags = [], [], set()
    for document, text, title in ((DWG, a_text, "LEVEL {n} PLAN"), (b_document, b_text, b_title)):
        for n in (1, 2, 3):
            units = _floor(n)
            pages.append(_page(document, n, text(n, *units) if text else _lines(f"LEVEL {n} PLAN", *units)))
            sheets.append(_sheet(n, f"M-10{n}", title.format(n=n), document))
            tags |= set(units)
    documents = [_doc(DWG, 3), Document(Path(b_document), b_document, "drawings", b_revision, 3)]
    return _catalogue(pages, sheets, sorted(tags), documents)


def test_two_documents_of_other_revision_labels_are_never_copy_and_original():
    assert document_repeats(_pair(REV, "1")) == []
    assert [r.same for r in document_repeats(_pair())] == [True]          # the same issue: a marked-up copy


def test_a_document_whose_text_is_not_the_originals_is_another_set_and_the_flag_says_why():
    """The same units and titles, but each document's general notes are not on the other: neither is a marked-up
    copy (a copy keeps its original's text and adds to it)."""
    a = " ".join(f"NOTE {k} PROVIDE CONTROL WIRING AND CONDUIT PER SPECIFICATION SECTION 230900" for k in range(9))
    b = " ".join(f"KEYED NOTE {k} EXISTING DAMPER ACTUATOR TO REMAIN REUSE WHERE ABLE" for k in range(9))
    catalogue = _pair(a_text=lambda n, *units: _lines(f"LEVEL {n} PLAN", a, *units),
                      b_text=lambda n, *units: _lines(f"LEVEL {n} PLAN", b, *units))
    [found] = document_repeats(catalogue)
    assert not found.same and found.why == "not their text"
    assert any("not their text" in line and "counted" in line for line in repeats(catalogue)[0])


def test_plans_titled_for_another_building_give_the_reason_in_the_flag():
    catalogue = _pair(b_title="BUILDING B LEVEL {n} PLAN")
    assert any("but not their plan titles — read as another set" in line for line in repeats(catalogue)[0])


def test_of_two_documents_the_one_showing_more_units_is_the_original_and_read(tmp_path):
    """Second Building.pdf is Mech.pdf plus one box (VAV-34 on LEVEL 3) and has the more text, so the copy rule by
    text alone made Mech.pdf the original and lost VAV-34. The superset is the original: Mech.pdf is its copy."""
    def b_text(n, *units):
        return _lines(f"LEVEL {n} PLAN", *units, *(["VAV-34"] if n == 3 else []))
    notes = " ".join(f"GENERAL NOTE {k}" for k in range(12))
    catalogue = _pair(b_text=lambda n, *u: _lines(notes, b_text(n, *u)),
                      a_text=lambda n, *u: _lines(notes, f"LEVEL {n} PLAN", *u))
    tags = sorted({t for n in (1, 2, 3) for t in _floor(n)} | {"VAV-34"})
    catalogue.tags = tuple(TagEntry(t, "", (), ("M-101",), 2) for t in tags)
    [found] = document_repeats(catalogue)
    assert (found.copy, found.original, found.same) == (DWG, OTHER, True)
    assert placements(catalogue, ["VAV-34"])["VAV-34"].count == 1


# ---- F2: versions nothing orders are summed and said ---------------------------------------------------------------

def test_two_versions_nothing_orders_are_both_read_and_the_flag_says_summed():
    def text(n, *units):
        return _lines(f"LEVEL {n} PLAN", *units, *(["VAV-34"] if n == 3 else []))
    catalogue = _pair(REV, "1", b_text=text)
    _supersessions, flags = supersede(catalogue, sheet_versions(catalogue))
    assert any(f.startswith("Sheet M-103 ") and "counted from Mech.pdf and Mech Rev 1.pdf, summed, for now" in f
               for f in flags)
    governing = governing_pages(catalogue)
    assert {(DWG, 3), (REV, 3), (DWG, 1)} <= governing and (REV, 1) not in governing


# ---- F7: one number on several pages ------------------------------------------------------------------------------

def test_two_pages_of_one_sheet_number_are_never_one_plan_group():
    tally = {"VAV-1": 1, "VAV-2": 1, "VAV-3": 1}
    plans = [(_sheet(1, "M-101", "FLOOR PLAN"), tally), (_sheet(3, "M-101", "FLOOR PLAN"), tally)]
    assert plan_groups(plans) == {(DWG, 1): ((DWG, 1),), (DWG, 3): ((DWG, 3),)}


# ---- low: hygiene ---------------------------------------------------------------------------------------------------

def test_the_decimal_type_is_public_and_the_dossiers_pages_are_not_rebound():
    import estimator.reading.inventory as inventory
    import estimator.writing.dossier as dossier
    from estimator.catalogue.tags import DECIMAL_TYPE
    assert DECIMAL_TYPE.match("AC-3.0")
    assert "_DECIMAL_TYPE" not in inspect.getsource(inventory)
    assert "counted" not in inspect.signature(dossier._counts).parameters
