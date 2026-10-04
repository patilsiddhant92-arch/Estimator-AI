"""tools/chat_guard.py keeps the team chat from losing history (invented messages only)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("chat_guard", Path(__file__).resolve().parents[1] / "tools" / "chat_guard.py")
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)

A = "[2026-01-01 10:00] ALPHA -> BETA\nhello\n"
B = "[2026-01-01 10:05] BETA -> ALPHA\nhi back\n"
C = "[2026-01-01 10:10] ALPHA -> BETA\nnext task\n"


def test_a_normal_append_is_not_an_alert(tmp_path):
    chat, archive = tmp_path / "chat.txt", tmp_path / "archive"
    chat.write_text("preamble\n\n" + A, encoding="utf-8")
    assert guard.run(chat, archive) == 0
    chat.write_text(chat.read_text(encoding="utf-8") + "\n" + B, encoding="utf-8")
    assert guard.run(chat, archive) == 0
    assert (archive / "chat.history.txt").read_text(encoding="utf-8") == chat.read_text(encoding="utf-8")


def test_an_overwritten_chat_is_restored_with_the_new_message_kept(tmp_path):
    chat, archive = tmp_path / "chat.txt", tmp_path / "archive"
    chat.write_text("preamble\n\n" + A + "\n" + B, encoding="utf-8")
    assert guard.run(chat, archive) == 0
    chat.write_text("preamble\n\n" + A + "\n" + C, encoding="utf-8")        # a tool wrote back a stale copy + its own post
    assert guard.run(chat, archive) == 3
    restored = chat.read_text(encoding="utf-8")
    assert "hi back" in restored and "next task" in restored and "hello" in restored
    assert restored.count("hello") == 1                                       # no duplicates


def test_check_mode_reports_but_does_not_write(tmp_path):
    chat, archive = tmp_path / "chat.txt", tmp_path / "archive"
    chat.write_text(A + "\n" + B, encoding="utf-8")
    guard.run(chat, archive)
    chat.write_text(C, encoding="utf-8")
    assert guard.run(chat, archive, check_only=True) == 3
    assert chat.read_text(encoding="utf-8") == C


def test_blocks_split_on_message_headers():
    blocks = guard.split_blocks("intro\n\n" + A + "\n" + B)
    assert len(blocks) == 3 and blocks[0].startswith("intro") and blocks[2].startswith("[2026-01-01 10:05]")
