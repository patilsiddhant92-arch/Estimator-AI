# G-002 report

1. Task G-002. Branch `grok/G-002`. Base `origin/lead/wave2` at `3ce5f11`. The report commit is the tip after the commits below.

2. Commits, oldest first:

- `2bb12ab` test: device lines print Qty (N) in front (G-002)
- `224676e` playbook: set the quantity prefix words (G-002)
- `5c44988` render: put Qty (N) in front of a device line (G-002)
- `4004a19` playbook: drop {qty} from the shape forms (G-002)
- `c547858` price sheet: read a Qty (N) prefix and keep the old end form (G-002)
- `bfd0193` fixtures: quantity prefix in the sample Playbook (G-002)
- `1cd0f45` tests: expect Qty (N) in front of the device line (G-002)

`git diff --stat origin/lead/wave2...HEAD` before this report file:

```
 playbook/shapes.json                            | 1172 +++++++++++------------
 playbook/wording.json                           |    4 +-
 src/bms/ai.py                                   |    3 +-
 src/bms/render.py                               |   43 +-
 src/bms/validate.py                             |   11 +-
 src/estimator/price_sheet/price_book.py         |    5 +-
 src/estimator/price_sheet/rows.py               |    9 +-
 src/estimator/price_sheet/write.py              |    8 +-
 tests/bms/fixtures/sample_playbook/shapes.json  |    8 +-
 tests/bms/fixtures/sample_playbook/wording.json |    4 +-
 tests/bms/test_citations_final_c.py             |    2 +-
 tests/bms/test_playbook_edits_1010.py           |    2 +-
 tests/bms/test_quantity_prefix.py               |   99 ++
 tests/bms/test_render.py                        |   16 +-
 tests/bms/test_render_count_notes.py            |    4 +-
 tests/bms/test_run_front_end.py                 |    4 +-
 tests/bms/test_t005e_addendum.py                |    4 +-
 tests/bms/test_validate.py                      |    7 +-
 18 files changed, 759 insertions(+), 646 deletions(-)
```

3. What changed:

- `playbook/wording.json`: `quantity.line` is `Qty ({n}) ` and `quantity.unknown` is `Qty (##) `.
- `playbook/shapes.json`: 586 shape forms each lost one trailing `{qty}`. No other byte on those lines changed.
- `src/bms/render.py`: `line_prints_quantity` is the shared rule. A matching line prints the prefix in front of the verb. `GENERIC_FORM` has no `{qty}`.
- `src/bms/validate.py`: an unknown count is a check when that rule matches.
- `src/bms/ai.py`: an untemplated line prints as `{verb} {device}{owner}`, and the renderer puts `Qty (N) ` in front when the count differs from the block's.
- `src/estimator/price_sheet/price_book.py`, `rows.py`, `write.py`: the prefix is not part of the price-book name. `Qty (##)` is QUANTITY PENDING. `(Qty. N Total)` still prices.
- `tests/bms/fixtures/sample_playbook/wording.json` and `shapes.json`: the same wording change, and `{qty}` removed from four lines (1, 2, 1 and 2 tokens).
- `tests/bms/test_quantity_prefix.py`: the new tests.
- Expected text in the seven test files listed in section 4.

4. Tests added: `test_a_different_count_prints_in_front_and_the_block_count_does_not`, `test_an_unknown_device_count_is_flagged`, `test_the_price_sheet_prices_both_forms_and_holds_an_unknown_line`, `test_price_key_takes_the_prefix_off_and_keeps_the_old_end_form`.

Changed test files: `tests/bms/test_render.py`, `tests/bms/test_render_count_notes.py`, `tests/bms/test_run_front_end.py`, `tests/bms/test_t005e_addendum.py`, `tests/bms/test_citations_final_c.py`, `tests/bms/test_playbook_edits_1010.py`, `tests/bms/test_validate.py`.

Real tails:

```
4 passed in 2.40s
```

```
FAILED tests/bms/test_validate.py::test_an_unknown_device_quantity_with_no_clarification_is_a_check
1 failed, 2745 passed, 4 xfailed in 276.42s (0:04:36)
```

```
5 passed in 2.58s
```

```
2746 passed, 4 xfailed in 285.23s (0:04:45)
```

```
5093 passed, 4 xfailed in 643.26s (0:10:43)
```

`python -m bms playbook-lint` printed `The Playbook at D:\EA-grok-g002\playbook is clean.` and exited 0.

Step 3 check, over every shape form on this base:

```
ended 586
matched 586
unmatched 0
extra Unit Ventilators terminal_strip_device kind device form {device}{owner}
```

The rule is: the form contains `{verb}` or `{device}`, and the slot kind is not `interlock`. It matches every form that ended with `{qty}`. It also matches `Unit Ventilators` / `terminal_strip_device`. That line gains a prefix when its count differs from the block's. The lead decides.

Step 4 check:

```
git diff --numstat playbook/shapes.json
586	586	playbook/shapes.json
```

2180 lines before and after. 586 changed lines. Each new line is the old line with one `{qty}` removed. No other change. The sample file is `4	4` and the removed token counts on those lines are 1, 2, 1 and 2. The sample file has no `{qty}` left.

5. Not done as written:

- The branch starts at `3ce5f11`, the `origin/lead/wave2` head when the Playbook gate opened. The task named `b0e0582` and 562 forms. This head has 586 forms. The count in the report is the count on this base.
- The starting patch's `rules.md` hunk was not applied. The `$format` hunk in `wording.json` was not applied.
- `playbook/shapes.json` still names `{qty}` in the `$format` note (the wording sentence near the top of the file). That sentence was left as it is.
- The check script was not committed.
- On the sample Playbook, four forms contain `{verb}` or `{device}` and never ended with `{qty}`: Exhaust Fan `start_stop_status`, Duct Heater `heater_control`, VRF `gateway`, and VRF `comm_wiring`. The same rule gives those lines a prefix when the count differs. The real Playbook has no extra form of that kind except `terminal_strip_device`. `test_validate.py` now uses RTU `map_points` as the line that prints no quantity. The lead decides.
- Commit `4004a19` says `The \ note stays.` The `$format` note itself is unchanged.

6. Questions: none.
