"""Command line of the rebuilt app.

    python -m bms estimate JOB_FOLDER --out FOLDER [--cache FOLDER] [--mode chat|api]
    python -m bms playbook-lint [PLAYBOOK_ROOT]
    python -m bms doctor [--cache FOLDER] [--playbook FOLDER] [--config FILE]
    python -m bms status OUT [--cache FOLDER]

chat (the default): every AI question is written to CACHE/judge-chat/requests for the chat to answer (the
/run-job skill and tools/run_job.py drive it); api: Claude through the Anthropic API (ANTHROPIC_API_KEY).

playbook-lint: checks playbook/rules.md, shapes.json and wording.json (default: the repo's playbook/, wherever it is
run from); prints each problem in plain words and exits 1, or says it is clean and exits 0.

doctor: checks Python environment, dependencies, configured models, Playbook, and cache folder writability; prints
diagnostic messages in plain words and exits 0 if all checks pass or 1 on error.

status: says, in plain words, how far the run in OUT got, from the files it already wrote; it never calls the AI and
writes nothing. Exits as estimate does: 0 done, 2 waiting for answers, 1 stopped, not finished, no folder or no run.
It may be run while an estimate is running: what it shows may then be a moment old.

Each subcommand is one entry in COMMANDS (name -> function of the parsed arguments, returning the exit code). The
heavy imports are inside each entry, so status (and playbook-lint) work even when the estimate stack cannot import.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable

from bms.playbook import DEFAULT_ROOT
from bms.playbook_lint import lint_playbook, referenced_rule_names

MODES = ("chat", "api")             # bms.run.MODES, kept here so the parser does not import the estimate stack


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bms", description="The rebuilt estimating app.")
    commands = p.add_subparsers(dest="command", required=True)
    e = commands.add_parser("estimate", help="write the proposal, price sheet, Evidence Package and review page "
                                             "from a job folder")
    e.add_argument("job", type=Path, help="the job folder")
    e.add_argument("--out", type=Path, required=True, help="where the outputs go (under out/, never the repo)")
    e.add_argument("--cache", type=Path, help="where reading is kept and chat requests go (default: OUT/.cache)")
    e.add_argument("--mode", choices=MODES, default="chat", help="who answers the AI questions (default: chat)")
    lint = commands.add_parser("playbook-lint", help="check playbook/rules.md, shapes.json and wording.json")
    lint.add_argument("root", nargs="?", type=Path, default=DEFAULT_ROOT,
                      help="the Playbook folder (default: the repo's playbook/)")
    d = commands.add_parser("doctor", help="check Python, dependencies, models, Playbook, and cache")
    d.add_argument("--cache", type=Path, default=None, help="cache directory to check (default: system temp / bms_cache)")
    d.add_argument("--playbook", type=Path, default=None, help="playbook directory to check (default: repo playbook/)")
    d.add_argument("--config", type=Path, default=None, help="configuration file to check (default: repo .claude/run-job.json)")
    s = commands.add_parser(
        "status", help="say, in plain words, how far a run got, from the files it already wrote",
        description="Say, in plain words, how far the run in OUT got, from the files it already wrote. It never "
                    "calls the AI and writes nothing. Exits 0 when done, 2 when requests wait for answers, and 1 "
                    "when the run stopped or has not finished, or there is no folder or no run. It may be run "
                    "while an estimate is running; what it shows may then be a moment old.")
    s.add_argument("out", type=Path, help="the output folder")
    s.add_argument("--cache", type=Path, help="where reading and chat requests are (default: OUT/.cache)")
    return p


def _cache(args: argparse.Namespace) -> Path:
    return args.cache or args.out / ".cache"


def _estimate(args: argparse.Namespace) -> int:
    from bms.run import estimate
    try:
        result = estimate(args.job, args.out, _cache(args), args.mode)
    except (PermissionError, FileNotFoundError, ValueError) as error:
        stopped = getattr(error, "run_result", None)     # the run ended as stopped, at its step (bms.run.estimate)
        if stopped is not None:
            for line in stopped.messages:
                print(line)
            print(f"Stopped at the {stopped.stage} step.")
            return 1
        if isinstance(error, ValueError) and str(error).startswith("Stopped:"):
            print(error)                                 # refused before the run began (a folder inside the repo)
            return 1
        raise
    for line in result.messages:
        print(line)
    if result.status == "waiting":
        if result.waiting:
            print(f"Waiting: {result.waiting} request(s) at the {result.stage} step.")
            return 2
        print(f"Stopped at the {result.stage} step.")
        return 1
    return 0


def _playbook_lint(args: argparse.Namespace) -> int:
    problems = lint_playbook(args.root, known_rule_names=referenced_rule_names())
    for problem in problems:
        print(problem)
    if problems:
        print(f"{len(problems)} problem(s) in the Playbook at {args.root}.")
        return 1
    print(f"The Playbook at {args.root} is clean.")
    return 0


def _doctor(args: argparse.Namespace) -> int:
    from bms.doctor import run_doctor
    ok, messages = run_doctor(cache_dir=args.cache, playbook_dir=args.playbook, config_path=args.config)
    for line in messages:
        print(line)
    return 0 if ok else 1


def _status(args: argparse.Namespace) -> int:
    from bms.status import check
    found = check(args.out, _cache(args))
    for line in found.lines:
        print(line)
    return found.code


COMMANDS: dict[str, Callable[[argparse.Namespace], int]] = {
    "estimate": _estimate,
    "playbook-lint": _playbook_lint,
    "doctor": _doctor,
    "status": _status,
}


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parser().parse_args(argv)
    return COMMANDS[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
