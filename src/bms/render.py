"""The renderer (workstream 4, design §4.4): the Job model to the house wording, as the inputs the OLD app's
writers take:

- `estimator.proposal.write.write_proposal(job: estimator.scope.Job, template_path: Path, out_path: Path) -> Path`
- `estimator.price_sheet.write.write_price_sheet(job: estimator.scope.Job, template_path: Path,
  book: estimator.price_sheet.price_book.PriceBook, out_path: Path) -> Path`
  (and `estimator.price_sheet.write.check_fit(job: estimator.scope.Job)` before writing).

Both take one `estimator.scope.Job` (pydantic, frozen): `header: Header`, `front_end: FrontEnd`,
`blocks: tuple[Block]` (`header: str`, `items: tuple[Item]`, `tech_hours`, `joined`, `numbered`), `add_alternates` /
`deduct_alternates: tuple[Alternate]`, `named_exceptions: tuple[str]`; an `Item` is `kind` ("line" | "note"),
`depth` 1-5, `runs: tuple[Run(text, bold)]`, `quantity` (priced when set), `tech_hours`.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field, replace

from estimator.price_sheet.write import PriceSheetError, check_fit
from estimator.scope import Alternate, Block, Item, Run
from estimator.scope import FrontEnd as ScopeFrontEnd
from estimator.scope import Header as ScopeHeader
from estimator.scope import Job as ScopeJob
from estimator.reading.inventory import COUNT_CAUSE_WORDS, COUNT_CAUSES_LEAD
from estimator.writing.write import tag_list

from bms.citations import SHEET, SourceIds, clarification_text, squash as _squash, strip_label
from bms.model import CLARIFICATION_KINDS, Clarification, Count, Device, FrontEnd, Job, ScopeException, System
from bms.playbook import DEFAULT_ORDER, Playbook, Shape

SEQUENCE_ONLY_ORDER = 20            # a block whose count prints "Qty (##)": after the equipment (shapes.json "order")
GENERIC_FORM = "{verb} {device}{owner}{qty}"       # a system or a slot with no shape
GENERIC_HEADER = "Qty ({n}) {name} {tags}"         # a system with no shape (wording.json "header.generic" when set)
ALTERNATE_LABEL = "ALT #{k}: {name}"               # an alternate's label (wording.json "alternate_label" when set)
_AFTER_LINES = ("confirm", "assumed", "per_drawings", "note")      # the order of the "*" lines
# an assumption's reason: the words put before it, and the lead words a reason may already carry (then none is put)
# (wording.json "assumption.because" / "assumption.leads" when set)
BECAUSE = "because "
_REASON_LEADS = ("as ", "since ", "given that ", "because ")

assert set(_AFTER_LINES) == set(CLARIFICATION_KINDS)


class RenderError(ValueError):
    """A Job that cannot be printed (no header, a shape the Playbook lacks, an assumption without its reason, a line
    left blank, a negative quantity or tech hours, more price sheets than the template holds)."""


# characters a Word or Excel file cannot hold (XML 1.0): control characters other than tab, line feed and return,
# lone surrogates, U+FFFE and U+FFFF
_NOT_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff￾￿]")


def _xml_safe(value):
    """The last of the client-text safety net: every string in a scope dump (or one text) with the characters a
    Word or Excel file cannot hold taken out, so a stray control character prints without it, never a crash."""
    if isinstance(value, str):
        return _NOT_XML.sub("", value)
    if isinstance(value, dict):
        return {k: _xml_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(_xml_safe(v) for v in value)
    return value


@dataclass(frozen=True)
class RenderedLine:
    """One printed line, traced back to the model (for the measurement tool and the review page)."""
    system_key: str            # "" for the front end
    device_id: str | None      # None for a header, a clarification or an integration-trio line with no device
    kind: str                  # "header" | "line" | "note"
    text: str                  # exactly as printed
    verb: str | None           # the device's verb, None when not a device line
    quantity: int | None       # the printed quantity, None when unknown or not a quantity line


@dataclass(frozen=True)
class ProposalDraft:
    """What `render` gives: `scope` is what `write_proposal` and `write_price_sheet` take, as is; `lines` is every
    printed line in print order, traced to its system and device."""
    scope: ScopeJob
    lines: tuple[RenderedLine, ...]


def render(job: Job, playbook: Playbook) -> ProposalDraft:
    """The Job in the house wording.

    Contract:
    - Pure: the same Job and Playbook give the same draft. All wording comes from `playbook.wording` and the
      system's shape (`playbook.shapes[system.shape]`): header form, line order (devices sorted by the slot's
      position in `line_order`, then their order in `System.devices`), the slot's wording form; owner brackets
      from `wording.owner_brackets[device.furnished_by]` (none for AME); "Qty (##)" forms when `Count.value` is
      None; a sub-line slot's device one level in under its parent's line; the block's one "*" clarification in its kind's form,
      as a `note` Item (the label its text already carries is not printed twice, the text is never cut or
      rewritten; an issued source id left in a stale text is taken out, token only, as in every client text); the block's Counts with `others` get one quantity note (`others_note`) naming the
      other counts by sheet number, never a file name.
    - A damper family linked under a fan (a system with other, non-damper families) prints no header of its own;
      each other family prints its own header, its count as `Count.printed` gives it (the schedule's, else the
      highest the documents give).
    - A system with no devices prints no block: it is one `note` line in `lines` ("left out, no lines written",
      with the writer's reason) for the Evidence Package, and, when it has equipment the documents list (tags or a
      schedule count), a named exception in the Playbook's form (`scope_exceptions`, rules.md "Named exceptions").
    - `job.header` must be set (the run sets it): it becomes `scope.header` (`date` parsed from ISO).
    - Blocks print in the Playbook's block order (`block_order`: the shape's `order`, Global Points first; a block
      whose count prints "Qty (##)" after the equipment blocks), the plan's own order kept within one order number.
    - Base systems become `scope.blocks`; `alternate` "add" / "deduct" systems go into `scope.add_alternates` /
      `scope.deduct_alternates`, each labelled "ALT #k: <name>" (adds and deducts numbered apart);
      `job.exceptions` become `scope.named_exceptions`; `job.front_end` the FrontEnd.
    - A system with no shape is rendered in the generic form "{verb} {device}{owner}{qty}" in device order.
    - Never adds a line that is not a field of the Job (nothing internal reaches the client document).
    """
    if job.header is None:
        raise RenderError("the job has no header (quote number, reference, engineer, date)")
    h = job.header
    try:
        header = ScopeHeader(to=h.to, date=dt.date.fromisoformat(h.date), quote_number=h.quote_number,
                             reference=h.reference, mep_engineer=h.mep_engineer, based_on=tuple(h.based_on))
    except ValueError as error:
        raise RenderError(f"the job header cannot be printed: {error}") from error
    lines: list[RenderedLine] = []
    ids = SourceIds.of_job(job)
    front = _front_end(job.front_end, playbook, lines, ids)
    base: list[Block] = []
    alternates: dict[str, list[tuple[Block, ...]]] = {"add": [], "deduct": []}
    after: dict[str, list[RenderedLine]] = {"add": [], "deduct": []}      # print order: base, add alternates, deducts
    for system in sorted(job.systems, key=lambda s: block_order(s, playbook)):      # stable: the plan's order kept
        printed: list[RenderedLine] = []
        blocks = _system_blocks(system, playbook, printed, ids)
        if system.alternate in alternates and blocks:
            alternates[system.alternate].append(blocks)
        elif system.alternate == "base":
            base.extend(blocks)
        (lines if system.alternate == "base" else after[system.alternate]).extend(printed)
    lines += after["add"] + after["deduct"]
    adds, deducts = (_alternates(alternates[side], playbook) for side in ("add", "deduct"))
    exceptions = []
    for x in scope_exceptions(job):
        if not x.text.strip():
            continue
        text = ids.without_issued(x.text).strip()
        if not text:
            # nothing but issued ids: left out (the validator's must_fix on the whole job names it), never a crash
            continue
        exceptions.append(text)
    exceptions = tuple(exceptions)
    try:
        scope = ScopeJob(header=header, front_end=front, blocks=tuple(base), add_alternates=tuple(adds),
                         deduct_alternates=tuple(deducts), named_exceptions=exceptions)
        scope = ScopeJob.model_validate(_xml_safe(scope.model_dump()))
    except ValueError as error:          # pydantic's ValidationError is a ValueError
        raise RenderError(f"the job cannot be printed: {error}") from error
    try:
        check_fit(scope)                 # the price sheet's room, checked here so the run stops before writing
    except PriceSheetError as error:
        raise RenderError(str(error)) from error
    lines = [replace(line, text=_xml_safe(line.text)) for line in lines]
    return ProposalDraft(scope=scope, lines=tuple(lines))


def _alternates(found: list[tuple[Block, ...]], playbook: Playbook) -> list[Alternate]:
    """One side's alternates in print order, numbered from 1 ("ALT #1: Duct Heaters DH-1, 2"): the name is the first
    header with its "Qty (...)" taken off, as the old app labelled them; adds and deducts are numbered apart."""
    form = playbook.wording.alternate_label or ALTERNATE_LABEL
    return [Alternate(label=_fill(form, k=str(k), name=re.sub(r"^\s*Qty\s*\([^)]*\)\s*", "", blocks[0].header)),
                      blocks=blocks) for k, blocks in enumerate(found, start=1)]


# ---- text helpers ----------------------------------------------------------------------------------------------

class _Blank(dict):
    def __missing__(self, key):
        return ""


def _fill(form: str, **values: str) -> str:
    """The form with its {placeholders} filled; a placeholder the caller has no value for prints as nothing."""
    return _squash(form.format_map(_Blank(values)))


def _trim(text: str) -> str:
    return _squash(text).rstrip(" .;")


# the house casing of names; wording.json "casing" (acronyms, small_words, not_plural, acronym_before) replaces a list
# it sets, the others stay as here
ACRONYMS = {a.lower(): a for a in ("BMS", "VFD", "DDC", "ERV", "RTU", "HPAC", "SCR", "UUKL", "BACnet")}
# NO, IT, CO and FA are also ordinary words ("no", "it", "co-located"): an upper-case word is kept as written, and a
# lower-case (or capitalised) "co" / "it" / "fa" becomes CO / IT / FA only before the words that name its thing
_ACRONYM_BEFORE = {"co": ("CO", {"sensor", "sensors", "detector", "detectors", "detection", "monitor", "monitoring"}),
                   "it": ("IT", {"room", "rooms", "closet", "closets", "rack", "racks"}),
                   "fa": ("FA", {"relay", "relays", "panel", "panels", "interface", "shutdown", "alarm", "alarms",
                                 "system", "interlock", "interlocks"})}
_NEXT_WORDS = re.compile(r"[A-Za-z]+")
_LIST_BASE = {"and", "or", "no"}     # with the _ACRONYM_BEFORE words: passed over to the thing a short list names
_LIST_WORDS = _LIST_BASE | set(_ACRONYM_BEFORE)       # ("co and no sensors")
_SMALL_WORDS = {"a", "an", "and", "as", "at", "b", "between", "but", "by", "for", "from", "in", "into", "it", "nor",
                "of", "on", "or", "per", "the", "thru", "to", "vs", "w", "with", "within"}
_NOT_PLURAL = {"points", "series", "status", "controls", "stairs", "chassis"}


@dataclass(frozen=True)
class _Casing:
    """The casing lists one render uses: the Playbook's where it sets them, else the renderer's own."""
    acronyms: dict
    before: dict
    listed: frozenset
    small: frozenset
    not_plural: frozenset


_HOUSE_CASING = _Casing(ACRONYMS, _ACRONYM_BEFORE, frozenset(_LIST_WORDS), frozenset(_SMALL_WORDS),
                        frozenset(_NOT_PLURAL))


def _casing(playbook: Playbook) -> _Casing:
    words = playbook.wording.casing
    if not words:
        return _HOUSE_CASING
    acronyms = {a.lower(): a for a in words["acronyms"]} if "acronyms" in words else ACRONYMS
    before = ({w: (w.upper(), set(f)) for w, f in words["acronym_before"].items()} if "acronym_before" in words
              else _ACRONYM_BEFORE)
    return _Casing(acronyms, before, frozenset(_LIST_BASE | set(before)),
                   frozenset(words.get("small_words", _SMALL_WORDS)), frozenset(words.get("not_plural", _NOT_PLURAL)))


def _title(text: str, casing: _Casing = _HOUSE_CASING) -> str:
    """A name as house lines read: each lower-case word capitalised (small joining words after the first, and the
    part after a hyphen, left alone), the house acronyms in their own spelling (BMS, VFD, BACnet ...); a word already
    capitalised is kept. An acronym that is also a word prints as the source writes it, except "co" / "it" / "fa"
    before the thing they name ("co sensor" -> "CO Sensor", "it room" -> "IT Room", "fa relay" -> "FA Relay", "co2" ->
    "CO2"); "no" never."""
    text = text or ""

    def word(match: re.Match) -> str:
        w = match.group(0)
        canon = casing.acronyms.get(w.lower())
        if canon:
            return canon
        after_hyphen = match.start() > 0 and text[match.start() - 1] == "-"
        context = casing.before.get(w.lower())
        if context and not w.isupper() and not after_hyphen:
            following = next((n.lower() for n in _NEXT_WORDS.findall(text, match.end())
                              if n.lower() not in casing.listed), "")
            if following in context[1] or (w.lower() == "co" and text[match.end():match.end() + 1] == "2"):
                return context[0]
        if w.islower() and not after_hyphen and (match.start() == 0 or w not in casing.small):
            return w[0].upper() + w[1:]
        return w
    return re.sub(r"[A-Za-z]+(?:'[a-z]+)?", word, text)


def _singular_word(word: str, not_plural=_NOT_PLURAL) -> str:
    lower = word.lower()
    if lower in not_plural or lower.endswith(("ss", "us", "is", "as")) or not lower.endswith("s") or len(word) < 3:
        return word
    if lower.endswith("ies") and len(word) > 4:
        return word[:-3] + ("Y" if word[-3].isupper() else "y")
    if lower.endswith(("ches", "shes", "xes", "zes")):
        return word[:-2]
    return word[:-1]


def _singular(text: str, not_plural=_NOT_PLURAL) -> str:
    """The text with its last word singular ("Exhaust Fans" -> "Exhaust Fan"); punctuation after it kept; a word in
    `not_plural` ("Points") is kept."""
    found = re.search(r"([A-Za-z]+)([^A-Za-z]*)$", text)
    if not found:
        return text
    return text[:found.start(1)] + _singular_word(found.group(1), not_plural) + found.group(2)


def _printed(count: Count) -> int | None:
    """The count that prints (`Count.printed`, the estimator's count ruling): the schedule's when a schedule gives
    it, else the highest any source gives; None when none is known."""
    return count.printed()


def _owner(device: Device, playbook: Playbook) -> str:
    return "" if device.furnished_by == "AME" else playbook.wording.owner_brackets.get(device.furnished_by, "")


def _reason(assumption, ids: SourceIds, playbook: Playbook) -> str:
    """"<what>, because <why>": the label off first, then the safety net (`SourceIds.without_issued`). Both are
    checked once cleaned: a what that is only its label, or a why that is only issued ids, is no assumption. The
    words before the why are the Playbook's `assumption.because` (else BECAUSE); a why that already starts with one
    of `assumption.leads` (else _REASON_LEADS) or with those words gets none."""
    what = _trim(strip_label("assumed", ids.without_issued(strip_label("assumed", assumption.what))))
    why = _trim(ids.without_issued(assumption.why))
    if not what or not why:
        raise RenderError(f"an assumption needs both what and why (got what={assumption.what!r}, "
                          f"why={assumption.why!r})")
    words = playbook.wording.assumption
    because = words.get("because", BECAUSE)
    leads = tuple(lead.lower() for lead in (*words.get("leads", _REASON_LEADS), because))
    lead = "" if why.lower().startswith(leads) else because
    return f"{what}, {lead}{why}"


# ---- places (a count note's, built by code) and the source-id safety net (bms.citations decides both) ----------

UNLABELLED = "elsewhere in the documents"       # a count with no place (wording.json quantity.unlabelled, optional)
# the count note's joiners: "(N) per <label>; M and K per <label>" (wording.json quantity.per / and / joiner, optional)
COUNT_PER, COUNT_AND, COUNT_JOINER = " per ", " and ", "; "
# what a count's quote counted, in the note's words (wording.json quantity.labels replaces a label it sets)
COUNT_LABELS = {"plan_placements": "plan placements", "schedule_rows": "schedule rows", "schedule": "the schedule",
                "riser": "the riser", "sheet_pictures": "the sheet pictures"}
# what a count's quote says it counted: (pattern on the quote, lower case; its number when it gives one, the label's
# key in COUNT_LABELS)
_COUNT_LABELS = (
    (re.compile(r"plan placements\s*(\d+)?"), "plan_placements"),
    (re.compile(r"schedule rows\s*(\d+)?"), "schedule_rows"),
    (re.compile(r"quantity column total\s*(\d+)?"), "schedule"),
    (re.compile(r"\briser\b\s*(\d+)?"), "riser"),
    (re.compile(r"sheet pictures?|\bpicture\b()"), "sheet_pictures"),
    (re.compile(r"\bschedule\b(?!\s+rows)()"), "schedule"),
)


def _named(devices, ids: SourceIds) -> list[Device]:
    """The devices with an issued id left in a stale name taken out, token only (`SourceIds.without_issued`, the
    safety net every client text goes through; the validator reports it as must_fix before render). A name that is
    nothing but such tokens (a device named "S4") is a name, not a citation: it prints as written."""
    out = []
    for device in devices:
        name = ids.without_issued(device.name)
        if not name.strip():
            name = device.name
        out.append(device if name == device.name else replace(device, name=name))
    return out


# ---- counts ----------------------------------------------------------------------------------------------------

def _header_count(count: Count, playbook: Playbook) -> str:
    n = _printed(count)
    words = playbook.wording.header
    return words["unknown_count"] if n is None else words["count"].format(n=n)


def _count_label(value: int, ref, ids: SourceIds, labels: dict = COUNT_LABELS) -> str:
    """Where a count is, as a person says it: the sheet number its ref names ("M-100.00"); else what its quote
    counted ("plan placements", "schedule rows", "the schedule", "the riser", "the sheet pictures": `labels`), the
    part of a counts line that gives this value; else a schedule or section name; else "" (the clause is left out).
    A source id is never a place (`SourceIds.place`)."""
    sheet = ids.sheet(ref.where)
    if sheet:
        return sheet
    quote = (ref.quote or "").lower()
    found = []
    for pattern, key in _COUNT_LABELS:
        match = pattern.search(quote)
        if match:
            number = match.group(1) if match.lastindex else None
            found.append((labels[key], int(number) if number else None))
    exact = [label for label, number in found if number == value]
    if exact:
        return exact[0]
    labels = list(dict.fromkeys(label for label, _ in found))
    if len(labels) == 1 and all(number is None for _, number in found):
        return labels[0]
    if found:
        return ""
    return ids.place(ref.where)


PLACEMENTS_LABEL = COUNT_LABELS["plan_placements"]


@dataclass(frozen=True)
class _CountWords:
    """The count note's words one render uses: the Playbook's `quantity` keys where it sets them, else the
    renderer's own."""
    unlabelled: str = UNLABELLED
    per: str = COUNT_PER
    both: str = COUNT_AND
    joiner: str = COUNT_JOINER
    labels: dict = field(default_factory=lambda: dict(COUNT_LABELS))


def _count_words(playbook: Playbook) -> _CountWords:
    q = playbook.wording.quantity
    return _CountWords(q.get("unlabelled", UNLABELLED), q.get("per", COUNT_PER), q.get("and", COUNT_AND),
                       q.get("joiner", COUNT_JOINER), {**COUNT_LABELS, **playbook.wording.quantity_labels})


def _count_causes(count: Count, playbook: Playbook) -> str:
    """The likely causes of a high plan count, in the Playbook's client words (`wording.count_causes`), as the
    equipment counts line's head names them in a quote of this count: each cause after COUNT_CAUSES_LEAD. "" when
    no quote names one. Only the cause's kind is read; its tags, sheets and the estimator's hints never print."""
    words = playbook.wording.count_causes
    if not words:
        return ""
    quotes = [r.quote or "" for r in count.sources] + [o.ref.quote or "" for o in count.others]
    named = [q.split(COUNT_CAUSES_LEAD, 1)[1] for q in quotes if COUNT_CAUSES_LEAD in q]
    keys = [key for key, marker in COUNT_CAUSE_WORDS.items() if any(marker in tail for tail in named)]
    if not keys:
        return ""
    return _fill(words["form"], causes=words["joiner"].join(words[key] for key in keys))


def _count_part(count: Count, ids: SourceIds, causes: str = "", words: _CountWords = _CountWords()) -> str:
    """One count's part of the quantity note: "(N) per <label>; M per <label>; K and J per <label>": the printed
    count (`Count.printed`) first, then every other count with its label, highest first, equal values from one label
    folded, none dropped (estimator ruling D6); a count with no label still prints, with the plain `unlabelled`
    words ("15 elsewhere in the documents", never "per the documents"); "" when there is no other count. `causes` (`_count_causes`) prints after
    the "plan placements" label, or after the printed count's sheet when the plan placements give that count too.
    `words` gives the labels and the joiners (" per ", " and ", "; ") and the unlabelled words."""
    n = _printed(count)
    if n is None:
        return ""
    entries = [(count.value, r) for r in count.sources] if count.value is not None else []
    entries += [(o.value, o.ref) for o in count.others]
    labels, placements = words.labels, words.labels["plan_placements"]
    heads = [label for label in (_count_label(v, r, ids, labels) for v, r in entries if v == n) if label]
    head = next((label for label in heads if SHEET.fullmatch(label)), heads[0] if heads else "")
    folded: dict[str, list[int]] = {}            # label ("" for no label) -> its values
    for value, ref in entries:
        if value is None or value == n:
            continue
        values = folded.setdefault(_count_label(value, ref, ids, labels), [])
        if value not in values:
            values.append(value)
    if not folded:
        return ""
    clauses = sorted(folded.items(), key=lambda item: -max(item[1]))

    def shown(label: str) -> str:
        return f"{label} {causes}" if causes and label == placements else label

    def clause(label: str, values: list[int]) -> str:
        numbers = words.both.join(str(v) for v in sorted(values, reverse=True))
        return f"{numbers}{words.per}{shown(label)}" if label else f"{numbers} {words.unlabelled}"

    others = words.joiner.join(clause(label, values) for label, values in clauses)
    first = shown(head)
    if causes and head != placements and placements in heads:
        first = f"{head} {causes}"               # the plan placements give the printed count too: their causes stay
    return f"({n}){words.per}{first}{words.joiner}{others}" if head else f"({n}){words.joiner}{others}"


def _count_note(counts: list[Count], playbook: Playbook, ids: SourceIds, names: list[str] | None = None) -> str:
    """The block's one quantity note naming every other count in the documents ("" when there is none). `names`
    gives, count by count, the family name its part opens with ("" for none: a block with one family, a device).
    It goes through the safety net every other client text goes through (`SourceIds.without_issued`): an issued id
    that reached a place is taken out, token only."""
    words = _count_words(playbook)
    names = list(names or []) + [""] * (len(counts) - len(names or []))
    seen: dict[str, str] = {}                    # a part -> the family name it opens with; a repeat prints once
    for count, name in zip(counts, names):       # (a device often carries its family's count: the family's wins)
        part = _count_part(count, ids, _count_causes(count, playbook), words)
        if part and part not in seen:
            seen[part] = name
    parts = [f"{name} {part}" if name else part for part, name in seen.items()]
    if not parts:
        return ""
    # made of places the where checks gave (`SourceIds.sheet`, `place`), so it is read as a where is: a source sheet
    # a where names stays, as the validator's where check keeps it (FINAL-J)
    return ids.without_issued(_fill(playbook.wording.quantity["others_note"], counts=words.joiner.join(parts)),
                              place=True)


# ---- one line --------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class _Printed:
    text: str
    depth: int
    device: Device
    verb: str | None
    quantity: int | None       # the device's quantity (None when unknown)
    priced: bool               # the price sheet prices it (AME furnishes, installs or wires it; not an interlock)


_PLACEHOLDER = re.compile(r"\{[a-z_]+\}")


def _plain(text: str) -> str:
    return _squash(text or "").rstrip(" .").lower()


def _fixed_texts(playbook: Playbook, shape: Shape | None) -> tuple[dict[str, str], dict[str, str]]:
    """The house lines that print as written with no verb: (by their plain words, by their slot). The lines are the
    integration trio's lines with no placeholder and the block's OWN shape's wordings with none ("Map Available Points
    Via Mfr. Provided BMS Interface", the mfr. rep line): another shape's fixed wording is an ordinary name here, so
    a device named like it keeps its verb and owner. The slots are every shape's integration slots whose wording is
    such a line (map_points, rep_assist, vfd_map_points, vfd_rep_assist)."""
    lines: dict[str, str] = {}
    slots: dict[str, str] = {}
    for line in playbook.wording.integration_trio:
        if not _PLACEHOLDER.search(line):
            lines.setdefault(_plain(line), line)
    for one in playbook.shapes.values():
        for slot, wording in one.wording.items():
            if _PLACEHOLDER.search(wording):
                continue
            if shape is not None and one.name == shape.name:
                lines.setdefault(_plain(wording), wording)
            if one.slot_kinds.get(slot) == "integration":
                slots.setdefault(slot, wording)
    return lines, slots


def _slot_form(shape: Shape | None, slot: str) -> str:
    if shape is not None and slot in shape.wording:
        return shape.wording[slot]
    return GENERIC_FORM


def line_form(device: Device, shape: Shape | None, playbook: Playbook) -> str:
    """The wording a device's line prints with: its slot's wording in the shape (else the generic form), a fixed
    integration slot's house line in a block whose shape lacks it, or a house line printed as written."""
    house_lines, house_slots = _fixed_texts(playbook, shape)
    form = _slot_form(shape, device.slot)
    if form == GENERIC_FORM and device.slot in house_slots:
        form = house_slots[device.slot]          # a fixed integration slot in a block whose shape lacks it
    return house_lines.get(_plain(device.name), form)    # a house line printed as written, never with a verb


def _device_lines(devices, shape: Shape | None, system: System | None, playbook: Playbook,
                  reference: set[int]) -> list[_Printed]:
    """The devices as printed lines: in the shape's line order, then the order given. A device of a sub-line slot
    (the shape's `under`) prints one level in, directly after its parent: the nearest device of the parent slot
    listed before it (else the last one listed), with no verb; with no parent device it prints in its own slot's
    place. A line of the integration trio whose slot the shape sets under no parent (a block with no shape) prints
    at the trio's own depth (wording.json integration_trio.depths: the rep line one level in). Every line prints its
    slot's wording (integration lines too: the comm wiring line names its controls,
    the map and rep lines are house text). A line carries a quantity form only when its slot's wording has {qty}
    and its quantity is unknown or not the block's own count."""
    devices = list(devices)
    order = {slot: i for i, slot in enumerate(shape.line_order)} if shape is not None else {}
    under = shape.under if shape is not None else {}
    keys: dict[int, tuple] = {}

    def parent_index(i: int) -> int | None:
        parent = under.get(devices[i].slot)
        if parent is None:
            return None
        before = [j for j in range(i) if devices[j].slot == parent]
        anywhere = [j for j, d in enumerate(devices) if d.slot == parent and j != i]
        return before[-1] if before else (anywhere[-1] if anywhere else None)

    def key(i: int, seen: frozenset = frozenset()) -> tuple:
        if i in keys:
            return keys[i]
        parent = parent_index(i)
        if parent is None or parent in seen:
            found = ((order.get(devices[i].slot, len(order)), i),)
        else:
            found = key(parent, seen | {i}) + ((i,),)
        keys[i] = found
        return found

    ranked = sorted(range(len(devices)), key=key)
    casing = _casing(playbook)
    what = _title(system.name, casing) if system is not None and system.control == "integration" else ""
    quantity_words = playbook.wording.quantity
    house_lines, _ = _fixed_texts(playbook, shape)
    trio = dict(zip(playbook.wording.integration_trio, playbook.wording.integration_depths))
    out: list[_Printed] = []
    for i in ranked:
        device = devices[i]
        slot_kind = shape.slot_kinds.get(device.slot) if shape is not None else None
        number = _printed(device.quantity)
        owner = _owner(device, playbook)
        form = line_form(device, shape, playbook)
        fixed = house_lines.get(_plain(device.name))     # a house line printed as written (line_form chose it)
        qty = ""
        if "{qty}" in form:
            if number is None:
                qty = quantity_words["unknown"]
            elif number not in reference:
                qty = quantity_words["line"].format(n=number)
        if _PLACEHOLDER.search(form):
            text = _fill(form, verb=device.verb, device=_title(device.name, casing), owner=owner, qty=qty, what=what)
        elif fixed is not None and owner and fixed not in playbook.wording.integration_trio:
            text = _squash(form + owner)             # a shape's house line another party furnishes keeps its bracket
        else:
            text = form
        verb = device.verb if "{verb}" in form else None
        acts = "AME" in (device.furnished_by, device.installed_by, device.wired_by)
        depth = len(key(i))
        if device.slot not in under and form in trio:   # a trio line the shape sets under no parent: the trio's
            depth = trio[form]                          # own depth (the rep line one level in, RND-13)
        out.append(_Printed(text, depth, device, verb, number, acts and slot_kind != "interlock"))
    return out


def printed_texts(system: System, shape: Shape | None, playbook: Playbook, ids: SourceIds) -> list[tuple[str, str]]:
    """Each line a system's devices print, as (device id, text), in print order: the text the proposal prints, an
    issued id taken out of a name as `_system_blocks` does. The front end (a system with no key) counts its lines
    against 1 and names no equipment, as `_front_end` does. The validator's line-length check reads it (VAL-14)."""
    if system.key:
        reference = {n for n in (_printed(f.count) for f in _header_families(system)) if n is not None}
    else:
        reference = {1}
    return [(p.device.id, p.text) for p in _device_lines(_named(system.devices, ids), shape,
                                                          system if system.key else None, playbook, reference)]


# ---- the "*" clarifications --------------------------------------------------------------------------------------

def _notes(clarifications: tuple[Clarification, ...], devices, counts: list[Count],
           playbook: Playbook, ids: SourceIds, names: list[str] | None = None) -> list[str]:
    """One "*" line per kind, after the lines: confirm, assumed (every assumption with its why), per drawings, the
    note line; then the one quantity note naming every other count. A text's own leading label is not printed
    twice, an issued source id left in a stale text never prints (the token alone is taken out: no sentence is
    rewritten), and a text is never cut."""
    texts: dict[str, list[str]] = {kind: [] for kind in CLARIFICATION_KINDS}
    for c in clarifications:
        text = _trim(clarification_text(c.kind, c.text, ids))
        if text:
            texts[c.kind].append(text)
    for device in devices:
        if device.assumption is not None:
            texts["assumed"].append(_reason(device.assumption, ids, playbook))
    out = []
    for kind in _AFTER_LINES:
        unique = list(dict.fromkeys(texts[kind]))
        if unique:
            out.append(_fill(playbook.wording.clarifications[kind], text="; ".join(unique)))
    note = _count_note(counts, playbook, ids, names)
    if note:
        out.append(note)
    return out


# ---- a system --------------------------------------------------------------------------------------------------

def _shape_of(system: System, playbook: Playbook) -> Shape | None:
    if not system.shape:
        return None
    try:
        return playbook.shape(system.shape)
    except KeyError:
        raise RenderError(f"system {system.key}: the shape {system.shape!r} is not in the Playbook") from None


def _header_text(form: str, name: str, tags: tuple[str, ...], count: Count, playbook: Playbook) -> str:
    """The header: the form filled, the name in house casing; for a single unit (one tag, or a count of 1) the
    kind word before the tags reads singular, as house headers do ("Qty (1) Exhaust Fan EF-1")."""
    joiner = playbook.wording.header["tags_joiner"]
    shown = joiner.join(part.strip() for part in tag_list(list(tags)).split(", ")) if tags else ""
    casing = _casing(playbook)
    n, name = _header_count(count, playbook), _title(name, casing)
    if len(tags) != 1 and _printed(count) != 1:
        return _fill(form, n=n, name=name, tags=shown)
    kind, marker, rest = form.partition("{tags}")
    kind_text = _singular(_squash(kind.format_map(_Blank(n=n, name=name))), casing.not_plural)
    return _fill(kind_text.replace("{", "{{").replace("}", "}}") + " " + marker + rest, tags=shown)


# rules.md "Named exceptions": "EXCEPTION TO ANY WORK WITH Qty (n) <tags> - <reason>" (the Master Template's own
# exception lines are in capitals: "EXCEPTION TO AUTO DIALER (...)")
EXCEPTION_FORM = "EXCEPTION TO ANY WORK WITH {equipment} - {reason}"
NO_WORK_REASON = "NO BMS WORK IN THE CONTRACT DOCUMENTS"
_PARTIES = (
    (re.compile(r"\bmechanical\s+contractor\b|\bM\.?C\.?(?![A-Za-z])|\bhvac\s+contractor\b|\bdivision\s+23\b", re.I),
     "MECHANICAL CONTRACTOR"),
    (re.compile(r"\belectrical\s+contractor\b|\bdivision\s+26\b", re.I), "ELECTRICAL CONTRACTOR"),
    (re.compile(r"\bunit\s+(?:mfr|manufacturer)\b|\bmanufacturer\b|\bfactory\b|\boem\b", re.I), "UNIT MFR."),
    (re.compile(r"\bowner\b", re.I), "OWNER"),
    (re.compile(r"\bothers\b", re.I), "OTHERS"),
)
_STAT = re.compile(r"\b(?:(integral|built[\s-]*in|unit[\s-]*mounted|wall[\s-]*mounted|line[\s-]*voltage|low[\s-]*voltage|"
                   r"programmable|factory|remote)\s+)?(?:space\s+|room\s+)?thermostats?\b", re.I)
_SWITCH = re.compile(r"\b(?:manufacturer|mfr\.?|unit)(?:'s)?\s+(?:on\s*/\s*off\s+|disconnect\s+|speed\s+)?switch|"
                     r"\bon\s*/\s*off\s+switch", re.I)
_NOT_IN_CONTRACT = re.compile(r"\bnot\s+in\s+(?:the\s+)?contract\b|\bN\.?I\.?C\.?(?![A-Za-z])", re.I)
_CONTROLS_BY = re.compile(r"\bcontrols?\s+(?:are\s+|is\s+)?(?:furnished\s+|provided\s+)?by\s+(?:the\s+)?(\w[\w\s.]*)", re.I)


def _party(text: str) -> str:
    return next((name for pattern, name in _PARTIES if pattern.search(text)), "")


def exception_reason(system: System) -> str:
    """The reason a block with no lines is excepted, in the estimator's capital words, read from the writer's
    no_scope_reason (and its clarifications): "INTEGRAL THERMOSTAT", "LINE-VOLTAGE THERMOSTAT", "MANUFACTURER ON/OFF
    SWITCH", "WALL MOUNTED THERMOSTAT BY MECHANICAL CONTRACTOR", "NOT IN CONTRACT", "CONTROLS BY OTHERS"; else
    NO_WORK_REASON. Never a sheet number, a source id or a tag."""
    text = " ".join([system.no_scope_reason or "", *(c.text for c in system.clarifications)])
    if _NOT_IN_CONTRACT.search(text):
        return "NOT IN CONTRACT"
    stat = _STAT.search(text)
    if stat:
        kind = re.sub(r"[\s-]+", " ", stat.group(1) or "").strip().upper()
        kind = {"LINE VOLTAGE": "LINE-VOLTAGE", "LOW VOLTAGE": "LOW-VOLTAGE", "BUILT IN": "BUILT-IN",
                "UNIT MOUNTED": "UNIT MOUNTED"}.get(kind, kind)
        words = f"{kind} THERMOSTAT".strip()
        if kind in ("INTEGRAL", "BUILT-IN", "LINE-VOLTAGE"):
            return words
        party = _party(text[stat.end():]) or _party(text)
        return f"{words} BY {party}" if party else words
    if _SWITCH.search(text):
        return "MANUFACTURER ON/OFF SWITCH"
    by = _CONTROLS_BY.search(text)
    if by:
        party = _party(by.group(1))
        if party:
            return f"CONTROLS BY {party}"
    return NO_WORK_REASON


def _excepted_equipment(system: System) -> str:
    """ "Qty (2) EF-14-1, 2": each family's printed count and its tags as a header prints them."""
    parts = []
    for family in system.families:
        n = _printed(family.count)
        shown = tag_list(list(family.tags)) if family.tags else family.name
        parts.append(f"Qty ({n if n is not None else '##'}) {shown}")
    return ", ".join(parts)


def scope_exceptions(job: Job) -> tuple[ScopeException, ...]:
    """The job's named exceptions, then one for each block the documents list equipment for (a family with tags or
    a schedule's count) that ends with no AME line and no exception of its own: "EXCEPTION TO ANY WORK WITH Qty (n)
    <tags> - <reason>" (rules.md "Named exceptions"; `exception_reason`), citing the family counts' sources.
    Idempotent: a block already excepted (by key) gets no second one."""
    out = list(job.exceptions)
    excepted = {x.system_key for x in out if x.system_key}
    for system in job.systems:
        if system.devices or system.key in excepted:
            continue
        listed = [f for f in system.families if f.tags or f.count.basis == "schedule"]
        if not listed or len(listed) != len(system.families):
            continue
        refs = tuple(dict.fromkeys(r for f in system.families for r in f.count.sources))
        text = EXCEPTION_FORM.format(equipment=_excepted_equipment(system), reason=exception_reason(system))
        out.append(ScopeException(system_key=system.key, text=text, refs=refs))
    return tuple(out)


LEFT_OUT = "{name}: left out, no lines written"


def left_out_text(system: System) -> str:
    """The Evidence Package note for a system with no lines (it prints nothing in the proposal), with the writer's
    reason: its no_scope_reason, else what its clarifications say."""
    reason = (_trim(system.no_scope_reason or "")
              or "; ".join(_trim(c.text) for c in system.clarifications if _trim(c.text)))
    return LEFT_OUT.format(name=system.name) + (f" ({reason})" if reason else "")


def _is_damper_family(family) -> bool:
    return "damper" in family.name.lower()


def _header_families(system: System):
    """The families that print a header: a damper family linked under a fan (a block with other, non-damper
    families) prints none, its devices sit under the fan's header; a damper-only block keeps its own."""
    others = tuple(f for f in system.families if not _is_damper_family(f))
    return others if others else system.families


def block_order(system: System, playbook: Playbook) -> int:
    """Where the system's block prints in the scope (lower first; shapes.json "order"): its shape's order (Global
    Points 0, the equipment 10; a system with no shape 10); a block whose count prints "Qty (##)" (a system named only
    in the sequence) after the equipment, at SEQUENCE_ONLY_ORDER."""
    shape = playbook.shapes.get(system.shape) if system.shape else None
    order = shape.order if shape is not None else DEFAULT_ORDER
    families = _header_families(system)
    if order >= DEFAULT_ORDER and all(_printed(f.count) is None for f in families):
        order = max(order, SEQUENCE_ONLY_ORDER)
    return order


def _system_blocks(system: System, playbook: Playbook, out: list[RenderedLine],
                   ids: SourceIds) -> tuple[Block, ...]:
    """One block, or one header per family stacked over the shared lines (the lines sit under the last header,
    the tech hours on the first). A system with no lines prints nothing: it is a note for the Evidence Package."""
    if not system.devices:
        out.append(RenderedLine(system.key, None, "note", left_out_text(system), None, None))
        return ()
    shape = _shape_of(system, playbook)
    form = shape.header if shape is not None else playbook.wording.header.get("generic", GENERIC_HEADER)
    families = _header_families(system)
    if len(families) <= 1:
        family = families[0] if families else None
        headers = [_header_text(form, system.name, family.tags if family else (),
                                family.count if family else Count(value=None), playbook)]
    else:
        headers = [_header_text(form, f.name, f.tags, f.count, playbook) for f in families]
    reference = {n for n in (_printed(f.count) for f in families) if n is not None}
    pending = not families or any(_printed(f.count) is None for f in families)     # "Qty (##)": nothing is priced
    printed = _device_lines(_named(system.devices, ids), shape, system, playbook, reference)
    named = len(system.families) > 1             # more than one family: each family's part names its family
    notes = _notes(system.clarifications, system.devices,
                   [f.count for f in system.families] + [d.quantity for d in system.devices], playbook, ids,
                   [_title(f.name, _casing(playbook)) if named else "" for f in system.families])
    try:                                 # every field checked: a blank line, a negative quantity or tech hours
        items = _items(printed, pending) + [Item(kind="note", runs=(Run(text=n),)) for n in notes]
        last = len(headers) - 1
        blocks = [Block(header=h, joined=i > 0, tech_hours=system.tech_hours if i == 0 else None,
                        items=tuple(items) if i == last else ()) for i, h in enumerate(headers)]
    except ValueError as error:          # pydantic's ValidationError is a ValueError
        raise RenderError(f"system {system.key}: {error}") from error
    out += [RenderedLine(system.key, None, "header", h, None, None) for h in headers]
    out += _traced(system.key, printed, notes)
    return tuple(blocks)


def _items(printed: list[_Printed], pending: bool) -> list[Item]:
    return [Item(kind="line", depth=p.depth, runs=(Run(text=p.text),),
                 quantity=p.quantity if (p.priced and not pending) else None) for p in printed]


def _traced(key: str, printed: list[_Printed], notes: list[str]) -> list[RenderedLine]:
    lines = [RenderedLine(key, p.device.id, "line", p.text, p.verb, p.quantity) for p in printed]
    return lines + [RenderedLine(key, None, "note", n, None, None) for n in notes]


# ---- the front end ---------------------------------------------------------------------------------------------

# rules.md "Front end mode": when the documents do not name the existing BMS, the proposal prints this and the front
# end asks the client to confirm the vendor (CORE-1)
EXISTING_PLACEHOLDER = "[existing BMS name]"
EXISTING_CONFIRM = "the existing BMS vendor, as the documents do not name it"
# a "name" that says the documents give none ("base building controls (vendor not named)", "unknown", "TBD")
_NO_NAME = re.compile(r"\b(?:not\s+(?:named|given|stated|identified|known|specified|provided|listed)|unnamed|unknown"
                      r"|unspecified|unidentified|tbd|tbc|n/a|none|vendor\s+not|no\s+vendor|by\s+others)\b", re.I)
# the words a description of an existing BMS uses when it names no product or vendor
_GENERIC_NAME_WORDS = frozenset(
    "existing base building buildings building's controls control system systems bms bas ems ddc automation "
    "management energy owner owner's owners vendor manufacturer house current present the a an of and to be "
    "confirmed name named tenant landlord central main".split())


def existing_name_given(name: str | None) -> bool:
    """True when `name` names an existing BMS (a vendor or a product, "Honeywell / Niagara N4", "Metasys"); False
    for a blank, the placeholder itself, a text that says no name is given ("vendor not named", "unknown") or one of
    generic words only ("base building controls")."""
    text = (name or "").strip()
    if not text or _NO_NAME.search(text):
        return False
    words = [w for w in re.split(r"[^A-Za-z0-9']+", text.casefold()) if w]
    return any(w not in _GENERIC_NAME_WORDS for w in words)


def existing_system_name(front: FrontEnd | None) -> str | None:
    """The existing BMS name the proposal prints: None for a new system (a stray name is not printed), the
    documents' name when one is given, else EXISTING_PLACEHOLDER (rules.md "Front end mode")."""
    if front is None or front.mode != "extend-existing":
        return None
    name = (front.existing_system_name or "").strip()
    return name if existing_name_given(name) else EXISTING_PLACEHOLDER


def _vendor_asked(clarifications) -> bool:
    return any(c.kind == "confirm" and re.search(r"\bvendor\b|existing\s+(?:bms|system)", c.text, re.I)
               for c in clarifications)


def _front_end(front: FrontEnd | None, playbook: Playbook, out: list[RenderedLine],
               ids: SourceIds) -> ScopeFrontEnd:
    if front is None:
        return ScopeFrontEnd(mode="new-system")
    name = existing_system_name(front)
    clarifications = front.clarifications
    if name == EXISTING_PLACEHOLDER and not _vendor_asked(clarifications):
        clarifications = (*clarifications, Clarification("confirm", EXISTING_CONFIRM))
    printed = _device_lines(_named(front.devices, ids), None, None, playbook, {1})
    notes = _notes(clarifications, front.devices, [d.quantity for d in front.devices], playbook, ids)
    out += _traced("", printed, notes)
    try:
        items = _items(printed, False) + [Item(kind="note", runs=(Run(text=n),)) for n in notes]
        return ScopeFrontEnd(mode=front.mode, existing_system_name=name,
                             items=tuple(items), tech_hours=front.tech_hours)
    except ValueError as error:
        raise RenderError(f"the front end cannot be printed: {error}") from error
