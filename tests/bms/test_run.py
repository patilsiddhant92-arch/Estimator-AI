"""Integration: `bms.run.estimate` end to end on an invented job folder, in chat mode, with a fake answerer that
answers every request the run writes (reading passes, plan count sheets, write and revise, QC) from canned invented
answers. No real job data: the PDFs are built here."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import openpyxl
import pytest

from bms.run import estimate

TESTS = Path(__file__).resolve().parents[1]
if str(TESTS) not in sys.path:
    sys.path.insert(0, str(TESTS))

from pdfs import FILLER, Page, make_pdf  # noqa: E402
from test_schedules import grid  # noqa: E402

W, H = 3024, 2160
JOB = "00-9999"
VAV_ROWS = [["VAV BOX SCHEDULE", "", "", "", ""],
            ["TAG", "SERVES", "MAX CFM", "HW GPM", "MANUFACTURER"],
            ["VAV-1", "ROOM 101", "600", "1.5", "INVENTED CO"],
            ["VAV-2", "ROOM 102", "700", "1.5", "INVENTED CO"],
            ["VAV-3", "ROOM 103", "500", "1.0", "INVENTED CO"]]


def _schedule_sheet() -> Page:
    lines, texts = grid(300, 300, [90, 120, 70, 70, 100], VAV_ROWS)
    return Page(W, H, ((200, 200, FILLER, 12), *texts,
                       (2640, 1860, "HVAC SCHEDULES", 20), (2800, 2000, "M-601", 40)), lines=lines)


PLAN = Page(W, H, ((200, 300, FILLER, 12), (900, 900, "VAV-1", 12), (900, 1000, "VAV-2", 12),
                   (900, 1100, "VAV-3", 12), (2640, 1860, "SECOND FLOOR PLAN", 20), (2800, 2000, "M-201", 40)))
SEQUENCE = Page(texts=((72, 72, "SECTION 23 09 93 - SEQUENCE OF OPERATIONS\n\n"
                                "A. VAV boxes: each VAV box shall maintain the space temperature setpoint with a "
                                "space temperature sensor furnished and installed by the controls contractor.\n\n"
                                "23 09 93 - 1", 10),))


@pytest.fixture
def job_folder(tmp_path) -> Path:
    root = tmp_path / f"{JOB}, 1 Invented Street"
    base = root / "2. Takeoffs" / "1. Base Takeoff"
    make_pdf(base / "Mech.pdf", _schedule_sheet(), PLAN)
    make_pdf(base / "230993.pdf", SEQUENCE)
    return root


# ---- the fake answerer: one canned, invented answer per request kind ------------------------------------------------

def _evidence_ref(prompt: str) -> dict:
    """A ref to the first source of the evidence that has words after its id, quoting its first words."""
    evidence = prompt.split("The evidence:", 1)[-1]
    for line in evidence.splitlines():
        found = re.match(r"\s*\[(S\d+)\]\s+(.*)", line)          # a document source, not a count record
        if found:
            words = re.findall(r"[A-Za-z0-9]+", found.group(2))[:4]
            if words:
                return {"source_id": found.group(1), "quote": " ".join(words), "where": "invented place"}
    raise AssertionError("the write request carries no evidence with an id")


def _first_slot(prompt: str) -> str:
    found = re.search(r"^- ([a-z0-9_]+) \((?:device|point)\)", prompt, re.M)
    return found.group(1) if found else "controller"


def _system_answer(request: dict) -> dict:
    prompt = request["prompt"]
    ref = _evidence_ref(prompt)
    key = request.get("plan_key") or "X"
    device = {"id": f"{key}.d1", "slot": _first_slot(prompt), "name": "Space Temperature Sensor",
              "verb": "Furnish and Install", "furnished_by": "AME", "installed_by": "AME", "wired_by": "AME",
              "quantity": {"value": None, "sources": [], "others": []}, "refs": [ref], "assumption": None,
              "flag": "quantity"}
    return {"key": key, "name": "answered", "shape": "", "control": "none", "families": [], "sequence_refs": [],
            "devices": [device], "clarifications": [{"kind": "per_drawings", "text": "Quantity as per drawings"}],
            "tech_hours": None, "alternate": "base"}


def _answer(request: dict) -> dict:
    kind = request["kind"]
    if kind == "read_pass":
        return {"facts": [], "contradictions": [], "confirmations": [], "understanding": "invented reading"}
    if kind == "count_tags":
        examined = list(range(1, len(request.get("tiles", [])) + 1))          # every tile opened
        return {"patterns": [{"pattern": p, "tiles_examined": examined, "tags": []}
                             for p in request.get("patterns", [])]}
    if kind == "write_system":
        return _system_answer(request)
    if kind == "qc_job":
        return {"findings": []}
    raise AssertionError(f"a request of an unknown kind: {kind}")


def answer_all(cache: Path) -> dict[str, int]:
    """Write an answer for every waiting request; how many of each kind."""
    kinds: dict[str, int] = {}
    for path in sorted((cache / "judge-chat" / "requests").glob("*.json")):
        request = json.loads(path.read_text(encoding="utf-8"))
        answer = Path(request["answer_file"])
        answer.parent.mkdir(parents=True, exist_ok=True)
        answer.write_text(json.dumps(_answer(request)), encoding="utf-8")
        kinds[request["kind"]] = kinds.get(request["kind"], 0) + 1
    return kinds


# ---- the run ---------------------------------------------------------------------------------------------------------

def test_a_run_waits_for_its_answers_then_writes_all_four_outputs(job_folder, tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out, cache = tmp_path / "out", tmp_path / "cache"

    first = estimate(job_folder, out, cache, "chat")
    assert first.status == "waiting" and first.stage == "read" and first.waiting >= 1
    assert first.proposal is None

    stages, kinds, result = [first.stage], {}, first
    for _ in range(25):
        for kind, n in answer_all(cache).items():
            kinds[kind] = kinds.get(kind, 0) + n
        result = estimate(job_folder, out, cache, "chat")
        if result.status == "done":
            break
        assert result.status == "waiting" and result.waiting >= 1
        stages.append(result.stage)
    assert result.status == "done" and result.stage == "done", stages

    assert stages.index("read") < stages.index("count") < stages.index("write") < stages.index("qc")
    assert {"read_pass", "count_tags", "write_system", "qc_job"} <= set(kinds)
    assert result.proposal.name == f"{JOB} Proposal.docx" and result.proposal.exists()
    assert result.price_sheet.name == f"{JOB} Price Sheet.xlsx" and result.price_sheet.exists()
    assert result.evidence.name == f"{JOB} Evidence Package.xlsx" and result.evidence.exists()
    assert result.review == out / "Review.html" and result.review.exists()
    assert result.job_file.exists()
    assert [f for f in result.findings if f.severity == "must_fix"] == []

    assert (out / "count-proofs" / "proofs.json").exists()          # the count proofs, beside the review page
    assert 'src="count-proofs/' in result.review.read_text(encoding="utf-8")

    book = openpyxl.load_workbook(result.evidence)
    assert book.sheetnames[1:3] == ["Scope lines", "Findings"]
    rows = [[c.value for c in row] for row in book["Scope lines"].iter_rows()]
    device = next(r for r in rows if r[2] == "device")
    assert device[6] == "Furnish and Install" and device[7:10] == ["AME", "AME", "AME"]
    assert "invented place" in device[12] and device[14] == "quantity"

    # a further run with every answer cached finishes straight away, writing nothing new to ask
    again = estimate(job_folder, out, cache, "chat")
    assert again.status == "done" and again.waiting == 0
    assert list((cache / "judge-chat" / "requests").glob("*.json")) == []


# ---- what stays open after the one revise round ----------------------------------------------------------------------

def _reach(job_folder, out, cache, stage):
    """Run until the estimate is waiting at `stage`. Answers every earlier request."""
    result = None
    for _ in range(25):
        result = estimate(job_folder, out, cache, "chat")
        if result.status == "done" or result.stage == stage:
            return result
        assert result.status == "waiting" and result.waiting >= 1
        assert answer_all(cache)
    raise AssertionError(result)


def test_a_killed_write_resumes_from_cached_answers_without_asking_again(job_folder, tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out, cache = tmp_path / "out", tmp_path / "cache"
    waiting = _reach(job_folder, out, cache, "write")
    assert waiting.stage == "write"
    folder = cache / "judge-chat" / "requests"
    requests = sorted(folder.glob("*.json"))
    assert requests and {json.loads(p.read_text(encoding="utf-8"))["kind"] for p in requests} == {"write_system"}
    saved = {p.name: p.read_bytes() for p in requests}

    # killed after the requests were written, before any answer: the same files, not a second ask
    resumed = estimate(job_folder, out, cache, "chat")
    assert resumed.status == "waiting" and resumed.stage == "write"
    assert {p.name: p.read_bytes() for p in folder.glob("*.json")} == saved

    # those answers are now cached, but a kill left the request files behind: resume must drop them
    for path in folder.glob("*.json"):
        request = json.loads(path.read_text(encoding="utf-8"))
        answer = Path(request["answer_file"])
        answer.parent.mkdir(parents=True, exist_ok=True)
        answer.write_text(json.dumps(_answer(request)), encoding="utf-8")
    consumed = estimate(job_folder, out, cache, "chat")
    assert consumed.stage != "write"
    for name, payload in saved.items():
        (folder / name).write_bytes(payload)
    estimate(job_folder, out, cache, "chat")
    assert not any(p.name in saved for p in folder.glob("*.json"))


def test_a_malformed_decisions_file_stops_with_a_plain_message(job_folder, tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out, cache = tmp_path / "out", tmp_path / "cache"
    assert _reach(job_folder, out, cache, "write").stage == "write"
    (out / "decisions.json").write_text("{", encoding="utf-8")
    assert answer_all(cache)
    result = estimate(job_folder, out, cache, "chat")
    assert result.messages and any("decisions.json" in line and "Stopped" in line for line in result.messages)
    assert result.proposal is None


def test_a_rerun_asks_the_writer_again_only_for_the_system_a_decision_changed(job_folder, tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out, cache = tmp_path / "out", tmp_path / "cache"
    assert _reach(job_folder, out, cache, "write").stage == "write"
    requests = sorted((cache / "judge-chat" / "requests").glob("*.json"))
    changed = json.loads(requests[0].read_text(encoding="utf-8"))["plan_key"]
    (out / "decisions.json").write_text(json.dumps([{
        "system_key": changed, "action": "delete", "device_id": f"{changed}.d1", "reason": "invented",
    }]), encoding="utf-8")
    assert answer_all(cache)
    result = estimate(job_folder, out, cache, "chat")
    assert result.status == "waiting"
    fresh = [json.loads(p.read_text(encoding="utf-8"))
             for p in (cache / "judge-chat" / "requests").glob("*.json")]
    assert [r.get("plan_key") for r in fresh] == [changed]
    assert fresh[0]["step"] == "write" and "estimator" in fresh[0]["prompt"].lower()


def test_a_qc_must_fix_the_revise_left_as_it_was_stays_open():
    import dataclasses

    from bms.model import Finding, Job
    from bms.run import _untouched

    job = Job.from_dict(json.loads((TESTS / "bms" / "fixtures" / "sample_job.json").read_text(encoding="utf-8")))
    ef = job.system("EF")
    changed = job.with_system(dataclasses.replace(ef, devices=(dataclasses.replace(ef.devices[0], name="New"),
                                                               *ef.devices[1:])))
    on = lambda device=None, key="EF": Finding("Every line cites this job", key, device, "must_fix", "w", "f")
    assert _untouched(on("EF.d2"), job, changed) and not _untouched(on("EF.d1"), job, changed)
    assert not _untouched(on(None), job, changed) and _untouched(on(None, "RTU"), job, changed)
    assert _untouched(on(None, ""), job, changed)
