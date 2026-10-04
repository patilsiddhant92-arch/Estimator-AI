"""The AI steps (workstream 5, design §4.5): write, QC and revise, each one prompt plus a JSON Schema; the answer is
checked against the schema (`bms.model.schema_errors`) before `from_dict`.

Two transports share the same steps:
- `ChatTransport` — the old app's chat hand-off, same folder layout and request fields as
  `estimator.writing.judge.Judge` in chat mode, so `tools/run_job.py` and the `/run-job` skill drive it:
  request `<handoff_dir>/requests/<key>.json` = {"key", "kind", "system", "job", "system_prompt", "prompt", **extra,
  "schema", "answer_file"}; answer `<handoff_dir>/answers/<key>.json`; `handoff_dir` defaults to
  `<cache>/judge-chat` (the same folder the old Judge uses for the reading passes of the same run); answers kept
  in `<cache>/judge/<key>.json` as {"version": 1, "kind", "model": "claude (chat)", "answer"}; `key` is
  `estimator.writing.judge._key(model, prompt, system_prompt)` with model "claude (chat)"; `job` is the dossier's
  `job_name` (the job folder name up to its first comma, as `tools/run_job.job_name`). On reading an answer the
  request file is deleted (that is how run_job.py tells a used answer from a rejected one). Do not reuse
  `judge._read_cache` / `judge._fits`: they check the old answer shapes.
- `ApiTransport` — the Anthropic SDK (anthropic 1.8.0), streamed, structured output
  (`output_config={"format": {"type": "json_schema", "schema": schema}}`), no temperature, the Playbook rules as
  the first system block with `cache_control: {"type": "ephemeral"}` (prompt caching), the step's own instructions
  as the second; same cache folder and file form under the API model's name; the key from the environment only.

Request kinds (what `/run-job` dispatches on): `write_system` for both writing and revising a system (extra
`"step": "write" | "revise"`, `"plan_key": system.key`), `qc_job` for the QC pass. In chat mode the request's
`system_prompt` is the Playbook rules text, a blank line, then the step's instructions.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol, runtime_checkable

from estimator.writing.dossier import Dossier

from bms.model import Finding, Job, System
from bms.playbook import Playbook

WRITE_SYSTEM = "write_system"       # kind of both the write and the revise request
QC_JOB = "qc_job"
STEPS = ("write", "revise")
CHAT_MODEL = "claude (chat)"


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


class ChatTransport:
    """Questions as request files for the chat; answers read back on the next run (see the module doc)."""

    def __init__(self, cache_dir: Path, job: str, handoff_dir: Path | None = None) -> None:
        """`cache_dir` is the run's cache (answers kept in `cache_dir/judge`); `handoff_dir` defaults to
        `cache_dir/judge-chat`; `job` is `dossier.job_name`."""
        raise NotImplementedError("workstream 5: the chat transport")

    waiting: int
    last_error: str | None

    def ask(self, kind: str, name: str, instructions: str, system_prompt: str, prompt: str, schema: dict,
            extra: dict | None = None, images: Sequence[Path] = ()) -> dict:
        raise NotImplementedError("workstream 5: the chat transport")


class ApiTransport:
    """Questions through the Anthropic API, with the Playbook cached (see the module doc)."""

    def __init__(self, cache_dir: Path, model: str | None = None, client=None) -> None:
        """`model` defaults to $ESTIMATOR_MODEL, else `estimator.writing.judge.DEFAULT_MODEL`; `client` is an
        `anthropic.Anthropic` (made from the environment when None; tests pass a fake)."""
        raise NotImplementedError("workstream 5: the API transport")

    waiting: int
    last_error: str | None

    def ask(self, kind: str, name: str, instructions: str, system_prompt: str, prompt: str, schema: dict,
            extra: dict | None = None, images: Sequence[Path] = ()) -> dict:
        raise NotImplementedError("workstream 5: the API transport")


def evidence_for(system: System, dossier: Dossier) -> str:
    """The evidence one system is written from: the dossier lines its refs, family tags and sequence refs point to,
    each kept with its "[S41]" source id and place, so the AI cites them by id. Only this job's text; no example
    from another job. Deterministic."""
    raise NotImplementedError("workstream 5: the evidence")


def evidence_index(dossier: Dossier) -> dict[str, str]:
    """Every source id of the dossier ("S41", "I2", "Q7") -> its text (a picture: its description), for the QC
    pass to check that each Ref's quote is in its source."""
    raise NotImplementedError("workstream 5: the evidence index")


def write_system(system: System, evidence: str, playbook: Playbook, transport: Transport) -> System:
    """The system with `devices`, `clarifications` and `tech_hours` filled from `evidence`.

    Contract: one WRITE_SYSTEM request (extra step "write", plan_key system.key) whose schema is
    `json_schema(System)`; the answer is checked with `schema_errors`, built with `System.from_dict`, and must keep
    the skeleton's `key`, `name`, `shape`, `control`, `families`, `sequence_refs` and `alternate` (the skeleton's
    values win). Every device has at least one Ref whose source_id is in the evidence. Raises NoAnswer when there
    is no answer yet (chat) or the answer cannot be used after the schema check."""
    raise NotImplementedError("workstream 5: write_system")


def qc_job(job: Job, evidence_index: Mapping[str, str], playbook: Playbook, transport: Transport) -> list[Finding]:
    """An independent reviewer's findings on the whole written job (one QC_JOB request, or one per part when the job
    is too long; schema {"findings": [Finding]}). Each Finding's `rule` is a Playbook rule name; `system_key` and
    `device_id` name what it is about. Raises NoAnswer as `write_system`."""
    raise NotImplementedError("workstream 5: qc_job")


def revise_system(system: System, findings: Sequence[Finding], evidence: str, playbook: Playbook,
                  transport: Transport) -> System:
    """The system revised for its `must_fix` findings only (the others are ignored), one round: one WRITE_SYSTEM
    request with extra step "revise"; same schema, checks and kept skeleton fields as `write_system`. With no
    must_fix finding for this system it returns `system` unchanged without asking. Raises NoAnswer."""
    raise NotImplementedError("workstream 5: revise_system")
