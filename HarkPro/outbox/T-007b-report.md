# T-007b report

1. Task T-007b, branch hark/T-007b, base origin/lead/wave2 658eb0a. Commits: 184f8d5 (code and tests) plus this report.
2. Changed:
   - src/bms/takeoff.py: QUESTION and count_question name the family ("How many Air Handling Units (AHU)? ..."); `_split_by_sheet`; `admit(breakdown=)` sets aside each dropped placement number by sheet, one SetAside per reason, parts adding up; recount passes `admitted=pages`.
   - src/bms/plan_read.py: Reader keeps each counts line's sheet-by-sheet text (`placed_by`), passes the family name (from its family fact) and the breakdown.
   - src/estimator/reading/inventory.py: `placements(..., admitted=)` (one optional parameter): an admitted page skips the demolition title check. Other calls unchanged.
   - src/bms/model.py: "count by unit register" added at the end of SetAsideReason; SetAside.reason doc.
   - src/bms/plan.py: `_parts_hold` uses the new reason; plan_job docstring.
   - src/bms/render.py: `_count_note` prints sheets then ": N set aside, M counted"; comment on reasons with no '*' line.
   - Spec: SetAsideReason row, Task 2.2 paragraph, Task 2.3 paragraph.
3. Tests: pins changed in test_takeoff.py, test_t007_review.py (xfail S2 removed), test_t007_set_aside.py, test_contracts.py. New: test_t007b_* in test_takeoff.py (star line, mixed reasons add up, no-sheets keeps old reason, admitted demolition-titled sheet, reason value) and a pump test in test_t007_review.py.
   Acceptance on fixture: AHU question as specified; set-asides "demolition sheet" 5 and "part plan of one area" 16; printed 5; AHU 5, EF 5, ERU 1, FCU 55.
   - `pytest tests/bms -q -n 4 -m "not slow"`: 7 failed, 2953 passed, 2 skipped, 4 xfailed. The 7 are the known environment ones (5 test_ai chat, test_review_final3 resource code, test_status_review normal-exit).
   - `pytest tests -q -n 2 -m "not slow"`: 11 failed, 5288 passed, 10 skipped, 4 xfailed. The 11 are the known 9 plus 2 flaky (test_revert_audit tools-change, utf8-bom); none touches this branch.
4. Not done / deviations: zero failures was not reachable; the known environment baseline remains (not re-run on a clean base this time). The plan doc (docs/.../2026-10-11-takeoff-pass-plan.md) still shows the old question form: not named by the task. Same-sheet reasons: sheets the register counts are "part plan of one area" if all one area, else "same unit labelled again" (my reading). Sheets not listed in the register, or numbers not adding up, fall back to the single old reason.
5. Questions: none.
