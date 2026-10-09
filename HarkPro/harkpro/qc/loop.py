"""The resolve loop: critic -> writer response -> critic verdicts ... until no open must-fix remains.

    round 1   critic walks every evidence item (in parts of `batch` items), opens threads
              writer answers every open thread (revise / justify / estimator question); revisions are applied
    round 2.. critic rules on each answered thread (resolved / reopen / escalate), may open new threads
              writer answers the reopened and new threads
    ...       up to `rounds` writer rounds; a final critic verdict step judges the last answers.

The run is a pure replay of the answers on disk: every call recomputes the state from the evidence, the scope and
the answers given so far, and stops at the first request still waiting (exit 2), so it can be run again after each
answer. Nothing is written outside the out folder; the writer's Job.json is never changed in place.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import checklist as cl
from . import scope as sc
from .evidence import Item, PARTY_CONCEPTS, load_evidence
from .handoff import Handoff, Stopped, Waiting
from .schemas import CRITIC, RESPOND

PROMPTS = Path(__file__).resolve().parents[2] / "qc_prompts"


def prompt_text(name: str) -> str:
    return (PROMPTS / f"{name}.md").read_text(encoding="utf-8")


@dataclass
class Thread:
    id: str
    kind: str
    severity: str
    system_key: str
    device_id: str | None
    evidence_ids: list[str]
    question: str
    critique: str
    proposed: dict | None
    citations: list[dict]
    opened_round: int
    status: str = "open"              # open | resolved | escalated
    history: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return dict(self.__dict__)

    def brief(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k not in ("status",)}
        return d


@dataclass
class State:
    evidence: list[Item]
    scope: dict
    checklists: list[dict]
    rulings: str
    items: dict[str, dict] = field(default_factory=dict)
    threads: dict[str, Thread] = field(default_factory=dict)
    round: int = 0
    scopes: list[dict] = field(default_factory=list)

    def open(self, severity: str | None = None) -> list[Thread]:
        return [t for t in self.threads.values() if t.status == "open" and (severity is None or t.severity == severity)]


@dataclass
class Result:
    status: str                       # waiting | done | stopped
    stage: str
    waiting: list[dict] = field(default_factory=list)
    message: str = ""
    state: State | None = None
    files: dict = field(default_factory=dict)

    @property
    def exit_code(self) -> int:
        return {"waiting": 2, "done": 0}.get(self.status, 1)


# ---- inputs -------------------------------------------------------------------------------------------------------

def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def evidence_view(items: list[Item], scope: dict) -> list[dict]:
    has = sc.scope_concepts(scope)
    return [{"id": i.id, "kind": i.kind, "text": i.text, "where": i.where, "source_id": i.source_id,
             "concepts": i.concepts, "scope_has": sorted(set(i.concepts) & has),
             "scope_lacks": sorted(set(i.concepts) - has - PARTY_CONCEPTS)} for i in items]


def screen(items: list[Item]) -> tuple[list[Item], list[Item]]:
    """(walked, screened): an item whose text names no controls concept at all is screened out of the walk; the
    critic still sees it in a one-line list and may raise a thread on it."""
    walked = [i for i in items if i.concepts]
    return walked, [i for i in items if not i.concepts]


def _batches(items: list[Item], size: int) -> list[list[Item]]:
    size = max(1, size)
    return [items[n:n + size] for n in range(0, len(items), size)] or [[]]


# ---- checks on answers ----------------------------------------------------------------------------------------

def _citation_problems(cites: list[dict], ev: dict[str, Item], where: str) -> list[str]:
    out = []
    for c in cites:
        item = ev.get(c.get("evidence_id"))
        if item is None:
            out.append(f"{where}: cites unknown evidence {c.get('evidence_id')!r}")
        elif _norm(c.get("quote")) and _norm(c.get("quote")) not in _norm(item.text):
            out.append(f"{where}: the quote is not in {item.id}'s text (copy it word for word)")
        elif not _norm(c.get("quote")):
            out.append(f"{where}: empty quote")
    return out


def _thread_problems(threads: list[dict], state: State, ev: dict[str, Item], lines: dict) -> list[str]:
    out = []
    dev_ids = {d.get("id") for _, d in sc.devices(state.scope)}
    keys = {b.get("key") for b in sc.blocks(state.scope)}
    seen = set()
    for t in threads:
        tid = t.get("id")
        w = f"thread {tid}"
        if tid in seen:
            out.append(f"{w}: id given twice")
        seen.add(tid)
        out += [f"{w}: unknown evidence {e!r}" for e in t.get("evidence_ids") or [] if e not in ev]
        if t.get("device_id") and t["device_id"] not in dev_ids:
            out.append(f"{w}: no device {t['device_id']!r} in the scope")
        if t.get("system_key") and t["system_key"] not in keys and t.get("kind") not in ("missing_system", "left_out"):
            out.append(f"{w}: no block {t['system_key']!r} in the scope (use kind missing_system for a new block)")
        out += _citation_problems(t.get("citations") or [], ev, w)
        p = t.get("proposed")
        if p and p.get("line_id"):
            line = lines.get(p["line_id"])
            if line is None:
                out.append(f"{w}: proposed line_id {p['line_id']!r} is not a checklist line")
            elif not cl.template_matches(line.get("text", ""), p.get("text", "")):
                out.append(f"{w}: proposed text is not the template line {p['line_id']} "
                           f"({line.get('text')!r}) with its placeholders filled")
    return out


def check_critic_round1(answer: dict, batch: list[Item], state: State, ev: dict, lines: dict,
                        screened: set[str] = frozenset()) -> list[str]:
    out = []
    want = {i.id for i in batch}
    got = [x.get("evidence_id") for x in answer.get("items") or []]
    missing = sorted(want - set(got))
    if missing:
        out.append(f"items: no entry for {', '.join(missing[:20])}{' ...' if len(missing) > 20 else ''} "
                   f"(every evidence item needs one)")
    extra = sorted(set(got) - want - set(screened))
    if extra:
        out.append(f"items: {', '.join(extra[:10])} are not in this part")
    dups = sorted({g for g in got if got.count(g) > 1})
    if dups:
        out.append(f"items: {', '.join(dups[:10])} given more than once")
    thread_ids = {t.get("id") for t in answer.get("threads") or []}
    dev_ids = {d.get("id") for _, d in sc.devices(state.scope)}
    for x in answer.get("items") or []:
        w = f"item {x.get('evidence_id')}"
        if x.get("status") == "raised" and not x.get("thread_ids"):
            out.append(f"{w}: raised but names no thread")
        out += [f"{w}: names thread {t!r} that is not in threads" for t in x.get("thread_ids") or []
                if t not in thread_ids]
        out += [f"{w}: names device {d!r} that is not in the scope" for d in x.get("device_ids") or []
                if d not in dev_ids]
        if x.get("status") == "covered" and not (x.get("device_ids") or x.get("note")):
            out.append(f"{w}: covered but names no device and gives no note")
        if x.get("status") == "dismissed" and not x.get("note"):
            out.append(f"{w}: dismissed without a reason")
    out += _thread_problems(answer.get("threads") or [], state, ev, lines)
    if answer.get("verdicts"):
        out.append("verdicts: round 1 has no earlier threads to rule on")
    return out


def check_critic_verdicts(answer: dict, awaiting: list[Thread], state: State, ev: dict, lines: dict) -> list[str]:
    out = []
    want = {t.id for t in awaiting}
    got = [v.get("thread_id") for v in answer.get("verdicts") or []]
    if want - set(got):
        out.append(f"verdicts: none for {', '.join(sorted(want - set(got)))}")
    if set(got) - want:
        out.append(f"verdicts: {', '.join(sorted(set(got) - want))} are not threads awaiting a verdict")
    for v in answer.get("verdicts") or []:
        out += _citation_problems(v.get("citations") or [], ev, f"verdict {v.get('thread_id')}")
        if not v.get("reason"):
            out.append(f"verdict {v.get('thread_id')}: no reason")
    clash = {t.get("id") for t in answer.get("threads") or []} & set(state.threads)
    if clash:
        out.append(f"threads: ids {', '.join(sorted(clash))} are already used")
    out += _thread_problems(answer.get("threads") or [], state, ev, lines)
    if answer.get("items"):
        out.append("items: only round 1 walks the evidence")
    return out


def check_respond(answer: dict, asked: list[Thread], state: State, ev: dict) -> list[str]:
    out = []
    want = {t.id for t in asked}
    got = [r.get("thread_id") for r in answer.get("responses") or []]
    if want - set(got):
        out.append(f"responses: none for {', '.join(sorted(want - set(got)))}")
    if set(got) - want:
        out.append(f"responses: {', '.join(sorted(set(got) - want))} were not asked")
    dups = sorted({g for g in got if got.count(g) > 1})
    if dups:
        out.append(f"responses: {', '.join(dups)} answered more than once")
    scope = state.scope
    for r in answer.get("responses") or []:
        w = f"response {r.get('thread_id')}"
        if r.get("action") == "revise" and not r.get("operations"):
            out.append(f"{w}: revise gives no operations")
        if r.get("action") == "justify" and not r.get("citations"):
            out.append(f"{w}: a justification cites the evidence")
        if not r.get("text"):
            out.append(f"{w}: no text")
        out += _citation_problems(r.get("citations") or [], ev, w)
        try:
            scope = sc.apply_operations(scope, r.get("operations") or [])
        except sc.OperationError as e:
            out.append(f"{w}: {e}")
    return out


# ---- the loop -------------------------------------------------------------------------------------------------

def _add_threads(state: State, raw: list[dict], rnd: int, rename: dict | None = None) -> None:
    for t in raw:
        tid = t["id"]
        if tid in state.threads:                     # two parts of round 1 used the same id
            n = 2
            while f"{tid}.{n}" in state.threads:
                n += 1
            new = f"{tid}.{n}"
            if rename is not None:
                rename[tid] = new
            tid = new
        state.threads[tid] = Thread(tid, t["kind"], t["severity"], t.get("system_key", ""), t.get("device_id"),
                                    list(t.get("evidence_ids") or []), t.get("question", ""), t.get("critique", ""),
                                    t.get("proposed"), list(t.get("citations") or []), rnd,
                                    history=[{"round": rnd, "by": "critic", "event": "opened"}])


def _cited(state: State, threads: list[Thread]) -> list[dict]:
    ids = sorted({e for t in threads for e in t.evidence_ids} |
                 {c.get("evidence_id") for t in threads for c in t.citations})
    ev = {i.id: i for i in state.evidence}
    return evidence_view([ev[i] for i in ids if i in ev], state.scope)


def _drop_stale(hand: Handoff, keep: set[str]) -> None:
    """Remove request files this run no longer asks (an earlier prompt version, a step already answered)."""
    if hand.requests_dir.is_dir():
        for f in hand.requests_dir.glob("*.json"):
            if f.name not in keep:
                f.unlink(missing_ok=True)


def run(ledger: dict, job: dict, out: str | Path, package: str | Path | None = None, rounds: int = 3,
        batch: int = 80, lines_path=None, rulings_path=None, screen_on: bool = True) -> Result:
    out = Path(out)
    lines_data = cl.load_lines(lines_path)
    lines = cl.line_index(lines_data)
    evidence = load_evidence(ledger, package)
    # families from the scope and the walked evidence (a legend fragment such as "CH" or "B" picks no family)
    fams = cl.families_for(job, screen(evidence)[0] if screen_on else evidence, lines_data)
    state = State(evidence, job, [cl.checklist(f) for f in fams], cl.load_rulings(rulings_path))
    state.scopes.append(job)
    ev = {i.id: i for i in evidence}
    hand = Handoff(out, job=str(job.get("name") or ""))
    critic_sys, respond_sys = prompt_text("critic"), prompt_text("respond")

    def waiting(stage: str, ws: list[Waiting]) -> Result:
        info = [{"kind": json.loads(w.request.read_text(encoding="utf-8"))["kind"], "file": str(w.request),
                 "answer_file": json.loads(w.request.read_text(encoding="utf-8"))["answer_file"],
                 **({"previous_problem": w.problem} if w.problem else {})} for w in ws]
        _drop_stale(hand, {Path(w.request).name for w in ws})
        return Result("waiting", stage, info, f"{len(ws)} request(s) waiting at the {stage} step", state)

    try:
        # round 1: walk the evidence
        state.round = 1
        walked, screened = screen(evidence) if screen_on else (evidence, [])
        for i in screened:
            state.items[i.id] = {"evidence_id": i.id, "status": "screened", "device_ids": [], "thread_ids": [],
                                 "note": "no controls word in the text (word scan)"}
        screened_view = [{"id": i.id, "text": i.text[:140]} for i in screened]
        parts = _batches(walked, batch)
        answers, ws = [], []
        for n, part in enumerate(parts, 1):
            obj = {"round": 1, "part": f"{n} of {len(parts)}", "evidence": evidence_view(part, state.scope),
                   "screened": screened_view,
                   "scope": sc.view(state.scope), "checklists": state.checklists, "rulings": state.rulings,
                   "threads": []}
            try:
                answers.append((part, hand.ask("qc_critic", f"QC critic round 1 part {n}", critic_sys, obj, CRITIC,
                                               lambda a, p=part: check_critic_round1(a, p, state, ev, lines,
                                                                                 {i.id for i in screened}))))
            except Waiting as w:
                ws.append(w)
        if ws:
            return waiting("critic", ws)
        for part, a in answers:
            rename: dict = {}
            _add_threads(state, a.get("threads") or [], 1, rename)
            for x in a.get("items") or []:
                x = dict(x, thread_ids=[rename.get(t, t) for t in x.get("thread_ids") or []])
                state.items[x["evidence_id"]] = x

        for rnd in range(1, rounds + 1):
            state.round = rnd
            asked = state.open()
            if rnd > 1 and not state.open("must_fix"):
                break
            if not asked:
                break
            obj = {"round": rnd, "threads": [t.brief() for t in asked], "evidence": _cited(state, asked),
                   "scope": sc.view(state.scope), "checklists": state.checklists, "rulings": state.rulings}
            try:
                resp = hand.ask("qc_respond", f"QC writer response round {rnd}", respond_sys, obj, RESPOND,
                                lambda a, asked=asked: check_respond(a, asked, state, ev))
            except Waiting as w:
                return waiting("respond", [w])
            for r in resp.get("responses") or []:
                t = state.threads[r["thread_id"]]
                t.history.append({"round": rnd, "by": "writer", "event": r["action"], "text": r.get("text", ""),
                                  "operations": r.get("operations") or [], "citations": r.get("citations") or []})
                state.scope = sc.apply_operations(state.scope, r.get("operations") or [])
            state.scopes.append(state.scope)

            # the critic rules on the answers
            obj = {"round": rnd + 1, "threads": [t.brief() for t in asked], "evidence": _cited(state, asked),
                   "scope": sc.view(state.scope), "checklists": state.checklists, "rulings": state.rulings}
            try:
                verdict = hand.ask("qc_critic", f"QC critic round {rnd + 1} (verdicts)", critic_sys, obj, CRITIC,
                                   lambda a, asked=asked: check_critic_verdicts(a, asked, state, ev, lines))
            except Waiting as w:
                return waiting("verdict", [w])
            for v in verdict.get("verdicts") or []:
                t = state.threads[v["thread_id"]]
                t.history.append({"round": rnd + 1, "by": "critic", "event": v["verdict"], "text": v.get("reason", ""),
                                  "citations": v.get("citations") or []})
                t.status = {"resolved": "resolved", "escalate": "escalated"}.get(v["verdict"], "open")
            _add_threads(state, verdict.get("threads") or [], rnd + 1)
        state.round = min(state.round, rounds)
    except Stopped as e:
        return Result("stopped", "stopped", message=str(e), state=state)
    _drop_stale(hand, set())
    from .report import write_report
    files = write_report(state, out, rounds)
    return Result("done", "done", message="QC finished", state=state, files=files)
