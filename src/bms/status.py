"""Plain-words status of a run, read only from the files the run already wrote.

No AI, no network, and nothing is written. The files are the ledger, the saved job (the one of the ledger's quote),
the run state the run writes first and last (`run state.json`), the chat requests and their answers, the refusal counters, the intake log, the review
page, and the proposal and price sheet.

The run is "done" only when the review page, the proposal and the price sheet are all at least as new as the
newest ledger and job, and the last run said it was done in its run state (a run from before the run state was
written: the outputs alone decide). A review page left by an earlier run never makes a run that is reading again,
stopped, or waiting on decisions look finished. A run writes "running" first and replaces it with how it ended
last, so a "running" state, of any age, means the run is still going or did not reach the end (it ended with an
error). A run state older than the ledger or the job is not trusted: a run saved them after the last one ended. A
run state that names another quote or job than the newest ledger's is another job's, and is not trusted either. A
run stopped after the most refusals leaves no request; its run state keeps the run's own words, which name the
request.

Only requests whose job is the ledger's job are this run's (the requests folder keeps other jobs' requests). Every
file is read whole in one go and closed (the estimate may be writing them at that moment); one that cannot be read,
or is half-written, is named and never raises. Exit codes follow `estimate`: 0 done, 2 waiting for answers, 1
stopped, not finished, no folder, or no run.
"""
from __future__ import annotations

import html
import json
import re
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

RUN_STATE = "run state.json"        # out/: "running", then how the last run ended; written by bms.run.estimate
REVIEW_PAGE = "Review.html"
_ORDER = ("read", "count", "write", "decisions", "qc", "revise", "done")
_KIND_STAGE = {"read_pass": "read", "read_schedule": "read", "count_tags": "count", "write_system": "write",
               "qc_job": "qc"}
_STEP_STAGE = {"count": "count", "write": "write", "decide": "write", "revise": "revise", "qc": "qc"}
_SHOWN = 10                         # names shown on one line before "and N more"
_RULE = re.compile(r'<span class="rule">Rule: (.*?)</span>', re.S)
_DONE = ("Stage: done. The review page, the proposal and the price sheet are written after the last reading and "
         "the last save of the job, and nothing is waiting.")


@dataclass(frozen=True)
class Status:
    code: int                       # 0 done, 2 waiting for answers, 1 stopped / not finished / no folder / no run
    lines: tuple[str, ...]


@dataclass(frozen=True)
class _Request:
    kind: str
    stage: str
    system: str
    job: str
    answered: bool                  # its answer file is newer than it: the next estimate reads it
    refused_before: bool            # asked again after an earlier answer was refused


def _bytes(path: Path) -> tuple[bytes | None, str]:
    try:
        return path.read_bytes(), ""
    except OSError as error:
        return None, error.strerror or str(error)


def _json(path: Path) -> tuple[object, str]:
    """The file's value and "", or None and a plain reason. A file that is locked or half-written is looked at again
    (3 looks, 100 ms apart) before it is given up on."""
    for look in range(3):
        raw, problem = _bytes(path)
        if raw is not None:
            try:
                return json.loads(raw.decode("utf-8-sig")), ""
            except (UnicodeDecodeError, ValueError):
                problem = "it is not whole JSON (it may be half-written; run status again)"
        if look < 2 and path.exists():
            time.sleep(0.1)
    return None, problem


def _dict(path: Path) -> tuple[dict, str]:
    value, problem = _json(path)
    if problem:
        return {}, problem
    if not isinstance(value, dict):
        return {}, "it does not hold what a run writes there"
    return value, ""


def _mtime(path: Path) -> int | None:
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return None


def _newest_first(folder: Path, pattern: str) -> list[Path]:
    """The files matching `pattern`, newest first; one that vanishes while it is listed is left out."""
    try:
        found = list(folder.glob(pattern))
    except OSError:
        return []
    stamped = [(stamp, path) for path in found if (stamp := _mtime(path)) is not None and path.is_file()]
    return [path for _, path in sorted(stamped, key=lambda item: (item[0], item[1].name), reverse=True)]


def _text(value, default: str = "") -> str:
    return value.strip() if isinstance(value, str) and value.strip() else default


def _names(items: list[str]) -> str:
    shown = ", ".join(items[:_SHOWN])
    return shown + (f" and {len(items) - _SHOWN} more" if len(items) > _SHOWN else "")


def _requests(cache: Path) -> tuple[list[_Request], int]:
    """The requests in the chat folder (not requests/old/), and how many could not be read."""
    found: list[_Request] = []
    unreadable = 0
    for path in sorted(_newest_first(cache / "judge-chat" / "requests", "*.json"), key=lambda p: p.name):
        data, problem = _dict(path)
        if problem:
            if _mtime(path) is not None:            # gone since the listing: retired or dropped, not a problem
                unreadable += 1
            continue
        kind = _text(data.get("kind"), "request")
        stage = _STEP_STAGE.get(_text(data.get("step"))) or _KIND_STAGE.get(kind, "")
        answer = _text(data.get("answer_file"))
        answer_time, asked_time = (_mtime(Path(answer)) if answer else None), _mtime(path)
        answered = answer_time is not None and (asked_time is None or answer_time > asked_time)
        found.append(_Request(kind, stage, _text(data.get("system"), "a question"), _text(data.get("job")),
                              answered, bool(data.get("previous_problem"))))
    return found, unreadable


def _systems(job_file: Path | None) -> list[str]:
    """A system is written once the writer filled its devices or said why it has no scope; else it is planned."""
    if job_file is None:
        return ["Systems written: none yet."]
    data, problem = _dict(job_file)
    if problem:
        return [f"Systems: the saved job {job_file.name} could not be read: {problem}."]
    written, planned = [], []
    systems = data.get("systems")
    for system in systems if isinstance(systems, list) else []:
        if not isinstance(system, dict) or not _text(system.get("name")):
            continue
        devices = system.get("devices")
        filled = (isinstance(devices, list) and bool(devices)) or bool(_text(system.get("no_scope_reason")))
        (written if filled else planned).append(_text(system.get("name")))
    lines = [f"Systems written: {_names(written) if written else 'none yet'}."]
    if planned:
        lines.append(f"Systems planned, not written yet: {_names(planned)}.")
    return lines


def _refusals(cache: Path) -> str:
    counts = []
    for path in _newest_first(cache / "judge" / "attempts", "*.json"):
        value = _dict(path)[0].get("attempts")
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            counts.append(value)
    if not counts:
        return "Refusals: none recorded."
    return f"Refusals: {len(counts)} question(s) have refused answers; the most for one question is {max(counts)}."


def _intake(cache: Path) -> list[str]:
    value, _ = _json(cache / "intake.json")
    items = [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []
    lines = [f"- {_text(item.get('system'), 'a system')}: {_text(item.get('change'), 'a change')}."
             for item in items if _text(item.get("system")) or _text(item.get("change"))]
    return ["Intake:", *lines] if lines else ["Intake: no changes recorded."]


def _findings(page: Path, current: bool) -> str:
    """The rule of each finding on the review page, from its rule spans only (never from quoted job text)."""
    if not page.is_file():
        return "Findings: no review page yet."
    raw, problem = _bytes(page)
    if raw is None:
        return f"Findings: the review page could not be read: {problem}."
    counts: dict[str, int] = defaultdict(int)
    for found in _RULE.findall(raw.decode("utf-8", errors="replace")):
        rule = html.unescape(found).strip()
        if rule:
            counts[rule] += 1
    where = "" if current else " (from a review page that is not this run's final one)"
    if not counts:
        return f"Findings{where}: the review page has none."
    return f"Findings{where}: " + "; ".join(f"{n} for {rule}" for rule, n in sorted(counts.items())) + "."


def check(out: Path, cache: Path) -> Status:
    """How far the run in `out` got, in lines a person can read, and the exit code."""
    out, cache = Path(out), Path(cache)
    if not out.exists():
        return Status(1, (f"There is no folder at {out}.",))
    if not out.is_dir():
        return Status(1, (f"{out} is not a folder. Give the output folder of a run.",))
    ledgers, jobs = _newest_first(out, "* Ledger.json"), _newest_first(out, "* Job.json")
    requests, unreadable = _requests(cache)
    state_file, page = out / RUN_STATE, out / REVIEW_PAGE
    if not (ledgers or jobs or requests or unreadable or page.is_file() or state_file.is_file()):
        return Status(1, ("This folder has no run. There is no ledger, no saved job, and no chat request.",))

    ledger, ledger_problem = _dict(ledgers[0]) if ledgers else ({}, "")
    job_name = _text(ledger.get("job_name"))
    mine = [r for r in requests if r.job == job_name] if job_name else requests
    others = len(requests) - len(mine)
    waiting = [r for r in mine if not r.answered]
    newest_saved = max((stamp for path in (*ledgers, *jobs) if (stamp := _mtime(path)) is not None), default=None)

    quote = (ledgers[0].name[:-len(" Ledger.json")] if ledgers
             else jobs[0].name[:-len(" Job.json")] if jobs else "")
    job_file = (out / f"{quote} Job.json" if (out / f"{quote} Job.json").is_file() else None) if ledgers else (
        jobs[0] if jobs else None)
    state_time = _mtime(state_file) if state_file.is_file() else None     # before the read: never newer than it
    state: dict = _dict(state_file)[0] if state_time is not None else {}
    if (_text(state.get("quote")) and quote and _text(state.get("quote")) != quote) or (
            _text(state.get("job")) and job_name and _text(state.get("job")) != job_name):
        state = {}                  # another job's run state
    running = _text(state.get("status")) == "running"        # the run never ended: of any age
    if not running and not (state_time is not None and (newest_saved is None or state_time >= newest_saved)):
        state = {}                  # an ending is trusted only when no ledger or job was saved after it
    stamps = [_mtime(path) for path in (page, out / f"{quote} Proposal.docx", out / f"{quote} Price Sheet.xlsx")]
    outputs_current = bool(quote) and newest_saved is not None and all(
        stamp is not None and stamp >= newest_saved for stamp in stamps)
    complete = ledger.get("complete") is True

    status, stage = _text(state.get("status")), _text(state.get("stage"))
    asked = state.get("waiting") if isinstance(state.get("waiting"), int) else 0
    said = [m for m in state.get("messages") or [] if isinstance(m, str)] if isinstance(
        state.get("messages"), list) else []
    request_stage = max((r.stage for r in mine if r.stage in _ORDER), key=_ORDER.index, default="")

    lines: list[str] = []
    if running:
        code = 1
        lines.append("Stage: not known. The run has not finished: the last run did not reach the end. It may still "
                     "be going, or it ended with an error; run estimate again to see where it stands.")
    elif status == "done" and outputs_current and not mine:
        code = 0
        lines.append(_DONE)
    elif mine or (status == "waiting" and asked > 0):
        code = 2
        stage = stage or request_stage or "not known"
        if not mine:
            lines.append(f"Stage: {stage}. The run said it waits for {asked} answer(s), but no request was found in "
                         "that cache folder (is --cache the one the run used?).")
        elif waiting:
            more = len(mine) - len(waiting)
            lines.append(f"Stage: {stage}. The run is waiting for {len(waiting)} answer(s)."
                         + (f" {more} more have an answer; run estimate again once all are in." if more else ""))
        else:
            lines.append(f"Stage: {stage}. Every waiting request has an answer: run estimate again to read them.")
        # a request stopped after the most refusals leaves no request file: only the run's own words name it
        lines += [f"  {m}" for m in said if m.startswith("Stopped:")]
    elif status == "waiting":
        code = 1
        lines.append(f"Stage: {stage or 'not known'}. The run stopped, and nothing it asked waits for an answer:")
        lines += [f"  {m}" for m in said] or ["  (the run gave no reason)"]
    elif not state_file.is_file() and outputs_current and complete:
        code = 0                    # a run from before the run state was written: the outputs alone decide
        lines.append(_DONE)
    else:
        code = 1
        if ledger_problem:
            lines.append(f"Stage: read. The ledger {ledgers[0].name} could not be read: {ledger_problem}.")
        elif ledgers and not complete:
            stopped = _text(ledger.get("stopped_at"))
            where = f"at the {stopped} pass" if stopped else "before it was complete"
            lines.append(f"Stage: read. Reading stopped {where}, and no request is waiting for it.")
        elif status == "done":
            lines.append("Stage: done, but the review page, the proposal or the price sheet is missing or older "
                         "than the job; run estimate again.")
        else:
            lines.append(f"Stage: {stage or 'not known'}.")
        lines.append("The run has not finished: no record says the last run ended after it last saved the ledger "
                     "or the job, and no full set of outputs is newer than them. A run may still be going, or it "
                     "ended with an error; run estimate again to see where it stands.")

    lines += _systems(job_file)
    if mine:
        by_kind: dict[str, list[str]] = defaultdict(list)
        answered: dict[str, list[str]] = defaultdict(list)
        for r in mine:
            name = r.system + (" (an earlier answer was refused)" if r.refused_before else "")
            (answered if r.answered else by_kind)[r.kind].append(name)
        lines += [f"Waiting: {len(names)} {kind} request(s): {_names(names)}."
                  for kind, names in sorted(by_kind.items())]
        lines += [f"Answered: {len(names)} {kind} request(s): {_names(names)}; run estimate again to read them."
                  for kind, names in sorted(answered.items())]
    else:
        lines.append("Waiting: no chat requests.")
    if not job_name and requests:
        lines.append("The ledger names no job, so every request in the folder is counted.")
    if others:
        lines.append(f"Not counted: {others} request(s) for other jobs are in the same requests folder.")
    if unreadable:
        lines.append(f"Not read: {unreadable} request file(s) could not be read (one may be being written); "
                     "run status again.")
    lines.append(_refusals(cache))
    lines += _intake(cache)
    lines.append(_findings(page, current=outputs_current))
    return Status(code, tuple(lines))
