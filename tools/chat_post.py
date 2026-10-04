"""Post a message to the team chat safely: append only, real time, one write.

    .venv\\Scripts\\python.exe tools\\chat_post.py --from GROK --to "CLAUDE, LUNA" --text "TASK-018 STATUS: DONE ..."
    .venv\\Scripts\\python.exe tools\\chat_post.py --from GROK --to ALL --file my-message.txt
    (or pipe the text on standard input)

It opens Colab\\chat.txt in append mode and writes the header "[YYYY-MM-DD HH:MM] FROM -> TO" with the machine's real
clock, then the text. It never reads or rewrites the file, so it cannot erase anyone's messages. Use it instead of
editing chat.txt in an editor or with a tool that saves the whole file.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def post(chat: Path, sender: str, to: str, text: str, now: dt.datetime | None = None) -> str:
    """Append one message block to `chat`; returns the block written."""
    when = (now or dt.datetime.now()).strftime("%Y-%m-%d %H:%M")
    block = f"\n[{when}] {sender} -> {to}\n{text.strip()}\n"
    chat.parent.mkdir(parents=True, exist_ok=True)
    with chat.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(block)
    return block


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--from", dest="sender", required=True)
    parser.add_argument("--to", required=True)
    parser.add_argument("--text")
    parser.add_argument("--file", type=Path)
    parser.add_argument("--chat", type=Path, default=ROOT / "Colab" / "chat.txt")
    args = parser.parse_args(argv)
    if args.text is not None:
        text = args.text
    elif args.file is not None:
        text = args.file.read_text(encoding="utf-8")
    else:
        text = sys.stdin.read()
    if not text.strip():
        print("Nothing to post: the message is empty.", file=sys.stderr)
        return 2
    post(args.chat, args.sender, args.to, text)
    print(f"Posted to {args.chat}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
