# T-G1 report

Branch `grok/T-G1` is pushed. Base is `origin/takeoff/s1` (`7408ff2`). Worktree is `D:\EA-grok-g1`.

Demolition Scope is on the Job, in the proposal as the last block, on the evidence tab, and on the price sheet as red labor rows. The run attaches it after `plan_job`.

## Commits

Oldest first, on top of `7408ff2`:

- `b593abd` model: DemolitionLine and Job.demolition (T-G1)
- `f144dad` takeoff: build Demolition Scope lines from units (T-G1)
- `e191e0e` render: print the Demolition Scope as the last block (T-G1)
- `7fd3ee1` evidence: add the Demolition Scope tab (T-G1)
- `49d1902` price sheet: red labor rows for the Demolition Scope (T-G1)
- `3318e9b` run: attach the Demolition Scope after plan_job (T-G1)
- `fe88640` header: keep the job folder when a Takeoff folder sits inside 2. Takeoffs

The report commit follows these.

## Diff stat

`git diff --stat origin/takeoff/s1...HEAD` before this report file:

```
 .../specs/2026-10-04-rebuild-interfaces.md         |  10 +-
 src/bms/evidence.py                                |  25 +++-
 src/bms/model.py                                   |  32 ++++-
 src/bms/render.py                                  |  39 ++++-
 src/bms/run.py                                     |   4 +
 src/bms/takeoff.py                                 |  65 +++++++++
 src/estimator/price_sheet/rows.py                  |  25 +++-
 src/estimator/price_sheet/write.py                 |   4 +
 src/estimator/writing/front_end.py                 |   5 +-
 tests/bms/fixtures/sample_job.json                 |   9 ++
 tests/bms/test_contracts.py                        |  44 +++++-
 tests/bms/test_demolition.py                       | 157 +++++++++++++++++++++
 tests/bms/test_render.py                           |  10 +-
 tests/bms/test_run.py                              |  34 +++++
 tests/bms/test_t005c_proposal.py                   |   4 +-
 15 files changed, 444 insertions(+), 23 deletions(-)
```

## Step tests

Commands ran from `D:\EA-grok-g1` with `PYTHONPATH=src` and `D:\Estimator AI\.venv\Scripts\python.exe`.

1. Model. `pytest tests/bms/test_contracts.py -q -p no:cacheprovider -k demolition` then the whole file.
   - `7 passed, 67 deselected in 56.63s`
   - `74 passed in 55.40s`

2. Builder. Demolition builder tests.
   - `4 passed in 36.13s`

3. Render. `tests/bms/test_demolition.py` and `tests/bms/test_render.py`.
   - `116 passed in 78.14s (0:01:18)`
   - The sample job now has one demolition line, so an older red-line test saw two red lines: `1 failed, 91 passed in 68.66s (0:01:08)`. Failure: `test_a_marked_line_in_a_system_block_prints_red_too`. The marked job is now built with `demolition=()`. Re-run: `7 passed in 33.30s`.

4. Evidence tab.
   - `1 passed in 25.92s`

5. Price sheet.
   - `1 passed in 90.61s (0:01:30)`

6. Run. `tests/bms/test_run.py` demolition test.
   - `1 passed in 39.26s`

`takeoff/s1` has no point that attaches the takeoff register. `attach_demolition` in `src/bms/takeoff.py` runs immediately after `plan_job`. HarkPro T-006 moves that call.

## Proof

First `pytest tests/bms -q -n 4 -p no:cacheprovider -m "not slow"`:

```
FAILED tests/bms/test_review_t005c.py::test_a_takeoff_subfolder_named_takeoff_does_not_become_the_job_folder
1 failed, 2584 passed in 901.35s (0:15:01)
```

`assert header.quote_number == "26-7102"` got `2. Takeoffs`.

After `fe88640`, the same BMS command:

```
2585 passed in 534.37s (0:08:54)
```

Full suite `pytest tests -q -n 4 -p no:cacheprovider -m "not slow"`:

```
4906 passed in 1214.54s (0:20:14)
```

Zero failures on both proof runs after `fe88640`.

Narrow header check before the BMS re-run: `10 passed, 48 deselected in 42.28s`.

## Step not done as written

`fe88640` is not a written G1 step. The BMS suite cannot be green without it. The failing test and `job_folder` had an empty diff against `origin/takeoff/s1` before the edit. A folder named `Takeoff` inside `2. Takeoffs` matched the takeoffs pattern, so the walk returned `2. Takeoffs` and the quote number became that name. The walk now skips a match whose parent also matches. The job folder stays the parent of the outer takeoffs folder. A higher folder that is also named Takeoffs does not win. `1. Base Takeoff` still does not match.

No other written step was skipped.
