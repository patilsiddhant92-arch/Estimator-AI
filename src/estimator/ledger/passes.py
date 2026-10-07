# src/estimator/ledger/passes.py
"""The seven reading passes (design 2026-09-29 §2): each reads its own documents from the dossier, sees the ledger
so far and the earlier passes' understanding, and answers with facts, contradictions, confirmations and its own
understanding. `apply` turns an answer into ledger changes and refuses, in plain words, whatever cannot be
trusted: a kind the pass may not write, a source the documents do not have, a fact with no quote. A different
value for a settled fact is never a change: it is a contradiction beside the fact. A provisional (added) fact of a
kind this pass settles takes the pass's value and is settled; a count that changes keeps the old count beside it,
so the higher still prints."""
from __future__ import annotations

import re
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
    not_sheet_types: tuple[str, ...] = ()   # sheets of these types are another pass's, even when typed for this one
    picture_types: tuple[str, ...] = ()     # its sheets of these types are also sent as whole-sheet pictures

    @property
    def kinds(self) -> tuple[str, ...]:
        return self.settles + self.may_add


PASSES: tuple[Pass, ...] = (
    Pass("schedules", "Schedules", ("family", "unit", "count", "provider"), (), (4, 5), (), True,
         "Settle the equipment list: every family on the schedules, its tags, its count (a QUANTITY column, else the "
         "rows) and, from the notes under each schedule, who provides the unit controller (\"unit mfr\", \"AME\", "
         "\"owner\", or the words used). A schedule that is a picture is given as an image: read it. Nothing later "
         "can add a scheduled family, so be complete."),
    Pass("plans", "Plans", ("location", "device", "link"), ("family", "unit", "count", "note"), (6, 7), ("Plans",), False,
         "For each family already in the ledger, settle where its units are (floors, zones, rooms) and the devices "
         "around them: sensors, thermostats, damper actuators, and the keynotes that add controls scope. Equipment "
         "on the plans that no schedule lists may only be added, with the subject \"seen on plans, not scheduled\" "
         "in its quote's words; it is flagged later. Give the family a short kind name (a few words) and put the reasons in "
         "a note fact with the family's prefix as the note's subject (never \"question\" or \"general\"), not in the name. Give the count you can see, citing the sheet. When a motorized "
         "damper sits on a fan's duct or next to a fan on the plan, record a link: subject the damper's tag or label, "
         "value the fan's tag. Note: a count's value is a whole number; put the words in the quote.",
         picture_types=("Plans",)),
    Pass("details", "Details and control diagrams", ("device", "link"), (), (), ("Details", "Control diagrams", "Diagrams"), False,
         "For units already in the ledger, settle what the details and control diagrams add: control valves, damper "
         "actuators, fire and smoke damper integration, expansion tank sensors, anything touching a scheduled "
         "unit. Write nothing about equipment the ledger does not hold.",
         not_sheet_types=("Air riser", "Water riser", "Network riser")),
    Pass("risers", "Air and water risers", ("link", "group", "device"), ("family", "unit", "count", "note"), (), ("Air riser", "Water riser"), False,
         "Settle how the systems fit together: which unit serves which (a link: subject the served unit, value the "
         "serving unit), the plant loop (a group: subject the plant's name, value the families in it, comma "
         "separated), and the sensors on the risers (pressure, differential pressure, stair pressurisation). "
         "A group is one plant that one sequence controls (a chilled water plant, a VRF system), never a riser, a "
         "shaft or a drain route; its subject is a short plant name of at most five words. "
         "Equipment on a riser that neither the schedule nor the plans showed may only be added, quoting the riser; give "
         "it a short kind name (a few words) and put the reasons in a note fact with the family's prefix as the note's subject (never \"question\" or \"general\"), not in the name. "
         "Note: a count's value is a whole number; put the words in the quote.",
         picture_types=("Air riser", "Water riser")),
    Pass("network", "Network riser", ("provider", "link"), (), (), ("Network riser",), False,
         "Settle who provides the backbone (fibre or Ethernet), the network switches, the server, the workstation "
         "or laptop, and every integration callout (VFDs, plumbing, electrical, lighting): a provider fact per item, "
         "subject the item, value the provider in the documents' words."),
    Pass("sequence", "Sequence of operation and points list", ("sequence_match", "note"), ("family", "unit", "count"), (2, 3), (), False,
         "Match each sequence section (its Q id) to the family or group in the ledger it describes: a "
         "sequence_match fact whose subject is the section's heading and whose value is that family's prefix or "
         "the group's name, citing the section. When a section gives the BMS work on a system that no family in the "
         "live list covers (plumbing pumps, domestic water heaters, heat tracing, a gas booster, glycol feed, a "
         "generator), add a family fact for it (kind and name, with a short subject; no count fact), citing the "
         "section; add a count fact only when the section itself states one, quoting it. Notes are also for alternates (subject \"alternate\", value "
         "\"add\" or \"deduct\" and the family), exceptions (subject \"exception\", value the one-line exception in "
         "capitals), questions for the estimator (subject \"question\"), and "
         "notes with subject \"general\" for rules the sequence sets for the whole job (fire/smoke damper control, "
         "who wires non-FSD actuators, global points)."),
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
        wanted, others = set(pass_.sheet_types), set(pass_.not_sheet_types)
        lines = [line for _sid, number, line in sheet_text_lines(dossier.text)
                 if number and wanted & set(types.get(number, ())) and not others & set(types.get(number, ()))]
        if lines:
            parts.append("\n".join([f"== SHEET TEXT: {', '.join(pass_.sheet_types)} ==", *lines]))
    return "\n\n".join(parts)


# --- the question ----------------------------------------------------------------------------------------------

def _match_values(ledger) -> list[str]:
    """What a sequence_match's value may be: the ledger's family prefixes, then its group subjects."""
    names = [f.subject for f in ledger.of_kind("family")] + [g.subject for g in ledger.of_kind("group")]
    return [n for n in dict.fromkeys(_text(n) for n in names) if n]


def prompt(pass_, ledger, text: str, images=(), ids=None, notes=()) -> str:
    from estimator.writing.whole_job import images_text
    job = getattr(ledger, "job_name", "") or "(unnamed job)"
    understood = "\n".join(f"- after the {name} pass: {words}" for name, words in ledger.understanding.items()) or "(nothing yet)"
    kinds = ", ".join(pass_.settles) + (f"; may only add: {', '.join(pass_.may_add)}" if pass_.may_add else "")
    instructions = pass_.instructions
    if "sequence_match" in pass_.settles:
        instructions += f"\nMatch values you may use: {', '.join(_match_values(ledger)) or '(none yet)'}"
    return "\n\n".join(filter(None, [
        f"Job: {job}\nThis is the {pass_.title} pass ({pass_.name}).",
        f"What the earlier passes understood:\n{understood}",
        f"The job ledger so far (id, kind, subject = value [source] “quote” (state, pass)):\n{ledger.table() or '(empty)'}",
        f"This pass settles these kinds of fact: {kinds}.\n{instructions}",
        f"The documents for this pass, each paragraph with its source id:\n{text}",
        images_text(list(images), ids) if images else "",
        "\n".join(notes),
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


_LEADING_NUMBER = re.compile(r"^\s*(?:about\s+)?(\d+)(?![\w\-/]|\.\d)", re.I)
NOT_A_NUMBER = "a count must be a number; the words go in the quote; left out"
GROUP_WORDS = 6          # a group's subject is a plant's short name: more words than this is a riser or a route


def _value(value, kind: str = ""):
    """The value as the ledger keeps it. A count is a whole number: its leading number ("55 placements on the
    plans" is 55, "about 27" is 27), or None when it has none (refused). A device takes its leading number when it
    has one, else keeps its words. Any other kind: a number when it is all digits, else the words."""
    if isinstance(value, bool):
        return None if kind == "count" else str(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else (None if kind == "count" else str(value))
    text = _text(value)
    if kind in ("count", "device"):
        match = _LEADING_NUMBER.match(text)
        if match:
            return int(match.group(1))
        return None if kind == "count" else text
    return int(text) if text.isdigit() else text


def _naming(name: str) -> re.Pattern:
    return re.compile(rf"(?<![A-Za-z0-9]){re.escape(name)}(?![A-Za-z0-9])", re.I)


def _names_a_system(value: str, names: list[str]) -> bool:
    """The value IS one of the ledger's family prefixes or group subjects (spaces squashed, any case)."""
    value = _text(value).casefold()
    return any(_text(name).casefold() == value for name in names if _text(name))


def _number(value) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    text = _text(value)
    return int(text) if text.isdigit() else None


def _many_valued(kind: str, subject: str) -> bool:
    """Kinds that hold many values for one subject: every note, the front end's lines and client notes, every
    location. Each value is its own fact; the rest hold one value per kind and subject."""
    return kind in ("note", "location") or (kind == "front_end" and subject.casefold() in ("line", "note"))


def _held(ledger: Ledger, kind: str, subject: str, sid: str):
    """The fact an answer speaks to. A sequence heading can repeat ("1. OCCUPIED MODE" under each system), so a
    sequence_match citing a section the ledger holds is that section's own fact, never another section's of the
    same heading; any other fact is found by its kind and subject."""
    if kind == "sequence_match":
        sections = [f for f in ledger.of_kind(kind) if f.source_id == sid]
        if sections:
            key = subject.casefold()
            return next((f for f in sections if f.subject.casefold() == key), None)
    return ledger.find(kind, subject)


def _take(ledger: Ledger, pass_, held, value, sid: str, quote: str) -> None:
    """A pass's different value for a fact. A provisional (added) fact of a kind the pass settles takes the value
    and is settled; a count that changes keeps the old count beside it, so the higher prints. Anything else is kept
    beside the fact as a contradiction."""
    if held.state != ADDED or held.kind not in pass_.settles:     # a settled fact, or a pass that may only add
        ledger.contradict(held.id, value, sid, quote, pass_.name)
        return
    old, new = _number(held.value), _number(value)
    ledger.resolve(held.id, value, sid, quote, pass_.name)          # the pass that owns the kind answers it
    if held.kind in ("count", "device") and old is not None and new is not None and old != new:
        ledger.contradict(held.id, held.value, held.source_id, held.quote, held.stage)   # the higher prints


def apply(pass_, ledger: Ledger, answer: dict, known: frozenset[str]) -> list[str]:
    """Write the pass's answer into the ledger; the refusals, in plain words."""
    refused: list[str] = []

    def known_source(sid: str) -> bool:
        """Only a source the ledger holds (the dossier's, a picture's) or a fact it has: an id that merely appears in
        a document's own words ("per detail [M5]") is in the prompt but is no source."""
        return bool(sid) and ledger.knows(sid)

    answered = [_text(raw.get("subject")) for raw in answer.get("facts") or []      # names this answer adds
                if isinstance(raw, dict) and _text(raw.get("kind")) in ("family", "group")]
    for raw in answer.get("facts") or []:
        if not isinstance(raw, dict):
            continue
        kind, subject = _text(raw.get("kind")), _text(raw.get("subject"))
        value = _value(raw.get("value"), kind)
        sid, quote = plain_id(raw.get("source_id")), _text(raw.get("quote"))
        label = f"{kind} {subject} = {value if value is not None else _text(raw.get('value'))}"
        if kind not in pass_.kinds:
            refused.append(f"the {pass_.name} pass may not write a {kind or 'nameless'} fact ({subject} = {value}); left out")
            continue
        if not known_source(sid):
            refused.append(f"{label} cites [{plain_id(raw.get('source_id')) or _text(raw.get('source_id')) or '?'}], which the documents do not have; left out")
            continue
        if not quote:
            refused.append(f"{label} has no quote; left out")
            continue
        if value is None:
            refused.append(f"{label}: {NOT_A_NUMBER}")
            continue
        if kind == "group" and len(subject.split()) > GROUP_WORDS:
            refused.append(f"{label}: a group is one plant with a short name, never a riser, a shaft or a drain "
                           "route; left out")
            continue
        if kind == "sequence_match" and value != "" and not _names_a_system(str(value), _match_values(ledger) + answered):
            refused.append(f"{label} names no system the ledger holds; left out")
            continue
        try:
            if _many_valued(kind, subject):              # notes, front-end lines and notes, locations: one fact per value
                same = ledger.find_value(kind, subject, value)
                if same is None:
                    ledger.add(kind, subject, value, sid, quote, pass_.name, SETTLED if kind in pass_.settles else ADDED)
                elif kind in pass_.settles:
                    ledger.settle(same.id)
                continue
            held = _held(ledger, kind, subject, sid)
            if held is not None and held.state != ADDED and str(held.value) != str(value):
                ledger.contradict(held.id, value, sid, quote, pass_.name)
                continue
            if held is not None and str(held.value) == str(value):
                if kind in pass_.settles:
                    ledger.settle(held.id)
                continue
            if held is not None and held.state == ADDED:
                _take(ledger, pass_, held, value, sid, quote)
                continue
            state = SETTLED if kind in pass_.settles else ADDED
            ledger.add(kind, subject, value, sid, quote, pass_.name, state)
        except ValueError as problem:         # a bad answer is refused, never a crash
            refused.append(f"{label}: {problem}; left out")

    for raw in answer.get("contradictions") or []:
        if not isinstance(raw, dict):
            continue
        fid = plain_id(raw.get("fact_id")) or _text(raw.get("fact_id"))
        sid, quote = plain_id(raw.get("source_id")), _text(raw.get("quote"))
        if fid not in ledger.facts:
            refused.append(f"a contradiction names {fid or '?'}, which the ledger does not have; left out")
            continue
        if not known_source(sid):
            refused.append(f"the contradiction of {fid} cites [{plain_id(raw.get('source_id')) or _text(raw.get('source_id')) or '?'}], which the documents do not have; left out")
            continue
        if not quote:
            refused.append(f"the contradiction of {fid} has no quote; left out")
            continue
        held = ledger.facts[fid]
        value = _value(raw.get("value"), held.kind)
        if value is None:
            refused.append(f"the contradiction of {fid} ({_text(raw.get('value'))}): {NOT_A_NUMBER}")
            continue
        try:
            _take(ledger, pass_, held, value, sid, quote)
        except ValueError as problem:
            refused.append(f"the contradiction of {fid}: {problem}; left out")

    for raw in answer.get("confirmations") or []:
        fid = plain_id(raw) or _text(raw)
        if fid not in ledger.facts:
            refused.append(f"a confirmation names {fid or '?'}, which the ledger does not have; left out")
            continue
        ledger.settle(fid)

    ledger.understanding[pass_.name] = _text(answer.get("understanding"))
    return refused
