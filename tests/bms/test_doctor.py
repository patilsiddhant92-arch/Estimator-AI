"""Tests for `bms doctor`: diagnosing Python version, dependencies, model configuration,
Playbook rules and citations, cache directory writability, and plain-language CLI output."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from bms import doctor
from bms.doctor import (
    CheckResult,
    check_cache_folder,
    check_config,
    check_dependencies,
    check_playbook,
    check_python,
    run_doctor,
)
from bms.__main__ import main, parser


ROOT = Path(__file__).resolve().parents[2]


# ---- Python version check -----------------------------------------------------------------------------------------

def test_check_python_succeeds_on_current_runtime():
    res = check_python()
    assert res.ok
    assert "Python" in res.message
    assert res.name == "Python"


def test_check_python_fails_when_below_minimum_version():
    res = check_python(min_version=(3, 99))
    assert not res.ok
    assert "older than required" in res.message


# ---- Dependency check ----------------------------------------------------------------------------------------------

def test_check_dependencies_finds_all_required_packages():
    res = check_dependencies()
    assert res.ok
    assert "pydantic" in res.message
    assert "openpyxl" in res.message
    assert "docx" in res.message


def test_check_dependencies_reports_missing_packages():
    res = check_dependencies(required=["nonexistent_pkg_foo_bar_123"])
    assert not res.ok
    assert "nonexistent_pkg_foo_bar_123" in res.message
    assert "Missing dependencies" in res.message


# ---- Configuration check (.claude/run-job.json) -------------------------------------------------------------------

def test_check_config_succeeds_with_valid_config(tmp_path):
    cfg_file = tmp_path / "run-job.json"
    cfg_file.write_text(json.dumps({
        "judge_model": "opus",
        "writer_model": "opus",
        "qc_model": "opus",
        "count_model": "sonnet",
        "max_attempts": 3,
    }), encoding="utf-8")
    res = check_config(cfg_file)
    assert res.ok
    assert "valid" in res.message.lower()


def test_check_config_fails_when_file_missing(tmp_path):
    missing_file = tmp_path / "nonexistent.json"
    res = check_config(missing_file)
    assert not res.ok
    assert "not found" in res.message


def test_check_config_fails_on_invalid_json(tmp_path):
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("{not-valid-json", encoding="utf-8")
    res = check_config(bad_file)
    assert not res.ok
    assert "not valid JSON" in res.message


def test_check_config_fails_when_model_key_missing(tmp_path):
    cfg_file = tmp_path / "run-job.json"
    cfg_file.write_text(json.dumps({
        "judge_model": "opus",
        "writer_model": "opus",
        # missing qc_model and count_model
    }), encoding="utf-8")
    res = check_config(cfg_file)
    assert not res.ok
    assert "missing required keys" in res.message.lower()
    assert "qc_model" in res.detail


def test_a_blank_model_name_is_rejected(tmp_path):
    cfg_file = tmp_path / "run-job.json"
    cfg_file.write_text(json.dumps({
        "judge_model": " ",
        "writer_model": "opus",
        "qc_model": "opus",
        "count_model": "sonnet",
    }), encoding="utf-8")
    res = check_config(cfg_file)
    assert not res.ok
    assert "judge_model" in res.message


def test_check_config_fails_when_max_attempts_invalid(tmp_path):
    cfg_file = tmp_path / "run-job.json"
    cfg_file.write_text(json.dumps({
        "judge_model": "opus",
        "writer_model": "opus",
        "qc_model": "opus",
        "count_model": "sonnet",
        "max_attempts": 0,
    }), encoding="utf-8")
    res = check_config(cfg_file)
    assert not res.ok
    assert "max_attempts" in res.message


def test_check_config_fails_when_max_attempts_is_bool(tmp_path):
    for val in (True, False):
        cfg_file = tmp_path / f"run-job_{val}.json"
        cfg_file.write_text(json.dumps({
            "judge_model": "opus",
            "writer_model": "opus",
            "qc_model": "opus",
            "count_model": "sonnet",
            "max_attempts": val,
        }), encoding="utf-8")
        res = check_config(cfg_file)
        assert not res.ok
        assert "max_attempts" in res.message


def test_check_config_succeeds_from_arbitrary_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    res = check_config()
    assert res.ok
    assert "valid" in res.message.lower()


# ---- Playbook & rule names check ----------------------------------------------------------------------------------

def test_check_playbook_succeeds_on_repo_playbook():
    res = check_playbook()
    assert res.ok
    assert "Playbook" in res.name
    assert "rules" in res.message


def test_check_playbook_fails_when_directory_missing(tmp_path):
    missing_dir = tmp_path / "missing_playbook"
    res = check_playbook(playbook_dir=missing_dir)
    assert not res.ok
    assert "cannot be loaded" in res.message or "not found" in res.message


def test_check_playbook_catches_missing_rules_against_prompts(tmp_path):
    sample = ROOT / "tests" / "bms" / "fixtures" / "sample_playbook"
    import shutil
    shutil.copytree(sample, tmp_path / "playbook")
    # Sample playbook lacks full repo rules: check_playbook should report missing rules vs validators/prompts
    res = check_playbook(playbook_dir=tmp_path / "playbook")
    assert not res.ok
    assert "missing" in res.message.lower()


def test_check_playbook_ignores_arbitrary_quotes_in_prompts(tmp_path):
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "custom.md").write_text('Some instruction saying "Hello There" and "General Kenobi".', encoding="utf-8")
    res = check_playbook(prompts_dir=prompts_dir)
    assert res.ok
    assert "Hello There" not in res.message


def test_check_playbook_catches_explicitly_cited_missing_rule(tmp_path):
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "custom.md").write_text('This breaks "Nonexistent Imaginary Rule Name".', encoding="utf-8")
    res = check_playbook(prompts_dir=prompts_dir)
    assert not res.ok
    assert "Nonexistent Imaginary Rule Name" in res.message


# ---- Cache folder writability check -------------------------------------------------------------------------------

def test_check_cache_folder_succeeds_on_writable_folder(tmp_path):
    cache = tmp_path / "cache"
    res = check_cache_folder(cache)
    assert res.ok
    assert "writable" in res.message.lower()


def test_check_cache_folder_fails_when_unwritable():
    with patch("pathlib.Path.mkdir", side_effect=OSError("Permission denied")):
        res = check_cache_folder(Path("/unwritable_dummy_cache"))
        assert not res.ok
        assert "not writable" in res.message.lower()


def test_check_cache_folder_cleans_up_new_directory(tmp_path):
    cache = tmp_path / "sub" / "new_cache"
    assert not cache.exists()
    res = check_cache_folder(cache)
    assert res.ok
    assert not cache.exists()


def test_check_cache_folder_preserves_existing_directory(tmp_path):
    cache = tmp_path / "existing_cache"
    cache.mkdir()
    res = check_cache_folder(cache)
    assert res.ok
    assert cache.exists()


def test_check_cache_folder_leaves_no_stray_cache_in_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    res = check_cache_folder()
    assert res.ok
    assert not (tmp_path / ".cache").exists()


# ---- Overall run_doctor & CLI --------------------------------------------------------------------------------------

def test_run_doctor_plain_language_output():
    ok, lines = run_doctor()
    assert ok
    text = "\n".join(lines)
    assert "[OK] Python:" in text
    assert "[OK] Dependencies:" in text
    assert "[OK] Configuration:" in text
    assert "[OK] Playbook & Rules:" in text
    assert "[OK] Cache Folder:" in text
    assert "All checks passed" in text


def test_cli_parser_has_doctor_command():
    p = parser()
    args = p.parse_args(["doctor", "--cache", ".test_cache"])
    assert args.command == "doctor"
    assert args.cache == Path(".test_cache")


def test_cli_main_doctor(capsys):
    exit_code = main(["doctor"])
    captured = capsys.readouterr().out
    assert exit_code == 0
    assert "BMS Doctor" in captured
    assert "All checks passed" in captured
