"""The AI steps (workstream 5, design §4.5): write, QC and revise, each one prompt plus a JSON Schema; the answer is
checked against the schema (`bms.model.schema_errors`) before `from_dict`.

Two transports share the same steps:
- `ChatTransport` — the old app's chat hand-off, same folder layout and request fields as
  `estimator.writing.judge.Judge` in chat mode, so `tools/run_job.py` and the `/run-job` skill drive it:
  request `<handoff_dir>/requests/<key>.json` = {"key", "kind", "system", "job", "system_prompt", "prompt", **extra,
  "schema", "answer_file"} (and "previous_problem" when an earlier answer was refused, so the next answer can fix
  it); answer `<handoff_dir>/answers/<key>.json`; `handoff_dir` defaults to `<cache>/judge-chat` (the same folder
  the old Judge uses for the reading passes of the same run); answers kept in `<cache>/judge/<key>.json` as
  {"version": 1, "kind", "model": "claude (chat)", "answer"}; `key` is
  `estimator.writing.judge._key(model, prompt, system_prompt)` with model "claude (chat)" (a question with pictures
  adds their fingerprint to the prompt for the key, so a changed picture is a new question); `job` is the dossier's
  `job_name`. On reading a usable answer the request file is deleted (that is how run_job.py tells a used answer
  from a rejected one); an answer a step refuses after the schema check is dropped from the cache and its request
  written again with the reason, the answer file left for run_job.py to count as rejected. The same question is
  not written twice while its request is still waiting, and a cached answer removes a request a killed run left
  behind. The reason an answer was refused is kept with its count, so a re-run with no new answer (or after a
  stop) writes the request with it again. A step that refuses the answer `max_attempts` times
  (`.claude/run-job.json`, else 3) stops: a plain message names the request, and no further request is written.
- `ApiTransport` — the Anthropic SDK (anthropic 1.8.0), streamed, structured output
  (`output_config={"format": {"type": "json_schema", "schema": schema}}`), no temperature, the Playbook rules as
  the first system block with `cache_control: {"type": "ephemeral"}` (prompt caching), the step's own instructions
  as the second; same cache folder and file form under the API model's name; the key from the environment only.
  An answer a step refuses, or one cut off or outside the schema (a network error is not counted), is dropped
  from the cache and the question asked again with the reason, up to `max_attempts` times, then the run stops
  with a plain message naming the request. The retry note is not part of the cache key, so an answer that passes
  on the retry is found by the next run.

Request kinds (what `/run-job` dispatches on): `write_system` for both writing and revising a system (extra
`"step": "write" | "revise"`, `"plan_key": system.key`, `"images"`; a revise request's "system" is the system's name
with " (revise)"; the front end is written and revised as a block of its own, "Front End" and "Front End (revise)",
`plan_key` its key: `write_front_end`, `revise_front_end`), `qc_job` for the QC pass (extra `"step": "qc"`). In chat
mode the request's `system_prompt` is the Playbook rules text, a blank line, then the step's instructions
(`src/bms/prompts/`).

Ground rules the steps hold: every device cites this job's evidence by id (an answer citing an id the evidence does
not carry is refused); the Master Template shape is only the frame (slots and their print form, never a line);
every assumption says what and why; one clarification per block; the skeleton's planner fields always win (a revise
may correct a family's count or the alternate that a must_fix finding about the whole block asks for, checked against
the evidence: the highest count prints and no count is dropped, `_corrections`).
A cosmetic slip in client text (a leading label, a source id) is cleaned on intake instead of refused, and logged
as [{"system", "change"}] in `<cache>/intake.json` (one log per run).
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol, runtime_checkable

from estimator.writing.dossier import Dossier
from estimator.writing.judge import DEFAULT_MODEL, KEY_VARIABLE, MODEL_VARIABLE, _key, _plain

from bms import ai_evidence
from bms.model import (ALTERNATES, Count, Device, Family, Finding, FrontEnd, Job, ModelError, OtherCount, Ref,
                       System, json_schema, schema_errors)
from bms.playbook import Playbook, Shape
from bms.validate import RULE
from bms.citations import WHERE_ADVICE, SourceIds, label_off, plan_refs, ref_sheets, system_tags

WRITE_SYSTEM = "write_system"       # kind of both the write and the revise request
QC_JOB = "qc_job"
STEPS = ("write", "revise")
CHAT_MODEL = "claude (chat)"

CACHE_VERSION = 1
MAX_TOKENS = 64_000                 # the answer plus the model's thinking (always on), streamed
TIMEOUT_SECONDS = 600.0
MAX_IMAGES = 100                    # pictures sent with one question
MAX_IMAGE_BYTES = 5 * 1024 * 1024   # the API takes no bigger picture
QC_PART_LIMIT = 400_000             # characters of job and sources in one QC request; a longer job is split
SOURCE_TEXT_LIMIT = 20_000          # characters of one source's text in a QC request
MAX_PROBLEMS = 8                    # problems named in a refusal
PROMPTS = Path(__file__).resolve().parent / "prompts"
LATE_DEVICE_FIELDS = {"mark": "", "mark_note": ""}     # Device fields added later (T-005c/T-005d): missing is empty
LATE_FIELDS = {"no_scope_reason": None, "serves": []}  # System fields added after answers were written: missing
#                                                       means this value
CITES_RULE = RULE["cites"]          # the rule the mechanical quote check reports under
SKELETON_FIELDS = ("key", "name", "shape", "control", "families", "sequence_refs", "alternate", "serves")
INTAKE_FILE = "intake.json"         # beside the cache: what the intake cleaned in this run's answers


def _instructions(name: str) -> str:
    return (PROMPTS / f"{name}.md").read_text(encoding="utf-8").strip()


class NoAnswer(Exception):
    """A step has no answer: `waiting` True when a chat request is written and waits for its answer (the run
    finishes writing the other requests, then stops); False when the AI failed (`reason` in plain words)."""

    def __init__(self, reason: str, waiting: bool = False):
        super().__init__(reason)
        self.reason = reason
        self.waiting = waiting


class _BadAnswer(NoAnswer):
    """The API answered, but the answer cannot be used (cut off, declined, not JSON, not in the schema). It is
    counted as a refusal and asked again with the reason, unlike a network error or a timeout."""


@runtime_checkable
class Transport(Protocol):
    """How a step's question reaches the AI and its answer comes back."""

    waiting: int                    # chat requests written on this run and still to answer
    last_error: str | None

    def ask(self, kind: str, name: str, instructions: str, system_prompt: str, prompt: str, schema: dict,
            extra: dict | None = None, images: Sequence[Path] = ()) -> dict:
        """The answer (a dict that fits `schema`, as the AI gave it) to one question. `kind` is WRITE_SYSTEM or
        QC_JOB; `name` the request's "system" (the system's name, or "QC"); `instructions` the Playbook rules text
        (cached); `system_prompt` the step's instructions; `extra` goes into the chat request as is; `images` are
        PNG paths (API: image blocks; chat: listed in the request). Cached by model and exact question: the same
        question never costs twice. Raises NoAnswer (waiting in chat mode, or a failure)."""
        ...


# ---- what both transports share: the question, its key and the cache ------------------------------------------

@dataclass(frozen=True)
class _Question:
    kind: str
    name: str
    instructions: str
    system_prompt: str
    prompt: str
    schema: dict
    extra: dict
    images: tuple[Path, ...]
    key: str
    model: str = ""

    @property
    def full_system_prompt(self) -> str:
        """The Playbook rules, a blank line, the step's instructions (the chat request's `system_prompt`)."""
        return f"{self.instructions}\n\n{self.system_prompt}"


def _fingerprint(images: Sequence[Path]) -> str:
    """What the pictures are, for the key: a changed picture is a new question."""
    if not images:
        return ""
    parts = []
    for path in images:
        try:
            digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        except OSError:
            digest = "missing"
        parts.append(f"{Path(path).name} {digest}")
    return "\n\nPictures:\n" + "\n".join(parts)


def _question(model: str, kind: str, name: str, instructions: str, system_prompt: str, prompt: str, schema: dict,
              extra: dict | None, images: Sequence[Path]) -> _Question:
    images = tuple(Path(p) for p in images or ())
    # The API's retry note is not part of the key: an answer that passes on the retry is the answer to the
    # question itself, found by the next run, and a refusal drops it from the one place it is kept.
    key = _key(model, _without_retry(prompt) + _fingerprint(images), f"{instructions}\n\n{system_prompt}")
    return _Question(kind, name, instructions, system_prompt, prompt, schema, dict(extra or {}), images, key, model)


def _write_json(path: Path, data, indent: int | None = None) -> None:
    """Written whole or not at all: to a temporary name first, then swapped into place."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=indent), encoding="utf-8")
    os.replace(tmp, path)


class _Cache:
    """Answers kept by key in `<cache>/judge/<key>.json` as {"version": 1, "kind", "model", "answer"}."""

    def __init__(self, folder: Path) -> None:
        self.folder = Path(folder)

    def file(self, q: _Question) -> Path:
        return self.folder / f"{q.key}.json"

    def read(self, q: _Question) -> dict | None:
        try:
            data = json.loads(self.file(q).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if (not isinstance(data, dict) or data.get("version") != CACHE_VERSION or data.get("kind") != q.kind
                or schema_errors(data.get("answer"), q.schema)):
            return None
        return data["answer"]

    def write(self, q: _Question, model: str, answer: dict) -> None:
        try:
            _write_json(self.file(q), {"version": CACHE_VERSION, "kind": q.kind, "model": model, "answer": answer})
        except OSError:
            pass                    # a cache that cannot be written only costs a second question next time

    def drop(self, q: _Question) -> None:
        try:
            self.file(q).unlink(missing_ok=True)
        except OSError:
            pass


def _max_attempts() -> int:
    """How many times a step may refuse one request before the run stops. The estimator's knob in
    `.claude/run-job.json`, else 3."""
    path = Path(__file__).resolve().parents[2] / ".claude" / "run-job.json"
    try:
        value = int(json.loads(path.read_text(encoding="utf-8")).get("max_attempts", 3))
    except (OSError, ValueError, TypeError):
        return 3
    return value if value >= 1 else 3


_RETRY_MARK = "\n\nYour earlier answer to this question could not be used:"


def _without_retry(prompt: str) -> str:
    """The prompt as first asked: the API's retry note taken off."""
    mark = prompt.find(_RETRY_MARK)
    return prompt[:mark] if mark != -1 else prompt


def _attempt_file(cache: _Cache, q: _Question) -> Path:
    """One counter per question. The prompt, the model, the Playbook rules text, the step's instructions and the
    answer's schema are part of the id, so a decision rewrite, new evidence, a fixed rules.md or another model does
    not share the first write's counter. The API's one immediate retry appends a fixed note; that note is not part
    of the id, so the retry keeps counting."""
    prompt = _without_retry(q.prompt)
    asked = hashlib.sha256("|".join((q.model, q.instructions, q.system_prompt,
                                    json.dumps(q.schema, sort_keys=True))).encode()).hexdigest()
    ident = f"{q.kind}|{q.extra.get('step', '')}|{q.name}|{q.extra.get('plan_key', '')}|{asked}|{prompt}"
    digest = hashlib.sha256(ident.encode()).hexdigest()
    return cache.folder / "attempts" / f"{digest}.json"


def _refusal_count(transport) -> int:
    cache, last = getattr(transport, "cache", None), getattr(transport, "_last", None)
    if cache is None or last is None:
        return 0
    try:
        data = json.loads(_attempt_file(cache, last).read_text(encoding="utf-8"))
        return int(data.get("attempts", 0))
    except (OSError, ValueError, TypeError):
        return 0


def _mtime_ns(path: Path) -> int | None:
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return None


def _answer_path(transport) -> Path | None:
    last = getattr(transport, "_last", None)
    answers = getattr(transport, "answers_dir", None)
    if last is None or answers is None:
        return None
    return Path(answers) / f"{last.key}.json"


def _rejected_answer_mtime(transport) -> int | None:
    """The mtime of the answer file last refused for this request, if one was recorded."""
    cache, last = getattr(transport, "cache", None), getattr(transport, "_last", None)
    if cache is None or last is None:
        return None
    try:
        data = json.loads(_attempt_file(cache, last).read_text(encoding="utf-8"))
        value = data.get("answer_mtime_ns")
        return int(value) if value is not None else None
    except (OSError, ValueError, TypeError):
        return None


def _saved_problem(transport) -> str | None:
    """Why the last answer to this request was refused, as saved with the count; a chat re-run with no new
    answer writes the request again with it."""
    cache, last = getattr(transport, "cache", None), getattr(transport, "_last", None)
    if cache is None or last is None:
        return None
    try:
        problem = json.loads(_attempt_file(cache, last).read_text(encoding="utf-8")).get("problem")
    except (OSError, ValueError, TypeError, AttributeError):
        return None
    return problem if isinstance(problem, str) and problem else None


def _record_refusal(transport, problem: str | None = None) -> int:
    cache, last = getattr(transport, "cache", None), getattr(transport, "_last", None)
    count = _refusal_count(transport) + 1
    if cache is not None and last is not None:
        payload: dict = {"attempts": count}
        problem = problem or _saved_problem(transport)
        if problem:
            payload["problem"] = problem
        path = _answer_path(transport)
        mtime = _mtime_ns(path) if path is not None else None
        if mtime is not None:
            payload["answer_mtime_ns"] = mtime
        try:
            _write_json(_attempt_file(cache, last), payload)
        except OSError:
            pass
    return count


def _clear_attempts(transport) -> None:
    cache, last = getattr(transport, "cache", None), getattr(transport, "_last", None)
    if cache is None or last is None:
        return
    try:
        _attempt_file(cache, last).unlink(missing_ok=True)
    except OSError:
        pass


def _answer_is_fresh(transport, answer_file: Path, request_file: Path) -> bool:
    """A chat answer counts only when it is newer than the request that asked for it and newer than the answer
    already refused. `refuse` leaves the old file in place; reading it again would burn an attempt."""
    answer_mtime = _mtime_ns(answer_file)
    if answer_mtime is None:
        return False
    if request_file.is_file():
        request_mtime = _mtime_ns(request_file)
        if request_mtime is not None and answer_mtime <= request_mtime:
            return False
    rejected = _rejected_answer_mtime(transport)
    return rejected is None or answer_mtime > rejected


def _restart_attempts_for_new_answer(transport, answer_file: Path) -> None:
    """After the run has stopped, one newer answer file gets a fresh set of attempts. The same file does not:
    a re-run with nothing new waits, it does not stop again."""
    if _refusal_count(transport) < _max_attempts():
        return
    rejected = _rejected_answer_mtime(transport)
    answer_mtime = _mtime_ns(answer_file)
    if rejected is not None and answer_mtime is not None and answer_mtime > rejected:
        _clear_attempts(transport)


def _drop_refused(transport) -> None:
    """The refused answer leaves the cache, and a chat request still on disk is not asked again. A stop also
    removes the answer file. The attempt counter stays until that file is deleted or a newer answer arrives."""
    last = getattr(transport, "_last", None)
    cache = getattr(transport, "cache", None)
    if last is not None and cache is not None:
        cache.drop(last)
    requests = getattr(transport, "requests_dir", None)
    if last is not None and requests is not None:
        try:
            (Path(requests) / f"{last.key}.json").unlink(missing_ok=True)
        except OSError:
            pass
    answer = _answer_path(transport)
    if answer is not None:
        try:
            answer.unlink(missing_ok=True)
        except OSError:
            pass


def _stop_reason(name: str, attempts: int, reason: str, counter: Path | None = None, *, chat: bool = False) -> str:
    """The stop, in sentences. In chat mode the next run writes the request again by itself, and only an answer
    newer than the one last refused is read (it gets a fresh set of attempts); the API asks again only once the
    counter file is deleted."""
    reason = str(reason).strip().rstrip(".")
    reason = reason[:1].upper() + reason[1:]
    if chat:
        where = (" The next run asks this question again by itself; only an answer saved after the one last refused "
                 "is read, and it starts a new count.")
        if counter is not None:
            where += f" The refusals are counted in {counter}."
    else:
        where = f" To ask this question again, delete {counter}." if counter is not None else ""
    changed = "new evidence, a changed Playbook" if chat else "new evidence, a changed Playbook, another model"
    return (f"Stopped: the request {name} was refused {attempts} times. {reason}.{where}"
            f" A changed question ({changed}) starts a new count.")


def _is_chat(transport) -> bool:
    """A chat transport writes request files for the next run (`requests_dir`); the API asks at once."""
    return getattr(transport, "requests_dir", None) is not None


def _problems(errors: list[str]) -> str:
    shown = "; ".join(errors[:MAX_PROBLEMS])
    return shown + (f"; and {len(errors) - MAX_PROBLEMS} more" if len(errors) > MAX_PROBLEMS else "")


class _IntakeLog:
    """What the intake cleaned in this run's answers (a label taken off, a source id put in words), kept as
    [{"system", "change"}] in `<cache>/intake.json`; a new transport (a new run) starts a new log."""

    intake: list[dict]

    def _start_intake(self, cache_dir: Path) -> None:
        self.intake = []
        self.intake_file = Path(cache_dir) / INTAKE_FILE
        try:
            self.intake_file.unlink(missing_ok=True)
        except OSError:
            pass

    def note_intake(self, system: str, change: str) -> None:
        self.intake.append({"system": system, "change": change})
        try:
            _write_json(self.intake_file, self.intake, indent=2)
        except OSError:
            pass


# ---- the chat transport -----------------------------------------------------------------------------------------

class ChatTransport(_IntakeLog):
    """Questions as request files for the chat; answers read back on the next run (see the module doc)."""

    def __init__(self, cache_dir: Path, job: str, handoff_dir: Path | None = None) -> None:
        """`cache_dir` is the run's cache (answers kept in `cache_dir/judge`); `handoff_dir` defaults to
        `cache_dir/judge-chat`; `job` is `dossier.job_name`."""
        self._start_intake(cache_dir)
        self.cache = _Cache(Path(cache_dir) / "judge")
        self.handoff_dir = Path(handoff_dir) if handoff_dir is not None else Path(cache_dir) / "judge-chat"
        self.job = job
        self.model = CHAT_MODEL
        self.waiting = 0
        self.last_error: str | None = None
        self.cached = 0
        self.answered_in_chat = 0
        self._last: _Question | None = None

    waiting: int
    last_error: str | None

    @property
    def requests_dir(self) -> Path:
        return self.handoff_dir / "requests"

    def _drop_request(self, key: str) -> None:
        """Remove this question's request, and the copy a new run parked in requests/old/."""
        for path in (self.requests_dir / f"{key}.json", self.requests_dir / "old" / f"{key}.json"):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass

    @property
    def answers_dir(self) -> Path:
        return self.handoff_dir / "answers"

    def ask(self, kind: str, name: str, instructions: str, system_prompt: str, prompt: str, schema: dict,
            extra: dict | None = None, images: Sequence[Path] = ()) -> dict:
        q = _question(self.model, kind, name, instructions, system_prompt, prompt, schema, extra, images)
        self._last = q
        cached = self.cache.read(q)
        if cached is not None:
            self.cached += 1
            self.last_error = None
            self._drop_request(q.key)   # a killed run may have left it, including the copy parked in old/
            return cached
        answer_file = self.answers_dir / f"{q.key}.json"
        request_file = self.requests_dir / f"{q.key}.json"
        problem = None
        if answer_file.is_file() and _answer_is_fresh(self, answer_file, request_file):
            _restart_attempts_for_new_answer(self, answer_file)
            answer, errors = _read_answer(answer_file, q.schema)
            if answer is not None:
                self.cache.write(q, CHAT_MODEL, answer)
                self._drop_request(q.key)
                self.answered_in_chat += 1
                self.last_error = None
                return answer
            problem = f"the answer for {name} could not be read: {_problems(errors)}"
            attempts = _record_refusal(self, problem)
            if attempts >= _max_attempts():
                counter = _attempt_file(self.cache, q) if self.cache is not None else None
                _drop_refused(self)
                self.last_error = _stop_reason(name, attempts, problem, counter, chat=True)
                raise NoAnswer(self.last_error, waiting=False)
        if problem is None:                 # nothing new: the request keeps the reason the last answer was refused
            problem = _saved_problem(self)
        raise self._request(q, problem)

    def refuse(self, problem: str) -> bool:
        """The last answer could not be used (`problem`): it leaves the cache and its request is written again
        with the reason, the answer file left in place for run_job.py to count as rejected. False: the chat
        answers on a later run."""
        if self._last is None:
            return False
        self.cache.drop(self._last)
        self._request(self._last, problem)
        return False

    def _request(self, q: _Question, problem: str | None) -> NoAnswer:
        request = self.requests_dir / f"{q.key}.json"
        answer_file = self.answers_dir / f"{q.key}.json"
        data = {"key": q.key, "kind": q.kind, "system": q.name, **({"job": self.job} if self.job else {}),
                "system_prompt": q.full_system_prompt, "prompt": q.prompt, **q.extra}
        if q.images and "images" not in q.extra:
            data["images"] = [str(p) for p in q.images]
        data |= {"schema": q.schema, "answer_file": str(answer_file)}
        if problem:
            data["previous_problem"] = problem
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        old = self.requests_dir / "old" / request.name
        # A new run parks this job's requests in old/ and would write them again. An unchanged request
        # goes back where it was, so the file and its mtime stay and nothing is left in old/.
        if not request.is_file() and old.is_file():
            try:
                if old.read_text(encoding="utf-8") == payload:
                    os.replace(old, request)
            except OSError:
                pass
        if request.is_file():
            try:
                same = request.read_text(encoding="utf-8") == payload
            except OSError:
                same = False
            if same:                                 # still waiting: do not ask this question a second time
                try:
                    (self.requests_dir / "old" / request.name).unlink(missing_ok=True)
                except OSError:
                    pass
                self.waiting += 1
                waiting = f"waiting for an answer in the chat (requests folder: {request.parent})"
                self.last_error = f"{problem}; asked again, {waiting}" if problem else waiting
                return NoAnswer(self.last_error, waiting=True)
        try:
            _write_json(request, data, indent=2)
            try:
                (self.requests_dir / "old" / request.name).unlink(missing_ok=True)  # asked again: no longer stale
            except OSError:
                pass
        except OSError:
            self.last_error = f"the request for {q.name} could not be written to {request.parent}"
            return NoAnswer(self.last_error, waiting=False)
        self.waiting += 1
        waiting = f"waiting for an answer in the chat (requests folder: {request.parent})"
        self.last_error = f"{problem}; asked again, {waiting}" if problem else waiting
        return NoAnswer(self.last_error, waiting=True)


def _late_device_fields(answer, schema: dict) -> None:
    """Fill the Device fields added to the contract after answers were written (`LATE_DEVICE_FIELDS`), in place, on
    each device of a System answer whose schema has them: a cached answer from before stays usable."""
    if not isinstance(answer, dict):
        return
    try:
        device_schema = schema["properties"]["devices"]["items"]["properties"]
    except (KeyError, TypeError):
        return
    for device in answer.get("devices") or ():
        if isinstance(device, dict):
            for name, empty in LATE_DEVICE_FIELDS.items():
                if name in device_schema and name not in device:
                    device[name] = empty
            if isinstance(device.get("mark"), str):         # "Future" is "future": a slip of case, not a refusal
                device["mark"] = device["mark"].strip().lower()


def _read_answer(path: Path, schema: dict) -> tuple[dict | None, list[str]]:
    try:
        answer = json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError:
        return None, ["the answer file cannot be opened"]
    except ValueError:
        return None, ["the answer is not valid JSON"]
    if isinstance(answer, dict):
        for name, empty in LATE_FIELDS.items():     # a field added to the contract later: missing means empty
            if name in schema.get("properties", {}) and name not in answer:
                answer[name] = json.loads(json.dumps(empty))
    _late_device_fields(answer, schema)
    errors = schema_errors(answer, schema)
    return (None, errors) if errors else (answer, [])


# ---- the API transport ------------------------------------------------------------------------------------------

class ApiTransport(_IntakeLog):
    """Questions through the Anthropic API, with the Playbook cached (see the module doc)."""

    def __init__(self, cache_dir: Path, model: str | None = None, client=None) -> None:
        """`model` defaults to $ESTIMATOR_MODEL, else `estimator.writing.judge.DEFAULT_MODEL`; `client` is an
        `anthropic.Anthropic` (made from the environment when None; tests pass a fake)."""
        self._start_intake(cache_dir)
        self.cache = _Cache(Path(cache_dir) / "judge")
        self.model = model or os.environ.get(MODEL_VARIABLE) or DEFAULT_MODEL
        self._client = client
        self.waiting = 0
        self.last_error: str | None = None
        self.calls = 0
        self.cached = 0
        self._last: _Question | None = None

    waiting: int
    last_error: str | None

    def ask(self, kind: str, name: str, instructions: str, system_prompt: str, prompt: str, schema: dict,
            extra: dict | None = None, images: Sequence[Path] = ()) -> dict:
        q = _question(self.model, kind, name, instructions, system_prompt, prompt, schema, extra, images)
        self._last = q
        cached = self.cache.read(q)
        if cached is not None:
            self.cached += 1
            self.last_error = None
            return cached
        attempts = _refusal_count(self)            # the saved count: a stopped question is not asked again
        limit = getattr(self, "max_attempts", None) or _max_attempts()
        if attempts >= limit:
            self.last_error = _stop_reason(name, attempts, "It is not asked again", _attempt_file(self.cache, q))
            raise NoAnswer(self.last_error, waiting=False)
        try:
            response = self._call(q)
            answer = _answer_of(response, q)
        except _BadAnswer as bad:           # an unusable answer is a refusal: counted, and asked again with the reason
            attempts = _record_refusal(self, bad.reason)
            if attempts >= limit:
                self.last_error = _stop_reason(name, attempts, bad.reason, _attempt_file(self.cache, q))
                raise NoAnswer(self.last_error, waiting=False) from None
            self.last_error = bad.reason
            raise
        except NoAnswer as failed:
            self.last_error = failed.reason
            raise
        except Exception as error:          # the API's own errors, in plain words
            self.last_error = f"{q.name}: {_plain(error)}"
            raise NoAnswer(self.last_error) from None
        self.cache.write(q, getattr(response, "model", None) or self.model, answer)
        self.calls += 1
        self.last_error = None
        return answer

    def refuse(self, problem: str) -> bool:
        """The last answer could not be used: it leaves the cache. True: the step may ask again now."""
        if self._last is not None:
            self.cache.drop(self._last)
        self.last_error = problem
        return True

    def _client_or_none(self):
        if self._client is None:
            if not os.environ.get(KEY_VARIABLE):
                return None
            import anthropic
            # The SDK finds the key in the environment itself; it is never read, printed or stored here.
            self._client = anthropic.Anthropic(timeout=TIMEOUT_SECONDS)
        return self._client

    def _call(self, q: _Question):
        client = self._client_or_none()
        if client is None:
            raise NoAnswer(f"{q.name}: no AI key set ({KEY_VARIABLE}); use the chat mode or set the key")
        params = dict(model=self.model, max_tokens=MAX_TOKENS,
                      system=[{"type": "text", "text": q.instructions, "cache_control": {"type": "ephemeral"}},
                              {"type": "text", "text": q.system_prompt}],
                      messages=[{"role": "user", "content": _content(q.prompt, q.images)}],
                      output_config={"format": {"type": "json_schema", "schema": q.schema}},
                      timeout=TIMEOUT_SECONDS)
        messages = client.messages
        if hasattr(messages, "stream"):
            with messages.stream(**params) as stream:
                return stream.get_final_message()
        return messages.create(**params)


def _content(prompt: str, images: Sequence[Path]) -> list[dict]:
    """The user message: the prompt, then each picture after its caption (a base64 PNG); a picture that cannot be
    read, or is too big to send, is named in words instead."""
    blocks: list[dict] = [{"type": "text", "text": prompt}]
    for path in list(images)[:MAX_IMAGES]:
        caption = f"Picture file {Path(path).name}"
        try:
            data = Path(path).read_bytes()
        except OSError:
            blocks.append({"type": "text", "text": f"{caption}: the picture could not be read."})
            continue
        if len(data) > MAX_IMAGE_BYTES:
            blocks.append({"type": "text", "text": f"{caption}: the picture is too big to send."})
            continue
        blocks.append({"type": "text", "text": caption})
        blocks.append({"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                   "data": base64.standard_b64encode(data).decode("ascii")}})
    if len(images) > MAX_IMAGES:
        blocks.append({"type": "text", "text": f"{len(images) - MAX_IMAGES} more pictures could not be sent."})
    return blocks


def _answer_of(response, q: _Question) -> dict:
    stop = getattr(response, "stop_reason", None)
    if stop == "max_tokens":
        raise _BadAnswer(f"{q.name}: the AI answer was cut off before it finished")
    if stop == "refusal":
        raise _BadAnswer(f"{q.name}: the AI declined to answer")
    text = "".join(getattr(block, "text", "") for block in getattr(response, "content", ())
                   if getattr(block, "type", None) == "text")
    try:
        answer = json.loads(text)
    except ValueError:
        raise _BadAnswer(f"the answer for {q.name} could not be read: it is not valid JSON") from None
    if isinstance(answer, dict):
        for name, empty in LATE_FIELDS.items():     # a field added to the contract later: missing means empty
            if name in q.schema.get("properties", {}) and name not in answer:
                answer[name] = json.loads(json.dumps(empty))
    _late_device_fields(answer, q.schema)
    errors = schema_errors(answer, q.schema)
    if errors:
        raise _BadAnswer(f"the answer for {q.name} could not be read: {_problems(errors)}")
    return answer


# ---- asking with the step's own checks -----------------------------------------------------------------------------

def _ask_checked(transport, kind: str, name: str, instructions: str, system_prompt: str, prompt: str, schema: dict,
                 extra: dict, images: Sequence[Path], check: Callable[[dict], tuple[object, list[str]]],
                 max_attempts: int | None = None):
    """Ask; run the step's `check` (value, problems) on the answer. An answer with problems is refused: the chat
    asks again on a later run (NoAnswer waiting); the API is asked once more now, with the reason. After
    `max_attempts` refusals the run stops with a plain message naming the request, and nothing is asked again."""
    prompt_now = prompt
    retried = False
    limit = max_attempts or getattr(transport, "max_attempts", None) or _max_attempts()
    while True:
        try:
            answer = transport.ask(kind, name, instructions, system_prompt, prompt_now, schema, extra, images)
        except _BadAnswer as bad:           # the API's answer was unusable: already counted, asked once more now
            if retried:
                raise NoAnswer(bad.reason) from None
            retried = True
            prompt_now = f"{prompt}{_RETRY_MARK} {bad.reason}. Answer again, fixing that."
            continue
        value, problems = check(answer)
        if not problems:
            _clear_attempts(transport)
            return value
        reason = f"the answer for {name} could not be used: {_problems(problems)}"
        counter = None
        cache, last = getattr(transport, "cache", None), getattr(transport, "_last", None)
        if cache is not None and last is not None:
            counter = _attempt_file(cache, last)
        if _refusal_count(transport) >= limit:
            _drop_refused(transport)
            raise NoAnswer(_stop_reason(name, limit, reason, counter, chat=_is_chat(transport)), waiting=False)
        attempts = _record_refusal(transport, reason)
        if attempts >= limit:
            _drop_refused(transport)
            raise NoAnswer(_stop_reason(name, attempts, reason, counter, chat=_is_chat(transport)), waiting=False)
        refuse = getattr(transport, "refuse", None)
        if refuse is None:
            raise NoAnswer(reason)
        if not refuse(reason):
            raise NoAnswer(reason + " (asked again)", waiting=True)
        if retried:                         # the API's one immediate retry already happened
            raise NoAnswer(reason)
        retried = True
        prompt_now = f"{prompt}{_RETRY_MARK} {_problems(problems)}. Answer again, fixing that."


# ---- the evidence ------------------------------------------------------------------------------------------------

def evidence_for(system: System, dossier: Dossier) -> str:
    """The evidence one system is written from: the dossier lines its refs, family tags and sequence refs point to,
    each kept with its "[S41]" source id and place, so the AI cites them by id. Only this job's text; no example
    from another job. Deterministic.

    In order: the ledger facts the planner cited (ids the dossier text does not carry); the sequence sections the
    planner cited, whole, and the sequence paragraphs naming its tags or names; its points list rows; its schedule
    rows under their schedule's title with the schedule's notes; its equipment counts and the devices counted on the
    sheets it is on; the notes naming it; the controls spec passages about it (and about integration, for a packaged
    or integrated system); the job's who-does-what passages; anything else cited; then each picture it cites or its
    passages name, as "[I3] Picture: <what>. File: <path>" (write_system attaches those files).

    When the dossier carries the reading's schedule objects, each included schedule is a small table — its columns,
    then the rows for this system's tags — instead of the flat dossier lines. The source id stays at the start of
    the title, of each row and of each note.

    T-005d: a controls sheet's own text (its title names controls, a sequence, points or a diagram) comes first among
    the notes and whole; another long plan sheet's text is given as excerpts about the system; a note repeated word
    for word is given once. Then the checklists: the passages that mark an item FUTURE or furnished integral with the
    unit, the end devices its unit schedules list, and, with `ledger`, the controls facts the reading found about it
    (the coverage gate's facts), so each one ends as a line, the clarification or the no-scope reason. `front_end`:
    the front end's evidence (its notes are those in the front end's own words)."""
    return system_evidence(system, dossier)


def system_evidence(system: System, dossier: Dossier, ledger=None, *, front_end: bool = False) -> str:
    """`evidence_for` with the reading's ledger (T-005d): the same passages, then the checklist of the controls facts
    the reading found about the system, so the writer ends each as a line, the clarification or the no-scope reason
    (the coverage gate reports what is still uncited after). `front_end`: the front end's evidence."""
    return ai_evidence.evidence(system, dossier.text, dict(dossier.sources or {}),
                                _sections_of(dossier), dossier.images, dossier.schedules, ledger=ledger,
                                front_end=front_end)


def _sections_of(dossier: Dossier) -> dict:
    """The dossier's sequence sections, read from its text when it carries none."""
    sections = dossier.sections or {}
    if not sections:
        from estimator.writing.dossier import sections_in
        sections = sections_in(dossier.text or "")
    return dict(sections)


def evidence_index(dossier: Dossier) -> dict[str, str]:
    """Every source id of the dossier ("S41", "I2", "Q7") -> its text (a picture: its description), for the QC
    pass to check that each Ref's quote is in its source."""
    return ai_evidence.index(dossier.text, dict(dossier.sources or {}), _sections_of(dossier))


# ---- write and revise: the prompt and the checks of a System answer -------------------------------------------------

def _shape(system: System, playbook: Playbook) -> Shape | None:
    return playbook.shapes.get(system.shape) if system.shape else None


def _skeleton_dict(system: System) -> dict:
    data = system.to_dict()
    return {name: data[name] for name in SKELETON_FIELDS}


def _shape_text(system: System, shape: Shape | None) -> str:
    if shape is None:
        missing = (f" (its shape {system.shape!r} is not in the Playbook)" if system.shape else "")
        return (f"No shape: this system has no Playbook shape{missing}, so it is an untemplated system. Name each "
                "slot yourself (short lower-case words joined by underscores that say what the line is); its lines "
                "print as \"{verb} {device}{owner}{qty}\".")
    lines = [f"The shape of its block: {shape.name}",
             f"Header form: {shape.header}",
             "Slots, in print order (slot, its kind, how its line prints):"]
    lines += [f"- {slot} ({shape.slot_kinds[slot]}): {shape.wording[slot]}"
              + (f" [sub-line under {shape.under[slot]}: printed one level in under that line, no verb; the "
                 f"device inherits the {shape.under[slot]} device's ownership]" if slot in shape.under else "")
              for slot in shape.line_order]
    th = shape.tech_hours
    rule = f"{th.hours:g} hours per {th.per.replace('_', ' ')}" if th.hours is not None else \
        f"no hours per {th.per.replace('_', ' ')} unless a condition below holds"
    for slots, hours in th.when:
        rule += f"; {hours:g} hours when the block has a device in each of: {', '.join(slots)}"
    lines.append(f"Tech hours rule: {rule}.")
    lines.append("The shape is only the frame: it says how a line prints and in what order, never that a line "
                 "exists.")
    return "\n".join(lines)


def _pictures(evidence: str) -> tuple[list[Path], list[dict]]:
    found = ai_evidence.pictures(evidence)
    return ([Path(path) for _, _, path in found],
            [{"id": pid, "path": path, "what": what} for pid, what, path in found])


def _write_prompt(system: System, shape: Shape | None, evidence: str) -> str:
    skeleton = {k: v for k, v in _skeleton_dict(system).items() if k != "serves"}   # said in words below
    return "\n\n".join(p for p in [
        "The system, as the planner set it up (copy these fields as they are):\n"
        + json.dumps(skeleton, indent=1, ensure_ascii=False),
        _shape_text(system, shape),
        _heater_text(system),
        f"Answer with the whole system as JSON in the schema given; number the devices {system.key}.d1, "
        f"{system.key}.d2 and so on, in print order.",
        "The evidence:\n" + evidence.strip()] if p)


# ---- duct heaters in one place -------------------------------------------------------------------------------------

_HEATER_LINE = re.compile(r"duct[\s_-]*heater", re.I)
FULL_HEATER_SCOPE = "discharge air temperature sensor, enable or SCR signal, status and alarm"


def _heats(system: System) -> list:
    """The units this duct heater block serves (empty when it is not one)."""
    return [s for s in system.serves if s.heater_key == system.key]


def _heated_by(system: System) -> list:
    """This unit's entries naming the duct heater block that writes its heaters."""
    return [s for s in system.serves if s.key == system.key and s.heater_key != system.key]


def _heater_tags(system: System) -> list[str]:
    return [t for f in system.families for t in f.tags]


def _heater_text(system: System) -> str:
    """What the writer is told about duct heaters: the heater block writes every heater, the served unit none."""
    heats, heated = _heats(system), _heated_by(system)
    if heats:
        tags = ", ".join(_heater_tags(system)) or "its heaters"
        counts = [f.count.value for f in system.families]
        count = f"{sum(counts)} in all" if counts and None not in counts else "count as the families give it"
        lines = [f"Duct heaters: this is the duct heater block. Every duct heater of this job is written here and "
                 f"only here: write the heater lines for ALL its heaters ({tags}; {count}), never an empty block. "
                 "Its heaters serve these units:"]
        for unit in heats:
            which = ", ".join(unit.heaters) or "the documents do not say which heaters"
            on = f"; tags {', '.join(unit.tags)}" if unit.tags else ""
            lines.append(f"- {unit.name} (block {unit.key}{on}): {which}")
        lines.append(
            "For each served unit: when a sentence of the sequence of operation gives the BMS the control of its "
            f"duct heater, write the heater's full field DDC scope ({FULL_HEATER_SCOPE}); when no sentence does, "
            "write only the interlock of the heater to the served unit (the heater comes packaged on its own "
            "controls). Each heater line's quantity is the heater count: the family's count, copied whole, when "
            "every heater takes the same lines; else the number of heaters the line covers. Write no heater line "
            "in a served unit's block: they are all here.")
        return "\n".join(lines)
    if heated:
        return "\n".join(
            f"Duct heaters: the duct heaters serving this unit ({', '.join(s.heaters) or 'its duct heaters'}) are "
            f"written in the {s.heater_name} block; write no duct heater line here (no heater sensor, enable or SCR "
            "signal, status, alarm or interlock)." for s in heated)
    return ""


def _heater_problems(system: System, devices: list[dict], kept: set[str] = frozenset()) -> list[str]:
    """A duct heater block with no line; a duct heater line (not one kept as it was) in a served unit's block."""
    if _heats(system) and not devices:
        return [f"this is the duct heater block and it has no lines: write the heater lines for all its heaters "
                f"({', '.join(_heater_tags(system)) or 'every heater'}) here"]
    problems = []
    for entry in _heated_by(system):
        named = [*entry.heaters, *{t.split("-")[0] for t in entry.heaters if "-" in t}]
        for n, device in enumerate(devices):
            if device.get("id") in kept:
                continue
            words = f"{device.get('slot', '')} {device.get('name', '')}"
            if _HEATER_LINE.search(words) or any(re.search(rf"(?<![A-Za-z0-9]){re.escape(t)}(?![A-Za-z0-9])",
                                                           words, re.I) for t in named if t):
                problems.append(f"device {device.get('id') or n + 1} is a duct heater line: the duct heaters "
                                f"serving this unit are written in the {entry.heater_name} block; leave it out here")
    return problems


def _finding_text(n: int, finding: Finding) -> str:
    about = f"device {finding.device_id}" if finding.device_id else "the whole block"
    return f"{n}. [{finding.rule}] {about}: {finding.what} Fix: {finding.fix}"


def _revise_prompt(system: System, findings: Sequence[Finding], shape: Shape | None, evidence: str,
                   revise: frozenset[str] = frozenset(), hold: frozenset[str] = frozenset()) -> str:
    return "\n\n".join(p for p in [
        "The block as written:\n" + json.dumps({k: v for k, v in system.to_dict().items() if k != "serves"},
                                               indent=1, ensure_ascii=False),
        "The findings to fix (must fix), and nothing else:\n"
        + "\n".join(_finding_text(n, f) for n, f in enumerate(findings, start=1)),
        _corrections_text(revise, hold),
        _shape_text(system, shape),
        _heater_text(system),
        "Answer with the whole revised system as JSON in the schema given.",
        "The evidence:\n" + evidence.strip()] if p)


def _ref_ids(refs) -> set[str]:
    """The source ids the refs cite; an empty id (a count record given without a source) is no id."""
    return {sid for sid in (str(r.source_id).strip().strip("[]") for r in refs) if sid}


def _all_refs(system: System) -> list[Ref]:
    refs = ai_evidence.system_refs(system)
    for device in system.devices:
        refs += list(device.refs) + list(device.quantity.sources) + [o.ref for o in device.quantity.others]
    return refs


def _sent_index(evidence: str) -> dict[str, str]:
    """Every source id of the evidence one system was sent -> its text there (a sequence section: its heading and
    the paragraphs under it, never the blocks after it), for the intake's quote check."""
    from estimator.writing.dossier import sections_in
    sections: dict = {}
    for block in (evidence or "").split("\n\n"):     # each block of the evidence follows an empty line
        sections |= sections_in(block)
    return ai_evidence.index(evidence, {}, sections)


def _quote_problem(ref: dict, index: Mapping[str, str]) -> str | None:
    """A ref whose quote is not in its source's text as the evidence gave it (a picture, the plan count check's own
    record and an id the evidence does not carry aside: the id check refuses that one)."""
    from bms.counts import LOCATED_QUOTE, NO_SOURCE_QUOTE, SEEN_QUOTE
    sid = str(ref.get("source_id", "")).strip().strip("[]")
    quote = ref.get("quote", "")
    if quote in (LOCATED_QUOTE, SEEN_QUOTE, NO_SOURCE_QUOTE) or sid not in index or re.fullmatch(r"I\d+", sid):
        return None
    if quote_in(quote, index[sid]):
        return None
    return f"quotes “{quote}” from {sid}, but {sid} does not say that (quote the exact words of the source)"


# ---- what a revise may correct of the planner's fields (HP 17) ---------------------------------------------------------

# The Playbook rules a finding about a block's count is under (`validate.RULE`); any other whole-block finding asks for a
# count when its fix sets one ("Set the Exhaust Fan count to 4").
COUNT_RULES = frozenset({RULE["higher"], RULE["unknown"]})
ALTERNATE_RULE = "Never invent an alternate"
_SETS_COUNT = re.compile(r"\b(?:set|carry|print|correct|change|make|use|raise)\b[^.]{0,80}\bcount\b"
                         r"|\bcount\b[^.]{0,40}\bto\s+\d+", re.I)
_SAYS_ALTERNATE = re.compile(r"\balternates?\b", re.I)


def _revisions(findings: Sequence[Finding], system: System) -> frozenset[str]:
    """What the must_fix findings about the whole block let a revise correct of the planner's fields: "count" (a
    family's count) when one is under a count rule or its fix sets a count, "alternate" when one is under the alternate
    rule or its fix names the alternate. A finding about one line, or about a line the block lacks (AI-16), opens
    neither."""
    found: set[str] = set()
    for f in findings:
        if f.severity != "must_fix" or f.device_id is not None or _missing_device(f, system):
            continue
        if f.rule in COUNT_RULES or _SETS_COUNT.search(f.fix or ""):
            found.add("count")
        if f.rule == ALTERNATE_RULE or _SAYS_ALTERNATE.search(f.fix or ""):
            found.add("alternate")
    return frozenset(found)


def _corrections_text(revise: frozenset[str], hold: frozenset[str] = frozenset()) -> str:
    """The paragraph of a revise question that says which planner fields the writer may correct ("" when none)."""
    if not revise:
        return ""
    parts = []
    if "count" in revise:
        parts.append(
            "a family's count: set the count of the family a finding names to the number the evidence gives, with "
            "the passages that give it as sources (source_id exactly as the evidence gives it, the exact quoted "
            "words, the place). The highest count prints, so the highest the evidence gives is the value. Keep "
            "every count the family already has: the app keeps each one with its source in others. The family keeps "
            "its name and its tags. Set each line counted from that family to the new count, and work out the tech "
            "hours again" + (f". Do not change the count of {', '.join(sorted(hold))}: the estimator set "
                             f"{'it' if len(hold) == 1 else 'them'}" if hold else ""))
    if "alternate" in revise:
        parts.append("the alternate: set it as the finding says. Use add or deduct only when a passage of the evidence "
                     "says this system is an add or a deduct alternate; otherwise use base.")
    return ("You may correct these planner fields of the block, because a finding above asks for it. "
            + " ".join(f"({n}) {p}" for n, p in enumerate(parts, start=1))
            + " Copy every other planner field exactly as given. The app checks each correction against the "
            "evidence and refuses one the evidence does not support.")


def _count_entries(count: Count) -> list[tuple[int, Ref | None]]:
    """Every count a Count holds, one entry for each source that backs it (a count with none: one entry without a ref),
    the printed count first."""
    entries: list[tuple[int, Ref | None]] = []
    if count.value is not None:
        entries += [(count.value, r) for r in count.sources] or [(count.value, None)]
    return entries + [(o.value, o.ref) for o in count.others]


def _count_from(entries: Sequence[tuple[int, Ref | None]], added_up: OtherCount | None) -> Count:
    """The Count of `entries`: the highest number is the value (never undershoot) with the refs that give it, every
    other number is in `others` with its ref, none dropped. The sum ruling L1 left out (`added_up`) stays only while it
    is above the printed count."""
    from bms.counts import NO_SOURCE_QUOTE
    if not entries:
        return Count(None)
    top = max(n for n, _ in entries)
    sources = tuple(dict.fromkeys(r for n, r in entries if n == top and r is not None))
    others = tuple(dict.fromkeys(OtherCount(n, r if r is not None else Ref("", NO_SOURCE_QUOTE, ""))
                                 for n, r in entries if n != top))
    return Count(top, sources, others, added_up if added_up is not None and added_up.value > top else None)


def _correct_count(family: Family, given, known: frozenset[str], index: Mapping[str, str] | None,
                   log: list[str]) -> tuple[Count | None, list[str]]:
    """The family's count after a revise answer's correction (HP 17), or the problems that refuse it. The answer's
    count is read for the counts it adds: each count it names that the family does not have, with its source. The
    family's own counts stay (the answer cannot drop or lower one), so the result is the family's counts and the
    added ones with the highest as the value, every other in `others` with its source: the highest prints and the
    "*" note names both numbers. A count the answer adds is 1 or more and cites a source this system's evidence carries
    (the plan count check's record given without a source aside), each quote in its source. None: no count is
    added."""
    from bms.counts import NO_SOURCE_QUOTE
    label = f"the {family.name} count"
    if not isinstance(given, dict):
        return None, []
    errors = schema_errors(given, json_schema(Count))
    if errors:
        return None, [f"{label} breaks the schema at {e.removeprefix('$.')}" for e in errors]
    answered = Count.from_dict(given)
    old = _count_entries(family.count)
    known_counts = {(n, None if r is None else r.source_id) for n, r in old}      # a count and the source it is from
    added: list[tuple[int, Ref | None]] = []
    for number, ref in _count_entries(answered):
        ref = ref if ref is None else replace(ref, source_id=str(ref.source_id).strip().strip("[]"))
        found = (number, None if ref is None else ref.source_id)
        if found not in known_counts:
            known_counts.add(found)
            added.append((number, ref))
    if not added:
        return None, []
    problems: list[str] = []
    for number, ref in added:
        if number < 1:
            problems.append(f"{label} gets {number}: a count is 1 or more, with the source that gives it")
        elif ref is None:
            problems.append(f"{label} gets {number} with no source: cite the evidence that gives it")
        elif ref.source_id not in known and not (not ref.source_id and ref.quote == NO_SOURCE_QUOTE):
            problems.append(f"{label} cites {ref.source_id or 'an empty id'}, not in this system's evidence (cite "
                            "the ids the evidence gives)")
        elif index is not None and (bad := _quote_problem(ref.to_dict(), index)):
            problems.append(f"{label}'s source {bad}")
    if problems:
        return None, list(dict.fromkeys(problems))
    count = _count_from([*old, *added], family.count.added_up)
    if count == family.count:
        return None, []
    numbers = ", ".join(str(n) for n, _ in added)
    log.append(f"{label}: {family.count.highest()} corrected to {count.highest()} as a finding asked (the answer "
               f"adds {numbers}; every earlier count stays with its source)")
    return count, []


def _corrections(answer: dict, skeleton: System, revise: frozenset[str], known: frozenset[str],
                 index: Mapping[str, str] | None, changes: list[str] | None,
                 hold: frozenset[str] = frozenset()) -> tuple[dict, list[str]]:
    """The planner's fields a revise answer corrects (HP 17), checked, as the skeleton fields to use instead of the
    skeleton's own: `families` with the corrected counts (a family keeps its name and tags; only its count changes,
    `_correct_count`) and `alternate` (an add or deduct alternate needs a passage of the evidence that says so, and
    "base" needs none). A family named in `hold` (the estimator set its count) never changes. Each correction is added
    to `changes` (the intake log). The problems returned refuse the answer."""
    out: dict = {}
    problems: list[str] = []
    log = changes if changes is not None else []
    if "alternate" in revise:
        kind = answer.get("alternate")
        if kind in ALTERNATES and kind != skeleton.alternate:
            if kind != "base" and not _alternate_said(kind, index or {}, skeleton):
                problems.append(f"it sets the alternate to {kind!r}, but no passage of the evidence says this system "
                                f"is a {kind} alternate: keep {skeleton.alternate!r}")
            else:
                out["alternate"] = kind
                log.append(f"alternate: {skeleton.alternate!r} corrected to {kind!r} as a finding asked")
    if "count" in revise and isinstance(answer.get("families"), list):
        given = {str(f.get("name", "")).casefold(): f for f in answer["families"] if isinstance(f, dict)}
        families, changed = [], False
        for family in skeleton.families:
            answered = given.get(family.name.casefold())
            count, why = (None, []) if family.name in hold or not answered else _correct_count(
                family, answered.get("count"), known, index, log)
            problems += why
            families.append(replace(family, count=count) if count is not None else family)
            changed = changed or count is not None
        if changed:
            out["families"] = [f.to_dict() for f in families]
    return out, problems


def _alternate_said(kind: str, index: Mapping[str, str], system: System) -> bool:
    """A passage of the evidence (its sources by id, `_sent_index`), or the block's own name, says the system is an
    add or deduct alternate: the kind word and "alternate" side by side ("add alternate 2", "alternate 1 (deduct)")."""
    near = re.compile(rf"\b{re.escape(kind)}\b[^.\n]{{0,40}}\balternates?\b|\balternates?\b[^.\n]{{0,40}}\b"
                      rf"{re.escape(kind)}\b", re.I)
    return any(near.search(text or "") for text in (*index.values(), system.name, *(f.name for f in system.families)))


def _check_system(answer, skeleton: System, shape: Shape | None, known: frozenset[str],
                  keep: Sequence[Device] = (), originals: Sequence[Device] = (),
                  changes: list[str] | None = None, tags: Sequence[str] = (),
                  ids: Sequence[str] = (), sheets: Sequence[str] = (),
                  source_sheets: Sequence[str] = (),
                  index: Mapping[str, str] | None = None,
                  recount: bool = False, block: Mapping | None = None,
                  revise: frozenset[str] = frozenset(), hold: frozenset[str] = frozenset(),
                  stated: frozenset[str] = frozenset()
                  ) -> tuple[System | None, list[str]]:
    """A System answer made usable, or the problems that stop it: the skeleton's fields win; untouched devices
    (`keep`) are put back as they were; labels come off the client texts (`_normalise`, each change added to
    `changes`) and a client text that prints a source id is refused;
    every device cites the evidence, and so does every source and other count of its quantity (the plan count
    check's record given without a source aside); with `index` (the evidence sent, `_sent_index`) every quote of
    a device is in its source; slots fit the shape; a known count is 1 or more; at most one clarification;
    every assumption says what and why; device ids unique and of this system. With `recount` (the count rewrite)
    a kept device takes the count the answer gives it (`_recounted`). With `block` (a revise whose findings all
    name devices) the block's clarifications, tech hours and no-scope reason are the original's (AI-10). With
    `revise` (a revise whose must_fix findings about the whole block ask for it, `_revisions`: "count",
    "alternate") the answer may correct a family's count or the alternate, each checked against the evidence
    (`_corrections`); a family named in `hold` keeps its count.

    T-005d: a device's mark is "", "future" or "notice"; a "future" line carries a mark_note "FUTURE AS PER <source>"
    (filled from its ref's place when the answer gave none), a line quoting a passage that marks it FUTURE is marked
    "future" on intake, and a mark_note is dropped from an unmarked line (`_marks`). An assumption that says a schedule,
    the sequence or a points list states the fact, on a line citing one of them (`stated`: the evidence's ids of those
    parts, `ai_evidence.stated_ids`), is no assumption: it is dropped and an "assumed" flag cleared (ruling 6); so is
    an ownership assumption against a cited stated passage that states the owner; one that says the source is silent
    stays. A flag text that runs long is shortened to points, never refused (`_shorten_flags`)."""
    from bms.counts import NO_SOURCE_QUOTE
    if not isinstance(answer, dict):
        return None, ["the answer is not a JSON object"]
    corrected, refused = _corrections(answer, skeleton, revise, known, index, changes, hold) if revise else ({}, [])
    if refused:
        return None, refused
    answer = {"no_scope_reason": None, **answer, **_skeleton_dict(skeleton), **corrected,
              **(block or {})}  # no field: null
    if keep:
        answer = dict(answer, devices=_put_back(answer.get("devices"), keep, originals,
                                                skeleton.families if recount else (), skeleton.key))
    _late_device_fields(answer, json_schema(System))
    errors = schema_errors(answer, json_schema(System))
    if errors:
        return None, [f"it breaks the schema at {e.removeprefix('$.')}" for e in errors]
    kept_ids = {d.id for d in keep}
    log = changes if changes is not None else []
    mark_problems = _marks(answer["devices"], kept_ids, log)
    _stated_not_assumed(answer["devices"], kept_ids, stated, log)
    _shorten_flags(answer, kept_ids, log)
    problems = list(mark_problems)
    problems += _normalise(answer, skeleton, kept_ids, changes if changes is not None else [], known, tags, ids,
                          sheets, source_sheets)
    for n, device in enumerate(answer["devices"]):
        value = device["quantity"]["value"]
        if device.get("id") not in kept_ids and value is not None and value <= 0:
            problems.append(f"device {device.get('id') or n + 1} has a quantity of {value}: a count is 1 or more, "
                            "or null when no source gives it")
    for n, device in enumerate(answer["devices"]):
        label = f"device {device.get('id') or n + 1}"
        if device.get("id") in kept_ids:
            continue
        refs = [dict(r, source_id=str(r["source_id"]).strip().strip("[]")) for r in device["refs"]]
        good = [r for r in refs if r["source_id"] in known]
        if not good:
            ids = ", ".join(dict.fromkeys(r["source_id"] for r in refs))
            problems.append(f"{label} cites {ids}, not in this system's evidence (cite the ids the evidence gives)")
        else:
            device["refs"] = good
        quantity = [*device["quantity"]["sources"], *(o["ref"] for o in device["quantity"]["others"])]
        unknown = [sid for r in quantity
                   if (sid := str(r["source_id"]).strip().strip("[]")) not in known
                   and not (not sid and r["quote"] == NO_SOURCE_QUOTE)]
        if unknown:
            named = ", ".join(dict.fromkeys(sid or "an empty id" for sid in unknown))
            problems.append(f"{label}'s quantity cites {named}, not in this system's evidence (cite the ids the "
                            "evidence gives)")
        if index is not None:
            misquoted = [_quote_problem(r, index) for r in [*device["refs"], *quantity]]
            problems += [f"{label} {p}" for p in dict.fromkeys(misquoted) if p]
        if not str(device["name"]).strip():
            problems.append(f"{label} has no name")
        if shape is not None and device["slot"] not in shape.line_order:
            problems.append(f"{label} fills the slot {device['slot']!r}, which the {shape.name} shape does not have "
                            f"(its slots: {', '.join(shape.line_order)})")
        elif shape is None and not str(device["slot"]).strip():
            problems.append(f"{label} names no slot")
        assumption = device.get("assumption")
        if assumption is not None:
            if not str(assumption["what"]).strip():
                problems.append(f"{label} has an assumption that does not say what was assumed")
            if not str(assumption["why"]).strip():
                problems.append(f"{label} has an assumption that does not say why")
            problems += [f"{label}'s assumption {p}" for p in _text_problems(
                f"{assumption['what']} {assumption['why']}")]
    problems += _heater_problems(skeleton, answer["devices"], kept_ids)
    if len(answer["clarifications"]) > 1:
        problems.append(f"it gives {len(answer['clarifications'])} clarifications; a block has at most one")
    for clarification in answer["clarifications"]:
        if not str(clarification["text"]).strip():
            problems.append("its clarification has no text")
        problems += [f"its clarification {p}" for p in _text_problems(clarification["text"])]
    if answer["devices"]:
        answer["no_scope_reason"] = None
    elif not str(answer.get("no_scope_reason") or "").strip():
        problems.append("it has no devices and no no_scope_reason: say in one plain sentence why the BMS has "
                        "nothing to scope on this system")
    else:
        problems += [f"its no_scope_reason {p}" for p in _text_problems(answer["no_scope_reason"])]
    hours = answer.get("tech_hours")
    if hours is not None and hours < 0:
        problems.append("its tech hours are below zero")
    if problems:
        return None, problems
    _number_devices(answer["devices"], skeleton.key, kept_ids)
    try:
        return System.from_dict(answer), []
    except ModelError as error:
        return None, [str(error)]


# ---- T-005d: marks, stated facts and short flags ---------------------------------------------------------------------

MARKS = ("", "future", "notice")
FUTURE_NOTE = "FUTURE AS PER"
MARK_NOTE_LIMIT = 120               # characters of a mark_note
ASSUMPTION_LIMIT = 300              # characters of an assumption's what and why together
CLARIFICATION_LIMIT = 500           # characters of a clarification
_FUTURE_WORD = re.compile(r"\bFUTURE\b|[\[(]\s*future\s*[\])]")
_SHEET_LIKE = re.compile(r"^[A-Z]{1,3}[- ]?\d[\w.\-]*$")
_STATED = re.compile(r"\b(?:schedules?|sequences?(?:\s+of\s+operations?)?|points?\s+lists?)\b[^.;]{0,40}?\b(?:states?|"
                     r"stated|says|said|shows?|shown|calls?\s+for|specif(?:y|ies|ied)|requires?|indicates?|notes?|"
                     r"gives?)\b", re.I)
# words that say a source is silent: "the schedule does not state the quantity", "shows no count", "without a count"
# (T-005d must fix 3): such an assumption is real and stays
_NEGATION = re.compile(r"\b(?:not|no|never|none|nor|neither|without|lacks?|lacking|silent|missing|absent|unstated|"
                       r"unclear|unknown)\b|n't\b", re.I)
_CLAUSE = re.compile(r"[^.;:,()]+")
# a passage that states who furnishes, installs or wires an item (T-005d should fix 2)
_STATES_OWNER = re.compile(r"\b(?:furnished|provided|supplied|installed|mounted|wired)\s+(?:and\s+\w+\s+)?by\b|"
                           r"\bby\s+(?:others|the\s+(?:unit\s+)?manufacturer|the\s+factory|the\s+owner|"
                           r"div(?:ision)?\.?\s*\d+|the\s+[\w\s]{0,20}?contractor)\b|"
                           r"\bfactory[\s-]*(?:furnished|installed|mounted|provided|wired)\b", re.I)
# an assumption about who furnishes, installs or wires an item
_ABOUT_OWNER = re.compile(r"\b(?:furnish\w*|provid\w*|suppl(?:y|ied|ies)|install\w*|wir(?:e|ed|es|ing)|mount\w*|"
                          r"owner|manufacturer|factory|contractor|by\s+(?:AME|others))\b", re.I)


def _says_stated(words: str) -> bool:
    """The words say a schedule, the sequence or a points list states the fact, in a clause with no negation."""
    return any(_STATED.search(clause) and not _NEGATION.search(clause) for clause in _CLAUSE.findall(words or ""))


def _says_silent(words: str) -> bool:
    """The words say a source is silent ("the schedule does not state the quantity")."""
    return bool(_NEGATION.search(words or ""))


def _future_source(refs: Sequence[dict]) -> str:
    """The document a FUTURE mark is as per, in a few words from its ref's place: "sheet M-9.01" for a sheet, else
    the place as given (the first ref that quotes FUTURE, else the first ref)."""
    ref = next((r for r in refs if _FUTURE_WORD.search(str(r.get("quote", "")))), refs[0] if refs else {})
    place = str(ref.get("where", "")).split(",", 1)[0].strip()
    if not place:
        return "the drawings"
    return f"sheet {place}" if _SHEET_LIKE.match(place) else place


def _marks(devices: list[dict], kept_ids: set[str], changes: list[str]) -> list[str]:
    """Each written device's mark and mark_note made usable, in place (ruling 7). A mark outside `MARKS` refuses the
    answer. A line whose ref quotes a passage that marks it FUTURE is marked "future"; a "future" line's mark_note
    starts "FUTURE AS PER" (its source's place when the answer gave none; the renderer adds the brackets); an unmarked
    line keeps no mark_note. Each change is logged; a mark_note over MARK_NOTE_LIMIT characters refuses the answer."""
    problems: list[str] = []
    for n, device in enumerate(devices):
        if device.get("id") in kept_ids:
            continue
        label = f"device {device.get('id') or n + 1}"
        mark = str(device.get("mark") or "").strip().lower()
        note = " ".join(str(device.get("mark_note") or "").split()).strip("()[] ")
        if mark not in MARKS:
            problems.append(f"{label} has the mark {device.get('mark')!r}: a mark is \"\", \"future\" or \"notice\"")
            continue
        refs = list(device.get("refs") or ())
        # only a quote whose FUTURE is beside the device's own words marks the line (should fix 1): "CAP FOR FUTURE
        # CONNECTION" on a controller's sheet marks no controller
        if not mark and any(ai_evidence.future_items(str(r.get("quote", "")), str(device.get("name") or ""))
                            for r in refs):
            mark = "future"
            changes.append(f"{label}: marked future, as its source marks it FUTURE")
        if mark == "future":
            if not note:
                note = f"{FUTURE_NOTE} {_future_source(refs)}"
                changes.append(f"{label}: mark_note written as {note!r}")
            elif not note.upper().startswith("FUTURE"):
                new = f"{FUTURE_NOTE} {note}"
                changes.append(f"{label}: mark_note {note!r} written as {new!r}")
                note = new
        elif not mark and note:
            changes.append(f"{label}: mark_note {note!r} dropped: the line has no mark")
            note = ""
        if len(note) > MARK_NOTE_LIMIT:
            problems.append(f"{label}'s mark_note runs to {len(note)} characters: keep it to the source, at most "
                            f"{MARK_NOTE_LIMIT} (\"{FUTURE_NOTE} control schematic on sheet M-1.00\")")
        device["mark"], device["mark_note"] = mark, note
    return problems


# who a passage says furnishes, installs or wires an item (lead fix 1): the party words, in the model's party names
_PARTY_WORDS = (
    (re.compile(r"\b(?:(?:temperature\s+)?controls?|BMS|BAS|ATC|DDC|EMS)\s+(?:contractor|vendor|subcontractor)\b|"
                r"\bdiv(?:ision)?\.?\s*23\s*09\b|\bAME\b", re.I), "AME"),
    (re.compile(r"\bunit\s+(?:manufacturer|mfr)\b|\bmanufacturer\b|\bfactory\b|\bequipment\s+(?:supplier|vendor)\b",
                re.I), "Unit Mfr."),
    (re.compile(r"\bmechanical\s+contractor\b|\bdiv(?:ision)?\.?\s*23\b(?!\s*09)", re.I), "Mechanical Contractor"),
    (re.compile(r"\belectrical\s+contractor\b|\bdiv(?:ision)?\.?\s*26\b", re.I), "Electrical Contractor"),
    (re.compile(r"\bfire\s+alarm\b", re.I), "FA"),
    (re.compile(r"\bothers\b", re.I), "Others"),
    (re.compile(r"\bowner\b", re.I), "Owner"),
)
_ROLE = {"furnished": "furnished_by", "provided": "furnished_by", "supplied": "furnished_by",
         "installed": "installed_by", "mounted": "installed_by", "wired": "wired_by"}
_ROLE_WORDS = {"furnished_by": "furnished", "installed_by": "installed", "wired_by": "wired"}
_ROLE_VERBS = {"furnished_by": "furnish", "installed_by": "install", "wired_by": "wire"}
_OWNER_CLAUSE = re.compile(r"\b(furnished|provided|supplied|installed|mounted|wired)\s+(?:and\s+"
                           r"(furnished|provided|supplied|installed|mounted|wired)\s+)?by\s+([^,.;:()]{2,60})", re.I)
_FACTORY_ROLE = re.compile(r"\bfactory[\s-]*(furnished|provided|supplied|installed|mounted|wired)\b", re.I)


def _party_of(words: str) -> str | None:
    """The model's party a few words name ("the unit manufacturer" is "Unit Mfr."), or None."""
    for pattern, party in _PARTY_WORDS:
        if pattern.search(words):
            return party
    return None


def stated_parties(quote: str) -> dict[str, str]:
    """Who a passage says furnishes, installs or wires the item: {"furnished_by": "Unit Mfr.", ...}, from "furnished
    by the unit manufacturer", "provided and installed by the electrical contractor", "factory mounted". A role the
    passage names twice with two parties is left out (the passage does not settle it)."""
    found: dict[str, set[str]] = {}
    for m in _OWNER_CLAUSE.finditer(str(quote or "")):
        party = _party_of(m.group(3))
        if party is None:
            continue
        for verb in (m.group(1), m.group(2)):
            if verb:
                found.setdefault(_ROLE[verb.lower()], set()).add(party)
    for m in _FACTORY_ROLE.finditer(str(quote or "")):
        found.setdefault(_ROLE[m.group(1).lower()], set()).add("Unit Mfr.")
    return {role: next(iter(parties)) for role, parties in found.items() if len(parties) == 1}


def _ownership_conflicts(device: dict, refs: Sequence[dict]) -> list[tuple[str, str, str]]:
    """Each (role, the line's party, the cited passage's party) where a cited stated passage names another party
    for a role than the line gives (lead fix 1)."""
    out: list[tuple[str, str, str]] = []
    for ref in refs:
        for role, party in stated_parties(str(ref.get("quote", ""))).items():
            mine = str(device.get(role) or "")
            if mine and mine != party and (role, mine, party) not in out:
                out.append((role, mine, party))
    return out


def _stated_not_assumed(devices: list[dict], kept_ids: set[str], stated: frozenset[str],
                        changes: list[str]) -> None:
    """Ruling 6: never "Assumed" when a cited schedule or sequence states the fact. On a line that cites one of them
    (`stated`), an assumption is dropped in place and an "assumed" flag cleared when its words say the source states
    it (in a clause with no negation, must fix 3), or when it is about who furnishes, installs or wires the item and
    a cited stated passage's quote states that, whatever reason it gives (the specification, should fix 2). An
    assumption whose words say the source is silent ("the schedule does not state the quantity") stays.

    Lead fix 1: an assumption is never dropped from a line whose parties contradict the cited stated passage (the
    line says furnished by AME, the schedule row says by the unit manufacturer). That line keeps an "ownership" flag
    (a "quantity" flag stays first) and its assumption names both parties, so the review page asks who is right. An
    ownership assumption is dropped only when the cited passage names the parties and the line agrees with them.
    Each change is logged."""
    if not stated:
        return
    for n, device in enumerate(devices):
        assumption = device.get("assumption")
        if device.get("id") in kept_ids or not assumption:
            continue
        what, why = str(assumption.get("what", "") or ""), str(assumption.get("why", "") or "")
        words = f"{what} {why}"
        refs = [r for r in device.get("refs") or ()
                if str(r.get("source_id", "")).strip().strip("[]") in stated]
        if not refs:
            continue
        said = _says_stated(words)
        about_owner = not _says_silent(words) and bool(_ABOUT_OWNER.search(what))
        owner = about_owner and any(stated_parties(str(r.get("quote", ""))) for r in refs)
        if not (said or owner):
            continue
        label = f"device {device.get('id') or n + 1}"
        conflicts = _ownership_conflicts(device, refs)
        if conflicts:
            mine = ", ".join(f"{_ROLE_WORDS[role]} by {party}" for role, party, _ in conflicts)
            theirs = ", ".join(f"{_ROLE_WORDS[role]} by {party}" for role, _, party in conflicts)
            roles = " and ".join(dict.fromkeys(_ROLE_VERBS[role] for role, _, _ in conflicts))
            device["assumption"] = {"what": f"this line has it {mine}"[:ASSUMPTION_LIMIT // 2],
                                    "why": f"the cited schedule or sequence says {theirs}; confirm who will {roles} it"
                                    [:ASSUMPTION_LIMIT // 2]}
            if device.get("flag") != "quantity":
                device["flag"] = "ownership"
            changes.append(f"{label}: assumption {words.strip()!r} kept as an ownership flag: the line has it {mine}, "
                           f"the cited passage {theirs}")
            continue
        reason = ("the schedule or sequence it cites states it" if said else
                  "the schedule or sequence it cites states who furnishes, installs or wires it")
        changes.append(f"{label}: assumption {words.strip()!r} dropped: {reason}")
        device["assumption"] = None
        if device.get("flag") in ("assumed", "ownership"):
            device["flag"] = "none"


_POINT_SPLIT = re.compile(r"(?<=[.;!?])\s+|\s*\n+\s*|\s+-\s+|\s*•\s*")


def _points(text: str, limit: int) -> str:
    """A text shortened to at most `limit` characters as short points (T-005d should fix 4): its sentences, clauses
    and list items in order, joined with "; ", as many as fit; a first point longer than the limit is cut at a word
    with " …". A text within the limit is returned as it was."""
    text = str(text or "").strip()
    if len(text) <= limit:
        return text
    points = [" ".join(p.split()).rstrip(".;, ") for p in _POINT_SPLIT.split(text)]
    points = [p for p in points if p]
    kept: list[str] = []
    for point in points:
        joined = "; ".join([*kept, point])
        if len(joined) > limit:
            break
        kept.append(point)
    if kept:
        return "; ".join(kept)
    head = (points[0] if points else text)[:max(1, limit - 2)]
    return (head.rsplit(" ", 1)[0] if " " in head else head) + " …"


def _shorten_flags(answer: dict, kept_ids: set[str], changes: list[str]) -> None:
    """A flag text that runs long is shortened in place to points, never refused (T-005d should fix 4: a refusal
    after max attempts stopped the run): an assumption's what and why together to ASSUMPTION_LIMIT characters (what
    first, at most half when both are long), a clarification to CLARIFICATION_LIMIT. The reason stays in the line's
    refs and the Evidence Package; QC reads the length as a "check". Each change is logged."""
    for n, device in enumerate(answer["devices"]):
        assumption = device.get("assumption")
        if device.get("id") in kept_ids or not isinstance(assumption, dict):
            continue
        what = str(assumption.get("what", "") or "").strip()
        why = str(assumption.get("why", "") or "").strip()
        if len(what) + len(why) <= ASSUMPTION_LIMIT:
            continue
        half = ASSUMPTION_LIMIT // 2
        new_what = _points(what, max(half, ASSUMPTION_LIMIT - len(why)) if len(why) < half else half)
        new_why = _points(why, ASSUMPTION_LIMIT - len(new_what))
        assumption["what"], assumption["why"] = new_what, new_why
        changes.append(f"device {device.get('id') or n + 1}: assumption shortened to points "
                       f"({len(what) + len(why)} to {len(new_what) + len(new_why)} characters)")
    for clarification in answer["clarifications"]:
        text = str(clarification.get("text", "") or "").strip()
        if len(text) > CLARIFICATION_LIMIT:
            clarification["text"] = _points(text, CLARIFICATION_LIMIT)
            changes.append(f"clarification shortened to points ({len(text)} to {len(clarification['text'])} "
                           "characters)")


_PLAYBOOK_WORD = re.compile(r"\bplaybook\b|\bfinding\s+\d+\b", re.I)


def _text_problems(text: str) -> list[str]:
    """What stops a text the client or the estimator reads: a Playbook rule named in it (labels are cleaned by
    `_normalise`, never refused; source ids are refused there)."""
    if _PLAYBOOK_WORD.search(str(text or "")):
        return ["names the Playbook or one of its rules: say the house practice in plain words, or name the "
                "document in a few plain words"]
    return []


# ---- the intake: labels come off; a source id in client text is refused, never rewritten (bms.citations) ---------

def _device_refs(device: dict) -> list[dict]:
    quantity = device.get("quantity") or {}
    return [*device["refs"], *quantity.get("sources", []), *(o["ref"] for o in quantity.get("others", []))]


def _normalise(answer: dict, skeleton: System, kept_ids: set[str], changes: list[str],
               known: frozenset[str] = frozenset(), tags: Sequence[str] = (),
               job_ids: Sequence[str] = (), sheets: Sequence[str] = (),
               source_sheets: Sequence[str] = ()) -> list[str]:
    """Take the leading label of its own kind off each assumption and clarification of `answer`, in place, each
    change added to `changes` (a per-drawings clarification keeps its discipline word only; one left empty is
    dropped). The label comes off first; nothing else in a text is changed. Then every client text (device name,
    assumption what and why, clarification text, no_scope_reason) is scanned for source ids
    (`bms.citations.SourceIds`, the renderer's and the validator's decision too). The problems returned refuse the
    answer, one for each text that prints an issued id (I: `job_ids`, the evidence's ids `known` and every ref the
    skeleton and the answer carry) or an unissued token joined to one. Never refused: T, `tags` (the run passes
    every tag of the job) and this system's own tags; a sheet number (after a sheet word, or one the planner's
    wheres name, K: `sheets`, the whole plan's that the run passes, and the skeleton's own; never a where on a
    device ref, which the writer types); one of the job's source sheets (`source_sheets`, `Job.source_sheets`) in
    a where and right after a sheet word, never bare in client text (FINAL-J); any other unissued lookalike ("(F1,
    F2)", "see C101"). A sheet word never makes an issued id a sheet (L-D): "sheet S141" is refused unless S141 is
    in K or a source sheet, and so is a where on a device ref
    that names an issued id anywhere, after a sheet word or not ("Sheet S141, Mechanical.pdf page 3", "S141,
    Mechanical.pdf page 3"; `SourceIds.where_issued`), whose place would be lost (FINAL-F)."""
    block = [*(r.to_dict() for r in ai_evidence.system_refs(skeleton))]
    for device in answer["devices"]:
        block += _device_refs(device)
    ids = SourceIds.of([*job_ids, *known, *(r.get("source_id", "") for r in block)], [*tags, *system_tags(skeleton)],
                       [*sheets, *ref_sheets(plan_refs(skeleton))], source_sheets=source_sheets)
    problems: list[str] = []

    def check(where: str, text) -> None:
        reason = ids.refusal(str(text or ""))
        if reason:
            problems.append(f"{where} {reason}")

    def labelled(where: str, kind: str, text: str) -> str:
        new = label_off(kind, text)
        if new != text.strip():
            changes.append(f"{where}: {text!r} written as {new!r}")
        return new

    for n, device in enumerate(answer["devices"]):
        if device.get("id") in kept_ids:
            continue
        label = f"device {device.get('id') or n + 1}"
        check(f"{label}'s name", device.get("name"))
        if str(device.get("mark_note") or "").strip():
            check(f"{label}'s mark_note", device.get("mark_note"))
        for ref in _device_refs(device):                 # a where the writer typed: its place prints (L-D)
            named = ids.where_issued(str(ref.get("where") or ""))
            if named:
                problems.append(f"{label}'s ref {ref.get('source_id')} has the where {ref.get('where')!r}, which "
                                f"names the source id{'s' if len(named) > 1 else ''} {', '.join(named)} as its place: "
                                f"{WHERE_ADVICE}")
        assumption = device.get("assumption")
        if assumption is None:
            continue
        for part in ("what", "why"):
            if str(assumption[part]).strip():
                assumption[part] = labelled(f"{label} assumption {part}", "assumed", assumption[part])
                check(f"{label}'s assumption {part}", assumption[part])
    kept = []
    for clarification in answer["clarifications"]:
        text, kind = clarification["text"], clarification["kind"]
        where = f"clarification ({kind})"
        new = labelled(where, kind, text)
        if not new and str(text).strip():
            changes.append(f"{where} {text!r} dropped: nothing left after its label")
            continue
        check(f"its {kind} clarification", new)
        kept.append(dict(clarification, text=new))
    answer["clarifications"] = kept
    if not answer["devices"] and str(answer.get("no_scope_reason") or "").strip():    # else it is dropped
        check("its no_scope_reason", answer["no_scope_reason"])
    return problems


def _log_intake(transport, name: str, changes: Sequence[str]) -> None:
    note = getattr(transport, "note_intake", None)
    if note is not None:
        for change in changes:
            note(name, change)


def _number_devices(devices: list[dict], key: str, reserved: set[str]) -> None:
    """Every device id unique and of this system ("<key>.d<n>"): a duplicate or a foreign id gets the next free
    number."""
    taken = set(reserved) | {d["id"] for d in devices if str(d["id"]).startswith(f"{key}.")}
    used: set[str] = set()
    n = 0
    for device in devices:
        if str(device["id"]).startswith(f"{key}.") and device["id"] not in used:
            used.add(device["id"])
            continue
        n += 1
        while f"{key}.d{n}" in taken:
            n += 1
        device["id"] = f"{key}.d{n}"
        taken.add(device["id"])
        used.add(device["id"])


def _recounted(device: Device, answered, families: Sequence[Family]) -> dict:
    """A kept device as it was, but carrying the count the count rewrite's answer gives it (AI-1): only when the
    device's quantity is counted from one of the system's families (`counts.counted_from`), or cites no source of
    its own and the number is one of the families' counts, and only the number (1 or more), never the answer's sources or flag (a kept device skips the intake's
    checks, and its flag is the estimator's and `counts.flag_written_devices`')."""
    from bms.counts import counted_from
    kept = device.to_dict()
    if not isinstance(answered, dict):
        return kept
    tied = any(counted_from(device, family) for family in families)
    if device.quantity.sources and not tied:
        return kept
    quantity = answered.get("quantity")
    value = quantity.get("value") if isinstance(quantity, dict) else None
    # a line citing no count source takes only a number one of the families now gives: never a stray lower one
    if not tied and value not in {family.count.value for family in families}:
        return kept
    if isinstance(value, int) and not isinstance(value, bool) and value >= 1:
        kept["quantity"] = dict(kept["quantity"], value=value)
    return kept


def _same_line(device: dict, slot, name) -> bool:
    """The answer's device is that line: the same slot and the same name (case and spacing aside)."""
    def norm(text) -> str:
        return " ".join(str(text or "").split()).casefold()
    return norm(device.get("slot")) == norm(slot) and norm(device.get("name")) == norm(name)


def _matched(devices: list, keep: Sequence[Device]) -> tuple[dict[int, str], set[int]]:
    """Which answer device (by its place in the answer) is which kept device, and which answer devices only repeat
    a kept one (AI-2). First by content, slot and name, whatever id it carries (a writer that adds a line renumbers
    the rest); then by id with the same slot (an unasked edit of that line, put back as it was). A later answer
    device with a kept device's content is a duplicate."""
    match: dict[int, str] = {}
    duplicates: set[int] = set()
    claimed: set[str] = set()
    for n, device in enumerate(devices):
        if not isinstance(device, dict):
            continue
        same = [d.id for d in keep if _same_line(device, d.slot, d.name)]
        if not same:
            continue
        free = [i for i in same if i not in claimed]
        if not free:
            duplicates.add(n)
            continue
        match[n] = device.get("id") if device.get("id") in free else free[0]
        claimed.add(match[n])
    for n, device in enumerate(devices):
        if not isinstance(device, dict) or n in match or n in duplicates:
            continue
        line = next((d for d in keep if d.id == device.get("id")), None)
        if line is not None and line.id not in claimed and _same_line(device, line.slot, device.get("name")):
            match[n] = line.id
            claimed.add(line.id)
    return match, duplicates


def _put_back(devices, keep: Sequence[Device], originals: Sequence[Device], families: Sequence[Family] = (),
              key: str = ""):
    """The answer's devices with every untouched device (`keep`) as it was, and back in its place if dropped.
    With `families` (the count rewrite only) a kept device the answer gives takes its new count (`_recounted`).

    An answer device is a kept one by its content, or by its id with the same slot (`_matched`); one that only
    repeats a kept line is dropped; a new line carrying a kept line's id gets the next free id of `key` (no id an
    original or the answer holds), so the kept line keeps its own (AI-2)."""
    if not isinstance(devices, list):
        return devices
    match, duplicates = _matched(devices, keep)
    kept = {d.id: d.to_dict() for d in keep}
    if families:
        by_id = {d.id: d for d in keep}
        kept.update({i: _recounted(by_id[i], devices[n], families) for n, i in match.items()})
    taken = {d.id for d in originals} | set(kept) | {str(d.get("id")) for d in devices if isinstance(d, dict)}
    out = []
    for n, device in enumerate(devices):
        if n in duplicates:
            continue
        if n in match:
            out.append(kept[match[n]])
        elif isinstance(device, dict) and key and device.get("id") in kept:
            number = 1
            while f"{key}.d{number}" in taken:
                number += 1
            taken.add(f"{key}.d{number}")
            out.append(dict(device, id=f"{key}.d{number}"))         # a new line in a kept line's id
        else:
            out.append(device)
    for n, device in enumerate(originals):
        if device.id not in kept or any(isinstance(d, dict) and d.get("id") == device.id for d in out):
            continue
        at = 0
        for before in reversed(originals[:n]):
            where = next((i for i, d in enumerate(out) if isinstance(d, dict) and d.get("id") == before.id), None)
            if where is not None:
                at = where + 1
                break
        out.insert(at, kept[device.id])
    return out


def write_system(system: System, evidence: str, playbook: Playbook, transport: Transport, *,
                 tags: Sequence[str] = (), ids: Sequence[str] = (), sheets: Sequence[str] = (),
                 source_sheets: Sequence[str] = ()) -> System:
    """The system with `devices`, `clarifications` and `tech_hours` filled from `evidence`.

    Contract: one WRITE_SYSTEM request (extra step "write", plan_key system.key) whose schema is
    `json_schema(System)`; the answer is checked with `schema_errors`, built with `System.from_dict`, and must keep
    the skeleton's `key`, `name`, `shape`, `control`, `families`, `sequence_refs`, `alternate` and `serves` (the
    skeleton's values win). Every device has at least one Ref whose source_id is in the evidence. Raises NoAnswer when there
    is no answer yet (chat) or the answer cannot be used after the schema check.

    Also: the pictures the evidence names are attached; a ref to an id the evidence does not carry is dropped when
    the device has another, and a device with none, a slot outside the shape, a count of 0 or below, more than one
    clarification, an assumption without its what or why, a quantity source or other count citing an id the
    evidence lacks, or a quote its source in the evidence does not hold refuses the answer (the chat asks again
    with the reason; the API is asked once more). A leading label ("Confirm", "Assumed:", "Quantity per") is cleaned on intake, never
    refused: it comes off an assumption or a clarification (a per-drawings clarification keeps its discipline word,
    "plumbing"; one left empty is dropped); each change goes to the run's `intake.json` beside the cache. A source id
    in client text is never rewritten: a text that prints an issued id (`ids`, every source id of the job, which the
    run passes, plus the evidence's ids), or an unissued id-shaped token in a citation, refuses the answer with the
    token named. `tags` is every tag of the job (`citations.job_tags`, which the run passes): a tag shaped like an
    id is never refused. `sheets` is the whole plan's sheet numbers (`citations.job_sheets`, the planner's wheres,
    which the run passes): one is never refused, as the validator and the renderer keep it. `source_sheets` is the
    job's source sheets (`Job.source_sheets`, the ledger sources' wheres, which the run passes): one is never refused
    in a where or right after a sheet word, and refused bare in client text when it is an issued id (FINAL-J), as the
    validator and the renderer read it. Duct heaters are written in one place: the duct heater block's writer is told the units it serves
    and must write all its heaters (an empty heater block is refused); a served unit's writer is told the heater
    block writes its heaters (a duct heater line there is refused)."""
    shape = _shape(system, playbook)
    images, listing = _pictures(evidence)
    known = ai_evidence.cited_ids(evidence) | _ref_ids(ai_evidence.system_refs(system))
    return _ask_system(transport, system.name, playbook, "write_system", _write_prompt(system, shape, evidence),
                       {"step": "write", "plan_key": system.key, "images": listing}, images, system, shape, known,
                       tags=tags, ids=ids, sheets=sheets, source_sheets=source_sheets, evidence=evidence)


def rewrite_for_count(system: System, evidence: str, playbook: Playbook, transport: Transport, *,
                      tags: Sequence[str] = (), ids: Sequence[str] = (), sheets: Sequence[str] = (),
                      source_sheets: Sequence[str] = ()) -> System:
    """Ask again only because a family count changed. Devices already on the system are kept by content and id.
    `tags`, `ids`, `sheets` and `source_sheets` are as for `write_system` (the run passes the job's after the
    decisions).

    The prompt names those devices by their id and words (to keep, never a list of ids to delete) and gives one id
    rule: keep the ids given; a new line takes the next free number. A renumbered answer loses no line and repeats
    none (`_put_back`, AI-2). A device decision does not
    come here: the run applies it and does not ask the writer again. A kept device keeps its words and id but
    carries the count the answer gives it when it is counted from a family or cites no count source of its own
    (`_recounted`, AI-1): the new count reaches the lines already written."""
    shape = _shape(system, playbook)
    images, listing = _pictures(evidence)
    known = ai_evidence.cited_ids(evidence) | _ref_ids(ai_evidence.system_refs(system))
    kept = "\n".join(f"- {device.id}: {device.name} ({device.slot})" for device in system.devices)
    prompt = (_write_prompt(system, shape, evidence)
              + "\n\nThe estimator changed a count. Keep every device already written. Do not drop one and do not "
              + "add a replacement. Each line that carries a changed family's count carries the new count. "
              + "Ids: keep the ids given; a new line takes the next free number.\n"
              + kept)
    return _ask_system(transport, system.name, playbook, "write_system", prompt,
                       {"step": "decide", "plan_key": system.key, "images": listing}, images, system, shape, known,
                       system.devices, system.devices, tags=tags, ids=ids, sheets=sheets,
                       source_sheets=source_sheets, evidence=evidence, recount=True)


def _ask_system(transport, name: str, playbook: Playbook, step: str, prompt: str, extra: dict,
                images: Sequence[Path], system: System, shape: Shape | None, known: frozenset[str],
                keep: Sequence[Device] = (), originals: Sequence[Device] = (), tags: Sequence[str] = (),
                ids: Sequence[str] = (), sheets: Sequence[str] = (), source_sheets: Sequence[str] = (),
                evidence: str = "", recount: bool = False, block: Mapping | None = None,
                revise: frozenset[str] = frozenset(), hold: frozenset[str] = frozenset()) -> System:
    """One WRITE_SYSTEM question checked by `_check_system`, every quote against the `evidence` sent; what the
    intake cleaned in the used answer goes to the transport's intake log. `recount`: the count rewrite's
    (`_recounted`); `block`: the block fields a device-only revise keeps; `revise` and `hold`: the planner fields a
    revise may correct, and the families whose count it may not (`_corrections`)."""
    changes: list[str] = []
    index = _sent_index(evidence)
    stated = ai_evidence.stated_ids(evidence)

    def check(answer):
        changes.clear()                     # only the used answer's changes are logged
        return _check_system(answer, system, shape, known, keep, originals, changes, tags, ids, sheets,
                             source_sheets, index, recount, block, revise, hold, stated)

    written = _ask_checked(transport, WRITE_SYSTEM, name, playbook.rules_text, _instructions(step), prompt,
                           json_schema(System), extra, images, check)
    _log_intake(transport, name, changes)
    return written


def revise_system(system: System, findings: Sequence[Finding], evidence: str, playbook: Playbook,
                  transport: Transport, *, tags: Sequence[str] = (), ids: Sequence[str] = (),
                  sheets: Sequence[str] = (), source_sheets: Sequence[str] = (),
                  hold_counts: Sequence[str] = ()) -> System:
    """The system revised for its `must_fix` findings only (the others are ignored), one round: one WRITE_SYSTEM
    request with extra step "revise"; same schema, checks and kept skeleton fields as `write_system`. With no
    must_fix finding for this system it returns `system` unchanged without asking. Raises NoAnswer.

    The request's name is the system's name with " (revise)". When every finding names a device, every other
    device is kept exactly as it was (put back if the answer changed or dropped it), and so are the block's
    clarifications, tech hours and no-scope reason (AI-10). A finding about a device the system lacks (QC's
    `_missing_device`) is about no device (AI-16): the writer is told it and may add the line it asks for, but it
    neither opens the whole block nor lets the other devices change.

    Corrections (HP 17): a must_fix finding about the whole block under a count rule, or whose fix sets a count, lets
    the answer correct a family's count; one under the alternate rule, or whose fix names the alternate, lets it
    correct the alternate (`_revisions`). Every other planner field still wins. A count correction adds the counts the
    evidence gives: the highest is the value, every count the family already had stays in `others` with its source,
    so the "*" note names both numbers and no count is lowered or dropped; an added count cites the evidence (id and
    quote) or the answer is refused. An add or deduct alternate needs a passage of the evidence that says so. A family
    named in `hold_counts` (the estimator set its count) keeps it."""
    mine = [f for f in findings if f.severity == "must_fix" and f.system_key == system.key]
    if not mine:
        return system
    shape = _shape(system, playbook)
    images, listing = _pictures(evidence)
    named = {f.device_id for f in mine if f.device_id}
    whole = any(f.device_id is None and not _missing_device(f, system) for f in mine)
    keep = () if whole else tuple(d for d in system.devices if d.id not in named)
    block = None if whole else {k: v for k, v in system.to_dict().items()
                                if k in ("clarifications", "tech_hours", "no_scope_reason")}
    hold = frozenset(hold_counts)
    revise = _revisions(mine, system)
    if all(f.name in hold for f in system.families):
        revise -= {"count"}                 # every count of the block is the estimator's
    # the evidence and the planner's refs only: an id the earlier answer wrote is no evidence of itself
    known = ai_evidence.cited_ids(evidence) | _ref_ids(ai_evidence.system_refs(system))
    return _ask_system(transport, f"{system.name} (revise)", playbook, "revise_system",
                       _revise_prompt(system, mine, shape, evidence, revise,
                                      hold & {f.name for f in system.families}),
                       {"step": "revise", "plan_key": system.key, "images": listing}, images, system, shape, known,
                       keep, system.devices, tags, ids, sheets, source_sheets, evidence, block=block,
                       revise=revise, hold=hold)


# ---- the front end: written and revised as a block of its own (HP 22, 186, 192d) ----------------------------------------

FRONT_END_KEY = "FE"                # the front end's key while it is written: its device ids are "FE.d1", "FE.d2" ...
FRONT_END_NAME = "Front End"
FRONT_END_TOPIC = "front end"       # the Playbook topic ("## Front end") whose rules are about it
_FRONT_END_WORDS = re.compile(r"\bfront[\s-]*end\b", re.I)
_EXCEPTION_WORDS = re.compile(r"\bnamed\s+exceptions?\b", re.I)


def _front_end_key(front: FrontEnd, taken: Iterable[str] = ()) -> str:
    """The key of the front end's block: the one its lines already carry in their ids, else FRONT_END_KEY, or that key
    with a number when a system of the job has it (a device id is unique in the job)."""
    for device in front.devices:
        head, dot, _ = device.id.partition(".")
        if dot and head:
            return head
    held, key, n = set(taken), FRONT_END_KEY, 1
    while key in held:
        n += 1
        key = f"{FRONT_END_KEY}{n}"
    return key


def front_end_system(front: FrontEnd, taken: Iterable[str] = ()) -> System:
    """The front end as a block the writer and the revise answer, and its evidence is chosen for: key FRONT_END_KEY, no
    shape (its lines print in the generic form), the planner's front-end refs as its cited passages (so its evidence
    carries the specification passages the reading found the front end in), integrated (so its evidence carries the
    integration passages too), and the front end's own lines, clarifications, tech hours and reason."""
    return System(key=_front_end_key(front, taken), name=FRONT_END_NAME, shape="", control="integration",
                  families=(), sequence_refs=tuple(front.refs), devices=front.devices,
                  clarifications=front.clarifications, tech_hours=front.tech_hours,
                  no_scope_reason=front.no_scope_reason)


def front_end_evidence(front: FrontEnd, dossier: Dossier, taken: Iterable[str] = (), ledger=None) -> str:
    """The evidence the front end is written from: the dossier passages its planner refs and its name point to
    (`evidence_for` of `front_end_system`), the notes in the front end's own words (the BMS, its network, graphics,
    training, integration) and, with `ledger`, the front-end facts the reading found. Only this job's text."""
    return system_evidence(front_end_system(front, taken), dossier, ledger, front_end=True)


def is_front_end_finding(finding: Finding, front: FrontEnd | None, playbook: Playbook | None = None) -> bool:
    """A finding about the front end. Its system key is the whole job's ("": the front end and the job's exceptions
    share it), so it is one that names a front-end line, or names none and is about the front end as a whole: it is
    under a rule of the Playbook's "Front end" part, says "front end" in its words, or is no finding about a named
    exception (the validator's findings about the front end's own clarification name no line)."""
    if front is None or finding.system_key != "":
        return False
    if finding.device_id is not None:
        return finding.device_id in {d.id for d in front.devices}
    rule = playbook.rules.get(finding.rule) if playbook is not None else None
    if rule is not None and rule.topic.strip().casefold() == FRONT_END_TOPIC:
        return True
    words = f"{finding.what} {finding.fix}"
    return bool(_FRONT_END_WORDS.search(words)) or not _EXCEPTION_WORDS.search(words)


def _template_wording(mode: str) -> str:
    """The Master Template's front-end lines for the mode, in its order (assets/front_end.json), for the writer as
    house wording only: "" when the file cannot be read."""
    from estimator.writing.front_end import FRONT_END_FILE, _load
    try:
        variant = _load(FRONT_END_FILE)["variants"][mode]
    except (OSError, KeyError, ValueError, TypeError):
        return ""
    out = []
    for line in variant:
        parts = ", ".join(str(p).strip() for p in line.get("lines", ()) if str(p).strip())
        out.append(f"- {str(line.get('text', '')).strip()}" + (f" (its parts: {parts})" if parts else ""))
    return "\n".join(out)


def _front_end_prompt(front: FrontEnd, system: System, evidence: str) -> str:
    skeleton = {k: v for k, v in _skeleton_dict(system).items() if k != "serves"}
    said = [f"The front end as the planner read it from this job's documents: mode {front.mode}"
            + (f"; the existing BMS the documents name is {front.existing_system_name}"
               if front.mode == "extend-existing" and front.existing_system_name else "") + "."]
    said += (["What the documents call for, in the reading's words (write a line for each the documents call for, "
              "citing its passage):", *(f"- {line}" for line in front.lines)]
             if front.lines else ["The reading found no front-end line in the documents."])
    if front.notes:
        said += ["Client notes the reading found for the front end (they go in the front end's one note clarification, "
                 "joined, only where a passage supports them):", *(f"- {note}" for note in front.notes)]
    house = _template_wording(front.mode)
    return "\n\n".join(p for p in [
        "The block, as the planner set it up (copy these fields as they are):\n"
        + json.dumps(skeleton, indent=1, ensure_ascii=False),
        "\n".join(said),
        ("The Master Template's front-end lines, in its order. This is house wording and order only: a line is "
         "written only when the evidence calls for it, and a part is a line of its own:\n" + house) if house else "",
        f"Answer with the whole block as JSON in the schema given; number the devices {system.key}.d1, "
        f"{system.key}.d2 and so on, in print order.",
        "The evidence:\n" + evidence.strip()] if p)


def _onto(front: FrontEnd, written: System) -> FrontEnd:
    """The front end with the lines, clarifications, tech hours and reason of its written block."""
    return replace(front, devices=written.devices, clarifications=written.clarifications,
                   tech_hours=written.tech_hours, no_scope_reason=written.no_scope_reason)


def write_front_end(front: FrontEnd, evidence: str, playbook: Playbook, transport: Transport, *,
                    tags: Sequence[str] = (), ids: Sequence[str] = (), sheets: Sequence[str] = (),
                    source_sheets: Sequence[str] = (), taken: Iterable[str] = ()) -> FrontEnd:
    """The front end with its `devices`, `clarifications`, `tech_hours` and `no_scope_reason` written from `evidence`
    (`front_end_evidence`), as `write_system` writes a block: one WRITE_SYSTEM request (name "Front End", extra step
    "write", plan_key the front end's key), the same schema and the same checks (every line cites this job's
    evidence by id and quote, one clarification, a block with no line says why). The Master Template's front-end
    lines are given as house wording only. `taken` are the keys of the job's systems (the front end's key avoids
    them). Asked only when the planner carried something the documents say about the front end (`lines` or `notes`)
    and nothing is written yet; else `front` is returned without asking. Raises NoAnswer as `write_system`."""
    if front.devices or front.clarifications or front.no_scope_reason or not (front.lines or front.notes):
        return front
    system = front_end_system(front, taken)
    images, listing = _pictures(evidence)
    known = ai_evidence.cited_ids(evidence) | _ref_ids(ai_evidence.system_refs(system))
    written = _ask_system(transport, FRONT_END_NAME, playbook, "write_front_end",
                          _front_end_prompt(front, system, evidence),
                          {"step": "write", "plan_key": system.key, "images": listing}, images, system, None, known,
                          tags=tags, ids=ids, sheets=sheets, source_sheets=source_sheets, evidence=evidence)
    return _onto(front, written)


def revise_front_end(front: FrontEnd, findings: Sequence[Finding], evidence: str, playbook: Playbook,
                     transport: Transport, *, tags: Sequence[str] = (), ids: Sequence[str] = (),
                     sheets: Sequence[str] = (), source_sheets: Sequence[str] = (),
                     taken: Iterable[str] = ()) -> FrontEnd:
    """The front end revised for its `must_fix` findings (`is_front_end_finding`), one round, as `revise_system`
    revises a block (the request's name is "Front End (revise)"); `front` unchanged, without asking, when there is
    none. Raises NoAnswer."""
    if not (front.devices or front.clarifications or front.lines or front.notes):
        return front                        # the documents call for no front end: nothing to revise, none is written
    system = front_end_system(front, taken)
    mine = [replace(f, system_key=system.key) for f in findings
            if f.severity == "must_fix" and is_front_end_finding(f, front, playbook)]
    if not mine:
        return front
    revised = revise_system(system, mine, evidence, playbook, transport, tags=tags, ids=ids, sheets=sheets,
                            source_sheets=source_sheets)
    return _onto(front, revised)


# ---- QC -------------------------------------------------------------------------------------------------------------

def _qc_schema(job: Job, playbook: Playbook) -> dict:
    """{"findings": [Finding]}, with the rule names and system keys as the only values allowed."""
    finding = json_schema(Finding)
    props = finding["properties"]
    props["rule"] = {**props["rule"], "enum": list(playbook.rules)}
    props["system_key"] = {**props["system_key"], "enum": ["", *(s.key for s in job.systems)]}
    return {"type": "object", "properties": {"findings": {"type": "array", "items": finding}},
            "required": ["findings"], "additionalProperties": False}


_WORD = re.compile(r"[^\W_]+")
_GAP = re.compile(r"\.\.\.|…")


def _words(text: str) -> str:
    text = (text or "").casefold().replace("’", "'").replace("‘", "'")
    return " " + " ".join(_WORD.findall(text)) + " "


def quote_in(quote: str, source: str) -> bool:
    """The quote's words are in the source, in order (case, punctuation and spacing aside; "..." marks a gap)."""
    pieces = [_words(p).strip() for p in _GAP.split(quote or "")]
    pieces = [p for p in pieces if p]
    if not pieces:
        return False
    text, at = _words(source), 0
    for piece in pieces:
        found = text.find(f" {piece} ", at)
        if found < 0:
            return False
        at = found + len(piece) + 1
    return True


def _ref_problem(ref: Ref, index: Mapping[str, str], planned: frozenset[str] = frozenset()) -> str | None:
    """What is wrong with one Ref of the written job, or None. `planned` is the ids the planner cited (its refs):
    a ledger fact (F) not in the dossier's text is this job's only when the planner gave it."""
    from bms.counts import LOCATED_QUOTE, NO_SOURCE_QUOTE, SEEN_QUOTE
    if ref.quote in (LOCATED_QUOTE, SEEN_QUOTE, NO_SOURCE_QUOTE):
        return None                 # the plan count check's own record (bms.counts), not words of a document
    sid = str(ref.source_id).strip().strip("[]")
    if re.fullmatch(r"I\d+", sid) and sid in index:
        return None                 # a picture of this job: its words are not in the dossier's text
    if sid.startswith("F") and sid not in index:
        if sid in planned:
            return None             # a ledger fact the planner cited: its words are the quote given with it
        return f"cites {sid}, which is no ledger fact the planner gave"
    if sid not in index:
        return f"cites {sid}, which is not among this job's sources"
    if not quote_in(ref.quote, index[sid]):
        return f"quotes “{ref.quote}” from {sid}, but {sid} does not say that"
    return None


QUOTE_FIX = ("Quote the exact words of the source that call for it, or cite the source of this job that does; a "
             "line no source of this job calls for comes out.")


def _quote_findings(job: Job, index: Mapping[str, str], rule: str) -> list[Finding]:
    """The mechanical check: every Ref's source is this job's and holds its quote."""
    out: list[Finding] = []
    # the planner's refs: of each system for its own lines, of the whole job for the front end and the exceptions
    planned_job = frozenset(_ref_ids([*(r for s in job.systems for r in ai_evidence.system_refs(s)),
                                      *(job.front_end.refs if job.front_end is not None else ()),
                                      *(r for e in job.exceptions for r in e.refs)]))
    planned = planned_job

    def check(system_key: str, device_id: str | None, refs) -> None:
        problems = list(dict.fromkeys(p for r in refs if (p := _ref_problem(r, index, planned))))
        if problems:
            what = f"{device_id or 'The block'} " + "; ".join(problems) + "."
            out.append(Finding(rule, system_key, device_id, "must_fix", what, QUOTE_FIX))

    for system in job.systems:
        planned = frozenset(_ref_ids(ai_evidence.system_refs(system)))
        check(system.key, None, ai_evidence.system_refs(system))
        for device in system.devices:
            check(system.key, device.id, [*device.refs, *device.quantity.sources,
                                          *(o.ref for o in device.quantity.others)])
    planned = planned_job
    if job.front_end is not None:
        for device in job.front_end.devices:
            check("", device.id, [*device.refs, *device.quantity.sources, *(o.ref for o in device.quantity.others)])
    for exception in job.exceptions:
        check("", None, exception.refs)
    return out


def _citation_rule(playbook: Playbook) -> str | None:
    """The Playbook rule the quote check reports under: the validators' citation rule (`validate.RULE["cites"]`),
    found by its name, so where it sits in rules.md and what its topic is called do not matter. None when the
    Playbook lacks it."""
    return CITES_RULE if CITES_RULE in playbook.rules else None


def quote_findings(job: Job, evidence_index: Mapping[str, str], playbook: Playbook) -> list[Finding]:
    """The QC pass's mechanical check alone (no question asked): every Ref of the job cites a source of this job
    whose text holds its quote. The run gives it the revised job, since QC is not asked again after the revise."""
    rule = _citation_rule(playbook)
    return _quote_findings(job, evidence_index, rule) if rule else []


def _job_refs(job: Job, systems: Sequence[System], whole: bool) -> list[Ref]:
    refs = [r for s in systems for r in _all_refs(s)]
    if whole:
        if job.front_end is not None:
            for device in job.front_end.devices:
                refs += [*device.refs, *device.quantity.sources, *(o.ref for o in device.quantity.others)]
        refs += [r for e in job.exceptions for r in e.refs]
    return refs


def _sources_text(refs: Sequence[Ref], index: Mapping[str, str], given: set[str]) -> list[str]:
    lines = []
    for sid in dict.fromkeys(str(r.source_id).strip().strip("[]") for r in refs):
        if sid in given:
            continue
        given.add(sid)
        text = index.get(sid)
        if text is None:
            what = ("a ledger fact; its words are the quote given with it" if sid.startswith("F")
                    else "not among this job's sources")
            lines.append(f"[{sid}] ({what})")
            continue
        if len(text) > SOURCE_TEXT_LIMIT:
            text = text[:SOURCE_TEXT_LIMIT] + f" (cut at {SOURCE_TEXT_LIMIT:,} characters)"
        lines.append(f"[{sid}] {text}")
    return lines


def _qc_parts(job: Job, index: Mapping[str, str]) -> list[tuple[System, ...]]:
    """The systems in parts of at most QC_PART_LIMIT characters of JSON and sources (a bigger system alone)."""
    parts: list[list[System]] = [[]]
    used = 0
    for system in job.systems:
        size = len(system.to_json(indent=1)) + sum(len(t) for t in _sources_text(_all_refs(system), index, set()))
        if parts[-1] and used + size > QC_PART_LIMIT:
            parts.append([])
            used = 0
        parts[-1].append(system)
        used += size
    return [tuple(p) for p in parts]


def _qc_prompt(job: Job, systems: Sequence[System], whole: bool, index: Mapping[str, str], playbook: Playbook,
               mechanical: Sequence[Finding]) -> str:
    keys = {s.key for s in systems}
    written = {"name": job.name, "systems": [{k: v for k, v in s.to_dict().items() if k != "serves"}
                                             for s in systems]}           # the served list is said in words
    if whole:
        written |= {"front_end": job.front_end.to_dict() if job.front_end else None,
                    "exceptions": [e.to_dict() for e in job.exceptions], "questions": list(job.questions)}
    shapes = []
    for system in systems:
        shape = _shape(system, playbook)
        shapes.append(f"- {system.key}: " + (f"{shape.name}, slots {', '.join(shape.line_order)}" if shape
                                              else "no shape (untemplated; any slot names)"))
    found = [f for f in mechanical if f.system_key in keys or (whole and f.system_key == "")]
    sources = _sources_text(_job_refs(job, systems, whole), index, set())
    heaters = [f"- the {s.name} block ({s.key}) writes every duct heater, those of: "
               + "; ".join(f"{u.name} ({u.key})" for u in _heats(s))
               for s in job.systems if _heats(s) and (s.key in keys or any(u.key in keys for u in _heats(s)))]
    return "\n\n".join(p for p in [
        f"Job: {job.name}",
        "The Playbook's rule names (a finding's rule is one of these, exactly):\n"
        + "\n".join(f"- {name}" for name in playbook.rules),
        "The shape of each block:\n" + "\n".join(shapes),
        "Mechanical findings already made (do not repeat them):\n"
        + ("\n".join(f"- {f.system_key or 'job'} {f.device_id or ''}: {f.what}" for f in found) or "(none)"),
        ("Duct heaters, written in one place (the heater lines belong to the heater block only):\n"
         + "\n".join(heaters)) if heaters else "",
        "The written job" + ("" if whole else " (this part)") + ":\n" + json.dumps(written, indent=1,
                                                                                    ensure_ascii=False),
        "The text of every source it cites, by id:\n" + ("\n".join(sources) or "(none)")] if p)


_MISSING = " (about {}, which the written job does not have)"
_MISSING_AT_END = re.compile(re.escape(_MISSING).replace(r"\{\}", r"(\S+)") + "$")   # the same words, read back


def _missing_device(finding: Finding, system: System) -> bool:
    """A finding about a device the system does not have: QC's (`_check_findings` nulls its device id and names the
    id in `what` with `_MISSING`), or one whose device id the system lacks."""
    ids = {d.id for d in system.devices}
    if finding.device_id is not None:
        return finding.device_id not in ids
    found = _MISSING_AT_END.search(finding.what)
    return found is not None and found.group(1) not in ids


def _check_findings(answer, job: Job) -> tuple[list[Finding] | None, list[str]]:
    if not isinstance(answer, dict) or not isinstance(answer.get("findings"), list):
        return None, ["the answer has no list of findings"]
    devices = {s.key: {d.id for d in s.devices} for s in job.systems}
    devices[""] = {d.id for d in job.front_end.devices} if job.front_end else set()
    out: list[Finding] = []
    for n, raw in enumerate(answer["findings"]):
        try:
            finding = Finding.from_dict(raw)
        except ModelError as error:
            return None, [f"finding {n + 1}: {error}"]
        if finding.device_id is not None and finding.device_id not in devices.get(finding.system_key, set()):
            finding = replace(finding, device_id=None, what=f"{finding.what}{_MISSING.format(finding.device_id)}")
        out.append(finding)
    return out, []


def qc_job(job: Job, evidence_index: Mapping[str, str], playbook: Playbook, transport: Transport) -> list[Finding]:
    """An independent reviewer's findings on the whole written job (one QC_JOB request, or one per part when the job
    is too long; schema {"findings": [Finding]}). Each Finding's `rule` is a Playbook rule name; `system_key` and
    `device_id` name what it is about. Raises NoAnswer as `write_system`.

    First a mechanical check: every Ref of the job cites a source of this job whose text holds its quote (a picture
    of this job, or a ledger fact the planner cited, aside); each device (or block) that fails is a must_fix
    finding under the Playbook's citation rule (`validate.RULE["cites"]`). Then the reviewer, told those findings, gets the job and the text of every source
    it cites (extra step "qc"; the schema's rule and system_key allow only the Playbook's rule names and the job's
    keys). Every part is asked before NoAnswer is raised. A finding naming a device the job lacks keeps the finding,
    its device_id null and the id named in `what`."""
    rule = _citation_rule(playbook)
    mechanical = _quote_findings(job, evidence_index, rule) if rule else []
    schema = _qc_schema(job, playbook)
    parts = _qc_parts(job, evidence_index)
    found: list[Finding] = []
    missing: list[NoAnswer] = []
    for n, systems in enumerate(parts, start=1):
        name = "QC" if len(parts) == 1 else f"QC (part {n} of {len(parts)})"
        prompt = _qc_prompt(job, systems, n == 1, evidence_index, playbook, mechanical)
        try:
            found += _ask_checked(transport, QC_JOB, name, playbook.rules_text, _instructions("qc_job"), prompt,
                                  schema, {"step": "qc"}, (), lambda answer: _check_findings(answer, job))
        except NoAnswer as no:
            missing.append(no)
    if missing:
        raise NoAnswer("; ".join(m.reason for m in missing), waiting=any(m.waiting for m in missing))
    seen = {(f.rule, f.system_key, f.device_id, f.what) for f in mechanical}
    out = list(mechanical)
    for finding in found:
        key = (finding.rule, finding.system_key, finding.device_id, finding.what)
        if key not in seen:
            seen.add(key)
            out.append(finding)
    return out
