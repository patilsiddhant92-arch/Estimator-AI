"""Helper for the /run-job skill. No AI, no subagents.

    python tools/run_job.py status JOB --out OUT [--cache CACHE] [--app bms|estimator]
    python tools/run_job.py check [--no-count] ANSWER_FILE REQUEST_FILE

`status` runs the estimate in chat mode: the rebuilt app by default (`python -m bms estimate --mode chat`; exit 2
while requests wait, exit 1 when the run stops with nothing left to answer, 0 when done), or with `--app estimator`
the old app (`python -m estimator estimate --ai chat`).
The child runs with this checkout's `src` first on PYTHONPATH: the venv's editable install can name another
checkout, and a run from a worktree would load that checkout's code.
It prints the tool's summary, then one JSON block listing the requests still waiting for an answer (kinds
`read_pass`, `count_tags`, `write_system`, `qc_job`) and the proposal path once it is written. A request still present although its answer file
exists was rejected by the estimator: it is listed with `"rejected": true` and the estimator's reason, its answer
file is deleted and an attempt is counted. A rebuilt app's request also lists its `step` (write, revise, qc) and,
when an earlier answer was refused, the `problem` the next answer must fix.
The waiting block also gives `exit` (the estimate's exit code) and `stage` (the rebuilt app's step it waits at).
`check` only reads JSON (no estimator import); a rebuilt app's request (one with a `step`) is held to its whole
schema with `bms.model.schema_errors` (loaded from this checkout's `src`).
Failed checks and rejected answers are counted per request key in OUT/.run-job-attempts.json.
`check --no-count` counts nothing: a subagent checks its own answer with it, so only the lead's check counts.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ATTEMPTS = ".run-job-attempts.json"
MAIN_LIST = {"read_pass": "facts", "write_system": "lines", "qc_job": "findings"}   # the answer's main list, by kind
OUT_MARKER = ".run-job-out"          # beside the requests: which out folder the last status run used


BMS_STEPS = ("count", "write", "decide", "revise", "qc")   # the rebuilt app's request steps (bms.ai, bms.counts)


def stage_of(text: str) -> str | None:
    """The rebuilt app's stage from its console line. Stages include read, count, write, decisions, qc, revise."""
    return next((m.group(1) for m in re.finditer(r"(?:request\(s\) at|Stopped at) the (\w+) step", text or "")),
                None)
APPS = ("estimator", "bms")


def _load(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _schema_errors(answer, schema: dict) -> list | None:
    """Every way the answer breaks the schema (bms.model.schema_errors), or None when bms cannot be imported."""
    try:
        if str(ROOT / "src") not in sys.path:
            sys.path.insert(0, str(ROOT / "src"))     # first: the editable install's .pth can name another checkout
        from bms.model import schema_errors
    except ImportError:
        return None
    return schema_errors(answer, schema)


def _unexamined_tiles(answer: dict, request: dict) -> str | None:
    """For a count_tags answer: a message when a pattern's tiles_examined leaves out a tile the request sent (the
    estimator refuses such an answer too), else None."""
    if request.get("kind") != "count_tags":
        return None
    tiles = len(request.get("tiles") or request.get("images") or ())
    for entry in answer.get("patterns") or ():
        if not isinstance(entry, dict):
            continue
        seen = {n for n in entry.get("tiles_examined") or () if isinstance(n, int)}
        missing = [n for n in range(1, tiles + 1) if n not in seen]
        if missing:
            which = f"tile {missing[0]}" if len(missing) == 1 else "tiles " + ", ".join(map(str, missing))
            return (f"pattern {entry.get('pattern', '?')}: {which} not examined; every tile picture must be opened "
                    f"and listed in tiles_examined (1 to {tiles})")
    return None


def _read_attempts(out: Path) -> dict:
    try:
        data = _load(out / ATTEMPTS)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def check_answer(answer_file: Path, request_file: Path) -> str | None:
    """None when the answer is fine, else a plain message."""
    try:
        answer = _load(answer_file)
    except OSError:
        return "the answer file is missing or unreadable"
    except ValueError:
        return "the answer is not valid JSON"
    if not isinstance(answer, dict):
        return "the answer is not a JSON object"
    request = _load(request_file)
    schema = request.get("schema") or {}
    if request.get("step") in BMS_STEPS and schema:
        errors = _schema_errors(answer, schema)
        if errors is not None:
            if errors:
                more = f"; and {len(errors) - 5} more" if len(errors) > 5 else ""
                return "the answer breaks its schema: " + "; ".join(errors[:5]) + more
            return _unexamined_tiles(answer, request)
    if request.get("kind") == "count_tags" and (problem := _unexamined_tiles(answer, request)):
        return problem
    missing = [k for k in schema.get("required", []) if k not in answer]
    if missing:
        return "the answer is missing: " + ", ".join(missing)
    main = MAIN_LIST.get(_load(request_file).get("kind"))
    props = schema.get("properties") or {}
    # a schema that names its properties but not the kind's old main list is the rebuilt app's (bms): its
    # write_system answers a System, whose "devices" list the property check below covers
    if main and (main in props or not props) and not isinstance(answer.get(main), list):
        return f"'{main}' must be a list"
    for key, prop in (schema.get("properties") or {}).items():
        if isinstance(prop, dict) and prop.get("type") == "array" and key in answer and not isinstance(answer[key], list):
            return f"'{key}' must be a list"
    return None


def cmd_check(args) -> int:
    message = check_answer(args.answer, args.request)
    if message is None:
        print("ok")
        return 0
    print(message)
    if getattr(args, "no_count", False):
        return 1
    try:
        key = _load(args.request).get("key")
        marker = Path(args.request).resolve().parent / OUT_MARKER
        out = Path(marker.read_text(encoding="utf-8").strip()) if marker.exists() else None
        if out is not None and key:
            attempts = _read_attempts(out)
            attempts[key] = attempts.get(key, 0) + 1
            (out / ATTEMPTS).write_text(json.dumps(attempts, indent=1), encoding="utf-8")
    except (OSError, ValueError):
        pass
    return 1


def job_name(job: Path) -> str:
    """The name the estimator writes as a request's `job`: the job folder's name up to the first comma."""
    return Path(job).name.split(",")[0].strip()


def _reason(text: str, system) -> str:
    """The estimator's words about this request's answer in the run's output ("the answer for X could not be
    read"), or ""."""
    if not system:
        return ""
    for line in (text or "").splitlines():
        found = re.search(rf"the answer for {re.escape(str(system))}[^;\n]*", line)
        if found:
            return found.group(0).strip().rstrip(".")
    return ""


def _answer_not_newer(answer_path: Path, request_path: Path) -> bool:
    """True when the answer is not newer than its request. Mirrors the app's own rule in `_answer_is_fresh`
    (src/bms/ai.py: an answer counts only when its modified time is after the request's); copied here, not imported,
    because that function also needs the chat transport's record of the last refused answer."""
    try:
        return answer_path.stat().st_mtime_ns <= request_path.stat().st_mtime_ns
    except OSError:
        return False


def waiting_requests(requests: Path, job: str, attempts: dict, text: str = "") -> list:
    """Every request file of this job (by `job`) still present after the run. The estimator deletes a request
    once it uses the answer, so one whose answer file is not newer than the request was rejected: it is listed with
    `rejected` and the reason the run printed (`text`), its answer file is deleted and an attempt counted in
    `attempts`. An answer newer than its request was simply not read yet (the run stopped early), so it stays. When
    the run crashed (`text` holds a Traceback) nothing is judged: no answer is deleted and no attempt counted."""
    waiting = []
    crashed = "Traceback" in text
    present = set()                  # keys of every request file still there (any job)
    for path in sorted(requests.glob("*.json")):
        try:
            request = _load(path)
        except ValueError:
            continue
        if isinstance(request, dict) and request.get("key"):
            present.add(request["key"])
        if not isinstance(request, dict) or request.get("job") != job:
            continue
        answer = request.get("answer_file", "")
        answer_path = Path(answer) if Path(answer).is_absolute() else ROOT / answer
        entry = {"file": str(path), "kind": request.get("kind"), "system": request.get("system"), "answer_file": answer}
        if request.get("step"):
            entry["step"] = request["step"]
        if request.get("previous_problem"):
            entry["problem"] = request["previous_problem"]
        if not crashed and answer and answer_path.exists() and _answer_not_newer(answer_path, path):
            key = request.get("key")
            try:
                answer_path.unlink()
            except OSError:
                pass
            if key:
                attempts[key] = attempts.get(key, 0) + 1
            entry |= {"rejected": True, "reason": _reason(text, request.get("system"))}
        elif (not crashed and request.get("key") and not request.get("previous_problem")
              and not (answer and answer_path.exists())):
            attempts.pop(request["key"], None)      # a fresh question: an earlier run's count does not carry over
        waiting.append(entry | {"attempts": attempts.get(request.get("key"), 0)})
    if not crashed:
        for key in [k for k in attempts if k not in present]:
            del attempts[key]                       # its request was used: nothing left to count
    return waiting


def estimate_command(job: Path, out: Path, cache: Path, app: str = "bms") -> list[str]:
    """The chat-mode estimate command of the rebuilt app (`bms`, the default) or the old one (`estimator`)."""
    if app == "bms":
        return [sys.executable, "-m", "bms", "estimate", str(job), "--out", str(out), "--cache", str(cache),
                "--mode", "chat"]
    return [sys.executable, "-m", "estimator", "estimate", str(job), "--out", str(out), "--cache", str(cache),
            "--ai", "chat"]


def child_env() -> dict:
    """The environment of the estimate child: this checkout's `src` first on PYTHONPATH, before any PYTHONPATH the
    caller set. A venv's editable install can name another checkout (a .pth file); PYTHONPATH wins over it."""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(ROOT / "src"), env.get("PYTHONPATH")]))
    return env


def cmd_status(args) -> int:
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    cache = args.cache or out / ".cache"
    cmd = estimate_command(args.job, out, cache, getattr(args, "app", "bms") or "bms")
    run = subprocess.run(cmd, cwd=ROOT, env=child_env(), capture_output=True, text=True, encoding="utf-8",
                         errors="replace")
    text = (run.stdout or "") + (run.stderr or "")
    print(text.rstrip())
    requests = Path(cache) / "judge-chat" / "requests"
    attempts = _read_attempts(out)
    waiting = []
    if requests.is_dir():
        (requests / OUT_MARKER).write_text(str(out.resolve()), encoding="utf-8")
        before = dict(attempts)
        waiting = waiting_requests(requests, job_name(args.job), attempts, text)
        if attempts != before:
            (out / ATTEMPTS).write_text(json.dumps(attempts, indent=1), encoding="utf-8")
    proposal = None
    if not waiting:
        for line in text.splitlines():
            m = re.match(r"Wrote (.+\.docx)\s*$", line.strip())
            if m:
                proposal = m.group(1)
    stage = stage_of(text)
    print(json.dumps({"waiting": waiting, "proposal": proposal, "exit": run.returncode, "stage": stage}, indent=1))
    return run.returncode


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")     # a piped Windows console is cp1252
    parser = argparse.ArgumentParser(prog="run_job")
    sub = parser.add_subparsers(dest="command", required=True)
    st = sub.add_parser("status")
    st.add_argument("job", type=Path)
    st.add_argument("--out", type=Path, required=True)
    st.add_argument("--cache", type=Path)
    st.add_argument("--app", choices=APPS, default="bms",
                    help="which app runs the estimate (default: bms, the rebuilt app; estimator: the old app)")
    ck = sub.add_parser("check")
    ck.add_argument("answer", type=Path)
    ck.add_argument("request", type=Path)
    ck.add_argument("--no-count", action="store_true",
                    help="a failed check adds no attempt (a subagent's check of its own answer)")
    args = parser.parse_args(argv)
    return cmd_status(args) if args.command == "status" else cmd_check(args)


if __name__ == "__main__":
    sys.exit(main())
