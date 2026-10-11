"""The vision count cross-check (workstream 6, design §4.6).

Two counts of each tagged family on the plan sheets that show its tags, independent of the planner's count:
- located on the sheet text: the family's tags in the PDF page's text layer, read by the planner's one label reader
  (`counts_text.located_labels`: `estimator.catalogue.tags.line_labels` and `plan_labels`, so "VAV-1 THRU VAV-5" is
  five, "CUH-A (TYP. OF 4)" four, "TO EF-7" none), each with its box;
- counted on the sheet picture: the whole-sheet picture (as `estimator.writing.dossier.sheet_pictures` draws it)
  cut into overlapping tiles, and the sheet asked of the AI through a `bms.ai` Transport as one question (request
  kind "count_tags") carrying every tile as its own picture and every family's tag pattern on that sheet together.

A family's located count on the plans is counted on each sheet and added up over its plan sheets by the
inventory's one counting rule (`estimator.reading.inventory.plan_groups`, `plan_count`, `counted_per_place`): sheets
that show one plan are one group, where a unit's tag counts once and a type's tag (EBB-A, CUH-A, AC-3.0) the most
places of one sheet; every other sheet adds up (a type's tag on two floor plans is 2). The picture count is the
number of different tags seen. `cross_check` adds every count that differs from the printed one to
`Count.others` with its Ref, keeps the highest as `Count.value`, never lowers a count, flags the devices counted from
a family whose counts disagree, and writes the proof images (a crop of the sheet with the counted tags boxed) and
their manifest under `<cache>/count-proofs/` for the review page (`load_proofs`, `proofs_for`). Without a transport
it does the located-text count only.
"""
from __future__ import annotations

import dataclasses
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from bms.citations import plain_id
from bms.counts_proof import PROOFS_FOLDER, draw_proof, load_manifest, save_manifest
from bms.counts_text import (canonical, family_pattern, family_tags, fits, located_boxes, natural, prefix_owners,
                              searcher)
from bms.counts_vision import COUNT_KIND, TILE, ask_sheet
from bms.model import Count, Device, Family, OtherCount, Ref, System

if TYPE_CHECKING:
    from estimator.catalogue.job import Catalogue

    from bms.model import Job

COUNT_TAGS = COUNT_KIND             # the request kind of a sheet's count question
LOCATED_QUOTE = "located on the sheet text"
SEEN_QUOTE = "counted on the sheet picture"
NO_SOURCE_QUOTE = "the count before the plan check, given without a source"
PLAN_TYPE = "Plans"
PICTURE_PLAN = 0.5    # pictures covering this much of a plan sheet make it a picture (a scan, a raster plan)
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
    untagged: int | None = None   # symbols of the equipment drawn with no tag, as the answer gives them (its own
                                  # count, never in `value`); None when the answer gives none


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


def count_sheet(image_path: Path, tag_patterns, *, transport=None,
                crops: list[tuple[tuple[int, int, int, int], Path]] | None = None) -> dict[str, CountResult]:
    """Count every pattern of `tag_patterns` on one whole-sheet picture with ONE vision question (every tile as its
    own picture, every pattern together): {pattern: CountResult}, each as `count_tags` gives it. Every result is
    `CountResult(None, ())` when the sheet could not be counted (unreadable picture, a bad pattern, no transport,
    no usable answer yet). A pattern the answer leaves out is absent from the result (no count, not a count of 0).
    `untagged` is the answer's own count of the equipment's symbols drawn with no tag, kept apart from `value`.
    Never raises."""
    patterns = list(dict.fromkeys(tag_patterns))
    unknown = {p: CountResult(None, ()) for p in patterns}
    try:
        for pattern in patterns:
            re.compile(pattern)
        if transport is None or not patterns:
            return unknown
        asked = ask_sheet(transport, Path(image_path), patterns, crops=crops)
        if asked is None:
            return unknown
        found, listed, untagged = asked
        results = {}
        for pattern in patterns:
            if pattern not in listed:
                continue          # the answer leaves this pattern out: no vision count for it
            boxes = _distinct([(text, box) for text, box in found if fits(pattern, text)])
            results[pattern] = CountResult(len(boxes), tuple(boxes), untagged.get(pattern))
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
    count when it found a tag; a plan count of 0 leaves it unknown), the earlier count moving to `others` with its sources; and the system's devices whose quantity was
    counted from the family's sources get flag "quantity" when the counts disagree. Proof images and their manifest
    go under `<cache>/count-proofs/`. A family whose whole-sheet pictures show symbols drawn with no tag
    (`CountResult.untagged` above 0) gets one plain-words question in `Job.questions` naming every such sheet and its
    number; they are never added to the count. A family's `Count.added_up` (the planner's sum of the sheets of one
    floor and area, ruling L1) is kept while it is above the new printed count and dropped when the plans reach it.
    Families whose sheets cannot be pictured or counted are left as they are.
    Pure apart from the picture cache under `cache`. Never lowers a count, never raises; running it twice changes
    nothing more."""
    try:
        return _Check(job, catalogue, Path(cache), transport, micro_crops=True).run()
    except Exception:
        return job


def family_sources(family: Family) -> set[str]:
    """The source ids (plain, "[C3]" is "C3") of a family's count: the sources of the printed count and of every
    disagreeing count. Empty ids are left out."""
    sources = {plain_id(r.source_id) for r in family.count.sources}
    sources.update(plain_id(other.ref.source_id) for other in family.count.others)
    sources.discard("")
    return sources


def counted_from(device: Device, family: Family) -> bool:
    """Whether a device's quantity was counted from a family: it cites one of the family's count sources (or one
    of its disagreeing counts) by source id. Tag text in a quote does not tie a device to a family ("MD-1
    interlocked with EF-1" is not an Exhaust Fan count). The one rule the run's flagging and the review page's
    family Accept both use. Pure."""
    return bool(family_sources(family) & {plain_id(r.source_id) for r in device.quantity.sources})


def disputed_families(system: System) -> list[Family]:
    """The system's families whose counts disagree (`others`) and that have a source a line can be counted from:
    the families `flag_written_devices` flags by, and the ones a family Accept must all settle before a line counted
    from them is cleared. Pure."""
    return [family for family in system.families if family.count.others and family_sources(family)]


def flag_written_devices(system: System) -> System:
    """Flag devices the writer just created when a family's counts disagree.

    `cross_check` flags devices that already exist and were counted from the family's sources. A planned system
    has no devices yet, so the run calls this after `write_system`. A family with no `others` changes nothing.
    A device counted from such a family (`counted_from`: its quantity cites one of that family's sources, or one
    of the disagreeing counts) gets flag "quantity" unless it is already flagged. Sources match by source id
    ("[C3]" is "C3"), not by the whole citation: a trimmed quote still cites the count. Pure."""
    disputed = disputed_families(system)
    if not disputed:
        return system
    devices = tuple(
        dataclasses.replace(device, flag="quantity")
        if device.flag == "none" and any(counted_from(device, family) for family in disputed) else device
        for device in system.devices)
    return system if devices == system.devices else dataclasses.replace(system, devices=devices)


def load_proofs(cache: Path) -> list[dict]:
    """Every proof `cross_check` wrote under `cache`: dicts with `system_key`, `family`, `sheet` (the place),
    `picture` (the whole-sheet PNG), `proof` (the cropped PNG with the boxes, or None), `located_text` and
    `vision` (that sheet's counts, None when not counted), `located_tags` / `vision_tags`, `located_boxes` /
    `vision_boxes` ({x, y, width, height, text} in the picture's pixels), `vision_untagged` (the symbols the
    picture's answer saw drawn with no tag: its own count, never in `vision`; None when not given) and
    `source_ids` (the Refs' ids)."""
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
    labels: Counter | None = None    # tag -> the places it is labelled on the sheet text (`located_labels`)
    evidence: Counter | None = None  # the labels alone, no backstop: which sheets show one plan (`plan_groups`)
    sheet: object = None             # the catalogue's Sheet
    seen: list | None = None         # (tag, box) on the picture; None when not counted
    counted: frozenset = frozenset() # the patterns the picture's answer counted (others were left out of it)
    untagged: dict = dataclasses.field(default_factory=dict)  # pattern -> symbols the picture shows with no tag


class _Check:
    def __init__(self, job, catalogue, cache: Path, transport, micro_crops: bool = True) -> None:
        self.job, self.catalogue, self.cache, self.transport = job, catalogue, cache, transport
        self.micro_crops = micro_crops
        self.pictured: dict[tuple[str, int], bool] = {}     # sheet key: mostly picture (`_mostly_picture`)
        self.listed: dict[str, set[str]] = {}               # pattern -> the families' own (expanded) tags
        self.groups: dict = {}                              # sheet key -> its plan group (`plan_groups`)
        self.patterns: dict[tuple[str, str], str] = {}     # (system key, family name) -> the family's pattern
        used = [int(m.group(1)) for ref in _refs(job) if (m := re.fullmatch(r"C(\d+)", ref.source_id))]
        self.next_id = max(used, default=0) + 1

    def run(self):
        from estimator.catalogue.job import CONTROLS_DISCIPLINES
        from estimator.catalogue.sheet_types import is_demolition

        families = [(s, f) for s in self.job.systems for f in s.families if any(t.strip() for t in f.tags)]
        if not families:
            return self.job
        owners = prefix_owners(f.tags for s in self.job.systems for f in s.families)
        patterns = self.patterns
        for system, family in families:
            pattern = family_pattern(family.tags, owners)
            if pattern is not None:
                patterns[(system.key, family.name)] = pattern
                self.listed.setdefault(pattern, set()).update(family_tags(family.tags))
        records = {(p.document, p.page): p for p in getattr(self.catalogue, "pages", ()) or ()}
        plans = [s for s in getattr(self.catalogue, "sheets", ()) or ()
                 if PLAN_TYPE in (s.types or ()) and s.discipline in CONTROLS_DISCIPLINES
                 and (s.document, s.page) in records
                 and not is_demolition(s)]   # ruling 1 (T-005a): a demolition plan's units are not counted
        # with a transport, a plan whose text names no family's tag is still asked when its page is mostly
        # picture (a raster plan under a vector title block): its tags are only in the picture
        finds = [searcher(pattern) for pattern in patterns.values()]
        pictured = set()
        if self.transport is not None:
            pictured = {(s.document, s.page) for s in plans
                        if not any(f.search(records[(s.document, s.page)].text or "") for f in finds)
                        and self._mostly_picture((s.document, s.page))}
        on_sheet: dict[tuple[str, str], list[tuple[str, int]]] = {}
        sheets: dict[tuple[str, int], _Sheet] = {}
        for (key, name), pattern in patterns.items():
            find = searcher(pattern)
            for sheet in plans:
                text = records[(sheet.document, sheet.page)].text or ""
                if (find.search(text) or (self.transport is not None and len(text.strip()) < 50)
                        or (sheet.document, sheet.page) in pictured):
                    on_sheet.setdefault((key, name), []).append((sheet.document, sheet.page))
                    if (sheet.document, sheet.page) not in sheets:
                        doc = _name(sheet.document)
                        sheets[(sheet.document, sheet.page)] = _Sheet(
                            (sheet.document, sheet.page),
                            f"{sheet.number}, {doc} page {sheet.page}" if sheet.number else f"{doc} page {sheet.page}",
                            (f"{sheet.number} whole sheet, {doc} page {sheet.page} (picture)" if sheet.number
                             else f"{doc} page {sheet.page} (picture)"), sheet=sheet)
        if not sheets:
            self._save_proofs([])
            return self.job
        for key, sheet in sheets.items():
            here = [patterns[f] for f, keys in on_sheet.items() if key in keys]
            self._count_sheet(sheet, here)
        self.groups = self._plan_groups(list(sheets.values()), plans)

        job, entries, asked = self.job, [], []
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
            merged = next(f for f in new_system.families if f.name == family.name)
            asked.append(_untagged_question(merged, pattern, [sheets[k] for k in keys]))
        self._save_proofs(entries)
        asked = [q for q in asked if q]
        if asked:
            # symbols drawn with no tag may be more units than counted: the estimator is asked, the count is not
            # changed (an undercount the estimator cannot see is the worst failure)
            job = dataclasses.replace(job, questions=tuple(dict.fromkeys([*job.questions, *asked])))
        return job

    def _save_proofs(self, entries: list[dict]) -> None:
        """The manifest with every entry of the families checked on this run replaced by this run's (a sheet no
        longer counted for a family leaves no proof behind beside a new count that may reuse its id)."""
        try:
            save_manifest(self.cache, entries, families=set(self.patterns))
        except Exception:
            pass

    # -- one sheet, both counts, every family on it at once

    def _count_sheet(self, sheet: _Sheet, here: list[str]) -> None:
        from estimator.writing.dossier import SHEET_DPI, sheet_pictures
        from bms.counts_text import classify_located_boxes, has_text_layer
        from bms.counts_vision import cut_micro_crops

        try:
            images, _flags = sheet_pictures(self.catalogue, self.cache, [sheet.key], "plan sheet, tags counted")
            sheet.picture = Path(images[0].path) if images else None
        except Exception:
            sheet.picture = None
        # the longest pattern first: where two families' tags start alike (VAV-1, VAV-1 01) the longer reading wins
        combined = "|".join(f"(?:{p})" for p in sorted(here, key=len, reverse=True))

        has_text = True
        confident, ambiguous = [], []
        listed = {tag for p in here for tag in self.listed.get(p, ())}
        try:
            confident, ambiguous, labels, evidence, has_text = self._classify(sheet, combined, SHEET_DPI / 72,
                                                                              listed)
            # only the tags the label reader counts are placed: "TO EF-7" is a note, not a box of the count
            confident = [(t, b) for t, b in confident if labels.get(canonical(t))]
            ambiguous = [(t, b, why) for t, b, why in ambiguous if labels.get(canonical(t))]
            sheet.located = ([(t, b) for t, b in confident] + [(t, b) for t, b, _ in ambiguous]) if has_text else None
            sheet.labels, sheet.evidence = (labels, evidence) if has_text else (None, None)
        except Exception:
            sheet.located, sheet.labels, sheet.evidence = None, None, None
            confident, ambiguous, has_text = [], [], False

        if (has_text and not confident and not ambiguous and self.transport is not None
                and self._mostly_picture(sheet.key)):
            # a page mostly picture whose text layer shows no tag: the text is a title block, not a count
            sheet.located, sheet.labels, sheet.evidence, has_text = None, None, None, False

        if self.transport is not None and sheet.picture is not None:
            results = {}
            if not (self.micro_crops and has_text):
                results = count_sheet(sheet.picture, here, transport=self.transport)
            else:
                if self._short_of_schedule(here, sheet) or self._schedule_disagrees(here, sheet):
                    # the text is short of the schedule or disagrees with it: the whole sheet is asked, whatever
                    # is ambiguous, so the picture count is independent of the text (and is never told the
                    # schedule's count)
                    results = count_sheet(sheet.picture, here, transport=self.transport)
                elif ambiguous:
                    self._confirm(sheet, here, confident, ambiguous, cut_micro_crops)

            if results and all(r.value is not None for r in results.values()):
                sheet.counted = frozenset(results)
                sheet.seen = [(b.text, (b.x, b.y, b.width, b.height)) for r in results.values() for b in r.boxes]
                sheet.untagged = {p: r.untagged for p, r in results.items() if r.untagged is not None}

    def _confirm(self, sheet: _Sheet, here: list[str], confident, ambiguous, cut_micro_crops) -> None:
        """Ask micro-crops around the ambiguous text boxes, and keep in the located count only the ambiguous tags
        the crops read (a pattern the answer leaves out, or no usable answer, keeps them all). The crops' answer is
        a check of the sheet text, never a count on the sheet picture: `sheet.seen` is left as it is."""
        try:
            crops = cut_micro_crops(sheet.picture, [b for _, b, _ in ambiguous])
            results = count_sheet(sheet.picture, here, transport=self.transport, crops=crops)
        except Exception:
            return
        if not results or any(r.value is None for r in results.values()):
            return
        kept = []
        for tag, box, _why in ambiguous:
            asked = [p for p in here if fits(p, tag) and p in results]
            read = {canonical(b.text) for p in asked for b in results[p].boxes}
            if not asked or canonical(tag) in read:
                kept.append((tag, box))
        sheet.located = [(t, b) for t, b in confident] + kept
        # a tag whose every box the crops did not read leaves the located count
        still = {canonical(t) for t, _ in sheet.located}
        for tag, _box, _why in ambiguous:
            if canonical(tag) not in still and sheet.labels is not None:
                sheet.labels.pop(canonical(tag), None)

    def _mostly_picture(self, key: tuple[str, int]) -> bool:
        """Whether pictures cover at least PICTURE_PLAN of the page (`dossier._picture_boxes`, overlapping ones
        merged, logos and stamps left out). False when the page cannot be read."""
        import pymupdf
        from estimator.writing.dossier import _picture_boxes

        cache = self.pictured
        if key not in cache:
            try:
                documents = {d.relative: Path(d.path) for d in self.catalogue.job.documents}
                with pymupdf.open(str(documents[key[0]])) as pdf:
                    page = pdf[key[1] - 1]
                    area = abs(page.rect)
                    cache[key] = area > 0 and sum(abs(b) for b in _picture_boxes(page)) >= PICTURE_PLAN * area
            except Exception:
                cache[key] = False
        return cache[key]

    def _classify(self, sheet: _Sheet, pattern: str, default_scale: float, listed=()):
        import pymupdf
        from PIL import Image
        from bms.counts_text import classify_located_boxes, has_text_layer, located_tallies

        documents = {d.relative: Path(d.path) for d in self.catalogue.job.documents}
        document, number = sheet.key
        with pymupdf.open(str(documents[document])) as pdf:
            page = pdf[number - 1]
            scale = default_scale
            if sheet.picture is not None:
                with Image.open(sheet.picture) as picture:
                    scale = picture.size[0] / page.rect.width
            if not has_text_layer(page):
                return [], [], Counter(), Counter(), False
            confident, ambiguous = classify_located_boxes(page, pattern, scale)
            return (confident, ambiguous, *located_tallies(page, pattern, listed), True)

    def _plan_groups(self, sheets: list[_Sheet], plans=()) -> dict:
        """The inventory's plan groups (`plan_groups`) of EVERY plan sheet of the job, the labels alone as evidence of
        the sheets this check read (`sheets`); a plan sheet that shows none of the families' tags has no evidence. A
        sheet that shows no tag is still a sheet of its floor: two sheets of one trade and one title make that floor
        too uncertain to group (ruling L1, `inventory._same_floor_and_area`), so a check that left the twin out would
        group sheets that the dossier, which sees it, does not, and its located count would fall below the dossier's.
        Empty when the groups cannot be made (every sheet is then its own group)."""
        from estimator.reading.inventory import plan_groups

        try:
            evidence = {s.key: dict(s.evidence or {}) for s in sheets}
            every = {(p.document, p.page): p for p in plans}
            every.update({s.key: s.sheet for s in sheets if s.sheet is not None})
            return plan_groups([(sheet, evidence.get(key, {})) for key, sheet in every.items()])
        except Exception:
            return {}

    def _counted_here(self, here: list[str]):
        """(the family's count, its pattern) for every family with a known count whose pattern is asked on this
        sheet: matched by the family's own pattern (`family_pattern`, so a list, a range or a bare prefix is
        matched as the check reads it), never the raw tag text."""
        for system in self.job.systems:
            for family in system.families:
                pattern = self.patterns.get((system.key, family.name))
                if family.count.value is not None and pattern in here:
                    yield family.count.value, pattern

    def _short_of_schedule(self, here: list[str], sheet: _Sheet) -> bool:
        """Whether the sheet's text shows fewer of a family's tags than its count: the whole sheet is then asked.
        Only the choice of question: the count itself is never put to the picture."""
        return any(value > _located_count([sheet], p) for value, p in self._counted_here(here))

    def _schedule_disagrees(self, here: list[str], sheet: _Sheet) -> bool:
        return any((n := _located_count([sheet], p)) > 0 and value != n for value, p in self._counted_here(here))

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
            read = [s for s in sheets if getattr(s, attr) is not None and (attr == "located" or pattern in s.counted)]
            if not read:
                continue
            if attr == "located":
                n = _located_count(read, pattern, self.groups)
            else:
                n = len({canonical(t) for s in read for t, _ in s.seen if fits(pattern, t)})
            complete = len(read) == len(sheets)
            if not complete and (family.count.value is None or n <= family.count.value):
                continue      # some sheets unread: only a count above the printed one says anything
            counted.append((n, quote, "; ".join(getattr(s, place) for s in read)))
        count, ids, disagree = self._merge(family.count, counted)
        if count == family.count:
            return system, ids
        families = tuple(dataclasses.replace(f, count=count) if f is family else f for f in system.families)
        devices = system.devices
        if disagree:
            # the tie `flag_written_devices` uses (`counted_from`, by source id), on the family as merged
            merged = dataclasses.replace(family, count=count)
            devices = tuple(dataclasses.replace(d, flag="quantity")
                            if d.flag == "none" and counted_from(d, merged) else d for d in devices)
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
            if value is None and n == 0:
                continue      # no tag found is no count: an unknown count stays unknown, never a known 0
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
        merged = Count(value, tuple(sources), tuple(others))
        if count.added_up is not None and (merged.highest() or 0) < count.added_up.value:
            merged = dataclasses.replace(merged, added_up=count.added_up)    # ruling L1's sum, while it is above
        return merged, ids, disagree

    # -- the proof images

    def _proofs(self, system_key: str, family: str, pattern: str, sheets: list[_Sheet], ids: dict) -> list[dict]:
        entries = []
        folder = self.cache.resolve() / PROOFS_FOLDER
        for sheet in sheets:
            located = _distinct([(t, b) for t, b in sheet.located or () if fits(pattern, t)])
            counted = sheet.seen is not None and pattern in sheet.counted
            seen = _distinct([(t, b) for t, b in sheet.seen or () if fits(pattern, t)]) if counted else []
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
                "located_text": _located_count([sheet], pattern) if sheet.located is not None else None,
                "vision": len(seen) if counted else None,
                "located_tags": [b.text for b in located], "vision_tags": [b.text for b in seen],
                "located_boxes": [dataclasses.asdict(b) for b in located],
                "vision_boxes": [dataclasses.asdict(b) for b in seen],
                "vision_untagged": sheet.untagged.get(pattern) if counted else None,
                "source_ids": [ids[q] for q in (LOCATED_QUOTE, SEEN_QUOTE) if q in ids],
            })
        return entries


def _located_count(sheets, pattern: str, groups: dict | None = None) -> int:
    """The located count of a pattern's tags over these sheets (`_Sheet.labels`) by the inventory's one counting rule
    (`estimator.reading.inventory.plan_count`, `counted_per_place`; `groups` from `plan_groups`, every sheet its own
    group when not given): in each plan group a unit's tag once, a tag counted at every place (a type's tag:
    "CUH-A (TYP. OF 4)" is 4) the most of one sheet; the groups added up (EBB-A on two floor plans is 2). The
    located count does not multiply by a typical sheet's floors: a typical plan can read lower than the planner's
    count, and then it is a cross-check other, never the printed count."""
    from estimator.reading.inventory import counted_per_place, plan_buildings, plan_count

    # ruling 2 of 2026-10-11 (T-005a): a unit's tag once in the job, once in each building of a job of several
    buildings = plan_buildings(s.sheet for s in sheets if s.sheet is not None)
    found: dict[str, list] = {}
    for sheet in sheets:
        for tag, n in (sheet.labels or {}).items():
            if n > 0 and fits(pattern, tag):
                found.setdefault(canonical(tag), []).append((sheet.key, n, frozenset()))
    total = 0
    for tag, mine in found.items():
        per_place = counted_per_place(tag, sum(n for _k, n, _f in mine), max(n for _k, n, _f in mine))
        total += plan_count(mine, groups or {}, per_place, buildings)
    return total


def _untagged_question(family: Family, pattern: str, sheets: list[_Sheet]) -> str | None:
    """One plain-words question for a family whose sheet pictures show symbols with no tag (the whole-sheet answer's
    `untagged_symbols`, never a micro-crop's): every such sheet and its number, the count left as it is. None when no
    sheet shows any."""
    seen = [(s.sheet.number if s.sheet is not None and s.sheet.number else s.place, n) for s in sheets
            if pattern in s.counted and (n := s.untagged.get(pattern) or 0) > 0]
    if not seen:
        return None
    (first, n), rest = seen[0], seen[1:]
    more = f" (and {', '.join(f'{m} on {where}' for where, m in rest)})" if rest else ""
    value = family.count.highest()
    counted = f"the count of {value}" if value is not None else "the count"
    return (f"The sheet picture of {first} shows {n} {family.name} {'symbol' if n == 1 else 'symbols'} with no "
            f"tag{more}; {counted} does not include them. Confirm whether they are more units.")


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
