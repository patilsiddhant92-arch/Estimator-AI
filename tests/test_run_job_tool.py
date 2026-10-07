# tests/test_run_job_tool.py
import json, os, subprocess, sys
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


def test_a_request_whose_answer_was_rejected_is_listed_and_its_answer_removed(tmp_path):
    sys.path.insert(0, "tools")
    import run_job
    answer = tmp_path / "a-ans.json"
    answer.write_text(json.dumps({"lines": "not a list"}), encoding="utf-8")
    (tmp_path / "a.json").write_text(json.dumps(
        {"key": "a", "kind": "write_system", "job": "26-0001", "system": "Rooftop Unit RTU-1", "answer_file": str(answer)}),
        encoding="utf-8")
    attempts = {}
    printed = "Writing systems: 1 request waiting\n  the answer for Rooftop Unit RTU-1 could not be read\n"
    waiting = run_job.waiting_requests(tmp_path, "26-0001", attempts, printed)
    assert len(waiting) == 1 and waiting[0]["rejected"] is True
    assert waiting[0]["reason"] == "the answer for Rooftop Unit RTU-1 could not be read"
    assert not answer.exists() and attempts == {"a": 1} and waiting[0]["attempts"] == 1


def _request_and_answer(tmp_path, request_ns, answer_ns):
    """One request and its answer file, with their modified times set exactly (nanoseconds)."""
    answer = tmp_path / "a-ans.json"
    answer.write_text(json.dumps({"lines": []}), encoding="utf-8")
    request = tmp_path / "a.json"
    request.write_text(json.dumps(
        {"key": "a", "kind": "write_system", "job": "26-0001", "system": "Rooftop Unit RTU-1", "answer_file": str(answer)}),
        encoding="utf-8")
    os.utime(request, ns=(request_ns, request_ns))
    os.utime(answer, ns=(answer_ns, answer_ns))
    return answer


def test_an_answer_newer_than_its_request_is_kept_and_not_counted_as_rejected(tmp_path):
    sys.path.insert(0, "tools")
    import run_job
    answer = _request_and_answer(tmp_path, 1_000_000_000_000, 2_000_000_000_000)
    attempts = {}
    waiting = run_job.waiting_requests(tmp_path, "26-0001", attempts, "Waiting: 1 request(s) at the write step.")
    assert len(waiting) == 1 and "rejected" not in waiting[0]
    assert answer.exists() and attempts == {} and waiting[0]["attempts"] == 0


def test_a_request_rewritten_after_its_answer_is_rejected(tmp_path):
    sys.path.insert(0, "tools")
    import run_job
    answer = _request_and_answer(tmp_path, 2_000_000_000_000, 1_000_000_000_000)
    attempts = {}
    waiting = run_job.waiting_requests(tmp_path, "26-0001", attempts, "the answer for Rooftop Unit RTU-1 could not be read")
    assert waiting[0]["rejected"] is True and not answer.exists() and attempts == {"a": 1}


def test_a_crashed_estimate_rejects_and_deletes_nothing(tmp_path):
    sys.path.insert(0, "tools")
    import run_job
    answer = _request_and_answer(tmp_path, 2_000_000_000_000, 1_000_000_000_000)
    attempts = {}
    crashed = "Traceback (most recent call last):\n  File x.py, line 1\nValueError: boom\n"
    waiting = run_job.waiting_requests(tmp_path, "26-0001", attempts, crashed)
    assert len(waiting) == 1 and "rejected" not in waiting[0]
    assert answer.exists() and attempts == {}


def test_a_stop_names_the_decisions_stage():
    sys.path.insert(0, "tools")
    from run_job import stage_of

    assert stage_of("Stopped at the decisions step.") == "decisions"
    assert stage_of("Waiting: 2 request(s) at the write step.") == "write"
    text = Path("docs/superpowers/specs/2026-10-04-rebuild-interfaces.md").read_text(encoding="utf-8")
    assert "decisions" in text and "exits 0 when done, 2 when requests are waiting, and 1 when" in text


def test_the_skill_stops_when_nothing_waits_and_no_proposal_was_written():
    text = Path(".claude/skills/run-job/SKILL.md").read_text(encoding="utf-8")
    assert "no waiting requests and no proposal: report the last summary and stop" in text


def test_an_earlier_runs_attempt_count_does_not_carry_over_to_a_fresh_request(tmp_path):
    sys.path.insert(0, "tools")
    import run_job
    (tmp_path / "k.json").write_text(json.dumps(
        {"key": "k", "kind": "qc_job", "job": "26-0001", "system": None, "answer_file": str(tmp_path / "k-ans.json")}),
        encoding="utf-8")
    attempts = {"k": 3, "gone": 2}
    waiting = run_job.waiting_requests(tmp_path, "26-0001", attempts, "")
    assert waiting[0]["attempts"] == 0 and attempts == {}


def test_a_retry_of_a_refused_answer_keeps_its_count(tmp_path):
    sys.path.insert(0, "tools")
    import run_job
    (tmp_path / "k.json").write_text(json.dumps(
        {"key": "k", "kind": "qc_job", "job": "26-0001", "system": None, "previous_problem": "no",
         "answer_file": str(tmp_path / "k-ans.json")}), encoding="utf-8")
    attempts = {"k": 2}
    assert run_job.waiting_requests(tmp_path, "26-0001", attempts, "")[0]["attempts"] == 2


def test_status_prints_its_json_block_on_a_cp1252_console(tmp_path):
    """A fake estimate prints a character cp1252 cannot hold; the JSON block still comes out, parseable."""
    pkg = tmp_path / "fake" / "bms"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "__main__.py").write_text("import sys\nsys.stdout.reconfigure(encoding='utf-8')\nprint('count \u2265 5')\n",
                                     encoding="utf-8")
    env = dict(os.environ, PYTHONIOENCODING="cp1252", PYTHONPATH=str(tmp_path / "fake"))
    run = subprocess.run([sys.executable, "tools/run_job.py", "status", str(tmp_path / "26-0001"), "--out",
                          str(tmp_path / "out")], capture_output=True, env=env)
    text = run.stdout.decode("utf-8").replace(chr(13) + chr(10), chr(10))
    assert run.returncode == 0, run.stderr
    block = json.loads(text[text.index('{\n "waiting"'):])
    assert block["waiting"] == [] and block["exit"] == 0
