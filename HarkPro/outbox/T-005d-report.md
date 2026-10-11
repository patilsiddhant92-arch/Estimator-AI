# T-005d report: writer and evidence (rulings 6, 7, 10; addendum)

1. Task T-005d, branch `hark/T-005d`, base `origin/lead/wave2` (0e78113). Last commit: the branch tip (this report is in it).

## Root causes found (checked on the 26-0544 documents, dossier built locally, no AI asked)

- **The control diagram never reached the AHU writer.** Every plan sheet's text "named" the air handlers through the
  project title in its title block ("REPLACEMENTS OF AIR HANDLING UNITS AND FAN COIL UNITS"), so all 20+ sheets were
  picked as notes for AHU, in sheet order. The 12,000-character notes cap filled before M710.00 (last sheet), and
  the AHU evidence said "(20 more passages name it; not given here)". So the FUTURE supply static pressure sensor and
  the FUTURE outdoor airflow station, the outdoor air temperature sensor, the freezestat, the smoke detectors and the
  EF VFD points on M710.00 were never in front of the AHU, EF or ERV writer. (FCU picked plan sheets the same way.)
- **The 8,000-character cut is real.** M001.00's text is 15,389 characters; its "BUILDING MANAGEMENT SYSTEM (BMS)
  NOTES: 1. INTEGRATE NEW HVAC EQUIPMENT INTO EXISTING SCHNEIDER ELECTRIC BMS VIA BACNET ... THE CONTROLS CONTRACTOR
  SHALL FURNISH AND INSTALL ALL NECESSARY CONTROLLERS ..." sits after character 14,000, so the dossier (and every
  reading pass and writer) lost it. M620.00 (12,068) and M610.00 (8,427) were also cut.
- **Sequence and point lists:** the 23 09 93 sequence (spec pages 422 to 429) does reach the writers as dossier
  part 2. No points list sheet was read (`points_pages` 0); the points are on the M710.00 control schematics, which
  are 7c sheet text, so they reached a writer only through the notes block above (now fixed).
- **ERV end devices:** the ERV schedule notes (S450 shipped loose, S455 discharge air sensor mounted in supply duct,
  S459 exhaust air sensors mounted in exhaust duct, filter switch, end switch) did reach the ERV writer; nothing told
  it to read them into scope. Now a checklist and a prompt section do.
- **FCU "Assumed":** the FCU writer had the FCU sequence (wall thermostat, pipe temperature changeover) and the
  schedule; the prompt never forbade an assumption that a schedule or sequence states.

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
    note always starts "FUTURE AS PER", filled as "FUTURE AS PER sheet M710.00" from the ref's place when the writer
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
evidence carries M710.00 whole with both [FUTURE] items listed in the FUTURE checklist; AHU notes no longer list the
demolition/title-block-only sheets beyond the ones whose text has an AHU tag; the ERV evidence lists S450/S455/S459 as
shipped loose or duct mounted; the front end evidence carries the M001.00 BMS notes (Schneider via BACnet), the
training passage and the "prequalified ... Approved Integrator's section" passage.

## 4. What I did not do, and why

- No explicit "dismissal" field: the writer's answer is a `System`, which has no place for one. A fact that is not
  AME's work is left out and the coverage gate still reports it on the review page. See question 1.
- Facts that name no system of the job (for example a global outside air sensor when the planner made no Global
  Points block) reach a writer only through a system whose passages carry them (here M710.00 reaches AHU). A
  "global points" block is the planner's (T-005b) to create.
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
2. Are the intake limits right (assumption 300, clarification 500, mark_note 120 characters)? A longer text is refused
   and the writer is asked again (up to the usual 3 attempts).
3. `PLAN_TEXT_LIMIT` 24,000 re-asks every reading pass on the next run (the dossier text changes). OK, or should the
   larger limit apply to the writer's evidence only?
