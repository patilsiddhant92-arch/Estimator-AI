# House rules, round 2 — implementation plan (2026-10-04)

**Spec:** the estimator's rules of 2026-10-04, appended to `assets/gem/ame_practice.txt` (paragraphs "ONE SYSTEM,
ONE BLOCK — VRF AND SPLIT SYSTEMS", "BMS SPACE TEMPERATURE SENSOR ON AC UNITS", "ELECTRIC DUCT HEATERS — ONE CLEAR
WRITE-UP", "ASSUMPTIONS GIVE THEIR REASON"), plus the earlier rules in the same file, and the open items found in the
26-0193 re-run (out/test/26-0193/shape2, shape3). Where this plan and those rules disagree, the rules win.

**Goal:** the next proposal writes a VRF system and a split system as one block each, gives every assumption its
reason, stops printing a BMS space sensor on every AC unit by default, writes duct heaters in one place, prints
sequence-only systems as "Qty (##)" blocks, keeps plan-only names short and prints clean quantity notes.

## Global constraints

- Python 3.13, package `estimator` under `src/`; run everything with `.venv/Scripts/python.exe` from the repo root.
- Test-first (RED then GREEN) for every behaviour change; full suite `.venv/Scripts/python.exe -m pytest tests -q -p no:cacheprovider` must pass at the end of each task (it is ~1473 tests, ~2.5 min).
- Job documents are under NDA: never copy job text into the repo, tests or reports. Tests use invented jobs (the existing fixtures' style: "Job 26-9999", "VAV-1 thru 3", "EF-1, 2").
- Never push. Commit on the current branch `step-5-follow-ups` with a message ending in the line
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Plain words in every printed text and review row; no invented codes; no emoji.
- No per-job tuning: rules are general (they must hold on any job), never keyed to 26-0193's tags.
- The Master Template is the frame for how a system looks; the job's documents decide what is in scope. No Master
  Template line ever stands in for a block the writer left empty (commit 10bfbed).
- Never undershoot a count: when a count cannot be worked out, the header prints "Qty (##)" with a review row; it
  never prints a smaller guess.

## Rulings already made (by the controller, from the estimator's words)

- **Space sensor:** the Master Template's Split System line "Furnish and Install Space Temperature Sensor (BMS
  Monitoring)" stops being a default; it becomes a conditional line printed only when the documents call for a
  BMS-furnished space sensor.
- **Duct heaters:** they get their own block (the heater family's block), never lines in the served unit's block.
  Each heater's scope follows what decides it: an explicit sequence item giving the BMS the heater's control (for
  example "the BMS will provide field installed controls for the electric duct heater") means full field-DDC heater
  scope, even on a packaged or factory-controlled unit; otherwise the house rule holds (interlock only on a packaged
  unit, full scope under an AME DDC controller). The estimator accepted this after reading the 26-0193 ERV reference.

## Task 1: VRF and split systems as one block each

Files: `src/estimator/ledger/to_plan.py`, `src/estimator/writing/assemble.py` (template matching only),
`tests/test_ledger_plan.py` (and a test file of your choice for template matching).

Today a `group` fact's value is split on commas and each piece must equal a family subject exactly. A riser judge
writes members with their tags, e.g. `ACCU (ACCU-12-1 thru 6), HRU (HRU-3 x3, HRU-4 x3), AC (AC-2.0, AC-3.0, AC-4.0), WAC-1.0, WAC-1.5`,
so only the bare names joined and the VRF printed as four blocks.

1. **Read group members with their tags.** Parse a group's value into members: split on commas that are not inside
   parentheses; each member is `PREFIX` or `PREFIX (tag list)`. Tags in the list are expanded the usual way
   (`expand_tags`); a "TAG xN" / "TAG ×N" item gives that tag a unit count of N. A member whose prefix is no family
   subject (case-insensitive) is ignored, as today.
2. **Whole family or part of it.** If the member lists no tags, or the listed tags are not a proper subset of the
   family's own tags (none of them match, or they cover all of them), the whole family joins the group (today's
   behaviour). If the listed tags are a proper subset of the family's own tags, the family is split: a part with the
   listed tags joins the group, and the rest stays a system of its own with the remaining tags.
3. **Counts of a split family, never undershooting.** The group part's quantity is the sum of the "xN" counts the
   group fact and the ledger's `link` facts give for its tags (a tag counted in several facts is summed across them;
   the same fact is read once); when no fact gives a count for a listed tag, the part's quantity is None ("Qty (##)",
   and the planner adds an unresolved question naming the family and tags). The rest keeps the family's printed count
   minus the part's count when both are known and the difference is at least the number of remaining tags; otherwise
   it keeps the family's own printed count, unchanged. Both parts keep the family's facts.
4. **Split systems are one block.** After the groups are formed, the families no group took whose prefix is a split
   system's indoor prefix (AC, CAC, IU, SS, FCU is NOT one) or outdoor prefix (ACCU, CU, OU, ODU) — the Master
   Template's Split System entry `applies_to.prefixes` is the source of truth; read it, do not hard-code a second list
   — join one group named "Split System". If the ledger's sequence matches put those families in two or more
   different sequence sections, form one "Split System" group per section (named "Split System — <section name>"),
   and a family matched to no section joins the group whose families share a tag suffix with it (AC-LOBBY-1 and
   ACCU-LOBBY-1 share "LOBBY-1"), else the first group. A lone family with no partner stays on its own.
   Plan-only families (their ledger count is ADDED, "seen on plans, not scheduled") join like any other.
5. **The VRF group takes the VRF template.** A system whose kind or group name contains the word VRF or VRV, or whose
   families include a branch selector / branch circuit controller prefix (BS, HRU, BC), takes the Master Template's
   "VRF System" entry in `system_template` (today it fell to Geothermal by nearness). Split System groups take the
   "Split System" entry. Tech hours and frame lines then follow those entries.
6. **Headers.** A group prints one stacked header per family (existing behaviour), each with its own count and tags.
   Use the template's `family_names` for the family word when the family's own name is a long description.

Tests (invented job): a group "VRF-A" with value `CU (CU-1 thru 4), BS (BS-1 x2), AC (AC-1, AC-2)` over families CU
(tags CU-1..CU-6, count 6), BS (BS-1, count 2), AC (AC-1, AC-2, AC-9, count 5) and links "AC-1 x3, AC-2 x1" →
one group system with families CU part (CU-1..CU-4, quantity None → question; or give it via "CU-1 thru 4" if your
rule reads ranges as one each — decide and test it), BS whole, AC part (AC-1, AC-2, quantity 4); the AC rest (AC-9,
quantity 1 = 5-4) and CU rest (CU-5, CU-6) then join a "Split System" group with each other; a kind "Acme VRF system"
gets the VRF System template; a sequence-split case gives two Split System groups. Update existing tests only where
the old behaviour is the one this task changes.

## Task 2: every assumption gives its reason

Files: `src/estimator/writing/assemble.py` (`_plain_assumption`, `flag_review`, `block_clarifications`,
`_listed`), `src/estimator/writing/whole_job.py` (`GEM_OUTPUT` flag sentence), `assets/gem/BMS_DDC_GEM_v4.txt`
(the FLAGS section: one sentence), tests.

1. **The writer gives the reason.** In `GEM_OUTPUT` and the v4 FLAGS section, say: for ASSUMED, `flag_text` is
   "ASSUMED: <what is assumed> — because <the reason, in a few plain words naming the document or the missing
   information>". Keep the rest of the flag rules.
2. **The clarification keeps it.** `_plain_assumption` returns "<what>, because <why>" when the flag text gives a
   reason after "because" (or after " — " when the text after it reads as a reason), cleaned the same way the "what"
   is today (client words only; rule names, source ids, confidence never print). It returns None when no client-safe
   reason can be found; then no "*Assumed" note prints for that line and the review row says the assumption has no
   reason to print.
3. **No hiding.** The block's one "*Assumed:" clarification lists every assumption with its reason, separated by
   "; ", with no "and N more" cut. One assumption stays at most 160 characters (cut at a word, never mid-reason; if
   the reason does not fit, it does not print and goes to the review row). The "*Confirm quantities:" note keeps its
   current 60-character list with "and N more" (the estimator raised no issue with it).
4. A bare "*Assumed: <device>" (no reason) never prints.

Tests: a line flagged orange with "ASSUMED: duct static sensor shipped loose — because the schedule shows no factory
sensor" prints "*Assumed: Duct static sensor shipped loose, because the schedule shows no factory sensor"; two such
lines in one block give one note with both; a flag with no reason prints no note and its review row says so; the
v4/GEM_OUTPUT text carries the new sentence (extend `tests/test_gem_v4.py`).

## Task 3: the BMS space sensor is conditional

Files: `assets/system_templates.json` (Split System entry), tests.

1. The Split System line "Furnish and Install Space Temperature Sensor (BMS Monitoring)" loses `"default": true` and
   gets `"when": ["bms_space_sensor"]`, with a condition `bms_space_sensor` whose `sequence` phrases are ones that
   name a sensor the BMS furnishes for the unit ("BMS space temperature sensor", "space temperature sensor furnished
   by the BMS", "BMS contractor shall provide a space temperature sensor", "provide space temperature sensor for BMS
   monitoring" — choose a short list that does not match "wire the manufacturer's space temperature sensor").
2. Check every other entry the Split System line pattern appears in (VRF System, PTAC, Packaged AC, etc.); the same
   rule applies wherever the line is a default on an indoor AC unit. Report which entries you changed.

Tests: the Split System entry's defaults no longer include the line; a sequence naming a BMS-furnished space sensor
makes it appear; one saying the BMS contractor wires the manufacturer's space temperature sensor does not.

## Task 4: duct heaters written in one place

Files: `src/estimator/ledger/to_plan.py`, `src/estimator/writing/brief.py`, `src/estimator/writing/house_check.py`,
`src/estimator/writing/whole_job.py` (write prompt text, only if the brief cannot carry it), `assets/gem/ame_practice.txt`
(the 2026-10-03 ELECTRIC DUCT HEATERS paragraph), tests.

1. **The heater block sees the served unit's sequence.** In `ledger_plan`, a duct heater family (the house style's
   `duct_heater_words` decide what is a duct heater) that the ledger links to the units it serves gets those
   systems' `sequence_sources` and `sequence_match` fact ids added to its own (each once), so its writer reads the
   served unit's sequence section.
2. **Served units do not write heater lines.** The brief for a system served by a duct heater family says: "The duct
   heaters serving this unit (<tags>) are written in the <heater header> block; write no duct heater line here." In
   `house_check`, a duct heater line in a block that is not the heater's own block, on a system whose heater family
   exists in the plan, is refused with that reason (a review row, as other refused lines).
3. **The heater's scope follows what decides it.** In `house_check`, the interlock-only cut for a heater block whose
   served class is packaged does not apply when the heater block's evidence holds a sequence sentence giving the BMS
   the heater's control (a sentence naming the duct heater together with "BMS" or "controls contractor" and
   "provide"/"field installed controls"/"control"). Keep the patterns in `assets/house_style.json`, not in code.
   The brief for the heater block says, per served unit, which rule applies and why (the sequence item, or the
   house rule).
4. **The practice rule says it.** Amend the ELECTRIC DUCT HEATERS paragraph of `ame_practice.txt` (2026-10-03) by one
   sentence at its end: "When the sequence explicitly gives the BMS the heater's control (for example 'the BMS will
   provide field installed controls for the electric duct heater'), AME writes the full duct heater scope even on a
   packaged unit: explicit assignment always wins (the estimator, 2026-10-04)."

Tests (invented job): an ERV-like packaged unit with a heater family linked to it and a sequence sentence giving the
BMS field-installed heater controls → the heater block keeps full scope lines; the same without that sentence →
interlock only (today's behaviour); a heater line written in the served unit's block is refused with the new reason;
the heater system's sequence sources include the served unit's.

## Task 5: the leftovers

Files: `src/estimator/ledger/passes.py`, `src/estimator/ledger/to_plan.py`, tests.

1. **Sequence-only systems print as "Qty (##)".** The sequence pass instruction today lets the judge add a family
   only when the section states a count. Change it: the judge adds a family (kind and name, no count fact) for a
   system the section gives the BMS work on and no family in the live list covers (plumbing pumps, domestic water
   heaters, heat tracing, gas booster, glycol feed, generator); a count fact only when the section states one. Such a
   family plans as today's sequence-only system (why "Named in the sequence of operation; no drawing shows it.",
   quantity None, "Qty (##)", per-drawings note).
2. **Plan-only names stay short.** In `to_plan`, a family value like "seen on plans, not scheduled: <description>
   (<reasoning>)" or "seen on the risers, not scheduled: …" gives the header and kind the short description only:
   drop the "seen on …, not scheduled:" lead, drop any parenthetical, and keep at most the first 8 words of what is
   left (cut at a word); the full value stays in the system's `why` text and the ledger. The plans and risers pass
   instructions also ask the judge for a short kind name and to put reasons in a note fact.
3. **Quantity notes read cleanly.** `count_note` / `place_words` / `_other_count` never print an unbalanced or empty
   parenthesis; a quote that is the tool's own counts line ("schedule rows N; QUANTITY column total —; distinct tags
   N; plan placements N (sheet n; …)") is said as "plan placements N" (or "schedule rows N"), without the per-sheet
   list. A damper block whose count dropped because fans claimed some of its dampers gets the note
   "*Qty. (<left>) not claimed by a fan; (<total>) per <place>, <claimed> of them listed under their fans." instead
   of the plain count note.

Tests: the pass instruction text (the new sentence); a plan-only family value with lead and parenthetical gives a
short header; a counts-line quote gives "plan placements 16"; the damper-block note; no "()" in any note produced by
the existing count-note tests.
