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
