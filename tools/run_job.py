"""Helper for the /run-job skill. No AI, no subagents.

    python tools/run_job.py status JOB --out OUT [--cache CACHE] [--app bms|estimator]
    python tools/run_job.py check ANSWER_FILE REQUEST_FILE

`status` runs the estimate in chat mode: the rebuilt app by default (`python -m bms estimate --mode chat`; exit 2
while requests wait, 0 when done), or with `--app estimator` the old app (`python -m estimator estimate --ai chat`).
It prints the tool's summary, then one JSON block listing the requests still waiting for an answer (kinds
`read_pass`, `count_tags`, `write_system`, `qc_job`) and the proposal path once it is written. A request still present although its answer file
exists was rejected by the estimator: it is listed with `"rejected": true` and the estimator's reason, its answer
file is deleted and an attempt is counted. A rebuilt app's request also lists its `step` (write, revise, qc) and,
when an earlier answer was refused, the `problem` the next answer must fix.
The waiting block also gives `exit` (the estimate's exit code) and `stage` (the rebuilt app's step it waits at).
`check` only reads JSON (no estimator import); a rebuilt app's request (one with a `step`) is held to its whole
schema with `bms.model.schema_errors`.
Failed checks and rejected answers are counted per request key in OUT/.run-job-attempts.json.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ATTEMPTS = ".run-job-attempts.json"
MAIN_LIST = {"read_pass": "facts", "write_system": "lines", "qc_job": "findings"}   # the answer's main list, by kind
OUT_MARKER = ".run-job-out"          # beside the requests: which out folder the last status run used


BMS_STEPS = ("count", "write", "revise", "qc")   # the rebuilt app's request steps (bms.ai, bms.counts)
APPS = ("estimator", "bms")


def _load(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _schema_errors(answer, schema: dict) -> list | None:
    """Every way the answer breaks the schema (bms.model.schema_errors), or None when bms cannot be imported."""
    try:
        if str(ROOT / "src") not in sys.path:
            sys.path.append(str(ROOT / "src"))
        from bms.model import schema_errors
    except ImportError:
        return None
    return schema_errors(answer, schema)


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
            return None
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


def waiting_requests(requests: Path, job: str, attempts: dict, text: str = "") -> list:
    """Every request file of this job (by `job`) still present after the run. The estimator deletes a request
    once it uses the answer, so one whose answer file exists was rejected: it is listed with `rejected` and the
    reason the run printed (`text`), its answer file is deleted and an attempt counted in `attempts`."""
    waiting = []
    for path in sorted(requests.glob("*.json")):
        try:
            request = _load(path)
        except ValueError:
            continue
        if not isinstance(request, dict) or request.get("job") != job:
            continue
        answer = request.get("answer_file", "")
        answer_path = Path(answer) if Path(answer).is_absolute() else ROOT / answer
        entry = {"file": str(path), "kind": request.get("kind"), "system": request.get("system"), "answer_file": answer}
        if request.get("step"):
            entry["step"] = request["step"]
        if request.get("previous_problem"):
            entry["problem"] = request["previous_problem"]
        if answer and answer_path.exists():
            key = request.get("key")
            try:
                answer_path.unlink()
            except OSError:
                pass
            if key:
                attempts[key] = attempts.get(key, 0) + 1
            entry |= {"rejected": True, "reason": _reason(text, request.get("system"))}
        waiting.append(entry | {"attempts": attempts.get(request.get("key"), 0)})
    return waiting


def estimate_command(job: Path, out: Path, cache: Path, app: str = "bms") -> list[str]:
    """The chat-mode estimate command of the rebuilt app (`bms`, the default) or the old one (`estimator`)."""
    if app == "bms":
        return [sys.executable, "-m", "bms", "estimate", str(job), "--out", str(out), "--cache", str(cache),
                "--mode", "chat"]
    return [sys.executable, "-m", "estimator", "estimate", str(job), "--out", str(out), "--cache", str(cache),
            "--ai", "chat"]


def cmd_status(args) -> int:
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    cache = args.cache or out / ".cache"
    cmd = estimate_command(args.job, out, cache, getattr(args, "app", "bms") or "bms")
    run = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    text = (run.stdout or "") + (run.stderr or "")
    print(text.rstrip())
    requests = Path(cache) / "judge-chat" / "requests"
    attempts = _read_attempts(out)
    waiting = []
    if requests.is_dir():
        (requests / OUT_MARKER).write_text(str(out.resolve()), encoding="utf-8")
        waiting = waiting_requests(requests, job_name(args.job), attempts, text)
        if any(w.get("rejected") for w in waiting):
            (out / ATTEMPTS).write_text(json.dumps(attempts, indent=1), encoding="utf-8")
    proposal = None
    if not waiting:
        for line in text.splitlines():
            m = re.match(r"Wrote (.+\.docx)\s*$", line.strip())
            if m:
                proposal = m.group(1)
    stage = next((m.group(1) for m in re.finditer(r"request\(s\) at the (\w+) step", text)), None)
    print(json.dumps({"waiting": waiting, "proposal": proposal, "exit": run.returncode, "stage": stage}, indent=1))
    return run.returncode


def main(argv=None) -> int:
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
    args = parser.parse_args(argv)
    return cmd_status(args) if args.command == "status" else cmd_check(args)


if __name__ == "__main__":
    sys.exit(main())
