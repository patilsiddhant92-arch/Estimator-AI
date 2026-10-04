"""Workstream 7: the held-out measurement. The final proposal is written from the invented `small_job` fixture."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from estimator.proposal.write import write_proposal

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import measure  # noqa: E402
from bms.render import RenderedLine  # noqa: E402


def _header(key: str, text: str) -> RenderedLine:
    return RenderedLine(key, None, "header", text, None, None)


def _line(key: str, device: str, text: str, verb: str, quantity: int | None) -> RenderedLine:
    return RenderedLine(key, device, "line", text, verb, quantity)


@pytest.fixture
def final(small_job, proposal_template, tmp_path) -> Path:
    return write_proposal(small_job, proposal_template, tmp_path / "final.docx")


def test_matches_on_system_device_verb_and_quantity(final):
    rendered = [
        _header("EF", "Qty (2) Exhaust Fans EF-1, 2"),
        _line("EF", "EF.d1", "Furnish and Install DDC Controller", "Furnish and Install", 2),
        _header("AHU", "Qty (1) Air Handling Unit AHU-1"),
        _line("AHU", "AHU.d1", "Furnish and Install Space Temperature Sensor", "Furnish and Install", 3),
        _line("AHU", "AHU.d2", "Furnish and Wire Filter DP Switch", "Furnish and Wire", 1),
    ]
    result = measure.measure(rendered, final)
    assert len(result.matched) == 3
    assert result.extra == ()
    assert result.share_matched == len(result.matched) / (len(result.matched) + len(result.missed))
    names = {m.device for m in result.missed}
    assert any("Relay" in n for n in names)   # a final line nothing rendered
    assert result.summary().startswith(f"matched 3/{3 + len(result.missed)}")


def test_wrong_verb_or_quantity_or_system_is_not_a_match(final):
    rendered = [
        _header("EF", "Qty (2) Exhaust Fans EF-1, 2"),
        _line("EF", "EF.d1", "Furnish DDC Controller", "Furnish", 2),                    # verb differs
        _header("AHU", "Qty (1) Air Handling Unit AHU-1"),
        _line("AHU", "AHU.d1", "Furnish Filter DP Switch", "Furnish", 1),   # right words, wrong verb
        _header("CH", "Qty (1) Chiller CH-1"),
        _line("CH", "CH.d1", "Furnish and Install DDC Controller", "Furnish and Install", 2),   # wrong system
    ]
    result = measure.measure(rendered, final)
    assert result.matched == ()
    assert len(result.extra) == 3


def test_an_unknown_rendered_quantity_matches_a_final_line_that_prints_none(final):
    rendered = [_header("EF", "Qty (2) Exhaust Fans EF-1, 2"),
                _line("EF", "EF.d1", "Furnish and Install DDC Controller Qty (##)", "Furnish and Install", None)]
    # the final proposal prints no quantity in the line text, so the unknown quantity still matches
    assert len(measure.measure(rendered, final).matched) == 1


def test_one_final_line_matches_at_most_one_rendered_line(final):
    rendered = [_header("AHU", "Qty (1) Air Handling Unit AHU-1")] + [
        _line("AHU", f"AHU.d{n}", "Furnish and Install Space Temperature Sensor", "Furnish and Install", 3)
        for n in (1, 2)]
    result = measure.measure(rendered, final)
    assert len(result.matched) == 1 and len(result.extra) == 1


def test_notes_and_headers_are_not_measured(final):
    rendered = [_header("EF", "Qty (2) Exhaust Fans EF-1, 2"),
                RenderedLine("EF", None, "note", "*DAMPERS BY OTHERS", None, None)]
    result = measure.measure(rendered, final)
    assert result.matched == () and result.extra == ()


def test_front_end_lines_match_under_front_end(final):
    rendered = [_line("", "FE.d1", "Furnish BMS Server", "Furnish", 1)]
    assert len(measure.measure(rendered, final).matched) == 1


def test_split_line_reads_verb_quantity_and_drops_owner_brackets():
    assert measure._split_line("Furnish and Install DDC Controller [By Unit Mfr.] (3)") == (
        "furnish and install", 3, "DDC Controller")
    assert measure._split_line("Install and Wire Duct Smoke Detector Qty (##)") == (
        "install and wire", None, "Duct Smoke Detector")
    assert measure._split_line("Mfr. to Provide Relay") == (None, None, "Mfr. to Provide Relay")


def test_empty_share_is_one():
    assert measure.MeasureResult((), (), ()).share_matched == 1.0


def test_cli_with_a_rendered_lines_file(final, tmp_path):
    rows = [{"system_key": "EF", "device_id": None, "kind": "header", "text": "Qty (2) Exhaust Fans EF-1, 2",
             "verb": None, "quantity": None},
            {"system_key": "EF", "device_id": "EF.d1", "kind": "line", "text": "Furnish and Install DDC Controller",
             "verb": "Furnish and Install", "quantity": 2}]
    lines = tmp_path / "lines.json"
    lines.write_text(json.dumps(rows), encoding="utf-8")
    done = subprocess.run([sys.executable, str(ROOT / "tools" / "measure.py"), str(lines), str(final)],
                          capture_output=True, text=True, cwd=ROOT)
    assert done.returncode == 0, done.stderr
    assert done.stdout.startswith("matched 1/")
    assert "missed:" in done.stdout


def test_cli_usage():
    done = subprocess.run([sys.executable, str(ROOT / "tools" / "measure.py")], capture_output=True, text=True)
    assert done.returncode == 2 and "usage" in done.stdout
