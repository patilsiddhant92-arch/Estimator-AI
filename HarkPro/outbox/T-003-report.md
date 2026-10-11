# T-003 report

1. Task T-003, branch hark/T-003, base origin/rebuild at ce07960. Last code commit: 97eb2b3; this report is the branch tip.
   Range reviewed: 8ccd0b3..ce07960 (merges fix1010/ws1, ws23, ws6, countsum, rv-read, rv-bms).

2. What I changed (all in `src/bms/review.py`, the count box; no file under the Limits touched; no lead-owned file touched)
- `_LEADING_COUNT`, `_UNKNOWN_COUNT`, `_COUNT_NAME`: case folding on ASCII letters only (`re.ASCII`), as the page's
  RegExp "i" does.
- `LEADING_COUNT_PATTERN` and `_typed_count`: the spaces are the page's JavaScript spaces, written out once
  (`_JS_SPACE_CLASS`, `JS_SPACES`); `strip()` became `strip(JS_SPACES)` (the page's `trim()`).
- `LEADING_COUNT_PATTERN`, `_COUNT_NAME`: a number is at most 15 digits (what `parseInt` holds exactly).

3. Defects (one commit each, failing test first)

D1. Case folding: Python and the page disagree, and Python raises. `src/bms/review.py:301-302` (at ce07960):
    `re.IGNORECASE` folds "ſ" (U+017F), "ı" (U+0131), "İ" (U+0130) and the Kelvin sign onto ASCII; JavaScript's
    RegExp "i" (no "u") does not. "ſix" / "fıve" was a count in Python and words on the page, and
    `NUMBER_WORDS.index("ſix")` raised ValueError at `review.py:318`. "5 unitſ" was 5 in Python, words on the page.
    Tests: `tests/bms/test_review_typed_count_parity.py::test_python_never_raises_on_a_letter_it_folds_onto_ascii`,
    `::test_a_non_ascii_letter_is_no_count_word_and_no_unit_word`, `::test_the_page_and_python_agree_on_folded_letters_and_space_characters`.
    Commit 5b0f45d.

D2. Spaces: Python and the page disagree. `src/bms/review.py:299-300` and `:309` (at ce07960): Python's `\s` and
    `strip()` take U+001C to U+001F and U+0085, which JavaScript's `\s` / `trim()` do not, and do not take U+FEFF,
    which JavaScript does. "5\x85units" was 5 in Python and words on the page; "\ufeff5" words in Python and 5 on the
    page. (After D1's `re.ASCII`, U+00A0 and U+2003 would also have differed; D2 covers them.)
    Tests: `::test_python_takes_the_spaces_the_page_takes_and_no_other`, the parity test above. Commit c3481f5.

D3. Long numbers: Python and the page disagree, and Python raises. `src/bms/review.py:299` / `:318` (at ce07960):
    `[0-9]+` with `int()` keeps every digit; the page's `parseInt` rounds past 2**53 ("99999999999999999999" is
    1e20 there). Python's `int()` raises ValueError on more than 4300 digits. A count is now at most 15 digits on both
    sides; a longer one is words (the page says it cannot read a count).
    Tests: `::test_python_never_raises_on_a_very_long_number`, `::test_a_count_is_at_most_fifteen_digits`,
    `::test_the_page_and_python_agree_on_long_numbers`. Commit 44cfd56.

D4. The older-page count name raises on the same texts. `src/bms/review.py:836-837` and `:853` (at ce07960):
    `_COUNT_NAME` (an older page's "2 units" saved as a line's new name) had the same `re.IGNORECASE` and `[0-9]+`:
    a saved name "ſix units" or a 5000-digit "… units" raised ValueError in `_read_count_name`, which
    `history`/`apply_decisions` call on every saved decision, so the whole run stopped reading decisions.json. Now
    ASCII folding and at most 15 digits, as the count box: such a name stays a rename.
    Tests: `tests/bms/test_review_older_count_name_safe.py` (both tests). Commit 97eb2b3.

Tests added: `tests/bms/test_review_typed_count_parity.py` (9 tests, 33 cases),
`tests/bms/test_review_older_count_name_safe.py` (2 tests, 11 cases).

Full suite
- Clean export of ce07960 (`git archive`, no .git), `-n 2`: 10 failed, 4409 passed, 10 skipped. 9 of the 10 are in
  the 12 baseline (5 test_ai chat, test_assets python pin, test_main open folder, test_review_final3 resource code,
  test_status_review normal exit). The 10th, `tests/test_revert_audit.py::test_a_new_test_that_passes_without_the_code_is_vacuous`,
  is not in the baseline list: it passes alone (`tests/test_revert_audit.py`: 2 passed). It is a revert-audit test
  that runs pytest in a child process, the same kind as the baseline's revert-audit tests that fail under load (the
  T-002 suite ran on the same 2 CPUs at the same time).
- hark/T-003 at 44cfd56 (D1 to D3), `-n 2`: 10 failed, 4442 passed, 10 skipped (the 33 new parity cases pass). All 10
  failures are in the 12 baseline: 5 test_ai chat, test_assets python pin, test_main open folder, test_review_final3
  resource code, test_revert_audit tools change, test_revert_audit_review utf8 bom.
- After D4 (97eb2b3): `tests/bms/test_review*.py` 635 passed, 1 failed (test_review_final3 resource code, baseline);
  `test_review_older_count_name_safe.py`, `test_review_typed_count_parity.py`, `test_review_typed_counts.py`,
  `test_count_added_up.py`, `test_run_older_page_words.py`, `test_run.py` all pass.
- hark/T-003 at 97eb2b3 (all fixes), `-n 2`: 11 failed, 4453 passed, 10 skipped. All 11 are in the 12 baseline
  (5 test_ai chat, test_assets python pin, test_main open folder, test_review_final3 resource code, test_status_review
  normal exit, test_revert_audit tools change, test_revert_audit_review class test). No failure outside the baseline.

4. What I checked and found correct
- Ruling L1, inventory (`inventory.py` `plan_groups`, `_same_floor_and_area`, `_place_facts`, `placements`,
  `_as_type`, `build_inventory`, `_totals`): every place that uses `Placements.count` after grouping also carries
  `summed` / `each_place_summed`, and each lowered item says both numbers in its reason with action "confirm";
  `FamilyTotal.summed` and its flag carry the family sum. A series row ("A THRU C") gets no sum, correctly (its tags
  are the count). The twin rule (two sheets of one trade and one title on a floor stop the whole floor from grouping)
  is applied before rule (1). Synonyms (DUCT/DUCTWORK, BAS/CONTROLS) are one trade, so halves titled two ways are
  twins. Parts (TOWER, WING, NORTH, 1 OF 2), other words (DEMOLITION, NEW WORK, KITCHEN) and enlarged/partial plans
  keep sheets apart. A title with a colon or a document name with ", " only stops grouping (counts are then summed:
  the safe side).
- Ruling L1, planner (`plan_read.py` `_stated_on_plans`, `_family_count`, `_with_sum`, `_total_sum`; `plan.py`
  `added_up_counts`, `_reduced`, `_left_out`): the stated counts take each tag's highest per group, summed over
  groups; `AddedUp` keeps both numbers whenever the sum is above. `Count.added_up` is set only above `highest()`.
  When a block carries the family's own count its "*" note names the sum; a family split between blocks (or
  `_reduced`) gets one planner question naming both numbers and where each is; a family with both sums is asked
  once. I found no case where a printed count goes below a source count with neither a "*" note nor a question.
- Ruling L1, counts check (`counts.py` `_plan_groups`, `_merge`): groups every plan sheet of the job (so a tagless
  twin still blocks grouping, as in the dossier); `_merge` keeps `added_up` only while it is above the merged
  highest, and never lowers or raises the count.
- `Count.added_up`: `highest()` ignores it (model, read only); `render._count_part` names it last, only when above
  the printed number, and `_line_counts` strips it from device copies so it is named once per family; `evidence._others`
  names it only when above; review cards and `_count_html` name both numbers only when above (`_adds_up`); a typed
  count clears it on both sides (JS `buildDecision`, Python `_new_count`, `_read_count_name`); `validate._count_problems`
  never reads it. It is never printed as the count anywhere I found.
- Air-outlet schedules (`schedules.py` `lists_air_devices`, `_passive`, `_passive_flags`, the OCR-text path;
  `inventory.air_outlet_codes` / `air_outlet_notes`; `dossier.py` `air_codes`, `_unindexed_plan_tags`): a schedule
  set aside by anything but its title is always flagged; one set aside by its title is flagged when its key column
  holds a known unit tag (EF-1, AHU-1, VAV-1, B-1); a plan tag left out of the dossier's units because an air outlet
  schedule lists it as a code gets a reading note with both numbers (labels, and the count as units), also when its
  prefix has no other unit (`air_only` line); `air_outlet_notes` and the dossier agree on "scheduled" (existing rows
  out on both sides). In the OCR-text path a passive section records no rows, so nothing is excluded from the plans
  (the safe side).
- Review count box: after D1 to D3, `_typed_count` and `parseNumber` agree on every sample in both parity tests,
  including number words, unit words, "##", "Qty (##)", a dot, Unicode spaces and folded letters.

5. What I did not do
- No change to the air-outlet reading: the unknown-prefix gap below is a question, since closing it means either
  growing the equipment list or flagging many diffuser codes.
- No change in plan_read.py, render.py, run.py, ai.py or the other lead-owned files.

6. Questions for the estimator
- Q1 (air outlets). A schedule whose title names air devices is passive whatever its rows say, and its rows are named
  in a flag only when a key cell is a unit tag with a prefix the equipment list knows. "AIR TERMINAL SCHEDULE" is
  passive (only "AIR TERMINAL UNIT(S)" is excluded). Prefixes the list does not know (TU, ATU, FTU, PIU, SDV, HV) are
  then dropped with no flag: a terminal-unit schedule titled "AIR TERMINAL SCHEDULE" with TU-1 to TU-8 gives no unit
  and says nothing. Should (a) these prefixes be added to the equipment list, or (b) a title-set-aside schedule name
  any key cell shaped like a unit tag (two or more letters, a dash, a number) that is not an air outlet code? (b)
  would also name diffuser codes like SA-1 or LRD-1 on many jobs.
- Q2 (counts check). `counts.py` reads every plan sheet of the catalogue, superseded pages included (no
  `governing_pages`). With ruling L1 an old and a reissued page of one plan are "two sheets of one trade and one
  title", so that floor is never grouped in the counts check, while the dossier (governing pages only) groups it.
  The located count is then higher than the dossier's and prints (the safe side, but a possible overcount). Should
  the counts check read only governing pages, as the dossier does?
- Q3 (L1 and the dossier text cap). `plan_read` groups only the plan sheets that 7c gives (capped at
  PLAN_TEXT_TOTAL). If the cap leaves out one of two same-trade sheets of a floor, plan_read groups that floor while
  the inventory does not. Never silent (AddedUp's question names both numbers), but the question then says sheets
  "show one floor and area" that the inventory did not group. Acceptable?
