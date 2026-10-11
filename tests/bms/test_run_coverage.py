"""The coverage gate in the run (chat mode, an invented job): a fact the ledger read that nothing in the final job cites
is one `check` finding on the review page (the group "Not cited in the job") and on the Evidence Package "Findings" tab;
a run in which everything is cited has none. The gate only reports: it never changes the Job, never blocks the run and
never changes the exit code."""
from __future__ import annotations

import argparse
import re

import openpyxl
import pytest
from estimator.ledger.facts import Ledger

from bms import run
from bms.__main__ import _estimate as cli_estimate
from bms.coverage import SCOPE_KINDS
from bms.review import NOT_CITED_GROUP
from test_run import _reach, job_folder  # noqa: F401  (job_folder is a fixture)

PLACE = "M-999, Invented.pdf page 9"
QUOTE = "ZZGIZMO-1 is shown here"


@pytest.fixture
def one_uncited_fact(monkeypatch):
    """The ledger the run reads holds one more fact: a device the drawings show and no planner step reads, so nothing in
    the job cites it. Its source is an invented one, so the place it prints is known."""
    real = run.read_ledger

    def read(judge, dossier, catalogue, save_to=None, **kw):
        ledger = real(judge, dossier, catalogue, save_to=save_to, **kw)
        ledger.sources["S900"] = PLACE
        ledger.add("device", "ZZGIZMO", "Invented gizmo", "S900", QUOTE, "seed")
        return ledger
    monkeypatch.setattr(run, "read_ledger", read)


def _done(job_folder, tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out, cache = tmp_path / "out", tmp_path / "cache"
    result = _reach(job_folder, out, cache, "never")
    assert result.status == "done", result
    return result, out, cache


def _coverage(result):
    return [f for f in result.findings if f.rule == "coverage"]


def _evidence_rows(result) -> list[list]:
    book = openpyxl.load_workbook(result.evidence)
    return [[c.value for c in row] for row in book["Findings"].iter_rows(min_row=2)]


def test_a_fact_nothing_cites_is_one_finding_on_the_review_page_and_in_the_evidence_package(
        job_folder, tmp_path, monkeypatch, one_uncited_fact):
    result, _, _ = _done(job_folder, tmp_path, monkeypatch)
    (finding,) = _coverage(result)
    assert (finding.severity, finding.system_key, finding.device_id) == ("check", "", None)
    assert "ZZGIZMO" in finding.what and PLACE in finding.what and QUOTE in finding.what

    page = result.review.read_text(encoding="utf-8")
    group = re.search(r'<section class="card" id="not-cited" data-group="not-cited">.*?</section>', page, re.S).group(0)
    assert f"<h2>{NOT_CITED_GROUP}</h2>" in group and group.count("<li>") == 1
    assert PLACE in group and QUOTE in group

    rows = [row for row in _evidence_rows(result) if row[0] == "coverage"]
    assert len(rows) == 1
    rule, system, device, severity, what, fix = rows[0]
    assert (system, device, severity) == ("Whole job", None, "check") and what == finding.what and fix == finding.fix


def test_a_run_where_everything_is_cited_has_no_coverage_finding(job_folder, tmp_path, monkeypatch):
    result, out, _ = _done(job_folder, tmp_path, monkeypatch)
    ledger = Ledger.load(next(out.glob("* Ledger.json")))
    assert [f for f in ledger.facts.values() if f.kind in SCOPE_KINDS]      # the gate had facts to look at
    assert _coverage(result) == []
    assert NOT_CITED_GROUP not in result.review.read_text(encoding="utf-8")
    assert not [row for row in _evidence_rows(result) if row[0] == "coverage"]


def test_the_gate_is_called_once_on_the_final_job_and_changes_nothing(job_folder, tmp_path, monkeypatch,
                                                                       one_uncited_fact):
    real, seen = run.coverage, []

    def spy(job, ledger, dossier=None):
        before = job.to_json()
        found = real(job, ledger, dossier)
        assert job.to_json() == before                     # the gate left the job as it was
        seen.append(before)
        return found
    monkeypatch.setattr(run, "coverage", spy)
    result, _, _ = _done(job_folder, tmp_path, monkeypatch)
    assert len(seen) == 1
    assert result.job_file.read_text(encoding="utf-8") == seen[0]       # the saved job is the job the gate was given


def test_the_gate_leaves_the_exit_code_alone(job_folder, tmp_path, monkeypatch, one_uncited_fact, capsys):
    _, out, cache = _done(job_folder, tmp_path, monkeypatch)
    again = argparse.Namespace(job=job_folder, out=out, cache=cache, mode="chat")
    assert cli_estimate(again) == 0                              # done, with a coverage finding on the page
    assert NOT_CITED_GROUP in (out / "Review.html").read_text(encoding="utf-8")
    assert "Coverage" not in capsys.readouterr().out             # and nothing to report about the gate itself


def test_a_fault_in_the_gate_never_blocks_the_run(job_folder, tmp_path, monkeypatch):
    def broken(job, ledger, dossier=None):
        raise RuntimeError("invented fault")
    monkeypatch.setattr(run, "coverage", broken)
    result, _, _ = _done(job_folder, tmp_path, monkeypatch)
    assert result.proposal.exists() and result.review.exists() and result.evidence.exists()
    assert _coverage(result) == []
    (said,) = [m for m in result.messages if "Coverage" in m]
    assert "invented fault" in said and "could not run" in said


def test_coverage_is_a_code_rule_and_no_playbook_rule_is_needed():
    """Like "decision not honored", the gate's rule names no rule of rules.md: nothing in the code demands one, and the
    repo's Playbook lints clean without it. (A Finding written as `Finding("coverage", ...)` would make the linter demand
    a rule, so the gate builds its Finding with the rule as a keyword.)"""
    from bms.playbook import DEFAULT_ROOT
    from bms.playbook_lint import lint_playbook, referenced_rule_names
    assert "coverage" not in referenced_rule_names()
    assert lint_playbook(DEFAULT_ROOT, referenced_rule_names()) == []
