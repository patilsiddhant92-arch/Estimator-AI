"""The vision count (workstream 6): a whole-sheet picture cut into overlapping tiles, each tile asked of the AI
through a `bms.ai` Transport, the answers put back into the whole picture's pixels."""
from __future__ import annotations

from pathlib import Path

from PIL import Image

from bms.model import schema_errors

TILE = 1568           # the longest tile edge, in pixels (the size a vision model reads without shrinking)
OVERLAP = 192         # tiles overlap by this, so a tag cut by one tile's edge is whole in the next
TILES_FOLDER = "count-tiles"
COUNT_KIND = "count_tags"   # the request kind of a tile question (chat hand-off and answer cache)

INSTRUCTIONS = """You count equipment tags on a mechanical or controls drawing sheet, one tile of the sheet at a time.

A tag is the short code that names one piece of equipment where it is drawn on the plan: EF-1, RTU-2, VAV-3-01, often
inside a bubble, hexagon or box, or at the end of a leader line. You are given a Python regular expression; report
only tags whose text fully matches it.

Report every tag you can read whole in this tile, each time it appears, with the tag's text exactly as printed and the
box around that text in this tile's pixels: x and y of the box's top-left corner measured from the tile's top-left
corner, then its width and height. Leave out a tag cut by the tile's edge (the tiles overlap, so it is whole in the
next one). Leave out sheet numbers, detail and section marks, room numbers, and words in the notes, legends and title
block. Do not guess: a tag you cannot read with confidence is left out. An empty list is a correct answer when the
tile shows none."""

STEP = "Answer with JSON only, in the schema given: {\"tags\": [{\"text\", \"x\", \"y\", \"width\", \"height\"}]}."

SCHEMA = {
    "type": "object",
    "properties": {
        "tags": {
            "type": "array",
            "description": "Every matching tag read whole in this tile, each time it appears.",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "The tag exactly as printed."},
                    "x": {"type": "integer", "description": "Left edge of the tag's box, pixels from the tile's left."},
                    "y": {"type": "integer", "description": "Top edge of the tag's box, pixels from the tile's top."},
                    "width": {"type": "integer", "description": "Width of the box in pixels."},
                    "height": {"type": "integer", "description": "Height of the box in pixels."},
                },
                "required": ["text", "x", "y", "width", "height"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["tags"],
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


def prompt(picture: Path, size: tuple[int, int], rect: tuple[int, int, int, int], pattern: str) -> str:
    x, y, w, h = rect
    return (f"Sheet picture {picture.name} ({size[0]} x {size[1]} pixels). This tile is the part at x {x}, y {y}, "
            f"{w} x {h} pixels.\n"
            f"The tags to report fully match this Python regular expression: {pattern}\n"
            f"List every one you can read whole in this tile, with its box in this tile's pixels.")


def read_answer(answer: dict, rect: tuple[int, int, int, int]) -> list[tuple[str, tuple[int, int, int, int]]] | None:
    """The answer's tags as (text, box in the whole picture's pixels); None when the answer breaks the schema. A box
    that does not lie in the tile is dropped (the AI misplaced it)."""
    if schema_errors(answer, SCHEMA):
        return None
    x0, y0, w, h = rect
    found = []
    for tag in answer["tags"]:
        x, y, tw, th = tag["x"], tag["y"], tag["width"], tag["height"]
        if tw <= 0 or th <= 0 or x < 0 or y < 0 or x >= w or y >= h:
            continue
        tw, th = min(tw, w - x), min(th, h - y)
        found.append((tag["text"], (x0 + x, y0 + y, tw, th)))
    return found


def ask_tiles(transport, picture: Path, pattern: str, name: str = ""
              ) -> list[tuple[str, tuple[int, int, int, int]]] | None:
    """Every tile of the picture asked (all of them, even after one has no answer, so a chat hand-off writes every
    request in one run); the found tags in the whole picture's pixels, or None when any tile has no usable answer."""
    from bms.ai import NoAnswer

    size, tiles = cut_tiles(picture)
    found: list[tuple[str, tuple[int, int, int, int]]] = []
    complete = True
    for n, (rect, path) in enumerate(tiles, start=1):
        try:
            answer = transport.ask(COUNT_KIND, name or f"Count tags {picture.stem} tile {n}", INSTRUCTIONS, STEP,
                                   prompt(picture, size, rect, pattern), SCHEMA,
                                   extra={"step": "count", "picture": str(picture), "tile": list(rect)},
                                   images=(path,))
        except NoAnswer:
            complete = False
            continue
        except Exception as error:          # a transport failure is no count, never a crash
            if hasattr(transport, "last_error"):
                try:
                    transport.last_error = f"{type(error).__name__}: {error}"
                except Exception:
                    pass
            complete = False
            continue
        tags = read_answer(answer, rect) if isinstance(answer, dict) else None
        if tags is None:
            complete = False
            continue
        found += tags
    return found if complete else None


