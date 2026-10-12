# T-009 report (Hark, 2026-10-12): task 1 (ruling 21) and task 2 (ruling 22) done

## 1. Task, branch, commits, base
- Task: T-009. Branch: `hark/T-009`. Base: `origin/rebuild` 52fd0ce at the start. T-008 was not in `rebuild` or `lead/wave2` then
  (`git branch -r --contains 7f033ce` listed only `hark/T-008` and `lead/t008-fixes`). T-008 was merged while I worked,
  so before the push I merged `origin/rebuild` e28ff96 into the branch (merge commit 8f9690f; no conflicts, no
  force-push). All test results below are on the merged tip.
- Commits, oldest first:
  - a9da17f T-009 task 2: the proposal prints one demolition exclusion (ruling 22)
  - 94be537 T-009: design note, question and report (task 1 waits) (docs only)
  - 89bd15b T-009 task 2 review fix: search only the exclusions section for the demolition lines
  - c496e11 T-009 task 1: thermostats and space sensors drawn on plans print the plan count (ruling 21)
  - d7826e2 T-009 task 1 self-review fixes: no false "*Verify" line, flag quantity, source-based "one per", wider
    kind detector
  - 8f9690f Merge origin/rebuild (e28ff96, T-008 and G-004) into hark/T-009
  - 8e13926 T-009: report (tasks 1 and 2, self-review, test tails) (pushed by the watcher run)
  - the report commit that adds the separate `tests/bms` run and the deviation note (the branch tip).

## 2. What I changed

### Task 1 design (ruling 21)
A new step, `takeoff.apply_plan_counts(job, devices, sheet_pages, ledger, typed=())`, runs once in `run.py` after the
writers and before the decisions. For each block it takes the areas of the sheets its counted units are drawn on (as
`_device_lines` does) and adds up the rows of the labels in `devices.json` `plan_count_labels` ("T", "TB") on the
new-work sheets of those areas only (a demolition sheet such as MD-201 never counts: 30, not 39). It keeps one `Ref`
per counted sheet, with the dossier's source id of that sheet's text. A thermostat or space-sensor line (see Kinds)
whose highest number is above that plan count gets `quantity = Count(value=plan, sources=<the sheet Refs>,
others=(), added_up=None)` and `flag = "quantity"` (always). So `Count.highest()` is the plan count, and `_printed`,
the "Qty (N)" prefix, `validate._count_problems` and `ai._count_from` need no change. Every number the line held, with
each source that gave it, becomes a `SetAside(family=<device id>, value=<n>, ref=<its Ref>, reason="plan count
prints", note="<n> not printed (<where>); the plan count <plan> of <thermostats> prints")` (lead answer, option A).
The ruling L1 sum (`added_up`) is kept the same way with the note form "<n> added up over the sheets, not a count
(ruling L1; <where>); ...". `render._verify_lines`, called from `_count_note`, builds the "*Verify" line from those
set-asides: the sheets of the line's quantity sources ("M-201 and M-202"), then every number above the plan count,
highest first, as "the sequence calls for one per <family> (<n>)" when the number's source is a family's (the source
id of the family's count, or a quote that says "per/each <family>"), else "<n> per <place>" (`_count_label`). It
prints only while the line still prints the plan count the set-aside records, never for the L1 sum, and splits at
"; " (or continues a long sheet list with "also drawn on ...") so no line passes 160 characters. The step is
idempotent, reads back from JSON, skips a line in `typed`, and drops its own set-asides for a line that no longer
prints their plan count (a typed count, a rewrite); when it reduces a line again it replaces them.

### Kinds, slots and labels
- Slots used (all in `playbook/shapes.json`, tested): `space_sensor`, `space_temperature`, `space_thermostat`,
  `thermostat`, `alternate_thermostat`, `mau_space_temperature`, `remote_space_sensor`, `bms_space_sensor`.
- Slots left out: `space_temperature_humidity` (a humidity sensor too, label T/H) and `extend_thermostat_wiring`
  (wiring).
- Names: a line matches by slot or by name: "thermostat(s)", or "space/room/zone/wall" + optional "temp/temperature"
  + "sensor(s)/transmitter(s)/thermostat(s)", or "space/room/zone/wall temp(erature)".
- Words that always make another kind of line: humidity, pressure, CO/CO2, discharge, mixed, outside, duct, wiring,
  wire, extend, relocat(ed), damper, valve, interlock.
- Words that make another kind only when the name does not say space/room/zone/wall temperature sensor: occupancy,
  return, supply, status, enable. So "Room Temperature Sensor with Occupancy Override" and "Space Temperature Sensor
  (return air plenum)" match; "Return Air Temperature Sensor", "Supply Air Temperature Sensor" and "Occupancy Sensor"
  do not.
- Labels used: "T" (Thermostat / temperature sensor) and "TB" (Thermostat (by others?)), in the new key
  `plan_count_labels` of `assets/reading_lists/devices.json`, read by `takeoff.plan_count_labels()`.
- Labels left out (the highest count prints for them): "TS" (Temperature sensor), "T/H" (Temperature / humidity
  sensor), "CO2", and every other label of the file (OCC, H, HS, RH, SP, DP, FM, FS, DWM, H2, LD, WS, SD, CO, NO2, PS,
  CS, DPS, FZ): none of them means thermostat.

### Files (task 1)
- `src/bms/takeoff.py`: new functions only (`plan_count_labels`, `is_plan_counted_kind`, `_counted_rows`,
  `_block_plan_count`, `_count_numbers`, `_plan_in_note`, `apply_plan_counts`) and their constants. `device_tally`,
  `_device_lines` and `register_text` are unchanged.
- `src/bms/render.py`: `_count_note` gains one line (it adds `_verify_lines`); new `_names_joined`, `_wrap_verify`,
  `_source_family`, `_verify_lines`. None of short_points, _reason, _notes, _header_families, render, _Printed,
  _device_lines, _header_text, the no-device code or _system_blocks is touched.
- `assets/reading_lists/devices.json`: one key, `"plan_count_labels": ["T", "TB"]`.
- `src/bms/prompts/write_system.md`, `qc_job.md`, `revise_system.md`: the count sentences only (below).
- `playbook/rules.md`: one rule (below).
- `src/bms/run.py`, `src/bms/model.py`, `tests/bms/test_contracts.py`, the interface spec: the hunks below.
- `HarkPro/outbox/T-009-design.md`: the design note (22 lines).

### Files (task 2, ruling 22)
- `src/estimator/proposal/layout.py`: the two template texts (`DEMOLITION_GENERAL`, `DEMOLITION_SPECIFIC`) next to
  `EXCLUSIONS`, and the block key and heading strings (written again: `estimator` does not import `bms`).
- `src/estimator/proposal/write.py`: `_keep_one_demolition_exclusion`, called in `write_proposal`. It finds each line
  by `squash`ed text, only between the "Exceptions and Exclusions" paragraph and "Base Price:" (89bd15b). With a
  Demolition Scope block it removes the general line, otherwise the specific one; a template with one line (or none)
  prints what it has.
- `src/estimator/proposal/read.py`: `read_named_exceptions` accepts a proposal with both demolition lines or lacking
  one of them; any other missing, edited or reordered standard line is still refused.

### Playbook text added (`playbook/rules.md`, end of "Counts and quantities", after "Quantities print in the line")
```
### Thermostats drawn on plans print the plan count
The plans draw thermostats, space sensors and wall sensors. When the plans draw them, the count on the plans prints as
the quantity, even when the sequence calls for more (for example one per unit). The line has no bracket. A short "*"
line says "Verify", names the sheets where the plans draw them, and names the other number with where it is. The
estimator checks the count, because the plans can miss a few. This is the one exception to Higher count prints and to
Never undershoot, and it covers only these devices. Every other device keeps both rules.
```
The words are the brief's, wrapped at 120 columns. "Higher count prints" and "Never undershoot" are unchanged.

Proposed sentences (not made):
- Higher count prints, at the end: "The one exception is Thermostats drawn on plans print the plan count: a thermostat
  or space sensor that the plans draw prints the plan count, and a "*Verify" line names the higher number."
- Never undershoot, in its list of exceptions: "...on two part plans, which a short "*" line names with both numbers,
  and a thermostat or space sensor that the plans draw, which prints the plan count with a "*Verify" line (Thermostats
  drawn on plans print the plan count)." (Today it says "The only exceptions ... are" the demolition and duplicate
  cases, and the new rule says "the one exception"; this sentence makes the two agree.)

### Prompt sentences (the count sentences only)
- `write_system.md` "Counts", one new bullet: "Thermostats drawn on plans print the plan count: for a thermostat or a
  space, room, zone or wall temperature sensor line, write the count the sequence gives (for example one per unit) as
  the line's count, as for any line. The app moves it: when the plans draw fewer, the plan count prints, with a
  "*Verify" line, and the sequence's number is kept apart with its source. Write no bracket and no note for it. Every
  other device keeps the highest count."
- `qc_job.md` line 7: "the value is the highest any cited source gives" gains "(except a thermostat or space sensor
  line that the plans draw: Thermostats drawn on plans print the plan count, so its value is the plan count and the
  sequence's number is not asked for again)".
- `revise_system.md` line 11: "the higher count prints" gains "(except a thermostat or space sensor line that the plans
  draw: Thermostats drawn on plans print the plan count, so keep its count as given and never raise it to the
  sequence's number)".

### Every hunk in lead-owned files
- `src/bms/run.py` (one hunk, after the front-end question, before `save(job)` at about line 609):
  ```
  +    # T-009 (ruling 21): a thermostat or space sensor line prints the plan count, the sequence's number set aside
  +    job = takeoff.apply_plan_counts(job, getattr(reading, "devices", ()) or (),
  +                                    getattr(dossier, "sheet_pages", None) or {}, ledger)
  ```
- `src/bms/model.py` (two hunks, lead answer option A):
  - `SetAsideReason`: `"plan count prints"` added at the end of the Literal.
  - `SetAside.reason` doc string: "... not a unit of this family, count by unit register (a pump or valve count the
    unit register changes) or plan count prints (a thermostat or space sensor line prints the plan count; the
    sequence's number is set aside, T-009)."
- `tests/bms/test_contracts.py` (one hunk): the `SET_ASIDE_REASONS` pin ends with `"plan count prints"`.
- `docs/superpowers/specs/2026-10-04-rebuild-interfaces.md` (one hunk, line 64): the `SetAsideReason` row ends with
  `"plan count prints"`.

### Pins changed, with the reason
- `tests/bms/test_contracts.py::test_enumerations_are_the_design_values`: `SET_ASIDE_REASONS` gains "plan count prints"
  at the end (lead answer, option A).
- `tests/bms/test_takeoff.py::test_t007b_a_pump_family_the_register_changes_has_the_new_reason` (about line 855): the
  T-007b reason is now at [-2] and "plan count prints" at [-1] (lead answer). Both are pinned.
- `tests/test_round_trip.py::test_26_0246_written_out_again_matches_what_was_sent` and
  `tests/test_end_to_end.py::test_the_proposal_matches_what_was_sent`: the sent proposal has both demolition lines; ours
  prints the general one only (no Demolition Scope block). Expected: the sent closing text minus the specific line.
  Every other line is still asserted in order (ruling 22).
- `tests/test_write_scope.py::test_named_exceptions_follow_the_standard_list` and
  `tests/test_write_cover.py::test_the_rest_of_the_template_is_untouched`: the same, the template's closing text minus
  the specific line (ruling 22).
- `tests/bms/test_t009_plan_count.py::test_no_source_of_the_other_numbers_is_lost` (own new test, changed in
  d7826e2): the "*Verify" line no longer names the L1 sum ("70 per M-601", never a count of the job) and names the
  second 55 by its place ("55 per M-601", its source is not the sequence's one per unit).
- The pin reasons are in the body of d7826e2 and here. The earlier commit bodies (a9da17f, c496e11) carry only the
  trailer; I did not rewrite pushed history (no force push).

### What the Evidence Package and the review page show for a plan-count line
- Evidence Package, "Scope" tab: the line as printed, `Qty (30) Furnish and Install Space Temperature Sensor`, with
  its quantity sources (one per counted sheet, M-201 and M-202).
- Evidence Package, "Set aside" tab (`evidence.set_aside_rows`): one row per other number and source, for example
  family `FCU.d2` (the device id, not a family tag), value 55, reason "plan count prints", note "55 not printed
  (M-701, Mech.pdf page 10); the plan count 30 of thermostats prints", and the sequence's citation. The demolition-sheet
  row for the 9 on MD-201 stays beside it. A row for an L1 sum says "not a count (ruling L1 ...)".
- Review page: the line at 30 with flag `quantity` (so the estimator is asked) and its sheet refs, which quote the
  label "T". `review.py` has no set-aside view, so the 55 shows there only through the printed "*Verify" note.
  `evidence.py` and `review.py` are unchanged.

## 3. Tests added
- `tests/bms/test_t009_plan_count.py` (60 tests with parameters): the brief's 12 cases (line and "*Verify" line and
  flag; 30 not 39, MD-201 not named; register number; no plan count x3; plan count not below; other kinds; detector
  3/3 plus more; validator; idempotent and JSON; typed count; 12 sheets as two lines; Playbook rule; prompts; one
  run.py call), the set-aside (reason, value, source, note), no source lost, and from the self-review: typed 33,
  typed 60 and a line rewritten at 60 print no "*Verify" line (the typed-33 test renders the job); the step clears its
  own set-aside for a typed line and replaces it when it reduces a rewritten line; flag `quantity` over "ownership";
  an equal number from another source is named by its place; the "also drawn on" path with 25 sheets; detector cases
  "Room Temperature Sensor with Occupancy Override", "Space Temperature Sensor (return air plenum)" (match) and "Return
  Air Temperature Sensor", "Supply Air Temperature Sensor", "Occupancy Sensor" (no match).
- `tests/bms/test_t009_demolition.py`: the brief's 5 cases (specific line with a block; general line without; every
  other standard line in order and a named exception last; a template with one line; read-back) and the review fix's
  two cases (a scope line with the text of the dropped exclusion stays, with and without the block).
- Each self-review fix test failed before its fix (10 failed, 41 passed at c496e11 with the new tests). The "also
  drawn on" test covers code that was already right and passed at once.

## Test output (real tails, sandbox has 2 CPUs so `-n 2`)
- Focused files, on the merged tip: `pytest tests/bms/test_t009_plan_count.py tests/bms/test_t009_demolition.py
  tests/bms/test_takeoff.py tests/bms/test_contracts.py tests/bms/test_rule_names.py tests/bms/test_t008_render.py
  tests/bms/test_render.py -q -n 2` -> `351 passed in 23.44s`.
- `python -m bms playbook-lint` (PYTHONPATH=src) -> `The Playbook at .../playbook is clean.`
- Full suite `pytest tests -q -p no:cacheprovider -n 2 -m "not slow"` on the merged tip:
  `9 failed, 5446 passed, 10 skipped, 4 xfailed, 208 warnings in 768.06s (0:12:48)`.
  The 9 failures, all named:
  - 5 chat tests in `tests/bms/test_ai.py`: `test_chat_writes_a_request_then_reads_the_answer_and_caches_it`,
    `test_chat_refuses_an_answer_that_breaks_the_schema`,
    `test_a_cached_answer_clears_a_request_left_behind_by_a_killed_run`, `test_every_cleanup_is_logged_beside_the_cache`,
    `test_write_system_through_the_chat_rejects_and_asks_again`
  - `tests/bms/test_review_final3.py::test_a_real_child_failing_with_the_resource_code_is_run_three_times_then_reported`
  - `tests/test_assets.py::test_running_on_the_project_python`
  - `tests/test_main.py::test_the_output_folder_being_a_file_that_is_open_is_plain`
  - `tests/test_revert_audit_review.py::test_a_new_test_inside_a_class_is_audited` (load-flaky: alone, the same file gives
    7 passed and 1 different utf8-bom failure; both pass on a quiet machine)
  These 8 environment tests also fail on an unchanged `origin/rebuild` e28ff96 (clean worktree, run: `8 failed, 238
  passed` over the same files; the revert-audit tests passed there under low load). `tests/bms/test_status_review.py`
  normal-exit (known flaky) passed this time.
- `pytest tests/bms -q -n 2 -p no:cacheprovider -m "not slow"`, run on its own on the merged tip by the fixer agent:
  `6 failed, 3108 passed, 2 skipped, 4 xfailed, 186 warnings in 722.37s (0:12:02)`. The 6, all known baseline:
  4 chat tests in `tests/bms/test_ai.py` (`test_chat_writes_a_request_then_reads_the_answer_and_caches_it`,
  `test_chat_refuses_an_answer_that_breaks_the_schema`, `test_a_cached_answer_clears_a_request_left_behind_by_a_killed_run`,
  `test_write_system_through_the_chat_rejects_and_asks_again`; the fifth passed this time),
  `tests/bms/test_review_final3.py::test_a_real_child_failing_with_the_resource_code_is_run_three_times_then_reported`
  and the known-flaky `tests/bms/test_status_review.py::test_every_normal_exit_writes_the_state_whole_and_status_agrees`
  (another project's test run shared the 2 CPUs). The junit file of the full run above agrees: 5469 tests, 9 failures,
  the 9 named.
- T-009 and pinned files again on the tip: `pytest tests/bms/test_t009_plan_count.py tests/bms/test_t009_demolition.py
  tests/bms/test_takeoff_evidence.py tests/test_end_to_end.py tests/test_round_trip.py tests/test_write_scope.py
  tests/test_write_cover.py -q -n 2` -> `116 passed in 30.36s`; `python -m bms playbook-lint` -> clean.
- Before the merge of `rebuild`, the same full suite at d7826e2's parent ran `10 failed, 5358 passed` (the 9 plus the
  known-flaky revert-audit tools-change test); no failure was caused by this branch.

## 4. What I did not do, and why
- Ruling 21 is not re-applied after the family-count rewrite (`run.py` step 4, `ai.rewrite_for_count`) or the
  revise (`_revised`). T-009 allows one `run.py` call, and it runs before them. If either writes the line again with
  the sequence's number, the 55 prints with the highest-prints rule; only the prompt sentences guard against it. Since
  d7826e2 the old set-aside then prints no false "*Verify" line (the render checks the plan count it records), but the
  plan count is lost for that line. See question 1.
- `-n 4`: the sandbox has 2 CPUs; I ran `-n 2`.
- Pin reasons are not in the bodies of the already-pushed commits a9da17f and c496e11 (no history rewrite); they are
  in d7826e2 and in this report.

## 5. Questions for the estimator / lead
1. May `run.py` call `takeoff.apply_plan_counts` a second time, after the family-count rewrite and the revise (or
   once, moved after them)? T-009 allows one call, so I did not add it. Without it, a rewrite or revise that brings
   the sequence's number back prints that number.
2. The plan-count refs quote the bare label "T" (with the sheet in `where`). A QC pass that checks "the passage really
   calls for the line" may flag it, which sends the block to revise and risks question 1's case. Do you want a fuller
   quote (for example "T, 14 drawn on M-201")?
3. "also drawn on <sheets>" continues a sheet list too long for one "*Verify" line (about 20 sheets or more). It is
   not in the estimator's form. Keep it, or another wording?
4. The two exception sentences above for "Higher count prints" and "Never undershoot": may I add them?

## Self-review
An independent reviewer agent (separate context; it did not write the code) ran the README checklist on c496e11 in a
detached worktree and wrote its findings. It found 3 must-fix and 9 should-fix items. A separate fixer agent made the
fixes in d7826e2 and this report.

Must fix:
1. False "*Verify" line after a typed count, a count rewrite or a revise. Fixed: `_verify_lines` prints only when the
   plan count in the set-aside note equals the printed count, and only for numbers above it; `apply_plan_counts`
   drops its own out-of-date set-asides and replaces them when it reduces a line again (idempotent). Tests: typed 33,
   typed 60, rewritten 60, the two step tests.
2. Ruling 21 is not re-applied after the rewrite and the revise. Left: T-009 allows one `run.py` call. Stated in
   "What I did not do" and question 1.
3. The report covered only task 2. Fixed: this report.

Should fix:
1. Flag `quantity` only when the flag was "none". Fixed: always `quantity`; test with "ownership".
2. The L1 sum named in the "*Verify" line. Fixed: kept as a set-aside (note "not a count (ruling L1 ...)"), left out of
   the line; the test's expected line changed (reason above).
3. "One per <family>" chosen by an equal number. Fixed: chosen by the number's source (family count source id, or a
   quote "per/each <family>"); test with 55 from the schedule on M-601.
4. The "also drawn on" path untested. Fixed: 25-sheet test; the wording is question 3.
5. `_OTHER_KIND` excluded "occupancy", "return", "supply", "status", "enable" anywhere. Fixed: these exclude only when
   the name does not say space/room/zone/wall temperature sensor; tests both ways, the brief's 3 no-match names stay
   out.
6. Pin reasons missing from commit bodies. Fixed in d7826e2's body and in this report; the pushed commits are not
   rewritten.
7. `T-009-design.md` was 34 lines. Fixed: 22 lines.
8. The typed-count test did not render. Fixed: it renders and asserts no "*Verify" line.
9. Two new code lines over 120 columns (`takeoff.py` `_KIND_NAME`, `render.py` comment). Fixed: wrapped; one more new
   line (`ADDED_UP_FORM`) wrapped too.
The reviewer also noted the bare "T" quote risk (question 2).

Checklist result on the tip: 1 invented fixtures only (Invented Hall, sample_job.json, M-2nn/M-3nn/M-601/M-701); 2
pins above, each with its reason; 3 rule "Thermostats drawn on plans print the plan count" checked against
`rules.md`; 4 every reduced number is a set-aside with both numbers; 5 detector tests 3+ each way; 6 only the task's
files and the lead-approved hunks above; 7 this report with tails; 8 one task per commit, subjects name the task; 9
"*Verify" lines at most 160 characters, flag `quantity`; 10 `playbook-lint` clean (above).

## Deviation
The T-009 rules allow one agent besides the worker: the self-review agent. The estimator (Siddhant) told Hark to finish
T-009 now with multiple agents. So the reviewer and the fixer are separate agents: the reviewer (its own context, did
not write the code) reviewed c496e11 in wt/T-009-review; the fixer made d7826e2 in wt/T-009-fix. The scheduled watcher
run, which had started the task in wt/T-009, merged d7826e2 and `origin/rebuild`, ran the full suite and pushed
8e13926; the fixer then ran `tests/bms` on its own (above) and pushed the tip. None of the agents started further
subagents.
