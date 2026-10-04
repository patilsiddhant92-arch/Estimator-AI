"""The optional AI judge: which of a system's template lines the job's evidence really calls for,
and, for a system the Master Template has no entry for, how to write it.

Two kinds of question:
- "choose" (`judge()`): Claude reads one system's evidence (schedule rows, notes, sequence
  passages) and answers every offered template line with include or leave out, a quote from the
  evidence and a confidence. Answers naming a line that was not offered are dropped and listed in
  `Judgement.dropped`. It may also add lines the evidence clearly calls for that no option covers
  (`Judgement.extra_lines`), such as an occupancy sensor the plans show.
- "compose" (`compose()`): for a system with no template, Claude writes the block itself, in the
  house style, shown the nearest templates and blocks from past proposals as examples.

The whole-job method adds two more (prompts and schemas in `estimator.ledger.passes` and whole_job.py):
- "read_pass" (`Judge.ask_pass`): one of the seven reading passes of `estimator.ledger`, each adding
  facts to the job ledger. The job's systems come from that ledger (`estimator.ledger.to_plan`).
- "write_system" (`Judge.write_system`): one pass per planned system writes its scope lines.

Every line Claude writes is checked against the house style (assets/house_style.json): a line
that does not start with a house verb, names hours or a price, is too long, or gives a quantity
or a reason with no quote is dropped and listed in `refused`, and so is a note that does not
start with "**".

The judge is optional. Without a key (`ANTHROPIC_API_KEY`) it is not `available`, and each
question returns None with the reason in `last_error`; the caller marks those lines PENDING. The
key is never read, printed or stored here: the SDK takes it from the environment itself.

Each answer is cached by the model and the exact prompt, so the same question never costs twice.

In "chat" mode no API is called: each question is written to a requests folder for Claude to
answer in the Claude Code chat, and the answer, saved to the answers folder under the same name,
is picked up on the next run and cached like any other. Each request says its kind ("choose" or
"compose") and carries the schema its answer follows. Chat answers are cached under the model
name "claude (chat)", so switching to the API later judges every system afresh.

Request shape (checked against anthropic 1.8.0 and the current models):
- The answer comes back as JSON through structured outputs (`output_config.format`), not a
  forced tool call: current models such as claude-opus-5-5 refuse `tool_choice` "tool"/"any".
- No temperature: current models refuse sampling settings, and the SDK no longer takes one.
- Thinking is always on for claude-opus-5-5 and counts toward `max_tokens`, so the limit leaves
  room for it.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path

import anthropic

from estimator.writing.style import HouseStyle, load_house_style

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
CHOOSE, COMPOSE = "choose", "compose"
READ_PASS = "read_pass"
KINDS = (CHOOSE, COMPOSE)
_MAIN_LIST = {CHOOSE: "choices", COMPOSE: "lines", READ_PASS: "facts"}   # the list an answer of each kind must carry
MAX_ANALOGS, MAX_EXAMPLES = 3, 4
MAX_DEPTH = 5
MAX_HEADER = 80
TECH_HOUR_BASES = ("unit", "hardware_point", "indoor_unit", "panel", "fan", "fixed", "line")

SYSTEM_PROMPT = """\
You are an HVAC controls estimator at AME. You are writing the scope of work for one system of a \
building controls proposal. The estimator's Master Template gives a list of possible lines for \
this system. Your job is to decide, from the job's own documents, which of those lines this job \
really calls for.

How to answer:
- Answer every numbered option: include true if the evidence calls for that line, false if it \
does not. Copy the option's text exactly as written.
- Never put a line that is not in the options among the choices.
- Some options are alternatives to each other (for example, different space sensor types). \
Include only the one the evidence supports.
- For each option, quote the words from the evidence that decide it, copied exactly. If nothing \
in the evidence decides it, write "no evidence" as the reason, leave the quote empty, and give a \
confidence of 0.5 or less.
- Give a quantity only when the evidence states a count for that line. Otherwise the quantity is \
null. Never work one out or guess one.
- The reason is one sentence in plain English.
- Confidence is a number from 0 to 1.
- Extra lines: when the evidence clearly calls for something no option covers (for example \
occupancy sensors the plans show as OCC), add it to extra_lines, written the way AME writes a \
line: it starts with one of the house verbs given, and it is at most 160 characters. Each extra \
line needs a reason and a quote from the evidence. Never repeat an option there. Give none when \
the options cover the evidence.
- Client notes are short clarifications for the client that the evidence supports, such as \
"**Start/Stop via Fire Alarm System". Each starts with "**". Never include estimating hints, tech \
hours or prices. Give none if the evidence supports none."""

COMPOSE_PROMPT = """\
You are an HVAC controls estimator at AME. You are writing the scope of work for one system of a \
building controls proposal. The estimator's Master Template has no entry for this system, so you \
write its block yourself, from the job's own documents, in AME's house style. You are shown the \
house style, the Master Template entries nearest to this system (their lines and when each one \
applies), and blocks AME wrote for similar systems in past proposals.

How to answer:
- header: only the kind of equipment, in plain words, the way a block header names it (for \
example "Electric Duct Heater"). Never the count or the tags: they are added for you.
- lines: the scope lines this job's evidence calls for, in the order a proposal lists them, in the \
house style. Depth 1 sits under the header; depth 2 under the line above it.
- Every line needs a one-sentence reason in plain English and a quote: the words from the \
evidence that call for it, copied exactly. Write no line the evidence does not support.
- Give a quantity only when the evidence states a count for that line. Otherwise the quantity is \
null. Never work one out or guess one.
- Confidence is a number from 0 to 1.
- client_notes: short clarifications for the client that the evidence supports, each starting \
with "**". Never estimating hints, tech hours or prices. Give none if the evidence supports none.
- tech_hours: the tech hours you suggest, following the nearest Master Template entry: what they \
are counted per, how many hours, and which entry they are like (its name exactly as given). Null \
when no entry is close enough.
- Never write prices, tech hours, confidence or category words in a line, the header or a note."""


@dataclass(frozen=True)
class Choice:
    line: str            # exactly one of the offered option texts
    include: bool
    quantity: int | None # when the evidence states a count, else None
    why: str             # one sentence, plain English
    quote: str           # the words from the evidence that decide it ("" if none)
    confidence: float    # 0–1


@dataclass(frozen=True)
class WrittenLine:
    """A line the AI wrote itself: beyond a template's options, or for a system with no template."""
    text: str
    depth: int
    quantity: int | None # only when the evidence states the count (then the quote holds it)
    why: str
    quote: str           # never empty
    confidence: float


@dataclass(frozen=True)
class TechHoursHint:
    per: str             # one of TECH_HOUR_BASES
    hours: float
    like: str            # the Master Template entry they follow, by name (checked by the writer)


@dataclass(frozen=True)
class Judgement:
    choices: tuple[Choice, ...]
    client_notes: tuple[str, ...]   # clarifications the evidence supports, each starting "**"
    model: str
    dropped: tuple[str, ...] = ()   # lines the model answered that were not offered, thrown away
    extra_lines: tuple[WrittenLine, ...] = ()   # lines the evidence calls for that no option covers
    refused: tuple[str, ...] = ()   # what it wrote that breaks the house style, and why


@dataclass(frozen=True)
class Composition:
    header: str                      # the kind wording only; "" when it could not be used
    lines: tuple[WrittenLine, ...]
    client_notes: tuple[str, ...]
    tech_hours: TechHoursHint | None
    model: str
    refused: tuple[str, ...] = ()


class Judge:
    """mode "api": Claude answers through the Anthropic API. mode "chat": each question is written
    to `handoff_dir/requests/<key>.json` for Claude to answer in the chat, and the answer is read
    back from `handoff_dir/answers/<key>.json` on the next run. Both keep answers in the same cache,
    under different model names, so switching from the chat to the API judges afresh."""

    def __init__(self, cache_dir: Path, model: str | None = None, client=None, *, mode: str = API,
                 handoff_dir: Path | None = None, style: HouseStyle | None = None, job: str | None = None):
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
        self._style = style
        self.job = job                  # the job a chat request is for (written into each request)
        self.retired: list[str] = []    # this job's requests moved into requests/old/ at the start of the run
        self.unrecorded = 0             # requests recording no job, moved into requests/old/ at the start of the run
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
    def old_requests_dir(self) -> Path:
        return self.requests_dir / "old"

    def retire_requests(self, sources: dict | None = None) -> int:
        """At the start of a chat run the requests folder is cleaned: every request for this job (all of them
        are from an older run of it) and every request whose job is not recorded moves into requests/old/.
        Only another job's requests stay. The questions the run still asks are written again (and leave old/);
        the answers are never touched. A request from before requests said their job is this job's when it is a
        reading pass whose prompt names the job's number, or a scope question whose places are this dossier's
        (`sources`); either way it moves. Returns how many were moved."""
        if self.mode != CHAT or not self.job or not self.requests_dir.is_dir():
            return 0
        moved = 0
        for path in sorted(self.requests_dir.glob("*.json")):
            try:
                request = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                request = None                      # it records no job that can be read
            recorded = isinstance(request, dict) and bool(request.get("job"))
            mine = isinstance(request, dict) and _for_job(request, self.job, sources)
            if recorded and not mine:
                continue                            # another job's request
            try:
                self.old_requests_dir.mkdir(parents=True, exist_ok=True)
                os.replace(path, self.old_requests_dir / path.name)
            except OSError:
                continue
            moved += 1
            if mine:
                self.retired.append(path.name)
            else:
                self.unrecorded += 1
        return moved

    def stale_requests(self) -> int:
        """How many of the requests moved into requests/old/ at the start of this run were not asked again."""
        return sum(1 for name in self.retired if (self.old_requests_dir / name).exists())

    @property
    def style(self) -> HouseStyle:
        if self._style is None:
            self._style = load_house_style()
        return self._style

    @property
    def available(self) -> bool:
        """The chat is always there; for the API, a client was given or a key is set in the
        environment (never read beyond that)."""
        if self.mode == CHAT:
            return True
        return self._client is not None or bool(os.environ.get(KEY_VARIABLE))

    # -- the two kinds of question
    def judge(self, system: str, evidence: str, options: list[str],
              rules: list[str]) -> Judgement | None:
        """Ask which options the evidence calls for. None, with `last_error` set, on any failure."""
        prompt = _prompt(system, evidence, options, rules, self.style)
        got = self._answer(CHOOSE, system, SYSTEM_PROMPT, prompt, _schema(options),
                           {"options": list(options)})
        if got is None:
            return None
        answer, model = got
        return _judgement(answer, options, model, self.style)

    def compose(self, system: str, evidence: str, examples, style: HouseStyle | None,
                analogs) -> Composition | None:
        """Write the block of a system with no template, from its evidence, in the house style,
        like the analog templates (up to 3) and the phrasing-bank examples (up to 4). None, with
        `last_error` set, on any failure."""
        style = style or self.style
        analogs = list(analogs)[:MAX_ANALOGS]
        prompt = _compose_prompt(system, evidence, list(examples)[:MAX_EXAMPLES], style, analogs)
        got = self._answer(COMPOSE, system, COMPOSE_PROMPT, prompt, _compose_schema(),
                           {"analogs": [a.name for a in analogs]})
        if got is None:
            return None
        answer, model = got
        return _composition(answer, model, style)

    # -- shared: the cache, the API and the chat hand-off
    def _answer(self, kind: str, system: str, system_prompt: str, prompt: str, schema: dict,
                extra: dict) -> tuple[dict, str] | None:
        key = _key(self.model, prompt, system_prompt)
        cache_file = self.cache_dir / f"{key}.json"
        cached = _read_cache(cache_file, kind)
        if cached is not None:
            self.last_error = None
            self.cached += 1
            return cached["answer"], cached["model"]
        if self.mode == CHAT:
            return self._from_chat(kind, key, system, system_prompt, prompt, schema, extra, cache_file)
        if not self.available:
            self.last_error = NO_KEY
            return None
        try:
            answer, model = self._ask(kind, system_prompt, prompt, schema)
        except Exception as error:  # the judge never raises into the pipeline
            self.last_error = _plain(error)
            return None
        _write_cache(cache_file, {"version": CACHE_VERSION, "kind": kind, "model": model, "answer": answer})
        self.calls += 1
        self.last_error = None
        return answer, model

    def _from_chat(self, kind: str, key: str, system: str, system_prompt: str, prompt: str, schema: dict,
                   extra: dict, cache_file: Path) -> tuple[dict, str] | None:
        """The chat's answer when it is in the answers folder; otherwise a request for one."""
        request = self.requests_dir / f"{key}.json"
        answer_file = self.answers_dir / f"{key}.json"
        problem = None
        if answer_file.exists():
            answer = _read_answer(answer_file, kind)
            if answer is not None:
                _write_cache(cache_file, {"version": CACHE_VERSION, "kind": kind, "model": CHAT_MODEL,
                                          "answer": answer})
                request.unlink(missing_ok=True)
                self.answered_in_chat += 1
                self.last_error = None
                return answer, CHAT_MODEL
            problem = f"the answer for {system} could not be read"
        try:
            _write_json(request, {"key": key, "kind": kind, "system": system,
                                  **({"job": self.job} if self.job else {}), "system_prompt": system_prompt,
                                  "prompt": prompt, **extra, "schema": schema,
                                  "answer_file": str(answer_file)}, indent=2)
            (self.old_requests_dir / request.name).unlink(missing_ok=True)      # asked again: no longer stale
        except OSError:
            self.last_error = f"judgement pending — the request for {system} could not be written to {request.parent}"
        else:
            self.waiting += 1
            self.last_error = f"judgement pending — waiting for an answer in the chat (requests folder: {request.parent})"
        if problem:
            self.last_error += f"; {problem}"
        return None

    def _ask(self, kind: str, system_prompt: str, prompt: str, schema: dict) -> tuple[dict, str]:
        response = self._get_client().messages.create(
            model=self.model,
            max_tokens=MAX_TOKENS,
            system=system_prompt,
            messages=[{"role": "user", "content": prompt}],
            output_config={"format": {"type": "json_schema", "schema": schema}},
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
        if not _fits(answer, kind):
            raise _Unusable("the AI answer could not be read")
        return answer, getattr(response, "model", None) or self.model

    def _get_client(self):
        if self._client is None:
            # The SDK finds the key in the environment itself; it is never handled here.
            self._client = anthropic.Anthropic(timeout=TIMEOUT_SECONDS)
        return self._client

    # -- a third kind of question: a schedule that is a picture, read by eye
    def read_schedule(self, image: Path, sheet: str | None, page: int, title_hint: str,
                      tiles: tuple[Path, ...] = ()) -> dict | None:
        """Read the schedules in one picture cut out of a drawing sheet (a PNG): {"schedules": [{title,
        headers, rows: [{cells}], notes}]}, every cell copied as printed and "" where it can't be read.
        `tiles` are the same picture in pieces, when it is too big to send whole. Same cache and hand-off as
        the other questions: in chat mode the request names the PNG for Claude to open in the chat; through
        the API the picture goes as image blocks. None, with `last_error` set, when there is no answer."""
        images = tuple(Path(p) for p in tiles) or (Path(image),)
        prompt = _read_schedule_prompt(sheet, page, title_hint, images)
        system = f"{sheet or 'sheet'} (page {page}) picture {Path(image).stem}"
        extra = {"image": str(image), "tiles": [str(p) for p in tiles], "sheet": sheet, "page": page,
                 "title_hint": title_hint}
        if self.mode == CHAT:
            got = self._answer(READ_SCHEDULE, system, READ_SCHEDULE_PROMPT, prompt, _read_schedule_schema(), extra)
            return got[0] if got is not None else None
        cache_file = self.cache_dir / f"{_key(self.model, prompt, READ_SCHEDULE_PROMPT)}.json"
        cached = _read_cache(cache_file, READ_SCHEDULE)
        if cached is not None:
            self.last_error = None
            self.cached += 1
            return cached["answer"]
        if not self.available:
            self.last_error = NO_KEY
            return None
        try:
            answer, model = self._ask_with_images(READ_SCHEDULE_PROMPT, prompt, _read_schedule_schema(), images)
        except Exception as error:  # the judge never raises into the pipeline
            self.last_error = _plain(error)
            return None
        _write_cache(cache_file, {"version": CACHE_VERSION, "kind": READ_SCHEDULE, "model": model, "answer": answer})
        self.calls += 1
        self.last_error = None
        return answer

    def _ask_with_images(self, system_prompt: str, prompt: str, schema: dict,
                         images: tuple[Path, ...]) -> tuple[dict, str]:
        content = [{"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                 "data": base64.standard_b64encode(p.read_bytes()).decode("ascii")}}
                   for p in images]
        response = self._get_client().messages.create(
            model=self.model,
            max_tokens=MAX_TOKENS,
            system=system_prompt,
            messages=[{"role": "user", "content": [*content, {"type": "text", "text": prompt}]}],
            output_config={"format": {"type": "json_schema", "schema": schema}},
        )
        stop = getattr(response, "stop_reason", None)
        if stop == "max_tokens":
            raise _Unusable("the AI answer was cut off before it finished")
        if stop == "refusal":
            raise _Unusable("the AI declined to read this picture")
        text = "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
        try:
            answer = json.loads(text)
        except ValueError:
            raise _Unusable("the AI answer could not be read") from None
        if not _fits(answer, READ_SCHEDULE):
            raise _Unusable("the AI answer could not be read")
        return answer, getattr(response, "model", None) or self.model

    # -- the whole-job questions (read_pass, write_system): see whole_job.py and estimator.ledger --------
    # Added for the whole-job method; the questions above are unchanged. The shapes, prompts, schemas
    # and checks live in whole_job.py (imported here, not at the top, as it imports this module).

    def write_system(self, system, evidence_text: str, images, options, examples, style_text: str,
                     hours_rule: str = "", image_ids=None, ledger_text: str = "", facts=(), counts=(),
                     brief: str = "", klass: str = "", owned_elsewhere=(), heater_class: str = "",
                     heater_home=("", "")):
        """Write one planned system's scope (a `whole_job.WrittenScope`) from its evidence, with the
        nearest Master Template's lines as a checklist (`options`: a template, its lines or plain
        texts), its tech-hour rule in words (`hours_rule`) and up to 4 phrasing-bank `examples`. None,
        with `last_error` set, on any failure. `image_ids` are the pictures' job-wide ids (I15, I17): the
        request cites them as the plan and the dossier do, never renumbered from I1. `brief` (the job brief) and
        `klass` (packaged or field) go into the request; after the ledger check the house check runs, with
        `owned_elsewhere` (item -> the system that owns it) keeping shared items with their owner, and
        `heater_class` (the class of the unit a duct heater serves) deciding a duct heater's own lines with the
        evidence (a sequence giving the BMS the heater's control keeps its full scope), and `heater_home` (the
        heaters' tags and their block's header) refusing duct heater lines in a unit whose heaters have a block."""
        from estimator.writing import whole_job as wj
        from estimator.writing.house_check import house_check
        images = list(images or ())
        ids = list(image_ids) if image_ids is not None and len(image_ids) == len(images) else None
        known = wj.known_ids(evidence_text, images, ids)
        if known:
            plan_ids = (system.quantity_source, *system.sequence_sources, *system.schedule_sources,
                        *str(getattr(system, "sequence_section", "") or "").split(","),
                        *(f.quantity_source for f in getattr(system, "families", ()) or ()))
            known = known | {wj.source_key(s) for s in plan_ids if s and s.strip()}
        prompt = wj.write_prompt(system, evidence_text, images, options, examples, style_text, hours_rule, ids,
                                 ledger_text=ledger_text, brief=brief, klass=klass)
        got = self._answer_with_images(WRITE_SYSTEM, system.header, wj.WRITE_PROMPT, prompt, wj.write_schema(),
                                       {"plan_key": system.key, "images": wj.images_listing(images, ids)}, images,
                                       ids)
        if got is None:
            return None
        answer, model = got
        scope = wj.parse_scope(answer, model, self.style, known)
        scope = wj.ledger_check(scope, frozenset(facts or ()), frozenset(int(c) for c in (counts or ())))
        return house_check(scope, system, klass, dict(owned_elsewhere or ()), self.style, heater_class=heater_class,
                           heater_home=tuple(heater_home or ("", "")), evidence=evidence_text)

    def ask_pass(self, name: str, system_prompt: str, prompt: str, schema: dict, images=(), extra: dict | None = None,
                 ids=None) -> tuple[dict, str] | None:
        """One reading pass of the job ledger (estimator.ledger.passes): the answer and the model, or None with
        `last_error` set (in chat mode, a request written for the chat and `waiting` counted)."""
        from estimator.writing import whole_job as wj
        images = list(images or ())
        return self._answer_with_images(READ_PASS, name, system_prompt, prompt, schema,
                                        {**(extra or {}), "images": wj.images_listing(images, ids)}, images, ids)

    def qc_job(self, name: str, system_prompt: str, prompt: str, schema: dict,
               extra: dict | None = None) -> tuple[dict, str] | None:
        """The proposal QC pass over the written draft (or one part of it; see qc.py): the answer and the model,
        or None with `last_error` set (in chat mode, a request written for the chat and `waiting` counted)."""
        return self._answer_with_images(QC_JOB, name, system_prompt, prompt, schema, dict(extra or {}), [])

    def _answer_with_images(self, kind: str, name: str, system_prompt: str, prompt: str, schema: dict,
                            extra: dict, images, ids=None) -> tuple[dict, str] | None:
        """As `_answer`, for a long question that may carry pictures: the pictures' contents are part
        of the cache key, the API gets them as image blocks and the chat request lists their paths."""
        from estimator.writing import whole_job as wj
        key = _key(self.model, prompt + wj.images_fingerprint(images, ids), system_prompt)
        cache_file = self.cache_dir / f"{key}.json"
        cached = _read_cache(cache_file, kind)
        if cached is not None:
            self.last_error = None
            self.cached += 1
            return cached["answer"], cached["model"]
        if self.mode == CHAT:
            return self._from_chat(kind, key, name, system_prompt, prompt, schema, extra, cache_file)
        if not self.available:
            self.last_error = NO_KEY
            return None
        try:
            answer, model = self._ask_long(kind, system_prompt, wj.content_blocks(prompt, images, ids), schema)
        except Exception as error:  # the judge never raises into the pipeline
            self.last_error = _plain(error)
            return None
        _write_cache(cache_file, {"version": CACHE_VERSION, "kind": kind, "model": model, "answer": answer})
        self.calls += 1
        self.last_error = None
        return answer, model

    def _ask_long(self, kind: str, system_prompt: str, content, schema: dict) -> tuple[dict, str]:
        """A long question with a long answer: streamed (so a big answer never meets the HTTP
        timeout) when the client can, with room for the model's thinking."""
        params = dict(model=self.model, max_tokens=WHOLE_JOB_MAX_TOKENS, system=system_prompt,
                      messages=[{"role": "user", "content": content}],
                      output_config={"format": {"type": "json_schema", "schema": schema}},
                      timeout=WHOLE_JOB_TIMEOUT_SECONDS)
        messages = self._get_client().messages
        if hasattr(messages, "stream"):
            with messages.stream(**params) as stream:
                response = stream.get_final_message()
        else:
            response = messages.create(**params)
        return _read_response(response, kind, self.model)


_JOB_NUMBER = re.compile(r"\b\d{2}-\d{4}\b")
_CITED_PLACE = re.compile(r"^\[S\d+\]\s+(.+?)\s*$", re.M)


def _for_job(request: dict, job: str, sources: dict | None) -> bool:
    """The request is for this job: it says so, or (a request from before requests said their job) it is a
    reading pass or a QC pass whose prompt names the job's number, or a scope question whose cited places are this dossier's."""
    said = request.get("job")
    if said:
        return said == job
    number = _JOB_NUMBER.search(job or "")
    prompt = str(request.get("prompt") or "")
    if request.get("kind") in (READ_PASS, QC_JOB):
        return bool(number) and number.group(0) in prompt[:400]      # a pass prompt starts "Job: <name>"
    if request.get("kind") == WRITE_SYSTEM and sources:
        places = set(sources.values())
        cited = _CITED_PLACE.findall(prompt)
        found = sum(1 for place in cited if place in places)
        return found >= max(1, round(0.3 * len(cited)))
    return False


class _Unusable(Exception):
    """A reply came back but cannot be used; the message is already in plain words."""


def _fits(answer, kind: str) -> bool:
    return isinstance(answer, dict) and isinstance(answer.get(_MAIN_LIST[kind]), list)


# --- the choose question -------------------------------------------------------------------------------

def _prompt(system: str, evidence: str, options: list[str], rules: list[str],
            style: HouseStyle | None = None) -> str:
    style = style or load_house_style()
    numbered = "\n".join(f"{n}. {option}" for n, option in enumerate(options, start=1))
    rule_text = "\n".join(f"- {rule}" for rule in rules) or "- (none)"
    return (f"System: {system}\n\n"
            f"Rules from the Master Template (what to look for, and hints):\n{rule_text}\n\n"
            f"Options (template lines):\n{numbered}\n\n"
            f"House verbs for an extra line: {'; '.join(style.verbs)}. Without a verb, only: "
            f"{'; '.join(style.no_verb_starts)}.\n\n"
            f"Evidence from the job's documents, each with its place:\n{evidence.strip() or '(none)'}")


def _line_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "depth": {"type": "integer"},
            "quantity": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
            "why": {"type": "string"},
            "quote": {"type": "string"},
            "confidence": {"type": "number"},
        },
        "required": ["text", "depth", "quantity", "why", "quote", "confidence"],
        "additionalProperties": False,
    }


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
            "extra_lines": {"type": "array", "items": _line_schema()},
            "client_notes": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["choices", "extra_lines", "client_notes"],
        "additionalProperties": False,
    }


def _judgement(answer: dict, options: list[str], model: str, style: HouseStyle) -> Judgement:
    """Check the answer against the offer: unknown lines dropped, numbers kept in range, extra
    lines and notes checked against the house style."""
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
    refused: list[str] = []
    known = {_squash(o).lower() for o in options}
    extras = _written_lines(answer.get("extra_lines"), style, refused, skip=known)
    notes = []
    for note in answer.get("client_notes") or []:
        note = str(note).strip()
        if not note.lstrip("*").strip():
            continue
        note = note if note.startswith("**") else "**" + note.lstrip("*").strip()
        bad = style.forbidden(note)
        if bad:
            refused.append(f"the note “{note}” — {bad}")
            continue
        notes.append(note)
    return Judgement(choices=tuple(choices), client_notes=tuple(notes), model=model,
                     dropped=tuple(dropped), extra_lines=tuple(extras), refused=tuple(refused))


# --- the compose question ------------------------------------------------------------------------------

def _hours_text(template) -> str:
    parts = []
    for th in (template.tech_hours, *template.extra_tech_hours):
        if th.hours is None:
            parts.append("none given")
            continue
        text = f"{th.hours:g} h per {th.per.replace('_', ' ')}"
        if th.of:
            text += f" (counting {', '.join(th.of)})"
        for when, hours in th.overrides:
            text += f"; {hours:g} h when {' and '.join(when)}"
        parts.append(text)
    return " + ".join(parts)


def _template_text(template) -> str:
    """One analog template: its lines, when each applies, the conditions' words and its tech hours."""
    out = [f"Entry: {template.name} (tech hours: {_hours_text(template)})", "  Lines:"]
    for line in template.lines:
        when = []
        if line.when:
            when.append("when " + " and ".join(line.when))
        if line.unless:
            when.append("not when " + " or ".join(line.unless))
        if line.choice:
            when.append(f"one choice of {line.choice}" + (" (the default)" if line.default else ""))
        elif line.default and not line.when:
            when.append("by default")
        out.append(f"  {'  ' * (line.depth - 1)}- {line.text}" + (f" [{'; '.join(when)}]" if when else ""))
    if template.conditions:
        out.append("  Conditions:")
        for name, c in template.conditions.items():
            places = [f"{', '.join(repr(w) for w in getattr(c, p))} in the {p.replace('_', ' ')}"
                      for p in ("schedule", "sequence", "notes", "prefix", "spec_overview") if getattr(c, p)]
            out.append(f"  - {name}: any of {'; or '.join(places)}")
    if template.client_notes:
        out.append("  Client notes: " + "; ".join(template.client_notes))
    return "\n".join(out)


def _example_text(example: dict) -> str:
    out = [f"From job {example.get('job', '?')}: {example.get('header', '')}"]
    for line in example.get("lines", ()):
        out.append(f"  {'  ' * (int(line.get('depth', 1)) - 1)}- {line.get('text', '')}")
    for note in example.get("notes", ()):
        out.append(f"  {note}")
    return "\n".join(out)


def _compose_prompt(system: str, evidence: str, examples, style: HouseStyle, analogs) -> str:
    analog_text = "\n\n".join(_template_text(t) for t in analogs) or "(none close enough)"
    example_text = "\n\n".join(_example_text(e) for e in examples) or "(none)"
    return (f"System: {system}\n\n"
            f"{style.prompt_text()}\n\n"
            f"The Master Template entries nearest to this system (how AME writes systems like it):\n"
            f"{analog_text}\n\n"
            f"Blocks AME wrote for similar systems in past proposals:\n{example_text}\n\n"
            f"Evidence from the job's documents, each with its place:\n{evidence.strip() or '(none)'}")


def _compose_schema() -> dict:
    hours = {
        "type": "object",
        "properties": {
            "per": {"type": "string", "enum": list(TECH_HOUR_BASES)},
            "hours": {"type": "number"},
            "like": {"type": "string"},
        },
        "required": ["per", "hours", "like"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "header": {"type": "string"},
            "lines": {"type": "array", "items": _line_schema()},
            "client_notes": {"type": "array", "items": {"type": "string"}},
            "tech_hours": {"anyOf": [hours, {"type": "null"}]},
        },
        "required": ["header", "lines", "client_notes", "tech_hours"],
        "additionalProperties": False,
    }


def _composition(answer: dict, model: str, style: HouseStyle) -> Composition:
    refused: list[str] = []
    header = _squash(re.sub(r"^\s*Qty\s*\([^)]*\)\s*", "", str(answer.get("header") or "")))
    bad = style.forbidden(header) or ("it is longer than a header" if len(header) > MAX_HEADER else None)
    if bad:
        refused.append(f"the header “{header}” — {bad}")
        header = ""
    lines = _written_lines(answer.get("lines"), style, refused)
    notes = []
    for note in answer.get("client_notes") or []:
        note = _squash(str(note))
        if not note:
            continue
        bad = style.check_note(note)
        if bad:
            refused.append(f"the note “{note}” — {bad}")
            continue
        notes.append(note)
    return Composition(header=header, lines=tuple(lines), client_notes=tuple(notes),
                       tech_hours=_tech_hours(answer.get("tech_hours"), refused), model=model,
                       refused=tuple(refused))


def _tech_hours(raw, refused: list[str]) -> TechHoursHint | None:
    if raw is None:
        return None
    try:
        per, hours, like = raw["per"], float(raw["hours"]), _squash(str(raw["like"]))
    except (TypeError, KeyError, ValueError):
        refused.append("the tech hours suggestion could not be read")
        return None
    if per not in TECH_HOUR_BASES or not math.isfinite(hours) or hours < 0 or not like:
        refused.append(f"the tech hours suggestion ({raw}) could not be used")
        return None
    return TechHoursHint(per, hours, like)


# --- checking what the AI wrote --------------------------------------------------------------------------

def _written_lines(raw_lines, style: HouseStyle, refused: list[str], skip=frozenset()) -> list[WrittenLine]:
    """The lines that follow the house style; each one that does not is listed in `refused`."""
    kept: list[WrittenLine] = []
    seen: set[str] = set()
    for raw in raw_lines or []:
        if not isinstance(raw, dict):
            continue
        text = _squash(str(raw.get("text") or ""))
        if not text or text.lower() in skip or text.lower() in seen:
            continue
        quote = _squash(str(raw.get("quote") or ""))
        why = _squash(str(raw.get("why") or ""))
        quantity = _quantity(raw.get("quantity"))
        reason = style.check_line(text, _depth(raw.get("depth")))
        if reason is None and quantity is not None and not quote:
            reason = "it gives a quantity with no quote to show it"
        if reason is None and not quote:
            reason = "it gives no quote from the evidence"
        if reason is None and not why:
            reason = "it gives no reason"
        if reason:
            refused.append(f"“{text}” — {reason}")
            continue
        seen.add(text.lower())
        kept.append(WrittenLine(text=text, depth=_depth(raw.get("depth")), quantity=quantity, why=why,
                                quote=quote, confidence=_confidence(raw.get("confidence"))))
    return kept


def _squash(text: str) -> str:
    return " ".join((text or "").split())


def _depth(value) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return 1
    return max(1, min(MAX_DEPTH, value))


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


# --- the read_schedule question: a schedule that is a picture ------------------------------------------------

READ_SCHEDULE = "read_schedule"
_MAIN_LIST[READ_SCHEDULE] = "schedules"

READ_SCHEDULE_PROMPT = """\
You are reading equipment schedules from a picture cut out of a building drawing sheet (HVAC, \
plumbing or controls). An estimator will count and price the units from what you copy, so copy, \
never interpret.

How to answer:
- Give every schedule in the picture: its title as printed, its column headers from left to \
right, one row for each printed row, and the notes printed with it.
- A header over several sub-columns is joined to each sub-header, for example "ELECTRICAL VOLTS".
- Each row gives one cell per header, in the same order as the headers.
- Copy every cell exactly as printed, character for character, with its dashes, units and \
abbreviations. Write "" for an empty cell, and "" for any cell you cannot read with certainty.
- Never guess, complete, correct or work out a value. Never add a row that is not printed. \
Leave out rows that are wholly blank.
- Give each note whole, with its number, as printed.
- When several images are given, they are consecutive pieces of one picture, overlapping a \
little: read them as one picture and give each row once.
- If the picture holds no schedule, give no schedules."""


def _read_schedule_prompt(sheet: str | None, page: int, title_hint: str, images) -> str:
    names = "; ".join(f"{p.name} (sha1 {hashlib.sha1(p.read_bytes()).hexdigest()})" for p in images)
    return (f"Sheet: {sheet or '(no sheet number)'}, page {page}\n"
            f"What the sheet's own text suggests it schedules: {title_hint or '(nothing readable)'}\n"
            f"Picture: {names}\n\n"
            f"Copy every schedule in the picture.")


def _read_schedule_schema() -> dict:
    row = {
        "type": "object",
        "properties": {"cells": {"type": "array", "items": {"type": "string"}}},
        "required": ["cells"],
        "additionalProperties": False,
    }
    schedule = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "headers": {"type": "array", "items": {"type": "string"}},
            "rows": {"type": "array", "items": row},
            "notes": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["title", "headers", "rows", "notes"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {"schedules": {"type": "array", "items": schedule}},
        "required": ["schedules"],
        "additionalProperties": False,
    }


# --- files -------------------------------------------------------------------------------------------------

def _key(model: str, prompt: str, system_prompt: str = SYSTEM_PROMPT) -> str:
    return hashlib.sha256(f"{CACHE_VERSION}\n{model}\n{system_prompt}\n{prompt}".encode()).hexdigest()


def _read_cache(cache_file: Path, kind: str = CHOOSE) -> dict | None:
    try:
        data = json.loads(cache_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("version") != CACHE_VERSION or not _fits(data.get("answer"), kind):
        return None
    return data


def _read_answer(answer_file: Path, kind: str = CHOOSE) -> dict | None:
    """The chat's answer, in the shape the API returns, or None when it cannot be used."""
    try:
        answer = json.loads(answer_file.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    return answer if _fits(answer, kind) else None


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


# --- the whole-job questions: request kinds "read_pass" and "write_system" (see whole_job.py) -------------

WRITE_SYSTEM = "write_system"
KINDS = KINDS + (WRITE_SYSTEM, READ_PASS)
_MAIN_LIST.update({WRITE_SYSTEM: "lines"})
QC_JOB = "qc_job"                  # the proposal QC pass (qc.py)
KINDS = KINDS + (QC_JOB,)
_MAIN_LIST[QC_JOB] = "findings"
WHOLE_JOB_MAX_TOKENS = 64000       # a reading pass or a system's scope, plus the thinking; streamed
WHOLE_JOB_TIMEOUT_SECONDS = 600.0


def _read_response(response, kind: str, model: str) -> tuple[dict, str]:
    """The JSON answer in a reply, as `Judge._ask` reads it; `_Unusable` when it cannot be used."""
    stop = getattr(response, "stop_reason", None)
    if stop == "max_tokens":
        raise _Unusable("the AI answer was cut off before it finished")
    if stop == "refusal":
        raise _Unusable("the AI declined to answer for this system")
    text = "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
    try:
        answer = json.loads(text)
    except ValueError:
        raise _Unusable("the AI answer could not be read") from None
    if not _fits(answer, kind):
        raise _Unusable("the AI answer could not be read")
    return answer, getattr(response, "model", None) or model
