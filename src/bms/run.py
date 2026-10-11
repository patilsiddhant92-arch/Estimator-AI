"""The rebuilt estimate, in its final order (design §5 "Integration"):

read (the old app's staged reading) -> takeoff (`bms.takeoff`: one whole-job AI step returns the sheet classes and the
unit register; stored on the Job, it changes no count) -> plan_job -> counts cross-check (text and vision, through
the run's transport)
-> write_system per system, then write_front_end (the front end is written like a system, from the passages the
planner cited for it; nothing is asked when the documents call for none) -> the estimator's decisions -> validate ->
qc_job -> revise_system (must_fix only, one round; revise_front_end for the front end's findings) -> validate ->
the coverage gate (`bms.coverage.coverage`, once, on the final Job: a fact the ledger read that nothing in the Job
cites is a `check` finding; it only reports, never changes the Job and never stops the run) -> review_page (with the
count proofs; the gate's findings are its group "Not cited in the job") -> render -> the Word proposal, the price
sheet and the Evidence Package (the Job's scope lines and findings beside the old reading tabs).

The run waits at "count" while the vision count's sheet questions have no answer: the counts are part of each
system's skeleton, so writing before they are in would ask the writer again once they arrive.

In chat mode a step with no answer yet writes its request and the run stops after the step has asked every question
it can (all systems are asked before stopping); the next run picks the cached answers up and does not ask a
question whose request is still waiting. A step that refuses an answer `max_attempts` times stops the run with a
plain message naming the request. Decisions saved from the review page are applied on the next run without asking
the writer again; only a changed family count makes the writer write that system again. A device decision is not
applied by id after that ask: the writer numbers devices from d1, so a second "delete d1" would remove the next
device. A delete is applied again after it by the line's saved content only, so the rewrite never writes a deleted
line back. A page change whose new name prints an issued source id is kept as the estimator wrote it, is not sent
to the revise (which would write the line back under its old name), and is a must_fix card naming the id. After
the last write, a saved decision that the final job does not still show is a must_fix "decision not honored" on
the review page. The page shows the job after the revise, so a device decision whose saved line matches nothing
the writer wrote (the revise re-worded it) is applied to the revised job instead; one that matches neither is a
must_fix "decision could not be applied" on the review page, never skipped in silence. The page saves only its own
answers, so the run keeps every save in `decisions history.json` and applies them all (`bms.review.merge_decisions`):
a later save never undoes an earlier one in silence. An earlier delete that took effect and whose line is in no job
any more makes no card while its system is as the last finished run left it; when the system changed since (it
was asked again), it is a "check this system" card (severity check), since the line may have come back
re-worded. An earlier change or accept that matches nothing keeps its "could not be applied" card. A malformed
decisions.json stops the run with a plain message. The run's first and very last acts are a small `run state.json`
in `out`: first "running" (rewritten with the quote and the job name once they are known), last how it ended
(status, stage, how many requests wait, its plain messages, the quote, the job, and how many decisions the history
held). Each is written whole or not at all, and one that cannot be written never stops the run. A run that crashes
leaves "running", which `python -m bms status` reports as not finished; a run a person can put right (a proposal
that cannot be printed, an output open in Word or Excel, a missing job folder) ends it as stopped at its step, in
words. Status trusts an ending only while no ledger or job is
newer. Every output goes under `out` (NDA: never the repo). Prints "Wrote <path>" per file, as the old app does (tools/run_job.py reads those lines).
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import json
import os
import time
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

from bms import ai, ai_evidence, takeoff
from bms.citations import device_refs, job_ids, job_sheets, job_tags, source_sheets
from bms.counts import counted_from, cross_check, flag_written_devices, publish_proofs
from bms.coverage import coverage
from bms.evidence import write_evidence
from bms.labor import labor_conditions, labor_findings, with_labor, with_warranty
from bms.model import Decision, Device, Finding, Header, Job, ModelError, System
from bms.plan import plan_job
from bms.takeoff import attach_demolition
from bms.playbook import load_playbook
from bms.citations import SourceIds
from bms.render import RenderError, render
from bms.status import RUN_STATE
from bms.review import (DECISIONS_FILE, DECISIONS_HISTORY, SavedDecision, _matches_nothing, _target, accept_families,
                        apply_decisions, apply_seen, copies_seen, held_back, keep_deleted, load_decisions, load_history,
                        merge_decisions, review_page, save_history, system_digest, unhonored_decisions)
from bms.validate import RULE, validate

Mode = Literal["chat", "api"]
ROOT = Path(__file__).resolve().parents[2]      # the app's own folder (the git tree)
MODES = ("chat", "api")
Status = Literal["waiting", "done"]


@dataclass(frozen=True)
class RunResult:
    """What one run did. `status` "waiting": chat requests wait for answers (`waiting` of them, at `stage`);
    "done": the proposal, price sheet and Evidence Package are written."""
    status: Status
    stage: str                              # the last step reached: "read", "takeoff", "count", "write", "decisions",
                                            # "qc", "revise", "done"; "render" only in the run state of a stop while
                                            # printing
    waiting: int = 0
    job_file: Path | None = None            # out/<quote> Job.json: the Job model as last saved
    findings: tuple[Finding, ...] = ()      # the final validate's findings, the QC findings left open and the coverage
                                            # gate's (facts the job does not cite)
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


def _counts_changed(decisions, key: str, families: frozenset[str] | None = None) -> bool:
    """True when a decision changes the count of any family in `families` of system `key` (of any family, for
    None)."""
    return any(d.system_key == key and d.family_name is not None and d.action == "change" and d.count is not None
               and (families is None or d.family_name in families) for d in decisions)


def _standing_accepts(entries: list[SavedDecision], key: str, job: Job | None = None) -> list[Decision]:
    """The accepts on system `key` that a count change does not overrule: those saved in a later round than every
    count change of every family the accepted line's quantity cites (the estimator saw the new count when
    accepting); a count change of a family the line does not cite leaves the accept standing. When the line's
    families are not known (no `job`, or the line cites no family's count), a count change of any family of the
    system counts. An accept
    from the same save as such a count change, or an older one, is dropped: the rewrite for the count flags the
    system again."""
    standing = []
    for entry in entries:
        d = entry.decision
        if d.system_key != key or d.action != "accept":
            continue
        families = accept_families(job, d)
        last = max((e.round for e in entries if _counts_changed([e.decision], key, families)), default=0)
        if entry.round > last:
            standing.append(d)
    return standing


def _held_counts(decisions, key: str) -> tuple[str, ...]:
    """The names of the families of system `key` whose count the estimator set (a family change among `decisions`):
    a revise never changes them (HP 17)."""
    return tuple(dict.fromkeys(d.family_name for d in decisions
                               if d.system_key == key and d.action == "change" and d.family_name is not None))


def _revised(system, findings, evidence, playbook, transport, job=None, decisions=None, ids=None, sheets=(),
             source_sheets=None, hold_counts=(), typed=frozenset()):
    """Revise, then flag quantity disagreements again. Devices accepted by the estimator stay accepted, unless a
    decision in `decisions` changes a family count of this system (the new count flags the system again). A revise
    may correct a family's count (HP 17, `ai.revise_system`): every line still at the old count it was counted from
    takes the new one (`_carry_new_counts`; a line in `typed` keeps the count the estimator typed), and a family in
    `hold_counts` (the estimator set its count) keeps it."""
    held = {"hold_counts": tuple(hold_counts)} if hold_counts else {}
    if job is None:
        revised = ai.revise_system(system, findings, evidence, playbook, transport, **held)
    else:
        revised = ai.revise_system(system, findings, evidence, playbook, transport, tags=job_tags(job),
                                    ids=job_ids(job) if ids is None else ids, sheets=sheets,
                                    source_sheets=tuple(job.source_sheets) if source_sheets is None
                                    else source_sheets, **held)
    if revised.families != system.families:
        revised = _carry_new_counts(system, revised, revised, frozenset(typed))
    flagged = flag_written_devices(revised)
    if not decisions:
        return flagged
    accepted = [d for d in decisions if d.action == "accept" and d.system_key == system.key
                and not _counts_changed(decisions, system.key, accept_families(job, d))]
    if not accepted:
        return flagged
    if job is not None:
        temp_job = dataclasses.replace(job, systems=(flagged,))
    else:
        temp_job = Job("temp", systems=(flagged,))
    return apply_decisions(temp_job, accepted).system(system.key)


def _families_changed(before: Job, key: str, after: Job) -> bool:
    """True when a decision changed a family's count. A device edit does not."""
    return before.system(key).families != after.system(key).families


def _typed_counts(decisions, key: str, before: Job) -> frozenset[str]:
    """The ids of `key`'s lines whose count the estimator set: a device change whose quantity differs from the
    line's as the page showed it (`was`; without one, the line in `before`). A rename or other words-only change
    sets no count, so its line still takes a changed family count (AI-1)."""
    lines = {d.id: d for d in before.system(key).devices} if any(s.key == key for s in before.systems) else {}
    typed = set()
    for d in decisions:
        if d.system_key != key or d.action != "change" or d.device is None or not d.device_id:
            continue
        shown = d.was if d.was is not None else lines.get(d.device_id)
        if shown is None or d.device.quantity != shown.quantity:
            typed.add(d.device_id)
    return frozenset(typed)


def _carry_new_counts(before: System, after: System, rewritten: System, typed: frozenset[str] = frozenset()
                      ) -> System:
    """The count rewrite's system with every line still at a changed family's old count given the new one (AI-1,
    the safety net under `ai.rewrite_for_count`): a line counted from the family as it was (`counts.counted_from`
    on `before`'s family, since the estimator's count may cite other sources) whose quantity is the old count.
    Only the number changes. A family is matched by name; one whose count was or is unknown changes nothing.
    A line whose count the estimator typed (its id in `typed`, `_typed_counts`) keeps the count it has in `after`:
    a typed count is never replaced, by the answer or by this net."""
    changed = [(old, new) for old in before.families for new in after.families
               if new.name == old.name and None not in (old.count.value, new.count.value)
               and old.count.value != new.count.value]
    own = {d.id: d.quantity for d in after.devices if d.id in typed}

    def carried(device: Device) -> Device:
        if device.id in own:
            return device if device.quantity == own[device.id] else dataclasses.replace(device,
                                                                                        quantity=own[device.id])
        for old, new in changed:
            if device.quantity.value == old.count.value and counted_from(device, old):
                return dataclasses.replace(device, quantity=dataclasses.replace(device.quantity,
                                                                                value=new.count.value))
        return device
    devices = tuple(carried(device) for device in rewritten.devices)
    return rewritten if devices == rewritten.devices else dataclasses.replace(rewritten, devices=devices)


def _reapplied(job: Job, base: System, rewritten: System, decisions: list[Decision],
               copies: dict[Decision, int]) -> System:
    """The count rewrite of `base` (the written system with only its count changes) with the system's line
    decisions (changes and deletes) applied again (RUN-2). The rewrite keeps every written line's id and words, but
    may give a line the new count, so a decision whose saved line (`was`) the rewrite no longer has word for word is
    applied to the line of the rewrite with the id of the line it named in `base`."""
    ids = {device.id for device in rewritten.devices}
    on = job.with_system(rewritten)
    shown_on = job.with_system(base)
    again = []
    for decision in decisions:
        if _matches_nothing(on, decision):
            line = _target(shown_on, decision)
            if line is not None and line.id in ids:
                now = next(device for device in rewritten.devices if device.id == line.id)
                decision = dataclasses.replace(decision, device_id=line.id, was=now)
        again.append(decision)
    return apply_seen(on, again, copies).system(rewritten.key)


def _count_note(decisions: tuple[Decision, ...] | list[Decision], key: str) -> str:
    """The count changes, by family name; nothing else, so the rewrite's question changes only with them (RUN-2).
    No device id: the writer must not renumber from one."""
    lines = ["The estimator's count decisions for this system:"]
    for decision in decisions:
        if not _counts_changed([decision], key):
            continue
        value = decision.count.value if decision.count is not None else None
        suffix = f" to {value}" if value is not None else ""
        lines.append(f"- {decision.action} the {decision.family_name} count{suffix}")
    return "\n".join(lines)


def _asked_about_front_end(job: Job) -> Job:
    """The job with one more question when the writer wrote no front-end line (HP 22): the estimator reads why, in
    the writer's words, and says whether the job needs a front end. The documents call for none, or give all of it to
    others; no standard line stands in."""
    front = job.front_end
    if front is None or front.devices or not (front.no_scope_reason or "").strip():
        return job
    reason = front.no_scope_reason.strip().rstrip(".")
    question = (f"No front-end line was written: {reason}. If this job needs a front end, say what it is and where "
                "the documents call for it.")
    return dataclasses.replace(job, questions=tuple(dict.fromkeys((*job.questions, question))))


def _coverage_findings(job: Job, ledger, dossier) -> tuple[list[Finding], tuple[str, ...]]:
    """The coverage gate (`bms.coverage.coverage`) on the final job: a fact the ledger read that nothing in the job
    cites is one `check` finding, for the review page and the Evidence Package. It only reports: the job is never
    changed, and a fault in the gate never stops the run. It gives no finding then, and the console gets one plain
    line that says so."""
    try:
        return coverage(job, ledger, dossier), ()
    except Exception as error:      # report only: a fault here must not block an estimate that is otherwise done
        return [], (f"Coverage: the check for facts the job does not cite could not run ({type(error).__name__}: "
                    f"{error}). The other findings stand.",)


def _check_this_system(decision: Decision) -> Finding:
    """The check (severity "check", a model Severity) for an earlier delete that took effect, whose line is in no
    job any more, on a system that was asked again since: the line may be back in other words. About the system (no
    line), so its card has no Delete button."""
    line = decision.was.name if decision.was is not None else decision.device_id
    return Finding("decision not honored", decision.system_key, None, "check",
                   f"check this system: an earlier delete of {line} may have come back re-worded",
                   "This system was written again after your delete. Check that the line you deleted is not back "
                   "under other words; delete it again if it is.")


def _ids_in_changes(job: Job, decisions) -> list[tuple[Decision, str, tuple[str, ...]]]:
    """The estimator's changed lines of `job` whose client text prints an issued source id (the detector the
    validator and the renderer use, `SourceIds.of_job`): (the change, the line's id in `job`, the issued tokens). A
    page change does not go through the writer's intake, so this is where it is checked. The page sets the name (and
    the quantity and the verb and parties, which are no free text); decisions.json can be edited by hand, so the
    assumption's what and why are checked too, as the validator checks them, and so is the where of each of its refs
    on a writer's system (`SourceIds.where_issued`, the validator's `_where_hits`; the front end's refs are the
    planner's). A Decision carries no clarification."""
    ids = SourceIds.of_job(job)
    found = []
    for decision in decisions:
        if decision.action != "change" or decision.device is None or decision.device_id is None:
            continue
        device = decision.device
        texts = [device.name, *((device.assumption.what, device.assumption.why) if device.assumption else ())]
        tokens = [f.token for text in texts for f in ids.scan(text) if f.kind == "issued"]
        if decision.system_key:
            tokens += [t for ref in device_refs(device) for t in ids.where_issued(ref.where)]
        tokens = tuple(dict.fromkeys(tokens))
        if not tokens:
            continue
        if decision.system_key == "":
            devices = job.front_end.devices if job.front_end is not None else ()
        else:
            devices = next((s.devices for s in job.systems if s.key == decision.system_key), ())
        probe = dataclasses.replace(decision.device, id="", flag="none")
        for device in devices:
            if dataclasses.replace(device, id="", flag="none") == probe:
                found.append((decision, device.id, tokens))
    return found


def _id_change_card(decision: Decision, device_id: str, tokens: tuple[str, ...]) -> Finding:
    """The must_fix for an estimator's change that prints an issued id: the line is kept as they wrote it."""
    return Finding(RULE["ids"], decision.system_key, device_id, "must_fix",
                   f"your change prints a source id ({', '.join(tokens)}): name the document in words",
                   "Your line is kept as you wrote it, but a proposal must not print a source id. Change the line "
                   "again with the document named in words (\"the mechanical schedule\", \"sheet M-101\").")


def _not_answered(name: str, missing: ai.NoAnswer) -> str:
    """A step's missing answer for the console: a stop in its own words, else the step's name and the reason."""
    reason = str(missing.reason)
    return _stopped(reason) if reason.startswith("Stopped:") else f"{name}: {reason}"


def _save_history(out: Path, history: list[SavedDecision], job_file: Path) -> RunResult | None:
    """Save the decisions history; when it cannot be saved (another program has it open), the run stops with a
    plain message naming the file, never a traceback (`save_history` gives every failure as a ModelError)."""
    try:
        saved_to = save_history(out, history)
    except ModelError as error:
        return RunResult("waiting", "decisions", waiting=0, job_file=job_file, messages=(_stopped(error),))
    print(f"Wrote {saved_to}")
    return None


def _stopped(reason: str) -> str:
    text = str(reason)
    return text if text.startswith("Stopped:") else f"Stopped: {text}"


def _stop_words(error: Exception, stage: str) -> str:
    """The plain "Stopped:" line for a run that cannot go on: a locked file by its name, a missing one by its path,
    a proposal that cannot be printed with the check's own words."""
    if isinstance(error, PermissionError):
        if error.filename:
            return _stopped(f"{Path(error.filename).name} is open in Word or Excel — close it and run again.")
        return _stopped(f"a file could not be written ({error.strerror or error}); another program may have it "
                        f"open. Close it and run again.")
    if isinstance(error, FileNotFoundError):
        return _stopped(f"{error.filename or error} was not found. Check the job folder and run again.")
    if str(error).startswith("Stopped:"):
        return str(error)
    if isinstance(error, RenderError) or stage == "render":
        return _stopped(f"the proposal could not be printed: {error}. Fix what it names and run again.")
    return _stopped(f"{error}. Fix what it names and run again.")


def _workers() -> int:
    return max(1, min(4, os.cpu_count() or 1))


def _untouched(finding: Finding, before: Job, after: Job, playbook=None) -> bool:
    """A QC finding the revise round left as it was: its device (or, for a finding about a whole system, the
    system; for a finding about the front end, its line or the front end; for the whole job, everything) is the same
    after the revise. It stays open for the estimator, since QC is not asked again."""
    if not finding.system_key:
        if ai.is_front_end_finding(finding, before.front_end, playbook):
            old, new = before.front_end, after.front_end
            if finding.device_id is None or new is None:
                return old == new
            device = {d.id: d for d in new.devices}.get(finding.device_id)
            return device is not None and device == {d.id: d for d in old.devices}.get(finding.device_id)
        return True
    try:
        old, new = before.system(finding.system_key), after.system(finding.system_key)
    except KeyError:
        return False
    if finding.device_id is None:
        return old == new
    device = {d.id: d for d in new.devices}.get(finding.device_id)
    return device is not None and device == {d.id: d for d in old.devices}.get(finding.device_id)


def _write_run_state(out: Path, state: dict) -> None:
    """`out/run state.json`, written whole (a temporary name, then swapped in), in plain ASCII so no text can fail to
    encode. The swap is tried up to 5 times, 100 ms apart (on Windows it fails while `bms status` or another reader
    holds the file open). One that still cannot be written is let go (the temporary file is removed): it never stops
    the run, and status then reads an older state, which never makes the run look finished."""
    path = out / RUN_STATE
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(json.dumps(state, ensure_ascii=True, indent=1), encoding="ascii")
        for attempt in range(5):
            try:
                os.replace(tmp, path)
                break
            except OSError:
                if attempt == 4:
                    raise
                time.sleep(0.1)
    except (OSError, ValueError):        # UnicodeError is a ValueError
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def _save_running(out: Path, quote: str = "", job: str = "", decisions: int = 0) -> None:
    """The run has started and not ended: written first, and again once the quote and the job name are known."""
    _write_run_state(out, {"version": 1, "status": "running", "stage": "read", "quote": quote, "job": job, "decisions": decisions})


def _save_run_state(out: Path, result: RunResult, quote: str = "", job: str = "", decisions: int = 0) -> None:
    """How the run ended, for `python -m bms status`, as the run's last act; with the quote (as in the ledger's file
    name) and the job name, so status never takes another job's ending for this one. `decisions`: how many
    decisions the decisions history held when a run last saved it (0: none saved yet), so a later run can tell a
    lost history from a first save."""
    _write_run_state(out, {"version": 1, "status": result.status, "stage": result.stage, "waiting": result.waiting,
                           "messages": [str(m) for m in result.messages], "quote": quote, "job": job,
                           "decisions": decisions})


def _decisions_saved_before(out: Path) -> int:
    """How many decisions the last run's state says the history held; 0 when not known."""
    try:
        value = json.loads((out / RUN_STATE).read_text(encoding="ascii")).get("decisions")
    except (OSError, ValueError, AttributeError):
        return 0
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def _check_folders_outside_repo(out: Path, cache: Path) -> None:
    """Job files must stay out of the git tree: an output or cache folder inside the app's folder is refused unless
    it is under its out/ folder. Nothing is written before this check."""
    for folder in (Path(out), Path(cache)):
        found = folder.resolve()
        if found.is_relative_to(ROOT) and not found.is_relative_to(ROOT / "out"):
            raise ValueError(f"Stopped: the folder {found} is inside the app's folder; job files must stay out of "
                             f"the repository. Use a folder under out/ or outside the app.")


def estimate(job_folder: Path, out: Path, cache: Path, mode: Mode = "chat") -> RunResult:
    """Run the rebuilt estimate on one job folder. `cache` is where reading is kept and where the chat requests go
    (`cache/judge-chat`); `mode` "chat" or "api" for every AI question (the reading passes too). Its first act is a
    "running" `out/run state.json`; however the run ends (done, waiting or stopped), its last act replaces it with
    how it ended. A run that cannot go on for a reason a person can fix (a proposal that cannot be printed,
    `RenderError`; an output open in Word or Excel, `PermissionError`; a missing job folder or file,
    `FileNotFoundError`; a template or fit check, `ValueError`) ends it as stopped at the step it reached, in plain
    words (status "waiting", nothing waiting, a "Stopped:" message); the error reaches the caller with that ending as
    its `run_result`. A `ModelError` (the pipeline built a bad model) and any other exception reach the caller
    unchanged and leave "running"."""
    if mode not in MODES:
        raise ValueError(f"the mode must be chat or api, not {mode!r}")
    job_folder, out, cache = Path(job_folder), Path(out), Path(cache)
    _check_folders_outside_repo(out, cache)
    out.mkdir(parents=True, exist_ok=True)
    # the quote and the job name once _estimate knows them; how many decisions the history held at the last save
    known: dict = {"decisions": _decisions_saved_before(out), "stage": "read"}
    _save_running(out, decisions=known["decisions"])
    try:
        result = _estimate(job_folder, out, cache, mode, known)
    except ModelError:
        raise
    except (RenderError, PermissionError, FileNotFoundError, ValueError) as error:
        stopped = RunResult("waiting", known["stage"], waiting=0, messages=(_stop_words(error, known["stage"]),))
        _save_run_state(out, stopped, known.get("quote", ""), known.get("job", ""), known["decisions"])
        error.run_result = stopped
        raise
    if result.job_file is not None and result.job_file.is_file():
        print(f"Wrote {result.job_file}")
    _save_run_state(out, result, known.get("quote", ""), known.get("job", ""), known["decisions"])
    print(f"Wrote {out / RUN_STATE}")
    return result


def _estimate(job_folder: Path, out: Path, cache: Path, mode: Mode, known: dict) -> RunResult:

    # 1. read: catalogue, reading, dossier, the ledger's staged passes (old app, unchanged)
    catalogue = catalogue_job(job_folder, cache, _workers())
    reading = read_job(catalogue, cache_dir=cache)
    old_header, header_flags = job_header(catalogue, reading, dt.date.today())
    quote = _safe_filename(old_header.quote_number)
    dossier = build_dossier(catalogue, reading, cache)
    known.update(quote=quote, job=str(dossier.job_name or ""))
    _save_running(out, known["quote"], known["job"], known["decisions"])
    judge = Judge(cache, mode=mode, job=dossier.job_name)
    judge.retire_requests(dossier.sources)
    ledger_file = out / f"{quote} Ledger.json"
    ledger = read_ledger(judge, dossier, catalogue, save_to=ledger_file)
    print(f"Wrote {ledger_file}")
    if not ledger.complete:
        return RunResult("waiting", "read", waiting=judge.waiting,
                         messages=(f"Reading stopped at the {ledger.stopped_at} pass: waiting for its answer.",))

    # 1b. the takeoff pass: one whole-job AI step returns the register (sheet classes, unit rows). Stage 1 stores it on
    # the Job; no count reads it.
    known["stage"] = "takeoff"
    playbook = load_playbook()
    transport = (ai.ChatTransport(cache, job=dossier.job_name) if mode == "chat" else ai.ApiTransport(cache))
    try:
        register = takeoff.take_off(ledger, catalogue, reading, dossier, playbook, transport)
    except ai.NoAnswer as missing:
        return RunResult("waiting", "takeoff", waiting=transport.waiting,
                         messages=(_not_answered("Takeoff", missing),))
    takeoff_file = out / f"{quote} Takeoff.json"
    if takeoff.save(register, takeoff_file):
        print(f"Wrote {takeoff_file}")

    # 2. plan, then the counts cross-check
    known["stage"] = "count"
    # takeoff Stage 2 (T-007): the register binds the counts and the blocks (`plan_job(register=...)`)
    job = plan_job(ledger, catalogue, dossier, playbook, register=register,
                   typicals=getattr(reading, "typicals", ()) or ())
    job = dataclasses.replace(job, header=Header(
        quote_number=old_header.quote_number, reference=old_header.reference, mep_engineer=old_header.mep_engineer,
        based_on=tuple(old_header.based_on), date=old_header.date.isoformat(), to=old_header.to),
        # the header's flags (a cover-page value left as *** or as a placeholder) stay open questions beside the
        # planner's, so the review page asks for them (T-005c review F2): the red mark alone is easy to miss
        questions=tuple(dict.fromkeys((*job.questions, *header_flags))),
        # the sheets the ledger's sources name, once: a known sheet in a where and after a sheet word (FINAL-J) for
        # every writer, the validator and the renderer alike, so a writer's exact copy of its evidence's where is
        # never refused
        source_sheets=source_sheets(ledger.sources, getattr(dossier, "sources", None) or {}))
    job = takeoff.attach(job, register)
    # the devices counted on sheets whose units do not count (thermostats on a demolition plan) are set aside too
    job = takeoff.attach_device_set_asides(job, getattr(reading, "devices", ()) or (),
                                           getattr(dossier, "sheet_pages", None) or {})
    job = attach_demolition(job)    # T-G1: the Demolition Scope from the register's units
    asked = transport.waiting
    job = cross_check(job, catalogue, cache, transport=transport)
    job_file = out / f"{quote} Job.json"

    def save(current: Job) -> None:
        job_file.write_text(current.to_json(), encoding="utf-8")

    # a count question refused with no answer to wait for stops the run here, in its own words: the systems are
    # not written without that sheet's count (beside any other sheet still waiting for its answer)
    count_stops = tuple(dict.fromkeys(_stopped(s) for s in getattr(transport, "count_stops", None) or ()))
    if count_stops or transport.waiting > asked:
        save(job)
        waits = ((f"Plan counts: {transport.waiting - asked} sheet(s) wait for the vision count.",)
                 if transport.waiting > asked else ())
        return RunResult("waiting", "count", waiting=transport.waiting, job_file=job_file,
                         messages=(*count_stops, *waits))

    # 3. write every system (all are asked before stopping for answers)
    known["stage"] = "write"
    # with its facts checklist (T-005d) and, first, its takeoff register (takeoff Task 2.5)
    evidence = {s.key: ai.system_evidence(s, dossier, ledger, register=takeoff.register_text(
        job, s, ledger, devices=getattr(reading, "devices", ()) or ())) for s in job.systems}
    # the front end is written like a system (HP 22): its own evidence, from the passages the planner cited for it
    taken = {s.key for s in job.systems}
    front_evidence = (ai.front_end_evidence(job.front_end, dossier, taken, ledger) if job.front_end is not None
                      else "")
    # I, one set for every writer and the revise: every id of the job and of every system's evidence (the front
    # end's too). A ref may cite only its system's evidence, so the final job's ids (the validator's and the
    # renderer's I) are in it, and a text one writer accepts is never an issued id once a later system cites it.
    evidence_ids = sorted(set().union(ai_evidence.cited_ids(front_evidence),
                                      *(ai_evidence.cited_ids(e) for e in evidence.values())))

    def issued(current: Job) -> tuple[str, ...]:
        return tuple(dict.fromkeys([*job_ids(current), *evidence_ids]))

    # K, the sheet numbers the planner's wheres name (after the counts cross-check, whose refs carry sheets), worked
    # out per call like I: the skeleton's refs win over every answer, so the writers all get the same K, but an
    # estimator's decision (a system deleted, a family count changed) can take planner refs out of the job, so the
    # decision rewrite and the revise get the K of the job they write into: the validator's and the renderer's K.
    def sheets(current: Job) -> tuple[str, ...]:
        return tuple(sorted(job_sheets(current)))

    # the job's source sheets (`Job.source_sheets`, set once above), passed beside K so the intake reads them as the
    # validator and the renderer do (`SourceIds.of_job`): a sheet in a where and after a sheet word only (FINAL-J)
    def source(current: Job) -> tuple[str, ...]:
        return tuple(current.source_sheets)

    pending: list[str] = []
    for system in job.systems:
        try:
            job = job.with_system(flag_written_devices(
                ai.write_system(system, evidence[system.key], playbook, transport, tags=job_tags(job),
                                ids=issued(job), sheets=sheets(job), source_sheets=source(job))))
        except ai.NoAnswer as missing:
            pending.append(_not_answered(system.name, missing))
    if job.front_end is not None:
        try:
            job = dataclasses.replace(job, front_end=ai.write_front_end(
                job.front_end, front_evidence, playbook, transport, tags=job_tags(job), ids=issued(job),
                sheets=sheets(job), source_sheets=source(job), taken=taken))
        except ai.NoAnswer as missing:
            pending.append(_not_answered(ai.FRONT_END_NAME, missing))
        else:
            job = _asked_about_front_end(job)
    save(job)
    if pending:
        return RunResult("waiting", "write", waiting=transport.waiting, job_file=job_file, messages=tuple(pending))

    # 4. the estimator's decisions. A device accept, change or delete is applied to the written devices and
    # the writer is not asked again: it would number devices from d1 and a later apply would hit the wrong one.
    # A family-count change is the only reason to ask again, and the devices already written are kept.
    # A malformed file stops the run in words. The page saves only its own answers, so the run keeps every save in
    # the history (bms.review.merge_decisions) and applies them all: a second save never undoes the first in silence.
    known["stage"] = "decisions"
    try:
        earlier = load_history(out)
        saved = load_decisions(out)
        history = merge_decisions(earlier, saved, job=job)
    except ModelError as error:
        return RunResult("waiting", "decisions", waiting=0, job_file=job_file, messages=(_stopped(error),))
    notes: tuple[str, ...] = ()
    # a first save has no history yet, which is normal: the note only when an earlier run saved one (its run state)
    if saved and not (out / DECISIONS_HISTORY).is_file() and known.get("decisions", 0) > 0:
        notes = (f"Decisions: no {DECISIONS_HISTORY} was found, so the decisions start from {DECISIONS_FILE} "
                 "alone; if an earlier history was deleted, the decisions of earlier saves are not applied.",)
    # decisions.json deleted to start over: the history still holds every earlier save and is still applied
    if earlier and not (out / DECISIONS_FILE).is_file():
        n = len(earlier)
        notes = (f"Decisions: no {DECISIONS_FILE} was found, but the {n} decision{'s' if n != 1 else ''} kept in "
                 f"{DECISIONS_HISTORY} {'are' if n != 1 else 'is'} still applied; to start over, delete both "
                 f"{DECISIONS_FILE} and {DECISIONS_HISTORY}.",)
    if history:
        stop = _save_history(out, history, job_file)
        if stop is not None:
            return stop
    # always, so a start-over (both files deleted) counts from 0 again and its first save is no lost history
    known["decisions"] = len(history)
    decisions = [entry.decision for entry in history]
    latest = max((entry.round for entry in history), default=0)
    decided_from = job
    copies = copies_seen(history)       # a twin's delete never takes the only copy (bms.review.apply_decisions)
    job = apply_seen(job, decisions, copies)
    # the deletes applied to the written job; after a count rewrite they are applied again by the saved line only
    deletes = [d for d in decisions if d.action == "delete" and not _matches_nothing(decided_from, d)
               and not held_back(decided_from, d, copies)]
    for key in _changed_system_keys(decided_from, job):
        system = job.system(key)
        if not _families_changed(decided_from, key, job):
            continue
        try:
            # a line the answer left at the old count still gets the new one; a line whose count the estimator
            # typed keeps it (AI-1)
            typed = _typed_counts(decisions, key, decided_from)
            # asked from the written system with only the count changes applied, so the question (its cache key)
            # depends on the count change alone: a later rename, delete or accept never asks the writer again
            # (RUN-2). The rewrite keeps the written lines' ids and words, so the system's line decisions are
            # applied to it again after (`_reapplied`), then the deletes by their saved line as before.
            counts = [d for d in decisions if _counts_changed([d], key)]
            base = apply_decisions(decided_from, counts).system(key)
            asked = ai.rewrite_for_count(
                base, f"{evidence[key]}\n\n{_count_note(decisions, key)}", playbook, transport,
                tags=job_tags(job), ids=issued(job), sheets=sheets(job), source_sheets=source(job))
            asked = _reapplied(job, base, asked, [d for d in decisions if d.system_key == key
                                                  and d.device_id is not None and d.action != "accept"], copies)
            rewritten = flag_written_devices(_carry_new_counts(decided_from.system(key), system, asked, typed))
            standing = _standing_accepts(history, key, decided_from)    # accepted after it saw the new count
            if standing:
                rewritten = apply_decisions(job.with_system(rewritten), standing).system(key)
            # the rewrite is asked from the evidence and may write a deleted line again; the rewrite numbers lines
            # again, so the delete is applied by its saved content (`was`) only, never by id
            job = job.with_system(keep_deleted(job, rewritten, deletes))

        except ai.NoAnswer as missing:
            pending.append(_not_answered(system.name, missing))
    save(job)
    if pending:
        return RunResult("waiting", "write", waiting=transport.waiting, job_file=job_file,
                         messages=(*notes, *pending))

    # validate and QC
    known["stage"] = "qc"
    findings = validate(job, playbook)
    index = ai.evidence_index(dossier)
    try:
        qc = ai.qc_job(job, index, playbook, transport)
    except ai.NoAnswer as missing:
        save(job)
        return RunResult("waiting", "qc", waiting=transport.waiting, job_file=job_file, findings=tuple(findings),
                         messages=(*notes, _not_answered("QC", missing)))

    # 5. revise (must_fix only, one round), validate again
    # an estimator's change that prints an issued id is kept as written: its id finding is not the revise's to fix
    # (the revise would write the line back under its old name); it gets its own card below
    known["stage"] = "revise"
    estimators = {(d.system_key, device_id) for d, device_id, _ in _ids_in_changes(job, decisions)}
    must_fix = [f for f in [*findings, *qc] if f.severity == "must_fix"
                and not (f.rule == RULE["ids"] and (f.system_key, f.device_id) in estimators)]
    written = job
    for key in dict.fromkeys(f.system_key for f in must_fix if f.system_key):
        system = job.system(key)
        try:
            job = job.with_system(_revised(system, [f for f in must_fix if f.system_key == key],
                                            evidence[key], playbook, transport, job,
                                            decisions=_standing_accepts(history, key, decided_from),
                                            ids=issued(job), sheets=sheets(job), source_sheets=source(job),
                                            hold_counts=_held_counts(decisions, key),
                                            typed=_typed_counts(decisions, key, decided_from)))

        except ai.NoAnswer as missing:
            pending.append(_not_answered(system.name, missing))
    # the front end is revised like a system (HP 22): its must_fix findings (they carry the whole job's key "")
    front_findings = [f for f in must_fix if ai.is_front_end_finding(f, job.front_end, playbook)]
    if front_findings:
        try:
            job = dataclasses.replace(job, front_end=ai.revise_front_end(
                job.front_end, front_findings, front_evidence, playbook, transport, tags=job_tags(job),
                ids=issued(job), sheets=sheets(job), source_sheets=source(job), taken=taken))
        except ai.NoAnswer as missing:
            pending.append(_not_answered(ai.FRONT_END_NAME, missing))
    # a device decision made on the page's (revised) wording that matched nothing the writer wrote is applied to
    # the revised job; one decision is never applied twice
    # (an accept a count change overrules is not applied late either)
    late = [d for d in decisions if _matches_nothing(decided_from, d)
            and (d.action != "accept" or d in _standing_accepts(history, d.system_key, decided_from))]
    early = [d for d in decisions if not _matches_nothing(decided_from, d)]
    revised_job = job
    job = apply_seen(job, late, copies)

    def took_effect(decision: Decision) -> bool:
        if not _matches_nothing(decided_from, decision):
            return not held_back(decided_from, decision, copies)
        return (decision in late and not _matches_nothing(revised_job, decision)
                and not held_back(revised_job, decision, copies))

    # a delete from an earlier save that took effect on some run and whose line is now in no job did its work: it
    # makes no card while its system is as the last finished run left it. When the system changed since (it was
    # asked again), the line may have come back re-worded: a check card asks the estimator to check the system.
    # A change or an accept that matches nothing, and a delete that never took effect, keep the card of every
    # decision ("could not be applied").
    quiet = [entry for entry in history if entry.round < latest and entry.took_effect
             and entry.decision.action == "delete" and entry.decision in late
             and _matches_nothing(revised_job, entry.decision)]
    checked_late = [d for d in late if not any(d == entry.decision for entry in quiet)]
    rechecks = [_check_this_system(entry.decision) for entry in quiet
                if entry.settled != system_digest(job, entry.decision.system_key)]
    # `took_effect` is saved now; `settled` (the system as this run leaves it) only once every output is written
    # (step 6): a run that stops or crashes before the end keeps the old digest, so the check card is not lost
    history = [dataclasses.replace(entry, took_effect=entry.took_effect or took_effect(entry.decision))
               for entry in history]
    if history:
        stop = _save_history(out, history, job_file)
        if stop is not None:
            save(job)
            return dataclasses.replace(stop, messages=(*notes, *stop.messages))
    save(job)
    if pending:
        return RunResult("waiting", "revise", waiting=transport.waiting, job_file=job_file,
                         messages=(*notes, *pending))
    findings = validate(job, playbook)
    open_qc = [f for f in qc if f.severity != "must_fix" or _untouched(f, written, job, playbook)]
    # the revised job's quotes, checked again: a revise that changed a line closes its QC finding, never the check
    known_qc = {(f.rule, f.system_key, f.device_id, f.what) for f in open_qc}
    open_qc += [f for f in ai.quote_findings(job, index, playbook)
                if (f.rule, f.system_key, f.device_id, f.what) not in known_qc]
    id_cards = [_id_change_card(*found) for found in _ids_in_changes(job, decisions)]
    # the coverage gate, once, on the final job: every write, revise and decision is in it (the late decisions too), and
    # nothing changes it after this. It only reports, so it joins the open findings and changes nothing else
    uncited, coverage_notes = _coverage_findings(job, ledger, dossier)
    all_findings = tuple([*id_cards, *findings, *open_qc, *unhonored_decisions(decided_from, early, job, copies=copies),
                          *unhonored_decisions(revised_job, checked_late, job, copies=copies), *rechecks, *uncited])

    # 6. the review page, the render and the three documents
    known["stage"] = "render"
    manifest = publish_proofs(job, cache, out)
    if manifest is not None:
        print(f"Wrote {manifest}")
    # T-005e: off-hours work and prevailing wage the documents call for: findings for the review page and the Evidence
    # Package, and red lines in the proposal and the price sheet (with_labor below)
    conditions = labor_conditions(getattr(catalogue, "overview", None))
    all_findings = (*all_findings, *labor_findings(conditions))
    review = review_page(job, all_findings, out)
    print(f"Wrote {review}")
    draft = render(job, playbook)
    draft = with_labor(draft, conditions)
    # T-005e addendum: the Master Template's warranty lines in the front end, when the specification states it
    draft = with_warranty(draft, getattr(catalogue, "overview", None))
    printed = {line.device_id: line.text for line in draft.lines if line.device_id}
    evidence_file = write_evidence(out / f"{quote} Evidence Package.xlsx", catalogue, reading, ledger, job,
                                   all_findings, printed)
    print(f"Wrote {evidence_file}")
    proposal, sheet = _build(draft.scope, PROPOSAL_TEMPLATE, WORKUP_TEMPLATE, PriceBook.load(PRICE_BOOK, ALIASES), out)
    print(f"Wrote {proposal}")
    print(f"Wrote {sheet}")
    if history:
        settled = [dataclasses.replace(entry, settled=system_digest(job, entry.decision.system_key))
                   for entry in history]
        stop = _save_history(out, settled, job_file)
        if stop is not None:
            return dataclasses.replace(stop, messages=(*notes, *stop.messages))
    return RunResult("done", "done", job_file=job_file, findings=all_findings, review=review, proposal=proposal,
                     price_sheet=sheet, evidence=evidence_file, messages=(*notes, *coverage_notes))
