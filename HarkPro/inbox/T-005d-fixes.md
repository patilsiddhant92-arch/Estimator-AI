# T-005d: fixes before merge (lead, 2026-10-11)

- Verdict: not merged yet. Fix the three items "Must fix 1" to "Must fix 3" below on hark/T-005d. Make the six review
  tests pass ("Must fix 4"). Push again. The full review is in `HarkPro/inbox/T-005d-review.md`.
- Base: origin/lead/wave2. It carries T-005c. Bring your branch up to date with it. In `src/bms/model.py`, take
  T-005c's side for `mark` and `mark_note` (both are optional fields there).
- Must fix 1 (root cause): job-wide facts that name no unit tag still reach no writer. Two examples are an
  outside-air temperature sensor and a changeover aquastat in a GENERAL sequence section. The sequence selection
  (`src/bms/ai_evidence.py` about line 278) and the facts checklist (about line 536) use the same tag-and-name test.
  Give every writer the job-wide facts and the sequence sections that name no tag. Put them under the heading
  "Job-wide facts". Then the system that owns the point can print it once, and the other systems can see that it
  exists.
- Must fix 2: a controls sheet goes first and whole. But `block` skips any entry over the 12,000-character notes limit
  (`src/bms/ai_evidence.py` about lines 241 and 447), and the branch raises the sheet cut to 24,000. So a controls
  sheet of 12,000 to 24,000 characters never reaches the writer. Never drop a sheet silently. Split it across blocks,
  or raise the per-entry limit together with the total. If the total cannot hold the sheet, stop with a clear
  message.
- Must fix 3: the `_STATED` pattern (`src/bms/ai.py` about line 1285) ignores negation. "The schedule does not state
  the quantity" must keep its "assumed" flag. Add a negation check, with a test.
- Must fix 4: add `HarkPro/inbox/T-005d-review-tests.py` to tests/bms/ as `test_t005d_review.py`. All 6 tests must
  pass. Each test covers one item:
  - `test_a_global_outside_air_sensor_in_the_sequence_reaches_the_ahu_evidence` and
    `test_a_changeover_aquastat_in_the_general_sequence_reaches_the_ahu_evidence`: Must fix 1.
  - `test_a_long_control_diagram_sheet_reaches_the_writer`: Must fix 2.
  - `test_an_assumption_that_says_the_schedule_does_not_state_the_value_is_kept`: Must fix 3.
  - `test_a_future_word_about_something_else_does_not_mark_the_line`: Should fix 1. Do this item too.
  - `test_an_assumption_against_a_stated_schedule_fact_is_not_kept`: Should fix 2. Do this item too.
- Should fix 1: FUTURE in upper case anywhere in a quote marks the line "future" (`src/bms/ai.py` about line 1316
  and `src/bms/ai_evidence.py` about line 45). Match the item, not any word.
- Should fix 2: the 26-0544 "Assumed" wording still passes the intake check (`src/bms/ai.py` about line 1350). An
  assumption against a schedule row that states the fact must not stay, even when its reason names the specification.
- Should fix 3: the end-device checklist calls every schedule row that names a device "furnished with the unit"
  (`src/bms/ai_evidence.py` about lines 495 to 517). Say "names an end device". Leave the owner to the passage.
- Should fix 4: a long flag text makes the run stop after max attempts (`src/bms/ai.py` about lines 1358 to 1375). Do
  not stop the run for it. Shorten the text to points instead.
- Should fix 5: the real sheet number M-710.00 is in a prompt and in code (`src/bms/prompts/write_system.md` about
  line 79, `src/bms/ai.py` about line 1291). Use an invented sheet. Never put job-specific text in prompts or code,
  ever.
- Should fix 6: at 24,000 characters per sheet, fewer sheets fit in the unchanged 400,000 total
  (`src/estimator/writing/dossier.py` about lines 59 to 61 and line 1321). On a large job, later sheets lose all
  text. Check the sheet order, or raise the total.
- Report: update `HarkPro/outbox/T-005d-report.md` with the real test output (the six review tests, touched files,
  tests/bms, full suite).
