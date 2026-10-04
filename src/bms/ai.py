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
  behind. A step that refuses the answer `max_attempts` times (`.claude/run-job.json`, else 3) stops: a plain
  message names the request, and no further request is written.
- `ApiTransport` — the Anthropic SDK (anthropic 1.8.0), streamed, structured output
  (`output_config={"format": {"type": "json_schema", "schema": schema}}`), no temperature, the Playbook rules as
  the first system block with `cache_control: {"type": "ephemeral"}` (prompt caching), the step's own instructions
  as the second; same cache folder and file form under the API model's name; the key from the environment only.
  An answer a step refuses is dropped from the cache and the question asked again with the reason, up to
  `max_attempts` times, then the run stops with a plain message naming the request.

Request kinds (what `/run-job` dispatches on): `write_system` for both writing and revising a system (extra
`"step": "write" | "revise"`, `"plan_key": system.key`, `"images"`; a revise request's "system" is the system's name
with " (revise)"), `qc_job` for the QC pass (extra `"step": "qc"`). In chat mode the request's `system_prompt` is
the Playbook rules text, a blank line, then the step's instructions (`src/bms/prompts/`).

Ground rules the steps hold: every device cites this job's evidence by id (an answer citing an id the evidence does
not carry is refused); the Master Template shape is only the frame (slots and their print form, never a line);
every assumption says what and why; one clarification per block; the skeleton's planner fields always win.
A cosmetic slip in client text (a leading label, a source id) is cleaned on intake instead of refused, and logged
as [{"system", "change"}] in `<cache>/intake.json` (one log per run).
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol, runtime_checkable

from estimator.writing.dossier import Dossier
from estimator.writing.judge import DEFAULT_MODEL, KEY_VARIABLE, MODEL_VARIABLE, _key, _plain

from bms import ai_evidence
from bms.model import Device, Finding, Job, ModelError, Ref, System, json_schema, schema_errors
from bms.playbook import Playbook, Shape
from bms.citations import SourceIds, per_drawings_text, strip_label, system_tags

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
LATE_FIELDS = {"no_scope_reason": None, "serves": []}  # System fields added after answers were written: missing
#                                                       means this value
SKELETON_FIELDS = ("key", "name", "shape", "control", "families", "sequence_refs", "alternate", "serves")
CITATIONS_TOPIC = "Evidence and citations"
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
    key = _key(model, prompt + _fingerprint(images), f"{instructions}\n\n{system_prompt}")
    return _Question(kind, name, instructions, system_prompt, prompt, schema, dict(extra or {}), images, key)


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


def _attempt_file(cache: _Cache, q: _Question) -> Path:
    """One counter per request (kind, step, name, plan key), so a retry whose prompt grew still counts."""
    ident = f"{q.kind}|{q.extra.get('step', '')}|{q.name}|{q.extra.get('plan_key', '')}"
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


def _record_refusal(transport) -> int:
    cache, last = getattr(transport, "cache", None), getattr(transport, "_last", None)
    count = _refusal_count(transport) + 1
    if cache is not None and last is not None:
        try:
            _write_json(_attempt_file(cache, last), {"attempts": count})
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


def _drop_refused(transport) -> None:
    """The refused answer leaves the cache, and a chat request still on disk is not asked again."""
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


def _stop_reason(name: str, attempts: int, reason: str) -> str:
    return f"Stopped: the request {name} was refused {attempts} times. {reason}"


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
            (self.requests_dir / f"{q.key}.json").unlink(missing_ok=True)   # a killed run may have left it
            return cached
        answer_file = self.answers_dir / f"{q.key}.json"
        problem = None
        if answer_file.exists():
            answer, errors = _read_answer(answer_file, q.schema)
            if answer is not None:
                self.cache.write(q, CHAT_MODEL, answer)
                (self.requests_dir / f"{q.key}.json").unlink(missing_ok=True)
                self.answered_in_chat += 1
                self.last_error = None
                return answer
            problem = f"the answer for {name} could not be read: {_problems(errors)}"
            attempts = _record_refusal(self)
            if attempts >= _max_attempts():
                _drop_refused(self)
                self.last_error = _stop_reason(name, attempts, problem)
                raise NoAnswer(self.last_error, waiting=False)
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
        if request.is_file():
            try:
                same = json.loads(request.read_text(encoding="utf-8")) == data
            except (OSError, ValueError):
                same = False
            if same:                                 # still waiting: do not ask this question a second time
                (self.requests_dir / "old" / request.name).unlink(missing_ok=True)
                self.waiting += 1
                waiting = f"waiting for an answer in the chat (requests folder: {request.parent})"
                self.last_error = f"{problem}; asked again, {waiting}" if problem else waiting
                return NoAnswer(self.last_error, waiting=True)
        try:
            _write_json(request, data, indent=2)
            (self.requests_dir / "old" / request.name).unlink(missing_ok=True)     # asked again: no longer stale
        except OSError:
            self.last_error = f"the request for {q.name} could not be written to {request.parent}"
            return NoAnswer(self.last_error, waiting=False)
        self.waiting += 1
        waiting = f"waiting for an answer in the chat (requests folder: {request.parent})"
        self.last_error = f"{problem}; asked again, {waiting}" if problem else waiting
        return NoAnswer(self.last_error, waiting=True)


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
        try:
            response = self._call(q)
            answer = _answer_of(response, q)
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
        raise NoAnswer(f"{q.name}: the AI answer was cut off before it finished")
    if stop == "refusal":
        raise NoAnswer(f"{q.name}: the AI declined to answer")
    text = "".join(getattr(block, "text", "") for block in getattr(response, "content", ())
                   if getattr(block, "type", None) == "text")
    try:
        answer = json.loads(text)
    except ValueError:
        raise NoAnswer(f"the answer for {q.name} could not be read: it is not valid JSON") from None
    if isinstance(answer, dict):
        for name, empty in LATE_FIELDS.items():     # a field added to the contract later: missing means empty
            if name in q.schema.get("properties", {}) and name not in answer:
                answer[name] = json.loads(json.dumps(empty))
    errors = schema_errors(answer, q.schema)
    if errors:
        raise NoAnswer(f"the answer for {q.name} could not be read: {_problems(errors)}")
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
        answer = transport.ask(kind, name, instructions, system_prompt, prompt_now, schema, extra, images)
        value, problems = check(answer)
        if not problems:
            _clear_attempts(transport)
            return value
        reason = f"the answer for {name} could not be used: {_problems(problems)}"
        if _refusal_count(transport) >= limit:
            _drop_refused(transport)
            raise NoAnswer(_stop_reason(name, limit, reason), waiting=False)
        attempts = _record_refusal(transport)
        if attempts >= limit:
            _drop_refused(transport)
            raise NoAnswer(_stop_reason(name, attempts, reason), waiting=False)
        refuse = getattr(transport, "refuse", None)
        if refuse is None:
            raise NoAnswer(reason)
        if not refuse(reason):
            raise NoAnswer(reason + " (asked again)", waiting=True)
        if retried:                         # the API's one immediate retry already happened
            raise NoAnswer(reason)
        retried = True
        prompt_now = (f"{prompt}\n\nYour earlier answer to this question could not be used: {_problems(problems)}. "
                      "Answer again, fixing that.")


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
    passages name, as "[I3] Picture: <what>. File: <path>" (write_system attaches those files)."""
    return ai_evidence.evidence(system, dossier.text, dict(dossier.sources or {}), dict(dossier.sections or {}),
                                dossier.images)


def evidence_index(dossier: Dossier) -> dict[str, str]:
    """Every source id of the dossier ("S41", "I2", "Q7") -> its text (a picture: its description), for the QC
    pass to check that each Ref's quote is in its source."""
    sections = dossier.sections or {}
    if not sections:
        from estimator.writing.dossier import sections_in
        sections = sections_in(dossier.text or "")
    return ai_evidence.index(dossier.text, dict(dossier.sources or {}), dict(sections))


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


def _revise_prompt(system: System, findings: Sequence[Finding], shape: Shape | None, evidence: str) -> str:
    return "\n\n".join(p for p in [
        "The block as written:\n" + json.dumps({k: v for k, v in system.to_dict().items() if k != "serves"},
                                               indent=1, ensure_ascii=False),
        "The findings to fix (must fix), and nothing else:\n"
        + "\n".join(_finding_text(n, f) for n, f in enumerate(findings, start=1)),
        _shape_text(system, shape),
        _heater_text(system),
        "Answer with the whole revised system as JSON in the schema given.",
        "The evidence:\n" + evidence.strip()] if p)


def _ref_ids(refs) -> set[str]:
    return {str(r.source_id).strip().strip("[]") for r in refs}


def _all_refs(system: System) -> list[Ref]:
    refs = ai_evidence.system_refs(system)
    for device in system.devices:
        refs += list(device.refs) + list(device.quantity.sources) + [o.ref for o in device.quantity.others]
    return refs


def _check_system(answer, skeleton: System, shape: Shape | None, known: frozenset[str],
                  keep: Sequence[Device] = (), originals: Sequence[Device] = (),
                  changes: list[str] | None = None, tags: Sequence[str] = ()) -> tuple[System | None, list[str]]:
    """A System answer made usable, or the problems that stop it: the skeleton's fields win; untouched devices
    (`keep`) are put back as they were; client texts are cleaned (`_normalise`, each change added to `changes`);
    every device cites the evidence; slots fit the shape; a known count is 1 or more; at most one clarification;
    every assumption says what and why; device ids unique and of this system."""
    if not isinstance(answer, dict):
        return None, ["the answer is not a JSON object"]
    answer = {"no_scope_reason": None, **answer, **_skeleton_dict(skeleton)}   # an answer without the field: null
    if keep:
        answer = dict(answer, devices=_put_back(answer.get("devices"), keep, originals))
    errors = schema_errors(answer, json_schema(System))
    if errors:
        return None, [f"it breaks the schema at {e.removeprefix('$.')}" for e in errors]
    problems: list[str] = []
    kept_ids = {d.id for d in keep}
    emptied = _normalise(answer, skeleton, kept_ids, changes if changes is not None else [], known, tags)
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
        if n in emptied:
            problems.append(f"{label} has no name left once its source ids are taken out ({emptied[n]!r}): name "
                            "the device in the document's own words")
        elif not str(device["name"]).strip():
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


_PLAYBOOK_WORD = re.compile(r"\bplaybook\b|\bfinding\s+\d+\b", re.I)


def _text_problems(text: str) -> list[str]:
    """What stops a text the client or the estimator reads and the intake cannot clean: a Playbook rule named in
    it (labels and source ids are cleaned by `_normalise`, never refused)."""
    if _PLAYBOOK_WORD.search(str(text or "")):
        return ["names the Playbook or one of its rules: say the house practice in plain words, or name the "
                "document in a few plain words"]
    return []


# ---- the intake: cosmetic slips in client text cleaned, not refused (bms.citations decides what is cleaned) ------

def _device_refs(device: dict) -> list[dict]:
    quantity = device.get("quantity") or {}
    return [*device["refs"], *quantity.get("sources", []), *(o["ref"] for o in quantity.get("others", []))]


def _normalise(answer: dict, skeleton: System, kept_ids: set[str], changes: list[str],
               known: frozenset[str] = frozenset(), tags: Sequence[str] = ()) -> dict[int, str]:
    """Clean the client texts of `answer` in place, each change added to `changes`: the leading label of the text's
    own kind taken off an assumption or a clarification (a per-drawings clarification keeps its discipline word
    only; one left empty is dropped) and source ids put in words in every client text (device names too). One
    decision, `bms.citations.SourceIds`, the renderer's and the validator's too: T is `tags` (the run passes every
    tag of the job, `citations.job_tags`) and this system's own tags; I is `known` (the evidence's ids) and every
    ref the skeleton and the answer carry. An unissued id removed from a citation is logged as such."""
    block = [*(r.to_dict() for r in ai_evidence.system_refs(skeleton))]
    for device in answer["devices"]:
        block += _device_refs(device)
    ids = SourceIds.of([*known, *(r.get("source_id", "") for r in block)], [*tags, *system_tags(skeleton)])

    def stripped(where: str, text: str, groups) -> str:
        cleaned = ids.clean(text, *groups)
        changes.extend(f"{where}: unissued id removed: {token}" for token in dict.fromkeys(cleaned.unissued_removed))
        return cleaned.text

    def clean(where: str, text: str, groups, label: bool = True) -> str:
        new = stripped(where, strip_label("assumed", text) if label else text.strip(), groups).strip()
        if new != text.strip():
            changes.append(f"{where}: {text!r} written as {new!r}")
        return new

    emptied: dict[int, str] = {}          # devices whose name had nothing but source ids: refused by the caller
    for n, device in enumerate(answer["devices"]):
        if device.get("id") in kept_ids:
            continue
        groups = (_device_refs(device), block)
        if str(device.get("name") or "").strip():
            name = device["name"]
            device["name"] = clean(f"device {device.get('id')} name", name, groups, label=False)
            if not device["name"]:
                emptied[n] = name
        assumption = device.get("assumption")
        if assumption is None:
            continue
        for part in ("what", "why"):
            if str(assumption[part]).strip():
                assumption[part] = clean(f"device {device.get('id')} assumption {part}", assumption[part], groups)
    kept = []
    for clarification in answer["clarifications"]:
        text, kind = clarification["text"], clarification["kind"]
        where = f"clarification ({kind})"
        new = stripped(where, text, (block,))
        new = (per_drawings_text(new) if kind == "per_drawings" else strip_label(kind, new)).strip()
        if not new and str(text).strip():
            changes.append(f"{where} {text!r} dropped: nothing left after its label")
            continue
        if new != text.strip():
            changes.append(f"{where}: {text!r} written as {new!r}")
        kept.append(dict(clarification, text=new))
    answer["clarifications"] = kept
    if str(answer.get("no_scope_reason") or "").strip():
        answer["no_scope_reason"] = clean("no_scope_reason", answer["no_scope_reason"], (block,), label=False)
    return emptied


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


def _put_back(devices, keep: Sequence[Device], originals: Sequence[Device]):
    """The answer's devices with every untouched device (`keep`) as it was, and back in its place if dropped."""
    if not isinstance(devices, list):
        return devices
    kept = {d.id: d.to_dict() for d in keep}
    out = [kept.get(d.get("id"), d) if isinstance(d, dict) else d for d in devices]
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
                 tags: Sequence[str] = ()) -> System:
    """The system with `devices`, `clarifications` and `tech_hours` filled from `evidence`.

    Contract: one WRITE_SYSTEM request (extra step "write", plan_key system.key) whose schema is
    `json_schema(System)`; the answer is checked with `schema_errors`, built with `System.from_dict`, and must keep
    the skeleton's `key`, `name`, `shape`, `control`, `families`, `sequence_refs`, `alternate` and `serves` (the
    skeleton's values win). Every device has at least one Ref whose source_id is in the evidence. Raises NoAnswer when there
    is no answer yet (chat) or the answer cannot be used after the schema check.

    Also: the pictures the evidence names are attached; a ref to an id the evidence does not carry is dropped when
    the device has another, and a device with none, a slot outside the shape, a count of 0 or below, more than one
    clarification or an assumption without its what or why refuses the answer (the chat asks again with the reason;
    the API is asked once more). Cosmetic slips are cleaned on intake, never refused: a leading label ("Confirm",
    "Assumed:", "Quantity per") comes off an assumption or a clarification (a per-drawings clarification keeps its
    discipline word, "plumbing"; one left empty is dropped) and a source id in client text becomes the place of its
    ref, or is taken out; each change goes to the run's `intake.json` beside the cache. `tags` is every tag of the
    job (`citations.job_tags`, which the run passes): a tag shaped like an id is never taken out. Duct heaters are written in one place: the duct heater block's writer is told the units it serves
    and must write all its heaters (an empty heater block is refused); a served unit's writer is told the heater
    block writes its heaters (a duct heater line there is refused)."""
    shape = _shape(system, playbook)
    images, listing = _pictures(evidence)
    known = ai_evidence.cited_ids(evidence) | _ref_ids(ai_evidence.system_refs(system))
    return _ask_system(transport, system.name, playbook, "write_system", _write_prompt(system, shape, evidence),
                       {"step": "write", "plan_key": system.key, "images": listing}, images, system, shape, known,
                       tags=tags)


def _ask_system(transport, name: str, playbook: Playbook, step: str, prompt: str, extra: dict,
                images: Sequence[Path], system: System, shape: Shape | None, known: frozenset[str],
                keep: Sequence[Device] = (), originals: Sequence[Device] = (), tags: Sequence[str] = ()) -> System:
    """One WRITE_SYSTEM question checked by `_check_system`; what the intake cleaned in the used answer goes to
    the transport's intake log."""
    changes: list[str] = []

    def check(answer):
        changes.clear()                     # only the used answer's changes are logged
        return _check_system(answer, system, shape, known, keep, originals, changes, tags)

    written = _ask_checked(transport, WRITE_SYSTEM, name, playbook.rules_text, _instructions(step), prompt,
                           json_schema(System), extra, images, check)
    _log_intake(transport, name, changes)
    return written


def revise_system(system: System, findings: Sequence[Finding], evidence: str, playbook: Playbook,
                  transport: Transport, *, tags: Sequence[str] = ()) -> System:
    """The system revised for its `must_fix` findings only (the others are ignored), one round: one WRITE_SYSTEM
    request with extra step "revise"; same schema, checks and kept skeleton fields as `write_system`. With no
    must_fix finding for this system it returns `system` unchanged without asking. Raises NoAnswer.

    The request's name is the system's name with " (revise)". When every finding names a device, every other
    device is kept exactly as it was (put back if the answer changed or dropped it)."""
    mine = [f for f in findings if f.severity == "must_fix" and f.system_key == system.key]
    if not mine:
        return system
    shape = _shape(system, playbook)
    images, listing = _pictures(evidence)
    named = {f.device_id for f in mine if f.device_id}
    whole = any(f.device_id is None for f in mine)
    keep = () if whole else tuple(d for d in system.devices if d.id not in named)
    known = (ai_evidence.cited_ids(evidence) | _ref_ids(_all_refs(system)))
    return _ask_system(transport, f"{system.name} (revise)", playbook, "revise_system",
                       _revise_prompt(system, mine, shape, evidence),
                       {"step": "revise", "plan_key": system.key, "images": listing}, images, system, shape, known,
                       keep, system.devices, tags)


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


def _ref_problem(ref: Ref, index: Mapping[str, str]) -> str | None:
    from bms.counts import LOCATED_QUOTE, NO_SOURCE_QUOTE, SEEN_QUOTE
    if ref.quote in (LOCATED_QUOTE, SEEN_QUOTE, NO_SOURCE_QUOTE):
        return None                 # the plan count check's own record (bms.counts), not words of a document
    sid = str(ref.source_id).strip().strip("[]")
    if sid.startswith(("F", "I")) and sid not in index or re.fullmatch(r"I\d+", sid):
        return None                 # a ledger fact or a picture: its words are not in the dossier's text
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

    def check(system_key: str, device_id: str | None, refs) -> None:
        problems = list(dict.fromkeys(p for r in refs if (p := _ref_problem(r, index))))
        if problems:
            what = f"{device_id or 'The block'} " + "; ".join(problems) + "."
            out.append(Finding(rule, system_key, device_id, "must_fix", what, QUOTE_FIX))

    for system in job.systems:
        check(system.key, None, ai_evidence.system_refs(system))
        for device in system.devices:
            check(system.key, device.id, [*device.refs, *device.quantity.sources,
                                          *(o.ref for o in device.quantity.others)])
    if job.front_end is not None:
        for device in job.front_end.devices:
            check("", device.id, [*device.refs, *device.quantity.sources, *(o.ref for o in device.quantity.others)])
    for exception in job.exceptions:
        check("", None, exception.refs)
    return out


def _citation_rule(playbook: Playbook) -> str | None:
    """The Playbook rule the quote check reports under: the first rule of the evidence and citations topic."""
    return next((r.name for r in playbook.rules.values() if r.topic == CITATIONS_TOPIC), None)


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
            finding = replace(finding, device_id=None,
                              what=f"{finding.what} (about {finding.device_id}, which the written job does not have)")
        out.append(finding)
    return out, []


def qc_job(job: Job, evidence_index: Mapping[str, str], playbook: Playbook, transport: Transport) -> list[Finding]:
    """An independent reviewer's findings on the whole written job (one QC_JOB request, or one per part when the job
    is too long; schema {"findings": [Finding]}). Each Finding's `rule` is a Playbook rule name; `system_key` and
    `device_id` name what it is about. Raises NoAnswer as `write_system`.

    First a mechanical check: every Ref of the job cites a source of this job whose text holds its quote (a picture
    or a ledger fact aside); each device (or block) that fails is a must_fix finding under the Playbook's first
    evidence and citations rule. Then the reviewer, told those findings, gets the job and the text of every source
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
