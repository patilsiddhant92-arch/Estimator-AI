"""The vision count (workstream 6): a whole-sheet picture cut into overlapping tiles, the sheet asked of the AI
through a `bms.ai` Transport as ONE question carrying every tile as its own picture (in order, each tile's place on
the sheet stated in the prompt) and every tag pattern counted on that sheet, the answers put back into the whole
picture's pixels."""
from __future__ import annotations

import re
from pathlib import Path

from PIL import Image

from bms.model import schema_errors

TILE = 1568           # the longest tile edge, in pixels (the size a vision model reads without shrinking)
OVERLAP = 192         # tiles overlap by this, so a tag cut by one tile's edge is whole in the next
TILES_FOLDER = "count-tiles"
COUNT_KIND = "count_tags"   # the request kind of a sheet's count question (chat hand-off and answer cache)

INSTRUCTIONS = """You count equipment tags on a mechanical or controls drawing sheet. The sheet comes as overlapping
tiles, each its own picture, in the order listed in the prompt with each tile's place on the whole sheet.

A tag is the short code that names one piece of equipment where it is drawn on the plan: EF-1, RTU-2, VAV-3-01, often
inside a bubble, hexagon or box, or at the end of a leader line. You are given one or more Python regular expressions,
one per family of equipment; for each of them, report every tag on the sheet whose text fully matches it.

For each tag: its text exactly as printed, how many times it appears on the sheet, and a box for every place it
appears: the number of the tile it is read in (1 for the first picture) and the box around the tag's text in that
tile's pixels: x and y of the box's top-left corner measured from that tile's top-left corner, then its width and
height. Read a tag in a tile where it is whole (the tiles overlap, so a tag cut by one tile's edge is whole in a
neighbour); a tag whole in two overlapping tiles is one place, boxed once. Leave out sheet numbers, detail and section
marks, room numbers, and words in the notes, legends and title block. Do not guess: a tag you cannot read with
confidence is left out. An empty list of tags is a correct answer for a pattern the sheet does not show."""

STEP = ("Answer with JSON only, in the schema given: {\"patterns\": [{\"pattern\", \"tags\": [{\"text\", "
        "\"count\", \"boxes\": [{\"tile\", \"x\", \"y\", \"width\", \"height\"}]}]}]}, one entry per pattern asked.")

_BOX = {
    "type": "object",
    "properties": {
        "tile": {"type": "integer", "description": "The tile the tag is read in: 1 for the first picture."},
        "x": {"type": "integer", "description": "Left edge of the tag's box, pixels from that tile's left."},
        "y": {"type": "integer", "description": "Top edge of the tag's box, pixels from that tile's top."},
        "width": {"type": "integer", "description": "Width of the box in pixels."},
        "height": {"type": "integer", "description": "Height of the box in pixels."},
    },
    "required": ["tile", "x", "y", "width", "height"],
    "additionalProperties": False,
}

SCHEMA = {
    "type": "object",
    "properties": {
        "patterns": {
            "type": "array",
            "description": "One entry per tag pattern asked, in the order asked.",
            "items": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "The pattern as given in the prompt."},
                    "tags": {
                        "type": "array",
                        "description": "Every different tag on the sheet that fully matches the pattern.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "text": {"type": "string", "description": "The tag exactly as printed."},
                                "count": {"type": "integer",
                                          "description": "How many places on the sheet show this tag."},
                                "boxes": {"type": "array", "description": "One box per place the tag is shown.",
                                          "items": _BOX},
                            },
                            "required": ["text", "count", "boxes"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["pattern", "tags"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["patterns"],
    "additionalProperties": False,
}


def tile_grid(width: int, height: int, tile: int = TILE, overlap: int = OVERLAP) -> list[tuple[int, int, int, int]]:
    """(x, y, width, height) of the tiles covering a picture, overlapping by `overlap`, none larger than `tile`."""
    def starts(size: int) -> list[int]:
        if size <= tile:
            return [0]
        step = tile - overlap
        points = list(range(0, size - tile, step))
        points.append(size - tile)
        return sorted(set(points))

    return [(x, y, min(tile, width - x), min(tile, height - y)) for y in starts(height) for x in starts(width)]


def cut_tiles(picture: Path) -> tuple[tuple[int, int], list[tuple[tuple[int, int, int, int], Path]]]:
    """The picture's size and its tiles, each saved once as a PNG beside the picture (reused when present)."""
    folder = picture.parent / TILES_FOLDER
    with Image.open(picture) as image:
        image.load()
        size = image.size
        tiles = []
        for rect in tile_grid(*size):
            x, y, w, h = rect
            path = folder / f"{picture.stem}-{x}-{y}-{w}-{h}.png"
            if not (path.exists() and path.stat().st_size > 0):
                folder.mkdir(parents=True, exist_ok=True)
                tmp = path.with_suffix(".tmp.png")
                image.crop((x, y, x + w, y + h)).save(tmp)
                tmp.replace(path)
            tiles.append((rect, path))
    return size, tiles


def prompt(picture: Path, size: tuple[int, int], rects: list[tuple[int, int, int, int]], patterns: list[str]) -> str:
    lines = [f"Sheet picture {picture.name} ({size[0]} x {size[1]} pixels), sent as {len(rects)} overlapping "
             f"tile(s), one picture each, in this order (each tile's place on the whole sheet):"]
    lines += [f"Tile {n}: x {x}, y {y}, {w} x {h} pixels." for n, (x, y, w, h) in enumerate(rects, start=1)]
    lines.append("Count the tags fully matching each of these Python regular expressions (one entry per pattern in "
                 "the answer, in this order):")
    lines += [f"Pattern {n}: {pattern}" for n, pattern in enumerate(patterns, start=1)]
    lines.append("For each tag give its text, how many places show it, and a box per place: the tile number and the "
                 "box in that tile's pixels.")
    return "\n".join(lines)


def read_answer(answer: dict, rects: list[tuple[int, int, int, int]]
                ) -> list[tuple[str, tuple[int, int, int, int]]] | None:
    """The answer's tags, every pattern's together, as (text, box in the whole picture's pixels), one per box; None
    when the answer breaks the schema. A box in no tile sent, or not lying in its tile, is dropped (the AI misplaced
    it)."""
    if schema_errors(answer, SCHEMA):
        return None
    found = []
    for entry in answer["patterns"]:
        for tag in entry["tags"]:
            if tag["count"] <= 0:
                continue
            for box in tag["boxes"]:
                n = box["tile"]
                if not 1 <= n <= len(rects):
                    continue
                x0, y0, w, h = rects[n - 1]
                x, y, tw, th = box["x"], box["y"], box["width"], box["height"]
                if tw <= 0 or th <= 0 or x < 0 or y < 0 or x >= w or y >= h:
                    continue
                tw, th = min(tw, w - x), min(th, h - y)
                found.append((tag["text"], (x0 + x, y0 + y, tw, th)))
    return found


def ask_sheet(transport, picture: Path, patterns: list[str], name: str = ""
              ) -> list[tuple[str, tuple[int, int, int, int]]] | None:
    """The sheet's one count question: every tile of the picture as its own image, every pattern asked together;
    the found tags (of every pattern) in the whole picture's pixels, or None when there is no usable answer (waiting
    for the chat, a transport failure, an answer that breaks the schema). Never raises for a bad pattern list
    (a pattern that is no regular expression gives None)."""
    from bms.ai import NoAnswer

    patterns = list(dict.fromkeys(patterns))
    if not patterns:
        return []
    for pattern in patterns:
        re.compile(pattern)
    size, tiles = cut_tiles(picture)
    rects = [rect for rect, _ in tiles]
    try:
        answer = transport.ask(COUNT_KIND, name or f"Count tags {picture.stem}", INSTRUCTIONS, STEP,
                               prompt(picture, size, rects, patterns), SCHEMA,
                               extra={"step": "count", "picture": str(picture), "tiles": [list(r) for r in rects],
                                      "patterns": patterns},
                               images=tuple(path for _, path in tiles))
    except NoAnswer:
        return None
    except Exception as error:          # a transport failure is no count, never a crash
        if hasattr(transport, "last_error"):
            try:
                transport.last_error = f"{type(error).__name__}: {error}"
            except Exception:
                pass
        return None
    return read_answer(answer, rects) if isinstance(answer, dict) else None
