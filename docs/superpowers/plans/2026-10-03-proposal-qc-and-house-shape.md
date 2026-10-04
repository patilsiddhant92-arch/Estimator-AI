# Proposal QC, the House Shape and Damper Placement — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The proposal reads like an AME proposal: every block is written into its Master Template frame with the right ownership verbs, the packaged-unit doctrine is enforced, dampers land under their fans, an independent QC pass lists what is still wrong, and a job can be run from any session with one command.

**Architecture:** The GEM is rewritten in plain language (v4) with the estimator's practice rules folded in. A job brief built from the ledger is shared by every write request and the QC request. The writer's prompt puts the template first; a new house check in code refuses lines the doctrine forbids. The plans and risers passes get sheet pictures and record damper-to-fan links; the planned systems take linked dampers. A `qc_job` question kind asks one independent pass over the whole draft; its findings become review rows and a tab. A repo skill, `/run-job`, drives chat mode to completion with subagents on configured models.

**Tech Stack:** Python 3.13, dataclasses, pytest 9.1.1, openpyxl, pymupdf. Run everything with `.venv/Scripts/python.exe`.

**Spec:** `docs/superpowers/specs/2026-10-03-proposal-qc-and-house-shape-design.md` (§8 holds the estimator's binding answers; `assets/gem/ame_practice.txt` holds the same rules in the estimator's words).

## Global Constraints

- Plain language everywhere the estimator or the client reads: prompts, refusals, review rows, notes, tab names. No emoji or coloured glyphs anywhere in the new GEM or the outputs. No invented codes beyond the existing ids (`S12`, `Q7`, `I2`, `F17`).
- The estimator's answers (spec §8) are binding: factory-installed devices are never lines; "Furnish <point>" lines only on AME-DDC systems; other trades in brackets as given; sequence-only systems print in the base bid as "Qty (##)" with "*Quantity per plumbing drawings"; no invented alternates; UUKL controls written in scope; 4 hours per integration-only system with no template rule; one "*" clarification per block.
- A line is refused, never silently dropped: every refusal is listed in `WrittenScope.refused` in plain words and quotes the rule or the document.
- The QC pass never changes the proposal; it lists findings.
- Nothing under `assets/templates/`, the readers, the catalogue, the dossier's source ids, the proposal or price sheet writers changes. `assets/gem/BMS_DDC_GEM_v3.2.txt` is kept; the tool loads v4.
- Job data is under NDA: tests use hand-made text only; the gate's outputs stay under `out/`.
- Commit after each task; never push. Commit messages end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Run the whole suite before each commit: `.venv/Scripts/python.exe -m pytest -q` (about 1,390 tests today).

## Shapes already in the code (read-only reference)

- `estimator.ledger.facts.Ledger`: `facts: dict[str, Fact]` in order, `of_kind`, `about`, `find`, `find_value`, `table(ids)`, `printed_count`, `sources`, `understanding: dict[pass, str]`. `Fact`: `id, kind, subject, value, source_id, quote, stage, state, contradictions`.
- `estimator.ledger.passes.Pass(name, title, settles, may_add, sections, sheet_types, with_images, instructions, not_sheet_types=())`, `PASSES`, `documents(pass_, dossier, catalogue)`, `prompt(pass_, ledger, text, images)`, `apply(...)`. `estimator.ledger.run.read_job(judge, dossier, catalogue, save_to=None, limit=None)`; it passes `dossier.images` to passes with `with_images`.
- `estimator.ledger.to_plan`: `ledger_plan(ledger) -> JobPlan`, `entry_text(system, ledger)`, `system_counts(system, ledger)`, `count_note(ledger, fact)`, `_naming`, `_matches`, `_system`, `_group_system`.
- `estimator.writing.whole_job`: `PlannedSystem(... families=(), count_note="", facts=())`, `WrittenLine(text, depth, quantity, quote, source_id, why, confidence, reference, flag, flag_text, fact_ids)`, `WrittenScope(lines, client_notes, tech_hours_hint, review_notes, model, refused, quick_scan, explanation, contradictions, misc_responsibilities, exclusions, qc)`, `write_prompt(system, evidence_text, images, options, examples, style_text, hours_rule="", image_ids=None, ledger_text="")`, `write_schema()`, `parse_scope(...)`, `ledger_check(scope, facts, counts)`, `gem_prompt(path=GEM_FILE, practice=PRACTICE_FILE)` with `GEM_START="WHO YOU ARE"`, `GEM_END="END OF INSTRUCTIONS"`, `GEM_AFTER="INPUT HANDLING — SEQUENCE AND POINT LIST"`, `GEM_CUTS`, `GEM_CONNECTING`, `GEM_OUTPUT`, `_gem_heading(line)` (an all-caps line), `TEMPLATE_WORDS`, `FLAGS=("", "red", "yellow", "orange", "green")`, `SPLIT_LIMIT`, `_chunks`, `known_ids`, `images_text`, `images_listing`, `content_blocks`.
- `estimator.writing.judge.Judge`: `_answer_with_images(kind, name, system_prompt, prompt, schema, extra, images, ids=None)`, `write_system(...)`, `ask_pass(...)`, kinds `CHOOSE, COMPOSE, READ_SCHEDULE, WRITE_SYSTEM, READ_PASS`, `_MAIN_LIST`, `KINDS`, `_for_job`.
- `estimator.writing.assemble`: `assemble_job(catalogue, reading, dossier, plan, scopes, today, templates=None)`, `_check_one` (the `ledger = bool(system.facts)` branch), `_nothing_behind`, `existence_question`, `_held_system`, `tech_hours(...)`, `flag_review(name, text, line, style) -> (ReviewItem | None, note | None)`, `with_clarifications(text, notes)`, the `_Row.after` list of per-line "*" notes, `_written_system(...)` (line ~2593 prints `with_clarifications(_with_total(r, style), r.after)`), `count_notes(written, parts)`, `TIER_FIRST, TIER_QUANTITY, TIER_QUESTION, TIER_DISAGREE, TIER_REST`.
- `estimator.writing.style.HouseStyle`: `internal(text)`, `forbidden(text)`, `house_opening(text)`, `is_monitoring`, `is_device`, `prompt_text()`, `check_note`; the JSON `assets/house_style.json` holds `verbs, trailing_forms, integration_trio, notes, forbidden, internal, clarifications, unit_maker_devices, misc_monitoring, line_order, sow_positions, …`.
- `estimator.writing.dossier`: `DossierImage(path, what, sheet, document, page)`, `_render(page, clip, dpi, folder, key) -> Path`, `SHEET_DPI=150`, `IMAGES_FOLDER="dossier-images"`, `IMAGE_VERSION`, `_file_key(path)`; `Dossier.images` are the schedule pictures with job-wide ids `I1..In`.
- `estimator.evidence.workbook.write_evidence(path, catalogue, reading=None, systems=None, review_flags=(), plan=None, ledger=None)`; tabs `TABS, ESTIMATE_TABS, PLAN_TAB, READ_TAB, LEDGER_TAB, GEM_TAB`; helpers `_headings, _append, _widths, _decision_columns(ws, column)`; `DECISION, CHANGE_TO` column names read back by `estimator corrections`.
- `estimator.__main__._estimate_whole_job`: builds the dossier, `read_ledger`, `ledger_plan`, the write loop, `assemble_job`, `plan_checks`, `review_list`, corrections, `write_evidence`, then the proposal and price sheet; `whole_job_lines(...)` prints the summary; argparse `estimate` has `--ai`, `--no-ai`, `--cache`, `--method`, `--documents`.
- Tests: `tests/test_whole_job.py` (`FakeClient`, `_response`, `_judge`, `_system`, `_ledger_answer`, `_ledger_line`), `tests/test_ledger_plan.py` (`_ledger()`, `_read` helper: seed → apply → ledger_plan), `tests/test_ledger_passes.py` (`_dossier`, `CATALOGUE`, `_answer`, `_known`), `tests/test_assemble.py` (`_dossier`, `FakeJudge`, the stand-in `PlannedSystem`), `tests/test_estimate.py` (`whole_job` fixture, `_fake_ledger`, `JOB_PLAN`, `SCOPES`), `tests/test_evidence.py` (`_catalogue()`), `tests/test_gem_round.py` (the GEM prompt's contents and schema).

---

## File structure

| File | Responsibility |
|---|---|
| `assets/gem/BMS_DDC_GEM_v4.txt` | the GEM in plain language, no emoji, practice rules folded in (Task 1) |
| `assets/house_style.json` | new key `packaged_units` (internal devices, shipped-loose devices, point-line pattern, controls-contractor terms, duct heater interlock patterns, damper prefixes) (Task 3) |
| `src/estimator/writing/brief.py` | `job_brief(ledger, plan, templates)`, `system_class(ledger, system)`, `shared_owners(ledger, plan)` (Task 2) |
| `src/estimator/writing/house_check.py` | `house_check(scope, system, klass, owned_elsewhere, style) -> WrittenScope` (Task 3) |
| `src/estimator/writing/whole_job.py` | write prompt order with the brief and the frame; `GEM_FILE` → v4; `GEM_OUTPUT` flag words (Tasks 1, 4) |
| `src/estimator/writing/judge.py` | `write_system(..., brief="", klass="", owned_elsewhere=())`; `QC_JOB` kind and `Judge.qc_job` (Tasks 4, 8) |
| `src/estimator/writing/assemble.py` | one clarification per block; sequence-only systems printed, not held; 4 h integration hours; count note place (Task 5) |
| `src/estimator/ledger/to_plan.py` | `count_note` place words; linked dampers join their fan; the remaining damper block (Tasks 5, 6) |
| `src/estimator/ledger/passes.py`, `run.py` | plans pass settles `link`; pictures for plans and risers with a cap and `--no-pictures` (Task 7) |
| `src/estimator/writing/dossier.py` | `sheet_pictures(catalogue, cache_dir, keys)` (Task 7) |
| `src/estimator/writing/qc.py` | the QC request, schema, parse, review rows (Task 8) |
| `src/estimator/evidence/workbook.py` | "Proposal QC" tab; brief and QC paragraphs on How the job was read (Task 9) |
| `src/estimator/__main__.py` | brief, house check inputs, QC pass, `--no-qc`, `--no-pictures` (Task 9) |
| `.claude/skills/run-job/SKILL.md`, `tools/run_job.py`, `.claude/run-job.json` | the run-job command (Task 10) |
| tests | `tests/test_gem_v4.py`, `tests/test_brief.py`, `tests/test_house_check.py`, `tests/test_qc.py`, additions to `test_ledger_plan.py`, `test_ledger_passes.py`, `test_ledger_run.py`, `test_assemble.py`, `test_evidence.py`, `test_estimate.py`, `test_whole_job.py` |

---

### Task 1: The GEM in plain language (v4)

**Files:**
- Create: `assets/gem/BMS_DDC_GEM_v4.txt`
- Modify: `src/estimator/writing/whole_job.py` (`GEM_FILE`, `GEM_OUTPUT`, `_FLAG_SYMBOLS` left for old answers)
- Test: `tests/test_gem_v4.py`; update `tests/test_gem_round.py` where it asserts v3.2 wording

**Interfaces:**
- Produces: `GEM_FILE = ASSETS / "gem" / "BMS_DDC_GEM_v4.txt"`; `gem_prompt()` unchanged in signature and still returns the text from "WHO YOU ARE" to "END OF INSTRUCTIONS" with the connecting section after "INPUT HANDLING — SEQUENCE AND POINT LIST", the practice rules, and the OUTPUT section.
- The v4 text keeps these exact headings (all caps lines, as `_gem_heading` detects them): `WHO YOU ARE`, `STEP 0 — PROJECT QUICK SCAN`, `CONTRACTOR NAME RULE`, `INPUT HANDLING — SEQUENCE AND POINT LIST`, `SCOPE OWNERSHIP — PRIMARY RULE`, `DEVICE OWNERSHIP RESOLUTION`, `BLANKET WIRING CLAUSE`, `DAMPER ACTUATOR RULE`, `FEEDBACK SIGNALS — HARDWIRED FURNISH POINTS`, `VERB RULES`, `FIRE ALARM AND LIFE SAFETY INTERFACE`, `PACKAGED UNITS — FACTORY CONTROLS` (replaces "FACTORY CONTROLS — COMPLETE RULE"), `MANDATORY MINIMUM POINTS`, `PUMPS`, `COOLING TOWERS`, `SOW ORDER — STANDARD TEMPLATE`, `INTEGRATION LINES — FIXED GROUP`, `MISCELLANEOUS RESPONSIBILITIES`, `CONTRADICTION AND ASSUMPTION SCAN`, `SELF-QC`, `FLAGS`, `ADDITIONAL RULES — NAMING, SENSORS, FILTERS, CONSOLIDATION`, `SYSTEM EXPLANATION`, `END OF INSTRUCTIONS`. The chat mechanics (RESET PROTOCOL, Phase 2 clean SOW, the display table, the hardware highlight option) are left out, so `GEM_CUTS` find nothing and skip.
- Flags are words everywhere in v4: `CONFIRM QUANTITY` (was the red circle), `CONFIRM OWNERSHIP` (yellow), `ASSUMED` (orange), `NOTE` (green). `GEM_OUTPUT` maps them: `flag: "red" for CONFIRM QUANTITY, "yellow" for CONFIRM OWNERSHIP, "orange" for ASSUMED, "green" for NOTE, "" for none`.

Content rules for the rewrite (the implementer reads v3.2 whole first):
- Same method, same order of sections, same rules; one idea per sentence; no emoji, no `★`, no `◊` (write "the manufacturer's representative line, one level in"), no `[?]` marks.
- Fold in `assets/gem/ame_practice.txt` where a rule is refined: the packaged-unit section says what the estimator said (internal devices never lines even under a blanket wiring clause; shipped-loose devices "Install and Wire … (Furnished by Unit Mfr.)"; "Wire … (Furnished by Unit Mfr.)" only when the sequence assigns that wiring; the three integration lines cover every "monitor at the BMS"; "Furnish <point>" lines only on AME-DDC systems); the damper section says actuators go under the fan they serve and untraceable dampers form one block with sheet references; the duct heater rule (interlock-only on packaged units); other trades in brackets; one "*" clarification per block; UUKL controls in scope; systems named only in the sequence printed with "Qty (##)" and "*Quantity per plumbing drawings".
- The "SOW ORDER — STANDARD TEMPLATE" section gains the frame rule: the Master Template entry given with the request is how AME writes this kind of system; write its lines in its order with the ownership verb the documents decide; leave one out only when the documents exclude it; add one only when the sequence explicitly assigns a device or work to the controls contractor that no template line covers; never a line per monitored point.
- Keep the Quick Scan's eight fields, the contradiction scan's six types (C1–C6) and the Self-QC's ten checks by their existing names, because the answer schema and the GEM QC tab use them.
- The report carries a side-by-side table: every v3.2 rule heading, the v4 heading, and "same | reworded | refined by practice rule <name> | dropped (chat mechanics)". The estimator reads that table before v4 replaces v3.2 in daily use.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_gem_v4.py
"""The GEM in plain language: same method, no emoji, the practice rules folded in, the tool's anchors kept."""
import re

from estimator.writing.whole_job import GEM_END, GEM_FILE, GEM_START, gem_prompt

EMOJI = re.compile(r"[\U0001F000-\U0001FAFF☀-➿⬀-⯿■-◿◆◊️]")
HEADINGS = ["WHO YOU ARE", "STEP 0 — PROJECT QUICK SCAN", "CONTRACTOR NAME RULE",
            "INPUT HANDLING — SEQUENCE AND POINT LIST", "SCOPE OWNERSHIP — PRIMARY RULE",
            "DEVICE OWNERSHIP RESOLUTION", "BLANKET WIRING CLAUSE", "DAMPER ACTUATOR RULE",
            "FEEDBACK SIGNALS — HARDWIRED FURNISH POINTS", "VERB RULES", "FIRE ALARM AND LIFE SAFETY INTERFACE",
            "PACKAGED UNITS — FACTORY CONTROLS", "MANDATORY MINIMUM POINTS", "SOW ORDER — STANDARD TEMPLATE",
            "INTEGRATION LINES — FIXED GROUP", "MISCELLANEOUS RESPONSIBILITIES", "CONTRADICTION AND ASSUMPTION SCAN",
            "SELF-QC", "FLAGS", "ADDITIONAL RULES — NAMING, SENSORS, FILTERS, CONSOLIDATION", "SYSTEM EXPLANATION",
            "END OF INSTRUCTIONS"]


def test_the_tool_loads_v4():
    assert GEM_FILE.name == "BMS_DDC_GEM_v4.txt" and GEM_FILE.exists()


def test_v4_has_no_emoji_or_marks():
    text = GEM_FILE.read_text(encoding="utf-8")
    assert not EMOJI.search(text), EMOJI.search(text).group(0)
    assert "[?]" not in text and "★" not in text and "◊" not in text


def test_v4_keeps_the_headings_in_order():
    text = GEM_FILE.read_text(encoding="utf-8")
    positions = [text.find(h) for h in HEADINGS]
    assert all(p >= 0 for p in positions), [h for h, p in zip(HEADINGS, positions) if p < 0]
    assert positions == sorted(positions)


def test_v4_flags_are_words():
    text = GEM_FILE.read_text(encoding="utf-8")
    for word in ("CONFIRM QUANTITY", "CONFIRM OWNERSHIP", "ASSUMED", "NOTE"):
        assert word in text


def test_v4_folds_in_the_estimators_rules():
    text = GEM_FILE.read_text(encoding="utf-8").lower()
    for phrase in ("install and wire", "furnished by unit mfr.", "never a line per monitored point",
                   "quantity per plumbing drawings", "one \"*\" clarification per block", "uukl",
                   "under the fan", "interlock"):
        assert phrase in text, phrase


def test_the_prompt_still_starts_and_ends_at_the_anchors_and_carries_the_output_section():
    prompt = gem_prompt()
    assert prompt.startswith(GEM_START)
    assert prompt.rstrip().endswith(GEM_END)
    assert "OUTPUT" in prompt and '"red" for CONFIRM QUANTITY' in prompt
    assert "CONNECTING THE DOTS" in prompt and "AME PRACTICE" in prompt
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_gem_v4.py -q`
Expected: FAIL (`GEM_FILE.name == "BMS_DDC_GEM_v3.2.txt"`, file missing)

- [ ] **Step 3: Write v4 and point the tool at it**

Write `assets/gem/BMS_DDC_GEM_v4.txt` per the content rules above (the implementer reads `BMS_DDC_GEM_v3.2.txt` and `ame_practice.txt` whole first). In `whole_job.py`: `GEM_FILE = ASSETS / "gem" / "BMS_DDC_GEM_v4.txt"`; in `GEM_OUTPUT` replace the flag sentence with: `flag: "red" for CONFIRM QUANTITY, "yellow" for CONFIRM OWNERSHIP, "orange" for ASSUMED, "green" for NOTE, or "" for none.` Keep `_FLAG_SYMBOLS` (old cached answers may still carry glyphs). Update any `tests/test_gem_round.py` assertion that quotes v3.2 wording to the v4 wording, and say which in the report.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_gem_v4.py tests/test_gem_round.py tests/test_gem_round2.py tests/test_whole_job.py -q`, then the full suite.
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add assets/gem/BMS_DDC_GEM_v4.txt src/estimator/writing/whole_job.py tests/test_gem_v4.py tests/test_gem_round.py
git commit -m "feat: the GEM in plain language (v4), the estimator's practice rules folded in; the tool loads it"
```

---

### Task 2: The job brief

**Files:**
- Create: `src/estimator/writing/brief.py`
- Test: `tests/test_brief.py`

**Interfaces:**
- Consumes: `Ledger`, `JobPlan`/`PlannedSystem`, templates (`load_templates()`; `system_template(system, templates)` from assemble).
- Produces:
  - `system_class(ledger, system) -> str` — `"packaged"` when a `provider` fact about one of the system's prefixes or tags (subject contains the prefix, case-insensitive, whole word) has a value naming the unit maker or factory (`unit mfr`, `manufacturer`, `factory`, `oem`, `packaged`, `comes with the unit`), or the writer's Quick Scan said so; `"field"` otherwise.
  - `shared_owners(ledger, plan) -> dict[str, str]` — item key → system key that owns it: for every `link` fact whose subject names a damper (prefix in `packaged_units.damper_prefixes` from house style, default `("MD",)`, or subject contains "damper") the fan/unit system the value names owns `"damper actuator <subject>"`; for every `link`/`provider` fact naming a duct heater (`EDH`) served unit, that unit's system owns `"duct heater interlock <tag>"`; the VRF/split system owns `"condensate pump float switch"` when any of its facts mention condensate.
  - `job_brief(ledger, plan, templates, limit=4000) -> str` — plain text, in this order: (1) "What the job is": the sequence pass's understanding, else the schedules pass's, cut at 1,200 characters at a sentence end; (2) "The systems": one line each `key | header | Qty n or ## | kind | packaged or field | serves: … | served by: …` from `link` facts; (3) "Rules the sequence sets for the whole job": the `note` facts with subject `general`, one per line; (4) "Who owns shared items": `shared_owners` as `item — <system key>`. Cut the whole text to `limit` at a line end, ending with "(cut)" when cut.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_brief.py
"""The job brief every write request and the QC pass share."""
from estimator.ledger.facts import SETTLED, Ledger
from estimator.ledger.to_plan import ledger_plan
from estimator.writing.brief import job_brief, shared_owners, system_class
from estimator.writing.templates import load_templates

SOURCES = {"S5": "equipment counts for RTU (schedules and plans)", "S6": "equipment counts for EF (schedules and plans)",
           "S7": "equipment counts for MD (schedules and plans)", "S10": "M-201, Drawings.pdf page 3 (sheet text)",
           "S20": "RTU SCHEDULE, Drawings.pdf page 12", "Q1": "sequence section “RTU”, Specs.pdf page 4"}


def _ledger():
    L = Ledger(SOURCES)
    L.add("family", "RTU", "Rooftop Unit", "[S5]", "RTU", "schedules", SETTLED)
    L.add("count", "RTU", 2, "[S5]", "schedule rows 2", "seed", SETTLED)
    L.add("unit", "RTU", "RTU-1, 2", "[S5]", "Tags: RTU-1, 2", "seed", SETTLED)
    L.add("provider", "RTU controller", "unit mfr: DDC microprocessor controls with unit mounted panel", "[S20]", "DDC MICROPROCESSOR CONTROLS", "schedules", SETTLED)
    L.add("family", "EF", "Exhaust Fan", "[S6]", "EF", "schedules", SETTLED)
    L.add("count", "EF", 3, "[S6]", "schedule rows 3", "seed", SETTLED)
    L.add("unit", "EF", "EF-1 thru 3", "[S6]", "Tags: EF-1 thru 3", "seed", SETTLED)
    L.add("family", "MD", "Motorized Damper", "[S7]", "MD", "schedules")
    L.add("count", "MD", 4, "[S7]", "plan placements 4", "seed")
    L.add("link", "MD-1", "EF-1", "[S10]", "MD-1 EF-1", "plans", SETTLED)
    L.add("link", "EF", "RTU-1", "[S10]", "EF-1 interlocked with RTU-1", "risers", SETTLED)
    L.add("note", "general", "fire/smoke dampers are controlled by the fire alarm system", "[Q1]", "Fire/smoke dampers shall be controlled through the fire alarm system", "sequence", SETTLED)
    L.understanding = {"schedules": "Two rooftop units and three fans.", "sequence": "Two packaged rooftop units serve the corridors; three exhaust fans interlock with them."}
    L.job_name = "26-9999"
    return L


def test_system_class_reads_the_provider_facts():
    L = _ledger(); plan = ledger_plan(L)
    rtu = next(s for s in plan.systems if s.key == "RTU"); ef = next(s for s in plan.systems if s.key == "EF")
    assert system_class(L, rtu) == "packaged"
    assert system_class(L, ef) == "field"


def test_shared_owners_follow_the_links():
    L = _ledger(); plan = ledger_plan(L)
    owners = shared_owners(L, plan)
    assert owners["damper actuator MD-1"] == "EF"


def test_the_brief_has_the_four_parts_in_order_and_fits_the_limit():
    L = _ledger(); plan = ledger_plan(L)
    text = job_brief(L, plan, load_templates())
    i = [text.index(h) for h in ("What the job is", "The systems", "Rules the sequence sets", "Who owns shared items")]
    assert i == sorted(i)
    assert "Two packaged rooftop units serve the corridors" in text
    assert "RTU | Rooftop Unit RTU-1, 2 | Qty 2 | Rooftop Unit | packaged" in text
    assert "EF | Exhaust Fan EF-1 thru 3 | Qty 3 | Exhaust Fan | field | served by: RTU-1" in text
    assert "fire/smoke dampers are controlled by the fire alarm system" in text
    assert "damper actuator MD-1 — EF" in text
    short = job_brief(L, plan, load_templates(), limit=300)
    assert len(short) <= 310 and short.rstrip().endswith("(cut)")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_brief.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'estimator.writing.brief'`

- [ ] **Step 3: Write the module**

```python
# src/estimator/writing/brief.py
"""The job brief (design 2026-10-03 §2.1): one short text built from the ledger after the passes, given to every
write request and to the QC pass, so each system is written knowing the whole job: what the job is, every system
with its count, kind, packaged-or-field class and links, the sequence's general rules, and who owns the shared
items (a damper's actuator belongs to its fan, a duct heater's interlock to the unit it serves)."""
from __future__ import annotations

import re

from estimator.writing.style import load_house_style

_MAKER = re.compile(r"\b(?:unit\s+mfr|manufacturer|factory|oem|packaged|comes?\s+with\s+the\s+unit|furnished\s+with\s+the\s+unit)\b", re.I)
_SPACES = re.compile(r"\s+")


def _squash(text) -> str:
    return _SPACES.sub(" ", str(text or "")).strip()


def _names(system) -> list[str]:
    names = [system.key] + list(system.tags or ())
    names += [t.split("-")[0] for t in system.tags or () if "-" in t]
    return [n for n in dict.fromkeys(_squash(n) for n in names) if n]


def _word(name: str, text: str) -> bool:
    return re.search(rf"(?<![A-Za-z0-9]){re.escape(name)}(?![A-Za-z0-9])", text, re.I) is not None


def system_class(ledger, system) -> str:
    """"packaged" when a provider fact about the system says the unit maker or the factory controls it; else "field"."""
    names = _names(system)
    for fact in ledger.of_kind("provider"):
        if any(_word(n, fact.subject) for n in names) and _MAKER.search(_squash(fact.value)):
            return "packaged"
    return "field"


def _system_of(plan, name: str):
    name = _squash(name)
    for system in plan.systems:
        if any(n.casefold() == name.casefold() for n in _names(system)):
            return system
    for system in plan.systems:
        if any(_word(n, name) for n in _names(system)):
            return system
    return None


def shared_owners(ledger, plan) -> dict[str, str]:
    """item -> the key of the system that owns it, from the ledger's links."""
    style = load_house_style()
    damper_prefixes = tuple(getattr(style, "packaged_units", {}).get("damper_prefixes", ("MD",)))
    owners: dict[str, str] = {}
    for fact in ledger.of_kind("link"):
        subject, value = _squash(fact.subject), _squash(fact.value)
        prefix = subject.split("-")[0].upper()
        if prefix in damper_prefixes or "damper" in subject.lower():
            owner = _system_of(plan, value)
            if owner is not None:
                owners[f"damper actuator {subject}"] = owner.key
        if subject.upper().startswith("EDH") or "duct heater" in subject.lower():
            owner = _system_of(plan, value)
            if owner is not None:
                owners[f"duct heater interlock {subject}"] = owner.key
    for system in plan.systems:
        if any("condensate" in _squash(ledger.facts[f].value).lower() for f in system.facts if f in ledger.facts):
            owners.setdefault("condensate pump float switch", system.key)
    return owners


def _links(ledger, system) -> tuple[list[str], list[str]]:
    names = _names(system)
    serves, served = [], []
    for fact in ledger.of_kind("link"):
        s, v = _squash(fact.subject), _squash(fact.value)
        if any(_word(n, s) for n in names) and not any(_word(n, v) for n in names):
            served.append(v)
        elif any(_word(n, v) for n in names) and not any(_word(n, s) for n in names):
            serves.append(s)
    return list(dict.fromkeys(serves)), list(dict.fromkeys(served))


def _cut(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    head = text[:limit]
    stop = max(head.rfind(". "), head.rfind("\n"))
    return (head[:stop + 1] if stop > 0 else head).rstrip() + " (cut)"


def job_brief(ledger, plan, templates=None, limit: int = 4000) -> str:
    what = ledger.understanding.get("sequence") or ledger.understanding.get("schedules") or ""
    lines = [f"Job: {getattr(ledger, 'job_name', '') or ''}".rstrip(), "", "What the job is", _cut(_squash(what), 1200), "",
             "The systems (key | header | count | kind | packaged or field | links)"]
    for system in plan.systems:
        serves, served = _links(ledger, system)
        qty = f"Qty {system.quantity}" if system.quantity is not None else "Qty ##"
        parts = [system.key, system.header, qty, system.kind, system_class(ledger, system)]
        if serves:
            parts.append("serves: " + ", ".join(serves))
        if served:
            parts.append("served by: " + ", ".join(served))
        lines.append(" | ".join(parts))
    general = [_squash(f.value) for f in ledger.of_kind("note") if f.subject.casefold() == "general"]
    if general:
        lines += ["", "Rules the sequence sets for the whole job"] + [f"- {g}" for g in general]
    owners = shared_owners(ledger, plan)
    if owners:
        lines += ["", "Who owns shared items (no other block writes them)"] + [f"- {item} — {key}" for item, key in owners.items()]
    text = "\n".join(lines)
    if len(text) > limit:
        head = text[:limit]
        text = head[:head.rfind("\n")].rstrip() + "\n(cut)"
    return text
```

Note: `load_house_style()` returns a `HouseStyle` dataclass without a `packaged_units` attribute until Task 3 adds it; `getattr(style, "packaged_units", {})` keeps this task independent.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_brief.py -q`, then the full suite.
Expected: all pass. If `test_the_brief_...` fails on the exact "served by" text because `_links` lists "RTU-1" under EF (the link `EF -> RTU-1` has subject EF), adjust `_links` so a link whose subject names the system is "served by"/"interlocked with" its value: that is the intended reading; keep the test.

- [ ] **Step 5: Commit**

```bash
git add src/estimator/writing/brief.py tests/test_brief.py
git commit -m "feat: the job brief every write request and the QC pass share"
```

---

### Task 3: The house check (the packaged-unit doctrine in code)

**Files:**
- Modify: `assets/house_style.json` (new key `packaged_units`), `src/estimator/writing/style.py` (`HouseStyle.packaged_units` dict, loaded like the other keys)
- Create: `src/estimator/writing/house_check.py`
- Test: `tests/test_house_check.py`

**Interfaces:**
- `house_style.json` gains:

```json
"packaged_units": {
  "about": "The estimator's packaged-unit doctrine (ame_practice.txt, 2026-10-03), enforced on a system the writer declared packaged/factory controls. 'internal' names devices wired inside the unit: a line about one is refused unless its quote names the controls contractor ('cc_terms'). 'shipped_loose' names devices the factory cannot mount: a 'Wire …' line about one becomes 'Install and Wire …'. 'point_line' matches a 'Furnish <point>' line, refused on a packaged unit. 'duct_heater_keep' are the duct heater lines kept on a packaged unit (the rest are refused). 'damper_prefixes' are the tag prefixes of motorized dampers. Regular expressions, ignoring case.",
  "internal": ["\\bvalve\\b", "\\bdx\\b", "\\bcompressor", "\\breversing\\s+valve", "\\bhot\\s+gas", "\\breheat\\b", "\\bfan\\s+speed", "\\bfilter\\s+(?:dp|differential)", "\\bairflow\\s+switch", "\\bcut-?out", "\\bsafet(?:y|ies)\\b", "\\bcondensate\\s+overflow", "\\bexpansion\\s+valve", "\\binternal\\b", "\\beconomizer\\b", "\\benergy\\s+(?:recovery\\s+)?wheel\\b", "\\bheat\\s+wheel\\b", "\\bleak\\s+detect(?:or|ion)\\b(?!.*shaft)"],
  "shipped_loose": ["\\bspace\\s+(?:temperature\\s+)?sensor", "\\bthermostat\\b", "\\bsupply\\s+air\\s+temperature", "\\bdischarge\\s+air\\s+temperature", "\\b(?:duct\\s+)?static\\s+pressure", "\\bhumidity\\s+sensor", "\\bco2?\\s+sensor", "\\bshipped\\s+loose", "\\bend\\s+devices?\\b"],
  "point_line": "^\\s*Furnish\\s+(?!and\\b)(?!BMS\\b)(?!DDC\\b)(?!Network\\b)(?!PC\\b)(?!POT\\b)(?!UPS\\b)(?!3-D\\b)(?!Necessary\\b)",
  "cc_terms": ["\\bbms\\s+contractor", "\\bcontrols?\\s+contractor", "\\batc\\s+contractor", "\\bthis\\s+contractor", "\\bddc\\s+contractor", "\\bbuilding\\s+automation\\s+contractor", "\\btemperature\\s+controls?\\s+contractor", "\\bame\\b"],
  "duct_heater_keep": ["\\binterlock", "\\bauxiliary\\s+contact", "\\benable\\b", "\\bremote\\s+(?:unit\\s+)?shutdown"],
  "duct_heater_words": "\\b(?:electric\\s+)?duct\\s+heater|\\bedh\\b",
  "damper_prefixes": ["MD"]
}
```

- `HouseStyle` gains `packaged_units: dict = field(default_factory=dict, hash=False, compare=False)`, filled from the JSON in `load_house_style()` the way the other dict keys are (read `style.py` to follow its pattern exactly).
- `house_check(scope: WrittenScope, system, klass: str, owned_elsewhere: dict[str, str], style: HouseStyle) -> WrittenScope`:
  - when `klass == "packaged"`:
    - a line whose text matches any `internal` pattern and whose `quote` matches no `cc_terms` pattern is refused: `"“{text}” is inside the unit and comes wired from the factory; the integration lines cover it (AME practice: packaged units); left out"`;
    - a line matching `point_line` (a "Furnish <point>" line) is refused: `"“{text}” is a monitored point on a packaged unit; the integration lines cover it (AME practice); left out"` — except the three integration lines themselves (`style.integration_trio` lines, matched after squashing);
    - a line starting `Wire ` whose text matches a `shipped_loose` pattern and carries `(Furnished by Unit Mfr.)` (or `Shipped Loose`) is rewritten to start `Install and Wire ` and the change is listed: `"“{old}” → “{new}” (AME practice: shipped-loose devices are installed and wired)"` in `refused`-style wording under a new `WrittenScope` field `changed: tuple[str, ...] = ()`;
    - a line matching `duct_heater_words` that matches none of `duct_heater_keep` is refused: `"“{text}”: on a packaged unit AME wires the duct heater's interlock only (AME practice: electric duct heaters); left out"`.
  - for any class: a line naming an item in `owned_elsewhere` whose owner is not this system (match the item's words after the kind: the damper tag, the duct heater tag, "condensate pump float switch") is refused: `"“{text}” is written under {owner}; left out here"`.
  - Lines kept otherwise; `refused` extended; the function never raises.
- `WrittenScope` gains `changed: tuple[str, ...] = ()` (whole_job.py).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_house_check.py
"""The packaged-unit doctrine in code: internal devices and monitored points are not lines on a packaged unit,
shipped-loose devices are installed and wired, duct heaters are interlock-only, shared items stay with their owner."""
from estimator.writing.house_check import house_check
from estimator.writing.style import load_house_style
from estimator.writing.whole_job import PlannedSystem, WrittenLine, WrittenScope


def _line(text, quote="BMS contractor shall connect the DDC controller to the BMS network"):
    return WrittenLine(text=text, depth=1, quantity=None, quote=quote, source_id="S2", why="", confidence=0.8,
                       reference="", flag="", flag_text="", fact_ids=("F1",))


def _scope(*lines):
    return WrittenScope(lines=tuple(lines), client_notes=(), tech_hours_hint=None, review_notes=(), model="m")


RTU = PlannedSystem("RTU", "Rooftop Unit RTU-1, 2", "Rooftop Unit", ("RTU-1", "RTU-2"), 2, "[S5]", "2", (), (), "", "", "", "", facts=("F1",))
STYLE = load_house_style()


def test_internal_devices_and_monitored_points_are_refused_on_a_packaged_unit():
    scope = _scope(_line("Wire DX Cooling Control (Each Stage)"), _line("Furnish Supply Fan Status"),
                   _line("Furnish BMS Communication Wiring to Factory Controls"),
                   _line("Install and Wire Space Temperature Sensor (Furnished by Unit Mfr.)"))
    out = house_check(scope, RTU, "packaged", {}, STYLE)
    assert [l.text for l in out.lines] == ["Furnish BMS Communication Wiring to Factory Controls",
                                           "Install and Wire Space Temperature Sensor (Furnished by Unit Mfr.)"]
    assert any("inside the unit" in r for r in out.refused)
    assert any("monitored point on a packaged unit" in r for r in out.refused)


def test_an_internal_device_the_sequence_assigns_to_the_controls_contractor_stays():
    scope = _scope(_line("Furnish and Wire Hot Water Control Valve and Actuator",
                         quote="The BMS contractor shall furnish and wire the hot water control valve"))
    out = house_check(scope, RTU, "packaged", {}, STYLE)
    assert len(out.lines) == 1 and out.refused == ()


def test_a_shipped_loose_wire_line_becomes_install_and_wire():
    scope = _scope(_line("Wire Supply Air Temperature Sensor (Furnished by Unit Mfr.)"))
    out = house_check(scope, RTU, "packaged", {}, STYLE)
    assert out.lines[0].text == "Install and Wire Supply Air Temperature Sensor (Furnished by Unit Mfr.)"
    assert out.changed and "shipped-loose" in out.changed[0]


def test_duct_heater_full_scope_is_cut_to_the_interlock_on_a_packaged_unit():
    scope = _scope(_line("Furnish Electric Duct Heater SCR Control"), _line("Wire Electric Duct Heater Auxiliary Contact for Remote Unit Shutdown"),
                   _line("Furnish and Install Electric Duct Heater Discharge Air Temperature Sensor"))
    out = house_check(scope, RTU, "packaged", {}, STYLE)
    assert [l.text for l in out.lines] == ["Wire Electric Duct Heater Auxiliary Contact for Remote Unit Shutdown"]


def test_a_field_ddc_system_keeps_its_point_lines():
    scope = _scope(_line("Furnish Fan Start / Stop and Status"), _line("Furnish and Install Damper Actuator"))
    out = house_check(scope, RTU, "field", {}, STYLE)
    assert len(out.lines) == 2 and out.refused == ()


def test_an_item_another_block_owns_is_refused_here():
    scope = _scope(_line("Furnish and Install Damper Actuator MD-1"), _line("Tie in Condensate Pump Float Switch"))
    out = house_check(scope, RTU, "field", {"damper actuator MD-1": "EF", "condensate pump float switch": "RTU"}, STYLE)
    assert [l.text for l in out.lines] == ["Tie in Condensate Pump Float Switch"]
    assert out.refused == ("“Furnish and Install Damper Actuator MD-1” is written under EF; left out here",)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_house_check.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'estimator.writing.house_check'`

- [ ] **Step 3: Write the code**

Add the JSON key, the `HouseStyle.packaged_units` field and its loading (follow how `internal` or `clarifications` are loaded in `style.py`; keep the raw dict with compiled patterns in a small helper). Add `changed: tuple[str, ...] = ()` to `WrittenScope`. Then:

```python
# src/estimator/writing/house_check.py
"""The house check (design 2026-10-03 §2.3): the estimator's packaged-unit doctrine and the shared-item rule,
enforced on a written scope after the ledger check. On a packaged unit a device wired inside the unit is never a
line unless the sequence names the controls contractor for it, a 'Furnish <point>' line is covered by the
integration lines, a shipped-loose device is installed and wired, and a duct heater keeps only its interlock lines.
In any block, an item another block owns is left to that block. Every refusal and change is listed in plain words."""
from __future__ import annotations

import dataclasses
import re

_SPACES = re.compile(r"\s+")


def _squash(text) -> str:
    return _SPACES.sub(" ", str(text or "")).strip()


def _patterns(style, key: str) -> list[re.Pattern]:
    raw = (getattr(style, "packaged_units", None) or {}).get(key, ())
    if isinstance(raw, str):
        raw = [raw]
    return [re.compile(p, re.I) for p in raw]


def _any(patterns, text: str) -> bool:
    return any(p.search(text) for p in patterns)


def _is_integration_line(style, text: str) -> bool:
    trio = getattr(style, "trio", ()) or ()
    plain = _squash(text).casefold()
    return any(_squash(t).casefold().split("{what}")[0].rstrip() in plain for t in trio)


def _item_words(item: str) -> str:
    for head in ("damper actuator ", "duct heater interlock "):
        if item.startswith(head):
            return item[len(head):]
    return item


def house_check(scope, system, klass: str, owned_elsewhere: dict[str, str], style):
    internal, loose, cc = _patterns(style, "internal"), _patterns(style, "shipped_loose"), _patterns(style, "cc_terms")
    point = _patterns(style, "point_line")
    keep, heater = _patterns(style, "duct_heater_keep"), _patterns(style, "duct_heater_words")
    kept, refused, changed = [], list(scope.refused), list(getattr(scope, "changed", ()))
    key = getattr(system, "key", "")
    for line in scope.lines:
        text, quote = line.text, line.quote or ""
        owner = next((o for item, o in owned_elsewhere.items()
                      if o != key and re.search(rf"(?<![A-Za-z0-9]){re.escape(_item_words(item))}(?![A-Za-z0-9])", text, re.I)), None)
        if owner:
            refused.append(f"“{text}” is written under {owner}; left out here")
            continue
        if klass == "packaged":
            if _any(heater, text) and not _any(keep, text):
                refused.append(f"“{text}”: on a packaged unit AME wires the duct heater's interlock only (AME practice: "
                               "electric duct heaters); left out")
                continue
            if _any(internal, text) and not _any(cc, quote):
                refused.append(f"“{text}” is inside the unit and comes wired from the factory; the integration lines "
                               "cover it (AME practice: packaged units); left out")
                continue
            if _any(point, text) and not _is_integration_line(style, text):
                refused.append(f"“{text}” is a monitored point on a packaged unit; the integration lines cover it "
                               "(AME practice); left out")
                continue
            if re.match(r"^\s*Wire\s+", text) and _any(loose, text) and re.search(r"Furnished by Unit Mfr|Shipped Loose", text, re.I):
                new = re.sub(r"^\s*Wire\s+", "Install and Wire ", text, count=1)
                changed.append(f"“{text}” → “{new}” (AME practice: shipped-loose devices are installed and wired)")
                line = dataclasses.replace(line, text=new)
        kept.append(line)
    return dataclasses.replace(scope, lines=tuple(kept), refused=tuple(refused), changed=tuple(changed))
```

`style.trio` holds the integration lines as the `HouseStyle` dataclass already names them (`trio: tuple[str, str, str]`); check the field name in `style.py` and use it.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_house_check.py tests/test_house_style.py tests/test_assets.py -q`, then the full suite.
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add assets/house_style.json src/estimator/writing/style.py src/estimator/writing/house_check.py src/estimator/writing/whole_job.py tests/test_house_check.py
git commit -m "feat: the house check enforces the packaged-unit doctrine and keeps shared items with their owner"
```

---

### Task 4: The writer takes the brief, the frame and the house check

**Files:**
- Modify: `src/estimator/writing/whole_job.py` (`write_prompt`, `TEMPLATE_WORDS`), `src/estimator/writing/judge.py` (`write_system`)
- Test: `tests/test_whole_job.py` (append)

**Interfaces:**
- `write_prompt(system, evidence_text, images, options, examples, style_text, hours_rule="", image_ids=None, ledger_text="", brief="", klass="")`: the order becomes (1) system text; (2) when `brief`: `"The job, as the reading settled it (every system is written knowing this):\n{brief}"`; (3) the Master Template block introduced as the frame: `"How AME writes this kind of system — the frame for this block. Write its lines, in its order, with the ownership verb the documents decide. Leave a line out only when the documents exclude it. Add a line only when the sequence explicitly assigns a device or work to the controls contractor that no template line covers, or names a device the template lacks. Never write a line per monitored point: the integration lines cover 'monitor at the BMS'.\n{options_text}"` (this replaces `TEMPLATE_WORDS`); (4) `"This unit is {packaged / field DDC} per the ledger: {one sentence of the doctrine for that class}"` when `klass`; (5) the ledger entry; (6) the evidence; (7) pictures; (8) the tech-hour rule.
- `Judge.write_system(..., brief="", klass="", owned_elsewhere=())`: passes `brief` and `klass` to `write_prompt`; after `parse_scope` and `ledger_check`, applies `house_check(scope, system, klass, dict(owned_elsewhere), self.style)`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_whole_job.py`)

```python
def test_the_write_prompt_puts_the_brief_then_the_frame_before_the_evidence():
    system = PlannedSystem(**{k: v for k, v in _system().items()})
    text = write_prompt(system, "[S2] evidence", [], ["Furnish and Install DDC Controller"], [], "",
                        ledger_text="F1 family RTU = x [S5] “x” (settled, seed)", brief="Job: 26-9999\nWhat the job is\nA school.",
                        klass="packaged")
    order = [text.index(s) for s in ("What the job is", "the frame for this block", "This unit is packaged",
                                     "The job ledger's facts", "[S2] evidence")]
    assert order == sorted(order)
    assert "Never write a line per monitored point" in text


def test_write_system_applies_the_house_check(tmp_path):
    reply = _ledger_answer(_ledger_line("Furnish Supply Fan Status"),
                           _ledger_line("Install and Wire Space Temperature Sensor (Furnished by Unit Mfr.)"))
    judge = _judge(tmp_path, FakeClient(_response(reply)))
    system = PlannedSystem(**{k: v for k, v in _system().items()})
    scope = judge.write_system(system, "[S2] evidence", [], [], [], "", ledger_text="F1 family RTU = x [S5] “x” (settled, seed)",
                               facts=("F1",), brief="Job", klass="packaged")
    assert [l.text for l in scope.lines] == ["Install and Wire Space Temperature Sensor (Furnished by Unit Mfr.)"]
    assert any("monitored point on a packaged unit" in r for r in scope.refused)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_whole_job.py -q -k "brief_then_the_frame or applies_the_house_check"`
Expected: FAIL (`write_prompt() got an unexpected keyword argument 'brief'`)

- [ ] **Step 3: Make the changes**

In `whole_job.py`: add the two parameters, the frame text as a module constant `FRAME_WORDS`, and the class sentence constants `CLASS_WORDS = {"packaged": "a packaged unit with factory controls: what is inside the unit is never a line; shipped-loose devices are 'Install and Wire … (Furnished by Unit Mfr.)'; the three integration lines cover every monitored point", "field": "a field-DDC system AME controls: write the controller, the sensors, the points and the actuators as the frame gives them"}`; keep `TEMPLATE_WORDS` defined (other code imports it) but the prompt uses `FRAME_WORDS`. In `judge.py`: add the parameters, pass them, and apply `house_check` last (import inside the method to avoid cycles).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_whole_job.py tests/test_gem_round.py tests/test_gem_round2.py tests/test_estimate.py -q`, then the full suite.

- [ ] **Step 5: Commit**

```bash
git add src/estimator/writing/whole_job.py src/estimator/writing/judge.py tests/test_whole_job.py
git commit -m "feat: the writer takes the job brief, writes into the Master Template frame, and passes the house check"
```

---

### Task 5: One clarification per block, sequence-only systems in the base bid, integration hours, count-note places

**Files:**
- Modify: `src/estimator/writing/assemble.py`, `src/estimator/ledger/to_plan.py`
- Test: `tests/test_assemble.py`, `tests/test_ledger_plan.py` (append)

**Interfaces and rules:**
1. **One clarification per block.** In `_written_system` (where each row prints `with_clarifications(_with_total(r, style), r.after)`): notes starting `*Confirm quantity:` and `*Assumed:` are taken out of `r.after` (maker notes `*… BY UNIT MFR.` stay inline) and gathered; after the block's lines, one note item per group: `"*Confirm quantities: <device A>, <device B>"` and `"*Assumed: <what A>; <what B>"` (devices and whats deduplicated, in line order, each at most 60 characters, the rest "and N more"). Review rows are unchanged. A function `block_clarifications(rows) -> tuple[list[_Row], list[str]]` does it and is unit-tested.
2. **Sequence-only systems print.** In `_check_one`: when `system.facts` is non-empty and the system's family fact stage is `"sequence"` (the `PlannedSystem.why` starts with "Named in the sequence of operation" — use that, it is what `to_plan` writes), the system is not held: category `PENDING`, review row `ReviewItem(name, PENDING, f"Give the count for {header}", "Named only in the sequence of operation; no drawing shows it", "Count it on the plumbing or electrical drawings and type the count in the header", tier=TIER_QUANTITY)`, and `_written_part` adds the note `"*Quantity per plumbing drawings"` to the block (a note item). Existence questions remain for systems the plan gave no facts for.
3. **Integration hours.** In `tech_hours`: when the template gives no hours (`template is None` or the "gives no hours" branch) and the system is integration-only (its kept lines are all integration lines, status/alarm "Furnish …" lines, or "Integrate …"/"Tie in …" lines, or its why says "Named in the sequence"), return `4.0` with `ReviewItem(name, ASSUMPTION, f"Tech hours for {name}: 4 h per integration (AME practice)", "No Master Template rule fits an integration-only system", "Confirm them")`. A helper `integration_only(system, lines, style) -> bool`.
4. **Count-note place.** In `to_plan.count_note`: a source whose `where` starts with `equipment counts for` prints as the quote's words instead of the place ("schedule rows 16", "distinct tags 15", "plan placements 731"); a sheet source prints its sheet number only (`M-101.00`), not the document and page. Form: `"*Qty. (16) per schedule rows 16; distinct tags 15."` and `"*Qty. (14) per M-201.00; schedule rows 12."` `where_short` stays for other uses; add `place_words(where, quote)` in `facts.py` or `to_plan.py`.

- [ ] **Step 1: Write the failing tests** (append; use the files' existing helpers)

```python
# tests/test_assemble.py
def test_one_clarification_per_block():
    from estimator.writing.assemble import block_clarifications, _Row
    from types import SimpleNamespace
    def row(text, after):
        return _Row(SimpleNamespace(text=text, flag="", source_id="", quote="", quantity=None, depth=1, origin=""), None, True, frozenset(), None, "S", after=list(after))
    rows = [row("Furnish and Install Sensor A", ["*Confirm quantity: Sensor A"]),
            row("Wire Relay B", ["*Assumed: the relay comes with the unit", "*RELAY B BY UNIT MFR."]),
            row("Furnish and Install Sensor C", ["*Confirm quantity: Sensor C"])]
    kept, notes = block_clarifications(rows)
    assert [r.after for r in kept] == [[], ["*RELAY B BY UNIT MFR."], []]
    assert notes == ["*Confirm quantities: Sensor A, Sensor C", "*Assumed: the relay comes with the unit"]


def test_a_sequence_only_system_prints_in_the_base_bid_with_its_note():
    from estimator.writing.assemble import _check_one
    from estimator.writing.whole_job import PlannedSystem
    system = PlannedSystem("EG", "Emergency Generator EG", "Emergency Generator", ("EG",), None, "", "", ("[Q21]",), (), "", "", "",
                           "Named in the sequence of operation; no drawing shows it.", sequence_section="[Q21]", facts=("F171",))
    check = _check_one(system, _dossier())
    assert check.held is False and check.category == "PENDING"
    assert any("Named only in the sequence" in r.evidence for r in check.review)


def test_integration_only_systems_get_four_hours():
    from estimator.writing.assemble import tech_hours
    from estimator.writing.whole_job import PlannedSystem
    system = PlannedSystem("HT", "Heat Tracing HT", "Heat Tracing", ("HT",), None, "", "", ("[Q24]",), (), "", "", "",
                           "Named in the sequence of operation; no drawing shows it.", facts=("F170",))
    hours, row = tech_hours(system, None, [("Integrate Heat Tracing Control Panel to the BMS via Serial Interface", None),
                                           ("Map Available Points Via Mfr. Provided BMS Interface", None)], None)
    assert hours == 4.0 and "4 h per integration" in row.decide
```

```python
# tests/test_ledger_plan.py
def test_the_count_note_names_the_place_in_plain_words():
    ledger = _ledger()
    ledger.contradict("F2", 14, "[S10]", "VAV-1 … VAV-14", "plans")
    # S10 is "M-201, Drawings.pdf page 3 (sheet text)": the sheet number only; F2's own source is the counts line,
    # so its quote's words stand in for the place
    assert count_note(ledger, ledger.facts["F2"]) == "*Qty. (14) per M-201; QUANTITY column total 12."
```

`_Row` is `_Row(line, q, own, tags, units, system, hours=None, folded=False, after=[])` (assemble.py ~line 1568); the test builds rows positionally as shown, each with its own `after` list.

5. **The left-out list suggests the line.** In `_left_out_rows`, each Master Template line the writer left out gets the action `f"Add it: {template line text}"` so adding it back is a decision, not a rewrite (spec §2.4).

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_assemble.py tests/test_ledger_plan.py -q -k "clarification_per_block or sequence_only or four_hours or place_in_plain"`
Expected: FAIL (`ImportError: cannot import name 'block_clarifications'`, held is True, hours None, old note text)

- [ ] **Step 3: Implement the four rules** as specified. For (2) also stop `_nothing_behind` from holding such a system (check `system.why` first). For (1) keep the per-line review rows exactly as before: only the printed brackets move.

- [ ] **Step 4: Run the tests to verify they pass**

Run: the five assemble test files, `tests/test_ledger_plan.py`, `tests/test_estimate.py`, then the full suite. Existing assemble tests that assert a per-line `(*Confirm quantity: …)` bracket must change to the block note; list each in the report.

- [ ] **Step 5: Commit**

```bash
git add src/estimator/writing/assemble.py src/estimator/ledger/to_plan.py tests/test_assemble.py tests/test_ledger_plan.py
git commit -m "feat: one clarification per block, sequence-only systems in the base bid, 4 h per integration, count notes name the place"
```

---

### Task 6: Linked dampers join their fan; the rest form one damper block

**Files:**
- Modify: `src/estimator/ledger/to_plan.py`, `src/estimator/ledger/passes.py` (plans pass `settles` gains `"link"`)
- Test: `tests/test_ledger_plan.py`, `tests/test_ledger_passes.py` (append)

**Interfaces and rules:**
- The plans pass may settle `link` (subject a damper tag or label as the sheet writes it, value the fan or unit it serves); its instructions gain one sentence: "When a motorized damper sits on a fan's duct or next to a fan on the plan, record a link: subject the damper's tag or label, value the fan's tag."
- In `ledger_plan`, after the systems are built: for every `link` fact whose subject is a damper (prefix in `packaged_units.damper_prefixes`, default `MD`, or the word "damper" in the subject) and whose value names a planned system (its key, a tag, or a tag prefix, whole word): the link fact's id and the damper's unit/location facts join that system's `facts`; the system gains `linked_dampers: int` (count of such links). `PlannedSystem` gains `linked_dampers: int = 0`.
- The damper family's own system: quantity = its printed count minus the linked count when positive; when no dampers remain unlinked, no damper system is planned. Its `why` lists the sheets from its `location` facts and link quotes: `"Dampers no fan claims; see M-101.00, M-112.00, M-134.00."`; its header stays the family's.
- `entry_text(system, ledger)` therefore shows the linked damper facts in the fan's entry, so the writer writes "Furnish and Install Damper Actuator (Qty. n Total)" there with the template line; `system_counts` includes the linked count (so the quantity passes the ledger check).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ledger_plan.py
def test_a_damper_linked_to_a_fan_joins_the_fan_and_leaves_the_damper_block():
    ledger = _ledger()
    ledger.add("family", "MD", "Motorized Damper", "[S10]", "MD", "plans")
    ledger.add("count", "MD", 3, "[S10]", "MD ×3", "plans")
    ledger.add("family", "EF", "Exhaust Fan", "[S10]", "EF-1", "plans")
    ledger.add("count", "EF", 1, "[S10]", "EF-1", "plans")
    ledger.add("link", "MD-1", "EF-1", "[S10]", "MD-1 at EF-1", "plans", SETTLED)
    plan = ledger_plan(ledger)
    ef = next(s for s in plan.systems if s.key == "EF")
    md = next(s for s in plan.systems if s.key == "MD")
    assert ef.linked_dampers == 1 and any(ledger.facts[f].kind == "link" for f in ef.facts)
    assert md.quantity == 2 and "no fan claims" in md.why
    assert 1 in system_counts(ef, ledger)


def test_when_every_damper_is_linked_there_is_no_damper_block():
    ledger = _ledger()
    ledger.add("family", "MD", "Motorized Damper", "[S10]", "MD", "plans")
    ledger.add("count", "MD", 1, "[S10]", "MD ×1", "plans")
    ledger.add("family", "EF", "Exhaust Fan", "[S10]", "EF-1", "plans")
    ledger.add("count", "EF", 1, "[S10]", "EF-1", "plans")
    ledger.add("link", "MD-1", "EF-1", "[S10]", "MD-1 at EF-1", "plans", SETTLED)
    assert [s.key for s in ledger_plan(ledger).systems if s.key == "MD"] == []
```

```python
# tests/test_ledger_passes.py
def test_the_plans_pass_may_settle_a_damper_link():
    ledger = seed(_dossier())
    refused = apply(pass_named("plans"), ledger, _answer(facts=[
        {"kind": "link", "subject": "MD-1", "value": "EF-1", "source_id": "[S10]", "quote": "MD-1 EF-1"}]), _known(ledger))
    assert refused == [] and ledger.find("link", "MD-1").state == SETTLED
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ledger_plan.py tests/test_ledger_passes.py -q -k "damper"`
Expected: FAIL (`PlannedSystem` has no `linked_dampers`; plans pass refuses `link`)

- [ ] **Step 3: Implement** in `to_plan.ledger_plan` (a post-pass over the built systems; `dataclasses.replace` on the frozen `PlannedSystem`s) and in `passes.py` (the plans pass's `settles` becomes `("location", "device", "link")` and the instruction sentence).

- [ ] **Step 4: Run the tests to verify they pass**, then the full suite.

- [ ] **Step 5: Commit**

```bash
git add src/estimator/ledger/to_plan.py src/estimator/ledger/passes.py src/estimator/writing/whole_job.py tests/test_ledger_plan.py tests/test_ledger_passes.py
git commit -m "feat: a damper linked to its fan is written under the fan; the rest form one damper block with sheet references"
```

---

### Task 7: Pictures for the plans and risers passes

**Files:**
- Modify: `src/estimator/writing/dossier.py` (new `sheet_pictures`), `src/estimator/ledger/passes.py` (`picture_types` on the plans and risers passes), `src/estimator/ledger/run.py` (`read_job(..., pictures=True, picture_cap=24)`), `src/estimator/__main__.py` (`--no-pictures`)
- Test: `tests/test_dossier.py`, `tests/test_ledger_run.py` (append)

**Interfaces:**
- `dossier.sheet_pictures(catalogue, cache_dir, keys: list[tuple[str, int]], what: str) -> list[DossierImage]`: renders each `(document, page)` whole at `SHEET_DPI` with `_render` under `cache_dir / IMAGES_FOLDER` (key `f"v{IMAGE_VERSION}|{document}|{_file_key(path)}|{page}|sheet|{SHEET_DPI}"`, so a schedule sheet already rendered is reused), `what = f"{sheet number} {title} — {what}"`; errors become no picture and a flag string in a second return value `(images, flags)`.
- `Pass` gains `picture_types: tuple[str, ...] = ()`: plans `("Plans",)`, risers `("Air riser", "Water riser")`.
- `run.read_job(judge, dossier, catalogue, save_to=None, limit=None, pictures=True, picture_cap=24)`: for a pass with `picture_types`, when `pictures`, the sheets whose text the pass reads (from `sheet_text_lines` ids → `catalogue.sheets` by number) and whose types intersect `picture_types`, ordered by the number of device labels the dossier counted on them (section 6 lines mention the sheet number; count mentions), capped at `picture_cap`; the rest are named in the prompt: `"Sheets not pictured (over the cap): M-104.00, M-106.00"`. Picture ids continue the dossier's numbering: `ids = [f"I{len(dossier.images) + k}" for k in 1..n]`, passed to `judge.ask_pass(..., images, extra, ids=ids)` (add an `ids=None` parameter to `ask_pass` and forward it to `_answer_with_images`), and `known_ids(part, images, ids)`.
- `__main__`: `--no-pictures` → `read_ledger(..., pictures=False)`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_dossier.py (append; `_picture_job(tmp_path)` already builds a catalogue with a one-page drawing "H.pdf", sheet H601)
def test_sheet_pictures_render_whole_sheets_once(tmp_path):
    from estimator.writing.dossier import sheet_pictures
    catalogue, _reading = _picture_job(tmp_path)
    images, flags = sheet_pictures(catalogue, tmp_path / "cache", [("H.pdf", 1)], "plan sheet")
    assert flags == [] and len(images) == 1
    path = Path(images[0].path)
    assert path.suffix == ".png" and path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert images[0].what == "H601 HVAC SCHEDULES — plan sheet"
    assert (images[0].sheet, images[0].document, images[0].page) == ("H601", "H.pdf", 1)
    again, _ = sheet_pictures(catalogue, tmp_path / "cache", [("H.pdf", 1)], "plan sheet")
    assert again[0].path == images[0].path
    missing, flags = sheet_pictures(catalogue, tmp_path / "cache", [("H.pdf", 9)], "plan sheet")
    assert missing == [] and len(flags) == 1
```

```python
# tests/test_ledger_run.py (append)
def test_the_plans_pass_lists_its_pictures_and_respects_the_cap(tmp_path, monkeypatch):
    from estimator.ledger import run as run_module
    rendered = []
    def fake_pictures(catalogue, cache_dir, keys, what):
        rendered.extend(keys)
        return [SimpleNamespace(path=str(tmp_path / f"{d}-{p}.png"), what=f"{d} {p} — {what}", sheet=None, document=d, page=p) for d, p in keys], []
    monkeypatch.setattr(run_module, "sheet_pictures", fake_pictures)
    client = FakeClient(*[_reply("ok") for _ in range(6)])
    judge = Judge(tmp_path / "cache", model="test-model", client=client)
    read_job(judge, _dossier(), CATALOGUE, picture_cap=1)
    plans_call = next(c for c in client.calls if "This is the Plans pass" in str(c["messages"][0]["content"]))
    content = str(plans_call["messages"][0]["content"])
    assert rendered == [("Drawings.pdf", 3)]          # the one plan sheet in the fixture
    assert "Picture I1" in content or "I1" in content


def test_no_pictures_keeps_the_passes_text_only(tmp_path, monkeypatch):
    from estimator.ledger import run as run_module
    monkeypatch.setattr(run_module, "sheet_pictures", lambda *a, **k: (_ for _ in ()).throw(AssertionError("rendered")))
    client = FakeClient(*[_reply("ok") for _ in range(6)])
    read_job(Judge(tmp_path / "cache", model="test-model", client=client), _dossier(), CATALOGUE, pictures=False)
```

- [ ] **Step 2: Run the tests to verify they fail**

- [ ] **Step 3: Implement** as specified. `run.py` imports `sheet_pictures` from `estimator.writing.dossier` at module level (so the test can monkeypatch it). The fixture `_dossier()` has no `images`, so the first new picture id is `I1`.

- [ ] **Step 4: Run the tests to verify they pass**, then the full suite.

- [ ] **Step 5: Commit**

```bash
git add src/estimator/writing/dossier.py src/estimator/ledger/passes.py src/estimator/ledger/run.py src/estimator/writing/judge.py src/estimator/__main__.py tests/test_dossier.py tests/test_ledger_run.py
git commit -m "feat: the plans and risers passes read their sheets as pictures too, within a cap; --no-pictures keeps them text-only"
```

---

### Task 8: The proposal QC pass

**Files:**
- Create: `src/estimator/writing/qc.py`
- Modify: `src/estimator/writing/judge.py` (`QC_JOB` kind, `Judge.qc_job`)
- Test: `tests/test_qc.py`

**Interfaces:**
- `qc.py`:
  - `QC_PROMPT: str` (system prompt): "You are a senior AME controls estimator reviewing a draft proposal another estimator wrote from this job's documents. You do not rewrite it. For each block you compare its lines with how AME writes that kind of system (the Master Template entry), with the estimator's practice rules, and with the job ledger's facts, and you list what is wrong in plain words, one finding per line or block, with the line as it should read when a fix is a line. Kinds of finding: ownership (wrong furnish/install/wire verb), not-ame-scope (inside a packaged unit, a monitored point restated, a device another party owns), missing (a template line usually present and not excluded, or an explicit sequence assignment no line covers), duplicate (the same device in two blocks), count, wording (not the house form), placement (belongs under another system). Severity must-fix when the proposal would be wrong or unpriceable as written, check otherwise. Then one paragraph per block in the estimator's voice, and one for the job. Never invent a device the documents do not name; never change a count."
  - `QcBlock` dataclass: `key, header, quantity, klass, lines: tuple[str, ...]` (the kept lines' text with "(Qty. N Total)" where the line has a quantity), `template_lines: tuple[str, ...]`, `hours_rule: str`, `ledger_entry: str`, `sequence_section: str`.
  - `qc_prompt(brief, blocks, practice_text, style_guide) -> str`; `qc_schema() -> dict` with `findings: [{system, line, kind (enum of the seven), say, fix, severity (must-fix|check), quote}]`, `block_notes: [{system, note}]`, `job_note: str`.
  - `QcFinding`, `QcReport(findings, block_notes, job_note, model, dropped)`; `parse_qc(answer, model, blocks) -> QcReport`: a finding naming an unknown system, or a `line` that is not one of that block's lines (squashed, case-insensitive; `""` allowed), is dropped and listed in `dropped`; `say` squashed; empty `say` dropped.
  - `qc_review_rows(report) -> list[ReviewItem]`: must-fix → `ReviewItem(system, "QC", say, quote, f"Change to: {fix}" if fix else "Remove the line" if line else "Add it", tier=TIER_FIRST, kind="qc")`; check → tier `TIER_DISAGREE`.
  - `split_blocks(blocks, limit) -> list[list[QcBlock]]`: whole blocks per part under the character limit.
- `judge.py`: `QC_JOB = "qc_job"`, `_MAIN_LIST[QC_JOB] = "findings"`, `KINDS += (QC_JOB,)`; `Judge.qc_job(name, system_prompt, prompt, schema, extra=None) -> (dict, str) | None` through `_answer_with_images(QC_JOB, name, ..., [], )`; `_for_job` recognises `qc_job` by the job number in the first 400 characters (the prompt starts "Job: …").

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_qc.py
"""The proposal QC pass: it compares, it never rewrites; its findings become review rows and a tab."""
from estimator.writing.qc import QcBlock, QcReport, parse_qc, qc_prompt, qc_review_rows, qc_schema, split_blocks

RTU = QcBlock("RTU", "Rooftop Unit RTU-1, 2", 2, "packaged",
              ("Wire Supply Air Temperature Sensor (Furnished by Unit Mfr.) (Qty. 2 Total)", "Furnish BMS Communication Wiring to Factory Controls"),
              ("Install and wire Supply Air Temperature Sensor (Furnished by Unit Mfr.)", "Furnish BMS Communication Wiring to Factory Controls",
               "Map Available Points Via Mfr. Provided BMS Interface"), "16 h per unit", "F1 family RTU = Rooftop Unit …", "[Q6]")


def test_the_prompt_carries_the_brief_the_blocks_the_template_and_the_rules():
    text = qc_prompt("Job: 26-9999\nWhat the job is\nA school.", [RTU], "PACKAGED UNITS — WHAT AME DOES: …", "How AME writes a system")
    for s in ("What the job is", "Rooftop Unit RTU-1, 2", "Wire Supply Air Temperature Sensor", "Map Available Points",
              "PACKAGED UNITS — WHAT AME DOES", "How AME writes a system", "packaged"):
        assert s in text
    assert qc_schema()["required"] == ["findings", "block_notes", "job_note"]


def test_findings_are_parsed_and_the_unknown_ones_dropped():
    answer = {"findings": [
        {"system": "RTU", "line": "Wire Supply Air Temperature Sensor (Furnished by Unit Mfr.) (Qty. 2 Total)", "kind": "ownership",
         "say": "The sensor ships loose, so AME installs and wires it.", "fix": "Install and Wire Supply Air Temperature Sensor (Furnished by Unit Mfr.) (Qty. 2 Total)",
         "severity": "must-fix", "quote": "Install and wire Supply Air Temperature Sensor (Furnished by Unit Mfr.)"},
        {"system": "RTU", "line": "", "kind": "missing", "say": "The Map Available Points line is missing.", "fix": "Map Available Points Via Mfr. Provided BMS Interface", "severity": "must-fix", "quote": ""},
        {"system": "RTU", "line": "Furnish DX Cooling", "kind": "not-ame-scope", "say": "not a line of this block", "fix": "", "severity": "check", "quote": ""},
        {"system": "XYZ", "line": "", "kind": "count", "say": "no such system", "fix": "", "severity": "check", "quote": ""}],
        "block_notes": [{"system": "RTU", "note": "Shape is right once the verb is fixed."}], "job_note": "A clean small job."}
    report = parse_qc(answer, "m", [RTU])
    assert [f.kind for f in report.findings] == ["ownership", "missing"]
    assert len(report.dropped) == 2 and report.block_notes["RTU"].startswith("Shape is right")
    rows = qc_review_rows(report)
    assert rows[0].system == "RTU" and rows[0].category == "QC" and rows[0].tier == 1 and rows[0].action.startswith("Change to: Install and Wire")
    assert rows[1].action == "Add it: Map Available Points Via Mfr. Provided BMS Interface"


def test_blocks_are_split_whole_under_the_limit():
    parts = split_blocks([RTU] * 5, limit=len(qc_prompt("", [RTU, RTU], "", "")) + 10)
    assert all(len(p) <= 2 for p in parts) and sum(len(p) for p in parts) == 5
```

- [ ] **Step 2: Run the tests to verify they fail**

- [ ] **Step 3: Write `qc.py`** per the interfaces (the prompt lists each block as: header line with key, count and class; its lines numbered; "How AME writes this kind of system:" with the template lines; the tech-hour rule; the ledger entry; the sequence section id), and the judge additions. The review-row action forms are exactly: `Change to: {fix}` when `line` and `fix`; `Remove the line` when `line` and no `fix`; `Add it: {fix}` when no `line`.

- [ ] **Step 4: Run the tests to verify they pass**, plus `tests/test_whole_job.py tests/test_judge.py`, then the full suite.

- [ ] **Step 5: Commit**

```bash
git add src/estimator/writing/qc.py src/estimator/writing/judge.py tests/test_qc.py
git commit -m "feat: the proposal QC pass compares every block with the house shape and lists what is wrong"
```

---

### Task 9: Wiring: the estimate runs the brief, the house check inputs, the QC pass; the Evidence Package shows them

**Files:**
- Modify: `src/estimator/__main__.py`, `src/estimator/evidence/workbook.py`
- Test: `tests/test_estimate.py`, `tests/test_evidence.py` (append)

**Interfaces and behaviour:**
- `__main__._estimate_whole_job`: after `plan = ledger_plan(ledger)`: `brief = job_brief(ledger, plan, templates)`, `owners = shared_owners(ledger, plan)`; each `write_system(...)` call gets `brief=brief, klass=system_class(ledger, system), owned_elsewhere=owners`. After the loop, when every scope is present and not `args.no_qc`: build `QcBlock`s from the plan and scopes (lines = kept lines' text with the quantity total appended where the line has one; `template_lines` from `template_options(system, templates)`; `hours_rule` from `tech_hour_rule`; `ledger_entry` from `entry_text`; `klass` from `system_class`), `report = judge.qc_job(...)` per `split_blocks` part (parts merged into one report); `None` → the summary says the QC request is waiting and the proposal is not written (same as a waiting write request). Then `assemble_job`; `review += qc_review_rows(report)`; `write_evidence(..., ledger=ledger, qc=report, brief=brief)`.
- `--no-qc` and `--no-pictures` flags on `estimate`.
- `write_evidence(..., qc=None, brief=None)`: the "How the job was read" tab prints the brief first (one row "Job brief", wrapped), then the reading rows, then, when `qc` is given, a row per block note and the job note under a heading row "What the QC pass said about the draft". A new tab "Proposal QC" right after "Scope lines": headings `["System", "Line", "Kind", "Severity", "What is wrong", "Change to", "Rests on", DECISION, CHANGE_TO]` with the decision columns via `_decision_columns`, one row per finding; an empty report prints one row "The QC pass found nothing to change."
- `whole_job_lines` adds one line: `"QC: {n} findings ({m} must-fix) on {k} blocks."` or `"QC: waiting for the chat's answer."` or `"QC: skipped (--no-qc)."`.
- `estimator corrections` reads the Proposal QC tab's decision columns the same way as the Scope lines tab (a "keep" on a QC row means the finding is dismissed next run; a "change" with text means the line changes). Check `corrections.py` reads tabs by name and add the tab name to its list; if that is more than a few lines, say so and leave it for a follow-up, noted in the report.

- [ ] **Step 1: Write the failing tests** (append; the `whole_job` fixture's `FakeJudge` gains `qc_job` returning a canned report answer; `FakeJudge.write_system` accepts `brief`, `klass`, `owned_elsewhere`)

```python
# tests/test_estimate.py
def test_the_run_asks_the_qc_pass_and_writes_its_tab(job, tmp_path, capsys, whole_job):
    main(["estimate", str(job), "--out", str(tmp_path / "out"), "--ai", "api"])
    from openpyxl import load_workbook
    book = load_workbook(next((tmp_path / "out").glob("* Evidence Package.xlsx")))
    assert "Proposal QC" in book.sheetnames
    rows = list(book["Proposal QC"].iter_rows(values_only=True))
    assert rows[0][:7] == ("System", "Line", "Kind", "Severity", "What is wrong", "Change to", "Rests on")
    assert any(r[2] == "ownership" for r in rows[1:])
    read = list(book["How the job was read"].iter_rows(values_only=True))
    assert read[1][0] == "Job brief"
    assert "QC: 1 findings (1 must-fix)" in capsys.readouterr().out.replace("1 finding (", "1 findings (")


def test_no_qc_skips_the_pass(job, tmp_path, capsys, whole_job):
    main(["estimate", str(job), "--out", str(tmp_path / "out"), "--ai", "api", "--no-qc"])
    assert "QC: skipped" in capsys.readouterr().out
    assert whole_job[-1].qc_calls == 0
```

```python
# tests/test_evidence.py
def test_the_qc_tab_and_the_brief(tmp_path):
    from estimator.evidence.workbook import write_evidence
    from estimator.writing.qc import QcFinding, QcReport
    report = QcReport((QcFinding("RTU", "Wire Sensor", "ownership", "ships loose", "Install and Wire Sensor", "must-fix", "template"),), {"RTU": "Nearly right."}, "Small job.", "m", ())
    path = write_evidence(tmp_path / "e.xlsx", _catalogue(), systems=[], review_flags=(), qc=report, brief="Job: 26-9999\nWhat the job is\nA school.")
    from openpyxl import load_workbook
    book = load_workbook(path)
    assert "Proposal QC" in book.sheetnames
    rows = list(book["Proposal QC"].iter_rows(values_only=True))
    assert rows[1][:6] == ("RTU", "Wire Sensor", "ownership", "must-fix", "ships loose", "Install and Wire Sensor")
```

- [ ] **Step 2: Run the tests to verify they fail**

- [ ] **Step 3: Implement** as specified (the summary line's singular/plural by number: "1 finding (1 must-fix) on 1 block.").

- [ ] **Step 4: Run the tests to verify they pass**, then the full suite.

- [ ] **Step 5: Commit**

```bash
git add src/estimator/__main__.py src/estimator/evidence/workbook.py src/estimator/corrections.py tests/test_estimate.py tests/test_evidence.py tests/test_assemble.py
git commit -m "feat: estimate shares the job brief, runs the proposal QC pass, and shows both in the Evidence Package"
```

---

### Task 10: The run-job command

**Files:**
- Create: `.claude/skills/run-job/SKILL.md`, `.claude/run-job.json`, `tools/run_job.py`
- Test: `tests/test_run_job_tool.py`

**Interfaces:**
- `.claude/run-job.json`: `{"judge_model": "fable", "writer_model": "fable", "qc_model": "fable", "max_attempts": 3}`. (The estimator can change the models; the skill reads them.)
- `tools/run_job.py` (no AI, no subagents; a helper the skill calls):
  - `python tools/run_job.py status JOB --out OUT [--cache CACHE]`: runs `estimate … --ai chat`, prints the tool's summary, then a JSON block `{"waiting": [{"file": path, "kind": "read_pass|write_system|qc_job", "system": …, "answer_file": …, "attempts": n}], "proposal": path or null}`. Attempts are counted in `OUT/.run-job-attempts.json` by request key.
  - `python tools/run_job.py check ANSWER_FILE REQUEST_FILE`: loads the answer, checks it is JSON with every `required` key of the request's schema at the top level (and the main list is a list); exit 0 or 1 with a plain message.
- `SKILL.md` (frontmatter `name: run-job`, `description: Run an estimate on a job folder in chat mode to completion, handing every AI request to a subagent on the configured model; usable from any session.`, `argument-hint: "<job folder> [--out FOLDER] [--cache FOLDER]"`): the loop in plain steps: (1) `status`; (2) for each waiting request, dispatch one subagent (model from `.claude/run-job.json` by kind) with this prompt: "You are the AI judge of the estimating tool. Read the request file <path>. Its `system_prompt` is your instructions; answer its `prompt` exactly in the JSON shape of its `schema`; write the JSON to its `answer_file` (relative to the repo root), UTF-8; do not spawn subagents; do not run the estimator; reply with one line." The reading passes run one at a time (each depends on the last); write requests may be dispatched up to 4 at once; (3) `check` each answer; a failing answer is deleted and the request re-dispatched up to `max_attempts`; (4) `status` again; stop when `proposal` is set, or when a request fails `max_attempts` times (report it). The skill never pastes request or answer contents into the conversation (NDA). It finishes by naming the three output files.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_run_job_tool.py
import json, subprocess, sys
from pathlib import Path


def test_check_accepts_a_complete_answer_and_rejects_a_missing_key(tmp_path):
    request = tmp_path / "r.json"; answer = tmp_path / "a.json"
    request.write_text(json.dumps({"kind": "read_pass", "schema": {"required": ["facts", "understanding"], "properties": {}}}), encoding="utf-8")
    answer.write_text(json.dumps({"facts": [], "understanding": "ok"}), encoding="utf-8")
    ok = subprocess.run([sys.executable, "tools/run_job.py", "check", str(answer), str(request)], capture_output=True, text=True)
    assert ok.returncode == 0
    answer.write_text(json.dumps({"facts": []}), encoding="utf-8")
    bad = subprocess.run([sys.executable, "tools/run_job.py", "check", str(answer), str(request)], capture_output=True, text=True)
    assert bad.returncode == 1 and "understanding" in bad.stdout + bad.stderr
```

- [ ] **Step 2: Run it to verify it fails**, **Step 3: write the tool, the config and the skill**, **Step 4: run it to verify it passes** (and the full suite), **Step 5: commit**:

```bash
git add .claude/skills/run-job/SKILL.md .claude/run-job.json tools/run_job.py tests/test_run_job_tool.py
git commit -m "feat: /run-job drives a job to completion from any session, handing each AI request to a subagent on the configured model"
```

---

### Task 11: The gate: 26-0193 again, through /run-job

No code. Run `/run-job "out/test-inputs-clean/26-0193, <project folder>" --out out/test/26-0193/shape --cache out/test/.cache` with the judge model set to the strongest available. Then read, and report to the estimator in plain words:

- the VRF block against the Master Template's VRF entry (expected: thermostat per indoor unit, VRF communication wiring once, the integration lines; no "Wire …" list);
- the ERV and duct heater blocks (expected: interlock-only duct heater lines);
- where the damper actuators landed and what the damper block says;
- the Proposal QC tab: how many findings, how many must-fix, and whether they are the kind an estimator would raise;
- the refused and changed lines per block (from the Evidence Package), and whether any refusal looks wrong;
- the summary line counts.

Report findings only; no tuning.
