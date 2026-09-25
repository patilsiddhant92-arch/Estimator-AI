"""Schedules pasted onto a sheet as pictures, read by eye (1.1).

Some schedule sheets are pictures: 26-0478's H601 is ten pasted images, and OCR's text of them loses
most of the units. When a Schedules sheet has pictures and no readable table, or its schedules look
thin (fewer units than the plans show of those families), each large picture is cut out of the sheet
as a PNG in the cache (`<cache>/schedule-images/<document hash>-p<page>-<n>.png`) and the AI judge is
asked to copy it, cell by cell (`Judge.read_schedule`, kind "read_schedule"). Its answer becomes the
same Schedule and ScheduleRow objects the table reader makes, marked `source="picture, read by eye"`.
With no judge, or while the chat has not answered yet, the count from the OCR text stays.

A picture is rendered at 200 dpi, lowered (never below 100 dpi) so its long edge fits the 2576 pixels
the AI reads an image at; one still too big at 100 dpi is also cut into overlapping tiles, sent together.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from estimator.reading.schedules import BY_EYE, Schedule, schedule_from_cells

MIN_REGION = 0.01      # share of the sheet a picture must cover to be read (logos and stamps are smaller)
DPI, MIN_DPI = 200, 100
MAX_EDGE = 2576        # pixels: the long edge the AI reads an image at, whole
MAX_PIXELS = 3.75e6
OVERLAP = 0.05         # share of a tile repeated in the next one


@dataclass(frozen=True)
class Picture:
    path: Path                  # the whole picture, as a PNG
    tiles: tuple[Path, ...]     # the same picture in pieces, when it is too big to send whole; else ()
    box: tuple[float, float, float, float]   # where it sits on the sheet, as the sheet is viewed


def picture_regions(page) -> list[pymupdf.Rect]:
    """The sheet's large pictures, as the sheet is viewed (rotation applied), top to bottom, left to right. A
    picture inside another is dropped."""
    view = page.rect
    area = view.width * view.height
    if area <= 0:
        return []
    matrix = page.rotation_matrix
    boxes = []
    for info in page.get_image_info():
        box = (pymupdf.Rect(info["bbox"]) * matrix) & view
        if not box.is_empty and box.get_area() >= MIN_REGION * area:
            boxes.append(box)
    kept = [b for b in boxes if not any(o is not b and o.contains(b) and o != b for o in boxes)]
    unique: list[pymupdf.Rect] = []
    for box in kept:
        if not any(box == u for u in unique):
            unique.append(box)
    return sorted(unique, key=lambda b: (round(b.y0), round(b.x0)))


def _dpi(box: pymupdf.Rect) -> int:
    long_edge, short_edge = max(box.width, box.height) / 72, min(box.width, box.height) / 72
    fit = min(MAX_EDGE / long_edge, math.sqrt(MAX_PIXELS / max(long_edge * short_edge, 1e-6)))
    return max(MIN_DPI, min(DPI, int(fit)))


def _save(page, clip: pymupdf.Rect, dpi: int, path: Path) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    pixmap = page.get_pixmap(clip=clip, dpi=dpi)
    tmp = path.with_name(path.stem + ".tmp.png")
    pixmap.save(str(tmp))
    tmp.replace(path)


def _tiles(box: pymupdf.Rect, dpi: int) -> list[pymupdf.Rect]:
    """The box cut along its long edge into pieces that each fit MAX_EDGE at `dpi`, overlapping a little."""
    wide = box.width >= box.height
    length = box.width if wide else box.height
    step_points = MAX_EDGE * 72 / dpi
    if length * dpi / 72 <= MAX_EDGE:
        return []
    count = math.ceil((length - step_points * OVERLAP) / (step_points * (1 - OVERLAP)))
    size = length / (count - (count - 1) * OVERLAP)
    pieces = []
    for n in range(count):
        start = n * size * (1 - OVERLAP)
        if wide:
            pieces.append(pymupdf.Rect(box.x0 + start, box.y0, min(box.x1, box.x0 + start + size), box.y1))
        else:
            pieces.append(pymupdf.Rect(box.x0, box.y0 + start, box.x1, min(box.y1, box.y0 + start + size)))
    return pieces


def render_pictures(page, image_dir: Path, stem: str) -> list[Picture]:
    """Each large picture on the sheet as a PNG in `image_dir` (kept: a picture already there is not drawn
    again), named `<stem>-<n>.png`, with its tiles `<stem>-<n>-t<k>.png` when it is too big to send whole."""
    pictures = []
    for n, box in enumerate(picture_regions(page), start=1):
        dpi = _dpi(box)
        path = Path(image_dir) / f"{stem}-{n}.png"
        _save(page, box, dpi, path)
        tiles = []
        for k, piece in enumerate(_tiles(box, dpi), start=1):
            tile = path.with_name(f"{stem}-{n}-t{k}.png")
            _save(page, piece, dpi, tile)
            tiles.append(tile)
        pictures.append(Picture(path, tuple(tiles), tuple(box)))
    return pictures


def read_by_eye(judge, pictures: list[Picture], where: tuple[str, int, str | None], title_hint: str,
                vocab=None, equipment=None) -> tuple[list[Schedule], int]:
    """The schedules the judge copied from the pictures, and how many pictures are still waiting for an
    answer (in the chat, or with no key). A picture the answer finds no schedule in gives none."""
    document, page, sheet = where
    schedules: list[Schedule] = []
    waiting = 0
    for picture in pictures:
        answer = judge.read_schedule(picture.path, sheet, page, title_hint, picture.tiles)
        if answer is None:
            waiting += 1
            continue
        for raw in answer.get("schedules") or []:
            if not isinstance(raw, dict):
                continue
            schedule = schedule_from_cells(str(raw.get("title") or ""), raw.get("headers") or [],
                                           raw.get("rows") or [], raw.get("notes") or [], where, vocab, equipment,
                                           BY_EYE)
            if schedule.rows:
                schedules.append(schedule)
    return schedules, waiting
