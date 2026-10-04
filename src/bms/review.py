"""The review page and the estimator's decisions (workstream 7, design §4.7)."""
from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from bms.model import Decision, Finding, Job

REVIEW_PAGE = "Review.html"
DECISIONS_FILE = "decisions.json"
MAX_QUESTIONS = 15


def review_page(job: Job, findings: Sequence[Finding], out_dir: Path) -> Path:
    """Write `out_dir/Review.html` and return its path.

    Contract: one card per system with its open questions (the findings, flagged devices — flag other than "none" —
    and assumptions), at most about MAX_QUESTIONS per job, ranked must_fix first; each count shown with every source
    and other count (and the cropped picture of what was counted when the run has one); buttons Accept / Change /
    Delete per question. One self-contained HTML file (no server, no network); its decisions save as a
    `decisions.json` the estimator puts in `out_dir` (a JSON list of `Decision.to_dict()`). No job text beyond
    what the Job and the Findings carry; the page lives under out/ (NDA), never the repo."""
    raise NotImplementedError("workstream 7: the review page")


def load_decisions(out_dir: Path) -> list[Decision]:
    """The decisions in `out_dir/decisions.json` (a JSON list of Decision dicts); [] when the file is missing.
    Raises `bms.model.ModelError` naming the entry when one is malformed."""
    raise NotImplementedError("workstream 7: the decisions")


def apply_decisions(job: Job, decisions: Sequence[Decision]) -> Job:
    """The job with the decisions applied, in order: accept clears the device's flag; delete removes the device (or
    the system, when no device or family is named); change replaces the device (same id) or the family's Count.
    A decision naming a system or device the job no longer has is skipped. Pure."""
    raise NotImplementedError("workstream 7: applying the decisions")
