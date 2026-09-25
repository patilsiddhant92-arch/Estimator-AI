import importlib.util
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location("learn_check", Path(__file__).resolve().parents[1] / "tools" / "learn_check.py")
learn_check = importlib.util.module_from_spec(_spec)
sys.modules["learn_check"] = learn_check     # a dataclass needs its module registered while it is defined
_spec.loader.exec_module(learn_check)


def _result(**changes):
    base = dict(job="26-9999", pages=10, ocr=0, unreadable=0, sheets=10, numbered=10, relevant=10, typed=9,
                controls_sections=1, bid="Qualifies", others=(), tags=5, blank_sheets=0, unlisted_files=())
    return learn_check.JobResult(**{**base, **changes})


EXPECTED = {"bid": "Qualifies", "sheet_numbers_at_least": 0.99, "typed_at_least": 0.85, "controls_sections": True}


def test_a_job_that_meets_its_expectations():
    assert learn_check.misses(_result(), EXPECTED) == []


def test_each_kind_of_miss_is_said_in_plain_words():
    found = learn_check.misses(_result(bid="Open", numbered=8, typed=5, controls_sections=0),
                               {**EXPECTED, "sheet_numbers_at_least": 0.9})
    assert found == ["bid check said Open, the estimator concluded Qualifies",
                     "sheet numbers found on 80% of drawing sheets, expected at least 90%",
                     "sorted by type on 50% of mechanical, controls and plumbing sheets, expected at least 85%",
                     "no controls section found, and the job has one"]


def test_a_bid_expectation_of_null_is_only_reported():
    assert learn_check.misses(_result(bid="Open"), {**EXPECTED, "bid": None}) == []


def test_a_job_with_no_drawings_is_not_a_sheet_miss():
    assert learn_check.misses(_result(sheets=0, numbered=0, relevant=0, typed=0), EXPECTED) == []


def test_others_include_is_checked():
    assert learn_check.misses(_result(others=("Distech Controls",)),
                              {**EXPECTED, "others_include": ["Distech Controls"]}) == []
    found = learn_check.misses(_result(others=()), {**EXPECTED, "others_include": ["Distech Controls"]})
    assert found == ["Distech Controls was expected among the other manufacturers named, but the check didn't find it"]


def test_others_include_is_optional():
    assert learn_check.misses(_result(), EXPECTED) == []


def test_a_blank_drawing_page_is_a_miss():
    assert learn_check.misses(_result(blank_sheets=2), EXPECTED) == [
        "2 blank drawing pages found — check whether they should have been read"]
    assert learn_check.misses(_result(blank_sheets=0), EXPECTED) == []


def test_finding_a_job_folder_by_its_number(tmp_path):
    (tmp_path / "26-0352, Tishman Speyer, 45 Rockefeller").mkdir()
    nested = tmp_path / "26-0436, Equinix" / "2. Takeoffs" / "1. Base Takeoff" / "26-0437"
    nested.mkdir(parents=True)
    assert learn_check.find_job(tmp_path, "26-0352") == tmp_path / "26-0352, Tishman Speyer, 45 Rockefeller"
    assert learn_check.find_job(tmp_path, "26-0437") == nested


# T3: a non-PDF file the job's own catalogue never accounted for, and too many unreadable pages.

def test_unreadable_at_most_is_checked():
    assert learn_check.misses(_result(unreadable=3), {**EXPECTED, "unreadable_at_most": 5}) == []
    found = learn_check.misses(_result(unreadable=8), {**EXPECTED, "unreadable_at_most": 5})
    assert found == ["8 pages could not be read, expected at most 5"]


def test_unreadable_at_most_is_optional():
    assert learn_check.misses(_result(unreadable=1000), EXPECTED) == []


def test_a_file_missing_from_the_documents_tab_is_a_miss():
    found = learn_check.misses(_result(unlisted_files=("2. Takeoffs/notes.xlsx",)), EXPECTED)
    assert found == ["1 non-PDF file under the job never reached the Documents tab (2. Takeoffs/notes.xlsx)"]
    assert learn_check.misses(_result(), EXPECTED) == []


def test_missing_from_documents_tab_finds_a_file_find_documents_did_not_account_for(tmp_path):
    from estimator.catalogue.documents import Document, JobFolder
    root = tmp_path / "26-9999"
    (root / "2. Takeoffs").mkdir(parents=True)
    (root / "2. Takeoffs" / "notes.xlsx").write_text("x")
    (root / "2. Takeoffs" / "spec.pdf").write_text("x")
    (root / "3. Proposal").mkdir()
    (root / "3. Proposal" / "quote.docx").write_text("x")
    document = Document(root / "2. Takeoffs" / "spec.pdf", "2. Takeoffs/spec.pdf", "specs", "base", 1)
    job = JobFolder("26-9999", root, (document,), (), ("3. Proposal",), (), ())
    assert learn_check.missing_from_documents_tab(job) == ("2. Takeoffs/notes.xlsx",)


def test_missing_from_documents_tab_is_empty_once_a_file_is_on_it(tmp_path):
    from estimator.catalogue.documents import JobFolder
    root = tmp_path / "26-9999"
    (root / "2. Takeoffs").mkdir(parents=True)
    (root / "2. Takeoffs" / "notes.xlsx").write_text("x")
    job = JobFolder("26-9999", root, (), (), (), (), ("2. Takeoffs/notes.xlsx",))
    assert learn_check.missing_from_documents_tab(job) == ()


# Task 3: the Spec overview table in the Learn check.

def test_overview_makers_include_is_checked():
    assert learn_check.misses(_result(overview_maker_names=("Belimo", "Vaisala")),
                              {**EXPECTED, "overview_makers_include": ["Belimo"]}) == []
    found = learn_check.misses(_result(overview_maker_names=()),
                               {**EXPECTED, "overview_makers_include": ["Belimo"]})
    assert found == ["Belimo was expected among the Spec overview manufacturers, but the check didn't find it"]


def test_overview_makers_include_is_optional():
    assert learn_check.misses(_result(), EXPECTED) == []


def test_measure_reads_the_spec_overview(tmp_path):
    from estimator.catalogue.job import catalogue_job
    from pdfs import make_pdf, Page

    root = tmp_path / "26-9999"
    base = root / "2. Takeoffs" / "1. Base Takeoff"
    spec = Page(texts=((72, 72, "SECTION 23 09 23 - INSTRUMENTATION AND CONTROL FOR HVAC\n"
                                "Actuators shall be Belimo or approved equal. Provide BACnet MS/TP.\n"
                                "23 09 23 - 1", 10),))
    make_pdf(base / "Marked_230923.pdf", spec)
    catalogue = catalogue_job(root, tmp_path / "cache")
    result = learn_check.measure(catalogue)
    assert result.overview_makers >= 1 and "Belimo" in result.overview_maker_names
    assert result.overview_ame >= 1
    assert "BACnet MS/TP" in result.overview_protocols
    assert result.overview_not_found > 0
