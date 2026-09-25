# Build Step 5 — Write Each System — Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development. Tasks 1–4 are independent: each adds only its own new files, and they run in parallel in their own worktrees. Task 5 puts them together. Task 6 is the command and the documents.

**Goal:** From a job folder to a draft proposal (.docx), a price sheet (.xlsx) and an Evidence Package, with nothing typed by hand. Each system is written the way the estimator's Master Template shows it:
- lines chosen from the job's own schedules, sequence and notes
- quantities from the inventory
- tech hours from the Master Template's rules
- a confidence score and a source on every line
- every uncertain choice on a review list

**Spec:** `docs/superpowers/specs/2026-09-24-estimator-ai-design.md` §10 (write each system), §11 (the review list) and §5 (the six guarantees).
- Only approved wording, which for now is the Master Template's own lines.
- Every number has a source.
- Nothing internal reaches the client.
- "No guessing": a line the tool can't decide is PENDING, and goes on the review list, never silently into the proposal.

**The estimator's teaching document:** `D:\Estimation Assistant\Brain\Master Template.docx` (read-only). A text dump is at `C:\Users\SIDDHA~1\AppData\Local\Temp\master.txt` (654 lines). What it holds:
- "Scope of Work Format": the line verbs.
  - Furnish and Install
  - Furnish
  - Furnish and Wire
  - Install and Wire … (Furnished by Unit Mfr.)
  - Install … (Furnished by Unit Mfr.)
  - Wire … (Furnished by Unit Mfr.)
  - "**" clarifications
- "Integration lines that go together (all 3)":
  - Furnish BMS Communication Wiring to <X> Factory Controls
  - Map Available Points Via Mfr. Provided BMS Interface
  - AME requires mfr. Rep to assist in integration, cost to be incurred by mech contractor
- **Two front-end variants:** New, and Extension of Existing. The facts for them are in spec 23 09 00 and similar sections.
- **A template per system**, each with its own rules and tech hours. Examples:
  - VAV: choose the space sensor type from the sequence; fan enable only if fan-powered; a discharge-air sensor if reheat; hot-water valve if the schedule has GPM; SCR or electric heat if the schedule has SCR or kW; 24 V by BMS contractor, a VAV transformer, or "coming with the unit". 4 h per hot-water reheat VAV, 3 h per cooling-only VAV.
  - The other systems: FCU, AHU (2 h per hardware point), packaged RTU/ERU (factory controls → the integration trio plus install-and-wire of shipped-loose sensors), exhaust fans (interlock, or DDC), gas detection (panel + sensors; always quoted), kitchen exhaust (interlocks, 40 h), FTR, EUH/CUH/UH, UV, air curtains, stair pressurization, fire/smoke dampers, split/VRF (2 h per indoor unit), CRAC, heat exchangers, chilled water, condenser water and boiler plants (2 h per hardware point), refrigerant monitoring, fuel oil, global points, and more.
- **The user's rule:**
  - Notes that clarify scope for the client ("**Start/Stop via Fire Alarm System", "**Refrigeration Leak Detection system is coming with the unit") are printed.
  - Estimator hints (tech hours, "look for GPM in schedule", "→" insights) are **never** printed.

**The AI:**
- Judgement, meaning which template lines a sequence of operation really calls for, goes to Claude through the Anthropic API when `ANTHROPIC_API_KEY` is set. The user is creating the key.
- **Without the key, the tool still runs.** The rule reading decides what rules can decide. The rest is PENDING, with the reason "judgement pending — no AI key set".
- The model is set in one place: default `claude-opus-5-5`, overridable with `ESTIMATOR_MODEL`.
- The API is never called in tests (use a fake).

## Global Constraints

- `D:\AME Estimation` and `D:\Estimation Assistant` are read-only.
- No job PDFs in the repo.
- Python 3.13, `.venv/Scripts/python.exe`. **One new package, `anthropic` (the official SDK).** Add it to `pyproject.toml` dependencies and install it into `.venv` with `.venv/Scripts/python.exe -m pip install anthropic`. Only Task 3 installs it.
- Never read, print or store the API key. Take it only from the environment, through the SDK's default.
- Every piece of text the user sees is plain English.
- Category words are the estimator's own: CONFIRMED, DISCREPANCY, ADDED, EXTRA, MISSING, ORPHANED, CONFLICT, EXISTING, ASSUMPTION and PENDING.
- Wording, rules, tech hours, groupings: JSON under `assets/`, never in code.
- The client documents come only from `estimator.scope.Job`, through the step 1 writers (`estimator.proposal.write`, `estimator.price_sheet.write`; see `_build` in `src/estimator/__main__.py`). Confidence, rule names and flags live only in the Evidence Package.
- Don't push. End commit messages with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Build, don't tune.** Run once over one or two Learn jobs as a smoke test; there's no scoring against past proposals.

## Existing interfaces (read, don't change, except in Task 5 and Task 6)

- `estimator.catalogue.job.catalogue_job(root, cache_dir) -> Catalogue`, with `.pages`, `.sheets`, `.sections`, `.tags`, `.bid`, `.overview` and `.job`.
  - `.overview` is the Spec overview: `topics` with status Found / Ruled out / Not found, `makers`, and the scope-review sections. See `src/estimator/catalogue/overview.py`.
- `estimator.reading.job.read_job(catalogue) -> JobReading`, from build step 4: schedules, inventory, totals, devices, legend, typicals, notes, versions, supersessions, backbone and flags. **Read `src/estimator/reading/*.py` for the real field names.**
- `estimator.scope`: `Job`, `Header`, `FrontEnd`, `Block`, `Item`, `Run` (pydantic, frozen). Read `src/estimator/scope.py` in full; its validators are binding.
- `estimator.price_sheet.price_book.PriceBook` and `price_key(text)`: the price book lookup used by the price sheet.

---

### Task 1: The Master Template as data

**Files:**
- Create `assets/system_templates.json`
- Create `src/estimator/writing/__init__.py` (empty; create only if missing) and `src/estimator/writing/templates.py`
- Test: `tests/test_templates.py`

**What:** turn every system in the Master Template into a JSON entry. **You read the Master Template and write the JSON.** This is the judgement part of the task. Keep the wording **exactly** as written; it is the approved wording. Fix only obvious typos, like a doubled space.

```json
{
  "about": "The estimator's Master Template as data: how each system looks, which line to pick when, and tech hours. Guidance, not a mandatory point list. Edit here, never in code.",
  "verbs": ["Furnish and Install", "Furnish", "Furnish and Wire", "Install and Wire", "Install", "Wire"],
  "integration_trio": ["Furnish BMS Communication Wiring to {what} Factory Controls", "Map Available Points Via Mfr. Provided BMS Interface", "AME requires mfr. Rep to assist in integration, cost to be incurred by mech contractor"],
  "systems": [
    {
      "name": "VAV / Fan VAV",
      "applies_to": {"prefixes": ["VAV", "FPB", "FPV", "FPT", "CAV"], "kinds": []},
      "header": "Qty ({n}) {kind} {tags}",
      "conditions": {
        "fan_powered": {"schedule": ["FAN POWERED", "FPB", "SERIES", "PARALLEL", "FAN HP", "FAN WATTS"], "prefix": ["FPB", "FPV", "FPT"]},
        "reheat_hot_water": {"schedule": ["GPM", "HW COIL", "HOT WATER"]},
        "reheat_electric_scr": {"schedule": ["SCR"], "sequence": ["SCR"]},
        "reheat_electric": {"schedule": ["KW", "ELECTRIC HEAT"], "sequence": ["electric heat"]},
        "sensor_t_h_co2": {"sequence": ["CO2", "humidity"]},
        "sensor_t_co2": {"sequence": ["CO2"]},
        "sensor_t_h": {"sequence": ["humidity"]},
        "power_24v_by_bms": {"sequence": ["24 V", "24V"], "notes": ["24V WIRING", "24 V WIRING BY BMS"]},
        "transformer_with_unit": {"schedule": ["TRANSFORMER"], "notes": ["TRANSFORMER"]}
      },
      "lines": [
        {"text": "Furnish DDC Controller to the Factory for Installation", "default": true, "quantity": "per_unit"},
        {"text": "Furnish and Install Space Temperature Sensor", "choice": "space_sensor", "default": true, "quantity": "per_unit"},
        {"text": "Furnish and Install Space Temperature / Humidity / CO2 Sensor", "choice": "space_sensor", "when": ["sensor_t_h_co2"], "quantity": "per_unit"},
        {"text": "Furnish Fan Enable", "when": ["fan_powered"], "quantity": "per_unit"}
      ],
      "client_notes": [],
      "hints": ["T, T/H, T/H/CO2, T/CO2 information is mostly in the sequence, sensor location can be on the plans", "Reheat VAV – Hot water; we include hot water control valve and actuator. Look for GPM in VAV schedule"],
      "tech_hours": {"per": "unit", "hours": 3, "when": [{"if": ["reheat_hot_water"], "hours": 4}]}
    }
  ]
}
```

**Field rules:**
- **`choice`:** lines sharing a choice group are alternatives ("OR" in the template). The one whose `when` conditions all hold wins, preferring the most specific (the most conditions). Otherwise the `default` wins.
- **`when` / `unless`:** condition names. Each condition says where to look:
  - `schedule`: words in the unit's schedule headers or cells
  - `sequence`: words in the passages about the system
  - `notes`: words in schedule notes or keynotes
  - `prefix`: tag prefixes
  - `spec_overview`: an overview item that must be Found, e.g. `"Graphics"`
- **`quantity`:**
  - `per_unit`: × the system's unit count
  - `one`: 1
  - `counted`: from the plan device counts, falling back to per_unit as an ASSUMPTION
  - `none`: a line with no quantity, which is a sub-note line
- **`client_notes`:** the "**" clarifications that are printed, only for systems where the template shows them.
- **`hints`:** everything else starting with "**" or "*", or containing "→". Never printed.
- **`tech_hours.per`:** `unit`, `hardware_point`, `indoor_unit`, `panel`, `fan` or `fixed`, with the hours and conditional overrides.
  - For `hardware_point`, a line counts as a hardware point when its verb is Furnish and Install / Furnish and Wire / Furnish (an I/O point). The integration trio and notes are not hardware points.
- **Plant and multi-equipment systems** (Chilled Water System, Condenser Water, Boiler, Heat Exchanger, Geothermal, Kitchen Exhaust, Gas Detection, Split System, VRF, Stair pressurization) have `applies_to` with several prefixes, and `"group": true`. They make one block listing several equipment headers, as the template shows ("Qty (2) ACCH… / Qty (3) CHGP… / Qty (1) ET…").
- **Tag prefixes** come from `assets/reading_lists/equipment.json`. A system for a prefix not in that file uses `kinds` instead, or adds the prefix. **Don't edit equipment.json.** List any missing prefixes in your report; Task 5 adds them.
- **The front end** is **not** in this file. Task 4 owns it.

**Loader:**

```python
@dataclass(frozen=True) class Condition: name: str; schedule: tuple[str,...]; sequence: tuple[str,...]; notes: tuple[str,...]; prefix: tuple[str,...]; spec_overview: tuple[str,...]
@dataclass(frozen=True) class TemplateLine: text: str; depth: int; when: tuple[str,...]; unless: tuple[str,...]; choice: str|None; default: bool; quantity: str; hardware_point: bool
@dataclass(frozen=True) class TechHours: per: str; hours: float; overrides: tuple[tuple[tuple[str,...], float], ...]
@dataclass(frozen=True) class SystemTemplate: name: str; prefixes: tuple[str,...]; kinds: tuple[str,...]; group: bool; header: str; conditions: dict[str, Condition]; lines: tuple[TemplateLine,...]; client_notes: tuple[str,...]; hints: tuple[str,...]; tech_hours: TechHours
def load_templates(path=...) -> tuple[SystemTemplate, ...]
def template_for(prefix: str, kind: str, templates) -> SystemTemplate | None
integration_trio(what: str) -> tuple[str, str, str]
```

**Tests:**
- Every system in the JSON loads.
- Every line text starts with one of the verbs, or is a trio line, or is a note.
- Choice groups have exactly one default.
- `template_for("VAV", …)` gives the VAV template.
- `template_for` gives None for an unknown prefix.
- Hints never appear in any line's text.

**Commit:** `feat: the Master Template as data — each system's lines, rules and tech hours`

### Task 2: Systems and their bundles

**Files:**
- Create `src/estimator/writing/systems.py` and `assets/system_groups.json`
- Test: `tests/test_systems.py`

**What:** group the step 4 inventory into systems, and gather each system's evidence in one place (design §10.1).

`system_groups.json` lists plant groupings by tag prefix, for example:
- `{"name": "Chilled Water System", "prefixes": ["CH", "CHLR", "ACCH", "CHWP", "CHGP", "PCHWP", "SCHWP", "ET", "AS", "CHF"]}`
- Condenser Water: CT, CWP, CTF
- Boiler Plant: B, BLR, HWP, BP
- Heat Exchanger: HX, PFHX
- Split System: SS, CU, IU, ACCU, AC, HP
- Kitchen Exhaust: KEF, DWEF, MAU, PCU
- Gas Detection: GDP

Anything not in a group is a system of its own family (one prefix).

**When a family joins a group:** only when it appears on the same schedule sheet, the same sequence passage, or the same riser or control-diagram sheet as another group member. Otherwise it stands alone. For example, MAU next to KEF is kitchen exhaust, while an MAU for a garage stands alone. When in doubt, it stands alone, with the flag "MAU-1 could belong to Kitchen Exhaust — check".

```python
@dataclass(frozen=True)
class Passage:
    where: str      # "23 09 93 SEQUENCE OF OPERATIONS, page 44"
    document: str
    page: int
    text: str       # the paragraph(s) mentioning the system, up to 3000 characters

@dataclass(frozen=True)
class Family:
    prefix: str
    kind: str
    tags: tuple[str, ...]
    quantity: int | None
    categories: dict[str, int]

@dataclass(frozen=True)
class SystemBundle:
    key: str                       # "VAV" or "Chilled Water System"
    name: str
    families: tuple[Family, ...]
    schedule_rows: tuple           # the step 4 schedule rows for these tags, with their schedule's title and sheet
    schedule_notes: tuple[str, ...]
    controls_by: tuple[str, ...]
    notes: tuple                   # step 4 Notes whose text names one of the tags or the kind
    passages: tuple[Passage, ...]  # from the backbone: sequence and points-list pages naming a tag, the prefix ("VAV"), or the kind name ("VARIABLE AIR VOLUME")
    devices: tuple                 # step 4 DeviceCounts on sheets where these tags appear
    sheets: tuple[str, ...]        # every sheet any of its tags is on
    flags: tuple[str, ...]

def build_bundles(catalogue, reading) -> list[SystemBundle]
```

**Rules:**
- **Passages** are paragraphs split on blank lines or numbered headings, keeping the one with the hit plus the next one. Keep at most 8 per system, preferring the sequence over the points list, and exact tags over the kind name.
- **EXISTING items** form their own "Existing …" bundle.
- **EXTRA and ORPHANED items** aren't in a bundle's quantity. They go into `flags` as "N more VAV tags on the drawings but not on the schedule (EXTRA) — not priced until confirmed".

**Tests:** hand-built inventory, schedules, notes and backbone pages covering:
- a chilled water group formed from a shared schedule sheet
- an MAU standing alone
- passage selection
- EXTRA kept out of the quantity

**Smoke:** 26-0352 (12 VAV and 1 EF bundles) and 26-0246. Report the bundle list.

**Commit:** `feat: group the equipment into systems and gather each system's evidence`

### Task 3: The AI judge (optional at run time)

**Files:**
- Create `src/estimator/writing/judge.py`
- Test: `tests/test_judge.py`
- Modify `pyproject.toml`: add `anthropic` to the dependencies.
- Install `anthropic` into `.venv`.

```python
@dataclass(frozen=True)
class Choice:
    line: str            # exactly one of the offered option texts
    include: bool
    quantity: int | None # when the evidence states a count, else None
    why: str             # one sentence, plain English
    quote: str           # the words from the evidence that decide it ("" if none)
    confidence: float    # 0–1

@dataclass(frozen=True)
class Judgement:
    choices: tuple[Choice, ...]
    client_notes: tuple[str, ...]   # clarifications the evidence supports, each starting "**"
    model: str

class Judge:
    def __init__(self, cache_dir: Path, model: str | None = None, client=None): ...
    @property
    def available(self) -> bool       # a client was given, or ANTHROPIC_API_KEY is set
    def judge(self, system: str, evidence: str, options: list[str], rules: list[str]) -> Judgement | None
```

**Behaviour:**
- **The prompt** is written in plain words. It says the model is an HVAC controls estimator at AME, and gives:
  - the system name
  - the rules: the template's conditions and hints, as text
  - the options: numbered template lines
  - the evidence: schedule rows, notes and passages, each with its place
- **The model must:**
  - answer every option with include true or false
  - quote the evidence that decides it
  - never invent a line not in the options
  - never invent a quantity the evidence doesn't state
  - say "no evidence" with confidence ≤ 0.5 when nothing decides
- **Output shape:** use tool use or structured output with a JSON schema so the answer parses. Validate it: unknown line texts are dropped, and the report says so.
- **The model** defaults to `claude-opus-5-5`, overridden by `ESTIMATOR_MODEL`. Use `max_tokens` 4000 and temperature 0.
- **Cache** by sha256 of (model + prompt) as JSON files in `cache_dir / "judge"`, written atomically. The same bundle never costs twice.
- **Failures:** an API error, a timeout, or no key → `None`, with the reason kept in `judge.last_error`, in plain words. Never raise into the pipeline.
- **Tests** use a fake client object with a `messages.create` method returning a canned tool-use response. They cover:
  - parse
  - an unknown line dropped
  - the cache hit (the fake is called once for two identical calls)
  - no key → `available` False and `judge()` → None
  - an API exception → None plus `last_error`
- **No test touches the network.**

**Commit:** `feat: an optional AI judge that picks template lines from the evidence, with quotes and a cache`

### Task 4: The front end, the header and "based on"

**Files:**
- Create `src/estimator/writing/front_end.py` and `assets/front_end.json`
- Test: `tests/test_front_end.py`

**`front_end.json`** holds the Master Template's two variants, verbatim:
- **New:**
  - Front End Web Enabled BMS System
  - Furnish Network Level Control Panel
  - Furnish PC Workstation
  - Furnish BMS Server
  - Furnish POT (Laptop or Tablet)
  - Furnish UPS – For workstation, server, network level control panel
  - Furnish 3-D Graphics
  - Furnish Necessary Training on New Controls
  - IT Infrastructure lines: Network Switches, Panels, Fiber – Ethernet
- **Extension of existing:**
  - Seamlessly Tie in to the Existing {system} BMS
  - Furnish Network Level Control Panel
  - Furnish 3-D Graphics to match existing
  - Furnish Necessary Training on New Controls
- **Warranty lines** from the template.

Each line has a condition over the Spec overview:
- the workstation needs the overview's "Operator workstation / front-end PC" Found
- the server needs "Server" Found
- UPS needs "UPS" Found
- the POT is included only if the text "laptop", "tablet" or "portable operator" is found
- graphics and training are defaults
- the IT infrastructure lines only when BACnet/IP is Found (not Ruled out) and the job doesn't say the network is by others or by the owner (the scope review's who-does-what)

When a server or switches are by the owner, add the line as a client note: "**BMS Server by Owner" / "**Network Switches by Owner", quoting the scope review.

```python
def front_end(catalogue) -> tuple[FrontEnd, list[str], list[Evidence]]   # FrontEnd model, flags, evidence per line
def job_header(catalogue, reading, today) -> tuple[Header, list[str]]
```

**Rules:**
- **Mode:** "extend-existing" when the overview's "Tie-in to an existing system" is Found. `existing_system_name` is taken from the quote (Honeywell / Niagara N4 / WEBs / Johnson Controls / Metasys, if named). Otherwise "the existing", flagged "Name the existing BMS". Otherwise the mode is "new-system".
- **Warranty lines** appear when the overview's services section finds a warranty, with the amount stated.
- **Header:**
  - `quote_number` = the job number from the folder name (`26-0352`)
  - `reference` = the rest of the folder name, or "PENDING — project name", flagged
  - `mep_engineer` = the most common engineering firm name in title blocks if readable, else "PENDING — MEP engineer", flagged
  - `based_on` = one line per discipline set, for example "M-001.00 thru M-701.00 Dated: 06/26/2026", from the sheets' numbers and the latest title-block revision date (step 4 `versions`)
  - `date` = today
- **Evidence** is a small dataclass defined here: `line`, `where`, `quote`, `status`. Task 5 reuses its shape.

**Tests:**
- new versus extension
- the server by owner
- the IT lines only with BACnet/IP Found
- header fields and "based on" from hand-built sheets and versions

**Commit:** `feat: the front end, the cover header and "based on" from the job's own documents`

### Task 5: Write each system

**Files:**
- Create `src/estimator/writing/write.py`
- Test: `tests/test_write_systems.py`
- May modify `assets/reading_lists/equipment.json` to add the prefixes Task 1 reported missing.

```python
@dataclass(frozen=True)
class ScopeLine:
    system: str
    text: str
    depth: int
    quantity: int | None
    tech_hours: float | None
    category: str        # CONFIRMED | ADDED | ASSUMPTION | PENDING | …
    confidence: float
    source: str          # "rule: reheat_hot_water (VAV schedule M-601, GPM column)" | "AI: quote …" | "default"
    evidence: str        # where + quote
    client: bool         # goes into the proposal

@dataclass(frozen=True)
class WrittenSystem:
    bundle_key: str
    block: Block          # estimator.scope.Block, the client view
    lines: tuple[ScopeLine, ...]
    review: tuple[str, ...]

def write_systems(catalogue, reading, bundles, templates, judge) -> list[WrittenSystem]
```

**Steps, per bundle:**
1. **Choose the template.** Use `template_for`, over the group or the family. No template → a PENDING block "No Master Template entry for <kind> — write this system by hand", with a review line.
2. **Rule reading.** Evaluate each condition against the bundle: schedule headers and cells, passages, notes, prefixes, and the Spec overview. A condition that holds is recorded with its evidence (where + the words).
3. **Choose lines:**
   - `when` all hold and no `unless` holds → include.
   - For a choice group, take the most specific winner, else the default.
   - **A line whose decision rests only on a default** is included with category ASSUMPTION and confidence 0.5, **only when it is the template's default line**.
   - Any other undecided line (it has a `when` that can't be checked because the evidence is missing) is PENDING and not printed.
   - **Factory controls:** when `controls_by` says "factory control package" or "controls by unit manufacturer", or the schedule says "factory mounted", the integration trio replaces the DDC-controller lines. The trio's `{what}` is the kind.
4. **AI judgement,** when `judge.available`:
   - Send the bundle evidence, the template's options (every line) and the rules (conditions + hints) to `judge.judge`.
   - AI choices with confidence ≥ 0.7 and a non-empty quote override a rule ASSUMPTION or PENDING; the category becomes CONFIRMED (a quote from the sequence) or ADDED (from drawings or notes).
   - When the AI disagrees with a rule decision that has evidence, **keep the rule's answer** and add a review line: "The rule and the AI disagree on <line> — <rule evidence> vs <AI quote>".
   - AI client notes go into the block as "**" notes only when they quote the evidence.
5. **Quantities:**
   - `per_unit` is the family quantity (scheduled count).
   - `counted` uses the device counts on the system's sheets, when the label maps to the line's device (Temperature sensor ↔ "Space Temperature Sensor", …, from a small map in `system_templates.json`). The category is CONFIRMED when counted, else per_unit as ASSUMPTION.
   - A quantity of `None` (PENDING) keeps the line off the price sheet and puts it on the review list.
   - The design's "never a silent 1" applies.
6. **Tech hours** come from `tech_hours`:
   - per unit × quantity, with the overrides by condition
   - `hardware_point`: 2 h × each included hardware-point line × its quantity
   - `indoor_unit`: × the indoor units in the group
   - `panel` / `fan`: × the count of those
   - Put the hours on the Block (`Block.tech_hours`). The price sheet reads it; check how step 1 used tech hours.
7. **The block:** header `Qty ({n}) {kind} {tags}` with a compact tag list ("VAV-21-01 thru 12"). Group systems list one header per family, stacked with `joined=True` as the template shows. Then the lines (the Items), then the client notes (a note Item, depth 1).
8. **Confidence** per line:
   - 0.9: counted, or an AI quote from the sequence
   - 0.8: a rule with schedule evidence
   - 0.7: AI from drawings or notes
   - 0.5: a default
   - 0: PENDING
   - The block's confidence is the lowest of its lines. It is in the Evidence Package only.

**Then:**

```python
def build_job(catalogue, reading, judge, today) -> tuple[Job, list[WrittenSystem], list[str]]
```

It combines `job_header`, `front_end` and the systems in a sensible order: front end; air systems (AHU, RTU, ERU, DOAS, MAU); terminal units (VAV, FPB, FCU, UV); fans; heating (FTR, UH, CUH); plants (chilled water, heating, condenser); split / VRF / CRAC; misc monitoring; then everything else. The order lives in `system_groups.json`.

**Tests:**
- A VAV bundle whose schedule has GPM, and a sequence saying "space temperature and CO2", gives:
  - DDC to factory
  - T/CO2 sensor (CONFIRMED by the rule, evidence the sequence)
  - DAT sensor
  - HW valve and actuator
  - 4 h × n
- A packaged RTU with "factory control package" gives the trio plus the install-and-wire lines.
- A fake judge overrides an ASSUMPTION, and a disagreement makes a review line.
- A missing template gives a PENDING block, not printed.
- `build_job` gives a `Job` that passes `check_fit`: import it from wherever `_build` imports it.

**Commit:** `feat: write each system from the Master Template — lines, quantities, tech hours, confidence and review`

### Task 6: The `estimate` command and the Evidence Package

**Files:**
- Modify `src/estimator/__main__.py`: a new command, `estimate JOB --out FOLDER [--workers N] [--no-ai]`.
  - It runs `catalogue_job`, `read_job`, `build_bundles`, the `Judge` (unless `--no-ai`, or it isn't available) and `build_job`.
  - It writes the proposal and price sheet with `_build`.
  - It writes the Evidence Package with the new tabs.
  - It prints a summary: systems written, lines, PENDING count, review count, whether the AI was used and how many calls it made (cached calls counted apart).
- Modify `src/estimator/evidence/workbook.py`. New tabs right after "Bid check":
  - **"Review list":** first, every PENDING, ASSUMPTION, DISCREPANCY, EXTRA, rule/AI disagreement and front-end or header flag, each with the system, what to decide, the evidence and the suggested action. Then the step 3 and 4 flags.
  - **"Scope lines":** every ScopeLine, with system, text, quantity, tech hours, category, confidence, source, evidence and "In the proposal?".
  - Keep the existing tabs.
- Tests: `tests/test_estimate.py`. Run end to end on a synthetic job folder built with `tests/pdfs.py`: a schedule sheet with 3 VAVs and GPM, a plan with the tags, and a spec page with "SECTION 23 09 93 SEQUENCE OF OPERATIONS … space temperature and CO2 …". Use `--no-ai`. Check:
  - the proposal and price sheet exist
  - the proposal text has "Qty (3)" and "Discharge Air Temperature Sensor"
  - the Evidence Package has "Review list" and "Scope lines"
  - nothing internal ("confidence", "ASSUMPTION", "rule:") is in the proposal text
- **Smoke:** `estimate` on 26-0352 and 26-0246 with `--no-ai`, writing to `out/estimate/<job>/`. Report the block headers and PENDING counts. No scoring.
- **Commit:** `feat: the estimate command writes the proposal, price sheet and Evidence Package from a job folder`
