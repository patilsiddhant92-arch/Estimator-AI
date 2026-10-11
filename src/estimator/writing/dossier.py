"""The job dossier: everything controls-relevant in the bid documents, gathered into one plain-text
document the judge reads as the estimator reads a bid set (whole-job writing, Part A).

Deterministic reading gathers and checks here; it never decides scope. The dossier holds the job's
documents and the Spec overview's findings, the full text of the sequence of operation and points
list, every schedule row, the equipment counts, the devices on the plans, the controls notes and the
parts of the controls spec that price the front end and services. Every paragraph and row carries a
short source id ("[S12]") that `Dossier.sources` resolves to a place in the documents, so the judge
can cite each line and number it writes. A schedule that is a picture, or whose table couldn't be
read, is rendered to a PNG the judge can look at ("I3").

The floor multiplier lives here, one rule for the counts and the devices alike: a plan sheet number
on N pages of one document stands for N floors, and a typical plan whose title names a floor range
stands for the floors in that range. The sheet is counted on its first page only, then multiplied.
"""
from __future__ import annotations

import hashlib
import os
import re
import secrets
from collections import Counter, defaultdict
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

from estimator.catalogue.documents import document_names
from estimator.catalogue.job import CONTROLS_DISCIPLINES, document_repeats
from estimator.catalogue.sheet_types import is_demolition
from estimator.catalogue.overview import FOUND, RULED_OUT, STANDARD_CLARIFICATION, STANDARD_EXCLUSION
from estimator.catalogue.tags import (STATED_MOST, Equipment, find_tags, label_keys, line_labels, plan_labels,
                                      sheet_number_tags, tag_location, tag_prefix, unread_counts)
from estimator.reading.inventory import (COUNT_CAUSE_WORDS, COUNT_CAUSES_LEAD, TYPE_ON_ONE_SHEET, TYPE_PLACED,
                                        air_outlet_codes, air_outlet_notes, counted_per_place, counting_pages,
                                        first_pages, plan_area_doubts, plan_areas, plan_count, plan_floors, plan_groups,
                                        sheet_floors, sheet_labels, demolition_work, plan_buildings)
from estimator.reading.revisions import governing_pages, typical_places
from estimator.reading.schedules import header_key, quantity_header, vocabulary
from estimator.reading.sequences import POINTS, SEQUENCE
from estimator.writing.systems import _paragraphs
from estimator.writing.write import tag_list

SEQUENCE_LIMIT = 1_200_000     # characters: a longer sequence is kept whole, flagged; the judge splits its passes
SPEC_LIMIT = 12_000          # characters of controls spec highlights
COPY_SHARE = 0.5             # share of a backbone's text already given above that makes it a copy of it
RUNNING_SHARE = 0.6          # a line on this share of a backbone's pages (3 at least) is a running header
EDGE_LINES = 8               # ... when it is among the first or last lines of the page
PICTURE_SHARE = 0.15         # pictures covering this much of a schedule sheet make it a picture schedule
MIN_PICTURE = 0.005          # share of the sheet: smaller pictures (logos, stamps) aren't rendered
ONE_PICTURE = 0.8            # one picture this big is the whole sheet
PICTURE_DPI = 200
SHEET_DPI = 150
MAX_PIXELS = 40e6            # a render bigger than this is drawn at a lower resolution
IMAGE_VERSION = 1            # raise when the way pictures are rendered changes
IMAGES_FOLDER = "dossier-images"
PLAN_NOTES_LIMIT = 3_000     # characters of one sheet's notes in 7b
PLAN_NOTE_DISCIPLINES = ("Mechanical", "Controls", "Plumbing")
PLAN_TEXT_LIMIT = 8_000     # characters of one plan sheet's own text in 7c (repeats collapsed first)
PLAN_TEXT_TOTAL = 400_000   # characters of all plan sheets' text in 7c

_QUANTITY_HEADERS = ("QTY", "QUANTITY", "NO OF UNITS", "NO. OF UNITS", "NUMBER OF UNITS", "NO. REQ'D", "NO REQD",
                     "UNITS REQUIRED", "COUNT")
_INT = re.compile(r"^\s*\(?(\d{1,5})\)?\s*(?:EA\.?|UNITS?)?\s*$", re.I)
_TYPE_CODE = re.compile(r"^[A-Z][A-Z0-9\-/]{0,11}$")
_ARTICLE = re.compile(r"^(\d{1,2}\.\d{1,2})\s+(\S.{1,79})$")
_LIST_MARKER = re.compile(r"^\(?[A-Za-z0-9#]{1,3}[.)]$")
_LIST_ITEM = re.compile(r"^\(?(?:[A-Za-z]|#{1,2})[.)]\s")    # "C. The unit shall …", "#. Point …" (digits made #)
_RISER = re.compile(r"\bRISERS?\b", re.I)

# The controls spec articles the estimator reads for the front end and the services, in the order
# they are given when the highlights run long. Headings only; the text under them is quoted whole.
SPEC_HEADINGS: tuple[tuple[str, re.Pattern], ...] = (
    ("front end", re.compile(r"front[- ]?end|work\s*stations?|servers?|operator\s+interface|graphic", re.I)),
    ("integration", re.compile(r"integrat|gateways?|interfac|third[- ]party|protocol|BACnet|network", re.I)),
    ("wiring", re.compile(r"wiring|conduit|raceway|electrical|cabl", re.I)),
    ("warranty", re.compile(r"warrant|guarantee", re.I)),
    ("training", re.compile(r"training|instruction", re.I)),
    ("commissioning", re.compile(r"commission|start[- ]?up|check[- ]?out|acceptance|demonstrat", re.I)),
    ("submittals", re.compile(r"submittals?", re.I)),
)


@dataclass(frozen=True)
class DossierImage:
    path: str            # absolute PNG path in cache_dir / "dossier-images"
    what: str            # "H601 HVAC SCHEDULES — picture schedule" | "M-701.00 schedule, table unreadable"
    sheet: str | None
    document: str
    page: int


@dataclass(frozen=True)
class Dossier:
    job_name: str
    text: str                       # the whole dossier as one plain-text document with numbered sections
    images: tuple[DossierImage, ...]
    sources: dict[str, str]         # source id -> "where", e.g. "S3" -> "23 09 93 SEQUENCE ..., Specs.pdf page 44"
    families: tuple                 # reading.totals as-is
    device_totals: dict[str, int]   # label -> total across controls-discipline plan sheets, floors applied
    counts: dict[str, dict]         # family prefix -> {"schedule_rows", "quantity_column", "plan_placements",
                                    #                   "riser", "distinct_tags"}
    stats: dict[str, int]           # characters per section, page counts, image count
    sections: dict = field(default_factory=dict)   # "Q7" -> (the sequence heading, the source ids under it)
    schedules: tuple = ()       # estimator.reading.schedules.Schedule, when the reading is still in hand
    sheet_pages: dict = field(default_factory=dict)   # 7c source id -> the (document, page) whose text it gives


# ---- small helpers ------------------------------------------------------------------------------

# the job's documents' names (`document_names`), set by `build_dossier` while it builds: a file name two documents
# share is cited by each one's path, so their places never read alike
_NAMES: ContextVar[dict[str, str]] = ContextVar("dossier_document_names", default={})


def _name(document: str) -> str:
    return _NAMES.get().get(document) or document.rsplit("/", 1)[-1]


def _squash(text: str | None) -> str:
    return " ".join((text or "").split())


_REPEAT = re.compile(r"(?<!\S)(\S{1,24})(?: \1(?!\S)){2,}")


def _collapse_repeats(text: str) -> str:
    """A label printed at every symbol on a plan ("EPIV EPIV EPIV …") is given once with its count ("EPIV ×9"),
    so the sheet's notes are not cut away behind the labels."""
    return _REPEAT.sub(lambda m: f"{m.group(1)} ×{len(m.group(0).split())}", text)


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _natural(tag: str) -> list:
    return [(0, int(part), "") if part.isdigit() else (1, 0, part) for part in re.split(r"(\d+)", tag)]


def _prefix(tag: str) -> str:
    return tag_prefix(tag)


def _plural(n: int, word: str, many: str | None = None) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {many or word + 's'}"


def _place(sheet: str | None, document: str, page: int) -> str:
    return f"{sheet}, {_name(document)} page {page}" if sheet else f"{_name(document)} page {page}"


class _Ids:
    """Source ids, short and unique, each resolving to the place it came from; and the sequence's (and the
    points list's) section blocks, Q1, Q2 …, each with its heading and the paragraphs under it."""

    def __init__(self) -> None:
        self.where: dict[str, str] = {}
        self._n = 0
        self.sections: dict[str, tuple[str, list[str]]] = {}

    def new(self, where: str) -> str:
        self._n += 1
        sid = f"S{self._n}"
        self.where[sid] = where
        return sid

    def section(self, heading: str, where: str) -> str:
        qid = f"Q{len(self.sections) + 1}"
        self.sections[qid] = (heading, [])
        self.where[qid] = f"sequence section “{heading}”, {where}"
        return qid


# ---- the sequence's section headings ---------------------------------------------------------------------

_SECTION_MARKER = re.compile(r"^(?P<marker>[A-Z][.)]|\d{1,2}\.\d{1,2}\.?|\d{1,2}[.)])\s+(?P<title>\S.*)$")
_SECTION_VERBS = re.compile(r"\b(?:shall|will|must|should|may|is|are|be|provide|provided|refer|submit|comply|"
                            r"coordinate|confirm|store|conceal|include|includes|furnish|install)\b", re.I)
SECTION_MARK = "--- [{qid}] {heading} ---"
_SECTION_LINE = re.compile(r"^--- \[(Q\d+)\] (.+?) ---$")
_ID_LINE = re.compile(r"^\[([A-Z]{1,3}\d+)\]")
_BLOCK_END = re.compile(r"^(?:== \d|--- 7[bc] )")
_PAGE_LINE = re.compile(r"^--- (.+) page \d+ ---$")
SECTION_WORDS = 12          # a heading is a title: at most this many words
SECTION_CHARACTERS = 90


def is_section_heading(paragraph: str) -> bool:
    """A lettered or numbered title of the sequence ("C. DRYER EXHAUST AND MAKE-UP AIR FANS", "1. RTU-1 AND RTU-2",
    "3.1 AIR HANDLING UNITS", "D. Outdoor Air Fan:"), never a sentence ("A. AHU-1 shall run …"), a list item ("a.
    Outdoor air temperature"), a sub-list label ("1. DDC points:") or a definition ("H. E/P: Electric to pneumatic.").
    A plain number ("1.") starts a heading only in capitals."""
    text = _squash(paragraph)
    m = _SECTION_MARKER.match(text)
    if m is None or len(text) > SECTION_CHARACTERS:
        return False
    marker, title = m.group("marker"), m.group("title").strip()
    words = title.split()
    if len(words) > SECTION_WORDS or _SECTION_VERBS.search(title) or title[-1] in ",;":
        return False
    letters = [c for c in title if c.isalpha()]
    if not letters or not title[0].isalnum():
        return False
    if re.fullmatch(r"\d{1,2}[.)]", marker):             # "1." — a heading only in capitals, with no stop or colon
        upper = sum(c.isupper() for c in letters) / len(letters)
        return upper >= 0.8 and title[-1] not in ".:"
    if title.endswith("."):
        return len(words) <= 6 and ":" not in title
    return ":" not in title[:-1]


def sections_in(text: str) -> dict[str, tuple[str, tuple[str, ...]]]:
    """The section blocks a dossier's text marks ("--- [Q7] C. DRYER … ---"): each Q id with its heading and the
    source ids of the paragraphs under it, up to the next section, the next numbered part of the dossier, or the
    points list's own part. Page lines ("--- … page 3 ---") do not end a section."""
    found: dict[str, tuple[str, list[str]]] = {}
    current, place = None, None
    for line in (text or "").splitlines():
        m = _SECTION_LINE.match(line)
        if m:
            current = m.group(1)
            found[current] = (m.group(2), [])
            continue
        if _BLOCK_END.match(line) or line.startswith("== "):
            current, place = None, None
            continue
        page = _PAGE_LINE.match(line)
        if page:
            if page.group(1) != place:                 # another document: no section runs on
                current = None
            place = page.group(1)
            continue
        sid = _ID_LINE.match(line)
        if sid and current is not None:
            found[current][1].append(sid.group(1))
    return {q: (heading, tuple(ids)) for q, (heading, ids) in found.items()}


# ---- the floor multiplier -------------------------------------------------------------------------

def floor_multipliers(catalogue, reading) -> dict[tuple[str, str], int]:
    """(document, sheet number), or (document, page) for a sheet with no number, -> how many floors that plan
    stands for. A typical plan whose title names a floor range stands for the range's floors; otherwise a sheet
    number on N pages of one document stands for N. Sheets not listed stand for one."""
    return {key: len(floors) for key, floors in plan_floors(catalogue, getattr(reading, "typicals", ())).items()}


def _counted_pages(catalogue, reading) -> frozenset[tuple[str, int]]:
    """The drawing pages counted: the governing page of each sheet, and of a sheet on several pages of
    one document with the same text on every page, the first page only (the multiplier stands for the rest,
    `inventory.first_pages`); pages of one number with other text are each counted (REVIEW-FINAL6 F6)."""
    governing = governing_pages(catalogue, getattr(reading, "supersessions", ()),
                                typical_places(getattr(reading, "typicals", ())))
    repeated = first_pages(catalogue)
    return frozenset((sheet.document, sheet.page) for sheet in catalogue.sheets
                     if (sheet.document, sheet.page) in governing and (sheet.document, sheet.page) not in repeated)


def _counted_plan_pages(catalogue, reading) -> frozenset[tuple[str, int]]:
    """The pages the counts line reads: the inventory's own (`counting_pages`), so the two count the same sheets; a
    plan sheet in two documents with the same text is two sheets (REVIEW-FINAL5 F7)."""
    return counting_pages(catalogue, governing_pages(catalogue, getattr(reading, "supersessions", ()),
                                                     typical_places(getattr(reading, "typicals", ()))))


# ---- section 1: the job ---------------------------------------------------------------------------

def _found_place(found) -> str:
    if not found.places:
        return ""
    p = found.places[0]
    label = p.section or p.sheet
    return f"{label}, {_name(p.document)} page {p.page}" if label else f"{_name(p.document)} page {p.page}"


def _quoted(found) -> str:
    return f" — “{_squash(found.quote)}”" if found.quote else ""


def _job_section(catalogue, reading, ids: _Ids) -> list[str]:
    job = catalogue.job
    lines = [f"[{ids.new(f'the job folder {job.name}')}] Job: {job.name}"]
    dates: dict[str, object] = {}
    for version in getattr(reading, "versions", ()):
        if version.latest and (version.document not in dates or version.latest > dates[version.document]):
            dates[version.document] = version.latest
    for d in job.documents:
        date = dates.get(d.relative)
        bits = [d.kind, _plural(d.pages, "page")]
        if d.revision and d.revision != "base":
            bits.append(f"revision {d.revision}")
        if date:
            bits.append(f"latest issue dated {date.isoformat()}")
        if d.duplicate_of:
            bits.append(f"the same file as {_name(d.duplicate_of)}, catalogued once")
        sid = ids.new(f"{d.relative} (the document list)")
        lines.append(f"[{sid}] Document: {_name(d.relative)} — {', '.join(bits)}")
    addenda = [d for d in job.documents if d.kind == "addendum" or (d.revision and d.revision != "base")]
    if addenda:
        sid = ids.new("the document list")
        lines.append(f"[{sid}] Addenda and revised documents: {', '.join(_name(d.relative) for d in addenda)}")
    disciplines = {(s.document, s.page): s.discipline for s in catalogue.sheets}
    others = 0
    for s in getattr(reading, "supersessions", ()):
        controls = (disciplines.get((s.current.document, s.current.page)) in CONTROLS_DISCIPLINES
                    or any(c.affects_controls for c in s.changes))
        if not controls:
            others += 1
            continue
        sid = ids.new(_place(s.sheet, s.current.document, s.current.page))
        lines.append(f"[{sid}] Sheet {s.sheet} replaced by a later issue: {_squash(s.note)}")
    if others:
        lines.append(f"({_plural(others, 'other sheet')} of other trades replaced by a later issue, "
                     f"no change there affecting controls)")
    bid = getattr(catalogue, "bid", None)
    if bid is not None:
        sid = ids.new("the bid check (all pages searched)")
        lines.append(f"[{sid}] Bid check: {bid.finding} — {_squash(bid.reason)}")
    overview = catalogue.overview
    for maker in overview.makers:
        if maker.priced:
            continue
        where = _found_place(maker)
        sid = ids.new(where or "the Spec overview")
        terms = f" ({maker.terms})" if maker.terms else ""
        lines.append(f"[{sid}] Controls platform named: {maker.maker}{terms}{_quoted(maker)}")
    for topic in overview.topics:
        if topic.status not in (FOUND, RULED_OUT):
            continue
        status = "ruled out" if topic.status == RULED_OUT else "found"
        sid = ids.new(_found_place(topic) or "the Spec overview")
        lines.append(f"[{sid}] {topic.section} — {topic.item}: {status}{_quoted(topic)}")
    for found in overview.who_does_what:
        sid = ids.new(_found_place(found) or "the Spec overview")
        lines.append(f"[{sid}] Who does what ({found.item}){_quoted(found)}")
    if overview.who_does_what_more:
        lines.append(f"(and {_plural(overview.who_does_what_more, 'more who-does-what sentence')}, not listed)")
    for found in overview.standard_lines:
        if found.status != FOUND:
            continue
        what = ("Standard exclusion the job speaks to" if found.section == STANDARD_EXCLUSION
                else "Standard clarification the job speaks to" if found.section == STANDARD_CLARIFICATION
                else found.section)
        sid = ids.new(_found_place(found) or "the Spec overview")
        lines.append(f"[{sid}] {what}: {found.item}{_quoted(found)}")
    for heading, group in (("Service", overview.services), ("Other system to connect to", overview.integrations),
                           ("Special system", overview.special_systems),
                           ("Project condition", overview.conditions)):
        for found in group:
            if found.status not in (FOUND, RULED_OUT):
                continue
            extra = []
            if found.amount:
                extra.append(found.amount)
            if found.protocol:
                extra.append(f"protocol: {found.protocol}")
            if found.status == RULED_OUT:
                extra.append("ruled out")
            detail = f" ({'; '.join(extra)})" if extra else ""
            sid = ids.new(_found_place(found) or "the Spec overview")
            lines.append(f"[{sid}] {heading}: {found.item}{detail}{_quoted(found)}")
    return lines


# ---- sections 2 and 3: the sequence of operation and the points list -------------------------------

def _label(where: str) -> str:
    label = re.sub(r"\s*\([^()]*\)\s*$", "", where).strip()
    return re.sub(r"^sequence inside\s+", "", label)


def _later(document) -> bool:
    return document is not None and (document.kind == "addendum" or (document.revision or "base") != "base")


def _running_key(line: str) -> str:
    return re.sub(r"\d+", "#", _squash(line))


def _edge_lines(text: str) -> list[str]:
    lines = [line for line in text.splitlines() if _squash(line)]
    return lines[:EDGE_LINES] + lines[-EDGE_LINES:]


def _running_lines(texts: list[str]) -> set[str]:
    """Lines at the top or foot of most pages of one backbone — the project name, the section's footer —
    with their digits ignored, so "230993 - 4" matches on every page. A bare list marker is never one,
    and a line in the body of the page is never one (a points list repeats its lines system by system)."""
    if len(texts) < 3:
        return set()
    seen: Counter = Counter()
    for text in texts:
        seen.update({_running_key(line) for line in _edge_lines(text)})
    need = max(3, int(len(texts) * RUNNING_SHARE + 0.999))
    return {line for line, n in seen.items()
            if n >= need and len(line) >= 3 and not _LIST_MARKER.match(line) and not _LIST_ITEM.match(line)}


def _without_running(text: str, running: set[str]) -> str:
    lines = text.splitlines()
    filled = [i for i, line in enumerate(lines) if _squash(line)]
    edge = set(filled[:EDGE_LINES] + filled[-EDGE_LINES:])
    return "\n".join(line for i, line in enumerate(lines) if not (i in edge and _running_key(line) in running))


def _page_paragraphs(texts: dict[tuple[str, int], str], document: str, first: int, last: int) -> list[tuple[int, str]]:
    pages = [(page, texts.get((document, page), "")) for page in range(first, last + 1)]
    running = _running_lines([text for _, text in pages])
    found = []
    for page, text in pages:
        if running:
            text = _without_running(text, running)
        found += [(page, _squash(p)) for p in _paragraphs(text) if _squash(p)]
    return found


@dataclass
class _Printed:
    """What sections 2 and 3 printed: pages, paragraph texts (-> where they were given), the spec
    sections given whole, and those left out because a later copy replaces them."""
    pages: set = field(default_factory=set)
    norms: dict = field(default_factory=dict)
    sections: set = field(default_factory=set)
    replaced: set = field(default_factory=set)
    place: tuple = ()               # the (label, document) of the page last printed
    section: str | None = None      # the sequence section (Q id) the paragraphs now printed belong to


def _backbone_section(catalogue, reading, what: str, ids: _Ids, printed: _Printed,
                      texts: dict[tuple[str, int], str]) -> tuple[list[str], int]:
    documents = {d.relative: d for d in catalogue.job.documents}
    order = {d.relative: i for i, d in enumerate(catalogue.job.documents)}
    items = [b for b in reading.backbone if b.what == what and not b.duplicate_of]
    items.sort(key=lambda b: (order.get(b.document, len(order)), b.first_page))
    lines: list[str] = []
    printed.place, printed.section = (), None
    # A spec section issued again in an addendum (or a later revision) is replaced by it: the later
    # copy is given, the older one named only.
    by_label: dict[str, list] = defaultdict(list)
    for b in items:
        if b.kind == "spec section":
            by_label[_label(b.where)].append(b)
    replaced = set()
    for label, group in by_label.items():
        later = [b for b in group if _later(documents.get(b.document))]
        if later and len(later) < len(group):
            keep = later[-1]
            for b in group:
                if b is not keep:
                    replaced.add(id(b))
                    lines.append(f"({b.where} is replaced by the copy in {_name(keep.document)}; "
                                 f"only that copy is given)")
                    printed.replaced.add((b.document, b.first_page, b.last_page))
    page_count = 0
    for b in items:
        if id(b) in replaced:
            continue
        paragraphs = [(page, p) for page, p in _page_paragraphs(texts, b.document, b.first_page, b.last_page)
                      if (b.document, page) not in printed.pages]
        if not paragraphs:
            continue
        total = sum(len(p) for _, p in paragraphs) or 1
        repeated = [(page, p) for page, p in paragraphs if _norm(p) in printed.norms]
        share = sum(len(p) for _, p in repeated) / total
        label = _label(b.where)
        copy_of = None
        if share >= COPY_SHARE:
            copy_of = Counter(printed.norms[_norm(p)] for _, p in repeated).most_common(1)[0][0]
            lines.append(f"({b.where} repeats {copy_of} — {round(share * 100)}% of its text is given above; "
                         f"only its paragraphs that differ are given here)")
            paragraphs = [(page, p) for page, p in paragraphs if _norm(p) not in printed.norms]
        current = None
        for page, text in paragraphs:
            if page != current:
                current = page
                page_count += 1
                if (label, _name(b.document)) != printed.place:      # another document: no section runs on
                    printed.place, printed.section = (label, _name(b.document)), None
                lines.append(f"--- {label}, {_name(b.document)} page {page} ---")
            if is_section_heading(text):
                printed.section = ids.section(_squash(text), f"{label}, {_name(b.document)} page {page}")
                lines.append(SECTION_MARK.format(qid=printed.section, heading=_squash(text)))
            sid = ids.new(f"{label}, {_name(b.document)} page {page}")
            lines.append(f"[{sid}] {text}")
            if printed.section is not None:
                ids.sections[printed.section][1].append(sid)
        for page, text in paragraphs:
            printed.norms.setdefault(_norm(text), label)
        printed.pages.update((b.document, page) for page in range(b.first_page, b.last_page + 1))
        if b.kind == "spec section" and copy_of is None:
            printed.sections.add((b.document, b.first_page, b.last_page))
    return lines, page_count


# ---- section 4: the schedules, and the pictures of them --------------------------------------------

def _picture_boxes(page: pymupdf.Page) -> list[pymupdf.Rect]:
    """The page's pictures, in the page's coordinates as viewed (what `get_pixmap(clip=)` takes),
    overlapping ones merged, small ones left out, in reading order."""
    area = abs(page.rect)
    if area <= 0:
        return []
    boxes = []
    for info in page.get_image_info():
        box = (pymupdf.Rect(info["bbox"]) * page.rotation_matrix) & page.rect
        if not box.is_empty and abs(box) >= MIN_PICTURE * area:
            boxes.append(pymupdf.Rect(box))
    merged = True
    while merged:
        merged = False
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                if boxes[i].intersects(boxes[j]):
                    boxes[i] = boxes[i] | boxes[j]
                    del boxes[j]
                    merged = True
                    break
            if merged:
                break
    band = page.rect.height * 0.05 or 1
    return sorted(boxes, key=lambda b: (int(b.y0 // band), b.x0))


def _dpi(rect: pymupdf.Rect, dpi: int) -> int:
    inches = (rect.width / 72) * (rect.height / 72)
    if inches <= 0:
        return dpi
    return max(36, min(dpi, int((MAX_PIXELS / inches) ** 0.5)))


def _render(page: pymupdf.Page, clip: pymupdf.Rect | None, dpi: int, folder: Path, key: str) -> Path:
    """The picture's PNG, written whole under a name no other run uses and then moved into place;
    an existing file for the same document, page, area and resolution is reused."""
    path = folder / f"{hashlib.sha1(key.encode('utf-8')).hexdigest()[:20]}.png"
    if path.exists() and path.stat().st_size > 0:
        return path
    folder.mkdir(parents=True, exist_ok=True)
    pixmap = page.get_pixmap(clip=clip, dpi=_dpi(clip if clip is not None else page.rect, dpi))
    tmp = path.with_name(f"{path.stem}.{os.getpid()}-{secrets.token_hex(4)}.tmp.png")
    try:
        pixmap.save(str(tmp))
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()
    return path


# each document's content hash for this process, by (path, size, date): a document is read once however many of
# its pages are pictured; a later run hashes it afresh (`_file_key`)
_DIGESTS: dict[tuple[str, int, int], str] = {}


def _file_key(path: Path) -> str:
    """The document's content hash (sha1, as `PageOpener.digest` names its cache files), never its size and date
    alone: a file rewritten with other content and its date set back is pictured again (LDG-15)."""
    try:
        stat = path.stat()
        memo = (str(Path(path).resolve()), stat.st_size, stat.st_mtime_ns)
        if memo not in _DIGESTS:
            with open(path, "rb") as handle:
                _DIGESTS[memo] = hashlib.file_digest(handle, "sha1").hexdigest()
        return _DIGESTS[memo]
    except OSError:
        return "missing"


def _schedule_images(catalogue, reading, counted: frozenset, cache_dir: Path | None
                     ) -> tuple[dict[tuple[str, int], list[DossierImage]], dict[tuple[str, int], str], list[str]]:
    """Pictures of every schedule sheet whose schedules are pictures, were counted from the sheet's text,
    or couldn't be read at all. Returns the images by page, why each page was pictured, and flags."""
    sheets = {(s.document, s.page): s for s in catalogue.sheets}
    records = {(p.document, p.page): p for p in catalogue.pages}
    read_pages = {(s.document, s.page) for s in reading.schedules}
    candidates: dict[tuple[str, int], str] = {}
    for s in reading.schedules:
        key = (s.document, s.page)
        if s.from_text:
            candidates[key] = "counted from the sheet's text; the table couldn't be read"
        else:
            candidates.setdefault(key, "")
    for sheet in catalogue.sheets:
        key = (sheet.document, sheet.page)
        if ("Schedules" in sheet.types and sheet.discipline in CONTROLS_DISCIPLINES and key in counted
                and key not in read_pages):
            record = records.get(key)
            if record is not None and record.status != "blank":
                candidates[key] = "no schedule could be read from it"
    images: dict[tuple[str, int], list[DossierImage]] = {}
    why: dict[tuple[str, int], str] = {}
    flags: list[str] = []
    if not candidates:
        return images, why, flags
    paths = {d.relative: Path(d.path) for d in catalogue.job.documents}
    folder = Path(cache_dir).resolve() / IMAGES_FOLDER if cache_dir is not None else None
    opened: dict[str, pymupdf.Document] = {}
    try:
        for key in sorted(candidates, key=lambda k: (list(paths).index(k[0]) if k[0] in paths else 0, k[1])):
            document, number = key
            reason = candidates[key]
            sheet = sheets.get(key)
            label = " ".join(x for x in (sheet.number if sheet else None, sheet.title if sheet else None) if x)
            label = label or f"{_name(document)} page {number}"
            try:
                if document not in opened:
                    opened[document] = pymupdf.open(str(paths[document]))
                page = opened[document][number - 1]
                boxes = _picture_boxes(page)
                area = abs(page.rect) or 1
                covered = sum(abs(b) for b in boxes) / area
                if not reason and covered < PICTURE_SHARE:
                    continue                  # a table read from the text layer: nothing to picture
                if folder is None:
                    flags.append(f"{label}: not pictured — no cache folder to keep pictures in")
                    continue
                base = f"v{IMAGE_VERSION}|{document}|{_file_key(paths[document])}|{number}"
                one_picture = any(abs(b) >= ONE_PICTURE * area for b in boxes)
                if covered >= PICTURE_SHARE and not one_picture:
                    found = []
                    for i, box in enumerate(boxes, start=1):
                        clip = f"{box.x0:.1f},{box.y0:.1f},{box.x1:.1f},{box.y1:.1f}"
                        path = _render(page, box, PICTURE_DPI, folder, f"{base}|{clip}|{PICTURE_DPI}")
                        part = f", picture {i} of {len(boxes)}" if len(boxes) > 1 else ""
                        found.append(DossierImage(str(path), f"{label} — picture schedule{part}",
                                                  sheet.number if sheet else None, document, number))
                    images[key] = found
                    why[key] = reason or "the schedules are pictures"
                else:
                    path = _render(page, None, SHEET_DPI, folder, f"{base}|sheet|{SHEET_DPI}")
                    what = (f"{label} — picture schedule (the whole sheet)" if one_picture or covered >= PICTURE_SHARE
                            else f"{label} — schedule, table unreadable")
                    images[key] = [DossierImage(str(path), what, sheet.number if sheet else None, document, number)]
                    why[key] = reason or "the sheet is one picture"
            except Exception as error:
                flags.append(f"{label}: could not be pictured — {_squash(str(error)) or type(error).__name__}")
    finally:
        for pdf in opened.values():
            pdf.close()
    return images, why, flags


def sheet_pictures(catalogue, cache_dir: Path | None, keys: list[tuple[str, int]], what: str
                   ) -> tuple[list[DossierImage], list[str]]:
    """Whole-sheet pictures of the (document, page) sheets given, at SHEET_DPI, for a reading pass (plans,
    risers). The render key is the schedules pass's whole-sheet key, so a sheet already pictured is reused. A
    sheet that cannot be pictured gives no picture and a flag."""
    sheets = {(s.document, s.page): s for s in getattr(catalogue, "sheets", ()) or ()}
    job = getattr(catalogue, "job", None)
    paths = {d.relative: Path(d.path) for d in getattr(job, "documents", ()) or ()}
    folder = Path(cache_dir).resolve() / IMAGES_FOLDER if cache_dir is not None else None
    images: list[DossierImage] = []
    flags: list[str] = []
    opened: dict[str, pymupdf.Document] = {}
    try:
        for document, number in keys:
            sheet = sheets.get((document, number))
            label = " ".join(x for x in (sheet.number if sheet else None, sheet.title if sheet else None) if x)
            label = label or f"{_name(document)} page {number}"
            if folder is None:
                flags.append(f"{label}: not pictured — no cache folder to keep pictures in")
                continue
            try:
                if document not in paths:
                    raise ValueError(f"{_name(document)} is not among the job's documents")
                if document not in opened:
                    opened[document] = pymupdf.open(str(paths[document]))
                if not 1 <= number <= opened[document].page_count:
                    raise IndexError(f"page {number} is not in {_name(document)}")
                page = opened[document][number - 1]
                key = f"v{IMAGE_VERSION}|{document}|{_file_key(paths[document])}|{number}|sheet|{SHEET_DPI}"
                path = _render(page, None, SHEET_DPI, folder, key)
                images.append(DossierImage(str(path), f"{label} — {what}", sheet.number if sheet else None,
                                           document, number))
            except Exception as error:
                flags.append(f"{label}: could not be pictured — {_squash(str(error)) or type(error).__name__}")
    finally:
        for pdf in opened.values():
            pdf.close()
    return images, flags


def _cell(text: str | None) -> str:
    return _squash(text) or "-"


def _schedules_section(catalogue, reading, ids: _Ids, images: dict, why: dict, image_ids: dict,
                       flags: list[str]) -> list[str]:
    lines: list[str] = []
    sheets = {(s.document, s.page): s for s in catalogue.sheets}
    pictured: set = set()
    for schedule in reading.schedules:
        key = (schedule.document, schedule.page)
        where = _place(schedule.sheet, schedule.document, schedule.page)
        sid = ids.new(f"{schedule.sheet + ' ' if schedule.sheet else ''}{schedule.title}, "
                      f"{_name(schedule.document)} page {schedule.page}")
        extras = []
        if schedule.passive:
            extras.append("air-device types (diffusers, grilles, louvers), passive: not equipment, no controller")
        elif schedule.type_only:
            extras.append("type rows, no unit tags")
        if schedule.from_text:
            extras.append("counted from the sheet's text; the table couldn't be read")
        lines.append(f"[{sid}] {schedule.title} — {where} ({_plural(len(schedule.rows), 'row')}"
                     f"{'; ' + '; '.join(extras) if extras else ''})")
        if key in images:
            names = ", ".join(image_ids[id(img)] for img in images[key])
            lines.append(f"    See {'image' if len(images[key]) == 1 else 'images'} {names}.")
            pictured.add(key)
        headers = list(schedule.headers)
        if headers:
            lines.append(f"    Columns: {' | '.join(_cell(h) for h in headers)}")
        for row in schedule.rows:
            first = row.tag or _cell(row.cells.get(headers[0]) if headers else None)
            cells = [_cell(row.cells.get(h)) for h in headers[1:]] if headers else []
            mark = " (EXISTING)" if row.existing else ""
            rid = ids.new(f"{schedule.title} row {first}, {where}")
            lines.append(f"[{rid}] {' | '.join([first + mark] + cells)}")
        for note in schedule.notes:
            nid = ids.new(f"{schedule.title} notes, {where}")
            lines.append(f"[{nid}] Note: {_squash(note)}")
        for sentence in schedule.controls_by:
            cid = ids.new(f"{schedule.title} notes, {where}")
            lines.append(f"[{cid}] Unit controls by: {_squash(sentence)}")
    for key, found in images.items():
        if key in pictured:
            continue
        sheet = sheets.get(key)
        where = _place(sheet.number if sheet else None, key[0], key[1])
        sid = ids.new(f"schedule sheet {where}")
        names = ", ".join(image_ids[id(img)] for img in found)
        lines.append(f"[{sid}] Schedule sheet {where}: {why.get(key, '')} — see "
                     f"{'image' if len(found) == 1 else 'images'} {names}.")
    lines += [f"({flag})" for flag in flags]
    return lines


# ---- section 5: the equipment counts -----------------------------------------------------------------

def _is_quantity(header: str) -> bool:
    key = header_key(header)
    return any(key == h or key.startswith(h + " ") for h in _QUANTITY_HEADERS)


def _number(text: str | None) -> int | None:
    m = _INT.match(_squash(text))
    return int(m.group(1)) if m else None


def _type_code(schedule, row) -> str | None:
    """A type row's code ("HPAC") stands for its family when the schedule lists units by type."""
    if row.tag or not schedule.headers:
        return None
    code = _squash(row.cells.get(schedule.headers[0])).upper()
    if not _TYPE_CODE.match(code) or code in {header_key(h) for h in schedule.headers}:
        return None
    return code


@dataclass
class _Family:
    rows: int = 0                       # schedule rows, not existing
    quantity: int | None = None         # the QUANTITY column's total, when the schedule has one
    scheduled: set = field(default_factory=set)
    on_plans: set = field(default_factory=set)
    placements: int = 0                 # on the controls plan sheets, floors applied: a unit once, a type every place
    by_sheet: list = field(default_factory=list)    # (sheet, count on its first page, floors)
    riser: int = 0
    notes: list = field(default_factory=list)       # why the placements are likely above the other counts
    causes: list = field(default_factory=list)      # those causes' keys (COUNT_CAUSE_WORDS), for the line's head
    air_only: bool = False              # no unit at all: only an air outlet schedule's codes (`air_outlet_notes`) made this
                                        # line; it is printed with its note and is no family of the counts


def _unindexed_plan_tags(plan_sheets: list[tuple], equipment: Equipment, sheet_numbers: frozenset[str]) -> set[str]:
    """The plan tags the catalogue's tag index (`index_tags`) leaves out. A tag of a schedule-only prefix (B, P, IU, SS: also
    an air outlet's code, a model number ...) is in the index only when a schedule sheet names it, so a boiler B-1 on the
    plans whose schedule is not among the documents is not. Read here from the text of the counted plan and riser sheets,
    the job's own sheet numbers left out (P-101 is a sheet, not a pump)."""
    return {tag for _sheet, _key, record, *_ in plan_sheets
            for tag in find_tags(record.text, equipment, sheet_numbers) if tag_prefix(tag) in equipment.schedule_only}


def _unlisted_notes(prefix: str, family: _Family, equipment: Equipment) -> list[str]:
    """The reading note for the tags of a schedule-only prefix that are on the plans and in no schedule read: what they are
    is not confirmed, since the prefix is also used for other things (an air outlet's code among them), but they are counted
    as units: a count that is too low is the worst error. Never in a client cause's words."""
    tags = sorted(family.on_plans - family.scheduled, key=_natural) if prefix in equipment.schedule_only else []
    if not tags:
        return []
    named = ", ".join(tags[:CAUSE_EXAMPLES]) + (f" and {len(tags) - CAUSE_EXAMPLES} more" if len(tags) > CAUSE_EXAMPLES else "")
    return [f"{named} on the plans and in no schedule read: the kind of unit is not confirmed (the prefix {prefix} is also used "
            f"for other things), counted as {'units' if len(tags) > 1 else 'a unit'}; check"]


def _counts(catalogue, reading, counted_pages: frozenset, multipliers: dict) -> dict[str, _Family]:
    equipment = Equipment.load()
    type_titles = vocabulary().type_titles
    families: dict[str, _Family] = defaultdict(_Family)
    blocks: set = set()
    on_page: dict[tuple[str, int], Counter] = defaultdict(Counter)
    codes: set[str] = set()
    typed: set[str] = set()          # tags the schedule calls a type: a QUANTITY column that gives no number (F1)
    counted_rows: set[int] = set()
    for schedule in reading.schedules:
        block = (schedule.document, schedule.page, tuple(row.tag for row in schedule.rows))
        if len(block[2]) >= 2 and all(block[2]) and block in blocks:
            continue                 # one schedule set out in two blocks (fan data, then coil data)
        blocks.add(block)
        quantity = next((h for h in schedule.headers if _is_quantity(h)), None)
        typing = quantity_header(schedule)       # the inventory's own test (`_as_type`), so the two agree
        for row in schedule.rows:
            if row.tag:
                key = _prefix(row.tag)
                on_page[(schedule.document, schedule.page)][row.tag] += 1
                if (typing and getattr(row, "shares", 1) == 1 and not row.existing
                        and _number(row.cells.get(typing)) is None):
                    typed.add(row.tag)
            else:
                key = _type_code(schedule, row)
                if key is None or type_titles.search(schedule.title) or schedule.passive:
                    continue         # an air device's type code (CD, RG, LRD-A) is no equipment family (HP 20)
                codes.add(key)
                on_page[(schedule.document, schedule.page)][key] += 1
            if row.existing:
                continue
            family = families[key]
            family.rows += 1
            if row.tag:
                family.scheduled.add(row.tag)
            n = _number(row.cells.get(quantity)) if quantity else None
            if n is not None and id(row.cells) in counted_rows:
                continue             # one row naming several tags ("A THRU C"): its quantity counted once
            counted_rows.add(id(row.cells))
            if n is not None:
                family.quantity = (family.quantity or 0) + n
    # an air device's code read as a tag (B1 is B-1, the boiler's, on a schedule sheet; SD-1 a smoke damper's) is no unit
    # of any family on the plans (HP 3): only a unit a non-air-device schedule lists keeps its tag
    air_codes = set(air_outlet_codes(reading.schedules, equipment))
    exclude = frozenset(tag for s in catalogue.sheets if s.number for tag in find_tags(s.number, equipment))
    records = {(p.document, p.page): p for p in catalogue.pages}
    plan_sheets: list[tuple] = []
    demolition: list[tuple] = []      # ruling 1 (T-005a): demolition plans, their units left out unless work is named
    for sheet in catalogue.sheets:
        key = (sheet.document, sheet.page)
        record = records.get(key)
        if key not in counted_pages or record is None or sheet.discipline not in CONTROLS_DISCIPLINES:
            continue
        is_plan = "Plans" in sheet.types
        is_riser = bool(_RISER.search(sheet.title or ""))
        if (is_plan or is_riser) and is_demolition(sheet):
            demolition.append((sheet, key, record, True, False))
        elif is_plan or is_riser:
            plan_sheets.append((sheet, key, record, is_plan, is_riser))
    # A plan tag is left out of the units only when an air outlet schedule of this job lists it as an air outlet's code
    # (`air_codes`), and even then a unit schedule that lists it keeps it. Every other plan tag stays: the tag index leaves
    # out a B-1 that no schedule sheet names (`_unindexed_plan_tags`), and the counts line says its kind is not confirmed.
    unindexed = _unindexed_plan_tags(plan_sheets, equipment,
                                     sheet_number_tags((s.number for s in catalogue.sheets), equipment))
    valid = (({t.tag for t in catalogue.tags} | unindexed) - air_codes) | {t for f in families.values() for t in f.scheduled}
    code_patterns = {code: re.compile(rf"(?<![A-Za-z0-9\-]){re.escape(code)}(?![A-Za-z0-9])") for code in codes}
    read: list[tuple] = [
        (sheet, key, record, is_plan, is_riser,
         Counter(tag for tag in find_tags("\n".join(s.text for s in record.edge_spans), equipment, exclude) if tag in valid))
        for sheet, key, record, is_plan, is_riser in plan_sheets + demolition]
    demolished = {key for _sheet, key, *_ in demolition}
    # A tag in the title-block strip of most of these sheets is the title block's own text (a project or
    # phone number that looks like a tag), not a unit: its words there aren't counted.
    in_edge = Counter(tag for *_, edge in read for tag in edge)
    title_block = {tag for tag, n in in_edge.items() if n >= max(2, len(read) / 2)}
    keys = label_keys(sorted((t for t in valid if t not in exclude), key=_natural))

    def tallies_of(key, record, edge, plan: bool = True) -> tuple[Counter, Counter]:
        """A sheet's tags as the inventory reads them, as (the count's tally, the labels' tally). The labels'
        (`line_labels`: a tag in a note is no placement, REVIEW-FINAL6 F7) is the plan groups' evidence; the count's
        is, on a plan, `plan_labels` (a unit named anywhere counts at least once, REVIEW-FINAL7 F4). Each less a
        schedule printed on the sheet and the title block's own text. Those two are taken off the tags named
        anywhere on the sheet, never off the labels alone: the count is the lower of the labels and the mentions
        less them, so a row written on one line (no label) never takes a label away. A type code counts wherever
        its pattern stands."""
        labels = line_labels(record.text, keys)
        anywhere = Counter(tag for tag in find_tags(record.text, equipment, exclude) if tag in valid)
        taken = Counter(on_page.get(key, Counter()))       # a schedule on a plan sheet names each unit once more
        taken.update({tag: n for tag, n in edge.items() if tag in title_block})
        codes = {code: len(pattern.findall(record.text)) - on_page.get(key, Counter())[code]
                 for code, pattern in code_patterns.items()}

        def less(found: Counter) -> Counter:
            tally = Counter({tag: min(n, max(n, anywhere[tag]) - taken[tag]) for tag, n in found.items()})
            for code, n in codes.items():
                tally[code] = n
            return Counter({tag: n for tag, n in tally.items() if n > 0})

        return less(plan_labels(record.text, keys, labels) if plan else labels), less(labels)

    tallies: dict[tuple[str, int], Counter] = {}
    evidence: dict[tuple[str, int], Counter] = {}       # the labels alone: which plans are one plan group
    for sheet, key, record, is_plan, is_riser, edge in read:
        tallies[key], evidence[key] = tallies_of(key, record, edge, is_plan)
    # Ruling 1 (T-005a): a demolition plan's units are left out of every new-work count. The lead's ruling on the
    # T-005a review: also a unit whose documents name work on it (`demolition_work`); the work is named beside it, for
    # the Demolition Scope block. What is left out is kept (`left_out`) so the counts line names it with both numbers.
    worked = demolition_work(catalogue, {t for key in demolished for t in tallies[key]}) if demolished else {}
    left_out: dict[tuple[str, int], Counter] = {}
    for key in demolished:
        left_out[key] = Counter(tallies[key])
        tallies[key] = Counter()
        evidence[key] = Counter()
    left_read = [entry for entry in read if entry[1] in demolished]
    read = [entry for entry in read if entry[1] not in demolished]
    # Lead rulings FINAL-I and L1, the one counting rule shared with the inventory (`plan_groups`, `plan_count`): plan
    # sheets are one plan group only when they are in one document and either show the same floor and area for other
    # trades (L1: no tag evidence needed), or their titles have the same words with a floor among them and they repeat
    # each other's unit tags (FINAL-I). In a group a unit's tag counts once and a type's tag (EBB-A, a type code, a
    # numbered tag placed as a type is) the most labels of one sheet, each times the floors the group stands for
    # (every floor once). Every other sheet is its own group, and the groups add up: when in doubt the sheets are
    # summed, the higher count, and the counts line names what may be counted twice.
    plans = [(sheet, tallies[key]) for sheet, key, _r, is_plan, *_ in read if is_plan]
    # the labels alone are the groups' evidence: the backstop (`plan_labels`) never joins two plans (FINAL-N)
    labelled_plans = [(sheet, evidence[key]) for sheet, key, _r, is_plan, *_ in read if is_plan]
    groups = plan_groups(labelled_plans, code_patterns)
    buildings = plan_buildings(sheet for sheet, _tags in labelled_plans)     # ruling 2: a unit once in each building
    doubts = [(a, b) for a, b in plan_area_doubts(labelled_plans, plan_areas(labelled_plans))
              if b not in groups.get(a, ())]
    labels = sheet_labels([*(sheet for sheet, *_ in read), *(entry[0] for entry in left_read if entry not in read)])
    floor_sets = plan_floors(catalogue, getattr(reading, "typicals", ()))
    places: dict[tuple[str, str], list] = defaultdict(list)          # (prefix, tag) -> [(sheet, places, floor set)]
    seen_on: dict[tuple[str, str], dict[str, str]] = defaultdict(dict)    # (prefix, tag) -> the sheets showing it
    printed: dict[tuple[str, str], tuple[str, int]] = {}                  # (prefix, tag) -> most places on a sheet
    unread: dict[str, list] = defaultdict(list)      # prefix -> a stated count of places not read (FINAL-O H3)
    for sheet, key, record, is_plan, is_riser, edge in read:
        label = labels[key]
        if is_plan:
            for tag, line in unread_counts(record.text, keys):
                unread[tag if tag in code_patterns else _prefix(tag)].append(
                    f"{tag} on {label} reads '{line}': the count beside it is not read (over {STATED_MOST}, or not a "
                    f"number), counted as one place; check")
        # a typical sheet with no number by its (document, page) (RD-13, `sheet_floors`)
        floors = multipliers.get((sheet.document, sheet.number) if sheet.number else (sheet.document, sheet.page), 1)
        own = sheet_floors(floor_sets, sheet)
        by_family: Counter = Counter()
        for tag, n in tallies[key].items():
            prefix = tag if tag in code_patterns else _prefix(tag)
            by_family[prefix] += n
            if is_plan:
                if tag not in code_patterns:
                    families[prefix].on_plans.add(tag)
                places[(prefix, tag)].append((key, n, own))
                seen_on[(prefix, tag)].setdefault(label, label)
                if n > printed.get((prefix, tag), ("", 1, 0))[1]:
                    printed[(prefix, tag)] = (label, n, n * floors)
        for prefix, n in by_family.items():
            family = families[prefix]
            if is_riser:
                family.riser += n
            if is_plan:
                family.by_sheet.append((label, n, floors))
    placed: Counter = Counter()                       # (prefix, tag) -> every place on every sheet, floors applied
    counted: Counter = Counter()                      # (prefix, tag) -> its count by the one counting rule
    per_place_of: dict[tuple[str, str], bool] = {}    # (prefix, tag) -> counted at every place
    each_place: dict[str, set] = defaultdict(set)     # prefix -> its tags that count at every place
    summed: dict[str, list] = defaultdict(list)       # prefix -> [(unit tag, its plan groups, count)]: 2+ groups
    labelled_often: dict[str, list] = defaultdict(list)   # prefix -> [(unit tag, sheet, labels)]: 2+ on one sheet
    for (prefix, tag), found in places.items():
        placed[(prefix, tag)] = sum(n * max(1, len(floors)) for _key, n, floors in found)
        # the labels as drawn, floors not applied: a typical sheet's floors multiply a unit, never make it a type
        drawn, most = sum(n for _key, n, _f in found), max(n for _key, n, _f in found)
        per_place = counted_per_place(tag, drawn, most, code=tag in code_patterns or tag in typed)
        count = plan_count(found, groups, per_place, buildings)
        counted[(prefix, tag)], per_place_of[(prefix, tag)] = count, per_place
        families[prefix].placements += count
        if per_place:
            each_place[prefix].add(tag)
            continue
        # ruling 2 (T-005a): one unit in the job however many plan sheets show it; the other labels are duplicates,
        # named with the number they would make if each sheet's were its own unit
        shown = list(dict.fromkeys(key for key, *_ in found))
        if len(shown) >= 2:
            each = sum(max(1, len(floors)) for key in shown
                       for floors in [frozenset().union(*(f for k, _n, f in found if k == key))])
            summed[prefix].append((tag, [labels[key] for key in shown], count, each))
        if most >= 2:
            labelled_often[prefix].append((tag, printed[(prefix, tag)][0], most))
    demolition_notes = _demolition_notes(left_read, left_out, worked, labels, places, groups, per_place_of, families,
                                         code_patterns, typed, buildings)
    extra = _copy_counts(catalogue, read, tallies_of, code_patterns, per_place_of)
    # the plan tags left out above as an air outlet's code are named, with both numbers: a drop is never silent. A prefix
    # with no other unit still gets its line, with the note (and no count: it is no family, so no system).
    air_notes = air_outlet_notes(catalogue, reading.schedules, getattr(reading, "typicals", ()), counted_pages)
    for prefix in air_notes:
        if prefix not in families:
            families[prefix] = _Family(air_only=True)
    # the families whose inventory total already says its sheets-added-up number (`FamilyTotal.summed`, its flag is
    # in the counts line): `_family_sum_note` does not say it twice
    summed_totals = {t.prefix for t in getattr(reading, "totals", ()) or () if getattr(t, "summed", None)}
    for prefix, family in families.items():
        family.notes, family.causes = _placement_causes(prefix, family, seen_on, printed, placed, each_place[prefix],
                                                        typed, counted)
        labelled = sum(n * floors for _label, n, floors in family.by_sheet)
        if labelled > family.placements:
            units = any(not per_place_of.get((p, t), False) for p, t in places if p == prefix)
            how = (("a type's tag counts the most labels of one sheet of each floor and area"
                    + (", a unit's tag once in the job" if units else "")) if each_place[prefix]
                   else "a unit's tag is counted once in the job")
            family.notes.append(f"the labels on the plan sheets add up to {labelled}; {how}, however often the plan "
                                "labels it")
        family.notes += (_family_sum_note(summed[prefix], family.placements, prefix in summed_totals)
                         + _summed_notes(summed[prefix]) + _labelled_often_notes(labelled_often[prefix]))
        family.notes += _group_notes(prefix, groups, places, labels, per_place_of)
        family.notes += _doubt_notes(prefix, doubts, places, labels)
        family.notes += list(dict.fromkeys(unread[prefix]))
        family.notes += [f"{_name(copy)} repeats {_name(original)} (same sheets, same units): read once, "
                         f"{family.placements}; if it is another building, {family.placements + n}; check"
                         for (copy, original), n in extra.get(prefix, {}).items() if n]
        family.notes += _unlisted_notes(prefix, family, equipment)
        family.notes += [air_notes[prefix]] if prefix in air_notes else []
        family.notes += demolition_notes.get(prefix, [])
    return families


def _demolition_notes(left_read: list, left_out: dict, worked: dict, labels: dict, places: dict, groups: dict,
                      per_place_of: dict, families: dict, code_patterns: dict, typed: set,
                      buildings: dict | None = None) -> dict[str, list[str]]:
    """prefix -> the counts line's reading notes for what the demolition plans show (ruling 1 of 2026-10-11, T-005a),
    each with both numbers: a unit only on demolition plans, left out ("AHU-6 is on demolition sheets only (MD
    315.00): left out of the count, 5; with the demolition sheets, 6"); a type's labels on them, left out; the work
    the documents name on a demolition unit, for the Demolition Scope (never added to the new-work count). A unit's tag also on a new-work plan changes nothing (one
    unit in the job, ruling 2) and is not named. Only families that have a counts line are named."""
    on_demo: dict[tuple[str, str], list] = defaultdict(list)
    for sheet, key, *_rest in left_read:
        for tag, n in left_out.get(key, Counter()).items():
            prefix = tag if tag in code_patterns else _prefix(tag)
            on_demo[(prefix, tag)].append((key, n, frozenset()))
    notes: dict[str, list[str]] = defaultdict(list)
    units: dict[str, list] = defaultdict(list)          # prefix -> [(tag, sheets)]: only on demolition plans
    for (prefix, tag), demo in sorted(on_demo.items(), key=lambda item: (item[0][0], _natural(item[0][1]))):
        if prefix not in families or families[prefix].air_only:
            continue
        found = places.get((prefix, tag), [])
        sheets = list(dict.fromkeys(labels[key] for key, _n, _f in demo))
        drawn, most = sum(n for _k, n, _f in found + demo), max(n for _k, n, _f in found + demo)
        per_place = per_place_of.get((prefix, tag)) if found else counted_per_place(
            tag, drawn, most, code=tag in code_patterns or tag in typed)
        now = plan_count(found, groups, per_place, buildings) if found else 0
        with_demo = plan_count(found + demo, groups, per_place, buildings)
        if with_demo <= now:
            continue
        if not found and not per_place:
            units[prefix].append((tag, sheets, with_demo))
            continue
        total = families[prefix].placements
        more = sum(n for _k, n, _f in demo)
        notes[prefix].append(f"{tag} has {more} more label{'s' if more != 1 else ''} on demolition sheets "
                             f"({', '.join(sheets)}): left out of the count, {total}; with the demolition sheets, "
                             f"{total + with_demo - now}")
    for prefix, found in units.items():
        total = families[prefix].placements
        tags = [tag for tag, _s, _n in found]
        sheets = list(dict.fromkeys(name for _t, names, _n in found for name in names))
        named = ", ".join(tags[:CAUSE_EXAMPLES]) + (f" and {len(tags) - CAUSE_EXAMPLES} more"
                                                     if len(tags) > CAUSE_EXAMPLES else "")
        notes[prefix].insert(0, f"{named} {'is' if len(tags) == 1 else 'are'} on demolition sheets only "
                                f"({', '.join(sheets)}): left out of the count, {total}; with the demolition sheets, "
                                f"{total + sum(n for _t, _s, n in found)}")
    # the lead's ruling on the T-005a review: a demolition unit with named work is not added to the new-work count;
    # its work is named for the Demolition Scope block (a new-work plan that also draws it has counted it already)
    for tag, line in sorted(worked.items(), key=lambda item: _natural(item[0])):
        prefix = tag if tag in code_patterns else _prefix(tag)
        demo = on_demo.get((prefix, tag))
        if prefix not in families or families[prefix].air_only or not demo:
            continue
        demo_sheets = list(dict.fromkeys(labels[key] for key, _n, _f in demo))
        notes[prefix].append(f"{tag} on demolition sheets ({', '.join(demo_sheets)}): the documents name work on it "
                             f"('{line[:120]}'): for the Demolition Scope, not added to the new-work count")
    return notes


def _copy_counts(catalogue, read: list, tallies_of, code_patterns: dict, per_place_of: dict
                 ) -> dict[str, dict[tuple[str, str], int]]:
    """prefix -> (copy, original) -> what the plans of a marked-up copy (`document_repeats`, same units; read once,
    never counted) would add if it were another building: its plan pages counted by the one rule, on their own
    (plan groups never cross documents). For the counts line's reading note only (REVIEW-FINAL6 F3)."""
    copies = [r for r in document_repeats(catalogue) if r.same]
    if not copies:
        return {}
    records = {(p.document, p.page): p for p in catalogue.pages}
    edge_of = {key: edge for _sheet, key, _r, _p, _riser, edge in read}
    found: dict[str, dict[tuple[str, str], int]] = defaultdict(lambda: defaultdict(int))
    for r in copies:
        plans, labelled = [], []
        for sheet in catalogue.sheets:
            key = (sheet.document, sheet.page)
            if (sheet.document == r.copy and sheet.number in r.numbers and "Plans" in sheet.types
                    and sheet.discipline in CONTROLS_DISCIPLINES and key in records):
                tally, labels = tallies_of(key, records[key], edge_of.get(key, Counter()))
                plans.append((sheet, tally))
                labelled.append((sheet, labels))
        groups = plan_groups(labelled, code_patterns)
        entries: dict[tuple[str, str], list] = defaultdict(list)
        for sheet, tally in plans:
            for tag, n in tally.items():
                prefix = tag if tag in code_patterns else _prefix(tag)
                entries[(prefix, tag)].append(((sheet.document, sheet.page), n, frozenset()))
        for (prefix, tag), mine in entries.items():
            found[prefix][(r.copy, r.original)] += plan_count(mine, groups, per_place_of.get((prefix, tag), False))
    return found


def _sheets_named(sheets: list[str]) -> str:
    return ", ".join(sheets[:CAUSE_EXAMPLES]) + (" …" if len(sheets) > CAUSE_EXAMPLES else "")


def _family_sum_note(summed: list, placements: int, said: bool) -> list[str]:
    """The family's note with both numbers when its numbered unit tags are on 2 or more plan sheets each (lead's
    ruling on the T-005a review: a unit tag is one unit in the job, across floors and areas too, but the reduction
    prints): the count, the count if each sheet's label were its own unit, and the sheets. The planner reads its
    "N counted, M if the sheets were added up" into the count's '*' note (`plan_read`, `Count.added_up`). Not said
    when the family's inventory total says it already (`said`)."""
    extra = sum(each - count for _tag, _sheets, count, each in summed if each > count)
    if said or not extra:
        return []
    tags = sum(1 for _tag, _sheets, count, each in summed if each > count)
    sheets = list(dict.fromkeys(s for _tag, names, count, each in summed if each > count for s in names))
    are = "tag is" if tags == 1 else "tags are"
    return [f"{tags} unit {are} drawn on more than one plan sheet ({_sheets_named(sheets)}), counted once, not added: "
            f"{placements} counted, {placements + extra} if the sheets were added up — check"]


def _summed_notes(summed: list) -> list[str]:
    """The reading note for each unit's tag (a numbered tag, `counted_per_place` false) shown on 2 or more plan sheets
    (ruling 2 of 2026-10-11, T-005a): one unit in the whole job, counted once, the other labels duplicates (the plans
    of other trades, part plans that overlap at a match line). The note says both numbers: the count, and what it
    would be if each sheet's label were its own unit (a numbered type used once on each floor's plan), so the
    estimator can check the schedule's quantity. The most plans first, at most CAUSE_EXAMPLES tags named. A hint for
    the estimator and the writers only: never in a client cause's words (no COUNT_CAUSE_WORDS)."""
    ranked = sorted(summed, key=lambda item: (-len(item[1]), _natural(item[0])))
    notes = [f"{tag} is on {len(sheets)} plans ({_sheets_named(sheets)}), counted once, {count}: a numbered unit tag is "
             f"one unit in the job, the other labels are duplicates; if each plan's {tag} is its own unit (a type used "
             f"once per plan), {each}: check "
             "the schedule's quantity"
             for tag, sheets, count, each in ranked[:CAUSE_EXAMPLES]]
    if len(ranked) > CAUSE_EXAMPLES:
        notes.append(f"{len(ranked) - CAUSE_EXAMPLES} more tags so: each counted once however many plans show it")
    return notes


def _labelled_often_notes(often: list) -> list[str]:
    """The reading note for each unit's tag labelled 2 or more times on one sheet, below the type rule
    (`counted_per_place`), and so counted once there (REVIEW-FINAL5 F3): it may be a typical unit at each place."""
    ranked = sorted(often, key=lambda item: (-item[2], _natural(item[0])))
    notes = [f"{tag} {n} times on {sheet}, counted as one unit: if it is a typical unit placed at each of those "
             "places, check the schedule's quantity" for tag, sheet, n in ranked[:CAUSE_EXAMPLES]]
    if len(ranked) > CAUSE_EXAMPLES:
        notes.append(f"{len(ranked) - CAUSE_EXAMPLES} more tags so: each counted once on its plan")
    return notes


def _family_sheets(prefix: str, places: dict) -> list[set]:
    return [{key for key, *_ in found} for (p, _tag), found in places.items() if p == prefix]


_PLACES = {2: "two", 3: "three", 4: "four", 5: "five"}


def _group_notes(prefix: str, groups: dict, places: dict, labels: dict, per_place_of: dict | None = None
                 ) -> list[str]:
    """The reading note for each plan group of 2 or more sheets (`plan_groups`) on which this family has a tag on
    two of its sheets: the sheets are counted as one plan, so the estimator can check it, with the family's count
    on them as one plan and as the places they would be if they are not one plan (REVIEW-FINAL6 F5: the title
    block may name the building elsewhere). Never in a client cause's words."""
    on = _family_sheets(prefix, places)
    per_place_of = per_place_of or {}
    notes = []
    for group in dict.fromkeys(groups.values()):
        if len(group) >= 2 and any(len(keys & set(group)) >= 2 for keys in on):
            names = [labels[key] for key in group]
            one = apart = 0
            for (p, tag), found in places.items():
                mine = [entry for entry in found if p == prefix and entry[0] in group]
                if mine:
                    per_place = per_place_of.get((p, tag), False)
                    one += plan_count(mine, groups, per_place)
                    apart += plan_count(mine, {}, per_place)
            if apart <= one:
                continue      # unit tags only: one unit in the job either way (ruling 2), nothing to check here
            many = _PLACES.get(len(group), str(len(group)))
            notes.append(f"{', '.join(names[:-1])} and {names[-1]} counted as one plan, {one} ({apart} if they are "
                         f"{many} places): same floor and area; check")
    return notes


def _doubt_notes(prefix: str, doubts: list, places: dict, labels: dict) -> list[str]:
    """The reading note for each pair of plan sheets that may show one plan (`plan_area_doubts`, a hint) but are not
    one plan group, where both show one tag of this family: both are counted, the higher count. Never in a client
    cause's words."""
    on = _family_sheets(prefix, places)
    return [f"{labels[a]} and {labels[b]} may show one plan; both are counted, the higher count: check whether one "
            "is the other drawn again" for a, b in doubts if any(a in keys and b in keys for keys in on)]


# ---- why the plan placements are above the other counts ------------------------------------------------
# (`plan_areas`, which sheets show one plan, is in estimator.reading.inventory: the type-tag check uses it too.)

CAUSE_EXAMPLES = 3       # tags named for each likely cause of too many placements


def _placement_causes(prefix: str, family: _Family, seen_on: dict, printed: dict, placed: Counter,
                      each_place: set = frozenset(), typed: set = frozenset(), counted: Counter | None = None
                      ) -> tuple[list[str], list[str]]:
    """Why the plan placements are likely above every other count of the family (the higher count still wins). Only
    tags counted at every place (`each_place`: a type's) can push them up, since a unit's tag counts once: a
    typical type tag placed at many places (the inventory's rule: TYPE_PLACED places, TYPE_ON_ONE_SHEET of them on
    one sheet), a type's tag on several different plans, a type's tag printed more than once on one sheet. Gives
    the reading note (tags and sheets, for the estimator and the writers) and the causes' keys (COUNT_CAUSE_WORDS,
    in that order, for the counts line's head); ([], []) when the placements are not above the other counts. A tag
    the schedule calls a type (`typed`: a QUANTITY column with no number) is a typical unit, never one unit labelled
    twice (REVIEW-FINAL6 F1). Each tag's places are its count (`counted`), never every label summed beside a lower
    count (F5)."""
    others = max(family.rows, family.quantity or 0, len(family.scheduled | family.on_plans))
    if family.placements <= others:
        return [], []
    counted = counted if counted is not None else placed
    mine = sorted((tag for p, tag in seen_on if p == prefix and tag in each_place), key=_natural)
    typical = [tag for tag in mine if (prefix, tag) in printed and ((placed[(prefix, tag)] >= TYPE_PLACED
               and printed[(prefix, tag)][2] >= TYPE_ON_ONE_SHEET) or tag in typed)]
    # a type's tag on several different sheets is most likely a typical unit on each floor or area they show, never "one
    # unit's tag shown again" (FINAL-D F5). It is the sheets that are counted here, not the plan groups: two sheets of
    # one floor and area are one plan (ruling L1), so the note says "sheets", never "plans".
    each_plan = [tag for tag in mine if tag not in typical and len(seen_on[(prefix, tag)]) > 1]
    # (a unit's tag on several plans, "shown again", counts once now (FINAL-G), so it is never a cause any more)
    units = [tag for tag in mine if tag not in typical and tag not in each_plan]
    twice = [(tag, *printed[(prefix, tag)][:2]) for tag in units if (prefix, tag) in printed]
    causes, kinds = [], []
    if typical:
        kinds.append("typical")
        named = "; ".join(f"{tag} {counted[(prefix, tag)]} places, {printed[(prefix, tag)][1]} on "
                          f"{printed[(prefix, tag)][0]}" for tag in typical[:CAUSE_EXAMPLES])
        more = f"; {len(typical) - CAUSE_EXAMPLES} more tags so" if len(typical) > CAUSE_EXAMPLES else ""
        causes.append(f"{named}{more} — likely a typical unit placed at each place: check the schedule's quantity")
    if each_plan:
        if "typical" not in kinds:
            kinds.append("typical")
        named = "; ".join(f"{tag} on {len(seen_on[(prefix, tag)])} different sheets "
                          f"({', '.join(seen_on[(prefix, tag)].values())})" for tag in each_plan[:CAUSE_EXAMPLES])
        more = f"; {len(each_plan) - CAUSE_EXAMPLES} more tags so" if len(each_plan) > CAUSE_EXAMPLES else ""
        causes.append(f"{named}{more}, a type's tag — likely a typical unit placed on each floor or area they show: "
                      "check the schedule's quantity")
    if twice:
        kinds.append("labelled_twice")
        named = "; ".join(f"{tag} {n} times on {sheet}" for tag, sheet, n in twice[:CAUSE_EXAMPLES])
        more = f"; {len(twice) - CAUSE_EXAMPLES} more tags so" if len(twice) > CAUSE_EXAMPLES else ""
        causes.append(f"{named}{more} — likely one unit labelled more than once (a tag beside a leader or a note), "
                      "unless it is a typical unit placed at each of those places")
    if not causes:
        return [], []
    return ([f"the {family.placements} placements on the plans are above the other counts: {'; and '.join(causes)}"],
            kinds)


def _counts_dict(families: dict[str, _Family]) -> dict[str, dict]:
    return {prefix: {"schedule_rows": f.rows, "quantity_column": f.quantity, "plan_placements": f.placements,
                     "riser": f.riser or None, "distinct_tags": len(f.scheduled | f.on_plans)}
            for prefix, f in families.items() if not f.air_only}


def _family_order(reading, families: dict[str, _Family]) -> list[str]:
    order = [t.prefix for t in reading.totals if t.prefix in families]
    order += [p for p in families if p not in order and families[p].rows]
    order += sorted((p for p in families if p not in order), key=lambda p: (-families[p].placements, p))
    return order


def _by_sheet(entries: list) -> str:
    """Each plan sheet with the family's tags on it ("M-101 9; M-113 1 × 10 = 10"); never "same plan as" (FINAL-G:
    no sheet is merged with another)."""
    return "; ".join(f"{sheet} {n} × {floors} = {n * floors}" if floors > 1 else f"{sheet} {n}"
                     for sheet, n, floors in entries)


def _counts_section(reading, families: dict[str, _Family], ids: _Ids) -> list[str]:
    equipment = Equipment.load()
    totals = {t.prefix: t for t in reading.totals}
    lines = []
    for prefix in _family_order(reading, families):
        f = families[prefix]
        total = totals.get(prefix)
        kind = (total.kind if total else None) or equipment.prefixes.get(prefix) or "type code on a schedule"
        tags = sorted(f.scheduled | f.on_plans, key=_natural)
        sid = ids.new(f"equipment counts for {prefix} (schedules and plans)")
        text = (f"[{sid}] {prefix} ({kind}): schedule rows {f.rows}; "
                f"QUANTITY column total {f.quantity if f.quantity is not None else '—'}; "
                f"distinct tags {len(tags)}; plan placements {f.placements}"
                f"{' (' + _by_sheet(f.by_sheet) + ')' if f.by_sheet else ''}; "
                f"riser {f.riser or '—'}"
                f"{'; ' + COUNT_CAUSES_LEAD + ' ' + ', '.join(COUNT_CAUSE_WORDS[k] for k in f.causes) if f.causes else ''}.")
        if tags:
            text += f" Tags: {tag_list(tags)}."
        places = Counter(place for tag in tags if (place := tag_location(tag)))
        if places:
            text += f" By location: {'; '.join(f'{place} {n}' for place, n in sorted(places.items()))}."
        notes = [*(total.flags if total else ()), *f.notes]
        if notes:
            text += f" Reading notes: {'; '.join(notes)}."
        lines.append(text)
    return lines


# ---- section 6: the devices on the plans ---------------------------------------------------------------

def _device_totals(catalogue, reading, multipliers: dict) -> tuple[dict[str, int], dict[str, list], dict[str, str]]:
    repeated = first_pages(catalogue)
    totals: Counter = Counter()
    by_label: dict[str, list] = defaultdict(list)
    names: dict[str, str] = {}
    for d in reading.devices:
        if d.sheet and (d.document, d.page) in repeated:
            continue                   # another page of a sheet, the same text, counted on its first page
        floors = multipliers.get((d.document, d.sheet), 1) if d.sheet else d.floors
        totals[d.label] += d.count * floors
        by_label[d.label].append((d.sheet or f"{_name(d.document)} p.{d.page}", d.count, floors))
        names.setdefault(d.label, d.device)
    return dict(totals.most_common()), by_label, names


def _devices_section(totals: dict, by_label: dict, names: dict, ids: _Ids) -> list[str]:
    lines = []
    for label, total in totals.items():
        sid = ids.new(f"device label {label} counted on the controls plan sheets")
        lines.append(f"[{sid}] {label} ({names[label]}): {total} in all — {_by_sheet(by_label[label])}")
    return lines


# ---- section 7: the notes ------------------------------------------------------------------------------

def _notes_section(catalogue, reading, ids: _Ids) -> list[str]:
    lines = []
    seen = set()
    current = None
    for note in reading.notes:
        if not note.controls:
            continue
        key = (note.document, note.page, note.sheet, note.block, note.number, note.text)
        if key in seen:
            continue
        seen.add(key)
        where = _place(note.sheet, note.document, note.page)
        if where != current:
            current = where
            lines.append(f"--- {where} ---")
        sid = ids.new(f"{note.block} {note.number}, {where}")
        who = f" ({note.who})" if note.who else ""
        lines.append(f"[{sid}] {note.block} {note.number}: {_squash(note.text)}{who}")
    return lines + _plan_sheet_notes(catalogue, reading, ids, seen)


def _plan_sheet_notes(catalogue, reading, ids: _Ids, given: set) -> list[str]:
    """7b: every keyed and general note of the mechanical, controls and plumbing sheets (the ones not
    given above), each with its source id, at most PLAN_NOTES_LIMIT characters a sheet."""
    disciplines = {(s.document, s.page): s.discipline for s in getattr(catalogue, "sheets", ()) or ()}
    by_sheet: dict[str, list] = defaultdict(list)
    seen = set(given)
    for note in reading.notes:
        if disciplines.get((note.document, note.page)) not in PLAN_NOTE_DISCIPLINES:
            continue
        key = (note.document, note.page, note.sheet, note.block, note.number, note.text)
        if key in seen:
            continue
        seen.add(key)
        by_sheet[_place(note.sheet, note.document, note.page)].append(note)
    if not by_sheet:
        return []
    lines = ["--- 7b PLAN SHEET NOTES ---",
             "(Every keyed and general note of the mechanical, controls and plumbing sheets; the notes given above "
             "are not repeated.)"]
    for where, notes in by_sheet.items():
        lines.append(f"--- {where} ---")
        used = 0
        for n, note in enumerate(notes):
            text = f"{note.block} {note.number}: {_squash(note.text)}" + (f" ({note.who})" if note.who else "")
            if used + len(text) > PLAN_NOTES_LIMIT:
                left = len(notes) - n
                lines.append(f"(Cut at {PLAN_NOTES_LIMIT:,} characters: {_plural(left, 'more note')} on this sheet.)")
                break
            sid = ids.new(f"{note.block} {note.number}, {where}")
            lines.append(f"[{sid}] {text}")
            used += len(text)
    return lines


PLAN_TEXT_HEAD = ("--- 7c PLAN SHEET TEXT ---",
                  "(Each mechanical, controls and plumbing sheet's own text, as printed, for notes written beside the "
                  f"drawing; cut at {PLAN_TEXT_LIMIT:,} characters a sheet.)")


@dataclass
class _SheetText:
    """What 7c has given so far: the pages given, the characters used, whether the total cap stopped it, and each
    line's source id with the (document, page) whose text it gives."""
    keys: set = field(default_factory=set)
    used: int = 0
    stopped: bool = False
    pages: dict = field(default_factory=dict)


def _choose_sheets(catalogue, counted, keep) -> dict[tuple[str, int], object]:
    """The plan-note sheets `keep(sheet)` takes, by (document, page), among the pages the readers count (`counted`:
    each sheet's governing pages, never a superseded page nor one that only repeats its sheet's first page). Two
    buildings' M-101 are two sheets; a reissue stands in for the page it replaces."""
    chosen: dict[tuple[str, int], object] = {}
    for sheet in getattr(catalogue, "sheets", ()) or ():
        key = (sheet.document, sheet.page)
        if sheet.discipline in PLAN_NOTE_DISCIPLINES and key in counted and keep(sheet):
            chosen.setdefault(key, sheet)
    return chosen


def _sheet_text_lines(chosen: dict, texts: dict, ids: _Ids, given: _SheetText, what: str) -> list[str]:
    """One line per chosen sheet: "[S] <place> <title>: <its text>", cut at PLAN_TEXT_LIMIT, within the
    PLAN_TEXT_TOTAL that `given` counts across 7c."""
    lines: list[str] = []
    for n, (key, sheet) in enumerate(chosen.items()):
        text = _collapse_repeats(_squash(texts.get((sheet.document, sheet.page))))
        if not text:
            continue
        if given.stopped or given.used + min(len(text), PLAN_TEXT_LIMIT) > PLAN_TEXT_TOTAL:
            lines.append(f"(Stopped at {PLAN_TEXT_TOTAL:,} characters: {_plural(len(chosen) - n, what)} "
                         "not given.)")
            given.stopped = True
            break
        cut = text[:PLAN_TEXT_LIMIT] + (" …" if len(text) > PLAN_TEXT_LIMIT else "")
        where = _place(sheet.number, sheet.document, sheet.page)
        sid = ids.new(f"{where} (sheet text)")
        lines.append(f"[{sid}] {where} {sheet.title or ''}: {cut}".replace("  ", " "))
        given.keys.add(key)
        given.pages[sid] = key
        given.used += len(cut)
    return lines


def _plan_sheet_text(catalogue, texts: dict, ids: _Ids, printed: _Printed, counted,
                     given: _SheetText | None = None) -> list[str]:
    """7c: each mechanical, controls and plumbing sheet's own text, squashed and cut at PLAN_TEXT_LIMIT
    characters. The note reader only catches blocks under a heading ("KEY NOTES"); keyed notes written
    beside the drawing (a damper actuator, a leak chime) are only here. One id per counted page (`counted`, as
    `_choose_sheets` reads it): a reissue's text and never the page it replaces, each building's sheet of one
    number; pages given above are skipped here (`_printed_sheet_text` adds the ones a 7c pass would otherwise
    miss)."""
    given = given if given is not None else _SheetText()
    chosen = _choose_sheets(catalogue, counted, lambda s: (s.document, s.page) not in printed.pages)
    if not chosen:
        return []
    return [*PLAN_TEXT_HEAD, *_sheet_text_lines(chosen, texts, ids, given, "more sheet")]


def _sheet_text_readers(sheet) -> list:
    """The reading passes that read this sheet's 7c line (by the sheet's own types, as `passes.documents` picks
    them)."""
    from estimator.ledger.passes import PASSES          # the passes read the dossier; imported here, not above
    types = set(sheet.types or ())
    return [p for p in PASSES if set(p.sheet_types) & types and not set(p.not_sheet_types) & types]


def _printed_sheet_text(catalogue, texts: dict, ids: _Ids, printed_by: dict, given: _SheetText,
                        counted) -> list[str]:
    """The 7c lines of the sheets whose pages sections 2 or 3 printed (`printed_by`: page -> section number) that a
    reading pass reads from 7c without reading the section that printed them. The details, risers, network and
    plans passes read no section 2 or 3, so a drawing sheet that is a sequence sheet and also a control diagram or
    a riser gets its own text here, never a pointer to text those passes do not receive. A sheet each of whose 7c
    passes reads the section that printed it, or that no pass reads from 7c, is not repeated. Built after section
    8, so no earlier source id moves; a page 7c already gave is not given twice."""
    def missed(sheet) -> bool:
        section = printed_by.get((sheet.document, sheet.page))
        if section is None:
            return False
        return any(section not in p.sections for p in _sheet_text_readers(sheet))

    chosen = {k: s for k, s in _choose_sheets(catalogue, counted, missed).items() if k not in given.keys}
    if not chosen:
        return []
    return _sheet_text_lines(chosen, texts, ids, given, "more sheet printed in sections 2 and 3")


# ---- section 8: the controls spec highlights -------------------------------------------------------------

def _spec_section(catalogue, printed: _Printed, texts: dict, ids: _Ids) -> list[str]:
    """The highlights of every controls spec section, even one sections 2 and 3 printed whole: the spec pass
    reads sections 1 and 8 only, so nothing here may point at text given above."""
    documents = {d.relative: d for d in catalogue.job.documents}
    sections = [s for s in catalogue.sections if s.controls]
    labels = defaultdict(list)
    for s in sections:
        labels[(s.number, s.title)].append(s)
    lines: list[str] = []
    articles: list[tuple[int, int, str, list[tuple[int, str]], object]] = []   # (priority, order, title, paras, section)
    for order, s in enumerate(sections):
        span = (s.document, s.first_page, s.last_page)
        label = f"{s.number} {s.title}".strip()
        if span in printed.replaced:
            lines.append(f"({label}, {_name(s.document)}: replaced by a later copy)")
            continue
        copies = labels[(s.number, s.title)]
        if not _later(documents.get(s.document)) and any(_later(documents.get(c.document)) for c in copies):
            lines.append(f"({label}, {_name(s.document)}: replaced by the copy in an addendum)")
            continue
        current: list[tuple[int, str]] | None = None
        title = ""
        found = len(articles)
        for page, paragraph in _page_paragraphs(texts, s.document, s.first_page, s.last_page):
            m = _ARTICLE.match(paragraph)
            if m and not m.group(2).rstrip().endswith((".", ";", ",")):
                current = [(page, paragraph)]
                title = f"{m.group(1)} {m.group(2)}"
                priority = next((i for i, (_, p) in enumerate(SPEC_HEADINGS) if p.search(m.group(2))), None)
                if priority is not None:
                    articles.append((priority, order * 10_000 + len(articles), title, current, s))
                else:
                    current = None
                continue
            if current is not None:
                current.append((page, paragraph))
        if len(articles) == found:
            lines.append(f"({label}, {_name(s.document)}: no article on the "
                         f"{', '.join(name for name, _ in SPEC_HEADINGS[:-1])} or {SPEC_HEADINGS[-1][0]})")
    articles.sort(key=lambda a: (a[0], a[1]))
    used = 0
    cut: list[str] = []
    for _, _, title, paragraphs, s in articles:
        size = sum(len(p) + 8 for _, p in paragraphs)
        label = f"{s.number} {s.title}".strip()
        if used >= SPEC_LIMIT:
            cut.append(f"{label} §{title} ({size:,} characters)")
            continue
        lines.append(f"--- {label} §{title}, {_name(s.document)} ---")
        for page, paragraph in paragraphs:
            if used + len(paragraph) > SPEC_LIMIT:
                left = sum(len(p) for _, p in paragraphs[paragraphs.index((page, paragraph)):])
                cut.append(f"the rest of {label} §{title} ({left:,} characters)")
                used = SPEC_LIMIT
                break
            sid = ids.new(f"{label} §{title}, {_name(s.document)} page {page}")
            lines.append(f"[{sid}] {paragraph}")
            used += len(paragraph) + 8
    if cut:
        lines.append(f"(Cut at {SPEC_LIMIT:,} characters. Left out: {'; '.join(cut)}.)")
    if not articles and not lines:
        lines.append("(No controls spec section found.)")
    return lines


# ---- the dossier ---------------------------------------------------------------------------------------

_SECTIONS = (("job", "1. JOB"), ("sequence", "2. SEQUENCE OF OPERATION"), ("points", "3. POINTS LISTS"),
             ("schedules", "4. SCHEDULES"), ("counts", "5. EQUIPMENT COUNTS"), ("devices", "6. DEVICES ON PLANS"),
             ("notes", "7. NOTES"), ("spec", "8. CONTROLS SPEC HIGHLIGHTS"))


def build_dossier(catalogue, reading, cache_dir: Path | None) -> Dossier:
    """Everything controls-relevant in the job, in one document with every paragraph citable."""
    documents = getattr(getattr(catalogue, "job", None), "documents", ()) or ()
    names = document_names([d.relative for d in documents] + [p.document for p in catalogue.pages])
    token = _NAMES.set(names)
    try:
        return _build_dossier(catalogue, reading, cache_dir)
    finally:
        _NAMES.reset(token)


def _build_dossier(catalogue, reading, cache_dir: Path | None) -> Dossier:
    ids = _Ids()
    texts = {(p.document, p.page): p.text for p in catalogue.pages}
    counted = _counted_pages(catalogue, reading)
    multipliers = floor_multipliers(catalogue, reading)
    body: dict[str, list[str]] = {}

    body["job"] = _job_section(catalogue, reading, ids)
    printed = _Printed()
    body["sequence"], sequence_pages = _backbone_section(catalogue, reading, SEQUENCE, ids, printed, texts)
    printed_by = {page: 2 for page in printed.pages}         # which section printed each page
    body["points"], points_pages = _backbone_section(catalogue, reading, POINTS, ids, printed, texts)
    printed_by.update({page: 3 for page in printed.pages if page not in printed_by})

    images, why, image_flags = _schedule_images(catalogue, reading, counted, cache_dir)
    all_images = [img for key in images for img in images[key]]
    image_ids = {id(img): f"I{i}" for i, img in enumerate(all_images, start=1)}
    for img in all_images:
        ids.where[image_ids[id(img)]] = f"{img.what}, {_name(img.document)} page {img.page} (picture)"
    body["schedules"] = _schedules_section(catalogue, reading, ids, images, why, image_ids, image_flags)

    families = _counts(catalogue, reading, _counted_plan_pages(catalogue, reading), multipliers)
    body["counts"] = _counts_section(reading, families, ids)
    device_totals, by_label, names = _device_totals(catalogue, reading, multipliers)
    body["devices"] = _devices_section(device_totals, by_label, names, ids)
    sheet_text = _SheetText()
    body["notes"] = _notes_section(catalogue, reading, ids) + _plan_sheet_text(catalogue, texts, ids, printed,
                                                                               counted, sheet_text)
    body["spec"] = _spec_section(catalogue, printed, texts, ids)
    more = _printed_sheet_text(catalogue, texts, ids, printed_by, sheet_text, counted)      # its ids come after section 8's
    if more:
        body["notes"] += ([] if PLAN_TEXT_HEAD[0] in body["notes"] else list(PLAN_TEXT_HEAD)) + more

    empty = {"sequence": "(No sequence of operation found in the documents.)",
             "points": "(No points list found in the documents.)",
             "schedules": "(No schedules read from the drawings.)",
             "counts": "(No equipment tags counted.)",
             "devices": "(No device labels counted on the plans.)",
             "notes": "(No notes that add controls scope.)"}
    stats: dict[str, int] = {}
    parts = [f"JOB DOSSIER — {catalogue.job.name}",
             "Everything controls-relevant in the bid documents. Every paragraph and row starts with its source "
             "id in square brackets (S1, S2 and so on); pictures are named I1, I2 and so on. Each lettered or "
             "numbered heading of the sequence starts a section block, named Q1, Q2 and so on in square brackets on "
             "its own line, with the heading; the paragraphs under it keep their own ids. "
             "Cite them."]
    sequence_chars = sum(len(line) + 1 for line in body["sequence"])
    if sequence_chars > SEQUENCE_LIMIT:
        parts.append(f"(The sequence of operation runs to {sequence_chars:,} characters, more than "
                     f"{SEQUENCE_LIMIT:,}; it is given whole.)")
    for key, heading in _SECTIONS:
        lines = body[key] or [empty.get(key, "(Nothing found.)")]
        section = "\n".join([f"== {heading} ==", *lines])
        stats[key] = len(section)
        parts.append(section)
    text = "\n\n".join(parts) + "\n"
    stats.update(total=len(text), sequence_pages=sequence_pages, points_pages=points_pages,
                 images=len(all_images), sources=len(ids.where),
                 sequence_over_limit=int(sequence_chars > SEQUENCE_LIMIT), families=len(families))
    sections = {q: (heading, tuple(sids)) for q, (heading, sids) in ids.sections.items()}
    return Dossier(catalogue.job.name, text, tuple(all_images), dict(ids.where), tuple(reading.totals),
                   device_totals, _counts_dict(families), stats, sections,
                   tuple(getattr(reading, "schedules", ()) or ()), dict(sheet_text.pages))
