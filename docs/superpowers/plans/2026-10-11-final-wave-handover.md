# Handover 2026-10-11: final development wave (for a new Fable session)

Written by the Opus lead session at the end of 2026-10-11. Read this first, then CLAUDE.md, memory
(`rulings-2026-10-11-first-run`, `front-end-bms-names`, `private-repo-job-data-ok`, `rulings-2026-10-10`), and the
Master Template and GEM in `Brain/`.

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
