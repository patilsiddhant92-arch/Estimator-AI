"""FINAL-O (REVIEW-FINAL8 H1 to H4): every reduction provably safe, otherwise summed and said.

H1: a reissue supersedes only the base sheet it is a version of: the same sheet number AND the same plan title
(trade and plan words and the number taken out). A same-numbered sheet of another document with another title is
another sheet, kept and read; two candidates the titles cannot tell apart are all kept, summed and flagged.
H2: a reissue with fewer pages than its base replaces only the pages its text matches best; the rest are kept and
flagged. H4: typical sheets, floor multipliers and the alike-pages set-aside are keyed by (document, sheet number).
H3: a stated multiplier after a tag ("CUH-A (TYP. OF 4)", "x4", "(4)", "4 PLACES") is that many places.

Invented fixtures only (job 26-9999, invented sheets and tags); no job is run."""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest

from estimator.catalogue.documents import Document
from estimator.catalogue.overview import SpecOverview
from estimator.catalogue.register import PageRecord
from estimator.catalogue.sheet_types import Sheet
from estimator.catalogue.tags import TagEntry, label_keys, line_labels
from estimator.reading.devices import typical_sheets
from estimator.reading.inventory import placements, plan_floors
from estimator.reading.revisions import governing_pages, sheet_versions, supersede
from estimator.writing.dossier import build_dossier
from test_dossier_plan_areas import _reading
from test_revisions import _table

MECH = "Drawings/Mech.pdf"
SECOND = "Drawings/Second Building.pdf"
ADDENDUM = "Addendum/Mech Addendum 1.pdf"
EARLY = _table(("3", "ISSUED FOR BID", "02/12/25"))
MIDDLE = _table(("4", "ADDENDUM #1", "02/26/25"), ("3", "ISSUED FOR BID", "02/12/25"))
LATE = _table(("5", "ADDENDUM #2", "03/10/25"), ("4", "ADDENDUM #1", "02/26/25"), ("3", "ISSUED FOR BID", "02/12/25"))
_TAG = re.compile(r"\b[A-Z]{2,4}-[0-9A-Z]+\b")


def _job(pages, kinds=None, revisions=None):
    """pages: (document, page, sheet number, title, tags or text lines, title-block spans)."""
    kinds, revisions = kinds or {}, revisions or {}
    relatives = list(dict.fromkeys(p[0] for p in pages))
    documents = tuple(Document(Path(r), r, kinds.get(r, "drawings"), revisions.get(r, "base"),
                               max(p[1] for p in pages if p[0] == r)) for r in relatives)
    records, sheets = [], []
    for document, page, number, title, lines, spans in pages:
        records.append(PageRecord(document, page, "text", "\n".join([title, *lines]), 0, True, spans))
        sheets.append(Sheet(document, page, number, title, "Mechanical", ("Plans",)))
    tags = sorted({t for r in records for t in _TAG.findall(r.text)})
    job = SimpleNamespace(name="26-9999", root=Path("."), documents=documents)
    return SimpleNamespace(job=job, pages=tuple(records), sheets=tuple(sheets), sections=(),
                           tags=tuple(TagEntry(t, "", (), ("M-101",), 2) for t in tags), overview=SpecOverview(),
                           bid=None, flags=())


def _read(catalogue, tmp_path):
    """Both sides on the production path, as `read_job` reads them."""
    supersessions, flags = supersede(catalogue, sheet_versions(catalogue))
    typicals = typical_sheets(catalogue)
    reading = _reading()
    reading.supersessions, reading.typicals = tuple(supersessions), tuple(typicals)
    pages = governing_pages(catalogue, supersessions, [(t.document, t.sheet) for t in typicals])
    tags = [t.tag for t in catalogue.tags]
    inventory: Counter = Counter()
    for tag, p in placements(catalogue, tags, typicals, pages).items():
        inventory[tag.split("-")[0]] += p.count
    d = build_dossier(catalogue, reading, tmp_path)
    dossier = {f: (c or {}).get("plan_placements", 0) for f, c in d.counts.items()}
    lines = {f: next((line for line in d.text.splitlines() if f"] {f} (" in line), "") for f in d.counts}
    return inventory, dossier, flags, supersessions, lines


def _same(inventory, dossier, **expected):
    for family, n in expected.items():
        assert (family, inventory[family], dossier.get(family, 0)) == (family, n, n)


# ---- H1: a reissue supersedes only the sheet whose title it shares --------------------------------------------------

def test_an_addendum_supersedes_only_the_base_sheet_whose_title_it_shares(tmp_path):
    catalogue = _job([(MECH, 1, "M-101", "BUILDING A HVAC LEVEL 1 PLAN", ["VAV-11", "VAV-12", "AHU-1"], ()),
                      (SECOND, 1, "M-101", "BUILDING B HVAC LEVEL 1 PLAN", ["VAV-21", "VAV-22", "AHU-2"], ()),
                      (ADDENDUM, 1, "M-101", "M-101 BUILDING A HVAC LEVEL 1 PLAN",
                       ["VAV-11", "VAV-12", "AHU-1", "VAV-18"], ())], kinds={ADDENDUM: "addendum"})
    inventory, dossier, flags, supersessions, _lines = _read(catalogue, tmp_path)
    [s] = supersessions
    assert s.current.document == ADDENDUM and [(v.document, v.page) for v in s.replaced] == [(MECH, 1)]
    assert flags == []
    _same(inventory, dossier, VAV=5, AHU=2)


def test_a_dated_reissue_supersedes_its_own_chain_and_never_another_buildings_sheet(tmp_path):
    """Rev 2 lists every issue of Rev 1 and of the base (a chain of one sheet's issues): it replaces both. Building B's
    M-101, of another title, is another sheet: kept and read."""
    rev1, rev2 = "Drawings/Mech Rev 1.pdf", "Drawings/Mech Rev 2.pdf"
    title = "BUILDING A HVAC LEVEL 1 PLAN"
    catalogue = _job([(MECH, 1, "M-101", title, ["VAV-11", "VAV-12"], EARLY),
                      (rev1, 1, "M-101", title, ["VAV-11", "VAV-12", "VAV-13"], MIDDLE),
                      (SECOND, 1, "M-101", "BUILDING B HVAC LEVEL 1 PLAN", ["VAV-21", "VAV-22"], EARLY),
                      (rev2, 1, "M-101", title, ["VAV-11", "VAV-12", "VAV-13", "VAV-14"], LATE)],
                     revisions={rev1: "1", rev2: "2"})
    inventory, dossier, flags, supersessions, _lines = _read(catalogue, tmp_path)
    [s] = supersessions
    assert s.current.document == rev2 and sorted(v.document for v in s.replaced) == sorted([MECH, rev1])
    assert flags == []
    _same(inventory, dossier, VAV=6)


def test_two_base_sheets_the_titles_cannot_tell_apart_are_both_kept_summed_and_flagged(tmp_path):
    catalogue = _job([(MECH, 1, "M-101", "HVAC LEVEL 1 PLAN", ["VAV-11", "VAV-12"], ()),
                      (SECOND, 1, "M-101", "HVAC LEVEL 1 PLAN", ["VAV-21", "VAV-22"], ()),
                      (ADDENDUM, 1, "M-101", "HVAC LEVEL 1 PLAN", ["VAV-11", "VAV-12", "VAV-18"], ())],
                     kinds={ADDENDUM: "addendum"})
    inventory, dossier, flags, supersessions, _lines = _read(catalogue, tmp_path)
    assert supersessions == []
    assert flags == ["addendum M-101 may replace one of two M-101 sheets (Mech.pdf, Second Building.pdf): "
                     "both counted; check"]
    _same(inventory, dossier, VAV=7)            # 3 + 2 + 2: summed, never below the 5 distinct tags


def test_a_reissue_whose_title_matches_no_base_sheet_replaces_nothing_and_says_so(tmp_path):
    catalogue = _job([(MECH, 1, "M-101", "HVAC LEVEL 1 PLAN", ["VAV-11", "VAV-12"], ()),
                      (ADDENDUM, 1, "M-101", "HVAC LEVEL 1 EAST PLAN", ["VAV-11", "VAV-18"], ())],
                     kinds={ADDENDUM: "addendum"})
    inventory, dossier, flags, supersessions, _lines = _read(catalogue, tmp_path)
    assert supersessions == []
    assert flags == ["addendum M-101 has another title than every other M-101 (Mech.pdf): both counted; check"]
    _same(inventory, dossier, VAV=4)


def test_an_addendum_to_one_of_two_sets_of_the_same_numbers_never_replaces_the_other_by_elimination(tmp_path):
    """Two buildings issued with the same numbers and titles (`other_sets`: Mech.pdf, with the more text, is read as
    another set beside Second Building.pdf). An addendum reissues M-101: it may be either building's, so both are
    kept, summed and flagged; never Second Building's replaced because Mech.pdf's was set aside as another set."""
    pages = []
    for n in (1, 2, 3):
        pages.append((MECH, n, f"M-10{n}", f"HVAC LEVEL {n} PLAN", [f"VAV-1{n}1", f"VAV-1{n}2", "SEE NOTE 4"], ()))
        pages.append((SECOND, n, f"M-10{n}", f"HVAC LEVEL {n} PLAN", [f"VAV-2{n}1", f"VAV-2{n}2"], ()))
    pages.append((ADDENDUM, 1, "M-101", "HVAC LEVEL 1 PLAN", ["VAV-111", "VAV-112", "VAV-118"], ()))
    catalogue = _job(pages, kinds={ADDENDUM: "addendum"})
    inventory, dossier, flags, supersessions, _lines = _read(catalogue, tmp_path)
    assert supersessions == []
    assert flags == ["addendum M-101 may replace one of two M-101 sheets (Mech.pdf, Second Building.pdf): "
                     "both counted; check"]
    _same(inventory, dossier, VAV=15)           # 3 + 2 + 2 on M-101, 4 + 4 on M-102 and M-103


# ---- H2: a reissue with fewer pages replaces only the pages it matches -----------------------------------------------

def test_a_one_page_reissue_of_a_two_page_number_keeps_the_page_it_does_not_match(tmp_path):
    base = [(MECH, 1, "M-101", "HVAC LEVEL 1 PLAN", ["VAV-11", "VAV-12"], ()),
            (MECH, 2, "M-101", "HVAC LEVEL 1 PLAN", ["VAV-15", "VAV-16"], ())]
    catalogue = _job(base + [(ADDENDUM, 1, "M-101", "HVAC LEVEL 1 PLAN", ["VAV-11", "VAV-12", "VAV-18"], ())],
                     kinds={ADDENDUM: "addendum"})
    inventory, dossier, flags, supersessions, _lines = _read(catalogue, tmp_path)
    [s] = supersessions
    assert [(v.document, v.page) for v in s.replaced] == [(MECH, 1)]
    assert flags == ["addendum reissues M-101 (1 page); base has 2 pages (Mech.pdf): unmatched page kept (p.2), "
                     "counted; check"]
    _same(inventory, dossier, VAV=5)
    # a reissue of both pages replaces both, and nothing is said
    both = _job(base + [(ADDENDUM, 1, "M-101", "HVAC LEVEL 1 PLAN", ["VAV-11", "VAV-12", "VAV-18"], ()),
                        (ADDENDUM, 2, "M-101", "HVAC LEVEL 1 PLAN", ["VAV-15", "VAV-16"], ())],
                kinds={ADDENDUM: "addendum"})
    inventory, dossier, flags, [s], _lines = _read(both, tmp_path)
    assert sorted((v.document, v.page) for v in s.replaced) == [(MECH, 1), (MECH, 2)] and flags == []
    _same(inventory, dossier, VAV=5)


def test_a_reissue_that_matches_two_base_pages_equally_replaces_neither(tmp_path):
    catalogue = _job([(MECH, 1, "M-101", "HVAC LEVEL 1 PLAN", ["VAV-11", "VAV-12"], ()),
                      (MECH, 2, "M-101", "HVAC LEVEL 1 PLAN", ["VAV-15", "VAV-16"], ()),
                      (ADDENDUM, 1, "M-101", "HVAC LEVEL 1 PLAN", ["VAV-11", "VAV-15", "VAV-18"], ())],
                     kinds={ADDENDUM: "addendum"})
    inventory, dossier, flags, supersessions, _lines = _read(catalogue, tmp_path)
    assert supersessions == []
    assert flags == ["addendum reissues M-101 (1 page); base has 2 pages (Mech.pdf): no page matched best, "
                     "every page kept and counted; check"]
    _same(inventory, dossier, VAV=7)


def test_pages_printed_again_alike_are_replaced_together_and_the_other_page_kept(tmp_path):
    """Pages 1 and 2 alike are one plan printed again: replaced together (never page 1 alone, which would leave
    page 2 set aside as page 1's repeat). Page 3, other text, is kept."""
    plan = ["VAV-11", "VAV-12"]
    catalogue = _job([(MECH, 1, "M-101", "HVAC LEVEL 1 PLAN", plan, ()),
                      (MECH, 2, "M-101", "HVAC LEVEL 1 PLAN", plan, ()),
                      (MECH, 3, "M-101", "HVAC LEVEL 1 PLAN", ["VAV-15"], ()),
                      (ADDENDUM, 1, "M-101", "HVAC LEVEL 1 PLAN", plan + ["VAV-18"], ())],
                     kinds={ADDENDUM: "addendum"})
    inventory, dossier, flags, [s], _lines = _read(catalogue, tmp_path)
    assert sorted(v.page for v in s.replaced) == [1, 2]
    assert flags == ["addendum reissues M-101 (1 page); base has 3 pages (Mech.pdf): unmatched page kept (p.3), "
                     "counted; check"]
    _same(inventory, dossier, VAV=4)


# ---- H4: typical sheets and floors keyed by (document, sheet number) -------------------------------------------------

def _alike_here_other_there():
    return _job([(MECH, 1, "M-101", "HVAC LEVEL 1 PLAN", ["VAV-11", "VAV-12"], ()),
                 (MECH, 2, "M-101", "HVAC LEVEL 1 PLAN", ["VAV-11", "VAV-12"], ()),
                 (SECOND, 1, "M-101", "HVAC LEVEL 1 PLAN", ["VAV-21"], ()),
                 (SECOND, 2, "M-101", "HVAC LEVEL 1 PLAN", [f"VAV-2{k}" for k in range(5, 10)], ())])


def test_a_number_printed_again_alike_in_one_document_is_typical_there_only(tmp_path):
    catalogue = _alike_here_other_there()
    [typical] = typical_sheets(catalogue)
    assert (typical.document, typical.sheet, typical.floors) == (MECH, "M-101", ("p.1", "p.2"))
    assert plan_floors(catalogue, [typical]) == {(MECH, "M-101"): frozenset({"P.1", "P.2"})}
    # by sheet number alone too (as the reviewer's path passes it): another document's pages of other text are read
    assert {(SECOND, 1), (SECOND, 2)} <= governing_pages(catalogue, (), ["M-101"])
    inventory, dossier, _flags, _s, _lines = _read(catalogue, tmp_path)
    _same(inventory, dossier, VAV=10)           # 2 x 2 floors + 1 + 5


def test_a_typical_title_multiplies_its_own_documents_sheet_only(tmp_path):
    catalogue = _job([(MECH, 1, "M-150", "HVAC TYPICAL FLOOR PLAN LEVEL 2 TO 4", ["VAV-11"], ()),
                      (SECOND, 1, "M-150", "BUILDING B HVAC LEVEL 2 PLAN", ["VAV-21", "VAV-22"], ())])
    [typical] = typical_sheets(catalogue)
    assert (typical.document, typical.floors) == (MECH, ("2", "3", "4"))
    assert plan_floors(catalogue, [typical]) == {(MECH, "M-150"): frozenset({"2", "3", "4"})}
    inventory, dossier, _flags, _s, _lines = _read(catalogue, tmp_path)
    _same(inventory, dossier, VAV=5)            # 1 x 3 floors + 2, never the second building's x 3
    # a typical each document titles so is one typical sheet per document
    both = _job([(MECH, 1, "M-150", "HVAC TYPICAL FLOOR PLAN LEVEL 2 TO 4", ["VAV-11"], ()),
                 (SECOND, 1, "M-150", "HVAC TYPICAL FLOOR PLAN LEVEL 2 TO 3", ["VAV-21"], ())])
    assert sorted((t.document, len(t.floors)) for t in typical_sheets(both)) == [(MECH, 3), (SECOND, 2)]
    # a typical given with no document (an older reading) stands for its number in every document, as before
    given = SimpleNamespace(sheet="M-150", floors=("2", "3"))
    assert set(plan_floors(both, [given])) == {(MECH, "M-150"), (SECOND, "M-150")}


def test_the_devices_take_the_floors_of_their_own_documents_sheet(monkeypatch):
    from estimator.reading import devices
    catalogue = _job([(MECH, 1, "M-150", "HVAC TYPICAL FLOOR PLAN LEVEL 2 TO 4", ["VAV-11"], ()),
                      (SECOND, 1, "M-150", "HVAC TYPICAL FLOOR PLAN LEVEL 2 TO 4", ["VAV-21"], ())])
    typicals = [t for t in typical_sheets(catalogue) if t.document == MECH]
    monkeypatch.setattr(devices, "_words", lambda page: [devices._Word("T", 10, 10, 12, 12, False)])
    counts, _flags = devices.count_devices(catalogue, lambda document, page: None, [], typicals)
    assert sorted((c.document, c.floors) for c in counts) == [(MECH, 3), (SECOND, 1)]


# ---- H3: a stated multiplier is a placement count ---------------------------------------------------------------------

KEYS = ["CUH-A", "VAV-1", "VAV-3", "VAV-101", "EBB-A"]


@pytest.mark.parametrize("line, tag, n", [
    ("CUH-A (TYP. OF 4)", "CUH-A", 4), ("CUH-A TYP OF 4", "CUH-A", 4), ("CUH-A TYP. OF 4", "CUH-A", 4),
    ("CUH-A (TYPICAL OF 4)", "CUH-A", 4), ("CUH-A x4", "CUH-A", 4), ("CUH-A X 4", "CUH-A", 4),
    ("CUH-A (4)", "CUH-A", 4), ("CUH-A 4 PLACES", "CUH-A", 4), ("CUH-A (4 PLACES)", "CUH-A", 4),
    ("EBB-A (TYP OF 50)", "EBB-A", 50), ("VAV-1 x2", "VAV-1", 2),
])
def test_a_stated_multiplier_after_a_tag_is_that_many_places(line, tag, n):
    assert line_labels(line, label_keys(KEYS)) == Counter({tag: n})


@pytest.mark.parametrize("line, tag", [
    ("VAV-3 450 CFM", "VAV-3"), ("VAV-101 (OFFICE 101)", "VAV-101"), ("VAV-1 (N)", "VAV-1"), ("CUH-A TYP", "CUH-A"),
    ("VAV-1 24X24", "VAV-1"), ("CUH-A (TYP. OF 60)", "CUH-A"), ("CUH-A TYP. OF FOUR", "CUH-A"), ("CUH-A (0)", "CUH-A"),
])
def test_guard_no_multiplier_or_one_out_of_reach_counts_one_place(line, tag):
    assert line_labels(line, label_keys(KEYS)) == Counter({tag: 1})


@pytest.mark.parametrize("text", ["CUH-A (TYP. OF 60)", "CUH-A TYP. OF FOUR"])
def test_a_multiplier_out_of_reach_is_counted_once_and_named_on_the_counts_line(tmp_path, text):
    catalogue = _job([(MECH, 1, "M-101", "HVAC LEVEL 1 PLAN", [text], ())])
    inventory, dossier, _flags, _s, lines = _read(catalogue, tmp_path)
    _same(inventory, dossier, CUH=1)
    assert f"CUH-A on M-101 reads '{text}': the count beside it is not read (over 50, or not a number), counted as one place; check" \
        in lines["CUH"]


def test_a_type_typical_of_four_counts_four_on_both_sides(tmp_path):
    catalogue = _job([(MECH, 1, "M-101", "HVAC LEVEL 1 PLAN", ["CUH-A (TYP. OF 4)", "VAV-1"], ())])
    inventory, dossier, _flags, _s, _lines = _read(catalogue, tmp_path)
    _same(inventory, dossier, CUH=4)


# ---- RD-3: a reissue of a plan printed alike on several pages keeps the floors -----------------------------------------

def _typical_reissue():
    """Mech.pdf prints M-102 on 3 identical pages (one plan for 3 floors); the addendum reissues it on 1 page with one
    note added."""
    plan = ["VAV-11", "FCU-A", "FCU-A"]
    base = [(MECH, n, "M-102", "HVAC TYPICAL FLOOR PLAN", plan, ()) for n in (1, 2, 3)]
    return base, _job(base + [(ADDENDUM, 1, "M-102", "HVAC TYPICAL FLOOR PLAN",
                               plan + ["PROVIDE NEW THERMOSTAT AT EACH FAN COIL"], ())], kinds={ADDENDUM: "addendum"})


def _read_reissued(catalogue, tmp_path):
    """As `read_job` reads them: the typical sheets know the supersessions (a reissue keeps the floors it replaces)."""
    supersessions, flags = supersede(catalogue, sheet_versions(catalogue))
    typicals = typical_sheets(catalogue, supersessions=supersessions)
    reading = _reading()
    reading.supersessions, reading.typicals = tuple(supersessions), tuple(typicals)
    pages = governing_pages(catalogue, supersessions, [(t.document, t.sheet) for t in typicals])
    placed = placements(catalogue, [t.tag for t in catalogue.tags], typicals, pages)
    d = build_dossier(catalogue, reading, tmp_path)
    dossier = {f: (c or {}).get("plan_placements", 0) for f, c in d.counts.items()}
    return placed, dossier, flags, supersessions, typicals, pages


def test_a_one_page_reissue_of_a_plan_printed_on_three_pages_keeps_its_three_floors(tmp_path):
    base, catalogue = _typical_reissue()
    alone = placements(_job(base), ["VAV-11", "FCU-A"], typical_sheets(_job(base)))
    assert (alone["VAV-11"].count, alone["FCU-A"].count) == (3, 6)
    placed, dossier, flags, [s], typicals, pages = _read_reissued(catalogue, tmp_path)
    assert s.current.document == ADDENDUM and sorted(v.page for v in s.replaced) == [1, 2, 3]
    assert s.floors == ("p.1", "p.2", "p.3")
    assert (placed["VAV-11"].count, placed["FCU-A"].count) == (3, 6)
    assert (dossier.get("VAV"), dossier.get("FCU")) == (3, 6)
    assert pages >= {(ADDENDUM, 1)} and not pages & {(MECH, 1), (MECH, 2), (MECH, 3)}
    [flag] = flags
    assert "1 page" in flag and "3 pages" in flag and "Mech.pdf" in flag and "3" in flag
    assert flag == "addendum reissues M-102 (1 page); base prints it on 3 pages (Mech.pdf), one plan for 3 floors: "                    "floors kept ×3; check"
    [typical] = [t for t in typicals if t.document == ADDENDUM]
    assert (typical.sheet, typical.floors) == ("M-102", ("p.1", "p.2", "p.3"))
    assert plan_floors(catalogue, typicals)[(ADDENDUM, "M-102")] == frozenset({"P.1", "P.2", "P.3"})


def test_a_two_page_reissue_of_a_plan_printed_on_three_pages_keeps_three_floors_not_two(tmp_path):
    plan = ["VAV-11", "FCU-A", "FCU-A"]
    new = plan + ["PROVIDE NEW THERMOSTAT AT EACH FAN COIL"]
    catalogue = _job([(MECH, n, "M-102", "HVAC TYPICAL FLOOR PLAN", plan, ()) for n in (1, 2, 3)]
                     + [(ADDENDUM, n, "M-102", "HVAC TYPICAL FLOOR PLAN", new, ()) for n in (1, 2)],
                     kinds={ADDENDUM: "addendum"})
    placed, dossier, flags, [s], typicals, _pages = _read_reissued(catalogue, tmp_path)
    assert (placed["VAV-11"].count, placed["FCU-A"].count) == (3, 6)
    assert (dossier.get("VAV"), dossier.get("FCU")) == (3, 6)
    assert flags == ["addendum reissues M-102 (2 pages); base prints it on 3 pages (Mech.pdf), one plan for 3 floors: "
                     "floors kept ×3; check"]
    assert [(t.document, len(t.floors)) for t in typicals if t.document == ADDENDUM] == [(ADDENDUM, 3)]


def test_the_devices_on_a_one_page_reissue_take_the_three_floors_too(tmp_path, monkeypatch):
    from estimator.reading import devices
    _base, catalogue = _typical_reissue()
    _placed, _dossier, _flags, _s, typicals, pages = _read_reissued(catalogue, tmp_path)
    monkeypatch.setattr(devices, "_words", lambda page: [devices._Word("T", 10, 10, 12, 12, False)])
    counts, _f = devices.count_devices(catalogue, lambda document, page: None, [], typicals, pages=pages)
    assert [(c.document, c.page, c.floors, c.total) for c in counts] == [(ADDENDUM, 1, 3, 3)]


def test_guard_a_reissue_of_a_page_the_base_never_multiplied_carries_no_floors(tmp_path):
    """Pages 1 and 2 alike beside a page 3 of other text are not one plan for several floors: nothing to carry."""
    plan = ["VAV-11", "VAV-12"]
    catalogue = _job([(MECH, 1, "M-101", "HVAC LEVEL 1 PLAN", plan, ()),
                      (MECH, 2, "M-101", "HVAC LEVEL 1 PLAN", plan, ()),
                      (MECH, 3, "M-101", "HVAC LEVEL 1 PLAN", ["VAV-15"], ()),
                      (ADDENDUM, 1, "M-101", "HVAC LEVEL 1 PLAN", plan + ["VAV-18"], ())],
                     kinds={ADDENDUM: "addendum"})
    placed, _dossier, _flags, [s], typicals, _pages = _read_reissued(catalogue, tmp_path)
    assert s.floors == () and typicals == []
    assert sum(p.count for t, p in placed.items() if t.startswith("VAV")) == 4


def test_read_job_gives_the_reissue_the_floors_it_replaces(monkeypatch):
    """The production path (`read_job`) passes the supersessions to the typical sheets."""
    from estimator.reading import devices
    from estimator.reading.job import read_job
    monkeypatch.setattr(devices, "_words", lambda page: [devices._Word("T", 10, 10, 12, 12, False)])
    _base, catalogue = _typical_reissue()
    reading = read_job(catalogue, page_opener=lambda document, page: None)
    assert [len(t.floors) for t in reading.typicals if t.document == ADDENDUM] == [3]
    assert [(d.document, d.page, d.total) for d in reading.devices] == [(ADDENDUM, 1, 3)]
