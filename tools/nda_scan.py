"""Scan the work tree and this branch's commit messages for denylist tokens.

    python tools/nda_scan.py --denylist FILE [--self-check]

FILE is one sensitive token per line. Keep it outside git. A hit prints
``path:line: TOKEN`` or ``commit:<hash>:line: TOKEN`` and never the line
itself. Exit 1 when any token matches, 0 when none. ``--self-check`` exits 2
when FILE is inside the work tree and is not ignored.

This file contains no job data.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


def _git(args: list[str], cwd: Path, text: bool) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=text, encoding="utf-8" if text else None)


def _root() -> Path:
    found = _git(["rev-parse", "--show-toplevel"], Path.cwd(), text=True)
    if found.returncode != 0 or not found.stdout.strip():
        print("nda_scan.py: not a git work tree", file=sys.stderr)
        raise SystemExit(2)
    return Path(found.stdout.strip())


def _tokens(path: Path) -> list[tuple[str, re.Pattern[str]]]:
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except OSError as error:
        print(f"nda_scan.py: cannot read the denylist ({error})", file=sys.stderr)
        raise SystemExit(2) from None
    compiled: list[tuple[str, re.Pattern[str]]] = []
    seen: set[str] = set()
    for line in raw.splitlines():
        token = line.strip()
        key = token.casefold()
        if not token or key in seen:
            continue
        seen.add(key)
        compiled.append((token, re.compile(rf"(?<!\w){re.escape(token)}(?!\w)", re.IGNORECASE)))
    return compiled


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _ignored(path: Path, root: Path) -> bool:
    checked = _git(["check-ignore", "-q", "--", str(path)], root, text=True)
    return checked.returncode == 0


def _files(root: Path) -> list[str]:
    names: list[str] = []
    for args in (["ls-files", "-z"], ["ls-files", "-z", "--others", "--exclude-standard"]):
        listed = subprocess.run(["git", *args], cwd=root, capture_output=True)
        if listed.returncode != 0:
            print("nda_scan.py: git ls-files failed", file=sys.stderr)
            raise SystemExit(2)
        for raw in listed.stdout.split(b"\0"):
            if raw:
                names.append(raw.decode("utf-8", "surrogateescape"))
    return names


def _hits(label: str, text: str, tokens: list[tuple[str, re.Pattern[str]]]) -> list[str]:
    found: list[str] = []
    for number, line in enumerate(text.splitlines(), start=1):
        for token, pattern in tokens:
            if pattern.search(line):
                found.append(f"{label}:{number}: {token}")
    return found


def _file_hits(root: Path, tokens: list[tuple[str, re.Pattern[str]]]) -> list[str]:
    found: list[str] = []
    for name in _files(root):
        path = root / name
        if not path.is_file():
            continue
        text = path.read_bytes().decode("utf-8", "replace")
        found.extend(_hits(Path(name).as_posix(), text, tokens))
    return found


def _commit_hits(root: Path, tokens: list[tuple[str, re.Pattern[str]]]) -> list[str]:
    listed = _git(["log", "--format=%H"], root, text=True)
    if listed.returncode != 0:
        return []
    found: list[str] = []
    for digest in listed.stdout.split():
        message = _git(["log", "-1", "--format=%B", digest], root, text=True)
        if message.returncode != 0:
            continue
        found.extend(_hits(f"commit:{digest}", message.stdout, tokens))
    return found


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="nda_scan.py", description="Scan for denylist tokens. Prints file:line "
                                     "and the token, never the line.")
    parser.add_argument("--denylist", type=Path, required=True, help="one sensitive token per line, kept outside git")
    parser.add_argument("--self-check", action="store_true",
                        help="exit 2 if the denylist is inside the work tree and is not ignored")
    args = parser.parse_args(argv)
    root = _root()
    denylist = Path(args.denylist)
    if args.self_check and _inside(denylist, root) and not _ignored(denylist, root):
        print(f"nda_scan.py: denylist is inside the work tree and is not ignored: {denylist}", file=sys.stderr)
        return 2
    tokens = _tokens(denylist)
    hits = _file_hits(root, tokens) + _commit_hits(root, tokens)
    for line in hits:
        print(line)
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
