# T-006 report: takeoff pass, Stage 1

1. Task T-006. Branch `hark/T-006`. Base `origin/takeoff/s1` at 7408ff2. Code tip before this report: 5ab09da. The report commit sits on top of it.

Commits (all authored "Hark (AI)"):
- 76c7328 docs: takeoff pass plan, the amended inbox copy (T-006-plan.md) replaces the branch copy
- bdfc074 takeoff: bms.takeoff, the whole-job takeoff request, its checks and the register (Task 1.3)
- c41ec4c takeoff: the takeoff_job prompt, the plan's text exactly (Task 1.4)
- e285411 takeoff: the takeoff request in both modes: status stage, run-job tool and skill, test answerer (Task 1.5)
- 387f204 run: the takeoff step after the reading; the register is stored on the Job (Task 1.6)
- 5ab09da spec: the takeoff pass in the interfaces (Task 1.7)

2. What changed
- src/bms/takeoff.py (new): the whole-job takeoff request, its answer schema and checks, and the register.
- src/bms/prompts/takeoff_job.md (new): the prompt with the plan's ruling list (morning 1, 2, 6, 7, 8, 9, 10; afternoon 14, 15, 17, 18).
- src/bms/run.py: the takeoff step runs after the reading; the register is stored on the Job. No count changes (Stage 1 is additive).
- src/bms/status.py: a "takeoff" stage.
- tools/run_job.py and .claude/skills/run-job/SKILL.md: the takeoff request kind in both modes.
- docs/superpowers/specs/2026-10-04-rebuild-interfaces.md: the takeoff pass added (Task 1.7, which T-006 names).
- docs/superpowers/plans/2026-10-11-takeoff-pass-plan.md: replaced by the inbox copy.
- Not touched: inventory.py, plan_read.py, plan.py, counts.py, model.py (Task 1.1 is on takeoff/s1). No `Flag` "future" value.

3. Tests added
- tests/bms/test_takeoff.py (22 tests), tests/bms/takeoff_fixture.py (invented fixture and test answerer).
- tests/bms/test_run.py (+66 lines) and tests/bms/test_status.py (+18): the takeoff step and stage.
- tests/bms/test_ai.py::test_run_job_check_holds_a_takeoff_answer_to_its_schema.
- tests/bms/test_status_review.py: one loop now treats "takeoff" like "read" (the takeoff asks before planning).

Test tails (Python 3.13, `PYTHONPATH=src`, from the worktree root, `-n 2`, `-m "not slow"`):

    pytest tests/bms -q
    8 failed, 2594 passed, 2 skipped in 309.69s (0:05:09)

    pytest tests -q -p no:cacheprovider
    12 failed, 4903 passed, 10 skipped in 399.27s (0:06:39)

The 12 failures in the full run:
- 5 tests/bms/test_ai.py chat tests (environment)
- tests/bms/test_review_final3.py::test_a_real_child_failing_with_the_resource_code_is_run_three_times_then_reported (environment)
- tests/test_main.py::test_the_output_folder_being_a_file_that_is_open_is_plain (environment)
- tests/test_assets.py::test_running_on_the_project_python (environment)
- tests/test_revert_audit.py::test_a_tools_change_is_reverted_too (flaky)
- tests/test_revert_audit_review.py::test_a_test_file_saved_with_a_utf8_bom_is_audited (flaky)
- tests/bms/test_status_review.py::test_every_normal_exit_writes_the_state_whole_and_status_agrees (flaky)
- tests/bms/test_review_t005c.py::test_a_takeoff_subfolder_named_takeoff_does_not_become_the_job_folder

Eleven are the known sandbox baseline. The last one is not in my usual baseline list, but it fails the same way on an unchanged `origin/takeoff/s1` (header.quote_number returns "2. Takeoffs", not "26-7102"). It is not caused by this branch.
The baseline test `test_a_new_test_inside_a_class_is_audited` passed in this run (it is environment-sensitive, and it failed alone in a separate check).

I cannot show "zero failures" as the task asks, because these 11 fail here for reasons outside the branch (Linux sandbox, no chat, file locks, Windows exit code, flaky revert-audit timing). On the estimator's Windows PC they should pass; please run both commands there.

4. Not done, and why
- Task 1.1 and 1.2 (model fields, invented fixture): the task says they are on takeoff/s1.
- Stage 2 (T-007): not started.
- No plan point was left unfollowed. No sub-agents were used.

5. Questions
- None.

Co-Authored-By: Hark (AI)
