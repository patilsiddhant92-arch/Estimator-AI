"""One job, catalogued: every stage of build step 3, and the flags an estimator should look at."""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from pathlib import Path

from estimator.catalogue.documents import JobFolder, find_documents
from estimator.catalogue.overview import FOUND, STANDARD_EXCLUSION, SpecOverview, build_overview
from estimator.catalogue.pdf import tessdata
from estimator.catalogue.qualify import BidCheck, check_bid
from estimator.catalogue.register import PageRecord, register_job
from estimator.catalogue.sheet_types import Sheet, classify_sheet, discipline_from_filename
from estimator.catalogue.spec_sections import SpecSection, index_sections
from estimator.catalogue.tags import TagEntry, index_tags, is_type_tag, label_keys, plan_labels
from estimator.catalogue.title_block import read_drawing_index, read_title_block


@dataclass(frozen=True)
class Catalogue:
    job: JobFolder
    pages: tuple[PageRecord, ...]
    sheets: tuple[Sheet, ...]
    sections: tuple[SpecSection, ...]
    bid: BidCheck
    tags: tuple[TagEntry, ...]
    flags: tuple[str, ...]
    overview: SpecOverview = field(default_factory=SpecOverview)


CONTROLS_DISCIPLINES = ("Mechanical", "Controls", "Plumbing", "Fire protection", "Unknown")


def catalogue_job(root: Path, cache_dir: Path | None = None, workers: int = 1,
                  documents: str | Path | None = None) -> Catalogue:
    """The job folder `root` catalogued; with `documents`, only that subfolder of it is read."""
    job = find_documents(root, documents)
    pages = tuple(register_job(job, cache_dir, workers))
    kinds = {d.relative: d.kind for d in job.documents}
    # A sheet whose title block gives no title takes it from the drawing index, wherever the job lists one.
    index = read_drawing_index(record.text for record in pages if record.status in ("text", "ocr"))
    sheets = tuple(classify_sheet(record, read_title_block(record.edge_spans, index))
                   for record in pages if record.large_sheet)
    # A sheet whose discipline is still unknown takes it from its document's file name, when the
    # name carries a single discipline token — but never for a spec book, which isn't a drawing set.
    sheets = tuple(_with_filename_discipline(sheet, kinds) for sheet in sheets)
    by_sheet = {(s.document, s.page): s for s in sheets}
    written = [record for record in pages if kinds[record.document] != "drawings"]
    sections = tuple(index_sections(written))
    has_spec_book = any(d.kind == "specs" for d in job.documents)
    bid = check_bid(pages, sections, by_sheet, has_spec_book)
    tags = tuple(index_tags(pages, by_sheet))
    overview = build_overview(pages, sheets, sections)
    catalogue = Catalogue(job, pages, sheets, sections, bid, tags, (), overview)
    return Catalogue(job, pages, sheets, sections, bid, tags, tuple(_flags(catalogue)), overview)


def _name(relative: str) -> str:
    return relative.rsplit("/", 1)[-1]


def _with_filename_discipline(sheet: Sheet, kinds: dict[str, str]) -> Sheet:
    if sheet.discipline != "Unknown" or kinds.get(sheet.document) != "drawings":
        return sheet
    discipline = discipline_from_filename(_name(sheet.document))
    return replace(sheet, discipline=discipline) if discipline else sheet


def _ranges(numbers: list[int]) -> str:
    runs: list[list[int]] = []
    for n in sorted(numbers):
        if runs and n == runs[-1][1] + 1:
            runs[-1][1] = n
        else:
            runs.append([n, n])
    return ", ".join(str(a) if a == b else f"{a}–{b}" for a, b in runs)


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


TRADE_WORDS = frozenset({"PLAN", "PLANS", "DUCTWORK", "DUCT", "PIPING", "PIPE", "CONTROLS", "CONTROL", "HVAC",
                         "MECHANICAL", "MECH", "PLUMBING", "AND"})


def title_without_number(sheet) -> str:
    """The title upper-cased, its own sheet number taken out only where a title block prefixes or ends it: as a
    whole token at the title's start or end ("M-301 MECHANICAL PLAN" is "MECHANICAL PLAN"). A number inside the
    title names a part of it ("WING MA1 FIRST FLOOR PLAN" on MA1 keeps MA1, REVIEW-FINAL6 F4)."""
    title = (sheet.title or "").upper().strip()
    if sheet.number:
        number = re.escape(sheet.number.upper().strip())
        title = re.sub(rf"^{number}(?![A-Z0-9])|(?<![A-Z0-9]){number}$", " ", title).strip()
    return title


def title_words(sheet) -> tuple[str, ...]:
    """The title's words IN ORDER, its own sheet number (`title_without_number`) and the trade and plan words
    (TRADE_WORDS) taken out ("HVAC DUCTWORK FIRST FLOOR PLAN" and "HVAC PIPING FIRST FLOOR PLAN" are both FIRST
    FLOOR). In order, never sorted: "BUILDING 1 LEVEL 2" and "BUILDING 2 LEVEL 1" are two places (REVIEW-FINAL6
    F2). The plan groups (`inventory.plan_groups`) and supersession (`revisions.supersede`: a reissue replaces only
    the sheet of its number with these same words) both read titles so."""
    title = re.sub(r"\bL-(\d)", r"L\1", title_without_number(sheet))
    return tuple(w for w in re.findall(r"[A-Z0-9]+", title) if w not in TRADE_WORDS)


COPY_SHARED = 3          # unit tags a marked-up copy's plans must repeat of its original's ...
COPY_OVERLAP = 0.6       # ... and this share of the original's unit tags (REVIEW-FINAL6 F3, REVIEW-FINAL7 F1)
COPY_TEXT = 0.9          # the share of the original's words on the shared sheets the copy repeats (REVIEW-FINAL7 F1)


@dataclass(frozen=True)
class DocumentRepeat:
    """A document whose sheet numbers are almost all another's (3 or more, 80% of its own)."""
    copy: str                   # the document that repeats
    original: str               # the document it repeats
    numbers: frozenset[str]     # the sheet numbers it repeats
    same: bool                  # True: a marked-up copy (the same units on its plans), read once; False: another set
                                # of drawings (a second building issued with the same sheet numbers), read and summed
    why: str = ""               # another set: why it is no marked-up copy, in words ("not their units")


def _issue(documents: dict, relative: str) -> tuple | None:
    """The issue a document belongs to (its revision); None for an addendum or a duplicate file, which reissue a
    sheet: supersession decides between them, never the copy rule."""
    d = documents.get(relative)
    if d is None:
        return ("",)
    if d.kind == "addendum" or getattr(d, "duplicate_of", None):
        return None
    return (d.revision,)


def _plan_units(catalogue, document: str, numbers: frozenset[str], keys: dict[str, str]) -> set[str]:
    """The unit tags (`is_type_tag` false) on the document's plan sheets of these numbers, as the counts read them
    (`plan_labels`: labelled, or named anywhere on the plan)."""
    texts = {(p.document, p.page): p.text for p in catalogue.pages}
    units: set[str] = set()
    for sheet in catalogue.sheets:
        if sheet.document == document and sheet.number in numbers and "Plans" in sheet.types:
            units |= {tag for tag in plan_labels(texts.get((sheet.document, sheet.page)) or "", keys)
                      if not is_type_tag(tag)}
    return units


def _words(catalogue, document: str, numbers: frozenset[str]) -> Counter:
    """The words (letters and digits, upper case) on the document's sheets of these numbers."""
    pages = {(s.document, s.page) for s in catalogue.sheets if s.document == document and s.number in numbers}
    words: Counter = Counter()
    for p in catalogue.pages:
        if (p.document, p.page) in pages:
            words.update(re.findall(r"[A-Z0-9]+", (p.text or "").upper()))
    return words


def _plan_titles(catalogue, document: str, numbers: frozenset[str]) -> dict[str, set[str]]:
    titles: dict[str, set[str]] = defaultdict(set)
    for s in catalogue.sheets:
        if s.document == document and s.number in numbers and "Plans" in s.types:
            titles[s.number].add(" ".join((s.title or "").upper().split()))
    return titles


def _not_a_copy(catalogue, original: str, copy: str, shared: frozenset[str], keys: dict[str, str]) -> str:
    """Why `copy` is no marked-up copy of `original` ("" when it is one). A marked-up copy only adds clouds and text:
    its plans show no unit tag the original lacks (the original is the superset), at least COPY_SHARED of the
    original's unit tags and COPY_OVERLAP of them; the same plan titles on the shared numbers (BUILDING B is never a
    copy of BUILDING A); and COPY_TEXT of the original's words on the shared sheets (REVIEW-FINAL7 F1, F5)."""
    a, b = _plan_units(catalogue, original, shared, keys), _plan_units(catalogue, copy, shared, keys)
    if b - a:
        return f"shows unit tags {_name(original)} does not"
    if len(b) < COPY_SHARED or len(b) < COPY_OVERLAP * len(a):
        return "not their units"
    titles_a, titles_b = _plan_titles(catalogue, original, shared), _plan_titles(catalogue, copy, shared)
    if any(titles_a[number] != titles_b[number] for number in set(titles_a) & set(titles_b)):
        return "not their plan titles"
    words_a, words_b = _words(catalogue, original, shared), _words(catalogue, copy, shared)
    total = sum(words_a.values())
    if total and sum((words_a & words_b).values()) < COPY_TEXT * total:
        return "not their text"
    return ""


def document_repeats(catalogue) -> list[DocumentRepeat]:
    """Each document that repeats most of another's sheet numbers, and whether it is a marked-up copy. Sheet numbers
    alone never make a copy (REVIEW-FINAL6 F3), nor do shared tags (REVIEW-FINAL7 F1): a copy is one only when all
    of `_not_a_copy`'s tests hold, so a reduction is made only where it is provably safe. Any other document of the
    same issue is another set of drawings (a second building issued with the same numbers): read and summed, and
    said. Two documents of other issues (another revision label, an addendum, a duplicate file) are never copy and
    original: supersession decides between them, by their dates, and says when it cannot (F2). Of two documents the
    same size, the original is the one whose plans show the more units, then the one with less text (a copy adds
    markups), then the one whose name does not say it is marked up. Two documents never each claim the other: a
    document claimed as a copy is never an original, and an original is never claimed."""
    numbers: dict[str, set[str]] = defaultdict(set)
    for sheet in catalogue.sheets:
        if sheet.number:
            numbers[sheet.document].add(sheet.number)
    documents = {d.relative: d for d in getattr(getattr(catalogue, "job", None), "documents", ())}
    text = Counter()
    for p in catalogue.pages:
        text[p.document] += len(p.text or "")
    by_size = sorted(numbers, key=lambda d: (-len(numbers[d]), text[d], "MARK" in _name(d).upper(), d))
    keys: dict[str, str] | None = None
    found: list[DocumentRepeat] = []
    claimed: set[str] = set()
    originals: set[str] = set()
    for original in by_size:
        for copy in by_size:
            if original in claimed:
                break
            if copy == original or copy in claimed or copy in originals or not numbers[copy]:
                continue
            if len(numbers[copy]) > len(numbers[original]):
                continue
            shared = frozenset(numbers[copy] & numbers[original])
            if not (len(numbers[copy]) >= 3 and len(shared) / len(numbers[copy]) >= 0.8):
                continue
            issues = _issue(documents, original), _issue(documents, copy)
            if None in issues or issues[0] != issues[1]:
                continue
            if keys is None:
                keys = label_keys(t.tag for t in getattr(catalogue, "tags", ()))
            why = _not_a_copy(catalogue, original, copy, shared, keys)
            if (why and len(numbers[copy]) == len(numbers[original]) and original not in originals
                    and not _not_a_copy(catalogue, copy, original, shared, keys)):
                # the other way round: the document taken for the original is the marked-up copy (its plans show
                # fewer units than the other's, or its text is the other's plus markups)
                found.append(DocumentRepeat(original, copy, shared, True))
                claimed.add(original)
                originals.add(copy)
                break
            found.append(DocumentRepeat(copy, original, shared, not why, why))
            claimed.add(copy)
            originals.add(original)
    return found


def other_sets(catalogue) -> set[tuple[str, str]]:
    """(sheet number, document) of each sheet of another set of drawings (`document_repeats`, not a copy): a sheet
    read and summed beside the original's, never a version of it."""
    return {(number, r.copy) for r in document_repeats(catalogue) if not r.same for number in r.numbers}


def _repeat_line(r: DocumentRepeat) -> str:
    if r.same:
        return f"{_name(r.copy)} repeats {len(r.numbers)} sheets of {_name(r.original)} — probably a marked-up copy"
    return (f"{_name(r.copy)} repeats {len(r.numbers)} sheets of {_name(r.original)} but {r.why or 'not their units'}"
            f" — read as another set of drawings and counted; check whether it is a marked-up copy")


def repeats(catalogue: Catalogue) -> tuple[list[str], set[tuple[str, str]]]:
    """One document's sheet numbers can be almost entirely a repeat of another's (`document_repeats`). One line says
    so, instead of an "is on N pages" flag per sheet (M2), and the sheets of a marked-up copy are given as
    (number, document): read once, from the original. Another set of drawings is said, never set aside."""
    found = document_repeats(catalogue)
    return ([_repeat_line(r) for r in found],
            {(number, r.copy) for r in found if r.same for number in r.numbers})


def repeated_plans(catalogue) -> dict[str, tuple[str, tuple[int, ...]]]:
    """Plan sheets printed on several pages of one document with the same text on every page: one plan
    standing for several floors (26-0193's M-113.00, "LEVEL 13 TO 22", is on 10 pages). Sheet number →
    (the first document that repeats it, its pages). What is on such a plan is counted once and
    multiplied (reading/devices.py `typical_sheets`)."""
    texts = {(p.document, p.page): p.text for p in catalogue.pages}
    by_place: dict[tuple[str, str], list[int]] = defaultdict(list)
    for sheet in catalogue.sheets:
        if sheet.number and "Plans" in sheet.types:
            by_place[(sheet.number, sheet.document)].append(sheet.page)
    found: dict[str, tuple[str, tuple[int, ...]]] = {}
    for (number, document), pages in by_place.items():
        if number in found or len(pages) < 2:
            continue
        if len({texts.get((document, page), "") for page in pages}) == 1:
            found[number] = (document, tuple(sorted(pages)))
    return found


def _flags(catalogue: Catalogue) -> list[str]:
    job = catalogue.job
    flags = list(job.notes)
    flags += [f"{d.relative} could not be opened — is it a real PDF?" for d in job.documents if d.kind == "unreadable"]
    flags += [f"{d.relative} is password-protected — ask for an unlocked copy" for d in job.documents if d.kind == "password"]
    flags += [f"{d.relative} is the same file as {d.duplicate_of} — catalogued once" for d in job.documents if d.duplicate_of]
    if job.other_files:
        by_type = Counter(Path(f).suffix.lower() or "no extension" for f in job.other_files)
        breakdown = ", ".join(f"{n} {ext}" for ext, n in sorted(by_type.items()))
        flags.append(f"{_plural(len(job.other_files), 'file')} under the bid documents could not be read "
                     f"— not PDFs ({breakdown})")
        flags += [f"{f} is a zip file — unzip it into the job folder and run again" for f in job.other_files
                  if f.lower().endswith(".zip")]
    read_errors: dict[str, tuple[int, str]] = {}
    for record in catalogue.pages:
        if record.read_error and record.document not in read_errors:
            read_errors[record.document] = (record.page, record.read_error)
    flags += [f"{_name(doc)} could not be read from page {page} on — {reason}" for doc, (page, reason) in read_errors.items()]
    unreadable: dict[str, list[int]] = defaultdict(list)
    for record in catalogue.pages:
        if record.status == "unreadable" and record.document not in read_errors:
            unreadable[record.document].append(record.page)
    why = "OCR found no words on them" if tessdata() is not None else "OCR isn't set up on this computer"
    flags += [f"{_name(doc)}: {_plural(len(p), 'page')} could not be read ({'page' if len(p) == 1 else 'pages'} {_ranges(p)}) — {why}"
              for doc, p in unreadable.items()]
    blank_sheets: dict[str, list[int]] = defaultdict(list)
    for record in catalogue.pages:
        if record.status == "blank" and record.large_sheet:
            blank_sheets[record.document].append(record.page)
    flags += [f"{_name(doc)}: {_plural(len(p), 'blank drawing page')} ({'page' if len(p) == 1 else 'pages'} {_ranges(p)})"
              for doc, p in blank_sheets.items()]
    per_document: dict[str, list] = defaultdict(list)
    for sheet in catalogue.sheets:
        per_document[sheet.document].append(sheet)
    for doc, sheets in per_document.items():
        missing = [s.page for s in sheets if not s.number]
        if missing:
            flags.append(f"{_name(doc)}: no sheet number found on {len(missing)} of {len(sheets)} sheets "
                         f"({'page' if len(missing) == 1 else 'pages'} {_ranges(missing)})")
    untyped = [s for s in catalogue.sheets if s.number and not s.types and s.discipline in CONTROLS_DISCIPLINES]
    if untyped:
        unique = list(dict.fromkeys(s.number for s in untyped))   # each number named once, even from copies
        names = ", ".join(unique[:20]) + (" …" if len(unique) > 20 else "")
        flags.append(f"{_plural(len(untyped), 'drawing sheet')} could not be sorted by type — {names}")
    found = document_repeats(catalogue)
    flags += [_repeat_line(r) for r in found]
    repeat_covered = {(number, r.copy) for r in found for number in r.numbers}   # copies and other sets: one line
    places: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    for sheet in catalogue.sheets:
        if sheet.number and (sheet.number, sheet.document) not in repeat_covered:
            places[sheet.number][sheet.document].append(sheet.page)
    per_floor = repeated_plans(catalogue)
    for number, by_document in places.items():
        count = sum(len(p) for p in by_document.values())
        if number in per_floor and len(by_document) == 1:
            continue    # one plan per floor: the reading multiplies what is on it, and says so
        if count > 1:
            where = "; ".join(f"{_name(doc)} p.{_ranges(p)}" for doc, p in by_document.items())
            flags.append(f"Sheet {number} is on {count} pages ({where})")
    if catalogue.bid.finding != "Qualifies":
        flags.append(f"Bid check: {catalogue.bid.finding} — the US team decides before this job is issued")
    return flags


def scope_review_counts(overview: SpecOverview) -> tuple[int, int, int]:
    """(standard exclusions the job asks for, other systems to connect to, who-does-what lines)."""
    exclusions = sum(1 for f in overview.standard_lines if f.section == STANDARD_EXCLUSION and f.status == FOUND)
    systems = sum(1 for f in overview.integrations if f.status == FOUND)
    return exclusions, systems, len(overview.who_does_what) + overview.who_does_what_more


def summary_lines(catalogue: Catalogue) -> list[str]:
    pages = catalogue.pages
    count = {status: sum(1 for p in pages if p.status == status) for status in ("ocr", "blank", "unreadable")}
    bid = catalogue.bid
    sheets = catalogue.sheets
    controls = list(dict.fromkeys(f"{s.number} {s.title}".strip() for s in catalogue.sections if s.controls))
    overview = catalogue.overview
    protocols = [t.item for t in overview.topics if t.section == "Protocols" and t.status == FOUND]
    ame_count = sum(1 for m in overview.makers if m.ame_quotes)
    exclusions, systems, who = scope_review_counts(overview)
    return [
        f"{catalogue.job.name} — {len(catalogue.job.documents)} documents, {len(pages)} pages: "
        f"{count['ocr']} read by OCR, {count['blank']} blank, {count['unreadable']} could not be read.",
        f"Bid check: {bid.finding} — {bid.reason}",
        f"Other controls manufacturers named, for the US team: {', '.join(bid.others) or 'none'}.",
        f"Spec overview: {len(overview.makers)} manufacturers named ({ame_count} AME gets prices for); "
        f"protocols: {', '.join(protocols) or 'none stated'}.",
        f"Scope review: {exclusions} standard exclusions the job asks for; {systems} other systems to connect to; "
        f"{who} who-does-what lines.",
        f"Drawing sheets: {len(sheets)}; {sum(1 for s in sheets if s.number)} with a sheet number; "
        f"{sum(1 for s in sheets if s.number and not s.types and s.discipline in CONTROLS_DISCIPLINES)} "
        f"sheets that carry controls scope not sorted by type.",
        f"Spec sections: {len(catalogue.sections)}; controls sections: {'; '.join(controls) or 'none found'}.",
        f"Equipment tags: {len(catalogue.tags)} ({sum(1 for t in catalogue.tags if t.on_schedules)} on schedules).",
        f"{_plural(len(catalogue.flags), 'thing')} to look at — see the Flags tab." if catalogue.flags else "Nothing to flag.",
    ]
