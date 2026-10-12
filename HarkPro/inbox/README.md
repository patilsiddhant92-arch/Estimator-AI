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

## Self-review before every push (mandatory from 2026-10-12)

Before HarkPro pushes a task branch, HarkPro starts a separate agent of its own that did not write the code. HarkPro gives it this checklist and the branch. It writes its findings into HarkPro's outbox report under "Self-review", and HarkPro fixes every item it finds before the push. The lead's review of record still follows; it found these same items in four of five branches this weekend, each costing a round trip.

Checklist:

1. Tests use invented fixtures only. No job text, no real project name, no real sheet number (M114.00, MD 111.00 and the like), no real tag list from a live job, in code, tests, prompts or comments. Replace with invented ones.
2. Every changed test still asserts the right behaviour. A pin changed to match new output needs a one-line reason in the commit; a pin that now asserts a wrong line (a label alone on a line, a heading out of order) is a defect, not a fix.
3. The Playbook wins over the GEM and over the Master Template when they disagree; the Master Template entry's own order wins over the GEM order; a line prints only with evidence from this job, except the Master Template front-end house lines. Check every new rule against `playbook/rules.md` and name the rule in the report.
4. Nothing drops silently: every count reduction records both numbers and a reason (set-aside, '*' line, question). Grep the diff for places that filter, dedupe or replace a number and ask where the dropped value is recorded.
5. Regexes and text detectors: list three sentences that must NOT match (for off-hours: "unoccupied 6 PM to 6 AM", "after-hours override", "no overtime permitted") and three that must; add them as tests.
6. Files outside the task's list are not touched. Lead-owned files (`model.py`, `run.py`, the fixtures, `test_contracts.py`, the interfaces spec) are touched only when the task names them, and the report lists every hunk.
7. The report exists in the outbox before the push, with the real tails of: the touched test files, `pytest tests/bms -q -n 4 -m "not slow"`, and the full suite. "Passed on my machine" without the tail does not count.
8. Each commit does one task; the subject names the task.
9. Red text and flags: FUTURE items, a non-AME BMS name, off-hours, prevailing wage and unknown counts ("Qty (##)") print red; one short '*' line per item, none over 160 characters, no label stranded alone.
10. Run `playbook-lint` if `playbook/` changed, and say so.
