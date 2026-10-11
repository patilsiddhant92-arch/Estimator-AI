# T-006 report: takeoff pass, Stage 1 (plan Tasks 1.3 to 1.7)

## 1. Task, branch, commits

- Task: T-006. Branch: `hark/T-006`. Base: `origin/takeoff/s1` at 7408ff2.
- Last code commit: 5ab09da. A first, shorter report went out as e9fa1cf. This report replaces it in the next commit. The short one said every plan point was followed and asked no questions; sections 4 and 5 below correct that.

| Commit | What |
|---|---|
| 76c7328 | docs: the plan file replaced by the inbox copy `T-006-plan.md` (byte for byte) |
| bdfc074 | Task 1.3: `src/bms/takeoff.py` and its tests |
| c41ec4c | Task 1.4: `src/bms/prompts/takeoff_job.md` |
| e285411 | Task 1.5: status stage, run-job tool and skill, test answerer |
| 387f204 | Task 1.6: the run step in `src/bms/run.py` |
| 5ab09da | Task 1.7: the interface spec |

Author and committer on all of them: `Hark (AI) <hark-ai@users.noreply.github.com>`. Every message ends with
`Co-Authored-By: Hark (AI)`. I pushed only `hark/T-006`.

## 2. What changed

- `src/bms/takeoff.py` (new): `TAKEOFF_JOB`, `TAKEOFF_LIMIT`, `Takeoff`, `answer_schema`, `prompt`, `check_answer`,
  `take_off`, `attach`, `save` and `load`, as plan Task 1.3 describes.
- `src/bms/prompts/takeoff_job.md` (new): the plan's text. The only change is the quote marks around examples (see 4.2).
- `src/bms/status.py`: stage "takeoff" between "read" and "count". `_KIND_STAGE` and `_STEP_STAGE` have the new entries.
- `tools/run_job.py`: `MAIN_LIST["takeoff_job"] = "units"`, and "takeoff" is in `BMS_STEPS`. The docstring lists the kind.
- `.claude/skills/run-job/SKILL.md`: the `takeoff_job` bullet, `judge_model` for `takeoff_job`, and "takeoff" in the stage list.
- `src/bms/run.py` (lead reviews this first). After the `ledger.complete` return:
  - The run sets `known["stage"] = "takeoff"`.
  - It moves the playbook load and the transport up, unchanged.
  - It calls `takeoff.take_off`. On `ai.NoAnswer` it returns `RunResult("waiting", "takeoff", ...)`.
  - Otherwise it saves `<quote> Takeoff.json` and prints `Wrote <path>`.
  - After the header replace it calls `job = takeoff.attach(job, register)`.
  - The docstring and the stage comment name "takeoff". The new block is labelled "1b" so the later steps keep their numbers.
- `docs/superpowers/specs/2026-10-04-rebuild-interfaces.md`:
  - §1 and §8: the new files.
  - §2.1: the enumerations and `COUNTED_STATUSES`.
  - §2.2: the four classes and the four Job fields.
  - §2.3: the answer schema.
  - §5: Workstream 8, `bms.takeoff`.
  - §6: the run step and stage "takeoff".
  - §7: the takeoff fixture.
  - It states that Stage 1 changes no count.
- `tests/bms/takeoff_fixture.py`: `takeoff_answer(request)`, the run tests' answerer (plan Task 1.5).
- Tests: `tests/bms/test_takeoff.py`, `test_status.py`, `test_ai.py` and `test_run.py`, plus a two-line loop fix in
  `test_status_review.py` (see 4.8).
- Not touched: `inventory.py`, `plan_read.py`, `plan.py`, `counts.py`, `model.py`, the fixture JSON files,
  `sample_job.json`, `test_contracts.py` and the playbook files.

## 3. Tests added

- `test_takeoff.py`. These are the plan's tests:
  - `test_the_request_carries_the_whole_job`
  - `test_the_prompt_is_the_same_twice`
  - `test_a_good_answer_loads`
  - `test_an_answer_with_a_problem_is_refused`: one parametrised test with 11 cases (sheet left out, given twice, unknown; plan with no area; AHU-4 with no row; unknown id F99; wrong quote; MD-401 counting with no ref; two rows for EF-2; serves AHU-12; set-aside citing S77).
  - `test_the_schedule_is_the_floor`
  - `test_counts_do_not_change`
  - `test_save_and_load`
- `test_takeoff.py`, my additions:
  - `test_a_prompt_over_the_limit_stops_in_words`
  - `test_the_answer_schema_is_the_five_lists`
  - `test_a_demolition_sheet_that_counts_is_kept_with_a_ref`
  - `test_a_schema_error_or_a_model_error_is_refused`
  - `test_a_numeric_quantity_column_is_part_of_the_floor`
  - `test_a_refused_answer_raises_no_answer`
  - `test_save_leaves_a_file_that_holds_the_same_register`
  - `test_the_takeoff_prompt_carries_the_amended_ruling_list`
  - `test_the_run_tests_answerer_answers_a_takeoff_request_the_checks_keep`
- `test_status.py`:
  - `test_a_waiting_takeoff_request_reports_the_takeoff_stage`
  - `test_the_takeoff_stage_sorts_between_read_and_count`
- `test_ai.py`: `test_run_job_check_holds_a_takeoff_answer_to_its_schema`. It accepts `answer()` and refuses an answer with no `units`.
- `test_run.py`:
  - `test_a_run_waits_at_takeoff_after_reading`
  - `test_takeoff_changes_no_count`: it compares the saved Job's family counts with `plan_job` plus `cross_check` on the run's own inputs, without a takeoff.

### Proof per task (real output tails)

I ran every proof with `-n 2`, not `-n 10` (see 4.1). Each proof ran at its own commit, in a clean detached checkout.

- Task 1.3 at bdfc074, `pytest tests/bms/test_takeoff.py -q -p no:cacheprovider -n 2`:
  ```
  FAILED tests/bms/test_takeoff.py::test_the_request_carries_the_whole_job - Fi...
  FAILED tests/bms/test_takeoff.py::test_a_good_answer_loads - FileNotFoundErro...
  FAILED tests/bms/test_takeoff.py::test_a_refused_answer_raises_no_answer - Fi...
  FAILED tests/bms/test_takeoff.py::test_counts_do_not_change - FileNotFoundErr...
  FAILED tests/bms/test_takeoff.py::test_save_and_load - FileNotFoundError: [Er...
  5 failed, 24 passed in 64.45s (0:01:04)
  ```
  All five fail with `FileNotFoundError: .../src/bms/prompts/takeoff_job.md`. Task 1.4 adds that file (see 4.3).
- Task 1.4 at c41ec4c, the same command:
  ```
  30 passed in 2.86s
  ```
- Task 1.5 at e285411, `pytest tests/bms/test_status.py tests/bms/test_ai.py -q -p no:cacheprovider -n 2`:
  ```
  FAILED tests/bms/test_ai.py::test_chat_writes_a_request_then_reads_the_answer_and_caches_it
  FAILED tests/bms/test_ai.py::test_chat_refuses_an_answer_that_breaks_the_schema
  FAILED tests/bms/test_ai.py::test_a_cached_answer_clears_a_request_left_behind_by_a_killed_run
  FAILED tests/bms/test_ai.py::test_every_cleanup_is_logged_beside_the_cache - ...
  FAILED tests/bms/test_ai.py::test_write_system_through_the_chat_rejects_and_asks_again
  5 failed, 172 passed, 4 warnings in 14.73s
  ```
  These are the five test_ai chat tests of the accepted environment baseline. The new tests pass.
- Task 1.6 at 387f204, `pytest tests/bms/test_run.py tests/bms/test_takeoff.py -q -p no:cacheprovider -n 2`:
  ```
  60 passed, 44 warnings in 46.39s
  ```
- Task 1.7 at 5ab09da, `pytest tests/bms/test_contracts.py -q -p no:cacheprovider -n 2`:
  ```
  71 passed in 3.42s
  ```

### Final runs at 5ab09da

- `pytest tests/bms -q -n 2 -m "not slow"`:
  ```
  FAILED tests/bms/test_ai.py::test_chat_writes_a_request_then_reads_the_answer_and_caches_it
  FAILED tests/bms/test_ai.py::test_chat_refuses_an_answer_that_breaks_the_schema
  FAILED tests/bms/test_ai.py::test_a_cached_answer_clears_a_request_left_behind_by_a_killed_run
  FAILED tests/bms/test_ai.py::test_every_cleanup_is_logged_beside_the_cache - ...
  FAILED tests/bms/test_ai.py::test_write_system_through_the_chat_rejects_and_asks_again
  FAILED tests/bms/test_review_final3.py::test_a_real_child_failing_with_the_resource_code_is_run_three_times_then_reported
  FAILED tests/bms/test_review_t005c.py::test_a_takeoff_subfolder_named_takeoff_does_not_become_the_job_folder
  FAILED tests/bms/test_status_review.py::test_every_normal_exit_writes_the_state_whole_and_status_agrees
  8 failed, 2594 passed, 2 skipped, 184 warnings in 309.69s (0:05:09)
  ```
- `pytest tests -q -n 2 -p no:cacheprovider -m "not slow"`:
  ```
  FAILED tests/bms/test_ai.py::test_chat_writes_a_request_then_reads_the_answer_and_caches_it
  FAILED tests/bms/test_ai.py::test_chat_refuses_an_answer_that_breaks_the_schema
  FAILED tests/bms/test_ai.py::test_a_cached_answer_clears_a_request_left_behind_by_a_killed_run
  FAILED tests/bms/test_ai.py::test_every_cleanup_is_logged_beside_the_cache - ...
  FAILED tests/bms/test_ai.py::test_write_system_through_the_chat_rejects_and_asks_again
  FAILED tests/bms/test_review_final3.py::test_a_real_child_failing_with_the_resource_code_is_run_three_times_then_reported
  FAILED tests/bms/test_review_t005c.py::test_a_takeoff_subfolder_named_takeoff_does_not_become_the_job_folder
  FAILED tests/test_main.py::test_the_output_folder_being_a_file_that_is_open_is_plain
  FAILED tests/test_revert_audit.py::test_a_tools_change_is_reverted_too - Asse...
  FAILED tests/test_revert_audit_review.py::test_a_test_file_saved_with_a_utf8_bom_is_audited
  FAILED tests/bms/test_status_review.py::test_every_normal_exit_writes_the_state_whole_and_status_agrees
  FAILED tests/test_assets.py::test_running_on_the_project_python - AssertionEr...
  12 failed, 4903 passed, 10 skipped, 206 warnings in 399.27s (0:06:39)
  ```

### Every failure, named

- Accepted environment baseline:
  - The five test_ai chat tests.
  - `test_review_final3` resource code.
  - `test_status_review` normal-exit. It also fails on 7408ff2.
  - `test_assets` project python.
  - `test_main` open output folder.
  - `test_revert_audit` and `test_revert_audit_review`. These are load-flaky. When I ran the two files alone, 7408ff2 gave 3 failures, 3 failures, and then the same 3 again. 5ab09da gave 1 failure on one run and 4 on another. The failures move between runs on both commits.
- Not in the accepted list, but already failing on the base:
  - `tests/bms/test_review_t005c.py::test_a_takeoff_subfolder_named_takeoff_does_not_become_the_job_folder`. It fails the same way on a clean checkout of 7408ff2 (`assert '2. Takeoffs' == '26-7102'`). It is header code from T-005c, which this task does not touch.
- No failure comes from this task.

## 4. Points of the plan I could not follow exactly, and why

1. I used `-n 2`, not `-n 10`. The sandbox has 2 CPUs and two sibling agents.
2. The prompt (Task 1.4) uses “ ” instead of straight quotes around its examples. The words are the plan's, and a test checks that only the quote marks differ. The reason is the Playbook linter: `playbook_lint.prompt_rule_names` reads every capitalised phrase in straight double quotes in `src/bms/prompts/*.md` as a rule citation. With straight quotes, "Demolition Scope", "Level 2 east", "AHU 1" and the "Qty (##) ..." forms failed seven tests: `test_rule_names` and the `test_playbook_lint*` / `pbk` / `run_coverage` lint tests. I fixed the Task 1.4 commit in place, before the first push.
3. The Task 1.3 commit is red on its own. The five tests that ask through `take_off` read `prompts/takeoff_job.md`, which Task 1.4 adds. The plan ties the prompt file to Task 1.4 ("Proof: test 1 of Task 1.3 reads the file"). From c41ec4c on, everything is green.
4. The base does not carry the amended Task 1.1 or Task 1.2, and the task says not to redo them. `takeoff/s1` (7408ff2) has the older model and fixture:
   - No `DemolitionAction`, `DEMOLITION_ACTIONS`, `DEMOLITION_OF`, `DemolitionLine` or `Job.demolition`.
   - No `Unit.with_plant`.
   - `COUNTED_STATUSES = ("new", "relocate")`, where the amendment says `("new",)`.
   - The fixture has 14 units and no pumps P-1..P-4 or boiler B-1.

   So:
   - Test 3 asserts 14 units, not the plan's 19.
   - Test 6 asserts that only `sheets`, `units` and `future_items` change. `set_aside` is `()` in this answer. The Job has no `demolition` field.
   - The floor check reads the model's `COUNTED_STATUSES`, so it follows the lead's change when that lands.
   - The spec describes the model as it is and names the amended items as not in the model yet.
5. The plan says to expand the scheduled tags "with `estimator.writing.write.tag_list`". `tag_list` only compresses tags into a run ("AHU-1 thru 5"); it cannot expand them. The reading already gives one `ScheduleRow` per tag (`schedules.py`: a "A THRU C" row becomes one row per tag with `shares`). So the check uses `row.tag` directly.
6. The schedule floor needs a reason and a cited passage. The plan's test changes only `reason`. The decision says "The AI can set a scheduled row aside only with a cited passage". The check therefore asks for a non-empty `reason` **and** at least one ref whose source is not the unit's own schedule. A fact counts by its own `source_id`; the schedule is matched by the "`<sheet> <title>,`" prefix of the source's where. This applies when a scheduled unit's status is not in `COUNTED_STATUSES`, or when its count is below the floor. The floor is 1 per row, or the row's numeric QTY or QUANTITY column. Its own schedule row alone is refused, and a test pins that.
7. `takeoff.save` returns a bool and leaves a file that already holds the same register; `run.py` prints `Wrote` only when it wrote. The reason is `test_correct_018f::test_f4_a_run_whose_history_cannot_be_saved_stops_in_plain_words`. It makes every `os.replace` fail (it patches `review.os`, which is the `os` module) and expects the run to stop at the decisions history. The plan writes the takeoff through `ai._write_json` on every run, so the run stopped at the takeoff instead. Every later run reads the same cached answer, so an unchanged file is not written again. This is in the Task 1.6 commit, because the run step exposed it.
8. Test answerers (Task 1.5):
   - I added the branch to `test_run._answer`. The answerers in `test_run_front_end.py`, `test_run_revise_count.py` and `test_review_019b.py` call `test_run._answer` for every other kind, so they needed no edit.
   - `test_final_fixes.py:116` only answers write requests after the run has passed the takeoff, so it needed no edit either.
   - `tests/test_whole_job.py` drives the old app, which has no takeoff step.
   - The full suite found two more drivers. The API-mode fake client in `test_run.py` now answers the takeoff schema. `test_status_review.py::test_a_model_error_from_the_pipeline_still_raises` now answers its loop through "read" and "takeoff". That file is not named in the plan; the change is one line, the loop condition.
9. The run step is commented "1b" so that the later step comments keep their numbers. This keeps the `run.py` diff small.
10. The plan does not define "plan-kind". In the check, a plan is `new_work`, `demolition`, `part_plan` or `enlarged_plan`, and needs an area. `riser`, `schedule`, `detail`, `control_diagram` and `other` do not.
11. The "Sheets" lines print `labels: none` when the code found no label, so no line ends with a trailing space. The labels are the code's own tally (`line_labels`), as it stands. That tally does not read "(D)AHU-6", so the AI sees that unit only in the notes and the ledger facts.

## 5. Questions

1. **`with_plant`:** the prompt (Task 1.4, as amended) asks for `with_plant`, but `json_schema(Unit)` on `takeoff/s1` has no such field, and the schema says `additionalProperties: false`. An answer that follows the prompt and sets `with_plant` is refused at the schema check. Will the lead land the amended Task 1.1 (`with_plant`, `DemolitionLine`, `Job.demolition`, `COUNTED_STATUSES = ("new",)`) on this branch's base before the merge? If not, should I take the `with_plant` sentence out of the prompt?
2. Is the floor rule in 4.6 right? It needs a reason plus a ref to a passage other than the unit's own schedule.
3. `test_review_t005c.py::test_a_takeoff_subfolder_named_takeoff_does_not_become_the_job_folder` already fails on 7408ff2. Should it join the accepted baseline, or will T-005c fix it?
