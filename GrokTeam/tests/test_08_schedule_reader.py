"""B-02 (High, GrokTeam/bugs.md): equipment schedules never become usable facts, so there is no maker, no
unit-furnished owner and no count anchor.

Where it is lost today (patch 08):
- `estimator.reading.schedules` reads the rows (tag, cells, manufacturer), but a "CONTROLS BY / NOTES" column is not
  taken as the remarks column (only a header that IS "NOTES"/"REMARKS"), so the controls owner in it is lost; and
  the drawing's revision block (MARK | DATE | DESCRIPTION) comes back as an untitled schedule;
- `estimator.writing.dossier` prints every row ("[S6] AHU-1 | 1 | ACME AIR | ..."), but `estimator.ledger.seed`
  reads only the counts lines (section 5): no fact per scheduled tag. Maker, area served, the row's QTY and the
  furnished-by owner are left for the AI schedules pass to notice in free text.

Patch 08 adds one fact per scheduled tag, each citing the row's own line: `schedule_qty`, `maker`, `area_served`
(new seed-only kinds; the AI passes' schema keeps its kinds) and `provider` (the owner, read from the CONTROLS BY /
NOTES cell or the note a "SEE NOTE n" cell points to). Area served feeds the 6c room-sensor work later (patch 09).
Invented schedule, generic tags and rooms."""
from pathlib import Path
from types import SimpleNamespace

import pymupdf
import pytest

from estimator.catalogue.documents import Document, JobFolder
from estimator.catalogue.job import Catalogue
from estimator.catalogue.qualify import BidCheck
from estimator.catalogue.register import PageRecord
from estimator.catalogue.sheet_types import Sheet
from estimator.reading.schedules import read_schedules
from estimator.writing.dossier import Dossier

DOC = "Invented/Mech.pdf"
WIDTH, HEIGHT = 2592, 1728

REVISIONS = [["MARK", "DATE", "DESCRIPTION"], ["1", "01/05/26", "ISSUED FOR BID"], ["2", "02/05/26", "ADDENDUM 1"],
             ["3", "03/05/26", "ADDENDUM 2"], ["4", "04/05/26", "REVISED PER COMMENTS"]]
AIR_UNITS = [["AIR HANDLING UNIT SCHEDULE", "", "", "", "", ""],
             ["TAG", "QTY", "MANUFACTURER", "MODEL", "AREA SERVED", "CONTROLS BY / NOTES"],
             ["AHU-1", "1", "ACME AIR", "AX-10", "LOUNGE 0907", "DDC BY UNIT MFR"],
             ["AHU-2", "2", "ACME AIR", "AX-12", "STUDIO 0908", "SEE NOTE 1"],
             ["AHU-3", "1", "ZENITH COIL", "ZC-4", "OFFICE 0912", "PROVIDE WITH DISCONNECT"]]
NOTES = ((200, 320, "NOTES:", 8), (200, 332, "1. SUPPLY SENSOR FURNISHED BY UNIT MFR, MOUNTED IN DUCT.", 8))


def _grid(x0, y0, widths, rows, height=16):
    xs = [x0]
    for w in widths:
        xs.append(xs[-1] + w)
    lines = [(xs[0], y0 + r * height, xs[-1], y0 + r * height) for r in range(len(rows) + 1)]
    lines += [(x, y0, x, y0 + len(rows) * height) for x in xs]
    texts = [(xs[c] + 3, y0 + r * height + height * 0.7, t, 8) for r, row in enumerate(rows) for c, t in enumerate(row) if t]
    return lines, texts


def _schedules(tmp_path, units=AIR_UNITS, widths=(90, 40, 120, 80, 120, 200)):
    rev_lines, rev_texts = _grid(2200, 1500, [40, 60, 200], REVISIONS)
    lines, texts = _grid(200, 200, list(widths), units)
    doc = pymupdf.open()
    page = doc.new_page(width=WIDTH, height=HEIGHT)
    for x, y, text, size in [*rev_texts, *texts, *NOTES]:
        page.insert_text((x, y), text, fontsize=size)
    for x0, y0, x1, y1 in [*rev_lines, *lines]:
        page.draw_line((x0, y0), (x1, y1))
    path = tmp_path / "Mech.pdf"
    doc.save(str(path))
    opened = pymupdf.open(path)
    job = JobFolder("00-0000", tmp_path, (Document(path, DOC, "drawings", "base", 1),), ())
    record = PageRecord(DOC, 1, "text", opened[0].get_text(), 0, large_sheet=True)
    sheet = Sheet(DOC, 1, "X-601", "MECHANICAL SCHEDULES", "Mechanical", ("Schedules",))
    catalogue = Catalogue(job, (record,), (sheet,), (), BidCheck("Qualifies", "", (), (), ()), (), ())
    return catalogue, read_schedules(catalogue, lambda document, n: opened[n - 1])


def _ledger(tmp_path, units=AIR_UNITS, widths=(90, 40, 120, 80, 120, 200)):
    from estimator.ledger.seed import seed
    from estimator.writing.dossier import _Ids, _schedules_section

    catalogue, schedules = _schedules(tmp_path, units, widths)
    ids = _Ids()
    lines = _schedules_section(catalogue, SimpleNamespace(schedules=schedules), ids, {}, {}, {}, [])
    text = "\n".join(["== 4. SCHEDULES ==", *lines]) + "\n"
    dossier = Dossier(job_name="Invented Job", text=text, images=(), sources=dict(ids.where), families=(),
                      device_totals={}, counts={}, stats={})
    return seed(dossier)


def _facts(ledger, kind):
    return {f.subject: f.value for f in ledger.of_kind(kind)}


# ---- the reader ---------------------------------------------------------------------------------------------------

def test_the_air_unit_schedule_rows_are_read_with_maker_and_area_cells(tmp_path):
    """REGRESSION GUARD (passes on current code): the reader itself finds the rows; the loss is downstream."""
    _catalogue, schedules = _schedules(tmp_path)
    (units,) = [s for s in schedules if s.title == "AIR HANDLING UNIT SCHEDULE"]
    assert [r.tag for r in units.rows] == ["AHU-1", "AHU-2", "AHU-3"]
    assert [r.manufacturer for r in units.rows] == ["ACME AIR", "ACME AIR", "ZENITH COIL"]
    assert units.rows[0].cells["AREA SERVED"] == "LOUNGE 0907"


def test_the_revision_block_is_not_taken_for_a_schedule(tmp_path):
    _catalogue, schedules = _schedules(tmp_path)
    assert [s.title for s in schedules] == ["AIR HANDLING UNIT SCHEDULE"], [(s.title, s.headers) for s in schedules]


def test_a_controls_by_notes_column_is_the_schedule_s_remarks_column(tmp_path):
    _catalogue, schedules = _schedules(tmp_path)
    (units,) = [s for s in schedules if s.title == "AIR HANDLING UNIT SCHEDULE"]
    assert "DDC BY UNIT MFR" in units.controls_by


# ---- the facts per scheduled tag ----------------------------------------------------------------------------------

def test_each_scheduled_tag_gets_its_qty_fact(tmp_path):
    assert _facts(_ledger(tmp_path), "schedule_qty") == {"AHU-1": 1, "AHU-2": 2, "AHU-3": 1}


def test_each_scheduled_tag_gets_its_maker_fact(tmp_path):
    assert _facts(_ledger(tmp_path), "maker") == {"AHU-1": "ACME AIR", "AHU-2": "ACME AIR", "AHU-3": "ZENITH COIL"}


def test_each_scheduled_tag_gets_its_area_served_fact(tmp_path):
    assert _facts(_ledger(tmp_path), "area_served") == {"AHU-1": "LOUNGE 0907", "AHU-2": "STUDIO 0908",
                                                        "AHU-3": "OFFICE 0912"}


def test_the_controls_owner_comes_from_the_cell_or_the_note_it_points_to(tmp_path):
    owners = _facts(_ledger(tmp_path), "provider")
    assert owners["AHU-1"] == "DDC BY UNIT MFR"
    assert owners["AHU-2"] == "SUPPLY SENSOR FURNISHED BY UNIT MFR, MOUNTED IN DUCT."


def test_a_remarks_cell_naming_no_party_gives_no_owner(tmp_path):
    """REGRESSION GUARD (negative; passes on current code, which reads no owner at all): "PROVIDE WITH DISCONNECT" says nothing about who furnishes or controls the unit."""
    assert "AHU-3" not in _facts(_ledger(tmp_path), "provider")


def test_every_schedule_fact_cites_its_row_or_note_line(tmp_path):
    ledger = _ledger(tmp_path)
    assert sum(len(ledger.of_kind(k)) for k in ("schedule_qty", "maker", "area_served", "provider")) == 11
    for kind in ("schedule_qty", "maker", "area_served", "provider"):
        for fact in ledger.of_kind(kind):
            assert ledger.knows(fact.source_id), fact
            assert fact.subject in fact.quote or fact.quote.startswith("SUPPLY SENSOR"), fact


def test_a_schedule_with_no_qty_column_gives_no_qty_facts(tmp_path):
    """Negative: no column, no fact (a row is one unit; the count lines keep that)."""
    units = [[row[0], *row[2:]] for row in AIR_UNITS]
    ledger = _ledger(tmp_path, units, (90, 120, 80, 120, 200))
    assert _facts(ledger, "schedule_qty") == {}
    assert _facts(ledger, "maker")["AHU-1"] == "ACME AIR"


def test_the_revision_rows_give_no_facts(tmp_path):
    """Negative: revision marks 1-4 are no unit tags."""
    ledger = _ledger(tmp_path)
    subjects = {f.subject for kind in ("schedule_qty", "maker", "area_served", "provider") for f in ledger.of_kind(kind)}
    assert subjects == {"AHU-1", "AHU-2", "AHU-3"}


def test_the_ledger_has_seed_kinds_for_the_schedule_columns_and_the_ai_passes_keep_theirs():
    """The kinds exist (the 6c area-served link starts here), and the AI passes' answer schema is unchanged."""
    from estimator.ledger import facts, passes
    assert {"schedule_qty", "maker", "area_served"} <= set(facts.KINDS)
    enum = passes.schema()["properties"]["facts"]["items"]["properties"]["kind"]["enum"]
    assert enum == ["family", "unit", "count", "location", "device", "provider", "link", "group", "sequence_match",
                    "front_end", "note"]
