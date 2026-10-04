"""tools/chat_post.py appends a message and never touches what is already in the chat (invented text only)."""
from __future__ import annotations

import datetime as dt
import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("chat_post", Path(__file__).resolve().parents[1] / "tools" / "chat_post.py")
poster = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(poster)

NOW = dt.datetime(2026, 1, 2, 3, 4)


def test_a_post_is_appended_with_a_real_header_and_old_text_is_untouched(tmp_path):
    chat = tmp_path / "chat.txt"
    chat.write_text("old one\nold two\n", encoding="utf-8")
    poster.post(chat, "ALPHA", "BETA, GAMMA", "hello there", now=NOW)
    text = chat.read_text(encoding="utf-8")
    assert text.startswith("old one\nold two\n")
    assert text.endswith("[2026-01-02 03:04] ALPHA -> BETA, GAMMA\nhello there\n")


def test_two_posts_keep_both_and_their_order(tmp_path):
    chat = tmp_path / "chat.txt"
    poster.post(chat, "A", "B", "first", now=NOW)
    poster.post(chat, "B", "A", "second", now=NOW)
    text = chat.read_text(encoding="utf-8")
    assert text.index("first") < text.index("second") and text.count("] ") == 2


def test_an_empty_message_is_refused(tmp_path, capsys):
    chat = tmp_path / "chat.txt"
    assert poster.main(["--from", "A", "--to", "B", "--text", "   ", "--chat", str(chat)]) == 2
    assert not chat.exists()
