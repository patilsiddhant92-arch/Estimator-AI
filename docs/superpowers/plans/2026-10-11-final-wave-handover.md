# Handover 2026-10-11: final development wave (for a new Fable session)

Written by the Opus lead session at the end of 2026-10-11. Read this first, then CLAUDE.md, memory
(`rulings-2026-10-11-first-run`, `front-end-bms-names`, `private-repo-job-data-ok`, `rulings-2026-10-10`), and the
Master Template and GEM in `Brain/`.

## 0. First task for the Fable lead: review CLAUDE.md

The estimator wants the Fable lead to review `CLAUDE.md` and edit it to suit this project and the final wave: remove
rules that block good output or waste effort, keep the ones that protect quality (tests first, the Playbook is the
estimator's, plan before large changes), and make it short and current. Show the estimator the changes in a few
lines; edit after their yes. The Opus lead already relaxed four lines on 2026-10-11 (house lines from the Master
Template, agent limits, quoting job lines in chat, the current plan).

## 1. State of the code

- `rebuild` = ce07960 (pushed): Wave 1 fixes (schedule reading, titles, sequences, plan areas under ruling L1,
  count notes, review page, `Count.added_up`, code-review fixes).
- `lead/wave2` = 0e78113 (pushed, not merged into `rebuild`): `rebuild` + WS4 (tag ranges, stated-count forms,
  schedule alternates), WS5 (front end planned/written/revised, revise counts, EXCEPTION lines, opening name), WS7
  (Playbook edits approved 2026-10-10), coverage gate (HarkPro T-001 + review, wired into run and review page),
  HarkPro T-002 (price book from the revised AME workbook) and T-003 (count-box parity fixes). Full suite 4,825 pass.
- Not merged: `hark/T-001b` (coverage gate: no citation by bare prefix) waits for review.
- Tests: `-n 10` (pytest-xdist installed), about 7 minutes. CLAUDE.md updated.
- Worktrees from today: D:/EA-wave2 (lead/wave2), EA-ws1, ws23, ws6, ws4, ws5, ws7, countsum, rv-read, rv-bms, wire,
  t001 (lead/t001-review), fix1010, hark-inbox. All merged except as noted; clean-up is still Phase 4 of the
  2026-10-10 plan.

## 2. The first live run (26-0544) and what it showed

Output: `out/26-0544/` (proposal, price sheet, Evidence Package, Review.html). Run time about 1 h 45 min in chat mode.
The estimator's verdict: not good enough. Counts against HarkPro's and Grok's proposals (they agree):
AHU 21 vs 5; EF 10 vs 5; ERV 3 vs 1; FCU 55 = 55; thermostats 61 vs 33.

Root causes found (details in `HarkPro/inbox/T-005-rootcause.md` on `lead/hark-inbox`):
- A numbered unit tag is counted once per plan group, so AHU-1..5 on four sheets = 20. Demolition sheets are never
  filtered (only Schedules are). Two part plans of one area read as two floors.
- Review page: one question card per device that repeats the family count (23 AHU cards).
- Header: Quote # and Reference parsed from the takeoff folder name, not the job folder.
- Missing lines HarkPro/Grok print: demolition work lines, global OAT, ERV freezestat and smoke status, EF VFD,
  changeover aquastat, front-end network panel / graphics / training. Wrong lines: FCU valves and pipe sensor.
- Format: the Master Template's scope-of-work format and the GEM's order of points were not followed.
- Writer: "Assumed" where the schedule states the fact; FUTURE items not flagged; long flag paragraphs (906 chars).
- Process faults in the chat run: subagents wrote invalid JSON (3 of 10 counts), one opened the wrong file, and
  they shared one temp folder. Fix the run-job skill prompt: write with Python json.dump, unique temp names.

The estimator's 13 rulings of 2026-10-11 are in memory `rulings-2026-10-11-first-run`.

## 3. Work in flight at HarkPro (lead/hark-inbox)

T-005 (a counting, b blocks/questions, c proposal/render/model, d writer/evidence) + T-005e (Master Template format,
GEM order, off-hours and prevailing wage), with the addendum (three-proposal comparison) and the root causes. Base
`origin/lead/wave2`. Branches `hark/T-005a`..`e`. HarkPro checks the inbox every 10 minutes; it pushes `hark/*` only.
T-004 (HarkPro's method) is answered: schedule-first counting, independent critic, valves under units, pumps split.

## 4. The lead's honest diagnosis (why progress was slow)

1. Built blind: tests on invented fixtures only and no live job until 2026-10-11, so real-document defects stayed
   hidden. Two days went to triage-list fixes before one end-to-end run.
2. House practice was not written down (demolition rule, red flags, front-end lines, valves under units). The
   Master Template and GEM hold much of it, and the lead did not check the output against them.
3. Strict rules were read too literally ("no standard lines", "no job data in git").
4. Architecture: judgement is done by regex code (which sheet is demolition, which tag is a unit or a type, which
   sheets show one area), and the AI writes one system at a time without the whole job. That is the wrong way round.
5. Cost: one long lead session (400k+ tokens of context) re-read on every notification turn. About $200 of cache
   reads in one day. Keep lead sessions short; hand over in a file like this one.

## 5. Proposed architecture direction (for the Fable session to decide)

- Code does bookkeeping: reading PDFs to text and pictures, citations, the ledger, rendering, pricing, checks.
- AI does judgement, with the whole job's evidence: classify each sheet (new work, demolition, part plan, riser,
  schedule, sequence), decide unit identity across sheets (one unit, many labels), decide scope per unit, and write
  each block in the Master Template format and GEM order. One whole-job "takeoff" pass before writing, so blocks are
  consistent (valves under units, pumps split, no double counts).
- An independent critic (QC) that compares the proposal with the Master Template and the evidence, and a coverage gate
  that turns every uncited fact into a line, exception, clarification or dismissal.
- The Playbook stays the estimator's rulebook; the 13 rulings of 2026-10-11 go into it as rules (estimator approval).

## 6. Acceptance for the final wave

1. 26-0544 rerun: counts AHU 5, EF 5, ERV 1, FCU 55, thermostats from new-work sheets; the header right; the format and
   the order of points as in the Master Template; red flags as ruled; off-hours and prevailing wage added and red;
   front end with the Master Template's existing-BMS lines and the non-AME BMS flag; one question per family.
2. The estimator reviews and signs off 26-0544. Then 26-0559 and 26-0562, one at a time.

## 7. Operating model the estimator asked for

The Fable session decides and reviews. Labor goes to HarkPro (parallel agents, its own capacity), and to Sonnet
executors and Haiku scouts/verifiers. Every agent prompt says: do not start subagents or review fan-outs. The lead
reads reports and diffs, not files. A background watcher (`git ls-remote origin 'refs/heads/hark/*'` every 60 s,
exits on change) wakes the lead when HarkPro pushes.

## 8. Master Template and GEM check of the 26-0544 proposal (scout, end of 2026-10-11)

Sources: `Brain/Master Template.docx`; `assets/gem/BMS_DDC_GEM_v4.txt` (GEM v4, approved 2026-10-03: the writing
instructions).
- Format: heading "Qty (#) <system>", no sub-headings, "OR" lines for alternatives, '*' notes after the scope lines,
  "**" lines are estimator hints, tech-hour line last. GEM: one '*' note per block (GEM ~548); a quantity note goes on
  the device line (GEM ~609). Our blocks carry 2-3 '*' notes.
- Existing-BMS front end (template ~lines 77-104): tie-in header, network control panel, 3-D graphics, training,
  warranty. Ours had none of panel, graphics, training, warranty.
- GEM v4 order of points (GEM ~408-432): 1 controller; 2 sensors; 3 switches; 4 leak detectors; 5 current switches;
  6 interposing relays; 7 damper actuators; 8 fan and pump signals; 9 primary equipment; 10 position feedback;
  11 other outputs; 12 power wiring; 13 fire alarm wires; 14 filter DP switches; 15 airflow stations; 16 valves;
  17 Install and Wire; 18 other Wire; 19 integration group; 20 miscellaneous. A Master Template entry sets the order
  when it has one (GEM ~396-402). Ours broke it in AHU, EF and pumps.
- Valves: always Furnish and Wire (GEM ~228); factory-unit valves are not CC lines (~291, 294).
- Pumps: Start/Stop, Status and VFD Control always (GEM ~348-349); fault and speed only when called. Chilled and hot
  water are separate blocks (template ~371, 611). Ours had no pump VFD Control.
- Factory controllers belong to the unit maker (GEM ~279-288). Shipped-loose devices: GEM ~296-303.
- Exclusions: only sequence items (GEM ~564); ours had 37 mostly generic lines, demolition excluded twice, and
  conflicts (smoke-detector wires scoped and excluded; airflow station scoped and excluded; factory mounting excluded
  but needed). No Miscellaneous section (GEM ~450-468).
- No rule in the sources for off-hours/prevailing wage, demolition plans or FUTURE items: those are the estimator's
  rulings of 2026-10-11 (memory `rulings-2026-10-11-first-run`); propose them as Playbook rules.
