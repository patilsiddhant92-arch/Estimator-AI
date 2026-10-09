"""python -m harkpro coverage|evidence|score ...

    python -m harkpro coverage LEDGER.json JOB.json --out DIR [--lines lines.json] [--dismissals d.json]
                                                     [--judge-answer a.json] [--strict]
    python -m harkpro evidence LEDGER.json JOB.json --out DIR [--debug] [--lines ...] [--dismissals ...]
    python -m harkpro diff OLD(.docx|Job.json) NEW(.docx|Job.json) --out DIR [--name NAME]   (alias: score)

Run with PYTHONPATH=<worktree>/HarkPro (and <worktree>/src for the app's renderer and price book; the CLI adds the
worktree's src/ itself when it can find it). Outputs go only to --out.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

APP_SRC = Path(__file__).resolve().parents[2] / "src"


def _app_on_path() -> None:
    try:
        import bms  # noqa: F401
    except ImportError:
        if APP_SRC.is_dir():
            sys.path.append(str(APP_SRC))


def main(argv: list[str] | None = None) -> int:
    _app_on_path()
    p = argparse.ArgumentParser(prog="harkpro", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("coverage", help="the coverage gate")
    c.add_argument("ledger")
    c.add_argument("job")
    c.add_argument("--out", required=True)
    c.add_argument("--lines")
    c.add_argument("--dismissals")
    c.add_argument("--judge-answer")
    c.add_argument("--strict", action="store_true", help="exit 2 when the gate fails")

    e = sub.add_parser("evidence", help="the 4-tab Evidence workbook")
    e.add_argument("ledger")
    e.add_argument("job")
    e.add_argument("--out", required=True)
    e.add_argument("--lines")
    e.add_argument("--dismissals")
    e.add_argument("--debug", action="store_true", help="also write the raw-ledger debug workbook")

    s = sub.add_parser("diff", aliases=["score"], help="run-to-run regression diff of two proposals")
    s.add_argument("old")
    s.add_argument("new")
    s.add_argument("--out", required=True)
    s.add_argument("--name", default="")

    args = p.parse_args(argv)
    if args.command == "coverage":
        from . import coverage
        r = coverage.run(args.ledger, args.job, args.out, args.lines, args.dismissals, args.judge_answer)
        sm = r.summary()
        print(f"coverage {'PASS' if r.passed else 'FAIL'}: {sm['relevant_facts']} facts, {sm['accounted']} accounted, "
              f"{sm['dismissed']} dismissed, {sm['partial'] + sm['unaccounted']} open ({sm['must_fix']} must fix), "
              f"{sm['count_gaps']} count gaps -> {args.out}")
        return 2 if args.strict and not r.passed else 0
    if args.command == "evidence":
        from . import appio, coverage, evidence
        from .doctrine import load_lines
        ledger, job = appio.load_json(args.ledger), appio.load_json(args.job)
        printed = appio.printed_texts(job)
        result = coverage.check(ledger, job, load_lines(args.lines), coverage.load_dismissals(args.dismissals),
                                printed)
        name = job.get("name") or "job"
        paths = [evidence.write(Path(args.out) / f"{name} Evidence (HarkPro).xlsx", job, ledger, result, printed,
                                notes=appio.printed_notes(job))]
        if args.debug:
            paths.append(evidence.write_debug(Path(args.out) / f"{name} Evidence debug (HarkPro).xlsx", job, ledger,
                                              result))
        for path in paths:
            print(f"wrote {path}")
        return 0
    if args.command in ("diff", "score"):
        from . import score
        r = score.run(args.old, args.new, args.out, args.name)
        t = r.totals
        print("diff: no change in scope" if r.unchanged else
              f"diff: blocks +{t['blocks_added']} -{t['blocks_removed']} ~{t['blocks_changed']}; lines "
              f"+{t['lines_added']} -{t['lines_removed']} ~{t['lines_changed']} -> {args.out}")
        return 0
    return 1
