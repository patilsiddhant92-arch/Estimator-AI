# T-005c report: proposal and render (rulings 3, 4, 5 and the printing of 7)

1. Task T-005c, branch `hark/T-005c`, base `origin/lead/wave2` (0e78113). Last commit: see `git log hark/T-005c`
   (the commit that adds this file).

## 2. What changed

### Ruling 3: header from the job folder
- `src/estimator/writing/front_end.py:366-385`: new `HEADER_PLACEHOLDER = "***"` and `job_folder(root)`. It walks up
  from the takeoff folder. The job folder is the parent of the folder named `N. Takeoffs` (regex
  `^(\d+[.)])?\s*take[\s-]?offs?$`, case-insensitive). If there is no such folder, it takes the nearest folder at or
  above the takeoff folder whose name opens with a job number (`^\d{2}-\d{3,}`). That second rule keeps the old app
  working, because it is given the job folder itself. If neither exists, it returns None.
- `front_end.py:387-405` `job_header`: Quote # is the text before the first comma of the job folder's name, and
  Reference is the text after it (26-0544 gives "26-0544" and "Monmouth County Courthouse - Rplc of Air Handling &
  Fan Coil Units, NJ"). If there is no job folder, both print `***` and a flag asks for the job number and project
  name. A job folder that has only a number gives Reference `***` and a flag. The takeoff folder's name and
  "[project name]" are never printed. `assets/front_end.json` `header.unnamed_reference` is no longer read for the
  reference.
- `src/estimator/proposal/write.py:173-174` `_set_after_label`: a cover value that contains `***` is painted red.

### Ruling 4: existing BMS, flag line, no front end
- `write.py:41-66`: `STARS`, `ame_bms(name)` and `_paint_red(run)`. `ame_bms` reads AME's three lines from
  `assets/reading_lists/manufacturers.json` "platforms_we_bid" (Honeywell WEBs, Johnson Controls FX / Facility
  Explorer, Niagara / Tridium), so the list is not typed a second time. Each part of a joined name such as
  "Honeywell / Niagara N4" is checked. A bare "Honeywell", a bare "Johnson Controls", Metasys, Schneider and the
  bracket fill-in are not AME's.
- `write.py:257-289` `_set_existing_name` (shared function, used for both the front-end heading and the opening
  sentence): a name that is not AME's prints red as `***<name>***`. This includes `***[existing BMS name]***`.
  AME's names print plain, as before.
- `src/bms/render.py:46-57`: `AME_ONLY_FLAG` = "***AME works only with Honeywell WEBS, Johnson FX (Facility Explorer)
  or Niagara Tridium front ends", and `NO_FRONT_END` = "No front end information found".
- `render.py:863-874` new `_front_end_flags`: adds NO_FRONT_END when the front end has no written line and no
  planner `lines`, and AME_ONLY_FLAG when the documents name an existing BMS that is not AME's. The unnamed fill-in
  gets no flag line, because the planner already asks for the name.
- `render.py:876-` `_front_end` (shared): `front_end=None` now prints the NO_FRONT_END note, red. The flags print as
  red notes after the front end's own notes and are traced in `lines` with system_key "".

### Ruling 5: a long clarification as short points
- `render.py:65-90` new `short_points(text)`. A "*" line longer than 150 characters (`LONG_CLARIFICATION`) is split
  after each sentence (". " before a capital letter, never after an abbreviation such as Mfr./Spec./No./e.g.) and
  after each "; ". The first point stays after the label and every other point goes on its own `- ` line. The points
  are separated by `\n` inside the one note, and `write.py` `_apply` prints each `\n` as a Word line break. No words
  are cut or changed. The quantity "*" note is not split.
- `render.py:720` `_notes` (shared): each kind's "*" line goes through `short_points`.

### Ruling 7, the printing part (the model and render)
- `src/bms/model.py:34-36, 52`: `Mark = Literal["", "future", "notice"]` and `MARKS`.
- `model.py:150-158` Device: `mark: Mark = ""` and `mark_note: str = ""`, both additive. I used a Literal and not
  the bare `str` the brief gives, so `from_dict` and the schema refuse a mark that is not one of those values.
- `model.py:382, 410` `json_schema`: a field with metadata `optional` is left out of "required". Without that, every
  AI answer written before this field (the cached and fixture answers, 101 tests) failed schema_errors with
  "missing mark". The writer may still send both fields.
- `render.py:828-845` `_items` (shared) and new `_with_marks`: a "future" device prints `<line> (<mark_note>)`, or
  `(FUTURE)` when it has no note. The note goes through `ids.without_issued`. "future" and "notice" lines print with
  `Run(red=True)`. `_with_marks` wraps the three callers of `_device_lines`: `printed_texts` (:695), `_system_blocks`
  (:811) and `_front_end` (:881). I did not edit `_device_lines` itself, because T-005e reworks it.
- `src/estimator/scope.py:24` Run: `red: bool = False`. **This file is outside my list (see question 1).** The line
  is character-for-character the same as T-005e's, comment included, so the two branches merge cleanly there.
- `write.py:362-366` `_apply` (shared): `part.red` prints the run in red (FF0000).

### Tests (changed only as the rulings require)
- `tests/bms/fixtures/sample_job.json`: added `"mark": ""` and `"mark_note": ""` to its 14 devices (the round trip is
  lossless).
- `tests/bms/test_contracts.py:179`: "every property required" now leaves out mark and mark_note.
- `tests/test_front_end.py:484`: a number-only job folder expects `***`, not "[project name]" (ruling 3).
- `tests/bms/test_front_end_opening.py:50-61`: "Acme Net" and the fill-in now print as `***Acme Net***` and
  `***[existing BMS name]***` (ruling 4).
- `tests/bms/test_render.py:14, 561, 648`: "Old BMS" now gets the AME_ONLY_FLAG line, and the block-order key list
  skips the front end's "" key (front_end=None now prints the NO_FRONT_END line). T-005e also edits this file.
- `tests/test_write_cover.py:116-119`: the "opening with no red sample" test now uses "Niagara N4" (an AME name, so it
  prints plain) instead of "Acme". The test is about the red sample, not the name.

## 3. Tests added

`tests/bms/test_t005c_proposal.py` (32 tests, invented folders and jobs):
- header: `test_the_header_reads_the_job_folder_that_holds_the_takeoffs` (3 depths),
  `test_the_header_never_prints_the_takeoff_folders_name_or_the_bracket_fill_in`,
  `test_a_job_folder_with_only_its_number_gives_a_red_placeholder_reference_and_a_question`,
  `test_a_job_folder_given_directly_still_reads_its_own_name`, `test_a_placeholder_header_value_prints_red`,
  `test_a_named_header_value_keeps_its_own_colour`
- model: `test_a_device_carries_an_optional_mark_and_mark_note`, `test_a_device_saved_before_the_mark_still_loads`
- ruling 7: `test_a_future_line_prints_its_note_in_brackets_in_red`, `test_a_future_line_with_no_note_still_says_future`,
  `test_a_notice_line_prints_in_red_with_no_bracket`, `test_a_marked_line_in_a_system_block_prints_red_too`,
  `test_a_red_line_and_short_points_print_in_the_document`
- ruling 4: `test_an_existing_bms_that_is_not_one_of_ames_three_gets_one_red_flag_line`,
  `test_one_of_ames_three_gets_no_flag` (6 names), `test_an_unnamed_existing_bms_gets_no_flag_line_the_planner_asks_for_the_name`,
  `test_ame_bms_check`, `test_no_front_end_in_the_documents_prints_no_front_end_information_found`,
  `test_a_front_end_the_documents_call_for_but_no_line_was_written_is_not_called_missing`,
  `test_a_non_ame_existing_bms_prints_red_with_stars_in_the_heading_and_the_opening`,
  `test_the_unnamed_placeholder_prints_red_with_stars`, `test_an_ame_existing_bms_prints_plain`
- ruling 5: `test_a_long_clarification_prints_as_short_points`, `test_a_short_clarification_stays_one_line`,
  `test_an_abbreviation_does_not_split_a_point`

Full suite (`-n 2 -p no:cacheprovider`, run in two chunks):
- `tests/bms`: `9 failed, 2530 passed, 2 skipped`. 7 of the 9 are baseline: the 5 test_ai chat tests,
  test_review_final3 resource code, and test_status_review normal-exit. The other 2 were in test_render (ruling 4:
  the flag line and the front end's "" key). I updated both, and `tests/bms/test_render.py` +
  `test_t005c_proposal.py` then gave `142 passed`.
- the rest (`--ignore=tests/bms`): `3 failed, 2305 passed, 8 skipped`. 2 are baseline: test_assets project python and
  test_main open output folder. The third was test_write_cover's "Acme" name (above). I fixed it, and
  test_write_cover + test_write_scope + test_render + test_t005c_proposal then gave `173 passed`.
- Nothing fails outside the 12 baseline tests. The revert_audit and test_review/revert_audit_review baseline tests
  passed in this run.

## 4. What I did not do, and why
- **The header question does not reach the review page yet.** `job_header` returns the flag, but `bms/run.py:492`
  throws the flags away (`old_header, _ = job_header(...)`). `run.py` is not in my list. The fix is one line: append
  those flags to `job.questions` at `run.py:510`. See question 2.
- **The run's output file names.** With no job folder, the quote is `***`. `run.py:493` `_safe_filename` turns it into
  `---`, so the files would be named "--- Ledger.json" and so on. This only happens in the fallback case.
- A "future" line keeps its normal price-sheet quantity. The ruling does not say whether a FUTURE item is priced, so
  the estimator decides on the review page.
- `assets/front_end.json` `header.unnamed_reference` ("[project name]") is now unused. I did not edit it because
  assets are not in my list.
- I did not touch `_device_lines`, the order or the block format. Those belong to T-005e.

## 5. Proposed Playbook changes (`playbook/wording.json`; the renderer keeps its own words until then)
- `front_end.ame_only_flag`: "***AME works only with Honeywell WEBS, Johnson FX (Facility Explorer) or Niagara Tridium
  front ends"
- `front_end.none_found`: "No front end information found"
- `marks.future_default`: "FUTURE" (printed as "(FUTURE)" when the writer gives no `mark_note`)
- `clarifications.points`: `{"over": 150, "bullet": "- "}`
- rules.md "Front end mode": an existing BMS that is not Honeywell WEBS, Johnson FX or Niagara Tridium prints red
  between *** wherever its name appears, and the front end carries the one flag line. The "[existing BMS name]"
  fill-in prints the same way.

## 6. Questions
1. `src/estimator/scope.py` is not in my list, but red printing needs a field on `Run`. I added
   `red: bool = False`, the same line as T-005e's, so the merge is clean. If you would rather I not touch it, the
   fallback is for `write.py` to paint any run that contains `***` red. That fallback cannot colour a FUTURE or
   notice line, though.
2. May I (or T-005b/d) add the `job_header` flags to `job.questions` in `bms/run.py` (one line near :510), so that a
   missing job folder or project name reaches the review page?
3. Merge note: T-005d's branch has a placeholder `mark: str = ""` / `mark_note: str = ""` on Device (no metadata).
   That hunk will conflict with mine. Please keep mine (the Literal, the docs, and `optional` in the schema) so that
   older answers still pass schema_errors.
4. Does a FUTURE item get priced? Right now it is priced like any other line.
