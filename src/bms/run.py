"""The rebuilt estimate, in its final order (design §5 "Integration"):

read (the old app's staged reading) -> plan_job -> counts cross-check (text and vision, through the run's transport)
-> write_system per system -> the estimator's decisions -> validate -> qc_job -> revise_system (must_fix only, one
round) -> validate -> review_page (with the count proofs) -> render -> the Word proposal, the price sheet and the
Evidence Package (the Job's scope lines and findings beside the old reading tabs).

The run waits at "count" while the vision count's sheet questions have no answer: the counts are part of each
system's skeleton, so writing before they are in would ask the writer again once they arrive.

In chat mode a step with no answer yet writes its request and the run stops after the step has asked every question
it can (all systems are asked before stopping); the next run picks the cached answers up and does not ask a
question whose request is still waiting. A step that refuses an answer `max_attempts` times stops the run with a
plain message naming the request. Decisions saved from the review page are applied on the next run, and the
writer is asked again only for the systems those decisions changed. A malformed decisions.json stops the run
with a plain message. Every output goes under `out`
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
from estimator.ledger.run import read_job as read_ledger
from estimator.price_sheet.price_book import PriceBook
from estimator.reading.job import read_job
from estimator.writing.dossier import build_dossier
from estimator.writing.front_end import job_header
from estimator.writing.judge import Judge

from bms import ai, ai_evidence
from bms.citations import job_ids, job_sheets, job_tags
from bms.counts import cross_check, flag_written_devices, publish_proofs
from bms.evidence import write_evidence
from bms.model import Decision, Finding, Header, Job, ModelError
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
    stage: str                              # the last step reached: "read", "count", "write", "qc", "revise", "done"
    waiting: int = 0
    job_file: Path | None = None            # out/<quote> Job.json: the Job model as last saved
    findings: tuple[Finding, ...] = ()      # the final validate's findings plus the QC findings left open
    review: Path | None = None              # out/Review.html
    proposal: Path | None = None
    price_sheet: Path | None = None
    evidence: Path | None = None
    messages: tuple[str, ...] = ()          # plain lines for the console


def _changed_system_keys(before: Job, after: Job) -> tuple[str, ...]:
    """Systems a decision actually changed. A deleted system is not asked again; it is already gone."""
    kept = {system.key for system in after.systems}
    return tuple(system.key for system in before.systems
                 if system.key in kept and system != after.system(system.key))


def _decision_note(decisions: tuple[Decision, ...] | list[Decision], key: str) -> str:
    """What the writer must keep when it is asked again for one system. Stable, so a resume hits the cache."""
    lines = ["The estimator's decisions for this system (keep them; do not undo them):"]
    for decision in decisions:
        if decision.system_key != key:
            continue
        what = decision.device_id or decision.family_name or "the whole system"
        reason = f": {decision.reason}" if decision.reason else ""
        lines.append(f"- {decision.action} {what}{reason}")
    return "\n".join(lines)


def _stopped(reason: str) -> str:
    text = str(reason)
    return text if text.startswith("Stopped:") else f"Stopped: {text}"


def _workers() -> int:
    return max(1, min(4, os.cpu_count() or 1))


def _untouched(finding: Finding, before: Job, after: Job) -> bool:
    """A QC finding the revise round left as it was: its device (or, for a finding about a whole system, the
    system; for the front end or the whole job, everything) is the same after the revise. It stays open for the
    estimator, since QC is not asked again."""
    if not finding.system_key:
        return True
    try:
        old, new = before.system(finding.system_key), after.system(finding.system_key)
    except KeyError:
        return False
    if finding.device_id is None:
        return old == new
    device = {d.id: d for d in new.devices}.get(finding.device_id)
    return device is not None and device == {d.id: d for d in old.devices}.get(finding.device_id)


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
    transport = (ai.ChatTransport(cache, job=dossier.job_name) if mode == "chat" else ai.ApiTransport(cache))
    asked = transport.waiting
    job = cross_check(job, catalogue, cache, transport=transport)
    job_file = out / f"{quote} Job.json"

    def save(current: Job) -> None:
        job_file.write_text(current.to_json(), encoding="utf-8")

    if transport.waiting > asked:
        save(job)
        return RunResult("waiting", "count", waiting=transport.waiting, job_file=job_file,
                         messages=(f"Plan counts: {transport.waiting - asked} sheet(s) wait for the vision "
                                   "count.",))

    # 3. write every system (all are asked before stopping for answers)
    evidence = {s.key: ai.evidence_for(s, dossier) for s in job.systems}
    # I, one set for every writer and the revise: every id of the job and of every system's evidence. A ref may
    # cite only its system's evidence, so the final job's ids (the validator's and the renderer's I) are in it, and a
    # text one writer accepts is never an issued id once a later system cites it.
    evidence_ids = sorted(set().union(*(ai_evidence.cited_ids(e) for e in evidence.values())))

    def issued(current: Job) -> tuple[str, ...]:
        return tuple(dict.fromkeys([*job_ids(current), *evidence_ids]))

    # K, one set for every writer, the decision rewrite and the revise: the sheet numbers the planner's wheres name
    # (after the counts cross-check, whose refs carry sheets). The skeleton's refs win over every answer, so K never
    # changes while the systems are written, and it is the validator's and the renderer's K too.
    sheets = tuple(sorted(job_sheets(job)))

    pending: list[str] = []
    for system in job.systems:
        try:
            job = job.with_system(flag_written_devices(
                ai.write_system(system, evidence[system.key], playbook, transport, tags=job_tags(job),
                                ids=issued(job), sheets=sheets)))
        except ai.NoAnswer as missing:
            pending.append(_stopped(missing.reason) if str(missing.reason).startswith("Stopped:")
                           else f"{system.name}: {missing.reason}")
    save(job)
    if pending:
        return RunResult("waiting", "write", waiting=transport.waiting, job_file=job_file, messages=tuple(pending))

    # 4. the estimator's decisions from the last review page. The writer is asked again only for a system a
    # decision changed; every other system's cached answer stands. A malformed file stops the run in words.
    try:
        decisions = load_decisions(out)
    except ModelError as error:
        return RunResult("waiting", "decisions", waiting=0, job_file=job_file, messages=(_stopped(error),))
    written = job
    job = apply_decisions(job, decisions)
    for key in _changed_system_keys(written, job):
        system = job.system(key)
        try:
            job = job.with_system(flag_written_devices(ai.write_system(
                system, f"{evidence[key]}\n\n{_decision_note(decisions, key)}", playbook, transport,
                tags=job_tags(job), ids=issued(job), sheets=sheets)))
        except ai.NoAnswer as missing:
            pending.append(_stopped(missing.reason) if str(missing.reason).startswith("Stopped:")
                           else f"{system.name}: {missing.reason}")
    if not pending:
        job = apply_decisions(job, decisions)   # a rewritten answer does not undo the decision
    save(job)
    if pending:
        return RunResult("waiting", "write", waiting=transport.waiting, job_file=job_file, messages=tuple(pending))

    # validate and QC
    findings = validate(job, playbook)
    try:
        qc = ai.qc_job(job, ai.evidence_index(dossier), playbook, transport)
    except ai.NoAnswer as missing:
        save(job)
        text = _stopped(missing.reason) if str(missing.reason).startswith("Stopped:") else f"QC: {missing.reason}"
        return RunResult("waiting", "qc", waiting=transport.waiting, job_file=job_file, findings=tuple(findings),
                         messages=(text,))

    # 5. revise (must_fix only, one round), validate again
    must_fix = [f for f in [*findings, *qc] if f.severity == "must_fix"]
    written = job
    for key in dict.fromkeys(f.system_key for f in must_fix if f.system_key):
        system = job.system(key)
        try:
            job = job.with_system(ai.revise_system(system, [f for f in must_fix if f.system_key == key],
                                                   evidence[key], playbook, transport, tags=job_tags(job),
                                                   ids=issued(job), sheets=sheets))
        except ai.NoAnswer as missing:
            pending.append(_stopped(missing.reason) if str(missing.reason).startswith("Stopped:")
                           else f"{system.name}: {missing.reason}")
    save(job)
    if pending:
        return RunResult("waiting", "revise", waiting=transport.waiting, job_file=job_file, messages=tuple(pending))
    findings = validate(job, playbook)
    open_qc = [f for f in qc if f.severity != "must_fix" or _untouched(f, written, job)]
    all_findings = tuple([*findings, *open_qc])

    # 6. the review page, the render and the three documents
    publish_proofs(job, cache, out)
    review = review_page(job, all_findings, out)
    print(f"Wrote {review}")
    draft = render(job, playbook)
    printed = {line.device_id: line.text for line in draft.lines if line.device_id}
    evidence_file = write_evidence(out / f"{quote} Evidence Package.xlsx", catalogue, reading, ledger, job,
                                   all_findings, printed)
    print(f"Wrote {evidence_file}")
    proposal, sheet = _build(draft.scope, PROPOSAL_TEMPLATE, WORKUP_TEMPLATE, PriceBook.load(PRICE_BOOK, ALIASES), out)
    print(f"Wrote {proposal}")
    print(f"Wrote {sheet}")
    return RunResult("done", "done", job_file=job_file, findings=all_findings, review=review, proposal=proposal,
                     price_sheet=sheet, evidence=evidence_file)
