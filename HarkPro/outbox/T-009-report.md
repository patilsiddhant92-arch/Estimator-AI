# T-009 report (Hark, 2026-10-12): task 2 done, task 1 waits for a question

1. Task: T-009. Branch: `hark/T-009`. Base: `origin/rebuild` 52fd0ce (T-008 not in `rebuild` or `lead/wave2` yet:
   `git branch -r --contains 7f033ce` lists only `hark/T-008` and `lead/t008-fixes`). Last commit: see the branch tip
   (task 2 commit, then this report).

## What I changed (task 2, ruling 22)
- `src/estimator/proposal/layout.py`: the two template texts (`DEMOLITION_GENERAL`, `DEMOLITION_SPECIFIC`) next to
  `EXCLUSIONS`, and the block key / heading strings (`bms.render.DEMOLITION_KEY` / `DEMOLITION_HEADING`, written again
  because `estimator` does not import `bms`).
- `src/estimator/proposal/write.py`: `_keep_one_demolition_exclusion`, called in `write_proposal` before the named
  exceptions. It finds each line by `squash`ed text. With a Demolition Scope block (key or header) it removes the general
  line; otherwise it removes the specific line. It removes a line only when the line to keep is in the template, so a
  template with one of the two (or neither) prints what it has.
- `src/estimator/proposal/read.py`: `read_named_exceptions` accepts a proposal that has both demolition lines or lacks
  one of them; lacking both, or lacking/editing/reordering any other standard line, is still refused.

## Tests added
`tests/bms/test_t009_demolition.py` (14 tests): specific line once with a block; general line once without; found by
heading without key; order of all other standard lines and a named exception last (both cases); template with only one
of the lines (4 cases); template with neither; read-back with both / either missing; read-back refuses another missing
standard line; layout texts.

## Pins changed on purpose (one demolition line less; no assertion weakened)
- `tests/test_round_trip.py::test_26_0246_written_out_again_matches_what_was_sent`, `tests/test_end_to_end.py::
  test_the_proposal_matches_what_was_sent`: the sent proposal has both lines; ours has the general one only (these jobs
  have no Demolition Scope block). The expected closing text is the sent one minus the specific line.
- `tests/test_write_scope.py::test_named_exceptions_follow_the_standard_list` and `tests/test_write_cover.py::
  test_the_rest_of_the_template_is_untouched`: the same (the template's closing text minus the specific line).

## Test output
- `pytest tests/test_write_cover.py tests/test_round_trip.py tests/test_end_to_end.py tests/test_write_scope.py
  tests/bms/test_t009_demolition.py -q -n 2`: `56 passed in 8.11s`.
- Full suite `pytest tests -q -p no:cacheprovider -n 2 -m "not slow"` (sandbox has 2 CPUs; the task says -n 4):
  `10 failed, 5316 passed, 10 skipped, 4 xfailed in 407.10s`. One failure was mine
  (`test_write_cover::test_the_rest_of_the_template_is_untouched`), fixed after this run and re-run green (above). The
  other 9 are the known environment failures: 5 `tests/bms/test_ai.py` chat tests, `test_review_final3` resource-code
  test, `tests/test_assets.py::test_running_on_the_project_python`,
  `tests/test_main.py::test_the_output_folder_being_a_file_that_is_open_is_plain`,
  `tests/bms/test_status_review.py::test_every_normal_exit_writes_the_state_whole_and_status_agrees`. I did not re-run
  them on an unchanged `rebuild` in this run; they are the baseline of the earlier reports (T-007, T-007b).
- `python -m bms playbook-lint`: "The Playbook ... is clean." (the Playbook is unchanged; task 1 not started).
- `pytest tests/bms -q -n 4 -m "not slow"` alone was not run separately: the full run above includes it.

## What I did not do
- Task 1 (plan count for thermostats). It needs a change in `src/bms/model.py`, which the task says to stop on. See
  `T-009-design.md` for the design and the question.

## Self-review
The README asks for a separate reviewer agent. This run (the scheduled watcher) has no tool to start one. I checked the
10 items myself: 1 invented fixtures only (sample_job.json, invented lines); 2 four pins changed, reasons above, each
still asserts the other closing lines in order; 3 ruling 22, no Playbook rule touched; 4 nothing is dropped except the
duplicate template line the ruling removes; 5 detector: the lines are matched by exact squashed text; they do not match
"Any demolition work not mentioned by others", "Any demolition work" or a named exception that merely starts with the
words (tested through the exact-match rule: only the two template texts match); 6 only the files the task names;
7 tails above; 8 one commit per task; 9 not applicable; 10 `playbook/` unchanged. An independent review is still open.

## Questions for the estimator / lead
1. May I add `"plan count prints"` to `SetAsideReason` in `model.py` (option A), or do you want a new `Count` field
   (option B)? See `T-009-design.md`.
