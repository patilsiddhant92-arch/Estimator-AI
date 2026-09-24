import importlib.util
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location("learn_check", Path(__file__).resolve().parents[1] / "tools" / "learn_check.py")
learn_check = importlib.util.module_from_spec(_spec)
sys.modules["learn_check"] = learn_check     # a dataclass needs its module registered while it is defined
_spec.loader.exec_module(learn_check)


def _result(**changes):
    base = dict(job="26-9999", pages=10, ocr=0, unreadable=0, sheets=10, numbered=10, relevant=10, typed=9,
                controls_sections=1, bid="Qualifies", others=(), tags=5, blank_sheets=0)
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
