"""The reading run (design 2026-09-29 §2): seed the ledger, then ask each pass in the estimator's order through the
judge, carrying the ledger between them. A pass with nothing to read is skipped and says so. A pass too long for one
request is cut at line ends and its parts asked and applied in turn. The run stops at the first pass with no
answer (in chat mode, the request is waiting), because every later pass reads this one's understanding.

The plans and risers passes also see the sheets they read as whole-sheet pictures (their `picture_types`), the
sheets with the most device labels first, up to a cap; the sheets left out are named in the prompt."""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from estimator.catalogue.documents import document_names
from estimator.ledger.passes import LEDGER_PROMPT, PASSES, apply, documents, prompt, schema
from estimator.ledger.seed import dossier_sections, seed, sheet_text_sheets
from estimator.writing.dossier import sheet_pictures

PICTURE_CAP = 24        # whole-sheet pictures sent with one pass


def _label_count(devices: str, number: str) -> int:
    """How many of the dossier's device-label lines (section 6) name this sheet; none for a sheet with no number."""
    if not number:
        return 0
    pattern = re.compile(rf"(?<![\w-]){re.escape(number)}(?![\w-]|\.\d)")
    return sum(1 for line in devices.splitlines() if pattern.search(line))


def _picture_sheets(pass_, dossier, catalogue, text: str, cap: int) -> tuple[list[tuple[str, int]], list[str]]:
    """The (document, page) of the sheets whose text this part of the pass reads and whose types are the pass's
    picture types, the most device labels first, within the cap; and the sheets left out over the cap, by name.
    Each 7c line is its own page (`sheet_text_sheets`): a reissue is pictured from its own page, never the one it
    replaces."""
    read = set(re.findall(r"\[(S\d+)\]", text))
    wanted = set(pass_.picture_types)
    chosen: dict[tuple[str, int], object] = {}
    for sid, sheet, _line in sheet_text_sheets(dossier, catalogue):
        if sid in read and sheet is not None and wanted & set(sheet.types or ()):
            chosen.setdefault((sheet.document, sheet.page), sheet)
    devices = dossier_sections(dossier.text).get(6, "")
    order = sorted(chosen, key=lambda k: -_label_count(devices, chosen[k].number or ""))   # stable: ties keep the order
    kept, left = order[:max(0, cap)], order[max(0, cap):]
    numbers = Counter(chosen[k].number for k in chosen if chosen[k].number)

    def name(key: tuple[str, int]) -> str:
        number = chosen[key].number
        if number and numbers[number] == 1:
            return number
        return f"{number} ({Path(key[0]).name})" if number else f"{Path(key[0]).name} page {key[1]}"

    return kept, [name(k) for k in left]


def _picture_source(image, catalogue) -> str:
    """A whole-sheet picture's source, starting with its sheet number ("M-201 FIRST FLOOR PLAN — whole sheet …,
    Drawings.pdf page 3 (picture)"), so a count note can name the sheet."""
    number = getattr(image, "sheet", None) or next(
        (s.number for s in getattr(catalogue, "sheets", ()) or ()
         if s.number and s.document == image.document and s.page == image.page), "")
    what = image.what if not number or image.what.startswith(number) else f"{number} {image.what}"
    documents = getattr(getattr(catalogue, "job", None), "documents", ()) or ()
    names = document_names([d.relative for d in documents] + [image.document])     # a shared file name: its path
    return f"{what}, {names.get(image.document) or Path(image.document).name} page {image.page} (picture)"


def read_job(judge, dossier, catalogue, save_to: Path | None = None, limit: int | None = None,
             pictures: bool = True, picture_cap: int = PICTURE_CAP):
    """`pictures=False` keeps every pass text-only. Sheet pictures are kept beside the dossier's own (the judge's
    cache folder's parent is the run's cache), so a schedule sheet already pictured is reused."""
    from estimator.writing import whole_job as wj
    limit = limit or wj.SPLIT_LIMIT
    ledger = seed(dossier)
    images = list(getattr(dossier, "images", ()) or ())
    known_all = wj.known_ids(dossier.text, images)
    next_id = len(images)              # picture ids continue the dossier's numbering, once each across the run
    picture_cache = Path(judge.cache_dir).parent if getattr(judge, "cache_dir", None) is not None else None

    def save() -> None:
        if save_to is not None:
            ledger.save(save_to)

    for pass_ in PASSES:
        text = documents(pass_, dossier, catalogue)
        if not text.strip():
            ledger.understanding[pass_.name] = f"nothing to read: no {pass_.title} in this job"
            save()
            continue
        parts = wj._chunks(text, limit) if len(text) > limit else [text]
        pass_images = images if pass_.with_images else []
        refused: list[str] = []
        understood: list[str] = []
        for n, part in enumerate(parts, start=1):
            name = f"the {pass_.title} pass" + (f" (part {n} of {len(parts)})" if len(parts) > 1 else "")
            extra = {"pass": pass_.name} | ({"part": f"{n} of {len(parts)}"} if len(parts) > 1 else {})
            part_images, ids, notes = list(pass_images), None, []
            if pictures and pass_.picture_types:
                keys, left_out = _picture_sheets(pass_, dossier, catalogue, part, picture_cap)
                drawn, flags = (sheet_pictures(catalogue, picture_cache, keys, f"whole sheet for the {pass_.title} pass")
                                if keys else ([], []))
                if drawn:
                    new_ids = [f"I{next_id + k}" for k in range(1, len(drawn) + 1)]
                    next_id += len(drawn)
                    for pid, image in zip(new_ids, drawn):
                        ledger.sources.setdefault(pid, _picture_source(image, catalogue))
                    ids = [f"I{k}" for k in range(1, len(part_images) + 1)] + new_ids
                    part_images += drawn
                if left_out:
                    notes.append(f"Sheets not pictured (over the cap): {', '.join(left_out)}")
                notes += [f"Not pictured: {flag}" for flag in flags]
            got = judge.ask_pass(name, LEDGER_PROMPT, prompt(pass_, ledger, part, part_images, ids, notes), schema(),
                                 part_images, extra, ids=ids)
            if got is None:
                ledger.stopped_at = pass_.name
                ledger.complete = False
                ledger.refused[pass_.name] = refused
                save()
                return ledger
            known = wj.known_ids(part, part_images, ids) | frozenset(ledger.facts) | known_all
            refused += apply(pass_, ledger, got[0], known)
            understood.append(ledger.understanding.get(pass_.name, ""))
        ledger.understanding[pass_.name] = " ".join(u for u in understood if u)   # every part's understanding
        ledger.refused[pass_.name] = refused
        save()
    ledger.complete = True
    ledger.stopped_at = ""
    save()
    return ledger
