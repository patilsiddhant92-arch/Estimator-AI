"""Check that each new test fails when the code it covers is put back.

    python tools/revert_audit.py <base> <head>

Exports ``head`` into a temporary folder and runs each new test there. The test
must pass on that untouched export. It then puts only the changed ``src`` and
``tools`` files back to ``base`` and runs the test again. A failure there means
the test bites. A pass is vacuous, unless a ``# characterization`` comment
covers the test. The line above the def or its decorators counts only when
that line is a comment and nothing else. A mark in the body counts. A string
that happens to contain those words is not a mark.

A test whose name already exists in the base file is not audited, even when
its body changed. A method named ``test_*`` is audited at every class depth,
and an ``async def`` test is audited too. The node id joins the class names
with ``::``. Renames are followed, so an unchanged renamed file is not
reported as new. For ``src`` and ``tools``, renames are expanded: the old path
is put back and the new path is removed.

A parametrized test is one row. Pytest runs the whole parameter set, and the
row is a failure when any parameter fails.

Exit 1 when any new test passes on the reverted tree without that comment.
Exit 0 when every new test fails there, or is marked. Exit 2 when git cannot
be run, a test file cannot be decoded or parsed, a new test fails on the
untouched head (``BROKEN ON HEAD``), or pytest exits with anything other than
a real test result. On the reverted tree, pytest exit 1 counts as a failure.
Exits 2 and 4 also count as a failure when the output is a collection error
whose ImportError names a changed or removed module, either ``No module named
X`` or ``cannot import name N from X``. Any other exit 2, and exits 3, 4, and
5, are errors.

``PYTHONPATH`` for the pytest run is the export's ``src`` only. The caller's
``PYTHONPATH`` is not kept.

Nothing is written into the repository. The export and the pytest run stay in
a temporary folder.
"""
from __future__ import annotations

import ast
import io
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import tokenize
from pathlib import Path

_MARK = "# characterization"


def _git(repo: Path, *args: str, text: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=text, encoding="utf-8")


def _status(repo: Path, base: str, head: str, *roots: str, renames: bool) -> list[list[str]]:
    flag = "-M" if renames else "--no-renames"
    result = _git(repo, "diff", "--name-status", flag, base, head, "--", *roots)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git diff failed")
    return [line.split("\t") for line in result.stdout.splitlines() if line.strip()]


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
        bundle.extractall(dest, filter="data")


def _restore(repo: Path, base: str, archive: Path, paths: list[str]) -> None:
    for rel in paths:
        target = archive / rel
        old = _blob(repo, f"{base}:{rel}")
        if old is None:
            target.unlink(missing_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(old)


def _as_text(blob: bytes, rel: str) -> str:
    try:
        return blob.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise RuntimeError(f"{rel}: {error}") from None


def _collect(text: str, rel: str) -> list[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]]:
    """``test_*`` functions, including nested classes and ``async def``."""
    if not text.strip():
        return []
    try:
        tree = ast.parse(text)
    except SyntaxError as error:
        raise RuntimeError(f"{rel}: {error}") from None
    found: list[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]] = []

    def walk(body: list[ast.stmt], prefix: str) -> None:
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                found.append((f"{prefix}{node.name}", node))
            elif isinstance(node, ast.ClassDef):
                walk(node.body, f"{prefix}{node.name}::")

    walk(tree.body, "")
    return found


def _comment_lines(text: str, rel: str) -> tuple[set[int], set[int]]:
    """Lines whose comment contains the mark, and lines that are only a comment."""
    marked: set[int] = set()
    comment_only: set[int] = set()
    rows = text.splitlines()
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type != tokenize.COMMENT:
                continue
            line_no = tok.start[0]
            source = rows[line_no - 1] if 1 <= line_no <= len(rows) else ""
            if source.lstrip().startswith("#"):
                comment_only.add(line_no)
            if _MARK in tok.string:
                marked.add(line_no)
    except tokenize.TokenError as error:
        raise RuntimeError(f"{rel}: {error}") from None
    return marked, comment_only


def _is_marked(node: ast.FunctionDef | ast.AsyncFunctionDef, marked: set[int], comment_only: set[int]) -> bool:
    start = min((item.lineno for item in node.decorator_list), default=node.lineno)
    end = node.end_lineno or node.lineno
    if any(line in marked for line in range(start, end + 1)):
        return True
    above = start - 1
    return above in marked and above in comment_only


def _new_tests(base_text: str, head_text: str, rel: str) -> list[tuple[str, bool]]:
    old = {name for name, _node in _collect(base_text, rel)}
    marked, comment_only = _comment_lines(head_text, rel)
    found: list[tuple[str, bool]] = []
    for name, node in _collect(head_text, rel):
        if name in old:
            continue
        found.append((name, _is_marked(node, marked, comment_only)))
    return found


def _run_one(archive: Path, node: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str((archive / "src").resolve())
    # --tb=line keeps the ImportError text. --tb=no drops it, so a collection error cannot be graded.
    return subprocess.run(
        [sys.executable, "-m", "pytest", node, "-q", "--tb=line", "-p", "no:cacheprovider"],
        cwd=archive, capture_output=True, text=True, encoding="utf-8", env=env)


def _module_names(rel: str) -> set[str]:
    path = Path(rel)
    if path.suffix != ".py":
        return set()
    names = {path.stem}
    if rel.startswith("src/"):
        names.add(path.with_suffix("").as_posix()[4:].replace("/", "."))
    return names


def _import_of_removed(output: str, modules: set[str]) -> bool:
    """True when the output is an ImportError naming one of these modules."""
    if "ImportError" not in output and "ModuleNotFoundError" not in output:
        return False
    return any(re.search(rf"(?<![\w.]){re.escape(name)}(?![\w])", output) for name in modules)


def _test_pairs(repo: Path, base: str, head: str) -> list[tuple[str, str | None]]:
    pairs: list[tuple[str, str | None]] = []
    for parts in _status(repo, base, head, "tests", renames=True):
        status = parts[0]
        if status.startswith(("R", "C")) and len(parts) >= 3:
            pairs.append((parts[2], parts[1]))
        elif status.startswith("A") and len(parts) >= 2:
            pairs.append((parts[1], None))
        elif status.startswith(("M", "T")) and len(parts) >= 2:
            pairs.append((parts[1], parts[1]))
    return pairs


def _changed_code(repo: Path, base: str, head: str) -> tuple[list[str], set[str]]:
    paths: list[str] = []
    for parts in _status(repo, base, head, "src", "tools", renames=False):
        paths.extend(parts[1:])
    modules: set[str] = set()
    for rel in paths:
        modules |= _module_names(rel)
    return paths, modules


def _grade(result: subprocess.CompletedProcess[str], marked: bool, modules: set[str]) -> str:
    code = result.returncode
    if code == 0:
        return "PASS characterization" if marked else "PASS vacuous"
    if code == 1:
        return "FAIL"
    output = (result.stdout or "") + (result.stderr or "")
    if code in (2, 4) and _import_of_removed(output, modules):
        return "FAIL"
    return f"ERROR exit {code}"


def audit(repo: Path, base: str, head: str) -> tuple[list[tuple[str, str]], int]:
    """Return rows of (node, verdict) and the exit code. The repo is not modified."""
    with tempfile.TemporaryDirectory() as folder:
        archive = Path(folder) / "export"
        archive.mkdir()
        _export(repo, head, archive)
        code_paths, modules = _changed_code(repo, base, head)
        rows: list[tuple[str, str]] = []
        pending: list[tuple[str, bool]] = []
        broken = False
        for head_rel, base_rel in _test_pairs(repo, base, head):
            if not head_rel.endswith(".py") or Path(head_rel).name.startswith("__"):
                continue
            head_blob = _blob(repo, f"{head}:{head_rel}")
            if head_blob is None:
                continue
            base_text = ""
            if base_rel is not None:
                base_blob = _blob(repo, f"{base}:{base_rel}")
                if base_blob is not None:
                    base_text = _as_text(base_blob, base_rel)
            head_text = _as_text(head_blob, head_rel)
            for name, marked in _new_tests(base_text, head_text, head_rel):
                node = f"{Path(head_rel).as_posix()}::{name}"
                head_run = _run_one(archive, node)
                if head_run.returncode != 0:
                    rows.append((node, "BROKEN ON HEAD"))
                    broken = True
                    continue
                pending.append((node, marked))
        _restore(repo, base, archive, code_paths)
        errored = False
        for node, marked in pending:
            verdict = _grade(_run_one(archive, node), marked, modules)
            if verdict.startswith("ERROR"):
                errored = True
            rows.append((node, verdict))
    if broken or errored:
        code = 2
    elif any(verdict == "PASS vacuous" for _, verdict in rows):
        code = 1
    else:
        code = 0
    return rows, code


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
