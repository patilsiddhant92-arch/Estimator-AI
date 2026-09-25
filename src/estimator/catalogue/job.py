"""One job, catalogued: every stage of build step 3, and the flags an estimator should look at."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from estimator.catalogue.documents import JobFolder, find_documents
from estimator.catalogue.overview import FOUND, SpecOverview, build_overview
from estimator.catalogue.pdf import tessdata
from estimator.catalogue.qualify import BidCheck, check_bid
from estimator.catalogue.register import PageRecord, register_job
from estimator.catalogue.sheet_types import Sheet, classify_sheet
from estimator.catalogue.spec_sections import SpecSection, index_sections
from estimator.catalogue.tags import TagEntry, index_tags
from estimator.catalogue.title_block import read_title_block


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


def catalogue_job(root: Path, cache_dir: Path | None = None, workers: int = 1) -> Catalogue:
    job = find_documents(root)
    pages = tuple(register_job(job, cache_dir, workers))
    kinds = {d.relative: d.kind for d in job.documents}
    sheets = tuple(classify_sheet(record, read_title_block(record.edge_spans))
                   for record in pages if record.large_sheet)
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


def _repeats(catalogue: Catalogue) -> tuple[list[str], set[tuple[str, str]]]:
    """One document's sheet numbers can be almost entirely a repeat of another's — a marked-up
    copy of the same set. One line says so, instead of an "is on N pages" flag per sheet (M2)."""
    numbers: dict[str, set[str]] = defaultdict(set)
    for sheet in catalogue.sheets:
        if sheet.number:
            numbers[sheet.document].add(sheet.number)
    by_size = sorted(numbers, key=lambda d: -len(numbers[d]))
    lines: list[str] = []
    claimed: set[str] = set()
    covered: set[tuple[str, str]] = set()
    for original in by_size:
        for copy in by_size:
            if copy == original or copy in claimed or not numbers[copy]:
                continue
            if len(numbers[copy]) > len(numbers[original]):
                continue
            shared = numbers[copy] & numbers[original]
            if len(numbers[copy]) >= 3 and len(shared) / len(numbers[copy]) >= 0.8:
                lines.append(f"{_name(copy)} repeats {len(shared)} sheets of {_name(original)} — probably a marked-up copy")
                claimed.add(copy)
                covered |= {(number, copy) for number in shared}
    return lines, covered


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
    repeat_lines, repeat_covered = _repeats(catalogue)
    flags += repeat_lines
    places: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    for sheet in catalogue.sheets:
        if sheet.number and (sheet.number, sheet.document) not in repeat_covered:
            places[sheet.number][sheet.document].append(sheet.page)
    for number, by_document in places.items():
        count = sum(len(p) for p in by_document.values())
        if count > 1:
            where = "; ".join(f"{_name(doc)} p.{_ranges(p)}" for doc, p in by_document.items())
            flags.append(f"Sheet {number} is on {count} pages ({where})")
    if catalogue.bid.finding != "Qualifies":
        flags.append(f"Bid check: {catalogue.bid.finding} — the US team decides before this job is issued")
    return flags


def summary_lines(catalogue: Catalogue) -> list[str]:
    pages = catalogue.pages
    count = {status: sum(1 for p in pages if p.status == status) for status in ("ocr", "blank", "unreadable")}
    bid = catalogue.bid
    sheets = catalogue.sheets
    controls = list(dict.fromkeys(f"{s.number} {s.title}".strip() for s in catalogue.sections if s.controls))
    overview = catalogue.overview
    protocols = [t.item for t in overview.topics if t.section == "Protocols" and t.status == FOUND]
    ame_count = sum(1 for m in overview.makers if m.ame_quotes)
    return [
        f"{catalogue.job.name} — {len(catalogue.job.documents)} documents, {len(pages)} pages: "
        f"{count['ocr']} read by OCR, {count['blank']} blank, {count['unreadable']} could not be read.",
        f"Bid check: {bid.finding} — {bid.reason}",
        f"Other controls manufacturers named, for the US team: {', '.join(bid.others) or 'none'}.",
        f"Spec overview: {len(overview.makers)} manufacturers named ({ame_count} AME gets prices for); "
        f"protocols: {', '.join(protocols) or 'none stated'}.",
        f"Drawing sheets: {len(sheets)}; {sum(1 for s in sheets if s.number)} with a sheet number; "
        f"{sum(1 for s in sheets if s.number and not s.types and s.discipline in CONTROLS_DISCIPLINES)} "
        f"sheets that carry controls scope not sorted by type.",
        f"Spec sections: {len(catalogue.sections)}; controls sections: {'; '.join(controls) or 'none found'}.",
        f"Equipment tags: {len(catalogue.tags)} ({sum(1 for t in catalogue.tags if t.on_schedules)} on schedules).",
        f"{_plural(len(catalogue.flags), 'thing')} to look at — see the Flags tab." if catalogue.flags else "Nothing to flag.",
    ]
