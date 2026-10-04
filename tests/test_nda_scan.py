"""tools/nda_scan.py, against an invented denylist in a temp git repo. No job text."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "nda_scan.py"
TOKEN = "QVEX-4410"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    (repo / "notes.txt").write_text("a clean invented line\n", encoding="utf-8")
    _git(repo, "add", "notes.txt")
    subprocess.run(["git", "-c", "user.email=test@example.com", "-c", "user.name=Test",
                    "commit", "-m", "add an invented note"], cwd=repo, check=True, capture_output=True, text=True)
    return repo


def _run(repo: Path, denylist: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(TOOL), "--denylist", str(denylist), *extra],
                          cwd=repo, capture_output=True, text=True)


def _deny(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "deny.txt"
    path.write_text(text, encoding="utf-8")
    return path


def test_a_whole_word_hit_prints_the_token_and_not_the_line(tmp_path):
    repo = _repo(tmp_path)
    (repo / "notes.txt").write_text("nothing here\nsee QVEX-4410 please\n", encoding="utf-8")
    result = _run(repo, _deny(tmp_path, "QVEX-4410\n\n"))
    assert result.returncode == 1
    assert "notes.txt:2: QVEX-4410" in result.stdout.splitlines()
    assert "please" not in result.stdout
    assert "nothing" not in result.stdout


def test_a_longer_word_is_not_a_hit_and_a_dot_is_literal(tmp_path):
    repo = _repo(tmp_path)
    (repo / "notes.txt").write_text("QVEX-4410X and AxB\n", encoding="utf-8")
    result = _run(repo, _deny(tmp_path, "QVEX-4410\nA.B\n"))
    assert result.returncode == 0
    assert result.stdout == ""


def test_the_match_is_case_insensitive(tmp_path):
    repo = _repo(tmp_path)
    (repo / "notes.txt").write_text("prefix qvex-4410 suffix\n", encoding="utf-8")
    result = _run(repo, _deny(tmp_path, "QVEX-4410\n"))
    assert result.returncode == 1
    assert "notes.txt:1: QVEX-4410" in result.stdout.splitlines()
    assert "prefix" not in result.stdout
    assert "suffix" not in result.stdout


def test_an_untracked_file_is_scanned_and_an_ignored_file_is_not(tmp_path):
    repo = _repo(tmp_path)
    (repo / "loose.txt").write_text("see QVEX-4410 please\n", encoding="utf-8")
    (repo / "secret.txt").write_text("see QVEX-4410 hidden\n", encoding="utf-8")
    (repo / ".gitignore").write_text("secret.txt\n", encoding="utf-8")
    result = _run(repo, _deny(tmp_path, "QVEX-4410\n"))
    assert result.returncode == 1
    assert "loose.txt:1: QVEX-4410" in result.stdout.splitlines()
    assert "secret.txt" not in result.stdout
    assert "hidden" not in result.stdout
    assert "please" not in result.stdout


def test_a_commit_message_is_scanned_without_printing_the_message(tmp_path):
    repo = _repo(tmp_path)
    subprocess.run(["git", "-c", "user.email=test@example.com", "-c", "user.name=Test",
                    "commit", "--allow-empty", "-m", "record QVEX-4410 in the message only"],
                   cwd=repo, check=True, capture_output=True, text=True)
    result = _run(repo, _deny(tmp_path, "QVEX-4410\n"))
    assert result.returncode == 1
    hits = [line for line in result.stdout.splitlines() if TOKEN in line]
    assert len(hits) == 1
    assert hits[0].startswith("commit:")
    assert hits[0].endswith(": QVEX-4410")
    assert "record" not in result.stdout
    assert "only" not in result.stdout


def test_no_hits_exits_zero(tmp_path):
    repo = _repo(tmp_path)
    result = _run(repo, _deny(tmp_path, "QVEX-4410\n"))
    assert result.returncode == 0
    assert result.stdout == ""


def test_self_check_fails_when_the_denylist_is_inside_and_not_ignored(tmp_path):
    repo = _repo(tmp_path)
    listed = repo / "deny.txt"
    listed.write_text("QVEX-4410\n", encoding="utf-8")
    result = _run(repo, listed, "--self-check")
    assert result.returncode == 2
    assert "not ignored" in result.stderr
    assert TOKEN not in result.stdout


def test_self_check_allows_a_denylist_outside_or_ignored(tmp_path):
    repo = _repo(tmp_path)
    outside = _run(repo, _deny(tmp_path, "QVEX-4410\n"), "--self-check")
    assert outside.returncode == 0
    assert outside.stdout == ""

    listed = repo / "deny.txt"
    listed.write_text("QVEX-4410\n", encoding="utf-8")
    (repo / ".gitignore").write_text("deny.txt\n", encoding="utf-8")
    ignored = _run(repo, listed, "--self-check")
    assert ignored.returncode == 0
    assert ignored.stdout == ""
