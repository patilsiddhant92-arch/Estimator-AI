"""FINAL-H (1): the known sheets of a job (K, `job_sheets`) also hold every sheet number a ledger source's where names
(`Job.source_sheets`), so a writer copying the evidence's own where exactly ("S201, Structural.pdf page 3", S201 also
an issued id) is accepted at intake, silent at validate and printed at render alike; an issued id no source's where
names as a sheet is still refused, must_fix and cut. Invented fixture and invented job folder only."""
from __future__ import annotations

import json
from dataclasses import replace

from bms import ai, run
from bms.citations import job_ids, job_sheets, job_tags, source_sheets
from bms.model import Job, json_schema
from bms.validate import RULE, validate

from test_review_final3 import SAMPLE, _job, _prints, _with_note, _with_other_count
from test_run import answer_all, job_folder  # noqa: F401  (job_folder is a fixture)

REFUSED = ("refused", "must_fix", "cut")
ACCEPTED = ("accepted", "none", "prints")


def _verdicts(job: Job, kind: str, probe: str, token: str) -> tuple[str, str, str]:
    """(intake, validator, render) on `job` with `probe` as EF's note (text) or a typed where (where)."""
    job = _with_note(job, probe) if kind == "text" else _with_other_count(job, probe)
    system = job.system("EF")
    written, _ = ai._check_system(system.to_dict(), system, None, frozenset(job_ids(job)), (), (), [],
                                  job_tags(job), job_ids(job), tuple(job_sheets(job)))
    severities = [f.severity for f in validate(job, SAMPLE) if f.rule == RULE["ids"] and f.system_key == "EF"]
    return ("refused" if written is None else "accepted", "must_fix" if "must_fix" in severities else "none",
            "prints" if _prints(job, token) else "cut")


def test_the_sheets_of_the_ledger_sources_wheres():
    sources = {"S9": "S201, Structural.pdf page 3 (sheet title)", "S10": "M-101, Drawings.pdf page 2",
               "S11": "Sheet C101, Civil.pdf page 1", "S12": "S12, Structural.pdf page 4",   # its own id: not trusted
               "F1": "equipment counts for EF (schedules and plans)", "I2": "S300.png"}
    assert source_sheets(sources) == ("C101", "S201")
    assert source_sheets(sources, {"S13": "s202, Structural.pdf page 5", "S9": "S201, Structural.pdf page 3"}) \
        == ("C101", "S201", "S202")
    assert source_sheets() == ()


def test_job_sheets_hold_the_source_sheets():
    job = replace(_job(), source_sheets=("S201",))
    assert "S201" in job_sheets(job)
    assert "S201" not in job_sheets(_job())


def test_an_exact_copy_of_a_sources_where_passes_intake_validate_and_render_alike():
    """S201 is an issued id of the job and the sheet a ledger source's where names: the writer's copy of that where
    is accepted, silent and printed; S141, issued and the sheet of no source, is still refused, must_fix and cut."""
    known = replace(_job(), source_sheets=("S201",))
    assert _verdicts(known, "where", "S201, Structural.pdf page 3", "S201") == ACCEPTED
    assert _verdicts(known, "where", "Sheet S201, Structural.pdf page 3", "S201") == ACCEPTED
    assert _verdicts(known, "where", "S141, Structural.pdf page 3", "S141") == REFUSED
    assert _verdicts(known, "text", "Valves per sheet S141.", "S141") == REFUSED
    # one K for client text too: a sheet number of the job reads as a sheet wherever it stands
    assert _verdicts(known, "text", "Valves per sheet S201.", "S201") == ACCEPTED
    # without the source's sheet the same copy is refused, as before
    assert _verdicts(_job(), "where", "S201, Structural.pdf page 3", "S201") == REFUSED


def test_the_source_sheets_round_trip_and_an_old_job_still_loads():
    job = replace(_job(), source_sheets=("C101", "S201"))
    data = json.loads(job.to_json())
    assert data["source_sheets"] == ["C101", "S201"]
    assert Job.from_json(job.to_json()) == job
    old = {k: v for k, v in data.items() if k != "source_sheets"}
    assert Job.from_dict(old).source_sheets == ()                  # a Job saved before the field still loads
    prop = json_schema(Job)["properties"]["source_sheets"]
    assert prop["type"] == "array" and prop["items"]["type"] == "string"


def test_the_run_carries_the_ledger_sources_sheets_on_the_job(job_folder, tmp_path, monkeypatch):  # noqa: F811
    """The run sets `source_sheets` from the ledger's sources once, after the plan, so Job.json carries it."""
    real = run.read_ledger

    def reading(*args, **kwargs):
        ledger = real(*args, **kwargs)
        ledger.sources["S900"] = "S201, Structural.pdf page 3"
        return ledger

    monkeypatch.setattr(run, "read_ledger", reading)
    out, cache = tmp_path / "out", tmp_path / "cache"
    for _ in range(25):
        result = run.estimate(job_folder, out, cache, "chat")
        if result.job_file is not None and result.job_file.exists():
            break
        assert result.status == "waiting" and answer_all(cache), result.messages
    else:
        raise AssertionError("the run never saved a job")
    saved = Job.from_json(result.job_file.read_text(encoding="utf-8"))
    assert "S201" in saved.source_sheets
    assert "S201" in job_sheets(saved)
