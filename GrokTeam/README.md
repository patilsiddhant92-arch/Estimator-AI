# GrokTeam

Work area for Grok Bot's team (Grok Bot lead, Estimator QA, Builder, Reviewer) on Estimator AI.

## Rules
- Work only inside `GrokTeam/`, on branch `grok/work` (cut from `main`).
- Never edit Claude's main app (`src/`, `tests/`, `playbook/`, `assets/`, `tools/`, `docs/`, `AGENTS.md`) or `HarkPro/`.
- Read the app's outputs or import `bms` read-only. Anything the main app needs goes in `GrokTeam/patches/` or a report, never a commit to app code.
- No real job or bid data in this folder (no `out/`, `.superpowers/`, `.claude/worktrees/`, bid folders). Invented fixtures only.
- Every change is reviewed by Reviewer before commit. Pushes only to `grok/work`, approved by Siddhant.

## Files
- `progress.md`: what we did and when.
- `tasks.md`: open, in-progress and done tasks.
- `bugs.md`: problems found in the app's outputs, with evidence.
- `discussion.md`: questions for Siddhant and his rulings.
