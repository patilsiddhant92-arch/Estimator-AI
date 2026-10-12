# T-009 task 1: design, and the question that stops it (Hark, 2026-10-12)

Task 2 (one demolition exclusion) is done. Task 1 needs a change in `src/bms/model.py`, so I stopped and ask first.

## Design
1. Read the plan count: new `takeoff.apply_plan_counts(job, devices, sheet_pages)`. For each block, it takes the sheets
   of the block's areas (as `_device_lines` does), tallies each label in `devices.json` key `plan_count_labels`
   ("T", "TB") with `device_tally` (new-work sheets only; MD sheets stay set aside), and finds the block's
   thermostat-kind lines (by slot, or by the words of the name, see the report).
2. A line with a plan count below another number gets `quantity = Count(value=plan, sources=one Ref per counted
   sheet, others=())` and `flag="quantity"`. `Count.highest()` then IS the plan count, so `_printed`, `_header_text`
   and `validate._count_problems` need no change, and `ai._count_from` / revise cannot restore the 55 because it is
   no longer in that Count.
3. Where the other numbers go (this is the question). `Count.others` cannot hold them (they would print). `Count.added_up`
   holds one number only and means a sum of sheets. So the sequence's number, and every other number, must live
   outside the line's Count with their citations. Two ways, both touch `model.py`:
   - A (my pick): add the value "plan count prints" to `SetAsideReason`. One `SetAside(family=<device id>, value=<other
     number>, ref=<its source>, reason="plan count prints", note="55 per sequence; 30 drawn on M-201 and M-202")`
     per other number. `Job.set_aside` already goes to the Evidence Package (`set_aside_rows`) and the writer register,
     so nothing is lost and `evidence.py` / `review.py` need no change. One enum value, no new field.
   - B: a new field on `Count` (`not_printed: tuple[OtherCount, ...]`). Cleaner in meaning, but it changes the schema
     of every Count, and `to_dict` / `from_dict` round trips.
4. The "*Verify" line: built in a new function that `render._count_note` calls. Sheets come from the line's
   `quantity.sources`; the other numbers come from the line's set-asides. Highest first, split at "; " over 160.
5. Validator and prompts: `_count_problems` is unchanged (the value is the highest its Count holds). The three
   prompts name the rule "Thermostats drawn on plans print the plan count" and say the writer keeps the sequence's
   number as the line's count; the step moves it. `run.py`: one call after the writers, after
   `attach_device_set_asides`.
6. Idempotent: a line whose value already equals the plan count with its set-asides present is left alone. A typed
   count in `decisions.json` is skipped (`run._typed_counts`).

## Question for the lead
May I add `"plan count prints"` to `SetAsideReason` in `model.py` (option A)? Or do you want option B? If A, also
`SET_ASIDE_REASONS` and the `SetAside.reason` doc string change; no other `model.py` line. I do task 1 as soon as you answer.
