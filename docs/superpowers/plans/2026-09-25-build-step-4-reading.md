# Build Step 4 — Read the Job — Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development. Tasks 1–5 are independent: each adds only its own new files, and they run in parallel, each in its own worktree. Task 6 wires them in, after all five are merged.

**Goal:** Read the job the way the estimator does:
- the equipment list from the schedules, checked against the other sheets by the estimator's quantity rules
- the devices marked on the plans
- the keynotes that add controls scope
- typical floors
- the latest date wins for reissued sheets, with every change logged
- where the sequence of operation and points list sit (the backbone of step 5)

Every result goes into the Evidence Package with its source.

**Spec:** `docs/superpowers/specs/2026-09-24-estimator-ai-design.md` §9.2–§9.8 and §5 (core type).
**Estimator's rules:** `D:\Estimation Assistant\Brain\Quantity rules.txt` (read-only). A summary is in "Rules" below.

**Research (measured on the Learn jobs, 2026-09-25):**
- **Schedules:** `page.find_tables()` finds each schedule as its own table.
  - One extra table spans the whole sheet (its border). Drop it.
  - A schedule has **no QTY column**. It lists one row per unit, so quantity = the number of distinct tags. The tag column is headed UNIT No., TAG, MARK or DESIGNATION.
  - On 26-0246 (58 VAV, 19 CAV), 26-0339 (41 WSHP) and 26-0352 (12 VAV, 1 EF) the counts match the issued proposal exactly.
  - The notes under a schedule say who provides the unit controller: "Digital control shall be furnished by Temperature Control Contractor", "Provide all units with factory control package", "coordinate with ATC vendor".
- **Plans:** devices are short text labels next to a drawn symbol (T, TS, CO2, OCC, H, SP, DP, FM, FS, TB, DWM, H2).
  - On 26-0352 M-200.00, `get_text("words")` gives "T" ×13 and "OCC" ×20. The estimator counted T 12 and OCC 21. The one extra T is the legend's own "T".
  - Keynote numbers on these jobs are bare digits with **no enclosing shape**. Bare digits are everywhere (dimensions, grid bubbles), so a placement count isn't reliable. The keynote *list* ("KEY NOTES:", "GENERAL NOTES A.–Q.") is readable.
  - Legends (M002.00, M00-01) pair a short code with its description in the same row band.
  - Typical floors are in titles: "MECHANICAL 10TH-16TH ERV LEVEL FLOOR PLAN TYPICAL" (26-0344). The same sheet is repeated on one PDF page per floor, with identical text.
- **Revisions:** no Learn job has an addendum.
  - Archive addenda name their sheets in three ways: a narrative by sheet number, item lists, or a whole reissued set with no list.
  - **The title block's revision table is the reliable signal**, for example `4  ADDENDUM #1  02 26 25`, following `3  ISSUED FOR BID  02 12 25`.
  - A flat word diff is noisy; diff by region instead (tags, schedule rows, note lines).
  - Revision-cloud arcs are confused with watermarks, so they are not used.
- **Sequences and point lists:** in spec sections (23 09 93 "SEQUENCE OF OPERATIONS", 15985, 25 xx) and/or on drawing sheets titled "SEQUENCE OF OPERATIONS" or "POINTS LIST" (26-0437 M-805 and M-809; 26-0445 IC04-01 to 04).
  - Spec text is sometimes carried twice (26-0356). Remove the repeat.
  - Some jobs have none (26-0352 is lighting-controls only). Say so.

## Global Constraints

- `D:\AME Estimation` and `D:\Estimation Assistant` are read-only.
- No job PDFs in the repo. Tests build synthetic PDFs with `tests/pdfs.py` (read it; it draws text and lines with pymupdf), or build `PageRecord` / `Sheet` / `SpecSection` objects directly.
- Recall is deterministic (design §9.1). **Never invent a number:** a count that can't be read is `None` and flagged "PENDING", never a silent 1.
- Every piece of text the user sees is plain English. The category words CONFIRMED, DISCREPANCY, EXTRA, MISSING, ORPHANED, CONFLICT, EXISTING, TYPE ONLY and PENDING are the estimator's own words from Quantity rules.txt, so use them. Each row also gives a plain-words reason.
- Patterns and vocabularies live in JSON under `assets/reading_lists/`, never in code.
- Run text through `clean_text` (`estimator.catalogue.pdf`) before matching.
- Python 3.13, `.venv/Scripts/python.exe`, pymupdf 1.28.2. No new packages.
- Don't touch the bid check (`qualify.py`, `manufacturers.json`).
- Don't push. End commit messages with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Don't spend time tuning on old jobs.** Run each task's module once over the Learn jobs as a smoke test: no crash, sensible totals. Report one line per job. Tuning comes later.

## Shared inputs (exist already; read, don't change)

- `estimator.catalogue.job.catalogue_job(root, cache_dir) -> Catalogue`, with fields:
  - `.pages`: `PageRecord` (document, page, status, text, rotation, large_sheet, edge_spans, read_error)
  - `.sheets`: `Sheet` (document, page, number, title, discipline, types)
  - `.sections`: `SpecSection` (number, title, document, first_page, last_page, `.controls`)
  - `.tags`: `TagEntry` (tag, kind, on_schedules, elsewhere, times)
  - `.job.documents`: `Document` (relative, path, kind, revision, duplicate_of, …)
- Opening a page for layout: `pymupdf.open(document.path)[page - 1]`. Tasks that need words or tables open the PDF themselves. They take a `page_opener: Callable[[str, int], pymupdf.Page]` so tests can pass synthetic pages.
- Tags: `estimator.catalogue.tags.find_tags(text, Equipment.load())` and `assets/reading_lists/equipment.json` (prefix → equipment kind).
- Smoke test: `from estimator.catalogue.job import catalogue_job; catalogue_job(Path(r"D:\Estimation Assistant\Learn\26-0352"), Path("out/learn/.cache"))`. It's cached, so it's fast. Job folders: 26-0246, 26-0328, 26-0334, 26-0339, 26-0344 (folder name has a suffix, so glob `26-0344*`), 26-0352*, 26-0356*, 26-0436*, and 26-0445. 26-0437 is nested inside 26-0436.

## Rules (from Quantity rules.txt, which you should read in full)

1. The schedule is the source of quantities. Other sheets verify it; they never change the count silently.
2. Check the schedule against every sheet type present: plans, risers, control diagrams.
3. Every item lands in exactly one category:
   - CONFIRMED
   - DISCREPANCY
   - EXTRA (on a sheet, not in the schedule)
   - MISSING (in the schedule, on no other sheet)
   - ORPHANED (appears once, nowhere else)
   - CONFLICT
   - EXISTING (existing, removal or reuse; not new work)
4. A flag states the equipment type, the source sheet, the category and the action (confirm, include pending, or exclude pending).
5. Nothing is left unclassified.
6. Never price an EXTRA or ORPHANED item without confirmation.
7. The same tag twice on a schedule → DISCREPANCY. Never collapse it to 1 or double it silently.
8. A type-only schedule (types or sizes, no tags) → count on the plans. With no count anywhere → PENDING.
9. Paired systems (split indoor and outdoor units, CRAC with its condensing unit): flag an unequal count as "check the pairing", not as a DISCREPANCY, because one outdoor unit can serve several indoor units (VRF, as on 26-0339).

---

### Task 1: Schedules and the equipment inventory

**Files:**
- Create `src/estimator/reading/__init__.py` (empty), `src/estimator/reading/schedules.py` and `src/estimator/reading/inventory.py`
- Create `assets/reading_lists/schedules.json`: tag-column headers, the words for manufacturer / model / serves / notes, and controls-responsibility phrases
- Tests: `tests/test_schedules.py`, `tests/test_inventory.py`

**Interfaces (produces):**

```python
@dataclass(frozen=True)
class ScheduleRow:
    tag: str | None            # canonical tag (find_tags), None on a type-only row
    cells: dict[str, str]      # header → cell text, as extracted
    manufacturer: str | None
    model: str | None

@dataclass(frozen=True)
class Schedule:
    document: str
    page: int
    sheet: str | None
    title: str                 # e.g. "VAV BOX SCHEDULE" (the table's first non-empty row, or the text just above)
    headers: tuple[str, ...]
    rows: tuple[ScheduleRow, ...]
    type_only: bool            # no row has a tag
    notes: tuple[str, ...]     # numbered notes under / beside the table
    controls_by: tuple[str, ...]   # the note sentences that say who provides the unit controller

def read_schedules(catalogue, page_opener) -> list[Schedule]

@dataclass(frozen=True)
class InventoryItem:
    tag: str
    kind: str                  # from equipment.json
    category: str              # CONFIRMED | DISCREPANCY | EXTRA | MISSING | ORPHANED | EXISTING | TYPE ONLY | PENDING
    quantity: int | None       # 1 per scheduled tag; None when PENDING
    schedule: str | None       # "M-601 VAV BOX SCHEDULE"
    seen_on: tuple[str, ...]   # other sheets it appears on (from TagEntry.elsewhere)
    reason: str                # plain words, e.g. "On the schedule (M-601) and on 2 plan sheets"
    action: str                # "" | "confirm" | "include pending" | "exclude pending"

@dataclass(frozen=True)
class FamilyTotal:
    kind: str                  # "Variable Air Volume Box"
    prefix: str                # "VAV"
    scheduled: int             # confirmed + missing + discrepancy (duplicate counted once and flagged)
    tags: str                  # compact list, e.g. "VAV-101 thru VAV-112, VAV-114"
    flags: tuple[str, ...]

def build_inventory(catalogue, schedules) -> tuple[list[InventoryItem], list[FamilyTotal], list[str]]   # items, totals, pair flags
```

**Behaviour:**
- Drop any table whose bbox covers more than 60% of the page area.
- Keep tables with at least 2 rows and 3 columns.
- The header row is the first row with a tag-column header word. The title is the row above it, or the text line just above the table.
- Expand "VAV-1 THRU VAV-12", "VAV-1 THRU 12" and "EF-1,2,3" into separate tags.
- A row whose cells say EXISTING, EXIST., (E) or "TO REMAIN" in the tag or remarks is EXISTING.
- **Categories:**
  - A scheduled tag that appears elsewhere (plans, risers, diagrams) is CONFIRMED.
  - A scheduled tag seen nowhere else is MISSING, with the reason "on the schedule only; no plan shows it".
  - A tag listed twice on schedules is DISCREPANCY.
  - A tag of a scheduled kind on drawings but not on any schedule is EXTRA.
  - A tag seen exactly once in the whole job and not on a schedule is ORPHANED.
  - If a job has no schedule sheets at all, every tag gets PENDING with the reason "no schedule in the set".
- **Pairs** come from a small list in `schedules.json`: `[["SS","CU"], ["IU","CU"], ["FCU","CU"], ["CRAC","ACCU"], ["AC","CU"], ["HP","ACCU"]]`. Different counts give the line "check the pairing: 10 HP, 6 ACCU".

**Tests:** synthetic PDFs drawn with ruled lines, for each case:
- a VAV schedule of 3 rows with notes "1. DIGITAL CONTROLS FURNISHED BY TEMPERATURE CONTROL CONTRACTOR."
- a whole-sheet border table (dropped)
- THRU expansion
- a duplicate tag (DISCREPANCY)
- a type-only diffuser schedule
- an EXISTING row
- the inventory categories, from hand-made `TagEntry` lists
- the pair flag

**Smoke:** the VAV / CAV / EF totals on 26-0246 and 26-0352 must equal 58 / 19 and 12 / 1. Report one line per Learn job.

- [ ] Tests first, then code, then the full suite. Commit: `feat: read the schedules into an equipment inventory, by the estimator's quantity rules`

### Task 2: Devices on the plans, the legend, typical floors

**Files:**
- Create `src/estimator/reading/devices.py`
- Create `assets/reading_lists/devices.json`
- Test: `tests/test_devices.py`

**`devices.json`:** label → device, matched exact-case as a whole word:
- T → Thermostat / temperature sensor
- TS → Temperature sensor
- CO2 → CO2 sensor
- OCC → Occupancy sensor
- H → Humidity sensor
- HS → Humidistat
- T/H → Temperature / humidity sensor
- SP → Static pressure sensor
- DP → Differential pressure sensor
- FM → Flow meter
- FS → Flow switch
- TB → Thermostat (by others?), which the legend decides
- DWM → Domestic water meter
- H2 → Hydrogen sensor
- LD → Leak detector
- WS → Weather station
- SD → Smoke detector
- CO → CO sensor
- NO2 → NO2 sensor
- RH → Humidity sensor
- PS → Pressure switch
- CS → Current switch
- DPS → Differential pressure switch
- FZ → Freezestat

Also a list of legend-sheet title words.

**Interfaces (produces):**

```python
@dataclass(frozen=True)
class LegendEntry:
    code: str
    meaning: str
    sheet: str | None

@dataclass(frozen=True)
class DeviceCount:
    sheet: str | None
    document: str
    page: int
    device: str            # "Occupancy sensor"
    label: str             # "OCC"
    count: int             # words on the sheet, outside its title block and legend area
    floors: int            # typical-floor multiplier (1 when not typical)
    total: int             # count * floors
    in_legend: bool        # the job's legend defines this label

@dataclass(frozen=True)
class TypicalSheet:
    sheet: str | None
    title: str
    floors: tuple[str, ...]   # e.g. ("10", "11", ..., "16")
    note: str                 # "Typical plan M-110.00 → floors 10–16: 7 floors. Check the floor list."

def read_legend(catalogue, page_opener) -> list[LegendEntry]
def typical_sheets(catalogue) -> list[TypicalSheet]
def count_devices(catalogue, page_opener, legend, typicals) -> tuple[list[DeviceCount], list[str]]   # counts, flags
```

**Behaviour:**
- **Plan sheets:** sheets whose types include the plans type in `assets/reading_lists/sheet_types.json`. Read the exact type names from that file.
- **Counting:** count the label words on each plan sheet. Exclude words inside the title-block edge (the right and bottom fifth; see `PageRecord.edge_spans`) and, when the sheet is itself a legend, the whole sheet.
- **The legend:** on a legend sheet (from `Sheet.types` "Notes and legends" and a title with LEGEND or SYMBOL), pair each short word (1–5 characters, found in `devices.json` or all capitals) with the longest text run to its right in the same row band (±0.6 of the word height). Where a legend exists, a counted label **not** in it gets `in_legend=False` and a flag: "'TB' counted on M-201 but not in the job's legend — check what it means".
- **Typical floors:** the title matches ordinal floor ranges ("10TH-16TH", "18TH - 21ST", "2ND THRU 5TH", tolerating "19ST") with TYPICAL or TYP. Floors = the range listed.
  - When the range crosses 13, the note says "Floor 13 may not exist — check the floor list".
  - When the same sheet number repeats on N pages (26-0344), count it once and use the floor range, not N. When N ≠ the range length, say so in the note.
- **No labels found** on any plan sheet gives the flag: "No device labels found on the plan sheets (N sheets searched) — device quantities will come from the sequence and point list".
- **Keep the estimator's markup annotations out.** Only page text counts; annotations are not in `PageRecord.text` anyway.

**Tests:** synthetic pages with:
- a plan carrying "T" ×3 and "OCC" ×2 plus a title-block "T" in the edge (not counted)
- a legend row "T  THERMOSTAT OR TEMPERATURE SENSOR" (paired)
- a label not in the legend (flagged)
- a typical title "MECHANICAL 10TH-16TH FLOOR PLAN TYPICAL" (7 floors, ×7), and "12TH-14TH" (note on 13)
- no labels at all (flag)

**Smoke:** 26-0352 M-200.00 gives T ≥ 12 and OCC ≥ 20. 26-0344 finds its four typical sheets. Report one line per Learn job.

- [ ] Commit: `feat: count the devices marked on the plans, read the legend, expand typical floors`

### Task 3: Keynotes and general notes that add controls scope

**Files:**
- Create `src/estimator/reading/keynotes.py`
- Create `assets/reading_lists/keynotes.json`: block headings, and the words that make a note controls-relevant
- Test: `tests/test_keynotes.py`

**Interfaces (produces):**

```python
@dataclass(frozen=True)
class Note:
    sheet: str | None
    document: str
    page: int
    block: str          # "KEY NOTES" | "GENERAL NOTES" | "CONTROLS NOTES" | ...
    number: str         # "7" or "A"
    text: str           # the note, whitespace squashed
    controls: bool      # it names controls scope
    who: str            # "by others" / "by the electrical contractor" / "furnished by the unit manufacturer" / "" — the first such phrase in the note

def read_notes(catalogue) -> list[Note]
```

**Behaviour:**
- Block headings: KEY NOTES, KEYNOTES, KEYED NOTES, SHEET NOTES, GENERAL NOTES, MECHANICAL NOTES, CONTROLS NOTES, BMS NOTES, HVAC NOTES and PLUMBING NOTES, each with an optional colon.
- Split a block into items at `^\s*(\d{1,2}|[A-Z])[.)]\s`. A block ends at the next heading, or after 60 items.
- A note is controls-relevant when it has a controls word: sensor, thermostat, BMS, BAS, ATC, DDC, controls, actuator, damper, valve, interlock, monitor, alarm, point, integration, VFD, "temperature control", "by others".
- **Don't count placements of the numbers.** The research shows they aren't enclosed in shapes on these jobs, so a count would be noise. Each note says "placements not counted".

**Tests:**
- a sheet text with "KEY NOTES: 1. PROVIDE SPACE STATIC PRESSURE SENSOR. BY CONTROLS CONTRACTOR. 2. DUCT DOWN TO UNIT." (note 1 is controls, note 2 isn't)
- lettered general notes
- a "BY OTHERS" note (who="by others")
- a numbered list in a spec page (not read: drawing sheets only)

**Smoke:** report the controls-note count per Learn job.

- [ ] Commit: `feat: read the keynotes and general notes that add controls scope`

### Task 4: Revisions, the latest date wins, and the change log

**Files:**
- Create `src/estimator/reading/revisions.py`
- Create `assets/reading_lists/revisions.json`: date formats, and issue words (ADDENDUM, BULLETIN, REVISED, ISSUED FOR BID, IFC, …)
- Test: `tests/test_revisions.py`

**Interfaces (produces):**

```python
@dataclass(frozen=True)
class Issue:
    number: str         # "4"
    description: str    # "ADDENDUM #1"
    date: date | None

@dataclass(frozen=True)
class SheetVersion:
    sheet: str
    document: str
    page: int
    issues: tuple[Issue, ...]   # from the title block's revision table, oldest first
    latest: date | None         # the latest issue date, else None
    source: str                 # "title block" | "document is an addendum" | "unknown"

@dataclass(frozen=True)
class Change:
    sheet: str
    what: str           # "tag added" | "tag removed" | "schedule row changed" | "note added" | "note removed"
    old: str
    new: str
    affects_controls: bool

@dataclass(frozen=True)
class Supersession:
    sheet: str
    current: SheetVersion
    replaced: tuple[SheetVersion, ...]
    changes: tuple[Change, ...]
    note: str           # "M-400.00: ADDENDUM #1 (02/26/25) replaces ISSUED FOR BID (02/12/25) — 14 changes, 3 affect controls"

def sheet_versions(catalogue) -> list[SheetVersion]
def supersede(catalogue, versions) -> tuple[list[Supersession], list[str]]   # plus flags
```

**Behaviour:**
- **The revision table:** in the page's edge spans (`PageRecord.edge_spans`, the title-block area), find rows of revision number + description + date. Accept these date forms: `02 26 25`, `02/26/25`, `02-26-2025`, `2/26/2025`, `FEB 26, 2025`, `2025-02-26`.
- **Latest date wins, per sheet number.** Among pages carrying the same sheet number in different documents:
  - the latest `latest` date governs;
  - when dates are missing, a document of kind "addendum" beats "base";
  - when neither decides, flag "Sheet M-201 is in two documents with no dates to order them — check which governs".
  - Pages repeated inside one document (typical floors) are not versions.
- **The change log** between the current version and each replaced one:
  - equipment tags added or removed (`find_tags` on each page's text);
  - note lines added or removed: lines in the page text, whitespace squashed, compared as sets, ignoring lines under 12 characters and lines in the title block;
  - `affects_controls` when the line or tag has a controls word (reuse the `keynotes.json` words if Task 3 has landed; otherwise keep its own list in `revisions.json`).
- **Don't use revision clouds.** A whole reissued set with no list (Montclair) is handled by the per-sheet rule.

**Tests:**
- synthetic title-block spans with a four-row revision table (latest = ADDENDUM #1 on 02/26/25)
- two documents with the same sheet number (the later governs)
- no dates plus an addendum document (the addendum governs)
- no dates and two base documents (flag)
- a change log with one tag added, one note removed and a controls note added (affects_controls)

**Smoke:** the Learn jobs have no addenda, so expect zero supersessions and no crash. Report the count of sheets with a readable revision table per job.

- [ ] Commit: `feat: read title-block revisions; the latest date wins per sheet; log every change`

### Task 5: Where the sequence of operation and points list sit

**Files:**
- Create `src/estimator/reading/sequences.py`
- Create `assets/reading_lists/sequences.json`
- Test: `tests/test_sequences.py`

**Interfaces (produces):**

```python
@dataclass(frozen=True)
class Backbone:
    what: str              # "Sequence of operation" | "Points list"
    where: str             # "23 09 93 SEQUENCE OF OPERATIONS (Specs.pdf, pages 40–75)" | "M-805 SEQUENCE OF OPERATIONS (Marked_M.pdf, page 173)"
    document: str
    first_page: int
    last_page: int
    kind: str              # "spec section" | "drawing sheet"
    duplicate_of: str | None   # the same text carried in another document

def find_backbone(catalogue) -> tuple[list[Backbone], list[str]]   # plus flags
```

**Behaviour:**
- **Sequence spec sections:** the number is 23 09 93, 15985 or 25 9x xx, or the title has "SEQUENCE". **Points-list sections:** the title has "POINT(S) LIST" or "POINTS SCHEDULE", or the number is 25 60 xx.
- **Drawing sheets:** the title has "SEQUENCE" or "POINTS LIST" / "POINT LIST" / "POINTS SCHEDULE".
- **A controls section that isn't titled a sequence** but whose pages contain "SEQUENCE OF OPERATION" as a heading also counts, as "sequence inside <section>".
- **Duplicates:** the same section number and title in two documents, with the first page's text ≥ 90% the same (difflib ratio on the first 2,000 characters). The second one gets `duplicate_of`.
- **Flags:**
  - none found: "No sequence of operation found — step 5 has no backbone for this job; scope comes from the drawings"
  - a sequence found but no points list: "No points list found — the sequence is not cross-checked"

**Tests:** built from `SpecSection` / `Sheet` / `PageRecord` objects:
- a 23 09 93 section
- a drawing sheet titled "BMS DOAS POINTS LIST AND SEQUENCE OF OPERATIONS" (both kinds)
- a duplicate section in two documents
- a job with none (flag)

**Smoke:** one line per Learn job. 26-0352 has none; 26-0437 has both, on drawings.

- [ ] Commit: `feat: find the sequence of operation and points list for each job`

### Task 6: Wire it in (after Tasks 1–5 are merged)

**Files:**
- Create `src/estimator/reading/job.py` with:

  ```python
  @dataclass(frozen=True)
  class JobReading:
      schedules
      inventory
      totals
      devices
      legend
      typicals
      notes
      versions
      supersessions
      backbone
      flags

  def read_job(catalogue, page_opener=None) -> JobReading
  ```

  The default opener opens `Document.path` with pymupdf and caches the open documents.
- Modify `src/estimator/evidence/workbook.py`. New tabs after "Spec overview":
  - "Equipment": the family totals first, then every item with its category, reason, schedule, seen on and action; the category cell is coloured green (CONFIRMED), amber (DISCREPANCY / PENDING / TYPE ONLY / EXTRA / ORPHANED / MISSING) or grey (EXISTING)
  - "Schedules": every schedule's title, sheet, row count and controls-by notes
  - "Devices on plans": per sheet, device, label, count, floors and total, then the legend
  - "Notes": the controls-relevant notes first
  - "Changes": the supersessions and every change
  - "Sequence and points": the backbone
  - Keep `write_evidence(path, catalogue)` working. Add an optional `reading: JobReading | None = None` parameter; the new tabs are written only when it is given.
- Modify `src/estimator/__main__.py`: the `catalogue` command calls `read_job` and passes it on, and prints `reading_lines(reading)` after `summary_lines`.
- Modify `tools/learn_check.py`: add a "Reading" table (Job | Scheduled units | Families | Categories needing a look | Device labels counted | Typical sheets | Controls notes | Supersessions | Sequence / points). Add the expectations `"families_include": {"VAV": 58, "CAV": 19}` for 26-0246 and `{"VAV": 12, "EF": 1}` for 26-0352, with the misses reported.
- Tests: `tests/test_reading_job.py`, plus updates to `test_evidence.py` and `test_main.py`.
- [ ] Commit: `feat: the Evidence Package shows the equipment, devices, notes, changes and the sequence backbone`
- [ ] Run the full suite and the Learn check (exit 0).
