"""REVIEW-017c: gaps in tools/nda_scan.py found by the primary review. Invented tokens and files only.

Each test fails on grok/correct-017 ba63bec.
"""
from __future__ import annotations

import io
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "nda_scan.py"
TOKEN = "QVEX-4410"


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    (repo / "notes.txt").write_text("a clean invented line\n", encoding="utf-8")
    subprocess.run(["git", "add", "notes.txt"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "-c", "user.email=test@example.com", "-c", "user.name=Test", "commit", "-m", "init"],
                   cwd=repo, check=True, capture_output=True)
    return repo


def _run(repo: Path, tmp_path: Path, tokens: str = TOKEN + "\n") -> subprocess.CompletedProcess[str]:
    denylist = tmp_path / "deny.txt"
    denylist.write_text(tokens, encoding="utf-8")
    return subprocess.run([sys.executable, str(TOOL), "--denylist", str(denylist)], cwd=repo,
                          capture_output=True, text=True)


def _docx(xml: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", xml)
    return buffer.getvalue()


def test_a_docx_with_a_damaged_part_is_listed_as_unread_and_not_a_crash(tmp_path):
    # The zip directory is intact, so ZipFile() opens it; reading the damaged part raises zlib.error (or
    # BadZipFile on a CRC mismatch), which _office_xml does not catch. Expected: exit 2 and the name on stderr.
    repo = _repo(tmp_path)
    data = bytearray(_docx("<w:t>" + "invented filler " * 300 + "</w:t>"))
    start = data.find(b"word/document.xml") + len(b"word/document.xml") + 10
    for i in range(start, start + 20):
        data[i] ^= 0xFF
    (repo / "damaged.docx").write_bytes(bytes(data))
    (repo / "notes.txt").write_text(f"see {TOKEN}\n", encoding="utf-8")
    result = _run(repo, tmp_path)
    assert "Traceback" not in result.stderr
    assert result.returncode == 2
    assert "damaged.docx" in result.stderr
    assert f"notes.txt:1: {TOKEN}" in result.stdout.splitlines()


def test_a_token_split_across_word_runs_is_found(tmp_path):
    # Word often splits one word over several <w:r> runs (spelling marks, edits); the text is still the token.
    repo = _repo(tmp_path)
    (repo / "split.docx").write_bytes(
        _docx("<w:p><w:r><w:t>see QVEX-</w:t></w:r><w:r><w:t>4410</w:t></w:r><w:r><w:t> please</w:t></w:r></w:p>"))
    result = _run(repo, tmp_path)
    assert result.returncode == 1
    assert any(line.startswith("split.docx:") and line.endswith(TOKEN) for line in result.stdout.splitlines())


def test_a_utf16_file_without_a_byte_order_mark_is_not_passed_clean(tmp_path):
    # UTF-16-LE without a BOM is valid UTF-8 (full of NUL bytes), so it decodes, the token never matches,
    # and the scan exits 0. It must either find the token or say the file could not be read.
    repo = _repo(tmp_path)
    (repo / "wide.txt").write_bytes(f"see {TOKEN} please\n".encode("utf-16-le"))
    result = _run(repo, tmp_path)
    assert result.returncode != 0
    assert "wide.txt" in result.stdout + result.stderr


def test_an_xml_entity_in_a_word_run_is_found(tmp_path):
    # The token is the invented firm name. The XML stores the ampersand as an entity, so a raw scan misses it.
    repo = _repo(tmp_path)
    (repo / "firm.docx").write_bytes(_docx("<w:t>Smith &amp; Sons</w:t>"))
    result = _run(repo, tmp_path, tokens="Smith & Sons\n")
    assert result.returncode == 1
    assert any(line.startswith("firm.docx:") and line.endswith("Smith & Sons") for line in result.stdout.splitlines())


def test_a_rels_part_is_scanned(tmp_path):
    repo = _repo(tmp_path)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/_rels/document.xml.rels", f'<Relationship Target="notes/{TOKEN}.txt"/>')
    (repo / "links.docx").write_bytes(buffer.getvalue())
    result = _run(repo, tmp_path)
    assert result.returncode == 1
    assert any(line.startswith("links.docx:") and line.endswith(TOKEN) for line in result.stdout.splitlines())


def test_a_docm_zip_is_scanned(tmp_path):
    repo = _repo(tmp_path)
    (repo / "macro.docm").write_bytes(_docx(f"<w:t>see {TOKEN}</w:t>"))
    result = _run(repo, tmp_path)
    assert result.returncode == 1
    assert any(line.startswith("macro.docm:") and line.endswith(TOKEN) for line in result.stdout.splitlines())


def test_a_windows_1252_file_reports_the_token_and_stays_unread(tmp_path):
    # 0x80 is not a UTF-8 byte. The token is still in the file, and the file stays unread.
    repo = _repo(tmp_path)
    (repo / "latin.txt").write_bytes(f"see {TOKEN} please\n".encode("ascii") + b"\x80")
    result = _run(repo, tmp_path)
    assert result.returncode == 2
    assert f"latin.txt:1: {TOKEN}" in result.stdout.splitlines()
    assert "latin.txt" in result.stderr


def test_a_form_feed_does_not_add_a_line(tmp_path):
    repo = _repo(tmp_path)
    (repo / "feed.txt").write_bytes(b"a\x0cb\nsee " + TOKEN.encode("ascii") + b"\n")
    result = _run(repo, tmp_path)
    assert f"feed.txt:2: {TOKEN}" in result.stdout.splitlines()


def _load():
    import importlib.util
    spec = importlib.util.spec_from_file_location("nda_scan_under_test", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_file_over_the_cap_is_named_unread(tmp_path, monkeypatch, capsys):
    module = _load()
    module._MAX_BYTES = 24
    repo = _repo(tmp_path)
    (repo / "big.txt").write_text(f"see {TOKEN} and more padding text\n", encoding="utf-8")
    denylist = tmp_path / "deny.txt"
    denylist.write_text(TOKEN + "\n", encoding="utf-8")
    monkeypatch.chdir(repo)
    code = module.main(["--denylist", str(denylist)])
    captured = capsys.readouterr()
    assert code == 2
    assert "big.txt" in captured.err
    assert TOKEN not in captured.out


def test_a_zip_part_over_the_cap_is_unread(tmp_path, monkeypatch, capsys):
    module = _load()
    xml = "<w:t>" + TOKEN + ("y" * 400) + "</w:t>"
    data = _docx(xml)
    assert len(xml) > len(data)
    module._MAX_BYTES = len(data) + 10
    assert len(xml) > module._MAX_BYTES
    repo = _repo(tmp_path)
    (repo / "fat.docx").write_bytes(data)
    denylist = tmp_path / "deny.txt"
    denylist.write_text(TOKEN + "\n", encoding="utf-8")
    monkeypatch.chdir(repo)
    code = module.main(["--denylist", str(denylist)])
    captured = capsys.readouterr()
    assert code == 2
    assert "fat.docx" in captured.err
    assert TOKEN not in captured.out
