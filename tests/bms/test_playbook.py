"""Tests for bms.playbook: loader, encoding checks, and per-file checks (TASK-023)."""
import shutil
from pathlib import Path

import pytest

from bms.playbook import (
    PlaybookError,
    check_file,
    load_playbook,
    load_rules,
    load_shapes,
    load_wording,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SAMPLE_PLAYBOOK = FIXTURES / "sample_playbook"


def test_load_playbook_raises_playbook_error_on_latin1_rules(tmp_path):
    """TASK-023: Latin-1 bytes in rules.md must raise PlaybookError, not raw UnicodeDecodeError."""
    folder = tmp_path / "pb"
    shutil.copytree(SAMPLE_PLAYBOOK, folder)
    # Write Latin-1 encoded byte 0xe9 (e-acute)
    (folder / "rules.md").write_bytes(b"# AME Playbook\n\n## Topic\n### Rule \xe9\nSome text.\n")
    with pytest.raises(PlaybookError) as exc_info:
        load_playbook(folder)
    msg = str(exc_info.value)
    assert "rules.md" in msg
    assert "UTF-8" in msg


def test_load_playbook_raises_playbook_error_on_latin1_shapes(tmp_path):
    folder = tmp_path / "pb"
    shutil.copytree(SAMPLE_PLAYBOOK, folder)
    (folder / "shapes.json").write_bytes(b'{"$format": {}, "shapes": [\xe9]}')
    with pytest.raises(PlaybookError) as exc_info:
        load_playbook(folder)
    msg = str(exc_info.value)
    assert "shapes.json" in msg
    assert "UTF-8" in msg


def test_load_playbook_raises_playbook_error_on_latin1_wording(tmp_path):
    folder = tmp_path / "pb"
    shutil.copytree(SAMPLE_PLAYBOOK, folder)
    (folder / "wording.json").write_bytes(b'{"$format": {}, "verbs": [\xe9]}')
    with pytest.raises(PlaybookError) as exc_info:
        load_playbook(folder)
    msg = str(exc_info.value)
    assert "wording.json" in msg
    assert "UTF-8" in msg


def test_check_file_accepts_valid_files():
    """check_file validates rules.md, shapes.json, and wording.json without error."""
    for filename in ("rules.md", "shapes.json", "wording.json"):
        check_file(SAMPLE_PLAYBOOK / filename)


def test_check_file_rejects_latin1_file(tmp_path):
    bad = tmp_path / "rules.md"
    bad.write_bytes(b"# Heading\n## Topic\n### Rule\nText \xe9.\n")
    with pytest.raises(PlaybookError, match="rules.md.*UTF-8"):
        check_file(bad)


def test_check_file_rejects_malformed_content(tmp_path):
    orphan_rules = tmp_path / "rules.md"
    orphan_rules.write_text("### Orphan\nNo topic heading.\n", encoding="utf-8")
    with pytest.raises(PlaybookError, match="not under a topic"):
        check_file(orphan_rules)

    bad_json = tmp_path / "shapes.json"
    bad_json.write_text("{ broken json", encoding="utf-8")
    with pytest.raises(PlaybookError, match="not valid JSON"):
        check_file(bad_json)


def test_check_file_rejects_unknown_filename(tmp_path):
    unknown = tmp_path / "unknown.txt"
    unknown.write_text("some text", encoding="utf-8")
    with pytest.raises(PlaybookError, match="not a Playbook file"):
        check_file(unknown)


def test_public_per_file_loaders():
    """load_rules, load_shapes, and load_wording are public functions for individual files."""
    text, topics, rules = load_rules(SAMPLE_PLAYBOOK / "rules.md")
    assert isinstance(text, str)
    assert isinstance(topics, tuple)
    assert "Every line cites this job" in rules

    shapes = load_shapes(SAMPLE_PLAYBOOK / "shapes.json")
    assert "Exhaust Fan" in shapes

    wording = load_wording(SAMPLE_PLAYBOOK / "wording.json")
    assert wording.verbs
