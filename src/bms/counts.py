"""The vision count cross-check (workstream 6, design §4.6)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from estimator.catalogue.job import Catalogue

    from bms.model import Job


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


def count_tags(image_path: Path, tag_pattern: str) -> CountResult:
    """Count the tags matching `tag_pattern` (a Python regular expression over the tag as printed, e.g.
    "EF-[0-9]+") on one whole-sheet picture (a PNG, as `estimator.writing.dossier.sheet_pictures` draws them), by
    vision on tiles, each tag once even where tiles overlap.

    Contract: never raises for an unreadable picture (returns `CountResult(None, ())`). The caller (the run, after
    planning) compares `value` with the family's Count: a different value is added to `Count.others` with a Ref
    (`source_id` the picture's id, `quote` "counted on the sheet picture", `where` the sheet), the printed value
    becomes the higher, and the devices of that family get flag "quantity".
    """
    raise NotImplementedError("workstream 6: the vision count")


def cross_check(job: "Job", catalogue: "Catalogue", cache: Path) -> "Job":
    """The job with every family's text count checked against the vision count (design §4.6), run after planning.

    Contract: for each family with tags, the plan sheets showing its tags are pictured
    (`estimator.writing.dossier.sheet_pictures(catalogue, cache, keys, what)`) and counted with `count_tags`;
    a vision count different from `Count.value` (or from every other count) is added to `Count.others` with its
    Ref, `Count.value` becomes the highest, and the family's devices (none yet at this step) — and so, through
    the planner's Count, the block header — carry the difference. Families whose sheets cannot be pictured or
    counted are left as they are. Pure apart from the picture cache under `cache`. Never lowers a count."""
    raise NotImplementedError("workstream 6: the count cross-check")
