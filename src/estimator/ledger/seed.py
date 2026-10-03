"""The ledger's seed (design 2026-09-29 §1.3): the facts the readers already found, written into the ledger before
the AI reads a single pass. A schedule's own count is settled; a count from the plans or the tags alone is added,
for the schedules pass to confirm, and so is every family's name. Every seed fact cites the dossier line it comes from."""
from __future__ import annotations

import re

from estimator.ledger.facts import ADDED, SETTLED, Ledger

_SECTION = re.compile(r"^== (\d)\. [A-Z ]+ ==\s*$")
_ID_LINE = re.compile(r"^\[(S\d+)\] (.*)$")
_SHEET_TEXT_START = "--- 7c PLAN SHEET TEXT ---"
_SHEET_LINE = re.compile(r"^\[(S\d+)\] (?:(?P<number>[A-Z][A-Z0-9.\-]*\d[A-Z0-9.\-]*), )?")
_COUNT_LINE = re.compile(r"^\[(S\d+)\] (?P<prefix>[A-Z0-9/\-]+) \((?P<kind>[^)]*)\): (?P<body>.*)$")
_DEVICE_LINE = re.compile(r"^\[(S\d+)\] (?P<label>\S+) \((?P<name>[^)]*)\): (?P<total>\d+) in all")
_TAGS = re.compile(r"\bTags: (.+?)\.(?: By location|\s*Reading notes|$)")


def dossier_sections(text: str) -> dict[int, str]:
    """{section number: its text, heading line first} for the dossier's "== N. HEADING ==" sections."""
    found: dict[int, list[str]] = {}
    current = None
    for line in (text or "").splitlines():
        match = _SECTION.match(line)
        if match:
            current = int(match.group(1))
            found[current] = [line]
        elif current is not None:
            found[current].append(line)
    return {n: "\n".join(lines) for n, lines in found.items()}


def sheet_text_lines(text: str) -> list[tuple[str, str, str]]:
    """(source id, sheet number or "", the line) for each sheet's own text in section 7's 7c block."""
    section = dossier_sections(text).get(7, "")
    if _SHEET_TEXT_START not in section:
        return []
    block = section.split(_SHEET_TEXT_START, 1)[1]
    lines = []
    for line in block.splitlines():
        match = _SHEET_LINE.match(line)
        if match:
            lines.append((match.group(1), match.group("number") or "", line))
    return lines


def _count_lines(sections: dict[int, str]) -> dict[str, tuple[str, str, str, str]]:
    """prefix -> (source id, the quote: the line up to its first full stop, the whole line, the kind the line names
    in brackets)."""
    found = {}
    for line in sections.get(5, "").splitlines():
        match = _COUNT_LINE.match(line)
        if match:
            body = match.group("body")
            head = f"{match.group('prefix')} ({match.group('kind')}): {body.split('.')[0]}"
            found[match.group("prefix")] = (match.group(1), head, line, match.group("kind").strip())
    return found


def _positive(value) -> int | None:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def seed(dossier) -> Ledger:
    ledger = Ledger(dict(dossier.sources))
    ledger.job_name = str(getattr(dossier, "job_name", "") or "")
    sections = dossier_sections(dossier.text)
    kinds = {f.prefix: f.kind for f in getattr(dossier, "families", ()) or ()}
    count_lines = _count_lines(sections)

    for prefix, counts in (getattr(dossier, "counts", None) or {}).items():
        if prefix not in count_lines:
            continue                      # no dossier line to cite: no fact
        sid, quote, line, kind_from_line = count_lines[prefix]
        rows = _positive(counts.get("schedule_rows"))
        # the kind's name is the catalogue's guess, not the schedule's words: the schedules pass settles it
        ledger.add("family", prefix, kinds.get(prefix) or kind_from_line or "equipment", sid, quote, "seed", ADDED)
        settled = _positive(counts.get("quantity_column")) or rows
        added = _positive(counts.get("plan_placements")) or _positive(counts.get("distinct_tags"))
        if settled:
            ledger.add("count", prefix, settled, sid, quote, "seed", SETTLED)
        elif added:
            ledger.add("count", prefix, added, sid, quote, "seed", ADDED)
        tags = _TAGS.search(line)
        if tags:
            ledger.add("unit", prefix, tags.group(1).strip(), sid, f"Tags: {tags.group(1).strip()}", "seed", ADDED)

    for line in sections.get(6, "").splitlines():
        match = _DEVICE_LINE.match(line)
        if match:
            ledger.add("device", match.group("label"), int(match.group("total")), match.group(1), line.split("] ", 1)[1],
                       "seed", ADDED)

    for qid, (heading, _ids) in (getattr(dossier, "sections", None) or {}).items():
        if ledger.knows(qid):
            ledger.add("sequence_match", heading, "", qid, heading, "seed", ADDED)
    return ledger
