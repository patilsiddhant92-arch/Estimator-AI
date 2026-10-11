# T-005d report: writer and evidence (rulings 6, 7, 10; addendum)

1. Task T-005d, branch `hark/T-005d`, first base `origin/lead/wave2` (0e78113); fixes round merged with `origin/lead/wave2` (T-005c and the lead's fixes) in d03c918. Last commit: the branch tip (this report is in it). The fixes round is the last section, "Fixes after review".

## Root causes found (checked on the 26-0544 documents locally, no AI asked; job text left out of git)

- **The control diagram never reached the AHU writer.** Every plan sheet's text "named" the air handlers through the
  project title in its title block, so every sheet was picked as a note for AHU, in sheet order. The 12,000-character
  notes cap filled before the control-diagram sheet (the last sheet), so its FUTURE items, the outside air
  temperature sensor, the freezestat, the smoke detectors and the EF VFD points never reached the AHU, EF or ERV
  writer. (FCU picked plan sheets the same way.)
- **The 8,000-character cut is real.** The general notes sheet's text runs to about 15,000 characters and its BMS
  notes (integrate into the existing BMS via BACnet; the controls contractor furnishes the controllers) sit past
  character 14,000, so the dossier, every reading pass and every writer lost them. Two schedule sheets were cut too.
- **Sequence and point lists:** the 23 09 93 sequence reaches the writers as dossier part 2. No points list sheet was
  read; the points are on the control schematics (7c sheet text), so they reached a writer only through the notes
  block above.
- **ERV end devices:** the ERV schedule notes (shipped loose, sensors mounted in the supply and exhaust ducts, filter
  switch, end switch) did reach the ERV writer; nothing told it to read them into scope.
- **FCU "Assumed":** the FCU writer had the FCU sequence and the schedule; the prompt never forbade an assumption that
  a schedule or sequence states.

## 2. What changed

Files I own:
- `src/bms/ai_evidence.py`
  - :20-23 new limits (`EXCERPT_OVER` 1,500, `EXCERPT_REACH` 300, `EXCERPTS_MAX` 12, `FACTS_MAX` 60).
  - :39-63 patterns: `_CONTROLS_SHEET`, `_FUTURE`, `_LOOSE`, `_NOTICE`, `_END_DEVICE` (a disconnect switch is not an
    end device), `_FRONT_END_TEXT` (notes), `_FRONT_END_SCOPE` (sequence, spec, job part: graphics, training,
    workstation, network controller, integrator / prequalified / eligible, existing BMS).
  - :218 `evidence(..., ledger=None, front_end=False)`.
  - :280, :319, :328 the front end also takes sequence, spec and job passages in its scope words (training, the
    approved-integrator passage).
  - :313 and :351-455 `_notes`: cited notes first, then a controls sheet's text (title names controls, sequence,
    points, diagram, schematic, BMS) whole, then other notes, then long plan-sheet text as excerpts around the
    system's tags (plus FUTURE / shipped-loose words) with " … " between them. For a tagged system a plan sheet's text
    is picked only by a tag, never by the name phrase (the title block). A note repeated word for word is given once.
  - :334-341 and :457-555 the checklists appended to every evidence: "Items its passages mark FUTURE",
    "Devices its passages say are integral or furnished with the unit", "End devices its unit schedules list"
    (shipped loose / mounted in a duct or field vs listed with the unit, the latter to be marked "notice"), and with a
    ledger "Controls facts the reading found about it" (the coverage gate's `SCOPE_KINDS` facts naming the system;
    the front end gets the `front_end` facts) as "[S..] “quote” — where (read as: kind subject = value)".
  - :782-797 `STATED_TITLES`, `stated_ids()` (sequence, points list and schedule ids of an evidence).
- `src/bms/ai.py`
  - :81 `LATE_DEVICE_FIELDS`; :549-566 `_late_device_fields` (a cached answer without mark/mark_note is still used;
    "Future" is lowercased), called at :578 (chat), :710 (API) and :1197 (intake).
  - :766-800 `evidence_for(system, dossier)` keeps the interface-spec signature and delegates to the new
    `system_evidence(system, dossier, ledger=None, *, front_end=False)`.
  - :1765 `front_end_evidence(front, dossier, taken=(), ledger=None)` (front_end=True).
  - :1180-1186 `_check_system` docstring; :1197-1206 intake order: late fields, schema, `_marks`,
    `_stated_not_assumed`, `_length_problems`, then `_normalise`; :1440 a mark_note that prints a source id is
    refused (same check as other client text).
  - :1276-1375 `MARKS`, `FUTURE_NOTE`, limits (mark_note 120, assumption 300, clarification 500 characters),
    `_future_source`, `_marks` (a line whose ref quotes "FUTURE"/"[FUTURE]" is marked "future"; a "future" line's
    note always starts "FUTURE AS PER", filled as "FUTURE AS PER sheet <sheet>" from the ref's place when the writer
    gave none; brackets stripped; an unmarked line keeps no note; a mark outside "", future, notice refused),
    `_stated_not_assumed` (ruling 6: an assumption that says a schedule / the sequence / a points list states it, on a
    line citing one of them, is dropped and an "assumed" flag cleared, logged in intake.json), `_length_problems`.
  - :1673 `_ask_system` passes `stated_ids(evidence)` to the intake.
- `src/bms/prompts/write_system.md` :70-97, new sections between `<!-- T-005d -->` markers: "Stated, never
  assumed", "FUTURE items and items to notice", "End devices on unit schedules", "Every controls fact ends
  somewhere" (lists the lines that were missed: outside air temperature, freezestat, smoke status, VFD points,
  changeover aquastat / pipe sensor, pump points), "Short flags".
- `src/bms/prompts/write_front_end.md` :32-41 (stated facts, marks, network panel / graphics / training each with its
  ref, the integrator eligibility point as a confirm clarification, facts checklist, short clarification).
- `src/bms/prompts/revise_system.md` :15-17 (keep marks; never answer a finding with an assumption a schedule states).
- `src/bms/prompts/qc_job.md` :17-20 (unmarked FUTURE line must_fix; furnished-with-unit line without "notice"
  check; stated assumption must_fix; unscoped shipped-loose end devices are missing lines).

Shared files I touched (please check on merge):
- `src/bms/model.py` :34-36, :52, :150-155, :459: Device `mark` / `mark_note`. I applied T-005c's uncommitted hunk
  from their worktree verbatim (`Mark = Literal["", "future", "notice"]`, `MARKS`, two fields with defaults, docs),
  so the two branches carry the same change. T-005c has since made the two fields optional in the AI schema
  (`optional=True` metadata and a `json_schema` change); take theirs on merge. I ran my tests and
  `test_front_end_write.py` against T-005c's newer `model.py`: they pass (`_late_device_fields` fills missing marks
  either way, and my schema test only asks that the properties exist).
- `tests/bms/fixtures/sample_job.json`: `"mark": "", "mark_note": ""` on every device. Byte-identical to T-005c's
  working copy at the time; needed so `test_contracts` passes with the new fields.
- `src/bms/run.py` :537-541: the writers get `ai.system_evidence(s, dossier, ledger)` and
  `ai.front_end_evidence(job.front_end, dossier, taken, ledger)` (two lines; T-005c's header change is elsewhere).
- `tests/test_dossier.py` :480-495 (`test_each_plan_sheets_own_text_is_given_in_7c_once_per_sheet_number`): the
  text and the bound now follow `PLAN_TEXT_LIMIT` instead of the fixed 8,000. T-005a's edits to this file are in other
  hunks (around :241 and :292).
- `src/estimator/writing/dossier.py` :59: `PLAN_TEXT_LIMIT` 8,000 -> 24,000 (the total cap 400,000 stays). T-005a's
  hunks in this file are elsewhere (imports and `_counts`). Note: this changes the dossier text, so every reading pass
  and writer is asked again on the next run (a new cache key); the counts are not affected.

## 3. Tests

Added `tests/bms/test_t005d_writer.py` (29 tests, invented "Invented Hall" fixture built inline). 27 of them fail on
the base and pass here (the two that passed on the base are the "kept" cases). The first code draft came before the
file; I then wrote the tests and checked them against the base. Names:
`test_the_control_diagram_sheet_reaches_the_writer_before_the_plan_sheets`,
`test_a_title_block_phrase_does_not_make_a_plan_sheet_name_a_tagged_system`,
`test_a_long_plan_sheet_text_is_given_as_excerpts_about_the_system`,
`test_every_plan_sheet_that_names_the_system_fits_the_notes_block`, `test_a_note_repeated_word_for_word_is_given_once`,
`test_the_future_items_are_listed_for_the_writer`, `test_the_end_devices_of_the_unit_schedule_are_listed`,
`test_the_stated_ids_are_the_sequence_and_schedule_passages`, `test_the_controls_facts_of_the_system_are_a_checklist`,
`test_the_front_end_gets_its_facts_its_bms_notes_training_and_the_integrator_passage`,
`test_the_run_writes_from_the_evidence_with_the_ledger`, `test_a_plan_sheet_text_is_not_cut_at_8000_characters`,
`test_a_line_quoting_a_future_passage_is_marked_future_with_its_source`, `test_a_mark_is_made_usable_on_intake` (4),
`test_an_unmarked_line_keeps_no_mark_note`, `test_a_notice_line_for_a_device_furnished_with_the_unit`,
`test_a_bad_mark_is_refused` (3), `test_an_answer_written_before_marks_existed_is_still_used`,
`test_the_writer_schema_asks_for_the_marks`, `test_an_assumption_a_cited_schedule_states_is_dropped`,
`test_an_assumption_on_a_line_citing_no_schedule_or_sequence_is_kept`, `test_a_long_assumption_is_refused`,
`test_a_long_clarification_is_refused`, `test_the_writer_prompts_carry_the_rulings`.

Full suite (`-n 2 -p no:cacheprovider`, run in 8 chunks of 25 files because four agents shared the CPUs):
4,834 passed, 10 skipped, 10 failed. All 10 failures are baseline: 4 `test_ai` chat tests (the 5th chat test passed
this time), `test_assets::test_running_on_the_project_python`,
`test_main::test_the_output_folder_being_a_file_that_is_open_is_plain`,
`test_review_final3::test_a_real_child_failing_with_the_resource_code_is_run_three_times_then_reported`,
`test_revert_audit::test_a_tools_change_is_reverted_too`, and
`test_revert_audit_review::test_a_test_file_saved_with_a_utf8_bom_is_audited` / `test_a_new_test_inside_a_class_is_audited`.
Two failures of mine came up in the first pass and are fixed: the playbook lint read my new double-quoted prompt
phrases as rule names (now in curly quotes), and `tests/test_dossier.py` checked the old 8,000 cut (now follows
`PLAN_TEXT_LIMIT`). I re-ran both chunks after the fixes and they pass.

Checked on the real 26-0544 documents (local only, nothing committed): with this branch the AHU, EF and ERV
evidence carries the control-diagram sheet whole with both FUTURE items listed in the FUTURE checklist; AHU notes no
longer list the title-block-only sheets; the ERV evidence lists the shipped-loose and duct-mounted schedule notes; the
front end evidence carries the general notes sheet's BMS notes, the training passage and the approved-integrator
passage.

## 4. What I did not do, and why

- No explicit "dismissal" field: the writer's answer is a `System`, which has no place for one. A fact that is not
  AME's work is left out and the coverage gate still reports it on the review page. See question 1.
- (Superseded by "Fixes after review", must fix 1: job-wide facts now reach every writer.)
- "Assumed when stated" is caught mechanically only when the assumption's own words say a schedule / sequence states
  it and the line cites one; the FCU case (the assumption cited the spec while the schedule and sequence said
  otherwise) is left to the prompt and the QC prompt rule. A mechanical check of meaning would guess.
- Notice marks are not set mechanically (the checklist names the candidates; the writer decides). FUTURE marks are
  set mechanically only from a ref quote containing FUTURE.
- The demolition sheets still reach the writer's notes when their text has the unit's tag (that is T-005a's
  ruling-1 work; the excerpts keep them small).
- Render of marks (red, brackets) is T-005c's.
- Did not edit `playbook/` or the interface spec.

## 5. Proposed Playbook changes (for the estimator)

1. Shipped-loose devices: add "A device the unit schedule says is mounted in a duct or in the field (for example
   'discharge air temperature sensor, wired in unit, mounted in supply duct') is a shipped-loose device."
2. New rule under Lines: "FUTURE items. An item the documents mark FUTURE prints as its own line with
   '(FUTURE AS PER <source>)' in red, as a flag; it is priced only when the estimator says so."
3. New rule: "Items to notice. A control device the unit schedule lists as furnished with the unit (drain pan level
   sensor, freezestat, filter switch) prints in red so the estimator checks who furnishes it."
4. Assumptions: add "Never assume what a schedule or the sequence states; cite it."
5. Clarifications: give the limits in characters as well as words (assumption about 25 words / 300 characters,
   clarification about 40 words / 500 characters), so the validator and the writer use the same number.

## 6. Questions

1. Should `System` (T-005c / lead) get a `dismissals` list (fact source id, quote, short reason), so the writer can
   close a coverage fact as "not AME's work" and the gate stops reporting it? Today it stays on the review page.
2. Are the intake limits right (assumption 300, clarification 500, mark_note 120 characters)? Since the fixes round a
   longer assumption or clarification is shortened to points, never refused (a mark_note over 120 is still refused).
3. `PLAN_TEXT_LIMIT` 24,000 re-asks every reading pass on the next run (the dossier text changes). OK, or should the
   larger limit apply to the writer's evidence only?

## Regression fixtures (NOTES 2026-10-11 rule 4)

- `tests/bms/fixtures/t005d_evidence.json`: an invented copy of the two 26-0544 evidence defects (same sheet-number
  form Mnnn.00, same title forms, same 7c sheet-text line form; an invented project title that names the system in
  every title block, invented sheets, notes and FUTURE item).
- `tests/bms/test_t005d_fixture_regressions.py` (7 tests) reads it. Six fail on the base 0e78113 (src exported from
  git) and pass here; the seventh only checks that the fixture's BMS note sits past character 8,000:
  - title-block phrase flooding the notes cap: `test_fixture_the_control_diagram_reaches_the_writer_before_the_plan_sheets`,
    `test_fixture_a_sheet_named_only_by_its_title_block_is_not_a_note_of_the_unit`,
    `test_fixture_every_tagged_plan_fits_the_notes_block_as_excerpts`, `test_fixture_the_future_item_is_listed_for_the_writer`;
  - BMS notes past the 8k cut: `test_fixture_the_general_notes_sheet_is_long_enough_to_be_cut_at_8000`,
    `test_fixture_the_bms_notes_past_8000_characters_stay_in_the_sheet_text`,
    `test_fixture_the_front_end_writer_gets_the_bms_notes`.
- The inline "Invented Hall" fixture in `test_t005d_writer.py`: its control-diagram line (S40) and the matching fact
  quote are now reworded with invented text (fixes round), and this report's root-cause section no longer quotes the
  job.

## Tests (NOTES 2026-10-11 rule 3)

Run on this commit, PYTHONPATH=src, `-p no:cacheprovider`:

- Files changed: `pytest tests/bms/test_t005d_fixture_regressions.py tests/bms/test_t005d_writer.py -q -n 2`
  -> `36 passed in 5.41s`
- `pytest tests/bms -q -n 2 -p no:cacheprovider` (one run, not chunked, while another agent's suite shared the CPUs):
  `7 failed, 2536 passed, 2 skipped, 178 warnings in 607.54s (0:10:07)`
  - **tests/bms pass count: 2536.**
  - All 7 failures are accepted baseline: the 5 `test_ai.py` chat tests, `test_review_final3` resource code,
    `test_status_review` normal-exit. No revert_audit test failed.

## Fixes after review (HarkPro/inbox/T-005d-fixes.md, 2026-10-11)

Merge: `origin/lead/wave2` merged into `hark/T-005d` (merge commit d03c918, no rebase, no force). `src/bms/model.py`:
T-005c's side for `mark` / `mark_note` (both `optional=True`). `tests/bms/fixtures/sample_job.json`: no conflict, the two
sides were identical, so it is wave2's. Then `HarkPro/inbox/T-005d-review-tests.py` copied to
`tests/bms/test_t005d_review.py`. Before any fix: **6 failed in 69.00s** (all six). After: **6 passed**.

| Item | Status | Where |
|---|---|---|
| Must fix 1: job-wide facts to every writer | done | `src/bms/ai_evidence.py:308-310` new block "Job-wide facts:" right after the system's sequence; `:521` `_job_wide_sections` (sections whose heading names no tag and is general, "A. GENERAL", "ALL SYSTEMS", "COMMON", "GLOBAL", "CHANGEOVER" ..., first; then any section none of whose paragraphs names a tag; capped at `JOB_WIDE_LIMIT` 8,000, `:22`); `:553` `_job_wide_facts` (reading facts whose subject, value and quote name no tag; heading "Job-wide facts the reading found ...", at most `JOB_WIDE_FACTS_MAX` 30, `:23`). The front end gets them too. `:930` "Job-wide facts:" is a stated title (a sequence passage states what it says). Prompt: `src/bms/prompts/write_system.md:93` (write one only when this system owns the point; otherwise the owner prints it once). |
| Must fix 2: never drop a long controls sheet silently | done | `src/bms/ai_evidence.py:342` controls sheets get their own block "Controls sheets that name it ..." before the notes, limit `CONTROLS_LIMIT` 60,000 (`:20`, room for two whole 24,000 sheets and excerpts of more); `:251-261` `block(..., whole=True)`; `:502` `_fit`: whole when it fits, else excerpts about the system, else the excerpts cut at a word with "(cut: the rest of the sheet is not given here)"; under `CONTROLS_MIN` 1,500 characters of room it raises `ValueError("Stopped: the controls sheet <title> ... CONTROLS_LIMIT ...")`, which the run reports as a plain "Stopped:" line. |
| Must fix 3: `_STATED` respects negation | done | `src/bms/ai.py:1292` `_NEGATION`; `:1305` `_says_stated` (a clause with a stated verb and no negation); `:1310` `_says_silent`; `:1365` `_stated_not_assumed` uses them. "the schedule does not state the quantity", "shows no count", "without a count", "doesn't state" keep the assumption. |
| Must fix 4: the six review tests | done | `tests/bms/test_t005d_review.py`, 6 passed (output below). |
| Should fix 1: FUTURE matches the item | done | `src/bms/ai_evidence.py:54-58` `_ITEM`, `FUTURE_REACH` 40; `:590` `future_items(text, name=None)`: a FUTURE counts only with an item word, or given a device name one of its words, within 40 characters; `:629` the FUTURE checklist uses it; `src/bms/ai.py:1343` the intake auto-marks "future" only when the quote's FUTURE is beside the device's own words. An explicit "future" mark from the writer is kept. Prompt `write_system.md:81`. |
| Should fix 2: assumption against a stated schedule row dropped even when it names the spec | done | `src/bms/ai.py:1296` `_STATES_OWNER` (FURNISHED/PROVIDED/... BY, BY OTHERS, BY THE UNIT MANUFACTURER, FACTORY WIRED ...), `:1301` `_ABOUT_OWNER`; `:1386` an assumption whose "what" is about who furnishes/installs/wires, on a line citing a stated passage whose quote states the owner, is dropped whatever its why says, unless its words say the source is silent. Logged in the intake log. Prompt `write_system.md:74` (follow the row; the conflict goes in the clarification). A quantity assumption is not dropped this way (only ownership: the 26-0544 shape). |
| Should fix 3: "names an end device" | done | `src/bms/ai_evidence.py:663`: "- names an end device (the passage says who furnishes it; when it says the unit or the factory furnishes it, a line for it is marked "notice")". |
| Should fix 4: long flag text shortened, never stops the run | done | `src/bms/ai.py:1401` `_points` (sentences/clauses/list items joined with "; " as many as fit; one long point cut at a word with " …"); `:1422` `_shorten_flags` (assumption what+why to 300, clarification to 500; logged); `:1206` called in the intake instead of the old refusal (`_length_problems` removed). Prompt `write_system.md:98` (put the most important point first). |
| Should fix 5: no real sheet number or job text in prompts and code | done | `write_system.md:79`, `src/bms/ai.py:1316`, `src/bms/model.py:157` (T-005c's AI schema doc), `src/bms/render.py:835` (T-005c's docstring) now say invented "M-9.01". `tests/bms/test_t005d_fixes.py::test_no_real_sheet_number_in_the_prompts_or_the_code` guards src/bms, its prompts and src/estimator. This report's root-cause section and the Invented Hall S40 line in `tests/bms/test_t005d_writer.py` no longer carry job wording. |
| Should fix 6: later sheets keep text under the 400,000 total | done | `src/estimator/writing/dossier.py:62-64` `PLAN_TEXT_FLOOR` 8,000, `_CONTROLS_TITLE`; `:1341` `_is_controls_sheet`; `:1347` `_sheet_cuts`: within the total every sheet keeps 24,000; past it the controls sheets keep 24,000 and the other sheets share the rest at one even cut (as high as fits, never under 8,000, after which the old "Stopped at" applies); `:1321` used by `_sheet_text_lines`. Sheet order, and so every source id, is unchanged. Total not raised: 7c lines also go to the reading passes, so a larger total costs every pass. |

Review notes, also handled: 12 (caps) `MARKS_MAX` 20 on the FUTURE and notice lists, `QUOTE_MAX` 300 on a fact's quote
(`ai_evidence.py:24-25`). Not changed: note 10 (`run.py:537-541`, lead's to accept), note 11 (the "Lines often missed"
list stays: generic BMS points, still evidence-only; `test_the_writer_prompts_carry_the_rulings` asserts it), note 13
(spec fields after merge: the interface spec is lead-owned).

Tests added: `tests/bms/test_t005d_fixes.py` (19 test functions, 22 cases) from the invented fixture
`tests/bms/fixtures/t005d_fixes.json` ("Invented Annex", units QX-3 / WV-8, sheets M-602 / M-902 / M-111):
`test_the_general_sequence_section_is_given_under_job_wide_facts`,
`test_a_job_wide_fact_of_the_reading_is_listed_and_a_tagged_one_is_not`,
`test_every_writer_gets_the_job_wide_facts_the_front_end_too`,
`test_a_section_already_given_as_the_systems_own_is_not_repeated`,
`test_a_controls_sheet_longer_than_the_notes_limit_is_given_whole`,
`test_a_controls_sheet_past_the_controls_limit_is_given_as_excerpts`,
`test_a_controls_sheet_with_no_room_left_stops_the_run_with_a_plain_message`,
`test_an_assumption_that_says_the_schedule_is_silent_is_kept` (4), `test_the_stated_test_reads_negation_per_clause`,
`test_a_future_item_beside_the_device_words_marks_the_line`,
`test_a_future_word_about_something_else_is_not_in_the_future_checklist`,
`test_future_items_needs_an_item_word_or_the_device_name`,
`test_an_ownership_assumption_against_the_schedule_row_is_dropped_whatever_its_reason`,
`test_an_ownership_assumption_on_a_stated_passage_that_names_no_owner_is_kept`,
`test_the_end_device_checklist_says_names_an_end_device`, `test_no_real_sheet_number_in_the_prompts_or_the_code`,
`test_the_plan_sheets_share_the_total_and_the_controls_sheets_keep_the_full_cut`,
`test_a_job_within_the_total_keeps_the_full_cut_on_every_sheet`, `test_every_sheet_of_a_large_job_reaches_7c`.
Changed: `test_t005d_writer.py` (controls sheet in its own block; "names an end device"; the two "long flag is
refused" tests are now "shortened to points, never refused", plus `test_one_long_point_is_cut_at_a_word`) and
`test_t005d_fixture_regressions.py::test_fixture_the_control_diagram_reaches_the_writer_before_the_plan_sheets`
(controls block before the notes).

### Test output (fixes round, PYTHONPATH=src, `-p no:cacheprovider`)

- Review tests before any fix: `6 failed in 69.00s (0:01:08)`.
- Review tests after: `pytest tests/bms/test_t005d_review.py -v` -> all six PASSED, `6 passed in 3.00s`.
- Touched files: `pytest tests/bms/test_t005d_review.py tests/bms/test_t005d_fixes.py tests/bms/test_t005d_writer.py
  tests/bms/test_t005d_fixture_regressions.py tests/test_dossier.py tests/test_dossier_7c_printed.py
  tests/bms/test_contracts.py tests/bms/test_render.py tests/bms/test_t005c_proposal.py tests/bms/test_playbook_lint.py -q`
  -> `334 passed in 21.48s`.
- `pytest tests/bms -q -n 2 -p no:cacheprovider` (one run, two sibling agents on the CPUs):
  `8 failed, 2623 passed, 2 skipped, 180 warnings in 692.71s (0:11:32)`. **tests/bms pass count: 2623.**
  Seven are accepted baseline: the 5 `test_ai.py` chat tests, `test_review_final3` resource code,
  `test_status_review` normal-exit. The eighth, `test_review_t005c.py::test_a_takeoff_subfolder_named_takeoff_does_not_become_the_job_folder`,
  fails on a clean `origin/lead/wave2` too (question 1). An earlier run of this round also showed 6 playbook-lint
  failures: the lint read a new straight-quoted prompt phrase as a rule name; fixed with curly quotes
  (`write_system.md:81`), then the lint files passed (`124 passed`, with the wave2 test above the only failure) and
  this run has none.
- Rest: `pytest tests -q -n 2 -p no:cacheprovider --ignore=tests/bms` -> `2 failed, 2312 passed, 8 skipped, 22 warnings
  in 239.54s (0:03:59)`. Both accepted baseline: `test_assets::test_running_on_the_project_python`,
  `test_main::test_the_output_folder_being_a_file_that_is_open_is_plain`. No revert_audit test failed.

### Questions (fixes round)

1. `tests/bms/test_review_t005c.py::test_a_takeoff_subfolder_named_takeoff_does_not_become_the_job_folder` fails here
   (`'2. Takeoffs' == '26-7102'`) and also on a clean `origin/lead/wave2` checkout in this sandbox (checked in a
   throwaway worktree), so it comes with the merge, not from T-005d. Lead's to look at (Linux path handling?).
2. A controls sheet that cannot be given in 1,500 characters stops the run ("Stopped: ... CONTROLS_LIMIT"), as the
   fixes file asks. With 60,000 characters (two whole sheets plus excerpts of the rest, each about 8,000 at most) this
   needs eight or more controls sheets naming one system. Keep the stop, or prefer cut excerpts with a review flag?
3. Job-wide sections: a section counts as job-wide when its heading names no tag and is general (GENERAL, ALL
   SYSTEMS, COMMON, GLOBAL, SYSTEM-WIDE, BUILDING-WIDE, CHANGEOVER, OUTSIDE AIR), or when no paragraph in it names a
   tag. A tagless section about one kind of equipment ("D. EXHAUST FANS") therefore reaches every writer too, under
   the 8,000 cap. OK, or narrow it to the general headings only?
4. Earlier commits on this branch (1c0c65c..bed60db) carry the old report text with job sheet numbers and drawing
   words. This commit removes them from the tip; they stay in history unless the lead squashes on merge.
