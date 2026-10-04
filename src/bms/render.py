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

from estimator.ledger.facts import where_short
from estimator.scope import Alternate, Block, Item, Run
from estimator.scope import FrontEnd as ScopeFrontEnd
from estimator.scope import Header as ScopeHeader
from estimator.scope import Job as ScopeJob
from estimator.writing.write import tag_list

from bms.model import CLARIFICATION_KINDS, Clarification, Count, Device, FrontEnd, Job, System
from bms.playbook import Playbook, Shape

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
      as a `note` Item; a Count with `others` gets the others note.
    - `job.header` must be set (the run sets it): it becomes `scope.header` (`date` parsed from ISO).
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
    for system in job.systems:
        printed: list[RenderedLine] = []
        blocks = _system_blocks(system, playbook, printed)
        if system.alternate == "add":
            adds.append(Alternate(blocks=blocks))
        elif system.alternate == "deduct":
            deducts.append(Alternate(blocks=blocks))
        else:
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


def _printed(count: Count) -> int | None:
    """The count that prints: the highest any source gives (never undershoot), None when none is known."""
    return count.highest()


def _owner(device: Device, playbook: Playbook) -> str:
    return "" if device.furnished_by == "AME" else playbook.wording.owner_brackets.get(device.furnished_by, "")


def _reason(assumption) -> str:
    what, why = _trim(assumption.what), _squash(assumption.why)
    if not what or not why:
        raise RenderError(f"an assumption needs both what and why (got what={assumption.what!r}, "
                          f"why={assumption.why!r})")
    lead = "" if why.lower().startswith(_REASON_LEADS) else "because "
    return f"{what}, {lead}{why}"


# ---- counts ----------------------------------------------------------------------------------------------------

def _header_count(count: Count, playbook: Playbook) -> str:
    n = _printed(count)
    words = playbook.wording.header
    return words["unknown_count"] if n is None else words["count"].format(n=n)


def _count_note(count: Count, playbook: Playbook) -> str:
    """The text naming every other count in the documents beside the printed one ("" when there is none)."""
    n = _printed(count)
    if n is None:
        return ""
    entries = [(count.value, count.sources[0].where if count.sources else "")] if count.value is not None else []
    entries += [(o.value, o.ref.where) for o in count.others]
    place = next((where_short(w) for v, w in entries if v == n and w), "")
    others = "; ".join(f"{v} per {where_short(w)}" if w else f"{v}" for v, w in entries if v != n)
    if not others:
        return ""
    return _fill(playbook.wording.quantity["others_note"], value=str(n), others=others, place=place)


# ---- one line --------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class _Printed:
    text: str
    depth: int
    device: Device
    verb: str | None
    quantity: int | None       # the device's quantity (None when unknown)
    priced: bool               # the price sheet prices it (AME furnishes, installs or wires it; not an interlock)


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
    what = system.name if system is not None and system.control == "integration" else ""
    quantity_words = playbook.wording.quantity
    out: list[_Printed] = []
    for i in ranked:
        device = devices[i]
        slot_kind = shape.slot_kinds.get(device.slot) if shape is not None else None
        number = _printed(device.quantity)
        owner = _owner(device, playbook)
        form = _slot_form(shape, device.slot)
        qty = ""
        if "{qty}" in form:
            if number is None:
                qty = quantity_words["unknown"]
            elif number not in reference:
                qty = quantity_words["line"].format(n=number)
        text = _fill(form, verb=device.verb, device=device.name, owner=owner, qty=qty, what=what)
        verb = device.verb if "{verb}" in form else None
        acts = "AME" in (device.furnished_by, device.installed_by, device.wired_by)
        out.append(_Printed(text, len(key(i)), device, verb, number, acts and slot_kind != "interlock"))
    return out


# ---- the "*" clarifications --------------------------------------------------------------------------------------

def _notes(clarifications: tuple[Clarification, ...], devices, counts: list[Count],
           playbook: Playbook) -> list[str]:
    """One "*" line per kind, after the lines: confirm, assumed (every assumption with its why), per drawings, and
    the note line (the notes, then the count notes naming every other count)."""
    texts: dict[str, list[str]] = {kind: [] for kind in CLARIFICATION_KINDS}
    for c in clarifications:
        if _trim(c.text):
            texts[c.kind].append(_trim(c.text))
    for device in devices:
        if device.assumption is not None:
            texts["assumed"].append(_reason(device.assumption))
    for count in counts:
        note = _count_note(count, playbook)
        if note:
            texts["note"].append(_trim(note))
    out = []
    for kind in _AFTER_LINES:
        unique = list(dict.fromkeys(texts[kind]))
        if unique:
            out.append(_fill(playbook.wording.clarifications[kind], text="; ".join(unique)))
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
    joiner = playbook.wording.header["tags_joiner"]
    shown = joiner.join(part.strip() for part in tag_list(list(tags)).split(", ")) if tags else ""
    return _fill(form, n=_header_count(count, playbook), name=name, tags=shown)


def _system_blocks(system: System, playbook: Playbook, out: list[RenderedLine]) -> tuple[Block, ...]:
    """One block, or one header per family stacked over the shared lines (the lines sit under the last header,
    the tech hours on the first)."""
    shape = _shape_of(system, playbook)
    form = shape.header if shape is not None else GENERIC_HEADER
    families = system.families
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
                   [f.count for f in families] + [d.quantity for d in system.devices], playbook)
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
