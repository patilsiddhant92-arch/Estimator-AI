"""The job dossier: everything controls-relevant in one document, every paragraph citable."""
import re
from pathlib import Path
from types import SimpleNamespace

import pymupdf

from estimator.catalogue.documents import Document
from estimator.catalogue.overview import SpecOverview
from estimator.catalogue.pdf import Span
from estimator.catalogue.register import PageRecord
from estimator.catalogue.sheet_types import Sheet
from estimator.catalogue.spec_sections import SpecSection
from estimator.catalogue.tags import TagEntry
from estimator.reading.devices import DeviceCount, TypicalSheet
from estimator.reading.inventory import FamilyTotal
from estimator.reading.keynotes import Note
from estimator.reading.schedules import Schedule, ScheduleRow
from estimator.reading.sequences import POINTS, SEQUENCE, Backbone
from estimator.writing import dossier as dossier_module
from estimator.writing.dossier import Dossier, build_dossier, floor_multipliers

SPEC = "Specs/Specs.pdf"
ADDENDUM = "Addendum/230923 Rev Adden 1.pdf"
DWG = "Drawings/Mech.pdf"
HEADINGS = ["== 1. JOB ==", "== 2. SEQUENCE OF OPERATION ==", "== 3. POINTS LISTS ==", "== 4. SCHEDULES ==",
            "== 5. EQUIPMENT COUNTS ==", "== 6. DEVICES ON PLANS ==", "== 7. NOTES ==",
            "== 8. CONTROLS SPEC HIGHLIGHTS =="]

SEQUENCE_PAGE_1 = """SECTION 23 09 93 - SEQUENCE OF OPERATIONS
3.1 AIR HANDLING UNITS

A. AHU-1 shall run continuously in the occupied mode and maintain the discharge air temperature setpoint of 55F.

B. The outdoor air damper shall open to its minimum position whenever the supply fan runs.
"""
SEQUENCE_PAGE_2 = """3.2 EXHAUST FANS

A. EF-1 and EF-2 shall be started and stopped by the BMS on a time schedule, with status by a current switch.
"""
POINTS_PAGE = """POINTS LIST
AHU-1 supply fan status, supply fan start/stop, discharge air temperature, mixed air temperature."""
CONTROLS_SPEC = """SECTION 23 09 23 - DIRECT DIGITAL CONTROL
1.1 RELATED DOCUMENTS

A. Drawings and general provisions of the Contract apply to this Section.

1.14 WARRANTY

A. The controls contractor shall warrant the system for two years from substantial completion.

2.3 OPERATOR WORKSTATION

A. Provide one operator workstation with a 27 inch monitor and the graphics software.
"""


def _doc(relative, kind, pages, revision="base", path=None):
    return Document(Path(path or relative), relative, kind, revision, pages)


def _page(document, page, text, large=False, status="text", edge=()):
    return PageRecord(document, page, status, text, 0, large, tuple(edge))


def _sheet(page, number, title, types=("Plans",), discipline="Mechanical", document=DWG):
    return Sheet(document, page, number, title, discipline, tuple(types))


def _tag(tag, kind="", elsewhere=("M-101",)):
    return TagEntry(tag, kind, (), tuple(elsewhere), 2)


def _catalogue(documents, pages=(), sheets=(), sections=(), tags=(), overview=None, name="26-9999"):
    job = SimpleNamespace(name=name, root=Path("."), documents=tuple(documents))
    return SimpleNamespace(job=job, pages=tuple(pages), sheets=tuple(sheets), sections=tuple(sections),
                           tags=tuple(tags), overview=overview or SpecOverview(), bid=None, flags=())


def _reading(schedules=(), totals=(), devices=(), typicals=(), notes=(), backbone=(), versions=(),
             supersessions=()):
    return SimpleNamespace(schedules=tuple(schedules), totals=tuple(totals), devices=tuple(devices),
                           typicals=tuple(typicals), notes=tuple(notes), backbone=tuple(backbone),
                           versions=tuple(versions), supersessions=tuple(supersessions), inventory=(), legend=(),
                           flags=())


def _backbone(what, where, document, first, last, kind="spec section", duplicate_of=None):
    return Backbone(what, where, document, first, last, kind, duplicate_of)


def _row(tag, cells=None, existing=False):
    return ScheduleRow(tag, dict(cells or {}), None, None, existing)


def _schedule(title, rows, headers=("TAG",), page=5, sheet="M-601", from_text=False, notes=(), controls_by=(),
              document=DWG, type_only=False):
    return Schedule(document, page, sheet, title, tuple(headers), tuple(rows), type_only, tuple(notes),
                    tuple(controls_by), from_text)


def _job(tmp_path=None):
    """A small job: a sequence in the spec, a points list, a schedule sheet and two plans."""
    documents = [_doc(SPEC, "specs", 3), _doc(DWG, "drawings", 3)]
    pages = [_page(SPEC, 1, SEQUENCE_PAGE_1), _page(SPEC, 2, SEQUENCE_PAGE_2), _page(SPEC, 3, POINTS_PAGE),
             _page(DWG, 1, "AHU-1 EF-1 EF-2 T T", large=True), _page(DWG, 2, "EF-1", large=True),
             _page(DWG, 3, "AHU SCHEDULE AHU-1 EF SCHEDULE EF-1 EF-2", large=True)]
    sheets = [_sheet(1, "M-101", "FIRST FLOOR PLAN"), _sheet(2, "M-102", "ROOF PLAN"),
              _sheet(3, "M-601", "SCHEDULES", types=("Schedules",))]
    backbone = [_backbone(SEQUENCE, "23 09 93 SEQUENCE OF OPERATIONS (Specs.pdf, pages 1–2)", SPEC, 1, 2),
                _backbone(POINTS, "Points list pages with no section heading (Specs.pdf, page 3)", SPEC, 3, 3,
                          kind="spec pages")]
    schedules = [_schedule("AHU SCHEDULE", [_row("AHU-1", {"TAG": "AHU-1", "CFM": "5000"})], ("TAG", "CFM"), page=3,
                           notes=("1. PROVIDE WITH FACTORY DDC CONTROLS.",)),
                 _schedule("EF SCHEDULE", [_row("EF-1", {"TAG": "EF-1"}), _row("EF-2", {"TAG": "EF-2"}, existing=True)],
                           page=3)]
    totals = [FamilyTotal("Air Handling Unit", "AHU", 1, "AHU-1", ()), FamilyTotal("Exhaust Fan", "EF", 1, "EF-1", ())]
    devices = [DeviceCount("M-101", DWG, 1, "Thermostat", "T", 2, 1, 2, True)]
    notes = [Note("M-101", DWG, 1, "KEY NOTES", "3", "PROVIDE A CURRENT SWITCH FOR EF-1.", True, ""),
             Note("M-101", DWG, 1, "KEY NOTES", "4", "PATCH THE ROOF.", False, "")]
    sections = [SpecSection("23 09 93", "SEQUENCE OF OPERATIONS", SPEC, 1, 2)]
    tags = [_tag("AHU-1"), _tag("EF-1"), _tag("EF-2")]
    catalogue = _catalogue(documents, pages, sheets, sections, tags)
    reading = _reading(schedules, totals, devices, notes=notes, backbone=backbone)
    return catalogue, reading


def _ids_in(text):
    return re.findall(r"\[(S\d+)\]", text)


# --- the sections and the source ids ------------------------------------------------------------------

def test_every_section_appears_in_order(tmp_path):
    catalogue, reading = _job()
    d = build_dossier(catalogue, reading, tmp_path)
    assert isinstance(d, Dossier) and d.job_name == "26-9999"
    at = [d.text.index(h) for h in HEADINGS]
    assert at == sorted(at)
    assert "AHU-1 shall run continuously in the occupied mode" in d.text
    assert "AHU-1 supply fan status" in d.text.split("== 3. POINTS LISTS ==")[1]
    assert "AHU-1 | 5000" in d.text
    assert "EF-2 (EXISTING)" in d.text
    assert "1. PROVIDE WITH FACTORY DDC CONTROLS." in d.text
    assert "PROVIDE A CURRENT SWITCH FOR EF-1." in d.text
    notes = d.text.split("== 7. NOTES ==")[1].split("== 8.")[0]
    assert "PATCH THE ROOF." in notes.split("--- 7b PLAN SHEET NOTES ---")[1]   # not a controls note: 7b only
    assert d.families == reading.totals
    for key in ("job", "sequence", "points", "schedules", "counts", "devices", "notes", "spec", "total"):
        assert d.stats[key] > 0
    assert d.stats["sequence_pages"] == 2 and d.stats["points_pages"] == 1


def test_source_ids_are_unique_and_resolve(tmp_path):
    catalogue, reading = _job()
    d = build_dossier(catalogue, reading, tmp_path)
    ids = _ids_in(d.text)
    assert ids and len(ids) == len(set(ids))
    assert set(ids) <= set(d.sources)
    assert all(d.sources[i] for i in ids)
    sequence_id = next(i for i in ids if "AHU-1 shall run" in d.text.split(f"[{i}]", 1)[1].split("\n", 1)[0])
    assert d.sources[sequence_id] == "23 09 93 SEQUENCE OF OPERATIONS, Specs.pdf page 1"


def test_the_paragraphs_keep_their_numbering_and_whitespace_is_squashed(tmp_path):
    catalogue, reading = _job()
    d = build_dossier(catalogue, reading, tmp_path)
    assert "] 3.1 AIR HANDLING UNITS\n" in d.text
    assert "] B. The outdoor air damper shall open to its minimum position whenever the supply fan runs." in d.text
    assert "--- 23 09 93 SEQUENCE OF OPERATIONS, Specs.pdf page 2 ---" in d.text


# --- the sequence: duplicates once ---------------------------------------------------------------------

def test_a_duplicate_sequence_appears_once(tmp_path):
    catalogue, reading = _job()
    copy = "Specs/Specs copy.pdf"
    catalogue.job.documents += (_doc(copy, "specs", 2),)
    catalogue.pages += (_page(copy, 1, SEQUENCE_PAGE_1), _page(copy, 2, SEQUENCE_PAGE_2),
                        _page(DWG, 4, SEQUENCE_PAGE_1 + "\n" + SEQUENCE_PAGE_2 + "\nM-002 SEQUENCE SHEET", large=True))
    catalogue.sheets += (_sheet(4, "M-002", "SEQUENCE OF OPERATION", types=()),)
    reading.backbone += (
        _backbone(SEQUENCE, "23 09 93 SEQUENCE OF OPERATIONS (Specs copy.pdf, pages 1–2)", copy, 1, 2,
                  duplicate_of="23 09 93 SEQUENCE OF OPERATIONS (Specs.pdf, pages 1–2)"),
        _backbone(SEQUENCE, "M-002 SEQUENCE OF OPERATION (Mech.pdf, page 4)", DWG, 4, 4, kind="drawing sheet"))
    d = build_dossier(catalogue, reading, tmp_path)
    assert d.text.count("AHU-1 shall run continuously in the occupied mode") == 1
    assert d.text.count("EF-1 and EF-2 shall be started and stopped") == 1
    assert "M-002 SEQUENCE OF OPERATION (Mech.pdf, page 4) repeats 23 09 93 SEQUENCE OF OPERATIONS" in d.text
    assert "M-002 SEQUENCE SHEET" in d.text                    # what differs is still given


def test_a_spec_section_reissued_in_an_addendum_is_given_from_the_addendum(tmp_path):
    catalogue, reading = _job()
    catalogue.job.documents += (_doc(ADDENDUM, "specs", 2, revision="Addendum"),)
    catalogue.pages += (_page(ADDENDUM, 1, SEQUENCE_PAGE_1.replace("55F", "53F")),
                        _page(ADDENDUM, 2, SEQUENCE_PAGE_2))
    reading.backbone = (_backbone(SEQUENCE, "23 09 93 SEQUENCE OF OPERATIONS (Specs.pdf, pages 1–2)", SPEC, 1, 2),
                        _backbone(SEQUENCE, "23 09 93 SEQUENCE OF OPERATIONS (230923 Rev Adden 1.pdf, pages 1–2)",
                                  ADDENDUM, 1, 2)) + reading.backbone[1:]
    d = build_dossier(catalogue, reading, tmp_path)
    sequence = d.text.split("== 2. SEQUENCE OF OPERATION ==")[1].split("== 3.")[0]
    assert "53F" in sequence and "55F" not in sequence
    assert "is replaced by the copy in 230923 Rev Adden 1.pdf" in sequence
    assert "replaced by a later copy" in d.text.split("== 8.")[1]


def test_running_headers_are_left_out_of_the_sequence(tmp_path):
    header = "Harbor Point / Issued for Construction\nSequence of Operations 230993 - {n}\n"
    body = "\n".join(f"{i}. Point {i} of the unit shall be shown at the BMS." for i in range(1, 12))
    documents = [_doc(SPEC, "specs", 4)]
    pages = [_page(SPEC, n, header.format(n=n) + f"\n{n}.1 SYSTEM {n}\nA. Unit {n} shall run on a schedule.\n"
                   f"B. DDC points:\n{body}\nC. The unit shall stop on a fire alarm.\n") for n in range(1, 5)]
    catalogue = _catalogue(documents, pages)
    reading = _reading(backbone=[_backbone(SEQUENCE, "23 09 93 SEQUENCE (Specs.pdf, pages 1–4)", SPEC, 1, 4)])
    d = build_dossier(catalogue, reading, tmp_path)
    assert "Issued for Construction" not in d.text
    assert "230993 -" not in d.text
    assert "A. Unit 3 shall run on a schedule." in d.text
    assert d.text.count("6. Point 6 of the unit shall be shown at the BMS.") == 4    # the body repeats: kept
    assert d.text.count("C. The unit shall stop on a fire alarm.") == 4              # a list item is never a footer


def test_a_long_sequence_is_kept_whole_and_flagged(tmp_path, monkeypatch):
    monkeypatch.setattr(dossier_module, "SEQUENCE_LIMIT", 100)
    catalogue, reading = _job()
    d = build_dossier(catalogue, reading, tmp_path)
    assert d.stats["sequence_over_limit"] == 1
    assert "EF-1 and EF-2 shall be started and stopped" in d.text
    assert "it is given whole" in d.text
    monkeypatch.setattr(dossier_module, "SEQUENCE_LIMIT", 150_000)
    assert build_dossier(*_job(), tmp_path).stats["sequence_over_limit"] == 0


# --- the counts -------------------------------------------------------------------------------------------

def test_the_counts_hold_schedule_rows_distinct_tags_and_plan_placements(tmp_path):
    catalogue, reading = _job()
    d = build_dossier(catalogue, reading, tmp_path)
    assert d.counts["AHU"] == {"schedule_rows": 1, "quantity_column": None, "plan_placements": 1, "riser": None,
                               "distinct_tags": 1}
    # EF-2 is existing on the schedule, but still placed on the plan: EF-1 on the FIRST FLOOR and the ROOF plans, EF-2
    # once. FINAL-I (lead ruling): two plans with other titles add up, so 3 (FINAL-G 2, EF-1 once over the set).
    assert d.counts["EF"]["schedule_rows"] == 1
    assert d.counts["EF"]["plan_placements"] == 3
    assert d.counts["EF"]["distinct_tags"] == 2
    assert "EF (Exhaust Fan): schedule rows 1;" in d.text
    assert "Tags: EF-1, 2." in d.text


def test_a_quantity_column_is_summed(tmp_path):
    catalogue, reading = _job()
    reading.schedules += (
        _schedule("FAN COIL SCHEDULE", [_row("FCU-A", {"TAG": "FCU-A", "QTY": "12"}),
                                        _row("FCU-B", {"TAG": "FCU-B", "QTY": "3"})], ("TAG", "QTY"), page=3),
        _schedule("HEAT PUMP AIR CONDITIONING UNIT SCHEDULE",
                  [_row(None, {"UNIT NO.": "HPAC", "QUANTITY": "719"})], ("UNIT NO.", "QUANTITY"), page=3,
                  type_only=True),
        _schedule("GRILLES, REGISTERS, & DIFFUSERS SCHEDULE", [_row(None, {"TAG": "CD", "QTY": "40"})],
                  ("TAG", "QTY"), page=3, type_only=True))
    d = build_dossier(catalogue, reading, tmp_path)
    assert d.counts["FCU"]["quantity_column"] == 15
    assert d.counts["FCU"]["schedule_rows"] == 2
    assert d.counts["HPAC"]["quantity_column"] == 719
    assert "CD" not in d.counts                                 # air devices are types, never units
    assert "QUANTITY column total 719" in d.text


def test_the_floor_multiplier_applies_to_placements_and_devices(tmp_path):
    documents = [_doc(DWG, "drawings", 5)]
    plan = "VAV-1 VAV-1 T T T"
    pages = [_page(DWG, n, plan, large=True) for n in (1, 2, 3)] + [_page(DWG, 4, "VAV-2 T", large=True)]
    sheets = [_sheet(n, "M-113", "LEVEL 13 TO 15 MECHANICAL PLAN") for n in (1, 2, 3)]
    sheets += [_sheet(4, "M-110", "10TH-16TH FLOOR PLAN TYPICAL")]
    typicals = [TypicalSheet("M-110", "10TH-16TH FLOOR PLAN TYPICAL", tuple(str(n) for n in range(10, 17)), "")]
    devices = [DeviceCount("M-113", DWG, 1, "Thermostat", "T", 3, 1, 3, True),
               DeviceCount("M-110", DWG, 4, "Thermostat", "T", 1, 7, 7, True)]
    catalogue = _catalogue(documents, pages, sheets, tags=[_tag("VAV-1"), _tag("VAV-2")])
    reading = _reading(devices=devices, typicals=typicals)
    assert floor_multipliers(catalogue, reading) == {(DWG, "M-113"): 3, (DWG, "M-110"): 7}
    d = build_dossier(catalogue, reading, tmp_path)
    # FINAL-G: VAV-1 twice on M-113 is one unit on each of its 3 floors (was 2 * 3)
    assert d.counts["VAV"]["plan_placements"] == 1 * 3 + 1 * 7
    assert d.device_totals == {"T": 3 * 3 + 1 * 7}
    assert "M-113 2 × 3 = 6" in d.text
    assert "M-110 1 × 7 = 7" in d.text


def test_a_riser_count_is_kept_separately(tmp_path):
    catalogue, reading = _job()
    catalogue.pages += (_page(DWG, 4, "AHU-1 EF-1 EF-2", large=True),)
    catalogue.sheets += (_sheet(4, "M-501", "AIR RISER DIAGRAM", types=("Air riser",)),)
    d = build_dossier(catalogue, reading, tmp_path)
    assert d.counts["EF"]["riser"] == 2
    assert d.counts["EF"]["plan_placements"] == 3               # the riser is not a plan (EF-1 on two plans: 2)


def test_a_tag_in_every_title_block_is_not_a_unit(tmp_path):
    documents = [_doc(DWG, "drawings", 3)]
    edge = [Span("TEL P-212", 8, 0.9, 0.9, 0.95, 0.92)]
    pages = [_page(DWG, n, f"VAV-{n}\nTEL P-212", large=True, edge=edge) for n in (1, 2, 3)]
    sheets = [_sheet(n, f"M-10{n}", "FLOOR PLAN") for n in (1, 2, 3)]
    catalogue = _catalogue(documents, pages, sheets, tags=[_tag("P-212"), _tag("VAV-1"), _tag("VAV-2"), _tag("VAV-3")])
    d = build_dossier(catalogue, _reading(), tmp_path)
    assert "P" not in d.counts
    assert d.counts["VAV"]["plan_placements"] == 3


# --- the pictures -----------------------------------------------------------------------------------------

def _picture_pdf(path: Path, rotation: int = 0) -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=1728, height=1152)
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 60, 40), False)
    pixmap.clear_with(40)
    page.insert_image(pymupdf.Rect(100, 100, 900, 700), pixmap=pixmap)
    page.insert_text((1300, 1100), "H601 HVAC SCHEDULES", fontsize=12)
    if rotation:
        page.set_rotation(rotation)
    doc.save(str(path))
    doc.close()


def _picture_job(tmp_path, rotation=0):
    pdf = tmp_path / "H.pdf"
    _picture_pdf(pdf, rotation)
    documents = [_doc("H.pdf", "drawings", 1, path=pdf)]
    pages = [_page("H.pdf", 1, "ROOFTOP UNIT SCHEDULE RTU-1 RTU-2", large=True, status="ocr")]
    sheets = [_sheet(1, "H601", "HVAC SCHEDULES", types=("Schedules",), document="H.pdf")]
    schedules = [_schedule("ROOFTOP UNIT SCHEDULE", [_row("RTU-1"), _row("RTU-2")], headers=(), page=1,
                           sheet="H601", from_text=True, document="H.pdf")]
    catalogue = _catalogue(documents, pages, sheets, tags=[_tag("RTU-1"), _tag("RTU-2")])
    return catalogue, _reading(schedules)


def test_a_picture_schedule_yields_an_image(tmp_path):
    catalogue, reading = _picture_job(tmp_path)
    cache = tmp_path / "cache"
    d = build_dossier(catalogue, reading, cache)
    [image] = d.images
    path = Path(image.path)
    assert path.is_absolute() and path.parent == (cache / "dossier-images").resolve()
    assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert image.what == "H601 HVAC SCHEDULES — picture schedule"
    assert (image.sheet, image.document, image.page) == ("H601", "H.pdf", 1)
    assert "See image I1." in d.text
    assert "I1" in d.sources and "picture" in d.sources["I1"]
    assert d.stats["images"] == 1
    assert 2150 <= pymupdf.Pixmap(str(path)).width <= 2250    # 800 points at 200 dpi
    assert not list(path.parent.glob("*.tmp*"))


def test_a_picture_is_reused_when_present(tmp_path):
    catalogue, reading = _picture_job(tmp_path)
    cache = tmp_path / "cache"
    first = build_dossier(catalogue, reading, cache)
    stamp = Path(first.images[0].path).stat().st_mtime_ns
    second = build_dossier(catalogue, reading, cache)
    assert second.images[0].path == first.images[0].path
    assert Path(second.images[0].path).stat().st_mtime_ns == stamp


def test_a_picture_on_a_rotated_sheet_is_clipped_where_it_is_seen(tmp_path):
    catalogue, reading = _picture_job(tmp_path, rotation=90)
    d = build_dossier(catalogue, reading, tmp_path / "cache")
    [image] = d.images
    pixmap = pymupdf.Pixmap(image.path)
    # The picture is 800 x 600 points on the unrotated page; seen rotated it is taller than wide.
    assert pixmap.height > pixmap.width
    samples = pixmap.samples
    dark = sum(1 for i in range(0, len(samples), pixmap.n) if samples[i] < 100) / (pixmap.width * pixmap.height)
    assert dark > 0.9


def test_a_schedule_sheet_with_no_picture_and_no_table_is_rendered_whole(tmp_path):
    pdf = tmp_path / "M.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=1728, height=1152)
    page.insert_text((100, 100), "EXHAUST FAN SCHEDULE  EF-1  EF-2", fontsize=12)
    doc.save(str(pdf))
    doc.close()
    documents = [_doc("M.pdf", "drawings", 1, path=pdf)]
    pages = [_page("M.pdf", 1, "EXHAUST FAN SCHEDULE EF-1 EF-2", large=True)]
    sheets = [_sheet(1, "M-701.00", "SCHEDULES", types=("Schedules",), document="M.pdf")]
    schedules = [_schedule("EXHAUST FAN SCHEDULE", [_row("EF-1"), _row("EF-2")], headers=(), page=1,
                           sheet="M-701.00", from_text=True, document="M.pdf")]
    d = build_dossier(_catalogue(documents, pages, sheets), _reading(schedules), tmp_path / "cache")
    [image] = d.images
    assert image.what == "M-701.00 SCHEDULES — schedule, table unreadable"
    assert 3550 <= pymupdf.Pixmap(image.path).width <= 3650  # 24 inches at 150 dpi


def test_a_schedule_read_from_its_table_has_no_picture(tmp_path):
    catalogue, reading = _job()
    d = build_dossier(catalogue, reading, tmp_path)
    assert d.images == ()
    assert "See image" not in d.text


# --- the job, the devices, the spec highlights -------------------------------------------------------------

def test_the_job_section_names_the_documents(tmp_path):
    catalogue, reading = _job()
    d = build_dossier(catalogue, reading, tmp_path)
    job = d.text.split("== 1. JOB ==")[1].split("== 2.")[0]
    assert "Job: 26-9999" in job
    assert "Document: Specs.pdf — specs, 3 pages" in job
    assert "Document: Mech.pdf — drawings, 3 pages" in job


def test_the_devices_list_each_label_with_its_sheets(tmp_path):
    catalogue, reading = _job()
    d = build_dossier(catalogue, reading, tmp_path)
    assert d.device_totals == {"T": 2}
    assert "T (Thermostat): 2 in all — M-101 2" in d.text


def test_the_controls_spec_highlights_keep_the_headings_that_price_the_job(tmp_path):
    catalogue, reading = _job()
    catalogue.job.documents += (_doc("Specs/230923.pdf", "specs", 1),)
    catalogue.pages += (_page("Specs/230923.pdf", 1, CONTROLS_SPEC),)
    catalogue.sections += (SpecSection("23 09 23", "DIRECT DIGITAL CONTROL", "Specs/230923.pdf", 1, 1),)
    d = build_dossier(catalogue, reading, tmp_path)
    spec = d.text.split("== 8. CONTROLS SPEC HIGHLIGHTS ==")[1]
    assert "warrant the system for two years" in spec
    assert "Provide one operator workstation" in spec
    assert "Drawings and general provisions" not in spec
    assert spec.index("OPERATOR WORKSTATION") < spec.index("WARRANTY")    # the front end first
    assert "above" not in spec                    # section 8 is read alone: it points at nothing
    ids = _ids_in(spec)
    assert all("23 09 23 DIRECT DIGITAL CONTROL §" in d.sources[i] for i in ids)


def test_the_controls_spec_highlights_are_capped_and_say_what_was_cut(tmp_path, monkeypatch):
    monkeypatch.setattr(dossier_module, "SPEC_LIMIT", 120)
    catalogue, reading = _job()
    catalogue.job.documents += (_doc("Specs/230923.pdf", "specs", 1),)
    catalogue.pages += (_page("Specs/230923.pdf", 1, CONTROLS_SPEC),)
    catalogue.sections += (SpecSection("23 09 23", "DIRECT DIGITAL CONTROL", "Specs/230923.pdf", 1, 1),)
    d = build_dossier(catalogue, reading, tmp_path)
    spec = d.text.split("== 8. CONTROLS SPEC HIGHLIGHTS ==")[1]
    assert "Cut at 120 characters. Left out:" in spec
    assert "1.14 WARRANTY" in spec.split("Left out:")[1]


def test_an_empty_job_still_has_every_section(tmp_path):
    d = build_dossier(_catalogue([]), _reading(), tmp_path)
    assert all(h in d.text for h in HEADINGS)
    assert "(No sequence of operation found in the documents.)" in d.text
    assert d.counts == {} and d.device_totals == {} and d.images == ()


# --- round 3: the plan sheets' own notes (7b) -------------------------------------------------------------

def test_the_plan_sheet_notes_are_all_given_in_7b_with_ids_capped_per_sheet(tmp_path, monkeypatch):
    from estimator.writing.whole_job import _sections
    catalogue, reading = _job()
    plumbing = "Drawings/Plumb.pdf"
    catalogue.sheets = catalogue.sheets + (_sheet(1, "P-101", "PLUMBING PLAN", discipline="Plumbing",
                                                  document=plumbing),
                                           _sheet(2, "A-101", "FLOOR PLAN", discipline="Architectural",
                                                  document=plumbing))
    long = [Note("P-101", plumbing, 1, "GENERAL NOTES", str(n), f"NOTE {n} " + "X" * 200, False, "")
            for n in range(1, 30)]
    reading.notes = reading.notes + tuple(long) + (Note("A-101", plumbing, 2, "GENERAL NOTES", "1",
                                                        "PAINT THE WALLS.", False, ""),)
    d = build_dossier(catalogue, reading, tmp_path)
    part = d.text.split("--- 7b PLAN SHEET NOTES ---")[1].split("== 8.")[0]
    assert "NOTE 1 " in part and "PATCH THE ROOF." in part and "PAINT THE WALLS." not in part
    p101 = part.split("P-101")[1]
    assert len(p101) < 3_600 and "more notes on this sheet" in p101
    assert "PROVIDE A CURRENT SWITCH FOR EF-1." not in part            # given above in 7, not repeated
    for sid in re.findall(r"\[(S\d+)\]", part):
        assert sid in d.sources
    _, sections = _sections(d.text)
    assert sorted(sections) == list(range(1, 9))
    assert "7b PLAN SHEET NOTES" in sections[7]


def test_each_plan_sheets_own_text_is_given_in_7c_once_per_sheet_number(tmp_path):
    catalogue, reading = _job()
    plumbing = "Drawings/Plumb.pdf"
    catalogue.sheets = catalogue.sheets + (_sheet(1, "P-101", "PLUMBING PLAN", discipline="Plumbing",
                                                  document=plumbing),
                                           _sheet(2, "A-101", "FLOOR PLAN", discipline="Architectural",
                                                  document=plumbing))
    catalogue.pages = catalogue.pages + (
        PageRecord(plumbing, 1, "text", "KEYED NOTE 4 PROVIDE 2-POSITION ACTUATOR ON INTAKE DAMPER " + "Y" * 9000, 0),
        PageRecord(plumbing, 2, "text", "PAINT THE WALLS.", 0))
    d = build_dossier(catalogue, reading, tmp_path)
    part = d.text.split("--- 7c PLAN SHEET TEXT ---")[1].split("== 8.")[0]
    assert "PROVIDE 2-POSITION ACTUATOR ON INTAKE DAMPER" in part and "PAINT THE WALLS." not in part
    p101 = part.split("P-101")[1]
    assert len(p101) < 8_200 and "…" in p101
    for sid in re.findall(r"\[(S\d+)\]", part):
        assert sid in d.sources


def test_sheet_pictures_render_whole_sheets_once(tmp_path):
    from estimator.writing.dossier import sheet_pictures
    catalogue, _reading = _picture_job(tmp_path)
    images, flags = sheet_pictures(catalogue, tmp_path / "cache", [("H.pdf", 1)], "plan sheet")
    assert flags == [] and len(images) == 1
    path = Path(images[0].path)
    assert path.suffix == ".png" and path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert images[0].what == "H601 HVAC SCHEDULES — plan sheet"
    assert (images[0].sheet, images[0].document, images[0].page) == ("H601", "H.pdf", 1)
    again, _ = sheet_pictures(catalogue, tmp_path / "cache", [("H.pdf", 1)], "plan sheet")
    assert again[0].path == images[0].path
    missing, flags = sheet_pictures(catalogue, tmp_path / "cache", [("H.pdf", 9)], "plan sheet")
    assert missing == [] and len(flags) == 1


# --- the spec pass reads sections 1 and 8 only: section 8 never points at text above -------------------

DDC = "Specs/230923.pdf"
DDC_ADDENDUM = "Addendum/230923 Adden 1.pdf"
DDC_POINTS = "POINTS LIST\nAHU-1 supply fan status and discharge air temperature.\n"


def _job_with_a_controls_spec_printed_whole_above():
    """The controls spec section carries a points list, so section 3 prints its pages whole."""
    catalogue, reading = _job()
    catalogue.job.documents += (_doc(DDC, "specs", 2),)
    catalogue.pages += (_page(DDC, 1, CONTROLS_SPEC), _page(DDC, 2, DDC_POINTS))
    catalogue.sections += (SpecSection("23 09 23", "DIRECT DIGITAL CONTROL", DDC, 1, 2),)
    reading.backbone += (_backbone(POINTS, "23 09 23 DIRECT DIGITAL CONTROL (230923.pdf, pages 1–2)", DDC, 1, 2),)
    return catalogue, reading


def _spec_pass_text(catalogue, reading, tmp_path):
    from estimator.ledger.passes import documents, pass_named
    d = build_dossier(catalogue, reading, tmp_path)
    return d, documents(pass_named("spec"), d, catalogue)


def test_the_spec_pass_gets_the_highlights_of_a_controls_spec_printed_whole_above(tmp_path):
    catalogue, reading = _job_with_a_controls_spec_printed_whole_above()
    d, text = _spec_pass_text(catalogue, reading, tmp_path)
    assert "warrant the system for two years" in d.text.split("== 3. POINTS LISTS ==")[1].split("== 4.")[0]
    spec = text.split("== 8. CONTROLS SPEC HIGHLIGHTS ==")[1]
    assert "warrant the system for two years" in spec
    assert "Provide one operator workstation" in spec
    assert "above" not in text.split("== 8.")[1]
    ids = _ids_in(spec)
    assert ids and all("23 09 23 DIRECT DIGITAL CONTROL §" in d.sources[i] for i in ids)


def test_the_spec_pass_gets_the_highlights_of_the_addendum_copy_without_a_pointer(tmp_path):
    catalogue, reading = _job_with_a_controls_spec_printed_whole_above()
    catalogue.job.documents += (_doc(DDC_ADDENDUM, "specs", 2, revision="Addendum"),)
    catalogue.pages += (_page(DDC_ADDENDUM, 1, CONTROLS_SPEC.replace("two years", "three years")),
                        _page(DDC_ADDENDUM, 2, DDC_POINTS))
    catalogue.sections += (SpecSection("23 09 23", "DIRECT DIGITAL CONTROL", DDC_ADDENDUM, 1, 2),)
    reading.backbone += (_backbone(POINTS, "23 09 23 DIRECT DIGITAL CONTROL (230923 Adden 1.pdf, pages 1–2)",
                                   DDC_ADDENDUM, 1, 2),)
    _, text = _spec_pass_text(catalogue, reading, tmp_path)
    spec = text.split("== 8. CONTROLS SPEC HIGHLIGHTS ==")[1]
    assert "warrant the system for three years" in spec
    assert "two years" not in spec                       # the replaced copy is named, not quoted
    assert "replaced by a later copy" in spec
    assert "above" not in spec


def test_the_highlights_of_a_section_printed_above_keep_the_cap_and_say_what_was_cut(tmp_path, monkeypatch):
    monkeypatch.setattr(dossier_module, "SPEC_LIMIT", 120)
    catalogue, reading = _job_with_a_controls_spec_printed_whole_above()
    _, text = _spec_pass_text(catalogue, reading, tmp_path)
    spec = text.split("== 8. CONTROLS SPEC HIGHLIGHTS ==")[1]
    assert "Cut at 120 characters. Left out:" in spec
    assert "1.14 WARRANTY" in spec.split("Left out:")[1]
    assert "above" not in spec


def test_a_controls_spec_with_no_highlight_article_says_so_without_a_pointer(tmp_path):
    catalogue, reading = _job()
    _, text = _spec_pass_text(catalogue, reading, tmp_path)
    spec = text.split("== 8. CONTROLS SPEC HIGHLIGHTS ==")[1]
    assert "above" not in spec
    assert "No controls spec section found" not in spec
    assert "23 09 93 SEQUENCE OF OPERATIONS, Specs.pdf" in spec


def test_the_same_keynote_on_the_same_sheet_of_two_documents_is_given_twice_with_two_sources(tmp_path):
    """LDG-9: building B's M-101 carries the same note text as building A's; each one is its own fact."""
    catalogue, reading = _job()
    other = "Drawings/BuildingB.pdf"
    catalogue.sheets = catalogue.sheets + (_sheet(1, "M-101", "FIRST FLOOR PLAN", document=other),)
    text = "PROVIDE A DUCT SMOKE DETECTOR RELAY FOR AHU-9."
    reading.notes = tuple(reading.notes) + (Note("M-101", DWG, 1, "KEY NOTES", "9", text, True, ""),
                                            Note("M-101", other, 1, "KEY NOTES", "9", text, True, ""))
    d = build_dossier(catalogue, reading, tmp_path)
    part = d.text.split("== 7. NOTES ==")[1].split("--- 7b PLAN SHEET NOTES ---")[0]
    lines = [ln for ln in part.splitlines() if text in ln]
    assert len(lines) == 2
    ids = {re.match(r"\[(S\d+)\]", ln).group(1) for ln in lines}
    assert len(ids) == 2 and all(sid in d.sources for sid in ids)


# --- 7c gives each governing page, keyed by (document, page) (LDG-8) -----------------------------------------

def _two_m101_job(second_kind="drawings", second_revision="base", supersessions=()):
    """Two documents that each carry an M-101 plan with its own text: two buildings, or a base and its reissue."""
    first, second = "Drawings/Bldg A.pdf", "Drawings/Bldg B.pdf"
    documents = [_doc(first, "drawings", 1), _doc(second, second_kind, 1, revision=second_revision)]
    pages = [_page(first, 1, "FIRST FLOOR PLAN KEYED NOTE 1 PROVIDE A LEAK CHIME AT WH-1."),
             _page(second, 1, "FIRST FLOOR PLAN KEYED NOTE 1 PROVIDE A DAMPER ACTUATOR AT MD-7.")]
    sheets = [_sheet(1, "M-101", "FIRST FLOOR PLAN", document=first),
              _sheet(1, "M-101", "FIRST FLOOR PLAN", document=second)]
    return _catalogue(documents, pages, sheets), _reading(supersessions=supersessions), first, second


def _sheet_text_part(d):
    return d.text.split("--- 7c PLAN SHEET TEXT ---")[1].split("== 8.")[0]


def test_two_base_documents_each_with_an_m101_give_both_texts_in_7c(tmp_path):
    catalogue, reading, first, second = _two_m101_job()
    d = build_dossier(catalogue, reading, tmp_path)
    part = _sheet_text_part(d)
    assert "LEAK CHIME AT WH-1" in part and "DAMPER ACTUATOR AT MD-7" in part
    assert d.sheet_pages and set(d.sheet_pages.values()) == {(first, 1), (second, 1)}


def test_a_revision_1_reissue_gives_only_the_reissues_text_in_7c(tmp_path):
    from estimator.reading.revisions import SheetVersion, Supersession
    first, second = "Drawings/Bldg A.pdf", "Drawings/Bldg B.pdf"
    base = SheetVersion("M-101", first, 1, (), None, "title block")
    reissue = SheetVersion("M-101", second, 1, (), None, "title block")
    catalogue, reading, _, _ = _two_m101_job(second_revision="1",
                                             supersessions=[Supersession("M-101", reissue, (base,), (), "")])
    d = build_dossier(catalogue, reading, tmp_path)
    part = _sheet_text_part(d)
    assert "DAMPER ACTUATOR AT MD-7" in part and "LEAK CHIME AT WH-1" not in part
    assert set(d.sheet_pages.values()) == {(second, 1)}


# --- two documents with one file name ------------------------------------------------------------------------

def test_two_documents_with_one_file_name_cite_their_own_paths(tmp_path):
    """LDG-10: "Mech.pdf" in two folders never gives two identical citations; a file name no other document
    shares is still cited by its name alone."""
    other = "Bldg B/mech.PDF"
    catalogue, reading = _job()
    catalogue.job.documents += (_doc(other, "drawings", 1),)
    catalogue.pages += (_page(other, 1, "EF-1", large=True),)
    catalogue.sheets += (_sheet(1, "M-101", "FIRST FLOOR PLAN", document=other),)
    reading.notes += (Note("M-101", other, 1, "KEY NOTES", "3", "PROVIDE A CURRENT SWITCH FOR EF-1.", True, ""),)
    d = build_dossier(catalogue, reading, tmp_path)
    wheres = [w for w in d.sources.values() if w.startswith("KEY NOTES 3, M-101")]
    assert wheres == ["KEY NOTES 3, M-101, Drawings/Mech.pdf page 1", "KEY NOTES 3, M-101, Bldg B/mech.PDF page 1"]
    assert "--- M-101, Bldg B/mech.PDF page 1 ---" in d.text
    assert any(w.endswith(", Specs.pdf page 1") for w in d.sources.values())      # a unique name stays short


def test_a_picture_is_drawn_again_when_its_documents_content_changes_though_its_size_and_date_do_not(tmp_path):
    # LDG-15: the picture's name follows the document's content (sha1), never its size and date alone
    import os
    from estimator.writing.dossier import sheet_pictures
    catalogue, reading = _picture_job(tmp_path)
    pdf = tmp_path / "H.pdf"
    before = pdf.stat()
    [first], _ = sheet_pictures(catalogue, tmp_path / "cache", [("H.pdf", 1)], "plan sheet")
    pictured = build_dossier(catalogue, reading, tmp_path / "cache").images[0].path
    changed = pdf.read_bytes().replace(b"(" * 7200, b"P" * 7200)          # the picture's grey made lighter
    assert changed != pdf.read_bytes() and len(changed) == before.st_size     # other content, the same size
    pdf.write_bytes(changed)
    os.utime(pdf, ns=(before.st_atime_ns, before.st_mtime_ns))                  # and the same date
    dossier_module._DIGESTS.clear()                 # a later run: its own hashes, the earlier run's PNGs on disk
    [again], _ = sheet_pictures(catalogue, tmp_path / "cache", [("H.pdf", 1)], "plan sheet")
    assert again.path != first.path
    assert build_dossier(catalogue, reading, tmp_path / "cache").images[0].path != pictured


def test_a_numberless_typical_plans_units_are_counted_times_its_floors_in_the_counts_line():
    # RD-13: the counts line the ledger seed and the planner read, not only the inventory
    title = "TYPICAL 2ND-5TH FLOOR PLAN"
    documents = [_doc(DWG, "drawings", 2)]
    pages = [_page(DWG, 1, "FAN COIL SCHEDULE FCU-1", large=True), _page(DWG, 2, "FCU-1", large=True)]
    sheets = [_sheet(1, "M-601", "SCHEDULES", types=("Schedules",)), _sheet(2, None, title)]
    catalogue = _catalogue(documents, pages, sheets, tags=[_tag("FCU-1", elsewhere=())])
    reading = _reading(typicals=[TypicalSheet(None, title, ("2", "3", "4", "5"), "", DWG)])
    d = build_dossier(catalogue, reading, None)
    assert d.counts["FCU"]["plan_placements"] == 4


# --- a schedule of air devices lists types, never units, families or systems (HP 3, HP 20) ----------------------

def _outlet_schedule(passive, title="Schedule (no title found)", codes=("B1", "B2", "CD"), page=2):
    """An air outlet schedule as the reader gives it: its type codes as rows with no unit tag."""
    rows = [_row(None, {"DESIGNATION": code, "DESCRIPTION": "DIFFUSER"}) for code in codes]
    return Schedule(DWG, page, "M-601", title, ("DESIGNATION", "DESCRIPTION"), tuple(rows), True, (), (), passive=passive)


def _outlet_job():
    plan ="\n".join(["B-1"] * 5 + ["B-2"] * 3 + ["CD"] * 4)
    pages = [_page(DWG, 1, plan, large=True), _page(DWG, 2, "AIR OUTLET SCHEDULE B1 B2 CD", large=True)]
    sheets = [_sheet(1, "M-101", "HVAC FIRST FLOOR PLAN"), _sheet(2, "M-601", "SCHEDULES", types=("Schedules",))]
    return _catalogue([_doc(DWG, "drawings", 2)], pages, sheets, tags=[_tag("B-1"), _tag("B-2")])


def test_an_air_device_schedules_codes_never_become_families(tmp_path):
    """B1 and B2 are no boilers, CD no equipment: their labels on the plans make no family, so no system."""
    d = build_dossier(_outlet_job(), _reading([_outlet_schedule(True)]), tmp_path / "passive")
    assert "B" not in d.counts and "CD" not in d.counts
    line = next(line for line in d.text.splitlines() if "Schedule (no title found)" in line and "M-601" in line)
    assert "passive" in line and "not equipment" in line
    assert "type rows, no unit tags" not in line
    # the same schedule without the mark is what the dossier did before: the codes become families
    control = build_dossier(_outlet_job(), _reading([_outlet_schedule(False)]), tmp_path / "plain")
    assert "CD" in control.counts and "B" in control.counts
    assert "type rows, no unit tags" in next(line for line in control.text.splitlines() if "M-601" in line and "(3 rows" in line)


def test_a_boiler_schedule_keeps_its_boilers_beside_an_air_outlet_schedule_that_reads_b1(tmp_path):
    """A job with both: the codes B1 to B4 of the air outlets never remove the boilers B-1 and B-2 of their schedule."""
    boilers = _schedule("BOILER SCHEDULE", [_row("B-1", {"TAG": "B-1"}), _row("B-2", {"TAG": "B-2"})], page=3)
    pages = [_page(DWG, 1, "B-1\nB-2", large=True), _page(DWG, 2, "AIR OUTLET SCHEDULE B1 B2 B3 B4", large=True),
             _page(DWG, 3, "BOILER SCHEDULE B-1 B-2", large=True)]
    sheets = [_sheet(1, "M-101", "HVAC BOILER PLAN"), _sheet(2, "M-601", "SCHEDULES", types=("Schedules",)),
              _sheet(3, "M-602", "SCHEDULES", types=("Schedules",))]
    catalogue = _catalogue([_doc(DWG, "drawings", 3)], pages, sheets, tags=[_tag(f"B-{n}") for n in range(1, 5)])
    outlets = _outlet_schedule(True, "AIR OUTLET SCHEDULE", ("B1", "B2", "B3", "B4"))
    d = build_dossier(catalogue, _reading([outlets, boilers]), tmp_path)
    assert d.counts["B"]["schedule_rows"] == 2
    assert d.counts["B"]["distinct_tags"] == 2          # B-3 and B-4 are air outlets
    assert d.counts["B"]["plan_placements"] == 2        # the boilers on their plan are still counted
    assert "Tags: B-1, 2." in d.text


def test_a_type_code_of_an_air_device_schedule_with_a_quantity_column_is_no_family(tmp_path):
    catalogue, reading = _job()
    reading.schedules += (Schedule(DWG, 3, "M-601", "SCHEDULE", ("TAG", "QTY"), (_row(None, {"TAG": "LD", "QTY": "40"}),),
                                   True, (), (), passive=True),)
    d = build_dossier(catalogue, reading, tmp_path)
    assert "LD" not in d.counts
