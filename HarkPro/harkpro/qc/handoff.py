"""Request / answer files, the app's chat hand-off form (`src/bms/ai.py` ChatTransport, `tools/run_job.py`).

A request is `<out>/requests/<key>.json` = {"key", "kind", "system", "job", "step", "system_prompt", "prompt",
"schema", "answer_file"} (+ "previous_problem" when an earlier answer was refused). The AI writes its JSON answer to
`answer_file`. A used answer stays in `answers/` (it is the cache: a re-run replays it) and its request is deleted.
A refused answer is moved to `answers/rejected/` and the request is written again with the reason; after
`max_attempts` refusals the run stops with a plain message.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .schemas import schema_errors

MAX_ATTEMPTS = 3


class Waiting(Exception):
    """The answer is not there yet: the request file is written."""

    def __init__(self, request: Path, problem: str | None = None):
        super().__init__(str(request))
        self.request = request
        self.problem = problem


class Stopped(Exception):
    """An answer was refused `MAX_ATTEMPTS` times."""


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


class Handoff:
    def __init__(self, folder: str | Path, job: str = "", max_attempts: int = MAX_ATTEMPTS):
        self.folder = Path(folder)
        self.job = job
        self.max_attempts = max_attempts
        self.requests_dir = self.folder / "requests"
        self.answers_dir = self.folder / "answers"
        self.attempts_file = self.folder / "attempts.json"

    @staticmethod
    def key(kind: str, system_prompt: str, prompt: str) -> str:
        return hashlib.sha1(f"{kind}\n{system_prompt}\n{prompt}".encode("utf-8")).hexdigest()[:16]

    def _attempts(self) -> dict:
        try:
            return json.loads(self.attempts_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def ask(self, kind: str, name: str, system_prompt: str, prompt_obj: dict, schema: dict, check=None):
        """The answer (a dict), or raise Waiting / Stopped. `check(answer)` gives a list of problems."""
        prompt = json.dumps(prompt_obj, ensure_ascii=False, indent=1)
        key = self.key(kind, system_prompt, prompt)
        request = self.requests_dir / f"{key}.json"
        answer_file = self.answers_dir / f"{key}.json"
        attempts = self._attempts()
        problem = (attempts.get(key) or {}).get("problem")
        if answer_file.is_file():
            try:
                answer = json.loads(answer_file.read_text(encoding="utf-8-sig"))
                errors = schema_errors(answer, schema)
                if not errors and check is not None:
                    errors = list(check(answer) or [])
            except ValueError as e:
                answer, errors = None, [f"not JSON: {e}"]
            if not errors:
                request.unlink(missing_ok=True)
                return answer
            problem = "; ".join(errors[:12]) + (f" (+{len(errors) - 12} more)" if len(errors) > 12 else "")
            entry = attempts.setdefault(key, {"count": 0})
            entry["count"] += 1
            entry["problem"] = problem
            _write(self.attempts_file, attempts)
            rejected = self.answers_dir / "rejected" / f"{key}.{entry['count']}.json"
            rejected.parent.mkdir(parents=True, exist_ok=True)
            answer_file.replace(rejected)
            if entry["count"] >= self.max_attempts:
                raise Stopped(f"{name}: answer refused {entry['count']} times: {problem}")
        data = {"key": key, "kind": kind, "system": name, **({"job": self.job} if self.job else {}),
                "step": kind, "system_prompt": system_prompt, "prompt": prompt, "schema": schema,
                "answer_file": str(answer_file)}
        if problem:
            data["previous_problem"] = problem
        _write(request, data)
        self.answers_dir.mkdir(parents=True, exist_ok=True)      # so the answerer can write straight into it
        raise Waiting(request, problem)


def check_file(answer_file: str | Path, request_file: str | Path) -> list[str]:
    """Schema problems of an answer against its request (the semantic checks run in the loop)."""
    request = json.loads(Path(request_file).read_text(encoding="utf-8"))
    try:
        answer = json.loads(Path(answer_file).read_text(encoding="utf-8-sig"))
    except ValueError as e:
        return [f"not JSON: {e}"]
    return schema_errors(answer, request.get("schema") or {})
