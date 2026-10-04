"""REVIEW-021: gaps in tools/revert_audit.py found by the primary review. Invented temp git repos only.

Each test fails on grok/task-021 bd0093b.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "revert_audit.py"
OLD_CODE = "def answer():\n    return 0\n"
NEW_CODE = "def answer():\n    return 1\n"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.email=tester@example.com", "-c", "user.name=Tester", *args],
                          cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


def _commit(repo: Path, files: dict[str, bytes | None], message: str) -> str:
    for rel, data in files.items():
        path = repo / rel
        if data is None:
            path.unlink()
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    _git(repo, "add", "-A")
    _git(repo, "commit", "--allow-empty", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _repo(tmp_path: Path, base: dict[str, bytes | None], head: dict[str, bytes | None]) -> tuple[Path, str, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    return repo, _commit(repo, base, "base"), _commit(repo, head, "head")


def _run(repo: Path, base: str, head: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(TOOL), base, head], cwd=repo, capture_output=True, text=True)


def test_a_new_test_that_also_fails_on_head_is_not_reported_as_biting(tmp_path):
    # Any non-zero pytest exit is read as "fails without the code (good)". A test that fails WITH the code
    # too (or never runs) proves nothing; the audit must not exit 0 on it.
    repo, base, head = _repo(tmp_path, {"src/demo.py": OLD_CODE.encode()}, {
        "src/demo.py": NEW_CODE.encode(),
        "tests/test_demo.py": b"def test_broken_everywhere():\n    assert False\n",
    })
    result = _run(repo, base, head)
    assert result.returncode != 0, result.stdout


def test_a_renamed_test_file_has_no_new_tests(tmp_path):
    kept = b"def test_kept():\n    assert True\n"
    repo, base, head = _repo(tmp_path, {"src/demo.py": OLD_CODE.encode(), "tests/test_old_name.py": kept}, {
        "src/demo.py": NEW_CODE.encode(),
        "tests/test_old_name.py": None,
        "tests/test_new_name.py": kept,
    })
    result = _run(repo, base, head)
    assert result.returncode == 0, result.stdout
    assert "PASS vacuous" not in result.stdout


def test_a_test_file_saved_with_a_utf8_bom_is_audited(tmp_path):
    # Windows editors and PowerShell often write a UTF-8 BOM; pytest reads such a file fine.
    repo, base, head = _repo(tmp_path, {"src/demo.py": OLD_CODE.encode()}, {
        "src/demo.py": NEW_CODE.encode(),
        "tests/test_demo.py": b"\xef\xbb\xbfdef test_bites():\n    from demo import answer\n    assert answer() == 1\n",
    })
    result = _run(repo, base, head)
    assert "Traceback" not in result.stderr
    assert result.returncode == 0
    assert "tests/test_demo.py::test_bites" in result.stdout


def test_a_characterization_comment_above_the_def_is_honored(tmp_path):
    # The mark sits on the line above the def. Today only the def line and the body are read.
    repo, base, head = _repo(tmp_path, {"src/demo.py": OLD_CODE.encode()}, {
        "src/demo.py": NEW_CODE.encode(),
        "tests/test_demo.py": b"# characterization\ndef test_kept():\n    assert True\n",
    })
    result = _run(repo, base, head)
    assert result.returncode == 0, result.stdout
    assert "PASS characterization" in result.stdout
    assert "PASS vacuous" not in result.stdout
    assert "DeprecationWarning" not in result.stderr


def test_a_characterization_string_is_not_a_mark(tmp_path):
    # The words appear in a string, which is not a comment. The test passes without the code, so it is vacuous.
    repo, base, head = _repo(tmp_path, {"src/demo.py": OLD_CODE.encode()}, {
        "src/demo.py": NEW_CODE.encode(),
        "tests/test_demo.py": b"def test_kept():\n    note = \"# characterization\"\n    assert True\n",
    })
    result = _run(repo, base, head)
    assert result.returncode == 1, result.stdout
    assert "PASS vacuous" in result.stdout


def test_a_syntax_error_is_reported_without_a_traceback(tmp_path):
    repo, base, head = _repo(tmp_path, {"src/demo.py": OLD_CODE.encode()}, {
        "src/demo.py": NEW_CODE.encode(),
        "tests/test_demo.py": b"def test_broken(\n",
    })
    result = _run(repo, base, head)
    assert "Traceback" not in result.stderr
    assert result.returncode == 2


def test_a_new_test_inside_a_class_is_audited(tmp_path):
    # A method on a class is invisible to a scan that only reads top-level functions, so the audit exits 0
    # with an empty table. It has to run the method and record that it fails once the code is put back.
    body = (
        "class TestDemo:\n"
        "    def test_bites(self):\n"
        "        from demo import answer\n"
        "        assert answer() == 1\n"
    )
    repo, base, head = _repo(tmp_path, {"src/demo.py": OLD_CODE.encode()}, {
        "src/demo.py": NEW_CODE.encode(),
        "tests/test_demo.py": body.encode(),
    })
    result = _run(repo, base, head)
    assert result.returncode == 0, result.stdout
    assert "tests/test_demo.py::TestDemo::test_bites" in result.stdout
    assert "FAIL" in result.stdout


def test_the_caller_pythonpath_cannot_supply_a_deleted_module(tmp_path, monkeypatch):
    # The reverted export deletes src/demo.py. A PYTHONPATH left by the caller still has a copy that returns 1,
    # so the old audit grades the test vacuous.
    decoy = tmp_path / "decoy"
    decoy.mkdir()
    (decoy / "demo.py").write_text(NEW_CODE, encoding="utf-8")
    monkeypatch.setenv("PYTHONPATH", str(decoy))
    repo, base, head = _repo(tmp_path, {"README.md": b"invented\n"}, {
        "README.md": b"invented\n",
        "src/demo.py": NEW_CODE.encode(),
        "tests/test_demo.py": b"def test_bites():\n    from demo import answer\n    assert answer() == 1\n",
    })
    result = _run(repo, base, head)
    assert result.returncode == 0, result.stdout
    assert "PASS vacuous" not in result.stdout
    assert "FAIL" in result.stdout
