"""Fix run 2026-10-10, row 17 (Grok 74, 2, 36): a count typed with words in Change ("2 units", "5 units", "2 ea",
"two") sets the quantity and keeps the line's name; on a family card it sets the family count instead of being lost;
a new name is typed in its own box; text with no count in it gets a plain message on the page, and the decision is not
lost. The page and the Python side read a typed count alike.
Invented data only: the sample fixture."""
from __future__ import annotations

import dataclasses
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from bms import review
from bms.model import Count, Decision, Job, ModelError

FIXTURES = Path(__file__).resolve().parent / "fixtures"
NODE = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")

# a count in words, and the number it says
COUNTS = [("2 units", 2), ("5 units", 5), ("2 ea", 2), ("2 ea.", 2), ("2 each", 2), ("two", 2), ("Two units", 2),
          ("twelve", 12), ("12 total", 12), ("4 (per the schedule)", 4), ("4, per the plans", 4), ("7", 7),
          ("007", 7), ("0", 0), ("(4)", 4), ("##", None), ("unknown", None), ("Not known", None)]
# words that hold no count
UNREADABLE = ["only the roof fans", "approx", "2.5 units", "10-12 fans", "1/2", "24V supply", "-3", "about 4", "2nd floor",
              "tenants"]


@pytest.fixture
def job() -> Job:
    return Job.from_dict(json.loads((FIXTURES / "sample_job.json").read_text(encoding="utf-8")))


def device_card(job: Job, system: str = "EF", device_id: str = "EF.d1") -> dict:
    line = next(d for d in job.system(system).devices if d.id == device_id)
    return {"id": "q1", "system_key": system, "level": "device", "device_id": device_id, "family_name": None,
            "finding_rule": None, "device": line.to_dict(), "count": line.quantity.to_dict()}


def family_card(job: Job, system: str = "RTU", name: str = "Rooftop Unit") -> dict:
    family = next(f for f in job.system(system).families if f.name == name)
    return {"id": "q2", "system_key": system, "level": "family", "device_id": None, "family_name": name,
            "finding_rule": None, "device": None, "count": family.count.to_dict()}


def run_js(tmp_path: Path, body: str):
    """The page's own decision code (`review._SCRIPT_CORE`) in node; `body` ends by printing one JSON value."""
    script = tmp_path / "h.js"
    script.write_text(review._SCRIPT_CORE + "\n" + body, encoding="utf-8")
    done = subprocess.run(["node", str(script)], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def decide(tmp_path: Path, card: dict, state: dict) -> dict:
    return run_js(tmp_path, f"console.log(JSON.stringify(buildDecision({json.dumps(card)}, {json.dumps(state)})));")


def problem(tmp_path: Path, card: dict, state: dict) -> str:
    return run_js(tmp_path, f"console.log(JSON.stringify(decisionProblem({json.dumps(card)}, {json.dumps(state)})));")


# ---- a device card ---------------------------------------------------------------------------------------------------

@NODE
@pytest.mark.parametrize("text, value", COUNTS)
def test_a_count_typed_with_words_sets_the_quantity_and_keeps_the_line_name(job, tmp_path, text, value):
    card = device_card(job)
    made = decide(tmp_path, card, {"action": "change", "text": text})
    line = made["device"]
    assert line["quantity"]["value"] == value and line["quantity"]["others"] == []
    assert line["name"] == card["device"]["name"] and line["flag"] == "none"
    assert made["reason"] == text
    assert problem(tmp_path, card, {"action": "change", "text": text}) == ""


@NODE
@pytest.mark.parametrize("text", UNREADABLE)
def test_words_with_no_count_do_not_rename_the_line_and_the_page_says_so(job, tmp_path, text):
    card = device_card(job, "VRF", "VRF.d2")                     # a line flagged "quantity"
    made = decide(tmp_path, card, {"action": "change", "text": text})
    assert made["device"]["name"] == card["device"]["name"]
    assert made["device"]["quantity"] == card["device"]["quantity"]
    assert made["device"]["flag"] == "quantity"                  # nothing was settled
    assert made["reason"] == text                                # the words are kept
    message = problem(tmp_path, card, {"action": "change", "text": text})
    assert text in message and "whole number" in message and "name box" in message


@NODE
def test_a_name_typed_in_the_name_box_renames_the_line_and_the_count_stays(job, tmp_path):
    card = device_card(job)
    made = decide(tmp_path, card, {"action": "change", "text": "", "fields": {"name": " Room Temperature Sensor "}})
    assert made["device"]["name"] == "Room Temperature Sensor"
    assert made["device"]["quantity"] == card["device"]["quantity"] and made["device"]["flag"] == "none"
    assert "Room Temperature Sensor" in made["reason"]
    assert problem(tmp_path, card, {"action": "change", "text": "", "fields": {"name": "Room Temperature Sensor"}}) == ""


@NODE
def test_a_count_and_a_name_typed_together_both_apply(job, tmp_path):
    card = device_card(job)
    made = decide(tmp_path, card, {"action": "change", "text": "3 units", "fields": {"name": "Room Sensor"}})
    assert made["device"]["name"] == "Room Sensor" and made["device"]["quantity"]["value"] == 3


@NODE
def test_the_name_box_as_the_page_shows_it_changes_nothing(job, tmp_path):
    """The name box starts with the line's own name: leaving it alone is no rename."""
    card = device_card(job)
    name = card["device"]["name"]
    made = decide(tmp_path, card, {"action": "change", "text": "4", "fields": {"name": name, "verb": "Furnish"}})
    assert made["device"]["name"] == name and made["device"]["quantity"]["value"] == 4
    assert made["device"]["verb"] == "Furnish"


@NODE
def test_an_empty_change_on_a_device_is_still_no_problem(job, tmp_path):
    assert problem(tmp_path, device_card(job), {"action": "change", "text": "  "}) == ""


# ---- a family card ---------------------------------------------------------------------------------------------------

@NODE
@pytest.mark.parametrize("text, value", COUNTS)
def test_a_family_change_typed_with_words_sets_the_family_count(job, tmp_path, text, value):
    card = family_card(job)
    made = decide(tmp_path, card, {"action": "change", "text": text})
    assert made["count"]["value"] == value and made["count"]["others"] == []
    assert made["count"]["sources"] == card["count"]["sources"]
    assert made["reason"] == text
    assert problem(tmp_path, card, {"action": "change", "text": text}) == ""


@NODE
@pytest.mark.parametrize("text", UNREADABLE)
def test_a_family_change_with_no_count_in_it_is_not_lost_and_the_page_says_so(job, tmp_path, text):
    card = family_card(job)
    made = decide(tmp_path, card, {"action": "change", "text": text})
    assert made["count"] is None and made["reason"] == text      # the decision keeps the words
    message = problem(tmp_path, card, {"action": "change", "text": text})
    assert text in message and "whole number" in message and "name box" not in message


@NODE
def test_an_empty_family_change_is_a_problem_the_page_names(job, tmp_path):
    message = problem(tmp_path, family_card(job), {"action": "change", "text": ""})
    assert "whole number" in message


@NODE
def test_only_a_change_has_a_problem_and_a_system_note_is_free_text(job, tmp_path):
    card = family_card(job)
    assert problem(tmp_path, card, {"action": "accept"}) == ""
    assert problem(tmp_path, card, None) == ""
    note = {"id": "q3", "system_key": "EF", "level": "system", "device_id": None, "family_name": None,
            "finding_rule": "x", "device": None, "count": None}
    assert problem(tmp_path, note, {"action": "change", "text": "ask the engineer about the fans"}) == ""
    assert decide(tmp_path, note, {"action": "change", "text": "ask the engineer about the fans"})["reason"] == (
        "ask the engineer about the fans")


@NODE
def test_the_live_message_says_what_the_change_will_do(job, tmp_path):
    device, family = device_card(job), family_card(job)
    said = run_js(tmp_path, f"""
var d = {json.dumps(device)}, f = {json.dumps(family)};
console.log(JSON.stringify([explainChange(d, {{action: "change", text: "5 units"}}),
                            explainChange(f, {{action: "change", text: "##"}}),
                            explainChange(d, {{action: "change", text: "", fields: {{name: "Room Sensor"}}}}),
                            explainChange(f, {{action: "change", text: "only the roof fans"}}),
                            explainChange(d, {{action: "accept"}})]));""")
    counted, unknown, renamed, bad, accepted = said
    assert counted["ok"] and "5" in counted["text"]
    assert unknown["ok"] and "not known" in unknown["text"]
    assert renamed["ok"] and "Room Sensor" in renamed["text"]
    assert not bad["ok"] and "only the roof fans" in bad["text"]
    assert accepted == {"ok": True, "text": ""}


# ---- the page and the Python side read a typed count alike ----------------------------------------------------------

SAMPLES = [*(text for text, _ in COUNTS), *UNREADABLE, "", "  ", "2.5", "2,5", "1,000", "3/4", "24V", "2-way valve",
           "(4)", "4 (per plan)", "x4", "twenty", "twenty-one", "ten", "tens", "ONE", "Qty (##)", "qty (##)", "## units"]


@NODE
def test_the_page_and_the_python_side_read_a_typed_count_alike(tmp_path):
    read = run_js(tmp_path, f"console.log(JSON.stringify({json.dumps(SAMPLES)}.map(parseNumber)));")
    for text, parsed in zip(SAMPLES, read):
        kind, value = review._typed_count(text)
        assert parsed["kind"] == kind, text
        if kind == "number":
            assert parsed["value"] == value, text


@pytest.mark.parametrize("text, value", COUNTS)
def test_python_reads_a_typed_count(text, value):
    assert review._typed_count(text) == ("number", value)


@pytest.mark.parametrize("text", UNREADABLE)
def test_python_does_not_read_a_count_from_words_without_one(text):
    assert review._typed_count(text) == ("words", None)
    assert review._typed_count("") == ("none", None) == review._typed_count("   ")


# ---- the Python side: the file, the apply, the post-check ----------------------------------------------------------

def _save(tmp_path: Path, *decisions: Decision) -> None:
    (tmp_path / "decisions.json").write_text(json.dumps([d.to_dict() for d in decisions]), encoding="utf-8")


@pytest.mark.parametrize("reason", ["5 units", "two", "##", "4 ea"])
def test_a_words_only_family_change_with_a_count_in_it_loads(tmp_path, reason):
    kept = Decision("RTU", "change", family_name="Rooftop Unit", reason=reason)
    _save(tmp_path, kept)
    assert review.load_decisions(tmp_path) == [kept]


@pytest.mark.parametrize("reason", UNREADABLE)
def test_a_words_only_family_change_with_no_count_in_it_is_refused_in_plain_words(tmp_path, reason):
    _save(tmp_path, Decision("RTU", "accept", device_id="RTU.d1"),
          Decision("RTU", "change", family_name="Rooftop Unit", reason=reason))
    with pytest.raises(ModelError) as caught:
        review.load_decisions(tmp_path)
    message = str(caught.value)
    assert "decisions[1]" in message and "Rooftop Unit" in message and repr(reason) in message
    assert "whole number" in message and "changes nothing" in message


@pytest.mark.parametrize("reason, value", [("5 units", 5), ("two", 2), ("##", None), ("4 ea", 4), ("007", 7)])
def test_a_words_only_family_change_sets_the_family_count_when_the_words_hold_one(job, reason, value):
    before = job.system("RTU").families[0].count
    assert before.others                                                  # the sample family has another count
    result = review.apply_decisions(job, [Decision("RTU", "change", family_name="Rooftop Unit", reason=reason)])
    count = result.system("RTU").families[0].count
    assert (count.value, count.others, count.sources) == (value, (), before.sources)
    assert job.system("RTU").families[0].count == before                  # pure


@pytest.mark.parametrize("reason", UNREADABLE)
def test_a_words_only_family_change_with_no_count_in_it_changes_nothing_in_the_job(job, reason):
    assert review.apply_decisions(job, [Decision("RTU", "change", family_name="Rooftop Unit", reason=reason)]) == job


def test_a_count_on_the_decision_wins_over_its_words(job):
    count = Count(value=9, sources=(), others=())
    result = review.apply_decisions(job, [Decision("RTU", "change", family_name="Rooftop Unit", count=count,
                                                   reason="3 units")])
    assert result.system("RTU").families[0].count == count


def test_a_words_only_family_decision_with_no_count_in_it_gets_a_plain_card(job):
    decision = Decision("RTU", "change", family_name="Rooftop Unit", reason="only the roof units")
    (found,) = review.unhonored_decisions(job, [decision], job)
    assert (found.rule, found.system_key, found.device_id, found.severity) == ("decision not honored", "RTU", None,
                                                                                 "check")
    assert "Rooftop Unit" in found.what and "only the roof units" in found.what and "not applied" in found.what
    assert "whole number" in found.fix


def test_a_words_only_family_decision_with_a_count_in_it_gets_no_card_once_it_took_effect(job):
    decision = Decision("RTU", "change", family_name="Rooftop Unit", reason="5 units")
    after = review.apply_decisions(job, [decision])
    assert review.unhonored_decisions(job, [decision], after) == []


# ---- the page ---------------------------------------------------------------------------------------------------------

@pytest.fixture
def page(job, tmp_path) -> str:
    return review.review_page(job, [], tmp_path).read_text(encoding="utf-8")


def test_a_device_card_has_a_name_box_and_says_what_each_box_is_for(page):
    assert page.count('data-field="name"') >= 1
    assert "5 units" in page and "name box" in page
    assert "or new words to rename the line" not in page


def test_the_name_box_starts_with_the_lines_own_name(job, tmp_path):
    text = review.review_page(job, [], tmp_path).read_text(encoding="utf-8")
    assert 'data-field="name" value="Space Temperature Sensor"' in text


def test_the_page_checks_every_answer_before_it_saves_anything():
    script = review._SCRIPT_PAGE
    assert script.index("decisionProblem") < script.index("new Blob")
    assert "Not saved" in script


# ---- an older page saved the words alone: the history gives them the count they say ----------------------------------

def test_the_history_gives_an_older_words_only_family_change_the_count_its_words_say(job):
    """A decisions.json saved before the page read a count from words: no `count`, the words in `reason`. The run
    keeps the decision with the count set on the family's own count (as the page builds it), so everything that reads
    a decision's count sees it (the run's count rewrite included), and the file as saved stays on record."""
    family = job.system("RTU").families[0]
    saved = Decision("RTU", "change", family_name="Rooftop Unit", reason="5 units")
    (entry,) = review.merge_decisions([], [saved], job=job)
    assert entry.decision.count == dataclasses.replace(family.count, value=5, others=())
    assert entry.decision.reason == "5 units" and entry.as_saved == saved and entry.round == 1
    assert review.apply_seen(job, [entry.decision], {}).system("RTU").families[0].count == entry.decision.count
    # reading the same file again adds nothing; an entry already given its count is left alone
    assert review.merge_decisions([entry], [saved], job=job) == [entry]
    assert review.merge_decisions([entry], [], job=job) == [entry]


def test_the_history_gives_an_entry_saved_earlier_its_count_too(job):
    saved = Decision("RTU", "change", family_name="Rooftop Unit", reason="two")
    earlier = review.SavedDecision(saved, 1, took_effect=True, settled="abc")
    (entry,) = review.merge_decisions([earlier], [], job=job)
    assert entry.decision.count.value == 2 and (entry.round, entry.took_effect, entry.settled) == (1, True, "abc")
    assert entry.as_saved == saved


@pytest.mark.parametrize("reason", UNREADABLE)
def test_the_history_leaves_words_with_no_count_as_they_are(job, reason):
    saved = Decision("RTU", "change", family_name="Rooftop Unit", reason=reason)
    (entry,) = review.merge_decisions([], [saved], job=job)
    assert entry.decision == saved and entry.saved is None


def test_the_history_leaves_a_family_the_job_does_not_have_as_it_is(job):
    saved = Decision("RTU", "change", family_name="Supply Fan", reason="5 units")
    assert review.merge_decisions([], [saved], job=job)[0].decision == saved
    assert review.merge_decisions([], [saved])[0].decision == saved                    # no job: nothing to build on


# ---- the whole run -----------------------------------------------------------------------------------------------------

from test_ai import dossier, raw  # noqa: E402,F401  (fixtures)
from test_review_final import _cards, _decision, _drive  # noqa: E402
from test_run import job_folder  # noqa: E402,F401  (a fixture)


def test_an_older_words_only_family_change_is_applied_by_the_whole_run(job_folder, tmp_path, monkeypatch):
    """Run 1 finishes. The estimator's file, saved by a page of before the fix, holds the VAV count change as words
    only ("5 units", no count). Run 2 asks the count rewrite once, ends with the family at 5 and no "decision not
    honored" card: the same end as a count the page built (test_review_final's lifecycle)."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out, cache = tmp_path / "out", tmp_path / "cache"
    _drive(job_folder, out, cache, [])
    family = next(c for c in _cards(out) if c["level"] == "family")
    (out / "decisions.json").write_text(json.dumps([_decision(family, "change", reason="5 units")]),
                                        encoding="utf-8")
    steps: list = []
    second = _drive(job_folder, out, cache, steps)
    assert [stage for _, stage, _ in steps] == ["write", "qc", "done"]            # the count rewrite, QC, the end
    job = json.loads(second.job_file.read_text(encoding="utf-8"))
    system = next(s for s in job["systems"] if s["key"] == family["system_key"])
    assert next(f for f in system["families"] if f["name"] == family["family_name"])["count"]["value"] == 5
    assert not [f for f in second.findings if f.rule == "decision not honored"]
    kept = json.loads((out / "decisions history.json").read_text(encoding="utf-8"))
    assert [(h["decision"]["count"]["value"], h["decision"]["reason"], h["took_effect"]) for h in kept] == [
        (5, "5 units", True)]
