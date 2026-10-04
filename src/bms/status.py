"""Plain-words status of a run, read only from the files the run already wrote.

No AI and no network. The files are the ledger, the job, the chat requests, the refusal counters, the intake
log, and the review page.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

_ORDER = ("read", "count", "write", "decisions", "qc", "revise", "done")
_KIND_STAGE = {"write_system": "write", "qc_job": "qc", "revise_system": "revise", "count_sheet": "count"}


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _requests(cache: Path) -> list[tuple[Path, dict]]:
    folder = cache / "judge-chat" / "requests"
    found = []
    for path in sorted(folder.glob("*.json")):
        data = _load(path)
        if isinstance(data, dict):
            found.append((path, data))
    return found


def _stage(out: Path, cache: Path, requests: list[tuple[Path, dict]]) -> str:
    steps = []
    for _, data in requests:
        step = data.get("step") or _KIND_STAGE.get(str(data.get("kind") or ""))
        if step in _ORDER:
            steps.append(step)
    if steps:
        return max(steps, key=_ORDER.index)
    if (out / "Review.html").is_file():
        return "done"
    ledgers = list(out.glob("* Ledger.json"))
    if ledgers:
        data = _load(ledgers[0]) or {}
        if not data.get("complete"):
            return "read"
    if list(out.glob("* Job.json")):
        return "write"
    if ledgers:
        return "read"
    return ""


def _systems(out: Path) -> list[str]:
    names: list[str] = []
    for path in sorted(out.glob("* Job.json")):
        data = _load(path) or {}
        for system in data.get("systems") or []:
            if isinstance(system, dict) and system.get("name"):
                names.append(str(system["name"]))
    return names


def _findings(out: Path) -> dict[str, int]:
    page = out / "Review.html"
    if not page.is_file():
        return {}
    counts: dict[str, int] = defaultdict(int)
    text = page.read_text(encoding="utf-8", errors="replace")
    for piece in text.split("Rule: ")[1:]:
        rule = piece.split("<", 1)[0].strip()
        if rule:
            counts[rule] += 1
    return dict(counts)


def report(out: Path, cache: Path) -> list[str]:
    """Lines a person can read. An empty run says so."""
    out, cache = Path(out), Path(cache)
    if not out.exists():
        return [f"There is no folder at {out}."]
    requests = _requests(cache)
    ledgers = list(out.glob("* Ledger.json"))
    jobs = list(out.glob("* Job.json"))
    if not ledgers and not jobs and not requests and not (out / "Review.html").is_file():
        return ["This folder has no run. There is no ledger, no saved job, and no chat request."]

    stage = _stage(out, cache, requests)
    lines = [f"Stage: {stage}."]
    if stage == "read" and ledgers:
        data = _load(ledgers[0]) or {}
        stopped = data.get("stopped_at") or "a reading pass"
        lines = [f"Stage: read. Reading stopped at the {stopped} pass."]
    elif requests:
        lines = [f"Stage: {stage}. The run is waiting for an answer."]
    elif stage == "done":
        lines = ["Stage: done. The review page is written and nothing is waiting."]
    elif jobs:
        lines = ["Stage: write. The job is saved and nothing is waiting for an answer."]

    systems = _systems(out)
    lines.append("Systems written: " + (", ".join(systems) if systems else "none yet") + ".")

    if requests:
        by_kind: dict[str, list[str]] = defaultdict(list)
        for path, data in requests:
            by_kind[str(data.get("kind") or "request")].append(path.name)
        for kind in sorted(by_kind):
            names = ", ".join(by_kind[kind])
            lines.append(f"Waiting: {len(by_kind[kind])} {kind} request(s): {names}.")
    else:
        lines.append("Waiting: no chat requests.")

    attempt_dir = cache / "attempts"
    attempt_files = sorted(attempt_dir.glob("*.json")) if attempt_dir.is_dir() else []
    total = 0
    named: list[str] = []
    for path in attempt_files:
        data = _load(path) or {}
        count = int(data.get("attempts") or 0)
        if count:
            total += count
            named.append(f"{path.name} ({count})")
    if named:
        lines.append(f"Refusals: {len(named)} question(s), {total} attempt(s): {', '.join(named)}.")
    else:
        lines.append("Refusals: none recorded.")

    intake = _load(cache / "intake.json")
    if isinstance(intake, list) and intake:
        lines.append("Intake:")
        for item in intake:
            if isinstance(item, dict):
                lines.append(f"- {item.get('system', 'a system')}: {item.get('change', 'a change')}.")
    else:
        lines.append("Intake: no changes recorded.")

    findings = _findings(out)
    if findings:
        bits = [f"{count} for {rule}" for rule, count in sorted(findings.items())]
        lines.append("Findings: " + "; ".join(bits) + ".")
    elif (out / "Review.html").is_file():
        lines.append("Findings: the review page has none.")
    else:
        lines.append("Findings: no review page yet.")
    return lines
