# Architecture review, 2026-10-11: where judgement lives, and the smallest change that moves it to the AI

Code: `D:/EA-wave2` at 28a966c; `git diff 0e78113 HEAD -- src` is empty, so every `src/` line is lead/wave2
0e78113. Output: `out/26-0544/` (NDA, this machine only).

## Headline finding

The AI already judged 26-0544 correctly. The code overruled it.

- The ledger's plans pass wrote: "Five new air handlers (AHU-1 to AHU-5) and five exhaust fans (EF-1 to EF-5) are
  in the penthouse mechanical room, and ERV-1 is on the penthouse roof; AHU-6 and EF-6 are existing units shown for
  demolition only" (Ledger.json `understanding.plans`).
- Its note facts agree: F90 (AHU-6 demolition only, new units AHU-1 to AHU-5), F108 (EF-6 likewise), F110-F113
  (FCU-1 11 + 20 + 24 = 55), F117 ("33 new thermostats on the construction plans"), F92 (demolition controls work),
  F174 and F176 (graphics, training), F181 (AFMS and static sensor marked future).
- Nothing downstream reads them. `ledger.understanding` is used only by later ledger passes
  (`estimator/ledger/passes.py:164`) and the Evidence Package (`estimator/evidence/workbook.py:149`). The planner
  reads note facts only for questions, exceptions, alternates and duct heaters (`bms/plan.py:74`, `:680-687`,
  `:1587-1595`, `:1648`). The plans pass may only *add* counts, never settle them (`passes.py:63`).
- The planner then prints the highest number from any source (`bms/plan_read.py:302-309`, `max(n for n, _ in
  entries)`), and the counts cross-check "never lowers a count" (`bms/counts.py:16`). A regex count of 21 beats the
  AI's 5.

The fault: the AI's judgement is untyped free text, and "highest wins" lets any code count override it. The fix:
make the AI's takeoff typed, cited and binding on which sources a count may use.

## 1. Where judgement lives in code today

| # | Place | What it decides | Input it sees | What it cannot know | 26-0544 defect |
|---|---|---|---|---|---|
| 1 | `estimator/catalogue/sheet_types.py:66-69` with `assets/reading_lists/sheet_types.json:13` | sheet type (Plans, Demolition, ...) | the title words only | whether a demolition sheet names work on a unit | MD sheets typed both "Plans" and "Demolition" |
| 2 | `estimator/reading/inventory.py:686-694` (`placements`), `estimator/writing/dossier.py:845-851` | which sheets are counted | sheet types | — | only `"Schedules"` is left out (`inventory.py:690`; `dossier.py:848` takes any "Plans"); MD 114/214/315 counted |
| 3 | `inventory.py:413-428` (`_place_facts`), `:434-443` (`_same_floor_and_area`), `:446-463` (`_one_plan`), `:279-280` (3 shared tags, 60 %) | which sheets show one area | title words, tag overlap | that "EQUIPMENT PENTHOUSE PLAN" and "DUCTWORK PENTHOUSE PLAN" are one room | I ran `_place_facts` on the titles: M114 gives other words `('CONSTRUCTION',)`, M314 gives `('CONSTRUCTION','EQUIPMENT')`, M315 gives floors `('PENTHOUSE','ROOF')`. Three areas, plus two demolition areas. AHU-1..5 counted per area: 21. ERV-1 (one tag, no tag overlap possible) on three areas: 3 |
| 4 | `inventory.py:56-64` (`counted_per_place`), thresholds `:40-41` | unit tag or type tag | label counts per sheet (3 places, 4 on one sheet) | what the schedule says the tag is | FCU-1 right by luck of numbers; AHU-n counted once per area |
| 5 | `inventory.py:497-512` (`plan_count`) | count = sum over groups | the groups from #3 | — | multiplies #3's errors |
| 6 | `bms/plan_read.py:302-309`, `:313-328` | printed count | every number from every source | which sources are admissible | 21 prints over schedule 5 and AI 5 |
| 7 | `bms/plan.py:6`, `:13-14` | one system per tag prefix; only dampers move under a fan | ledger families, link facts | that valves serve AHUs, that P-1..12 are two services | CV-1..12 its own block; pumps one block named "Sequence Of Operation - Chilled Pump" |
| 8 | `plan.py:45`, `:1105-1116` (`_GLOBAL_WORDS`) | global points | sequence section title words | an OAT sensor named inside the AHU sequence is one job-wide point | no Global Points block; OAT and OA RH written per AHU, Qty 21 |
| 9 | `plan.py:1456-1461` (`_FRONT_END_ITEM`), `:1464-1499`; `bms/ai.py:1664-1665` | front-end lines | provider facts by keyword; "a line is written only when the evidence calls for it" | house lines (panel, graphics, training, warranty) the Master Template always carries | front end has one wiring line; no panel, graphics, training |
| 10 | `estimator/writing/front_end.py:370-373` | Quote # and Reference | `catalogue.job.root` folder name split on "," | that the takeoff folder is not the job folder | "Quote #: 1. Base Takeoff", "Reference: [project name]" |
| 11 | `bms/ai_evidence.py:174-188` (`_about`), `:190-307` | what evidence a writer sees | tag and name regex per system | job-wide facts that name no tag (changeover, OAT, demolition work) | missing aquastat, demolition lines; FCU writer told only "FCU-1" passages |
| 12 | `bms/review.py:166-182` | one card per flagged device | `device.quantity.others` | that 22 lines share one family count | 23 AHU cards |

HarkPro T-005a fixes #2, #3, #5 and #6 with better rules. It cannot fix the class: each new title form needs a new
rule.

## 2. What the AI sees when it writes a system

- One request per system (`bms/run.py:564-568`): skeleton JSON, shape text, heater text, evidence
  (`bms/ai.py:820-835`). The skeleton's count (21) and tags (AHU-1..6) are fixed: "Copy key, name, shape, control,
  families ... exactly as given" (`prompts/write_system.md:8`).
- The evidence is a regex selection by tag and name (`ai_evidence.py:190-307`), notes and spec capped at 12,000
  characters each (`:21-22`).
- It does not see the other systems, the ledger understanding, uncited notes (F90, F117, F181), sheet classes or
  the rulings.
- Master Template: the writer gets only the shape's slot names and print forms (`ai.py:790-811`). It never gets the
  template block text, its OR lines, its "*"/"**" notes or its tech-hour line. The front-end writer does get the
  template's front-end lines, but as "house wording and order only" (`ai.py:1664`).
- GEM order: not given. "Order the devices in the shape's line order" (`write_system.md:26`). The shapes copy the
  Master Template's order, but every catch-all slot (`other_device`, `other_point`, `fire_alarm`, `other_valve` ...)
  sits after the valves (`playbook/shapes.json`, Air Handling Unit `line_order`). The AHU writer put the OAT and
  OA RH sensors and the drain pan sensor in `other_device`, so they print after the valves (proposal lines 33-37).
- No word on FUTURE, red, demolition, OR lines, Miscellaneous, off-hours or prevailing wage. "Never write a line
  because systems of this kind usually have one" (`write_system.md:12`) conflicts with the GEM: "Leave a template
  line out only when the documents exclude it" (see Open points).

## 3. What `model.py` allows

| Need | Today | Gap |
|---|---|---|
| Sheet classification | `Job.source_sheets` is sheet numbers only (`model.py:249`) | no class, area, or "counts for units" |
| Unit identity across sheets | `Family.tags` + one `Count` (`model.py:117-121`) | no unit row, no aliases, no status (new / demolish / existing / future), no sheets per unit |
| FUTURE flag | `Flag` = none, quantity, ownership, assumed (`model.py:27`) | no "future" and no source for it |
| Red-flag lines | no colour on `Device` or `Clarification`; the scope `Run` has `text` and `bold` only (`estimator/scope.py:19-23`) | red cannot be printed; 26-0544 has no red run at all, the existing name included |
| "*" note with both counts | `Count.others`, `Count.added_up` (`model.py:97-106`) | data is there; render splits it (see 4) |
| OR line | `System.alternate` is base/add/deduct for a whole block (`model.py:184`) | no alternative between two lines |
| Miscellaneous section | `Job` holds systems, front end, exceptions, questions (`model.py:237-249`) | no place for GEM Category B work (demolition of controls, panel reuse) |
| Off-hours, prevailing wage | none; the Word template excludes "All off-hours or overtime labor" (proposal line 110); no "prevailing" in `playbook/` or `src/bms` | no field, no rule |
| Estimator hint ("**") vs client note | `ClarificationKind` confirm, assumed, per_drawings, note (`model.py:28`) | no hint kind that stays off the client copy |

## 4. Render: ours against the Master Template

**Example 1, AHU.** Template: "Qty (##) Air handling Unit AHU", controller, sensors, fan signals, switches,
filter DP, AFMS, dampers, valves, "(**tech hour: 2 hour each hardware point)". Ours: "Qty (21) Air Handling
Unit AHU-1 thru 6"; OAT, OA RH and drain pan sensors after the valves; smoke detectors last; "Supply Fan VFD Speed"
for the template's "VFD control"; three "*" lines (proposal lines 40-42), two of them count notes that repeat each
other; no tech-hour line. The OAT belongs once, in the template's "Qty (1) Global Points" block ("Furnish and
Install Outside Air Temperature").

**Example 2, Fan Coil Unit.** Template: "Qty (2) Fan Coil Unit FCU", "Furnish and Install DDC Controller", "Furnish
and Install Space Temperature Sensor", "Furnish and Install Discharge Temperature Sensor", "Furnish Fan Start / Stop
(low, med, hi) and Status", "Furnish and Wire Filter DP Switch", valves, "**tech hour: 4 hours per fcu". Ours: "Qty
(55) Fan Coil Unit FCU-1", "Remote Wall-Mounted Thermostat (Qty. 61 Total)" (template wording is a space sensor;
the count should be 33 per F117), "Pipe Temperature Sensor (Qty. ##)", "Control Valve and Actuator" with
"*Assumed: one control valve ... per fan coil unit".

**Example 3, Front end (extension).** Template: "Seamlessly Tie in to the Existing Honeywell / Niagara N4 BMS",
"Furnish Network Level Control Panel", "Furnish 3-D Graphics to match existing", "Furnish Necessary Training on New
Controls", then the warranty lines. Ours: "Seamlessly Tie in to the Existing Schneider Electric BMS (existing, with
existing network area controller NAC-1) BMS" (the ledger's whole value pasted, "BMS" twice), one wiring line, and a
long "*Confirm ownership" paragraph. Schneider is not WEBS, FX or Niagara: by ruling it prints red with ***.
Nothing is red.

Gaps that sit in render or the Playbook files, not in the writer (T-005e must close them there):

1. Several "*" lines per block. `bms/render.py:654-678` (`_notes`) prints one "*" line per kind plus a separate
   quantity note, and every device assumption adds to the "assumed" line. GEM: "write one '*' clarification per
   block".
2. Catch-all slots print after the valves. `render.py:582` sorts by `shape.line_order`; the shapes put
   `other_device`, `fire_alarm` and the like at the end. The GEM order must place them (sensors at 2, leak at 4,
   fire alarm at 13, valves at 16).
3. No red. `estimator/scope.py:19-23` `Run` has no colour, so FUTURE, non-AME BMS, off-hours and prevailing-wage
   lines cannot print red whatever the writer does.
4. No tech-hour line, no OR line, no Miscellaneous section in the renderer's block form.
5. Exclusions are the Word template's fixed list ("Any demolition work not ... mentioned" twice, proposal lines
   132, 146); the GEM wants sequence items only.

## 5. Decision input: two options

Both keep code for bookkeeping (reading, citations, ledger, counting labels, render, price) and move four judgements
to the AI: sheet class, area identity, unit identity and status, and unit-to-unit service.

### Option A: whole-job takeoff pass, binding on counts

Insert one AI step after the ledger is complete and before `plan_job` (`run.py:500-509`).

- **New files.** `src/bms/takeoff.py` (request, schema, intake checks), `src/bms/prompts/takeoff_job.md`.
- **Input.** The whole ledger (facts and understanding), every sheet (number, title, the code's type guess and
  label tally), schedule rows, keynotes, sequence headings, the rulings. 26-0544: 214 facts, 724 sources, 59,000
  characters: one request.
- **Output.** `sheets`: per sheet, class (new_work, demolition, part_plan, enlarged, riser, schedule, detail, other),
  area name, `counts_units` yes/no, refs. `units`: per unit, family prefix, id, labels seen, status (new, demolish,
  demolish_with_work, existing_remain, future), sheets, serves (AHU-1 for CV-1), service (chilled water, hot water),
  refs. `devices`: per device kind tied to a family (thermostats), the admissible sheets.
- **Code changes, deterministic.** `inventory.placements` already takes `pages` (`inventory.py:670-671`) and
  `plan_count` takes a groups map (`:497`): pass the admissible pages and the AI's area groups. `plan_read._count`
  takes only admissible sources; the "highest prints" rule stays, over admissible sources. Excluded counts stay in
  the reading notes with both numbers, so no drop is silent. `plan.py` takes tags from the register (AHU-6 out),
  moves served valves under their unit, and splits a family by `service`. The writer evidence gets the system's
  register rows and the ledger understanding (`ai_evidence.py`, one block).
- **Intake checks (code).** Every plan sheet classified; every scheduled tag in the register; every ref real; a
  count below the schedule refused unless a cited fact says why; a count below the code tally makes one family
  question.
- **model.py.** Add `Job.sheets: tuple[SheetClass, ...] = ()` and `Job.units: tuple[Unit, ...] = ()`, default
  empty. Add `"future"` to `Flag`. Optional fields only: old Job files still load. Contract tests change.
- **Risk.** Medium. A misclassified sheet is caught by the intake checks and the family card; the schedule floor
  guards undercount. Prompt caching (`ai.py:22-23`) keeps cost low.
- **Coexistence with HarkPro.** T-005a's rules become the code's first guess shown to the AI, and the path when the
  register is empty (fixtures). T-005b..e keep their purpose. Land A after T-005a..e merge. The lead writes the
  `run.py` and `model.py` parts (CLAUDE.md rule 4).
- **Estimate.** 5 to 7 executor-days (takeoff step 2, wiring 2, model 0.5, run-job skill 0.5, tests and rerun 1-2).

### Option B: AI also plans the blocks and the scope per unit

As A, plus the AI returns the block plan: which units form each block, which Master Template entry it follows,
served devices, global points, Miscellaneous items, sequence-only exclusions. `plan.py`, `plan_groups.py` and most of
`plan_read.py` (about 2,600 lines) become checks on the AI's plan. The writer gets the template entry text, the GEM
order and the whole-job register in every request.

- **Files.** A's, plus `plan.py`, `ai.py` prompts, `validate.py`, `review.py`, `render.py`, the plan tests.
- **model.py.** A's fields, plus `System.template_entry`, `System.units`, `Job.misc`, an OR group on `Device`.
- **Risk.** High. Many tested rulings (VRF, duct heaters, dampers under fans, split pairs) live in `plan.py` and
  must be re-proved. Part of T-005a and T-005d is thrown away.
- **Estimate.** 12 to 18 executor-days.

### Recommendation: A, now

- The evidence shows the AI already gets the judgement right; the loss is in plumbing, not in reasoning. A fixes
  the plumbing.
- A reaches the count acceptance (AHU 5, EF 5, ERV 1, FCU 55, thermostats 33), puts valves under units and splits
  pumps, with testable code after one AI step.
- Header, red, off-hours, prevailing wage, one card per family and template format are not judgement problems:
  T-005b/c/e plus the gaps in 3 and 4.
- Decide B after 26-0559 and 26-0562; B would build on A's register.

## 6. The independent critic

**Today.** `qc_job` (`ai.py:1864-1898`, `prompts/qc_job.md`) gets the written job as JSON, the text of the sources
it cites only (`ai.py:1822-1848`), the rule names, the shapes' slot names and the mechanical findings. `validate.py`
checks fields only, never wording (`validate.py:1-7`). So the critic:

- cannot find a missing line whose source nothing cites (OAT, aquastat, demolition work);
- never sees the printed proposal, the Master Template, the GEM or the rulings, so format drift is invisible;
- has no register, so it cannot say "AHU-6 is demolition".

**What a template-and-evidence critic needs.** (1) The rendered lines with their trace (`render.py:82` already
traces them). (2) Per block, the Master Template entry, the GEM order and QC-01 to QC-10, and the rulings. (3) The
register and sheet classes. (4) All ledger facts and the uncited facts, not only cited sources. (5) A fresh context
and its own prompt. It returns findings by printed line, mapped to device ids for the one revise round.

## Open points for the lead

1. **House lines vs evidence-only.** The GEM says write the template entry's lines unless the documents exclude
   them; `write_system.md:12` and `ai.py:1664` say write only what the evidence calls for. CLAUDE.md rule 3 allows
   house lines for the front end. The estimator should say which blocks carry house lines.
2. **"Highest prints"** over admissible sources only is a change in meaning: a Playbook rule for the estimator.
3. **Front end ownership.** Ledger F191 gives front-end integration to the owner's contractor; HarkPro and Grok
   still print panel, graphics and training. The estimator rules.
