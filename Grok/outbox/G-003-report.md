# G-003 report

1. Task: G-003. Branch: `grok/G-003`. Code tip before this report: `ba8250a5d4db782f0b2b0b895f4444b168e7730c`. Base used for the work: `origin/lead/wave2` at `5d1e5b67a581282ec9a6b779d8877340f51f3e0b`. The task named `5b1bd74` or later. The branch started at `5b1bd74`. G-002 landed during the work, so this branch merged `origin/lead/wave2` (`5d1e5b6`) before the first push. That merge is `5dc9adc`.

The lead merged `grok/G-003` at `f5b64af` on 2026-10-12, then committed `3c64f79` on `lead/wave2` (user-guide wording and a reviewer test). This report is the commit after `ba8250a` on `grok/G-003`.

2. Commits, oldest first:

- `3b8067d` fix: Demolition Scope labor rows are hours, not a device price
- `5dc9adc` Merge origin/lead/wave2 into grok/G-003
- `7315e34` fix: a red price-sheet row paints only the description and the flag
- `bb703f5` fix: the Demolition Scope block has a stable key
- `ba8250a` docs: add the final-wave section to the user guide

Diff stat against `5d1e5b6` (three-dot):

```
 docs/USER-GUIDE.md                   |  21 +++++
 src/bms/render.py                    |   5 +-
 src/estimator/price_sheet/check.py   |   4 +-
 src/estimator/price_sheet/rows.py    |  15 ++-
 src/estimator/price_sheet/write.py   |  16 +++-
 src/estimator/scope.py               |   1 +
 tests/bms/test_demolition.py         |  11 ++-
 tests/bms/test_price_sheet_polish.py | 176 +++++++++++++++++++++++++++++++++++
 8 files changed, 236 insertions(+), 13 deletions(-)
```

3. What changed:

- `src/estimator/price_sheet/rows.py`: a labor row carries `Row.labor`. A known demolition count is flagged `HOURS BY ESTIMATOR`. An unknown count sets `quantity_pending`. `SentRow.flag` is read from column H. `sheet_plan` selects labor rows with `Block.key == "demolition"`.
- `src/estimator/price_sheet/write.py`: a labor row skips the price book. Hours and price stay empty. A red row paints the description and the flag. Hours and quantity keep their own font.
- `src/estimator/price_sheet/check.py`: a row flagged `HOURS BY ESTIMATOR` is left out of the price-check counts.
- `src/estimator/scope.py`: `Block.key` defaults to `""`.
- `src/bms/render.py`: `_demolition_block` sets the key. The constant `DEMOLITION_KEY` sits next to that function. No other function in that file was edited.
- `docs/USER-GUIDE.md`: the new section "What changed in the final wave", 21 lines, after "How to run a job".
- `tests/bms/test_price_sheet_polish.py`: the new tests.
- `tests/bms/test_demolition.py`: the red-row assertion now matches Task 2.

4. Tests added:

- `test_a_known_labor_count_is_hours_by_estimator_and_not_priced`
- `test_an_unknown_labor_count_is_quantity_pending`
- `test_an_unmatched_device_stays_price_pending_and_a_labor_row_does_not`
- `test_an_off_hours_row_is_red_only_on_the_description_and_the_flag`
- `test_a_demolition_labor_row_is_red_only_on_the_description_and_the_flag`
- `test_render_gives_the_demolition_block_a_key`
- `test_the_key_selects_labor_rows_when_the_heading_text_differs`
- `test_a_job_saved_without_the_key_loads_with_an_empty_key`

Existing test whose expected result changed:

- `tests/bms/test_demolition.py::test_the_price_sheet_has_a_red_labor_row_per_line`. Task 2 stops the red paint on the quantity cell and the hours cell. The assertion now requires those cells to stay free of `FF0000` and `C00000`, and the flag cell to be bold `C00000`. The description cell stays `FF0000`.

The unmatched-device test counts `PRICE PENDING` on every price sheet. The sample job has an add alternate, so Price Sheet 1 alone is a short count.

Real tails, from `D:\EA-grok-g003` with `PYTHONPATH=src`:

- Before any code change: `8 failed in 21.84s` (`tests/bms/test_price_sheet_polish.py`).
- Task 1 tests after the labor-row change: `3 passed, 5 deselected in 10.86s`.
- Polish file plus the demolition red-row test, after Tasks 2 and 3: `9 passed in 11.94s`.
- Named proof set (polish, price book, price check, price rows, write price sheet, demolition, g1 review, t005e labor, render): `242 passed in 90.63s (0:01:30)`.
- `pytest tests/bms -q -n 4 -p no:cacheprovider -m "not slow"`: `2913 passed, 4 xfailed in 463.60s (0:07:43)`.
- `pytest tests -q -n 4 -p no:cacheprovider -m "not slow"`: `5260 passed, 4 xfailed in 905.09s (0:15:05)`.

Zero failures. These runs are on `ba8250a`, before the lead's follow-up commit `3c64f79`.

5. What was done in a different form from the task text:

- The review page code (`src/bms/review.py`, `review_page`) builds one card per system, plus a card for the front end and the whole job when those have questions. A count question is asked once per family, on that system's card. The guide section I pushed says that. The task text said "one card per family". The lead's commit `3c64f79` on `lead/wave2` changed the guide sentence to one card per family. I left the page code as it is.
- Demolition is the last block of the base bid (`src/bms/render.py`). `bms.labor.with_labor` adds Labor Conditions after it. Alternates print after the base bid. The guide says that. The task text said the block prints last.
- In chat mode the takeoff stage uses `ChatTransport` and the run returns `waiting` at stage `takeoff` (`src/bms/run.py`). The guide I pushed says the estimator answers that request like the other requests. The lead's `3c64f79` says a subagent of the lead's session answers it, and the estimator reviews the result on the review page.
- `src/estimator/proposal/read.py` builds a `Block` from the Word file and does not copy a key. That file is outside the task's list, so I left it. A price sheet made from a proposal that was read back from Word has an empty key, so the heading text alone does not select labor rows.
- The price check skips an `HOURS BY ESTIMATOR` row for every total in that report. The row is absent from the unmatched list. The Summary's `PRICE PENDING` count also leaves the labor row out.
- I merged `origin/lead/wave2` once, at the G-002 landing (`5d1e5b6`). I left the later tip (`658eb0a`, HarkPro T-007, then `3c64f79`) unmerged into this branch. The lead has already merged `grok/G-003` on top of T-007.
- The Task 1 commit message was amended before any push, to remove a byte-order mark. The pushed hash is `3b8067d`.

6. Questions:

- A proposal read back from Word loses `Block.key`. Should `read.py` keep the key so a later price sheet still treats the Demolition Scope as labor? I did not edit that file.
- The merged guide on `lead/wave2` (`3c64f79`) says the review page has one card per family. The page code still builds one card per system. I made no further code change after the merge.

Choices this task left open:

- Key field name: `key`. Value for the Demolition Scope: `demolition`. A Job saved before the field loads with `key` equal to `""`.
- Flag-cell red: `C00000`, bold, the existing `_FLAG_FONT`. Description-cell red: `FF0000`, the existing `_RED_FONT`.
- New guide section: 21 lines, from the heading "What changed in the final wave" through the blank line before "What you get".
