"""Scan the work tree and this branch's commit messages for denylist tokens.

    python tools/nda_scan.py --denylist FILE [--self-check]

FILE is one sensitive token per line. Keep it outside git. A hit prints
``path:line: TOKEN`` or ``commit:<hash>:line: TOKEN`` and never the line
itself. Exit 1 when any token matches, 0 when none. Exit 2 when a file could
not be read (the names are listed on stderr), or when ``--self-check`` finds
FILE inside the work tree and not ignored. Hits are still printed when a file
could not be read.

Text is read as UTF-16 when a byte-order mark is present, otherwise as UTF-8
(a UTF-8 mark is accepted). UTF-8 that contains NUL bytes is tried again as
UTF-16 without a mark. A zip (a PK header, including docx, xlsx, and pptx)
is read from its XML and .rels parts, both raw and with the tags removed.
A file that is not valid UTF-8 is also scanned as Windows-1252 and is still
reported unread. A file or a zip part over the size cap is unread.

This file contains no job data.
"""
from __future__ import annotations

import argparse
import html
import re
import subprocess
import sys
import zipfile
import zlib
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


def _lines(text: str) -> list[str]:
    """Break on LF and CR only. A form feed stays inside its line."""
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def _hits(label: str, text: str, tokens: list[tuple[str, re.Pattern[str]]]) -> list[str]:
    found: list[str] = []
    for number, line in enumerate(_lines(text), start=1):
        for token, pattern in tokens:
            if pattern.search(line):
                found.append(f"{label}:{number}: {token}")
    return found


_OFFICE = {".docx", ".xlsx", ".pptx"}
_ZIP_MAGIC = b"PK\x03\x04"
# A test may set this lower. Files and zip parts above it are unread, not loaded.
_MAX_BYTES = 100 * 1024 * 1024
_READ_ERRORS = (OSError, zipfile.BadZipFile, zlib.error, RuntimeError, NotImplementedError, EOFError)


def _decode(raw: bytes) -> str | None:
    """UTF-16 when a mark is present, otherwise strict UTF-8. NUL bytes are tried as UTF-16 without a mark."""
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return raw.decode("utf-16")
        except UnicodeError:
            return None
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeError:
        return None
    if "\x00" not in text:
        return text
    for encoding in ("utf-16-le", "utf-16-be"):
        try:
            wide = raw.decode(encoding)
        except UnicodeError:
            continue
        if "\x00" not in wide:
            return wide
    return None


def _plain_xml(xml: str) -> str:
    """Join Word runs and turn XML entities into characters. Paragraph ends stay line breaks."""
    text = re.sub(r"</w:p\b[^>]*>", "\n", xml, flags=re.IGNORECASE)
    text = re.sub(r"</a:p\b[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</si\b[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<w:br\b[^>]*/>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<w:tab\b[^>]*/>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text)


def _scanned_part(name: str) -> bool:
    lower = name.lower()
    return lower.endswith(".xml") or lower.endswith(".rels")


def _office_xml(path: Path) -> list[str] | None:
    """Text of each XML or .rels part. None when the zip or a part cannot be read."""
    try:
        archive = zipfile.ZipFile(path)
    except _READ_ERRORS:
        return None
    parts: list[str] = []
    try:
        with archive:
            for info in archive.infolist():
                if info.is_dir() or not _scanned_part(info.filename):
                    continue
                if info.file_size > _MAX_BYTES:
                    return None
                try:
                    raw = archive.read(info)
                except _READ_ERRORS:
                    return None
                if len(raw) > _MAX_BYTES:
                    return None
                text = _decode(raw)
                if text is None:
                    return None
                parts.append(text)
    except _READ_ERRORS:
        return None
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
            size = path.stat().st_size
        except OSError:
            unread.append(label)
            continue
        if size > _MAX_BYTES:
            unread.append(label)
            continue
        try:
            raw = path.read_bytes()
        except OSError:
            unread.append(label)
            continue
        if raw.startswith(_ZIP_MAGIC) or (path.suffix.lower() in _OFFICE and _decode(raw) is None):
            parts = _office_xml(path)
            if parts is None:
                unread.append(label)
                continue
            for part in parts:
                found.extend(_hits(label, part, tokens))
                found.extend(_hits(label, _plain_xml(part), tokens))
            continue
        text = _decode(raw)
        if text is None:
            try:
                latin = raw.decode("cp1252")
            except UnicodeError:
                latin = ""
            if latin:
                found.extend(_hits(label, latin, tokens))
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
