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


def make_pdf(path: Path, *pages: Page) -> Path:
    doc = pymupdf.open()
    for spec in pages:
        page = doc.new_page(width=spec.width, height=spec.height)
        for x, y, text, size in spec.texts:
            page.insert_text((x, y), text, fontsize=size)
        if spec.scanned:
            source = pymupdf.open()
            drawn = source.new_page(width=spec.width, height=spec.height)
            drawn.insert_text((72, 200), spec.scanned, fontsize=36)
            page.insert_image(page.rect, pixmap=drawn.get_pixmap(dpi=spec.scan_dpi))
        if spec.rotation:
            page.set_rotation(spec.rotation)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(path))
    return path
