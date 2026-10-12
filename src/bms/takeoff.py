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
    """The job with the register on it: `sheets`, `units`, `set_aside` and `future_items` only. No count changes.
    The set-asides the planner already made from the register (Stage 2, `admit`) are kept after the register's own."""
    planned = tuple(a for a in job.set_aside if a not in takeoff.set_aside)
    return dataclasses.replace(job, sheets=takeoff.sheets, units=takeoff.units,
                               set_aside=(*takeoff.set_aside, *planned), future_items=takeoff.future_items)


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


def attach_device_set_asides(job: Job, devices, sheet_pages: dict | None = None) -> Job:
    """The job with every device label's set-asides (`device_tally` over `job.sheets`) after its own, each once."""
    labels = list(dict.fromkeys(d.label for d in devices or ()))
    found = [a for label in labels for a in device_tally(devices, job.sheets, label, sheet_pages)[1]]
    new = tuple(a for a in found if a not in job.set_aside)
    return dataclasses.replace(job, set_aside=(*job.set_aside, *new)) if new else job


# ---- T-009 (estimator ruling 21): the plan count of a thermostat or space sensor prints -----------------------------

PLAN_COUNT_REASON = "plan count prints"
_LABEL_FILE = Path(__file__).resolve().parents[2] / "assets" / "reading_lists" / "devices.json"
# the Playbook shape slots whose line is a thermostat or a space, room, zone or wall temperature sensor
# (playbook/shapes.json); "space_temperature_humidity" is a humidity sensor too (label T/H), "extend_thermostat_wiring"
# is wiring: both stay out
PLAN_COUNT_SLOTS = frozenset({"space_sensor", "space_temperature", "space_thermostat", "thermostat",
                              "alternate_thermostat", "mau_space_temperature", "remote_space_sensor",
                              "bms_space_sensor"})
_SPACE_KIND = (r"(?:space|room|zone|wall)\s+(?:temp(?:erature)?\s+)?(?:sensors?|transmitters?|thermostats?)"
               r"|(?:space|room|zone|wall)\s+temp(?:erature)?")
_KIND_NAME = re.compile(rf"\b(?:thermostats?|{_SPACE_KIND})\b", re.I)
_SPACE_NAME = re.compile(rf"\b(?:{_SPACE_KIND})\b", re.I)
# a name with one of these words is another kind of line, whatever its slot or its other words
_OTHER_KIND = re.compile(r"humidity|pressure|\bco2?\b|discharge|mixed|outside|duct|wiring|"
                         r"\bwire|extend|relocat|damper|valve|interlock", re.I)
# these words make another kind of line only when the name does not say space, room, zone or wall temperature sensor:
# "Return Air Temperature Sensor" is out, "Room Temperature Sensor with Occupancy Override" is in
_SOFT_OTHER_KIND = re.compile(r"occupancy|return|supply|status|enable", re.I)
NOTE_FORM = "{other} not printed ({why}); the plan count {plan} of {word} prints"
# the sum ruling L1 left out (`Count.added_up`) is kept too, but it is never a count of the job: the "*Verify" line
# does not name it (`render._verify_lines` knows it by "(ruling L1")
ADDED_UP_FORM = ("{other} added up over the sheets, not a count (ruling L1; {why}); "
                 "the plan count {plan} of {word} prints")
_PLAN_IN_NOTE = re.compile(r"the plan count (\d+) of ")


def plan_count_labels(path: Path | None = None) -> tuple[str, ...]:
    """The plan labels whose count is a thermostat count: `plan_count_labels` of assets/reading_lists/devices.json
    (the estimator adds a label there, never in code). () when the file has none."""
    data = json.loads(Path(path or _LABEL_FILE).read_text(encoding="utf-8"))
    return tuple(str(label) for label in data.get("plan_count_labels", ()))


def is_plan_counted_kind(name: str, slot: str = "") -> bool:
    """True for a thermostat or a space, room, zone or wall temperature sensor line: its slot is one of
    `PLAN_COUNT_SLOTS` or its name says so, and its name is not another kind of line (humidity, pressure, CO2,
    discharge, outside or duct air, wiring, a damper, a valve; or occupancy, return, supply, status or enable when it
    does not say space, room, zone or wall temperature sensor)."""
    name = " ".join(str(name or "").split())
    if _OTHER_KIND.search(name) or (_SOFT_OTHER_KIND.search(name) and not _SPACE_NAME.search(name)):
        return False
    return slot in PLAN_COUNT_SLOTS or bool(_KIND_NAME.search(name))


def _counted_rows(devices, sheets, label: str) -> list:
    """The device rows of `label` on the sheets that count (`device_tally` keeps the same rows)."""
    by_key = {_sheet_key(s): s for s in sheets or ()}
    rows = []
    for d in devices or ():
        sheet = by_key.get((d.document, int(d.page)))
        if d.label == label and d.total > 0 and (sheet is None or sheet.counts_units):
            rows.append(d)
    return rows


def _block_plan_count(job: Job, system, devices, labels, sheet_pages, ledger):
    """(the plan count, its Refs, the device word) of one block: the thermostat labels counted on the new-work sheets
    of the areas of the block (the areas of the sheets its counted units are drawn on, as `_device_lines` finds them),
    one `Ref` for each counted sheet; None when the block has no area or the plans draw none."""
    prefixes = _system_prefixes(job, system, ledger)
    units = [u for u in job.units if u.family in prefixes]
    tags = {u.tag for u in units}
    units += [u for u in job.units if u not in units and u.serves and u.serves in tags]
    counted = {s.number for u in units if u.status in COUNTED_STATUSES for s in job.sheets if s.number in u.sheets}
    areas = {s.area for s in job.sheets if s.number in counted and s.area}
    if not areas:
        return None
    mine = [row for row in devices or ()
            if (sheet := _sheet_of(job, row.document, row.page, row.sheet)) is not None and sheet.area in areas]
    ids = {(doc, int(page)): sid for sid, (doc, page) in (sheet_pages or {}).items()}
    refs: list[Ref] = []
    total, word = 0, ""
    for label in labels:
        for row in _counted_rows(mine, job.sheets, label):
            total += row.total
            word = word or str(row.device).split("/")[0].strip()
            where = f"{row.sheet}, {row.document} page {row.page}" if row.sheet else f"{row.document} page {row.page}"
            ref = Ref(source_id=ids.get((row.document, int(row.page)), ""), quote=label, where=where)
            if ref not in refs:
                refs.append(ref)
    return (total, tuple(refs), word) if total > 0 else None


def _count_numbers(count) -> list:
    """Every number a Count holds, with the Ref that gives it (None for a value with no source) and whether it is the
    sum ruling L1 left out: the value once for each source, the other counts, then the L1 sum."""
    entries = []
    if count.value is not None:
        entries += [(count.value, r, False) for r in count.sources] or [(count.value, None, False)]
    entries += [(o.value, o.ref, False) for o in count.others]
    if count.added_up is not None:
        entries.append((count.added_up.value, count.added_up.ref, True))
    return entries


def _plan_in_note(aside: SetAside) -> int | None:
    """The plan count a "plan count prints" set-aside was recorded for (from its note), None when the note has none."""
    found = _PLAN_IN_NOTE.search(aside.note or "")
    return int(found[1]) if found else None


def apply_plan_counts(job: Job, devices, sheet_pages: dict | None = None, ledger=None,
                      typed: frozenset = frozenset()) -> Job:
    """Estimator ruling 21 (2026-10-12). A thermostat or space sensor line whose plan count is below another number it
    holds (the sequence's one per unit) prints the plan count: the line's `quantity` becomes the plan count, backed by
    one `Ref` for each counted sheet (`_block_plan_count`), no other count; every number it held becomes a `SetAside`
    with reason "plan count prints", `family` the line's id, the number's own `Ref`, so none is lost; the line is
    flagged "quantity" (whatever flag it had). The render builds the "*Verify" line from the set-asides
    (`render._verify_lines`). A line with no plan count, a plan count not below the other numbers, another kind of
    line, or whose (system key, id) is in `typed` (the estimator typed its count) is left as it is. The step's own
    set-asides follow the line: a line it reduces again gets a new set (the old ones go), and a line that no longer
    prints the plan count they were recorded for (a typed count, a rewrite) loses them, as does a line the job no
    longer has. Run twice it gives the same job: the line then holds only the plan count. The run calls it after the
    writers, after the decisions' count rewrites and after the revise (`run._plan_counts`), so a later step that
    copies the sequence's number back is reduced again. Every other device keeps the highest-prints rule."""
    from bms.counts import NO_SOURCE_QUOTE

    labels = plan_count_labels()
    if not labels or not devices:
        return job
    systems, asides, stale = [], [], set()
    for system in job.systems:
        found = _block_plan_count(job, system, devices, labels, sheet_pages, ledger)
        lines = []
        for d in system.devices:
            top = d.quantity.highest()
            if (found is None or (system.key, d.id) in typed or not is_plan_counted_kind(d.name, d.slot)
                    or top is None or top <= found[0]):
                lines.append(d)
                stale |= {a for a in job.set_aside if a.reason == PLAN_COUNT_REASON and a.family == d.id
                          and _plan_in_note(a) != top}       # it no longer prints the plan count they describe
                continue
            plan, refs, word = found
            stale |= {a for a in job.set_aside if a.reason == PLAN_COUNT_REASON and a.family == d.id}
            entries = _count_numbers(d.quantity)
            kept = tuple(dict.fromkeys((*refs, *(r for n, r, summed in entries
                                                 if n == plan and r is not None and not summed))))
            other: list[tuple[int, Ref, bool]] = []
            for n, r, summed in entries:             # one set-aside for each number and each source that gives it
                entry = (n, r if r is not None else Ref("", NO_SOURCE_QUOTE, ""), summed)
                if n != plan and entry not in other:
                    other.append(entry)
            for n, ref, summed in sorted(other, key=lambda entry: -entry[0]):
                why = ref.where or ref.quote or "no source"
                form = ADDED_UP_FORM if summed else NOTE_FORM
                asides.append(SetAside(family=d.id, value=n, ref=ref, reason=PLAN_COUNT_REASON,
                                       note=form.format(word=plural(word or "thermostat"), other=n, why=why,
                                                        plan=plan)))
            lines.append(dataclasses.replace(d, quantity=dataclasses.replace(d.quantity, value=plan, sources=kept,
                                                                              others=(), added_up=None),
                                             flag="quantity"))
        systems.append(dataclasses.replace(system, devices=tuple(lines)) if tuple(lines) != system.devices else system)
    # a line the job no longer has (a revise or a rewrite removed it) keeps no set-aside that says its plan count prints
    lines_now = {d.id for system in systems for d in system.devices}
    stale |= {a for a in job.set_aside if a.reason == PLAN_COUNT_REASON and a.family not in lines_now}
    kept_asides = tuple(a for a in job.set_aside if a not in stale)
    new = tuple(dict.fromkeys(a for a in asides if a not in kept_asides))
    if tuple(systems) == job.systems and kept_asides == job.set_aside and not new:
        return job
    return dataclasses.replace(job, systems=tuple(systems), set_aside=(*kept_asides, *new))


# ---- Task 2.2: the sources a family's count may use ---------------------------------------------------------------

# the counts cross-check's quotes (`bms.counts.LOCATED_QUOTE`, `SEEN_QUOTE`), kept here so this module needs no import
# of the cross-check
_SHEET_COUNTS = ("located on the sheet text", "counted on the sheet picture")
_PLACEMENTS = "plan placements"
# why a scheduled unit that is not counted takes its schedule's number out of the count
_STATUS_REASON = {"demolish": "demolition sheet", "demolish_with_work": "demolition sheet",
                  "existing_remain": "existing to remain", "relocate": "existing to remain", "future": "future item"}
QUESTION = "How many {family}? {printed} print from the new-work sheets; the code counted {counted}."
_BREAKDOWN = re.compile(r"([A-Za-z]+[\w.]*(?:-[\w.]+)*)\s+(\d+)")


@dataclass(frozen=True)
class Recount:
    """A family's plan placements counted again over the sheets the register admits, by its areas (Task 2.1): the
    count, and why a different placement count of the code is set aside."""
    value: int
    reason: str


def _plain_family(family: str) -> str:
    return re.sub(r"\s+", "", str(family or "")).upper()


def family_rows(register, family: str) -> list[Unit]:
    """The register's unit rows of one family (by its prefix, any case)."""
    key = _plain_family(family)
    return [u for u in getattr(register, "units", ()) or () if _plain_family(u.family) == key]


def counted_tags(register, family: str) -> tuple[str, ...]:
    """The tags of the family's units whose status counts (`COUNTED_STATUSES`), in register order."""
    return tuple(dict.fromkeys(u.tag for u in family_rows(register, family) if u.status in COUNTED_STATUSES))


def uncounted_tags(register, family: str) -> frozenset[str]:
    """The tags (plain) of the family's units whose status does not count: they are in no new-work count."""
    return frozenset(_plain(u.tag) for u in family_rows(register, family) if u.status not in COUNTED_STATUSES)


def recount(catalogue, register, typicals=()) -> dict[str, Recount]:
    """Each register family's plan placements (prefix in capitals -> `Recount`): the family's counted tags placed over
    the sheets the register admits (`admissible_pages`, the governing pages only) and counted by its areas
    (`area_groups`), the floors of the typical sheets applied. The reason a different code count is set aside: a
    sheet the register does not count is one the code counted ("demolition sheet", or its kind's reason), else the
    code added up sheets of one area ("part plan of one area"). Only the sheets the code counted decide it (the code
    already reads no demolition plan, T-005a).. Empty with no register sheets."""
    from estimator.reading.inventory import placements
    from estimator.reading.revisions import governing_pages, typical_places

    sheets = tuple(getattr(register, "sheets", ()) or ())
    if not sheets:
        return {}
    pages = admissible_pages(sheets) & governing_pages(catalogue, (), typical_places(typicals))
    groups = area_groups(sheets)
    by_number = {s.number: s for s in sheets if s.number}
    out: dict[str, Recount] = {}
    for family in dict.fromkeys(_plain_family(u.family) for u in getattr(register, "units", ()) or ()):
        tags = counted_tags(register, family)
        if not tags:
            out[family] = Recount(0, "demolition sheet")
            continue
        found = placements(catalogue, tags, typicals, pages=pages, groups=groups, admitted=pages)
        code = placements(catalogue, tags, typicals)
        shown = {name for p in code.values() for name in p.on_plans}     # the sheets the code counted
        excluded = [by_number[name] for name in shown if name in by_number and not by_number[name].counts_units]
        out[family] = Recount(sum(p.count for p in found.values()),
                              aside_reason(excluded[0]) if excluded else "part plan of one area")
    return out


def _on_excluded_sheets(where: str, sheets) -> bool:
    """A cross-check count whose place names only sheets whose units do not count."""
    named = [s for s in sheets if s.number and re.search(rf"(?<![\w-]){re.escape(s.number)}(?![\w-])", where or "")]
    return bool(named) and not any(s.counts_units for s in named)


def admit(prefix: str, entries, register, recount: dict | None = None,
          breakdown: dict | None = None) -> tuple[list, list[SetAside]]:
    """The numbers a family's count may print from, by the register (Task 2.2): `entries` are (number, refs) as the
    planner reads them (`plan_read.Reader._entries`). Returns (the entries kept, the numbers set aside).

    With no register, or no register row of the family, every entry is kept and nothing is set aside. Otherwise:
    - an entry the register sets aside (its family, number and source) is dropped (it is already in the register's
      set-asides);
    - a cross-check count whose sheets all have `counts_units` false is set aside;
    - a number above the register's count that the family's uncounted units account for (a scheduled unit the
      register shows for removal, kept as it is, relocated or future, each cited) is set aside for their reason;
    - a "plan placements" number that differs from the recount over the admitted sheets (`recount`) is set aside
      and the recount kept in its place (none when the recount is 0);
    - the register's own count is added: the sum of `Unit.count` over the family's units whose status counts,
      citing the first such unit's refs.
    The highest kept entry prints (the planner's rule, unchanged).

    `breakdown` (T-007b): the counts line's sheet by sheet text of a "plan placements" number ({number: "M-401 5;
    M-402 5; MD-401 5"}). With it a dropped placement number is set aside by sheet, one `SetAside` for each reason
    (`_split_by_sheet`), each with its own number, its sheets named in its note, and the printed count."""
    rows = family_rows(register, prefix) if register is not None else []
    if not rows:
        return list(entries), []
    sheets = tuple(getattr(register, "sheets", ()) or ())
    given = [a for a in getattr(register, "set_aside", ()) or () if _plain_family(a.family) == _plain_family(prefix)]
    counted_rows = [u for u in rows if u.status in COUNTED_STATUSES]
    counted = sum(u.count for u in counted_rows)
    uncounted = [u for u in rows if u.status not in COUNTED_STATUSES]
    explained = counted + sum(u.count for u in uncounted)
    again = (recount or {}).get(_plain_family(prefix))
    register_refs = tuple(counted_rows[0].refs) if counted_rows else ()
    kept: list = []
    aside: list[SetAside] = []
    family = rows[0].family

    def set_aside(n: int, ref: Ref, reason: str) -> None:
        if not any((a.value, a.reason) == (n, reason) for a in aside):
            aside.append(SetAside(family=family, value=n, ref=ref, reason=reason,
                                  note=f"{n} set aside ({reason}); {counted} {family} on the new-work sheets"))

    for n, refs in entries:
        ref = refs[0] if refs else Ref(source_id="", quote="", where="")
        sid = str(ref.source_id).strip().strip("[]")
        if any(a.value == n and str(a.ref.source_id).strip().strip("[]") == sid for a in given):
            continue
        if ref.quote in _SHEET_COUNTS and _on_excluded_sheets(ref.where, sheets):
            set_aside(n, ref, aside_reason(next(s for s in sheets if s.number and s.number in ref.where)))
            continue
        if uncounted and counted < n <= explained:
            set_aside(n, ref, _STATUS_REASON.get(uncounted[0].status, "not a unit of this family"))
            continue
        if str(ref.quote).startswith(_PLACEMENTS) and again is not None and again.value != n:
            parts = _split_by_sheet((breakdown or {}).get(n, ""), n, register)
            if parts:
                for reason, value, named in parts:
                    # the same number and reason on other sheets is another part, kept (T-007b review)
                    note = (f"{value} set aside ({reason}: {', '.join(named)}); {counted} {family} on the "
                            "new-work sheets")
                    if not any((a.value, a.reason, a.note) == (value, reason, note) for a in aside):
                        aside.append(SetAside(family=family, value=value, ref=ref, reason=reason, note=note))
            else:
                set_aside(n, ref, again.reason)
            if again.value:
                kept.append((again.value, register_refs or tuple(refs)))
            continue
        kept.append((n, tuple(refs)))
    if counted_rows:
        kept.append((counted, register_refs))
    return kept, aside


def count_question(family: str, printed: int | None, counted: int | None, name: str = "") -> str | None:
    """The one question for a family whose printed count fell below the code's count (Task 2.2), else None. `family`
    is the prefix; with the family's `name` it reads "How many Air Handling Units (AHU)? 5 print from the new-work
    sheets; the code counted 21." (T-007b: the name in the plural, the prefix in brackets); with no name, the prefix
    alone."""
    if printed is None or counted is None or printed >= counted:
        return None
    label = f"{_plural(name)} ({family})" if name.strip() else family
    return QUESTION.format(family=label, printed=printed, counted=counted)


def _split_by_sheet(breakdown: str, n: int, register) -> list[tuple[str, int, list[str]]] | None:
    """T-007b: the dropped placement number `n` given the sheet by sheet by the counts line ("M-401 5; M-402 5;
    MD-401 5"), as [(reason, number, sheets)], one row per reason in the order the sheets first show it. Each sheet's
    reason is its own: a sheet the register does not count has its kind's reason (`aside_reason`: "demolition
    sheet"); the sheets it counts are "part plan of one area" when they are all of one area, else "same unit labelled
    again". None when the line names no sheet, names a sheet the register does not list, or its numbers do not add up
    to `n` (the caller keeps the single reason then)."""
    by_number = {s.number: s for s in getattr(register, "sheets", ()) or () if s.number}
    pairs = [(m.group(1), int(m.group(2))) for m in _BREAKDOWN.finditer(breakdown or "")]
    if not pairs or sum(v for _, v in pairs) != n or any(name not in by_number for name, _ in pairs):
        return None
    counted_areas = {" ".join(by_number[name].area.split()).casefold() for name, _ in pairs
                     if by_number[name].counts_units}
    rows: dict[str, list] = {}
    for name, value in pairs:
        sheet = by_number[name]
        if sheet.counts_units:
            reason = "part plan of one area" if len(counted_areas) <= 1 else "same unit labelled again"
        else:
            reason = aside_reason(sheet)
        row = rows.setdefault(reason, [0, []])
        row[0] += value
        if name not in row[1]:
            row[1].append(name)
    return [(reason, value, sheets) for reason, (value, sheets) in rows.items()]


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


# ---- the writer sees the register (Stage 2, Task 2.5) -----------------------------------------------------------

REGISTER_HEADING = "Takeoff register for this system"
_PREFIX = re.compile(r"^([A-Za-z]+)")


def _system_prefixes(job: Job, system, ledger) -> set[str]:
    """The ledger family prefixes of the system's families: from their tags, and from the ledger's family facts whose
    value is the family's name."""
    found: set[str] = set()
    names = {family.name for family in system.families}
    for family in system.families:
        found |= {m.group(1) for tag in family.tags if (m := _PREFIX.match(tag))}
    facts = getattr(ledger, "facts", None) or {}
    found |= {str(f.subject) for f in facts.values() if f.kind == "family" and str(f.value) in names}
    return found


def _sheet_of(job: Job, document: str, page: int, number: str):
    return next((s for s in job.sheets if (s.document, s.page) == (document, page)),
                next((s for s in job.sheets if number and s.number == number), None))


def _plural(name: str) -> str:
    return name if name.endswith("s") else f"{name}s"


def _device_lines(job: Job, units: list[Unit], devices) -> list[str]:
    """One line per device label the reading counted on the sheets of the system's areas (the areas of the sheets its
    counted units are drawn on), by `device_tally` (Task 2.1): the number on the sheets that count, then the numbers
    set aside with their reason, "Thermostats: 30 on the new-work sheets; 9 set aside (demolition sheet)"."""
    counted = {s.number for u in units if u.status in COUNTED_STATUSES for s in job.sheets if s.number in u.sheets}
    areas = {s.area for s in job.sheets if s.number in counted and s.area}
    if not areas:
        return []
    mine = [row for row in devices or ()
            if (sheet := _sheet_of(job, row.document, row.page, row.sheet)) is not None and sheet.area in areas]
    lines = []
    for label in dict.fromkeys(row.label for row in mine):
        kept, aside = device_tally(mine, job.sheets, label)
        reasons: dict[str, int] = {}
        for row in aside:
            reasons[row.reason] = reasons.get(row.reason, 0) + row.value
        device = next(row.device for row in mine if row.label == label)
        line = f"{_plural(device)}: {kept} on the new-work sheets"
        line += "".join(f"; {n} set aside ({reason})" for reason, n in reasons.items())
        lines.append(line)
    return lines


def register_text(job: Job, system, ledger, devices=()) -> str:
    """The takeoff register of one system, for its writer's evidence (`ai_evidence.evidence(register=...)`): the unit
    rows of its families (and the rows that serve its units), with their status, count, sheets, reason and ledger ids;
    the items the takeoff lists as future; the counts set aside for its families; one line per device counted on the
    sheets of its areas (`devices`: the reading's device counts, kept on the sheets that count and set aside on the
    others); what the plans pass understood; then the passages the register cites, as "- [F3] “quote” — where" (never a
    passage line of the evidence, which starts with its id). ""
    when the job has no register for the system. Deterministic."""
    prefixes = _system_prefixes(job, system, ledger)
    units = [u for u in job.units if u.family in prefixes]
    tags = {u.tag for u in units}
    units += [u for u in job.units if u not in units and u.serves and u.serves in tags]
    future = [f for f in job.future_items if f.family in prefixes]
    if not units and not future:
        return ""
    refs: list[Ref] = []

    def cite(found) -> str:
        for ref in found:
            if ref not in refs:
                refs.append(ref)
        ids = dict.fromkeys(f"[{r.source_id.strip('[] ')}]" for r in found)
        return f" {' '.join(ids)}" if ids else ""

    out = [f"{REGISTER_HEADING} (one pass over every sheet of the job). Only a unit with status “new” counts in "
           "this block; a demolished, existing or relocated unit is in the Demolition Scope, never in this block."]
    if units:
        out.append("Units:")
        for unit in units:
            drawn = f", drawn on {', '.join(unit.sheets)}" if unit.sheets else ""
            serves = f", serves {unit.serves}" if unit.serves else ""
            service = f", {unit.service}" if unit.service else ""
            reason = f" {unit.reason.strip()}" if unit.reason.strip() else ""
            out.append(f"- {unit.tag}: {unit.status}, count {unit.count}{drawn}{serves}{service}.{reason}"
                       f"{cite(unit.refs)}")
    if future:
        out.append("Future items (each is a line marked future):")
        out += [f"- {f.family}: {f.item}{cite(f.refs)}" for f in future]
    aside = [s for s in job.set_aside if s.family in prefixes]
    if aside:
        out.append("Counts set aside (not in this block's count):")
        out += [f"- {s.family} {s.value} ({s.reason}){': ' + s.note if s.note else ''}{cite((s.ref,))}"
                for s in aside]
    out += _device_lines(job, units, devices)
    plans = (getattr(ledger, "understanding", None) or {}).get("plans", "")
    if plans:
        out.append(f"What the plans pass understood: {plans}")
    if refs:
        # "- " first: these are the register's citations, never passages of the evidence (`ai_evidence._ENTRY`)
        out.append("The passages the register cites (each is given above under its own id, or in the ledger):")
        out += [f"- [{r.source_id.strip('[] ')}] “{r.quote}” — {r.where}" for r in refs]
    return "\n".join(out) + "\n"
