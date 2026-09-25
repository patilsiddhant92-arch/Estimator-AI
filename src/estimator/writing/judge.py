"""The optional AI judge: which of a system's template lines the job's evidence really calls for.

Claude, through the Anthropic API, reads one system's evidence (schedule rows, notes, sequence
passages) and answers every offered template line with include or leave out, a quote from the
evidence and a confidence. It never writes a line of its own: answers naming a line that was not
offered are dropped and listed in `Judgement.dropped`.

The judge is optional. Without a key (`ANTHROPIC_API_KEY`) it is not `available`, and `judge()`
returns None with the reason in `last_error`; the caller marks those lines PENDING. The key is
never read, printed or stored here: the SDK takes it from the environment itself.

Each answer is cached by the model and the exact prompt, so the same system never costs twice.

In "chat" mode no API is called: each question is written to a requests folder for Claude to
answer in the Claude Code chat, and the answer, saved to the answers folder under the same name,
is picked up on the next run and cached like any other. Chat answers are cached under the model
name "claude (chat)", so switching to the API later judges every system afresh.

Request shape (checked against anthropic 1.8.0 and the current models):
- The answer comes back as JSON through structured outputs (`output_config.format`), not a
  forced tool call: current models such as claude-opus-5-5 refuse `tool_choice` "tool"/"any".
- No temperature: current models refuse sampling settings, and the SDK no longer takes one.
- Thinking is always on for claude-opus-5-5 and counts toward `max_tokens`, so the limit leaves
  room for it.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

import anthropic

DEFAULT_MODEL = "claude-opus-5-5"
MODEL_VARIABLE = "ESTIMATOR_MODEL"
KEY_VARIABLE = "ANTHROPIC_API_KEY"
MAX_TOKENS = 16000     # the answer plus the model's thinking, which counts toward the limit
TIMEOUT_SECONDS = 180.0
NO_EVIDENCE_CONFIDENCE = 0.5
NO_KEY = "judgement pending — no AI key set"
CACHE_VERSION = 1
API, CHAT = "api", "chat"
MODES = (API, CHAT)
CHAT_MODEL = "claude (chat)"   # the model name chat answers are cached under, apart from the API's

SYSTEM_PROMPT = """\
You are an HVAC controls estimator at AME. You are writing the scope of work for one system of a \
building controls proposal. The estimator's Master Template gives a list of possible lines for \
this system. Your job is to decide, from the job's own documents, which of those lines this job \
really calls for.

How to answer:
- Answer every numbered option: include true if the evidence calls for that line, false if it \
does not. Copy the option's text exactly as written.
- Never invent a line that is not in the options.
- Some options are alternatives to each other (for example, different space sensor types). \
Include only the one the evidence supports.
- For each option, quote the words from the evidence that decide it, copied exactly. If nothing \
in the evidence decides it, write "no evidence" as the reason, leave the quote empty, and give a \
confidence of 0.5 or less.
- Give a quantity only when the evidence states a count for that line. Otherwise the quantity is \
null. Never work one out or guess one.
- The reason is one sentence in plain English.
- Confidence is a number from 0 to 1.
- Client notes are short clarifications for the client that the evidence supports, such as \
"**Start/Stop via Fire Alarm System". Each starts with "**". Never include estimating hints, tech \
hours or prices. Give none if the evidence supports none."""


@dataclass(frozen=True)
class Choice:
    line: str            # exactly one of the offered option texts
    include: bool
    quantity: int | None # when the evidence states a count, else None
    why: str             # one sentence, plain English
    quote: str           # the words from the evidence that decide it ("" if none)
    confidence: float    # 0–1


@dataclass(frozen=True)
class Judgement:
    choices: tuple[Choice, ...]
    client_notes: tuple[str, ...]   # clarifications the evidence supports, each starting "**"
    model: str
    dropped: tuple[str, ...] = ()   # lines the model answered that were not offered, thrown away


class Judge:
    """mode "api": Claude answers through the Anthropic API. mode "chat": each question is written
    to `handoff_dir/requests/<key>.json` for Claude to answer in the chat, and the answer is read
    back from `handoff_dir/answers/<key>.json` on the next run. Both keep answers in the same cache,
    under different model names, so switching from the chat to the API judges afresh."""

    def __init__(self, cache_dir: Path, model: str | None = None, client=None, *, mode: str = API,
                 handoff_dir: Path | None = None):
        if mode not in MODES:
            raise ValueError(f"the AI mode must be one of {', '.join(MODES)}, not {mode!r}")
        self.mode = mode
        self.cache_dir = Path(cache_dir) / "judge"
        self.handoff_dir = Path(handoff_dir) if handoff_dir is not None else Path(cache_dir) / "judge-chat"
        if mode == CHAT:
            self.model = CHAT_MODEL
        else:
            self.model = model or os.environ.get(MODEL_VARIABLE) or DEFAULT_MODEL
        self._client = client
        self.last_error: str | None = None
        self.calls = 0              # answers the AI service gave on this run
        self.cached = 0             # answers taken from the cache, at no cost
        self.answered_in_chat = 0   # chat answers picked up from the answers folder on this run
        self.waiting = 0            # questions written to the requests folder, still to answer

    @property
    def requests_dir(self) -> Path:
        return self.handoff_dir / "requests"

    @property
    def answers_dir(self) -> Path:
        return self.handoff_dir / "answers"

    @property
    def available(self) -> bool:
        """The chat is always there; for the API, a client was given or a key is set in the
        environment (never read beyond that)."""
        if self.mode == CHAT:
            return True
        return self._client is not None or bool(os.environ.get(KEY_VARIABLE))

    def judge(self, system: str, evidence: str, options: list[str],
              rules: list[str]) -> Judgement | None:
        """Ask which options the evidence calls for. None, with `last_error` set, on any failure."""
        prompt = _prompt(system, evidence, options, rules)
        key = _key(self.model, prompt)
        cache_file = self.cache_dir / f"{key}.json"
        cached = _read_cache(cache_file)
        if cached is not None:
            self.last_error = None
            self.cached += 1
            return _judgement(cached["answer"], options, cached["model"])
        if self.mode == CHAT:
            return self._from_chat(key, system, prompt, options, cache_file)
        if not self.available:
            self.last_error = NO_KEY
            return None
        try:
            answer, model = self._ask(prompt, options)
        except Exception as error:  # the judge never raises into the pipeline
            self.last_error = _plain(error)
            return None
        _write_cache(cache_file, {"version": CACHE_VERSION, "model": model, "answer": answer})
        self.calls += 1
        self.last_error = None
        return _judgement(answer, options, model)

    def _from_chat(self, key: str, system: str, prompt: str, options: list[str],
                   cache_file: Path) -> Judgement | None:
        """The chat's answer when it is in the answers folder; otherwise a request for one."""
        request = self.requests_dir / f"{key}.json"
        answer_file = self.answers_dir / f"{key}.json"
        problem = None
        if answer_file.exists():
            answer = _read_answer(answer_file)
            if answer is not None:
                _write_cache(cache_file, {"version": CACHE_VERSION, "model": CHAT_MODEL, "answer": answer})
                request.unlink(missing_ok=True)
                self.answered_in_chat += 1
                self.last_error = None
                return _judgement(answer, options, CHAT_MODEL)
            problem = f"the answer for {system} could not be read"
        try:
            _write_json(request, {"key": key, "system": system, "system_prompt": SYSTEM_PROMPT,
                                  "prompt": prompt, "options": list(options), "schema": _schema(options),
                                  "answer_file": str(answer_file)}, indent=2)
        except OSError:
            self.last_error = f"judgement pending — the request for {system} could not be written to {request.parent}"
        else:
            self.waiting += 1
            self.last_error = f"judgement pending — waiting for an answer in the chat (requests folder: {request.parent})"
        if problem:
            self.last_error += f"; {problem}"
        return None

    def _ask(self, prompt: str, options: list[str]) -> tuple[dict, str]:
        response = self._get_client().messages.create(
            model=self.model,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
            output_config={"format": {"type": "json_schema", "schema": _schema(options)}},
        )
        stop = getattr(response, "stop_reason", None)
        if stop == "max_tokens":
            raise _Unusable("the AI answer was cut off before it finished")
        if stop == "refusal":
            raise _Unusable("the AI declined to answer for this system")
        text = "".join(block.text for block in response.content
                       if getattr(block, "type", None) == "text")
        try:
            answer = json.loads(text)
        except ValueError:
            raise _Unusable("the AI answer could not be read") from None
        if not isinstance(answer, dict) or not isinstance(answer.get("choices"), list):
            raise _Unusable("the AI answer could not be read")
        return answer, getattr(response, "model", None) or self.model

    def _get_client(self):
        if self._client is None:
            # The SDK finds the key in the environment itself; it is never handled here.
            self._client = anthropic.Anthropic(timeout=TIMEOUT_SECONDS)
        return self._client


class _Unusable(Exception):
    """A reply came back but cannot be used; the message is already in plain words."""


def _prompt(system: str, evidence: str, options: list[str], rules: list[str]) -> str:
    numbered = "\n".join(f"{n}. {option}" for n, option in enumerate(options, start=1))
    rule_text = "\n".join(f"- {rule}" for rule in rules) or "- (none)"
    return (f"System: {system}\n\n"
            f"Rules from the Master Template (what to look for, and hints):\n{rule_text}\n\n"
            f"Options (template lines):\n{numbered}\n\n"
            f"Evidence from the job's documents, each with its place:\n{evidence.strip() or '(none)'}")


def _schema(options: list[str]) -> dict:
    choice = {
        "type": "object",
        "properties": {
            "line": {"type": "string", "enum": list(options)},
            "include": {"type": "boolean"},
            "quantity": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
            "why": {"type": "string"},
            "quote": {"type": "string"},
            "confidence": {"type": "number"},
        },
        "required": ["line", "include", "quantity", "why", "quote", "confidence"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "choices": {"type": "array", "items": choice},
            "client_notes": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["choices", "client_notes"],
        "additionalProperties": False,
    }


def _judgement(answer: dict, options: list[str], model: str) -> Judgement:
    """Check the answer against the offer: unknown lines dropped, numbers kept in range."""
    offered = set(options)
    choices: list[Choice] = []
    seen: set[str] = set()
    dropped: list[str] = []
    for raw in answer.get("choices") or []:
        if not isinstance(raw, dict):
            continue
        line = str(raw.get("line", ""))
        if line not in offered:
            dropped.append(line)
            continue
        if line in seen:  # a second answer for the same line: the first one stands
            continue
        seen.add(line)
        quote = str(raw.get("quote") or "").strip()
        confidence = _confidence(raw.get("confidence"))
        if not quote:
            confidence = min(confidence, NO_EVIDENCE_CONFIDENCE)
        choices.append(Choice(line=line, include=raw.get("include") is True,
                              quantity=_quantity(raw.get("quantity")),
                              why=str(raw.get("why") or "").strip(), quote=quote,
                              confidence=confidence))
    notes = []
    for note in answer.get("client_notes") or []:
        note = str(note).strip()
        if note.lstrip("*").strip():
            notes.append(note if note.startswith("**") else "**" + note.lstrip("*").strip())
    return Judgement(choices=tuple(choices), client_notes=tuple(notes), model=model,
                     dropped=tuple(dropped))


def _confidence(value) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number != number:  # NaN
        return 0.0
    return max(0.0, min(1.0, number))


def _quantity(value) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _key(model: str, prompt: str) -> str:
    return hashlib.sha256(f"{CACHE_VERSION}\n{model}\n{SYSTEM_PROMPT}\n{prompt}".encode()).hexdigest()


def _read_cache(cache_file: Path) -> dict | None:
    try:
        data = json.loads(cache_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("version") != CACHE_VERSION \
            or not isinstance(data.get("answer"), dict):
        return None
    return data


def _read_answer(answer_file: Path) -> dict | None:
    """The chat's answer, in the shape the API returns, or None when it cannot be used."""
    try:
        answer = json.loads(answer_file.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    if not isinstance(answer, dict) or not isinstance(answer.get("choices"), list):
        return None
    return answer


def _write_json(path: Path, data: dict, indent: int | None = None) -> None:
    """Written whole or not at all: to a temporary name first, then swapped into place."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=indent), encoding="utf-8")
    os.replace(tmp, path)


def _write_cache(cache_file: Path, data: dict) -> None:
    try:
        _write_json(cache_file, data)
    except OSError:
        pass  # a cache that cannot be written only costs a second call next time


def _plain(error: Exception) -> str:
    """The reason a call failed, in plain words for the review list."""
    if isinstance(error, _Unusable):
        return str(error)
    if isinstance(error, anthropic.APITimeoutError):
        return "the AI service took too long to answer"
    if isinstance(error, anthropic.APIConnectionError):
        return "could not reach the AI service (check the internet connection)"
    if isinstance(error, anthropic.AuthenticationError):
        return "the AI service did not accept the key"
    if isinstance(error, anthropic.PermissionDeniedError):
        return "the AI key is not allowed to use this model"
    if isinstance(error, anthropic.NotFoundError):
        return "the AI service does not know the model (check ESTIMATOR_MODEL)"
    if isinstance(error, anthropic.RateLimitError):
        return "the AI service is busy (too many requests); try again later"
    if isinstance(error, anthropic.APIStatusError):
        return f"the AI service returned an error ({error.status_code})"
    return f"the AI call failed: {error}"
