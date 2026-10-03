"""The whole-job judge: the AI reads the job's whole dossier the way an estimator reads a bid set.

The two questions the judge answers for the whole job:
- "read_pass" (`Judge.ask_pass`): the seven reading passes of `estimator.ledger` read the dossier and
  record every fact (families, units, counts, places, devices, links) in the job ledger, each with the
  source id and the words it rests on. A dossier over `SPLIT_LIMIT` characters is read in pieces
  (`_chunks`). The job's systems come from that ledger (`estimator.ledger.to_plan` builds the `JobPlan`).
- "write_system" (`Judge.write_system`): one pass per planned system writes its scope lines in the
  house style from its ledger entry and the passages it cites, with the nearest Master Template's lines
  as a checklist (never a closed menu) and past proposals' blocks as examples; every line quotes its
  source.

This module holds the write question's shapes, prompt, schema and checks, and the pictures and source
ids both questions share; `judge.py` asks the questions through its cache and its chat/API hand-off.
Nothing here decides scope by itself: it only
reads the AI's answer and throws out what cannot be trusted (a quantity with no words stating it, a
header the client must not see, a source id the dossier does not have), saying so in plain words.

A dossier picture (`DossierImage`) is anything with path, what, sheet, document and page. In the
API it goes as an image block with its caption; in the chat the request lists the paths to open.
"""
from __future__ import annotations

import base64
import dataclasses
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, Sequence

from estimator.writing.judge import (MAX_DEPTH, MAX_EXAMPLES, NO_EVIDENCE_CONFIDENCE, TECH_HOUR_BASES,
                                     TechHoursHint, _confidence, _depth, _example_text, _quantity, _squash,
                                     _tech_hours, _template_text)
from estimator.writing.style import ASSETS, HouseStyle

SPLIT_LIMIT = 1_200_000        # characters of dossier read in one pass (about 300,000 tokens — inside one request for the current models; splitting loses the sequence for the later parts)
MAX_IMAGES = 100             # pictures sent with one question
MAX_IMAGE_BYTES = 5 * 1024 * 1024   # the API takes no bigger picture
_CHECKLIST_LINE = 300        # characters of one checklist line

# --- the write step's system prompt: the estimator's GEM ----------------------------------------------------------

GEM_FILE = ASSETS / "gem" / "BMS_DDC_GEM_v4.txt"         # v3.2 stays beside it for comparison
PRACTICE_FILE = ASSETS / "gem" / "ame_practice.txt"      # the estimators' own rules, added to as plain text
PROPOSED_PRACTICE_FILE = ASSETS / "gem" / "ame_practice_proposed.txt"   # rules from corrections, for approval
GEM_START, GEM_END = "WHO YOU ARE", "END OF INSTRUCTIONS"
# The GEM's chat mechanics, left out: (the first line cut, the line the text goes on from).
GEM_CUTS = (("RESET PROTOCOL", "STEP 0 — PROJECT QUICK SCAN"),                     # and the auto-start note
            ("PHASE 2 — CLEAN SOW", "CONTRADICTION AND ASSUMPTION SCAN"),
            ("DISPLAY FORMAT — after every SOW output", "If any check shows FAIL"),
            ("OPTION: SEQUENCE HARDWARE HIGHLIGHT", GEM_END))
# Inside the tool the GEM reads more than a pasted sequence: this section, after the GEM's INPUT HANDLING, tells it
# how the other documents connect. (The controller's addendum to the GEM round.)
GEM_AFTER = "INPUT HANDLING — SEQUENCE AND POINT LIST"
GEM_CONNECTING = """\
CONNECTING THE DOTS — THE OTHER DOCUMENTS (addendum for use inside the estimating tool)
The sequence is not the only document here. With each system's sequence
you are given the other documents of the bid set. Read them all and
connect the dots.
SOURCE PRIORITY — EXTENDED PAST THE POINT LIST
Sequence is Source Priority 1. Point List is Source Priority 2.
  Priority 3 — Equipment schedules and their notes
  Priority 4 — Plans: device labels and symbols, keyed and general notes,
               typical-floor labels
  Priority 5 — Details and risers: valves, DP sensors, damper actuators,
               the network riser (who furnishes fiber, switches,
               workstations)
  Priority 6 — The specification: ownership clauses, front end, warranty,
               training
The sequence still governs control logic and ownership wording.
The later sources fill what it leaves out.
When two sources disagree, flag C1 / C2 with both snippets quoted.
QUANTITIES — FROM THE DOCUMENTS (Quantity rules, Rule 1 and 2)
Never take a quantity from the sequence's wording alone. Count from:
— the schedule row count, or its QUANTITY column
— the plan placements times the floors a typical plan serves
— the riser count
— the device labels counted on the plans
A count given in the evidence's "Counts from the drawings" is a
confirmed quantity: write (Qty. N Total).
Only when no document counts it, flag CONFIRM QUANTITY and write
(Qty. per Mechanical Schedule) or (Qty. per Drawing).
UNIT TYPE — FROM THE SCHEDULE WHEN THE SEQUENCE IS SILENT
A schedule note "factory-mounted DDC controls" / "controls by unit
manufacturer" / "BACnet gateway", or a CONTROLS column, means the unit
is Factory/OEM Controls.
"Controls by ATC/BMS contractor" / "DDC controller furnished to the
factory" means the unit is Field-Installed DDC.
Cite the note.
DEVICES SHOWN ON THE PLANS — NOT IN THE SEQUENCE
A thermostat label, a CO2 label or a damper actuator keynote on the plans
needs a scope line, flagged:
    (As per Plan — not called in sequence)
It is treated the same way as a point-list-only item.
A keyed note that assigns work to CC is a reference line like any
sequence sentence.
SCHEDULE NOTES — OWNERSHIP UNDER QUESTION 1
A schedule note decides who furnishes, exactly like a sequence sentence:
  "furnished with unit" / "shipped loose" / "24V transformer with unit" /
  "thermostat by unit manufacturer" means the unit manufacturer furnishes it.
  Write the Install and Wire / Wire lines and the "*... BY UNIT MFR." note
  accordingly.
WHAT THE SPEC ASSIGNS — CATEGORY B
A warranty term, training hours, the front end, "all control wiring by
this contractor": when the spec names CC, it is a CC obligation under
Category B.
REFERENCE LINES — NAME THE SOURCE
Each reference line names its source: the sequence snippet, or
  (Schedule note 4, H601)
  (Keyed note 7, H111)
  (Plan count, M-101 times 10 floors)
  (Spec 23 09 23 paragraph 3.4)"""
GEM_OUTPUT = """\
OUTPUT
Answer as JSON in the schema given. Put the Quick Scan, the System Explanation, the scope lines (each with its \
reference line and flag), the Contradiction and Assumption scan, the Miscellaneous Responsibilities, the Exclusions \
and the Self-QC results in their fields.
  quick_scan: the eight Quick Scan fields, as the block fills them.
  explanation: the System Explanation.
  lines: one per scope line, in SOW order. text: the scope line as the SOW writes it, with its quantity note on the \
same line, without the flag. reference: the words of its reference line, without the brackets. flag: "red" for \
CONFIRM QUANTITY, "yellow" for CONFIRM OWNERSHIP, "orange" for ASSUMED, "green" for NOTE, or "" for none. flag_text: what the flag says (what to confirm, or the exact basis of \
the assumption). quantity: the number its quantity note states, or null. quote: the exact words of the evidence it \
rests on, copied from it. source_id: the id of that passage, such as "[S12]". depth: 1, or 2 for a line one level \
in (the manufacturer's representative line). The system's header and count are printed for you: never write them as a line.
  contradictions: one entry per hit of the scan (type C1 to C6, the item, the snippets quoted, the flag); none when \
there is nothing to flag.
  misc_responsibilities: the Miscellaneous Responsibilities, one plain statement each.
  exclusions: the Exclusions, one plain line each.
  qc: QC-01 to QC-10, each with its evidence token, whether it passes, and the fix applied when it fails.
  client_notes: clarifications for the client, each starting with "**"; never estimating hints, tech hours or \
prices. tech_hours: from the Master Template tech-hour rule given, or null when it gives none. review_notes: the \
A&C notes and anything else for the estimator."""


def _gem_heading(line: str) -> bool:
    """A GEM section heading: a line in capitals at the margin, not a label ending in a colon ("PRIORITY RULE:")."""
    text = line.rstrip()
    letters = [c for c in text if c.isalpha()]
    return (bool(text) and not text[0].isspace() and len(letters) >= 6 and text == text.upper()
            and not text.endswith(":"))


def ame_practice(path: Path = PRACTICE_FILE) -> list[str]:
    """The estimators' own rules (assets/gem/ame_practice.txt), as plain text lines; none when the file is not there."""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError:
        return []
    return [line.rstrip() for line in text.strip().splitlines()]


def gem_prompt(path: Path = GEM_FILE, practice: Path = PRACTICE_FILE) -> str:
    """The GEM's text from "WHO YOU ARE" to "END OF INSTRUCTIONS", word for word, without its chat mechanics (the
    RESET protocol and the auto-start note, the Phase 2 clean SOW on confirmation, the display table, the hardware
    highlight option), with the section connecting the other documents after its INPUT HANDLING, followed by the
    estimators' AME practice rules (assets/gem/ame_practice.txt), and with the OUTPUT section before its end. The
    dump's "[?] " line marks are taken off."""
    lines = [re.sub(r"^\[\?\]\s?", "", line.rstrip()) for line in path.read_text(encoding="utf-8-sig").splitlines()]
    first = next(n for n, line in enumerate(lines) if line.strip().startswith(GEM_START))
    last = next(n for n, line in enumerate(lines) if line.strip().startswith(GEM_END))
    body = lines[first:last + 1]
    for cut, resume in GEM_CUTS:
        at = next((n for n, line in enumerate(body) if line.strip().startswith(cut)), None)
        if at is None:
            continue
        back = next(n for n in range(at + 1, len(body)) if body[n].strip().startswith(resume))
        body = body[:at] + body[back:]
    heading = next(n for n, line in enumerate(body) if line.strip().startswith(GEM_AFTER))
    after = next(n for n in range(heading + 1, len(body)) if _gem_heading(body[n]))
    body = body[:after] + GEM_CONNECTING.splitlines() + ame_practice(practice) + body[after:]
    end = next(n for n, line in enumerate(body) if line.strip().startswith(GEM_END))
    return "\n".join(body[:end] + GEM_OUTPUT.splitlines() + body[end:])


WRITE_PROMPT = gem_prompt()
FLAGS = ("", "red", "yellow", "orange", "green")
_FLAG_SYMBOLS = {"\U0001F534": "red", "\U0001F7E1": "yellow", "\U0001F7E0": "orange", "\U0001F7E2": "green"}
CONFLICT_TYPES = tuple(f"C{n}" for n in range(1, 7))
QC_CHECKS = tuple(f"QC-{n:02d}" for n in range(1, 11))
QUICK_SCAN = ("systems_identified", "unit_type", "controller", "submittal_status", "blanket_wiring_clause",
              "fa_interface_present", "point_list_provided", "contractor_name_used")
TEMPLATE_WORDS = ("The Standard Template defines the ORDER OF CATEGORIES in the output. It does not define device "
                  "names.")
NO_REFERENCE = "No reference line: nothing in the sequence was quoted for it"
_DIAMOND = re.compile(r"^\s*(?:◊\s*)?(?:the\s+)?(?:controls\s+contractor|cc)\s+requires\s+mfr\.?\s+rep\b", re.I)
REFERENCED_CONFIDENCE, UNREFERENCED_CONFIDENCE = 0.85, 0.5


class DossierImage(Protocol):
    """A picture of the job's documents the text could not read (a picture schedule, say)."""
    path: str
    what: str
    sheet: str | None
    document: str
    page: int


@dataclass(frozen=True)
class Family:
    """One equipment family a planned system covers: its own header and count (a stacked header)."""
    header: str               # house form without the Qty: "Dryer Exhaust Fan DXF-1-1, 2"
    tags: tuple[str, ...]
    quantity: int | None      # only when a source states it
    quantity_source: str      # "[S41]" | ""
    quantity_quote: str


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
    exception: str            # "" or the one-line exception text in capitals
    why: str
    sequence_section: str = ""                 # the sequence section(s) it is: "Q7" (or "Q7, Q8"), "" when none
    families: tuple[Family, ...] = ()          # two or more: one stacked header each; () for a one-family system
    count_note: str = ""                       # "*Qty. (14) per …; … lists (12)." when the ledger's count is contradicted
    facts: tuple[str, ...] = ()                # the ledger fact ids it rests on (F1, F9, …)


@dataclass(frozen=True)
class JobPlan:
    systems: tuple[PlannedSystem, ...]
    front_end: dict           # {"mode": "new-system"|"extend-existing"|"", "existing_name", "lines", "notes", "sources"}
    unresolved: tuple[str, ...]   # plain questions for the estimator
    model: str
    dropped: tuple[str, ...] = ()  # systems the AI planned that could not be trusted, and why


@dataclass(frozen=True)
class WrittenLine:
    """One scope line the judge wrote for a planned system: the GEM's scope line with its reference line and flag."""
    text: str
    depth: int
    quantity: int | None      # only when the evidence states the count (then the quote holds it)
    quote: str                # the words from the evidence that call for it ("" when none: low confidence)
    source_id: str            # "[S12]" | ""
    why: str
    confidence: float
    reference: str = ""       # the GEM's indented reference line
    flag: str = ""            # "" | "red" | "yellow" | "orange" | "green"
    flag_text: str = ""       # what the flag says: what to confirm, or the basis of an assumption
    fact_ids: tuple[str, ...] = ()  # the ledger facts the line rests on (F1, F9)


@dataclass(frozen=True)
class Contradiction:
    """One hit of the GEM's Contradiction and Assumption scan."""
    type: str                 # "C1" … "C6"
    item: str
    quotes: tuple[str, ...]
    flag: str


@dataclass(frozen=True)
class QcCheck:
    """One of the GEM's ten evidence-based Self-QC checks."""
    check: str                # "QC-01" … "QC-10"
    evidence: str
    passed: bool
    fix: str


@dataclass(frozen=True)
class WrittenScope:
    lines: tuple[WrittenLine, ...]
    client_notes: tuple[str, ...]           # each starting "**"
    tech_hours_hint: TechHoursHint | None   # the judge's suggestion, checked by the writer
    review_notes: tuple[str, ...]           # the judge's remarks for the estimator, never printed
    model: str
    refused: tuple[str, ...] = ()           # what it wrote that could not be used, and why
    quick_scan: dict = field(default_factory=dict)          # the GEM's Quick Scan, field by field
    explanation: str = ""                                   # the GEM's System Explanation
    contradictions: tuple[Contradiction, ...] = ()
    misc_responsibilities: tuple[str, ...] = ()             # printed as "**" notes at the end of the block
    exclusions: tuple[str, ...] = ()                        # review rows proposing named exceptions
    qc: tuple[QcCheck, ...] = ()
    changed: tuple[str, ...] = ()                           # lines the house check rewrote, each in plain words


# --- source ids ----------------------------------------------------------------------------------------

_ID = re.compile(r"\[?\b([A-Za-z]{1,4}\d+[a-z]?)\b\]?")
_CITED = re.compile(r"\[([A-Za-z]{1,4}\d+[a-z]?)\]")


def source_key(source: str) -> str:
    """"[S41]" -> "S41", the form `Dossier.sources` is keyed by."""
    return (source or "").strip().strip("[]").strip()


def known_ids(text: str, images: Sequence = (), ids: Sequence[str] | None = None) -> frozenset[str]:
    """The source ids the dossier text carries, with the pictures' ids (I1, I2, ..., or the job-wide `ids`)."""
    found = set(_CITED.findall(text or ""))
    if not found:
        return frozenset()
    return frozenset(found | set(_picture_ids(images, ids)))


def _ids(value, known: frozenset[str], unknown: list[str]) -> tuple[str, ...]:
    """The source ids in an answer's field, as "[S41]", in order, once each; ids the dossier does not
    have (when it has any) are left out and listed in `unknown`."""
    items = value if isinstance(value, (list, tuple)) else [value]
    out: list[str] = []
    for item in items:
        for found in _ID.findall(str(item or "")):
            if known and found not in known:
                unknown.append(found)
                continue
            cited = f"[{found}]"
            if cited not in out:
                out.append(cited)
    return tuple(out)


# --- pictures ------------------------------------------------------------------------------------------

def image_id(number: int) -> str:
    return f"I{number}"


def _picture_ids(images: Sequence, ids: Sequence[str] | None = None) -> list[str]:
    """Each picture's id: the job-wide ids given (I15, I17), else I1 … In in the order given."""
    if ids is not None and len(ids) == len(images):
        return [str(i) for i in ids]
    return [image_id(n) for n in range(1, len(images) + 1)]


def image_caption(image) -> str:
    where = [str(image.document or "")]
    if getattr(image, "sheet", None):
        where.insert(0, f"sheet {image.sheet}")
    if getattr(image, "page", None):
        where.append(f"page {image.page}")
    return f"{image.what} ({', '.join(w for w in where if w)})"


def images_text(images: Sequence, ids: Sequence[str] | None = None) -> str:
    if not images:
        return "Pictures: (none)"
    lines = [f"- {pid}: {image_caption(image)}" for pid, image in zip(_picture_ids(images, ids), images)]
    return "Pictures of the documents, attached (cite each by its id):\n" + "\n".join(lines)


def images_listing(images: Sequence, ids: Sequence[str] | None = None) -> list[dict]:
    """The pictures as the chat request lists them, for the chat helper to open, each by its job-wide id."""
    return [{"id": pid, "path": str(image.path), "what": image.what, "sheet": image.sheet,
             "document": image.document, "page": image.page} for pid, image in zip(_picture_ids(images, ids), images)]


def images_fingerprint(images: Sequence, ids: Sequence[str] | None = None) -> str:
    """What the pictures are, for the cache key: a changed picture is a new question."""
    if not images:
        return ""
    parts = []
    for pid, image in zip(_picture_ids(images, ids), images):
        try:
            digest = hashlib.sha256(Path(image.path).read_bytes()).hexdigest()
        except OSError:
            digest = "missing"
        parts.append(f"{pid} {image_caption(image)} {digest}")
    return "\n\nPictures:\n" + "\n".join(parts)


def content_blocks(prompt: str, images: Sequence, ids: Sequence[str] | None = None) -> list[dict]:
    """The API message: the prompt, then each picture after its caption (a base64 PNG). A picture
    that cannot be read, or is too big to send, is named in words instead."""
    blocks: list[dict] = [{"type": "text", "text": prompt}]
    for pid, image in list(zip(_picture_ids(images, ids), images))[:MAX_IMAGES]:
        caption = f"Picture {pid}: {image_caption(image)}"
        try:
            data = Path(image.path).read_bytes()
        except OSError:
            blocks.append({"type": "text", "text": f"{caption} — the picture could not be read."})
            continue
        if len(data) > MAX_IMAGE_BYTES:
            blocks.append({"type": "text", "text": f"{caption} — the picture is too big to send."})
            continue
        blocks.append({"type": "text", "text": caption})
        blocks.append({"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                   "data": base64.standard_b64encode(data).decode("ascii")}})
    if len(images) > MAX_IMAGES:
        blocks.append({"type": "text", "text": f"{len(images) - MAX_IMAGES} more pictures could not be sent."})
    return blocks


# --- the checklist ---------------------------------------------------------------------------------------

def checklist_text(templates) -> str:
    """The Master Template's systems, one line each: the name, the tags and kinds it applies to, and
    its hints on when it applies (never its tech hours)."""
    lines = []
    for template in templates:
        where = []
        if template.prefixes:
            where.append("tags " + ", ".join(template.prefixes))
        if template.kinds:
            where.append("kinds " + ", ".join(template.kinds))
        hints = [_squash(h).lstrip("*( ").rstrip(")") for h in template.hints]
        hints = [h for h in hints if h and "tech hour" not in h.lower()]
        line = f"- {template.name}"
        if where:
            line += f" ({'; '.join(where)})"
        if hints:
            line += ": " + "; ".join(hints)
        if len(line) > _CHECKLIST_LINE:
            line = line[: _CHECKLIST_LINE - 1].rstrip() + "…"
        lines.append(line)
    return "\n".join(lines)


# --- reading an answer ------------------------------------------------------------------------------

def _text(value) -> str:
    return _squash(str(value)) if isinstance(value, (str, int, float)) and not isinstance(value, bool) else ""


def _texts(value) -> list[str]:
    out = []
    for item in value if isinstance(value, (list, tuple)) else []:
        text = _text(item)
        if text and text not in out:
            out.append(text)
    return out


# --- the scope question: one planned system ---------------------------------------------------------------

def _system_text(system: PlannedSystem) -> str:
    quantity = ("not stated" if system.quantity is None
                else f"{system.quantity}, from {system.quantity_source or 'no source'}: “{system.quantity_quote}”")
    lines = [f"System: {system.header} (key {system.key})",
             f"Kind: {system.kind or '(not given)'}",
             f"Tags: {', '.join(system.tags) or '(none)'}",
             f"Quantity: {quantity}"]
    if system.group:
        lines.append(f"Group: {system.group} (it shares one block with the other systems of this group)")
    if system.alternate:
        lines.append(f"Alternate: {system.alternate} (the documents price it separately)")
    if system.exception:
        lines.append(f"Exception: {system.exception}")
    section = getattr(system, "sequence_section", "")
    lines.append(f"Sequence section: {section or '(none: no sequence section covers it)'}")
    families = getattr(system, "families", ()) or ()
    if families:
        lines.append("Families (one stacked header each, in this order):")
        for family in families:
            count = ("not stated" if family.quantity is None
                     else f"{family.quantity}, from {family.quantity_source or 'no source'}: “{family.quantity_quote}”")
            lines.append(f"- {family.header}: {count}")
    lines.append(f"Sources the plan cited: sequence {', '.join(system.sequence_sources) or '(none)'}; "
                 f"schedules {', '.join(system.schedule_sources) or '(none)'}")
    if system.why:
        lines.append(f"Why the plan wrote it: {system.why}")
    return "\n".join(lines)


def options_text(options) -> str:
    """The checklist: a template (its lines and when each applies), template lines, or plain texts."""
    if options is None:
        return "(no Master Template entry is close enough)"
    if isinstance(options, str):
        return options.strip() or "(none)"
    if hasattr(options, "lines") and hasattr(options, "name"):
        return _template_text(options)
    out = []
    for item in options:
        if isinstance(item, str):
            out.append(f"- {item}")
        elif hasattr(item, "lines") and hasattr(item, "name"):
            out.append(_template_text(item))
        elif hasattr(item, "text"):
            out.append(f"{'  ' * (max(1, int(getattr(item, 'depth', 1))) - 1)}- {item.text}")
    return "\n".join(out) or "(none)"


def write_prompt(system: PlannedSystem, evidence_text: str, images: Sequence, options, examples,
                 style_text: str, hours_rule: str = "", image_ids: Sequence[str] | None = None,
                 ledger_text: str = "") -> str:
    """The GEM's input for one system: the plan's system (its section and families), its evidence in the GEM's
    order (the whole sequence section, the points list, the schedule, the plan notes, the counts), its pictures,
    the nearest Master Template block introduced in the GEM's own words, and the template's tech-hour rule.
    `examples` and `style_text` are no longer asked: the GEM decides the wording. `ledger_text`, the system's
    ledger entry, goes right after the system, before the evidence."""
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


def write_schema() -> dict:
    text = {"type": "string"}
    texts = {"type": "array", "items": text}
    line = {
        "type": "object",
        "properties": {
            "text": text,
            "reference": text,
            "flag": {"type": "string", "enum": list(FLAGS)},
            "flag_text": text,
            "quantity": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
            "quote": text,
            "source_id": text,
            "depth": {"type": "integer"},
            "fact_ids": {"type": "array", "items": text},
        },
        "required": ["text", "reference", "flag", "flag_text", "quantity", "quote", "source_id", "depth", "fact_ids"],
        "additionalProperties": False,
    }
    quick_scan = {"type": "object", "properties": {k: text for k in QUICK_SCAN}, "required": list(QUICK_SCAN),
                  "additionalProperties": False}
    contradiction = {
        "type": "object",
        "properties": {"type": {"type": "string", "enum": list(CONFLICT_TYPES)}, "item": text, "quotes": texts,
                       "flag": {"type": "string", "enum": list(FLAGS)}},
        "required": ["type", "item", "quotes", "flag"],
        "additionalProperties": False,
    }
    qc = {
        "type": "object",
        "properties": {"check": {"type": "string", "enum": list(QC_CHECKS)}, "evidence": text,
                       "pass": {"type": "boolean"}, "fix": text},
        "required": ["check", "evidence", "pass", "fix"],
        "additionalProperties": False,
    }
    hours = {
        "type": "object",
        "properties": {
            "per": {"type": "string", "enum": list(TECH_HOUR_BASES)},
            "hours": {"type": "number"},
            "like": {"type": "string"},
        },
        "required": ["per", "hours", "like"],
        "additionalProperties": False,
    }
    properties = {
        "quick_scan": quick_scan,
        "explanation": text,
        "lines": {"type": "array", "items": line},
        "contradictions": {"type": "array", "items": contradiction},
        "misc_responsibilities": texts,
        "exclusions": texts,
        "qc": {"type": "array", "items": qc},
        "client_notes": texts,
        "tech_hours": {"anyOf": [hours, {"type": "null"}]},
        "review_notes": texts,
    }
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


_FACT_ID = re.compile(r"^\s*\[?\s*(F\d+)\s*\]?\s*$")


def _plain_fact_id(value) -> str:
    match = _FACT_ID.match(str(value or ""))
    return match.group(1) if match else ""


def _flag(value) -> str:
    """ "red" / "🔴" / "RED" as "red"; anything else as ""."""
    text = _text(value).strip()
    if text in _FLAG_SYMBOLS:
        return _FLAG_SYMBOLS[text]
    low = text.lower()
    return low if low in FLAGS else ""


def _without_flag(text: str) -> tuple[str, str]:
    """(the line without a flag symbol written into it, the flag it named or "")."""
    found = ""
    for symbol, flag in _FLAG_SYMBOLS.items():
        if symbol in text:
            found = found or flag
            text = text.replace(symbol, " ")
    return _squash(text), found


def _diamond(text: str, style: HouseStyle) -> str | None:
    """The GEM's "Controls Contractor requires mfr. rep …" line (v3.2 marked it "◊"; v4 does not) as the Master
    Template writes it."""
    if not _DIAMOND.match(text):
        return None
    return next((line for line in style.trio if line.lower().startswith("ame requires")), None)


def parse_scope(answer: dict, model: str, style: HouseStyle, known: frozenset[str] = frozenset()) -> WrittenScope:
    """Read the GEM's answer. Every line is kept, in the GEM's words: a line with no reference line is flagged
    orange (its flag_text says so), never dropped. Only a line the client must never see (prices, hours, a
    category word) or one copying the specification's wording with no house verb is refused. A number with no
    words stating it is taken off its line; a source id the evidence does not have is cleared. The GEM's "◊"
    line is the Master Template's "AME requires mfr. Rep …" line, one level deeper. Each refusal is listed."""
    refused: list[str] = []
    lines: list[WrittenLine] = []
    seen: set[tuple[str, int]] = set()
    last_depth = 0
    for raw in answer.get("lines") or []:
        if not isinstance(raw, dict):
            continue
        text, written_flag = _without_flag(_text(raw.get("text")))
        if not text:
            continue
        diamond = _diamond(text, style)
        if diamond is not None:
            text, depth = diamond, min(max(last_depth, 1) + 1, MAX_DEPTH)
        else:
            depth = min(_depth(raw.get("depth")), last_depth + 1, MAX_DEPTH)
            house = style.house_opening(text)      # "ATC Contractor to provide …" is "Furnish …"
            if house is None:
                refused.append(f"“{text}” — it copies the specification's wording (“ATC Contractor to …”) with no "
                               "house verb for it")
                continue
            text = house
        bad = style.forbidden(text)
        if bad:
            refused.append(f"“{text}” — {bad}")
            continue
        if (text.lower(), depth) in seen:          # an exact repeat
            continue
        legacy = "reference" not in raw           # an answer from before the GEM: no reference line to ask for
        reference = _text(raw.get("reference"))
        flag, flag_text = _flag(raw.get("flag")) or written_flag, _text(raw.get("flag_text"))
        quote, why = _text(raw.get("quote")), _text(raw.get("why")) or reference
        if not legacy and not reference and flag in ("", "green"):
            flag, flag_text = "orange", flag_text or NO_REFERENCE
        quantity = _quantity(raw.get("quantity"))
        if quantity is not None and not quote:
            refused.append(f"the AI gave {quantity} for “{text}” with no words stating it; the number was left out")
            quantity = None
        if "confidence" in raw:
            confidence = _confidence(raw.get("confidence"))
        else:
            confidence = REFERENCED_CONFIDENCE if reference and quote else UNREFERENCED_CONFIDENCE
        if not quote:
            confidence = min(confidence, NO_EVIDENCE_CONFIDENCE)
        unknown: list[str] = []
        sources = _ids(raw.get("source_id"), known, unknown)
        if unknown:
            refused.append(f"“{text}” cites {', '.join(f'[{u}]' for u in unknown)}, which the evidence does "
                           "not have; the source was left out")
        seen.add((text.lower(), depth))
        last_depth = depth
        fact_ids = tuple(i for i in (_plain_fact_id(f) for f in (raw.get("fact_ids") or ())) if i)
        lines.append(WrittenLine(text=text, depth=depth, quantity=quantity, quote=quote,
                                 source_id=sources[0] if sources else "", why=why, confidence=confidence,
                                 reference=reference, flag=flag, flag_text=flag_text, fact_ids=fact_ids))
    notes = []
    for note in answer.get("client_notes") or []:
        note = _text(note)
        if not note:
            continue
        bad = style.check_note(note) or ("it copies the specification's wording (“ATC Contractor to …”)"
                                         if style.is_spec_wording(note) else None)
        if bad:
            refused.append(f"the note “{note}” — {bad}")
            continue
        if note not in notes:
            notes.append(note)
    hint = _tech_hours(answer.get("tech_hours"), refused)
    return WrittenScope(lines=tuple(lines), client_notes=tuple(notes), tech_hours_hint=hint,
                        review_notes=tuple(_texts(answer.get("review_notes"))), model=model,
                        refused=tuple(refused), quick_scan=_quick_scan(answer.get("quick_scan")),
                        explanation=_text(answer.get("explanation")),
                        contradictions=_contradictions(answer.get("contradictions")),
                        misc_responsibilities=tuple(_texts(answer.get("misc_responsibilities"))),
                        exclusions=tuple(_texts(answer.get("exclusions"))), qc=_qc(answer.get("qc")))


_QTY_IN_TEXT = re.compile(r"\(?\bQty\.?\s*\(?\s*(\d+)", re.I)   # "(Qty. 12 Total)" written in a line


def ledger_check(scope: WrittenScope, facts: frozenset[str], counts: frozenset[int]) -> WrittenScope:
    """The two ledger rules on a written scope: with `facts`, a line naming none of them is refused; with `counts`,
    a line whose quantity, or a count written in its text ("(Qty. 12 Total)"), is none of them is refused; with
    facts but no counts, a line giving any count is refused. Each refusal is listed in plain words."""
    if not facts and not counts:
        return scope
    kept, refused = [], list(scope.refused)
    for line in scope.lines:
        if facts and not (set(line.fact_ids) & set(facts)):
            refused.append(f"“{line.text}” names no fact of this system's ledger entry; left out")
            continue
        if facts and not counts:                 # the entry holds no count: a line may give none
            given = line.quantity if line.quantity is not None else                 next((int(m) for m in _QTY_IN_TEXT.findall(line.text)), None)
            if given is not None:
                refused.append(f"“{line.text}” gives {given}, but this system's ledger entry holds no count; left out")
                continue
        if counts and line.quantity is not None and line.quantity not in counts:
            refused.append(f"“{line.text}” gives {line.quantity}, which is no count in this system's ledger entry; "
                           "left out")
            continue
        written = next((n for n in (int(m) for m in _QTY_IN_TEXT.findall(line.text)) if n not in counts), None) \
            if counts else None
        if written is not None:
            refused.append(f"“{line.text}” gives {written}, which is no count in this system's ledger entry; "
                           "left out")
            continue
        kept.append(line)
    return dataclasses.replace(scope, lines=tuple(kept), refused=tuple(refused))


def _quick_scan(raw) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    return {k: _text(raw.get(k)) for k in QUICK_SCAN if _text(raw.get(k))}


def _contradictions(raw) -> tuple[Contradiction, ...]:
    out = []
    for item in raw if isinstance(raw, (list, tuple)) else []:
        if not isinstance(item, dict):
            continue
        kind = _text(item.get("type")).upper()
        what = _text(item.get("item"))
        if kind not in CONFLICT_TYPES or not what:
            continue
        out.append(Contradiction(kind, what, tuple(_texts(item.get("quotes"))), _flag(item.get("flag"))))
    return tuple(out)


def _qc(raw) -> tuple[QcCheck, ...]:
    out = []
    for item in raw if isinstance(raw, (list, tuple)) else []:
        if not isinstance(item, dict):
            continue
        check = _text(item.get("check")).upper()
        if check not in QC_CHECKS:
            continue
        out.append(QcCheck(check, _text(item.get("evidence")), item.get("pass") is True, _text(item.get("fix"))))
    return tuple(out)


# --- the dossier's sections, and a text too long to read at once -------------------------------------

# The dossier's numbered sections, by number: the words each heading carries.
_SECTIONS = {1: "job", 2: "sequence", 3: "point", 4: "schedule", 5: "count", 6: "device", 7: "note", 8: "spec"}
_HEADING = re.compile(r"^[ \t#=*]*(?:section\s+)?([1-8])\s*[.):]?\s*[-—:]?\s*(\S.{0,90})$", re.I)


def _sections(text: str) -> tuple[str, dict[int, str]]:
    """(text before the first heading, {section number: its text with its heading}). Headings count
    only in order, so a numbered paragraph inside the sequence is never taken for one."""
    lines = text.splitlines(keepends=True)
    before: list[str] = []
    found: dict[int, list[str]] = {}
    current = None
    for line in lines:
        match = _HEADING.match(line.rstrip("\r\n"))
        if match:
            number = int(match.group(1))
            if (current is None or number > current) and _SECTIONS[number] in match.group(2).lower():
                current = number
                found[number] = [line]
                continue
        (found[current] if current is not None else before).append(line)
    return "".join(before), {n: "".join(chunk) for n, chunk in found.items()}


def _chunks(text: str, limit: int) -> list[str]:
    """The text cut at line ends into pieces of at most `limit` characters (a longer line is cut too)."""
    limit = max(limit, 1000)
    pieces: list[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        while len(line) > limit:
            if current:
                pieces.append(current)
                current = ""
            pieces.append(line[:limit])
            line = line[limit:]
        if len(current) + len(line) > limit and current:
            pieces.append(current)
            current = ""
        current += line
    if current.strip():
        pieces.append(current)
    return pieces
