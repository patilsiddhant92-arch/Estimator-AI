# T-005b report: blocks and questions (rulings 8, 9, 11)

1. Task T-005b, branch `hark/T-005b`, base `origin/lead/wave2` 0e78113. Last commit: see `git log -1 hark/T-005b`.
   The code commit is 71e8d9f. The report commit comes after it.

## 2. What changed

### `src/bms/plan.py` (planning of systems and families, question list)

- **Ruling 8, control valves under the unit they serve.** `_Planner.link_valves` (plan.py:1317) runs after
  `place_seen` (plan_job, plan.py:2043).
  - A family is a control valve when its name says "valve" and is not a balancing, relief, check, backflow, PRV,
    isolation, shut-off, gas or fire valve, or when its prefix is CV, TCV or ACV (`_is_control_valve` plan.py:1741;
    patterns at plan.py:88-92).
  - A valve tag is tied to one unit by any of these:
    - a fact (device, link, location, note or provider) that names the valve's tags and exactly one unit;
    - its schedule row, when the other cells name exactly one unit (the "serves" column);
    - plan proximity text (a location fact);
    - its own tag holding the unit's tag (CV-AHU-1).
  - Tag lists and ranges in free text are read: "CV-1 thru 10", "P-1,3,5" (`_named_tags` plan.py:1721).
  - A tag named with two units, by one text or by two, is tied to none.
  - The unit's block takes a family of its valves. It is counted one per tag, cites what tied them, and carries the
    valve family's sequence passages.
  - A family counted by type (count is not one per tag) moves whole only when all of its tags go to one unit.
  - Untied valves stay in the valve block. Its count drops by the valves placed, so nothing is lost, and a question
    asks which unit each serves (and names the tags that were torn between units).
- **Ruling 9, pumps split by service.** `_Planner.split_pumps` (plan.py:1213) runs right after
  `general_kind_tags` (plan.py:2038).
  - Pump families qualify. Condensate and domestic pumps never do.
  - A text that names some pump tags and says exactly one service gives those tags that service. The texts read are
    sequence titles, schedule rows and ledger facts. The services are chilled water, hot water and condenser water
    (`_SERVICES` plan.py:94).
  - Two or more services give one block per service:
    - key `"<prefix> <Service>"`, name `"<Service> Pump"`, new draft kind `"pumps"`;
    - the block's own tags, with a count of one per tag;
    - its own sequence sections (`_section_services` plan.py:1297). A lettered sub-section follows its section. A
      section that says no service goes to every block.
  - Shape lookup per block (`_pump_shape` plan.py:1183, called at plan.py:922): first the shape its name says, then
    the shape whose name or kind words say the service ("Chilled Water System"), then the prefix.
  - Pumps of one service keep one block. It takes the service's name (when its own name is just "Pump") and the
    service's shape.
  - A pump with no service stays in a block of its own and is asked. A pump family counted by type is not split and
    is asked.
- **Ruling 11, plan side.** `one_count_question_per_family` (plan.py:1752) merges count questions about one family
  ("Name (PREFIX): ...; confirm the count.") into one question. It keeps every reason, in the place of the first.
  plan_job uses it at plan.py:2057 (this replaces the plain string dedupe).
- **Addendum, demolition work.** `_Planner.demolition_work` (plan.py:1408) runs before the systems are built.
  - It looks for a note, provider or device fact with a removal word and a controls word (patterns at plan.py:104).
  - When the fact names a block, its citation joins that block's `sequence_refs`. The writer then gets it in its
    evidence ("Ledger facts the planner cited" / "Other passages cited") and can print the removal line.
  - Demolition work that names no block becomes a question.
  - Demolition of a unit alone (no controls word) is left to the counts (T-005a).
- **Addendum, FCU valves and the "Qty ##" pipe sensor.** `_Planner.off_bms` (plan.py:1433) handles a unit that a note
  or provider fact puts off the BMS ("no BMS points", "not connected to the BMS", "stand-alone"; plan.py:108).
  - It asks one question: control valves, pipe sensors and other BMS points print only where the documents give them
    to AME.
  - The question names any valves planned under that unit.
  - I chose to ask rather than drop. See section 4.
- `_Draft.service` was added (plan.py:148). The module docstring lists the new behaviours.

### `src/bms/review.py` (question grouping, ruling 11)

- `_questions` (review.py:96 onward):
  - A line flagged only for its count (flag "quantity", no assumption) folds into the family card when all of these
    hold:
    - it was counted from exactly one disputed family of its block that has a card (`counts.counted_from`, the same
      tie the family Accept clears by);
    - it prints that family's count;
    - its other counts are among the family's (`_repeats_family_count` review.py:225).
  - The family card gets one note naming the folded lines, saying that the answer there settles them too
    (review.py:215).
  - A line with its own count, an assumption, a finding, or two disputed families keeps its own card.
  - Cards with no line (system and family level) that ask the same title in the same block merge into one card
    (`by_title` review.py:100; `squash_title` review.py:220). This merges the duplicate pairs: the q36=q47 / q37=q48
    kind, the same finding given twice.

### Check on the 26-0544 ledger (local only, not committed)

I ran the plan on the 26-0544 ledger I hold from my 2026-10-09 run (real Playbook, empty dossier):
- AHU block holds Control Valve CV-1..10 (10). ERV block holds CV-11, CV-12 (2). There is no CV block.
- "P Chilled Water" (Chilled Water System shape) holds P-1,3,5,7,9,11 with sequence Q50-Q55.
- "P Hot Water" (Hot Water System shape) holds P-2,4,..,12 with sequence Q56-Q61.
- S559 (remove obsolete TCMC controls) goes to AHU. S558 (remove FCUs and associated controls) goes to FCU.
- One question says the FCUs are not on the BMS.

The AHU count of 21 in that ledger is T-005a's area.

## 3. Tests

- `tests/bms/test_t005b_plan_blocks.py` (15):
  - valves by tag reference, by schedule serves column, and by proximity text plus a unit tag inside the valve tag;
  - an untied or torn valve is asked and keeps its count;
  - a valve counted by type moves whole;
  - a balancing valve stays;
  - valves under an off-BMS unit are asked;
  - an off-BMS unit with no valves is asked once;
  - pumps split by service with their own shape and sequence;
  - a schedule row gives the service;
  - pumps of one service take its name and shape;
  - a pump with no service is asked, and a section that says no service goes to every block;
  - condensate pumps are never split;
  - one count question per family;
  - demolition work reaches its block, and work naming no block is asked.
- `tests/bms/test_t005b_review_once.py` (6):
  - lines that only repeat the family count fold into the family card;
  - a line with its own count or an assumption keeps its card;
  - a line counted from two disputed families keeps its card;
  - a finding on a line still shows;
  - the same question twice in one block is one card;
  - the page shows one card for 22 repeating lines.
- Targeted runs:
  - every plan test file (21 files): 620 passed;
  - all `tests/bms/test_review*.py`: 643 passed and 1 failed, which is baseline `test_review_final3` (resource code).
- Full suite result: see the final section.

## 4. What I did not do, and why

- **Removal lines are not printed by the planner.** The planner puts the demolition citation in the block. Printing
  the removal line in `other_wiring` is the writer's job (T-005d, rules.md "Miscellaneous responsibilities").
- **No Demolition block is made for work that names no block.** That work is asked about instead. A block would need
  a Playbook shape and a header.
- **FCU control valves and the pipe sensor are not dropped.** They are writer lines (T-005d). The planner only knows
  that a unit is off the BMS, so it asks. On 26-0544 the documents state that FCUs run on a wall thermostat with
  pipe-temperature changeover. So the "pipe sensor" may belong to the thermostat (by the unit maker), not the BMS. I
  did not set `control="none"` from a note, because that would turn the whole FCU block into an exception. The FCU
  block still has thermostat and demolition scope.
- **Lines from the addendum outside my files were not touched:** global OAT, ERV freezestat and smoke status, EF VFD,
  changeover aquastat, pump controller, and the front-end lines. They belong to T-005d (writer and evidence) and to
  the front end.
- **Plan-only pump tags.** If one is seen on the drawings after a split (`place_seen` runs later), it joins the first
  pump block of its prefix. It is still asked as plan-only.
- **The review fold applies only to flag "quantity" lines.** A line with flag "none" whose own count carries others
  keeps its card, because a family Accept does not clear those others.
- No sibling's files were touched.

## 5. Proposed Playbook changes (for the estimator; I did not edit `playbook/`)

1. Add a rule "Control valves print under the unit they serve": tied by tag reference, schedule "serves" column or
   plan proximity; otherwise a question, never a block of their own. The shapes' `hot_water_valve`/`other_valve`
   slots already exist.
2. Add a rule "Pumps are planned by service". Optionally add a "Chilled Water Pump" / "Hot Water Pump" shape (or kind
   words "chilled water pump", "hot water pump" on the Chilled Water / Hot Water System shapes), so the lookup does
   not depend on the service words of the plant shapes.
3. Optional: a "Demolition" shape (or a rule naming the block that takes job-wide controls demolition, e.g. the
   front end or the first unit block), so work like "remove obsolete TCMC controls" has a home without a question.
4. In "Miscellaneous responsibilities": "A unit the documents put off the BMS (stand-alone thermostat, no BMS points)
   gets no valve, pipe sensor or point lines unless the documents give them to AME."

## 6. Questions

1. Where should controls demolition that names no unit print, for example "remove obsolete controls at the TCMC"?
   - (a) in the front end;
   - (b) in the block of the equipment it serves (AHU on 26-0544, which the planner already does when the fact names
     AHU);
   - (c) a Demolition block.
2. Should an untied control valve stay in a valve block until answered (what I did: never undershoot)? Or should it
   go nowhere until the estimator answers?

## Full-suite result

I ran `python -m pytest tests -n 2 -p no:cacheprovider` in 4 chunks of the 199 test files. A sandbox restart killed
a single whole run, so I used chunks.

| Chunk | Passed | Skipped | Failed |
|---|---|---|---|
| 1 | 1519 | 0 | 5 |
| 2 | 893 | 2 | 2 |
| 3 | 1044 | 0 | 1 |
| 4 | 1371 | 8 | 1 |
| **Total** | **4827** | **10** | **9** |

All 9 failures are accepted baseline tests:
- the 5 `tests/bms/test_ai.py` chat tests;
- `test_review_final3` (resource code);
- `test_status_review` (normal-exit);
- `test_assets` (project python);
- `test_main` (open output folder).

The two revert_audit baseline tests passed this time.

Nothing failed outside the baseline.

## Regression fixtures (NOTES 2026-10-11 rule 4)

- `tests/bms/fixtures/t005b_blocks.json`: an invented copy of the 26-0544 planning defects (same tag forms CV-n, P-n,
  AHU-n, ERV-n, same sheet-number form Mnnn.00, the valve schedule's TAG / LOCATION / SERVES / VALVE TYPE columns,
  pump tags as comma lists in the sequence section titles; invented names and numbers).
- `tests/bms/test_t005b_fixture_regressions.py` (4 tests) reads it:
  - valves as a block of their own: `test_fixture_valves_go_under_the_unit_their_schedule_serves_column_names`
    (8 valves, 6 under three AHUs and 2 under the ERV, no CV block, no question);
  - pumps of two services in one block: `test_fixture_pumps_split_into_one_block_per_service` (chilled water and hot
    water blocks, each with its shape and its own sequence sections);
  - repeated questions: `test_fixture_count_questions_on_one_family_are_asked_once` (plan side) and
    `test_fixture_review_page_shows_one_card_for_lines_that_repeat_the_family_count` (10 repeating lines, one card).
- The inline tests in `test_t005b_plan_blocks.py` / `test_t005b_review_once.py` stay as they are. Note for the lead:
  `test_demolition_work_on_a_unit_reaches_its_block_and_work_naming_none_is_asked` quotes a removal note naming the
  job's control center abbreviation (TCMC); the new fixture does not cover demolition work.

## Tests (NOTES 2026-10-11 rule 3)

Run on this commit, PYTHONPATH=src, `-p no:cacheprovider`:

- Files changed: `pytest tests/bms/test_t005b_fixture_regressions.py tests/bms/test_t005b_plan_blocks.py
  tests/bms/test_t005b_review_once.py -q -n 2` -> `25 passed in 3.05s`
- `pytest tests/bms -q -n 2 -p no:cacheprovider` (one run, not chunked):
  `6 failed, 2526 passed, 2 skipped, 178 warnings in 404.84s (0:06:44)`
  - **tests/bms pass count: 2526.**
  - All 6 failures are accepted baseline: the 5 `test_ai.py` chat tests and `test_review_final3` resource code.
    `test_status_review` and the revert_audit tests passed this time.
