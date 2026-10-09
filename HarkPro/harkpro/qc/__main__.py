"""python -m harkpro.qc ...

    run    --ledger L --job J [--evidence PACKAGE.xlsx] --out DIR [--rounds 3] [--batch 80]
           Advance the critic -> respond loop as far as the answers on disk allow. Prints a JSON block: status,
           stage, the waiting requests (file, answer_file, previous_problem) or the report files.
           Exit 2 while requests wait, 0 when done, 1 when stopped.
    check  ANSWER_FILE REQUEST_FILE      schema check of one answer (the loop also runs the semantic checks)
    evidence --ledger L [--evidence PACKAGE.xlsx]   list the evidence items the critic will walk
    grade  --out DIR --known KNOWN.json [--job ORIGINAL_JOB.json]   recall against known misses
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m harkpro.qc")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--ledger", required=True)
    r.add_argument("--job", required=True)
    r.add_argument("--evidence")
    r.add_argument("--out", required=True)
    r.add_argument("--rounds", type=int, default=3)
    r.add_argument("--batch", type=int, default=80)
    r.add_argument("--no-screen", action="store_true", help="walk every item, even those with no controls word")
    c = sub.add_parser("check")
    c.add_argument("answer")
    c.add_argument("request")
    e = sub.add_parser("evidence")
    e.add_argument("--ledger", required=True)
    e.add_argument("--evidence")
    g = sub.add_parser("grade")
    g.add_argument("--out", required=True)
    g.add_argument("--known", required=True)
    g.add_argument("--job")
    a = p.parse_args(argv)

    if a.cmd == "run":
        from .loop import run
        ledger = json.loads(Path(a.ledger).read_text(encoding="utf-8"))
        job = json.loads(Path(a.job).read_text(encoding="utf-8"))
        res = run(ledger, job, a.out, a.evidence, a.rounds, a.batch, screen_on=not a.no_screen)
        block = {"status": res.status, "stage": res.stage, "message": res.message, "waiting": res.waiting,
                 "files": res.files, "exit": res.exit_code}
        if res.state is not None:
            block["threads"] = len(res.state.threads)
            block["open_must_fix"] = len(res.state.open("must_fix"))
        print(json.dumps(block, indent=1))
        return res.exit_code
    if a.cmd == "check":
        from .handoff import check_file
        errors = check_file(a.answer, a.request)
        print("OK" if not errors else "\n".join(errors))
        return 0 if not errors else 1
    if a.cmd == "evidence":
        from .evidence import load_evidence
        ledger = json.loads(Path(a.ledger).read_text(encoding="utf-8"))
        for i in load_evidence(ledger, a.evidence):
            print(f"{i.id} [{i.kind}] {i.text[:160]}  <{','.join(i.concepts)}>")
        return 0
    if a.cmd == "grade":
        from .grade import grade_folder
        print(json.dumps(grade_folder(a.out, a.known, a.job), indent=1, ensure_ascii=False))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
