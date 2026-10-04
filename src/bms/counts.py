"""The vision count cross-check (workstream 6, design §4.6).

Two counts of each tagged family on the plan sheets that show its tags, independent of the planner's count:
- located on the sheet text: the family's tags in the PDF page's text layer, each with its box (a tag inside a
  line of more than a few words is a note naming it, not a placed tag);
- counted on the sheet picture: the whole-sheet picture (as `estimator.writing.dossier.sheet_pictures` draws it)
  cut into overlapping tiles, and the sheet asked of the AI through a `bms.ai` Transport as one question (request
  kind "count_tags") carrying every tile as its own picture and every family's tag pattern on that sheet together.

A family's count on the plans is the number of different tags of the family found over all its plan sheets (a tag
shown on two sheets is one unit). `cross_check` adds every count that differs from the printed one to
`Count.others` with its Ref, keeps the highest as `Count.value`, never lowers a count, flags the devices counted from
a family whose counts disagree, and writes the proof images (a crop of the sheet with the counted tags boxed) and
their manifest under `<cache>/count-proofs/` for the review page (`load_proofs`, `proofs_for`). Without a transport
it does the located-text count only.
"""
from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from bms.counts_proof import PROOFS_FOLDER, draw_proof, load_manifest, save_manifest
from bms.counts_text import (canonical, family_pattern, fits, located_boxes, natural, prefix_owners, searcher)
from bms.counts_vision import COUNT_KIND, TILE, ask_sheet
from bms.model import Count, OtherCount, Ref

if TYPE_CHECKING:
    from estimator.catalogue.job import Catalogue

    from bms.model import Job

COUNT_TAGS = COUNT_KIND             # the request kind of a sheet's count question
LOCATED_QUOTE = "located on the sheet text"
SEEN_QUOTE = "counted on the sheet picture"
NO_SOURCE_QUOTE = "the count before the plan check, given without a source"
PLAN_TYPE = "Plans"
__all__ = ["Box", "CountResult", "count_tags", "count_sheet", "cross_check", "load_proofs", "proofs_for", "publish_proofs",
           "COUNT_TAGS", "TILE", "LOCATED_QUOTE", "SEEN_QUOTE", "PROOFS_FOLDER"]


@dataclass(frozen=True)
class Box:
    """Where one counted tag is on the sheet picture, in pixels of that picture."""
    x: int
    y: int
    width: int
    height: int
    text: str                 # the tag as read, e.g. "EF-3"


@dataclass(frozen=True)
class CountResult:
    value: int | None         # how many tags matching the pattern are on the sheet; None when it could not count
    boxes: tuple[Box, ...]    # one per counted tag (len(boxes) == value when value is not None)


def count_tags(image_path: Path, tag_pattern: str, *, transport=None) -> CountResult:
    """Count the tags matching `tag_pattern` (a Python regular expression over the tag as printed, e.g.
    "EF-[0-9]+") on one whole-sheet picture (a PNG, as `estimator.writing.dossier.sheet_pictures` draws them), by
    vision on tiles, each tag once even where tiles overlap.

    `transport` is a `bms.ai` Transport (chat or API); the sheet is one "count_tags" question carrying every tile's
    PNG (see `count_sheet`, which asks several patterns in the same question). The value is the number of different
    tags found (a tag read twice is one), with the box where each is first seen.

    Contract: never raises for an unreadable picture, a bad pattern, no transport or an unusable answer (returns
    `CountResult(None, ())`). The caller (`cross_check`) compares `value` with the family's Count: a different value
    is added to `Count.others` with a Ref (`source_id` the count's id, `quote` "counted on the sheet picture", `where`
    the sheet), the printed value becomes the higher, and the devices of that family get flag "quantity".
    """
    return count_sheet(image_path, [tag_pattern], transport=transport).get(tag_pattern, CountResult(None, ()))


def count_sheet(image_path: Path, tag_patterns, *, transport=None) -> dict[str, CountResult]:
    """Count every pattern of `tag_patterns` on one whole-sheet picture with ONE vision question (every tile as its
    own picture, every pattern together): {pattern: CountResult}, each as `count_tags` gives it. Every result is
    `CountResult(None, ())` when the sheet could not be counted (unreadable picture, a bad pattern, no transport,
    no usable answer yet). Never raises."""
    patterns = list(dict.fromkeys(tag_patterns))
    unknown = {p: CountResult(None, ()) for p in patterns}
    try:
        for pattern in patterns:
            re.compile(pattern)
        if transport is None or not patterns:
            return unknown
        found = ask_sheet(transport, Path(image_path), patterns)
        if found is None:
            return unknown
        results = {}
        for pattern in patterns:
            boxes = _distinct([(text, box) for text, box in found if fits(pattern, text)])
            results[pattern] = CountResult(len(boxes), tuple(boxes))
        return results
    except Exception:
        return unknown


def cross_check(job: "Job", catalogue: "Catalogue", cache: Path, *, transport=None) -> "Job":
    """The job with every family's text count checked against the plan counts (design §4.6), run after planning.

    Contract: for each family with tags, the plan sheets (sheet type "Plans", a controls discipline) whose text shows
    its tags are pictured (`estimator.writing.dossier.sheet_pictures(catalogue, cache, keys, what)`) and counted
    twice: located on the sheet text, and — with a `transport` — by `count_tags` on the picture (one vision pass per
    sheet for every family on it). Each count different from `Count.value` is added to `Count.others` with its Ref
    (`source_id` "C<n>", quote "located on the sheet text" or "counted on the sheet picture", `where` the sheets);
    a count equal to it is added to `sources`; `Count.value` becomes the highest (an unknown count takes the plan
    count), the earlier count moving to `others` with its sources; and the system's devices whose quantity was
    counted from the family's sources get flag "quantity" when the counts disagree. Proof images and their manifest
    go under `<cache>/count-proofs/`. Families whose sheets cannot be pictured or counted are left as they are.
    Pure apart from the picture cache under `cache`. Never lowers a count, never raises; running it twice changes
    nothing more."""
    try:
        return _Check(job, catalogue, Path(cache), transport).run()
    except Exception:
        return job


def load_proofs(cache: Path) -> list[dict]:
    """Every proof `cross_check` wrote under `cache`: dicts with `system_key`, `family`, `sheet` (the place),
    `picture` (the whole-sheet PNG), `proof` (the cropped PNG with the boxes, or None), `located_text` and
    `vision` (that sheet's counts, None when not counted), `located_tags` / `vision_tags`, `located_boxes` /
    `vision_boxes` ({x, y, width, height, text} in the picture's pixels) and `source_ids` (the Refs' ids)."""
    return load_manifest(cache)


def proofs_for(cache: Path, system_key: str, family: str) -> list[dict]:
    """The proofs of one family (see `load_proofs`), in sheet order."""
    return [p for p in load_manifest(cache) if p.get("system_key") == system_key and p.get("family") == family]


def publish_proofs(job: "Job", cache: Path, out: Path) -> Path | None:
    """Copy the proofs of this job's counts from `cache` into `out/count-proofs/` with their manifest
    (`proofs.json`, each `proof` a path relative to `out`), where `bms.review.review_page` shows them beside the
    count whose Ref id the entry names. Only entries of this job's families whose source ids this job still cites.
    Returns the manifest's path, or None when there is no proof to show. Never raises."""
    import json
    import shutil

    try:
        cited: dict[tuple[str, str], set[str]] = {}
        for system in job.systems:
            for family in system.families:
                refs = [*family.count.sources, *(o.ref for o in family.count.others)]
                cited[(system.key, family.name)] = {r.source_id for r in refs}
        folder = Path(out) / PROOFS_FOLDER
        entries = []
        for entry in load_manifest(cache):
            ids = cited.get((entry.get("system_key"), entry.get("family")), set())
            proof = Path(entry["proof"]) if entry.get("proof") else None
            if not ids & set(entry.get("source_ids") or ()) or proof is None or not proof.is_file():
                continue
            folder.mkdir(parents=True, exist_ok=True)
            if proof.resolve() != (folder / proof.name).resolve():
                shutil.copyfile(proof, folder / proof.name)
            entries.append({**entry, "proof": f"{PROOFS_FOLDER}/{proof.name}", "picture": None})
        if not entries:
            return None
        manifest = folder / "proofs.json"
        manifest.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
        return manifest
    except Exception:
        return None


# ---- the check -------------------------------------------------------------------------------------------------

def _distinct(found) -> list[Box]:
    """One box per different tag (where it is first seen, top to bottom, left to right), in tag order."""
    first: dict[str, tuple[int, int, int, int]] = {}
    for text, box in sorted(found, key=lambda f: (f[1][1], f[1][0])):
        first.setdefault(canonical(text), box)
    return [Box(*first[tag], tag) for tag in sorted(first, key=natural)]


def _name(document: str) -> str:
    return document.rsplit("/", 1)[-1]


@dataclass
class _Sheet:
    key: tuple[str, int]
    place: str                       # "M-101, Drawings.pdf page 2"
    picture_place: str               # "M-101 whole sheet, Drawings.pdf page 2 (picture)"
    picture: Path | None = None
    located: list | None = None      # (tag, box) on the sheet text; None when the page could not be read
    seen: list | None = None         # (tag, box) on the picture; None when not counted


class _Check:
    def __init__(self, job, catalogue, cache: Path, transport) -> None:
        self.job, self.catalogue, self.cache, self.transport = job, catalogue, cache, transport
        used = [int(m.group(1)) for ref in _refs(job) if (m := re.fullmatch(r"C(\d+)", ref.source_id))]
        self.next_id = max(used, default=0) + 1

    def run(self):
        from estimator.catalogue.job import CONTROLS_DISCIPLINES

        families = [(s, f) for s in self.job.systems for f in s.families if any(t.strip() for t in f.tags)]
        if not families:
            return self.job
        owners = prefix_owners(f.tags for s in self.job.systems for f in s.families)
        patterns = {}
        for system, family in families:
            pattern = family_pattern(family.tags, owners)
            if pattern is not None:
                patterns[(system.key, family.name)] = pattern
        records = {(p.document, p.page): p for p in getattr(self.catalogue, "pages", ()) or ()}
        plans = [s for s in getattr(self.catalogue, "sheets", ()) or ()
                 if PLAN_TYPE in (s.types or ()) and s.discipline in CONTROLS_DISCIPLINES
                 and (s.document, s.page) in records]
        on_sheet: dict[tuple[str, str], list[tuple[str, int]]] = {}
        sheets: dict[tuple[str, int], _Sheet] = {}
        for (key, name), pattern in patterns.items():
            find = searcher(pattern)
            for sheet in plans:
                if find.search(records[(sheet.document, sheet.page)].text or ""):
                    on_sheet.setdefault((key, name), []).append((sheet.document, sheet.page))
                    if (sheet.document, sheet.page) not in sheets:
                        doc = _name(sheet.document)
                        sheets[(sheet.document, sheet.page)] = _Sheet(
                            (sheet.document, sheet.page),
                            f"{sheet.number}, {doc} page {sheet.page}" if sheet.number else f"{doc} page {sheet.page}",
                            (f"{sheet.number} whole sheet, {doc} page {sheet.page} (picture)" if sheet.number
                             else f"{doc} page {sheet.page} (picture)"))
        if not sheets:
            return self.job
        for key, sheet in sheets.items():
            here = [patterns[f] for f, keys in on_sheet.items() if key in keys]
            self._count_sheet(sheet, here)

        job, entries = self.job, []
        for system, family in families:
            keys = on_sheet.get((system.key, family.name))
            if not keys:
                continue
            pattern = patterns[(system.key, family.name)]
            system = job.system(system.key)
            family = next(f for f in system.families if f.name == family.name)
            new_system, ids = self._check_family(system, family, pattern, [sheets[k] for k in keys])
            job = job.with_system(new_system)
            entries += self._proofs(system.key, family.name, pattern, [sheets[k] for k in keys], ids)
        if entries:
            try:
                save_manifest(self.cache, entries)
            except Exception:
                pass
        return job

    # -- one sheet, both counts, every family on it at once

    def _count_sheet(self, sheet: _Sheet, here: list[str]) -> None:
        from estimator.writing.dossier import SHEET_DPI, sheet_pictures

        try:
            images, _flags = sheet_pictures(self.catalogue, self.cache, [sheet.key], "plan sheet, tags counted")
            sheet.picture = Path(images[0].path) if images else None
        except Exception:
            sheet.picture = None
        combined = "|".join(f"(?:{p})" for p in here)
        try:
            sheet.located = self._located(sheet, combined, SHEET_DPI / 72)
        except Exception:
            sheet.located = None
        if self.transport is not None and sheet.picture is not None:
            results = count_sheet(sheet.picture, here, transport=self.transport)    # one question for the sheet
            if all(r.value is not None for r in results.values()):
                sheet.seen = [(b.text, (b.x, b.y, b.width, b.height)) for r in results.values() for b in r.boxes]

    def _located(self, sheet: _Sheet, pattern: str, default_scale: float) -> list:
        import pymupdf
        from PIL import Image

        documents = {d.relative: Path(d.path) for d in self.catalogue.job.documents}
        document, number = sheet.key
        with pymupdf.open(str(documents[document])) as pdf:
            page = pdf[number - 1]
            scale = default_scale
            if sheet.picture is not None:
                with Image.open(sheet.picture) as picture:
                    scale = picture.size[0] / page.rect.width
            return located_boxes(page, pattern, scale)

    # -- one family: its counts over its sheets, merged into its Count

    def _check_family(self, system, family, pattern: str, sheets: list[_Sheet]):
        counted = []          # (value, quote, where)
        for quote, attr, place in ((LOCATED_QUOTE, "located", "place"), (SEEN_QUOTE, "seen", "picture_place")):
            read = [s for s in sheets if getattr(s, attr) is not None]
            if not read:
                continue
            tags = {canonical(t) for s in read for t, _ in getattr(s, attr) if fits(pattern, t)}
            complete = len(read) == len(sheets)
            if not complete and (family.count.value is None or len(tags) <= family.count.value):
                continue      # some sheets unread: only a count above the printed one says anything
            counted.append((len(tags), quote, "; ".join(getattr(s, place) for s in read)))
        count, ids, disagree = self._merge(family.count, counted)
        if count == family.count:
            return system, ids
        families = tuple(dataclasses.replace(f, count=count) if f is family else f for f in system.families)
        devices = system.devices
        if disagree:
            old = set(family.count.sources)
            devices = tuple(dataclasses.replace(d, flag="quantity")
                            if d.flag == "none" and old & set(d.quantity.sources) else d for d in devices)
        return dataclasses.replace(system, families=families, devices=devices), ids

    def _merge(self, count: Count, counted) -> tuple[Count, dict[str, str], bool]:
        value, sources, others = count.value, list(count.sources), list(count.others)
        ids: dict[str, str] = {}
        disagree = False
        for n, quote, where in counted:
            known = next((r for r in [*sources, *(o.ref for o in others)] if r.quote == quote and r.where == where),
                         None)
            if known is not None:
                ids[quote] = known.source_id
                continue
            ref = Ref(f"C{self.next_id}", quote, where)
            self.next_id += 1
            ids[quote] = ref.source_id
            if value is None:
                value, sources = n, [ref]
            elif n == value:
                sources.append(ref)
            elif n < value:
                others.append(OtherCount(n, ref))
                disagree = True
            else:
                others += [OtherCount(value, s) for s in sources] or [OtherCount(value, Ref("", NO_SOURCE_QUOTE, ""))]
                value, sources = n, [ref]
                disagree = True
        return Count(value, tuple(sources), tuple(others)), ids, disagree

    # -- the proof images

    def _proofs(self, system_key: str, family: str, pattern: str, sheets: list[_Sheet], ids: dict) -> list[dict]:
        entries = []
        folder = self.cache.resolve() / PROOFS_FOLDER
        for sheet in sheets:
            located = _distinct([(t, b) for t, b in sheet.located or () if fits(pattern, t)])
            seen = _distinct([(t, b) for t, b in sheet.seen or () if fits(pattern, t)])
            proof = None
            if sheet.picture is not None:
                try:
                    proof = draw_proof(sheet.picture, [(b.x, b.y, b.width, b.height) for b in located],
                                       [(b.x, b.y, b.width, b.height) for b in seen], folder,
                                       f"{system_key}-{family}-{sheet.place}")
                except Exception:
                    proof = None
            entries.append({
                "system_key": system_key, "family": family, "sheet": sheet.place,
                "picture": str(sheet.picture) if sheet.picture else None,
                "proof": str(proof) if proof else None,
                "located_text": len(located) if sheet.located is not None else None,
                "vision": len(seen) if sheet.seen is not None else None,
                "located_tags": [b.text for b in located], "vision_tags": [b.text for b in seen],
                "located_boxes": [dataclasses.asdict(b) for b in located],
                "vision_boxes": [dataclasses.asdict(b) for b in seen],
                "source_ids": [ids[q] for q in (LOCATED_QUOTE, SEEN_QUOTE) if q in ids],
            })
        return entries


def _refs(job):
    """Every Ref in the job."""
    for system in job.systems:
        for family in system.families:
            yield from family.count.sources
            yield from (o.ref for o in family.count.others)
        yield from system.sequence_refs
        for device in system.devices:
            yield from device.refs
            yield from device.quantity.sources
            yield from (o.ref for o in device.quantity.others)
