"""The runner: the ledger is seeded, each pass asked in order, long passes split, empty passes skipped, and the
run stops at the first pass with no answer."""
import json
from types import SimpleNamespace

from estimator.ledger.facts import SETTLED
from estimator.ledger.run import read_job
from estimator.writing.judge import Judge
from tests.test_ledger_passes import CATALOGUE
from tests.test_ledger_seed import _dossier
from tests.test_whole_job import FakeClient, _response


def _reply(understanding="ok", facts=()):
    return _response({"facts": list(facts), "contradictions": [], "confirmations": [], "understanding": understanding})


def test_every_pass_with_documents_is_asked_in_order_and_the_rest_skipped(tmp_path):
    client = FakeClient(*[_reply(f"pass {n}") for n in range(1, 8)])
    judge = Judge(tmp_path / "cache", model="test-model", client=client)
    ledger = read_job(judge, _dossier(), CATALOGUE, save_to=tmp_path / "ledger.json")

    asked = [c["messages"][0]["content"] for c in client.calls]
    names = [next(line for line in (t if isinstance(t, str) else t[0]["text"]).splitlines() if line.startswith("This is the "))
             for t in asked]
    assert names == ["This is the Schedules pass (schedules).", "This is the Plans pass (plans).",
                     "This is the Sequence of operation and points list pass (sequence).",
                     "This is the Controls specification pass (spec)."]
    assert ledger.understanding["details"] == "nothing to read: no Details and control diagrams in this job"
    assert ledger.understanding["risers"] == "nothing to read: no Air and water risers in this job"
    assert ledger.understanding["network"] == "nothing to read: no Network riser in this job"
    assert ledger.complete is True and ledger.stopped_at == ""
    assert ledger.job_name == "26-9999"
    saved = json.loads((tmp_path / "ledger.json").read_text(encoding="utf-8"))
    assert saved["complete"] is True and saved["understanding"]["spec"] == "pass 4"


def test_a_passs_facts_are_in_the_ledger_and_its_refusals_kept(tmp_path):
    client = FakeClient(_reply("schedules", [
        {"kind": "provider", "subject": "VAV controller", "value": "AME", "source_id": "[S4]", "quote": "VAV BOX SCHEDULE"},
        {"kind": "link", "subject": "VAV", "value": "RTU-1", "source_id": "[S4]", "quote": "VAV BOX SCHEDULE"}]),
        _reply(), _reply(), _reply())
    judge = Judge(tmp_path / "cache", model="test-model", client=client)
    ledger = read_job(judge, _dossier(), CATALOGUE)
    fact = ledger.find("provider", "VAV controller")
    assert fact.value == "AME" and fact.state == SETTLED and fact.stage == "schedules"
    assert ledger.refused["schedules"] == ["the schedules pass may not write a link fact (VAV = RTU-1); left out"]


def test_the_run_stops_at_the_first_pass_without_an_answer(tmp_path):
    judge = Judge(tmp_path / "cache", mode="chat", job="26-9999", handoff_dir=tmp_path / "chat")
    ledger = read_job(judge, _dossier(), CATALOGUE, save_to=tmp_path / "ledger.json")
    assert ledger.complete is False and ledger.stopped_at == "schedules"
    assert judge.waiting == 1                       # only the first pass was asked: the next depends on its answer
    assert ledger.find("count", "VAV").value == 12  # the seed is there
    assert (tmp_path / "ledger.json").exists()


def test_a_long_pass_is_split_and_each_part_applied_in_turn(tmp_path):
    long_text = _dossier().text.replace("[S4] VAV BOX SCHEDULE", "[S4] " + "x" * 1200 + " VAV BOX SCHEDULE")
    client = FakeClient(_reply("part one", [{"kind": "provider", "subject": "VAV controller", "value": "AME", "source_id": "[S4]", "quote": "VAV BOX SCHEDULE"}]),
                        _reply("part two"), _reply(), _reply(), _reply())
    judge = Judge(tmp_path / "cache", model="test-model", client=client)
    ledger = read_job(judge, _dossier(text=long_text), CATALOGUE, limit=1500)
    first, second = client.calls[0], client.calls[1]
    assert "part 1 of 2" not in str(first)          # the part number is in the request name, not the prompt
    assert ledger.understanding["schedules"] == "part one part two"     # every part's understanding is kept
    assert ledger.find("provider", "VAV controller") is not None
    assert "F" in str(second["messages"][0]["content"])   # the second part saw the first part's facts


def test_the_plans_pass_lists_its_pictures_and_respects_the_cap(tmp_path, monkeypatch):
    from estimator.ledger import run as run_module
    rendered = []
    def fake_pictures(catalogue, cache_dir, keys, what):
        rendered.extend(keys)
        return [SimpleNamespace(path=str(tmp_path / f"{d}-{p}.png"), what=f"{d} {p} — {what}", sheet=None, document=d, page=p) for d, p in keys], []
    monkeypatch.setattr(run_module, "sheet_pictures", fake_pictures)
    client = FakeClient(*[_reply("ok") for _ in range(6)])
    judge = Judge(tmp_path / "cache", model="test-model", client=client)
    read_job(judge, _dossier(), CATALOGUE, picture_cap=1)
    plans_call = next(c for c in client.calls if "This is the Plans pass" in str(c["messages"][0]["content"]))
    content = str(plans_call["messages"][0]["content"])
    assert rendered == [("Drawings.pdf", 3)]          # the one plan sheet in the fixture
    assert "Picture I1" in content or "I1" in content


def test_no_pictures_keeps_the_passes_text_only(tmp_path, monkeypatch):
    from estimator.ledger import run as run_module
    monkeypatch.setattr(run_module, "sheet_pictures", lambda *a, **k: (_ for _ in ()).throw(AssertionError("rendered")))
    client = FakeClient(*[_reply("ok") for _ in range(6)])
    read_job(Judge(tmp_path / "cache", model="test-model", client=client), _dossier(), CATALOGUE, pictures=False)


def test_a_picture_source_starts_with_its_sheet_number(tmp_path, monkeypatch):
    from estimator.ledger import run as run_module
    from estimator.ledger.to_plan import place_words
    monkeypatch.setattr(run_module, "sheet_pictures", lambda catalogue, cache_dir, keys, what: (
        [SimpleNamespace(path=str(tmp_path / f"{p}.png"), what=f"{d} page {p} — {what}", sheet=None, document=d, page=p)
         for d, p in keys], []))
    client = FakeClient(*[_reply("ok") for _ in range(6)])
    ledger = read_job(Judge(tmp_path / "cache", model="test-model", client=client), _dossier(), CATALOGUE)
    (source,) = [v for v in ledger.sources.values() if v.endswith("(picture)")]
    assert source.startswith("M-201 ")
    assert place_words(source, "VAV-1 VAV-2") == "M-201"
