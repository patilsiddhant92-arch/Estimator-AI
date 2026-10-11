# T-005a report: Counting (rulings 1 and 2)

1. Task T-005a, branch `hark/T-005a`, base `origin/lead/wave2` (0e78113). Code commit b1372ea; the report and
   test_final_d_plan_areas commit follows it (branch tip).

## Root cause of AHU 21

`estimator.reading.inventory.plan_count` counted a numbered unit tag once **per plan group** and added the groups
(FINAL-I, "when in doubt sum"). On 26-0544 the penthouse is drawn on four sheets of four trades and titles
(M114.00 ductwork, M214.00 piping, M314.00 equipment, M315.00 roof). Only M114.00 and M214.00 group (ruling L1);
M314.00 and M315.00 read as other floors, so AHU-1..5 counted 3 or 4 times each (20). The demolition sheets
(MD 110.00..MD 315.00, typed "Plans" + "Demolition") were counted like new-work plans everywhere except the
inventory's no-schedule families, so AHU-6 (MD 315.00 only) made 21, EF 10, ERV 3, thermostats 61. Every count
(inventory, dossier counts line, `bms.counts` cross-check C1) uses `plan_count`, so all three agreed on the wrong
number. The fix is in that one rule and in which sheets are read, not in any threshold.

## What changed (file:line on the branch)

- `src/estimator/reading/inventory.py`
  - :507 `plan_buildings`: the building a plan shows (title words BUILDING / BLDG / TOWER / PAVILION and their id, plus
    the document when one sheet number is in two documents). "" for floors, wings, areas and part plans of one building.
  - :529 `plan_count`: **a numbered unit tag counts once in the job** (ruling 2), times the floors its typical
    sheets stand for, once per building. Where the tag is on a typical sheet, a plain plan that also shows it adds
    one floor (FIRST FLOOR beside TYPICAL 2-4 stays 4 per tag: when in doubt the higher). Type tags unchanged (L1).
  - :215 `Placements.demolition` (new, defaulted): demolition sheet -> labels left out.
  - :744-:772 `placements`: demolition sheets (`is_demolition`) are read apart; their units are left out, unless
    `demolition_work` names work on the unit, then they count there. `buildings` passed to `plan_count`.
  - :814 `demolition_work(catalogue, tags)`: tag -> the first line of any page naming the tag and a work word.
  - `_as_type` reason wording: "a unit's tag counts once in the job".
- `src/estimator/catalogue/sheet_types.py` :119 `is_demolition` (type Demolition and no NEW WORK / NEW CONSTRUCTION
  in the title), :127 `work_words`.
- `assets/reading_lists/sheet_types.json`: Demolition also matches "EXISTING TO BE REMOVED"; new keys
  `demolition_new_work`, `demolition_work` (REFURBISH, RECONDITION, RETROFIT, RELOCAT*, REWORK, REBUILD, OVERHAUL,
  UPGRAD*, REPLACE (EXISTING) THERMOSTAT/SENSOR/CONTROLS/VALVE..., NEW (DDC) CONTROLS) and an "about" line.
- `src/estimator/writing/dossier.py` (counts only)
  - :844 demolition plans read apart; :904 work named -> counted; the rest kept in `left_out`.
  - :923 `buildings` into the counts; `_demolition_notes` (:1018) adds to the counts line, with both numbers:
    "AHU-6 is on demolition sheets only (MD 315.00): left out of the count, 5; with the demolition sheets, 6";
    for a type tag "FCU-1 has 3 more labels on demolition sheets (...): left out of the count, 5; with the demolition
    sheets, 8"; and "... counted: the documents name work on it ('<line>')".
  - :1111 `_summed_notes`: a unit's tag on 2+ plan sheets is named as a duplicate with both numbers: "AHU-1 is on 4
    plans (M114.00, M214.00, M314.00 …), counted once, 1: a numbered unit tag is one unit in the job, the other labels
    are duplicates; if each plan's AHU-1 is its own unit (a type used once per plan), 4: check the schedule's quantity".
  - :1166 `_group_notes` skips a group note whose two numbers are equal (unit tags only).
- `src/bms/counts.py` :274/:290 the cross-check skips demolition plans; :612 `_located_count` passes buildings.
- `src/bms/plan_read.py` :238 `_demolition_text`, :399 a count stated on a demolition sheet's text line is not read.
- `src/estimator/reading/devices.py` (not in my list; minimal, named here): :390 device labels on demolition plans are
  not counted; :155 `_demolition_flags` adds one flag per label with both numbers ("'T' 29 more on demolition sheets
  (MD 111.00, MD 112.00, MD 113.00): left out of the count, 32; with them, 61 — ... check").

No sibling-owned file touched (plan.py, review.py, render.py, write.py, model.py, ai.py, prompts, price sheet).
Note for the merge: T-005d's worktree also edits `src/estimator/writing/dossier.py`; my changes are in `_counts`,
`_demolition_notes`, `_summed_notes`, `_group_notes` and the imports.

## Counts reached on 26-0544 (Mech.pdf, read locally, no AI; the PDF is not in git)

| Family | Before | Now | Target |
|---|---|---|---|
| AHU | 21 | 5 (AHU-6 named: left out, 5; with demolition, 6) | 5 |
| EF | 10 | 5 | 5 |
| FCU | 55 | 55 | 55 |
| ERV | 3 | 1 | 1 |
| Thermostats (T) | 61 | 32 (flag: 61 with demolition) | 33 by your and Grok's proposals |

Inventory totals agree (AHU 5, EF 5, ERV 1, FCU 55). P 12 and CV 12 unchanged.

## Tests

- New: `tests/test_t005a_counting.py` (18 tests: sheet typing, `plan_count`, the 26-0544 penthouse shape, overlapping
  part plans, type tags, demolition unit/type/work-named, inventory, removal lines, thermostats, cross-check) and
  `tests/bms/test_t005a_plan_read.py` (2).
- Updated to the new rule (each edit commented "T-005a"): test_count_cause_note, test_dossier, test_dossier_plan_areas,
  test_final_d_count_causes, test_final_d_plan_areas, test_final_g/h/i/n_counts, test_inventory, test_inventory_same_floor,
  test_review_final2/6/7/8_counts, bms/test_counts, bms/test_count_added_up (its fixture now uses a QTY-column
  schedule so the planner's L1-sum tests still exercise a sum, which only type rows carry now).
- Full suite (`-n 2 -p no:cacheprovider`, run in 4 file chunks on the code commit, PYTHONPATH=src): 4826 passed,
  10 skipped, 10 failed. 9 of the failures are accepted baseline tests: the 5 tests/bms/test_ai.py chat tests,
  test_assets project python, test_main open output folder, test_review_final3 resource code. The 10th was
  tests/test_final_d_plan_areas.py (two asserts of the old summing rule); it is updated in the report commit and
  passes (6/6). The revert_audit, revert_audit_review and status_review baseline tests passed in this run.

## What I did not do, and why

- "(D)AHU-6" (the demolition prefix glued to the tag) is not read as a label by `catalogue.tags.plan_labels`; on
  26-0544 AHU-6 still reaches the counts line from "TO AHU-6" on MD 315.00. Not changed: tags.py is not mine.
- A family seen only on demolition sheets (no schedule row, no new-work plan) gets no counts line, so its left-out
  units are not named anywhere. I did not create zero-count families (they could become systems).
- Device labels on a demolition plan are always left out (with the flag); a note that relocates thermostats does not
  bring them back, because a device label carries no unit tag to match the note to.
- Thermostats: 32, not 33. I did not find the 33rd; it may be a T on a detail or schedule sheet, or a label the
  reader misses. Worth one look by the estimator.
- Inventory item reasons do not yet mention demolition sheets (`Placements.demolition` is filled for later use).
- No schedule-first reconciliation beyond what exists: with unit tags counted once, schedule rows and plan counts
  now agree on 26-0544; T-004 answer 6 is otherwise unchanged.

## Proposed Playbook changes (not edited)

1. rules.md, counting: "A numbered unit tag (AHU-1, EF-3) is one unit in the whole job, however many plan sheets show
   it (other trades' plans, overlapping part plans, other floors). Only a type tag counts per placement. A job of
   several buildings counts a reused tag once per building the sheet titles name."
2. rules.md, demolition: "Demolition plans (DEMOLITION, DEMO, REMOVAL, EXISTING TO BE REMOVED) are never counted,
   unless the documents name work on the unit (refurbish, relocate its sensors or thermostats, new controls). A unit
   left out is named in the Evidence Package with both numbers. Demolition WORK the documents call for prints as
   removal lines" (the addendum's point; T-005b/d own the lines).
3. The duplicate labels of one unit are evidence notes, not a '*' count note on the proposal.

## Questions

1. Wings: two wings of one building reuse tags as one unit now (part plans). If a job's wings number their units
   separately (VAV-1 in each wing), should WING count like a building?
2. CV-11/CV-12 and P-11/P-12 on M630.00 list "AHU-6" in their serves column. AHU-6 is demolition-only on the plans.
   Is AHU-6 kept with new valves and pumps (then work is named on it and it counts), or are these schedule leftovers?
3. Should demolition-sheet thermostats come back when a general note says thermostats are relocated (no tag on the
   note)? Today they stay out with a flag giving both numbers.

## Regression fixtures (NOTES 2026-10-11 rule 4) and seams (rule 5)

- `tests/bms/fixtures/t005a_counting.json`: an invented copy of the two 26-0544 counting defects (same tag forms
  AHU-n / FCU-n, same sheet-number form Mnnn.00 / MD nnn.00, same title forms; invented names and numbers): four
  units on four penthouse plans of four trades, a unit drawn only on a demolition roof plan, a type tag with labels on
  a demolition floor plan, a note naming work on the demolition unit, and a removal-only note.
- `tests/bms/test_t005a_fixture_regressions.py` (10 tests) reads it:
  - defect 1 (a unit on four plans counted 4x): `test_fixture_unit_on_four_penthouse_plans_counts_once`,
    `test_fixture_inventory_counts_each_unit_once`;
  - defect 2 (a demolition-only unit counted): `test_fixture_demolition_only_unit_is_left_out_with_both_numbers`,
    `test_fixture_type_tag_labels_on_a_demolition_plan_are_left_out`,
    `test_fixture_demolition_unit_with_work_named_is_counted`, `test_fixture_removal_line_names_no_work`,
    `test_fixture_inventory_leaves_the_demolition_unit_out`;
  - rule 5, the seams are kept and callable with explicit sources (none was folded away; no code changed):
    `test_seam_placements_reads_only_the_pages_it_is_given` (`inventory.placements(..., pages=...)`),
    `test_seam_plan_count_takes_explicit_groups` (`inventory.plan_count(..., groups=...)`),
    `test_seam_plan_read_count_takes_an_explicit_list_of_sources` (`plan_read.Reader._count(facts, extra)`).
- The inline tests in `tests/test_t005a_counting.py` stay as they are. Note: they use the job's own sheet numbers
  (M114.00, M214.00, M314.00, M315.00, MD 315.00); the new fixture uses invented ones.

## Tests (NOTES 2026-10-11 rule 3)

Run on this commit, PYTHONPATH=src, `-p no:cacheprovider`:

- Files changed: `pytest tests/bms/test_t005a_fixture_regressions.py tests/bms/test_t005a_plan_read.py -q -n 2`
  -> `12 passed in 3.53s`
- `pytest tests/bms -q -n 2 -p no:cacheprovider` (one run, not chunked; this also re-verifies the code commit b1372ea
  and the report commit 2d93d06):
  `6 failed, 2513 passed, 2 skipped, 178 warnings in 340.02s (0:05:40)`
  - **tests/bms pass count: 2513.**
  - All 6 failures are accepted baseline: 4 `test_ai.py` chat tests (`test_chat_refuses_an_answer_that_breaks_the_schema`,
    `test_a_cached_answer_clears_a_request_left_behind_by_a_killed_run`, `test_every_cleanup_is_logged_beside_the_cache`,
    `test_write_system_through_the_chat_rejects_and_asks_again`; the 5th chat test passed this time),
    `test_review_final3` resource code, `test_status_review` normal-exit. No revert_audit test failed.
