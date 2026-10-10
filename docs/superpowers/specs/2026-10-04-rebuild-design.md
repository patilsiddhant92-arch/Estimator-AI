# Estimator rebuild — design (2026-10-04)

Status: approved by the estimator on 2026-10-04 ("Do not cut the scope and quality at all"; target the same day, 11:59 PM).

## 1. Why

The current app has the AI write free-text scope lines, then about 40 text patterns in assembly parse, rewrite or
refuse them. Rules live in five places (GEM, practice rules, house style, Master Template, code) that contradict each
other. Most defects this month came from that layer. Patching it further is not possible (the estimator,
2026-10-04). The rebuild replaces the writing, checking and assembly with a structured job model; it keeps the parts
that read the job.

## 2. Ground rules (the estimator's, binding)

1. The job's documents drive the scope. Every device line rests on a citation from this job.
2. No "AME standard" line, no fallback line, no example from another job. A line is written only when this job's
   documents call for it.
3. The Master Template sets only the shape of a block: the header form, the order of lines, the wording form of a
   line. Never its content.
4. Ownership is the estimator's responsibility: every line carries Furnish / Install / Wire and who does each.
5. The schedule count prints (the estimator's ruling, 2026-10-09, replacing "higher count prints"): the equipment
   schedule's count is the working count; plan, riser and picture counts verify it, and a difference is a flag
   (DISCREPANCY; CONFLICT where no schedule gives the count, when the highest prints) with every count named. Never
   change a count silently; unknown is "Qty (##)".
6. One "*" clarification per block; every assumption says what and why.
7. The estimator's practice rules (packaged units, shipped-loose devices, dampers under their fan, duct heaters in
   one place, VRF and split as one block, integration lines, UUKL, residential equipment) carry over unchanged in
   meaning into the Playbook.
8. Job data never leaves the machine; never into the repo.

## 3. What is kept, what is new

| Kept as is (imported, not edited) | New (package `src/bms/`) |
|---|---|
| `estimator.catalogue` (documents, sheets, spec sections, tags) | Playbook (one rule book) |
| `estimator.reading` (pages, schedules, devices, keynotes) | Job model and its validators |
| `estimator.ledger` facts, passes, run (staged reading) | Planner from ledger to job-model skeleton |
| `estimator.proposal` Word writer, `estimator.price_sheet` | Writer (AI fills the model), QC and revise |
| | Vision count cross-check |
| | Renderer (model to house wording) |
| | Review page; held-out measurement |

The old app stays runnable for shadow use until the new one replaces it.

## 4. The interfaces (fixed before any parallel work)

### 4.1 Playbook — `playbook/`

- `playbook/rules.md`: every practice rule in plain words, one heading per topic, each rule with a short name
  ("Packaged units", "Shipped-loose devices"). Loaded whole as the cached instructions of every AI step.
- `playbook/shapes.yaml`: one entry per system type (from the Master Template, shape only): `name`, `applies_to`
  (prefixes, kind words), `header` form, `family_names`, `line_order` (slot names in print order), `wording` per slot
  (the house phrase form, e.g. `"{verb} {device}{owner}{qty}"`), `tech_hours` rule. No default lines.
- `playbook/wording.yaml`: verbs ("Furnish and Install", "Furnish", "Furnish and Wire", "Install and Wire", "Wire"),
  owner brackets ("(Furnished by Unit Mfr.)", "(Relay Furnished by FA)", "(Furnished by Others)", "(Furnished by
  Mechanical Contractor)"), integration trio text, clarification forms.

### 4.2 Job model — `src/bms/model.py` (dataclasses, JSON round-trip, JSON Schema exported for the AI)

```
Job: name, systems[System], front_end, exceptions[Exception], questions[str]
System: key, name, shape (Playbook shape name), control (packaged | field | integration | none),
        families[Family], sequence_refs[Ref], devices[Device], clarifications[Clarification],
        tech_hours, alternate (base | add | deduct)
Family: name, tags[str], count Count
Count: value (int | null), sources[Ref], others[{value, ref}]   # higher wins; others print in the note
Device: id, slot (Playbook line slot), name (the document's words), verb, furnished_by, installed_by, wired_by,
        quantity Count, refs[Ref] (at least one), assumption {what, why} | null, flag (none|quantity|ownership|assumed)
Ref: source_id, quote (exact words), where (sheet / spec section / page)
Clarification: kind (confirm | assumed | per_drawings | note), text
Exception: system_key, text, refs[Ref]
```

### 4.3 Validators — `src/bms/validate.py`

`validate(job, playbook) -> list[Finding]`; `Finding: rule (Playbook rule name), system_key, device_id | null,
severity (must_fix | check), what (plain words), fix (plain words)`. One small function per Playbook rule, on fields,
never on sentence text (e.g. packaged control: no device with verb "Furnish" whose slot is a point; a device with no
ref is must_fix; a duct heater device outside the heater system is must_fix).

### 4.4 Renderer — `src/bms/render.py`

`render(job, playbook) -> ProposalDraft` (the blocks the existing Word and price-sheet writers take). Pure function:
same model, same text. All wording from `wording.yaml` and `shapes.yaml`.

### 4.5 AI steps — `src/bms/ai.py`

Each step is one prompt plus a JSON Schema; the answer is validated against the schema before use.
- `write_system(system_skeleton, evidence, playbook) -> System` (devices filled).
- `qc_job(job, evidence_index, playbook) -> list[Finding]` (independent reviewer).
- `revise_system(system, findings, evidence, playbook) -> System` (one round, must_fix only).
Chat mode (request and answer files, as today) and API mode (prompt caching on the Playbook) share the same code.

### 4.6 Counts — `src/bms/counts.py`

`count_tags(sheet_image, tag_pattern) -> {value, boxes}` by vision on tiles; the planner compares it with the
text count and records both in `Count.others`; disagreement sets the quantity flag.

### 4.7 Review page — `out/<job>/Review.html`

Generated from the Job and the Findings: one card per system with its open questions (at most about 15 per job,
ranked), each count with a cropped image of what was counted, buttons Accept / Change / Delete. Decisions save to
`decisions.json`; the next run applies them and proposes Playbook rule changes from repeated decisions.

### 4.8 Measurement — `tools/measure.py`

On the held-out jobs only: match the rendered lines to the estimator's final proposal (system, device, verb,
quantity) and print the share matched, missed and extra. Used to see whether a change helped, never to tune.

## 5. Workstreams (parallel, each in its own worktree, each against the interfaces in section 4)

| # | Workstream | Depends on | Model |
|---|---|---|---|
| 0 | Interfaces: model.py, Playbook file formats, JSON Schemas, stub functions, contract tests | — | Fable (controller) |
| 1 | Playbook content: merge GEM v4, practice rules, house style, Master Template shapes into `playbook/` | 0 | Opus, estimator reviews |
| 2 | Planner: ledger to Job skeleton (systems, families, counts, groups, damper links, heaters) | 0 | Opus |
| 3 | Validators | 0, 1 | Sonnet |
| 4 | Renderer and the bridge to the Word and price-sheet writers | 0, 1 | Sonnet |
| 5 | AI steps: write, QC, revise prompts and schemas; chat and API modes | 0, 1 | Opus |
| 6 | Vision count cross-check | 0 | Opus |
| 7 | Review page and decisions; measurement tool | 0 | Sonnet |

Integration (controller): wire 2 to 5 to 3 to 4 into one `bms estimate` command and `/run-job`, run on one job,
fix, run on a held-out job.

## 6. Timeline

- Day 1: workstream 0 (morning), then 1 to 7 in parallel. The estimator reviews the Playbook draft.
- Day 2: integration; first full run on a test job; the estimator reads the draft.
- Day 3: fixes from the estimator's reading; a held-out run with the measurement; package as a Claude skill.

The tight points are the estimator's Playbook review and the vision counts (the app ships with text counts and the
cross-check flags if vision needs longer).
