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
  written again with the reason, the answer file left for run_job.py to count as rejected.
- `ApiTransport` — the Anthropic SDK (anthropic 1.8.0), streamed, structured output
  (`output_config={"format": {"type": "json_schema", "schema": schema}}`), no temperature, the Playbook rules as
  the first system block with `cache_control: {"type": "ephemeral"}` (prompt caching), the step's own instructions
  as the second; same cache folder and file form under the API model's name; the key from the environment only.
  An answer a step refuses is dropped from the cache and the question asked once more with the reason.

Request kinds (what `/run-job` dispatches on): `write_system` for both writing and revising a system (extra
`"step": "write" | "revise"`, `"plan_key": system.key`, `"images"`; a revise request's "system" is the system's name
with " (revise)"), `qc_job` for the QC pass (extra `"step": "qc"`). In chat mode the request's `system_prompt` is
the Playbook rules text, a blank line, then the step's instructions (`src/bms/prompts/`).

Ground rules the steps hold: every device cites this job's evidence by id (an answer citing an id the evidence does
not carry is refused); the Master Template shape is only the frame (slots and their print form, never a line);
every assumption says what and why; one clarification per block; the skeleton's planner fields always win.
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
SKELETON_FIELDS = ("key", "name", "shape", "control", "families", "sequence_refs", "alternate")
CITATIONS_TOPIC = "Evidence and citations"


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


def _problems(errors: list[str]) -> str:
    shown = "; ".join(errors[:MAX_PROBLEMS])
    return shown + (f"; and {len(errors) - MAX_PROBLEMS} more" if len(errors) > MAX_PROBLEMS else "")


# ---- the chat transport -----------------------------------------------------------------------------------------

class ChatTransport:
    """Questions as request files for the chat; answers read back on the next run (see the module doc)."""

    def __init__(self, cache_dir: Path, job: str, handoff_dir: Path | None = None) -> None:
        """`cache_dir` is the run's cache (answers kept in `cache_dir/judge`); `handoff_dir` defaults to
        `cache_dir/judge-chat`; `job` is `dossier.job_name`."""
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
    errors = schema_errors(answer, schema)
    return (None, errors) if errors else (answer, [])


# ---- the API transport ------------------------------------------------------------------------------------------

class ApiTransport:
    """Questions through the Anthropic API, with the Playbook cached (see the module doc)."""

    def __init__(self, cache_dir: Path, model: str | None = None, client=None) -> None:
        """`model` defaults to $ESTIMATOR_MODEL, else `estimator.writing.judge.DEFAULT_MODEL`; `client` is an
        `anthropic.Anthropic` (made from the environment when None; tests pass a fake)."""
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
    errors = schema_errors(answer, q.schema)
    if errors:
        raise NoAnswer(f"the answer for {q.name} could not be read: {_problems(errors)}")
    return answer


# ---- asking with the step's own checks -----------------------------------------------------------------------------

def _ask_checked(transport, kind: str, name: str, instructions: str, system_prompt: str, prompt: str, schema: dict,
                 extra: dict, images: Sequence[Path], check: Callable[[dict], tuple[object, list[str]]]):
    """Ask; run the step's `check` (value, problems) on the answer. An answer with problems is refused: the chat
    asks again on a later run (NoAnswer waiting); the API is asked once more now, with the reason."""
    answer = transport.ask(kind, name, instructions, system_prompt, prompt, schema, extra, images)
    value, problems = check(answer)
    if not problems:
        return value
    reason = f"the answer for {name} could not be used: {_problems(problems)}"
    refuse = getattr(transport, "refuse", None)
    if refuse is None:
        raise NoAnswer(reason)
    if not refuse(reason):
        raise NoAnswer(reason + " (asked again)", waiting=True)
    again = (f"{prompt}\n\nYour earlier answer to this question could not be used: {_problems(problems)}. "
             "Answer again, fixing that.")
    answer = transport.ask(kind, name, instructions, system_prompt, again, schema, extra, images)
    value, problems = check(answer)
    if problems:
        reason = f"the answer for {name} could not be used: {_problems(problems)}"
        refuse(reason)
        raise NoAnswer(reason)
    return value


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
    return "\n\n".join([
        "The system, as the planner set it up (copy these fields as they are):\n"
        + json.dumps(_skeleton_dict(system), indent=1, ensure_ascii=False),
        _shape_text(system, shape),
        f"Answer with the whole system as JSON in the schema given; number the devices {system.key}.d1, "
        f"{system.key}.d2 and so on, in print order.",
        "The evidence:\n" + evidence.strip()])


def _finding_text(n: int, finding: Finding) -> str:
    about = f"device {finding.device_id}" if finding.device_id else "the whole block"
    return f"{n}. [{finding.rule}] {about}: {finding.what} Fix: {finding.fix}"


def _revise_prompt(system: System, findings: Sequence[Finding], shape: Shape | None, evidence: str) -> str:
    return "\n\n".join([
        "The block as written:\n" + system.to_json(indent=1),
        "The findings to fix (must fix), and nothing else:\n"
        + "\n".join(_finding_text(n, f) for n, f in enumerate(findings, start=1)),
        _shape_text(system, shape),
        "Answer with the whole revised system as JSON in the schema given.",
        "The evidence:\n" + evidence.strip()])


def _ref_ids(refs) -> set[str]:
    return {str(r.source_id).strip().strip("[]") for r in refs}


def _all_refs(system: System) -> list[Ref]:
    refs = ai_evidence.system_refs(system)
    for device in system.devices:
        refs += list(device.refs) + list(device.quantity.sources) + [o.ref for o in device.quantity.others]
    return refs


def _check_system(answer, skeleton: System, shape: Shape | None, known: frozenset[str],
                  keep: Sequence[Device] = (), originals: Sequence[Device] = ()) -> tuple[System | None, list[str]]:
    """A System answer made usable, or the problems that stop it: the skeleton's fields win; untouched devices
    (`keep`) are put back as they were; every device cites the evidence; slots fit the shape; at most one
    clarification; every assumption says what and why; device ids unique and of this system."""
    if not isinstance(answer, dict):
        return None, ["the answer is not a JSON object"]
    answer = {**answer, **_skeleton_dict(skeleton)}
    if keep:
        answer = dict(answer, devices=_put_back(answer.get("devices"), keep, originals))
    errors = schema_errors(answer, json_schema(System))
    if errors:
        return None, [f"it breaks the schema at {e.removeprefix('$.')}" for e in errors]
    problems: list[str] = []
    kept_ids = {d.id for d in keep}
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
                f"{assumption['what']} {assumption['why']}", assumption["what"], assumption["why"])]
    if len(answer["clarifications"]) > 1:
        problems.append(f"it gives {len(answer['clarifications'])} clarifications; a block has at most one")
    for clarification in answer["clarifications"]:
        if not str(clarification["text"]).strip():
            problems.append("its clarification has no text")
        problems += [f"its clarification {p}" for p in _text_problems(clarification["text"], clarification["text"])]
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


_SOURCE_ID = re.compile(r"\[?\b[SQIFC]\d+[a-z]?\b\]?")
_LABEL = re.compile(r"^\s*(?:confirm\b|assumed\b|assumption\s*:|note\s*:|quantity\s+per\b|(?:as\s+)?per\s+drawings\b)",
                    re.I)


def _text_problems(text: str, *starts: str) -> list[str]:
    """What stops a text the client or the estimator reads: a source id in it (name the document in words), or a
    label at the start of one of `starts` (the renderer adds the label)."""
    problems = []
    ids = list(dict.fromkeys(m.group(0).strip("[]") for m in _SOURCE_ID.finditer(str(text or ""))))
    if ids:
        problems.append(f"names the source id {', '.join(ids)}: name the document in words "
                        "(\"the mechanical schedule\", \"the sequence of operations\") instead")
    if any(_LABEL.match(str(s or "")) for s in starts):
        problems.append("starts with a label (\"Confirm\", \"Assumed:\", \"Quantity per\"): leave it out, the "
                        "renderer adds it")
    return problems


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


def write_system(system: System, evidence: str, playbook: Playbook, transport: Transport) -> System:
    """The system with `devices`, `clarifications` and `tech_hours` filled from `evidence`.

    Contract: one WRITE_SYSTEM request (extra step "write", plan_key system.key) whose schema is
    `json_schema(System)`; the answer is checked with `schema_errors`, built with `System.from_dict`, and must keep
    the skeleton's `key`, `name`, `shape`, `control`, `families`, `sequence_refs` and `alternate` (the skeleton's
    values win). Every device has at least one Ref whose source_id is in the evidence. Raises NoAnswer when there
    is no answer yet (chat) or the answer cannot be used after the schema check.

    Also: the pictures the evidence names are attached; a ref to an id the evidence does not carry is dropped when
    the device has another, and a device with none, a slot outside the shape, more than one clarification or an
    assumption without its what or why refuses the answer (the chat asks again with the reason; the API is asked
    once more)."""
    shape = _shape(system, playbook)
    images, listing = _pictures(evidence)
    known = ai_evidence.cited_ids(evidence) | _ref_ids(ai_evidence.system_refs(system))
    return _ask_checked(transport, WRITE_SYSTEM, system.name, playbook.rules_text, _instructions("write_system"),
                        _write_prompt(system, shape, evidence), json_schema(System),
                        {"step": "write", "plan_key": system.key, "images": listing}, images,
                        lambda answer: _check_system(answer, system, shape, known))


def revise_system(system: System, findings: Sequence[Finding], evidence: str, playbook: Playbook,
                  transport: Transport) -> System:
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
    return _ask_checked(transport, WRITE_SYSTEM, f"{system.name} (revise)", playbook.rules_text,
                        _instructions("revise_system"), _revise_prompt(system, mine, shape, evidence),
                        json_schema(System), {"step": "revise", "plan_key": system.key, "images": listing}, images,
                        lambda answer: _check_system(answer, system, shape, known, keep, system.devices))


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
    written = {"name": job.name, "systems": [s.to_dict() for s in systems]}
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
    return "\n\n".join([
        f"Job: {job.name}",
        "The Playbook's rule names (a finding's rule is one of these, exactly):\n"
        + "\n".join(f"- {name}" for name in playbook.rules),
        "The shape of each block:\n" + "\n".join(shapes),
        "Mechanical findings already made (do not repeat them):\n"
        + ("\n".join(f"- {f.system_key or 'job'} {f.device_id or ''}: {f.what}" for f in found) or "(none)"),
        "The written job" + ("" if whole else " (this part)") + ":\n" + json.dumps(written, indent=1,
                                                                                    ensure_ascii=False),
        "The text of every source it cites, by id:\n" + ("\n".join(sources) or "(none)")])


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
