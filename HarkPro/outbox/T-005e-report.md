# T-005e report: Master Template format, GEM order of points, off-hours and prevailing wage

1. **Task** T-005e. **Branch** `hark/T-005e`. **Base** `origin/lead/wave2` (0e78113). **Last commit**: the commit
   that carries this report, on top of 1df101c (the code). See `git log hark/T-005e`.

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

Full suite (`-n 2 -p no:cacheprovider`, in two chunks). **Nothing fails outside the 12 baseline tests.**
- **Chunk 1** (tests/bms plus test_price_rows, test_write_price_sheet, test_write_scope, test_write_cover,
  test_write_systems, test_round_trip, test_sent, test_price_check, test_price_book_revised and test_next_batch):
  7 failed, 2716 passed, 2 skipped. All 7 are baseline: the 5 test_ai chat tests, test_review_final3 resource code,
  and test_status_review normal-exit.
- **Chunk 2** (every other tests/*.py): 2 failed, 2129 passed, 8 skipped. Both are baseline: test_assets project
  python and test_main open output folder.
- The revert_audit tests passed in this run.
- After the chunks I made two small edits: T-005c's exact `_apply` hunk, and the front-end "no information" guard. I
  re-ran test_t005e_format_order_labor, test_render and test_front_end_name after them: 160 passed.

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

---

## Follow-up for the T-005e addendum and NOTES 2026-10-11 (with the fixes of T-005e-review.md / T-005e-fixes.md and the rulings of 2026-10-11 afternoon)

**Branch** `hark/T-005e`, on top of b1b5045. Commits: `30c1f32` (addendum work), a merge of `origin/hark/T-005c`
(tip 21d5303, which contains f453c8c; `origin/lead/wave2` did not yet show the T-005c merge when I started), and
one commit with the review fixes, the afternoon rulings and this report. Sources read: `HarkPro/inbox/T-005e-addendum.md`,
`NOTES-2026-10-11.md` (incl. bfeafb2, items 14-19), `README.md`, `T-005e-review.md`, `T-005e-fixes.md`,
`T-005e-review-tests.py`, `assets/gem/BMS_DDC_GEM_v4.txt`, `Brain/Master Template.docx`.

### A. The fix list, item by item

**Must fix 1 - the Master Template entry's own order wins over the GEM position.** Done.
`src/bms/render.py` `_device_lines` (l.590-722, the key is `rank`, l.667): a block with a shape prints its template
slots in the shape's `line_order` (GEM v4 ~396-402, `rules.md` ~599). The GEM position is used only for the
catch-all slots (`other_device`, `other_point`, `fire_alarm`, `other_valve`, `other_install_and_wire`, `other_wire`,
`other_interlock`, `other_wiring`), for a slot the shape lacks, and for blocks with no shape. Such a line goes after
the template's last line of the same GEM position; else after the first template line of a lower position and
before the next template line of a higher one (`src/bms/order.py` `is_catch_all` l.106, `place` l.111). So the AHU
prints Start/Stop, Freezestat, Damper (the template's order), and the Exhaust Fan keeps "Interlock with Associated
... Unit Operation" first. The integration group stays last in every block (GEM v4 "never changed"; VFD group first,
`integration_rank` l.126). The branch's own AHU test now pins the template order
(`test_an_air_handler_prints_in_the_master_template_order_not_the_writers`).

**Must fix 2 - the reviewer's 6 tests.** Added as `tests/bms/test_review_t005e.py`, unchanged (a copy of
`HarkPro/inbox/T-005e-review-tests.py`). All 6 pass (output in part E).

**Should fix - valve position feedback is GEM 10.** Done in `assets/gem_order.json`: the position-feedback rule
(now also `\bvalve\s+position\b`) comes before the valve rule, and the valve rule has `not_words` for position /
end switch.

**Should fix - classify "Furnish and Wire" devices by what they are.** Done: the catch-all "Furnish and Wire -> 16"
rule is now the last rule, so a Furnish and Wire leak detector is 4, a current switch 5, a damper actuator 7; an
otherwise unnamed Furnish and Wire device (a humidifier) still goes with the valves. Also from the review: "Furnish
Heat Pump Start/Stop" is 8 (a start/stop rule before the primary-equipment rule), "Relay Panel" is 6 (the controller
rule skips relays). Tests: `test_lines_get_their_gem_category_not_their_verb` (7 cases).

**Should fix - an overtime ban is not off-hours work.** Done: `src/bms/labor.py` `calls_for_off_hours` (l.66) reads
clause by clause (split on `. ; :` and on but/however/except) and skips a clause with a negation (`_NEGATION`, l.61:
no, not, never, without, prohibited, shall not ...). Tests: the reviewer's `test_a_ban_on_overtime_is_not_off_hours_work`
and `test_an_overtime_ban_is_no_off_hours_work_but_a_call_beside_it_is`.

**Should fix - remove the sub-headings inside blocks.** Done (the addendum asked the same): no unnumbered
"Chilled Water System" / "Hot Water System" / "VRF System" / "Kitchen Exhaust Ventilation" block any more;
`sub_headings` is gone from the asset and `sub_heading` from `order.py`.

**Should fix - the labor lines in the Evidence Package and Review.html.** Done through the findings, which both
already show: `labor_findings(conditions)` (`labor.py` l.216) gives one "check" finding per condition, for the whole
job (system key "", no device), rule "Off-hours work and prevailing wage", with the quote, where it is and the red
line's text. The run adds them to `all_findings` before `review_page` (so the "Front end and whole job" card shows
them) and the same tuple goes to `write_evidence` (Findings tab). A decision on that card changes nothing
(`review._apply_one` ignores a whole-job decision with no device), and the finding's fix text says so.

**run.py - every line changed, and why** (`src/bms/run.py`, diff against 0e78113):
- l.68: `from bms.labor import labor_conditions, labor_findings, with_labor, with_warranty`.
- l.752-755: work out the labor conditions once, before the review page, and add their findings to `all_findings`
  (review finding 8).
- l.759: `draft = with_labor(draft, conditions)` after `render` (the red lines in the proposal and the price sheet).
- l.760-761: `draft = with_warranty(draft, catalogue.overview)` (the Master Template's warranty lines, addendum).
Nothing else in run.py changed. No test drives this wiring at the run level (as the review says); the functions are
tested on their own.

**Afternoon rulings (NOTES items 14-19), where they touch T-005e:**
- **14 - one short '*' line per item.** Done: `render.py` `_notes` (l.842) prints each item in its kind's form on its
  own line (confirm, assumed, per drawings, client notes, in that order), a repeat once, a long item as T-005c's
  `short_points`. This replaces the "one '*' note per block" I had built from GEM ~548 and NOTES rule 7 (dropped).
- **15 - quantities in the line, "Qty (#) <device>", no separate quantity note.** Done:
  - a line whose quantity is not the block's count (or is unknown) prints "Furnish and Install Qty (4) Outside Air
    Damper Actuator" / "Qty (##) ..." (`LINE_QTY`, l.806; in `_device_lines`);
  - the other counts the documents give (ruling L2/D6) print in the line itself: a device's after its name
    "(4 per M-601; 2 per M-401)" (`_qty_notes` l.820), a family's after its header "Qty (2) Rooftop Units RTU-1, 2
    (2 per M-001; 1 per M-101)" (`_header_counts` l.835). The old "*Qty. ..." note (`_count_note`) is removed.
  - the price sheet looks the price up without the "Qty (n)" words (`price_sheet/write.py` l.23, l.90), and a
    "Qty (##)" line is flagged quantity-pending like "(Qty. ##)" was (`price_sheet/rows.py` l.77-78).
- **16 - tech hours never print.** Already right: no tech-hour line; the hours stay on the price-sheet row of the first
  header.
- **17 - Demolition Scope.** Not added (the fixes doc gives it to the lead).
- **18 - pumps.** No planner change here (not in my files). With the sub-headings gone, render adds nothing about
  plant vs remote pumps; the pump minimum (VFD Control) applies in either block.
- **19 - front-end house lines follow the template.** Done: the New front end now prints the template's "Default"
  lines (Furnish 3-D Graphics, Furnish Necessary Training on New Controls, `assets/gem_order.json`
  `front_end.new_lines`, `order.new_lines` l.175) unless the writer wrote one of the same kind; a written line now
  counts for every entry it names ("BMS Server Software and Graphics" covers server and graphics,
  `order.front_end_entries` l.157). The Extension of Existing front end prints panel, graphics, training; the tie-in
  header is printed by the proposal writer from the mode and is now traced in `draft.lines` (kind "header"); the
  warranty lines come from `with_warranty` when the specification states the warranty and its length.

### B. What else changed (file:line)
- `assets/gem_order.json`: GEM v4 positions (19 the integration group, 20 the Miscellaneous Responsibilities: a
  plain statement of `other_wiring` with no verb prints after the integration lines), `catch_all_slots`,
  `integration.first_slots`, `alternatives` (the template's "OR" groups: Fire / Smoke Dampers end switch vs fan
  starter interlock; VAV hot water valve vs electric heat enable vs SCR; VAV power loop vs transformer),
  `minimum_points` (pumps), `valves`, `front_end.new_lines`. The `about` cites GEM v4. Re-indented by `json.dumps`.
- `src/bms/order.py`: `is_catch_all`, `place`, `integration_rank`, `alternatives`/`alternative_word`,
  `minimum_points`, `valve_rules`, `front_end_entries`, `new_lines`; INTEGRATION = 19, MISCELLANEOUS = 20.
- `src/bms/render.py`:
  - `_device_lines` (l.590): order as in A; the "OR" line (`_Printed.marker`, l.717) between two alternatives printed
    next to each other, only the first priced; quantities as in ruling 15.
  - `_gem_devices` (l.753), `_is_valve` (l.747), `_pump_minimums` (l.777): a valve written Furnish and Install prints
    Furnish and Wire (GEM ~228); a valve the unit maker furnishes inside a packaged/integration unit, not installed by
    AME, is left out with a note in `draft.lines` (GEM ~291, ~294); a pump Start/Stop under field control with no
    VFD Control for that pump gets "Furnish <pump> VFD Control", citing the Start/Stop line (GEM ~346-349). Fault and
    speed feedback are never added.
  - `printed_texts` (l.725): no "OR" line and no added line (they are not the writer's); T-005c's `_with_marks`.
  - `_system_blocks` (l.925), `_front_end` (l.1031), `_existing_template_lines` (l.1001), `_items` (l.965: an "OR" line
    is never red), `_traced` (l.983: an "OR" line has no device id).
- `src/bms/labor.py`: negation (l.61-77), `warranty_items` / `with_warranty` (l.176-210), `labor_findings` (l.216).
- `src/estimator/price_sheet/write.py` l.23, l.90; `src/estimator/price_sheet/rows.py` l.77-78 (ruling 15).
- Tests: new `tests/bms/test_review_t005e.py` (the lead's), `tests/bms/test_t005e_addendum.py` (35 tests) and its
  invented fixture `tests/bms/fixtures/t005e_addendum_job.json` (NOTES rule 4: invented names, tags, sheets and
  numbers; the patterns of the 26-0544 findings: catch-all lines after the valves, a pump without VFD Control, a
  valve written Furnish and Install, a factory valve, several '*' notes, other counts in a separate note, the
  existing front end without panel/graphics/training/warranty, FSD alternatives). Updated for the rulings:
  `test_render.py`, `test_render_count_notes.py`, `test_citations_reviews.py`, `test_citations_final_c.py`,
  `test_final_l.py`, `test_final_m.py`, `test_t005e_format_order_labor.py`, `test_front_end_name.py`,
  `test_t005c_proposal.py` (two front-end tests now pick their own line, since the default lines print too). Each
  changed assertion carries a "T-005e" comment naming the ruling.

### C. Conflicts with the earlier v3.2 work, and with the Playbook
1. **Order**: v3.2 sorted every shaped block by GEM position; now the template order stands and only catch-all lines
   are placed by GEM. The v3.2 goldens I had changed (Exhaust Fan, AHU) are back to the template order.
2. **Miscellaneous after the integration lines** (GEM v4) vs `rules.md` "Standard order" (plain work statements before
   the integration lines). I followed GEM v4 as the addendum asks; the Playbook needs the edit (proposal 1). If the
   estimator keeps the Playbook's order, it is one rule in the asset (`slot_kinds: wiring, verbs: ""` -> 18).
3. **Sub-headings**: removed; withdraw the v3.2 proposal "Sub-headings".
4. **'*' notes**: v3.2 left the Playbook's "one line per kind"; the addendum asked one line per block; ruling 14 now
   says one short line per item. Implemented ruling 14. `rules.md` "Joining into the one clarification" and
   wording.json `quantity.others_note` contradict 14 and 15 (proposal 2).
5. **The quantity note**: moved into the lines (ruling 15). This changes ruling L2's "*" note into a bracket on the
   header or line; every count is still named with its place.
6. **The integration group is always last**, even where a shape's `line_order` puts a slot after it (the sample
   Playbook's Rooftop Unit `shipped_loose`, VRF `gateway`).
7. **Merge with T-005c** (resolved here): `render` docstring (both paragraphs kept), `_front_end` (T-005e's merged
   template lines, then the notes, then T-005c's red flags, as the review suggests), `printed_texts`/`_system_blocks`
   (T-005c's `_with_marks` around T-005e's `_device_lines`), `_notes` (T-005c's `short_points` applied per item),
   `test_extend_existing_front_end_and_deduct_alternate` (template lines, writer's line, note, `AME_ONLY_FLAG`).

### D. Not done, and proposals
- **Exclusions only from sequence items (GEM ~564)**: not implemented. I built a writer pass that took out a template
  exclusion the scope contradicts (AFMS, smoke detector wiring, factory mounting, flow/power/gas meters, gas
  detection) and the second "Any demolition work not ... mentioned", then reverted it: `proposal/write.py` is shared
  with the older app, and its tests of the proposals actually sent (`test_end_to_end` "matches what was sent",
  `test_round_trip` 26-0246, `test_write_cover`, `test_write_scope`) show the estimator's sent proposals keep the full
  template list, both demolition lines included. Proposal: (a) a scope-level list of job exclusions in the model and
  the writer, filled by the writer/planner from sequence items; (b) the conflict pairs above as an asset the writer
  reads; (c) the estimator rules whether the boilerplate list stays.
- **Miscellaneous section**: done inside each block (position 20, after the integration lines, before the '*' lines).
  A proposal-level "Miscellaneous Responsibilities" section would need model and writer changes.
- **"OR" lines**: only the FSD and VAV groups. The FSD shape's `line_order` (fan starter interlock before end switch)
  differs from the Master Template (end switch, OR, fan starter): proposal for `shapes.json`. VRF (central controller
  OR integration trio) and EUH (thermostat OR BACnet thermostat, one slot) are not done.
- **A family that prints no header** (a damper family linked under a fan): its other counts print only where a damper
  line carries that count.
- **The added pump VFD Control line** has id `<start/stop id>.vfd`; it is not a Job device, so the Evidence Package's
  scope rows do not list it (its printed text is in `draft.lines`).

**Proposed Playbook changes** (`playbook/rules.md`, `wording.json`; I changed no Playbook file):
1. "Standard order": "A block with a shape prints its slots in the shape's order (its Master Template entry). The
   standard order (GEM v4) places the lines of the catch-all slots and every line of a block with no shape: ...
   other Wire; the integration group, always last within the scope, the VFD group first; then the Miscellaneous
   Responsibilities (the plain statements of other_wiring)."
2. "Joining into the one clarification" -> "One '*' line per item" (ruling 14); `wording.json quantity.others_note`
   and "Quantity detailing" -> "a line's quantity prints as 'Qty (#) <device>'; other counts follow in brackets on
   the line or header" (ruling 15).
3. "Minimum points on AME-run equipment": pumps get VFD Control always (GEM v4) - the Playbook says "when the
   equipment has a VFD" (question 2).
4. "Packaged units": a valve inside the unit is never a line.
5. New rule "Off-hours work and prevailing wage" (as in part 5 above), now with "a sentence that forbids it is no call
   for it".
6. New rules for the other 2026-10-11 rulings with no source rule, as the estimator worded them: demolition (now
   ruling 17, the lead's "Demolition Scope" block) and FUTURE items (T-005c's red "(FUTURE ...)" line).
7. New rule "Alternatives": the Master Template's "OR" line between two alternatives the documents leave open; only
   the first is priced.
8. "Front end lines": the New front end prints the template's Default lines (3-D Graphics, Training); the Extension of
   Existing prints panel, graphics, training; warranty when the specification states its length (ruling 19).

### Questions
1. **Family other counts on the header line** ("Qty (2) Rooftop Units RTU-1, 2 (2 per M-001; 1 per M-101)"): is this
   the reading of ruling 15 you want, or should they stay as a short '*' line?
2. **Pump VFD Control**: GEM v4 "always" vs `rules.md` "when the equipment has a VFD". I follow GEM v4.
3. **A factory valve that AME only wires** ("Wire ... (Furnished by Unit Mfr.)" on a packaged unit): left out (GEM
   ~294 "never a line"); GEM ~3 of the packaged-unit section allows it when the sequence assigns the wiring.
4. **Tech-hour line**: the Master Template prints "**tech hour" last; ruling 16 and the Playbook say never. Kept off.
5. **"Labor Conditions"** is still an unnumbered heading block (not a sub-heading over stacked headers). Keep it, or
   print "Qty (1) Labor Conditions"?
6. **Exclusions**: may the shared writer drop template exclusions the scope contradicts (part D)?

### E. Tests (real output)

Run on 2026-10-11 in the worktree, after the merge of origin/hark/T-005c (21d5303, which carries f453c8c) and every
fix above, with `PYTHONPATH=$PWD/src .venv/bin/python -m pytest <files> -q -n 2 -p no:cacheprovider`, in chunks by
file (the sandbox stops a command after about two minutes). The summary line of each chunk:

**tests/bms** (100 files, 2627 tests) - **2620 passed, 5 failed, 2 skipped**:
- files 1-20: `4 failed, 682 passed, 18 warnings in 78.93s` (the 4: test_ai chat tests)
- files 21-40: `639 passed, 14 warnings in 65.04s`
- files 41-70: `1 failed, 908 passed, 2 skipped, 30 warnings in 102.07s` (test_review_final3 resource code)
- files 71-85: `135 passed, 84 warnings in 101.00s`
- files 86-100: `256 passed, 32 warnings in 98.59s`

The 5 failures are the known sandbox baseline: the test_ai chat tests (4 of the 5 failed in this run; a fifth,
`test_every_cleanup_is_logged_beside_the_cache`, fails in some runs) and `test_review_final3`
`test_a_real_child_failing_with_the_resource_code_is_run_three_times_then_reported`. `test_status_review`
`test_every_normal_exit_writes_the_state_whole_and_status_agrees` (baseline) passed in this run. The lead's six tests
in `tests/bms/test_review_t005e.py` pass (`70 passed` with the other touched files).

**The rest** (`tests --ignore=tests/bms`, 104 files, 2316 tests) - **2304 passed, 4 failed, 8 skipped**:
- files 1-25: `1 failed, 398 passed, 18 warnings in 13.07s` (test_assets `test_running_on_the_project_python`)
- files 26-60: `1 failed, 709 passed, 1 skipped in 9.92s` (test_main `test_the_output_folder_being_a_file_that_is_open_is_plain`)
- files 61-104: `2 failed, 1197 passed, 7 skipped, 4 warnings in 82.02s` (test_revert_audit
  `test_a_tools_change_is_reverted_too`, test_revert_audit_review `test_a_test_file_saved_with_a_utf8_bom_is_audited`)

All 4 are the known baseline. The revert_audit tests are flaky alone too: `test_a_tools_change_is_reverted_too` run
alone three times gave failed, passed, passed; the BOM test passed alone.

**Test files whose expectation changed in this follow-up** (each changed assertion carries a "T-005e" comment):
- Ruling 15 (other counts in brackets on the header or line, "Qty (#) <device>", no "*Qty." note):
  `tests/bms/test_render_count_notes.py` (new helper `headers`: the bracket of each header; the silent-count sweep now
  reads the header brackets), `tests/bms/test_count_added_up.py` (the sum in the header's bracket),
  `tests/bms/test_citations_reviews.py` (the count place on the header; the stale note its own short line, ruling 14),
  `tests/bms/test_citations_final_c.py`, `tests/bms/test_render_rnd14.py`, `tests/bms/test_render_rnd9.py`,
  `tests/test_count_cause_note.py`, `tests/test_final_d_count_causes.py`, `tests/test_review_final2_counts.py`.
- Ruling 15, the line selector only: `tests/bms/test_final_l.py`, `tests/bms/test_final_m.py`,
  `tests/bms/test_review_final6_ids.py` picked the lines holding "Qty. " / "Qty. (", which no longer print: they now
  read the "Qty (" lines (before the fix the id guards there passed on an empty text).
- Ruling 19 and 15: `tests/bms/test_run_front_end.py` (the new front end prints the template default lines with the
  writer's line, in template order; the line reads "Furnish and Install Qty (##) ..." while its count is unknown).
- Ruling 19: `tests/bms/test_t005e_format_order_labor.py` (New front end gets 3-D Graphics), and the merge with
  T-005c: the existing-BMS fixtures name "Niagara N4" (one of AME's three) so T-005c's red *** flag stays out.
- Merge with T-005c: `tests/bms/test_render.py` (conflict resolved), `tests/bms/test_t005c_proposal.py` (two
  front-end tests pick their own line).
- Must fix 1: `tests/bms/test_t005e_addendum.py` and its fixture `tests/bms/fixtures/t005e_addendum_job.json`.
- New: `tests/bms/test_review_t005e.py` (the lead's six tests, as sent).
