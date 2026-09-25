"""Small PDFs built on the fly, so the tests never need a real job's documents."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pymupdf

# Enough text (over 50 characters) that a test sheet isn't taken for a blank page.
FILLER = "GENERAL NOTES: ALL DUCTWORK SHALL BE SUPPORTED FROM THE STRUCTURE ABOVE."


@dataclass(frozen=True)
class Page:
    width: float = 612
    height: float = 792
    texts: tuple[tuple[float, float, str, float], ...] = ()   # (x, y, text, font size), in the page's own coordinates
    rotation: int = 0                                          # applied after the text is placed
    scanned: str | None = None                                 # text drawn into an image only — no text layer
    scan_dpi: int = 150
    lines: tuple[tuple[float, float, float, float], ...] = ()  # (x0, y0, x1, y1) vector line segments, no text
    picture: tuple[float, float, float, float, str] | None = None   # (x0, y0, x1, y1, text): text drawn into an
                                                                    # image placed there, beside the text layer


def make_pdf(path: Path, *pages: Page) -> Path:
    doc = pymupdf.open()
    for spec in pages:
        page = doc.new_page(width=spec.width, height=spec.height)
        for x, y, text, size in spec.texts:
            page.insert_text((x, y), text, fontsize=size)
        for x0, y0, x1, y1 in spec.lines:
            page.draw_line((x0, y0), (x1, y1))
        if spec.scanned:
            source = pymupdf.open()
            drawn = source.new_page(width=spec.width, height=spec.height)
            drawn.insert_text((72, 200), spec.scanned, fontsize=36)
            page.insert_image(page.rect, pixmap=drawn.get_pixmap(dpi=spec.scan_dpi))
        if spec.picture:
            x0, y0, x1, y1, text = spec.picture
            source = pymupdf.open()
            drawn = source.new_page(width=x1 - x0, height=y1 - y0)
            for n, line in enumerate(text.splitlines()):
                drawn.insert_text((20, 40 + 30 * n), line, fontsize=20)
            page.insert_image(pymupdf.Rect(x0, y0, x1, y1), pixmap=drawn.get_pixmap(dpi=200))
        if spec.rotation:
            page.set_rotation(spec.rotation)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(path))
    return path
