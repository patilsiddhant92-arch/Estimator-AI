"""The takeoff pass (plan 2026-10-11, Stage 1): one whole-job AI step after the ledger is complete.

The step is given the whole job as the reading left it (every ledger fact, what each reading pass understood, every
drawing sheet with the code's type guess and its label tally, the schedule rows, the notes on the sheets, the
sequence headings and the devices counted per sheet) and returns a register: what each sheet is (`SheetClass`), the
units the documents show (`Unit`), the counts set aside (`SetAside`), the items marked future (`FutureItem`) and at
most one question per family.

- `prompt(...)` builds the request text, deterministic (the cache key stays stable). A request longer than
  `TAKEOFF_LIMIT` characters stops the run in words; it is never cut in silence.
- `check_answer(...)` refuses an answer that leaves a sheet out, gives one twice or names an unknown one; a plan with
  no area; a scheduled tag with no unit row; a ref whose id the job does not know or whose quote is not in it; a
  demolition sheet that counts with no ref; two rows for one unit; `serves` naming no unit; a scheduled unit set
  aside, or counted below the schedule, without a reason and a cited passage other than the schedule itself (the
  schedule floor: the scheduled rows, plus the numeric quantity column when the schedule has one).
- `take_off(...)` asks through the run's transport (chat or API) with those checks; `ai.NoAnswer` as the writers.
- `attach(job, takeoff)` puts the register on the Job. Stage 1 changes no count: nothing reads the register yet.
- `save` / `load`: `out/<quote> Takeoff.json`.
"""
from __future__ import annotations

import dataclasses
import json
import re
from dataclasses import dataclass
from pathlib import Path

from estimator.catalogue.job import CONTROLS_DISCIPLINES
from estimator.catalogue.tags import label_keys, line_labels

from bms import ai
from bms.model import (COUNTED_STATUSES, FutureItem, Job, ModelError, Ref, SetAside, SheetClass, Unit, json_schema,
                       schema_errors)

TAKEOFF_JOB = "takeoff_job"
TAKEOFF_NAME = "Takeoff"
TAKEOFF_LIMIT = 600_000             # characters of one takeoff request
VERSION = 1
# the sheet kinds that are plans of a place: each needs an area
PLAN_KINDS = ("new_work", "demolition", "part_plan", "enlarged_plan")
_KEYS = ("sheets", "units", "set_aside", "future_items", "questions")
_CLASSES = {"sheets": SheetClass, "units": Unit, "set_aside": SetAside, "future_items": FutureItem}
_QUANTITY = re.compile(r"^\s*(?:QTY|QUANTITY)\b", re.I)
_NUMBER = re.compile(r"^\s*(\d+)\s*$")


@dataclass(frozen=True)
class Takeoff:
    """The takeoff register of one job, as the takeoff reader answered and the checks kept it."""
    sheets: tuple[SheetClass, ...]
    units: tuple[Unit, ...]
    set_aside: tuple[SetAside, ...]
    future_items: tuple[FutureItem, ...]
    questions: tuple[str, ...]

    def to_dict(self) -> dict:
        return {"sheets": [s.to_dict() for s in self.sheets], "units": [u.to_dict() for u in self.units],
                "set_aside": [s.to_dict() for s in self.set_aside],
                "future_items": [f.to_dict() for f in self.future_items], "questions": list(self.questions)}

    @classmethod
    def from_dict(cls, data: dict) -> "Takeoff":
        return cls(**{key: tuple(_CLASSES[key].from_dict(row) for row in data[key]) for key in _CLASSES},
                   questions=tuple(str(q) for q in data["questions"]))


def answer_schema() -> dict:
    """The answer: the five lists, all required, nothing else."""
    properties = {key: {"type": "array", "items": json_schema(cls)} for key, cls in _CLASSES.items()}
    properties["questions"] = {"type": "array", "items": {"type": "string"}}
    return {"type": "object", "properties": properties, "required": list(_KEYS), "additionalProperties": False}


# ---- the request ---------------------------------------------------------------------------------------------------

def _natural(tag: str) -> tuple:
    return tuple((0, int(part), "") if part.isdigit() else (1, 0, part) for part in re.split(r"(\d+)", tag))


def _sheets(catalogue) -> list:
    return sorted((s for s in catalogue.sheets if s.discipline in CONTROLS_DISCIPLINES),
                  key=lambda s: (s.document, s.page))


def _sheet_lines(catalogue, dossier) -> list[str]:
    texts = {(doc, page): sid for sid, (doc, page) in (getattr(dossier, "sheet_pages", None) or {}).items()}
    pages = {(p.document, p.page): p.text for p in catalogue.pages}
    keys = label_keys(t.tag for t in catalogue.tags)
    lines = []
    for sheet in _sheets(catalogue):
        tally = line_labels(pages.get((sheet.document, sheet.page), "") or "", keys)
        labels = ", ".join(f"{tag} x{tally[tag]}" for tag in sorted(tally, key=_natural)) or "none"
        lines.append(f"{sheet.document} | page {sheet.page} | {sheet.number or '-'} | {sheet.title or '-'} | "
                     f"code guess: {', '.join(sheet.types) or 'none'} | text: {texts.get((sheet.document, sheet.page), '-')}"
                     f" | labels: {labels}")
    return lines


def _schedule_lines(reading) -> list[str]:
    lines = []
    for schedule in getattr(reading, "schedules", ()) or ():
        lines.append(f"{schedule.sheet or '-'} {schedule.title}")
        for row in schedule.rows:
            cells = "; ".join(f"{column}={value}" for column, value in row.cells.items())
            lines.append(f"{row.tag or '-'}: {cells}")
    return lines


def prompt(ledger, catalogue, reading, dossier) -> str:
    """The takeoff request: seven sections, each under a "## " heading line, in the plan's order. Deterministic.
    Longer than TAKEOFF_LIMIT characters: a ValueError that stops the run in words."""
    sections = [
        ("Ledger facts", [ledger.table()]),
        ("What each reading pass understood", [f"- {name}: {text}" for name, text in ledger.understanding.items()]),
        ("Sheets", _sheet_lines(catalogue, dossier)),
        ("Schedules", _schedule_lines(reading)),
        ("Notes on the sheets", [f"{n.sheet or '-'} {n.block} {n.number}: {n.text}"
                                 for n in getattr(reading, "notes", ()) or ()]),
        ("Sequence sections", [f"{qid}: {heading}"
                               for qid, (heading, *_) in (getattr(dossier, "sections", None) or {}).items()]),
        ("Devices counted on the sheets", [f"{d.sheet or '-'} {d.device} ({d.label}) {d.count}"
                                           for d in getattr(reading, "devices", ()) or ()]),
    ]
    text = "\n\n".join("\n".join([f"## {heading}", *(lines or ["(none)"])]) for heading, lines in sections)
    if len(text) > TAKEOFF_LIMIT:
        raise ValueError(f"Stopped: the takeoff request is too long ({len(text)} characters); the most is "
                         f"{TAKEOFF_LIMIT}. Nothing was cut: the job must be read in parts before the takeoff can run.")
    return text


# ---- the checks ------------------------------------------------------------------------------------------------------

def _plain(tag: str) -> str:
    return re.sub(r"[\s\-_]", "", str(tag or "")).upper()


def _ref_problem(ref: Ref, ledger, index: dict) -> str | None:
    sid = str(ref.source_id).strip().strip("[]")
    fact = ledger.facts.get(sid)
    if fact is not None:
        text = f"{fact.quote} {fact.value}"
    elif sid in index:
        text = index[sid]
    else:
        return f"cites {sid}, which the ledger does not know"
    if not ai.quote_in(ref.quote, text):
        return f"quotes “{ref.quote}” from {sid}, but {sid} does not say that"
    return None


def _scheduled(reading) -> dict[str, tuple[str, int, str]]:
    """Each scheduled tag (plain) -> (the tag as printed, its floor, its schedule's "<sheet> <title>"): the floor is
    one per row, or the row's numeric quantity column when the schedule has one. The reading already lists one row
    per tag ("A THRU C" rows are expanded)."""
    floor: dict[str, tuple[str, int, str]] = {}
    for schedule in getattr(reading, "schedules", ()) or ():
        if getattr(schedule, "passive", False):
            continue
        quantity = next((h for h in schedule.headers if _QUANTITY.match(str(h))), None)
        name = f"{schedule.sheet or '-'} {schedule.title}"
        for row in schedule.rows:
            if not row.tag:
                continue
            number = _NUMBER.match(str(row.cells.get(quantity, ""))) if quantity else None
            least = int(number.group(1)) if number else 1
            tag, before, _ = floor.get(_plain(row.tag), (row.tag, 0, name))
            floor[_plain(row.tag)] = (tag, max(before, least), name)
    return floor


def _cites_beyond(unit: Unit, schedule: str, ledger) -> bool:
    """The unit cites a passage other than its schedule: a ref whose source (a fact's own source) is not the
    schedule's ("M-601 AIR HANDLING UNIT SCHEDULE, Mech.pdf page 1" is the schedule "M-601 AIR HANDLING UNIT
    SCHEDULE")."""
    for ref in unit.refs:
        sid = str(ref.source_id).strip().strip("[]")
        fact = ledger.facts.get(sid)
        source = fact.source_id if fact is not None else sid
        if not str(ledger.sources.get(source, "")).startswith(f"{schedule},"):
            return True
    return False


def _problems(takeoff: Takeoff, ledger, catalogue, reading, index: dict) -> list[str]:
    problems: list[str] = []
    # sheets: every listed sheet exactly once, by document and page
    listed = {(s.document, s.page): s for s in _sheets(catalogue)}
    seen: dict[tuple, int] = {}
    for sheet in takeoff.sheets:
        key = (sheet.document, sheet.page)
        name = f"{sheet.number or '-'} ({sheet.document} page {sheet.page})"
        seen[key] = seen.get(key, 0) + 1
        if key not in listed:
            problems.append(f"sheet {name} is not a sheet of this job")
        elif seen[key] == 2:
            problems.append(f"sheet {name} is given twice")
        if sheet.kind in PLAN_KINDS and not sheet.area.strip():
            problems.append(f"sheet {name} is a {sheet.kind} plan with no area")
        if sheet.kind == "demolition" and sheet.counts_units and not sheet.refs:
            problems.append(f"sheet {name} is a demolition sheet whose units count, with no ref naming work on them")
    for key, sheet in listed.items():
        if key not in seen:
            problems.append(f"sheet {sheet.number or '-'} ({sheet.document} page {sheet.page}) is left out")
    # units: one row per (family, tag); serves names a unit; refs real
    tags = {_plain(u.tag) for u in takeoff.units}
    rows: dict[tuple, int] = {}
    for unit in takeoff.units:
        key = (unit.family.upper(), _plain(unit.tag))
        rows[key] = rows.get(key, 0) + 1
        if rows[key] == 2:
            problems.append(f"unit {unit.tag} ({unit.family}) has two rows")
        if unit.serves and _plain(unit.serves) not in tags:
            problems.append(f"unit {unit.tag} serves {unit.serves}, which is no unit of the register")
    # the schedule floor
    by_tag = {_plain(u.tag): u for u in takeoff.units}
    for plain, (tag, least, schedule) in _scheduled(reading).items():
        unit = by_tag.get(plain)
        if unit is None:
            problems.append(f"scheduled tag {tag} has no unit row")
            continue
        explained = bool(unit.reason.strip()) and _cites_beyond(unit, schedule, ledger)
        if unit.status not in COUNTED_STATUSES and not explained:
            problems.append(f"unit {unit.tag} is scheduled but its status is {unit.status}: give the reason and cite "
                            "the passage that sets the scheduled row aside")
        elif unit.status in COUNTED_STATUSES and unit.count < least and not explained:
            problems.append(f"unit {unit.tag} counts {unit.count}, below the schedule's {least}: give the reason "
                            "and cite the passage that says why")
    # every ref is this job's, in its own words
    cited = [(f"sheet {s.number or s.page}", r) for s in takeoff.sheets for r in s.refs]
    cited += [(f"unit {u.tag}", r) for u in takeoff.units for r in u.refs]
    cited += [(f"set-aside {a.family} {a.value}", a.ref) for a in takeoff.set_aside]
    cited += [(f"future item {f.item}", r) for f in takeoff.future_items for r in f.refs]
    for name, ref in cited:
        problem = _ref_problem(ref, ledger, index)
        if problem:
            problems.append(f"{name} {problem}")
    return problems


def check_answer(answer, ledger, catalogue, reading, index) -> tuple[Takeoff | None, list[str]]:
    """The register, or None and the problems that refuse the answer (each names its item)."""
    errors = schema_errors(answer, answer_schema())
    if errors:
        return None, errors
    built: dict = {}
    problems: list[str] = []
    for key, cls in _CLASSES.items():
        rows = []
        for n, row in enumerate(answer[key]):
            try:
                rows.append(cls.from_dict(row))
            except ModelError as error:
                problems.append(f"{key}[{n}]: {error}")
        built[key] = tuple(rows)
    if problems:
        return None, problems
    takeoff = Takeoff(**built, questions=tuple(str(q) for q in answer["questions"]))
    problems = _problems(takeoff, ledger, catalogue, reading, dict(index or {}))
    return (None, problems) if problems else (takeoff, [])


# ---- the step ----------------------------------------------------------------------------------------------------------

def take_off(ledger, catalogue, reading, dossier, playbook, transport) -> Takeoff:
    """Ask the takeoff question with its checks. Raises ai.NoAnswer as the writers do (waiting in chat mode, or the
    stop after the most refusals); a request over the limit raises ValueError."""
    text = prompt(ledger, catalogue, reading, dossier)
    index = ai.evidence_index(dossier)

    def check(answer):
        return check_answer(answer, ledger, catalogue, reading, index)

    return ai._ask_checked(transport, TAKEOFF_JOB, TAKEOFF_NAME, playbook.rules_text, ai._instructions(TAKEOFF_JOB),
                           text, answer_schema(), {"step": "takeoff"}, (), check)


def attach(job: Job, takeoff: Takeoff) -> Job:
    """The job with the register on it: `sheets`, `units`, `set_aside` and `future_items` only. No count changes."""
    return dataclasses.replace(job, sheets=takeoff.sheets, units=takeoff.units, set_aside=takeoff.set_aside,
                               future_items=takeoff.future_items)


def save(takeoff: Takeoff, path: Path) -> bool:
    """Write the register whole or not at all (`ai._write_json`); a file that already holds this register is left
    as it is (every later run reads the same cached answer). True when it was written."""
    path = Path(path)
    try:
        if load(path) == takeoff:
            return False
    except (OSError, ValueError, KeyError, TypeError, ModelError):
        pass                        # missing, unreadable or another register: write it
    ai._write_json(path, {"version": VERSION, **takeoff.to_dict()}, indent=1)
    return True


def load(path: Path) -> Takeoff:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return Takeoff.from_dict({key: data.get(key) or [] for key in _KEYS})
