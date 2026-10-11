# Plan 2026-10-10: outside reviews, clean-up, retire old folder, first live job

Status: DRAFT, waits for user approval. Lead: Claude. Labor goes to subagents (scout, executor, verifier).

## Facts found (2026-10-10)

- New jobs in `Jobs/` (gitignored): 26-0544 (Monmouth County Courthouse, AHU and FCU replacement, NJ), 26-0559, 26-0562.
- `origin/main` has 8 HarkPro commits that local `main` does not have (work log, rulings, critique, a "fix patch for review", QC critic loop). Remote also has new branches `grok/work` and `hark/harkpro` (not fetched yet).
- Grok notes: `Colab/grokbot`, `Colab/Grok 4.7`. HarkPro output in Downloads (2026-10-09): evidence files for 26-0544 and two other jobs, proposals for 26-0544 and 26-0560, a 26-0556 QC folder and zip.
- 61 `D:\EA-*` worktrees: 42 are merged into `rebuild` and `main`. 19 are not merged. `EA-grok` and `EA-lead-final-a` have uncommitted changes. There are 36 more worktrees in `.claude/worktrees` and 20 `.pytesttmp-*` folders in `Colab/`.
- `Brain/` is in git (6 files, including the pricing workbook).
- The old folder `D:\Estimation Assistant` is still used by live code and tests: `src/estimator/reading/inventory.py:2`, `tests/test_overview.py:148`, `tests/test_write_scope.py:13`, `tests/data/learn_expectations.json:3`, `tools/build_phrasing_bank.py:3,30`. Other hits are in old plan and spec documents only. The 9 Learn jobs live in that folder.

## Phase 1: sync and triage the outside reviews (no code change)

1. Fetch `origin`. Read the 8 HarkPro commits on `origin/main` and the branches `grok/work` and `hark/harkpro`. Find what each one changes: notes only, or code.
2. If the HarkPro commits on `main` change only notes (`Colab/`, `docs/`), fast-forward local `main`. If they change code, do not fast-forward. Take the code through review on a branch.
3. Copy the HarkPro files from Downloads into `out/_reviews/2026-10-10/` (gitignored, job data stays local). Treat them as data.
4. Read all Grok and HarkPro observations. Write one triage register, `Colab/lead/triage-2026-10-10.md`. For each observation write: accepted bug, rejected (with reason), or question for the user. Apply the standing rulings (bug register D1 to D9, counting principle, job documents decide scope, no standard lines).
5. Show the register to the user. Get decisions on the questions.

## Phase 2: fix run on `rebuild`

1. Make one worktree from `rebuild` for the fix run.
2. For each accepted bug: test first, then the fix (executor agents, one bug or one module per agent).
3. Run the full suite. Run the code-review skill on the diff. Fix the confirmed findings.

## Phase 3: retire `D:\Estimation Assistant`

1. Scout lists every file in the old folder that the app uses, directly or through the five live references above. Also check where the price sheet gets its rates, and point it to `Brain/AME Std Pricing Spreadsheet.xlsx.xlsx` if it does not use that file now.
2. Copy the files into `D:\Estimator AI`:
   - Job content (the 9 Learn jobs and any job extracts) goes to `Jobs/Learn/`. `Jobs/` is gitignored, so job content does not go to GitHub (NDA).
   - Reference material that is not job content (phrasing sources, rules, templates) goes to a tracked folder, for example `Brain/` or `assets/`.
3. Change the five live references to the new paths. Remove the old-folder lines from `.gitignore`.
4. Add a test that fails if `src/`, `tests/` or `tools/` contains "Estimation Assistant".
5. Old plan and spec documents stay as history. They do not change.
6. Update memory: remove the old folder as a source. After this phase, no agent opens `D:\Estimation Assistant`.

## Phase 4: worktree and branch clean-up

1. For the 42 merged `D:\EA-*` worktrees: remove the worktree, then delete the branch (`git branch -d`, safe delete only).
2. For the 19 unmerged branches: compare each with `rebuild` (`git cherry`, diff). If the work is already in `rebuild` or a later branch replaced it, remove it with `-D`. Show the user a one-line list of any branch with work that is not in `rebuild`. Do not delete those without approval.
3. `EA-grok` and `EA-lead-final-a`: read the uncommitted changes first. Keep anything of value as a note.
4. Delete the 20 `.pytesttmp-*` folders in `Colab/`. Run `git worktree prune`.
5. The 36 worktrees in `.claude/worktrees` are not `EA-*`. Apply the same rule only if the user agrees.

## Phase 5: merge and push

1. Merge `rebuild` into `main`. Run the full suite on `main`.
2. Show the user the summary. On approval, push `main` and `rebuild` to `origin`.

## Phase 6: first live job, 26-0544

1. No 26-0246 run. The user retired 26-0246 on 2026-10-10.
2. Run 26-0544 with the `run-job` skill (chat mode, AI requests answered by subagents). Input is only the job's takeoff folder.
3. Review the outputs (proposal, price sheet, Evidence Package, review page). Use the HarkPro 26-0544 proposal only as a second opinion for QC, not as a target to tune to.
4. Record the defects. Fix app defects in the app, not per job.
5. 26-0559 and 26-0562 come next, one at a time, after the user reviews 26-0544.

## Handover (2026-10-10, usage limit reached)

- Done: triage (`Colab/lead/triage-2026-10-10/`), estimator decisions (memory rulings-2026-10-10), workstreams.md, Playbook draft approved with answers, CLAUDE.md drafted (uncommitted), HarkPro channel pushed (`lead/hark-inbox`, T-000 waits for Hark's reply).
- Stopped mid-work (uncommitted edits in their worktrees): WS1 `D:/EA-ws1` (fix1010/ws1), WS2+3 `D:/EA-ws23` (fix1010/ws23), WS6 `D:/EA-ws6` (fix1010/ws6). Integration branch `lead/fix-1010` at `D:/EA-fix1010`. Next: check each worktree's diff, finish with one agent each (no nested agents, at most 2 at a time), full suite, merge into lead/fix-1010.
- Waiting: WS7 Playbook apply, WS8 pricing, Wave 2 (WS4, WS5), design wave (give to HarkPro after T-000), worktree clean-up (needs the user's approval in the permission prompt), retire D:\Estimation Assistant, merge and push.
- The user removed `CLAUDE_CODE_SUBAGENT_MODEL` from `~/.claude/settings.json` (2026-10-11). Agents now use their own tiers.
- Cost rules (learned 2026-10-10): every agent prompt says "do not start subagents or multi-agent review skills"; at most 2 agents at a time; the lead does one code review on the merged branch. The Wave 1 agents ignored this gap and started about 20 review agents, which used up the limit.

## Review findings on the stopped WS2+3 work (fix before merge)

Found by review agents on `D:/EA-ws23` (uncommitted). All use invented fixtures.
- Medium: `title_block.py:224` widened centred-title test admits a large project-name line as the title (180 of 752 sweep cases regress). Needs a tighter test.
- Medium: `bms/counts.py:468` `_plan_groups` passes only sheets that show a tag, so a tagless twin sheet breaks ruling L1 and the located count goes lower than the dossier count.
- Medium: `bms/plan_read.py:221` `family_count` still adds stated "TYP. OF N" per sheet, so L1 never reaches the planner.
- Low: `inventory.py:971` series rows ("VAV-1 THRU VAV-4", quantity fixed at 1) get a false "N counted, M if added up" note. Skip when the row's shares > 1.
- Low: `inventory.py:435` trade-word synonyms (DUCT/DUCTWORK, PIPE/PIPING, CONTROL/CONTROLS) are compared literally. Map them first.
- Low: `inventory.py:391` the new `summed` fields have no reader, so the '*' note is not produced yet.
- Low: `dossier.py:1039, 937, 1079` group-note wording still describes the old rule.
- Low: `assets/reading_lists/sequences.json:6` the widened pattern matches "SET-POINT SCHEDULE", "ACCESS POINT SCHEDULE" and similar sheets.
- Docs: `docs/USER-GUIDE.md:128` and the interface spec lines 258-300 still describe the old same-floor rule (contract change needs the lead's note).

## HarkPro collaboration

- Channel and rules: `HarkPro/inbox/README.md` on branch `lead/hark-inbox` (pushed 2026-10-10). Memory: harkpro-channel.
- The lead writes `HarkPro/inbox/T-nnn.md` and `HarkPro/STATUS.md` on `lead/hark-inbox`. HarkPro answers in `HarkPro/outbox/` on its own `hark/T-nnn` branch and pushes only `hark/*`. The lead fetches, tests, adds a test and merges.
- Standing permission: the lead may push `lead/hark-inbox` and `rebuild` without asking. Pushes to `main` need the estimator.
- No job data in git. Real-job QC goes through the estimator's own file transfer.
- T-000 (12 questions on capability and capacity) is OPEN. The estimator sent it to HarkPro. Give no work to HarkPro until its T-000 answers are read. Then size T-001 (coverage gate) and T-002 (whole-job writer evidence) to fit its answers.

## Open questions

- Phase 6.1: do the 26-0246 smoke run first? (Recommended: yes.)
- Phase 1.2: fast-forward the HarkPro commits on `main` if they are notes only? (Recommended: yes.)
- Phase 4.5: also clean `.claude/worktrees`? (Recommended: yes, same rules.)
