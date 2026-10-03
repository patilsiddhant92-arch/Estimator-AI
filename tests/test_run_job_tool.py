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


def test_check_requires_the_kinds_main_list(tmp_path):
    request = tmp_path / "r.json"; answer = tmp_path / "a.json"
    request.write_text(json.dumps({"kind": "read_pass", "schema": {"required": ["facts"], "properties": {}}}), encoding="utf-8")
    answer.write_text(json.dumps({"facts": "none"}), encoding="utf-8")
    bad = subprocess.run([sys.executable, "tools/run_job.py", "check", str(answer), str(request)], capture_output=True, text=True)
    assert bad.returncode == 1 and "facts" in bad.stdout + bad.stderr


def test_status_lists_only_this_jobs_requests(tmp_path):
    sys.path.insert(0, "tools")
    import run_job
    for name, job in (("a", "26-0001"), ("b", "26-0002")):
        (tmp_path / f"{name}.json").write_text(json.dumps(
            {"key": name, "kind": "qc_job", "job": job, "system": None, "answer_file": str(tmp_path / f"{name}-ans.json")}), encoding="utf-8")
    waiting = run_job.waiting_requests(tmp_path, run_job.job_name(Path("X/26-0001, Some School")), {})
    assert [Path(w["file"]).name for w in waiting] == ["a.json"]
