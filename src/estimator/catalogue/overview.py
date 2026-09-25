"""The Spec overview: what the job says about the controls platform, protocols, the network
and front end, electrical and conduit, and every manufacturer named — with who AME asks for a
price. Nothing is guessed (design §9.1): each row either quotes the job word for word, with
where it was found, or says it wasn't found. Topics, manufacturers and the AME vendor list are
JSON files in assets/reading_lists/ — the user adds to them, never to code.
"""
from __future__ import annotations

import bisect
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from estimator.catalogue.pdf import clean_text
from estimator.catalogue.register import PageRecord
from estimator.catalogue.sheet_types import Sheet
from estimator.catalogue.spec_sections import SpecSection

ASSETS = Path(__file__).resolve().parents[3] / "assets"
SPEC_OVERVIEW = ASSETS / "reading_lists" / "spec_overview.json"
OVERVIEW_MANUFACTURERS = ASSETS / "reading_lists" / "overview_manufacturers.json"
AME_VENDORS = ASSETS / "reading_lists" / "ame_vendors.json"

# The order places are listed in, and searched: the first match wins (design's "scope").
STRENGTHS = ("Controls spec", "Controls drawing", "Mechanical drawing", "Mechanical spec", "Electrical drawing")
_STRENGTH_RANK = {name: index for index, name in enumerate(STRENGTHS)}

_CONTROLS_WORDS = re.compile(
    r"\bBMS\b|\bBAS\b|\bATC\b|\bDDC\b|building\s+(?:automation|management)|"
    r"temperature\s+control(?!ler)|controls?\s+contractor|thermostats?|\bsensors?\b|"
    r"control\s+(?:panel|wiring|device)s?", re.I)

_MECH_SPEC_PREFIXES = ("23", "25", "15")

# A sentence ends at ". ", "; ", a line break followed by a list marker (A., 1., a., (1)), or a
# blank line.
_SENTENCE_END = re.compile(r"[.;][ \t]+")
_LIST_MARKER = re.compile(r"\n[ \t]*((?:[A-Za-z]{1,2}\.|\d{1,3}\.|\(\d{1,3}\)))[ \t]+")
_BLANK_LINE = re.compile(r"\n[ \t]*\n")
_QUOTE_LIMIT = 300

_BASIS = re.compile(r"basis\s+of\s+design", re.I)
_NO_SUBSTITUTION = re.compile(r"no\s+substitution", re.I)
_OR_EQUAL = re.compile(r"or\s+(?:approved\s+)?equal", re.I)

_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9&']*")


@dataclass(frozen=True)
class Place:
    document: str          # Document.relative
    page: int
    sheet: str | None      # the sheet number, when the page is a drawing sheet
    section: str | None    # the spec section number, when inside one
    strength: str          # "Controls spec" | "Controls drawing" | "Mechanical drawing" | "Mechanical spec" | "Electrical drawing"


@dataclass(frozen=True)
class Found:
    section: str           # "Protocols" | "Network and front end" | "Electrical and conduit"
    item: str
    places: tuple[Place, ...]   # strongest first, then document order; empty = not found
    quote: str                  # the sentence at the first place, word for word; "" when not found


@dataclass(frozen=True)
class MakerRow:
    category: str
    maker: str                  # the list's canonical "name"
    places: tuple[Place, ...]
    quote: str
    terms: str                  # "Basis of design" / "Or approved equal" / "No substitutions" / "" — from the quoted sentence
    ame_quotes: bool
    vendors: tuple[str, ...]    # "Broudy Precision — jchandler@…; tsanroman@…", one per matching vendor
    email_draft: str            # the template filled in, only when ame_quotes; else ""
    priced: bool = True         # False for a category that isn't a device to price (the controls platform)


@dataclass(frozen=True)
class SpecOverview:
    topics: tuple[Found, ...] = ()       # every topic in spec_overview.json order, found or not
    makers: tuple[MakerRow, ...] = ()    # only makers found; sorted by category order in the list, then maker name
    not_found: tuple[str, ...] = ()      # plain lines: each topic not found, then each ask_if_missing category with no maker


@dataclass(frozen=True)
class _Topic:
    section: str
    item: str
    patterns: tuple[re.Pattern, ...]
    electrical: bool


@dataclass(frozen=True)
class _Maker:
    category: str
    name: str
    names: tuple[str, ...]
    patterns: tuple[re.Pattern, ...]
    not_before: tuple[str, ...]
    not_after: tuple[str, ...]


@dataclass(frozen=True)
class _Category:
    category: str
    ask_if_missing: bool
    makers: tuple[_Maker, ...]
    priced: bool = True


@dataclass(frozen=True)
class _Vendor:
    vendor: str
    makers: tuple[str, ...]
    products_match: tuple[str, ...]
    contact: str


@dataclass(frozen=True)
class _Vendors:
    email_draft: str
    vendors: tuple[_Vendor, ...]


def _name_pattern(text: str) -> re.Pattern:
    words = text.split()
    escaped = r"\s+".join(re.escape(w) for w in words)
    return re.compile(rf"\b{escaped}\b")


@lru_cache
def _load_topics(path: str) -> tuple[_Topic, ...]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return tuple(_Topic(t["section"], t["item"], tuple(re.compile(p, re.I) for p in t["patterns"]),
                        t.get("electrical", False))
                 for t in data["topics"])


@lru_cache
def _load_manufacturers(path: str) -> tuple[_Category, ...]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    categories = []
    for c in data["categories"]:
        makers = []
        for m in c["makers"]:
            forms = {form for name in m["names"] for form in (name, name.upper())}
            patterns = tuple(_name_pattern(form) for form in sorted(forms))
            makers.append(_Maker(c["category"], m["name"], tuple(m["names"]), patterns,
                                 tuple(m.get("not_before", ())), tuple(m.get("not_after", ()))))
        categories.append(_Category(c["category"], c["ask_if_missing"], tuple(makers), c.get("priced", True)))
    return tuple(categories)


@lru_cache
def _load_vendors(path: str) -> _Vendors:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    vendors = tuple(_Vendor(v["vendor"], tuple(v.get("makers", ())), tuple(v.get("products_match", ())), v["contact"])
                    for v in data["vendors"])
    return _Vendors(data["email_draft"], vendors)


def _boundaries(text: str) -> list[int]:
    points = {0, len(text)}
    points.update(m.end() for m in _SENTENCE_END.finditer(text))
    points.update(m.start(1) for m in _LIST_MARKER.finditer(text))
    for m in _BLANK_LINE.finditer(text):
        points.add(m.start())
        points.add(m.end())
    return sorted(points)


def _span_at(boundaries: list[int], start: int, end: int) -> tuple[int, int]:
    lo = boundaries[max(bisect.bisect_right(boundaries, start) - 1, 0)]
    hi = boundaries[min(bisect.bisect_left(boundaries, end), len(boundaries) - 1)]
    return lo, hi


def _quote_at(text: str, start: int, end: int) -> str:
    lo, hi = _span_at(_boundaries(text), start, end)
    window_lo, window_hi = lo, hi
    if hi - lo > _QUOTE_LIMIT:
        mid = (start + end) // 2
        window_lo = max(lo, mid - _QUOTE_LIMIT // 2)
        window_hi = min(hi, window_lo + _QUOTE_LIMIT)
        window_lo = max(lo, window_hi - _QUOTE_LIMIT)
    quote = " ".join(text[window_lo:window_hi].split())
    if window_lo > lo:
        quote = f"…{quote}"
    if window_hi < hi:
        quote = f"{quote}…"
    return quote


def _sentence_at(text: str, start: int, end: int) -> tuple[int, int]:
    return _span_at(_boundaries(text), start, end)


def _blocked(text: str, start: int, end: int, not_before: tuple[str, ...], not_after: tuple[str, ...]) -> bool:
    before = text[max(0, start - 60):start]
    after = text[end:end + 60]
    for phrase in not_before:
        pattern = re.compile(r"\b" + r"\s+".join(re.escape(w) for w in phrase.split()) + r"\b[^A-Za-z0-9]*$")
        if pattern.search(before):
            return True
    for phrase in not_after:
        pattern = re.compile(r"^[^A-Za-z0-9]*\b" + r"\s+".join(re.escape(w) for w in phrase.split()) + r"\b")
        if pattern.search(after):
            return True
    return False


def _terms(quote: str) -> str:
    if _BASIS.search(quote):
        return "Basis of design"
    if _NO_SUBSTITUTION.search(quote):
        return "No substitutions"
    if _OR_EQUAL.search(quote):
        return "Or approved equal"
    return ""


def _place_for(record: PageRecord, sheet: Sheet | None,
               controls_sections: list[SpecSection], mech_sections: list[SpecSection]) -> Place | None:
    for section in controls_sections:
        if section.document == record.document and section.first_page <= record.page <= section.last_page:
            return Place(record.document, record.page, None, section.number, "Controls spec")
    if sheet is not None and sheet.discipline == "Controls":
        return Place(record.document, record.page, sheet.number, None, "Controls drawing")
    if sheet is not None and sheet.discipline == "Mechanical":
        return Place(record.document, record.page, sheet.number, None, "Mechanical drawing")
    for section in mech_sections:
        if section.document == record.document and section.first_page <= record.page <= section.last_page:
            return Place(record.document, record.page, None, section.number, "Mechanical spec")
    if sheet is not None and sheet.discipline == "Electrical":
        return Place(record.document, record.page, sheet.number, None, "Electrical drawing")
    return None


def short_place(places: tuple[Place, ...]) -> str:
    """"M-601.00 (Marked_Mech.pdf, page 10)  (+4 other)" / "Specs.pdf · 23 09 23 · page 124  (+2 other)"."""
    if not places:
        return ""
    first = places[0]
    base_name = first.document.rsplit("/", 1)[-1]
    if first.sheet:
        primary = f"{first.sheet} ({base_name}, page {first.page})"
    elif first.section:
        primary = f"{base_name} · {first.section} · page {first.page}"
    else:
        primary = f"{base_name}, page {first.page}"
    extra = len(places) - 1
    return f"{primary}  (+{extra} other)" if extra else primary


def _first_match(patterns: tuple[re.Pattern, ...], text: str) -> tuple[int, int] | None:
    matches = sorted((m.start(), m.end()) for p in patterns for m in p.finditer(text))
    return matches[0] if matches else None


def _first_unblocked_match(maker: _Maker, text: str) -> tuple[int, int] | None:
    matches = sorted((m.start(), m.end()) for p in maker.patterns for m in p.finditer(text))
    for start, end in matches:
        if not _blocked(text, start, end, maker.not_before, maker.not_after):
            return start, end
    return None


def _matches_maker(vendor: _Vendor, maker: _Maker) -> bool:
    candidates = {maker.name.lower()} | {n.lower() for n in maker.names}
    return any(m.lower() in candidates for m in vendor.makers)


def _matches_category(vendor: _Vendor, category: str) -> bool:
    if vendor.makers:
        return False
    low = category.lower()
    return any(word.lower() in low for word in vendor.products_match)


def _vendors_for(maker: _Maker, category: str, vendors: _Vendors) -> tuple[str, ...]:
    return tuple(f"{v.vendor} — {v.contact}" for v in vendors.vendors
                if _matches_maker(v, maker) or _matches_category(v, category))


def build_overview(pages, sheets, sections) -> SpecOverview:
    topics = _load_topics(str(SPEC_OVERVIEW))
    categories = _load_manufacturers(str(OVERVIEW_MANUFACTURERS))
    vendors = _load_vendors(str(AME_VENDORS))

    by_page = {(s.document, s.page): s for s in sheets}
    controls_sections = [s for s in sections if s.controls]
    mech_sections = [s for s in sections if not s.controls and s.number.startswith(_MECH_SPEC_PREFIXES)]

    topic_hits: dict[tuple[str, str], list[tuple[Place, str]]] = defaultdict(list)
    topic_seen: dict[tuple[str, str], set[tuple[str, int]]] = defaultdict(set)
    maker_hits: dict[str, list[tuple[Place, str]]] = defaultdict(list)
    maker_seen: dict[str, set[tuple[str, int]]] = defaultdict(set)
    maker_by_name: dict[str, tuple[_Maker, str]] = {}

    for record in pages:
        sheet = by_page.get((record.document, record.page))
        place = _place_for(record, sheet, controls_sections, mech_sections)
        if place is None:
            continue
        text = clean_text(record.text)
        if place.strength == "Electrical drawing":
            for topic in topics:
                if not topic.electrical:
                    continue
                key = (topic.section, topic.item)
                if (record.document, record.page) in topic_seen[key]:
                    continue
                match = _first_match(topic.patterns, text)
                if match is None:
                    continue
                s_lo, s_hi = _sentence_at(text, *match)
                if not _CONTROLS_WORDS.search(text[s_lo:s_hi]):
                    continue
                topic_seen[key].add((record.document, record.page))
                topic_hits[key].append((place, _quote_at(text, *match)))
            continue
        for topic in topics:
            key = (topic.section, topic.item)
            if (record.document, record.page) in topic_seen[key]:
                continue
            match = _first_match(topic.patterns, text)
            if match is None:
                continue
            topic_seen[key].add((record.document, record.page))
            topic_hits[key].append((place, _quote_at(text, *match)))
        for category in categories:
            for maker in category.makers:
                if (record.document, record.page) in maker_seen[maker.name]:
                    continue
                match = _first_unblocked_match(maker, text)
                if match is None:
                    continue
                maker_seen[maker.name].add((record.document, record.page))
                maker_hits[maker.name].append((place, _quote_at(text, *match)))
                maker_by_name[maker.name] = (maker, category.category)

    found_topics = []
    for topic in topics:
        key = (topic.section, topic.item)
        entries = sorted(topic_hits.get(key, ()), key=lambda pq: _STRENGTH_RANK[pq[0].strength])
        places = tuple(pq[0] for pq in entries)
        quote = entries[0][1] if entries else ""
        found_topics.append(Found(topic.section, topic.item, places, quote))

    makers_out: list[MakerRow] = []
    not_found: list[str] = []
    for topic in topics:
        key = (topic.section, topic.item)
        if not topic_hits.get(key):
            not_found.append(f"{topic.item} — not found in the controls spec or the mechanical and controls "
                             f"drawings; ask the engineer if it matters")

    for category in categories:
        category_rows = []
        for maker in sorted(category.makers, key=lambda m: m.name):
            entries = sorted(maker_hits.get(maker.name, ()), key=lambda pq: _STRENGTH_RANK[pq[0].strength])
            if not entries:
                continue
            places = tuple(pq[0] for pq in entries)
            quote = entries[0][1]
            vendor_list = _vendors_for(maker, category.category, vendors) if category.priced else ()
            ame_quotes = bool(vendor_list)
            email_draft = (vendors.email_draft.format(maker=maker.name, category=category.category)
                          if ame_quotes else "")
            category_rows.append(MakerRow(category.category, maker.name, places, quote, _terms(quote),
                                          ame_quotes, vendor_list, email_draft, category.priced))
        makers_out.extend(category_rows)
        if category.ask_if_missing and not category_rows:
            not_found.append(f"No {category.category.lower()} maker named — ask the engineer if the job needs one")

    return SpecOverview(tuple(found_topics), tuple(makers_out), tuple(not_found))
