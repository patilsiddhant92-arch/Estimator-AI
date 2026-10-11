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
from estimator.writing.write import tag_list

from bms.citations import SHEET, SourceIds, clarification_text, squash as _squash, strip_label
from bms.model import CLARIFICATION_KINDS, UNNAMED_EXISTING, Clarification, Count, Device, FrontEnd, Job, Ref, System
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
    - A system with no shape is rendered in the generic form "{verb} {device}{owner}{qty}" in device order.
    - Never adds a line that is not a field of the Job (nothing internal reaches the client document), except the
      estimator's red flags of T-005 ruling 4 in the front end (`_front_end_flags`: "No front end information found",
      the AME_ONLY_FLAG line). A "future" device prints "(<mark_note>)" after its line and a "future" or "notice"
      device prints red (`_with_marks`, `_items`); a "*" line over LONG_CLARIFICATION prints as short points.
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
        blocks = _system_blocks(system, playbook, printed, ids, mine)
        if system.alternate in alternates and blocks:
            alternates[system.alternate].append(blocks)
        elif system.alternate == "base":
            base.extend(blocks)
        (lines if system.alternate == "base" else after[system.alternate]).extend(printed)
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


def _line_counts(devices) -> list[Count]:
    """The devices' quantities for the quantity note, each without a sum: the sum is the planner's, set on a family
    from the sheets (`plan_read.Reader.family`), so a line that carries one (a writer's copy of its family's count, or
    a number it made up) names none."""
    return [replace(d.quantity, added_up=None) for d in devices]


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
    `_count_note` compares lines by)."""
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


def _count_note(counts: list[Count], playbook: Playbook, ids: SourceIds, names: list[str] | None = None) -> str:
    """The block's one quantity note naming every other count in the documents ("" when there is none), and, last in
    a count's part, the sum ruling L1 left out of it. `names` gives, count by count, the family name its part opens
    with ("" for none: a block with one family, a device). It goes through the safety net every other client text
    goes through (`SourceIds.without_issued`): an issued id that reached a place is taken out, token only."""
    words = _count_words(playbook)
    names = list(names or []) + [""] * (len(counts) - len(names or []))
    # a part, without its sum clause -> (the family name it opens with, the part) for each; a repeat prints once
    seen: dict[str, list[tuple[str, str]]] = {}
    for count, name in zip(counts, names):       # (a device often carries its family's count: the family's wins)
        causes = _count_causes(count, playbook)
        part = _count_part(count, ids, causes, words)
        if not part:
            continue
        under = seen.setdefault(_count_part(count, ids, causes, words, with_sum=False) or part, [])
        # a line that carries a family's count adds nothing, with or without the family's sum; a second family that
        # reads the same numbers from the same places is a count of its own, and prints under its own name (none
        # dropped)
        if any(name == other for other, _ in under) or (not name and under):
            continue
        under.append((name, part))
    parts = [f"{name} {part}" if name else part for under in seen.values() for name, part in under]
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
    return [(p.device.id, p.text) for p in _with_marks(_device_lines(_named(system.devices, ids), shape,
                                                                      system if system.key else None, playbook,
                                                                      reference), ids)]


# ---- the "*" clarifications --------------------------------------------------------------------------------------

def _notes(clarifications: tuple[Clarification, ...], devices, counts: list[Count],
           playbook: Playbook, ids: SourceIds, names: list[str] | None = None) -> list[str]:
    """One "*" line per kind, after the lines: confirm, assumed (every assumption with its why), per drawings, the
    note line; then the one quantity note naming every other count (and the sum ruling L1 left out of a family's
    count). A text's own leading label is not printed twice, an issued source id left in a stale text never prints
    (the token alone is taken out: no sentence is rewritten), and a text is never cut."""
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
            out.append(short_points(_fill(playbook.wording.clarifications[kind], text="; ".join(unique))))
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
                   exceptions: Sequence[str] = ()) -> tuple[Block, ...]:
    """One block, or one header per family stacked over the shared lines (the lines sit under the last header,
    the tech hours on the first). A system with no lines prints no block: it is a note (`left_out_text`: its named
    exception lines when it has any, which print among the proposal's exceptions)."""
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
                                family.count if family else Count(value=None), playbook)]
    else:
        headers = [_header_text(form, f.name, f.tags, f.count, playbook) for f in families]
    reference = {n for n in (_printed(f.count) for f in families) if n is not None}
    pending = not families or any(_printed(f.count) is None for f in families)     # "Qty (##)": nothing is priced
    printed = _with_marks(_device_lines(_named(system.devices, ids), shape, system, playbook, reference), ids)
    named = len(system.families) > 1             # more than one family: each family's part names its family
    notes = _notes(system.clarifications, system.devices,
                   [f.count for f in system.families] + _line_counts(system.devices), playbook, ids,
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
    return [Item(kind="line", depth=p.depth, runs=(Run(text=p.text, red=p.device.mark in RED_MARKS),),
                 quantity=p.quantity if (p.priced and not pending) else None) for p in printed]


def _with_marks(printed: list[_Printed], ids: SourceIds) -> list[_Printed]:
    """The printed lines with a "future" device's "(<mark_note>)" after its words (T-005 ruling 7: "(FUTURE AS PER
    control schematic on sheet M710.00)"; "(FUTURE)" with no note). The note goes through the safety net every client
    text goes through (`SourceIds.without_issued`). `_items` prints a "future" or "notice" line in red."""
    out = []
    for p in printed:
        if p.device.mark == "future":
            note = _squash(ids.without_issued(p.device.mark_note or "")).strip(" ()") or FUTURE_WORD
            p = replace(p, text=f"{p.text} ({note})")
        out.append(p)
    return out


def _traced(key: str, printed: list[_Printed], notes: list[str]) -> list[RenderedLine]:
    lines = [RenderedLine(key, p.device.id, "line", p.text, p.verb, p.quantity) for p in printed]
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
    printed = _with_marks(_device_lines(_named(front.devices, ids), None, None, playbook, {1}), ids)
    notes = _notes(front.clarifications, front.devices, _line_counts(front.devices), playbook, ids)
    red_notes = _front_end_flags(front, printed)
    out += _traced("", printed, notes) + [RenderedLine("", None, "note", n, None, None) for n in red_notes]
    try:
        items = (_items(printed, False) + [Item(kind="note", runs=(Run(text=n),)) for n in notes]
                 + [Item(kind="note", runs=(Run(text=n, red=True),)) for n in red_notes])
        return ScopeFrontEnd(mode=front.mode, existing_system_name=existing_system_name(front),
                             items=tuple(items), tech_hours=front.tech_hours)
    except ValueError as error:
        raise RenderError(f"the front end cannot be printed: {error}") from error
