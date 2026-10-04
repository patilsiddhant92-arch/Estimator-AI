"""A second-model review of a branch, from the command line.

    .venv\\Scripts\\python.exe tools\\second_opinion.py <branch> [--base rebuild] [--turns 6]

Writes the branch's diff against its merge base with --base to Colab\\review-input\\<branch>.diff (git-ignored), then asks
the Grok CLI (headless, read-only, one bounded run, run from an empty temporary folder) to review ONLY that file and report
real defects with file:line. It prints the reviewer's answer. It changes nothing and never merges.

The answer is a second opinion, not a verdict: verify each finding against the code before acting on it.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_BIN = Path.home() / ".grok" / "bin"
GROK = next((p for p in (_BIN / "grok.exe", _BIN / "grok.cmd", _BIN / "grok") if p.exists()), _BIN / "grok")

PROMPT = (
    "You are a code reviewer. Read ONLY the unified diff file {diff} (a branch of an estimating app's Python code). "
    "Do not open any other folder, and never open a folder named out. Report REAL defects only: wrong behaviour, a bug, "
    "a crash path, a missing test that matters. For each: file:line from the diff, why it matters, a suggested fix. "
    "If you find none, list exactly what you checked. Maximum 14 lines."
)


def diff_of(branch: str, base: str) -> str:
    merge_base = subprocess.run(["git", "merge-base", base, branch], cwd=ROOT, capture_output=True, text=True,
                                encoding="utf-8", check=True).stdout.strip()
    return subprocess.run(["git", "diff", merge_base, branch], cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", check=True).stdout


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("branch")
    parser.add_argument("--base", default="rebuild")
    parser.add_argument("--turns", type=int, default=6)
    parser.add_argument("--timeout", type=int, default=420)
    args = parser.parse_args(argv)
    if not GROK.exists():
        print(f"The Grok CLI is not installed at {GROK}.", file=sys.stderr)
        return 2
    text = diff_of(args.branch, args.base)
    if not text.strip():
        print(f"No difference between {args.base} and {args.branch}.")
        return 0
    folder = ROOT / "Colab" / "review-input"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / (args.branch.replace("/", "-") + ".diff")
    target.write_text(text, encoding="utf-8")
    with tempfile.TemporaryDirectory() as empty:
        run = subprocess.run(
            [str(GROK), "-p", PROMPT.format(diff=target), "--max-turns", str(args.turns), "--sandbox", "read-only",
             "--output-format", "plain"],
            cwd=empty, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=args.timeout)
    print(run.stdout.strip() or run.stderr.strip())
    return run.returncode


if __name__ == "__main__":
    raise SystemExit(main())
