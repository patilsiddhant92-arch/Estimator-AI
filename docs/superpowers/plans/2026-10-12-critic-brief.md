# Critic brief: the estimating method behind Estimator AI

Date: 2026-10-12. Written by the Fable lead of the final wave for the next session, at the estimator's request.

## 1. What the estimator asked for

The estimator (the user) does not want another review of the code. The estimator wants a critic of the method:
how an estimate for a BMS/DDC controls bid is done, from the takeoff folder to the signed proposal. The method is
the estimator's own. It lives in the Playbook, the Brain documents, the Master Template, the GEM, the rulings given
in chat over the last weeks, and the marked-up jobs in the archive. The app is the attempt to capture that method.

Three questions, in this order of weight:

1. **Is the method sound?** Where does the way the estimator reads drawings, sequences and specs, marks up the
   plans, counts, decides scope, writes and prices leave room for error, above all for a low count or a missed
   scope item? Where are the rules inconsistent, job-specific dressed as general, or missing?
2. **Is there a better way?** If a different workflow would reach a more accurate output, say so and describe it.
   The estimator said: "If Fable has a better way of getting to the output we are getting now by a much more
   accurate workflow, I am open to listen." Take that at face value. Do not soften it.
3. **Is the app ready to produce a bid?** Will a run of 26-0544 today give a proposal the estimator can sign off
   after small corrections? If not, name the reasons, in order of weight.

## 2. Who you are and the rules

You are an independent critic. You did not build the app and you did not write the rules. You owe nothing to the
decisions in the plans. Be direct. The estimator asked for criticism of their own work and will read it as such.
Praise is not useful. A confirmed weakness with a cause and a better way is.

- Change nothing: no code, no tests, no Playbook, no settings. Write one report file and nothing else.
- Do not run a job. A run costs many AI calls; the estimator decides when 26-0544 runs again. Cheap checks are
  fine: `doctor`, `playbook-lint`, `status` on an existing out folder, a subset of the tests.
- Do not commit or push. Leave the report uncommitted.
- Use `.venv\Scripts\python.exe` for all Python, from the repo root, with `PYTHONPATH=src`.
- Give the reading to scouts (Haiku or Sonnet), at most 3 at a time. Keep the judgment in the main session. Tell
  every agent: "Do not start subagents or multi-agent review skills." Do the reading of the proposals, the markups
  and the rulings yourself: that judgment is the job.
- Two folders are read-only: `D:\AME Estimation` (the real job archive, with the estimator's markups and final
  proposals) and `D:\Estimation Assistant` (the previous tool). Read them freely. Never write there.
- NDA: job names, tags and short quotes may appear in the report, because the repo is private. Never put job
  content in a public Artifact or an upload.
- Say "verified" when you saw it and "suspected" when you reason from a document. Never mix the two.

## 3. The goal, in the estimator's terms

For each job, a takeoff folder holds the clean plan sets and the specification sections. From that folder, with no
help from the estimator, the output must be: a Word proposal in the house format (Master Template), one block per
system, device lines in the GEM v4 order, each line true for this job and cited to this job's documents; a price
sheet with devices, counts and tech hours (tech hours never print in the proposal); an Evidence Package that shows
where every line and count came from; a review page with the questions the estimator must answer.

The measure of success is how little the estimator must correct, and above all that no count is low. The
estimator's words: "A count that is too low is the worst error." Second, trust: every place where the app was unsure
or the sources disagreed must be red. Third, cost and time: one job per day in chat mode, later in API mode.

## 4. What to read

Scouts take the long documents and report with `file:line` evidence. You read the proposals, the markups, the
rulings and the output yourself.

### The method, as the estimator wrote it

1. `playbook/rules.md`, `playbook/shapes.json`, `playbook/wording.json`. The estimator's rule book. It wins over
   code and tests.
2. `Brain/`: the doctrine documents, the quantity rules, the GEM v3.2 and the Master Template
   (`Brain/Master Template.docx`; the working copy has an uncommitted edit by the estimator). `Brain/AGENTS.md` is
   not this project's rules; read it only as history.
3. `assets/gem/BMS_DDC_GEM_v4.txt`: the approved writing method, one system per sequence section, points in order.
4. `docs/USER-GUIDE.md`.

### The method, as the estimator said it in chat

5. The memory files named in `MEMORY.md`, in this order: `counting-principle-undercount-worst`,
   `master-template-guidelines`, `gem-is-the-method`, `job-inputs-only`, `takeoff-folder-is-the-input`,
   `proposal-feedback-2026-10-03`, `proposal-feedback-2026-10-04`, `gate-rerun-2026-10-03-open-questions`,
   `bug-register-rulings-2026-10-07`, `rulings-2026-10-10`, `rulings-2026-10-11-first-run`,
   `rulings-2026-10-11-afternoon` (rulings 14 to 26), `front-end-bms-names`.
6. `docs/superpowers/plans/2026-10-11-playbook-rules-proposal.md` (the text the rulings became),
   `bugs.md` section 3 (rulings D1 to D9), `Gemini bugs_10.08.2026.md`.
7. `docs/superpowers/plans/2026-10-11-architecture-review.md` and `2026-10-11-takeoff-pass-plan.md`: how the lead
   turned the counting method into a design (the takeoff register, admissible sources, schedule as the floor,
   higher count prints with every count named, set-asides shown).

### The method, as the estimator practises it

8. `D:\AME Estimation`: pick three finished jobs of different kinds (one with air handlers and fan coils like
   26-0544, one with a plant, one with VAV or packaged rooftops). For each, read the takeoff folder, the marked-up
   plans, the final proposal and the price workup. This is the ground truth of the method. Note what the markups
   capture, in what order the estimator seems to have worked, and what the final proposal contains that no rule in
   the Playbook states.
9. The held-out jobs the lead never used for tuning: 26-0521, 26-0422, 26-0256 (see memory `test-jobs-nda`).
   `tools/measure.py` can compare an app output against a finished proposal. Use it only on an output that
   already exists; do not run a job to make one.

### The output and the app

10. `docs/superpowers/plans/2026-10-11-evening-state.md`, "Wave complete" section first, then the rest. It lists
    what was built, what was fixed after the last run, and what is open.
11. `docs/superpowers/plans/2026-10-11-final-wave-handover.md`, section 6 (the acceptance list).
12. `out/26-0544-r2/`: the latest run (proposal, price sheet, Evidence Package, `Review.html`, `Job.json`,
    `Takeoff.json`). It predates the last fixes; the state file lists them. Judge the proposal as the estimator's
    client would read it. Then trace three counts and two scope lines back to the job's takeoff folder
    (`Jobs/26-0544, Monmouth County Courthouse - Rplc of Air Handling & Fan Coil Units, NJ/2. Takeoffs/1. Base
    Takeoff`) yourself. Do not trust the Evidence Package for this; test it.
13. The code, only as far as the questions need it: `src/bms/run.py` (`estimate()`), `takeoff.py`, `plan.py`,
    `plan_read.py`, `counts.py`, `ai.py`, `validate.py`, `labor.py`, `render.py`, `review.py`, `evidence.py`,
    `prompts/`. `CLAUDE.md` has the map.
14. `.claude/skills/run-job/SKILL.md` and `tools/run_job.py`: how a run is driven in chat mode.

## 5. Questions you must answer

Answer each with a verdict (sound, partly, not), the evidence, and, where not sound, the cause and the better way.

### Reading the job

- What does the estimator read first, and does the order protect against missing a system? Schedules, plans,
  sequences, controls diagrams, the spec sections (controls, general conditions for off-hours and prevailing wage,
  demolition). Which document wins when they disagree, and is that stated anywhere?
- Clean sets are the input; the markups are the estimator's own working notes. What do the markups carry that the
  clean set plus the rules do not? Is the markup step a real part of the method, or a workaround for not having a
  register? Could the app's takeoff register replace it, or should the estimator's register come first and the app
  write from it?
- Sequences of operation: the method takes one system per sequence section and one device per sequence point. Where
  does that fail (shared sequences, typical units, sequences that name devices the plans do not show, packaged
  units with factory controls)?

### Counting

- The counting rules: schedule as the floor, plan count, sequence count, typical units, part-plan overlap counted
  once, demolition sheets set aside, future items set aside, higher count prints with every count named. Take each
  rule and ask: when does it give a low count, and when a high one the estimator must then cut by hand?
- The thermostat exception (ruling 21: the plan count prints with a verify flag, not the one-per-unit sequence
  count) contradicts "higher prints". Is it right as a rule, or right for 26-0544? What would a client-safe rule be?
- Where does the method count by eye on a plan, and is that the right job for a person, for a vision model, or for
  neither?

### Scope

- Who furnishes what: freezestats, filter switches, valves, dampers and actuators, VFDs, flow switches, sensors
  shipped with packaged units, the front end. The rulings fix some cases (23 on freezestats and filter switches;
  the front-end rules). Are these principles, or a growing list of exceptions? Could one rule cover them?
- Global points, Demolition Scope, Labor Conditions, the generic Clarifications and Exclusions sections with red
  sub-bullets. Does each belong in the proposal, and does the client read it the way the estimator means it?
- "The job's documents decide the scope; the Master Template sets the format and the house lines; the GEM sets the
  order." Is that boundary clear in the rules, or does it depend on who last answered a question?

### Writing and pricing

- Compare 26-0544-r2 and an archive proposal line by line for one block. Where is the method's output verbose,
  generic, silent, or wrong in tone for the client?
- Tech hours and the price book: how does the estimator get from a device list to hours and a price? What in that
  path is rule, what is judgment, and what is habit? 54 rows were PRICE PENDING on r2: is that the app or the
  method?
- Red flags: are they the right ones? What should be red and is not?

### The rulings as a body

- 26 rulings in two days, plus D1 to D9 and the review rulings of 2026-10-10. Sort them: general principle, house
  style, this-job-only, or a reaction to a defect in the app. How many of the "rules" would the estimator have
  written down before seeing the app's output? Which ones conflict (15 and 24; 3 and 21)?
- Was teaching the app through rulings on one live job a good way to transfer the method? What did it miss that a
  corpus of finished jobs with a measurement would have caught?

### A better way

- Describe the workflow you would use to reach the same output with fewer low counts and fewer corrections. Say
  what the estimator does, what the app does, and where the estimator checks. Consider at least these: the
  estimator approves the takeoff register before anything is written; the app is measured against the archive
  before every live run; counting by vision on every plan sheet; a second independent pass that reads only the
  finished proposal against the documents. Say what each costs in time and AI calls and what it buys.
- If the current method is already the right one, say so and say why the alternatives lose.

### Readiness

- Will a run of 26-0544 today give a proposal the estimator can sign off after small corrections? Verdict with
  the reasons, in order of weight. Separate the reasons that are the method's from the ones that are the app's.
- 26-0559 and 26-0562 are next. From their takeoff folders (names and sheet lists only; do not run them), what do
  they have that 26-0544 did not, and will the method and the app handle it?

## 6. Known open items

Verify these; do not take them as true.

- A second, independent pass over the finished proposal against the documents was proposed and deferred.
- API mode waits on the estimator's admin. Chat mode is the only tested path.
- The price sheet shows PRICE PENDING on 54 rows of r2.
- Thermostats: the plan-count rule is in the Playbook and the render, but no fresh run has shown it.
- `playbook/shapes.json` line 15 and the sample Playbook `wording.json` still mention `{qty}` after ruling 24.
- The takeoff fixture characterisation test pins the current count after a change from 16 to 5.
- Two old worktrees under `D:/EA-*` are kept, dirty.

## 7. The report

Write `docs/superpowers/plans/2026-10-12-critic-report.md`. The estimator reads it, not an engineer. Keep the body
under 3,000 words; long evidence goes in an appendix. Sections, in this order:

1. **The method as it stands.** One page: how an estimate is done today, from folder to proposal, step by step,
   with who or what does each step. Reconstructed from the rules, the rulings and the archive, not from the plans.
2. **Where the method can fail.** The weaknesses, ranked by their chance of producing a low count or a missed
   scope item. For each: the weakness, the evidence (a rule, a ruling, a markup, an output line), why it fails,
   and the better rule or step.
3. **The rulings sorted.** Principle, house style, this job only, reaction to the app. The conflicts and how to
   resolve them. Which rules to drop.
4. **A better workflow, if there is one.** The path from folder to signed proposal you recommend. What the
   estimator does, what the app does, where the estimator checks, what it costs, what it buys. If the current path
   is right, say so.
5. **Is the app ready to produce a bid.** Verdict in one sentence, then the reasons in order, each marked
   "method" or "app", verified or suspected.
6. **Before the next run of 26-0544.** Only what blocks a sign-off.
7. **Before 26-0559 and 26-0562.**
8. **Do not do.** Work that looks useful and is not.
9. **Appendix.** The archive comparison, the count traces, the ruling sort, the request count per run.

In chat, after the file is written, give the estimator ten lines: the verdict on the method in one sentence, the
three weaknesses that matter most, whether there is a better workflow, and whether the app is ready. Nothing else.

## 8. How to begin

Say in one line what you are about to do. Start three scouts on the written method (items 1 to 7), one on the
state file and handover (10 and 11), and one on the code map (13 and 14), three at a time. Read the archive jobs
(item 8) and the r2 output (item 12) yourself; do the count traces with an executor that reports `file:line` and
sheet references for every hop, and check its report against the files before you use it. Write the report last,
in one pass, after every verdict has its evidence.
