"""The whole reading of a job, wired together (build step 4, Task 6)."""
from pathlib import Path

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


def test_a_plan_printed_once_per_floor_multiplies_its_devices_and_says_so(tmp_path):
    root = tmp_path / "26-9999, 1 Test Street"
    make_pdf(root / "2. Takeoffs" / "1. Base Takeoff" / "Mech.pdf", _schedule_sheet(), PLAN, PLAN, PLAN)
    catalogue = catalogue_job(root, tmp_path / "cache")
    assert not [f for f in catalogue.flags if f.startswith("Sheet M-201")]
    reading = read_job(catalogue)
    assert {(d.label, d.total) for d in reading.devices} == {("T", 6), ("OCC", 3)}
    [typical] = reading.typicals
    assert typical.note in reading.flags and "multiplied by 3" in typical.note


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


# ---- review fixes: governing pages, a bad page, the cache key ----------------------------------

def test_a_sheet_in_the_base_set_and_an_addendum_is_read_once(job, tmp_path):
    """The addendum reissues M-201 and M-601; the devices and schedules are read from it alone."""
    addendum = job / "2. Takeoffs" / "2. Addendum 1"
    make_pdf(addendum / "Addendum 1 Mech.pdf", _schedule_sheet(), PLAN)
    catalogue = catalogue_job(job, tmp_path / "cache")
    reading = read_job(catalogue)
    assert {(d.label, d.total) for d in reading.devices} == {("T", 2), ("OCC", 1)}
    assert [(t.prefix, t.scheduled) for t in reading.totals] == [("VAV", 3)]
    assert len(reading.schedules) == 1
    assert sum(1 for n in reading.notes if "STATIC PRESSURE SENSOR" in n.text) == 1


def test_one_page_that_cannot_be_read_never_stops_the_run(job, tmp_path):
    catalogue = catalogue_job(job, tmp_path / "cache")
    real = pymupdf.open(str(job / "2. Takeoffs" / "1. Base Takeoff" / "Mech.pdf"))

    def flaky(document, page):
        if page == 1:
            raise RuntimeError("broken page")
        return real[page - 1]

    reading = read_job(catalogue, page_opener=flaky)
    real.close()
    assert reading.schedules == ()
    assert {(d.label, d.total) for d in reading.devices} == {("T", 2), ("OCC", 1)}
    assert "M-601 (Mech.pdf page 1) could not be read for schedules — broken page; check it by hand" in reading.flags


def test_a_document_that_will_not_open_is_flagged_not_raised(job, tmp_path):
    from estimator.reading.pages import PageOpener

    catalogue = catalogue_job(job, tmp_path / "cache")
    opener = PageOpener(catalogue)
    opener._paths = {name: tmp_path / "gone.pdf" for name in opener._paths}
    reading = read_job(catalogue, page_opener=opener)
    assert reading.devices == () and reading.schedules == ()
    assert any(f.startswith("M-601 (Mech.pdf page 1) could not be read for schedules — the document would not open")
               for f in reading.flags)


def test_the_cache_file_names_carry_the_pymupdf_version(job, tmp_path):
    cache = tmp_path / "cache"
    read_job(catalogue_job(job, cache), cache_dir=cache)
    names = [p.name for p in cache.glob("reading-v*.json")]
    assert names and all(f"-pymupdf{pymupdf.VersionBind}-" in n for n in names)
    assert not list(cache.glob("*.tmp"))


def test_a_cache_file_is_written_under_a_name_no_other_run_uses(tmp_path, monkeypatch):
    import os

    from estimator.reading import pages

    moved = []
    real_replace = os.replace
    monkeypatch.setattr(pages.os, "replace", lambda src, dst: moved.append(Path(src).name) or real_replace(src, dst))
    pages._store(tmp_path / "x.json", {"shape": {}, "data": 1})
    pages._store(tmp_path / "x.json", {"shape": {}, "data": 2})
    assert len(set(moved)) == 2 and all(f".{os.getpid()}-" in name and name.endswith(".tmp") for name in moved)


# ---- a passing failure: a busy machine, a locked file, never a schedule lost --------------------

def _unreadable(reading) -> list[str]:
    return [f for f in reading.flags if "could not be read" in f]


def test_a_page_that_failed_once_is_not_kept_failed_in_the_cache(job, tmp_path, monkeypatch):
    """A page whose tables raised on one run is flagged on that run, and read in full on the next:
    the cache never holds the failure."""
    cache = tmp_path / "cache"
    catalogue = catalogue_job(job, cache)
    whole = read_job(catalogue)
    real = pymupdf.Page.find_tables
    calls = []

    def once(page, *args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("a passing failure")
        return real(page, *args, **kwargs)

    monkeypatch.setattr(pymupdf.Page, "find_tables", once)
    broken = read_job(catalogue, cache_dir=cache)
    assert broken.schedules == () and _unreadable(broken)
    monkeypatch.setattr(pymupdf.Page, "find_tables", real)
    assert read_job(catalogue, cache_dir=cache) == whole


def test_a_cache_file_that_cannot_be_written_never_loses_the_page(job, tmp_path, monkeypatch):
    """Moving a cache file into place can fail on Windows while a virus scanner holds the old one:
    the page was read, so it is used; the cache is simply not kept this time."""
    import os

    from estimator.reading import pages

    cache = tmp_path / "cache"
    catalogue = catalogue_job(job, cache)
    whole = read_job(catalogue)
    real_replace = os.replace

    def locked(src, dst):
        if "reading-v" in Path(dst).name:
            raise PermissionError(13, "The process cannot access the file because it is being used by another process")
        return real_replace(src, dst)

    monkeypatch.setattr(pages, "RETRY_PAUSE", 0)
    monkeypatch.setattr(pages.os, "replace", locked)
    reading = read_job(catalogue, cache_dir=cache)
    assert reading == whole and not _unreadable(reading)
    assert not list(cache.glob("reading-v*"))


def test_a_document_locked_for_a_moment_is_opened_on_a_retry(job, tmp_path, monkeypatch):
    """A PDF another program holds for a moment won't open (pymupdf says FileDataError); it is tried
    again after a short pause, and read in full, not flagged as unreadable for the whole run."""
    from estimator.reading import pages

    catalogue = catalogue_job(job, tmp_path / "cache")
    whole = read_job(catalogue)
    real_open = pymupdf.open
    calls = []

    def busy(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise pymupdf.FileDataError("Failed to open file as type pdf.")
        return real_open(*args, **kwargs)

    monkeypatch.setattr(pages, "RETRY_PAUSE", 0)
    monkeypatch.setattr(pymupdf, "open", busy)
    reading = read_job(catalogue, cache_dir=tmp_path / "pages")
    assert reading == whole and not _unreadable(reading)


def test_a_document_still_locked_after_the_retries_is_flagged(job, tmp_path, monkeypatch):
    from estimator.reading import pages

    catalogue = catalogue_job(job, tmp_path / "cache")

    def busy(*args, **kwargs):
        raise pymupdf.FileDataError("Failed to open file as type pdf.")

    monkeypatch.setattr(pages, "RETRY_PAUSE", 0)
    monkeypatch.setattr(pymupdf, "open", busy)
    reading = read_job(catalogue, cache_dir=tmp_path / "pages")
    assert reading.schedules == ()
    assert any(f.startswith("M-601 (Mech.pdf page 1) could not be read for schedules — the document would not open")
               for f in reading.flags)


def test_a_document_hashed_while_locked_for_a_moment_is_hashed_on_a_retry(job, tmp_path, monkeypatch):
    from estimator.reading import pages

    catalogue = catalogue_job(job, tmp_path / "cache")
    whole = read_job(catalogue)
    real_digest = pages.hashlib.file_digest
    calls = []

    def busy(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise PermissionError(13, "Permission denied")
        return real_digest(*args, **kwargs)

    monkeypatch.setattr(pages, "RETRY_PAUSE", 0)
    monkeypatch.setattr(pages.hashlib, "file_digest", busy)
    reading = read_job(catalogue, cache_dir=tmp_path / "pages")
    assert reading == whole and not _unreadable(reading)
