"""Reading the existing app's outputs, and the few app functions HarkPro reuses (read-only).

Job.json and Ledger.json are read as plain dicts, not through `bms.model.Job.from_dict`: that loader is strict and a
Job written by a newer branch of the app (an extra key such as `count.basis`) would refuse to load. When the app is
importable, `app_job()` prunes unknown keys and builds the real model so the app's renderer and price book can be used;
when it is not, HarkPro falls back to its own plain wording and leaves prices pending.
"""
from __future__ import annotations

import dataclasses
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import get_args, get_origin, get_type_hints, Union
import types

# ---- files -------------------------------------------------------------------------------------------------


def load_json(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def fact_list(ledger: dict) -> list[dict]:
    return list(ledger.get("facts") or [])


def where(ledger: dict, source_id: str) -> str:
    """The place a source id names in the ledger ("M-201, Drawings.pdf page 3"), "" when unknown."""
    value = (ledger.get("sources") or {}).get(source_id, "")
    return value if isinstance(value, str) else str(value.get("where", "")) if isinstance(value, dict) else ""


def split_where(text: str) -> tuple[str, str]:
    """("M-201", "Drawings.pdf page 3") from "M-201, Drawings.pdf page 3"; ("", text) when there is no sheet part."""
    text = re.sub(r"\s*\([^)]*\)\s*$", "", text or "").strip()
    m = re.search(r"([^,]*?\.pdf\s+page\s+\d+)", text, re.I)
    if not m:
        return "", text
    doc = m.group(1).strip()
    sheet = text[: m.start()].strip().rstrip(",").strip()
    found = re.findall(r"\b([A-Z]{1,3}-?\d{3,4}(?:\.\d{1,3})?)\b", sheet)
    return (found[-1] if found else sheet), doc


# ---- tags --------------------------------------------------------------------------------------------------

_TAG = re.compile(r"\b([A-Z]{1,5}(?:-[A-Z0-9]{1,4})*-\d{1,3}[A-Z]?)\b")
_RUN = re.compile(r"\b([A-Z]{1,5}(?:-[A-Z0-9]{1,4})*-)(\d{1,3})((?:\s*,\s*\d{1,3}\b)+|\s+(?:thru|through|to)\s+(?:\1)?(\d{1,3})\b)", re.I)


def norm_tag(tag: str) -> str:
    return re.sub(r"[-_ #]", "", str(tag).upper())


def tags_in(text: str) -> set[str]:
    """Equipment tags a text names, normalised ("AC-3-1, 2" gives AC31 and AC32; "VAV-1 thru 3" gives three)."""
    text = str(text or "")
    found: set[str] = set()
    try:  # the app's own expansion, when it is importable
        from estimator.writing.assemble import header_tags
        found |= {norm_tag(t) for t in header_tags(text)}
    except Exception:  # pragma: no cover - the app is not on the path
        pass
    upper = text.upper()
    found |= {norm_tag(t) for t in _TAG.findall(upper)}
    for m in _RUN.finditer(upper):
        prefix, first = m.group(1), m.group(2)
        width = len(first)
        if m.group(4):
            lo, hi = int(first), int(m.group(4))
            numbers = range(lo, hi + 1) if 0 < hi - lo < 200 else [lo, hi]
        else:
            numbers = [int(first)] + [int(n) for n in re.findall(r"\d{1,3}", m.group(3))]
        found |= {norm_tag(f"{prefix}{str(n).zfill(width)}") for n in numbers}
    return found


# ---- the job as rows -----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Line:
    """One printed scope line of a Job, as HarkPro sees it."""
    id: str
    system_key: str          # "FE" for the front end
    system_name: str
    alternate: str           # base / add / deduct
    slot: str
    name: str
    verb: str
    furnished_by: str
    installed_by: str
    wired_by: str
    quantity: int | None
    refs: tuple[dict, ...]
    flag: str
    assumption: str
    text: str                # as printed (the app's renderer when available)


def _qty(count) -> int | None:
    if not isinstance(count, dict):
        return None
    # ruling R1: the schedule count (the count's own value) prints; the others are discrepancy flags, never a max
    value = count.get("value")
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def plain_text(device: dict) -> str:
    """The house line without the app's renderer: "<Verb> <Name> (Furnished by X)"."""
    verb, name = device.get("verb", ""), device.get("name", "")
    text = f"{verb} {name}".strip()
    furnisher = device.get("furnished_by", "")
    if verb in ("Install and Wire", "Wire") and furnisher and furnisher != "AME":
        text += f" (Furnished by {furnisher})"
    return text


def job_lines(job: dict, printed: dict[str, str] | None = None) -> list[Line]:
    printed = printed or {}
    out: list[Line] = []
    blocks = [(s.get("key", ""), s.get("name", ""), s.get("alternate", "base"), s.get("devices") or [])
              for s in job.get("systems") or []]
    fe = job.get("front_end") or {}
    blocks.append(("FE", "Front end", "base", fe.get("devices") or []))
    for key, name, alternate, devices in blocks:
        for d in devices:
            a = d.get("assumption") or {}
            assumption = f"{a.get('what', '')}. Why: {a.get('why', '')}" if a else ""
            out.append(Line(d.get("id", ""), key, name, alternate, d.get("slot", ""), d.get("name", ""),
                            d.get("verb", ""), d.get("furnished_by", ""), d.get("installed_by", ""),
                            d.get("wired_by", ""), _qty(d.get("quantity")), tuple(d.get("refs") or ()),
                            d.get("flag", "none"), assumption, printed.get(d.get("id", "")) or plain_text(d)))
    return out


def system_quantity(system: dict) -> int | None:
    """The block's heading count: its tagged families' counts (an untagged family, such as the dampers a unit
    carries, is not part of the heading), else the first family's."""
    families = list(system.get("families") or [])
    tagged = [f for f in families if f.get("tags")] or families[:1]
    numbers = [q for f in tagged if (q := _qty(f.get("count"))) is not None]
    return sum(numbers) if numbers else None


# ---- the app, read-only ------------------------------------------------------------------------------------


def _prune(tp, data):
    """`data` with every key the app's model does not know dropped, recursively (for a Job from a newer branch)."""
    origin = get_origin(tp)
    if origin in (Union, types.UnionType):
        inner = [a for a in get_args(tp) if a is not type(None)]
        return data if data is None or len(inner) != 1 else _prune(inner[0], data)
    if origin is tuple and isinstance(data, list):
        (item,) = [a for a in get_args(tp) if a is not Ellipsis]
        return [_prune(item, v) for v in data]
    if dataclasses.is_dataclass(tp) and isinstance(data, dict):
        hints = get_type_hints(tp)
        names = {f.name for f in dataclasses.fields(tp)}
        return {k: _prune(hints[k], v) for k, v in data.items() if k in names}
    return data


def app_job(job: dict):
    """The app's `bms.model.Job` for this dict, or None when the app is not importable or the dict will not load."""
    try:
        from bms.model import Job
        return Job.from_dict(_prune(Job, job))
    except Exception:
        return None


def printed_texts(job: dict) -> dict[str, str]:
    """device id -> the line exactly as the app's renderer prints it; {} when the app cannot render this job."""
    model = app_job(job)
    if model is None:
        return {}
    try:
        from bms.playbook import load_playbook
        from bms.render import render
        draft = render(model, load_playbook())
        return {line.device_id: line.text for line in draft.lines if line.device_id and line.kind == "line"}
    except Exception:
        return {}


def printed_notes(job: dict) -> dict[str, list[str]] | None:
    """system key ("FE" for the front end) -> the "*" / "**" notes exactly as the app's renderer prints them under
    that block (clarifications and the *Assumed reasons of its lines); None when the app cannot render this job."""
    model = app_job(job)
    if model is None:
        return None
    try:
        from bms.playbook import load_playbook
        from bms.render import render
        draft = render(model, load_playbook())
    except Exception:
        return None
    out: dict[str, list[str]] = {}
    for line in draft.lines:
        if line.kind == "note" and line.text.lstrip().startswith("*"):
            out.setdefault(line.system_key or "FE", []).append(line.text)
    return out


class Prices:
    """The app's price book, read-only: a printed line's unit price, or None (PRICE PENDING)."""

    def __init__(self) -> None:
        self.book = None
        try:
            from estimator.__main__ import ALIASES, PRICE_BOOK
            from estimator.price_sheet.price_book import PriceBook
            self.book = PriceBook.load(PRICE_BOOK, ALIASES)
        except Exception:
            self.book = None

    def unit(self, text: str) -> float | None:
        if self.book is None:
            return None
        try:
            item = self.book.lookup(text)
        except Exception:
            return None
        return None if item is None else float(item.price)
