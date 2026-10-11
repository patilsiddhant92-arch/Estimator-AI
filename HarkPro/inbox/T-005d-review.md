# Review of record: hark/T-005d (writer and evidence), 2026-10-11

Reviewer: Claude (Opus), worktree `D:\EA-rv-t005d` (detached at f7ebed4). Base `0e78113`. Commits `1c0c65c`
(writer and evidence), `f7ebed4` (prompt quotes, test_dossier, report). 13 files, +1,064 / -37.

## Verdict

Do not merge yet. It does not fix the stated root cause
(job-wide facts that name no tag still reach no writer), it can drop the control-diagram sheet it puts first, and its
intake removes real assumptions. Fix the three must-fix items, then merge (take T-005c's `model.py`).

## Merge checks (`git merge-tree --write-tree`)

- origin/lead/wave2: clean. origin/hark/T-005a: clean. origin/hark/T-005e: clean.
- origin/hark/T-005c: CONFLICT in `src/bms/model.py` (Device.mark/mark_note; T-005c adds `optional=True` and a
  `json_schema` change). Take T-005c's side; the author agrees (report :74-79).

## Tests

- Author's files (`tests/bms/test_t005d_writer.py`, `tests/test_dossier.py`): `81 passed in 276.66s`.
- `pytest tests/bms -q -n 10 -m "not slow"`: `1 failed, 2519 passed in 1003.70s`. The failure
  (`test_review_m018d.py::test_guard_the_counter_id_and_the_system_digest_are_the_same_in_every_process`) is a
  multi-process test on a loaded machine; alone `1 passed in 333.30s`, and it passed in the full run.
- Full suite `-n 10 -m "not slow"`: `4835 passed in 3223.20s (0:53:43)`.
- Reviewer's tests (below): 6 tests, 6 fail. Each failure is a finding.

## Findings

### Must fix

1. **Root cause not fixed: a job-wide fact that names no tag still reaches no writer.** Sequence selection is
   unchanged (`src/bms/ai_evidence.py:278-280`), and the new facts checklist uses the same name test
   (`ai_evidence.py:536-537`: `about.names(subject value)` or `names_tag(quote)`). A GENERAL sequence section with a
   global outside air temperature sensor and a changeover aquastat, and ledger facts with value None, reach neither
   the sequence block nor the checklist. The author's fact test passes only because its fact carries value "AHU-1"
   (`test_t005d_writer.py:201`). Fix: give every writer the job-wide sequence sections and the scope facts that name
   no tag of any system, under their own heading, with a cap.
2. **A long control-diagram sheet is dropped whole.** `_notes` puts controls sheets first and never excerpts them
   (`ai_evidence.py:447`), but `block` skips an entry longer than what is left of `NOTES_LIMIT` 12,000
   (`ai_evidence.py:241`). The branch raises `PLAN_TEXT_LIMIT` to 24,000 (`src/estimator/writing/dossier.py:59`), so a
   controls sheet of 12,001-24,000 characters is never given; a second controls sheet is lost once the first uses the
   budget. Fix: excerpt a controls sheet that does not fit, or give controls sheets their own block and limit.
3. **The intake drops real assumptions.** `_STATED` (`src/bms/ai.py:1285`) ignores negation: "the schedule does not
   state the quantity" and the fixture's own RTU.d4 why ("the schedule note names a detector ... without a count")
   match, and `_stated_not_assumed` (`ai.py:1337-1356`) sets assumption None and flag "none". A real uncertainty
   disappears from the proposal and the review. Fix: do not drop on words alone (log a finding for QC), or at least
   exclude negations.

### Should fix

4. **FUTURE auto-mark on any upper-case FUTURE in a quote** (`ai.py:1316`; checklist `ai_evidence.py:45`). Drawing
   text is upper case: "CAP FOR FUTURE CONNECTION BY OTHERS" marks the line "future", which prints red. Require the
   word next to the line's device words, or leave the mark to the writer and QC.
5. **Ruling 6's own failure pattern passes intake.** An assumption against a schedule row that states the fact, with
   a why naming the specification (the 26-0544 shape), is kept (`ai.py:1350` needs "schedule/sequence ... states").
   Only the prompts carry the rule (`write_system.md:73-74`, `qc_job.md:18`). Acceptable if the lead accepts prompt
   plus QC as the control; the report should say so.
6. **End-device checklist sets ownership.** `_end_devices_checklist` (`ai_evidence.py:495-517`) labels every schedule
   entry with a device word "listed with the unit (furnished with it; ... marked "notice")"; "SMOKE DETECTOR QUANTITY
   BY OTHERS" is labelled so. Say "names an end device" and leave the owner to the passage.
7. **Long flags stop the run.** `_length_problems` (`ai.py:1358-1375`) refuses an assumption over 300 or a
   clarification over 500 characters; after `max_attempts` the run stops (`ai.py:745-750`). Ruling 5 is presentation:
   make it a "check" finding, as `qc_job.md:15` already does.
8. **Real-job sheet number in prompt and code**: "control schematic on sheet M-710.00" (`write_system.md:79`,
   `ai.py:1291`). The brief forbids 26-0544 text in prompts. Use an invented sheet.
9. **`PLAN_TEXT_LIMIT` 24,000 under an unchanged `PLAN_TEXT_TOTAL` 400,000** (`dossier.py:59-61`, :1321): on a large
   job fewer sheets fit before "Stopped", and later sheets lose all text. Every cache key also changes (report
   :88-89). Check the sheet order, or raise the total.

### Note

10. `run.py:537-541` is a lead-owned file (hard rule 4): two lines for the lead to accept.
11. `write_system.md:92` "Lines often missed ..." is the 26-0544 comparison list as a prompt checklist. It is
    conditional on evidence and every line still needs a cited quote, so no line prints without evidence; but it is
    tuning to one job. The generic rule at :91 is enough.
12. Evidence size: facts capped at 60 (`FACTS_MAX`), notice at 20; the FUTURE list (`ai_evidence.py:482, 486-487`)
    and fact quote lengths have no cap. Add caps.
13. Contracts: the `model.py` change is additive; `sample_job.json` gains `"mark": "", "mark_note": ""` per device;
    `test_contracts.py` and the interfaces spec are unchanged. Add the two fields to the spec after the T-005c merge.

## Prompt quality

- write_system :73 "Never write an assumption that a schedule or the sequence states." Testable (QC :18; code only
  partly, finding 5). No conflict; matches the Playbook example at rules.md:251 (assume only when the schedule shows
  nothing).
- :74 "An assumption is only for what no schedule, sequence, points list or specification passage of this job
  states." Testable. Compatible with :35 (Playbook default parties still take an ownership assumption).
- :78-80 every device has mark/mark_note; a FUTURE item is "a line of its own ... even when the sequence also calls
  for it"; "notice" for a device "furnished with the unit or integral to it". Testable (`_marks`, QC). No GEM conflict:
  print order is unchanged.
- :85-87 schedule end devices read into scope; shipped loose "Install and Wire <device> (Furnished by Unit Mfr.)";
  unnamed devices take "the one line the Playbook gives". Testable; matches rules.md:335-349.
- :91 each listed fact "ends as one of: a line ..., the block's clarification, or the no_scope_reason". Testable
  (coverage gate). Tension with :58 "clarifications holds at most one item" plus the 500-character cap: many facts
  cannot all go into one short clarification.
- :92 "Lines often missed": finding 11.
- :96 short flags (25 words / 300, 40 words / 500), "an answer with a longer text is refused". Matches :47; finding 7.
- write_front_end :34-40: stated facts, marks, the Master Template front-end lines "when the documents call for
  them", integrator eligibility as a confirm clarification, short clarification. Testable; no conflict found.
- revise_system :16 "Never answer a finding with an assumption that a schedule or the sequence states". No conflict.
- qc_job :18-19: unmarked FUTURE line must_fix, furnished-with-unit without "notice" check, stated assumption
  must_fix, unscoped shipped-loose devices must_fix. No conflict.

No new instruction lets a line print without this job's evidence: every line still needs a ref whose quote the
mechanical check finds.

## Reviewer's test

`D:\EA-rv-t005d\tests\bms\test_t005d_review.py` (uncommitted, invented "Invented Library", unit ZZ-7). Six tests, all
fail: global outside-air sensor (finding 1), changeover aquastat (1), assumption against a stated schedule fact (5),
assumption that says the schedule does not state the value (3), long control diagram (2), unrelated FUTURE word (4).
