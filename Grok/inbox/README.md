# Grok inbox: how the lead and Grok work together

Lead: Claude (local, on the estimator's PC). Worker: Grok (outside agent).
The lead opened this channel on 2026-10-11.

## Channel

- The lead writes tasks and answers in `Grok/inbox/` on branch `lead/grok-inbox`. The lead pushes that branch.
- Grok writes reports and questions in `Grok/outbox/` on its own task branch `grok/G-nnn`.
- `Grok/STATUS.md` (on `lead/grok-inbox`) shows each task: OPEN, ACCEPTED, DONE, REVIEWED, MERGED or CLOSED. Only the lead changes it.
- One task = one file `Grok/inbox/G-nnn.md` and one branch `grok/G-nnn`.
- Start every task branch from the base that the task names. That base is always on GitHub.
- A task file can name a different branch or report file. Then use the names in the task file. G-001 and G-002 do this.

## Every 10 minutes

1. Run `git -C "D:/Estimator AI" fetch origin`.
2. Read `Grok/STATUS.md` on `origin/lead/grok-inbox`: `git -C "D:/Estimator AI" show origin/lead/grok-inbox:Grok/STATUS.md`.
3. Find the tasks that STATUS shows as OPEN. Do them in the order that STATUS lists. Do one task at a time.

## For each task

1. Read the task file: `git -C "D:/Estimator AI" show origin/lead/grok-inbox:Grok/inbox/G-nnn.md`.
2. Make a worktree on a new branch from the base that the task names: `git -C "D:/Estimator AI" worktree add D:/EA-grok-<task> -b grok/G-nnn <base>`.
3. Work only in that worktree. Do not work in `D:\Estimator AI`.
4. Test. Commit.
5. Push only `grok/G-nnn`.
6. Write `Grok/outbox/G-nnn-report.md` on that branch. Put the real test output in it.
7. Commit the report. Push `grok/G-nnn` again.
8. Take the next OPEN task.

## Sent-back tasks

The lead can send a task back. Then the task file has the mark SENT BACK.
The file lists the fixes. It also names a tests file to add.
Do the fixes on the same branch. Add the tests file. Update the report with the new test output. Push the same branch again.

## Hard rules

1. Push only the task branch `grok/G-nnn`. Never push `main`, `rebuild`, `lead/*`, `takeoff/*` or `hark/*`. Never merge. Never force-push a branch that the lead has fetched.
2. Change only the files that the task names. If you must change another file, write a question first.
3. Use only invented fixtures. Never copy job text. Never open `Jobs/`, `out/` or `.pdf` files.
4. Do not edit the files in `playbook/`. Do not edit the interface spec `docs/superpowers/specs/2026-10-04-rebuild-interfaces.md` unless the task says so.
5. Test first. Put new tests under `tests/`. Run the checks that the task names. Every test must pass.
6. Use `D:\Estimator AI\.venv\Scripts\python.exe` for all Python. Run every command from your worktree with `PYTHONPATH=src` set. Without it, the venv loads the code of another checkout. In Git Bash: `cd /d/EA-grok-<task> && PYTHONPATH=src "/d/Estimator AI/.venv/Scripts/python.exe" -m pytest <files> -q -p no:cacheprovider`.
7. Run one pytest at a time. Use `-n 4` at most. Other suites run on this machine.
8. You may use several agents of your own. Give each agent file ownership. Never let two agents edit one file.
9. Every commit message ends with a blank line and `Co-Authored-By: Grok <noreply@x.ai>`.
10. The lead reviews every branch and merges. A task is not finished until the lead marks it MERGED.

## Estimator rulings that every task follows (2026-10-10)

- Evidence only: a line prints only when the job's documents show that device. The Master Template gives wording, order and hours. It never makes a line exist.
- The highest count prints. Every other count that differs prints in a "*" note with both numbers and their sources.

## Report format (`Grok/outbox/G-nnn-report.md`)

1. Task id, branch, last commit hash, base commit.
2. The commits (hash and subject) and the diff stat against the base.
3. What you changed (files and one line each).
4. Tests added (names). Also the real tail of each test run, with its result line.
5. What you did not do, or could not do as written, and why.
6. Questions (or "none").
