# Takeoff pass (Option A): implementation plan

**Goal.** One whole-job AI step returns a register: what each sheet is, which units exist, which counts are set
aside. Stage 1 stores it and changes no count. Stage 2 makes it binding: "highest prints" over admissible sources
only; every excluded count stays visible with both numbers and its reason.

**Base.** `lead/wave2` (0e78113). Stage 1 branch: `takeoff/s1` from `lead/wave2`. Stage 2 branch: `takeoff/s2` from
`rebuild` after HarkPro T-005a..e merge.

**Rules for every task.** Test first; invented fixtures only; no subagents or multi-agent review skills (no
/code-review or /simplify fan-out); `.venv\Scripts\python.exe` with `PYTHONPATH=src`.
Proof command (task tests): `.venv\Scripts\python.exe -m pytest <files> -q -p no:cacheprovider`.

**Files.**
- New: `src/bms/takeoff.py`, `src/bms/prompts/takeoff_job.md`, `tests/bms/test_takeoff.py`,
  `tests/bms/takeoff_fixture.py`, `tests/bms/fixtures/takeoff/` (four JSON files).
- Lead-owned (the lead reviews these diffs first): `src/bms/model.py`, `src/bms/run.py`,
  `tests/bms/fixtures/sample_job.json`, `tests/bms/test_contracts.py`, `docs/superpowers/specs/2026-10-04-rebuild-interfaces.md`.
- Stage 1 small edits: `src/bms/status.py`, `tools/run_job.py`, `.claude/skills/run-job/SKILL.md`, and the test
  answerers in `tests/bms/test_run.py`, `test_run_front_end.py`,
  `test_run_revise_count.py`, `test_review_019b.py`, `test_final_fixes.py`, `tests/test_whole_job.py`.
- Stage 2: `inventory.py`, `plan_read.py`, `plan.py`, `counts.py`, `ai_evidence.py`, `ai.py`, `write_system.md`,
  `render.py`, `evidence.py`, `review.py`. HarkPro edits these too: line references are marked **(may have moved)**.

---

## Stage 1: additive only

### Task 1.1 (lead-owned): model fields. 3.5 h, Sonnet; the lead reviews

File: `src/bms/model.py`, after the T-005c merge. T-005c adds `Device.mark` (its `Mark` includes "future"; `Flag`
does not change) and keeps a field with `_doc(..., optional=True)` out of the schema's `required`. Every field here
follows that rule: a default (empty, `""`, `False`) and `optional=True`.

Test first, in `tests/bms/test_contracts.py`:
- `test_enumerations_are_the_design_values`: add asserts for `SHEET_KINDS`, `UNIT_STATUSES`, `SET_ASIDE_REASONS`
  and `DEMOLITION_ACTIONS` with the exact tuples below. The FLAGS line stays as it is.
- `test_takeoff_fields_round_trip`: the fixture's one entry per new field survives `Job.from_json(job.to_json())`.
- `test_old_job_without_takeoff_fields_loads`: delete the five new keys from `raw` and load it. All five are `()`.
- `test_takeoff_fields_are_not_required_in_the_schema`: `json_schema(Job)["required"]` names none of the five, and
  `json_schema(Unit)["required"]` does not name `serves`, `service`, `with_plant` or `reason`.
- `test_unit_needs_a_ref`: a `Unit` with `refs=()` raises `ModelError`.

Code. Add after `DecisionAction` (`model.py:33`):

```python
SheetKind = Literal["new_work", "demolition", "part_plan", "enlarged_plan", "riser", "schedule", "detail",
                    "control_diagram", "other"]
UnitStatus = Literal["new", "demolish", "demolish_with_work", "existing_remain", "relocate", "future"]
SetAsideReason = Literal["demolition sheet", "same unit labelled again", "part plan of one area", "future item",
                         "existing to remain", "not a unit of this family"]
DemolitionAction = Literal["demo", "existing to remain", "relocation"]
```

Add the tuples `SHEET_KINDS`, `UNIT_STATUSES`, `SET_ASIDE_REASONS`, `DEMOLITION_ACTIONS` beside `FLAGS`
(`model.py:42`), `COUNTED_STATUSES = ("new",)` (ruling 17: demolished, existing and relocated units never enter the
new-work counts) and `DEMOLITION_OF = {"demolish": "demo", "demolish_with_work": "demo", "existing_remain":
"existing to remain", "relocate": "relocation"}`. Add these classes before `Job`, each `@dataclass(frozen=True)` on
`_Model`, with `_doc` texts (a field shown with a default gets `optional=True`):

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
    with_plant: bool = False          # a pump drawn and scheduled as part of a plant that is in scope (ruling 18)
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

class DemolitionLine(_Model):         # one line of the "Demolition Scope" block (Task 2.8)
    family: str                       # "AHU"
    action: DemolitionAction
    count: int | None                 # None prints "Qty (##)"
    refs: tuple[Ref, ...]             # the unit rows' refs
```

Model choice for the Demolition Scope: `Job.demolition: tuple[DemolitionLine, ...]`, not a `System` with a kind. A
System brings slots, verbs, parties, the writer, the validator and QC, none of which a demolition count line has; a
separate tuple keeps the writer's schema unchanged, and code builds it from the register alone.

Add to `Job`, after `source_sheets` (`model.py:249`), each `optional=True`: `sheets: tuple[SheetClass, ...] = ()`,
`units: tuple[Unit, ...] = ()`, `set_aside: tuple[SetAside, ...] = ()`, `future_items: tuple[FutureItem, ...] = ()`,
`demolition: tuple[DemolitionLine, ...] = ()`. Append the five classes to `MODEL_CLASSES` (`model.py:292`) and the new names to the module's export list.

Fixture: `tests/bms/fixtures/sample_job.json` gets one entry per new key, citing `S1` ("Drawings.pdf" page 2): sheet
`M-101` `new_work` "Level 1"; unit `EF-1` `new`; a set-aside "demolition sheet" 2; a future item "outside airflow
measuring station"; a demolition line EF demo 1.

Proof: `pytest tests/bms/test_contracts.py`. Then `pytest tests/bms -q -n 10 -m "not slow"`.

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

`reading.json`: schedules on M-601 (AHU-1..5; EF-1..5; ERU-1; FCU-1 with a blank QTY); `DeviceCount` rows for
"Thermostat" (`T`): 14, 16, 9 on pages 7, 8, 9; one MD-401 keynote "EXISTING AHU-6 AND EF-6 TO BE REMOVED".

`ledger.json` (`Ledger.to_dict` form, `complete` true): schedules-pass family, unit and count facts (AHU 5, EF 5,
ERU 1, FCU 1); plans-pass notes "AHU-6 and EF-6 are existing units shown for demolition only" and "FCU-1 is a typical
unit drawn 25 times on M-201 and 30 on M-202"; a sequence-pass question note that the AFMS is future; an invented
`understanding.plans` sentence (five new air handlers, five exhaust fans).

`answer.json`: the correct register for this job.
- Sheets: M-401..M-404 have area "Attic", `counts_units` true. MD-401 and MD-201 are `demolition` with
  `counts_units` false. M-201 and M-202 are areas "Level 1" and "Level 2".
- Units: AHU-1..5 `new`, AHU-6 `demolish`, EF-1..5 `new`, EF-6 `demolish`, ERU-1 `new`, and FCU-1 `new` with count
  55. Each cites a ledger fact by its id.
- Pumps (for Task 2.3): P-1 (chilled water) and P-2 (hot water) drawn alone on M-401 with `with_plant` false; P-3
  and P-4 scheduled with boiler B-1 and `with_plant` true, `serves` "B-1". Add their schedule rows and a boiler
  schedule row B-1 to `reading.json`, and their labels to M-401.
- Set-asides: none (the code works out the excluded sheet counts in Stage 2).
- Future items: one, "outside airflow measuring station", which cites the question fact.

`tests/bms/takeoff_fixture.py`: `catalogue()` (built as `tests/test_inventory_same_floor.py:126-138` does; `TagEntry`
for every label except `T`); `reading()` (a `SimpleNamespace(schedules, devices, notes, typicals=(), totals=())` of
`Schedule`, `ScheduleRow`, `DeviceCount`, `Note`); `ledger()` (`Ledger.from_dict`); `dossier()` (a `Dossier` whose
`sources` are the ledger's, `sheet_pages` one 7c id per sheet); `answer()`.

Proof: `pytest tests/bms/test_takeoff.py -k fixture`. `test_fixture_reproduces_the_defect`: `plan_job(ledger(),
catalogue(), dossier(), PLAYBOOK)` (sample playbook) counts AHU above 5 and EF above 5; pin the exact numbers.

### Task 1.3: `src/bms/takeoff.py`. 8 h, Sonnet

Tests first, in `tests/bms/test_takeoff.py`. Use a fake transport like `tests/bms/test_ai.py`'s: it answers
`answer()` and records the request.
1. `test_the_request_carries_the_whole_job`: kind `"takeoff_job"` and extra `{"step": "takeoff"}`. The prompt holds
   every fact line (`Fact.line()`), every understanding paragraph, all 10 sheets, the M-601 rows, the MD-401
   keynote, and the thermostat counts. Instructions are `playbook.rules_text`. The system prompt is
   `prompts/takeoff_job.md`.
2. `test_the_prompt_is_the_same_twice`: two builds give equal text, so the cache key stays stable.
3. `test_a_good_answer_loads`: `take_off(...)` returns a `Takeoff` with 10 sheets and 19 units, and the units
   round-trip through `Unit.to_dict` and `Unit.from_dict`.
4. Refusals (one parametrised test; each problem names the item): a sheet left out, given twice or unknown; a
   plan-kind sheet with no area; a scheduled tag (AHU-4) with no unit row; a ref whose id the ledger does not know
   or whose quote is not in that fact or source; a demolition sheet with `counts_units` true and no ref; two rows
   for one (family, tag); `serves` naming no unit; a set-aside with an unknown ref.
5. `test_the_schedule_is_the_floor`: AHU-5 with status `demolish` and `reason` "" is refused. With a reason and a
   ref, it is kept.
6. `test_counts_do_not_change`: `attach(job, takeoff)` changes only `sheets`, `units`, `set_aside` and
   `future_items` (`demolition` stays empty until Task 2.8). Every `family.count` is unchanged.
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
- `check_answer(answer, ledger, catalogue, reading, index) -> (Takeoff | None, problems)`: `schema_errors` first;
  then each class's `from_dict` (a `ModelError` is a problem); then the refusals of test 4. Quotes: `ai.quote_in(quote,
  text)`, where a fact id's text is its quote and value and a source id's is `ai.evidence_index(dossier)[id]`.
  Scheduled tags: the row tags of `reading.schedules`, expanded with `estimator.writing.write.tag_list`.
- `take_off(ledger, catalogue, reading, dossier, playbook, transport) -> Takeoff`: call
  `ai._ask_checked(transport, TAKEOFF_JOB, "Takeoff", playbook.rules_text, ai._instructions("takeoff_job"), prompt, answer_schema(), {"step": "takeoff"}, (), check)`.
  It raises `ai.NoAnswer` as the writers do.
- `attach(job, takeoff) -> Job`: `dataclasses.replace` of `sheets`, `units`, `set_aside`, `future_items` only.
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
- status: new; demolish (shown for removal, no other work); demolish_with_work (shown for removal and the documents name controls work on it); existing_remain; relocate; future (the documents say it is future). Only new units enter the counts; demolish, demolish_with_work, existing_remain and relocate units print in the Demolition Scope block.
- count: 1 for a numbered unit. For a typical unit whose one tag is drawn at many places, the number of places on the counted sheets.
- sheets: the counted sheets it is drawn on. serves: the unit it serves (a control valve or a pump that serves an air handler); empty otherwise. service: the service it is on (chilled water, hot water, condenser water); empty otherwise. with_plant: true when a pump is drawn and scheduled as part of a plant that is in this job's scope and serves it (then serves names the plant's unit); false for a remote pump. The documents decide.
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

## The estimator's rulings of 2026-10-11 (by the estimator's numbers; bind this answer where they apply)
1. Units on demolition plans are not counted, unless the documents name work on them.
2. Part plans can share one area: a unit on both counts once.
6. Never write "Assumed" when a schedule states the fact.
7. A future item prints with "(FUTURE AS PER <source>)" in red.
8. Control valves go under the unit they serve.
9. Pumps are split by service, unless ruling 18 puts them in a plant block.
10. Devices a unit schedule says are shipped loose are read into the scope.
14. A '*' note is one short line per item.
15. Quantities print as "Qty (#) <device>".
17. Units from demolition sheets print in a "Demolition Scope" block, last in the proposal ("Qty (##) AHU demo", "Qty (##) FCU Existing to Remain", "Qty (##) VAV Relocation"), never in the new-work counts.
18. Pumps are part of the plant block when the plant is in the job's scope and they serve it; they are a block of their own per service when the job shows remote pumps. The documents decide.

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

Code:
- `src/bms/status.py:34-37`: put "takeoff" after "read" in `_ORDER`. Add `"takeoff_job": "takeoff"` to
  `_KIND_STAGE` and `"takeoff": "takeoff"` to `_STEP_STAGE`.
- `tools/run_job.py:28`: add `"takeoff_job": "units"` to `MAIN_LIST`. At `:31`, add "takeoff" to `BMS_STEPS`.
- `.claude/skills/run-job/SKILL.md`, step 2: add the bullet "`takeoff_job`: alone, after the reading; it goes to
  `judge_model`". In the model sentence, add "`judge_model` for `takeoff_job`".
- Test answerers: add `if kind == "takeoff_job": return takeoff_answer(request)` to `_answer` in
  `tests/bms/test_run.py:89-100` and to the answerers in `test_run_front_end.py`, `test_run_revise_count.py`,
  `test_review_019b.py`, `test_final_fixes.py:116`, `tests/test_whole_job.py` (run the suite to find others).
  `takeoff_answer` (in `takeoff_fixture.py`) reads the "Sheets" lines and schedule tags from the prompt: every sheet
  `new_work`, area its number, `counts_units` true; one `new` unit per scheduled tag, citing the first fact naming it.

API mode needs no new code: `ApiTransport.ask` sends `playbook.rules_text` as the cached first system block
(`ai.py:22-23`).

Proof: `pytest tests/bms/test_status.py tests/bms/test_ai.py`.

### Task 1.6 (lead-owned): the run step. 3 h, Sonnet; the lead reviews

File: `src/bms/run.py`.

Tests first, in `tests/bms/test_run.py`:
- `test_a_run_waits_at_takeoff_after_reading`: the stages go read, then takeoff, then count. Once the takeoff is
  answered, `out/<quote> Takeoff.json` exists. `Job.json` carries `units` and `sheets`.
- `test_takeoff_changes_no_count`: run with the fixture answerer. Then compare every family count in `Job.json`
  with `plan_job` plus `cross_check` on the same inputs without a takeoff. They are equal.

Code: after the `if not ledger.complete` return (`run.py:502-505`), set `known["stage"] = "takeoff"`; move the
playbook load (`:508`) and the transport (`:517`) up, unchanged; `register = takeoff.take_off(ledger, catalogue,
reading, dossier, playbook, transport)`; on `ai.NoAnswer` return `RunResult("waiting", "takeoff",
waiting=transport.waiting, messages=(_not_answered("Takeoff", missing),))`; else `takeoff.save(register, out /
f"{quote} Takeoff.json")` and print `Wrote <path>`. After the header replace (`:510-516`), `job =
takeoff.attach(job, register)`. Add "takeoff" to the stage comment (`:90`) and the module docstring.

Proof: `pytest tests/bms/test_run.py tests/bms/test_takeoff.py`. Then run the whole suite in the background:
`pytest tests -q -p no:cacheprovider -n 10`.

### Task 1.7 (lead-owned): the spec. 1 h, Sonnet; the lead reviews

In `docs/superpowers/specs/2026-10-04-rebuild-interfaces.md`:
- §2.1: add the four enumerations, `COUNTED_STATUSES` and `DEMOLITION_OF`.
- §2.2: add the five classes and the five Job fields, all optional (the T-005c rule).
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
- `estimator/reading/inventory.py`, `placements` (`:670-747` **(may have moved)**): add the keyword `groups: dict |
  None = None`, used in place of the `plan_groups(...)` result (`:703`) when given.
- In `takeoff.py`, add `admissible_pages`, `area_groups` (the keys of one area share one tuple, as `plan_groups`
  returns) and `device_tally`. `device_tally` returns `(kept, [SetAside])`.

### Task 2.2: admissible sources in the planner. 6 h, **Opus**

Tests first: the fixture planned with the register prints AHU 5, EF 5, ERU 1, FCU 55; `job.set_aside` holds the
code's earlier AHU, EF and ERU placement counts with reason "demolition sheet" or "part plan of one area" and both
numbers; one question per family whose printed count fell below the code tally. With AHU-5 `demolish` and a ref,
AHU prints 4, the set-aside names 5, and there is one question.

Code, in `bms/plan_read.py`, `_count` (`:301-309` **(may have moved)**):
- Before `max`, call `takeoff.admit(prefix, entries, register, recount)`. It returns `(kept, set_aside)`.
- Drop an entry whose number and source match a register `SetAside`, or a "plan placements" or "located/seen"
  clause whose sheets are all `counts_units` false. Replace a "plan placements" entry by the Task 2.1 recount when
  they differ. Each dropped or replaced number goes to `set_aside`.
- Add the register entry: the sum of `count` over units of the family whose status is in `COUNTED_STATUSES`. It
  cites the first unit's refs.
- The highest kept entry prints. When `register` is None, nothing changes.
- The Reader takes `register` and `recount` from the Job fields. `plan_job` passes them through.
- The questions use the form "How many <family> units? <N> print from the new-work sheets; the code counted <M>."

### Task 2.3: tags, valves under units, pumps split. 8 h, **Opus**

Tests first (fixture plus CV-1..5 serving AHU-1..5, and the Task 1.2 pumps): the AHU header tags are AHU-1 thru 5;
CV is a family in the AHU system; P-3 and P-4 (`with_plant` true) are a family in the B-1 system; P-1 and P-2
(`with_plant` false) are systems "Chilled Water Pump" and "Hot Water Pump", 1 each.

Code, in `bms/plan.py`, `plan_job` (`:1621-1669` **(may have moved)**):
- After `link_dampers` (`:715` **(may have moved)**), `planner.serve_units(drafts, job_units)`, modelled on it: a
  family whose units all serve one other draft's tags moves into that draft; for pumps, only the `with_plant` units
  move (into the plant's draft).
- Then `planner.split_by_service(drafts, job_units)`: only units with `with_plant` false split; a draft whose such
  units carry two or more services becomes one draft per service, named the service plus the kind word. A
  `with_plant` pump never leaves its plant.
- At the end, set each family's tags to the tags of its counted units, when the register has rows for the family.

### Task 2.4: the cross-check skips excluded sheets. 2 h, Sonnet

Test: `cross_check` on the fixture job pictures no page with `counts_units` false.

Code: in `bms/counts.py`, the sheet filter (`:287` **(may have moved)**) also requires the sheet to be admissible
when `job.sheets` is not empty.

### Task 2.5: the writer sees the register. 4 h, Sonnet; `run.py` part lead-owned

Test: the AHU evidence holds "Takeoff register for this system", each unit row, the future item and the plans
understanding. The FCU evidence holds "Thermostats: 30 on the new-work sheets; 9 set aside (demolition sheet)".

Code: `takeoff.register_text(job, system, ledger)` builds the text; `ai_evidence.evidence` (`:190` **(may have
moved)**) takes `register: str = ""` and prints it first; `ai.evidence_for` (`:745`) and `run.py:537` pass it.
- `write_system.md` gains one rule: "A device or unit the takeoff lists as future has mark "future" and mark_note
  "FUTURE AS PER <the document in words>"." Coordinate this with the T-005c and T-005d prompt edits.

### Task 2.6: the notes and one card per family. 3 h, Sonnet

Tests: a "same unit labelled again" or "part plan of one area" set-aside prints one short '*' line in its block
("*AHU counted once on part plans M-403 and M-404"); a "demolition sheet" set-aside prints no '*' line (the Demolition
Scope block of Task 2.8 carries those units); the Evidence Package has a "Set aside" tab with every set-aside; the
AHU family has one review card and no device card (skip if T-005b already does it).

Code: `render._count_note` (`:484` **(may have moved)**) reads `job.set_aside`: one short line per duplicate
(ruling 14), demolition-sheet set-asides skipped; `evidence.write_evidence` adds the tab; `review._questions`
(`:166-182` **(may have moved)**) skips a device whose only reason is the family count.

### Task 2.7: end to end, and the 26-0544 rerun. 3 h, Sonnet; the rerun is the lead's

Test: `test_takeoff_end_to_end`. The fixture through `plan_job`, `attach`, `cross_check` (no transport) and
`render` prints AHU 5, EF 5, ERU 1, FCU 55 and thermostats 30. The last block before the alternates is
"Demolition Scope" with "Qty (1) AHU demo" and "Qty (1) EF demo"; AHU-6 and EF-6 are in no AHU or EF header or count.
The set-asides and the demolition lines are present in `Job.json`. Then the whole suite. The lead then runs `/run-job` on 26-0544 and compares with the acceptance.

### Task 2.8: the Demolition Scope block. 6 h, **Opus**

Tests first (`tests/bms/test_takeoff.py`, `tests/bms/test_render.py`), on the fixture:
- `demolition_lines(job.units)` gives AHU demo 1 and EF demo 1: one line per (family, action), counts summed, the
  unit rows' refs. With FCU-9 `existing_remain` count 3 and VAV-1 `relocate` added: "Qty (3) FCU Existing to Remain",
  "Qty (1) VAV Relocation".
- `render` prints a group block "Demolition Scope" after every system block, before the alternates, with "Qty (1)
  AHU demo" and "Qty (1) EF demo"; the AHU and EF blocks show 5; no demolition line is in a system.
- The Evidence Package has a "Demolition Scope" tab (family, action, count, refs). No demolition units: no block.

Code:
- `takeoff.demolition_lines(units)`: group the units whose status is in `DEMOLITION_OF` by (family,
  `DEMOLITION_OF[status]`), in register order; the count is the sum of `Unit.count`.
- `plan_job`, at the end **(may have moved)**: set `Job.demolition` from it when the register has units.
- `render.render` (`:87`, the block loop `:138` **(may have moved)**): after the system blocks, append
  `Block(header="Demolition Scope", items=..., numbered=False)` with one line item per DemolitionLine. Its text is
  `f"Qty ({count if count is not None else '##'}) {family} {label}"`, where label is "demo", "Existing to Remain"
  or "Relocation".
- `evidence.write_evidence` adds the tab.

---

## Estimates

Stage 1 (23 h, all Sonnet): 1.1 model 3.5 (lead), 1.2 fixture 4 (lead), 1.3 takeoff.py 8, 1.4 prompt 0.5, 1.5
request flow 3, 1.6 run step 3 (lead), 1.7 spec 1 (lead). Stage 2 (36 h): 2.1 admissible sheets 4, 2.2 planner
sources 6 (Opus), 2.3 tags, valves, pumps 8 (Opus), 2.4 cross-check 2, 2.5 writer evidence 4, 2.6 notes and cards 3,
2.7 end to end 3, 2.8 Demolition Scope 6 (Opus). Total 59 h.

## Open points for the estimator

1. A `demolish_with_work` unit prints "Qty (##) <family> demo", as a plain demolish. Should its named work (remove
   the old controls) be a line of its own?
2. The floor is the tags schedules list as rows, not a type tag's QUANTITY column (often blank). Right?
3. The AI may set aside a schedule count (rows of other schedules naming an AHU-6); the floor still holds. Accepted?
4. Should the Demolition Scope lines go on the price sheet? This plan leaves them off.
