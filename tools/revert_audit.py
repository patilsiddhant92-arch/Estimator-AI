"""Check that each new test fails when the code it covers is put back.

    python tools/revert_audit.py <base> <head>

Exports ``head`` into a temporary folder, puts only the changed ``src`` and
``tools`` files back to ``base``, and runs the test files that changed. A new
test that FAILS there is doing its job. A new test that PASSES is vacuous,
unless the test itself carries the comment ``# characterization``. Exit 1 when
any new test passes without that comment. Exit 0 when every new test fails or
is marked. Exit 2 when git or pytest cannot be run.

Nothing is written into the repository. The export and the pytest run stay in
a temporary folder.
"""
from __future__ import annotations

import ast
import io
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

_MARK = "# characterization"


def _git(repo: Path, *args: str, text: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=text, encoding="utf-8")


def _names(repo: Path, base: str, head: str, *roots: str) -> list[str]:
    result = _git(repo, "diff", "--name-only", base, head, "--", *roots)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git diff failed")
    return [line for line in result.stdout.splitlines() if line]


def _blob(repo: Path, spec: str) -> bytes | None:
    result = subprocess.run(["git", "cat-file", "-e", spec], cwd=repo, capture_output=True)
    if result.returncode != 0:
        return None
    data = subprocess.run(["git", "cat-file", "blob", spec], cwd=repo, capture_output=True)
    if data.returncode != 0:
        raise RuntimeError(data.stderr.decode("utf-8", "replace").strip() or f"cannot read {spec}")
    return data.stdout


def _export(repo: Path, head: str, dest: Path) -> None:
    packed = subprocess.run(["git", "archive", head], cwd=repo, capture_output=True)
    if packed.returncode != 0:
        raise RuntimeError(packed.stderr.decode("utf-8", "replace").strip() or "git archive failed")
    with tarfile.open(fileobj=io.BytesIO(packed.stdout)) as bundle:
        bundle.extractall(dest)


def _restore(repo: Path, base: str, archive: Path, paths: list[str]) -> None:
    for rel in paths:
        target = archive / rel
        old = _blob(repo, f"{base}:{rel}")
        if old is None:
            target.unlink(missing_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(old)


def _functions(text: str) -> list[ast.FunctionDef]:
    if not text.strip():
        return []
    tree = ast.parse(text)
    return [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")]


def _new_tests(base_text: str, head_text: str) -> list[tuple[str, bool]]:
    old = {node.name for node in _functions(base_text)}
    found: list[tuple[str, bool]] = []
    lines = head_text.splitlines()
    for node in _functions(head_text):
        if node.name in old:
            continue
        end = node.end_lineno or node.lineno
        body = "\n".join(lines[node.lineno - 1:end])
        found.append((node.name, _MARK in body))
    return found


def _run_one(archive: Path, node: str) -> bool:
    env = os.environ.copy()
    env["PYTHONPATH"] = "src" + os.pathsep + env.get("PYTHONPATH", "")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", node, "-q", "--tb=no", "-p", "no:cacheprovider"],
        cwd=archive, capture_output=True, text=True, encoding="utf-8", env=env)
    return result.returncode == 0


def audit(repo: Path, base: str, head: str) -> tuple[list[tuple[str, str]], int]:
    """Return rows of (node, verdict) and the exit code. The repo is not modified."""
    with tempfile.TemporaryDirectory() as folder:
        archive = Path(folder) / "export"
        archive.mkdir()
        _export(repo, head, archive)
        _restore(repo, base, archive, _names(repo, base, head, "src", "tools"))
        rows: list[tuple[str, str]] = []
        for rel in _names(repo, base, head, "tests"):
            if not rel.endswith(".py") or Path(rel).name.startswith("__"):
                continue
            head_blob = _blob(repo, f"{head}:{rel}")
            if head_blob is None:
                continue
            base_blob = _blob(repo, f"{base}:{rel}")
            base_text = "" if base_blob is None else base_blob.decode("utf-8")
            head_text = head_blob.decode("utf-8")
            for name, marked in _new_tests(base_text, head_text):
                node = f"{Path(rel).as_posix()}::{name}"
                passed = _run_one(archive, node)
                if passed and marked:
                    verdict = "PASS characterization"
                elif passed:
                    verdict = "PASS vacuous"
                else:
                    verdict = "FAIL"
                rows.append((node, verdict))
    vacuous = any(verdict == "PASS vacuous" for _, verdict in rows)
    return rows, 1 if vacuous else 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2:
        print("Usage: python tools/revert_audit.py <base> <head>", file=sys.stderr)
        return 2
    repo = Path.cwd()
    try:
        rows, code = audit(repo, args[0], args[1])
    except (RuntimeError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(f"{'test':<60} result")
    for node, verdict in rows:
        print(f"{node:<60} {verdict}")
    print(f"{len(rows)} new test(s); {sum(v == 'PASS vacuous' for _, v in rows)} vacuous")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
