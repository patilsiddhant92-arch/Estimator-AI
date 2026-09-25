"""Reading a PDF page: clean text, where each piece of it sits as the sheet is viewed, and OCR.

PDF text coordinates are those of the page before any rotation; a drawing sheet is very
often stored rotated 90° or 270°. Positions here are always converted to the sheet as a
person sees it, as fractions of its width and height, so "bottom-right" means the same
thing on every sheet.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

import pymupdf

DEFAULT_TESSDATA = Path(r"C:\Program Files\Tesseract-OCR\tessdata")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean_text(text: str) -> str:
    """Some PDF exports use a control character (commonly 0x04) as the space between words;
    turn those, and non-breaking spaces, into plain spaces. Line breaks and tabs are kept."""
    return _CONTROL.sub(" ", text).replace("\xa0", " ")


@dataclass(frozen=True)
class Span:
    text: str
    size: float     # font size in points
    x0: float       # fractions of the sheet as viewed: 0 = left / top, 1 = right / bottom
    y0: float
    x1: float
    y1: float


def visual_spans(page: pymupdf.Page, textpage: pymupdf.TextPage | None = None) -> list[Span]:
    """Every run of text on the page, placed as the sheet is viewed."""
    width, height = page.rect.width, page.rect.height
    matrix = page.rotation_matrix
    data = page.get_text("dict", textpage=textpage) if textpage is not None else page.get_text("dict")
    spans = []
    for block in data["blocks"]:
        for line in block.get("lines", ()):
            for span in line["spans"]:
                text = clean_text(span["text"]).strip()
                if not text:
                    continue
                box = pymupdf.Rect(span["bbox"]) * matrix
                spans.append(Span(text, round(span["size"], 2),
                                  box.x0 / width, box.y0 / height, box.x1 / width, box.y1 / height))
    return spans


def tessdata() -> Path | None:
    """Tesseract's language folder, or None when OCR isn't set up on this computer."""
    configured = os.environ.get("ESTIMATOR_TESSDATA")
    folder = Path(configured) if configured else DEFAULT_TESSDATA
    return folder if (folder / "eng.traineddata").exists() else None


def ocr_textpage(page: pymupdf.Page, dpi: int = 300) -> pymupdf.TextPage | None:
    """Read a page that has no text layer by OCR. None when OCR isn't set up."""
    folder = tessdata()
    if folder is None:
        return None
    return page.get_textpage_ocr(language="eng", dpi=dpi, full=True, tessdata=str(folder))


def ocr_images_textpage(page: pymupdf.Page, dpi: int = 300) -> pymupdf.TextPage | None:
    """Read the parts of a page its text layer doesn't cover — the pictures pasted onto a sheet — by OCR,
    keeping the text layer as it is. None when OCR isn't set up.

    pymupdf renders the page with its text taken out and OCRs that, so a picture's words are read
    whole even where the picture was cut into tiles. The textpage it gives is of the page with its
    rotation taken off: use it for the page's words, not their positions."""
    folder = tessdata()
    if folder is None:
        return None
    return page.get_textpage_ocr(language="eng", dpi=dpi, full=False, tessdata=str(folder))
