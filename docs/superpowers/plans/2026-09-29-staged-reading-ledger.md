# Reading in Stages with a Job Ledger — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The AI reads a job in seven passes in the estimator's order, carrying a ledger of facts that lock, and writes each system from its ledger entry instead of the whole dossier.

**Architecture:** A new `estimator.ledger` package holds the fact model, the seed from the existing readers, the seven pass definitions and the runner. The runner asks each pass through the existing `Judge` (cache, chat hand-off, API). A derived `JobPlan` is built from the ledger so the assembler, the checks and the Evidence Package keep working; the plan pass is then deleted.

**Tech Stack:** Python 3.13, dataclasses, pytest 9.1.1. Run everything with `.venv/Scripts/python.exe` (the bare `python` is another project's 3.14).

**Spec:** `docs/superpowers/specs/2026-09-29-staged-reading-ledger-design.md`

## Global Constraints

- Plain language everywhere the estimator reads (prompts, refusals, review rows, tab names). No invented codes beyond the existing ids (`S12`, `I2`, `Q7`, and the new `F17`).
- A fact needs a `source_id` the dossier or ledger knows and a non-empty `quote`; otherwise it is refused and listed, never kept.
- A settled fact's value never changes. A different value becomes a contradiction beside it.
- A contradicted count prints the **higher** value; the block gets a `*` note naming both; the review list gets the row at tier 2 (`TIER_QUANTITY`).
- Nothing in `assets/`, the readers, the catalogue, the dossier text, the GEM, the templates, the proposal or price sheet writers changes.
- Job data is under NDA: tests use hand-made text only, never files from `Jobs/` or the archive.
- Commit after each task; never push. Commit messages end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Run the whole suite before the final task: `.venv/Scripts/python.exe -m pytest -q`.

## Shapes already in the code (read-only reference)

- `estimator.writing.dossier.Dossier`: `job_name, text, images, sources: dict[str,str], families: tuple[FamilyTotal], device_totals: dict[str,int], counts: dict[str,dict], stats, sections: dict[str, (heading, ids)]`. `counts[prefix]` has keys `schedule_rows, quantity_column, plan_placements, riser, distinct_tags`.
- Dossier text: sections start with a line `== N. HEADING ==` for N = 1..8 (`1. JOB`, `2. SEQUENCE OF OPERATION`, `3. POINTS LISTS`, `4. SCHEDULES`, `5. EQUIPMENT COUNTS`, `6. DEVICES ON PLANS`, `7. NOTES`, `8. CONTROLS SPEC HIGHLIGHTS`). Inside section 7, the line `--- 7c PLAN SHEET TEXT ---` starts one `[Sn] <sheet number>, <document> page <p> <title>: <text>` line per mechanical, controls or plumbing sheet. Counts lines look like `[S60] VAV (Variable Air Volume Box): schedule rows 12; QUANTITY column total 12; distinct tags 12; plan placements 14 (M-201 6, M-202 8); riser —. Tags: VAV-1 thru 12.` Device lines look like `[S70] OCC (Occupancy sensor): 21 in all — M-201 10, M-202 11`.
- `estimator.catalogue.sheet_types.Sheet`: `document, page, number, title, discipline, types: tuple[str,...]`. Types include `"Schedules", "Plans", "Details", "Air riser", "Water riser", "Network riser", "Control diagrams", "Diagrams"`. `catalogue.sheets` is a tuple of them.
- `estimator.writing.judge.Judge`: `_answer_with_images(kind, name, system_prompt, prompt, schema, extra, images, ids=None) -> (answer, model) | None` with `last_error`, `mode` (`"api"` | `"chat"`), `waiting`. `_MAIN_LIST` maps an answer kind to the list key its answer must carry; `_fits` checks it. `_for_job` decides whether an old chat request belongs to a job.
- `estimator.writing.whole_job`: `PlannedSystem`, `Family`, `JobPlan`, `WrittenLine`, `WrittenScope`, `write_prompt`, `write_schema`, `parse_scope`, `known_ids`, `_chunks(text, limit)`, `SPLIT_LIMIT`.
- `estimator.writing.assemble`: `assemble_job(catalogue, reading, dossier, plan, scopes, today, templates=None)`, `expand_tags(tags) -> list[str]`, `TIER_QUANTITY`; imports `Block, Item, Run` from `estimator.scope` and `ReviewItem, WrittenSystem` from `estimator.writing.write`.
- `estimator.scope.Item(kind="note", runs=(Run(text=...),))`, `Block.items`, `Block.model_copy(update={...})`.
- `estimator.evidence.workbook.write_evidence(path, catalogue, reading=None, systems=None, review_flags=(), plan=None)`; helpers `_headings(ws, list)`, `_append(ws, row)`, `_widths(ws, list)`, `_table(ws, headings, rows)`.
- Tests fake the API with `tests/test_whole_job.py::FakeClient` (canned replies, records calls) and build small dossiers with `Dossier(...)` as `tests/test_assemble.py::_dossier` does.

---

## File structure

| File | Responsibility |
|---|---|
| `src/estimator/ledger/__init__.py` | package marker, re-exports `Ledger`, `Fact` |
| `src/estimator/ledger/facts.py` | `Fact`, `Contradiction`, `Ledger` (add, settle, contradict, printed_count, table text, save/load) |
| `src/estimator/ledger/seed.py` | `seed(dossier) -> Ledger` from the dossier's counts, devices and sequence sections |
| `src/estimator/ledger/passes.py` | the seven `Pass` definitions, `documents()`, `prompt()`, `schema()`, `apply()`, `LEDGER_PROMPT` |
| `src/estimator/ledger/run.py` | `read_job(judge, dossier, catalogue, save_to) -> Ledger`: seed, ask each pass, split, skip, stop when waiting |
| `src/estimator/ledger/to_plan.py` | `ledger_plan(ledger) -> JobPlan`; `entry_text(system, ledger)`; the `*` count note text |
| `src/estimator/writing/judge.py` | `READ_PASS` kind, `Judge.ask_pass`, `write_system` takes the ledger entry, fact ids and counts |
| `src/estimator/writing/whole_job.py` | `PlannedSystem.count_note/facts`, `WrittenLine.fact_ids`, `write_prompt` ledger text, `write_schema` fact_ids, `ledger_check`; later the plan pass removed |
| `src/estimator/writing/assemble.py` | the `*` count note on the block and its review row |
| `src/estimator/evidence/workbook.py` | "How the job was read" and "Job ledger" tabs |
| `src/estimator/__main__.py` | the estimate command runs the passes, derives the plan, writes the ledger |
| `tests/test_ledger_facts.py`, `tests/test_ledger_seed.py`, `tests/test_ledger_passes.py`, `tests/test_ledger_run.py`, `tests/test_ledger_plan.py` | the new package |
| `tests/test_whole_job.py`, `tests/test_assemble.py`, `tests/test_evidence.py`, `tests/test_estimate.py` | the changed seams |

---

### Task 1: The fact model and the ledger

**Files:**
- Create: `src/estimator/ledger/__init__.py`
- Create: `src/estimator/ledger/facts.py`
- Test: `tests/test_ledger_facts.py`

**Interfaces:**
- Produces:
  - constants `KINDS`, `STAGES`, `SETTLED`, `ADDED`, `CONTRADICTED`
  - `Contradiction(value, source_id, quote, stage)` frozen dataclass
  - `Fact(id, kind, subject, value, source_id, quote, stage, state, contradictions)` frozen dataclass
  - `Ledger(sources: dict[str,str])` with `facts: dict[str, Fact]`, `understanding: dict[str, str]`, `complete: bool`, `stopped_at: str`, `job_name: str`, `refused: dict[str, list[str]]` (per pass)
  - `Ledger.add(kind, subject, value, source_id, quote, stage, state=ADDED) -> Fact` (raises `ValueError` in plain words when kind or stage is unknown, source_id is unknown, or quote is empty)
  - `Ledger.settle(fact_id) -> Fact`
  - `Ledger.contradict(fact_id, value, source_id, quote, stage) -> Fact`
  - `Ledger.printed_count(fact_id) -> int | None`
  - `Ledger.of_kind(kind) -> list[Fact]`, `Ledger.about(subject) -> list[Fact]`, `Ledger.find(kind, subject) -> Fact | None`
  - `Ledger.table(fact_ids=None) -> str` (one line per fact for prompts)
  - `Ledger.to_dict() / Ledger.from_dict(data)`, `Ledger.save(path)`, `Ledger.load(path)`
  - `where_short(where: str) -> str` (a source's place without its parenthetical)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ledger_facts.py
"""The job ledger: facts that lock, contradictions beside them, the higher count printed."""
import json

import pytest

from estimator.ledger.facts import ADDED, CONTRADICTED, SETTLED, Fact, Ledger, where_short

SOURCES = {"S41": "M-601 VAV BOX SCHEDULE, Drawings.pdf page 12", "S60": "equipment counts for VAV (schedules and plans)",
           "S12": "M-201, Drawings.pdf page 3 (sheet text)", "Q7": "sequence section “VAV BOXES”, Specs.pdf page 44"}


def _ledger():
    return Ledger(dict(SOURCES))


def test_a_fact_is_added_with_its_source_quote_and_stage():
    ledger = _ledger()
    fact = ledger.add("count", "VAV", 12, "[S41]", "QUANTITY 12", "schedules", SETTLED)

    assert fact.id == "F1"
    assert fact.source_id == "S41"            # brackets stripped, so every id is stored one way
    assert fact.state == SETTLED
    assert ledger.facts["F1"] is fact
    assert ledger.find("count", "VAV") is fact


def test_a_fact_needs_a_known_source_and_a_quote():
    ledger = _ledger()
    with pytest.raises(ValueError, match="source"):
        ledger.add("count", "VAV", 12, "[S99]", "QUANTITY 12", "schedules")
    with pytest.raises(ValueError, match="quote"):
        ledger.add("count", "VAV", 12, "[S41]", "", "schedules")
    with pytest.raises(ValueError, match="kind"):
        ledger.add("guess", "VAV", 12, "[S41]", "QUANTITY 12", "schedules")
    with pytest.raises(ValueError, match="pass"):
        ledger.add("count", "VAV", 12, "[S41]", "QUANTITY 12", "dreams")


def test_a_settled_fact_never_changes_its_value_a_contradiction_sits_beside_it():
    ledger = _ledger()
    fact = ledger.add("count", "VAV", 12, "[S41]", "QUANTITY 12", "schedules", SETTLED)
    after = ledger.contradict("F1", 14, "[S12]", "VAV-1 … VAV-14", "plans")

    assert after.value == 12
    assert after.state == CONTRADICTED
    assert after.contradictions[0].value == 14
    assert after.contradictions[0].source_id == "S12"
    assert after.contradictions[0].stage == "plans"
    assert ledger.facts["F1"] is after and fact is not after


def test_the_same_value_again_is_not_a_contradiction():
    ledger = _ledger()
    ledger.add("count", "VAV", 12, "[S41]", "QUANTITY 12", "schedules", SETTLED)
    after = ledger.contradict("F1", 12, "[S12]", "twelve boxes", "plans")
    assert after.state == SETTLED and after.contradictions == ()


def test_the_printed_count_is_the_highest_value():
    ledger = _ledger()
    ledger.add("count", "VAV", 12, "[S41]", "QUANTITY 12", "schedules", SETTLED)
    ledger.contradict("F1", 14, "[S12]", "VAV-1 … VAV-14", "plans")
    ledger.contradict("F1", 10, "[S60]", "distinct tags 10", "plans")
    assert ledger.printed_count("F1") == 14
    ledger.add("provider", "RTU", "unit mfr", "[S41]", "controller by unit mfr", "schedules", SETTLED)
    assert ledger.printed_count("F2") is None


def test_settling_an_added_fact():
    ledger = _ledger()
    ledger.add("device", "OCC", 21, "[S60]", "21 in all", "seed")
    assert ledger.facts["F1"].state == ADDED
    assert ledger.settle("F1").state == SETTLED


def test_the_table_lists_each_fact_in_one_line():
    ledger = _ledger()
    ledger.add("count", "VAV", 12, "[S41]", "QUANTITY 12", "schedules", SETTLED)
    ledger.contradict("F1", 14, "[S12]", "VAV-1 … VAV-14", "plans")
    ledger.add("sequence_match", "VAV BOXES", "VAV", "[Q7]", "VAV BOXES", "sequence", SETTLED)
    text = ledger.table()
    assert "F1 count VAV = 12 [S41] “QUANTITY 12” (contradicted, schedules; plans says 14 [S12] “VAV-1 … VAV-14”)" in text
    assert "F2 sequence_match VAV BOXES = VAV [Q7] “VAV BOXES” (settled, sequence)" in text
    assert ledger.table(["F2"]).count("\n") == 0


def test_the_ledger_round_trips_through_json(tmp_path):
    ledger = _ledger()
    ledger.add("count", "VAV", 12, "[S41]", "QUANTITY 12", "schedules", SETTLED)
    ledger.contradict("F1", 14, "[S12]", "VAV-1 … VAV-14", "plans")
    ledger.understanding["schedules"] = "Twelve VAV boxes on one schedule."
    ledger.complete = False
    ledger.stopped_at = "plans"
    ledger.job_name = "26-9999"
    ledger.refused = {"schedules": ["count T = 3 has no quote; left out"]}
    path = tmp_path / "ledger.json"
    ledger.save(path)

    back = Ledger.load(path)
    assert back.facts["F1"] == ledger.facts["F1"]
    assert back.understanding == {"schedules": "Twelve VAV boxes on one schedule."}
    assert back.sources == SOURCES
    assert back.complete is False and back.stopped_at == "plans"
    assert back.job_name == "26-9999" and back.refused == {"schedules": ["count T = 3 has no quote; left out"]}
    assert json.loads(path.read_text(encoding="utf-8"))["facts"][0]["id"] == "F1"


def test_where_short_drops_the_parenthetical():
    assert where_short("M-201, Drawings.pdf page 3 (sheet text)") == "M-201, Drawings.pdf page 3"
    assert where_short("equipment counts for VAV (schedules and plans)") == "equipment counts for VAV"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ledger_facts.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'estimator.ledger'`

- [ ] **Step 3: Write the package**

```python
# src/estimator/ledger/__init__.py
"""The job ledger: what the tool knows about a job, settled pass by pass in the estimator's reading order."""
from estimator.ledger.facts import Fact, Ledger  # noqa: F401
```

```python
# src/estimator/ledger/facts.py
"""The job ledger's facts (design 2026-09-29 §1): each with its kind, subject, value, source, quote, the pass that
settled it and its state. A settled fact never changes its value; a different value from a later pass is a
contradiction kept beside it, and the printed count is the highest value among them.

Ids are stored without brackets ("S41", "Q7", "I2", "F17") however they were given."""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

KINDS = ("family", "unit", "count", "location", "device", "provider", "link", "group", "sequence_match",
         "front_end", "note")
STAGES = ("seed", "schedules", "plans", "details", "risers", "network", "sequence", "spec")
SETTLED, ADDED, CONTRADICTED = "settled", "added", "contradicted"
STATES = (SETTLED, ADDED, CONTRADICTED)

_BRACKETS = re.compile(r"^\s*\[?\s*([A-Za-z]{1,4}\d+[a-z]?)\s*\]?\s*$")
_PAREN = re.compile(r"\s*\([^)]*\)\s*$")


def plain_id(value) -> str:
    """"[S41]" or "S41" -> "S41"; anything else -> ""."""
    match = _BRACKETS.match(str(value or ""))
    return match.group(1) if match else ""


def where_short(where: str) -> str:
    """A source's place without the trailing parenthetical: "M-201, Drawings.pdf page 3"."""
    return _PAREN.sub("", where or "").strip()


@dataclass(frozen=True)
class Contradiction:
    value: object
    source_id: str
    quote: str
    stage: str


@dataclass(frozen=True)
class Fact:
    id: str
    kind: str
    subject: str
    value: object
    source_id: str
    quote: str
    stage: str
    state: str = ADDED
    contradictions: tuple[Contradiction, ...] = ()

    def line(self) -> str:
        """One line for a prompt or a tab: id, kind, subject, value, source, quote, state and pass, then each
        contradiction."""
        head = f"{self.id} {self.kind} {self.subject} = {self.value} [{self.source_id}] “{self.quote}”"
        tail = f"{self.state}, {self.stage}"
        for c in self.contradictions:
            tail += f"; {c.stage} says {c.value} [{c.source_id}] “{c.quote}”"
        return f"{head} ({tail})"


def _number(value) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        text = str(value).strip()
        return int(text) if text.isdigit() else None
    except (TypeError, ValueError):
        return None


class Ledger:
    """The facts of one job, in the order they were added, with the understanding paragraph of each pass."""

    def __init__(self, sources: dict[str, str] | None = None) -> None:
        self.sources: dict[str, str] = dict(sources or {})
        self.facts: dict[str, Fact] = {}
        self.understanding: dict[str, str] = {}
        self.complete: bool = False
        self.stopped_at: str = ""
        self.job_name: str = ""
        self.refused: dict[str, list[str]] = {}     # per pass: what the answer said that could not be kept
        self._n = 0

    # --- adding and changing ------------------------------------------------------------------------

    def knows(self, source_id: str) -> bool:
        sid = plain_id(source_id)
        return bool(sid) and (sid in self.sources or sid in self.facts)

    def add(self, kind: str, subject: str, value, source_id: str, quote: str, stage: str, state: str = ADDED) -> Fact:
        if kind not in KINDS:
            raise ValueError(f"a fact's kind must be one of {', '.join(KINDS)}, not {kind!r}")
        if stage not in STAGES:
            raise ValueError(f"a fact's pass must be one of {', '.join(STAGES)}, not {stage!r}")
        if state not in STATES:
            raise ValueError(f"a fact's state must be one of {', '.join(STATES)}, not {state!r}")
        sid = plain_id(source_id)
        if not self.knows(sid):
            raise ValueError(f"the source {source_id!r} is not one the dossier or the ledger has")
        quote = " ".join(str(quote or "").split())
        if not quote:
            raise ValueError("a fact needs a quote: the words or numbers stating it")
        self._n += 1
        fact = Fact(f"F{self._n}", kind, " ".join(str(subject or "").split()), value, sid, quote, stage, state)
        self.facts[fact.id] = fact
        return fact

    def settle(self, fact_id: str) -> Fact:
        fact = self.facts[plain_id(fact_id) or fact_id]
        if fact.state == ADDED:
            fact = replace(fact, state=SETTLED)
            self.facts[fact.id] = fact
        return fact

    def contradict(self, fact_id: str, value, source_id: str, quote: str, stage: str) -> Fact:
        """A different value for a fact, kept beside it with its own source; the fact's value stays."""
        fact = self.facts[plain_id(fact_id) or fact_id]
        if str(value) == str(fact.value) or any(str(c.value) == str(value) for c in fact.contradictions):
            return fact
        sid = plain_id(source_id)
        if not self.knows(sid):
            raise ValueError(f"the source {source_id!r} is not one the dossier or the ledger has")
        quote = " ".join(str(quote or "").split())
        if not quote:
            raise ValueError("a contradiction needs a quote: the words or numbers stating the other value")
        fact = replace(fact, state=CONTRADICTED,
                       contradictions=fact.contradictions + (Contradiction(value, sid, quote, stage),))
        self.facts[fact.id] = fact
        return fact

    # --- reading ------------------------------------------------------------------------------------

    def printed_count(self, fact_id: str) -> int | None:
        """The highest number among a fact's value and its contradictions; None when none is a number."""
        fact = self.facts[plain_id(fact_id) or fact_id]
        numbers = [n for n in (_number(fact.value), *(_number(c.value) for c in fact.contradictions)) if n is not None]
        return max(numbers) if numbers else None

    def of_kind(self, kind: str) -> list[Fact]:
        return [f for f in self.facts.values() if f.kind == kind]

    def about(self, subject: str) -> list[Fact]:
        key = subject.casefold()
        return [f for f in self.facts.values() if f.subject.casefold() == key]

    def find(self, kind: str, subject: str) -> Fact | None:
        key = subject.casefold()
        return next((f for f in self.facts.values() if f.kind == kind and f.subject.casefold() == key), None)

    def table(self, fact_ids=None) -> str:
        facts = self.facts.values() if fact_ids is None else [self.facts[plain_id(i) or i] for i in fact_ids
                                                                if (plain_id(i) or i) in self.facts]
        return "\n".join(f.line() for f in facts)

    # --- saving ---------------------------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {"version": 1, "job_name": self.job_name, "sources": self.sources, "complete": self.complete,
                "stopped_at": self.stopped_at, "understanding": self.understanding, "refused": self.refused,
                "facts": [asdict(f) for f in self.facts.values()]}

    @classmethod
    def from_dict(cls, data: dict) -> "Ledger":
        ledger = cls(data.get("sources") or {})
        ledger.complete = bool(data.get("complete"))
        ledger.stopped_at = str(data.get("stopped_at") or "")
        ledger.job_name = str(data.get("job_name") or "")
        ledger.understanding = dict(data.get("understanding") or {})
        ledger.refused = {k: list(v) for k, v in (data.get("refused") or {}).items()}
        for raw in data.get("facts") or []:
            fact = Fact(raw["id"], raw["kind"], raw["subject"], raw["value"], raw["source_id"], raw["quote"],
                        raw["stage"], raw.get("state", ADDED),
                        tuple(Contradiction(**c) for c in raw.get("contradictions") or ()))
            ledger.facts[fact.id] = fact
            ledger._n = max(ledger._n, int(fact.id[1:]))
        return ledger

    def save(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path) -> "Ledger":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ledger_facts.py -q`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add src/estimator/ledger/__init__.py src/estimator/ledger/facts.py tests/test_ledger_facts.py
git commit -m "feat: the job ledger, facts that lock with contradictions beside them

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: Seeding the ledger from the dossier

**Files:**
- Create: `src/estimator/ledger/seed.py`
- Test: `tests/test_ledger_seed.py`

**Interfaces:**
- Consumes: `Ledger`, `SETTLED`, `ADDED` from Task 1; `Dossier` fields `text, sources, families, counts, device_totals, sections`.
- Produces: `seed(dossier) -> Ledger`; `dossier_sections(text) -> dict[int, str]` (section number to its text, heading line included); `sheet_text_lines(text) -> list[tuple[str, str, str]]` (source id, sheet number or "", the whole line) from the `--- 7c PLAN SHEET TEXT ---` block.

Seed rules (design §1.3). The seed takes only what the dossier's own lines carry an id for: families, counts, tags, device totals and sequence headings. Locations, provider notes and plant groupings are left for the plans, schedules and risers passes to settle, since the dossier has no line of its own to cite for them.
- one `family` fact per `dossier.counts` prefix: subject the prefix, value the kind from `dossier.families` (else "equipment"), source the counts line's id, quote the counts line up to its first `.`; **settled** when `schedule_rows > 0`, else **added**.
- one `count` fact per prefix: value the `quantity_column` when it is a number > 0, else `schedule_rows` when > 0 (both **settled**); else `plan_placements` when > 0, else `distinct_tags` when > 0 (both **added**); no fact when all are 0.
- one `unit` fact per prefix that has tags: value the `Tags:` text of the counts line, **added**.
- one `device` fact per device line of section 6: subject the label, value the total, quote the line, **added**.
- one `sequence_match` fact per `dossier.sections` entry: subject the heading, value `""` (matched to nothing yet), source the Q id, quote the heading, **added**.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ledger_seed.py
"""The ledger's seed: what the readers already know, before the AI reads a pass."""
from types import SimpleNamespace

from estimator.ledger.facts import ADDED, SETTLED
from estimator.ledger.seed import dossier_sections, seed, sheet_text_lines
from estimator.writing.dossier import Dossier

TEXT = """JOB DOSSIER — 26-9999
Everything controls-relevant.

== 1. JOB ==
[S1] 26-9999 Somerville HS. Controls: new BACnet system.

== 2. SEQUENCE OF OPERATION ==
--- [Q1] VAV BOXES ---
[S2] Each VAV box shall maintain space temperature.
--- [Q2] EXHAUST FANS ---
[S3] EF-1 shall run with RTU-1.

== 3. POINTS LISTS ==
(No points list found in the documents.)

== 4. SCHEDULES ==
[S4] VAV BOX SCHEDULE (M-601, page 12): VAV-1 | 500 CFM ; VAV-2 | 500 CFM

== 5. EQUIPMENT COUNTS ==
[S5] VAV (Variable Air Volume Box): schedule rows 12; QUANTITY column total 12; distinct tags 12; plan placements 14 (M-201 6, M-202 8); riser —. Tags: VAV-1 thru 12.
[S6] EF (Exhaust Fan): schedule rows 0; QUANTITY column total —; distinct tags 2; plan placements 2 (M-201 2); riser —. Tags: EF-1, EF-2.
[S7] T (type code on a schedule): schedule rows 0; QUANTITY column total —; distinct tags 0; plan placements 0; riser —.

== 6. DEVICES ON PLANS ==
[S8] OCC (Occupancy sensor): 21 in all — M-201 10, M-202 11

== 7. NOTES ==
[S9] M-201 KEY NOTES 3: Provide damper actuator by ATC.
--- 7c PLAN SHEET TEXT ---
(Each sheet's own text.)
[S10] M-201, Drawings.pdf page 3 FIRST FLOOR PLAN: VAV-1 VAV-2 OCC
[S11] M-601, Drawings.pdf page 12 SCHEDULES: VAV BOX SCHEDULE
[S12] Drawings.pdf page 30: no sheet number here

== 8. CONTROLS SPEC HIGHLIGHTS ==
[S13] 23 09 00 1.2: Honeywell WEBs.
"""
SOURCES = {f"S{n}": f"place {n}" for n in range(1, 14)} | {"Q1": "sequence section “VAV BOXES”", "Q2": "sequence section “EXHAUST FANS”"}
FAMILIES = (SimpleNamespace(kind="Variable Air Volume Box", prefix="VAV", scheduled=12, tags="VAV-1 thru 12", flags=()),
            SimpleNamespace(kind="Exhaust Fan", prefix="EF", scheduled=0, tags="EF-1, EF-2", flags=()))
COUNTS = {"VAV": {"schedule_rows": 12, "quantity_column": 12, "plan_placements": 14, "riser": 0, "distinct_tags": 12},
          "EF": {"schedule_rows": 0, "quantity_column": None, "plan_placements": 2, "riser": 0, "distinct_tags": 2},
          "T": {"schedule_rows": 0, "quantity_column": None, "plan_placements": 0, "riser": 0, "distinct_tags": 0}}


def _dossier(**kw):
    values = dict(job_name="26-9999", text=TEXT, images=(), sources=SOURCES, families=FAMILIES, device_totals={"OCC": 21},
                  counts=COUNTS, stats={}, sections={"Q1": ("VAV BOXES", ("S2",)), "Q2": ("EXHAUST FANS", ("S3",))})
    values.update(kw)
    return Dossier(**values)


def test_the_sections_are_split_by_their_headings():
    sections = dossier_sections(TEXT)
    assert sorted(sections) == [1, 2, 3, 4, 5, 6, 7, 8]
    assert sections[5].startswith("== 5. EQUIPMENT COUNTS ==")
    assert "[S7] T" in sections[5] and "[S8] OCC" not in sections[5]


def test_sheet_text_lines_carry_their_sheet_numbers():
    lines = sheet_text_lines(TEXT)
    assert [(sid, number) for sid, number, _ in lines] == [("S10", "M-201"), ("S11", "M-601"), ("S12", "")]
    assert lines[0][2].startswith("[S10] M-201, Drawings.pdf page 3")


def test_a_scheduled_family_seeds_a_settled_family_and_count():
    ledger = seed(_dossier())
    family = ledger.find("family", "VAV")
    count = ledger.find("count", "VAV")
    assert family.value == "Variable Air Volume Box" and family.state == SETTLED and family.source_id == "S5"
    assert family.quote == "VAV (Variable Air Volume Box): schedule rows 12; QUANTITY column total 12; distinct tags 12; plan placements 14 (M-201 6, M-202 8); riser —"
    assert count.value == 12 and count.state == SETTLED and count.stage == "seed"
    assert ledger.find("unit", "VAV").value == "VAV-1 thru 12"


def test_a_plan_only_family_seeds_added_facts_with_the_plan_count():
    ledger = seed(_dossier())
    assert ledger.find("family", "EF").state == ADDED
    count = ledger.find("count", "EF")
    assert count.value == 2 and count.state == ADDED


def test_a_family_with_nothing_counted_gets_no_count_fact():
    ledger = seed(_dossier())
    assert ledger.find("family", "T") is not None
    assert ledger.find("count", "T") is None
    assert ledger.find("unit", "T") is None


def test_devices_and_sequence_headings_are_seeded_as_added():
    ledger = seed(_dossier())
    occ = ledger.find("device", "OCC")
    assert occ.value == 21 and occ.source_id == "S8" and occ.state == ADDED
    heading = ledger.find("sequence_match", "VAV BOXES")
    assert heading.value == "" and heading.source_id == "Q1" and heading.state == ADDED


def test_the_seed_keeps_the_dossier_sources_and_names_the_job():
    ledger = seed(_dossier())
    assert ledger.sources == SOURCES and ledger.job_name == "26-9999"
    assert ledger.understanding == {} and ledger.complete is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ledger_seed.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'estimator.ledger.seed'`

- [ ] **Step 3: Write the seed**

```python
# src/estimator/ledger/seed.py
"""The ledger's seed (design 2026-09-29 §1.3): the facts the readers already found, written into the ledger before
the AI reads a single pass. A schedule's own count is settled; a count from the plans or the tags alone is added,
for the schedules pass to confirm. Every seed fact cites the dossier line it comes from."""
from __future__ import annotations

import re

from estimator.ledger.facts import ADDED, SETTLED, Ledger

_SECTION = re.compile(r"^== (\d)\. [A-Z ]+ ==\s*$")
_ID_LINE = re.compile(r"^\[(S\d+)\] (.*)$")
_SHEET_TEXT_START = "--- 7c PLAN SHEET TEXT ---"
_SHEET_LINE = re.compile(r"^\[(S\d+)\] (?:(?P<number>[A-Z][A-Z0-9.\-]*\d[A-Z0-9.\-]*), )?")
_COUNT_LINE = re.compile(r"^\[(S\d+)\] (?P<prefix>[A-Z0-9/\-]+) \((?P<kind>[^)]*)\): (?P<body>.*)$")
_DEVICE_LINE = re.compile(r"^\[(S\d+)\] (?P<label>\S+) \((?P<name>[^)]*)\): (?P<total>\d+) in all")
_TAGS = re.compile(r"\bTags: (.+?)\.(?: By location|\s*Reading notes|$)")


def dossier_sections(text: str) -> dict[int, str]:
    """{section number: its text, heading line first} for the dossier's "== N. HEADING ==" sections."""
    found: dict[int, list[str]] = {}
    current = None
    for line in (text or "").splitlines():
        match = _SECTION.match(line)
        if match:
            current = int(match.group(1))
            found[current] = [line]
        elif current is not None:
            found[current].append(line)
    return {n: "\n".join(lines) for n, lines in found.items()}


def sheet_text_lines(text: str) -> list[tuple[str, str, str]]:
    """(source id, sheet number or "", the line) for each sheet's own text in section 7's 7c block."""
    section = dossier_sections(text).get(7, "")
    if _SHEET_TEXT_START not in section:
        return []
    block = section.split(_SHEET_TEXT_START, 1)[1]
    lines = []
    for line in block.splitlines():
        match = _SHEET_LINE.match(line)
        if match:
            lines.append((match.group(1), match.group("number") or "", line))
    return lines


def _count_lines(sections: dict[int, str]) -> dict[str, tuple[str, str, str]]:
    """prefix -> (source id, the quote: the line up to its first full stop, the whole line)."""
    found = {}
    for line in sections.get(5, "").splitlines():
        match = _COUNT_LINE.match(line)
        if match:
            body = match.group("body")
            head = f"{match.group('prefix')} ({match.group('kind')}): {body.split('.')[0]}"
            found[match.group("prefix")] = (match.group(1), head, line)
    return found


def _positive(value) -> int | None:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def seed(dossier) -> Ledger:
    ledger = Ledger(dict(dossier.sources))
    ledger.job_name = str(getattr(dossier, "job_name", "") or "")
    sections = dossier_sections(dossier.text)
    kinds = {f.prefix: f.kind for f in getattr(dossier, "families", ()) or ()}
    count_lines = _count_lines(sections)

    for prefix, counts in (getattr(dossier, "counts", None) or {}).items():
        if prefix not in count_lines:
            continue                      # no dossier line to cite: no fact
        sid, quote, line = count_lines[prefix]
        rows = _positive(counts.get("schedule_rows"))
        ledger.add("family", prefix, kinds.get(prefix) or "equipment", sid, quote, "seed",
                   SETTLED if rows else ADDED)
        settled = _positive(counts.get("quantity_column")) or rows
        added = _positive(counts.get("plan_placements")) or _positive(counts.get("distinct_tags"))
        if settled:
            ledger.add("count", prefix, settled, sid, quote, "seed", SETTLED)
        elif added:
            ledger.add("count", prefix, added, sid, quote, "seed", ADDED)
        tags = _TAGS.search(line)
        if tags:
            ledger.add("unit", prefix, tags.group(1).strip(), sid, f"Tags: {tags.group(1).strip()}", "seed", ADDED)

    for line in sections.get(6, "").splitlines():
        match = _DEVICE_LINE.match(line)
        if match:
            ledger.add("device", match.group("label"), int(match.group("total")), match.group(1), line.split("] ", 1)[1],
                       "seed", ADDED)

    for qid, (heading, _ids) in (getattr(dossier, "sections", None) or {}).items():
        if ledger.knows(qid):
            ledger.add("sequence_match", heading, "", qid, heading, "seed", ADDED)
    return ledger
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ledger_seed.py -q`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add src/estimator/ledger/seed.py tests/test_ledger_seed.py
git commit -m "feat: the ledger is seeded from the dossier's counts, devices and sequence headings

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: The seven passes: documents, prompt, schema, and applying an answer

**Files:**
- Create: `src/estimator/ledger/passes.py`
- Test: `tests/test_ledger_passes.py`

**Interfaces:**
- Consumes: `Ledger`, `Fact`, `SETTLED`, `ADDED`, `plain_id` (Task 1); `dossier_sections`, `sheet_text_lines` (Task 2); `estimator.writing.whole_job.known_ids`, `images_text`.
- Produces:
  - `Pass(name, title, settles, may_add, sections, sheet_types, with_images, instructions)` frozen dataclass; `PASSES: tuple[Pass, ...]` in order; `pass_named(name) -> Pass`
  - `LEDGER_PROMPT: str` (the system prompt shared by every pass)
  - `documents(pass_, dossier, catalogue) -> str` (empty when the pass has nothing to read)
  - `prompt(pass_, ledger, text, images=()) -> str`
  - `schema() -> dict`
  - `apply(pass_, ledger, answer, known: frozenset[str]) -> list[str]` (the refusals, in plain words; the ledger is changed in place)

Sheet types per pass: plans `("Plans",)`; details `("Details", "Control diagrams", "Diagrams")`; risers `("Air riser", "Water riser")`; network `("Network riser",)`. Dossier sections per pass: schedules `(4, 5)` with images; plans `(6, 7)` where section 7 is its notes (before the 7c marker) plus the 7c lines of plan sheets; details, risers, network: their 7c lines only, network also section 1; sequence `(2, 3)`; spec `(1, 8)`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ledger_passes.py
"""The seven reading passes: what each reads, what it may settle, and how its answer changes the ledger."""
from types import SimpleNamespace

from estimator.ledger.facts import ADDED, CONTRADICTED, SETTLED, Ledger
from estimator.ledger.passes import LEDGER_PROMPT, PASSES, apply, documents, pass_named, prompt, schema
from estimator.ledger.seed import seed
from tests.test_ledger_seed import SOURCES, _dossier

SHEETS = (SimpleNamespace(document="Drawings.pdf", page=3, number="M-201", title="FIRST FLOOR PLAN", discipline="Mechanical",
                          types=("Plans",)),
          SimpleNamespace(document="Drawings.pdf", page=12, number="M-601", title="SCHEDULES", discipline="Mechanical",
                          types=("Schedules",)))
CATALOGUE = SimpleNamespace(sheets=SHEETS)


def test_the_passes_are_in_the_estimators_order():
    assert [p.name for p in PASSES] == ["schedules", "plans", "details", "risers", "network", "sequence", "spec"]
    assert pass_named("risers").settles == ("link", "group", "device")
    assert pass_named("plans").may_add == ("family", "unit", "count")
    assert pass_named("schedules").may_add == ()


def test_each_pass_reads_only_its_own_documents():
    dossier = _dossier()
    assert "[S4] VAV BOX SCHEDULE" in documents(pass_named("schedules"), dossier, CATALOGUE)
    assert "[S2] Each VAV box" not in documents(pass_named("schedules"), dossier, CATALOGUE)
    plans = documents(pass_named("plans"), dossier, CATALOGUE)
    assert "[S8] OCC" in plans and "[S9] M-201 KEY NOTES" in plans and "[S10] M-201" in plans
    assert "[S11] M-601" not in plans                 # a schedule sheet's text is not the plans pass's
    assert documents(pass_named("risers"), dossier, CATALOGUE) == ""     # no riser sheets in this job
    sequence = documents(pass_named("sequence"), dossier, CATALOGUE)
    assert "[Q1] VAV BOXES" in sequence and "No points list" in sequence
    spec = documents(pass_named("spec"), dossier, CATALOGUE)
    assert "[S13]" in spec and "[S1]" in spec


def test_the_prompt_carries_the_understanding_the_ledger_and_the_documents():
    ledger = seed(_dossier())
    ledger.understanding["schedules"] = "Twelve VAV boxes and two exhaust fans."
    text = prompt(pass_named("plans"), ledger, "[S8] OCC (Occupancy sensor): 21 in all — M-201 10, M-202 11")
    assert text.index("Job: 26-9999") < text.index("What the earlier passes understood") < text.index("F1 family VAV")
    assert text.index("F1 family VAV") < text.index("The documents for this pass") < text.index("[S8] OCC")
    assert "Twelve VAV boxes and two exhaust fans." in text
    assert "seen on plans, not scheduled" in text          # the plans pass's own instructions
    assert "You are an HVAC controls estimator at AME" in LEDGER_PROMPT
    assert schema()["required"] == ["facts", "contradictions", "confirmations", "understanding"]


def _answer(**overrides):
    answer = {"facts": [], "contradictions": [], "confirmations": [], "understanding": "A small school."}
    answer.update(overrides)
    return answer


def _known(ledger):
    return frozenset(ledger.sources) | frozenset(ledger.facts)


def test_a_pass_settles_the_kinds_it_owns_and_adds_the_rest():
    ledger = seed(_dossier())
    refused = apply(pass_named("plans"), ledger, _answer(facts=[
        {"kind": "location", "subject": "VAV", "value": "floors 1 and 2", "source_id": "[S10]", "quote": "FIRST FLOOR PLAN: VAV-1 VAV-2"},
        {"kind": "family", "subject": "GD", "value": "Gravity damper", "source_id": "[S10]", "quote": "GD-1 beside EF-1"},
    ]), _known(ledger))

    assert refused == []
    assert ledger.find("location", "VAV").state == SETTLED and ledger.find("location", "VAV").stage == "plans"
    assert ledger.find("family", "GD").state == ADDED          # the plans pass may only add a family


def test_a_kind_the_pass_may_not_touch_is_refused():
    ledger = seed(_dossier())
    refused = apply(pass_named("plans"), ledger, _answer(facts=[
        {"kind": "front_end", "subject": "mode", "value": "new-system", "source_id": "[S10]", "quote": "new BMS"}]),
        _known(ledger))
    assert refused == ["the plans pass may not write a front_end fact (mode = new-system); left out"]
    assert ledger.find("front_end", "mode") is None


def test_a_fact_with_an_unknown_source_or_no_quote_is_refused():
    ledger = seed(_dossier())
    refused = apply(pass_named("plans"), ledger, _answer(facts=[
        {"kind": "location", "subject": "VAV", "value": "floor 1", "source_id": "[S99]", "quote": "VAV-1"},
        {"kind": "location", "subject": "EF", "value": "roof", "source_id": "[S10]", "quote": ""}]), _known(ledger))
    assert refused == ["location VAV = floor 1 cites [S99], which the documents do not have; left out",
                       "location EF = roof has no quote; left out"]


def test_a_different_value_for_a_settled_fact_becomes_a_contradiction():
    ledger = seed(_dossier())
    refused = apply(pass_named("plans"), ledger, _answer(facts=[
        {"kind": "count", "subject": "VAV", "value": 14, "source_id": "[S10]", "quote": "VAV-1 … VAV-14"}]), _known(ledger))
    count = ledger.find("count", "VAV")
    assert refused == []
    assert count.value == 12 and count.state == CONTRADICTED
    assert count.contradictions[0].value == 14 and count.contradictions[0].stage == "plans"
    assert len(ledger.of_kind("count")) == 2       # VAV and EF: no second VAV count was added


def test_contradictions_and_confirmations_by_id():
    ledger = seed(_dossier())
    ef = ledger.find("count", "EF")
    refused = apply(pass_named("schedules"), ledger, _answer(
        contradictions=[{"fact_id": "F1", "value": "Chilled Beam", "source_id": "[S4]", "quote": "VAV BOX SCHEDULE"},
                        {"fact_id": "F99", "value": 3, "source_id": "[S4]", "quote": "three"}],
        confirmations=[ef.id, "F98"]), _known(ledger))
    assert ledger.facts["F1"].state == CONTRADICTED
    assert ledger.find("count", "EF").state == SETTLED
    assert refused == ["a contradiction names F99, which the ledger does not have; left out",
                       "a confirmation names F98, which the ledger does not have; left out"]


def test_the_understanding_is_kept_per_pass():
    ledger = seed(_dossier())
    apply(pass_named("schedules"), ledger, _answer(understanding="  Twelve VAV boxes.  "), _known(ledger))
    assert ledger.understanding == {"schedules": "Twelve VAV boxes."}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ledger_passes.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'estimator.ledger.passes'`

- [ ] **Step 3: Write the passes**

```python
# src/estimator/ledger/passes.py
"""The seven reading passes (design 2026-09-29 §2): each reads its own documents from the dossier, sees the ledger
so far and the earlier passes' understanding, and answers with facts, contradictions, confirmations and its own
understanding. `apply` turns an answer into ledger changes and refuses, in plain words, whatever cannot be
trusted: a kind the pass may not write, a source the documents do not have, a fact with no quote. A different
value for a settled fact is never a change: it is a contradiction beside the fact."""
from __future__ import annotations

from dataclasses import dataclass

from estimator.ledger.facts import ADDED, KINDS, SETTLED, Ledger, plain_id
from estimator.ledger.seed import dossier_sections, sheet_text_lines

SHEET_TEXT_MARK = "--- 7c PLAN SHEET TEXT ---"

LEDGER_PROMPT = """\
You are an HVAC controls estimator at AME. You are reading the bid set of a building controls job the way you \
always do: in stages, one kind of document at a time, settling what you know as you go. Schedules first, then the \
plans, the details, the air and water risers, the network riser, the sequence of operation, and the specification.

You are given the job ledger: every fact settled so far, each with its id (F1, F2 …), its source id in the \
documents ([S12], [Q7], [I2]) and the words that state it. A settled fact is settled: you never change it. When \
this pass's documents say something different, give a contradiction with the fact's id, the other value, its \
source and its words, and say so in your understanding. When they agree with a fact that is only "added", \
confirm it by id.

Add every new fact this pass's documents state, with its source id and the words or numbers stating it, copied \
exactly. Never invent a number, a tag or a provider: a fact with no words behind it is refused. Only write the \
kinds of fact this pass is allowed to; the pass's instructions say which.

End with your understanding of the job so far, in plain words, two to six sentences: what the building is, what \
equipment it has, how the systems fit together, who provides what, and what is still open. The next pass reads \
it first."""


@dataclass(frozen=True)
class Pass:
    name: str
    title: str
    settles: tuple[str, ...]        # kinds this pass writes as settled
    may_add: tuple[str, ...]        # kinds it may write only as added (flagged later)
    sections: tuple[int, ...]       # dossier sections it reads whole
    sheet_types: tuple[str, ...]    # sheet-text lines (7c) it reads, by the sheet's type
    with_images: bool
    instructions: str

    @property
    def kinds(self) -> tuple[str, ...]:
        return self.settles + self.may_add


PASSES: tuple[Pass, ...] = (
    Pass("schedules", "Schedules", ("family", "unit", "count", "provider"), (), (4, 5), (), True,
         "Settle the equipment list: every family on the schedules, its tags, its count (a QUANTITY column, else the "
         "rows) and, from the notes under each schedule, who provides the unit controller (\"unit mfr\", \"AME\", "
         "\"owner\", or the words used). A schedule that is a picture is given as an image: read it. Nothing later "
         "can add a scheduled family, so be complete."),
    Pass("plans", "Plans", ("location", "device"), ("family", "unit", "count"), (6, 7), ("Plans",), False,
         "For each family already in the ledger, settle where its units are (floors, zones, rooms) and the devices "
         "around them: sensors, thermostats, damper actuators, and the keynotes that add controls scope. Equipment "
         "on the plans that no schedule lists may only be added, with the subject \"seen on plans, not scheduled\" "
         "in its quote's words; it is flagged later. Give the count you can see, citing the sheet."),
    Pass("details", "Details and control diagrams", ("device", "link"), (), (), ("Details", "Control diagrams", "Diagrams"), False,
         "For units already in the ledger, settle what the details and control diagrams add: control valves, damper "
         "actuators, fire and smoke damper integration, expansion tank sensors, anything touching a scheduled "
         "unit. Write nothing about equipment the ledger does not hold."),
    Pass("risers", "Air and water risers", ("link", "group", "device"), ("family", "unit", "count"), (), ("Air riser", "Water riser"), False,
         "Settle how the systems fit together: which unit serves which (a link: subject the served unit, value the "
         "serving unit), the plant loop (a group: subject the plant's name, value the families in it, comma "
         "separated), and the sensors on the risers (pressure, differential pressure, stair pressurisation). "
         "Equipment on a riser that neither the schedule nor the plans showed may only be added, quoting the riser."),
    Pass("network", "Network riser", ("provider", "link"), (), (1,), ("Network riser",), False,
         "Settle who provides the backbone (fibre or Ethernet), the network switches, the server, the workstation "
         "or laptop, and every integration callout (VFDs, plumbing, electrical, lighting): a provider fact per item, "
         "subject the item, value the provider in the documents' words."),
    Pass("sequence", "Sequence of operation and points list", ("sequence_match", "note"), ("family", "unit", "count"), (2, 3), (), False,
         "Match each sequence section (its Q id) to the family or group in the ledger it describes: a "
         "sequence_match fact whose subject is the section's heading and whose value is that family's prefix or "
         "the group's name, citing the section. A section naming equipment the ledger does not hold may add it "
         "only when the section itself states a count, quoting it; otherwise write a note fact with the subject "
         "\"named in sequence, not found on drawings\". Notes are also for alternates (subject \"alternate\", value "
         "\"add\" or \"deduct\" and the family), exceptions (subject \"exception\", value the one-line exception in "
         "capitals) and questions for the estimator (subject \"question\")."),
    Pass("spec", "Controls specification", ("front_end", "provider", "note"), (), (1, 8), (), False,
         "Settle the front end: a front_end fact with subject \"mode\" and value \"new-system\" or "
         "\"extend-existing\" (and one with subject \"existing_name\" when extending), one per front end line the "
         "spec calls for (subject \"line\"), one per clarification for the client (subject \"note\", starting "
         "\"**\"); the manufacturer (provider, subject \"manufacturer\"); warranty, training and services as "
         "provider facts in the spec's words."),
)


def pass_named(name: str) -> Pass:
    for p in PASSES:
        if p.name == name:
            return p
    raise KeyError(f"no reading pass named {name!r}")


# --- the documents a pass reads --------------------------------------------------------------------------------

def _types_by_number(catalogue) -> dict[str, tuple[str, ...]]:
    found: dict[str, tuple[str, ...]] = {}
    for sheet in getattr(catalogue, "sheets", ()) or ():
        if sheet.number:
            found.setdefault(sheet.number, tuple(sheet.types or ()))
    return found


def documents(pass_, dossier, catalogue) -> str:
    """The dossier text this pass reads: its sections whole, then the sheet-text lines of its sheet types. "" when
    there is nothing for it in this job."""
    sections = dossier_sections(dossier.text)
    parts = []
    for n in pass_.sections:
        text = sections.get(n, "")
        if n == 7 and SHEET_TEXT_MARK in text:
            text = text.split(SHEET_TEXT_MARK, 1)[0].rstrip()
        if text.strip():
            parts.append(text)
    if pass_.sheet_types:
        types = _types_by_number(catalogue)
        wanted = set(pass_.sheet_types)
        lines = [line for _sid, number, line in sheet_text_lines(dossier.text)
                 if number and wanted & set(types.get(number, ()))]
        if lines:
            parts.append("\n".join([f"== SHEET TEXT: {', '.join(pass_.sheet_types)} ==", *lines]))
    return "\n\n".join(parts)


# --- the question ----------------------------------------------------------------------------------------------

def prompt(pass_, ledger, text: str, images=()) -> str:
    from estimator.writing.whole_job import images_text
    job = getattr(ledger, "job_name", "") or "(unnamed job)"
    understood = "\n".join(f"- after the {name} pass: {words}" for name, words in ledger.understanding.items()) or "(nothing yet)"
    kinds = ", ".join(pass_.settles) + (f"; may only add: {', '.join(pass_.may_add)}" if pass_.may_add else "")
    return "\n\n".join(filter(None, [
        f"Job: {job}\nThis is the {pass_.title} pass ({pass_.name}).",
        f"What the earlier passes understood:\n{understood}",
        f"The job ledger so far (id, kind, subject = value [source] “quote” (state, pass)):\n{ledger.table() or '(empty)'}",
        f"This pass settles these kinds of fact: {kinds}.\n{pass_.instructions}",
        f"The documents for this pass, each paragraph with its source id:\n{text}",
        images_text(list(images)) if images else "",
    ]))


def schema() -> dict:
    text = {"type": "string"}
    fact = {"type": "object",
            "properties": {"kind": {"type": "string", "enum": list(KINDS)}, "subject": text,
                           "value": {"anyOf": [{"type": "string"}, {"type": "integer"}]},
                           "source_id": text, "quote": text},
            "required": ["kind", "subject", "value", "source_id", "quote"], "additionalProperties": False}
    contradiction = {"type": "object",
                     "properties": {"fact_id": text, "value": {"anyOf": [{"type": "string"}, {"type": "integer"}]},
                                    "source_id": text, "quote": text},
                     "required": ["fact_id", "value", "source_id", "quote"], "additionalProperties": False}
    return {"type": "object",
            "properties": {"facts": {"type": "array", "items": fact},
                           "contradictions": {"type": "array", "items": contradiction},
                           "confirmations": {"type": "array", "items": text},
                           "understanding": text},
            "required": ["facts", "contradictions", "confirmations", "understanding"], "additionalProperties": False}


# --- applying an answer ---------------------------------------------------------------------------------------

def _text(value) -> str:
    return " ".join(str(value if value is not None else "").split())


def _value(value):
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return value
    text = _text(value)
    return int(text) if text.isdigit() else text


def apply(pass_, ledger: Ledger, answer: dict, known: frozenset[str]) -> list[str]:
    """Write the pass's answer into the ledger; the refusals, in plain words."""
    refused: list[str] = []
    prompt_ids = {plain_id(k) or k for k in known}

    def known_source(sid: str) -> bool:
        return bool(sid) and (sid in prompt_ids or ledger.knows(sid))

    for raw in answer.get("facts") or []:
        if not isinstance(raw, dict):
            continue
        kind, subject, value = _text(raw.get("kind")), _text(raw.get("subject")), _value(raw.get("value"))
        sid, quote = plain_id(raw.get("source_id")), _text(raw.get("quote"))
        label = f"{kind} {subject} = {value}"
        if kind not in pass_.kinds:
            refused.append(f"the {pass_.name} pass may not write a {kind or 'nameless'} fact ({subject} = {value}); left out")
            continue
        if not known_source(sid):
            refused.append(f"{label} cites [{_text(raw.get('source_id')) or '?'}], which the documents do not have; left out")
            continue
        if not quote:
            refused.append(f"{label} has no quote; left out")
            continue
        held = ledger.find(kind, subject)
        if held is not None and held.state != ADDED and str(held.value) != str(value):
            ledger.contradict(held.id, value, sid, quote, pass_.name)
            continue
        if held is not None and str(held.value) == str(value):
            if kind in pass_.settles:
                ledger.settle(held.id)
            continue
        state = SETTLED if kind in pass_.settles else ADDED
        if held is not None and held.state == ADDED:      # a seed candidate with another value: kept beside it,
            ledger.contradict(held.id, value, sid, quote, pass_.name)     # the higher count prints
            continue
        ledger.add(kind, subject, value, sid, quote, pass_.name, state)

    for raw in answer.get("contradictions") or []:
        if not isinstance(raw, dict):
            continue
        fid = plain_id(raw.get("fact_id")) or _text(raw.get("fact_id"))
        sid, quote = plain_id(raw.get("source_id")), _text(raw.get("quote"))
        if fid not in ledger.facts:
            refused.append(f"a contradiction names {fid or '?'}, which the ledger does not have; left out")
            continue
        if not known_source(sid):
            refused.append(f"the contradiction of {fid} cites [{_text(raw.get('source_id')) or '?'}], which the documents do not have; left out")
            continue
        if not quote:
            refused.append(f"the contradiction of {fid} has no quote; left out")
            continue
        ledger.contradict(fid, _value(raw.get("value")), sid, quote, pass_.name)

    for raw in answer.get("confirmations") or []:
        fid = plain_id(raw) or _text(raw)
        if fid not in ledger.facts:
            refused.append(f"a confirmation names {fid or '?'}, which the ledger does not have; left out")
            continue
        ledger.settle(fid)

    ledger.understanding[pass_.name] = _text(answer.get("understanding"))
    return refused
```

Note for the implementer: the `plans` pass prompt must contain the words `seen on plans, not scheduled`, which the instructions above do.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ledger_passes.py -q`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add src/estimator/ledger/passes.py tests/test_ledger_passes.py
git commit -m "feat: the seven reading passes, each with its documents, prompt and answer checks

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: The judge asks a pass

**Files:**
- Modify: `src/estimator/writing/judge.py` (constants near line 60-66; `_for_job` near line 538; `PLAN_JOB, WRITE_SYSTEM` near line 966; new method after `write_system`)
- Test: `tests/test_whole_job.py` (append)

**Interfaces:**
- Produces: `READ_PASS = "read_pass"`; `Judge.ask_pass(name, system_prompt, prompt, schema, images=(), extra=None) -> (answer: dict, model: str) | None` (None with `last_error` set; in chat mode writes a request and sets `waiting`).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_whole_job.py`)

```python
# --- the reading passes ask through the judge ------------------------------------------------------------

from estimator.writing.judge import READ_PASS


def test_a_pass_is_asked_and_its_answer_cached(tmp_path):
    reply = {"facts": [], "contradictions": [], "confirmations": [], "understanding": "A school."}
    client = FakeClient(_response(reply))
    judge = _judge(tmp_path, client)

    got = judge.ask_pass("the schedules pass", "SYSTEM", "PROMPT", {"type": "object"})
    assert got == (reply, "claude-opus-5-5")
    assert client.calls[0]["system"] == "SYSTEM"
    assert judge.calls == 1
    again = judge.ask_pass("the schedules pass", "SYSTEM", "PROMPT", {"type": "object"})
    assert again == got and judge.cached == 1 and len(client.calls) == 1


def test_an_answer_without_a_facts_list_is_unusable(tmp_path):
    judge = _judge(tmp_path, FakeClient(_response({"understanding": "nothing else"})))
    assert judge.ask_pass("the plans pass", "SYSTEM", "PROMPT", {"type": "object"}) is None
    assert "could not be read" in judge.last_error


def test_in_chat_mode_a_pass_waits_as_a_request_of_its_own_kind(tmp_path):
    judge = Judge(tmp_path / "cache", mode="chat", job="26-9999 Somerville")
    assert judge.ask_pass("the schedules pass", "SYSTEM", "Job: 26-9999 Somerville\nPROMPT", {"type": "object"}) is None
    assert judge.waiting == 1
    request = json.loads(next(judge.requests_dir.glob("*.json")).read_text(encoding="utf-8"))
    assert request["kind"] == READ_PASS and request["system"] == "the schedules pass" and request["job"] == "26-9999 Somerville"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_whole_job.py -q -k "pass_is_asked or facts_list or waits_as_a_request"`
Expected: FAIL with `ImportError: cannot import name 'READ_PASS'`

- [ ] **Step 3: Add the kind and the method**

In `src/estimator/writing/judge.py`:

1. Change the kinds block (lines 63-65) to:

```python
CHOOSE, COMPOSE = "choose", "compose"
READ_PASS = "read_pass"
KINDS = (CHOOSE, COMPOSE)
_MAIN_LIST = {CHOOSE: "choices", COMPOSE: "lines", READ_PASS: "facts"}   # the list an answer of each kind must carry
```

2. Near line 966 the whole-job kinds register themselves with `KINDS = KINDS + (PLAN_JOB, WRITE_SYSTEM)` and `_MAIN_LIST.update({PLAN_JOB: "systems", WRITE_SYSTEM: "lines"})`. Add `READ_PASS` to that `KINDS` line too: `KINDS = KINDS + (PLAN_JOB, WRITE_SYSTEM, READ_PASS)`. Its list key is already in `_MAIN_LIST` from step 1.

3. In `_for_job`, after the `PLAN_JOB` branch, add:

```python
    if request.get("kind") == READ_PASS:
        return bool(number) and number.group(0) in prompt[:400]      # a pass prompt starts "Job: <name>"
```

4. After `write_system` in `class Judge`, add:

```python
    def ask_pass(self, name: str, system_prompt: str, prompt: str, schema: dict, images=(), extra: dict | None = None
                 ) -> tuple[dict, str] | None:
        """One reading pass of the job ledger (estimator.ledger.passes): the answer and the model, or None with
        `last_error` set (in chat mode, a request written for the chat and `waiting` counted)."""
        from estimator.writing import whole_job as wj
        images = list(images or ())
        return self._answer_with_images(READ_PASS, name, system_prompt, prompt, schema,
                                        {**(extra or {}), "images": wj.images_listing(images)}, images)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_whole_job.py tests/test_judge.py -q`
Expected: all pass (the three new tests among them)

- [ ] **Step 5: Commit**

```bash
git add src/estimator/writing/judge.py tests/test_whole_job.py
git commit -m "feat: the judge asks a reading pass, cached and handed to the chat like its other questions

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: The runner: seed, seven passes, splitting, skipping, stopping

**Files:**
- Create: `src/estimator/ledger/run.py`
- Test: `tests/test_ledger_run.py`

**Interfaces:**
- Consumes: `seed`, `PASSES`, `documents`, `prompt`, `schema`, `apply`, `LEDGER_PROMPT`, `Judge.ask_pass`, `whole_job._chunks`, `whole_job.SPLIT_LIMIT`, `whole_job.known_ids`.
- Produces: `read_job(judge, dossier, catalogue, save_to: Path | None = None, limit: int = SPLIT_LIMIT) -> Ledger` with `ledger.complete`, `ledger.stopped_at` (the pass that got no answer, "" when complete), `ledger.refused: dict[str, list[str]]` (per pass), `ledger.job_name`.

Rules:
- A pass with empty `documents()` is skipped: `understanding[name] = "nothing to read: no <title> in this job"`.
- Text over `limit` characters is cut with `_chunks(text, limit)`; each chunk is asked in turn, named "the <title> pass (part i of n)", and applied in turn, so a later chunk sees the earlier chunk's facts.
- The schedules pass passes `dossier.images` (its `with_images`).
- When any ask returns None, the runner saves what it has, sets `stopped_at`, and returns without asking later passes (each depends on the last).
- The ledger is saved to `save_to` after every pass when `save_to` is given.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ledger_run.py
"""The runner: the ledger is seeded, each pass asked in order, long passes split, empty passes skipped, and the
run stops at the first pass with no answer."""
import json
from types import SimpleNamespace

from estimator.ledger.facts import SETTLED
from estimator.ledger.run import read_job
from estimator.writing.judge import Judge
from tests.test_ledger_passes import CATALOGUE
from tests.test_ledger_seed import _dossier
from tests.test_whole_job import FakeClient, _response


def _reply(understanding="ok", facts=()):
    return _response({"facts": list(facts), "contradictions": [], "confirmations": [], "understanding": understanding})


def test_every_pass_with_documents_is_asked_in_order_and_the_rest_skipped(tmp_path):
    client = FakeClient(*[_reply(f"pass {n}") for n in range(1, 8)])
    judge = Judge(tmp_path / "cache", model="test-model", client=client)
    ledger = read_job(judge, _dossier(), CATALOGUE, save_to=tmp_path / "ledger.json")

    asked = [c["messages"][0]["content"] for c in client.calls]
    names = [next(line for line in (t if isinstance(t, str) else t[0]["text"]).splitlines() if line.startswith("This is the "))
             for t in asked]
    assert names == ["This is the Schedules pass (schedules).", "This is the Plans pass (plans).",
                     "This is the Sequence of operation and points list pass (sequence).",
                     "This is the Controls specification pass (spec)."]
    assert ledger.understanding["details"] == "nothing to read: no Details and control diagrams in this job"
    assert ledger.understanding["risers"] == "nothing to read: no Air and water risers in this job"
    assert ledger.understanding["network"] == "nothing to read: no Network riser in this job"
    assert ledger.complete is True and ledger.stopped_at == ""
    assert ledger.job_name == "26-9999"
    saved = json.loads((tmp_path / "ledger.json").read_text(encoding="utf-8"))
    assert saved["complete"] is True and saved["understanding"]["spec"] == "pass 4"


def test_a_passs_facts_are_in_the_ledger_and_its_refusals_kept(tmp_path):
    client = FakeClient(_reply("schedules", [
        {"kind": "provider", "subject": "VAV controller", "value": "AME", "source_id": "[S4]", "quote": "VAV BOX SCHEDULE"},
        {"kind": "link", "subject": "VAV", "value": "RTU-1", "source_id": "[S4]", "quote": "VAV BOX SCHEDULE"}]),
        _reply(), _reply(), _reply())
    judge = Judge(tmp_path / "cache", model="test-model", client=client)
    ledger = read_job(judge, _dossier(), CATALOGUE)
    fact = ledger.find("provider", "VAV controller")
    assert fact.value == "AME" and fact.state == SETTLED and fact.stage == "schedules"
    assert ledger.refused["schedules"] == ["the schedules pass may not write a link fact (VAV = RTU-1); left out"]


def test_the_run_stops_at_the_first_pass_without_an_answer(tmp_path):
    judge = Judge(tmp_path / "cache", mode="chat", job="26-9999", handoff_dir=tmp_path / "chat")
    ledger = read_job(judge, _dossier(), CATALOGUE, save_to=tmp_path / "ledger.json")
    assert ledger.complete is False and ledger.stopped_at == "schedules"
    assert judge.waiting == 1                       # only the first pass was asked: the next depends on its answer
    assert ledger.find("count", "VAV").value == 12  # the seed is there
    assert (tmp_path / "ledger.json").exists()


def test_a_long_pass_is_split_and_each_part_applied_in_turn(tmp_path):
    long_text = _dossier().text.replace("[S4] VAV BOX SCHEDULE", "[S4] " + "x" * 1500 + " VAV BOX SCHEDULE")
    client = FakeClient(_reply("part one", [{"kind": "provider", "subject": "VAV controller", "value": "AME", "source_id": "[S4]", "quote": "VAV BOX SCHEDULE"}]),
                        _reply("part two"), _reply(), _reply(), _reply())
    judge = Judge(tmp_path / "cache", model="test-model", client=client)
    ledger = read_job(judge, _dossier(text=long_text), CATALOGUE, limit=1000)
    first, second = client.calls[0], client.calls[1]
    assert "part 1 of 2" not in str(first)          # the part number is in the request name, not the prompt
    assert ledger.understanding["schedules"] == "part two"
    assert ledger.find("provider", "VAV controller") is not None
    assert "F" in str(second["messages"][0]["content"])   # the second part saw the first part's facts
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ledger_run.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'estimator.ledger.run'`

- [ ] **Step 3: Write the runner**

```python
# src/estimator/ledger/run.py
"""The reading run (design 2026-09-29 §2): seed the ledger, then ask each pass in the estimator's order through the
judge, carrying the ledger between them. A pass with nothing to read is skipped and says so. A pass too long for one
request is cut at line ends and its parts asked and applied in turn. The run stops at the first pass with no
answer (in chat mode, the request is waiting), because every later pass reads this one's understanding."""
from __future__ import annotations

from pathlib import Path

from estimator.ledger.passes import LEDGER_PROMPT, PASSES, apply, documents, prompt, schema
from estimator.ledger.seed import seed


def read_job(judge, dossier, catalogue, save_to: Path | None = None, limit: int | None = None):
    from estimator.writing import whole_job as wj
    limit = limit or wj.SPLIT_LIMIT
    ledger = seed(dossier)
    images = list(getattr(dossier, "images", ()) or ())
    known_all = wj.known_ids(dossier.text, images)

    def save() -> None:
        if save_to is not None:
            ledger.save(save_to)

    for pass_ in PASSES:
        text = documents(pass_, dossier, catalogue)
        if not text.strip():
            ledger.understanding[pass_.name] = f"nothing to read: no {pass_.title} in this job"
            save()
            continue
        parts = wj._chunks(text, limit) if len(text) > limit else [text]
        pass_images = images if pass_.with_images else []
        refused: list[str] = []
        for n, part in enumerate(parts, start=1):
            name = f"the {pass_.title} pass" + (f" (part {n} of {len(parts)})" if len(parts) > 1 else "")
            extra = {"pass": pass_.name} | ({"part": f"{n} of {len(parts)}"} if len(parts) > 1 else {})
            got = judge.ask_pass(name, LEDGER_PROMPT, prompt(pass_, ledger, part, pass_images), schema(), pass_images, extra)
            if got is None:
                ledger.stopped_at = pass_.name
                ledger.complete = False
                ledger.refused[pass_.name] = refused
                save()
                return ledger
            known = wj.known_ids(part, pass_images) | frozenset(ledger.facts) | known_all
            refused += apply(pass_, ledger, got[0], known)
        ledger.refused[pass_.name] = refused
        save()
    ledger.complete = True
    ledger.stopped_at = ""
    save()
    return ledger
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ledger_run.py tests/test_ledger_facts.py -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add src/estimator/ledger/run.py tests/test_ledger_run.py
git commit -m "feat: the reading run asks the seven passes in order, splitting long ones and stopping when one waits

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: From the ledger to the systems the writer takes

**Files:**
- Modify: `src/estimator/writing/whole_job.py` (`PlannedSystem` near line 283)
- Create: `src/estimator/ledger/to_plan.py`
- Test: `tests/test_ledger_plan.py`

**Interfaces:**
- Consumes: `Ledger`, `Fact`, `where_short`; `PlannedSystem`, `Family`, `JobPlan` from `whole_job`; `expand_tags` from `assemble`.
- Produces:
  - `PlannedSystem` gains two defaulted fields: `count_note: str = ""` (the `*` note when its count is contradicted) and `facts: tuple[str, ...] = ()` (the ledger fact ids it rests on).
  - `ledger_plan(ledger) -> JobPlan` with `model="ledger"`.
  - `count_note(ledger, fact) -> str` — `"*Qty. (14) per M-201, Drawings.pdf page 3; equipment counts for VAV lists (12)."` built from the highest value's source and the fact's own.
  - `entry_text(system, ledger) -> str` — the system's facts as ledger table lines, for the write prompt.
  - `system_counts(system, ledger) -> frozenset[int]` — every number a line for this system may carry: each count and device fact's printed count, and the values inside their contradictions.

Rules:
- One system per `group` fact: key the group name squashed, header the group name, kind the group name, `group` the name, `families` one `Family` per prefix named in the group's value (comma separated), tags the union; quantity `None`; the families' counts from their count facts.
- One system per `family` fact not in any group: key the prefix, header `"{kind} {tags}"` (tags from the unit fact, else the prefix), kind the family's value, tags `expand_tags([unit value])` when a unit fact exists else `(prefix,)`.
- quantity = `printed_count` of the family's count fact; `quantity_source`/`quantity_quote` from the fact when its own value is the printed one, else from the contradiction holding the printed value; `count_note` when the fact is contradicted.
- `sequence_section` = the source id (`"[Q7]"`, comma-joined) of every `sequence_match` fact whose value equals the prefix or the group name (case-insensitive); `sequence_sources` the same ids; `schedule_sources` = `("[S60]",)` of the count fact.
- exception = value of a `note` fact with subject `"exception"` whose value names the prefix (case-insensitive substring); alternate = `"add"`/`"deduct"` from a note with subject `"alternate"` whose value names the prefix.
- why = `"From the job ledger: {n} facts."`; `facts` = ids of every fact whose subject equals the prefix (or a group's prefixes/name) plus the matched sequence facts.
- A family fact whose state is `added` (never confirmed) still becomes a system, with why `"Seen on the drawings but on no schedule; confirm it exists."`.
- front_end: mode from the `front_end` fact with subject `"mode"` (`""` when none), `existing_name`, `lines` (subject `"line"` values in order), `notes` (subject `"note"`), sources the bracketed ids of those facts.
- unresolved = the values of `note` facts with subject `"question"`.
- Systems in ledger order; groups placed where their first family was.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ledger_plan.py
"""The ledger becomes the systems the writer takes: one per family or group, the higher count printed with its
note, each system carrying the ids of the facts it rests on."""
from estimator.ledger.facts import SETTLED, Ledger
from estimator.ledger.to_plan import count_note, entry_text, ledger_plan, system_counts
from estimator.writing.whole_job import JobPlan, PlannedSystem

SOURCES = {"S5": "equipment counts for VAV (schedules and plans)", "S6": "equipment counts for CH (schedules and plans)",
           "S7": "equipment counts for CHWP (schedules and plans)", "S10": "M-201, Drawings.pdf page 3 (sheet text)",
           "S13": "23 09 00, Specs.pdf page 4", "Q1": "sequence section “VAV BOXES”, Specs.pdf page 44",
           "Q2": "sequence section “CHILLED WATER PLANT”, Specs.pdf page 50"}


def _ledger():
    ledger = Ledger(SOURCES)
    ledger.add("family", "VAV", "Variable Air Volume Box", "[S5]", "VAV: schedule rows 12", "seed", SETTLED)
    ledger.add("count", "VAV", 12, "[S5]", "QUANTITY column total 12", "seed", SETTLED)
    ledger.add("unit", "VAV", "VAV-1 thru 12", "[S5]", "Tags: VAV-1 thru 12", "seed", SETTLED)
    ledger.add("family", "CH", "Chiller", "[S6]", "CH: schedule rows 2", "seed", SETTLED)
    ledger.add("count", "CH", 2, "[S6]", "schedule rows 2", "seed", SETTLED)
    ledger.add("family", "CHWP", "Chilled Water Pump", "[S7]", "CHWP: schedule rows 2", "seed", SETTLED)
    ledger.add("count", "CHWP", 2, "[S7]", "schedule rows 2", "seed", SETTLED)
    ledger.add("group", "Chilled Water Plant", "CH, CHWP", "[Q2]", "CHILLED WATER PLANT", "risers", SETTLED)
    ledger.add("sequence_match", "VAV BOXES", "VAV", "[Q1]", "VAV BOXES", "sequence", SETTLED)
    ledger.add("sequence_match", "CHILLED WATER PLANT", "Chilled Water Plant", "[Q2]", "CHILLED WATER PLANT", "sequence", SETTLED)
    ledger.add("device", "OCC", 21, "[S10]", "OCC 21 in all", "plans", SETTLED)
    ledger.add("front_end", "mode", "new-system", "[S13]", "provide a new BMS", "spec", SETTLED)
    ledger.add("front_end", "line", "Provide a new Niagara N4 front end", "[S13]", "Niagara N4", "spec", SETTLED)
    ledger.add("note", "question", "Is the existing BMS kept?", "[S13]", "existing BMS", "spec", SETTLED)
    return ledger


def test_families_and_groups_become_systems_in_ledger_order():
    plan = ledger_plan(_ledger())
    assert isinstance(plan, JobPlan) and plan.model == "ledger"
    vav, plant = plan.systems
    assert vav.key == "VAV" and vav.header == "Variable Air Volume Box VAV-1 thru 12" and vav.kind == "Variable Air Volume Box"
    assert vav.tags == tuple(f"VAV-{n}" for n in range(1, 13))
    assert vav.quantity == 12 and vav.quantity_source == "[S5]" and vav.quantity_quote == "QUANTITY column total 12"
    assert vav.sequence_section == "[Q1]" and vav.sequence_sources == ("[Q1]",) and vav.schedule_sources == ("[S5]",)
    assert vav.count_note == "" and "F1" in vav.facts and "F9" in vav.facts
    assert plant.group == "Chilled Water Plant" and plant.key == "Chilled Water Plant" and plant.quantity is None
    assert [f.header for f in plant.families] == ["Chiller CH", "Chilled Water Pump CHWP"]
    assert [f.quantity for f in plant.families] == [2, 2]
    assert plant.sequence_section == "[Q2]"


def test_the_higher_count_is_printed_with_its_note():
    ledger = _ledger()
    ledger.contradict("F2", 14, "[S10]", "VAV-1 … VAV-14", "plans")
    plan = ledger_plan(ledger)
    vav = plan.systems[0]
    assert vav.quantity == 14 and vav.quantity_source == "[S10]" and vav.quantity_quote == "VAV-1 … VAV-14"
    assert vav.count_note == "*Qty. (14) per M-201, Drawings.pdf page 3; equipment counts for VAV lists (12)."
    assert count_note(ledger, ledger.facts["F2"]) == vav.count_note
    assert system_counts(vav, ledger) == frozenset({12, 14})


def test_front_end_and_questions_come_from_the_ledger():
    plan = ledger_plan(_ledger())
    assert plan.front_end == {"mode": "new-system", "existing_name": "", "lines": ["Provide a new Niagara N4 front end"],
                              "notes": [], "sources": ["[S13]"]}
    assert plan.unresolved == ("Is the existing BMS kept?",)


def test_exceptions_alternates_and_unconfirmed_families():
    ledger = _ledger()
    ledger.add("note", "exception", "EXCEPTION TO ANY WORK WITH Qty (12) VAV-1 THRU 12 - INTEGRAL THERMOSTAT", "[Q1]", "integral thermostat", "sequence", SETTLED)
    ledger.add("family", "HPAC", "Apartment Heat Pump", "[S10]", "seen on plans, not scheduled: HPAC", "plans")
    ledger.add("count", "HPAC", 120, "[S10]", "HPAC x120", "plans")
    ledger.add("note", "alternate", "add: HPAC", "[Q1]", "priced per apartment", "sequence", SETTLED)
    plan = ledger_plan(ledger)
    vav, plant, hpac = plan.systems
    assert vav.exception.startswith("EXCEPTION TO ANY WORK WITH Qty (12) VAV-1")
    assert hpac.alternate == "add" and hpac.quantity == 120 and hpac.tags == ("HPAC",)
    assert hpac.why == "Seen on the drawings but on no schedule; confirm it exists."


def test_the_entry_text_lists_the_systems_facts_only():
    ledger = _ledger()
    vav = ledger_plan(ledger).systems[0]
    text = entry_text(vav, ledger)
    assert "F1 family VAV" in text and "F9 sequence_match VAV BOXES" in text
    assert "F4 family CH" not in text


def test_planned_system_defaults_keep_old_callers_working():
    system = PlannedSystem("K", "H", "kind", ("T",), 1, "[S1]", "one", (), (), "", "", "", "why")
    assert system.count_note == "" and system.facts == ()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ledger_plan.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'estimator.ledger.to_plan'`

- [ ] **Step 3: Add the fields and write the module**

In `src/estimator/writing/whole_job.py`, `class PlannedSystem`, after `families: tuple[Family, ...] = ()` add:

```python
    count_note: str = ""                       # "*Qty. (14) per …; … lists (12)." when the ledger's count is contradicted
    facts: tuple[str, ...] = ()                # the ledger fact ids it rests on (F1, F9, …)
```

```python
# src/estimator/ledger/to_plan.py
"""From the ledger to the systems the writer takes (design 2026-09-29 §3): one PlannedSystem per family or group,
in ledger order, its quantity the printed (highest) count with a "*" note when the count is contradicted, and the
ids of the facts it rests on. The writer, the checks and the Evidence Package read a JobPlan as before."""
from __future__ import annotations

import re

from estimator.ledger.facts import CONTRADICTED, Fact, Ledger, where_short
from estimator.writing.whole_job import Family, JobPlan, PlannedSystem

_SPACES = re.compile(r"\s+")


def _squash(text) -> str:
    return _SPACES.sub(" ", str(text or "")).strip()


def _bracket(sid: str) -> str:
    return f"[{sid}]" if sid else ""


def _printed(ledger: Ledger, fact: Fact) -> tuple[int | None, str, str]:
    """(the printed count, its source id in brackets, its quote): the highest value's."""
    printed = ledger.printed_count(fact.id)
    if printed is None:
        return None, _bracket(fact.source_id), fact.quote
    if str(fact.value) == str(printed):
        return printed, _bracket(fact.source_id), fact.quote
    other = next(c for c in fact.contradictions if str(c.value) == str(printed))
    return printed, _bracket(other.source_id), other.quote


def count_note(ledger: Ledger, fact: Fact) -> str:
    """The "*" note under a system whose count is contradicted: the printed count and its place, then each other
    count and its place. "" when the fact is not contradicted or none of its values is a number."""
    if fact.state != CONTRADICTED:
        return ""
    printed, sid, _quote = _printed(ledger, fact)
    if printed is None:
        return ""
    others = [(fact.value, fact.source_id)] + [(c.value, c.source_id) for c in fact.contradictions]
    others = [(v, s) for v, s in others if str(v) != str(printed)]
    place = where_short(ledger.sources.get(sid.strip("[]"), sid))
    rest = "; ".join(f"{where_short(ledger.sources.get(s, s))} lists ({v})" for v, s in others)
    return f"*Qty. ({printed}) per {place}; {rest}."


def _tags(ledger: Ledger, prefix: str) -> tuple[str, ...]:
    from estimator.writing.assemble import expand_tags
    unit = ledger.find("unit", prefix)
    if unit is None or not _squash(unit.value):
        return (prefix,)
    return tuple(expand_tags([_squash(unit.value)]) or (prefix,))


def _matches(ledger: Ledger, name: str) -> list[Fact]:
    key = name.casefold()
    return [f for f in ledger.of_kind("sequence_match") if _squash(f.value).casefold() == key]


def _note(ledger: Ledger, subject: str, prefix: str) -> str:
    key = prefix.casefold()
    for fact in ledger.of_kind("note"):
        if fact.subject.casefold() == subject and key in _squash(fact.value).casefold():
            return _squash(fact.value)
    return ""


def _alternate(ledger: Ledger, prefix: str) -> str:
    value = _note(ledger, "alternate", prefix).casefold()
    return "add" if value.startswith("add") else "deduct" if value.startswith("deduct") else ""


def _family(ledger: Ledger, fact: Fact) -> tuple[Family, list[str]]:
    prefix = fact.subject
    tags = _tags(ledger, prefix)
    unit = ledger.find("unit", prefix)
    header = f"{_squash(fact.value)} {_squash(unit.value) if unit else prefix}".strip()
    count = ledger.find("count", prefix)
    quantity, source, quote = _printed(ledger, count) if count else (None, "", "")
    ids = [f.id for f in ledger.about(prefix)]
    return Family(header, tags, quantity, source, quote), ids


def _system(ledger: Ledger, fact: Fact) -> PlannedSystem:
    prefix = fact.subject
    family, ids = _family(ledger, fact)
    count = ledger.find("count", prefix)
    matched = _matches(ledger, prefix)
    sequence = tuple(_bracket(m.source_id) for m in matched)
    note = count_note(ledger, count) if count else ""
    why = ("Seen on the drawings but on no schedule; confirm it exists." if fact.state == "added"
           else f"From the job ledger: {len(ids) + len(matched)} facts.")
    return PlannedSystem(key=prefix, header=family.header, kind=_squash(fact.value), tags=family.tags,
                         quantity=family.quantity, quantity_source=family.quantity_source,
                         quantity_quote=family.quantity_quote, sequence_sources=sequence,
                         schedule_sources=(_bracket(count.source_id),) if count else (), group="",
                         alternate=_alternate(ledger, prefix), exception=_note(ledger, "exception", prefix), why=why,
                         sequence_section=", ".join(sequence), families=(), count_note=note,
                         facts=tuple(ids + [m.id for m in matched]))


def _group_system(ledger: Ledger, group: Fact, members: list[Fact]) -> PlannedSystem:
    families, ids = [], [group.id]
    for member in members:
        family, member_ids = _family(ledger, member)
        families.append(family)
        ids += member_ids
    matched = _matches(ledger, group.subject)
    sequence = tuple(_bracket(m.source_id) for m in matched)
    tags = tuple(t for f in families for t in f.tags)
    notes = [count_note(ledger, ledger.find("count", m.subject)) for m in members if ledger.find("count", m.subject)]
    return PlannedSystem(key=_squash(group.subject), header=_squash(group.subject), kind=_squash(group.subject),
                         tags=tags, quantity=None, quantity_source="", quantity_quote="", sequence_sources=sequence,
                         schedule_sources=tuple(_bracket(ledger.find("count", m.subject).source_id) for m in members
                                                if ledger.find("count", m.subject)),
                         group=_squash(group.subject), alternate="", exception="",
                         why=f"From the job ledger: {len(ids) + len(matched)} facts.",
                         sequence_section=", ".join(sequence), families=tuple(families),
                         count_note=" ".join(n for n in notes if n), facts=tuple(ids + [m.id for m in matched]))


def _front_end(ledger: Ledger) -> dict:
    facts = ledger.of_kind("front_end")
    by = lambda subject: [f for f in facts if f.subject.casefold() == subject]      # noqa: E731
    mode = next((_squash(f.value) for f in by("mode")), "")
    return {"mode": mode if mode in ("new-system", "extend-existing") else "",
            "existing_name": next((_squash(f.value) for f in by("existing_name")), ""),
            "lines": [_squash(f.value) for f in by("line")],
            "notes": [_squash(f.value) for f in by("note")],
            "sources": sorted({_bracket(f.source_id) for f in facts if f.source_id})}


def ledger_plan(ledger: Ledger) -> JobPlan:
    groups = ledger.of_kind("group")
    member_of: dict[str, Fact] = {}
    for group in groups:
        for prefix in (p.strip() for p in _squash(group.value).split(",")):
            if prefix:
                member_of.setdefault(prefix.casefold(), group)
    systems: list[PlannedSystem] = []
    placed: set[str] = set()
    for fact in ledger.of_kind("family"):
        group = member_of.get(fact.subject.casefold())
        if group is None:
            systems.append(_system(ledger, fact))
        elif group.id not in placed:
            placed.add(group.id)
            members = [f for f in ledger.of_kind("family") if member_of.get(f.subject.casefold()) is group]
            systems.append(_group_system(ledger, group, members))
    questions = tuple(_squash(f.value) for f in ledger.of_kind("note") if f.subject.casefold() == "question")
    return JobPlan(systems=tuple(systems), front_end=_front_end(ledger), unresolved=questions, model="ledger")


def entry_text(system: PlannedSystem, ledger: Ledger) -> str:
    """The system's ledger entry: its facts, one line each, for the write prompt."""
    return ledger.table(list(getattr(system, "facts", ()) or ()))


def system_counts(system: PlannedSystem, ledger: Ledger) -> frozenset[int]:
    """Every number a scope line for this system may carry: its count and device facts' values, printed or not."""
    numbers: set[int] = set()
    for fid in getattr(system, "facts", ()) or ():
        fact = ledger.facts.get(fid)
        if fact is None or fact.kind not in ("count", "device"):
            continue
        for value in (fact.value, *(c.value for c in fact.contradictions)):
            if isinstance(value, int) and not isinstance(value, bool):
                numbers.add(value)
            elif str(value).strip().isdigit():
                numbers.add(int(str(value).strip()))
    return frozenset(numbers)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ledger_plan.py tests/test_whole_job.py tests/test_assemble.py -q`
Expected: all pass (the `PlannedSystem` defaults leave the old constructors working)

- [ ] **Step 5: Commit**

```bash
git add src/estimator/ledger/to_plan.py src/estimator/writing/whole_job.py tests/test_ledger_plan.py
git commit -m "feat: the ledger becomes the planned systems, the higher count printed with its note

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: Writing from the ledger entry: fact ids on every line, ledger counts only

**Files:**
- Modify: `src/estimator/writing/whole_job.py` (`WrittenLine` ~line 311, `write_prompt` ~line 766, `write_schema` ~line 781, `parse_scope` ~line 866; new `ledger_check`)
- Modify: `src/estimator/writing/judge.py` (`Judge.write_system` ~line 466)
- Test: `tests/test_whole_job.py` (append)

**Interfaces:**
- `WrittenLine.fact_ids: tuple[str, ...] = ()`.
- `write_prompt(system, evidence_text, images, options, examples, style_text, hours_rule="", image_ids=None, ledger_text="")`: when `ledger_text` is given, a block `"The job ledger's facts for this system. Every line you write names, in fact_ids, the ids of the facts it rests on; a count in a line is one of these facts' counts:\n{ledger_text}"` goes right after the system text, before the evidence.
- `write_schema()`: the line object gains `"fact_ids": {"type": "array", "items": {"type": "string"}}` in its properties and in `required`.
- `parse_scope` reads `raw.get("fact_ids")` into `fact_ids` (bracket-stripped with `plain_id`, unknown-shaped entries dropped).
- `ledger_check(scope, facts: frozenset[str], counts: frozenset[int]) -> WrittenScope`: when `facts` is non-empty, a line naming none of them is refused as `"“{text}” names no fact of this system's ledger entry; left out"`; when `counts` is non-empty, a line whose `quantity` is not in `counts` is refused as `"“{text}” gives {n}, which is no count in this system's ledger entry; left out"`. Both are appended to `refused`, and the kept lines replace `lines`. With empty `facts` and `counts` the scope comes back unchanged.
- `Judge.write_system(..., ledger_text: str = "", facts=(), counts=())`: passes `ledger_text` to the prompt and runs `ledger_check` on the parsed scope.
- Past-proposal blocks: `write_prompt` already leaves `examples` out (the GEM decides the wording), so the spec's "wording only, after the facts" rule holds without a change; nothing new shows old jobs to the writer.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_whole_job.py`)

```python
# --- writing from the ledger entry ------------------------------------------------------------------------

from estimator.writing.whole_job import ledger_check, parse_scope, write_prompt, write_schema
from estimator.writing.style import load_house_style


def _scope_answer(*lines):
    return {"lines": list(lines), "client_notes": [], "review_notes": [], "tech_hours": None,
            "quick_scan": {}, "explanation": "", "contradictions": [], "misc_responsibilities": [],
            "exclusions": [], "qc": []}


def _line(text, quantity=None, fact_ids=("F1",)):
    return {"text": text, "reference": "each VAV box shall maintain", "flag": "", "flag_text": "", "quantity": quantity,
            "quote": "twelve boxes" if quantity is not None else "", "source_id": "[S2]", "depth": 1,
            "fact_ids": list(fact_ids)}


def test_the_write_prompt_puts_the_ledger_entry_before_the_evidence():
    system = PlannedSystem(**{k: v for k, v in _system().items()})
    text = write_prompt(system, "[S2] evidence", [], [], [], "", ledger_text="F1 family VAV = Variable Air Volume Box [S5] “x” (settled, seed)")
    assert text.index("The job ledger's facts for this system") < text.index("[S2] evidence")
    assert "names, in fact_ids, the ids of the facts it rests on" in text
    assert "fact_ids" in write_schema()["properties"]["lines"]["items"]["required"]


def test_parse_scope_reads_the_fact_ids():
    style = load_house_style()
    scope = parse_scope(_scope_answer(_line("Furnish and Install Space Temperature Sensor", fact_ids=["[F1]", "F9", "nonsense"])),
                        "m", style, frozenset({"S2"}))
    assert scope.lines[0].fact_ids == ("F1", "F9")


def test_ledger_check_refuses_lines_naming_no_fact_or_a_count_the_ledger_lacks():
    style = load_house_style()
    scope = parse_scope(_scope_answer(
        _line("Furnish and Install Space Temperature Sensor (Qty. 12 Total)", 12),
        _line("Furnish and Install Discharge Air Temperature Sensor", fact_ids=[]),
        _line("Furnish and Install VAV Controller", 13)), "m", style, frozenset({"S2"}))
    checked = ledger_check(scope, frozenset({"F1", "F2"}), frozenset({12, 14}))
    assert [line.text for line in checked.lines] == ["Furnish and Install Space Temperature Sensor (Qty. 12 Total)"]
    assert checked.refused[-2:] == (
        "“Furnish and Install Discharge Air Temperature Sensor” names no fact of this system's ledger entry; left out",
        "“Furnish and Install VAV Controller” gives 13, which is no count in this system's ledger entry; left out")
    assert ledger_check(scope, frozenset(), frozenset()) == scope


def test_write_system_carries_the_ledger_entry_and_checks_the_lines(tmp_path):
    reply = _scope_answer(_line("Furnish and Install Space Temperature Sensor"),
                          _line("Furnish and Install VAV Controller", 13))
    client = FakeClient(_response(reply))
    judge = _judge(tmp_path, client)
    system = PlannedSystem(**{k: v for k, v in _system().items()})
    scope = judge.write_system(system, "[S2] evidence", [], [], [], "", ledger_text="F1 family VAV = x [S5] “x” (settled, seed)",
                               facts=("F1",), counts=(12,))
    assert "F1 family VAV" in str(client.calls[0]["messages"][0]["content"])
    assert [line.text for line in scope.lines] == ["Furnish and Install Space Temperature Sensor"]
    assert any("gives 13" in r for r in scope.refused)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_whole_job.py -q -k "ledger or fact_ids"`
Expected: FAIL with `ImportError: cannot import name 'ledger_check'`

- [ ] **Step 3: Make the changes**

In `whole_job.py`:

1. `class WrittenLine`: add `fact_ids: tuple[str, ...] = ()` after `flag_text`.

2. `write_prompt`: add the parameter `ledger_text: str = ""` at the end of the signature and change the body to:

```python
    ledger_block = (f"The job ledger's facts for this system. Every line you write names, in fact_ids, the ids of the "
                    f"facts it rests on; a count in a line is one of these facts' counts:\n{ledger_text.strip()}"
                    if ledger_text.strip() else "")
    return "\n\n".join(filter(None, [
        _system_text(system),
        ledger_block,
        f"The job's evidence for this system, each passage with its source id:\n"
        f"{(evidence_text or '').strip() or '(none)'}",
        images_text(images, image_ids),
        f"The Master Template block for the nearest system. {TEMPLATE_WORDS}\n" + options_text(options),
        f"The Master Template's tech-hour rule for the nearest system: {hours_rule or 'none in the template'}"]))
```

3. `write_schema`: in the `line` object add `"fact_ids": {"type": "array", "items": text},` to `properties` and `"fact_ids"` to `required`.

4. `parse_scope`: just before `lines.append(WrittenLine(...))` add

```python
        fact_ids = tuple(i for i in (_plain_fact_id(f) for f in (raw.get("fact_ids") or ())) if i)
```

and pass `fact_ids=fact_ids` into the `WrittenLine(...)` call. Add near `_flag`:

```python
_FACT_ID = re.compile(r"^\s*\[?\s*(F\d+)\s*\]?\s*$")


def _plain_fact_id(value) -> str:
    match = _FACT_ID.match(str(value or ""))
    return match.group(1) if match else ""
```

5. After `parse_scope` add:

```python
def ledger_check(scope: WrittenScope, facts: frozenset[str], counts: frozenset[int]) -> WrittenScope:
    """The two ledger rules on a written scope: with `facts`, a line naming none of them is refused; with `counts`,
    a line whose quantity is none of them is refused. Each refusal is listed in plain words."""
    if not facts and not counts:
        return scope
    kept, refused = [], list(scope.refused)
    for line in scope.lines:
        if facts and not (set(line.fact_ids) & set(facts)):
            refused.append(f"“{line.text}” names no fact of this system's ledger entry; left out")
            continue
        if counts and line.quantity is not None and line.quantity not in counts:
            refused.append(f"“{line.text}” gives {line.quantity}, which is no count in this system's ledger entry; "
                           "left out")
            continue
        kept.append(line)
    return dataclasses.replace(scope, lines=tuple(kept), refused=tuple(refused))
```

(`import dataclasses` at the top if it is not already there.)

In `judge.py`, `Judge.write_system`: add `ledger_text: str = "", facts=(), counts=()` to the signature; pass `ledger_text=ledger_text` into `wj.write_prompt(...)`; and replace the last line with:

```python
        scope = wj.parse_scope(answer, model, self.style, known)
        return wj.ledger_check(scope, frozenset(facts or ()), frozenset(int(c) for c in (counts or ())))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_whole_job.py tests/test_gem_round.py tests/test_gem_round2.py tests/test_estimate.py -q`
Expected: all pass. If a GEM-round test builds a `write_schema()` answer without `fact_ids`, `parse_scope` still reads it (the field is optional on read); only the schema advertises it as required.

- [ ] **Step 5: Commit**

```bash
git add src/estimator/writing/whole_job.py src/estimator/writing/judge.py tests/test_whole_job.py
git commit -m "feat: each system is written from its ledger entry; lines name their facts and count only ledger counts

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: The `*` count note on the block and its review row

**Files:**
- Modify: `src/estimator/writing/assemble.py` (`assemble_job`, the loop `for key, parts in misc_monitoring(written_runs, style):` near line 3168)
- Test: `tests/test_assemble.py` (append)

**Interfaces:**
- Consumes: `PlannedSystem.count_note` (Task 6); `Item`, `Run`, `ReviewItem`, `TIER_QUANTITY`, `dataclasses`.
- Produces: `count_notes(written: WrittenSystem, parts) -> WrittenSystem` — the written system with one note item per distinct `count_note` appended to its last block, and one `ReviewItem(bundle_key, "DISCREPANCY", "Two counts for {header}: {note}", "the job ledger", "Confirm the count; the higher one is printed", tier=TIER_QUANTITY)` per note.

- [ ] **Step 1: Write the failing test** (append to `tests/test_assemble.py`; reuse that file's `_dossier`, `_plan`/system helpers as they exist there — read the top of the file first and follow its way of building a plan with one written system)

```python
def test_a_contradicted_count_prints_its_note_and_a_review_row():
    from estimator.writing.assemble import count_notes
    from estimator.writing.write import ScopeLine, WrittenSystem
    from estimator.scope import Block, Item, Run
    from types import SimpleNamespace
    block = Block(header="Qty (14) Variable Air Volume Box VAV-1 thru 14", items=(Item(kind="line", runs=(Run(text="Furnish x"),)),))
    written = WrittenSystem("VAV", (block,), (), ())
    part = SimpleNamespace(system=SimpleNamespace(header="Variable Air Volume Box VAV-1 thru 14",
                                                  count_note="*Qty. (14) per M-201, Drawings.pdf page 3; equipment counts for VAV lists (12)."))

    noted = count_notes(written, [part])

    assert noted.blocks[0].items[-1].kind == "note"
    assert noted.blocks[0].items[-1].text == "*Qty. (14) per M-201, Drawings.pdf page 3; equipment counts for VAV lists (12)."
    row = noted.review[-1]
    assert row.category == "DISCREPANCY" and row.tier == 2
    assert row.decide == "Two counts for Variable Air Volume Box VAV-1 thru 14: *Qty. (14) per M-201, Drawings.pdf page 3; equipment counts for VAV lists (12)."
    assert count_notes(written, [SimpleNamespace(system=SimpleNamespace(header="x", count_note=""))]) == written
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_assemble.py -q -k contradicted_count`
Expected: FAIL with `ImportError: cannot import name 'count_notes'`

- [ ] **Step 3: Add the function and call it**

In `assemble.py`, before `assemble_job`:

```python
def count_notes(written: WrittenSystem, parts) -> WrittenSystem:
    """A system whose ledger count is contradicted prints the "*" note naming both counts under its last block, and
    gets a tier-2 review row for each; unchanged when no part carries a note."""
    notes: list[tuple[str, str]] = []
    for part in parts:
        note = _squash(getattr(part.system, "count_note", "") or "")
        if note and note not in [n for _h, n in notes]:
            notes.append((_squash(getattr(part.system, "header", "") or written.bundle_key), note))
    if not notes or not written.blocks:
        return written
    blocks = list(written.blocks)
    last = blocks[-1]
    blocks[-1] = last.model_copy(update={"items": tuple(last.items) + tuple(
        Item(kind="note", runs=(Run(text=note),)) for _h, note in notes)})
    review = tuple(ReviewItem(written.bundle_key, "DISCREPANCY", f"Two counts for {header}: {note}", "the job ledger",
                              "Confirm the count; the higher one is printed", tier=TIER_QUANTITY)
                   for header, note in notes)
    return dataclasses.replace(written, blocks=tuple(blocks), review=written.review + review)
```

In `assemble_job`, in the loop over `misc_monitoring(written_runs, style)`, right after `written = _written_system(key, parts, ...)` add:

```python
        written = count_notes(written, parts)
```

(`_Part` has a `.system` attribute; check `class _Part` near line 1582 and confirm the name, adjusting the attribute in `count_notes` only if it differs.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_assemble.py tests/test_assemble_fixes.py tests/test_assemble_round3.py tests/test_assemble_round4.py tests/test_assemble_round5.py -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add src/estimator/writing/assemble.py tests/test_assemble.py
git commit -m "feat: a contradicted count prints its note under the block and a review row

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 9: The Evidence Package: "How the job was read" and "Job ledger"

**Files:**
- Modify: `src/estimator/evidence/workbook.py` (`write_evidence`, new `_how_read`, `_ledger`)
- Test: `tests/test_evidence.py` (append)

**Interfaces:**
- `write_evidence(path, catalogue, reading=None, systems=None, review_flags=(), plan=None, ledger=None)`. With a ledger: a tab `"How the job was read"` right after `"Bid check"` (one row per pass in `PASSES` order: pass title, its understanding, its refusals joined by `"; "`), and a tab `"Job ledger"` right after the Plan tab (or after Scope lines when there is no plan) with headings `["Id", "Kind", "Subject", "Value", "Printed count", "State", "Pass", "Source", "Where", "Quote", "Other values"]`.
- Constants `READ_TAB = "How the job was read"`, `LEDGER_TAB = "Job ledger"`.

- [ ] **Step 1: Write the failing test** (append to `tests/test_evidence.py`; `_catalogue()` there builds the small catalogue the other tests use)

```python
def test_the_ledger_tabs_show_how_the_job_was_read_and_every_fact(tmp_path):
    catalogue = _catalogue()
    from openpyxl import load_workbook
    from estimator.evidence.workbook import LEDGER_TAB, READ_TAB, write_evidence
    from estimator.ledger.facts import SETTLED, Ledger
    ledger = Ledger({"S5": "equipment counts for VAV (schedules and plans)", "S10": "M-201, Drawings.pdf page 3 (sheet text)"})
    ledger.add("count", "VAV", 12, "[S5]", "QUANTITY column total 12", "seed", SETTLED)
    ledger.contradict("F1", 14, "[S10]", "VAV-1 … VAV-14", "plans")
    ledger.understanding = {"schedules": "Twelve VAV boxes.", "plans": "Fourteen placed; two more than scheduled."}
    ledger.refused = {"plans": ["location EF = roof has no quote; left out"]}

    path = write_evidence(tmp_path / "e.xlsx", catalogue, ledger=ledger)
    book = load_workbook(path)
    assert book.sheetnames[:2] == ["Bid check", READ_TAB]
    read = list(book[READ_TAB].iter_rows(values_only=True))
    assert read[0] == ("Pass", "What the tool understood", "What it refused")
    assert read[1] == ("Schedules", "Twelve VAV boxes.", None)
    assert read[2] == ("Plans", "Fourteen placed; two more than scheduled.", "location EF = roof has no quote; left out")
    assert read[3][:2] == ("Details and control diagrams", "(not read)")
    rows = list(book[LEDGER_TAB].iter_rows(values_only=True))
    assert rows[0] == ("Id", "Kind", "Subject", "Value", "Printed count", "State", "Pass", "Source", "Where", "Quote", "Other values")
    assert rows[1] == ("F1", "count", "VAV", 12, 14, "contradicted", "seed", "S5", "equipment counts for VAV (schedules and plans)",
                       "QUANTITY column total 12", "plans says 14 [S10] “VAV-1 … VAV-14”")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_evidence.py -q -k ledger_tabs`
Expected: FAIL with `ImportError: cannot import name 'LEDGER_TAB'`

- [ ] **Step 3: Add the tabs**

In `workbook.py`, next to `PLAN_TAB`:

```python
READ_TAB = "How the job was read"
LEDGER_TAB = "Job ledger"
```

Change `write_evidence`'s signature to add `ledger=None` and, right after `_bid_check(...)`:

```python
    if ledger is not None:
        _how_read(workbook.create_sheet(READ_TAB), ledger)
```

and right after the `if plan is not None:` block:

```python
    if ledger is not None:
        _ledger(workbook.create_sheet(LEDGER_TAB), ledger)
```

Add the two writers:

```python
def _how_read(ws, ledger) -> None:
    """One row per reading pass, in the estimator's order: what the tool understood after it, and what it refused."""
    from estimator.ledger.passes import PASSES
    _headings(ws, ["Pass", "What the tool understood", "What it refused"])
    for p in PASSES:
        refused = "; ".join(ledger.refused.get(p.name, ()) or ()) or None
        _append(ws, [p.title, ledger.understanding.get(p.name) or "(not read)", refused])
        for column in (2, 3):
            ws.cell(ws.max_row, column).alignment = Alignment(wrap_text=True, vertical="top")
    _widths(ws, [30, 90, 60])


def _ledger(ws, ledger) -> None:
    """Every fact of the job ledger: its value, the count that prints, its state and pass, where it comes from and
    the words that state it, then the other values later passes found."""
    _headings(ws, ["Id", "Kind", "Subject", "Value", "Printed count", "State", "Pass", "Source", "Where", "Quote",
                   "Other values"])
    ws.freeze_panes = "A2"
    for fact in ledger.facts.values():
        others = "; ".join(f"{c.stage} says {c.value} [{c.source_id}] “{c.quote}”" for c in fact.contradictions) or None
        _append(ws, [fact.id, fact.kind, fact.subject, fact.value, ledger.printed_count(fact.id), fact.state, fact.stage,
                     fact.source_id, ledger.sources.get(fact.source_id) or None, fact.quote, others])
        for column in (10, 11):
            ws.cell(ws.max_row, column).alignment = Alignment(wrap_text=True, vertical="top")
    if not ledger.facts:
        _append(ws, ["", "The ledger holds no facts."])
    ws.auto_filter.ref = ws.dimensions
    _widths(ws, [8, 14, 24, 30, 12, 12, 10, 8, 40, 50, 50])
```

(`Alignment` is already imported in the module; check the import line and add it if not.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_evidence.py -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add src/estimator/evidence/workbook.py tests/test_evidence.py
git commit -m "feat: the Evidence Package shows how the job was read and every ledger fact

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 10: The estimate command reads in passes

**Files:**
- Modify: `src/estimator/__main__.py` (`_estimate_whole_job` ~line 334, `whole_job_lines` ~line 396, imports ~line 58)
- Test: `tests/test_estimate.py` (the `whole_job` fixture ~line 223 and the tests using it)

**Interfaces:**
- Consumes: `read_job` (Task 5), `ledger_plan`, `entry_text`, `system_counts` (Task 6), `Judge.write_system(..., ledger_text, facts, counts)` (Task 7), `write_evidence(..., ledger=)` (Task 9).
- Behaviour:
  1. after the dossier is written and the judge made: `ledger = read_job(judge, dossier, catalogue, save_to=args.out / f"{quote} Ledger.json")`.
  2. when `not ledger.complete`: `write_evidence(package_path, catalogue, reading, ledger=ledger)`, print the summary lines (`whole_job_lines(None, [], [], judge, ledger=ledger)`), print `Wrote …`, return.
  3. `plan = ledger_plan(ledger)`; the write loop passes `ledger_text=entry_text(system, ledger), facts=system.facts, counts=system_counts(system, ledger)`.
  4. `write_evidence(..., plan=checks, ledger=ledger)`.
  5. `whole_job_lines(plan, systems, review, judge, reading_flags, ledger=None)`: with a ledger that is not complete, the first line is `f"Reading the job: stopped at the {title} pass — {judge.last_error or 'no answer'}."`; with a complete ledger, the first line is `"Reading the job: 12 facts settled in 4 passes; 1 contradiction."` (singular and plural by the number) where facts counts state settled or contradicted, passes counts understandings not starting with "nothing to read", and contradictions counts contradicted facts. The old closing line "The AI gave no plan" prints only when there is no ledger.

- [ ] **Step 1: Update the fixture and write the failing tests**

In `tests/test_estimate.py`, read the `whole_job` fixture and `FakeJudge` (they fake `plan_job` and `write_system`). Change the fixture so the run goes through the ledger instead of `plan_job`:

```python
@pytest.fixture
def whole_job(monkeypatch):
    monkeypatch.setattr("estimator.__main__.build_dossier", _fake_dossier)
    monkeypatch.setattr("estimator.__main__.read_job", lambda judge, dossier, catalogue, save_to=None: _fake_ledger(save_to))
    monkeypatch.setattr("estimator.__main__.ledger_plan", lambda ledger: JOB_PLAN)
    judges = []

    def make(cache, mode, job=None):
        judges.append(FakeJudge(JOB_PLAN, SCOPES, mode=mode))
        return judges[-1]

    monkeypatch.setattr("estimator.__main__.Judge", make)
    return judges
```

with, near `_fake_dossier`:

```python
def _fake_ledger(save_to=None):
    from estimator.ledger.facts import SETTLED, Ledger
    ledger = Ledger({"S1": "the job"})
    ledger.add("family", "VAV", "Variable Air Volume Box", "[S1]", "VAV", "seed", SETTLED)
    ledger.understanding = {"schedules": "A school with VAV boxes."}
    ledger.complete = True
    ledger.job_name = "26-9999"
    if save_to is not None:
        ledger.save(save_to)
    return ledger
```

`FakeJudge.write_system` must accept the new keyword arguments: add `ledger_text="", facts=(), counts=()` to its signature (and keep returning the canned scope). Delete `FakeJudge.plan_job` only in Task 11.

Add the tests:

```python
def test_the_whole_job_method_writes_the_ledger_and_its_tabs(job, tmp_path, capsys, whole_job):
    main(["estimate", str(job), "--out", str(tmp_path / "out"), "--ai", "api"])
    out = tmp_path / "out"
    ledger = next(out.glob("* Ledger.json"))
    assert json.loads(ledger.read_text(encoding="utf-8"))["complete"] is True
    from openpyxl import load_workbook
    book = load_workbook(next(out.glob("* Evidence Package.xlsx")))
    assert "How the job was read" in book.sheetnames and "Job ledger" in book.sheetnames
    printed = capsys.readouterr().out
    assert "Reading the job: 1 fact settled in 1 pass; 0 contradictions." in printed


def test_when_a_pass_is_waiting_the_run_stops_after_the_evidence_package(job, tmp_path, capsys, monkeypatch, whole_job):
    def waiting(judge, dossier, catalogue, save_to=None):
        ledger = _fake_ledger(save_to)
        ledger.complete, ledger.stopped_at = False, "plans"
        judge.last_error = "judgement pending — waiting for an answer in the chat"
        return ledger

    monkeypatch.setattr("estimator.__main__.read_job", waiting)
    main(["estimate", str(job), "--out", str(tmp_path / "out"), "--ai", "api"])
    out = tmp_path / "out"
    assert next(out.glob("* Evidence Package.xlsx"), None) is not None
    assert next(out.glob("*.docx"), None) is None
    assert "Reading the job: stopped at the Plans pass — judgement pending" in capsys.readouterr().out
```

(`main` and `json` are imported at the top of `tests/test_estimate.py` already; check and add if not.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_estimate.py -q -k "ledger or waiting"`
Expected: FAIL with `AttributeError: <module 'estimator.__main__'> has no attribute 'read_job'`

- [ ] **Step 3: Wire the command**

In `__main__.py` imports add:

```python
from estimator.ledger.run import read_job
from estimator.ledger.to_plan import entry_text, ledger_plan, system_counts
```

Replace, in `_estimate_whole_job`, the block from `plan = judge.plan_job(...)` through its `return` with:

```python
    ledger = read_job(judge, dossier, catalogue, save_to=args.out / f"{quote} Ledger.json")
    print(f"Wrote {args.out / f'{quote} Ledger.json'}")
    if not ledger.complete:
        package = write_evidence(package_path, catalogue, reading, ledger=ledger)
        for line in whole_job_lines(None, [], [], judge, ledger=ledger):
            print(line)
        print(f"Wrote {package}")
        return
    plan = ledger_plan(ledger)
```

In the write loop, add to the `judge.write_system(...)` call:

```python
                                                ledger_text=entry_text(system, ledger), facts=system.facts,
                                                counts=system_counts(system, ledger),
```

Change `write_evidence(package_path, catalogue, reading, systems=systems, review_flags=review, plan=checks)` to add `, ledger=ledger`, and the following `whole_job_lines(...)` call to add `, ledger=ledger`.

Change `whole_job_lines`'s signature to `def whole_job_lines(plan, systems, review, judge, reading_flags: int = 0, ledger=None) -> list[str]:` and at its start:

```python
    summary = []
    if ledger is not None and not getattr(ledger, "complete", True):
        from estimator.ledger.passes import pass_named
        title = pass_named(ledger.stopped_at).title if ledger.stopped_at else "first"
        summary.append(f"Reading the job: stopped at the {title} pass — {judge.last_error or 'no answer'}.")
    elif ledger is not None:
        facts = list(ledger.facts.values())
        settled = sum(1 for f in facts if f.state in ("settled", "contradicted"))
        contradicted = sum(1 for f in facts if f.state == "contradicted")
        read = sum(1 for words in ledger.understanding.values() if not words.startswith("nothing to read"))
        summary.append(f"Reading the job: {settled} {'fact' if settled == 1 else 'facts'} settled in {read} "
                       f"{'pass' if read == 1 else 'passes'}; {contradicted} "
                       f"{'contradiction' if contradicted == 1 else 'contradictions'}.")
```

(replace the existing `summary = []` line). Change the function's last `if plan is None:` to `if plan is None and ledger is None:` so "The AI gave no plan" prints only when nothing was read at all. Leave the rest as it is.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_estimate.py tests/test_main.py -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add src/estimator/__main__.py tests/test_estimate.py
git commit -m "feat: estimate reads the job in seven passes and writes each system from its ledger entry

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 11: Retire the plan pass

**Files:**
- Modify: `src/estimator/writing/judge.py` (delete `Judge.plan_job`; `_for_job`'s `PLAN_JOB` branch; the `PLAN_JOB` constant)
- Modify: `src/estimator/writing/whole_job.py` (delete `PLAN_PROMPT`, `plan_prompt`, `plan_schema`, `parse_plan`, `_families`, `_front_end`, `merge_plans`, `split_dossier`, `DossierPart`, `_sections`, `_SECTIONS`, `_HEADING`, `_FIRST_GROUP`, `_SECOND_GROUP`; keep `_chunks`, `SPLIT_LIMIT`, `checklist_text`, `known_ids`, `images_*`, `content_blocks`)
- Modify: `src/estimator/__main__.py` (the `checklist_text` import if now unused; `import-sent`/`score` untouched)
- Modify: `tests/test_whole_job.py` (delete the B1 plan tests and `_plan`; keep `FakeClient`, `_response`, `_judge`, `_system`, `_plan_answer` only if other tests still use them), `tests/test_estimate.py` (delete `FakeJudge.plan_job`), any other test importing a deleted name (`grep -rn "plan_job\|parse_plan\|merge_plans\|split_dossier\|PLAN_PROMPT\|plan_schema\|DossierPart" tests src`)

- [ ] **Step 1: Find every use**

Run: `grep -rn "plan_job\|parse_plan\|merge_plans\|split_dossier\|PLAN_PROMPT\|plan_schema\|plan_prompt\|DossierPart\|PLAN_JOB" src tests --include=*.py`
Expected: hits only in `judge.py`, `whole_job.py`, `tests/test_whole_job.py`, `tests/test_estimate.py`, and the module docstrings. If `assemble.py` or the workbook use any (they should not), stop and report.

- [ ] **Step 2: Delete the names and their tests**

Remove the functions, constants and classes listed above, and the tests that call them. Update the module docstrings of `whole_job.py` and `judge.py`: the whole-job judge now answers "read_pass" (the seven passes of `estimator.ledger`) and "write_system"; the systems come from the ledger (`estimator.ledger.to_plan`). In `_for_job`, drop the `PLAN_JOB` branch (old plan requests in a requests folder are then "not for this job" and retire, which is right: they are never asked again).

- [ ] **Step 3: Run the whole suite**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: all pass, no `ImportError`

- [ ] **Step 4: Commit**

```bash
git add -A src tests
git commit -m "refactor: the plan pass is gone; the systems come from the job ledger

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 12: Chat mode round on a Learn job (the quick gate)

**Files:**
- No code changes expected. Output under `out/` only (job data never enters the repository).

- [ ] **Step 1: Run one Learn job in chat mode**

Run (pick the smallest Learn job folder the user has used before; ask the user which if unsure):

```bash
.venv/Scripts/python.exe -m estimator estimate "<job folder>" --out "out/<job>" --ai chat
```

Expected: `Wrote … Ledger.json`, `Reading the job: stopped at the Schedules pass — judgement pending …`, one request in the requests folder whose `kind` is `read_pass`.

- [ ] **Step 2: Answer the pass in chat, re-run, repeat until `complete`**

Each request is answered in the Claude Code chat as the existing questions are (the answer JSON saved to the `answer_file` the request names). Re-run the same command after each answer. Expected after the seventh answer: `Reading the job: N facts settled in M passes; K contradictions.` and the write requests for each system.

- [ ] **Step 3: Read the "How the job was read" tab**

Open the Evidence Package and read the seven understanding paragraphs against the job. Report to the user, in plain words: does the tool's picture of the job match how they would describe it, which pass went wrong if any, and how many lines the ledger rules refused. No tuning: findings only.

- [ ] **Step 4: Report**

No commit. Report what the run showed, with the Ledger.json path and the request count per pass.
