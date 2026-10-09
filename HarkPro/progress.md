# Progress log

## 2026-10-08
- Repo access set up through the Hark GitHub App.
- Read the app, AGENTS.md and the design spec. Ran a full audit (five parallel audits, each High/Critical backed by a repro). Baseline: tests/bms 1,696 pass, 6 fail (Windows-only).
- Cross-checked the Gemini bug file: most of its claims were confirmed or partly confirmed; it missed the reading-layer and count defects.

## 2026-10-09
- Evidence Package redesigned (Summary, device-only Scope lines, Findings/Counts/Citations/System notes). Commit 7e27873 on hark/evidence-ui, not pushed.
- First AI run of Job 2a (no API key: Hark answered the app's AI requests). It printed VAV 30 and EF/AC 4 instead of 15 and 2. Root cause: app logic, not the AI answers (same-floor sum, revise reverted to planner, VAV classing, diffuser codes).
- Fixed READ, PLAN, DOC-1..4, CORE, RUN-1/2/4/11 and VAV scope. Suite: 3,911 pass, 11 pre-existing fails.
- Job 2a rerun on the fixed code: VAV 15 (field DDC, 45 h), AC 2, CP 2, BIPO 2 as Add Alternate #1, EF left out. Price sheet total incl. tax $15,687.66, 10 PRICE PENDING lines.
- Round 2 fixes: front end, add alternate from the schedule title, automatic EXCEPTION lines, opening wording. 26 new tests; no new failures (tests/bms 1,874 pass; tests/ 2,062 pass).
- Waiting on Siddhant's review. No rerun until then.
- New HarkPro flow (built beside the app, app untouched): doctrine/ (Master Template as lines.json: 39 families, 438 lines; rulings.md R1-R18; conflicts.md C1-C36), harkpro/ coverage gate, 4-tab Evidence, run-to-run diff, CLI. On Job 2a v2 the gate fails as it should: 4 of the 5 known misses are flagged (the 5th, the radiator interlock, is printed), plus the EF thermostat, the leak and float ruling breaks, and a thermostat count gap. Independent QC critic agent in progress.
- Independent QC critic (harkpro/qc, qc_prompts/): reads the evidence log next to the scope; critic → writer → resolve rounds until no must-fix is open; the rest become estimator questions. Job 2a proof: 19 threads, 3 rounds, 15 fixed, 4 estimator questions; all 8 known misses raised. Not blind (the rulings encode these cases), so a blind test on Job 3 is next. Gap: schedule notes sit in the ledger only as ids, not text.
