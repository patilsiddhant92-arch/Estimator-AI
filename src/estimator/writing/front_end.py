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
from estimator.reading.revisions import parse_date
from estimator.scope import Block, FrontEnd, Header, Item, Run
from estimator.writing.templates import load_templates, template_for

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
        said = held.check(line["said_by"]) if when is None and line.get("said_by") else None
        if said is not None:                      # always printed; the specification also calls for it
            evidence.append(Evidence(line["text"], said[0], said[1], "CONFIRMED"))
        elif when is None:
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
        """The row whose one sentence names both the thing and the party; with "not_ownership", not when
        those words stand between them ("the owner shall provide a connection … to a corporate server")."""
        things = _compile(condition["who"], self._shared)
        parties = _compile(self._data["parties"][condition["party"]], self._shared)
        not_own = _compile([condition["not_ownership"]], self._shared)[0] if condition.get("not_ownership") else None
        rows = list(self._catalogue.overview.who_does_what)
        also = self._topics.get(condition.get("also_topic", ""))
        if also is not None and also.status == FOUND:
            rows.append(also)
        for row in rows:
            for sentence in _sentences(row.quote or ""):
                named = [m for p in things for m in p.finditer(sentence)]
                given = [m for p in parties for m in p.finditer(sentence)]
                if not named or not given:
                    continue
                if not_own is not None and all(not_own.search(sentence[min(a.end(), b.end()):max(a.start(), b.start())])
                                               for a in named for b in given):
                    continue
                return short_place(row.places), row.quote
        return None


def _sentences(text: str) -> list[str]:
    """The text's sentences: cut after a full stop or semicolon that ends a word (never "1." in a list)."""
    return [s for s in re.split(r"(?<=[A-Za-z\)][.;])\s+(?=[A-Z])", text) if s.strip()]


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


def _term(amount: str) -> str:
    return re.sub(r"\s*-?\s*(year|month)s?\s*$", r"-\1", amount.strip().lower())


def _warranty_rows(overview, found: Found) -> list[Found]:
    services = {s.item: s for s in overview.services}
    agreement = services.get(_SERVICE_AGREEMENT)
    return [found] + ([agreement] if agreement is not None and agreement.status == FOUND else [])


def _warranty_extension(rows: list[Found], warranty: dict) -> tuple[str, str, Found] | None:
    """("found"|"missing_years", the extension line or "", the row it came from) for the first row
    whose quote calls for a warranty or service contract longer than the standard year — None when
    none does."""
    for row in rows:
        if not any(re.search(p, row.quote, re.I) for p in warranty["extension_words"]):
            continue
        years = re.search(warranty["extension_years"], row.quote, re.I)
        if years is None:
            return "missing_years", "", row
        return "found", warranty["extension"].format(years=years.group(1).lower()), row
    return None


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
    contract = warranty["contract"].format(term=_term(found.amount))
    items = [_line(warranty["heading"], 1, None), _line(contract, 2, None)]
    evidence.append(Evidence(warranty["heading"], where, found.quote, "CONFIRMED"))
    evidence.append(Evidence(contract, where, found.quote, "CONFIRMED"))

    extension = _warranty_extension(_warranty_rows(overview, found), warranty)
    if extension is not None:
        state, text, row = extension
        if state == "missing_years":
            flags.append(f"Say for how many years the warranty is extended — the job asks for it but the years "
                         f"weren't read: “{row.quote}” ({short_place(row.places)})")
        else:
            items.append(_line(text, 2, None))
            evidence.append(Evidence(text, short_place(row.places), row.quote, "CONFIRMED"))
    return items


def extended_warranty_block(catalogue, data: dict | None = None) -> tuple[Block | None, list[str], list[Evidence]]:
    """The Master Template's standalone "Qty (1) Extended Warranty" block: printed only when the
    job's warranty or service/maintenance agreement calls for a term longer than the standard year,
    with that term quoted word for word.

    Call this from estimator.writing.write.build_job, after the front end and the systems are
    written, and — when it returns a block — append the block to Job.blocks and fold its evidence
    and flags into the review list the same way apply_exceptions' systems are. None, with no flags
    and no evidence, when the job never asks for an extension."""
    data = data or _load(FRONT_END_FILE)
    warranty = data["warranty"]
    overview = catalogue.overview
    services = {s.item: s for s in overview.services}
    found = services.get(_WARRANTY)
    if found is None or found.status != FOUND or not found.amount:
        return None, [], []
    extension = _warranty_extension(_warranty_rows(overview, found), warranty)
    if extension is None:
        return None, [], []
    state, text, row = extension
    if state == "missing_years":
        flag = (f"Say for how many years the warranty is extended — the job asks for it but the years "
               f"weren't read: “{row.quote}” ({short_place(row.places)})")
        return None, [flag], []
    where = short_place(found.places)
    contract = warranty["contract"].format(term=_term(found.amount))
    items = (_line(warranty["heading"], 1, None), _line(contract, 2, None), _line(text, 2, None))
    evidence = [Evidence(warranty["heading"], where, found.quote, "CONFIRMED"),
               Evidence(contract, where, found.quote, "CONFIRMED"),
               Evidence(text, short_place(row.places), row.quote, "CONFIRMED")]
    return Block(header=warranty["extended_header"], items=items), [], evidence


_GLOBAL_POINTS = "Global Points"
_GP_TEMPERATURE_LINE = "Furnish and Install Outside Air Temperature"
_GP_HUMIDITY_LINE = "Furnish and Install Outside Air Humidity"


def global_points_block(catalogue, data: dict | None = None, templates=None
                        ) -> tuple[Block | None, list[Evidence]]:
    """The Master Template's "Qty (1) Global Points" block, with the outside-air temperature and
    humidity lines: printed only when the spec or sequence names an outside-air temperature or
    humidity sensor, using the Master Template's own Global Points entry (assets/system_templates.json)
    for the header and the lines' wording.

    Call this from estimator.writing.write.build_job (templates is the same tuple load_templates()
    already gives it), after the front end and the systems are written, and — when it returns a
    block — append the block to Job.blocks and fold its evidence into the review list the same way
    apply_exceptions' systems are. None, with no evidence, when neither is named."""
    data = data or _load(FRONT_END_FILE)
    templates = templates if templates is not None else load_templates()
    template = template_for("", _GLOBAL_POINTS, templates)
    if template is None:
        return None, []
    held = _Conditions(catalogue, data, {t.item: t for t in catalogue.overview.topics})
    temperature = held.check("oa_temperature")
    humidity = held.check("oa_humidity")
    if temperature is None and humidity is None:
        return None, []
    lines = {line.text: line for line in template.lines}
    items: list[Item] = []
    evidence: list[Evidence] = []
    temp_line = lines.get(_GP_TEMPERATURE_LINE)
    if temp_line is not None:
        items.append(_line(temp_line.text, 1, 1))
        if temperature is not None:
            where, quote = temperature
            evidence.append(Evidence(temp_line.text, where, quote, "CONFIRMED"))
        else:
            evidence.append(Evidence(temp_line.text, _TEMPLATE_DEFAULT, "", "ASSUMPTION"))
    humidity_line = lines.get(_GP_HUMIDITY_LINE)
    if humidity_line is not None and humidity is not None:
        where, quote = humidity
        items.append(_line(humidity_line.text, 1, 1))
        evidence.append(Evidence(humidity_line.text, where, quote, "CONFIRMED"))
    header = " ".join(template.header.format(n=1).split())
    return Block(header=header, items=tuple(items)), evidence


# --- the header -------------------------------------------------------------------

# T-005 ruling 3 (estimator, 2026-10-11): "Quote #" is the job number and "Reference" the project name, both from the
# job folder ("<job number>, <project name>"), the parent of "2. Takeoffs". The run is given the takeoff folder, so the
# job folder is found by walking up from it. When there is none, both print as a red *** placeholder (the proposal
# writer paints a value carrying *** red) and a flag asks for them: never the takeoff folder's name, never a bracket
# fill-in.
HEADER_PLACEHOLDER = "***"
_TAKEOFFS_FOLDER = re.compile(r"^\s*(?:\d+\s*[.)]\s*)?take[\s-]?offs?\s*$", re.I)
_JOB_NUMBER_FOLDER = re.compile(r"^\s*\d{2}-\d{3,}\b")


def job_folder(root: Path) -> Path | None:
    """The job folder of a takeoff folder: the parent of the "2. Takeoffs" folder at or above `root`; else the nearest
    folder at or above `root` whose name opens with a job number ("26-0544, ..."), which is a job folder by its name
    (the old app is given the job folder itself); else None."""
    chain = [Path(root), *Path(root).parents]
    for here, parent in zip(chain, chain[1:]):
        # a folder named Takeoff inside "2. Takeoffs" matches the same word. Keep walking so the job folder is the
        # parent of the outer takeoffs folder, not "2. Takeoffs" itself.
        if (_TAKEOFFS_FOLDER.match(here.name) and parent.name
                and not _TAKEOFFS_FOLDER.match(parent.name)):
            return parent
    return next((here for here in chain if _JOB_NUMBER_FOLDER.match(here.name)), None)


def job_header(catalogue, reading, today: dt.date, data: dict | None = None) -> tuple[Header, list[str]]:
    """The cover page's table, and the flags for whatever had to be left PENDING."""
    settings = (data or _load(FRONT_END_FILE))["header"]
    flags: list[str] = []
    found = job_folder(Path(catalogue.job.root))
    if found is None:
        quote_number = reference = HEADER_PLACEHOLDER
        flags.append(f"Give the job number and the project name for the cover page — the takeoff folder "
                     f"“{Path(catalogue.job.root).name}” is not inside a job folder (the folder that holds "
                     f"“2. Takeoffs”), so both print as {HEADER_PLACEHOLDER}")
    else:
        number, _, rest = found.name.partition(",")
        quote_number = number.strip() or HEADER_PLACEHOLDER
        reference = rest.strip()
        if not reference:
            reference = HEADER_PLACEHOLDER
            flags.append(f"Give the project name for the cover page — the job folder “{found.name}” has only its "
                         f"number")

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
    own ("ALDER & BRISK, Inc."). A real title block is a grid of several labels and values
    ("ENGINEER" and "DATE" side by side, each with its own value below it), so the value is read from
    the same column as the label — the nearest text below it, close to its own left edge — never
    whatever merely comes next in reading order (that could be another column's label or value
    entirely, "ISSUE FOR BID" under a neighbouring "DATE"). Of what's in that column, a name that
    looks like a firm's (an "&", or a corporate suffix) is preferred to one that reads as a person's
    (a name with a professional-license line, "PAT Q. ALDER, PE")."""
    label = re.compile(settings["engineer_label"], re.I)
    skip = {w.upper() for w in settings.get("engineer_label_skip", ())}
    hint = re.compile(settings["engineer_label_company_hint"], re.I)
    x_tolerance = settings.get("engineer_label_x_tolerance", 0.05)
    y_reach = settings.get("engineer_label_y_reach", 0.03)
    pages = {(s.document, s.page) for s in catalogue.sheets if s.discipline in settings["engineer_disciplines"]}
    for record in catalogue.pages:
        if (record.document, record.page) not in pages:
            continue
        spans = record.edge_spans
        for label_span in spans:
            if not label.match(" ".join(label_span.text.split())):
                continue
            candidates = [s for s in spans if s is not label_span
                         and label_span.y0 < s.y0 <= label_span.y0 + y_reach
                         and abs(s.x0 - label_span.x0) <= x_tolerance]
            candidates = [" ".join(s.text.split()) for s in sorted(candidates, key=lambda s: s.y0)]
            candidates = [c for c in candidates if not label.match(c) and c.rstrip(":").strip().upper() not in skip]
            if not candidates:
                continue
            return next((c for c in candidates if hint.search(c)), candidates[0])
    return None


def _spec_pages(catalogue) -> set[tuple[str, int]]:
    pages: set[tuple[str, int]] = set()
    for section in getattr(catalogue, "sections", ()):
        for page in range(section.first_page, section.last_page + 1):
            pages.add((section.document, page))
    return pages


def _spec_footer_engineer(catalogue, firm: re.Pattern) -> str | None:
    """Else the most common firm name printed on the spec's own pages — the same boilerplate line
    (a header or a footer, wherever the page puts it) that repeats on page after page, the same
    "engineer/consulting/associates" firm-name pattern the title blocks use."""
    spec_pages = _spec_pages(catalogue)
    counts: Counter[str] = Counter()
    for record in catalogue.pages:
        if (record.document, record.page) not in spec_pages:
            continue
        for line in clean_text(record.text).splitlines():
            squashed = " ".join(line.split())
            if squashed and firm.search(squashed):
                counts[squashed] += 1
    return counts.most_common(1)[0][0] if counts else None


def _natural(number: str) -> tuple:
    return tuple(int(part) if part.isdigit() else part for part in re.split(r"(\d+)", number.upper()))


def _letters(number: str) -> str:
    match = re.match(r"[A-Za-z]+", number)
    return match.group(0).upper() if match else ""


def _dated(template: str, dates) -> str:
    """The "based on" line's form: with no date read, the "Dated: …" part is left out rather than
    printing a placeholder (the review list asks for the date)."""
    return template if dates else re.sub(r"\s*Dated:\s*\{date\}", "", template)


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
        lines.append(_dated(template, dates).format(first=ordered[0], last=ordered[-1], date=date))
    if undated:
        flags.append("Give the drawings' issue date for “based on” — no revision date was read from the title "
                     f"blocks of the {', '.join(undated)} set")

    section_lines, undated_sections = _based_on_sections(catalogue, reading, settings)
    lines += section_lines
    if undated_sections:
        word = "section" if len(undated_sections) == 1 else "sections"
        flags.append(f"Give the issue date for “based on” — no date was read from the {word} "
                     f"{', '.join(undated_sections)}")

    if not lines:
        flags.append("Say which drawings the proposal is based on — no mechanical or controls sheet numbers were read")
        return ["[drawings the proposal is based on]"]
    return lines


_EDGE_LINES = 6                 # a page's header and footer: its first and last lines
_PROJECT_NUMBER = re.compile(r"\bproject\s*(?:no\.?|number|#)", re.I)
_NEAR_PROJECT = 300             # characters either side of "Project No." a date is read from


def _edge_date(text: str) -> dt.date | None:
    lines = [line for line in (text or "").splitlines() if line.strip()]
    return parse_date("\n".join(lines[:_EDGE_LINES] + lines[-_EDGE_LINES:])) if lines else None


def _project_date(text: str) -> dt.date | None:
    for m in _PROJECT_NUMBER.finditer(text or ""):
        found = parse_date(text[max(0, m.start() - _NEAR_PROJECT):m.end() + _NEAR_PROJECT])
        if found:
            return found
    return None


def _section_dates(catalogue, section) -> list[dt.date]:
    """The spec section's issue dates: from its pages' header or footer ("Issued for Bid 03/31/2026"), else
    a date near "Project No." on its pages, else near "Project No." elsewhere in the same document (the
    volume's cover). Never a date from the body's text."""
    pages = [r for r in catalogue.pages if r.document == section.document]
    own = [r for r in pages if section.first_page <= r.page <= section.last_page]
    others = [r for r in pages if not section.first_page <= r.page <= section.last_page]
    for records, read in ((own, _edge_date), (own, _project_date), (others, _project_date)):
        dates = [d for d in (read(r.text) for r in records) if d]
        if dates:
            return dates
    return []


def _based_on_sections(catalogue, reading, settings: dict) -> tuple[list[str], list[str]]:
    """The controls spec sections that carry a schedule or a sequence of operation, each with its
    date — else "[date]", flagged. The same section number reissued in more than one document (a
    base spec and its addendum) is one line, not two: its dates are pooled and the latest governs,
    the same way "based on"'s own sheet numbers already do."""
    schedule_pages = {(s.document, s.page) for s in getattr(reading, "schedules", ())}
    sequence_ranges = [(b.document, b.first_page, b.last_page) for b in getattr(reading, "backbone", ())
                       if not b.duplicate_of]
    pooled: dict[str, dict] = {}
    order: list[str] = []
    for section in getattr(catalogue, "sections", ()):
        if not section.controls:
            continue
        has_schedule = any(document == section.document and section.first_page <= page <= section.last_page
                           for document, page in schedule_pages)
        has_sequence = any(document == section.document and first <= section.last_page and last >= section.first_page
                           for document, first, last in sequence_ranges)
        if not (has_schedule or has_sequence):
            continue
        dates = _section_dates(catalogue, section)
        entry = pooled.setdefault(section.number, {"title": section.title, "dates": []})
        entry["dates"] += dates
        if section.number not in order:
            order.append(section.number)

    lines, undated = [], []
    for number in order:
        entry = pooled[number]
        dates = entry["dates"]
        date = max(dates).strftime(settings["date_format"]) if dates else settings["undated"]
        if not dates:
            undated.append(number)
        lines.append(_dated(settings["spec_section_line"], dates).format(number=number, title=entry["title"],
                                                                         date=date))
    return lines, undated
