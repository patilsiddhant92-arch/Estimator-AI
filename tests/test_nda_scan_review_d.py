"""REVIEW-017d: gaps left in the corrected NDA scan (grok/correct-017c c82ab6d). Invented tokens and files only.

Each test fails on c82ab6d: the scan exits 0 (clean) while the token is in the file.
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


def _run(repo: Path, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    denylist = tmp_path / "deny.txt"
    denylist.write_text(TOKEN + "\n", encoding="utf-8")
    return subprocess.run([sys.executable, str(TOOL), "--denylist", str(denylist)], cwd=repo,
                          capture_output=True, text=True)


def test_utf8_text_with_one_stray_nul_is_not_read_as_utf16(tmp_path):
    # Even length, one NUL: it decodes as UTF-16-LE without any NUL, so the UTF-8 reading (which holds the
    # token) is thrown away. ba63bec found this token; c82ab6d passes the file clean.
    repo = _repo(tmp_path)
    raw = f"see {TOKEN} here\n\x00".encode()
    assert len(raw) % 2 == 0
    (repo / "notes2.txt").write_bytes(raw)
    result = _run(repo, tmp_path)
    assert result.returncode != 0
    assert "notes2.txt" in result.stdout + result.stderr


def test_a_text_file_inside_a_zip_is_not_passed_clean(tmp_path):
    # Every PK file is now opened as a zip, but only .xml and .rels parts are read; a .txt part is skipped
    # silently. It must be scanned, or the zip must be named unread.
    repo = _repo(tmp_path)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("notes/readme.txt", f"see {TOKEN}\n")
    (repo / "bundle.zip").write_bytes(buffer.getvalue())
    result = _run(repo, tmp_path)
    assert result.returncode != 0
    assert "bundle.zip" in result.stdout + result.stderr


def _docx(xml: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", xml)
    return buffer.getvalue()


def test_an_office_hit_is_printed_once_and_names_the_part(tmp_path):
    repo = _repo(tmp_path)
    (repo / "plain.docx").write_bytes(_docx(f"<w:t>see {TOKEN}</w:t>"))
    result = _run(repo, tmp_path)
    hits = [line for line in result.stdout.splitlines() if line.endswith(TOKEN)]
    assert hits == [f"plain.docx!word/document.xml:1: {TOKEN}"]


def test_an_undefined_cp1252_byte_still_reports_the_token(tmp_path):
    # 0x81 is not a cp1252 character. The token is still in the file, and the file stays unread.
    repo = _repo(tmp_path)
    (repo / "latin.txt").write_bytes(b"caf\x81 " + TOKEN.encode("ascii") + b"\n")
    result = _run(repo, tmp_path)
    assert result.returncode == 2
    assert f"latin.txt:1: {TOKEN}" in result.stdout.splitlines()
    assert "latin.txt" in result.stderr


def test_text_that_starts_with_a_zip_header_is_still_scanned(tmp_path):
    # The bytes are not a zip. Opening them as one fails, so the text has to be read.
    repo = _repo(tmp_path)
    (repo / "header.txt").write_bytes(b"PK\x03\x04see " + TOKEN.encode("ascii") + b"\n")
    result = _run(repo, tmp_path)
    assert result.returncode == 1
    assert f"header.txt:1: {TOKEN}" in result.stdout.splitlines()


def test_a_token_in_a_spreadsheet_embedded_in_a_docx_is_found(tmp_path):
    repo = _repo(tmp_path)
    sheet = io.BytesIO()
    with zipfile.ZipFile(sheet, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/sharedStrings.xml", f"<t>see {TOKEN}</t>")
    outer = io.BytesIO()
    with zipfile.ZipFile(outer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "<w:t>a clean invented line</w:t>")
        archive.writestr("word/embeddings/sheet.xlsx", sheet.getvalue())
    (repo / "embed.docx").write_bytes(outer.getvalue())
    result = _run(repo, tmp_path)
    assert result.returncode != 0
    assert any(line.startswith("embed.docx!word/embeddings/sheet.xlsx!") and line.endswith(TOKEN)
               for line in result.stdout.splitlines())
