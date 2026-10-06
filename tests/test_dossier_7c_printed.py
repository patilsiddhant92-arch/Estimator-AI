"""Section 7c (plan sheet text) gives the text of a drawing sheet that sections 2 or 3 printed whenever a reading
pass reads that sheet from 7c but not the section that printed it (FINAL-A, task 3). The details, risers, network
and plans passes read no section 2 or 3, so a sequence sheet that is also a control diagram or a riser was missing
from them with no line saying so. Never a pointer to text the pass does not receive; no earlier source id moves.
Invented fixtures only."""
import re
from pathlib import Path
from types import SimpleNamespace

from estimator.catalogue.documents import Document
from estimator.catalogue.overview import SpecOverview
from estimator.catalogue.register import PageRecord
from estimator.catalogue.sheet_types import Sheet
from estimator.ledger.passes import PASSES, documents
from estimator.reading.sequences import POINTS, SEQUENCE, Backbone
from estimator.writing.dossier import build_dossier

DWG = "Drawings/Mech.pdf"
DIAGRAM_TEXT = ("CONTROL DIAGRAM AHU-1\n3.1 AIR HANDLING UNIT AHU-1\nA. AHU-1 shall run in the occupied mode.\n"
                "PROVIDE A FREEZESTAT AT THE COIL.")
RISER_TEXT = "BMS NETWORK RISER\nPOINTS: AHU-1 SUPPLY FAN STATUS, SUPPLY FAN START STOP.\nFIBRE BACKBONE BY OTHERS."
PLAN_TEXT = "FIRST FLOOR PLAN\nAHU-1\nEF-1\nKEYNOTE: PROVIDE A CURRENT SWITCH FOR EF-1."


def _job(diagram_types=("Control diagrams",)):
    """A drawing set whose control diagram sheet (M-701) is the sequence (printed whole by section 2), whose
    network riser (M-702) is the points list (printed by section 3), and a floor plan (M-101) printed by neither."""
    pages = [PageRecord(DWG, 1, "text", PLAN_TEXT, 0, True, ()),
             PageRecord(DWG, 2, "text", DIAGRAM_TEXT, 0, True, ()),
             PageRecord(DWG, 3, "text", RISER_TEXT, 0, True, ())]
    sheets = [Sheet(DWG, 1, "M-101", "FIRST FLOOR PLAN", "Mechanical", ("Plans",)),
              Sheet(DWG, 2, "M-701", "CONTROL DIAGRAMS", "Mechanical", tuple(diagram_types)),
              Sheet(DWG, 3, "M-702", "BMS NETWORK RISER", "Mechanical", ("Network riser",))]
    job = SimpleNamespace(name="26-9999", root=Path("."), documents=(Document(Path(DWG), DWG, "drawings", "base", 3),))
    catalogue = SimpleNamespace(job=job, pages=tuple(pages), sheets=tuple(sheets), sections=(), tags=(),
                                overview=SpecOverview(), bid=None, flags=())
    backbone = (Backbone(SEQUENCE, "M-701 CONTROL DIAGRAMS (Mech.pdf, page 2)", DWG, 2, 2, "drawing", None),
                Backbone(POINTS, "M-702 BMS NETWORK RISER (Mech.pdf, page 3)", DWG, 3, 3, "drawing", None))
    reading = SimpleNamespace(schedules=(), totals=(), devices=(), typicals=(), notes=(), backbone=backbone,
                              versions=(), supersessions=(), inventory=(), legend=(), flags=())
    return catalogue, reading


def _pass(name):
    return next(p for p in PASSES if p.name == name)


def test_the_details_pass_gets_the_text_of_a_control_diagram_sheet_the_sequence_printed(tmp_path):
    catalogue, reading = _job()
    d = build_dossier(catalogue, reading, tmp_path)
    assert "FREEZESTAT" in d.text.split("== 3. POINTS LISTS ==")[0]          # section 2 printed it
    text = documents(_pass("details"), d, catalogue)
    assert "M-701" in text and "PROVIDE A FREEZESTAT AT THE COIL" in text
    assert "above" not in text


def test_the_network_pass_gets_the_text_of_a_riser_sheet_the_points_list_printed(tmp_path):
    catalogue, reading = _job()
    d = build_dossier(catalogue, reading, tmp_path)
    text = documents(_pass("network"), d, catalogue)
    assert "M-702" in text and "FIBRE BACKBONE BY OTHERS" in text


def test_the_added_lines_take_ids_after_section_8_so_no_earlier_id_moves(tmp_path):
    catalogue, reading = _job()
    d = build_dossier(catalogue, reading, tmp_path)
    seventh = d.text.split("== 7. NOTES ==")[1].split("== 8.")[0]
    added = {int(n) for n in re.findall(r"^\[S(\d+)\] M-70[12]", seventh, re.M)}
    others = {int(n) for n in re.findall(r"^\[S(\d+)\]", d.text, re.M)} - added
    assert len(added) == 2 and min(added) > max(others)
    assert re.search(r"^\[S\d+\] M-101, Mech\.pdf page 1 FIRST FLOOR PLAN: ", seventh, re.M)       # the plan keeps its place first


def test_a_sheet_no_pass_reads_from_7c_is_not_repeated(tmp_path):
    catalogue, reading = _job(diagram_types=("Sequence",))
    d = build_dossier(catalogue, reading, tmp_path)
    seventh = d.text.split("== 7. NOTES ==")[1].split("== 8.")[0]
    assert "M-701" not in seventh
    assert "M-702" in seventh


def test_the_plans_pass_and_the_sequence_pass_are_unchanged_when_their_sheets_are_not_involved(tmp_path):
    catalogue, reading = _job()
    d = build_dossier(catalogue, reading, tmp_path)
    plans = documents(_pass("plans"), d, catalogue)
    assert "M-701" not in plans and "M-702" not in plans
    sequence = documents(_pass("sequence"), d, catalogue)
    assert "7c" not in sequence
