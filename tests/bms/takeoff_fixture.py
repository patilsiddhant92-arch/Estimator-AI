"""The invented takeoff fixture (takeoff pass plan 2026-10-11, Task 1.2): "Invented Hall", job 00-1111, one document,
Mech.pdf. Every name and number is invented. It has the defect of the first live run in small: five new air handlers
and five exhaust fans, each drawn on several plan sheets (a duct plan and a piping plan of one attic, two part plans
of it, and a demolition plan that also shows one old unit of each kind), so the plan placements count above the
schedules; and a typical unit, FCU-1, drawn 25 times on one floor and 30 on the next.

The data is in `fixtures/takeoff/`: `sheets.json` (the catalogue's sheets and their text, one label per line),
`reading.json` (what the reading found: schedules, device counts, notes), `ledger.json` (the completed ledger, in
`Ledger.to_dict` form) and `answer.json` (the correct takeoff register for this job). The functions here build the
objects the code takes: `catalogue()`, `reading()`, `ledger()`, `dossier()` and `answer()`."""
from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

from estimator.catalogue.documents import JobFolder
from estimator.catalogue.job import Catalogue
from estimator.catalogue.qualify import BidCheck
from estimator.catalogue.register import PageRecord
from estimator.catalogue.sheet_types import Sheet
from estimator.catalogue.tags import TagEntry
from estimator.ledger.facts import Ledger
from estimator.reading.devices import DeviceCount
from estimator.reading.keynotes import Note
from estimator.reading.schedules import Schedule, ScheduleRow
from estimator.writing.dossier import Dossier

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "takeoff"
DOC = "Mech.pdf"
JOB_NAME = "Invented Hall"
JOB_NUMBER = "00-1111"
KINDS = {"AHU": "Air Handling Unit", "EF": "Exhaust Fan", "ERU": "Energy Recovery Unit", "FCU": "Fan Coil Unit"}
_TAG = re.compile(r"^(?:\(D\))?([A-Z]+-\d+)$")      # a label that is a tag alone; "(D)" marks a unit to be demolished


def _load(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def sheets() -> list[dict]:
    """The rows of `sheets.json`: page, number, title, types and text."""
    return _load("sheets.json")


def _tag_entries(rows: list[dict], scheduled: set[str]) -> list[TagEntry]:
    """One entry for every label of the plans except `T` (a device label, not a tag), in tag order."""
    places: dict[str, list[str]] = {}
    for row in rows:
        for line in row["text"].splitlines():
            found = _TAG.match(line)
            if found:
                places.setdefault(found.group(1), []).append(row["number"])
    entries = []
    for tag in sorted(places, key=lambda t: (t.split("-")[0], int(t.split("-")[1]))):
        elsewhere = tuple(dict.fromkeys(places[tag]))
        entries.append(TagEntry(tag, KINDS[tag.split("-")[0]], ("M-601",) if tag in scheduled else (), elsewhere,
                                len(places[tag]) + (1 if tag in scheduled else 0)))
    return entries


def catalogue() -> Catalogue:
    """The job as catalogued, built as `tests/test_inventory_same_floor.py` builds one: ten sheets of Mech.pdf (every
    one Mechanical, with the types the code guesses from the title) and each page's own text."""
    rows = sheets()
    scheduled = {row.tag for schedule in reading().schedules for row in schedule.rows if row.tag}
    return Catalogue(
        JobFolder(f"{JOB_NUMBER} {JOB_NAME}", Path(f"{JOB_NUMBER} {JOB_NAME}"), (), ()),
        tuple(PageRecord(DOC, r["page"], "text", r["text"], 0, True) for r in rows),
        tuple(Sheet(DOC, r["page"], r["number"], r["title"], "Mechanical", tuple(r["types"])) for r in rows),
        (), BidCheck("Qualifies", "", (), (), ()), tuple(_tag_entries(rows, scheduled)), ())


def reading() -> SimpleNamespace:
    """What the reading found, as the readers' own classes: four schedules on M-601, the thermostat counts on three
    plan sheets and one keynote on the demolition plan. `typicals` and `totals` are empty."""
    data = _load("reading.json")
    schedules = tuple(
        Schedule(s["document"], s["page"], s["sheet"], s["title"], tuple(s["headers"]),
                 tuple(ScheduleRow(**row) for row in s["rows"]), s["type_only"], tuple(s["notes"]),
                 tuple(s["controls_by"]), s["from_text"], s["source"], s["passive"])
        for s in data["schedules"])
    return SimpleNamespace(schedules=schedules, devices=tuple(DeviceCount(**d) for d in data["devices"]),
                           notes=tuple(Note(**n) for n in data["notes"]), typicals=(), totals=())


def ledger() -> Ledger:
    """The completed ledger (`ledger.json`): the schedules pass settled the families, tags and counts (AHU 5, EF 5, ERU
    1, FCU 1; each count fact's quote is the dossier's counts line, with its "plan placements" clause), the plans pass
    added a note about the units to be demolished and one about the typical FCU-1, and the sequence pass asked about
    the measuring station marked future."""
    return Ledger.from_dict(_load("ledger.json"))


_SHEET_TEXT = re.compile(r"^.+?, (?P<document>.+?) page (?P<page>\d+) \(sheet text\)$")


def dossier() -> Dossier:
    """A dossier of this job as far as the planner and the takeoff read it: its `sources` are the ledger's, and
    `sheet_pages` gives the (document, page) of each sheet's own text (7c), one id per sheet. It has no text."""
    sources = dict(ledger().sources)
    pages = {sid: (m["document"], int(m["page"])) for sid, where in sources.items()
             if (m := _SHEET_TEXT.match(where))}
    return Dossier(job_name=JOB_NAME, text="", images=(), sources=sources, families=(), device_totals={}, counts={},
                   stats={}, sheet_pages=pages)


def answer() -> dict:
    """The correct takeoff register for this job (`answer.json`): ten sheets, fourteen units, no set-aside (the code
    works out the excluded sheets' counts) and one future item, as the AI's answer to the takeoff request."""
    return _load("answer.json")


# ---- the run tests' takeoff answerer (plan Task 1.5) ------------------------------------------------------------------

_SHEET_LINE = re.compile(r"^(?P<document>.+?) \| page (?P<page>\d+) \| (?P<number>.+?) \| .* \| text: (?P<text>\S+) \| "
                         r"labels: (?P<labels>.*)$")
_FACT_LINE = re.compile(r"^(?P<id>F\d+) \w+ \S+ = (?P<value>.*?) \[\w+\] “(?P<quote>.*)” \(")
_ROW_LINE = re.compile(r"^(?P<tag>[^\s:]+): (?P<cells>.*)$")
_QUANTITY = re.compile(r"(?:^|; )(?:QTY|QUANTITY)[^=;]*=\s*(\d+)\s*(?:;|$)", re.I)


def _section(prompt: str, heading: str) -> list[str]:
    lines, inside = [], False
    for line in prompt.splitlines():
        if line.startswith("## "):
            inside = line == f"## {heading}"
            continue
        if inside and line.strip() and line != "(none)":
            lines.append(line)
    return lines


def takeoff_answer(request: dict) -> dict:
    """A plain answer to any takeoff request, from its prompt alone: every listed sheet `new_work`, its area its
    number (or its page), `counts_units` true; one `new` unit per scheduled tag (its count the schedule's numeric
    quantity, else 1), citing the first fact line that names it. A job whose ledger has no fact naming the tag (the
    run tests' reading passes answer no facts) cites the text of the first sheet whose labels list it."""
    prompt = request["prompt"]
    sheets, labelled = [], []
    for line in _section(prompt, "Sheets"):
        found = _SHEET_LINE.match(line)
        if not found:
            continue
        number = "" if found["number"] == "-" else found["number"]
        sheets.append({"document": found["document"], "page": int(found["page"]), "number": number,
                       "kind": "new_work", "area": number or f"page {found['page']}", "counts_units": True,
                       "reason": "Invented: every sheet counts.", "refs": []})
        labelled.append((found["text"], found["number"], [label.rsplit(" x", 1)[0]
                                                          for label in found["labels"].split(", ")]))
    facts = [m for line in _section(prompt, "Ledger facts") if (m := _FACT_LINE.match(line))]
    units, seen = [], set()
    for line in _section(prompt, "Schedules"):
        found = _ROW_LINE.match(line)
        if not found or found["tag"] == "-" or found["tag"] in seen or "=" not in found["cells"]:
            continue
        tag = found["tag"]
        seen.add(tag)
        word = re.compile(rf"(?<![\w-]){re.escape(tag)}(?![\w-])")
        fact = next((f for f in facts if word.search(f["quote"]) or word.search(f["value"])), None)
        if fact is not None:
            ref = {"source_id": fact["id"], "quote": tag, "where": "invented"}
        else:
            text, where = next(((t, n) for t, n, labels in labelled if tag in labels and t != "-"), (None, None))
            if text is None:
                continue                    # nothing to cite: the check names the tag
            ref = {"source_id": text, "quote": tag, "where": where}
        quantity = _QUANTITY.search(found["cells"])
        units.append({"family": re.match(r"[A-Za-z]*", tag).group(0) or tag, "tag": tag, "labels": [tag],
                      "status": "new", "count": int(quantity.group(1)) if quantity else 1, "sheets": [],
                      "refs": [ref], "serves": "", "service": "", "with_plant": False,
                      "reason": ""})
    return {"sheets": sheets, "units": units, "set_aside": [], "future_items": [], "questions": []}
