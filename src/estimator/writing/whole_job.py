"""The whole-job judge: the AI reads the job's whole dossier the way an estimator reads a bid set.

The question the judge answers here:
- "plan_job" (`Judge.plan_job`): one pass over the whole dossier lists every system the job gives
  AME controls scope for, with its quantity, where the documents state it, and the source id of
  every paragraph, row and count it rests on. A dossier over `SPLIT_LIMIT` characters is read in
  parts (the sequence and the schedules first, then the rest) and the parts' plans are merged by key.

This module holds the answers' shapes, the prompts, the schemas and the checks; `judge.py` asks the
questions through its cache and its chat/API hand-off. Nothing here decides scope by itself: it only
reads the AI's answer and throws out what cannot be trusted (a quantity with no words stating it, a
header the client must not see, a source id the dossier does not have), saying so in plain words.

A dossier picture (`DossierImage`) is anything with path, what, sheet, document and page. In the
API it goes as an image block with its caption; in the chat the request lists the paths to open.
"""
from __future__ import annotations

import base64
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence

from estimator.writing.judge import MAX_HEADER, _quantity, _squash
from estimator.writing.style import HouseStyle

SPLIT_LIMIT = 150_000        # characters of dossier read in one pass
MAX_IMAGES = 100             # pictures sent with one question
MAX_IMAGE_BYTES = 5 * 1024 * 1024   # the API takes no bigger picture
ALTERNATES = ("", "add", "deduct")
FRONT_END_MODES = ("new-system", "extend-existing")
_CHECKLIST_LINE = 300        # characters of one checklist line

PLAN_PROMPT = """\
You are an HVAC controls estimator at AME. You are reading the whole bid set of a building controls \
job, gathered into one dossier: the job's documents, the sequence of operation, the points lists, the \
equipment schedules, the equipment counts, the devices shown on the plans, the drawing notes and the \
controls specification. Every paragraph, row and count carries a source id in brackets, such as [S12]. \
Read it the way you would read the bid set itself, then list every system this job gives AME controls \
scope for, with its quantity. A later pass writes each system's scope lines; this pass decides what \
the systems are.

How to answer:
- systems: every system the sequence of operation, the schedules or the plans give controls scope \
to, in the order a proposal lists them. Include the ones with no tag, such as a fire pump, a \
generator, a CO detection panel, heat tracing or destratification fans. Use the Master Template \
checklist to make sure nothing is missed, but it is not a closed menu: write any system the \
documents give controls scope to.
- key: a short unique key you choose from the tags, such as "RTU-1-3".
- header: the block header the way AME writes it, without the count: the kind, then the tags, such \
as "Rooftop Unit RTU-1 thru 3".
- kind: the kind of equipment in plain words; the Master Template system name when one fits.
- tags: every equipment tag the system covers, as the documents write them.
- Split a family into two systems where the sequence treats some of its units differently from the \
rest (for example exhaust fans interlocked with a unit, and exhaust fans on the BMS schedule).
- quantity: a type row with a QUANTITY column, or a tag placed many times on the plans, is that many \
units, never one. Give a quantity only when a source states it or a count in the dossier shows it: \
quantity_source is the source id of that row, count or paragraph, such as "[S41]", and \
quantity_quote the words or numbers stating it, copied exactly. Never invent a number: when no \
source states it, the quantity is null and why says what is missing.
- sequence_sources and schedule_sources: the source ids of the sequence paragraphs and the schedule \
rows about this system. A picture is cited by its image id, such as "[I2]".
- group: when several systems share one block (for example a chilled water plant's chillers and \
pumps), the same group name on each; otherwise "".
- alternate: "add" or "deduct" only when the documents say the system is an alternate (for example \
in-apartment equipment the documents price separately); otherwise "".
- exception: when a unit needs no BMS work because it runs on its own integral thermostat or a \
manufacturer's switch, the one-line exception in capitals, such as "EXCEPTION TO ANY WORK WITH \
Qty (4) CUH-1 thru 4 - INTEGRAL THERMOSTAT"; otherwise "".
- why: one sentence in plain English.
- front_end: "new-system" when the job gets a new BMS, "extend-existing" when the documents say the \
work extends an existing one (existing_name: that system's name as the documents give it, else \
""); lines: the front end scope the documents call for, in the house style; notes: clarifications \
for the client, each starting with "**"; sources: the source ids they rest on.
- unresolved: plain questions for the estimator, about anything the documents leave open.
- Cite a source id for everything. Never write prices, tech hours, confidence or category words."""


class DossierImage(Protocol):
    """A picture of the job's documents the text could not read (a picture schedule, say)."""
    path: str
    what: str
    sheet: str | None
    document: str
    page: int


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


@dataclass(frozen=True)
class JobPlan:
    systems: tuple[PlannedSystem, ...]
    front_end: dict           # {"mode": "new-system"|"extend-existing"|"", "existing_name", "lines", "notes", "sources"}
    unresolved: tuple[str, ...]   # plain questions for the estimator
    model: str
    dropped: tuple[str, ...] = ()  # systems the AI planned that could not be trusted, and why


@dataclass(frozen=True)
class DossierPart:
    """One pass's share of a dossier too long to read at once."""
    text: str
    number: int
    of: int
    has_schedules: bool       # the part with the schedules takes the pictures


# --- source ids ----------------------------------------------------------------------------------------

_ID = re.compile(r"\[?\b([A-Za-z]{1,4}\d+[a-z]?)\b\]?")
_CITED = re.compile(r"\[([A-Za-z]{1,4}\d+[a-z]?)\]")


def source_key(source: str) -> str:
    """"[S41]" -> "S41", the form `Dossier.sources` is keyed by."""
    return (source or "").strip().strip("[]").strip()


def known_ids(text: str, images: Sequence = ()) -> frozenset[str]:
    """The source ids the dossier text carries, with the pictures' ids (I1, I2, ...)."""
    found = set(_CITED.findall(text or ""))
    if not found:
        return frozenset()
    return frozenset(found | {f"I{n}" for n in range(1, len(images) + 1)})


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


def image_caption(image) -> str:
    where = [str(image.document or "")]
    if getattr(image, "sheet", None):
        where.insert(0, f"sheet {image.sheet}")
    if getattr(image, "page", None):
        where.append(f"page {image.page}")
    return f"{image.what} ({', '.join(w for w in where if w)})"


def images_text(images: Sequence) -> str:
    if not images:
        return "Pictures: (none)"
    lines = [f"- {image_id(n)}: {image_caption(image)}" for n, image in enumerate(images, start=1)]
    return "Pictures of the documents, attached (cite each by its id):\n" + "\n".join(lines)


def images_listing(images: Sequence) -> list[dict]:
    """The pictures as the chat request lists them, for the chat helper to open."""
    return [{"id": image_id(n), "path": str(image.path), "what": image.what, "sheet": image.sheet,
             "document": image.document, "page": image.page} for n, image in enumerate(images, start=1)]


def images_fingerprint(images: Sequence) -> str:
    """What the pictures are, for the cache key: a changed picture is a new question."""
    if not images:
        return ""
    parts = []
    for n, image in enumerate(images, start=1):
        try:
            digest = hashlib.sha256(Path(image.path).read_bytes()).hexdigest()
        except OSError:
            digest = "missing"
        parts.append(f"{image_id(n)} {image_caption(image)} {digest}")
    return "\n\nPictures:\n" + "\n".join(parts)


def content_blocks(prompt: str, images: Sequence) -> list[dict]:
    """The API message: the prompt, then each picture after its caption (a base64 PNG). A picture
    that cannot be read, or is too big to send, is named in words instead."""
    blocks: list[dict] = [{"type": "text", "text": prompt}]
    for n, image in enumerate(images[:MAX_IMAGES], start=1):
        caption = f"Picture {image_id(n)}: {image_caption(image)}"
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


def _checklist(checklist) -> str:
    if isinstance(checklist, str):
        return checklist
    return checklist_text(checklist)


# --- the plan question -----------------------------------------------------------------------------------

def plan_prompt(dossier_text: str, images: Sequence, checklist, style_text: str,
                part: DossierPart | None = None) -> str:
    parts = []
    if part is not None and part.of > 1:
        parts.append(
            f"This is part {part.number} of {part.of} of the dossier: it was too long to read at once. "
            "Plan the systems this part shows. Another pass reads the rest and the plans are merged by "
            "key, so give each system the key its tags suggest (such as \"RTU-1-3\"), the same in every part.")
    parts += [f"The dossier:\n{(dossier_text or '').strip() or '(empty)'}",
              images_text(images if part is None or part.has_schedules else ()),
              "The Master Template checklist (the systems AME writes, and when each applies):\n"
              + (_checklist(checklist).strip() or "(none)"),
              (style_text or "").strip() or "(no house style given)"]
    return "\n\n".join(parts)


def plan_schema() -> dict:
    ids = {"type": "array", "items": {"type": "string"}}
    system = {
        "type": "object",
        "properties": {
            "key": {"type": "string"},
            "header": {"type": "string"},
            "kind": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
            "quantity": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
            "quantity_source": {"type": "string"},
            "quantity_quote": {"type": "string"},
            "sequence_sources": ids,
            "schedule_sources": ids,
            "group": {"type": "string"},
            "alternate": {"type": "string", "enum": list(ALTERNATES)},
            "exception": {"type": "string"},
            "why": {"type": "string"},
        },
        "required": ["key", "header", "kind", "tags", "quantity", "quantity_source", "quantity_quote",
                     "sequence_sources", "schedule_sources", "group", "alternate", "exception", "why"],
        "additionalProperties": False,
    }
    front_end = {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": list(FRONT_END_MODES)},
            "existing_name": {"type": "string"},
            "lines": {"type": "array", "items": {"type": "string"}},
            "notes": {"type": "array", "items": {"type": "string"}},
            "sources": ids,
        },
        "required": ["mode", "existing_name", "lines", "notes", "sources"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "systems": {"type": "array", "items": system},
            "front_end": front_end,
            "unresolved": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["systems", "front_end", "unresolved"],
        "additionalProperties": False,
    }


def _text(value) -> str:
    return _squash(str(value)) if isinstance(value, (str, int, float)) and not isinstance(value, bool) else ""


def _texts(value) -> list[str]:
    out = []
    for item in value if isinstance(value, (list, tuple)) else []:
        text = _text(item)
        if text and text not in out:
            out.append(text)
    return out


def _exception(text: str) -> str:
    """In capitals, with the house "Qty (n)" kept as the estimator writes it."""
    return re.sub(r"\bQTY\s*\(", "Qty (", text.upper())


def parse_plan(answer: dict, model: str, style: HouseStyle, known: frozenset[str] = frozenset()) -> JobPlan:
    """Read the AI's plan. A system with a quantity but no words stating it, or with no usable header,
    is dropped and put to the estimator; ids the dossier does not have are left out and named."""
    systems: list[PlannedSystem] = []
    dropped: list[str] = []
    unresolved: list[str] = []
    keys: set[str] = set()
    for raw in answer.get("systems") or []:
        if not isinstance(raw, dict):
            continue
        header = _squash(re.sub(r"^\s*Qty\s*\([^)]*\)\s*", "", _text(raw.get("header"))))
        kind = _text(raw.get("kind"))
        key = _text(raw.get("key")) or header
        name = header or kind or key or "a system"
        bad = ("it has no header" if not header else style.forbidden(header)
               or ("it is longer than a header" if len(header) > MAX_HEADER else None))
        if bad:
            dropped.append(f"{name} — {bad}")
            unresolved.append(f"The AI planned “{name}” but its header could not be used ({bad}): "
                              "should it be written?")
            continue
        unknown: list[str] = []
        quantity = _quantity(raw.get("quantity"))
        quote = _text(raw.get("quantity_quote"))
        quantity_sources = _ids(raw.get("quantity_source"), known, unknown)
        if quantity is not None and not quote:
            dropped.append(f"{name} — it gives {quantity} with no words stating it")
            unresolved.append(f"The AI planned {quantity} × “{name}” but quoted no words stating the number, "
                              "so it was left out: how many are there?")
            continue
        exception = _text(raw.get("exception"))
        bad_exception = style.forbidden(exception) if exception else None
        if bad_exception:
            unresolved.append(f"The exception the AI wrote for “{name}” was left out ({bad_exception}).")
            exception = ""
        alternate = _text(raw.get("alternate")).lower()
        if key.lower() in keys:
            key = f"{key}-{len(systems) + 1}"
        keys.add(key.lower())
        system = PlannedSystem(
            key=key, header=header, kind=kind, tags=tuple(_texts(raw.get("tags"))), quantity=quantity,
            quantity_source=quantity_sources[0] if quantity_sources else "", quantity_quote=quote,
            sequence_sources=_ids(raw.get("sequence_sources") or [], known, unknown),
            schedule_sources=_ids(raw.get("schedule_sources") or [], known, unknown),
            group=_text(raw.get("group")), alternate=alternate if alternate in ALTERNATES else "",
            exception=_exception(exception), why=_text(raw.get("why")))
        if unknown:
            unresolved.append(f"The AI cited {', '.join(f'[{u}]' for u in dict.fromkeys(unknown))} for "
                              f"“{name}”, which the dossier does not have; left out.")
        systems.append(system)
    front_end = _front_end(answer.get("front_end"), known, unresolved)
    for question in _texts(answer.get("unresolved")):
        if question not in unresolved:
            unresolved.append(question)
    return JobPlan(systems=tuple(systems), front_end=front_end, unresolved=tuple(unresolved), model=model,
                   dropped=tuple(dropped))


def _front_end(raw, known: frozenset[str], unresolved: list[str]) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    mode = _text(raw.get("mode"))
    unknown: list[str] = []
    front_end = {"mode": mode if mode in FRONT_END_MODES else "",
                 "existing_name": _text(raw.get("existing_name")),
                 "lines": _texts(raw.get("lines")),
                 "notes": _texts(raw.get("notes")),
                 "sources": list(_ids(raw.get("sources") or [], known, unknown))}
    if unknown:
        unresolved.append(f"The AI cited {', '.join(f'[{u}]' for u in dict.fromkeys(unknown))} for the front "
                          "end, which the dossier does not have; left out.")
    return front_end


# --- a dossier too long to read at once -------------------------------------------------------------------

# The dossier's numbered sections, by number: the words each heading carries.
_SECTIONS = {1: "job", 2: "sequence", 3: "point", 4: "schedule", 5: "count", 6: "device", 7: "note", 8: "spec"}
_FIRST_GROUP, _SECOND_GROUP = (2, 3, 4), (5, 6, 7, 8)
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


def split_dossier(text: str, limit: int = SPLIT_LIMIT) -> list[DossierPart]:
    """The dossier in parts of about `limit` characters, each opening with the Job section: the
    sequence, points lists and schedules first, then the counts, devices, notes and spec. A dossier
    within the limit is one part, whole."""
    text = text or ""
    if len(text) <= limit:
        return [DossierPart(text=text, number=1, of=1, has_schedules=True)]
    before, sections = _sections(text)
    head = before + sections.get(1, "")
    if len(head) > limit // 4:           # no usable Job section to repeat: cut the whole text
        head = ""
    pieces: list[tuple[str, bool]] = []
    if sections.keys() - {1}:
        groups = [_FIRST_GROUP, _SECOND_GROUP]
    else:
        groups = []
        pieces = [(chunk, False) for chunk in _chunks(text, limit)]
    for group in groups:
        body = "".join(sections.get(n, "") for n in group)
        if not body.strip():
            continue
        schedules = sections.get(4, "").strip()
        for chunk in _chunks(body, limit - len(head)):
            pieces.append((head + chunk, bool(schedules) and schedules[:200] in chunk))
    if not any(has for _, has in pieces) and pieces:
        pieces[0] = (pieces[0][0], True)
    elif sum(has for _, has in pieces) > 1:          # the schedules ran over two parts: the first takes the pictures
        first = next(i for i, (_, has) in enumerate(pieces) if has)
        pieces = [(t, i == first) for i, (t, _) in enumerate(pieces)]
    return [DossierPart(text=t, number=n, of=len(pieces), has_schedules=has)
            for n, (t, has) in enumerate(pieces, start=1)]


def merge_plans(plans: Sequence[JobPlan], total: int) -> JobPlan:
    """The parts' plans as one, merged by key (or by the same tags): the first part's header, kind
    and number stand; tags and sources are joined; a number that disagrees goes to the estimator."""
    merged: dict[str, dict] = {}
    order: list[str] = []
    by_tags: dict[tuple, str] = {}
    unresolved: list[str] = [f"The dossier was {total:,} characters, so the AI read it in parts "
                             f"({len(plans)}) and the plans were merged by key: check nothing is counted twice."]
    dropped: list[str] = []
    front_end = {"mode": "", "existing_name": "", "lines": [], "notes": [], "sources": []}
    for plan in plans:
        for system in plan.systems:
            tags = tuple(sorted(t.upper() for t in system.tags))
            key = system.key.lower()
            if key not in merged and tags and tags in by_tags:
                key = by_tags[tags]
            if key not in merged:
                merged[key] = dict(system.__dict__)
                order.append(key)
                if tags:
                    by_tags.setdefault(tags, key)
                continue
            have = merged[key]
            for field in ("tags", "sequence_sources", "schedule_sources"):
                have[field] = tuple(dict.fromkeys((*have[field], *getattr(system, field))))
            if have["quantity"] is None and system.quantity is not None:
                for field in ("quantity", "quantity_source", "quantity_quote"):
                    have[field] = getattr(system, field)
            elif system.quantity is not None and system.quantity != have["quantity"]:
                question = (f"For {have['key']} one part of the dossier gives {have['quantity']} "
                            f"({have['quantity_source'] or 'no source'}) and another {system.quantity} "
                            f"({system.quantity_source or 'no source'}): which is right?")
                if question not in unresolved:
                    unresolved.append(question)
            for field in ("group", "alternate", "exception", "why", "kind"):
                if not have[field] and getattr(system, field):
                    have[field] = getattr(system, field)
        for field in ("mode", "existing_name"):
            if not front_end[field] and plan.front_end.get(field):
                front_end[field] = plan.front_end[field]
        for field in ("lines", "notes", "sources"):
            for item in plan.front_end.get(field, []):
                if item not in front_end[field]:
                    front_end[field].append(item)
        for question in plan.unresolved:
            if question not in unresolved:
                unresolved.append(question)
        dropped += [d for d in plan.dropped if d not in dropped]
    return JobPlan(systems=tuple(PlannedSystem(**merged[k]) for k in order), front_end=front_end,
                   unresolved=tuple(unresolved), model=plans[0].model if plans else "", dropped=tuple(dropped))
