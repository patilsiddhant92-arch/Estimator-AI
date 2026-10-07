"""tools/revert_audit.py, against an invented git repo. No job text."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "revert_audit.py"


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-c", "user.email=tester@example.com", "-c", "user.name=Tester", *args],
        cwd=repo, check=True, capture_output=True, text=True, encoding="utf-8")


def _repo(tmp_path: Path, head_test: str, code_root: str = "src") -> tuple[Path, str, str]:
    repo = tmp_path / "repo"
    (repo / code_root).mkdir(parents=True)
    (repo / "tests").mkdir()
    _git(repo, "init", "-b", "main")
    (repo / code_root / "demo.py").write_text("def answer():\n    return 0\n", encoding="utf-8")
    (repo / "tests" / "test_demo.py").write_text("def test_old():\n    assert True\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD").stdout.strip()
    (repo / code_root / "demo.py").write_text("def answer():\n    return 1\n", encoding="utf-8")
    (repo / "tests" / "test_demo.py").write_text(head_test, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "head")
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    return repo, base, head


def _run(repo: Path, base: str, head: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), base, head],
        cwd=repo, capture_output=True, text=True, encoding="utf-8")


_HEAD = """
def test_old():
    assert True

def test_the_new_answer_is_one():
    from demo import answer
    assert answer() == 1

def test_true_is_true():
    assert True

def test_a_kept_snapshot():  # characterization
    assert True
"""


def test_a_new_test_that_passes_without_the_code_is_vacuous(tmp_path):
    repo, base, head = _repo(tmp_path, _HEAD)
    before = _git(repo, "status", "--porcelain").stdout
    result = _run(repo, base, head)
    assert _git(repo, "status", "--porcelain").stdout == before
    assert result.returncode == 1
    text = result.stdout
    assert "test_demo.py::test_the_new_answer_is_one" in text and "FAIL" in text
    assert "test_demo.py::test_true_is_true" in text and "PASS vacuous" in text
    assert "test_demo.py::test_a_kept_snapshot" in text and "PASS characterization" in text
    assert "test_old" not in text


def test_a_tools_change_is_reverted_too(tmp_path):
    head = """
def test_the_new_answer_is_one():
    import importlib.util
    spec = importlib.util.spec_from_file_location("demo", "tools/demo.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.answer() == 1
"""
    repo, base, head_rev = _repo(tmp_path, head, code_root="tools")
    result = _run(repo, base, head_rev)
    assert result.returncode == 0
    assert "PASS vacuous" not in result.stdout
    assert "test_demo.py::test_the_new_answer_is_one" in result.stdout
    assert "FAIL" in result.stdout
