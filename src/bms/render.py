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
from dataclasses import dataclass

from estimator.scope import Alternate, Block, Item, Run
from estimator.scope import FrontEnd as ScopeFrontEnd
from estimator.scope import Header as ScopeHeader
from estimator.scope import Job as ScopeJob
from estimator.writing.write import tag_list

from bms.model import CLARIFICATION_KINDS, Clarification, Count, Device, FrontEnd, Job, System
from bms.playbook import DEFAULT_ORDER, Playbook, Shape

SEQUENCE_ONLY_ORDER = 20            # a block whose count prints "Qty (##)": after the equipment (shapes.json "order")
GENERIC_FORM = "{verb} {device}{owner}{qty}"       # a system or a slot with no shape
GENERIC_HEADER = "Qty ({n}) {name} {tags}"         # a system with no shape
_AFTER_LINES = ("confirm", "assumed", "per_drawings", "note")      # the order of the "*" lines
_REASON_LEADS = ("as ", "since ", "given that ", "because ")       # a reason that already carries its own lead word

assert set(_AFTER_LINES) == set(CLARIFICATION_KINDS)


class RenderError(ValueError):
    """A Job that cannot be printed (no header, a shape the Playbook lacks, an assumption without its reason)."""


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
      as a `note` Item (the label its text already carries is not printed twice, source ids never print, the
      text is never cut); the block's Counts with `others` get one quantity note (`others_note`) naming the
      other counts by sheet number, never a file name.
    - A damper family linked under a fan (a system with other, non-damper families) prints no header of its own;
      each other family prints its own header, its count the highest the documents give.
    - A system with no devices prints nothing in the proposal: it is one `note` line in `lines` ("left out, no
      lines written", with the writer's reason) for the Evidence Package only.
    - `job.header` must be set (the run sets it): it becomes `scope.header` (`date` parsed from ISO).
    - Blocks print in the Playbook's block order (`block_order`: the shape's `order`, Global Points first; a block
      whose count prints "Qty (##)" after the equipment blocks), the plan's own order kept within one order number.
    - Base systems become `scope.blocks`; `alternate` "add" / "deduct" systems go into `scope.add_alternates` /
      `scope.deduct_alternates`; `job.exceptions` become `scope.named_exceptions`; `job.front_end` the FrontEnd.
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
    front = _front_end(job.front_end, playbook, lines)
    base: list[Block] = []
    adds: list[Alternate] = []
    deducts: list[Alternate] = []
    after: dict[str, list[RenderedLine]] = {"add": [], "deduct": []}      # print order: base, add alternates, deducts
    for system in sorted(job.systems, key=lambda s: block_order(s, playbook)):      # stable: the plan's order kept
        printed: list[RenderedLine] = []
        blocks = _system_blocks(system, playbook, printed)
        if system.alternate == "add" and blocks:
            adds.append(Alternate(blocks=blocks))
        elif system.alternate == "deduct" and blocks:
            deducts.append(Alternate(blocks=blocks))
        elif system.alternate == "base":
            base.extend(blocks)
        (lines if system.alternate == "base" else after[system.alternate]).extend(printed)
    lines += after["add"] + after["deduct"]
    exceptions = tuple(x.text for x in job.exceptions if x.text.strip())
    scope = ScopeJob(header=header, front_end=front, blocks=tuple(base), add_alternates=tuple(adds),
                     deduct_alternates=tuple(deducts), named_exceptions=exceptions)
    return ProposalDraft(scope=scope, lines=tuple(lines))


# ---- text helpers ----------------------------------------------------------------------------------------------

class _Blank(dict):
    def __missing__(self, key):
        return ""


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _fill(form: str, **values: str) -> str:
    """The form with its {placeholders} filled; a placeholder the caller has no value for prints as nothing."""
    return _squash(form.format_map(_Blank(values)))


def _trim(text: str) -> str:
    return _squash(text).rstrip(" .;")


ACRONYMS = {a.lower(): a for a in ("BMS", "VFD", "DDC", "CO", "NO", "ERV", "RTU", "IT", "HPAC", "SCR", "UUKL", "FA",
                                   "BACnet")}
_SMALL_WORDS = {"a", "an", "and", "as", "at", "b", "between", "but", "by", "for", "from", "in", "into", "nor", "of",
                "on", "or", "per", "the", "thru", "to", "vs", "w", "with", "within"}


def _title(text: str) -> str:
    """A name as house lines read: each lower-case word capitalised (small joining words after the first left
    alone), the house acronyms in their own spelling (BMS, VFD, CO, BACnet ...); a word already capitalised is kept."""
    def word(match: re.Match) -> str:
        w = match.group(0)
        canon = ACRONYMS.get(w.lower())
        if canon:
            return canon
        if w.islower() and (match.start() == 0 or w not in _SMALL_WORDS):
            return w[0].upper() + w[1:]
        return w
    return re.sub(r"[A-Za-z]+(?:'[a-z]+)?", word, text or "")


_NOT_PLURAL = {"points", "series", "status", "controls", "stairs", "chassis"}


def _singular_word(word: str) -> str:
    lower = word.lower()
    if lower in _NOT_PLURAL or lower.endswith(("ss", "us", "is", "as")) or not lower.endswith("s") or len(word) < 3:
        return word
    if lower.endswith("ies") and len(word) > 4:
        return word[:-3] + ("Y" if word[-3].isupper() else "y")
    if lower.endswith(("ches", "shes", "xes", "zes")):
        return word[:-2]
    return word[:-1]


def _singular(text: str) -> str:
    """The text with its last word singular ("Exhaust Fans" -> "Exhaust Fan"); punctuation after it kept."""
    found = re.search(r"([A-Za-z]+)([^A-Za-z]*)$", text)
    if not found:
        return text
    return text[:found.start(1)] + _singular_word(found.group(1)) + found.group(2)


def _printed(count: Count) -> int | None:
    """The count that prints: the highest any source gives (never undershoot), None when none is known."""
    return count.highest()


def _owner(device: Device, playbook: Playbook) -> str:
    return "" if device.furnished_by == "AME" else playbook.wording.owner_brackets.get(device.furnished_by, "")


def _reason(assumption, refs: "_Refs") -> str:
    what = _trim(_no_ids(_strip_labels(assumption.what), refs))
    why = _trim(_no_ids(assumption.why, refs))
    if not _trim(assumption.what) or not _squash(assumption.why):
        raise RenderError(f"an assumption needs both what and why (got what={assumption.what!r}, "
                          f"why={assumption.why!r})")
    lead = "" if why.lower().startswith(_REASON_LEADS) else "because "
    return f"{what}, {lead}{why}" if why else what


# ---- places: a sheet number or a section, never a file name --------------------------------------------------

_SHEET = re.compile(r"\b[A-Z]{1,2}-?\d{1,3}(?:\.\d{1,3})?[A-Z]?\b")
_FILE_PART = re.compile(r"\.(?:pdf|docx?|xlsx?|dwg|txt)\b|\bpage\s+\d+\b", re.IGNORECASE)
_NOT_A_DOCUMENT = ("equipment counts",)          # the dossier's own label for a combined count, not a document
MAX_COUNT_CLAUSES = 5                            # the printed count's clause and at most four others
# what a count's quote says it counted: (pattern on the quote, lower case; its number when it gives one, the label)
_COUNT_LABELS = (
    (re.compile(r"plan placements\s*(\d+)?"), "plan placements"),
    (re.compile(r"schedule rows\s*(\d+)?"), "schedule rows"),
    (re.compile(r"quantity column total\s*(\d+)?"), "the schedule"),
    (re.compile(r"\briser\b\s*(\d+)?"), "the riser"),
    (re.compile(r"sheet pictures?|\bpicture\b()"), "the sheet pictures"),
    (re.compile(r"\bschedule\b(?!\s+rows)()"), "the schedule"),
)


def _place(where: str) -> str:
    """Where a source is, as the client reads it: the first sheet number in it ("M-112.00"); else the schedule,
    section or document name with the file name and its page left out; else "" (no place)."""
    text = _squash(re.sub(r"\([^)]*\)", " ", where or ""))
    found = _SHEET.search(text)
    if found:
        return found.group(0)
    if text.lower().startswith(_NOT_A_DOCUMENT):
        return ""
    for part in re.split(r"[,;]", text):
        part = _squash(part)
        if part and not _FILE_PART.search(part):
            return part
    return ""


# ---- source ids: never printed ---------------------------------------------------------------------------------

_ID = r"\bS\d{1,4}\b(?:\s+(?:note|paragraph)\s+\d+)?"
_ID_GROUP = re.compile(rf"{_ID}(?:\s*(?:,|and|to|through|thru|-|–)\s*{_ID})*")
_ONE_ID = re.compile(r"\bS\d{1,4}\b")
_DANGLING = re.compile(r"\s*\b(?:because|per|in|on|by|from|of|and|see|the)\s*(?=[,;:.)]|$)", re.IGNORECASE)


class _Refs:
    """The refs a text's source ids are looked up in: the device's own first, then the rest of its block's."""

    def __init__(self, *groups) -> None:
        self.groups = [tuple(g) for g in groups if g]

    def place(self, source_id: str) -> str:
        for group in self.groups:
            for ref in group:
                if ref.source_id == source_id and _place(ref.where):
                    return _place(ref.where)
        return ""

    def first(self, *refs) -> "_Refs":
        return _Refs(refs, *self.groups)


def _no_ids(text: str, refs: _Refs) -> str:
    """The text with every source id ("S141", "S394 note 1", "S243 to S250") replaced by the sheet or section of
    its ref, or dropped (with the words around it tidied) when no ref names it."""
    if not _ONE_ID.search(text or ""):
        return text

    def swap(match: re.Match) -> str:
        places = list(dict.fromkeys(p for p in (refs.place(i) for i in _ONE_ID.findall(match.group(0))) if p))
        return " and ".join(places)

    out = _ID_GROUP.sub(swap, text)
    out = re.sub(r"\(\s*(?:(?:,|;|and)\s*)*\)", " ", out)          # an emptied bracket
    out = re.sub(r"\(\s+", "(", out)
    out = re.sub(r"\s+([,;:.)])", r"\1", out)
    while True:
        tidy = _DANGLING.sub("", out)
        tidy = re.sub(r"([,;:])\s*(?=[,;:.)]|$)", "", tidy)          # a separator left with nothing after it
        if tidy == out:
            break
        out = tidy
    return _squash(out).lstrip(",;: ")


# ---- the clarification labels -----------------------------------------------------------------------------------

_LABEL = re.compile(r"^\s*(?:\*+|confirm\b\s*:?|assumed\s*:)\s*", re.IGNORECASE)
_PER = re.compile(r"^\s*(?:\*+|quantity\s+per\b|as\s+per\b|per\b)\s*", re.IGNORECASE)
_TRADE = re.compile(r"\b(plumbing|electrical|mechanical|architectural|fire protection|civil|structural)\b",
                    re.IGNORECASE)


def _strip_labels(text: str) -> str:
    """The text without the leading label(s) it already carries ("*", "Confirm", "Assumed:"): the form adds its own."""
    text = text or ""
    while True:
        stripped = _LABEL.sub("", text, count=1)
        if stripped == text:
            return text
        text = stripped


def _per_drawings_text(text: str) -> str:
    """What a per-drawings clarification puts in its form: the trade its text names ("plumbing"), else the text
    without its own "Quantity per" and "drawings"."""
    trade = _TRADE.search(text or "")
    if trade:
        return trade.group(1).lower()
    text = _strip_labels(text)
    while True:
        stripped = _PER.sub("", text, count=1)
        if stripped == text:
            break
        text = stripped
    return re.sub(r"\s*\bdrawings?\b\s*$", "", _trim(text), flags=re.IGNORECASE)


def _clarification_text(kind: str, text: str, refs: _Refs) -> str:
    text = _no_ids(text, refs)
    return _trim(_per_drawings_text(text) if kind == "per_drawings" else _strip_labels(text))


# ---- counts ----------------------------------------------------------------------------------------------------

def _header_count(count: Count, playbook: Playbook) -> str:
    n = _printed(count)
    words = playbook.wording.header
    return words["unknown_count"] if n is None else words["count"].format(n=n)


def _sheet(where: str) -> str:
    text = _squash(re.sub(r"\([^)]*\)", " ", where or ""))
    if text.lower().startswith(_NOT_A_DOCUMENT):
        return ""
    found = _SHEET.search(text)
    return found.group(0) if found else ""


def _count_label(value: int, ref) -> str:
    """Where a count is, as a person says it: the sheet number its ref names ("M-100.00"); else what its quote
    counted ("plan placements", "schedule rows", "the schedule", "the riser", "the sheet pictures"), the part of a
    counts line that gives this value; else a schedule or section name; else "" (the clause is left out)."""
    sheet = _sheet(ref.where)
    if sheet:
        return sheet
    quote = (ref.quote or "").lower()
    found = []
    for pattern, label in _COUNT_LABELS:
        match = pattern.search(quote)
        if match:
            number = match.group(1) if match.lastindex else None
            found.append((label, int(number) if number else None))
    exact = [label for label, number in found if number == value]
    if exact:
        return exact[0]
    labels = list(dict.fromkeys(label for label, _ in found))
    if len(labels) == 1 and all(number is None for _, number in found):
        return labels[0]
    if found:
        return ""
    return _place(ref.where)


def _count_part(count: Count) -> str:
    """One count's part of the quantity note: "(N) per <label>; M per <label>; K and J per <label>": the printed
    (highest) count first, then each other count with its label, highest first, equal values from one label
    folded, at most MAX_COUNT_CLAUSES clauses; a count with no label is left out (never "per the documents");
    "" when no other count has a label."""
    n = _printed(count)
    if n is None:
        return ""
    entries = [(count.value, r) for r in count.sources] if count.value is not None else []
    entries += [(o.value, o.ref) for o in count.others]
    heads = [label for label in (_count_label(v, r) for v, r in entries if v == n) if label]
    head = next((label for label in heads if _SHEET.fullmatch(label)), heads[0] if heads else "")
    folded: dict[str, list[int]] = {}
    for value, ref in entries:
        label = _count_label(value, ref) if value != n else ""
        if label:
            values = folded.setdefault(label, [])
            if value not in values:
                values.append(value)
    if not folded:
        return ""
    clauses = sorted(folded.items(), key=lambda item: -max(item[1]))[:MAX_COUNT_CLAUSES - 1]
    others = "; ".join(f"{' and '.join(str(v) for v in sorted(values, reverse=True))} per {label}"
                       for label, values in clauses)
    return f"({n}) per {head}; {others}" if head else f"({n}); {others}"


def _count_note(counts: list[Count], playbook: Playbook) -> str:
    """The block's one quantity note naming every other count in the documents ("" when there is none)."""
    parts = list(dict.fromkeys(p for p in (_count_part(c) for c in counts) if p))
    if not parts:
        return ""
    return _fill(playbook.wording.quantity["others_note"], counts="; ".join(parts))


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


def _fixed_texts(playbook: Playbook) -> tuple[dict[str, str], dict[str, str]]:
    """The house lines that print as written with no verb: (by their plain words, by their slot). The lines are the
    integration trio's lines with no placeholder and every shape wording with none ("Map Available Points Via Mfr.
    Provided BMS Interface", the mfr. rep line); the slots are the integration slots whose wording is such a line
    (map_points, rep_assist, vfd_map_points, vfd_rep_assist)."""
    lines: dict[str, str] = {}
    slots: dict[str, str] = {}
    for line in playbook.wording.integration_trio:
        if not _PLACEHOLDER.search(line):
            lines.setdefault(_plain(line), line)
    for shape in playbook.shapes.values():
        for slot, wording in shape.wording.items():
            if _PLACEHOLDER.search(wording):
                continue
            lines.setdefault(_plain(wording), wording)
            if shape.slot_kinds.get(slot) == "integration":
                slots.setdefault(slot, wording)
    return lines, slots


def _slot_form(shape: Shape | None, slot: str) -> str:
    if shape is not None and slot in shape.wording:
        return shape.wording[slot]
    return GENERIC_FORM


def _device_lines(devices, shape: Shape | None, system: System | None, playbook: Playbook,
                  reference: set[int]) -> list[_Printed]:
    """The devices as printed lines: in the shape's line order, then the order given. A device of a sub-line slot
    (the shape's `under`) prints one level in, directly after its parent: the nearest device of the parent slot
    listed before it (else the last one listed), with no verb; with no parent device it prints in its own slot's
    place. Every line prints its slot's wording (integration lines too: the comm wiring line names its controls,
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
    what = _title(system.name) if system is not None and system.control == "integration" else ""
    quantity_words = playbook.wording.quantity
    house_lines, house_slots = _fixed_texts(playbook)
    out: list[_Printed] = []
    for i in ranked:
        device = devices[i]
        slot_kind = shape.slot_kinds.get(device.slot) if shape is not None else None
        number = _printed(device.quantity)
        owner = _owner(device, playbook)
        form = _slot_form(shape, device.slot)
        if form == GENERIC_FORM and device.slot in house_slots:
            form = house_slots[device.slot]          # a fixed integration slot in a block whose shape lacks it
        fixed = house_lines.get(_plain(device.name))
        if fixed is not None:
            form = fixed                             # a house line printed as written, never with a verb
        qty = ""
        if "{qty}" in form:
            if number is None:
                qty = quantity_words["unknown"]
            elif number not in reference:
                qty = quantity_words["line"].format(n=number)
        if _PLACEHOLDER.search(form):
            text = _fill(form, verb=device.verb, device=_title(device.name), owner=owner, qty=qty, what=what)
        else:
            text = form
        verb = device.verb if "{verb}" in form else None
        acts = "AME" in (device.furnished_by, device.installed_by, device.wired_by)
        out.append(_Printed(text, len(key(i)), device, verb, number, acts and slot_kind != "interlock"))
    return out


# ---- the "*" clarifications --------------------------------------------------------------------------------------

def _notes(clarifications: tuple[Clarification, ...], devices, counts: list[Count],
           playbook: Playbook, extra_refs=()) -> list[str]:
    """One "*" line per kind, after the lines: confirm, assumed (every assumption with its why), per drawings, the
    note line; then the one quantity note naming every other count. A text's own leading label is not printed
    twice, its source ids never print, and it is never cut."""
    block_refs = tuple(r for d in devices for r in d.refs) + tuple(extra_refs)
    refs = _Refs(block_refs)
    texts: dict[str, list[str]] = {kind: [] for kind in CLARIFICATION_KINDS}
    for c in clarifications:
        text = _clarification_text(c.kind, c.text, refs)
        if text:
            texts[c.kind].append(text)
    for device in devices:
        if device.assumption is not None:
            texts["assumed"].append(_reason(device.assumption, refs.first(*device.refs)))
    out = []
    for kind in _AFTER_LINES:
        unique = list(dict.fromkeys(texts[kind]))
        if unique:
            out.append(_fill(playbook.wording.clarifications[kind], text="; ".join(unique)))
    note = _count_note(counts, playbook)
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
    n, name = _header_count(count, playbook), _title(name)
    if len(tags) != 1 and _printed(count) != 1:
        return _fill(form, n=n, name=name, tags=shown)
    kind, marker, rest = form.partition("{tags}")
    kind_text = _singular(_squash(kind.format_map(_Blank(n=n, name=name))))
    return _fill(kind_text.replace("{", "{{").replace("}", "}}") + " " + marker + rest, tags=shown)


LEFT_OUT = "{name}: left out, no lines written"


def left_out_text(system: System) -> str:
    """The Evidence Package note for a system with no lines (it prints nothing in the proposal), with the writer's
    reason when its clarifications give one."""
    reason = "; ".join(_trim(c.text) for c in system.clarifications if _trim(c.text))
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


def _system_blocks(system: System, playbook: Playbook, out: list[RenderedLine]) -> tuple[Block, ...]:
    """One block, or one header per family stacked over the shared lines (the lines sit under the last header,
    the tech hours on the first). A system with no lines prints nothing: it is a note for the Evidence Package."""
    if not system.devices:
        out.append(RenderedLine(system.key, None, "note", left_out_text(system), None, None))
        return ()
    shape = _shape_of(system, playbook)
    form = shape.header if shape is not None else GENERIC_HEADER
    families = _header_families(system)
    if len(families) <= 1:
        family = families[0] if families else None
        headers = [_header_text(form, system.name, family.tags if family else (),
                                family.count if family else Count(value=None), playbook)]
    else:
        headers = [_header_text(form, f.name, f.tags, f.count, playbook) for f in families]
    reference = {n for n in (_printed(f.count) for f in families) if n is not None}
    pending = not families or any(_printed(f.count) is None for f in families)     # "Qty (##)": nothing is priced
    printed = _device_lines(system.devices, shape, system, playbook, reference)
    items = _items(printed, pending)
    notes = _notes(system.clarifications, system.devices,
                   [f.count for f in system.families] + [d.quantity for d in system.devices], playbook,
                   system.sequence_refs)
    items += [Item(kind="note", runs=(Run(text=n),)) for n in notes]
    out += [RenderedLine(system.key, None, "header", h, None, None) for h in headers]
    out += _traced(system.key, printed, notes)
    blocks = [Block(header=h, joined=i > 0) for i, h in enumerate(headers)]
    blocks[0] = blocks[0].model_copy(update={"tech_hours": system.tech_hours})
    blocks[-1] = blocks[-1].model_copy(update={"items": tuple(items)})
    return tuple(blocks)


def _items(printed: list[_Printed], pending: bool) -> list[Item]:
    return [Item(kind="line", depth=p.depth, runs=(Run(text=p.text),),
                 quantity=p.quantity if (p.priced and not pending) else None) for p in printed]


def _traced(key: str, printed: list[_Printed], notes: list[str]) -> list[RenderedLine]:
    lines = [RenderedLine(key, p.device.id, "line", p.text, p.verb, p.quantity) for p in printed]
    return lines + [RenderedLine(key, None, "note", n, None, None) for n in notes]


# ---- the front end ---------------------------------------------------------------------------------------------

def _front_end(front: FrontEnd | None, playbook: Playbook, out: list[RenderedLine]) -> ScopeFrontEnd:
    if front is None:
        return ScopeFrontEnd(mode="new-system")
    printed = _device_lines(front.devices, None, None, playbook, {1})
    items = _items(printed, False)
    notes = _notes(front.clarifications, front.devices, [d.quantity for d in front.devices], playbook)
    items += [Item(kind="note", runs=(Run(text=n),)) for n in notes]
    out += _traced("", printed, notes)
    try:
        return ScopeFrontEnd(mode=front.mode, existing_system_name=front.existing_system_name,
                             items=tuple(items), tech_hours=front.tech_hours)
    except ValueError as error:
        raise RenderError(f"the front end cannot be printed: {error}") from error
