from pathlib import Path

import pytest

from estimator.catalogue import register
from estimator.catalogue.documents import find_documents
from estimator.catalogue.pdf import tessdata
from estimator.catalogue.register import read_document, register_job
from pdfs import FILLER, Page, make_pdf

SPEC_TEXT = "PART 1 - GENERAL\n1.1 SUMMARY\nA. This section covers the building management system and its controls."


def _job(tmp_path, *files):
    root = tmp_path / "26-9999"
    for name, pages in files:
        make_pdf(root / "2. Takeoffs" / "1. Base Takeoff" / name, *pages)
    return find_documents(root)


def test_a_page_with_text_is_read_by_its_text(tmp_path):
    job = _job(tmp_path, ("spec.pdf", [Page(texts=((72, 72, SPEC_TEXT, 10),))]))
    [record] = read_document(job.documents[0])
    assert (record.page, record.status, record.edge_spans) == (1, "text", ())
    assert "building management system" in record.text


def test_blank_pages(tmp_path):
    job = _job(tmp_path, ("spec.pdf", [Page(), Page(texts=((72, 72, "This page intentionally left blank.", 12),))]))
    assert [r.status for r in read_document(job.documents[0])] == ["blank", "blank"]


@pytest.mark.skipif(tessdata() is None, reason="Tesseract's tessdata folder isn't on this computer")
def test_a_scanned_page_is_read_by_ocr(tmp_path):
    job = _job(tmp_path, ("scan.pdf", [Page(scanned="HOT WATER PUMP SCHEDULE")]))
    [record] = read_document(job.documents[0])
    assert record.status == "ocr" and "HOT WATER PUMP SCHEDULE" in record.text


def test_a_scanned_page_without_ocr_is_unreadable_not_skipped(tmp_path, monkeypatch):
    monkeypatch.setattr(register, "ocr_textpage", lambda page, dpi=300: None)
    job = _job(tmp_path, ("scan.pdf", [Page(scanned="HOT WATER PUMP SCHEDULE")]))
    [record] = read_document(job.documents[0])
    assert (record.status, record.text.strip()) == ("unreadable", "")


def test_a_vector_only_page_is_ocrd_not_called_blank(tmp_path, monkeypatch):
    # SHX-exported CAD text is drawn as lines, not a text run — get_images() alone misses it.
    calls = []
    monkeypatch.setattr(register, "ocr_textpage", lambda page, dpi=300: calls.append(dpi) or None)
    job = _job(tmp_path, ("drawing.pdf", [Page(lines=((10, 10, 100, 100), (10, 100, 100, 10)))]))
    [record] = read_document(job.documents[0])
    assert calls, "OCR was never attempted on a page with drawn objects and no text"
    assert record.status == "unreadable"


@pytest.mark.skipif(tessdata() is None, reason="Tesseract's tessdata folder isn't on this computer")
def test_a_near_empty_page_of_ruled_lines_is_blank_not_unreadable(tmp_path):
    # N7: a few drawn lines, no image, and OCR genuinely finds nothing — that's blank, not a
    # flag-worthy "could not be read".
    job = _job(tmp_path, ("manual.pdf", [Page(lines=((72, 700, 540, 700),))]))
    [record] = read_document(job.documents[0])
    assert record.status == "blank"


def test_a_page_with_neither_text_images_nor_drawings_is_blank(tmp_path, monkeypatch):
    monkeypatch.setattr(register, "ocr_textpage", lambda page, dpi=300: pytest.fail("OCR should not run"))
    job = _job(tmp_path, ("blank.pdf", [Page()]))
    [record] = read_document(job.documents[0])
    assert record.status == "blank"


@pytest.mark.skipif(tessdata() is None, reason="Tesseract's tessdata folder isn't on this computer")
def test_a_stamped_scan_keeps_the_text_layer_and_adds_the_ocr_text(tmp_path):
    stamp = ("ISSUED FOR BID -- ADDENDUM 3 -- REVISED PER OWNER COMMENTS DATED JANUARY 5 2026 "
             "-- SEE THE ATTACHED NARRATIVE FOR THE FULL SCOPE OF CHANGES")
    job = _job(tmp_path, ("scan.pdf", [Page(texts=((72, 700, stamp, 10),), scanned="HOT WATER PUMP SCHEDULE")]))
    [record] = read_document(job.documents[0])
    assert record.status == "ocr"
    assert "ISSUED FOR BID" in record.text and "HOT WATER PUMP SCHEDULE" in record.text


def test_large_sheet_is_recorded_whatever_the_document_kind(tmp_path):
    cover = Page(texts=((72, 72, "TRANSMITTAL COVER SHEET", 12),))
    sheet = Page(width=3024, height=2160, texts=((200, 300, FILLER, 12), (2800, 2000, "M-101", 40)))
    job = _job(tmp_path, ("Mech Set.pdf", [cover, sheet]))
    records = read_document(job.documents[0])
    assert [r.large_sheet for r in records] == [False, True]
    assert records[1].edge_spans and records[1].edge_spans[0].text == "M-101"


def test_drawings_keep_the_text_at_the_right_and_bottom_edges(tmp_path):
    sheet = Page(width=3024, height=2160, texts=((200, 300, FILLER, 12), (1500, 1000, "SUPPLY AIR DUCT", 12),
                                                 (2800, 2000, "M101", 40)))
    job = _job(tmp_path, ("mech.pdf", [sheet]))
    [record] = read_document(job.documents[0])
    assert [s.text for s in record.edge_spans] == ["M101"]
    assert "SUPPLY AIR DUCT" in record.text


def test_every_page_in_document_order(tmp_path):
    job = _job(tmp_path, ("a spec.pdf", [Page(texts=((72, 72, SPEC_TEXT, 10),))] * 2),
               ("b spec.pdf", [Page(texts=((72, 72, SPEC_TEXT, 10),))]))
    assert [(r.document.rsplit("/", 1)[-1], r.page) for r in register_job(job)] == [
        ("a spec.pdf", 1), ("a spec.pdf", 2), ("b spec.pdf", 1)]


def test_duplicates_and_unreadable_documents_are_not_read(tmp_path):
    job = _job(tmp_path, ("a spec.pdf", [Page(texts=((72, 72, SPEC_TEXT, 10),))]))
    base = job.root / "2. Takeoffs" / "1. Base Takeoff"
    (base / "copy of a spec.pdf").write_bytes((base / "a spec.pdf").read_bytes())
    (base / "broken.pdf").write_bytes(b"not a pdf")
    job = find_documents(job.root)
    assert {r.document.rsplit("/", 1)[-1] for r in register_job(job)} == {"a spec.pdf"}


def test_a_second_run_reads_the_cache_not_the_pdfs(tmp_path, monkeypatch):
    job = _job(tmp_path, ("spec.pdf", [Page(texts=((72, 72, SPEC_TEXT, 10),))]))
    cache = tmp_path / "cache"
    first = register_job(job, cache)
    monkeypatch.setattr(register, "read_document", lambda document: pytest.fail("the PDF was read again"))
    assert register_job(job, cache) == first


def test_the_cache_keeps_edge_spans(tmp_path):
    job = _job(tmp_path, ("mech.pdf", [Page(width=3024, height=2160, texts=((200, 300, FILLER, 12), (2800, 2000, "M101", 40)))]))
    cache = tmp_path / "cache"
    assert register_job(job, cache) == register_job(job, cache)
    assert register_job(job, cache)[0].edge_spans[0].text == "M101"


def test_a_failure_partway_through_a_document_registers_the_rest_as_unreadable(tmp_path, monkeypatch):
    job = _job(tmp_path, ("spec.pdf", [Page(texts=((72, 72, SPEC_TEXT, 10),))] * 3))
    real_read_page = register._read_page

    def _flaky(document, number, page):
        if number == 2:
            raise RuntimeError("page 2 is corrupt")
        return real_read_page(document, number, page)

    monkeypatch.setattr(register, "_read_page", _flaky)
    records = read_document(job.documents[0])
    assert [(r.page, r.status) for r in records] == [(1, "text"), (2, "unreadable"), (3, "unreadable")]
    assert records[1].read_error == "page 2 is corrupt" and records[2].read_error is None


def test_a_document_that_cannot_be_opened_at_all_is_unreadable_start_to_end(tmp_path, monkeypatch):
    job = _job(tmp_path, ("spec.pdf", [Page(texts=((72, 72, SPEC_TEXT, 10),))] * 2))
    monkeypatch.setattr(register.pymupdf, "open", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("cannot open broken document")))
    records = read_document(job.documents[0])
    assert [r.status for r in records] == ["unreadable", "unreadable"]
    assert records[0].read_error == "cannot open broken document"


def test_one_bad_document_does_not_stop_the_others(tmp_path, monkeypatch):
    job = _job(tmp_path, ("bad.pdf", [Page(texts=((72, 72, SPEC_TEXT, 10),))]),
               ("good.pdf", [Page(texts=((72, 72, SPEC_TEXT, 10),))]))
    real_read_document = register.read_document

    def _flaky(document):
        if document.relative.endswith("bad.pdf"):
            raise RuntimeError("out of memory")
        return real_read_document(document)

    monkeypatch.setattr(register, "read_document", _flaky)
    records = register_job(job)
    by_doc = {r.document.rsplit("/", 1)[-1]: r for r in records}
    assert by_doc["good.pdf"].status == "text"
    assert by_doc["bad.pdf"].status == "unreadable" and by_doc["bad.pdf"].read_error == "out of memory"


def test_a_failed_read_is_not_cached(tmp_path, monkeypatch):
    job = _job(tmp_path, ("bad.pdf", [Page(texts=((72, 72, SPEC_TEXT, 10),))]))
    monkeypatch.setattr(register, "read_document", lambda document: register._unreadable_from(document, 1, RuntimeError("boom")))
    cache = tmp_path / "cache"
    register_job(job, cache)
    assert list(cache.glob("*.json")) == []


def test_a_truncated_cache_file_is_ignored_and_the_document_is_read_again(tmp_path):
    job = _job(tmp_path, ("spec.pdf", [Page(texts=((72, 72, SPEC_TEXT, 10),))]))
    cache = tmp_path / "cache"
    first = register_job(job, cache)
    [cache_file] = cache.glob("*.json")
    cache_file.write_text('{"not": "valid json"', encoding="utf-8")
    assert register_job(job, cache) == first
    assert [p for p in cache.glob("*") if p.suffix == ".tmp"] == []


def test_no_temp_files_are_left_behind_after_a_successful_run(tmp_path):
    job = _job(tmp_path, *[(f"{n} spec.pdf", [Page(texts=((72, 72, SPEC_TEXT, 10),))]) for n in range(3)])
    cache = tmp_path / "cache"
    register_job(job, cache, workers=2)
    assert [p for p in cache.iterdir() if p.suffix == ".tmp"] == []
    assert len(list(cache.glob("*.json"))) == 3


def test_a_document_is_read_again_once_ocr_becomes_available(tmp_path, monkeypatch):
    job = _job(tmp_path, ("scan.pdf", [Page(scanned="HOT WATER PUMP SCHEDULE")]))
    cache = tmp_path / "cache"
    monkeypatch.setattr(register, "tessdata", lambda: None)
    register_job(job, cache)
    monkeypatch.setattr(register, "tessdata", lambda: Path(r"C:\fake\tessdata"))
    calls = []
    monkeypatch.setattr(register, "read_document", lambda document: calls.append(document) or [])
    register_job(job, cache)
    assert calls, "OCR becoming available should invalidate the earlier cache entry"


def test_parallel_reading_gives_the_same_register(tmp_path):
    job = _job(tmp_path, *[(f"{n} spec.pdf", [Page(texts=((72, 72, SPEC_TEXT, 10),))]) for n in range(3)])
    assert register_job(job, workers=2) == register_job(job)
