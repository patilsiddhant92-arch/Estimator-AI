"""Open a Word or Excel file, refusing in plain words when it isn't one.

python-docx and openpyxl each raise their own low-level exception — a bare
zipfile.BadZipFile, a KeyError for a missing internal part, python-docx's own
PackageNotFoundError — for a file that isn't really a .docx or .xlsx, or is too
damaged to open. None of those are something an estimator should ever see.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

import docx
import openpyxl
from docx.document import Document as DocxDocument
from docx.opc.exceptions import PackageNotFoundError
from openpyxl.workbook import Workbook

_UNREADABLE = (PackageNotFoundError, zipfile.BadZipFile, KeyError)


class UnreadableFileError(ValueError):
    """A file that isn't a real Word or Excel file, or is too damaged to open."""


def open_docx(path: Path) -> DocxDocument:
    if not Path(path).exists():
        raise FileNotFoundError(2, "No such file or directory", str(path))
    try:
        return docx.Document(str(path))
    except _UNREADABLE as error:
        raise UnreadableFileError(f"{path} can't be opened — is it a real Word file?") from error


def open_workbook(path: Path, **kwargs) -> Workbook:
    if not Path(path).exists():
        raise FileNotFoundError(2, "No such file or directory", str(path))
    try:
        return openpyxl.load_workbook(str(path), **kwargs)
    except _UNREADABLE as error:
        raise UnreadableFileError(f"{path} can't be opened — is it a real Excel file?") from error
