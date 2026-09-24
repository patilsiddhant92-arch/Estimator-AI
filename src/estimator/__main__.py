"""Command line.

    python -m estimator build JOB.json --out FOLDER
    python -m estimator import-sent PROPOSAL.docx WORKUP.xlsx --out JOB.json
    python -m estimator price-check GENERATED.xlsx SENT.xlsx --out REPORT.md
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import docx

from estimator.price_sheet.check import price_check
from estimator.price_sheet.price_book import PriceBook
from estimator.price_sheet.write import check_fit, write_price_sheet
from estimator.proposal.write import check_template, write_proposal
from estimator.scope import Job
from estimator.sent import job_from_sent

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "assets"
PROPOSAL_TEMPLATE = ASSETS / "templates" / "AME_nordomatic Proposal Template.docx"
WORKUP_TEMPLATE = ASSETS / "templates" / "PriceWorkup_Template - 12-21-25.xlsx"
PRICE_BOOK = ASSETS / "price_book" / "AME Std Pricing Spreadsheet.xlsx"
ALIASES = ASSETS / "price_book" / "aliases.json"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="estimator")
    commands = parser.add_subparsers(dest="command", required=True)

    build = commands.add_parser("build", help="write the proposal and price sheet for a job")
    build.add_argument("job", type=Path)
    build.add_argument("--out", type=Path, required=True)
    build.add_argument("--template", type=Path, default=PROPOSAL_TEMPLATE)
    build.add_argument("--workup-template", type=Path, default=WORKUP_TEMPLATE)

    importer = commands.add_parser("import-sent", help="turn a sent proposal and its workup into a job file")
    importer.add_argument("proposal", type=Path)
    importer.add_argument("workup", type=Path)
    importer.add_argument("--out", type=Path, required=True)
    importer.add_argument("--template", type=Path, default=PROPOSAL_TEMPLATE)

    check = commands.add_parser("price-check", help="compare a generated price sheet with the workup that was sent")
    check.add_argument("generated", type=Path)
    check.add_argument("sent", type=Path)
    check.add_argument("--out", type=Path, required=True)
    return parser


def _build(job: Job, template: Path, workup_template: Path, book: PriceBook, out: Path) -> tuple[Path, Path]:
    """Write the proposal and the price sheet as one unit: check the job fits both templates
    before writing anything, then write both under temporary names and rename them into place
    together, so a job that doesn't fit never leaves a proposal behind with no price sheet, or a
    stale price sheet beside a freshly written proposal."""
    check_template(docx.Document(str(template)))
    check_fit(job)
    out.mkdir(parents=True, exist_ok=True)
    quote = job.header.quote_number
    proposal_path, sheet_path = out / f"{quote} Proposal.docx", out / f"{quote} Price Sheet.xlsx"
    tmp_proposal, tmp_sheet = out / f".{proposal_path.name}.tmp", out / f".{sheet_path.name}.tmp"
    try:
        write_proposal(job, template, tmp_proposal)
        write_price_sheet(job, workup_template, book, tmp_sheet)
        os.replace(tmp_proposal, proposal_path)
        os.replace(tmp_sheet, sheet_path)
    finally:
        tmp_proposal.unlink(missing_ok=True)
        tmp_sheet.unlink(missing_ok=True)
    return proposal_path, sheet_path


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = _parser().parse_args(argv)
    if args.command == "build":
        job = Job.model_validate_json(args.job.read_text(encoding="utf-8"))
        book = PriceBook.load(PRICE_BOOK, ALIASES)
        proposal, sheet = _build(job, args.template, args.workup_template, book, args.out)
        print(f"Wrote {proposal}")
        print(f"Wrote {sheet}")
    elif args.command == "import-sent":
        job, report = job_from_sent(args.proposal, args.workup, args.template)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(job.model_dump_json(indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {args.out} — {report.matched} lines matched between the proposal and the workup.")
        if report.unmatched_ours:
            print("In the proposal but not the workup, so no hours or quantity were taken:")
            for text in report.unmatched_ours:
                print(f"    {text}")
        if report.unmatched_theirs:
            print("In the workup but not the proposal, so ignored:")
            for text in report.unmatched_theirs:
                print(f"    {text}")
        if report.ignored:
            print("On a matched line, but with nowhere in the job to go, so ignored:")
            for text in report.ignored:
                print(f"    {text}")
    elif args.command == "price-check":
        book = PriceBook.load(PRICE_BOOK, ALIASES)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(price_check(args.generated, args.sent, book, args.generated.stem), encoding="utf-8")
        print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
