# Build Step 3 — Check the Job Can Be Bid, and Catalogue Every Page — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Point the tool at a job folder and get, in minutes, whether the job can be bid, plus a catalogue of every page. The catalogue covers every document, every page read (by its text, or by OCR where it has none), every drawing sheet's number, title and type, every spec section, and every equipment tag and where it appears. All of it lands in the job's Evidence Package (`.xlsx`).

**Architecture:** A new package, `estimator.catalogue`, reads a job folder in fixed stages:
1. It finds the documents.
2. It registers every page.
3. It reads each drawing's title block.
4. It sorts sheets by type, using a reading list kept as data.
5. It indexes spec sections.
6. It runs the bid check over the spec text.
7. It indexes equipment tags.

Every stage is deterministic: nothing here depends on an AI model. That is the design's "recall never depends on judgement" rule (§9.1). A new writer, `estimator.evidence`, puts the results into the Evidence Package, and `python -m estimator catalogue` runs the whole thing. `tools/learn_check.py` runs it over the nine Learn jobs and compares the results with what an estimator concluded.

**Tech Stack:** Python 3.13.15, `pymupdf` 1.28.2 (moved from the dev extras to a runtime dependency; OCR through its Tesseract binding), `openpyxl` 3.1.5, `pytest` 9.1.1.

**Spec:** `docs/superpowers/specs/2026-09-24-estimator-ai-design.md` — §8 (qualify), §9.1 (recall is deterministic), §9.2 (sheet classification and reading lists), §9.3 (alias resolution), §13 (stack), §14 (build order). Measured facts about the real documents: `docs/superpowers/plans/step-3-facts.md`.

**Decisions made since the design, by the user (2026-09-24):**
- There is no separate scoreboard step. The nine jobs in `D:\Estimation Assistant\Learn` are the benchmark, re-run inside each build step, and nothing is held back.
- Build steps 3–5 are wanted as soon as possible.

## Global Constraints

- **Interpreter:** always `.venv/Scripts/python.exe` (Python 3.13.15), run from the repo root `D:\Estimator AI` in Git Bash. The bare `python` on this machine is another project's 3.14.4 — never use it.
- **Pinned dependencies:** `pydantic==2.13.5`, `python-docx==1.2.0`, `openpyxl==3.1.5`, `pillow==12.3.0`, `lxml==6.1.3`, `pymupdf==1.28.2` (runtime, from Task 1); dev: `pytest==9.1.1`. Do not add others.
- **Read-only folders:** `D:\AME Estimation` and `D:\Estimation Assistant`. Read freely; never write, build or run tests inside them. The Learn check reads the Learn jobs and writes only under `out/learn/`.
- **No job data in the repository:** tests build their own small PDFs with `pymupdf` (see `tests/pdfs.py`, Task 1). No PDF from a job is ever copied into the repo (`.gitignore` already ignores `*.pdf`).
- **OCR:** through `pymupdf`'s `Page.get_textpage_ocr`, with Tesseract's `tessdata` folder at `C:\Program Files\Tesseract-OCR\tessdata` unless the environment variable `ESTIMATOR_TESSDATA` names another. A test that needs OCR skips itself when that folder has no `eng.traineddata`.
- **Clean text before matching:** some PDF exports use control characters (commonly `\x04`) as the space between words. Every piece of PDF text goes through `estimator.catalogue.pdf.clean_text` before any pattern is matched against it.
- **Recall never depends on judgement:** every page of every document is registered. A page that can't be read is reported as a flag, never skipped silently.
- **Reading lists are data, not code:** manufacturer names, equipment prefixes and sheet-type keywords live in `assets/reading_lists/*.json`.
- **The tool reports; the US team decides:** the bid check quotes the spec word for word and names every other controls manufacturer it finds. It never decides to drop a job.
- **Plain language** in everything an estimator reads: the Evidence Package, command-line messages, error messages. Their trade terms (VAV, AHU, riser, keynote, basis of design) are fine; software terms are not.
- **Commit after each task. Never push.** Every commit message ends with a blank line and the implementing model's own `Co-Authored-By:` line.
- **Executors work alone:** they never spawn subagents.

## File map

| File | Responsibility |
|---|---|
| `src/estimator/catalogue/__init__.py` | package marker |
| `src/estimator/catalogue/pdf.py` | clean text; where text sits on the sheet as viewed; OCR |
| `src/estimator/catalogue/documents.py` | the bid documents in a job folder, what each is, which revision |
| `src/estimator/catalogue/register.py` | every page read (text / OCR / blank / unreadable), cached, in parallel |
| `src/estimator/catalogue/title_block.py` | a drawing sheet's number and title |
| `src/estimator/catalogue/sheet_types.py` | sheet discipline and type, from the reading list |
| `src/estimator/catalogue/spec_sections.py` | spec sections and their pages; which are controls sections |
| `src/estimator/catalogue/qualify.py` | the bid check |
| `src/estimator/catalogue/tags.py` | equipment tags, their spellings, and where each appears |
| `src/estimator/catalogue/job.py` | runs every stage for one job; gathers the flags |
| `src/estimator/evidence/__init__.py`, `workbook.py` | the Evidence Package `.xlsx` |
| `src/estimator/__main__.py` | adds the `catalogue` command |
| `assets/reading_lists/manufacturers.json`, `equipment.json`, `sheet_types.json` | the reading lists |
| `tools/learn_check.py`, `tests/data/learn_expectations.json` | the Learn-jobs check |
| `tests/pdfs.py` | builds small test PDFs |

---

### Task 1: Reading PDF pages — clean text, position on the sheet, OCR

**Files:**
- Modify: `pyproject.toml` (move `pymupdf==1.28.2` from `[project.optional-dependencies] dev` into `dependencies`)
- Create: `src/estimator/catalogue/__init__.py`, `src/estimator/catalogue/pdf.py`, `tests/pdfs.py`, `tests/test_pdf.py`

**Interfaces:**
- Produces:
  - `clean_text(text: str) -> str`
  - `Span(text: str, size: float, x0: float, y0: float, x1: float, y1: float)` — frozen dataclass; positions are fractions of the sheet **as viewed** (0 = left/top, 1 = right/bottom).
  - `visual_spans(page: pymupdf.Page, textpage: pymupdf.TextPage | None = None) -> list[Span]`
  - `tessdata() -> Path | None`
  - `ocr_textpage(page: pymupdf.Page, dpi: int = 300) -> pymupdf.TextPage | None`
  - In tests: `tests.pdfs.Page` (dataclass) and `make_pdf(path, *pages) -> Path`

- [ ] **Step 1: Move pymupdf to the runtime dependencies**

In `pyproject.toml`, change the `dependencies` list and the `dev` extra to:
```toml
dependencies = [
  "pydantic==2.13.5",
  "python-docx==1.2.0",
  "openpyxl==3.1.5",
  "pillow==12.3.0",   # openpyxl needs it to keep the logo in the price workup
  "lxml==6.1.3",
  "pymupdf==1.28.2",  # reads the bid documents; AGPL — fine for internal use inside Nordomatic (design §13)
]

[project.optional-dependencies]
dev = ["pytest==9.1.1"]
```
Then run `.venv/Scripts/python.exe -m pip install --no-deps -e .` (nothing new is downloaded — pymupdf is already installed).

- [ ] **Step 2: Write the PDF-building test helper**

`tests/pdfs.py`:
```python
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
```

- [ ] **Step 3: Write the failing tests**

`tests/test_pdf.py`:
```python
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
```

- [ ] **Step 4: Run them to see them fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_pdf.py -v`
Expected: collection error — `ModuleNotFoundError: No module named 'estimator.catalogue'`.

- [ ] **Step 5: Write the code**

`src/estimator/catalogue/__init__.py`:
```python
"""Step 3: check the job can be bid, and catalogue every page."""
```

`src/estimator/catalogue/pdf.py`:
```python
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
```

- [ ] **Step 6: Run the tests to see them pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_pdf.py -v`
Expected: 6 passed. (The OCR test is skipped only on a computer without Tesseract; this one has it.)

- [ ] **Step 7: Run everything, then commit**

Run: `.venv/Scripts/python.exe -m pytest -q` — expected: all pass (207 before this task, 213 after).
```bash
git add -A
git commit -m "feat: read PDF pages — clean text, position as the sheet is viewed, OCR

<your Co-Authored-By line>"
```

---

### Task 2: The bid documents in a job folder

**Files:**
- Create: `src/estimator/catalogue/documents.py`, `tests/test_documents.py`

**Interfaces:**
- Consumes: `clean_text` (Task 1); `tests.pdfs.Page`, `make_pdf`.
- Produces:
  - `KINDS = ("drawings", "specs", "addendum", "rfi", "other", "unreadable")`
  - `Document(path: Path, relative: str, kind: str, revision: str, pages: int, duplicate_of: str | None = None)` — frozen dataclass. `relative` is the path inside the job folder with `/` separators.
  - `JobFolder(name: str, root: Path, documents: tuple[Document, ...], notes: tuple[str, ...], left_out: tuple[str, ...] = ())` — frozen dataclass. `notes` are plain-words flags (another job's folder found inside this one); `left_out` lists AME's own folders that were skipped (relative paths), for the Documents tab.
  - `job_name(root: Path) -> str` — the folder name up to its first comma, e.g. `"26-0352"`.
  - `find_documents(root: Path) -> JobFolder` — raises `FileNotFoundError` if `root` isn't a folder.

The layouts it must handle, measured in `step-3-facts.md` §1:
- The Learn jobs keep their documents under `2. Takeoffs\1. Base Takeoff`. The archive jobs keep theirs under `1. Project Documents\{1. Base Documents, 2. A, 3. A, 2. IFC}`.
- AME's own folders are left out: `3. Proposal`, `5. Price Workup`, `6. Electrical`, `7. Vendor-Sub Quotes`, `Trace_Logs`, and two artefact folders from earlier tools, `00_Stage0_Artifacts` and `04_Deliverable`.
- A folder named like a job number (`26-0437`, found inside 26-0436) is another job's folder. It is left out with a note.
- The document kind is decided in this order:
  1. a name with "addend" or "bulletin" → addendum;
  2. "RFI" as a word → rfi;
  3. page 1's long edge ≥ 1500 points → drawings (every drawing sheet in the Learn jobs measures at least this, and nothing smaller is a drawing);
  4. a name with "spec", "manual", a five-digit section number (`15970`) or a six-digit one written `23-09-00` / `23_09_00` / `23 09 00` → specs;
  5. the first five pages' text contains `SECTION 23 09 23`, `SECTION 15970` or `END OF SECTION` → specs;
  6. otherwise → other.
  A file pymupdf can't open → unreadable.
- The same file stored twice (the same size, with the same first and last megabyte) is catalogued once. The copy points at the first with `duplicate_of`.

- [ ] **Step 1: Write the failing tests**

`tests/test_documents.py`:
```python
import shutil

import pytest

from estimator.catalogue.documents import find_documents, job_name
from pdfs import Page, make_pdf

DRAWING = Page(width=3024, height=2160, texts=((200, 200, "FLOOR PLAN", 20),))
LETTER = Page(texts=((72, 72, "Some words on a page", 12),))


@pytest.fixture
def job(tmp_path):
    root = tmp_path / "26-9999, 1 Test Street"
    base = root / "2. Takeoffs" / "1. Base Takeoff"
    make_pdf(base / "Marked_Mech.pdf", DRAWING)
    make_pdf(base / "Marked_15970.pdf", LETTER)
    make_pdf(base / "Project book.pdf", Page(texts=((72, 72, "SECTION 23 09 23 - INSTRUMENTATION AND CONTROL", 12),)))
    make_pdf(base / "Addendum 1.pdf", LETTER)
    make_pdf(base / "RFI Log for WP-4.pdf", LETTER)
    make_pdf(base / "Bid form.pdf", LETTER)
    make_pdf(base / "Specs" / "23-09-00-Controls.pdf", LETTER)
    make_pdf(root / "2. Takeoffs" / "2. A" / "Mech rev A.pdf", DRAWING)
    make_pdf(root / "3. Proposal" / "1. Base Proposal" / "26-9999.pdf", LETTER)
    make_pdf(root / "5. Price Workup" / "sheet.pdf", LETTER)
    make_pdf(base / "26-9998" / "2. Takeoffs" / "their plan.pdf", DRAWING)
    (base / "copies").mkdir()
    shutil.copy(base / "Marked_Mech.pdf", base / "copies" / "Mech again.pdf")
    (base / "broken.pdf").write_bytes(b"this is not a pdf")
    (base / "notes.txt").write_text("not a pdf")
    return root


def _by_name(folder):
    return {d.relative.rsplit("/", 1)[-1]: d for d in folder.documents}


def test_job_name_is_the_number():
    from pathlib import Path
    assert job_name(Path("D:/x/26-0352, Tishman Speyer, 45 Rockefeller")) == "26-0352"
    assert job_name(Path("D:/x/26-0246")) == "26-0246"


def test_each_document_is_found_with_its_kind(job):
    documents = _by_name(find_documents(job))
    kinds = {name: d.kind for name, d in documents.items()}
    assert kinds == {
        "Marked_Mech.pdf": "drawings", "Marked_15970.pdf": "specs", "Project book.pdf": "specs",
        "Addendum 1.pdf": "addendum", "RFI Log for WP-4.pdf": "rfi", "Bid form.pdf": "other",
        "23-09-00-Controls.pdf": "specs", "Mech rev A.pdf": "drawings", "Mech again.pdf": "drawings",
        "broken.pdf": "unreadable",
    }


def test_revision_comes_from_the_folder_under_takeoffs(job):
    documents = _by_name(find_documents(job))
    assert documents["Marked_Mech.pdf"].revision == "base"
    assert documents["23-09-00-Controls.pdf"].revision == "base"
    assert documents["Mech rev A.pdf"].revision == "A"


def test_relative_paths_and_page_counts(job):
    documents = _by_name(find_documents(job))
    assert documents["Marked_Mech.pdf"].relative == "2. Takeoffs/1. Base Takeoff/Marked_Mech.pdf"
    assert documents["Marked_Mech.pdf"].pages == 1
    assert documents["broken.pdf"].pages == 0


def test_the_same_file_twice_is_catalogued_once(job):
    documents = _by_name(find_documents(job))
    assert documents["Mech again.pdf"].duplicate_of == "2. Takeoffs/1. Base Takeoff/Marked_Mech.pdf"
    assert documents["Marked_Mech.pdf"].duplicate_of is None


def test_ames_own_folders_and_other_jobs_are_left_out_and_listed(job):
    folder = find_documents(job)
    assert folder.name == "26-9999"
    assert not [d for d in folder.documents if "Proposal" in d.relative or "Price Workup" in d.relative]
    assert not [d for d in folder.documents if "26-9998" in d.relative]
    assert folder.notes == ("26-9998 is another job's folder inside this one — catalogue it on its own",)
    assert folder.left_out == ("3. Proposal", "5. Price Workup")


def test_documents_are_listed_in_a_fixed_order(job):
    assert [d.relative for d in find_documents(job).documents] == sorted(d.relative for d in find_documents(job).documents)


def test_a_missing_folder_is_refused(tmp_path):
    with pytest.raises(FileNotFoundError):
        find_documents(tmp_path / "nowhere")
```
Note that `test_documents_are_listed_in_a_fixed_order` expects plain sorted order of the relative paths. `find_documents` returns them sorted that way (see Step 3).

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_documents.py -v`
Expected: collection error — `ModuleNotFoundError: No module named 'estimator.catalogue.documents'`.

- [ ] **Step 3: Write the code**

`src/estimator/catalogue/documents.py`:
```python
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
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_documents.py -v`
Expected: 8 passed.

- [ ] **Step 5: Run everything, then commit**

Run: `.venv/Scripts/python.exe -m pytest -q` — expected: all pass.
```bash
git add -A
git commit -m "feat: find a job's bid documents, what each is, and which revision

<your Co-Authored-By line>"
```

---

### Task 3: The page register — every page read

**Files:**
- Create: `src/estimator/catalogue/register.py`, `tests/test_register.py`

**Interfaces:**
- Consumes: `Document`, `JobFolder` (Task 2); `Span`, `clean_text`, `ocr_textpage`, `visual_spans`, `tessdata` (Task 1).
- Produces:
  - `PageRecord(document: str, page: int, status: str, text: str, rotation: int, edge_spans: tuple[Span, ...] = ())` — frozen dataclass. `page` counts from 1, as a PDF viewer numbers it. `status` is one of:
    - `"text"`: read from its text;
    - `"ocr"`: read by OCR;
    - `"blank"`: a blank page;
    - `"unreadable"`: an image that OCR couldn't read, or OCR isn't set up.
  - `edge_spans` is set only for pages of `drawings` documents. It holds the text in the right and bottom fifths of the sheet, for the title block.
  - `read_document(document: Document) -> list[PageRecord]`
  - `register_job(job: JobFolder, cache_dir: Path | None = None, workers: int = 1) -> list[PageRecord]` — every page of every document, in document order then page order. Duplicates and unreadable documents are skipped (the job stage flags them).

The rules:
- A page with at least 50 characters of text is `text`.
- A page with fewer, and no image, is `blank`.
- A page with fewer and an image is read by OCR, at 300 dpi for pages up to tabloid size (long edge ≤ 1224 points) and at 150 dpi for larger sheets. At 300 dpi an oversized sheet costs about 8 s and several hundred megabytes; title-block sheet numbers are large enough to read at 150.
- An OCR result of at least 20 characters makes the page `ocr`. Otherwise it is `unreadable`, and it is `unreadable` too when OCR isn't set up.
- Any page whose whole text is under 200 characters and says "intentionally left blank" is `blank`.

Results are cached per document in `cache_dir`, one JSON file per document, keyed by its path, size, modification time and a cache version. A second run over an unchanged job reads no PDFs. With `workers > 1`, documents are read in parallel processes.

- [ ] **Step 1: Write the failing tests**

`tests/test_register.py`:
```python
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
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_register.py -v`
Expected: collection error — `ModuleNotFoundError: No module named 'estimator.catalogue.register'`.

- [ ] **Step 3: Write the code**

`src/estimator/catalogue/register.py`:
```python
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
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_register.py -v`
Expected: 10 passed.

- [ ] **Step 5: Run everything, then commit**

Run: `.venv/Scripts/python.exe -m pytest -q` — expected: all pass.
```bash
git add -A
git commit -m "feat: the page register — every page read by its text or OCR, cached, in parallel

<your Co-Authored-By line>"
```

---

### Task 4: A drawing sheet's number and title

**Files:**
- Create: `src/estimator/catalogue/title_block.py`, `tests/test_title_block.py`

**Interfaces:**
- Consumes: `Span` (Task 1); `read_document` (Task 3); `find_documents` (Task 2).
- Produces:
  - `SHEET_NUMBER` — compiled pattern.
  - `TitleBlock(number: str | None, title: str | None)` — frozen dataclass.
  - `read_title_block(spans: Sequence[Span]) -> TitleBlock`

The rule, measured in `step-3-facts.md` §3:
- In every drawing set in the Learn jobs, the title block is a strip along the right edge and/or the bottom edge of the sheet as viewed.
- The sheet number is the largest text there (37–56 pt) that has a sheet number's shape. The shapes seen:
  - `M001.00` and `M-101` (the simple shapes);
  - `M00-03` and `TC00-00` (two-part numbers);
  - `MSK-001`, `E-1.01` and `FP-101A`.
- The first version of the pattern missed the two-part numbers, which accounted for almost every failure on 26-0328 and 26-0445. The pattern below includes them.
- The title, where the title block labels it (checked on 26-0246, 26-0352, 26-0356 and 26-0437), is the large text just below the label, in its column, up to the next label. The label can be "DRAWING TITLE:", "SHEET TITLE:", or "DRAWING" and "TITLE" on two small lines.
- Where there is no label (26-0328/26-0445, 26-0436's controls set, 26-0344), the title is the largest text directly above the number, in the same column, within 18% of the sheet's height. It can be as large as the number itself, and it can run to several lines of the same size, joined top to bottom: "LEVEL 02 - / OVERALL PLAN - / MASTER / MECHANICAL / EQUIPMENT".
- The label comes first because, without it, a larger permit number (26-0246's plumbing) or the project's name would be read as the title.
- Labels, dates, scales, revision entries and small text (under 12 pt) are never part of a title.

- [ ] **Step 1: Write the failing tests**

`tests/test_title_block.py`:
```python
import pytest

from estimator.catalogue.documents import find_documents
from estimator.catalogue.pdf import Span
from estimator.catalogue.register import read_document
from estimator.catalogue.title_block import SHEET_NUMBER, TitleBlock, read_title_block
from pdfs import FILLER, Page, make_pdf


@pytest.mark.parametrize("text", ["M001.00", "M-101", "M1.01", "M00-03", "TC00-00", "H-301", "M-111",
                                  "FP-101A", "MSK-001", "E-1.01", "M001.3", "M 101"])
def test_sheet_number_shapes(text):
    assert SHEET_NUMBER.fullmatch(text)


@pytest.mark.parametrize("text", ["275 HARTZ WAY", "2026", "PROJECT", "A", "SCALE: 1/8\"=1'-0\"", "15970",
                                  "ISSUED FOR CONSTRUCTION", "03/31/2026"])
def test_not_sheet_numbers(text):
    assert not SHEET_NUMBER.fullmatch(text)


def _span(text, size, x, y, w=0.05, h=0.012):
    return Span(text, size, x, y, x + w, y + h)


def test_a_title_block_with_the_title_above_the_number():
    spans = [_span("HVAC SCHEDULES SHEET 3", 20.4, 0.91, 0.851, w=0.07),
             _span("M006.00", 41, 0.935, 0.92, h=0.02),
             _span("PROJECT NO.", 8, 0.90, 0.96), _span("139717", 9, 0.95, 0.96),
             _span("SCA", 30, 0.90, 0.02)]
    assert read_title_block(spans) == TitleBlock("M006.00", "HVAC SCHEDULES SHEET 3")


def test_a_title_over_several_lines():
    lines = ["LEVEL 02 -", "OVERALL PLAN -", "MASTER", "MECHANICAL", "EQUIPMENT"]
    spans = [_span(t, 24.9, 0.935, 0.84 + i * 0.022) for i, t in enumerate(lines)]
    spans.append(_span("M00-03", 45.1, 0.933, 0.973, h=0.02))
    assert read_title_block(spans) == TitleBlock("M00-03", "LEVEL 02 - OVERALL PLAN - MASTER MECHANICAL EQUIPMENT")


def test_the_largest_number_wins_over_a_cross_reference():
    spans = [_span("SEE M-101", 10, 0.90, 0.90), _span("M-101", 10, 0.90, 0.91),
             _span("MECHANICAL PLAN", 22, 0.94, 0.88), _span("M-111", 50, 0.94, 0.94, h=0.02)]
    assert read_title_block(spans).number == "M-111"


def test_labels_dates_and_revisions_are_not_part_of_the_title():
    spans = [_span("SHEET TITLE:", 9.5, 0.89, 0.786), _span("FIRST FLOOR PLAN", 22, 0.90, 0.80, w=0.08),
             _span("DATE: 06/22/2026", 9, 0.90, 0.83), _span("SHEET NO.", 9, 0.89, 0.90),
             _span("M-101", 50, 0.94, 0.93, h=0.02)]
    assert read_title_block(spans) == TitleBlock("M-101", "FIRST FLOOR PLAN")


def test_the_title_under_its_label_not_the_permit_number_beside_it():
    # 26-0246's plumbing sheets: a larger DOB permit number sits between the title and the sheet number.
    spans = [_span("Project:", 8.6, 0.887, 0.788), _span("PS Q517 @ 1 BEACH 39TH", 20.4, 0.890, 0.793, w=0.08),
             _span("Drawing Title:", 8.6, 0.887, 0.846), _span("PLUMBING AND DRAINAGE", 20.4, 0.890, 0.851, w=0.09),
             _span("FIRST FLOOR PLAN", 20.4, 0.890, 0.862, w=0.06), _span("DOB NOW #:", 8.6, 0.887, 0.885),
             _span("Q01333361-S2", 29.4, 0.890, 0.897, w=0.05), _span("P101.00", 41.1, 0.942, 0.924, h=0.02)]
    assert read_title_block(spans) == TitleBlock("P101.00", "PLUMBING AND DRAINAGE FIRST FLOOR PLAN")


def test_a_label_split_over_two_lines():
    # 26-0352: "DRAWING" and "TITLE" are two small lines, the title beside them.
    spans = [_span("TISHMAN SPEYER", 18.8, 0.874, 0.788), _span("DRAWING", 9.4, 0.832, 0.842),
             _span("TITLE", 9.4, 0.832, 0.849), _span("MECHANICAL 21ST FLOOR PLAN", 16.9, 0.857, 0.857, w=0.09),
             _span("SEAL & SIGNATURE", 9.4, 0.832, 0.886), _span("M-100.00", 25.1, 0.926, 0.930, h=0.014)]
    assert read_title_block(spans) == TitleBlock("M-100.00", "MECHANICAL 21ST FLOOR PLAN")


def test_a_title_as_large_as_the_sheet_number():
    # 26-0344: title and sheet number are both 19.4 pt, and a column of 9 pt notes sits alongside.
    spans = [_span("MECHANICAL", 19.4, 0.946, 0.857), _span("6TH FLOOR", 19.4, 0.947, 0.872),
             _span("PLAN", 19.4, 0.946, 0.886), _span("ALL DUCT SHALL FOLLOW SMACNA", 9.0, 0.859, 0.730),
             _span("Drawing No.", 9.7, 0.947, 0.926), _span("M-106.00", 19.4, 0.947, 0.945, h=0.014)]
    assert read_title_block(spans) == TitleBlock("M-106.00", "MECHANICAL 6TH FLOOR PLAN")


def test_an_address_just_smaller_than_the_title_is_left_out():
    # 26-0436's controls sheets: the firm's address is 13.1 pt, the title 15.6 pt.
    spans = [_span("CONTROLS AND DESIGN", 13.1, 0.913, 0.853), _span("275 HARTZ WAY", 13.1, 0.922, 0.860),
             _span("SECOND FLOOR RAS", 15.6, 0.914, 0.885), _span("INSTRUMENT LOCATION", 15.6, 0.910, 0.894),
             _span("IC015", 36.7, 0.922, 0.972, h=0.02)]
    assert read_title_block(spans) == TitleBlock("IC015", "SECOND FLOOR RAS INSTRUMENT LOCATION")


def test_a_file_path_on_the_sheet_edge_is_not_part_of_the_title():
    spans = [_span("TYPICAL DETAILS - 1", 20.4, 0.890, 0.862), _span("C:\\Revit\\EL139717_CENTRAL.rvt", 12.7, 0.994, 0.779),
             _span("E701.00", 41.1, 0.942, 0.924, h=0.02)]
    assert read_title_block(spans).title == "TYPICAL DETAILS - 1"


def test_stamps_and_disclaimers_are_not_titles():
    # Seen by the fact sheet on 26-0436/26-0437 sheets with no title label.
    disclaimer = "THIS DRAWING IS NOT TO BE USED AS BUILDING CONSTRUCTION DRAWING AND NO RESPONSIBILITY IS ACCEPTED FOR ITS USE"
    spans = [_span("NOT FOR CONSTRUCTION", 15.5, 0.908, 0.800), _span("INTERNAL FR - OFFICIAL USE /", 19.0, 0.896, 0.820),
             _span(disclaimer, 14, 0.90, 0.85, w=0.09), _span("M-121", 50.5, 0.940, 0.933, h=0.02)]
    assert read_title_block(spans) == TitleBlock("M-121", None)


def test_no_number_and_no_title():
    spans = [_span("275 HARTZ WAY", 15.7, 0.90, 0.90), _span("REVISIONS", 10, 0.90, 0.80)]
    assert read_title_block(spans) == TitleBlock(None, None)


def test_small_text_shaped_like_a_number_is_not_the_sheet_number():
    assert read_title_block([_span("M-101", 8, 0.95, 0.95)]).number is None


def test_a_rotated_sheet_read_from_the_pdf(tmp_path):
    # Stored portrait and turned 90°, like most of 26-0246's mechanical sheets.
    sheet = Page(width=2160, height=3024, rotation=90,
                 texts=((200, 1500, FILLER, 10), (1650, 250, "HVAC GENERAL NOTES", 20), (1900, 150, "M001.00", 40)))
    make_pdf(tmp_path / "26-9999" / "2. Takeoffs" / "1. Base Takeoff" / "mech.pdf", sheet)
    [record] = read_document(find_documents(tmp_path / "26-9999").documents[0])
    assert read_title_block(record.edge_spans) == TitleBlock("M001.00", "HVAC GENERAL NOTES")
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_title_block.py -v`
Expected: collection error — `ModuleNotFoundError: No module named 'estimator.catalogue.title_block'`.

- [ ] **Step 3: Write the code**

`src/estimator/catalogue/title_block.py`:
```python
"""A drawing sheet's number and title, read from its title block.

Measured on the nine Learn jobs (step-3-facts.md §3): the title block is always a strip
along the right and/or bottom edge of the sheet as viewed, and the sheet number is the
largest text in it with a sheet number's shape. The title is the largest text directly
above the number, in the same column.
"""
from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from estimator.catalogue.pdf import Span

SHEET_NUMBER = re.compile(r"[A-Z]{1,3}[-\s.]?\d{1,4}(?:-\d{1,3})?(?:\.\d{1,3})?[A-Z]?")
MIN_NUMBER_SIZE = 12      # points: sheet numbers measured 19–56 pt; a cross-reference is ~10
MIN_TITLE_SIZE = 12       # points: titles measured 15–25 pt; labels, names and notes are 7–10
LABEL_SIZE = 12           # labels ("DRAWING TITLE:", "SCALE", "Drawing No.:") are smaller than this
TITLE_REACH = 0.18        # how far above the number, as a fraction of the sheet's height, a title can start
COLUMN_SLACK = 0.06       # how far left of the number's column a title line can begin
SAME_SIZE = 0.9           # title lines are within 10% of the title's largest line
MAX_TITLE_CHARS = 90      # a longer line is a paragraph — a disclaimer or a note — not a title line
_TITLE_LABEL = re.compile(r"^(?:(?:SHEET|DRAWING)\s*)?TITLE\s*:?$", re.I)
_NOT_TITLE = re.compile(
    r"^(?:(?:SHEET|DRAWING|DWG)\s*(?:NO\.?|NUMBER|TITLE)|SCALE|DATE|REV|REVISION|REVISIONS|PROJECT|PROJ|DRAWN|CHECKED|"
    r"ISSUED|JOB|SEAL|KEY PLAN|NORTH|TRUE NORTH|NOT FOR CONSTRUCTION|INTERNAL|THIS DRAWING|COPYRIGHT|PRINCIPAL)\b"
    r"|^[\d/.\-: ]+$|^[A-Z]:\\", re.I)   # the last: a file path printed on the sheet edge


@dataclass(frozen=True)
class TitleBlock:
    number: str | None
    title: str | None


def read_title_block(spans: Sequence[Span]) -> TitleBlock:
    numbers = [s for s in spans if s.size >= MIN_NUMBER_SIZE and SHEET_NUMBER.fullmatch(s.text)]
    if not numbers:
        return TitleBlock(None, None)
    number = max(numbers, key=lambda s: (s.size, s.y0))
    return TitleBlock(" ".join(number.text.split()), _title_by_label(spans, number) or _title_above(spans, number))


def _join(lines: list[Span]) -> str:
    return " ".join(" ".join(s.text.split()) for s in sorted(lines, key=lambda s: (round(s.y0, 3), s.x0)))


def _is_label(span: Span) -> bool:
    text = span.text.strip()
    return span.size < LABEL_SIZE and (text.endswith(":") or bool(_NOT_TITLE.search(text))
                                       or text.upper() in {"DRAWING", "SHEET", "TITLE"})


def _title_by_label(spans: Sequence[Span], number: Span) -> str | None:
    """Most title blocks label the title — "DRAWING TITLE:", "SHEET TITLE:", or "DRAWING" and "TITLE" on
    two lines. The title is the large text just below the label, in its column, up to the next label."""
    for label in (s for s in spans if _TITLE_LABEL.match(s.text.strip()) and s.size < LABEL_SIZE):
        below = sorted((s for s in spans
                        if s is not label and label.y0 - 0.004 <= s.y0 <= label.y0 + 0.10 and s.y0 < number.y0
                        and label.x0 - 0.01 <= s.x0 <= label.x0 + 0.12),
                       key=lambda s: (round(s.y0, 3), s.x0))
        lines: list[Span] = []
        for span in below:
            if _is_label(span):
                if lines:
                    break
                continue
            if span.size >= MIN_TITLE_SIZE and len(span.text) <= MAX_TITLE_CHARS and not SHEET_NUMBER.fullmatch(span.text):
                lines.append(span)
        if lines:
            return _join(lines)
    return None


def _title_above(spans: Sequence[Span], number: Span) -> str | None:
    """With no label, the title is the largest text directly above the sheet number, in its column."""
    above = [s for s in spans
             if s is not number
             and s.y1 <= number.y0 + 0.005 and s.y0 >= number.y0 - TITLE_REACH
             and number.x0 - COLUMN_SLACK <= s.x0 <= number.x1
             and MIN_TITLE_SIZE <= s.size <= number.size
             and len(s.text) <= MAX_TITLE_CHARS
             and not _NOT_TITLE.search(s.text)
             and not SHEET_NUMBER.fullmatch(s.text)]
    if not above:
        return None
    largest = max(s.size for s in above)
    return _join([s for s in above if s.size >= largest * SAME_SIZE])
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_title_block.py -v`
Expected: 33 passed (12 + 8 shape cases, and 13 others).

- [ ] **Step 5: Run everything, then commit**

Run: `.venv/Scripts/python.exe -m pytest -q` — expected: all pass.
```bash
git add -A
git commit -m "feat: read a drawing sheet's number and title from its title block

<your Co-Authored-By line>"
```

---

### Task 5: What kind of sheet it is — discipline and type

**Files:**
- Create: `assets/reading_lists/sheet_types.json`, `src/estimator/catalogue/sheet_types.py`, `tests/test_sheet_types.py`

**Interfaces:**
- Consumes: `PageRecord` (Task 3); `TitleBlock` (Task 4).
- Produces:
  - `Sheet(document: str, page: int, number: str | None, title: str | None, discipline: str, types: tuple[str, ...])` — frozen dataclass.
  - `SheetTypes` — the reading list, `SheetTypes.load(path=SHEET_TYPES)`; `SHEET_TYPES = ASSETS / "reading_lists" / "sheet_types.json"`.
  - `TYPES` — the type names in the reading list's order: `("Schedules", "Plans", "Details", "Air riser", "Water riser", "Network riser", "Control diagrams", "Diagrams", "Sections and elevations", "Demolition", "Specifications", "Notes and legends")`.
  - `discipline_of(number: str | None, title: str | None, reading: SheetTypes) -> str`
  - `types_of(title: str | None, reading: SheetTypes) -> tuple[str, ...]`
  - `classify_sheet(record: PageRecord, block: TitleBlock, reading: SheetTypes | None = None) -> Sheet`

How sheets are typed (design §9.2: "title-block title and content, not the sheet number alone — numbering conventions differ between engineering firms"):
- **Type** comes from the title's words, and a sheet can carry more than one type. "HVAC CONTROL DIAGRAM SHEET 2 NETWORK ARCHITECTURE DIAGRAM" is both a control diagram and a network riser. "MECHANICAL 21ST FLOOR DEMOLITION PLAN" is a plan and a demolition sheet.
- A title that says "controls" together with "plan" is a plan, not a control diagram: "HVAC PIPING AND CONTROLS FIRST FLOOR PLAN".
- A sheet with no title, or none of the words, has no type, and the job stage flags it.
- **Discipline** comes from the title's words first ("MECHANICAL", "HVAC", "PLUMBING"…), then from the letters of the sheet number. The title comes first because letters differ between firms: `H` is HVAC on 26-0246 but hazardous materials on 26-0356.

The rules below were measured on the titles the Task 4 rule reads from 26-0246, 26-0339, 26-0344, 26-0352 and 26-0356 (all 477 of their sheets carry a number and a title).

- [ ] **Step 1: Write the reading list**

`assets/reading_lists/sheet_types.json`:
```json
{
  "about": "How a drawing sheet's discipline and type are read from its title block (design §9.2). Patterns are matched against the sheet title, ignoring case. A sheet can have several types. Extend this file when the Learn check shows a sheet it couldn't sort — never code.",
  "types": [
    {"name": "Schedules", "patterns": ["\\bSCHEDULES?\\b"]},
    {"name": "Plans", "patterns": ["\\bPLANS?\\b", "\\bRCP\\b", "\\bLAYOUTS?\\b", "^(?!.*\\b(?:RISERS?|DIAGRAMS?|SCHEDULES?|DETAILS?|SECTIONS?|ELEVATIONS?)\\b).*\\b(?:LEVEL|SECTOR|OVERALL|FLOOR)\\b"]},
    {"name": "Details", "patterns": ["\\bDETAILS?\\b", "\\bPRV\\s+STATION\\b"]},
    {"name": "Air riser", "patterns": ["\\b(?:AIR|DUCT|DUCTWORK|AIRFLOW|EXHAUST|SUPPLY|VENTILATION|SMOKE)\\b.*\\bRISERS?\\b", "\\bRISERS?\\b.*\\b(?:AIR|DUCT|DUCTWORK)\\b", "\\bAIR\\s*FLOW\\s+DIAGRAMS?\\b"]},
    {"name": "Water riser", "patterns": ["\\b(?:WATER|PIPING|HYDRONIC|STEAM|CONDENSER|CONDENSATE|CHILLED|GLYCOL|REFRIGERANT|HEATING|SANITARY|STORM|GAS)\\b.*\\b(?:RISERS?|FLOW\\s+DIAGRAMS?|SCHEMATICS?)\\b"]},
    {"name": "Network riser", "patterns": ["\\bNETWORK\\b", "\\b(?:BMS|BAS|COMMUNICATIONS?|DATA)\\b.*\\b(?:RISERS?|ARCHITECTURE|DIAGRAMS?)\\b", "\\bSYSTEM\\s+ARCHITECTURE\\b"]},
    {"name": "Control diagrams", "patterns": ["^(?!.*\\bPLANS?\\b).*\\bCONTROLS?\\b", "\\bSEQUENCES?\\s+OF\\s+OPERATIONS?\\b", "\\bPOINTS?\\s+LISTS?\\b", "\\bINSTRUMENT(?:ATION)?\\b", "^(?!.*\\bPLANS?\\b).*\\b(?:BMS|BAS|EPMS|DCIM)\\b"]},
    {"name": "Diagrams", "patterns": ["\\bDIAGRAMS?\\b", "\\bONE[- ]LINE\\b", "\\bSCHEMATICS?\\b", "\\bRISERS?\\b", "\\bISOMETRICS?\\b"]},
    {"name": "Sections and elevations", "patterns": ["\\bSECTIONS?\\b", "\\bELEVATIONS?\\b"]},
    {"name": "Demolition", "patterns": ["\\bDEMOLITION\\b", "\\bDEMO\\b", "\\bREMOVALS?\\b"]},
    {"name": "Specifications", "patterns": ["\\bSPECIFICATIONS?\\b", "\\bSPECS\\b"]},
    {"name": "Notes and legends", "patterns": ["\\bNOTES\\b", "\\bLEGENDS?\\b", "\\bSYMBOLS\\b", "\\bABBREVIATIONS\\b", "\\bCOVER\\b", "\\bINDEX\\b", "\\bDRAWINGS?\\s+LISTS?\\b", "\\bTABLE\\s+OF\\s+CONTENTS\\b", "\\bGENERAL\\s+INFORMATION\\b", "\\bINSPECTIONS?\\b", "\\bCOMPLIANCE\\b"]}
  ],
  "disciplines_by_title": [
    {"name": "Mechanical", "patterns": ["\\bMECHANICAL\\b", "\\bHVAC\\b"]},
    {"name": "Plumbing", "patterns": ["\\bPLUMBING\\b", "\\bSANITARY\\b", "\\bDOMESTIC\\s+WATER\\b"]},
    {"name": "Fire protection", "patterns": ["\\bFIRE\\s+PROTECTION\\b", "\\bSPRINKLERS?\\b", "\\bSTANDPIPE\\b"]},
    {"name": "Electrical", "patterns": ["\\bELECTRICAL\\b", "\\bLIGHTING\\b", "\\bPOWER\\b"]},
    {"name": "Technology", "patterns": ["\\bTELECOM(?:MUNICATIONS?)?\\b", "\\bTECHNOLOGY\\b"]},
    {"name": "Architectural", "patterns": ["\\bARCHITECTURAL\\b"]},
    {"name": "Structural", "patterns": ["\\bSTRUCTURAL\\b"]},
    {"name": "Civil", "patterns": ["\\bCIVIL\\b"]},
    {"name": "Hazardous materials", "patterns": ["\\bASBESTOS\\b", "\\bABATEMENT\\b", "\\bHAZARDOUS\\b"]}
  ],
  "disciplines_by_letters": {
    "M": "Mechanical", "H": "Mechanical", "MD": "Mechanical", "MH": "Mechanical", "MP": "Mechanical", "MSK": "Mechanical",
    "IC": "Controls", "TC": "Controls", "BMS": "Controls", "BAS": "Controls",
    "P": "Plumbing", "PL": "Plumbing", "PD": "Plumbing",
    "FP": "Fire protection", "F": "Fire protection", "SP": "Fire protection",
    "E": "Electrical", "ED": "Electrical", "EL": "Electrical", "EP": "Electrical", "FA": "Electrical",
    "TN": "Technology", "TY": "Technology",
    "A": "Architectural", "AD": "Architectural", "ID": "Architectural", "LS": "Architectural", "G": "General", "GI": "General",
    "S": "Structural", "C": "Civil", "CS": "Civil", "L": "Civil"
  }
}
```

- [ ] **Step 2: Write the failing tests**

`tests/test_sheet_types.py`:
```python
import pytest

from estimator.catalogue.register import PageRecord
from estimator.catalogue.sheet_types import Sheet, SheetTypes, TYPES, classify_sheet, discipline_of, types_of
from estimator.catalogue.title_block import TitleBlock

READING = SheetTypes.load()


@pytest.mark.parametrize("title, types", [
    ("HVAC SCHEDULES SHEET 3", ("Schedules",)),
    ("HVAC VENTILATION SCHEDULES SHEET 2", ("Schedules",)),
    ("HVAC FIRST FLOOR PLAN", ("Plans",)),
    ("HVAC PIPING AND CONTROLS SECOND FLOOR PLAN", ("Plans",)),
    ("MECHANICAL 21ST FLOOR CONTROLS PLAN", ("Plans",)),
    ("HVAC AIR RISER DIAGRAM 1", ("Air riser", "Diagrams")),
    ("MECHANICAL HOT WATER AND STEAM RISER DIAGRAM", ("Water riser", "Diagrams")),
    ("MECHANICAL CONDENSER WATER RISER DIAGRAM", ("Water riser", "Diagrams")),
    ("HVAC CONTROL DIAGRAM SHEET 2 NETWORK ARCHITECTURE DIAGRAM", ("Network riser", "Control diagrams", "Diagrams")),
    ("HVAC CONTROL DIAGRAM SHEET 5 VAV BOX CONTROL DIAGRAMS", ("Control diagrams", "Diagrams")),
    ("MECHANICAL CONTROLS - II", ("Control diagrams",)),
    ("SECOND FLOOR RAS INSTRUMENT LOCATION", ("Plans", "Control diagrams")),   # a floor plan of instrument locations
    ("HVAC DETAILS SHEET 1", ("Details",)),
    ("HVAC SECTIONS AND ENLARGED PLAN SHEET 4", ("Plans", "Sections and elevations")),
    ("MECHANICAL 21ST FLOOR DEMOLITION PLAN", ("Plans", "Demolition")),
    ("MECHANICAL SPECIFICATIONS SHEET 1 OF 3", ("Specifications",)),
    ("HVAC SYMBOLS, ABBREVIATIONS, AND NOTES", ("Notes and legends",)),
    ("COVER SHEET AND DRAWING LIST", ("Notes and legends",)),
    ("ELECTRICAL - 21ST FLOOR LIGHTING RCP", ("Plans",)),
    ("PLUMBING SANITARY RISER DIAGRAM SHEET 3 OF 3", ("Water riser", "Diagrams")),
    ("ONE LINE DIAGRAM", ("Diagrams",)),
    ("MECHANICAL AIR FLOW DIAGRAMS", ("Air riser", "Diagrams")),
    ("CHILLED WATER FLOW DIAGRAM - DATA HALL 1100 & 2100", ("Water riser", "Diagrams")),
    ("SANITARY PIPING RISER DIAGRAM - SEGMENT E2", ("Water riser", "Diagrams")),
    ("LEVEL 01 - SECTOR D", ("Plans",)),
    ("HVAC - LEVEL ONE - OVERALL", ("Plans",)),
    ("FIRST FLOOR - POWER SYSTEMS", ("Plans",)),
    ("MECHANICAL VENTILATION COMPLIANCE", ("Notes and legends",)),
    ("ISOMETRIC VIEWS", ("Diagrams",)),
    ("CHILLED WATER PLANT 2 DCIM BMS/EPMS DIAGRAM", ("Network riser", "Control diagrams", "Diagrams")),
    ("PLUMBING AND DRAINAGE DRAWINGS LISTS AND SPECIAL INSPECTIONS", ("Notes and legends",)),
    ("MECHANICAL STEAM PRV STATION", ("Details",)),
    ("HVAC CHIMNEY VENT ANALYSIS", ()),
    (None, ()),
])
def test_types_from_the_title(title, types):
    assert types_of(title, READING) == types


@pytest.mark.parametrize("number, title, discipline", [
    ("M006.00", "HVAC SCHEDULES SHEET 3", "Mechanical"),
    ("H200.00", "SUB-SLAB DEPRESSURIZATION PLAN", "Mechanical"),
    ("H-100.00", "SECOND FLOOR ASBESTOS ABATEMENT PLAN", "Hazardous materials"),
    ("MD-103.00", "ROOF DEMOLITION PLAN", "Mechanical"),
    ("P101.00", "PLUMBING AND DRAINAGE FIRST FLOOR PLAN", "Plumbing"),
    ("E701.00", "TYPICAL DETAILS - 1", "Electrical"),
    ("IC015", "SECOND FLOOR RAS INSTRUMENT LOCATION", "Controls"),
    ("M00-03", "LEVEL 02 - OVERALL PLAN - MASTER MECHANICAL EQUIPMENT", "Mechanical"),
    ("T-001.00", "COVER SHEET AND DRAWING LIST", "Unknown"),     # T is a title sheet on one job, technology on another
    ("X-1", "SOMETHING", "Unknown"),
    (None, None, "Unknown"),
])
def test_discipline_from_the_title_first_then_the_letters(number, title, discipline):
    assert discipline_of(number, title, READING) == discipline


def test_a_sheet_record():
    record = PageRecord("mech.pdf", 6, "text", "…", 90)
    assert classify_sheet(record, TitleBlock("M006.00", "HVAC SCHEDULES SHEET 3"), READING) == \
        Sheet("mech.pdf", 6, "M006.00", "HVAC SCHEDULES SHEET 3", "Mechanical", ("Schedules",))


def test_the_type_names_are_the_reading_lists():
    assert tuple(t for t, _ in READING.types) == TYPES
```

- [ ] **Step 3: Run them to see them fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_sheet_types.py -v`
Expected: collection error — `ModuleNotFoundError: No module named 'estimator.catalogue.sheet_types'`.

- [ ] **Step 4: Write the code**

`src/estimator/catalogue/sheet_types.py`:
```python
"""What kind of sheet a drawing is — its discipline and its types — read from its title block.

The rules are the reading list in assets/reading_lists/sheet_types.json (design §9.2: the
reading lists are data). Type comes from the title's words; a sheet can have several.
Discipline comes from the title's words first, then from the sheet number's letters,
because firms use the letters differently.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from estimator.catalogue.register import PageRecord
from estimator.catalogue.title_block import TitleBlock

ASSETS = Path(__file__).resolve().parents[3] / "assets"
SHEET_TYPES = ASSETS / "reading_lists" / "sheet_types.json"
TYPES = ("Schedules", "Plans", "Details", "Air riser", "Water riser", "Network riser", "Control diagrams", "Diagrams",
         "Sections and elevations", "Demolition", "Specifications", "Notes and legends")
_LETTERS = re.compile(r"^([A-Z]{1,3})")


@dataclass(frozen=True)
class Sheet:
    document: str
    page: int
    number: str | None
    title: str | None
    discipline: str
    types: tuple[str, ...]


@dataclass(frozen=True)
class SheetTypes:
    types: tuple[tuple[str, tuple[re.Pattern, ...]], ...]
    by_title: tuple[tuple[str, tuple[re.Pattern, ...]], ...]
    by_letters: dict[str, str]

    @classmethod
    def load(cls, path: Path = SHEET_TYPES) -> "SheetTypes":
        data = json.loads(Path(path).read_text(encoding="utf-8"))

        def rules(key):
            return tuple((e["name"], tuple(re.compile(p, re.I) for p in e["patterns"])) for e in data[key])

        return cls(rules("types"), rules("disciplines_by_title"), data["disciplines_by_letters"])


def types_of(title: str | None, reading: SheetTypes) -> tuple[str, ...]:
    if not title:
        return ()
    return tuple(name for name, patterns in reading.types if any(p.search(title) for p in patterns))


def discipline_of(number: str | None, title: str | None, reading: SheetTypes) -> str:
    if title:
        for name, patterns in reading.by_title:
            if any(p.search(title) for p in patterns):
                return name
    letters = _LETTERS.match(number or "")
    if letters:
        code = letters.group(1)
        for length in range(len(code), 0, -1):
            if code[:length] in reading.by_letters:
                return reading.by_letters[code[:length]]
    return "Unknown"


def classify_sheet(record: PageRecord, block: TitleBlock, reading: SheetTypes | None = None) -> Sheet:
    reading = reading or SheetTypes.load()
    return Sheet(record.document, record.page, block.number, block.title,
                 discipline_of(block.number, block.title, reading), types_of(block.title, reading))
```

- [ ] **Step 5: Run the tests to see them pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_sheet_types.py -v`
Expected: 47 passed (34 + 11 parametrized, and 2 others). If a title case fails, fix the reading list (`sheet_types.json`), not the test, and say which pattern changed in your report.

- [ ] **Step 6: Run everything, then commit**

Run: `.venv/Scripts/python.exe -m pytest -q` — expected: all pass.
```bash
git add -A
git commit -m "feat: sort drawing sheets by discipline and type, from a reading list

<your Co-Authored-By line>"
```

---

### Task 6: Spec sections and their pages

**Files:**
- Create: `src/estimator/catalogue/spec_sections.py`, `tests/test_spec_sections.py`

**Interfaces:**
- Consumes: `PageRecord` (Task 3); `clean_text` (Task 1).
- Produces:
  - `section_number(raw: str) -> str` — `"230923"` → `"23 09 23"`, `"23 05 00.1"` stays, `"15970"` stays.
  - `is_controls_section(number: str, title: str) -> bool`
  - `SpecSection(number: str, title: str, document: str, first_page: int, last_page: int)` — frozen dataclass, with a property `controls: bool`.
  - `index_sections(pages: Sequence[PageRecord]) -> list[SpecSection]` — the caller passes only the pages of spec, addendum, RFI and other documents, in register order.

A heading counts only when "SECTION" is in capitals, within the first eight lines of text on the page, and not followed by punctuation. On 26-0246's specs a looser rule opened sixteen sections, eight of them body cross-references such as "Section 16727, “Data Cabling System”."

What the Learn jobs' specs look like (`step-3-facts.md` §5):
- A section opens with a header line, `SECTION 15970`, `SECTION 230500` or `SECTION 23 09 23`, often followed by the title on the same line or the next.
- Every page carries a footer: `15970 - 15`, `230500-1` or `23 09 23 - 1`.
- `END OF SECTION` closes a section.

Controls sections are:
- anything in 23 09 xx or Division 25;
- 15900–15999 in the old numbering;
- any section whose title names building management, building automation, temperature control, instrumentation and control, DDC or a sequence of operation. 26-0334's BMS section is 23 39 00, so the number alone isn't enough.

A page with three or more different section headers is a table of contents and opens nothing.

- [ ] **Step 1: Write the failing tests**

`tests/test_spec_sections.py`:
```python
import pytest

from estimator.catalogue.pdf import clean_text
from estimator.catalogue.register import PageRecord
from estimator.catalogue.spec_sections import SpecSection, index_sections, is_controls_section, section_number


def _pages(document, *texts):
    return [PageRecord(document, n, "text", text, 0) for n, text in enumerate(texts, start=1)]


@pytest.mark.parametrize("raw, number", [("230923", "23 09 23"), ("23 09 23", "23 09 23"), ("23 05 00.1", "23 05 00.1"),
                                         ("15970", "15970"), ("250000", "25 00 00")])
def test_section_numbers(raw, number):
    assert section_number(raw) == number


@pytest.mark.parametrize("number, title, controls", [
    ("23 09 23", "", True), ("25 00 00", "INTEGRATED AUTOMATION", True), ("15970", "", True),
    ("15985", "SEQUENCE OF OPERATION", True), ("23 39 00", "BUILDING MANAGEMENT SYSTEMS", True),
    ("23 05 00", "COMMON WORK RESULTS FOR HVAC", False), ("15400", "PLUMBING", False),
    ("23 73 13", "MODULAR INDOOR CENTRAL-STATION AIR-HANDLING UNITS", False)])
def test_which_sections_are_controls(number, title, controls):
    assert is_controls_section(number, title) is controls


def test_an_old_style_section_from_header_to_end():
    pages = _pages("specs.pdf",
                   "SECTION 15970\nTEMPERATURE CONTROL SYSTEM (BACNET BMS/DDC)\nPART 1 - GENERAL\n15970 - 1",
                   "1.2 SUMMARY\nA. Work includes the BMS.\n15970 - 2",
                   "END OF SECTION 15970\n15970 - 3",
                   "SECTION 15985\nSEQUENCE OF OPERATION\n15985 - 1")
    assert index_sections(pages) == [
        SpecSection("15970", "TEMPERATURE CONTROL SYSTEM (BACNET BMS/DDC)", "specs.pdf", 1, 3),
        SpecSection("15985", "SEQUENCE OF OPERATION", "specs.pdf", 4, 4)]


def test_a_title_on_the_header_line_and_footers_without_headers():
    pages = _pages("manual.pdf",
                   "SECTION 23 09 23 - INSTRUMENTATION AND CONTROL FOR HVAC\nPART 1\n23 09 23 - 1",
                   "text\n23 09 23 - 2",
                   "more text\n230500-1",
                   "still common work\n230500-2")
    sections = index_sections(pages)
    assert [(s.number, s.title, s.first_page, s.last_page) for s in sections] == [
        ("23 09 23", "INSTRUMENTATION AND CONTROL FOR HVAC", 1, 2), ("23 05 00", "", 3, 4)]
    assert [s.controls for s in sections] == [True, False]


def test_control_characters_used_as_spaces():
    pages = _pages("k9.pdf", clean_text("SECTION\x04230500\nCOMMON\x04WORK\x04RESULTS\n230500\x04-\x041"))
    assert index_sections(pages) == [SpecSection("23 05 00", "COMMON WORK RESULTS", "k9.pdf", 1, 1)]


def test_a_table_of_contents_opens_nothing():
    toc = "TABLE OF CONTENTS\nSECTION 23 05 00 COMMON WORK\nSECTION 23 09 23 CONTROLS\nSECTION 23 73 13 AHUS"
    pages = _pages("manual.pdf", toc, "SECTION 23 05 00 - COMMON WORK RESULTS FOR HVAC\n23 05 00 - 1")
    assert [(s.number, s.first_page) for s in index_sections(pages)] == [("23 05 00", 2)]


def test_a_cross_reference_opens_nothing():
    body = "\n".join(["PART 1 - GENERAL", "1.1 RELATED WORK", "A. Drawings apply.", "B. Coordinate with the work",
                      "of other sections.", "C. Cabling:", "D. Wiring:", "E. Refer to Division 16.",
                      "SECTION 16727 DATA CABLING SYSTEM", "F. Grounding."])
    pages = _pages("specs.pdf", "SECTION 15970\nTEMPERATURE CONTROL SYSTEM\n15970 - 1",
                   body + "\n15970 - 2",                                              # too far down the page
                   "SECTION 15985, “SEQUENCE OF OPERATION”.\nSection 15985 applies.\n15970 - 3")   # punctuation; lower case
    assert index_sections(pages) == [SpecSection("15970", "TEMPERATURE CONTROL SYSTEM", "specs.pdf", 1, 3)]


def test_a_running_header_at_the_top_of_every_page():
    # 26-0356: the capitalised heading is the ninth line, below the running header.
    top = "Mott Haven Houses\nCommunity Center Upgrades\nRFQ No. 511469\nBid Documents\n09/10/2025\n"
    pages = _pages("rfq.pdf",
                   top + "Page 1 of 42\nSection 23 09 00\nInstrumentation and Controls for HVAC\n"
                         "SECTION 23 09 00\nINSTRUMENTATION AND CONTROLS FOR HVAC\nPART 1",
                   top + "Page 2 of 42\nSection 23 09 00\nInstrumentation and Controls for HVAC\n"
                         "controllers furnished in this section shall communicate over BACnet IP.")
    assert index_sections(pages) == [SpecSection("23 09 00", "Instrumentation and Controls for HVAC", "rfq.pdf", 1, 2)]


def test_number_page_and_title_on_one_line():
    # 26-0344: "230900-4" and the title share the page's first lines.
    pages = _pages("hvac.pdf",
                   "80 Broad Street Conversion\nPennoni Associates, Inc.\n230900-4        Instrumentation and Control of HVAC\n"
                   "50% CD\nF. Samples for Verification",
                   "80 Broad Street Conversion\nPennoni Associates, Inc.\n230900-5        Instrumentation and Control of HVAC\n"
                   "2.2 CONTROL SYSTEM")
    assert index_sections(pages) == [SpecSection("23 09 00", "Instrumentation and Control of HVAC", "hvac.pdf", 1, 2)]


def test_sections_do_not_run_across_documents():
    pages = _pages("a.pdf", "SECTION 230923\nCONTROLS\n230923 - 1") + _pages("b.pdf", "no header here")
    assert index_sections(pages) == [SpecSection("23 09 23", "CONTROLS", "a.pdf", 1, 1)]
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_spec_sections.py -v`
Expected: collection error — `ModuleNotFoundError: No module named 'estimator.catalogue.spec_sections'`.

- [ ] **Step 3: Write the code**

`src/estimator/catalogue/spec_sections.py`:
```python
"""Spec sections and the pages they run over; which of them are controls sections."""
from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from estimator.catalogue.register import PageRecord

_NUMBER = r"(\d{2}\s?\d{2}\s?\d{2}(?:\.\d{1,2})?|\d{5})"
# A section heading is "SECTION" in capitals, near the top of its page, not followed by punctuation:
# "Section 16727, “Data Cabling System”." in the body is a cross-reference, not a heading.
_HEADER = re.compile(rf"^[ \t]*SECTION[ \t]+{_NUMBER}\b[ \t]*[-–:]?[ \t]*(.*)$", re.M)
# A running header repeated at the top of every page: "Section 23 09 00" alone on its line, the title
# on the next (26-0356), or the number, page and title on one line: "230900-4    Instrumentation and
# Control of HVAC" (26-0344).
_RUNNING = re.compile(rf"^[ \t]*SECTION[ \t]+{_NUMBER}[ \t]*$", re.I | re.M)
_NUMBERED_TITLE = re.compile(rf"^[ \t]*{_NUMBER}[ \t]*[-–][ \t]*\d{{1,3}}[ \t]{{2,}}(\S.*?)[ \t]*$", re.M)
HEADER_LINES = 8            # a heading sits within the first eight lines of text on its page
_NOT_A_TITLE = re.compile(r"^[,.;:)”\"'’]|^[a-z]")
_FOOTER = re.compile(rf"^\s*{_NUMBER}\s*[-–]\s*\d{{1,3}}\s*$", re.M)
_END = re.compile(r"END\s+OF\s+SECTION", re.I)
_CONTROLS_TITLE = re.compile(
    r"building\s+(?:management|automation)|temperature\s+control|instrumentation\s+and\s+control|"
    r"\bDDC\b|direct\s+digital|sequences?\s+of\s+operations?|\bBMS\b|\bBAS\b|energy\s+management", re.I)


def section_number(raw: str) -> str:
    digits, _, suffix = raw.replace(" ", "").partition(".")
    number = f"{digits[0:2]} {digits[2:4]} {digits[4:6]}" if len(digits) == 6 else digits
    return f"{number}.{suffix}" if suffix else number


def is_controls_section(number: str, title: str) -> bool:
    if number.startswith(("23 09", "25 ")):
        return True
    if len(number) >= 5 and number[:5].isdigit() and 15900 <= int(number[:5]) <= 15999:
        return True
    return bool(_CONTROLS_TITLE.search(title))


@dataclass(frozen=True)
class SpecSection:
    number: str
    title: str
    document: str
    first_page: int
    last_page: int

    @property
    def controls(self) -> bool:
        return is_controls_section(self.number, self.title)


def _title_after(match: re.Match, text: str) -> str:
    title = " ".join(match.group(2).split()).strip(" -–:")
    if title:
        return title
    rest = text[match.end():].lstrip("\n")
    following = rest.split("\n", 1)[0].strip()
    return " ".join(following.split()) if following.isupper() else ""


def _next_line(match: re.Match, text: str) -> str:
    following = text[match.end():].lstrip("\n").split("\n", 1)[0].strip()
    looks_like_a_title = following[:1].isupper() and len(following) <= 80 and "INTENTIONALLY" not in following.upper()
    return " ".join(following.split()) if looks_like_a_title else ""


def _section_on(text: str) -> tuple[str | None, str]:
    """The section a page belongs to, and its title if the page gives it."""
    top = "\n".join([line for line in text.split("\n") if line.strip()][:HEADER_LINES])
    headers = [h for h in _HEADER.finditer(top) if not _NOT_A_TITLE.match(h.group(2).strip())]
    if headers:
        return section_number(headers[0].group(1)), _title_after(headers[0], top)
    running = _RUNNING.search(top)
    if running:
        return section_number(running.group(1)), _next_line(running, top)
    numbered = _NUMBERED_TITLE.search(top)
    if numbered:
        return section_number(numbered.group(1)), " ".join(numbered.group(2).split())
    footer = _FOOTER.search(text)
    return (section_number(footer.group(1)), "") if footer else (None, "")


def index_sections(pages: Sequence[PageRecord]) -> list[SpecSection]:
    sections: list[SpecSection] = []
    current: dict | None = None

    def close():
        nonlocal current
        if current is not None:
            sections.append(SpecSection(**current))
            current = None

    for record in pages:
        if current is not None and record.document != current["document"]:
            close()
        if len({section_number(h.group(1)) for h in _HEADER.finditer(record.text)}) >= 3:
            continue                                   # a table of contents
        number, title = _section_on(record.text)
        if number is not None and (current is None or current["number"] != number):
            close()
            current = {"number": number, "title": title, "document": record.document,
                       "first_page": record.page, "last_page": record.page}
        elif current is not None:
            current["last_page"] = record.page
            if title and not current["title"]:
                current["title"] = title
        if current is not None and _END.search(record.text):
            close()
    close()
    return sections
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_spec_sections.py -v`
Expected: 21 passed (5 + 8 parametrized, and 8 others).

- [ ] **Step 5: Run everything, then commit**

Run: `.venv/Scripts/python.exe -m pytest -q` — expected: all pass.
```bash
git add -A
git commit -m "feat: index spec sections and mark the controls sections

<your Co-Authored-By line>"
```

---

### Task 7: The bid check

**Files:**
- Create: `assets/reading_lists/manufacturers.json`, `src/estimator/catalogue/qualify.py`, `tests/test_qualify.py`

**Interfaces:**
- Consumes: `PageRecord` (Task 3); `SpecSection` (Task 6).
- Produces:
  - `MANUFACTURERS = ASSETS / "reading_lists" / "manufacturers.json"` (module constant; `ASSETS` is the repo's `assets` folder).
  - `Mention(document: str, page: int, quote: str, ours: tuple[str, ...], listed: tuple[str, ...], others: tuple[str, ...], sole: bool)` — frozen dataclass:
    - `ours`: the platforms AME bids that the passage names;
    - `listed`: Honeywell / Johnson Controls named in a list of acceptable manufacturers;
    - `others`: other controls manufacturers named;
    - `sole`: whether it uses sole-source wording.
  - `BidCheck(finding: str, reason: str, others: tuple[str, ...], mentions: tuple[Mention, ...], controls_sections: tuple[str, ...])` — frozen dataclass. `finding` is `"Qualifies"`, `"Open"` or `"Does not qualify"`.
  - `ReadingList` — loaded from the JSON; `ReadingList.load(path=MANUFACTURERS)`.
  - `check_bid(pages: Sequence[PageRecord], sections: Sequence[SpecSection], reading: ReadingList | None = None) -> BidCheck` — the caller passes the pages of every document that isn't a drawing.

The rule, from the design's §8, made mechanical:
- A passage is the text around a manufacturer's name, 350 characters either side, cut back to whole lines.
- A passage counts only when it sits in a controls section, or when it uses controls words itself (BMS, BAS, DDC, building automation…). That keeps "Trane" in an equipment schedule, and "Kele … or approved equal" on a horn alarm, out of the bid check.
- **Qualifies:** a passage names Honeywell WEBs, Johnson Controls FX or Niagara (Tridium, N4, Niagara 4, Niagara Framework), or a list of acceptable manufacturers includes Honeywell or Johnson Controls.
- **Does not qualify:** a passage names only another manufacturer, in sole-source wording ("no substitution", "sole source", "only systems that…"), and nothing qualifies.
- **Open:** another manufacturer is named, and nothing qualifies (basis of design, "or approved equal", or simply named). Also open when a qualifying passage and another manufacturer's sole-source passage both exist, because the spec says two things and the US team decides.
- **Open, silent:** no controls manufacturer is named at all.

Every other controls manufacturer found is listed for the US team, whatever the finding. That is the estimator's own rule: any other manufacturer mentioned is highlighted.

- [ ] **Step 1: Write the reading list**

`assets/reading_lists/manufacturers.json`:
```json
{
  "about": "The bid check's reading list (design §8). Everything is matched ignoring case, except a name marked exact_case (because in lower case it is an ordinary word). Add a manufacturer here, never in code.",
  "platforms_we_bid": [
    {"name": "Honeywell WEBs", "patterns": ["\\bWEBs(?:[- ]?N4)?\\b", "\\bWEBStation\\b"]},
    {"name": "Johnson Controls FX", "patterns": ["\\bJohnson\\s+Controls\\b[^\\n]{0,60}?\\bFX\\b", "\\bFX\\s?(?:Server|Supervisory|Supervisor|Workbench|PCG|PCX|PCV|PCA|80|90)\\b", "\\bFacility\\s+Explorer\\b"]},
    {"name": "Niagara N4", "patterns": ["\\bNiagara\\b", "\\bTridium\\b", "\\bN4\\s+Framework\\b"]}
  ],
  "on_an_approved_list": [
    {"name": "Honeywell", "patterns": ["\\bHoneywell\\b"]},
    {"name": "Johnson Controls", "patterns": ["\\bJohnson\\s+Controls\\b", "\\bJCI\\b"]}
  ],
  "other_manufacturers": [
    {"name": "Siemens", "patterns": ["\\bSiemens\\b"]},
    {"name": "Automated Logic", "patterns": ["\\bAutomated\\s+Logic\\b"]},
    {"name": "Distech Controls", "patterns": ["\\bDistech\\b"]},
    {"name": "Delta Controls", "patterns": ["\\bDelta\\s+Controls\\b"]},
    {"name": "Alerton", "patterns": ["\\bAlerton\\b"]},
    {"name": "KMC Controls", "patterns": ["\\bKMC\\b"]},
    {"name": "Trane", "patterns": ["\\bTrane\\b"]},
    {"name": "Carrier", "patterns": ["\\bCarrier\\b(?!\\s+Sense)"], "exact_case": true},
    {"name": "Schneider Electric", "patterns": ["\\bSchneider\\b", "\\bAndover\\b", "\\bEcoStruxure\\b"]},
    {"name": "Reliable Controls", "patterns": ["\\bReliable\\s+Controls\\b"], "exact_case": true},
    {"name": "Johnson Controls Metasys", "patterns": ["\\bMetasys\\b"]},
    {"name": "Rockwell Automation (Allen-Bradley)", "patterns": ["\\bRockwell\\b", "\\bAllen[- ]Bradley\\b"]},
    {"name": "American Auto-Matrix", "patterns": ["\\bAuto-?Matrix\\b"]},
    {"name": "Carel", "patterns": ["\\bCarel\\b"]},
    {"name": "Crestron", "patterns": ["\\bCrestron\\b"]},
    {"name": "Emerson", "patterns": ["\\bEmerson\\b"]}
  ],
  "controls_words": ["\\bBMS\\b", "\\bBAS\\b", "\\bDDC\\b", "building\\s+automation", "building\\s+management", "temperature\\s+control", "control\\s+system", "controls\\s+contractor", "direct\\s+digital", "\\bBACnet\\b", "energy\\s+management", "\\bEMS\\b", "\\bSCADA\\b", "front[- ]end"],
  "list_words": ["acceptable\\s+manufacturers?", "approved\\s+manufacturers?", "available\\s+manufacturers?", "manufacturers?\\s*:", "one\\s+of\\s+the\\s+following", "subject\\s+to\\s+compliance"],
  "sole_words": ["no\\s+substitutions?", "sole[- ]source", "no\\s+exceptions", "shall\\s+be\\s+unacceptable", "only\\s+systems\\s+that", "no\\s+other\\s+(?:manufacturer|system|vendor)s?"]
}
```

- [ ] **Step 2: Write the failing tests**

`tests/test_qualify.py` (the passages are made up for the tests, in the style of real specs):
```python
from estimator.catalogue.qualify import ReadingList, check_bid
from estimator.catalogue.register import PageRecord
from estimator.catalogue.spec_sections import SpecSection

CONTROLS = SpecSection("23 09 23", "INSTRUMENTATION AND CONTROL FOR HVAC", "spec.pdf", 1, 5)


def _pages(*texts, document="spec.pdf"):
    return [PageRecord(document, n, "text", t, 0) for n, t in enumerate(texts, start=1)]


def test_niagara_named_qualifies():
    pages = _pages("2.1 SYSTEM\nA. The BMS shall be built on the Tridium Niagara 4 Framework.")
    bid = check_bid(pages, [CONTROLS])
    assert bid.finding == "Qualifies"
    assert "Niagara N4" in bid.reason and "spec.pdf, page 1" in bid.reason
    assert bid.others == () and bid.controls_sections == ("23 09 23 INSTRUMENTATION AND CONTROL FOR HVAC",)
    assert "Tridium Niagara 4 Framework" in bid.mentions[0].quote


def test_an_approved_list_with_honeywell_qualifies_and_names_the_others():
    pages = _pages("2.2 CONTROL SYSTEM\nA. Available Manufacturers:\n1. Alerton Inc.\n2. Automated Logic Corporation.\n"
                   "3. Honeywell International Inc.\n4. Siemens Building Technologies.")
    bid = check_bid(pages, [CONTROLS])
    assert bid.finding == "Qualifies" and "Honeywell" in bid.reason
    assert bid.others == ("Alerton", "Automated Logic", "Siemens")


def test_another_manufacturer_as_basis_of_design_is_open():
    pages = _pages("2.1 MANUFACTURERS\nA. Basis of design: Siemens Desigo CC building automation system, or approved equal.")
    bid = check_bid(pages, [CONTROLS])
    assert bid.finding == "Open" and "Siemens" in bid.reason and bid.others == ("Siemens",)


def test_another_manufacturer_sole_source_does_not_qualify():
    pages = _pages("A. The building automation system shall be Automated Logic WebCTRL. No substitutions.")
    bid = check_bid(pages, [CONTROLS])
    assert bid.finding == "Does not qualify" and "Automated Logic" in bid.reason


def test_both_at_once_is_open_for_the_us_team():
    pages = _pages("A. The BMS shall be Automated Logic WebCTRL. No substitutions.",
                   "B. Integration to the owner's Niagara supervisor is required.")
    bid = check_bid(pages, [CONTROLS])
    assert bid.finding == "Open" and "two" in bid.reason


def test_silent_is_open():
    pages = _pages("PART 3 - EXECUTION\nA. Install the BMS per the drawings.")
    bid = check_bid(pages, [CONTROLS])
    assert (bid.finding, bid.others, bid.mentions) == ("Open", (), ())
    assert "names no controls manufacturer" in bid.reason


def test_no_controls_section_is_said_in_the_reason():
    bid = check_bid(_pages("Plumbing fixtures shall be by Kohler."), [])
    assert bid.finding == "Open" and "no controls section" in bid.reason


def test_a_name_outside_controls_is_ignored():
    pages = _pages("2.3 PACKAGED ROOFTOP UNITS\nA. Manufacturers: Trane, Carrier, Daikin.", document="hvac equipment.pdf")
    rooftop = SpecSection("23 74 13", "PACKAGED ROOFTOP UNITS", "hvac equipment.pdf", 1, 1)
    bid = check_bid(pages, [rooftop])
    assert (bid.finding, bid.others) == ("Open", ())


def test_a_name_with_controls_words_outside_a_controls_section_counts():
    pages = _pages("Unit controls shall be BACnet compatible for integration to the Siemens BMS.", document="equipment.pdf")
    bid = check_bid(pages, [])
    assert bid.others == ("Siemens",)


def test_metasys_is_not_the_line_we_bid():
    pages = _pages("A. The BMS shall be a Johnson Controls Metasys system.")
    bid = check_bid(pages, [CONTROLS])
    assert bid.finding == "Open" and bid.others == ("Johnson Controls Metasys",)


def test_names_in_capitals_are_found():
    pages = _pages("2.1 MANUFACTURERS\nA. SIEMENS BUILDING TECHNOLOGIES — BASIS OF DESIGN FOR THE BMS.")
    assert check_bid(pages, [CONTROLS]).others == ("Siemens",)


def test_carrier_in_lower_case_is_an_ordinary_word():
    pages = _pages("A. The BMS contractor shall coordinate with the telecom carrier for the internet connection.")
    assert check_bid(pages, [CONTROLS]).others == ()


def test_carrier_sense_is_a_network_term():
    pages = _pages("1. The BACnet IP network shall employ Carrier Sense Multiple Access/Collision Detection.")
    assert check_bid(pages, [CONTROLS]).others == ()


def test_the_reading_list_file_loads():
    reading = ReadingList.load()
    assert {"Honeywell WEBs", "Johnson Controls FX", "Niagara N4"} == {p.name for p in reading.ours}
```

- [ ] **Step 3: Run them to see them fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_qualify.py -v`
Expected: collection error — `ModuleNotFoundError: No module named 'estimator.catalogue.qualify'`.

- [ ] **Step 4: Write the code**

`src/estimator/catalogue/qualify.py`:
```python
"""The bid check: does the spec let AME bid this job? (design §8)

AME bids two Niagara N4 product lines, Honeywell WEBs and Johnson Controls FX. The check
finds every passage that names a controls manufacturer, quotes it word for word, and
sorts the job into Qualifies / Open / Does not qualify. The tool reports; the US team
decides. Every other controls manufacturer found is listed for them, whatever the finding.
"""
from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from estimator.catalogue.register import PageRecord
from estimator.catalogue.spec_sections import SpecSection

ASSETS = Path(__file__).resolve().parents[3] / "assets"
MANUFACTURERS = ASSETS / "reading_lists" / "manufacturers.json"
REACH = 350        # characters either side of a manufacturer's name that make up its passage


@dataclass(frozen=True)
class Named:
    name: str
    patterns: tuple[re.Pattern, ...]

    def found_in(self, text: str) -> bool:
        return any(p.search(text) for p in self.patterns)


@dataclass(frozen=True)
class ReadingList:
    ours: tuple[Named, ...]
    listed: tuple[Named, ...]
    others: tuple[Named, ...]
    controls_words: re.Pattern
    list_words: re.Pattern
    sole_words: re.Pattern

    @classmethod
    def load(cls, path: Path = MANUFACTURERS) -> "ReadingList":
        data = json.loads(Path(path).read_text(encoding="utf-8"))

        def named(key):
            return tuple(Named(e["name"], tuple(re.compile(p, 0 if e.get("exact_case") else re.I) for p in e["patterns"]))
                         for e in data[key])

        def words(key):
            return re.compile("|".join(f"(?:{w})" for w in data[key]), re.I)

        return cls(named("platforms_we_bid"), named("on_an_approved_list"), named("other_manufacturers"),
                   words("controls_words"), words("list_words"), words("sole_words"))

    def all_names(self) -> tuple[Named, ...]:
        return self.ours + self.listed + self.others


@dataclass(frozen=True)
class Mention:
    document: str
    page: int
    quote: str
    ours: tuple[str, ...]
    listed: tuple[str, ...]
    others: tuple[str, ...]
    sole: bool


@dataclass(frozen=True)
class BidCheck:
    finding: str                       # "Qualifies" | "Open" | "Does not qualify"
    reason: str                        # one plain sentence
    others: tuple[str, ...]            # every other controls manufacturer named — for the US team
    mentions: tuple[Mention, ...]
    controls_sections: tuple[str, ...]


def check_bid(pages: Sequence[PageRecord], sections: Sequence[SpecSection],
              reading: ReadingList | None = None) -> BidCheck:
    reading = reading or ReadingList.load()
    controls = [s for s in sections if s.controls]
    mentions = [m for record in pages for m in _mentions(record, controls, reading)]
    others = tuple(sorted({name for m in mentions for name in m.others}))
    section_names = tuple(dict.fromkeys(f"{s.number} {s.title}".strip() for s in controls))   # each named once
    finding, reason = _judge(mentions, others)
    if not controls:
        reason += " The specs have no controls section (23 09 xx, 159xx or Division 25) — the whole spec was searched."
    return BidCheck(finding, reason, others, tuple(mentions), section_names)


def _mentions(record: PageRecord, controls: Sequence[SpecSection], reading: ReadingList) -> list[Mention]:
    in_controls = any(s.document == record.document and s.first_page <= record.page <= s.last_page for s in controls)
    text = record.text
    windows = []
    for named in reading.all_names():
        for pattern in named.patterns:
            for match in pattern.finditer(text):
                start = text.rfind("\n", 0, max(0, match.start() - REACH)) + 1
                end = text.find("\n", min(len(text), match.end() + REACH))
                windows.append((start, len(text) if end == -1 else end))
    merged: list[list[int]] = []
    for start, end in sorted(windows):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    found = []
    for start, end in merged:
        passage = text[start:end]
        if not (in_controls or reading.controls_words.search(passage)):
            continue
        ours = tuple(n.name for n in reading.ours if n.found_in(passage))
        listed = tuple(n.name for n in reading.listed if n.found_in(passage)) if reading.list_words.search(passage) else ()
        others = tuple(n.name for n in reading.others if n.found_in(passage))
        if ours or listed or others:
            found.append(Mention(record.document, record.page, " ".join(passage.split()),
                                 ours, listed, others, bool(reading.sole_words.search(passage))))
    return found


def _where(mention: Mention) -> str:
    return f"{mention.document.rsplit('/', 1)[-1]}, page {mention.page}"


def _judge(mentions: Sequence[Mention], others: tuple[str, ...]) -> tuple[str, str]:
    qualifying = [m for m in mentions if m.ours or m.listed]
    blocking = [m for m in mentions if m.sole and m.others and not m.ours]
    if qualifying and blocking:
        return ("Open", f"The spec says two different things: it names {', '.join(qualifying[0].ours or qualifying[0].listed)} "
                        f"({_where(qualifying[0])}) but also requires {', '.join(blocking[0].others)} with no substitutions "
                        f"({_where(blocking[0])}). The US team decides.")
    if qualifying:
        first = next((m for m in qualifying if m.ours), qualifying[0])
        if first.ours:
            return "Qualifies", f"The spec names {', '.join(first.ours)} ({_where(first)})."
        verb = "is" if len(first.listed) == 1 else "are"
        return "Qualifies", f"{' and '.join(first.listed)} {verb} on the spec's list of acceptable manufacturers ({_where(first)})."
    if blocking:
        return ("Does not qualify", f"The spec requires {', '.join(blocking[0].others)} with no substitutions "
                                    f"({_where(blocking[0])}). The US team decides.")
    if others:
        return "Open", f"The spec names {', '.join(others)}, and none of the lines AME bids ({_where(mentions[0])}). The US team decides."
    return "Open", "The spec names no controls manufacturer at all. The US team decides."
```

- [ ] **Step 5: Run the tests to see them pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_qualify.py -v`
Expected: 14 passed.

- [ ] **Step 6: Run everything, then commit**

Run: `.venv/Scripts/python.exe -m pytest -q` — expected: all pass.
```bash
git add -A
git commit -m "feat: the bid check — Qualifies / Open / Does not qualify, with every passage quoted

<your Co-Authored-By line>"
```

---

### Task 8: Equipment tags — every spelling, and every place each appears

**Files:**
- Create: `assets/reading_lists/equipment.json`, `src/estimator/catalogue/tags.py`, `tests/test_tags.py`

**Interfaces:**
- Consumes: `PageRecord` (Task 3); `Sheet` (Task 5 — `Sheet(document, page, number, title, discipline, types)`).
- Produces:
  - `EQUIPMENT = ASSETS / "reading_lists" / "equipment.json"`
  - `Equipment` — loaded with `Equipment.load(path=EQUIPMENT)`, with the attributes:
    - `prefixes: dict[str, str]` (tag prefix → what it is);
    - `names: dict[str, str]` (written-out name → prefix);
    - `schedule_only: frozenset[str]`.
  - `find_tags(text: str, equipment: Equipment, exclude: frozenset[str] = frozenset()) -> list[str]` — every tag in the text, in order, repeats kept, each in its one spelling (`AHU-1`).
  - `TagEntry(tag: str, kind: str, on_schedules: tuple[str, ...], elsewhere: tuple[str, ...], times: int)` — frozen dataclass.
  - `index_tags(pages: Sequence[PageRecord], sheets: Mapping[tuple[str, int], Sheet], equipment: Equipment | None = None) -> list[TagEntry]`
  - `unlisted_prefixes(texts: Iterable[str], equipment: Equipment) -> Counter` — tag-shaped codes whose prefix isn't in the reading list yet, for the Learn check to show.

The rule (design §9.3, `step-3-facts.md` §7):
- A tag is a known prefix, an optional separator (hyphen, en or em dash, `#`, `No.`, or a space), then the rest: a digit followed by letters and digits, in dash-separated parts. So `AHU-1`, `VAV-21-01`, `CHLR-1CY40-A110` and `MUH05`-style codes all read.
- A tag like `CBH-A` (a letter after the hyphen) is also read, but only with a real hyphen or dash, so that `ACME` never reads as `AC-ME`.
- Whole-token only: `AHU-1` never matches inside `AHU-10`.
- `AHU 1`, `AHU#1`, `AHU–1`, `AHU No. 1` and "Air Handling Unit No. 1" are all `AHU-1`.
- The prefix must be in the reading list. That is what keeps `FLOOR 14`, `SUITE 310`, `R454B` and `M-101` out; the facts sheet showed a loose pattern turning these up by the hundred.
- The job's own sheet numbers are never tags. `P-101` is a plumbing sheet, not pump 101.
- Single-letter prefixes (`B` boiler, `P` pump) are counted only when the tag also appears on a schedule sheet. On its own, `P-1` is as likely to be a plumbing fixture.
- A place is the sheet number for a drawing sheet that has one, and otherwise "document name p.N".

- [ ] **Step 1: Write the reading list**

`assets/reading_lists/equipment.json`:
```json
{
  "about": "Equipment tag prefixes the tag index recognises (design §9.3). The Learn check lists tag-shaped codes whose prefix isn't here yet — add them here, never in code. Single-letter prefixes count only when the tag is on a schedule.",
  "prefixes": {
    "AHU": "Air Handling Unit", "RTU": "Rooftop Unit", "MAU": "Makeup Air Unit", "ERU": "Energy Recovery Unit",
    "ERV": "Energy Recovery Ventilator", "DOAS": "Dedicated Outdoor Air System", "HRU": "Heat Recovery Unit",
    "FCU": "Fan Coil Unit", "VAV": "Variable Air Volume Box", "CAV": "Constant Air Volume Box", "FPB": "Fan Powered Box",
    "FPV": "Fan Powered VAV", "FTR": "Finned Tube Radiation", "CUH": "Cabinet Unit Heater", "ECUH": "Electric Cabinet Unit Heater",
    "CBH": "Cabinet Heater", "EUH": "Electric Unit Heater", "UH": "Unit Heater", "UV": "Unit Ventilator", "BB": "Baseboard Heater",
    "EBB": "Electric Baseboard Heater", "ACU": "Air Curtain", "ARC": "Air Curtain",
    "EF": "Exhaust Fan", "TEF": "Toilet Exhaust Fan", "TX": "Toilet Exhaust Fan", "KEF": "Kitchen Exhaust Fan",
    "GEF": "General Exhaust Fan", "DWEF": "Dishwasher Exhaust Fan", "DX": "Dryer Exhaust Fan", "SF": "Supply Fan",
    "RF": "Return Fan", "SPF": "Stair Pressurization Fan", "SX": "Smoke Exhaust Fan", "IF": "Inline Fan", "CF": "Ceiling Fan",
    "CRAC": "Computer Room Air Conditioner", "CRAH": "Computer Room Air Handler", "ACCU": "Air Cooled Condensing Unit",
    "CU": "Condensing Unit", "OU": "Outdoor Unit", "AC": "Air Conditioning Unit", "HP": "Heat Pump", "WSHP": "Water Source Heat Pump",
    "GHP": "Geothermal Heat Pump", "IDU": "Indoor Unit", "ODU": "Outdoor Unit", "BS": "Branch Selector",
    "GV": "Gravity Ventilator", "EDH": "Electric Duct Heater", "DH": "Duct Heater",
    "CH": "Chiller", "CHLR": "Chiller", "ACCH": "Air Cooled Chiller", "CT": "Cooling Tower", "B": "Boiler", "BLR": "Boiler",
    "P": "Pump", "CHWP": "Chilled Water Pump", "HWP": "Hot Water Pump", "CWP": "Condenser Water Pump", "CHGP": "Chilled Glycol Pump",
    "GWP": "Glycol Water Pump", "BP": "Boiler Pump", "HX": "Heat Exchanger", "PFHX": "Plate Frame Heat Exchanger",
    "ET": "Expansion Tank", "AS": "Air Separator", "FSD": "Fire/Smoke Damper", "SD": "Smoke Damper", "MD": "Motorized Damper",
    "VFD": "Variable Frequency Drive", "HTCP": "Heat Trace Control Panel", "HUM": "Humidifier", "DHU": "Dehumidifier",
    "EVP": "Elevator Sump Pump", "SP": "Sump Pump", "WBP": "Water Booster Pump", "WH": "Water Heater", "DWH": "Domestic Water Heater"
  },
  "names": {
    "AIR HANDLING UNIT": "AHU", "ROOFTOP UNIT": "RTU", "MAKEUP AIR UNIT": "MAU", "MAKE-UP AIR UNIT": "MAU",
    "ENERGY RECOVERY UNIT": "ERU", "ENERGY RECOVERY VENTILATOR": "ERV", "FAN COIL UNIT": "FCU", "EXHAUST FAN": "EF",
    "SUPPLY FAN": "SF", "RETURN FAN": "RF", "UNIT HEATER": "UH", "CABINET UNIT HEATER": "CUH", "UNIT VENTILATOR": "UV",
    "CHILLER": "CH", "COOLING TOWER": "CT", "BOILER": "B", "PUMP": "P", "HEAT EXCHANGER": "HX", "EXPANSION TANK": "ET"
  },
  "schedule_only": ["B", "P"]
}
```

- [ ] **Step 2: Write the failing tests**

`tests/test_tags.py`:
```python
import pytest

from estimator.catalogue.register import PageRecord
from estimator.catalogue.sheet_types import Sheet
from estimator.catalogue.tags import Equipment, TagEntry, find_tags, index_tags, unlisted_prefixes

EQUIPMENT = Equipment.load()


@pytest.mark.parametrize("written", ["AHU-1", "AHU 1", "AHU#1", "AHU–1", "AHU — 1", "AHU No. 1", "AHU1",
                                     "Air Handling Unit No. 1", "AIR HANDLING UNIT #1"])
def test_every_spelling_is_one_tag(written):
    assert find_tags(f"serves {written}, on the roof", EQUIPMENT) == ["AHU-1"]


def test_ahu_1_is_never_ahu_10():
    assert find_tags("AHU-1 and AHU-10 and AHU-1A", EQUIPMENT) == ["AHU-1", "AHU-10", "AHU-1A"]


@pytest.mark.parametrize("text, tags", [("VAV-21-01", ["VAV-21-01"]), ("CHLR-1CY40-A110", ["CHLR-1CY40-A110"]),
                                        ("CBH-A", ["CBH-A"]), ("ECUH-5", ["ECUH-5"]), ("EF-2 & 3", ["EF-2"])])
def test_tag_shapes(text, tags):
    assert find_tags(text, EQUIPMENT) == tags


@pytest.mark.parametrize("text", ["SEE M-101", "FLOOR 14", "SUITE 310", "SECTION 230900", "R454B", "ACME CORP",
                                  "EFFICIENCY 2", "ahu-1 in lower case"])
def test_look_alikes_are_not_tags(text):
    assert find_tags(text, EQUIPMENT) == []


def test_the_jobs_own_sheet_numbers_are_not_tags():
    assert find_tags("SEE P-101 FOR PUMP P-1", EQUIPMENT, exclude=frozenset({"P-101"})) == ["P-1"]


def _record(document, page, text):
    return PageRecord(document, page, "text", text, 0)


def test_the_index_says_where_each_tag_appears():
    pages = [_record("mech.pdf", 1, "AIR HANDLING UNIT SCHEDULE\nAHU-1 AHU-2\nPUMP SCHEDULE P-1"),
             _record("mech.pdf", 2, "AHU-1 ON ROOF. AHU 1 CURB. EF-3. P-1 AND P-7. SEE P-101."),
             _record("spec.pdf", 4, "AHU-1 shall have a BACnet interface.")]
    sheets = {("mech.pdf", 1): Sheet("mech.pdf", 1, "M-601", "SCHEDULES", "Mechanical", ("Schedules",)),
              ("mech.pdf", 2): Sheet("mech.pdf", 2, "M-101", "FIRST FLOOR PLAN", "Mechanical", ("Plans",)),
              ("plumb.pdf", 1): Sheet("plumb.pdf", 1, "P-101", "PLUMBING PLAN", "Plumbing", ("Plans",))}
    assert index_tags(pages, sheets, EQUIPMENT) == [
        TagEntry("AHU-1", "Air Handling Unit", ("M-601",), ("M-101", "spec.pdf p.4"), 4),
        TagEntry("AHU-2", "Air Handling Unit", ("M-601",), (), 1),
        TagEntry("EF-3", "Exhaust Fan", (), ("M-101",), 1),
        TagEntry("P-1", "Pump", ("M-601",), ("M-101",), 2)]


def test_tags_sort_in_number_order():
    pages = [_record("mech.pdf", 1, "VAV-10 VAV-2 VAV-1 AHU-3")]
    tags = [e.tag for e in index_tags(pages, {}, EQUIPMENT)]
    assert tags == ["AHU-3", "VAV-1", "VAV-2", "VAV-10"]


def test_codes_with_an_unlisted_prefix_are_counted_for_the_learn_check():
    counts = unlisted_prefixes(["FFCH-548 FFCH-549 AHU-1 MUH-05", "XYZ-1"], EQUIPMENT)
    assert counts["FFCH"] == 2 and counts["MUH"] == 1 and counts["XYZ"] == 1 and "AHU" not in counts
```

- [ ] **Step 3: Run them to see them fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_tags.py -v`
Expected: collection error — `ModuleNotFoundError: No module named 'estimator.catalogue.tags'` (or `sheet_types`, if Task 5 isn't done yet — Task 5 comes first in execution order).

- [ ] **Step 4: Write the code**

`src/estimator/catalogue/tags.py`:
```python
"""Equipment tags — the codes that name each unit (AHU-1, VAV-21-01, EF-3) — in every
spelling, and every place each one appears (design §9.3)."""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from estimator.catalogue.register import PageRecord
from estimator.catalogue.sheet_types import Sheet

ASSETS = Path(__file__).resolve().parents[3] / "assets"
EQUIPMENT = ASSETS / "reading_lists" / "equipment.json"
_DASH = "-‐‑–—"
_TAG_SHAPED = re.compile(rf"(?<![A-Za-z0-9])([A-Z]{{2,5}})[{_DASH}]\d")


@dataclass(frozen=True)
class Equipment:
    prefixes: dict[str, str]
    names: dict[str, str]
    schedule_only: frozenset[str]

    @classmethod
    def load(cls, path: Path = EQUIPMENT) -> "Equipment":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(data["prefixes"], data["names"], frozenset(data["schedule_only"]))

    def patterns(self) -> tuple[re.Pattern, re.Pattern]:
        codes = "|".join(re.escape(p) for p in sorted(self.prefixes, key=len, reverse=True))
        rest = rf"\d[A-Z0-9]*(?:[{_DASH}][A-Z0-9]+)*"
        letter_rest = rf"[A-Z]{{1,2}}\d*(?:[{_DASH}][A-Z0-9]+)*"
        sep = rf"(?:\s*(?:[{_DASH}#]|No\.?)\s*|\s)"
        by_code = re.compile(rf"(?<![A-Za-z0-9])({codes})(?:{sep}?({rest})|[{_DASH}]({letter_rest}))(?![A-Za-z0-9])")
        names = "|".join(re.escape(n) for n in sorted(self.names, key=len, reverse=True))
        by_name = re.compile(rf"(?<![A-Za-z])({names})\s*(?:No\.?|#)\s*(\d[A-Z0-9]*)(?![A-Za-z0-9])", re.I)
        return by_code, by_name


def _canonical(prefix: str, rest: str) -> str:
    return f"{prefix}-{re.sub(f'[{_DASH}]', '-', rest)}"


def find_tags(text: str, equipment: Equipment, exclude: frozenset[str] = frozenset()) -> list[str]:
    by_code, by_name = equipment.patterns()
    found = [(m.start(), _canonical(m.group(1), m.group(2) or m.group(3))) for m in by_code.finditer(text)]
    found += [(m.start(), _canonical(equipment.names[m.group(1).upper()], m.group(2))) for m in by_name.finditer(text)]
    return [tag for _, tag in sorted(found) if tag not in exclude]


@dataclass(frozen=True)
class TagEntry:
    tag: str
    kind: str                       # what it is, from the reading list: "Air Handling Unit"
    on_schedules: tuple[str, ...]   # the schedule sheets it appears on
    elsewhere: tuple[str, ...]      # every other sheet or spec page it appears on
    times: int                      # how many times it appears in all


def _place(record: PageRecord, sheet: Sheet | None) -> str:
    if sheet is not None and sheet.number:
        return sheet.number
    return f"{record.document.rsplit('/', 1)[-1]} p.{record.page}"


def _natural(tag: str) -> list:
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", tag)]


def index_tags(pages: Sequence[PageRecord], sheets: Mapping[tuple[str, int], Sheet],
               equipment: Equipment | None = None) -> list[TagEntry]:
    equipment = equipment or Equipment.load()
    exclude = frozenset(_canonical(*n.split("-", 1)) if "-" in n else n
                        for n in (s.number for s in sheets.values() if s.number))
    on_schedules: dict[str, list[str]] = defaultdict(list)
    elsewhere: dict[str, list[str]] = defaultdict(list)
    times: Counter = Counter()
    for record in pages:
        sheet = sheets.get((record.document, record.page))
        place = _place(record, sheet)
        is_schedule = sheet is not None and "Schedules" in sheet.types
        for tag in find_tags(record.text, equipment, exclude):
            times[tag] += 1
            bucket = on_schedules if is_schedule else elsewhere
            if place not in bucket[tag]:
                bucket[tag].append(place)
    entries = []
    for tag in sorted(times, key=_natural):
        prefix = tag.split("-", 1)[0]
        if prefix in equipment.schedule_only and not on_schedules[tag]:
            continue
        entries.append(TagEntry(tag, equipment.prefixes[prefix], tuple(on_schedules[tag]), tuple(elsewhere[tag]), times[tag]))
    return entries


def unlisted_prefixes(texts: Iterable[str], equipment: Equipment) -> Counter:
    counts: Counter = Counter()
    for text in texts:
        counts.update(m.group(1) for m in _TAG_SHAPED.finditer(text) if m.group(1) not in equipment.prefixes)
    return counts
```

- [ ] **Step 5: Run the tests to see them pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_tags.py -v`
Expected: 27 passed (9 + 5 + 8 parametrized, and 5 others). If a spelling case fails, fix the pattern in `Equipment.patterns`, not the test.

- [ ] **Step 6: Run everything, then commit**

Run: `.venv/Scripts/python.exe -m pytest -q` — expected: all pass.
```bash
git add -A
git commit -m "feat: equipment tags in every spelling, and every place each appears

<your Co-Authored-By line>"
```

---

### Task 9: The Evidence Package

**Files:**
- Create: `src/estimator/catalogue/job.py` (the `Catalogue` record only — Task 10 adds the rest), `src/estimator/evidence/__init__.py`, `src/estimator/evidence/workbook.py`, `tests/test_evidence.py`

**Interfaces:**
- Consumes: `JobFolder`, `Document` (Task 2); `PageRecord` (Task 3); `Sheet` (Task 5); `SpecSection` (Task 6); `BidCheck`, `Mention` (Task 7); `TagEntry` (Task 8).
- Produces:
  - `Catalogue(job: JobFolder, pages: tuple[PageRecord, ...], sheets: tuple[Sheet, ...], sections: tuple[SpecSection, ...], bid: BidCheck, tags: tuple[TagEntry, ...], flags: tuple[str, ...])` — frozen dataclass in `estimator.catalogue.job`.
  - `write_evidence(path: Path, catalogue: Catalogue) -> Path`
  - `TABS = ("Bid check", "Flags", "Documents", "Pages", "Sheets", "Spec sections", "Equipment tags")`

The Evidence Package is the design's third deliverable (§1): "every quantity's provenance, every flag, every discrepancy". Build step 3 fills its first pages. The bid check comes first, because it is the first page the US team reads (design §8). Column headings are in the estimator's words.

- [ ] **Step 1: Write the failing tests**

`tests/test_evidence.py`:
```python
from pathlib import Path

import openpyxl

from estimator.catalogue.documents import Document, JobFolder
from estimator.catalogue.job import Catalogue
from estimator.catalogue.qualify import BidCheck, Mention
from estimator.catalogue.register import PageRecord
from estimator.catalogue.sheet_types import Sheet
from estimator.catalogue.spec_sections import SpecSection
from estimator.catalogue.tags import TagEntry
from estimator.evidence.workbook import TABS, write_evidence


def _catalogue() -> Catalogue:
    documents = (Document(Path("m.pdf"), "2. Takeoffs/1. Base Takeoff/Mech.pdf", "drawings", "base", 2),
                 Document(Path("s.pdf"), "2. Takeoffs/1. Base Takeoff/15970.pdf", "specs", "base", 1),
                 Document(Path("c.pdf"), "2. Takeoffs/1. Base Takeoff/copy.pdf", "drawings", "base", 2,
                          duplicate_of="2. Takeoffs/1. Base Takeoff/Mech.pdf"))
    job = JobFolder("26-9999", Path("26-9999"), documents, (), ("3. Proposal",))
    pages = (PageRecord(documents[0].relative, 1, "text", "AHU-1", 90), PageRecord(documents[0].relative, 2, "unreadable", "", 0),
             PageRecord(documents[1].relative, 1, "ocr", "SECTION 15970", 0))
    sheets = (Sheet(documents[0].relative, 1, "M-601", "HVAC SCHEDULES", "Mechanical", ("Schedules",)),
              Sheet(documents[0].relative, 2, None, None, "Unknown", ()))
    mention = Mention(documents[1].relative, 1, "The BMS shall be built on the Niagara 4 Framework.", ("Niagara N4",), (), (), False)
    bid = BidCheck("Qualifies", "The spec names Niagara N4 (15970.pdf, page 1).", ("Siemens",), (mention,), ("15970 TEMPERATURE CONTROL",))
    sections = (SpecSection("15970", "TEMPERATURE CONTROL", documents[1].relative, 1, 1),)
    tags = (TagEntry("AHU-1", "Air Handling Unit", ("M-601",), (), 1),)
    return Catalogue(job, pages, sheets, sections, bid, tags, ("Mech.pdf: 1 page could not be read (page 2)",))


def _values(ws):
    return [[c.value for c in row] for row in ws.iter_rows()]


def test_the_tabs_in_order(tmp_path):
    out = write_evidence(tmp_path / "26-9999 Evidence Package.xlsx", _catalogue())
    assert openpyxl.load_workbook(out).sheetnames == list(TABS)


def test_the_bid_check_comes_first_and_quotes_the_spec(tmp_path):
    ws = openpyxl.load_workbook(write_evidence(tmp_path / "e.xlsx", _catalogue()))["Bid check"]
    rows = _values(ws)
    assert rows[0][0] == "Bid check — 26-9999"
    assert ["Finding", "Qualifies"] == rows[2][:2]
    assert ["Other controls manufacturers named (for the US team)", "Siemens"] == rows[4][:2]
    assert ["2. Takeoffs/1. Base Takeoff/15970.pdf", 1, "Niagara N4",
            "The BMS shall be built on the Niagara 4 Framework."] in rows


def test_flags_documents_pages_sheets_sections_and_tags(tmp_path):
    wb = openpyxl.load_workbook(write_evidence(tmp_path / "e.xlsx", _catalogue()))
    assert _values(wb["Flags"])[1] == ["Mech.pdf: 1 page could not be read (page 2)"]
    assert _values(wb["Documents"])[3] == ["2. Takeoffs/1. Base Takeoff/copy.pdf", "Drawings", "base", 2,
                                           "2. Takeoffs/1. Base Takeoff/Mech.pdf"]
    assert _values(wb["Documents"])[4] == ["3. Proposal", "Left out — AME's own work, not a bid document", None, None, None]
    assert _values(wb["Pages"])[2] == ["2. Takeoffs/1. Base Takeoff/Mech.pdf", 2, "could not be read", None]
    assert _values(wb["Pages"])[1][3] == "M-601"
    assert _values(wb["Sheets"])[1] == ["M-601", "HVAC SCHEDULES", "Mechanical", "Schedules",
                                        "2. Takeoffs/1. Base Takeoff/Mech.pdf", 1]
    assert _values(wb["Spec sections"])[1] == ["15970", "TEMPERATURE CONTROL", "yes", "2. Takeoffs/1. Base Takeoff/15970.pdf", 1, 1]
    assert _values(wb["Equipment tags"])[1] == ["AHU-1", "Air Handling Unit", "M-601", None, 1]


def test_nothing_to_flag_says_so(tmp_path):
    from dataclasses import replace
    wb = openpyxl.load_workbook(write_evidence(tmp_path / "e.xlsx", replace(_catalogue(), flags=())))
    assert _values(wb["Flags"])[1] == ["Nothing to flag."]


def test_headings_are_bold_and_frozen(tmp_path):
    ws = openpyxl.load_workbook(write_evidence(tmp_path / "e.xlsx", _catalogue()))["Sheets"]
    assert ws["A1"].font.bold and ws.freeze_panes == "A2"
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_evidence.py -v`
Expected: collection error — `ModuleNotFoundError: No module named 'estimator.catalogue.job'`.

- [ ] **Step 3: Write the code**

`src/estimator/catalogue/job.py`:
```python
"""One job, catalogued: every stage of build step 3, and the flags an estimator should look at."""
from __future__ import annotations

from dataclasses import dataclass

from estimator.catalogue.documents import JobFolder
from estimator.catalogue.qualify import BidCheck
from estimator.catalogue.register import PageRecord
from estimator.catalogue.sheet_types import Sheet
from estimator.catalogue.spec_sections import SpecSection
from estimator.catalogue.tags import TagEntry


@dataclass(frozen=True)
class Catalogue:
    job: JobFolder
    pages: tuple[PageRecord, ...]
    sheets: tuple[Sheet, ...]
    sections: tuple[SpecSection, ...]
    bid: BidCheck
    tags: tuple[TagEntry, ...]
    flags: tuple[str, ...]
```

`src/estimator/evidence/__init__.py`:
```python
"""The Evidence Package: the job's record of what the tool found, and where."""
```

`src/estimator/evidence/workbook.py`:
```python
"""Write the Evidence Package (.xlsx).

The bid check is the first tab, because it is the first thing the US team reads (design
§8). Every page of every bid document is on the Pages tab, so a page that couldn't be read
is visible, never missing.
"""
from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from estimator.catalogue.job import Catalogue

TABS = ("Bid check", "Flags", "Documents", "Pages", "Sheets", "Spec sections", "Equipment tags")
_KIND = {"drawings": "Drawings", "specs": "Specs", "addendum": "Addendum", "rfi": "RFI", "other": "Other",
         "unreadable": "Could not be opened"}
_READ_BY = {"text": "its text", "ocr": "OCR", "blank": "blank page", "unreadable": "could not be read"}
_FINDING = {"Qualifies": "C6EFCE", "Open": "FFEB9C", "Does not qualify": "FFC7CE"}
_HEADING = PatternFill("solid", fgColor="D9E1F2")
_BOLD = Font(bold=True)
_WIDEST = 80


def write_evidence(path: Path, catalogue: Catalogue) -> Path:
    workbook = Workbook()
    workbook.remove(workbook.active)
    _bid_check(workbook.create_sheet(TABS[0]), catalogue)
    _table(workbook.create_sheet(TABS[1]), ["What to look at"], [[f] for f in catalogue.flags] or [["Nothing to flag."]])
    _table(workbook.create_sheet(TABS[2]), ["Document", "What it is", "Revision", "Pages", "Same file as"],
           [[d.relative, _KIND[d.kind], d.revision, d.pages, d.duplicate_of] for d in catalogue.job.documents]
           + [[folder, "Left out — AME's own work, not a bid document", None, None, None] for folder in catalogue.job.left_out])
    numbers = {(s.document, s.page): s.number for s in catalogue.sheets}
    _table(workbook.create_sheet(TABS[3]), ["Document", "Page", "Read by", "Sheet number"],
           [[p.document, p.page, _READ_BY[p.status], numbers.get((p.document, p.page))] for p in catalogue.pages])
    _table(workbook.create_sheet(TABS[4]), ["Sheet number", "Title", "Discipline", "Type", "Document", "Page"],
           [[s.number, s.title, s.discipline, ", ".join(s.types) or None, s.document, s.page] for s in catalogue.sheets])
    _table(workbook.create_sheet(TABS[5]), ["Section", "Title", "Controls section", "Document", "First page", "Last page"],
           [[s.number, s.title, "yes" if s.controls else "no", s.document, s.first_page, s.last_page]
            for s in catalogue.sections])
    _table(workbook.create_sheet(TABS[6]), ["Tag", "What it is", "On schedules", "Also appears on", "Times found"],
           [[t.tag, t.kind, ", ".join(t.on_schedules) or None, ", ".join(t.elsewhere) or None, t.times]
            for t in catalogue.tags])
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(str(path))
    return path


def _bid_check(ws, catalogue: Catalogue) -> None:
    bid = catalogue.bid
    ws.append([f"Bid check — {catalogue.job.name}"])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append([])
    ws.append(["Finding", bid.finding])
    ws["B3"].fill = PatternFill("solid", fgColor=_FINDING.get(bid.finding, "FFFFFF"))
    ws["B3"].font = _BOLD
    ws.append(["Why", bid.reason])
    ws.append(["Other controls manufacturers named (for the US team)", ", ".join(bid.others) or "none"])
    ws.append(["Controls sections in the specs", "; ".join(bid.controls_sections) or "none found"])
    ws.append(["The US team makes the final call. Every passage the check found is quoted below, word for word."])
    ws.append([])
    ws.append(["Document", "Page", "Manufacturers named", "What the spec says (word for word)"])
    for cell in ws[ws.max_row]:
        cell.font, cell.fill = _BOLD, _HEADING
    for m in bid.mentions:
        ws.append([m.document, m.page, ", ".join(m.ours + m.listed + m.others), m.quote])
        ws.cell(ws.max_row, 4).alignment = Alignment(wrap_text=True, vertical="top")
    for row in range(3, 7):
        ws.cell(row, 1).font = _BOLD
    ws.column_dimensions["A"].width = 52
    ws.column_dimensions["B"].width = 24
    ws.column_dimensions["C"].width = 30
    ws.column_dimensions["D"].width = 110


def _table(ws, headings: list[str], rows: list[list]) -> None:
    ws.append(headings)
    for cell in ws[1]:
        cell.font, cell.fill = _BOLD, _HEADING
    for row in rows:
        ws.append(row)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for index, heading in enumerate(headings, start=1):
        longest = max([len(heading)] + [len(str(r[index - 1])) for r in rows if r[index - 1] is not None])
        ws.column_dimensions[get_column_letter(index)].width = min(longest + 2, _WIDEST)
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_evidence.py -v`
Expected: 5 passed.

- [ ] **Step 5: Run everything, then commit**

Run: `.venv/Scripts/python.exe -m pytest -q` — expected: all pass.
```bash
git add -A
git commit -m "feat: the Evidence Package — bid check first, then flags, documents, pages, sheets, sections, tags

<your Co-Authored-By line>"
```

---

### Task 10: One job, catalogued — and the `catalogue` command

**Files:**
- Modify: `src/estimator/catalogue/job.py` (add `catalogue_job`, `summary_lines` and the flags)
- Modify: `src/estimator/__main__.py` (add the `catalogue` command)
- Create: `tests/test_catalogue_job.py`

**Interfaces:**
- Consumes: everything from Tasks 1–9.
- Produces:
  - `catalogue_job(root: Path, cache_dir: Path | None = None, workers: int = 1) -> Catalogue`
  - `summary_lines(catalogue: Catalogue) -> list[str]` — the plain-words summary the command prints.
  - `CONTROLS_DISCIPLINES = ("Mechanical", "Controls", "Plumbing", "Fire protection", "Unknown")` — the disciplines whose unsorted sheets are flagged.
  - `python -m estimator catalogue JOB_FOLDER --out FOLDER [--workers N]` — writes `FOLDER/<job> Evidence Package.xlsx`; caches page reads in `FOLDER/.cache`.

The flags, in plain words, in this order. AME's own folders that were left out aren't flags; they are listed on the Documents tab.
1. Another job's folder found inside this one.
2. Documents that couldn't be opened.
3. Documents stored twice.
4. Pages that couldn't be read, one line per document. The page numbers are written as ranges ("3–7, 9"), and each line gives the reason: OCR found no words on them, or OCR isn't set up on this computer.
5. Drawing sheets with no sheet number found, one line per document.
6. Drawing sheets that couldn't be sorted by type, one line, naming up to 20 of them. Only the disciplines that carry controls scope count: mechanical, controls, plumbing, fire protection, and unknown. An electrical grounding sheet with no type is not worth the estimator's time.
7. A sheet number that appears on more than one page, excluding a document stored twice: "Sheet M-206.00 is on 15 pages (Marked-Mech.pdf p.9–23)". This is usually a marked copy next to an unmarked one, or a typical floor repeated.
8. The bid check, when it isn't "Qualifies": "Bid check: Open — the US team decides before this job is issued."

- [ ] **Step 1: Write the failing tests**

`tests/test_catalogue_job.py`:
```python
import openpyxl
import pytest

from estimator.__main__ import main
from estimator.catalogue.job import catalogue_job, summary_lines
from pdfs import FILLER, Page, make_pdf

SCHEDULE = Page(width=3024, height=2160, texts=((200, 300, FILLER, 12), (300, 400, "AIR HANDLING UNIT SCHEDULE", 18),
                                                (300, 450, "AHU-1  AHU-2", 12), (2640, 1860, "HVAC SCHEDULES", 20),
                                                (2800, 2000, "M-601", 40)))
PLAN = Page(width=3024, height=2160, texts=((200, 300, FILLER, 12), (900, 900, "AHU-1 ON ROOF", 12),
                                            (2640, 1860, "ROOF PLAN", 20), (2800, 2000, "M-101", 40)))
NO_NUMBER = Page(width=3024, height=2160, texts=((200, 300, FILLER, 12),))
SPEC = Page(texts=((72, 72, "SECTION 23 09 23 - INSTRUMENTATION AND CONTROL FOR HVAC\n"
                            "2.1 SYSTEM\nA. The BMS shall be built on the Tridium Niagara 4 Framework.\n23 09 23 - 1", 10),))


@pytest.fixture
def job(tmp_path):
    root = tmp_path / "26-9999, 1 Test Street"
    base = root / "2. Takeoffs" / "1. Base Takeoff"
    make_pdf(base / "Mech.pdf", SCHEDULE, PLAN, NO_NUMBER)
    make_pdf(base / "Marked_230923.pdf", SPEC)
    (base / "broken.pdf").write_bytes(b"not a pdf")
    return root


def test_every_stage_runs(job, tmp_path):
    result = catalogue_job(job, tmp_path / "cache")
    assert result.job.name == "26-9999"
    assert [p.status for p in result.pages] == ["text", "text", "text", "text"]
    assert [(s.number, s.title) for s in result.sheets] == [("M-601", "HVAC SCHEDULES"), ("M-101", "ROOF PLAN"), (None, None)]
    assert "Schedules" in result.sheets[0].types and "Plans" in result.sheets[1].types
    assert [(s.number, s.controls) for s in result.sections] == [("23 09 23", True)]
    assert result.bid.finding == "Qualifies"
    [ahu1, ahu2] = result.tags
    assert (ahu1.tag, ahu1.on_schedules, ahu1.elsewhere) == ("AHU-1", ("M-601",), ("M-101",))
    assert ahu2.tag == "AHU-2"


def test_the_flags(job, tmp_path):
    flags = catalogue_job(job, tmp_path / "cache").flags
    assert any("broken.pdf could not be opened" in f for f in flags)
    assert any("Mech.pdf: no sheet number found on 1 of 3 sheets (page 3)" in f for f in flags)


def test_the_summary_is_in_plain_words(job, tmp_path):
    lines = summary_lines(catalogue_job(job, tmp_path / "cache"))
    assert lines[0] == "26-9999 — 3 documents, 4 pages: 0 read by OCR, 0 blank, 0 could not be read."
    assert lines[1].startswith("Bid check: Qualifies — The spec names Niagara N4")


def test_the_command_writes_the_evidence_package(job, tmp_path, capsys):
    out = tmp_path / "out"
    assert main(["catalogue", str(job), "--out", str(out), "--workers", "1"]) == 0
    package = out / "26-9999 Evidence Package.xlsx"
    assert openpyxl.load_workbook(package).sheetnames[0] == "Bid check"
    printed = capsys.readouterr().out
    assert "Bid check: Qualifies" in printed and f"Wrote {package}" in printed


def test_a_missing_job_folder_is_plain(tmp_path, capsys):
    assert main(["catalogue", str(tmp_path / "nowhere"), "--out", str(tmp_path / "out")]) == 1
    assert capsys.readouterr().err.strip() == f"Stopped: can't find {tmp_path / 'nowhere'}"
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_catalogue_job.py -v`
Expected: FAIL — `ImportError: cannot import name 'catalogue_job'`.

- [ ] **Step 3: Write the code**

Append to `src/estimator/catalogue/job.py` (keep the `Catalogue` class; add these imports at the top with the others):
```python
from collections import defaultdict
from pathlib import Path

from estimator.catalogue.documents import find_documents
from estimator.catalogue.pdf import tessdata
from estimator.catalogue.qualify import check_bid
from estimator.catalogue.register import register_job
from estimator.catalogue.sheet_types import classify_sheet
from estimator.catalogue.spec_sections import index_sections
from estimator.catalogue.tags import index_tags
from estimator.catalogue.title_block import read_title_block
```
and after the class:
```python
CONTROLS_DISCIPLINES = ("Mechanical", "Controls", "Plumbing", "Fire protection", "Unknown")


def catalogue_job(root: Path, cache_dir: Path | None = None, workers: int = 1) -> Catalogue:
    job = find_documents(root)
    pages = tuple(register_job(job, cache_dir, workers))
    kinds = {d.relative: d.kind for d in job.documents}
    sheets = tuple(classify_sheet(record, read_title_block(record.edge_spans))
                   for record in pages if kinds[record.document] == "drawings")
    written = [record for record in pages if kinds[record.document] != "drawings"]
    sections = tuple(index_sections(written))
    bid = check_bid(written, sections)
    tags = tuple(index_tags(pages, {(s.document, s.page): s for s in sheets}))
    catalogue = Catalogue(job, pages, sheets, sections, bid, tags, ())
    return Catalogue(job, pages, sheets, sections, bid, tags, tuple(_flags(catalogue)))


def _name(relative: str) -> str:
    return relative.rsplit("/", 1)[-1]


def _ranges(numbers: list[int]) -> str:
    runs: list[list[int]] = []
    for n in sorted(numbers):
        if runs and n == runs[-1][1] + 1:
            runs[-1][1] = n
        else:
            runs.append([n, n])
    return ", ".join(str(a) if a == b else f"{a}–{b}" for a, b in runs)


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _flags(catalogue: Catalogue) -> list[str]:
    job = catalogue.job
    flags = list(job.notes)
    flags += [f"{d.relative} could not be opened — is it a real PDF?" for d in job.documents if d.kind == "unreadable"]
    flags += [f"{d.relative} is the same file as {d.duplicate_of} — catalogued once" for d in job.documents if d.duplicate_of]
    unreadable: dict[str, list[int]] = defaultdict(list)
    for record in catalogue.pages:
        if record.status == "unreadable":
            unreadable[record.document].append(record.page)
    why = "OCR found no words on them" if tessdata() is not None else "OCR isn't set up on this computer"
    flags += [f"{_name(doc)}: {_plural(len(p), 'page')} could not be read ({'page' if len(p) == 1 else 'pages'} {_ranges(p)}) — {why}"
              for doc, p in unreadable.items()]
    per_document: dict[str, list] = defaultdict(list)
    for sheet in catalogue.sheets:
        per_document[sheet.document].append(sheet)
    for doc, sheets in per_document.items():
        missing = [s.page for s in sheets if not s.number]
        if missing:
            flags.append(f"{_name(doc)}: no sheet number found on {len(missing)} of {len(sheets)} sheets "
                         f"({'page' if len(missing) == 1 else 'pages'} {_ranges(missing)})")
    untyped = [s for s in catalogue.sheets if s.number and not s.types and s.discipline in CONTROLS_DISCIPLINES]
    if untyped:
        names = ", ".join(s.number for s in untyped[:20]) + (" …" if len(untyped) > 20 else "")
        flags.append(f"{_plural(len(untyped), 'drawing sheet')} could not be sorted by type — {names}")
    places: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    for sheet in catalogue.sheets:
        if sheet.number:
            places[sheet.number][sheet.document].append(sheet.page)
    for number, by_document in places.items():
        count = sum(len(p) for p in by_document.values())
        if count > 1:
            where = "; ".join(f"{_name(doc)} p.{_ranges(p)}" for doc, p in by_document.items())
            flags.append(f"Sheet {number} is on {count} pages ({where})")
    if catalogue.bid.finding != "Qualifies":
        flags.append(f"Bid check: {catalogue.bid.finding} — the US team decides before this job is issued")
    return flags


def summary_lines(catalogue: Catalogue) -> list[str]:
    pages = catalogue.pages
    count = {status: sum(1 for p in pages if p.status == status) for status in ("ocr", "blank", "unreadable")}
    bid = catalogue.bid
    sheets = catalogue.sheets
    controls = list(dict.fromkeys(f"{s.number} {s.title}".strip() for s in catalogue.sections if s.controls))
    return [
        f"{catalogue.job.name} — {len(catalogue.job.documents)} documents, {len(pages)} pages: "
        f"{count['ocr']} read by OCR, {count['blank']} blank, {count['unreadable']} could not be read.",
        f"Bid check: {bid.finding} — {bid.reason}",
        f"Other controls manufacturers named, for the US team: {', '.join(bid.others) or 'none'}.",
        f"Drawing sheets: {len(sheets)}; {sum(1 for s in sheets if s.number)} with a sheet number; "
        f"{sum(1 for s in sheets if s.number and not s.types and s.discipline in CONTROLS_DISCIPLINES)} "
        f"mechanical, controls or plumbing sheets not sorted by type.",
        f"Spec sections: {len(catalogue.sections)}; controls sections: {'; '.join(controls) or 'none found'}.",
        f"Equipment tags: {len(catalogue.tags)} ({sum(1 for t in catalogue.tags if t.on_schedules)} on schedules).",
        f"{_plural(len(catalogue.flags), 'thing')} to look at — see the Flags tab." if catalogue.flags else "Nothing to flag.",
    ]
```

In `src/estimator/__main__.py`:
- add to the imports:
```python
from estimator.catalogue.job import catalogue_job, summary_lines
from estimator.evidence.workbook import write_evidence
```
- add the command's usage line to the module docstring: `    python -m estimator catalogue JOB_FOLDER --out FOLDER`
- in `_parser()`, before `return parser`:
```python
    catalogue = commands.add_parser("catalogue", help="check the job can be bid, and catalogue every page")
    catalogue.add_argument("job", type=Path)
    catalogue.add_argument("--out", type=Path, required=True)
    catalogue.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1))
```
- in `_run()`, before `return 0`:
```python
    elif args.command == "catalogue":
        result = catalogue_job(args.job, args.out / ".cache", args.workers)
        package = write_evidence(args.out / f"{_safe_filename(result.job.name)} Evidence Package.xlsx", result)
        for line in summary_lines(result):
            print(line)
        print(f"Wrote {package}")
```
`find_documents` raises `FileNotFoundError` for a missing folder, which `main()` already turns into `Stopped: can't find …`.

- [ ] **Step 4: Run the tests to see them pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_catalogue_job.py -v`
Expected: 5 passed.

- [ ] **Step 5: Run everything, then commit**

Run: `.venv/Scripts/python.exe -m pytest -q` — expected: all pass.
```bash
git add -A
git commit -m "feat: the catalogue command — one job, every stage, flags in plain words

<your Co-Authored-By line>"
```

---

### Task 11: The Learn check — all nine jobs, against what the estimator concluded

**Files:**
- Create: `tests/data/learn_expectations.json`, `tools/learn_check.py`, `tests/test_learn_check.py`

**Interfaces:**
- Consumes: `catalogue_job`, `summary_lines` (Task 10); `write_evidence` (Task 9); `unlisted_prefixes`, `Equipment` (Task 8).
- Produces:
  - `.venv/Scripts/python.exe tools/learn_check.py [--jobs 26-0246 26-0352 …] [--workers N]` — catalogues each Learn job into `out/learn/<job>/`, prints one table and writes it to `out/learn/learn-check.md`. It exits 1 if any job misses its expectation.
  - In the tool module:
    - `JobResult(job, pages, ocr, unreadable, sheets, numbered, relevant, typed, controls_sections, bid, others, tags)` — dataclass; `relevant` counts the sheets in `CONTROLS_DISCIPLINES`, and `typed` counts how many of those were sorted;
    - `measure(catalogue) -> JobResult`;
    - `misses(result: JobResult, expected: dict) -> list[str]`;
    - `find_job(learn: Path, key: str) -> Path`.

This is the step's acceptance test on real documents. It reads `D:\Estimation Assistant\Learn` and writes nothing there. What each job is expected to show comes from `step-3-facts.md`:
- **§6: the bid check.** 26-0436's own specs weren't read for it, since the Niagara quote came from 26-0437's folder, so its expectation is `null`: the result is reported, not checked.
- **§3: the sheet-number hit rate.** The expectations are the measured rates after the two-part-number fix, rounded down.
- **§5: the controls sections.** 26-0352 has no spec at all.

26-0437 sits inside 26-0436 and is catalogued as a job of its own.

- [ ] **Step 1: Write the expectations**

`tests/data/learn_expectations.json`:
```json
{
  "about": "What the estimator concluded for each Learn job (docs/superpowers/plans/step-3-facts.md). bid null = report the result, don't check it. sheet_numbers_at_least / typed_at_least = share of drawing sheets whose sheet number must be found / that must be sorted by type.",
  "learn_folder": "D:\\Estimation Assistant\\Learn",
  "jobs": {
    "26-0246": {"bid": "Qualifies", "sheet_numbers_at_least": 0.99, "typed_at_least": 0.90, "controls_sections": true},
    "26-0328": {"bid": "Open", "sheet_numbers_at_least": 0.80, "typed_at_least": 0.70, "controls_sections": true},
    "26-0334": {"bid": "Qualifies", "sheet_numbers_at_least": 0.70, "typed_at_least": 0.50, "controls_sections": true},
    "26-0339": {"bid": "Open", "sheet_numbers_at_least": 0.99, "typed_at_least": 0.90, "controls_sections": true},
    "26-0344": {"bid": "Qualifies", "sheet_numbers_at_least": 0.99, "typed_at_least": 0.90, "controls_sections": true},
    "26-0352": {"bid": "Open", "sheet_numbers_at_least": 0.99, "typed_at_least": 0.90, "controls_sections": false},
    "26-0356": {"bid": "Qualifies", "sheet_numbers_at_least": 0.99, "typed_at_least": 0.85, "controls_sections": true},
    "26-0436": {"bid": null, "sheet_numbers_at_least": 0.90, "typed_at_least": 0.70, "controls_sections": true},
    "26-0437": {"bid": "Qualifies", "sheet_numbers_at_least": 0.95, "typed_at_least": 0.80, "controls_sections": true},
    "26-0445": {"bid": "Open", "sheet_numbers_at_least": 0.90, "typed_at_least": 0.70, "controls_sections": true}
  }
}
```

- [ ] **Step 2: Write the failing tests** (for the comparison and the folder search — the tool's run over real jobs is Step 5, not a test)

`tests/test_learn_check.py`:
```python
import importlib.util
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location("learn_check", Path(__file__).resolve().parents[1] / "tools" / "learn_check.py")
learn_check = importlib.util.module_from_spec(_spec)
sys.modules["learn_check"] = learn_check     # a dataclass needs its module registered while it is defined
_spec.loader.exec_module(learn_check)


def _result(**changes):
    base = dict(job="26-9999", pages=10, ocr=0, unreadable=0, sheets=10, numbered=10, relevant=10, typed=9,
                controls_sections=1, bid="Qualifies", others=(), tags=5)
    return learn_check.JobResult(**{**base, **changes})


EXPECTED = {"bid": "Qualifies", "sheet_numbers_at_least": 0.99, "typed_at_least": 0.85, "controls_sections": True}


def test_a_job_that_meets_its_expectations():
    assert learn_check.misses(_result(), EXPECTED) == []


def test_each_kind_of_miss_is_said_in_plain_words():
    found = learn_check.misses(_result(bid="Open", numbered=8, typed=5, controls_sections=0),
                               {**EXPECTED, "sheet_numbers_at_least": 0.9})
    assert found == ["bid check said Open, the estimator concluded Qualifies",
                     "sheet numbers found on 80% of drawing sheets, expected at least 90%",
                     "sorted by type on 50% of mechanical, controls and plumbing sheets, expected at least 85%",
                     "no controls section found, and the job has one"]


def test_a_bid_expectation_of_null_is_only_reported():
    assert learn_check.misses(_result(bid="Open"), {**EXPECTED, "bid": None}) == []


def test_a_job_with_no_drawings_is_not_a_sheet_miss():
    assert learn_check.misses(_result(sheets=0, numbered=0, relevant=0, typed=0), EXPECTED) == []


def test_finding_a_job_folder_by_its_number(tmp_path):
    (tmp_path / "26-0352, Tishman Speyer, 45 Rockefeller").mkdir()
    nested = tmp_path / "26-0436, Equinix" / "2. Takeoffs" / "1. Base Takeoff" / "26-0437"
    nested.mkdir(parents=True)
    assert learn_check.find_job(tmp_path, "26-0352") == tmp_path / "26-0352, Tishman Speyer, 45 Rockefeller"
    assert learn_check.find_job(tmp_path, "26-0437") == nested
```

- [ ] **Step 3: Run them to see them fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_learn_check.py -v`
Expected: FAIL — `FileNotFoundError` for `tools/learn_check.py`.

- [ ] **Step 4: Write the tool**

`tools/learn_check.py`:
```python
"""Catalogue the Learn jobs and compare each with what the estimator concluded.

    .venv/Scripts/python.exe tools/learn_check.py [--jobs 26-0246 26-0352] [--workers 4]

Reads the Learn folder (read-only) and writes only under out/learn/. Exits 1 if any job
misses its expectation in tests/data/learn_expectations.json.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTATIONS = ROOT / "tests" / "data" / "learn_expectations.json"
OUT = ROOT / "out" / "learn"


@dataclass(frozen=True)
class JobResult:
    job: str
    pages: int
    ocr: int
    unreadable: int
    sheets: int
    numbered: int
    relevant: int          # sheets in the disciplines that carry controls scope (CONTROLS_DISCIPLINES)
    typed: int             # of those, how many were sorted by type
    controls_sections: int
    bid: str
    others: tuple[str, ...]
    tags: int


def measure(catalogue) -> JobResult:
    from estimator.catalogue.job import CONTROLS_DISCIPLINES
    pages, sheets = catalogue.pages, catalogue.sheets
    relevant = [s for s in sheets if s.discipline in CONTROLS_DISCIPLINES]
    return JobResult(
        job=catalogue.job.name, pages=len(pages),
        ocr=sum(1 for p in pages if p.status == "ocr"), unreadable=sum(1 for p in pages if p.status == "unreadable"),
        sheets=len(sheets), numbered=sum(1 for s in sheets if s.number),
        relevant=len(relevant), typed=sum(1 for s in relevant if s.types),
        controls_sections=sum(1 for s in catalogue.sections if s.controls),
        bid=catalogue.bid.finding, others=catalogue.bid.others, tags=len(catalogue.tags))


def misses(result: JobResult, expected: dict) -> list[str]:
    found = []
    if expected["bid"] is not None and result.bid != expected["bid"]:
        found.append(f"bid check said {result.bid}, the estimator concluded {expected['bid']}")
    if result.sheets:
        share = result.numbered / result.sheets
        if share < expected["sheet_numbers_at_least"]:
            found.append(f"sheet numbers found on {share:.0%} of drawing sheets, "
                         f"expected at least {expected['sheet_numbers_at_least']:.0%}")
    if result.relevant:
        typed = result.typed / result.relevant
        if typed < expected["typed_at_least"]:
            found.append(f"sorted by type on {typed:.0%} of mechanical, controls and plumbing sheets, "
                         f"expected at least {expected['typed_at_least']:.0%}")
    if expected["controls_sections"] and not result.controls_sections:
        found.append("no controls section found, and the job has one")
    if not expected["controls_sections"] and result.controls_sections:
        found.append(f"{result.controls_sections} controls sections found, and the job has none")
    return found


def find_job(learn: Path, key: str) -> Path:
    """The job's folder: a folder whose name starts with the job number, at any depth up to four."""
    for depth in range(1, 5):
        for folder in sorted(learn.glob("/".join(["*"] * depth))):
            if folder.is_dir() and folder.name.split(",")[0].strip() == key:
                return folder
    raise FileNotFoundError(2, "No such job folder", str(learn / key))


def main(argv: list[str] | None = None) -> int:
    from estimator.catalogue.job import catalogue_job, summary_lines
    from estimator.catalogue.tags import Equipment, unlisted_prefixes
    from estimator.evidence.workbook import write_evidence

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", nargs="*")
    parser.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1))
    args = parser.parse_args(argv)
    expectations = json.loads(EXPECTATIONS.read_text(encoding="utf-8"))
    learn = Path(expectations["learn_folder"])
    keys = args.jobs or list(expectations["jobs"])
    lines = ["| Job | Pages | OCR | Could not read | Drawing sheets | With number | Mech/controls/plumbing sorted by type | Controls sections "
             "| Bid check | Other manufacturers | Tags | Misses |", "|" + "---|" * 12]
    total_misses, unlisted = 0, {}
    equipment = Equipment.load()
    for key in keys:
        folder = find_job(learn, key)
        print(f"Cataloguing {key} …", flush=True)
        catalogue = catalogue_job(folder, OUT / ".cache", args.workers)
        write_evidence(OUT / key / f"{key} Evidence Package.xlsx", catalogue)
        for line in summary_lines(catalogue):
            print("   " + line)
        result = measure(catalogue)
        found = misses(result, expectations["jobs"][key])
        total_misses += len(found)
        for prefix, n in unlisted_prefixes((p.text for p in catalogue.pages), equipment).items():
            unlisted[prefix] = unlisted.get(prefix, 0) + n
        share = lambda n, of: f"{n} of {of} ({n / of:.0%})" if of else "—"
        lines.append(f"| {key} | {result.pages} | {result.ocr} | {result.unreadable} | {result.sheets} "
                     f"| {share(result.numbered, result.sheets)} | {share(result.typed, result.relevant)} "
                     f"| {result.controls_sections} | {result.bid} | {', '.join(result.others) or '—'} "
                     f"| {result.tags} | {'; '.join(found) or 'none'} |")
    common = sorted(unlisted.items(), key=lambda kv: -kv[1])[:25]
    lines += ["", "Tag-shaped codes whose prefix isn't in assets/reading_lists/equipment.json yet (most common first):",
              ", ".join(f"{p} ×{n}" for p, n in common) or "none"]
    report = "\n".join(lines) + "\n"
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "learn-check.md").write_text(report, encoding="utf-8")
    print(report)
    return 1 if total_misses else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run the tests, then run the check over all ten jobs**

Run: `.venv/Scripts/python.exe -m pytest tests/test_learn_check.py -v` — expected: 5 passed.
Run: `.venv/Scripts/python.exe -m pytest -q` — expected: all pass.

Then run it over the real jobs. The first run takes a while (26-0436 and 26-0445 are about five minutes each); later runs read the cache:
```bash
.venv/Scripts/python.exe tools/learn_check.py
```
Paste the whole printed output into your task report. **Do not change any code, reading list or expectation to make a miss go away.** Report each miss as it is, with what you see when you look at the page it concerns: the sheet number and title the tool read against what the sheet says, or the passage the bid check quoted. The controller rules on each one.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: the Learn check — catalogue every Learn job and compare with the estimator's conclusions

<your Co-Authored-By line>"
```

- [ ] **Step 7: Stop — the estimator checks two jobs by eye**

Hand the estimator, in plain words:
- `out/learn/26-0246/26-0246 Evidence Package.xlsx` and one larger job's Evidence Package;
- the Learn check table.

Ask:
- whether the bid check reads the way they would read the spec;
- whether the sheet list and its types match the drawings;
- whether any flag is noise.

Build step 3 is done when they say so.

---

## Self-review notes (for the controller)

- Design §8, the bid check: Task 7, with the reading list as data; the Evidence Package's first tab in Task 9.
- Design §9.1, recall: the page register (Task 3) and the unreadable-page flags (Task 10). The legend and keynote extraction named in §9.1 belong with device counting in build step 4, and are not in this plan.
- §9.2, sheet typing: Task 5, with the reading list as data. The per-type reading lists are build step 4.
- §9.3, aliases: Task 8.
- §9.4–9.6 (authority ladder, supersession, revision diff) are build step 4. Task 2 records each document's kind and revision so that step 4 has them.
