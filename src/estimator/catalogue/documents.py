"""The bid documents in a job folder: what each one is, and which revision it belongs to.

Only the bid documents are catalogued — the drawings, specs, addenda, RFIs and anything
else the owner issued. AME's own folders (the proposal, the price workup, vendor quotes)
and folders left behind by earlier tools are left out, each with a note, and so is a
second job's folder stored inside this one.
"""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from estimator.catalogue.pdf import clean_text

KINDS = ("drawings", "specs", "addendum", "rfi", "other", "unreadable")
LARGE_SHEET = 1500   # points: the long edge of every drawing sheet in the Learn jobs is at least this

_LEFT_OUT = re.compile(
    r"^(?:\d+\.\s*)?(proposal|price workup|electrical|vendor.*|trace_logs|00_stage0_artifacts|04_deliverable)$", re.I)
_JOB_FOLDER = re.compile(r"^\d{2}-\d{4}\b")
_DOCUMENTS_FOLDER = re.compile(r"^(?:\d+\.\s*)?(takeoffs|project documents)$", re.I)
_NUMBERED = re.compile(r"^\d+\.\s*(.+)$")
_ADDENDUM = re.compile(r"addend|bulletin", re.I)
_RFI = re.compile(r"(?<![a-z])rfi(?![a-z])", re.I)
_SPEC_NAME = re.compile(r"spec|manual|(?<!\d)\d{5}(?!\d)|(?<!\d)\d{2}[-_ ]\d{2}[-_ ]\d{2}(?!\d)", re.I)
_SPEC_TEXT = re.compile(r"\bSECTION\s+(?:\d{2}\s?\d{2}\s?\d{2}|\d{5})\b|END\s+OF\s+SECTION", re.I)
_MEGABYTE = 1 << 20


@dataclass(frozen=True)
class Document:
    path: Path
    relative: str               # the path inside the job folder, with "/" between folders
    kind: str                   # one of KINDS
    revision: str               # "base", or the revision folder's own name ("A", "IFC")
    pages: int
    duplicate_of: str | None = None


@dataclass(frozen=True)
class JobFolder:
    name: str
    root: Path
    documents: tuple[Document, ...]
    notes: tuple[str, ...]              # in plain words, for the flags: another job's folder found inside this one
    left_out: tuple[str, ...] = ()      # AME's own folders that were skipped, for the Documents tab


def job_name(root: Path) -> str:
    return Path(root).name.split(",")[0].strip()


def find_documents(root: Path) -> JobFolder:
    root = Path(root)
    if not root.is_dir():
        raise FileNotFoundError(2, "No such folder", str(root))
    paths, notes, left_out = [], [], []
    for folder, subfolders, files in os.walk(root):
        here = Path(folder)
        kept = []
        for name in sorted(subfolders):
            if _JOB_FOLDER.match(name):
                notes.append(f"{name} is another job's folder inside this one — catalogue it on its own")
            elif _LEFT_OUT.match(name):
                left_out.append((here / name).relative_to(root).as_posix())
            else:
                kept.append(name)
        subfolders[:] = kept
        paths += [here / name for name in files if name.lower().endswith(".pdf")]
    paths.sort(key=lambda p: p.relative_to(root).as_posix())
    seen: dict[tuple, str] = {}
    documents = tuple(_describe(root, path, seen) for path in paths)
    return JobFolder(job_name(root), root, documents, tuple(notes), tuple(left_out))


def _describe(root: Path, path: Path, seen: dict[tuple, str]) -> Document:
    relative = path.relative_to(root).as_posix()
    revision = _revision(path.relative_to(root).parts)
    first = seen.setdefault(_fingerprint(path), relative)
    duplicate_of = None if first == relative else first
    try:
        with pymupdf.open(str(path)) as pdf:
            return Document(path, relative, _kind(path.name, pdf), revision, pdf.page_count, duplicate_of)
    except (pymupdf.FileDataError, RuntimeError, ValueError):
        return Document(path, relative, "unreadable", revision, 0, duplicate_of)


def _kind(name: str, pdf: pymupdf.Document) -> str:
    if _ADDENDUM.search(name):
        return "addendum"
    if _RFI.search(name):
        return "rfi"
    if pdf.page_count and max(pdf[0].rect.width, pdf[0].rect.height) >= LARGE_SHEET:
        return "drawings"
    if _SPEC_NAME.search(name):
        return "specs"
    first_pages = " ".join(clean_text(pdf[i].get_text()) for i in range(min(5, pdf.page_count)))
    return "specs" if _SPEC_TEXT.search(first_pages) else "other"


def _revision(parts: tuple[str, ...]) -> str:
    """The revision folder is the one directly under "Takeoffs" or "Project Documents"."""
    for index, part in enumerate(parts[:-2]):
        if _DOCUMENTS_FOLDER.match(part):
            label = parts[index + 1]
            numbered = _NUMBERED.match(label)
            label = numbered.group(1) if numbered else label
            return "base" if "base" in label.lower() else label
    return "base"


def _fingerprint(path: Path) -> tuple:
    size = path.stat().st_size
    digest = hashlib.sha1()
    with path.open("rb") as handle:
        digest.update(handle.read(_MEGABYTE))
        if size > _MEGABYTE:
            handle.seek(max(size - _MEGABYTE, _MEGABYTE))
            digest.update(handle.read(_MEGABYTE))
    return size, digest.hexdigest()
