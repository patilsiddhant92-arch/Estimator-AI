"""Command line.

    python -m estimator build JOB.json --out FOLDER
    python -m estimator import-sent PROPOSAL.docx WORKUP.xlsx --out JOB.json
    python -m estimator price-check GENERATED.xlsx SENT.xlsx --out REPORT.md
    python -m estimator catalogue JOB_FOLDER --out FOLDER
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

from docx.opc.exceptions import PackageNotFoundError
from pydantic import ValidationError

from estimator.catalogue.job import catalogue_job, summary_lines
from estimator.evidence.workbook import write_evidence
from estimator.files import open_docx
from estimator.price_sheet.check import price_check
from estimator.price_sheet.price_book import PriceBook
from estimator.price_sheet.write import check_fit, write_price_sheet
from estimator.proposal.write import check_template, write_proposal
from estimator.scope import Job
from estimator.sent import job_from_sent

_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*]')

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

    catalogue = commands.add_parser("catalogue", help="check the job can be bid, and catalogue every page")
    catalogue.add_argument("job", type=Path)
    catalogue.add_argument("--out", type=Path, required=True)
    catalogue.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1))
    return parser


def _safe_filename(text: str) -> str:
    """A quote number used in a file name: a "/" would silently create a subfolder, and
    none of <>:"/\\|?* are allowed in a Windows file name at all."""
    return _INVALID_FILENAME_CHARS.sub("-", text)


def _build(job: Job, template: Path, workup_template: Path, book: PriceBook, out: Path) -> tuple[Path, Path]:
    """Write the proposal and the price sheet as one unit: check the job fits both templates
    before writing anything, then write both under temporary names and swap them into place
    together, so a job that doesn't fit never leaves a proposal behind with no price sheet, or a
    stale price sheet beside a freshly written proposal — and so does a destination that can't be
    replaced because it's open in Word or Excel."""
    check_template(open_docx(template))
    check_fit(job)
    out.mkdir(parents=True, exist_ok=True)
    quote = _safe_filename(job.header.quote_number)
    proposal_path, sheet_path = out / f"{quote} Proposal.docx", out / f"{quote} Price Sheet.xlsx"
    tmp_proposal, tmp_sheet = out / f".{proposal_path.name}.tmp", out / f".{sheet_path.name}.tmp"
    try:
        write_proposal(job, template, tmp_proposal)
        write_price_sheet(job, workup_template, book, tmp_sheet)
        _swap_into_place([(tmp_proposal, proposal_path), (tmp_sheet, sheet_path)])
    finally:
        tmp_proposal.unlink(missing_ok=True)
        tmp_sheet.unlink(missing_ok=True)
    return proposal_path, sheet_path


def _swap_into_place(pairs: list[tuple[Path, Path]]) -> None:
    """Replace every (new file, real destination) pair as one unit — both files or neither.

    Each existing destination is moved aside to a backup name first, so a destination that
    can't be moved (open in Word or Excel) stops everything before either file has changed.
    Only then are the new files moved into place. On any failure, the backups go back and any
    new file already placed is removed, so the folder ends up exactly as it started. Either
    way — success or failure — no backup or temp file is left in the folder."""
    backups: list[tuple[Path, Path]] = []
    placed: list[Path] = []
    try:
        for _, dest in pairs:
            if dest.exists():
                backup = dest.with_name(f".{dest.name}.bak")
                _replace(dest, backup, real=dest)
                backups.append((backup, dest))
        for tmp, dest in pairs:
            _replace(tmp, dest, real=dest)
            placed.append(dest)
    except BaseException:
        backed_up = {dest for _, dest in backups}
        for dest in placed:
            if dest not in backed_up:
                dest.unlink(missing_ok=True)
        for backup, dest in backups:
            os.replace(backup, dest)
        raise
    else:
        for backup, _ in backups:
            backup.unlink(missing_ok=True)


def _replace(src: Path, dest: Path, *, real: Path) -> None:
    """os.replace, but a failure always names `real` — the file an estimator would actually
    have open — never a hidden temp or backup name, whichever side of the move it lands on."""
    try:
        os.replace(src, dest)
    except OSError as error:
        raise PermissionError(error.errno, error.strerror, str(real)) from error


def _job_validation_message(error: ValidationError) -> str:
    """pydantic's own dump — Field required [type=missing, input_value={}, ...] For further
    information visit https://errors.pydantic.dev/... — is not something an estimator reads.
    Say instead which field, in plain words, and drop pydantic's own "Value error, " prefix."""
    errors = error.errors()
    if len(errors) == 1 and errors[0]["type"] == "json_invalid":
        match = re.search(r"line (\d+)", errors[0]["msg"])
        return f"the job file isn't valid: line {match.group(1)}" if match else "the job file isn't valid"
    lines = []
    for err in errors:
        path = " → ".join(str(step) for step in err["loc"])
        msg = err["msg"]
        if msg.startswith("Value error, "):
            msg = msg[len("Value error, "):]
        lines.append(f"{path}: {msg}" if path else msg)
    return "the job file isn't valid:\n" + "\n".join(f"    {line}" for line in lines)


def _missing_package_path(error: PackageNotFoundError) -> str:
    match = re.search(r"at '(.+)'", str(error))
    return match.group(1) if match else str(error)


def _run(args: argparse.Namespace) -> int:
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
    elif args.command == "catalogue":
        workers = max(1, min(args.workers, 61, os.cpu_count() or 1))
        result = catalogue_job(args.job, args.out / ".cache", workers)
        package = write_evidence(args.out / f"{_safe_filename(result.job.name)} Evidence Package.xlsx", result)
        for line in summary_lines(result):
            print(line)
        print(f"Wrote {package}")
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = _parser().parse_args(argv)
    try:
        return _run(args)
    except ValidationError as error:
        print(f"Stopped: {_job_validation_message(error)}", file=sys.stderr)
    except PackageNotFoundError as error:
        print(f"Stopped: can't find {_missing_package_path(error)}", file=sys.stderr)
    except FileNotFoundError as error:
        print(f"Stopped: can't find {error.filename}", file=sys.stderr)
    except PermissionError as error:
        print(f"Stopped: {error.filename} is open in Word or Excel — close it and run again", file=sys.stderr)
    except ValueError as error:
        # TemplateError, ProposalFormatError, PriceSheetError, and the price book's own
        # ValueError are all plain-words already — nothing more to translate.
        print(f"Stopped: {error}", file=sys.stderr)
    except Exception as error:  # last resort: a plain word or two, never a Python traceback
        print(f"Stopped: {error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
