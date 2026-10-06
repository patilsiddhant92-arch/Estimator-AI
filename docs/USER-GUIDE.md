# Estimator app: how to use it

The app reads a bid job the way an estimator does, writes the controls scope system by system, checks its own work,
and gives you a draft proposal, a price sheet, an Evidence Package and a review page. You stay in charge: the
draft is for you to check, correct and sign off.

## What you give it

The job's takeoff folder (the plan sets and specification sections you would work from). Marked-up copies carry
the earlier estimator's counts, so give it clean copies.

## How to run a job

In any Claude Code session in this folder, type:

```
/run-job "<job folder>" --out out/<job name>
```

The command runs the whole job. It reads the documents in stages, counts equipment on the plan sheets, writes each
system, has an independent reviewer check the draft, revises what the reviewer found wrong, and writes the files.
A run takes about 25 to 45 minutes of working time. Work is shared out to AI agents, and the models they use are in
`.claude/run-job.json`. You do not switch models by hand.

## What you get (in the out folder)

| File | What it is |
|---|---|
| Proposal (.docx) | The draft scope, in the house format |
| Price Sheet (.xlsx) | Tech hours and quantities per line |
| Evidence Package (.xlsx) | Every line with its verb, owners, quantity, the quote and sheet or section it rests on, and the reviewer's findings |
| Review.html | One page of open questions: each count with the images it was counted from, each assumption with its reason |
| Job.json | The whole job as data, for reading, for measuring and for `status`. The next run does not read it: it builds the job again from the answers it has kept |
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

A changed Playbook, new documents or another model make it a new question, which starts a new count.

## The rules it follows

All the rules live in one book, `playbook/rules.md`. Change a rule there, and the next run follows it.
The main ones:

- The job's own documents decide the scope. Every line cites this job. No standard lines are added.
- The Master Template sets only the shape of a block, never what is in it.
- Every line says who furnishes, installs and wires.
- The higher count prints, flagged, with every count named. An unknown count prints as "Qty (##)".
- On the plans, a unit's tag (VAV-101, EF-3) is one unit however many plan sheets show it, so a floor drawn on two
  plan sheets (a ductwork plan and its piping and controls plan) never doubles the units. A type's tag (EBB-A) is
  counted at every place on every sheet, never merged: if one floor is drawn twice that is the higher count, and
  the counts line names the two sheets that may show one plan. When the plans still show more than the schedule,
  the quantity note says the likely cause in plain words, for example
  "*Qty. (12) per plan placements (likely a typical unit at each place); 1 per schedule rows." Those words
  are in `playbook/wording.json` (`count_causes`). The tags and sheets behind a cause go to the writers'
  evidence, never into the client's note.
- One "*" clarification per block. Every assumption says what and why.

## Older app

The earlier app still runs with `/run-job ... --app estimator`. It stays until you decide to retire it.
