"""Helper for the /run-job skill. No AI, no subagents.

    python tools/run_job.py status JOB --out OUT [--cache CACHE]
    python tools/run_job.py check ANSWER_FILE REQUEST_FILE

`status` runs `estimate --ai chat`, prints the tool's summary, then one JSON block listing the requests still
waiting for an answer and the proposal path once it is written. `check` only reads JSON (no estimator import).
Failed checks are counted per request key in OUT/.run-job-attempts.json.
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


def _load(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


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
    schema = _load(request_file).get("schema") or {}
    missing = [k for k in schema.get("required", []) if k not in answer]
    if missing:
        return "the answer is missing: " + ", ".join(missing)
    main = MAIN_LIST.get(_load(request_file).get("kind"))
    if main and not isinstance(answer.get(main), list):
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


def waiting_requests(requests: Path, job: str, attempts: dict) -> list:
    """This job's requests (by `job`) whose answer file does not exist yet."""
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
        if answer_path.exists():
            continue
        waiting.append({"file": str(path), "kind": request.get("kind"), "system": request.get("system"),
                        "answer_file": answer, "attempts": attempts.get(request.get("key"), 0)})
    return waiting


def cmd_status(args) -> int:
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    cache = args.cache or out / ".cache"
    cmd = [sys.executable, "-m", "estimator", "estimate", str(args.job), "--out", str(out), "--cache", str(cache),
           "--ai", "chat"]
    run = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    text = (run.stdout or "") + (run.stderr or "")
    print(text.rstrip())
    requests = Path(cache) / "judge-chat" / "requests"
    attempts = _read_attempts(out)
    waiting = []
    if requests.is_dir():
        (requests / OUT_MARKER).write_text(str(out.resolve()), encoding="utf-8")
        waiting = waiting_requests(requests, job_name(args.job), attempts)
    proposal = None
    if not waiting:
        for line in text.splitlines():
            m = re.match(r"Wrote (.+\.docx)\s*$", line.strip())
            if m:
                proposal = m.group(1)
    print(json.dumps({"waiting": waiting, "proposal": proposal}, indent=1))
    return run.returncode


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="run_job")
    sub = parser.add_subparsers(dest="command", required=True)
    st = sub.add_parser("status")
    st.add_argument("job", type=Path)
    st.add_argument("--out", type=Path, required=True)
    st.add_argument("--cache", type=Path)
    ck = sub.add_parser("check")
    ck.add_argument("answer", type=Path)
    ck.add_argument("request", type=Path)
    args = parser.parse_args(argv)
    return cmd_status(args) if args.command == "status" else cmd_check(args)


if __name__ == "__main__":
    sys.exit(main())
