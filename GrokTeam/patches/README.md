# Builder patches, 2026-10-09 (test job run follow-ups)

Proposed fixes for six app bugs found on the 2026-10-09 test run. **Not applied to `src/` and not committed.**
Each patch is a unified diff against `src/` at `grok/work` @167c3b2 (src unchanged at @49a237d). Each one applies alone, and all six apply
together (patches 02, 05 and 06 touch `src/bms/plan.py`; 02 and 05 touch `src/bms/render.py`; all in separate
hunks).
Every fixture is invented, with generic tags and no real project data.

How to verify (uses a throwaway worktree and never touches the real `src/`):

    PY=/path/to/python3.13 GrokTeam/patches/verify.sh /tmp/gt-verify   # per-patch before/after, then all together
    cd /tmp/gt-verify && PYTHONPATH=src $PY -m pytest -q -m "not slow" tests   # existing suite on the patched tree
    git -C <repo> worktree remove --force /tmp/gt-verify

The tests are in `GrokTeam/tests/` (their `conftest.py` puts the tree's own `src/` first on `sys.path`).
Run them with `python -m pytest GrokTeam/tests`.

## Results (verify.sh, Python 3.13.5, pytest 9.1.1)

| # | Patch | Test file | Clean src | With the patch alone |
|---|-------|-----------|-----------|----------------------|
| 1 | `01-validate-no-bms-integration.patch` | `test_01_validate_no_bms.py` | 3 failed, 3 passed | 6 passed |
| 2 | `02-plan-front-end-unresolved.patch` | `test_02_plan_front_end_unresolved.py` | 5 failed, 2 passed | 7 passed |
| 3 | `03-ai-evidence-key-sources.patch` | `test_03_ai_evidence_budget.py` | 3 failed, 3 passed | 6 passed |
| 4 | `04-count-overshoot.patch` | `test_04_count_overshoot.py` | 5 failed, 9 passed | 14 passed |
| 5 | `05-omitted-systems-as-exceptions.patch` | `test_05_omitted_systems_as_exceptions.py` | 4 failed, 4 passed | 8 passed |
| 6 | `06-schedule-only-questions.patch` | `test_06_schedule_only_template_lines.py` | 2 failed, 11 passed, 14 xfailed | 13 passed, 14 xfailed |

With all six applied, GrokTeam/tests gives 54 passed and 14 xfailed. On clean src, the tests that pass are the negative or
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
- **Tests.** Plan gives `front_end is None`. The question is kept and assumes nothing. Render, price sheet and
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
ignored. The original 6a ("required template lines always print") was reversed by the owner and replaced.

The fixture is an invented schedule-only ledger: IDU, VAV, UH, EF, ACU and MD families, plus RLD for 6d. It has
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
  list short. The VAV DDC controller (R11) is not asserted.
- *Negative: a supported template device raises no question.* REGRESSION GUARD.

**6b (revision 2): who furnishes a damper actuator is open.** No wording and no furnisher is asserted. "Wire
Motorized Damper (Furnished by Others)" is acceptable, and the forced actuator-wording test was dropped.
- *The documents are silent on who furnishes the actuators, so the planner asks.* **Patched**
  (`plan._unplaced_questions`). It asks "…who does? No damper line is printed until this is answered" when all of
  these hold:
  - the block is damper-only (not fire or smoke);
  - no provider fact names the block;
  - there is no sequence passage;
  - no other question already names its tags.
- *Negative: documents silent, so no damper line prints.* Passes before and after.
- *Negative: a provider fact names the furnisher, so no question.* Passes before and after.

**6c.** *A humidity sensor drawn next to a dehumidifier attaches to the dehumidifier, and its negative (a sensor
next to a VAV stays with the VAV).* Both are xfail(strict). Design note: the counts read tag text only. Nothing
attaches untagged symbols to units by drawing position. The proposed `bms.counts.attach_symbols(symbols, units)`
would use the nearest tagged unit on the same sheet, within a distance limit, and ask when two units are about the
same distance away. It needs the symbol boxes from the vision pass (`counts_vision`). That is too big to patch
cleanly here.

**6d.** *Equipment with no template family (an invented refrigerant leak detector, RLD) raises a question.*
**Patched** (`plan._unplaced_questions`). It asks only when there is no sequence passage and no other question
already names the system. A first, broader version flooded 28 existing plan tests with duplicate questions. It asks "No Master Template family fits … is it in AME's scope? If not, it is a named
exception." The system is still planned in the generic form. Negatives (pass before and after): it is still
planned, and a family with a shape raises no such question. With patch 05, if the writer then leaves it with no
lines, it prints as an exception with its quantity.

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
  - **Finding:** a bare detail-sheet note ("T'STAT PROVIDED BY UNIT MFGR.") names no tag and no system phrase, so
    `ai_evidence` never gives it to the writer. This is the likely root cause. xfail(strict). Design note: give a
    detail-sheet note that names a device word of the shape's slots (thermostat or t'stat, transformer, damper)
    to each system whose shape has that slot, under a budget like patch 03's.
  - Both wordings ("T'STAT PROVIDED BY UNIT MFGR.", "THERMOSTAT FURNISHED BY EQUIPMENT MANUFACTURER") give one
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

## Existing suite (`tests/`, `-m "not slow"`, on this Linux box)
- **Clean src (baseline):** 9 failed, 3735 passed, 10 skipped. The failures are environmental and not caused by
  these patches: 5 chat tests in `test_ai.py`, the Windows resource-code test in `test_review_final3.py`,
  `test_assets.py::test_running_on_the_project_python`, and 2 `test_main.py` file tests.
- **Patches 01-05 applied:** 13 failed, 3731 passed.
  - 2 failures are intentional (listed below).
  - 3 are `tests/test_revert_audit*.py`. These are flaky. Rerunning them on **clean** src fails a different 1-2 of
    them each time (subprocess and git timing).
  - The rest are the baseline set. One `test_ai` chat test passed in this run, so it is flaky too.
- **All six applied (final):** 15 failed, 3729 passed, 10 skipped.
  - The 4 intentional contradictions listed below.
  - 3 flaky tests, each also seen failing on **clean** src on rerun: `test_status_review.py::
    test_every_normal_exit_writes_the_state_whole_and_status_agrees`, `test_revert_audit.py::
    test_a_tools_change_is_reverted_too` and `test_revert_audit_review.py::
    test_a_test_file_saved_with_a_utf8_bom_is_audited`.
  - The 8 remaining are baseline environmental failures.
  - No other existing test changed result.

## Existing tests these patches intentionally contradict (they need the owner's decision; we cannot edit tests/)

1. `tests/bms/test_plan.py::test_an_existing_system_is_named_and_a_missing_mode_is_asked` asserts
   `job.front_end.mode == "new-system"` when no mode fact exists. That is bug 2 itself. With patch 02,
   `front_end` is None and the question is kept, so the test's last assertion still holds. Proposed edit:
   `assert job.front_end is None`.
2. `tests/bms/test_counts.py::test_a_unit_on_two_floor_plans_adds_up_as_the_inventory_counts` (CNT-5) asserts
   that EF-2, drawn on two floor plans, counts 2. That is the per-sheet overshoot from bug 4. With patch 04 it is 3
   (EF-1, EF-2, EF-5). This test follows the FINAL-I "groups summed" lead ruling. Rule R1 and the owner's steer
   ("a repeated tag is one unit") say otherwise. **The owner should confirm that R1 supersedes CNT-5 / FINAL-I for
   unit tags** before this patch lands. The estimator-side `inventory.plan_count` / `_as_type` (the Evidence
   Package) still sums groups. A follow-up patch would align it.

## Open doubts
- Bug 1 and bug 2 use one signal: `Job.front_end is None` means no source names a BMS. That covers both "the
  documents say nothing" and "the extraction missed it". The front-end question on Review.html is the safety net.
- Bug 2 adds the `"pending"` mode to `estimator.scope.FrontEnd`, which the old estimator path shares. The reader
  accepts a scope with no front-end heading only when the next paragraph is a block header or "ADD ALTERNATES:".
- Bug 3 keeps key passages without limit. A system with a very large number of tagged notes could produce a long
  prompt. A hard ceiling (for example 3x the limit) could be added if that shows up.
- Bug 5: if the AI writer later writes lines for a control-`none` system, it would show as both a block and a plan
  exception. Validate could flag that.

## Existing tests these patches intentionally contradict (continued, patch 06)
3. `tests/bms/test_plan.py::test_a_plan_only_split_unit_keeps_its_existence_question_in_the_block` asserts the
   exact question list. With the test **sample** Playbook, which has no Split shape, the "Split System (AC-1)"
   block now also gets the 6d "No Master Template family fits" question. The repo Playbook has a Split System
   shape.
4. `tests/bms/test_final_b.py::test_condensate_pumps_with_no_split_units_are_left_as_they_are` asserts that no
   question names CP-21. A stand-alone condensate pump has no shape in either Playbook, so 6d asks about it. R4
   gives the condensate pump a tie-in line under split, VRF or CRAC blocks. The owner should decide whether a
   stand-alone pump should be asked about (as patched) or left alone (as the test says).
