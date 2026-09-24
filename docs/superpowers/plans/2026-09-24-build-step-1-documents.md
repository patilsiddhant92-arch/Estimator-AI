# Build Step 1 — Make the Documents Come Out Right: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Given the scope of one job, produce a proposal and a price sheet that match what an AME estimator actually sends — proven on job 26-0246 — before the tool reads a single drawing.

**Architecture:** One `Job` (pydantic) holds the scope. A proposal writer fills the team's own Word template in place with python-docx; a price-sheet writer fills the team's own price workup with openpyxl, typing only into input cells so every formula survives. A proposal reader turns a sent proposal back into a `Job`, which is how the test job is made and how the round trip is proven. The price sheet is priced from the AME price book by strict name match only; anything else is marked PRICE PENDING.

**Tech Stack:** Python 3.13.15 · pydantic 2.13.5 · python-docx 1.2.0 · openpyxl 3.1.5 · pillow 12.3.0 · lxml 6.1.3 · pytest 9.1.1 · pymupdf 1.28.2 (review tool only) · Microsoft Word and Excel through PowerShell (review tool only)

**Spec:** `docs/superpowers/specs/2026-09-24-estimator-ai-design.md` — build step 1 in §14, the input assets in §6, the six guarantees in §5.

## Global Constraints

- **Interpreter:** always `.venv/Scripts/python.exe` (Python 3.13.15). The bare `python` on this machine is 3.14.4 and belongs to another project — never use it for this repo.
- **Pinned dependencies:** `pydantic==2.13.5`, `python-docx==1.2.0`, `openpyxl==3.1.5`, `pillow==12.3.0`, `lxml==6.1.3`; dev: `pytest==9.1.1`, `pymupdf==1.28.2`. Do not add others.
- **Read-only folders:** `D:\AME Estimation` and `D:\Estimation Assistant`. Copy files *out* of them in Task 1; never write, build or run tests inside them.
- **The template owns the boilerplate:** no clarification, exclusion, cover-page, back-page or signature text is ever written from code. The tool writes only fields of the `Job`.
- **Nothing internal reaches the proposal:** no emoji, no flag words, no tool names, no confidence scores in the `.docx`.
- **No guessing a price:** a line is priced only on an exact name match against the price book or an entry in `assets/price_book/aliases.json`. Otherwise it is PRICE PENDING.
- **Never write to a formula cell** in the price workup. Load it with openpyxl's default (`data_only=False`).
- **Plain language** in everything an estimator reads — the price check report, command-line messages, error messages. Their trade terms (VAV, AHU, VFD, keynote, riser) are fine; software terms are not.
- **Commit after each task. Never push.** Every commit message ends with a blank line and `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Executors work alone** — do not spawn subagents.
- **All commands run from the repo root** (`D:\Àpps\Estimator AI`) in Git Bash. The path contains `À` and a space; keep paths quoted.

## What was measured while planning

Read this before starting. Every number below was measured on the real files, and the tests pin them.

**The proposal template** (`AME_nordomatic Proposal Template.docx`, the team's master in `D:\AME Estimation\2026\NEW TEMPLATE\`):
- Cover page: a table. Labels are red (`EC1E27`), values dark (`231F20`). Cells: `To: All Bidders`; `Date:` followed by a live Word `DATE` field (it shows *today* every time the file opens); `Quote #: 26-#####`; `Reference: ########`; `MEP Engineer: #######`; `Based on Plans and Specs:` with `########` on the next line.
- Two openings, in this order: new system (`A.M.E., Inc, is pleased…Automated Temperature Controls system.`), then `SCOPE OF WORK –`, then `Front End Web Enabled BMS System` and its default lines including an `IT Infrastructure – By AME or by Others?` question; then an `OR` line; then the extend-existing opening, its own `SCOPE OF WORK –`, and `Seamlessly Tie in to the Existing Honeywell / Niagara N4 BMS` — the name typed in **red (`FF0000`)** as a placeholder — with three default lines. Then `ADD ALTERNATES:` / `ALT #:` / `DEDUCT ALTERNATES:` / `ALT #:`, the clarifications, 37 exclusions, the base price lines and the signature.
- **The template has no example of an equipment block.** Estimators paste block formatting in from older proposals.
- Styles `PR1`/`PR2`/`PR3` are numbered by list 4 at levels 4/5/6 — shown as `A.` / `1.` / `a.`. A `PR2` paragraph with no numbering written on it is therefore numbered automatically: that is what makes every equipment block header `1.`, `2.`, `3.`…
- List 12 levels 4–8: bullets `o ➢ ▪ • ` at indents 1800, 2160, 2520, 2880, 3240 twips. This is the house list for scope lines.
- List 11 levels 1–2 (new-system front end): indents 1440, 2160. List 10 levels 1–2 (extend-existing front end): 1440, 2160.

**The proposal sent for 26-0246** (`Learn/26-0246/3. Proposal/1. Base Proposal/26-0246.docx`):
- Block headers: all 46 are `PR2`, no numbering written, left indent 1566, bold 12pt.
- Scope lines were built from six different lists (5, 9, 12, 14, 29, 34) in two styles and two fonts (Myriad Pro and pasted-in Calibri). The *indent* is consistent: every line sits on the 360-twip grid from 1800.
- Read with the rules in this plan: front end **7 lines + 5 notes**; **44 base blocks holding 204 items** — 137 lines at depth 1, 31 at depth 2, 15 at depth 3, 8 at depth 4, 13 notes; one ADD alternate (1 block, 2 lines); one DEDUCT alternate (1 block, 2 lines, 1 note).
- Everything from the clarifications to the end is word-for-word the template, plus one line appended to the exclusions: `EXCEPTION TO ANY WORK WITH EXHAUST FAN EF-4 (24/7 OPERATION)`.
- The cover label was hand-edited to `Quote:`; the template says `Quote #:`. The tool follows the template.
- The date field's stored value is `6/8/2026`.

**The price workup template** (`PriceWorkup_Template - 12-21-25.xlsx`):
- Sheets `Summary`, `Price Sheet 1` … `Price Sheet 10`. Row 4 of each price sheet: B Tech Hours · C Quantities · D Scope of Work · E Unit Price · F Material Totals · G Electric Costs.
- Rows 6–396 already hold `F = E × C`. Row 401 sums; rows 403–442 hold the rates and the sell-price chain. **4,199 formulas across the workbook**, 408 of them on `Price Sheet 1`.
- Column H is empty on rows 6–396 of every price sheet. Summary `B33` and `B34` are empty.
- The Summary carries a leftover `MCCC LA ` in `B7` (Job Name) and `B21` (location of Price Sheet 1), and a stale date. The master template itself holds these.
- The Summary has a logo picture. openpyxl keeps it only if Pillow is installed.

**The workup sent for 26-0246:** tech hours sit on the `SCOPE OF WORK` row (140 — the front end) and on each block header (10, 25…); quantity and unit price sit on the lines. The scope text was pasted from Word, so the list markers are literal text (`1.`, `o`, `⮚`, `·`) followed by non-breaking spaces. Its two alternate blocks are numbered 44 and 45, but in the proposal they are 45 and 46 — the two documents had drifted apart.

**The price book** (`AME Std Pricing Spreadsheet.xlsx`): sheets `Parts Pricing` (50 priced rows) and `BMS-DDC-Panels` (17). Column B name, column C estimation price. No two names collide once the verb is taken off. Rows 46, 49, 52, 53, 54 of `Parts Pricing` have a note in column A starting "Need…" (46 Filter DP Switch and 49 Spot Leak Sensor still have prices). Known prices: Space Temperature Sensor 142, UPS 500, BMS Server 2500, Discharge Air Temperature Sensor 25, Space Temperature / CO2 Sensor 182, BACnet Thermostat 355, Standard Damper Actuator 320, Filter DP Switch 50. Only 13 of 26-0246's 74 priced lines match a book name exactly, and 12 of those 13 differ in price from what was entered. **That is not the book being wrong:** the book holds the generic price used on most jobs, and a job can use a vendor quote sourced for it instead — 26-0246's Space Temperature / CO2 Sensor was quoted at $380 against the book's generic $182. Nothing in build step 1 changes a book price or copies a sent price into the book.

## File structure

```
pyproject.toml, README.md, .gitattributes, .gitignore (add out/)
src/estimator/
  __init__.py
  __main__.py            command line: build, import-sent, price-check
  scope.py               the Job and its parts
  text.py                squash(), strip_list_marker()
  sent.py                a sent proposal + workup -> Job with hours and quantities
  proposal/
    __init__.py
    word.py              how Word draws a paragraph: list, level, indent, emphasis, fields
    layout.py            fixed headings, and the one format for each kind of line
    read.py              sent proposal -> Job
    write.py             Job -> proposal .docx, filling the template in place
    sections.py          a proposal's parts as plain text, for comparing proposals
  price_sheet/
    __init__.py
    price_book.py        the price book and its strict lookup
    rows.py              the price sheet as rows; reading a sent workup; lining rows up
    write.py             Job -> price sheet .xlsx
    check.py             generated price sheet vs the sent workup -> plain-language report
assets/
  templates/             the team's two master templates, copied in
  price_book/            the price book, and aliases.json (starts empty)
tests/
  conftest.py
  data/26-0246/          sent-proposal.docx, sent-workup.xlsx, job.json
  test_*.py
tools/
  side_by_side.py        pages of two proposals side by side; Excel recalculation check
```

---

### Task 1: Project skeleton and assets

**Files:**
- Create: `pyproject.toml`, `README.md`, `.gitattributes`, `src/estimator/__init__.py`, `src/estimator/proposal/__init__.py`, `src/estimator/price_sheet/__init__.py`, `assets/price_book/aliases.json`, `tests/conftest.py`, `tests/test_assets.py`
- Copy in: the two templates, the price book, the 26-0246 proposal and workup
- Modify: `.gitignore`

**Interfaces:**
- Produces: package `estimator` (importable), fixtures `proposal_template`, `workup_template`, `price_book_path`, `aliases_path`, `sent_proposal`, `sent_workup`, and module constants in `tests/conftest.py` of the same names in capitals.

- [ ] **Step 1: Create the virtual environment**

```bash
py -3.13 -m venv .venv
.venv/Scripts/python.exe --version
```
Expected: `Python 3.13.15`

- [ ] **Step 2: Write `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=75"]
build-backend = "setuptools.build_meta"

[project]
name = "estimator"
version = "0.1.0"
description = "HVAC/BMS controls proposals and price sheets, built on AME's own templates"
requires-python = "==3.13.*"
dependencies = [
  "pydantic==2.13.5",
  "python-docx==1.2.0",
  "openpyxl==3.1.5",
  "pillow==12.3.0",   # openpyxl needs it to keep the logo in the price workup
  "lxml==6.1.3",
]

[project.optional-dependencies]
dev = ["pytest==9.1.1", "pymupdf==1.28.2"]

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 3: Create the package folders and empty `__init__.py` files**

`src/estimator/__init__.py`:
```python
"""Estimator AI — HVAC/BMS controls proposals and price sheets, built on AME's own templates."""
```
`src/estimator/proposal/__init__.py`:
```python
"""The proposal: reading one that was sent, and writing one from a Job."""
```
`src/estimator/price_sheet/__init__.py`:
```python
"""The price sheet: the price book, the workup rows, and writing a workup from a Job."""
```

- [ ] **Step 4: Install**

```bash
.venv/Scripts/python.exe -m pip install --upgrade pip
.venv/Scripts/python.exe -m pip install -e ".[dev]"
```
Expected: ends with `Successfully installed ... estimator-0.1.0 ...`

- [ ] **Step 5: Write the failing asset test**

`tests/conftest.py`:
```python
"""Shared test fixtures: where the real templates, price book and test job live."""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
PROPOSAL_TEMPLATE = ASSETS / "templates" / "AME_nordomatic Proposal Template.docx"
WORKUP_TEMPLATE = ASSETS / "templates" / "PriceWorkup_Template - 12-21-25.xlsx"
PRICE_BOOK = ASSETS / "price_book" / "AME Std Pricing Spreadsheet.xlsx"
ALIASES = ASSETS / "price_book" / "aliases.json"
TEST_JOB_DIR = ROOT / "tests" / "data" / "26-0246"
SENT_PROPOSAL = TEST_JOB_DIR / "sent-proposal.docx"
SENT_WORKUP = TEST_JOB_DIR / "sent-workup.xlsx"
TEST_JOB_FILE = TEST_JOB_DIR / "job.json"


@pytest.fixture
def proposal_template() -> Path:
    return PROPOSAL_TEMPLATE


@pytest.fixture
def workup_template() -> Path:
    return WORKUP_TEMPLATE


@pytest.fixture
def price_book_path() -> Path:
    return PRICE_BOOK


@pytest.fixture
def aliases_path() -> Path:
    return ALIASES


@pytest.fixture
def sent_proposal() -> Path:
    return SENT_PROPOSAL


@pytest.fixture
def sent_workup() -> Path:
    return SENT_WORKUP
```

`tests/test_assets.py`:
```python
"""The files copied in from the team's folders are exactly the ones measured while planning."""
import hashlib
import json
import sys

import pytest

from conftest import ALIASES, PRICE_BOOK, PROPOSAL_TEMPLATE, SENT_PROPOSAL, SENT_WORKUP, WORKUP_TEMPLATE

EXPECTED = {
    PROPOSAL_TEMPLATE: "cdc84d56e9b085bd8f8140651e51be9e4422c3f968a316c636df39d9cbd13085",
    WORKUP_TEMPLATE: "70925fb6ebe3a5f726146b7bc479f436d9a16d976a72d413550c433f7aef7ad7",
    PRICE_BOOK: "7485d8bf608551a018dea497b00ca4d39fca2fafc92fb98bdb34d71257c4231a",
    SENT_PROPOSAL: "3d2c48982eb94a0a697b9cb56bab03ccd80052f2734a1e9b6869851355566319",
    SENT_WORKUP: "8a516b27bd7448fc174c1eaf3d7c74d057fbe1bcd2cd77912093171cc41c60d7",
}


@pytest.mark.parametrize("path", list(EXPECTED), ids=lambda p: p.name)
def test_asset_is_the_measured_file(path):
    assert path.exists(), f"{path} is missing — copy it in (Task 1, Step 7)"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == EXPECTED[path]


def test_alias_file_starts_empty():
    assert json.loads(ALIASES.read_text(encoding="utf-8"))["aliases"] == {}


def test_running_on_the_project_python():
    assert sys.version_info[:3] == (3, 13, 15), "run tests with .venv/Scripts/python.exe"
```

- [ ] **Step 6: Run it to see it fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_assets.py -v`
Expected: FAIL — the five asset tests report `... is missing`, and the alias test fails with `FileNotFoundError`.

- [ ] **Step 7: Copy the files in, and create the alias file**

```bash
mkdir -p assets/templates assets/price_book tests/data/26-0246
cp "/d/AME Estimation/2026/NEW TEMPLATE/3. Proposal/1. Base Proposal/AME_nordomatic Proposal Template.docx" assets/templates/
cp "/d/AME Estimation/2026/NEW TEMPLATE/5. Price Workup/1. Base Documents/PriceWorkup_Template - 12-21-25.xlsx" assets/templates/
cp "/d/Estimation Assistant/Brain/AME Std Pricing Spreadsheet.xlsx" assets/price_book/
cp "/d/Estimation Assistant/Learn/26-0246/3. Proposal/1. Base Proposal/26-0246.docx" tests/data/26-0246/sent-proposal.docx
cp "/d/Estimation Assistant/Learn/26-0246/5. Price Workup/1. Base Documents/26-0246.xlsx" tests/data/26-0246/sent-workup.xlsx
```

`assets/price_book/aliases.json`:
```json
{
  "about": "Tells the tool which price book item a scope line means, when the names differ. The key is the scope line; the tool ignores its bullet, its leading verb (Furnish, Furnish and Install, Install and wire, ...) and any '(Qty. N Total)'. The value is the price book item's name exactly as the price book writes it. Add an entry only when an estimator has confirmed the match.",
  "aliases": {}
}
```

`.gitattributes`:
```
*.docx binary
*.xlsx binary
*.xlsm binary
*.png binary
```

Append to `.gitignore`:
```
# Generated documents
out/
```

`README.md`:
```markdown
# Estimator AI

Reads an HVAC/BMS controls bid package and produces the proposal and price sheet an AME estimator issues — built on the team's own templates.

The design is in `docs/superpowers/specs/2026-09-24-estimator-ai-design.md`.

## Set up once

    py -3.13 -m venv .venv
    .venv/Scripts/python.exe -m pip install -e ".[dev]"

Always run things with `.venv/Scripts/python.exe`. The bare `python` on this machine is 3.14 and belongs to another project.

## Make a job's proposal and price sheet

    .venv/Scripts/python.exe -m estimator build JOB.json --out out/JOB

## When the team updates a template

Copy the new file over the one in `assets/templates/`, then run the tests:

    .venv/Scripts/python.exe -m pytest
```

- [ ] **Step 8: Run the tests to see them pass**

Run: `.venv/Scripts/python.exe -m pytest -v`
Expected: 7 passed.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "feat: project skeleton, pinned environment, and the files everything is measured against

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: The scope model

**Files:**
- Create: `src/estimator/scope.py`, `tests/test_scope.py`
- Modify: `tests/conftest.py` (add `small_job`, `bare_job`, `without_prices`)

**Interfaces:**
- Produces:
  - `Run(text: str, bold: bool = False)`
  - `Item(kind: "line" | "note", depth: int = 1, runs: tuple[Run, ...], quantity: int | None = None)`, property `text -> str`
  - `Block(header: str, items: tuple[Item, ...] = (), tech_hours: float | None = None)`
  - `FrontEnd(mode: "new-system" | "extend-existing", existing_system_name: str | None = None, items: tuple[Item, ...] = (), tech_hours: float | None = None)`
  - `Alternate(label: str = "ALT #:", blocks: tuple[Block, ...] = ())`
  - `Header(to: str = "All Bidders", date: datetime.date, quote_number: str, reference: str, mep_engineer: str, based_on: tuple[str, ...])`
  - `Job(header, scope_heading_suffix: str = "", front_end, blocks = (), add_alternates = (), deduct_alternates = (), named_exceptions: tuple[str, ...] = ())`
  - All models frozen; unknown fields refused.
  - Fixtures: `small_job`, `bare_job`, `without_prices` (a function `Job -> Job` with every `tech_hours` and `quantity` cleared).

- [ ] **Step 1: Write the failing tests**

`tests/test_scope.py`:
```python
import datetime as dt

import pytest
from pydantic import ValidationError

from estimator.scope import Block, FrontEnd, Header, Item, Job, Run


def test_item_text_joins_its_runs():
    item = Item(kind="line", runs=(Run(text="Furnish and Install "), Run(text="(Rack Mounted)", bold=True), Run(text=" BACnet Server")))
    assert item.text == "Furnish and Install (Rack Mounted) BACnet Server"


def test_an_item_needs_text():
    with pytest.raises(ValidationError, match="needs some text"):
        Item(kind="line", runs=(Run(text="   "),))


def test_a_note_is_never_nested():
    with pytest.raises(ValidationError, match="depth 1"):
        Item(kind="note", depth=2, runs=(Run(text="*BY OTHERS"),))


def test_a_note_has_no_quantity():
    with pytest.raises(ValidationError, match="no quantity"):
        Item(kind="note", runs=(Run(text="*BY OTHERS"),), quantity=2)


def test_depth_is_one_to_five():
    with pytest.raises(ValidationError):
        Item(kind="line", depth=6, runs=(Run(text="x"),))


def test_extending_an_existing_bms_needs_its_name():
    with pytest.raises(ValidationError, match="existing system's name"):
        FrontEnd(mode="extend-existing")


def test_a_new_system_has_no_existing_name():
    with pytest.raises(ValidationError, match="no existing system name"):
        FrontEnd(mode="new-system", existing_system_name="Honeywell")


def test_front_end_lines_are_at_most_two_deep():
    with pytest.raises(ValidationError, match="two levels"):
        FrontEnd(mode="new-system", items=(Item(kind="line", depth=3, runs=(Run(text="x"),)),))


def test_unknown_fields_are_refused():
    with pytest.raises(ValidationError):
        Block(header="Qty (1) EF-1", colour="red")


def test_the_cover_needs_a_drawing_list():
    with pytest.raises(ValidationError):
        Header(date=dt.date(2026, 1, 1), quote_number="26-1", reference="r", mep_engineer="m", based_on=())


def test_a_job_survives_a_trip_through_json(small_job):
    assert Job.model_validate_json(small_job.model_dump_json()) == small_job


def test_without_prices_clears_hours_and_quantities(small_job, without_prices):
    bare = without_prices(small_job)
    assert bare.front_end.tech_hours is None
    assert all(b.tech_hours is None for b in bare.blocks)
    assert all(i.quantity is None for b in bare.blocks for i in b.items)
    assert bare.blocks[0].header == small_job.blocks[0].header
```

Add to `tests/conftest.py`:
```python
import datetime as dt

from estimator.scope import Alternate, Block, FrontEnd, Header, Item, Job, Run


def _line(text: str, *, quantity: int | None = None, depth: int = 1, bold: bool = False) -> Item:
    return Item(kind="line", depth=depth, runs=(Run(text=text, bold=bold),), quantity=quantity)


def _note(text: str) -> Item:
    return Item(kind="note", runs=(Run(text=text, bold=True),))


_HEADER = Header(
    date=dt.date(2026, 6, 8),
    quote_number="26-9999",
    reference="Test Building, 1 Main St",
    mep_engineer="Test MEP",
    based_on=("M-001 thru M-100 Dated: 01/02/2026", "Specs 23 09 00"),
)


@pytest.fixture
def small_job() -> Job:
    """A small job that uses every kind of line, both sections, a priced, a pending and a questioned price."""
    return Job(
        header=_HEADER,
        scope_heading_suffix="PREVAILING WAGE",
        front_end=FrontEnd(mode="new-system", tech_hours=40.0, items=(
            _line("Furnish Network Level Control Panel", quantity=1, bold=True),   # no price book match
            _line("Furnish BMS Server", quantity=1, bold=True),                    # price book: 2500
            _note("*CONNECTION TO OWNER WAN BY OTHERS"),
        )),
        blocks=(
            Block(header="Qty (2) Exhaust Fan EF-1, 2", tech_hours=8.0, items=(
                _line("Furnish and Install DDC Controller", quantity=2),           # no price book match
                _line("Mfr. to Provide Relay", depth=2),
                _note("*DAMPERS BY OTHERS"),
            )),
            Block(header="Qty (1) Air Handling Unit AHU-1", tech_hours=12.0, items=(
                _line("Furnish and Install Space Temperature Sensor", quantity=3), # price book: 142
                _line("Furnish and Wire Filter DP Switch", quantity=1),            # price book: 50, marked "Need review"
                Item(kind="line", runs=(Run(text="Furnish and Install "), Run(text="(Duct Mounted)", bold=True),
                                        Run(text=" Static Pressure Sensor"))),
            )),
        ),
        add_alternates=(Alternate(label="ALT 1: Controls for EF-3", blocks=(
            Block(header="Qty (1) Exhaust Fan EF-3", tech_hours=4.0, items=(
                _line("Furnish and Install DDC Controller", quantity=1),
            )),
        )),),
        named_exceptions=("EXCEPTION TO ANY WORK WITH EXHAUST FAN EF-4",),
    )


@pytest.fixture
def bare_job() -> Job:
    """Only the cover page and the front-end choice — no scope lines at all."""
    return Job(header=_HEADER, scope_heading_suffix="PREVAILING WAGE", front_end=FrontEnd(mode="new-system"))


@pytest.fixture
def without_prices():
    """Clear every tech_hours and quantity: what a proposal alone can tell you."""
    def clear(job: Job) -> Job:
        data = job.model_dump()

        def walk(node):
            if isinstance(node, dict):
                node.pop("tech_hours", None)
                node.pop("quantity", None)
                for value in node.values():
                    walk(value)
            elif isinstance(node, (list, tuple)):
                for value in node:
                    walk(value)

        walk(data)
        return Job.model_validate(data)

    return clear
```

- [ ] **Step 2: Run to see it fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_scope.py -v`
Expected: ERROR while loading conftest — `ModuleNotFoundError: No module named 'estimator.scope'`.

- [ ] **Step 3: Write `src/estimator/scope.py`**

```python
"""The scope of one job — everything the proposal says and the price sheet prices.

A Job is the single list both documents are produced from (the one-list,
two-documents guarantee). Nothing reaches the client document unless it is a
field here.
"""
from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Run(_Model):
    """A stretch of text with one emphasis — "(Rack Mounted)" in bold, say."""

    text: str
    bold: bool = False


class Item(_Model):
    """One line under a block header or under the front end.

    A "line" has a bullet. Depth 1 sits directly under the header, depth 2 under
    a line, and so on down to 5. A "note" has no bullet — a remark such as
    "*ENCLOSURE BY OTHERS" — and always has depth 1.

    quantity is what the price sheet puts in its Quantities column. A line with
    a quantity is a priced line.
    """

    kind: Literal["line", "note"]
    depth: int = Field(default=1, ge=1, le=5)
    runs: tuple[Run, ...] = Field(min_length=1)
    quantity: int | None = Field(default=None, ge=0)

    @property
    def text(self) -> str:
        return "".join(run.text for run in self.runs)

    @model_validator(mode="after")
    def _check(self) -> "Item":
        if not self.text.strip():
            raise ValueError("an item needs some text")
        if self.kind == "note" and self.depth != 1:
            raise ValueError("a note always has depth 1")
        if self.kind == "note" and self.quantity is not None:
            raise ValueError("a note has no quantity")
        return self


class Block(_Model):
    """An equipment block: a numbered "Qty (N) ..." header and what sits under it."""

    header: str = Field(min_length=1)
    items: tuple[Item, ...] = ()
    tech_hours: float | None = Field(default=None, ge=0)


class FrontEnd(_Model):
    """The front-end block. `mode` picks which of the template's two openings is used."""

    mode: Literal["new-system", "extend-existing"]
    existing_system_name: str | None = None
    items: tuple[Item, ...] = ()
    tech_hours: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _check(self) -> "FrontEnd":
        if self.mode == "extend-existing" and not (self.existing_system_name or "").strip():
            raise ValueError("extending an existing BMS needs the existing system's name")
        if self.mode == "new-system" and self.existing_system_name is not None:
            raise ValueError("a new system has no existing system name")
        if any(item.depth > 2 for item in self.items):
            raise ValueError("a front-end line can be at most two levels deep — the template's front-end lists have two")
        return self


class Alternate(_Model):
    label: str = "ALT #:"
    blocks: tuple[Block, ...] = ()


class Header(_Model):
    """The table on the cover page."""

    to: str = "All Bidders"
    date: dt.date
    quote_number: str = Field(min_length=1)
    reference: str = Field(min_length=1)
    mep_engineer: str = Field(min_length=1)
    based_on: tuple[str, ...] = Field(min_length=1)


class Job(_Model):
    header: Header
    scope_heading_suffix: str = ""
    front_end: FrontEnd
    blocks: tuple[Block, ...] = ()
    add_alternates: tuple[Alternate, ...] = ()
    deduct_alternates: tuple[Alternate, ...] = ()
    named_exceptions: tuple[str, ...] = ()
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_scope.py -v`
Expected: 12 passed.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: the scope model — one Job that both documents are written from

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Reading how Word draws a paragraph

**Files:**
- Create: `src/estimator/text.py`, `src/estimator/proposal/word.py`, `tests/test_text.py`, `tests/test_word.py`
- Modify: `tests/conftest.py` (add `template_document`, `sent_document`)

**Interfaces:**
- Produces:
  - `estimator.text.squash(text: str) -> str` — every run of whitespace (non-breaking spaces included) becomes one space; ends trimmed.
  - `estimator.text.strip_list_marker(text: str) -> str` — squashes, then removes one leading `1.` / `o` / `⮚` / `➢` / `·` / `•` / `▪` / `◦` and the spaces after it.
  - `estimator.proposal.word.WordLists(document)` with `has_level(list_id, level) -> bool`, `level_indent(list_id, level) -> int | None`, `style_numbering(style_id) -> (list_id, level) | None`, static `written_numbering(paragraph) -> (list_id, level) | None` (includes list 0), `numbering(paragraph) -> (list_id, level) | None` (None when no bullet or number is drawn), `left_indent(paragraph) -> int` (twips).
  - `merged_runs(paragraph) -> list[tuple[str, bool]]` — text as (text, bold) stretches, trimmed at both ends.
  - `visible_text(paragraph) -> str` — every character of text anywhere in the paragraph's XML.
  - `field_result_text(paragraph, instruction: str) -> str | None` — what Word last displayed for a field such as `DATE`.
  - Fixtures (session scope): `template_document`, `sent_document` — python-docx `Document` objects. Tests must not change them.

- [ ] **Step 1: Write the failing tests**

`tests/test_text.py`:
```python
import pytest

from estimator.text import squash, strip_list_marker


def test_squash_collapses_every_kind_of_space():
    assert squash("  Furnish\xa0\xa0and\tInstall  UPS \n") == "Furnish and Install UPS"


@pytest.mark.parametrize("pasted, clean", [
    ("1.\xa0\xa0\xa0\xa0\xa0\xa0\xa0\xa0 *Qty (1) BACnet Data Cabinet", "*Qty (1) BACnet Data Cabinet"),
    ("44.\xa0\xa0\xa0\xa0 *Qty (1) Can Wash Kitchen Exhaust Fan EF-9 ", "*Qty (1) Can Wash Kitchen Exhaust Fan EF-9"),
    ("o\xa0\xa0 Furnish and Install UPS", "Furnish and Install UPS"),
    ("⮚\xa0\xa0\xa0\xa0\xa0 Keyboard ", "Keyboard"),
    ("·\xa0\xa0\xa0\xa0\xa0\xa0\xa0\xa0 Front End Web Enabled BMS System", "Front End Web Enabled BMS System"),
    ("•  Front End Web Enabled BMS System", "Front End Web Enabled BMS System"),
    ("Outside Air Temperature", "Outside Air Temperature"),
    ("2 Year Workmanship and Material Guarantee", "2 Year Workmanship and Material Guarantee"),
    ("o  1. something", "1. something"),
])
def test_strip_list_marker(pasted, clean):
    assert strip_list_marker(pasted) == clean
```

`tests/test_word.py`:
```python
import pytest
from docx.oxml.ns import qn
from docx.table import _Cell

from estimator.proposal.word import WordLists, field_result_text, merged_runs, visible_text
from estimator.text import squash


def _paragraph(document, text):
    return next(p for p in document.paragraphs if squash(p.text) == text)


def _date_paragraph(document):
    table = document.tables[0]
    return next(p for tc in table._tbl.iter(qn("w:tc")) for p in _Cell(tc, table).paragraphs
                if p.text.strip().startswith("Date:"))


def test_scope_line_list_steps_in_by_360(template_document):
    lists = WordLists(template_document)
    assert [lists.level_indent(12, level) for level in range(4, 9)] == [1800, 2160, 2520, 2880, 3240]


def test_front_end_lists(template_document):
    lists = WordLists(template_document)
    assert [lists.level_indent(11, 1), lists.level_indent(11, 2)] == [1440, 2160]
    assert [lists.level_indent(10, 1), lists.level_indent(10, 2)] == [1440, 2160]
    assert lists.has_level(12, 8) and not lists.has_level(12, 9)


def test_pr2_numbers_its_paragraphs(template_document):
    assert WordLists(template_document).style_numbering("PR2") == (4, 5)


def test_a_block_header(sent_document):
    lists = WordLists(sent_document)
    header = _paragraph(sent_document, "Qty (4) Packaged Air Handling Unit AHU-1, 2, 3, 4")
    assert header.style.name == "PR2"
    assert WordLists.written_numbering(header) is None
    assert lists.numbering(header) == (4, 5)
    assert lists.left_indent(header) == 1566


def test_the_scope_heading_switches_numbering_off(sent_document):
    heading = next(p for p in sent_document.paragraphs if squash(p.text).startswith("SCOPE OF WORK"))
    assert WordLists.written_numbering(heading) == (0, 0)
    assert WordLists(sent_document).numbering(heading) is None


@pytest.mark.parametrize("text, indent", [
    ("Map Available Points Via Mfr. Provided BMS Interface or Connect to Nearby DDC Controller", 1800),
    ("Main Electrical Meter (Furnished and Installed by Others) – (Qty. 1 Total)", 2160),
    ("Booster Pump Set General Fault Alarm", 2520),
    ("DB-ELEV – (Qty. 1 Total)", 2880),
    ("Intrusion Alarm", 2160),
])
def test_nested_lines_resolve_to_the_indent_word_draws(sent_document, text, indent):
    lists = WordLists(sent_document)
    paragraph = _paragraph(sent_document, text)
    assert lists.numbering(paragraph) is not None
    assert lists.left_indent(paragraph) == indent


def test_emphasis_inside_a_line_is_kept(sent_document):
    paragraph = _paragraph(sent_document, "Furnish and Install (Rack Mounted) BACnet Server")
    stretches = merged_runs(paragraph)
    assert [text.strip() for text, bold in stretches if bold] == ["(Rack Mounted)"]
    assert squash("".join(text for text, _ in stretches)) == "Furnish and Install (Rack Mounted) BACnet Server"


def test_visible_text_matches_the_runs_for_an_ordinary_line(sent_document):
    paragraph = _paragraph(sent_document, "Furnish and Install (Rack Mounted) BACnet Server")
    assert squash(visible_text(paragraph)) == squash(paragraph.text)


def test_the_date_field_gives_its_stored_value(template_document, sent_document):
    assert field_result_text(_date_paragraph(template_document), "DATE") == "3/6/2026"
    assert field_result_text(_date_paragraph(sent_document), "DATE") == "6/8/2026"


def test_a_paragraph_without_the_field(sent_document):
    assert field_result_text(_paragraph(sent_document, "Intrusion Alarm"), "DATE") is None
```

Add to `tests/conftest.py`:
```python
import docx


@pytest.fixture(scope="session")
def template_document():
    return docx.Document(str(PROPOSAL_TEMPLATE))


@pytest.fixture(scope="session")
def sent_document():
    return docx.Document(str(SENT_PROPOSAL))
```

- [ ] **Step 2: Run to see it fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_text.py tests/test_word.py -v`
Expected: collection errors — `ModuleNotFoundError: No module named 'estimator.text'` and `'estimator.proposal.word'`.

- [ ] **Step 3: Write `src/estimator/text.py`**

```python
"""Small text helpers shared by the proposal and the price sheet."""
from __future__ import annotations

import re

_SPACE = re.compile(r"\s+")
# What Word draws in front of a list item, once pasted into Excel as plain text.
_LIST_MARKER = re.compile(r"^(?:\d{1,3}\.|o|⮚|➢|·|•|▪|◦)\s+")


def squash(text: str) -> str:
    """Collapse every run of whitespace, non-breaking spaces included, to one space."""
    return _SPACE.sub(" ", text.replace("\xa0", " ")).strip()


def strip_list_marker(text: str) -> str:
    """Remove one leading list number or bullet, as found in a pasted price sheet."""
    return _LIST_MARKER.sub("", squash(text), count=1)
```

- [ ] **Step 4: Write `src/estimator/proposal/word.py`**

```python
"""How Word draws a paragraph: its bullet or number, its indent, its emphasis.

Proposals are copy-pasted between jobs, so the same visual level turns up
built from several different lists and styles. Everything here reads what Word
actually draws rather than what the style is called.
"""
from __future__ import annotations

from collections.abc import Iterator

from docx.document import Document as DocxDocument
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph


def _left(pPr) -> int | None:
    """The left indent written on a paragraph-properties element, in twips."""
    if pPr is None:
        return None
    ind = pPr.find(qn("w:ind"))
    if ind is None:
        return None
    value = ind.get(qn("w:left"))
    if value is None:
        value = ind.get(qn("w:start"))
    return int(value) if value is not None else None


class WordLists:
    """The document's lists and styles, resolved the way Word resolves them."""

    def __init__(self, document: DocxDocument) -> None:
        self._styles = {s.get(qn("w:styleId")): s for s in document.styles.element.findall(qn("w:style"))}
        numbering = document.part.numbering_part.element
        self._list_to_definition = {
            int(n.get(qn("w:numId"))): n.find(qn("w:abstractNumId")).get(qn("w:val"))
            for n in numbering.findall(qn("w:num"))
        }
        self._definitions = {a.get(qn("w:abstractNumId")): a for a in numbering.findall(qn("w:abstractNum"))}

    # lists ----------------------------------------------------------------------

    def _level(self, list_id: int, level: int):
        definition = self._definitions.get(self._list_to_definition.get(list_id))
        if definition is None:
            return None
        for lvl in definition.findall(qn("w:lvl")):
            if lvl.get(qn("w:ilvl")) == str(level):
                return lvl
        return None

    def has_level(self, list_id: int, level: int) -> bool:
        return self._level(list_id, level) is not None

    def level_indent(self, list_id: int, level: int) -> int | None:
        lvl = self._level(list_id, level)
        return _left(lvl.find(qn("w:pPr"))) if lvl is not None else None

    # styles ---------------------------------------------------------------------

    def _style_chain(self, style_id: str | None) -> Iterator:
        seen: set[str] = set()
        while style_id and style_id not in seen:
            seen.add(style_id)
            style = self._styles.get(style_id)
            if style is None:
                return
            yield style
            based_on = style.find(qn("w:basedOn"))
            style_id = based_on.get(qn("w:val")) if based_on is not None else None

    def style_numbering(self, style_id: str) -> tuple[int, int] | None:
        """The list a style numbers its paragraphs with, if it has one."""
        for style in self._style_chain(style_id):
            pPr = style.find(qn("w:pPr"))
            numPr = pPr.find(qn("w:numPr")) if pPr is not None else None
            if numPr is not None:
                num_id = numPr.find(qn("w:numId"))
                ilvl = numPr.find(qn("w:ilvl"))
                list_id = int(num_id.get(qn("w:val"))) if num_id is not None else 0
                level = int(ilvl.get(qn("w:val"))) if ilvl is not None else 0
                return None if list_id == 0 else (list_id, level)
        return None

    # paragraphs -----------------------------------------------------------------

    @staticmethod
    def written_numbering(paragraph: Paragraph) -> tuple[int, int] | None:
        """The list and level written on the paragraph itself — list 0 ("no number") included."""
        pPr = paragraph._p.pPr
        if pPr is None or pPr.numPr is None or pPr.numPr.numId is None:
            return None
        level = pPr.numPr.ilvl.val if pPr.numPr.ilvl is not None else 0
        return int(pPr.numPr.numId.val), int(level)

    def numbering(self, paragraph: Paragraph) -> tuple[int, int] | None:
        """The list and level Word draws for this paragraph; None if it has no bullet or number."""
        written = self.written_numbering(paragraph)
        if written is not None:
            return None if written[0] == 0 else written
        return self.style_numbering(paragraph.style.style_id)

    def left_indent(self, paragraph: Paragraph) -> int:
        """Where Word starts the paragraph's text, in twips (1440 twips = one inch)."""
        written = _left(paragraph._p.pPr)
        if written is not None:
            return written
        numbering = self.numbering(paragraph)
        if numbering is not None:
            from_list = self.level_indent(*numbering)
            if from_list is not None:
                return from_list
        for style in self._style_chain(paragraph.style.style_id):
            from_style = _left(style.find(qn("w:pPr")))
            if from_style is not None:
                return from_style
        return 0


def merged_runs(paragraph: Paragraph) -> list[tuple[str, bool]]:
    """The paragraph's text as (text, bold) stretches, trimmed at both ends.

    A run of pure whitespace joins whatever comes before it, so a bold space
    between two plain words doesn't split the line into three pieces.
    """
    stretches: list[list] = []
    for content in paragraph.iter_inner_content():
        for run in (content.runs if hasattr(content, "runs") else [content]):
            if not run.text:
                continue
            bold = run.bold is True
            if stretches and (stretches[-1][1] == bold or not run.text.strip()):
                stretches[-1][0] += run.text
            else:
                stretches.append([run.text, bold])
    while stretches and not stretches[0][0].strip():
        stretches.pop(0)
    while stretches and not stretches[-1][0].strip():
        stretches.pop()
    if stretches:
        stretches[0][0] = stretches[0][0].lstrip()
        stretches[-1][0] = stretches[-1][0].rstrip()
    return [(text, bold) for text, bold in stretches]


def visible_text(paragraph: Paragraph) -> str:
    """Every character of text in the paragraph's XML, wherever it sits."""
    parts = []
    for element in paragraph._p.iter(qn("w:t"), qn("w:noBreakHyphen")):
        parts.append((element.text or "") if element.tag == qn("w:t") else "-")
    return "".join(parts)


def field_result_text(paragraph: Paragraph, instruction: str) -> str | None:
    """The text Word last displayed for a field such as DATE, or None if there is none."""
    state, code, shown = None, "", []
    for run in paragraph._p.findall(qn("w:r")):
        char = run.find(qn("w:fldChar"))
        if char is not None:
            kind = char.get(qn("w:fldCharType"))
            if kind == "begin":
                state, code, shown = "code", "", []
            elif kind == "separate":
                state = "shown"
            elif kind == "end":
                if code.strip().upper().startswith(instruction.upper()):
                    return "".join(shown)
                state = None
            continue
        if state == "code":
            instr = run.find(qn("w:instrText"))
            if instr is not None and instr.text:
                code += instr.text
        elif state == "shown":
            shown.extend(t.text or "" for t in run.findall(qn("w:t")))
    for simple in paragraph._p.findall(qn("w:fldSimple")):
        if (simple.get(qn("w:instr")) or "").strip().upper().startswith(instruction.upper()):
            return "".join(t.text or "" for t in simple.iter(qn("w:t")))
    return None
```

- [ ] **Step 5: Run the tests to see them pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_text.py tests/test_word.py -v`
Expected: 24 passed (10 + 14).

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: read what Word actually draws — list, level, indent, emphasis, field values

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: The proposal's layout

**Files:**
- Create: `src/estimator/proposal/layout.py`, `tests/test_layout.py`

**Interfaces:**
- Consumes: `WordLists` (Task 3), `FrontEnd`, `Job` (Task 2).
- Produces (all in `estimator.proposal.layout`):
  - heading constants `OPENING`, `SCOPE_HEADING`, `NEW_SYSTEM_HEADING`, `EXISTING_SYSTEM_HEADING`, `OR_LINE`, `ADD_ALTERNATES`, `DEDUCT_ALTERNATES`, `ALTERNATE_LABEL`, `CLARIFICATIONS`, `EXCLUSIONS`, `BASE_PRICE`, `EXISTING_NAME_COLOUR`
  - list constants `BLOCK_LINE_LIST = 12`, `FRONT_END_LIST = {"new-system": 11, "extend-existing": 10}`, `OUTLINE_STYLE = "PR2"`, `BLOCK_LINE_INDENT = 1800`, `BLOCK_LINE_STEP = 360`, `FRONT_END_LINE_INDENT = 1440`, `FRONT_END_LINE_STEP = 720`
  - `ParagraphFormat(style, list_id=None, level=None, indent=None, space_after=None, size=None, bold=None)`
  - `BLANK`, `BLOCK_HEADER`, `BLOCK_NOTE`, `FRONT_END_NOTE`, `block_line(depth)`, `front_end_line(mode, depth)`
  - `BLOCK_LINE_MARKER`, `FRONT_END_LINE_MARKER`, `FRONT_END_HEADING_MARKER`
  - `scope_heading(job) -> str`, `front_end_heading(front_end) -> str`

- [ ] **Step 1: Write the failing tests**

`tests/test_layout.py`:
```python
import pytest

from estimator.proposal import layout
from estimator.proposal.word import WordLists
from estimator.scope import FrontEnd
from estimator.text import squash


@pytest.mark.parametrize("depth", [1, 2, 3, 4, 5])
def test_every_block_line_depth_is_a_level_the_template_defines(template_document, depth):
    lists = WordLists(template_document)
    fmt = layout.block_line(depth)
    assert lists.has_level(fmt.list_id, fmt.level)
    assert lists.level_indent(fmt.list_id, fmt.level) == layout.BLOCK_LINE_INDENT + layout.BLOCK_LINE_STEP * (depth - 1)


@pytest.mark.parametrize("mode", ["new-system", "extend-existing"])
@pytest.mark.parametrize("depth", [1, 2])
def test_every_front_end_depth_is_a_level_the_template_defines(template_document, mode, depth):
    lists = WordLists(template_document)
    fmt = layout.front_end_line(mode, depth)
    assert lists.level_indent(fmt.list_id, fmt.level) == layout.FRONT_END_LINE_INDENT + layout.FRONT_END_LINE_STEP * (depth - 1)


def test_block_headers_are_numbered_by_their_style(template_document):
    assert layout.BLOCK_HEADER.style == layout.OUTLINE_STYLE and layout.BLOCK_HEADER.list_id is None
    assert WordLists(template_document).style_numbering(layout.OUTLINE_STYLE) is not None


def test_scope_lines_are_plain_normal_paragraphs_with_a_bullet():
    # Normal, not PR2: if an estimator later removes the bullet in Word, the line
    # stays a line instead of turning into a numbered block header.
    assert layout.block_line(1).style == "Normal"


def test_every_heading_the_tool_looks_for_is_in_the_template(template_document):
    texts = [squash(p.text) for p in template_document.paragraphs]
    for heading in (layout.OPENING, layout.SCOPE_HEADING, layout.NEW_SYSTEM_HEADING, layout.EXISTING_SYSTEM_HEADING,
                    layout.ADD_ALTERNATES, layout.DEDUCT_ALTERNATES, layout.CLARIFICATIONS, layout.EXCLUSIONS,
                    layout.BASE_PRICE):
        assert any(t.startswith(heading) for t in texts), heading
    assert layout.OR_LINE in texts and texts.count(layout.ALTERNATE_LABEL) == 2


def test_scope_heading(small_job, bare_job):
    assert layout.scope_heading(small_job) == "SCOPE OF WORK – PREVAILING WAGE"
    assert layout.scope_heading(bare_job.model_copy(update={"scope_heading_suffix": ""})) == "SCOPE OF WORK –"


def test_front_end_heading():
    assert layout.front_end_heading(FrontEnd(mode="new-system")) == "Front End Web Enabled BMS System"
    existing = FrontEnd(mode="extend-existing", existing_system_name="Honeywell WEBs")
    assert layout.front_end_heading(existing) == "Seamlessly Tie in to the Existing Honeywell WEBs BMS"
```

- [ ] **Step 2: Run to see it fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_layout.py -v`
Expected: collection error — `ImportError: cannot import name 'layout' from 'estimator.proposal'`.

- [ ] **Step 3: Write `src/estimator/proposal/layout.py`**

```python
"""The layout of an AME proposal: its fixed headings, and how each kind of line looks.

Every format here uses a list the AME template already defines — measured on the
template and on the proposal sent for 26-0246. Each kind of line has exactly one
format, so a proposal never ends up with the same kind of line in two fonts or
two different bullets.
"""
from __future__ import annotations

from dataclasses import dataclass

from estimator.scope import FrontEnd, Job

# Fixed wording the tool looks for in the template.
OPENING = "A.M.E., Inc, is pleased to provide a quotation"
SCOPE_HEADING = "SCOPE OF WORK –"
NEW_SYSTEM_HEADING = "Front End Web Enabled BMS System"
EXISTING_SYSTEM_HEADING = "Seamlessly Tie in to the Existing"
OR_LINE = "OR"
ADD_ALTERNATES = "ADD ALTERNATES:"
DEDUCT_ALTERNATES = "DEDUCT ALTERNATES:"
ALTERNATE_LABEL = "ALT #:"
CLARIFICATIONS = "Clarifications and Inclusions considered:"
EXCLUSIONS = "Exceptions and Exclusions"
BASE_PRICE = "Base Price:"
EXISTING_NAME_COLOUR = "FF0000"   # the template types the existing system's name in red

# The lists the template defines.
BLOCK_LINE_LIST = 12              # o ➢ ▪ • at levels 4-8; indents 1800, 2160, 2520, 2880, 3240
FRONT_END_LIST = {"new-system": 11, "extend-existing": 10}
OUTLINE_STYLE = "PR2"             # numbered 1., 2., 3. by the template's outline list

# Where Word starts depth-1 text, and how far each deeper level steps in (twips).
BLOCK_LINE_INDENT, BLOCK_LINE_STEP = 1800, 360
FRONT_END_LINE_INDENT, FRONT_END_LINE_STEP = 1440, 720


@dataclass(frozen=True)
class ParagraphFormat:
    style: str                        # Word style name
    list_id: int | None = None        # bullet list; None = no bullet
    level: int | None = None
    indent: int | None = None         # left indent in twips; None = from the list or style
    space_after: int | None = None    # points
    size: float | None = None         # font size in points; None = from the style
    bold: bool | None = None          # True forces bold; None = each run's own emphasis


BLANK = ParagraphFormat(style="Normal")
BLOCK_HEADER = ParagraphFormat(style=OUTLINE_STYLE, indent=1566, space_after=0, size=12, bold=True)
BLOCK_NOTE = ParagraphFormat(style="Normal", indent=1440, space_after=0)
FRONT_END_NOTE = ParagraphFormat(style="Normal", indent=720)


def block_line(depth: int) -> ParagraphFormat:
    """A bulleted line under a block header. Depth 1 is list 12 level 4; depth 5 is level 8."""
    return ParagraphFormat(style="Normal", list_id=BLOCK_LINE_LIST, level=3 + depth, space_after=0)


def front_end_line(mode: str, depth: int) -> ParagraphFormat:
    return ParagraphFormat(style="Normal", list_id=FRONT_END_LIST[mode], level=depth, size=12)


# What Word draws in front of each kind of line — written into the price sheet as text.
BLOCK_LINE_MARKER = {1: "o", 2: "➢", 3: "▪", 4: "•", 5: "◦"}
FRONT_END_LINE_MARKER = {"new-system": {1: "o", 2: "▪"}, "extend-existing": {1: "•", 2: "o"}}
FRONT_END_HEADING_MARKER = "•"


def scope_heading(job: Job) -> str:
    return f"{SCOPE_HEADING} {job.scope_heading_suffix}".strip()


def front_end_heading(front_end: FrontEnd) -> str:
    if front_end.mode == "new-system":
        return NEW_SYSTEM_HEADING
    return f"{EXISTING_SYSTEM_HEADING} {front_end.existing_system_name} BMS"
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_layout.py -v`
Expected: 14 passed.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: one format for each kind of proposal line, tied to the template's own lists

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Reading a sent proposal — cover page and exclusions

**Files:**
- Create: `src/estimator/proposal/read.py`, `tests/test_read_cover.py`

**Interfaces:**
- Consumes: `squash` (Task 3), `field_result_text` (Task 3), `layout` constants (Task 4), `Header` (Task 2).
- Produces:
  - `ProposalFormatError(ValueError)`
  - `read_cover(document) -> Header`
  - `read_named_exceptions(document, template_path: Path) -> tuple[str, ...]` — exclusions added after the template's standard list. Raises `ProposalFormatError` if the standard list was edited, reordered or cut.

- [ ] **Step 1: Write the failing tests**

`tests/test_read_cover.py`:
```python
import datetime as dt

import docx
import pytest

from conftest import PROPOSAL_TEMPLATE, SENT_PROPOSAL
from estimator.proposal.read import ProposalFormatError, read_cover, read_named_exceptions
from estimator.scope import Header
from estimator.text import squash


def test_cover_page_of_what_was_sent(sent_document):
    assert read_cover(sent_document) == Header(
        to="All Bidders",
        date=dt.date(2026, 6, 8),
        quote_number="26-0246",
        reference="PS Q517, 1 Beach 39th St, Queens NY - New Bldg",
        mep_engineer="SCA",
        based_on=("M001.00 Thru M505.00 Dated: 03/31/2026",),
    )


def test_the_template_cover_is_placeholders(template_document):
    header = read_cover(template_document)
    assert (header.quote_number, header.reference, header.mep_engineer) == ("26-#####", "########", "#######")
    assert header.date == dt.date(2026, 3, 6)
    assert header.based_on == ("########",)


def test_named_exceptions_of_what_was_sent(sent_document):
    assert read_named_exceptions(sent_document, PROPOSAL_TEMPLATE) == (
        "EXCEPTION TO ANY WORK WITH EXHAUST FAN EF-4 (24/7 OPERATION)",
    )


def test_the_template_itself_has_none(template_document):
    assert read_named_exceptions(template_document, PROPOSAL_TEMPLATE) == ()


def test_an_edited_standard_exclusion_is_refused(tmp_path):
    document = docx.Document(str(SENT_PROPOSAL))
    target = next(p for p in document.paragraphs if squash(p.text) == "All gas meters.")
    target.runs[0].text = "All gas meters, except the one on the roof."
    edited = tmp_path / "edited.docx"
    document.save(str(edited))
    with pytest.raises(ProposalFormatError, match="standard exclusions"):
        read_named_exceptions(docx.Document(str(edited)), PROPOSAL_TEMPLATE)
```

- [ ] **Step 2: Run to see it fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_read_cover.py -v`
Expected: collection error — `ModuleNotFoundError: No module named 'estimator.proposal.read'`.

- [ ] **Step 3: Write `src/estimator/proposal/read.py`**

```python
"""Read a proposal written on the AME template back into a Job.

Used to turn the proposal an estimator actually sent into test data and, from
build step 2, to score the tool against past jobs. It reads what Word draws —
bullets, numbering, indent — rather than what the styles are called, because
copy-paste between proposals leaves the same visual level built from several
different lists and styles.
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import docx
from docx.document import Document as DocxDocument
from docx.oxml.ns import qn
from docx.table import _Cell
from docx.text.paragraph import Paragraph

from estimator.proposal import layout
from estimator.proposal.word import WordLists, field_result_text, merged_runs, visible_text
from estimator.scope import Alternate, Block, FrontEnd, Header, Item, Job, Run
from estimator.text import squash


class ProposalFormatError(ValueError):
    """The proposal doesn't follow the template closely enough to be read safely."""


# --- the cover page ---------------------------------------------------------------

def read_cover(document: DocxDocument) -> Header:
    """The table on the cover page: to, date, quote number, reference, engineer, drawings."""
    table = document.tables[0]
    values: dict[str, object] = {}
    for tc in table._tbl.iter(qn("w:tc")):
        lines = [p for p in _Cell(tc, table).paragraphs if p.text.strip()]
        if not lines:
            continue
        first = squash(lines[0].text)
        if first.startswith("To:"):
            values["to"] = first[len("To:"):].strip()
        elif first.startswith("Date:"):
            values["date"] = _date(field_result_text(lines[0], "DATE") or first[len("Date:"):])
        elif first.startswith("Quote"):
            values["quote_number"] = re.sub(r"^Quote\s*#?\s*:\s*", "", first)
        elif first.startswith("Reference"):
            joined = " ".join(squash(p.text) for p in lines)
            values["reference"] = re.sub(r"^Reference\s*:\s*", "", joined)
        elif first.startswith("MEP Engineer:"):
            values["mep_engineer"] = first[len("MEP Engineer:"):].strip()
        elif first.startswith("Based on Plans and Specs:"):
            rest = first[len("Based on Plans and Specs:"):].strip()
            values["based_on"] = tuple(([rest] if rest else []) + [squash(p.text) for p in lines[1:]])
    missing = {"to", "date", "quote_number", "reference", "mep_engineer", "based_on"} - values.keys()
    if missing:
        raise ProposalFormatError(f"the cover page is missing {sorted(missing)}")
    return Header(**values)


def _date(text: str) -> dt.date:
    try:
        return dt.datetime.strptime(squash(text), "%m/%d/%Y").date()
    except ValueError as error:
        raise ProposalFormatError(f"can't read the date {text!r}") from error


# --- the exclusions ---------------------------------------------------------------

def _exclusions(document: DocxDocument) -> list[str]:
    texts = [squash(p.text) for p in document.paragraphs if p.text.strip()]
    start = next((i for i, t in enumerate(texts) if t.startswith(layout.EXCLUSIONS)), None)
    end = next((i for i, t in enumerate(texts) if t.startswith(layout.BASE_PRICE)), None)
    if start is None or end is None or end <= start:
        raise ProposalFormatError("can't find the exclusions list")
    return texts[start + 1 : end]


def read_named_exceptions(document: DocxDocument, template_path: Path) -> tuple[str, ...]:
    """Exclusions this job added after the template's standard list."""
    standard = _exclusions(docx.Document(str(template_path)))
    sent = _exclusions(document)
    if sent[: len(standard)] != standard:
        raise ProposalFormatError(
            "the standard exclusions were edited, reordered or cut in this proposal; the tool can "
            "only add exceptions after the standard list, so it can't reproduce this one")
    return tuple(sent[len(standard):])
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_read_cover.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: read a sent proposal's cover page and the exceptions it added

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Reading a sent proposal — the scope of work

**Files:**
- Modify: `src/estimator/proposal/read.py` (append), `tests/conftest.py` (add `sent_scope`, `sent_job`)
- Create: `tests/test_read_scope.py`

**Interfaces:**
- Consumes: everything in Task 5, `WordLists`, `merged_runs`, `visible_text` (Task 3), scope models (Task 2).
- Produces:
  - `read_scope(document) -> tuple[str, FrontEnd, tuple[Block, ...], tuple[Alternate, ...], tuple[Alternate, ...]]` — (scope heading suffix, front end, blocks, add alternates, deduct alternates).
  - `read_proposal(path: Path, template_path: Path) -> Job` — hours and quantities are always `None` (a proposal doesn't carry them).
  - Fixtures (session): `sent_scope` = `read_scope(sent_document)`, `sent_job` = `read_proposal(SENT_PROPOSAL, PROPOSAL_TEMPLATE)`.

- [ ] **Step 1: Write the failing tests**

`tests/test_read_scope.py`:
```python
from collections import Counter

import docx
import pytest

from conftest import PROPOSAL_TEMPLATE, SENT_PROPOSAL
from estimator.proposal.read import ProposalFormatError, read_proposal
from estimator.text import squash

MISC_MONITORING_DEPTHS = [1, 2, 3, 2, 3, 2, 3, 2, 4, 4, 4, 4, 4, 4, 4, 3, 2, 2, 2, 3, 3, 2, 3, 3, 2, 3, 3, 3, 3, 4, 2]


def test_scope_heading_and_front_end(sent_scope):
    suffix, front_end, *_ = sent_scope
    assert suffix == "PREWAILING WAGE"
    assert (front_end.mode, front_end.existing_system_name) == ("new-system", None)
    assert [item.kind for item in front_end.items] == ["line"] * 7 + ["note"] * 5
    assert front_end.items[0].text == "Furnish Network Level Control Panel"
    assert front_end.items[1].text == "Furnish PC Workstation (School Operator Console )"
    assert front_end.items[5].text == "Furnish 3-D Graphics"
    assert all(run.bold for item in front_end.items for run in item.runs)


def test_blocks(sent_scope):
    blocks = sent_scope[2]
    assert len(blocks) == 44
    assert blocks[0].header == "*Qty (1) BACnet Data Cabinet"
    assert blocks[-1].header == "Provide 2 Year Guarantee for Workmanship and Material – 15970-49"
    items = [item for block in blocks for item in block.items]
    assert len(items) == 204
    assert Counter((i.kind, i.depth) for i in items) == {
        ("line", 1): 137, ("line", 2): 31, ("line", 3): 15, ("line", 4): 8, ("note", 1): 13}


def test_nesting_is_read_from_the_indent(sent_scope):
    misc = next(b for b in sent_scope[2] if b.header == "Misc Monitoring Systems")
    assert [item.depth for item in misc.items] == MISC_MONITORING_DEPTHS
    assert all(item.kind == "line" for item in misc.items)


def test_emphasis_survives(sent_scope):
    cabinet = sent_scope[2][0]
    server = next(i for i in cabinet.items if squash(i.text) == "Furnish and Install (Rack Mounted) BACnet Server")
    assert [run.text.strip() for run in server.runs if run.bold] == ["(Rack Mounted)"]


def test_alternates(sent_scope):
    add, deduct = sent_scope[3], sent_scope[4]
    assert [a.label for a in add] == ["ALT 1: Controls As per Sequence of operation 15985 – 18"]
    assert [b.header for b in add[0].blocks] == ["*Qty (1) Can Wash Kitchen Exhaust Fan EF-9"]
    assert [i.text for i in add[0].blocks[0].items] == [
        "Furnish and Install DDC Controller", "Furnish Fan Start / Stop and Status"]
    assert [a.label for a in deduct] == ["ALT #:"]
    assert [b.header for b in deduct[0].blocks] == ["Qty (1) Shower Room Exhaust Fan EF-2"]
    assert [i.kind for i in deduct[0].blocks[0].items] == ["line", "line", "note"]


def test_the_whole_proposal(sent_job):
    assert sent_job.header.quote_number == "26-0246"
    assert sent_job.scope_heading_suffix == "PREWAILING WAGE"
    assert len(sent_job.blocks) == 44
    assert sent_job.named_exceptions == ("EXCEPTION TO ANY WORK WITH EXHAUST FAN EF-4 (24/7 OPERATION)",)
    assert sent_job.front_end.tech_hours is None and sent_job.blocks[0].items[0].quantity is None


def test_a_table_inside_the_scope_is_refused(tmp_path):
    document = docx.Document(str(SENT_PROPOSAL))
    table = document.add_table(rows=1, cols=1)
    heading = next(p for p in document.paragraphs if squash(p.text).startswith("SCOPE OF WORK"))
    heading._p.addnext(table._tbl)
    edited = tmp_path / "with-table.docx"
    document.save(str(edited))
    with pytest.raises(ProposalFormatError, match="table"):
        read_proposal(edited, PROPOSAL_TEMPLATE)
```

Add to `tests/conftest.py`:
```python
from estimator.proposal.read import read_proposal, read_scope


@pytest.fixture(scope="session")
def sent_scope(sent_document):
    return read_scope(sent_document)


@pytest.fixture(scope="session")
def sent_job():
    return read_proposal(SENT_PROPOSAL, PROPOSAL_TEMPLATE)
```

- [ ] **Step 2: Run to see it fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_read_scope.py -v`
Expected: ERROR loading conftest — `ImportError: cannot import name 'read_proposal' from 'estimator.proposal.read'`.

- [ ] **Step 3: Append the scope reader to `src/estimator/proposal/read.py`**

```python
# --- the scope of work ------------------------------------------------------------

def read_proposal(path: Path, template_path: Path) -> Job:
    """A sent proposal as a Job. A proposal carries no hours or quantities, so those stay empty."""
    document = docx.Document(str(path))
    suffix, front_end, blocks, add, deduct = read_scope(document)
    return Job(
        header=read_cover(document),
        scope_heading_suffix=suffix,
        front_end=front_end,
        blocks=blocks,
        add_alternates=add,
        deduct_alternates=deduct,
        named_exceptions=read_named_exceptions(document, template_path),
    )


def read_scope(document: DocxDocument):
    """(scope heading suffix, front end, blocks, add alternates, deduct alternates)."""
    lists = WordLists(document)
    paragraphs = [p for p in document.paragraphs if p.text.strip()]
    start = _find(paragraphs, layout.SCOPE_HEADING)
    end = _find(paragraphs, layout.CLARIFICATIONS)
    _refuse_tables_between(document, paragraphs[start], paragraphs[end])
    suffix = squash(paragraphs[start].text)[len(layout.SCOPE_HEADING):].strip()
    mode, existing = _front_end_mode(squash(paragraphs[start + 1].text))

    front_end_items: list[Item] = []
    blocks: list[dict] = []
    alternates: dict[str, list[dict]] = {"add": [], "deduct": []}
    section = "front end"
    items: list[Item] | None = None
    for paragraph in paragraphs[start + 2 : end]:
        text = squash(paragraph.text)
        if text.upper().startswith(layout.ADD_ALTERNATES):
            section, items = "add", None
            continue
        if text.upper().startswith(layout.DEDUCT_ALTERNATES):
            section, items = "deduct", None
            continue
        if section in alternates and re.match(r"ALT\b", text):
            alternates[section].append({"label": text, "blocks": []})
            items = None
            continue
        if _is_block_header(paragraph):
            block = {"header": text, "items": []}
            if section == "front end":
                section = "blocks"
            if section == "blocks":
                blocks.append(block)
            elif alternates[section]:
                alternates[section][-1]["blocks"].append(block)
            else:
                raise ProposalFormatError(f"{text!r} sits under the {section} alternates before any ALT line")
            items = block["items"]
            continue
        item = _read_item(paragraph, lists, in_front_end=(section == "front end"))
        if section == "front end":
            front_end_items.append(item)
        elif items is not None:
            items.append(item)
        else:
            raise ProposalFormatError(f"{text!r} sits outside any block")

    front_end = FrontEnd(mode=mode, existing_system_name=existing, items=tuple(front_end_items))
    return (
        suffix,
        front_end,
        tuple(_block(b) for b in blocks),
        _alternates(alternates["add"]),
        _alternates(alternates["deduct"]),
    )


def _alternates(raw: list[dict]) -> tuple[Alternate, ...]:
    """The template's own empty "ALT #:" line is a placeholder, not an alternate — leave it out."""
    return tuple(_alternate(a) for a in raw if a["blocks"] or a["label"] != layout.ALTERNATE_LABEL)


def _find(paragraphs: list[Paragraph], heading: str) -> int:
    for index, paragraph in enumerate(paragraphs):
        if squash(paragraph.text).startswith(heading):
            return index
    raise ProposalFormatError(f"can't find {heading!r}")


def _refuse_tables_between(document: DocxDocument, first: Paragraph, last: Paragraph) -> None:
    inside = False
    for element in document.element.body.iterchildren():
        if element is first._p:
            inside = True
        elif element is last._p:
            return
        elif inside and element.tag == qn("w:tbl"):
            raise ProposalFormatError("a table sits inside the scope of work; the reader doesn't handle tables yet")


def _front_end_mode(heading: str) -> tuple[str, str | None]:
    if heading.startswith(layout.NEW_SYSTEM_HEADING):
        return "new-system", None
    if heading.startswith(layout.EXISTING_SYSTEM_HEADING):
        name = heading[len(layout.EXISTING_SYSTEM_HEADING):].strip()
        return "extend-existing", re.sub(r"\s*BMS$", "", name).strip()
    raise ProposalFormatError(f"expected the front-end heading after SCOPE OF WORK, found {heading!r}")


def _is_block_header(paragraph: Paragraph) -> bool:
    """A PR2 paragraph with nothing written over the template's outline numbering — Word numbers it."""
    return paragraph.style.name == layout.OUTLINE_STYLE and WordLists.written_numbering(paragraph) is None


def _read_item(paragraph: Paragraph, lists: WordLists, *, in_front_end: bool) -> Item:
    stretches = merged_runs(paragraph)
    if re.sub(r"\s+", "", "".join(t for t, _ in stretches)) != re.sub(r"\s+", "", visible_text(paragraph)):
        raise ProposalFormatError(
            f"part of {squash(paragraph.text)!r} sits inside something the reader doesn't handle yet "
            "(a tracked change, a content control or a text box)")
    runs = tuple(Run(text=re.sub(r"\s+", " ", text), bold=bold) for text, bold in stretches)
    if lists.numbering(paragraph) is None:
        return Item(kind="note", runs=runs)
    base, step = ((layout.FRONT_END_LINE_INDENT, layout.FRONT_END_LINE_STEP) if in_front_end
                  else (layout.BLOCK_LINE_INDENT, layout.BLOCK_LINE_STEP))
    depth = max(1, 1 + round((lists.left_indent(paragraph) - base) / step))
    limit = 2 if in_front_end else 5
    if depth > limit:
        raise ProposalFormatError(f"{squash(paragraph.text)!r} is indented to depth {depth}; the most is {limit}")
    return Item(kind="line", depth=depth, runs=runs)


def _block(raw: dict) -> Block:
    return Block(header=raw["header"], items=tuple(raw["items"]))


def _alternate(raw: dict) -> Alternate:
    return Alternate(label=raw["label"], blocks=tuple(_block(b) for b in raw["blocks"]))
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_read_scope.py tests/test_read_cover.py -v`
Expected: 12 passed.

If `test_blocks` or `test_nesting_is_read_from_the_indent` fails with different numbers, **stop and report the actual numbers** — do not change the expected values. They were measured independently while planning.

If the hidden-text check raises on 26-0246, stop and report the paragraph it names. Do not weaken the check.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: read a sent proposal's scope — front end, 44 blocks, nesting by indent, alternates

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Writing the proposal — cover page and front-end choice

**Files:**
- Create: `src/estimator/proposal/write.py`, `tests/test_write_cover.py`

**Interfaces:**
- Consumes: `layout` (Task 4), `WordLists`, `squash` (Task 3), `Job`, `Header` (Task 2).
- Produces:
  - `TemplateError(ValueError)`
  - `check_template(document) -> None` — raises `TemplateError` naming every problem.
  - `write_proposal(job: Job, template_path: Path, out_path: Path) -> Path` — in this task it writes the cover page, keeps one opening and adds the scope heading's suffix. It raises `NotImplementedError` if the job has any front-end items, blocks, alternates or named exceptions; Task 8 removes that.

- [ ] **Step 1: Write the failing tests**

`tests/test_write_cover.py`:
```python
import shutil

import docx
import pytest
from docx.oxml.ns import qn
from docx.table import _Cell

from estimator.proposal import layout
from estimator.proposal.write import TemplateError, check_template, write_proposal
from estimator.scope import FrontEnd
from estimator.text import squash


def _cover_runs(path):
    document = docx.Document(str(path))
    table = document.tables[0]
    return [p for tc in table._tbl.iter(qn("w:tc")) for p in _Cell(tc, table).paragraphs if p.text.strip()]


def _texts(path):
    return [squash(p.text) for p in docx.Document(str(path)).paragraphs if p.text.strip()]


def test_the_template_is_recognised(template_document):
    check_template(template_document)


def test_a_changed_template_is_refused(proposal_template, tmp_path):
    document = docx.Document(str(proposal_template))
    heading = next(p for p in document.paragraphs if squash(p.text) == layout.ADD_ALTERNATES)
    heading.runs[0].text = "OPTIONAL EXTRAS:"
    with pytest.raises(TemplateError, match="ADD ALTERNATES"):
        check_template(document)


def test_the_cover_page_is_filled(bare_job, proposal_template, tmp_path):
    out = write_proposal(bare_job, proposal_template, tmp_path / "p.docx")
    assert [squash(p.text) for p in _cover_runs(out)] == [
        "To: All Bidders",
        "Date: 6/8/2026",
        "Quote #: 26-9999",
        "Reference: Test Building, 1 Main St",
        "MEP Engineer: Test MEP",
        "Based on Plans and Specs:",
        "M-001 thru M-100 Dated: 01/02/2026",
        "Specs 23 09 00",
    ]


def test_the_date_is_written_down_not_left_as_a_field(bare_job, proposal_template, tmp_path):
    out = write_proposal(bare_job, proposal_template, tmp_path / "p.docx")
    date = next(p for p in _cover_runs(out) if p.text.startswith("Date:"))
    assert date._p.find(f".//{qn('w:fldChar')}") is None


def test_labels_keep_their_red_and_values_stay_dark(bare_job, proposal_template, tmp_path):
    out = write_proposal(bare_job, proposal_template, tmp_path / "p.docx")
    quote = next(p for p in _cover_runs(out) if p.text.startswith("Quote"))
    colours = {r.text: r.font.color.rgb for r in quote.runs}
    assert str(colours["Quote #: "]) == "EC1E27"
    assert str(colours["26-9999"]) == "231F20"


def test_a_new_system_keeps_only_its_own_opening(bare_job, proposal_template, tmp_path):
    texts = _texts(write_proposal(bare_job, proposal_template, tmp_path / "p.docx"))
    assert sum(t.startswith(layout.OPENING) for t in texts) == 1
    assert sum(t.startswith(layout.SCOPE_HEADING) for t in texts) == 1
    assert layout.NEW_SYSTEM_HEADING in texts
    assert layout.OR_LINE not in texts
    assert not [t for t in texts if t.startswith(layout.EXISTING_SYSTEM_HEADING) or "IT Infrastructure" in t]


def test_extending_an_existing_system(bare_job, proposal_template, tmp_path):
    job = bare_job.model_copy(update={"front_end": FrontEnd(mode="extend-existing", existing_system_name="Honeywell WEBs")})
    out = write_proposal(job, proposal_template, tmp_path / "p.docx")
    texts = _texts(out)
    openings = [t for t in texts if t.startswith(layout.OPENING)]
    assert len(openings) == 1 and "extension of the existing" in openings[0]
    assert "Seamlessly Tie in to the Existing Honeywell WEBs BMS" in texts
    assert layout.NEW_SYSTEM_HEADING not in texts and layout.OR_LINE not in texts
    heading = next(p for p in docx.Document(str(out)).paragraphs if squash(p.text).startswith(layout.EXISTING_SYSTEM_HEADING))
    assert not [r for r in heading.runs if r.font.color.rgb is not None and str(r.font.color.rgb) == "FF0000"]


def test_scope_heading_suffix(bare_job, proposal_template, tmp_path):
    assert "SCOPE OF WORK – PREVAILING WAGE" in _texts(write_proposal(bare_job, proposal_template, tmp_path / "p.docx"))


def test_the_rest_of_the_template_is_untouched(bare_job, proposal_template, tmp_path):
    out_texts = _texts(write_proposal(bare_job, proposal_template, tmp_path / "p.docx"))
    template_texts = _texts(proposal_template)
    start = next(i for i, t in enumerate(template_texts) if t == layout.ADD_ALTERNATES)
    assert out_texts[out_texts.index(layout.ADD_ALTERNATES):] == template_texts[start:]


def test_scope_content_waits_for_the_next_task(small_job, proposal_template, tmp_path):
    with pytest.raises(NotImplementedError):
        write_proposal(small_job, proposal_template, tmp_path / "p.docx")
```

- [ ] **Step 2: Run to see it fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_write_cover.py -v`
Expected: collection error — `ModuleNotFoundError: No module named 'estimator.proposal.write'`.

- [ ] **Step 3: Write `src/estimator/proposal/write.py`**

```python
"""Fill the AME proposal template with a Job.

The template is the team's own file, used as it is. Everything the tool does
not write — the clarifications, the exclusions, the cover and back pages, the
signature — stays exactly as the team wrote it (the template-owns-the-
boilerplate guarantee). The tool writes only fields of the Job, into the places
named below, so nothing internal can reach the client document (the
nothing-internal-reaches-the-client guarantee).
"""
from __future__ import annotations

import copy
import datetime as dt
from pathlib import Path

import docx
from docx.document import Document as DocxDocument
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, Twips
from docx.table import _Cell
from docx.text.paragraph import Paragraph

from estimator.proposal import layout
from estimator.proposal.layout import ParagraphFormat
from estimator.proposal.word import WordLists
from estimator.scope import Alternate, Block, Header, Item, Job, Run
from estimator.text import squash

_XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"


class TemplateError(ValueError):
    """The template has changed in a way the tool doesn't recognise."""


def write_proposal(job: Job, template_path: Path, out_path: Path) -> Path:
    if job.front_end.items or job.blocks or job.add_alternates or job.deduct_alternates or job.named_exceptions:
        raise NotImplementedError("writing the scope of work is added in the next task")
    document = docx.Document(str(template_path))
    check_template(document)
    _fill_cover(document, job.header)
    _keep_front_end(document, job)
    _set_scope_suffix(document, job.scope_heading_suffix)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    document.save(str(out_path))
    return out_path


def check_template(document: DocxDocument) -> None:
    """Refuse a template the tool doesn't recognise, rather than fill it wrongly."""
    lists = WordLists(document)
    texts = [squash(p.text) for p in document.paragraphs]
    problems = []
    for prefix, expected in (
        (layout.OPENING, 2), (layout.SCOPE_HEADING, 2), (layout.NEW_SYSTEM_HEADING, 1),
        (layout.EXISTING_SYSTEM_HEADING, 1), (layout.ADD_ALTERNATES, 1), (layout.DEDUCT_ALTERNATES, 1),
        (layout.CLARIFICATIONS, 1), (layout.EXCLUSIONS, 1), (layout.BASE_PRICE, 1),
    ):
        found = sum(1 for t in texts if t.startswith(prefix))
        if found != expected:
            problems.append(f"expected {expected} paragraph(s) starting {prefix!r}, found {found}")
    if texts.count(layout.OR_LINE) != 1:
        problems.append("expected one 'OR' line between the two openings")
    if texts.count(layout.ALTERNATE_LABEL) != 2:
        problems.append(f"expected two {layout.ALTERNATE_LABEL!r} lines")
    for list_id, levels in ((layout.BLOCK_LINE_LIST, range(4, 9)),
                            (layout.FRONT_END_LIST["new-system"], (1, 2)),
                            (layout.FRONT_END_LIST["extend-existing"], (1, 2))):
        for level in levels:
            if not lists.has_level(list_id, level):
                problems.append(f"list {list_id} has no level {level}")
    if lists.style_numbering(layout.OUTLINE_STYLE) is None:
        problems.append(f"style {layout.OUTLINE_STYLE} no longer numbers its paragraphs")
    if problems:
        raise TemplateError("the proposal template has changed: " + "; ".join(problems))


# --- the cover page ---------------------------------------------------------------

def _fill_cover(document: DocxDocument, header: Header) -> None:
    table = document.tables[0]
    cells = [_Cell(tc, table) for tc in table._tbl.iter(qn("w:tc"))]

    def cell(label: str) -> _Cell:
        for candidate in cells:
            if candidate.paragraphs and squash(candidate.paragraphs[0].text).startswith(label):
                return candidate
        raise TemplateError(f"the cover page has no {label!r}")

    _set_after_label(cell("To:").paragraphs[0], "To:", header.to)
    _set_date(cell("Date:").paragraphs[0], header.date)
    _set_after_label(cell("Quote").paragraphs[0], "Quote #:", header.quote_number)
    _set_after_label(cell("Reference").paragraphs[0], "Reference:", header.reference)
    _set_after_label(cell("MEP Engineer:").paragraphs[0], "MEP Engineer:", header.mep_engineer)
    _set_lines(cell("Based on Plans and Specs:"), header.based_on)


def _run_text(run) -> str:
    return "".join(t.text or "" for t in run.findall(qn("w:t")))


def _set_run_text(run, text: str) -> None:
    """Replace a run's text, keeping its formatting."""
    for child in list(run):
        if child.tag != qn("w:rPr"):
            run.remove(child)
    t = OxmlElement("w:t")
    t.text = text
    t.set(_XML_SPACE, "preserve")
    run.append(t)


def _replace_text(paragraph: Paragraph, text: str) -> None:
    """Give a paragraph new text in the format of its first run."""
    runs = paragraph._p.findall(qn("w:r"))
    if not runs:
        raise TemplateError(f"nothing to write into in {paragraph.text!r}")
    _set_run_text(runs[0], text)
    for run in runs[1:]:
        run.getparent().remove(run)


def _set_after_label(paragraph: Paragraph, label: str, value: str) -> None:
    """Replace whatever follows a red label like "Quote #:" with the value, in the value's own colour."""
    runs = paragraph._p.findall(qn("w:r"))
    seen = ""
    for index, run in enumerate(runs):
        seen += _run_text(run)
        if squash(seen).endswith(label):
            break
    else:
        raise TemplateError(f"{label!r} not found in {paragraph.text!r}")
    rest = runs[index + 1:]
    while rest and not _run_text(rest[0]).strip():
        rest = rest[1:]
    if not rest:
        raise TemplateError(f"nothing to fill after {label!r}")
    _set_run_text(rest[0], value)
    for run in rest[1:]:
        run.getparent().remove(run)


def _us_date(when: dt.date) -> str:
    return f"{when.month}/{when.day}/{when.year}"


def _set_date(paragraph: Paragraph, when: dt.date) -> None:
    """Write the date as text. The template's DATE field would show today's date every time the file opened."""
    runs = paragraph._p.findall(qn("w:r"))
    kinds = []
    for run in runs:
        char = run.find(qn("w:fldChar"))
        kinds.append(char.get(qn("w:fldCharType")) if char is not None else None)
    if "begin" not in kinds:
        _set_after_label(paragraph, "Date:", _us_date(when))
        return
    begin = kinds.index("begin")
    end = kinds.index("end", begin)
    separate = kinds.index("separate", begin, end)
    written = copy.deepcopy(runs[separate + 1])
    _set_run_text(written, _us_date(when))
    runs[begin].addprevious(written)
    for run in runs[begin : end + 1]:
        run.getparent().remove(run)


def _set_lines(cell: _Cell, lines: tuple[str, ...]) -> None:
    """Fill the placeholder line under "Based on Plans and Specs:", one paragraph per line."""
    placeholder = next((p for p in cell.paragraphs[1:] if "#" in p.text), None)
    if placeholder is None:
        raise TemplateError("the cover page has no placeholder line under 'Based on Plans and Specs:'")
    _replace_text(placeholder, lines[0])
    previous = placeholder._p
    for line in lines[1:]:
        clone = copy.deepcopy(placeholder._p)
        _replace_text(Paragraph(clone, placeholder._parent), line)
        previous.addnext(clone)
        previous = clone


# --- the front-end choice ---------------------------------------------------------

def _paragraph(document: DocxDocument, prefix: str) -> Paragraph:
    for paragraph in document.paragraphs:
        if squash(paragraph.text).startswith(prefix):
            return paragraph
    raise TemplateError(f"the template has no paragraph starting {prefix!r}")


def _delete_between(first: Paragraph, last: Paragraph) -> None:
    element = first._p.getnext()
    while element is not None and element is not last._p:
        following = element.getnext()
        if element.tag == qn("w:tbl"):
            raise TemplateError("a table sits inside the front-end block of the template")
        element.getparent().remove(element)
        element = following
    if element is None:
        raise TemplateError("the front-end block runs to the end of the template")


def _delete_from_until(first: Paragraph, stop: Paragraph) -> None:
    element = first._p
    while element is not None and element is not stop._p:
        following = element.getnext()
        element.getparent().remove(element)
        element = following


def _set_existing_name(heading: Paragraph, name: str) -> None:
    runs = heading._p.findall(qn("w:r"))
    red = []
    for run in runs:
        colour = run.find(f"{qn('w:rPr')}/{qn('w:color')}")
        if colour is not None and (colour.get(qn("w:val")) or "").upper() == layout.EXISTING_NAME_COLOUR:
            red.append(run)
    if not red:
        raise TemplateError("the red placeholder for the existing system's name is gone")
    # The placeholder carries the spaces either side of the name ("Honeywell / Niagara N4 "); keep them.
    original = "".join(_run_text(run) for run in red)
    before = original[: len(original) - len(original.lstrip())]
    after = original[len(original.rstrip()):]
    model = runs[0].find(qn("w:rPr"))
    first = red[0]
    old = first.find(qn("w:rPr"))
    if old is not None:
        first.remove(old)
    if model is not None:
        first.insert(0, copy.deepcopy(model))
    _set_run_text(first, f"{before}{name}{after}")
    for run in red[1:]:
        run.getparent().remove(run)


def _keep_front_end(document: DocxDocument, job: Job) -> Paragraph:
    """Keep the job's opening and front-end heading; remove the other opening and every default line.

    Returns the kept front-end heading: the job's own front-end lines go straight after it.
    """
    openings = [p for p in document.paragraphs if squash(p.text).startswith(layout.OPENING)]
    new_heading = _paragraph(document, layout.NEW_SYSTEM_HEADING)
    existing_heading = _paragraph(document, layout.EXISTING_SYSTEM_HEADING)
    add_heading = _paragraph(document, layout.ADD_ALTERNATES)
    if job.front_end.mode == "new-system":
        _delete_between(new_heading, add_heading)
        return new_heading
    _delete_from_until(openings[0], openings[1])
    _delete_between(existing_heading, add_heading)
    _set_existing_name(existing_heading, job.front_end.existing_system_name)
    return existing_heading


def _set_scope_suffix(document: DocxDocument, suffix: str) -> None:
    if not suffix:
        return
    heading = _paragraph(document, layout.SCOPE_HEADING)
    runs = heading._p.findall(qn("w:r"))
    extra = copy.deepcopy(runs[-1])
    _set_run_text(extra, suffix if heading.text.endswith((" ", "\xa0")) else f" {suffix}")
    runs[-1].addnext(extra)
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_write_cover.py -v`
Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: fill the template's cover page and keep the right opening

The cover date is written as text: the template's live DATE field shows
today's date every time a proposal is reopened.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Writing the proposal — the scope of work, and the round trip

**Files:**
- Modify: `src/estimator/proposal/write.py`
- Create: `src/estimator/proposal/sections.py`, `tests/test_write_scope.py`, `tests/test_round_trip.py`
- Modify: `tests/test_write_cover.py` (delete `test_scope_content_waits_for_the_next_task`)

**Interfaces:**
- Consumes: Task 7's `write.py`; `read_proposal` (Task 6).
- Produces:
  - `write_proposal(job, template_path, out_path) -> Path` — now writes everything.
  - `estimator.proposal.sections`: `scope_texts(path) -> list[str]` (from `SCOPE OF WORK` to before the clarifications), `closing_texts(path) -> list[str]` (from the clarifications to the end), `opening_texts(path) -> list[str]` (before the opening sentence), `cover_lines(path) -> list[str]` (the cover-page table's lines). All squashed, empty lines dropped.

- [ ] **Step 1: Write the failing tests**

`tests/test_write_scope.py`:
```python
import docx
from docx.shared import Pt, Twips

from estimator.proposal import layout
from estimator.proposal.sections import closing_texts, opening_texts, scope_texts
from estimator.proposal.word import WordLists
from estimator.proposal.write import write_proposal
from estimator.text import squash

INTERNAL_MARKERS = ("🟡", "🔴", "🟠", "🟢", "PRICE PENDING", "PRICE NEEDS REVIEW", "[CONFIRMED", "ASSUMPTION]",
                    "Estimation Assistant", "Estimator AI", "generated by")


def _written(small_job, proposal_template, tmp_path):
    out = write_proposal(small_job, proposal_template, tmp_path / "p.docx")
    return out, docx.Document(str(out))


def _paragraph(document, text):
    return next(p for p in document.paragraphs if squash(p.text) == text)


def test_block_headers(small_job, proposal_template, tmp_path):
    _, document = _written(small_job, proposal_template, tmp_path)
    header = _paragraph(document, "Qty (2) Exhaust Fan EF-1, 2")
    assert header.style.name == "PR2" and WordLists.written_numbering(header) is None
    assert header.paragraph_format.left_indent == Twips(1566)
    assert all(r.bold for r in header.runs) and header.runs[0].font.size == Pt(12)


def test_lines_and_notes(small_job, proposal_template, tmp_path):
    _, document = _written(small_job, proposal_template, tmp_path)
    assert WordLists.written_numbering(_paragraph(document, "Furnish and Install DDC Controller")) == (12, 4)
    assert WordLists.written_numbering(_paragraph(document, "Mfr. to Provide Relay")) == (12, 5)
    note = _paragraph(document, "*DAMPERS BY OTHERS")
    assert WordLists.written_numbering(note) is None and note.paragraph_format.left_indent == Twips(1440)


def test_front_end_lines_and_notes(small_job, proposal_template, tmp_path):
    _, document = _written(small_job, proposal_template, tmp_path)
    line = _paragraph(document, "Furnish Network Level Control Panel")
    assert WordLists.written_numbering(line) == (11, 1)
    assert line.runs[0].bold and line.runs[0].font.size == Pt(12)
    note = _paragraph(document, "*CONNECTION TO OWNER WAN BY OTHERS")
    assert WordLists.written_numbering(note) is None and note.paragraph_format.left_indent == Twips(720)


def test_emphasis_inside_a_line(small_job, proposal_template, tmp_path):
    _, document = _written(small_job, proposal_template, tmp_path)
    line = _paragraph(document, "Furnish and Install (Duct Mounted) Static Pressure Sensor")
    assert [r.text for r in line.runs if r.bold] == ["(Duct Mounted)"]


def test_each_block_header_has_a_blank_line_before_it(small_job, proposal_template, tmp_path):
    _, document = _written(small_job, proposal_template, tmp_path)
    paragraphs = document.paragraphs
    headers = {b.header for b in small_job.blocks} | {b.header for a in small_job.add_alternates for b in a.blocks}
    for index, paragraph in enumerate(paragraphs):
        if squash(paragraph.text) in headers:
            assert not paragraphs[index - 1].text.strip()


def test_word_numbers_exactly_the_block_headers(small_job, proposal_template, tmp_path):
    _, document = _written(small_job, proposal_template, tmp_path)
    paragraphs = [p for p in document.paragraphs if p.text.strip()]
    end = next(i for i, p in enumerate(paragraphs) if squash(p.text).startswith(layout.CLARIFICATIONS))
    numbered = [squash(p.text) for p in paragraphs[:end] if p.style.name == "PR2" and WordLists.written_numbering(p) is None]
    assert numbered == [b.header for b in small_job.blocks] + [b.header for a in small_job.add_alternates for b in a.blocks]
    assert not [p for p in paragraphs[:end] if p.style.name == "PR1"]


def test_alternates(small_job, proposal_template, tmp_path):
    out, document = _written(small_job, proposal_template, tmp_path)
    texts = scope_texts(out)
    at = texts.index(layout.ADD_ALTERNATES)
    assert texts[at + 1 : at + 4] == ["ALT 1: Controls for EF-3", "Qty (1) Exhaust Fan EF-3", "Furnish and Install DDC Controller"]
    assert texts[texts.index(layout.DEDUCT_ALTERNATES) + 1] == layout.ALTERNATE_LABEL
    assert WordLists.written_numbering(_paragraph(document, "ALT 1: Controls for EF-3")) == (23, 0)


def test_named_exceptions_follow_the_standard_list(small_job, proposal_template, tmp_path):
    out, _ = _written(small_job, proposal_template, tmp_path)
    closing = closing_texts(out)
    base = next(i for i, t in enumerate(closing) if t.startswith(layout.BASE_PRICE))
    assert closing[base - 1] == "EXCEPTION TO ANY WORK WITH EXHAUST FAN EF-4"
    assert [t for t in closing if t != "EXCEPTION TO ANY WORK WITH EXHAUST FAN EF-4"] == closing_texts(proposal_template)


def test_the_cover_and_heading_area_is_untouched(small_job, proposal_template, tmp_path):
    out, _ = _written(small_job, proposal_template, tmp_path)
    assert opening_texts(out) == opening_texts(proposal_template)


def test_nothing_internal_reaches_the_client_document(small_job, proposal_template, tmp_path):
    out, document = _written(small_job, proposal_template, tmp_path)
    everything = "\n".join(p.text for p in document.paragraphs).lower()
    assert not [m for m in INTERNAL_MARKERS if m.lower() in everything]
    template_text = "\n".join(p.text for p in docx.Document(str(proposal_template)).paragraphs).lower()
    assert not [m for m in INTERNAL_MARKERS if m.lower() in template_text], "the marker list must not flag the template itself"
```

`tests/test_round_trip.py`:
```python
from estimator.proposal.read import read_proposal
from estimator.proposal.sections import closing_texts, opening_texts, scope_texts
from estimator.proposal.write import write_proposal
from estimator.scope import FrontEnd


def test_a_written_job_reads_back_the_same(small_job, proposal_template, tmp_path, without_prices):
    out = write_proposal(small_job, proposal_template, tmp_path / "p.docx")
    assert read_proposal(out, proposal_template) == without_prices(small_job)


def test_an_extend_existing_job_reads_back_the_same(small_job, proposal_template, tmp_path, without_prices):
    front_end = FrontEnd(mode="extend-existing", existing_system_name="Honeywell WEBs", items=small_job.front_end.items)
    job = small_job.model_copy(update={"front_end": front_end})
    out = write_proposal(job, proposal_template, tmp_path / "p.docx")
    assert read_proposal(out, proposal_template) == without_prices(job)


def test_26_0246_written_out_again_matches_what_was_sent(sent_job, proposal_template, sent_proposal, tmp_path):
    out = write_proposal(sent_job, proposal_template, tmp_path / "26-0246.docx")
    assert scope_texts(out) == scope_texts(sent_proposal)
    assert closing_texts(out) == closing_texts(sent_proposal)
    assert opening_texts(out) == opening_texts(sent_proposal)
    assert read_proposal(out, proposal_template) == sent_job
```

- [ ] **Step 2: Run to see it fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_write_scope.py tests/test_round_trip.py -v`
Expected: collection error — `ModuleNotFoundError: No module named 'estimator.proposal.sections'`.

- [ ] **Step 3: Write `src/estimator/proposal/sections.py`**

```python
"""A proposal's parts as plain text — for checking one proposal against another."""
from __future__ import annotations

from pathlib import Path

import docx
from docx.oxml.ns import qn
from docx.table import _Cell

from estimator.proposal import layout
from estimator.text import squash


def _texts(path: Path) -> list[str]:
    return [squash(p.text) for p in docx.Document(str(path)).paragraphs if p.text.strip()]


def _index(texts: list[str], prefix: str) -> int:
    return next(i for i, t in enumerate(texts) if t.startswith(prefix))


def scope_texts(path: Path) -> list[str]:
    """Every line from SCOPE OF WORK down to, not including, the clarifications."""
    texts = _texts(path)
    return texts[_index(texts, layout.SCOPE_HEADING) : _index(texts, layout.CLARIFICATIONS)]


def closing_texts(path: Path) -> list[str]:
    """Every line from the clarifications to the end — the part the template owns."""
    texts = _texts(path)
    return texts[_index(texts, layout.CLARIFICATIONS) :]


def opening_texts(path: Path) -> list[str]:
    """Every line before the opening sentence — the heading area the template owns."""
    texts = _texts(path)
    return texts[: _index(texts, layout.OPENING)]


def cover_lines(path: Path) -> list[str]:
    """The cover page table, line by line."""
    document = docx.Document(str(path))
    table = document.tables[0]
    return [squash(p.text) for tc in table._tbl.iter(qn("w:tc")) for p in _Cell(tc, table).paragraphs if p.text.strip()]
```

- [ ] **Step 4: Complete `write_proposal` in `src/estimator/proposal/write.py`**

Replace the whole `write_proposal` function with:
```python
def write_proposal(job: Job, template_path: Path, out_path: Path) -> Path:
    document = docx.Document(str(template_path))
    check_template(document)
    _fill_cover(document, job.header)
    heading = _keep_front_end(document, job)
    _set_scope_suffix(document, job.scope_heading_suffix)
    _write_scope(heading, job)
    _write_alternates(document, layout.ADD_ALTERNATES, job.add_alternates)
    _write_alternates(document, layout.DEDUCT_ALTERNATES, job.deduct_alternates)
    _add_named_exceptions(document, job.named_exceptions)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    document.save(str(out_path))
    return out_path
```

Append to the end of `src/estimator/proposal/write.py`:
```python
# --- the scope of work ------------------------------------------------------------

def _apply(paragraph: Paragraph, fmt: ParagraphFormat, runs: tuple[Run, ...]) -> None:
    paragraph.style = fmt.style
    if fmt.list_id is not None:
        numPr = paragraph._p.get_or_add_pPr().get_or_add_numPr()
        numPr.get_or_add_ilvl().val = fmt.level
        numPr.get_or_add_numId().val = fmt.list_id
    if fmt.indent is not None:
        paragraph.paragraph_format.left_indent = Twips(fmt.indent)
    if fmt.space_after is not None:
        paragraph.paragraph_format.space_after = Pt(fmt.space_after)
    for part in runs:
        run = paragraph.add_run(part.text)
        if fmt.bold or part.bold:
            run.bold = True
        if fmt.size is not None:
            run.font.size = Pt(fmt.size)


def _insert_after(cursor: Paragraph, fmt: ParagraphFormat, runs: tuple[Run, ...] = ()) -> Paragraph:
    element = OxmlElement("w:p")
    cursor._p.addnext(element)
    paragraph = Paragraph(element, cursor._parent)
    _apply(paragraph, fmt, runs)
    return paragraph


def _front_end_format(mode: str, item: Item) -> ParagraphFormat:
    return layout.FRONT_END_NOTE if item.kind == "note" else layout.front_end_line(mode, item.depth)


def _block_format(item: Item) -> ParagraphFormat:
    return layout.BLOCK_NOTE if item.kind == "note" else layout.block_line(item.depth)


def _write_block(cursor: Paragraph, block: Block) -> Paragraph:
    cursor = _insert_after(cursor, layout.BLANK)
    cursor = _insert_after(cursor, layout.BLOCK_HEADER, (Run(text=block.header, bold=True),))
    for item in block.items:
        cursor = _insert_after(cursor, _block_format(item), item.runs)
    return cursor


def _write_scope(heading: Paragraph, job: Job) -> None:
    """The job's front-end lines straight after the kept heading, then every block, then a blank line."""
    cursor = heading
    for item in job.front_end.items:
        cursor = _insert_after(cursor, _front_end_format(job.front_end.mode, item), item.runs)
    for block in job.blocks:
        cursor = _write_block(cursor, block)
    _insert_after(cursor, layout.BLANK)


def _label_under(document: DocxDocument, section: str) -> Paragraph:
    paragraphs = document.paragraphs
    start = next(i for i, p in enumerate(paragraphs) if squash(p.text).startswith(section))
    for paragraph in paragraphs[start + 1 :]:
        text = squash(paragraph.text)
        if text == layout.ALTERNATE_LABEL:
            return paragraph
        if text:
            break
    raise TemplateError(f"no {layout.ALTERNATE_LABEL!r} line under {section!r}")


def _write_alternates(document: DocxDocument, section: str, alternates: tuple[Alternate, ...]) -> None:
    if not alternates:
        return
    label = _label_under(document, section)
    untouched_label = copy.deepcopy(label._p)
    cursor = label
    for index, alternate in enumerate(alternates):
        if index:
            element = copy.deepcopy(untouched_label)
            cursor._p.addnext(element)
            cursor = Paragraph(element, cursor._parent)
        _replace_text(cursor, alternate.label)
        for block in alternate.blocks:
            cursor = _write_block(cursor, block)


def _add_named_exceptions(document: DocxDocument, exceptions: tuple[str, ...]) -> None:
    if not exceptions:
        return
    paragraphs = document.paragraphs
    base = next(i for i, p in enumerate(paragraphs) if squash(p.text).startswith(layout.BASE_PRICE))
    last = next(p for p in reversed(paragraphs[:base]) if p.text.strip())
    cursor = last._p
    for text in exceptions:
        clone = copy.deepcopy(last._p)
        _replace_text(Paragraph(clone, last._parent), text)
        cursor.addnext(clone)
        cursor = clone
```

In `tests/test_write_cover.py`, delete the function `test_scope_content_waits_for_the_next_task`.

- [ ] **Step 5: Run the tests to see them pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_write_scope.py tests/test_round_trip.py tests/test_write_cover.py -v`
Expected: 22 passed (10 + 3 + 9).

If `test_26_0246_written_out_again_matches_what_was_sent` fails, print the first differing line of each list and report it — do not change the reader or writer to paper over it without saying what differed.

- [ ] **Step 6: Run everything**

Run: `.venv/Scripts/python.exe -m pytest -v`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat: write the scope of work; 26-0246 reads back identically after a round trip

Every block, line and note goes in with the one format its kind has, using
lists the template already defines. The proposal sent for 26-0246 is read,
written out again, and read back to the same Job.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: The price book

**Files:**
- Create: `src/estimator/price_sheet/price_book.py`, `tests/test_price_book.py`
- Modify: `tests/conftest.py` (add `price_book`)

**Interfaces:**
- Consumes: `squash`, `strip_list_marker` (Task 3).
- Produces:
  - `price_key(text: str) -> str` — list marker, leading verb and `– (Qty. N Total)…` removed; lower case.
  - `BookItem(name: str, price: float, sheet: str, row: int, needs_review: bool)`
  - `PriceBook(items: list[BookItem], aliases: dict[str, str])` — raises `ValueError` if two items share a key or an alias names a missing item. `.items`, `.lookup(scope_text) -> BookItem | None`, `.closest(scope_text, count=3) -> list[BookItem]`, classmethod `.load(book_path, aliases_path) -> PriceBook`.
  - Fixture (session): `price_book`.

- [ ] **Step 1: Write the failing tests**

`tests/test_price_book.py`:
```python
import pytest

from estimator.price_sheet.price_book import BookItem, PriceBook, price_key


@pytest.mark.parametrize("line, key", [
    ("o  Furnish and Install BACnet IP Router – (Qty. 7 Total)", "bacnet ip router"),
    ("Furnish NEMA 12K Enclosure – (Qty. 5 Total) Installation by Others", "nema 12k enclosure"),
    ("Install and wire Programmable Thermostat (Furnished by Unit Mfr.)", "programmable thermostat (furnished by unit mfr.)"),
    ("Furnish and Wire Filter DP Switch", "filter dp switch"),
    ("Furnish UPS", "ups"),
])
def test_price_key(line, key):
    assert price_key(line) == key


def test_every_priced_row_is_loaded(price_book):
    assert len(price_book.items) == 67
    assert sum(1 for i in price_book.items if i.sheet == "Parts Pricing") == 50
    assert sum(1 for i in price_book.items if i.sheet == "BMS-DDC-Panels") == 17


@pytest.mark.parametrize("line, price", [
    ("Furnish and Install Space Temperature Sensor", 142.0),
    ("Furnish UPS", 500.0),
    ("Furnish BMS Server", 2500.0),
    ("o  Furnish and Install Discharge Air Temperature Sensor – (Qty. 2 Total)", 25.0),
    ("Furnish and Install Space Temperature / CO2 Sensor", 182.0),
    ("Furnish and Install BACnet Thermostat – (Qty. 42 Total)", 355.0),
])
def test_known_prices(price_book, line, price):
    assert price_book.lookup(line).price == price


def test_no_guessing(price_book):
    assert price_book.lookup("Furnish and Install DDC Controller") is None
    assert price_book.lookup("Furnish and Install Damper Actuator") is None


def test_the_books_own_doubts_are_kept(price_book):
    assert price_book.lookup("Furnish and Wire Filter DP Switch").needs_review is True
    assert price_book.lookup("Furnish and Install Space Temperature Sensor").needs_review is False


def test_rows_without_a_price_are_not_items(price_book):
    assert price_book.lookup("Furnish and Install Horn and Strobe") is None
    assert "Horn and Strobe" not in {i.name for i in price_book.items}


def test_a_confirmed_alias_prices_a_line(price_book):
    book = PriceBook(price_book.items, {"Furnish and Install Damper Actuator": "Standard Damper Actuator"})
    assert book.lookup("o  Furnish and Install Damper Actuator – (Qty. 3 Total)").price == 320.0


def test_an_alias_to_a_missing_item_is_refused(price_book):
    with pytest.raises(ValueError, match="isn't in the price book"):
        PriceBook(price_book.items, {"damper actuator": "Golden Damper Actuator"})


def test_two_items_that_read_the_same_are_refused():
    items = [BookItem("UPS", 500, "a", 1, False), BookItem("Furnish UPS", 450, "a", 2, False)]
    with pytest.raises(ValueError, match="same"):
        PriceBook(items, {})


def test_closest_names_help_an_estimator_confirm_a_match(price_book):
    assert "Standard Damper Actuator" in [i.name for i in price_book.closest("Furnish and Install Damper Actuator")]
```

Add to `tests/conftest.py`:
```python
from estimator.price_sheet.price_book import PriceBook


@pytest.fixture(scope="session")
def price_book():
    return PriceBook.load(PRICE_BOOK, ALIASES)
```

- [ ] **Step 2: Run to see it fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_price_book.py -v`
Expected: ERROR loading conftest — `ModuleNotFoundError: No module named 'estimator.price_sheet.price_book'`.

- [ ] **Step 3: Write `src/estimator/price_sheet/price_book.py`**

```python
"""The AME price book: what each device costs, and which device is the standard pick.

Lookup is deliberately strict. A scope line is priced only when its name — with
the list marker, the leading verb and any "(Qty. N Total)" taken off — is the
same as a price book item's name, or when an estimator has confirmed the match
in the alias file. Anything else is PRICE PENDING: guessing a price is the same
failure as guessing a quantity.
"""
from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass
from pathlib import Path

import openpyxl

from estimator.text import squash, strip_list_marker

SHEETS = ("Parts Pricing", "BMS-DDC-Panels")
_QUANTITY = re.compile(r"\s*[–-]\s*\(qty\.?\s*\d+\s*total\).*$", re.IGNORECASE)
_VERB = re.compile(r"^(?:furnish and install|furnish and wire|install and wire|furnish|install|provide)\s+", re.IGNORECASE)


def price_key(text: str) -> str:
    """The part of a scope line that names the device, in lower case."""
    text = strip_list_marker(text)
    text = _QUANTITY.sub("", text)
    text = _VERB.sub("", text)
    return squash(text).casefold()


@dataclass(frozen=True)
class BookItem:
    name: str             # as the price book writes it
    price: float          # the Estimation Price column
    sheet: str
    row: int
    needs_review: bool    # the price book's own note says this price needs checking


class PriceBook:
    def __init__(self, items: list[BookItem], aliases: dict[str, str]) -> None:
        self.items = list(items)
        self._by_key: dict[str, BookItem] = {}
        for item in self.items:
            key = price_key(item.name)
            if key in self._by_key:
                raise ValueError(f"two price book items read the same once the verb is taken off: "
                                 f"{self._by_key[key].name!r} and {item.name!r}")
            self._by_key[key] = item
        by_name = {item.name: item for item in self.items}
        self._aliases: dict[str, BookItem] = {}
        for line, name in aliases.items():
            if name not in by_name:
                raise ValueError(f"the alias for {line!r} points at {name!r}, which isn't in the price book")
            self._aliases[price_key(line)] = by_name[name]

    @classmethod
    def load(cls, book_path: Path, aliases_path: Path) -> "PriceBook":
        workbook = openpyxl.load_workbook(str(book_path), data_only=True)
        items = []
        for sheet in SHEETS:
            ws = workbook[sheet]
            for row in range(1, ws.max_row + 1):
                name, price = ws.cell(row, 2).value, ws.cell(row, 3).value
                if isinstance(name, str) and name.strip() and isinstance(price, (int, float)) and not isinstance(price, bool):
                    note = ws.cell(row, 1).value
                    items.append(BookItem(name=name.strip(), price=float(price), sheet=sheet, row=row,
                                          needs_review=isinstance(note, str) and note.strip().startswith("Need")))
        aliases = json.loads(Path(aliases_path).read_text(encoding="utf-8"))["aliases"]
        return cls(items, aliases)

    def lookup(self, scope_text: str) -> BookItem | None:
        key = price_key(scope_text)
        return self._by_key.get(key) or self._aliases.get(key)

    def closest(self, scope_text: str, count: int = 3) -> list[BookItem]:
        """Price book items whose names come nearest — to help an estimator confirm a match, never to price."""
        keys = difflib.get_close_matches(price_key(scope_text), list(self._by_key), n=count, cutoff=0.4)
        return [self._by_key[key] for key in keys]
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_price_book.py -v`
Expected: 19 passed.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: the price book, with a strict lookup that never guesses a price

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: The price sheet as rows

**Files:**
- Create: `src/estimator/price_sheet/rows.py`, `tests/test_price_rows.py`

**Interfaces:**
- Consumes: `layout` (Task 4), scope models (Task 2), `squash`, `strip_list_marker` (Task 3).
- Produces:
  - column and row constants `FIRST_ROW = 6`, `LAST_ROW = 396`, `HOURS = 2`, `QUANTITY = 3`, `SCOPE = 4`, `UNIT_PRICE = 5`, `FLAG = 8`
  - `Row(text: str = "", hours: float | None = None, quantity: int | None = None, item: Item | None = None, ref: tuple = ())` — `ref` is the path into `Job.model_dump()` this row came from: `("front_end",)`, `("front_end", "items", j)`, `("blocks", i)`, `("blocks", i, "items", j)`, `("add_alternates", k, "blocks", i[, "items", j])`, same for `deduct_alternates`; `()` for headings, labels and blank rows.
  - `Sheet(title: str, rows: tuple[Row, ...])`
  - `sheet_plan(job) -> list[Sheet]` — `"Price Sheet 1"` for the base bid; then one sheet per alternate: `"ADD ALT"` / `"DEDUCT ALT"` when a section has one alternate, `"ADD ALT 1"`, `"ADD ALT 2"`… when it has several. Block numbers run on from the base into the alternates, exactly as Word numbers them.
  - `SentRow(sheet: str, row: int, text: str, hours: float | None, quantity: int | None, unit_price: float | None)`
  - `read_sent_rows(path: Path) -> dict[str, list[SentRow]]` — every sheet except `Summary`; rows 6–396 with text in column D.
  - `align(ours: list[str], theirs: list[str]) -> list[tuple[int, int]]` — pairs of indices of rows that say the same thing once list markers, spacing and case are ignored.

- [ ] **Step 1: Write the failing tests**

`tests/test_price_rows.py`:
```python
from estimator.price_sheet.rows import align, read_sent_rows, sheet_plan
from estimator.scope import Alternate
from estimator.text import squash, strip_list_marker


def test_the_base_sheet_follows_the_proposal(small_job):
    base = sheet_plan(small_job)[0]
    assert base.title == "Price Sheet 1"
    assert [row.text for row in base.rows if row.text] == [
        "SCOPE OF WORK – PREVAILING WAGE",
        "•  Front End Web Enabled BMS System",
        "o  Furnish Network Level Control Panel",
        "o  Furnish BMS Server",
        "*CONNECTION TO OWNER WAN BY OTHERS",
        "1.  Qty (2) Exhaust Fan EF-1, 2",
        "o  Furnish and Install DDC Controller",
        "➢  Mfr. to Provide Relay",
        "*DAMPERS BY OTHERS",
        "2.  Qty (1) Air Handling Unit AHU-1",
        "o  Furnish and Install Space Temperature Sensor",
        "o  Furnish and Wire Filter DP Switch",
        "o  Furnish and Install (Duct Mounted) Static Pressure Sensor",
    ]


def test_hours_sit_on_headings_and_quantities_on_lines(small_job):
    rows = {row.text: row for row in sheet_plan(small_job)[0].rows if row.text}
    assert rows["SCOPE OF WORK – PREVAILING WAGE"].hours == 40.0
    assert rows["1.  Qty (2) Exhaust Fan EF-1, 2"].hours == 8.0
    assert rows["o  Furnish and Install DDC Controller"].quantity == 2
    assert rows["o  Furnish and Install Space Temperature Sensor"].ref == ("blocks", 1, "items", 0)


def test_alternates_get_their_own_sheet_and_numbering_runs_on(small_job):
    alternate = sheet_plan(small_job)[1]
    assert alternate.title == "ADD ALT"
    assert [row.text for row in alternate.rows if row.text] == [
        "ADD ALTERNATES:", "1.  ALT 1: Controls for EF-3", "3.  Qty (1) Exhaust Fan EF-3",
        "o  Furnish and Install DDC Controller"]


def test_several_alternates_are_numbered_sheets(small_job):
    second = Alternate(label="ALT 2: Controls for EF-4", blocks=small_job.add_alternates[0].blocks)
    job = small_job.model_copy(update={"add_alternates": small_job.add_alternates + (second,)})
    assert [s.title for s in sheet_plan(job)] == ["Price Sheet 1", "ADD ALT 1", "ADD ALT 2"]


def test_reading_what_was_sent(sent_workup):
    sheets = read_sent_rows(sent_workup)
    assert {"Price Sheet 1", "ADD ALT", "DEDUCT ALT"} <= set(sheets)
    first = sheets["Price Sheet 1"][0]
    assert (first.row, squash(first.text), first.hours) == (6, "SCOPE OF WORK – PREWAILING WAGE", 140.0)
    ups = next(r for r in sheets["Price Sheet 1"] if strip_list_marker(r.text) == "Furnish and Install UPS")
    assert (ups.row, ups.quantity, ups.unit_price) == (28, 1, 350.0)
    router = next(r for r in sheets["Price Sheet 1"] if "BACnet IP Router" in r.text)
    assert (router.quantity, router.unit_price) == (7, None)
    assert [strip_list_marker(r.text) for r in sheets["ADD ALT"]][:3] == [
        "ADD ALTERNATES:", "ALT 1: Controls As per Sequence of operation 15985 – 18",
        "*Qty (1) Can Wash Kitchen Exhaust Fan EF-9"]


def test_align_pairs_rows_in_order():
    assert align(["a", "b", "c"], ["x", "a", "c"]) == [(0, 1), (2, 2)]


def test_align_ignores_markers_spacing_and_case():
    assert align(["o  Furnish UPS", "44.  *Qty (1) EF-9"], ["o\xa0\xa0 furnish ups", "45.\xa0\xa0 *qty (1) ef-9 "]) == [(0, 0), (1, 1)]
```

- [ ] **Step 2: Run to see it fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_price_rows.py -v`
Expected: collection error — `ModuleNotFoundError: No module named 'estimator.price_sheet.rows'`.

- [ ] **Step 3: Write `src/estimator/price_sheet/rows.py`**

```python
"""The price sheet as rows: what the tool writes, what a sent workup holds, and how to line them up.

The rows are the proposal's own lines, in the proposal's order — the same list
the proposal is written from (the one-list, two-documents guarantee).
"""
from __future__ import annotations

import difflib
from dataclasses import dataclass
from pathlib import Path

import openpyxl

from estimator.proposal import layout
from estimator.scope import Block, Item, Job
from estimator.text import squash, strip_list_marker

FIRST_ROW, LAST_ROW = 6, 396                               # the rows that hold Material Total = Unit Price × Quantity
HOURS, QUANTITY, SCOPE, UNIT_PRICE, FLAG = 2, 3, 4, 5, 8   # columns B, C, D, E, H


@dataclass(frozen=True)
class Row:
    text: str = ""                   # column D; empty for a blank spacer row
    hours: float | None = None       # column B
    quantity: int | None = None      # column C
    item: Item | None = None         # set for a line or note
    ref: tuple = ()                  # where in Job.model_dump() this row came from


@dataclass(frozen=True)
class Sheet:
    title: str
    rows: tuple[Row, ...]


def sheet_plan(job: Job) -> list[Sheet]:
    """Every price sheet the job needs, in workbook order: the base bid, then each alternate."""
    numbers = iter(range(1, 10_000))
    base = [
        Row(layout.scope_heading(job), hours=job.front_end.tech_hours, ref=("front_end",)),
        Row(f"{layout.FRONT_END_HEADING_MARKER}  {layout.front_end_heading(job.front_end)}"),
    ]
    markers = layout.FRONT_END_LINE_MARKER[job.front_end.mode]
    for j, item in enumerate(job.front_end.items):
        base.append(_item_row(item, markers, ("front_end", "items", j)))
    for i, block in enumerate(job.blocks):
        base += _block_rows(block, next(numbers), ("blocks", i))
    sheets = [Sheet("Price Sheet 1", tuple(base))]
    for field, heading, name in (("add_alternates", layout.ADD_ALTERNATES, "ADD ALT"),
                                 ("deduct_alternates", layout.DEDUCT_ALTERNATES, "DEDUCT ALT")):
        alternates = getattr(job, field)
        for k, alternate in enumerate(alternates):
            rows = [Row(heading), Row(), Row(f"{k + 1}.  {alternate.label}")]
            for i, block in enumerate(alternate.blocks):
                rows += _block_rows(block, next(numbers), (field, k, "blocks", i))
            title = name if len(alternates) == 1 else f"{name} {k + 1}"
            sheets.append(Sheet(title, tuple(rows)))
    return sheets


def _block_rows(block: Block, number: int, ref: tuple) -> list[Row]:
    rows = [Row(), Row(f"{number}.  {squash(block.header)}", hours=block.tech_hours, ref=ref)]
    for j, item in enumerate(block.items):
        rows.append(_item_row(item, layout.BLOCK_LINE_MARKER, ref + ("items", j)))
    return rows


def _item_row(item: Item, markers: dict[int, str], ref: tuple) -> Row:
    text = squash(item.text) if item.kind == "note" else f"{markers[item.depth]}  {squash(item.text)}"
    return Row(text, quantity=item.quantity, item=item, ref=ref)


@dataclass(frozen=True)
class SentRow:
    sheet: str
    row: int
    text: str
    hours: float | None
    quantity: int | None
    unit_price: float | None


def _number(value) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _whole(value) -> int | None:
    number = _number(value)
    return int(number) if number is not None and number.is_integer() else None


def read_sent_rows(path: Path) -> dict[str, list[SentRow]]:
    """Every price sheet's scope rows, as written — markers, odd spacing and all."""
    workbook = openpyxl.load_workbook(str(path), data_only=True)
    sheets: dict[str, list[SentRow]] = {}
    for ws in workbook.worksheets:
        if ws.title == "Summary":
            continue
        rows = []
        for r in range(FIRST_ROW, LAST_ROW + 1):
            text = ws.cell(r, SCOPE).value
            if isinstance(text, str) and text.strip():
                rows.append(SentRow(ws.title, r, text, _number(ws.cell(r, HOURS).value),
                                    _whole(ws.cell(r, QUANTITY).value), _number(ws.cell(r, UNIT_PRICE).value)))
        sheets[ws.title] = rows
    return sheets


def _key(text: str) -> str:
    return strip_list_marker(text).casefold()


def align(ours: list[str], theirs: list[str]) -> list[tuple[int, int]]:
    """Pairs (our index, their index) of rows that say the same thing, in order."""
    matcher = difflib.SequenceMatcher(None, [_key(t) for t in ours], [_key(t) for t in theirs], autojunk=False)
    return [(block.a + k, block.b + k) for block in matcher.get_matching_blocks() for k in range(block.size)]
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_price_rows.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: the price sheet as the proposal's own rows, and reading a sent workup

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: Writing the price sheet

**Files:**
- Create: `src/estimator/price_sheet/write.py`, `tests/test_write_price_sheet.py`

**Interfaces:**
- Consumes: `sheet_plan`, `read_sent_rows`, row/column constants (Task 10); `PriceBook` (Task 9); `write_proposal`, `scope_texts` (Task 8).
- Produces:
  - `PRICE_PENDING = "PRICE PENDING"`, `PRICE_NEEDS_REVIEW = "PRICE NEEDS REVIEW"`, `BASE_LABEL = "Base Bid"`, `PriceSheetError(ValueError)`
  - `write_price_sheet(job, template_path, book, out_path) -> Path`

- [ ] **Step 1: Write the failing tests**

`tests/test_write_price_sheet.py`:
```python
import re
import zipfile

import openpyxl
import pytest

from estimator.price_sheet.rows import read_sent_rows
from estimator.price_sheet.write import PRICE_NEEDS_REVIEW, PRICE_PENDING, PriceSheetError, write_price_sheet
from estimator.proposal import layout
from estimator.proposal.sections import scope_texts
from estimator.proposal.write import write_proposal
from estimator.text import strip_list_marker


@pytest.fixture
def written(small_job, workup_template, price_book, tmp_path):
    out = write_price_sheet(small_job, workup_template, price_book, tmp_path / "sheet.xlsx")
    return out, openpyxl.load_workbook(str(out))


def _formulas(workbook, rename=None):
    rename = rename or {}
    return {(rename.get(ws.title, ws.title), c.coordinate): c.value
            for ws in workbook.worksheets for row in ws.iter_rows() for c in row
            if isinstance(c.value, str) and c.value.startswith("=")}


def test_rows_land_in_order(written):
    ws = written[1]["Price Sheet 1"]
    assert (ws["D6"].value, ws["B6"].value) == ("SCOPE OF WORK – PREVAILING WAGE", 40)
    assert ws["D7"].value == "•  Front End Web Enabled BMS System"
    assert (ws["D12"].value, ws["B12"].value) == ("1.  Qty (2) Exhaust Fan EF-1, 2", 8)
    assert (ws["D13"].value, ws["C13"].value) == ("o  Furnish and Install DDC Controller", 2)
    assert ws["D11"].value is None                     # the blank line before a block


def test_prices_come_from_the_price_book(written):
    ws = written[1]["Price Sheet 1"]
    assert (ws["E9"].value, ws["H9"].value) == (2500, None)      # Furnish BMS Server
    assert (ws["E18"].value, ws["H18"].value) == (142, None)     # Space Temperature Sensor
    assert (ws["E20"].value, ws["H20"].value) == (None, None)    # no quantity, so not priced


def test_a_line_the_book_cannot_price_is_price_pending(written):
    ws = written[1]["Price Sheet 1"]
    assert (ws["E8"].value, ws["H8"].value) == (None, PRICE_PENDING)     # Network Level Control Panel
    assert (ws["E13"].value, ws["H13"].value) == (None, PRICE_PENDING)   # DDC Controller


def test_a_price_the_book_itself_questions_is_marked(written):
    ws = written[1]["Price Sheet 1"]
    assert (ws["E19"].value, ws["H19"].value) == (50, PRICE_NEEDS_REVIEW)  # Filter DP Switch


def test_the_summary_says_how_many_lines_have_no_price(written):
    assert written[1]["Summary"]["B34"].value.startswith("3 lines with a quantity have no price yet")


def test_the_summary_is_filled_and_the_leftover_job_name_is_gone(written, small_job):
    wb = written[1]
    summary = wb["Summary"]
    assert summary["B7"].value == small_job.header.reference
    assert summary["B9"].value == "26-9999"
    assert summary["B15"].value.date() == small_job.header.date
    assert (summary["B21"].value, summary["B22"].value) == ("Base Bid", "ADD ALT")
    leftovers = [c.coordinate for ws in wb.worksheets for row in ws.iter_rows() for c in row
                 if isinstance(c.value, str) and "MCCC LA" in c.value]
    assert leftovers == []


def test_an_alternate_sheet_is_renamed_and_the_summary_follows(written):
    wb = written[1]
    assert "ADD ALT" in wb.sheetnames and "Price Sheet 2" not in wb.sheetnames
    assert wb["Summary"]["C22"].value == "='ADD ALT'!B401"


def test_every_template_formula_survives(written, workup_template):
    before = _formulas(openpyxl.load_workbook(str(workup_template)), {"Price Sheet 2": "ADD ALT"})
    expected = {key: value.replace("'Price Sheet 2'!", "'ADD ALT'!") for key, value in before.items()}
    assert len(expected) == 4199
    assert _formulas(written[1]) == expected


def test_no_formula_points_at_a_sheet_that_does_not_exist(written):
    wb = written[1]
    named = {name for formula in _formulas(wb).values() for name in re.findall(r"'([^']+)'!", formula)}
    assert named <= set(wb.sheetnames)


def test_the_logo_is_kept(written):
    assert "xl/media/image1.png" in zipfile.ZipFile(written[0]).namelist()


def test_excel_recalculates_when_the_file_opens(written):
    assert written[1].calculation.fullCalcOnLoad is True


def test_a_job_too_long_for_one_sheet_is_refused(small_job, workup_template, price_book, tmp_path):
    long_job = small_job.model_copy(update={"blocks": tuple(small_job.blocks[0] for _ in range(100))})
    with pytest.raises(PriceSheetError, match="rows"):
        write_price_sheet(long_job, workup_template, price_book, tmp_path / "long.xlsx")


def test_the_price_sheet_is_the_proposal_row_for_row(small_job, proposal_template, workup_template, price_book, tmp_path):
    proposal = write_proposal(small_job, proposal_template, tmp_path / "p.docx")
    sheet = write_price_sheet(small_job, workup_template, price_book, tmp_path / "s.xlsx")
    rows = read_sent_rows(sheet)
    in_sheet = [strip_list_marker(r.text) for title in ("Price Sheet 1", "ADD ALT") for r in rows[title]]
    in_proposal = scope_texts(proposal)
    in_proposal = in_proposal[: in_proposal.index(layout.DEDUCT_ALTERNATES)]   # small_job has no deduct alternates
    assert in_sheet == in_proposal
```

- [ ] **Step 2: Run to see it fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_write_price_sheet.py -v`
Expected: collection error — `ModuleNotFoundError: No module named 'estimator.price_sheet.write'`.

- [ ] **Step 3: Write `src/estimator/price_sheet/write.py`**

```python
"""Fill the AME price workup template from a Job.

The template's own formulas do all the arithmetic — material total, labour,
project management, engineering, tax, markup, sell price. The tool types only
into the input columns (hours, quantity, scope, unit price) and never touches a
formula cell. A line the price book can't price is left without a price and
marked PRICE PENDING, and the Summary says how many there are, so an incomplete
total is never mistaken for a complete one.
"""
from __future__ import annotations

from pathlib import Path

import openpyxl
from openpyxl.styles import Font

from estimator.price_sheet.price_book import PriceBook
from estimator.price_sheet.rows import FIRST_ROW, FLAG, HOURS, LAST_ROW, QUANTITY, SCOPE, UNIT_PRICE, Sheet, sheet_plan
from estimator.scope import Job

PRICE_PENDING = "PRICE PENDING"
PRICE_NEEDS_REVIEW = "PRICE NEEDS REVIEW"   # the price book's own note questions this price
BASE_LABEL = "Base Bid"
MAX_SHEETS = 10
_FLAG_FONT = Font(bold=True, color="C00000")


class PriceSheetError(ValueError):
    """The job doesn't fit the price workup template."""


def write_price_sheet(job: Job, template_path: Path, book: PriceBook, out_path: Path) -> Path:
    workbook = openpyxl.load_workbook(str(template_path))    # formulas kept as formulas
    plan = sheet_plan(job)
    if len(plan) > MAX_SHEETS:
        raise PriceSheetError(f"the job needs {len(plan)} price sheets; the template has {MAX_SHEETS}")
    pending = 0
    for index, sheet in enumerate(plan):
        template_title = f"Price Sheet {index + 1}"
        if sheet.title != template_title:
            _rename_sheet(workbook, template_title, sheet.title)
        pending += _fill(workbook[sheet.title], sheet, book)
    _fill_summary(workbook["Summary"], job, plan, pending)
    workbook.calculation.fullCalcOnLoad = True
    out_path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(str(out_path))
    return out_path


def _fill(ws, sheet: Sheet, book: PriceBook) -> int:
    room = LAST_ROW - FIRST_ROW + 1
    if len(sheet.rows) > room:
        raise PriceSheetError(f"{sheet.title} needs {len(sheet.rows)} rows; the template has room for {room}")
    pending = 0
    for offset, row in enumerate(sheet.rows):
        r = FIRST_ROW + offset
        if row.text:
            ws.cell(r, SCOPE).value = row.text
        if row.hours is not None:
            ws.cell(r, HOURS).value = row.hours
        if row.quantity is not None:
            ws.cell(r, QUANTITY).value = row.quantity
            match = book.lookup(row.item.text)
            if match is None:
                _flag(ws, r, PRICE_PENDING)
                pending += 1
            else:
                ws.cell(r, UNIT_PRICE).value = match.price
                if match.needs_review:
                    _flag(ws, r, PRICE_NEEDS_REVIEW)
    return pending


def _flag(ws, row: int, text: str) -> None:
    cell = ws.cell(row, FLAG)
    cell.value = text
    cell.font = _FLAG_FONT


def _rename_sheet(workbook, old: str, new: str) -> None:
    """Rename a sheet and every reference to it. openpyxl, unlike Excel, doesn't follow a rename."""
    workbook[old].title = new
    old_ref, new_ref = f"'{old}'!", f"'{new}'!"
    for ws in workbook.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and cell.value.startswith("=") and old_ref in cell.value:
                    cell.value = cell.value.replace(old_ref, new_ref)
    names = list(workbook.defined_names.values())
    for ws in workbook.worksheets:
        names += list(ws.defined_names.values())
    for defined in names:
        if defined.attr_text and old_ref in defined.attr_text:
            defined.attr_text = defined.attr_text.replace(old_ref, new_ref)


def _fill_summary(ws, job: Job, plan: list[Sheet], pending: int) -> None:
    ws["B7"] = job.header.reference
    ws["B9"] = job.header.quote_number
    ws["B15"] = job.header.date
    for index, sheet in enumerate(plan):
        ws.cell(21 + index, 2).value = BASE_LABEL if index == 0 else sheet.title
    if pending:
        lines, have = ("line", "has") if pending == 1 else ("lines", "have")
        cell = ws["B34"]
        cell.value = (f"{pending} {lines} with a quantity {have} no price yet — marked {PRICE_PENDING} "
                      f"in column H of the price sheets. The totals above leave them out.")
        cell.font = _FLAG_FONT
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_write_price_sheet.py -v`
Expected: 13 passed.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: fill the price workup — every formula and the logo kept, unpriced lines marked

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12: The test job, made from what was sent for 26-0246

**Files:**
- Create: `src/estimator/sent.py`, `src/estimator/__main__.py`, `tests/test_sent.py`, `tests/data/26-0246/job.json` (generated)
- Modify: `tests/conftest.py` (add `test_job`)

**Interfaces:**
- Consumes: `read_proposal` (Task 6); `sheet_plan`, `read_sent_rows`, `align` (Task 10).
- Produces:
  - `ImportReport(matched: int, unmatched_ours: tuple[str, ...], unmatched_theirs: tuple[str, ...])`
  - `job_from_sent(proposal: Path, workup: Path, template: Path) -> tuple[Job, ImportReport]` — hours onto the front end and blocks, quantities onto lines only.
  - `python -m estimator import-sent PROPOSAL WORKUP --out JOB.json [--template DOCX]`
  - `python -m estimator build JOB.json --out FOLDER [--template DOCX] [--workup-template XLSX]`
  - Fixture: `test_job` — the `Job` in `tests/data/26-0246/job.json`.

- [ ] **Step 1: Write the failing tests**

`tests/test_sent.py`:
```python
from conftest import PROPOSAL_TEMPLATE, SENT_PROPOSAL, SENT_WORKUP, TEST_JOB_FILE
from estimator.scope import Job
from estimator.sent import job_from_sent


def _imported():
    return job_from_sent(SENT_PROPOSAL, SENT_WORKUP, PROPOSAL_TEMPLATE)


def test_hours_come_from_the_workup():
    job, _ = _imported()
    assert job.front_end.tech_hours == 140.0
    assert (job.blocks[0].header, job.blocks[0].tech_hours) == ("*Qty (1) BACnet Data Cabinet", 10.0)
    assert job.blocks[1].tech_hours == 25.0


def test_quantities_come_from_the_workup():
    job, _ = _imported()
    assert [i.quantity for i in job.front_end.items] == [1, 1, 1, 1, 1, 1, None, None, None, None, None, None]
    assert [i.quantity for i in job.blocks[0].items] == [1, 1, 1, None, None, None, None, None]
    router_cabinet = job.blocks[1].items
    assert (router_cabinet[0].quantity, router_cabinet[1].quantity) == (5, 7)
    assert router_cabinet[1].text.startswith("Furnish and Install BACnet IP Router")


def test_alternates_get_their_hours_and_quantities():
    job, _ = _imported()
    add, deduct = job.add_alternates[0].blocks[0], job.deduct_alternates[0].blocks[0]
    assert (add.tech_hours, [i.quantity for i in add.items]) == (4.0, [1, 1])
    assert (deduct.tech_hours, [i.quantity for i in deduct.items]) == (4.0, [1, 1, None])


def test_most_lines_match_between_the_proposal_and_the_workup():
    # The exact figure is printed in Step 5. The sent workup was made from an earlier
    # draft of the proposal, so a handful of lines are expected not to match.
    _, report = _imported()
    assert report.matched >= 200


def test_the_committed_test_job_is_what_the_importer_makes():
    assert Job.model_validate_json(TEST_JOB_FILE.read_text(encoding="utf-8")) == _imported()[0]
```

Add to `tests/conftest.py` (`Job` is already imported there from Task 2):
```python
@pytest.fixture(scope="session")
def test_job():
    return Job.model_validate_json(TEST_JOB_FILE.read_text(encoding="utf-8"))
```

- [ ] **Step 2: Run to see it fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_sent.py -v`
Expected: collection error — `ModuleNotFoundError: No module named 'estimator.sent'`.

- [ ] **Step 3: Write `src/estimator/sent.py`**

```python
"""Turn what was actually sent for a past job — its proposal and its price workup — into a Job.

The proposal gives the scope. The workup gives the tech hours on each block and
the quantity on each line. The two are matched row by row, because the workup
is the proposal pasted into Excel.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from estimator.price_sheet.rows import align, read_sent_rows, sheet_plan
from estimator.proposal.read import read_proposal
from estimator.scope import Job


@dataclass(frozen=True)
class ImportReport:
    matched: int
    unmatched_ours: tuple[str, ...]      # proposal lines with no workup row: no hours or quantity taken
    unmatched_theirs: tuple[str, ...]    # workup rows that match nothing in the proposal: ignored


def job_from_sent(proposal: Path, workup: Path, template: Path) -> tuple[Job, ImportReport]:
    job = read_proposal(proposal, template)
    sent = read_sent_rows(workup)
    data = job.model_dump()
    matched, lost_ours, lost_theirs = 0, [], []
    for sheet in sheet_plan(job):
        ours = [row for row in sheet.rows if row.text]
        theirs = sent.get(sheet.title, [])
        pairs = align([row.text for row in ours], [row.text for row in theirs])
        matched += len(pairs)
        for a, b in pairs:
            row, found = ours[a], theirs[b]
            if not row.ref:
                continue
            target = _at(data, row.ref)
            if row.item is None:
                if found.hours is not None:
                    target["tech_hours"] = found.hours
            elif row.item.kind == "line" and found.quantity is not None:
                target["quantity"] = found.quantity
        paired_ours = {a for a, _ in pairs}
        paired_theirs = {b for _, b in pairs}
        lost_ours += [ours[a].text for a in range(len(ours)) if a not in paired_ours]
        lost_theirs += [theirs[b].text for b in range(len(theirs)) if b not in paired_theirs]
    return Job.model_validate(data), ImportReport(matched, tuple(lost_ours), tuple(lost_theirs))


def _at(data: dict, ref: tuple) -> dict:
    node = data
    for step in ref:
        node = node[step]
    return node
```

- [ ] **Step 4: Write `src/estimator/__main__.py`**

```python
"""Command line.

    python -m estimator build JOB.json --out FOLDER
    python -m estimator import-sent PROPOSAL.docx WORKUP.xlsx --out JOB.json
    python -m estimator price-check GENERATED.xlsx SENT.xlsx --out REPORT.md
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from estimator.price_sheet.price_book import PriceBook
from estimator.price_sheet.write import write_price_sheet
from estimator.proposal.write import write_proposal
from estimator.scope import Job
from estimator.sent import job_from_sent

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "assets"
PROPOSAL_TEMPLATE = ASSETS / "templates" / "AME_nordomatic Proposal Template.docx"
WORKUP_TEMPLATE = ASSETS / "templates" / "PriceWorkup_Template - 12-21-25.xlsx"
PRICE_BOOK = ASSETS / "price_book" / "AME Std Pricing Spreadsheet.xlsx"
ALIASES = ASSETS / "price_book" / "aliases.json"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="estimator")
    commands = parser.add_subparsers(dest="command", required=True)

    build = commands.add_parser("build", help="write the proposal and price sheet for a job")
    build.add_argument("job", type=Path)
    build.add_argument("--out", type=Path, required=True)
    build.add_argument("--template", type=Path, default=PROPOSAL_TEMPLATE)
    build.add_argument("--workup-template", type=Path, default=WORKUP_TEMPLATE)

    importer = commands.add_parser("import-sent", help="turn a sent proposal and its workup into a job file")
    importer.add_argument("proposal", type=Path)
    importer.add_argument("workup", type=Path)
    importer.add_argument("--out", type=Path, required=True)
    importer.add_argument("--template", type=Path, default=PROPOSAL_TEMPLATE)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "build":
        job = Job.model_validate_json(args.job.read_text(encoding="utf-8"))
        book = PriceBook.load(PRICE_BOOK, ALIASES)
        quote = job.header.quote_number
        proposal = write_proposal(job, args.template, args.out / f"{quote} Proposal.docx")
        sheet = write_price_sheet(job, args.workup_template, book, args.out / f"{quote} Price Sheet.xlsx")
        print(f"Wrote {proposal}")
        print(f"Wrote {sheet}")
    elif args.command == "import-sent":
        job, report = job_from_sent(args.proposal, args.workup, args.template)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(job.model_dump_json(indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {args.out} — {report.matched} lines matched between the proposal and the workup.")
        if report.unmatched_ours:
            print("In the proposal but not the workup, so no hours or quantity were taken:")
            for text in report.unmatched_ours:
                print(f"    {text}")
        if report.unmatched_theirs:
            print("In the workup but not the proposal, so ignored:")
            for text in report.unmatched_theirs:
                print(f"    {text}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Generate the test job and read the report**

```bash
.venv/Scripts/python.exe -m estimator import-sent tests/data/26-0246/sent-proposal.docx tests/data/26-0246/sent-workup.xlsx --out tests/data/26-0246/job.json
```
Expected: `Wrote tests/data/26-0246/job.json — NNN lines matched…` followed by the unmatched lists. **Copy the whole printed output into your task report** — it shows which block the sent workup was missing, which the estimator will want to see.

- [ ] **Step 6: Run the tests to see them pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_sent.py -v`
Expected: 5 passed.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat: the 26-0246 test job — scope from the sent proposal, hours and quantities from its workup

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 13: The price check report, and the end-to-end test on 26-0246

**Files:**
- Create: `src/estimator/price_sheet/check.py`, `tests/test_price_check.py`, `tests/test_end_to_end.py`
- Modify: `src/estimator/__main__.py` (add `price-check`)

**Interfaces:**
- Consumes: `read_sent_rows`, `align` (Task 10); `PriceBook` (Task 9); both writers; `sections` (Task 8); `main` (Task 12).
- Produces:
  - `price_check(generated: Path, sent: Path, book: PriceBook, title: str) -> str` — a Markdown report in plain language.
  - `python -m estimator price-check GENERATED.xlsx SENT.xlsx --out REPORT.md`

- [ ] **Step 1: Write the failing tests**

`tests/test_price_check.py`:
```python
from estimator.price_sheet.check import price_check
from estimator.price_sheet.write import write_price_sheet


def test_price_check_on_26_0246(test_job, workup_template, price_book, sent_workup, tmp_path):
    sheet = write_price_sheet(test_job, workup_template, price_book, tmp_path / "26-0246 Price Sheet.xlsx")
    report = price_check(sheet, sent_workup, price_book, "26-0246")
    assert report.startswith("# Price check — 26-0246")
    assert "| Furnish BMS Server | 1 | $2,500.00 | $2,000.00 |" in report
    assert "| Furnish and Install Space Temperature / CO2 Sensor | 58 | $182.00 | $380.00 |" in report
    assert "## No price book match yet" in report
    assert "BACnet IP Router" in report
```

`tests/test_end_to_end.py`:
```python
import openpyxl

from estimator.__main__ import main
from estimator.price_sheet.rows import read_sent_rows
from estimator.proposal.read import read_proposal
from estimator.proposal.sections import closing_texts, cover_lines, opening_texts, scope_texts
from estimator.text import strip_list_marker


def _build(tmp_path):
    main(["build", "tests/data/26-0246/job.json", "--out", str(tmp_path)])
    return tmp_path / "26-0246 Proposal.docx", tmp_path / "26-0246 Price Sheet.xlsx"


def test_the_proposal_matches_what_was_sent(tmp_path, sent_proposal, proposal_template, test_job, without_prices):
    proposal, _ = _build(tmp_path)
    assert scope_texts(proposal) == scope_texts(sent_proposal)
    assert closing_texts(proposal) == closing_texts(sent_proposal)
    assert opening_texts(proposal) == opening_texts(sent_proposal)
    assert read_proposal(proposal, proposal_template) == without_prices(test_job)


def test_the_cover_page_differs_only_where_the_sent_copy_left_the_template(tmp_path, sent_proposal):
    proposal, _ = _build(tmp_path)
    ours, sent = cover_lines(proposal), cover_lines(sent_proposal)
    assert len(ours) == len(sent)
    assert [i for i, (a, b) in enumerate(zip(ours, sent)) if a != b] == [2]
    assert (ours[2], sent[2]) == ("Quote #: 26-0246", "Quote: 26-0246")   # the template's label; the sent copy was edited


def test_the_price_sheet_is_the_proposal_row_for_row(tmp_path):
    proposal, sheet = _build(tmp_path)
    rows = read_sent_rows(sheet)
    in_sheet = [strip_list_marker(r.text) for title in ("Price Sheet 1", "ADD ALT", "DEDUCT ALT") for r in rows[title]]
    assert in_sheet == scope_texts(proposal)


def test_hours_and_quantities_reach_the_price_sheet(tmp_path):
    _, sheet = _build(tmp_path)
    ws = openpyxl.load_workbook(str(sheet))["Price Sheet 1"]
    assert (ws["D6"].value, ws["B6"].value) == ("SCOPE OF WORK – PREWAILING WAGE", 140)
    header = next(r for r in range(6, 397) if ws.cell(r, 4).value == "1.  *Qty (1) BACnet Data Cabinet")
    assert ws.cell(header, 2).value == 10
    assert (ws.cell(header + 1, 4).value, ws.cell(header + 1, 3).value) == ("o  Furnish and Install UPS", 1)


def test_the_alternates_are_numbered_as_the_proposal_numbers_them(tmp_path):
    _, sheet = _build(tmp_path)
    wb = openpyxl.load_workbook(str(sheet))
    assert "45.  *Qty (1) Can Wash Kitchen Exhaust Fan EF-9" in [c.value for c in wb["ADD ALT"]["D"]]
    assert "46.  Qty (1) Shower Room Exhaust Fan EF-2" in [c.value for c in wb["DEDUCT ALT"]["D"]]
```

- [ ] **Step 2: Run to see it fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_price_check.py tests/test_end_to_end.py -v`
Expected: `test_price_check.py` fails at collection with `ModuleNotFoundError: No module named 'estimator.price_sheet.check'`; the end-to-end tests should already pass — they prove Tasks 1–12 fit together. If any end-to-end test fails, stop and report it before continuing.

- [ ] **Step 3: Write `src/estimator/price_sheet/check.py`**

```python
"""Compare a generated price sheet with the workup that was actually sent.

Nothing here fails a build. The price book holds the generic price used on most
jobs; a job can use a different price for a line — usually a vendor quote sourced for
that job — so a difference is not an error in the book. The report lists those
differences, and the lines the price book can't price yet, so an estimator can
confirm which price book item each unmatched line means.
"""
from __future__ import annotations

from pathlib import Path

from estimator.price_sheet.price_book import PriceBook
from estimator.price_sheet.rows import align, read_sent_rows
from estimator.text import strip_list_marker


def _money(value: float | None) -> str:
    return "—" if value is None else f"${value:,.2f}"


def price_check(generated: Path, sent: Path, book: PriceBook, title: str) -> str:
    ours_by_sheet, theirs_by_sheet = read_sent_rows(generated), read_sent_rows(sent)
    differs, same, pending, unpriced_sent, questioned = [], 0, [], [], []
    for sheet, ours in ours_by_sheet.items():
        theirs = theirs_by_sheet.get(sheet, [])
        partner = dict(align([r.text for r in ours], [r.text for r in theirs]))
        for index, row in enumerate(ours):
            if row.quantity is None:
                continue
            line = strip_list_marker(row.text)
            sent_price = theirs[partner[index]].unit_price if index in partner else None
            if row.unit_price is None:
                pending.append((line, row.quantity, sent_price, book.closest(line)))
                continue
            match = book.lookup(line)
            if match is not None and match.needs_review:
                questioned.append((line, row.quantity, row.unit_price))
            if sent_price is None:
                unpriced_sent.append((line, row.quantity, row.unit_price))
            elif sent_price == row.unit_price:
                same += 1
            else:
                differs.append((line, row.quantity, row.unit_price, sent_price))

    priced = same + len(differs) + len(unpriced_sent)
    out = [
        f"# Price check — {title}",
        "",
        "This price sheet was priced from the AME price book. Each line that carries a quantity is "
        "compared below with the workup that was sent for this job. The price book holds the generic "
        "price used on most jobs; where the sent workup used a different price, it was usually a vendor "
        "quote sourced for this job — so a difference here is not a mistake in the price book.",
        "",
        "| | Lines |",
        "|---|---|",
        f"| Lines with a quantity | {priced + len(pending)} |",
        f"| Priced from the price book | {priced} |",
        f"| — same price as the sent workup | {same} |",
        f"| — a different price was used for this job | {len(differs)} |",
        f"| — the sent workup had no price | {len(unpriced_sent)} |",
        f"| No price book match yet (PRICE PENDING) | {len(pending)} |",
        "",
        "## The sent workup used a different price",
        "",
        "Usually a vendor quote sourced for this job. The price book stays as it is.",
        "",
        "| Line | Qty | Price book | Sent workup |",
        "|---|---|---|---|",
        *[f"| {line} | {qty} | {_money(book_price)} | {_money(sent_price)} |" for line, qty, book_price, sent_price in differs],
        "",
        "## No price book match yet",
        "",
        "Each of these needs an estimator to say which price book item it is, if any. A confirmed "
        "match goes in `assets/price_book/aliases.json`, and the line is priced from then on.",
        "",
        "| Line | Qty | Sent workup price | Closest price book items |",
        "|---|---|---|---|",
        *[f"| {line} | {qty} | {_money(sent_price)} | {', '.join(i.name for i in near) or '—'} |"
          for line, qty, sent_price, near in pending],
        "",
        "## Priced by the book, but the sent workup had no price",
        "",
        "| Line | Qty | Price book |",
        "|---|---|---|",
        *[f"| {line} | {qty} | {_money(book_price)} |" for line, qty, book_price in unpriced_sent],
        "",
        "## Priced, but the price book itself marks the price as needing review",
        "",
        "| Line | Qty | Price book |",
        "|---|---|---|",
        *[f"| {line} | {qty} | {_money(book_price)} |" for line, qty, book_price in questioned],
        "",
    ]
    return "\n".join(out)
```

- [ ] **Step 4: Add `price-check` to `src/estimator/__main__.py`**

Add the import at the top with the others:
```python
from estimator.price_sheet.check import price_check
```

In `_parser()`, before `return parser`, add:
```python
    check = commands.add_parser("price-check", help="compare a generated price sheet with the workup that was sent")
    check.add_argument("generated", type=Path)
    check.add_argument("sent", type=Path)
    check.add_argument("--out", type=Path, required=True)
```

In `main()`, before `return 0`, add:
```python
    elif args.command == "price-check":
        book = PriceBook.load(PRICE_BOOK, ALIASES)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(price_check(args.generated, args.sent, book, args.generated.stem), encoding="utf-8")
        print(f"Wrote {args.out}")
```

- [ ] **Step 5: Run the tests to see them pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_price_check.py tests/test_end_to_end.py -v`
Expected: 6 passed.

- [ ] **Step 6: Run everything**

Run: `.venv/Scripts/python.exe -m pytest -v`
Expected: all pass. Paste the final summary line into your task report.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat: the price check report, and the end-to-end test on 26-0246

The proposal comes out matching what was sent, line for line; the price sheet
is the proposal row for row, with the alternates numbered 45 and 46 as the
proposal numbers them.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 14: Side by side, by eye — and the estimator's sign-off

**Files:**
- Create: `tools/side_by_side.py`, `tests/test_side_by_side.py`

**Interfaces:**
- Consumes: the command line (Tasks 12–13).
- Produces:
  - `compose(left: Path, right: Path, out: Path) -> Path` — two page images side by side on white, 20 px apart.
  - `python tools/side_by_side.py SENT.docx GENERATED.docx --sheet GENERATED.xlsx --out FOLDER [--workup-template XLSX]` — writes `page-01.png`… (sent on the left, generated on the right) and prints each filled price sheet's recalculated totals. Exits 1 if Excel shows a formula error the empty template doesn't already have (unused price sheets divide by zero in the template itself).

- [ ] **Step 1: Write the failing test for the one part that needs no Word or Excel**

`tests/test_side_by_side.py`:
```python
import importlib.util
from pathlib import Path

from PIL import Image

_spec = importlib.util.spec_from_file_location("side_by_side", Path(__file__).resolve().parents[1] / "tools" / "side_by_side.py")
side_by_side = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(side_by_side)


def test_compose_puts_two_pages_side_by_side(tmp_path):
    Image.new("RGB", (100, 140), "red").save(tmp_path / "a.png")
    Image.new("RGB", (100, 120), "blue").save(tmp_path / "b.png")
    out = side_by_side.compose(tmp_path / "a.png", tmp_path / "b.png", tmp_path / "ab.png")
    image = Image.open(out)
    assert image.size == (220, 140)
    assert image.getpixel((10, 10)) == (255, 0, 0)
    assert image.getpixel((130, 10)) == (0, 0, 255)
    assert image.getpixel((110, 10)) == (255, 255, 255)
```

- [ ] **Step 2: Run to see it fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_side_by_side.py -v`
Expected: FAIL — `FileNotFoundError` for `tools/side_by_side.py`.

- [ ] **Step 3: Write `tools/side_by_side.py`**

```python
"""Put a sent proposal and a generated one side by side, page by page, for checking by eye.

Also opens the generated price sheet in Excel, lets it recalculate, and prints
the totals — proving the template's formulas still work, and catching any
formula that now shows an error.

Needs Microsoft Word and Excel. Windows only.

    .venv/Scripts/python.exe tools/side_by_side.py SENT.docx GENERATED.docx --sheet GENERATED.xlsx --out FOLDER
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

_GAP = 20


def compose(left: Path, right: Path, out: Path) -> Path:
    a, b = Image.open(left).convert("RGB"), Image.open(right).convert("RGB")
    canvas = Image.new("RGB", (a.width + _GAP + b.width, max(a.height, b.height)), "white")
    canvas.paste(a, (0, 0))
    canvas.paste(b, (a.width + _GAP, 0))
    canvas.save(out)
    return out


def _powershell(script: str) -> str:
    done = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                          capture_output=True, text=True, timeout=600)
    if done.returncode != 0:
        raise RuntimeError(done.stderr.strip() or done.stdout.strip())
    return done.stdout


def _to_pdf(documents: list[Path]) -> None:
    pairs = ",".join(f"@('{d}','{d.with_suffix('.pdf')}')" for d in documents)
    _powershell(f"""
$ErrorActionPreference = 'Stop'
$word = New-Object -ComObject Word.Application
$word.Visible = $false; $word.DisplayAlerts = 0
try {{
  foreach ($pair in @({pairs})) {{
    $doc = $word.Documents.Open($pair[0], $false, $true, $false)
    $doc.SaveAs2($pair[1], 17)
    $doc.Close(0)
  }}
}} finally {{ $word.Quit() }}
""")


def _render(pdf: Path, folder: Path, stem: str) -> list[Path]:
    import fitz
    pages = []
    with fitz.open(str(pdf)) as document:
        for number, page in enumerate(document, 1):
            path = folder / f"{stem}-{number:02d}.png"
            page.get_pixmap(dpi=70).save(str(path))
            pages.append(path)
    return pages


def _excel_check(workbooks: list[Path]) -> list[list[dict]]:
    """Open each workbook in Excel, recalculate, and report each sheet's error cells and totals."""
    paths = ",".join(f"'{w}'" for w in workbooks)
    out = _powershell(f"""
$ErrorActionPreference = 'Stop'
$excel = New-Object -ComObject Excel.Application
$excel.Visible = $false; $excel.DisplayAlerts = $false
$all = @()
try {{
  foreach ($path in @({paths})) {{
    $wb = $excel.Workbooks.Open($path, 0, $true)
    $excel.CalculateFull()
    $sheets = @()
    foreach ($ws in $wb.Worksheets) {{
      $errors = ''
      try {{ $errors = $ws.UsedRange.SpecialCells(-4123, 16).Address(0, 0) }} catch {{ }}
      $row = @{{ name = $ws.Name; errors = $errors }}
      if ($ws.Name -ne 'Summary') {{
        $row.hours = $ws.Range('B401').Value2; $row.material = $ws.Range('F401').Value2; $row.sell = $ws.Range('E436').Value2
      }}
      $sheets += $row
    }}
    $wb.Close($false)
    $all += ,$sheets
  }}
}} finally {{ $excel.Quit() }}
ConvertTo-Json -InputObject $all -Depth 4
""")
    return json.loads(out)


def _cells(address: str) -> set[str]:
    """Expand an Excel address like "E437,L24:L30" into single cells."""
    from openpyxl.utils import get_column_letter, range_boundaries
    cells = set()
    for area in filter(None, (address or "").split(",")):
        min_col, min_row, max_col, max_row = range_boundaries(area)
        for col in range(min_col, max_col + 1):
            for row in range(min_row, max_row + 1):
                cells.add(f"{get_column_letter(col)}{row}")
    return cells


_WORKUP_TEMPLATE = Path(__file__).resolve().parents[1] / "assets" / "templates" / "PriceWorkup_Template - 12-21-25.xlsx"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("sent", type=Path)
    parser.add_argument("generated", type=Path)
    parser.add_argument("--sheet", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workup-template", type=Path, default=_WORKUP_TEMPLATE)
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)

    work = Path(tempfile.mkdtemp(prefix="estimator-"))
    sent, generated = work / "sent.docx", work / "generated.docx"
    shutil.copy2(args.sent, sent)
    shutil.copy2(args.generated, generated)
    _to_pdf([sent, generated])
    left, right = _render(sent.with_suffix(".pdf"), work, "sent"), _render(generated.with_suffix(".pdf"), work, "generated")
    blank = work / "blank.png"
    Image.new("RGB", Image.open(left[0]).size, "white").save(blank)
    for number in range(max(len(left), len(right))):
        compose(left[number] if number < len(left) else blank,
                right[number] if number < len(right) else blank,
                args.out / f"page-{number + 1:02d}.png")
    print(f"{max(len(left), len(right))} pages written to {args.out} — sent on the left, generated on the right.")
    print(f"The sent proposal has {len(left)} pages; the generated one has {len(right)}.")
    print("The sent proposal's cover shows today's date: its date field updates whenever Word opens it. "
          "The generated one shows the date it was issued.")

    # Unused price sheets divide by zero in the template's own margin formulas, so compare
    # with the empty template and report only errors the template did not already have.
    template, sheet = work / "template.xlsx", work / "sheet.xlsx"
    shutil.copy2(args.workup_template, template)
    shutil.copy2(args.sheet, sheet)
    before, after = _excel_check([template, sheet])
    new_errors = []
    for empty, filled in zip(before, after):
        fresh = sorted(_cells(filled["errors"]) - _cells(empty["errors"]))
        if fresh:
            new_errors.append(f"{filled['name']}: {', '.join(fresh)}")
    for row in after:
        if row["name"] != "Summary" and row.get("hours"):
            print(f"{row['name']}: {row['hours']:g} tech hours, material ${row['material']:,.2f}, "
                  f"sell price ${row['sell']:,.2f}")
    if new_errors:
        print("Excel shows formula errors the empty template doesn't have:")
        for line in new_errors:
            print(f"    {line}")
        return 1
    print("Excel recalculated every formula, and none shows an error the template doesn't already have.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the test to see it pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_side_by_side.py -v`
Expected: 1 passed.

- [ ] **Step 5: Produce everything for 26-0246**

```bash
.venv/Scripts/python.exe -m estimator build tests/data/26-0246/job.json --out out/26-0246
.venv/Scripts/python.exe -m estimator price-check "out/26-0246/26-0246 Price Sheet.xlsx" tests/data/26-0246/sent-workup.xlsx --out "out/26-0246/26-0246 price check.md"
.venv/Scripts/python.exe tools/side_by_side.py tests/data/26-0246/sent-proposal.docx "out/26-0246/26-0246 Proposal.docx" --sheet "out/26-0246/26-0246 Price Sheet.xlsx" --out out/26-0246/side-by-side
```
Expected: two `Wrote …` lines; `Wrote …price check.md`; the page count and each filled price sheet's hours, material and sell price; and `Excel recalculated every formula, and none shows an error the template doesn't already have.` Paste all of it into your task report.

- [ ] **Step 6: Run everything one last time**

Run: `.venv/Scripts/python.exe -m pytest -v`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat: side-by-side pages and an Excel recalculation check, for review by eye

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 8: Stop — the estimator signs this off, not the tests**

Hand the estimator, in plain words:
- the side-by-side pages in `out/26-0246/side-by-side/` — the sent proposal on the left, the generated one on the right;
- `out/26-0246/26-0246 Proposal.docx` and `out/26-0246/26-0246 Price Sheet.xlsx`, to open in Word and Excel;
- `out/26-0246/26-0246 price check.md`;
- the import report from Task 12 (which block the sent workup was missing).

Ask whether the proposal reads as theirs, and whether any kind of line should look different. A change of look is one edit in `src/estimator/proposal/layout.py`. Build step 1 is done when they say so.
