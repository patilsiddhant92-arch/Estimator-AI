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
plain message naming the request. Decisions saved from the review page are applied once on the next run, and the
writer is asked again only for the systems those decisions changed. The decision is not applied a second time
after that ask: the writer numbers devices from d1, so a second "delete d1" would remove the next device. After
the last write, a saved decision that the final job does not still show is a must_fix "decision not honored" on
the review page. The page shows the job after the revise, so a device decision whose saved line matches nothing
the writer wrote (the revise re-worded it) is applied to the revised job instead; one that matches neither is a
must_fix "decision could not be applied" on the review page, never skipped in silence. The page saves only its own
answers, so the run keeps every save in `decisions history.json` and applies them all (`bms.review.merge_decisions`):
a later save never undoes an earlier one in silence, and an earlier decision that took effect and whose line is in
no job any more makes no card. A malformed decisions.json stops the run with a plain message. Every output goes under `out`
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

from bms import ai
from bms.citations import job_ids, job_tags
from bms.counts import cross_check, flag_written_devices, publish_proofs
from bms.evidence import write_evidence
from bms.model import Decision, Finding, Header, Job, ModelError
from bms.plan import plan_job
from bms.playbook import load_playbook
from bms.render import render
from bms.review import (SavedDecision, _matches_nothing, apply_decisions, load_decisions, load_history,
                        merge_decisions, review_page, save_history, unhonored_decisions)
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


def _counts_changed(decisions, key: str) -> bool:
    return any(d.system_key == key and d.family_name is not None and d.action == "change" and d.count is not None
               for d in decisions)


def _standing_accepts(entries: list[SavedDecision], key: str) -> list[Decision]:
    """The accepts on system `key` that a count change does not overrule: those saved in a later round than every
    count change on that system (the estimator saw the new count when accepting). An accept from the same save as a
    count change, or an older one, is dropped: the rewrite for the count flags the system again."""
    last = max((e.round for e in entries if _counts_changed([e.decision], key)), default=0)
    return [e.decision for e in entries
            if e.decision.system_key == key and e.decision.action == "accept" and e.round > last]


def _revised(system, findings, evidence, playbook, transport, job=None, decisions=None):
    """Revise, then flag quantity disagreements again. Devices accepted by the estimator stay accepted, unless a
    decision in `decisions` changes a family count of this system (the new count flags the system again)."""
    if job is None:
        revised = ai.revise_system(system, findings, evidence, playbook, transport)
    else:
        revised = ai.revise_system(system, findings, evidence, playbook, transport,
                                    tags=job_tags(job), ids=job_ids(job))
    flagged = flag_written_devices(revised)
    if not decisions:
        return flagged
    accepted = [d for d in decisions if d.action == "accept" and d.system_key == system.key]
    if not accepted or _counts_changed(decisions, system.key):
        return flagged
    if job is not None:
        temp_job = dataclasses.replace(job, systems=(flagged,))
    else:
        temp_job = Job("temp", systems=(flagged,))
    return apply_decisions(temp_job, accepted).system(system.key)


def _families_changed(before: Job, key: str, after: Job) -> bool:
    """True when a decision changed a family's count. A device edit does not."""
    return before.system(key).families != after.system(key).families


def _count_note(decisions: tuple[Decision, ...] | list[Decision], key: str) -> str:
    """The count change, by family name. No device id: the writer must not renumber from one."""
    lines = ["The estimator's count decisions for this system:"]
    for decision in decisions:
        if decision.system_key != key or not decision.family_name:
            continue
        value = decision.count.value if decision.count is not None else None
        suffix = f" to {value}" if value is not None else ""
        lines.append(f"- {decision.action} the {decision.family_name} count{suffix}")
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
    pending: list[str] = []
    for system in job.systems:
        try:
            job = job.with_system(flag_written_devices(
                ai.write_system(system, evidence[system.key], playbook, transport, tags=job_tags(job),
                                ids=job_ids(job))))
        except ai.NoAnswer as missing:
            pending.append(_stopped(missing.reason) if str(missing.reason).startswith("Stopped:")
                           else f"{system.name}: {missing.reason}")
    save(job)
    if pending:
        return RunResult("waiting", "write", waiting=transport.waiting, job_file=job_file, messages=tuple(pending))

    # 4. the estimator's decisions. A device accept, change or delete is applied to the written devices and
    # the writer is not asked again: it would number devices from d1 and a later apply would hit the wrong one.
    # A family-count change is the only reason to ask again, and the devices already written are kept.
    # A malformed file stops the run in words. The page saves only its own answers, so the run keeps every save in
    # the history (bms.review.merge_decisions) and applies them all: a second save never undoes the first in silence.
    try:
        history = merge_decisions(load_history(out), load_decisions(out))
    except ModelError as error:
        return RunResult("waiting", "decisions", waiting=0, job_file=job_file, messages=(_stopped(error),))
    if history:
        save_history(out, history)
    decisions = [entry.decision for entry in history]
    latest = max((entry.round for entry in history), default=0)
    decided_from = job
    job = apply_decisions(job, decisions)
    for key in _changed_system_keys(decided_from, job):
        system = job.system(key)
        if not _families_changed(decided_from, key, job):
            continue
        try:
            rewritten = flag_written_devices(ai.rewrite_for_count(
                system, f"{evidence[key]}\n\n{_count_note(decisions, key)}", playbook, transport,
                tags=job_tags(job), ids=job_ids(job)))
            standing = _standing_accepts(history, key)          # accepted after the estimator saw the new count
            if standing:
                rewritten = apply_decisions(job.with_system(rewritten), standing).system(key)
            job = job.with_system(rewritten)
        except ai.NoAnswer as missing:
            pending.append(_stopped(missing.reason) if str(missing.reason).startswith("Stopped:")
                           else f"{system.name}: {missing.reason}")
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
            job = job.with_system(_revised(system, [f for f in must_fix if f.system_key == key],
                                            evidence[key], playbook, transport, job,
                                            decisions=_standing_accepts(history, key)))
        except ai.NoAnswer as missing:
            pending.append(_stopped(missing.reason) if str(missing.reason).startswith("Stopped:")
                           else f"{system.name}: {missing.reason}")
    # a device decision made on the page's (revised) wording that matched nothing the writer wrote is applied to
    # the revised job; one decision is never applied twice
    # (an accept a count change overrules is not applied late either)
    late = [d for d in decisions if _matches_nothing(decided_from, d)
            and (d.action != "accept" or d in _standing_accepts(history, d.system_key))]
    early = [d for d in decisions if not _matches_nothing(decided_from, d)]
    revised_job = job
    job = apply_decisions(job, late)

    def took_effect(decision: Decision) -> bool:
        return not _matches_nothing(decided_from, decision) or (
            decision in late and not _matches_nothing(revised_job, decision))

    # a decision from an earlier save that took effect on some run and whose line is now in no job stays silent:
    # it did its work. One that never took effect keeps its "could not be applied" card.
    quiet = [entry.decision for entry in history if entry.round < latest and entry.took_effect]
    checked_late = [d for d in late if not (d in quiet and _matches_nothing(revised_job, d))]
    history = [dataclasses.replace(entry, took_effect=entry.took_effect or took_effect(entry.decision))
               for entry in history]
    if history:
        save_history(out, history)
    save(job)
    if pending:
        return RunResult("waiting", "revise", waiting=transport.waiting, job_file=job_file, messages=tuple(pending))
    findings = validate(job, playbook)
    open_qc = [f for f in qc if f.severity != "must_fix" or _untouched(f, written, job)]
    all_findings = tuple([*findings, *open_qc, *unhonored_decisions(decided_from, early, job),
                          *unhonored_decisions(revised_job, checked_late, job)])

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
