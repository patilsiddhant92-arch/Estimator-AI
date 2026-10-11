# T-001 report

1. Task T-001, branch hark/T-001, base origin/rebuild at 8ccd0b3 (ce07960 is not on GitHub; used rebuild as it is). Last commit: see branch tip.

2. Changed
- src/bms/coverage.py (new): `coverage(job, ledger, dossier=None) -> list[Finding]`. Pure, report only; adds nothing to the job.
- tests/bms/test_coverage.py (new).

How it decides: scope kinds are family, unit, device, sequence_match, front_end. Left out: count (the family fact covers it), location (where, not what), provider and link (who/how), group (planning detail), note (free text, no subject to cite). A fact is cited when a job ref has the same source id and a matching quote (either contains the other), or its subject (for a unit, also its value) appears as a whole word in the job's text (system and family names, tags, line names, clarifications, exceptions, questions, served units, front end). A front_end fact is cited when the front end has a line or clarification. Each uncited fact gives one Finding: rule coverage, severity check, system_key "", device_id None; what names the fact id, kind, subject, value, place (sheet/section/page) and quote; fix is the task's wording.

Where to call: in run.py after the last write/revise step, once per run on the final Job and the ledger (before the review page is built), and again after each estimator decision is applied. Review page: one "Not cited" group of check items, each showing the fact's place and quote with actions: add a question, add an exception, or mark not scope (a decision that silences that fact id).

3. Tests: test_coverage.py (8): cited fact gives none; finding shape; question/exception/clarification cite; same source+quote ref; unit by tag; non-scope kinds ignored; front end; job unchanged. Full suite: 10 failed, 3761 passed, 10 skipped. The 10 are all in the baseline 12: 5 test_ai chat, test_status_review normal-exit (flaky), test_review_final3 resource code, test_assets python pin, test_main open folder, test_revert_audit_review class test. The same fail on unchanged rebuild.

4. Not done: no wiring in run.py/review; model.py, playbook, interface spec untouched. Subject matching is word-based, so a short prefix may match unrelated text (a miss, never a false alarm). Count differences are not checked.

5. Questions: none. Should "not scope" be a stored decision on a fact id? (Needs the lead's model change.)
