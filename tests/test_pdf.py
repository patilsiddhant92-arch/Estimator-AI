import pymupdf
import pytest

from estimator.catalogue.pdf import clean_text, ocr_textpage, tessdata, visual_spans
from pdfs import Page, make_pdf


def test_control_characters_used_as_spaces_become_spaces():
    assert clean_text("New\x04Construction\xa0of\x04the") == "New Construction of the"
    assert clean_text("230500\x04-\x041") == "230500 - 1"
    assert clean_text("line one\nline two\tend") == "line one\nline two\tend"


def test_a_span_on_an_unrotated_sheet(tmp_path):
    path = make_pdf(tmp_path / "a.pdf", Page(width=3024, height=2160, texts=((2800, 2000, "M001.00", 40),)))
    with pymupdf.open(path) as pdf:
        [span] = visual_spans(pdf[0])
    assert span.text == "M001.00" and span.size == 40
    assert 0.92 < span.x0 < 0.93 and 0.90 < span.y0 < 0.92


def test_a_span_on_a_rotated_sheet_is_placed_as_the_sheet_is_viewed(tmp_path):
    # Drawn at the top-right of the portrait page, then the page is turned 90°: viewed, it sits bottom-right.
    path = make_pdf(tmp_path / "r.pdf", Page(width=2160, height=3024, texts=((1900, 150, "M006.00", 40),), rotation=90))
    with pymupdf.open(path) as pdf:
        page = pdf[0]
        assert (page.rect.width, page.rect.height) == (3024, 2160)
        [span] = visual_spans(page)
    assert 0.94 < span.x0 < 0.95 and 0.87 < span.y0 < 0.89


def test_blank_text_is_left_out(tmp_path):
    path = make_pdf(tmp_path / "b.pdf", Page(texts=((72, 72, "   ", 12), (72, 100, "EF-1", 12))))
    with pymupdf.open(path) as pdf:
        assert [s.text for s in visual_spans(pdf[0])] == ["EF-1"]


@pytest.mark.skipif(tessdata() is None, reason="Tesseract's tessdata folder isn't on this computer")
def test_ocr_reads_a_page_that_is_only_an_image(tmp_path):
    path = make_pdf(tmp_path / "s.pdf", Page(scanned="EXHAUST FAN SCHEDULE"))
    with pymupdf.open(path) as pdf:
        page = pdf[0]
        assert page.get_text().strip() == ""
        textpage = ocr_textpage(page)
        assert "EXHAUST FAN SCHEDULE" in page.get_text("text", textpage=textpage)
        assert "EXHAUST" in [s.text for s in visual_spans(page, textpage)]


def test_no_ocr_without_tessdata(tmp_path, monkeypatch):
    monkeypatch.setenv("ESTIMATOR_TESSDATA", str(tmp_path / "nowhere"))
    assert tessdata() is None
    path = make_pdf(tmp_path / "s.pdf", Page(scanned="X"))
    with pymupdf.open(path) as pdf:
        assert ocr_textpage(pdf[0]) is None
