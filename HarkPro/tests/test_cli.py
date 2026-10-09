import json
from pathlib import Path

from harkpro.cli import main

FIX = Path(__file__).parent / "fixtures"


def test_cli_coverage_and_evidence(tmp_path, capsys):
    assert main(["coverage", str(FIX / "ledger.json"), str(FIX / "job.json"), "--out", str(tmp_path),
                 "--lines", str(FIX / "lines.json")]) == 0
    assert main(["coverage", str(FIX / "ledger.json"), str(FIX / "job.json"), "--out", str(tmp_path),
                 "--strict"]) == 2
    assert "coverage FAIL" in capsys.readouterr().out
    assert main(["evidence", str(FIX / "ledger.json"), str(FIX / "job.json"), "--out", str(tmp_path),
                 "--debug"]) == 0
    assert (tmp_path / "sample-clinic Evidence (HarkPro).xlsx").exists()
    assert (tmp_path / "sample-clinic Evidence debug (HarkPro).xlsx").exists()


def test_cli_diff(tmp_path, capsys):
    from test_score import V1, V2, proposal
    a, b = proposal(tmp_path / "a.docx", V1), proposal(tmp_path / "b.docx", V2)
    assert main(["diff", str(a), str(b), "--out", str(tmp_path), "--name", "g"]) == 0
    assert "lines +2 -1 ~2" in capsys.readouterr().out
    assert main(["score", str(a), str(a), "--out", str(tmp_path), "--name", "same"]) == 0
    assert "no change" in capsys.readouterr().out
    assert json.loads((tmp_path / "g diff.json").read_text())["totals"]["blocks_added"] == 1
