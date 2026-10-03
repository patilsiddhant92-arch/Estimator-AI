# Proposal QC, the house shape, and damper placement — Design

**Date:** 2026-10-03
**Status:** Agreed in conversation; waiting for sign-off on this written spec
**Builds on:** `2026-09-29-staged-reading-ledger-design.md` (the ledger and the seven passes)
**Prompted by:** the estimator's reading of the first ledger-flow proposal (26-0193) on 2026-10-03

---

## In plain words

The first proposal written from the ledger was faithful to the documents but did not look like an
AME proposal. Three things were wrong, and each has a cause:

1. **Blocks read like the sequence's task list, not AME's blocks.** The VRF block had fourteen
   "Wire …" lines copied from the sequence. Cause: the writer treats the sequence as the shape and
   the Master Template as a checklist. The estimator's rule is the other way round: the Master
   Template is how the system looks in the ideal case, the sequence fills it and may add an explicit
   item, and AME's responsibility on each line is the ownership verb (Furnish, Install and Wire,
   Wire, Tie in). On a packaged unit, what is inside the unit is never a line; the shipped-loose
   devices are "Install and Wire … (Furnished by Unit Mfr.)"; "monitor at the BMS" is covered by the
   three integration lines.
2. **Each system was written blind to the others.** Damper actuators landed in one block at the end,
   duct heaters got full scope though they serve packaged units. Cause: the 26 write requests were
   independent; none saw the whole job.
3. **Nothing checked the finished proposal.** The tool's checks are mechanical (fact ids, counts,
   quotes, house verbs); the GEM's Self-QC is filled in by the writer itself. Cause: there is no
   independent QC pass.

This design adds three pieces and changes nothing else:

- **A proposal QC pass**: an independent AI pass that reads the finished draft block by block against
  the Master Template entry, the practice rules and the ledger, and lists what is wrong in plain words.
  It never rewrites; the estimator decides.
- **The house shape in the writer**: every write request carries a short job brief shared by all
  systems, the Master Template entry is the frame the block is written into, and the packaged-unit
  doctrine and the shipped-loose verb are rules the writer follows and the verifier enforces.
- **Damper placement**: the plans and risers passes record which fan or unit a damper serves, reading
  the sheets as pictures as well as text; an actuator whose damper is linked is written under that
  system; the rest form one damper block with sheet references and the count, flagged.

The estimator's decisions behind this (2026-10-03): an independent AI agent does the QC; the
template is the ideal and the sequence is taken into consideration; the packaged-unit doctrine as
written in `assets/gem/ame_practice.txt`; the higher count stays, flagged; dampers are traced on the
plans and risers when possible, else listed with page references and a total.

---

## 1. The proposal QC pass

### 1.1 When it runs

After every system is written and before assembly: the draft blocks exist as `WrittenScope`s, the
ledger is complete, the templates and practice rules are loaded. In chat mode it is one more request
(split into parts for a big job); in API mode one more call. It is on by default; `--no-qc` skips it.

### 1.2 What it reads

One request for the whole draft (so cross-system checks are possible), holding:

- the job brief (§2.1);
- for each system: its header and count, its written lines as the draft will print them (text,
  ownership words, quantity, flag), its Master Template entry (the lines and the tech-hour rule),
  its ledger entry (the facts), and its sequence section id;
- the practice rules (`ame_practice.txt`) and the house style guide;
- the packaged/field classification the writer declared for the system (the GEM's Quick Scan
  `unit_type` and `controller`).

A draft over the request limit is split by system groups (whole systems, never a block cut in two),
each part carrying the brief and the full list of system headers so a duplicate across parts can still
be seen.

### 1.3 What it answers

For each block, a list of findings, each with:

```
system      the block's key
line        the line text it is about ("" for a block-level finding)
kind        ownership | not-ame-scope | missing | duplicate | count | wording | placement
say         one sentence in the estimator's words: what is wrong and why
fix         the line as it should read ("" when the fix is to remove it or to add nothing)
severity    must-fix | check
quote       the template line, practice rule or document words it rests on
```

The kinds, in the estimator's terms:

- **ownership**: wrong verb for who furnishes, installs or wires ("Wire" where the device ships
  loose and is "Install and Wire"; "Furnish and Install" where the unit maker furnishes).
- **not-ame-scope**: a line for something inside a packaged unit, a monitored point restated as a
  line, or a device another party owns with no assignment to the controls contractor.
- **missing**: a Master Template line usually present for this kind of unit that the block lacks and
  the documents do not exclude; or an explicit sequence assignment to the controls contractor that
  no line covers.
- **duplicate**: the same device or interlock written in two blocks.
- **count**: a line count that does not match the block's count or the ledger.
- **wording**: not the house form (the template's own words exist for this line).
- **placement**: a line that belongs under another system (a damper actuator under a damper block
  when its fan is known; a duct heater's control under the fan it serves).

And one paragraph per block, "what the estimator would say about this block", and one for the job.

### 1.4 What happens with the findings

- Nothing in the proposal changes by itself. Each `must-fix` becomes a review row at tier 1, each
  `check` at tier 4, worded as the QC pass said it, with the suggested line in the row's action.
- The Evidence Package gains a "Proposal QC" tab: every finding, by block, with the suggested fix,
  and the two columns for the estimator's decision that the Scope lines tab already has, so a
  decision here flows through the corrections mechanism on the next run.
- The QC pass's block paragraphs print on the "How the job was read" tab under the reading
  paragraphs, so the top of the package reads: how the job was understood, then how the draft
  measures up.

### 1.5 What it must not do

Invent a device the documents do not name, change a count, or rewrite the GEM's wording rules. It
compares; it does not write. Findings that name a line the draft does not have, or a system the plan
does not have, are dropped and listed, as unusable answers are elsewhere.

---

## 2. The house shape in the writer

### 2.1 The job brief

One short text built from the ledger after the passes and given to every write request and to the QC
pass, so every system is written knowing the whole job:

- the seven understanding paragraphs, condensed by the sequence pass's own paragraph when the
  dossier is long (the brief is capped at about 4,000 characters);
- the list of systems: key, header, count, kind, packaged or field DDC as the ledger's provider
  facts say ("controller by unit mfr" against "BMS contractor furnishes DDC"), the systems it is
  linked to (serves, is served by, interlocked with);
- the job's general rules from the sequence's notes (fire/smoke dampers by the fire alarm, actuators
  for non-FSD dampers by the controls contractor, the global points);
- the duplicate guard: which device each system already owns (the condensate switch under the VRF
  block, the damper actuator under its fan), so no second block writes it.

### 2.2 The write prompt

The order of what the writer is told changes, not the GEM text:

1. the job brief;
2. the Master Template entry for this kind, introduced as **the frame**: "This is how AME writes
   this kind of system. Write its lines, in its order, with the ownership verb the documents decide.
   Leave a line out only when the documents exclude it. Add a line only when the sequence explicitly
   assigns a device or a piece of work to the controls contractor that no template line covers, or
   names a device the template lacks. Never write a line per monitored point: the integration lines
   cover 'monitor at the BMS'.";
3. the packaged-unit doctrine and the shipped-loose verb, quoted from `ame_practice.txt`;
4. the ledger entry and the evidence, as today;
5. the GEM remains the system prompt; the practice rules already govern where more specific.

### 2.3 What the verifier enforces (code, not prompt)

Added to the checks that already refuse a line (unknown fact, non-ledger count, forbidden words):

- On a system the writer declared packaged/factory controls: a line whose device is on the internal
  list (valve, actuator inside the unit, DX stage, compressor, reversing valve, fan speed, hot gas
  reheat, filter DP, internal safety, refrigerant leak detector of a split, airflow switch) is refused
  as "inside the unit; covered by the integration lines" unless the sequence passage it quotes
  names the controls contractor. The internal list lives in `assets/house_style.json`, not code.
- A line on a packaged unit for a shipped-loose device written "Wire …" is rewritten to "Install
  and Wire …" and listed as a wording change (the estimator's rule: almost every time).
- A device already owned by another system (the brief's duplicate guard) is refused in a second
  block, listed, and the first block keeps it.
- Electric duct heaters: on a packaged unit only the interlock lines are kept (enable/interlock,
  auxiliary contact); the full-scope lines are refused with the practice rule quoted. Under a field
  DDC controller the full scope stands.

### 2.4 The left-out list

The Master Template lines the writer left out of a block are already listed for the estimator. They
now print with the template's own line text as the suggested fix, so adding one back is a decision,
not a rewrite.

---

## 3. Damper placement

### 3.1 The link

The plans pass and the risers pass may each record a `link` fact: subject the damper tag or label as
the sheet writes it ("MD-1 on M-101", "MD at EF-3"), value the fan or unit it serves, source the
sheet, quote the words or labels next to it. Both passes get pictures of their sheets as well as the
text (§3.2), because the relationship is drawn, not written.

The planned systems take the link: a damper linked to a fan joins that fan's facts, and the writer
writes the actuator line in that block (the template's "Furnish and Install Damper Actuator" with the
count of linked dampers). Dampers with no link form one block, "Motorized Dampers", whose lines
carry the sheet references and the total ("(Qty. 7) per M-101.00, M-112.00, M-134.00"), flagged for
the estimator; the stair-top vent dampers interlocked with a smoke detector keep their own line in
that block, as the Master Template's Stair / Elevator Vent entry writes it.

Fire/smoke dampers are unchanged: their own block, interlock and end-switch lines only.

### 3.2 Reading the sheets as pictures

The plans and risers passes send pictures of their sheets the way the schedules pass already does:
each controls-discipline plan sheet and each riser sheet is rendered once at a moderate resolution
into the dossier's image folder, numbered with the dossier's picture ids, and listed in the request.
In the API the pictures go as image blocks; in chat mode the request lists the paths and the judge
opens them. A cap (default 24 pictures a pass, the busiest sheets first by device count) keeps the
request within limits; sheets left out are named in the prompt so the judge knows.

This is the one decision in this spec with a running cost: pictures make the plans and risers passes
heavier in API mode. The estimator chose tracing when possible; pictures are what make it possible.
`--no-pictures` keeps the text-only passes.

---

## 4. Also in this step (small, no decision needed)

- **One flag per decision.** Where the writer attaches the same "*Confirm quantity" or "*Assumed"
  to several lines of one block, the block prints the flag once, under the block, naming the lines.
- **The count note names the place.** "*Qty. (16) per equipment counts for ACCU" becomes "*Qty. (16)
  per the VRF condenser schedule, M-701.00; the plans show 15", using the fact's source place.
- **Job brief in the Evidence Package.** The brief (§2.1) prints first on "How the job was read".

## 5. Later, each its own spec (the estimator decides whether and when)

- **Learn the house shape from the archive.** A tool that reads the sent proposals in the archive by
  system kind and proposes practice rules and template changes into `ame_practice_proposed.txt` for
  approval. Shape, not content; nothing per job.
- **Merge passes.** Details with risers; the sequence pass also planning the systems. Fewer requests,
  same ledger.
- **A model per pass.** In API mode: Opus for the schedules, plans, details and network passes, the
  strongest model for the sequence, spec, writing and QC passes.
- **Corrections into rules.** The QC tab's decisions and the scope-line decisions proposing practice
  rules automatically, as the corrections mechanism already starts to do.

---

## 6. Where it lands in the code

- New: `src/estimator/writing/qc.py` (the QC request, schema, answer checks, findings to review rows
  and tab); `src/estimator/writing/brief.py` (the job brief from the ledger).
- Changed: `whole_job.py` (write prompt order; the packaged-unit, duplicate and duct-heater refusals;
  the shipped-loose rewrite), `assets/house_style.json` (the internal-device list, the left-out
  suggested text), `ledger/passes.py` (link kind allowed for plans; pictures for plans and risers;
  the picture cap), `ledger/to_plan.py` (dampers join the linked fan; the damper block), `dossier.py`
  (render plan and riser sheets like schedule pictures), `judge.py` (the "qc_job" question kind),
  `assemble.py` (one flag per decision; the count note's place), `workbook.py` (Proposal QC tab; the
  brief on How the job was read), `__main__.py` (brief, QC pass, `--no-qc`, `--no-pictures`).
- Untouched: the GEM text, the Master Template, the readers, the catalogue, the proposal and price
  sheet writers.

## 7. Testing

Unit tests on hand-made drafts and ledgers: a packaged unit's internal-device line is refused and the
reason quotes the rule; a shipped-loose "Wire" becomes "Install and Wire"; a duplicate device in a
second block is refused; duct heater full scope on a packaged unit is reduced to the interlock lines;
a damper linked to a fan writes its actuator under the fan and leaves the damper block; an unlinked
damper block prints sheet references and the total; the QC answer's findings become review rows and
tab rows, and a finding naming an unknown line is dropped and listed; the brief lists every system
with its packaged/field class and links; the plans pass request lists its pictures within the cap.

Then the gate: 26-0193 again in chat mode, the estimator reading the VRF, ERV, duct heater and
damper blocks and the QC tab. No per-job tuning.

---

## 8. The estimator's answers (2026-10-03) — binding on the pieces above

1. A factory-installed device is never a line, blanket wiring clause or not; "Wire X (Furnished by
   Unit Mfr.)" only when the sequence itself assigns that wiring to the controls contractor.
2. "Furnish <point>" lines only for a system AME's own DDC controller runs; on packaged units the
   three integration lines cover every monitored point.
3. Other trades in brackets: "(Relay Furnished by FA)", "(Furnished by Others)" for dampers and end
   switches, "(Furnished by Mechanical Contractor)" for condensate pumps and float switches.
4. Systems the sequence names but no drawing shows print in the base bid with their integration
   lines, "Qty (##)" and "*Quantity per plumbing drawings"; no longer held back as questions.
5. Residential equipment in the hundreds stays in the normal scope; an add or deduct alternate only
   when the documents clearly say so; never invented. Factory-controlled units with no BMS work are a
   named exception.
6. Electric unit heater with a factory thermostat: one "Install and Wire Space Thermostat (Furnished
   by Unit Mfr.)" line with the plan count.
7. UL-864 UUKL: write the UUKL-listed controls in scope; no exception.
8. Tech hours for integration-only systems with no template rule: 4 hours each.
9. One "*" clarification per block, naming the lines; per-line detail in the Evidence Package.
10. The GEM rewrite keeps its structure; flags become words.

These are recorded in `assets/gem/ame_practice.txt` and govern the writer, the verifier and the QC pass.

## 9. Two more pieces, added at the estimator's request

### 9.1 The GEM in plain language

`assets/gem/BMS_DDC_GEM_v4.txt`, written from v3.2: the same method and structure (Quick Scan,
contractor-name rule, CC work extraction, scope ownership and device ownership resolution, mandatory
minimum points, damper and fire-alarm relay rules, factory-controls rule, SOW order, contradiction
scan, Self-QC), in plain sentences, without emoji or decorative markers; flags as words (CONFIRM
QUANTITY, CONFIRM OWNERSHIP, ASSUMED, NOTE); the practice rules folded into the sections they refine
(the factory-controls rule becomes the packaged-unit doctrine; the shipped-loose verb; the three
integration lines; the one-clarification-per-block rule). The tool loads v4; v3.2 stays in the repo
for comparison. `gem_prompt()` keeps its cuts and additions working against the new headings. The
original `.docx` in the Brain folder is untouched. The rewrite is reviewed by the estimator before it
replaces v3.2 (a side-by-side of every rule, old and new, in the Evidence of the plan's report).

### 9.2 Running a job from any session

A repo command, `/run-job <job folder> [--out …]`, usable in any Claude Code session whatever model it
runs on. It drives chat mode to completion: run the estimate; for each waiting request, hand the
request file to a subagent on the configured judge model (default the strongest available, set in
`.claude/run-job.json`: `judge_model`, `writer_model`, `qc_model`), which writes the answer file;
run again; stop when the proposal is written or a request fails three times. The session only runs
commands and copies files. With the API on, the command runs the estimate once and the models per
pass come from the tool's own setting (§5). The judge subagent's instructions are the request's own
system prompt and prompt; the command adds only the answer-file contract and the "no subagents" rule.
