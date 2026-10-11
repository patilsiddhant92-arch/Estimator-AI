# T-005e: fixes before merge (lead, 2026-10-11)

- Verdict: not merged as is. The red-text path and the off-hours and prevailing-wage work are sound. Fix the items
  below on hark/T-005e and push again. The full review is in `HarkPro/inbox/T-005e-review.md`.
- Base: origin/lead/wave2 now carries hark/T-005c (merged by the lead today). If origin/lead/wave2 does not yet show
  that merge when you start, merge origin/hark/T-005c (f453c8c) into hark/T-005e yourself and resolve the render.py
  and test_render.py conflicts (front-end section and docstring). The lead merges the result.
- Must fix 1: src/bms/render.py about lines 618-623 sorts by GEM position before the shape's slot order. The Master
  Template entry's own order wins (GEM v4 about lines 396-402; playbook/rules.md about line 599). The GEM order applies
  only to the devices the entry does not order (the catch-all slots): place each such device at its GEM position among
  the ordered slots. The branch's own AHU test pins the wrong order (Freezestat and the damper before the fan
  start/stop): fix the test with the code.
- Must fix 2: add the file `HarkPro/inbox/T-005e-review-tests.py` to tests/bms/ as test_review_t005e.py and make all 6
  tests pass. 4 fail now.
- Should fix: valve position feedback is GEM slot 10, not 16; classify "Furnish and Wire" devices by what they are, not
  by the verb. An overtime ban ("no overtime", "overtime is not permitted") is not off-hours work: add a negation check
  with a test. Remove the sub-headings inside blocks; the Master Template has none. The off-hours and prevailing-wage
  lines must also appear in the Evidence Package and Review.html.
- Afternoon rulings (NOTES-2026-10-11.md, items 14 to 19) that T-005e must follow: '*' notes are one short line per
  item, several per block allowed, never a paragraph; quantities print in the line itself as "Qty (#) <device>", no
  separate quantity note; no tech-hour line in the proposal (already right). The Demolition Scope block is the lead's
  work; do not add it.
- run.py: you edited src/bms/run.py (about lines 68 and 756). The rule is now: an agent may edit run.py when the task
  names it, and the lead reviews that diff first. List in your report every run.py line you changed and why. Keep it
  minimal.
- Report: HarkPro/outbox/T-005e-report.md updated with the real test output (touched files, tests/bms, full suite).
