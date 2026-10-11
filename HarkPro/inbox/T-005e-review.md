# T-005e review (reviewer of record, 2026-10-11)

Branch `hark/T-005e`, reviewed at **b1b5045**. I started at 1df101c. b1b5045 changes only
`HarkPro/outbox/T-005e-report.md` (the note on the full-suite result). Base `0e78113` (the merge-base with
`origin/lead/wave2`). Commits: `1df101c` (code) and `b1b5045` (report). Diff: 13 files, +1042 / -51. New files:
`assets/gem_order.json`, `src/bms/order.py`, `src/bms/labor.py` and the test file. Edited: `render.py`, `run.py`,
`scope.py`, `proposal/write.py`, `price_sheet/rows.py`, `price_sheet/write.py` and two tests.

## Tests (at b1b5045, from the review worktree, PYTHONPATH=src)
- The touched files (`test_t005e_format_order_labor`, `test_render`, `test_front_end_name`): **160 passed**. The result
  was also 160 at 1df101c.
- `tests/bms -n 10 -m "not slow"`: **2532 passed**, 0 failed.
- Full `tests -n 10 -m "not slow"`: **4 failed, 4849 passed**. All 4 failures are my new reviewer tests (see below).
  No test of the branch or of the older app fails.
- Reviewer tests, `D:\EA-rv-t005e\tests\bms\test_review_t005e.py` (uncommitted): 6 tests, **2 pass, 4 fail**.

## Verdict
**Do not merge as is.** The red-text path and the off-hours and prevailing-wage work are sound. But the order of
points turns the source rule upside down: the GEM position wins over the Master Template entry's own order.

## Findings

### Must fix
1. **The GEM position overrides the Master Template entry's order.** `src/bms/render.py:618-623` sorts by
   `(gem_position, shape slot order)`. GEM v4 ~396-402 makes the Master Template entry the frame ("Write its lines, in
   its order"). The standard order applies only when there is no entry, and it places any line you add.
   `playbook/rules.md:599` says the same ("Lines print in their shape's slot order"). The Playbook wins over code, so
   the branch now contradicts it. The Master Template AHU entry prints the fan signals, then the switches, then the
   filter and AFMS lines, then the dampers, and `shapes.json` follows it. The branch prints the Freezestat and the
   damper before the supply fan start/stop. My test `test_master_template_entry_order_wins_over_the_standard_order`
   fails: the order it gets is `Freezestat, Damper, Start/Stop`. The branch's own
   `test_an_air_handler_prints_in_the_gem_order_not_the_writers` pins the wrong order. The Exhaust Fan entry has the
   same problem: the template prints "Interlock with Associated ... Unit Operation" first, and the branch moves the
   interlock to position 18 (the author's question 1). Fix: use the shape slot order for the template's own slots. Use
   the GEM position only for the catch-all slots (`other_*`, `fire_alarm`) and for blocks with no shape. That is also
   the real cause the task named (the catch-all slots print after the valves).
2. **`run.py` is edited** (`src/bms/run.py:68,756`). CLAUDE.md hard rule 4 says only the lead changes `run.py`. The hunk
   is small and correct (`catalogue.overview` exists, `estimator/catalogue/job.py:29`). The lead must take it in or
   write it again. No test drives this wiring at the run level.

### Should fix
3. **Some lines get the wrong GEM slot from `assets/gem_order.json`** (the first match wins):
   - "Furnish ... Valve Position Feedback" gets 16 (line 40, `\bvalves?\b`). GEM item 10 names valve position
     feedback. My test fails (16, expected 10).
   - Every "Furnish and Wire" device gets 16 (line 41). So a Furnish and Wire leak detector, current switch, sensor or
     damper actuator prints after the valves. My test fails (16, expected 4).
   - "Furnish Heat Pump Start/Stop" gets 9 (primary equipment), not 8. "Relay Panel" gets 1.
4. **Positions 19 and 20 do not follow GEM v4.** The asset cites GEM **v3.2** (its `about`, line 2). It puts "plain
   work statements" at 19, before the integration lines at 20. GEM v4 puts integration at 19 (last in the scope) and
   Miscellaneous Responsibilities at 20, as a separate section after the integration lines. The branch follows
   `rules.md:604-605`, and the Playbook wins, so this is a question for the estimator, not a code bug. The asset must
   cite v4.
5. **The off-hours check does not see negation.** `src/bms/labor.py:33` matches "overtime" and "outside normal working
   hours" in any sentence. So "No overtime work is permitted; work outside normal working hours is not allowed"
   prints a red "Off-Hours Labor ... Included" line and removes the exclusion. My test fails. The red colour limits
   the harm, but the line is on the client copy.
6. **The sub-headings contradict the addendum.** `render.py:783` adds an unnumbered block ("Chilled Water System",
   "Hot Water System", "VRF System" or "Kitchen Exhaust Ventilation") over stacked headers. The addendum says "no
   sub-headings". The Master Template does print these group lines, so the lead must rule. The change is one hunk, so
   it is easy to keep or to drop.
7. **The existing-BMS front end is not complete against the template** (`existing_lines` in `assets/gem_order.json`).
   It has no "Seamlessly Tie in to the Existing <BMS>" line and no warranty line (template ~77 and ~83, "mentioned in
   specs"). The new-system variant adds no house lines, but the template marks 3-D Graphics and Training "Default"
   (~58-61).
8. **The labor conditions are not in the Evidence Package or `Review.html`.** `with_labor` runs after `review_page`
   (`run.py:756`). The author's report says so.

### Note
9. Playbook files: **0 lines changed** (`git diff --stat` on `playbook/` is empty). These contract files are not
   changed: `model.py`, `playbook.py`, `__main__.py`, the fixtures and `test_contracts.py`. The `render()` signature is
   not changed. `scope.Job.labor_conditions` and `Run.red` are new fields with defaults, so nothing old breaks.
10. I found no real-job wording or counts in the code, tests or assets (I scanned the added lines for job numbers and
    names).
11. Lines with no evidence: only the three template front-end house lines (`render.py:827-840`). Hard rule 3 allows
    them. The labor lines cite the place in the overview row.
12. `proposal/write.py:451` calls `next(...)` with no default. It raises `StopIteration` if the template has no
    Clarifications heading. The risk is low because the template is fixed.
13. `with_labor` calls `check_fit` and raises `RenderError` when the extra block makes the price sheet overflow. That
    stops the run, which is acceptable, but no test covers it.

## Order check against GEM v4 lines 408-432
The names of positions 1-18 in `positions` match GEM items 1-18. Positions 19 and 20 differ (finding 4). The rules
list gives the wrong slot in the three cases of finding 3. The rule that a Master Template entry's own order wins is
**not kept** (finding 1).

## Red-text path
`scope.Run.red` (`scope.py:24`) -> `_apply` in `proposal/write.py` sets `run.font.color.rgb` from
`layout.EXISTING_NAME_COLOUR` ("FF0000"). The items of the labor block carry `Run(red=True)` (`labor_block` in
`labor.py`). `_make_red` makes the new clarifications red. Price sheet: `Row.red` in `rows.py` comes from the runs.
`_fill` in `write.py` makes column D red and writes the flag `LABOR PREMIUM - ESTIMATOR TO PRICE` in column H, with no
quantity. `_fill_summary` writes B34. The branch's tests pin each step
(`test_the_proposal_carries_off_hours_and_wage_in_red...` and
`test_the_price_sheet_carries_the_lines_in_red_with_a_flag`). The app does not price the premium. That is by design:
the estimator prices it.

## Overlap
- `git merge-tree origin/hark/T-005c origin/hark/T-005e` gives **conflicts**:
  - `src/bms/render.py`, lines of the merged file: 158-165 (the `render` docstring); 891-916 (`_front_end_flags`
    against `_existing_template_lines`); 926-949 (the body of `_front_end`).
  - `tests/bms/test_render.py`, lines 567-576 (the expected items in
    `test_extend_existing_front_end_and_deduct_alternate`).
  - `scope.py` (`Run.red`, the same line in both) and `proposal/write.py` (`_apply`) merge cleanly.
  - To resolve: keep both front-end lists. First T-005e's merged lines, then the notes, then T-005c's red flags. The
    test must expect the template lines, the writer's line, the note and `AME_ONLY_FLAG`.
- `git merge-tree origin/lead/wave2 origin/hark/T-005e` (wave2 at 28a966c): **no conflicts**.

## Against the afternoon rulings
1. **'*' notes, one short line per item.** The branch does not change `_notes`. The base still joins all the items of
   one kind into one line with "; " (`rules.md:242-248`). That is against the ruling, but it is outside this diff. Red
   for the estimator: the branch adds it only to the labor lines.
2. **The quantity in the line, as "Qty (#) <device>".** Not done. Lines still print "(Qty. N Total)" after the device,
   and the separate quantity note stays. Nothing in the branch moves toward this ruling.
3. **Tech hours never in the proposal.** Pass. The branch adds no tech-hour line. Tech hours stay on the price-sheet
   row of the first Qty header (`tech_hours=... if i == 0` in `render.py`). The sub-heading block has none.
4. **A "Demolition Scope" block last.** There is no such block and no slot for it. What exists: plain statements in
   each block's `other_wiring` slot (`rules.md:273-282`, GEM position 19 in the branch); the "Existing Fan Coil Unit
   (relocated)" shape with its `demo_wiring` slot; and the add-a-block-last pattern of `labor.with_labor`, which a
   demolition block could use again.
5. **Pumps.** The branch does not change where pumps go. The plant shapes stack the pump families (`Chilled Water
   System`, `Hot Water System`, `Condenser Water System`), and the branch adds the plant sub-heading when they stack.
   There is no shape for a remote pump on its own (only the Fuel Oil Pump System). The branch does not have the rule
   that the documents decide.
6. **Front-end house lines follow the template's front-end section.** Partly. The order follows it
   (`front_end.order`). The extension variant adds 3 of the template's 5 items (no tie-in line, no warranty). The new
   variant adds none of its "Default" lines (graphics, training). See finding 7.
