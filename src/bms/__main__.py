"""Command line of the rebuilt app.

    python -m bms estimate JOB_FOLDER --out FOLDER [--cache FOLDER] [--mode chat|api]
    python -m bms playbook-lint [PLAYBOOK_ROOT]

chat (the default): every AI question is written to CACHE/judge-chat/requests for the chat to answer (the
/run-job skill and tools/run_job.py drive it); api: Claude through the Anthropic API (ANTHROPIC_API_KEY).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from bms.run import MODES, estimate
from bms.playbook_lint import lint_playbook, VALIDATOR_RULE_NAMES


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bms", description="The rebuilt estimating app.")
    commands = p.add_subparsers(dest="command", required=True)
    e = commands.add_parser("estimate", help="write the proposal, price sheet, Evidence Package and review page "
                                             "from a job folder")
    e.add_argument("job", type=Path, help="the job folder")
    e.add_argument("--out", type=Path, required=True, help="where the outputs go (under out/, never the repo)")
    e.add_argument("--cache", type=Path, help="where reading is kept and chat requests go (default: OUT/.cache)")
    e.add_argument("--mode", choices=MODES, default="chat", help="who answers the AI questions (default: chat)")
    l = commands.add_parser("playbook-lint", help="lint playbook/rules.md, shapes.json, wording.json for problems")
    l.add_argument("root", nargs="?", type=Path, default=Path("playbook"),
                   help="playbook root folder (default: playbook/)")
    return p


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parser().parse_args(argv)
    if args.command == "estimate":
        result = estimate(args.job, args.out, args.cache or args.out / ".cache", args.mode)
        for line in result.messages:
            print(line)
        if result.status == "waiting":
            if result.waiting:
                print(f"Waiting: {result.waiting} request(s) at the {result.stage} step.")
                return 2
            return 1
        return 0
    if args.command == "playbook-lint":
        problems = lint_playbook(args.root, known_rule_names=VALIDATOR_RULE_NAMES)
        for p in problems:
            print(p)
        return 1 if problems else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())