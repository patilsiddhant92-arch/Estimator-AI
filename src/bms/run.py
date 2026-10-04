"""The rebuilt estimate, in its final order (design §5 "Integration"):

read (the old app's staged reading) -> plan_job -> counts cross-check -> write_system per system -> the estimator's
decisions -> validate -> qc_job -> revise_system (must_fix only, one round) -> validate -> review_page -> render ->
the Word proposal, the price sheet and the Evidence Package.

In chat mode a step with no answer yet writes its request and the run stops after the step has asked every question
it can (all systems are asked before stopping); the next run picks the answers up. Every output goes under `out`
(NDA: never the repo). Prints "Wrote <path>" per file, as the old app does (tools/run_job.py reads those lines).
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from estimator.__main__ import (ALIASES, PRICE_BOOK, PROPOSAL_TEMPLATE, WORKUP_TEMPLATE, _build,
                                _safe_filename)
from estimator.catalogue.job import catalogue_job
from estimator.evidence.workbook import write_evidence
from estimator.ledger.run import read_job as read_ledger
from estimator.price_sheet.price_book import PriceBook
from estimator.reading.job import read_job
from estimator.writing.dossier import build_dossier
from estimator.writing.front_end import job_header
from estimator.writing.judge import Judge

from bms import ai
from bms.counts import cross_check
from bms.model import Finding, Header, Job
from bms.plan import plan_job
from bms.playbook import load_playbook
from bms.render import render
from bms.review import apply_decisions, load_decisions, review_page
from bms.validate import validate

Mode = Literal["chat", "api"]
MODES = ("chat", "api")
Status = Literal["waiting", "done"]


@dataclass(frozen=True)
class RunResult:
    """What one run did. `status` "waiting": chat requests wait for answers (`waiting` of them, at `stage`);
    "done": the proposal, price sheet and Evidence Package are written."""
    status: Status
    stage: str                              # the last step reached: "read", "write", "qc", "revise", "done"
    waiting: int = 0
    job_file: Path | None = None            # out/<quote> Job.json: the Job model as last saved
    findings: tuple[Finding, ...] = ()      # the final validate's findings plus the QC findings left open
    review: Path | None = None              # out/Review.html
    proposal: Path | None = None
    price_sheet: Path | None = None
    evidence: Path | None = None
    messages: tuple[str, ...] = ()          # plain lines for the console


def _workers() -> int:
    return max(1, min(4, os.cpu_count() or 1))


def estimate(job_folder: Path, out: Path, cache: Path, mode: Mode = "chat") -> RunResult:
    """Run the rebuilt estimate on one job folder. `cache` is where reading is kept and where the chat requests go
    (`cache/judge-chat`); `mode` "chat" or "api" for every AI question (the reading passes too)."""
    if mode not in MODES:
        raise ValueError(f"the mode must be chat or api, not {mode!r}")
    job_folder, out, cache = Path(job_folder), Path(out), Path(cache)
    out.mkdir(parents=True, exist_ok=True)

    # 1. read: catalogue, reading, dossier, the ledger's staged passes (old app, unchanged)
    catalogue = catalogue_job(job_folder, cache, _workers())
    reading = read_job(catalogue, cache_dir=cache)
    old_header, _ = job_header(catalogue, reading, dt.date.today())
    quote = _safe_filename(old_header.quote_number)
    dossier = build_dossier(catalogue, reading, cache)
    judge = Judge(cache, mode=mode, job=dossier.job_name)
    judge.retire_requests(dossier.sources)
    ledger_file = out / f"{quote} Ledger.json"
    ledger = read_ledger(judge, dossier, catalogue, save_to=ledger_file)
    print(f"Wrote {ledger_file}")
    if not ledger.complete:
        return RunResult("waiting", "read", waiting=judge.waiting,
                         messages=(f"Reading stopped at the {ledger.stopped_at} pass: waiting for its answer.",))

    # 2. plan, then the counts cross-check
    playbook = load_playbook()
    job = plan_job(ledger, catalogue, dossier, playbook)
    job = dataclasses.replace(job, header=Header(
        quote_number=old_header.quote_number, reference=old_header.reference, mep_engineer=old_header.mep_engineer,
        based_on=tuple(old_header.based_on), date=old_header.date.isoformat(), to=old_header.to))
    job = cross_check(job, catalogue, cache)
    job_file = out / f"{quote} Job.json"

    def save(current: Job) -> None:
        job_file.write_text(current.to_json(), encoding="utf-8")

    # 3. write every system (all are asked before stopping for answers)
    transport = (ai.ChatTransport(cache, job=dossier.job_name) if mode == "chat" else ai.ApiTransport(cache))
    evidence = {s.key: ai.evidence_for(s, dossier) for s in job.systems}
    pending: list[str] = []
    for system in job.systems:
        try:
            job = job.with_system(ai.write_system(system, evidence[system.key], playbook, transport))
        except ai.NoAnswer as missing:
            pending.append(f"{system.name}: {missing.reason}")
    save(job)
    if pending:
        return RunResult("waiting", "write", waiting=transport.waiting, job_file=job_file, messages=tuple(pending))

    # 4. the estimator's decisions from the last review page, then validate and QC
    job = apply_decisions(job, load_decisions(out))
    findings = validate(job, playbook)
    try:
        qc = ai.qc_job(job, ai.evidence_index(dossier), playbook, transport)
    except ai.NoAnswer as missing:
        save(job)
        return RunResult("waiting", "qc", waiting=transport.waiting, job_file=job_file, findings=tuple(findings),
                         messages=(f"QC: {missing.reason}",))

    # 5. revise (must_fix only, one round), validate again
    must_fix = [f for f in [*findings, *qc] if f.severity == "must_fix"]
    for key in dict.fromkeys(f.system_key for f in must_fix if f.system_key):
        system = job.system(key)
        try:
            job = job.with_system(ai.revise_system(system, [f for f in must_fix if f.system_key == key],
                                                   evidence[key], playbook, transport))
        except ai.NoAnswer as missing:
            pending.append(f"{system.name}: {missing.reason}")
    save(job)
    if pending:
        return RunResult("waiting", "revise", waiting=transport.waiting, job_file=job_file, messages=tuple(pending))
    findings = validate(job, playbook)
    open_qc = [f for f in qc if f.severity != "must_fix"]
    all_findings = tuple([*findings, *open_qc])

    # 6. the review page, the render and the three documents
    review = review_page(job, all_findings, out)
    print(f"Wrote {review}")
    draft = render(job, playbook)
    evidence_file = write_evidence(out / f"{quote} Evidence Package.xlsx", catalogue, reading, ledger=ledger)
    print(f"Wrote {evidence_file}")
    proposal, sheet = _build(draft.scope, PROPOSAL_TEMPLATE, WORKUP_TEMPLATE, PriceBook.load(PRICE_BOOK, ALIASES), out)
    print(f"Wrote {proposal}")
    print(f"Wrote {sheet}")
    return RunResult("done", "done", job_file=job_file, findings=all_findings, review=review, proposal=proposal,
                     price_sheet=sheet, evidence=evidence_file)
