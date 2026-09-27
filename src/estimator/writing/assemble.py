"""The whole-job path, after the judge: cross-check the AI's plan and scope, then assemble the job.

The judge reads the whole dossier and plans every system (estimator.writing.whole_job), then
writes each planned system's scope. Nothing here decides scope. It checks:

- every planned quantity against the counts the dossier gathered (the schedule's QUANTITY column,
  the distinct tags, the placements on the plans, the riser): CONFIRMED when one agrees or the
  quote states it, DISCREPANCY with both numbers when the counts disagree, PENDING when the plan
  gives none. The AI's number is never changed silently;
- every family on the drawings that no planned system covers (listed, never silently added);
- every written line for its quote (in the dossier, word for word or nearly), the house style, and
  the words the client must never see;
- each scope against its Master Template entry, as a checklist: lines usually present that the AI
  left out are listed;
- the tech hours: the Master Template's rule when it fits the kind, else the AI's suggestion as an
  ASSUMPTION, else none, with a review line. Never invented.

And it never loses a planned system: a header too long for a block is shortened (or stacked, one
header per family), a system with no quantity is printed "Qty (##)" with the count to give at the top
of the review list, and a system whose lines were all refused is printed with the Master Template's
lines, marked ASSUMPTION. The review list is ranked, the most urgent first, and repeated rows merged.

The shapes it reads are the plan's (docs/superpowers/plans/2026-09-26-whole-job-writing.md): a
Dossier (text, images, sources, families, device_totals, counts), a JobPlan of PlannedSystems and
a WrittenScope of WrittenLines per system. They are read by their field names only.
"""
from __future__ import annotations

import dataclasses
import math
import re
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from types import SimpleNamespace
from typing import NamedTuple

from estimator.catalogue.overview import FOUND as FOUND_STATUS, short_place
from estimator.catalogue.pdf import clean_text
from estimator.reading.inventory import ON_PLANS
from estimator.scope import Alternate, Block, Item, Job, Run
from estimator.writing.front_end import (FRONT_END_FILE, Evidence, _load as _front_end_data, _term,
                                         extended_warranty_block, front_end, global_points_block, job_header)
from estimator.writing.judge import MAX_HEADER
from estimator.writing.phrasing import examples_for, load_bank
from estimator.writing.style import load_house_style
from estimator.writing.templates import load_templates, nearest_templates, template_for
from estimator.writing.write import (ADDED, ASSUMPTION, CONFIRMED, PENDING, ReviewItem, ScopeLine, WrittenSystem,
                                     _front_end_system, _hardware, _note_is_borne_out, _word, tag_list)

DISCREPANCY = "DISCREPANCY"
SOURCE = "AI (whole job)"
UNSOURCED_CONFIDENCE = 0.4    # a planned system that cites no source: still written, never surer than this
UNQUOTED_CAP = 0.5            # a line whose quote is not in the dossier
PICTURE_CAP = 0.7             # a quote the judge read off a picture (I1, I2 …): it cannot be machine-checked
COUNT_TO_FILL = "##"          # "Qty (##)": the house form of a count still to be filled
FALLBACK = "System written with fallback lines — check"
MAX_FRONT_END_LINES = 6       # the front end's lines (under each, its own sub-lines); the rest go to the review
NEAR_DUPLICATE = 0.6          # a plan front-end line sharing this share of its words with a line already there
CONTROLS_TRADES = ("Mechanical", "Controls")     # a schedule on these sheets is the controls trade's
# How urgent a review row is: the order of the ranked review list. First a system that can't be written (fallback
# lines, a system nothing shows), then the quantities (a count to give, a quantity conflict), then the AI's questions,
# then the rules and the AI disagreeing, then the rest.
TIER_FIRST, TIER_DISCREPANCY, TIER_QUESTION, TIER_DISAGREE, TIER_REST = 1, 2, 3, 4, 5
TIER_QUANTITY = TIER_DISCREPANCY
QUOTE_SHARE = 0.6             # of the quote's words, in order, that must be in the dossier
SHORT_QUOTE = 3               # a quote of this many words or fewer must be there word for word
_COUNT_LABELS = (("quantity_column", "the schedule's QUANTITY column"), ("distinct_tags", "distinct tags"),
                 ("plan_placements", "placements on the plans"), ("riser", "the riser"))
_COUNT_COLUMNS = ("schedule_rows", "quantity_column", "distinct_tags", "plan_placements", "riser")
_NUMBER_WORDS = {w: n for n, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
    "seventeen eighteen nineteen twenty".split())}
_ID = re.compile(r"\[?\s*([A-Z]{1,3}\d+)\s*\]?")
_NEVER = re.compile(r"\$|\bhours?\b|\bhrs?\b|confidence|\brule:|\bAI:", re.I)


def _squash(text: str) -> str:
    return " ".join((text or "").split())


def _plain(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").casefold()).strip()


# --- tags and source ids ----------------------------------------------------------------------------

def _stem(tag: str) -> str:
    cut = max(tag.rfind("-"), tag.rfind("."))
    return tag[:cut + 1] if cut > 0 else ""


def expand_tags(tags) -> list[str]:
    """Every tag, one by one: "VAV-101 thru VAV-112, VAV-114", "RTU-1 thru 3", "AHU-1, 2, 3" or a
    tuple of such pieces."""
    items = [tags] if isinstance(tags, str) else list(tags or ())
    out: list[str] = []
    stem = head = ""
    for item in items:
        for part in (p.strip() for p in str(item).split(",")):
            if not part:
                continue
            m = re.match(r"^(.+?)\s+thru\s+(.+)$", part, re.I)
            first, last = (m.group(1).strip(), m.group(2).strip()) if m else (part, None)
            if stem and re.fullmatch(r"\d+[A-Za-z]?", first):
                first = stem + first
            elif head and re.fullmatch(r"\d+(?:\.\d+)?(?:-\d+(?:\.\d+)?)*[A-Za-z]?", first):
                segments, previous = first.split("-"), head.split("-")    # "EDH-1-2, 1-3": EDH-1-3
                if len(previous) > len(segments):                          # "ERV-C-1, 1-1": ERV-1-1
                    first = "-".join(previous[:len(previous) - len(segments)] + segments)
            stem = _stem(first)
            head = first
            if last is None:
                out.append(first)
                continue
            if re.fullmatch(r"\d+[A-Za-z]?", last):
                last = stem + last
            elif re.fullmatch(r"\d+(?:\.\d+)?(?:-\d+(?:\.\d+)?)+[A-Za-z]?", last):    # "VAV-4-1 thru 4-7"
                segments, previous = last.split("-"), first.split("-")
                if len(previous) > len(segments):
                    last = "-".join(previous[:len(previous) - len(segments)] + segments)
            a, b =re.match(r"^(.*?)(\d+)$", first), re.match(r"^(.*?)(\d+)$", last)
            if a and b and a.group(1) == b.group(1) and 0 <= int(b.group(2)) - int(a.group(2)) <= 1000:
                width = len(a.group(2)) if a.group(2).startswith("0") else 0
                out += [f"{a.group(1)}{str(k).zfill(width)}" for k in range(int(a.group(2)), int(b.group(2)) + 1)]
            else:
                out += [first, last]
    return list(dict.fromkeys(out))


def _tag_prefix(tag: str) -> str:
    m = re.match(r"[A-Za-z]+", tag or "")
    return m.group(0).upper() if m else ""


_EQUIPMENT_TAG = re.compile(r"^[A-Za-z]{1,6}(?:-?\d[A-Za-z0-9.]*|-[A-Za-z0-9]+(?:\.\d+)?)(?:-[A-Za-z0-9]+(?:\.\d+)?)*$")


def is_equipment_tag(tag: str) -> bool:
    """The text looks like an equipment tag: letters, a dash and digits or letters ("RTU-1", "AC-EMR-1", "SPXF-A",
    "HRU-3.0"). A room ("Garage 111"), a name ("Fire Pump") or a bare word ("MVF") is not."""
    return bool(_EQUIPMENT_TAG.match(_squash(tag)))


def equipment_tags(system) -> list[str]:
    """The system's tags that look like equipment tags, one by one."""
    return [t for t in expand_tags(system.tags) if is_equipment_tag(t)]


def locations(system) -> list[str]:
    """The rooms or places the plan listed as the system's "tags" ("Fire Pump Room 008", "Garage 111")."""
    return [t for t in expand_tags(system.tags) if not is_equipment_tag(t) and _is_room(t)]


def source_ids(*values) -> list[str]:
    """The source ids in "[S41]", "S41", or a tuple of them, in order, each once."""
    ids: list[str] = []
    for value in values:
        for piece in ([value] if isinstance(value, str) else list(value or ())):
            ids += [m.group(1) for m in _ID.finditer(str(piece))]
    return list(dict.fromkeys(ids))


def _system_ids(system) -> list[str]:
    return source_ids(system.quantity_source, system.sequence_sources, system.schedule_sources)


_SHEET = re.compile(r"[A-Z]{1,3}-?\d{1,4}(?:\.\d{1,2})?[A-Z]?")
_SECTION_NUMBER = re.compile(r"^\d{2} \d{2} \d{2}(?: \d{2})?")
_WHERE_PAGE = re.compile(r",\s*([^,]+?)\s+page\s+(\d+)")
_ANY_ID = re.compile(r"\[\s*([SI]\d+)\s*\]|(?<![\w\-.])([SI]\d+)(?![\w\-])")


def plain_place(where: str) -> str:
    """A source's place in few words, the sheet or the spec section and the page: "23 09 23 page 10",
    "H601 page 19", "P502 page 10 (picture)"."""
    where = _squash(re.sub(r"\s*\(\+\d+ others?\)\s*$", "", _squash(where)))
    m = re.match(r"^(?P<sheet>\S+) \((?P<doc>[^,]+), page (?P<page>\d+)\)$", where)       # "M-601.00 (Mech.pdf, page 10)"
    if m:
        return f"{m.group('sheet')} page {m.group('page')}"
    m = re.match(r"^[^·]+·\s*(?P<section>[^·]+?)\s*·\s*page (?P<page>\d+)$", where)     # "Specs.pdf · 23 09 23 · page 12"
    if m:
        return f"{m.group('section')} page {m.group('page')}"
    matches = list(_WHERE_PAGE.finditer(where))
    if not matches:
        m = re.match(r"^(.*?)\s*\(the document list\)$", where)
        return m.group(1).rsplit("/", 1)[-1] if m else where
    m = matches[-1]
    label, page = where[:m.start()].strip(), m.group(2)
    picture = " (picture)" if "(picture)" in where else ""
    section = _SECTION_NUMBER.match(label)
    if section:
        return f"{section.group(0)} page {page}{picture}"
    for piece in reversed([p.strip() for p in label.split(",")]):
        first = piece.split(" ", 1)[0] if piece else ""
        if _SHEET.fullmatch(first):
            return f"{first} page {page}{picture}"
    short = label if len(label) <= 50 else label[:50].rsplit(" ", 1)[0]
    return f"{short} page {page}{picture}" if short else f"{m.group(1)} page {page}{picture}"


def plain_ids(text: str, dossier, images=None) -> str:
    """The text with each source id ([S97], I15) replaced by the place it points to. `images` numbers the
    pictures the way one question did (I1 is its first picture); else the dossier's numbering."""
    if not text or dossier is None:
        return text

    def place(m: re.Match) -> str:
        sid = m.group(1) or m.group(2)
        if sid.startswith("I") and images is not None:
            n = int(sid[1:])
            return plain_place(_image_where(images[n - 1])) if 1 <= n <= len(images) else "a picture"
        where = (dossier.sources or {}).get(sid)
        if where:
            return plain_place(where)
        if sid.startswith("I"):
            pictures = list(dossier.images or ())
            n = int(sid[1:])
            return plain_place(_image_where(pictures[n - 1])) if 1 <= n <= len(pictures) else "a picture"
        return "the job's documents"

    return _ANY_ID.sub(place, text)


def _image_where(image) -> str:
    sheet = getattr(image, "sheet", None)
    label = f"{sheet} {image.what}" if sheet and not str(image.what).startswith(sheet) else image.what
    return f"{label}, {image.document} page {image.page} (picture)"


def cited_text(dossier, source_id: str) -> str:
    """The dossier's paragraph or row that carries `[source_id]`: from the id to the next blank line
    or the next line that starts with an id. "" when the text does not carry it."""
    text = dossier.text or ""
    at = text.find(f"[{source_id}]")
    if at < 0:
        return ""
    end = len(text)
    blank = re.search(r"\n\s*\n", text[at:])
    if blank:
        end = at + blank.start()
    nxt = re.search(r"\n\s*\[[A-Z]{1,3}\d+\]", text[at:end])
    if nxt:
        end = at + nxt.start()
    return text[at:end].strip()[:4000]


# --- the quote check ------------------------------------------------------------------------------------

def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (text or "").casefold())


class _Index:
    """The dossier's words, for finding a quote: whitespace and punctuation ignored."""

    def __init__(self, text: str):
        self.words = _tokens(text)
        self.joined = " " + " ".join(self.words) + " "
        self.at: dict[str, list[int]] = defaultdict(list)
        for i, w in enumerate(self.words):
            self.at[w].append(i)

    def holds(self, quote: str, share: float = QUOTE_SHARE) -> bool:
        wanted = _tokens(quote)[:60]
        if not wanted:
            return False
        if " " + " ".join(wanted) + " " in self.joined:
            return True
        if len(wanted) <= SHORT_QUOTE:
            return False
        need = math.ceil(share * len(wanted))
        present = [w for w in dict.fromkeys(wanted) if w in self.at]
        anchors = sorted(present, key=lambda w: len(self.at[w]))[:3]
        n = len(wanted)
        for word in anchors:
            for pos in self.at[word][:300]:
                window = self.words[max(0, pos - 2 * n): pos + 2 * n]
                if _in_order(wanted, window) >= need:
                    return True
        return False


def _in_order(a: list[str], b: list[str]) -> int:
    """How many of a's words appear in b in the same order (the longest common subsequence)."""
    previous = [0] * (len(b) + 1)
    for x in a:
        current = [0]
        for j, y in enumerate(b):
            current.append(previous[j] + 1 if x == y else max(previous[j + 1], current[j]))
        previous = current
    return previous[-1]


@lru_cache(maxsize=4)
def _index(text: str) -> _Index:
    return _Index(text)


def quote_in_dossier(quote: str, dossier) -> bool:
    return _index(dossier.text or "").holds(quote)


def _states(quote: str, n: int) -> bool:
    """The quote states the number n (as digits or a word)."""
    if re.search(rf"(?<![\w.-]){n}(?![\d.])", quote or ""):
        return True
    return any(_NUMBER_WORDS.get(w) == n for w in _tokens(quote))


# --- C1: the plan against the counts ----------------------------------------------------------------------

@dataclass(frozen=True)
class PlanCheck:
    """One planned system, checked: its quantity's category, the counts it was checked against,
    and the review lines."""
    system: object                 # the PlannedSystem
    category: str                  # CONFIRMED | DISCREPANCY | ASSUMPTION | PENDING
    counts: dict                   # label -> n: the counts the quantity was checked against
    columns: dict                  # the dossier's counts for the system's families, summed (for the Plan tab)
    quote_found: bool
    sourced: bool                  # the plan cites at least one source id for it
    where: str                     # where its quantity source is, in words
    review: tuple[ReviewItem, ...]
    quantity: object = None        # the count its header prints: the plan's, one counted from the plans, or panels
    devices: int | None = None     # a panel's device count, printed on its device line "(Qty. N Total)"
    held: bool = False             # nothing on the drawings shows it: a question, never a block

    @property
    def goes(self) -> str:
        s = self.system
        if s.exception:
            return "the exceptions"
        if self.held:
            return "held back — a question: does it exist?"
        if s.alternate in ("add", "deduct"):
            return f"{s.alternate} alternate" + (", Qty (##)" if self.category == PENDING else "")
        if self.category == PENDING:
            return "the base bid, Qty (##)"
        return "the base bid"


def _families(dossier) -> list[tuple[object, set[str]]]:
    return [(f, {t.upper() for t in expand_tags(getattr(f, "tags", "") or "")}) for f in dossier.families or ()]


def _name(system) -> str:
    return _squash(re.sub(r"^\s*Qty\s*\([^)]*\)\s*", "", system.header or "")) or system.key


class Fold(NamedTuple):
    """A planned system whose header folds other units in ("ERV-C-1, 1-1, 2-1 w/ Electric Duct Heater
    EDH-C-1, …"): the parent's own tags, and each folded family as (its kind, its tags)."""
    parent: tuple[str, ...]
    folded: tuple[tuple[str, tuple[str, ...]], ...]


def fold(system) -> Fold:
    """The parent's tags and the units its header folds in after " w/ ". A folded unit never counts toward
    the parent's quantity; it gets its own stacked header."""
    tags = expand_tags(system.tags)
    name = _name(system)
    m = re.search(r"\s+w/\s*(.+)$", name, re.I)
    if m is None or "|" in name:
        return Fold(tuple(tags), ())
    kind, rest = _split_kind(m.group(1))
    named = _named_tags(m.group(1))
    leftover = re.sub(r"\b(?:thru|and)\b", " ", _TAG_RUN.sub("", rest or ""), flags=re.I)
    if named and rest and not re.search(r"[A-Za-z]{2,}", leftover):
        named = [t.upper() for t in expand_tags(re.sub(r"\s*(?:&|\band\b)\s*", ", ", rest))]   # "EDH-1-2, 1-3"
    if not named:
        return Fold(tuple(tags), ())
    folded = [t for t in tags if t.upper() in set(named)] or named
    kind = kind or _squash(m.group(1))
    parent = [t for t in tags if t.upper() not in {f.upper() for f in folded}]
    if not parent or {_tag_prefix(t) for t in folded} & {_tag_prefix(t) for t in parent}:
        return Fold(tuple(tags), ())      # "VAV Box w/ SCR Electric Reheat VAV-4-1 …": a descriptor of its own units
    return Fold(tuple(parent), ((kind, tuple(folded)),))


def _counts_for(system, dossier) -> tuple[dict, dict]:
    """(label -> n to check the quantity against, column -> n summed for the Plan tab). Only the parent's
    own tags count: the units its header folds in never do."""
    tags = {t.upper() for t in fold(system).parent}
    if not tags:
        return {}, {}
    families = _families(dossier)
    touched = [(f, own) for f, own in families if own & tags]
    known = set().union(*(own for _, own in families)) if families else set()
    prefixes = [f.prefix.upper() for f, _ in touched]
    prefixes += [p for p in dict.fromkeys(_tag_prefix(t) for t in tags - known)
                 if p and p not in prefixes and p in {k.upper() for k in (dossier.counts or {})}]
    counts = {k.upper(): v for k, v in (dossier.counts or {}).items()}
    columns = {}
    for column in _COUNT_COLUMNS:
        values = [counts.get(p, {}).get(column) for p in prefixes]
        if values and all(isinstance(v, int) for v in values):
            columns[column] = sum(values)
    subset = any(not own <= tags for _, own in touched)
    if subset:
        mine = len(tags & known)
        return ({"its own tags on the schedule": mine} if mine else {}), columns
    return {label: columns[key] for key, label in _COUNT_LABELS if key in columns}, columns


def _counts_text(counts: dict) -> str:
    return ", ".join(f"{n} by {label}" for label, n in counts.items()) or "no count"


def _one_per_type(q: int, counts: dict, columns: dict) -> bool:
    """The quantity agrees only with the distinct tags, but the schedule's QUANTITY column counts more:
    a type row counted as one unit, when it is that many."""
    column = columns.get("quantity_column")
    agree = [label for label, n in counts.items() if n == q]
    return column is not None and column != q and agree == ["distinct tags"]


def _is_picture(source_id: str, dossier) -> bool:
    """The id is one of the dossier's pictures (I1 … In): what the judge read there cannot be machine-checked."""
    m = re.fullmatch(r"I(\d+)", source_id or "")
    return bool(m) and 1 <= int(m.group(1)) <= len(dossier.images or ())


def _check_system(system, dossier) -> PlanCheck:
    name = _name(system)
    counts, columns = _counts_for(system, dossier)
    ids = _system_ids(system)
    sourced = bool(ids)
    qid = (source_ids(system.quantity_source) or [""])[0]
    where = (dossier.sources or {}).get(qid, "") if qid else ""
    quote = system.quantity_quote or ""
    found = bool(quote) and (quote_in_dossier(quote, dossier) or _is_picture(qid, dossier))
    quoted = f"{plain_place(where) + ': ' if where else ''}“{quote}”" if quote else "no quote"
    review: list[ReviewItem] = []
    q = system.quantity
    printed, devices = q, None
    panel = is_panel_system(system)
    if panel:                         # a panel's header counts panels; the devices go on the device line
        printed = load_house_style().panels_in(quote) or 1
        devices = q if q is not None and q != printed else None
        if devices is not None:
            review.append(ReviewItem(name, "", f"{name}: the header counts the panels ({printed}); the plan's count "
                                     f"({q}) is the devices, printed on the device line", quoted,
                                     "Check the panels and the devices", tier=TIER_DISAGREE))
    counted = _counted(counts, columns) if q is None and not panel else None
    if q is None and panel:
        category = ASSUMPTION
        if not system.exception:
            review.append(ReviewItem(name, ASSUMPTION, f"{name}: printed as {printed} panel — the documents state no "
                                     "count", system.why or "", "Confirm the number of panels", tier=TIER_DISAGREE))
    elif q is None and counted is not None:
        printed, label = counted
        category = ON_PLANS
        if not system.exception:
            review.append(ReviewItem(name, ON_PLANS, f"{shape_header(system, printed).headers[0]}: counted from the "
                                     f"plans — {printed} by {label}; the plan gave no quantity",
                                     f"The counts: {_counts_text(counts)}. The plan says: {system.why or 'nothing'}",
                                     "Check the count", tier=TIER_DISAGREE))
    elif q is None:
        category = PENDING
        if not system.exception and _nothing_behind(system, dossier):
            return PlanCheck(system, category, counts, columns, found, sourced, where,
                             (existence_question(system, dossier),), None, None, held=True)
        if not system.exception:
            review.append(ReviewItem(name, PENDING, f"Give the count for {shape_header(system, None).headers[0]}",
                                     f"The plan gives no quantity. The counts: {_counts_text(counts)}. The plan says: "
                                     f"{system.why or 'nothing'}", "Count the units and type the count in the header",
                                     tier=TIER_QUANTITY))
    elif counts and q in counts.values() and not _one_per_type(q, counts, columns):
        category = CONFIRMED
    elif counts:
        category = DISCREPANCY
        stated = " (its quote states it)" if found and _states(quote, q) else ""
        only_tags = _tags_only(counts)
        review.append(ReviewItem(name, DISCREPANCY, f"The plan counts {q} for {name}{stated}; the counts disagree: "
                                 f"{_counts_text(counts)}" + (" (counted only from the schedule's tags, which may not "
                                                              "have been read in full)" if only_tags else ""), quoted,
                                 "The plan's number is kept — correct it if one of the counts is right",
                                 tier=TIER_REST if only_tags else 0))
    elif found and _states(quote, q):
        category = CONFIRMED
    else:
        category = ASSUMPTION
        why = "its quote is not in the job's documents" if quote and not found else "its quote does not state it"
        review.append(ReviewItem(name, ASSUMPTION, f"The plan counts {q} for {name}, with no count to check it "
                                 f"against, and {why}", quoted, "Confirm the count"))
    if not sourced:
        review.append(ReviewItem(name, "", f"The plan cites no source for {name} — it is written, but check every "
                                 "line", system.why or "", "Check the block against the drawings and the sequence"))
    return PlanCheck(system, category, counts, columns, found, sourced, where, tuple(review), printed, devices)


_TAG_COUNTS = ("its own tags on the schedule", "distinct tags")


def _tags_only(counts: dict) -> bool:
    """The only counts are the schedule's tags (its own tags, the distinct tags): no QUANTITY column, no placement
    on the plans, no riser. A table that could not be read in full gives such a count."""
    given = [label for label, n in counts.items() if isinstance(n, int) and n > 0]
    return bool(given) and all(label in _TAG_COUNTS for label in given)


def _on_drawings(system, dossier) -> bool:
    """One of the system's tags is on a schedule or counted on the plans."""
    tags = {t.upper() for t in expand_tags(system.tags)}
    if not tags:
        return False
    known = set().union(*(own for _, own in _families(dossier))) if dossier.families else set()
    counts = {k.upper(): v for k, v in (dossier.counts or {}).items()}
    counted = {p for p, v in counts.items() if any(isinstance(n, int) and n > 0 for n in (v or {}).values())}
    return bool(tags & known) or any(_tag_prefix(t) in counted for t in tags)


def _named_in_sequence(system, dossier) -> bool:
    """A sequence paragraph the plan cites names the system: every word of its name in one paragraph."""
    words = {_singular(w) for w in _plain(_TAG_RUN.sub(" ", _name(system))).split() if w not in _LINE_STOP}
    if not words:
        return False
    for sid in source_ids(system.sequence_sources):
        have = {_singular(w) for w in _plain(cited_text(dossier, sid)).split()}
        if words <= have:
            return True
    return False


def _nothing_behind(system, dossier) -> bool:
    """Nothing on the drawings shows the system (it has no count, so this is asked only then): no schedule row and
    none of its tags on a schedule or the plans. A system with no tags at all is still printed when a sequence
    paragraph it cites names it (a monitoring system whose equipment is not tagged: "Plumbing Pumps")."""
    if source_ids(system.schedule_sources) or is_panel_system(system) or _on_drawings(system, dossier):
        return False
    if expand_tags(system.tags):
        return True                    # the plan names units that no schedule and no plan shows
    return not _named_in_sequence(system, dossier)


def _places(system, dossier) -> str:
    ids = source_ids(system.sequence_sources, system.quantity_source, system.schedule_sources)
    places = [plain_place(_where(dossier, sid)) for sid in ids if _where(dossier, sid)]
    return ", ".join(dict.fromkeys(places)) or "no source"


def existence_question(system, dossier) -> ReviewItem:
    """The top question for a system nothing on the drawings shows: does it exist?"""
    name = _name(system)
    return ReviewItem(name, "", f"Does {name} exist on this job? The plan wrote it from {_places(system, dossier)}; no "
                      "schedule or count shows it.", f"The plan says: {system.why or 'nothing'}",
                      "If it exists, add its block with its count; if not, nothing to do", tier=TIER_FIRST)


_COUNTED_ORDER = ("the schedule's QUANTITY column", "its own tags on the schedule")


def _counted(counts: dict, columns: dict | None = None) -> tuple[int, str] | None:
    """The count the dossier gives for a system the plan gave none: the schedule's QUANTITY column, else its
    own tags; else, for one type tag, its placements on the plans; else the distinct tags, else the placements.
    The riser never counts it alone. None when nothing counts it, or when the system is part of a family whose
    tags are placed more often than they are listed (type tags: its own tags do not count its units)."""
    columns = columns or {}
    if "its own tags on the schedule" in counts and \
            (columns.get("plan_placements") or 0) > (columns.get("distinct_tags") or 0):
        return None

    def positive(label):
        n = counts.get(label)
        return n if isinstance(n, int) and n > 0 else None

    for label in _COUNTED_ORDER:
        if positive(label):
            return counts[label], label
    distinct, placed = positive("distinct tags"), positive("placements on the plans")
    if placed and (distinct or 0) <= 1:
        return placed, "placements on the plans"
    if distinct:
        return distinct, "distinct tags"
    return (placed, "placements on the plans") if placed else None


def is_panel_system(system) -> bool:
    """A system with no tags whose header or kind names a panel or a controller ("Gas Detection System",
    "Fire Pump Controller", "Heat Tracing Control Panel"): its header counts panels."""
    return not expand_tags(system.tags) and load_house_style().is_panel(f"{system.header} {system.kind or ''}")


def _existing(reading) -> set[str]:
    return {i.tag.upper() for i in getattr(reading, "inventory", ()) or () if i.category == "EXISTING"}


_OTHER_TRADE = re.compile(r"\b(?:plumbing|electrical|fire\s+protection|sprinkler|lighting|architectural)\b", re.I)


def _on_controls_schedule(prefix: str, reading, catalogue) -> bool:
    """A schedule row of the family on a controls-trade sheet (mechanical or controls). Without the
    sheet's discipline, the schedule's title decides: a plumbing or electrical schedule is another trade's."""
    disciplines = {(s.document, s.page): s.discipline for s in getattr(catalogue, "sheets", ()) or ()}
    for schedule in getattr(reading, "schedules", ()) or ():
        if not any(_tag_prefix(getattr(row, "tag", "") or "") == prefix for row in schedule.rows):
            continue
        discipline = disciplines.get((schedule.document, schedule.page))
        if discipline in CONTROLS_TRADES or (discipline is None and not _OTHER_TRADE.search(schedule.title or "")):
            return True
    return False


def _reading_noise(family, dossier, reading, catalogue) -> bool:
    """A family the reading found only as model numbers (B, CT, AS …) or only on another trade's schedule:
    no placement on the plans and no row on a controls-trade schedule."""
    prefix = family.prefix.upper()
    counts = {k.upper(): v for k, v in (dossier.counts or {}).items()}.get(prefix) or {}
    if (counts.get("plan_placements") or 0) > 0:
        return False
    return not _on_controls_schedule(prefix, reading, catalogue)


def _uncovered(plan, dossier, reading, catalogue=None) -> list[ReviewItem]:
    planned = {t.upper() for s in plan.systems for t in expand_tags(s.tags)}
    prefixes = {_tag_prefix(t) for t in planned}
    kinds = {_plain(s.kind) for s in plan.systems}
    existing = _existing(reading)
    missed = []
    for family, own in _families(dossier):
        if _reading_noise(family, dossier, reading, catalogue):
            continue
        if not own:
            if family.prefix.upper() not in prefixes and _plain(family.kind) not in kinds:
                missed.append(f"{family.kind} ({family.prefix})")
            continue
        left = [t for t in expand_tags(family.tags) if t.upper() not in planned and t.upper() not in existing]
        if left:
            missed.append(f"{family.kind} {tag_list(left)}")
    if not missed:
        return []
    return [ReviewItem("The plan", DISCREPANCY, "Equipment on the drawings the plan didn't write: " + "; ".join(missed),
                       "On the schedules, but in no planned system", "Add a block for each the job needs")]


def plan_checks(plan, dossier, reading, catalogue=None) -> tuple[list[PlanCheck], list[ReviewItem]]:
    """Each planned system checked, in the plan's order, and the review lines that belong to no
    system (families the plan didn't write; `catalogue` gives the schedules' trades)."""
    return [_check_system(s, dossier) for s in plan.systems], _uncovered(plan, dossier, reading, catalogue)


def check_plan(plan, dossier, reading, catalogue=None) -> list[ReviewItem]:
    """Every review line the plan's cross-checks give: each system's quantity (CONFIRMED needs none,
    DISCREPANCY, ASSUMPTION, PENDING), a system with no source, and the families not written."""
    checks, general = plan_checks(plan, dossier, reading, catalogue)
    return [item for c in checks for item in c.review] + general


# --- C1: the scope against its quotes, the house style and the Master Template --------------------------------

@dataclass(frozen=True)
class CheckedLine:
    text: str
    depth: int
    quantity: int | None     # the count the quote states; None when it states none (the writer counts per unit)
    quote: str
    source_id: str
    why: str
    confidence: float
    quoted: bool             # the quote is in the dossier
    origin: str = ""         # "" for the AI's line; else where it came from ("the Master Template (fallback)")


def system_template(system, templates=None):
    """The Master Template entry that fits the system's kind (or its tag prefix); None when none fits."""
    templates = templates if templates is not None else load_templates()
    tags = expand_tags(system.tags)
    prefix = _tag_prefix(tags[0]) if tags else ""
    return template_for(prefix, system.kind or "", templates)


COUNTS_INTRO = ("Counts from the drawings (a count on the drawings is a confirmed quantity — Quantity rules, Rule 1 "
                "and 2):")
PLAN_NOTES_EVIDENCE = 12_000      # characters of plan sheet notes naming the system's tags, in one system's evidence
_ENTRY_ID = re.compile(r"^\[([A-Z]{1,3}\d+)\]")
_DEVICE_SHEETS = re.compile(r"—\s*(.+)$")
_SHEETS_IN_COUNTS = re.compile(r"plan placements \d+ \(([^)]*)\)")


def system_tags(system) -> list[str]:
    """Every tag the system covers, its families' too, one by one."""
    tags = expand_tags(system.tags)
    for family in getattr(system, "families", ()) or ():
        tags += [t for t in expand_tags(family.tags) if t not in tags]
    return tags


def system_sections(system) -> list[str]:
    """The sequence sections ("Q7") the plan says the system is."""
    return re.findall(r"Q\d+", str(getattr(system, "sequence_section", "") or ""))


def _entries(text: str) -> list[tuple[str | None, str]]:
    """A dossier part's entries: each line starting with a source id, with the indented lines under it (a
    schedule's columns); other lines (a page line, a remark in brackets) as entries of their own, with no id."""
    out: list[list] = []
    for line in (text or "").splitlines():
        if not line.strip():
            continue
        m = _ENTRY_ID.match(line)
        if m:
            out.append([m.group(1), line])
        elif line[:1].isspace() and out and out[-1][0]:
            out[-1][1] += "\n" + line
        else:
            out.append([None, line])
    return [(sid, body) for sid, body in out]


def _dossier_parts(dossier) -> dict[int, str]:
    from estimator.writing.whole_job import _sections as dossier_sections
    return dossier_sections(dossier.text or "")[1]


def _names_any(text: str, tags: set[str], prefixes: set[str]) -> bool:
    """The text names one of the tags (a "thru" range counts each tag), or starts a schedule row with one of the
    type codes (a type row: "HPAC | 719")."""
    body = _ENTRY_ID.sub("", text).strip()
    if tags and set(_named_tags(body)) & tags:
        return True
    first = body.split("|", 1)[0].strip().upper() if "|" in body else ""
    return bool(first) and (first in tags or first in prefixes)


def _dossier_sections_of(dossier) -> dict:
    sections = getattr(dossier, "sections", None)
    if sections:
        return sections
    from estimator.writing.dossier import sections_in
    return sections_in(dossier.text or "")


def system_evidence(system, dossier) -> str:
    """What the GEM reads to write one planned system, in the GEM's order, each passage with its source id: the
    full sequence section(s) the plan says it is (every paragraph, not only the ones the plan cited); the points
    list's rows for its equipment; its schedule rows with the schedule's notes; the plan sheet notes naming its
    tags; its counts from the drawings (the counts, the placements by sheet, the device labels on its sheets); then
    any other passage the plan cited."""
    tags = system_tags(system)
    own = {t.upper() for t in tags if is_equipment_tag(t)}
    prefixes = {_tag_prefix(t) for t in own}
    parts = [f"System: {_name(system)} ({system.kind})",
             f"Tags: {tag_list(tags) if tags else 'none'}",
             f"Planned quantity: {system.quantity if system.quantity is not None else 'not stated'}"
             + (f" — {system.quantity_source} “{system.quantity_quote}”" if system.quantity_quote else "")]
    given: set[str] = set()
    cited = _system_ids(system) + [i for f in getattr(system, "families", ()) or ()
                                   for i in source_ids(f.quantity_source)]
    dossier_parts = _dossier_parts(dossier)

    def block(title: str, entries: list[tuple[str | None, str]]) -> None:
        entries = [(sid, body) for sid, body in entries if sid is None or sid not in given]
        if not any(sid for sid, _ in entries):
            return
        parts.append(f"\n{title}")
        for sid, body in entries:
            parts.append(body)
            if sid:
                given.add(sid)

    # 1. the sequence section(s), whole
    sections = _dossier_sections_of(dossier)
    wanted = [q for q in system_sections(system) if q in sections]
    sequence: list[tuple[str | None, str]] = []
    for q in wanted:
        heading, ids = sections[q]
        sequence.append((None, f"--- [{q}] {heading} ---"))
        sequence += [(sid, cited_text(dossier, sid) or f"[{sid}]") for sid in ids]
    if not wanted:                     # no section: the sequence paragraphs the plan cited
        sequence = [(sid, cited_text(dossier, sid)) for sid in source_ids(system.sequence_sources)
                    if cited_text(dossier, sid)]
    block(f"The sequence of operation for this system{' (' + ', '.join(wanted) + ')' if wanted else ''}:", sequence)

    # 2. the points list's rows for its equipment
    points = _entries(dossier_parts.get(3, ""))
    section_ids = {sid for q in wanted for sid in sections[q][1]}
    rows = [(sid, body) for sid, body in points if sid and (sid in section_ids or sid in cited
                                                           or _names_any(body, own, prefixes))]
    block("The points list rows for its equipment:", rows)

    # 3. its schedule rows and the schedule's notes
    block("Its schedule rows and the schedule's notes:", _schedule_evidence(dossier_parts.get(4, ""), own, prefixes,
                                                                           set(cited)))

    # 4. the plan sheet notes naming its tags
    notes, used, left = [], 0, 0
    for sid, body in _entries(dossier_parts.get(7, "")):
        if sid and (sid in cited or _names_any(body, own, set())):
            if used + len(body) > PLAN_NOTES_EVIDENCE:
                left += 1
                continue
            notes.append((sid, body))
            used += len(body)
    if left:
        notes.append((None, f"({left} more plan sheet notes name it; not given here)"))
    block("Plan sheet notes that name its tags:", notes)

    # 5. its counts from the drawings
    counts = {k.upper(): v for k, v in (dossier.counts or {}).items()}
    count_rows: list[tuple[str | None, str]] = []
    for p in sorted(prefixes):
        if p in counts:
            shown = ", ".join(f"{k.replace('_', ' ')}: {v}" for k, v in counts[p].items() if v is not None)
            count_rows.append((None, f"Counts for {p}: {shown}"))
    sheets: set[str] = set()
    for sid, body in _entries(dossier_parts.get(5, "")):
        head = _ENTRY_ID.sub("", body).strip()
        if sid and head.split(" ", 1)[0].upper() in prefixes:
            count_rows.append((sid, body))
            m = _SHEETS_IN_COUNTS.search(head)
            if m:
                sheets |= {piece.strip().split(" ", 1)[0] for piece in m.group(1).split(";") if piece.strip()}
    devices = [(sid, body) for sid, body in _entries(dossier_parts.get(6, "")) if sid]
    if devices:
        for sid, body in devices:
            m = _DEVICE_SHEETS.search(body)
            on = {piece.strip().split(" ", 1)[0] for piece in m.group(1).split(";")} if m else set()
            if not sheets or on & sheets or sid in cited:
                count_rows.append((sid, body))
    elif dossier.device_totals:
        count_rows.append((None, "Devices counted on the plans (whole job): "
                           + "; ".join(f"{label}: {n}" for label, n in dossier.device_totals.items())))
    if count_rows:
        parts.append(f"\n{COUNTS_INTRO}")
        for sid, body in count_rows:
            if sid is None or sid not in given:
                parts.append(body)
                if sid:
                    given.add(sid)

    # 6. anything else the plan cited
    block("Other passages the plan cited:", [(sid, f"[{sid}] {(dossier.sources or {}).get(sid, '')}\n"
                                                   f"{cited_text(dossier, sid)}".rstrip())
                                            for sid in dict.fromkeys(cited) if not sid.startswith(("I", "Q"))])
    return "\n".join(parts)


def _schedule_evidence(text: str, tags: set[str], prefixes: set[str], cited: set[str]) -> list:
    """The schedule rows naming the system's tags (or the rows the plan cited), each under its schedule's title,
    with that schedule's notes."""
    out: list = []
    title, rows, notes = None, [], []

    def flush():
        if rows:
            if title is not None:
                out.append(title)
            out.extend(rows)
            out.extend(notes)

    for sid, body in _entries(text):
        plain_body = _ENTRY_ID.sub("", body).strip()
        if sid is None:
            continue
        if plain_body.startswith(("Note:", "Unit controls by:")):
            notes.append((sid, body))
        elif "|" not in plain_body.split("\n", 1)[0]:
            flush()
            title, rows, notes = (sid, body), [], []
            if sid in cited:
                rows.append((None, ""))           # the plan cites the schedule itself: its notes too
        elif sid in cited or _names_any(plain_body.split("\n", 1)[0], tags, prefixes):
            rows.append((sid, body))
    flush()
    return [(sid, body) for sid, body in out if body]


def _holds(condition, evidence: str) -> bool:
    words = [w for place in ("schedule", "sequence", "notes", "prefix", "spec_overview")
             for w in getattr(condition, place)]
    return any(_word(w).search(evidence) for w in words)


def _left_out(template, kept, system, evidence: str) -> list[str]:
    """The Master Template's lines usually present for this system that the scope leaves out: its
    defaults, and a line whose conditions the evidence names."""
    have = {_plain(line.text) for line in kept}
    prefixes = {_tag_prefix(t) for t in expand_tags(system.tags)}
    missing, groups = [], set()
    for line in template.lines:
        if line.of and not prefixes & set(line.of):
            continue
        if "{" in line.text:
            continue
        if any(_holds(template.conditions[n], evidence) for n in line.unless):
            continue
        if line.choice:
            if line.choice in groups:
                continue
            groups.add(line.choice)
            members = [m for m in template.lines if m.choice == line.choice]
            if not any(_plain(m.text) in have for m in members):
                missing.append(" or ".join(m.text for m in members))
            continue
        expected = (all(_holds(template.conditions[n], evidence) for n in line.when) if line.when
                    else line.default)
        if expected and _plain(line.text) not in have:
            missing.append(line.text)
    return missing


def check_scope(system, scope, dossier, templates=None, style=None, sourced: bool = True
                ) -> tuple[list[CheckedLine], list[ReviewItem]]:
    """The lines kept, and the review. A line naming prices, hours, confidence or a category word,
    or breaking the house style, is dropped and listed. A line whose quote is not in the dossier is
    kept at confidence 0.5 at most, with a review line; a quote the judge read off a picture (its
    source is an image id) is accepted at 0.7 at most; every line of a system the plan cites no
    source for, at 0.4 at most. The Master Template's lines usually present that the AI left out
    are listed."""
    style = style or load_house_style()
    name = _name(system)
    review: list[ReviewItem] = []
    kept: list[CheckedLine] = []
    dropped: list[str] = []
    previous = 0
    for line in scope.lines:
        text = _squash(line.text)
        house = style.house_opening(text)      # "ATC Contractor to provide …" is "Furnish …"
        text = house if house is not None else text
        problem = ("it copies the specification's wording (“ATC Contractor to …”)" if house is None else
                   "it names prices, hours, confidence or the tool's own words" if _NEVER.search(text)
                   else style.check_line(text, line.depth))
        if problem:
            dropped.append(f"“{text}” ({problem})")
            continue
        depth = max(1, min(int(line.depth or 1), previous + 1))
        previous = depth
        quote = line.quote or ""
        sid = (source_ids(getattr(line, "source_id", "") or "") or [""])[0]
        picture = _is_picture(sid, dossier)
        if not picture:                       # a quote naming a picture by its job-wide id ("I15")
            named = next((i for i in source_ids(quote) if _is_picture(i, dossier)), "") if len(quote) <= 40 else ""
            picture, sid = (True, sid or named) if named else (False, sid)
        quoted = bool(quote) and (picture or quote_in_dossier(quote, dossier))
        confidence = max(0.0, min(float(line.confidence or 0.0), 1.0))
        if picture:
            confidence = min(confidence, PICTURE_CAP)
        quantity = line.quantity
        if not quoted:                        # a count given with a quote is kept; the quote goes to review
            confidence, quantity = min(confidence, UNQUOTED_CAP), (quantity if quote else None)
            review.append(ReviewItem(name, "", f"The quote for “{text}” is not in the job's documents",
                                     f"“{quote}”" if quote else "no quote", "Check the line by hand"))
        if not sourced:
            confidence = min(confidence, UNSOURCED_CONFIDENCE)
        kept.append(CheckedLine(text, depth, quantity, quote, sid, line.why or "", confidence, quoted))
    dropped += [_squash(str(r)) for r in getattr(scope, "refused", ()) or ()]     # thrown away by the judge
    if dropped:
        review.append(ReviewItem(name, "", "The AI wrote lines the client must never see, or that break the house "
                                 "style; they were dropped", "; ".join(dropped), "Nothing to do unless a line is missing"))
    template = system_template(system, templates)
    if template is not None:
        missing = _left_out(template, kept, system, system_evidence(system, dossier))
        if missing:
            review.append(ReviewItem(name, "", f"Usually present in the Master Template's {template.name}; the AI left "
                                     "out: " + "; ".join(missing), "", "Add any line the job needs"))
    for note in getattr(scope, "review_notes", ()) or ():      # the question cited the pictures by their job-wide ids
        review.append(ReviewItem(name, "", plain_ids(_squash(note), dossier), "the AI's note", ""))
    return kept, review


# --- C1: tech hours -------------------------------------------------------------------------------------------

_PUMP_NAME = re.compile(r"\b([A-Za-z][A-Za-z-]*)\s+pumps?\b", re.I)
_COUNTED_RULES = ("hardware_point", "line")


def hours_count(system, quantity: int | None) -> int | None:
    """The count a system's tech hours are counted on: its own quantity, except a single system whose
    header names several pumps ("Fire Pump Controller Monitoring (Fire Pump and Jockey Pump)"): its pumps."""
    names = {m.group(1).lower() for m in _PUMP_NAME.finditer(f"{system.header} {system.kind or ''}")}
    return len(names) if quantity == 1 and len(names) > 1 else quantity


def _hardware_point(text: str) -> bool:
    """A hardware point: a line furnishing a device or a wired point, never an integration line, an
    interlock, a note or a software point ("… Alarm at BMS")."""
    style = load_house_style()
    return (_hardware(text) and not style.is_trio(text) and style.line_group(text) != "integration"
            and not style.is_software_point(text))


def _counted_line(text: str, template) -> bool:
    """A line a "per line" rule counts: a hardware point, or one of the template's own counted lines
    ("Fire Pump & Jockey Pump Common Fault Alarm Monitoring")."""
    if _hardware_point(text):
        return True
    return any(line.quantity == "counted" and _plain(line.text) == _plain(text) for line in template.lines)


def _lines3(lines) -> list[tuple[str, int | None, int]]:
    return [(entry[0], entry[1], entry[2] if len(entry) > 2 else 1) for entry in lines]


def _hours(per: str, hours: float, of, count: int | None, lines, prefixes, primary: bool, template
           ) -> float | None:
    if per == "fixed":
        return hours
    if per == "hardware_point":
        return hours * sum(q or 0 for text, q, _ in lines if _hardware_point(text))
    if per == "line":        # each thing monitored: the system's own count, or more when its lines count more
        counted = sum(q or 0 for text, q, depth in lines if depth == 1 and _counted_line(text, template))
        return hours * max(count or 0, counted)
    if of and (not prefixes & set(of) if prefixes else not primary):
        return 0.0                                   # another family of the template (the outdoor units, say)
    return None if count is None else hours * count


def _rule_text(template) -> str:
    """The template's tech-hour rule in words: "16 h per unit", "none (4 h per unit when fan ddc)"."""
    parts = []
    for th in (template.tech_hours, *template.extra_tech_hours):
        per = th.per.replace("_", " ")
        base = "none" if th.hours is None else f"{th.hours:g} h per {per}"
        overrides = "; ".join(f"{hours:g} h per {per} when {' and '.join(c.replace('_', ' ') for c in conds)}"
                              for conds, hours in th.overrides)
        parts.append(base + (f" ({overrides})" if overrides else ""))
    return "; ".join(parts)


def tech_hour_rule(system, templates=None) -> str:
    """The nearest Master Template entry's tech-hour rule in words, for the judge's question:
    "Packaged ERU / RTU / AHU: 16 h per unit", or "none in the template"."""
    templates = templates if templates is not None else load_templates()
    template = _nearest_template(system, templates)
    if template is None:
        return "none in the template"
    rule = _rule_text(template)
    return f"{template.name}: {rule}" if re.search(r"\d", rule) else "none in the template"


def tech_hours(system, quantity: int | None, lines, hint, templates=None, evidence: str = ""
               ) -> tuple[float | None, ReviewItem | None]:
    """The system's tech hours and the review line they need. `lines` holds (text, quantity[, depth]) of
    the printed lines. The nearest Master Template entry's rule, applied to the system's own count (a rule
    per hardware point counts the hardware-point lines only; one per line, the monitored lines); a rule
    from an entry that is not the system's own is an ASSUMPTION. When the entry gives no rule, or there is
    no entry, there are no hours (never the AI's guess), with a review line to enter them. `hint`, the AI's
    suggestion, is never used for the hours."""
    templates = templates if templates is not None else load_templates()
    name = _name(system)
    prefixes = {_tag_prefix(t) for t in fold(system).parent}
    template = _nearest_template(system, templates)
    own = system_template(system, templates) is not None
    count = hours_count(system, quantity)
    rows = _lines3(lines)
    if template is not None:
        parts, counted = [], []
        for n, th in enumerate((template.tech_hours, *template.extra_tech_hours)):
            hours = th.hours
            for conditions, override in th.overrides:
                if all(_holds(template.conditions[c], evidence) for c in conditions):
                    hours = override
                    break
            value = None if hours is None else _hours(th.per, hours, th.of, count, rows, prefixes, n == 0, template)
            parts.append(value)
            counted.append(th.per in _COUNTED_RULES)
        nothing_counted = all(counted) and all(p == 0 for p in parts if p is not None)
        if parts and all(p is not None for p in parts) and not nothing_counted:
            total = float(sum(parts))
            if own:
                return total, None
            return total, ReviewItem(name, ASSUMPTION, f"Tech hours from the nearest Master Template entry, "
                                     f"{template.name}", f"{_rule_text(template)}; {total:g} h in all",
                                     "Confirm them")
        why = (f"The Master Template's {template.name} counts none of its lines" if nothing_counted
               and all(p is not None for p in parts) else
               f"The nearest Master Template entry, {template.name}, gives no hours for it ({_rule_text(template)})")
    else:
        why = "No Master Template entry is near it"
    return None, ReviewItem(name, "", f"No tech hours for {name} — enter them", why,
                            "Type the hours on the block's header row of the price sheet")


# --- what the judge is asked --------------------------------------------------------------------------------

def checklist_text(templates=None) -> str:
    """The Master Template's systems, one line each on when they apply, for the plan's prompt."""
    templates = templates if templates is not None else load_templates()
    lines = []
    for t in templates:
        applies = []
        if t.prefixes:
            applies.append("tags " + ", ".join(t.prefixes))
        if t.kinds:
            applies.append("also called " + ", ".join(t.kinds))
        hint = next((_squash(h).lstrip("*( ").rstrip(")") for h in t.hints
                     if h.strip() and not re.search(r"tech hour|\bhours?\b", h, re.I)), "")
        lines.append(f"- {t.name}" + (f" ({'; '.join(applies)})" if applies else "") + (f": {hint}" if hint else ""))
    return "\n".join(lines)


def template_options(system, templates=None) -> list[str]:
    """The nearest Master Template entry's lines, as a checklist of what is usually present."""
    templates = templates if templates is not None else load_templates()
    template = system_template(system, templates)
    if template is None:
        tags = expand_tags(system.tags)
        near = nearest_templates(system.kind or _name(system), _tag_prefix(tags[0]) if tags else "", templates, k=1)
        template = near[0] if near else None
    if template is None:
        return []
    return list(dict.fromkeys(line.text for line in template.lines))


def system_examples(system) -> list[dict]:
    """Blocks from past proposals for the same prefix or kind (up to 4)."""
    prefixes = list(dict.fromkeys(_tag_prefix(t) for t in expand_tags(system.tags)))
    return examples_for(prefixes, system.kind or _name(system), load_bank())


def system_pictures(system, dossier) -> list[tuple[str, object]]:
    """The dossier's pictures the plan cites for this system, each with its job-wide id ("I15" is the
    fifteenth): the write request cites them by these ids, never renumbered from I1."""
    images = list(dossier.images or ())
    wanted = [sid for sid in _system_ids(system) if sid.startswith("I")]
    for sid in _system_ids(system):
        wanted += re.findall(r"\bimage (I\d+)", cited_text(dossier, sid))
    out: list[tuple[str, object]] = []
    for sid in dict.fromkeys(wanted):
        n = int(sid[1:])
        if 1 <= n <= len(images) and all(images[n - 1] is not image for _, image in out):
            out.append((sid, images[n - 1]))
    return out


def system_images(system, dossier) -> list:
    """The dossier's pictures the plan cites for this system ("I3" is the third)."""
    return [image for _, image in system_pictures(system, dossier)]


# --- C2: the block header: never too long, never a pipe ---------------------------------------------------------

_TAG = r"[A-Z]{1,6}(?:-[A-Z0-9]+(?:\.\d+)?)+"
_TAG_RUN = re.compile(rf"(?<![A-Za-z0-9-])({_TAG}(?:\s*(?:,|&|\band\b|\bthru\b)\s*"
                      rf"(?:{_TAG}|\d+(?:\.\d+)?(?:-\d+(?:\.\d+)?)*[A-Z]?)(?![A-Za-z0-9-]))*)")   # "… thru 4-7"


class HeaderShape(NamedTuple):
    """How a planned system's header is printed: one header, or several stacked (one per family),
    each with its count, and the descriptors taken out of a header too long, as a note for the block's
    first line ("" when none). The last `folded` headers are the units the header folds in."""
    headers: tuple[str, ...]
    quantities: tuple
    note: str
    folded: int = 0


def _named_tags(text: str) -> list[str]:
    """The equipment tags a text names ("UH-1 thru 6", "RTU-4, 5", "RTU-3 only"), one by one, in capitals."""
    out: list[str] = []
    for m in _TAG_RUN.finditer(text or ""):
        out += expand_tags(re.sub(r"\s*(?:&|\band\b)\s*", ", ", m.group(1)))
    return list(dict.fromkeys(t.upper() for t in out))


def _base_name(system) -> str:
    """The plan's header without its count, with the tags when it names none: only the equipment tags, never the
    rooms or names the plan listed as tags (they go in a "(Location: …)" line)."""
    base = _name(system)
    tags = expand_tags(system.tags)
    if tags and not any(t.upper() in base.upper() for t in (tags[0], *system.tags[:1])):
        own = [t for t in tags if is_equipment_tag(t)]
        if own:
            base = f"{base} {tag_list(own)}"
    return base


def _count(quantity) -> str:
    return COUNT_TO_FILL if quantity is None else str(quantity)


def _split_kind(name: str) -> tuple[str, str]:
    """(the words before the first tag, the rest)."""
    m = _TAG_RUN.search(name)
    if m is None:
        return name, ""
    return name[:m.start()].strip(" -–,"), name[m.start():]


def _strip_descriptors(name: str) -> tuple[str, list[str]]:
    """The header without the words after " w/ " and without its brackets, and what was taken out. The tags
    those words name stay in the header: a tag list is never moved into a note."""
    found = []
    m = re.search(r"\s+w/\s*(.+)$", name, re.I)
    if m:
        after = m.group(1)
        runs = [r.group(1) for r in _TAG_RUN.finditer(after)]
        found.append(_squash(_TAG_RUN.sub(" ", after)).strip(" ,&-–"))
        name = name[:m.start()] + (" " + ", ".join(runs) if runs else "")
    found += [p.strip() for p in re.findall(r"\(([^()]*)\)", name) if not _TAG_RUN.search(p)]
    name = re.sub(r"\s*\((?![^()]*" + _TAG + r")[^()]*\)", "", name)
    return _squash(name).strip(" -–,"), [f for f in found if f]


def _by_family(kind: str, tags: list[str], quantity) -> list[tuple[str, object]]:
    """One header per family (tag prefix), stacked. A family is never cut in two, however long its header."""
    families: list[list[str]] = []
    for tag in tags:
        if families and _tag_prefix(families[-1][-1]) == _tag_prefix(tag):
            families[-1].append(tag)
        else:
            families.append([tag])
    return [(f"{kind} {tag_list(family)}", None if quantity is None else len(family)) for family in families]


def _compact(name: str, tags: list[str]) -> str:
    """The header with each run of tags it names written the house way ("VAV-4-1 thru 7, VAV-5-1 thru 8")."""
    def compact(m: re.Match) -> str:
        named = _named_tags(m.group(1))
        own = [t for t in tags if t.upper() in set(named)] or named
        return tag_list(own) if len(own) > 1 else m.group(1)
    return _squash(_TAG_RUN.sub(compact, name))


def _fit(name: str, tags: list[str], quantity, moved: list[str]) -> list[tuple[str, object]]:
    """A header piece made to fit: the tags compacted, then the descriptors dropped (into the block's first
    note), then, for several families, one header per family. The tags are never cut: a header of one family
    still too long is printed whole. Each is (the header without its count, the count)."""
    if len(name) <= MAX_HEADER:
        return [(name, quantity)]
    name = _compact(name, tags)
    if len(name) <= MAX_HEADER:
        return [(name, quantity)]
    stripped, found = _strip_descriptors(name)
    if found:
        moved.extend(found)
        name = _compact(stripped, tags)
        if len(name) <= MAX_HEADER:
            return [(name, quantity)]
    kind, _ = _split_kind(name)
    own = [t for t in tags if t.upper() in set(_named_tags(name))] or tags
    if kind and len({_tag_prefix(t) for t in own}) > 1:
        return _by_family(kind, own, quantity)
    return [(name, quantity)]


@lru_cache(maxsize=1)
def _equipment_names() -> dict[str, str]:
    from estimator.catalogue.tags import Equipment
    return {k.upper(): v for k, v in Equipment.load().prefixes.items()}


def _with_kind(piece: str, kind: str) -> str:
    """The header piece with the equipment's name before its tags ("CU-1, 2" is "Condensing Unit CU-1, 2"): the
    name equipment.json gives the tag's prefix, else the plan's kind."""
    words, rest = _split_kind(piece)
    if words or not rest:
        return piece
    name = _equipment_names().get(_tag_prefix(rest)) or _squash(kind)
    return f"{name} {piece}" if name else piece


def header_tags(header: str) -> list[str]:
    """The tags a printed header lists, one by one."""
    return _named_tags(re.sub(r"^\s*Qty\s*\([^)]*\)\s*", "", header or ""))


def _piece_tags(piece: str, tags: list[str]) -> list[str]:
    named = set(_named_tags(piece))
    own = [t for t in tags if t.upper() in named]
    if own:
        return own
    return [t for t in tags if re.search(rf"(?<![A-Za-z]){re.escape(_tag_prefix(t))}-", piece)]


def shape_header(system, quantity) -> HeaderShape:
    """The system's block header(s), in the house style: "Qty (3) Rooftop Unit RTU-1 thru 3", "Qty (##) …"
    when the count is still to fill. A pipe never goes in a header: two families are two stacked headers.
    A header longer than a block header drops the words after " w/ " and its brackets (they go into the
    block's first line, as a note), and when it is still too long, it is one header per family, stacked.
    The units a header folds in after " w/ " (tagged ones) get their own stacked header, with their count."""
    folding = fold(system)
    if folding.folded:
        return _folded_shape(system, quantity, folding)
    name = _base_name(system)
    tags = equipment_tags(system)          # a room or a name listed as a tag is never a header of its own
    pieces = [p.strip() for p in name.split("|") if p.strip()] or [name]
    headers, quantities, moved = [], [], []
    for piece in pieces:
        own = _piece_tags(piece, tags) if len(pieces) > 1 else tags
        q = len(own) if len(pieces) > 1 and own and quantity is not None else quantity
        for text, n in _fit(_with_kind(piece, system.kind or ""), own, q, moved):
            headers.append(_squash(f"Qty ({_count(n)}) {text}"))
            quantities.append(n)
    note = ("**Includes " + "; ".join(moved)) if moved else ""
    return HeaderShape(tuple(headers), tuple(quantities), note)


def _folded_shape(system, quantity, folding: Fold) -> HeaderShape:
    """The parent's header (its words before " w/ ", with its own tags), then one per folded family."""
    base = re.split(r"\s+w/\s*", _name(system), maxsplit=1, flags=re.I)[0].strip()
    parent = list(folding.parent)
    if parent and not any(t.upper() in set(_named_tags(base)) for t in parent):
        base = f"{base} {tag_list(parent)}"
    headers, quantities, moved = [], [], []
    for text, n in _fit(base, parent, quantity, moved):
        headers.append(_squash(f"Qty ({_count(n)}) {text}"))
        quantities.append(n)
    count = 0
    for kind, tags in folding.folded:
        for text, n in _fit(f"{kind} {tag_list(list(tags))}", list(tags), len(tags), moved):
            headers.append(_squash(f"Qty ({_count(n)}) {text}"))
            quantities.append(n)
            count += 1
    note = ("**Includes " + "; ".join(moved)) if moved else ""
    return HeaderShape(tuple(headers), tuple(quantities), note, count)


def block_header(system, quantity) -> str:
    """"Qty (3) Variable Air Volume Box VAV-1 thru 3": the system's first header."""
    return shape_header(system, quantity).headers[0]


# --- C2: a line's quantity comes from the line; the house-style polish ----------------------------------------

_QTY_IN_LINE = re.compile(r"\bQty\.?\s*\(?\s*(\d+)\s*\)?", re.I)
_LOCATION = re.compile(r"\(Location:\s*([^)]*)\)", re.I)
_ROOM_WORDS = frozenset("room rooms office garage closet lobby corridor gym gymnasium toilet restroom kitchen lab "
                        "laboratory classroom vestibule stair stairs storage laundry lounge locker shaft suite "
                        "library cafeteria auditorium hall".split())
_POINT_CODE = re.compile(r"\s*\((?:AO|DO|AI|DI|BO|BI)\)")
_AS_PER_SEQUENCE = re.compile(r"\s*\(as per sequence\)\s*$", re.I)


def _location_items(text: str) -> list[str]:
    m = _LOCATION.search(text or "")
    return [i.strip() for i in re.split(r",|&|\band\b", m.group(1)) if i.strip()] if m else []


def _places_of(text: str) -> frozenset[str]:
    """The places a line's "(Location: …)" names; none for "(Location: Each Box)", which is every unit."""
    items = _location_items(text)
    if any(re.search(r"\b(?:each|all|every)\b", i, re.I) for i in items):
        return frozenset()
    return frozenset(_plain(i) for i in items)


def _is_room(item: str) -> bool:
    words = _plain(item).split()
    return bool(re.search(r"\b\d+[A-Za-z]?\b", item)) or any(w in _ROOM_WORDS for w in words)


def _rooms(text: str) -> list[str]:
    """The rooms a line lists in its "(Location: …)", when it is a list of two or more rooms, or one room
    with its number ("Fire Pump Room (Location: Room 008)")."""
    items = _location_items(text)
    if not items or any(re.search(r"\b(?:each|all|every)\b", i, re.I) for i in items):
        return []
    if len(items) == 1:
        return items if re.search(r"\b\d+[A-Za-z]?\b", items[0]) and _is_room(items[0]) else []
    return items if all(_is_room(i) for i in items) else []


def _line_count(text: str, quote: str, ai_quantity, system, quantity) -> tuple[int | None, bool]:
    """(the line's count, whether it is the line's own count rather than the system's)."""
    m = _QTY_IN_LINE.search(text or "")
    if m:
        return int(m.group(1)), True
    if ai_quantity is not None:
        return ai_quantity, True
    folding = fold(system)
    folded = {t.upper() for _, tags in folding.folded for t in tags}
    if folded:
        named = [t for t in _named_tags(text) if t in folded]
        if named:
            return len(named), True                       # a line for the units the header folds in
    tags = [t.upper() for t in folding.parent]
    if len(tags) > 1 and (quantity is None or quantity == len(tags)):
        named = [t for t in _named_tags(text) if t in set(tags)]
        if named and len(named) < len(tags):
            return len(named), True
    rooms = _rooms(text)
    if rooms:
        return len(rooms), True
    return quantity, False


def line_quantity(text: str, quote: str, ai_quantity, system, quantity) -> int | None:
    """A line's quantity, from the line: the count it states ("(Qty. 9 Total)"), the AI's count when its
    quote states it, the subset of the system's tags it names ("UH-7", "RTU-3 only"), the rooms it lists;
    else the system's quantity (None: the count is still to fill)."""
    return _line_count(text, quote, ai_quantity, system, quantity)[0]


@lru_cache(maxsize=1)
def _template_texts() -> frozenset[str]:
    texts = {_plain(line.text) for t in load_templates() for line in t.lines}
    data = _front_end_data(FRONT_END_FILE)
    for variant in data.get("variants", {}).values():
        for line in variant:
            texts.add(_plain(line.get("text", "")))
            texts.update(_plain(sub) for sub in line.get("lines", ()))
    return frozenset(texts)


def polish_line(text: str) -> list[str]:
    """The house-style polish: no point-type code ("(AO)"), no trailing "(as per sequence)" unless the line
    is the template's own, a line joining two actions with ";" split into two lines, and a Master Template
    line in the template's own capitals ("AME requires mfr. Rep to assist in integration, …")."""
    text = _squash(_POINT_CODE.sub("", text or ""))
    if _plain(text) not in _template_texts():
        text = _AS_PER_SEQUENCE.sub("", text).strip()
    style = load_house_style()
    parts = [p.strip() for p in text.split(";")]
    if len(parts) > 1 and all(p and (style.verb(p) or style.starts_without_verb(p)) for p in parts):
        return [style.template_form(p) for p in parts]
    return [style.template_form(text)]


# --- C2: a system whose lines were all refused ---------------------------------------------------------------

_REFUSED = re.compile(r"^[“\"](?P<text>.+?)[”\"]\s*(?:—|-|\()\s*(?P<why>.*)$")


def _nearest_template(system, templates):
    template = system_template(system, templates)
    if template is None:
        tags = expand_tags(system.tags)
        near = nearest_templates(system.kind or _name(system), _tag_prefix(tags[0]) if tags else "", templates, k=1)
        template = near[0] if near else None
    return template


def _template_defaults(template, system, evidence: str) -> list[tuple[str, int]]:
    """The Master Template's lines usually present for the system: its defaults and the lines whose
    conditions the evidence names, one of each choice, in the template's order."""
    prefixes = {_tag_prefix(t) for t in expand_tags(system.tags)}
    out, groups = [], set()
    for line in template.lines:
        if line.of and prefixes and not prefixes & set(line.of):
            continue
        text = _squash(line.text.replace("{what} ", "").replace(" {what}", ""))
        if "{" in text:
            continue
        if any(_holds(template.conditions[n], evidence) for n in line.unless):
            continue
        if line.choice:
            if line.choice in groups:
                continue
            groups.add(line.choice)
            out.append((text, line.depth))
            continue
        expected = (all(_holds(template.conditions[n], evidence) for n in line.when) if line.when
                    else line.default)
        if expected:
            out.append((text, line.depth))
    return out


def _rewritten(refused) -> list[str]:
    """The refused lines that lacked only a verb, with one added: "Wire …" for a device furnished by
    others, else "Furnish …". A line refused for anything else stays out."""
    out = []
    for entry in refused or ():
        m = _REFUSED.match(_squash(str(entry)))
        if m is None or "verb" not in m.group("why"):
            continue
        text = m.group("text").strip()
        style = load_house_style()
        if style.is_spec_wording(text):
            house = style.house_opening(text)
            if house is None:
                continue                      # spec wording with no house verb: it stays out
            text = house
        else:
            verb = "Wire" if re.search(r"\(Furnished by", text, re.I) else "Furnish"
            text = f"{verb} {text}"
        if load_house_style().check_line(text, 1) is None and not _NEVER.search(text):
            out.append(text)
    return out


def _fallback(system, scope, dossier, templates) -> tuple[list[CheckedLine], str]:
    """The lines a system is printed with when the AI wrote none that could be used: the nearest Master
    Template entry's usual lines, else the refused lines rewritten with a verb. (lines, where they came from)."""
    template = _nearest_template(system, templates)
    if template is not None:
        lines = _template_defaults(template, system, system_evidence(system, dossier))
        if lines:
            why = f"the Master Template's {template.name} line"
            return [CheckedLine(text, depth, None, "", "", why, _EVIDENCE_CONFIDENCE[ASSUMPTION], False,
                                "the Master Template (fallback)")
                    for text, depth in lines], f"the Master Template's {template.name} lines"
    texts = _rewritten(getattr(scope, "refused", ()) if scope is not None else ())
    why = "the AI's line, refused for want of a verb, rewritten with one"
    return ([CheckedLine(t, 1, None, "", "", why, _EVIDENCE_CONFIDENCE[ASSUMPTION], False,
                         "the Master Template (fallback)") for t in texts],
            "the AI's refused lines, rewritten with a verb" if texts else "no line at all")


# --- C2: one device, one place ----------------------------------------------------------------------------------

_DEVICE_STOP = frozenset("furnish install and wire the a an of for to with at in on each new per provided by unit "
                         "mfr furnished others qty total location via".split())
_QUALIFIERS = frozenset("space room dedicated high low alarm alarms temp monitoring bms remote".split())


def _singular(word: str) -> str:
    return word[:-1] if len(word) > 3 and word.endswith("s") and not word.endswith("ss") else word


def _device_words(text: str) -> frozenset[str]:
    """The device a line names, as words: its brackets, its dash clause, the verbs and the words that only
    qualify it (space, room, high, low, alarm …) left out."""
    text = re.sub(r"\([^)]*\)", " ", text or "")
    text = re.sub(r"\s+[–-]\s+.*$", " ", text)
    return frozenset(_singular(w) for w in _plain(text).split()
                     if w not in _DEVICE_STOP and w not in _QUALIFIERS and not w.isdigit())


def _room_keys(text: str, children=()) -> frozenset[str]:
    """The rooms a line is for: the numbers (else the names) its "(Location: …)" lists, and for each
    sub-line naming a room ("Fire Pump Room (Location: Room 008)"), its name and number."""
    keys = set()
    for item in _location_items(text):
        numbers = re.findall(r"\b(\d+[A-Za-z]?)\b", item)
        keys.update(n.lower() for n in numbers) if numbers else keys.add(_plain(item))
    for child in children:
        items = _location_items(child)
        if not items:
            continue                                 # a sub-line naming no room is not a room
        name = _plain(re.sub(r"\([^)]*\)", " ", child))
        if name:
            keys.add(name)
        for item in items:
            keys.update(n.lower() for n in re.findall(r"\b(\d+[A-Za-z]?)\b", item))
    return frozenset(keys)


def _names_all(evidence: str, rooms: frozenset[str], tags: frozenset[str]) -> bool:
    plain = f" {_plain(evidence)} "
    wanted = rooms or {t.lower() for t in tags}
    return bool(wanted) and all(f" {_plain(w)} " in plain for w in wanted)


def _heads(kept: list) -> list[tuple[object, list]]:
    """Each top line with its sub-lines."""
    out: list[tuple[object, list]] = []
    for line in kept:
        if line.depth > 1 and out:
            out[-1][1].append(line)
        else:
            out.append((line, []))
    return out


def _shared_line(text: str) -> bool:
    """An integration line every system with factory controls carries: never one device in two places."""
    style = load_house_style()
    return style.is_trio(text) or style.line_group(text) == "integration"


def _one_place(entries: list, dossier) -> None:
    """The same device named for the same rooms or tags in two systems is kept in the system whose cited
    evidence names them (when both do, the one whose own name names the device, then the one that lists
    the rooms line by line), and taken out of the other with its sub-lines, with a review line there.
    `entries` holds [system, kept lines, review] in the plan's order; they are changed in place."""
    evidence = {}
    for i in range(len(entries)):
        for j in range(i + 1, len(entries)):
            system, other = entries[i][0], entries[j][0]
            for a, a_children in _heads(entries[i][1]):
                for b, b_children in _heads(entries[j][1]):
                    if a not in entries[i][1] or b not in entries[j][1] or _shared_line(a.text) \
                            or _shared_line(b.text):
                        continue
                    wa, wb = _device_words(a.text), _device_words(b.text)
                    if not (wa and wb and (wa <= wb or wb <= wa)):
                        continue
                    ra = _room_keys(a.text, [c.text for c in a_children])
                    rb = _room_keys(b.text, [c.text for c in b_children])
                    ta, tb = frozenset(_named_tags(a.text)), frozenset(_named_tags(b.text))
                    rooms = bool(ra and rb and (ra <= rb or rb <= ra))
                    if not (rooms or (not ra and not rb and ta and ta == tb)):
                        continue
                    wanted = (ra & rb) if rooms else frozenset()
                    for s in (system, other):
                        if s.key not in evidence:
                            evidence[s.key] = system_evidence(s, dossier)

                    def score(s, children):
                        named = _names_all(evidence[s.key], wanted, ta)
                        own_name = bool(set(_plain(f"{s.header} {s.kind}").split()) & (wa | wb))
                        return named, own_name, bool(children)

                    first, second = score(system, a_children), score(other, b_children)
                    keep_first = first >= second
                    winner, loser, line, children, at = ((system, other, b, b_children, j) if keep_first
                                                         else (other, system, a, a_children, i))
                    what = ", ".join(sorted(wanted or ta))
                    for gone in (line, *children):
                        entries[at][1].remove(gone)
                    kept_score = first if keep_first else second
                    why = ("its evidence names them" if kept_score[0] else
                           "neither system's evidence names them, so it stays where the plan lists it first")
                    if kept_score[0] and kept_score[1] and (second if keep_first else first)[0]:
                        why = "both name them; it is the system for that device"
                    entries[at][2].append(ReviewItem(
                        _name(loser), "", f"“{line.text}” was named in both {_name(loser)} and {_name(winner)}; kept "
                        f"in {_name(winner)} — {why}", f"One device, one place: {what}",
                        "Move it back if it belongs here", tier=TIER_DISAGREE))


# --- C2: the job from the plan -------------------------------------------------------------------------------

_FRONT_END_KEY = "Front end"
_GLOBAL_POINTS = "Global Points"
_WARRANTY = "Extended Warranty"
_ADDED_CONFIDENCE = 0.7
_EXCEPTION_CONFIDENCE = 0.8
_EVIDENCE_CONFIDENCE = {CONFIRMED: 0.8, ASSUMPTION: 0.5, PENDING: 0.0}
_MFR = re.compile(r"\s*(?:,\s*)?(?:(?:is|are|to be|will be)\s+)?(?:furnished\s+|provided\s+|supplied\s+)?by\s+"
                  r"(?:the\s+)?(?:unit\s+)?(?:mfr\.?|manufacturer)\b.*$", re.I)
_MFR_TOPICS = ("leak detect", "transformer", "integral thermostat", "airflow station", "airflow measuring",
               "air flow station", "air flow measuring")
_LINE_STOP = frozenset("the a an of for to with at in on and each new per via by from between its".split())


@dataclass
class _Row:
    """One scope line of a system, before a block's lines are merged, ordered and printed."""
    line: CheckedLine
    q: int | None
    own: bool                   # the line's own count, not the system's
    tags: frozenset             # the tags the AI's line named: duplicates naming different tags add their counts
    units: int | None           # the system's quantity: a total that is not one a unit is printed "(Qty. N Total)"
    system: str                 # the system's name, for the Evidence Package
    hours: float | None = None  # the line's tech hours, for a rule per hardware point
    folded: bool = False        # a line for the units the header folds in: printed after the parent's


@dataclass
class _Part:
    """One planned system, written: its headers, lines and notes, before a group's headers are stacked."""
    system: object
    headers: tuple
    rows: list
    notes: list                 # the client notes printed, in order
    includes: str               # "**Includes …": the words taken out of a header too long ("" when none)
    review: list
    hours: float | None
    printed: bool = True

    @property
    def header(self) -> str:
        return self.headers[0]


def _where(dossier, sid: str) -> str:
    return (dossier.sources or {}).get(sid, "") if sid else ""


def _source(sid: str) -> str:
    return f"{SOURCE} [{sid}]" if sid else SOURCE


def _by_unit_mfr(note: str, evidence: str, pictured: bool) -> str | None:
    """The standing house rule: a note giving a device to the unit manufacturer (leak detection, a
    transformer, an integral thermostat, an airflow station) is the house's "*… BY UNIT MFR." note, when
    the evidence names the device or the system rests on a picture."""
    low = note.lower()
    topic = next((t for t in _MFR_TOPICS if t in low), None)
    if topic is None or not _MFR.search(note.lstrip("*")):
        return None
    if not (pictured or topic.split()[0] in evidence.lower()):
        return None
    subject = _MFR.sub("", note.lstrip("*")).strip(" ,.-–")
    return f"*{subject.upper()} BY UNIT MFR." if subject else None


def _client_note(note: str, evidence: str, pictured: bool, style) -> tuple[str, str | None]:
    """(the note as printed, why it cannot be printed or None). A long note giving a device to the unit
    ("… are coming with the unit per equipment schedule") takes the short house form "*<ITEM> BY UNIT MFR."."""
    house = _by_unit_mfr(note, evidence, pictured)
    if house is not None:
        return house, style.forbidden(house)
    item = style.by_unit_mfr_item(note) if len(note) > style.long_note else None
    if item:
        words = [w for w in _plain(item).split() if len(w) >= 4]
        have = set(_plain(evidence).split())
        borne = pictured or (words and sum(w in have for w in words) * 2 >= len(words))
        short = style.short_note(note)
        too_long = f"it is longer than {style.max_line_length} characters" if len(short) > style.max_line_length else None
        return short, style.forbidden(short) or too_long or (None if borne else "the evidence does not bear it out")
    on_picture = pictured and re.search(r"schedul", note, re.I)          # it rests on the schedule's picture
    problem = style.check_note(note) or (None if _note_is_borne_out(note, evidence) or on_picture
                                         else "the evidence does not bear it out")
    return note, problem


# --- a block's lines: one of each, in the house order, with their totals ----------------------------------------

def _opening(text: str, style) -> str:
    verb = style.verb(text)
    if verb:
        return verb.lower()
    low = _squash(text).lower()
    start = next((s for s in sorted(style.openings, key=len, reverse=True) if low.startswith(s.lower() + " ")),
                 None)
    return start.lower() if start else (low.split(" ", 1)[0] if low else "")


def _same_opening(a: str, b: str, style) -> bool:
    """The same verb, or openings of one family (an interlock and low-voltage wiring)."""
    oa, ob = _opening(a, style), _opening(b, style)
    families = style.same_opening or {}
    return oa == ob or (oa in families and families.get(oa) == families.get(ob))


def _line_words(text: str, style) -> frozenset[str]:
    """A line's words for finding a near-duplicate: without its opening, its brackets, its tags and the
    small words; plurals as singulars."""
    text = _squash(text)
    text = text[len(_opening(text, style)):] if text.lower().startswith(_opening(text, style)) else text
    text = re.sub(r"\([^)]*\)", " ", text)
    text = _TAG_RUN.sub(" ", text)
    return frozenset(_singular(w) for w in _plain(text).split() if w not in _LINE_STOP)


def same_line(a: str, b: str, style=None) -> bool:
    """Two scope lines that say the same thing: the same verb and at least 70 % of their words shared."""
    style = style or load_house_style()
    if _plain(a) == _plain(b) or style.same_start(a, b):
        return True
    la, lb = _places_of(a), _places_of(b)
    if (la or lb) and la != lb:
        return False                        # one device in two places (or one line for some rooms) is two lines
    if not _same_opening(a, b, style):
        return False
    wa, wb = _line_words(a, style), _line_words(b, style)
    return bool(wa and wb) and len(wa & wb) / len(wa | wb) >= style.duplicate_share


def _natural_key(tag: str) -> list:
    return [(0, int(p), "") if p.isdigit() else (1, 0, p) for p in re.split(r"(\d+)", tag)]


def _retag(text: str, tags: frozenset) -> str:
    """The line with its tag list naming all of `tags`."""
    m = _TAG_RUN.search(text)
    if m is None:
        return text
    return text[:m.start()] + tag_list(sorted(tags, key=_natural_key)) + text[m.end():]


def _states_total(row: _Row) -> bool:
    """The line states its own total ("(Qty. 9 Total)"): a total is never stripped by keeping the other line."""
    return bool(_QTY_IN_LINE.search(row.line.text))


def _better(a: _Row, b: _Row) -> bool:
    """a has the better evidence (its quote found, then a total it states, then its confidence); on a tie, the one
    saying more."""
    return ((a.line.quoted, _states_total(a), a.line.confidence, len(a.line.text))
            >= (b.line.quoted, _states_total(b), b.line.confidence, len(b.line.text)))


def _combine(keep: _Row, drop: _Row) -> _Row:
    """Two duplicates as one: the better line; their counts added only when they name different tags."""
    if keep.tags and drop.tags and keep.tags.isdisjoint(drop.tags) and keep.q is not None and drop.q is not None:
        union = frozenset(keep.tags | drop.tags)
        line = dataclasses.replace(keep.line, text=_retag(keep.line.text, union))
        hours = None if keep.hours is None and drop.hours is None else (keep.hours or 0) + (drop.hours or 0)
        return dataclasses.replace(keep, line=line, q=keep.q + drop.q, tags=union, hours=hours)
    if keep.q is None and drop.q is not None:
        return dataclasses.replace(keep, q=drop.q, own=drop.own, hours=drop.hours)
    return keep


def _group_rows(rows: list[_Row]) -> list[list[_Row]]:
    """Each top line with its sub-lines."""
    groups: list[list[_Row]] = []
    for row in rows:
        if row.line.depth > 1 and groups:
            groups[-1].append(row)
        else:
            groups.append([row])
    return groups


def _logged(keep: _Row, drop: _Row, log: list | None) -> None:
    """A line merged into another is listed for review, unless it repeated it word for word or the two named
    different tags (they are one line naming both)."""
    if log is None or _plain(keep.line.text) == _plain(drop.line.text):
        return
    if keep.tags and drop.tags and keep.tags.isdisjoint(drop.tags):
        return
    log.append((drop, keep))


def _dedupe_flat(rows: list[_Row], style, log: list | None = None) -> list[_Row]:
    out: list[_Row] = []
    for row in rows:
        at = next((k for k, o in enumerate(out) if o.line.depth == row.line.depth
                   and same_line(o.line.text, row.line.text, style)), None)
        if at is None:
            out.append(row)
        else:
            keep, drop = (out[at], row) if _better(out[at], row) else (row, out[at])
            _logged(keep, drop, log)
            out[at] = _combine(keep, drop)
    return out


def _dedupe_groups(groups: list[list[_Row]], style, log: list | None = None) -> list[list[_Row]]:
    """Within a block, lines that say the same thing with the same verb are one line (the one with the best
    evidence, their sub-lines together). `log` gathers (the line dropped, the line kept)."""
    out: list[list[_Row]] = []
    for group in groups:
        head = group[0]
        at = next((k for k, o in enumerate(out) if o[0].line.depth == head.line.depth
                   and same_line(o[0].line.text, head.line.text, style)), None)
        if at is None:
            out.append([head] + _dedupe_flat(group[1:], style, log))
            continue
        old = out[at]
        keep, drop = (old, group) if _better(old[0], head) else (group, old)
        if style.is_trio(drop[0].line.text) and not style.is_trio(keep[0].line.text):
            keep, drop = drop, keep            # two "Map Available Points …" lines: the house's own form stays
        _logged(keep[0], drop[0], log)
        children = _dedupe_flat(keep[1:] + drop[1:], style, log)
        children.sort(key=lambda r: style.is_trio(r.line.text))        # "AME requires …" last
        out[at] = [_combine(keep[0], drop[0])] + children
    return out


# --- a block's repeats by meaning: each line as (device, action) ---------------------------------------------------

_LIST_SPLIT = re.compile(r",|&|\band\b", re.I)
_PARTNER_SPLIT = re.compile(r",|&|\b(?:between|with|to|and|from)\b", re.I)


def _action(row: _Row, style) -> str | None:
    """The line's action (furnish, install, wire, monitor, interlock), one per family: a sub-line with no verb is
    a point, furnished. None for a line that is neither (a note-like line, "AME requires …")."""
    text = _squash(row.line.text)
    low = text.casefold()
    family = style.same_action or {}
    for opening, action in style.repeat_actions:
        if low.startswith(opening + " "):
            return family.get(action, action)
    if row.line.depth > 1 and not style.verb(text) and not style.starts_without_verb(text):
        return family.get("furnish", "furnish")
    return None


def _meaning_words(text: str, style, ignore: frozenset) -> frozenset[str]:
    """A device's words: each tag prefix written as the equipment's name ("EDH" is "electric duct heater"), without
    its tags, the small words and the words the house reads it without."""
    names = _equipment_names()
    words: list[str] = []
    for token in re.findall(r"[A-Za-z0-9]+", _TAG_RUN.sub(" ", text or "")):
        expanded = names.get(token) if token.isupper() and len(token) > 1 else None
        words += _plain(expanded).split() if expanded else [token.casefold()]
    return frozenset(_singular(w) for w in words if w not in _LINE_STOP and w not in ignore and not w.isdigit())


def _devices(row: _Row, style) -> frozenset[frozenset[str]]:
    """The devices a line names ("Fan VFD Speed Control, VFD Speed Feedback and VFD Fault" is three)."""
    device = style._device(row.line.text)
    items = (_meaning_words(piece, style, style.repeat_ignore) for piece in _LIST_SPLIT.split(device))
    return frozenset(i for i in items if i)


def _own_unit(row: _Row, style) -> frozenset[str]:
    return _meaning_words(re.sub(r"\([^)]*\)", " ", row.system), style, style.repeat_ignore | style.partner_ignore)


def _partners(row: _Row, style) -> list[frozenset[str]]:
    """What an interlock ties together; when it names one thing, the unit it is written for is the other."""
    text = re.sub(r"\([^)]*\)", " ", _squash(row.line.text))
    text = re.sub(r"\s+[–-]\s+.*$", " ", text)
    low = text.casefold()
    opening = next((o for o, _ in style.repeat_actions if low.startswith(o + " ")), "")
    ignore = style.repeat_ignore | style.partner_ignore
    out = [w for w in (_meaning_words(p, style, ignore) for p in _PARTNER_SPLIT.split(text[len(opening):])) if w]
    if len(out) == 1:
        own = _own_unit(row, style)
        if own and not any(own <= w or w <= own for w in out):
            out.append(own)
    return out


def _same_partners(a: list, b: list) -> bool:
    def near(x, y):
        return x <= y or y <= x
    return (bool(a) and len(a) == len(b) and all(any(near(x, y) for y in b) for x in a)
            and all(any(near(y, x) for x in a) for y in b))


def _repeat(x: _Row, y: _Row, style) -> str | None:
    """How line x repeats line y: "same" (one device, one action), "x" (y lists all of x's devices and more), "y"
    (the other way), or None. Never lines naming different tags, different locations or different totals."""
    ax, ay = _action(x, style), _action(y, style)
    if ax is None or ax != ay:
        return None
    for row in (x, y):
        text = _squash(row.line.text)
        if style.is_trio(text) and not style.verb(text) or any(
                text.casefold().startswith(s.casefold()) for s in style.same_line_starts):
            return None                        # "Map Available Points …", "AME requires …": the house's own lines
    if x.tags and y.tags and x.tags != y.tags:
        return None
    lx, ly = _places_of(x.line.text), _places_of(y.line.text)
    if (lx or ly) and lx != ly:
        return None
    qx, qy = _QTY_IN_LINE.search(x.line.text), _QTY_IN_LINE.search(y.line.text)
    if qx and qy and qx.group(1) != qy.group(1):
        return None
    if ax == (style.same_action or {}).get("interlock", "interlock"):
        return "same" if _same_partners(_partners(x, style), _partners(y, style)) else None
    dx, dy = _devices(x, style), _devices(y, style)
    if not dx or not dy:
        return None
    if dx == dy:
        return "same"
    return "x" if dx < dy else "y" if dy < dx else None


def _drop_repeats(groups: list[list[_Row]], style) -> tuple[list[list[_Row]], list[tuple[_Row, _Row]]]:
    """Within a block, a line whose (device, action) is already there is dropped: the one with the stronger evidence
    stays (a line listing more devices stays over the one it covers). A dropped line's sub-lines go under the line
    kept. Returns the groups and each (line dropped, line kept)."""
    groups = [list(g) for g in groups]
    gone: list[tuple[_Row, _Row]] = []
    while True:
        rows = [(gi, ri) for gi, g in enumerate(groups) for ri in range(len(g))]
        found = None
        for b in range(len(rows)):
            for a in range(b):
                (ga, ra), (gb, rb) = rows[a], rows[b]
                x, y = groups[ga][ra], groups[gb][rb]
                how = _repeat(x, y, style)
                if how is None:
                    continue
                drop_x = how == "x" or (how == "same" and not _better(x, y))
                drop, keep = ((ga, ra), (gb, rb)) if drop_x else ((gb, rb), (ga, ra))
                if drop[1] == 0 and len(groups[drop[0]]) > 1 and keep[1] > 0:
                    if keep[0] == drop[0]:
                        continue                       # a line and its own sub-line
                    drop, keep = keep, drop            # a line with sub-lines stays over a sub-line
                found = drop, keep
                break
            if found:
                break
        if found is None:
            return [g for g in groups if g], gone
        (gd, rd), (gk, rk) = found
        dropped, kept = groups[gd][rd], groups[gk][rk]
        gone.append((dropped, kept))
        if rd == 0:
            children = groups[gd][1:]
            groups[gd] = []
            if children:
                groups[gk].extend(children)
                head, rest = groups[gk][0], groups[gk][1:]
                rest.sort(key=lambda r: style.is_trio(r.line.text))
                groups[gk] = [head] + rest
        else:
            groups[gd].pop(rd)
        if kept.q is None and dropped.q is not None:
            groups[gk][groups[gk].index(kept)] = dataclasses.replace(kept, q=dropped.q, own=dropped.own)


def _house_order(groups: list[list[_Row]], style) -> list[list[_Row]]:
    """The house order: controller, sensors, points, valves and dampers, integration. A line no group's words
    are in stays next to the line above it; a sub-line moves with its parent."""
    ranked, previous = [], 0
    for n, group in enumerate(groups):
        rank = style.line_rank(group[0].line.text)
        previous = previous if rank is None else rank
        ranked.append((group[0].folded, previous, n, group))
    return [group for *_, group in sorted(ranked, key=lambda r: r[:3])]


def _mergeable(group: list[_Row], style) -> str | None:
    """The opening a one-line group may be merged on ("Monitor"): no sub-line, no bracket, no tags and no
    quantity of its own. None when it may not."""
    if len(group) != 1:
        return None
    row = group[0]
    text = _squash(row.line.text)
    opening = next((o for o in style.merge_openings if text.casefold().startswith(o.casefold() + " ")), None)
    if opening is None or row.line.depth != 1 or "(" in text or row.tags or _QTY_IN_LINE.search(text):
        return None
    if re.search(r",|\band\b", text[len(opening):]):
        return None                            # "Monitor Fan Start/Stop, Status and Fail": already a list
    if row.own and row.q is not None and row.q != row.units:
        return None
    return opening


def _joined_objects(opening: str, objects: list[str]) -> str:
    body = objects[0] if len(objects) == 1 else ", ".join(objects[:-1]) + " and " + objects[-1]
    return f"{opening} {body}"


def _merge_openings(groups: list[list[_Row]], style) -> list[list[_Row]]:
    """ "Monitor X", "Monitor Y" and "Monitor Z", with no quantity of their own, as one line "Monitor X, Y and Z"
    where the first was (more lines when one would be too long)."""
    by_opening: dict[tuple, list[int]] = defaultdict(list)
    for n, group in enumerate(groups):
        opening = _mergeable(group, style)
        if opening is not None:
            by_opening[(opening, group[0].folded, group[0].system)].append(n)      # one system's lines only
    replace: dict[int, list[list[_Row]]] = {}
    gone: set[int] = set()
    for (opening, _, _), at in by_opening.items():
        if len(at) < 2:
            continue
        rows = [groups[n][0] for n in at]
        merged: list[list[_Row]] = []
        chunk: list[_Row] = []
        for row in rows:
            objects = [_squash(r.line.text)[len(opening):].strip() for r in chunk + [row]]
            if chunk and len(_joined_objects(opening, objects)) > style.max_line_length:
                merged.append(chunk)
                chunk = []
            chunk.append(row)
        merged.append(chunk)
        out = []
        for chunk in merged:
            first = chunk[0]
            text = _joined_objects(opening, [_squash(r.line.text)[len(opening):].strip() for r in chunk])
            line = dataclasses.replace(first.line, text=text, confidence=min(r.line.confidence for r in chunk),
                                       quoted=all(r.line.quoted for r in chunk))
            out.append([dataclasses.replace(first, line=line)])
        replace[at[0]] = out
        gone.update(at[1:])
    result: list[list[_Row]] = []
    for n, group in enumerate(groups):
        if n in gone:
            continue
        result += replace.get(n, [group])
    return result


def _with_total(row: _Row, style) -> str:
    """The line with "(Qty. N Total)" when its count is not one a unit and the line does not say it already
    (by its own total, or by the tags it names)."""
    text = row.line.text
    if (row.q is None or row.q <= 1 or row.q == row.units or row.tags or _QTY_IN_LINE.search(text)
            or style.is_trio(text) or style.line_group(text) == "integration"):
        return text
    total = f"{text} (Qty. {row.q} Total)"
    return total if len(total) <= style.max_line_length else text


def _names_folded(text: str, kind: str, tags) -> bool:
    """The line is for the units a header folds in: it names one of their tags, their tag prefix or the
    kind's last word ("heater")."""
    named = set(_named_tags(text))
    if named & {t.upper() for t in tags}:
        return True
    words = {_singular(w) for w in _plain(text).split()}
    prefixes = {_tag_prefix(t).lower() for t in tags}
    head = _singular(_plain(kind).split()[-1]) if _plain(kind) else ""
    return bool(words & prefixes) or (bool(head) and head in words)


def _folded_rows(system, rows: list[_Row], evidence: str, templates, name: str) -> tuple[list[_Row], list]:
    """The lines of the units a header folds in, when the judge wrote none for them: the nearest Master
    Template entry's usual lines, as ASSUMPTION, with a review line."""
    added, review = [], []
    for kind, tags in fold(system).folded:
        if any(_names_folded(r.line.text, kind, tags) for r in rows):
            continue
        near = nearest_templates(kind, _tag_prefix(tags[0]) if tags else "", templates, k=1)
        if not near:
            continue
        template = near[0]
        lines = _template_defaults(template, SimpleNamespace(tags=tags), evidence)
        origin = f"the Master Template ({template.name}, for the folded {kind})"
        why = f"the Master Template's {template.name} line, for the {kind} folded into {name}"
        added += [_Row(CheckedLine(text, depth, None, "", "", why, _EVIDENCE_CONFIDENCE[ASSUMPTION], False, origin),
                       len(tags), True, frozenset(), len(tags), name, folded=True) for text, depth in lines]
        review.append(ReviewItem(name, ASSUMPTION, f"{kind} {tag_list(list(tags))} is folded into {name} with no line "
                                 f"of its own; it is printed with the Master Template's {template.name} lines",
                                 "", "Check them against the drawings and the sequence"))
    return added, review


def _location_row(system, rows: list[_Row], quantity, name: str) -> list[_Row]:
    """The rooms the plan listed as the system's tags, as the house's "(Location: …)" line under the header;
    none when a line of the block already lists them all."""
    rooms = locations(system)
    if not rooms:
        return []
    wanted = {_plain(r) for r in rooms}
    if any(wanted <= {_plain(i) for i in _location_items(r.line.text)} for r in rows):
        return []
    text = f"(Location: {', '.join(rooms)})"
    why = "the rooms the plan lists for the system"
    line = CheckedLine(text, 1, None, system.quantity_quote or "", (source_ids(system.quantity_source) or [""])[0],
                       why, _EVIDENCE_CONFIDENCE[CONFIRMED], True, "the plan's locations")
    return [_Row(line, None, False, frozenset(), quantity, name)]


def _checked_shape(system, check: PlanCheck, shape: HeaderShape, quantity) -> tuple[HeaderShape, list]:
    """The header check after writing: the tags each header lists add up to its count. When they don't, the
    plan's own header and quantity are printed, with a review row. A type tag counted many times (one tag, or
    a count other than the distinct tags agreeing) is no disagreement."""
    name = _name(system)
    counted_by_others = {n for label, n in (check.counts or {}).items() if label != "distinct tags"}
    wrong = []
    for header, n in zip(shape.headers, shape.quantities):
        listed = len(header_tags(header))
        if n is None or listed <= 1 or listed == n or n in counted_by_others:
            continue
        wrong.append((header, listed, n))
    if not wrong:
        return shape, []
    base = _base_name(system)
    if "|" not in base:
        shape = HeaderShape((_squash(f"Qty ({_count(quantity)}) {_with_kind(base, system.kind or '')}"),),
                            (quantity,), "", 0)
    said = "; ".join(f"“{h}” lists {listed} tags for a count of {n}" for h, listed, n in wrong)
    return shape, [ReviewItem(name, DISCREPANCY, f"{shape.headers[0]}: tag list and quantity disagree — {said}",
                              f"The plan: “{base}”, {_count(quantity)}", "Correct the count or the tags",
                              tier=TIER_DISCREPANCY)]


_FURNISH = re.compile(r"^furnish\b", re.I)


def _unit_maker_sentences(evidence: str, style) -> list[str]:
    """The sentences of the evidence that give something to the unit's manufacturer."""
    out = []
    for sentence in re.split(r"(?<=[.;])\s+|\n", evidence or ""):
        text = sentence.strip()
        if text and any(re.search(p, text, re.I) for p in style.by_unit_mfr_patterns):
            out.append(text)
    return out


def _given_to_unit_maker(rows: list, evidence: str, style) -> tuple[list, list[str]]:
    """A Master Template line furnishing a device that a schedule note gives to the unit's manufacturer is the
    house note "*<DEVICE> BY UNIT MFR.", never a furnish line. The AI's own lines are left as written."""
    sentences = _unit_maker_sentences(evidence, style)
    if not sentences:
        return rows, []
    kept, notes = [], []
    words_of = [{_singular(w) for w in _plain(s).split()} for s in sentences]
    for row in rows:
        text = row.line.text
        if row.line.origin and row.line.depth == 1 and _FURNISH.match(text):
            device = style._device(text)
            wanted = {_singular(w) for w in _plain(device).split() if w not in _LINE_STOP}
            if wanted and any(wanted <= have for have in words_of):
                note = style.by_unit_mfr.format(item=_squash(device).upper())
                if note not in notes:
                    notes.append(note)
                continue
        kept.append(row)
    return kept, notes


def _device_line(rows: list, check: PlanCheck, style, name: str) -> list:
    """A panel's device count on its device line, "(Qty. N Total)": the sensor or detector line (the one
    sharing words with the plan's quote first). A review row when no line names the devices."""
    quote = {_singular(w) for w in _plain(check.system.quantity_quote or "").split()}
    candidates = [r for r in rows if r.line.depth == 1 and style.line_group(r.line.text) == "sensors"]
    candidates.sort(key=lambda r: -len(quote & {_singular(w) for w in _plain(style._device(r.line.text)).split()}))
    if not candidates:
        return [ReviewItem(name, "", f"{name}: the plan counts {check.devices} devices, but no line names them",
                           check.system.quantity_quote or "", "Add the device line with (Qty. N Total)")]
    row = candidates[0]
    stated = _QTY_IN_LINE.search(row.line.text)
    if stated is None or int(stated.group(1)) == check.devices:
        row.q, row.own = check.devices, True
    return []


def _written_part(system, check: PlanCheck, scope, got, dossier, templates, style) -> _Part:
    """One planned system written: its checked lines polished and counted, its notes, its tech hours. A
    system with no usable line falls back to the Master Template; one with no quantity is "Qty (##)"."""
    name = _name(system)
    quantity = check.quantity if check.quantity is not None or check.category == PENDING else system.quantity
    kept, scope_review = got if got is not None else ([], [])
    review = [*check.review, *scope_review]
    evidence = system_evidence(system, dossier)
    shape = shape_header(system, quantity)
    shape, disagree = _checked_shape(system, check, shape, quantity)
    review += disagree
    fallback = ""
    if not kept:
        kept, fallback = _fallback(system, scope, dossier, templates)
        what = "the AI has not written it yet" if scope is None else "the AI wrote no line that could be used"
        review.insert(0, ReviewItem(name, ASSUMPTION, f"{FALLBACK} {shape.headers[0]}",
                                    f"{what}; it is printed with {fallback}", "Rewrite the block from the drawings "
                                    "and the sequence", tier=TIER_FIRST))
    one_kind = "|" not in _base_name(system)          # a pipe's families count their own units
    parents = len(shape.headers) - shape.folded
    if one_kind and parents > 1 and quantity is not None and check.category != DISCREPANCY and not disagree \
            and sum(n for n in shape.quantities[:parents] if n is not None) != quantity:
        review.append(ReviewItem(name, DISCREPANCY, f"The plan counts {quantity} for {name}; its stacked headers "
                                 f"count their own tags: {', '.join(shape.headers[:parents])}", "",
                                 "Correct the headers' counts", tier=TIER_DISCREPANCY))
    rows: list[_Row] = []
    for line in kept:
        if style.is_trio(line.text) and not style.verb(line.text):
            q, own = None, False               # "Map Available Points …": no count
        else:
            q, own = _line_count(line.text, line.quote, line.quantity, system, quantity)
        tags = frozenset(_named_tags(line.text))
        folded = any(_names_folded(line.text, kind, ftags) for kind, ftags in fold(system).folded)
        for text in ([style.template_form(line.text)] if fallback else polish_line(line.text)):
            rows.append(_Row(dataclasses.replace(line, text=text), q, own, tags, quantity, name, folded=folded))
    added, folded_review = _folded_rows(system, rows, evidence, templates, name)
    rows += added
    review += folded_review
    rows = _location_row(system, rows, quantity, name) + rows
    rows, maker_notes = _given_to_unit_maker(rows, evidence, style)
    if check.devices is not None:
        review += _device_line(rows, check, style, name)
    pictured = (any(_is_picture(sid, dossier) for sid in _system_ids(system))       # the judge read a picture
                or any(_is_picture(line.source_id, dossier) for line in kept))     # for this system
    notes: list[str] = list(maker_notes)
    for note in getattr(scope, "client_notes", ()) or ():
        note = _squash(note)
        text, problem = _client_note(note, evidence, pictured, style)
        if problem is None:
            if not any(style.same_note(text, have) for have in notes + ([shape.note] if shape.note else [])):
                notes.append(text)
        else:
            review.append(ReviewItem(name, "", f"The AI suggests the client note “{note}”, but {problem}", "",
                                     "Add it by hand if it applies"))
    count = hours_count(system, quantity)
    printed = "\n".join(r.line.text for r in rows)    # a rule's "when it gets more points" reads the system's own lines
    hours, hours_note = tech_hours(system, quantity, [(r.line.text, r.q if r.own else count, r.line.depth)
                                                      for r in rows],
                                   getattr(scope, "tech_hours_hint", None), templates, printed)
    if hours_note is not None:
        review.append(hours_note)
    template = _nearest_template(system, templates)
    point = (template.tech_hours.hours if template is not None and template.tech_hours.per == "hardware_point"
             else None)
    for row in rows:
        if point is not None and _hardware_point(row.line.text):
            row.hours = point * (row.q or 0)
    includes = shape.note if shape.note and not style.forbidden(shape.note) else ""
    return _Part(system, shape.headers, rows, notes, includes, review, hours)


def _scope_line(row: _Row, text: str, dossier) -> ScopeLine:
    line = row.line
    category = ASSUMPTION if line.origin or not line.quoted else CONFIRMED
    where = _where(dossier, line.source_id)
    said = f"{where + ': ' if where else ''}“{line.quote}”" if line.quote else (line.why or "no quote")
    return ScopeLine(row.system, text, line.depth, row.q, row.hours, category, line.confidence,
                     line.origin or _source(line.source_id), said + (f" ({line.why})" if line.why and line.quote
                                                                     else ""), True)


def _left_out_rows(review: list, key: str, texts: list[str], style) -> list:
    """A group's "usually present in the Master Template" rows as one for the block: the lines the merged
    block has taken out, under the block's name."""
    lead = "the AI left out: "
    rows = [r for r in review if r.decide.startswith("Usually present in the Master Template's")]
    if not rows:
        return review
    template = rows[0].decide.split("Master Template's ", 1)[1].split(";", 1)[0]
    missing = []
    for r in rows:
        for entry in r.decide.split(lead, 1)[-1].split("; "):
            options = entry.split(" or ")
            if entry and entry not in missing and not any(same_line(o, t, style) for o in options for t in texts):
                missing.append(entry)
    out = [r for r in review if r not in rows]
    if missing:
        out.append(ReviewItem(key, "", f"Usually present in the Master Template's {template}; the AI left out: "
                              + "; ".join(missing), "", "Add any line the job needs"))
    return out


def _written_system(key: str, parts: list[_Part], template: str | None, dossier=None, style=None) -> WrittenSystem:
    """One block, or several headers stacked over the lines they share (a group, or one system whose header
    is one header per family or folds other units in). The lines are merged into one set: a line said twice
    is written once, in the house order, with its total when it is not one a unit."""
    style = style or load_house_style()
    headers = [h for p in parts for h in p.headers]
    blocks = [Block(header=h, joined=i > 0) for i, h in enumerate(headers)]
    hours = None if any(p.hours is None for p in parts) else float(sum(p.hours for p in parts))
    blocks[0] = blocks[0].model_copy(update={"tech_hours": hours})
    merged: list[tuple[_Row, _Row]] = []
    groups = _dedupe_groups(_group_rows([r for p in parts for r in p.rows]), style, merged)
    groups, repeats = _drop_repeats(groups, style)
    merged += repeats
    groups = _merge_openings(_house_order(groups, style), style)
    rows = [r for g in groups for r in g]
    includes = list(dict.fromkeys(p.includes for p in parts if p.includes))
    notes: list[tuple[str, str]] = []
    for p in parts:
        for note in p.notes:
            if not any(style.same_note(note, have) for have, _ in notes) and note not in includes:
                notes.append((note, _name(p.system)))
    texts = [_with_total(r, style) for r in rows]
    items = [Item(kind="note", runs=(Run(text=n),)) for n in includes]
    items += [Item(kind="line", depth=r.line.depth, runs=(Run(text=t),), quantity=r.q) for r, t in zip(rows, texts)]
    items += [Item(kind="note", runs=(Run(text=n),)) for n, _ in notes]
    blocks[-1] = blocks[-1].model_copy(update={"items": tuple(items)})
    lines = [ScopeLine(_name(p.system), p.includes, 1, None, None, CONFIRMED, _ADDED_CONFIDENCE, SOURCE,
                       f"taken out of the plan's header: “{_base_name(p.system)}”", True) for p in parts if p.includes]
    lines += [_scope_line(r, t, dossier) for r, t in zip(rows, texts)]
    lines += [ScopeLine(who, n, 1, None, None, CONFIRMED, _ADDED_CONFIDENCE, SOURCE,
                        "a clarification the evidence bears out", True) for n, who in notes]
    review = [r for p in parts for r in p.review]
    if len(parts) > 1:
        review = _left_out_rows(review, key, [r.line.text for r in rows], style)
        review = [dataclasses.replace(r, system=key, decide=f"{r.system}: {r.decide}") if r.evidence == _AI_NOTE
                  else r for r in review]       # the AI's notes on the block's units: one row for the block
    if merged:
        review.append(ReviewItem(key, "", f"Repeated lines printed once in {headers[0]} ({len(merged)})",
                                 "; ".join(f"“{gone.line.text}” (kept “{kept.line.text}”)" for gone, kept in merged),
                                 "Put a line back if it is for another unit", tier=TIER_REST))
    if len(rows) > style.block_review_over:
        review.append(ReviewItem(key, "", f"long block — check for merged or repeated lines: {headers[0]} has "
                                 f"{len(rows)} lines (the house writes 4 to 9)", "", "Merge or delete lines the job "
                                 "does not need", tier=TIER_DISAGREE))
    return WrittenSystem(key, tuple(blocks), tuple(lines), tuple(review), printed=True, template=template,
                         tech_hours=hours)


def _held_system(system, check: PlanCheck, scope) -> WrittenSystem:
    """A system nothing on the drawings shows: not printed; its question carries the lines the AI wrote for it."""
    question = check.review[0]
    written = [_squash(line.text) for line in getattr(scope, "lines", ()) or ()]
    if written:
        question = dataclasses.replace(question, evidence=_squash(
            f"{question.evidence} — The AI wrote for it: " + "; ".join(f"“{t}”" for t in written)))
    return WrittenSystem(system.key, (), (), (question,) + tuple(check.review[1:]), printed=False)


def _asks_about(question: str, key: str, plan) -> bool:
    """The AI's question is about the held system: it names the system (its name, or a tag it lists)."""
    system = next((s for s in plan.systems if s.key == key), None)
    if system is None:
        return False
    asked = f" {_plain(question)} "
    name = _plain(_TAG_RUN.sub(" ", _name(system)))
    tags = [_plain(t) for t in expand_tags(system.tags) if is_equipment_tag(t)]
    return bool(name) and f" {name} " in asked or any(t and f" {t} " in asked for t in tags)


def _exception(system, check: PlanCheck, style) -> tuple[WrittenSystem, str | None]:
    """A unit that needs no BMS work: its one line goes into the proposal's exceptions."""
    name = _name(system)
    text = _squash(system.exception)
    review = list(check.review)
    ids = _system_ids(system)
    evidence = (system.quantity_quote or system.why or "") + (f" [{', '.join(ids)}]" if ids else "")
    bad = style.forbidden(text) or ("it names prices, hours or confidence" if _NEVER.search(text) else None)
    if bad:
        review.insert(0, ReviewItem(name, "", f"The AI's exception for {name} was left out — {bad}", text,
                                    "Write the exception by hand"))
        return WrittenSystem(system.key, (), (), tuple(review), printed=False), None
    confidence = _EXCEPTION_CONFIDENCE if check.sourced else UNSOURCED_CONFIDENCE
    line = ScopeLine(name, text, 1, None, None, CONFIRMED if check.sourced else ASSUMPTION, confidence,
                     _source(ids[0] if ids else ""), evidence, True)
    review.insert(0, ReviewItem(name, "", f"{name} not priced — put in the exceptions", system.why or evidence,
                                "Price it if the job wants the BMS to see it"))
    return WrittenSystem(system.key, (), (line,), tuple(review), printed=True), text


# --- C2: the front end ------------------------------------------------------------------------------------------

_FE_STOP = frozenset("furnish install and wire the a an of for to on in at with new all each provide necessary "
                     "bms system".split())
_WARRANTY_CLAUSE = re.compile(r"^(?P<rest>.+)(?:,\s*|\s+and\s+)(?P<clause>[^,]*\bwarrant\w*\b[^,]*)$", re.I)
_LONG_TERM = re.compile(r"\b(?:(?P<months>\d+)\s*-?\s*months?|(?P<years>\d+|two|three|four|five)\s*-?\s*years?)\b",
                        re.I)


def _plan_lines(value) -> list[str]:
    out = []
    for entry in value or ():
        text = entry.get("text", "") if isinstance(entry, dict) else str(entry)
        if _squash(text):
            out.append(_squash(text))
    return out


def _fe_words(text: str) -> frozenset[str]:
    return frozenset(w for w in _plain(text.lstrip("*")).split() if w not in _FE_STOP)


def _near_duplicate(text: str, have: list[str]) -> bool:
    words = _fe_words(text)
    if not words:
        return True
    return any(_plain(text) == _plain(h) or len(words & _fe_words(h)) / len(words) >= NEAR_DUPLICATE for h in have)


def _contradiction(text: str, have: list[str]) -> str | None:
    """The front-end line already there that the plan's line contradicts: a server furnished against a
    server by the owner (or the other way), a second workstation, a second kind of graphics."""
    low = text.lower()
    if "server" in low:
        furnishes = bool(re.match(r"furnish(?:\s+and\s+install)?\s+(?:an?\s+|the\s+)?(?:bms\s+)?server\b", low))
        for h in have:
            hl = h.lower()
            by_owner = "server" in hl and bool(re.search(r"\bby\s+(?:the\s+)?owner\b", hl))
            furnished = "server" in hl and hl.startswith("furnish")
            if (furnishes and by_owner) or (not furnishes and "owner" in low and furnished):
                return h
    for word in ("workstation", "graphic"):
        if word in low:
            match = next((h for h in have if word in h.lower()), None)
            if match is not None:
                return match
    return None


def _long_warranty(text: str) -> bool:
    """The warranty's term is longer than the standard year ("24-Month", "two-year")."""
    words = {"two": 2, "three": 3, "four": 4, "five": 5}
    for m in _LONG_TERM.finditer(text):
        if m.group("months") and int(m.group("months")) > 12:
            return True
        years = m.group("years")
        if years and (int(years) if years.isdigit() else words.get(years.lower(), 0)) > 1:
            return True
    return False


_TERM = re.compile(r"\b(?P<n>\d+|one|two|three|four|five)(?:\s*\(\d+\))?\s*-?\s*(?P<unit>years?|months?)\b", re.I)
_MAKERS_WARRANTY = re.compile(r"\b(?:manufacturer\w*|mfr|factory|compressor|exchanger|motor)\b", re.I)


class WarrantyTerm(NamedTuple):
    term: str            # "24 months", as the specification writes it
    sentence: str        # the sentence, word for word
    where: str           # its place, in few words
    long: bool           # longer than the standard year


def spec_warranty(catalogue) -> WarrantyTerm | None:
    """The warranty term the specification names, from the Spec overview's services (the warranty, a service or
    maintenance agreement): the quote, then the sentences on its places in the controls specification. The first
    sentence naming a warranty and a term decides; a maker's warranty ("five-year manufacturer's warranty") never
    does. None when no term is named."""
    services = {s.item: s for s in getattr(getattr(catalogue, "overview", None), "services", ()) or ()}
    pages = {(r.document, r.page): r for r in getattr(catalogue, "pages", ()) or ()}
    for item in ("Warranty", "Service or maintenance agreement"):
        found = services.get(item)
        if found is None or found.status != FOUND_STATUS:
            continue
        candidates = [(found.quote or "", found.places[:1])]
        for place in found.places:
            record = pages.get((place.document, place.page))
            if place.strength != "Controls spec" or record is None:
                continue
            text = _squash(clean_text(record.text))
            candidates += [(s, (place,)) for s in re.split(r"(?<=[.;])\s+", text)]
        for sentence, places in candidates:
            if not re.search(r"\bwarrant", sentence, re.I) or _MAKERS_WARRANTY.search(sentence):
                continue
            m = _TERM.search(sentence)
            if m is None:
                continue
            n = m.group("n").lower()
            n = int(n) if n.isdigit() else "one two three four five".split().index(n) + 1
            long = n > 12 if m.group("unit").lower().startswith("month") else n > 1
            return WarrantyTerm(m.group(0), _squash(sentence), short_place(places) if places else "", long)
    return None


def _spec_warranty_block(found: WarrantyTerm) -> tuple[Block, list]:
    """The Master Template's Extended Warranty block for a term the specification names, with its evidence."""
    data = _front_end_data(FRONT_END_FILE)["warranty"]
    contract = data["contract"].format(term=_term(found.term))
    items = (Item(kind="line", depth=1, runs=(Run(text=data["heading"], bold=True),)),
             Item(kind="line", depth=2, runs=(Run(text=contract, bold=True),)))
    evidence = [Evidence(data["heading"], found.where, found.sentence, CONFIRMED),
                Evidence(contract, found.where, found.sentence, CONFIRMED)]
    return Block(header=data["extended_header"], items=items), evidence


def _printed_because(text: str, evidence) -> str:
    """Why the front end prints a line, in plain words, from its evidence."""
    found = next((e for e in evidence or () if _plain(e.line) == _plain(text)), None)
    if found is None:
        return "the Master Template's front end"
    quote = f": “{found.quote[:140]}”" if found.quote else ""
    if found.status != CONFIRMED:
        return "a Master Template default"
    if text.startswith("**") and "owner" in text.lower():
        return f"the specification gives it to the owner — {plain_place(found.where)}{quote}"
    return f"the specification calls for it — {plain_place(found.where)}{quote}"


def _fe_patterns(key: str):
    data = _front_end_data(FRONT_END_FILE).get(key) or {}
    return data


def _given_away(note: str, have: list[str]) -> str | None:
    """The printed front-end line whose item a client note gives to the owner or others ("**Computers … by others"
    against "Furnish PC Workstation"), or None."""
    data = _fe_patterns("contradicts")
    if not any(re.search(p, note, re.I) for p in data.get("given_away", ())):
        return None
    for line, patterns in (data.get("lines") or {}).items():
        if line in have and any(re.search(p, note, re.I) for p in patterns):
            return line
    return None


def _note_supported(line: str, overview) -> str:
    """A sentence of the Spec overview naming the line's item and giving it to the owner or others, or ""."""
    from estimator.writing.front_end import _sentences
    data = _front_end_data(FRONT_END_FILE)
    things = (data.get("contradicts") or {}).get("lines", {}).get(line, ())
    parties = [*data["parties"]["owner"], *data["parties"]["others"]]
    rows = [*getattr(overview, "who_does_what", ()), *getattr(overview, "topics", ()), *getattr(overview, "services", ())]
    for row in rows:
        if getattr(row, "status", FOUND_STATUS) != FOUND_STATUS:
            continue
        for sentence in _sentences(row.quote or ""):
            if any(re.search(p, sentence, re.I) for p in things) and any(re.search(p, sentence, re.I) for p in parties):
                return f"“{_squash(sentence)[:160]}”"
    return ""


def _line_supported(line: str, evidence) -> bool:
    """The specification calls for the front-end line (its evidence is the job's own words)."""
    return any(_plain(e.line) == _plain(line) and e.status == CONFIRMED for e in evidence or ())


def _without_line(fe, line: str):
    """The front end without the line and its sub-lines."""
    items, skipping = [], False
    for item in fe.items:
        if item.kind == "line" and item.depth == 1:
            skipping = item.text == line
        elif item.kind != "line":
            skipping = False
        if not skipping:
            items.append(item)
    return fe.model_copy(update={"items": tuple(items)})


def _reconcile_front_end(fe, plan, dossier, style, warranty_block, evidence=(), topics=frozenset(), overview=None):
    """The deterministic front end (the Master Template's lines the Spec overview calls for) is the base.
    A line the plan adds goes in only when it adds something new (not a near-duplicate), cites a source and
    keeps the house style; a contradiction keeps the deterministic answer, and a client note giving a printed
    line's item to others keeps the one the documents support in the same sentence; the warranty goes into the
    Extended Warranty block, never the front end; the plan's lines fill the front end to MAX_FRONT_END_LINES lines
    at most, except a line the specification explicitly calls for (`topics`: the Spec overview's found topics).
    Each review row says plainly which line was printed and why (`evidence`: the front end's own).
    Returns (front end, added scope lines, review, an Extended Warranty block the plan gives or None)."""
    raw = getattr(plan, "front_end", None) or {}
    review: list[ReviewItem] = []
    added: list[ScopeLine] = []
    ids = [i for i in source_ids(raw.get("sources", ())) if i in (dossier.sources or {})]
    where = "; ".join(dict.fromkeys(plain_place(_where(dossier, i)) for i in ids)) or "no source"
    mode = raw.get("mode") or ""
    if mode and mode != fe.mode:
        why = ("the specification asks for a tie-in to the existing system" if fe.mode == "extend-existing"
               else "the specification asks for no tie-in to an existing system")
        review.append(ReviewItem(_FRONT_END_KEY, "", f"Printed the {fe.mode.replace('-', ' ')} front end, because "
                                 f"{why}; the AI's plan reads the front end as {mode.replace('-', ' ')}", where,
                                 "Change the front end by hand if the plan is right", tier=TIER_DISAGREE))
    name = _squash(raw.get("existing_name") or "")
    if name and fe.mode == "extend-existing" and _plain(name) not in _plain(fe.existing_system_name or ""):
        heading = next((e for e in evidence or () if e.line.startswith("Seamlessly")), None)
        said = f" ({plain_place(heading.where)}: “{heading.quote[:140]}”)" if heading and heading.quote else ""
        review.append(ReviewItem(_FRONT_END_KEY, "", f"Printed the existing BMS as “{fe.existing_system_name}”, as "
                                 f"the specification names it{said}; the AI's plan names it “{name}”", where,
                                 "Check which it is", tier=TIER_DISAGREE))
    have = [i.text for i in fe.items]
    lines, notes = _plan_lines(raw.get("lines")), _plan_lines(raw.get("notes"))
    new_lines, new_notes, left, over, warranties, contradicted, settled = [], [], [], [], [], [], []
    for text, is_note in [(t, False) for t in lines] + [(t, True) for t in notes]:
        if style.is_spec_wording(text):
            house = None if is_note else style.house_opening(text)
            if house is None:
                left.append(f"“{text}” (it copies the specification's wording, “ATC Contractor to …”)")
                continue
            text = house
        if not is_note:
            text = polish_line(text)[0]
        if re.search(r"\bwarrant", text, re.I):
            m = _WARRANTY_CLAUSE.match(text)
            if m and len(_fe_words(m.group("rest"))) >= 2:
                warranties.append(m.group("clause").strip())
                text = m.group("rest").strip()
            else:
                warranties.append(text)
                continue
        if _near_duplicate(text, have):
            continue
        against = _contradiction(text, have)
        if against is not None:
            contradicted.append((text, against))
            continue
        given = _given_away(text, have) if is_note else None
        if given is not None:                 # a note giving a printed line's item to others
            note_ok, line_ok = _note_supported(given, overview), _line_supported(given, evidence)
            if note_ok and not line_ok:
                fe = _without_line(fe, given)
                have = [h for h in have if h != given]
                settled.append((text, given, "a sentence of the specification gives it to others: "
                                + note_ok))
            else:
                why = (f"{_printed_because(given, evidence)}" + ("; the specification also gives it to others: "
                                                                 + note_ok if note_ok else ""))
                settled.append((given, text, why))
                continue
        problem = None if ids else "it cites no source"
        if problem is None and _NEVER.search(text):
            problem = "it names prices, hours or confidence"
        problem = problem or (style.check_note(text) if is_note else style.check_line(text, 1))
        if problem:
            left.append(f"“{text}” ({problem})")
            continue
        have.append(text)
        item = Item(kind="note" if is_note else "line", runs=(Run(text=text, bold=True),))
        (new_notes if is_note else new_lines).append(item)
        added.append(ScopeLine(_FRONT_END_KEY, text, 1, None, None, ADDED, _ADDED_CONFIDENCE, _source(ids[0]),
                               where, True))
    fe, new_lines, over = _cap_front_end(fe, new_lines, topics)
    added = [a for a in added if a.text not in set(over)]
    if new_lines or new_notes:
        review.append(ReviewItem(_FRONT_END_KEY, ADDED, "Front-end lines added from the AI's plan: "
                                 + "; ".join(f"“{i.text}”" for i in new_lines + new_notes), where,
                                 "Check each, and price the lines"))
    for text, against in contradicted:
        review.append(ReviewItem(_FRONT_END_KEY, "", f"Printed “{against}” and kept it ({_printed_because(against, evidence)}); "
                                 f"the AI's plan wrote “{text}”, which contradicts it and was left out", where,
                                 "Change the front end by hand if the plan is right", tier=TIER_DISAGREE))
    for kept, gone, why in settled:
        review.append(ReviewItem(_FRONT_END_KEY, "", f"Printed “{kept}” and left out “{gone}”: the two contradict, "
                                 f"and the documents support the one printed ({why})", where,
                                 "Change the front end by hand if the other is right", tier=TIER_DISAGREE))
    if over:
        review.append(ReviewItem(_FRONT_END_KEY, "", f"Spec items the front end could add (the AI's plan fills it to "
                                 f"{MAX_FRONT_END_LINES} lines at most)", "; ".join(over),
                                 "Add any the job needs in place of a line there"))
    block = None
    if warranties:
        if warranty_block is None and any(_long_warranty(w) for w in warranties):
            text = next(w for w in warranties if _long_warranty(w))
            block = Block(header=_front_end_data(FRONT_END_FILE)["warranty"]["extended_header"],
                          items=(Item(kind="line", runs=(Run(text=text),)),))
            review.append(ReviewItem(_WARRANTY, ADDED, f"Extended Warranty block written from the AI's plan: “{text}”",
                                     where, "Check the term and price it"))
        else:
            carried = " (the Extended Warranty block carries it)" if warranty_block else ""
            left += [f"“{w}” (a warranty never goes in the front end{carried})" for w in warranties]
    if left:
        review.append(ReviewItem(_FRONT_END_KEY, "", "Front-end lines in the AI's plan left out: " + "; ".join(left),
                                 where, "Add any by hand if the job needs it"))
    if lines:
        planned = {_plain(t) for t in lines}
        missing = [i.text for i in fe.items if i.kind == "line" and i.depth == 1 and _plain(i.text) not in planned
                   and not _near_duplicate(i.text, lines)]
        if missing:
            review.append(ReviewItem(_FRONT_END_KEY, "", "The AI's plan leaves out front-end lines the specification "
                                     "or the Master Template gives; they are printed: "
                                     + "; ".join(f"“{m}” ({_printed_because(m, evidence)})" for m in missing), where,
                                     "Delete any the job does not need", tier=TIER_DISAGREE))
    if new_lines or new_notes:
        items = list(fe.items)
        at = next((k for k, i in enumerate(items) if i.kind == "note"), len(items))
        items[at:at] = new_lines
        fe = fe.model_copy(update={"items": tuple(items + new_notes)})
    return fe, added, review, block


def _past_the_cap(text: str, topics) -> bool:
    """A plan's front-end line the specification explicitly calls for (a UPS, the IT infrastructure: network
    switches, fiber), when the Spec overview found its topic."""
    for entry in _fe_patterns("past_the_cap").get("lines", ()):
        if set(entry.get("topics", ())) & set(topics or ()) and any(re.search(p, text, re.I)
                                                                   for p in entry.get("words", ())):
            return True
    return False


def _cap_front_end(fe, plan_lines: list, topics=frozenset()) -> tuple[object, list, list[str]]:
    """The cap applies only to the lines the plan adds: the Master Template's front end is printed whole, and the
    plan's lines fill it to MAX_FRONT_END_LINES lines at most, in order, except a line the specification explicitly
    calls for (`topics`: the Spec overview's found topics), which goes in past the cap.
    Returns (the front end, the plan's lines kept, the plan's lines left out)."""
    printed = sum(1 for item in fe.items if item.kind == "line" and item.depth == 1)
    room = max(0, MAX_FRONT_END_LINES - printed)
    kept, over = [], []
    for item in plan_lines:
        if _past_the_cap(item.text, topics):
            kept.append(item)
        elif room > 0:
            kept.append(item)
            room -= 1
        else:
            over.append(item.text)
    return fe, kept, over


def _evidence_system(key: str, block: Block, evidence, template: str | None = None) -> WrittenSystem:
    """A block the deterministic reading writes (Global Points, Extended Warranty), with its evidence."""
    quantities = {i.text: i.quantity for i in block.items}
    lines = tuple(ScopeLine(key, e.line, 1, quantities.get(e.line), None, e.status,
                            _EVIDENCE_CONFIDENCE.get(e.status, 0.5),
                            "the Spec overview" if e.status == CONFIRMED else "default",
                            f"{e.where}: “{e.quote}”" if e.quote else e.where, True) for e in evidence)
    return WrittenSystem(key, (block,), lines, (), printed=True, template=template)


def _order(plan) -> list[list]:
    """The planned systems in the plan's order, each group's members together where the first one is."""
    runs: list[list] = []
    seen: dict[str, list] = {}
    for system in plan.systems:
        group = _squash(system.group)
        if group and group in seen:
            seen[group].append(system)
            continue
        run = [system]
        runs.append(run)
        if group:
            seen[group] = run
    return runs


def assemble_job(catalogue, reading, dossier, plan, scopes, today, templates=None
                 ) -> tuple[Job, list[WrittenSystem], list[ReviewItem]]:
    """The Job from the whole-job plan and each system's scope, the written systems for the Evidence
    Package (the front end first) and the review lines that belong to no system.

    `scopes` maps each planned system's key to its WrittenScope, or None when the AI has not written
    it yet. Nothing planned is lost: exceptions go into the exceptions, alternates into the add or
    deduct alternates, every other system into the base bid — "Qty (##)" when it has no quantity, with
    the Master Template's lines when the AI wrote none that could be used (each with a top review line)."""
    templates = templates if templates is not None else load_templates()
    style = load_house_style()
    header, header_flags = job_header(catalogue, reading, today)
    fe, fe_flags, fe_evidence = front_end(catalogue, bid_check=getattr(catalogue, "bid", None))
    points, points_evidence = global_points_block(catalogue, templates=templates)
    warranty, warranty_flags, warranty_evidence = extended_warranty_block(catalogue)
    named = spec_warranty(catalogue) if warranty is None else None
    if named is not None:             # a term was found: the warranty is no longer a question
        fe_flags = [f for f in fe_flags if not f.startswith("Say how long the warranty is")]
        if named.long:
            warranty, warranty_evidence = _spec_warranty_block(named)
    topics = {t.item for t in getattr(catalogue.overview, "topics", ()) or () if t.status == FOUND_STATUS}
    fe, fe_added, fe_review, plan_warranty = _reconcile_front_end(fe, plan, dossier, style, warranty, fe_evidence,
                                                                  topics, catalogue.overview)
    printed = {_plain(i.text) for i in fe.items}
    fe_evidence = [e for e in fe_evidence if _plain(e.line) in printed]      # a line the cap left out is not printed
    if warranty is not None:          # the standalone block carries the warranty: the front end's lines go
        moved = {_plain(i.text) for i in warranty.items}
        fe = fe.model_copy(update={"items": tuple(i for i in fe.items if _plain(i.text) not in moved)})
        fe_evidence = [e for e in fe_evidence if _plain(e.line) not in moved]
    front = _front_end_system(fe, fe_flags, fe_evidence, header_flags)
    extra_review = fe_review + [ReviewItem(_FRONT_END_KEY, "", *f.partition(" — ")[::2], "") for f in warranty_flags]
    front = dataclasses.replace(front, lines=front.lines + tuple(fe_added), review=front.review + tuple(extra_review))

    checks, general = plan_checks(plan, dossier, reading, catalogue)
    check_of = {id(c.system): c for c in checks}
    systems: list[WrittenSystem] = []
    held: list[WrittenSystem] = []
    base: list[Block] = []
    exceptions: list[str] = []
    alternates: dict[str, list] = {"add": [], "deduct": []}
    if points is not None:
        systems.append(_evidence_system(_GLOBAL_POINTS, points, points_evidence, _GLOBAL_POINTS))
        base.append(points)

    def merged_into_points(system) -> bool:
        return points is not None and _GLOBAL_POINTS.lower() in f"{system.header} {system.kind}".lower()

    # Each system's lines are checked first, so one device named in two systems stays in one place.
    entries, checked = [], {}
    for system in plan.systems:
        if system.exception or merged_into_points(system) or check_of[id(system)].held:
            continue
        scope = (scopes or {}).get(system.key)
        if scope is not None:
            kept, review = check_scope(system, scope, dossier, templates, style, sourced=check_of[id(system)].sourced)
            entries.append([system, kept, review])
            checked[id(system)] = entries[-1]
    _one_place(entries, dossier)

    for run in _order(plan):
        parts = []
        for system in run:
            check = check_of[id(system)]
            if system.exception:
                written, text = _exception(system, check, style)
                systems.append(written)
                if text:
                    exceptions.append(text)
                continue
            if merged_into_points(system):
                continue                  # printed: the Master Template's Global Points block carries it
            if check.held:
                held.append(_held_system(system, check, (scopes or {}).get(system.key)))
                continue                  # nothing on the drawings shows it: a question, never a block
            entry = checked.get(id(system))
            got = (entry[1], entry[2]) if entry is not None else None
            parts.append(_written_part(system, check, (scopes or {}).get(system.key), got, dossier, templates,
                                       style))
        if not parts:
            continue
        grouped = len(parts) > 1
        key = _squash(run[0].group) if grouped else parts[0].system.key
        template = system_template(parts[0].system, templates)
        written = _written_system(key, parts, template.name if template is not None else None, dossier, style)
        systems.append(written)
        side = parts[0].system.alternate if parts[0].system.alternate in ("add", "deduct") else ""
        if side:
            label = key if grouped else _squash(re.sub(r"^\s*Qty\s*\([^)]*\)\s*", "", parts[0].header))
            alternates[side].append((label, written.blocks))
        else:
            base.extend(written.blocks)
    if warranty is not None:
        systems.append(_evidence_system(_WARRANTY, warranty, warranty_evidence))
        base.append(warranty)
    elif plan_warranty is not None:
        text = plan_warranty.items[0].text
        systems.append(WrittenSystem(_WARRANTY, (plan_warranty,), (ScopeLine(
            _WARRANTY, text, 1, None, None, ADDED, _ADDED_CONFIDENCE, SOURCE, "the AI's plan of the front end",
            True),), (), printed=True))
        base.append(plan_warranty)

    add, deduct = ([Alternate(label=f"ALT #{k}: {label}", blocks=blocks)
                    for k, (label, blocks) in enumerate(alternates[side], start=1)] for side in ("add", "deduct"))
    job = Job(header=header, front_end=fe, blocks=tuple(base), add_alternates=tuple(add),
              deduct_alternates=tuple(deduct), named_exceptions=tuple(exceptions))
    questions = []
    for q in getattr(plan, "unresolved", ()) or ():
        at = next((n for n, h in enumerate(held) if _asks_about(q, h.bundle_key, plan)), None)
        if at is None:
            questions.append(ReviewItem("The plan", "", _squash(q), "the AI's question",
                                        "Decide it, and change the proposal by hand if needed", tier=TIER_QUESTION))
            continue
        row = held[at].review[0]          # the AI asked it too: one question
        held[at] = dataclasses.replace(held[at], review=(dataclasses.replace(
            row, evidence=_squash(f"{row.evidence} — The AI asks the same: {q}")),) + held[at].review[1:])
    systems += held
    general += questions
    dropped = [_squash(str(d)) for d in getattr(plan, "dropped", ()) or ()]
    if dropped:
        general.append(ReviewItem("The plan", "", "The AI planned systems that could not be used; they were thrown "
                                  "away", "; ".join(dropped), "Add a block by hand for any the job needs",
                                  tier=TIER_FIRST))
    return job, [front] + systems, general


# --- the review list, ranked and short ----------------------------------------------------------------------------

_AI_NOTE = "the AI's note"
_NEAREST_HOURS = "Tech hours from the nearest Master Template entry"
_LEFT_OUT = "Usually present in the Master Template's"


def _left_out_line(item: ReviewItem) -> str:
    """ "Usually present in the Master Template's X; the AI left out: a; b" as "System (X): a; b"."""
    template, _, missing = item.decide[len(_LEFT_OUT):].strip().partition("; the AI left out: ")
    return f"{item.system} ({template}): {missing}"
_HOURS_WORDS = re.compile(r"tech[\s-]*hour", re.I)


def _tier(item: ReviewItem) -> int:
    if item.tier:
        return item.tier
    if item.category == DISCREPANCY:
        return TIER_DISCREPANCY
    if item.evidence == "the AI's question":
        return TIER_QUESTION
    return TIER_REST


def _joined(items, what) -> str:
    return "; ".join(dict.fromkeys(what(i) for i in items if what(i)))


def _merge_review(items: list[ReviewItem]) -> list[ReviewItem]:
    """Repeated rows as one: every system with no tech hours in one row, every quote not found in one, the
    AI's own notes on a system in one row per system (its remarks on tech hours folded into the tech-hours
    row), the lines dropped for the house style in one, the client notes not borne out in one, the counts
    with nothing to check them against in one, the exceptions in one."""
    rules = [
        ("hours", lambda i: i.decide.startswith("No tech hours for"),
         lambda g: ReviewItem("Tech hours", "", "No tech hours for: " + _joined(g, lambda i: i.system)
                              + " — enter them", "The nearest Master Template entry gives them no rule, or none is "
                              "near: " + _joined(g, lambda i: f"{i.system}: {i.evidence}"),
                              "Type the hours on each block's header row of the price sheet")),
        ("hours-ai", lambda i: i.decide.startswith(_NEAREST_HOURS),
         lambda g: ReviewItem("Tech hours", ASSUMPTION, "Tech hours from the nearest Master Template entry, not "
                              "the system's own: " + _joined(g, lambda i: f"{i.system} "
                                                             f"({i.decide[len(_NEAREST_HOURS) + 2:]})"),
                              _joined(g, lambda i: f"{i.system}: {i.evidence}"), "Confirm them")),
        ("left-out", lambda i: i.decide.startswith(_LEFT_OUT),
         lambda g: ReviewItem("Master Template", "", f"Lines usually present in the Master Template that the AI "
                              f"left out, one line per system ({len(g)})",
                              "\n".join(_left_out_line(i) for i in g), "Add any line the job needs")),
        ("quotes", lambda i: "is not in the job's documents" in i.decide and i.decide.startswith("The quote for"),
         lambda g: ReviewItem("Quotes", "", f"Lines whose quote is not in the job's documents ({len(g)}) — check "
                              "each by hand", _joined(g, lambda i: f"{i.system}: {i.decide[len('The quote for '):]}"
                                                      .replace(" is not in the job's documents", "")), "")),
        ("dropped", lambda i: i.decide.startswith("The AI wrote lines the client must never see"),
         lambda g: ReviewItem("House style", "", "Lines the AI wrote that break the house style were dropped ("
                              + _joined(g, lambda i: i.system) + ")", _joined(g, lambda i: f"{i.system}: {i.evidence}"),
                              "Nothing to do unless a line is missing")),
        ("notes", lambda i: i.decide.startswith("The AI suggests the client note"),
         lambda g: ReviewItem("Client notes", "", f"Client notes the AI suggested that were not printed ({len(g)})",
                              _joined(g, lambda i: f"{i.system}: " + i.decide.replace("The AI suggests the client note ",
                                                                                     "")),
                              "Add any by hand if it applies")),
        ("unchecked", lambda i: i.category == ASSUMPTION and i.decide.startswith("The plan counts")
         and "with no count to check it" in i.decide,
         lambda g: ReviewItem("Counts", ASSUMPTION, "Counts with nothing to check them against: "
                              + _joined(g, lambda i: i.decide.split(" for ", 1)[1].split(",")[0] + " — "
                                        + i.decide.split("The plan counts ", 1)[1].split(" for ")[0]),
                              _joined(g, lambda i: i.evidence), "Confirm each count")),
        ("unsourced", lambda i: "cites no source for" in i.decide,
         lambda g: ReviewItem("Sources", "", "The plan cites no source for: " + _joined(g, lambda i: i.system)
                              + " — they are written, but check every line", "", "Check the blocks against the "
                              "drawings and the sequence")),
        ("repeats", lambda i: i.decide.startswith("Repeated lines printed once in "),
         lambda g: ReviewItem("Repeated lines", "", f"Repeated lines printed once, one line per block ({len(g)})",
                              "\n".join(f"{i.system}: {i.evidence}" for i in g), "Put a line back if it is for "
                              "another unit", tier=TIER_REST)),
        ("exceptions", lambda i: i.decide.endswith("not priced — put in the exceptions"),
         lambda g: ReviewItem("Exceptions", "", "Not priced — put in the exceptions: " + _joined(g, lambda i: i.system),
                              _joined(g, lambda i: f"{i.system}: {i.evidence}"), "Price any the job wants the BMS to see")),
    ]
    groups: dict[str, list] = defaultdict(list)
    per_system: dict[str, list] = defaultdict(list)
    out: list = []
    for item in items:
        if "mentioned only in the specs" in item.decide:
            continue
        if item.evidence == _AI_NOTE:
            if _HOURS_WORDS.search(item.decide):
                continue                                  # the tech-hours row says it
            if item.system not in per_system:
                out.append(("system", item.system))
            per_system[item.system].append(item)
            continue
        rule = next((r for r in rules if r[1](item)), None)
        if rule is None:
            out.append(item)
            continue
        if rule[0] not in groups:
            out.append(("rule", rule[0]))
        groups[rule[0]].append(item)
    build = {r[0]: r[2] for r in rules}
    merged = []
    for entry in out:
        if isinstance(entry, ReviewItem):
            merged.append(entry)
        elif entry[0] == "rule":
            group = groups[entry[1]]
            single = len(group) == 1 and entry[1] not in ("hours", "hours-ai", "left-out")
            merged.append(group[0] if single else build[entry[1]](group))
        else:
            notes = per_system[entry[1]]
            merged.append(ReviewItem(entry[1], "", f"The AI's notes on {entry[1]}: "
                                     + " | ".join(dict.fromkeys(i.decide for i in notes)), "the AI's notes",
                                     "Add any line the job needs"))
    return _fold(merged)


_COUNT_HOSTS = (": counted from the plans", " panel — the documents state no count", ": the header counts the panels")


def _fold(merged: list[ReviewItem]) -> list[ReviewItem]:
    """One urgent row per system: a system written with fallback lines and with no count is one row, and a
    system that has an urgent row (fallback lines, no count, a quantity conflict) carries its other rows
    there (the AI's notes, the lines it left out, the lines dropped). The front end's Master Template
    defaults go with the row saying the plan leaves the front end's lines out."""
    merged = list(merged)
    dropped: set[int] = set()
    fallback = {item.system: n for n, item in enumerate(merged) if item.decide.startswith(FALLBACK)}
    for n, item in enumerate(merged):
        if item.decide.startswith("Give the count for") and item.system in fallback:
            at = fallback[item.system]
            merged[at] = dataclasses.replace(merged[at], decide=f"{merged[at].decide} — and give its count",
                                             evidence=_squash(f"{merged[at].evidence} — {item.evidence}"))
            dropped.add(n)
    urgent: dict[str, int] = {}
    for n, item in enumerate(merged):
        if n not in dropped and _tier(item) <= TIER_DISCREPANCY and item.system not in urgent:
            urgent[item.system] = n
    for n, item in enumerate(merged):      # a system's count row (counted from the plans, panels) hosts the rest too
        if n not in dropped and item.system not in urgent and any(h in item.decide for h in _COUNT_HOSTS):
            urgent[item.system] = n
    for n, item in enumerate(merged):
        at = urgent.get(item.system)
        if n in dropped or at is None or at == n or _tier(item) <= TIER_QUESTION or item.tier:
            continue
        host = merged[at]
        merged[at] = dataclasses.replace(host, evidence=_squash(f"{host.evidence} — {item.decide}"))
        dropped.add(n)
    starts = ("The AI's plan leaves out front-end lines", "Front-end lines that are Master Template defaults")
    found = [next((n for n, i in enumerate(merged) if n not in dropped and i.system == _FRONT_END_KEY
                   and i.decide.startswith(s)), None) for s in starts]
    if None not in found:
        host, guest = found
        merged[host] = dataclasses.replace(merged[host], evidence=_squash(
            f"{merged[host].evidence} — Master Template defaults in the front end: {merged[guest].evidence}"))
        dropped.add(guest)
    return [item for n, item in enumerate(merged) if n not in dropped]


def review_list(systems, general, dossier=None) -> list[ReviewItem]:
    """Every review row of the job, merged and ranked: a system written with fallback lines or with no count
    first, then the quantity conflicts, the AI's unresolved questions, the rule and AI disagreements, then
    the rest. Each carries its rank (1 = the most urgent). With the dossier, every source id ([S97], I15) is
    replaced by the place it points to, the sheet or section and the page."""
    items = [item for system in systems for item in system.review] + list(general)
    merged = _merge_review(items)
    ordered = sorted(enumerate(merged), key=lambda pair: (_tier(pair[1]), pair[0]))
    return [dataclasses.replace(item, rank=n, decide=plain_ids(item.decide, dossier),
                                evidence=plain_ids(item.evidence, dossier), action=plain_ids(item.action, dossier))
            for n, (_, item) in enumerate(ordered, start=1)]
