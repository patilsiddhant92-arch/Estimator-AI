"""The proof images of the counts (workstream 6), for the review page: a crop of the sheet picture with every
counted tag boxed — red where the tag was located on the sheet text, blue where it was counted on the sheet
picture — and a manifest, `<cache>/count-proofs/proofs.json`, naming each proof with its counts and tags."""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
from collections.abc import Sequence
from pathlib import Path

from PIL import Image, ImageDraw

PROOFS_FOLDER = "count-proofs"
MANIFEST = "proofs.json"
MARGIN = 80          # pixels of the sheet kept around the boxes
MIN_SIDE = 400       # a crop is at least this wide and high (where the sheet allows), so the tag is seen in place
MAX_SIDE = 2000      # a larger crop is shrunk to this longest edge
LOCATED = (220, 20, 20)
SEEN = (20, 60, 230)

Box = tuple[int, int, int, int]


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-")[:40] or "x"


def draw_proof(picture: Path, located: Sequence[Box], seen: Sequence[Box], folder: Path, name: str) -> Path | None:
    """The crop of `picture` around every box, boxes drawn (located red, seen blue), saved under `folder`; None when
    there is nothing to show."""
    boxes = [*located, *seen]
    if not boxes:
        return None
    with Image.open(picture) as image:
        width, height = image.size
        left = max(0, min(x for x, _, _, _ in boxes) - MARGIN)
        top = max(0, min(y for _, y, _, _ in boxes) - MARGIN)
        right = min(width, max(x + w for x, _, w, _ in boxes) + MARGIN)
        bottom = min(height, max(y + h for _, y, _, h in boxes) + MARGIN)
        left, right = _widen(left, right, width)
        top, bottom = _widen(top, bottom, height)
        crop = image.crop((left, top, right, bottom)).convert("RGB")
    draw = ImageDraw.Draw(crop)
    line = max(3, (right - left) // 600)
    for colour, group, pad in ((LOCATED, located, 4), (SEEN, seen, 4 + line + 2)):
        for x, y, w, h in group:
            draw.rectangle((x - left - pad, y - top - pad, x - left + w + pad, y - top + h + pad), outline=colour,
                           width=line)
    longest = max(crop.size)
    if longest > MAX_SIDE:
        ratio = MAX_SIDE / longest
        crop = crop.resize((max(1, int(crop.size[0] * ratio)), max(1, int(crop.size[1] * ratio))))
    folder.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(f"{picture}|{sorted(located)}|{sorted(seen)}".encode()).hexdigest()[:10]
    path = folder / f"{_slug(name)}-{digest}.png"
    tmp = path.with_name(f"{path.stem}.{os.getpid()}-{secrets.token_hex(4)}.tmp.png")
    try:
        crop.save(tmp)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()
    return path


def _widen(low: int, high: int, limit: int) -> tuple[int, int]:
    """The span [low, high) grown about its middle to MIN_SIDE, kept inside [0, limit)."""
    if high - low >= MIN_SIDE:
        return low, high
    if limit <= MIN_SIDE:
        return 0, limit
    start = max(0, min((low + high) // 2 - MIN_SIDE // 2, limit - MIN_SIDE))
    return start, start + MIN_SIDE


def manifest_path(cache: Path) -> Path:
    return Path(cache).resolve() / PROOFS_FOLDER / MANIFEST


def load_manifest(cache: Path) -> list[dict]:
    try:
        data = json.loads(manifest_path(cache).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [entry for entry in data if isinstance(entry, dict)] if isinstance(data, list) else []


def save_manifest(cache: Path, entries: Sequence[dict]) -> None:
    """The manifest with `entries` replacing any earlier entry for the same system, family and sheet."""
    path = manifest_path(cache)
    def key(entry):
        return entry.get("system_key"), entry.get("family"), entry.get("sheet")
    fresh = {key(e) for e in entries}
    kept = [e for e in load_manifest(cache) if key(e) not in fresh]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.stem}.{os.getpid()}-{secrets.token_hex(4)}.tmp")
    try:
        tmp.write_text(json.dumps([*kept, *entries], indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()
