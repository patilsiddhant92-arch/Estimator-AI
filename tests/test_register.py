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


def test_parallel_reading_gives_the_same_register(tmp_path):
    job = _job(tmp_path, *[(f"{n} spec.pdf", [Page(texts=((72, 72, SPEC_TEXT, 10),))]) for n in range(3)])
    assert register_job(job, workers=2) == register_job(job)
