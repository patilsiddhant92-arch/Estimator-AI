"""Keep the team's chat file from losing history.

    .venv\\Scripts\\python.exe tools\\chat_guard.py            # reconcile, restore if the chat was overwritten
    .venv\\Scripts\\python.exe tools\\chat_guard.py --check    # report only, never write chat.txt

Colab\\chat.txt is append-only by agreement, but a tool that reads part of the file and writes it back whole can
wipe messages. This keeps a full history in Colab\\archive\\chat.history.txt. Each run: if chat.txt still starts with
the history, the history is just brought up to date; if not (it was truncated or rewritten), every message block
(a line starting "[YYYY-MM-DD HH:MM] ") that is missing from the history is appended to it and the merged text is
written back to chat.txt. Exit code 0 = nothing wrong, 3 = the chat had been overwritten (and was restored).
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEADER = re.compile(r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}\] ", re.M)


def split_blocks(text: str) -> list[str]:
    """The preamble (if any) and each message block, in order."""
    starts = [m.start() for m in HEADER.finditer(text)]
    if not starts:
        return [text] if text.strip() else []
    blocks = [text[:starts[0]]] if text[:starts[0]].strip() else []
    for a, b in zip(starts, starts[1:] + [len(text)]):
        blocks.append(text[a:b])
    return blocks


def reconcile(history: str, current: str) -> tuple[str, bool]:
    """(the text chat.txt should hold, whether the chat had been overwritten)."""
    if current.startswith(history):
        return current, False
    seen = {b.strip() for b in split_blocks(history)}
    extra = [b.strip("\n") for b in split_blocks(current) if b.strip() not in seen]
    if not extra:
        return history, True
    return history.rstrip("\n") + "\n\n" + "\n\n".join(extra) + "\n", True


def write_if_unchanged(chat: Path, text: str, expected: str) -> bool:
    """Replace chat.txt with `text` only while it still holds `expected`: the text goes to a temporary file beside it
    first (LF line ends, as chat_post writes), chat.txt is read again, and only then is the file swapped in whole.
    False (nothing replaced) when someone appended in the meantime."""
    tmp = chat.with_name(chat.name + ".tmp")
    try:
        tmp.write_text(text, encoding="utf-8", newline="\n")
        if chat.read_text(encoding="utf-8") != expected:
            return False
        os.replace(tmp, chat)
        return True
    finally:
        tmp.unlink(missing_ok=True)


def run(chat: Path, archive: Path, check_only: bool = False) -> int:
    archive.mkdir(parents=True, exist_ok=True)
    history_file = archive / "chat.history.txt"
    history = history_file.read_text(encoding="utf-8") if history_file.exists() else ""
    current = chat.read_text(encoding="utf-8") if chat.exists() else ""
    merged, overwritten = reconcile(history, current)
    if overwritten:
        print(f"ALERT: {chat} was overwritten or truncated ({len(current)} bytes now, history holds {len(history)}).")
        if check_only:
            return 3
        if not write_if_unchanged(chat, merged, current):         # someone appended while we worked: look again
            return run(chat, archive, check_only)
        print(f"Restored: {len(merged)} bytes written back.")
    history_file.write_text(merged, encoding="utf-8", newline="\n")
    return 3 if overwritten else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--chat", type=Path, default=ROOT / "Colab" / "chat.txt")
    parser.add_argument("--archive", type=Path, default=ROOT / "Colab" / "archive")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    return run(args.chat, args.archive, args.check)


if __name__ == "__main__":
    sys.exit(main())
