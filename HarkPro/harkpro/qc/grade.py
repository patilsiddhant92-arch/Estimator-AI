"""Recall against an estimator's list of known misses (kept OUTSIDE the repo for a real job).

`known` is a JSON list of {"id", "label", "patterns": [regex, ...]}. A miss is *raised* when a thread's question,
critique or proposed line matches any pattern, and *fixed* when a line of the revised scope (Job.qc.json) matches.
Threads matching no known miss are listed as `other` for the estimator to sort into real finds and false alarms.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import scope as sc


def _thread_text(t: dict) -> str:
    p = t.get("proposed") or {}
    return " ".join([t.get("question", ""), t.get("critique", ""), p.get("text", "")])


def grade(threads: list[dict], job: dict, known: list[dict], original: dict | None = None) -> dict:
    lines = [sc.printed(d) for _, d in sc.devices(job)]
    before = [sc.printed(d) for _, d in sc.devices(original)] if original else []
    rows, matched = [], set()
    for k in known:
        rx = [re.compile(p, re.I) for p in k.get("patterns") or []]
        hit = [t["id"] for t in threads if any(r.search(_thread_text(t)) for r in rx)]
        matched |= set(hit)
        rows.append({"id": k.get("id"), "label": k.get("label"), "raised_by": hit, "raised": bool(hit),
                     "fixed_in_scope": [l for l in lines if any(r.search(l) for r in rx)],
                     "already_in_writer_scope": [l for l in before if any(r.search(l) for r in rx)]})
    other = [{"id": t["id"], "kind": t.get("kind"), "severity": t.get("severity"), "status": t.get("status"),
              "critique": t.get("critique")} for t in threads if t["id"] not in matched]
    raised = sum(r["raised"] for r in rows)
    return {"recall": f"{raised}/{len(rows)}", "known": rows, "other": other}


def grade_folder(out: str | Path, known_path: str | Path, original_job: str | Path | None = None) -> dict:
    out = Path(out)
    threads = json.loads((out / "threads.json").read_text(encoding="utf-8"))
    job = json.loads((out / "Job.qc.json").read_text(encoding="utf-8"))
    known = json.loads(Path(known_path).read_text(encoding="utf-8"))
    original = json.loads(Path(original_job).read_text(encoding="utf-8")) if original_job else None
    return grade(threads, job, known, original)
