# T-009 task 1: design (Hark, 2026-10-12; the lead approved option A the same day)

## Design
1. Read the plan count: new `takeoff.apply_plan_counts(job, devices, sheet_pages)`. For each block it takes the sheets
   of the block's areas (as `_device_lines` does) and tallies the labels of `devices.json` key `plan_count_labels`
   ("T", "TB") on the new-work sheets only (MD sheets stay set aside). It finds the thermostat-kind lines by slot or
   by the words of the name (see the report).
2. A line with a plan count below another number gets `quantity = Count(value=plan, sources=one Ref per counted
   sheet, others=())` and `flag="quantity"`. `Count.highest()` is then the plan count, so `_printed`, `_header_text`
   and `validate._count_problems` need no change, and `ai._count_from` cannot restore the 55 from that Count.
3. The other numbers: `Count.others` would print them and `Count.added_up` means a sum of sheets, so they live
   outside the line's Count. Option A (approved): the value "plan count prints" of `SetAsideReason`; one
   `SetAside(family=<device id>, value=<other number>, ref=<its source>, reason="plan count prints", note=<both
   numbers>)` per number and source. `Job.set_aside` already reaches the Evidence Package and the writer register.
   (Option B, a new `Count` field, was not built.)
4. The "*Verify" line: new `render._verify_lines`, called by `_count_note`. Sheets come from the line's
   `quantity.sources`, the other numbers from its set-asides, highest first, split at "; " over 160 characters.
   It prints only while the line still prints the plan count the set-aside was recorded for.
5. Validator and prompts: `_count_problems` is unchanged. The three prompts name the rule "Thermostats drawn on plans
   print the plan count". `run.py`: one call after the writers and `attach_device_set_asides`, before the decisions.
6. Idempotent: a line that already prints the plan count keeps its set-asides. A typed count is skipped. The step
   drops its own set-asides for a line that no longer prints their plan count.
