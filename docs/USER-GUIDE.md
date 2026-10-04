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
| Job.json | The whole job as data, for the next run and for measuring |

## Your part

1. Open Review.html. Accept, change or delete each item. Save the decisions file into the out folder.
2. Run the job again. It applies your decisions and rewrites only what changed.
3. Check the proposal and the Evidence Package, then sign off.

## The rules it follows

All the rules live in one book, `playbook/rules.md`. Change a rule there, and the next run follows it.
The main ones:

- The job's own documents decide the scope. Every line cites this job. No standard lines are added.
- The Master Template sets only the shape of a block, never what is in it.
- Every line says who furnishes, installs and wires.
- The higher count prints, flagged, with every count named. An unknown count prints as "Qty (##)".
- One "*" clarification per block. Every assumption says what and why.

## Older app

The earlier app still runs with `/run-job ... --app estimator`. It stays until you decide to retire it.
