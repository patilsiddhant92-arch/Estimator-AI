# Progress

- 2026-10-09 IST: GrokTeam folder and grok/work branch created from main @a54ea82. Team: Grok Bot (lead), Estimator QA, Builder, Reviewer.
- 2026-10-09 IST (Builder): bugs 1-6 have failing tests in `GrokTeam/tests/` (invented fixtures) and proposed patches in
  `GrokTeam/patches/01..06-*.patch` (not applied, not committed by Builder). Results:
  - Each patch makes its own test file pass. On clean src, only the bug cases fail; negatives and REGRESSION GUARDs
    pass both before and after.
  - Combined: GrokTeam/tests gives 54 passed and 14 xfailed (strict: bug 6 design notes).
  - Existing suite (`-m "not slow"`): clean src 9 failed (environmental) / 3735 passed. All six patches applied:
    15 failed / 3729 passed. That is 4 intentional contradictions needing owner decisions (test_plan missing mode;
    CNT-5 unit tag summed over floor plans; 2 sample-Playbook question lists), 3 flaky (also fail on clean src on
    rerun) and the baseline.
  - Details, design notes and doubts are in `patches/README.md`. Verified in throwaway worktrees with
    `patches/verify.sh`; the worktrees were removed afterwards.
  - Note: commit 49a237d (lead, "record template-as-checklist ruling") included an earlier, in-progress copy of
    these files. The current working tree is newer and uncommitted, and Reviewer has not reviewed it yet.

- 2026-10-09 Builder, Reviewer CHANGES NEEDED round: every test_06 xfail names its error (raises=); the broken-fixture check fails loudly. Real job tags replaced with invented ones (AHU-9X/AHU-9Y/ZR-7/X-90n) in test_04, README and patch 04 (comments only). `_vrf_job` control is now `field`. verify.sh always rebuilds its worktree at HEAD. verify.sh numbers are unchanged (54 passed, 14 xfailed). Full suite with patches: 15 failed / 3729 passed, the same set as before. CNT-5 and condensate-pump are on hold for Siddhant. Not committed.
- 2026-10-09 14:55 IST Builder, rulings round:
  - R2-R6 adopted as PROVISIONAL and R1 as FINAL (Q4 / R11). Q1, Q2, Q7 and Q11 are cited from discussion.md. All recorded in discussion.md.
  - Patch 02 (R2 standalone question), patch 04 (R3 schedule quantities) and patch 06 (R4 wording, R5 alarm/interlock, R6 no damper question, provisional R1 question removed) are updated.
  - New patch 07: `bms/rulings.py` with the DOCUMENTED_DEFAULTS table (Q1 and R1 only), R6, Q2, Q7 and Q11, hooked into run.py. New test file test_07.
  - 6c reworked to room-served assignment (strict xfails). Finding: no area-served link exists in src.
  - verify.sh now covers 07 and cleans new files. Result: 86 passed, 19 xfailed. Full suite: 17 failed / 3727 passed (5 intentional, 3 flaky, 9 baseline).
  - Not committed.
- 2026-10-09 15:15 IST Builder:
  - Q11 narrowed in patch 07 to control devices only (done before the pause). The README gains the R6 wording note.
  - Job-data cleanup in tests and the README: invented rooms and tags (LOUNGE 9, Lobby & Lounge / Lounge, LOUNGE 0907, STUDIO 0907 / MEDIA STUDIO 0407, AC-7-1, AC-8-1, VAV-7-2), and the T'STAT note reworded to "T-STAT SUPPLIED BY UNIT MFR.". The grep of the listed terms is now empty.
  - verify.sh numbers are unchanged (90 passed, 19 xfailed). Paused per the lead. Not committed.
- 2026-10-09 17:30 IST Builder (pause lifted for step 1):
  - 1a / B-02: new patch `08-schedule-reader.patch` and `tests/test_08_schedule_reader.py` (12 tests). Schedule rows now become ledger facts per tag: `schedule_qty`, `maker`, `area_served` and a `provider` owner (from the cell, or from the note a SEE NOTE cell points to). The revision block is no longer a schedule, and CONTROLS BY / NOTES counts as a remarks column. The AI pass schema is unchanged. The 6c `area_served` KINDS xfail moved out of test_06 (now 18 xfailed). The room-sensor patch is renumbered 09.
  - 1b: patch 04 extended with the demolition filter (new / existing to remain / removed). Per the lead's correction, `(E)` alone is existing, never removed; `(ER)`, `(D)`, a remove keynote tied to the tag, or a demolition sheet removes it. A schedule cap was added. 12 new tests in test_04, including the `(E)` negative, the `(ER)` positive, and test (5) on a dashed-only item.
  - verify.sh (path /tmp/gt-builder-verify, [08] added): all 8 fail before and pass after. Combined: 114 passed, 18 xfailed. Full suite with all 8: 16 failed / 3728 passed, the same set as before (5 intentional + environmental).
  - Not committed.
- 2026-10-09 17:45 IST Builder (step 1 follow-ups):
  - Patch 04: the cap reads 08's `schedule_qty` facts (`run.py` wraps `cross_check` in `scheduled_quantities(ledger_schedule_quantities(ledger))`, so the contract signature is kept), and falls back to the count quote's "QTY n" only with no qty column. 04+08 land together: verify.sh applies 08 before 04's "after" run, and the combined run applies cleanly.
  - Demolition and dashed questions now name the sheet and the reason. MD-x / MD### counts only from the title-block sheet number (fullmatch). DEMO counts only as a whole word in the title.
  - Cap question added (the cap lowered the count, extra placements on different new floor plans), with `floor_plan_sheet` built from the catalogue Sheet's types and title words.
  - test_04 now has 55 tests (+22). KL-01 (dashed lines cannot be read from the sheet text) appended to bugs.md.
  - verify.sh: all fail before and pass after. Combined: 136 passed, 18 xfailed. Not committed.
  - Full suite with all 8: 17 failed / 3727 passed (5 intentional + environmental/flaky). A first wiring with `cross_check(scheduled=)` broke `test_contracts` and `test_run_review_detect2`; I reworked it to a context variable and both pass now.
