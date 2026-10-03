# tests/test_run_job_tool.py
import json, subprocess, sys
from pathlib import Path


def test_check_accepts_a_complete_answer_and_rejects_a_missing_key(tmp_path):
    request = tmp_path / "r.json"; answer = tmp_path / "a.json"
    request.write_text(json.dumps({"kind": "read_pass", "schema": {"required": ["facts", "understanding"], "properties": {}}}), encoding="utf-8")
    answer.write_text(json.dumps({"facts": [], "understanding": "ok"}), encoding="utf-8")
    ok = subprocess.run([sys.executable, "tools/run_job.py", "check", str(answer), str(request)], capture_output=True, text=True)
    assert ok.returncode == 0
    answer.write_text(json.dumps({"facts": []}), encoding="utf-8")
    bad = subprocess.run([sys.executable, "tools/run_job.py", "check", str(answer), str(request)], capture_output=True, text=True)
    assert bad.returncode == 1 and "understanding" in bad.stdout + bad.stderr
