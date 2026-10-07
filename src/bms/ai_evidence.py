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

def evidence(system: System, text: str, sources: dict[str, str], sections: dict, images, schedules=()) -> str:
    """The evidence one system is written from (see `bms.ai.evidence_for`)."""
    about = _about(system)
    entries = parse(text)
    by_part: dict[int, list[Entry]] = {}
    for entry in entries:
        by_part.setdefault(entry.part, []).append(entry)
    ids_in_text = {e.sid for e in entries if e.sid}
    elsewhere = _other_kinds(entries, about)
    sections = sections or {}
    given: set[str] = set()
    out = [f"Evidence for {system.name} (system {system.key}), from this job's documents only. Each passage starts "
           "with its source id in square brackets; cite a passage by that id."]

    def block(title: str, chosen: Iterable[Entry], limit: int | None = None) -> None:
        lines: list[str] = []
        used, left, place = 0, 0, None
        for entry in chosen:
            if entry.sid and entry.sid in given:
                continue
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
              or (e.sid and (e.sid in cited or about.names(e.body)))]
    block("The sequence of operation for this system:", chosen)
    in_sections = {sid for q in wanted if q in sections for sid in sections[q][1]}

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

    # 5. the notes naming it
    block("Notes that name it:", [e for e in by_part.get(NOTES, []) if e.sid and (e.sid in cited or about.names(e.body))],
          NOTES_LIMIT)

    # 6. the controls specification passages about it (and about integration, for an integrated system)
    integrated = system.control in ("integration", "packaged")
    block("Controls specification passages about it:",
          [e for e in by_part.get(SPEC, []) if e.sid and (e.sid in cited or about.names(e.body)
                                                          or (integrated and _INTEGRATION_WORDS.search(e.body)
                                                              and not _names_another(e.body, about, elsewhere)))],
          SPEC_LIMIT)

    # 7. who does what, for the whole job (ownership), and the job part's passages naming it
    block("Who does what (whole job) and the job's own passages about it:",
          [e for e in by_part.get(JOB, []) if e.sid and (e.sid in cited or e.body.startswith("Who does what")
                                                         or about.names(e.body))])

    # 8. anything else the planner cited
    rest = [e for e in entries if e.sid and e.sid in cited and e.sid not in given]
    block("Other passages cited for it:", rest)

    # 9. the pictures it cites or its passages name
    named = set(re.findall(r"\bI\d+\b", "\n".join(out))) | {c for c in about.cited if _PICTURE_ID.fullmatch(c)}
    pictures = [(pid, image) for pid, image in _picture_ids(sources, images) if pid in named]
    if pictures:
        out += ["", "Pictures of the documents, attached (cite one by its id):"]
        for pid, image in pictures:
            out.append(f"[{pid}] Picture: {sources.get(pid) or getattr(image, 'what', '')}. File: {image.path}")
    return "\n".join(out) + "\n"


def _other_kinds(entries: list[Entry], about: _About) -> list[re.Pattern]:
    """The kinds of equipment the job's documents name that are not this system's: the sequence section headings
    ("B. EXHAUST FANS") and the schedule titles ("VRF SCHEDULE"), as name phrases."""
    names: list[str] = []
    for entry in entries:
        heading = _SECTION.match(entry.text) if entry.sid is None else None
        if heading:
            names.append(re.sub(r"^[A-Z0-9]{1,3}[.)]\s+", "", heading.group(2)))
        elif entry.part == SCHEDULES and entry.sid and " — " in entry.text.split("\n", 1)[0]:
            title = _ENTRY.sub(lambda m: m.group(2), entry.text.split("\n", 1)[0], count=1).split(" — ", 1)[0]
            names.append(re.sub(r"\s+(?:SCHEDULES?|LIST)$", "", title.strip(), flags=re.I))
    phrases = (_phrase(n) for n in dict.fromkeys(names) if not about.names_phrase(n))
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


_CITED = re.compile(r"\[([A-Z]{1,3}\d+[a-z]?)\]")


def cited_ids(evidence_text: str) -> frozenset[str]:
    """Every source id the evidence carries ("[S41]" -> "S41")."""
    return frozenset(_CITED.findall(evidence_text or ""))
