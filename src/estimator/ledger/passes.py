# src/estimator/ledger/passes.py
"""The seven reading passes (design 2026-09-29 §2): each reads its own documents from the dossier, sees the ledger
so far and the earlier passes' understanding, and answers with facts, contradictions, confirmations and its own
understanding. `apply` turns an answer into ledger changes and refuses, in plain words, whatever cannot be
trusted: a kind the pass may not write, a source the documents do not have, a fact with no quote. A different
value for a settled fact is never a change: it is a contradiction beside the fact. A provisional (added) fact of a
kind this pass settles takes the pass's value and is settled; a count that changes keeps the old count beside it,
so the higher still prints."""
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
    not_sheet_types: tuple[str, ...] = ()   # sheets of these types are another pass's, even when typed for this one

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
         "unit. Write nothing about equipment the ledger does not hold.",
         not_sheet_types=("Air riser", "Water riser", "Network riser")),
    Pass("risers", "Air and water risers", ("link", "group", "device"), ("family", "unit", "count"), (), ("Air riser", "Water riser"), False,
         "Settle how the systems fit together: which unit serves which (a link: subject the served unit, value the "
         "serving unit), the plant loop (a group: subject the plant's name, value the families in it, comma "
         "separated), and the sensors on the risers (pressure, differential pressure, stair pressurisation). "
         "Equipment on a riser that neither the schedule nor the plans showed may only be added, quoting the riser."),
    Pass("network", "Network riser", ("provider", "link"), (), (), ("Network riser",), False,
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
        wanted, others = set(pass_.sheet_types), set(pass_.not_sheet_types)
        lines = [line for _sid, number, line in sheet_text_lines(dossier.text)
                 if number and wanted & set(types.get(number, ())) and not others & set(types.get(number, ()))]
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
            refused.append(f"{label} cites [{plain_id(raw.get('source_id')) or _text(raw.get('source_id')) or '?'}], which the documents do not have; left out")
            continue
        if not quote:
            refused.append(f"{label} has no quote; left out")
            continue
        if _many_valued(kind, subject):              # notes, front-end lines and notes, locations: one fact per value
            same = ledger.find_value(kind, subject, value)
            if same is None:
                ledger.add(kind, subject, value, sid, quote, pass_.name, SETTLED if kind in pass_.settles else ADDED)
            elif kind in pass_.settles:
                ledger.settle(same.id)
            continue
        held = ledger.find(kind, subject)
        if held is not None and held.state != ADDED and str(held.value) != str(value):
            ledger.contradict(held.id, value, sid, quote, pass_.name)
            continue
        if held is not None and str(held.value) == str(value):
            if kind in pass_.settles:
                ledger.settle(held.id)
            continue
        if held is not None and held.state == ADDED:
            if kind not in pass_.settles:                 # a pass that may only add: kept beside it, the higher prints
                ledger.contradict(held.id, value, sid, quote, pass_.name)
                continue
            old, new = _number(held.value), _number(value)
            ledger.resolve(held.id, value, sid, quote, pass_.name)          # the pass that owns the kind answers it
            if kind in ("count", "device") and old is not None and new is not None and old != new:
                ledger.contradict(held.id, held.value, held.source_id, held.quote, held.stage)   # the higher prints
            continue
        state = SETTLED if kind in pass_.settles else ADDED
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
            refused.append(f"the contradiction of {fid} cites [{plain_id(raw.get('source_id')) or _text(raw.get('source_id')) or '?'}], which the documents do not have; left out")
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
