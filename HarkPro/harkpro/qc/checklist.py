"""Generic family checklists from the Master Template as data (`HarkPro/doctrine/lines.json`).

`families_for(job, evidence, data)` picks every family the scope or the evidence names (by its `aliases`: a short
upper-case alias such as "AC" or "EF" is a tag prefix and matches "AC-1" or a tag list; a longer alias is matched as
words). A shared alias (AC is both a split system and a packaged unit's tag) picks both families: the critic decides
which one the documents describe. The front end is always in. `checklist(family)` lists every line of the family with
what the critic needs to judge it. Nothing here is job-specific: the checks come from the template, so a miss is
caught by method, not by a ruling written for one job.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

DOCTRINE = Path(__file__).resolve().parents[2] / "doctrine"
LINES = DOCTRINE / "lines.json"
RULINGS = DOCTRINE / "rulings.md"
ALWAYS = ("front_end",)

LINE_KEYS = ("id", "text", "verb", "owner_furnish", "owner_install", "owner_wire", "applies_when", "required",
             "alt_group", "variant", "depth", "parent", "template_exact")


def load_lines(path: str | Path | None = None) -> dict:
    return json.loads(Path(path or LINES).read_text(encoding="utf-8"))


def load_rulings(path: str | Path | None = None) -> str:
    try:
        return Path(path or RULINGS).read_text(encoding="utf-8")
    except OSError:
        return ""


def _alias_rx(alias: str) -> re.Pattern:
    a = alias.strip()
    if re.fullmatch(r"[A-Z0-9/]{1,6}", a):                     # a tag prefix: "AC" matches AC-3-1, "AC 1", "ACs"
        return re.compile(rf"(?<![A-Z0-9]){re.escape(a)}(?:-?\d|-[A-Z0-9]|\b)")
    return re.compile(rf"\b{re.escape(a)}s?\b", re.I)


def _texts(job: dict, evidence) -> list[str]:
    out = []
    for s in job.get("systems") or []:
        out.append(f"{s.get('name', '')} {s.get('shape', '')}")
        for f in s.get("families") or []:
            out.append(" ".join([f.get("name", "")] + list(f.get("tags") or [])))
    out += [getattr(e, "text", "") if not isinstance(e, dict) else e.get("text", "") for e in evidence or []]
    return out


def families_for(job: dict, evidence=(), data: dict | None = None) -> list[dict]:
    data = data or load_lines()
    texts = _texts(job, evidence)
    picked = []
    for fam in data.get("families") or []:
        fid = fam.get("id")
        aliases = [a for a in fam.get("aliases") or [] if isinstance(a, str) and a.strip()]
        names = [fam.get("family") or fam.get("name") or ""]
        hit = fid in ALWAYS or any(_alias_rx(a).search(t) for a in aliases + [n for n in names if n] for t in texts)
        if hit:
            picked.append(fam)
    return picked


def checklist(fam: dict) -> dict:
    return {"family_id": fam.get("id"), "family": fam.get("family") or fam.get("name"),
            "aliases": fam.get("aliases") or [], "variants": fam.get("variants") or {},
            "lines": [{k: ln[k] for k in LINE_KEYS if k in ln} for ln in fam.get("lines") or []],
            "client_notes": [c.get("text") if isinstance(c, dict) else c for c in fam.get("client_notes") or []]}


def line_index(data: dict | None = None) -> dict[str, dict]:
    data = data or load_lines()
    return {ln["id"]: ln for fam in data.get("families") or [] for ln in fam.get("lines") or [] if "id" in ln}


_PLACEHOLDER = re.compile(r"\{[a-z_]+\}|##+|#|\*{3,}|\bABC\b")


def template_matches(template: str, text: str) -> bool:
    """Whether `text` is the template line with its placeholders filled (case and spacing aside)."""
    def norm(s):
        return re.sub(r"\s+", " ", s).strip().lower()
    parts = [norm(p) for p in _PLACEHOLDER.split(re.sub(r"\s+", " ", template).strip())]
    rx = r"\s*.*?\s*".join(re.escape(p) for p in parts)
    return re.fullmatch(rx + r"(?:\s*\(.*\))?", norm(text)) is not None
