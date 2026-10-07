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

You must open and examine EVERY TILE picture listed, one by one, at full size, and look through each of them for
every pattern. Do not count from a whole-sheet or reduced picture, and do not skip a tile because it looks empty or
because another picture seems to show the same area: small tags are only readable in the tiles. For each pattern,
"tiles_examined" lists the number of every tile you opened and examined for it; it must hold every tile number
from 1 to the last tile. An answer whose tiles_examined leaves out a tile is refused and asked again.

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

STEP = ("Answer with JSON only, in the schema given: {\"patterns\": [{\"pattern\", \"tiles_examined\", \"tags\": "
        "[{\"text\", \"count\", \"boxes\": [{\"tile\", \"x\", \"y\", \"width\", \"height\"}]}]}]}, one entry per "
        "pattern asked, each with every tile number in tiles_examined.")

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
                    "tiles_examined": {
                        "type": "array",
                        "description": "The number of every tile picture opened and examined for this pattern "
                                       "(1 for the first picture); it must cover every tile sent.",
                        "items": {"type": "integer"},
                    },
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
                    "untagged_symbols": {
                        "type": "integer",
                        "description": "Count of untagged symbols matching this equipment type.",
                    },
                },
                "required": ["pattern", "tiles_examined", "tags"],
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


def cut_micro_crops(picture: Path, boxes: Sequence[tuple[int, int, int, int]],
                    margin: int = 80, min_size: int = 200, max_size: int = 400
                    ) -> list[tuple[tuple[int, int, int, int], Path]]:
    """Cut small micro-crop images around each ambiguous box on the sheet picture.
    Returns list of ((crop_x, crop_y, crop_w, crop_h), path_to_saved_crop_png)."""
    folder = picture.parent / "count-crops"
    folder.mkdir(parents=True, exist_ok=True)
    crops = []
    with Image.open(picture) as image:
        image.load()
        img_w, img_h = image.size
        for idx, (bx, by, bw, bh) in enumerate(boxes, start=1):
            cx, cy = bx + bw // 2, by + bh // 2
            target_w = min(max_size, max(min_size, bw + 2 * margin))
            target_h = min(max_size, max(min_size, bh + 2 * margin))
            x0 = max(0, min(cx - target_w // 2, img_w - target_w))
            y0 = max(0, min(cy - target_h // 2, img_h - target_h))
            w = min(target_w, img_w - x0)
            h = min(target_h, img_h - y0)
            crop_rect = (x0, y0, w, h)
            crop_path = folder / f"{picture.stem}-crop-{x0}-{y0}-{w}-{h}.png"
            if not (crop_path.exists() and crop_path.stat().st_size > 0):
                tmp = crop_path.with_suffix(".tmp.png")
                image.crop((x0, y0, x0 + w, y0 + h)).save(tmp)
                tmp.replace(crop_path)
            crops.append((crop_rect, crop_path))
    return crops


def prompt(picture: Path, size: tuple[int, int], rects: list[tuple[int, int, int, int]],
           patterns: list[str], is_crops: bool = False,
           symbols_expected: dict[str, int] | None = None) -> str:
    kind = "micro-crop picture" if is_crops else "overlapping tile"
    lines = [f"Sheet picture {picture.name} ({size[0]} x {size[1]} pixels), sent as {len(rects)} {kind}(s), "
             f"one picture each, in this order (each image's place on the whole sheet):"]
    prefix = "Micro-crop" if is_crops else "Tile"
    lines += [f"{prefix} {n}: x {x}, y {y}, {w} x {h} pixels." for n, (x, y, w, h) in enumerate(rects, start=1)]
    lines.append("Count the tags fully matching each of these Python regular expressions (one entry per pattern in "
                 "the answer, in this order):")
    lines += [f"Pattern {n}: {pattern}" for n, pattern in enumerate(patterns, start=1)]
    if symbols_expected:
        lines.append("For equipment where the schedule specifies a count, also count any matching symbols appearing on the drawing without an explicit tag:")
        for pat, exp_cnt in symbols_expected.items():
            lines.append(f"  Pattern {pat}: expect approximately {exp_cnt} untagged symbol(s).")
    item = "crop" if is_crops else "tile"
    items = "micro-crops" if is_crops else "tiles"
    lines.append(f"For each tag give its text, how many places show it, and a box per place: the image number and the "
                 f"box in that {item}'s pixels.")
    every = ", ".join(str(n) for n in range(1, len(rects) + 1))
    lines.append(f"Open and examine all {len(rects)} {items} ({item} {every}), each at full size, for every pattern; "
                 f"each pattern's tiles_examined must list every one of them ({every}), or the answer is refused "
                 "and asked again.")
    return "\n".join(lines)


def unexamined(answer: dict, tiles: int) -> list[str]:
    """The answer's problems with the tiles it examined: one per pattern whose tiles_examined leaves out a tile of
    the `tiles` sent (an empty list when every pattern's answer covers every tile)."""
    problems = []
    for entry in answer.get("patterns", ()) if isinstance(answer, dict) else ():
        if not isinstance(entry, dict):
            continue
        seen = {n for n in entry.get("tiles_examined") or () if isinstance(n, int)}
        missing = [n for n in range(1, tiles + 1) if n not in seen]
        if missing:
            which = f"tile {missing[0]}" if len(missing) == 1 else "tiles " + ", ".join(map(str, missing))
            problems.append(f"pattern {entry.get('pattern', '?')}: {which} not examined (tiles_examined must list "
                            f"every tile from 1 to {tiles}; open and examine each tile picture)")
    return problems


def _placed(box: dict, rects: list[tuple[int, int, int, int]]) -> tuple[int, int, int, int] | None:
    """A box of the answer in the whole picture's pixels, cut to its tile; None when it is in no tile sent or does
    not lie in its tile."""
    n = box["tile"]
    if not 1 <= n <= len(rects):
        return None
    x0, y0, w, h = rects[n - 1]
    x, y, tw, th = box["x"], box["y"], box["width"], box["height"]
    if tw <= 0 or th <= 0 or x < 0 or y < 0 or x >= w or y >= h:
        return None
    return x0 + x, y0 + y, min(tw, w - x), min(th, h - y)


def _clamped(tag: dict, rects: list[tuple[int, int, int, int]]) -> tuple[int, int, int, int]:
    """A box for a counted tag none of whose boxes lies in its tile: its first box pulled into its tile (the first
    tile when it names none sent), at least one pixel, in the whole picture's pixels."""
    box = next((b for b in tag["boxes"] if 1 <= b["tile"] <= len(rects)), None)
    x0, y0, w, h = rects[box["tile"] - 1] if box else rects[0]
    x = min(max(box["x"], 0), w - 1) if box else 0
    y = min(max(box["y"], 0), h - 1) if box else 0
    tw = min(max(box["width"], 1), w - x) if box else 1
    th = min(max(box["height"], 1), h - y) if box else 1
    return x0 + x, y0 + y, tw, th


def misplaced(answer: dict, rects: list[tuple[int, int, int, int]]) -> list[str]:
    """The answer's problems with its boxes: one per pattern that counts tags but has no box lying in a tile sent
    (boxes given in the whole sheet's pixels, or none at all). An empty list when every such pattern places a box."""
    sizes = "; ".join(f"tile {n}: 0 to {w} by 0 to {h}" for n, (_, _, w, h) in enumerate(rects, start=1))
    problems = []
    for entry in answer.get("patterns", ()) if isinstance(answer, dict) else ():
        tags = [t for t in entry.get("tags") or () if isinstance(t, dict) and (t.get("count") or 0) > 0]
        if tags and not any(_placed(b, rects) for t in tags for b in t.get("boxes") or ()):
            problems.append(f"pattern {entry.get('pattern', '?')}: no box lies in its tile (boxes must be in the "
                            f"tile's own pixels, measured from that tile's top-left corner, one box per place the "
                            f"tag is shown; {sizes})")
    return problems


def read_answer(answer: dict, rects: list[tuple[int, int, int, int]]
                ) -> list[tuple[str, tuple[int, int, int, int]]] | None:
    """The answer's tags, every pattern's together, as (text, box in the whole picture's pixels), one per box; None
    when the answer breaks the schema. A box in no tile sent, or not lying in its tile, is dropped (the AI misplaced
    it). A pattern whose counted tags would then keep no box at all keeps each counted tag once, its box pulled into
    the tile (`_clamped`): a tag the AI counts is never silently a count of 0."""
    if schema_errors(answer, SCHEMA):
        return None
    found = []
    for entry in answer["patterns"]:
        tags = [tag for tag in entry["tags"] if tag["count"] > 0]
        placed = [(tag["text"], box) for tag in tags for box in (_placed(b, rects) for b in tag["boxes"]) if box]
        if not placed and rects:
            placed = [(tag["text"], _clamped(tag, rects)) for tag in tags]
        found += placed
    return found


def _loose(pattern: str) -> str:
    """A pattern as compared across the answer: re-escaped text (doubled backslashes) and spacing do not matter."""
    return re.sub(r"\\+", r"\\", pattern).replace(" ", "")


def answered(answer: dict, patterns: list[str]) -> set[str]:
    """The asked patterns the answer has an entry for (leniently: a re-escaped pattern text is the same pattern)."""
    listed = {_loose(str(entry.get("pattern", ""))) for entry in answer.get("patterns", ()) if isinstance(entry, dict)}
    return {p for p in patterns if _loose(p) in listed}


def ask_sheet(transport, picture: Path, patterns: list[str], name: str = "",
              crops: list[tuple[tuple[int, int, int, int], Path]] | None = None,
              symbols_expected: dict[str, int] | None = None
              ) -> tuple[list[tuple[str, tuple[int, int, int, int]]], set[str]] | None:
    """The sheet's one count question: every tile or micro-crop of the picture as its own image, every pattern asked together;
    (the found tags (of every pattern) in the whole picture's pixels, the patterns the answer has an entry for), or
    None when there is no usable answer (waiting for the chat, a transport failure, an answer that breaks the
    schema, an answer whose tiles_examined leaves out a tile, an answer whose counted tags have no box in their tile).
    A pattern the answer leaves out is not counted: it is not among the listed patterns. An answer that breaks the
    schema, did not examine every tile or placed no box in a tile (`misplaced`) is refused through
    the transport's `refuse` (the chat asks again on a later run, the API once more now, with the reason). A
    question refused `max_attempts` times gives None and its "Stopped:" message is added to the transport's
    `count_stops` list, which the run checks after the counts. Never raises for a bad pattern list (a pattern
    that is no regular expression gives None)."""
    from bms.ai import NoAnswer, _ask_checked

    patterns = list(dict.fromkeys(patterns))
    if not patterns:
        return [], set()
    for pattern in patterns:
        re.compile(pattern)
    if crops is not None:
        with Image.open(picture) as img:
            size = img.size
        tiles = crops
        is_crops = True
    else:
        size, tiles = cut_tiles(picture)
        is_crops = False
    rects = [rect for rect, _ in tiles]

    def check(answer):
        if not isinstance(answer, dict):
            return None, ["the answer is not a JSON object"]
        problems = schema_errors(answer, SCHEMA) or unexamined(answer, len(rects)) or misplaced(answer, rects)
        if problems:
            return None, problems
        found = read_answer(answer, rects)
        return (None, ["the answer breaks the schema"]) if found is None else ((found, answered(answer, patterns)), [])

    prompt_text = prompt(picture, size, rects, patterns, is_crops=is_crops, symbols_expected=symbols_expected)
    extra = {
        "step": "count", "picture": str(picture), "tiles": [list(r) for r in rects],
        "patterns": patterns,
    }
    if is_crops:
        extra["is_crops"] = True
    if symbols_expected:
        extra["symbols_expected"] = symbols_expected

    try:
        return _ask_checked(transport, COUNT_KIND, name or f"Count tags {picture.stem}", INSTRUCTIONS, STEP,
                            prompt_text, SCHEMA, extra,
                            tuple(path for _, path in tiles), check)
    except NoAnswer as missing:
        # a question refused its last time is a stop, not a missing count: it is kept on the transport
        # (`count_stops`) so the run stops at the count step with it instead of writing without the count
        if not missing.waiting and str(missing.reason).startswith("Stopped:"):
            try:
                stops = getattr(transport, "count_stops", None)
                if stops is None:
                    stops = []
                    transport.count_stops = stops
                stops.append(str(missing.reason))
            except Exception:
                pass
        return None
    except Exception as error:          # a transport failure is no count, never a crash
        if hasattr(transport, "last_error"):
            try:
                transport.last_error = f"{type(error).__name__}: {error}"
            except Exception:
                pass
        return None
