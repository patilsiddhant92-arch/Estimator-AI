"""The front end, the cover header and "based on", from the job's own documents.

The front end is one of the Master Template's two openings (assets/front_end.json): a new
system, or an extension of the existing BMS when the Spec overview finds a tie-in to one.
Each of the template's lines is printed only when its condition holds in the Spec overview
(or, for the portable terminal, when its words are in the controls documents); graphics and
training are the template's defaults. A server or switches the owner provides become a "**"
note for the client, quoting the job. The warranty lines are printed only when the job states
how long the warranty is.

The header comes from the folder name, the title blocks and the sheets' revision dates. What
can't be read is PENDING and flagged, never guessed.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from estimator.catalogue.overview import FOUND, Found, Place, short_place
from estimator.catalogue.pdf import clean_text
from estimator.scope import FrontEnd, Header, Item, Run

ASSETS = Path(__file__).resolve().parents[3] / "assets"
FRONT_END_FILE = ASSETS / "front_end.json"

_TIE_IN = "Tie-in to an existing system"
_WARRANTY = "Warranty"
_SERVICE_AGREEMENT = "Service or maintenance agreement"
_TEMPLATE_DEFAULT = "Master Template default"
_QUOTE_LIMIT = 300


@dataclass(frozen=True)
class Evidence:
    """Why one line is in the scope: the line, where the job says so, its words, and its category."""

    line: str
    where: str
    quote: str
    status: str          # CONFIRMED (the job says so), ASSUMPTION (a template default), PENDING


@lru_cache(maxsize=4)
def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _compile(patterns, shared: dict) -> tuple[re.Pattern, ...]:
    return tuple(re.compile(shared[p[1:]] if p.startswith("@") else p, re.I) for p in patterns)


# --- the front end ----------------------------------------------------------------

def front_end(catalogue, data: dict | None = None, bid_check=None
             ) -> tuple[FrontEnd, list[str], list[Evidence]]:
    """The front-end block, the flags for the review list, and the evidence for each printed line.

    bid_check: the catalogue's Bid check (estimator.catalogue.qualify.BidCheck), when there is one.
    Its passages name the existing BMS when the Spec overview's own tie-in quote doesn't."""
    data = data or _load(FRONT_END_FILE)
    overview = catalogue.overview
    topics = {t.item: t for t in overview.topics}
    flags: list[str] = []
    evidence: list[Evidence] = []

    tie_in = topics.get(_TIE_IN)
    if tie_in is not None and tie_in.status == FOUND:
        mode = "extend-existing"
        name = _existing_name(tie_in.quote, data["existing_systems"])
        where, quote = short_place(tie_in.places), tie_in.quote
        if name is None and bid_check is not None:
            found = _existing_name_from_bid_check(bid_check, data["existing_systems"])
            if found is not None:
                name, where, quote = found
        if name is None:
            name = data["existing_systems"]["unnamed"]
            flags.append(f"Name the existing BMS — the job asks for a tie-in to an existing system but doesn't say "
                         f"which one: “{tie_in.quote}” ({short_place(tie_in.places)})")
        heading = data["headings"][mode].format(system=name)
        evidence.append(Evidence(heading, where, quote,
                                 "CONFIRMED" if name != data["existing_systems"]["unnamed"] else "PENDING"))
    else:
        mode, name = "new-system", None

    held = _Conditions(catalogue, data, topics)
    items: list[Item] = []
    for line in data["variants"][mode]:
        when, unless = line.get("when"), line.get("unless")
        if when is not None and held.check(when) is None:
            continue
        if unless is not None and held.check(unless) is not None:
            continue
        items.append(_line(line["text"], 1, line.get("quantity")))
        for sub in line.get("lines", ()):
            items.append(_line(sub, 2, None))
        if when is None:
            evidence.append(Evidence(line["text"], _TEMPLATE_DEFAULT, "", "ASSUMPTION"))
        else:
            where, quote = held.check(when)
            evidence.append(Evidence(line["text"], where, quote, "CONFIRMED"))

    for condition, note in data["client_notes"].items():
        hit = held.check(condition)
        if hit is not None:
            items.append(Item(kind="note", runs=(Run(text=note, bold=True),)))
            evidence.append(Evidence(note, hit[0], hit[1], "CONFIRMED"))

    items += _warranty(overview, data["warranty"], flags, evidence)
    return FrontEnd(mode=mode, existing_system_name=name, items=tuple(items)), flags, evidence


def _line(text: str, depth: int, quantity: int | None) -> Item:
    return Item(kind="line", depth=depth, runs=(Run(text=text, bold=True),), quantity=quantity)


def _existing_name(quote: str, systems: dict) -> str | None:
    names = [entry["name"] for entry in systems["names"]
             if any(re.search(p, quote, re.I) for p in entry["patterns"])]
    return " / ".join(names) or None


def _existing_name_from_bid_check(bid_check, systems: dict) -> tuple[str, str, str] | None:
    """(name, where, quote) from the first Bid check passage that names one of the existing_systems
    names — None when no passage does."""
    from estimator.catalogue.qualify import where as bid_where

    for mention in bid_check.mentions:
        name = _existing_name(mention.quote, systems)
        if name is not None:
            return name, bid_where(mention), mention.quote
    return None


class _Conditions:
    """Each condition of front_end.json, checked once: (where, quote) when it holds, else None."""

    def __init__(self, catalogue, data: dict, topics: dict[str, Found]):
        self._catalogue = catalogue
        self._data = data
        self._topics = topics
        self._shared = data.get("shared_patterns", {})
        self._seen: dict[str, tuple[str, str] | None] = {}

    def check(self, name: str) -> tuple[str, str] | None:
        if name not in self._seen:
            self._seen[name] = self._evaluate(self._data["conditions"][name])
        return self._seen[name]

    def _evaluate(self, condition: dict) -> tuple[str, str] | None:
        if "topic" in condition:
            topic = self._topics.get(condition["topic"])
            if topic is None or topic.status != FOUND:
                return None
            return short_place(topic.places), topic.quote
        if "words" in condition:
            return _words_in_controls_documents(self._catalogue, _compile(condition["words"], self._shared),
                                                self._data["words_are_searched_in"])
        if "who" in condition:
            return self._who(condition)
        raise ValueError(f"front_end.json: a condition needs a topic, words or who: {condition}")

    def _who(self, condition: dict) -> tuple[str, str] | None:
        things = _compile(condition["who"], self._shared)
        parties = _compile(self._data["parties"][condition["party"]], self._shared)
        rows = list(self._catalogue.overview.who_does_what)
        also = self._topics.get(condition.get("also_topic", ""))
        if also is not None and also.status == FOUND:
            rows.append(also)
        for row in rows:
            if row.quote and any(p.search(row.quote) for p in things) and any(p.search(row.quote) for p in parties):
                return short_place(row.places), row.quote
        return None


def _place(record, sheets: dict, controls_sections) -> Place | None:
    for section in controls_sections:
        if section.document == record.document and section.first_page <= record.page <= section.last_page:
            return Place(record.document, record.page, None, section.number, "Controls spec")
    sheet = sheets.get((record.document, record.page))
    if sheet is not None and sheet.discipline in ("Controls", "Mechanical"):
        return Place(record.document, record.page, sheet.number, None, f"{sheet.discipline} drawing")
    return None


def _words_in_controls_documents(catalogue, patterns, places: list[str]) -> tuple[str, str] | None:
    sheets = {(s.document, s.page): s for s in catalogue.sheets}
    controls_sections = [s for s in catalogue.sections if s.controls]
    for strength in places:
        for record in catalogue.pages:
            place = _place(record, sheets, controls_sections)
            if place is None or place.strength != strength:
                continue
            text = clean_text(record.text)
            for pattern in patterns:
                match = pattern.search(text)
                if match:
                    return short_place((place,)), _sentence(text, match.start(), match.end())
    return None


def _sentence(text: str, start: int, end: int) -> str:
    lo = max(text.rfind(". ", 0, start) + 2, text.rfind("\n", 0, start) + 1, 0)
    ends = [i for i in (text.find(". ", end), text.find("\n", end)) if i != -1]
    hi = min(ends) + 1 if ends else len(text)
    quote = " ".join(text[lo:hi].split())
    return quote if len(quote) <= _QUOTE_LIMIT else quote[:_QUOTE_LIMIT].rstrip() + "…"


def _warranty(overview, warranty: dict, flags: list[str], evidence: list[Evidence]) -> list[Item]:
    services = {s.item: s for s in overview.services}
    found = services.get(_WARRANTY)
    if found is None or found.status != FOUND:
        return []
    where = short_place(found.places)
    if not found.amount:
        flags.append(f"Say how long the warranty is — the job asks for one but no length was read: "
                     f"“{found.quote}” ({where})")
        return []
    term = re.sub(r"\s*-?\s*(year|month)s?\s*$", r"-\1", found.amount.strip().lower())
    contract = warranty["contract"].format(term=term)
    items = [_line(warranty["heading"], 1, None), _line(contract, 2, None)]
    evidence.append(Evidence(warranty["heading"], where, found.quote, "CONFIRMED"))
    evidence.append(Evidence(contract, where, found.quote, "CONFIRMED"))

    agreement = services.get(_SERVICE_AGREEMENT)
    rows = [found] + ([agreement] if agreement is not None and agreement.status == FOUND else [])
    for row in rows:
        if not any(re.search(p, row.quote, re.I) for p in warranty["extension_words"]):
            continue
        years = re.search(warranty["extension_years"], row.quote, re.I)
        if years is None:
            flags.append(f"Say for how many years the warranty is extended — the job asks for it but the years "
                         f"weren't read: “{row.quote}” ({short_place(row.places)})")
            break
        extension = warranty["extension"].format(years=years.group(1).lower())
        items.append(_line(extension, 2, None))
        evidence.append(Evidence(extension, short_place(row.places), row.quote, "CONFIRMED"))
        break
    return items


# --- the header -------------------------------------------------------------------

def job_header(catalogue, reading, today: dt.date, data: dict | None = None) -> tuple[Header, list[str]]:
    """The cover page's table, and the flags for whatever had to be left PENDING."""
    settings = (data or _load(FRONT_END_FILE))["header"]
    flags: list[str] = []
    folder = Path(catalogue.job.root).name
    number, _, rest = folder.partition(",")
    quote_number = number.strip() or catalogue.job.name
    reference = rest.strip()
    if not reference:
        reference = settings["unnamed_reference"]
        flags.append(f"Give the project name for the cover page — the job folder “{folder}” has only its number")

    engineer = _engineer(catalogue, settings)
    if engineer is None:
        engineer = settings["unnamed_engineer"]
        flags.append("Give the MEP engineer for the cover page — no engineering firm's name could be read from the "
                     "mechanical title blocks")

    based_on = _based_on(catalogue, reading, settings, flags)
    header = Header(date=today, quote_number=quote_number, reference=reference, mep_engineer=engineer,
                    based_on=tuple(based_on))
    return header, flags


def _engineer(catalogue, settings: dict) -> str | None:
    label = _label_engineer(catalogue, settings)
    if label is not None:
        return label
    firm = re.compile(settings["engineer_firm"], re.I)
    for discipline in settings["engineer_disciplines"]:
        pages = {(s.document, s.page) for s in catalogue.sheets if s.discipline == discipline}
        counts: Counter[str] = Counter()
        for record in catalogue.pages:
            if (record.document, record.page) not in pages:
                continue
            names = {" ".join(span.text.split()) for span in record.edge_spans}
            counts.update(name for name in names if firm.search(name))
        if counts:
            return counts.most_common(1)[0][0]
    return _spec_footer_engineer(catalogue, firm)


def _label_engineer(catalogue, settings: dict) -> str | None:
    """The text beside the title block's ENGINEER / MEP ENGINEER / CONSULTING ENGINEER label — the
    firm's own name, whatever it is, even one with no "engineer/consulting/associates" word of its
    own ("GILLAN & HARTMANN, Inc.")."""
    label = re.compile(settings["engineer_label"], re.I)
    skip = {w.upper() for w in settings.get("engineer_label_skip", ())}
    pages = {(s.document, s.page) for s in catalogue.sheets if s.discipline in settings["engineer_disciplines"]}
    for record in catalogue.pages:
        if (record.document, record.page) not in pages:
            continue
        ordered = sorted(record.edge_spans, key=lambda s: (round(s.y0, 3), s.x0))
        texts = [" ".join(s.text.split()) for s in ordered]
        for i, text in enumerate(texts):
            if not label.match(text):
                continue
            for candidate in texts[i + 1:]:
                if label.match(candidate) or candidate.rstrip(":").strip().upper() in skip:
                    continue
                return candidate
    return None


def _spec_pages(catalogue) -> set[tuple[str, int]]:
    pages: set[tuple[str, int]] = set()
    for section in getattr(catalogue, "sections", ()):
        for page in range(section.first_page, section.last_page + 1):
            pages.add((section.document, page))
    return pages


def _footer_line(text: str) -> str:
    lines = [line for line in clean_text(text).splitlines() if line.strip()]
    return " ".join(lines[-1].split()) if lines else ""


def _spec_footer_engineer(catalogue, firm: re.Pattern) -> str | None:
    """Else the most common firm name in the spec's page footers — the last printed line of each
    spec page, the same "engineer/consulting/associates" firm-name pattern the title blocks use."""
    spec_pages = _spec_pages(catalogue)
    counts: Counter[str] = Counter()
    for record in catalogue.pages:
        if (record.document, record.page) not in spec_pages:
            continue
        footer = _footer_line(record.text)
        if firm.search(footer):
            counts[footer] += 1
    return counts.most_common(1)[0][0] if counts else None


def _natural(number: str) -> tuple:
    return tuple(int(part) if part.isdigit() else part for part in re.split(r"(\d+)", number.upper()))


def _letters(number: str) -> str:
    match = re.match(r"[A-Za-z]+", number)
    return match.group(0).upper() if match else ""


def _based_on(catalogue, reading, settings: dict, flags: list[str]) -> list[str]:
    disciplines = settings["based_on_disciplines"]
    by_page = {(s.document, s.page): s.discipline for s in catalogue.sheets}
    sets: dict[tuple[int, str], dict[str, dt.date | None]] = {}
    for version in reading.versions:
        discipline = by_page.get((version.document, version.page))
        if discipline not in disciplines:
            continue
        key = (disciplines.index(discipline), _letters(version.sheet))
        numbers = sets.setdefault(key, {})
        latest = numbers.get(version.sheet)
        if version.sheet not in numbers or (version.latest and (latest is None or version.latest > latest)):
            numbers[version.sheet] = version.latest
    if not sets:
        flags.append("Say which drawings the proposal is based on — no mechanical or controls sheet numbers were read")
        return ["[drawings the proposal is based on]"]

    lines = []
    undated = []
    for key in sorted(sets, key=lambda k: k[0]):       # stable: within a discipline, the order the sheets came in
        numbers = sets[key]
        ordered = sorted(numbers, key=_natural)
        dates = [d for d in numbers.values() if d]
        date = max(dates).strftime(settings["date_format"]) if dates else settings["undated"]
        if not dates:
            undated.append(ordered[0])
        template = settings["based_on_line"] if len(ordered) > 1 else settings["based_on_single"]
        lines.append(template.format(first=ordered[0], last=ordered[-1], date=date))
    if undated:
        flags.append("Give the drawings' issue date for “based on” — no revision date was read from the title "
                     f"blocks of the {', '.join(undated)} set")
    return lines
