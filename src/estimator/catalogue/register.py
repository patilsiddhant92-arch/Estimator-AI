"""The page register: every page of every bid document, read.

A page is read by its text layer. A page with no text layer but an image on it is read
by OCR. A page with neither is blank. A page that OCR can't read — or every image page,
when OCR isn't set up — is "unreadable", and stays in the register as such: a page is
never dropped because it couldn't be read (design §9.1).
"""
from __future__ import annotations

import hashlib
import json
import re
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path

import pymupdf

from estimator.catalogue.documents import Document, JobFolder
from estimator.catalogue.pdf import Span, clean_text, ocr_textpage, visual_spans

CACHE_VERSION = 1
MIN_TEXT = 50          # characters: fewer and the page is treated as having no text layer
MIN_OCR_TEXT = 20      # characters OCR must recover for the page to count as read
TABLOID = 1224         # points: pages up to this size are OCR'd at 300 dpi, larger sheets at 150
EDGE = 0.80            # title blocks sit in the right or bottom fifth of a drawing sheet
_BLANK = re.compile(r"intentionally\s+left\s+blank", re.I)


@dataclass(frozen=True)
class PageRecord:
    document: str                       # Document.relative
    page: int                           # counted from 1, as a PDF viewer numbers pages
    status: str                         # "text" | "ocr" | "blank" | "unreadable"
    text: str
    rotation: int
    edge_spans: tuple[Span, ...] = ()   # drawings only: the text in the right and bottom fifths


def read_document(document: Document) -> list[PageRecord]:
    with pymupdf.open(str(document.path)) as pdf:
        return [_read_page(document, number, page) for number, page in enumerate(pdf, start=1)]


def _read_page(document: Document, number: int, page: pymupdf.Page) -> PageRecord:
    text = clean_text(page.get_text())
    textpage = None
    status = "text"
    if len(text.strip()) < MIN_TEXT:
        if not page.get_images():
            status = "blank"
        else:
            dpi = 300 if max(page.rect.width, page.rect.height) <= TABLOID else 150
            textpage = ocr_textpage(page, dpi)
            if textpage is None:
                status = "unreadable"
            else:
                text = clean_text(page.get_text("text", textpage=textpage))
                status = "ocr" if len(text.strip()) >= MIN_OCR_TEXT else "unreadable"
    if len(text.strip()) < 200 and _BLANK.search(text):
        status = "blank"
    edge = ()
    if document.kind == "drawings" and status in ("text", "ocr"):
        edge = tuple(s for s in visual_spans(page, textpage) if s.x0 >= EDGE or s.y0 >= EDGE)
    return PageRecord(document.relative, number, status, text, page.rotation, edge)


def register_job(job: JobFolder, cache_dir: Path | None = None, workers: int = 1) -> list[PageRecord]:
    """Every page of the job's documents, in document order. Duplicates and unreadable documents
    aren't read — the job stage reports them."""
    documents = [d for d in job.documents if d.duplicate_of is None and d.kind != "unreadable"]
    found: dict[str, list[PageRecord]] = {}
    to_read: list[tuple[Document, Path | None]] = []
    for document in documents:
        cache_file = _cache_file(cache_dir, document) if cache_dir is not None else None
        if cache_file is not None and cache_file.exists():
            found[document.relative] = _load(cache_file)
        else:
            to_read.append((document, cache_file))
    if workers > 1 and len(to_read) > 1:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(read_document, [document for document, _ in to_read]))
    else:
        results = [read_document(document) for document, _ in to_read]
    for (document, cache_file), records in zip(to_read, results):
        found[document.relative] = records
        if cache_file is not None:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps([asdict(r) for r in records]), encoding="utf-8")
    return [record for document in documents for record in found[document.relative]]


def _cache_file(cache_dir: Path, document: Document) -> Path:
    stat = document.path.stat()
    key = f"{CACHE_VERSION}|{document.relative}|{document.kind}|{stat.st_size}|{stat.st_mtime_ns}"
    return Path(cache_dir) / f"{hashlib.sha1(key.encode()).hexdigest()}.json"


def _load(cache_file: Path) -> list[PageRecord]:
    return [PageRecord(**{**raw, "edge_spans": tuple(Span(**s) for s in raw["edge_spans"])})
            for raw in json.loads(cache_file.read_text(encoding="utf-8"))]
