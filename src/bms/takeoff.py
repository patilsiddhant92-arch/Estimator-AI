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
  aside, or counted below the schedule, without a reason and a cited passage other than the schedule and the unit's
  own schedule row (the schedule floor: the scheduled rows, plus the numeric quantity column when the schedule has
  one).
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
from bms.model import (COUNTED_STATUSES, DemolitionLine, FutureItem, Job, ModelError, Ref, SetAside, SheetClass, Unit,
                       json_schema, schema_errors)

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


def _scheduled(reading) -> dict[str, tuple[str, int, tuple[str, ...]]]:
    """Each scheduled tag (plain) -> (the tag as printed, its floor, the source-name prefixes that are the schedule
    itself for that row): the floor is one per row, or the row's numeric quantity column when the schedule has one.
    The reading already lists one row per tag ("A THRU C" rows are expanded)."""
    floor: dict[str, tuple[str, int, tuple[str, ...]]] = {}
    for schedule in getattr(reading, "schedules", ()) or ():
        if getattr(schedule, "passive", False):
            continue
        quantity = next((h for h in schedule.headers if _QUANTITY.match(str(h))), None)
        for row in schedule.rows:
            if not row.tag:
                continue
            number = _NUMBER.match(str(row.cells.get(quantity, ""))) if quantity else None
            least = int(number.group(1)) if number else 1
            tag, before, own = floor.get(_plain(row.tag), (row.tag, 0, ()))
            floor[_plain(row.tag)] = (tag, max(before, least), own + _own_sources(schedule, row.tag))
    return floor


def _own_sources(schedule, tag: str) -> tuple[str, ...]:
    """The names the dossier gives the schedule and this tag's row (`estimator.writing.dossier`): the schedule
    "<sheet> <title>, <document> page <n>" ("<title>, ..." with no sheet) and the row "<title> row <tag>, <where>".
    The schedule's notes ("<title> notes, ...") are other passages."""
    head = f"{schedule.sheet} {schedule.title}" if schedule.sheet else schedule.title
    return (f"{head}, ", f"{schedule.title} row {tag}, ")


def _cites_beyond(unit: Unit, own: tuple[str, ...], ledger) -> bool:
    """The unit cites a passage other than its schedule and its own schedule row: a ref whose source (a fact's own
    source) is not named as the schedule or that row ("M-601 AIR HANDLING UNIT SCHEDULE, Mech.pdf page 1" is the
    schedule; "AIR HANDLING UNIT SCHEDULE row AHU-5, M-601, Mech.pdf page 1" is the row of AHU-5)."""
    for ref in unit.refs:
        sid = str(ref.source_id).strip().strip("[]")
        fact = ledger.facts.get(sid)
        source = fact.source_id if fact is not None else sid
        name = str(ledger.sources.get(source, ""))
        if not any(name.startswith(prefix) for prefix in own):
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
    for plain, (tag, least, own) in _scheduled(reading).items():
        unit = by_tag.get(plain)
        if unit is None:
            problems.append(f"scheduled tag {tag} has no unit row")
            continue
        explained = bool(unit.reason.strip()) and _cites_beyond(unit, own, ledger)
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


# ---- Stage 2: the register binds the counts (plan Tasks 2.1 to 2.5) ------------------------------------------

def _sheet_key(sheet) -> tuple[str, int]:
    return (sheet.document, int(sheet.page))


def admissible_pages(sheets) -> frozenset[tuple[str, int]]:
    """The (document, page) of every sheet whose units and devices count for this job (`counts_units` true)."""
    return frozenset(_sheet_key(s) for s in sheets or () if s.counts_units)


def area_groups(sheets) -> dict[tuple[str, int], tuple[tuple[str, int], ...]]:
    """(document, page) -> the sheets of its area, in the form `inventory.plan_groups` returns: the counted sheets
    (`counts_units` true) that name one area (the same words, any case) share one tuple, in (document, page) order.
    A counted sheet with no area is a group of its own; a sheet whose units do not count is in no group (it is
    never read for a count, `admissible_pages`)."""
    counted = sorted((s for s in sheets or () if s.counts_units), key=_sheet_key)
    members: dict[str, list[tuple[str, int]]] = {}
    for sheet in counted:
        area = " ".join(sheet.area.split()).casefold()
        members.setdefault(area or f"\0{sheet.document}\0{sheet.page}", []).append(_sheet_key(sheet))
    return {key: tuple(keys) for keys in members.values() for key in keys}


def plural(word: str) -> str:
    """ "Thermostat" -> "thermostats": a device name as a count's plain words."""
    word = " ".join(str(word or "").split()).lower()
    return word if not word or word.endswith("s") else f"{word}s"


def aside_reason(sheet) -> str:
    """Why the counts of a sheet whose units do not count are set aside, in the register's words."""
    return {"demolition": "demolition sheet", "part_plan": "part plan of one area",
            "enlarged_plan": "same unit labelled again"}.get(getattr(sheet, "kind", ""), "not a unit of this family")


def device_tally(devices, sheets, label: str, sheet_pages: dict | None = None) -> tuple[int, list[SetAside]]:
    """The devices labelled `label` (`reading.devices`, the `DeviceCount`s) counted over the sheets the register
    admits: (the total of the counted sheets, one `SetAside` per sheet whose units do not count). A device counted on
    a sheet the register does not list is kept (the register decides only the sheets it classed). With no register
    sheets every count is kept. `sheet_pages` (`Dossier.sheet_pages`, 7c id -> (document, page)) gives each set-aside
    its sheet text's source id; without it the id is empty."""
    by_key = {_sheet_key(s): s for s in sheets or ()}
    ids = {(doc, int(page)): sid for sid, (doc, page) in (sheet_pages or {}).items()}
    mine = [d for d in devices or () if d.label == label]
    kept = 0
    out: list[tuple] = []
    for d in mine:
        sheet = by_key.get((d.document, int(d.page)))
        if sheet is None or sheet.counts_units:
            kept += d.total
        else:
            out.append((d, sheet))
    aside = []
    for d, sheet in out:
        reason = aside_reason(sheet)
        where = (f"{d.sheet}, {d.document} page {d.page}" if d.sheet else f"{d.document} page {d.page}")
        aside.append(SetAside(family=label, value=d.total,
                              ref=Ref(source_id=ids.get((d.document, int(d.page)), ""), quote=label, where=where),
                              reason=reason,
                              note=f"{d.total} {plural(d.device)} on {d.sheet or where} set aside ({reason}); {kept} on the "
                                   "new-work sheets"))
    return kept, aside


# ---- Demolition Scope (T-G1) -------------------------------------------------------------------------------

# A unit of one of these statuses prints in the Demolition Scope. new and future do not.
_ACTION = {
    "demolish": "demo",
    "demolish_with_work": "demo",
    "existing_remain": "existing to remain",
    "relocate": "relocation",
}


def demolition_lines(units: tuple[Unit, ...]) -> tuple[DemolitionLine, ...]:
    """One Demolition Scope line per family, action and note, in the order the units first show that group.

    demolish and demolish_with_work are "demo". existing_remain is "existing to remain". relocate is
    "relocation". new and future give no line. A demolish unit has no note; the note of a demolish_with_work unit
    is its reason text, so a unit with named work prints its own line, apart from the plain demo line, and units
    with the same named work print together. A blank reason is no note. count is the sum of Unit.count. refs is
    the union of the units' refs, in first-seen order.
    """
    groups: dict[tuple[str, str, str], dict] = {}
    order: list[tuple[str, str, str]] = []
    for unit in units:
        action = _ACTION.get(unit.status)
        if action is None:
            continue
        note = unit.reason.strip() if unit.status == "demolish_with_work" else ""
        key = (unit.family, action, note)
        group = groups.get(key)
        if group is None:
            group = {"count": 0, "refs": []}
            groups[key] = group
            order.append(key)
        group["count"] += unit.count
        for ref in unit.refs:
            if ref not in group["refs"]:
                group["refs"].append(ref)
    lines = []
    for family, action, note in order:
        group = groups[(family, action, note)]
        lines.append(DemolitionLine(family, action, group["count"], tuple(group["refs"]), note))
    return tuple(lines)


def attach_demolition(job: Job) -> Job:
    """Set `Job.demolition` from the units on the job (T-G1).

    The run calls this right after `takeoff.attach`, so the units are the takeoff register's. A job with no
    units keeps an empty Demolition Scope.
    """
    return dataclasses.replace(job, demolition=demolition_lines(job.units))
