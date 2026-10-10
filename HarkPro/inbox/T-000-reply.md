# T-000 reply (lead, 2026-10-11)

Thank you for the T-000 report. Answers to your questions:

1. Interpreter: use Python 3.13 (3.13.5 is good). Do not use 3.12.
2. Rule 5: "No failures except the 9 environment failures" is a pass only if your report names the 9 tests and you show that the same 9 tests also fail on an unchanged `rebuild` in your sandbox.
3. Conflicts C11-C16 and R1: mark them as superseded. The estimator's rulings of 2026-10-10 replace them. Make sure that references to "lines.json" are removed.
4. Round-2 fixes and `hark/evidence-ui`: push each one as its own `hark/*` branch, based on `origin/rebuild`. They are references only. The lead does not merge them without review and tests.
5. Sub-agents: you can use your own agents. Each one works in its own worktree, and each one obeys the channel rules.

## New rule: check the inbox on a schedule

From now on, check `origin/lead/hark-inbox` every 10 minutes while you work, as the estimator set on your side. When a new `HarkPro/inbox/T-nnn*.md` file appears, start it. When you push to `hark/*`, the lead sees it in 1 minute and replies on `lead/hark-inbox`. Questions for the estimator go in your report under "Questions for the estimator".

T-001 and T-002 follow soon. Do not start new work before they arrive.
