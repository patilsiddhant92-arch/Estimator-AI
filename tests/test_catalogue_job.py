import openpyxl
import pytest

from estimator.__main__ import main
from estimator.catalogue.job import catalogue_job, repeated_plans, summary_lines
from pdfs import FILLER, Page, make_pdf

SCHEDULE = Page(width=3024, height=2160, texts=((200, 300, FILLER, 12), (300, 400, "AIR HANDLING UNIT SCHEDULE", 18),
                                                (300, 450, "AHU-1  AHU-2", 12), (2640, 1860, "HVAC SCHEDULES", 20),
                                                (2800, 2000, "M-601", 40)))
PLAN = Page(width=3024, height=2160, texts=((200, 300, FILLER, 12), (900, 900, "AHU-1 ON ROOF", 12),
                                            (2640, 1860, "ROOF PLAN", 20), (2800, 2000, "M-101", 40)))
NO_NUMBER = Page(width=3024, height=2160, texts=((200, 300, FILLER, 12),))
SPEC = Page(texts=((72, 72, "SECTION 23 09 23 - INSTRUMENTATION AND CONTROL FOR HVAC\n"
                            "2.1 SYSTEM\nA. The BMS shall be built on the Tridium Niagara 4 Framework.\n23 09 23 - 1", 10),))
SPEC_SHEET = Page(width=3024, height=2160,
                  texts=((200, 300, "PROVIDE DISTECH ALLURE EC-SMART-AIR SERIES CONTROLLERS AND RELAYS.", 12),
                        (2640, 1860, "MECHANICAL SPECIFICATIONS", 20), (2800, 2000, "M-601", 40)))


@pytest.fixture
def job(tmp_path):
    root = tmp_path / "26-9999, 1 Test Street"
    base = root / "2. Takeoffs" / "1. Base Takeoff"
    make_pdf(base / "Mech.pdf", SCHEDULE, PLAN, NO_NUMBER)
    make_pdf(base / "Marked_230923.pdf", SPEC)
    (base / "broken.pdf").write_bytes(b"not a pdf")
    return root


def test_every_stage_runs(job, tmp_path):
    result = catalogue_job(job, tmp_path / "cache")
    assert result.job.name == "26-9999"
    assert [p.status for p in result.pages] == ["text", "text", "text", "text"]
    assert [(s.number, s.title) for s in result.sheets] == [("M-601", "HVAC SCHEDULES"), ("M-101", "ROOF PLAN"), (None, None)]
    assert "Schedules" in result.sheets[0].types and "Plans" in result.sheets[1].types
    assert [(s.number, s.controls) for s in result.sections] == [("23 09 23", True)]
    assert result.bid.finding == "Qualifies"
    [ahu1, ahu2] = result.tags
    assert (ahu1.tag, ahu1.on_schedules, ahu1.elsewhere) == ("AHU-1", ("M-601",), ("M-101",))
    assert ahu2.tag == "AHU-2"


def test_the_flags(job, tmp_path):
    flags = catalogue_job(job, tmp_path / "cache").flags
    assert any("broken.pdf could not be opened" in f for f in flags)
    assert any("Mech.pdf: no sheet number found on 1 of 3 sheets (page 3)" in f for f in flags)


def test_the_summary_is_in_plain_words(job, tmp_path):
    lines = summary_lines(catalogue_job(job, tmp_path / "cache"))
    assert lines[0] == "26-9999 — 3 documents, 4 pages: 0 read by OCR, 0 blank, 0 could not be read."
    assert lines[1].startswith("Bid check: Qualifies — The spec names Niagara N4")


def test_the_summary_has_a_spec_overview_line(job, tmp_path):
    lines = summary_lines(catalogue_job(job, tmp_path / "cache"))
    assert any(line.startswith("Spec overview:") for line in lines)
    line = next(line for line in lines if line.startswith("Spec overview:"))
    assert "manufacturers named" in line and "AME gets prices for" in line and "protocols:" in line


def test_the_catalogue_carries_a_spec_overview(job, tmp_path):
    result = catalogue_job(job, tmp_path / "cache")
    assert any(m.maker == "Tridium / Niagara" for m in result.overview.makers)


def test_the_command_writes_the_evidence_package(job, tmp_path, capsys):
    out = tmp_path / "out"
    assert main(["catalogue", str(job), "--out", str(out), "--workers", "1"]) == 0
    package = out / "26-9999 Evidence Package.xlsx"
    assert openpyxl.load_workbook(package).sheetnames[0] == "Bid check"
    printed = capsys.readouterr().out
    assert "Bid check: Qualifies" in printed and f"Wrote {package}" in printed


def test_a_missing_job_folder_is_plain(tmp_path, capsys):
    assert main(["catalogue", str(tmp_path / "nowhere"), "--out", str(tmp_path / "out")]) == 1
    assert capsys.readouterr().err.strip() == f"Stopped: can't find {tmp_path / 'nowhere'}"


def test_an_addendum_of_drawing_sheets_still_gets_a_sheet_number(tmp_path):
    # I5: a reissued sheet in "Addendum 1.pdf" is a large page, whatever the document's kind.
    root = tmp_path / "26-9999"
    base = root / "2. Takeoffs" / "1. Base Takeoff"
    reissue = Page(width=3024, height=2160, texts=((200, 300, FILLER, 12), (2640, 1860, "REVISED ROOF PLAN", 20),
                                                   (2800, 2000, "M-101", 40)))
    make_pdf(base / "Addendum 1.pdf", reissue)
    result = catalogue_job(root, tmp_path / "cache")
    [sheet] = result.sheets
    assert sheet.number == "M-101" and sheet.document.endswith("Addendum 1.pdf")


def test_a_blank_drawing_sheet_is_flagged(tmp_path):
    root = tmp_path / "26-9999"
    base = root / "2. Takeoffs" / "1. Base Takeoff"
    make_pdf(base / "Mech.pdf", Page(width=3024, height=2160))
    result = catalogue_job(root, tmp_path / "cache")
    assert any("Mech.pdf" in f and "blank drawing page" in f for f in result.flags)


def test_specs_on_a_drawing_sheet_are_found_when_there_is_no_spec_book(tmp_path):
    # C1 / 26-0352: a job with no spec book, whose specifications live on a drawing sheet.
    root = tmp_path / "26-9999"
    base = root / "2. Takeoffs" / "1. Base Takeoff"
    make_pdf(base / "Marked_Mech.pdf", SPEC_SHEET)
    result = catalogue_job(root, tmp_path / "cache")
    assert result.bid.others == ("Distech Controls",)
    assert "No spec book was found among the bid documents" in result.bid.reason
    assert any(m.sheet == "M-601" for m in result.bid.mentions)


def test_non_pdf_files_are_flagged_by_type_and_zip_gets_its_own_advice(tmp_path):
    root = tmp_path / "26-9999"
    base = root / "2. Takeoffs" / "1. Base Takeoff"
    make_pdf(base / "spec.pdf", NO_NUMBER)
    (base / "RFI Responses.xlsx").write_text("not really a workbook")
    (base / "Bid Checklist.xlsx").write_text("not really a workbook")
    (base / "Addendum 2.zip").write_bytes(b"PK\x03\x04")
    result = catalogue_job(root, tmp_path / "cache")
    assert any("2 .xlsx" in f and "1 .zip" in f and "3 files" in f for f in result.flags)
    assert any(f == "2. Takeoffs/1. Base Takeoff/Addendum 2.zip is a zip file — unzip it into the job folder and run again"
              for f in result.flags)


def _sheet(number):
    return Page(width=3024, height=2160, texts=((200, 300, FILLER, 12), (2640, 1860, "ROOF PLAN", 20),
                                                (2800, 2000, number, 40)))


def _plan_with_units(number):
    """A roof plan that shows three units (FINAL-K: a marked-up copy is told by its plans' unit tags)."""
    units = tuple((400 + 300 * k, 900, f"VAV-{k}", 14) for k in (1, 2, 3))
    return Page(width=3024, height=2160, texts=((200, 300, FILLER, 12), *units, (2640, 1860, "ROOF PLAN", 20),
                                                (2800, 2000, number, 40)))


def test_m2_a_marked_up_copy_gets_one_flag_not_one_per_sheet(tmp_path):
    root = tmp_path / "26-9999"
    base = root / "2. Takeoffs" / "1. Base Takeoff"
    numbers = [f"M-10{n}" for n in range(1, 6)]
    make_pdf(base / "Mech.pdf", *[_plan_with_units(n) for n in numbers])
    make_pdf(base / "Marked_Mech.pdf", *[_plan_with_units(n) for n in numbers])
    result = catalogue_job(root, tmp_path / "cache")
    assert any(f == "Marked_Mech.pdf repeats 5 sheets of Mech.pdf — probably a marked-up copy" for f in result.flags)
    assert not [f for f in result.flags if f.startswith("Sheet M-10")]


def test_a_plan_printed_once_per_floor_is_left_to_the_floor_rule_not_flagged_per_sheet(tmp_path):
    """The same plan on several pages of one document is one plan per floor: the reading multiplies what is
    on it, and says so there. Any other sheet on several pages is still flagged."""
    root = tmp_path / "26-9999"
    base = root / "2. Takeoffs" / "1. Base Takeoff"
    details = Page(width=3024, height=2160, texts=((200, 300, FILLER, 12), (2640, 1860, "MECHANICAL DETAILS", 20),
                                                   (2800, 2000, "M-501", 40)))
    make_pdf(base / "Mech.pdf", _sheet("M-113"), _sheet("M-113"), _sheet("M-113"), details, details)
    result = catalogue_job(root, tmp_path / "cache")
    assert repeated_plans(result) == {"M-113": ("2. Takeoffs/1. Base Takeoff/Mech.pdf", (1, 2, 3))}
    assert not [f for f in result.flags if f.startswith("Sheet M-113")]
    assert any(f.startswith("Sheet M-501 is on 2 pages") for f in result.flags)


def test_m4_the_summary_names_controls_scope_not_a_discipline_list(tmp_path):
    root = tmp_path / "26-9999"
    base = root / "2. Takeoffs" / "1. Base Takeoff"
    make_pdf(base / "Mech.pdf", NO_NUMBER)
    make_pdf(base / "Marked_230923.pdf", SPEC)
    lines = summary_lines(catalogue_job(root, tmp_path / "cache"))
    assert any("sheets that carry controls scope not sorted by type" in line for line in lines)


def test_m5_a_password_protected_pdf_says_so(tmp_path):
    import pymupdf
    root = tmp_path / "26-9999"
    base = root / "2. Takeoffs" / "1. Base Takeoff"
    make_pdf(base / "spec.pdf", SPEC)
    locked = pymupdf.open()
    locked.new_page()
    locked.save(str(base / "Locked Addendum.pdf"), encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="secret")
    result = catalogue_job(root, tmp_path / "cache")
    assert any(f == "2. Takeoffs/1. Base Takeoff/Locked Addendum.pdf is password-protected — ask for an unlocked copy"
              for f in result.flags)


def test_a_document_that_fails_partway_is_flagged_in_plain_words(tmp_path, monkeypatch):
    from estimator.catalogue import register
    root = tmp_path / "26-9999"
    base = root / "2. Takeoffs" / "1. Base Takeoff"
    make_pdf(base / "Specs.pdf", Page(texts=((72, 72, "PART 1", 10),)), Page(texts=((72, 72, "PART 2", 10),)))
    real_read_page = register._read_page

    def _flaky(document, number, page):
        if number == 2:
            raise RuntimeError("truncated stream")
        return real_read_page(document, number, page)

    monkeypatch.setattr(register, "_read_page", _flaky)
    result = catalogue_job(root, tmp_path / "cache")
    assert any(f == "Specs.pdf could not be read from page 2 on — truncated stream" for f in result.flags)


def test_a_sheet_whose_title_block_gives_no_title_takes_it_from_the_drawing_index(tmp_path):
    root = tmp_path / "26-9999"
    base = root / "2. Takeoffs" / "1. Base Takeoff"
    lines = ["DRAWING INDEX", "H001", "HVAC LEGEND AND NOTES", "H101", "HVAC NEW WORK FLOOR PLAN",
             "H111", "HVAC NEW WORK ROOF PLAN", "H501", "HVAC DETAILS", "H601", "HVAC SCHEDULES"]
    cover = Page(width=3024, height=2160, texts=tuple((300, 300 + 30 * n, line, 14) for n, line in enumerate(lines))
                 + ((2800, 2000, "G001", 40),))
    # No title in H601's title block that the reader can find: only small labels and the number.
    schedules = Page(width=3024, height=2160, texts=((200, 300, FILLER, 12), (2750, 1900, "Drawing Number:", 8),
                                                     (2800, 2000, "H601", 40)))
    make_pdf(base / "HVAC.pdf", cover, schedules)
    result = catalogue_job(root, tmp_path / "cache")
    sheet = next(s for s in result.sheets if s.number == "H601")
    assert (sheet.title, sheet.title_source, sheet.types) == ("HVAC SCHEDULES", "drawing index", ("Schedules",))


def test_a_sheet_with_no_discipline_takes_it_from_the_document_name(tmp_path):
    # Neither the title nor the sheet number's letters name a discipline, but the file name does.
    root = tmp_path / "26-9999"
    base = root / "2. Takeoffs" / "1. Base Takeoff"
    plan = Page(width=3024, height=2160, texts=((200, 300, FILLER, 12), (2640, 1860, "SOMETHING", 20),
                                                (2800, 2000, "X-1", 40)))
    make_pdf(base / "20260917-PROJ-TFO-M-IFR.pdf", plan)
    result = catalogue_job(root, tmp_path / "cache")
    [sheet] = result.sheets
    assert (sheet.number, sheet.discipline) == ("X-1", "Mechanical")


def test_a_non_drawing_document_is_not_given_a_discipline_by_its_file_name(tmp_path):
    # The document fallback only applies to a drawing set, not a bulletin/addendum (or a spec
    # book) that happens to carry a discipline token in its name.
    root = tmp_path / "26-9999"
    base = root / "2. Takeoffs" / "1. Base Takeoff"
    plan = Page(width=3024, height=2160, texts=((200, 300, FILLER, 12), (2640, 1860, "SOMETHING", 20),
                                                (2800, 2000, "X-1", 40)))
    make_pdf(base / "Addendum 1 - M.pdf", plan)
    result = catalogue_job(root, tmp_path / "cache")
    [sheet] = result.sheets
    assert sheet.discipline == "Unknown"


def test_a_copy_with_the_same_file_name_is_named_by_its_path(tmp_path):
    """LDG-10: "Mech.pdf repeats … of Mech.pdf" says nothing; two documents of one file name are named by their
    paths in the job folder."""
    root = tmp_path / "26-9999"
    base = root / "2. Takeoffs" / "1. Base Takeoff"
    numbers = [f"M-10{n}" for n in range(1, 6)]
    make_pdf(base / "Mech.pdf", *[_plan_with_units(n) for n in numbers])
    make_pdf(base / "Marked" / "Mech.pdf", *[_plan_with_units(n) for n in numbers])
    result = catalogue_job(root, tmp_path / "cache")
    repeats = [f for f in result.flags if " repeats 5 sheets of " in f]
    assert len(repeats) == 1
    assert "2. Takeoffs/1. Base Takeoff/Mech.pdf" in repeats[0]
    assert "2. Takeoffs/1. Base Takeoff/Marked/Mech.pdf" in repeats[0]


def _index(*pairs):
    return Page(texts=((72, 72, "DRAWING INDEX\n" + "\n".join(f"{n} {t}" for n, t in pairs), 10),))


def _untitled(number):
    return Page(width=3024, height=2160, texts=((200, 300, FILLER, 12), (2800, 2000, number, 40)))


def test_each_document_titles_its_sheets_from_its_own_drawing_index(tmp_path):
    # RD-6: two sets with their own indexes, each giving M-101 another title; the title blocks give none
    root = tmp_path / "26-9999"
    base = root / "2. Takeoffs" / "1. Base Takeoff"
    shared = [("M-001", "HVAC LEGEND"), ("M-002", "HVAC NOTES")]
    make_pdf(base / "Building A.pdf", _index(("M-101", "BUILDING A HVAC LEVEL 1 PLAN"),
                                             ("M-601", "BUILDING A HVAC SCHEDULES"), *shared), _untitled("M-101"))
    make_pdf(base / "Building B.pdf", _index(("M-101", "BUILDING B HVAC LEVEL 1 PLAN"), ("M-105", "BUILDING B HVAC ROOF PLAN"),
                                             ("M-601", "BUILDING B HVAC SCHEDULES"), *shared), _untitled("M-101"))
    make_pdf(base / "Loose sheets.pdf", _untitled("M-105"), _untitled("M-601"), _untitled("M-001"))
    result = catalogue_job(root, tmp_path / "cache")
    titles = {(s.document.rsplit("/", 1)[-1], s.number): s.title for s in result.sheets}
    assert titles[("Building A.pdf", "M-101")] == "BUILDING A HVAC LEVEL 1 PLAN"
    assert titles[("Building B.pdf", "M-101")] == "BUILDING B HVAC LEVEL 1 PLAN"
    # a document with no index of its own: a number only one document's index lists takes that title ...
    assert titles[("Loose sheets.pdf", "M-105")] == "BUILDING B HVAC ROOF PLAN"
    # ... one two indexes give one title takes it (a cover sheet reissued with its index) ...
    assert titles[("Loose sheets.pdf", "M-001")] == "HVAC LEGEND"
    # ... and one two indexes give two titles takes neither: nothing says which set it belongs to
    assert titles[("Loose sheets.pdf", "M-601")] not in ("BUILDING A HVAC SCHEDULES", "BUILDING B HVAC SCHEDULES")


def test_one_sheet_written_two_ways_in_two_documents_is_flagged_once(tmp_path):
    # RD-10 (ruling D8): "M-101" and "M101" are one sheet; the flag names it as first printed
    root = tmp_path / "26-9999"
    takeoffs = root / "2. Takeoffs"
    make_pdf(takeoffs / "1. Base Takeoff" / "Mech.pdf", _untitled("M-101"))
    make_pdf(takeoffs / "2. Addendum 1" / "Addendum 1.pdf", _untitled("M101"))
    flags = catalogue_job(root, tmp_path / "cache").flags
    assert [f for f in flags if f.startswith("Sheet ")] == ["Sheet M-101 is on 2 pages (Mech.pdf p.1; Addendum 1.pdf p.1)"]


# --- ruling L1: the words that name a plan's kind (the plan groups) never widen the words that name a sheet ------

def test_the_plan_kind_words_widen_the_plan_groups_vocabulary_and_never_the_supersession_one():
    from types import SimpleNamespace

    from estimator.catalogue.job import GENERIC_PLAN_WORDS, PLAN_DISCIPLINE_WORDS, TRADE_WORDS, title_words

    assert TRADE_WORDS <= PLAN_DISCIPLINE_WORDS and GENERIC_PLAN_WORDS <= PLAN_DISCIPLINE_WORDS
    assert {"ZONING", "AIRFLOW", "BALANCING", "HYDRONIC", "REFRIGERANT"} <= PLAN_DISCIPLINE_WORDS
    assert "ZONING" not in TRADE_WORDS and "AIRFLOW" not in TRADE_WORDS    # `title_words` also names a reissued sheet
    assert "ZONE" not in PLAN_DISCIPLINE_WORDS                              # "ZONE 2" names a part of a floor
    assert not GENERIC_PLAN_WORDS & {"DUCTWORK", "PIPING", "CONTROLS", "ZONING", "PLUMBING"}
    assert title_words(SimpleNamespace(title="LEVEL 4 ZONING PLAN", number="M-301")) == ("LEVEL", "4", "ZONING")
    assert title_words(SimpleNamespace(title="LEVEL 4 DUCTWORK PLAN", number="M-201")) == ("LEVEL", "4")
