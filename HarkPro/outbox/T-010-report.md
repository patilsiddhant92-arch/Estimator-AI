# T-010 report: freezestat and filter-switch ownership (ruling 23); source contradictions in red (ruling 25)

## 1. Task, branch, commits, base

- Task: T-010. Branch: `hark/T-010`. Base: **764389a** (`origin/rebuild` head, T-009 merged as of the fetch).
- Commits, oldest first:
  - `4aba751` T-010 task 1: freezestat and filter-switch ownership (ruling 23)
  - `1e36c24` T-010 task 2: source contradictions print in red (ruling 25)
  - `7045e57` T-010 task 1 review fixes: each device kind read on its own; Furnish and Wire refused when the sequence
    gives it to Unit Mfr.
  - `5bcf785` T-010 task 2 review fixes: long count contradictions packed with a repeated family label; one new
    function
  - the commit that adds this report, "T-010: report" (the last commit on the branch).
- Author and committer of every commit: "Hark (AI) <hark-ai@users.noreply.github.com>". Each message ends
  "Co-Authored-By: Hark (AI)".

## 2. What changed

| File | Change |
|---|---|
| `src/bms/ai.py` | Task 1: `owned_device_kind`, `_rule_quote`, `_ame_provides_ddc`, `_freezestat_filter_problems` (new section before T-005d's). `_check_system` takes `diagram` and `rules` and calls the check after `_heater_problems`. `_ask_system` computes `diagram` and passes it with `playbook.rules`. No other function. `_stated_not_assumed` is unchanged. |
| `src/bms/ai_evidence.py` | Task 1: `SEQUENCE_DIAGRAM_TITLES` and `sequence_and_diagram_ids`, next to `stated_ids`. |
| `playbook/rules.md` | Task 1: two rules at the end of "Packaged units" (text in section 5). |
| `src/bms/prompts/write_system.md` | Task 1: two Ownership bullets naming both rules. The "notice" sentence, the two end-device sentences and "Lines often missed" changed. |
| `src/bms/render.py` | Task 2: constants (`COUNTS_DIFFER`, `COUNTS_CONT`, `RED_LINE_LIMIT`, `OWNER_DIFFERS`, `OWNER_PLACE`, `OWNER_PAIR`, `_OWNER_ROLES`), one new function `_contradiction_lines`, and the one place in `_system_blocks` that builds the note items and the traced lines. |
| `tests/bms/test_t010_ownership.py` | New, 37 tests. |
| `tests/bms/test_t010_contradictions.py` | New, 11 tests. |
| `tests/bms/fixtures/sample_playbook/rules.md` | **Outside the task's list.** PBK-10c forced it: the two new rule names, one sentence each (section 7). |
| `tests/bms/test_t005d_fixes.py`, `test_render.py`, `test_render_count_notes.py`, `test_count_added_up.py`, `test_citations_reviews.py`, `test_t005e_addendum.py` | Pins (section 7). |

`revise_system.md` and `qc_job.md` did not change. Neither file names a freezestat or a filter switch. qc_job's "furnished with
the unit ... without mark notice is a check finding" does not contradict ruling 23.

## 3. Devices, slots, words and the detector (task 1)

`ai.owned_device_kind(name, slot="")` returns "freezestat", "filter switch" or None. It uses **both** the slot and the name:
- Slots (`playbook/shapes.json`): `freezestat` gives freezestat, and `filter_dp` gives filter switch. The slot wins.
- Words in the device name (case-insensitive):
  - freezestat: `\bfreeze[\s-]?stats?\b` (Freezestat, Freeze Stat, Freeze-stat, Low Limit Freezestat).
  - filter switch: `\bfilters?\s+((differential\s+)?(pressure|dp|d.p.)\s+)?(switch|status)\b` or
    `\bdirty[\s-]+filters?\s+(switch|status|alarm|indicator)\b` (Filter Switch, Filter Status, Filter Differential
    Pressure Switch, Filter DP Switch, Dirty Filter Switch / Alarm).
- Tested must-match names: Freezestat, Low Limit Freezestat, Dirty Filter Switch, Filter Differential Pressure Switch, Freeze
  Stat, Filter Status. Tested must-not-match names: Discharge Air Temperature Sensor, Duct Smoke Detector, Filter Section Access
  Door, Freeze Protection Pump, Oil Filter Housing.
- The check skips two kinds of line. A line in a slot that the shape gives as a **point** is a point, not the device (for
  example a "Filter Status" point line). A kept device (`kept_ids`) is not checked either.
- Cited quotes: the check decides whether a passage "names" the device by reading **each kind separately**
  (`_KIND_WORDS[kind]`, review fix M1). One passage can name the freezestat and the filter switch, and it counts for each.
- Words that do not count (only the slot catches them): "low limit thermostat", and "low temperature detection" without
  "freezestat". See question 6.

### The check (intake, `_check_system` -> `_freezestat_filter_problems`)
- The case comes from `System.control`: "field" or "packaged". Any other value gets no check.
- The rule name and its first sentence come from the loaded Playbook (`playbook.rules`). When the rule is not in the loaded
  Playbook, that case is not checked, because the Playbook wins.
- Unit with AME's DDC. The answer is accepted only in these two forms:
  - (a) verb "Furnish and Wire", furnished_by AME, wired_by AME, **and** no cited sequence or controls-diagram passage that
    names the device says the unit manufacturer furnishes it (review fix M2);
  - (b) verb "Wire", furnished_by Unit Mfr., wired_by AME, **and** a cited ref that meets all of these:
    - its id is in the sequence or controls-sheet block;
    - its quote names the device;
    - `stated_parties(quote)["furnished_by"]` is "Unit Mfr.".

  Every other form is refused.
- Packaged unit (factory controls): a freezestat line must cite a sequence or controls-sheet passage whose quote names a
  freezestat. Otherwise it is refused with the second rule. The verb is not checked there. Filter switches on packaged units are not
  checked: they stay under "Nothing inside the unit is a line".
- "Sequence or controls diagram" ids come from `ai_evidence.sequence_and_diagram_ids(evidence)`. These are the entry ids under "The
  sequence of operation for this system:" and "Controls sheets that name it (control diagrams, points, sequences):". Schedule,
  notes, spec and job-wide blocks never count.
- Reason forms (invented ids). Each quotes the rule's name in quotes and its first sentence:
  - wrong verb: `device QZ.d1 (Freezestat): it is “Furnish and Install” furnished by AME, wired by AME; it breaks the
    Playbook rule "Freezestat and filter switch on a unit with AME controls": On a unit whose DDC AME provides, AME
    furnishes and wires the freezestat and the dirty-filter switch. Write “Furnish and Wire <device>” (furnished and
    wired by AME), or “Wire <device> (Furnished by Unit Mfr.)” citing the sequence or controls-diagram passage that
    gives it to the unit manufacturer.`
  - Unit Mfr. on a schedule only: `...: no cited sequence or controls-diagram passage says the unit manufacturer
    furnishes it (a schedule row or note is not enough); it breaks the Playbook rule "..."...`
  - Furnish and Wire against a sequence that gives the device to Unit Mfr. (M2): `...: a cited sequence or
    controls-diagram passage says the unit manufacturer furnishes it, so the line is “Wire <device> (Furnished by Unit
    Mfr.)”; it breaks the Playbook rule "..."...`
  - packaged: `device QZ.d1 (Freezestat) is a freezestat line on a packaged unit that cites no sequence or
    controls-diagram passage naming a freezestat; it breaks the Playbook rule "Freezestat on a packaged unit": On a
    packaged unit AME mostly never furnishes a freezestat. Delete the line, or cite the passage that names it.`

## 4. A packaged unit whose controller AME furnishes to the manufacturer

The planner (`plan._control`) gives "packaged" whenever a provider fact names the factory or the manufacturer, so such a unit
usually shows as "packaged". The check treats a "packaged" system as a **unit with AME's DDC** when any line of the answer (kept
lines included) is in slot `controller` with furnished_by AME. In that case the first rule applies to both devices and the packaged
freezestat rule does not. Without such a controller line it is a plain packaged unit. Test:
`test_a_packaged_unit_with_an_ame_furnished_controller_takes_the_ame_ddc_rule`.
**Still open:** the validator's `_packaged` still gives that AME controller line a **must_fix** ("No AME controller on a
packaged unit") and gives an AME-furnished device a check. That behaviour was there before this task and is unchanged here, because
validate.py is off-limits. See question 5.

## 5. Playbook text, prompt sentences, proposal

Exact text added to `playbook/rules.md` at the end of "Packaged units", after "Template is the ideal case":

```
### Freezestat and filter switch on a unit with AME controls
On a unit whose DDC AME provides, AME furnishes and wires the freezestat and the dirty-filter switch. The line is
"Furnish and Wire <device>". The one exception is a sequence or a controls diagram that says the unit manufacturer
furnishes the device: the line is then "Wire <device> (Furnished by Unit Mfr.)". A schedule row or a schedule note
alone does not give the device to the unit manufacturer.

### Freezestat on a packaged unit
On a packaged unit AME mostly never furnishes a freezestat. Write no freezestat line unless the sequence or the
controls diagram names it.
```

The last sentence of the first rule comes from this task file's settled point: "A schedule passage alone never gives one of the two
devices to the unit manufacturer". `playbook-lint` is clean (section 9).

**Proposed sentence (not made)** for "Unit control devices when AME provides the controls", placed after "...when the factory
installs the device and AME wires it.":

> The freezestat and the dirty-filter switch are the exception: they are "Furnish and Wire" (see Freezestat and
> filter switch on a unit with AME controls).

Changes to `write_system.md`:
- Ownership: two new bullets name "Freezestat and filter switch on a unit with AME controls" and "Freezestat on a packaged
  unit".
- "notice" sentence, added: "Such a schedule entry never moves a freezestat or a dirty-filter switch to the unit manufacturer:
  on a unit whose DDC AME provides it stays “Furnish and Wire <device>”, and on a packaged unit a freezestat that only the
  schedule names is no line (see the Ownership section)."
- End devices: "Read each into scope, except a freezestat on a packaged unit: it is a line only when the sequence or the controls
  diagram names it." On shipped-loose: "A freezestat or a dirty-filter switch on a unit whose DDC AME provides is “Furnish
  and Wire <device>” even then, unless the sequence or the controls diagram gives it to the unit manufacturer."
- "Lines often missed": "a freezestat (on a packaged unit only when the sequence or the controls diagram names it)".

## 6. The red lines (task 2) and how they are painted

**Painting:** each red line is a note `Item(kind="note", runs=(Run(text=line, red=True),))`, built the same way `_front_end`
builds its red notes. `Device.mark` is not used. The lines print after the block's other "*" notes and are passed to
`_traced(system.key, printed, notes + red)`, so they are in `draft.lines`.

- **Count**: `*{family} counts differ: {counts}`.
  - `{counts}` is exactly `_counts_text(family.count, playbook, ids)`, the header bracket's contents in `_count_part`'s words.
  - Order: the printed (highest) count with its place first, then every other count, highest first, then the L1 sum last.
  - Example (invented): `*Fan Coil Unit counts differ: 55 per M-901; 1 per schedule rows; 1 per M-902`.
  - No line when every other count equals the printed count. No line for an L1 `added_up` sum alone.
  - One line per header family (`_header_families`), in header order.
  - **Long contradiction (review fix S1):** the counts are packed into lines of 160 characters or fewer. Each continuation
    starts `*{family} counts differ (cont.): `, so no bare `*N per <place>` line prints and no number is lost. Invented
    19-sheet example, from the test:
    ```
    *Fan Coil Unit counts differ: 55 per M-901; 19 per M-919; 18 per M-918; ... 12 per M-912        (154 chars)
    *Fan Coil Unit counts differ (cont.): 11 per M-911; 10 per M-910; ... 3 per M-903               (155 chars)
    *Fan Coil Unit counts differ (cont.): 2 per M-902; 1 per M-901
    ```
  - When the printed count has no place: `*Exhaust Fan counts differ: 5; 3 per M-101`. This is the same as its bracket. See
    question 7.
- **Owner, structured form**: `*{device}: this line has it {mine}; {place} says {theirs}`.
  - Example (invented): `*Freezestat: this line has it furnished by AME; 23 09 93 Invented Sequence says furnished by
    Unit Mfr.`
  - `{place}` is `ids.place(ref.where)` of the first contested ref. When there is none, it reads "the cited schedule or
    sequence".
- **Owner, fallback form**: `*{device}: {assumption.what}; {assumption.why}`. It is used when no cited quote settles the
  parties but the assumption names AME on one side and Unit Mfr. on the other.
- Every line starts with "*", is 160 characters or fewer, and has no source id. Device and family names go through
  `ids.without_issued`. A repeated line prints once. A red line that repeats a black note is dropped.
- How the two parties are found (inside `_contradiction_lines`; review fix S2 folded `_owner_contest` into it):
  1. Only a device with `flag == "ownership"` and an `assumption` is read. `ai._stated_not_assumed` makes that case.
  2. Each ref's quote goes through `ai.stated_parties`. For each role (furnished, installed, wired), the role is contested when the
     line's party and the quote's party are exactly {AME, Unit Mfr.}.
  3. When no quote settles it, `ai._party_of(what)` and `ai._party_of(why)` are compared.
  4. Any other pair (for example AME against the Electrical Contractor) gives no red line, and the black `*Assumed` line stays.
  - A contested device's black `*Assumed` line is not printed (`_notes` gets the devices minus the contested ids).
- A family with **both a set-aside and other counts** prints both lines. First comes the black set-aside line from `_count_note`,
  unchanged (`*FC counted once, labelled again on M-904 and M-905: 4 set aside, 55 counted`). The red counts-differ line
  follows. The set-aside value is not repeated in the red line.

## 7. Pins changed, with reasons

Task 1:
1. `test_t005d_fixes.py::test_an_assumption_that_says_the_schedule_is_silent_is_kept` (4 params). Its invented "Filter Switch"
   on a field unit was "Furnish and Install", which ruling 23 now refuses. It now passes `verb="Furnish and Wire",
   installed_by="Unit Mfr."`. The assertion (the assumption is kept, flag "assumed") is unchanged.
2. `tests/bms/fixtures/sample_playbook/rules.md`: added the two rule headings, one sentence each. PBK-10c
   (`test_the_sample_playbook_lints_clean_with_the_rule_names_the_code_needs`) requires every rule name a prompt quotes to be
   in the sample Playbook. This fixture is outside the task's file list (question 0 below).

Task 2. These are the 22 render pins. Each now also expects the contested family's one red line after the block's other notes.
The header bracket and every other assertion are unchanged:
- `test_render.py`:
  - `test_rooftop_block_golden` (RTU 2 vs 1);
  - `test_confirm_note_and_count_note_for_vrf` (Branch Selector 2 vs 1);
  - `test_count_note_is_one_line_per_block_beside_the_confirm` (the confirm line is now second to last);
  - `test_a_two_family_count_note_names_each_family` ("the device does not repeat the family count" now counts only lines
    that do not start with "*").
- `test_render_count_notes.py`: in each of these, `notes == []` becomes the one red line with the bracket's numbers:
  - `test_every_kind_of_other_count_prints_with_its_number_and_its_place` (x7);
  - `test_an_alternate_block_names_its_other_counts_too`;
  - `test_a_printed_count_below_the_highest_with_no_source_is_named`;
  - `test_a_zero_below_the_highest_is_named_not_dropped`;
  - `test_two_families_with_the_same_counts_each_name_their_own_note`;
  - `test_a_line_that_carries_its_familys_count_still_prints_it_once`.
- `test_count_added_up.py`: in these, the red line ends with the L1 sum. The pins for a sum alone stay `[]`:
  - `test_the_note_puts_the_sum_after_every_other_count`;
  - `test_a_line_that_carries_the_family_count_adds_no_second_note` (x2).
- `test_citations_reviews.py::test_a_count_note_place_is_a_sheet_never_an_id_and_a_stale_note_is_not_rewritten` (x10):
  `lines[-1:]` becomes `lines[-2:]`. The "no issued id" check still holds over every line.
- `test_t005e_addendum.py::test_one_short_star_line_per_item_and_no_quantity_note` (AHU 2 vs 1).

Review fixes:
- `test_t010_contradictions.py::test_a_long_count_contradiction_prints_as_short_lines_with_every_number` now asserts the packed
  form. The first line is "*Fan Coil Unit counts differ: 55 per M-901; ...", every other line starts "(cont.)", and every
  number appears in order. Before, one line printed per count. The test was updated first and failed before the code change.

## 8. What the review page, Evidence Package and validator show

- **Review page** (`review.py`, unchanged). It is built from the Job (`review._questions`), not from the draft, so it shows no red
  line. It shows the same contradictions as before: the ownership card ("Who furnishes, installs or wires this line is not
  settled." with the full assumption naming both parties) and the family-count cards. Ruling-23 lines show like any device
  line, with their refs and quotes. A refused intake answer never reaches the page: it is asked again, through the API once more
  with the reason, or through chat with the refusal written while the run waits.
- **Evidence Package** (`evidence.py`, unchanged). `run.py` passes only `{device_id: text}` for traced lines that have a device
  id. Red notes have `device_id=None`, so **they do not reach the Evidence Package**. The package keeps its numbers as before:
  each family count row with its other counts and full citations (L1 sum included), and each device row with its assumption and
  flag "ownership". See question 1.
- **Validator** (`validate.py`, unchanged). It reads the Job only, so task 2 does not affect it. `_verb` accepts both ruling-23
  forms ("Furnish and Wire" = AME furnishes and wires; "Wire" = AME wires what it does not furnish). It has no ruling-23 check
  of its own, so a line the estimator edits by hand is not checked against the rule. On a packaged unit, `_packaged` gives an
  AME-furnished freezestat a "check" and an AME controller a **must_fix**. That behaviour is unchanged (question 5).
- Proposal and price sheet get the red note items the same way as the front end's red notes.

## 9. Test tails (real output)

Write-first runs for the review fixes:
- M1/M2, `tests/bms/test_t010_ownership.py` before the ai.py change: `4 failed, 33 passed in 73.05s`. The 4 failing tests were
  the M1 test and the three M2 params.
- S1, the long-contradiction test before the render.py change: `1 failed, 10 deselected in 1.56s`
  (`assert red[0].startswith("*Fan Coil Unit counts differ: 55 per M-901; ")`).

Touched files, task 1 (test_t010_ownership, test_t005d_fixes, test_playbook_pbk, test_rule_names):
```
........................................................................ [ 68%]
.................................                                        [100%]
105 passed in 2.96s
```

Touched files, task 2 plus task 1's new file (test_t010_contradictions, test_t010_ownership, test_render,
test_render_count_notes, test_count_added_up, test_citations_reviews, test_t005e_addendum):
```
........................................................................ [ 95%]
................                                                         [100%]
376 passed in 15.25s
```

`PYTHONPATH=src python -m bms playbook-lint`:
```
The Playbook at <checkout>/playbook is clean.
```

Full suite, `pytest tests -q -n 2 -p no:cacheprovider -m "not slow"` (at 5bcf785, the code commit before this report):
```
=========================== short test summary info ============================
FAILED tests/bms/test_ai.py::test_chat_writes_a_request_then_reads_the_answer_and_caches_it
FAILED tests/bms/test_ai.py::test_chat_refuses_an_answer_that_breaks_the_schema
FAILED tests/bms/test_ai.py::test_a_cached_answer_clears_a_request_left_behind_by_a_killed_run
FAILED tests/bms/test_ai.py::test_write_system_through_the_chat_rejects_and_asks_again
FAILED tests/bms/test_review_final3.py::test_a_real_child_failing_with_the_resource_code_is_run_three_times_then_reported
FAILED tests/test_assets.py::test_running_on_the_project_python - AssertionEr...
FAILED tests/test_main.py::test_the_output_folder_being_a_file_that_is_open_is_plain
FAILED tests/test_revert_audit.py::test_a_tools_change_is_reverted_too - Asse...
FAILED tests/bms/test_status_review.py::test_every_normal_exit_writes_the_state_whole_and_status_agrees
9 failed, 5541 passed, 10 skipped, 4 xfailed, 208 warnings in 404.59s (0:06:44)
```
All 9 are the known environment failures: 4 test_ai chat tests (the fifth, `test_every_cleanup_is_logged_beside_the_cache`, passed this run), review_final3 resource-code, test_running_on_the_project_python, output-folder-open, the flaky status_review normal-exit, and the load-flaky revert_audit. The revert_audit failure this time was `test_revert_audit.py::test_a_tools_change_is_reverted_too`. Run alone on 5bcf785 four times it gave 3 passed and 1 failed, and it passed on base 764389a. Neither `tools/` nor that test differs from base. No other failure.

## 10. Self-review

An **independent reviewer agent** ran the README checklist on the branch at 1e36c24. It ran in a separate context and did not write
the code. It found **3 must-fix** items and several should-fix items. A fourth agent, which wrote neither task, made the fixes and
this report. Items and how each was handled:
- **M1, must-fix** (ai.py, the passage detector). `owned_device_kind(quote)` returned only the first kind it found. A sequence
  passage naming both the freezestat and the filter switch therefore never counted for the filter switch, and "Wire Dirty Filter
  Switch (Furnished by Unit Mfr.)" on such a passage was wrongly refused. **Fixed** in `7045e57`: each kind is read separately
  (`_KIND_WORDS[kind]`). New test: `test_a_passage_naming_both_devices_counts_for_the_filter_switch_too`.
- **M2, must-fix** (ai.py). "Furnish and Wire <device>" was accepted on a field unit even when a cited sequence or
  controls-diagram passage gives the device to the unit manufacturer. That is the rule's one exception, so the line must be
  "Wire ... (Furnished by Unit Mfr.)". **Fixed** in `7045e57`: such a line is refused, and the reason quotes the first rule.
  New tests: `test_furnish_and_wire_is_refused_when_the_sequence_or_diagram_gives_it_to_the_manufacturer` (freezestat on a
  sequence passage, freezestat on a controls-diagram passage, dirty filter switch on a sequence passage). This also settles the
  task-1 author's open question about accepting "Furnish and Wire" against such a passage.
- **M3, must-fix** (checklist 7): no outbox report on the branch. **Fixed** in the report commit: this file.
- **S1, should-fix** (render.py). A long count contradiction split by `short_points` into one bare `*N per <place>` line per
  count, so numbers were stranded on lines with no label (checklist 9). **Fixed** in `5bcf785`: the counts are packed into lines of
  160 characters or fewer, each continuation repeating "*<Family> counts differ (cont.):". The test was updated.
- **S2, should-fix** (render.py, function limit). The task allows "a new function", but task 2 added two
  (`_contradiction_lines` and `_owner_contest`). **Fixed** in `5bcf785`: `_owner_contest` is folded inline into
  `_contradiction_lines`, so one new function remains.
- Other should-fix observations are carried as questions 1 to 7 below.
- Checklist status after the fixes:
  1. Fixtures are invented (QZ-1, FC, M-9xx, "Invented Set.pdf").
  2. Every changed pin has its reason above.
  3. Both rules are in the Playbook, and the check quotes them.
  4. No count is dropped: the red line repeats every number of the bracket, and the bracket and the Evidence Package keep
     theirs.
  5. The detector has must-match and must-not-match tests.
  6. One file is outside the task's list: the sample_playbook fixture, forced by PBK-10c.
  7. This report is in the outbox before the push, with real tails.
  8. One task per commit, and each subject names its task.
  9. Red lines are 160 characters or fewer, and no label stands alone.
  10. `playbook-lint` is clean.

## 11. What I did not do, and deviations

- **Multiple agents (deviation):** the estimator asked for this task to be done by several agents. Task 1, task 2, the reviewer
  and the fixer were separate agents. Task 2 was written in its own worktree (`t010-red`) and then put on `hark/T-010` after
  task 1. The README's "self-review agent" is the reviewer above. The task file's "do not start subagents" was set aside on the
  estimator's instruction.
- **Test runs:** tests ran with `-n 2`, not the task's `-n 4`, because of the worker's resource limit. The full suite was run
  once, with `tests` covering `tests/bms`, rather than as two separate runs.
- The known environment failures are listed in section 9. They come from the remote sandbox (chat transport, project Python,
  open output folder, process and resource limits). None of them is in a file this task touches.
- **Packing limit:** the packed count line keeps each "N per <place>" whole. A single part longer than about 120 characters
  (only possible with an unusually long place name) would make that one line exceed 160 characters. No fixture has one.

## 12. Questions for the lead

0. The fixture `tests/bms/fixtures/sample_playbook/rules.md` is outside the task's file list, but PBK-10c forced the edit. Is
   it OK as made?
1. **Evidence Package:** red notes do not reach it, because `run.py` passes only device lines (`{device_id: text}`). Should the
   lead pass note lines in `run.py` or `evidence.py`, or are the existing count rows and the "ownership" flag column enough?
2. **Double printing:** the writer's own black clarification can already name the same count contradiction. Examples are the
   golden RTU "*Unit count carried at 2; the roof plan shows 1" and VRF "*Branch selector count: ... - to be confirmed". The
   red line now prints beside it. Should a `write_system.md` sentence tell the writer not to write such count notes, since the
   renderer now prints them?
3. **Order:** silent-scope star lines (`_scope_star`, for lines the scope is silent on) are added to the block later, so they
   print after the red line. The task says the red line prints after the block's other "*" lines. Should they move ahead of it,
   which needs a change outside the one allowed place?
4. A device flagged "quantity" that also has an AME / Unit Mfr. owner contest gets no red owner line, because
   `_stated_not_assumed` keeps "quantity" first. Is that acceptable, or should the owner contest also print?
5. The validator gives a packaged unit with an AME-furnished controller a **must_fix** ("No AME controller on a packaged unit"),
   while ruling 23 and "Unit control devices when AME provides the controls" treat that unit as AME DDC. Should `_packaged` in
   validate.py be revisited?
6. Should "low limit thermostat" (and "low temperature detection") count as a freezestat in the name detector? Today only the
   slot `freezestat` catches them.
7. When the printed count has no place, the red line reads `*Exhaust Fan counts differ: 5; 3 per M-101`, with a bare first
   number, the same as the bracket. Should it say something like "5 carried" instead?
