"""The Master Template as data (`HarkPro/doctrine/lines.json`), read tolerantly.

Expected shape (written by the doctrine work, in parallel with this code):

    {"families": [ {"id": "vav", "family": "VAV box" (or "name"), "aliases": ["VAV", ...], "tech_hours": ...,
                    "lines": [ {"id": "VAV.space_sensor", "text": "Furnish and Install Space Temperature Sensor",
                                "verb": "Furnish and Install", "owner_furnish": "AME", "owner_install": "AME",
                                "owner_wire": "AME", "applies_when": "...", "source": "..."} ]} ],
     "tech_hours": {...}, "client_notes": [...]}

`families` may also be an object keyed by family id. Any extra keys are kept and ignored. When the file is missing
or unreadable, `load_lines()` gives an empty library and every suggestion is left blank.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "doctrine" / "lines.json"


@dataclass(frozen=True)
class LibLine:
    family_id: str
    family_name: str
    id: str
    text: str
    verb: str = ""
    applies_when: str = ""
    aliases: tuple[str, ...] = ()
    raw: dict = field(default_factory=dict, compare=False, hash=False, repr=False)


@dataclass
class Library:
    lines: list[LibLine] = field(default_factory=list)
    families: dict[str, str] = field(default_factory=dict)       # id -> name
    client_notes: list = field(default_factory=list)
    path: str = ""

    def __bool__(self) -> bool:
        return bool(self.lines)


def _families(data) -> list[tuple[str, dict]]:
    fams = data.get("families") if isinstance(data, dict) else data
    if isinstance(fams, dict):
        return [(str(k), v if isinstance(v, dict) else {"lines": v}) for k, v in fams.items()]
    out = []
    for f in fams or []:
        if isinstance(f, dict):
            out.append((str(f.get("id") or f.get("key") or f.get("name") or ""), f))
    return out


def parse_lines(data) -> Library:
    lib = Library()
    for fid, fam in _families(data):
        name = str(fam.get("name") or fam.get("family") or fam.get("title") or fid)
        aliases = tuple(str(a) for a in fam.get("aliases") or [] if isinstance(a, str))
        lib.families[fid] = name
        if fam.get("client_notes"):
            lib.client_notes.extend(fam["client_notes"] if isinstance(fam["client_notes"], list)
                                    else [fam["client_notes"]])
        for ln in fam.get("lines") or []:
            if isinstance(ln, str):
                ln = {"text": ln}
            if not isinstance(ln, dict):
                continue
            text = str(ln.get("text") or ln.get("line") or "")
            if not text:
                continue
            lib.lines.append(LibLine(fid, name, str(ln.get("id") or f"{fid}.{len(lib.lines) + 1}"), text,
                                     str(ln.get("verb") or ""), str(ln.get("applies_when") or ""), aliases, ln))
    if isinstance(data, dict) and data.get("client_notes"):
        lib.client_notes = list(data["client_notes"]) + lib.client_notes
    return lib


def load_lines(path: str | Path | None = None) -> Library:
    path = Path(path) if path else DEFAULT_PATH
    try:
        lib = parse_lines(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return Library()
    lib.path = str(path)
    return lib
