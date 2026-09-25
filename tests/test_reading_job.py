"""The whole reading of a job, wired together (build step 4, Task 6)."""
import pymupdf
import pytest

from estimator.catalogue.job import catalogue_job
from estimator.reading.job import JobReading, read_job, reading_lines
from pdfs import FILLER, Page, make_pdf
from test_schedules import grid

W, H = 3024, 2160
VAV_ROWS = [["VAV BOX SCHEDULE", "", "", ""],
            ["TAG", "SERVES", "MAX CFM", "MANUFACTURER"],
            ["VAV-1", "OFFICE 101", "600", "TITUS"],
            ["VAV-2", "OFFICE 102", "700", "TITUS"],
            ["VAV-3", "OFFICE 103", "500", "TITUS"]]


def _schedule_sheet() -> Page:
    lines, texts = grid(300, 300, [90, 120, 70, 100], VAV_ROWS)
    return Page(W, H, ((200, 200, FILLER, 12), *texts,
                       (300, 420, "1. DIGITAL CONTROLS FURNISHED BY TEMPERATURE CONTROL CONTRACTOR.", 8),
                       (2640, 1860, "HVAC SCHEDULES", 20), (2800, 2000, "M-601", 40)), lines=lines)


PLAN = Page(W, H, ((200, 300, FILLER, 12), (900, 900, "VAV-1", 12), (1000, 900, "T", 12),
                   (900, 1000, "VAV-2", 12), (1000, 1000, "T", 12), (1100, 1000, "OCC", 12),
                   (200, 400, "KEY NOTES:", 12), (200, 420, "1. PROVIDE SPACE STATIC PRESSURE SENSOR.", 12),
                   (2640, 1860, "SECOND FLOOR PLAN", 20), (2800, 2000, "M-201", 40)))
SEQUENCE = Page(texts=((72, 72, "SECTION 23 09 93 - SEQUENCE OF OPERATIONS\nA. The AHU shall start.\n23 09 93 - 1", 10),))


@pytest.fixture
def job(tmp_path):
    root = tmp_path / "26-9999, 1 Test Street"
    base = root / "2. Takeoffs" / "1. Base Takeoff"
    make_pdf(base / "Mech.pdf", _schedule_sheet(), PLAN)
    make_pdf(base / "230993.pdf", SEQUENCE)
    return root


def test_the_job_is_read_end_to_end(job, tmp_path):
    catalogue = catalogue_job(job, tmp_path / "cache")
    reading = read_job(catalogue)
    assert isinstance(reading, JobReading)
    assert [(t.prefix, t.scheduled) for t in reading.totals] == [("VAV", 3)]
    categories = {i.tag: i.category for i in reading.inventory}
    assert categories == {"VAV-1": "CONFIRMED", "VAV-2": "CONFIRMED", "VAV-3": "MISSING"}
    assert {(d.label, d.total) for d in reading.devices} == {("T", 2), ("OCC", 1)}
    assert any(n.controls and "STATIC PRESSURE SENSOR" in n.text for n in reading.notes)
    assert [b.what for b in reading.backbone] == ["Sequence of operation"]
    assert "No points list found — the sequence is not cross-checked" in reading.flags


def test_the_reading_lines_are_plain(job, tmp_path):
    lines = reading_lines(read_job(catalogue_job(job, tmp_path / "cache")))
    assert lines[0] == "Equipment: 3 units on the schedules (VAV 3), from 1 schedule; to look at: MISSING 1."
    assert lines[1].startswith("Devices on the plans: T 2, OCC 1;")
    assert any(line.startswith("Sequence and points list — sequence of operation: 23 09 93 SEQUENCE OF OPERATIONS")
               and line.endswith("points list: none found.") for line in lines)


def test_a_second_read_uses_the_cache_and_opens_no_pdf(job, tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    catalogue = catalogue_job(job, cache)
    first = read_job(catalogue, cache_dir=cache)
    assert list(cache.glob("reading-v*-tables.json")) and list(cache.glob("reading-v*-words.json"))

    def refuse(*args, **kwargs):
        raise AssertionError("a PDF page was read again on the second run")

    monkeypatch.setattr(pymupdf.Page, "find_tables", refuse)
    monkeypatch.setattr(pymupdf.Page, "get_text", refuse)
    monkeypatch.setattr(pymupdf, "open", refuse)
    assert read_job(catalogue, cache_dir=cache) == first


def test_a_cache_file_cut_short_is_read_again(job, tmp_path):
    cache = tmp_path / "cache"
    catalogue = catalogue_job(job, cache)
    first = read_job(catalogue, cache_dir=cache)
    for path in cache.glob("reading-v*.json"):
        path.write_text('{"shape": ', encoding="utf-8")
    assert read_job(catalogue, cache_dir=cache) == first
