# G-004 report

## 1. Task

- Task id: G-004.
- Branch: `grok/G-004`.
- Code tip: `8fc296d60f1b8779664b4a8d0597028bbd0d73ce`.
- Base: `52fd0ce5fc80f93bf2eb02cf4e75d80353a76f41` (`origin/rebuild` at the start of this branch). `0ff732c` is an ancestor of that commit.
- This file is the report commit on the same branch.

## 2. Commits

Commits on this branch after the base:

- `ce9456d5cd4dbcf69226e9db3dfe26604e4f8055` review: one question per family, with a sub-point for each
- `e665c0aba70182525a536d9122bfad7a8f42341a` render: print an unknown device count in red
- `8fc296d60f1b8779664b4a8d0597028bbd0d73ce` render: note a system that has no devices

Diff stat of those three commits against the base:

```
 src/bms/render.py                   | 112 ++++++++++-
 src/bms/review.py                   | 118 ++++++++++--
 tests/bms/test_g004_review_flags.py | 367 ++++++++++++++++++++++++++++++++++++
 tests/bms/test_quantity_prefix.py   |   2 +
 tests/bms/test_render.py            |   3 +
 tests/bms/test_review.py            |  29 ++-
 tests/bms/test_t005c_proposal.py    |   4 +-
 7 files changed, 601 insertions(+), 34 deletions(-)
```

## 3. What changed

- `src/bms/review.py`: one review card per system. Inside the card, questions are grouped. A group counts as one question toward the cap of 15.
- `src/bms/render.py`: a device line that prints `Qty (##)` is red. A base system with no devices and a reason prints one note on the proposal.
- `tests/bms/test_g004_review_flags.py`: the new tests.
- `tests/bms/test_review.py`, `tests/bms/test_render.py`, `tests/bms/test_quantity_prefix.py`, `tests/bms/test_t005c_proposal.py`: expected results updated where a task changes the result on purpose.

## 4. Tests

New tests in `tests/bms/test_g004_review_flags.py`:

- `test_one_family_with_seven_flagged_devices_is_one_group`
- `test_accept_on_one_sub_point_changes_only_that_device`
- `test_a_finding_that_names_a_flagged_device_keeps_one_sub_point`
- `test_two_families_put_other_questions_in_the_system_group`
- `test_a_group_counts_as_one_question_toward_the_cap`
- `test_show_all_hides_whole_groups`
- `test_a_system_with_no_family_uses_the_system_name`
- `test_front_end_questions_use_one_group_named_front_end`
- `test_an_unknown_device_count_prints_red_qty_hashes`
- `test_a_front_end_unknown_count_prints_red_qty_hashes`
- `test_the_price_sheet_row_for_an_unknown_count_is_red`
- `test_a_reason_that_names_one_block_prints_a_star_line_on_that_block`
- `test_a_reason_that_holds_the_system_name_does_not_repeat_it`
- `test_a_reason_that_names_no_block_prints_no_bms_scope_before_demolition`
- `test_a_reason_that_names_two_blocks_prints_no_bms_scope_on_the_last_block_only`
- `test_a_key_inside_a_longer_tag_does_not_name_that_block`
- `test_a_named_exception_prints_no_scope_note`
- `test_a_system_with_no_reason_prints_no_scope_note`
- `test_an_alternate_with_no_devices_prints_no_scope_note_on_the_base_bid`
- `test_a_long_reason_prints_as_short_points`
- `test_a_job_with_no_block_keeps_todays_left_out_note`

Each new-behavior test failed before the code for that task. The commands ran from `D:\EA-grok-g004` with `PYTHONPATH=src` and `D:\Estimator AI\.venv\Scripts\python.exe`.

Task 1, after the review change, the review files:

```
77 passed in 18.91s
```

Task 1, `pytest tests/bms -q -n 4 -p no:cacheprovider -m "not slow"`:

```
2983 passed, 4 xfailed in 695.69s (0:11:35)
```

Task 2, the named proof files plus `tests/bms/test_t005c_proposal.py`:

```
216 passed in 67.38s
```

Task 2, the same BMS command:

```
1 failed, 2985 passed, 4 xfailed in 457.65s
```

The one failure was `tests/bms/test_ai.py::test_revise_source_id_refusal_is_actionable_and_stops_at_three` (`assert 4 == 3` on `client.calls`). The same test alone:

```
1 passed in 2.99s
```

`ai.py` was not edited. The final full suite below includes this test and passed.

Task 3, the new tests before the render change (`-k` for the Task 3 names):

```
6 failed, 4 passed, 11 deselected in 9.25s
```

The six failures are the new notes. The four passes are the cases that already match today's result (a named exception, a blank reason, an alternate, a job with no block).

Task 3, the same tests after the render change:

```
10 passed, 11 deselected in 10.97s
```

Task 3, the named proof set (`test_g004_review_flags.py`, `test_review.py`, `test_t005b_review_once.py`, `test_render.py`, `test_render_count_notes.py`, `test_quantity_prefix.py`, `test_price_sheet_polish.py`, `test_demolition.py`, `test_exceptions_outside_scope.py`):

```
255 passed in 21.38s
```

Task 3, `pytest tests/bms -q -n 4 -p no:cacheprovider -m "not slow"`:

```
2996 passed, 4 xfailed in 436.82s (0:07:16)
```

Once, at the end, `pytest tests -q -n 4 -p no:cacheprovider -m "not slow"`:

```
5343 passed, 4 xfailed in 607.66s (0:10:07)
```

Zero failures on that run.

## 5. Existing tests whose expected result changed

- `tests/bms/test_review.py::test_cap_about_fifteen_and_show_all`. Thirty Exhaust Fan checks become one group, because that system has one family. The cap would not hide a group. The test now uses an invented job of 16 systems, one flagged device each. It expects 15 `<section class="group">`, one `<section class="group extra">`, no `class="q extra"`, and the header `15 of 16 question(s) shown`.
- `tests/bms/test_review.py::test_must_fix_never_hidden_behind_the_cap`. The sample job, 30 Exhaust Fan checks, and a Duct Heater must-fix stay. Duct Heater has one family, so the must-fix joins that family group. Rank 0 keeps the group visible. The group section that contains `urgent` starts with `<section class="group">` and contains `Must fix`.
- `tests/bms/test_render.py::test_unknown_count_prints_hashes_and_quantity_unknown`. The device line that prints `Qty (##)` has a red run and `quantity is None`. The header is not an item.
- `tests/bms/test_quantity_prefix.py`, the unknown price-sheet row. Column 4 font color ends with `FF0000` and is not a theme color. The flag stays `QUANTITY PENDING`. Quantity and unit price stay empty.
- `tests/bms/test_t005c_proposal.py::test_a_marked_line_in_a_system_block_prints_red_too`. The future line is still one of the red lines. Every other red line starts with `Qty (##) `.

Task 3 changed no existing expected result. The named proof set passed with the current assertions.

## 6. Choices

Group heading: `{name}: {n} point(s) to check`. The word is `point` when n is 1, and `points` otherwise. The name is the family name for a family question. A device question or a system question uses that family name when the system has one family.

A system with more than one family: each family question stays in its family group. The other questions go in one group named with `system.name`.

A system with no families uses `system.name`. The front end (`system_key` `""` and a front end on the job) uses the name `Front end`. A whole-job question with no front end uses the name `Whole job`.

The cap counts a group as one question. The group rank is the lowest rank of its sub-points. The first 15 groups are visible. A hidden group is one `<section class="group extra">`. The `.q` elements inside it are not marked `extra`. A card that has hidden groups shows `N more question(s)`. `Answered` still counts the sub-points.

Duplicate fold: a finding on device A can name device B of the same system as a whole id in the title or the notes. B's flag-only question is dropped. The flag words are added to A's notes. A keeps A's device id. A question that has its own finding stays. A system-level finding does not fold another device. The id match is `(?<![\w.])id(?![\w.])`, so `AHU.d2` does not match inside `AHU.d23`.

`Qty (##)`: the device line's one run is red. The text, the depth, and `quantity is None` stay. A known `Qty (N)` stays black. A future line stays red. A block header that prints `Qty (##)` is not an item. A known device count under an unknown family count prints `Qty (N)` in black, and the item quantity is empty because the block is pending. The price-sheet row follows the run. `rows.py` was not edited.

Place of `No BMS scope`: the last item of the last base-bid block, before the Demolition Scope block. The words are the constant `NO_BMS_SCOPE` next to `LEFT_OUT`: `No BMS scope: {reason}`. The line has no leading star. When the job has no base block, the proposal keeps today's left-out line only.

How a reason is matched to a block: whole phrase, any case, hyphen included in the phrase, against the other system's key, name, or family tag. The pattern is `(?i)(?<![A-Za-z0-9-]){token}(?![A-Za-z0-9-])`. The key `ERV` does not match inside the tag `ERV-1`. Candidates are other base systems that have devices. Exactly one match prints one `*` line on that system's last block, after its other `*` lines. Zero matches, or more than one, print `No BMS scope` on the last base block. The match is made before the system loop, so the named block can print before or after the silent system.

The `*` line is `*{name}: {reason}` when the reason does not already hold the silent system's name as a whole phrase. It is `*{reason}` when the reason already holds that name. A reason that already starts with `*` keeps one star.

`short_points` runs on the composed line only when the reason itself is longer than 150 characters. `short_points` was not edited.

The silent system's left-out line stays in `draft.lines`. The new note is also a `RenderedLine` in `draft.lines`, under the carrier's key for the `*` line, and under the last base system's key for `No BMS scope`.

## 7. What was not done as written

- HarkPro's items stay with HarkPro: valve headers in `_header_families`, off-hours in `labor.py`, and the long `*` notes in `short_points`. Those functions were not edited. `short_points` is called.
- `evidence.py` was not edited. The Scope lines tab still builds the left-out row from `left_out_text`. That row still holds the writer's reason. The new proposal note is in `draft.lines`.
- No merge. No rebase. No push of any branch except `grok/G-004`.

## 8. Questions

None.
