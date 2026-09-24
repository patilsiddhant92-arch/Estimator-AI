"""The page register: every page of every bid document, read.

A page is read by its text layer. A page with no text layer but an image on it is read
by OCR. A page with neither is blank. A page that OCR can't read — or every image page,
when OCR isn't set up — is "unreadable", and stays in the register as such: a page is
never dropped because it couldn't be read (design §9.1).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path

import pymupdf

from estimator.catalogue.documents import LARGE_SHEET, Document, JobFolder
from estimator.catalogue.pdf import Span, clean_text, ocr_textpage, tessdata, visual_spans

CACHE_VERSION = 2
MIN_TEXT = 50          # characters: fewer and the page is treated as having no text layer
MIN_OCR_TEXT = 20      # characters OCR must recover for the page to count as read
IMAGE_TEXT = 500       # characters: below this, a page more than half covered by an image is OCR'd too
IMAGE_COVER = 0.5      # share of the page an image must cover for IMAGE_TEXT to apply
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
    large_sheet: bool = False           # its long edge is at least LARGE_SHEET, whatever the document's kind
    edge_spans: tuple[Span, ...] = ()   # large sheets only: the text in the right and bottom fifths
    read_error: str | None = None       # set only on the first page after a document's read broke down


def read_document(document: Document) -> list[PageRecord]:
    """Every page of one document. A failure partway through — a corrupt page, an out-of-memory
    error, a worker killed mid-read — never loses the pages already read, and never stops the
    job: every page from the break onward is registered "unreadable", with a plain-words flag on
    the first of them (design §9.1: recall never depends on the read succeeding)."""
    records: list[PageRecord] = []
    try:
        with pymupdf.open(str(document.path)) as pdf:
            for number, page in enumerate(pdf, start=1):
                records.append(_read_page(document, number, page))
        return records
    except Exception as error:
        return records + _unreadable_from(document, len(records) + 1, error)


def _plain_reason(error: BaseException) -> str:
    text = str(error).strip()
    if isinstance(error, MemoryError) or not text:
        return "the file is too large or too damaged to read"
    return text


def _unreadable_from(document: Document, start: int, error: BaseException) -> list[PageRecord]:
    last = max(document.pages, start)
    return [PageRecord(document.relative, number, "unreadable", "", 0, False, (),
                       _plain_reason(error) if number == start else None)
            for number in range(start, last + 1)]


def _image_covers_half(page: pymupdf.Page) -> bool:
    area = page.rect.width * page.rect.height
    if area <= 0:
        return False
    covered = sum((pymupdf.Rect(info["bbox"]) & page.rect).get_area() for info in page.get_image_info())
    return covered / area > IMAGE_COVER


def _read_page(document: Document, number: int, page: pymupdf.Page) -> PageRecord:
    text = clean_text(page.get_text())
    stripped = text.strip()
    large = max(page.rect.width, page.rect.height) >= LARGE_SHEET
    dpi = 300 if max(page.rect.width, page.rect.height) <= TABLOID else 150
    textpage = None
    status = "text"
    if len(stripped) < MIN_TEXT:
        # A page can carry no text layer at all and still hold real content: CAD sets exported with
        # text drawn as lines (SHX fonts) are common in MEP work, and page.get_drawings() catches them.
        if not (page.get_images() or page.get_drawings()):
            status = "blank"
        else:
            textpage = ocr_textpage(page, dpi)
            if textpage is None:
                status = "unreadable"
            else:
                text = clean_text(page.get_text("text", textpage=textpage))
                status = "ocr" if len(text.strip()) >= MIN_OCR_TEXT else "unreadable"
    elif len(stripped) < IMAGE_TEXT and _image_covers_half(page):
        # A scanned page can carry a thin digital text layer over it (an "ISSUED FOR BID" stamp, a
        # cover sheet's typed title) — read that layer, but OCR the image behind it too.
        textpage = ocr_textpage(page, dpi)
        if textpage is not None:
            ocr_text = clean_text(page.get_text("text", textpage=textpage))
            if len(ocr_text.strip()) >= MIN_OCR_TEXT:
                text, status = f"{text}\n{ocr_text}".strip(), "ocr"
    if len(text.strip()) < 200 and _BLANK.search(text):
        status = "blank"
    edge = ()
    if large and status in ("text", "ocr"):
        edge = tuple(s for s in visual_spans(page, textpage) if s.x0 >= EDGE or s.y0 >= EDGE)
    return PageRecord(document.relative, number, status, text, page.rotation, large, edge)


def register_job(job: JobFolder, cache_dir: Path | None = None, workers: int = 1) -> list[PageRecord]:
    """Every page of the job's documents, in document order. Duplicates and unreadable documents
    aren't read — the job stage reports them."""
    documents = [d for d in job.documents if d.duplicate_of is None and d.kind not in ("unreadable", "password")]
    found: dict[str, list[PageRecord]] = {}
    to_read: list[tuple[Document, Path | None]] = []
    for document in documents:
        cache_file = _cache_file(cache_dir, document) if cache_dir is not None else None
        cached = _load(cache_file) if cache_file is not None and cache_file.exists() else None
        if cached is not None:
            found[document.relative] = cached
        else:
            to_read.append((document, cache_file))
    if workers > 1 and len(to_read) > 1:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(read_document, document): (document, cache_file) for document, cache_file in to_read}
            for future in as_completed(futures):
                document, cache_file = futures[future]
                try:
                    records = future.result()
                except BaseException as error:  # a worker killed mid-read (BrokenProcessPool) or similar
                    records = _unreadable_from(document, 1, error)
                _store(found, document, cache_file, records)
    else:
        for document, cache_file in to_read:
            try:
                records = read_document(document)
            except BaseException as error:  # read_document guards its own errors; this is a last resort
                records = _unreadable_from(document, 1, error)
            _store(found, document, cache_file, records)
    return [record for document in documents for record in found[document.relative]]


def _store(found: dict[str, list[PageRecord]], document: Document, cache_file: Path | None,
           records: list[PageRecord]) -> None:
    found[document.relative] = records
    # Never cache a document some of whose pages failed to read: the failure may be transient
    # (a busy machine, a killed worker), and the next run should try reading it again.
    if cache_file is not None and not any(r.read_error for r in records):
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache_file.with_name(cache_file.name + ".tmp")
        tmp.write_text(json.dumps([asdict(r) for r in records]), encoding="utf-8")
        os.replace(tmp, cache_file)


def _cache_file(cache_dir: Path, document: Document) -> Path:
    stat = document.path.stat()
    # Whether OCR is set up is part of the key: a page unreadable for lack of OCR must be read
    # again, not kept stale, once Tesseract is installed (I4).
    key = (f"{CACHE_VERSION}|{document.relative}|{document.kind}|{stat.st_size}|{stat.st_mtime_ns}"
           f"|ocr={tessdata() is not None}")
    return Path(cache_dir) / f"{hashlib.sha1(key.encode()).hexdigest()}.json"


def _load(cache_file: Path) -> list[PageRecord] | None:
    """None when the cache file is missing, or won't parse — a truncated write from an
    interrupted run is ignored, not fatal: the document is simply read again."""
    try:
        raw_records = json.loads(cache_file.read_text(encoding="utf-8"))
        return [PageRecord(**{**raw, "edge_spans": tuple(Span(**s) for s in raw["edge_spans"])}) for raw in raw_records]
    except (OSError, ValueError, TypeError, KeyError):
        return None
