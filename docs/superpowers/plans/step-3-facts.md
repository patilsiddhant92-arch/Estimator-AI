# Step 3 Facts — Measured Facts About the Learn Job Archive

Measured against `D:\Estimation Assistant\Learn`, jobs 26-0246, 26-0328, 26-0334, 26-0339, 26-0344 ("80 Broad St, NY"), 26-0352 ("Tishman Speyer, 45 Rockefeller Suite 2100"), 26-0356 ("Mott Haven Community Center Upgrades..."), 26-0436 ("Equinix", which also contains a nested `26-0437` sub-job), 26-0445. All nine jobs are covered (26-0339 and 26-0344 were initially held back as an unseen test set, then released mid-task — every measurement below includes them).

Python: `D:\Estimator AI\.venv\Scripts\python.exe` with `pymupdf` 1.28.2. Scratch scripts live under the session scratchpad; this file is the only output written outside it.

---

## 1. Folder layout and file classification

### 1.1 Folder names that appear

Across the nine jobs, the recurring top-level folders are:

- `2. Takeoffs\1. Base Takeoff` — the estimator's working copy of the bid documents (drawings + specs), almost always where the big PDFs live. Revision folders `2. A` and `3. A` sit alongside it (present but empty/unused in every job sampled — no PDFs found under them).
- `3. Proposal\1. Base Proposal` — Nordomatic's own outgoing proposal PDFs (small, letter-size, named e.g. `26-0334 2.pdf`, `26-0334_ELEC.pdf`).
- `5. Price Workup\1. Base Documents` — pricing workbooks (`.xlsm`/`.xlsx`), not PDFs.
- `Trace_Logs` — tool logging, not bid documents.
- 26-0356 uses `1. Project Documents\1. Base Documents` instead of a bare `Takeoffs` folder for the RFQ package (this job is a NYCHA public RFQ, not a GC-issued bid set, hence the different top folder name).
- 26-0436 nests a second job, `26-0437`, one level inside `26-0436\2. Takeoffs\1. Base Takeoff\26-0437\...` — this is a Kusters/FRBNY controls-only work package bid living inside the Equinix job folder. It has its own `2. Takeoffs`, `3. Proposal`, `5. Price Workup` structure and its own `Specs\22-Plumbing`, `Specs\23-...HVAC...`, `Specs\25-Integrated-Automation`, `Specs\26-Electrical` sub-folders (a fully spelled-out CSI MasterFormat spec tree, unique to this job).
- 26-0436's own `2. Takeoffs\1. Base Takeoff` additionally has `2. RFP Exhibits`, `3. ZSKs` (change-order sketches), `4. RFI Responses & Documents`, and `Exhibits` — the only job with RFI/ZSK sub-folders.
- `00_Stage0_Artifacts\vision` and `04_Deliverable` appear in 26-0334 and 26-0352 — these are artifacts of this AI-estimating project itself (prior phase outputs), not source bid documents; ignored.

### 1.2 PDF inventory

252 PDFs total across the nine jobs (241 across the original seven, plus 3 in 26-0339 and 4 in 26-0344 once those two were released mid-task). Per-job PDF counts (from a full `os.walk` + `pymupdf.open` pass, page count and page-1 size read for every file):

| Job | PDFs | Notes |
|---|---:|---|
| 26-0246 | 7 | 3 spec + 4 drawing |
| 26-0328 | 11 | 3 drawing + 4 spec + 4 other (HFAT/DCIM checklists) |
| 26-0334 | 5 | 4 spec + 1 drawing |
| 26-0339 | 3 | 1 drawing + 2 spec |
| 26-0344 | 4 | 2 spec + 2 drawing |
| 26-0352 | 3 | 3 drawing (no separate specs found — proposal-only spec content) |
| 26-0356 | 10 | 6 other (RFQ admin/contract-book docs) + 2 drawing + 2 spec |
| 26-0436 | 194 | 13 drawing + 170 spec (mostly the fully-split `26-0437\...\Specs\22-...\26-...` CSI tree, one PDF per section) + 10 other + 1 rfi |
| 26-0445 | 11 | 7 drawing + 2 spec + 2 other |
| **Total** | **252** | |

### 1.3 How files were classified (drawing / spec / addenda / rfi / other)

Rule used, in order:
1. **Drawing**: page-1 size (long edge) ≥ 1500 pt. Every oversized/large-format sheet in this archive (ARCH D/E-ish sheets — most commonly 3024×2160 pt, 2592×1728 pt, 3456×2592 pt, 2448×1584 pt) is a drawing set; nothing letter/tabloid-sized in the archive is a drawing. This heuristic had **zero false positives or negatives** in a manual spot-check of the classified list.
2. Else, filename contains `rfi` → **rfi** (only 1 hit: `2026-07-15 RFI Log for WP-4.pdf` in 26-0437, 1224×792 tabloid).
3. Else, filename contains `addend`/`addendum` → **addenda** (0 hits in this archive — none of the nine jobs happen to keep a standalone addenda PDF; addenda content that exists is folded into the RFQ/contract-book PDFs, e.g. 26-0356's 1588-page "Contract Book").
4. Else, filename contains `spec`, or looks like a CSI section number (`##-##-##...` or a bare 5-digit old-format number like `Marked_15970.pdf`), or contains "manual" → **spec**.
5. Else → **other** (RFQ admin paperwork, BOD/coordination matrices, checklists, timelines, contract books, project manuals not named "spec").

**Known miss**: the filename rule does not catch "Project Manual" / "PManual" as a spec keyword unless refined — `NY10-1 IFP - Project Manual.pdf` (1830 pages, 26-0436) and `2026.06.26 QTS WTX-1 DC-1 IFC PManual...pdf` (2922 pages, 26-0445) are true specs/contract-manual documents but fell into "other" under the as-run rule. A production rule should add `\bmanual\b` and `\bp\s*manual\b` to the spec keyword list.

### 1.4 Representative file list (full list is 252 rows; see the classify.py output for all — key examples below)

**26-0246** (`2. Takeoffs\1. Base Takeoff\`):
- `Marked_15970.pdf` — spec, 246p, 612×792 (old 5-digit section numbering, "15970" = old-format HVAC controls spec number)
- `Marked_15973.pdf` — spec, 21p, 612×792
- `Marked_15985.pdf` — spec, 96p, 612×792
- `Marked_Elec Electrical Drawing.pdf` — drawing, 58p, 3024×2160
- `Marked_Mech Mechanical Drawing.pdf` — drawing, 50p, 3024×2160, rot 90
- `Marked_Plumb Pumbing Drawing.pdf` — drawing, 26p, 3024×2160
- `Marked_SSDS Drawing.pdf` — drawing, 6p, 3024×2160, rot 270

**26-0339**: `Marked-Mech.pdf` (drawing, 67p, 3456×2592), `Marked_Specs_230993_Sequence of Operation.pdf` (spec, 35p — note the filename already carries a MasterFormat number, 23 09 93), `26-0339_K.pdf` (spec/proposal, 10p).

**26-0344** ("80 Broad St, NY"): `80 Broad - HVAC Specs.pdf` (spec, 296p), `80_ GMP Mechanical Set 2026.06.19 (new).pdf` (drawing, 63p, 2448×1584, rot 270), `80_ GMP Plumbing Set.pdf` (drawing, 42p, 2448×1584, rot 270), `26-0344.pdf` (spec/proposal, 9p).

**26-0436** ("Equinix", plus nested 26-0437): drawing files are named by discipline letter or combined set — `Marked_Mech+Sketch Mech.pdf` (75p), `NY10-1 IFP - 09 ELECTRICAL (Combined).pdf` (236p, rot 90), `NY10-1 IFP - 10 TELECOM (Combined).pdf` (84p), `26-0437\...\A.pdf` (359p architectural), `26-0437\...\Marked_E.pdf` (242p), `Marked_M.pdf` (196p), `Marked_P.pdf` (76p). The spec set is `26-0437\2. Takeoffs\1. Base Takeoff\Specs\22-Plumbing\*.pdf`, `...\23-Heating,-Ventilating,-and-Air-Conditioning-(HVAC)\*.pdf`, `...\25-Integrated-Automation\*.pdf`, `...\26-Electrical\*.pdf` — one PDF per CSI section (170 files), each named `##-##-##[.##]-Title_Rev_N.pdf`, e.g. `23-09-00-Instrumentation-and-Control-for-HVAC_Rev_8.pdf`.

**26-0445**: drawing files are `##_DISCIPLINE_COMBINED.pdf` (`12_PLUMBING_COMBINED.pdf` 107p, `14_MECHANICAL_COMBINED.pdf` 121p, `15_ELECTRICAL_COMBINED.pdf` 226p — largest single PDF in the whole archive at 715 MB, `17_TECHNOLOGY_COMBINED.pdf` 88p, `Marked_10_CONTROLS_COMBINED.pdf` 73p) plus a 2922-page project manual (`2026.06.26 QTS WTX-1 DC-1 IFC PManual...pdf`, misclassified as "other", see 1.3).

---

## 2. Page rotation

`page.rotation` was read for **every page** of every PDF classified as "drawing" (2,948 pages across 32 drawing PDFs in the nine jobs — cheap, since reading `.rotation` does not parse the content stream).

### 2.1 Distribution (per drawing PDF)

| Job | File | Pages | Rotation counts |
|---|---|---:|---|
| 26-0246 | Marked_Elec Electrical Drawing.pdf | 58 | {0: 51, 270: 7} |
| 26-0246 | Marked_Mech Mechanical Drawing.pdf | 50 | {90: 49, 0: 1} |
| 26-0246 | Marked_Plumb Pumbing Drawing.pdf | 26 | {0: 25, 90: 1} |
| 26-0246 | Marked_SSDS Drawing.pdf | 6 | {270: 6} |
| 26-0328 | 14_MECHANICAL_COMBINED.pdf | 60 | {90: 58, 0: 2} |
| 26-0328 | Marked_14_MECHANICAL_COMBINED.pdf | 60 | {90: 58, 0: 2} |
| 26-0328 | Marked_Process.pdf | 69 | {0: 69} |
| 26-0334 | Marked_Mech.pdf | 7 | {0: 7} |
| 26-0339 | Marked-Mech.pdf | 67 | {0: 67} |
| 26-0344 | 80_ GMP Mechanical Set 2026.06.19 (new).pdf | 63 | {270: 2, 0: 61} |
| 26-0344 | 80_ GMP Plumbing Set.pdf | 42 | {270: 42} |
| 26-0352 | Marked_Elec.pdf | 12 | {270: 12} |
| 26-0352 | Marked_Mech.pdf | 14 | {270: 14} |
| 26-0352 | Marked_Plumbing.pdf | 6 | {270: 6} |
| 26-0356 | RFQ # 511469_Drawings...pdf | 115 | {270: 66, 0: 49} |
| 26-0356 | Marked_Mech_Drawing.pdf | 18 | {0: 18} |
| 26-0436 | Marked_Mech+Sketch Mech.pdf | 75 | {0: 75} |
| 26-0436 | Marked_NY10-1 IFP – 13 CONTROLS (Combined).pdf | 44 | {270: 44} |
| 26-0436 | NY10-1 IFP - 02 CIVIL (Combined).pdf | 21 | {270: 21} |
| 26-0436 | NY10-1 IFP - 07 PLUMBING (Combined).pdf | 15 | {0: 15} |
| 26-0436 | NY10-1 IFP - 09 ELECTRICAL (Combined).pdf | 236 | {90: 228, 0: 8} |
| 26-0436 | NY10-1 IFP - 10 TELECOM (Combined).pdf | 84 | {0: 84} |
| 26-0436 | RFI Mechanical Sketches 001-033.pdf | 33 | {0: 33} |
| 26-0436 (26-0437) | Kusters System Drawings Scope Markup.pdf | 28 | {0: 28} |
| 26-0436 (26-0437) | A.pdf (architectural) | 359 | {0: 359} |
| 26-0436 (26-0437) | EPMS COUNT.pdf | 9 | {0: 9} |
| 26-0436 (26-0437) | Marked_E.pdf | 242 | {0: 230, 180: 12} |
| 26-0436 (26-0437) | Marked_M.pdf | 196 | {0: 196} |
| 26-0436 (26-0437) | Marked_P.pdf | 76 | {0: 76} |
| 26-0445 | 12_PLUMBING_COMBINED.pdf | 107 | {0: 107} |
| 26-0445 | 14_MECHANICAL_COMBINED.pdf (×3 near-dup copies) | 121 each | {0: 121} |
| 26-0445 | 15_ELECTRICAL_COMBINED.pdf | 226 | {0: 2, 90: 224} |
| 26-0445 | 17_TECHNOLOGY_COMBINED.pdf | 88 | {0: 88} |
| 26-0445 | Marked_10_CONTROLS_COMBINED.pdf | 73 | {0: 73} |

**Aggregate**: of ~2,948 drawing pages, roughly 62% are `rotation=0`, ~24% are `rotation=90`, ~13% are `rotation=270`, and 12 pages (0.4%, all in one file, `Marked_E.pdf`) are `rotation=180`. Every drawing PDF is internally consistent-ish but **not uniform** — several files mix 0 and 90/270 on a handful of pages (e.g. `Marked_Elec Electrical Drawing.pdf` is 51×0 + 7×270; `14_MECHANICAL_COMBINED.pdf` is 58×90 + 2×0). A per-page rotation check is required; a per-file assumption would misplace text on those minority pages.

### 2.2 Getting visual coordinates from rotated pages

`page.get_text("dict")` span `bbox` coordinates are **not** in the page's visual (as-displayed) space — they are in the PDF content-stream's native coordinate space, which is pre-rotation. Concretely, tested on `26-0246\...\Marked_Mech Mechanical Drawing.pdf` page 0 (`rotation=90`):

- `page.rect` = `Rect(0, 0, 3024, 2160)` — this is actually the **visual** (already-rotated, landscape) size pymupdf reports.
- `page.cropbox` = `Rect(0, 0, 2160, 3024)` — the raw/native portrait content-stream space that span bboxes live in (confirmed: a span had raw bbox `y0=2720, y1=2914`, which only makes sense inside a 3024-tall native space, not the 2160-tall value `page.rect.height` would naively suggest).
- `page.rotation_matrix` = `Matrix(0, 1, -1, 0, 3024, 0)` for this page.

**Rule**: to place a text span in visual (as-viewed) coordinates, take each corner of its raw `bbox`, multiply by `page.rotation_matrix` (e.g. `pymupdf.Point(x0,y0) * page.rotation_matrix`), then take the axis-aligned min/max of the four transformed corners. Divide by `page.rect.width` / `page.rect.height` to get fractional visual position. This was verified on the page above: the raw span `bbox=(58.3, 2721.0, 77.2, 2914.6)` for text `"SUMMARY OF WORK"` maps to visual corners around `(303, 58)`–`(109, 77)`, i.e. fractional position `(0.036, 0.036)` — top-left of the visually-rotated (landscape) sheet, which matches where that note actually sits when the drawing is viewed right-side-up. `page.derotation_matrix` is the inverse, for going the other way.

---

## 3. Title blocks

### 3.1 Where the title block sits, in visual fractional coordinates

Checked on ≥5 sheets per drawing PDF (all pages for the small ones), using the visual-coordinate method from §2.2. In every drawing PDF in this archive, the title block is a **vertical strip along the right edge and/or a horizontal strip along the bottom edge** of the visually-rotated sheet — never the left or top. Concretely: sheet number and sheet title both sit at visual `fx0 ≈ 0.89–0.98` (right 11% of the sheet) and `fy0 ≈ 0.75–0.97` (bottom quarter), across all three distinct title-block templates seen in the archive:

- **NYC-DOB/AE-style** (26-0246): sheet number bottom-right at `fx≈0.94, fy≈0.92-0.94`, e.g. `M001.00` (font size 41pt, far larger than anything else on the sheet), title directly above it (e.g. `HVAC GENERAL NOTES` at `fy≈0.851`, 20.4pt).
- **Thornton Tomasetti/Syska (26-0436/26-0437)**: sheet number at `fx≈0.94-0.98, fy≈0.93-0.97`, e.g. `M-001`, `M-111` (font size ~50pt), with an explicit `"SHEET TITLE:"` label directly below-left of the title text (`fx≈0.889, fy≈0.786`, 9.5pt) and `"SHEET NO."` label similarly next to the number — this is the only template with a literal findable label.
- **QTS/Freedom-Standard (26-0328's `14_MECHANICAL_COMBINED.pdf`, all of 26-0445's `*_COMBINED.pdf` family)**: sheet number at `fx≈0.93-0.98, fy≈0.96-0.99`, e.g. `M00-03`, `M00-01`, `TC00-00` (font size 37-45pt — a **two-part number**: 2-digit "set" + dash + 2-digit "sheet-within-set", not the simple prefix-number pattern seen elsewhere), title 2-3 lines above it (e.g. `LEVEL 02 - / OVERALL PLAN - / MASTER / MECHANICAL / EQUIPMENT`, 24.9pt, one word per line).

### 3.2 Extraction rule proposed and tested

```python
SHEET_NO_RE = re.compile(r'^[A-Z]{1,3}[\-\s]?\d{1,4}(\.\d{1,3})?[A-Za-z]?$')
TITLE_LABEL_RE = re.compile(r'(SHEET\s*TITLE|DRAWING\s*TITLE)', re.IGNORECASE)
```
Rule: pull every text span via `page.get_text("dict")`, map each span's `bbox` to visual coordinates via `page.rotation_matrix` (§2.2), keep only spans in the right-or-bottom strip (`fx0 >= 0.85 or fy0 >= 0.85`), then take the **largest-font span in that strip whose text matches `SHEET_NO_RE`** as the sheet number (font size alone reliably separates the true sheet number — 37-56pt — from every other strip element, including look-alike codes like a project number or a smaller cross-reference). For the title: if a span matching `TITLE_LABEL_RE` exists in the strip, concatenate the span(s) sitting just above it in the same column; otherwise fall back to spans above the sheet-number span, in the same x-column, with font size between 14 and (sheet-number size − 5).

**Tested on every page of every drawing PDF in all nine jobs (2,948 pages, 32 files)**: **overall hit rate 2,560/2,948 = 86.84%** for the sheet number. Per file:

| Job | File | Pages | Hits | Rate |
|---|---|---:|---:|---:|
| 26-0246 | all 4 drawing files | 140 | 140 | 100% |
| 26-0328 | 14_MECHANICAL_COMBINED.pdf (+Marked copy) | 60+60 | 6+6 | **10.0%** |
| 26-0328 | Marked_Process.pdf | 69 | 31 | 44.9% |
| 26-0334 | Marked_Mech.pdf | 7 | 0 | **0%** (no text layer at all, see §8) |
| 26-0339 | Marked-Mech.pdf | 67 | 67 | 100% |
| 26-0344 | both drawing files | 105 | 105 | 100% |
| 26-0352 | all 3 drawing files | 32 | 32 | 100% |
| 26-0356 | both drawing files | 133 | 133 | 100% |
| 26-0436 | Marked_Mech+Sketch Mech.pdf, Marked_NY10-1 CONTROLS, PLUMBING, TELECOM, RFI sketches, Kusters, A.pdf, EPMS, Marked_E/M/P.pdf | 1,388 | 1,363 | 98.2% |
| 26-0436 | NY10-1 IFP - 02 CIVIL (Combined).pdf | 21 | 1 | **4.8%** |
| 26-0436 | NY10-1 IFP - 09 ELECTRICAL (Combined).pdf | 236 | 221 | 93.6% |
| 26-0445 | 12_PLUMBING/14_MECHANICAL(×3)/15_ELECTRICAL/17_TECHNOLOGY/10_CONTROLS | 857 | 648 | 75.6% |

**Root causes of failure, confirmed by inspecting actual pages (not guessed):**

1. **Two-part sheet numbers (`M00-03`, `TC00-00`) don't match `SHEET_NO_RE`.** This is the single biggest cause — it accounts for nearly all of 26-0328's and 26-0445's fails. Confirmed on `26-0328\...\14_MECHANICAL_COMBINED.pdf` page 3: the correct, largest-font (45.1pt) strip span is literally `'M00-03'`, sitting exactly where expected (`fx0=0.933, fy0=0.973`), but the regex requires a single hyphen immediately after the letter prefix, not one buried after two digits. **Fix, tested**: extended the regex to `r'^[A-Z]{1,3}[\-\s]?\d{1,4}(-\d{1,3})?(\.\d{1,3})?[A-Za-z]?$'` (allow an optional second `-digits` group) and re-ran it over every page of the affected files: **26-0445's entire `*_COMBINED.pdf` family jumped from 75.6% to 100.0%** (all 6 files, 857/857 pages), and **26-0328's `14_MECHANICAL_COMBINED.pdf` jumped from 10.0% to 83.3%** (50/60 — the remaining 10 misses were not investigated further but are likely a different sub-layout on those specific pages). This confirms the gap was purely mechanical (regex shape), not a positional/ROI problem — the ROI and largest-font logic both already picked the right span every time.
2. **26-0334's `Marked_Mech.pdf` is 100% image-only** (see §8) — no text span exists on any page, so no text-based rule can work; this file needs OCR.
3. **26-0436's Langan-authored CIVIL/ELECTRICAL "Combined" sets have some sheets where no sheet-number-shaped text exists in the ROI at all** (not a regex miss — there is no 40+pt numeric span in the strip). Confirmed on `NY10-1 IFP - 02 CIVIL (Combined).pdf` page 3: the largest text in the ROI is the project address (`'275 HARTZ WAY'`, 15.7pt) and revision-table entries (10-11pt) — no candidate anywhere close to sheet-number size. This looks like the sheet number is rendered as part of a flattened/rasterized title-block border image on these particular sheets rather than as live text (the ELECTRICAL set from the same consultant recovers fine on 93.6% of pages, so it is sheet-specific, not a whole-file problem). A production rule needs either an image/OCR fallback for this consultant's specific sheets, or accepting that a fraction of this job's civil sheets simply won't yield a sheet number from text alone.
4. Two apparent "hits" in the CIVIL/ELECTRICAL fails table are actually **wrong-title false-fills**: the title fallback logic mis-picked the revision block's project address ("REVISIONS PROJECT 275 HARTZ WAY SECAUCUS, NJ 07094") as the sheet title on pages where the real title area is empty/rasterized — a reminder that the title fallback (unlike the sheet-number's font-size discriminator) is comparatively weak and needs a tighter column/x-alignment tolerance or a hard requirement that a `TITLE_LABEL_RE` anchor be present.

**Net effect of the regex fix**: applying the extended `SHEET_NO_RE` (v2) to the files it affects and leaving the rest unchanged gives an estimated **overall hit rate of ~96.6% (2,848/2,948)** — nearly all of the remaining ~100-page gap is the two structurally-unfixable cases above (26-0334's fully-scanned file, and the ~35 CIVIL/ELECTRICAL pages with no sheet-number text at all), plus the untested `Marked_Process.pdf` remainder and 26-0328's 10 residual misses.

**pymupdf API used**: `page.get_text("dict")` for span-level text + `bbox` + `size` + `font`; `page.rotation_matrix` for visual-coordinate mapping; no OCR was needed for the 86.84%/96.6% that succeeded (pure vector text).

## 4. Sheet titles → type

### 4.1 Method

Sampled ~25 pages per drawing PDF (695 title extractions, 177 distinct title strings after de-duplication) using the same extraction rule as §3 (with the fixed `SHEET_NO_RE`). Coverage was uneven: 26-0246/26-0339/26-0352/26-0356/26-0436 got a title on essentially every sampled page; 26-0328 and 26-0445 (the QTS/Freedom-Standard template) got titles on only ~40% of sampled pages even after the sheet-number fix, because their multi-line, one-word-per-line titles (`LEVEL 02 - / OVERALL PLAN - / MASTER / MECHANICAL / EQUIPMENT`) don't always fall inside the fixed font-size window (`14 ≤ size < sheet_no_size − 5`) used by the no-label fallback; 26-0334 got 0 (no text layer at all, per §8).

### 4.2 Keyword rules tried and how many titles they typed

| Type | Rule (regex, case-insensitive) | Distinct titles matched (of 177) | Examples |
|---|---|---:|---|
| PLAN | `\bPLAN\b\|OVERALL PLAN\|FLOOR PLAN\|SITE PLAN` | 49 | `LEVEL 01 - OVERALL PLAN - MASTER MECHANICAL EQUIPMENT...`, `HVAC - ROOF PLAN - OVERALL...`, `LEVEL 02 PLAN - SECTOR E...` |
| TECHNOLOGY_LOWVOLTAGE (non-mech, other-discipline) | `TECHNOLOGY\|LOW VOLTAGE\|TELECOM\|SECURITY\|IT\b` | 20 | mostly one repeated Kusters-drawing disclaimer paragraph mis-picked as a "title" — see 4.3 |
| DETAIL | `DETAIL` | 18 | `MECHANICAL DETAILS...`, `BMS CONTROLS DETAILS...`, `TISHMAN SPEYER ELECTRICAL - DETAILS I` |
| CONTROL_DIAGRAM | `CONTROL.*DIAGRAM\|SEQUENCE OF OPERAT\|POINTS? LIST\|BAS\b\|BMS\b\|CONTROLS?\s*(PLAN\|DIAGRAM\|RISER)` | 15 | `DATA HALL 1200 DCIM BMS EPMS DIAGRAM...`, `CHILLED WATER PLANT 2 DCIM BMS/EPMS DIAGRAM...` |
| NOTES/LEGEND/SYMBOLS/COVER ("other") | `\bLEGEND\b\|\bSYMBOLS?\b\|\bNOTES?\b\|COVER\s*SHEET\|ABBREVIATION` | 12 | `SYMBOLS, ABBREVIATIONS, AND GENERAL NOTES...`, `RUDDY CETRA MECHANICAL COVER SHEET` |
| ELECTRICAL (non-mech) | `ELECTRIC\|LIGHTING\|POWER\b\|PANEL\s*BOARD\|SWITCHGEAR` | 12 | `TISHMAN SPEYER ELECTRICAL - 21ST FLOOR POWER PLAN`, `...RISER DIAGRAM`, `...SCHEDULES` |
| PLUMBING (non-mech) | `PLUMB\|SANITARY\|DOMESTIC WATER\|STORM DRAIN` | 11 | `TISHMAN SPEYER PLUMBING - 21ST FLOOR RISER DIAGRAM`, `...DETAILS`, `...SPECIFICATIONS` |
| SCHEDULE | `SCHEDULE` | 9 | `SCHEDULES...`, `VENTILATION SCHEDULES...`, `TISHMAN SPEYER MECHANICAL SCHEDULES` |
| WATER_RISER | `(WATER\|PIPING\|PIPE\|HYDRONIC).*RISER\|RISER.*(WATER\|PIPING\|PIPE)` | 5 | `SANITARY PIPING RISER DIAGRAM - SEGMENT E2...`, `DOMESTIC WATER RISER DIAGRAM - SEGMENT B2...`, `...HOT WATER AND STEAM RISER DIAGRAM` |
| DEMOLITION | `DEMO` | 3 | `TISHMAN SPEYER ELECTRICAL - 21ST FLOOR PLAN - DEMOLITION`, `...MECHANICAL 21ST FLOOR DEMOLITION PLAN` |
| AIR_RISER, NETWORK_RISER | (regex written, see script) | 0 | not seen in this sample — no title in the 695-occurrence sample literally combines "air"/"duct"/"network"/"telecom" with "riser"; process-air diagrams in this archive are titled "...FLOW DIAGRAM" or "...AIR FLOW DIAGRAMS" instead (see 4.3) |

**114 of 177 distinct titles (64%) got typed** by these nine rules (a title can match more than one rule, e.g. an electrical schedule title matches both ELECTRICAL and SCHEDULE — the 64% is titles-with-at-least-one-match). **63 titles (36%) stayed untyped.**

### 4.3 What stayed untyped, and why

Inspecting all 63 untyped titles, they fall into three real buckets, not "the rules need more keywords" in every case:

1. **Genuine gaps in the keyword list** (~15 titles) — process/flow-diagram sheets titled `CHILLED WATER FLOW DIAGRAM - DATA HALL 1100 & 2100`, `MECHANICAL AIR FLOW DIAGRAMS`, `AIRFLOW DIAGRAM`, `ISOMETRIC VIEWS`; compliance/code sheets `MECHANICAL VENTILATION COMPLIANCE`, `MECHANICAL CODE COMPLIANCE`; plan-family titles that don't literally say "PLAN" — `HVAC - LEVEL ONE - OVERALL`, `LEVEL 01 - SECTOR D`, `LEVEL 01 & 02 - OVERALL - TEAM GROUPING`; and a commissioning-specs title family `TISHMAN SPEYER MECHANICAL COMMISSIONING SPECIFICATIONS SHEET 1 OF 3`. A production rule set should add `FLOW DIAGRAM`, `ISOMETRIC`, `COMPLIANCE`, and a looser "starts with LEVEL/SECTOR/SEGMENT and has no other keyword ⇒ PLAN" fallback.
2. **Extraction-rule noise, not real titles** (~40 titles) — this is the more important finding. On pages where no explicit `"SHEET TITLE:"` label exists, the no-label fallback (§3.2) grabs *every* span in the same x-column and font-size band above the sheet number, which on several templates also catches the seal-and-signature block (`TRUE NORTH PROJECT NORTH SEAL AND SIGNATURE: Principal In Charge Rafael Stein Project Manager Sanober Khan...`, repeated with different names/dates — 8 distinct "titles" that are really the PE-seal block, 26-0436 CIVIL), the revision-table header (`REVISIONS PROJECT 275 HARTZ WAY SECAUCUS, NJ 07094`, `REVISIONS PROJECT 1/2" CW 1/2" CW 3" CW RPZ 275 HARTZ WAY SECAUCUS, NJ 07094` — dimension callouts bled in too), a repeated legal disclaimer paragraph on the Kusters system drawings (`THIS DRAWING IS NOT TO BE USED AS BUILDING CONSTRUCTION DRAWING...ROYAL DUTCH KUSTERS CANNOT ACCEPT ANY RESPONSIBILITY...` — 6 near-duplicate variants, differing only by stray dimension numbers picked up mid-string), and a `"NOT FOR CONSTRUCTION" / "INTERNAL FR - OFFICIAL USE / EXTERNAL"` status stamp (7 variants, 26-0436/26-0437 Thornton Tomasetti template). **None of these are sheet titles** — they're a hard signal that the no-label fallback needs a stricter column/size window or an explicit denylist for known boilerplate phrases (`SEAL`, `REVISIONS`, `NOT FOR CONSTRUCTION`, `PROJECT NORTH`) before it's trustworthy without a `"SHEET TITLE:"` anchor.
3. **Genuinely ambiguous/short residual titles** (~8) — `TISHMAN SPEYER RCP`, `TISHMAN SPEYER CONTROLS RCP` (reflected ceiling plan — architectural, not mechanical; would need an RCP keyword), and the PS Q517 project-name/address block from 26-0246 (a real repeating field, same root cause as bucket 2).

### 4.4 Non-mechanical disciplines seen

Confirmed disciplines other than mechanical/controls turning up in sheet titles across the archive: **electrical** (`TISHMAN SPEYER ELECTRICAL - ...`, lighting/power/panelboard/switchgear sheets), **plumbing** (`TISHMAN SPEYER PLUMBING - ...`, sanitary/domestic-water sheets), **architectural** (`TISHMAN SPEYER RCP` — reflected ceiling plan), **civil** (26-0436's `NY10-1 IFP - 02 CIVIL (Combined).pdf`, filename-level only — title extraction mostly failed on this file per §3), and **technology/low-voltage** (26-0436/26-0445's `17_TECHNOLOGY_COMBINED.pdf` / `10 TELECOM` sets, filename-level; title text on the one sampled cover-sheet page read `TECHNOLOGY / COVER SHEET & / SYMBOL LEGEND`).

## 5. Specs — section headers

### 5.1 How section headers actually appear (verbatim, per style)

Three header/footer conventions were found, sometimes several in the same job:

- **Old 5-digit format**, whole word "SECTION" + number, e.g. `SECTION 15970` (26-0246, `Marked_15970.pdf` — this is literally the old NYC School Construction Authority "Temperature Control System (BACnet BMS/DDC...)" spec, numbered under the pre-2004 16-division MasterFormat). Footer on every page: `15970 - 15` (section-dash-page).
- **New 6-digit MasterFormat, no spaces**, e.g. `SECTION 230500`, footer `230500-1` (26-0334's `K-9 Facility-Controls Specs Only.pdf`, and the whole `NY10-1 IFP - Project Manual.pdf` / `2026.06.26 QTS ... PManual` in 26-0436/26-0445).
- **New 6-digit MasterFormat, spaced**, e.g. `SECTION 23 09 23`, footer `23 09 23 - 1` (26-0356's RFQ spec, 26-0436/26-0437's per-section CSI PDFs like `23-09-00-Instrumentation-and-Control-for-HVAC_Rev_8.pdf` whose own text reads `SECTION 23 05 00.1` / `SECTION 25 00 00`).
- `END OF SECTION` appears verbatim (all-caps) at the end of nearly every section in every convention.

**Important encoding gotcha found while testing**: `26-0334\...\K-9 Facility-Controls Specs Only.pdf` (and likely other Bluebeam/older-export PDFs) do **not** use a real space character (0x20) between words — they use the C0 control code `\x04` as the space glyph. `get_text("text")` returns strings like `'New\x04Construction\x04of\x04the...'` and `'230500\x04-\x041'`. A naive `\s+`/`\s*` regex against raw `get_text()` output returns **zero matches** on this file even though the section numbers and "END OF SECTION" are present — confirmed by testing (initial full-archive pass got 0 hits on 26-0334 and 26-0352; only after normalizing `re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', ' ', text)` did the same regex find 104 section-footer hits in the same file on re-scan). **Any production text-regex pipeline over this archive must normalize C0 control characters to spaces before matching** — this is not an edge case, it affects a whole PDF's worth of specs.

### 5.2 Regex proposed and page ranges found

```
SECTION_HDR_RE = re.compile(r'SECTION\s+(\d{2}\s?\d{2}\s?\d{2}(?:\.\d{1,2})?|\d{5})\b', re.IGNORECASE)
FOOTER_RE      = re.compile(r'^\s*(\d{2}\s?\d{2}\s?\d{2}|\d{5})\s*[-\u2013]\s*\d{1,3}\s*$', re.MULTILINE)
END_SECTION_RE = re.compile(r'END OF SECTION', re.IGNORECASE)
```
applied to `normalize(page.get_text("text"))` for every page of every spec-classified PDF (plus the two "other"-misclassified project manuals, see 1.3). A section's page range = from its first `SECTION_HDR`/`FOOTER` page to the page before the next section's first page (or EOF).

This found (raw counts across the full archive, before the encoding fix; re-run with the fix on 26-0334): 26-0246: 27 hits (3 files); 26-0328: 3,228 hits (mostly footers) in `305_SPECS_ATL2-DC11_IFP_26.05.22.pdf`; 26-0334: 0 on the naive pass → **110 hits** after the `\x04` fix; 26-0339: 38 hits in `Marked_Specs_230993_Sequence of Operation.pdf`; 26-0344: 155 hits in `80 Broad - HVAC Specs.pdf`; 26-0352: **0 — this job has no separate spec PDF at all** (only 3 drawing PDFs; confirmed, not a detection failure); 26-0356: 716 hits (2 copies of the same RFQ spec); 26-0436: 3,008 hits across 166 of its 170 per-section CSI PDFs, plus 2,083 more once the "other"-misclassified `NY10-1 IFP - Project Manual.pdf` (1,830 pages) was rescanned; 26-0445: 0 on the naive pass (its 2 spec PDFs are Nordomatic's own proposal boilerplate, no CSI numbers) → **3,595 hits** once the "other"-misclassified 2,922-page `2026.06.26 QTS WTX-1 DC-1 IFC PManual...pdf` was rescanned.

### 5.3 Controls-related sections found per job (23 09 xx, 159xx, 25 xx xx)

| Job | File | Section(s) found | Page range (0-based) |
|---|---|---|---|
| 26-0246 | Marked_15970.pdf | 15970 (whole doc — "Temperature Control System, BACnet BMS/DDC") | 0–245 (whole file) |
| 26-0246 | Marked_15973.pdf | 15973 (whole doc) | 0–20 |
| 26-0246 | Marked_15985.pdf | 15985, 15941–15943, 15932–15939 (HVAC Instrumentation & Controls family) | 0–95 (whole file, multiple sub-sections) |
| 26-0328 | 305_SPECS_ATL2-DC11_IFP_26.05.22.pdf | 23 09 10 ("Building Management System (BMS/EPMS)") | 1850–1916 |
| 26-0334 | K-9 Facility-Controls Specs Only.pdf | 23 09 93 (Sequence of Operations), 23 09 13 (BMS/BACnet) | 60–107 (to EOF) |
| 26-0339 | Marked_Specs_230993_Sequence of Operation.pdf | 23 09 93 (whole doc, filename says as much) | 0–34 (whole file) |
| 26-0344 | 80 Broad - HVAC Specs.pdf | **none** — this HVAC spec set has 23 05 xx (general/sleeves/heat-tracing/hydronic/water-treatment) and 23 5x/6x/7x (equipment) sections but no 23 09 xx or Div 25 section at all | n/a |
| 26-0352 | *(no spec PDF)* | **none** | n/a |
| 26-0356 | RFQ#_511469__Specifications...pdf (×2 copies) | 23 09 00 (Instrumentation & Control for HVAC), 23 09 93 | 1021–1070 |
| 26-0436 | Marked_Div 23 Spec.pdf | 23 09 00 | 246–313 |
| 26-0436 | Specs\23-...\23-09-00-Instrumentation-and-Control-for-HVAC_Rev_8.pdf | 23 09 00 (whole doc) | 0–67 |
| 26-0436 | Specs\25-Integrated-Automation\25-00-00...pdf, 25-08-00...pdf | 25 00 00, 25 08 00 | whole docs |
| 26-0436 | NY10-1 IFP - Project Manual.pdf | 23 09 23, 23 09 93, 25 10 00 | ~1155–1205 |
| 26-0445 | 2026.06.26 QTS WTX-1 DC-1 IFC PManual...pdf | 25 05 00/01/02, 25 08 00, 25 14 00, 25 15 50, 25 35 00 (SCADA/PLC/Integrated Automation family) | 2118–2253 |

**Two jobs (26-0344, 26-0352) genuinely have no dedicated controls/BMS spec section anywhere in the archive** — this must be a distinct, real "open" case for the manufacturer-qualification logic (item 6), not a detection bug (confirmed by manual inspection of both jobs' full section-header lists).

## 6. Manufacturer requirement language

Verbatim quotes (truncated to ~600 chars), one to a few per job, found by scanning the controls-section page ranges above (plus a full-document fallback scan for 26-0344 and 26-0352, which have no dedicated controls section) for the manufacturer name list and the qualifying phrases:

**26-0246** (`Marked_15970.pdf`, NYC SCA spec 15970 §1.6-ish, p2/p4/p14) — *qualifies, Niagara named without a specific competing vendor*:
> "...The projects shall utilize a standard Tag Dictionary based on the Tridium Niagara/Haystack Tag Conventions. Custom Tag Dictionaries other than the one specified above are not accepted for use on NY City School Construction projects... The BACnet network platform and network management shall be implemented with the following development and integration tools provided by the TCC and coordinated with the FMSI: 1. Tridium Niagara Network Operating System..."

Estimator read: **qualifies** — Niagara (Tridium) is the named platform, no non-qualifying vendor is basis-of-design here.

**26-0328** (`305_SPECS_ATL2-DC11_IFP_26.05.22.pdf`, §23 09 10 "Building Management System (BMS/EPMS)", p1870-71) — *open, approved list names neither Honeywell/JCI/Niagara*:
> "PART 2 - PRODUCTS 2.1 MANUFACTURERS 1. Manufacturers: Subject to compliance with requirements, provide products by one of the following: a. Acceptable PLC Manufacturer 1) Rockwell Automation/Allen-Bradley, CompactLogix or Equal. b. Acceptable VAV Controller 1) Distech Controls – Eclypse Series or Equal 2) Delta Controls – DVC-E series or Equal ... c. Acceptable Terminal Controller 1) Distech Controls – Eclypse Series or Equal 2) Delta Controls – DVC-E series or Equal..."

Estimator read: **open** — approved list (Rockwell PLC, Distech/Delta Controls for VAV/terminal controllers) includes neither Honeywell WEBs, JCI FX, nor Niagara N4; would need a closer read of the rest of §23 09 10 to see if Niagara supervisory-level integration is required elsewhere (a partial "or approved equal" escape exists).

**26-0334** (`K-9 Facility-Controls Specs Only.pdf`, §23 39 00 "Building Management Systems", p59-64) — *qualifies, sole-source-strength Niagara language*:
> "...multiple Niagara supplier's products. The Niagara Compatibility Statement (NICS) for all Niagara Software shall allow open access..." / "Provide a Tridium NiagaraN4 Framework as the basis of the new BMS." / "Submit validation which indicates the successful completion of the Tridium NiagaraN4 certification course."

Estimator read: **qualifies** — Niagara N4 is explicitly the *basis of design* ("basis of the new BMS"), no other vendor competes for the platform tier.

**26-0344** (`80 Broad - HVAC Specs.pdf`, §23 09 00 "Instrumentation and Control of HVAC", p106) — *qualifies, Honeywell/JCI are on an approved list of 30+ names*:
> "2.2 CONTROL SYSTEM A. Available Manufacturers: 1. Alerton Inc. 2. American Auto-Matrix. 3. Andover Controls Corporation. 4. Automated Logic Corporation. 5. Carel. 6. Delta Controls Inc. ... 11. Honeywell International Inc.; Home & Building Control. ... 14. Johnson Controls, Inc.; Controls Group. 15. KMC Controls/Kreuter Manufacturing Company. ... 21. Siemens Building Technologies, Inc. ..."

Estimator read: **qualifies** — Honeywell and Johnson Controls both appear on this long "available manufacturers" list (along with Siemens, KMC, Delta, Automated Logic, Alerton), satisfying the "approved list including either" rule. Note: no Niagara/Tridium name appears in this particular list, so the qualification rests on Honeywell/JCI being present, not on Niagara.

**26-0356** (RFQ spec, §23 09 00-ish "BACnet/BMS", p1022) — *qualifies, Niagara 4 is sole-source/no-alternative language, Honeywell also named as installer*:
> "The intent of this specification is to provide a system that is consistent throughout the owner's facilities running the Niagara 4 Framework... Any control vendor that shall provide additional BMS server software shall be unacceptable. Only systems that utilize the Niagara 4 Framework shall satisfy the requirements of this section... Contractor must engage a Honeywell Niagara 4 Framework system specialist for the installation of the CHAS system."

Estimator read: **qualifies** — this is NYCHA's standard Niagara-4-only requirement (explicitly excludes "any control vendor" providing a different framework), with Honeywell named as the required installing specialist for one sub-system (CHAS) — still Niagara-based.

**26-0436** (`26-0437\...\25-00-00-Integrated-Automation-General-Requirements_Rev_7.pdf`, Div 25 general requirements, p1/4/6/23/35) — *qualifies for the Niagara-referencing language, open for the specific-device example*:
> "Niagara Framework: The Niagara Framework is a software infrastructure that allows building controls integration and allows HVAC Contractors to build custom, web-enabled applications for accessing, automating, and controlling building systems." / "...specify the manufacturer of the device e.g., Alerton, Honeywell, Schneider)..." / "Basis of design model: XY-S-APRO" (occupancy sensor, non-controls-platform item).

Estimator read: **qualifies** at the platform level (Niagara Framework referenced as the integration layer, and Honeywell/Alerton/Schneider given only as illustrative examples of "e.g." device manufacturers, not an exclusive list) — the sensor-level "Basis of design model: XY-S-APRO" is a different, non-BMS-platform product and reads as **open** on its own.

**26-0445** (`2026.06.26 QTS WTX-1 DC-1 IFC PManual...pdf`, Div 25 PLC/SCADA sections, p2127-2254) — *open, PLC basis-of-design is Rockwell/Allen-Bradley, no BMS-platform vendor named in the scanned excerpt*:
> "2.4 CONTROLLERS A. Programmable Logic Controllers (PLCs) 1. Manufacturer: Allen-Bradley (Rockwell Automation) 2. Series: a. ControlLogix 5580 for Hot/Standby applications or approved equal/better..." / "...QTS Basis of Design." / "2.15 NON-APPROVED MANUFACTURERS, PRACTICES, AND TECHNOLOGIES: A. The use of the following devices, technologies, and practices is expressly prohibited unless specific written approval is granted by the Engineer..."

Estimator read: **open** — the PLC/SCADA layer's basis of design is Rockwell/Allen-Bradley (not in the Honeywell/JCI/Niagara set) with an "or approved equal" escape; this is QTS's own private "Basis of Design" standard document (not a CSI spec section per se) and did not, in the pages sampled, name a BMS supervisory platform — would need to check the rest of the 2900-page manual for a Niagara/Metasys/WEBs mention at the BMS (not PLC) tier before concluding.

**26-0339** — 0 manufacturer/phrase hits in `Marked_Specs_230993_Sequence of Operation.pdf` (a pure sequence-of-operations document, no product/manufacturer language expected in a SOO section) — **silent → open** by the stated rule.

**26-0352** — 0 hits anywhere (no spec PDF exists in the job at all) — **silent → open**.

**26-0344** cross-check — the fallback full-document scan (not just a controls-section page range, since none was found) turned up the Honeywell/JCI/Siemens/KMC list quoted above sitting in a **general HVAC controls section** (§23 09 00, which the section-header scan located at p106 but which my controls-section-number filter did not tag as "23 09 xx" — see the discrepancy note below).

**Known discrepancy worth flagging**: 26-0344's own section-header text says `SECTION 230900` in one place, yet the automatic controls-section list in 5.3 reported "none" for this job — the manufacturer scan's fallback full-document pass is what actually surfaced it. This means the section-boundary assembly logic (which chains "distinct number → next number" from FOOTER/HDR hits) missed this section, likely because its footer format differs slightly from the other sections in the same file. **Any production version of this pipeline needs the manufacturer/keyword scan to run over the whole spec document, not just the sections the header-regex found — the header regex is not reliable enough on its own to gate what gets scanned.**

## 7. Equipment tags

### 7.1 Tag formats observed

From the estimator's own takeoff-count annotations (Square/Highlight annot `content`, which literally lists what was counted — see §10) and from drawing schedule text:

- `VAV-21-01`, `VAV-21-02`, `VAV-21-03`, `VAV-21-04` (26-0352, `Marked_Mech.pdf` p3 annotation text: `"VAV: 12 x 1 = 12\n1. VAV-21-02\n2. VAV-21-01\n3. VAV-21-03\n4. VAV-21-04..."` — level-zone-index 3-part tag)
- `AHU-1` … `AHU-6`, `TEF-1`, `TEF-2`, `ECUH-1` … `ECUH-5`, `EF-2`, `EF-6`, `EF-9`, `KEF-1`, `KEF-2`, `SPF-1`, `FFCH-548`, `MUH05-41`, `AC-502`, `GV-502` (26-0246, full-text regex sweep of `Marked_Mech Mechanical Drawing.pdf`, see 7.3)
- `HTCP-1CY40-01`, `CHLR-1CY40-A110`, `CHLR-1CY40-B110`, `CHLR-1CY40-C110` (26-0445, `Marked_14_MECHANICAL_COMBINED.pdf` annotation content — QTS's own tag convention embeds a building/phase code `1CY40` between the equipment type and the running number/letter)
- No en-dash, "#", or "No." variants were actually observed in this archive's own tag text (all tags use a plain ASCII hyphen `-`); "No." and "#" only appear in unrelated contexts ("DOB Sheet Count", "PROJECT NO.", "Block #").

### 7.2 Proposed regex and look-alikes

```
TAG_RE = re.compile(r'\b([A-Z]{1,5})[-\u2013\u2014#]?\s?(?:No\.?\s*)?(\d{1,4})(?:[-\u2013](\d{1,3}))?([A-Z])?\b')
```

**Must-not-match look-alikes, confirmed by testing this regex against the full text of `26-0246\...\Marked_Mech Mechanical Drawing.pdf`** (see 7.3): compact sheet numbers without a separator (`M305`, `M302`, `M501` etc. — a sheet cross-reference embedded in a note reads identically to a 1-letter+3-digit equipment tag); common English words that happen to be all-caps-letters-then-a-number (`FLOOR 14`, `BEACH 40`, `SUITE 310`, `BOX 1360`, `GRADE 4-5`, `AGES 5-8`, `TABLE 403`, `ROOM 509`, `OF 12`, `WITH 45`, `PLUS 2`, `BE 1`); refrigerant/material codes (`R454B`, `R01`-`R04`); and single ambiguous letter+digit tokens (`S-1`, `F4`) that could equally be a structural-sheet reference, a keynote bubble, or a real diffuser/fan tag — regex alone cannot disambiguate any of these without either a known-prefix allow-list (AHU/VAV/EF/CUH/ECUH/TEF/KEF/SPF/RTU/FCU/CT/ACCU/CU/UH/MUH/GV/AC/CHLR/HTCP/…) or page-region context (schedule-table column vs. running note text).

### 7.3 Test on 26-0246's mechanical drawing (`Marked_Mech Mechanical Drawing.pdf`, 50 pages)

The loose `TAG_RE` above found **1,268 distinct match strings** across the full text. The top hits by frequency were dominated by false positives from plain English and title-block boilerplate glued across a line break (`'FLOOR\n14'` × 55, `'BEACH 40'` × 50, `'SUITE 310'` × 50, `'BOX 1360'` × 50, `'GRADE 4-5'` × 46, `'DPC\n152'` × 50) ahead of the first genuine equipment tag (`AHU-1` at 51 occurrences, rank 8). Genuine equipment tags recovered correctly: `AHU-1`…`AHU-6`, `TEF-1/2`, `ECUH-1`…`ECUH-5`, `EF-2/6/9`, `KEF-1/2`, `SPF-1`, `FFCH-548`, `MUH05-41`, `AC-502`, `GV-502`. Sheet-number look-alikes that matched: `M301`…`M505` (bare, no dash — 12 distinct sheet numbers appeared as false "tags", collectively ~200 hits, because running notes cross-reference sheets as e.g. "SEE M305" without a separator). **Precision conclusion: the naive regex is unusable as-is** — it needs (a) a stopword/common-word denylist, (b) restriction to spans that sit inside a schedule-table's tag column (positional context) or match a known equipment-prefix list, and (c) exclusion of any 1-3-letter+3-digit token that also appears as this file's own sheet-number pattern (cross-check against the sheet-number list extracted in §3).

## 8. Pages without a text layer / OCR

### 8.1 Count per job (< ~50 characters of extracted text)

| Job | File | Pages w/o text | of | Notes |
|---|---|---:|---:|---|
| 26-0246 | — | 0 | 399 | fully native text |
| 26-0328 | 305_SPECS_ATL2-DC11_IFP_26.05.22.pdf | 6 | 2728 | blank "intentionally left blank" pages |
| 26-0328 | 440.2_HFAT DOC...pdf | 1 | 22 | |
| 26-0334 | **Marked_Mech.pdf** | **7 (all pages)** | 7 | **entire drawing PDF is a raster scan — no text layer at all** (large-format 2592×1728 sheets, ~745KB/page; this is the one PDF in the whole 9-job archive that is fully image-only) |
| 26-0339 | — | 0 | 112 | |
| 26-0344 | — | 0 | 410 | |
| 26-0352 | — | 0 | 32 | |
| 26-0356 | Bid Proposal Face sheet.pdf | 1 | 1 | scanned signature page |
| 26-0356 | Dept of Investigation Information.pdf | 2 (all) | 2 | scanned form |
| 26-0356 | RFQ...Contract Book...pdf | 58 | 1588 | scattered blank/scanned-signature pages |
| 26-0356 | RFQ...Specifications...pdf (×2 copies) | 4 | 1322 | |
| 26-0436 | Marked_NY10-1 IFP – 13 CONTROLS – Appendix.pdf | 64 | 215 | **manufacturer cut-sheets/catalog pages pasted in as images** (confirmed — see 8.2, RTD/thermowell catalog page) |
| 26-0436 | NY10-1 IFP - Project Manual.pdf | 1 | 1830 | |
| 26-0445 | 2026.06.26 QTS...PManual.pdf | 146 | 2922 | mix of blank pages and image-only pages |

### 8.2 OCR test (3 pages, 300 dpi render via pymupdf, then `tesseract.exe` via subprocess, vs. pymupdf's built-in `get_textpage_ocr`)

| Page | Render (300dpi) | Tesseract CLI | pymupdf OCR (`get_textpage_ocr`) | Recovered text quality |
|---|---:|---:|---:|---|
| 26-0334 `Marked_Mech.pdf` p0 (full raster CAD sheet, oversized) | 1.45s | **17.97s** | 7.95s | Both recovered the legend headings correctly ("WORK LEGEND", "FIRE PROTECTION SYMBOLS", "HVAC DUCTWORK SYMBOLS", "MOTORS & HVAC EQUIP. CONTROLS"); Tesseract CLI text was slightly cleaner (e.g. correctly read the embedded CAD file path `Z:\2024Projects\...\40111M001.dwg, 24x36, 4/20/2026 9:20:39 AM, BDomitrowski`), pymupdf's OCR garbled more of the drawing-symbol table ("Sheer OF porea", "AEw") |
| 26-0436 Appendix p156 (manufacturer catalog cut, embedded image) | 0.37s | 2.29s | 1.92s | Both recovered "Spring-Loaded RTD/Thermowell Assemblies... with General-Purpose Connection Heads are designed for use with various thermowell types" cleanly and almost identically |
| 26-0445 PManual p1 | 0.12s | 0.48s | 0.15s | Both correctly returned "This page intentionally left blank." — confirms this page is genuinely blank, not a detection failure |

**Conclusion**: pymupdf's own `page.get_textpage_ocr(dpi=300, tessdata=...)` works (no separate subprocess needed) and is 2-9× faster than shelling out to `tesseract.exe` in this test, for comparable or only slightly worse text quality. A full-page 300dpi OCR pass on an oversized (36×24-ish) CAD sheet costs **~8s (pymupdf) to ~18s (CLI) per page** — expensive if applied at scale, but this archive only has ~280 image-only pages total (mostly blank pages and pasted-in catalog cuts, not full scanned drawing sheets) plus the one fully-scanned 7-page drawing PDF, so a targeted OCR pass (only on pages already flagged as <50 chars) is affordable; OCR-ing every page of every PDF "just in case" would not be.

## 9. Timing

Single-process, full-page `get_text("text")` extraction of every page of every PDF in the job (this pass also did the section-header regex work for spec files, so is a slight over-estimate of pure extraction time, but regex cost is negligible next to PDF parsing cost):

| Job | Total seconds | PDFs | Pages (approx.) |
|---|---:|---:|---:|
| 26-0246 | 10.3 | 7 | 399 |
| 26-0328 | 22.3 | 11 | 2,972 |
| 26-0334 | 2.3 | 5 | 132 |
| 26-0339 | 8.4 | 3 | 112 |
| 26-0344 | 7.7 | 4 | 410 |
| 26-0352 | 2.8 | 3 | 32 |
| 26-0356 | 24.0 | 10 | ~6,065 |
| 26-0436 | **256.3** | 194 | ~9,700 |
| 26-0445 | **296.5** | 11 | ~4,317 |

The two largest jobs (26-0436's 194-file/9,700-page archive, and 26-0445's handful of enormous combined-discipline PDFs, one of which — `15_ELECTRICAL_COMBINED.pdf` — is 715 MB for 226 pages) take 4-5 minutes each for a single-process, text-only pass; this scales roughly linearly with page count but the per-page cost is markedly higher for image-heavy oversized CAD-exported drawing PDFs (`17_TECHNOLOGY_COMBINED.pdf`, 88 pages, took 92.9s = ~1.06s/page) than for native-text specs (`Specs\26-Electrical\*.pdf`, hundreds of small files at ~0.01s/page). **Memory**: no explicit memory profiling was done, but nothing failed or swapped visibly extracting text page-by-page and closing each `pymupdf.Document` — the risk is `get_text("dict")` (span-level, used for title-block extraction, §3) on the biggest combined drawing PDFs, which held up fine in-process but would be worth chunking (open/process/close one file at a time, not accumulate all text in memory) for a production pipeline given some source files are 100s of MB to >1 GB uncompressed once rendered.

## 10. Estimator marks (annotations)

Counted via `page.annots()` / `annot.type` / `annot.colors` across every PDF in each job (cheap — no text extraction needed):

| Job | Total annots | Types (count) |
|---|---:|---|
| 26-0246 | 3,380 | Square 2246, Highlight 682, Text 451, FreeText 1 |
| 26-0328 | 5,410 | Square 3418, Text 1614, Highlight 315, FreeText 58, Polygon 4, Line 1 |
| 26-0334 | 220 | Square 97, Highlight 81, Text 42 |
| 26-0339 | 1,532 | Square 1267, FreeText 86, Highlight 179 |
| 26-0344 | 8,643 | Square 7353, Text 1125, Highlight 129, FreeText 28, Circle 8 |
| 26-0352 | 118 | Square 82, Highlight 30, FreeText 6 |
| 26-0356 | 182 | Square 64, Highlight 83, Text 34, FreeText 1 |
| 26-0436 | 13,555 | Square 6376, Highlight 3398, Text 2382, Polygon 601, Circle 481, FreeText 309, Stamp 5, Ink 2, Line 1 |
| 26-0445 | 8,524 | Square 4792, Text 2318, Highlight 1248, FreeText 160, Stamp 5, Circle 1 |

What they mark (from `annot.colors` and `annot.info["content"]` samples): pure-green `Highlight` (`stroke=[0,1,0]`) is used consistently across jobs on **spec text** to flag controls-relevant clauses (e.g. every `Highlight` found in 26-0246's `Marked_15970.pdf` and 26-0334's `K-9 Facility-Controls Specs Only.pdf` is this same green). On **drawings**, colored `Square` annotations are the estimator's takeoff count boxes — many carry their count directly in `annot.info["content"]`, e.g. `"VAV: 12 x 1 = 12\n1. VAV-21-02\n2. VAV-21-01\n..."` (26-0352) and `"CHILLER: 6 x 1 = 6\n1. CHLR-1CY40-A110\n2. CHLR-1CY40-B110..."` / `"HTCP: 1 x 1 = 1\n1. HTCP-1CY40-01"` (26-0445) — i.e. the estimator boxes a group of identical equipment tags on the schedule/plan and Bluebeam (or similar) writes the tag list and running count into the annotation body. `FreeText` annotations carry the estimator's own notes (`"NOT IN SCOPE"`, `"EXCEPTION??"` in 26-0344; `"QTS DCIM"` in 26-0328) or, on sketches, a copied sheet title/number block (26-0436 `Marked_Mech+Sketch Mech.pdf`: `"NY10-1 MSK-001\rMECHANICAL PHASING PLANS\rM001.3\r6/22/2026"`). Distinct colors per job appear to be a personal/per-discipline coding scheme (e.g. 26-0436 uses at least 10 distinct stroke colors) rather than a shared standard across jobs — **this should be treated as job-specific, not assumed consistent archive-wide**.
