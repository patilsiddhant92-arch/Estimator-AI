"""Catalogue the Learn jobs and compare each with what the estimator concluded.

    .venv/Scripts/python.exe tools/learn_check.py [--jobs 26-0246 26-0352] [--workers 4]

Reads the Learn folder (read-only) and writes only under out/learn/. Exits 1 if any job
misses its expectation in tests/data/learn_expectations.json.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTATIONS = ROOT / "tests" / "data" / "learn_expectations.json"
OUT = ROOT / "out" / "learn"


@dataclass(frozen=True)
class JobResult:
    job: str
    pages: int
    ocr: int
    unreadable: int
    sheets: int
    numbered: int
    relevant: int          # sheets in the disciplines that carry controls scope (CONTROLS_DISCIPLINES)
    typed: int             # of those, how many were sorted by type
    controls_sections: int
    bid: str
    others: tuple[str, ...]
    tags: int


def measure(catalogue) -> JobResult:
    from estimator.catalogue.job import CONTROLS_DISCIPLINES
    pages, sheets = catalogue.pages, catalogue.sheets
    relevant = [s for s in sheets if s.discipline in CONTROLS_DISCIPLINES]
    return JobResult(
        job=catalogue.job.name, pages=len(pages),
        ocr=sum(1 for p in pages if p.status == "ocr"), unreadable=sum(1 for p in pages if p.status == "unreadable"),
        sheets=len(sheets), numbered=sum(1 for s in sheets if s.number),
        relevant=len(relevant), typed=sum(1 for s in relevant if s.types),
        controls_sections=sum(1 for s in catalogue.sections if s.controls),
        bid=catalogue.bid.finding, others=catalogue.bid.others, tags=len(catalogue.tags))


def misses(result: JobResult, expected: dict) -> list[str]:
    found = []
    if expected["bid"] is not None and result.bid != expected["bid"]:
        found.append(f"bid check said {result.bid}, the estimator concluded {expected['bid']}")
    if result.sheets:
        share = result.numbered / result.sheets
        if share < expected["sheet_numbers_at_least"]:
            found.append(f"sheet numbers found on {share:.0%} of drawing sheets, "
                         f"expected at least {expected['sheet_numbers_at_least']:.0%}")
    if result.relevant:
        typed = result.typed / result.relevant
        if typed < expected["typed_at_least"]:
            found.append(f"sorted by type on {typed:.0%} of mechanical, controls and plumbing sheets, "
                         f"expected at least {expected['typed_at_least']:.0%}")
    if expected["controls_sections"] and not result.controls_sections:
        found.append("no controls section found, and the job has one")
    if not expected["controls_sections"] and result.controls_sections:
        found.append(f"{result.controls_sections} controls sections found, and the job has none")
    return found


def find_job(learn: Path, key: str) -> Path:
    """The job's folder: a folder whose name starts with the job number, at any depth up to four."""
    for depth in range(1, 5):
        for folder in sorted(learn.glob("/".join(["*"] * depth))):
            if folder.is_dir() and folder.name.split(",")[0].strip() == key:
                return folder
    raise FileNotFoundError(2, "No such job folder", str(learn / key))


def main(argv: list[str] | None = None) -> int:
    from estimator.catalogue.job import catalogue_job, summary_lines
    from estimator.catalogue.tags import Equipment, unlisted_prefixes
    from estimator.evidence.workbook import write_evidence

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", nargs="*")
    parser.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1))
    args = parser.parse_args(argv)
    expectations = json.loads(EXPECTATIONS.read_text(encoding="utf-8"))
    learn = Path(expectations["learn_folder"])
    keys = args.jobs or list(expectations["jobs"])
    lines = ["| Job | Pages | OCR | Could not read | Drawing sheets | With number | Mech/controls/plumbing sorted by type | Controls sections "
             "| Bid check | Other manufacturers | Tags | Misses |", "|" + "---|" * 12]
    total_misses, unlisted = 0, {}
    equipment = Equipment.load()
    for key in keys:
        folder = find_job(learn, key)
        print(f"Cataloguing {key} …", flush=True)
        catalogue = catalogue_job(folder, OUT / ".cache", args.workers)
        write_evidence(OUT / key / f"{key} Evidence Package.xlsx", catalogue)
        for line in summary_lines(catalogue):
            print("   " + line)
        result = measure(catalogue)
        found = misses(result, expectations["jobs"][key])
        total_misses += len(found)
        for prefix, n in unlisted_prefixes((p.text for p in catalogue.pages), equipment).items():
            unlisted[prefix] = unlisted.get(prefix, 0) + n
        share = lambda n, of: f"{n} of {of} ({n / of:.0%})" if of else "—"
        lines.append(f"| {key} | {result.pages} | {result.ocr} | {result.unreadable} | {result.sheets} "
                     f"| {share(result.numbered, result.sheets)} | {share(result.typed, result.relevant)} "
                     f"| {result.controls_sections} | {result.bid} | {', '.join(result.others) or '—'} "
                     f"| {result.tags} | {'; '.join(found) or 'none'} |")
    common = sorted(unlisted.items(), key=lambda kv: -kv[1])[:25]
    lines += ["", "Tag-shaped codes whose prefix isn't in assets/reading_lists/equipment.json yet (most common first):",
              ", ".join(f"{p} ×{n}" for p, n in common) or "none"]
    report = "\n".join(lines) + "\n"
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "learn-check.md").write_text(report, encoding="utf-8")
    print(report)
    return 1 if total_misses else 0


if __name__ == "__main__":
    sys.exit(main())
