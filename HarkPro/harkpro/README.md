# harkpro: the new estimating flow, beside the app

Reads the app's own outputs (Ledger.json, Job.json, Proposal.docx); never writes to `src/`.
Doctrine: `HarkPro/doctrine/lines.json` (line library) and `rulings.md` (R2-R9 are coded in `coverage.py`).

    PYTHONPATH=<worktree>/HarkPro:<worktree>/src python -m harkpro coverage LEDGER JOB --out DIR [--dismissals d.json] [--judge-answer a.json] [--strict]
    PYTHONPATH=... python -m harkpro evidence LEDGER JOB --out DIR [--debug]
    PYTHONPATH=... python -m harkpro diff OLD NEW --out DIR        # docx or Job.json each side (alias: score)

- `coverage.py`: the gate. Each controls fact must end as a printed line, exception, clarification or a dismissal
  with a reason. Writes `<job> coverage.json/.md` and, when anything is left, `<job> coverage judge request.json`
  (an AI judge hook: written, never sent; fold an answer back with `--judge-answer`).
- `evidence.py`: Summary, Scope, Questions & Flags, Sources (+ optional debug workbook with the raw ledger).
- `score.py`: run-to-run regression diff (there are no golden answer keys).
- Tests: `python -m pytest HarkPro/tests -q -p no:cacheprovider` (synthetic fixtures only).
