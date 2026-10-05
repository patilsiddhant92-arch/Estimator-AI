# Whole-Job Writing — Implementation Plan (the inversion)

> **For agentic workers:** three helpers build parts A, B and C in parallel, each in its own worktree from `step-5-follow-ups`. The interfaces below are binding, so each part can be built and tested against fakes of the others. The controller merges and wires.

**Why.** The first end-to-end test (26-0478, 26-0193) matched 13 of 47 and 13 of 49 of the estimator's scope lines. The cause was the order of decision, not the reading: the system list was built from equipment tags, quantities from schedule rows, and scope lines from pattern rules, with the AI only filling gaps from the Master Template's menu. The estimator does the reverse: reads the whole sequence of operation, the schedules and the plans, then writes every system. The user chose to invert the pipeline (2026-09-26).

**The new order:**
1. **Deterministic reading gathers and checks; it never decides scope.** What exists today (catalogue + step 4 reading + Spec overview) becomes a **dossier**: everything controls-relevant in the job, in one structured document.
2. **The judge reads the whole dossier in one pass** and writes the system list with quantities, then **one pass per system** for the scope lines, in house style, quoting the source of every line and number.
3. **Deterministic cross-checks** then verify every quantity against the counts, every line for its quote, the house style, and the Master Template as a checklist. Disagreements go on the review list. Nothing is invented.

**Spec:** `docs/superpowers/specs/2026-09-24-estimator-ai-design.md` §9.1 (recall deterministic, judgement not), §10, §11, §5 (the six guarantees). The guarantees still hold: one list two documents; every number has a source; no guessing; template owns boilerplate; nothing internal reaches the client; approved wording (house style + phrasing bank).

## Global Constraints

- `D:\Estimation Assistant` and `D:\AME Estimation` are read-only. Never touch `D:\Estimator AI\out\test-inputs*` or the user's uploaded job folders. **Never open** the estimator's proposals or markups for 26-0478 / 26-0193 (`out\26-0478…\3. Proposal`, `…\2. Takeoffs`, `D:\AME Estimation\2026\26-0193…\*.docx`, marked PDFs): they are the answer key.
- Python 3.13, `.venv/Scripts/python.exe`. Run tests with `PYTHONPATH` set to your worktree's `src` and the venv at `D:\Estimator AI\.venv\Scripts\python.exe`; if Bash refuses the quoted path, use PowerShell: `$env:PYTHONPATH="$PWD\src"; & "D:\Estimator AI\.venv\Scripts\python.exe" -m pytest -q`.
- No network in tests: fake judges and fake clients only.
- Never read, print or store an API key.
- Words, rules and prompts live in `assets/` JSON where they are data; prompts may live in code as constants.
- Plain English in everything the user sees. Category words are the estimator's own (CONFIRMED, ADDED, DISCREPANCY, ASSUMPTION, PENDING, EXTRA, ORPHANED, EXISTING).
- Tests first. One commit per numbered item, ending `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. Never dispatch subagents. Never push.
- Test inputs and cache for smoke runs: `D:\Estimator AI\out\test-inputs\26-0478, Example HS - New Gym Bldg`, `D:\Estimator AI\out\test-inputs-clean\26-0193, <project folder>`, cache `D:\Estimator AI\out\test\.cache`. Write outputs under your worktree's `out\`.

## Existing pieces (read, reuse, don't rewrite)

- `estimator.catalogue.job.catalogue_job(root, cache_dir) -> Catalogue` (`.pages`, `.sheets`, `.sections`, `.tags`, `.bid`, `.overview`, `.job`).
- `estimator.reading.job.read_job(catalogue, cache_dir=...) -> JobReading` (schedules, inventory, totals, devices, legend, typicals, notes, versions, supersessions, backbone, flags). Fields: `Schedule(document, page, sheet, title, headers, rows, type_only, notes, controls_by, from_text)`, `ScheduleRow(tag, cells, manufacturer, model, existing, kind)`, `DeviceCount(sheet, document, page, device, label, count, floors, total, in_legend)`, `Backbone(what, where, document, first_page, last_page, kind, duplicate_of)`, `Note(sheet, document, page, block, number, text, controls, who)`, `InventoryItem(tag, kind, category, quantity, schedule, seen_on, reason, action, types)`, `FamilyTotal(kind, prefix, scheduled, tags, flags)`.
- `estimator.writing.judge.Judge` (modes api / chat, cache, hand-off; `judge()`, `compose()`; request kinds "choose" and "compose"). Part B adds two kinds.
- `estimator.writing.style.load_house_style()` (`HouseStyle.check_line(text, depth)`, `check_note`, `prompt_text()`), `estimator.writing.phrasing` (the bank: 160 blocks from the Learn proposals; `examples_for(...)`), `estimator.writing.templates.load_templates()` (33 Master Template systems, `nearest_templates`).
- `estimator.writing.front_end`: `front_end(catalogue, bid_check=None) -> (FrontEnd, flags, evidence)`, `job_header(catalogue, reading, today)`, `global_points_block(catalogue, templates=...) -> (Block|None, evidence)`, `extended_warranty_block(catalogue) -> (Block|None, flags, evidence)`.
- `estimator.writing.write`: `ScopeLine`, `ReviewItem`, `WrittenSystem`, `tag_list(tags)`, `build_job(...)` (the old path; keep it working as `--method rules`).
- `estimator.scope`: `Job`, `Block`, `Item`, `Run`, `FrontEnd`, `Header`, `Alternate` (read the validators).
- `estimator.proposal.write` / `estimator.price_sheet.write` / `_build` in `__main__.py`; `estimator.evidence.workbook.write_evidence(path, catalogue, reading=None, ...)`.

---

## Part A — The dossier (`src/estimator/writing/dossier.py`, `tests/test_dossier.py`)

One function: `build_dossier(catalogue, reading, cache_dir) -> Dossier`.

```python
@dataclass(frozen=True)
class DossierImage:
    path: str            # absolute PNG path in cache_dir / "dossier-images"
    what: str            # "H601 HVAC SCHEDULES — picture schedule" | "M-701.00 schedule, table unreadable"
    sheet: str | None
    document: str
    page: int

@dataclass(frozen=True)
class Dossier:
    job_name: str
    text: str                       # the whole dossier as one plain-text document with numbered sections (below)
    images: tuple[DossierImage, ...]
    sources: dict[str, str]         # source id -> "where" string, e.g. "S3" -> "23 09 93 SEQUENCE OF OPERATIONS FOR HVAC, Specs.pdf page 44"
    families: tuple                 # reading.totals as-is
    device_totals: dict[str, int]   # label -> total across controls-discipline plan sheets, floors applied
    counts: dict[str, dict]         # tag family prefix -> {"schedule_rows": n, "quantity_column": n|None, "plan_placements": n, "riser": n|None, "distinct_tags": n}
    stats: dict[str, int]           # characters per section, page counts, image count
```

**`text` layout.** Numbered sections with **source ids** on every paragraph or row so the judge can cite them (`[S12]`). Keep each id short and unique. Sections:
1. **Job** — name, documents (kind, pages, date), addenda, the Spec overview's controls platform line, protocols found/ruled out, who-does-what lines, standard exclusions the job asks for, services found (training, warranty term, commissioning), special systems.
2. **Sequence of operation** — the **full text** of every backbone page marked "Sequence of operation" (reading.backbone), duplicates removed, in document order, with `[S..]` per paragraph and a page marker per page. Squash whitespace; keep numbering and lettered headings.
3. **Points lists** — full text of backbone pages marked "Points list", same treatment.
4. **Schedules** — every `Schedule`: title, sheet, page, source id; headers; rows as `tag | cell | cell…` with `existing` marked; notes; controls_by. Picture schedules and `from_text` schedules also produce a `DossierImage` (render the sheet's picture regions at 200 dpi, or the whole sheet at 150 dpi when the sheet is one picture; write atomically; reuse if present), and the text says "see image I3".
5. **Equipment counts** — per family: prefix, kind, schedule rows, QUANTITY-column total if any, distinct tags, plan placements (from `catalogue.tags` occurrences on plan sheets of controls disciplines, times the sheet's floor multiplier from `reading.typicals` / repeated pages), riser count if any sheet titled RISER carries the tags, and the tags compacted with `tag_list`. This is what `counts` holds too.
6. **Devices on plans** — `device_totals` per label with sheet breakdown.
7. **Notes** — every controls-relevant `Note` (block, number, text, who), by sheet.
8. **Controls spec highlights** — the controls spec sections' text **limited to** these headings when present: front end / workstation / server, warranty, training, commissioning, integration/gateways, wiring/conduit responsibility, submittals. Cap 12,000 characters; say what was cut.

- **Floor multiplier:** a plan sheet number repeated on N pages in one document, or a typical title with a floor range → N (or the range length). One rule, in this module, reused by the counts.
- **Size:** report `stats`. If the sequence text exceeds 150,000 characters, keep it whole but flag; Part B splits passes.
- **Tests:** synthetic catalogue/reading objects (see `tests/test_write_systems.py` and `tests/test_systems.py` for how they build them): every section appears; source ids are unique and resolve; a picture schedule yields an image; the floor multiplier applies to placements; a QUANTITY column is summed; duplicate sequence pages appear once.
- **Smoke:** build the dossier for both test jobs; report `stats` and the counts for the three biggest families.

Commit: `feat: the job dossier — everything controls-relevant in one document, every paragraph citable`

## Part B — The whole-job judge (`src/estimator/writing/whole_job.py`, additive changes to `judge.py`, `tests/test_whole_job.py`)

Two new request kinds, through the existing `Judge` cache and chat/API hand-off (add methods and schema functions; don't change existing ones):

**B1. `judge.plan_job(dossier_text, images, checklist, style_text) -> JobPlan | None`** — one pass over the whole dossier.

```python
@dataclass(frozen=True)
class PlannedSystem:
    key: str                  # short unique key the judge chooses, e.g. "RTU-1-3"
    header: str               # house form without the Qty: "Rooftop Unit RTU-1 thru 3"
    kind: str
    tags: tuple[str, ...]
    quantity: int | None      # only when a source states it
    quantity_source: str      # "[S41]" | "" ; the id of the row/count/paragraph
    quantity_quote: str       # the words stating it, exact
    sequence_sources: tuple[str, ...]   # ids of the sequence paragraphs about this system
    schedule_sources: tuple[str, ...]
    group: str                # "" or a plant/group name when several headers share one block
    alternate: str            # "" | "add" | "deduct" — when the documents say it's an alternate
    exception: str            # "" or the one-line exception text in capitals, when the unit needs no BMS work (integral thermostat, manufacturer switch)
    why: str

@dataclass(frozen=True)
class JobPlan:
    systems: tuple[PlannedSystem, ...]
    front_end: dict           # {"mode": "new-system"|"extend-existing", "existing_name": str, "lines": [...], "notes": [...], "sources": [...]}
    unresolved: tuple[str, ...]   # plain questions for the estimator
    model: str
```

**The prompt** says: you are an AME controls estimator; read the whole dossier as you would a bid set; list **every** system the sequence of operation, the schedules or the plans give controls scope to, including ones with no tag (fire pump, generator, CO panel, heat tracing, destratification fans); split a family where the sequence treats a subset differently; a type row with a QUANTITY column, or a tag placed many times on the plans, is that many units, never one; mark units run by an integral thermostat or a manufacturer switch as exceptions; mark in-apartment equipment the documents price separately as an alternate only when the documents say so; cite source ids for everything; never invent a number — leave quantity null and say why. Include the **checklist**: the Master Template system names with one line each on when they apply (from `system_templates.json` `applies_to` and `hints`), and the house style.

**Images:** in API mode, attach each `DossierImage` as an image block with its caption; in chat mode the request file lists the paths and the chat helper opens them.

**B2. `judge.write_system(system: PlannedSystem, evidence_text, images, options, examples, style_text) -> WrittenScope | None`** — one pass per planned system.

- `evidence_text` = the dossier paragraphs whose ids the plan cited, plus the family's counts and device totals (Part C assembles it).
- `options` = the nearest Master Template's lines as a checklist ("usually present; say why if you leave it out"), never a closed menu.
- `examples` = phrasing-bank blocks for the same prefix/kind (up to 4).
- Answer: `WrittenScope(lines: tuple[WrittenLine,...], client_notes, tech_hours_hint, review_notes, model)`; `WrittenLine(text, depth, quantity, quote, source_id, why, confidence)`. Reuse `judge.py`'s existing `WrittenLine`/validation helpers if they fit; else define here and validate with `HouseStyle.check_line(text, depth)`.
- **Splitting a huge dossier:** if `dossier.text` is over 150,000 characters, `plan_job` runs per document group (sequence + schedules first, then the rest) and merges by `key`; say so in `unresolved`.

**Chat request files** for both kinds carry `"kind": "plan_job" | "write_system"`, the schema, the prompt and image paths, exactly as the existing kinds do.

**Tests:** fake client returning canned JSON for each kind; schema validation drops a system with a quantity but no quote; images listed in the chat request; cache hit; unknown fields ignored; a huge dossier splits into two plan requests.

Commits: `feat: the whole-job judge — plan every system from the dossier` and `feat: the judge writes each planned system's scope in house style`

## Part C — Cross-checks, assembly, command and Evidence Package (`src/estimator/writing/assemble.py`, `__main__.py`, `evidence/workbook.py`, `tests/test_assemble.py`, `tests/test_estimate.py`)

Build against the interfaces above with fakes (a `FakeJudge` whose `plan_job` / `write_system` return canned objects; a hand-built `Dossier`).

**C1. `check_plan(plan, dossier, reading) -> list[ReviewItem]` and `check_scope(system, scope, dossier) -> (kept_lines, review)`:**
- A planned quantity is **CONFIRMED** when it equals one of `dossier.counts[prefix]` values (quantity column, distinct tags, plan placements, riser) or the quoted source states it; **DISCREPANCY** (with both numbers) when the counts disagree with it; **PENDING** when null. Never change the AI's number silently; the review line carries the alternatives.
- A family in `dossier.families` that no planned system covers → review "Equipment on the drawings the plan didn't write: …" (not silently added).
- A planned system with no source ids → review, still written but confidence 0.4.
- Each written line needs a quote that appears in the dossier text (whitespace-insensitive, ≥ 60% of its words in order): else confidence capped 0.5 and a review line. Style check with `HouseStyle`. Lines with "$", "hour", "confidence", category words → dropped and listed.
- Master Template checklist diff: template lines for that kind that the scope leaves out → one review line per system listing them ("usually present; the AI left out: …").
- Tech hours: from the nearest template's rule when it fits the kind, else the judge's hint marked ASSUMPTION, else None with a review line. Never invented.

**C2. `assemble_job(catalogue, reading, dossier, plan, scopes, today, templates) -> (Job, list[WrittenSystem], list[ReviewItem])`:**
- Header: `job_header`. Front end: `front_end(catalogue, bid_check=catalogue.bid)`, reconciled with `plan.front_end` (the plan may add a line only with a source; a disagreement → review, the deterministic answer kept). Then `global_points_block` and `extended_warranty_block`; when the warranty block exists, drop the front end's warranty-extension lines.
- Blocks in the plan's order grouped by `group`; headers `Qty ({n}) {header}` with `tag_list`; a PENDING quantity prints as `Qty (?)` **only in the Evidence Package** — such a block is left out of the proposal and listed on the review list (no guessing).
- Exceptions → `Job.named_exceptions`; alternates → `Job.add_alternates` / `deduct_alternates` with the same blocks.
- `WrittenSystem`/`ScopeLine` filled as the old path does, with `source` = "AI (whole job) [S12]" and the confidence.
- The `Job` must pass `check_fit`.

**C3. The command and the workbook:**
- `estimate JOB --out … --ai chat|api|off --method whole-job|rules` (default `whole-job`). With `off`, the whole-job method writes the dossier and the Evidence Package, prints "the AI writes the scope; run with --ai chat or api", and writes no proposal.
- Steps: catalogue → read_job → build_dossier → plan_job (chat: stop with "N requests waiting" if unanswered) → write_system per planned system (same) → checks → assemble → `_build` → `write_evidence`.
- Save `dossier.text` to `OUT/<job> Dossier.txt` for the estimator.
- Evidence Package: keep all tabs; the **Review list** and **Scope lines** tabs take the new items; add a **Plan** tab: every planned system with quantity, source, quote, the cross-check numbers and its category.
- Summary lines: systems planned / written / pending, lines, review count, AI calls and cached.

**Tests:** `check_plan` categories (CONFIRMED / DISCREPANCY / PENDING); an uncovered family reviewed; quote check caps confidence; checklist diff; assembly passes `check_fit`; exception and alternate placement; `estimate --method whole-job --ai off` writes the dossier and Evidence Package and no proposal; with a FakeJudge end to end on the synthetic job in `tests/test_estimate.py` → proposal has the planned blocks and nothing internal (extend the existing INTERNAL check).

Commits: `feat: cross-check the AI's plan and scope against the counts and the house style`, `feat: assemble the job from the whole-job plan`, `feat: estimate --method whole-job writes the dossier, plan and proposal`

## After the merge (controller)

Run both test jobs with `--method whole-job --ai chat`, answer the plan requests and the per-system requests in the chat (helpers, evidence-only, images opened by eye), run again, then the read-only comparison against the estimator's work. Same scoring as the first test.
