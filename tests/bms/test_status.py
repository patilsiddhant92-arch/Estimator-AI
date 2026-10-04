"""python -m bms status, on an invented run folder. No job text."""
from __future__ import annotations

import json
from pathlib import Path

from bms.__main__ import main
from bms.status import report


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_an_empty_folder_says_there_is_no_run(tmp_path, capsys):
    assert main(["status", str(tmp_path)]) == 0
    assert "no run" in capsys.readouterr().out


def test_a_waiting_write_names_the_systems_the_requests_and_the_findings(tmp_path):
    out, cache = tmp_path / "out", tmp_path / "cache"
    _write(out / "00-0000 Ledger.json", {"complete": True, "stopped_at": ""})
    _write(out / "00-0000 Job.json", {"name": "Invented", "systems": [
        {"key": "EF", "name": "Exhaust Fans"}, {"key": "RTU", "name": "Rooftop Units"}]})
    _write(cache / "judge-chat" / "requests" / "one.json",
           {"kind": "write_system", "step": "write", "system": "Exhaust Fans"})
    _write(cache / "judge-chat" / "requests" / "old" / "stale.json",
           {"kind": "write_system", "step": "write"})
    _write(cache / "attempts" / "abc.json", {"attempts": 2})
    _write(cache / "intake.json", [{"system": "Exhaust Fans", "change": "took a label off"}])
    (out / "Review.html").write_text(
        '<span class="rule">Rule: Name the verb</span>'
        '<span class="rule">Rule: Name the verb</span>'
        '<span class="rule">Rule: A point needs a source</span>', encoding="utf-8")
    text = "\n".join(report(out, cache))
    assert "Stage: write" in text
    assert "Exhaust Fans, Rooftop Units" in text
    assert "1 write_system request(s): one.json" in text
    assert "stale.json" not in text
    assert "1 question(s), 2 attempt(s): abc.json (2)" in text
    assert "Exhaust Fans: took a label off" in text
    assert "2 for Name the verb" in text and "1 for A point needs a source" in text


def test_reading_that_stopped_names_the_pass(tmp_path):
    out = tmp_path / "out"
    _write(out / "00-0000 Ledger.json", {"complete": False, "stopped_at": "scope"})
    text = "\n".join(report(out, tmp_path / "cache"))
    assert "Stage: read" in text and "scope" in text
    assert "none yet" in text
