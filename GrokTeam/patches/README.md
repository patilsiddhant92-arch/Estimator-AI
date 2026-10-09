# Builder patches, 2026-10-09 (test job run follow-ups)

Proposed fixes for six app bugs found on the 2026-10-09 test run, plus patch 07 for the estimator's rulings and
patch 08 for B-02 (schedule rows become ledger facts).
**Not applied to `src/` and not committed.** Each patch is a unified diff against `src/` at `grok/work` (src
unchanged at @e99d7b9). Each one applies alone, and all eight apply together. Patches 02, 05 and 06 touch
`src/bms/plan.py`, and 02 and 05 touch `src/bms/render.py`, in separate hunks. Patch 07 adds `src/bms/rulings.py`
and hooks it into `src/bms/run.py`. Patch 08 touches `src/estimator/` only (reading/schedules.py,
ledger/facts.py, ledger/passes.py, ledger/seed.py). The planned room-sensor patch (6c) is now numbered 09.
**Dependency: 04 and 08 land together.** Patch 04's schedule cap reads 08's `schedule_qty` facts. 04 still applies
alone (separate files), but its four schedule_qty tests then fail (`Ledger.add` rejects the kind), so `verify.sh`
applies 08 before 04's "after" run. The combined run applies 01 to 08 in order, and they apply cleanly.

Rulings come from `GrokTeam/discussion.md`. **FINAL** means Siddhant ruled: R1 (Q4 / R11) and the standing Q1, Q2,
Q7 and Q11. **PROVISIONAL** means the lead adopted it and Siddhant has not ruled yet: R2 through R6. Every test
docstring says which. R3 (CNT-5) and R5 (condensate pumps) are on the items Siddhant asked to hold. They are coded
as provisional and need his ruling before they land.
Every fixture is invented, with generic tags and no real project data.

How to verify (uses a throwaway worktree and never touches the real `src/`):

    PY=/path/to/python3.13 GrokTeam/patches/verify.sh /tmp/gt-builder-verify   # per-patch, then all together
    cd /tmp/gt-builder-verify && PYTHONPATH=src $PY -m pytest -q -m "not slow" tests   # existing suite, patched
    git -C <repo> worktree remove --force /tmp/gt-builder-verify

The tests are in `GrokTeam/tests/` (their `conftest.py` puts the tree's own `src/` first on `sys.path`).
Run them with `python -m pytest GrokTeam/tests`.

## Results (verify.sh, Python 3.13.5, pytest 9.1.1)

| # | Patch | Test file | Clean src | With the patch alone |
|---|-------|-----------|-----------|----------------------|
| 1 | `01-validate-no-bms-integration.patch` | `test_01_validate_no_bms.py` | 3 failed, 3 passed | 6 passed |
| 2 | `02-plan-front-end-unresolved.patch` | `test_02_plan_front_end_unresolved.py` | 6 failed, 3 passed | 9 passed |
| 3 | `03-ai-evidence-key-sources.patch` | `test_03_ai_evidence_budget.py` | 3 failed, 3 passed | 6 passed |
| 4 | `04-count-overshoot.patch` (+ 08) | `test_04_count_overshoot.py` | 44 failed, 11 passed | 55 passed (04 alone: 4 failed, 51 passed) |
| 5 | `05-omitted-systems-as-exceptions.patch` | `test_05_omitted_systems_as_exceptions.py` | 4 failed, 4 passed | 8 passed |
| 6 | `06-schedule-only-questions.patch` | `test_06_schedule_only_template_lines.py` | 3 failed, 14 passed, 18 xfailed | 17 passed, 18 xfailed |
| 7 | `07-standing-rulings.patch` | `test_07_standing_rulings.py` | 23 failed | 23 passed |
| 8 | `08-schedule-reader.patch` | `test_08_schedule_reader.py` | 10 failed, 2 passed | 12 passed |

With all eight applied, GrokTeam/tests gives 136 passed and 18 xfailed. On clean src, the tests that pass are the negative or
regression cases. They pass both before and after their patch. The tests that fail on clean src are the bug cases.

## The bugs and the fixes

### 1. validate.py `_packaged`: integration lines demanded with no BMS
- **Bug.** A packaged block got three must_fix findings (`The 'comm_wiring' / 'map_points' / 'rep_assist'
  integration line is missing`) even when no source names a BMS. Example: stand-alone controls by the mechanical
  contractor, with no front end anywhere.
- **Fix (owner ruling 2026-10-09: with no BMS, the integration lines are dropped).** The fix applies when
  `job.front_end is None` (no source names a BMS; see patch 2) and the block has none of its integration lines.
  In that case no integration line is asked for and the rule makes no finding.
- **Still enforced.** If a block already has some integration lines, the whole trio is still required (the writer
  found integration evidence). With a BMS named, the trio is still must_fix.
- **Tests.** No BMS gives no integration finding (2 cases). The mechanical contractor's stand-alone controls case
  gives no finding. Negative cases: with a BMS, a missing trio is still must_fix; a partial trio is still must_fix;
  a full trio is clean.

### 2. plan.py `_front_end`: defaults to a new BMS and prints the front end with no source
- **Bug.** With no `front_end` mode fact, the planner set `new-system` ("The plan assumes a new system"). The
  proposal then printed "Front End Web Enabled BMS System" with no source.
- **Fix (owner ruling: with no front-end source, no front-end line is printed).**
  - `plan._front_end` returns `None` and keeps the question, worded as "No front end is printed until this is
    answered".
  - `render._front_end` maps `None` to a new `estimator.scope.FrontEnd` mode, `"pending"`.
  - The writer deletes both template front ends, including their headings and default lines, so the blocks start
    right under "SCOPE OF WORK –".
  - The price sheet has no front-end heading row.
  - `read_scope` reads a proposal with no front-end heading back as `pending`. A stray line still raises
    "sits outside any block".
- **PROVISIONAL R2.** When nothing shows a BMS or a front end (no `front_end` fact and no `integration` fact), the
  scope prints standalone and the planner adds ONE question, word for word: "No BMS or front end is shown in the
  documents; confirm standalone controls." (`plan.STANDALONE_QUESTION`). When a front_end fact shows a BMS but not
  its mode, the new-or-existing question stays, without the "assumes a new system" wording.
- **Tests.** Plan gives `front_end is None`. R2: exactly one standalone question and no other front-end question.
  R2 negative: a BMS fact without its mode asks new-or-existing and not the standalone question. R2 regression
  guard: the standalone blocks still print. Render, price sheet and
  written docx have no front-end heading or line. Negative cases: a sourced mode is still used; the docx reads back.

### 3. ai_evidence.py `NOTES_LIMIT` / `SPEC_LIMIT`: 12,000-character cut drops key sources
- **Bug.** The notes and spec blocks took passages in dossier order until 12,000 characters were used. A passage
  naming the system's own tag (EF-7) could come after pages of passages that only mention "exhaust fan". If it was
  longer than the budget that was left, it was dropped.
- **Fix (design).** The budget now ranks passages:
  - A passage the planner cited, or one that names one of the system's tags or type codes, is a key passage. Key
    passages are always given, always whole, and counted against the budget first.
  - Phrase-only and integration-word passages fill what is left, in dossier order, and are counted in the
    "(N more passages … cut at …)" line as before.
  - Entries are never truncated.
- **Tests.** A late note with the tag is kept. A late spec passage with the tag is kept. Kept entries are whole.
  Negative cases: phrase-only passages still stay within the budget and the cut line still prints; a cited late
  note is given; a small dossier gives everything with no cut line.

### 4. counts.py `_located_count` and counts_text.py `family_pattern`: count overshoot
- **(a) Bug.** A unit's numbered tag on several sheets in different plan groups was counted once per group. A
  riser label on every floor (invented ZR-7) and a phase-2 or roof plan reusing the tags both raised the printed count,
  because `Count.value` takes the highest count.
- **(a) Fix.** A tag that is not counted per place (it is not a type, see `is_type_tag` and `counted_per_place`)
  counts once over all the sheets. Type tags keep the per-group rule.
- **(b) Bug.** A room named after its unit (invented "AHU-9X") matched the family's generic pattern, whose number part
  allowed any letter suffix, so it counted as another AHU.
- **(b) Fix.** The generic number part takes a letter suffix only when the family's own tags have one. A family
  tagged by a bare prefix keeps the old any-tag rule, since nothing is known about its tags.
- **Tests (positive).** A riser label on 3 sheets counts 1. The same tag on a phase plan and a roof plan counts 1.
  A phase-2 plan reusing the VAV-1 and VAV-2 tags counts 2. "AHU-9X" does not fit and is not found in
  "MECH RM AHU-9X". A sheet with AHU-1, AHU-2, AHU-9 plus the room label counts 3.
- **Tests (negative, pass before and after).** One plan group counts once. Two different tags on two sheets count
  2. VAV-1 and VAV-2 on one sheet count 2. A type tag EBB-A on two plans counts 2. A scheduled AHU-9X or AHU-9Y
  still fits and counts 2. AHU-1, AHU-9, AHU-4 (unscheduled, own prefix) and "AHU 12" still fit.
- As instructed, there is no "same tag twice on one sheet counts 2" case (R1: a repeated tag is one unit).
- **PROVISIONAL R3: the schedule count wins.** A unit tag shown on several plans counts its schedule quantity once
  over all sheets: 1 when the schedule lists it once, 2 when the schedule says QTY 2. The new
  `counts.schedule_quantities(family)` reads a per-tag quantity only where it is stated: a family of one unit tag
  whose count comes from a document source that quotes that tag with a stated "QTY n" equal to the count. A
  representative tag with a total ("VAV-1" standing for 5 boxes) gives nothing per tag. A first version without the
  QTY check broke main test `test_the_located_count_reads_labels_as_the_planner_does` (VAV-1 x 5), so the check
  was added. `_located_count(..., schedule)` and the picture count both use it. Type tags are unchanged.
  Tests: QTY 2 on three plans gives 2; listed once on three plans gives 1; a type tag ignores the map;
  `schedule_quantities` for a one-unit family, a many-unit family, this check's own located count and a
  representative tag.
  **What R3 means for CNT-5** (`tests/bms/test_counts.py::test_a_unit_on_two_floor_plans_adds_up_as_the_inventory_counts`):
  its EF-2 is on two floor plans and its schedule lists EF-2 once, so R3 counts it once. The located count is 3
  (EF-1, EF-2, EF-5), equal to the planner's 3, so `ef.value == 4` fails on purpose. The proposed edit is
  `ef.value == 3`, with the located ref added beside S6 and no "other" count. Siddhant asked to hold the CNT-5
  change, so this is provisional.
- **1b: demolition filter (new work, existing to remain, existing to be removed).** A plan tag is in one of three
  states. New work counts. Existing to remain is not counted as a new unit, and its tie-in lines stay where the
  sequence names it. Existing to be removed is out. Per the lead's correction, `(E)` alone means existing (usually
  to remain) and is never a demolition mark. A tag is removed only by `(ER)`, `(D)`, a REMOVE / EXISTING TO BE
  REMOVED keynote on the tag's line, or a demolition sheet (DEMOLITION or DEMO in the title, or numbered MD-x /
  MD###). `(E)` on a demolition sheet is still existing. A bare REMOVE note on a new-work plan ("REMOVE AND REPLACE
  FILTERS AT AHU-9") never drops a unit: an unmarked tag needs EXISTING or (E) on the same line as the remove words.
  New in `counts.py`: `tag_state`, `sheet_marks` (reads the marks from the sheet text into `_Sheet.marks`),
  `demolition_sheet`, `counts_as_new` and `demolition_questions`. `_located_count` and the picture count skip any
  tag that is not new work. `demolition_questions` asks about a tag shown only as removed (counted 0). It also asks
  about a tag drawn dashed only that no schedule lists: that one is still counted and asked, never dropped silently.
  The **schedule cap**: a tag the schedule gives a quantity for never counts above that quantity, type tags
  included.
  Tests: (1) a type tag on a new plan and on its demolition plan counts 1 (a type tag, so this is the filter at work
  and not R3), and the MD series is a demolition sheet whatever its title; (2) a tag only on MD-101 counts 0 with one
  question, and `(D)`, `(ER)`, an EXISTING ... TO BE REMOVED keynote and `(E)` + REMOVE all mark it removed;
  `(ER)` counts as removed (positive); negative: `(E) AHU-9` with no remove keynote is EXISTING (also on a
  demolition sheet), not counted, and not asked as removed; negative: a bare REMOVE note marks nothing; (3)
  REGRESSION GUARD: an existing unit the sequence names is still planned with its sequence refs; (4) 3 placements
  vs schedule QTY 1 gives 1, and the negative with no quantity keeps 3 (REGRESSION GUARD); (5) a dashed-only EF-9
  with no schedule is counted 1 and asked, and the negative (EF-9 on the schedule) is not asked.
  Limits: the sheet text carries no line style, so "dashed" comes only from a picture or fixture mark
  (`_Sheet.marks[tag] = UNKNOWN`), and nothing sets it from a drawing yet (logged as KL-01 in `GrokTeam/bugs.md`).
- **1b follow-ups (this round).**
  - **The cap reads the schedule_qty facts (needs 08).** `run.py` calls `cross_check` inside
    `with counts.scheduled_quantities(counts.ledger_schedule_quantities(ledger)):` (tag -> the schedule row's
    QTY; a context variable read by `cross_check`). This keeps `cross_check`'s signature, which
    `tests/bms/test_contracts.py` pins, and which `test_run_review_detect2` wraps by monkeypatching `run.cross_check`.
    A first version added a `scheduled=` parameter and broke both tests, so it was reworked.
    `family_schedule` takes those for the tags that fit the family. Only when the schedule gives none of them (no
    qty column, so the seed wrote no `schedule_qty`) does it fall back to the count quote's "QTY n"
    (`schedule_quantities`). Tests: facts are read per tag; schedule_qty 1 wins over a quote's "QTY 5" (3
    placements give 1); a unit tag with schedule_qty 2 on 3 plans gives 2; the fallback with no qty column (maker
    facts only) uses "EF-3 QTY 2"; the run.py wiring is in place, and `cross_check` hands the quantities
    to the check inside the context and none outside it.
  - **Questions name the sheet and the reason.** "AHU-9 appears only on demolition sheet MD-101; ...", "...
    demolition sheets MD-1, MD-2", 'EF-4 appears only as removed: on X-901, marked "(ER)"', the remove keynote
    quoted, and "EF-9 appears only drawn dashed, on sheet X-901, and no schedule lists it; ...". The reasons come
    from `mark_reasons` (stored in `_Sheet.reasons`). The text is asserted in the tests.
  - **MD comes only from the sheet-number field.** `demolition_sheet` reads only the catalogue Sheet (title block:
    `number`, `title`), never the plan text. The whole number must be MD-x / MD### (`fullmatch`; "MD-2.1" and
    "MD101" are fine, "MD-1 MOTORIZED DAMPER" is not), and MD in a title means nothing. Negative: a new plan M-101
    carrying MD-1 motorized damper tags marks nothing, counts MD-1 and EF-3 as new, and asks nothing.
  - **DEMO is a whole word, title only.** `\b(?:DEMO|DEMOLITION)\b` on `Sheet.title`. Negatives: DEMONSTRATION
    ROOM and a DEMO LAB room tag in the plan text mark nothing, and a "DEMONSTRATION ROOM FIT-OUT PLAN" title is
    not demolition. Positives: "DEMO PLAN" and "... DEMOLITION PLAN".
  - **Cap question.** When the cap lowers a count and the extra placements are on different new-work floor plans:
    "AHU-9: 3 new placements on sheets M-1, M-2, M-3; schedule qty 1; counted 1. Confirm the schedule quantity."
    (`cap_questions`, raised in `_Check.run` beside the demolition questions). Floors are counted one per plan
    group (`plan_groups`), so two parts of one floor plan are one floor. Repeats on enlarged plans, details,
    risers, sections or demolition sheets are capped silently.
    **How a floor plan is told apart (`floor_plan_sheet`):** from the catalogue's Sheet, which comes from the title
    block. `Sheet.types` is set by `estimator.catalogue.sheet_types.classify_sheet`, which runs
    `assets/reading_lists/sheet_types.json` over the title. A floor plan has "Plans" and none of Schedules, Details,
    Air/Water/Network riser, Control diagrams, Diagrams, Sections and elevations or Demolition. It is also no
    `demolition_sheet`, and its title matches no ENLARGED / ENLARGEMENT / PARTIAL / BLOW-UP / DETAIL / SECTION /
    RISER / "MECHANICAL ROOM" (or equipment, fan, boiler, pump, chiller, AHU room). Enlarged plans have no type of
    their own in sheet_types.json (they are "Plans"), so the title words are what separate them. A sheet the
    catalogue cannot name is never a floor plan (silent).
    Tests: (a) AHU-9 on 3 new floor plans with qty 1 counts 1 and asks, text asserted; (b) negative: floor plan
    plus "ENLARGED MECHANICAL ROOM PLAN" with qty 1 counts 1 and asks nothing. Further negatives: details, riser,
    sections, demolition and partial plans (parametrized); floors within the qty; two sheets of one plan group.

### 5. Omitted systems do not print as exceptions
- **Bug (plan).** `Job.exceptions` came only from the ledger's "exception" notes. A system with no controls in the
  contract (control `none`) was planned as a block, so the plan's exception list was empty.
- **Bug (render).** A system the writer left with no lines became an Evidence Package note only.
- **Fix.**
  - New `render.omitted_exception_text(system, reason)` builds the rules.md "Named exceptions" form:
    `EXCEPTION TO ANY WORK WITH Qty (n) <tags> - <REASON>`. The quantity is always there (owner ruling): the sum of
    the family counts, or `Qty (##)` when a count is unknown. The tags are used if there are any, otherwise the
    system name. The reason is the source's or writer's own words, or left off. No reason wording is invented,
    since R15 is PENDING.
  - `plan._exceptions` adds one exception for every control-`none` system, citing its provider fact, unless a note
    exception already names that system.
  - `render` adds one exception for every system with no devices, unless an exception already names it.
- **Tests.** The NIC system is a plan exception with Qty and tags. A system with no lines prints as an exception.
  Untagged fire/smoke dampers "by others", qty 12, give an exception with `Qty (12)`. Every rendered exception
  carries a Qty. Negative cases: a system with lines is not an exception; a system already excepted prints once,
  and no note-made duplicate is added.

### 6. Schedule-only job (no sequence of operation, no BMS)
Owner rulings 2026-10-09 apply here. The Master Template is the ideal-case checklist only (rules.md "Template is
the ideal case", "No standard or fallback lines"), so **nothing prints by default** and HarkPro C11-C16 are
ignored. The two documented exceptions, Q1 and final R1, are added after the writer by patch 07 (section 7), never
by the planner. The original 6a ("required template lines always print") was reversed by the owner and replaced.

The fixture is an invented schedule-only ledger: IDU, VAV, UH, EF, ACU and MD families, plus WM (R4), RLD (Q11)
and CP (R5). It has
no sequence, no `front_end` fact and no BMS. Line wording is read from `HarkPro/doctrine/lines.json`, read-only.

- **REGRESSION GUARD** marks a test that already passes on current code. It pins behaviour and is not a bug proof.
- **xfail(strict=True)** marks a test with a design note and no patch. It turns into a failure the day the
  behaviour lands, so the mark has to be removed then. Every xfail names the error it expects (`raises=`):
  `ModuleNotFoundError` for the 6f tests that import the proposed `bms.supported`; `ImportError` for a missing name
  in an existing module (6c `attach_symbols`, 6f(iii) `trace_riser_dampers`); `AssertionError` where the assert
  decides (6a question, 6e, the 6f(i) bare note). Each fixture is built before the proposed import. Checked on a
  throwaway copy: with every fixture deliberately broken (TypeError/NameError), all 22 fixture-using tests in
  test_06 FAIL loudly (none xfails quietly). The 6f(iii) fixture was checked on its own and fails too.

**6a (revised twice).**
- *A template device the documents support prints with its schedule quantity and owner.* REGRESSION GUARD.
  Current render prints `Install and Wire Space Thermostat (Furnished by Unit Mfr.)` with quantity 2.
- *Negative: no template line prints by default.* REGRESSION GUARD. The planner writes no line, and a Device with no
  citation raises `ModelError`. The current code already behaves this way, so there is no patch for that half.
- **Live test:** *an unsupported template device (a VAV space temperature sensor on a schedule-only job) becomes a
  planner question and does not print.* xfail(strict). The "does not print" half holds today. The question does
  not exist yet. Design note: the planner has no ideal-case checklist to compare the documents against.
  `shapes.json` says "Never content", and its slots are not a list of template devices. Two possible checklist
  sources: a curated per-shape `checklist` in the app's Playbook (owner-approved, from lines.json
  `required: true`), or reading lines.json directly, which couples the app to HarkPro. The question form would be
  "<tags>: the documents do not show <device>; is it in scope?". The owner has to choose the source and keep the
  list short. The VAV DDC controller is final ruling R1, a documented default in patch 07 (test_07).
- *Negative: a supported template device raises no question.* REGRESSION GUARD.

**6b (PROVISIONAL R6): an actuator with no named furnisher prints and is not asked about.** R6 reverses
revision 2 ("documents silent: a question, no line"). Patch 06 no longer asks the damper question. Patch 07 prints
`Wire Damper Actuator (Furnished by Others)` (test_07). Planner tests: documents silent raise no actuator question
(REGRESSION GUARD); a named furnisher raises none (REGRESSION GUARD).

**6c (reworked): a room sensor belongs to the unit that serves its room, never to the nearest tag.**
- **Finding: the link does not exist today.**
  - The schedule reader (`src/estimator/reading/schedules.py`) keeps tags and rows. It has no area-served, room or
    serves field.
  - The ledger kinds (`src/estimator/ledger/facts.py:13`, `KINDS`) include `location` (the plans pass, free-text
    floors, zones and rooms, `passes.py:63`) and `link` (served unit <- serving unit, for dampers and risers,
    `passes.py:78`). There is no area-served kind.
  - `plan.py` `_SERVES` (line 69) and `Served` tie duct heaters only. Location facts are used only for naming
    (`plan.py:375`) and heater ties (`plan.py:683`).
  - The counts read tags only.
- **Proposed.** A ledger kind `area_served` (subject the unit tag, value the schedule cell). Patch 08 now delivers
  this kind, seeded from the schedule row; its test moved to test_08. Still proposed, as patch 09:
  `bms.counts.assign_room_sensors(sensors, area_served, units)`, which returns (sensor id -> unit tag, questions).
  Rooms match on their number when they have one, with leading zeros and case ignored ("Lounge 907" ==
  "LOUNGE 0907"). The name is only a fallback. Never by drawing distance and never by duct colour. The tests give
  the link as fixture data.
- **Tests, all strict xfail with no patch:**
  - (a) a CO2 sensor in LOUNGE 9 goes to AC-9-1, scheduled for LOUNGE 9, though a VAV tag is nearer;
  - (b) a sensor in OFFICE 9A stays with VAV-9-2;
  - (c) a room no unit serves gives one confirm question and never the nearest tag;
  - (d) a tie (AC-9-1 "Lobby & Lounge" and VAV-9 "Lounge") goes to neither, with one confirm question naming
    both;
  - (e) a number match ignores leading zeros and case;
  - (f) "Studio" 0907 vs "Media Studio" 0407 never match.
  Tests (a) to (f) use `raises=ImportError`. Every tag and room in them is invented.

**6d (PROVISIONAL R4): equipment with no template family is never dropped silently.** **Patched**
(`plan._unplaced_questions`). It asks "No template family fits <system> (<tags>); is it in AME's scope? If not, it
is a named exception", only when there is no sequence passage and no other question already names the system. The
fixture is now an invented water meter (WM). A refrigerant leak detector is not asked about (standing Q11: AME
furnishes it; REGRESSION GUARD). Negatives: it is still planned; a family with a shape raises no such question.

**R5 (PROVISIONAL): a stand-alone condensate pump.** **Patched** (`plan._unplaced_questions`). The planner asks
only when a document (a ledger fact or a dossier text naming the pump's tag or prefix) shows an alarm or interlock
for it. Positives: "CP-21 HIGH WATER ALARM TO BMS" and "CP-21 INTERLOCK WITH AC-21 SHUTDOWN". Negatives
(REGRESSION GUARDs): no alarm gives no question; an alarm on another unit gives no question. This restores main
`test_final_b::test_condensate_pumps_with_no_split_units_are_left_as_they_are`. Siddhant asked to hold the
condensate change, so this is provisional.

**6e.** *A printed line that hits a house exclusion (gas detection) is flagged.* xfail(strict). Design note: the
app has no house-exclusion list. The owner has to provide one (proposed: a `wording.json`
`house_exclusions` list, plus a validator check under a new rules.md heading). Negative: an ordinary line is not
flagged (passes before and after).

**6f: devices the documents support are not written.** The AI writer (`bms.ai.write_system`) writes the lines
from each system's evidence, and the planner writes none by design. Each case is tested in two halves.
1. Does the supporting passage reach the system's evidence? This runs on current code.
2. The proposed deterministic step `bms.supported.supported_lines(job, dossier_text)` turns the passage into the
   line. This is xfail(strict) with a design note.

Each note fixture has two wordings with the same meaning, so a patch that matches one exact string fails. Each
positive has a negative where the item goes to someone else.
- (i) VRF thermostat by the unit maker. The `_vrf_job` fixture is a no-BMS VRF with control `field` (AME installs
  and wires the maker's thermostats), not `integration`.
  - A detail note that names the indoor unit reaches the VRF evidence. REGRESSION GUARD.
  - **Finding:** a bare detail-sheet note ("T-STAT SUPPLIED BY UNIT MFR.") names no tag and no system phrase, so
    `ai_evidence` never gives it to the writer. This is the likely root cause. xfail(strict). Design note: give a
    detail-sheet note that names a device word of the shape's slots (thermostat or t'stat, transformer, damper)
    to each system whose shape has that slot, under a budget like patch 03's.
  - Both wordings ("T-STAT SUPPLIED BY UNIT MFR.", "THERMOSTAT FURNISHED BY EQUIPMENT MANUFACTURER") give one
    Install and Wire thermostat line furnished by the Unit Mfr., with quantity = N indoor units. xfail(strict).
  - "THERMOSTAT BY OTHERS" names only the furnisher. It must give a planner question about install and wire, never
    a silent drop, and no AME-furnished thermostat line. xfail(strict).
  - True negative: "THERMOSTAT FURNISHED, INSTALLED AND WIRED BY OTHERS" gives no AME line. xfail(strict), because
    it uses the same proposed API, which returns `(lines by system key, questions)`. It goes live when the API
    lands.
- (ii) VAV 24V transformer.
  - The schedule's own note reaches the VAV evidence. REGRESSION GUARD.
  - Same meaning, two wordings: "PROVIDE 24V TRANSFORMER" and "24V CONTROL TRANSFORMER FURNISHED WITH UNIT" (the
    box maker furnishes it; a VAV schedule note is the maker's, R10). Both give one 24V line furnished by the
    Unit Mfr. xfail(strict).
  - A separate ownership case: "24 VAC TRANSFORMER BY CONTROLS CONTRACTOR" gives one 24V line furnished by AME,
    and the test asserts its owner differs from the unit case. xfail(strict).
  - True negative: "24V TRANSFORMER FURNISHED, INSTALLED AND WIRED BY OTHERS" gives no AME line. xfail(strict).
  - With no note, no 24V line. REGRESSION GUARD.
- (iii) An outside-air damper on a riser is traced to the unit it serves. xfail(strict). Design note: there is no
  riser tracing. A riser's duct-run labels would link a damper to the unit on the same run (proposed
  `bms.counts.trace_riser_dampers`), feeding rules.md "Dampers under their fan".
- Why there is no patch for the writing half: lines that come from notes without the AI writer would mean a
  deterministic phrase-to-line table. That needs owner-approved vocabulary (party words, device words). A
  string-matching patch is what the reworded fixtures are designed to reject.

Side observation (not patched): in the 6a fixture, the planner gives `IDU` (named "VRF Indoor Unit") the
`VRF System` shape but control `field`, not `integration`. Estimator QA may want to check this.

### 7. Rulings on the written system (`07-standing-rulings.patch`, new `src/bms/rulings.py`)
`apply_rulings(system, evidence, playbook)` is pure. `bms.run` calls it on every written system and on every
count rewrite, before `flag_written_devices`. An estimator's delete of a ruling line stays deleted: line ids are
fixed (`<key>.dd<n>`, `<key>.r6`) and `keep_deleted` matches by content after a rewrite.
- **`DOCUMENTED_DEFAULTS`: one table, exactly two entries,** the only exceptions to "No standard or fallback lines".
  Each entry holds the system family (shape), the template line and its lines.json id, the parties, a quantity
  rule, its own override check (a document gives the item to someone else) and a citation to discussion.md:
  - Q1 (standing): VRF System, "VRF Communication Wiring" (vrf_system.05), AME, one per system. The override is
    control or communication wiring "by" anyone but AME or the controls contractor.
  - R1 (FINAL, Q4 / R11, 14:50 IST): VAV / Fan VAV, "Furnish DDC Controller to the Factory for Installation"
    (vav.01), furnished by AME and installed and wired by the Unit Mfr. Its quantity is the VAV family count. The
    override is controls or a controller "by" anyone but AME or the controls contractor. The old provisional R1
    question is removed.
  - A default is added only when the writer left that slot empty, the override does not match, and a family count
    source can be cited.
- **R6 (PROVISIONAL), Motorized Dampers blocks only.** A written actuator whose cited quotes name no party becomes
  Wire / Others / Others / AME. A block the writer left with no actuator line gets "Wire Damper Actuator (Furnished
  by Others)", citing the family count and the evidence passages that name its tags. It gets no line when a cited
  passage names a furnisher.
- **Q2 (standing), VRF.** A central-controller line is removed (OEM / vendor scope). A remote-controller line
  becomes "Install and Wire Programmable Thermostat (Furnished by Unit Mfr.)".
- **Q7 (standing).** "w/ End Switch" stays only when a cited quote says end switch. An `end_switch_status` line
  without one is dropped. The R6 line gets "w/ End Switch" only when its citations call for one.
- **Q11 (standing, read narrowly).** A line whose cited quote says "provide" and names no party becomes Furnish
  and Install, AME, only for a control device: a sensor, detector (the ruling's leak detector), thermostat, switch,
  transmitter and the like. Never for a damper, a louver or equipment (fan, pump, unit, valve, panel...), even one
  whose name carries a device word ("Condensate Pump w/ Float Switch").
- **Tests** (23, all failing on clean src and passing with 07):
  - a guard that the table holds exactly the Q1 and R1 entries, each citing discussion.md;
  - R1 (a): 3 VAVs print the line with Qty 3; (b) "CONTROLS BY VAV MANUFACTURER" and "VAV BOX CONTROLS BY OTHERS"
    print no default; (c) no non-VAV system gets it; no doubling;
  - R6: documents silent print the Wire line; a guessed AME actuator becomes Wire by Others; a named furnisher is
    left alone;
  - Q1: a VRF system gets it; (a) no non-VRF system does; (b) "CONTROL WIRING BY VRF MANUFACTURER" and "VRF
    COMMUNICATION WIRING BY DIV 26" print no AME default;
  - Q2: central controller removed; remote controller becomes the thermostat; a correct thermostat is unchanged;
  - Q7: the positive, the negative and a kept end switch;
  - Q11: the leak-detector positive and a negative ("FURNISHED BY VRF MANUFACTURER"); a sensor positive
    ("PROVIDE SPACE TEMPERATURE SENSOR"); negatives "PROVIDE MOTORIZED DAMPER", "PROVIDE LOUVER" and
    "PROVIDE CONDENSATE PUMP W/ FLOAT SWITCH" do not become AME scope.
- **Wording choice for Siddhant (R6).** Patch 07 prints "Wire Damper Actuator (Furnished by Others)", the Master
  Template's device name (motorized_dampers.01, "Damper Actuator") under the Wire verb. The Proposal's own form is
  "Wire Motorized Damper ... (Furnished by Others)". Both carry the same ownership. Which device name prints is
  Siddhant's call; it is one constant (`rulings.DAMPER_ACTUATOR`) and the two R6 / Q7 printed-text asserts in
  test_07.

### 8. B-02: schedule rows become ledger facts (`08-schedule-reader.patch`)
- **Where it is lost.** `estimator.reading.schedules` does read the rows (tag, cells, manufacturer). But a
  "CONTROLS BY / NOTES" column was not taken as the remarks column (only a header that *is* NOTES or REMARKS
  counted), so the controls owner in it was lost. The drawing's revision block (MARK | DATE | DESCRIPTION) came back
  as an untitled schedule. The dossier prints every row, but `estimator.ledger.seed` read only the count lines
  (section 5), so no scheduled tag got a fact of its own.
- **Fix.**
  - `reading/schedules.py`: a remarks column is any header with a notes word in it, or CONTROLS BY / FURNISHED BY.
    A table keyed by MARK whose other headers are DATE / DESCRIPTION / REVISION / BY and the like, with no tagged
    rows, is a revision block and is dropped.
  - `ledger/facts.py`: new seed-only kinds `schedule_qty`, `maker` and `area_served` (`SCHEDULE_KINDS`). The AI
    passes keep their kinds (`PASS_KINDS`), so `passes.schema()` is byte-identical and cached pass answers stay
    valid.
  - `ledger/seed.py`: `schedule_row_facts` reads the dossier's section 4 and writes one fact per scheduled unit
    tag, citing the row's own line. A QTY column gives `schedule_qty`, a manufacturer column gives `maker`, and
    AREA SERVED / SERVES / ROOM / LOCATION gives `area_served`. The owner becomes a `provider` fact (ADDED, for the
    schedules pass to confirm). It is read from a CONTROLS BY / NOTES / REMARKS cell that names a party ("DDC BY
    UNIT MFR"), or from the schedule note a "SEE NOTE n" cell points to, citing that note. No column means no
    fact. A remarks cell naming no party ("PROVIDE WITH DISCONNECT") gives no owner, and rows without a unit tag
    (types, revision rows) give nothing.
- **Tests** (invented PDF page: AHU-1..AHU-3 with TAG, QTY, MANUFACTURER, MODEL, AREA SERVED, CONTROLS BY / NOTES,
  a note 1, and a revision block). The reader reads the rows (REGRESSION GUARD). The revision block is not a
  schedule. CONTROLS BY / NOTES is the remarks column. Then the facts: qty, maker, area served, the owner from the
  cell and from note 1, and every fact cites its row or note. Negatives: a party-less remarks cell gives no owner
  (REGRESSION GUARD), no QTY column gives no qty facts, and revision rows give no facts. Finally, the kinds exist
  and the AI pass enum is unchanged.
- **Effect on the planner.** The planner already reads `provider` facts named by a unit: one that says the unit
  maker (`_MAKER`) makes the unit's control `packaged`. That is B-02's "unit-furnished owner". The new kinds are
  not read by the planner yet. The count anchor (`schedule_qty` into `counts.schedule_quantities`) and room
  sensors (patch 09) are the next steps.

## Existing suite (`tests/`, `-m "not slow"`, on this Linux box)
- **Clean src (baseline):** 9 failed, 3735 passed, 10 skipped. The failures are environmental and not caused by
  these patches: 5 chat tests in `test_ai.py`, the Windows resource-code test in `test_review_final3.py`,
  `test_assets.py::test_running_on_the_project_python`, and 2 `test_main.py` file tests.
- **All eight applied (this round, after the step-1 follow-ups):** 17 failed, 3727 passed, 10 skipped, 19
  deselected. These are the 5 intentional contradictions plus environmental failures that also fail on a clean
  tree: 5 `test_ai` chat tests, `test_review_final3`, `test_assets`, 2 `test_main` and 3 `test_revert_audit*`.
  `test_status_review::test_every_normal_exit...` flaked once (it failed on clean src and passed with the patches
  on rerun). `test_contracts::test_signature[cross_check]` and `test_run_review_detect2` pass again after the
  context-variable rework.
- **All seven applied (previous round):** 17 failed, 3727 passed, 10 skipped, 19 deselected.
  - The 5 intentional contradictions listed below.
  - 3 flaky `test_revert_audit*` tests, which also fail on clean src on rerun.
  - The 9 baseline environmental failures. `test_ai::test_every_cleanup_is_logged_beside_the_cache` also fails on
    clean src here.
  - `test_final_b` condensate passes again (R5).

## Existing tests these patches intentionally contradict (they need the owner's decision; we cannot edit tests/)

1. `tests/bms/test_plan.py::test_an_existing_system_is_named_and_a_missing_mode_is_asked` (patch 02, R2). It
   asserts `job.front_end.mode == "new-system"` and a "new or extends" question for an empty ledger. With patch 02
   the front end is None, and under R2 the empty ledger gets the standalone question. Proposed edit:
   `assert job.front_end is None` and `plan.STANDALONE_QUESTION in job.questions`.
2. `tests/bms/test_counts.py::test_a_unit_on_two_floor_plans_adds_up_as_the_inventory_counts` (CNT-5; patch 04,
   PROVISIONAL R3). See section 4. Proposed: `ef.value == 3`. On hold for Siddhant.
3. `tests/bms/test_plan.py::test_a_plan_only_split_unit_keeps_its_existence_question_in_the_block` (patch 06, R4).
   The test's sample Playbook has no Split shape, so the block also gets "No template family fits". The repo
   Playbook has a Split shape.
4. `tests/bms/test_review_final.py::test_a_delete_saved_with_a_family_count_change_stays_deleted` (patch 07, FINAL
   R1). The deleted sensor stays deleted, which is the test's point. The VAV block now also carries the R1 line
   "DDC Controller to the Factory for Installation", so `devices == []` fails. Proposed: assert that no sensor line
   is left.
5. `tests/bms/test_final_fixes.py::test_a_delete_saved_after_a_change_and_a_count_change_stays_deleted` (patch
   07, FINAL R1). Same cause: `VAV.dd2`, the R1 controller, is left. Same proposed edit.

No longer contradicted: `tests/bms/test_final_b.py::test_condensate_pumps_with_no_split_units_are_left_as_they_are`
(R5 asks only on an alarm or interlock).

## Open doubts
- Cap question: the floor-plan test is a title word list. A floor plan titled e.g. "LEVEL 2 MECHANICAL ROOM AND
  CORRIDOR PLAN" would be taken as enlarged (silent cap). A plan group from `plan_groups` with typical floors (one
  sheet for many floors) counts as one floor.
- 1b: a dashed-only tag that no schedule lists stays counted and asked. Under "an undercount is the worst failure"
  it is never dropped, but if it really is existing, the count overshoots by one until the estimator answers.
  Which way to lean is Siddhant's call. A removed-only tag counts 0 and is asked.
- 1b: a tag on a demolition sheet with no mark at all counts as removed. Demolition plans sometimes show existing
  equipment to remain without "(E)" or TO REMAIN. That is still safe for the count (0 new) but could ask a "shown
  only as removed" question about a unit that stays. The planner keeps its system either way.
- 08: the owner words (`seed._OWNER_WORDS` plus the schedules vocabulary's controls phrases) are a first cut; a
  remarks cell such as "FACTORY MOUNTED DISCONNECT" is not an owner, but "FACTORY MOUNTED CONTROLS" is.
- 08 leaves the revision-block rule in code, not in `assets/reading_lists/schedules.json` (assets are out of bounds).
- Bug 1 and bug 2 use one signal: `Job.front_end is None` means no source names a BMS. That covers both "the
  documents say nothing" and "the extraction missed it". The front-end question on Review.html is the safety net.
- Bug 2 adds the `"pending"` mode to `estimator.scope.FrontEnd`, which the old estimator path shares. The reader
  accepts a scope with no front-end heading only when the next paragraph is a block header or "ADD ALTERNATES:".
- Bug 3 keeps key passages without limit. A system with a very large number of tagged notes could produce a long
  prompt. A hard ceiling (for example 3x the limit) could be added if that shows up.
- Bug 5: if the AI writer later writes lines for a control-`none` system, it would show as both a block and a plan
  exception. Validate could flag that.
