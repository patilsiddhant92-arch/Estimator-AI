"""Scan the work tree and this branch's commit messages for denylist tokens.

    python tools/nda_scan.py --denylist FILE [--self-check]

FILE is one sensitive token per line. Keep it outside git. A hit prints
``path:line: TOKEN`` or ``commit:<hash>:line: TOKEN`` and never the line
itself. Exit 1 when any token matches, 0 when none. Exit 2 when a file could
not be read (the names are listed on stderr), or when ``--self-check`` finds
FILE inside the work tree and not ignored. Hits are still printed when a file
could not be read.

Text is read as UTF-16 when a byte-order mark is present, otherwise as UTF-8
(a UTF-8 mark is accepted). A docx, xlsx, or pptx file is read from the XML
parts inside the zip.

This file contains no job data.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import zipfile
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


_OFFICE = {".docx", ".xlsx", ".pptx"}


def _decode(raw: bytes) -> str | None:
    """UTF-16 when the bytes start with a byte-order mark, otherwise strict UTF-8. None when neither fits."""
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return raw.decode("utf-16")
        except UnicodeError:
            return None
    try:
        return raw.decode("utf-8-sig")
    except UnicodeError:
        return None


def _office_xml(path: Path) -> list[str] | None:
    """Text of each XML part in a docx, xlsx, or pptx. None when the zip cannot be read or a part is not text."""
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile):
        return None
    parts: list[str] = []
    with archive:
        for info in archive.infolist():
            if info.is_dir() or not info.filename.lower().endswith(".xml"):
                continue
            try:
                raw = archive.read(info)
            except OSError:
                return None
            text = _decode(raw)
            if text is None:
                return None
            parts.append(text)
    return parts


def _file_hits(root: Path, tokens: list[tuple[str, re.Pattern[str]]]) -> tuple[list[str], list[str]]:
    found: list[str] = []
    unread: list[str] = []
    for name in _files(root):
        path = root / name
        label = Path(name).as_posix()
        if not path.is_file():
            continue
        try:
            raw = path.read_bytes()
        except OSError:
            unread.append(label)
            continue
        text = _decode(raw)
        if text is None and path.suffix.lower() in _OFFICE:
            parts = _office_xml(path)
            if parts is None:
                unread.append(label)
                continue
            for part in parts:
                found.extend(_hits(label, part, tokens))
            continue
        if text is None:
            unread.append(label)
            continue
        found.extend(_hits(label, text, tokens))
    return found, unread


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
    file_hits, unread = _file_hits(root, tokens)
    hits = file_hits + _commit_hits(root, tokens)
    for line in hits:
        print(line)
    for name in unread:
        print(f"nda_scan.py: could not read {name}", file=sys.stderr)
    if unread:
        return 2
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
