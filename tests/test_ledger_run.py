"""The runner: the ledger is seeded, each pass asked in order, long passes split, empty passes skipped, and the
run stops at the first pass with no answer."""
import json
import re
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


def test_an_addendum_reissue_is_pictured_from_its_own_page_not_the_superseded_one(tmp_path, monkeypatch):
    from estimator.catalogue.register import PageRecord
    from estimator.catalogue.sheet_types import Sheet
    from estimator.ledger import run as run_module
    from estimator.reading.revisions import SheetVersion, Supersession
    from tests.test_ledger_passes import _built
    base, addendum = "Drawings/Mech.pdf", "Addendum/Addendum 1.pdf"
    sheets = [Sheet(base, 1, "M-101", "FIRST FLOOR PLAN", "Mechanical", ("Plans",)),
              Sheet(addendum, 4, "M-101", "FIRST FLOOR PLAN", "Mechanical", ("Plans",))]
    pages = [PageRecord(base, 1, "text", "FIRST FLOOR PLAN KEYED NOTE 1 PROVIDE A LEAK CHIME AT WH-1.", 0, True, ()),
             PageRecord(addendum, 4, "text", "FIRST FLOOR PLAN KEYED NOTE 1 PROVIDE A DAMPER ACTUATOR AT MD-7.", 0,
                        True, ())]
    replaced = SheetVersion("M-101", base, 1, (), None, "title block")
    current = SheetVersion("M-101", addendum, 4, (), None, "document is an addendum")
    dossier, catalogue = _built(sheets, pages, documents=((base, "drawings", "base"), (addendum, "addendum", "base")),
                                supersessions=[Supersession("M-101", current, (replaced,), (), "")])
    rendered = []
    def fake_pictures(catalogue, cache_dir, keys, what):
        rendered.extend(keys)
        return [SimpleNamespace(path=str(tmp_path / f"{p}.png"), what=f"page {p} — {what}", sheet=None, document=d,
                                page=p) for d, p in keys], []
    monkeypatch.setattr(run_module, "sheet_pictures", fake_pictures)
    client = FakeClient(*[_reply("ok") for _ in range(8)])
    read_job(Judge(tmp_path / "cache", model="test-model", client=client), dossier, catalogue)
    assert rendered == [(addendum, 4)]


EMPTY_TEXT = """JOB DOSSIER — 26-9999
Everything controls-relevant.

== 1. JOB ==
[S1] 26-9999 Example HS. Controls: new BACnet system.

== 2. SEQUENCE OF OPERATION ==
(No sequence of operation found in the documents.)

== 3. POINTS LISTS ==
(No points list found in the documents.)

== 4. SCHEDULES ==
(No schedules read from the drawings.)

== 5. EQUIPMENT COUNTS ==
(No equipment tags counted.)

== 6. DEVICES ON PLANS ==
(No device labels counted on the plans.)

== 7. NOTES ==
(No notes that add controls scope.)

== 8. CONTROLS SPEC HIGHLIGHTS ==
(No controls spec section found.)
"""


def test_a_pass_whose_sections_hold_only_a_placeholder_is_not_asked(tmp_path):
    # LDG-12: "(No schedules read from the drawings.)" is no document: the pass has nothing to read
    client = FakeClient(_reply("spec"))
    judge = Judge(tmp_path / "cache", model="test-model", client=client)
    ledger = read_job(judge, _dossier(text=EMPTY_TEXT, counts={}, sections={}, families=(), device_totals={}),
                      CATALOGUE)
    asked = [c["messages"][0]["content"] for c in client.calls]
    names = [next(line for line in (t if isinstance(t, str) else t[0]["text"]).splitlines() if line.startswith("This is the "))
             for t in asked]
    # only the spec pass is asked: it reads the job section too (the bid check, the makers), which has lines
    assert names == ["This is the Controls specification pass (spec)."]
    assert ledger.understanding["schedules"] == "nothing to read: no Schedules in this job"
    assert ledger.understanding["plans"] == "nothing to read: no Plans in this job"
    assert ledger.understanding["sequence"] == ("nothing to read: no Sequence of operation and points list in "
                                                "this job")
    assert ledger.complete is True


def test_a_long_sequence_is_split_at_its_section_marks(tmp_path):
    # LDG-14: a part never begins mid-section without its "--- [Qn] heading ---" line
    blocks = "".join(f"--- [Q{n}] SYSTEM {n} ---\n" + "".join(f"[S{n}] The fan {n} shall run, step {k}.\n" for k in range(12))
                     for n in range(1, 7))
    text = _dossier().text.split("== 2. SEQUENCE OF OPERATION ==\n", 1)
    text = text[0] + "== 2. SEQUENCE OF OPERATION ==\n" + blocks + "\n== 3." + text[1].split("\n== 3.", 1)[1]
    client = FakeClient(*[_reply("ok") for _ in range(20)])
    judge = Judge(tmp_path / "cache", model="test-model", client=client)
    read_job(judge, _dossier(text=text), CATALOGUE, limit=1000)
    head = "The documents for this pass, each paragraph with its source id:\n"
    parts = [str(c["messages"][0]["content"] if isinstance(c["messages"][0]["content"], str)
                 else c["messages"][0]["content"][0]["text"]).split(head, 1)[1]
             for c in client.calls if "This is the Sequence of operation" in str(c["messages"][0]["content"])]
    assert len(parts) > 1
    assert parts[0].startswith("== 2. SEQUENCE OF OPERATION ==\n--- [Q1] SYSTEM 1 ---")
    for part in parts[1:]:
        assert re.match(r"--- \[Q\d+\] SYSTEM \d+ ---\n", part), part[:80]
    joined = "".join(parts)
    for n in range(1, 7):                       # every section once, whole
        assert joined.count(f"--- [Q{n}] SYSTEM {n} ---") == 1
        assert all(f"[S{n}] The fan {n} shall run, step {k}." in joined for k in range(12))


def test_a_sequence_section_longer_than_a_part_keeps_its_line_on_every_piece():
    from estimator.ledger.run import _parts
    text = ("== 2. SEQUENCE OF OPERATION ==\n--- [Q1] SHORT ---\n[S1] One line.\n--- [Q2] LONG ---\n"
            + "".join(f"[S2] The chiller plant shall stage, step {k}.\n" for k in range(80)))
    parts = _parts(text, 1000)
    assert len(parts) > 2 and parts[0].startswith("== 2. SEQUENCE OF OPERATION ==\n--- [Q1] SHORT ---")
    assert all(part.startswith("--- [Q2] LONG ---\n") for part in parts[1:])
    assert all(f"step {k}." in "".join(parts) for k in range(80))
