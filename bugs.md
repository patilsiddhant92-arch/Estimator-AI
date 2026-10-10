# Estimator AI — bug register

Audit date: 2026-10-07. Branch audited: `rebuild` at commit `4b019e0`. Nine read-only reviewers each read one
subsystem in full, reproduced every finding they could on invented fixtures, and reported. The lead spot-checked
the highest-impact findings against the source. No code was changed by the audit. The full suite at this commit
passes: 3,396 tests (one intermittent timing failure, see TST-1).

Progress 2026-10-07 (lead): 125 FIXED, 3 WONTFIX (VAL-8, RND-4 by ruling D1; LDG-11 old planner only), 1 open (VAL-11, waits on ruling D3). Final suite on rebuild: 3773 passed. Follow-ups found while fixing: section 4b.

Totals: 128 bugs (AI-15 is a cross-reference to RUN-8). By priority: 34 P0, 60 P1, 34 P2. By status: 119
CONFIRMED, 9 LIKELY. PBK-10 and RUN-12 each bundle several small items under one id.

What was audited: the live app, `src/bms/` and every `src/estimator/` module it imports (catalogue, reading,
ledger, dossier, proposal, price_sheet, evidence workbook, scope), plus `playbook/`, `src/bms/prompts/`,
`tools/run_job.py`, `tools/measure.py`, `tools/chat_guard.py`, `tools/chat_post.py`, `.claude/run-job.json` and
the run-job skill. Not audited: the old writing layer (`estimator.writing.assemble/write/systems/whole_job/
front_end/style/qc/brief/templates/house_check/phrasing`, `estimator.corrections`, `estimator.score`,
`estimator.sent`, the old CLI). It is the retired app and is out of scope.

---

## 1. How to work this list (read before fixing anything)

**Who fixes.** Opus or Sonnet agents, one bug or one tight cluster per task, in their own worktree and branch made
from `rebuild` (AGENTS.md rule 2). Test-first: write the test named under "Test to add" and watch it fail, then
fix, then run the whole suite with `PYTHONPATH=src .venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider`
(about 3,400 tests, 3 to 5 minutes on an idle machine). Report DONE in `Colab/chat.txt` with branch, commit and
the test count (rule 6).

**Hard limits.**
- Never open `out/`, `Jobs/`, `.superpowers/`, `.claude/worktrees/`, `scratch_verify/` or any real bid folder.
  Repro everything on `tests/bms/fixtures/`, `tests/data/26-0246` and synthetic PDFs from `tests/pdfs.py`.
- Do not edit `playbook/rules.md`, `playbook/shapes.json` or `playbook/wording.json` (rule 4). Where a fix needs
  a Playbook change, the bug says so and the change is listed in section 3 for the estimator. Code the fix so
  that it reads the new key when present and keeps today's behaviour when absent, or wait for the ruling.
- Keep the public signatures in `docs/superpowers/specs/2026-10-04-rebuild-interfaces.md` (rule 5). Where a fix
  needs a contract change, the bug says "contract change" and the lead must approve it first.
- Some bugs are behaviour that an existing test asserts on purpose. Those tests are named in the bug. Do not
  change such a test without the ruling in section 3; otherwise the fix will be reverted at review.

**Status key.** CONFIRMED: the reviewer reproduced it or traced the exact code path. LIKELY: strong reading, not
reproduced. **Priority key.** P0: an undercount, a silent data loss, a crash on the normal run path, or job data
written into the repo. P1: wrong text or wrong numbers in the proposal, price sheet, Evidence Package or review
page; a decision from the review page applied wrongly; a false must_fix that steers the revise step wrong.
P2: a contract or documentation mismatch, a weak check, a minor case.

**Marking progress.** When a bug is fixed, change its Status line to `FIXED <branch> <commit>` and leave the rest
as a record. When a bug is ruled "not a bug" by the lead, change it to `WONTFIX: <reason>`.

**IDs.** Each bug has a short id by area so tasks can name it: RD (reading layer), LDG (ledger and dossier), PLN
(planner), CNT (counts cross-check), PBK (model and Playbook loader), VAL (validators and citations), AI (AI steps
and prompts), RND (renderer and outputs), RUN (run, review, status, tools), TST (test suite).

---

## 2. Priority order

Work top to bottom. Items on one line share a root cause or the same lines of code and should be one task.

### P0 — undercounts, data loss, crashes on the run path, NDA

| Id | One line |
|---|---|
| RD-1 | Schedules de-duplicated by sheet number alone: every "both counted" decision is undone for schedule sheets |
| RD-2 | Full-page OCR of a rotated scanned sheet loses about a third of the sheet, no flag |
| RD-3 | A reissue of a plan printed alike on N pages loses the floor multiplier |
| RD-4 | Copy rule ignores type-tag placements: a set that shows more units is dropped as a copy |
| RD-5 | `label_key` merges VAV-1-11 and VAV-11-1 |
| LDG-1 | Two sequence sections with one heading collide: a system loses its sequence, no question |
| LDG-2 | A bracketed id in document text lets the AI cite it; the run then crashes on every rerun |
| LDG-5, LDG-6 | Seed regexes drop devices whose name has brackets and cut the counts quote at "Bldg." |
| LDG-7, LDG-8 | Plan-sheet text keyed by sheet number: spaced numbers, unnumbered sheets, second buildings and reissues lost or wrong |
| LDG-9 | Keynotes de-duplicated without their document |
| PLN-1 + LDG-4 | Tags a later pass adds to a family are dropped (planner reads no contradictions; `_take` keeps none for `unit`) |
| PLN-2, PLN-5 | Damper links: a non-MD damper is credited to the MD family (MD undercounted); non-MD damper families never move under their fan |
| PLN-3 | Rebuilt counts cite the old number, drop the other counts and raise no question (five places) |
| PLN-10 | A count of 0 prints 0 although the family lists tags |
| CNT-1, CNT-2 | An unknown count becomes 0 from a note-only mention or from a vision answer whose boxes are dropped |
| CNT-3 | Tag search matches inside a longer tag; a combined pattern lets one family take another's tags |
| CNT-6 | Micro-crop path stops the vision count from being independent; text boxes labelled as "counted on the sheet picture" |
| CNT-8 | A raster plan with a vector title block is never counted by vision |
| AI-1 | `rewrite_for_count` can never apply the changed count to the lines already written |
| AI-3, AI-4, AI-5 | Quantity refs never checked; revised quotes never checked; empty source id counts as known |
| RUN-1 | A family Accept saved after a count change silently puts the old count back |
| RUN-3 | A vision-count question refused `max_attempts` times is swallowed; the run goes on with the text count |
| RUN-4 | Print error, locked file or missing job folder: traceback, run state "running" forever |
| RUN-6 | `tools/run_job.py status` deletes answers the run never read and counts them as rejections |
| RUN-11 | Nothing stops `--out` or `--cache` from pointing into the repo (NDA) |
| RND-1 | Price book never strips the renderer's " (Qty. N Total)": every line with its own total goes PRICE PENDING |
| RND-3 | Drafts that cannot be printed fail with something other than RenderError (crash, state "running") |

### P1 — wrong output, decision bugs, false must_fix

| Id | One line |
|---|---|
| RD-6, RD-7, RD-10, RD-11 | Drawing index job-wide by number; revision dates: wrong pattern wins, dates inside words; raw sheet-number compare; addendum with two same-numbered sheets |
| RD-8, RD-9 | Takeoff folder as input skips "Electrical" and never reads a revision folder; addendum recognised by file name only |
| LDG-3 | A may-only-add pass can remove the "confirm it exists" flag from a plan-only family |
| LDG-10 | Two documents with the same file name give identical citations |
| PLN-4 | Systems matched by bare prefix: a group holding one EF tag takes other EF tags' dampers, exceptions and control |
| PLN-6, PLN-7, PLN-8 | VRF group split into blocks; lone split unit loses its shape when pumps join; prefix beats family name (DH into Duct Heaters, Air Curtain into Split) |
| PLN-9, PLN-11 | Group-member multiplier forms drop the member or take the whole family; a later group listing a family whole loses it |
| CNT-4, CNT-5 | Stacked-line check invents tags; the located-text count has its own label rules that contradict the guide |
| CNT-7 | A vision answer leaving out every pattern is accepted and never asked again |
| CNT-9, CNT-10 | Prompt tells the "independent" count what to expect; stale proof entries published under a reused id |
| PBK-1 | Wording forms never checked: a Playbook typo crashes the render or prints wrong client text |
| PBK-2 | Citation check depends on where a rule sits in rules.md |
| PBK-5 | Loader refuses UTF-8 with BOM; lint reads it; a BOM leaks into AI instructions |
| VAL-1 to VAL-5, VAL-9 | False must_fix: valid Wire / Install and Wire lines; AME devices on packaged units; damper blocks; sequence-only test; trio on an empty block; header forced up to a line total |
| VAL-6 + RND-8 | `no_scope_reason` ignored: "the writer gave no reason" and the reason never reaches the Evidence Package |
| VAL-7 | A shape name not in the Playbook validates clean, then the renderer raises |
| VAL-8 + RND-4 | A block prints several "*" lines; validate counts only `clarifications` (needs ruling D1) |
| VAL-10, VAL-11, VAL-12 | Verb never checked against the owners; sub-line ownership not compared with parent; VRF/split splits and repeats not caught |
| VAL-13, VAL-15, VAL-18, VAL-19 | Empty `where` passes; unknown device quantity unflagged; value None with others; point lines on VRF |
| AI-2 | `_put_back` matches by id only: an added line is lost and a kept line duplicated |
| AI-6, AI-17, AI-18 | Evidence: a system with no plan sheets gets every plan device; other systems' integration passages; no `sections_in` fallback |
| AI-7, AI-8, AI-9 | API mode: passing retry cached under the retry prompt; schema-invalid answer uncounted and re-asked forever; chat refusal reason erased on a repeated run |
| AI-10 | Revise can change clarification, tech hours and no_scope_reason with no finding about them |
| AI-11, AI-12, AI-13 | Prompts contradict the Playbook on integration lines, default ownership and the relay line (needs ruling D5) |
| RND-2 | A "(Qty. ##)" line inside a block with a known count is unpriced and unflagged |
| RND-5, RND-6 | A higher count can print with no count named; clauses past five dropped; multi-family note unlabelled; count causes vanish when a sheet source exists |
| RND-7 | Evidence Package quantity disagrees with the proposal; other counts lose id and quote |
| RND-9, RND-10, RND-11, RND-12 | Alternates all "ALT #:"; title-casing makes NO/IT/CO acronyms; any device matching any shape's fixed wording loses verb and owner; assumption checked before cleaning |
| RUN-2 | After a count change, any later rename or delete on that system asks the writer again |
| RUN-5 | A device decision on a system the job no longer has is skipped with no card |
| RUN-9 | Run state keeps the old decision count after both decision files are deleted: false "history lost" note |

### P2 — contract, docs, weak checks, minor

| Id | One line |
|---|---|
| RD-12 to RD-15 | Image-covers-half ignores rotation; numberless typical sheet; unreadable-page count without document; unopenable file stops cataloguing |
| LDG-11 to LDG-15 | Old planner ignores counts-line clauses; empty passes still asked; file openers leak library errors; spec vs code; dossier picture cache by size and mtime |
| PLN-12 | Sheet "TAG ×N" reader does not accept the other multiplier forms |
| CNT-11 | A family whose tag is only its prefix is never checked |
| PBK-3, PBK-4, PBK-6 to PBK-10 | "decision not honored" rule not in rules.md; kind word with punctuation never matches; wrong loader line numbers; sample marker variants; malformed headings; `shape_for` specificity; minor items |
| VAL-14, VAL-16, VAL-17, VAL-20, VAL-21 | 160-character limit unenforced; invisible format characters split an id; ids with 5+ digits; misfiled rule names; "Words the client never sees" unchecked |
| AI-14, AI-15, AI-16 | Chat mode "another model makes a new question" is false; run_job attempt counter never resets (= RUN-8); phantom QC device id unlocks the whole block |
| RND-13, RND-14 | `integration_trio.depths` unused; client wording hard-coded in render.py |
| RUN-7, RUN-8, RUN-10, RUN-12 | run_job crashes on cp1252 console; attempt counter never resets; missing "Wrote" lines; smaller items (locked decisions file, no-op decisions, lost final state write, doctor too lenient, chat_guard restore) |
| TST-1 | Growth-timing tests are flaky under machine load |

---

## 3. Rulings needed before certain fixes (lead and estimator)

**Rulings given by the estimator, 2026-10-07:**
- D1: separate "*" lines per kind are fine; amend rules.md to allow it (count note its own line); today's render
  and its tests stay. VAL-8 and RND-4 become WONTFIX-by-ruling once rules.md is amended. D6 (ruled 2026-10-07):
  the count note lists EVERY other count (no five-clause cap; an unlabelled count still prints, e.g. "15
  elsewhere in the documents"), still on its own "*" line. RND-5 to be fixed that way.
- D2: the Playbook wins; rewrite the named tests to the Playbook's words.
- D3 (ruled 2026-10-07): the integration trio is standard practice and always comes together when controls are by others: comm wiring, map points, and the rep-assist sub-line "AME requires mfr. Rep to assist in integration, cost to be incurred by mech contractor". The rep-assist sub-line is owned by the mechanical contractor under an AME parent: integration sub-lines are exempt from the parent-ownership match; every other sub-line matches its parent.
- D4: fix the docs: lint accepts a named list of run-level rule names; rules.md untouched.
- D5: accepted; show the estimator the new prompt wording when done.
- D7: fix the docs (USER-GUIDE and the stop message), no contract change.
- D8: "M-101", "M101", "M 101" are the same sheet (one canonical key; keep the dot in "M-1.01"). Naming is
  usually standard within one drawing set. When a sheet is cited, give its page beside it: "M-101 (pg.56)"
  (citation-format request: check where the `where` texts are built before changing).
- D9: accepted (value is the highest whenever any count exists; Evidence Package prints the same).
- COUNT RULING (2026-10-09, the estimator; narrows D9; audit DOC-1..4, PLAN-1..5): the equipment schedule is the
  primary source of truth. When a schedule gives a count (`Count.basis` "schedule"), the schedule's quantity prints
  and is the working count; plan, riser and vision counts verify it, and every difference is a flag per
  Brain/Quantity rules.txt (DISCREPANCY beside a schedule; a duplicate tag row on a schedule is a DISCREPANCY), shown
  in the counts evidence, never silently raising or lowering the count. Only with no schedule does D9 hold: the
  highest supported count prints, flagged (CONFLICT). Playbook rules "The schedule count prints" and "Never change a
  count silently" replace "Higher count prints" and "Never undershoot".

These are not code the fixer can decide alone. Each names the bugs waiting on it.

- **D1. One "*" line per block (VAL-8, RND-4, RND-5).** `rules.md` "One clarification per block" and "Joining
  into the one clarification" say every part (confirm, assumed, per drawings, the quantity note, client notes) is
  joined into one clarification of one kind. `wording.json` `$format.quantity.others_note` and five render tests
  (`test_rooftop_block_golden`, `test_one_star_line_per_kind_in_a_fixed_order`,
  `test_count_note_is_one_line_per_block_beside_the_confirm`, `test_confirm_note_and_count_note_for_vrf`,
  `test_unknown_count_prints_hashes_and_quantity_unknown`) encode one line per kind plus a separate count note.
  Ruling: follow rules.md (recommended; it is the estimator's approved method) and add lead-word forms
  (`assumed_part`, `note_part`, `unlabelled`, `more_counts`) to `wording.json`; or amend rules.md to allow the
  count note as its own line.
- **D2. Validators that today assert the opposite of the Playbook (VAL-1 to VAL-5, VAL-9).** Tests encoding the
  current behaviour: `test_packaged_internal_device_and_trio_twice` (RTU.d4), `test_a_stand_alone_damper_block_is_must_fix`,
  `test_an_air_handler_with_a_damper_is_only_a_check`, `test_sequence_only_system_prints_no_count`,
  `test_a_device_quantity_above_the_header_count_is_must_fix`. Ruling: the Playbook wins (recommended); the fixer
  rewrites those tests to the Playbook's words.
- **D3. Sub-line ownership (VAL-11).** rules.md says a sub-line carries the parent's ownership; the sample fixture's
  `rep_assist` is Mechanical Contractor ×3 under an AME `map_points`. Ruling: exempt integration sub-lines, or fix
  the fixture.
- **D4. "decision not honored" finding rule (PBK-3).** Either add `### Decisions are honored` to rules.md (Playbook
  content, estimator) and a `RULE["honored"]` constant, or amend interfaces §2.2 to allow a named list of run-level
  rules that the lint exempts.
- **D5. Prompt text that contradicts rules.md (AI-11, AI-12, AI-13).** The prompts are code, not the Playbook, so
  the fixer may change them, but the estimator should see the new wording since it steers what the writer flags.
- **D6. Count-note clause cap and unlabelled counts (RND-5).** `wording.json` `$format` and
  `test_count_note_drops_clauses_with_no_label_and_keeps_five` cap the note at five clauses and drop unlabelled
  counts. rules.md says "every other count is named with where it is". Ruling as D1.
- **D7. Chat-mode question key and the model (AI-14).** Either add the configured step model to the chat key
  (contract change) or correct the USER-GUIDE and the stop message.
- **D8. Sheet-number canonical key (RD-10, RD-6).** Compare sheet numbers through one canonical form ("M-101",
  "M101", "M 101" equal; keep the dot between digits so "M-1.01" stays distinct). Touches revisions, job flags,
  title block and the drawing index. Approve once so the four fixes agree.
- **D9. `Count.value None` with other counts (VAL-18, RND-7).** `model.py` says None prints "Qty (##)"; the
  renderer prints `highest()`. Recommended: value is always the highest when any count exists (the planner and
  counts set it), None only when no count exists at all; the Evidence Package prints `highest()`.
- **Playbook content proposals (estimator, not bugs):** kind words or prefixes for Boilers, Chillers, Cooling
  Towers, Roof Top Units, Make-Up Air Units, Air Handlers, VAV boxes, Smoke Dampers, CRAC units (PBK-9 notes); move
  VAV below AHU or narrow its kind word; narrow "global" to "global point"; Fire / Smoke Damper interlock wordings
  that drop verb, owner and quantity (RND-11); sub-line forms without `{owner}` (RND-11); new wording keys listed
  under RND-14 and D1.

---

## 4. Bugs by area

### A. Reading layer — `src/estimator/catalogue`, `src/estimator/reading`

#### RD-1. Schedules are de-duplicated by sheet number alone
- **Where:** `src/estimator/reading/inventory.py:136-154` (`_one_copy_per_sheet`), called at `:682` from
  `build_inventory` with `other_sets(catalogue)`.
- **Status:** FIXED fix/rd1 1682e8e (merged a35878d). **Priority:** P0 undercount.
- **What happens:** `read_schedules` reads only the governing pages, and `governing_pages` keeps both documents'
  pages whenever it cannot prove one replaces the other. `_one_copy_per_sheet` then keeps only the first document
  per sheet number, dropping one schedule again. Case: base `Mech.pdf` has M-601 on p.1 (VAV schedule) and p.2
  (EF schedule); an addendum reissues only p.1 with a new VAV-4. `supersede` replaces p.1 and flags "unmatched
  page kept (p.2), counted". Then `_one_copy_per_sheet` drops the addendum's schedule and VAV-1 to VAV-4 vanish.
  In production the documents sort by relative path, so which schedule is lost depends on folder names. The same
  drop hits two undated versions ("summed, for now"), "may replace one of two", "another title than every other",
  and two documents sharing a schedule sheet number that fail the 3-sheet / 80% `other_sets` test.
- **Why wrong:** USER-GUIDE "When nothing says which one wins, both are counted" and "The other page is kept and
  counted". The guide keys everything by (document, sheet number). The drop flag names no counts.
- **Fix:** Once schedules come from governing pages, do not de-duplicate by number. Drop only (number, document)
  pairs that `repeats(catalogue)[1]` marks as marked-up copies:
  ```python
  def _one_copy_per_sheet(schedules, flags=None, copies=frozenset()):
      return [s for s in schedules if (s.sheet, s.document) not in copies]
  ```
  Pass `repeats(catalogue)[1]` from `build_inventory`. Remove the number-only branch.
- **Test to add:** new `tests/test_schedule_versions.py`: (a) base M-601 p.1 and p.2 plus addendum M-601 p.1 with
  tags; assert both VAV and EF families are in the inventory. (b) Two undated documents each with its own M-601
  listing different tags; assert both tag sets are present.

#### RD-2. Full-page OCR of a rotated scanned sheet loses about a third of the sheet
- **Where:** `src/estimator/catalogue/pdf.py:62-67` (`ocr_textpage` → `page.get_textpage_ocr(..., full=True)`),
  used by `register._read_page` and `visual_spans`.
- **Status:** FIXED fix/rd2 44b5c1d (merged 3ea6f4b). **Priority:** P0 undercount.
- **What happens:** An image-only landscape scan stored as a portrait page with /Rotate 90 or 270, 24 tags in six
  columns: rotation 0 reads 24; rotation 90 reads 16; rotation 270 reads 16 and loses the sheet number M-601
  (`edge_spans` empty). The missing columns are the strip beyond the page's unrotated width. Status stays "ocr"
  because 20+ characters came back, so nothing is flagged. `ocr_images_textpage` (full=False) reads a rotated
  pasted picture correctly.
- **Fix:** In `ocr_textpage`, for a rotated page render as viewed (`pix = page.get_pixmap(dpi=dpi)`), OCR the
  pixmap (`pymupdf.open("pdf", pix.pdfocr_tobytes(language="eng", tessdata=...))`) and build text and spans from
  that one-page PDF, scaling by `page.rect.width / ocrpage.rect.width`; positions are already as viewed, so do
  not apply `rotation_matrix` again. Or have `_read_page` compare the OCR character count of a rotated page
  against an unrotated render and flag a shortfall.
- **Test to add:** `tests/test_register.py`: build the sheet at rotation 0, 90 and 270 (skip when `tessdata()` is
  None); assert all 24 tags in `_read_page(...).text` and M-601 in `edge_spans` for every rotation.

#### RD-3. A reissue of a plan printed alike on N pages loses the floor multiplier
- **Where:** `src/estimator/reading/revisions.py` `supersede` (`_runs`, `_matched`); `inventory.plan_floors` /
  `_alike_pages`; `devices.typical_sheets` / `count_devices` (`floors_of`). All key floors to the base (document,
  number).
- **Status:** FIXED fix/rd3 c30b0ed (merged a3a0fd6). **Priority:** P0 undercount.
- **What happens:** `Mech.pdf` prints M-102 "HVAC TYPICAL FLOOR PLAN" on 3 identical pages (VAV-11, FCU-A ×2).
  Alone: VAV-11 = 3, FCU-A = 6. With an addendum reissuing M-102 once, `_runs` makes the 3 alike pages one run and
  replaces all 3; `plan_floors` still gives floors only to the base key, so the addendum page counts ×1: VAV-11 =
  1, FCU-A = 2. Only output: "M-102: ... replaces ... — 1 change". No flag gives 3 and 1.
- **Fix:** In `supersede`, when the replaced run has more than one page and the reissue's run is shorter, carry
  the floors across (`Supersession.floors`, then `plan_floors` and `typical_sheets` give `(current.document,
  sheet)` the base's floor set). Or do not let a shorter reissue replace a whole multi-page run: keep the run, sum,
  and flag "addendum reissues M-102 (1 page); base prints it on 3 pages (3 floors): floors kept ×3; check".
- **Test to add:** `tests/test_final_o_counts.py`: the fixture above; assert `placements(...)["VAV-11"].count == 3`
  and `["FCU-A"].count == 6` after the reissue, and a flag names 1 page and 3 pages.

#### RD-4. The copy rule ignores type-tag placements
- **Where:** `src/estimator/catalogue/job.py` `_not_a_copy` (compares `_plan_units` with `if not is_type_tag(tag)`
  and a one-way word test).
- **Status:** FIXED fix/rd4 a138560 (merged a31c354). **Priority:** P0 undercount.
- **What happens:** `Mech.pdf` and `Rev 1/Mech.pdf` share M-101 to M-103, same titles, same unit tags; each Rev 1
  sheet labels EBB-A 4 times instead of 2. `document_repeats` returns `same=True`, only Mech.pdf is read, EBB-A
  is 6 instead of 12; flag says "probably a marked-up copy" with no counts. (Because of RD-8 every document has
  revision "base", so a real reissue in a subfolder reaches this rule instead of supersession.)
- **Why wrong:** USER-GUIDE: a copy is read once "only when it shows nothing the other lacks". More placements of
  a type, or stated counts, are things the other set lacks.
- **Fix:** In `_not_a_copy`, also compare `line_labels` per shared plan sheet:
  ```python
  for number in shared:
      la = sum((line_labels(text_of(original, number), keys)), Counter())
      lb = sum((line_labels(text_of(copy, number), keys)), Counter())
      if lb - la:
          return f"shows more labels of {', '.join(sorted(lb - la))}"
  ```
- **Test to add:** `tests/test_review_final7_counts.py`: assert `document_repeats(cat)[0].same is False` with a
  `why` naming EBB-A, and `placements(...)["EBB-A"].count >= 12`.

#### RD-5. `label_key` merges different tags (VAV-1-11 and VAV-11-1)
- **Where:** `src/estimator/catalogue/tags.py:264-278`.
- **Status:** FIXED fix/rd5 8162496 (merged a2ad04f). **Priority:** P0 (overcount and an undercount path).
- **What happens:** `label_keys(["VAV-1-11","VAV-11-1"])` gives `{'VAV111': 'VAV-1-11'}`;
  `line_labels("VAV-11-1", keys)` gives `{'VAV-1-11': 1}`. In `placements`, VAV-11-1 is never in `asked`, so its
  labels inflate VAV-1-11. In the copy test, a copy showing VAV-11-1 where the original shows VAV-1-11 passes "no
  unit the other does not show" and is dropped. `_Alike.label_counts` can call two different pages alike.
- **Fix:** Keep segment boundaries: after stripping noise, `re.sub(r"(?<=\d)[\s\-‐‑–—]+(?=\d)", "-", t)`, then
  remove the remaining dashes, spaces and `#` (so "VAV 1" and "VAV-1" still share a key).
- **Test to add:** `tests/test_tags.py`: `line_labels("VAV-11-1", label_keys(["VAV-1-11","VAV-11-1"])) ==
  Counter({"VAV-11-1": 1})`; "VAV 1" and "VAV-1" share a key.

#### RD-6. The drawing index is read job-wide, keyed by sheet number alone
- **Where:** `src/estimator/catalogue/job.py:42`; `title_block.read_drawing_index`, `index_key`.
- **Status:** FIXED fix/rd10 e900e42 (merged e77fbf9). **Priority:** P1 (undercount path through supersession).
- **What happens:** A sheet whose title block gives no title takes the first index title for its number found
  anywhere, possibly another building's cover sheet. Titles drive supersession and the copy test, so an addendum
  to A's M-101 can match B's sheet. `index_key` also merges "M-1.01" and "M-101".
- **Fix:** One index per document; look up in the sheet's own document first, job-wide only when exactly one
  document's index lists that number; record the title source. Keep the dot between digits (D8).
- **Test to add:** `tests/test_catalogue_job.py`: two documents with their own indexes giving M-101 different
  titles and title blocks with no title; assert each sheet takes its own document's title.

#### RD-7. Revision-table dates: the wrong date wins and dates are found inside words
- **Where:** `src/estimator/reading/revisions.py:125-148` (`_date_match`), `assets/reading_lists/revisions.json`.
- **Status:** FIXED fix/rd10 e900e42 (merged e77fbf9). **Priority:** P1 (decides which version governs).
- **What happens:** patterns are tried in list order, not by text position: `parse_date("ADDENDUM 1 3/4/2025 (REF
  2025-10-01)")` returns 2025-10-01. The month-name pattern has no leading word boundary: "SUMMARY 3, 2026" reads
  as 2026-03-03. "2026/01/15" is not read. Callers never pass `today`, so two-digit-year cutoffs follow the wall
  clock and output can change months apart.
- **Fix:** Collect matches from all patterns and take the smallest `match.start()`. Prefix month patterns with
  `\b`. Add a `(\d{4})/(\d{1,2})/(\d{1,2})` pattern. Pass a fixed `today` (recorded in the cache, or the newest
  date in the job) through `sheet_versions`.
- **Test to add:** `tests/test_revisions.py`: the three strings give 2025-03-04, None and 2026-01-15.

#### RD-8. The takeoff folder as input skips its "Electrical" subfolder and never reads a revision folder
- **Where:** `src/estimator/catalogue/documents.py:219-220` (`_LEFT_OUT` includes `electrical`), `:295`,
  `:356-364` (`_revision` looks only under "Takeoffs" / "Project Documents"). Production call: `bms/run.py:330`.
- **Status:** FIXED fix/rd8 9a9a9a5 (merged 99d44e6). **Priority:** P1.
- **What happens:** With the takeoff folder as root, `Electrical/` is left out with no flag line, and every
  document gets revision "base". So `_issue` can never tell "Rev 1/" from the base set, reissues fall to the copy
  rule (RD-4) instead of dated supersession, and discipline subfolders become separate issues.
- **Fix:** Apply `_LEFT_OUT` only at the job root and never inside the bid-documents folder; read the revision
  from the first folder under the input folder whatever its name; add left-out folders to the flags.
- **Test to add:** `tests/test_documents.py`: root = takeoff folder with `Electrical/E.pdf` and `Rev 1/M.pdf`;
  assert E.pdf is catalogued and M.pdf's revision is "Rev 1".

#### RD-9. An addendum is recognised by file name only
- **Where:** `documents.py:344` (`_ADDENDUM.search(name)`).
- **Status:** FIXED fix/rd8 9a9a9a5 (merged 99d44e6). **Priority:** P1 (fails safe: summed).
- **Fix:** `if any(_ADDENDUM.search(p) for p in Path(relative).parts)`.
- **Test to add:** `tests/test_documents.py`: "Addendum 2/M.pdf" has kind "addendum".

#### RD-10. Sheet numbers compared as raw strings; the pattern takes "REV 2" and misses "M-101-A"
- **Where:** `revisions.py:244` (`_sheet_number`), `job.py` `_flags`, `title_block.py:20-23` (`SHEET_NUMBER`).
- **Status:** FIXED fix/rd10 e900e42 (merged e77fbf9). **Priority:** P1 (unflagged overcount; needs D8).
- **What happens:** base "M-101" and addendum "M101" are never versions of each other, both read, no flag.
  `SHEET_NUMBER.fullmatch("REV 2")` is True. "M-101-A" and "M2.1-B" get no number.
- **Fix:** One canonical key in `_sheet_number` and `_flags` (D8). Add `(?:-[A-Z])?` before the final `[A-Z]?` in
  `SHEET_NUMBER`. Reject `^(?:REV|NO)\b` candidates in `read_title_block` and `_index_pairs`.
- **Test to add:** `tests/test_title_block.py`: "M-101-A" matches, "REV 2" is never chosen. `tests/test_revisions.py`:
  "M101" in an addendum supersedes "M-101".

#### RD-11. An addendum reissuing two same-numbered sheets of different titles is matched on its first page only
- **Where:** `revisions.py:383` (`by_sheet[...].setdefault(version.document, version)`), `:433`.
- **Status:** FIXED fix/rd10 e900e42 (merged e77fbf9). **Priority:** P1 (overcount named only by the generic "is on N pages" line).
- **Fix:** In `supersede`, group the current document's pages of the number by `title_words` and match once per
  title group.
- **Test to add:** `tests/test_final_o_counts.py`: base A and base B M-101 plus an addendum with both titles;
  assert both bases are replaced.

#### RD-12. `_image_covers_half` intersects unrotated image boxes with the rotated page rectangle
- **Where:** `register.py:81-86`. **Status:** FIXED fix/rd2 44b5c1d (merged 3ea6f4b). **Priority:** P2.
- **Fix:** `space = page.rect * page.derotation_matrix; covered = sum((Rect(b) & space).get_area() ...)`.
- **Test to add:** `tests/test_register.py`: same result for a rotated and an unrotated full-page scan.

#### RD-13. A typical sheet with no number is multiplied for devices but not for equipment
- **Where:** `inventory.plan_floors` (`if t.sheet and t.floors`), `revisions.governing_pages`, vs
  `devices.count_devices` (`floors_of` keyed by `(document, None, title)`).
- **Status:** FIXED fix/rd13 ec1428d (merged 8e18a54). **Priority:** P2 undercount.
- **Fix:** Key a numberless typical by (document, page) in `plan_floors` and `placements`, as `typical_sheets` does.
- **Test to add:** `tests/test_inventory.py`: numberless "TYPICAL 2ND-5TH FLOOR PLAN" with FCU-A; count is 4.

#### RD-14. The bid check counts unreadable pages without their document
- **Where:** `qualify.py` `check_bid` (`unread = sorted({r.page ...})`). **Status:** FIXED fix/rd13 ec1428d (merged 8e18a54). **Priority:** P2.
- **Fix:** collect `(r.document, r.page)` and report per document. **Test:** `tests/test_qualify.py`.

#### RD-15. A file that cannot be opened stops cataloguing
- **Where:** `documents.py:330-340` (`_fingerprint` → `path.open("rb")` before the `try`; `OSError` not caught).
- **Status:** FIXED fix/rd8 9a9a9a5 (merged 99d44e6). **Priority:** P2 crash.
- **Fix:** wrap in `try/except OSError` and return a `Document(..., "unreadable", ...)`.
- **Test to add:** `tests/test_documents.py`: monkeypatch `_fingerprint` to raise `PermissionError`; kind is
  "unreadable", no exception.

### B. Ledger and dossier — `src/estimator/ledger`, `src/estimator/writing/dossier.py`

#### LDG-1. Two sequence sections with the same heading collide
- **Where:** `ledger/seed.py:98-100` (sequence_match keyed by heading), `ledger/passes.py:306-316`
  (`ledger.find(kind, subject)`), `bms/plan.py:1178-1196` (`_unmatched_sections` groups by subject).
- **Status:** FIXED fix/ldg1 92d7171 (merged 58ea727). **Priority:** P0 (a system loses its sequence, no question).
- **What happens:** numbered capital sub-headings ("1. OCCUPIED MODE") under each system pass
  `is_section_heading`, so repeating headings are common. `apply` finds the first fact with that heading. Q1 and Q2
  both "1. OCCUPIED MODE", answered VAV and EF: F9 = VAV (contradicted; says EF [Q2]) and F10 (Q2) stays "" added.
  `Reader.matches("EF")` returns `[]`. `_unmatched_sections` sees F9 used so the whole group counts as used.
- **Fix:** In `apply`, for `sequence_match`, find the held fact by section id: `held = next((f for f in
  ledger.of_kind("sequence_match") if f.source_id == sid), None)`, falling back to `find` only when `sid` is not a
  Q id. In `_unmatched_sections`, group by `fact.source_id`.
- **Test to add:** `tests/test_ledger_passes.py`: two Q sections one heading, answered VAV and EF; both settled
  with their own values; `Reader.matches("EF")` gives Q2. `tests/bms/test_plan.py`: an unmatched duplicate-heading
  section raises a question.

#### LDG-2. Any bracketed id in document text lets the AI cite it; the run crashes on every rerun
- **Where:** `passes.py:266-269` (`known_source` accepts `sid in prompt_ids`), `facts.py:103-104` (`add` raises),
  `facts.py:144-145`.
- **Status:** FIXED fix/ldg2 5348c2f (merged a309cae). **Priority:** P0 crash.
- **What happens:** `known` is every `[X123]` in the dossier text, including document text such as "per detail
  [M5]". `Ledger.add` requires `self.knows(sid)` and raises `ValueError`. Nothing catches it; `read_job` and
  `bms.run.estimate` die. The judge cached the answer first, so every rerun replays and crashes until the cache
  file is deleted by hand.
- **Fix:** `def known_source(sid): return bool(sid) and ledger.knows(sid)`. Also wrap `ledger.add` / `_take` in
  `try/except ValueError` → `refused.append(...)`.
- **Test to add:** `tests/test_ledger_passes.py`: part text with `[M5]`, answer cites `[M5]`; `apply` returns a
  refusal, ledger unchanged.

#### LDG-3. A may-only-add pass can remove the "confirm it exists" flag
- **Where:** `passes.py:341-346` (confirmations settle any fact id), `passes.py:254-256` (`_take` → `contradict`
  sets CONTRADICTED on an ADDED fact); read in `bms/plan_read.py:233`, `ledger/to_plan.py:203`.
- **Status:** FIXED fix/ldg3 c2f596a (merged d4396a0). **Priority:** P1.
- **What happens:** the spec pass can confirm EF's plan-only count and it becomes settled; or the plans pass gives
  EF = 3 and the state goes added → contradicted. Both planners test `state == ADDED` for "seen on plans, on no
  schedule"; the warning and its question disappear.
- **Fix:** refuse a confirmation unless `ledger.facts[fid].kind in pass_.settles`. In `Ledger.contradict`, keep
  ADDED when the fact was ADDED (a separate `provisional` flag, or set CONTRADICTED only when not ADDED; the
  contradictions tuple alone marks the conflict).
- **Test to add:** `tests/test_ledger_passes.py`: spec pass confirms a seeded ADDED count → stays ADDED, refusal
  listed; plans pass gives a different EF count → `Reader.family(...).plan_only` still True.

#### LDG-4. A settling pass overwrites the seed's value with no record (plan-only tags lost)
- **Where:** `passes.py:250-260` (`_take` → `resolve`; record kept only for count and device).
- **Status:** FIXED fix/pln1 ef65d46 (merged db545b9). **Priority:** P0 with PLN-1.
- **What happens:** seed `unit` holds the counts line's tags (scheduled ∪ plans), e.g. "VAV-1 thru 12". Schedules
  pass answers "VAV-1 thru 10"; the fact becomes that, contradictions `()`. VAV-11 and VAV-12 are on no list.
- **Fix:** keep the old value as a contradiction for `unit` too; have the planner union a unit fact's value with
  its contradictions' tags (PLN-1). For other kinds, log "F5 unit VAV changed from … to …".
- **Test to add:** `tests/test_ledger_seed.py` / `test_ledger_passes.py`: seed "VAV-1 thru 12", schedules pass
  "VAV-1 thru 10"; old value kept beside the fact; planner's tags still include VAV-11 and VAV-12.

#### LDG-5. A device whose name has brackets is never seeded
- **Where:** `seed.py:15` `_DEVICE_LINE` (`\((?P<name>[^)]*)\)`). **Status:** FIXED fix/ldg5 c5a7550 (merged fdc28bc). **Priority:** P0 undercount.
- **What happens:** `assets/reading_lists/devices.json` maps `TB` to "Thermostat (by others?)"; legend meanings
  often carry brackets. The dossier line `[S8] TB (Thermostat (by others?)): 21 in all` does not match; no device
  fact; silent.
- **Fix:** `^\[(S\d+)\] (?P<label>\S+) \((?P<name>.*)\): (?P<total>\d+) in all`; same for `_COUNT_LINE`'s kind
  (`(?P<kind>.*?)\): `). Record unparsed `[S…]` lines in `ledger.refused["seed"]`; `seed.py:76-77` `continue`
  should leave a record.
- **Test to add:** `tests/test_ledger_seed.py`: `TB (Thermostat (by others?)): 21 in all` → device fact TB = 21.

#### LDG-6. The counts quote is cut at the first ". ", so "Bldg. A" drops the riser count
- **Where:** `seed.py:55` `re.split(r'\.(?:\s|$)', body, maxsplit=1)[0]`. **Status:** FIXED fix/ldg5 c5a7550 (merged fdc28bc). **Priority:** P0.
- **What happens:** per-sheet labels carry the document name when a number is in two documents or the sheet is
  unnumbered. The quote becomes `… plan placements 3 (M-101 (Bldg`, so `riser 7` is lost; `plan_read.counts_clauses`
  prints 3.
- **Fix:** cut only at the sentence that ends the clause list:
  `re.split(r"\.(?=\s+(?:Tags|By location|Reading notes):|\s*$)", body, maxsplit=1)[0]`. Better: seed riser and
  plan counts as their own facts (LDG-11).
- **Test to add:** `tests/test_ledger_seed.py`: counts line with "(Bldg. A.pdf)"; quote contains "riser 7";
  `Reader.family_count` gives 7.

#### LDG-7. Plan-sheet text (7c) no pass reads: spaced sheet numbers and unnumbered sheets
- **Where:** `seed.py:13` `_SHEET_LINE`, `passes.py:142-143`, `run.py:_picture_sheets`.
- **Status:** FIXED fix/ldg7 9bde7d7 (merged 25a15f3). **Priority:** P0 undercount (keynotes beside the drawing lost).
- **What happens:** "M 201" is a valid number but the 7c line parses with number ""; `documents(plans)` lacks it;
  not pictured. An unnumbered sheet's 7c line (key `doc#page`) is dropped by every pass.
- **Fix:** do not re-parse the number from the line. Map each 7c source id to its (document, page) and look up the
  catalogue sheet by that key (record `sid -> (document, page)` in `_sheet_text_lines`, or parse
  `dossier.sources[sid]`). Same fix as LDG-8(b).
- **Test to add:** `tests/test_ledger_passes.py`: "M 201" typed Plans and an unnumbered Plans sheet; both 7c lines
  in `documents(pass_named("plans"), …)`.

#### LDG-8. 7c keeps one sheet per number chosen by document kind, not the governing page; picture may be of another page
- **Where:** `dossier.py:1232-1243` (`_choose_sheets`), `ledger/run.py:29-32`, `passes.py:120-125`.
- **Status:** FIXED fix/ldg7 9bde7d7 (merged 25a15f3). **Priority:** P0.
- **What happens:** (a) two buildings each with M-101: 7c gives only A's text. (b) an addendum reissues M-101: 7c
  gives the addendum's text but `_picture_sheets` takes the first catalogue sheet with that number, so the plans
  pass sees the superseded page's picture. (c) a reissue in a "drawings" document with `revision="1"` is ignored;
  with two addenda the first wins. `_choose_sheets` ignores `governing_pages` and `supersessions`.
- **Fix:** `_plan_sheet_text` / `_printed_sheet_text` choose pages with `governing_pages(catalogue,
  reading.supersessions, typical_places(reading.typicals))`, key by `(document, page)`, skip `first_pages`
  repeats. `run._picture_sheets` and `passes._types_by_number` resolve each 7c sid to its own (document, page).
- **Test to add:** `tests/test_dossier.py`: two base documents with M-101 → both texts; base plus revision-1
  reissue → only the reissue's text. `tests/test_ledger_run.py`: the addendum's 7c picture key is the addendum's page.

#### LDG-9. Keynotes de-duplicated without their document
- **Where:** `dossier.py:1171`, `:1194` (`key = (note.sheet, note.block, note.number, note.text)`).
- **Status:** FIXED fix/ldg9 d4919ee (merged 9d19eba). **Priority:** P0 undercount.
- **Fix:** add `note.document` and `note.page` to both keys.
- **Test to add:** `tests/test_dossier.py`: same note on M-101 of two documents → two section-7 lines, two sources.

#### LDG-10. Two documents with the same file name give identical citations
- **Where:** `dossier.py:107-108` (`_name` keeps the file name), `_place`, page lines, every `where`.
- **Status:** FIXED fix/ldg3 c2f596a (merged d4396a0). **Priority:** P1.
- **Fix:** in `_place` and the page-line label use the relative path when the file name is not unique among
  `catalogue.job.documents`; compute a `names` map once in `build_dossier` as `sheet_labels` does.
- **Test to add:** `tests/test_dossier.py`: two same-named documents → their sources' wheres differ.

#### LDG-11. The old planner ignores the counts-line clauses; Ledger.json records only the lower count
- **Where:** `to_plan.py:33-44`, `seed.py:82-87`. **Status:** WONTFIX: only the old planner (to_plan.py) is affected; the bms planner reads the counts clauses itself; the fix breaks three seed/pass tests and drops a duplicate cited count (patch kept at Colab/lead/ldg11.patch). **Priority:** P2 (bms path unaffected).
- **Fix:** in `seed`, when plan placements or riser exceed the settled count, add it as a contradiction
  (`ledger.contradict(count.id, placements, sid, quote, "seed")`).
- **Test to add:** `tests/test_ledger_seed.py`: rows 12, placements 14 → `printed_count == 14`.

#### LDG-12. Passes with nothing to read are still asked
- **Where:** `passes.py:128-146` (`documents`), `dossier.py:1423-1428` placeholders. **Status:** FIXED fix/rd13 ec1428d (merged 8e18a54). **Priority:** P2.
- **Fix:** drop a section whose body is only a placeholder line (`^\(No .*\)$`), or export the placeholder set.
- **Test to add:** `tests/test_ledger_run.py`: empty dossier → no schedules or sequence request; "nothing to read".

#### LDG-13. `files.open_docx` / `open_workbook` let raw library errors through
- **Where:** `src/estimator/files.py:19`. **Status:** FIXED fix/rd13 ec1428d (merged 8e18a54). **Priority:** P2.
- **Fix:** add `ValueError` and `InvalidFileException` to `_UNREADABLE`; check `UnreadableFileError` first.
- **Test to add:** `tests/test_files.py`: each opener given the other's file type raises `UnreadableFileError`.

#### LDG-14. The ledger design spec and the code disagree
- **Where:** `docs/superpowers/specs/2026-09-29-staged-reading-ledger-design.md` §1, §1.3, §2 vs `seed.py`, `run.py`.
- **Status:** FIXED fix/rd13 ec1428d (merged 8e18a54). **Priority:** P2 docs.
- **What happens:** spec says one `unit` per tag, `location` per placement, `provider`, `front_end`, `group`
  candidates; code seeds family, one count, one unit tag list, device, sequence_match. Spec says split by sheet or
  section; code cuts at line ends so a part can begin mid-section without its `--- [Qn] ---` marker. Spec names
  `out/<job>/ledger.json`; code writes `<quote> Ledger.json`.
- **Fix:** update the spec to the code; split the sequence pass at `SECTION_MARK` lines carrying the marker.
- **Test to add:** `tests/test_ledger_run.py`: each part of a split sequence starts at a `--- [Q…] ---` line.

#### LDG-15. Dossier picture cache keyed by size and mtime, not content
- **Where:** `dossier.py:541-546` (`_file_key`). **Status:** FIXED fix/rd13 ec1428d (merged 8e18a54). **Priority:** P2 stale cache.
- **Fix:** use the document's sha1 (as `PageOpener.digest`) cached per document.
- **Test to add:** `tests/test_dossier.py`: rewrite a PDF with other content, `os.utime` back → new PNG path.

### C. Planner — `src/bms/plan.py`, `plan_groups.py`, `plan_read.py`

#### PLN-1. Tags a later pass adds to a family are dropped
- **Where:** `plan_read.py:228-229` (`Reader.family` reads only `unit.value`), `:250-252` (`seen_tags` skips
  family prefixes), `plan.py:847-852` (`lost`). Root also in LDG-4.
- **Status:** FIXED fix/pln1 ef65d46 (merged db545b9). **Priority:** P0 undercount.
- **What happens:** family EF, unit "EF-1 thru 3", count 3; the plans pass contradicts the unit with "EF-1 thru 4".
  Result: one EF system, tags EF-1..3, count 3. EF-4 is nowhere and no question names it.
- **Fix:** build tags from the value plus every `unit.contradictions[*].value` (expand each, drop bracket text as
  `seen_tags` does, de-duplicate in order). Tags only from a contradiction add one each to a unit count (as
  `place_seen` does) or raise a question naming both numbers. `lost()` uses the same union.
- **Test to add:** `tests/bms/test_plan.py::test_tags_a_later_pass_adds_to_a_family_are_kept`: "EF-4" in the
  system's tags or a question; count at least 4 or a question names 3 and 4.

#### PLN-2. A damper link not led by "MD" is credited to the MD family
- **Where:** `plan.py:610-615` (`link_dampers` prefix fallback), `:592` (`damper_keys`), `:48`.
- **Status:** FIXED fix/pln2 c61ffcf (merged 29482ec). **Priority:** P0 undercount.
- **What happens:** EF (EF-1); MD (MD-1, MD-2, 2); CD "Motorized Control Damper" (CD-1, 1); link "CD-1 damper" →
  EF-1. EF gets "Motorized Damper" tags () count 1; MD drops to 1 keeping both tags; CD stays 1 (CD-1 counted
  twice); question says "1 of the 2 are linked to no fan" which is false.
- **Fix:** use the fallback only when the subject has no tag of any family; if it holds a tag, credit
  `family_of_tag`. Never take a link off a family whose tags it does not name unless it is the only damper family.
- **Test to add:** `test_plan.py::test_a_damper_link_is_credited_to_the_family_of_its_tag`: MD stays 2 with both
  tags; CD-1 under EF; no "1 of the 2" question.

#### PLN-3. Rebuilt counts cite the old number, drop the other counts, raise no question (five places)
- **Where:** `plan.py:331-335` (`_rest`), `:680` (`_less_dampers`), `:697` (`_unclaimed`), `:306` (`_group`),
  `:366-368` (`general_kind_tags`); `plan_groups.py:87-97` (`stated`).
- **Status:** FIXED fix/pln3 f18296f (merged 2cf2fb8). **Priority:** P0.
- **What happens:** (a) EF-1..10 count 10 contradicted by 9; group "AHU-1 Plant" = "AHU, EF (EF-1, EF-2)": rest
  block prints 8 citing "EF rows 10", others `[]`, no question. (b) `stated()` sums every link fact in the job
  into each group part: HRU-1..4 count 12, group "AHU, HRU (HRU-1 x3)", link "HRU-1 x3" → AHU-1: part reads 6,
  rest prints 6 (12 − 6) while the documents support 9. (c) `_less_dampers`: MD count 3 contradicted by 2 → group
  MD becomes 2 citing "rows 3", others dropped, no question. (d) `general_kind_tags`: P (P-1, SPX-1, SPX-2) count 3
  contradicted by 2; SPX family: P prints 1 citing "rows 3" with others `[(2, …)]`, so `highest()` is 2 while
  `value` is 1.
- **Why wrong:** design §2 every reduction notes both numbers; interfaces §2.2 `value` is the highest, `others`
  are every different count.
- **Fix:** one helper `_reduced(count, new, why_ref)` → `Count(new, (derived ref,), others = old value + old
  others minus any equal to new)`; use it in all five places and append a question naming both numbers ("EF: 10
  per the schedule; 2 are in AHU-1 Plant, so this block prints 8"). In `stated()`, read a link fact only when it is
  about the group (subject or value names the group or a member tag) and never add a number repeating the same tag
  and number; or in `_rest` subtract only part counts read from the group fact itself and otherwise keep the family
  count.
- **Test to add:** `test_plan.py::test_a_rest_block_names_the_count_it_was_reduced_from`: for (a) to (d) the
  reduced family's `others` holds the original top number; no `others` equals `value`; `value == highest()` or a
  question names both; (b) rest block at least 9 or 12 kept.

#### PLN-4. Systems matched by bare prefix: a group with one EF tag takes other EF tags' dampers, exceptions and control
- **Where:** `plan.py:113-116` (`_Draft.names()` includes prefixes), used at `:603-604` (damper target), `:789`
  (`_control`), `:1173` (`_exceptions`), `:1120-1123` (`_units_named`). `_draft_named` (`:1127`) is dead code.
- **Status:** FIXED fix/pln4 e8a580a (merged a7626d1). **Priority:** P1.
- **What happens:** EF (EF-1, EF-2); AHU-1; MD (MD-1, MD-2); group "AHU-1 Plant" = "AHU, EF (EF-1)"; link MD-1 →
  EF-2: MD-1 goes under AHU-1 Plant. With `exception` "EF-2 controls by others" and provider EF-2 = "furnished
  with the unit": `ScopeException(system_key='AHU-1 Plant')` and `control=packaged` on both.
- **Fix:** two-step target: a draft holding the exact tag named (`naming(tag).search(text)` over `d.tags()`),
  then key/prefix fallback only when no draft holds a named tag. Apply in `link_dampers`, `_exceptions`,
  `_control` (a provider fact naming tags sets only those drafts' control). Use `_draft_named` or delete it.
- **Test to add:** `test_plan.py::test_a_link_exception_or_provider_naming_a_tag_lands_on_the_block_holding_that_tag`.

#### PLN-5. A damper family not prefixed MD never moves under its fan
- **Where:** `plan.py:48` (`DAMPER_PREFIXES = ("MD",)`), `:172-178` (`is_damper`), `:592`, `:637-638`.
- **Status:** FIXED fix/pln2 c61ffcf (merged 29482ec). **Priority:** P0 with PLN-2.
- **What happens:** EF (EF-1); CD "Motorized Control Damper" (CD-1, CD-2); link CD-1 → EF-1: CD block stays whole,
  shape "". `is_damper("CD-1")` is False (no "damper" in the tag text; never asks the ledger). "MD1" (no dash) and
  "(MD-1)" also fail. When moved, tags are `()` unless the subject is exactly a tag. `_damper_family` names a moved
  family "Motorized Damper" when the ledger has none (fixed wording, ground rule 2, minor).
- **Fix:** `is_damper` true when the subject's tag belongs to a family whose ledger name says "damper" and not
  fire/smoke; build `damper_keys` from those families plus the Playbook damper shape's prefixes (as
  `split_prefixes()` does); take tags with the same regex as `family_of_tag`.
- **Test to add:** `test_plan.py::test_a_damper_family_with_another_prefix_moves_under_its_fan`: EF holds
  "Motorized Control Damper" (CD-1,) count 1; CD keeps CD-2 count 1 plus a question naming 2 and 1.

#### PLN-6. A VRF group is split when indoor and outdoor families match separate sequence sections
- **Where:** `plan.py:185-192` (`drafts`), `plan_groups.py:55-60` (`split_apart`). **Status:** FIXED fix/pln4 e8a580a (merged a7626d1). **Priority:** P1.
- **What happens:** CU "VRF Condensing Unit", FCU "VRF Indoor Unit", BS "Branch Selector Box", group "VRF System",
  sequence matches "VRF OUTDOOR UNITS" → CU and "VRF INDOOR UNITS" → FCU: three systems (Split System, Fan Coil
  Unit, VRF System), all `field`; the question names CU and FCU but not BS.
- **Fix:** in `drafts()`, skip `split_apart` for a VRF or split group (`_VRF_WORDS` / `_BRANCH_WORDS`, or a member
  role branch/condensing with an indoor member). List every member prefix in the question.
- **Test to add:** `test_plan.py::test_a_vrf_group_with_indoor_and_outdoor_sections_stays_one_block`: one system,
  shape "VRF System", control "integration", families Indoor, Condensing, Branch; `sequence_refs` hold Q1 and Q2.

#### PLN-7. A lone split unit loses its Split System shape when condensate pumps join it
- **Where:** `plan.py:414-447` (`_condensate_pumps`), `:727-729` (`system`). **Status:** FIXED fix/pln4 e8a580a (merged a7626d1). **Priority:** P1.
- **Fix:** clear the shape only when every family is a condensate pump, or set `block.kind = "split"` when pumps
  join a single split draft.
- **Test to add:** `test_plan.py::test_condensate_pumps_joining_a_lone_split_unit_keep_its_split_shape`.

#### PLN-8. A prefix outweighs a clear family name (DH Dehumidifier into Duct Heaters; AC Air Curtain into Split)
- **Where:** `plan.py:166-170` (`is_duct_heater` falls back to `shape_for(name, [prefix])`), `:509`, `:387`
  (`gather_splits` loose by `_lead(d.key) in prefixes` only). **Status:** FIXED fix/pln4 e8a580a (merged a7626d1). **Priority:** P1.
- **Fix:** `is_duct_heater` from name or kind words only, prefix only when the name is generic; in
  `gather_splits` drop a loose draft whose ledger name matches another shape's kind words and not the split shape's.
- **Test to add:** `test_plan.py::test_a_family_named_otherwise_is_not_gathered_by_prefix`.

#### PLN-9. Some multiplier forms in a group fact drop the member or take the whole family
- **Where:** `plan_groups.py:14-17` (`_MEMBER`, `_TIMES`, `_TAG_TIMES`), `:41-48` (`members`). **Status:** FIXED fix/pln9 59e8c60 (merged 150a8da). **Priority:** P1.
- **What happens:** with AHU and CUH (CUH-A, CUH-B, 6): "AHU, CUH-A (TYP. OF 4)" drops the member; "AHU, CUH
  (CUH-A (4), CUH-B)" nested brackets drop the piece; "AHU, CUH-A 4 PLACES" and "CUH (CUH-Ax4)" take the whole
  family. `_TAG_TIMES` reads only "x N" / "×N".
- **Fix:** normalise each piece before `_MEMBER` (TAG (TYP. OF n), TAG (n), TAG n PLACES, TAG xn, TAGxn → TAG ×n,
  removing the inner bracket first); widen `_TAG_TIMES` and `_TIMES`; when a piece names no family, add a question
  instead of `continue`.
- **Test to add:** `test_plan.py::test_group_member_multiplier_forms` parametrised over the five values: group
  holds CUH ("CUH-A",) count 4; CUH block keeps CUH-B.

#### PLN-10. A count of 0 prints 0 although the family lists tags
- **Where:** `plan_read.py:29-36` (`number`), `:137-140` (`_entries`). **Status:** FIXED fix/pln10 1b73b74 (merged a22764d). **Priority:** P0.
- **Fix:** in `_entries`, skip `n == 0` as `counts_clauses` does so the count falls to None (Qty (##)); optionally a
  question "the schedule gives 0 for EF but lists EF-1, EF-2".
- **Test to add:** `test_plan.py::test_a_zero_count_with_tags_is_not_printed_as_zero`: value None or ≥ 2.

#### PLN-11. A later group listing a family whole loses it after an earlier group took part
- **Where:** `plan_groups.py:76-79` (`parts`). **Status:** FIXED fix/pln9 59e8c60 (merged 150a8da). **Priority:** P1 minor.
- **Fix:** when a later group wants the whole family and earlier groups took only parts, give it the untaken tags,
  or raise a question naming both groups.
- **Test to add:** `test_plan.py::test_a_later_group_listing_a_family_whole_takes_the_untaken_tags`.

#### PLN-12. The sheet "TAG ×N" reader does not accept the other multiplier forms
- **Where:** `plan_read.py:194-211` (`_tag_times_on_sheets`). **Status:** FIXED fix/pln9 59e8c60 (merged 150a8da). **Priority:** P2.
- **Fix:** share one multiplier regex with `estimator.catalogue.tags` or PLN-9's normaliser.
- **Test to add:** dossier line `[S2] CUH-A (TYP. OF 4)` → CUH count at least 4.

### D. Counts cross-check — `src/bms/counts*.py`

Shared fact: `render._printed` returns `Count.highest()`, so `Count(0)` prints as a known 0 and is priced; it does
not print "Qty (##)". Any path that turns an unknown count into 0 is an undercount.

#### CNT-1. An unknown count becomes 0 when the plan only names the tag in a note
- **Where:** `counts.py:420-427` (`_check_family`), `:453-454` (`_merge`: `if value is None: value, sources = n,
  [ref]`). **Status:** FIXED fix/cnt1 8e43708 (merged f4c83f2). **Priority:** P0.
- **What happens:** family ("EF-1",) `Count(None)`; the plan's only mention is a long note "EF-1 SHALL BE
  INTERLOCKED WITH …". `find.search` puts the sheet in `on_sheet`; the note filter leaves `located == []`, so
  `complete=True` and (0, LOCATED_QUOTE) is passed; `_merge` sets value 0.
- **Fix:** in `_merge`, adopt `n` for an unknown value only when `n > 0`; record a 0 as `others` (or drop it) and
  leave `value=None`. `test_an_unknown_count_takes_the_plan_count` still passes (its count is 4).
- **Test to add:** `tests/bms/test_counts.py`: plan with only the long note and `Count(None)` → `value is None` or ≥ 1.

#### CNT-2. An unknown count becomes 0 when the vision answer's boxes are all dropped
- **Where:** `counts_vision.py:216-228` (`read_answer`), `counts.py:101-102` (`count_sheet`), `:453-454`.
- **Status:** FIXED fix/cnt1 8e43708 (merged f4c83f2; partial-box follow-up in 4b). **Priority:** P0.
- **What happens:** raster plan (text ""), `Count(None)`; the AI names EF-1 and EF-2 but gives boxes in whole-sheet
  pixels (x=3000 in a 1568-px tile) or `boxes: []`. Every box is dropped, `count_sheet` returns `CountResult(0,
  ())`, the job prints 0 "counted on the sheet picture".
- **Fix:** in `read_answer`, a tag with `count > 0` and no surviving box is kept once with a clamped box, or the
  answer returns None so `ask_sheet` refuses it; in `check()` refuse boxes outside the tile ("boxes must be in the
  tile's own pixels"); apply CNT-1 so a vision 0 never replaces an unknown count.
- **Test to add:** `test_counts.py`: FakeVision with whole-sheet coordinates on a scanned sheet with `Count(None)`
  → value not 0.

#### CNT-3. Tag search matches inside a longer tag; the combined pattern lets one family take another's tags
- **Where:** `counts_text.py:111-113` (`searcher` lookahead `(?![A-Za-z0-9])` lets a dash or dot follow),
  `:58-66` (`_spelled` joint ` ?`), `counts.py:316` (`combined = "|".join(...)`, leftmost wins).
- **Status:** FIXED fix/cnt3 1f1258d (merged 4184dcf). **Priority:** P0 (false 0 for one family, false confirmation for another).
- **What happens:** `searcher("VAV…1")` finds "VAV-1" inside "VAV-1-01" and "CAC-1" inside "CAC-1.5"; the spelled
  pattern for VAV-1-01 also matches "VAV-101" (`fits()` accepts). System B ("VAV-1",) first and system A
  ("VAV-1-01","VAV-1-02"): both plan tags read as "VAV-1"; A's located count is 0 (an other, flagged), B is
  "confirmed" by a VAV-1 not on the plan.
- **Fix:** `searcher` lookahead `(?![A-Za-z0-9]|[-‐‑–—.][A-Za-z0-9])`; `_spelled` requires a dash or space after
  the first numbered part; `_count_sheet` searches each family pattern separately, or matches one generic token
  then classifies with `fits`; at minimum order alternatives longest first.
- **Test to add:** `test_counts.py`: the two-system setup in both orders → A located 2, B no "located on the sheet
  text" source; `fits(family_pattern(["VAV-1-01"], {"VAV": 2}), "VAV-101")` False;
  `searcher(pattern_for("CAC-1")).search("CAC-1.5")` None.

#### CNT-4. The stacked-line check invents tags from a tag and the number below it
- **Where:** `counts_text.py:203-228` (`_extract_page_tags`, stacked block). **Status:** FIXED fix/cnt4 ed1d300 (merged ba54472). **Priority:** P1 (overcount wins).
- **What happens:** consecutive lines are joined `f"{s1}-{s2}"` and the pattern searched anywhere: "EF-1 / 450
  CFM" yields `EF-1-450`; a family of 2 became 4 with located tags EF-1, EF-1-450, EF-2, EF-2-12. Adjacent different
  tags produce a box spanning both; `_distinct` picks the wide box as proof.
- **Fix:** join only when line 1 is a bare prefix or ends with a dash and line 2 is a bare number or letter part
  (as `estimator.catalogue.tags._SPLIT_TAG`); require `fullmatch`; skip pairs where either line already holds a tag.
- **Test to add:** `test_counts_microcrops.py`: textbox "EF-1\n450 CFM" → located ["EF-1"]; "VAV"/"1" still VAV-1.

#### CNT-5. The located-text count uses its own label rules, contradicting the guide and the planner's reader
- **Where:** `counts_text.py:14` (`NOTE_WORDS = 5`), `:170`, `:192-201`; `counts.py:10-11`, `:423`; vs
  `estimator/catalogue/tags.py:241-255` (`NOTE_WORDS = 12`, `_REFERENCE_WORDS`, ranges, `_STATED`, `is_type_tag`,
  `line_labels` / `plan_labels`). **Status:** FIXED fix/cnt4 ed1d300 (merged ba54472). **Priority:** P1 (undercount for unknown counts).
- **What happens:** "EF-2 ON ROOF ABOVE CORRIDOR SECOND FLOOR" (7 words) is dropped → a false dispute; "VAV-1 THRU
  VAV-5" gives 2 not 5; "CUH-A (TYP. OF 4)" gives 1 not 4; "TO EF-7" kept as placed; EBB-A on two floor plans
  gives 1 (docstring says "a tag shown on two sheets is one unit", the guide says sheets add up for type tags).
  With `Count(None)` these low numbers become the printed value.
- **Fix:** build the located count from the tags.py rules (`line_labels` / `plan_labels` with `label_keys(family
  tags)` per rawdict line), keep `_line_chars` only to map tags to boxes; count placements per sheet and add across
  sheets with the inventory's copy rule (unit tag once per plan, type tag its placements); fix the docstring and
  `NOTE_WORDS`.
- **Test to add:** `test_counts.py`: one plan with the three lines plus EBB-A on two floor plans → EF 1, VAV 5,
  CUH 4, EBB 2; no family whose planner count matches gets a located other.

#### CNT-6. Micro-crop path stops the vision count being independent; text boxes labelled "counted on the sheet picture"
- **Where:** `counts.py:327-350` (`_count_sheet`, esp. `:330-345`). **Status:** FIXED fix/cnt6 53e4a6a (merged ac6447a). **Priority:** P0.
- **What happens:** on any sheet with a text layer and one ambiguous box, only micro-crops around the ambiguous
  text boxes are sent; the result is merged with confident text boxes and stored as `sheet.seen` under
  "counted on the sheet picture". EF-1 clean, "(EF-2)" ambiguous, EF-3 drawn only in the picture, count 3: 2 crops
  sent, EF-3 never found, `vision=1, vision_tags=['EF-1']` recorded (a text box relabelled), proof draws EF-1 as
  vision. Because of CNT-4 almost any two adjacent tags are "ambiguous", so the full-tile branch nearly never runs.
- **Fix:** keep the crop answer separate: use it only to confirm or reject ambiguous text boxes inside the located
  count, never store as SEEN; whenever `symbols_expected` or `_schedule_disagrees` holds, ask the full tiles
  regardless of ambiguous boxes; never merge text boxes into `seen`.
- **Test to add:** `test_counts_microcrops.py`: the setup above → full tiles asked (not `is_crops`), vision count
  includes EF-3, `vision_tags` never holds a tag the transport did not return.

#### CNT-7. A vision answer leaving out every asked pattern (or echoing with plain dashes) is accepted and never asked again
- **Where:** `counts_vision.py:271-278` (`check`), `:232-240` (`_loose`, `answered`), `counts.py:98-100`.
- **Status:** FIXED fix/cnt4 ed1d300 (merged ba54472). **Priority:** P1 (the cross-check is silently switched off for that sheet).
- **Fix:** in `check()`, one problem per asked pattern missing from `answered(answer, patterns)`; in `_loose` fold
  `‐‑–—` to `-`; or ask with a stable pattern number and match by index.
- **Test to add:** `test_counts.py`: a `Refusable` answer with ASCII dashes or `{"patterns": []}` → `refused`
  non-empty; with `again=True` the second answer gives the count.

#### CNT-8. A raster plan with a vector title block is never counted by vision
- **Where:** `counts.py:271` (sheet selected only if the text matches the pattern or has < 50 characters).
- **Status:** FIXED fix/cnt6 53e4a6a (merged ac6447a). **Priority:** P0 risk.
- **Fix:** with a transport, also select plan sheets whose text matches no family but whose page is mostly picture
  (`dossier._picture_boxes` / `PICTURE_SHARE`, or no tag-shaped token plus an image covering most of the page).
- **Test to add:** `test_counts_microcrops.py`: scanned page plus a vector title → one vision question, full tiles.

#### CNT-9. `untagged_symbols` is asked for and thrown away; the prompt tells the count what to expect
- **Where:** `counts.py:376-387` (`_symbols_expected`), `counts_vision.py:89-92`, `:176-179`, `:207-229`.
- **Status:** FIXED fix/cnt9 29dd70d (merged 1f83543). **Priority:** P1.
- **What happens:** N is job-wide family count minus one sheet's located count, so a family of 10 over 5 sheets
  tells every sheet to expect about 8 more; `fits` runs on raw `family.tags` so list and range families never get
  the hint; `symbols[p]` overwritten when two families share a pattern; `read_answer` never reads the field.
- **Fix:** remove the number from the prompt (or compute per sheet); read `untagged_symbols` into the result as its
  own named count or drop the field; use `family_tags()` before `fits`.
- **Test to add:** `test_counts_microcrops.py`: prompt holds no expected number; `untagged_symbols` shows in the
  proof/count or is not asked for.

#### CNT-10. Stale proof entries published next to a different count with the same id
- **Where:** `counts_proof.py:91-105` (`save_manifest` keeps unrefreshed keys), `counts.py:192-207` (`publish_proofs`
  filters by `source_ids`). **Status:** FIXED fix/cnt9 29dd70d (merged 1f83543). **Priority:** P1.
- **Fix:** in `run`, replace all entries for the families checked (by `(system_key, family)`), or store a digest of
  the Ref (quote + where) and match on it.
- **Test to add:** `test_counts.py`: `cross_check` on a two-sheet catalogue then on a one-sheet catalogue with the
  same cache → `publish_proofs` lists only the current sheet.

#### CNT-11. A family whose tag is only its prefix is never checked
- **Where:** `plan.py:242`, `counts_text.py:41,53` (`is_tag` rejects "AHU"), `counts.py:258-260`.
- **Status:** FIXED fix/cnt9 29dd70d (merged 1f83543). **Priority:** P2.
- **Fix:** treat a bare prefix only this family owns as `_generic(prefix, numbers=True, letters=True)`.
- **Test to add:** `family_pattern(["AHU"], {"AHU": 1})` matches "AHU-1".

### E. Model, Playbook loader, lint — `src/bms/model.py`, `playbook.py`, `playbook_lint.py`, `playbook/`

#### PBK-1. Wording forms are never checked: a Playbook typo crashes the render or prints wrong client text
- **Where:** `playbook.py:262-264`, `:270-273`, `:339-342`, `:354-359` (keys only); used at `render.py:238`, `:426`,
  `:137` (`_fill` through `_Blank`). **Status:** FIXED fix/pbk1 399a2d8 (merged e63ae25). **Priority:** P1.
- **What happens:** `quantity.line` = `" (Qty. {count} Total)"` → `KeyError: 'count'`; `header.count` = `"{N}"` →
  `KeyError`; an unclosed `{device` → `ValueError`, or in a slot with no other placeholder prints `Interlock with
  Associated {device Operation`; `{devcie}` prints `Furnish and Install (Qty. 2 Total)` (name dropped, no error);
  header `{tag}` prints `Qty (3) Exhaust Fans` (tags dropped); `others_note` = `"*Qty. {count}."` prints `*Qty. .`;
  an owner bracket without a leading space prints `Furnish Motor Starter(Furnished by Others)`.
- **Fix:** helper `_form(text, where, path, allowed, required=())` walking `string.Formatter().parse(text)`
  (raises on a stray brace), rejecting field names outside `allowed`, numeric or empty names, format specs or
  conversions, and missing `required`. Apply: shape header {n, name, tags} req {n}; shape wording {verb, device,
  owner, qty, what}; `integration_trio` lines {what}; clarification forms {text} req {text}; `header.count` {n}
  req {n}; `header.unknown_count` and `quantity.unknown` {}; `quantity.line` req {n}; `others_note` req {counts};
  `count_causes.form` req {causes}. Require each owner bracket to start with `" ("`. Reject `{verb}` in `under`
  sub-line slots.
- **Test to add:** `tests/bms/test_playbook.py` parametrised over the eight edits → `PlaybookError` naming file and
  field; the shipped Playbook still loads.

#### PBK-2. The mechanical citation check depends on where a rule sits in rules.md
- **Where:** `ai.py:75` (`CITATIONS_TOPIC`), `:1262` (`_citation_rule` returns the first rule under that topic),
  `:1369`; lint `playbook_lint.py:85-88` knows no topic names. **Status:** FIXED fix/pbk2 ce23c31 (merged d22237e). **Priority:** P1 (silent loss of
  the only mechanical quote check).
- **Fix:** look the rule up by name `validate.RULE["cites"]`; if topic names must stay fixed, add
  `referenced_topic_names()` to the lint.
- **Test to add:** `tests/bms/test_ai*.py`: with the first two citation rules swapped, mechanical findings still
  carry `RULE["cites"]`; `test_playbook_lint_fixes.py`: a renamed citations topic does not lint clean.

#### PBK-3. Findings named "decision not honored" use a rule not in rules.md; lint cannot see it
- **Where:** `review.py:854`, `:860`, `:871`, `run.py:175`. **Status:** FIXED fix/pbk2 ce23c31 (merged d22237e; ruling D4). **Priority:** P2 (needs D4).
- **Fix:** per D4; either way have the lint gather literal `Finding("...")` rule names from `src/bms/*.py`.
- **Test to add:** `tests/bms/test_rule_names.py`: every literal `Finding(` rule in `src/bms` is in
  `referenced_rule_names()` or the exempt list.

#### PBK-4. A kind word with punctuation can never match, and the loader accepts it
- **Where:** `playbook.py:116-118`, `:259-261`. **Status:** FIXED fix/pbk2 ce23c31 (merged d22237e). **Priority:** P2.
- **Fix:** require each kind word to fully match `[a-z0-9]+( [a-z0-9]+)*`, or normalise kind words as the name is.
- **Test to add:** `test_playbook.py`: kind word `"make-up air unit"` raises `PlaybookError`.

#### PBK-5. Windows: the loader refuses UTF-8 with BOM, the lint reads it, a BOM leaks into AI instructions
- **Where:** `playbook.py:377` (`encoding="utf-8"`), `playbook_lint.py:111` (`utf-8-sig`). **Status:** FIXED fix/pbk1 399a2d8 (merged e63ae25). **Priority:** P1.
- **What happens:** BOM'd `shapes.json` / `wording.json` refused ("Unexpected UTF-8 BOM"); BOM'd `rules.md` loads
  with `rules_text` starting `'﻿# …'` sent to every AI step; a BOM'd file starting with `## Topic` loses
  that topic. Notepad and PowerShell 5.1 `Set-Content -Encoding utf8` write a BOM.
- **Fix:** `_read` uses `encoding="utf-8-sig"`.
- **Test to add:** `test_playbook.py`: each file written with a BOM loads; `rules_text` has no `﻿`.

#### PBK-6. Loader error line numbers in rules.md are wrong after any multi-line comment
- **Where:** `playbook.py:159` (`re.sub(..., "", text)` deletes line breaks), `:176`. **Status:** FIXED fix/pbk2 ce23c31 (merged d22237e). **Priority:** P2.
- **Fix:** strip comments with `lambda m: "\n" * m.group().count("\n")`, as the lint's `_blank` does.
- **Test to add:** a 5-line comment then a duplicate rule at line N → `PlaybookError` containing `line N`.

#### PBK-7. Sample-marker variants: loader keeps them as rule text, lint says the app cannot load the file
- **Where:** `playbook.py:159`, `:170` (exact `<!-- sample -->` only); lint `_COMMENT`. **Status:** FIXED fix/pbk2 ce23c31 (merged d22237e). **Priority:** P2.
- **Fix:** detect with `re.search(r"<!--\s*sample\s*-->", joined)` and remove with `re.sub`.
- **Test to add:** `test_playbook_lint_review.py`: `<!--sample-->` gives the same verdict from loader and lint;
  `Rule.sample` True.

#### PBK-8. A malformed heading (`###Name`, `##Topic`, `###<tab>Name`) silently joins the previous rule; lint stays clean
- **Where:** `playbook.py:176-197`, `playbook_lint.py:184-212`. **Status:** FIXED fix/pbk2 ce23c31 (merged d22237e). **Priority:** P2 (fix in the lint only;
  `test_an_indented_heading_is_rule_text_as_the_loader_reads_it` pins loader behaviour).
- **Fix:** lint warns on `^#{1,6}(?=[^#\s])` or `^#{2,3}\t` outside code fences.
- **Test to add:** `test_playbook_lint_fixes.py`: `###Second rule` gives one problem at its line.

#### PBK-9. `shape_for`: a prefix match beats any kind word; kind words taken in file order not by specificity
- **Where:** `playbook.py:112-120`; shapes order. **Status:** FIXED fix/pbk9 fe6b119 (merged 5379d5a). **Priority:** P2
  (code plus Playbook content).
- **What happens:** `shape_for("Existing Fan Coil Units", ["FCU"])` → "Fan Coil Unit" (the existing shape has no
  prefixes); "VAV Air Handling Units" → "VAV / Fan VAV"; kind word "global" catches "Fire Alarm Global Shutdown".
- **Fix:** among kind-word matches prefer one matching at the end of the name, then the longest, then file order;
  when a prefix-matched shape's kind word is a proper sub-phrase of another shape's matching kind word, the more
  specific wins. Content proposals in section 3.
- **Test to add:** `test_playbook.py`: `shape_for("VAV Air Handling Units", [])` is "Air Handling Unit";
  `shape_for("Existing Fan Coil Units", ["FCU"])` is "Existing Fan Coil Unit (relocated)".

#### PBK-10. Minor loader and docs items (all CONFIRMED)
- **Status:** FIXED: a, b, c, f fix/pbk2 ce23c31 (merged d22237e); d FIXED fix/docs 22d9a52 (merged ae32ebc); e FIXED fix/pbk10e b0f659e (merged 5103e26).
- a. No check for a prefix or kind word repeated across shapes (later shape unreachable). Fix: reject in
  `load_shapes`. Test: a duplicate `EF` raises.
- b. `tech_hours.when[].hours` (`playbook.py:315-321`) accepts negatives while top-level `hours < 0` is refused
  (`:309`). Test: `{"if": [slot], "hours": -2}` raises.
- c. `tests/bms/fixtures/sample_playbook/rules.md` lacks 7 names the code requires (Assumption wording has no
  source ids, Every line carries its ownership, Never undershoot, One system one block, Placing a device in a slot,
  Sub-lines under their parent, Systems named only in the sequence). Fix: add the headings (controller-owned
  fixture). Test: `lint_playbook(sample_playbook, referenced_rule_names()) == []`.
- d. Docs: interfaces §3.2 omits `order`; §3.4 `Shape` omits `under`, `order`, `parent_of()`; Constants omit
  `DEFAULT_ORDER`; §2.3 says every schema field "carries a description" but Job, Header and Decision fields have
  none; `System.shape` description omits the `""` case.
- e. No house-style check (arrows, emoji, source ids, trailing whitespace) on shapes.json wording or wording.json.
- f. `Rule.sample` and `Wording.draft` are loaded but never read; a leftover sample rule or non-empty `$draft`
  never warns.

### F. Validators and citations — `src/bms/validate.py`, `src/bms/citations.py`

Several of these are asserted by existing tests in `tests/bms/test_validate.py` (named per bug). Ruling D2 first.

#### VAL-1. `_loose` refuses legitimate "Wire (Furnished by Unit Mfr.)" and "Install and Wire" lines by other trades
- **Where:** `validate.py:168-177`. **Status:** FIXED fix/val1 b8db594 (merged 1e41e99). **Priority:** P1 false must_fix.
- **What happens:** `loose = verb == "Install and Wire" or (kind == "device" and furnished_by == "Unit Mfr.")`
  then requires exactly Install and Wire / Unit Mfr. / AME / AME. A Wire "Filter Differential Pressure Switch"
  (Unit Mfr., Unit Mfr., AME) and an Install and Wire "Condensate Float Switch" (Mechanical Contractor) both come
  back must_fix with a fix text that assigns wrong ownership.
- **Why wrong:** rules.md "Factory-installed devices", "Shipped-loose devices", "Verb from the three answers",
  "Other trades in brackets".
- **Fix:** shipped loose only when furnished by Unit Mfr. and installed by AME (then require Install and Wire and
  wired by AME); a Wire line where Unit Mfr. furnishes and installs and AME wires is fine; Install and Wire from
  any non-AME furnisher is fine. General verb/party consistency belongs to VAL-10.
- **Test to add:** on the repo "Packaged ERU / RTU / AHU": no "Shipped-loose devices" finding for the two lines
  above; `test_shipped_loose_must_be_install_and_wire` still passes.

#### VAL-2. `_packaged` makes every AME-furnished device on a packaged unit a must_fix
- **Where:** `validate.py:139-141`. **Status:** FIXED fix/val1 b8db594 (merged 1e41e99). **Priority:** P1 (ordered deletion = undercount).
- **Why wrong:** "Packaged units: … any device the documents explicitly give to the controls contractor";
  "Explicit assignment always wins"; "Mixed ownership device by device".
- **Fix:** downgrade to `check` ("If the documents give this device to the controls contractor, keep it;
  otherwise delete it"); keep must_fix only for a DDC controller slot on a packaged unit.
- **Test to add:** an AME-furnished `other_device` on a packaged block gives `check`.
  `test_packaged_internal_device_and_trio_twice` (RTU.d4) needs D2.

#### VAL-3. `_dampers`: must_fix on damper blocks the Playbook allows; noise checks on every unit's own dampers
- **Where:** `validate.py:67-71`, `:180-190`. **Status:** FIXED fix/val1 b8db594 (merged 1e41e99). **Priority:** P1.
- **What happens:** any job with a fan block plus a "Motorized Dampers" or stair-vent block gets must_fix "a damper
  in a block with no fan"; an AHU with `oa_damper` gets a check; `_is_fan_system` is false for AHU, FCU, Kitchen
  Exhaust, Stair Vent, Gas Detection, Unit Ventilators, Hot Water System though they have damper slots; an AHU
  whose only line is its OA damper becomes must_fix via the "every line a damper" fallback; the must_fix's fix text
  permits no change so revise can never close it.
- **Why wrong:** "Untraced dampers in their own block", "Unclaimed dampers in their own block", "Dampers under
  their fan" (the unit's own OA damper belongs in its block).
- **Fix:** drop the must_fix branch (at most a check "confirm the fan cannot be traced"); skip dampers whose slot
  is one of the block's own shape slots (not `other_*`); remove the `_is_damper_block` fallback.
- **Test to add:** with an EF block present, a Motorized Dampers block gives no must_fix; AHU with controller plus
  `oa_damper` gives no "Dampers under their fan". Tests `test_a_stand_alone_damper_block_is_must_fix` and
  `test_an_air_handler_with_a_damper_is_only_a_check` need D2.

#### VAL-4. `_sequence_only` uses the wrong test: any empty block with a sourced count gets must_fix "clear the count"
- **Where:** `validate.py:87-88`, `:309-315`; `_unknown` at `:279`. **Status:** FIXED fix/val1 b8db594 (merged 1e41e99). **Priority:** P1 (tells revise to
  erase a documented count).
- **Fix:** sequence-only from counts: `all(not f.count.sources and not f.count.others for f in families) and
  bool(sequence_refs)`; in `_sequence` require `value is None` and a `per_drawings` or `confirm` clarification
  whether or not the block has devices.
- **Test to add:** sourced family count, `devices=()`, `no_scope_reason` → no "Systems named only in the sequence"
  finding; family with no sources, None, integration lines, no clarification → finding.
  `test_sequence_only_system_prints_no_count` needs D2.

#### VAL-5. `_packaged` requires the integration trio on a packaged block with no lines
- **Where:** `validate.py:142-151`. **Status:** FIXED fix/val1 b8db594 (merged 1e41e99). **Priority:** P1.
- **Fix:** `if not system.devices: return` before the trio loop.
- **Test to add:** empty packaged block with `no_scope_reason` → no "Packaged units" finding.

#### VAL-6. `_left_out` reports "the writer gave no reason" while `no_scope_reason` holds it (see RND-8)
- **Where:** `validate.py:318-325`. **Status:** FIXED fix/val6 8bbe5ef (merged aff93bd). **Priority:** P1.
- **Fix:** `reason = (system.no_scope_reason or "").strip() or "; ".join(... clarifications ...)`.
- **Test to add:** `devices=()` with `no_scope_reason="x"` → `what` contains "x".

#### VAL-7. A shape name not in the Playbook validates clean, then the renderer raises
- **Where:** `validate.py:464` and every `if shape is None: return`. **Status:** FIXED fix/val6 8bbe5ef (merged aff93bd). **Priority:** P1.
- **Fix:** when `system.shape and system.shape not in playbook.shapes`, must_fix under "Placing a device in a slot"
  ("the shape 'X' is not in the Playbook"; fix "set the shape to a Playbook shape name or leave it empty").
- **Test to add:** a shape typo gives must_fix with `device_id None`.

#### VAL-8. A block that prints two or three "*" lines passes validate (see RND-4, D1)
- **Where:** `validate.py:290-294` (`_one_note`), `render.py:439-461`. **Status:** WONTFIX: ruling D1 (estimator, 2026-10-07): one '*' line per kind is the rule; rules.md amended in the main tree (uncommitted). **Priority:** P1.
- **Fix:** (a) preferred under D1: renderer joins into one line; (b) otherwise `_one_note` counts what prints
  (kinds ∪ assumed-if-any-device-assumption + 1 if any count has others).
- **Test to add:** per D1: sample RTU block has exactly one line starting "*", or `validate(sample)` reports "One
  clarification per block" for RTU.

#### VAL-9. `_header_under` forces the unit count up to a line total
- **Where:** `validate.py:391-405`. **Status:** FIXED fix/val1 b8db594 (merged 1e41e99). **Priority:** P1.
- **Why wrong:** "Line quantity: … Identical lines for several units are one line with the total." Two dampers per
  fan are normal.
- **Fix:** downgrade to `check`, or limit to one-per-unit slots (controller, start/stop, status).
- **Test to add:** 3 fans with damper quantity 6 → no must_fix. `test_a_device_quantity_above_the_header_count_is_must_fix`
  needs D2.

#### VAL-10. The verb is never checked against the three owners
- **Where:** `validate.py:101-107` (`_owners`). **Status:** FIXED fix/val10 eb0af1c (merged d14b3a5). **Priority:** P1 false negative.
- **Fix:** skip integration-kind slots; then
  ```python
  f, i, w = (p == "AME" for p in (d.furnished_by, d.installed_by, d.wired_by))
  ok = {"Furnish and Install": f and i, "Furnish and Wire": f and w, "Furnish": f,
        "Install and Wire": not f and i and w, "Wire": not f and w}[d.verb]
  if not (f or i or w): must_fix "not AME's scope: move it to the exclusions"
  elif not ok: must_fix f"the verb {d.verb} does not follow from who furnishes, installs and wires it"
  ```
  (zero hits on `sample_job.json`, so `test_the_sample_job_is_clean` stays green).
- **Test to add:** Install and Wire furnished by AME; Wire wired by EC; all Others → each must_fix under "Every
  line carries its ownership".

#### VAL-11. Sub-line ownership never compared with its parent's (D3)
- **Where:** `validate.py:119-128`. **Status:** CONFIRMED absent. **Priority:** P1.
- **Fix:** after finding the parent, compare `(furnished_by, installed_by, wired_by)` with the first device in the
  parent slot; must_fix when different; exemption per D3.
- **Test to add:** a gas-detection sub-line with ownership different from its panel gives must_fix.

#### VAL-12. VRF and split, one block: most splits and repeats not caught; split blocks get a noise check
- **Where:** `validate.py:235-259`. **Status:** FIXED fix/val10 eb0af1c (merged d14b3a5). **Priority:** P1.
- **What happens:** only family names "indoor unit" and "condensing unit" are recognised ("Outdoor Unit" is not);
  a separate "Branch Selector" block repeating VRF Communication Wiring gives nothing; repeats only in slots
  containing "comm" (`map_points` twice passes); both split blocks get "no communication wiring line".
- **Fix:** classify families into indoor / outdoor (condensing, outdoor, heat pump) / branch (selector,
  controller); must_fix when a VRF or split block lacks a role another block carries alone; count repeats per slot
  for every integration-kind slot and `vrf_comm_wiring`; the comm check only when the shape has `vrf_comm_wiring`.
- **Test to add:** Indoor / Outdoor split blocks → must_fix; Branch-Selector-only block → must_fix; `map_points`
  twice → must_fix; clean split block → no check.

#### VAL-13. `_cites` accepts a ref whose `where` is empty
- **Where:** `validate.py:94-98`. **Status:** FIXED fix/val6 8bbe5ef (merged aff93bd). **Priority:** P1 minor.
- **Fix:** add `or not r.where.strip()`; word as "a citation of X is missing its source id, quote or place".
- **Test to add:** `Ref("S9", "quote", "")` → must_fix under "Every line cites this job".

#### VAL-14. The 160-character line limit is not enforced anywhere
- **Status:** FIXED fix/val14 ef25cfb (merged d1660bd). **Priority:** P2. **Fix:** `_long_line` under "Line form": check when the rendered line
  exceeds 160. **Test:** a 300-character name gives a check.

#### VAL-15. An unknown device quantity prints "(Qty. ##)" with no confirm
- **Where:** `validate.py:278-287` (`_unknown` looks only at families). **Status:** FIXED fix/val6 8bbe5ef (merged aff93bd). **Priority:** P1.
- **Fix:** also a check for devices whose `quantity.highest()` is None when the slot's wording contains `{qty}` and
  there is no confirm or per_drawings clarification.
- **Test to add:** `other_device` with `Count(None)` and no clarification → check under "Never undershoot".

#### VAL-16. The id detector misses an id split by an invisible format character; the safety net prints it
- **Where:** `citations.py:70` (`_ZERO_WIDTH`), `_for_detection` `:342-353`. **Status:** FIXED fix/val14 ef25cfb (merged d1660bd). **Priority:** P2.
- **Fix:** treat every `unicodedata.category(ch) == "Cf"` (and U+034F) as zero-width in `_for_detection` and
  `_tag_copy`; keep the soft-hyphen case.
- **Test to add:** `tests/bms/test_citations_detector_gaps.py` parametrised: `scan("per S" + ch + "201")` → one
  issued token.

#### VAL-17. Ids with five or more digits are never detected; allocation has no cap
- **Where:** `citations.py:49, 52, 58` (`\d{1,4}`); `dossier.py:155`, `facts.py:109` unbounded. **Status:** FIXED fix/val14 ef25cfb (merged d1660bd). **Priority:** P2 conditional.
- **Fix:** widen to `\d{1,6}` in `ONE_ID_TEXT`, `_TOKEN`, `SHEET`, `LEDGER_BRACKET`, `_TAG_RANGE` together; or assert
  in dossier and ledger that ids stay at four digits.
- **Test to add:** `SourceIds.of(ids=["S10001"]).scan("per S10001")` → one issued token.

#### VAL-18. A count with `value None` but a known other passes (D9)
- **Where:** `validate.py:262-266`. **Status:** FIXED fix/val1 b8db594 (merged 1e41e99). **Priority:** P1 contract.
- **Fix:** in `_count_problems`, `value is None and top is not None` → must_fix "set the count to {top}".
- **Test to add:** value None, others [5] → must_fix.

#### VAL-19. Point lines and controller lines on a factory-controlled VRF pass
- **Where:** `validate.py:131-141` (gated on `control == "packaged"`); `plan.py:796` gives VRF `integration`.
- **Status:** FIXED fix/val10 eb0af1c (merged d14b3a5). **Priority:** P1.
- **Fix:** extend the point and controller checks to `control == "integration"` for VRF and split shapes only.
- **Test to add:** VRF block with an `other_point` Furnish → must_fix.

#### VAL-20. Rule names misfiled; length limits the rules never state
- **Where:** `validate.py:19-40, 42`. **Status:** FIXED in part fix/val14 ef25cfb (merged d1660bd); id-hit refiling left, see 4b. **Priority:** P2 docs.
- **What happens:** `left_out` filed under "One system one block"; `long_note` / `long_assumption` use an invented
  220-character limit while the QC prompt says about 25 / 40 words; `ids` hits on names and exceptions filed under
  "Assumption wording has no source ids" rather than "Words the client never sees".
- **Fix:** refile; choose one length limit and write it into rules.md through the estimator.
- **Test to add:** `test_rule_names.py` asserts the remapped names.

#### VAL-21. "Words the client never sees" has no surface check
- **Status:** FIXED fix/val14 ef25cfb (merged d1660bd). **Priority:** P2. **Fix:** word-boundary regex for `\$`, `\bGEM\b`, `\bQC\b` and
  the capitalised flag words over client texts → check. **Test:** a clarification with "PENDING" or "$500" gives a check.

Rule coverage note: of about 85 rule headings in rules.md, 14 have a validator; the rest are enforced only by the
QC prompt or by render order. The reviewer's full table is in the audit transcript; the gaps that are
field-checkable are VAL-10 to VAL-15, VAL-19 and VAL-21.

### G. AI steps and prompts — `src/bms/ai.py`, `ai_evidence.py`, `prompts/`

#### AI-1. `rewrite_for_count` can never apply the changed count to the lines already written
- **Where:** `ai.py:1118-1137` (passes `system.devices` as both `keep` and `originals`), `_put_back` `:1064-1080`.
- **Status:** FIXED fix/ai1 b82fa2d (merged 8f8258d). **Priority:** P0 (silent undershoot; `_header_under` catches only the other direction).
- **What happens:** the estimator changes EF from 3 to 5; the writer answers d1, d2 at 5; `_put_back` swaps every
  matching id back to the original: `[('EF.d1', 3), ('EF.d2', 3), ('EF.d3', 2)]` while the family says 5. Validate
  gives no finding. Device quantity is what render prints and prices.
- **Fix:** keep each device's identity and words but take `quantity` (and `flag`) from the answer device with the
  same id, or after `_put_back` set `quantity` to the new family count for each kept device
  `bms.counts.counted_from` ties to a changed family. Add a prompt sentence: "Each line that carries a changed
  family's count carries the new count."
- **Test to add:** `tests/bms/test_ai.py`: rewrite EF with count 5 and an answer carrying 5 → devices that carried 3
  now carry 5; `validate()` flags a family-count device left below the family count.

#### AI-2. `_put_back` matches by id only: an added line is lost and a kept line duplicated
- **Where:** `ai.py:1064-1080`. **Status:** FIXED fix/ai2 a16fda3 (merged e6a467b). **Priority:** P1.
- **What happens:** the write prompt numbers devices "d1, d2 … in print order"; revise inherits it. A writer that
  inserts a new line renumbers the rest; revise with a finding on d1 and answer `d1, NEW(d2), old-d2-as-d3,
  old-d3-as-d4` gives the new line lost and the damper actuator twice. Same in `rewrite_for_count`, whose prompt
  never shows ids.
- **Fix:** match an answer device to a kept one only when slot and name match too; renumber an answer device whose
  id collides but content differs; drop an answer device that duplicates a kept device's content under another id;
  state one id rule in both prompts ("keep the ids given; a new line takes the next free number").
- **Test to add:** `test_ai.py`: revise and count rewrite with the renumbered answer → new line present, no
  name/slot pair twice.

#### AI-3. Quantity refs never checked against the evidence; the QC quote check waves through any F or I id
- **Where:** `ai.py:897-907` (only `device["refs"]` filtered), `:1224` (`_ref_problem` returns None for any F not in
  index or any `I\d+`). **Status:** FIXED fix/ai3 a3bcbed (merged e1d0ab6). **Priority:** P0 ground rule.
- **What happens:** d3 `quantity: {value: 7, sources: [F999], others: [{9, I999}]}` is accepted; `_quote_findings`
  makes no finding; validate does not check quantity refs; in a revise, `known` includes `_all_refs(system)` so a
  fake id in an earlier quantity source becomes citable as a device ref.
- **Fix:** in `_check_system` one problem per quantity source or other whose `source_id` is not in `known`
  (skipping the counts' own records `LOCATED_QUOTE`, `SEEN_QUOTE`, `NO_SOURCE_QUOTE`); in `_ref_problem` return
  None for an I id only when `sid in index` or it is a known count-proof id; check F ids against `system_refs`;
  in `revise_system` build `known` from the evidence plus `system_refs(system)` only.
- **Test to add:** `test_ai.py`: the F999/I999 answer is refused naming the id; a job whose device quantity cites
  I999 gets a must_fix from `qc_job`.

#### AI-4. A revised answer's quotes are never checked, and the QC finding is closed anyway
- **Where:** `ai.py:1159-1180` (`revise_system` → `_check_system` checks ids not quotes), `run.py:527`, `:246-259`.
- **Status:** FIXED fix/ai3 a3bcbed (merged e1d0ab6). **Priority:** P0 ground rule (an invented quote ships with no card).
- **Fix:** at intake, check quotes against the evidence sent (`ai_evidence.index` on the evidence entries) in
  `_check_system` for write, rewrite and revise; or at least run `_quote_findings` on the revised job in `run.py`
  and keep those findings open.
- **Test to add:** `test_ai.py`: a revise answer with a quote missing from its source is refused naming the source
  id; the equivalent write-path test passes.

#### AI-5. An empty source id `""` counts as known; the evidence prints a "[]" fact
- **Where:** `ai.py:860-861` (`_ref_ids` keeps `""`), `:1112/1129/1176`, `ai_evidence.py:227-233`; source
  `counts.py:461` (`OtherCount(value, Ref("", NO_SOURCE_QUOTE, ""))`). **Status:** FIXED fix/ai5 ed23354 (merged a7d0c0f). **Priority:** P0 with AI-3.
- **Fix:** `_ref_ids` drops empty ids; `evidence()` skips refs with an empty id or a counts-record quote.
- **Test to add:** `test_ai.py`: no evidence line starting `[]`; a device citing `""` is refused.

#### AI-6. A system with no plan sheets gets every plan device in the job as its evidence
- **Where:** `ai_evidence.py:271` (`if not sheets or on & sheets or …`). **Status:** FIXED fix/ai6 368b752 (merged 3d3f592). **Priority:** P1.
- **Fix:** `if (sheets and on & sheets) or entry.sid in cited or about.names(entry.body):`.
- **Test to add:** extend `test_evidence_for_a_system_without_tags_uses_its_section_and_its_name`; DH evidence has
  no S36 or S43.

#### AI-7. API mode: an answer that passes on the retry is cached under the retry prompt
- **Where:** `ai.py:684-687` (`prompt_now = f"{prompt}{_RETRY_MARK} …"`), `ApiTransport.ask` `:548-568`.
- **Status:** FIXED fix/ai7 775180d (merged 2528179). **Priority:** P1 stale cache (identical inputs give a different job on the next run).
- **Fix:** when the retry passes, also write the answer under the original question's key, or key the API cache by
  the prompt without `_RETRY_MARK` as `_attempt_file` does.
- **Test to add:** `test_ai.py`: run 1 bad then good A, run 2 good B → run 2 makes 0 calls and returns good A.

#### AI-8. API mode: a schema-invalid or cut-off answer is not counted, no reason fed back, asked again every run
- **Where:** `ai.py:559-567`, `_answer_of` `:628-647` (NoAnswer raised inside `ask`). **Status:** FIXED fix/ai7 775180d (merged 2528179). **Priority:** P1.
- **Fix:** in `ApiTransport.ask`, for a schema-invalid answer call `_record_refusal`, stop at the cap with
  `_stop_reason`, otherwise return the problem so `_ask_checked` retries with `_RETRY_MARK`; leave transport errors
  uncounted.
- **Test to add:** `test_ai.py`: 3 schema-invalid responses → the second prompt carries the reason; the run after
  the third makes 0 calls with "Stopped:".

#### AI-9. Chat mode: the refusal reason is erased whenever the run is repeated before a new answer arrives
- **Where:** `ChatTransport.ask` `ai.py:430-449` (`self._request(q, None)`), `_request` `:461-507`.
- **Status:** FIXED fix/ai7 775180d (merged 2528179). **Priority:** P1 (the skill dispatches in batches of 4, so this happens on every job with more
  than 4 write requests).
- **Fix:** save the reason in the attempt file; when `problem` is None use the saved problem.
- **Test to add:** `test_ai.py`: refuse once, run again with no new answer → request still has `previous_problem`;
  same after a stop.

#### AI-10. The revise can change the clarification, tech hours and no_scope_reason with no finding about them
- **Where:** `revise_system` `ai.py:1159-1180`. **Status:** FIXED fix/ai2 a16fda3 (merged e6a467b). **Priority:** P1.
- **Fix:** when every finding names a device, put back `clarifications`, `tech_hours`, `no_scope_reason`.
- **Test to add:** a device-only revise answer changing clarification and tech hours returns the originals.

#### AI-11. The QC prompt contradicts the Playbook's integration rules (D5)
- **Where:** `prompts/qc_job.md:12` ("Ask for an integration line only when a cited source calls for the BMS to
  integrate that unit"). **Status:** FIXED fix/ai11 ec87e4e (merged 8d8f907; wording 1c251f0). **Priority:** P1.
- **Fix:** "never ask for VFD or speed lines a factory-controlled unit does not have. The integration trio follows
  the Playbook's integration rules."
- **Test to add:** prompt-text test in `test_ai.py`.

#### AI-12. The write prompt flags ownership whenever the evidence is silent (D5)
- **Where:** `prompts/write_system.md:35`. **Status:** FIXED fix/ai11 ec87e4e (merged 8d8f907; wording 1c251f0). **Priority:** P1 (most lines get a flag and assumption).
- **Fix:** "When the evidence names no party, take the Playbook's default. Set flag "ownership" (with an
  assumption) only in the cases the Playbook lists under unclear ownership."
- **Test to add:** prompt-text test.

#### AI-13. The write prompt invites a separate relay line the Playbook absorbs (D5)
- **Where:** `write_system.md:13`. **Status:** FIXED fix/ai11 ec87e4e (merged 8d8f907). **Priority:** P2.
- **Fix:** add "unless the Playbook says another line already covers it or it is inside a packaged unit".

#### AI-14. Chat mode: "another model makes a new question" is false (D7)
- **Where:** `ai.py:61` `CHAT_MODEL` in `_question` and `_attempt_file`; contradicted by USER-GUIDE:114, the
  interfaces "Refusals" paragraph, `ai.py:347`. **Status:** FIXED fix/run7 fc621c6 (merged 06a02c5; docs per ruling D7). **Priority:** P2.

#### AI-15. `tools/run_job.py` attempt counter never resets — same as RUN-8.
- **Status:** FIXED with RUN-8 (fix/run7 fc621c6).

#### AI-16. A QC finding naming a device that does not exist turns the revise into a whole-block rewrite
- **Where:** `_check_findings` `ai.py:1350-1352`, `revise_system` `:1174-1175`. **Status:** FIXED fix/ai2 a16fda3 (merged e6a467b). **Priority:** P2.
- **Fix:** treat such a finding as "about no device" so the revise keeps the other devices, or drop it.
- **Test to add:** one real-device finding plus one phantom-id finding keeps the unnamed devices.

#### AI-17. A packaged or integrated system gets other systems' integration passages
- **Where:** `ai_evidence.py:280-284`. **Status:** FIXED fix/ai6 368b752 (merged 3d3f592). **Priority:** P1 minor.
- **Fix:** include a word-only match only when the passage names no other system's tags or names.
- **Test to add:** RTU evidence has no S38.

#### AI-18. `evidence_for` has no `sections_in` fallback while `evidence_index` and `plan` do
- **Where:** `ai.py:707-708` vs `:714-717`. **Status:** FIXED fix/ai6 368b752 (merged 3d3f592). **Priority:** P2.
- **Fix:** `sections = dossier.sections or sections_in(dossier.text or "")`.
- **Test to add:** EF evidence with `sections={}` still contains `--- [Q2] B. EXHAUST FANS ---`, S18 and S19.

### H. Renderer, price sheet, Evidence Package — `src/bms/render.py`, `evidence.py`, kept writers

#### RND-1. The price book never strips the renderer's " (Qty. N Total)"
- **Where:** `src/estimator/price_sheet/price_book.py:21` (`_QUANTITY` requires a dash before the bracket);
  `wording.json` `quantity.line` is `" (Qty. {n} Total)"`. **Status:** FIXED fix/rnd1 c4a5131 (merged a05174a). **Priority:** P0 (every job; every line
  whose quantity differs from the block count goes PRICE PENDING). `tests/test_price_book.py` uses only the old
  "– (Qty. N Total)" form.
- **Fix:** `_QUANTITY = re.compile(r"\s*(?:[–-]\s*)?\(qty\.?\s*(?:\d+|##)\s*(?:total)?\s*\).*$", re.IGNORECASE)`.
- **Test to add:** `tests/test_price_book.py`: `price_key("o  Furnish and Install Space Temperature Sensor (Qty. 6
  Total)") == "space temperature sensor"`. `tests/bms/test_render.py`: render a device whose quantity differs from
  the block count, write the price sheet, assert column E holds the book price and column H is empty.

#### RND-2. A "(Qty. ##)" line inside a block with a known count is unpriced and unflagged
- **Where:** `price_sheet/write.py:64-84` (`_fill`), `rows.py:72-74`. **Status:** FIXED fix/rnd5 8bde3b2 (merged 53a18ed). **Priority:** P1.
- **Fix:** `Row.quantity_pending = item.kind == "line" and item.quantity is None and "(Qty. ##)" in item.text`;
  `_flag(ws, r, QUANTITY_PENDING)`; add to the `counts` message in `_fill_summary`.
- **Test to add:** `tests/test_price_rows.py`: Block "Qty (2) X" with Item "… (Qty. ##)" writes QUANTITY PENDING in
  column H and B34 mentions it.

#### RND-3. Drafts that cannot be printed fail with something other than RenderError
- **Where:** `render.py:546-554` (`Block`/`Item` construction, `model_copy`), `:102-111` (one `Alternate` per system);
  `run.py:536-541`. **Status:** FIXED fix/run4 679f243 (merged 2d6c673). **Priority:** P0 crash (run left "running").
- **What happens:** a blank sub-line name → `pydantic ValidationError`; quantity -1 → `ValidationError`; both can
  arrive from a review-page "change" (`review._apply_one` only type-checks). `model_copy(update=…)` skips
  validation so tech hours -1.0 pass into the price sheet. A control character in a name → `ValueError: All
  strings must be XML compatible` from `write_proposal` after the Evidence Package is written. Ten add-alternate
  systems → `PriceSheetError` ("needs 11 price sheets; the template has 10") inside `_build`.
- **Fix:** wrap `Item(...)`/`Block(...)` in `try/except ValueError → RenderError(f"system {key}: {e}")`; replace
  `model_copy` with `Block.model_validate`; at the end of `render` call `price_sheet.write.check_fit(scope)` and
  convert `PriceSheetError` to `RenderError`; strip XML-illegal characters in the client-text safety net or refuse.
- **Test to add:** `test_render.py`: blank-named sub-line → RenderError; tech_hours -1 → RenderError; ten add
  alternates → RenderError; a `\x01` in a name → RenderError or printed without it.

#### RND-4. A block prints several "*" lines (D1)
- **Where:** `render.py:439-461` (`_notes`), `:541-543`. **Status:** WONTFIX: ruling D1; rules.md 'One clarification per block' and 'Joining into the one clarification' amended to today's render. **Priority:** P1 ground rule 6.
- **Fix (under D1):** `_notes` returns at most one string: collect parts (confirm, assumption reasons, per
  drawings, the quantity note, client notes), pick the kind by rules.md precedence, first part takes its kind's
  form, later parts take lead forms from new wording.json keys.
- **Test to add:** a block with a confirm, an assumption and an others count → one line starting "*Confirm"
  containing "Assumed:" and the quantity clauses; for every sample-job block `sum(t.startswith("*")) <= 1`.

#### RND-5. A higher count can print with no count named; clauses past five dropped; multi-family note unlabelled (D6)
- **Where:** `render.py:285-325` (`_count_part`: `if not folded: return ""` at 304; `[:MAX_COUNT_CLAUSES - 1]` at 306;
  `_count_note` join at 320). **Status:** FIXED fix/rnd5 8bde3b2 (merged 53a18ed). **Priority:** P1.
- **Fix:** an unlabelled count still prints with a Playbook word (new key `unlabelled`); raise or remove the cap or
  print "and N more counts"; prefix each family part with the family name when a block has more than one.
- **Test to add:** Count(20, others=[15 unlabelled]) prints one note naming 15; six others print all six; the
  two-family note names both families.

#### RND-6. The client's count-cause words vanish when the printed count also has a sheet source
- **Where:** `render.py:296`, `:308-313`. **Status:** FIXED fix/rnd9 b0f724c (merged e75c0da). **Priority:** P1.
- **Fix:** when `causes` is set and `PLACEMENTS_LABEL in heads`, use it as the head or append `causes` after
  whatever head prints.
- **Test to add:** plan placements 12 plus a sheet-picture 12 on M-101 → note contains "likely a typical unit at
  each place".

#### RND-7. Evidence Package quantity disagrees with the proposal; other counts lose source id and quote (D9)
- **Where:** `bms/evidence.py:40-45` (`_quantity`, `_others`). **Status:** FIXED fix/rnd5 8bde3b2 (merged 53a18ed). **Priority:** P1.
- **Fix:** `_quantity`: `n = count.highest(); "Qty (##), not known" if n is None else str(n)`; `_others`:
  `f"{o.value} per {_ref(o.ref)}"` with id and quote; rename column "Line" to "Device id"; correct the model
  docstring to "None and no other count".
- **Test to add:** new `tests/bms/test_evidence.py`: `scope_rows` for Count(None, others=[2 @ S2 "q"]) gives
  quantity "2" and the other-counts cell contains "S2" and the quote.

#### RND-8. A left-out system's reason is lost; its note never reaches the Evidence Package (with VAL-6)
- **Where:** `render.py:491-495` (`left_out_text`), `evidence.py:56-82` (`scope_rows`), `run.py:537`.
- **Status:** FIXED fix/val6 8bbe5ef (merged aff93bd). **Priority:** P1.
- **Fix:** `left_out_text` uses `system.no_scope_reason` first; `scope_rows` appends a "left out" row with the
  reason for `not system.devices`.
- **Test to add:** `test_render.py`: no devices and `no_scope_reason="X"` → note contains "X";
  `tests/bms/test_evidence.py`: `scope_rows` has a "left out" row naming X.

#### RND-9. Every alternate prints the template placeholder "ALT #:"
- **Where:** `render.py:105-108`; default label in `estimator/scope.py:96`. **Status:** FIXED fix/rnd9 b0f724c (merged e75c0da). **Priority:** P1.
- **Fix:** after sorting, `label=f"ALT #{k}: {name}"` (form from a new wording.json key); number adds and deducts
  separately.
- **Test to add:** two add systems → labels "ALT #1: …" and "ALT #2: …".

#### RND-10. Title-casing turns ordinary words into acronyms ("No" → "NO", "It" → "IT", "Co-located" → "CO-Located")
- **Where:** `render.py:144-161` (`ACRONYMS`, `_title`). **Status:** FIXED fix/rnd9 b0f724c (merged e75c0da). **Priority:** P1.
- **Fix:** apply ambiguous acronyms (NO, IT, CO, FA) only when already upper case in the source; unambiguous ones
  (BMS, VFD, DDC, ERV, RTU, HPAC, SCR, UUKL, BACnet) on lower case; never rewrite an already-capitalised word; move
  both lists to wording.json (RND-14).
- **Test to add:** parametrised: "Damper actuator with no end switch", "No. 2 fuel oil pump", "Co-located
  sensor", "connect it to the panel" print unchanged apart from first-letter capitals.

#### RND-11. Any device whose name matches any shape's fixed wording loses its verb and owner bracket
- **Where:** `render.py:347-364` (`_fixed_texts`, one global lookup over every shape), `:418-420`. **Status:** FIXED fix/rnd9 b0f724c (merged e75c0da).
  **Priority:** P1 ground rule 4.
- **What happens:** an Exhaust Fan device "Condenser Interlock Wiring" (Wire, Others) prints with no verb and no
  "(Furnished by Others)". Related: an orphan sub-line device prints at depth 1 with no verb.
- **Fix:** limit `lines` to the integration trio's placeholder-free lines plus the current shape's own fixed
  wordings; keep `{owner}` when the device is not AME's. Playbook proposals in section 3.
- **Test to add:** the case prints "Wire Condenser Interlock Wiring (Furnished by Others)".

#### RND-12. An assumption is checked for what and why before cleaning
- **Where:** `render.py:195-203` (`_reason`). **Status:** FIXED fix/rnd9 b0f724c (merged e75c0da). **Priority:** P1 ground rule 6.
- **What happens:** why = "S141" prints `*Assumed: one sensor per unit` with no reason; what = "Assumed:" prints
  `*Assumed: , because …`.
- **Fix:** run the check on the cleaned `what` and `why`; raise `RenderError` if either is empty.
- **Test to add:** both cases raise `RenderError` matching "what and why".

#### RND-13. `wording.json` `integration_trio.depths` is loaded but never used
- **Where:** `playbook.py:79`, `render.py:394-433`. **Status:** FIXED fix/val14 ef25cfb (merged d1660bd). **Priority:** P2.
- **Fix:** in `_device_lines`, a trio line with no `under` parent takes its depth from
  `playbook.wording.integration_depths`.
- **Test to add:** the shapeless map and rep pair prints depths [1, 2].

#### RND-14. Client wording hard-coded in render.py instead of the Playbook
- **Where:** `render.py:31-35` (`GENERIC_HEADER`), `:35`, `:202` (`_REASON_LEADS`, "because "), `:144-147`, `:164`
  (`ACRONYMS`, `_SMALL_WORDS`, `_NOT_PLURAL`), `:210-216`, `:267` (count labels), `:311-313` (" per ", " and ", "; ").
- **Status:** FIXED fix/rnd14 e3a3ec4 (merged 357a198). **Priority:** P2 contract.
- **Fix:** propose keys `assumption.because`, `assumption.leads`, `quantity.per`, `quantity.and`,
  `quantity.labels{…}`, `header.generic`, `casing.acronyms`, `casing.small_words`; read them in render.
- **Test to add:** with a sample Playbook whose `assumption.because` is "since ", the note reads "…, since …".

### I. Run, review, status, CLI, tools — `src/bms/run.py`, `review.py`, `status.py`, `doctor.py`, `tools/`

#### RUN-1. A family Accept saved after a count change silently erases the change
- **Where:** `review.py:595-596` (`_same_line` family branch: name only), `:619-620` (`merge_decisions` drops the
  "same line"), `:288-291` (JS `buildDecision` family change keeps `others`). **Status:** FIXED fix/run1 5ae12a7 (merged be58630). **Priority:** P0.
- **What happens:** save 1 changes VAV from 4 to 5; the run rewrites and shows 5; the family card comes back
  (JS replaces only `value`, `others` stay); the estimator clicks Accept (save 2); `_same_line` treats the accept as
  the same line as the change and replaces it; the next run prints 4. No card.
- **Fix:** (a) a family `accept` is never the same line as an earlier family `change` (or rebase: keep the change
  and add the accept after it); (b) JS: a family or device count change settles the dispute (`others = []`);
  (c) `buildDecision` emits `count: null` when `parsed.kind !== "number"` so a words-only change is not a count change.
- **Test to add:** `tests/bms/test_review_merge_family.py`: `merge_decisions([SavedDecision(change F 5, 1)],
  [accept F])` keeps the change; `apply_seen` gives 5. Integration `tests/bms/test_run_family_accept.py`: change,
  drive, accept, drive → Job.json count 5, history keeps the change.

#### RUN-2. After a count change, any later rename or delete on that system asks the writer again
- **Where:** `run.py:439-452` (rewrite asked from `job.system(key)` after every decision), `ai.py:1130-1133`
  (prompt lists current device names), `run.py:158-167` (`_count_note` lists accepts too). **Status:** FIXED fix/run2 2aa2cd7 (merged 156514f). **Priority:** P1.
- **Fix:** ask `rewrite_for_count` from the written system with only the family-count changes applied, then
  re-apply that system's device decisions (`apply_seen`, then `keep_deleted`); `_count_note` lists only `action ==
  "change" and count is not None`.
- **Test to add:** `tests/bms/test_run_rewrite_key.py`: after a count change and a finished run, a line rename
  (and separately a family accept) → next `estimate` is "done" with no `write_system` request.

#### RUN-3. A vision-count question refused `max_attempts` times is swallowed
- **Where:** `counts_vision.py:290-295` (`except NoAnswer: return None` catches the `waiting=False` stop),
  `run.py:364-368` (gate is only `transport.waiting > asked`). **Status:** FIXED fix/run3 55be7ab (merged a76c6c4). **Priority:** P0.
- **What happens:** on the 3rd refusal the request and answer are deleted, `ask_sheet` returns None, the run goes
  straight to "write" with skeletons lacking the vision count, no "Stopped:" message; the next run re-asks and goes
  back to "count" after the write answers were spent.
- **Fix:** in `ask_sheet` re-raise a `NoAnswer` whose `waiting` is False (or record it on the transport); in
  `run._estimate` after `cross_check`, return `RunResult("waiting", "count", …, messages=stops)` when any count stop
  was recorded.
- **Test to add:** `tests/bms/test_run_count_stop.py`: patch the vision ask to raise `NoAnswer("Stopped: …",
  waiting=False)` → stage "count" with the message, no `write_system` request.

#### RUN-4. Print error, locked file or missing job folder: traceback, run state "running" forever
- **Where:** `__main__.py:68-79` (catches nothing), `run.py:316-324` (only `RenderError`). **Status:** FIXED fix/run4 679f243 (merged 2d6c673; ModelError follow-up in 4b). **Priority:** P0.
- **What happens:** a locked Proposal, Price Sheet or Evidence Package → `PermissionError`; `check_fit` and template
  checks → `ValueError`; missing job folder → `FileNotFoundError`. All leave "running" and a traceback; `bms status`
  says "It may still be going". For a `RenderError` the words go only to the run state, not the console, and no
  "Stopped at the render step." line, so `tools/run_job.py stage_of` reports null.
- **Fix:** in `run.estimate` widen to `(RenderError, PermissionError, FileNotFoundError, ValueError)`, write a
  stopped state with the reached stage and a plain message ("Stopped: <file> is open in Word or Excel — close it
  and run again"), re-raise; in `__main__._estimate` catch the same, print the message and "Stopped at the render
  step.", return 1.
- **Test to add:** `tests/bms/test_run_locked_outputs.py`: monkeypatch `run._build` to raise `PermissionError` →
  state not "running", messages name the file, `check().code == 1`; `main([...])` with a missing folder → return 1,
  a `Stopped:` line, no traceback.

#### RUN-5. A device decision on a system the job no longer has is skipped with no card
- **Where:** `review.py:826-832` (`_matches_nothing` False when system absent), `:906-909` (`_device_holds` True when
  `_target` is None). **Status:** FIXED fix/run2 2aa2cd7 (merged 156514f). **Priority:** P1.
- **Fix:** in `_unhonored`, if the decision has `was` (or `family_name`) and `_devices(before, key) is None` and no
  system-level delete covers it, return "decision could not be applied" with `_GONE_OTHER`; same in `_family_holds`
  when `earlier is None`.
- **Test to add:** `tests/bms/test_review_missing_system.py`: remove a system → one must_fix "decision could not be
  applied"; with a system delete in the history → none.

#### RUN-6. `tools/run_job.py status` deletes answers the run never read and counts them as rejections
- **Where:** `tools/run_job.py:174-182` (`waiting_requests`: "present + answer exists" = rejected). **Status:** FIXED fix/run6 a91b6e0 (merged d22e561). **Priority:** P0 data loss.
- **What happens:** an estimate that crashes before `Judge.retire_requests` (`run.py:338`) leaves every request
  next to its fresh answer; `run_job` deletes all those answers, adds an attempt each, and the skill re-dispatches
  (or stops at `max_attempts`).
- **Fix:** mark rejected only when `answer_path.stat().st_mtime_ns <= path.stat().st_mtime_ns` (the app's own rule
  in `ai._answer_is_fresh`); skip rejection detection when the estimate output contains "Traceback".
- **Test to add:** `tests/test_next_batch.py`: a request then a newer answer → answer kept, no `rejected`;
  rewriting the request after the answer → `rejected`.

#### RUN-7. `tools/run_job.py status` crashes on the Windows console encoding before printing its JSON block
- **Where:** `tools/run_job.py:201-203`. **Status:** FIXED fix/run7 fc621c6 (merged 06a02c5). **Priority:** P2 crash.
- **Fix:** at the top of `main`: `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`; same in
  `tools/measure.py`.
- **Test to add:** run `status` with `PYTHONIOENCODING=cp1252` and a fake estimate printing "≥" → parseable JSON block.

#### RUN-8. `run_job`'s attempt counter never resets, so later `/run-job` runs give up at once (= AI-15)
- **Where:** `tools/run_job.py:75-80, 130-132, 180-183`; `.claude/skills/run-job/SKILL.md` steps 3 and 4.
- **Status:** FIXED fix/run7 fc621c6 (merged 06a02c5). **Priority:** P2.
- **Fix:** drop keys with no request in `requests/` and not rejected this time; or report the app's own counter
  (`cache/judge/attempts/<digest>.json`); or reset a key when its request has no `previous_problem`.
- **Test to add:** attempts `{"k": 3}` plus a fresh request `k` → `cmd_status` reports 0.

#### RUN-9. Run state keeps the old decision count after both decision files are deleted
- **Where:** `run.py:426-430` (`known["decisions"] = len(history)` only `if history:`), `:417-419`. **Status:** FIXED fix/run2 2aa2cd7 (merged 156514f). **Priority:** P1.
- **What happens:** save, run (decisions: 1); delete both files, run (still 1); save a new accept, run → false
  "no decisions history.json was found … earlier saves are not applied" note.
- **Fix:** always set `known["decisions"] = len(history)`.
- **Test to add:** `tests/bms/test_run_decisions_reset.py`: the sequence → `decisions == 0` after start-over,
  `messages == ()` on the first new save.

#### RUN-10. No "Wrote <path>" for Job.json, decisions history, run state or count proofs
- **Where:** `run.py:361-362`, `:427, :518, :547`, `:533`. **Status:** FIXED fix/run7 fc621c6 (merged 06a02c5). **Priority:** P2 contract.
- **Fix:** print `Wrote {job_file}` after the final `save`, `Wrote {manifest}` from `publish_proofs`, `Wrote {out /
  DECISIONS_HISTORY}` after `_save_history`.
- **Test to add:** `tests/bms/test_run.py`: a `Wrote` line for each file under `out` the run touched.

#### RUN-11. Nothing stops `--out` or `--cache` from pointing into the repo (NDA)
- **Where:** `__main__.py:43`, `run.py:302-312`. **Status:** FIXED fix/run11 a850cea (merged 34483dc). **Priority:** P0 NDA.
- **Fix:** resolve `out` and `cache`; if either `is_relative_to(ROOT)` and not `is_relative_to(ROOT / "out")`,
  raise `ValueError` with a plain message before writing anything.
- **Test to add:** `tests/bms/test_run_out_guard.py`: `estimate(job, ROOT / "docs" / "tmpx", …)` raises; folder absent.

#### RUN-12. Smaller items (LIKELY)
- **Status:** FIXED: items 1 and 3 fix/run12 24e0afa (merged 7c52d68); items 2, 4, 5 fix/run7 fc621c6 (merged 06a02c5).
1. A locked or unreadable decisions file: `review.py:462`, `:525` catch only decode errors; `OSError` crashes.
   Fix: add `OSError` → plain `ModelError`. Test: monkeypatch `Path.read_text` to raise `PermissionError`.
2. `load_decisions` accepts no-op entries (change with `device: null`, family change with `count: null`, family
   delete, `system_key: ""` with `family_name`). Fix: validate shape, raise `ModelError("decisions[n]: …")`.
3. `_write_run_state` (`run.py:262-275`) gives up on the first `os.replace` failure; on Windows the replace fails
   while `bms status` holds the file open, leaving "running" after a finished run. Fix: retry 5 × 100 ms.
4. `doctor` says "ready" when: `PROPOSAL_TEMPLATE`, `WORKUP_TEMPLATE`, `PRICE_BOOK`, `ALIASES` are missing (never
   checked); Python ≥ 3.10 accepted while pyproject pins 3.13; any non-empty model string passes ("opsu"). Fix:
   asset check, `min_version=(3, 13)`, models in {"opus", "sonnet", "haiku", "fable"}. Test: `tests/bms/test_doctor.py`.
5. `chat_guard` restore (`tools/chat_guard.py:55-57`) rewrites chat.txt whole and non-atomically; a `chat_post`
   append in between is lost, and it writes CRLF while `chat_post` writes LF. Fix: temp file, re-check unchanged,
   `os.replace`, `newline="\n"`.

### J. Test suite

#### TST-1. Growth-timing tests are flaky under machine load
- **Where:** `tests/timing.py` (`grows_linearly`, `growth`); used by `tests/bms/test_review_final3.py:253`
  (`test_grows_linearly_fails_quadratic_work_from_any_starting_size[20]`, failed on this audit's first full run
  while nine review agents loaded the machine), and timing tests in `test_citations_final_c.py`,
  `test_citations_properties.py`, `test_citations_reviews.py`, `test_citations_review_detect2.py`, `test_final_f.py`,
  `test_final_j.py`, `test_playbook_lint_fixes.py`, `test_render.py`.
- **Status:** FIXED fix/run12 24e0afa + fix/run7 fc621c6 (all five items). **Priority:** P2.
- **What happens:** `grows_linearly(_quadratic, 20, attempts=1)` returned True. With `MIN_BASE = 0.03` s the base
  is raised until the small run takes 30 ms; under load, a burst during the base run inflates it so the 4n run looks
  less than 8× slower. The "must fail" direction uses `any(... < limit)` which a single lucky measurement satisfies.
- **Fix:** for the negative tests, require every attempt to exceed the limit (use `all`/`min` growth over 3
  attempts), raise `MIN_BASE` to 0.1 s, and mark the timing tests `@pytest.mark.slow` so they can be deselected
  when the machine is busy. Do not loosen the positive (linear) direction.
- **Test to add:** none new; make `tests/test_timing_helper.py` assert the quadratic case fails with `attempts=3`
  under an artificial 2× jitter on the base run.

---

## 4b. Follow-ups found while fixing (2026-10-07)

- After CNT-2: a vision answer with SOME boxes inside the tile and some outside still drops the outside ones
  (partial undercount on that sheet). Refusing any misplaced box needs `test_count_tags_drops_a_box_outside_its_tile`
  changed. P1.
- After LDG-1: a sequence answer that matches a heading but cites an S id (not the section's Q id) still takes the
  first section with that heading, and `ledger.resolve` then replaces the fact's Q id with the S id. P2.
- After PLN-2/5: with several damper families, an untagged damper link gives the fan a "Motorized Damper" family
  and reduces no family (overcount, no question asking which family). P2.
- After RD-4: the copy flag names documents by file name only, so "Mech.pdf repeats Mech.pdf" for `Mech.pdf` and
  `Rev 1/Mech.pdf` (ambiguous; same root as LDG-10). P2.
- After RD-1: (being fixed in the same branch) type-only quantity schedules in two versions.
- After CNT-3: a placed "EF-1-A" in a family numbered only (EF-1, EF-2) is no longer read as EF-1 by the sheet-text
  cross-check (it was before). Cross-check only; the printed count takes the highest. Watch on a real job. P2.
- After RUN-4: a `ModelError` from the pipeline still leaves the run state "running" (pinned by
  `test_status_review.py::test_a_model_error_from_the_pipeline_still_raises`). P2.
- Lead, 2026-10-07: `test_reading_job.py::test_a_cache_file_cut_short_is_read_again` failed once under load
  (schedules empty on the re-read). Cause: a cache WRITE (`os.replace` PermissionError), the document hash, or a
  momentary PDF lock raised after a good read, and the schedules reader dropped the page for that run; a failed
  open was remembered for the whole run. Fixed in fix/cachefail 6fd44e9 (retries; a cache write never raises).
  Left: `catalogue/register.py` `_store` `os.replace` can still raise (loud, not silent). P2.
- After AI-3/4: quotes are now checked word for word (case and punctuation aside) against the evidence sent; a
  writer that joins a schedule header with a cell value would be refused. Watch the refusal rate on the first real
  run. An id whose passage was cut by the evidence length limits is checked only by the run-level recheck.
  `ai.quote_findings` is new and not yet in the interfaces doc. P2.
- After RD-3: interfaces doc needs `Supersession.floors` and `typical_sheets(..., supersessions=())`. Edge cases
  (all overcount, flagged): a 2-page reissue with different page texts gets the carried floors on each page; a
  reissue title naming more floors wins but the flag still says the base number. P2 docs.
- After PLN-1/LDG-4: no change log for non-unit kinds a pass overwrites ("F5 … changed from … to …"; needs a
  notes field). A plans-pass tag another family also lists can land in two blocks (overcount). P2.
- After CNT-6/8: a mostly-picture plan always goes to full-tile vision (its located count becomes unknown even
  when its OCR text shows tags); a vector plan over a raster background with no family tags is now asked (cost);
  `_mostly_picture` opens each plan sheet's PDF once (speed on large sets); a crop that rejects an ambiguous box
  never triggers a second full-tile question. Watch cost on the first real run. P2.
- After AI-1: a line citing no count source that the rewrite answer leaves at the old family count is not lifted by
  the safety net and no finding catches it. P2.
- After RND-9/11: proposed optional wording.json key `"alternate_label": "ALT #{k}: {name}"` (estimator to add if
  wanted; renderer defaults to the same text); interfaces doc's Wording line lacks `alternate_label`. An orphan
  sub-line device still prints at depth 1 with no verb (RND-11 related note, no fix given). P2.
- After LDG-10: still named by file name only when two documents share a name: `picture_place` in
  `bms/counts.py`, the left-out pictures list in `ledger/run.py`, other `job.py` flags (unreadable or blank pages,
  missing sheet numbers), the backbone where in `reading/sequences.py`. P2.
- After CNT-4/5/7: the located count does not multiply by typical floors (a typical plan reads lower: a cross-check
  other only); a vision answer covering only some patterns is accepted (by design, pinned by
  `test_a_pattern_the_answer_leaves_out_gets_no_vision_count`). P2.
- After RND-5 (for the estimator, wording.json is theirs): proposed optional key
  `"quantity": {"unlabelled": "elsewhere in the documents"}` (the code defaults to these words), and new text for
  the `$format.quantity.others_note` description: "... the printed (highest) count first and every other count
  highest first, none dropped; ... a count with no label prints as "N elsewhere in the documents" (the optional key
  quantity.unlabelled), never "per the documents"; in a block with more than one family each family's part opens
  with the family name; ...". Today's description still says "at most five clauses" and "a count with no label is
  left out" (stale since ruling D6).
- After AI-2/10/16: an answer line with a kept line's id and slot but new words is taken as an unasked edit and
  put back (a replacement under the old id is lost); the count-rewrite prompt still says "do not add a replacement"
  though an added line is now kept; `revise_system.md` still says "Keep the clarification and the tech hours unless
  a finding is about them" while the code now restores them whenever every finding names a device; in
  `run._untouched` a phantom-device finding (device_id None) counts as fixed by any change to the block. P2.
- After VAL-1..18: a DDC controller written into `other_device` on a packaged unit gets only the check; a family
  with value None and another count gets both VAL-18's must_fix and `_unknown`'s check (redundant). P2.
- Lead, 2026-10-07: the prompt rule-name reader used by `bms doctor` (and the rule-names check) takes the
  apostrophe in "the Playbook's" as an opening quote, so "the Playbook's default (" read as a rule name and failed
  doctor. Worked around in the prompt wording (1c251f0); the reader itself should ignore an apostrophe inside a
  word. P2.
- After AI-17: "another system's passage" is recognised from the dossier's sequence headings and schedule titles
  (the `evidence_for(system, dossier)` signature is pinned, so other systems' names are not passed in); a system
  named in neither is not caught. P2.
- After PLN-4/6/7/8: a unit tagged EDH but named neither a heater nor a general word no longer counts as a duct
  heater (no fixture has one). P2.
- After RD-8: under an input folder not named Takeoffs / Project Documents, a first folder is a revision only when
  named like one (Rev, Addendum, Bulletin, IFC, a date ...); a bare "23-09" or "1.5" reads as a dated revision.
  "Takeoffs/Mechanical/" now gives revision "base" (was "Mechanical"). Watch on the first real job. P2.
- After RUN-5: the missing-system card is a system-level "decision not honored" check with no Delete button; it
  shows on every run until the decision files are cleared. P2.
- After CNT-9: the vision count's `untagged_symbols` is read into `CountResult.untagged` and saved as
  `vision_untagged` in proofs.json, but neither the review page nor the Evidence Package shows it (a possible
  undercount the estimator cannot see). A family spread over several sheets still gets a whole-sheet question on
  every sheet (job-wide count vs one sheet's located count: cost, not accuracy). Interfaces doc lists
  `CountResult (value, boxes)` without `untagged`. P1/P2.
- After PLN-9/11/12: `src/estimator/ledger/to_plan.py` (old planner) keeps its own old-form `_MEMBER`/`_TIMES`/
  `_TAG_TIMES`; the "names no family" group question may fire on descriptive pieces of AI-written group facts
  (watch on the first real job); if an earlier group takes a family whole, a later group's part of it is skipped
  with no question (no count lost). P2.
- After RD-6/7/10/11: the copy rule (`document_repeats`) still compares raw sheet numbers (M-101 vs M101 never
  a copy pair: summed, the safe side); "M.101" and "M101" stay separate (D8 does not cover a dot after the
  letters); a job with no four-digit revision date still reads two-digit years by the wall clock; the drawing
  index's title source is not recorded per document. P2.
- After VAL-10/12/19: VAL-19 findings are filed under "Packaged units" (the closer heading "Point lines only on AME
  controllers" would need a new rule key and break `test_every_check_has_a_trigger`); two stricter Playbook verb
  cases are not flagged ("Furnish and Install" where AME does not wire; "Wire" where AME installs) — could be checks.
  P2.
- Lead: the review page lists the planner's and the counts' questions under "Open questions for the client",
  though most are for the estimator (count confirmations, untagged symbols). Heading or split to decide with the
  estimator. P2.
- After VAL-20 (partial): source-id hits in names, places, exceptions and the no-lines reason stay filed under
  "Assumption wording has no source ids" (moving them to "Words the client never sees" breaks six tests and needs
  run.py's revise filter to accept both names): cosmetic, left. For the estimator, proposed rules.md sentence under
  "Every assumption says why" / "One clarification per block": "An assumption is at most about 25 words and a
  clarification at most about 40; the validator flags any over 220 characters." P2.
- After PBK-9, Playbook proposals for the estimator (shapes.json): narrow kind word "global" to "global point"
  ("Fire Alarm Global Shutdown" still gives Global Points); add kind words or prefixes for names that get no shape:
  Boilers, Chillers, Cooling Towers, "Roof Top Units" (two words), Make-Up Air Units, Air Handlers, Smoke Dampers,
  CRAC Units ("crac" is a prefix but not a kind word); optional kind word "kitchen exhaust fan". No longer needed:
  moving VAV below AHU. The code now treats overlapping kind words as one phrase ("kitchen exhaust" beats
  "exhaust fan").
- After RND-14, optional wording.json keys for the estimator (defaults = today's text, so adding them changes
  nothing): `assumption.because` "because ", `assumption.leads` ["as ", "since ", "given that ", "because "],
  `header.generic` "Qty ({n}) {name} {tags}", `quantity.per` " per ", `quantity.and` " and ", `quantity.joiner`
  "; ", `quantity.labels` {plan_placements, schedule_rows, schedule, riser, sheet_pictures}, `casing.acronyms`,
  `casing.small_words`, `casing.not_plural`, `casing.acronym_before` {co, it, fa}. Full JSON in the fix/rnd14 report.
  Still hard-coded: the shapeless line form, co2→CO2, the "({n})" brackets in the count note, the list words
  and/or/no, "left out, no lines written", the clarification joiner; an alternate's label strips a literal leading
  "Qty (...)". Interfaces doc's Wording line lacks the three new fields. P2.
- After LDG-9: the same keynote on two pages of one document is now listed twice (by design; dossier text only).

## 5. Checked and found sound (so nobody re-audits it)

- **model.py:** enumerations match §2.1; `from_dict` strict on unknown keys, types, enums, paths; round trip
  lossless; `schema_errors` agrees with the dataclasses (only documented difference: the schema requires defaulted
  fields); all keywords used by the other schemas are covered.
- **Playbook:** shipped files load and lint clean; every `RULE` value and prompt-quoted name present; `shape_for`
  prefix normalisation and plurals work; lint fences, Latin-1, missing file and BOM'd JSON handled.
- **Planner:** empty ledger no crash; `_natural_key` safe; output order independent of dict/set order; unique
  system keys; `place_seen`, `_unclaimed`, `_join_owner`, `_split_blocks`, `_pair_up`, `family_of_tag`,
  `part_count`, `_schedule_links`, `_front_end`, `Reader.where` depth cap all sound.
- **Counts:** lookbehinds stop RTU-1 in ERTU-1 and VAV-1 in VAV-10; regex metacharacters escaped; tag with no
  number gives no pattern; unreadable PDF or picture gives unknown not 0; tiles cover edges and `_distinct` dedupes
  across tiles; `_merge` never lowers `value`; proof paths Windows-safe and under `out/count-proofs`, atomic;
  deterministic order; C ids do not collide.
- **Citations:** detector catches ids at line start, in parentheses, lower case, trailing punctuation, after `#`,
  `_`, `[`, in `S201/S202`, full-width digits, split by U+200B; leaves `S201ft`, `S201.5`, `1S201`, `S-201`, tags
  and ranges alone; sheet words read; no catastrophic backtracking on 180 KB inputs; `validate(Job("x"))` and
  empty systems do not crash; duplicate ids reported; Finding contract held.
- **AI:** schema strictness at every level; cached answers re-checked; key covers model, rules, instructions,
  prompt and picture bytes, deterministic; file names sha256, UTF-8, atomic; chat freshness, `old/` park, counter
  clear and `max_attempts` stop; API rules block cached, streams, json_schema output, timeouts, `max_tokens` and
  `refusal` stop reasons as no-answer; evidence cut announced; QC device ids checked per system.
- **Render and writers:** pure across `PYTHONHASHSEED`; RenderError on bad header, unknown shape, blank why,
  extend-existing without name, depth over 2; alternates never in base; slot order and sub-lines right; empty
  slots print nothing (ground rule 3 holds); owner brackets from wording; "Qty (##)" header and line forms; tech
  hours reach the price sheet; Word writer round-trips through `read_proposal`; template passes `check_template`;
  Evidence rows match headings; openpyxl 3.1.5 and python-docx 1.2.0 APIs current.
- **Run and review:** Review.html escaping safe (no XSS from `<` in a quote); `proof_image` path checks; run state
  first and last, atomic, ASCII; `status` trust rules and exit codes; history atomic; damaged history and malformed
  decisions.json stop in words; `merge_decisions` idempotent, device rebases right; `keep_deleted` after a count
  rewrite; standing accepts; QC parts all asked; `max_attempts` read fresh; `run_job` parsing of stage and proposal
  lines; skill model mapping; `chat_post` append-only; `measure.py` deterministic.
- **Reading layer:** corrupt, truncated, empty and non-PDF ".pdf" files become "unreadable" without a crash;
  deterministic order; `picture_regions` crops rotated sheets right; spec sections, detail callouts, grids and
  "PLAN 2" rejected as sheet numbers; label reader rules match the guide (alone or starting a short line, reference
  words, 12-word limit, THRU ranges, stated counts, the 50 cap); copy thresholds as stated apart from RD-4;
  supersession title matching and partial-reissue page matching as stated; plan groups (`_one_plan`) as stated;
  caches atomic, every read UTF-8.
- **Ledger and dossier:** dossier text and Ledger JSON identical across hash seeds; JSON round trip equal; section
  parity between `sections_in` and `Dossier.sections`; empty job builds; pictures under `cache/dossier-images`,
  atomic, rotation handled; `PageOpener` keyed by content sha1; judge pass key includes full prompt and picture
  hashes; picture ids stable; `Document.relative` POSIX.
- **Cross-module:** no `open()` or `read_text()` without an encoding in the live app; no bare `except:`.

## 6. Out of scope of this audit

The old writing layer and old CLI (see the top of this file). `estimator.writing.systems` still calls
`_one_copy_per_sheet` with no `others` (RD-1 is worse there) but it is retired code.
