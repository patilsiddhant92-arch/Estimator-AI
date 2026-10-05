"""Review of record, source-id detector gaps (lead/detector-gaps): the run's K after the estimator's decisions.
Invented job folder only (the one `test_run` builds).

The run computes K (`citations.job_sheets`) once, before the writers, and gives that same set to the decision
rewrite and the revise. A decision can take planner refs out of the job (it deletes a system, or changes a family's
count to the estimator's own), so the validator's and the renderer's K shrink. The decision rewrite and the revise
must be given the K of the job they write into, or a text their intake accepts as a sheet is must_fix and cut at
render ("Damper per S901" prints "Damper per").
"""
from __future__ import annotations

import dataclasses
import json

import pytest

from test_run import _reach, answer_all, job_folder  # noqa: F401  (job_folder is a fixture)

SHEET_REF = {"source_id": "Q901", "quote": "invented", "where": "Sheet S901, Structural.pdf page 3"}


@pytest.mark.xfail(strict=True, reason="review of record detector gaps, finding R-1: run.py computes K once; a "
                                       "decision that takes a planner's sheet ref out of the job leaves that sheet "
                                       "in the decision rewrite's and the revise's K")
def test_the_decision_rewrite_and_the_revise_are_given_the_sheets_of_the_job_after_the_decisions(job_folder, tmp_path,
                                                                                                monkeypatch):
    from bms import ai, citations, run
    from bms.model import Finding, Job, Ref
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    real_cross_check = run.cross_check

    def cross_check(job, *args, **kwargs):          # the first family's count also cites a ref naming sheet S901
        job = real_cross_check(job, *args, **kwargs)
        system = job.systems[0]
        family = system.families[0]
        count = dataclasses.replace(family.count, sources=family.count.sources + (Ref(**SHEET_REF),))
        return job.with_system(dataclasses.replace(
            system, families=(dataclasses.replace(family, count=count),) + system.families[1:]))

    written, rewritten, revised = [], [], []
    real_write = ai.write_system

    def spy(system, evidence, playbook, transport, **kw):
        (rewritten if "The estimator's decisions" in evidence else written).append(kw.get("sheets"))
        return real_write(system, evidence, playbook, transport, **kw)

    def revise_spy(system, findings, evidence, playbook, transport, **kw):
        revised.append(kw.get("sheets"))
        return system

    def must_fix(job, playbook):
        return [Finding("Every line cites this job", s.key, None, "must_fix", "invented", "invented")
                for s in job.systems[:1]]

    monkeypatch.setattr(run, "cross_check", cross_check)
    monkeypatch.setattr(run.ai, "write_system", spy)
    out, cache = tmp_path / "out", tmp_path / "cache"
    first = _reach(job_folder, out, cache, "write")
    assert first.stage == "write"
    planned = Job.from_json(first.job_file.read_text(encoding="utf-8"))
    assert "S901" in citations.job_sheets(planned)
    system = planned.systems[0]
    family = system.families[0]
    estimators = dataclasses.replace(family.count, sources=tuple(r for r in family.count.sources
                                                                 if r.source_id != "Q901"))
    (out / "decisions.json").write_text(json.dumps([{
        "system_key": system.key, "action": "change", "family_name": family.name, "count": estimators.to_dict(),
        "reason": "invented"}]), encoding="utf-8")
    assert answer_all(cache)
    monkeypatch.setattr(run.ai, "revise_system", revise_spy)
    monkeypatch.setattr(run, "validate", must_fix)
    result = _reach(job_folder, out, cache, "never")
    job = Job.from_json(result.job_file.read_text(encoding="utf-8"))
    assert written and all("S901" in (sheets or ()) for sheets in written), written
    assert "S901" not in citations.job_sheets(job)                    # the validator's and the renderer's K
    assert rewritten and revised, (rewritten, revised)
    for sheets in (*rewritten, *revised):
        assert set(sheets) == set(citations.job_sheets(job)), sheets
