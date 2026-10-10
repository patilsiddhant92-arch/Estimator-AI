# T-000 report: introduction

## 1. Task
- Task: T-000. Branch: `hark/T-000`. Base commit: `c5d3fa6` (tip of `lead/hark-inbox`). Last commit: see `git log -1 hark/T-000`.

## 2. What I changed
- `HarkPro/outbox/T-000-report.md` (new): this report. No other file was changed.

## 3. Tests
- None added (questions only). For the capacity answers, I ran the full suite on `c5d3fa6`, unchanged, in my sandbox:
  `9 failed, 3754 passed, 10 skipped in 441.81s` (Python 3.13.5, Linux, `-n 2`). All 9 failures are environment-only:
  - 5 in `test_ai.py`, the chat tests;
  - `test_assets.py::test_running_on_the_project_python`, which pins 3.13.15 (I have 3.13.5);
  - `test_main.py` Windows open-file lock;
  - `test_review_final3.py` Windows resource code;
  - `test_revert_audit_review.py` class audit, flaky here before.

  The same set failed on my earlier runs of clean commits. So for me, "the suite passes" means "no failures outside this list". Please confirm, or tell me which interpreter pin to use.

## 4. Not done
- No code, as the task says. I did not start T-001 or T-002.

## 5. Answers

1. **Models.** Hark routes each task to different models; I don't have privileged access to which one runs at a given time.
2. **Agents.** I run as one lead agent. I can start sub-agents in parallel; I have used five at once on this repo, each in its own git worktree and branch in the same sandbox, and up to 6 browser sessions. All of them share one machine, so heavy test runs compete.
3. **Capacity.** About 3 to 5 medium tasks a day, when the estimator keeps me moving. The first limit is compute: 2 CPUs and 7 GB RAM, so a full suite run takes about 7.5 min, and two at once take longer. Next is that I only work when the estimator messages me (see 7).
4. **Turnaround.** For a medium task (about 300 lines of code and tests): about 30 to 90 min from "read the inbox" to the report pushed. That includes two or more full suite runs at about 8 min each.
5. **Code.** Yes: Debian 13 Linux, git, Python 3.12.15 and 3.13.5, uv, node v22. The repo pins `requires-python ==3.13.*`, so I can't install it on 3.12; I run on 3.13 with `PYTHONPATH=src`. I can run the JS tests with node.
6. **Documents.**
   - PDF: yes. Text layer with `pdftotext`/pypdf; I can render pages to images and look at them (for example, count symbols on a plan tile).
   - .docx and .xlsx: yes, read and write (python-docx, openpyxl).
   - LibreOffice: no, not at the moment (it was there earlier and is gone). So I can't recalc formulas or render xlsx/docx to PDF. Price-sheet totals need Excel on your side.
7. **Git.** Yes: fetch, branch, commit and push to `hark/*`, with no step by the estimator (GitHub App with access to this repo). I don't see new commits by myself. I look when the estimator messages me, or on a schedule if he asks me to set one (for example, check the inbox every 2 hours).
8. **Memory.** Yes, across sessions:
   - a persistent workspace (clones, worktrees, scripts, job outputs);
   - my own notes on the estimator and the project;
   - a project brief;
   - in git, the `HarkPro/` folder on `hark/harkpro` (bugs, progress, discussion, `learnings.md`, `sessions/`, `doctrine/rulings.md`).
9. **Strengths and limits.**
   - Best at:
     - auditing and finding root causes with repro scripts;
     - reading drawings, specs and schedules for scope and ownership;
     - building test-first fixes in parallel worktrees;
     - running a job end to end and checking the output against the documents.
   - Weaker at:
     - long sessions that must wait on the estimator's PC (Windows-only behaviour, his local files);
     - anything needing LibreOffice;
     - tasks that need sight of new commits the moment they land.
10. **Rules.** I accept all 7. Two notes:
    - Rule 5: on my machine the full suite has the 9 environment failures from section 3. I will report the result line and list any failure outside that set.
    - Rule 3: my earlier `hark/harkpro` work used only "Job 1/2a/2b/3/4" names. My local job folders and outputs stay out of git, as before.
11. **Conflicts with my notes.** Five, plus one gap:
    - **R20 vs the packaged-unit damper ruling.** R20 said a damper actuator is AME's Furnish and Install even when the schedule lists it with the unit. The new ruling keeps a damper inside a factory-controlled packaged unit with the factory when only the schedule mentions it. I read R20 as now limited to dampers shown on the plans, the control diagram or the sequence. Job 4's exhaust-fan dampers are also in the sequence, so that job's output still holds.
    - **R1 replaced.** My `84e7a16` coverage gate and the Job 2a/2b/4 outputs follow "the schedule count prints". They must change to "the highest count prints, with the others in a * note". Job 4 prints the FCU plan count 55, which is the highest, so it agrees, but the note format must be checked.
    - **"Required" lines.** `harkpro/qc/checklist.py` still passes the lines.json `required` flag to the QC critic. In T-001, the critic must ignore it or the flag must be removed, or it will ask for template lines with no evidence. `harkpro/coverage.py` doesn't use it.
    - **EF hours.** Job 4 put the EF points on the AHU controller with no extra hours. The new rule gives 4 h per fan (5 fans = 20 h). This also answers draft point 8.
    - **R19.** R19 still holds only when AME furnishes the controller. A factory-controlled unit keeps its devices (consistent with the new damper ruling).
    - **Gap:** conflicts C11-C16 in `HarkPro/doctrine/conflicts.md` resolve to "lines.json". They are now reversed (evidence only), and I haven't edited the file. Tell me if I should mark them superseded on `hark/harkpro`.
12. **Things you must not lose.** None of these is on `main` or `rebuild`:
    - **The fix patch.** `HarkPro/patches/fix-all-uncommitted.patch` on `hark/harkpro` (6022f8f) holds the READ/PLAN/DOC-1..4/CORE/RUN fixes, based on `7e27873`, which is NOT on GitHub (this is last week's "base not on GitHub" problem). The later round-2 fixes (front end planned/written/revised, add/deduct alternate read from the schedule title, automatic EXCEPTION lines) are in my sandbox worktree, uncommitted, and are not in that patch. If you want them, give me a task and I will push both as a branch on a GitHub base.
    - **The Evidence Package redesign.** Branch `hark/evidence-ui` (7e27873): Summary, device-only Scope lines, Findings/Counts/Citations tabs. Local only.
    - **The "run a job with no API key" procedure.** Answer each `tools/run_job.py` request with an AI judge, then `check`. My driver scripts are in the sandbox, not in git.
    - **Learnings and bugs.** `learnings.md` and `bugs.md` on `hark/harkpro`. `bugs.md` lists 14 Job 4 app bugs not yet fixed, including:
      - control schematic and EF schedule notes not read;
      - a seed count contradicted by a pass still prints;
      - the same source id carries different text;
      - plan double counts across duct and piping sheets;
      - "(E) RH COIL" read as a humidity sensor.

## Split of T-001 and T-002
They touch different stages, so two sub-agents in two worktrees, each on its own branch (`hark/T-001`, `hark/T-002`) from the same base commit:
- **T-001** owns the gate after writing.
- **T-002** owns the writer's input.

The only shared surface is the fact model the gate reads. Freeze its shape at the start, or do T-002 first if it changes facts. I review both and run the full suite on each before pushing. The two full-suite runs are the bottleneck (2 CPUs), not the coding.

## Questions
1. Section 3: is "no failures outside the 9 environment failures" an acceptable pass for rule 5 on my machine?
2. Should I mark conflicts C11-C16 and R1 as superseded in `HarkPro/doctrine/` on `hark/harkpro`?
3. Do you want the uncommitted round-2 fixes and `hark/evidence-ui` pushed as `hark/*` branches on a GitHub base, as reference for T-001/T-002?
