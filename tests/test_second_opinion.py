"""A timeout from the reviewer is a plain message, not a traceback."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import second_opinion  # noqa: E402


def test_a_timeout_is_a_plain_message(monkeypatch, tmp_path, capsys):
    grok = tmp_path / "grok"
    grok.write_text("", encoding="utf-8")
    monkeypatch.setattr(second_opinion, "GROK", grok)
    monkeypatch.setattr(second_opinion, "diff_of", lambda branch, base: "invented diff\n")

    def run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 1))

    monkeypatch.setattr(second_opinion.subprocess, "run", run)
    assert second_opinion.main(["grok/invented"]) == 2
    assert "did not finish" in capsys.readouterr().err
