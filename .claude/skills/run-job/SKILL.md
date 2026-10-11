---
name: run-job
description: Run an estimate on a job folder in chat mode to completion, handing every AI request to a subagent on the configured model; usable from any session.
argument-hint: "<job folder> [--out FOLDER] [--cache FOLDER] [--app bms|estimator]"
allowed-tools: Bash, Read, Agent
---

# Run a job to completion

Run the estimator on the job folder given in the arguments, answering each AI request through a subagent,
until the proposal is written. Use `.venv/Scripts/python.exe` for every Python command, from the repo root.
Out folder: the `--out` given, else `out/estimate/<job folder name>`. Pass `--cache` through when given. The rebuilt
app (`python -m bms`) runs by default (`--app bms`); pass `--app estimator` through only when given, to run the old
app (`python -m estimator`).

This work is under NDA. Never paste the contents of a request file or an answer file into the conversation,
and never print job content. Say only counts, kinds, system names and file paths.

## Settings

Read `.claude/run-job.json`: `judge_model` (reading passes), `writer_model` (write requests), `qc_model`
(the QC request), `count_model` (the vision count's sheet requests) and `max_attempts`. The estimator can change them, so always read them fresh.

## Steps

1. Run `.venv/Scripts/python.exe tools/run_job.py status <job> --out <out> [--cache <cache>] [--app estimator]`. It
   runs the estimate and ends with a block listing the requests still waiting, the proposal path if any, the
   estimate's `exit` code (2 while requests wait, 0 when done) and the `stage` it waits at (read, takeoff, count,
   write, qc, revise). Go by the block, not the exit code.
2. If `proposal` is set, go to the finish.
   Stop rule: no waiting requests and no proposal: report the last summary and stop.
   A request listed with `"rejected": true` was answered but the estimator could not use the answer (its
   `reason` says why, when the run printed one); its answer file is already deleted and the attempt counted, so
   dispatch it again. Otherwise handle the waiting requests by kind:
   - `read_pass`: one at a time, in the order listed (each reading depends on the one before).
   - `takeoff_job`: alone, after the reading; it goes to `judge_model`.
   - `count_tags`: the plan count check, one request per plan sheet (its tiles listed under `images`, in order,
     every tag pattern on the sheet asked together); up to 4 at once, each in its own subagent,
     all dispatched in one message; they go to `count_model`.
   - `write_system`: up to 4 at once, each in its own subagent, all dispatched in one message. This kind covers
     both writing a system and, in the rebuilt app, revising one (its `step` is `revise` and its system name ends
     with "(revise)"); both go to `writer_model`.
   - `qc_job`: alone (one per part when the QC is split; the parts are independent).

   For each request, start one subagent whose Agent `model` parameter is `judge_model` for `read_pass`,
   `judge_model` for `takeoff_job`, `count_model` for `count_tags`, `writer_model` for `write_system` and `qc_model` for `qc_job`. Give it exactly this
   prompt, with `<path>` taken from the status block's `file`, `<answer_file>` from its `answer_file`, and `<scratch>`
   set to `<out folder>/.scratch/<request file name without .json>`:

   "You are the AI judge of the estimating tool. Read the request file <path>. Its `system_prompt` is your
   instructions; answer its `prompt` exactly in the JSON shape of its `schema`. Run every Python command from the
   repo root with `.venv/Scripts/python.exe`. Obey these rules.
   1. Open only <path>. Do not list the requests folder. Do not open any other request file.
   2. Build the answer as Python data in `obj`. Write it with
      `with open(r"<answer_file>", "w", encoding="utf-8") as f: json.dump(obj, f, ensure_ascii=False, indent=2)`.
      Do not type JSON by hand into a file. Do not use a heredoc or an editor tool to write <answer_file>.
   3. Put each scratch file, such as your script, in <scratch>. Make that folder yourself. Do not use a shared temp
      folder.
   4. After you write <answer_file>, run
      `.venv/Scripts/python.exe tools/run_job.py check --no-count "<answer_file>" "<path>"`.
      If the check fails, fix the answer and run the check again. Report only after the check prints `ok`.
   5. Do not start subagents or review skills. Do not run the estimator. Report in fewer than 100 words: the path of
      <answer_file>, the real output of the check, and any doubt about the evidence."

   Add to the prompt that the subagent must create the answer file's parent folder if it is missing, that it must
   open every picture the request lists under `images` (each by its path) before answering, and that when the
   request has a `previous_problem`, an earlier answer was refused for that reason and the new answer must fix it.
   For `count_tags`, add that it must open and examine every tile picture under `images` (never count from a
   whole-sheet picture) and list every tile number in each pattern's `tiles_examined`; an answer that leaves a
   tile out is refused.
3. When a subagent is done, run `.venv/Scripts/python.exe tools/run_job.py check <answer_file> <request file>`.
   If it fails, delete the answer file and dispatch that request again. Stop retrying a request once it has
   failed `max_attempts` times (the `attempts` count in the status block); report which request and why, and stop.
4. Run `status` again and go back to step 2. Stop when `proposal` is set, when a request has failed (or been
   rejected) `max_attempts` times, or when nothing is waiting and there is no proposal.

## Finish

Name the three output files in the out folder: the proposal (.docx), the price sheet (.xlsx) and the Evidence
Package (the rebuilt app also writes the review page, Review.html). Say how many requests were answered and whether any were re-dispatched. Nothing more.
