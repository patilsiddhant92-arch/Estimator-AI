# GEM v4: what changed from v3.2 (spec §9.1)

**Status: approved by the estimator on 2026-10-03.** Version 4 replaces version 3.2 as the method. Version 3.2 stays in `assets/gem/` for comparison only.

Copied from the Task 1 implementer's report on 2026-10-03; the rewritten text is assets/gem/BMS_DDC_GEM_v4.txt.

# Task 1 report: the GEM in plain language (v4)

Status: DONE. Commit `27fe997` on `step-5-follow-ups`, not pushed.

## What I wrote

`assets/gem/BMS_DDC_GEM_v4.txt` (new, about 30,000 characters). It is a sentence-by-sentence rewrite of v3.2, not a summary:
- It keeps the same method and every rule. Each sentence carries one idea.
- It has no emoji, no "★", no "◊" and no "[?]" marks. The checkmarks in v3.2's QC-04 example became the word "present".
- Flags are words everywhere: CONFIRM QUANTITY, CONFIRM OWNERSHIP, ASSUMED, NOTE.
- v3.2's C2 "CONFIRM VERB" and C3 "CONFIRM SCOPE/EXCLUSION" were yellow flags. They are now CONFIRM OWNERSHIP, with the sentence naming what has to be confirmed (the verb, or scope against exclusion).
- "CC" became "the controls contractor". WHO YOU ARE says that on these estimates this is AME, and that the sections the tool adds call it CC.
- The chat mechanics are left out: RESET PROTOCOL, the auto-start note, Phase 2 clean SOW, the display table and the hardware highlight option. None of the `GEM_CUTS` strings start a line in v4, so every cut finds nothing and is skipped.
- The practice rules of 2026-10-03 are written into the sections they refine. The table below names each one.
- `SOW ORDER — STANDARD TEMPLATE` opens with the frame rule. It is worded as the brief gives it and ends "Never a line per monitored point".
- These names are unchanged: the Quick Scan's eight fields, C1–C6 by type name, and QC-01..QC-10 by check name.

`src/estimator/writing/whole_job.py`:
- `GEM_FILE` now points at `BMS_DDC_GEM_v4.txt`. v3.2 stays in the repo.
- In `GEM_OUTPUT`, the flag sentence now reads `flag: "red" for CONFIRM QUANTITY, "yellow" for CONFIRM OWNERSHIP, "orange" for ASSUMED, "green" for NOTE, or "" for none.`
- Two small extra edits in `GEM_OUTPUT`, so it agrees with v4:
  - "without the flag symbol" became "without the flag";
  - "depth … 2 for a line one level in (the ◊ line)" became "(the manufacturer's representative line)".
- `_FLAG_SYMBOLS`, `_DIAMOND`, `GEM_CUTS` and `gem_prompt()` are unchanged.

## Side-by-side: every v3.2 rule heading against v4

| v3.2 heading | v4 heading | Change |
|---|---|---|
| BMS/DDC CONTROLS ESTIMATION GEM / v3.2 / ★ CHANGES IN v3.2 (5 items) | File header "What changed from version 3.2" (outside the prompt) | reworded. v3.2's five changes (references, VFD fault, C1–C6, evidence QC) are now part of the method itself. The auto-start part is dropped (chat mechanics). |
| WHO YOU ARE | WHO YOU ARE | reworded. Adds what "the controls contractor" means (AME) and that the AME PRACTICE rules govern where they are more specific. |
| RESET PROTOCOL | none | dropped (chat mechanics) |
| AUTO-START BEHAVIOR / ★ NO MENU | none | dropped (chat mechanics). Its order (Quick Scan, then System Explanation, then scope) is kept in SYSTEM EXPLANATION. |
| STEP 0 — PROJECT QUICK SCAN (MANDATORY BEFORE ANY SCOPE) | STEP 0 — PROJECT QUICK SCAN (ALWAYS, BEFORE ANY SCOPE) | reworded. The eight fields keep their names, written in Title Case (see concern 3). The Unit Type values are unchanged ("Field-Installed DDC", "Factory/OEM Controls"), because assembly reads their first words. |
| CONTRACTOR NAME RULE | CONTRACTOR NAME RULE | reworded ("flag 🟡" became "flag CONFIRM OWNERSHIP") |
| PRE-SCOPE CC WORK EXTRACTION (MANDATORY — run as part of Quick Scan) | PRE-SCOPE WORK EXTRACTION (ALWAYS, AS PART OF THE QUICK SCAN) | reworded |
| CATEGORY A / CATEGORY B | Category A / Category B (same section) | reworded |
| INPUT HANDLING — SEQUENCE AND POINT LIST | INPUT HANDLING — SEQUENCE AND POINT LIST | reworded. The `PRIORITY RULE:` label is kept as written. |
| POINT LIST INTEGRATION RULE (MANDATORY) | POINT LIST INTEGRATION RULE (MANDATORY) | refined by practice rule OWNERSHIP ANSWERS (2): on a packaged unit the integration lines cover a hardwired signal. The heading text is unchanged, so CONNECTING THE DOTS and the practice rules still go in before it. |
| SCOPE OWNERSHIP — PRIMARY RULE | SCOPE OWNERSHIP — PRIMARY RULE | reworded |
| DEVICE OWNERSHIP RESOLUTION — UNIVERSAL RULE (QUESTION 1/2/3) | DEVICE OWNERSHIP RESOLUTION — UNIVERSAL RULE (QUESTION 1/2/3) | reworded |
| BLANKET WIRING CLAUSE | BLANKET WIRING CLAUSE | refined by practice rule OWNERSHIP ANSWERS (1): a device installed at the factory is never a line, blanket clause or not. It becomes "Wire … (Furnished by Unit Mfr.)" only when the sequence assigns that wiring. |
| VERB ASSIGNMENT — based on Q1 + Q2 + Q3 | VERB ASSIGNMENT — FROM THE THREE ANSWERS | reworded |
| EXPLICIT ASSIGNMENT ALWAYS WINS / MIXED OWNERSHIP | same | same / reworded |
| DAMPER ACTUATOR RULE — DISTINCT TYPES, DISTINCT LINES | same heading, plus a new sub-heading WHERE DAMPER ACTUATORS GO | refined by practice rules DAMPER ACTUATORS — AME PRACTICE and DAMPER ACTUATORS — WHERE THEY GO: the actuator goes under the fan it serves; a damper that cannot be traced goes in a block of its own with sheet references, total count and a flag; fire/smoke dampers keep their own block. The 🔴 in the examples became "flagged CONFIRM QUANTITY". |
| FEEDBACK SIGNALS — HARDWIRED FURNISH POINTS | same | refined by practice rule OWNERSHIP ANSWERS (2), one sentence: these lines are for a system AME's own DDC controller runs |
| VERB RULES — ASSIGNMENTS AND FORMAT (the table; FURNISH AND INSTALL; FURNISH; FURNISH AND WIRE; INSTALL AND WIRE; WIRE) | same heading and sub-headings, plus OTHER TRADES IN BRACKETS | The table became four sentences. FURNISH is refined by OWNERSHIP ANSWERS (2). INSTALL AND WIRE is refined by SHIPPED-LOOSE DEVICES: "(Furnished by Unit Mfr.)". WIRE is refined by OWNERSHIP ANSWERS (1). OTHER TRADES IN BRACKETS is new, from OWNERSHIP ANSWERS (3). |
| FIRE ALARM AND LIFE SAFETY INTERFACE — COMPLETE RULE (STEP 1–3) | same, plus SMOKE CONTROL — UL-864 UUKL | reworded. The UUKL rule is from practice rule SMOKE CONTROL (UL-864 UUKL). |
| FACTORY CONTROLS — COMPLETE RULE (QUICK SCAN DECLARATION; items 1–4; NOT CC SCOPE) | PACKAGED UNITS — FACTORY CONTROLS (QUICK SCAN DECLARATION; WHAT IS INSIDE THE UNIT IS NOT A LINE; items 1–4; ELECTRIC DUCT HEATERS) | Refined by practice rules PACKAGED UNITS — WHAT AME DOES, FACTORY CONTROLS — AME PRACTICE, SHIPPED-LOOSE DEVICES, OWNERSHIP ANSWERS (1)(2) and ELECTRIC DUCT HEATERS. Item 3 changed: v3.2 made a blanket clause alone a Wire line; v4 needs the sequence to assign that wiring. The three integration lines cover every "monitor … at the BMS". There are no Furnish <point> lines on a packaged unit. |
| MANDATORY MINIMUM POINTS — ALWAYS INCLUDE (v3.2), with its ★ VFD fault note | MANDATORY MINIMUM POINTS — ALWAYS INCLUDE | reworded. The VFD fault note became plain sentences. Refined by OWNERSHIP ANSWERS (2): the minimums are for equipment AME's own DDC runs. |
| FANS — UNCONDITIONAL / FANS — CONDITIONAL | FANS ("Always written…" / "Written only when…") | reworded |
| PUMPS — UNCONDITIONAL / PUMPS — CONDITIONAL | PUMPS | reworded |
| BOILERS / CHILLERS / COOLING TOWERS | same | same |
| REFERENCE LINE FORMAT (v3.2) / ★ SEPARATE INDENTED LINE / EXAMPLES | REFERENCE LINE FORMAT | reworded; the examples are the same |
| PHASE 2 — CLEAN SOW | none | dropped (chat mechanics) |
| CONTRADICTION AND ASSUMPTION SCAN (MANDATORY — before Self-QC), C1–C6 | CONTRADICTION AND ASSUMPTION SCAN, C1–C6 by name | Reworded, and moved after MISCELLANEOUS RESPONSIBILITIES (see concern 1). C2 and C3 now carry CONFIRM OWNERSHIP. The text says the scan still runs before the Self-QC and before the scope is given. |
| SELF-QC — EVIDENCE-BASED (v3.2), QC-01..QC-10 | SELF-QC — EVIDENCE-BASED, RUN BEFORE EVERY SCOPE IS GIVEN, QC-01..QC-10 by name | reworded and moved (concern 1) |
| DISPLAY FORMAT — after every SOW output | none | Dropped (chat mechanics). Its closing lines are kept: "If any check shows FAIL: state the issue and the fix applied." is unchanged, and "until all Tier 1 checks show PASS" became "until every check passes". |
| SOW ORDER — STANDARD TEMPLATE (POSITION 1–20) | SOW ORDER — STANDARD TEMPLATE (THE MASTER TEMPLATE ENTRY IS THE FRAME; THE STANDARD ORDER 1–20) | Refined by the frame rule (brief; spec §2.2) and practice rule PACKAGED UNITS — WHAT AME DOES. The positions became a numbered list. "Device names from the documents" is kept. |
| INTEGRATION LINES — FIXED GROUP, NEVER MODIFIED | INTEGRATION LINES — FIXED GROUP, NEVER CHANGED | reworded. "◊ Controls Contractor requires mfr. rep …" became the same words, indented, introduced as "the manufacturer's representative line, written one level in". |
| MISCELLANEOUS RESPONSIBILITIES | MISCELLANEOUS RESPONSIBILITIES | reworded (🟢 became NOTE, 🔴 became CONFIRM QUANTITY, 🟠 became ASSUMED) |
| FLAGS — INLINE WITH SEQUENCE SNIPPET | FLAGS — WORDS, WITH THE SEQUENCE SNIPPET, plus ONE CLARIFICATION PER BLOCK | refined by practice rule FLAGS IN THE DRAFT: one "*" clarification per block, naming the lines; per-line detail in the Evidence Package |
| A&C FORMAT / EXCLUSIONS | ASSUMPTIONS AND CLARIFICATIONS — FORMAT / Exclusions | reworded (the flags are words) |
| ADDITIONAL RULES — NAMING, SENSORS, FILTERS, CONSOLIDATION | same | see the sub-rows |
| DEVICE NAMING — EXACT SEQUENCE LANGUAGE | same | reworded |
| VFD FAULT NAMING RULE | same | reworded |
| START/STOP AND STATUS — RELAY AND CURRENT SWITCH RULE | same | reworded |
| SENSOR NAMING — COMBO VS SPLIT | SENSOR NAMING — COMBINED OR SEPARATE | reworded |
| FILTER DP SWITCHES | same | same |
| CONSOLIDATING IDENTICAL SCOPE LINES | same | same |
| QUANTITY DETAILING | same, plus SYSTEMS NAMED ONLY IN THE SEQUENCE | Refined by practice rule CONTRADICTED COUNTS: the higher count prints, flagged, with both counts named. The new sub-section is from SYSTEMS NAMED ONLY IN THE SEQUENCE: base bid, "Qty (##)", "*Quantity per plumbing drawings". (superseded 2026-10-09: the schedule's count prints, a different count is a DISCREPANCY flag; the higher prints only with no schedule) |
| SOW FORMAT — STANDARD | same | reworded ("flags always on the same line" became "the flag stays with the device's own line") |
| SYSTEM EXPLANATION | SYSTEM EXPLANATION | reworded |
| OPTION: SEQUENCE HARDWARE HIGHLIGHT | none | dropped (chat mechanics) |
| END OF INSTRUCTIONS — v3.2 | END OF INSTRUCTIONS | The version suffix is gone, because the new test needs the prompt to end with `GEM_END`. |

Some practice rules are not folded into v4. They still reach the prompt whole through `ame_practice.txt`, as before:
- SPLIT SYSTEMS AND VRF;
- VRF SYSTEMS;
- RESIDENTIAL EQUIPMENT IN THE HUNDREDS, including the electric unit heater line;
- the 4-hour tech-hour rule. The GEM leaves tech hours to the template rule and `GEM_OUTPUT`.

## Tests: RED, then GREEN

RED, `.venv/Scripts/python.exe -m pytest tests/test_gem_v4.py -q` before v4 existed:
```
FAILED tests/test_gem_v4.py::test_the_tool_loads_v4 - AssertionError: assert ...
FAILED tests/test_gem_v4.py::test_v4_has_no_emoji_or_marks - AssertionError: ★
FAILED tests/test_gem_v4.py::test_v4_keeps_the_headings_in_order - AssertionE...
FAILED tests/test_gem_v4.py::test_v4_folds_in_the_estimators_rules - Assertio...
FAILED tests/test_gem_v4.py::test_the_prompt_still_starts_and_ends_at_the_anchors_and_carries_the_output_section
5 failed, 1 passed in 5.33s
```
These failed for the stated reason: `GEM_FILE` was still v3.2. `test_v4_flags_are_words` already passed on v3.2, because v3.2's A&C format spells out "CONFIRM QUANTITY" and the other flag words.

GREEN:
```
.venv/Scripts/python.exe -m pytest tests/test_gem_v4.py -q                 -> 6 passed
.venv/Scripts/python.exe -m pytest tests/test_gem_v4.py tests/test_gem_round.py tests/test_gem_round2.py tests/test_whole_job.py -q
                                                                            -> 85 passed in 4.55s
.venv/Scripts/python.exe -m pytest -q                                       -> 1393 passed in 131.28s
```
I made one wording edit to v4 after the full suite (the contradiction scan's "run before the Self-QC" sentence). After it I re-ran the GEM files plus `test_next_batch.py`: 110 passed.

## Existing tests changed, and why

- `tests/test_gem_round.py::test_the_gem_is_copied_into_the_assets`: `GEM_FILE.name` is now `BMS_DDC_GEM_v4.txt`. It also asserts that v3.2 is still beside v4.
- `tests/test_gem_round.py::test_the_system_prompt_is_the_gem_without_its_chat_mechanics`, three quotes updated:
  - `endswith("END OF INSTRUCTIONS — v3.2")` became `endswith("END OF INSTRUCTIONS")`.
  - "No named party + packaged/factory controls unit" became "No party is named, on a packaged or factory-controls unit: it is the unit manufacturer's scope."
  - "POSITION 19 — INTEGRATION LINES (always last within scope)" became "19. Integration lines (always last within the scope)".
- `tests/test_whole_job.py::test_the_write_prompt_gives_the_controls_contractor_what_no_one_else_is_named_for_on_a_field_ddc_unit`:
  - "No named party + field DDC unit → CC furnishes it." became "No party is named, on a field DDC unit: the controls contractor furnishes it."
  - The packaged quote changed as above.
  - This file is not in the brief's `git add` list. It quoted v3.2 wording, so it is included in the commit.

All other quoted phrases were kept word for word in v4, so their tests are untouched. These include "PRIORITY RULE:", "POINT LIST INTEGRATION RULE (MANDATORY)", "EXPLICIT ASSIGNMENT ALWAYS WINS.", "Default format: (Qty. ## Total)", "Unknown quantities: (Qty. per Mechanical Schedule) / (Qty. per Drawing)" and "never invent a number".

## Files changed

- `assets/gem/BMS_DDC_GEM_v4.txt` (new)
- `src/estimator/writing/whole_job.py`
- `tests/test_gem_v4.py` (new)
- `tests/test_gem_round.py`
- `tests/test_whole_job.py`

## Concerns

1. **Section order.** The brief's heading list, which the test enforces, puts SOW ORDER, INTEGRATION LINES and MISCELLANEOUS before CONTRADICTION SCAN and SELF-QC. In v3.2 those two came before SOW ORDER. I followed the test and moved them. v4 says outright that both still run before the scope is given. The estimator should know the reading order changed.
2. **The rep line without "◊".** `parse_scope`'s `_DIAMOND` needs the ◊, so a v4 answer's "Controls Contractor requires mfr. rep …" line is no longer swapped for the house line in `parse_scope`. Assembly's `_REP_LINE` does swap it, because it accepts the line without ◊, and it also forces depth 2. A small follow-up would make the ◊ optional in `_DIAMOND`. I did not change it, because it is outside the brief.
3. **Quick Scan field labels are in Title Case** ("Blanket Wiring Clause:"). An all-caps "BLANKET WIRING CLAUSE:" in the Quick Scan would come before its section heading and break the order test. The field names themselves are unchanged. The same goes for references to "Miscellaneous Responsibilities" before that heading.
4. **The Install and Wire form changed.** v3.2's "(Furnished by [trade], Shipped Loose)" is now "(Furnished by [trade])", and "(Furnished by Unit Mfr.)" for the unit maker, as the estimator's shipped-loose rule writes it.
5. **The prompt still has emoji.** `GEM_CONNECTING` in the code is the tool's own addendum, not part of the GEM file. It still says "flag 🔴" and uses arrows. The brief limited the code change to `GEM_FILE` and `GEM_OUTPUT`, so I left it. A one-word follow-up ("flag CONFIRM QUANTITY") would make the whole prompt free of emoji.
6. **No flag word for untraceable dampers.** The practice rule says only "flagged for the estimator", so v4 says that without choosing a flag word.

## Fix report (review round 1): commit `ab17620`

1. **No glyph in the assembled prompt.** In `GEM_CONNECTING` (`whole_job.py`):
   - "flag 🔴 and write" became "flag CONFIRM QUANTITY and write".
   - Every "→" became words ("means the unit is …", "needs a scope line", ": write …").
   - "×" became "times", "§3.4" became "paragraph 3.4", and "*…" became "*...".
   - `GEM_OUTPUT` had no glyph left. The assembled `gem_prompt()` now has no character outside ASCII except the em dash.
   - New test `test_the_assembled_prompt_has_no_glyph_or_arrow` checks three things: no match for the EMOJI regex in `gem_prompt()`, no "→", and that "flag CONFIRM QUANTITY and write" is present.
   - `tests/test_gem_round.py::test_the_gem_connects_the_dots_with_the_other_documents_after_its_input_handling` had two quotes updated: "(Plan count, M-101 times 10 floors)" and "(Spec 23 09 23 paragraph 3.4)".
2. **The rep line is recognised without its diamond.** `_DIAMOND` is now `^\s*(?:◊\s*)?(?:the\s+)?(?:controls\s+contractor|cc)\s+requires\s+mfr\.?\s+rep\b`, so the ◊ is optional, as in `_REP_LINE`. The `_diamond` docstring now says so.
   - New test `test_the_rep_line_without_its_diamond_is_the_house_line_one_level_in` sends a depth-1 "Map Available Points …" line, then "Controls Contractor requires mfr. rep to assist in integration, cost to be incurred by mech contractor" with no ◊.
   - It checks that the second line comes out as ("AME requires mfr. Rep to assist in integration, cost to be incurred by mech contractor", 2).
3. **v4 wording.** The SOW FORMAT reference line is now "indented, in parentheses". It was "in brackets".
4. **v4 flags section.** New sentence: "The flag word goes in the answer's flag field, never in the text of the scope line."

RED, with `whole_job.py` stashed and the new tests run on the old code:
```
FAILED tests/test_gem_v4.py::test_the_assembled_prompt_has_no_glyph_or_arrow
FAILED tests/test_gem_v4.py::test_the_rep_line_without_its_diamond_is_the_house_line_one_level_in
2 failed, 6 passed
```
GREEN:
```
.venv/Scripts/python.exe -m pytest tests/test_gem_v4.py tests/test_gem_round.py tests/test_gem_round2.py tests/test_whole_job.py -q  -> 87 passed
.venv/Scripts/python.exe -m pytest -q                                                                                              -> 1395 passed in 131.10s
```
Files changed:
- `assets/gem/BMS_DDC_GEM_v4.txt`
- `src/estimator/writing/whole_job.py`
- `tests/test_gem_v4.py`
- `tests/test_gem_round.py`

Two other places in v4 still say "in brackets", both about naming the furnishing party ("(Furnished by Unit Mfr.)"). I left them, because that is the estimator's own wording in the practice rule "Devices by other trades are named in brackets".
