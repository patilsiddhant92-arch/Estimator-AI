# T-005e report: Master Template format, GEM order of points, off-hours and prevailing wage

1. **Task** T-005e. **Branch** `hark/T-005e`. **Base** `origin/lead/wave2` (0e78113). **Last commit**: the commit
   that carries this report (see `git log hark/T-005e`).

## 2. What changed

### New files
- `assets/gem_order.json`: the data for the order of points and the front-end format (no words in code):
  - `rules`: the GEM v3.2 "SOW ORDER - STANDARD TEMPLATE" positions 1-20, as `playbook/rules.md` "Standard order"
    words them (its wiring runs and plain work statements print before the integration lines).
  - `front_end.order`: the Master Template's front-end order.
  - `front_end.existing_lines`: the Master Template's "Extension of Existing" lines.
  - `sub_headings`: the Master Template's unnumbered group headings (Chilled Water System, Hot Water System,
    VRF System, Kitchen Exhaust Ventilation).
- `src/bms/order.py`: reads that asset. It has `position(text, verb, slot, slot_kind)`, `front_end_rank`,
  `front_end_entry`, `existing_lines` and `sub_heading`.
- `src/bms/labor.py`: off-hours work and prevailing wage.
  - `labor_conditions(overview)` reads the Spec overview's "Project conditions that change the price" rows and the
    standard lines the job speaks to. It keeps only quotes that really call for off-hours work (the words, or a time
    range that starts in the evening) or for prevailing wage. Each condition gets its source as "Spec Section xx xx xx",
    "Sheet X", or document and page.
  - `labor_block` builds the red "Labor Conditions" group block.
  - `with_labor(draft, conditions)` adds that block last in the base bid and sets `scope.labor_conditions`.
- `tests/bms/test_t005e_format_order_labor.py`: 41 tests (listed in part 3).

### Shared functions touched (for the merge)
- `src/bms/render.py`
  - `_device_lines` (about l.574-660), rewritten in place.
    - It works out every line's text first. Then it sorts by **(GEM position, the shape's slot order, the writer's
      order)**. The front end, which has no shape and no system, sorts by the Master Template's front-end rank instead.
    - Sub-lines still sit directly under their parent, so the rep line stays under its Map line.
    - The text, depth and priced rules are unchanged.
  - `_system_blocks` (l.783-800): when a grouped shape stacks more than one Qty header, it puts the Master Template's
    sub-heading in front as an unnumbered block (`numbered=False`). The Qty headers are then `joined`. The tech hours
    stay on the first Qty header.
  - New `_existing_template_lines` (l.827).
  - `_front_end` (l.841-875): one merged list in the Master Template's front-end order.
    - For an existing BMS (`extend-existing`), the template's three lines are added: Network Level Control Panel,
      3-D Graphics to match existing, Training. A line is added only when the writer did not already write one of the
      same kind. The writer's line, which cites the job, always stands.
    - Nothing is added when there is no front-end information (no devices and no reading lines). That keeps it apart
      from T-005c's "No front end information found".
    - Nothing is added when the writer wrote none and gave a `no_scope_reason`.
    - Added lines have quantity 1, are priced, and are traced with `device_id=None`.
  - The import of `bms.order` (l.31). The `render` docstring.
  - `render`'s signature is **unchanged**: it is fixed by the interface spec and `test_contracts`.
- `src/estimator/scope.py` (not a named file; additive only):
  - `Run.red: bool = False`. T-005c's worktree has the same line, word for word, so the hunk should merge cleanly.
  - New `LaborCondition(kind, text, source, quote)`.
  - `Job.labor_conditions: tuple[LaborCondition, ...] = ()`.
- `src/estimator/proposal/write.py`
  - `_apply`: a `Run.red` run prints red. I copied T-005c's hunk exactly to avoid a conflict.
  - New `_write_labor_conditions`, called from `write_proposal`. When off-hours work applies:
    - the template's "All labor will be performed during normal business working hours..." clarification becomes a
      red "All labor for the off-hours work the documents call for is included (As per <source>)";
    - the "All off-hours or overtime labor." exclusion is taken out. The red scope line and the red clarification carry
      it, so it is never excluded silently.
  - When prevailing wage applies, a red "All labor is priced at prevailing wage rates, as the documents require
    (As per <source>)" follows that clarification.
  - With no condition, nothing changes.
- `src/estimator/price_sheet/rows.py`: `Row.red` is set from the item's runs in `_item_row`.
- `src/estimator/price_sheet/write.py`
  - `_fill`: a red row's scope cell is red, and a labor-condition row is flagged `LABOR PREMIUM - ESTIMATOR TO PRICE`
    in column H. It has no quantity, so it is not priced as material.
  - `_fill_summary`: B34 says which condition the documents call for and where.
- `src/bms/run.py` (not a named file; 2 lines plus 1 import): after `render`, the run calls
  `draft = with_labor(draft, labor_conditions(getattr(catalogue, "overview", None)))`.
  - It is a separate hunk; drop it if you want to wire it yourself.
  - T-005d also edits run.py, but in other places.
- Tests updated for the new, intended order. Each change is commented "T-005e" in the test:
  - `tests/bms/test_render.py`:
    - rooftop golden: Install and Wire now prints before the integration trio;
    - exhaust fan golden and two others: the damper now prints before the fan start/stop;
    - RTU quantities and depths;
    - VRF: now has the "VRF System" sub-heading;
    - existing front end: now prints the 3 template lines;
    - the shapeless test now uses two sensors, so device order still decides.
  - `tests/bms/test_front_end_name.py`: the writer's line now comes after the template lines.

### Format items checked against the Master Template, with no code change
- **Heading form** "Qty (#) <System> <tags>": already what the shapes print.
- **The "*"/"**" lines**: already after the lines, in the Playbook's fixed order ("Joining into the one
  clarification"). I left this alone: the Playbook rule wins.
- **The tech hours line**: the Master Template's "**tech hour" lines are estimator notes. The Playbook says "Tech hours
  never print", so they stay on the price sheet, on the block header row.

## 3. Tests

New tests, in `tests/bms/test_t005e_format_order_labor.py`:
- `test_each_line_takes_its_gem_position` (22 cases)
- `test_slot_kinds_place_interlocks_wiring_and_integration`
- `test_an_air_handler_prints_in_the_gem_order_not_the_writers` (real Playbook)
- `test_a_shapeless_block_follows_the_gem_order_too`
- `test_the_rep_line_stays_under_its_map_line_and_the_trio_prints_last`
- `test_a_grouped_system_gets_the_master_template_sub_heading`
- `test_a_single_family_block_gets_no_sub_heading`
- `test_an_existing_bms_front_end_prints_the_master_template_lines_in_its_order`
- `test_an_existing_front_end_the_documents_give_to_others_gets_no_template_line`
- `test_an_existing_front_end_with_nothing_in_the_documents_gets_no_template_line`
- `test_an_existing_front_end_the_reading_found_but_no_line_written_gets_the_template_lines`
- `test_a_new_system_front_end_is_ordered_but_never_filled`
- `test_the_quote_decides_off_hours`
- `test_labor_conditions_from_the_spec_overview`
- `test_a_not_found_row_is_not_a_condition`
- `test_the_labor_block_is_red_and_unpriced`
- `test_with_labor_adds_the_block_last_in_the_base_bid`
- `test_the_proposal_carries_off_hours_and_wage_in_red_and_never_excludes_them`
- `test_without_conditions_the_template_boilerplate_stays`
- `test_the_price_sheet_carries_the_lines_in_red_with_a_flag`

Full suite (`-n 2 -p no:cacheprovider`, in two chunks; see the final line in the commit message):
- **Chunk 1** (tests/bms plus the writer and price-sheet test files): 7 failed, 2716 passed, 2 skipped. All 7 are
  baseline: the 5 test_ai chat tests, test_review_final3 resource code, and test_status_review normal-exit.
- **Chunk 2** (the rest): see the commit message.

## 4. What I did not do, and why
- **Prompts** (`src/bms/prompts/`): not edited. T-005d is rewriting all four prompts, and the order is now enforced in
  code (render sorts every block). The front-end prompt's "Order the lines as the Master Template orders its front end"
  already matches. If you want a hint in `write_system.md` anyway: "Lines print in the GEM order of points (the
  renderer sorts them); you need not order them."
- **The Evidence Package**: the labor conditions are not in it yet. Their quote is in `LaborCondition.quote` and on
  `draft.lines` under the key "labor".
- **Off-hours detection** reads the Spec overview's one deciding sentence per row. When a row's deciding sentence is
  a "normal hours" sentence and the off-hours sentence is elsewhere, the condition is missed. Widening it means
  scanning every sentence in `estimator.catalogue.overview`, which is outside my files.
- **The price of the premium**: not computed. The row is red and flagged for the estimator, and the Summary says so.
  The workup template has no labor-multiplier input I can type into without touching formulas.
- **Gas Detection, Misc Monitoring, Condenser Water**: they get no sub-heading. Their Master Template headings are
  job-specific or single-header.

## 5. Proposed Playbook changes (`playbook/rules.md`)
- **"Standard order"**: replace "Lines print in their shape's slot order. Without a shape the order is: ..." with
  "Lines print in the standard order below (GEM v3.2 order of points); lines of one place in that order keep their
  shape's slot order (the Master Template's), then the writer's order. A sub-line stays under its parent."
  Also say where an interlock or tie-in line goes. I put them with "other Wire" (position 18), because the GEM does
  not list them. The Master Template's Exhaust Fan block prints "Interlock with Associated ... Unit Operation" first.
- **"Front end lines cite the specification"**: add "For an extension of an existing BMS, the Master Template's
  'Extension of Existing' lines (Furnish Network Level Control Panel, Furnish 3-D Graphics to match existing, Furnish
  Necessary Training on New Controls) print unless the documents give the front end to others; a line the documents
  speak to cites them." This conflicts with the 2026-10-10 ruling "the Master Template never makes a line exist", so
  the estimator should confirm it.
- **New rule "Off-hours work and prevailing wage"**: "When the documents call for off-hours work or prevailing wage,
  the proposal prints a red 'Labor Conditions' line citing the source and a red clarification. The 'normal business
  working hours' clarification and the 'All off-hours or overtime labor' exclusion are not printed. The price sheet
  flags the row for the labor premium."
- **New rule "Sub-headings"**: the Master Template's unnumbered group heading over a grouped system's stacked headers
  (Chilled Water System, Hot Water System, VRF System, Kitchen Exhaust Ventilation).

## 6. Questions
1. **Interlock lines**: GEM position 18 (after Install and Wire), or first, as the Master Template's Exhaust Fan
   block shows them? It is one entry in `assets/gem_order.json`.
2. **Existing-BMS front end**: should "Furnish PC Workstation" also print by default? `assets/front_end.json`'s
   extend-existing variant keeps it unless it is the owner's, but the Master Template's extension lists only the
   three lines. I print only the three.
3. **Removing the off-hours exclusion**: is it right to take it out of the boilerplate, or would you rather keep it in
   red with a strike-through?
4. **Merge with T-005c**: we both touched `_front_end`, `_items`/`_apply` and `scope.Run.red`. My `_front_end` builds
   one merged list. T-005c's flags (`_front_end_flags`) can be appended after my `traced`/`lines`, as their notes are.
