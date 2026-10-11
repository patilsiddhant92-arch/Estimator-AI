# T-007 report: takeoff pass, Stage 2 wiring (plan Tasks 2.1 to 2.5, 2.7, 2.6 reduced)

## 1. Task, branch, commits

- Task: T-007. Branch: `hark/T-007`. Base: `origin/lead/wave2` at 5b1bd74 (it did not move while I worked; checked
  at each push). Last code commit: 53a34b0; the tip is this report's commit.
- Author and committer of every commit: `Hark (AI) <hark-ai@users.noreply.github.com>`; every message ends with
  `Co-Authored-By: Hark (AI)`. Pushed only `hark/T-007` (incrementally, as the inbox update of 02:15 asked). No force-push.

| Commit | Task | What |
|---|---|---|
| f5608f4 | 2.1 | `inventory.placements(groups=)`; `takeoff.admissible_pages`, `area_groups`, `device_tally`; spec |
| 9c9b1a4 | 2.2 | `plan_read.Reader(register=, recount=)`, `takeoff.recount`, `admit`, `count_question`; `plan_job(register=, typicals=)`; `attach` keeps the planner's set-asides; spec |
| 08a0a44 | 2.2 wiring | `run.py` plans with the register and the reading's typicals; `takeoff.attach_device_set_asides`; test_run's Stage 1 test updated; spec §6 |
| 7100b12 | 2.3 | `plan.py`: `serve_units`, `split_by_service`, `register_tags`; spec |
| cc1ad7b (merged 3cb0c0c) | 2.6 reduced | helper t007-26: `render._count_note`, Evidence Package "Set aside" tab |
| 51b8d41 (merged af3f9cc) | 2.4 | helper t007-24: `counts.cross_check` skips sheets with `counts_units` false |
| b7930ed (merged c5e1c7f) | 2.5 | helper t007-25: `takeoff.register_text`, `ai_evidence.evidence(register=)`, `ai.evidence_for` / `system_evidence(register=)`, `run.py`, `write_system.md` rule |
| 0c51ad9 | merge fix | `register_text`'s device line reads Task 2.1's `device_tally` (the helper's interim tally replaced) |
| ae68199 | 2.7 | `test_takeoff_end_to_end` |
| 53a34b0 | test fix | `test_contracts` plan_job signature; `test_run_front_end` plan_job fake passes keywords |

## 2. How the work was split (deviation, the estimator's instruction)

T-007 says "Do not start subagents". At 02:20 the estimator (Siddhant) instructed that T-007 be finished faster
with several agents. Three helper agents each worked in their own worktree off 5b1bd74, committing on a local branch
(no push): t007-24 (Task 2.4), t007-25 (Task 2.5), t007-26 (Task 2.6 reduced). I did 2.1, 2.2, 2.3, the merges,
2.7, the final suites and this report. The three branches merged without conflicts.

## 3. What changed

- `src/estimator/reading/inventory.py`: `placements(..., groups=None)`: given groups replace `plan_groups`.
- `src/bms/takeoff.py`:
  - 2.1: `admissible_pages`, `area_groups` (counted sheets of one area share one tuple; non-counting sheets in no
    group), `aside_reason`, `plural`, `device_tally(devices, sheets, label, sheet_pages=None) -> (kept, [SetAside])`.
  - 2.2: `Recount`, `family_rows`, `counted_tags`, `uncounted_tags`, `recount(catalogue, register, typicals)`,
    `admit(prefix, entries, register, recount)`, `count_question`, `QUESTION`; `attach` keeps the planner's
    set-asides after the register's; `attach_device_set_asides(job, devices, sheet_pages)`.
  - 2.5 (helper): `register_text(job, system, ledger, devices=())`.
- `src/bms/plan_read.py`: `Reader(register=, recount=)`; `_count(..., prefix)` admits through `takeoff.admit`,
  collects `set_aside` and `count_questions`; `family()` drops the register's uncounted tags.
- `src/bms/plan.py`: `plan_job(..., register=None, typicals=())`; `serve_units`, `split_by_service` after
  `link_dampers`; `register_tags` before the systems; the Job carries the register's sheets, units, future items
  and the set-asides; the count questions join the questions.
- `src/bms/run.py`: `plan_job(..., register=register, typicals=reading.typicals)`;
  `takeoff.attach_device_set_asides` after `attach`; (helper) the register text into each writer's evidence, after
  `attach` and `attach_demolition`.
- `src/bms/counts.py` (helper): the plan-sheet filter also drops sheets `job.sheets` marks `counts_units` false.
- `src/bms/ai_evidence.py`, `src/bms/ai.py`, `src/bms/prompts/write_system.md` (helper, Task 2.5).
- `src/bms/render.py`, `src/bms/evidence.py` (helper, Task 2.6 reduced).
- `docs/superpowers/specs/2026-10-04-rebuild-interfaces.md`: §1, §5 Workstream 8 (Stage 2, Tasks 2.1 to 2.5), the
  inventory row, §6 run order.
- Tests: `tests/bms/test_takeoff.py` (2.1, 2.2, 2.3, 2.7), `tests/bms/test_takeoff_crosscheck.py` (2.4),
  `tests/bms/test_takeoff_evidence.py` (2.5), `tests/bms/test_t007_set_aside.py` (2.6); edited outside the plan's
  list (see 6): `tests/bms/test_run.py`, `test_contracts.py`, `test_t005d_writer.py`, `test_run_front_end.py`.

## 4. Proof per task (real output tails, `-n 2`)

- 2.1 at f5608f4, `pytest tests/bms/test_takeoff.py tests/test_inventory.py tests/test_inventory_plan_areas.py tests/test_inventory_same_floor.py -q -p no:cacheprovider -n 2`:
  ```
  120 passed in 3.27s
  ```
- 2.2 at 9c9b1a4, `pytest tests/bms/test_takeoff.py tests/bms/test_*plan*.py -q -p no:cacheprovider -n 2`:
  ```
  333 passed in 4.44s
  ```
- 2.2 wiring at 08a0a44, `pytest tests/bms/test_run.py -q -p no:cacheprovider -n 2 -k "takeoff or demolish"`:
  ```
  3 passed, 6 warnings in 18.87s
  ```
- 2.3 at 7100b12, `pytest tests/bms/test_takeoff.py tests/bms/test_*plan*.py -q -p no:cacheprovider -n 2`:
  ```
  385 passed in 6.56s
  ```
- 2.4 (helper t007-24, 51b8d41), as the helper reported: `test_takeoff_crosscheck.py` 3 passed; `test_counts.py` +
  crosscheck 55 passed; `-k 'count or takeoff or cross'` 895 passed, 0 failed (run in chunks).
- 2.5 (helper t007-25, b7930ed), as reported: `287 passed, 6 warnings in 17.28s` (-k evidence/takeoff/prompt/lint/contract); touched files 110 passed.
- 2.6 (helper t007-26, cc1ad7b), as reported: `test_t007_set_aside` 10 passed; `-k 'render or evidence or review'`
  1218 tests in file chunks, all pass but the two baseline failures (final3 resource code, status_review normal-exit).
- After the merges and the device-line fix (0c51ad9), `pytest tests/bms/test_takeoff.py tests/bms/test_takeoff_evidence.py tests/bms/test_takeoff_crosscheck.py tests/bms/test_t007_set_aside.py -q -p no:cacheprovider -n 2`:
  ```
  71 passed in 3.26s
  ```
- 2.7 at ae68199, `pytest tests/bms/test_takeoff.py tests/bms/test_takeoff_evidence.py -q -p no:cacheprovider`:
  ```
  58 passed in 1.86s
  ```

## 5. Final runs

Both at 53a34b0 (the last code commit; this report adds only the report file).

- `pytest tests/bms -q -n 2 -m "not slow"`:
  ```
  FAILED tests/bms/test_ai.py::test_chat_writes_a_request_then_reads_the_answer_and_caches_it
  FAILED tests/bms/test_ai.py::test_chat_refuses_an_answer_that_breaks_the_schema
  FAILED tests/bms/test_ai.py::test_a_cached_answer_clears_a_request_left_behind_by_a_killed_run
  FAILED tests/bms/test_ai.py::test_every_cleanup_is_logged_beside_the_cache - ...
  FAILED tests/bms/test_ai.py::test_write_system_through_the_chat_rejects_and_asks_again
  FAILED tests/bms/test_review_final3.py::test_a_real_child_failing_with_the_resource_code_is_run_three_times_then_reported
  FAILED tests/bms/test_status_review.py::test_every_normal_exit_writes_the_state_whole_and_status_agrees
  7 failed, 2926 passed, 2 skipped, 4 xfailed, 186 warnings in 386.20s (0:06:26)
  ```
- `pytest tests -q -n 2 -p no:cacheprovider -m "not slow"`:
  ```
  FAILED tests/bms/test_ai.py::test_chat_writes_a_request_then_reads_the_answer_and_caches_it
  FAILED tests/bms/test_ai.py::test_chat_refuses_an_answer_that_breaks_the_schema
  FAILED tests/bms/test_ai.py::test_a_cached_answer_clears_a_request_left_behind_by_a_killed_run
  FAILED tests/bms/test_ai.py::test_every_cleanup_is_logged_beside_the_cache - ...
  FAILED tests/bms/test_ai.py::test_write_system_through_the_chat_rejects_and_asks_again
  FAILED tests/bms/test_review_final3.py::test_a_real_child_failing_with_the_resource_code_is_run_three_times_then_reported
  FAILED tests/test_assets.py::test_running_on_the_project_python - AssertionEr...
  FAILED tests/test_main.py::test_the_output_folder_being_a_file_that_is_open_is_plain
  FAILED tests/test_revert_audit.py::test_a_tools_change_is_reverted_too - Asse...
  FAILED tests/test_revert_audit_review.py::test_a_test_file_saved_with_a_utf8_bom_is_audited
  FAILED tests/test_revert_audit_review.py::test_a_new_test_inside_a_class_is_audited
  FAILED tests/bms/test_status_review.py::test_every_normal_exit_writes_the_state_whole_and_status_agrees
  12 failed, 5260 passed, 10 skipped, 4 xfailed, 208 warnings in 396.67s (0:06:36)
  ```

Every failure is in the accepted environment baseline:
- Clean base 5b1bd74, `pytest tests/bms -q -n 2 -m "not slow"`: `7 failed, 2887 passed, 2 skipped, 4 xfailed, 186
  warnings in 354.39s` with the same seven tests (the five test_ai chat tests, final3 resource code, status_review
  normal-exit). The branch adds 39 bms tests, all passing.
- `test_assets` project python and `test_main` open output folder: accepted baseline.
- revert_audit, load-flaky, confirmed on the base: the two files alone gave on 5b1bd74 `2 failed, 8 passed`
  (test_a_tools_change_is_reverted_too, test_a_new_test_inside_a_class_is_audited) and on the branch `2 failed, 8
  passed` (test_a_test_file_saved_with_a_utf8_bom_is_audited, test_a_new_test_inside_a_class_is_audited): the
  failing tests move between runs on both.
- A first full bms run after the merges found four failures this branch caused (test_contracts plan_job signature;
  three test_run_front_end tests whose plan_job fake took no keywords). 53a34b0 fixes them.

## 6. Acceptance on the invented fixture (`test_takeoff_end_to_end`)

The fixture on the base has no valves, pumps or boiler (the amended Task 1.2 rows never landed: 14 units, not 19).
I did not edit the lead-owned fixture files. The test extends the fixture in memory (`_extended_ledger`,
`_extended_register` in `test_takeoff.py`): CV-1..5 serving AHU-1..5; P-1 chilled water and P-2 hot water,
`with_plant` false; P-3 and P-4 hot water, `with_plant` true, serving B-1; boiler B-1. All invented.

| Item | Result |
|---|---|
| AHU | Qty (5) Air Handling Unit AHU-1 thru 5 |
| EF | Qty (5) Exhaust Fan EF-1 thru 5 |
| ERU | Qty (1) Energy Recovery Unit ERU-1 |
| FCU | Qty (55) Fan Coil Unit FCU-1 |
| Thermostats | 30 kept, 9 set aside (MD-201, "demolition sheet"); the FCU writer evidence says "Thermostats: 30 on the new-work sheets; 9 set aside (demolition sheet)". The printed sensor line is 30 through a stand-in writer (no transport): the real line depends on the AI writer reading that evidence. |
| Valves | Qty (5) Control Valve CV-1 thru 5, a joined header inside the AHU block; no CV block, no valve question |
| Pumps | Two blocks for the remote pumps: Qty (1) Chilled Water Pump P-1, Qty (1) Hot Water Pump P-2. The plant pumps stay in the boiler block: Qty (1) Boiler B-1 then Qty (2) Pump P-3, 4 |
| Demolition Scope | last block: "Qty (1) AHU demo", "Qty (1) EF demo"; AHU-6 and EF-6 in no header or count |
| Questions | no count question on the correct register (printed equals the code's count). On the invented case AHU-5 demolished: one question, "How many AHU units? 4 print from the new-work sheets; the code counted 5." On the invented pre-T-005a ledger (placements 21/16/3): one each for AHU, EF and ERU, none for FCU |
| Job.json | set-asides, units and demolition lines round-trip |

## 7. Plan points I could not follow exactly, and why

1. Subagents: used at the estimator's instruction (section 2).
2. `-n 2`, not `-n 4`: the sandbox has 2 CPUs.
3. Task 2.2's "job.set_aside holds the code's earlier AHU, EF and ERU placement counts": on 5b1bd74 the code's
   placements already give 5, 5 and 1 (T-005a), so the correct register sets nothing aside for those families. I
   prove the set-aside path on an invented ledger whose counts lines say 21, 16 and 3 placements (the pre-T-005a
   numbers), all set aside as "part plan of one area" with both numbers.
4. "The Reader takes register and recount from the Job fields": `plan_job` builds the Job, so it takes them as
   keywords instead (`plan_job(..., register=None, typicals=())`); the run passes the register. The Job then
   carries them, and `attach` after it is idempotent.
5. My addition to `admit`, needed for the plan's own test (AHU-5 demolished prints 4): a number above the register
   count that the family's uncounted units account for (schedule rows 5 with one demolished, cited unit) is set
   aside, reason by status. The plan's rules alone would keep "schedule rows 5" and print 5.
6. `recount` reads the admitted pages intersected with the governing pages (superseded sheets stay out), and applies
   the reading's typicals. The plan names only the admitted pages.
7. Thermostats: `device_tally` keeps a device on a sheet the register does not list. Device set-asides go on the Job
   by a new `takeoff.attach_device_set_asides` in the run; the register text ties a device to a system by area (the
   areas of the sheets its counted units are drawn on).
8. Task 2.3: the text-based `split_pumps` and `link_valves` of T-005b still run; the register's moves come first
   for what the register places. A family moves whole only when all its register units serve one other block.
9. Task 2.6: the review card was skipped (T-005b already gives one card per family; a helper test checks it still
   holds with set-asides). The '*' line names the sheets from the set-aside's where and note; the planner's own
   set-asides cite the counts line ("equipment counts for AHU"), so they print the fallback with both numbers:
   "*AHU counted once on part plans: 21 set aside, 5 counted".
10. Task 2.7: the e2e test also checks the Demolition Scope and the demolition lines in `Job.json` (T-G1 is on the
   base). The live 26-0544 run was not done (the lead's).
11. Files changed outside the plan's list (tests only): `tests/bms/test_run.py` (the Stage 1 test
   `test_takeoff_changes_no_count` is now `test_the_run_plans_with_the_register`: Stage 2 changes counts by
   design), `test_contracts.py` (plan_job and evidence signatures), `test_t005d_writer.py` (helper, evidence
   signature), `test_run_front_end.py` (its plan_job fake passes the keywords through).
12. More than one commit per plan task in places: the 2.2 run wiring, the merge fix of the device line and the test
   fixes are their own commits, and the helpers' work came in as merge commits.

## 8. Questions for the lead

1. Task 2.4 reading (helper t007-24): `cross_check` drops a sheet only when `job.sheets` marks it `counts_units`
   false. A sheet the register does not list is still decided by the catalogue, because the stricter reading (only
   listed counting sheets) broke 12 `test_counts` tests on `sample_job.json`. Confirm.
2. Is the rule of 7.5 (uncounted register units explain a higher schedule number) right? It only applies to
   numbers between the register count and the register count plus the uncounted units.
3. The question names the family by its prefix ("How many AHU units?"). Should it be the family name instead?
4. The recount's reason is "demolition sheet" only when a sheet the code counted is one the register does not count;
   otherwise "part plan of one area". Acceptable?
5. A device is tied to a system by area in the writer's evidence. On a job where two systems share an area (FCUs
   and VAVs on one floor), both see the thermostat line. Keep it, or tie devices by the takeoff (a later register
   field)?
