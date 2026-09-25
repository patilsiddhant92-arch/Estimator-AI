"""The Spec overview: what the job says about the controls platform, protocols, the network
and front end, electrical and conduit, and every manufacturer named — with who AME asks for a
price — and the scope review: potential scope AME needs to carry, such as a standard exclusion
the job asks the controls contractor for. Nothing is guessed (design §9.1): each row either
quotes the job word for word, with where it was found, or says it wasn't found. Topics,
manufacturers, the AME vendor list and the scope review's words are JSON files in
assets/reading_lists/ — the user adds to them, never to code. AME's standard clarifications and
exclusions are read from the proposal template itself, so they never drift from what the
proposal prints.
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
SCOPE_REVIEW = ASSETS / "reading_lists" / "scope_review.json"
PROPOSAL_TEMPLATE = ASSETS / "templates" / "AME_nordomatic Proposal Template.docx"

FOUND, RULED_OUT, NOT_FOUND = "Found", "Ruled out", "Not found"
DIVISION_1 = "General requirements (Division 1)"
CONTROLS_PLACES = ("Controls spec", "Controls drawing")

# The order places are listed in, and searched: the first match wins (design's "scope").
STRENGTHS = ("Controls spec", "Controls drawing", "Mechanical drawing", "Mechanical spec", "Electrical drawing",
             DIVISION_1)
_STRENGTH_RANK = {name: index for index, name in enumerate(STRENGTHS)}

STANDARD_CLARIFICATION = "Standard clarification"
STANDARD_EXCLUSION = "Standard exclusion"

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
_RULED_OUT_REACH = 120     # characters either side of a hit that the forbidding words must sit within

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
    strength: str          # one of STRENGTHS


@dataclass(frozen=True)
class Found:
    section: str           # "Protocols" | "Network and front end" | "Electrical and conduit" | a scope review section
    item: str
    places: tuple[Place, ...]   # strongest first, then document order; empty = not found
    quote: str                  # the sentence that decided the status, word for word; "" when not found
    status: str                 # FOUND | RULED_OUT (the only strongest sentences forbid it) | NOT_FOUND
    amount: str = ""            # hours, sessions or years stated in the quote, when the reading list captures one
    protocol: str = ""          # other systems to connect to: the protocol named in the quote, or "not stated"


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
    standard_lines: tuple[Found, ...] = ()   # AME's standard clarifications and exclusions the job speaks to, template order


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


class _AnyOf:
    """Several patterns searched one by one — much faster in Python than one long alternation,
    which defeats the regex engine's quick scan for each pattern's first letters."""

    def __init__(self, patterns):
        self.patterns = tuple(p if isinstance(p, re.Pattern) else re.compile(p, re.I) for p in patterns)

    def search(self, text: str) -> bool:
        return any(p.search(text) for p in self.patterns)

    def finditer(self, text: str) -> list[re.Match]:
        return sorted((m for p in self.patterns for m in p.finditer(text)), key=lambda m: (m.start(), -m.end()))


def _any_of(patterns) -> _AnyOf | None:
    """One matcher for any of several patterns; None for none. Each keeps its own inline flags."""
    patterns = list(patterns)
    return _AnyOf(patterns) if patterns else None


@dataclass(frozen=True)
class _Search:
    """One thing the scope review looks for."""
    section: str
    item: str
    pattern: _AnyOf | None              # None = not searched
    verbs: _AnyOf | None = None        # the words must also carry one of these, not given to someone else
    also: _AnyOf | None = None         # the words must also carry one of these
    amount: _AnyOf | None = None       # captured into Found.amount


@dataclass(frozen=True)
class _ScopeReview:
    ruled_out: _AnyOf
    word_lists: dict                     # list name -> _AnyOf
    needs: dict                          # section key -> the word lists a hit outside the controls places needs one of
    after_verb_other: re.Pattern         # "…ed by others", "…ed and installed under Division 23"
    before_verb_other: re.Pattern        # "the Owner will …"
    lines: tuple[_Search, ...]           # AME's standard clarifications, then its exclusions, in template order
    unmatched_lines: tuple[str, ...]     # template lines with no entry in the reading list
    unused_entries: tuple[str, ...]      # reading-list entries that match no template line


@lru_cache
def _template_lines(template: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    from estimator.proposal.read import read_standard_lines
    return read_standard_lines(Path(template))


def _starts(line: str, start: str) -> bool:
    return line.strip().lower().startswith(start.strip().lower())


@lru_cache
def _load_scope_review(path: str, template: str) -> _ScopeReview:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    word_lists = {key: _any_of(data[key]) for key in ("controls_party_words", "controls_words", "responsibility_words")}
    needs = {section: tuple(keys) for section, keys in data["outside_controls_needs"].items()}
    others = "|".join(f"(?:{p})" for p in data["other_parties"])
    after = re.compile(rf"^\w*(?:\s*(?:,|and|&|/|or)\s*\w+)?\s+(?:by|under)\s+(?:{others})", re.I)
    before = re.compile(rf"\b(?:{others})\s+(?:shall|will|to|is\s+to|are\s+to|must)\s+(?:\w+\s+(?:and|&)\s+)?$", re.I)
    default_verbs = data["exclusion_verbs"]
    clarifications, exclusions = _template_lines(template)
    entries = data["exclusions"]
    lines, unmatched, used = [], [], set()
    for kind, template_lines in ((STANDARD_CLARIFICATION, clarifications), (STANDARD_EXCLUSION, exclusions)):
        for line in template_lines:
            entry = next((e for e in entries if _starts(line, e["line_starts"])), None)
            if entry is None:
                unmatched.append(line)
                continue
            used.add(entry["line_starts"])
            verbs = None
            if kind == STANDARD_EXCLUSION:
                verbs = _any_of(entry.get("verbs", default_verbs))
            lines.append(_Search(kind, line, _any_of(entry["patterns"]), verbs))
    unused = tuple(e["line_starts"] for e in entries if e["line_starts"] not in used)
    return _ScopeReview(_any_of(data["ruled_out_words"]), word_lists, needs, after, before, tuple(lines), tuple(unmatched), unused)


def template_lines_without_an_entry() -> tuple[str, ...]:
    """Lines of the proposal template's clarifications and exclusions that scope_review.json has
    no entry for — each would silently go unchecked."""
    return _load_scope_review(str(SCOPE_REVIEW), str(PROPOSAL_TEMPLATE)).unmatched_lines


def entries_without_a_template_line() -> tuple[str, ...]:
    """scope_review.json exclusion entries whose line_starts matches no line of the template."""
    return _load_scope_review(str(SCOPE_REVIEW), str(PROPOSAL_TEMPLATE)).unused_entries


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


def _quote_at(text: str, start: int, end: int, boundaries: list[int] | None = None) -> str:
    lo, hi = _span_at(boundaries if boundaries is not None else _boundaries(text), start, end)
    window_lo, window_hi = lo, hi
    if hi - lo > _QUOTE_LIMIT:
        mid = (start + end) // 2
        window_lo = max(lo, mid - _QUOTE_LIMIT // 2)
        window_hi = min(hi, window_lo + _QUOTE_LIMIT)
        window_lo = max(lo, window_hi - _QUOTE_LIMIT)
    return _as_quote(text, lo, hi, window_lo, window_hi)


def _as_quote(text: str, lo: int, hi: int, window_lo: int, window_hi: int) -> str:
    quote = " ".join(text[window_lo:window_hi].split())
    if window_lo > lo:
        quote = f"…{quote}"
    if window_hi < hi:
        quote = f"{quote}…"
    return quote


def _window(text: str, boundaries: list[int], start: int, end: int) -> tuple[int, int, int, int]:
    """The words a scope review hit is judged on, and quoted from: its sentence, run on over the
    list that follows when the sentence ends in a colon ("The Owner will provide the following:
    1. Servers 2. Switches"), cut to _QUOTE_LIMIT characters — more after the hit than before it,
    since a list follows its lead-in. Returns (sentence lo, sentence hi, window lo, window hi)."""
    lo, hi = _span_at(boundaries, start, end)
    if text[lo:hi].rstrip().endswith(":"):
        limit = hi + _QUOTE_LIMIT
        index = bisect.bisect_right(boundaries, limit) - 1
        hi = max(hi, boundaries[index])
    if hi - lo <= _QUOTE_LIMIT:
        return lo, hi, lo, hi
    window_lo = max(lo, start - _QUOTE_LIMIT // 3)
    window_hi = min(hi, max(end, window_lo + _QUOTE_LIMIT))
    window_lo = max(lo, min(window_lo, window_hi - _QUOTE_LIMIT))
    return lo, hi, window_lo, window_hi


def _ruled_out(text: str, window_lo: int, window_hi: int, start: int, end: int, ruled_out: _AnyOf) -> bool:
    near = text[max(window_lo, start - _RULED_OUT_REACH):min(window_hi, end + _RULED_OUT_REACH)]
    return bool(ruled_out.search(near))


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


def _place_for(record: PageRecord, sheet: Sheet | None, controls_sections: list[SpecSection],
               mech_sections: list[SpecSection], division_1: list[SpecSection] = ()) -> Place | None:
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
    for section in division_1:
        if section.document == record.document and section.first_page <= record.page <= section.last_page:
            return Place(record.document, record.page, None, section.number, DIVISION_1)
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


@dataclass(frozen=True)
class _Hit:
    place: Place
    quote: str
    ruled_out: bool
    amount: str = ""
    protocol: str = ""


def _topic_hit(topic: _Topic, text: str, boundaries: list[int], place: Place, ruled_out: _AnyOf,
               needs_controls_word: bool) -> _Hit | None:
    """The page's first sentence naming the topic that doesn't forbid it; else the first that does."""
    first_ruled = None
    for start, end in sorted((m.start(), m.end()) for p in topic.patterns for m in p.finditer(text)):
        lo, hi = _span_at(boundaries, start, end)
        if needs_controls_word and not _CONTROLS_WORDS.search(text[lo:hi]):
            continue
        ruled = _ruled_out(text, lo, hi, start, end, ruled_out)
        if ruled and first_ruled is not None:
            continue
        hit = _Hit(place, _quote_at(text, start, end, boundaries), ruled)
        if not ruled:
            return hit
        first_ruled = hit
    return first_ruled


def _live_verb(verbs: _AnyOf, window: str, review: _ScopeReview) -> bool:
    """A furnish-or-provide verb in the words that isn't given to someone else: "furnished by
    others", "installed under Division 23" and "the Owner will provide" don't count."""
    for m in verbs.finditer(window):
        after = window[m.end():m.end() + 100]
        if m.group().lower().endswith("by"):
            after = " by" + after
        if review.after_verb_other.match(after):
            continue
        if review.before_verb_other.search(window[max(0, m.start() - 60):m.start()]):
            continue
        return True
    return False


def _scope_hit(search: _Search, text: str, boundaries: list[int], place: Place, gate: _AnyOf | None,
               review: _ScopeReview) -> _Hit | None:
    """The page's first qualifying hit that doesn't forbid the thing; else the first that does."""
    first_ruled = None
    for m in search.pattern.finditer(text):
        lo, hi, w_lo, w_hi = _window(text, boundaries, m.start(), m.end())
        window = text[w_lo:w_hi]
        if gate is not None and not gate.search(window):
            continue
        if search.also is not None and not search.also.search(window):
            continue
        if search.verbs is not None and not _live_verb(search.verbs, window, review):
            continue
        ruled = _ruled_out(text, w_lo, w_hi, m.start(), m.end(), review.ruled_out)
        if ruled and first_ruled is not None:
            continue
        amount = ""
        if search.amount is not None:
            found = search.amount.search(window)
            amount = " ".join(found.group().split()) if found else ""
        hit = _Hit(place, _as_quote(text, lo, hi, w_lo, w_hi), ruled, amount)
        if not ruled:
            return hit
        first_ruled = hit
    return first_ruled


def _page_gates(review: _ScopeReview, text: str, in_controls: bool) -> dict:
    """For each scope review section: None (a controls page: every hit counts), the words a hit
    needs, or False when the page carries none of those words anywhere, so nothing on it can count."""
    if in_controls:
        return {section: None for section in review.needs}
    present = {name: words for name, words in review.word_lists.items() if words.search(text)}
    return {section: (_AnyOf(p for name in names if name in present for p in present[name].patterns)
                      if any(name in present for name in names) else False)
            for section, names in review.needs.items()}


def _resolve(section: str, item: str, hits: list[_Hit]) -> Found:
    """Found or Ruled out, decided by the strongest places that name it: Ruled out only when every
    sentence there forbids it. The deciding sentence's place comes first."""
    if not hits:
        return Found(section, item, (), "", NOT_FOUND)
    ordered = sorted(hits, key=lambda h: _STRENGTH_RANK[h.place.strength])
    top = _STRENGTH_RANK[ordered[0].place.strength]
    deciding = next((h for h in ordered if _STRENGTH_RANK[h.place.strength] == top and not h.ruled_out), None)
    status = FOUND if deciding is not None else RULED_OUT
    deciding = deciding or ordered[0]
    places = (deciding.place,) + tuple(h.place for h in ordered if h is not deciding)
    return Found(section, item, places, deciding.quote, status, deciding.amount, deciding.protocol)


def _not_found_line(item: str, division_1: bool = False) -> str:
    where = ("the general requirements (Division 1), the controls spec or the mechanical and controls drawings"
             if division_1 else "the controls spec or the mechanical and controls drawings")
    return f"{item} — not found in {where}; ask the engineer if it matters"


def build_overview(pages, sheets, sections) -> SpecOverview:
    topics = _load_topics(str(SPEC_OVERVIEW))
    categories = _load_manufacturers(str(OVERVIEW_MANUFACTURERS))
    vendors = _load_vendors(str(AME_VENDORS))
    review = _load_scope_review(str(SCOPE_REVIEW), str(PROPOSAL_TEMPLATE))

    by_page = {(s.document, s.page): s for s in sheets}
    controls_sections = [s for s in sections if s.controls]
    mech_sections = [s for s in sections if not s.controls and s.number.startswith(_MECH_SPEC_PREFIXES)]
    division_1 = [s for s in sections if s.number.startswith("01")]

    topic_hits: dict[tuple[str, str], list[_Hit]] = defaultdict(list)
    line_hits: dict[str, list[_Hit]] = defaultdict(list)
    maker_hits: dict[str, list[tuple[Place, str]]] = defaultdict(list)

    for record in pages:
        sheet = by_page.get((record.document, record.page))
        place = _place_for(record, sheet, controls_sections, mech_sections, division_1)
        if place is None:
            continue
        text = clean_text(record.text)
        boundaries = _boundaries(text)
        in_controls = place.strength in CONTROLS_PLACES
        if place.strength == DIVISION_1:
            continue
        gates = _page_gates(review, text, in_controls)
        if gates["exclusions"] is not False:
            for search in review.lines:
                if search.pattern is None:
                    continue
                hit = _scope_hit(search, text, boundaries, place, gates["exclusions"], review)
                if hit is not None:
                    line_hits[search.item].append(hit)
        electrical = place.strength == "Electrical drawing"
        for topic in topics:
            if electrical and not topic.electrical:
                continue
            hit = _topic_hit(topic, text, boundaries, place, review.ruled_out, electrical)
            if hit is not None:
                topic_hits[(topic.section, topic.item)].append(hit)
        if electrical:
            continue
        for category in categories:
            for maker in category.makers:
                match = _first_unblocked_match(maker, text)
                if match is None:
                    continue
                maker_hits[maker.name].append((place, _quote_at(text, *match, boundaries)))

    found_topics = tuple(_resolve(t.section, t.item, topic_hits.get((t.section, t.item), [])) for t in topics)
    standard_lines = []
    for search in review.lines:
        found = _resolve(search.section, search.item, line_hits.get(search.item, []))
        # An exclusion the job only forbids isn't asked for; a clarification it forbids is worth a look.
        if found.status == FOUND or (found.status == RULED_OUT and search.section == STANDARD_CLARIFICATION):
            standard_lines.append(found)

    makers_out: list[MakerRow] = []
    not_found: list[str] = [_not_found_line(t.item) for t in found_topics if t.status == NOT_FOUND]

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

    return SpecOverview(found_topics, tuple(makers_out), tuple(not_found), tuple(standard_lines))
