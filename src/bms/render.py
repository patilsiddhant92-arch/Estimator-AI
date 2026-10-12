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
from collections.abc import Sequence
from dataclasses import dataclass, field, replace

from estimator.price_sheet.write import PriceSheetError, check_fit
from estimator.proposal.write import ame_bms
from estimator.scope import Alternate, Block, Item, Run
from estimator.scope import FrontEnd as ScopeFrontEnd
from estimator.scope import Header as ScopeHeader
from estimator.scope import Job as ScopeJob
from estimator.reading.inventory import COUNT_CAUSE_WORDS, COUNT_CAUSES_LEAD
from estimator.catalogue.tags import tag_prefix
from estimator.writing.write import tag_list

from bms.citations import SHEET, SourceIds, clarification_text, squash as _squash, strip_label
from bms.model import (CLARIFICATION_KINDS, UNNAMED_EXISTING, Clarification, Count, DemolitionLine, Device, FrontEnd,
                       Job, Ref, SetAside, System)
from bms import order as gem_module
from bms.order import (existing_lines, front_end_entries, front_end_rank, group_line, new_lines,
                       position as gem_position)
from estimator.proposal.layout import EXISTING_SYSTEM_HEADING
from bms.playbook import DEFAULT_ORDER, Playbook, Shape

SEQUENCE_ONLY_ORDER = 20            # a block whose count prints "Qty (##)": after the equipment (shapes.json "order")
GENERIC_FORM = "{verb} {device}{owner}"          # a system or a slot with no shape
GENERIC_HEADER = "Qty ({n}) {name} {tags}"         # a system with no shape (wording.json "header.generic" when set)
ALTERNATE_LABEL = "ALT #{k}: {name}"               # an alternate's label (wording.json "alternate_label" when set)
_AFTER_LINES = ("confirm", "assumed", "per_drawings", "note")      # the order of the "*" lines
# an assumption's reason: the words put before it, and the lead words a reason may already carry (then none is put)
# (wording.json "assumption.because" / "assumption.leads" when set)
BECAUSE = "because "
_REASON_LEADS = ("as ", "since ", "given that ", "because ")

assert set(_AFTER_LINES) == set(CLARIFICATION_KINDS)

# ---- T-005c (estimator rulings of 2026-10-11, 4, 5 and the printing of 7): the renderer's own words ------------------
# (wording.json keys proposed to the Playbook in HarkPro/outbox/T-005c-report.md)
# the one flag line of a front end whose existing BMS is not one of AME's three (`estimator.proposal.write.ame_bms`)
AME_ONLY_FLAG = ("***AME works only with Honeywell WEBS, Johnson FX (Facility Explorer) or Niagara Tridium "
                 "front ends")
# the front end when the documents call for none (no front-end line from the reading, none written)
NO_FRONT_END = "No front end information found"
# a device marked "future" prints "(<mark_note>)" after its line, in red; "(FUTURE)" when it has no note
FUTURE_WORD = "FUTURE"
RED_MARKS = ("future", "notice")
# the Demolition Scope (T-G1): the last block. "demo" prints as written; the other actions print in these words.
DEMOLITION_HEADING = "Demolition Scope"
_ACTION_WORDS = {"demo": "demo", "existing to remain": "Existing to Remain", "relocation": "Relocation"}
# a "*" line longer than this prints as short points: the first after the label, each other on its own "- " line
LONG_CLARIFICATION = 150
_ABBREVIATIONS = {"mfr", "mfrs", "spec", "specs", "sec", "no", "nos", "e.g", "i.e", "etc", "inc", "co", "corp",
                  "approx", "dwg", "dwgs", "fig", "div", "vol", "st", "ft", "min", "max", "ref", "typ", "incl", "qty",
                  "vs", "dept", "bldg", "mech", "elec"}
_POINT_BREAK = re.compile(r"([.;])\s+")
_WORD_BEFORE = re.compile(r"([A-Za-z.]+)$")


def short_points(text: str) -> str:
    """A long "*" line as short points (T-005 ruling 5): split after each sentence (". " before a capital, never after
    an abbreviation such as "Mfr." or "Spec.") and each "; ", the first point after the line's label, each other on a
    line of its own after "- " (a line break in the one note, so the words are never cut or reworded). A line of at most
    LONG_CLARIFICATION characters, or one sentence, is given back as it is."""
    text = (text or "").strip()
    if len(text) <= LONG_CLARIFICATION:
        return text
    pieces, start = [], 0
    for match in _POINT_BREAK.finditer(text):
        if match.group(1) == ".":
            word = _WORD_BEFORE.search(text[start:match.start()])
            if not text[match.end():match.end() + 1].isupper():
                continue
            if word and (len(word.group(1).strip(".")) <= 1 or word.group(1).lower().strip(".") in _ABBREVIATIONS):
                continue
        pieces.append(text[start:match.start()])
        start = match.end()
    pieces.append(text[start:])
    pieces = [p.strip().rstrip(" .;") for p in pieces if p.strip(" .;")]
    if len(pieces) < 2:
        return text
    return "\n".join([pieces[0]] + [f"- {p}" for p in pieces[1:]])


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
      each other family prints its own header, its count the highest the documents give.
    - A system with no devices prints no block: it is one `note` line in `lines` ("left out, no lines written", with
      the writer's reason) for the Evidence Package, or, when the documents put it outside AME's scope (a named
      exception of `job.exceptions` has its key, `plan._exceptions`, HP 24), the EXCEPTION line(s) in the job's own
      words, which `named_exceptions` prints (`left_out_text`).
    - `job.header` must be set (the run sets it): it becomes `scope.header` (`date` parsed from ISO).
    - Blocks print in the Playbook's block order (`block_order`: the shape's `order`, Global Points first; a block
      whose count prints "Qty (##)" after the equipment blocks), the plan's own order kept within one order number.
    - Base systems become `scope.blocks`; `alternate` "add" / "deduct" systems go into `scope.add_alternates` /
      `scope.deduct_alternates`, each labelled "ALT #k: <name>" (adds and deducts numbered apart);
      `job.exceptions` become `scope.named_exceptions`; `job.front_end` the FrontEnd.
    - A system with no shape is rendered in the generic form "{verb} {device}{owner}" in device order.
    - Never adds a line that is not a field of the Job (nothing internal reaches the client document), except the
      Master Template's existing-BMS front-end lines T-005e names (`_existing_template_lines`), its "OR" line between
      two alternatives, and the pump VFD Control GEM v4 always writes (`_gem_devices`). GEM v4 also prints a valve
      Furnish and Wire and leaves out a valve inside a factory-controlled unit (a note in `lines`). The off-hours work,
      prevailing wage and warranty the documents call for are added after, by `bms.labor.with_labor` and
      `with_warranty`. Also the
      estimator's red flags of T-005 ruling 4 in the front end (`_front_end_flags`: "No front end information found",
      the AME_ONLY_FLAG line). A "future" device prints "(<mark_note>)" after its line and a "future" or "notice"
      device prints red (`_with_marks`, `_items`); a "*" line over LONG_CLARIFICATION prints as short points.
    - `job.demolition` prints as the last block of the base bid, headed "Demolition Scope" (no quantity and no number
      in the heading, as Labor Conditions has none). Each line is "Qty (N) <family> <action words>" and red, the same
      mark as a line the estimator must notice. A note follows the line after a comma. No demolition lines prints no
      such block. The alternates, and the Labor Conditions block that `bms.labor.with_labor` adds, print after it.
    - `job.set_aside` (T-007): a "same unit labelled again" or "part plan of one area" set-aside prints one short "*"
      line in its family's block, naming the sheets ("*AHU counted once on part plans M-403 and M-404",
      `_count_note`); a "demolition sheet" set-aside prints none (the Demolition Scope carries those units).
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
    exception_lines: list[tuple[str, str]] = []                  # (the block it is about, "" for none; the line)
    for x in job.exceptions:
        if not x.text.strip():
            continue
        text = ids.without_issued(x.text).strip()
        if not text:
            # nothing but issued ids: left out (the validator's must_fix on the whole job names it), never a crash
            continue
        exception_lines.append((x.system_key, text))
    exceptions = tuple(text for _, text in exception_lines)
    base: list[Block] = []
    alternates: dict[str, list[tuple[Block, ...]]] = {"add": [], "deduct": []}
    after: dict[str, list[RenderedLine]] = {"add": [], "deduct": []}      # print order: base, add alternates, deducts
    for system in sorted(job.systems, key=lambda s: block_order(s, playbook)):      # stable: the plan's order kept
        printed: list[RenderedLine] = []
        mine = tuple(text for key, text in exception_lines if key and key == system.key)
        blocks = _system_blocks(system, playbook, printed, ids, mine, job.set_aside)
        if system.alternate in alternates and blocks:
            alternates[system.alternate].append(blocks)
        elif system.alternate == "base":
            base.extend(blocks)
        (lines if system.alternate == "base" else after[system.alternate]).extend(printed)
    demo = _demolition_block(job, ids)
    if demo is not None:
        base.append(demo)
        lines.append(RenderedLine("", None, "header", demo.header, None, None))
        lines += [RenderedLine("", None, "line", item.text, None, item.quantity) for item in demo.items]
    lines += after["add"] + after["deduct"]
    adds, deducts = (_alternates(alternates[side], playbook) for side in ("add", "deduct"))
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


DEMOLITION_KEY = "demolition"   # sheet_plan selects labor rows by this key, not by the heading text


def _demolition_block(job: Job, ids: SourceIds) -> Block | None:
    """The Demolition Scope, or None when the job has no demolition lines.

    The heading carries no quantity and takes no number (`numbered=False`, as Labor Conditions: the price sheet
    gives it none). Each line uses the block-line style (`Item` kind "line") and is red, as a marked line is
    (`Run.red`). "demo" stays "demo"; the other actions print as `Existing to Remain` and `Relocation`. A note
    follows after a comma. The note goes through the same issued-id cut as other client text.
    """
    if not job.demolition:
        return None
    items = []
    for line in job.demolition:
        text = _demolition_text(line, ids)
        items.append(Item(kind="line", depth=1, runs=(Run(text=text, red=True),), quantity=line.count))
    return Block(header=DEMOLITION_HEADING, items=tuple(items), numbered=False, key=DEMOLITION_KEY)


def _demolition_text(line: DemolitionLine, ids: SourceIds) -> str:
    words = _ACTION_WORDS[line.action]
    text = f"Qty ({line.count}) {line.family} {words}"
    note = _squash(ids.without_issued(line.note)).strip()
    if note:
        text = f"{text}, {note}"
    return text


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
    """The count that prints: the highest any source gives (never undershoot), None when none is known. Estimator
    ruling L2 (2026-10-10; the schedule's count does not take its place): every other count that differs is named,
    with its place, in the block's "*Qty." note (`_count_part`), so none is silent."""
    return count.highest()


_NO_PLACE = Ref("", "", "")      # the place of a count that cites no source (printed as `unlabelled` says)


def _own_entries(count: Count) -> list[tuple[int, Ref]]:
    """The count's own `value`, once for each source that backs it. A `value` with no source is one entry with no
    place, so when another count is higher (the highest prints) the lower `value` is still named in the note, never
    dropped. [] when `value` is unknown."""
    if count.value is None:
        return []
    return [(count.value, r) for r in count.sources] or [(count.value, _NO_PLACE)]


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
# the last clause of a count's part when ruling L1 left a sum out of it (`Count.added_up`): the sheets of one floor and
# area count once, so the sum is named, never printed as the count. The renderer's own words (no wording.json key).
COUNT_ADDED_UP = "{n} if every sheet of the same floor and area is added up"
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
    added_up: str = COUNT_ADDED_UP


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


def _added_up(count: Count, printed: int) -> int | None:
    """The sum ruling L1 left out of the count (`Count.added_up`) when it is above the number that prints: the number
    the note names beside it. None when there is none, or the printed count has reached it (a count typed or read
    since): then no sum is left to name."""
    up = count.added_up
    return up.value if up is not None and up.value > printed else None


def _count_part(count: Count, ids: SourceIds, causes: str = "", words: _CountWords = _CountWords(),
                with_sum: bool = True) -> str:
    """One count's part of the quantity note: "(N) per <label>; M per <label>; K and J per <label>": the printed
    (highest) count first, then every other count with its label, highest first, equal values from one label
    folded, none dropped (estimator ruling D6); a count with no label still prints, with the plain `unlabelled`
    words ("15 elsewhere in the documents", never "per the documents"); "" when there is no other count. `causes` (`_count_causes`) prints after
    the "plan placements" label, or after the printed count's sheet when the plan placements give that count too.
    `words` gives the labels and the joiners (" per ", " and ", "; ") and the unlabelled words. The last clause is the
    sum ruling L1 left out of the count, when it is above the printed count ("9 if every sheet of the same floor and
    area is added up"): it makes a part of a count with no other count; `with_sum` False leaves it off (the part
    `_qty_notes` compares lines by)."""
    n = _printed(count)
    if n is None:
        return ""
    entries = _own_entries(count)
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
    added = _added_up(count, n) if with_sum else None
    if not folded and added is None:
        return ""
    clauses = sorted(folded.items(), key=lambda item: -max(item[1]))

    def shown(label: str) -> str:
        return f"{label} {causes}" if causes and label == placements else label

    def clause(label: str, values: list[int]) -> str:
        numbers = words.both.join(str(v) for v in sorted(values, reverse=True))
        return f"{numbers}{words.per}{shown(label)}" if label else f"{numbers} {words.unlabelled}"

    pieces = [clause(label, values) for label, values in clauses]
    if added is not None:
        pieces.append(words.added_up.format(n=added))
    others = words.joiner.join(pieces)
    first = shown(head)
    if causes and head != placements and placements in heads:
        first = f"{head} {causes}"               # the plan placements give the printed count too: their causes stay
    return f"({n}){words.per}{first}{words.joiner}{others}" if head else f"({n}){words.joiner}{others}"


# ---- one line --------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class _Printed:
    text: str
    depth: int
    device: Device
    verb: str | None
    quantity: int | None       # the device's quantity (None when unknown)
    priced: bool               # the price sheet prices it (AME furnishes, installs or wires it; not an interlock)
    marker: bool = False       # the Master Template's "OR" line between two alternatives (no device of its own)


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


def line_prints_quantity(form: str, slot_kind: str | None) -> bool:
    """A device line prints "Qty (N)" in front when its wording names a verb or a device and the slot is not an
    interlock. That is the set of lines whose form ended with {qty}, plus Unit Ventilators terminal_strip_device."""
    if slot_kind == "interlock":
        return False
    return "{verb}" in form or "{device}" in form


def line_form(device: Device, shape: Shape | None, playbook: Playbook) -> str:
    """The wording a device's line prints with: its slot's wording in the shape (else the generic form), a fixed
    integration slot's house line in a block whose shape lacks it, or a house line printed as written."""
    house_lines, house_slots = _fixed_texts(playbook, shape)
    form = _slot_form(shape, device.slot)
    if form == GENERIC_FORM and device.slot in house_slots:
        form = house_slots[device.slot]          # a fixed integration slot in a block whose shape lacks it
    return house_lines.get(_plain(device.name), form)    # a house line printed as written, never with a verb


def _device_lines(devices, shape: Shape | None, system: System | None, playbook: Playbook,
                  reference: set[int], qty_notes: dict[str, str] | None = None) -> list[_Printed]:
    """The devices as printed lines, in the order GEM v4 sets (T-005e addendum, `bms.order`):
    - a block with a shape prints its template slots in the shape's line order (its Master Template entry, GEM v4
      ~396-402), then the order given;
    - the standard order (`bms.order.position`: controller, sensors, switches, leak, current switches, relays,
      dampers, fan and pump signals, primary equipment signals, feedback, other outputs, power wiring, fire alarm,
      filters, airflow stations, valves, Install and Wire, other Wire and interlocks) places every other line: a
      catch-all slot's line or a slot the shape lacks goes after the template's last line of its position, else
      between the template lines of a lower and a higher position (`bms.order.place`), never after the valves by its
      slot's place; a block with no shape is in the standard order throughout;
    - the integration group is always last within the scope (19; the VFD group first), then the Miscellaneous
      Responsibilities (20: the plain work statements of the other_wiring slot, with no verb);
    - the front end (no shape, no system) follows the Master Template's front-end order (`bms.order.front_end_rank`).
    A device of a sub-line slot (the shape's `under`) prints one level in, directly after its parent: the nearest
    device of the parent slot listed before it (else the last one listed), with no verb; with no parent device it
    prints in its own slot's place. A line of the integration trio whose slot the shape sets under no parent (a block
    with no shape) prints at the trio's own depth (wording.json integration_trio.depths: the rep line one level in).
    Every line prints its slot's wording. A line whose wording names a verb or a device, and whose slot is not an
    interlock (`line_prints_quantity`), prints "Qty (N)" in front when its count is unknown or not the block's own
    count (`wording.json` quantity.unknown / quantity.line), and only then. `qty_notes` (device id -> the quantity
    note) puts a device's other counts after its own line (GEM v4 ~609); the note does not add the prefix.
    Two lines of one Master Template "OR" group printed next to each other get an "OR" line between them, and only
    the first is priced (`bms.order.alternatives`)."""
    devices = list(devices)
    qty_notes = qty_notes or {}
    line_order = shape.line_order if shape is not None else ()
    slot_index = {slot: i for i, slot in enumerate(line_order)}
    under = shape.under if shape is not None else {}
    casing = _casing(playbook)
    what = _title(system.name, casing) if system is not None and system.control == "integration" else ""
    quantity_words = playbook.wording.quantity
    house_lines, _ = _fixed_texts(playbook, shape)
    trio = dict(zip(playbook.wording.integration_trio, playbook.wording.integration_depths))
    front_end = shape is None and system is None
    worded: list[tuple[str, str, str | None]] = []      # per device: (its text, its form, its verb when printed)
    for device in devices:
        number = _printed(device.quantity)
        owner = _owner(device, playbook)
        form = line_form(device, shape, playbook)
        fixed = house_lines.get(_plain(device.name))     # a house line printed as written (line_form chose it)
        shown = _title(device.name, casing)
        slot_kind = shape.slot_kinds.get(device.slot) if shape is not None else None
        if _PLACEHOLDER.search(form):
            text = _fill(form, verb=device.verb, device=shown, owner=owner, qty="", what=what)
        elif fixed is not None and owner and fixed not in playbook.wording.integration_trio:
            text = _squash(form + owner)             # a shape's house line another party furnishes keeps its bracket
        else:
            text = form
        if line_prints_quantity(form, slot_kind):
            # ruling 15, G-002: "Qty (N) <device line>", in front of the verb, only when N is not the block's count;
            # other counts stay after the line and never add the prefix (rules.md "Line quantity")
            note = qty_notes.get(device.id, "")
            if number is None or number not in reference:
                prefix = quantity_words["unknown"] if number is None else quantity_words["line"].format(n=number)
                text = prefix + text
            if note:
                text += note
        worded.append((text, form, device.verb if "{verb}" in form else None))

    def kind_of(i: int) -> str | None:
        return shape.slot_kinds.get(devices[i].slot) if shape is not None else None

    def gem(i: int) -> int:
        text, _, verb = worded[i]
        return gem_position(text, verb, devices[i].slot, kind_of(i))

    gem_integration = gem_module.INTEGRATION

    def last_group(i: int) -> bool:          # the integration group: always last in the block (rules.md:486)
        return kind_of(i) == "integration" or gem(i) >= gem_integration

    # the template lines (a shape's own slots; not a sub-line, not the integration group) in the shape's order
    template = sorted((i for i in range(len(devices)) if shape is not None and devices[i].slot not in under
                       and not gem_module.is_catch_all(devices[i].slot, line_order) and not last_group(i)),
                      key=lambda i: (slot_index[devices[i].slot], i))
    template_at = {i: k for k, i in enumerate(template)}
    template_positions = [gem(i) for i in template]

    def rank(i: int) -> tuple:
        if front_end:
            return (front_end_rank(worded[i][0]), 0.0, 0, 0)
        p = gem(i)
        if last_group(i):
            p = gem_integration if kind_of(i) == "integration" else p
            group = gem_module.integration_rank(devices[i].slot) if p == gem_integration else 0
            return (1, float(p), group, slot_index.get(devices[i].slot, len(slot_index)))
        if shape is None:
            return (0, float(p), 0, 0)
        if i in template_at:
            return (0, float(template_at[i]), 0, 0)
        return (0, gem_module.place(template_positions, p), p, slot_index.get(devices[i].slot, len(slot_index)))

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
            found = ((*rank(i), i),)
        else:
            found = key(parent, seen | {i}) + ((i,),)
        keys[i] = found
        return found

    ranked = sorted(range(len(devices)), key=key)
    groups = gem_module.alternatives(shape.name if shape is not None else None)
    out: list[_Printed] = []
    previous: Device | None = None              # the last top-level line printed
    for i in ranked:
        device = devices[i]
        text, form, verb = worded[i]
        slot_kind = kind_of(i)
        acts = "AME" in (device.furnished_by, device.installed_by, device.wired_by)
        depth = len(key(i))
        if device.slot not in under and form in trio:   # a trio line the shape sets under no parent: the trio's
            depth = trio[form]                          # own depth (the rep line one level in, RND-13)
        priced = acts and slot_kind != "interlock"
        if depth == 1 and previous is not None and previous.slot != device.slot and any(
                {previous.slot, device.slot} <= group for group in groups):
            out.append(_Printed(gem_module.alternative_word(), 1, device, None, None, False, marker=True))
            priced = False                  # an alternative to the line above: only the first is priced
        out.append(_Printed(text, depth, device, verb, _printed(device.quantity), priced))
        if depth == 1:
            previous = device
    return out


def printed_texts(system: System, shape: Shape | None, playbook: Playbook, ids: SourceIds) -> list[tuple[str, str]]:
    """Each line a system's devices print, as (device id, text), in print order: the text the proposal prints, an
    issued id taken out of a name as `_system_blocks` does. The front end (a system with no key) counts its lines
    against 1 and names no equipment, as `_front_end` does. The validator's line-length check reads it (VAL-14). The
    "OR" lines and the lines GEM v4 adds (`_gem_devices`: a pump's VFD Control) are not the writer's: left out."""
    if system.key:
        reference = {n for n in (_printed(f.count) for f in _header_families(system)) if n is not None}
        devices, _ = _gem_devices(system, shape, playbook)
        counts = [f.count for f in _header_families(system)]
    else:
        reference = {1}
        devices, counts = list(system.devices), []
    named = _named(devices, ids)
    notes = _qty_notes(named, counts, playbook, ids)
    own = {d.id for d in system.devices}
    printed = _with_marks(_device_lines(named, shape, system if system.key else None, playbook, reference, notes),
                          ids)
    return [(p.device.id, p.text) for p in printed if not p.marker and p.device.id in own]


# ---- what GEM v4 decides about a line (T-005e addendum) ----------------------------------------------------------

def _is_valve(name: str) -> bool:
    words = gem_module.valve_rules()
    return bool(re.search(words.get("words", r"\bvalves?\b"), name or "", re.I)) and not (
        words.get("not_words") and re.search(words["not_words"], name or "", re.I))


def _gem_devices(system: System, shape: Shape | None, playbook: Playbook) -> tuple[list[Device], list[str]]:
    """The system's devices as GEM v4 prints them, and the lines left out (for the Evidence Package's note):
    - a valve is always Furnish and Wire (GEM v4 ~228): one written Furnish and Install prints Furnish and Wire;
    - a valve inside a factory-controlled unit (packaged or integration control) that the unit maker furnishes and AME
      does not install is not a controls line (GEM v4 ~291, ~294): left out;
    - a pump AME's own DDC controller runs gets VFD Control with its Start/Stop and Status only when the documents
      show a VFD on that pump (playbook/rules.md "Minimum points on AME-run equipment": "VFD Control when the
      equipment has a VFD"; lead ruling 2026-10-11, the Playbook wins over GEM v4 ~346-349): a block under field
      control whose pump Start/Stop line has no VFD Control line for that pump, but another line of the block names
      that pump's VFD (a VFD fault or speed feedback) or the Start/Stop line's own quote names a VFD, gets one, citing
      the Start/Stop line's sources (`bms.order.minimum_points`). A constant-speed pump gets none. Fault and speed
      feedback are never added.
    Pure: the Job is not changed."""
    rules = gem_module.valve_rules()
    factory = system.control in tuple(rules.get("factory_controls", ("packaged", "integration")))
    out: list[Device] = []
    left: list[str] = []
    for d in system.devices:
        if _is_valve(d.name):
            if factory and d.furnished_by == "Unit Mfr." and d.installed_by != "AME":
                left.append(_fill(rules.get("left_out", "{line}: left out"), line=_title(d.name, _casing(playbook))))
                continue
            if d.verb == "Furnish and Install":
                d = replace(d, verb="Furnish and Wire")
        out.append(d)
    return out + _pump_minimums(system, shape, out), left


def _pump_minimums(system: System, shape: Shape | None, devices: list[Device]) -> list[Device]:
    if system.control != "field":
        return []
    words = gem_module.minimum_points()
    if not words:
        return []
    pump, start, vfd, not_control = (re.compile(words[k], re.I) for k in ("pump", "start_stop", "vfd_control",
                                                                          "not_control"))
    controls = [d.name for d in devices if vfd.search(d.name) and not not_control.search(d.name)]
    named_vfd = [d.name for d in devices if vfd.search(d.name)]          # any line naming a VFD (control, fault ...)
    starts = [d for d in devices if d.verb == "Furnish" and d.furnished_by == "AME" and pump.search(d.name)
              and start.search(d.name)]
    added: list[Device] = []
    for d in starts:
        stem = _squash(re.sub(words["stem_end"], "", d.name, flags=re.I))
        if not stem:
            continue
        mine = [c for c in controls if stem.lower() in c.lower()]
        if mine or (len(starts) == 1 and any(pump.search(c) for c in controls)):
            continue
        # the Playbook wins (rules.md "Minimum points on AME-run equipment"): only a pump the documents show with a
        # VFD gets VFD Control; a constant-speed pump gets none (lead ruling 2026-10-11)
        if not (any(stem.lower() in n.lower() for n in named_vfd) or any(vfd.search(r.quote or "") for r in d.refs)):
            continue
        line_order = shape.line_order if shape is not None else ()
        slot = next((s for s in (d.slot.replace("start_stop", "vfd_control"), d.slot.replace("start_stop", "vfd"))
                     if s != d.slot and s in line_order), "other_point" if "other_point" in line_order else d.slot)
        added.append(replace(d, id=f"{d.id}.vfd", slot=slot, name=words["line"].format(pump=stem), assumption=None,
                             flag="none"))
    return added


# ---- the quantity notes on a device's own line (GEM v4 ~609) -------------------------------------------------------

LINE_COUNTS = " ({counts})"        # its other counts after it: " (4 per M-601; 2 per M-401)"


def _counts_text(count: Count, playbook: Playbook, ids: SourceIds, with_sum: bool = True) -> str:
    """A count's other counts as a line carries them ("4 per M-601; 2 per M-401", the printed one first, ruling L2
    and D6), "" when the documents give no other; through the safety net every client text goes through."""
    words = _count_words(playbook)
    part = _count_part(count, ids, _count_causes(count, playbook), words, with_sum=with_sum)
    if not part:
        return ""
    return ids.without_issued(re.sub(r"^\((\d+)\)", r"\1", part), place=True)


def _qty_notes(devices, family_counts: list[Count], playbook: Playbook, ids: SourceIds) -> dict[str, str]:
    """device id -> the other counts its own line carries (GEM v4 ~609; estimator ruling 15, 2026-10-11 afternoon:
    quantities print in the line itself, no separate quantity note), when its count names other counts that no header
    family of the block already names (the header carries those, `_header_counts`)."""
    families = {_counts_text(c, playbook, ids, with_sum=False) for c in family_counts}
    families.discard("")
    out: dict[str, str] = {}
    for d in devices:
        count = replace(d.quantity, added_up=None)
        text = _counts_text(count, playbook, ids)
        if text and text not in families:
            out[d.id] = LINE_COUNTS.format(counts=text)
    return out


def _header_counts(count: Count, playbook: Playbook, ids: SourceIds) -> str:
    """The other counts a header's family has, after the header (ruling 15; ruling L2: every other count prints with
    both numbers and where), "" for none: " (2 per M-001; 1 per M-101)", and the sum ruling L1 left out last."""
    text = _counts_text(count, playbook, ids)
    return LINE_COUNTS.format(counts=text) if text else ""


def _notes(clarifications: tuple[Clarification, ...], devices, playbook: Playbook, ids: SourceIds) -> list[str]:
    """The block's "*" lines after its lines: one short line per item, never a paragraph (estimator ruling 14,
    2026-10-11 afternoon; it replaces "one '*' note per block"). The kinds in the Playbook's order: confirm, assumed
    (every assumption with its why), per drawings, the client notes; each item in its kind's form, a repeat printed
    once, a long item as short points (`short_points`). No quantity note: quantities print in the lines (ruling 15,
    `_qty_notes`, `_header_counts`). A text's own leading label is not printed twice, an issued source id left in a
    stale text never prints (the token alone is taken out: no sentence is rewritten), and a text is never cut."""
    texts: dict[str, list[str]] = {kind: [] for kind in CLARIFICATION_KINDS}
    for c in clarifications:
        text = _trim(clarification_text(c.kind, c.text, ids))
        if text:
            texts[c.kind].append(text)
    for device in devices:
        if device.assumption is not None:
            texts["assumed"].append(_reason(device.assumption, ids, playbook))
    return [short_points(_fill(playbook.wording.clarifications[kind], text=text))
            for kind in _AFTER_LINES for text in dict.fromkeys(texts[kind])]


# T-007 Task 2.6 (reduced; estimator ruling 14): a duplicate of one unit the takeoff set aside prints one short '*'
# line in its family's block. A "demolition sheet" set-aside prints none: the Demolition Scope block carries those
# units. The other reasons (future item, existing to remain, not a unit of this family, count by unit register) print
# none here either.
DUPLICATE_WORDS = {"part plan of one area": " on part plans", "same unit labelled again": ", labelled again on"}
COUNTED_ONCE = "*{family} counted once{words}"
_SHEET_SPLIT = re.compile(r"\s*(?:[,;&/]|\band\b)\s*", re.IGNORECASE)


def _family_prefix(tag: str) -> str:
    match = re.match(r"[A-Z]+", tag_prefix(str(tag).strip().upper()))
    return match.group(0) if match else ""


def _sheets_named(texts: Sequence[str], ids: SourceIds, tags: frozenset[str] = frozenset()) -> list[str]:
    """The printable sheet numbers the texts name, in order, each once ("M-403", "M-404"); a word whose letters are
    one of the block's tag prefixes (`tags`: "EF" for "EF-2A") is a unit, never a sheet."""
    found: list[str] = []
    for text in texts:
        for part in _SHEET_SPLIT.split(text or ""):
            for word in part.split():
                sheet = ids.sheet(word)
                if sheet and _family_prefix(sheet) not in tags and sheet not in found:
                    found.append(sheet)
    return found


def _count_note(system: System, set_aside: Sequence[SetAside], ids: SourceIds) -> list[str]:
    """The block's '*' lines for the takeoff's set-asides: one short line per "same unit labelled again" or "part plan
    of one area" set-aside of a family the block carries (its tags' prefix is the set-aside's family), never a
    paragraph and never tech hours (rulings 14 and 16). The line names the sheets: "*AHU counted once on part plans
    M-403 and M-404" (the ref's where, then the note's sheets), then both numbers (T-007b): "*AHU counted once on part plans M-401,
    M-402, M-403 and M-404: 16 set aside, 5 counted". With no sheet to name it gives both numbers instead:
    "*AHU counted once on part plans: 6 set aside, 5 counted". A "demolition sheet" set-aside prints no line."""
    counts = {}
    for family in system.families:
        for tag in family.tags:
            prefix = _family_prefix(tag)
            if prefix:
                counts.setdefault(prefix, _printed(family.count))
    out: list[str] = []
    for aside in set_aside:
        words = DUPLICATE_WORDS.get(aside.reason)
        family = _family_prefix(aside.family)
        if words is None or not family or family not in counts:
            continue
        text = COUNTED_ONCE.format(family=aside.family.strip().upper(), words=words)
        sheets = _sheets_named((aside.ref.where, aside.note), ids, frozenset(counts))
        counted = counts[family]
        numbers = f": {aside.value} set aside" + (f", {counted} counted" if counted is not None else "")
        if sheets:
            text = f"{text} {' and '.join(sheets)}" if len(sheets) <= 2 else \
                f"{text} {', '.join(sheets[:-1])} and {sheets[-1]}"
            text += numbers
        else:
            text = f"{text.replace(', labelled again on', ', labelled again')}{numbers}"
        text = _squash(ids.without_issued(text)).strip()
        if text and text not in out:
            out.append(text)
    out += [n for n in _verify_lines(system, set_aside, ids) if n not in out]
    return out


# T-009 (estimator ruling 21): a thermostat or space sensor line that prints the plan count (`takeoff.apply_plan_counts`)
# gets one "*Verify" line built from its "plan count prints" set-asides: the sheets of its quantity's sources, then
# every number that did not print, highest first (ruling D6: none is silent).
PLAN_COUNT_REASON = "plan count prints"
VERIFY = "*Verify: "
VERIFY_LIMIT = 160
_ASIDE_WORD = re.compile(r" of ([^;()]+) prints$")      # `takeoff.NOTE_FORM` ends with the device word, plural


def _names_joined(names: Sequence[str]) -> str:
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"


def _wrap_verify(head: str, phrases: Sequence[str], names: Sequence[str], word: str, n: int) -> list[str]:
    """The "*Verify" lines of one device, none over `VERIFY_LIMIT` characters: the pieces joined by "; " while they fit,
    a new line (with its own "*Verify: ") where they do not; a sheet list too long for one line is split at its
    commas, never cut."""
    room = VERIFY_LIMIT - len(VERIFY)
    pieces = [head, *phrases]
    if len(head) > room:                                    # the sheets alone fill a line: continue them
        chunks, current = [], []
        for name in names:
            trial = _names_joined([*current, name])
            if current and len(f"{n} {word} drawn on {trial}") > room:
                chunks.append(current)
                current = []
            current.append(name)
        chunks.append(current)
        pieces = [f"{n} {word} drawn on {_names_joined(chunks[0])}",
                  *(f"also drawn on {_names_joined(c)}" for c in chunks[1:]), *phrases]
    lines: list[str] = []
    for piece in pieces:
        if lines and len(f"{lines[-1]}; {piece}") <= VERIFY_LIMIT:
            lines[-1] = f"{lines[-1]}; {piece}"
        else:
            lines.append(f"{VERIFY}{piece}")
    return lines


def _verify_lines(system: System, set_aside: Sequence[SetAside], ids: SourceIds) -> list[str]:
    """The block's "*Verify" lines for its thermostat and space sensor lines that print the plan count: "*Verify: 30
    thermostats drawn on M-201 and M-202; the sequence calls for one per fan coil unit (55)". The other number is
    named "the sequence calls for one per <family> (<n>)" when it is a family's count of the block, else
    "<n> per <place>" as the quantity note names it (`_count_label`). A sheet with no number is named by its document
    and page. Each line is at most 160 characters and splits at "; ". Only a device the block still has gets a line."""
    tags = frozenset(p for f in system.families for t in f.tags if (p := _family_prefix(t)))
    families = [(f.name, _printed(f.count)) for f in system.families if _printed(f.count) is not None]
    words = _CountWords()
    out: list[str] = []
    for device in system.devices:
        mine = sorted((a for a in set_aside if a.reason == PLAN_COUNT_REASON and a.family == device.id),
                      key=lambda a: -a.value)
        plan = device.quantity.highest()
        if not mine or plan is None:
            continue
        names: list[str] = []
        for ref in device.quantity.sources:
            found = _sheets_named((ref.where,), ids, tags)
            name = found[0] if found else _squash(ids.without_issued(ref.where)).strip()
            if name and name not in names:
                names.append(name)
        if not names:
            continue
        word = (_ASIDE_WORD.search(mine[0].note) or [None, "thermostats"])[1]
        phrases = []
        for aside in mine:
            family = next((name for name, count in families if count == aside.value), "")
            if family:
                phrases.append(f"the sequence calls for one per {family.lower()} ({aside.value})")
                continue
            place = _count_label(aside.value, aside.ref, ids, words.labels)
            phrases.append(f"{aside.value}{words.per}{place}" if place else f"{aside.value} {words.unlabelled}")
        head = f"{plan} {word} drawn on {_names_joined(names)}"
        out += [_squash(ids.without_issued(line)).strip()
                for line in _wrap_verify(head, list(dict.fromkeys(phrases)), names, word, plan)]
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


LEFT_OUT = "{name}: left out, no lines written"


def left_out_text(system: System, exceptions: Sequence[str] = ()) -> str:
    """The note for a system with no lines (it prints no block). When the documents put the system outside AME's scope
    (HP 24: `exceptions` are the lines of the named exceptions of its key, `plan._exceptions`, as the proposal prints
    them), the note is that EXCEPTION line, in the job's own words, one line for each, never a fixed text. Otherwise
    it says the system is left out, with the writer's reason: its no_scope_reason, else what its clarifications say
    (the Evidence Package's note)."""
    if exceptions:
        return "\n".join(exceptions)
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


def _system_blocks(system: System, playbook: Playbook, out: list[RenderedLine], ids: SourceIds,
                   exceptions: Sequence[str] = (), set_aside: Sequence[SetAside] = ()) -> tuple[Block, ...]:
    """One block, or one header per family stacked over the shared lines (the lines sit under the last header,
    the tech hours on the first). A system with no lines prints no block: it is a note (`left_out_text`: its named
    exception lines when it has any, which print among the proposal's exceptions). The takeoff's duplicate set-asides
    of the block's families print as '*' lines after its other notes (`_count_note`)."""
    if not system.devices:
        out += [RenderedLine(system.key, None, "note", line, None, None)
                for line in left_out_text(system, exceptions).split("\n")]
        return ()
    shape = _shape_of(system, playbook)
    form = shape.header if shape is not None else playbook.wording.header.get("generic", GENERIC_HEADER)
    families = _header_families(system)
    if len(families) <= 1:
        family = families[0] if families else None
        headers = [_header_text(form, system.name, family.tags if family else (),
                                family.count if family else Count(value=None), playbook)
                   + (_header_counts(family.count, playbook, ids) if family else "")]
    else:
        headers = [_header_text(form, f.name, f.tags, f.count, playbook) + _header_counts(f.count, playbook, ids)
                   for f in families]
    # T-005e evening correction (lead, 2026-10-11): the Master Template entry decides. Where it prints a group line
    # over its stacked Qty headers ("Chilled Water System"), the block keeps it, unnumbered; where it prints none, none
    group = group_line(shape.name if shape is not None else None) if len(headers) > 1 else ""
    reference = {n for n in (_printed(f.count) for f in families) if n is not None}
    pending = not families or any(_printed(f.count) is None for f in families)     # "Qty (##)": nothing is priced
    devices, left = _gem_devices(system, shape, playbook)       # T-005e addendum: valves, pump minimum (GEM v4)
    devices = _named(devices, ids)
    qty_notes = _qty_notes(devices, [f.count for f in families], playbook, ids)
    printed = _with_marks(_device_lines(devices, shape, system, playbook, reference, qty_notes), ids)
    notes = _notes(system.clarifications, system.devices, playbook, ids)
    notes += [n for n in _count_note(system, set_aside, ids) if n not in notes]
    try:                                 # every field checked: a blank line, a negative quantity or tech hours
        items = _items(printed, pending) + [Item(kind="note", runs=(Run(text=n),)) for n in notes]
        last = len(headers) - 1
        blocks = [Block(header=h, joined=i > 0 or bool(group), tech_hours=system.tech_hours if i == 0 else None,
                        items=tuple(items) if i == last else ()) for i, h in enumerate(headers)]
        if group:                        # the group line: no number, no hours, no lines (the hours stay on Qty 1)
            blocks.insert(0, Block(header=group, numbered=False))
    except ValueError as error:          # pydantic's ValidationError is a ValueError
        raise RenderError(f"system {system.key}: {error}") from error
    out += [RenderedLine(system.key, None, "header", h, None, None) for h in ([group] if group else []) + headers]
    out += _traced(system.key, printed, notes)
    out += [RenderedLine(system.key, None, "note", line, None, None) for line in left]
    return tuple(blocks)


def _items(printed: list[_Printed], pending: bool) -> list[Item]:
    return [Item(kind="line", depth=p.depth, runs=(Run(text=p.text, red=not p.marker and p.device.mark in RED_MARKS),),
                 quantity=p.quantity if (p.priced and not pending) else None) for p in printed]


def _with_marks(printed: list[_Printed], ids: SourceIds) -> list[_Printed]:
    """The printed lines with a "future" device's "(<mark_note>)" after its words (T-005 ruling 7: "(FUTURE AS PER
    control schematic on sheet M-9.01)"; "(FUTURE)" with no note). The note goes through the safety net every client
    text goes through (`SourceIds.without_issued`). `_items` prints a "future" or "notice" line in red."""
    out = []
    for p in printed:
        if p.device.mark == "future":
            note = _squash(ids.without_issued(p.device.mark_note or "")).strip(" ()") or FUTURE_WORD
            p = replace(p, text=f"{p.text} ({note})")
        out.append(p)
    return out


def _traced(key: str, printed: list[_Printed], notes: list[str]) -> list[RenderedLine]:
    lines = [RenderedLine(key, None if p.marker else p.device.id, "line", p.text, p.verb, p.quantity)
             for p in printed]
    return lines + [RenderedLine(key, None, "note", n, None, None) for n in notes]


# ---- the front end ---------------------------------------------------------------------------------------------

def existing_system_name(front: FrontEnd) -> str | None:
    """The name the proposal prints for the existing BMS (HP 9): None for a new system (a name left on it is not
    printed), the name the documents give (white space squeezed), else the plain fill-in `UNNAMED_EXISTING` (rules.md
    "Front end mode"). The old writer refuses an existing BMS with no name; the planner has asked for it in a
    question, so the proposal prints the fill-in and the estimator completes it."""
    if front.mode != "extend-existing":
        return None
    return _squash(front.existing_system_name or "") or UNNAMED_EXISTING


def _existing_template_lines(front: FrontEnd, printed: list[_Printed]) -> list[str]:
    """The Master Template's front-end house lines the writer's lines do not already carry (T-005e; estimator ruling
    19, 2026-10-11 afternoon: the template's front-end section defines the standard lines): for an EXISTING BMS its
    "Extension of Existing" lines (network level control panel, 3-D graphics to match existing, training:
    `bms.order.existing_lines`), for a NEW system its "Default" lines (3-D graphics, training: `bms.order.new_lines`).
    A written line of the same entry stands, citing this job. None when the documents call for no front end (no line
    from the reading, none written: T-005c's "No front end information found"), or when the writer wrote no
    front-end line and said why (the documents give the front end to others)."""
    if not (front.devices or front.lines):
        return []
    if not front.devices and _squash(front.no_scope_reason or ""):
        return []
    have = set().union(*(front_end_entries(p.text) for p in printed))
    template = existing_lines() if front.mode == "extend-existing" else new_lines()
    return [text for text, entry in template if entry not in have]


def _front_end_flags(front: FrontEnd, printed: list[_Printed]) -> list[str]:
    """The front end's red lines (T-005 ruling 4): "No front end information found" when the documents call for none
    (no line from the reading, none written); the one AME_ONLY_FLAG line when the existing BMS the documents name is
    not one of AME's three (the unnamed fill-in has the planner's question instead)."""
    flags = []
    if not printed and not front.lines:
        flags.append(NO_FRONT_END)
    name = existing_system_name(front)
    if name and name != UNNAMED_EXISTING and not ame_bms(name):
        flags.append(AME_ONLY_FLAG)
    return flags


def _front_end(front: FrontEnd | None, playbook: Playbook, out: list[RenderedLine],
               ids: SourceIds) -> ScopeFrontEnd:
    if front is None:
        out.append(RenderedLine("", None, "note", NO_FRONT_END, None, None))
        return ScopeFrontEnd(mode="new-system", items=(Item(kind="note", runs=(Run(text=NO_FRONT_END, red=True),)),))
    devices = _named(front.devices, ids)
    qty_notes = _qty_notes(devices, [], playbook, ids)
    printed = _with_marks(_device_lines(devices, None, None, playbook, {1}, qty_notes), ids)
    notes = _notes(front.clarifications, front.devices, playbook, ids)
    added = _existing_template_lines(front, printed)
    # one list in the Master Template's front-end order: the writer's lines and the template's existing-BMS lines
    merged = sorted([(front_end_rank(p.text), n, p) for n, p in enumerate(printed)]
                    + [(front_end_rank(text), -1, text) for text in added], key=lambda e: (e[0], e[1] < 0, e[1]))
    traced: list[RenderedLine] = []
    lines: list[Item] = []
    for _, _, entry in merged:
        if isinstance(entry, str):
            traced.append(RenderedLine("", None, "line", entry, None, 1))
            lines.append(Item(kind="line", depth=1, runs=(Run(text=entry),), quantity=1))
        else:
            traced += _traced("", [entry], [])
            lines += _items([entry], False)
    if front.mode == "extend-existing":       # the Master Template's tie-in header (template ~77): the proposal
        # writer prints it from the mode (estimator.proposal.layout.front_end_heading); traced here for the review
        traced.insert(0, RenderedLine("", None, "header",
                                      f"{EXISTING_SYSTEM_HEADING} {existing_system_name(front)} BMS", None, None))
    red_notes = _front_end_flags(front, printed)         # T-005c: after the lines and the notes
    out += traced + _traced("", [], notes) + [RenderedLine("", None, "note", n, None, None) for n in red_notes]
    try:
        items = (lines + [Item(kind="note", runs=(Run(text=n),)) for n in notes]
                 + [Item(kind="note", runs=(Run(text=n, red=True),)) for n in red_notes])
        return ScopeFrontEnd(mode=front.mode, existing_system_name=existing_system_name(front),
                             items=tuple(items), tech_hours=front.tech_hours)
    except ValueError as error:
        raise RenderError(f"the front end cannot be printed: {error}") from error
