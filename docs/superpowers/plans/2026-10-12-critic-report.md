# Critic report: the estimating method, the app and the process that built it

Date: 2026-10-12. Written by an independent Fable critic at the estimator's request, from the brief
`2026-10-12-critic-brief.md`. Nothing was changed: no code, no tests, no Playbook, no job run. Every statement is
marked **verified** (seen in a file) or **suspected** (reasoned from documents). File and page evidence is in the
appendix. The body runs about 4,000 words, over the brief's 3,000, because the estimator asked for the whole process,
not one job.

Sources: the r2 output of 26-0544 traced back to its own PDFs; three finished archive jobs with markups and price
workups (26-0050 air handlers and VRF, 26-0154 boiler plant, 26-0236 VAV); the held-out job 26-0521; the next two
jobs; the Playbook, Brain, GEM, Master Template, rulings, plans and state files; the code of both apps.

## 1. The method as the estimator practises it

Steps marked E are the estimator's, A the app's. All verified unless marked.

1. **E: Make the takeoff folder.** Copy the mechanical set and the specification into `2. Takeoffs/1. Base Takeoff`.
   The copies are not always clean (26-0544 carries 15 highlights on the schedule remarks and coil details). The two
   next jobs have empty takeoff folders. The rule "the takeoff folder is the input" is not followed in the archive
   either: many jobs have markups but no clean copy.
2. **E: Mark up in Bluebeam.** One habit across 80 archive jobs: a count box per tag family per plan sheet with the
   tag list inside ("VAV: 13 x 1 = 13 [tags]"), a "DUPLICATE" box when a unit is drawn again on another sheet, "EX"
   boxes for existing units, and a green box on every point of the controls schematic as it is written. This is a
   takeoff register with part-plan handling built in. It lives in PDF annotations, which the app does not read.
3. **E: Write from the Master Template.** One block per system, "Qty (N) tag list" header, terse device lines,
   sub-counts inline ("-qty. 12 total"), one or two "*" notes per block for maker-supplied items. No "Assumed" or
   "Confirm" lines. Red marks filled-in fields, not uncertainty. The QC Checklist in each job folder is a blank form
   on every job I opened. Suspected to be unused.
4. **E: Price in the workup.** Tech hours once per block on the controller line (26-0050: 80 h per air handler, 4 h
   per VAV, 4 h per exhaust fan, 1.5 h per reheat coil), electrical subcontract once per block (42 percent of the
   26-0050 price), round material unit prices. The hours table exists only in the estimator's head.
5. **E: Read in no stated order.** No document states what is read first or which source wins. The Brain says the
   schedule is primary; the Playbook has no schedule rule and puts the sequence first; the markups tick the controls
   schematic. The job conditions (hours, wage, labor agreement) are read when they are noticed.

The archive proposals also carry human errors: 26-0050 writes "Furnish Supply Fan ECM Speed" twice where the second
should read Exhaust Fan; 26-0236 prints "Master Template" inside a block header. The human method has no second
reader either.

## 2. How the app was built and how it is run

This is the process the estimator asked to have criticised. Verified unless marked.

**Two apps in one.** The rebuilt app (`src/bms`) imports the older app's reading, ledger, inventory, dossier,
proposal and price-sheet code (`src/estimator`). The counting method is split across both: placements are counted in
`src/estimator/reading/inventory.py`, the register and the highest-count rule in `src/bms/takeoff.py` and
`plan_read.py`, the price match in `src/estimator/price_sheet/`. A rule about counting can live in either place, and
the Playbook, the code and the tests each hold a version of it.

**The whole Playbook is the system prompt of every AI step.** `rules.md` goes into the takeoff, write, QC and revise
calls entire. The GEM v4, which the estimator approved as "the method", is in no prompt; the line order comes from a
code table. The Master Template reaches the model only for the front end. So the model writes from a 700-line rule
book that contradicts itself in places (freezestat Furnish and Install at lines 104 to 110, Furnish and Wire at 375
to 380; count notes both forbidden and required) and never sees the document the estimator calls the method.

**What the model decides and what the code decides.** The model classifies every sheet (new work, demolition,
detail, schedule), gives each sheet an area, sets units aside, decides unit status, writes the lines, writes the tech
hours per block, and in QC judges the result. The code picks the highest admissible count, orders lines, runs the
validators and renders. The split is the wrong way round in two places: tech hours (a number the estimator sets by
table) are a model guess checked only for `>= 0`, and the set-asides (a reduction of a count) are a model decision
the code accepts with a reason string. The highest-count rule never lowers a count in code; the model can, by setting
a source aside or classing a sheet as not counting.

**Rulings on one live job as the teaching method.** 26 rulings on 2026-10-11 and 12, D1 to D9 on 2026-10-07, R1
to R22 on 2026-10-09, all from the output of one or two jobs. Six fixes landed after the r2 run and no run has shown
them. Code changed during the r2 run itself (a revise fix at 05:32, the run finished at 05:35). The next job will
produce its own 26 rulings, because the rules were written against layouts, not against the archive.

**No measurement.** The repo has `tools/measure.py` to match rendered lines against a finished proposal. It has never
been run on the rebuilt app; no result exists anywhere. The three held-out jobs went through the older app's
scoreboard on 2026-09-28. The suite has about 5,600 tests, and the takeoff characterisation test pins the current
counts (EF 16 to 5, AHU 21 to 5) after a change: the tests pin behaviour, not truth. The only oracle is the estimator
reading one proposal at a time.

**Outside agents and branches.** HarkPro and Grok work on their own branches through an inbox on GitHub. 16 worktrees
sit under `D:/EA-*`, two dirty, five branches unmerged into `rebuild`. The Master Template working copy is modified
and uncommitted. The lead rotates every 300k tokens and hands over in plan files; the plan folder now holds the
method in a dozen files that the Playbook does not reference.

**Chat mode as the only tested path.** A run makes about 29 AI requests (r2: 5 reading, 1 takeoff, 7 count, 9 write,
1 QC, 6 revise), each answered by a subagent on a model set per step, with 3 attempts. The run stops at the count
stage until the vision answers arrive. The estimator's review page then downloads a decisions file that must be saved
by hand into the out folder before a rerun. API mode is written and untested live. The cost of a run is known
(requests); the estimator's time per run is not recorded anywhere.

**The review loop asks the estimator to do the method's work.** The r2 review page has 29 questions. They mix
blocking scope questions (the removed fan coil count, the pump points) with style findings ("the clarification is 253
characters, over 220") and with questions the method should answer by rule (who wires a smoke detector status). A
reviewer who answers 29 questions per job has not been given a tool; the tool has been given a reviewer.

## 3. The app as a system

What is sound, verified: every fact in the ledger carries a citation; the register names every set-aside with both
numbers; the Evidence Package shows the source of each line; the highest count prints and the code never lowers it;
FUTURE items, owner contradictions and a foreign BMS print red; the AHU, exhaust fan, pump and valve counts and the
ERV coil bank grouping on 26-0544 are right against the PDFs.

What is weak by construction, verified:

- **Text first.** Counts come from the PDF text layer; vision runs only when the text count is short or absent and
  then confirms distinct tags, never placements. Symbol devices (thermostats, dampers, sensors) get no picture count.
  A scanned set has no text to count (26-0562).
- **Evidence is block-local.** A block sees the controls sections, the sequence and the schedule row. An equipment
  section (23 82 19 for fan coils) reaches a block only when its title matches a rule. Division 00 and 01 are searched
  by a word list; no AI reads them whole.
- **Ownership by words.** "Packaged" is decided by whether a fact says "unit mfr", "factory" or "packaged". The
  validator then forbids AME points on that system. A pump with a Taco starter becomes packaged.
- **Pricing is not built.** The price book has 114 names matched exactly; 56 of 63 r2 device names had no match. Tech
  hours are per block from the model. There is no table of hours per device anywhere in the repo.
- **The proposal carries the register.** Count breakdowns, "counted once" notes, "(likely a typical unit)" and
  "Qty (##)" print in the client document. The archive proposals carry none of it.
- **The front end has one shape.** Extend AME's own system, with house lines. There is no block for AME's controllers
  under another party's front end, and the red flag for a foreign BMS does not change what is written beneath it.

## 4. Where the method can fail

General faults, ranked by their chance of a low count or a missed scope item. 26-0544 is the evidence, not the
subject. Each has the cause and the better rule.

**1. Job conditions are not a step.** Hours, wage, labor agreement and phasing decide the labor price before any
device is counted, and the method has no step that settles them first; the app finds them by word list and prints
the template's normal-hours line regardless. Evidence: 26-0544 is all night work (every plan sheet, 01 14 00, the bid
form) under a Project Labor Agreement; r2 prints normal hours and excludes off-hours; at HEAD the off-hours line would
print but the normal-hours clarification stays and nothing knows a labor agreement. Better: a job-conditions pass
first, four fixed answers in the header and the price sheet, no block written until set.

**2. Devices named only in the equipment specification are not seen.** The sequence and the controls sections name
points; the equipment sections name the devices the maker ships or leaves to others. The method reads the first and
not the second. Evidence: 23 82 19 gives each fan coil "1 motorized control valve"; the r2 fan coil block has no
valve, 55 wirings missing; every archive fan coil block has it. Better: the equipment section of every scheduled
family is always part of that block's evidence.

**3. Exceptions to "higher count prints" are written as rules.** Ruling 21 prints the plan count for thermostats
"even when the sequence calls for more". The plan count is a text-layer count that vision never checks. Evidence:
the plan has 33 symbols (8, 11, 14), the app found 32, the sequence says 55. The rule meant to be cautious prints
low against its own source. Better: no exception prints below the higher count unless a picture count of every sheet
agrees with the text count and the estimator has confirmed it.

**4. Set-aside becomes unread.** Demolition sheets are set aside so they do not inflate new work, and nothing then
counts them for the Demolition Scope. Evidence: MD 111.00 to MD 113.00 carry 55 "(D)FCU" tags and 30 existing
thermostats in the text; Demolition Scope prints "Qty (1) AHU demo, Qty (1) EF demo"; the review asks the estimator
how many are removed. Better: demolition sheets feed a demolition register, and the Demolition Scope prints from it.

**5. Ownership has a list of cases instead of a rule.** Freezestats, filter switches, dampers, actuators, VFDs,
packaged sensors and the front end each have their own ruling, and "packaged" has no definition. Evidence: the pumps
were classed packaged on the word "TACO" and a must-fix told the estimator to remove 12 points; the Playbook gives
the freezestat two verbs. Better: one rule. A device is the maker's only when the documents name the maker as its
party; otherwise it is AME's, flagged where two sources disagree. Ruling 23 and the front-end rulings become
instances.

**6. The front end is a flag, not a decision.** A foreign BMS prints a red house line and the block is still written
as an extension of it. Evidence: the specification names Stark Tech "or approved equal", asks others for credentials,
and bars third-party front-end software on the existing Schneider system; r2 promises graphics, schedules and alarms
on it. Better: a front-end decision before writing (extend, integrate with points by BACnet and graphics by their
vendor, or no bid) that picks the block shape.

**7. Counting by eye is skipped where it matters most.** Where the drawing is text the app counts text; where it is a
picture it asks the estimator. Evidence: thermostats, the sixth motorized damper (existing, drawn grey), the circled
S, H and P duct tags on M114.00 all went to questions; 26-0562 has no text layer. Better: a picture count of every
tagged family on every plan sheet, with a picture count below the text count treated as a question, never a result.

**8. Pricing is unwritten.** The estimator prices by a table in the head; the app prices by exact name match and a
model's hours. Evidence: 54 of 61 r2 rows PRICE PENDING; the r2 hours have no source. Better: one hours-and-price
table per device name in the Playbook, a closed device-name list the writer must use, and electrical cost per block
as the estimator does it.

**9. Working notes print to the client.** The rulings that put count notes into the proposal (14, D6, 24) override
the estimator's own rule that hints never reach the client. Evidence: "(20 if every sheet of the same floor and area
is added up)", "*AHU counted once, labelled again on M610.00", "Qty (##)". Better: counts and sources in the Evidence
Package and the review page; one number per line in the proposal.

**10. The review does not rank.** Blocking scope questions, style findings and rule-answerable questions arrive as one
list of 29. Better: two lists, blocking and style; the run does not finish on a blocking question; a question the
Playbook can answer is not asked.

## 5. The rulings sorted

Rulings 1 to 26, D1 to D9, R1 to R22, the feedback of 2026-10-03/04. Table in the appendix.

- **General principle (would be written before any output), about 9 of 40:** undercount is worst; job documents
  decide scope; explicit assignment wins; one block per system; factory controls stay with the maker unless assigned;
  higher count prints with every count named; every line cites.
- **House style, about 12:** short "*" lines; "Qty (N) tag list" header; "(Qty. N Total)"; tech hours in Excel only;
  Demolition Scope last; pumps by service; front-end house lines; red for client-facing uncertainty.
- **This job only, dressed as general, about 7:** 21 (thermostats, from 26-0544's group control); 9 and 18 (pumps,
  from its one-pump-per-unit layout); 23 (freezestat and filter switch, from M620.00 notes 12 and 16); the VRF and
  duct heater rulings of 2026-10-04 (from 26-0193).
- **Reaction to an app defect, about 12:** 2, 3, 6, 7, 11, 22, 25, most of D1 to D9, R12, R22.

Conflicts and resolutions:

- **15 against 24.** 15: quantity in the line, no separate note. 24: "(Qty. N Total)", supersedes 15. D6 keeps a
  count note on its own line; `rules.md` says both. Resolve: 24 for device lines, nothing else.
- **3 against 21** (the brief's pairing). Ruling 3 is the header and shares no subject with 21. The real pair is the
  Playbook's "the only exceptions are demolition and part-plan duplicates" against 21's "the one exception". Resolve:
  drop 21 as a rule; keep it as the 26-0544 decision it was.
- **No fallback lines against house lines always carried.** `rules.md` says the template is never a reason for a
  line; `CLAUDE.md` and the GEM say the front end always carries graphics, training, warranty and the network panel.
  Resolve: a closed list of house lines in the Playbook, named as the one exception.
- **Freezestat Furnish and Install against Furnish and Wire.** Same file. Resolve with the ownership rule in fault 5.
- **One system per sequence section against VRF, split, pumps and Demolition Scope.** The exception list grows by
  ruling. Resolve: one block per scheduled family unless the documents put two families under one sequence.

Drop: 21, 15, D6's own-line count note, the "(N if every sheet is added up)" header text. Keep the principle rulings
as the Playbook's first page.

A corpus of finished jobs with a measurement would have caught the missing fan coil valve, the terse "*" style, the
per-block hours and the front-end shape; no ruling mentions any of them. Rulings transferred the estimator's
reactions to one layout. The archive holds 80 jobs with a final proposal and a marked set; the method is already
written down there.

## 6. A better workflow

The current path has the right shape in one respect: a register before writing, every count named. It is wrong in
where the estimator checks, in what the model is allowed to decide, and in what is measured.

1. **E, 10 minutes: job conditions.** Hours, wage, labor agreement, front-end decision, from Division 00 and 01 and
   the plan notes. The app proposes answers with citations. Nothing is written until set.
2. **A, one call per sheet and one per family: the register.** Text count and picture count of every tagged family
   on every plan sheet; demolition sheets into their own register; equipment and controls sections attached to each
   family. Both counts print where they differ. The app writes the register as Bluebeam-style boxes on a copy of the
   set, in the estimator's colours, so the markup step and the register become one thing and the estimator's existing
   80 marked sets become training and test data.
3. **E, 20 to 40 minutes: approve the register.** Accept or correct counts per sheet on the marked copy; answer
   blocking questions only. This replaces the markup step, which today costs an hour or more and yields data the app
   cannot read.
4. **A: write from the approved register.** Lines from the sequence, the schematic and the equipment section; hours
   and prices from a table keyed by device name; one number per line; client notes only. The model writes words, not
   counts, not hours, not set-asides.
5. **A, one call per block: a blind second pass.** A model that sees only the finished block and the block's
   documents lists what the documents call for and the block lacks. Misses print as blocking questions.
6. **Before every change and every live run: measure.** `tools/measure.py` against archive proposals of the job's
   kind (for 26-0544: 26-0050 and 26-0267). Share matched and missed lines print before the estimator sees anything.
   A change that lowers the share on the archive does not merge. This replaces rulings as the teaching method.
7. **E: sign off.** Corrections go into the Playbook table and the archive measurement, not into the Word file.

Cost against today's 29 requests: about 55 to 60 calls (one small Sonnet call per plan sheet, one per block). The
estimator spends 30 to 50 minutes before the write instead of an unknown time after it. It buys a register approved
before a word is written, a second reader for the device the writer missed, and a change test against 80 finished
jobs instead of one live one. Vision on every sheet does not lose: the text layer is not the drawing. Approving the
register first does not lose: it moves the estimator's work earlier and shortens it. The second pass has no downside.
The measurement costs nothing per run and is the only step that makes the next 26 rulings unnecessary.

## 7. Is the app ready to produce a bid

**No. A run of 26-0544 today gives a proposal the estimator can correct into a bid, not one to sign after small
corrections.** Reasons in order of weight:

1. Method, verified: all night work under a Project Labor Agreement; the proposal says normal hours and no agreement.
2. Method, verified: 55 fan coil control valve wirings missing; the equipment section is not read.
3. Method, verified: no front-end decision; the proposal promises work on a Schneider front end AME does not do.
4. App, verified: 54 of 61 price rows pending and tech hours a model's guess. There is no price to sign.
5. Method, verified: the thermostat rule prints 32 where the plan shows 33 and the sequence says 55.
6. Method, verified: Demolition Scope 1 and 1 where 55 fan coil units and 30 thermostats come out.
7. App, verified: a must-fix on the pumps would remove 12 points if accepted.
8. App, verified: count notes and "##" print to the client; an editing pass is needed before it leaves the office.
9. App, suspected: T-008 to T-010 landed after r2 and no run has shown them end to end.

Right, and not to be touched: the AHU and exhaust fan counts; the pump and valve tags and their grouping (CV-11,
CV-12, P-11, P-12 on the ERV coil bank); the controller furnished for factory installation; the Taco starter and
relay-panel integration lines; the FUTURE items in red. All verified against the PDFs.

## 8. Before the next run of 26-0544

Only what blocks a sign-off:

1. Decide the front end: integrate to the County's Schneider system as an approved-equal controls contractor, graphics
   by Stark Tech, or no bid. The estimator's call; no run can make it.
2. Labor conditions: 6PM to 6AM and weekends, prevailing wage (01 29 00), Project Labor Agreement (Exhibit K), one
   phase at a time (M114.00). Drop the normal-hours clarification when off-hours is set.
3. Fan coil control valve (23 82 19) and aquastat (M520.00 detail 8): Qty (55) each.
4. 55 thermostats, or 33 only after the estimator confirms group control from the plan pictures.
5. Demolition Scope from the demolition sheets: 55 fan coil units, 30 thermostats, AHU-6, EF-6.
6. Working notes out of the proposal text, into the Evidence Package.
7. Price by hand in the workup. The app's price sheet is not ready.

## 9. Before 26-0559 and 26-0562

Both takeoff folders are empty; the documents sit in `1. Project Documents`. Verified.

26-0559 (tenant floors, NYC): no specification book; the specification is on sheets M-600 to M-605; no 23 09
section. "Wiring and BMS integration to be provided by base building BMS controls vendor"; the vendor list says "BMS
Vendor: Not applicable"; no platform is named. The radiator scope contradicts itself across four sheets. VAV boxes
come with Titus digital controls. The owner pre-buys equipment. Verified. The method has no rule for a scope split
between a tenant's controls contractor and a landlord's vendor, nor for a specification that lives on the drawings.
The app's section filters will find nothing to attach.

26-0562 (public, CUNY): almost no text layer; one sheet is a bitmap. No equipment sequence, only an energy-code
sequence naming units that do not exist. VAV controllers "Neptronic or equivalent" wired to a panel per air handler.
Relocated and existing boxes with new thermostats. Verified. The app counts text first; here there is no text.
Without picture counts on every sheet this job cannot be counted by the app at all.

Neither job has a fan coil, an ERV, a hydronic pump or a coil bank. Both have VAV terminals, DX units, radiator
valves, bipolar ionization and leak-detection interlocks, none of which 26-0544 exercised. No ruling of the last two
days touches any of them. The archive has dozens of VAV jobs; 26-0236 alone has 81 boxes in four sub-types with a
finished proposal and markups.

## 10. Do not do

- No more rulings from 26-0544. The next two jobs share no family with it.
- No further tuning of the thermostat, pump or part-plan rules on this job. Measure against the archive instead.
- No work on the price book's alias list before a closed device-name list exists. Free text against 114 names will
  keep failing.
- No API mode before the chat-mode output is signable. It changes cost, not correctness.
- No cleaning of the 16 worktrees under `D:/EA-*` now. They block nothing.
- No count notes back into the proposal in a new form. The Evidence Package is the place.
- No more rule text into `rules.md` without removing the sentence it replaces. The file already says both sides of
  three questions.
- Do not treat the r2 proposal file as the run's output. It was saved in Word after the run.

---

## 11. Appendix

### A. Archive comparison: one block, 26-0050 air handlers against 26-0544 r2 air handlers

| | 26-0050, estimator (AC-1 thru 6) | 26-0544 r2, app (AHU-1 thru 5) |
|---|---|---|
| Header | "Qty (6) AC-1 thru 6" | "Qty (5) Air Handling Unit AHU-1 thru 5 (5 per M620.00; 20 if every sheet of the same floor and area is added up)" |
| Controller line | "Furnish and Install DDC Controller" first | "Furnish Terminal Unit Controller to the Factory for Installation" after a valve line |
| Sub-counts | inline "-qty. 12 total" | separate "Qty (10) Control Valve CV-1 thru 10" line, then two valve lines again |
| Notes | none | 2 "*Confirm", 3 "*Assumed", 2 "*counted once", 5 sub-bullets |
| Red | header fields and BMS name | FUTURE items, smoke detector status, drain pan sensor, house line |
| Lines | 37 | 27 plus 12 notes |
| Error in the estimator's own | "Furnish Supply Fan ECM Speed" written twice (should read Exhaust Fan) | |

The archive block is terse and complete. The app block is complete on devices (the fan coil block is not) and
verbose on notes.

### B. Count traces, 26-0544 (independent of the Evidence Package)

| Item | App r2 | Documents | Where | Verdict |
|---|---|---|---|---|
| AHU | 5 | AHU-1 to 5 scheduled; AHU-6 demolition only | M620.00 p20; MD 114.00 p6 | right |
| FCU | 55 | "FCU-1" 11 + 20 + 24, text | M111.00 to M113.00 p10 to 12 | right |
| Thermostats | 32 (sequence 55) | 33 "T" symbols, 8 + 11 + 14; one per room with group control (note 5); sequence 3.07 "each fan coil unit shall be provided with a remote, wall-mounted thermostat" | p10 to 12; Binder p429 | app text count low by 1; rule picks the lower source |
| Removed FCU | asked | 55 "(D)FCU", 30 existing T | MD 111.00 to MD 113.00 p3 to 5 | missed count |
| FCU control valve | no line | "1 motorized control valve" per unit | Binder p480, 23 82 19 | missed scope |
| Pipe sensor | "##" | aquastat with immersion well on the fan coil detail | M520.00 p18 detail 8 | 55 |
| EF | 5; 6 dampers | EF-1 to 5; 6 "MD", one grey existing | M114.00 p13 | right; the sixth is existing |
| EF controller | 5 red + note | sequence 3.04 "shall be provided with a BACnet compatible controller"; schematic puts the points on the AHU controller | Binder p427; M710.00 p22 | both readings carried, acceptable |
| Pumps, valves | 6 + 6; 10 valves + 2 on ERV | P-1 to 12, CV-1 to 12; P-11, P-12, CV-11, CV-12 scheduled "AHU-6", flows match ERV coils C-1, C-2 | M630.00 p21; M620.00 p20 | right |
| Taco wiring | 5 | notes 7 (TAS on odd pumps), 8 (CP-1 on P-11), 9 (CP-2 on even) | M630.00 p21 | right |
| AHU controller ownership | furnish for factory install | note 8 M620.00; Binder p422 3.01.A.8 | | right |
| Hours | normal, off-hours excluded | 6PM to 6AM weekdays, anytime weekends (every sheet; 01 14 00 p182; bid form p6) | | wrong |
| Labor agreement | none | Project Labor Agreement, Exhibit K p54 to 81 | | missing |
| Prevailing wage | 01 29 00 | 01 29 00 1.04.I p193 | | right |
| Front end | extend Schneider; red house line | Stark Tech "or approved equal" p410; credentials p409; "no third party front-end workstation software" p408 | | decision not made |

### C. Ruling sort (short form)

Principle: CP undercount worst; JI job inputs; GM1 factory controls; R2, R19, R21 end devices AME's unless
assigned; 10-1 evidence only; 10-2 highest prints; 13 Master Template format and GEM order; D2 Playbook beats
validators; D9 value is highest.
House style: 5, 14, 15, 16, 17, 18, 19, 22, 24, 26, D1, D8, R12, F04-4 "*Assumed gives reason".
This job only: 21, 9, 18, 23, F04-1 VRF one block, F04-3 duct heater once, R20 narrowed.
Reaction to the app: 1, 2, 3, 4, 6, 7, 10, 11, 12, 20, 25, D3 to D7, R22, 10-4 "fix 36 serious".
Conflicts: 15/24; 21 against "never undershoot"; no fallback against house lines; freezestat 104-110 against
375-380; one block per sequence against VRF, pumps, Demolition Scope; 9 against 18; R20 against 23.

### D. Requests per run

| Run | Requests | Split | Notes |
|---|---|---|---|
| r1 (2026-10-11) | 26 | not recorded | 3 of 10 count answers were invalid JSON |
| r2 (2026-10-12, 05:35) | 29 | 5 reading, 1 takeoff, 7 count, 9 write, 1 QC, 6 revise | 3 re-dispatched; code changed during the run; models opus except count on sonnet |

### E. Other verified facts used above

- Two apps: `src/bms` imports `src/estimator` reading, ledger, inventory, dossier, proposal and price-sheet code
  (`CLAUDE.md`; `src/estimator/reading/inventory.py:536-568` counts placements; `src/estimator/price_sheet/price_book.py:46`).
- Playbook as system prompt of every step: `src/bms/playbook.py:98`. GEM v4 in no prompt; order from
  `assets/gem_order.json` (`src/bms/render.py:737-835`). Master Template lines only for the front end
  (`assets/front_end.json`, `src/bms/ai.py:2108`).
- Model decides register, set-asides, lines and tech hours; code checks hours only for `>= 0` (`src/bms/ai.py:1284`);
  highest count in code (`src/bms/plan_read.py:357`); model may count below the schedule floor with a cited reason
  (`src/bms/takeoff.py:231-236`); `admit` drops set-aside entries (`takeoff.py:627, 675-690`).
- Vision: `src/bms/counts.py:234-239, 289-294, 393-402, 565-571`; thermostats get no vision count; thermostat text
  count from "T"/"TB" words (`assets/reading_lists/devices.json`, `takeoff.py:488-547`).
- Off-hours: `src/bms/labor.py:33-38, 74-76`; the template normal-hours line stays (`src/estimator/proposal/write.py:38`);
  no PLA or union detection in `src/` or `playbook/`.
- Packaged: `src/bms/plan.py:1004`, `validate.py:195-235`; the r2 pump blocks are "packaged".
- Equipment sections: `src/estimator/catalogue/spec_sections.py:34-39`; `assets/reading_lists/sequences.json:3-5`;
  Division 1 by word list (`src/estimator/catalogue/overview.py:736`).
- Price book: 114 items, 75 aliases, exact match; 56 of 63 r2 names unmatched; PRICE PENDING at
  `src/estimator/price_sheet/write.py:98-100`.
- Reading order: no source states it; Brain `Quantity rules.txt:7` schedule primary; `playbook/rules.md:35-40`
  sequence first. Thermostat rule `rules.md:254-259`. No fallback `rules.md:27-29` against `CLAUDE.md:113-115` and
  `assets/gem/BMS_DDC_GEM_v4.txt:396-400`. Freezestat `rules.md:104-110` against `375-380`.
- Build process: state file `2026-10-11-evening-state.md:60-97`; fixes after r2 at 06:15 to 15:32 IST; revise fix
  e08f799 at 05:32:54 during the run; `tools/run_job.py:239` starts a new process per status call; 16 worktrees
  (`git worktree list`), five branches unmerged; `tests/bms/test_takeoff.py:559-568` pins EF 16 to 5, AHU 21 to 5.
- Measurement: `tools/measure.py` has no recorded result in docs, tools, tests, reviews or git log; held-out jobs
  26-0521, 26-0422, 26-0256 have older-app runs of 2026-09-28 under `out/test/`.
- Chat mode: `.claude/run-job.json` (opus for reading, takeoff, write, revise, QC; sonnet for count;
  `max_attempts` 3); `src/bms/run.py:1-15` stages and the wait at count; decisions via download and rerun
  (`src/bms/review.py:4, 698`).
- r2 proposal docx last saved in Word by the estimator at 09:53 on 2026-10-12.
- Archive: 80 jobs with a final proposal and a marked set; 54 with a filled price workup; 26-0050's price
  ($1,015,075) equals its workup; electrical subcontract 42 percent. Bluebeam count boxes with tag lists and
  "DUPLICATE" boxes on 26-0521 (1,193 markups), 26-0050 (206), 26-0236 (470); green boxes on every point of the
  26-0050 controls schematic M-204.00.
- `Brain/Master Template.docx` working copy modified and uncommitted ("Mandatory for VAVs", "Standard if BMS is
  there"). `playbook/shapes.json:15` and the sample Playbook `wording.json:10` still mention `{qty}`.
- Next jobs: `2. Takeoffs/1. Base Takeoff` empty on both; 26-0559 specification on sheets M-600 to M-605, "BMS
  Vendor: Not applicable", base-building vendor does integration (M-400); 26-0562 near-empty text layer, Neptronic
  VAV controllers (M-401), no equipment sequence.
