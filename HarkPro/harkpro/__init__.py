"""HarkPro: the new estimating flow, built beside (not inside) the existing app.

It reads the app's own outputs (Ledger.json, Job.json, Proposal.docx) and adds three things the app lacks:

- `harkpro.coverage`: the coverage gate. Every controls fact in the ledger must end as a printed line, an exception,
  a clarification or an explicit dismissal with a reason.
- `harkpro.evidence`: a 4-tab Evidence workbook (Summary, Scope, Questions & Flags, Sources).
- `harkpro.score`: the golden-job scorer (a produced proposal against the estimator's final).

The existing app (`src/bms`, `src/estimator`) is imported read-only when it is on the path; nothing here writes to it.
"""

__version__ = "0.1.0"
