# Estimator app: how to use it

The app reads a bid job the way an estimator does, writes the controls scope system by system, checks its own work,
and gives you a draft proposal, a price sheet, an Evidence Package and a review page. You stay in charge: the
draft is for you to check, correct and sign off.

## What you give it

The job's takeoff folder (the plan sets and specification sections you would work from). Marked-up copies carry
the earlier estimator's counts, so give it clean copies.

How it reads a set with copies, reissues and addenda. The rule behind all of it: counting too few is the worst
mistake, so the app leaves a page out only when it can prove the page adds nothing. Otherwise it counts both and
tells you, with both numbers.

- A marked-up copy. A document that repeats most of another's sheet numbers (at least 3 sheets, 80% of its own)
  is read once, as a copy, only when it shows nothing the other lacks: no unit the other does not show, at least 3
  of the other's units and 60% of them, the same plan titles, and 90% of the other's words. If any of that fails,
  it is read as another set of drawings (for example a second building with the same sheet numbers), counted, and
  the Flags tab says why ("but not their units") so you can check.
- Two versions of one sheet. The later date in the title block wins; with no dates, an addendum wins. When nothing
  says which one wins, both are counted, and the flag says "summed, for now". Tell the app which one governs.
- An addendum or reissue replaces only the sheet it is a new version of: the same sheet number AND the same plan
  title (the trade words aside). Building B's own M-101 is never dropped because building A's M-101 was reissued.
  If two sheets have the same number and the same title, so the app cannot tell which one the addendum replaces,
  it keeps both and says "addendum M-101 may replace one of two M-101 sheets (...): both counted; check". If the
  addendum's title matches no sheet of its number, nothing is replaced and the flag says so.
- An addendum page that replaces part of a sheet. If the base set has M-101 on two pages and the addendum reissues
  only one, the addendum page replaces the base page it is most like. The other page is kept and counted, and the
  flag says "addendum reissues M-101 (1 page); base has 2 pages (...): unmatched page kept (p.2), counted; check".
  If the addendum page is just as like both, neither is replaced.
- One page printed again. A sheet number printed on several pages of one document with exactly the same text is
  one plan for several floors: counted once and multiplied by its pages. Pages of one number with different text
  are each a sheet, each counted. This is decided document by document: a number printed twice in Mech.pdf never
  changes how Second Building.pdf's sheet of that number is read.

## How to run a job

In any Claude Code session in this folder, type:

```
/run-job "<job folder>" --out out/<job name>
```

The command runs the whole job. It reads the documents in stages, counts equipment on the plan sheets, writes each
system, has an independent reviewer check the draft, revises what the reviewer found wrong, and writes the files.
A run takes about 25 to 45 minutes of working time. Work is shared out to AI agents, and the models they use are in
`.claude/run-job.json`. You do not switch models by hand.

## What changed in the final wave

Start a run from the main project folder, on the branch `rebuild`.

The run waits at a takeoff stage. That stage is one AI request. The request classifies every sheet and lists every unit. In chat mode, a subagent of the lead's session answers it, the same way it answers the other requests. You review the result on the review page.

The Demolition Scope is the last scope block of the base bid. The Labor Conditions notes follow it. The add alternates and deduct alternates print after the base bid. Each of these prints only when the job has it.

Red text means one of these:

- The line is marked FUTURE.
- The documents name a BMS that is not an AME BMS. AME works only with Honeywell WEBS, Johnson FX (Facility Explorer), or Niagara Tridium.
- The documents call for off-hours work or for prevailing wage.
- The line is one you must check. A notice mark, a demolition line, and the line "No front end information found" are red for this reason.

The review page has one card per family. A count question is asked once for each family, on that family's card. The page also has a card for the front end and the whole job when those have questions.

The 19 rulings of 2026-10-11 are recorded as rules in `playbook/rules.md`. That file does not use the word "ruling".

When the proposal, the price sheet, and the Evidence Package are written, the run is done.

## What you get (in the out folder)

| File | What it is |
|---|---|
| Proposal (.docx) | The draft scope, in the house format |
| Price Sheet (.xlsx) | Tech hours and quantities per line |
| Evidence Package (.xlsx) | Every line with its verb, owners, quantity, the quote and sheet or section it rests on, and the reviewer's findings |
| Review.html | One page of open questions: each count with the images it was counted from, each assumption with its reason |
| Job.json | The whole job as data, for reading, for measuring and for `status`. The next run does not read it: it builds the job again from the answers it has kept. Its `source_sheets` list is every sheet number the facts were read from: a line may name one of them after a sheet word ("per sheet S201"); written alone, one that looks like a source id the app issued (S201) is refused |
| Ledger.json | The facts the app read from the documents, each with where it was found |
| count-proofs (folder) | The sheet pictures the counts were made from; the review page shows them |
| decisions history.json | Every set of decisions you have saved, kept by the app (see "Your part") |
| run state.json | How the last run ended (the stage it reached, its messages, and how many saved decisions the history held); `status` reads it |

## Your part

1. Open Review.html. Accept, change or delete each item. Save the decisions file (`decisions.json`) into the out
   folder.
2. Run the job again. It applies your decisions:
   - An accept, change or delete of a line is applied to the line as written. The writer is not asked again.
   - A changed count of a group of equipment makes the writer write that one system again, keeping the lines
     already written.
3. Check the proposal and the Evidence Package, then sign off.

Each save of the page holds only the answers on that page. The app keeps every save in `decisions history.json`,
so a later save does not undo an earlier one. A new answer on the same line replaces the old one. To start your
decisions over, delete both `decisions.json` and `decisions history.json`. If either file is damaged, the run stops
and says so in plain words.

A `decisions.json` that an older page saved can hold a family change with words and no count, such as "4 pipe FCU".
That file now stops the run, and the run says which change it is. Open Review.html, type a whole number (5 or
5 units) or ## on that card, and save the decisions again.

### Cards about your decisions on the review page

- **Decision not honored**: a later write undid your decision. The page shows the line as it is now. Decide on it
  again.
- **Decision could not be applied**: the line you decided on is not in this run's job (it was removed or worded
  differently), or the number of copies of a repeated line changed since you deleted one. Find the line on the page
  and decide again, or check how many copies the system needs.
- **Check this system**: you deleted a line earlier, and the system has since been written again. The line may be
  back in other words. Check the system, and delete the line again if it is back.

## Checking how far a run got

```
python -m bms status "<out folder>"
```

This only reads the files the run already wrote (mainly `run state.json`). It never runs the job, never asks the AI
anything and writes nothing, so it is safe to use while a run is going. It ends with:

- 0: the run is done.
- 2: questions are waiting for answers.
- 1: the run stopped, has not finished, or there is no run in that folder. A proposal that could not be printed
  stops the run at the stage "render", with the reason in words.

This is not the same as `tools/run_job.py status`, which runs the job (it is what `/run-job` uses).

## When an AI answer is refused

The app checks every AI answer against the rules. An answer that breaks one (for example, one that prints a source
id in the proposal text) is refused and the question is asked again, with the reason. After 3 refusals of the same
question (the number is `max_attempts` in `.claude/run-job.json`) the run stops and names the question.

- In chat mode (the usual way), the next run asks the question again by itself.
- In API mode, delete the counter file the message names, then run again.

A changed Playbook or new documents make it a new question, which starts a new count. In chat mode the question
is always put to the same chat model, so a different model never makes a new question there; the same question is
asked again, with the reason it was refused, until the 3 attempts are used. (In API mode a different model does make
a new question.)

## The rules it follows

All the rules live in one book, `playbook/rules.md`. Change a rule there, and the next run follows it.
The main ones:

- The job's own documents decide the scope. Every line cites this job. No standard lines are added.
- The Master Template sets only the shape of a block, never what is in it.
- Every line says who furnishes, installs and wires.
- The higher count prints, flagged, with every count named. An unknown count prints as "Qty (##)".
- On the plans, sheets that show the same floor and area are not added together (ruling L1). A ductwork plan, a
  piping plan and a controls plan of one floor draw the same units, each for its own trade. The app counts them as
  one plan.
  Two plan sheets are one plan when all of these are true:
  - They are in one document.
  - They have two different sheet numbers. Two pages of one number are never one plan.
  - One of the two tests below is true.

  Test 1, the same floor and area for other trades. The titles name the same one floor, the same parts of it
  (TOWER A, EAST WING) and the same other words. The trades they name are not the same: "LEVEL 2 HVAC DUCTWORK PLAN"
  and "LEVEL 2 HVAC PIPING PLAN". "1ST FLOOR", "FIRST FLOOR" and "LEVEL 1" are one floor. Two words for one trade are
  one trade (DUCT and DUCTWORK, BAS and CONTROLS). This test needs no tag evidence. Two sheets of one trade with one
  title could be the two halves of a floor, so they never group by this test. A floor that has two such sheets
  groups none of its sheets by this test. A plan named ENLARGED or PARTIAL never groups by this test. A plan that
  names several floors never groups by this test.

  Test 2, the same title and the same units. The titles say the same words in the same order, with a floor among
  them (the trade words aside). The sheets repeat at least three of each other's units, and 60% of the smaller
  sheet's. "BUILDING 1 LEVEL 2" and "BUILDING 2 LEVEL 1" are two places.

  In a group, each tag counts the highest count of one sheet. A unit's tag (VAV-101) counts once. A type's tag
  (EBB-A) counts the most labels of one sheet. The floors and areas then add up.
  When this count is lower than the sheets add up to, the counts line gives both numbers. For example:
  "M-101 and M-201 counted as one plan, 4 (8 if they are two places): same floor and area; check".
  Every other sheet adds up, because a count that is too low is the worst error. So EBB-1 on ten floors' plans is
  10. The counts line names it, in case it is one unit shown again. The counts line also names sheets that may show
  one plan. A typical plan counts once per floor it stands for, and each floor counts once.
  A count stated beside a tag ("CUH-A (TYP. OF 4)") on sheets of one floor and area counts once in the same way.
  When this makes the count lower than the sheets add up to, the planner asks you to confirm it.
  The Evidence Package's inventory counts with the same rule.
  When the plans still show more than the schedule, the quantity note gives the likely cause in plain words. For
  example: "*Qty. (12) per plan placements (likely a typical unit at each place); 1 per schedule rows." Those words
  are in `playbook/wording.json` (`count_causes`). The tags and sheets behind a cause go to the writers' evidence.
  They never go into the client's note.
- How a label is read. A tag counts on a plan when it stands alone ("VAV-3", "(VAV-3)") or starts a short line,
  whatever words follow ("VAV-3 450 CFM", "EF-2 ON ROOF"); other tags on that line count too ("FCU-4 / FCU-5",
  "VAV-1 THRU VAV-5"). A tag after a word like TO, FROM, SEE, PER or SERVED BY is a note, not a label, and so is any
  line of more than 12 words. A count written after a tag is that many places: "CUH-A (TYP. OF 4)", "CUH-A x4",
  "CUH-A (4)" and "CUH-A 4 PLACES" are four. A count over 50, or one the app cannot read, is counted as one place,
  and the counts line names the tag and the words so you can check.
- A unit is never lost. A unit's tag (VAV-101) the plan names anywhere, even only in a note, counts once on that
  plan when it is labelled nowhere. A type's tag (EBB-A) counts only where it is labelled.
- One "*" clarification per block. Every assumption says what and why.

## Older app

The earlier app still runs with `/run-job ... --app estimator`. It stays until you decide to retire it.
