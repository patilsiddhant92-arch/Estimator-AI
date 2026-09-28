"""Command line.

    python -m estimator build JOB.json --out FOLDER
    python -m estimator import-sent PROPOSAL.docx WORKUP.xlsx --out JOB.json
    python -m estimator price-check GENERATED.xlsx SENT.xlsx --out REPORT.md
    python -m estimator catalogue JOB_FOLDER --out FOLDER [--documents SUBFOLDER]
    python -m estimator estimate JOB_FOLDER --out FOLDER [--workers N] [--ai chat|api|off] [--cache FOLDER]
                                 [--method whole-job|rules] [--documents SUBFOLDER]

--documents reads only that subfolder of the job folder (such as "1. Project Documents"); the job's name still
comes from the job folder.

--ai picks who answers: "api" (Claude through the Anthropic API, the default when ANTHROPIC_API_KEY is
set), "chat" (the questions are written to a requests folder for Claude to answer in the Claude Code
chat, the default otherwise) or "off". --no-ai is the same as --ai off.

--method picks how the scope is written. "whole-job" (the default): the job's documents are gathered
into one dossier (saved beside the proposal), the AI reads it whole and plans every system, then writes
each one, and the plan and every line are checked against the counts and the house style. With the AI
off it writes the dossier and the Evidence Package only. "rules": the older path, each system written
from its Master Template entry by rules, the AI judging the lines they leave open.
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
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
from estimator.reading.job import read_job, reading_lines
from estimator.scope import Job
from estimator.sent import job_from_sent
from estimator.writing.dossier import build_dossier
from estimator.writing.assemble import (assemble_job, checklist_text, plan_checks, review_list, system_evidence,
                                        system_examples, system_pictures, tech_hour_rule, template_options)
from estimator.writing.front_end import job_header
from estimator.writing.judge import API, CHAT, KEY_VARIABLE, Judge
from estimator.writing.style import load_house_style
from estimator.writing.templates import load_templates
from estimator.writing.write import build_job

OFF = "off"
WHOLE_JOB, RULES = "whole-job", "rules"
_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*]')

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "assets"
PROPOSAL_TEMPLATE = ASSETS / "templates" / "AME_nordomatic Proposal Template.docx"
WORKUP_TEMPLATE = ASSETS / "templates" / "PriceWorkup_Template - 12-21-25.xlsx"
PRICE_BOOK = ASSETS / "price_book" / "AME Std Pricing Spreadsheet.xlsx"
ALIASES = ASSETS / "price_book" / "aliases.json"


DOCUMENTS_HELP = ('read only this subfolder of the job folder, such as "1. Project Documents" (default: the whole '
                  "job folder); the job's name still comes from the job folder")


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
    catalogue.add_argument("--documents", metavar="SUBFOLDER", help=DOCUMENTS_HELP)

    estimate = commands.add_parser("estimate", help="write the proposal, price sheet and Evidence Package "
                                                    "from a job folder")
    estimate.add_argument("job", type=Path)
    estimate.add_argument("--out", type=Path, required=True)
    estimate.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1))
    estimate.add_argument("--documents", metavar="SUBFOLDER", help=DOCUMENTS_HELP)
    ai = estimate.add_mutually_exclusive_group()
    ai.add_argument("--ai", choices=(CHAT, API, OFF),
                    help="who judges the template lines: the chat, the API, or no one "
                         "(default: api when ANTHROPIC_API_KEY is set, otherwise chat)")
    ai.add_argument("--no-ai", action="store_true", help="the same as --ai off: its lines stay PENDING")
    estimate.add_argument("--cache", type=Path, help="where to keep what was read (default: OUT/.cache)")
    estimate.add_argument("--method", choices=(WHOLE_JOB, RULES), default=WHOLE_JOB,
                          help="whole-job: the AI reads the whole job and writes every system, and the counts "
                               "check it (the default); rules: each system from its Master Template entry")
    return parser


def ai_mode(args: argparse.Namespace) -> str:
    """chat, api or off: the flag when given, else the API when a key is set, else the chat."""
    if args.no_ai:
        return OFF
    if args.ai:
        return args.ai
    return API if os.environ.get(KEY_VARIABLE) else CHAT


def _documents(args: argparse.Namespace) -> dict:
    """The --documents subfolder for catalogue_job, when one is given."""
    folder = getattr(args, "documents", None)
    return {"documents": folder} if folder else {}


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
        result = catalogue_job(args.job, args.out / ".cache", workers, **_documents(args))
        reading = read_job(result, cache_dir=args.out / ".cache")
        package = write_evidence(args.out / f"{_safe_filename(result.job.name)} Evidence Package.xlsx", result, reading)
        for line in summary_lines(result) + reading_lines(reading):
            print(line)
        print(f"Wrote {package}")
    elif args.command == "estimate":
        _estimate(args)
    return 0


def _estimate(args: argparse.Namespace) -> None:
    if getattr(args, "method", WHOLE_JOB) == RULES:
        _estimate_rules(args)
    else:
        _estimate_whole_job(args)


def _estimate_whole_job(args: argparse.Namespace) -> None:
    """The whole-job method: catalogue, read, gather the dossier, the AI plans every system and
    writes each one, the cross-checks, then the job. The dossier and the Evidence Package are
    written first, so they are there even when the AI has not answered yet."""
    workers = max(1, min(args.workers, 61, os.cpu_count() or 1))
    cache = args.cache or args.out / ".cache"
    catalogue = catalogue_job(args.job, cache, workers, **_documents(args))
    reading = read_job(catalogue, cache_dir=cache)
    today = dt.date.today()
    header, _ = job_header(catalogue, reading, today)
    quote = _safe_filename(header.quote_number)
    args.out.mkdir(parents=True, exist_ok=True)
    dossier = build_dossier(catalogue, reading, cache)
    dossier_path = args.out / f"{quote} Dossier.txt"
    dossier_path.write_text(dossier.text, encoding="utf-8")
    print(f"Wrote {dossier_path}")
    package_path = args.out / f"{quote} Evidence Package.xlsx"

    mode = ai_mode(args)
    if mode == OFF:
        package = write_evidence(package_path, catalogue, reading)
        print("AI: not used (--ai off) — the AI writes the scope; run with --ai chat or api. No proposal was written.")
        print(f"Wrote {package}")
        return
    judge = Judge(cache, mode=mode, job=dossier.job_name)
    judge.retire_requests(dossier.sources)     # this job's requests the run does not ask again end in requests/old/
    templates, style = load_templates(), load_house_style()
    plan = judge.plan_job(dossier.text, dossier.images, checklist_text(templates), style.prompt_text())
    if plan is None:
        package = write_evidence(package_path, catalogue, reading)
        for line in whole_job_lines(None, [], [], judge):
            print(line)
        print(f"Wrote {package}")
        return

    scopes = {}
    for system in plan.systems:
        if system.exception:
            continue
        pictures = system_pictures(system, dossier)      # each with its job-wide id (I15, I17)
        scopes[system.key] = judge.write_system(system, system_evidence(system, dossier),
                                                [image for _, image in pictures], template_options(system, templates),
                                                system_examples(system), style.prompt_text(),
                                                hours_rule=tech_hour_rule(system, templates),
                                                image_ids=[pid for pid, _ in pictures])
    unrecorded = getattr(judge, "unrecorded", 0)
    if unrecorded:
        print(f"Moved {unrecorded} {'request' if unrecorded == 1 else 'requests'} that recorded no job into "
              f"{judge.old_requests_dir}.")
    stale = judge.stale_requests()
    if stale:
        print(f"Moved {stale} earlier {'request' if stale == 1 else 'requests'} for this job that this run does not "
              f"ask again into {judge.old_requests_dir} (the answers are kept).")
    job, systems, review = assemble_job(catalogue, reading, dossier, plan, scopes, today, templates)
    checks, _ = plan_checks(plan, dossier, reading, catalogue)
    review = review_list(systems, review, dossier)     # every system's rows too: merged and ranked, in plain words
    systems = [dataclasses.replace(s, review=()) for s in systems]
    package = write_evidence(package_path, catalogue, reading, systems=systems, review_flags=review, plan=checks)
    for line in whole_job_lines(plan, systems, review, judge, len(catalogue.flags) + len(reading.flags)):
        print(line)
    print(f"Wrote {package}")
    if getattr(judge, "mode", API) == CHAT and judge.waiting:
        return                                   # the proposal waits for the chat's answers
    book = PriceBook.load(PRICE_BOOK, ALIASES)
    proposal, sheet = _build(job, PROPOSAL_TEMPLATE, WORKUP_TEMPLATE, book, args.out)
    print(f"Wrote {proposal}")
    print(f"Wrote {sheet}")


def whole_job_lines(plan, systems, review, judge, reading_flags: int = 0) -> list[str]:
    """The whole-job run's summary, in plain words."""
    summary = []
    if plan is not None:
        planned = list(plan.systems)
        excepted = sum(1 for s in planned if s.exception)
        written = [s for s in systems if s.bundle_key != "Front end" and s.blocks]
        pending = sum(1 for s in written for b in s.blocks if b.header.startswith("Qty (##)"))
        printed = sum(1 for s in written if s.printed)
        lines = [line for s in systems for line in s.lines]
        in_proposal = sum(1 for line in lines if line.client)
        count = sum(len(s.review) for s in systems) + len(review)
        summary.append(f"Systems planned: {len(planned)}; {printed} written in the proposal"
                       + (f", {pending} printed as Qty (##) (no quantity yet)" if pending else "")
                       + (f", {excepted} put in the exceptions" if excepted else "")
                       + (f", {len(written) - printed} left out until written" if len(written) > printed else "")
                       + ".")
        summary.append(f"Lines: {in_proposal} in the proposal; {count} {'item' if count == 1 else 'items'} on the "
                       "review list" + (f", then {reading_flags} {'flag' if reading_flags == 1 else 'flags'} from "
                                        "reading the job." if reading_flags else "."))
    if getattr(judge, "mode", API) == CHAT:
        answered = judge.answered_in_chat + judge.cached
        line = f"AI: answered in the chat {answered} {'time' if answered == 1 else 'times'}; "
        if judge.waiting:
            line += (f"{judge.waiting} {'request' if judge.waiting == 1 else 'requests'} waiting — requests in "
                     f"{judge.requests_dir}. Answer them, then run estimate again. No proposal was written yet.")
        else:
            line += "none waiting."
        summary.append(line)
    elif not judge.available and not judge.cached:
        summary.append("AI: not used — no AI key set (ANTHROPIC_API_KEY); the AI writes the scope, so no proposal "
                       "was written.")
    else:
        summary.append(f"AI: {judge.calls} {'call' if judge.calls == 1 else 'calls'} to {judge.model}, "
                       f"{judge.cached} answered from the cache at no cost.")
        if plan is None:
            summary.append(f"The AI gave no plan — {judge.last_error or 'no answer'}. No proposal was written.")
    return summary


def _estimate_rules(args: argparse.Namespace) -> None:
    """From a job folder to the draft proposal, the price sheet and the Evidence Package. The
    Evidence Package is written first, so the review list is there even when the proposal can't be."""
    workers = max(1, min(args.workers, 61, os.cpu_count() or 1))
    cache = args.cache or args.out / ".cache"
    catalogue = catalogue_job(args.job, cache, workers, **_documents(args))
    mode = ai_mode(args)
    judge = None if mode == OFF else Judge(cache, mode=mode)
    reading = read_job(catalogue, cache_dir=cache, judge=judge)   # the judge also reads schedules that are pictures
    job, systems, review_flags = build_job(catalogue, reading, judge, dt.date.today())
    args.out.mkdir(parents=True, exist_ok=True)
    package = write_evidence(args.out / f"{_safe_filename(job.header.quote_number)} Evidence Package.xlsx",
                             catalogue, reading, systems=systems, review_flags=review_flags)
    reading_flags = len(catalogue.flags) + len(reading.flags)
    for line in estimate_lines(systems, review_flags, judge, mode == OFF, reading_flags):
        print(line)
    print(f"Wrote {package}")
    book = PriceBook.load(PRICE_BOOK, ALIASES)
    proposal, sheet = _build(job, PROPOSAL_TEMPLATE, WORKUP_TEMPLATE, book, args.out)
    print(f"Wrote {proposal}")
    print(f"Wrote {sheet}")


def estimate_lines(systems, review_flags, judge, no_ai: bool, reading_flags: int = 0) -> list[str]:
    """The run's summary, in plain words."""
    written = [s for s in systems if s.bundle_key != "Front end" and s.blocks]
    excepted = [s for s in systems if s.bundle_key != "Front end" and not s.blocks]
    printed = [s for s in written if s.printed]
    lines = [line for s in systems for line in s.lines]
    in_proposal = sum(1 for line in lines if line.client)
    pending = sum(1 for line in lines if line.category == "PENDING")
    review = sum(len(s.review) for s in systems) + len(review_flags)
    held = len(written) - len(printed)
    summary = [f"Systems written: {len(printed)} in the proposal"
               + (f", {held} left out until the estimator writes {'it' if held == 1 else 'them'}" if held else "")
               + (f", {len(excepted)} put in the exceptions" if excepted else "")
               + ".",
               f"Lines: {in_proposal} in the proposal; {pending} PENDING (kept out); "
               f"{review} {'item' if review == 1 else 'items'} on the review list"
               + (f", then {reading_flags} {'flag' if reading_flags == 1 else 'flags'} from reading the job."
                  if reading_flags else ".")]
    if no_ai:
        summary.append("AI: not used (--ai off); lines it would judge are PENDING.")
    elif judge is not None and getattr(judge, "mode", API) == CHAT:
        answered = judge.answered_in_chat + judge.cached
        line = f"AI: answered in the chat for {answered} {'system' if answered == 1 else 'systems'}; "
        if judge.waiting:
            line += (f"{judge.waiting} waiting — requests in {judge.requests_dir}. "
                     "Answer them, then run estimate again.")
        else:
            line += "none waiting."
        summary.append(line)
    elif judge is not None and not judge.available and not judge.cached:
        summary.append("AI: not used — no AI key set (ANTHROPIC_API_KEY); lines it would judge are PENDING.")
    elif judge is not None:
        summary.append(f"AI: {judge.calls} {'call' if judge.calls == 1 else 'calls'} to {judge.model}, "
                       f"{judge.cached} answered from the cache at no cost.")
    return summary


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
