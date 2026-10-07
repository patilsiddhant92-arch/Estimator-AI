"""REVIEW-021b: gaps left in the corrected revert audit (grok/correct-021 cd0bc64). Invented temp git repos only.

Each test fails on cd0bc64.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "revert_audit.py"
OLD_CODE = "def answer():\n    return 0\n"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.email=tester@example.com", "-c", "user.name=Tester", *args],
                          cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


def _commit(repo: Path, files: dict[str, str], message: str) -> str:
    for rel, text in files.items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "--allow-empty", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _repo(tmp_path: Path, base: dict[str, str], head: dict[str, str]) -> tuple[Path, str, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    return repo, _commit(repo, base, "base"), _commit(repo, head, "head")


def _run(repo: Path, base: str, head: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(TOOL), base, head], cwd=repo, capture_output=True, text=True)


def test_a_top_level_import_of_a_new_name_from_a_changed_module_bites(tmp_path):
    # The usual shape of a new test file: `from module import the_new_function` at the top. Without the code,
    # collection fails (pytest exit 4 for a node id, or 2) because the name is missing from a CHANGED module.
    # That is the test biting, not a tool error; today it is "ERROR exit 4" and the audit exits 2.
    repo, base, head = _repo(tmp_path, {"src/demo.py": OLD_CODE}, {
        "src/demo.py": OLD_CODE + "\n\ndef new_func():\n    return 2\n",
        "tests/test_demo.py": "from demo import new_func\n\n\ndef test_new_func():\n    assert new_func() == 2\n",
    })
    result = _run(repo, base, head)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "tests/test_demo.py::test_new_func" in result.stdout
    assert "FAIL" in result.stdout


def test_a_top_level_import_of_a_new_module_bites(tmp_path):
    # The linter branch's own shape: a new module and a new test file that imports it at the top. pytest exits 4
    # for the node id when collection fails, and only exit 2 is checked for an ImportError of a removed module.
    repo, base, head = _repo(tmp_path, {"src/demo.py": OLD_CODE}, {
        "src/fresh_module.py": "def value():\n    return 3\n",
        "tests/test_fresh.py": "from fresh_module import value\n\n\ndef test_value():\n    assert value() == 3\n",
    })
    result = _run(repo, base, head)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "tests/test_fresh.py::test_value" in result.stdout
    assert "FAIL" in result.stdout


def test_a_mark_ending_the_previous_test_does_not_cover_the_next(tmp_path):
    # The "line above the def" rule reads the last line of the previous test when there is no blank line.
    repo, base, head = _repo(tmp_path, {"src/demo.py": OLD_CODE}, {
        "src/demo.py": OLD_CODE.replace("0", "1"),
        "tests/test_demo.py": ("def test_kept_snapshot():\n    assert True  # characterization\n"
                               "def test_vacuous():\n    assert True\n"),
    })
    result = _run(repo, base, head)
    assert "test_vacuous" in result.stdout and "PASS vacuous" in result.stdout
    assert result.returncode == 1


def test_a_nested_class_test_is_audited(tmp_path):
    # One class level is audited. A test on a class inside a class is not, so a vacuous one exits 0.
    repo, base, head = _repo(tmp_path, {"src/demo.py": OLD_CODE}, {
        "src/demo.py": OLD_CODE.replace("0", "1"),
        "tests/test_demo.py": ("class TestOuter:\n"
                               "    class TestInner:\n"
                               "        def test_vac(self):\n"
                               "            assert True\n"),
    })
    result = _run(repo, base, head)
    assert "TestOuter::TestInner::test_vac" in result.stdout
    assert "PASS vacuous" in result.stdout
    assert result.returncode == 1


def test_an_async_test_is_audited(tmp_path):
    # async def tests are not collected. This venv has no async plugin, so once the test is seen it fails on
    # the new code and the row is BROKEN ON HEAD.
    repo, base, head = _repo(tmp_path, {"src/demo.py": OLD_CODE}, {
        "src/demo.py": OLD_CODE.replace("0", "1"),
        "tests/test_demo.py": "async def test_async():\n    assert True\n",
    })
    result = _run(repo, base, head)
    assert "tests/test_demo.py::test_async" in result.stdout
    assert "BROKEN ON HEAD" in result.stdout
    assert result.returncode == 2
