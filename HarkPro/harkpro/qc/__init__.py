"""HarkPro independent QC: a critic that reads the EVIDENCE LOG next to the SCOPE and argues with the writer.

The app's own QC reviews the writer's Job.json against the sources the writer cited, so it inherits the writer's
blind spots. This QC starts from the other end: every piece of evidence the app read (Ledger.json facts, the
Evidence Package's notes, schedules, plan device counts, spec lines, flags, open findings) must be accounted for in
the scope. The critic's only tools are questions and critiques; the writer answers each one with a revision, a
justification or an estimator question; the loop repeats until no open must-fix remains (or N rounds), and what is
left goes to the estimator.

Modules: `evidence` (the log + a generic concept scan), `scope` (Job.json view and revisions), `checklist` (generic
family wording checklists from lines.json; wording only), `schemas`, `handoff` (request / answer files, the app's chat form), `loop` (the
rounds), `report`, `grade` (recall against an estimator's known misses). Prompts: `HarkPro/qc_prompts/`.
"""
