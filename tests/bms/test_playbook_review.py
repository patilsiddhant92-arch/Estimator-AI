"""REVIEW-023: a non-UTF-8 JSON Playbook file is reported as bad JSON.

Invented bytes only. Fails on gemini/task-023 3f161ba.
"""
from pathlib import Path

import pytest

from bms.playbook import PlaybookError, check_file


def test_a_non_utf8_json_file_is_an_encoding_error(tmp_path: Path):
    # 0xE9 is not UTF-8. _read raises PlaybookError, and PlaybookError is a ValueError, so _json
    # catches it and reports "not valid JSON" with the encoding sentence buried inside.
    for name in ("shapes.json", "wording.json"):
        bad = tmp_path / name
        bad.write_bytes(b"\xe9")
        with pytest.raises(PlaybookError) as caught:
            check_file(bad)
        message = str(caught.value)
        assert name in message
        assert "not valid UTF-8" in message
        assert "not valid JSON" not in message
