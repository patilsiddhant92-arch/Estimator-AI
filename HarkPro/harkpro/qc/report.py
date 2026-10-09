"""The QC report, the must-fix list for the app's revise step, the estimator questions and the revised scope.

Files (all in the run's out folder):
- `QC_Report.md`        the summary, the coverage of every evidence item, every thread with its history;
- `findings.json`       open and escalated threads in the app's Finding shape {rule, system_key, device_id,
                        severity, what, fix} (`bms.model.Finding`): unresolved must-fix threads are "must_fix" (feed
                        them to the revise step), escalated ones "check";
- `estimator_questions.json`  what only the estimator can settle;
- `threads.json`, `coverage.json`  the raw state;
- `Job.qc.json`         the scope with every revision the writer made in the loop.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from . import scope as sc


def _dump(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def outcome(t) -> str:
    if t.status == "resolved":
        last_writer = next((h["event"] for h in reversed(t.history) if h["by"] == "writer"), None)
        return {"revise": "fixed by revision", "justify": "writer justified",
                "estimator_question": "resolved"}.get(last_writer, "resolved")
    if t.status == "escalated":
        return "estimator question"
    return "unresolved"


def findings(state) -> list[dict]:
    out = []
    for t in state.threads.values():
        if t.status == "resolved":
            continue
        fix = t.proposed.get("text") if t.proposed else ""
        last = next((h.get("text") for h in reversed(t.history) if h.get("text")), "")
        out.append({"rule": f"Independent QC: {t.kind}", "system_key": "" if t.system_key == sc.FE else t.system_key,
                    "device_id": t.device_id,
                    "severity": "must_fix" if t.status == "open" and t.severity == "must_fix" else "check",
                    "what": t.critique, "fix": fix or last or t.question})
    return out


def questions(state) -> list[dict]:
    out = []
    for t in state.threads.values():
        if t.status == "escalated" or (t.status == "open"):
            asked = next((h.get("text") for h in reversed(t.history)
                          if h["by"] == "writer" and h["event"] == "estimator_question"), "") or t.question
            out.append({"thread": t.id, "system_key": t.system_key, "question": asked,
                        "why": t.critique, "status": outcome(t),
                        "evidence": [c.get("quote") for c in t.citations]})
    return out


def write_report(state, out: str | Path, rounds: int) -> dict:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    threads = list(state.threads.values())
    files = {"report": out / "QC_Report.md", "findings": out / "findings.json",
             "questions": out / "estimator_questions.json", "threads": out / "threads.json",
             "coverage": out / "coverage.json", "job": out / "Job.qc.json"}
    _dump(files["findings"], findings(state))
    _dump(files["questions"], questions(state))
    _dump(files["threads"], [t.to_dict() for t in threads])
    _dump(files["coverage"], [{"evidence_id": i.id, "text": i.text, "where": i.where,
                               **(state.items.get(i.id) or {"status": "not walked"})} for i in state.evidence])
    _dump(files["job"], state.scope)

    status = Counter((state.items.get(i.id) or {}).get("status", "not walked") for i in state.evidence)
    out_c = Counter(outcome(t) for t in threads)
    sev = Counter(t.severity for t in threads)
    ev = {i.id: i for i in state.evidence}
    L = [f"# Independent QC report: {state.scope.get('name', '')}", "",
         f"Evidence items walked: {len(state.evidence)} ({', '.join(f'{k} {v}' for k, v in sorted(status.items()))}).",
         f"Threads opened: {len(threads)} ({sev.get('must_fix', 0)} must-fix, {sev.get('check', 0)} check). "
         f"Rounds used: {state.round} of {rounds}.",
         "Outcome: " + ", ".join(f"{k} {v}" for k, v in sorted(out_c.items())) + ".", "",
         "## Must fix (unresolved)", ""]
    must = [t for t in threads if t.status == "open" and t.severity == "must_fix"]
    L += [f"- **{t.id}** [{t.system_key or 'job'}] {t.critique}" for t in must] or ["- none"]
    L += ["", "## Estimator questions", ""]
    qs = questions(state)
    L += [f"- **{q['thread']}** [{q['system_key'] or 'job'}] {q['question']}" for q in qs] or ["- none"]
    L += ["", "## Threads", ""]
    for t in threads:
        L.append(f"### {t.id} ({t.kind}, {t.severity}) [{t.system_key or 'job'}{'/' + t.device_id if t.device_id else ''}]"
                 f": {outcome(t)}")
        L.append(f"- Question: {t.question}")
        L.append(f"- Critique: {t.critique}")
        if t.proposed:
            L.append(f"- Proposed: {t.proposed.get('text')} ({t.proposed.get('line_id') or 'no template line'}; "
                     f"qty {t.proposed.get('quantity')})")
        for c in t.citations:
            item = ev.get(c.get("evidence_id"))
            where = c.get("where") or (item.where if item else "")
            L.append(f"- Evidence {c.get('evidence_id')} ({where}): \"{c.get('quote')}\"")
        for h in t.history[1:]:
            ops = "; ".join(f"{o.get('op')} {o.get('system_key')}/{(o.get('device') or {}).get('id') or o.get('device_id')}"
                            f" {sc.printed(o['device']) if o.get('device') else ''}".strip()
                            for o in h.get("operations") or [])
            L.append(f"- Round {h['round']} {h['by']} -> {h['event']}: {h.get('text', '')}" + (f" [{ops}]" if ops else ""))
        L.append("")
    L += ["## Evidence coverage", "", "| Evidence | Status | Scope lines / threads | Note |", "|---|---|---|---|"]
    for i in state.evidence:
        x = state.items.get(i.id) or {}
        refs = ", ".join((x.get("device_ids") or []) + (x.get("thread_ids") or []))
        text = i.text if len(i.text) <= 110 else i.text[:107] + "..."
        L.append(f"| {i.id} {text.replace('|', '/')} | {x.get('status', 'not walked')} | {refs} | "
                 f"{(x.get('note') or '').replace('|', '/')} |")
    files["report"].write_text("\n".join(L) + "\n", encoding="utf-8")
    return {k: str(v) for k, v in files.items()}
