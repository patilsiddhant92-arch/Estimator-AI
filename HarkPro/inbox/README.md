# HarkPro inbox: how the lead and HarkPro work together

Lead: Claude (local, on the estimator's PC). Worker: HarkPro (remote).
The estimator approved this channel on 2026-10-10.

## Channel

- The lead writes tasks and answers in `HarkPro/inbox/` on branch `lead/hark-inbox`.
- HarkPro writes reports and questions in `HarkPro/outbox/` on its own task branch `hark/T-nnn`.
- `HarkPro/STATUS.md` (on `lead/hark-inbox`) shows each task: OPEN, ACCEPTED, DONE, REVIEWED, MERGED or CLOSED. Only the lead changes it.
- One task = one file `HarkPro/inbox/T-nnn.md` and one branch `hark/T-nnn`.
- Start every task branch from the commit that the task names. That commit is always on GitHub.

## Hard rules

1. Push only to branches that start with `hark/`. Never push to `main`, `rebuild` or `lead/*`. Never force-push a branch that the lead has fetched.
2. Change only the files that the task names. If you must change another file, write a question first.
3. No job data in git. Do not commit real job names, tags, sheet numbers, drawing text, proposals or evidence workbooks. Use only invented fixtures. Job work that the estimator gives you directly goes back to the estimator, not to git.
4. Do not edit `playbook/rules.md`, `playbook/shapes.json`, `playbook/wording.json` or the interface spec `docs/superpowers/specs/2026-10-04-rebuild-interfaces.md` unless the task says so.
5. Test first. The full suite must pass: `python -m pytest tests -q -p no:cacheprovider` with `PYTHONPATH=src` from the repo root. Put new tests under `tests/`.
6. Every commit message ends with `Co-Authored-By: Hark (AI)`.
7. The lead reviews, tests and merges. A task is not finished until the lead marks it MERGED.

## Estimator rulings that every task follows (2026-10-10)

- Evidence only: a line prints only when the job's documents show that device. The Master Template gives wording, order and hours. It never makes a line exist. `lines.json` "required" lines are not used.
- The highest count prints. Every other count that differs prints in a "*" note with both numbers and their sources.
- HarkPro rulings R2 to R22 are accepted, with the changes in `HarkPro/inbox/ref/playbook-edits-draft.md` and the answers below. R1 is replaced by the count rule above.
- Lighting integration given to the ATC vendor prints in Front End. Lighting monitoring stays in Misc Monitoring.
- VAV 24 V power-loop wiring prints when the mechanical drawings or the specs mention it.
- A damper inside a factory-controlled packaged unit stays with the factory when only the schedule mentions it. A remote duct damper shown on a riser or plan for that unit is AME's Furnish and Install.
- An exhaust fan with points and no AME controller carries 4 h per fan.

## Report format (`HarkPro/outbox/T-nnn-report.md`)

1. Task id, branch, last commit hash, base commit.
2. What you changed (files and one line each).
3. Tests added (names) and the full-suite result line.
4. What you did not do, and why.
5. Questions (or "none").
