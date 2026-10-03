---
name: run-job
description: Run an estimate on a job folder in chat mode to completion, handing every AI request to a subagent on the configured model; usable from any session.
argument-hint: "<job folder> [--out FOLDER] [--cache FOLDER]"
allowed-tools: Bash, Read, Agent
---

# Run a job to completion

Run the estimator on the job folder given in the arguments, answering each AI request through a subagent,
until the proposal is written. Use `.venv/Scripts/python.exe` for every Python command, from the repo root.
Out folder: the `--out` given, else `out/estimate/<job folder name>`. Pass `--cache` through when given.

This work is under NDA. Never paste the contents of a request file or an answer file into the conversation,
and never print job content. Say only counts, kinds, system names and file paths.

## Settings

Read `.claude/run-job.json`: `judge_model` (reading passes), `writer_model` (write requests), `qc_model`
(the QC request) and `max_attempts`. The estimator can change them, so always read them fresh.

## Steps

1. Run `.venv/Scripts/python.exe tools/run_job.py status <job> --out <out> [--cache <cache>]`. It runs the
   estimate and ends with a block listing the requests still waiting and the proposal path, if any.
   A non-zero exit from `status` while requests are waiting is expected; go by the block, not the exit code.
2. If `proposal` is set, go to the finish. Otherwise handle the waiting requests by kind:
   - `read_pass`: one at a time, in the order listed (each reading depends on the one before).
   - `write_system`: up to 4 at once, each in its own subagent, all dispatched in one message.
   - `qc_job`: alone.

   For each request, start one subagent whose Agent `model` parameter is `judge_model` for `read_pass`,
   `writer_model` for `write_system` and `qc_model` for `qc_job`. Give it exactly this prompt, with `<path>`
   taken from the status block's `file` (and its `answer_file` from the block's `answer_file`):

   "You are the AI judge of the estimating tool. Read the request file <path>. Its `system_prompt` is your
   instructions; answer its `prompt` exactly in the JSON shape of its `schema`; write the JSON to its
   `answer_file` (relative to the repo root), UTF-8; do not spawn subagents; do not run the estimator; reply
   with one line."

   Add to the prompt that the subagent must create the answer file's parent folder if it is missing.
3. When a subagent is done, run `.venv/Scripts/python.exe tools/run_job.py check <answer_file> <request file>`.
   If it fails, delete the answer file and dispatch that request again. Stop retrying a request once it has
   failed `max_attempts` times (the `attempts` count in the status block); report which request and why, and stop.
4. Run `status` again and go back to step 2. Stop when `proposal` is set, or when a request has failed
   `max_attempts` times.

## Finish

Name the three output files in the out folder: the proposal (.docx), the price sheet (.xlsx) and the Evidence
Package. Say how many requests were answered and whether any were re-dispatched. Nothing more.
