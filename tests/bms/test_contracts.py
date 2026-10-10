"""Phase 0 contract tests: the Job model, its JSON Schema, the Playbook formats, the stubs' signatures and the CLI.
Every later workstream builds against these; a change here is a contract change (the controller's)."""
from __future__ import annotations

import copy
import inspect
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from bms import ai, counts, plan, render, review, run, validate
from bms.model import (ALTERNATES, CLARIFICATION_KINDS, CONTROLS, FLAGS, PARTIES, VERBS, Count, Decision, Device,
                       Finding, Job, ModelError, Ref, Served, System, json_schema, schema_errors)
from bms.playbook import Playbook, PlaybookError, load_playbook

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
SAMPLE_JOB = FIXTURES / "sample_job.json"
SAMPLE_PLAYBOOK = FIXTURES / "sample_playbook"
sys.path.insert(0, str(ROOT / "tools"))
import measure  # noqa: E402


@pytest.fixture
def raw() -> dict:
    return json.loads(SAMPLE_JOB.read_text(encoding="utf-8"))


@pytest.fixture
def job(raw) -> Job:
    return Job.from_dict(raw)


# ---- the model ------------------------------------------------------------------------------------------------

def test_enumerations_are_the_design_values():
    assert VERBS == ("Furnish and Install", "Furnish", "Furnish and Wire", "Install and Wire", "Wire")
    assert CONTROLS == ("packaged", "field", "integration", "none")
    assert FLAGS == ("none", "quantity", "ownership", "assumed")
    assert CLARIFICATION_KINDS == ("confirm", "assumed", "per_drawings", "note")
    assert ALTERNATES == ("base", "add", "deduct")
    assert PARTIES == ("AME", "Unit Mfr.", "FA", "Mechanical Contractor", "Electrical Contractor", "Others", "Owner")


def test_fixture_round_trips_losslessly(raw, job):
    assert job.to_dict() == raw
    assert Job.from_json(job.to_json()) == job


def test_fixture_exercises_the_model(job):
    assert len(job.systems) == 5
    by_key = {s.key: s for s in job.systems}
    assert by_key["RTU"].control == "packaged"
    assert any(d.furnished_by == "Unit Mfr." and d.installed_by == "AME" for d in by_key["RTU"].devices)
    assert any(d.slot == "damper_actuator" for d in by_key["EF"].devices)
    assert [f.name for f in by_key["VRF"].families] == ["Indoor Unit", "Condensing Unit", "Branch Selector"]
    assert by_key["DH"].sequence_refs
    assert by_key["CUH"].families[0].count.value is None
    devices = [d for s in job.systems for d in s.devices]
    assert all(d.refs for d in devices)
    assert any(d.assumption and d.assumption.why for d in devices)
    contradicted = [f.count for s in job.systems for f in s.families if f.count.others]
    assert contradicted and all(c.value == c.highest() for c in contradicted)
    assert {s.alternate for s in job.systems} >= {"base", "add"}


def test_a_device_needs_a_ref():
    with pytest.raises(ModelError):
        Device("x", "controller", "DDC Controller", "Furnish and Install", "AME", "AME", "AME", Count(1), ())


def test_from_dict_is_strict(raw):
    bad = copy.deepcopy(raw)
    bad["systems"][0]["devices"][0]["verb"] = "Provide"
    with pytest.raises(ModelError, match=r"systems\[0\]\.devices\[0\]\.verb"):
        Job.from_dict(bad)
    bad = copy.deepcopy(raw)
    bad["systems"][0]["devices"][0]["refs"] = []
    with pytest.raises(ModelError, match="no ref"):
        Job.from_dict(bad)
    bad = copy.deepcopy(raw)
    bad["systems"][0]["colour"] = "red"
    with pytest.raises(ModelError, match="unknown field"):
        Job.from_dict(bad)
    bad = copy.deepcopy(raw)
    del bad["systems"][0]["key"]
    with pytest.raises(ModelError, match="missing field key"):
        Job.from_dict(bad)


def test_with_system_replaces_by_key(job):
    ef = job.system("EF")
    changed = job.with_system(System(ef.key, "Fans", ef.shape, ef.control, ef.families))
    assert changed.system("EF").name == "Fans" and changed.system("RTU") == job.system("RTU")


def test_a_system_with_nothing_to_scope_says_why():
    system = System("XF", "Exhaust Fan", "", "none", (), no_scope_reason="The fan has its own controls.")
    data = system.to_dict()
    assert data["no_scope_reason"] == "The fan has its own controls." and data["devices"] == []
    assert System.from_dict(data) == system
    assert System("XF", "Exhaust Fan", "", "none", ()).no_scope_reason is None
    prop = json_schema(System)["properties"]["no_scope_reason"]
    assert {"type": "null"} in prop["anyOf"] and {"type": "string"} in prop["anyOf"]
    old = {k: v for k, v in data.items() if k != "no_scope_reason"}
    assert System.from_dict(old).no_scope_reason is None          # a Job saved before the field still loads


def test_a_duct_heater_block_lists_the_units_it_serves():
    tie = Served(key="AHU", name="Air Handling Unit", tags=("AHU-1",), heaters=("EDH-1",), heater_key="EDH",
                 heater_name="Electric Duct Heater")
    system = System("EDH", "Electric Duct Heater", "", "field", (), serves=(tie,))
    data = system.to_dict()
    assert data["serves"] == [{"key": "AHU", "name": "Air Handling Unit", "tags": ["AHU-1"], "heaters": ["EDH-1"],
                               "heater_key": "EDH", "heater_name": "Electric Duct Heater"}]
    assert System.from_dict(data) == system
    assert System("XF", "Exhaust Fan", "", "none", ()).serves == ()
    prop = json_schema(System)["properties"]["serves"]
    assert prop["type"] == "array"
    assert prop["items"]["required"] == ["key", "name", "tags", "heaters", "heater_key", "heater_name"]
    old = {k: v for k, v in data.items() if k != "serves"}
    assert System.from_dict(old).serves == ()                     # a Job saved before the field still loads


def test_finding_and_decision_round_trip():
    finding = Finding("Packaged units", "RTU", "RTU.d1", "must_fix", "what", "fix")
    assert Finding.from_dict(finding.to_dict()) == finding
    device = Device("EF.d1", "controller", "DDC Controller", "Furnish and Install", "AME", "AME", "AME", Count(3),
                    (Ref("S1", "q", "w"),))
    decision = Decision("EF", "change", device_id="EF.d1", device=device, reason="r")
    assert Decision.from_dict(json.loads(json.dumps(decision.to_dict()))) == decision


# ---- the JSON Schema ---------------------------------------------------------------------------------------------

def _objects(schema: dict):
    if schema.get("type") == "object":
        yield schema
    for value in schema.values():
        if isinstance(value, dict):
            yield from _objects(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    yield from _objects(item)


def test_system_schema_validates_the_fixture_systems(raw):
    schema = json_schema(System)
    for system in raw["systems"]:
        assert schema_errors(system, schema) == []
    assert schema_errors(raw, json_schema(Job)) == []


def test_system_schema_is_strict_for_structured_outputs():
    schema = json_schema(System)
    for obj in _objects(schema):
        assert obj["additionalProperties"] is False
        assert obj["required"] == list(obj["properties"])
    device = schema["properties"]["devices"]["items"]
    assert device["properties"]["refs"]["minItems"] == 1
    assert device["properties"]["verb"]["enum"] == list(VERBS)
    assert device["properties"]["furnished_by"]["enum"] == list(PARTIES)
    assert schema["properties"]["control"]["enum"] == list(CONTROLS)
    count = device["properties"]["quantity"]["properties"]["value"]
    assert {"type": "null"} in count["anyOf"]
    json.dumps(schema)


def test_schema_errors_catch_bad_answers(raw):
    schema = json_schema(System)
    system = copy.deepcopy(raw["systems"][1])
    system["devices"][0]["refs"] = []
    system["devices"][1]["verb"] = "Provide"
    system["devices"][2]["quantity"]["value"] = "three"
    del system["tech_hours"]
    system["extra"] = 1
    errors = schema_errors(system, schema)
    assert any("refs" in e and "at least 1" in e for e in errors)
    assert any("verb" in e for e in errors)
    assert any("quantity.value" in e for e in errors)
    assert any("missing tech_hours" in e for e in errors)
    assert any("unexpected extra" in e for e in errors)


def test_finding_schema_is_what_qc_answers():
    schema = {"type": "object", "properties": {"findings": {"type": "array", "items": json_schema(Finding)}},
              "required": ["findings"], "additionalProperties": False}
    answer = {"findings": [Finding("The schedule count prints", "VRF", None, "check", "w", "f").to_dict()]}
    assert schema_errors(answer, schema) == []


# ---- the Playbook ---------------------------------------------------------------------------------------------

def test_repo_playbook_loads():
    playbook = load_playbook()
    assert isinstance(playbook, Playbook)
    assert "Packaged units" in playbook.topics
    assert not any(rule.sample for rule in playbook.rules.values())      # workstream 1 replaced the samples
    assert playbook.shape("Exhaust Fan").header.startswith("Qty ({n})")
    assert playbook.wording.verbs == VERBS
    assert playbook.rules_text.startswith("# AME Playbook")
    assert load_playbook(ROOT / "playbook") == playbook


def test_sample_playbook_covers_the_fixture(job):
    playbook = load_playbook(SAMPLE_PLAYBOOK)
    for system in job.systems:
        shape = playbook.shape(system.shape)
        assert all(d.slot in shape.line_order for d in system.devices), system.key
    assert playbook.shape_for("Exhaust Fans", ["EF"]).name == "Exhaust Fan"
    assert playbook.shape_for("anything", ["ef-"]).name == "Exhaust Fan"
    assert playbook.shape_for("Electric Duct Heaters", []).name == "Duct Heater"
    assert playbook.shape_for("Chiller Plant", ["CH"]) is None
    assert playbook.shape("Rooftop Unit").slots_of_kind("integration") == ("comm_wiring", "map_points", "rep_assist")


@pytest.mark.parametrize("file, change, message", [
    ("shapes.json", lambda d: d["shapes"][0].pop("header"), "missing header"),
    ("shapes.json", lambda d: d["shapes"][0]["slot_kinds"].update(comm_wiring="gadget"), "slot_kinds"),
    ("shapes.json", lambda d: d["shapes"][0]["wording"].pop("comm_wiring"), "wording must cover"),
    ("shapes.json", lambda d: d["shapes"].append(d["shapes"][0]), "appears twice"),
    ("shapes.json", lambda d: d["shapes"][0]["tech_hours"].update(per="week"), "tech_hours.per"),
    ("wording.json", lambda d: d["verbs"].append("Install"), "verbs must be exactly"),
    ("wording.json", lambda d: d["owner_brackets"].pop("FA"), "owner_brackets"),
    ("wording.json", lambda d: d["clarifications"].update(note="{text}"), "clarifications"),
])
def test_malformed_playbook_json_is_refused(tmp_path, file, change, message):
    folder = tmp_path / "pb"
    shutil.copytree(SAMPLE_PLAYBOOK, folder)
    data = json.loads((folder / file).read_text(encoding="utf-8"))
    change(data)
    (folder / file).write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(PlaybookError, match=message):
        load_playbook(folder)


@pytest.mark.parametrize("text, message", [
    ("### Orphan\nText.\n", "not under a topic"),
    ("## T\n### A\nx\n### A\ny\n", "appears twice"),
    ("## T\n### Empty\n## U\n", "has no text"),
    ("No headings at all\n", "no topic"),
])
def test_malformed_rules_are_refused(tmp_path, text, message):
    folder = tmp_path / "pb"
    shutil.copytree(SAMPLE_PLAYBOOK, folder)
    (folder / "rules.md").write_text(text, encoding="utf-8")
    with pytest.raises(PlaybookError, match=message):
        load_playbook(folder)


def test_broken_json_names_the_file(tmp_path):
    folder = tmp_path / "pb"
    shutil.copytree(SAMPLE_PLAYBOOK, folder)
    (folder / "wording.json").write_text("{", encoding="utf-8")
    with pytest.raises(PlaybookError, match="wording.json: not valid JSON"):
        load_playbook(folder)


# ---- the stubs' signatures (the brief, exactly) --------------------------------------------------------------

SIGNATURES = {
    plan.plan_job: ["ledger", "catalogue", "dossier", "playbook"],
    validate.validate: ["job", "playbook"],
    render.render: ["job", "playbook"],
    ai.write_system: ["system", "evidence", "playbook", "transport", "tags", "ids", "sheets",
                      "source_sheets"],   # optional, kw-only (source_sheets: FINAL-J)
    ai.qc_job: ["job", "evidence_index", "playbook", "transport"],
    ai.revise_system: ["system", "findings", "evidence", "playbook", "transport", "tags", "ids", "sheets",
                       "source_sheets", "estimators", "deleted", "counts_decided"],   # as write_system; the
    # estimator's lines (RUN-1) and the counts they set (RUN-11): optional, kw-only
    ai.evidence_for: ["system", "dossier"],
    ai.evidence_index: ["dossier"],
    counts.count_tags: ["image_path", "tag_pattern", "transport"],      # transport: optional, keyword-only
    counts.cross_check: ["job", "catalogue", "cache", "transport"],     # transport: optional, keyword-only
    review.review_page: ["job", "findings", "out_dir"],
    review.load_decisions: ["out_dir"],
    review.apply_decisions: ["job", "decisions"],
    measure.measure: ["rendered_lines", "final_proposal_path"],
    run.estimate: ["job_folder", "out", "cache", "mode"],
}

RETURNS = {
    plan.plan_job: "Job", validate.validate: "list[Finding]", render.render: "ProposalDraft",
    ai.write_system: "System", ai.qc_job: "list[Finding]", ai.revise_system: "System", ai.evidence_for: "str",
    counts.count_tags: "CountResult", review.review_page: "Path", review.load_decisions: "list[Decision]",
    review.apply_decisions: "Job", measure.measure: "MeasureResult", run.estimate: "RunResult",
}


@pytest.mark.parametrize("function", list(SIGNATURES), ids=lambda f: f"{f.__module__}.{f.__name__}")
def test_signature(function):
    signature = inspect.signature(function)
    assert list(signature.parameters) == SIGNATURES[function]
    if function in RETURNS:
        assert signature.return_annotation == RETURNS[function]
    assert len(inspect.getdoc(function) or "") > 80          # the contract is stated


def test_the_writers_take_tags_ids_and_sheets_keyword_only_with_an_empty_default():
    for function in (ai.write_system, ai.revise_system, ai.rewrite_for_count):     # the count rewrite too (R-1)
        for name in ("ids", "tags", "sheets", "source_sheets"):
            parameter = inspect.signature(function).parameters.get(name)
            assert parameter is not None, (function, name)
            assert parameter.kind is parameter.KEYWORD_ONLY and parameter.default == (), (function, name)


def test_estimate_defaults_to_chat():
    assert inspect.signature(run.estimate).parameters["mode"].default == "chat"


def test_render_names_the_old_writers_input():
    from estimator.scope import Job as ScopeJob
    assert render.ProposalDraft.__dataclass_fields__["scope"].type in ("ScopeJob", ScopeJob)
    assert "write_proposal" in render.__doc__ and "write_price_sheet" in render.__doc__


def test_plan_job_takes_the_old_app_types():
    hints = inspect.get_annotations(plan.plan_job, eval_str=True)
    from estimator.catalogue.job import Catalogue
    from estimator.ledger.facts import Ledger
    from estimator.writing.dossier import Dossier
    assert hints["ledger"] is Ledger and hints["catalogue"] is Catalogue and hints["dossier"] is Dossier


def test_transports_follow_the_protocol():
    names = ["self", "kind", "name", "instructions", "system_prompt", "prompt", "schema", "extra", "images"]
    for cls in (ai.ChatTransport, ai.ApiTransport):
        assert list(inspect.signature(cls.ask).parameters) == names
    assert list(inspect.signature(ai.Transport.ask).parameters) == names
    assert list(inspect.signature(ai.ChatTransport.__init__).parameters) == ["self", "cache_dir", "job", "handoff_dir"]
    assert list(inspect.signature(ai.ApiTransport.__init__).parameters) == ["self", "cache_dir", "model", "client"]
    assert ai.WRITE_SYSTEM == "write_system" and ai.QC_JOB == "qc_job"


def test_count_result_shape():
    result = counts.CountResult(2, (counts.Box(0, 0, 10, 10, "EF-1"), counts.Box(5, 5, 10, 10, "EF-2")))
    assert result.value == len(result.boxes)


def test_measure_result_summary():
    line = measure.LineMatch("EF", "DDC Controller", "Furnish and Install", 3)
    result = measure.MeasureResult(((line, line),), (line,), ())
    assert result.summary() == "matched 1/2 (50%), missed 1, extra 0"


# ---- the command line -------------------------------------------------------------------------------------------

def test_cli_help():
    for args in (["--help"], ["estimate", "--help"]):
        done = subprocess.run([sys.executable, "-m", "bms", *args], cwd=ROOT, capture_output=True, text=True)
        assert done.returncode == 0, done.stderr
        assert "estimate" in done.stdout
    done = subprocess.run([sys.executable, "-m", "bms", "estimate", "--help"], cwd=ROOT, capture_output=True,
                          text=True)
    assert "--mode" in done.stdout and "--cache" in done.stdout and "--out" in done.stdout


def test_run_job_check_accepts_a_system_answer(tmp_path, raw):
    import run_job
    request, answer = tmp_path / "r.json", tmp_path / "a.json"
    request.write_text(json.dumps({"key": "k", "kind": ai.WRITE_SYSTEM, "schema": json_schema(System)}),
                       encoding="utf-8")
    answer.write_text(json.dumps(raw["systems"][1]), encoding="utf-8")
    assert run_job.check_answer(answer, request) is None
