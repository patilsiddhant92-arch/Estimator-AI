"""Opening drawing pages for reading, and keeping what was read from them.

Finding a sheet's tables (`page.find_tables()`) and its words (`page.get_text("words")`) takes
minutes on a big job. Both are kept, page by page, in the cache folder the page register uses,
so a second read of the same job opens no PDF at all. A page's cache file is keyed by its
document's content hash, a version number and the pymupdf version: an edited document, a new
way of reading, or a new pymupdf is read again, never answered from a stale file. Each file is
written whole under a name no other run uses, then moved into place, so an interrupted run
never leaves half a file behind and two runs never write into each other's.

A page that can't be read (a document that won't open, a page pymupdf chokes on) raises; the
readers catch it, skip that page, and say so with `unreadable_page`.

`PageOpener(catalogue, cache_dir)` is called as `opener(document, page)` — the page opener the
schedules and devices readers take. What it returns behaves like a pymupdf page for what they
use: `rect`, `rotation`, `rotation_matrix`, `get_text("words")` and `find_tables().tables`.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pymupdf

CACHE_VERSION = 1     # raise it whenever what is kept, or how it is read, changes
_PYMUPDF = "".join(ch for ch in str(getattr(pymupdf, "VersionBind", "") or getattr(pymupdf, "__version__", ""))
                   if ch.isalnum() or ch == ".") or "unknown"


def unreadable_page(sheet: str | None, document: str, page: int, what: str, error: BaseException) -> str:
    """The flag for one page a reader had to skip, in plain words."""
    name = document.rsplit("/", 1)[-1]
    where = f"{sheet} ({name} page {page})" if sheet else f"{name} page {page}"
    reason = " ".join(str(error).split()) or type(error).__name__
    if len(reason) > 120:
        reason = reason[:119] + "…"
    return f"{where} could not be read for {what} — {reason}; check it by hand"


@dataclass(frozen=True)
class _Row:
    bbox: tuple[float, float, float, float]
    cells: tuple[tuple[float, float, float, float] | None, ...]


@dataclass(frozen=True)
class _Table:
    """A table as `find_tables()` found it: its box, its rows' and cells' boxes, and its cells' text."""
    bbox: tuple[float, float, float, float]
    row_count: int
    col_count: int
    rows: tuple[_Row, ...]
    texts: tuple[tuple[str | None, ...], ...]

    def extract(self) -> list[list[str | None]]:
        return [list(row) for row in self.texts]


def _box(values) -> tuple[float, ...] | None:
    return tuple(float(v) for v in values) if values is not None else None


def _table_data(table) -> dict:
    return {"bbox": list(table.bbox), "row_count": table.row_count, "col_count": table.col_count,
            "texts": table.extract(),
            "rows": [{"bbox": list(row.bbox), "cells": [list(c) if c is not None else None for c in row.cells]}
                     for row in table.rows]}


def _table(data: dict) -> _Table:
    rows = tuple(_Row(_box(r["bbox"]), tuple(_box(c) for c in r["cells"])) for r in data["rows"])
    return _Table(_box(data["bbox"]), int(data["row_count"]), int(data["col_count"]), rows,
                  tuple(tuple(row) for row in data["texts"]))


def _shape_of(page: pymupdf.Page) -> dict:
    return {"rect": list(page.rect), "rotation": page.rotation, "matrix": list(page.rotation_matrix)}


class CachedPage:
    """One page, read from its cache files when they're there, from the PDF (and then kept) when not."""

    def __init__(self, opener: "PageOpener", document: str, page: int):
        self._opener, self._document, self._page = opener, document, page
        self._shape: dict | None = None

    def _real(self) -> pymupdf.Page:
        return self._opener.real_page(self._document, self._page)

    def _part(self, part: str, read) -> object:
        path = self._opener.cache_file(self._document, self._page, part)
        if path is not None:
            cached = _load(path)
            if cached is not None:
                self._shape = self._shape or cached["shape"]
                return cached["data"]
        page = self._real()
        self._shape = _shape_of(page)
        data = read(page)
        if path is not None:
            _store(path, {"shape": self._shape, "data": data})
        return data

    def _get_shape(self) -> dict:
        if self._shape is None:
            for part in ("words", "tables"):
                path = self._opener.cache_file(self._document, self._page, part)
                cached = _load(path) if path is not None else None
                if cached is not None:
                    self._shape = cached["shape"]
                    break
            else:
                self._shape = _shape_of(self._real())
        return self._shape

    @property
    def rect(self) -> pymupdf.Rect:
        return pymupdf.Rect(*self._get_shape()["rect"])

    @property
    def rotation(self) -> int:
        return int(self._get_shape()["rotation"])

    @property
    def rotation_matrix(self) -> pymupdf.Matrix:
        return pymupdf.Matrix(*self._get_shape()["matrix"])

    def get_text(self, option: str = "text", **kwargs):
        if option != "words" or kwargs:
            return self._real().get_text(option, **kwargs)
        words = self._part("words", lambda page: [list(w) for w in page.get_text("words")])
        return [tuple(w) for w in words]

    def find_tables(self, **kwargs):
        if kwargs:
            return self._real().find_tables(**kwargs)
        tables = self._part("tables", lambda page: [_table_data(t) for t in page.find_tables().tables])
        return SimpleNamespace(tables=[_table(t) for t in tables])


class PageOpener:
    """`opener(document, page)` for a catalogued job: each document opened once, and only when a
    page isn't in the cache. With no cache folder, the pages are read straight from the PDFs."""

    def __init__(self, catalogue, cache_dir: Path | None = None):
        self._paths = {d.relative: Path(d.path) for d in catalogue.job.documents}
        self._cache_dir = Path(cache_dir) if cache_dir is not None else None
        self._open: dict[str, pymupdf.Document] = {}
        self._failed: dict[str, str] = {}
        self._digests: dict[str, str] = {}

    def __call__(self, document: str, page: int):
        if self._cache_dir is None:
            return self.real_page(document, page)
        return CachedPage(self, document, page)

    def real_page(self, document: str, page: int) -> pymupdf.Page:
        if document not in self._open:
            if document in self._failed:
                raise RuntimeError(self._failed[document])
            try:
                self._open[document] = pymupdf.open(str(self._paths[document]))
            except Exception as error:
                self._failed[document] = f"the document would not open ({' '.join(str(error).split()) or type(error).__name__})"
                raise RuntimeError(self._failed[document]) from error
        return self._open[document][page - 1]

    def cache_file(self, document: str, page: int, part: str) -> Path | None:
        if self._cache_dir is None:
            return None
        if document not in self._digests:
            with open(self._paths[document], "rb") as handle:
                self._digests[document] = hashlib.file_digest(handle, "sha1").hexdigest()
        return (self._cache_dir
                / f"reading-v{CACHE_VERSION}-pymupdf{_PYMUPDF}-{self._digests[document]}-p{page}-{part}.json")

    def close(self) -> None:
        for pdf in self._open.values():
            pdf.close()
        self._open.clear()

    def __enter__(self) -> "PageOpener":
        return self

    def __exit__(self, *_) -> None:
        self.close()


def _load(path: Path) -> dict | None:
    """None when the file is missing or won't parse (a truncated write): the page is read again."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) and "shape" in data and "data" in data else None
    except (OSError, ValueError):
        return None


def _store(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}-{secrets.token_hex(4)}.tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp, path)
