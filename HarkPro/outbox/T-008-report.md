# T-008 report

1. Task T-008, branch hark/T-008, base origin/rebuild 52fd0ce (has the T-008 base 0ff732c). Commits: 00f5cdf (task 2), 583ff9f (tasks 1 and 3), plus a third with the two pin changes and this report.
2. Changed:
   - src/bms/render.py: `_header_families` also drops valve families when other families stay (valve-only block keeps its header); `short_points` now returns a list of lines (sentence and "; " split, then ", because" for points over 150, then first ": "); new `lower_after_because`; `_reason` lower-cases a plain word after "because"; `_notes` flattens the lines.
   - src/bms/labor.py: `_CLAUSES` also splits at "then"; "nights, weekends" added to `_OFF_HOURS`; `labor_conditions(overview, ledger=None, notes=())` reads overview rows, then ledger facts (any kind and state, quote), then key notes (controls or not); one condition of each kind.
   - assets/reading_lists/scope_review.json: last `ruled_out_words` entry is the lead's pattern `(?<!\bif )\bno\s+[a-z](?:(?!\bthen\b)[^.;]){0,60}?\bshall\s+be\b`.
   - src/bms/run.py: only the `labor_conditions` call (passes `ledger` and `getattr(reading, "notes", ())`).
3. Choices left to me:
   - Source text: fact -> `where_short(ledger.sources[fact.source_id])` ("the documents" when missing); key note -> "Sheet <sheet>", else "<document file name> page <n>".
   - After "because": a capital then lower-case letters is lower-cased ("The", "Plan"). A tag with a digit or hyphen (AHU-1, M-401) and an acronym are kept. A short list of manufacturer/product names (Niagara, Tridium, Honeywell, Johnson, Siemens, Trane, Carrier, Daikin, Taco, ...) is kept as written; any other capitalised plain word is lower-cased.
   - A split at ", because" puts the lower-cased word at the start of the next line; the ": " split keeps the colon on the first part.
4. Pins changed on purpose (expected result only):
   - test_t005c_proposal.py: test_a_long_clarification_prints_as_short_points (one "*" Item per point, no "- "), test_an_abbreviation_does_not_split_a_point (short_points is a list), test_a_red_line_and_short_points_print_in_the_document (a paragraph per point, no line break).
   - test_review_t005c.py: test_short_points_keep_every_word (list of "*" lines).
   - test_render.py::test_a_long_clarification_prints_whole: long note now prints "*Confirm quantity:" and "*<rest>" (the ": " split).
   - test_takeoff.py::test_takeoff_end_to_end: no "Control Valve" header; the block after AHU is not a joined valve header.
5. Tests: new tests/bms/test_t008_labor.py (15), tests/bms/test_t008_render.py (8), two in tests/test_scope_review.py (the FOUND test fails before the change; the ban test stays RULED_OUT).
   - tests/bms -n 2 not slow: 9 failed, 2987 passed. Failures: 5 test_ai chat, test_review_final3 resource code, test_status_review normal-exit, plus test_render long-clarification and test_takeoff end-to-end, which were the two pins above; both pass after the pin changes (111 passed on those files).
   - tests -n 2 not slow: 13 failed, 5324 passed. The 13 are the 9 known (5 chat, py pin, Windows file lock, resource code, normal-exit, one more flaky) plus 2 revert_audit flaky (utf8-bom, class test) plus the 2 fixed pins. After the pin fix the targeted re-run of revert_audit, takeoff, render and the new tests gave 1 failed (test_a_new_test_inside_a_class_is_audited, load-flaky), 197 passed.
   - Zero failures was not reachable. Not re-run on a clean base this time.
6. Not done: nothing skipped. Task 3(a) (red "Qty (##)") is not in this task.
7. Questions for the estimator: none.
