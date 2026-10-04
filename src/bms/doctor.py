"""Diagnostic health checks for the BMS estimating system (`python -m bms doctor`).

Checks:
1. Python version (minimum 3.10+).
2. Required third-party dependencies.
3. Model configuration in `.claude/run-job.json`.
4. Playbook loading and rule name citations against validators and prompts.
5. Cache directory writability.
"""
from __future__ import annotations

import importlib
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from bms.playbook import Playbook, PlaybookError, load_playbook
from bms.validate import RULE


REQUIRED_PACKAGES: list[tuple[str, str]] = [
    ("pydantic", "pydantic"),
    ("docx", "python-docx"),
    ("openpyxl", "openpyxl"),
    ("PIL", "pillow"),
    ("lxml", "lxml"),
    ("pymupdf", "pymupdf"),
    ("anthropic", "anthropic"),
]

REQUIRED_CONFIG_KEYS = ["judge_model", "writer_model", "qc_model", "count_model"]


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    message: str
    detail: str = ""


def check_python(min_version: tuple[int, int] = (3, 10)) -> CheckResult:
    """Check that Python meets the minimum version requirement."""
    version = sys.version_info[:2]
    ver_str = ".".join(map(str, sys.version_info[:3]))
    exec_path = sys.executable
    min_str = ".".join(map(str, min_version))
    if version < min_version:
        return CheckResult(
            name="Python",
            ok=False,
            message=f"Python version {ver_str} at {exec_path} is older than required {min_str}+",
            detail=f"Please run using Python {min_str} or newer (project .venv).",
        )
    return CheckResult(
        name="Python",
        ok=True,
        message=f"Python {ver_str} at {exec_path}",
    )


def check_dependencies(required: Sequence[str] | None = None) -> CheckResult:
    """Check that required third-party packages can be imported."""
    modules_to_check: list[tuple[str, str]]
    if required is None:
        modules_to_check = REQUIRED_PACKAGES
    else:
        modules_to_check = [(pkg, pkg) for pkg in required]

    missing: list[str] = []
    installed: list[str] = []

    for mod_name, disp_name in modules_to_check:
        try:
            mod = importlib.import_module(mod_name)
            version = getattr(mod, "__version__", None)
            ver_text = f" {version}" if version else ""
            installed.append(f"{disp_name}{ver_text}")
        except ImportError:
            missing.append(disp_name)

    if missing:
        return CheckResult(
            name="Dependencies",
            ok=False,
            message=f"Missing dependencies: {', '.join(missing)}",
            detail="Install missing dependencies with: pip install -e .",
        )
    return CheckResult(
        name="Dependencies",
        ok=True,
        message=f"All {len(installed)} required packages installed ({', '.join(installed)})",
    )


def check_config(config_path: Path | None = None) -> CheckResult:
    """Check that .claude/run-job.json exists and defines valid models."""
    path = Path(config_path or Path(".claude") / "run-job.json")
    if not path.is_file():
        return CheckResult(
            name="Configuration",
            ok=False,
            message=f"Configuration file not found: {path}",
            detail="Create .claude/run-job.json with judge_model, writer_model, qc_model, count_model.",
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        return CheckResult(
            name="Configuration",
            ok=False,
            message=f"Configuration file {path} is not valid JSON: {err}",
        )
    if not isinstance(data, dict):
        return CheckResult(
            name="Configuration",
            ok=False,
            message=f"Configuration file {path} must contain a JSON object",
        )

    missing = [k for k in REQUIRED_CONFIG_KEYS if not isinstance(data.get(k), str) or not data.get(k, "").strip()]
    if missing:
        return CheckResult(
            name="Configuration",
            ok=False,
            message=f"Configuration file {path} missing required keys: {', '.join(missing)}",
            detail=f"Required string keys: {', '.join(REQUIRED_CONFIG_KEYS)}",
        )

    max_attempts = data.get("max_attempts")
    if max_attempts is not None:
        if not isinstance(max_attempts, int) or max_attempts < 1:
            return CheckResult(
                name="Configuration",
                ok=False,
                message=f"Configuration 'max_attempts' must be an integer >= 1 (got {max_attempts!r})",
            )

    models_desc = ", ".join(f"{k.replace('_model', '')}: {data[k]}" for k in REQUIRED_CONFIG_KEYS)
    if max_attempts is not None:
        models_desc += f", max_attempts: {max_attempts}"
    return CheckResult(
        name="Configuration",
        ok=True,
        message=f"Valid model configuration at {path} ({models_desc})",
    )


def check_playbook(playbook_dir: Path | None = None, prompts_dir: Path | None = None) -> CheckResult:
    """Check that the Playbook loads and that all rule names cited by validators and prompts exist."""
    try:
        playbook: Playbook = load_playbook(playbook_dir) if playbook_dir is not None else load_playbook()
    except (PlaybookError, OSError, ValueError) as err:
        return CheckResult(
            name="Playbook & Rules",
            ok=False,
            message=f"Playbook cannot be loaded: {err}",
        )

    # Check validator rule names
    missing_validator = sorted(name for name in RULE.values() if name not in playbook.rules)
    if missing_validator:
        return CheckResult(
            name="Playbook & Rules",
            ok=False,
            message=f"Playbook missing {len(missing_validator)} rule(s) cited by validators: {', '.join(missing_validator)}",
        )

    # Check prompt rule names
    prompts_path = Path(prompts_dir or Path(__file__).resolve().parent / "prompts")
    quoted_citations: set[str] = set()
    if prompts_path.is_dir():
        for prompt_file in prompts_path.glob("*.md"):
            try:
                content = prompt_file.read_text(encoding="utf-8")
                quoted_citations |= {
                    q for q in re.findall(r'"([^"\n]+)"', content)
                    if q[:1].isupper() and " " in q
                }
            except OSError:
                pass

    missing_prompt = sorted(q for q in quoted_citations if q not in playbook.rules)
    if missing_prompt:
        return CheckResult(
            name="Playbook & Rules",
            ok=False,
            message=f"Playbook missing {len(missing_prompt)} rule(s) cited in prompts: {', '.join(missing_prompt)}",
        )

    num_shapes = len(playbook.shapes)
    num_rules = len(playbook.rules)
    return CheckResult(
        name="Playbook & Rules",
        ok=True,
        message=f"Loaded {num_shapes} shapes and {num_rules} rules; all validator and prompt rule citations exist",
    )


def check_cache_folder(cache_dir: Path | None = None) -> CheckResult:
    """Check that the cache directory can be created and is writable."""
    target = Path(cache_dir or Path(".cache"))
    try:
        target.mkdir(parents=True, exist_ok=True)
        probe = target / f".probe_doctor_{os.getpid()}"
        probe.write_text("doctor-ok", encoding="utf-8")
        read_back = probe.read_text(encoding="utf-8")
        probe.unlink(missing_ok=True)
        if read_back != "doctor-ok":
            return CheckResult(
                name="Cache Folder",
                ok=False,
                message=f"Cache directory {target} read-write verification failed",
            )
    except OSError as err:
        return CheckResult(
            name="Cache Folder",
            ok=False,
            message=f"Cache directory {target} is not writable: {err}",
            detail=f"Ensure write permissions for {target.resolve()}.",
        )
    return CheckResult(
        name="Cache Folder",
        ok=True,
        message=f"Cache folder {target} is writable",
    )


def run_doctor(cache_dir: Path | None = None, playbook_dir: Path | None = None,
               config_path: Path | None = None, prompts_dir: Path | None = None) -> tuple[bool, list[str]]:
    """Execute all diagnostic checks and return (all_passed, formatted_lines)."""
    checks = [
        check_python(),
        check_dependencies(),
        check_config(config_path),
        check_playbook(playbook_dir, prompts_dir),
        check_cache_folder(cache_dir),
    ]

    all_ok = all(c.ok for c in checks)
    lines: list[str] = [
        "BMS Doctor",
        "==========",
    ]

    for c in checks:
        prefix = "[OK]" if c.ok else "[FAIL]"
        lines.append(f"{prefix} {c.name}: {c.message}")
        if not c.ok and c.detail:
            lines.append(f"       -> {c.detail}")

    lines.append("")
    if all_ok:
        lines.append("All checks passed. System is ready.")
    else:
        fails = sum(1 for c in checks if not c.ok)
        lines.append(f"Diagnostic failed with {fails} issue(s).")

    return all_ok, lines
