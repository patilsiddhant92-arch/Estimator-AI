# REFERENCE-NOTES: hark/ref-round2-fixes

Reference branch only (lead reply to T-000, answer 4). Not for merge without the lead's review and tests.

## What this branch is

- Base: `origin/rebuild` at `8ccd0b3`.
- Content: the uncommitted READ / PLAN / DOC / CORE / RUN fixes, the VAV scope fixes and the round-2 fixes
  (front end planned / written / revised; add / deduct alternate read from schedule titles; automatic EXCEPTION
  lines) that sat in Hark's local worktree on branch `hark/fix-all`.
- How it was made: `git diff --binary 7e27873` of that worktree (index + working tree against its HEAD `7e27873`, so
  the evidence-ui commit `7e27873` itself is excluded), applied with `git apply --3way` on a new worktree from
  `origin/rebuild`. 58 files in the diff; 56 applied cleanly (several by direct application), 2 conflicted.
- The Evidence Package redesign is on its own reference branch, `hark/ref-evidence-ui`.

## Conflicts and how they were resolved

The two conflicted files are the ones the evidence-ui redesign rewrote. On `rebuild` they are still the old, short
versions, so the round-2 hunks (written on top of the redesign) had nothing to land on.

1. `src/bms/evidence.py`: kept `rebuild`'s version and ported only what applies to it:
   - `_quantity()` now prints `Count.printed()` instead of `Count.highest()`.
   - Added `quantity()` and `count_flag()` (pure functions on `Count`, copied from the round-2 change) because the new
     test module `tests/bms/test_plan_counts_ruling.py` imports them.
2. `tests/bms/test_bms_evidence.py`: kept `rebuild`'s version. The round-2 edits change tests of the redesign
   (`count_rows`, `quantity_note`, the Counts tab) that do not exist on `rebuild`.
3. `tests/bms/test_plan_counts_ruling.py` (new file from round 2): it imported `count_rows`, which exists only with the
   redesign. Changed the import to `from bms import evidence` and the Counts-row check in
   `test_plan3_a_longer_unit_tag_list_than_the_schedule_is_a_discrepancy` runs only when `evidence.count_rows` exists.
   The plan assertions of that test still run.

## Not resolved (needs the lead)

- **Round-2 Evidence Package hunks not ported**: the Counts tab `count_flag` column, the `quantity_note()` wording
  under the DISCREPANCY / CONFLICT flag, and the Summary tile / per-system "Qty (##)" counts using `printed()`. They
  only make sense on top of `hark/ref-evidence-ui`. If both branches are taken, re-apply these hunks after the
  redesign (they are small; see the round-2 diff of `src/bms/evidence.py` and `tests/bms/test_bms_evidence.py`).
- **Count ruling is out of date.** Round 2 codes the estimator's count ruling of 2026-10-09 (the schedule's count
  prints; other counts are a DISCREPANCY / CONFLICT flag; `Count.basis`, `Count.printed()`). The estimator's rulings
  of 2026-10-10 replace it: **the highest count prints; every other differing count prints in a * note with both
  numbers and sources.** `Count.printed()`, `count_flag()`, `test_plan_counts_ruling.py`, `test_revise_count_basis.py`
  and the related `playbook/rules.md` text must be reworked to the 2026-10-10 rule before any of this is used.
- **Protected files touched.** The diff edits `playbook/rules.md`, `playbook/shapes.json` and the interface spec
  `docs/superpowers/specs/2026-10-04-rebuild-interfaces.md` (inbox rule 4). Kept as-is for reference; the lead
  decides.
- **Evidence-only ruling not checked.** Round 2 predates the 2026-10-10 "evidence only" ruling; the VAV scope and
  automatic front-end / EXCEPTION lines were not re-audited against it.

## Redaction check

Grepped the full staged diff (case-insensitive) for the real job names / numbers listed by the lead. None found;
nothing redacted.

## Full suite

`PYTHONPATH=src .venv/bin/python -m pytest tests -q -p no:cacheprovider -n 2` (Python 3.13.5, Linux, 2 CPUs):

`11 failed, 3923 passed, 10 skipped, 180 warnings in 360.06s (0:06:00)`

Failures: the 9 expected environment failures (5 `tests/bms/test_ai.py` chat tests,
`tests/test_assets.py::test_running_on_the_project_python`,
`tests/test_main.py::test_the_output_folder_being_a_file_that_is_open_is_plain`,
`tests/bms/test_review_final3.py::test_a_real_child_failing_with_the_resource_code_is_run_three_times_then_reported`,
`tests/test_revert_audit_review.py::test_a_new_test_inside_a_class_is_audited`) plus 2 that also fail on an unchanged
`rebuild` in this sandbox: `tests/bms/test_status_review.py::test_every_normal_exit_writes_the_state_whole_and_status_agrees`
and `tests/test_revert_audit_review.py::test_a_test_file_saved_with_a_utf8_bom_is_audited`. No failure is new against
the `rebuild` baseline (which had 12 here: these 11 plus the flaky
`tests/test_revert_audit.py::test_a_tools_change_is_reverted_too`, which passed on this run).
The first run, before `test_plan_counts_ruling.py` was fixed, had a collection error on that module (ImportError on
`count_rows` / `count_flag`).
