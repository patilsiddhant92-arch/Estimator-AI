# T-000 follow-up: steps from the lead's T-000 reply

Task: T-000 (follow-up). Branch: `hark/T-000`. Base: `276c874` (my T-000 report). Interpreter: Python 3.13.5, Linux,
2 CPUs, `-n 2`.

## A. Reference branches (based on `origin/rebuild` = `8ccd0b3`)

| Branch | Commit | What |
|---|---|---|
| `hark/ref-evidence-ui` | `9a0c8eb` | The Evidence Package redesign (`7e27873` cherry-picked onto `rebuild`). Clean pick, no conflicts: `7e27873`'s only other parent commit (`b8dce01`) is a doc rename. `tests/bms/test_bms_evidence.py` + `tests/bms/test_run.py`: 41 passed. Full suite not run on this branch. |
| `hark/ref-round2-fixes` | `ec1857f` | READ/PLAN/DOC/CORE/RUN fixes, VAV scope fixes, round-2 fixes (front end planned/written/revised, add/deduct alternates from schedule titles, automatic EXCEPTION lines). Diff of the `hark/fix-all` worktree against `7e27873` (evidence-ui excluded), applied with `git apply --3way`. 56 of 58 files clean; `src/bms/evidence.py` and `tests/bms/test_bms_evidence.py` conflicted (they are the files the redesign rewrote) and were resolved toward `rebuild`. `REFERENCE-NOTES.md` at the root lists what was ported and what was not. |

Suite on `hark/ref-round2-fixes`: `11 failed, 3923 passed, 10 skipped, 180 warnings in 360.06s (0:06:00)`. All 11
also fail on unchanged `rebuild` here (see B). No new failure.

Redaction: the full staged diff of both branches was grepped (case-insensitive) for the job names and numbers you
listed. None found; nothing redacted.

Two points for your review (details in `REFERENCE-NOTES.md`):
- **The round-2 count code is out of date.** It codes the 2026-10-09 ruling (the schedule's count prints; others are a
  DISCREPANCY / CONFLICT flag: `Count.basis`, `Count.printed()`, `count_flag()`). The 2026-10-10 ruling replaces it
  (the highest count prints; every other differing count goes in a * note with both numbers and sources). This must
  be reworked before any of it is used.
- The round-2 diff edits `playbook/rules.md`, `playbook/shapes.json` and `docs/superpowers/specs/2026-10-04-rebuild-interfaces.md`
  (inbox rule 4). I kept the edits for reference only.

## B. Rebuild baseline

Clean worktree, detached at `origin/rebuild` `8ccd0b3`:
`PYTHONPATH=src .venv/bin/python -m pytest tests -q -p no:cacheprovider -n 2`

Result: `12 failed, 3751 passed, 10 skipped, 172 warnings in 357.56s (0:05:57)`

The 9 you expect all fail:
1. `tests/bms/test_ai.py::test_chat_writes_a_request_then_reads_the_answer_and_caches_it`
2. `tests/bms/test_ai.py::test_chat_refuses_an_answer_that_breaks_the_schema`
3. `tests/bms/test_ai.py::test_a_cached_answer_clears_a_request_left_behind_by_a_killed_run`
4. `tests/bms/test_ai.py::test_every_cleanup_is_logged_beside_the_cache`
5. `tests/bms/test_ai.py::test_write_system_through_the_chat_rejects_and_asks_again`
6. `tests/test_assets.py::test_running_on_the_project_python`
7. `tests/test_main.py::test_the_output_folder_being_a_file_that_is_open_is_plain`
8. `tests/bms/test_review_final3.py::test_a_real_child_failing_with_the_resource_code_is_run_three_times_then_reported`
9. `tests/test_revert_audit_review.py::test_a_new_test_inside_a_class_is_audited`

**Difference: 3 more failed on unchanged `rebuild` in this run:**
10. `tests/bms/test_status_review.py::test_every_normal_exit_writes_the_state_whole_and_status_agrees`
    (status text says "waiting for 1 answer(s)" where the test expects "run estimate again").
11. `tests/test_revert_audit_review.py::test_a_test_file_saved_with_a_utf8_bom_is_audited`
12. `tests/test_revert_audit.py::test_a_tools_change_is_reverted_too`

10-12 also failed when run alone on `rebuild`. On the `c5d3fa6` worktree, 2 of the 3 failed and 1 passed when run
alone, and 12 passed on the final `hark/ref-round2-fixes` run. So they look flaky in this sandbox, not caused by a
branch. For 11 and 12 the audit reports "PASS vacuous": the test still passes after the code is reverted. My guess,
not checked: the reverted file is rewritten within the same second at the same size, so Python reuses the stale
`.pyc`. My T-000 run on `c5d3fa6` had only the 9.

So on my side, "no failures except the environment failures" means no failure outside these 12 tests, each shown to
fail on unchanged `rebuild` here. Please confirm that, or tell me to look into 10-12.

## C. `hark/harkpro`

Commit `17c52fd` (fast-forward from `f3485b6`), HarkPro/ only:
- `doctrine/rulings.md`: R1 marked **SUPERSEDED 2026-10-10** ("the highest count prints; every other differing count
  prints in a * note with both numbers and sources"). The line-id note now says `lines.json` gives wording, order and
  hours only.
- `doctrine/conflicts.md`: section B and rows C11-C16 marked **SUPERSEDED 2026-10-10** ("evidence only: a line prints
  only when the job's documents show that device; the Master Template gives wording, order and hours only"). C27 (which
  relies on R1) noted.
- `harkpro/qc/checklist.py`: the legacy `required` flag is no longer passed to the critic (dropped from `LINE_KEYS`).
  The docstring says checklists are wording only.
- `qc_prompts/critic.md`: no `required` field. The method check is now "each evidenced device against its family's
  wording". The critic never asks for a line without an evidence item that shows the device. The quantity check
  follows the 2026-10-10 count rule.
- `doctrine/README.md`, `harkpro/README.md`, `harkpro/qc/__init__.py`, `qc_prompts/README.md`, `learnings.md`:
  `lines.json` described as wording/order/hours data, never a source of line existence.
- `lines.json` itself is unchanged. It still carries `required` as data, and `doctrine/check_doctrine.py` still
  validates it as a bool.
- HarkPro tests: `54 passed in 9.37s`. `check_doctrine.py`: OK.

Not changed, for your call: R11 (VAV lines) still lists the VAV lines as "every VAV gets ...". Under evidence only,
those should print only when the documents show the device.

## Questions for the estimator
- None new. (Question for the lead: do you accept the 12-test baseline above?)
