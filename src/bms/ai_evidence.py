"""The evidence the AI steps read (workstream 5, private to `bms.ai`): one system's passages of the job dossier, and
every source id's text for the QC pass.

The dossier (`estimator.writing.dossier`) is one plain-text document: numbered parts ("== 2. SEQUENCE OF OPERATION
=="), place lines ("--- M-101, Drawings.pdf page 2 ---"), sequence section lines ("--- [Q7] C. EXHAUST FANS ---")
and entries, each starting with its source id ("[S41] ...") with indented lines under it (a schedule's columns).
A system's evidence is the entries of this job that are about it, each copied whole with its id, so the writer cites
them by id. Nothing here comes from another job, a template or an example; the selection is deterministic.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from bms.model import Ref, System

JOB, SEQUENCE, POINTS, SCHEDULES, COUNTS, DEVICES, NOTES, SPEC = 1, 2, 3, 4, 5, 6, 7, 8
NOTES_LIMIT = 12_000            # characters of notes naming the system, in one system's evidence
CONTROLS_LIMIT = 60_000         # characters of controls sheets' text (whole, else excerpts) in one system's evidence
CONTROLS_MIN = 1_500            # a controls sheet is given in at least this many characters, or the run stops
JOB_WIDE_LIMIT = 8_000          # characters of the job-wide sequence sections (they name no unit tag), in each evidence
JOB_WIDE_FACTS_MAX = 30         # job-wide ledger facts (they name no unit tag) listed in each evidence
MARKS_MAX = 20                  # passages listed in each marks checklist (FUTURE; integral with the unit)
QUOTE_MAX = 300                 # characters of a fact's quote in a checklist
EXCERPT_OVER = 1_500            # a plan sheet's text longer than this is given as excerpts about the system (T-005d)
EXCERPT_REACH = 300             # characters each side of a mention in an excerpt
EXCERPTS_MAX = 12               # excerpts of one sheet's text
FACTS_MAX = 60                  # ledger facts listed in the checklist of one system's evidence
SPEC_LIMIT = 12_000             # characters of controls spec passages, in one system's evidence
RANGE_LIMIT = 200               # a tag range longer than this is not expanded

_PART = re.compile(r"^== (\d)\. .+ ==\s*$")
_ENTRY = re.compile(r"^\[([A-Z]{1,3}\d+[a-z]?)\]\s?(.*)$")
_SECTION = re.compile(r"^--- \[(Q\d+)\] (.+?) ---\s*$")
_PLACE = re.compile(r"^--- (.+?) ---\s*$")
_TAG = re.compile(r"\b([A-Z]{1,5})[- ]?(\d{1,4}[A-Z]?)\b")
_RANGE = re.compile(r"\b([A-Z]{1,5})[- ]?(\d{1,4})\s*(?:THRU|THROUGH|TO|thru|through|to)\s*(?:([A-Z]{1,5})[- ]?)?"
                    r"(\d{1,4})\b")
_PLACEMENTS = re.compile(r"plan placements \d+ \(([^)]*)\)")
_DEVICE_SHEETS = re.compile(r"—\s*(.+)$")
_PICTURE_ID = re.compile(r"\bI\d+\b")
_INTEGRATION_WORDS = re.compile(r"integrat|gateway|bacnet|modbus|lonworks|interface|protocol", re.I)
_SCHEDULE_NOTE = ("Note:", "Unit controls by:")
# ---- T-005d: what the writer must see and act on (rulings 6, 7, 10; addendum) -------------------------------------
SHEET_TEXT_PLACE = "7c PLAN SHEET TEXT"     # the place line the dossier puts over the plan sheets' own text
# a sheet whose title says it draws the controls: its text is given whole and before any other sheet's
_CONTROLS_SHEET = re.compile(r"\b(?:CONTROLS?|SEQUENCES?|POINTS?|DIAGRAMS?|SCHEMATICS?|BMS|BAS|ATC|DDC)\b", re.I)
# words a passage marks an item with: FUTURE (ruling 7), shipped loose or field mounted (ruling 10), furnished in
# the unit (an item to notice, ruling 7)
_FUTURE = re.compile(r"\bFUTURE\b|[\[(]\s*future\s*[\])]")
# what an item is: FUTURE marks an item only when one of these is beside it ("FUTURE SUPPLY AIR STATIC PRESSURE AI",
# "[FUTURE] SPACE SENSOR"); "CAP FOR FUTURE CONNECTION" marks no item (should fix 1)
_ITEM = re.compile(r"\b(?:sensors?|switch(?:es)?|thermostats?|detectors?|freezestats?|aquastats?|stats?|actuators?|"
                   r"transmitters?|stations?|relays?|monitors?|meters?|transducers?|valves?|dampers?|vfds?|drives?|"
                   r"fans?|pumps?|controllers?|panels?|points?|alarms?|status|pressure|temperature|humidity|flow|"
                   r"level|co2|ai|ao|bi|bo|units?|coils?|heaters?|boilers?|chillers?|starters?)\b", re.I)
FUTURE_REACH = 40               # characters each side of FUTURE an item word must be in
# a sequence section heading that says it holds the whole job's points
_GENERAL_HEADING = re.compile(r"\b(?:GENERAL|ALL\s+(?:SYSTEMS|EQUIPMENT|UNITS)|COMMON|GLOBAL|SYSTEM[\s-]*WIDE|"
                              r"BUILDING[\s-]*WIDE|CHANGEOVER|OUTSIDE\s+AIR|(?:BMS|BAS|DDC|ATC|CONTROLS?)\s+"
                              r"(?:SYSTEM|GENERAL|REQUIREMENTS|NETWORK|POINTS)|ALARMS?|SCHEDULING|TRENDS?|TRENDING|"
                              r"(?:NIGHT\s+)?SETBACK|OCCUPANCY|GLOBAL\s+POINTS?)\b", re.I)
# the words that name a kind of equipment (a family of its own): a sequence section or a fact that names one belongs
# to that family's writer, not to every writer (lead fix 2, T-005d). Devices (valves, dampers, drives) are not here.
_EQUIPMENT = re.compile(r"\b(?:units?|heaters?|fans?|pumps?|boilers?|chillers?|coils?|terminals?|vav|boxes|ahus?|"
                        r"rtus?|ervs?|hrvs?|doas|vrf|splits?|condens(?:er|ers|ing)|towers?|exchangers?|humidifiers?|"
                        r"furnaces?|radiators?|convectors?|curtains?|ventilators?|handlers?|cuhs?|uhs?|fcus?|efs?|"
                        r"equipment|tanks?)\b", re.I)
_LOOSE = re.compile(r"\bship(?:ped|s)?\s+loose\b|\bloose\b[^.]{0,30}\bfield\b|\bfield[\s-]+(?:mounted|installed)\b"
                    r"|\bmounted\s+in\s+(?:the\s+)?(?:supply|return|exhaust|outside|outdoor|mixed)[\w\s]{0,12}duct\b",
                    re.I)
_NOTICE = re.compile(r"\b(?:integral|factory[\s-]*(?:furnished|installed|mounted|provided|wired)|furnished\s+(?:with|by)"
                     r"\s+(?:the\s+)?(?:unit|manufacturer|factory))\b", re.I)
_END_DEVICE = re.compile(r"\b(?:sensors?|(?<!disconnect )switch(?:es)?|thermostats?|detectors?|freezestats?|aquastats?|stats?|"
                         r"actuators?|transmitters?|(?:flow|airflow|measuring)\s+stations?|relays?|monitors?|meters?|"
                         r"transducers?)\b", re.I)
# the front end's own words in a note: the BMS, its network, its graphics and training, integration
_FRONT_END_TEXT = re.compile(r"\b(?:BMS|BAS|EMS|building\s+(?:management|automation)|front[\s-]*end|graphics?|"
                             r"training|workstation|network|integrat\w*|BACnet|niagara|tridium|schneider|"
                             r"controls?\s+(?:contractor|vendor))\b", re.I)
# the front end's scope words in the sequence, the spec and the job's own passages: its lines (graphics, training, the
# workstation, the network panel) and who may integrate (an approved or prequalified integrator: a question)
_FRONT_END_SCOPE = re.compile(r"\b(?:front[\s-]*end|graphics?|training|workstations?|network\s+(?:area|level|server)?\s*"
                              r"(?:controllers?|panels?)|integrators?|prequalified|pre-qualified|eligib\w*|"
                              r"certified\s+(?:integrator|installer|contractor)|existing\s+(?:BMS|BAS|front))\b", re.I)
# A name that is only a general kind of equipment says nothing about which units: "Pump" names every sump, booster
# and circulation pump of the job. The planner asks about such a family (bms.plan) and reads this set too.
GENERAL_KINDS = frozenset({"fan", "fans", "equipment", "unit", "units", "pump", "pumps", "heater", "heaters",
                           "damper", "dampers", "device", "devices", "motor", "motors", "system", "systems"})


@dataclass
class Entry:
    """One dossier entry: its source id (None for a remark line), its text as printed (continuation lines joined
    with a newline), the part it is in, the place line above it and the sequence section it belongs to."""
    sid: str | None
    text: str
    part: int
    place: str | None
    section: str | None

    @property
    def body(self) -> str:
        """The entry without its "[S41] " id."""
        return _ENTRY.sub(lambda m: m.group(2), self.text, count=1) if self.sid else self.text


def parse(text: str) -> list[Entry]:
    """The dossier's entries, in order."""
    entries: list[Entry] = []
    part, place, section = 0, None, None
    for line in (text or "").splitlines():
        if not line.strip():
            continue
        m = _PART.match(line)
        if m:
            part, place, section = int(m.group(1)), None, None
            continue
        m = _SECTION.match(line)
        if m:
            section = m.group(1)
            entries.append(Entry(None, line, part, place, section))
            continue
        m = _PLACE.match(line)
        if m:
            if m.group(1) != place and part == SEQUENCE:
                # another page of the same backbone keeps its section; another document starts afresh
                if not (place and _same_document(place, m.group(1))):
                    section = None
            place = m.group(1)
            continue
        m = _ENTRY.match(line)
        if m:
            entries.append(Entry(m.group(1), line, part, place, section if part == SEQUENCE else None))
        elif line[:1].isspace() and entries and entries[-1].sid:
            entries[-1].text += "\n" + line
        else:
            entries.append(Entry(None, line, part, place, None))
    return entries


def _same_document(a: str, b: str) -> bool:
    strip = lambda p: re.sub(r"\s+page \d+$", "", p)
    return strip(a) == strip(b)


def index(text: str, sources: dict[str, str], sections: dict) -> dict[str, str]:
    """Every source id -> its text: an entry's words without its id; a sequence section (Q) its heading and every
    paragraph under it; a picture (I) or any id with no entry, its description from `sources`."""
    entries = [e for e in parse(text) if e.sid]
    found: dict[str, str] = {}
    for entry in entries:
        found[entry.sid] = (found[entry.sid] + "\n" + entry.body) if entry.sid in found else entry.body
    for q, (heading, ids) in (sections or {}).items():
        found[q] = "\n".join([heading, *(found[i] for i in ids if i in found)])
    for sid, where in (sources or {}).items():
        if sid not in found:
            found[sid] = f"Picture: {where}" if sid.startswith("I") else where
    return found


# ---- what a system is: its tags, prefixes and names ------------------------------------------------------------

def plain_tag(tag: str) -> str:
    return re.sub(r"[\s\-_]", "", str(tag)).upper()


def tags_in(text: str) -> set[str]:
    """Every equipment tag a text names, plain ("EF1"); a range ("FCU-1 THRU FCU-4") names each tag in it."""
    found = {plain_tag(a + b) for a, b in _TAG.findall(text or "")}
    for prefix, first, other, last in _RANGE.findall(text or ""):
        if other and other != prefix:
            continue
        lo, hi = int(first), int(last)
        if lo < hi and hi - lo <= RANGE_LIMIT:
            found |= {f"{prefix}{n}" for n in range(lo, hi + 1)}
    return found


def _prefix(tag: str) -> str:
    m = re.match(r"[A-Z]+", plain_tag(tag))
    return m.group(0) if m else ""


def _phrase(name: str) -> re.Pattern | None:
    words = re.findall(r"[a-z0-9]+", (name or "").lower())
    if not words:
        return None
    last = re.sub(r"(?:es|s)$", "", words[-1]) if len(words[-1]) > 3 else words[-1]
    body = r"\W+".join(map(re.escape, [*words[:-1], last]))
    return re.compile(rf"\b{body}(?:s|es)?\b", re.I)


@dataclass(frozen=True)
class _About:
    tags: frozenset[str]
    prefixes: frozenset[str]
    phrases: tuple[re.Pattern, ...]
    cited: tuple[str, ...]

    def names_tag(self, text: str) -> bool:
        return bool(self.tags & tags_in(text))

    def names_phrase(self, text: str) -> bool:
        return any(p.search(text) for p in self.phrases)

    def names(self, text: str) -> bool:
        return self.names_tag(text) or self.names_phrase(text)

    def type_row(self, body: str) -> bool:
        """A schedule row whose first cell is one of the system's tags or type codes."""
        first = body.split("\n", 1)[0].split("|", 1)[0].strip() if "|" in body else ""
        return bool(first) and (plain_tag(first) in self.tags or plain_tag(first) in self.prefixes
                                or self.names_tag(first))


def system_refs(system: System) -> list[Ref]:
    """Every Ref the planner set on the skeleton: the sequence refs, then each family count's sources and others."""
    refs = list(system.sequence_refs)
    for family in system.families:
        refs += list(family.count.sources) + [o.ref for o in family.count.others]
    return refs


def _about(system: System) -> _About:
    tags: set[str] = set()
    for family in system.families:
        for tag in family.tags:
            tags |= tags_in(tag) or {plain_tag(tag)}
    names = [system.name, *(f.name for f in system.families)]
    if tags:
        # a bare general kind ("Pump") is no name phrase for a system with tags: its tags say which units it is
        names = [n for n in names if " ".join(re.findall(r"[a-z0-9]+", (n or "").lower())) not in GENERAL_KINDS]
    phrases = tuple(p for p in dict.fromkeys(_phrase(n) for n in names if n) if p is not None)
    cited = tuple(dict.fromkeys(r.source_id.strip().strip("[]") for r in system_refs(system)))
    return _About(frozenset(tags), frozenset(p for p in map(_prefix, tags) if p), phrases, cited)


# ---- one system's evidence ---------------------------------------------------------------------------------------

def evidence(system: System, text: str, sources: dict[str, str], sections: dict, images, schedules=(),
             ledger=None, front_end: bool = False, register: str = "") -> str:
    """The evidence one system is written from (see `bms.ai.evidence_for`). `ledger` (the reading's facts) adds the
    checklist of the controls facts about it (`_facts_checklist`); `front_end` is the front end's evidence, whose
    notes are the ones in the front end's own words (the BMS, its network, graphics, training, integration).
    `register` (takeoff Task 2.5: `bms.takeoff.register_text`) is printed first, before everything else."""
    about = _about(system)
    entries = parse(text)
    by_part: dict[int, list[Entry]] = {}
    for entry in entries:
        by_part.setdefault(entry.part, []).append(entry)
    ids_in_text = {e.sid for e in entries if e.sid}
    elsewhere = _other_kinds(entries, about)
    sections = sections or {}
    given: set[str] = set()
    head = [register.rstrip("\n"), ""] if register.strip() else []     # the takeoff register, first (Task 2.5)
    out = [*head,
           f"Evidence for {system.name} (system {system.key}), from this job's documents only. Each passage starts "
           "with its source id in square brackets; cite a passage by that id."]

    def block(title: str, chosen: Iterable[Entry], limit: int | None = None, whole: bool = False) -> None:
        """The entries under `title`, at most `limit` characters. `whole` (the controls sheets): an entry that does
        not fit is given as excerpts about the system, and a sheet that cannot be given in CONTROLS_MIN characters
        stops the run with a plain message: a controls sheet is never dropped silently (T-005d must fix 2)."""
        lines: list[str] = []
        used, left, place = 0, 0, None
        for entry in chosen:
            if entry.sid and entry.sid in given:
                continue
            if whole and limit is not None and entry.sid and used + len(entry.text) > limit:
                entry = _fit(entry, about, front_end, limit - used, system)
            if limit is not None and entry.sid and used + len(entry.text) > limit:
                left += 1
                continue
            if entry.place and entry.place != place and entry.part in (SEQUENCE, POINTS, NOTES, SPEC):
                place = entry.place
                lines.append(f"--- {place} ---")
            lines.append(entry.text)
            if entry.sid:
                given.add(entry.sid)
                used += len(entry.text)
        if left:
            lines.append(f"({left} more passages name it; not given here, cut at {limit:,} characters)")
        if any(_ENTRY.match(line) for line in lines):
            out.append("")
            out.append(title)
            out.extend(lines)

    # 0. what the planner cited that is not a passage of the dossier (ledger facts)
    # (the plan count check's own records have no source id or carry its record quotes: not facts of the ledger)
    from bms.counts import LOCATED_QUOTE, NO_SOURCE_QUOTE, SEEN_QUOTE
    facts = [r for r in system_refs(system) if r.source_id.strip("[] ") not in ids_in_text
             and r.source_id.strip("[] ") and r.quote not in (LOCATED_QUOTE, SEEN_QUOTE, NO_SOURCE_QUOTE)
             and not r.source_id.strip("[] ").startswith(("Q", "I"))]
    if facts:
        out += ["", "Ledger facts the planner cited for this system:"]
        for ref in dict.fromkeys(facts):
            out.append(f"[{ref.source_id.strip('[] ')}] “{ref.quote}” — {ref.where}")
            given.add(ref.source_id.strip("[] "))

    # 1. the sequence: the sections the planner cited (whole), sections whose heading names it, paragraphs naming it
    sequence = by_part.get(SEQUENCE, [])
    cited = set(about.cited)
    wanted = [q for q in sections if q in cited or any(sid in cited for sid in sections[q][1])]
    for entry in sequence:
        heading = _SECTION.match(entry.text) if entry.sid is None else None
        if heading and heading.group(1) not in wanted and about.names(heading.group(2)):
            wanted.append(heading.group(1))
    chosen = [e for e in sequence if (e.section in wanted and (e.sid or _SECTION.match(e.text)))
              or (e.sid and (e.sid in cited or about.names(e.body)
                             or (front_end and _FRONT_END_SCOPE.search(e.body))))]
    block("The sequence of operation for this system:", chosen)
    in_sections = {sid for q in wanted if q in sections for sid in sections[q][1]}

    # 1b. job-wide facts (T-005d must fix 1): the sequence sections that name no unit tag (a global outside air
    # sensor, a changeover aquastat in "A. GENERAL") go to every writer, so the system that owns a point writes it
    # once and the others see that it exists; then the reading's facts that name no unit tag
    families = _other_kinds(entries, about, skip=_GENERAL_HEADING)      # the job's other families' names
    block(JOB_WIDE_TITLE, _job_wide_sections(sequence, sections, given, families), JOB_WIDE_LIMIT)
    if ledger is not None:
        out.extend(_job_wide_facts(ledger, about, given, front_end, families))

    # 2. the points list rows for its equipment
    block("Points list rows for its equipment:",
          [e for e in by_part.get(POINTS, []) if e.sid and (e.sid in cited or e.sid in in_sections
                                                            or about.names(e.body) or about.type_row(e.body))])

    # 3. its schedule rows, under their schedule's title, with the schedule's notes.
    # Schedule objects (the reading) become a small table; without them the dossier's flat lines are used.
    schedule_rows = by_part.get(SCHEDULES, [])
    chosen_schedules = (_schedule_tables(schedules, schedule_rows, about, cited) if schedules
                        else _schedules(schedule_rows, about, cited))
    block("Its schedule rows and the schedules' notes:", chosen_schedules)

    # 4. its counts from the drawings, and the devices counted on the sheets it is on
    counts = [e for e in by_part.get(COUNTS, []) if e.sid and (e.sid in cited or _count_of(e.body, about))]
    block("Equipment counts from the drawings:", counts)
    sheets = {piece.strip().split(" ", 1)[0] for e in counts for m in [_PLACEMENTS.search(e.body)] if m
              for piece in m.group(1).split(";") if piece.strip()}
    devices = []
    for entry in by_part.get(DEVICES, []):
        if not entry.sid:
            continue
        m = _DEVICE_SHEETS.search(entry.body)
        on = {piece.strip().split(" ", 1)[0] for piece in m.group(1).split(";")} if m else set()
        if (sheets and on & sheets) or entry.sid in cited or about.names(entry.body):
            devices.append(entry)
    block("Devices counted on the plan sheets it is on:", devices)

    # 5. the notes naming it: a controls sheet's text whole and first, a long plan sheet's text as excerpts about it,
    # a note repeated word for word once (T-005d: the controls diagram reached no writer behind the plan sheets)
    notes = _notes(by_part.get(NOTES, []), about, cited, front_end)
    block("Controls sheets that name it (control diagrams, points, sequences):",
          [e for e in notes if _is_controls_sheet(e)], CONTROLS_LIMIT, whole=True)
    block("Notes that name it:", [e for e in notes if not _is_controls_sheet(e)], NOTES_LIMIT)

    # 6. the controls specification passages about it (and about integration, for an integrated system)
    integrated = system.control in ("integration", "packaged")
    block("Controls specification passages about it:",
          [e for e in by_part.get(SPEC, []) if e.sid and (e.sid in cited or about.names(e.body)
                                                          or (front_end and _FRONT_END_SCOPE.search(e.body))
                                                          or (integrated and _INTEGRATION_WORDS.search(e.body)
                                                              and not _names_another(e.body, about, elsewhere)))],
          SPEC_LIMIT)

    # 7. who does what, for the whole job (ownership), and the job part's passages naming it
    block("Who does what (whole job) and the job's own passages about it:",
          [e for e in by_part.get(JOB, []) if e.sid and (e.sid in cited or e.body.startswith("Who does what")
                                                         or about.names(e.body)
                                                         or (front_end and _FRONT_END_SCOPE.search(e.body)))])

    # 8. anything else the planner cited
    rest = [e for e in entries if e.sid and e.sid in cited and e.sid not in given]
    block("Other passages cited for it:", rest)

    # 9. the checklists (T-005d): the words that mark an item, the end devices its unit schedules list, and the
    # controls facts the reading found about it. Each ends as a line, the clarification or the no-scope reason.
    out.extend(_marks_checklist(out[len(head):]))     # the passages only: the register lists its own future items
    out.extend(_end_devices_checklist(chosen_schedules, cited))
    if ledger is not None:
        out.extend(_facts_checklist(ledger, about, front_end))

    # 10. the pictures it cites or its passages name
    named = set(re.findall(r"\bI\d+\b", "\n".join(out))) | {c for c in about.cited if _PICTURE_ID.fullmatch(c)}
    pictures = [(pid, image) for pid, image in _picture_ids(sources, images) if pid in named]
    if pictures:
        out += ["", "Pictures of the documents, attached (cite one by its id):"]
        for pid, image in pictures:
            out.append(f"[{pid}] Picture: {sources.get(pid) or getattr(image, 'what', '')}. File: {image.path}")
    return "\n".join(out) + "\n"


# ---- T-005d: the notes, the excerpts and the checklists --------------------------------------------------------

def _sheet_title(entry: Entry) -> str:
    """A plan sheet text entry's place and title: the words before its first colon."""
    return entry.body.split(":", 1)[0]


def _is_sheet_text(entry: Entry) -> bool:
    return entry.place == SHEET_TEXT_PLACE


def _is_controls_sheet(entry: Entry) -> bool:
    return _is_sheet_text(entry) and bool(_CONTROLS_SHEET.search(_sheet_title(entry)))


def _word_window(text: str, start: int, end: int) -> tuple[int, int]:
    """The span widened by EXCERPT_REACH each side, to whole words."""
    lo, hi = max(0, start - EXCERPT_REACH), min(len(text), end + EXCERPT_REACH)
    while lo > 0 and not text[lo - 1].isspace():
        lo -= 1
    while hi < len(text) and not text[hi].isspace():
        hi += 1
    return lo, hi


def _mentions(text: str, about: _About, front_end: bool) -> list[tuple[int, int]]:
    """Where the text names the system (a tag, a range holding one, a name phrase), or the front end's words, and
    where it marks an item (FUTURE, shipped loose)."""
    spans: list[tuple[int, int]] = []
    for m in _TAG.finditer(text):
        if plain_tag(m.group(1) + m.group(2)) in about.tags:
            spans.append(m.span())
    for m in _RANGE.finditer(text):
        if about.tags & tags_in(m.group(0)):
            spans.append(m.span())
    if not about.tags:          # a tagged system is found by its tags: its name is in every sheet's title block
        for phrase in about.phrases:
            spans += [m.span() for m in phrase.finditer(text)]
    if front_end:
        spans += [m.span() for m in _FRONT_END_TEXT.finditer(text)]
    if spans:
        spans += [m.span() for m in _FUTURE.finditer(text)] + [m.span() for m in _LOOSE.finditer(text)]
    return sorted(spans)


def _excerpt(entry: Entry, about: _About, front_end: bool, force: bool = False) -> Entry:
    """A long plan sheet's text as the excerpts about the system: each mention with EXCERPT_REACH characters each
    side, joined where they meet, at most EXCERPTS_MAX, in the sheet's order, split by " … ". Each excerpt is the
    sheet's own words, so a quote from one is in its source. A short text, or one with no mention, is kept whole."""
    body = entry.body
    head, colon, rest = body.partition(":")
    if not colon or (len(rest) <= EXCERPT_OVER and not force):
        return entry
    spans = _mentions(rest, about, front_end)
    if not spans:
        return entry
    windows: list[list[int]] = []
    for start, end in spans:
        lo, hi = _word_window(rest, start, end)
        if windows and lo <= windows[-1][1]:
            windows[-1][1] = max(windows[-1][1], hi)
        else:
            windows.append([lo, hi])
    shown = windows[:EXCERPTS_MAX]
    pieces = [" ".join(rest[lo:hi].split()) for lo, hi in shown]
    more = len(windows) - len(shown)
    tail = f" ({more} more excerpts not given)" if more > 0 else ""
    text = f"[{entry.sid}] {head} (excerpts about it): … " + " … ".join(pieces) + " …" + tail
    return Entry(entry.sid, text, entry.part, entry.place, entry.section)


def _notes(entries: list[Entry], about: _About, cited: set[str], front_end: bool) -> list[Entry]:
    """The notes for one system's evidence, in order of need: the cited ones, the controls sheets' text (whole: the
    control diagram and its points), the notes, then the other plan sheets' text as excerpts about it. A note whose
    words repeat an earlier one is given once (its first id), unless cited."""
    def wanted(e: Entry) -> bool:
        if not e.sid:
            return False
        if e.sid in cited:
            return True
        # a plan sheet's text names a tagged system by a tag: the project title in its title block ("replacement of
        # air handling units") names it on every sheet
        if (about.names_tag(e.body) if (about.tags and _is_sheet_text(e)) else about.names(e.body)):
            return True
        return front_end and bool(_FRONT_END_TEXT.search(e.body))

    chosen = [e for e in entries if wanted(e)]
    seen: set[str] = set()
    unique: list[Entry] = []
    for e in chosen:
        key = " ".join(e.body.split()).casefold()
        if key in seen and e.sid not in cited:
            continue
        seen.add(key)
        unique.append(e)
    first = [e for e in unique if e.sid in cited]
    controls = [e for e in unique if e.sid not in cited and _is_controls_sheet(e)]
    notes = [e for e in unique if e.sid not in cited and not _is_sheet_text(e)]
    sheets = [_excerpt(e, about, front_end) for e in unique
              if e.sid not in cited and _is_sheet_text(e) and not _is_controls_sheet(e)]
    return first + controls + notes + sheets


_SENTENCE_END = re.compile(r"(?<=[.;])\s+")

JOB_WIDE_TITLE = "Job-wide facts:"
_NAME_STOP = frozenset({"and", "the", "for", "with", "per", "new", "existing", "furnish", "install", "wire", "wiring",
                        "unit", "units", "system", "systems", "device", "devices", "all", "each"})


def _cut(text: str, limit: int) -> str:
    """The text cut to at most `limit` characters at a word, with " …" when cut."""
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    head = text[:max(0, limit - 2)]
    head = head.rsplit(" ", 1)[0] if " " in head else head
    return head + " …"


def _fit(entry: Entry, about: _About, front_end: bool, room: int, system: System) -> Entry:
    """A controls sheet's text in at most `room` characters: whole when it fits, else the excerpts about the system
    (`_excerpt`), else those cut at a word with a note that the rest is not given. Under CONTROLS_MIN characters
    there is no useful room left: the run stops with a plain message naming the sheet (T-005d must fix 2)."""
    if len(entry.text) <= room:
        return entry
    shown = _excerpt(entry, about, front_end, force=True)
    if len(shown.text) <= room:
        return shown
    if room < CONTROLS_MIN:
        raise ValueError(f"Stopped: the controls sheet {_sheet_title(entry)} ({len(entry.text):,} characters) does not "
                         f"fit the evidence for {system.name}: its controls sheets already use the "
                         f"{CONTROLS_LIMIT:,} characters bms.ai_evidence.CONTROLS_LIMIT allows. Raise it, or split "
                         "the system, and run again.")
    note = " (cut: the rest of the sheet is not given here)"
    text = _cut(shown.text, room - len(note)) + note
    return Entry(entry.sid, text, entry.part, entry.place, entry.section)


def _names_family(text: str, kinds: list[re.Pattern], own: str = "") -> bool:
    """The words name a kind of equipment (`_EQUIPMENT`) or another family's name (`kinds`, from the job's section
    headings and schedule titles; `own`, a section's own heading, is not counted against itself)."""
    mine = _phrase(re.sub(r"^[A-Z0-9]{1,3}[.)]\s+", "", own)) if own else None
    return bool(_EQUIPMENT.search(text)) or any(p.search(text) for p in kinds
                                                 if mine is None or p.pattern != mine.pattern)


def _job_wide_sections(sequence: list[Entry], sections: dict, given: set[str],
                       kinds: list[re.Pattern] = ()) -> list[Entry]:
    """The sequence sections that belong to no system (T-005d must fix 1; lead fix 2): a section whose heading names
    no tag, and either its heading says it is general ("A. GENERAL", "ALL SYSTEMS", "BMS SYSTEM", "ALARMS") and
    names no kind of equipment beside those words, or (another heading) neither its heading nor its first line
    names a tag, a kind of equipment or another family's name (`kinds`). So "C. CABINET UNIT HEATERS" goes to that
    family's writer only. The general ones first, each section whole (its heading line and paragraphs), in the
    dossier's order; a section already given is skipped."""
    by_section: dict[str, list[Entry]] = {}
    headings: dict[str, str] = {}
    for entry in sequence:
        if not entry.section:
            continue
        heading = _SECTION.match(entry.text) if entry.sid is None else None
        if heading:
            headings.setdefault(entry.section, heading.group(2))
            by_section.setdefault(entry.section, []).insert(0, entry)
        elif entry.sid:
            by_section.setdefault(entry.section, []).append(entry)
    general: list[Entry] = []
    other: list[Entry] = []
    for q, chosen in by_section.items():
        title = headings.get(q) or (sections.get(q, ("",))[0] if sections else "")
        if tags_in(title):
            continue
        paragraphs = [e for e in chosen if e.sid]
        if not paragraphs or all(e.sid in given for e in paragraphs):
            continue
        if _GENERAL_HEADING.search(title):
            if not _names_family(_GENERAL_HEADING.sub(" ", title), kinds, title):
                general += chosen
            continue
        bare = " ".join(re.sub(r"^[A-Z0-9]{1,3}[.)]\s+", "", title).split()).casefold()
        first = next((e for e in paragraphs if " ".join(re.sub(r"^[A-Z0-9]{1,3}[.)]\s+", "", e.body).split())
                      .casefold() != bare), None)
        words = f"{title} {first.body if first is not None else ''}"
        if not tags_in(words) and not _names_family(words, kinds, title) and \
                not any(tags_in(e.body) for e in paragraphs):
            other += chosen
    return general + other


def _job_wide_facts(ledger, about: _About, given: set[str], front_end: bool,
                    kinds: list[re.Pattern] = ()) -> list[str]:
    """The reading's controls facts that belong to no system: no unit tag (subject, value and quote), and (lead fix
    2) a subject and value that name no kind of equipment or other family (`_names_family`), as "[id] “quote” —
    where (read as: ...)", at most JOB_WIDE_FACTS_MAX, under their own heading: every writer sees them; the system
    that owns the point writes it."""
    from bms.coverage import SCOPE_KINDS
    from estimator.ledger.facts import where_short
    lines: list[str] = []
    for fact in getattr(ledger, "facts", {}).values():
        if fact.kind not in SCOPE_KINDS or fact.kind == "front_end":
            continue
        said = f"{fact.subject} {'' if fact.value is None else fact.value} {fact.quote or ''}"
        if tags_in(said) or (not front_end and about.names(said)):
            continue
        if _names_family(f"{fact.subject} {'' if fact.value is None else fact.value}", kinds):
            continue                    # a cabinet unit heater's thermostat is that family's (lead fix 2)
        sid = str(fact.source_id or "").strip().strip("[]")
        if not sid or sid in given or not str(fact.quote or "").strip():   # a passage given above: once
            continue
        where = where_short(getattr(ledger, "sources", {}).get(sid, ""))
        line = f"[{sid}] “{_cut(fact.quote, QUOTE_MAX)}”" + (f" — {where}" if where else "")
        lines.append(f"{line} (read as: {_fact_text(fact)})")
    lines = list(dict.fromkeys(lines))
    if not lines:
        return []
    shown = lines[:JOB_WIDE_FACTS_MAX]
    out = ["", "Job-wide facts the reading found (they name no unit tag): write one as a line only when this system "
           "owns the point (its sequence, points list or a control diagram puts it here); otherwise leave it to the "
           "system that owns it.", *shown]
    if len(lines) > len(shown):
        out.append(f"({len(lines) - len(shown)} more job-wide facts not listed)")
    return out


def _name_words(name: str) -> list[re.Pattern]:
    words = [w for w in re.findall(r"[a-z0-9]+", (name or "").lower()) if len(w) >= 3 and w not in _NAME_STOP]
    stems = dict.fromkeys(re.sub(r"(?:es|s)$", "", w) if len(w) > 4 else w for w in words)
    return [re.compile(rf"\b{re.escape(stem)}\w*", re.I) for stem in stems]


def future_items(text: str, name: str | None = None) -> list[tuple[int, int]]:
    """Where the text marks an item FUTURE (T-005d should fix 1): each FUTURE with, within FUTURE_REACH characters
    of it, an item word (`_ITEM`) or, given `name`, one of that device name's words. "ZZ-7 CAP FOR FUTURE
    CONNECTION" marks no item."""
    text = str(text or "")
    words = _name_words(name) if name is not None else []
    found: list[tuple[int, int]] = []
    for m in _FUTURE.finditer(text):
        near = text[max(0, m.start() - FUTURE_REACH):m.start()] + " " + text[m.end():m.end() + FUTURE_REACH]
        if (any(w.search(near) for w in words) if name is not None else _ITEM.search(near)):
            found.append(m.span())
    return found


def _windows(body: str, pattern: re.Pattern, reach: int = 120) -> list[str]:
    """Each place `pattern` matches in the body, with up to `reach` characters each side, cut to whole words."""
    found: list[str] = []
    for m in pattern.finditer(body):
        lo, hi = max(0, m.start() - reach), min(len(body), m.end() + reach)
        while lo > 0 and not body[lo - 1].isspace():
            lo -= 1
        while hi < len(body) and not body[hi].isspace():
            hi += 1
        piece = " ".join(body[lo:hi].split())
        if piece and piece not in found:
            found.append(piece)
    return found


def _marks_checklist(lines: list[str]) -> list[str]:
    """The passages of the evidence so far that mark an item FUTURE (ruling 7: its own line, mark "future") and the
    ones that say an item is furnished integral or by the factory (mark "notice"), each as "[id] “words”": the
    words are the passage's own, so they can be quoted."""
    future: list[str] = []
    notice: list[str] = []
    for entry in parse("\n".join(lines)):
        if not entry.sid or entry.sid.startswith("I"):
            continue
        body = entry.body
        if future_items(body):
            future += [f"[{entry.sid}] “{w}”" for w in _windows(body, _FUTURE) if future_items(w)]
        if _END_DEVICE.search(body):
            notice += [f"[{entry.sid}] “{w}”" for w in _windows(body, _NOTICE, 80) if _END_DEVICE.search(w)]
    out: list[str] = []
    if future:
        out += ["", "Items its passages mark FUTURE (an item of this system is a line of its own with mark \"future\" "
                "and mark_note \"FUTURE AS PER <the document in a few words>\"):", *list(dict.fromkeys(future))[:MARKS_MAX]]
    if notice:
        out += ["", "Devices its passages say are integral or furnished with the unit (the estimator must notice "
                "each: when it is a line, mark it \"notice\"):", *list(dict.fromkeys(notice))[:MARKS_MAX]]
    return out


def _end_devices_checklist(schedule_entries: Iterable[Entry], cited: set[str]) -> list[str]:
    """The end devices its unit schedules list, in their rows and notes (ruling 10): the ids, so the writer reads each
    into scope (a device shipped loose or mounted in the field is AME's to install and wire)."""
    loose: list[str] = []
    devices: list[str] = []
    for entry in schedule_entries:
        if not entry.sid:
            continue
        body = entry.body
        if _LOOSE.search(body) and entry.sid not in loose:
            loose.append(entry.sid)
        elif _END_DEVICE.search(body) and entry.sid not in devices:
            devices.append(entry.sid)
    out: list[str] = []
    if loose or devices:
        out += ["", "End devices its unit schedules list (each ends as a line, or in the clarification; a device the "
                "schedule says ships loose or is mounted in a duct or in the field is installed and wired by AME):"]
        if loose:
            out.append("- shipped loose or mounted in the field: " + ", ".join(loose))
        if devices:
            out.append("- names an end device (the passage says who furnishes it; when it says the unit or the factory "
                       "furnishes it, a line for it is marked \"notice\"): " + ", ".join(devices))
    return out


def _fact_text(fact) -> str:
    value = "" if fact.value is None else " ".join(str(fact.value).split())
    return f"{fact.kind.replace('_', ' ')} {fact.subject}" + (f" = {value}" if value else "")


def _facts_checklist(ledger, about: _About, front_end: bool) -> list[str]:
    """The controls facts the reading found about this system (the coverage gate's facts, `bms.coverage.SCOPE_KINDS`),
    each as "[source id] “quote” — where (read as: kind subject = value)", so the writer ends each one as a line, the
    clarification or the no-scope reason (critique flow step 5) instead of the gate finding it uncited afterwards."""
    from bms.coverage import SCOPE_KINDS
    from estimator.ledger.facts import where_short
    lines: list[str] = []
    for fact in getattr(ledger, "facts", {}).values():
        if fact.kind not in SCOPE_KINDS:
            continue
        said = f"{fact.subject} {'' if fact.value is None else fact.value}"
        mine = (fact.kind == "front_end") if front_end else (fact.kind != "front_end" and
                                                              (about.names(said) or about.names_tag(fact.quote or "")))
        if not mine:
            continue
        sid = str(fact.source_id or "").strip().strip("[]")
        if not sid or not str(fact.quote or "").strip():
            continue
        where = where_short(getattr(ledger, "sources", {}).get(sid, ""))
        line = f"[{sid}] “{_cut(fact.quote, QUOTE_MAX)}”" + (f" — {where}" if where else "")
        lines.append(f"{line} (read as: {_fact_text(fact)})")
    lines = list(dict.fromkeys(lines))
    if not lines:
        return []
    shown = lines[:FACTS_MAX]
    out = ["", "Controls facts the reading found about it (each ends as a line that cites it, the block's "
           "clarification, or the no_scope_reason; one that is not AME's work is left out and goes to the estimator):",
           *shown]
    if len(lines) > len(shown):
        out.append(f"({len(lines) - len(shown)} more facts not listed)")
    return out


def _other_kinds(entries: list[Entry], about: _About, skip: re.Pattern | None = None) -> list[re.Pattern]:
    """The kinds of equipment the job's documents name that are not this system's: the sequence section headings
    ("B. EXHAUST FANS") and the schedule titles ("VRF SCHEDULE"), as name phrases. `skip`: names it matches are
    left out (the general headings, for the job-wide facts)."""
    names: list[str] = []
    for entry in entries:
        heading = _SECTION.match(entry.text) if entry.sid is None else None
        if heading:
            names.append(re.sub(r"^[A-Z0-9]{1,3}[.)]\s+", "", heading.group(2)))
        elif entry.part == SCHEDULES and entry.sid and " — " in entry.text.split("\n", 1)[0]:
            title = _ENTRY.sub(lambda m: m.group(2), entry.text.split("\n", 1)[0], count=1).split(" — ", 1)[0]
            names.append(re.sub(r"\s+(?:SCHEDULES?|LIST)$", "", title.strip(), flags=re.I))
    phrases = (_phrase(n) for n in dict.fromkeys(names)
               if not about.names_phrase(n) and not (skip is not None and skip.search(n)))
    return [p for p in phrases if p is not None]


def _names_another(body: str, about: _About, elsewhere: list[re.Pattern]) -> bool:
    """The passage names another system's tags or kind of equipment (or a tag that is none of this system's)."""
    return bool(tags_in(body) - about.tags) or any(p.search(body) for p in elsewhere)


def _count_of(body: str, about: _About) -> bool:
    head = body.split(" ", 1)[0].split("(", 1)[0]
    return plain_tag(head) in about.prefixes or (not about.prefixes and about.names_phrase(body.split(":", 1)[0]))


def _schedules(entries: list[Entry], about: _About, cited: set[str]) -> list[Entry]:
    """Each schedule (its title entry, then rows, then notes) that has a row naming the system, or that the planner
    cited, or (a system with no tags) whose title names it: the title, those rows (all rows for a cited schedule or
    an untagged system's schedule) and the schedule's notes."""
    out: list[Entry] = []
    title: Entry | None = None
    rows: list[Entry] = []
    notes: list[Entry] = []
    whole = False

    def flush() -> None:
        if rows or whole:
            if title is not None:
                out.append(title)
            out.extend(rows)
            out.extend(notes)

    for entry in entries:
        if entry.sid is None:
            continue
        first = entry.body.split("\n", 1)[0]
        if first.startswith(_SCHEDULE_NOTE):
            notes.append(entry)
        elif "|" not in first:
            flush()
            title, rows, notes = entry, [], []
            whole = entry.sid in cited or (not about.tags and about.names_phrase(first))
        elif whole or entry.sid in cited or about.type_row(entry.body) or about.names_tag(first):
            rows.append(entry)
    flush()
    return out


def _cell(text: str | None) -> str:
    return " ".join((text or "").split()) or "-"


def _schedule_blocks(entries: list[Entry]) -> list[tuple[Entry, list[Entry], list[Entry]]]:
    """Each schedule in the dossier text: its title entry, its row entries, its note entries."""
    blocks: list[tuple[Entry, list[Entry], list[Entry]]] = []
    title: Entry | None = None
    rows: list[Entry] = []
    notes: list[Entry] = []

    def flush() -> None:
        if title is not None:
            blocks.append((title, list(rows), list(notes)))

    for entry in entries:
        if entry.sid is None:
            continue
        first = entry.body.split("\n", 1)[0]
        if first.startswith(_SCHEDULE_NOTE):
            notes.append(entry)
        elif "|" not in first:
            flush()
            title, rows, notes = entry, [], []
        else:
            rows.append(entry)
    flush()
    return blocks


def _block_for(schedule, blocks, used: set[int]):
    """The dossier block whose title line carries this schedule's title, once."""
    title = (schedule.title or "").strip()
    for index, block in enumerate(blocks):
        if index in used or not title:
            continue
        if title in block[0].body.split("\n", 1)[0]:
            used.add(index)
            return block
    return None, [], []


def _object_row_matches(row, schedule, about: _About) -> bool:
    bits: list[str] = []
    if row.tag:
        bits.append(str(row.tag))
    headers = schedule.headers or ()
    if headers and row.cells:
        shown = row.cells.get(headers[0])
        if shown:
            bits.append(str(shown))
    return any(about.type_row(f"{bit} |") or about.names_tag(bit) for bit in bits)


def _same_row(row, schedule, first: str) -> bool:
    if row.tag and (plain_tag(row.tag) == plain_tag(first) or plain_tag(row.tag) in tags_in(first)):
        return True
    headers = schedule.headers or ()
    if headers and row.cells:
        shown = str(row.cells.get(headers[0]) or "")
        if shown and (plain_tag(shown) == plain_tag(first) or shown.strip() == first.strip()):
            return True
    return False


def _row_sid(row, schedule, row_entries: list[Entry], used: set[str]) -> str | None:
    for entry in row_entries:
        if not entry.sid or entry.sid in used:
            continue
        if _same_row(row, schedule, entry.body.split("|", 1)[0].strip()):
            used.add(entry.sid)
            return entry.sid
    return None


def _note_sid(label: str, text: str, note_entries: list[Entry], used: set[str]) -> str | None:
    want = " ".join((text or "").split())
    if not want:
        return None
    prefix = f"{label}:"
    for entry in note_entries:
        if not entry.sid or entry.sid in used:
            continue
        body = " ".join(entry.body.split())
        if body.startswith(prefix) and want in body:
            used.add(entry.sid)
            return entry.sid
    return None


def _schedule_tables(schedules, entries: list[Entry], about: _About, cited: set[str]) -> list[Entry]:
    """One small table per schedule object that belongs to this system: the title (its citation, and any
    "See image" line), the columns, the rows for its tags, then the notes. Cells come from the schedule object.
    Each title, row and note keeps the source id the dossier gave it."""
    blocks = _schedule_blocks(entries)
    used_blocks: set[int] = set()
    out: list[Entry] = []
    for schedule in schedules:
        title, row_entries, note_entries = _block_for(schedule, blocks, used_blocks)
        title_sid = title.sid if title is not None else None
        whole = bool(title_sid and title_sid in cited) or (not about.tags and about.names_phrase(schedule.title or ""))
        matched = [row for row in schedule.rows
                   if _object_row_matches(row, schedule, about)
                   or (_row_sid(row, schedule, row_entries, set()) in cited)]
        chosen = matched if matched else (list(schedule.rows) if whole else [])
        if not chosen and not (whole and (schedule.notes or schedule.controls_by)):
            continue
        part = title.part if title is not None else SCHEDULES
        place = title.place if title is not None else None
        section = title.section if title is not None else None
        if title is not None:
            out.append(Entry(title.sid, title.text.split("\n", 1)[0], part, place, section))
            for line in title.text.split("\n")[1:]:
                if line.strip().startswith("Columns:"):
                    continue
                out.append(Entry(None, line, part, place, section))
        else:
            name = (schedule.document or "").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
            where = ", ".join(bit for bit in (schedule.sheet, f"{name} page {schedule.page}" if name else "") if bit)
            text = f"{schedule.title} — {where}" if where else (schedule.title or "Schedule")
            out.append(Entry(None, text, part, place, section))
        headers = tuple(schedule.headers or ())
        synthetic = not headers
        if synthetic:
            headers = ("TAG",)
        out.append(Entry(None, "    | " + " | ".join(_cell(header) for header in headers) + " |", part, place, section))
        out.append(Entry(None, "    | " + " | ".join("---" for _ in headers) + " |", part, place, section))
        used: set[str] = set()
        for row in chosen:
            sid = _row_sid(row, schedule, row_entries, used)
            cells = []
            for index, header in enumerate(headers):
                raw = row.cells.get(header) if row.cells and not synthetic else None
                if synthetic and index == 0:
                    raw = row.tag
                value = _cell(None if raw is None else str(raw))
                if index == 0 and getattr(row, "existing", False) and "EXISTING" not in value.upper():
                    value = f"{value} (EXISTING)"
                cells.append(value)
            body = " | ".join(cells)
            out.append(Entry(sid, f"[{sid}] | {body} |" if sid else f"| {body} |", part, place, section))
        for note in schedule.notes or ():
            sid = _note_sid("Note", str(note), note_entries, used)
            text = f"Note: {' '.join(str(note).split())}"
            out.append(Entry(sid, f"[{sid}] {text}" if sid else text, part, place, section))
        for sentence in schedule.controls_by or ():
            sid = _note_sid("Unit controls by", str(sentence), note_entries, used)
            text = f"Unit controls by: {' '.join(str(sentence).split())}"
            out.append(Entry(sid, f"[{sid}] {text}" if sid else text, part, place, section))
    return out


def _picture_ids(sources: dict[str, str], images) -> list[tuple[str, object]]:
    """Each dossier picture with its id: I1 ... In in the dossier's order (as `build_dossier` numbers them)."""
    return [(f"I{n}", image) for n, image in enumerate(images or (), start=1)]


_PICTURE_LINE = re.compile(r"^\[(I\d+)\] Picture: (.*)\. File: (.+?)\s*$", re.M)


def pictures(evidence_text: str) -> list[tuple[str, str, str]]:
    """The pictures a system's evidence attaches: (id, what, file path), in order."""
    return [(m.group(1), m.group(2), m.group(3)) for m in _PICTURE_LINE.finditer(evidence_text or "")]


# the evidence's blocks whose passages state facts a line may rest on without an assumption (ruling 6)
STATED_TITLES = ("The sequence of operation for this system:", "Points list rows for its equipment:",
                 "Its schedule rows and the schedules' notes:", "Job-wide facts:")


def stated_ids(evidence_text: str) -> frozenset[str]:
    """The source ids the evidence gives under its sequence, points list and schedule blocks."""
    found: set[str] = set()
    for chunk in (evidence_text or "").split("\n\n"):
        title, _, rest = chunk.partition("\n")
        if title.strip() in STATED_TITLES:
            found |= {m.group(1) for m in _ENTRY_ID.finditer(rest)}
    return frozenset(found)


_ENTRY_ID = re.compile(r"^\[([A-Z]{1,3}\d+[a-z]?)\]", re.M)
_CITED = re.compile(r"\[([A-Z]{1,3}\d+[a-z]?)\]")


def cited_ids(evidence_text: str) -> frozenset[str]:
    """Every source id the evidence carries ("[S41]" -> "S41")."""
    return frozenset(_CITED.findall(evidence_text or ""))
