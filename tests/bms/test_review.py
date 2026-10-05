"""Workstream 7: the review page, the decisions and applying them. Invented data only."""
from __future__ import annotations

import dataclasses
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from bms import review
from bms.model import Count, Decision, Finding, Job, ModelError, OtherCount, Ref

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def job() -> Job:
    return Job.from_dict(json.loads((FIXTURES / "sample_job.json").read_text(encoding="utf-8")))


def _page(job, findings, tmp_path) -> str:
    return review.review_page(job, findings, tmp_path).read_text(encoding="utf-8")


def _find(key, device_id, severity="must_fix", what="Something is off"):
    return Finding("Every line cites this job", key, device_id, severity, what, "Look at it")


# ---- the page -----------------------------------------------------------------------------------------------------


def test_page_is_one_self_contained_file(job, tmp_path):
    path = review.review_page(job, [], tmp_path)
    assert path == tmp_path / "Review.html"
    text = path.read_text(encoding="utf-8")
    assert not re.search(r'(?:src|href)="https?:', text) and "http://" not in text and "https://" not in text
    assert "<style>" in text and "<script>" in text
    for system in job.systems:
        assert f"({system.key})" in text
    assert "decisions.json" in text and "out folder" in text
    for word in ("Accept", "Change", "Delete", "Save decisions", "Show all questions"):
        assert word in text


def test_no_questions_still_gives_a_card_per_system(job, tmp_path):
    clean = dataclasses.replace(job, systems=tuple(
        dataclasses.replace(s, devices=(), families=()) for s in job.systems), front_end=None)
    text = _page(clean, [], tmp_path)
    assert text.count('class="card"') >= len(job.systems)
    assert "Nothing to ask here." in text


def test_ranking_must_fix_then_flagged_then_assumptions_then_checks(job, tmp_path):
    findings = [_find("EF", "EF.d1", "check", "check one"), _find("EF", "EF.d2", "must_fix", "must one")]
    ranked = review._ranked(review._questions(job, findings))
    ranks = [q.rank for q in ranked]
    assert ranks == sorted(ranks)
    assert ranks[0] == review.RANK_MUST_FIX and ranks[-1] == review.RANK_CHECK
    assert review.RANK_FLAGGED in ranks
    titles = [q.title for q in ranked]
    assert titles.index("must one") < titles.index("check one")


def test_a_device_with_a_finding_and_a_flag_gets_one_card(job):
    device = next(d for d in job.system("RTU").devices if d.flag != "none")
    questions = review._questions(job, [_find("RTU", device.id, "must_fix", "missing citation")])
    cards = [q for q in questions if q.device_id == device.id]
    assert len(cards) == 1
    assert cards[0].rank == review.RANK_MUST_FIX
    assert cards[0].finding_rule == "Every line cites this job"
    assert any(review._FLAG_WORDS[device.flag] == note for note in cards[0].notes)
    assert any("What to do" in note for note in cards[0].notes)


def test_flagged_devices_and_counts_with_others_and_assumptions_are_questions(job):
    questions = review._questions(job, [])
    flagged = {q.device_id for q in questions if q.rank == review.RANK_FLAGGED and q.device_id}
    assert {"RTU.d4", "VRF.d2", "VRF.d3", "CUH.d1"} <= flagged
    families = {q.family_name for q in questions if q.level == "family"}
    assert "Rooftop Unit" in families            # a contradicted count in `others`
    assert "Cabinet Unit Heater" in families     # an unknown count


def test_cap_about_fifteen_and_show_all(job, tmp_path):
    findings = [_find("EF", None, "check", f"check {n}") for n in range(30)]
    text = _page(job, findings, tmp_path)
    total = len(review._questions(job, findings))
    assert total > review.MAX_QUESTIONS
    assert text.count('class="q extra"') == total - review.MAX_QUESTIONS
    assert text.count('class="q"') == review.MAX_QUESTIONS
    assert "Show all questions" in text


def test_must_fix_never_hidden_behind_the_cap(job, tmp_path):
    findings = [_find("EF", None, "check", f"check {n}") for n in range(30)] + [_find("DH", None, "must_fix", "urgent")]
    text = _page(job, findings, tmp_path)
    shown = re.findall(r'<div class="q" id="q\d+"[^>]*>.*?</div>\s*<div class="buttons">', text, re.S)
    assert any("urgent" in block for block in shown)


def test_count_shows_its_others_and_proof_image(job, tmp_path):
    rtu = job.system("RTU")
    proof = Ref("S9", "RTU-1 RTU-2 RTU-3", "M-102, proof/rtu-count.png")
    family = dataclasses.replace(rtu.families[0], count=Count(
        3, (proof,), (OtherCount(2, Ref("S3", "RTU-1 RTU-2", "M-101, Drawings.pdf page 2")),)))
    text = _page(job.with_system(dataclasses.replace(rtu, families=(family,))), [], tmp_path)
    assert 'src="proof/rtu-count.png"' in text
    assert "The other counts" in text and "RTU-1 RTU-2" in text and "Printed count: 3" in text


def test_only_relative_images(job):
    assert review.proof_image(Ref("S1", "x", "see crops/EF-1.PNG here")) == "crops/EF-1.PNG"
    assert review.proof_image(Ref("S1", "x", "C:/secret/a.png")) is None
    assert review.proof_image(Ref("S1", "x", "/etc/a.png")) is None
    assert review.proof_image(Ref("S1", "x", "https://example.com/a.png")) is None
    assert review.proof_image(Ref("S1", "x", "../up/a.png")) is None
    assert review.proof_image(Ref("S1", "x", "M-001, Drawings.pdf page 1")) is None


def test_text_is_escaped(job, tmp_path):
    text = _page(job, [_find("EF", None, "must_fix", "<script>alert(1)</script> & more")], tmp_path)
    assert "<script>alert(1)</script>" not in text
    assert "&lt;script&gt;alert(1)&lt;/script&gt; &amp; more" in text


def test_front_end_and_whole_job_findings_get_cards(job, tmp_path):
    text = _page(job, [_find("", None, "must_fix", "whole job thing"), _find("ZZ", None, "check", "unknown system")],
                 tmp_path)
    assert "Front end and whole job" in text and "whole job thing" in text and ">ZZ<" in text


def test_page_data_matches_the_decision_form(job, tmp_path):
    text = _page(job, [], tmp_path)
    data = [json.loads(m) for m in re.findall(r'class="qdata">(.*?)</script>', text, re.S)]
    assert data
    device_q = next(q for q in data if q["level"] == "device")
    from bms.model import Device
    Device.from_dict(device_q["device"])


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_saved_decisions_load_back_into_decisions(job, tmp_path):
    """Run the page's own decision builder in node and read what it makes with load_decisions."""
    text = _page(job, [_find("EF", "EF.d1", "must_fix", "needs a look")], tmp_path)
    core = re.search(r"<script>(.*?)</script>\s*</body>", text, re.S).group(1)
    core = core.split("var questions = {}, states = {};")[0]
    qdata = re.findall(r'class="qdata">(.*?)</script>', text, re.S)
    harness = core + """
var qs = %s.map(function (s) { return JSON.parse(s); });
var out = [];
qs.forEach(function (q) {
  var a = buildDecision(q, {action: "accept"}); out.push(a);
  var c = buildDecision(q, {action: "change", text: q.level === "device" ? "7" : "##",
                            fields: {verb: "Furnish", furnished_by: "AME"}}); out.push(c);
  out.push(buildDecision(q, {action: "delete"}));
});
out.push(buildDecision(qs[0], {}));
console.log(JSON.stringify(out.filter(Boolean)));
""" % json.dumps(qdata)
    script = tmp_path / "h.js"
    script.write_text(harness, encoding="utf-8")
    done = subprocess.run(["node", str(script)], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    made = json.loads(done.stdout)
    (tmp_path / "decisions.json").write_text(json.dumps(made), encoding="utf-8")
    decisions = review.load_decisions(tmp_path)
    assert len(decisions) == len(made) and len(made) % 3 == 0
    changes = [d for d in decisions if d.action == "change" and d.device is not None]
    assert changes and all(d.device.quantity.value == 7 and d.device.flag == "none" for d in changes)
    assert any(d.action == "change" and d.count is not None and d.count.value is None for d in decisions)


# ---- load_decisions ----------------------------------------------------------------------------------------------


def test_load_missing_is_empty(tmp_path):
    assert review.load_decisions(tmp_path) == []


def test_load_round_trip(tmp_path):
    decisions = [Decision("EF", "accept", device_id="EF.d1"), Decision("RTU", "delete", reason="not ours")]
    (tmp_path / "decisions.json").write_text(json.dumps([d.to_dict() for d in decisions]), encoding="utf-8")
    assert review.load_decisions(tmp_path) == decisions


@pytest.mark.parametrize("content, word", [
    ("not json", "not valid JSON"),
    ('{"a": 1}', "expected a list"),
    ('[{"system_key": "EF", "action": "maybe"}]', "decisions[0]"),
    ('[{"system_key": "EF", "action": "accept"}, {"action": "accept"}]', "decisions[1]"),
])
def test_load_malformed_names_the_entry(tmp_path, content, word):
    (tmp_path / "decisions.json").write_text(content, encoding="utf-8")
    with pytest.raises(ModelError, match=re.escape(word)):
        review.load_decisions(tmp_path)


# ---- apply_decisions ---------------------------------------------------------------------------------------------


def test_accept_clears_the_flag(job):
    assert job.system("RTU").devices[3].flag == "assumed"
    result = review.apply_decisions(job, [Decision("RTU", "accept", device_id="RTU.d4")])
    assert result.system("RTU").devices[3].flag == "none"
    assert result.system("RTU").devices[3].assumption == job.system("RTU").devices[3].assumption
    assert job.system("RTU").devices[3].flag == "assumed"       # pure: the original is untouched


def test_delete_a_device_and_a_system(job):
    result = review.apply_decisions(job, [Decision("EF", "delete", device_id="EF.d2"), Decision("DH", "delete")])
    assert [d.id for d in result.system("EF").devices] == ["EF.d1", "EF.d3"]
    assert [s.key for s in result.systems] == [s.key for s in job.systems if s.key != "DH"]


def test_change_a_device_keeps_the_id(job):
    new = dataclasses.replace(job.system("EF").devices[0], id="other", name="Changed", quantity=Count(9))
    result = review.apply_decisions(job, [Decision("EF", "change", device_id="EF.d1", device=new)])
    changed = result.system("EF").devices[0]
    assert (changed.id, changed.name, changed.quantity.value) == ("EF.d1", "Changed", 9)


def test_accept_a_family_clears_quantity_flags_and_leaves_other_flags(job):
    system = job.system("EF")
    devices = list(system.devices)
    devices[0] = dataclasses.replace(devices[0], flag="quantity")
    devices[1] = dataclasses.replace(devices[1], flag="assumed")
    job2 = job.with_system(dataclasses.replace(system, devices=tuple(devices)))
    family = job2.system("EF").families[0].name
    result = review.apply_decisions(job2, [Decision("EF", "accept", family_name=family)])
    flags = [d.flag for d in result.system("EF").devices]
    assert flags[0] == "none" and flags[1] == "assumed"
    assert result.system("EF").families == job2.system("EF").families
    assert review.apply_decisions(job2, [Decision("EF", "accept", family_name="No such family")]) == job2


def test_change_a_family_count(job):
    result = review.apply_decisions(job, [Decision("CUH", "change", family_name="Cabinet Unit Heater",
                                                   count=Count(4))])
    assert result.system("CUH").families[0].count.value == 4


def test_front_end_devices_use_the_empty_system_key(job):
    front = job.front_end
    if not front or not front.devices:
        pytest.skip("sample job has no front-end devices")
    first = front.devices[0]
    result = review.apply_decisions(job, [Decision("", "delete", device_id=first.id)])
    assert first.id not in [d.id for d in result.front_end.devices]


def test_unknown_things_are_skipped_and_order_matters(job):
    skipped = [Decision("NOPE", "delete"), Decision("EF", "delete", device_id="EF.zz"),
               Decision("EF", "change", family_name="Nothing", count=Count(1)),
               Decision("EF", "accept"), Decision("EF", "change"), Decision("", "delete")]
    assert review.apply_decisions(job, skipped) == job
    again = review.apply_decisions(job, [Decision("EF", "delete", device_id="EF.d1"),
                                         Decision("EF", "accept", device_id="EF.d1")])
    assert [d.id for d in again.system("EF").devices] == ["EF.d2", "EF.d3"]
    gone = review.apply_decisions(job, [Decision("DH", "delete"), Decision("DH", "accept", device_id="DH.d1")])
    assert "DH" not in [s.key for s in gone.systems]


# ---- a decision the last write undid -------------------------------------------------------------------------------


def test_reusing_a_deleted_devices_id_is_honored_when_the_line_is_a_different_one(job):
    system = job.system("EF")
    deleted, kept = system.devices[0], system.devices[1]
    assert deleted.name != kept.name
    after = job.with_system(dataclasses.replace(
        system, devices=(dataclasses.replace(kept, id=deleted.id), *system.devices[2:])))
    assert review.unhonored_decisions(job, [Decision("EF", "delete", device_id=deleted.id)], after) == []


def test_a_deleted_line_that_comes_back_under_a_new_id_is_not_honored(job, tmp_path):
    system = job.system("EF")
    deleted, kept = system.devices[0], system.devices[1]
    after = job.with_system(dataclasses.replace(system, devices=(
        dataclasses.replace(kept, id="EF.d1"), dataclasses.replace(deleted, id="EF.d9"))))
    findings = review.unhonored_decisions(job, [Decision("EF", "delete", device_id=deleted.id)], after)
    assert [f.severity for f in findings] == ["must_fix"]
    assert findings[0].what == f"decision not honored: delete {deleted.id}"
    assert findings[0].device_id == "EF.d9"
    assert "decision not honored" in _page(after, findings, tmp_path)


def test_a_deleted_system_holds_only_while_it_stays_gone(job):
    decision = Decision("DH", "delete")
    applied = review.apply_decisions(job, [decision])
    assert review.unhonored_decisions(job, [decision], applied) == []
    assert review.unhonored_decisions(job, [decision], job)[0].what == "decision not honored: delete DH"


def test_a_changed_device_holds_when_its_content_survives_a_new_id(job):
    old = job.system("EF").devices[0]
    new = dataclasses.replace(old, name="Changed sensor", quantity=Count(9))
    decision = Decision("EF", "change", device_id=old.id, device=new)
    applied = review.apply_decisions(job, [decision])
    changed = applied.system("EF").devices[0]
    after = job.with_system(dataclasses.replace(
        applied.system("EF"),
        devices=tuple(dataclasses.replace(device, id="EF.d8") if device.id == changed.id else device
                      for device in applied.system("EF").devices)))
    assert review.unhonored_decisions(job, [decision], after) == []
    undone = review.unhonored_decisions(job, [decision], job)
    assert undone[0].what == f"decision not honored: change {old.id}"


def test_a_changed_family_count_holds_only_while_the_family_keeps_it(job):
    decision = Decision("CUH", "change", family_name="Cabinet Unit Heater", count=Count(4))
    applied = review.apply_decisions(job, [decision])
    assert review.unhonored_decisions(job, [decision], applied) == []
    assert "decision not honored: change Cabinet Unit Heater" in review.unhonored_decisions(
        job, [decision], job)[0].what


def test_an_accepted_device_holds_when_the_line_stays_and_not_when_it_is_dropped(job):
    system = job.system("RTU")
    kept = next(device for device in system.devices if device.id == "RTU.d4")
    decision = Decision("RTU", "accept", device_id="RTU.d4")
    renumbered = job.with_system(dataclasses.replace(system, devices=tuple(
        dataclasses.replace(device, id="RTU.d9", flag="none") if device.id == "RTU.d4" else device
        for device in system.devices)))
    assert review.unhonored_decisions(job, [decision], renumbered) == []
    dropped = job.with_system(dataclasses.replace(
        system, devices=tuple(device for device in system.devices if device.id != "RTU.d4")))
    assert review.unhonored_decisions(job, [decision], dropped)[0].what == "decision not honored: accept RTU.d4"
    assert kept.name


def test_an_accept_whose_flag_came_back_is_not_honored(job):
    system = job.system("RTU")
    decision = Decision("RTU", "accept", device_id="RTU.d4")
    reflagged = job.with_system(dataclasses.replace(system, devices=tuple(
        dataclasses.replace(device, id="RTU.d9", flag="quantity") if device.id == "RTU.d4" else device
        for device in system.devices)))
    findings = review.unhonored_decisions(job, [decision], reflagged)
    assert findings and findings[0].what == "decision not honored: accept RTU.d4"
    assert findings[0].severity == "must_fix"


def test_apply_decisions_with_was_deletes_matching_device_when_ids_differ(job):
    system = job.system("EF")
    target = system.devices[2]
    # Decision was made on revised page where target had id EF.d1
    decision = Decision("EF", "delete", device_id="EF.d1", was=target)
    applied = review.apply_decisions(job, [decision])
    assert not any(d.name == target.name for d in applied.system("EF").devices)
    assert len(applied.system("EF").devices) == len(system.devices) - 1


def test_apply_decisions_with_duplicate_identical_devices_deletes_named_id(job):
    system = job.system("EF")
    d1 = dataclasses.replace(system.devices[0], id="EF.d1")
    d2 = dataclasses.replace(system.devices[0], id="EF.d2")
    job_dup = job.with_system(dataclasses.replace(system, devices=(d1, d2)))
    decision = Decision("EF", "delete", device_id="EF.d2", was=d2)
    applied = review.apply_decisions(job_dup, [decision])
    remaining = applied.system("EF").devices
    assert len(remaining) == 1
    assert remaining[0].id == "EF.d1"


def test_apply_decisions_with_stale_nonmatching_was_does_not_delete_reused_id(job):
    system = job.system("EF")
    d1 = system.devices[0]
    stale_was = dataclasses.replace(d1, name="Completely Different Nonexistent Sensor")
    decision = Decision("EF", "delete", device_id=d1.id, was=stale_was)
    applied = review.apply_decisions(job, [decision])
    # The unrelated line d1 is retained
    assert any(d.id == d1.id for d in applied.system("EF").devices)
    assert len(applied.system("EF").devices) == len(system.devices)


def test_a_decision_that_names_nothing_on_the_job_is_not_a_finding(job):
    assert review.unhonored_decisions(job, [Decision("EF", "delete", device_id="EF.zz"),
                                            Decision("NOPE", "delete")], job) == []
