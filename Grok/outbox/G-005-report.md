# G-005 report

Task: G-005. Branch: `grok/G-005`. Base: `e28ff96` (`origin/rebuild` at the start of this task). Code tip: `4e67c1e`. This report is the commit after that tip.

`origin/rebuild` moved 14 commits after `e28ff96` while this branch was open (T-009 and the lead's prompt wording for ruling 24). This branch stays on `e28ff96` plus the three commits below. It was not merged and it was not rebased.

## Commits

- `95d840d` fixtures: sample playbook quantity words use the end form
- `2b6ff2b` render: a device line ends with its quantity (ruling 24)
- `4e67c1e` proposal: labor facts print as red sub-bullets (ruling 26)

Diff stat against `e28ff96`: 24 files, 646 insertions, 135 deletions.

## What changed

- `playbook/wording.json` and `tests/bms/fixtures/sample_playbook/wording.json`: `quantity.line` is ` (Qty. {n} Total)`. `quantity.unknown` is ` (Qty. ##)`.
- `src/bms/render.py`: `_device_lines` appends those words after the owner bracket and before other-count notes. An unknown count stays red.
- `playbook/rules.md`: the five device-line rules below. No other rule.
- `src/estimator/proposal/write.py`: a labor condition is a red `PR3` sub-bullet under its template point. The template points stay.
- `src/estimator/proposal/read.py`: `_exclusions` skips a paragraph of style `PR3`.
- `src/bms/labor.py`: the module doc string no longer says the template lines give way.
- Tests listed below.

The price-sheet code is unchanged. `test_the_price_sheet_reads_the_end_form_and_the_old_prefix` passed with the end form and with the old prefix.

## Tests added

`tests/bms/test_g005_quantity_form.py`

- `test_a_different_count_prints_at_the_end`
- `test_the_block_count_with_no_note_prints_no_quantity_words`
- `test_the_block_count_with_a_note_prints_the_total_then_the_other_counts`
- `test_an_unknown_count_ends_red_and_a_future_line_stays_red`
- `test_the_fan_coil_header_keeps_the_source_breakdown`
- `test_a_front_end_line_uses_the_same_end_form`
- `test_demolition_and_named_exceptions_keep_qty_n`
- `test_the_price_sheet_reads_the_end_form_and_the_old_prefix`
- `test_the_real_playbook_loads_and_lints_clean`

`tests/bms/test_g005_generic_sections.py`

- `test_both_sections_keep_every_template_point_and_add_two_red_sub_bullets`
- `test_each_sub_bullet_follows_its_parent`
- `test_the_five_template_sub_bullets_stay_under_their_parent`
- `test_the_normal_hours_point_and_the_off_hours_exclusion_stay`
- `test_off_hours_with_no_range_names_the_work_and_the_source`
- `test_one_condition_adds_one_sub_bullet`
- `test_no_labor_condition_leaves_both_sections_as_the_template`
- `test_a_sub_bullet_is_not_a_named_exception`
- `test_a_missing_parent_raises`
- `test_the_hours_reader_takes_a_time_range_in_the_first_brackets_only` (six sentences)

## Existing tests whose expected result changed

Ruling 24. Each pin now expects the quantity at the end of a device line.

- `test_citations_final_c.py`: the controller line is `(Qty. 2 Total)` and then the other-count note.
- `test_final_l.py`, `test_final_m.py`, `test_review_final6_ids.py`: the line filter also matches `(Qty.` so an end-form line is still checked. The assertions are the same.
- `test_g004_review_flags.py`: an unknown line ends with ` (Qty. ##)` and stays red. A known line ends with ` (Qty. 4 Total)`. A future line contains ` (Qty. 2 Total)` and ends with `(FUTURE)`.
- `test_playbook_rulings_1011.py`: the five device-line rules name ruling 24 and the end form.
- `test_quantity_prefix.py`: a different count ends with `(Qty. N Total)`. The block count with no note has no quantity words. The old prefix still prices.
- `test_quantity_prefix_review.py`: `(Qty. N Total)` comes before the other-count note.
- `test_render.py`: golden device lines use the end form. Headers stay `Qty (n)`.
- `test_render_count_notes.py`: a line whose count equals the block and that carries a note includes `(Qty. 5 Total)` before the note.
- `test_run_front_end.py`: an unknown front-end line ends with ` (Qty. ##)`.
- `test_t005c_proposal.py`: a red line may end with ` (Qty. ##)` or with the future mark.
- `test_t005e_addendum.py`: the damper line ends with `(Qty. 4 Total)` before the other-count note.
- `test_t008_render.py`: a valve whose count differs from the block ends with `(Qty. 10 Total)`.

Ruling 26.

- `test_t005e_format_order_labor.py`: `test_the_proposal_keeps_both_labor_points_and_adds_red_sub_bullets`. Both template points stay. The red lines are the sub-bullets under them.

These files name `labor_conditions` and needed no expected-result change: `test_t008_labor.py`, `test_t008_reviewer.py`, `test_review_t005e.py`, `test_g003_review.py`.

## Test tails

Ruling 24, new file, before the production edit: `6 failed, 3 passed in 11.85s`.

Ruling 24 proof set after the first expected-result edit: `1 failed, 507 passed in 69.80s`. The failure was `test_a_device_quantity_below_the_highest_with_no_source_is_named`. The line carries a note, so the pin now includes `(Qty. 5 Total)` before the note.

Ruling 24 BMS suite after that pin, before the valve pin: `1 failed, 3056 passed, 4 xfailed in 985.67s (0:16:25)`. The failure was `test_a_valve_family_under_an_ahu_prints_no_header_of_its_own`. The valve count differs from the block, so the pin now looks for `(Qty. 10 Total)`.

Valve test after that pin: `1 passed in 7.46s`.

Ruling 24 BMS suite after that pin: `3057 passed, 4 xfailed in 1167.08s (0:19:27)`.

Ruling 26, new file, before the production edit: `13 failed, 2 passed in 15.35s`.

Ruling 26 file plus `test_t005e_format_order_labor.py` after the production edit: `56 passed in 36.28s`.

Proof set (`test_g005_quantity_form.py`, `test_g005_generic_sections.py`, `test_render.py`, `test_quantity_prefix.py`, `test_quantity_prefix_review.py`, `test_g004_review_flags.py`, `test_playbook_rulings_1011.py`, `test_price_sheet_polish.py`, `test_t005e_format_order_labor.py`, `test_t008_labor.py`, `test_t008_reviewer.py`, `test_review_t005e.py`, `test_t005e_addendum.py`, `test_g003_review.py`, `tests/test_scope_review.py`): `371 passed in 85.20s (0:01:25)`.

BMS suite after ruling 26: `1 failed, 3071 passed, 4 xfailed in 534.54s (0:08:54)`. The one failure was `test_f6_a_run_without_a_history_says_so_in_one_line` (`assert answer_all(cache)` got `{}`). The same test alone: `1 passed in 16.14s`. The full suite below includes that test and passed.

Full suite: `5421 passed, 4 xfailed in 747.44s (0:12:27)`.

`python -m bms playbook-lint` (`PYTHONPATH=src`, worktree `D:\EA-grok-g005`): `The Playbook at D:\EA-grok-g005\playbook is clean.` Exit 0.

## Playbook rules (ruling 24)

Never undershoot: Never print a count lower than one the documents give. Never invent a number. An unknown count prints "Qty (##)" in a header, and "(Qty. ##)" at the end of a device line (ruling 24), flagged to confirm. The only exceptions, here and in Higher count prints, are the units on demolition sheets, whose count moves to Demolition Scope with its number, and a duplicate label of one unit on two part plans, which a short "*" line names with both numbers.

Line quantity: A line's quantity prints at the end of the line (ruling 24), as "<device line> (Qty. N Total)", when the count is known and differs from the block's count, or when the line carries a note. When the count equals the block's count and the line carries no note, the line has no quantity words. Identical lines for several units are one line with the total ("Furnish Chiller Enable (Qty. 6 Total)"), never one line per tag.

Quantities print in the line: A quantity prints in the line it counts. The block heading keeps "Qty (n) <system>". A device line ends with "(Qty. N Total)" when its count is known and differs from the block count, or when the line carries a note (ruling 24), for example "Furnish and Install Space Temperature Sensor (Qty. 33 Total)". There is no separate quantity note. When two counts differ, the line prints the highest and names each other count with where it is, in brackets, for example "(4 per plan placements)".

Line form: Each line starts with its verb, or with an interlock, tie-in or wiring phrase when it has no verb. A line whose count is known and differs from the block's count, or that carries a note, ends with "(Qty. N Total)" (ruling 24; see Line quantity). No bullets, no category or verb-group headers, no dash after the verb. Details go after the device in brackets: the owner, "(as per sequence)", "(Location: ...)". A combined sensor the documents name as one ("temperature and humidity sensor") is one line; named separately, two lines. A filter switch is one line per filter stage in the documents' name. A line is at most 160 characters.

Untemplated systems: A system with no shape is still written, from its evidence, in the house form "<verb> <device><owner> (Qty. N Total)" (the quantity at the end, ruling 24, see Line quantity), in the standard order, under a header "Qty (n) <name> <tags>". Every rule in this book applies to it.

Proposed text for "Off-hours work and prevailing wage" (left unchanged; the lead decides):

When the documents name off-hours work (for example 6 PM to 6 AM) or prevailing wage, add each to the proposal and to the price sheet, highlighted red. Never exclude either one silently. The standard exclusion "All off-hours or overtime labor." stays. A red sub-bullet under it says what the documents require, for example "The documents require work between 6 PM and 6 AM (Spec Section 01 14 00)". The prevailing-wage sentence keeps its words and moves under the template point about wages or labor rates. When the template has no such point, it moves under "All labor will be performed during normal business working hours (M to F, 7AM to 4PM)." It is a sub-bullet under that point. The section keeps its own points and its own numbering.

## Choices

- Wage parent: the normal-hours clarification, "All labor will be performed during normal business working hours (M to F, 7AM to 4PM)." The code looks first for a clarifications `PR2` point whose text contains "wage" or "labor rate". This template has none.
- Reader: `_exclusions` skips style `PR3` after the hidden-text check. `_clarifications` still returns its `PR3` lines. `read_named_exceptions` is unchanged.
- Quantity words and a FUTURE mark: `_with_marks` still appends `(FUTURE)` after the finished line. The order is the owner bracket, then `(Qty. N Total)`, then the other-count bracket, then `(FUTURE ...)`. `_with_marks` is unchanged.
- A missing parent raises `TemplateError`. Off-hours: "the exclusions section has no off-hours point". Wage: "the clarifications section has no labor point".

## Left as it is

- Ruling 22. The two demolition exclusion lines. HarkPro's T-009 places: `_printed`, `_count_part`, `_counts_text`, `_qty_notes`, `_header_counts`, `_count_note`, `write_proposal`, `read_named_exceptions`, `scope.py`.
- `line_prints_quantity` (`src/bms/render.py` lines 717-718) still says the prefix is in front.
- `LaborCondition` in `src/estimator/scope.py` lines 114-115 still says the template lines give way.
- `src/bms/ai.py` line 834 still says the renderer puts "Qty (N) " in front.
- `src/bms/prompts/takeoff_job.md` line 44 still says quantities print as "Qty (#) <device>". The later rebuild commits `8c9d233` and `0be8585` change the prompts. Those commits are not on this branch.
- Block headers, Demolition Scope, and named exceptions still use "Qty (n)".
- The scope block "Labor Conditions" and the red price-sheet rows.

## Self-review

Two separate agents reviewed the branch. Neither agent wrote the code. Neither review found a defect. Nothing was left to fix before the push.

Ruling 24 (`e28ff96..2b6ff2b`): invented fixtures; the changed pins match the end form; the five rules agree; the diff adds the suffix and drops no count; no new regex; only the allowed files; one fixture commit and one ruling-24 commit; unknown and FUTURE lines stay red; `test_the_real_playbook_loads_and_lints_clean` runs playbook-lint.

Ruling 26 (the diff that is `4e67c1e`): invented fixtures, including the six required hours sentences; the changed labor test keeps both template points; no Playbook edit; both labor points stay and a missing parent raises `TemplateError`; the hours test has three matches and three non-matches; only the five allowed files; the new sub-bullets are red `PR3` lines under 160 characters; `playbook/` is absent from that diff.

## Questions

none.
