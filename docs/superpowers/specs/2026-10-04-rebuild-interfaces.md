# Estimator rebuild — the interfaces (Phase 0, 2026-10-04)

The contract every workstream builds against, with the design (`2026-10-04-rebuild-design.md`, §2–§5 binding).
Everything named here exists on branch `rebuild` as code; the stubs raise `NotImplementedError` and their docstrings
repeat the contract. `tests/bms/test_contracts.py` pins it: a workstream that needs a contract change asks the
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
| `src/bms/ai.py` | `write_system`, `qc_job`, `revise_system`, `evidence_for`, `evidence_index`, transports | workstream 5 |
| `src/bms/counts.py` | `count_tags`, `cross_check`, `CountResult`, `Box` | workstream 6 |
| `src/bms/review.py` | `review_page`, `load_decisions`, `apply_decisions` | workstream 7 |
| `tools/measure.py` | `measure`, `MeasureResult`, `LineMatch` | workstream 7 |
| `src/bms/run.py` | `estimate`, `RunResult` (the orchestration) | controller |
| `src/bms/__main__.py` | `python -m bms estimate JOB --out OUT [--cache C] [--mode chat\|api]` | controller |
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
                exceptions: tuple[ScopeException] = (), questions: tuple[str] = (), header: Header | None = None
                  job.system(key) -> System (KeyError); job.with_system(system) -> Job (replaced by key).
Finding:        rule: str, system_key: str, device_id: str | None, severity: Severity, what: str, fix: str
                  rule = a Playbook rule name (### heading); system_key "" for the front end / whole job.
Decision:       system_key: str, action: DecisionAction, device_id: str | None = None, family_name: str | None = None,
                device: Device | None = None, count: Count | None = None, finding_rule: str | None = None,
                reason: str = ""
```

`MODEL_CLASSES` lists them all.

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
`others_note` with `{value}` and `{others}`).

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
          clarifications: dict, header: dict, quantity: dict, draft: tuple[str]
Constants: TECH_HOUR_BASES, SLOT_KINDS, DEFAULT_ROOT
```

## 4. The old-app types consumed and produced (imported, never edited)

| Type / function | Module | Used by |
|---|---|---|
| `Catalogue` (job, pages, sheets, sections, bid, tags, flags, overview); `catalogue_job(root, cache_dir, workers, documents=None)` | `estimator.catalogue.job` | run, plan, counts |
| `JobReading`; `read_job(catalogue, page_opener=None, cache_dir=None, judge=None)` | `estimator.reading.job` | run |
| `Dossier` (job_name, text, images: tuple[DossierImage], sources: dict id→where, families, device_totals, counts, stats, sections); `build_dossier(catalogue, reading, cache_dir)`; `sheet_pictures(catalogue, cache_dir, keys, what)` | `estimator.writing.dossier` | run, plan, ai, counts |
| `Ledger` (sources, facts: dict[id, Fact], understanding, complete, stopped_at, job_name, refused; `of_kind`, `about`, `find`, `printed_count`, `to_dict`/`from_dict`/`load`); `Fact` (id, kind, subject, value, source_id, quote, stage, state, contradictions); `Contradiction`; `KINDS`; `where_short` | `estimator.ledger.facts` | plan |
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
write_system(system: System, evidence: str, playbook: Playbook, transport: Transport, *, tags: Sequence[str] = (), ids: Sequence[str] = ()) -> System
qc_job(job: Job, evidence_index: Mapping[str, str], playbook: Playbook, transport: Transport) -> list[Finding]
revise_system(system: System, findings: Sequence[Finding], evidence: str, playbook: Playbook, transport, *, tags: Sequence[str] = (), ids: Sequence[str] = ()) -> System
# tags (optional): every tag of the job (bms.citations.job_tags); the run passes it so the intake never refuses a tag shaped like a source id
# ids (optional): every source id of the job (bms.citations.job_ids); the run passes it so the intake refuses a client text that prints any of them
# (with the evidence's own ids). A source id in client text is detected and refused, never rewritten.
```
Chat hand-off (unchanged from the old Judge so `tools/run_job.py` and the `/run-job` skill drive it):
request `<cache>/judge-chat/requests/<key>.json` with fields `key`, `kind`, `system` (the system name, or "QC"),
`job` (= `dossier.job_name`), `system_prompt` (Playbook rules text + blank line + step instructions), `prompt`,
the extras (`step`, `plan_key`, `images`), `schema`, `answer_file` (`<cache>/judge-chat/answers/<key>.json`);
`key = estimator.writing.judge._key(CHAT_MODEL, prompt, system_prompt)`; on a usable answer the answer is cached
in `<cache>/judge/<key>.json` as `{"version": 1, "kind", "model", "answer"}` and the request file is deleted.
Kinds: `write_system` (write and revise, so `/run-job` dispatches them to the writer model) and `qc_job`.
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
then stop "waiting" at "write" if any NoAnswer; saves `<quote> Job.json`) → `apply_decisions(load_decisions(out))`
→ `validate` → `qc_job` (waiting at "qc") → `revise_system` for systems with must_fix findings (validate's and
QC's; one round; waiting at "revise") → `validate` → `review_page` → `render` → `write_evidence` → `_build`
(proposal and price sheet). Prints `Wrote <path>` for every file.
`RunResult(status: "waiting"|"done", stage, waiting=0, job_file=None, findings=(), review=None, proposal=None,
price_sheet=None, evidence=None, messages=())`. `python -m bms estimate` exits 0 when done, 2 when waiting.
`tools/run_job.py status` still calls `python -m estimator`; switching it to `python -m bms` is integration's.

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
