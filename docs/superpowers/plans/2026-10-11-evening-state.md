# State of the final wave, 2026-10-11 evening (Fable lead)

Read this before the handover of the morning (`2026-10-11-final-wave-handover.md`). Update it at every merge.

## Target

The estimator wants the app ready over the weekend and a rerun of 26-0544 on Monday 2026-10-12. Acceptance is
section 6 of the morning handover. The estimator does not follow git: the lead merges and pushes everything but
`main` without asking, and reports outcomes in plain words.

## Branches (GitHub `origin`, private)

- `lead/wave2`: the integration branch. Carries T-005c (+2 lead fixes), T-001b, the run-job fixes (answer files by
  json.dump, one request per subagent, unique scratch folders, `check --no-count`, worktree PYTHONPATH), the
  approved CLAUDE.md. The integration run of this evening adds T-005b, T-005e, the Playbook rulings, T-005a and the
  F3 header fix, then merges into `rebuild`.
- `takeoff/s1`: Stage 1 of the takeoff pass, tasks 1.1 (model fields) and 1.2 (invented fixture) done. Base for
  Grok's G1 and G2.
- `lead/t005a-fixes`, `lead/t005b-fixes`, `lead/t005e-fixes`, `lead/playbook-1011`: review-of-record fix branches,
  merged by the integration run.
- `lead/hark-inbox`: HarkPro's task channel (`HarkPro/inbox`, `HarkPro/STATUS.md`).
- `hark/T-005d` (sent back with 4 must-fixes and 6 tests), `hark/T-007` (waits for "T-007 base ready" in STATUS).
- `grok/T-G1` (Demolition Scope block), `grok/T-G2` (takeoff Stage 1 tasks 1.3 to 1.7, reassigned from HarkPro).
- `main`: release branch, old. HarkPro pushed 8 commits under `HarkPro/` to it on 2026-10-09; leave them.

Worktrees in use: `D:/EA-wave2`, `D:/EA-takeoff`, `D:/EA-hark-inbox`, `D:/EA-playbook`, `D:/EA-rebuild`,
`D:/EA-rv-*` (reviews), `D:/EA-grok-g1`, `D:/EA-grok-g2`. The main folder `D:/Estimator AI` is on `main`: run
nothing from it except the CLI with `PYTHONPATH=src` from a worktree. Every worktree command needs
`PYTHONPATH=src` (shared venv, editable install points at the main folder).

## Decisions of the day (all recorded in memory too)

- Architecture: Option A, the whole-job takeoff pass (plan `2026-10-11-takeoff-pass-plan.md`, 15 tasks).
- Rulings 14 to 19 (afternoon): '*' notes one short line per item; "Qty (#) <device>" (renderer catch-up is T-008);
  tech hours in the price sheet only; Demolition Scope block last in the proposal; pumps with the plant unless remote;
  front end per the Master Template. Rulings 1 to 19 are in `playbook/` on `lead/playbook-1011`.
- Lead rulings: a numbered tag is one unit across areas, with a '*' note that shows both numbers; a demolition unit
  with named work prints in the Demolition Scope, not in the new-work count; the schedule floor is rows plus a
  numeric quantity column; miscellaneous lines print before integration (Playbook); pump VFD Control only with a VFD.
- Deferred: T-008 device-line quantity prefix (wording.json, 586 shape forms, price-sheet parser); the
  independent template-and-evidence critic; Option B.

## Queue

HarkPro: T-005d fixes, then T-007 when STATUS says "T-007 base ready" (after T-005a fixes, G2 and G1 merge).
Grok: G1, then G2. Lead: review of record for each push (watcher on `hark/*` and `grok/*`, 5-minute poll), merge,
one full suite per batch, push `lead/wave2` and `rebuild`, mark "T-007 base ready", then post T-008.
Monday: `/run-job` on 26-0544 from a worktree on `rebuild` with `PYTHONPATH=src`, chat mode (API on hold).

## Agent rules learned today

One pytest at a time per machine, `-n 4` in agents, the full suite once per batch at `-n 10`. Tail test output.
Resume an agent only when its context is the point; otherwise spawn a small one. Agents refuse CLAUDE.md edits
and pushes on an agent's word: the lead does those two things itself.

## Update, Sunday 2026-10-11 evening (India time)


Merged into `lead/wave2` and `rebuild` today, each batch with one green full suite:
- Batch 1 (rebuild 86c9f50): T-005c (+ lead fixes), T-001b, T-005b (+ fixes), T-005e (+ fixes and HarkPro's group-line tail), the Playbook rulings 1 to 19 (`lead/playbook-1011`), T-005a (+ fixes). 5,089 passed.
- Batch 2 (rebuild 6153484): T-006 takeoff Stage 1 (+ `with_plant`, `COUNTED_STATUSES = ("new",)`, floor check), T-005d writer fixes (+ ownership flag, job-wide scope, Global Points owner). 5,227 passed. HarkPro STATUS says "T-007 base ready (6931eae)".
- Batch 3 (in progress): grok/T-G1 Demolition Scope by the G1 review recipe, named work on its own line, heading unnumbered, T-005e render tests isolated with `demolition=()`.

Open: HarkPro T-007 (Stage 2 wiring), Grok G-002 (device-line quantity prefix; branch exists, not delivered).
Decision: no interim rerun. One run of 26-0544 on Monday 2026-10-12 after T-007 and G-002 merge, from `D:/EA-rebuild`
(the main folder stays on `main`: the permission filter refused the worktree removal needed to move it; try again
when no agent uses `D:/EA-rebuild`, or run from there). Input folder: the job's `2. Takeoffs/1. Base Takeoff`.
Permission rules: the estimator was given the `settings.local.json` allow list for push, merge, worktree, checkout.
API mode: on hold until the estimator's admin answers.

- Monday 2026-10-12 early morning: G-002 (quantity prefix) and T-007 (Stage 2 wiring, with lead fixes M1-M3, S1) merged; rebuild a6f7afc, full suite 5,321 passed. G-003 (price-sheet polish, user guide) in review. The 26-0544 run started from the main folder at about 04:00 into out/26-0544-r2.

## Monday 2026-10-12 morning: build complete, first rerun done

Rebuild head after the merge of `lead/wave2`: 69422b0. `lead/wave2` and `rebuild` now hold the same work.
Full suite on `lead/wave2` before the merge: 5,341 passed, 4 xfailed.

Merged since the last update:
- G-002 (Grok): the device-line quantity prefix.
- T-007 (HarkPro): takeoff pass Stage 2 wiring, with the lead fixes M1 to M3 and S1.
- G-003 (Grok): price-sheet polish and the user guide.
- T-007b (HarkPro): the Stage 2 follow-ups, with the lead's dedupe fix.
- `lead/revise-noscope` (lead): the live-run intake fix. A partial revise that empties a block keeps the answer's `no_scope_reason`.

26-0544 rerun completed at about 05:50 India time into out/26-0544-r2 (29 requests answered: 5 reading passes, 1 takeoff, 7 counts, 9 writes, 1 QC, 6 revises; 3 re-dispatched; one app defect found and fixed mid-run: a partial revise that empties a block lost its no_scope_reason).

Next: the estimator reviews out/26-0544-r2; then 26-0559.

- Monday 2026-10-12 09:40: T-008 (+lead fixes) and G-004 (+Grok self-review fixes) on rebuild e28ff96, full suite 5,416. Estimator rulings 21-26 recorded (thermostat plan count + verify flag; one demolition exclusion; freezestat/filter switch ownership; "(Qty. N Total)" at the end of device lines with the source breakdown in the header; contradictions in red; generic sections keep their points and get red sub-bullets). Open: HarkPro T-009 task 1 (thermostat rule, option A), T-010 (ownership rules, contradictions red); Grok G-005 (quantity form, sub-bullets). Self-review checklist is mandatory in both channels. No job run until the estimator asks.
