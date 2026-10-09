# HarkPro independent QC: critic → writer → critic

The critic reads the **evidence log** (the app's `Ledger.json` facts and the Evidence Package's notes, schedules, plan
device counts, spec lines, flags, earlier findings and cited quotes) next to the **scope** (`Job.json`). It works
only through questions and critiques. The writer answers each one with a revision, a justification or an estimator
question. The loop repeats until no open must-fix is left (or `--rounds` is reached), and whatever is still open goes
to the estimator.

| Prompt | Step | Answer schema |
|---|---|---|
| `critic.md` | `qc_critic`: round 1 walks every evidence item (covered / dismissed / raised) and runs the method checks (every family against its `lines.json` checklist, cross-system devices, systems left out, the front end, unsupported lines, alternates). Later rounds give a verdict on every answered thread (resolved / reopen / escalate). | `harkpro.qc.schemas.CRITIC` |
| `respond.md` | `qc_respond`: the writer answers each open thread: `revise` (add / change / delete / clarify / except), `justify`, or `estimator_question`. | `harkpro.qc.schemas.RESPOND` |

Running it (no API key: each request is answered as a JSON file, the same way `tools/run_job.py` hands off the app's
requests):

```
PYTHONPATH=HarkPro .venv/bin/python -m harkpro.qc run --ledger L.json --job J.json \
    [--evidence "Evidence Package.xlsx"] --out OUT [--rounds 3] [--batch 80] [--no-screen]
# exit 2: answer each request listed under "waiting" (write its answer_file), then run again
# exit 0: OUT/QC_Report.md, findings.json (bms Finding shape, for the revise step), estimator_questions.json,
#         threads.json, coverage.json, Job.qc.json (the scope with the writer's revisions)
python -m harkpro.qc check ANSWER REQUEST      # schema check
python -m harkpro.qc evidence --ledger L.json [--evidence X.xlsx]
python -m harkpro.qc grade --out OUT --known KNOWN.json [--job ORIGINAL_JOB.json]
```

The code refuses an answer, and writes the request again with the reason as `previous_problem` (3 tries), when:
an evidence item of the part has no entry; a quote is not word for word in the cited item; a thread names a device or
block the scope does not have; a proposed template line's text is not the `lines.json` line with its placeholders
filled; a verdict is missing for an answered thread; a response is missing, or a revision does not apply.
