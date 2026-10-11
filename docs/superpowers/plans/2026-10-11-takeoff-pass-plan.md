# Takeoff pass (Option A): implementation plan

**Goal.** Add one whole-job AI step. It reads the ledger and every sheet. It returns a register: what each sheet is,
which units exist, and which counts are set aside. Stage 1 adds the step and stores the register, and no count
changes. Stage 2 makes the register binding: "highest prints" stays, but only over the sources the register allows.
Every excluded count stays visible with both numbers and its reason.

**Base.** `lead/wave2` (0e78113). Stage 1 branch: `takeoff/s1` from `lead/wave2`. Stage 2 branch: `takeoff/s2` from
`rebuild` after HarkPro T-005a..e merge.

**Rules for every task.** Write the test first. Use invented fixtures only. Do not start subagents or multi-agent
review skills (no /code-review or /simplify fan-out). Run Python as `.venv\Scripts\python.exe` with `PYTHONPATH=src`.
Proof command (task tests): `.venv\Scripts\python.exe -m pytest <files> -q -p no:cacheprovider`.

**Files.**
- New: `src/bms/takeoff.py`, `src/bms/prompts/takeoff_job.md`, `tests/bms/test_takeoff.py`,
  `tests/bms/takeoff_fixture.py`, `tests/bms/fixtures/takeoff/` (four JSON files).
- Lead-owned (the lead reviews these diffs first): `src/bms/model.py`, `src/bms/run.py`,
  `tests/bms/fixtures/sample_job.json`, `tests/bms/test_contracts.py`, `docs/superpowers/specs/2026-10-04-rebuild-interfaces.md`.
- Stage 1 small edits: `src/bms/status.py`, `tools/run_job.py`, `.claude/skills/run-job/SKILL.md`, `src/bms/review.py`
  (one dict entry), and the test answerers in `tests/bms/test_run.py`, `test_run_front_end.py`,
  `test_run_revise_count.py`, `test_review_019b.py`, `test_final_fixes.py`, `tests/test_whole_job.py`.
- Stage 2: `estimator/reading/inventory.py`, `bms/plan_read.py`, `bms/plan.py`, `bms/counts.py`,
  `bms/ai_evidence.py`, `bms/ai.py`, `bms/prompts/write_system.md`, `bms/render.py`, `bms/evidence.py`,
  `bms/review.py`. HarkPro edits these too, so each Stage 2 line reference is marked **(may have moved)**.

---

## Stage 1: additive only

### Task 1.1 (lead-owned): model fields. 3 h, Sonnet; the lead reviews

File: `src/bms/model.py`.

Test first, in `tests/bms/test_contracts.py`:
- `test_enumerations_are_the_design_values`: change the FLAGS line to
  `("none", "quantity", "ownership", "assumed", "future")`. Add asserts for `SHEET_KINDS`, `UNIT_STATUSES`,
  `SET_ASIDE_REASONS` with the exact tuples below.
- `test_takeoff_fields_round_trip`: `Job.from_dict(raw)` keeps one `SheetClass`, one `Unit`, one `SetAside` and one
  `FutureItem` from the fixture; `Job.from_json(job.to_json()) == job`.
- `test_old_job_without_takeoff_fields_loads`: delete the four keys from `raw` and load it. All four are `()`.
- `test_unit_needs_a_ref`: a `Unit` with `refs=()` raises `ModelError`.

Code. Add after `DecisionAction` (`model.py:33`):

```python
SheetKind = Literal["new_work", "demolition", "part_plan", "enlarged_plan", "riser", "schedule", "detail",
                    "control_diagram", "other"]
UnitStatus = Literal["new", "demolish", "demolish_with_work", "existing_remain", "relocate", "future"]
SetAsideReason = Literal["demolition sheet", "same unit labelled again", "part plan of one area", "future item",
                         "existing to remain", "not a unit of this family"]
```

Change `Flag` (`model.py:27`) to end with `"future"`. Add the tuples `SHEET_KINDS`, `UNIT_STATUSES`,
`SET_ASIDE_REASONS` beside `FLAGS` (`model.py:42`), and `COUNTED_STATUSES = ("new", "relocate")`. Add these classes
before `Job`, each `@dataclass(frozen=True)` on `_Model`, with `_doc` texts:

```python
class SheetClass(_Model):
    document: str
    page: int
    number: str                       # "" when the sheet has none
    kind: SheetKind
    area: str                         # plain words; one area name for every sheet of one place; "" off plans
    counts_units: bool                # units and devices drawn here count for this job
    reason: str                       # one short sentence
    refs: tuple[Ref, ...] = ()

class Unit(_Model):
    family: str                       # the ledger family prefix, "AHU"
    tag: str                          # as the schedule prints it; a type tag ("FCU-1") for a typical unit
    labels: tuple[str, ...]           # every label the sheets show for it
    status: UnitStatus
    count: int                        # 1 for a numbered unit; the places for a type tag
    sheets: tuple[str, ...]           # the counted sheets it is drawn on
    refs: tuple[Ref, ...]             # at least one (ModelError otherwise, as Device does)
    serves: str = ""                  # the unit it serves ("AHU-2" for a valve)
    service: str = ""                 # "chilled water", "hot water"; "" when none
    reason: str = ""

class SetAside(_Model):
    family: str
    value: int
    ref: Ref                          # the source of the number that is set aside
    reason: SetAsideReason
    note: str = ""                    # both numbers in plain words

class FutureItem(_Model):
    family: str
    item: str                         # "outside airflow measuring station"
    refs: tuple[Ref, ...]
```

Add to `Job`, after `source_sheets` (`model.py:249`): `sheets: tuple[SheetClass, ...] = ()`,
`units: tuple[Unit, ...] = ()`, `set_aside: tuple[SetAside, ...] = ()`, `future_items: tuple[FutureItem, ...] = ()`.
Append the four classes to `MODEL_CLASSES` (`model.py:292`) and the new names to the module's export list.

Fixture: in `tests/bms/fixtures/sample_job.json`, add one entry to each new key. Use the existing sources (`S1`,
"Drawings.pdf", page 2). Sheet `M-101` is `new_work`, area "Level 1", `counts_units` true. Unit `EF-1` is `new`,
count 1. The set-aside is reason "demolition sheet", value 2. The future item is "outside airflow measuring station".

Proof: `pytest tests/bms/test_contracts.py`. Then `pytest tests/bms -q -n 10 -m "not slow"`. A writer-schema test may
now show `"future"` in the flag enum; update its expected list only.

### Task 1.2 (lead-owned): the invented takeoff fixture. 4 h, Sonnet; the lead reviews

New folder `tests/bms/fixtures/takeoff/`. The job is "Invented Hall", job number `00-1111`. The document is
`Mech.pdf`. Every name and number is invented.

`sheets.json`: a list of `{page, number, title, types, text}`. Each `text` holds one label per line.

| page | number | title | types | labels in `text` |
|---|---|---|---|---|
| 1 | M-601 | MECHANICAL SCHEDULES | Schedules | (none) |
| 2 | M-401 | MECHANICAL NEW WORK DUCTWORK ATTIC PLAN | Plans | AHU-1..5, EF-1..5, ERU-1 |
| 3 | M-402 | MECHANICAL NEW WORK PIPING ATTIC PLAN | Plans | AHU-1..5, ERU-1 |
| 4 | M-403 | MECHANICAL NEW WORK EQUIPMENT ATTIC PLAN - PART A | Plans | AHU-1, 2, 3; EF-1, 2, 3 |
| 5 | M-404 | MECHANICAL NEW WORK EQUIPMENT ATTIC PLAN - PART B | Plans | AHU-3, 4, 5; EF-3, 4, 5; ERU-1 |
| 6 | MD-401 | MECHANICAL DEMOLITION DUCTWORK ATTIC PLAN | Plans, Demolition | AHU-1..5, (D)AHU-6, EF-1..5, (D)EF-6 |
| 7 | M-201 | MECHANICAL NEW WORK FIRST FLOOR PLAN | Plans | FCU-1 x25, T x14 |
| 8 | M-202 | MECHANICAL NEW WORK SECOND FLOOR PLAN | Plans | FCU-1 x30, T x16 |
| 9 | MD-201 | MECHANICAL DEMOLITION FIRST FLOOR PLAN | Plans, Demolition | T x9 |
| 10 | M-701 | CONTROL DIAGRAMS | Control diagrams | "AHU OUTSIDE AIRFLOW MEASURING STATION (FUTURE)" |

`reading.json`:
- `schedules`: one schedule on M-601, "AIR HANDLING UNIT SCHEDULE", rows AHU-1..5. Also an exhaust fan schedule with
  rows EF-1..5, an ERU schedule with row ERU-1, and an FCU schedule with one row FCU-1 and a blank QTY.
- `devices`: the `DeviceCount` rows for label `T`, device "Thermostat": 14, 16 and 9 on pages 7, 8 and 9.
- `notes`: one keynote on MD-401, "EXISTING AHU-6 AND EF-6 TO BE REMOVED", with `controls` false.

`ledger.json` (the `Ledger.to_dict` form, `complete` true):
- The schedules pass settles family, unit and count facts: AHU 5, EF 5, ERU 1, FCU 1.
- The plans pass adds a note: "AHU-6 and EF-6 are existing units shown for demolition only".
- It adds a note about FCU-1: "FCU-1 is a typical unit drawn 25 times on M-201 and 30 on M-202".
- The sequence pass adds a question note: the AFMS is marked future.
- `understanding.plans`: one invented sentence saying five new air handlers and five exhaust fans.

`answer.json`: the correct register for this job.
- Sheets: M-401..M-404 have area "Attic", `counts_units` true. MD-401 and MD-201 are `demolition` with
  `counts_units` false. M-201 and M-202 are areas "Level 1" and "Level 2".
- Units: AHU-1..5 `new`, AHU-6 `demolish`, EF-1..5 `new`, EF-6 `demolish`, ERU-1 `new`, and FCU-1 `new` with count
  55. Each cites a ledger fact by its id.
- Set-asides: none (the code works out the excluded sheet counts in Stage 2).
- Future items: one, "outside airflow measuring station", which cites the question fact.

`tests/bms/takeoff_fixture.py`:
- `catalogue()` builds the `Catalogue` as `tests/test_inventory_same_floor.py:126-138` does. Its `TagEntry` list
  holds every label except `T`.
- `reading()` is a `SimpleNamespace(schedules=..., devices=..., notes=..., typicals=(), totals=())`, built from
  `estimator.reading.schedules.Schedule`, `ScheduleRow`, `estimator.reading.devices.DeviceCount` and
  `estimator.reading.keynotes.Note`.
- `ledger()` is `Ledger.from_dict(...)`.
- `dossier()` is a `Dossier` with `sources` equal to the ledger's sources, and `sheet_pages` mapping one 7c id per
  sheet.
- `answer()` loads `answer.json`.

Proof: `pytest tests/bms/test_takeoff.py -k fixture`. The test
`test_fixture_reproduces_the_defect` builds the Job with `plan_job(ledger(), catalogue(), dossier(), PLAYBOOK)`
(sample playbook). It asserts that the AHU count is above 5 and the EF count is above 5. Record the exact numbers
as a characterisation in the test.

### Task 1.3: `src/bms/takeoff.py`. 8 h, Sonnet

Tests first, in `tests/bms/test_takeoff.py`. Use a fake transport like `tests/bms/test_ai.py`'s: it answers
`answer()` and records the request.
1. `test_the_request_carries_the_whole_job`: kind `"takeoff_job"` and extra `{"step": "takeoff"}`. The prompt holds
   every fact line (`Fact.line()`), every understanding paragraph, all 10 sheets, the M-601 rows, the MD-401
   keynote, and the thermostat counts. Instructions are `playbook.rules_text`. The system prompt is
   `prompts/takeoff_job.md`.
2. `test_the_prompt_is_the_same_twice`: two builds give equal text, so the cache key stays stable.
3. `test_a_good_answer_loads`: `take_off(...)` returns a `Takeoff` with 10 sheets and 14 units, and the units
   round-trip through `Unit.to_dict` and `Unit.from_dict`.
4. Refusals: each of these makes `check_answer` return a problem that names the item:
   - a sheet left out, a sheet given twice, or an unknown sheet;
   - a plan-kind sheet with no area;
   - a scheduled tag (AHU-4) with no unit row;
   - a unit ref whose source id the ledger does not know, or whose quote is not in that fact or source;
   - a demolition sheet with `counts_units` true and no ref;
   - two rows for one (family, tag);
   - `serves` naming no unit;
   - a set-aside whose ref is unknown.
5. `test_the_schedule_is_the_floor`: AHU-5 with status `demolish` and `reason` "" is refused. With a reason and a
   ref, it is kept.
6. `test_counts_do_not_change`: `attach(job, takeoff)` changes only the four new Job fields. Every
   `family.count` is equal to the count before attach.
7. `test_save_and_load`: `save(takeoff, path)`, then `load(path) == takeoff`.

Code:
- `TAKEOFF_JOB = "takeoff_job"`. `TAKEOFF_LIMIT = 600_000` characters. A longer prompt raises `ValueError`
  ("Stopped: the takeoff request is too long (N characters) ..."). Never cut it in silence.
- `@dataclass(frozen=True) class Takeoff`: `sheets`, `units`, `set_aside`, `future_items` (the model tuples) and
  `questions: tuple[str, ...]`.
- `answer_schema()`: an object with those five arrays. The item schemas are `json_schema(SheetClass)` and so on.
  `questions` is an array of strings. All five keys are required, and `additionalProperties` is false.
- `prompt(ledger, catalogue, reading, dossier) -> str`. Sections, in this order, each with a heading line:
  1. "Ledger facts": `ledger.table()`.
  2. "What each reading pass understood": `- <pass>: <text>` lines.
  3. "Sheets": the sheets of `CONTROLS_DISCIPLINES`, sorted by (document, page), one line each:
     `<document> | page <n> | <number or -> | <title> | code guess: <types or none> | text: <7c id or -> | labels: <TAG xN, ...>`.
     The labels come from `estimator.catalogue.tags.line_labels(page.text, label_keys(t.tag for t in catalogue.tags))`.
  4. "Schedules": each schedule's sheet and title, then `TAG: col=value; ...` rows.
  5. "Notes on the sheets": `<sheet> <block> <number>: <text>`.
  6. "Sequence sections": `<Q id>: <heading>` from `dossier.sections`.
  7. "Devices counted on the sheets": `<sheet> <device> (<label>) <count>`.
- `check_answer(answer, ledger, catalogue, reading, index) -> (Takeoff | None, problems)`:
  - run `schema_errors` first;
  - build with each class's `from_dict`, which turns a `ModelError` into a problem;
  - then run the refusals of test 4;
  - the quote check uses `ai.quote_in(quote, text)`. The text for a fact id is its quote plus its value. The text
    for a source id is `index[id]` from `ai.evidence_index(dossier)`;
  - the scheduled tags come from the row tags on `reading.schedules`, expanded with
    `estimator.writing.write.tag_list` where needed.
- `take_off(ledger, catalogue, reading, dossier, playbook, transport) -> Takeoff`: call
  `ai._ask_checked(transport, TAKEOFF_JOB, "Takeoff", playbook.rules_text, ai._instructions("takeoff_job"), prompt, answer_schema(), {"step": "takeoff"}, (), check)`.
  It raises `ai.NoAnswer` as the writers do.
- `attach(job, takeoff) -> Job`: `dataclasses.replace` of the four fields only.
- `save(takeoff, path)`, `load(path)`: JSON `{"version": 1, ...}`, written through `ai._write_json`.

Proof: `pytest tests/bms/test_takeoff.py`.

### Task 1.4: the prompt `src/bms/prompts/takeoff_job.md`. 0.5 h, Sonnet

Write this text exactly:

```
You are the takeoff reader of a building controls (BMS / DDC) estimate for AME. The rules above are the estimator's Playbook. They bind every answer.

You are given the whole job as the reading left it: every ledger fact with its id, what each reading pass understood, every drawing sheet with its number, its title, the code's guess of its type and the tags the code found on it with how many times, the schedule rows, the notes on the sheets, the sequence section headings and the devices the code counted on each sheet. The code counts labels; it cannot tell what a sheet is or which labels are one unit. You decide that. Answer with JSON only, in the schema given.

## Sheets
- Give every sheet listed exactly once, by its document and page, with the number as listed.
- kind: new_work (new or construction work), demolition (removal or existing-to-be-removed), part_plan (part of an area, often at a match line), enlarged_plan (a larger-scale drawing of a room another plan also shows), riser, schedule, detail, control_diagram, other.
- area: plain words for the place the sheet shows ("Attic", "Level 2 east"). Every sheet that shows the same place has the same area words: a ductwork plan and a piping plan of one floor, two part plans that meet at a match line, an enlarged plan and the plan it enlarges. Leave area empty for a sheet that is not a plan.
- counts_units: true when the units and devices drawn on the sheet count for this job. A demolition sheet is false, unless the documents name work on a unit drawn there; then cite that passage in refs.
- reason: one short sentence.

## Units
- One row per unit the documents show: every tag a schedule lists, every unit drawn on a plan, the existing units on demolition sheets.
- tag: as the schedule prints it. labels: every way the sheets label it ("AHU-1", "AHU 1", "(D)AHU-6").
- status: new; demolish (shown for removal, no other work); demolish_with_work (shown for removal and the documents name controls work on it); existing_remain; relocate; future (the documents say it is future).
- count: 1 for a numbered unit. For a typical unit whose one tag is drawn at many places, the number of places on the counted sheets.
- sheets: the counted sheets it is drawn on. serves: the unit it serves (a control valve or a pump that serves an air handler); empty otherwise. service: the service it is on (chilled water, hot water, condenser water); empty otherwise.
- Every tag a schedule lists has a row. A scheduled unit you do not count (demolish, existing_remain, future) must cite the passage that says so.
- refs: at least one per unit.

## Counts set aside
- When a count in the ledger counts the same unit twice, counts units of a demolition sheet, counts rows that are not units of the family, or counts a future item, give a set_aside row: the family, the number, the source of that number as a ref, the reason, and a note with both numbers in plain words ("21 plan placements set aside; 5 units on the new-work sheets").
- Never set aside a count without saying which count stays.

## Future items
- Every device or unit the documents mark future, with its family and refs.

## Questions
- At most one question per family, in plain words, when the documents do not let you decide.

## Citations
- A ref has source_id (a fact id such as "F90", or a source id the job data gives such as "S537"), quote (the exact words, copied) and where (the sheet or page).
- Cite only ids in the job data. Never invent a number.

## The estimator's rulings of 2026-10-11 (bind this answer where they apply)
1. Units on demolition plans are not counted, unless the documents name work on them.
2. Part plans can share one area: a unit on both counts once.
3. The header's quote number is the job number and its reference is the project name, from the job folder.
4. An existing BMS other than Honeywell WEBS, Johnson FX or Niagara Tridium prints in red with *** and a flag.
5. Long clarifications become short points.
6. Never write "Assumed" when a schedule states the fact.
7. A future item prints with "(FUTURE AS PER <source>)" in red.
8. Control valves go under the unit they serve.
9. Pumps are split by service.
10. Devices a unit schedule says are shipped loose are read into the scope.
11. A review question is never repeated.
12. Off-hours work and prevailing wage are added in red.
13. Every block follows the Master Template format and the GEM order of points.

## Plain words
- No emoji, no markdown, no codes of your own.
```

Proof: test 1 of Task 1.3 reads the file.

### Task 1.5: the request flow in both modes. 3 h, Sonnet

Tests first:
- `tests/bms/test_status.py`: a request with kind `takeoff_job` and step `takeoff` reports stage "takeoff". "takeoff"
  sorts between "read" and "count".
- `tests/bms/test_ai.py`: `run_job.check_answer` accepts `answer()` for a takeoff request and refuses one with no
  `units` list.
- `tests/bms/test_review.py`: a device with flag "future" makes a card whose note is
  "This line is a future item in the documents."

Code:
- `src/bms/status.py:34-37`: put "takeoff" after "read" in `_ORDER`. Add `"takeoff_job": "takeoff"` to
  `_KIND_STAGE` and `"takeoff": "takeoff"` to `_STEP_STAGE`.
- `tools/run_job.py:28`: add `"takeoff_job": "units"` to `MAIN_LIST`. At `:31`, add "takeoff" to `BMS_STEPS`.
- `.claude/skills/run-job/SKILL.md`, step 2: add the bullet "`takeoff_job`: alone, after the reading; it goes to
  `judge_model`". In the model sentence, add "`judge_model` for `takeoff_job`".
- `src/bms/review.py:43-47`: add `"future": "This line is a future item in the documents."` to `_FLAG_WORDS`.
- Test answerers: in `tests/bms/test_run.py:89-100` `_answer`, add
  `if kind == "takeoff_job": return takeoff_answer(request)`. Put `takeoff_answer` in
  `tests/bms/takeoff_fixture.py`. From the request prompt it reads the "Sheets" lines and the schedule tags. It
  answers every sheet `new_work`, area = its number, `counts_units` true, and one `new` unit per scheduled tag. Each
  unit cites the first fact line that names it. Add the same branch to the answerers in `test_run_front_end.py`,
  `test_run_revise_count.py`, `test_review_019b.py`, `test_final_fixes.py:116` and `tests/test_whole_job.py`. Then
  run the full suite to find any others.

API mode needs no new code: `ApiTransport.ask` sends `playbook.rules_text` as the cached first system block
(`ai.py:22-23`).

Proof: `pytest tests/bms/test_status.py tests/bms/test_ai.py tests/bms/test_review.py`.

### Task 1.6 (lead-owned): the run step. 3 h, Sonnet; the lead reviews

File: `src/bms/run.py`.

Tests first, in `tests/bms/test_run.py`:
- `test_a_run_waits_at_takeoff_after_reading`: the stages go read, then takeoff, then count. Once the takeoff is
  answered, `out/<quote> Takeoff.json` exists. `Job.json` carries `units` and `sheets`.
- `test_takeoff_changes_no_count`: run with the fixture answerer. Then compare every family count in `Job.json`
  with `plan_job` plus `cross_check` on the same inputs without a takeoff. They are equal.

Code:
- After the `if not ledger.complete` return (`run.py:502-505`), set `known["stage"] = "takeoff"`. Load the playbook
  and build the transport here: move `run.py:508` and `:517` up, unchanged.
- Call `register = takeoff.take_off(ledger, catalogue, reading, dossier, playbook, transport)`.
- On `ai.NoAnswer`, return
  `RunResult("waiting", "takeoff", waiting=transport.waiting, messages=(_not_answered("Takeoff", missing),))`.
- On success, call `takeoff.save(register, out / f"{quote} Takeoff.json")` and print `Wrote <path>`.
- After the header replace (`run.py:510-516`), set `job = takeoff.attach(job, register)`.
- Add "takeoff" to the stage list in the `RunResult.stage` comment (`run.py:90`) and in the module docstring.

Proof: `pytest tests/bms/test_run.py tests/bms/test_takeoff.py`. Then run the whole suite in the background:
`pytest tests -q -p no:cacheprovider -n 10`.

### Task 1.7 (lead-owned): the spec. 1 h, Sonnet; the lead reviews

In `docs/superpowers/specs/2026-10-04-rebuild-interfaces.md`:
- §2.1: add the three enumerations and "future".
- §2.2: add the four classes and the four Job fields.
- §5: add "Workstream 8: `bms.takeoff`", with the signatures of Task 1.3 and the request kind.
- §6: add the run step between the ledger and `plan_job`.
- §7: add the takeoff fixture.

State that Stage 1 changes no count.

Proof: the lead reads the diff. `pytest tests/bms/test_contracts.py`.

---

## Stage 2: wiring (after T-005a..e merge into `rebuild`)

Before each task, open the named function as it stands on `rebuild`. The line numbers below are from 0e78113.

### Task 2.1: count over admissible sheets. 4 h, Sonnet

Tests first, in `tests/bms/test_takeoff.py`:
- `admissible_pages(job.sheets)` holds the pages with `counts_units` true.
- `area_groups(job.sheets)` maps M-401..M-404 to one group.
- On the fixture, `placements(catalogue(), ["AHU-1", ..., "AHU-5"], pages=..., groups=...)` gives `plan` 5 per family
  total, with no group on MD-401.
- `device_tally(reading().devices, job.sheets, "T")` is 30 kept, with 9 set aside on MD-201.

Code:
- `estimator/reading/inventory.py`, `placements` (`:670-747` **(may have moved)**): add the keyword
  `groups: dict | None = None`. When it is given, use it in place of the `plan_groups(...)` result (`:703`
  **(may have moved)**). `plan_count` (`:497`) already takes a groups map.
- In `takeoff.py`, add `admissible_pages`, `area_groups` (the keys of one area share one tuple, as `plan_groups`
  returns) and `device_tally`. `device_tally` returns `(kept, [SetAside])`.

### Task 2.2: admissible sources in the planner. 6 h, **Opus**

Tests first:
- The fixture job planned with the register prints AHU 5, EF 5, ERU 1 and FCU 55.
- `job.set_aside` holds the code's earlier AHU, EF and ERU placement counts. Each has reason "demolition sheet" or
  "part plan of one area", and a note naming both numbers.
- Exactly one question per family whose printed count fell below the code tally.
- A register below the schedule cannot reach here, because Task 1.3 refuses it. Assert it with a register that has
  AHU-5 `demolish` and a ref: the AHU count is 4, the set-aside names 5, and there is one question.

Code, in `bms/plan_read.py`, `_count` (`:301-309` **(may have moved)**):
- Before `max`, call `takeoff.admit(prefix, entries, register, recount)`. It returns `(kept, set_aside)`.
- An entry is dropped when its number and source match a register `SetAside`.
- An entry is also dropped when it is a "plan placements" or "located/seen" clause whose sheets are all
  `counts_units` false.
- A "plan placements" entry is replaced by the recount of Task 2.1 when the two differ. The old number goes to
  `set_aside`.
- Add the register entry: the sum of `count` over units of the family whose status is in `COUNTED_STATUSES`. It
  cites the first unit's refs.
- The highest kept entry prints. When `register` is None, nothing changes.
- The Reader takes `register` and `recount` from the Job fields. `plan_job` passes them through.
- The questions use the form "How many <family> units? <N> print from the new-work sheets; the code counted <M>."

### Task 2.3: tags, valves under units, pumps split. 8 h, **Opus**

Tests first, using the fixture plus CV-1..5 serving AHU-1..5 and P-1..4 with services chilled water and hot water:
- The AHU header tags are AHU-1 thru 5. AHU-6 is not among them.
- CV is not a system of its own. It is a family in the AHU system.
- The pumps are two systems, "Chilled Water Pump" and "Hot Water Pump", with 2 each.

Code, in `bms/plan.py`, `plan_job` (`:1621-1669` **(may have moved)**):
- After `link_dampers` (`:715` **(may have moved)**), add `planner.serve_units(drafts, job_units)`, modelled on
  `link_dampers`. A family whose units all serve tags of one other draft moves into that draft as a family.
- Add `planner.split_by_service(drafts, job_units)`. A draft whose units carry two or more services becomes one draft
  per service. Its name is the service, title-cased, plus the family's kind word.
- At the end, set each family's tags to the tags of its counted units, when the register has rows for the family.

### Task 2.4: the cross-check skips excluded sheets. 2 h, Sonnet

Test: `cross_check` on the fixture job pictures no page with `counts_units` false.

Code: in `bms/counts.py`, the sheet filter (`:287` **(may have moved)**) also requires the sheet to be admissible
when `job.sheets` is not empty.

### Task 2.5: the writer sees the register. 4 h, Sonnet; `run.py` part lead-owned

Test: the AHU evidence holds "Takeoff register for this system", each unit row, the future item and the plans
understanding. The FCU evidence holds "Thermostats: 30 on the new-work sheets; 9 set aside (demolition sheet)".

Code:
- `ai_evidence.evidence` (`:190` **(may have moved)**): add the keyword `register: str = ""` and print it first,
  under that heading.
- `ai.evidence_for` (`:745` **(may have moved)**) passes the keyword.
- `takeoff.register_text(job, system, ledger)` builds it.
- `run.py:537` passes it.
- `write_system.md` gains one rule: "A device or unit the takeoff lists as future has flag "future"; its name ends
  "(FUTURE AS PER <the document in words>)"." Coordinate this with T-005d's prompt edits.

### Task 2.6: the notes and one card per family. 3 h, Sonnet

Tests:
- The AHU block's quantity note names the set-aside numbers with their reasons.
- The Evidence Package has a "Set aside" tab.
- Review: the AHU family has one card and no device card for lines counted from it (skip this if T-005b already
  does it).

Code:
- `render._count_note` (`:484` **(may have moved)**) reads `job.set_aside` for the family.
- `evidence.write_evidence` adds the tab.
- `review._questions` (`:166-182` **(may have moved)**) skips a device whose only reason is the family count.

### Task 2.7: end to end, and the 26-0544 rerun. 3 h, Sonnet; the rerun is the lead's

Test: `test_takeoff_end_to_end`. The fixture through `plan_job`, `attach`, `cross_check` (no transport) and
`render` prints AHU 5, EF 5, ERU 1, FCU 55 and thermostats 30. The set-asides are present in `Job.json`. Then the
whole suite. The lead then runs `/run-job` on 26-0544 and compares with the acceptance.

---

## Estimates

| Task | Hours | Tier |
|---|---|---|
| 1.1 model (lead) | 3 | Sonnet |
| 1.2 fixture (lead) | 4 | Sonnet |
| 1.3 takeoff.py | 8 | Sonnet |
| 1.4 prompt | 0.5 | Sonnet |
| 1.5 request flow | 3 | Sonnet |
| 1.6 run step (lead) | 3 | Sonnet |
| 1.7 spec (lead) | 1 | Sonnet |
| 2.1 admissible sheets | 4 | Sonnet |
| 2.2 planner sources | 6 | Opus |
| 2.3 tags, valves, pumps | 8 | Opus |
| 2.4 cross-check | 2 | Sonnet |
| 2.5 writer evidence | 4 | Sonnet |
| 2.6 notes, cards | 3 | Sonnet |
| 2.7 end to end | 3 | Sonnet |
| **Total** | **52.5** (Stage 1: 22.5) | |

## Open points for the estimator

1. **Demolition work.** A unit with status `demolish_with_work` is not added to the unit count. Its work (remove
   the old controls) needs a line or a Miscellaneous section, and the model has no Miscellaneous section yet. Where
   does it print?
2. **The schedule floor.** The floor is the tags that schedules list as rows. A schedule's QUANTITY column for a type
   tag (FCU-1) is not a floor here, because it is often blank. Is that right?
3. **The AI may set aside a schedule count.** For example, rows of other schedules that name an AHU-6. The floor
   still holds. Does the estimator accept this?
4. **Model fields.** Two fields beyond the three named, `Job.set_aside` and `Job.future_items`, are needed so that no
   count drops silently. They sit on the Job, not on `Count`, so the writer's schema does not change.
