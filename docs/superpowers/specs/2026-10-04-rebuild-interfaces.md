# Estimator rebuild — the interfaces (Phase 0, 2026-10-04)

The contract every workstream builds against, with the design (`2026-10-04-rebuild-design.md`, §2–§5 binding).
Everything named here exists on branch `rebuild` as working code (no stubs are left); the docstrings repeat the
contract. `tests/bms/test_contracts.py` pins it: a workstream that needs a contract change asks the
controller; it never edits `model.py`, `playbook.py`, `run.py`, `__main__.py`, the fixtures or the contract tests.

Ground rules for every workstream: Python via `.venv/Scripts/python.exe`; `src` is on the path through the
editable install (`import bms` works anywhere in the repo, and `python -m bms`); never edit `src/estimator/`
(import only); never put job text in code, tests or docs (NDA — tests use the invented fixture); no new
dependency without the controller (`jsonschema` and `yaml` are not installed — the Playbook is JSON, and
`bms.model.schema_errors` is the schema check); never push; commits end with
`Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`; run `.venv/Scripts/python.exe -m pytest tests -q -p no:cacheprovider`
(old suite and `tests/bms`) before committing.

## 1. Package layout

| Path | What | Owner |
|---|---|---|
| `src/bms/__init__.py` | package | controller |
| `src/bms/model.py` | Job model, enumerations, JSON round-trip, JSON Schema, schema check | controller |
| `src/bms/playbook.py` | Playbook loader and checks, `shape_for` | controller |
| `src/bms/plan.py` | `plan_job` | workstream 2 |
| `src/bms/validate.py` | `validate` | workstream 3 |
| `src/bms/render.py` | `render`, `ProposalDraft`, `RenderedLine` | workstream 4 |
| `src/bms/ai.py` | `write_system`, `rewrite_for_count`, `qc_job`, `revise_system`, `evidence_for`, `evidence_index`, transports | workstream 5 |
| `src/bms/citations.py` | source ids in client text: `SourceIds` (`scan`, `refusal`, `without_issued`; `source_sheets`, FINAL-J), `job_tags`, `job_ids`, `job_sheets`, `source_sheets`, `tag_tokens`, `plan_refs`, `ref_sheets`, the clarification labels | controller |
| `src/bms/counts.py` | `count_tags`, `cross_check`, `CountResult`, `Box`, `flag_written_devices`, `publish_proofs` | workstream 6 |
| `src/bms/review.py` | `review_page`, `load_decisions`, `apply_decisions`; the decisions history: `SavedDecision`, `load_history`, `save_history`, `merge_decisions(history, saved, *, job=None)`, `apply_seen`, `copies_seen`, `held_back`, `unhonored_decisions`, `system_digest`, `accept_families`; `DECISIONS_FILE`, `DECISIONS_HISTORY` | workstream 7 |
| `tools/measure.py` | `measure`, `MeasureResult`, `LineMatch` | workstream 7 |
| `src/bms/run.py` | `estimate`, `RunResult` (the orchestration) | controller |
| `src/bms/status.py` | `check(out, cache) -> Status` (exit code and plain lines), `Status`, `RUN_STATE` (`"run state.json"`) | controller |
| `src/bms/doctor.py` | `run_doctor` and its checks (Python, dependencies, `.claude/run-job.json` models, Playbook, cache folder) | controller |
| `src/bms/playbook_lint.py` | `lint_playbook`, `LintProblem`, `referenced_rule_names` | controller |
| `src/bms/__main__.py` | `python -m bms estimate JOB --out OUT [--cache C] [--mode chat\|api]`; `status OUT [--cache C]`; `doctor [--cache C] [--playbook P] [--config F]`; `playbook-lint [ROOT]` | controller |
| `playbook/rules.md`, `shapes.json`, `wording.json` | the Playbook | workstream 1 (content), controller (format) |
| `tests/bms/fixtures/sample_job.json`, `sample_playbook/` | the invented test job and minimal Playbook | controller |
| `tests/bms/test_contracts.py` | contract tests | controller |

## 2. The Job model — `src/bms/model.py`

Frozen dataclasses; every list field is a `tuple`. Each class has `to_dict()`, `from_dict(d)` (strict: unknown key,
missing required key, wrong type or a value outside an enumeration raises `ModelError` naming the path, e.g.
`Job.systems[0].devices[0].verb`), `to_json()`, `from_json()`. `to_dict()` → `from_dict()` is lossless.

### 2.1 Enumerations (exact strings; tuples of the values beside each alias)

| Alias | Values | Tuple |
|---|---|---|
| `Verb` | "Furnish and Install", "Furnish", "Furnish and Wire", "Install and Wire", "Wire" | `VERBS` |
| `Control` | "packaged", "field", "integration", "none" | `CONTROLS` |
| `Flag` | "none", "quantity", "ownership", "assumed" | `FLAGS` |
| `ClarificationKind` | "confirm", "assumed", "per_drawings", "note" | `CLARIFICATION_KINDS` |
| `AlternateKind` | "base", "add", "deduct" | `ALTERNATES` |
| `Party` | "AME", "Unit Mfr.", "FA", "Mechanical Contractor", "Electrical Contractor", "Others", "Owner" | `PARTIES` |
| `Severity` | "must_fix", "check" | `SEVERITIES` |
| `FrontEndMode` | "new-system", "extend-existing" | `FRONT_END_MODES` |
| `DecisionAction` | "accept", "change", "delete" | `DECISION_ACTIONS` |

### 2.2 Classes (field: type = default)

```
Ref:            source_id: str, quote: str, where: str
                  source_id is a dossier / ledger id without brackets ("S41", "I2", "Q7", "F17"); quote the exact
                  words; where the place ("M-201, Drawings.pdf page 3").
OtherCount:     value: int, ref: Ref
Count:          value: int | None, sources: tuple[Ref] = (), others: tuple[OtherCount] = ()
                  value is the printed count = the highest any source gives; None = unknown, prints "Qty (##)".
                  others = every different count with its source (printed in the note). highest() -> int | None.
Family:         name: str, tags: tuple[str], count: Count
Assumption:     what: str, why: str
Device:         id: str, slot: str, name: str, verb: Verb, furnished_by: Party, installed_by: Party,
                wired_by: Party, quantity: Count, refs: tuple[Ref] (>= 1, enforced: ModelError),
                assumption: Assumption | None = None, flag: Flag = "none"
                  id unique in the job ("EF.d3"); slot a slot of the system's shape; name the document's words.
Clarification:  kind: ClarificationKind, text: str
Served:         key: str, name: str, tags: tuple[str], heaters: tuple[str], heater_key: str, heater_name: str
                  a unit duct heaters serve (its key, name, tags), the heater tags serving it, and the duct heater
                  block that writes them.
System:         key: str, name: str, shape: str, control: Control, families: tuple[Family],
                sequence_refs: tuple[Ref] = (), devices: tuple[Device] = (), clarifications: tuple[Clarification] = (),
                tech_hours: float | None = None, alternate: AlternateKind = "base",
                no_scope_reason: str | None = None, serves: tuple[Served] = ()
                  shape is a Playbook shape name, or "" when no shape applies (an untemplated system).
                  serves (the planner's): on the duct heater block one entry per unit it serves; on a served unit's
                  block its own entry, so its writer leaves the heaters to the heater block.
ScopeException: system_key: str, text: str, refs: tuple[Ref] = ()        # design §4.2 "Exception" (renamed: builtin)
FrontEnd:       mode: FrontEndMode, existing_system_name: str | None = None, devices: tuple[Device] = (),
                clarifications: tuple[Clarification] = (), tech_hours: float | None = None
Header:         quote_number: str, reference: str, mep_engineer: str, based_on: tuple[str], date: str (ISO),
                to: str = "All Bidders"                                     # mirrors estimator.scope.Header
Job:            name: str, systems: tuple[System] = (), front_end: FrontEnd | None = None,
                exceptions: tuple[ScopeException] = (), questions: tuple[str] = (), header: Header | None = None,
                source_sheets: tuple[str] = ()
                  source_sheets: the id-shaped sheet numbers the ledger's sources' wheres name (upper case, sorted;
                  set once by the run, `bms.citations.source_sheets`); not part of K (`job_sheets`, the planner's
                  wheres) since FINAL-J: a known sheet only in a where and right after a sheet word in client text
                  (`SourceIds.source_sheets`); a bare one that is an issued id stays refused / must_fix / cut. () on an
                  old Job.json.
                  job.system(key) -> System (KeyError); job.with_system(system) -> Job (replaced by key).
Finding:        rule: str, system_key: str, device_id: str | None, severity: Severity, what: str, fix: str
                  rule = a Playbook rule name (### heading); system_key "" for the front end / whole job.
Decision:       system_key: str, action: DecisionAction, device_id: str | None = None, family_name: str | None = None,
                device: Device | None = None, count: Count | None = None, finding_rule: str | None = None,
                reason: str = "", was: Device | None = None
```

`MODEL_CLASSES` lists them all.

`Finding.severity` is only ever `must_fix` or `check`, the run's own findings too: the run's "check this system"
card (an earlier delete that may be back re-worded) is a `check` (REVIEW-FINAL F2: the run built it as
"should_fix", which is not a `Severity`; the fix is to use `check`).

### 2.3 JSON Schema and the schema check

- `json_schema(cls) -> dict` — the schema of any model class, in the form Anthropic structured outputs accept:
  every object lists all its properties in `required` (fields with defaults too) and has
  `additionalProperties: false`; nullable fields are `anyOf [X, {"type": "null"}]`; enumerations are
  `{"type": "string", "enum": [...]}`; `Device.refs` has `minItems: 1`; nested classes are inlined (no `$ref`);
  each field carries a `description`.
- `write_system` / `revise_system` answer `json_schema(System)`. `qc_job` answers
  `{"type": "object", "properties": {"findings": {"type": "array", "items": json_schema(Finding)}},
  "required": ["findings"], "additionalProperties": false}`.
- `schema_errors(value, schema) -> list[str]` — every way a JSON value breaks a schema (type, enum, properties,
  required, additionalProperties false, items, minItems, anyOf). Run it on an AI answer before `from_dict`.

## 3. The Playbook — `playbook/` and `src/bms/playbook.py`

Note: the design names `shapes.yaml` / `wording.yaml`; the files are JSON (`yaml` is not installed; the brief
says JSON). Same content.

### 3.1 `rules.md`
`# ` title; one `## ` heading per topic; under a topic each rule is a `### ` short name then plain sentences.
Rule names are unique (they are the ids `Finding.rule` names). No rule outside a topic, no empty rule, no `####`.
HTML comments are ignored, except `<!-- sample -->` right under a rule heading, which marks a Phase 0 format
sample (workstream 1 replaces it). Topics now: Evidence and citations; Ownership; Counts and quantities;
Clarifications and assumptions; Packaged units; Shipped-loose devices; Dampers under their fan; Duct heaters;
VRF and split systems; Integration lines; UUKL; Residential equipment; Front end; Exceptions and alternates;
Tech hours; Shapes and wording. The whole file is `Playbook.rules_text`, the cached instructions of every AI step.

### 3.2 `shapes.json`
`{"$format": {...}, "shapes": [entry, ...]}`; each entry has exactly:

| Field | Form |
|---|---|
| `name` | unique text; `System.shape` refers to it |
| `applies_to` | `{"prefixes": [upper case, no dash], "kind_words": [lower case]}` |
| `header` | form with `{n}` (count or `##`), `{name}`, `{tags}` |
| `family_names` | non-empty list, print order |
| `line_order` | non-empty list of unique slot names, print order |
| `slot_kinds` | slot → `device` \| `point` \| `interlock` \| `integration` \| `wiring`, exactly the slots of `line_order` |
| `wording` | slot → phrase form with `{verb}`, `{device}`, `{owner}`, `{qty}`, `{what}`, exactly the slots of `line_order` |
| `tech_hours` | `{"per": unit\|hardware_point\|indoor_unit\|panel\|fan\|fixed\|line, "hours": number\|null, "when": [{"if": [slots], "hours": n}]}` |
| `under` (optional) | sub-line slot → parent slot (earlier in `line_order`); the sub-line prints one level in after its parent, no verb (integration) |

No default lines anywhere: a shape says how a line prints, never that a line exists.

### 3.3 `wording.json`
`$format`, optional `$draft` (dotted keys still placeholders), and exactly: `verbs` (= `VERBS`, in order);
`owner_brackets` (every party but AME → `" (Furnished by …)"`, with its leading space); `integration_trio`
(`lines`: 3 forms with `{what}`, `depths`: 3 of 1 or 2); `clarifications` (each kind → a form starting `*` with
`{text}`); `header` (`count`, `unknown_count`, `tags_joiner`); `quantity` (`line` with `{n}`, `unknown`,
`others_note` with `{counts}`); `count_causes` (`form` with `{causes}`, `joiner`, and the client words of each
likely cause of a high plan count: `typical`, `labelled_twice`; `bms.playbook.COUNT_CAUSE_KEYS`; the retired
`same_plan` and `shown_again` were removed in FINAL-H and a file still giving them is refused).

### 3.4 Loader

```
load_playbook(root: Path = <repo>/playbook) -> Playbook        # raises PlaybookError("<file>: <problem>")
Playbook: rules_text: str, topics: tuple[str], rules: dict[str, Rule], shapes: dict[str, Shape], wording: Wording,
          root: Path
          .rule(name) -> Rule (KeyError), .shape(name) -> Shape (KeyError),
          .shape_for(system_kind: str, prefixes) -> Shape | None
             first shape (file order) sharing a prefix (compared upper case without dash/space/underscore); else
             first whose kind word appears as whole words in system_kind (plural s/es allowed); else None.
Rule:     topic, name, text, sample: bool
Shape:    name, prefixes, kind_words, header, family_names, line_order, slot_kinds: dict, wording: dict,
          tech_hours: TechHours; .slots_of_kind(kind) -> tuple[str]
TechHours: per, hours: float | None, when: tuple[(tuple[slot], hours)]
Wording:  verbs, owner_brackets: dict, integration_trio: tuple[str] (3), integration_depths: tuple[int],
          clarifications: dict, header: dict, quantity: dict, draft: tuple[str], count_causes: dict
Constants: TECH_HOUR_BASES, SLOT_KINDS, DEFAULT_ROOT, COUNT_CAUSE_KEYS
```

## 4. The old-app types consumed and produced (imported, never edited)

| Type / function | Module | Used by |
|---|---|---|
| `Catalogue` (job, pages, sheets, sections, bid, tags, flags, overview); `catalogue_job(root, cache_dir, workers, documents=None)` | `estimator.catalogue.job` | run, plan, counts |
| `JobReading`; `read_job(catalogue, page_opener=None, cache_dir=None, judge=None)` | `estimator.reading.job` | run |
| `Dossier` (job_name, text, images: tuple[DossierImage], sources: dict id→where, families, device_totals, counts, stats, sections, schedules, sheet_pages: dict 7c id→(document, page)); `build_dossier(catalogue, reading, cache_dir)`; `sheet_pictures(catalogue, cache_dir, keys, what)`; `plan_areas` (re-exported from `estimator.reading.inventory`) | `estimator.writing.dossier` | run, plan, ai, counts |
| `plan_areas(plans: [(sheet, tags)]) -> {(document, page): area}` (retired, FINAL-G: every sheet its own area); `plan_area_doubts(plans, areas=None) -> [((document, page), (document, page))]` (a hint only); `is_type_tag(tag)`, `counted_per_place(tag, places, most_on_one_sheet, code=False)`; `plan_groups(plans, codes=()) -> {(document, page): group}`, `plan_count(found, groups, per_place) -> int`, `plan_floors(catalogue, typicals=()) -> {(document, number): floors}`, `counting_pages(catalogue, governing) -> pages`, `first_pages(catalogue) -> {(document, page): first page}` (the pages that only repeat an alike number, FINAL-N), `sheet_labels(sheets) -> {(document, page): label}` (FINAL-I, the one counting rule); `placements(catalogue, tags, typicals=(), pages=None) -> {tag: Placements}`; `COUNT_CAUSES_LEAD`, `COUNT_CAUSE_WORDS` (`typical`, `labelled_twice`; `SAME_PLAN` removed, FINAL-H) | `estimator.reading.inventory` | dossier, render |
| `Ledger` (sources, facts: dict[id, Fact], understanding, complete, stopped_at, job_name, refused; `of_kind`, `about`, `find`, `printed_count`, `to_dict`/`from_dict`/`load`); `Fact` (id, kind, subject, value, source_id, quote, stage, state, contradictions, was_settled); `Contradiction`; `KINDS`; `where_short` | `estimator.ledger.facts` | plan |
| `read_job(judge, dossier, catalogue, save_to=None, limit=None, pictures=True, picture_cap=24) -> Ledger` (imported as `read_ledger`; the brief's "read_ledger") | `estimator.ledger.run` | run |
| `ledger_plan`, `count_note`, `place_words` (the old planner, for reference / reuse) | `estimator.ledger.to_plan` | plan (may import) |
| `Judge(cache_dir, mode="chat"\|"api", job=...)`, `retire_requests`, `ask_pass`, `waiting`; `_key(model, prompt, system_prompt)`; `DEFAULT_MODEL`, `KEY_VARIABLE`, `MODEL_VARIABLE` | `estimator.writing.judge` | run (reading), ai |
| `job_header(catalogue, reading, today) -> (estimator.scope.Header, flags)` | `estimator.writing.front_end` | run |
| `estimator.scope.Job` / `Header` / `FrontEnd` / `Block` / `Item` / `Run` / `Alternate` (pydantic, frozen) | `estimator.scope` | render (produces) |
| `write_proposal(job: estimator.scope.Job, template_path, out_path) -> Path` | `estimator.proposal.write` | run (via `_build`) |
| `write_price_sheet(job: estimator.scope.Job, template_path, book: PriceBook, out_path) -> Path`; `check_fit(job)` | `estimator.price_sheet.write` | run (via `_build`) |
| `PriceBook.load(price_book, aliases)` | `estimator.price_sheet.price_book` | run |
| `_build(job, template, workup_template, book, out) -> (proposal, sheet)`; `_safe_filename`; `PROPOSAL_TEMPLATE`, `WORKUP_TEMPLATE`, `PRICE_BOOK`, `ALIASES` | `estimator.__main__` | run |
| `write_evidence(path, catalogue, reading=None, systems=None, review_flags=(), plan=None, ledger=None, qc=None, brief=None)` | `estimator.evidence.workbook` | run (catalogue, reading, ledger only) |
| `read_proposal(path, template_path) -> estimator.scope.Job` | `estimator.proposal.read` | measure |

## 5. The functions each workstream fills

### Workstream 2 — `bms.plan`
`plan_job(ledger: Ledger, catalogue: Catalogue, dossier: Dossier, playbook: Playbook) -> Job` — the skeleton:
systems with key, name, shape (`playbook.shape_for`, or ""), control, families (tags, Count with highest value,
sources, others), sequence_refs, alternate; devices / clarifications empty, tech_hours None. VRF/split groups one
system (indoor, condensing, branch-selector families); dampers linked to a fan under that fan; duct heaters in one
place; exceptions and questions filled; front_end set; header left None. Pure, no AI.

### Workstream 3 — `bms.validate`
`validate(job: Job, playbook: Playbook) -> list[Finding]` — one small function per Playbook rule, on fields only;
`Finding.rule` is a key of `playbook.rules`. Ordered by system then device. Never raises on a well-formed Job.

### Workstream 4 — `bms.render`
`render(job: Job, playbook: Playbook) -> ProposalDraft`.
`ProposalDraft(scope: estimator.scope.Job, lines: tuple[RenderedLine])`;
`RenderedLine(system_key: str, device_id: str | None, kind: "header"|"line"|"note", text: str, verb: str | None,
quantity: int | None)`. Pure; all wording from the Playbook; `job.header` required; add/deduct systems to the
alternates; exceptions to `named_exceptions`; a shapeless system in the form "{verb} {device}{owner}{qty}".
The quantity note (`others_note`) names each other count by its label ("(70) per plan placements; 11 per schedule
rows"). When a quote of the count is an equipment counts line that names why the placements are high, the
"plan placements" label is followed by `count_causes.form` with each cause's client words, in this order:
`typical`, `labelled_twice` (the words of `COUNT_CAUSE_WORDS` after `COUNT_CAUSES_LEAD`; the retired "same plan
as" and "shown again" causes could not fire since FINAL-G and were removed in FINAL-H). Only the cause's kind is read: its
tags, sheets and the estimator's hints never print.

Plan counting, lead ruling FINAL-I (the final rule; conservative: when in doubt the sheets are SUMMED, since an
overcount is named for the estimator and an undercount is invisible). One rule serves the dossier's equipment counts
line and `inventory.placements` / `_as_type` (the Evidence Package), so the two always agree: `plan_groups`,
`plan_count`, `plan_floors`, `counting_pages`, `sheet_labels` in `estimator.reading.inventory`.
- Sheets are keyed by (document, page), never by sheet number. A plan sheet whose number is in another document of
  the same issue with exactly the same text (not an addendum, a duplicate file or a marked-up copy, `repeats`) is
  counted too (two identical buildings, REVIEW-FINAL5 F7); a number counted from two documents is printed with its
  document's name ("M-101 (Second Building.pdf)").
- Plan sheets are one plan group only when ALL hold: the same document; two different sheet numbers (two pages of
  one number are never one group: alike on every page they are one plan for several floors, else each page is its
  own sheet, REVIEW-FINAL7 F7); the same title words IN THE SAME ORDER (`catalogue.job.title_words`, since FINAL-K:
  "BUILDING 1 LEVEL 2" and "BUILDING 2 LEVEL 1" are two places, REVIEW-FINAL6 F2) once the sheet number and the
  trade and plan words (PLAN, PLANS, DUCTWORK, DUCT, PIPING, PIPE, CONTROLS, CONTROL, HVAC, MECHANICAL, MECH,
  PLUMBING, AND, punctuation) are taken out, with a floor word left (FLOOR, LEVEL, an ordinal, a number, BASEMENT,
  ROOF, TYPICAL ...); and at least AREA_SHARED (3) unit tags repeated, AREA_OVERLAP (0.6) of the smaller sheet's.
  The evidence is the labels alone (`line_labels`, never the backstop), and a type's tag, or a unit's tag labelled
  TYPE_ON_ONE_SHEET (4) or more times on the sheet, is never evidence. BASEMENT 1 / 2, BLDG. A / B, SUITE 3 / 4,
  TOWERS 1 AND 2 / 3 AND 4, 1000 / 2000 never group.
- Pages printed again: a sheet number on 2 or more pages of ONE document is set aside to its first page only when
  every page of that number in that document has the same text (`inventory.first_pages`, `_alike_pages`; one plan
  standing for one floor per page, `plan_floors` multiplies it by its pages). Pages of one number with other text
  are each read and counted (REVIEW-FINAL7 F7: pages 1 and 3 alike, page 2 other, are three sheets). A typical sheet
  is read on its first page in each document, and another page of its number in that document only when it shows
  something the first lacks (`governing_pages`).
- Typical sheets and floors are keyed by (document, sheet number), never by the number alone (FINAL-O, REVIEW-FINAL8
  H4): `typical_sheets` gives one `TypicalSheet` per (document, number) with its `document`, `plan_floors` and
  `count_devices` give its floors to that document's sheet only, and `governing_pages` never sets aside another
  document's page of the number because the number is typical in one document. A number printed twice alike in
  Mech.pdf is two floors there; Second Building.pdf's M-101 on two pages of other text is read page by page, once.
- In a group a unit's tag counts once, and a tag counted at every place (`counted_per_place`: a type's tag
  `is_type_tag`, EBB-A, CUH-A, AC-3.0; a schedule's type code; a numbered tag drawn at TYPE_PLACED places with
  TYPE_ON_ONE_SHEET on one sheet, labels as drawn) the most labels of one sheet of the group; each times the floors
  the group's sheets stand for, every floor once (typical floors 2-5 and 2-5 are 4 floors; 2-5 and 6-10 are 9).
  The groups, and every sheet in no group, are summed.
- The line's "Reading notes" (the estimator's and the writers' hints, never a client cause): each group of 2+
  sheets ("M-101 and M-201 counted as one plan: same floor title, same units; check"); each pair that MAY show one
  plan but is not a group (`plan_area_doubts`: "M-101 and C-101 may show one plan; both are counted, the higher
  count ..."); each numbered tag counted on 2+ plans, at most three ("EBB-1 is on 10 plans (M-101, M-102, M-103 …),
  counted on each, 10: likely a type used on each plan; if it is one unit shown on several plans, it is 1 ..."); each
  unit's tag labelled 2 or 3 times on one sheet ("FCU-1 3 times on M-101, counted as one unit: if it is a typical
  unit placed at each of those places, check the schedule's quantity"); and, when every sheet's labels add up to more
  than the placements, that sum. Every sheet is listed with its labels ("M-101 9; M-201 9"), never "same plan as". A
  schedule's QUANTITY column above the placements still wins (the higher count). The inventory counts a scheduled
  unit's tag the plans count more than once as that many units ("counted N times on the plans ... check the count"). When the placements are still above every other count, the line's head (the part the
ledger's count fact quotes) ends "; placements above the other counts, likely: <causes>" (a typical unit at each
place; one unit labelled more than once, said only of tags counted at every place) and its "Reading notes" give the
tags and sheets. The inventory's type-tag check (`placements`, "labelled N times on the plans") sums every sheet's
labels, never merged. Section 7c also gives the text of a sheet sections 2 or 3 printed when a pass that reads it from 7c
(details, risers, network, plans) does not read that section; those lines take ids after section 8's.

Reading the drawing set (FINAL-K to FINAL-O). The principle, ruled: an undercount is the worst failure, so every
reduction (a page set aside, a copy read once, a sheet replaced) is made only where it is provably safe; otherwise
the pages are summed and the estimator is told, with both numbers where there are two.
- Copies (`catalogue.job.document_repeats`). A document is compared with another only when it has at least 3 sheet
  numbers and 80% of them are the other's, and only within one issue (the same revision label; an addendum or a
  duplicate file never: supersession decides between versions). It is a marked-up copy, read once from the
  original, only when ALL of `_not_a_copy` hold: its plans show no unit tag the original lacks (the superset is
  always the original); they repeat at least COPY_SHARED (3) of the original's unit tags and COPY_OVERLAP (0.6) of
  them; the plan titles on the shared numbers are the same; and it repeats COPY_TEXT (0.9) of the original's words
  on those sheets. Of two documents the same size the original is the one whose plans show more units, then the one
  with less text, then the one whose name does not say it is marked up. Any other such document is another set of
  drawings (`other_sets`, a second building issued with the same numbers): read and summed beside the original, and
  flagged "X.pdf repeats N sheets of Y.pdf but not their units / text / plan titles — read as another set of
  drawings and counted; check whether it is a marked-up copy". A copy's own count is still said on the counts line
  ("... read once, N; if it is another building, M; check").
- Versions (`revisions.supersede`). A sheet number in two or more documents: the latest title-block date governs;
  with no dates, a single addendum governs. When nothing orders them, every version is read and SUMMED, and the flag
  says so: "Sheet M-201 is in two documents with no dates to order them — check which governs; counted from
  Mech.pdf and Mech reissue.pdf, summed, for now" (REVIEW-FINAL7 F2).
- A reissue replaces only the sheet it is a version of (FINAL-O, REVIEW-FINAL8 H1). Of its number, only the pages
  whose title words (`title_words`: the number and the trade and plan words out, word order kept) are the reissue's
  own. A same-numbered sheet of another document with another title is another sheet: kept and read, with no flag
  (the match is provable). Base versions of the same title in two or more documents that are not one sheet's chain
  of issues (each revision table listing every row of the one before, all listed on the reissue's) are all kept,
  summed and flagged: "addendum M-101 may replace one of two M-101 sheets (Mech.pdf, Second Building.pdf): both
  counted; check". A reissue whose title matches no other sheet of its number replaces nothing: "addendum M-101 has
  another title than every other M-101 (Mech.pdf): both counted; check". Another set's sheet (`other_sets`) is a
  candidate too, so an addendum never replaces one building's sheet because the other's was set aside. The 3-number
  and 80% gate of the copy rule plays no part here.
- A reissue with fewer pages than its base (FINAL-O, REVIEW-FINAL8 H2). Pages printed again alike are one run,
  replaced whole or not at all. A reissue with as many runs as the base, or more, replaces them all; with fewer,
  each reissued page replaces the one base run its tags and note lines are most like, only when it is strictly the
  most like and like it at all. A page it does not match is kept and counted: "addendum reissues M-101 (1 page);
  base has 2 pages (Mech.pdf): unmatched page kept (p.2), counted; check"; a tie replaces nothing ("... no page
  matched best, every page kept and counted; check"). `Supersession.replaced` lists every replaced page, and
  `governing_pages` sets aside exactly those (document, page) pairs; every other page of the number is read.
- The label reader (`catalogue.tags.line_labels`, one reader for the inventory, the dossier and the copy and
  version tests). A label is a line that is the tag alone ("VAV-3", "(VAV-3)", "[VAV-3]", "VAV-3.", "(N) VAV-1",
  "VAV-1 TYP."), a bubble (a prefix alone over its number), a tag split over two lines ("VAV-" over "3"), or a line
  that STARTS with a tag, whatever words follow ("VAV-3 450 CFM", "EF-2 ON ROOF", "VAV-101 (OFFICE 101)"). On such
  a line every other tag counts too ("FCU-4 / FCU-5", "FCU-4&FCU-5", "VAV-1, VAV-2", "/", "&", "+", "," and ";"
  are joiners), and a THRU range counts its members between its ends ("VAV-1 THRU VAV-5", "VAV-1 THRU 5"), at most
  RANGE_SPAN (200). Never a label: a tag after a reference word (TO, FROM, SEE, PER, BY, SERVING, SERVES, SERVED,
  FEEDS, FEED, FEEDING, CONNECT, CONNECTS, CONNECTED, VIA, FOR, OF, WITH, AS, REFER, SIMILAR, SAME: "AHU-1 SUPPLY
  TO VAV-3" labels AHU-1 only), a line that does not start with a tag ("TO VAV-3"), and any line of more than
  NOTE_WORDS (12) words (a note).
- A stated count after a tag is that many places (FINAL-O, REVIEW-FINAL8 H3, ruled): "CUH-A (TYP. OF 4)", "CUH-A
  TYP OF 4", "CUH-A x4", "CUH-A (4)", "CUH-A 4 PLACES" are 4 labels of CUH-A on that sheet, up to STATED_MOST (50).
  The line must be the tag and the count only. A count over 50, zero, or not a number ("TYP. OF FOUR") is one
  place, and the counts line's reading notes say so ("CUH-A on M-101 reads 'CUH-A (TYP. OF 60)': the count beside
  it is not read (over 50, or not a number), counted as one place; check", `unread_counts`). A unit's tag so
  labelled ("VAV-1 x2") is still counted once on its plan by the one counting rule, with the "labelled N times"
  note.
- The backstop (`plan_labels`, REVIEW-FINAL7 F4). On a counted plan, a unit's tag the sheet names anywhere (in a
  note too) and labels nowhere counts once there, so a unit shown on a plan is never lost however it is written. A
  type's tag counts only where it is labelled. The labels alone (never the backstop) are the plan groups' evidence.

### Workstream 5 — `bms.ai`
```
class NoAnswer(Exception): reason: str, waiting: bool
class Transport(Protocol):
    waiting: int; last_error: str | None
    ask(kind, name, instructions, system_prompt, prompt, schema, extra=None, images=()) -> dict   # raises NoAnswer
class ChatTransport:  __init__(cache_dir: Path, job: str, handoff_dir: Path | None = None)
class ApiTransport:   __init__(cache_dir: Path, model: str | None = None, client=None)
WRITE_SYSTEM = "write_system"; QC_JOB = "qc_job"; STEPS = ("write", "revise"); CHAT_MODEL = "claude (chat)"
evidence_for(system: System, dossier: Dossier) -> str
evidence_index(dossier: Dossier) -> dict[str, str]
write_system(system: System, evidence: str, playbook: Playbook, transport: Transport, *, tags: Sequence[str] = (), ids: Sequence[str] = (), sheets: Sequence[str] = (), source_sheets: Sequence[str] = ()) -> System
qc_job(job: Job, evidence_index: Mapping[str, str], playbook: Playbook, transport: Transport) -> list[Finding]
revise_system(system: System, findings: Sequence[Finding], evidence: str, playbook: Playbook, transport, *, tags: Sequence[str] = (), ids: Sequence[str] = (), sheets: Sequence[str] = (), source_sheets: Sequence[str] = ()) -> System
rewrite_for_count(system: System, evidence: str, playbook: Playbook, transport: Transport, *, tags: Sequence[str] = (), ids: Sequence[str] = (), sheets: Sequence[str] = (), source_sheets: Sequence[str] = ()) -> System
# rewrite_for_count: asked only when an estimator's decision changed a family count; the devices already written are named in the prompt by their words and kept (by content and id); a device decision never comes here
# tags (optional): every tag of the job (bms.citations.job_tags). A tag protects only the form it is written in (bms.citations.tag_tokens): "F1", "C2", "AHU-S1" (as S1) and a range "F1-F4" protect those tokens; "S-1", "EF-S-1" and "F-1 thru F-4" protect nothing, since their plain forms are issued ids of the job
# ids (optional): I, the source ids the intake refuses in client text; the run passes one set to every writer, the count rewrite and the revise: every id of the job (bms.citations.job_ids) plus every id each system's evidence cites. A tag (in its written form) and a sheet number in K are never refused. A source id in client text is detected and refused, never rewritten
# sheets (optional): K, the whole plan's sheet numbers (bms.citations.job_sheets: the wheres of the planner's refs, never a writer's device refs and, since FINAL-J, never the ledger sources' wheres); the run works it out per call from the job it writes into (a decision can take planner refs out) and passes it to every writer, the count rewrite and the revise, so intake, validator and render agree on a sheet another system's where names. A K sheet is a sheet wherever it stands
# source_sheets (optional, FINAL-J): the job's source sheets (Job.source_sheets, the ledger sources' wheres); the run passes the job's to every writer, the count rewrite and the revise beside K. One is a known sheet in a where (anywhere in it) and in client text right after a sheet word ("per sheet S201", "sheets S201 and S202"); bare in client text ("Valves per S201.") an issued one is refused, as the validator (must_fix) and the renderer (cut) read it: `SourceIds.of(ids, tags, sheets, *, source_sheets=())`, `SourceIds.of_job` reads Job.source_sheets; client text goes through `scan` / `refusal` / `without_issued`, a where through `where_issued` / `sheet` / `place`, the renderer's quantity note (made of places) through `without_issued(text, place=True)`
```
Chat hand-off (unchanged from the old Judge so `tools/run_job.py` and the `/run-job` skill drive it):
request `<cache>/judge-chat/requests/<key>.json` with fields `key`, `kind`, `system` (the system name, or "QC"),
`job` (= `dossier.job_name`), `system_prompt` (Playbook rules text + blank line + step instructions), `prompt`,
the extras (`step`, `plan_key`, `images`), `schema`, `answer_file` (`<cache>/judge-chat/answers/<key>.json`);
`key = estimator.writing.judge._key(CHAT_MODEL, prompt, system_prompt)`; on a usable answer the answer is cached
in `<cache>/judge/<key>.json` as `{"version": 1, "kind", "model", "answer"}` and the request file is deleted.
Kinds: `write_system` (write, count rewrite and revise, so `/run-job` dispatches them to the writer model) and
`qc_job`. The `step` extra is `"write"`, `"decide"` (the count rewrite, `rewrite_for_count`) or `"revise"` on a
`write_system` request, and `"qc"` on a `qc_job` request (`STEPS` still lists only write and revise). A request whose
earlier answer was refused also carries `previous_problem`.
Answer freshness: an answer file counts only when it is newer than its request file and newer than the answer last
refused for that request; an older file is not read again (it would burn an attempt).
Old requests: a new run parks this job's waiting requests in `requests/old/`; a request the run writes again
unchanged goes back where it was (same file, same mtime), and a cached answer removes both copies.
Refusals: an answer a step refuses is dropped from the cache and its request written again with the reason. After
`max_attempts` refusals of one request (`.claude/run-job.json`, else 3) the run stops with a plain "Stopped:" message
naming the request; the counter is `<cache>/judge/attempts/<digest>.json`, one per question (the digest covers the
model, the step's instructions, the Playbook rules text, the schema and the prompt, so a changed Playbook, new
evidence or, in API mode, another model starts a new count; in chat mode the key always uses the one chat model, so
the same question is asked again with the reason it was refused, up to `max_attempts`). In chat mode, a newer answer file for a stopped request gets a fresh
set of attempts on the next run. The API transport reads the saved count first and, at the cap, stops without
calling the API.
`tools/run_job.py check` already accepts a System answer (Phase 0 changed its main-list check). API mode: the
Playbook rules as the first system block with `cache_control: {"type": "ephemeral"}`, streamed, structured output.
The skeleton fields of a System (key, name, shape, control, families, sequence_refs, alternate, serves) always win over the
answer's. Workstream 5 may also edit `tools/run_job.py` and `.claude/skills/run-job/SKILL.md` if the hand-off needs
it (e.g. naming a revise request), keeping the old app working.

### Workstream 6 — `bms.counts`
`count_tags(image_path: Path, tag_pattern: str) -> CountResult` — `CountResult(value: int | None, boxes:
tuple[Box])`, `Box(x, y, width, height, text)`; never raises on an unreadable picture.
`cross_check(job: Job, catalogue: Catalogue, cache: Path) -> Job` — adds a differing vision count to the family's
`Count.others` (Ref: picture id, "counted on the sheet picture", the sheet), keeps the highest as `value`, never
lowers a count. The app ships with text counts if vision is not ready: `cross_check` may then return `job` unchanged.
Patterns (2026-10-04): a family's patterns are built from its expanded tags (`expand_tags`: "SPXF-A, B, C" is three
tags), match lettered, numbered and dotted tags (TXF-B, EUH-2, CAC-1.5) and never a bare letter or number; the
located-text and vision counts use the same patterns. Each pattern's vision answer lists `tiles_examined`; one that
does not cover every tile sent is refused and asked again like a bad answer.

### Workstream 7 — `bms.review`, `tools/measure.py`
`review_page(job: Job, findings: Sequence[Finding], out_dir: Path) -> Path` (writes `out_dir/Review.html`, one
self-contained file; at most about 15 ranked questions; Accept / Change / Delete; decisions saved as
`decisions.json` = list of `Decision.to_dict()`); `load_decisions(out_dir: Path) -> list[Decision]` ([] when
missing; ModelError when malformed); `apply_decisions(job: Job, decisions: Sequence[Decision]) -> Job` (pure).
The decisions history: the page saves only its own answers, so the run keeps every save in
`out/decisions history.json` (`DECISIONS_HISTORY`), a list of `SavedDecision(decision, round, took_effect=False,
saved=None, settled=None, copies=None)`; `round` is the save it came from (1 for the first). `load_history(out_dir)`
([] when missing; ModelError naming the file when malformed); `save_history(out_dir, entries)` (written whole to a
temporary file and swapped in, or not at all; ModelError in plain words); `merge_decisions(history, saved, *,
job=None)` adds one decisions.json: earlier rounds stay unless the new save decides the same line (the new answer
wins); reading the same file again adds nothing; a delete or change of a line an earlier save changed is rebased
onto the line the writer wrote (change X to Y then delete Y is kept as delete X). `apply_seen(job, decisions,
copies)` is `apply_decisions` with `copies_seen(history)`, the number of copies of its line each delete saw;
`held_back` is true for a delete of a twin line whose number of copies changed, which is not applied.
`unhonored_decisions(before, decisions, after, *, copies=None) -> list[Finding]`: a must_fix "decision not honored"
for each decision the final job does not still show (lines recognised by content, not id), and a must_fix
"decision could not be applied" (same rule name) for a device decision whose line is in no job of this run, or a
held-back delete. `system_digest(job, key)` is what `settled` stores; `accept_families(job, decision)` is the set of
families an accept is about (a count change of any of them overrules the accept).
`measure(rendered_lines: Sequence[RenderedLine], final_proposal_path: Path) -> MeasureResult` —
`MeasureResult(matched: tuple[(LineMatch, LineMatch)], missed: tuple[LineMatch], extra: tuple[LineMatch])`,
`.share_matched`, `.summary()`; `LineMatch(system, device, verb, quantity)`. Held-out jobs only, never to tune.

### Workstream 1 — the Playbook content
Fills `playbook/rules.md` (the topics above; each rule a `###` short name; the practice rules of design §2.7 carry
over unchanged in meaning; replaces the two `<!-- sample -->` rules), `playbook/shapes.json` (one entry per Master
Template system type, shape only) and `playbook/wording.json` (confirms the `$draft` values, empties `$draft`), in
the formats of §3, so `load_playbook()` passes. Rule names it writes are what workstreams 3 and 5 cite: publish the
final list of rule names in the commit message.

## 6. The run — `bms.run`

Integration (2026-10-04): `cross_check` gets the run's transport and the run waits at "count" while vision tiles
are unanswered (the counts are part of the write prompts); `publish_proofs` copies the count proofs into
`out/count-proofs/` for the review page; the Evidence Package is `bms.evidence.write_evidence` (the old workbook
plus "Scope lines" and "Findings"); a QC must_fix the revise round left unchanged stays open; `tools/run_job.py`
runs `python -m bms` by default (`--app estimator` for the old app).

`estimate(job_folder: Path, out: Path, cache: Path, mode: "chat"|"api" = "chat") -> RunResult`, in order:
`catalogue_job` → `estimator.reading.job.read_job` → `job_header` → `build_dossier` → `Judge` +
`retire_requests` → `estimator.ledger.run.read_job` (saves `<quote> Ledger.json`; stops "waiting" at "read" when
incomplete) → `load_playbook` → `plan_job` → header set → `cross_check` → `write_system` per system (all asked,
then stop "waiting" at "write" if any NoAnswer; saves `<quote> Job.json`) → `load_history` + `load_decisions`
(a malformed file stops at "decisions") → `merge_decisions(job=)` → save the history → `apply_seen` (every
decision of the history) → `rewrite_for_count` for each system whose family counts the decisions changed, then the
standing accepts applied to it (waiting at "write") → `validate` → `qc_job` (waiting at "qc") → `revise_system`
for systems with must_fix findings (validate's and QC's; one round; the standing accepts applied again; waiting at
"revise") → the late decisions (device decisions made on the page's revised wording, which matched nothing the
writer wrote) applied to the revised job → history saved (`took_effect`) → `validate` → the "not honored", "could
not be applied" and "check this system" findings → `publish_proofs` → `review_page` → `render` → `write_evidence`
→ `_build` (proposal and price sheet) → history saved (`settled`). The run's first act writes `out/run state.json`
as "running" (again once the quote and job name are known); its last act replaces it with how the run ended
(`version`, `status`, `stage`, `waiting`, `messages`, `quote`, `job`, and `decisions`: how many decisions the
decisions history held when a run last saved it, 0 when none was saved yet, so a later run can tell a lost history
from a first save; the "running" state carries `version`, `status`, `quote`, `job` and `decisions`). Prints
`Wrote <path>` for every file.
`RunResult(status: "waiting"|"done", stage, waiting=0, job_file=None, findings=(), review=None, proposal=None,
price_sheet=None, evidence=None, messages=())`. `stage` is `read`, `count`, `write`, `decisions`, `qc`, `revise`
or `done`. `decisions` is a bad decisions file (or a history that cannot be saved): the run stops in words and
waits for no request. `render` appears only in the run state: a proposal that cannot be printed
(`bms.render.RenderError`) ends the run as stopped (status "waiting", nothing waiting, a "Stopped:" message) and
the error reaches the caller.
`python -m bms estimate` exits 0 when done, 2 when requests are waiting, and 1 when it stops with nothing to answer
(a refusal limit, or the `decisions` stage).
Two commands are called "status" and they mean different things. `tools/run_job.py status JOB --out OUT` *runs the
estimate* (`python -m bms estimate --mode chat` by default, `--app estimator` for the old app) and lists the
requests still waiting. `python -m bms status OUT [--cache C]` (`bms.status.check`) never runs anything, never
calls the AI and writes nothing: it reads the files the run already wrote (`run state.json`, the ledger, the job,
the chat requests and answers, the refusal counters, the review page and the documents) and says how far the run
got, with the same exit codes as `estimate` (0 done, 2 waiting, 1 stopped, not finished, no folder or no run).

## 7. Fixtures

- `tests/bms/fixtures/sample_job.json` — an invented job (no real job text): front end; five systems — `RTU`
  packaged rooftop units (integration trio slots, a shipped-loose duct smoke detector furnished by Unit Mfr., an
  assumption with its reason, a contradicted unit count in `others`), `EF` field exhaust fans (controller, a
  start/stop point, a linked damper actuator), `VRF` integration group (Indoor Unit, Condensing Unit, Branch
  Selector families; a vision count in `others`), `DH` duct heaters (sequence ref, an add alternate), `CUH` a
  sequence-only cabinet unit heater system (`Count.value` null, a quantity-flagged device); one exception; one
  question; refs on every device. Load with `Job.from_dict(json.load(...))`.
- `tests/bms/fixtures/sample_playbook/` — a minimal Playbook in the real format whose shapes (Rooftop Unit, Exhaust
  Fan, VRF System, Duct Heater, Unit Heater) cover every slot the fixture uses, and rules named: Every line cites
  this job, Higher count prints, One clarification per block, Every assumption says why, Packaged units,
  Shipped-loose devices, Dampers under their fan, Duct heaters in one place, VRF and split as one block.
  Workstreams test against it, not against `playbook/` (which workstream 1 is changing).

## 8. Files each workstream owns (and must not touch outside)

| # | Owns | Tests |
|---|---|---|
| 1 | `playbook/rules.md`, `playbook/shapes.json`, `playbook/wording.json` | — (the contract test loads them) |
| 2 | `src/bms/plan.py` (+ private helpers `src/bms/plan_*.py`) | `tests/bms/test_plan.py` |
| 3 | `src/bms/validate.py` (+ `src/bms/validate_*.py`) | `tests/bms/test_validate.py` |
| 4 | `src/bms/render.py` (+ `src/bms/render_*.py`) | `tests/bms/test_render.py` |
| 5 | `src/bms/ai.py` (+ `src/bms/ai_*.py`, `src/bms/prompts/`), `tools/run_job.py`, `.claude/skills/run-job/SKILL.md` | `tests/bms/test_ai.py` |
| 6 | `src/bms/counts.py` (+ `src/bms/counts_*.py`) | `tests/bms/test_counts.py` |
| 7 | `src/bms/review.py` (+ `src/bms/review_*.py`), `tools/measure.py` | `tests/bms/test_review.py`, `tests/bms/test_measure.py` |

A workstream keeps its public signatures exactly as above (the contract tests check them); private helpers are
free. New fixtures go under `tests/bms/fixtures/<workstream>/`, invented only.
